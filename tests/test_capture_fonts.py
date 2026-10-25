"""Capture with a slow, uncacheable web font (`font-display: optional`).

Bug (CI, 2026-10-25): the capture relied on Chrome's HTTP cache to have the web font ready on the
reload. When the font could not be served from the cache fast enough, every reload painted the
fallback font and the capture gave up (median width deviation 11.4%). The capture now keeps the
downloaded fonts in memory and serves them itself on reloads.

Needs Chrome and network (the Outfit font is fetched from Google Fonts once, like the fixture tests).
"""
import http.server
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from pbridge.paths import node_command

CAPTURE = os.environ.get("PB_SELFTEST_CAPTURE", "1") == "1"
GOOGLE_CSS = "https://fonts.googleapis.com/css2?family=Outfit:wght@400&display=optional"
CHROME_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130 Safari/537.36"
FONT_DELAY_SECONDS = 0.4      # far beyond the ~100 ms that font-display: optional waits for

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>
  @font-face { font-family: Outfit; font-weight: 100 900; font-display: optional; src: url(/outfit.woff2) format("woff2"); }
  body { margin: 0; padding: 40px; font-family: Outfit, Arial, sans-serif; font-size: 20px; }
  p { margin: 0 0 12px; }
</style></head><body>
<p>Plan your week in minutes</p><p>Track time across projects</p><p>Invoices from tracked hours</p>
<p>Reports your clients understand</p><p>Works on every device you own</p><p>Free for unlimited users</p>
</body></html>"""


def download_outfit() -> bytes:
    request = urllib.request.Request(GOOGLE_CSS, headers={"User-Agent": CHROME_AGENT})
    css = urllib.request.urlopen(request, timeout=20).read().decode()
    font_url = re.findall(r"url\((https://[^)]+\.woff2)\)", css)[-1]
    return urllib.request.urlopen(font_url, timeout=20).read()


class SlowFontHandler(http.server.BaseHTTPRequestHandler):
    """Serves the page; the font only after a delay and with `no-store` (never cached)."""
    font_bytes = b""

    def do_GET(self):
        if self.path.startswith("/outfit"):
            time.sleep(FONT_DELAY_SECONDS)
            body, content_type = self.font_bytes, "font/woff2"
        else:
            body, content_type = PAGE.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):   # keep test output clean
        pass


@unittest.skipUnless(CAPTURE, "capture disabled")
class SlowUncacheableFont(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            font_bytes = download_outfit()
        except OSError as error:
            raise unittest.SkipTest(f"Google Fonts not reachable: {error}") from None
        handler = type("Handler", (SlowFontHandler,), {"font_bytes": font_bytes})
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/page.html"
        cls.tmp = Path(tempfile.mkdtemp(prefix="pb-fonts-"))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_real_font_painted_although_the_cache_never_helps(self):
        out = self.tmp / "capture"
        result = subprocess.run([*node_command("capture"), "--url", self.url, "--out", str(out), "--width", "900",
                                 "--fonts", "Outfit", "--no-scroll", "--no-freeze", "--wait", "0"],
                                capture_output=True, text=True, timeout=240)
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        font_render = json.loads((out / "layout.json").read_text())["quality"]["fontRender"]["Outfit"]
        self.assertGreaterEqual(font_render["samples"], 5, font_render)
        self.assertLess(font_render["medianDev"], 0.02, f"fallback font painted: {font_render}\n{result.stderr[-1500:]}")


if __name__ == "__main__":
    unittest.main()
