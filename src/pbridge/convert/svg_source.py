"""Download SVG files referenced by <img> so they can be imported as editable vectors."""
from __future__ import annotations

import re
import urllib.request

# process-wide cache: one conversion fetches each SVG once, repeated conversions reuse it
_CACHE: dict[str, str | None] = {}

# SVG features Penpot's importer mishandles -> keep such files as raster images
COMPLEX_SVG_RE = re.compile(r"<(clipPath|mask|pattern|filter|use|image|text|foreignObject)\b")


def fetch_svg(url: str, max_bytes: int = 600_000) -> str | None:
    """SVG markup (XML prolog/doctype stripped), or None if unavailable, too big or unsafe."""
    if url in _CACHE:
        return _CACHE[url]
    markup = None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read(max_bytes + 1)
        if len(data) <= max_bytes:
            text = data.decode("utf-8", errors="replace")
            text = re.sub(r"<\?xml[^>]*\?>", "", text)
            text = re.sub(r"<!DOCTYPE[^>]*>", "", text)
            if "<svg" in text and "<foreignObject" not in text and "<script" not in text:
                markup = text.strip()
    except Exception:
        markup = None
    _CACHE[url] = markup
    return markup
