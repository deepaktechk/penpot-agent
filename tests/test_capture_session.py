"""Capture session options: dark mode emulation and cookies for pages behind a login.

Needs Chrome (skipped with PB_SELFTEST_CAPTURE=0, like the fixture tests).
"""
import functools
import http.server
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from pbridge.paths import TESTS_DIR, node_command

CAPTURE = os.environ.get("PB_SELFTEST_CAPTURE", "1") == "1"
FAST = ["--no-warmup", "--no-scroll", "--no-freeze", "--wait", "0", "--width", "800"]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):   # keep test output clean
        pass


def element_by_id(layout: dict, html_id: str) -> dict:
    return next(element for element in layout["elements"] if element.get("htmlId") == html_id)


@unittest.skipUnless(CAPTURE, "capture disabled")
class CaptureSession(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(QuietHandler, directory=str(TESTS_DIR / "fixtures"))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/session.html"
        cls.tmp = Path(tempfile.mkdtemp(prefix="pb-session-"))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def capture(self, name: str, *extra: str) -> dict:
        out = self.tmp / name
        result = subprocess.run([*node_command("capture"), "--url", self.url, "--out", str(out), *FAST, *extra],
                                capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        return json.loads((out / "layout.json").read_text())

    def test_default_is_light_even_on_a_dark_mode_os(self):
        # bug: headless Chrome followed the OS appearance, so a dark-mode Mac captured dark pages
        self.assertEqual(element_by_id(self.capture("default"), "scheme-probe")["box"]["bg"], "rgb(255, 255, 255)")

    def test_dark_color_scheme(self):
        light = element_by_id(self.capture("light"), "scheme-probe")
        dark = element_by_id(self.capture("dark", "--color-scheme", "dark"), "scheme-probe")
        self.assertEqual(light["box"]["bg"], "rgb(255, 255, 255)")
        self.assertEqual(dark["box"]["bg"], "rgb(17, 24, 39)")

    def test_cookies_reach_the_page(self):
        # browser-extension export format: expirationDate + sameSite "no_restriction" must be converted
        cookie_file = self.tmp / "cookies.json"
        cookie_file.write_text(json.dumps([{"name": "session", "value": "ok", "domain": "127.0.0.1", "path": "/",
                                            "expirationDate": 4102444800, "sameSite": "unspecified", "secure": False}]))
        layout = self.capture("cookies", "--cookies", str(cookie_file))
        texts = [element.get("text") for element in layout["elements"] if element.get("text")]
        self.assertIn("Welcome back, member", texts)
        self.assertNotIn("Please sign in", texts)

    def test_without_cookies_the_page_is_logged_out(self):
        texts = [element.get("text") for element in self.capture("guest")["elements"] if element.get("text")]
        self.assertIn("Please sign in", texts)


if __name__ == "__main__":
    unittest.main()
