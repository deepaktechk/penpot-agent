"""MCP client transport: the HTTP requests pbridge sends to the Penpot MCP server."""
import io
import json
import unittest
from unittest import mock

from pbridge import __version__
from pbridge.connection.mcp_client import MCPClient


class FakeResponse(io.BytesIO):
    def __init__(self, payload: dict):
        super().__init__(json.dumps(payload).encode())
        self.headers = {"Content-Type": "application/json"}


class Transport(unittest.TestCase):
    def test_requests_identify_pbridge(self):
        # design.penpot.app sits behind Cloudflare, which rejects the default
        # "Python-urllib/3.x" signature with error 1010 (HTTP 403).
        client = MCPClient("http://localhost:4401/mcp")
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse({"jsonrpc": "2.0", "id": 1, "result": {}})) as urlopen:
            client._post({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), f"pbridge/{__version__}")


if __name__ == "__main__":
    unittest.main()
