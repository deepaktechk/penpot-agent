"""Run JavaScript inside the Penpot plugin with the pbridge runtime (`pb`) in scope.

How a call works:
  1. The plugin runtime (bundles/plugin-runtime.js, built from js/src/plugin) is stored in
     the plugin's `storage.pb`. It is injected lazily and re-injected automatically after a
     plugin reload: every call starts with a version check (sha1 of the bundle).
  2. `exec(body, data)` wraps `body` so that `pb`, `DATA` and `penpot` are in scope and JS
     exceptions come back as `{__pb_error: stack}` -> PluginError.
  3. `data` is sent inline when small, otherwise in chunks (the server rejects requests
     above ~100 KB) that the runtime reassembles (`pb.chunkPut` / `pb.chunkTake`).

Image descriptors uploaded earlier (.pbridge/assets.json) are re-registered after every
re-injection, so images never need re-uploading.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import uuid
from typing import Any

from pbridge.connection.discovery import discover_mcp_url
from pbridge.connection.errors import PluginError
from pbridge.connection.mcp_client import MCPClient
from pbridge.paths import PLUGIN_RUNTIME, js_bundle
from pbridge.project import ProjectState

MAX_REQUEST = 90_000      # bytes of JSON request body allowed per call (server limit ~100 KB)
CHUNK = 60_000            # characters per data chunk
VERSION_PLACEHOLDER = "__PB_VERSION__"


class Bridge:
    def __init__(self, state: ProjectState | None = None, verbose: bool = False):
        self.state = state or ProjectState.open()
        self.client = MCPClient(discover_mcp_url(self.state), verbose=verbose)
        self.verbose = verbose
        bundle = js_bundle(PLUGIN_RUNTIME).read_text()
        self.version = hashlib.sha1(bundle.encode()).hexdigest()[:10]
        self.runtime_source = bundle.replace(VERSION_PLACEHOLDER, self.version)
        self.calls = 0   # number of execute_code round trips (profiling)

    # ------------------------------------------------------------------ low level
    def _raw(self, code: str, timeout: float | None = None) -> dict[str, Any]:
        """One `execute_code` call, no wrapping. Returns {"result": ..., "log": ...}."""
        self.calls += 1
        result = self.client.call("execute_code", {"code": code}, timeout=timeout)
        if result.is_error:
            raise PluginError(result.text)
        return result.json()

    def _runtime_current_js(self) -> str:
        return f"(storage.pb && storage.pb.version === '{self.version}')"

    def ensure_prelude(self, force: bool = False) -> bool:
        """Inject the plugin runtime if missing or outdated. Returns True if it was injected."""
        if not force:
            reply = self._raw(f"return !!{self._runtime_current_js()};")
            if reply.get("result") is True:
                return False
        if len(self.runtime_source) > MAX_REQUEST:
            raise RuntimeError("plugin runtime too large for one request; split it")
        # the bundle is an IIFE that stores itself in storage.pb; then report its version
        reply = self._raw(self.runtime_source + "\nreturn storage.pb && storage.pb.version;")
        if reply.get("result") != self.version:
            raise PluginError(f"prelude injection failed: {str(reply)[:300]}")
        self._restore_images()
        return True

    def _restore_images(self) -> None:
        assets = self.state.load_json("assets.json", {})
        descriptors = {key: entry["image"] for key, entry in assets.items() if entry.get("image")}
        if descriptors:
            self.exec("return pb.registerImages(DATA);", data=descriptors, _prelude_checked=True)

    # ------------------------------------------------------------------ data transfer
    def _send_chunks(self, text: str) -> str:
        """Upload `text` in pieces into the runtime's chunk store; returns the chunk id."""
        chunk_id = uuid.uuid4().hex[:12]
        parts = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)]
        for i, part in enumerate(parts):
            self._raw(f"return storage.pb.chunkPut({json.dumps(chunk_id)}, {i}, {len(parts)}, {json.dumps(part)});")
        return chunk_id

    # ------------------------------------------------------------------ public exec
    def exec(self, body: str, data: Any = None, timeout: float | None = None,
             _prelude_checked: bool = False, idempotent: bool = False) -> Any:
        """Run JS `body` (may use `await`, `pb`, `DATA`, `penpot`) and return its value.

        idempotent=True means the call is safe to repeat, so a server-side task timeout
        (throttled tab, ~120 s kill) is retried after waiting for the plugin. Never set it
        for relative edits (moves, appends): a retry would apply them twice.
        """
        for attempt in range(3 if idempotent else 1):
            try:
                return self._exec(body, data, timeout, _prelude_checked)
            except PluginError as error:
                if not (idempotent and "timed out" in str(error)) or attempt == 2:
                    raise
                self.client.wait_for_plugin("task timed out")

    def _exec(self, body: str, data: Any = None, timeout: float | None = None, _prelude_checked: bool = False) -> Any:
        if data is not None:
            data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            if len(data_json) + len(body) > MAX_REQUEST - 2000:
                chunk_id = self._send_chunks(data_json)
                head = f"const DATA = JSON.parse(pb.chunkTake({json.dumps(chunk_id)}));\n"
            else:
                head = f"const DATA = {data_json};\n"
        else:
            head = ""
        # a runtime from an older build (or none at all) answers {__pb_need_prelude: true}
        guard = "" if _prelude_checked else f"if (!{self._runtime_current_js()}) return {{__pb_need_prelude: true}};\n"
        code = (guard + "const pb = storage.pb;\ntry {\n" + head + body +
                "\n} catch (error) { return {__pb_error: String((error && error.stack) || error), __pb_warn: pb && pb.warnings}; }")
        if len(code) > MAX_REQUEST and data is None:
            raise RuntimeError(f"code too large ({len(code)} bytes); pass bulk content through data=")
        for _ in range(3):
            started = time.time()
            reply = self._raw(code, timeout=timeout)
            if self.verbose:
                print(f"[exec {time.time() - started:6.2f}s] {body.strip().splitlines()[0][:70]}", file=sys.stderr)
            value = reply.get("result")
            if isinstance(value, dict) and value.get("__pb_need_prelude"):
                self.ensure_prelude(force=True)
                if data is not None and "chunkTake" in head:   # the chunks lived in the old runtime
                    return self._exec(body, data, timeout)
                continue
            if isinstance(value, dict) and "__pb_error" in value:
                raise PluginError(value["__pb_error"])
            if reply.get("log") and self.verbose:
                print("[plugin log]", reply["log"])
            return value
        raise PluginError("prelude injection loop")
