"""Find the Penpot MCP endpoint and keep its token out of every output.

Resolution order:
  1. env PENPOT_MCP_URL
  2. <project>/.pbridge/config.json  {"mcp_url": ...}
  3. .mcp.json in the project folder or a parent (Claude Code project-scoped MCP servers)
  4. ~/.claude.json  (Claude Code user/local scope: `claude mcp add`, `npx add-mcp -g`)
In 3 and 4, the first `mcpServers` entry whose name contains "penpot" (any case) is used.

The URL embeds a user token (`?userToken=...`): it is never printed or logged.
Anything that may contain it must go through `redact()` first.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from pbridge.project import ProjectState


def _collect_penpot_urls(config: Any, found: list[str]) -> None:
    """Depth-first search of a Claude config for `mcpServers.<*penpot*>.url`."""
    if isinstance(config, dict):
        for key, value in config.items():
            if key == "mcpServers" and isinstance(value, dict):
                for name, server in value.items():
                    if "penpot" in name.lower() and isinstance(server, dict) and server.get("url"):
                        found.append(server["url"])
            _collect_penpot_urls(value, found)


def _urls_in(config_file: Path) -> list[str]:
    """Penpot MCP URLs configured in a JSON file (missing or unreadable file -> [])."""
    found: list[str] = []
    try:
        _collect_penpot_urls(json.loads(config_file.read_text()), found)
    except (OSError, json.JSONDecodeError):
        pass
    return found


def discover_mcp_url(state: ProjectState | None = None) -> str:
    if os.environ.get("PENPOT_MCP_URL"):
        return os.environ["PENPOT_MCP_URL"]
    if state and state.config.get("mcp_url"):
        return state.config["mcp_url"]
    start = state.root if state else Path.cwd()
    for folder in [start, *start.parents]:
        found = _urls_in(folder / ".mcp.json")
        if found:
            return found[0]
    found = _urls_in(Path.home() / ".claude.json")
    if found:
        return found[0]
    raise RuntimeError("Penpot MCP URL not found: add the Penpot MCP server to Claude Code (name containing 'penpot') "
                       "or set PENPOT_MCP_URL - see docs/penpot-setup.md")


def redact(text: object) -> str:
    """Remove user tokens from any string before showing it."""
    return re.sub(r"(userToken=)[^&\s\"']+", r"\1***", str(text))
