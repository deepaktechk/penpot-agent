"""Resolve image URLs found in the capture."""
from __future__ import annotations

import urllib.parse

from pbridge.assets.urls import norm_url


def resolve_img_url(src: str | None, base: str) -> str | None:
    """Absolute, normalized URL; Next.js `/_next/image?url=` proxies are unwrapped."""
    if not src:
        return None
    if src.startswith("data:"):
        return src
    if "/_next/image" in src:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(src).query)
        if "url" in query:
            src = query["url"][0]
    return norm_url(urllib.parse.urljoin(base, src))
