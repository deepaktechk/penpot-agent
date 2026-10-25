"""Get image bytes locally when Penpot cannot fetch a URL itself.

* `download`      - http(s)/file/data URLs -> (bytes, mime)
* `rasterize_svg` - SVG -> PNG via headless Chrome (Penpot media cannot be SVG bytes)
"""
from __future__ import annotations

import base64
import mimetypes
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from pbridge.paths import node_command

USER_AGENT = {"User-Agent": "Mozilla/5.0"}


def download(url: str) -> tuple[bytes, str]:
    """Fetch bytes for file://, localhost, intranet or data: URLs."""
    if url.startswith("data:"):
        header, encoded = url.split(",", 1)
        return base64.b64decode(encoded), header[5:].split(";")[0] or "image/png"
    with urllib.request.urlopen(urllib.request.Request(url, headers=USER_AGENT), timeout=60) as response:
        data = response.read()
        mime = (response.headers.get("Content-Type") or "").split(";")[0].strip()
    if not mime or mime == "application/octet-stream":
        mime = mimetypes.guess_type(url.split("?")[0])[0] or "image/png"
    return data, mime


def rasterize_svg(url: str, scale: float = 2.0) -> bytes:
    """Render an SVG with Chrome at `scale`x and return the PNG bytes."""
    with tempfile.TemporaryDirectory() as temp_dir:
        out = Path(temp_dir) / "raster.png"
        result = subprocess.run([*node_command("rasterize"), url, str(out), str(scale)], capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError("svg rasterize failed: " + result.stderr[-400:])
        return out.read_bytes()
