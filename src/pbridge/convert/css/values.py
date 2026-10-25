"""Small CSS value helpers shared by the other parsers."""
from __future__ import annotations

import re


def parse_number(token: str, scale: float = 1.0) -> float:
    """CSS number/percentage/angle/length token -> float.

    '50%' -> 0.5 * scale; 'none' or '' -> 0; units 'deg'/'px' are stripped.
    """
    token = token.strip()
    if token.endswith("%"):
        return float(token[:-1]) / 100 * scale
    if token in ("none", ""):
        return 0.0
    return float(re.sub(r"(deg|px)$", "", token))


def parse_px(value: object) -> float:
    """'12.5px' -> 12.5; 'normal', empty or unparsable -> 0."""
    if not value or value == "normal":
        return 0
    try:
        return round(float(str(value).replace("px", "")), 3)
    except ValueError:
        return 0


def split_top(text: str, separator: str = ",") -> list[str]:
    """Split on `separator` only outside parentheses: 'a(1,2), b' -> ['a(1,2)', 'b']."""
    parts, depth, current = [], 0, ""
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == separator and depth == 0:
            parts.append(current.strip()); current = ""
        else:
            current += char
    if current.strip():
        parts.append(current.strip())
    return parts
