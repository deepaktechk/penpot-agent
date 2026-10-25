"""Design review rules over a layer tree (Penpot `pb.serialize` output or a spec - same format).

Each rule returns issues: {"rule", "severity" (error | warning | info), "id", "key", "name",
"message", "box": [x, y, w, h], "fix": patch op or None}. Fixes are only offered where the
change is safe and unambiguous (merging near-identical values, snapping 1-2 px misalignments).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from pbridge.review.colors import RGB, contrast_ratio, distance, min_contrast, parse_hex, solid_color, to_hex

Node = dict[str, Any]
FILLED_TYPES = ("rect", "board", "ellipse", "path", "image", "svg")
DEFAULT_NAME_PREFIXES = ("Rectangle", "Ellipse", "Path", "Board", "Group", "Text")
TOUCH_TARGET = 44          # px, Apple HIG / Material minimum
SMALL_TEXT = 12            # px


@dataclass
class ReviewOptions:
    grid: int = 0                    # spacing grid in px (0 = do not check)
    mobile: bool = False             # check touch target sizes
    rules: set[str] = field(default_factory=set)   # empty = all


@dataclass
class Placed:
    """A node with its paint order (higher = painted later = on top)."""
    node: Node
    order: int
    parent: Node | None


def walk(nodes: list[Node], parent: Node | None = None, counter: list[int] | None = None) -> Iterator[Placed]:
    """Pre-order walk in paint order: a parent is painted before its children, children in list order."""
    counter = counter if counter is not None else [0]
    for node in nodes:
        counter[0] += 1
        yield Placed(node, counter[0], parent)
        yield from walk(node.get("children") or [], node, counter)


def box(node: Node) -> list[float] | None:
    if all(key in node for key in ("x", "y", "w", "h")):
        return [node["x"], node["y"], node["w"], node["h"]]
    return None


def issue(rule: str, severity: str, node: Node, message: str, fix: dict | None = None) -> dict:
    return {"rule": rule, "severity": severity, "id": node.get("id"), "key": node.get("key"), "name": node.get("name"),
            "message": message, "box": box(node), "fix": fix}


def selector(node: Node) -> dict:
    """Patch selector for a node: Penpot id when reviewing a live file, else its spec key."""
    return {"id": node["id"]} if node.get("id") else {"key": node.get("key")}


def text_style(node: Node) -> dict:
    return node.get("text") or {}


# ---------------------------------------------------------------------------------- contrast
def _background_from_tree(text_node: Placed, placed: list[Placed]) -> RGB | None:
    """Topmost solid fill painted before the text whose box contains the text's centre."""
    text_box = box(text_node.node)
    if not text_box:
        return None
    center_x, center_y = text_box[0] + text_box[2] / 2, text_box[1] + text_box[3] / 2
    best = None
    for candidate in placed:
        if candidate.order >= text_node.order or candidate.node.get("t") not in FILLED_TYPES:
            continue
        candidate_box = box(candidate.node)
        color = solid_color(candidate.node.get("fill"))
        if color and candidate_box and candidate_box[0] <= center_x <= candidate_box[0] + candidate_box[2] \
                and candidate_box[1] <= center_y <= candidate_box[1] + candidate_box[3]:
            best = color
    return parse_hex(best) if best else None


def _background_from_render(text_node: Node, render, origin: tuple[float, float], text_rgb: RGB) -> RGB | None:
    """Most common rendered colour in the text box that is not the text colour itself."""
    text_box = box(text_node)
    if render is None or not text_box:
        return None
    left, top = int(text_box[0] - origin[0]), int(text_box[1] - origin[1])
    crop = render.crop((max(0, left), max(0, top), min(render.width, left + int(text_box[2]) + 1),
                        min(render.height, top + int(text_box[3]) + 1))).convert("RGB")
    if crop.width < 2 or crop.height < 2:
        return None
    colors = [(count, rgb) for count, rgb in crop.getcolors(crop.width * crop.height) if distance(rgb, text_rgb) > 60]
    return max(colors)[1] if colors else None


