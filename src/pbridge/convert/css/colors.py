"""CSS colors -> ('#RRGGBB', alpha) and spec paints.

Supported: #rgb[a] / #rrggbb[aa], rgb[a](), hsl[a](), oklab(), oklch(), CIE lab()/lch()
(D50 white, Bradford-adapted to D65), color(srgb|display-p3|<linear spaces>).
Fully transparent colors return None (nothing to paint).
"""
from __future__ import annotations

import colorsys
import math
import re

from pbridge.convert.css.values import parse_number

Color = tuple[str, float]          # ('#RRGGBB', alpha 0..1)
Paint = str | list                 # '#RRGGBB' or ['#RRGGBB', opacity] (spec format)


def _linear_to_srgb(channel: float) -> float:
    """Linear-light channel -> sRGB gamma-encoded channel (both 0..1)."""
    channel = max(0.0, min(1.0, channel))
    return 12.92 * channel if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def _oklab_to_rgb(lightness: float, a_axis: float, b_axis: float) -> tuple[int, int, int]:
    """OKLab (lightness, green-red axis, blue-yellow axis) -> sRGB 0-255."""
    # cube roots of the long/medium/short cone responses (LMS)
    long_root = lightness + 0.3963377774 * a_axis + 0.2158037573 * b_axis
    medium_root = lightness - 0.1055613458 * a_axis - 0.0638541728 * b_axis
    short_root = lightness - 0.0894841775 * a_axis - 1.2914855480 * b_axis
    long_cone, medium_cone, short_cone = long_root ** 3, medium_root ** 3, short_root ** 3
    red = 4.0767416621 * long_cone - 3.3077115913 * medium_cone + 0.2309699292 * short_cone
    green = -1.2684380046 * long_cone + 2.6097574011 * medium_cone - 0.3413193965 * short_cone
    blue = -0.0041960863 * long_cone - 0.7034186147 * medium_cone + 1.7076147010 * short_cone
    return tuple(round(255 * _linear_to_srgb(channel)) for channel in (red, green, blue))


def _lab_to_rgb(lightness: float, a_axis: float, b_axis: float) -> tuple[int, int, int]:
    """CSS lab() (CIE Lab, D50) -> sRGB 0-255."""
    f_y = (lightness + 16) / 116; f_x = f_y + a_axis / 500; f_z = f_y - b_axis / 200
    epsilon, kappa = 216 / 24389, 24389 / 27          # CIE constants
    x_ratio = f_x ** 3 if f_x ** 3 > epsilon else (116 * f_x - 16) / kappa
    y_ratio = ((lightness + 16) / 116) ** 3 if lightness > kappa * epsilon else lightness / kappa
    z_ratio = f_z ** 3 if f_z ** 3 > epsilon else (116 * f_z - 16) / kappa
    x_d50, y_d50, z_d50 = x_ratio * 0.96422, y_ratio * 1.0, z_ratio * 0.82521          # D50 white
    # Bradford chromatic adaptation D50 -> D65
    x_d65 = 0.9554734527042182 * x_d50 - 0.023098536874261423 * y_d50 + 0.0632593086610217 * z_d50
    y_d65 = -0.028369706963208136 * x_d50 + 1.0099954580058226 * y_d50 + 0.021041398966943008 * z_d50
    z_d65 = 0.012314001688319899 * x_d50 - 0.020507696433477912 * y_d50 + 1.3303659366080753 * z_d50
    # XYZ (D65) -> linear sRGB
    red = 3.2409699419045226 * x_d65 - 1.537383177570094 * y_d65 - 0.4986107602930034 * z_d65
    green = -0.9692436362808796 * x_d65 + 1.8759675015077202 * y_d65 + 0.04155505740717559 * z_d65
    blue = 0.05563007969699366 * x_d65 - 0.20397695888897652 * y_d65 + 1.0569715142428786 * z_d65
    return tuple(round(255 * _linear_to_srgb(channel)) for channel in (red, green, blue))


