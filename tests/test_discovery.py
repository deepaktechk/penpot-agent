"""Finding the Penpot MCP URL, and keeping its token out of every output."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pbridge.connection.discovery import discover_mcp_url, redact
from pbridge.project import ProjectState

TOKEN_URL = "http://localhost:9001/mcp/stream?userToken=secret123"


class Discovery(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="pb-home-"))
        self.project = self.home / "work" / "site"
        self.project.mkdir(parents=True)
        self.state = ProjectState(root=self.project)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patcher.start(); self.addCleanup(patcher.stop)
        os.environ.pop("PENPOT_MCP_URL", None)

    def write(self, path: Path, servers: dict) -> None:
        path.write_text(json.dumps({"mcpServers": servers}))

    def test_environment_variable_wins(self):
        self.write(self.home / ".claude.json", {"penpot": {"url": "http://from-claude-json"}})
        with mock.patch.dict(os.environ, {"PENPOT_MCP_URL": "http://from-env"}):
            self.assertEqual(discover_mcp_url(self.state), "http://from-env")

    def test_project_config_before_claude_configs(self):
        self.state.config["mcp_url"] = "http://from-project"
        self.write(self.home / ".claude.json", {"penpot": {"url": "http://from-claude-json"}})
        self.assertEqual(discover_mcp_url(self.state), "http://from-project")

    def test_project_scoped_mcp_json_in_a_parent_folder(self):
        self.write(self.home / "work" / ".mcp.json", {"Penpot-Design": {"type": "http", "url": "http://from-mcp-json"}})
        self.assertEqual(discover_mcp_url(self.state), "http://from-mcp-json")

    def test_nested_local_scope_entry_in_claude_json(self):
        # `claude mcp add` (local scope) nests servers under projects/<path>/mcpServers
        config = {"projects": {"/somewhere": {"mcpServers": {"other": {"url": "http://x"}, "penpot": {"url": TOKEN_URL}}}}}
        (self.home / ".claude.json").write_text(json.dumps(config))
        self.assertEqual(discover_mcp_url(self.state), TOKEN_URL)

    def test_missing_configuration_explains_what_to_do(self):
        with self.assertRaises(RuntimeError) as raised:
            discover_mcp_url(self.state)
        self.assertIn("PENPOT_MCP_URL", str(raised.exception))

    def test_token_is_redacted(self):
        self.assertEqual(redact(f"cannot reach {TOKEN_URL}&x=1"), "cannot reach http://localhost:9001/mcp/stream?userToken=***&x=1")


if __name__ == "__main__":
    unittest.main()
