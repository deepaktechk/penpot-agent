"""CSS gradients -> spec gradient paints, and gradient text emulation.

Spec gradient: {"g": [x1, y1, x2, y2, [[hex, opacity, offset], ...]], "radial": 1?}
with start/end points in the shape's unit box (0..1).
"""
from __future__ import annotations

import math
import re

from pbridge.convert.css.colors import parse_color
from pbridge.convert.css.values import split_top

# CSS "to <side>" keywords -> angle in degrees (0 = up, 90 = right)
ANGLES = {"to right": 90, "to left": 270, "to bottom": 180, "to top": 0, "to right bottom": 135, "to bottom right": 135,
          "to left bottom": 225, "to bottom left": 225, "to right top": 45, "to top right": 45, "to left top": 315, "to top left": 315}

# one color stop: color, optional position (% or px), optional second position
_STOP_RE = re.compile(r"^(.*?\)|#[0-9a-fA-F]+|transparent|[a-z]+)\s*([-\d.]+%|[-\d.]+px)?(?:\s+([-\d.]+%))?$")
_TRANSPARENT = ("#000000", 0.0)


def _linear_angle(parts: list[str]) -> float:
    """Consume the direction/interpolation prefix of a linear gradient; return its angle."""
    angle = 180.0
    first = parts[0]
    if first.startswith("to "):
        angle = ANGLES.get(re.sub(r"\s+", " ", first.replace("in oklab", "").strip()), 180); parts.pop(0)
    elif re.match(r"^-?[\d.]+(deg|turn|rad)", first):
        value = float(re.match(r"-?[\d.]+", first).group(0))
        angle = value * 360 if "turn" in first else math.degrees(value) if "rad" in first else value
        parts.pop(0)
    elif first.startswith("in "):          # color interpolation space only
        parts.pop(0)
    if parts and parts[0].startswith("in "):
        parts.pop(0)
    return angle


def _parse_stops(parts: list[str], width: float, opacity: float) -> list[list]:
    stops = []
    count = len(parts)
    for index, part in enumerate(parts):
        match = _STOP_RE.match(part.strip())
        if not match:
            continue
        color_token, position = match.group(1), match.group(2)
        color = _TRANSPARENT if color_token == "transparent" else parse_color(color_token) or _TRANSPARENT
        if position:
            offset = float(position[:-1]) / 100 if position.endswith("%") else float(position[:-2]) / max(width, 1)
        else:
            offset = index / max(1, count - 1)        # evenly spaced when no position is given
        stops.append([color[0], round(color[1] * opacity, 4), round(max(0, min(1, offset)), 4)])
    # transparent stops take the neighbour's color (CSS interpolates in premultiplied space)
    for index, stop in enumerate(stops):
        if stop[1] == 0 and stop[0] == "#000000":
            neighbour = stops[index + 1] if index + 1 < len(stops) else stops[index - 1] if index else None
            if neighbour:
                stop[0] = neighbour[0]
    return stops


def parse_gradient(background_image: str, width: float = 1, height: float = 1, opacity: float = 1.0) -> dict | None:
    """CSS linear/radial-gradient() -> spec gradient paint, or None."""
    match = re.match(r"(repeating-)?(linear|radial)-gradient\((.*)\)$", background_image.strip(), re.S)
    if not match:
        return None
    kind, body = match.group(2), match.group(3)
    parts = split_top(body)
    angle = 180.0
    if kind == "linear":
        angle = _linear_angle(parts)
    elif not re.match(r"^(rgb|rgba|oklab|oklch|hsl|#|color|transparent)", parts[0]):
        parts.pop(0)                       # radial shape/position prefix
    stops = _parse_stops(parts, width, opacity)
    if not stops:
        return None
    if kind == "radial":
        return {"g": [0.5, 0.5, 1.0, 0.5, stops], "radial": 1}
    # CSS angle -> start/end points of the gradient line through the box centre
    radians = math.radians(angle)
    dx, dy = math.sin(radians), -math.cos(radians)
    line_length = abs(width * dx) + abs(height * dy)
    half_x, half_y = dx * line_length / 2 / max(width, 1e-6), dy * line_length / 2 / max(height, 1e-6)
    return {"g": [round(0.5 - half_x, 4), round(0.5 - half_y, 4), round(0.5 + half_x, 4), round(0.5 + half_y, 4), stops]}


def lerp_stop(stops: list[list], position: float) -> tuple[str, float]:
    """Sample a gradient (stops [[hex, opacity, offset], ...]) at `position` -> (hex, opacity)."""
    stops = sorted(stops, key=lambda stop: stop[2])
    if position <= stops[0][2]:
        return stops[0][0], stops[0][1]
    for before, after in zip(stops, stops[1:]):
        if before[2] <= position <= after[2]:
            fraction = (position - before[2]) / max(1e-6, after[2] - before[2])
            rgb_before = [int(before[0][i:i + 2], 16) for i in (1, 3, 5)]
            rgb_after = [int(after[0][i:i + 2], 16) for i in (1, 3, 5)]
            color = "#" + "".join(f"{round(start + (end - start) * fraction):02X}" for start, end in zip(rgb_before, rgb_after))
            return color, round(before[1] + (after[1] - before[1]) * fraction, 3)
    return stops[-1][0], stops[-1][1]


def gradient_char_ranges(start: int, end: int, gradient: dict, text: str) -> list[list]:
    """Penpot cannot paint gradients on text ranges: emulate a (mostly horizontal)
    gradient with one solid color per character, sampled at the character centre."""
    geometry = gradient["g"]; stops = geometry[4]
    char_indexes = [i for i in range(start, end) if text[i] not in "\n"]
    ranges = []
    count = max(1, len(char_indexes))
    for order, char_index in enumerate(char_indexes):
        along_text = (order + 0.5) / count
        # project onto the gradient axis (x1,y1)->(x2,y2) in the unit box; text runs along x
        start_x, end_x = geometry[0], geometry[2]
        along_axis = (along_text - start_x) / (end_x - start_x) if abs(end_x - start_x) > 1e-6 else 0.5
        color, opacity = lerp_stop(stops, max(0.0, min(1.0, along_axis)))
        ranges.append([char_index, char_index + 1, {"color": color if opacity >= 0.999 else [color, opacity]}])
    return ranges
