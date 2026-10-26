"""`--layout auto`: Penpot flex layouts for containers whose children they reproduce exactly.

The pass runs on the finished spec tree (after snapping), so it sees every node at the absolute
position the absolute build would give it. For each container group (a DOM element with a box,
tagged `_rect` by the tree assembler) it looks for a flex layout that puts every in-flow child at
exactly that position, simulated with Penpot's own rules (`simulate`, measured against Penpot in
tests/fixtures/penpot_layout_conformance.json). Only a verified layout is emitted; otherwise the
container stays an absolutely positioned group, so `auto` never places a shape differently from
`absolute`.

Encodings, in order of preference:
  semantic  the container's CSS flex (direction, gap, padding, justify, align) as is
  derived   justify start along the children's axis, the smallest spacing as gap, the rest as
            margins (exact by construction for any non-overlapping row or column)

Penpot rules that differ from CSS (measured, see AGENTS.md):
  * space-around / space-evenly ignore the gap -> used only when the CSS gap is 0
  * align-self center/end of a child larger than the cross room puts it at the start (the
    container's align-items centres / ends it like CSS); negative margins work
  * reverse directions put "start" at the physical start -> children are ordered physically and
    the direction stays forward (CSS flex-start/flex-end of a reverse container are mirrored)
  * a flex board paints its children in spec (append) order, later on top, and flows the in-flow
    ones in that same order; its `parentIndex` values are stored reversed and do not tell the
    paint order (measured by exporting). So the original paint order is kept and only the flow
    items are re-sequenced into flow order, which is refused if it would swap overlapping items.
  * the builder makes a group by building its children into the group's parent first: in a flex
    board they would be flowed before being grouped. A group directly in a flex board therefore
    becomes a plain board of the same bounds (no layout, fill or clip: it looks the same).
  * shapes the plugin resizes or moves after building stay absolute: `contain`-fitted images (the
    picture is smaller than its box) and symbol lines fitted in Penpot (`fitW`, anchored after fitting)
  * grid layouts are not emitted yet (grid containers stay absolute)

Node tags set by the tree assembler (removed from the output):
  _rect  element border box of a container group      _lay  its captured flex/grid CSS
  _own   the container's own paint (not text)          _oof  out of flow (position absolute/fixed)
"""
from __future__ import annotations

from typing import Any

from pbridge.convert.context import ConversionContext, Node

TOLERANCE = 0.02          # px: a layout is used only if every child lands this close
CONTAINS_SLACK = 0.5      # px: children poking this far out of the element box still count as inside
OVERLAP_MIN = 0.5         # px: thinner intersections are touching edges, not overlaps

Box = tuple[float, float, float, float]   # x, y, width, height

JUSTIFY = {"normal": "start", "flex-start": "start", "start": "start", "left": "start", "stretch": "start",
           "center": "center", "flex-end": "end", "end": "end", "right": "end",
           "space-between": "space-between", "space-around": "space-around", "space-evenly": "space-evenly"}
ALIGN = {"normal": "start", "stretch": "start", "flex-start": "start", "start": "start", "self-start": "start",
         "center": "center", "flex-end": "end", "end": "end", "self-end": "end"}
MIRRORED = {"start": "end", "end": "start"}


# ---------------------------------------------------------------------- geometry
def node_box(node: Node) -> Box | None:
    """Bounds Penpot gives the shape: a group is the union of its children, anything else its own box."""
    if node.get("t") == "group":
        return union([box for box in (node_box(child) for child in node.get("children", [])) if box])
    if all(isinstance(node.get(key), (int, float)) for key in ("x", "y", "w", "h")):
        return (node["x"], node["y"], node["w"], node["h"])
    return None


def visual_box(node: Node) -> Box | None:
    """Everything the node paints: unclipped boards and groups include their children."""
    own = node_box(node)
    if node.get("t") in ("group", "board") and not node.get("clip"):
        return union([box for box in [own] + [visual_box(child) for child in node.get("children", [])] if box])
    return own


def union(boxes: list[Box]) -> Box | None:
    if not boxes:
        return None
    left = min(box[0] for box in boxes); top = min(box[1] for box in boxes)
    right = max(box[0] + box[2] for box in boxes); bottom = max(box[1] + box[3] for box in boxes)
    return (left, top, right - left, bottom - top)


def overlaps(first: Box | None, second: Box | None) -> bool:
    if not first or not second:
        return False
    width = min(first[0] + first[2], second[0] + second[2]) - max(first[0], second[0])
    height = min(first[1] + first[3], second[1] + second[3]) - max(first[1], second[1])
    return width > OVERLAP_MIN and height > OVERLAP_MIN


