"""Box decoration parsers: shadows, border radius, clip-path polygons, rotation."""
from __future__ import annotations

import math
import re

from pbridge.convert.css.colors import parse_color
from pbridge.convert.css.values import parse_number, split_top


def parse_shadows(box_shadow: str | None, opacity: float = 1.0) -> list[list]:
    """box-shadow -> [[x, y, blur, spread, '#hex', opacity, (1 if inset)], ...]"""
    shadows = []
    if not box_shadow:
        return shadows
    for part in split_top(box_shadow):
        inset = "inset" in part
        part = part.replace("inset", "").strip()
        color_match = re.search(r"((?:rgba?|oklab|oklch|hsla?|color)\([^)]*\)|#[0-9a-fA-F]{3,8})", part)
        color = parse_color(color_match.group(1)) if color_match else ("#000000", 1)
        if not color:
            continue
        lengths_text = part.replace(color_match.group(1), "") if color_match else part
        lengths = [float(value) for value in re.findall(r"(-?[\d.]+)px", lengths_text)]
        lengths += [0] * (4 - len(lengths))
        offset_x, offset_y, blur, spread = lengths[:4]
        shadows.append([offset_x, offset_y, blur, spread, color[0], round(color[1] * opacity, 3)] + ([1] if inset else []))
    return shadows


def parse_radius(radius: list[str], width: float, height: float) -> float | list[float] | None:
    """Four CSS corner radii (tl, tr, br, bl) -> one value, a list of four, or None.

    Percentages are relative to the smaller side; radii are capped at half a side.
    """
    corners = []
    for corner in radius:
        horizontal = str(corner).split(" ")[0]       # elliptical radii: keep the horizontal one
        if horizontal.endswith("%"):
            value = float(horizontal[:-1]) / 100 * min(width, height)
        else:
            value = float(re.sub("px", "", horizontal) or 0)
        corners.append(round(min(value, width / 2, height / 2), 2))
    if all(corner == corners[0] for corner in corners):
        return corners[0] or None
    return corners


def parse_clip_polygon(clip: str | None, x: float, y: float, width: float, height: float) -> str | None:
    """clip-path: polygon(...) -> absolute SVG path data, or None."""
    match = re.match(r"polygon\((.*)\)", clip or "")
    if not match:
        return None
    points = []
    for pair in split_top(match.group(1)):
        point_x, point_y = pair.split()[:2]
        points.append((x + parse_number(point_x, width), y + parse_number(point_y, height)))
    return "M " + " L ".join(f"{point_x:.2f} {point_y:.2f}" for point_x, point_y in points) + " Z"


def uniform_scale_of(transform: str | None) -> float:
    """Scale factor of a computed `matrix(s, 0, 0, s, e, f)` transform; 1.0 for anything else
    (no transform, rotation, skew or a non-uniform scale)."""
    match = re.match(r"matrix\(([^)]*)\)", transform or "")
    if not match:
        return 1.0
    scale_x, skew_y, skew_x, scale_y = [float(value) for value in match.group(1).split(",")[:4]]
    if abs(skew_y) > 1e-6 or abs(skew_x) > 1e-6 or abs(scale_x - scale_y) > 1e-4 or scale_x <= 0:
        return 1.0
    return scale_x


def rotation_of(transform: str | None) -> float:
    """Rotation angle (degrees) of a computed `matrix(a, b, c, d, e, f)` transform."""
    match = re.match(r"matrix\(([^)]*)\)", transform or "")
    if not match:
        return 0.0
    cos_scaled, sin_scaled = [float(value) for value in match.group(1).split(",")[:2]]
    angle = math.degrees(math.atan2(sin_scaled, cos_scaled))
    return round(angle, 2) if abs(angle) > 0.05 else 0.0
