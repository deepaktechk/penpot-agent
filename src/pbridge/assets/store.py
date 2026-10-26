"""Image assets: upload once, reuse forever (per project).

`.pbridge/assets.json` maps an asset key to where it came from and the Penpot ImageData
descriptor returned by the upload:

    {key: {"src": url | path, "hash": sha1, "image": {id, width, height, ...}}}

Upload strategy for a URL (`many_urls` does step 1 for many URLs at once, concurrently):
  1. ask Penpot's server to fetch it (`penpot.uploadMediaUrl`)  - public URLs
  2. else download locally and relay the bytes (`uploadMediaData`) - private hosts, file://
     SVGs are rasterized first because Penpot media cannot be SVG bytes.
Identical bytes are detected by hash and never uploaded twice.
"""
from __future__ import annotations

import base64
import hashlib
import io
import zlib
from pathlib import Path
from typing import Any

from pbridge.assets.fetch import download, rasterize_svg
from pbridge.assets.urls import is_local, is_svg, key_for, norm_url
from pbridge.connection import Bridge

UPLOAD_BATCH = 12   # public URLs uploaded concurrently per plugin call

MIME_BY_SUFFIX = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
                  ".gif": "image/gif", ".svg": "image/svg+xml"}


class AssetStore:
    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.entries: dict[str, dict[str, Any]] = bridge.state.load_json("assets.json", {})

    def save(self) -> None:
        self.bridge.state.save_json("assets.json", self.entries)

    def get(self, key: str) -> dict[str, Any] | None:
        return self.entries.get(key)

    def _by_hash(self, digest: str) -> tuple[str | None, dict[str, Any] | None]:
        for key, entry in self.entries.items():
            if entry.get("hash") == digest and entry.get("image"):
                return key, entry
        return None, None

    # ------------------------------------------------------------------ uploads
    def from_url(self, url: str, key: str | None = None, force: bool = False) -> str:
        """Upload an image URL (cached by key). Returns the asset key."""
        url = norm_url(url)
        key = key or key_for(url)
        if not force and key in self.entries and self.entries[key].get("image"):
            self._ensure_registered(key)
            return key
        image = None
        if not is_local(url):
            try:
                image = self.bridge.exec("return await pb.uploadUrl(DATA.key, DATA.url);", data={"key": key, "url": url}, timeout=180)
            except Exception:
                image = None   # Penpot's server could not fetch it (private host, auth, ...) -> relay bytes
        if not image:
            return self._upload_local(url, key)
        if not image.get("id"):
            raise ValueError(f"{key}: Penpot returned an incomplete image descriptor")
        self.entries[key] = {"src": url, "hash": hashlib.sha1(url.encode()).hexdigest(), "image": image}
        self.save()
        return key

    def from_bytes(self, data: bytes, key: str, mime: str = "image/png", src: str = "") -> str:
        """Upload raw bytes (deduplicated by sha1). Returns the asset key."""
        digest = hashlib.sha1(data).hexdigest()
        existing_key, existing = self._by_hash(digest)
        if existing:
            if existing_key != key:
                self.entries[key] = dict(existing, src=src or existing.get("src"))
                self.save()
            self._ensure_registered(key)
            return key
        if mime == "image/svg+xml":
            raise ValueError(f"{key}: SVG files cannot be uploaded as Penpot media; import them as vectors (t:'svg')")
        # the CRC lets the plugin detect a corrupted base64 transfer
        payload = {"key": key, "base64": base64.b64encode(data).decode(), "mime": mime, "crc": zlib.crc32(data)}
        image = self.bridge.exec("return await pb.uploadB64(DATA.key, DATA.base64, DATA.mime, DATA.crc);", data=payload, timeout=300)
        if not image or not image.get("id"):
            raise ValueError(f"{key}: Penpot returned an incomplete image descriptor ({image})")
        self.entries[key] = {"src": src, "hash": digest, "image": image}
        self.save()
        return key

    def from_file(self, path: str | Path, key: str | None = None, crop: list[int] | None = None,
                  quantize: int | None = None, scale: float | None = None, fmt: str | None = None,
                  quality: int = 88) -> str:
        """Upload a local image, optionally cropped (x0,y0,x1,y1), scaled, palette-quantized
        or re-encoded (fmt='JPEG' for photos)."""
        from PIL import Image
        path = Path(path)
        key = key or (path.stem + (f"-{crop[0]}_{crop[1]}_{crop[2]}_{crop[3]}" if crop else ""))
        if not crop and not quantize and not scale and not fmt:
            mime = MIME_BY_SUFFIX.get(path.suffix.lower(), "image/png")
            return self.from_bytes(path.read_bytes(), key, mime, str(path))
        image = Image.open(path)
        image = image.convert("RGBA") if image.mode in ("P", "LA", "RGBA") else image.convert("RGB")
        if crop:
            image = image.crop(tuple(int(value) for value in crop))
        if scale:
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
        buffer = io.BytesIO()
        if fmt and fmt.upper() in ("JPEG", "JPG"):
            image.convert("RGB").save(buffer, "JPEG", quality=quality, optimize=True)
            mime = "image/jpeg"
        else:
            if quantize:
                method = Image.Quantize.FASTOCTREE if image.mode == "RGBA" else Image.Quantize.MEDIANCUT
                image = image.quantize(colors=quantize, method=method, dither=Image.Dither.NONE)
            image.save(buffer, "PNG", optimize=True)
            mime = "image/png"
        return self.from_bytes(buffer.getvalue(), key, mime, f"{path}#{crop}")

    # ------------------------------------------------------------------ plugin registry
    def _ensure_registered(self, key: str) -> None:
        """The descriptor exists locally; make sure the plugin runtime knows it (cheap)."""
        image = self.entries[key]["image"]
        self.bridge.exec("pb.imgs[DATA.key] = pb.imgs[DATA.key] || DATA.image; return 1;", data={"key": key, "image": image})

    def sync(self) -> int:
        """Re-register every known image in the plugin runtime."""
        descriptors = {key: entry["image"] for key, entry in self.entries.items() if entry.get("image")}
        return self.bridge.exec("return pb.registerImages(DATA);", data=descriptors)

    def many_urls(self, mapping: dict[str, str], force: bool = False, batch: int = UPLOAD_BATCH) -> dict[str, str]:
        """Upload {key: url}; failures are reported as 'ERR <message>' instead of raising.

        Public URLs go to Penpot's server `batch` at a time in one plugin call (concurrent
        uploadMediaUrl); only the ones it cannot fetch take the one-by-one path (download or
        rasterize locally, upload bytes). Callers register the descriptors with `sync()`.
        """
        results: dict[str, str] = {}
        remote: list[dict[str, str]] = []
        for key, url in mapping.items():
            if not force and key in self.entries and self.entries[key].get("image"):
                results[key] = key
            elif is_local(norm_url(url)):
                results[key] = ""     # one by one below
            else:
                remote.append({"key": key, "url": norm_url(url)})
        for start in range(0, len(remote), batch):
            chunk = remote[start:start + batch]
            try:
                uploaded = self.bridge.exec("return await pb.uploadUrls(DATA);", data=chunk, timeout=300)
            except Exception:
                uploaded = {}     # the whole call failed: every item of the chunk falls back below
            for item in chunk:
                image = uploaded.get(item["key"]) or {}
                if image.get("id"):
                    self.entries[item["key"]] = {"src": item["url"], "hash": hashlib.sha1(item["url"].encode()).hexdigest(),
                                                 "image": image}
                    results[item["key"]] = item["key"]
                else:
                    results[item["key"]] = ""
        self.save()
        for key, url in mapping.items():
            if results.get(key):
                continue
            try:
                results[key] = self._upload_local(norm_url(url), key)
            except Exception as error:
                results[key] = f"ERR {str(error)[:120]}"
        return results

    def _upload_local(self, url: str, key: str) -> str:
        """Penpot's server could not fetch `url`: get the bytes here (SVG rasterized) and upload them."""
        if is_svg(url):
            data, mime = rasterize_svg(url), "image/png"
        else:
            data, mime = download(url)
        return self.from_bytes(data, key, mime, url)