def contains(outer: Box, inner: Box) -> bool:
    return (inner[0] >= outer[0] - CONTAINS_SLACK and inner[1] >= outer[1] - CONTAINS_SLACK
            and inner[0] + inner[2] <= outer[0] + outer[2] + CONTAINS_SLACK and inner[1] + inner[3] <= outer[1] + outer[3] + CONTAINS_SLACK)


class Axes:
    """Main / cross axis accessors of a box for a flex direction ("row" or "column")."""

    def __init__(self, direction: str):
        self.row = direction == "row"

    def start(self, box: Box) -> float:
        return box[0] if self.row else box[1]

    def size(self, box: Box) -> float:
        return box[2] if self.row else box[3]

    def cross_start(self, box: Box) -> float:
        return box[1] if self.row else box[0]

    def cross_size(self, box: Box) -> float:
        return box[3] if self.row else box[2]

    def padding(self, padding: list[float]) -> tuple[float, float, float, float]:
        """[top, right, bottom, left] -> (main start, main end, cross start, cross end)."""
        top, right, bottom, left = padding
        return (left, right, top, bottom) if self.row else (top, bottom, left, right)

    def to_padding(self, main_start: float, main_end: float, cross_start: float, cross_end: float) -> list[float]:
        return [cross_start, main_end, cross_end, main_start] if self.row else [main_start, cross_end, main_end, cross_start]

    def margin(self, main_before: float, cross_before: float) -> list[float]:
        """[top, right, bottom, left] with only the leading margins set."""
        return [cross_before, 0, 0, main_before] if self.row else [main_before, 0, 0, cross_before]


# ---------------------------------------------------------------------- Penpot flex (measured rules)
def four_sides(value: Any) -> list[float]:
    """Spec shorthand like CSS: 8 | [vertical, horizontal] | [top, right, bottom, left]."""
    if value is None:
        return [0.0, 0.0, 0.0, 0.0]
    if isinstance(value, (int, float)):
        return [float(value)] * 4
    if len(value) == 2:
        return [value[0], value[1], value[0], value[1]]
    return list(value)


def main_gap(layout: dict[str, Any]) -> float:
    """Gap along the direction: a number, or [row gap, column gap] (spec)."""
    gap = layout.get("gap", 0)
    if isinstance(gap, (list, tuple)):
        return gap[1] if Axes(layout.get("dir", "row")).row else gap[0]
    return gap


def simulate(layout: dict[str, Any], board: Box, sizes: list[tuple[float, float]],
             children: list[dict[str, Any]] | None = None) -> list[tuple[float, float]]:
    """Top-left corner Penpot gives each fixed-size child of a single-line flex board.

    layout: {dir row|column, gap, padding [t, r, b, l], justify, align}; children: per child
    {margin [t, r, b, l], alignSelf}. Matches Chrome except space-around/evenly, where Penpot
    ignores the gap (tests/fixtures/penpot_layout_conformance.json)."""
    axes = Axes(layout.get("dir", "row"))
    children = children or [{} for _ in sizes]
    pad_main_start, pad_main_end, pad_cross_start, pad_cross_end = axes.padding(four_sides(layout.get("padding")))
    gap = main_gap(layout)
    content_start = axes.start(board) + pad_main_start
    content_size = axes.size(board) - pad_main_start - pad_main_end
    cross_origin = axes.cross_start(board) + pad_cross_start
    cross_room = axes.cross_size(board) - pad_cross_start - pad_cross_end
    margins = [axes.padding(four_sides(child.get("margin"))) for child in children]   # (before, after, cross before, cross after)
    main_sizes = [width if axes.row else height for width, height in sizes]
    cross_sizes = [height if axes.row else width for width, height in sizes]
    outer = [size + margin[0] + margin[1] for size, margin in zip(main_sizes, margins)]
    count = len(sizes)
    justify = layout.get("justify", "start")
    offset, between = 0.0, gap
    if justify in ("space-around", "space-evenly"):
        free = content_size - sum(outer)                      # Penpot: the gap is not part of the distribution
        slots = count if justify == "space-around" else count + 1
        between = free / slots
        offset = between / 2 if justify == "space-around" else between
    else:
        free = content_size - sum(outer) - gap * (count - 1)
        if justify == "center":
            offset = free / 2
        elif justify == "end":
            offset = free
        elif justify == "space-between" and count > 1:
            between = gap + free / (count - 1)
    positions = []
    cursor = content_start + offset
    for i in range(count):
        main = cursor + margins[i][0]
        cursor += outer[i] + between
        align = children[i].get("alignSelf") or layout.get("align", "start")
        cross_before, cross_after = margins[i][2], margins[i][3]
        if children[i].get("alignSelf") and cross_sizes[i] + cross_before + cross_after > cross_room + TOLERANCE:
            align = "start"                                    # Penpot: an overflowing align-self child goes to the start
        if align == "center":
            cross = cross_origin + cross_before + (cross_room - cross_sizes[i] - cross_before - cross_after) / 2
        elif align == "end":
            cross = cross_origin + cross_room - cross_sizes[i] - cross_after
        else:                                                  # start, stretch of a fixed-size child
            cross = cross_origin + cross_before
        positions.append((main, cross) if axes.row else (cross, main))
    return positions


