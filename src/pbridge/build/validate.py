"""Check a spec before building it: catch the mistakes hand-written and AI-written specs make.

Errors stop `pb build` (missing required keys, wrong types, broken paints, ranges outside the
text, image keys that cannot be resolved); warnings do not (unknown keys - usually typos such as
"width" instead of "w" - and doubtful values). The format is documented in docs/spec-format.md
and typed in js/src/plugin/spec.ts.
"""
from __future__ import annotations

import difflib
import math
import re
from typing import Any

NODE_TYPES = {"board", "frame", "rect", "ellipse", "path", "line", "text", "image", "svg", "group", "component"}
COMMON_KEYS = {"t", "key", "tag", "name", "x", "y", "w", "h", "fill", "stroke", "sh", "blur", "op", "blend", "r", "hidden",
               "locked", "flipX", "flipY", "cons", "data", "children", "component", "child", "rot"}
TYPE_KEYS = {
    "board": {"clip", "flex", "layout"}, "frame": {"clip", "flex", "layout"},
    "path": {"d"}, "line": {"d"}, "text": {"text"}, "svg": {"svg"},
    "image": {"img", "fit", "nat", "pos", "iop"}, "component": {"ref"},
}
TEXT_KEYS = {"text", "font", "weight", "italic", "size", "lh", "lhr", "ls", "color", "upper", "lower", "cap", "deco", "align",
             "valign", "grow", "fitW", "ranges"}
RANGE_STYLE_KEYS = {"font", "weight", "italic", "size", "lh", "lhr", "ls", "color", "upper", "lower", "cap", "deco"}
LAYOUT_KEYS = {"type", "dir", "gap", "padding", "align", "justify", "alignContent", "wrap", "sizing", "columns", "rows"}
CHILD_KEYS = {"sizing", "alignSelf", "margin", "absolute", "zIndex", "minW", "maxW", "minH", "maxH", "cell"}
NEEDS_BOX = {"board", "frame", "rect", "ellipse", "image", "svg"}
HEX_RE = re.compile(r"^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8}|[0-9A-Fa-f]{3})$")
SIZING = {"fix", "auto", "fill"}


class SpecReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _unknown_keys(report: SpecReport, where: str, mapping: dict, allowed: set[str]) -> None:
    for key in mapping:
        if key not in allowed:
            hint = difflib.get_close_matches(key, sorted(allowed), n=1)
            suggestion = f" (did you mean '{hint[0]}'?)" if hint else ""
            report.warn(where, f"unknown key '{key}'{suggestion}")


def _check_paint(report: SpecReport, where: str, paint: Any, images: dict) -> None:
    if paint is None or paint is False:
        return
    if isinstance(paint, str):
        if not HEX_RE.match(paint):
            report.error(where, f"colour '{paint}' is not #RGB, #RRGGBB or #RRGGBBAA")
    elif isinstance(paint, list):
        if len(paint) == 2 and isinstance(paint[0], str) and _is_number(paint[1]):
            _check_paint(report, where, paint[0], images)
            if not 0 <= paint[1] <= 1:
                report.error(where, f"opacity {paint[1]} outside 0..1")
        else:
            for index, item in enumerate(paint):
                _check_paint(report, f"{where}[{index}]", item, images)
    elif isinstance(paint, dict):
        if "g" in paint:
            geometry = paint["g"]
            if not (isinstance(geometry, list) and len(geometry) == 5 and all(_is_number(value) for value in geometry[:4])
                    and isinstance(geometry[4], list) and geometry[4]):
                report.error(where, "gradient must be {\"g\": [x1, y1, x2, y2, [[hex, opacity, offset], ...]]}")
            else:
                for stop in geometry[4]:
                    if not (isinstance(stop, list) and len(stop) == 3 and isinstance(stop[0], str)):
                        report.error(where, f"gradient stop {stop!r} must be [hex, opacity, offset]")
                    else:
                        _check_paint(report, where, stop[0], images)
        elif "img" in paint:
            if images is not None and paint["img"] not in images:
                report.warn(where, f"image key '{paint['img']}' is not in the spec's images (must be uploaded already)")
        else:
            report.error(where, f"paint {paint!r} is neither a colour, a gradient nor an image")
    else:
        report.error(where, f"paint {paint!r} has the wrong type")


def _check_text(report: SpecReport, where: str, text: Any) -> None:
    if not isinstance(text, dict) or not isinstance(text.get("text"), str):
        report.error(where, "text nodes need \"text\": {\"text\": \"...\", ...}")
        return
    _unknown_keys(report, where + ".text", text, TEXT_KEYS)
    for key in ("size", "lh", "lhr", "ls", "fitW"):
        if key in text and not _is_number(text[key]):
            report.error(where, f"text.{key} must be a number")
    if "size" in text and _is_number(text["size"]) and text["size"] <= 0:
        report.error(where, "text.size must be > 0")
    length = len(text["text"])
    for index, text_range in enumerate(text.get("ranges") or []):
        if not (isinstance(text_range, list) and len(text_range) == 3 and _is_number(text_range[0]) and _is_number(text_range[1])
                and isinstance(text_range[2], dict)):
            report.error(where, f"ranges[{index}] must be [start, end, style]")
            continue
        start, end, style = text_range
        if not 0 <= start < end <= length:
            report.error(where, f"ranges[{index}] [{start}, {end}] is outside the text (length {length})")
        _unknown_keys(report, f"{where}.ranges[{index}]", style, RANGE_STYLE_KEYS)


