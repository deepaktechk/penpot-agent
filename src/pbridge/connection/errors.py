"""Error types raised while talking to Penpot."""
from __future__ import annotations


class MCPError(RuntimeError):
    """Transport or protocol failure (server down, HTTP error, bad JSON-RPC reply)."""


class PluginSuspended(MCPError):
    """The browser throttled or closed the Penpot tab running the MCP plugin.

    The user has to focus (or reopen) that tab; nothing else fixes it.
    """


class PluginError(MCPError):
    """JavaScript raised inside the Penpot plugin, or a plugin task was killed (~120 s limit)."""
