"""Image URL helpers shared by the converter and the asset store."""
from __future__ import annotations

import hashlib
import re
import urllib.parse


def norm_url(url: str) -> str:
    """Percent-encode spaces/unicode in path & query (the Penpot backend is strict)."""
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/%:@!$&'()*+,;=-._~")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def key_for(src: str) -> str:
    """Stable, readable asset key: '<file name>-<6 hex of sha1(src)>'."""
    base = src.split("?")[0].rstrip("/").split("/")[-1] or "asset"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", urllib.parse.unquote(base))[:48]
    return f"{base}-{hashlib.sha1(src.encode()).hexdigest()[:6]}"


def is_local(url: str) -> bool:
    """URLs the Penpot server cannot fetch by itself (bytes must be relayed)."""
    return url.startswith(("file:", "data:")) or "://localhost" in url or "://127." in url


def is_svg(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".svg")