def _check_layout(report: SpecReport, where: str, layout: Any) -> None:
    if not isinstance(layout, dict) or layout.get("type") not in ("flex", "grid"):
        report.error(where, "layout needs \"type\": \"flex\" or \"grid\"")
        return
    _unknown_keys(report, where + ".layout", layout, LAYOUT_KEYS)
    sizing = layout.get("sizing")
    if sizing is not None and not (isinstance(sizing, list) and len(sizing) == 2 and set(sizing) <= SIZING):
        report.error(where, "layout.sizing must be [horizontal, vertical] of fix / auto / fill")
    if layout.get("type") == "flex" and ("columns" in layout or "rows" in layout):
        report.warn(where, "columns/rows only apply to grid layouts")


def _check_node(report: SpecReport, node: Any, where: str, images: dict, keys_seen: set[str], parent_layout: bool) -> None:
    if not isinstance(node, dict):
        report.error(where, "node must be an object")
        return
    node_type = node.get("t")
    label = f"{where} ({node.get('name') or node.get('key') or node_type})"
    if node_type not in NODE_TYPES:
        hint = difflib.get_close_matches(str(node_type), sorted(NODE_TYPES), n=1)
        report.error(label, f"unknown type t={node_type!r}" + (f" (did you mean '{hint[0]}'?)" if hint else ""))
        return
    _unknown_keys(report, label, node, COMMON_KEYS | TYPE_KEYS.get(node_type, set()))
    for key in ("x", "y", "w", "h", "op", "blur", "rot"):
        if key in node and not _is_number(node[key]):
            report.error(label, f"'{key}' must be a number, got {node[key]!r}")
    if node_type in NEEDS_BOX and not (node.get("layout") or parent_layout):
        for key in ("x", "y", "w", "h"):
            if key not in node:
                report.error(label, f"missing '{key}'")
    for key in ("w", "h"):
        if _is_number(node.get(key)) and node[key] <= 0:
            report.error(label, f"'{key}' must be > 0")
    if _is_number(node.get("op")) and not 0 <= node["op"] <= 1:
        report.error(label, "'op' (opacity) must be 0..1")
    if node.get("key"):
        if node["key"] in keys_seen:
            report.error(label, f"duplicate key '{node['key']}'")
        keys_seen.add(node["key"])
    if "fill" in node:
        _check_paint(report, label + ".fill", node["fill"], images)
    if node_type == "text":
        _check_text(report, label, node.get("text"))
    elif node_type == "image" and not node.get("img"):
        report.error(label, "image nodes need \"img\" (an asset key)")
    elif node_type == "image" and images is not None and node["img"] not in images:
        report.warn(label, f"image key '{node['img']}' is not in the spec's images (must be uploaded already)")
    elif node_type == "svg" and not str(node.get("svg", "")).lstrip().startswith("<svg"):
        report.error(label, "svg nodes need \"svg\": \"<svg ...>...</svg>\"")
    elif node_type in ("path", "line") and not node.get("d"):
        report.error(label, "path nodes need \"d\" (SVG path data)")
    elif node_type == "component" and not node.get("ref"):
        report.error(label, "component nodes need \"ref\" (library component name or id)")
    if node.get("layout") is not None:
        if node_type not in ("board", "frame"):
            report.error(label, "only boards can have a layout")
        _check_layout(report, label, node["layout"])
    if node.get("child") is not None:
        if not isinstance(node["child"], dict):
            report.error(label, "child must be an object")
        else:
            _unknown_keys(report, label + ".child", node["child"], CHILD_KEYS)
            if not parent_layout:
                report.warn(label, "child layout properties have no effect: the parent has no layout")
    children = node.get("children")
    if children is not None:
        if not isinstance(children, list):
            report.error(label, "children must be a list")
            return
        if node_type not in ("board", "frame", "group"):
            report.warn(label, f"children of a {node_type} are ignored")
        has_layout = bool(node.get("layout") or node.get("flex"))
        for index, child in enumerate(children):
            _check_node(report, child, f"{where}.children[{index}]", images, keys_seen, has_layout)


def validate_spec(spec: Any) -> SpecReport:
    """Validate a spec document ({"nodes": [...], "images": {...}}) or a bare list of nodes."""
    report = SpecReport()
    if isinstance(spec, dict):
        nodes, images = spec.get("nodes"), spec.get("images", {})
        if not isinstance(nodes, list):
            report.error("spec", "needs \"nodes\": [...]")
            return report
    elif isinstance(spec, list):
        nodes, images = spec, None
    else:
        report.error("spec", "must be an object with \"nodes\" or a list of nodes")
        return report
    if not nodes:
        report.warn("spec", "no nodes")
    keys_seen: set[str] = set()
    for index, node in enumerate(nodes):
        _check_node(report, node, f"nodes[{index}]", images, keys_seen, False)
    return report
