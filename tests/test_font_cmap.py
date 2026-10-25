"""Font character coverage (cmap) - offline, with tiny fonts built in memory."""
import struct
import unittest

from pbridge.convert import font_cmap


def font_with_cmap(subtable: bytes, platform: int = 3, encoding: int = 1) -> bytes:
    """A font that only has a table directory and one cmap table with one subtable."""
    cmap = struct.pack(">HHHHI", 0, 1, platform, encoding, 12) + subtable
    directory = struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0)
    record = b"cmap" + struct.pack(">III", 0, 12 + 16, len(cmap))
    return directory + record + cmap


def format4(segments: list[tuple[int, int, int]]) -> bytes:
    """(first, last, delta) segments + the mandatory 0xFFFF end segment, no glyphIdArray."""
    segments = segments + [(0xFFFF, 0xFFFF, 1)]
    count = len(segments)
    body = struct.pack(f">{count}H", *(last for _, last, _ in segments)) + b"\0\0"
    body += struct.pack(f">{count}H", *(first for first, _, _ in segments))
    body += struct.pack(f">{count}H", *(delta % 65536 for _, _, delta in segments))
    body += struct.pack(f">{count}H", *([0] * count))
    header = struct.pack(">HHHHHHH", 4, 14 + len(body), 0, 2 * count, 0, 0, 0)
    return header + body


def format12(groups: list[tuple[int, int]]) -> bytes:
    body = b"".join(struct.pack(">III", first, last, 1) for first, last in groups)
    return struct.pack(">HHIII", 12, 0, 16 + len(body), 0, len(groups)) + body


class Coverage(unittest.TestCase):
    def test_latin_font_does_not_cover_indic_scripts(self):
        # bug: google.com language links measured with Arimo (Latin only) were squeezed by a letter-spacing fit
        ranges = font_cmap.unicode_ranges(font_with_cmap(format4([(0x20, 0x7E, -29)])))
        self.assertEqual(ranges, [(0x20, 0x7E)])
        self.assertTrue(font_cmap.covers(ranges, "Google offered in:"))
        self.assertFalse(font_cmap.covers(ranges, "Google offered in: हिन्दी"))

    def test_whitespace_never_needs_a_glyph(self):
        self.assertTrue(font_cmap.covers([(0x41, 0x5A)], "AB C\tD"))

    def test_format12_full_range(self):
        ranges = font_cmap.unicode_ranges(font_with_cmap(format12([(0x20, 0x7E), (0x0900, 0x097F)]), 3, 10))
        self.assertTrue(font_cmap.covers(ranges, "Hi हिन्दी"))
        self.assertFalse(font_cmap.covers(ranges, "বাংলা"))

    def test_unreadable_font_has_no_ranges(self):
        self.assertEqual(font_cmap.unicode_ranges(b"not a font"), [])


if __name__ == "__main__":
    unittest.main()
