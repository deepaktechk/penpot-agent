"""Whole-image / region metrics between a reference and a render.

mad       mean absolute difference, 0-255 (on luma of the RGB difference)
pct_diff  % of pixels whose difference exceeds `tolerance`
ssim      block SSIM on luma (dependency-free approximation)
"""
from __future__ import annotations

from PIL import Image, ImageChops, ImageStat


def load(path, mode: str = "RGB") -> Image.Image:
    return Image.open(path).convert(mode)


def align_sizes(reference: Image.Image, render: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Pad the smaller image (white) so both share the same canvas."""
    width, height = max(reference.width, render.width), max(reference.height, render.height)

    def pad(image: Image.Image) -> Image.Image:
        if image.size == (width, height):
            return image
        canvas = Image.new(image.mode, (width, height), "white"); canvas.paste(image, (0, 0)); return canvas

    return pad(reference), pad(render)


def mad(first: Image.Image, second: Image.Image) -> float:
    return ImageStat.Stat(ImageChops.difference(first, second).convert("L")).mean[0]


def pct_diff(first: Image.Image, second: Image.Image, tolerance: int = 24) -> float:
    mask = ImageChops.difference(first, second).convert("L").point(lambda value: 255 if value > tolerance else 0)
    return 100.0 * ImageStat.Stat(mask).mean[0] / 255.0


def ssim(first: Image.Image, second: Image.Image, block: int = 8) -> float:
    """Block SSIM on luma: mean SSIM over non-overlapping block x block tiles."""
    luma_first, luma_second = first.convert("L"), second.convert("L")
    if luma_first.width < block or luma_first.height < block:
        return 1.0 if mad(luma_first, luma_second) < 1 else 0.0
    # luma values sampled on a grid resized to whole blocks
    blocks_x, blocks_y = max(1, luma_first.width // block), max(1, luma_first.height // block)
    grid_size = (blocks_x * block, blocks_y * block)
    pixels_first, pixels_second = luma_first.resize(grid_size).load(), luma_second.resize(grid_size).load()
    stabilizer_mean, stabilizer_var = (0.01 * 255) ** 2, (0.03 * 255) ** 2       # the usual SSIM C1, C2
    total, count = 0.0, 0
    for block_y in range(blocks_y):
        for block_x in range(blocks_x):
            values_first = [pixels_first[block_x * block + i, block_y * block + j] for j in range(block) for i in range(block)]
            values_second = [pixels_second[block_x * block + i, block_y * block + j] for j in range(block) for i in range(block)]
            size = len(values_first)
            mean_first = sum(values_first) / size; mean_second = sum(values_second) / size
            var_first = sum((value - mean_first) ** 2 for value in values_first) / size
            var_second = sum((value - mean_second) ** 2 for value in values_second) / size
            covariance = sum((value_first - mean_first) * (value_second - mean_second)
                             for value_first, value_second in zip(values_first, values_second)) / size
            numerator = (2 * mean_first * mean_second + stabilizer_mean) * (2 * covariance + stabilizer_var)
            denominator = ((mean_first * mean_first + mean_second * mean_second + stabilizer_mean)
                           * (var_first + var_second + stabilizer_var))
            total += numerator / denominator
            count += 1
    return total / max(count, 1)


def compare(reference_path, render_path, region=None, want_ssim: bool = False) -> dict:
    """Metrics of a render vs the reference, optionally inside region (x0, y0, x1, y1)."""
    reference, render = align_sizes(load(reference_path), load(render_path))
    if region:
        reference, render = reference.crop(region), render.crop(region)
    result = {"mad": round(mad(reference, render), 3), "pct": round(pct_diff(reference, render), 3), "size": list(reference.size)}
    if want_ssim:
        result["ssim"] = round(ssim(reference, render), 4)
    return result
