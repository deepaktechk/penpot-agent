"""Penpot backend API client (personal access token), for work that does not need the browser tab.

The MCP plugin runs inside one browser tab: single-threaded, ~100 KB per request, tasks killed
after ~120 s, throttled when the tab is hidden. Bulk transfers (image uploads, whole-file imports)
go straight to the backend instead, where requests can run in parallel.

Calls are `POST <base>/api/main/methods/<method>` with a JSON body (the path since Penpot 2.12;
design.penpot.app answers 403 on the old /api/rpc/command/ path). The token comes from env
PENPOT_ACCESS_TOKEN only and every error goes through `redact()`.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from pbridge import __version__
from pbridge.connection.discovery import access_token, discover_backend_url, redact
from pbridge.connection.errors import MCPError
from pbridge.project import ProjectState

# Cloudflare (design.penpot.app) rejects urllib's default "Python-urllib/3.x" signature
USER_AGENT = f"pbridge/{__version__}"


class BackendError(MCPError):
    """The backend API refused or failed a call (bad token, unknown method, server error)."""


class BackendClient:
    def __init__(self, state: ProjectState | None = None, timeout: float = 120):
        token = access_token()
        if not token:
            raise BackendError("no Penpot access token: create one in Penpot (Your account → Access tokens) "
                               "and set PENPOT_ACCESS_TOKEN in your shell - see docs/fast-build.md")
        self.base_url = discover_backend_url(state)
        self.timeout = timeout
        self._token = token

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> Any:
        """One backend method call with a JSON body; returns the decoded JSON reply."""
        request = urllib.request.Request(
            f"{self.base_url}/api/main/methods/{method}",
            data=json.dumps(params or {}).encode(),
            headers={"Authorization": f"Token {self._token}", "Content-Type": "application/json",
                     "Accept": "application/json", "User-Agent": USER_AGENT},
            method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            message = error.read().decode(errors="replace")[:500]
            raise BackendError(f"{method}: HTTP {error.code}: {redact(message)}") from None
        except urllib.error.URLError as error:
            raise BackendError(f"{method}: cannot reach the Penpot backend ({redact(error.reason)})") from None
        return json.loads(body) if body.strip() else None
