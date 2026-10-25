"""Images for humans: diff overlays and hotspot montages.

Color code everywhere: red = only in the reference, cyan = only in the render.
"""
from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw

from pbridge.imaging.metrics import align_sizes, load


def _red_cyan(reference: Image.Image, render: Image.Image) -> Image.Image:
    reference_luma = reference.convert("L")
    return Image.merge("RGB", (render.convert("L"), reference_luma, reference_luma))


def overlay(reference_path, render_path, out_path, region=None, mode: str = "stack", scale: float = 1.0):
    """mode: stack (reference above the red/cyan overlay), overlay, heat, side (side by side)."""
    reference, render = align_sizes(load(reference_path), load(render_path))
    if region:
        reference, render = reference.crop(region), render.crop(region)
    red_cyan = _red_cyan(reference, render)
    if mode == "overlay":
        image = red_cyan
    elif mode == "heat":
        heat = ImageChops.difference(reference, render).convert("L").point(lambda value: min(255, value * 3))
        image = Image.merge("RGB", (heat, Image.new("L", heat.size, 0), Image.new("L", heat.size, 0)))
        image = Image.blend(reference.convert("RGB"), image, 0.6)
    elif mode == "side":
        image = Image.new("RGB", (reference.width * 2 + 6, reference.height), "yellow")
        image.paste(reference, (0, 0)); image.paste(render, (reference.width + 6, 0))
    else:
        image = Image.new("RGB", (reference.width, reference.height * 2 + 6), "yellow")
        image.paste(reference, (0, 0)); image.paste(red_cyan, (0, reference.height + 6))
    if scale != 1.0:
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.LANCZOS)
    image.save(out_path)
    return out_path


def montage(reference_path, render_path, boxes, out_path, pad: int = 16, max_width: int = 900, label: bool = True):
    """One image: for each box, the reference crop above its red/cyan overlay (labelled #i)."""
    reference, render = align_sizes(load(reference_path), load(render_path))
    tiles = []
    for i, spot in enumerate(boxes):
        x, y, width, height = (spot["x"], spot["y"], spot["w"], spot["h"]) if isinstance(spot, dict) else spot
        box = (max(0, int(x - pad)), max(0, int(y - pad)),
               min(reference.width, int(x + width + pad)), min(reference.height, int(y + height + pad)))
        reference_crop, render_crop = reference.crop(box), render.crop(box)
        tile = Image.new("RGB", (reference_crop.width, reference_crop.height * 2 + 22), "yellow")
        tile.paste(reference_crop, (0, 18)); tile.paste(_red_cyan(reference_crop, render_crop), (0, reference_crop.height + 22))
        if label:
            ImageDraw.Draw(tile).text((4, 3), f"#{i} {box}", fill="black")
        shrink = min(1.0, max_width / tile.width)
        if shrink < 1:
            tile = tile.resize((int(tile.width * shrink), int(tile.height * shrink)), Image.LANCZOS)
        tiles.append(tile)
    if not tiles:
        return None
    sheet_width = max(tile.width for tile in tiles); sheet_height = sum(tile.height + 8 for tile in tiles)
    sheet = Image.new("RGB", (sheet_width, sheet_height), "white"); top = 0
    for tile in tiles:
        sheet.paste(tile, (0, top)); top += tile.height + 8
    sheet.save(out_path)
    return out_path
