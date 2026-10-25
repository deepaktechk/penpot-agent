"""Which characters a TrueType/OpenType font has glyphs for (its `cmap` table), stdlib only.

Pillow measures a missing character with the font's .notdef box, so a width measured with a
font that lacks some of the text's scripts (Devanagari, Bengali... in a Latin font) is wrong.
fontmetrics uses this to tell when its measurement can be trusted.

Reads the Unicode subtables in format 4 (BMP segments) and 12 (full-range groups), which is
what Google Fonts files ship.
"""
from __future__ import annotations

import struct

# (platform id, encoding id) of Unicode cmap subtables, best first
UNICODE_SUBTABLES = ((3, 10), (0, 4), (0, 6), (3, 1), (0, 3), (0, 2), (0, 1), (0, 0))


def _table_offset(font: bytes, tag: bytes) -> int | None:
    """Offset of a table in the font's table directory (single fonts, not collections)."""
    (table_count,) = struct.unpack_from(">H", font, 4)
    for index in range(table_count):
        record = 12 + 16 * index
        if font[record:record + 4] == tag:
            return struct.unpack_from(">I", font, record + 8)[0]
    return None


def _format4(font: bytes, start: int) -> list[tuple[int, int]]:
    (segment_count_x2,) = struct.unpack_from(">H", font, start + 6)
    segment_count = segment_count_x2 // 2
    ends_at = start + 14
    starts_at = ends_at + segment_count_x2 + 2                      # + reservedPad
    deltas_at = starts_at + segment_count_x2
    range_offsets_at = deltas_at + segment_count_x2
    ranges = []
    for segment in range(segment_count):
        end = struct.unpack_from(">H", font, ends_at + 2 * segment)[0]
        first = struct.unpack_from(">H", font, starts_at + 2 * segment)[0]
        if first == 0xFFFF:
            continue
        delta = struct.unpack_from(">H", font, deltas_at + 2 * segment)[0]
        range_offset_at = range_offsets_at + 2 * segment
        range_offset = struct.unpack_from(">H", font, range_offset_at)[0]
        if range_offset == 0:
            # glyph = (code + delta) mod 65536; glyph 0 (.notdef) only for one code at most
            ranges.append((first, end))
            continue
        # glyph ids come from glyphIdArray: keep the codes whose glyph is not .notdef
        for code in range(first, end + 1):
            glyph_at = range_offset_at + range_offset + 2 * (code - first)
            if glyph_at + 2 <= len(font) and (struct.unpack_from(">H", font, glyph_at)[0] + delta) % 65536:
                ranges.append((code, code))
    return ranges


def _format12(font: bytes, start: int) -> list[tuple[int, int]]:
    (group_count,) = struct.unpack_from(">I", font, start + 12)
    ranges = []
    for group in range(group_count):
        first, end, _ = struct.unpack_from(">III", font, start + 16 + 12 * group)
        ranges.append((first, end))
    return ranges


def unicode_ranges(font: bytes) -> list[tuple[int, int]]:
    """Inclusive (first, last) code point ranges the font maps to glyphs. Empty if unreadable."""
    try:
        cmap = _table_offset(font, b"cmap")
        if cmap is None:
            return []
        _, subtable_count = struct.unpack_from(">HH", font, cmap)
        subtables = {}
        for index in range(subtable_count):
            platform, encoding, offset = struct.unpack_from(">HHI", font, cmap + 4 + 8 * index)
            subtables.setdefault((platform, encoding), cmap + offset)
        for key in UNICODE_SUBTABLES:
            if key not in subtables:
                continue
            start = subtables[key]
            (subtable_format,) = struct.unpack_from(">H", font, start)
            if subtable_format == 12:
                return _format12(font, start)
            if subtable_format == 4:
                return _format4(font, start)
    except struct.error:
        pass
    return []


def covers(ranges: list[tuple[int, int]], text: str) -> bool:
    """True when every non-whitespace character of text is inside ranges."""
    return all(char.isspace() or any(first <= ord(char) <= last for first, last in ranges) for char in text)
