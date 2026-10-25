"""Measure a design image (screenshot, mockup, photo of a UI): palette and solid boxes.

Used to turn images into Penpot designs: an AI (or a person) reads the content of the image,
`pb analyze` supplies exact numbers - the colours, and the position, size, colour and corner
radius of every flat-coloured box (cards, buttons, bars, sections) - so the spec can be written
with real values and then checked against the image with `pb compare`.

Algorithm for boxes: downscale, quantize to a small palette, find 4-connected regions of one
palette colour, and keep regions whose outline fills most of their bounding box (rectangles,
rounded rectangles - text or cards painted on top of a box leave holes, which do not count
against it). Positions are measured back at full resolution.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from PIL import Image

ANALYSIS_WIDTH = 480          # boxes are searched on a copy this wide (keeps pure-Python flood fill fast)
PALETTE_SAMPLE = 400          # palette is measured on a copy at most this wide


def to_hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb[:3])


def _distance(first, second) -> float:
    return sum((channel_a - channel_b) ** 2 for channel_a, channel_b in zip(first[:3], second[:3])) ** 0.5


def palette(image: Image.Image, count: int = 8, merge_distance: float = 18) -> list[dict]:
    """Dominant colours: [{hex, share}] sorted by share (0..1), near-identical colours merged."""
    sample = image.convert("RGB")
    if sample.width > PALETTE_SAMPLE:
        sample = sample.resize((PALETTE_SAMPLE, max(1, round(sample.height * PALETTE_SAMPLE / sample.width))), Image.BOX)
    quantized = sample.quantize(colors=max(2, count * 2), method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    flat_palette = quantized.getpalette()[: max(2, count * 2) * 3]
    pixel_count = sample.width * sample.height
    colours: list[list] = []          # [rgb, pixels]
    for pixels, index in sorted(quantized.getcolors(), reverse=True):
        rgb = tuple(flat_palette[index * 3: index * 3 + 3])
        similar = next((entry for entry in colours if _distance(entry[0], rgb) < merge_distance), None)
        if similar:
            similar[1] += pixels
        else:
            colours.append([rgb, pixels])
    colours.sort(key=lambda entry: -entry[1])
    return [{"hex": to_hex(rgb), "share": round(pixels / pixel_count, 4)} for rgb, pixels in colours[:count]]


@dataclass
class Box:
    """A flat-coloured rectangle found in the image, in full-resolution pixels."""
    x: int
    y: int
    width: int
    height: int
    color: str
    share: float        # fraction of the image area
    radius: int         # estimated corner radius
    fill_ratio: float   # outline coverage of the bounding box (1.0 = sharp rectangle)

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.width, "h": self.height, "color": self.color, "share": self.share,
                "r": self.radius, "fill": self.fill_ratio}


def _regions(labels: list[list[int]], width: int, height: int):
    """Yield (label, pixel list) for every 4-connected region of equal labels."""
    seen = [[False] * width for _ in range(height)]
    for start_y in range(height):
        for start_x in range(width):
            if seen[start_y][start_x]:
                continue
            label = labels[start_y][start_x]
            seen[start_y][start_x] = True
            queue = deque([(start_x, start_y)]); pixels = []
            while queue:
                x, y = queue.popleft(); pixels.append((x, y))
                for next_x, next_y in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= next_x < width and 0 <= next_y < height and not seen[next_y][next_x] and labels[next_y][next_x] == label:
                        seen[next_y][next_x] = True; queue.append((next_x, next_y))
            yield label, pixels


def _corner_radius(pixels: set, left: int, top: int, right: int, bottom: int) -> int:
    """Corner radius estimate: how far the top-left corner's diagonal is empty before the region starts."""
    gap = 0
    while gap < min(right - left, bottom - top) // 2 and (left + gap, top + gap) not in pixels:
        gap += 1
    # for a circle-cornered box the empty diagonal is r * (1 - 1/sqrt(2)) ~ 0.29 r
    return round(gap / 0.293) if gap else 0