# ---------------------------------------------------------------------- encoder
class LayoutEncoder:
    def __init__(self, ctx: ConversionContext):
        self.ctx = ctx

    def apply(self, sections: list[Node]) -> None:
        """Encode layouts inside every section (sections are page slices, not DOM boxes), then drop the tags."""
        for section in sections:
            for child in section.get("children", []):
                self.visit(child)
            children = section.get("children", [])
            if len(children) == 1 and children[0].get("t") == "group":
                section["children"] = children[0]["children"]   # the section board is that group (as in absolute mode)
        for section in sections:
            strip_tags(section)

    def visit(self, node: Node) -> None:
        for child in node.get("children", []):   # children first: their final bounds feed the parent
            self.visit(child)
        if node.get("t") == "group" and node.get("_rect"):
            if self.encode(node):
                self.ctx.report["layout_boards"] += 1
            else:
                self.ctx.report["layout_kept_absolute"] += 1

    def encode(self, node: Node) -> bool:
        """Turn a container group into a flex board when a verified layout exists."""
        children = node["children"]
        flow = [child for child in children if not (child.get("_own") or child.get("_oof") or child.get("rot") or self.settles_later(child))
                and node_box(child)]
        if not flow:
            return False
        css = node.get("_lay") or {}
        if css.get("d") == "grid" or (css.get("d") == "flex" and css.get("wrap", "nowrap") != "nowrap"):
            return False                       # grid and multi-line flex: not encoded yet
        flow_boxes = [node_box(child) for child in flow]
        board = tuple(node["_rect"])
        if not all(contains(board, box) for box in flow_boxes):
            board = union([board] + flow_boxes)
        directions = (["row" if css["dir"].startswith("row") else "column"] if css.get("d") == "flex" else ["column", "row"])
        for direction in directions:
            axes = Axes(direction)
            order = sorted(range(len(flow)), key=lambda i: axes.start(flow_boxes[i]))
            boxes = [flow_boxes[i] for i in order]
            if any(axes.start(boxes[i]) < axes.start(boxes[i - 1]) + axes.size(boxes[i - 1]) - TOLERANCE for i in range(1, len(boxes))):
                continue                       # not a single row/column
            semantic = self.semantic(css, direction, board, boxes) if css.get("d") == "flex" else None
            encoding = semantic or self.derived(direction, board, boxes)
            if not encoding:
                continue
            layers = self.layer_order(children, flow, [flow[i] for i in order])
            if layers is None:
                continue                       # flow order would paint overlapping items the wrong way round
            layout, child_props = encoding
            for item, props in zip([flow[i] for i in order], child_props):
                item["child"] = {"sizing": self.sizing(item), **props}
            node.update({"t": "board", "x": board[0], "y": board[1], "w": board[2], "h": board[3], "fill": None, "clip": False,
                         "layout": {"type": "flex", **layout, "sizing": ["fix", "fix"], "pin": True}, "children": layers})
            flow_ids = {id(item) for item in flow}
            for child in layers:
                if id(child) not in flow_ids:
                    child["child"] = {"absolute": True}
                if child.get("t") == "group":
                    as_board(child)
            self.ctx.report["layout_flow_items"] += len(flow)
            return True
        return False

    @staticmethod
    def settles_later(node: Node) -> bool:
        """Shapes whose final box the plugin decides after building: they keep their x/y."""
        return ((node.get("t") == "image" and node.get("fit") == "contain")
                or (node.get("t") == "text" and bool((node.get("text") or {}).get("fitW"))))

    @staticmethod
    def sizing(item: Node) -> list[str]:
        """Fixed boxes keep the browser size; texts keep their grow behaviour (hug a single line)."""
        grow = (item.get("text") or {}).get("grow") if item.get("t") == "text" else None
        if grow == "auto-width":
            return ["auto", "auto"]
        if grow == "auto-height":
            return ["fix", "auto"]
        return ["fix", "fix"]

    def semantic(self, css: dict[str, Any], direction: str, board: Box, boxes: list[Box]):
        """The container's own CSS flex, if Penpot reproduces it (cross misfits get align-self / margins)."""
        reverse = css.get("dir", "").endswith("reverse")
        justify = JUSTIFY.get(css.get("jc", "normal"))
        if justify is None:
            return None
        if reverse and css.get("jc") in ("normal", "flex-start", "flex-end", "stretch"):
            justify = MIRRORED.get(justify, justify)    # flex-start of a reverse container is the physical end
        axes = Axes(direction)
        gap = css["gap"][1] if axes.row else css["gap"][0]
        if justify in ("space-around", "space-evenly") and gap > TOLERANCE:
            return None                                  # Penpot ignores the gap there
        layout = {"dir": direction, "gap": gap, "padding": list(css["inset"]), "justify": justify,
                  "align": ALIGN.get(css.get("ai", "normal"), "start")}
        return self.fit_cross(layout, board, boxes)

    def derived(self, direction: str, board: Box, boxes: list[Box]):
        """Start-justified row/column: smallest spacing as gap, the rest as leading margins."""
        axes = Axes(direction)
        spacings = [axes.start(boxes[i]) - axes.start(boxes[i - 1]) - axes.size(boxes[i - 1]) for i in range(1, len(boxes))]
        gap = round(max(0.0, min(spacings)), 3) if spacings else 0.0
        main_start = axes.start(boxes[0]) - axes.start(board)
        main_end = axes.start(board) + axes.size(board) - axes.start(boxes[-1]) - axes.size(boxes[-1])
        cross_start = min(axes.cross_start(box) for box in boxes) - axes.cross_start(board)
        cross_end = axes.cross_start(board) + axes.cross_size(board) - max(axes.cross_start(box) + axes.cross_size(box) for box in boxes)
        padding = axes.to_padding(round(max(0.0, main_start), 3), round(max(0.0, main_end), 3),
                                  round(max(0.0, cross_start), 3), round(max(0.0, cross_end), 3))
        # a lone child or an evenly spaced run may be centred / end-aligned as a whole: no margins needed
        for justify in ("start", "center", "end"):
            whole = {"dir": direction, "gap": gap, "padding": padding, "justify": justify, "align": "start"}
            candidate = self.fit_cross(whole, board, boxes)
            if candidate:
                return candidate
        layout = {"dir": direction, "gap": gap, "padding": padding, "justify": "start", "align": "start"}
        main_margins = [0.0] + [round(spacing - gap, 3) for spacing in spacings]
        return self.fit_cross(layout, board, boxes, main_margins)

    def fit_cross(self, layout: dict[str, Any], board: Box, boxes: list[Box], main_margins: list[float] | None = None):
        """Per-child cross alignment (container align, else align-self, else a margin), then verify."""
        axes = Axes(layout["dir"])
        sizes = [(box[2], box[3]) for box in boxes]
        main_margins = main_margins or [0.0] * len(boxes)
        props: list[dict[str, Any]] = []
        for i, box in enumerate(boxes):
            base = {"margin": axes.margin(main_margins[i], 0)} if main_margins[i] else {}
            chosen = None
            for align in [None, "start", "center", "end"]:
                trial = {**base, **({"alignSelf": align} if align else {})}
                cross = simulate(layout, board, [sizes[i]], [trial])[0]
                if abs((cross[1] if axes.row else cross[0]) - axes.cross_start(box)) <= TOLERANCE:
                    chosen = trial
                    break
            if chosen is None:                              # start + the exact (possibly negative) margin
                pad_cross_start = axes.padding(four_sides(layout["padding"]))[2]
                cross_margin = round(axes.cross_start(box) - axes.cross_start(board) - pad_cross_start, 3)
                chosen = {"margin": axes.margin(main_margins[i], cross_margin), "alignSelf": "start"}
            props.append(chosen)
        positions = simulate(layout, board, sizes, props)
        if all(abs(x - box[0]) <= TOLERANCE and abs(y - box[1]) <= TOLERANCE for (x, y), box in zip(positions, boxes)):
            return layout, props
        return None

    @staticmethod
    def layer_order(children: list[Node], flow: list[Node], ordered_flow: list[Node]) -> list[Node] | None:
        """Spec order of a flex board = paint order (bottom first) = flow order of its in-flow children:
        the original paint order with the flow items put in flow order in their slots. None when that
        swaps two flow items that overlap (what is painted on top would change)."""
        paint_index = {id(child): i for i, child in enumerate(children)}
        for i, first in enumerate(ordered_flow):
            for second in ordered_flow[i + 1:]:
                if paint_index[id(first)] > paint_index[id(second)] and overlaps(visual_box(first), visual_box(second)):
                    return None
        flow_ids = {id(child) for child in flow}
        sequence = iter(ordered_flow)
        return [next(sequence) if id(child) in flow_ids else child for child in children]


