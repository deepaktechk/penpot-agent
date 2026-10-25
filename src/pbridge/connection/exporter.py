"""Export Penpot shapes to PNG/SVG files.

Two strategies:
  * whole shape through MCP `export_shape`, re-exported until two renders are identical
    ("settled": fonts and images finished loading in the browser);
  * stitched: when the server times out on a big board, export each child separately and
    composite them on a canvas at their visual bounds.
"""
from __future__ import annotations

import hashlib
import io
import time
from pathlib import Path

from pbridge.connection.bridge import Bridge
from pbridge.connection.errors import PluginError

# geometry of a board and of each child: visual bounds include children that overflow (unless clipped)
_STITCH_INFO_JS = """
    const board = pb.byId(DATA);
    const visualBounds = (shape) => {
      let left = shape.x, top = shape.y, right = shape.x + shape.width, bottom = shape.y + shape.height;
      if (shape.type !== 'board' || !shape.clipContent) for (const child of (shape.children || [])) {
        const bounds = visualBounds(child);
        left = Math.min(left, bounds[0]); top = Math.min(top, bounds[1]);
        right = Math.max(right, bounds[2]); bottom = Math.max(bottom, bounds[3]);
      }
      return [left, top, right, bottom]; };
    return {x: board.x, y: board.y, width: board.width, height: board.height,
            fill: (board.fills && board.fills[0] && board.fills[0].fillColor) || '#FFFFFF',
            children: board.children.map(child => ({id: child.id, bounds: visualBounds(child), hidden: child.hidden}))};"""


class Exporter:
    def __init__(self, bridge: Bridge):
        self.bridge = bridge

    def _export_once(self, shape_id: str, fmt: str, _retry: bool = True) -> bytes:
        try:
            result = self.bridge.client.call("export_shape", {"shapeId": shape_id, "format": fmt}, timeout=300)
        except PluginError as error:
            # the plugin task was killed while the tab was throttled: wait once and retry
            if _retry and "timed out" in str(error) and "Task" in str(error):
                self.bridge.client.wait_for_plugin("export timed out")
                return self._export_once(shape_id, fmt, _retry=False)
            raise
        if result.is_error or not result.images:
            raise PluginError(result.text or "export returned no image")
        return result.images[0][1]

    def _default_out(self, shape_id: str, fmt: str) -> Path:
        return self.bridge.state.path("renders", f"{shape_id[:8]}-{int(time.time())}.{fmt}")

    def export_stitched(self, shape_id: str, out: Path | None = None) -> Path:
        """Export a big board child by child and composite (avoids the per-task timeout)."""
        from PIL import Image
        info = self.bridge.exec(_STITCH_INFO_JS, data=shape_id)
        canvas = Image.new("RGBA", (round(info["width"]), round(info["height"])), info["fill"])
        for child in info["children"]:
            if child["hidden"]:
                continue
            image = Image.open(io.BytesIO(self._export_once(child["id"], "png"))).convert("RGBA")
            left, top, right, bottom = child["bounds"]
            # the export covers the visual bounds; resize guard against rounding differences
            if abs(image.width - (right - left)) > 2 or abs(image.height - (bottom - top)) > 2:
                image = image.resize((max(1, round(right - left)), max(1, round(bottom - top))))
            canvas.alpha_composite(image, (round(left - info["x"]), round(top - info["y"])))
        out = out or self._default_out(shape_id, "png")
        canvas.convert("RGB").save(out)
        return Path(out)

    def export(self, shape_id: str, fmt: str = "png", out: Path | None = None, settle: bool = True) -> Path:
        """Export a shape to `out` (default .pbridge/renders/<id>-<time>.<fmt>).

        settle=True re-exports (up to 5 times) until two consecutive renders are identical.
        Falls back to a stitched export when the server times out on a large board.
        """
        previous_hash, data = None, b""
        for attempt in range(5 if settle else 1):
            try:
                data = self._export_once(shape_id, fmt)
            except PluginError as error:
                if "timed out" in str(error) and fmt == "png":
                    return self.export_stitched(shape_id, out)
                raise
            render_hash = hashlib.md5(data).hexdigest()
            if not settle or render_hash == previous_hash:
                break
            previous_hash = render_hash
            time.sleep(1.0 + attempt)
        out = out or self._default_out(shape_id, fmt)
        Path(out).write_bytes(data)
        return Path(out)
