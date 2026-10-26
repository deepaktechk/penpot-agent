"""Download SVG files referenced by <img> so they can be imported as editable vectors.

The converter asks for SVGs one element at a time; `prefetch_svgs` downloads every SVG of a
layout in parallel first (a page often has 50-80; one by one they cost ~0.2 s each), so
those per-element calls are cache hits.
"""
from __future__ import annotations

import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

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


SVG_URL_RE = re.compile(r"https?://[^\s\"')]+?\.svg(?:[?#][^\s\"')]*)?(?=[\s\"')]|$)", re.IGNORECASE)


def svg_urls(layout: Any) -> list[str]:
    """Every distinct http(s) .svg URL found in a capture layout (any field, in first-seen order)."""
    found: dict[str, None] = {}

    def walk(value: Any) -> None:
        if isinstance(value, str):
            if ".svg" in value.lower():
                for url in SVG_URL_RE.findall(value):
                    found.setdefault(url, None)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(layout)
    return list(found)


def prefetch_svgs(urls: list[str], workers: int = 8) -> None:
    """Download SVGs concurrently into the cache `fetch_svg` reads (failures are cached as None)."""
    pending = [url for url in urls if url not in _CACHE]
    if pending:
        with ThreadPoolExecutor(max(1, min(workers, len(pending)))) as pool:
            list(pool.map(fetch_svg, pending))