def settle_correction(item: dict[str, Any], measured: list[list[float] | None]) -> dict[str, Any] | None:
    """Flex props that put each flow child of a built board back at its spec x/y, given the sizes Penpot
    gave them (hugging texts are often a pixel wider than in the browser). None when the spec layout
    already does, or a child is gone.

    item: a plugin pin item {board, box, layout, flow: [[id, x, y, w, h, child]]}; measured: [w, h, x, y]
    per flow child. Correction: justify start, the gap shrunk to the smallest real spacing (margins
    never go negative), each child's leading margins exact and align-self start."""
    if not item["flow"] or any(entry is None for entry in measured):
        return None
    layout, board = item["layout"], tuple(item["box"])
    sizes = [(entry[0], entry[1]) for entry in measured]
    targets = [(entry[1], entry[2]) for entry in item["flow"]]
    props = [{key: value for key, value in (entry[5] or {}).items() if key in ("margin", "alignSelf")} for entry in item["flow"]]
    positions = simulate(layout, board, sizes, props)
    if all(abs(x - target[0]) <= TOLERANCE and abs(y - target[1]) <= TOLERANCE for (x, y), target in zip(positions, targets)):
        return None
    axes = Axes(layout.get("dir", "row"))
    pad_main_start, _, pad_cross_start, _ = axes.padding(four_sides(layout.get("padding")))
    boxes = [(x, y, width, height) for (x, y), (width, height) in zip(targets, sizes)]
    spacings = [axes.start(boxes[i]) - axes.start(boxes[i - 1]) - axes.size(boxes[i - 1]) for i in range(1, len(boxes))]
    gap = main_gap(layout)
    if spacings:
        gap = round(min(gap, max(0.0, min(spacings))), 3)
    cursor = axes.start(board) + pad_main_start
    cross_origin = axes.cross_start(board) + pad_cross_start
    children = []
    for (shape_id, *_), box in zip(item["flow"], boxes):
        margin = axes.margin(round(axes.start(box) - cursor, 3), round(axes.cross_start(box) - cross_origin, 3))
        children.append([shape_id, margin, "start"])
        cursor = axes.start(box) + axes.size(box) + gap
    return {"board": item["board"], "layout": {"justify": "start", "gap": gap}, "children": children}


