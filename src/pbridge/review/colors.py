"""Colour maths for design review: parsing spec paints, WCAG contrast, perceptual distance."""
from __future__ import annotations

RGB = tuple[int, int, int]


def parse_hex(value: str) -> RGB | None:
    """'#RGB' / '#RRGGBB' / '#RRGGBBAA' -> (r, g, b); anything else -> None."""
    if not isinstance(value, str) or not value.startswith("#"):
        return None
    digits = value[1:]
    if len(digits) in (3, 4):
        digits = "".join(digit * 2 for digit in digits[:3])
    if len(digits) not in (6, 8):
        return None
    try:
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def solid_color(paint) -> str | None:
    """The single solid colour of a spec paint ('#hex' or ['#hex', opacity >= 0.95]), else None."""
    if isinstance(paint, str):
        return paint.upper()[:7] if parse_hex(paint) else None
    if isinstance(paint, list) and len(paint) == 2 and isinstance(paint[0], str) and isinstance(paint[1], (int, float)):
        return paint[0].upper()[:7] if paint[1] >= 0.95 and parse_hex(paint[0]) else None
    return None


def to_hex(rgb: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def luminance(rgb: RGB) -> float:
    """WCAG relative luminance."""
    red, green, blue = (_linear(channel) for channel in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: RGB, second: RGB) -> float:
    """WCAG contrast ratio, 1..21."""
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def min_contrast(font_size: float, weight: int) -> float:
    """WCAG AA: 3:1 for large text (>= 24 px, or >= 18.66 px bold), 4.5:1 otherwise."""
    large = font_size >= 24 or (font_size >= 18.66 and weight >= 700)
    return 3.0 if large else 4.5


def distance(first: RGB, second: RGB) -> float:
    """Perceptual-ish distance ("redmean" weighted RGB); < ~12 looks identical, < ~25 very close."""
    mean_red = (first[0] + second[0]) / 2
    delta_red, delta_green, delta_blue = (first[0] - second[0]), (first[1] - second[1]), (first[2] - second[2])
    return ((2 + mean_red / 256) * delta_red ** 2 + 4 * delta_green ** 2 + (2 + (255 - mean_red) / 256) * delta_blue ** 2) ** 0.5 / 3