def _outline_coverage(pixels: list[tuple[int, int]], left: int, top: int, right: int, bottom: int) -> float:
    """Share of the bounding box inside the region's outline (holes filled): min of the row-span
    and column-span coverage, so an L-shape or a diagonal band scores low while a box with text on
    it scores ~1."""
    row_spans: dict[int, list[int]] = {}
    column_spans: dict[int, list[int]] = {}
    for x, y in pixels:
        row = row_spans.setdefault(y, [x, x]); row[0] = min(row[0], x); row[1] = max(row[1], x)
        column = column_spans.setdefault(x, [y, y]); column[0] = min(column[0], y); column[1] = max(column[1], y)
    area = (right - left) * (bottom - top)
    by_rows = sum(span[1] - span[0] + 1 for span in row_spans.values()) / area
    by_columns = sum(span[1] - span[0] + 1 for span in column_spans.values()) / area
    return min(by_rows, by_columns)


def boxes(image: Image.Image, colors: int = 16, min_area: int = 600, min_fill: float = 0.85, limit: int = 60) -> dict:
    """Flat-coloured boxes and the background: {"background": hex, "boxes": [Box.to_dict()]}.

    min_area: smallest box in full-resolution px² (600 ~ a 30x20 button); min_fill: outline coverage.
    """
    source = image.convert("RGB")
    scale = source.width / ANALYSIS_WIDTH if source.width > ANALYSIS_WIDTH else 1.0
    small = source.resize((round(source.width / scale), max(1, round(source.height / scale))), Image.BOX) if scale > 1 else source
    quantized = small.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    width, height = quantized.size
    data = quantized.tobytes()          # mode "P": one palette index per byte
    labels = [data[row * width:(row + 1) * width] for row in range(height)]
    flat_palette = quantized.getpalette()
    total = width * height
    min_cells = max(6, min_area / (scale * scale))      # min_area measured on the downscaled grid
    found: list[Box] = []
    background, background_size = None, 0
    for label, pixels in _regions(labels, width, height):
        if len(pixels) > background_size:
            background, background_size = label, len(pixels)
        if len(pixels) < min_cells:
            continue
        columns = [x for x, _ in pixels]; rows = [y for _, y in pixels]
        left, top, right, bottom = min(columns), min(rows), max(columns) + 1, max(rows) + 1
        fill_ratio = _outline_coverage(pixels, left, top, right, bottom)
        if fill_ratio < min_fill or right - left < 3 or bottom - top < 3:
            continue
        rgb = flat_palette[label * 3: label * 3 + 3]
        radius = _corner_radius(set(pixels), left, top, right, bottom)
        found.append(Box(round(left * scale), round(top * scale), round((right - left) * scale), round((bottom - top) * scale),
                         to_hex(rgb), round(len(pixels) / total, 4), round(radius * scale), round(fill_ratio, 3)))
    background_hex = to_hex(flat_palette[background * 3: background * 3 + 3]) if background is not None else None
    # the page background itself is not a box
    found = [box for box in found if not (box.color == background_hex and box.share > 0.3)]
    found.sort(key=lambda box: -box.share)
    return {"background": background_hex, "boxes": [box.to_dict() for box in found[:limit]]}


def analyze(path, region: tuple | None = None, colors: int = 8, box_limit: int = 60) -> dict:
    """Everything `pb analyze` reports for one image (optionally a crop x0, y0, x1, y1 of it)."""
    image = Image.open(path)
    offset_x, offset_y = 0, 0
    if region:
        image = image.crop(region); offset_x, offset_y = region[0], region[1]
    found = boxes(image, limit=box_limit)
    for box in found["boxes"]:      # report positions in the coordinates of the whole image
        box["x"] += offset_x; box["y"] += offset_y
    return {"image": str(path), "size": [image.width, image.height], "offset": [offset_x, offset_y],
            "background": found["background"], "palette": palette(image, colors), "boxes": found["boxes"]}


def combined_palette(analyses: list[dict], count: int = 12, merge_distance: float = 18) -> list[dict]:
    """Merge the palettes of several images (moodboard): share = average over the images."""
    merged: list[list] = []      # [rgb, total share]
    for analysis in analyses:
        for entry in analysis["palette"]:
            rgb = tuple(int(entry["hex"][i:i + 2], 16) for i in (1, 3, 5))
            similar = next((item for item in merged if _distance(item[0], rgb) < merge_distance), None)
            if similar:
                similar[1] += entry["share"]
            else:
                merged.append([rgb, entry["share"]])
    merged.sort(key=lambda item: -item[1])
    return [{"hex": to_hex(rgb), "share": round(share / len(analyses), 4)} for rgb, share in merged[:count]]