def contrast(placed: list[Placed], render=None, origin=(0, 0)) -> list[dict]:
    issues = []
    for item in placed:
        node = item.node
        if node.get("t") != "text" or node.get("hidden"):
            continue
        style = text_style(node)
        text_color = parse_hex(solid_color(style.get("color")) or "")
        if not text_color or not style.get("text", "").strip():
            continue
        background = _background_from_render(node, render, origin, text_color) or _background_from_tree(item, placed)
        if not background:
            continue
        size = float(style.get("size") or 16); weight = int(float(style.get("weight") or 400))
        ratio = contrast_ratio(text_color, background); needed = min_contrast(size, weight)
        if ratio < needed:
            issues.append(issue("contrast", "error", node,
                                f"contrast {ratio:.2f}:1 between {to_hex(text_color)} text and {to_hex(background)} background "
                                f"is below WCAG AA {needed}:1 for {size:g}px/{weight}"))
    return issues


# ---------------------------------------------------------------------------------- text
def small_text(placed: list[Placed]) -> list[dict]:
    return [issue("small-text", "warning", item.node, f"text size {text_style(item.node).get('size')}px is below {SMALL_TEXT}px")
            for item in placed if item.node.get("t") == "text" and float(text_style(item.node).get("size") or 16) < SMALL_TEXT]


def font_sizes(placed: list[Placed]) -> list[dict]:
    """Sizes 1px away from a more frequent size are almost certainly the same style: merge them."""
    texts = [item.node for item in placed if item.node.get("t") == "text" and text_style(item.node).get("size")]
    counts = Counter(round(float(text_style(node)["size"]), 2) for node in texts)
    issues = []
    for node in texts:
        size = round(float(text_style(node)["size"]), 2)
        better = [other for other in counts if other != size and abs(other - size) <= 1 and counts[other] > counts[size]]
        if better:
            target = max(better, key=lambda other: counts[other])
            issues.append(issue("font-size", "warning", node, f"font size {size:g}px is next to the common {target:g}px "
                                f"({counts[target]} texts) - inconsistent type scale",
                                {"sel": selector(node), "set": {"textStyle": {"size": target}}}))
    if len(counts) > 10:
        issues.append({"rule": "font-size", "severity": "info", "id": None, "key": None, "name": None, "box": None, "fix": None,
                       "message": f"{len(counts)} different font sizes in use: consider a smaller type scale"})
    return issues


# ---------------------------------------------------------------------------------- colours
def near_duplicate_colors(placed: list[Placed]) -> list[dict]:
    """Colours that look identical (distance < 6) but are not: merge into the more frequent one."""
    usage: Counter = Counter()
    users: dict[str, list[tuple[Node, str]]] = {}
    for item in placed:
        node = item.node
        candidates = [("fill", node.get("fill"))] if node.get("t") != "text" else [("color", text_style(node).get("color"))]
        for kind, paint in candidates:
            color = solid_color(paint)
            if color:
                usage[color] += 1; users.setdefault(color, []).append((node, kind))
    issues = []
    for color in usage:
        rgb = parse_hex(color)
        similar = [other for other in usage if other != color and distance(rgb, parse_hex(other)) < 6 and usage[other] > usage[color]]
        if not similar:
            continue
        target = max(similar, key=lambda other: usage[other])
        for node, kind in users[color]:
            fix = ({"sel": selector(node), "set": {"fill": target}} if kind == "fill"
                   else {"sel": selector(node), "set": {"textStyle": {"color": target}}})
            issues.append(issue("near-duplicate-color", "warning", node,
                                f"{color} is almost {target} (used {usage[target]}x) - merge into one colour", fix))
    return issues


# ---------------------------------------------------------------------------------- geometry
def alignment(placed: list[Placed]) -> list[dict]:
    """Siblings whose left edges are 1-2 px apart were meant to line up: snap to the common edge."""
    issues = []
    siblings: dict[int, list[Node]] = {}
    for item in placed:
        if item.parent is not None and box(item.node):
            siblings.setdefault(id(item.parent), []).append(item.node)
    for group in siblings.values():
        lefts = Counter(round(node["x"], 1) for node in group)
        for node in group:
            left = round(node["x"], 1)
            near = [other for other in lefts if other != left and abs(other - left) <= 2 and lefts[other] > lefts[left]]
            if near:
                target = max(near, key=lambda other: lefts[other])
                issues.append(issue("alignment", "warning", node,
                                    f"left edge x={left:g} is {abs(target - left):g}px off the common edge x={target:g}",
                                    {"sel": selector(node), "set": {"x": target}}))
    return issues