def as_board(group: Node) -> None:
    """A group as a plain board of its own bounds: same look, but its children are built inside it."""
    x, y, width, height = node_box(group) or (0, 0, 0, 0)
    group.update({"t": "board", "x": x, "y": y, "w": width, "h": height, "fill": None, "clip": False})


def layout_errors(nodes: list[Node]) -> list[str]:
    """Flex boards whose flow children Penpot would not place at their spec x/y, or with a group child
    (its children would be flowed before grouping). Empty = all exact."""
    errors: list[str] = []
    for node in nodes:
        layout = node.get("layout")
        if layout:
            errors += [f"{node.get('name')}: group child {child.get('name')}"
                       for child in node.get("children", []) if child.get("t") == "group"]
        if layout and layout.get("type") == "flex":
            flow = [child for child in node.get("children", []) if not (child.get("child") or {}).get("absolute")]
            boxes = [node_box(child) for child in flow]
            props = [{key: value for key, value in (child.get("child") or {}).items() if key in ("margin", "alignSelf")}
                     for child in flow]
            positions = simulate(layout, (node["x"], node["y"], node["w"], node["h"]), [(box[2], box[3]) for box in boxes], props)
            for child, box, (x, y) in zip(flow, boxes, positions):
                if abs(x - box[0]) > TOLERANCE or abs(y - box[1]) > TOLERANCE:
                    errors.append(f"{node.get('name')}: {child.get('name')} at {box[0]:.2f},{box[1]:.2f}, "
                                  f"layout puts it at {x:.2f},{y:.2f}")
        errors += layout_errors(node.get("children", []))
    return errors


def strip_tags(node: Node) -> None:
    """Remove the assembler's private `_` keys (never part of the spec format)."""
    for key in [key for key in node if key.startswith("_")]:
        del node[key]
    for child in node.get("children", []):
        strip_tags(child)
