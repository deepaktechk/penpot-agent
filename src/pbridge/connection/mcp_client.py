"""Minimal MCP client (streamable HTTP, JSON-RPC 2.0) for the Penpot MCP server.

Responsibilities:
  * session handshake (`initialize` + `notifications/initialized`), re-created when it expires
  * replies as plain JSON or as Server-Sent Events
  * retries with backoff when the server is unreachable
  * the Penpot-specific "plugin tab suspended" state: notify the user and wait

Penpot tools used by pbridge: `execute_code` (run JS in the plugin) and `export_shape`.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from pbridge import __version__
from pbridge.connection.discovery import redact
from pbridge.connection.errors import MCPError, PluginError, PluginSuspended
from pbridge.connection.notifier import notify

PROTOCOL_VERSION = "2025-03-26"

# name the client honestly: Cloudflare (design.penpot.app) rejects urllib's default
# "Python-urllib/3.x" signature with error 1010
USER_AGENT = f"pbridge/{__version__}"

# substrings of a tool error that mean "the plugin tab is asleep / not connected"
SUSPENDED_MARKERS = ("suspended", "heartbeat", "not connected", "no plugin", "no client", "plugin is not")


@dataclass
class ToolResult:
    """Decoded `tools/call` result."""

    text: str                          # all text content blocks joined with "\n"
    images: list[tuple[str, bytes]]    # (mime type, bytes) of image / blob blocks
    raw: dict[str, Any]
    is_error: bool

    def json(self) -> dict[str, Any]:
        """`execute_code` answers with '{"result": ..., "log": ...}' as text."""
        try:
            return json.loads(self.text)
        except json.JSONDecodeError:
            return {"result": self.text, "log": ""}


def _parse_sse(body: str, want_id: int) -> dict[str, Any] | None:
    """Return the JSON-RPC message with id `want_id` from an SSE body (last one wins)."""
    wanted, data_lines = None, []
    for line in body.splitlines() + [""]:
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line == "" and data_lines:   # blank line = end of one event
            try:
                message = json.loads("\n".join(data_lines))
            except json.JSONDecodeError:
                message = None
            data_lines = []
            if isinstance(message, dict) and message.get("id") == want_id:
                wanted = message
    return wanted


def _decode_content(blocks: list[dict[str, Any]]) -> tuple[list[str], list[tuple[str, bytes]]]:
    """Split MCP content blocks into texts and binary payloads."""
    texts: list[str] = []
    images: list[tuple[str, bytes]] = []
    for block in blocks:
        if block.get("type") == "text":
            texts.append(block.get("text", ""))
        elif block.get("type") == "image":
            images.append((block.get("mimeType", "image/png"), base64.b64decode(block.get("data", ""))))
        elif block.get("type") == "resource" and block.get("resource", {}).get("blob"):
            resource = block["resource"]
            images.append((resource.get("mimeType", "application/octet-stream"), base64.b64decode(resource["blob"])))
    return texts, images


class MCPClient:
    def __init__(self, url: str, timeout: float = 120, retries: int = 4, verbose: bool = False):
        self.url = url
        self.timeout = timeout
        self.retries = retries
        self.verbose = verbose
        self.session_id: str | None = None
        self._id = 0
        self.server_info: dict[str, Any] = {}

    # ------------------------------------------------------------------ transport
    def _post(self, body: dict[str, Any], timeout: float | None = None) -> dict[str, Any] | None:
        """POST one JSON-RPC message. Notifications (no "id") return None."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": USER_AGENT,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(self.url, json.dumps(body).encode(), headers)
        try:
            response = urllib.request.urlopen(request, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as error:
            message = error.read().decode(errors="replace")[:500]
            raise MCPError(f"HTTP {error.code}: {redact(message)}") from None
        except urllib.error.URLError as error:
            raise MCPError(f"cannot reach Penpot MCP server ({redact(error.reason)}) - is the MCP server running?") from None
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self.session_id = session_id
        content_type = response.headers.get("Content-Type", "")
        data = response.read().decode("utf-8", errors="replace")
        if "id" not in body:
            return None
        if "text/event-stream" in content_type or data.startswith("event:") or data.startswith("data:"):
            return _parse_sse(data, body["id"])
        return json.loads(data) if data.strip() else None

    # kept as a static method for callers/tests that used MCPClient._parse_sse
    _parse_sse = staticmethod(_parse_sse)

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    # ------------------------------------------------------------------ protocol
    def connect(self) -> dict[str, Any]:
        """Open a fresh MCP session; returns the server info."""
        self.session_id = None
        reply = self._post({"jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
                            "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                       "clientInfo": {"name": "pbridge", "version": "1.0"}}}, timeout=30)
        if not reply or "result" not in reply:
            raise MCPError(f"initialize failed: {redact(reply)}")
        self.server_info = reply["result"].get("serverInfo", {})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=30)
        return self.server_info

    def rpc(self, method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> Any:
        """One JSON-RPC request; reconnects once if the session expired."""
        if not self.session_id:
            self.connect()
        body = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params or {}}
        reply = self._post(body, timeout)
        if reply is None:
            raise MCPError(f"no response for {method}")
        if "error" in reply:
            error = reply["error"]
            if "session" in str(error).lower():
                self.connect()
                reply = self._post(body, timeout)
                if "error" not in reply:
                    return reply["result"]
            raise MCPError(redact(json.dumps(error)))
        return reply["result"]

    def list_tools(self) -> list[str]:
        return [tool["name"] for tool in self.rpc("tools/list")["tools"]]

    # ------------------------------------------------------------------ plugin availability
    def wait_for_plugin(self, why: str = "") -> bool:
        """Block until the Penpot plugin answers again (the user focuses its tab).

        Notifies once (terminal bell + desktop notification), then pings every 5 s.
        Max wait = env PBRIDGE_WAIT seconds (default 600; 0 disables waiting).
        Returns True if the plugin came back.
        """
        limit = float(os.environ.get("PBRIDGE_WAIT", "600"))
        if limit <= 0:
            return False
        print("\a[pbridge] Penpot plugin is asleep (browser throttled the tab). Click the Penpot tab to resume - waiting…",
              file=sys.stderr, flush=True)
        notify("pbridge: Penpot tab asleep", "Click the Penpot tab so the bridge can continue")
        started = time.time()
        while time.time() - started < limit:
            time.sleep(5)
            try:
                reply = self.rpc("tools/call", {"name": "execute_code", "arguments": {"code": "return 1;"}}, timeout=20)
                text = "".join(block.get("text", "") for block in reply.get("content", []))
                if not reply.get("isError") and not text.startswith("Tool execution failed"):
                    print(f"[pbridge] plugin is back after {time.time() - started:.0f}s", file=sys.stderr, flush=True)
                    return True
            except MCPError:
                pass
        return False

    # ------------------------------------------------------------------ tools
    def call(self, name: str, arguments: dict[str, Any], timeout: float | None = None) -> ToolResult:
        """`tools/call` with retries.

        * server unreachable -> exponential backoff, new session
        * plugin suspended   -> wait for the user, then retry
        * any other tool error -> PluginError (carries the JS message/stack)
        """
        delay = 2.0
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                reply = self.rpc("tools/call", {"name": name, "arguments": arguments}, timeout)
            except MCPError as error:
                last = error
                if "cannot reach" in str(error) and attempt < self.retries:
                    time.sleep(delay); delay *= 1.7; self.session_id = None
                    continue
                raise
            texts, images = _decode_content(reply.get("content", []))
            text = "\n".join(texts)
            failed = bool(reply.get("isError")) or text.startswith("Tool execution failed")
            result = ToolResult(text=text, images=images, raw=reply, is_error=failed)
            if not result.is_error:
                return result
            if any(marker in text.lower() for marker in SUSPENDED_MARKERS):
                last = PluginSuspended(text)
                if self.wait_for_plugin(text):
                    continue
                if attempt < self.retries:
                    if self.verbose:
                        print(f"[pbridge] plugin unavailable, retry {attempt + 1}/{self.retries} in {delay:.0f}s", file=sys.stderr)
                    time.sleep(delay); delay *= 1.7
                    continue
                raise PluginSuspended("Penpot plugin is suspended/disconnected: click the Penpot tab (keep it visible) and retry.\n" + text)
            raise PluginError(text)
        raise last or MCPError("call failed")
