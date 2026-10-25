"""Measure text with the exact font files Penpot uses (Google Fonts TTF), offline.

Lets the converter compute letter-spacing fits and centred/right anchors without any
round trips to the (possibly throttled) Penpot tab. Fonts are cached in
~/.cache/pbridge/fonts.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

from pbridge.convert import font_cmap

CACHE = Path.home() / ".cache" / "pbridge" / "fonts"


def _fetch(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        with urllib.request.urlopen(url, timeout=30) as response:
            dest.write_bytes(response.read())
    return dest


@lru_cache(maxsize=256)
def font_file(family: str, weight: int = 400, italic: bool = False) -> Path | None:
    """Download (once) the TTF for family/weight/style from Google Fonts. None if unavailable."""
    key = f"{family}-{weight}{'i' if italic else ''}"
    dest = CACHE / (re.sub(r"[^A-Za-z0-9-]", "_", key) + ".ttf")
    if dest.exists():
        return dest
    axes = f"ital,wght@{1 if italic else 0},{weight}"
    url = "https://fonts.googleapis.com/css2?family=" + urllib.parse.quote(family) + ":" + axes
    try:
        css = urllib.request.urlopen(url, timeout=20).read().decode()   # no UA -> TTF urls
    except Exception:
        return None
    match = re.search(r"url\((https://[^)]+\.ttf)\)", css)
    if not match:
        return None
    try:
        return _fetch(match.group(1), dest)
    except Exception:
        return None


@lru_cache(maxsize=1024)
def _font(path: str, size: float):
    from PIL import ImageFont
    # size in px; Pillow takes an int/float size in pixels (points == px at 72dpi in Pillow)
    try:
        return ImageFont.truetype(path, size=size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        return ImageFont.truetype(path, size=size)


def text_width(text: str, family: str, size: float, weight: int = 400, italic: bool = False,
               letter_spacing: float = 0.0, upper: bool = False) -> float | None:
    """Advance width in px of a single line (incl. letter-spacing after every char but the last,
    like Penpot/CSS). None if the font file is unavailable."""
    path = font_file(family, int(weight), bool(italic))
    if not path:
        return None
    if upper:
        text = text.upper()
    width = _font(str(path), float(size)).getlength(text)
    return width + letter_spacing * max(0, len(text) - 1)



@lru_cache(maxsize=64)
def _unicode_ranges(path: str) -> tuple[tuple[int, int], ...]:
    return tuple(font_cmap.unicode_ranges(Path(path).read_bytes()))


def covers(text: str, family: str, weight: int = 400, italic: bool = False) -> bool | None:
    """True when the Penpot font has a glyph for every character of text (so text_width is
    trustworthy). None if the font file or its cmap is unavailable."""
    path = font_file(family, int(weight), bool(italic))
    if not path:
        return None
    ranges = _unicode_ranges(str(path))
    if not ranges:
        return None
    return font_cmap.covers(list(ranges), text)

def fit_letter_spacing(lines: list[str], target_width: float, family: str, size: float, weight: int = 400,
                       italic=False, base_letter_spacing: float = 0.0, upper=False) -> float | None:
    """Letter-spacing that makes the widest line exactly target_width wide."""
    widest = None          # (width, line)
    for line in lines:
        width = text_width(line, family, size, weight, italic, base_letter_spacing, upper)
        if width is None:
            return None
        if widest is None or width > widest[0]:
            widest = (width, line)
    if not widest:
        return None
    width, line = widest
    gaps = max(1, len(line) - 1)
    return round(base_letter_spacing + (target_width - width) / gaps, 3)
