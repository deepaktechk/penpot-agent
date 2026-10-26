"""SVG downloads for vector import: parallel prefetch fills the same cache `fetch_svg` reads."""
import threading
import time
import unittest
from unittest import mock

from pbridge.convert import svg_source


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def read(self, _limit: int = -1) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class SvgPrefetch(unittest.TestCase):
    def setUp(self):
        svg_source._CACHE.clear()
        self.addCleanup(svg_source._CACHE.clear)

    def test_svg_urls_are_found_anywhere_in_the_layout(self):
        layout = {"els": [{"src": "https://site.test/a.svg"}, {"bg": "url(https://site.test/b.svg?v=2)"},
                          {"src": "https://site.test/photo.webp"}, {"children": [{"src": "https://site.test/a.svg"}]}]}
        self.assertEqual(svg_source.svg_urls(layout), ["https://site.test/a.svg", "https://site.test/b.svg?v=2"])

    def test_prefetch_downloads_in_parallel_and_fills_the_cache(self):
        active, peak, lock = [0], [0], threading.Lock()

        def slow_urlopen(request, timeout=None):
            with lock:
                active[0] += 1; peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            with lock:
                active[0] -= 1
            return FakeResponse(f'<?xml version="1.0"?><svg id="{request.full_url[-5]}"/>'.encode())

        urls = [f"https://site.test/{i}.svg" for i in range(8)]
        with mock.patch("urllib.request.urlopen", slow_urlopen):
            svg_source.prefetch_svgs(urls, workers=8)
        self.assertGreater(peak[0], 1)                       # really concurrent
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used after prefetch")):
            self.assertEqual(svg_source.fetch_svg(urls[3]), '<svg id="3"/>')


if __name__ == "__main__":
    unittest.main()
