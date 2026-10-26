"""Finding the Penpot MCP URL, and keeping its token out of every output."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from pbridge.connection.backend import BackendClient, BackendError
from pbridge.connection.discovery import access_token, discover_backend_url, discover_mcp_url, redact
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


ACCESS_TOKEN = "eyJhbGciOiJBMjU2S1ciLCJlbmMiOiJBMjU2R0NNIn0.secret-part"


class Backend(unittest.TestCase):
    """Penpot backend API (access token): base URL and token discovery, token redaction."""

    def setUp(self):
        self.state = ProjectState(root=Path(tempfile.mkdtemp(prefix="pb-site-")))
        patcher = mock.patch.dict(os.environ, {})
        patcher.start(); self.addCleanup(patcher.stop)
        os.environ.pop("PENPOT_URL", None); os.environ.pop("PENPOT_ACCESS_TOKEN", None)

    def test_default_backend_is_design_penpot_app(self):
        self.assertEqual(discover_backend_url(self.state), "https://design.penpot.app")

    def test_backend_url_from_environment_then_project_config(self):
        self.state.config["penpot_url"] = "http://localhost:9001/"
        self.assertEqual(discover_backend_url(self.state), "http://localhost:9001")
        with mock.patch.dict(os.environ, {"PENPOT_URL": "https://penpot.example.com/"}):
            self.assertEqual(discover_backend_url(self.state), "https://penpot.example.com")

    def test_access_token_only_from_environment(self):
        self.state.config["access_token"] = "never-read-from-project-files"
        self.assertIsNone(access_token())
        with mock.patch.dict(os.environ, {"PENPOT_ACCESS_TOKEN": f"  {ACCESS_TOKEN}\n"}):
            self.assertEqual(access_token(), ACCESS_TOKEN)

    def test_access_token_is_redacted(self):
        with mock.patch.dict(os.environ, {"PENPOT_ACCESS_TOKEN": ACCESS_TOKEN}):
            shown = redact(f"HTTP 401 for Authorization: Token {ACCESS_TOKEN} (token {ACCESS_TOKEN})")
        self.assertNotIn("secret-part", shown)
        self.assertIn("Authorization: Token ***", shown)
        # the header form is masked even when the variable is not set in this process
        self.assertEqual(redact("Authorization: Token abc.def"), "Authorization: Token ***")



class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self.body, self.status = body, status

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class BackendClientCalls(unittest.TestCase):
    """BackendClient: one JSON POST per method on /api/main/methods/, errors redacted."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"PENPOT_ACCESS_TOKEN": ACCESS_TOKEN, "PENPOT_URL": "https://penpot.test"})
        patcher.start(); self.addCleanup(patcher.stop)
        self.state = ProjectState(root=Path(tempfile.mkdtemp(prefix="pb-site-")))

    def test_call_posts_json_with_token_and_user_agent(self):
        sent = {}

        def fake_urlopen(request, timeout=None):
            sent["url"], sent["headers"], sent["body"] = request.full_url, dict(request.header_items()), request.data
            return FakeResponse(b'{"id": "profile-1"}')

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            reply = BackendClient(self.state).call("get-profile")
        self.assertEqual(reply, {"id": "profile-1"})
        self.assertEqual(sent["url"], "https://penpot.test/api/main/methods/get-profile")
        self.assertEqual(sent["headers"]["Authorization"], f"Token {ACCESS_TOKEN}")
        self.assertNotIn("urllib", sent["headers"]["User-agent"].lower())   # Cloudflare rejects urllib's default
        self.assertEqual(json.loads(sent["body"]), {})

    def test_http_error_is_redacted(self):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 401, "denied", {}, io.BytesIO(f"bad token {ACCESS_TOKEN}".encode()))

        with mock.patch("urllib.request.urlopen", fake_urlopen), self.assertRaises(BackendError) as raised:
            BackendClient(self.state).call("get-profile")
        self.assertIn("401", str(raised.exception))
        self.assertNotIn("secret-part", str(raised.exception))

    def test_missing_token_explains_what_to_do(self):
        with mock.patch.dict(os.environ, {"PENPOT_ACCESS_TOKEN": ""}), self.assertRaises(BackendError) as raised:
            BackendClient(self.state)
        self.assertIn("PENPOT_ACCESS_TOKEN", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