def _parse_hex(color: str) -> Color | None:
    digits = color[1:]
    if len(digits) in (3, 4):
        digits = "".join(digit * 2 for digit in digits)
    alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
    return ("#" + digits[:6].upper(), round(alpha, 3)) if alpha > 0.002 else None


def _polar_to_ab(chroma: float, hue_degrees: float) -> tuple[float, float]:
    """LCH-style chroma + hue -> the two Lab axes."""
    return chroma * math.cos(math.radians(hue_degrees)), chroma * math.sin(math.radians(hue_degrees))


def parse_color(color: str | None) -> Color | None:
    """CSS color string -> ('#RRGGBB', alpha) or None (transparent / unknown)."""
    if not color:
        return None
    color = color.strip()
    if color in ("transparent", "none", "currentcolor"):
        return None
    if color.startswith("#"):
        return _parse_hex(color)
    match = re.match(r"(rgba?|hsla?|oklab|oklch|lab|lch|color)\((.*)\)$", color)
    if not match:
        return None
    function, body = match.group(1), match.group(2)
    alpha = 1.0
    if "/" in body:                       # modern syntax: 'r g b / alpha'
        body, alpha_token = body.rsplit("/", 1)
        alpha = parse_number(alpha_token, 1.0)
    args = [arg for arg in re.split(r"[\s,]+", body.strip()) if arg]
    if function in ("rgb", "rgba"):
        red, green, blue = (parse_number(arg, 255) for arg in args[:3])
        if len(args) > 3:
            alpha = parse_number(args[3], 1.0)
    elif function in ("hsl", "hsla"):
        hue, saturation, lightness = parse_number(args[0]) / 360, parse_number(args[1], 1), parse_number(args[2], 1)
        if len(args) > 3:
            alpha = parse_number(args[3], 1.0)
        red, green, blue = (channel * 255 for channel in colorsys.hls_to_rgb(hue, lightness, saturation))
    elif function == "oklab":
        red, green, blue = _oklab_to_rgb(parse_number(args[0], 1), parse_number(args[1], 0.4), parse_number(args[2], 0.4))
    elif function == "oklch":
        lightness, chroma, hue = parse_number(args[0], 1), parse_number(args[1], 0.4), parse_number(args[2])
        red, green, blue = _oklab_to_rgb(lightness, *_polar_to_ab(chroma, hue))
    elif function == "lab":
        red, green, blue = _lab_to_rgb(parse_number(args[0], 100), parse_number(args[1], 125), parse_number(args[2], 125))
    elif function == "lch":
        lightness, chroma, hue = parse_number(args[0], 100), parse_number(args[1], 150), parse_number(args[2])
        red, green, blue = _lab_to_rgb(lightness, *_polar_to_ab(chroma, hue))
    elif function == "color":
        space = args[0]
        channels = [parse_number(arg, 1) for arg in args[1:4]]
        if space in ("srgb", "display-p3"):
            red, green, blue = (channel * 255 for channel in channels)
        else:                              # linear spaces (srgb-linear, xyz, ...)
            red, green, blue = (_linear_to_srgb(channel) * 255 for channel in channels)
    else:
        return None
    if alpha <= 0.002:
        return None
    return ("#" + "".join(f"{max(0, min(255, round(channel))):02X}" for channel in (red, green, blue)), round(alpha, 3))


def paint(color: str | Color | None, opacity: float = 1.0) -> Paint | None:
    """Color (string or parsed tuple) times opacity -> spec paint ('#hex' if opaque)."""
    parsed = parse_color(color) if isinstance(color, str) else color
    if not parsed:
        return None
    alpha = round(parsed[1] * opacity, 3)
    return parsed[0] if alpha >= 0.999 else [parsed[0], alpha]


def paint_with_op(spec_paint: Paint | None, opacity: float) -> list | None:
    """Multiply an existing spec paint by an element opacity (always returns [hex, opacity])."""
    if spec_paint is None:
        return None
    if isinstance(spec_paint, str):
        return [spec_paint, round(opacity, 3)]
    return [spec_paint[0], round(spec_paint[1] * opacity, 3)]