def grid(placed: list[Placed], step: int) -> list[dict]:
    issues = []
    for item in placed:
        node = item.node
        if item.parent is None or not box(node) or node.get("t") == "text":
            continue
        parent_box = box(item.parent) or [0, 0, 0, 0]
        offsets = {"x": node["x"] - parent_box[0], "y": node["y"] - parent_box[1], "w": node["w"], "h": node["h"]}
        off_grid = {key: value for key, value in offsets.items() if abs(value - round(value / step) * step) > 0.5}
        if off_grid:
            issues.append(issue("grid", "info", node, "not on the " + str(step) + "px grid: " +
                                ", ".join(f"{key}={value:g}" for key, value in off_grid.items())))
    return issues


def is_interactive(name: str) -> bool:
    """Layer names of links and buttons: cloned layers are named after their tag ('a.nav-link',
    'a: Pricing', 'button#signup'); hand-made ones usually contain 'button' or 'btn'."""
    lowered = name.lower()
    return lowered[:2] in ("a ", "a.", "a#", "a:") or "button" in lowered or "btn" in lowered


def touch_targets(placed: list[Placed]) -> list[dict]:
    issues = []
    for item in placed:
        node = item.node
        if is_interactive(str(node.get("name") or "")) and box(node) and (node["w"] < TOUCH_TARGET or node["h"] < TOUCH_TARGET):
            issues.append(issue("touch-target", "warning", node,
                                f"{node['w']:g}x{node['h']:g}px is smaller than the {TOUCH_TARGET}x{TOUCH_TARGET}px touch target"))
    return issues


# ---------------------------------------------------------------------------------- hygiene
def hygiene(placed: list[Placed]) -> list[dict]:
    issues = []
    for item in placed:
        node = item.node
        name = str(node.get("name") or "")
        if node.get("t") == "text" and not text_style(node).get("text", "").strip():
            issues.append(issue("empty-text", "warning", node, "empty text layer"))
        if box(node) and (node["w"] < 0.5 or node["h"] < 0.5):
            issues.append(issue("degenerate", "warning", node, f"zero-size layer ({node['w']:g}x{node['h']:g})"))
        if any(name == prefix or name.startswith(prefix + " ") and name[len(prefix) + 1:].isdigit() for prefix in DEFAULT_NAME_PREFIXES):
            issues.append(issue("layer-name", "info", node, f"default layer name '{name}'"))
    return issues


RULES = ["contrast", "small-text", "font-size", "near-duplicate-color", "alignment", "grid", "touch-target", "hygiene"]


def review(nodes: list[Node], options: ReviewOptions | None = None, render=None, origin=(0, 0)) -> dict:
    """Run every enabled rule; returns {"summary": {...}, "issues": [...]} sorted by severity."""
    options = options or ReviewOptions()
    placed = list(walk(nodes))
    enabled = options.rules or set(RULES)
    issues: list[dict] = []
    if "contrast" in enabled:
        issues += contrast(placed, render, origin)
    if "small-text" in enabled:
        issues += small_text(placed)
    if "font-size" in enabled:
        issues += font_sizes(placed)
    if "near-duplicate-color" in enabled:
        issues += near_duplicate_colors(placed)
    if "alignment" in enabled:
        issues += alignment(placed)
    if "grid" in enabled and options.grid:
        issues += grid(placed, options.grid)
    if "touch-target" in enabled and options.mobile:
        issues += touch_targets(placed)
    if "hygiene" in enabled:
        issues += hygiene(placed)
    severity_order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda found: (severity_order[found["severity"]], found["rule"]))
    summary = Counter(found["severity"] for found in issues)
    return {"summary": {"layers": len(placed), "errors": summary["error"], "warnings": summary["warning"], "info": summary["info"],
                        "fixable": sum(1 for found in issues if found["fix"])},
            "issues": issues}
