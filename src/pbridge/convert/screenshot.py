"""Pixel evidence from the reference screenshot.

The DOM cannot describe everything (pseudo-element rules, coloured underlines, text
lines that are hidden by clipping). These helpers look at the captured screenshot instead.
"""
from __future__ import annotations

from pbridge.convert.context import ConversionContext


class ScreenshotProbe:
    def __init__(self, ctx: ConversionContext, path: str | None):
        self.ctx = ctx
        self.gray = None   # luma image, for "is anything painted here?"
        self.rgb = None    # color image, for color-run search
        if path:
            from PIL import Image
            self.gray = Image.open(path).convert("L")
            self.rgb = Image.open(path).convert("RGB")

    @property
    def available(self) -> bool:
        return self.rgb is not None

    def locate_color_runs(self, box, color: str, tolerance: int = 40, min_length: int = 1, gap: int = 10) -> list[tuple]:
        """Axis-aligned rectangles of `color` inside `box` (x0, y0, x1, y1) -> [(x, y, w, h)].

        A pixel matches when the sum of its RGB channel differences to `color` is <= tolerance.
        """
        if self.rgb is None:
            return []
        left, top, right, bottom = [int(round(value)) for value in box]
        image_width, image_height = self.rgb.size
        left, top, right, bottom = max(0, left), max(0, top), min(image_width, right), min(image_height, bottom)
        if right - left < 2 or bottom - top < 1:
            return []
        hex_digits = color.lstrip("#"); target = tuple(int(hex_digits[i:i + 2], 16) for i in (0, 2, 4))
        pixels = self.rgb.load()

        def matches(x: int, y: int) -> bool:
            return sum(abs(channel - wanted) for channel, wanted in zip(pixels[x, y], target)) <= tolerance

        # 1. horizontal runs of matching pixels, row by row: (y, x_start, x_end)
        runs = []
        for y in range(top, bottom):
            x = left
            while x < right:
                if matches(x, y):
                    run_start = x
                    while x < right and matches(x, y):
                        x += 1
                    runs.append((y, run_start, x))
                else:
                    x += 1
        # 2. join runs on the same row separated by small gaps (text-decoration-skip-ink, dashes)
        joined = []
        for y, run_start, run_end in runs:
            if joined and joined[-1][0] == y and run_start - joined[-1][2] <= gap:
                joined[-1] = (y, joined[-1][1], run_end)
            else:
                joined.append((y, run_start, run_end))
        runs = [run for run in joined if run[2] - run[1] >= min_length]
        # 3. merge vertically adjacent runs with similar extents into rectangles [left, top, right, bottom]
        rects = []
        for y, run_start, run_end in runs:
            for rect in rects:
                if rect[3] == y and abs(rect[0] - run_start) <= 2 and abs(rect[2] - run_end) <= 2:
                    rect[3] = y + 1; rect[0] = min(rect[0], run_start); rect[2] = max(rect[2], run_end); break
            else:
                rects.append([run_start, y, run_end, y + 1])
        return [(rect_left, rect_top, rect_right - rect_left, rect_bottom - rect_top)
                for rect_left, rect_top, rect_right, rect_bottom in rects]

    def line_has_ink(self, line_rect) -> bool:
        """Does the screenshot show anything inside this text line box? (visual ground truth)"""
        from PIL import ImageStat
        x, y, width, height = line_rect
        image_width, image_height = self.gray.size
        box = (max(0, int(x)), max(0, int(y + height * 0.15)), min(image_width, int(x + width + 1)),
               min(image_height, int(y + height * 0.85)))
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            return True
        stats = ImageStat.Stat(self.gray.crop(box))
        lowest, highest = stats.extrema[0]
        has_ink = stats.stddev[0] > 6 or (highest - lowest) > 40
        if not has_ink:
            self.ctx.report["hidden_lines_dropped"] += 1
        return has_ink
