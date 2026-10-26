"""Capture gate (offline): references that must never become a design."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pbridge.quality import capture_gate


def screenshot(folder: Path, height: int) -> Path:
    """A non-blank screenshot of the given height."""
    path = folder / "shot.png"
    image = Image.new("RGB", (1920, height), "white")
    ImageDraw.Draw(image).rectangle([100, 100, 900, 400], fill="navy")
    image.save(path)
    return path


def page(title: str, texts: list[str], height: int = 1080) -> dict:
    elements = [{"i": i, "p": -1, "tag": "p", "r": [0, 40 * i, 600, 30], "op": 1, "text": text} for i, text in enumerate(texts)]
    elements += [{"i": 100 + i, "p": -1, "tag": "div", "r": [0, 0, 10, 10], "op": 1} for i in range(12)]
    return {"url": "https://example.com/", "title": title, "width": 1920, "height": height, "elements": elements,
            "quality": {"fontRender": {}, "brokenImages": [], "lazyPending": 0}}


class BotChallenge(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.shot = screenshot(Path(self.folder.name), 1080)

    def tearDown(self):
        self.folder.cleanup()

    def test_cloudflare_check_page_fails(self):
        # getjobber.com 2026-10-26: headless Chrome got Cloudflare's "Just a moment..." page and the gate
        # passed it, so a 16-element check page would have been built as the site's design
        gate = capture_gate(page("Just a moment...", ["www.getjobber.com", "Verifying you are human. This may take a few seconds."]),
                            self.shot)
        self.assertFalse(gate["ok"])
        self.assertTrue(any("bot check" in error for error in gate["errors"]), gate["errors"])

    def test_real_page_mentioning_cloudflare_passes(self):
        gate = capture_gate(page("Pricing | Example", ["We use Cloudflare to serve this page fast", "Start your free trial"]), self.shot)
        self.assertTrue(gate["ok"], gate["errors"])


if __name__ == "__main__":
    unittest.main()
