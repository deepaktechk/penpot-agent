"""Design tokens from a capture: the most used colors and text styles.

Colors are weighted by usage (text lines count double, opaque backgrounds triple);
typographies are (family, size, weight, line-height, letter-spacing) tuples by frequency.
`publish_tokens` writes them into the Penpot file's local library.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from pbridge.connection import Bridge
from pbridge.convert import parse_color

Typography = tuple[str, str, str, str, str]   # (family, size, weight, lineHeight, letterSpacing) as CSS strings


def extract_tokens(layout: dict[str, Any], n_colors: int, n_types: int) -> tuple[list[str], list[Typography]]:
    color_usage: Counter = Counter()
    typography_usage: Counter = Counter()
    for element in layout["elements"]:
        if element.get("font"):
            font = element["font"]; text_color = parse_color(font[5])
            if text_color:
                color_usage[text_color[0]] += len(element.get("lines") or [1]) * 2
            typography_usage[(font[0], font[1], font[2], font[3], font[4])] += 1
        if element.get("box"):
            background = parse_color(element["box"].get("bg"))
            if background and background[1] > 0.99:
                color_usage[background[0]] += 3
    return ([color for color, _ in color_usage.most_common(n_colors)],
            [typography for typography, _ in typography_usage.most_common(n_types)])


def publish_tokens(bridge: Bridge, colors: list[str], typographies: list[Typography], prefix: str,
                   font_map: dict[str, str] | None) -> dict[str, list]:
    """Create/update library colors '<prefix>/color-NN #hex' and typographies '<prefix>/<family> <w> <size>/<lh>'."""
    results: dict[str, list] = {"colors": [], "typographies": []}
    for i, color in enumerate(colors):
        results["colors"].append(bridge.exec("return pb.addColor(DATA.name, DATA.color);",
                                             data={"name": f"{prefix}/color-{i + 1:02d} {color}", "color": color}))
    for family, size, weight, line_height_css, letter_spacing_css in typographies:
        font_size = float(size.replace("px", ""))
        line_height = float(line_height_css.replace("px", "")) if line_height_css.endswith("px") else font_size * 1.2
        letter_spacing = float(letter_spacing_css.replace("px", "")) if letter_spacing_css.endswith("px") else 0
        name = f"{prefix}/{family} {int(float(weight))} {font_size:g}/{line_height:g}"
        style = {"font": font_map.get(family, family) if font_map else family, "weight": int(float(weight)),
                 "size": font_size, "lh": line_height, "ls": letter_spacing}
        results["typographies"].append(bridge.exec("return pb.addTypography(DATA.name, DATA.style);",
                                                   data={"name": name, "style": style}))
    return results
