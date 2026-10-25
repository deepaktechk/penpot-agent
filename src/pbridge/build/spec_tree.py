"""Pure helpers over spec node trees (no Penpot access)."""
from __future__ import annotations

import re
from typing import Any

Node = dict[str, Any]


def assign_keys(nodes: list[Node], prefix: str = "") -> list[Node]:
    """Give every node a stable hierarchical key ("n0", "sec03.2.1"); keeps existing keys."""
    for i, node in enumerate(nodes):
        if not node.get("key"):
            node["key"] = f"{prefix}{i}" if prefix else f"n{i}"
        if node.get("children"):
            assign_keys(node["children"], node["key"] + ".")
    return nodes


def flatten(nodes: list[Node], into: list[Node] | None = None) -> list[Node]:
    """Pre-order list of every node in the tree."""
    into = [] if into is None else into
    for node in nodes:
        into.append(node)
        flatten(node.get("children", []), into)
    return into


def node_box(node: Node) -> list[float] | None:
    """[x, y, w, h] of a positioned node (groups have no box of their own)."""
    if all(key in node for key in ("x", "y", "w", "h")) and node.get("t") not in ("group",):
        return [node["x"], node["y"], node["w"], node["h"]]
    return None


def _shift_path(path_data: str, dx: float, dy: float) -> str:
    """Translate absolute SVG path data: numbers alternate x, y after each command letter."""
    tokens = re.split(r"(\s+|,)", path_data)
    shifted, axis = [], 0          # axis: 0, 2, 4... = x coordinate, odd = y coordinate
    for token in tokens:
        try:
            value = float(token)
            shifted.append(f"{value + (dx if axis % 2 == 0 else dy):.2f}"); axis += 1
        except ValueError:
            if token.strip().isalpha():
                axis = 0
            shifted.append(token)
    return "".join(shifted)


def offset_nodes(nodes: list[Node], dx: float = 0.0, dy: float = 0.0) -> list[Node]:
    """Translate a spec tree in place (positions and path data)."""
    for node in flatten(nodes):
        if "x" in node:
            node["x"] = round(node["x"] + dx, 2)
        if "y" in node:
            node["y"] = round(node["y"] + dy, 2)
        if node.get("t") in ("path", "line") and node.get("d") and (dx or dy):
            node["d"] = _shift_path(node["d"], dx, dy)
    return nodes
