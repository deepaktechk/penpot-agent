"""Split the page into top-level section boards with semantic names.

Starting at the document roots, "wrapper" elements (full-width containers whose children
are themselves full-width or stacked blocks) are descended into; everything else becomes a
section board named after its biggest heading. Wrapper backgrounds are collected into one
"Page background" board (key `secbg`) underneath all sections.
"""
from __future__ import annotations

from pbridge.convert.context import ConversionContext, Node
from pbridge.convert.naming import slug
from pbridge.convert.tree import TreeAssembler

LANDMARK_TAGS = ("header", "footer", "nav")


class SectionSplitter:
    def __init__(self, ctx: ConversionContext, tree: TreeAssembler):
        self.ctx = ctx
        self.tree = tree
        self.wrapper_own: dict[int, list[Node]] = {}   # wrapper element -> its own nodes (page backgrounds)

    def _visible(self, index: int) -> bool:
        x, y, width, height = self.ctx.by_i[index]["r"]
        return width > 2 and height > 2 and y + height > 0 and x + width > 0 and x < self.ctx.width

    def _is_wrapper(self, index: int, children: list[int]) -> bool:
        page_width = self.ctx.width
        element = self.ctx.by_i[index]

        def rect(child: int) -> list:
            return self.ctx.by_i[child]["r"]

        # stacked blocks at least half the page wide (centred containers count too)
        half_width_children = [child for child in children if rect(child)[2] >= page_width * 0.5 and rect(child)[3] >= 120]
        spans = sorted((rect(child)[1], rect(child)[1] + rect(child)[3]) for child in half_width_children)   # (top, bottom)
        stacked = all(below[0] >= above[1] - 2 for above, below in zip(spans, spans[1:]))
        covered = sum(rect(child)[3] for child in half_width_children)
        wide = [child for child in children if rect(child)[2] >= page_width * 0.85]
        covered_wide = sum(rect(child)[3] for child in wide)
        own_height = element["r"][3]
        return (element["r"][2] >= page_width * 0.85 and element["tag"] not in LANDMARK_TAGS and (
            (len(wide) >= 2 and covered_wide >= 0.6 * own_height)                                  # full-width blocks (may overlap)
            or (len(half_width_children) >= 2 and stacked and covered >= 0.6 * own_height)       # centred containers, stacked
            or (len(children) == 1 and wide)))                                                    # single full-width child

    def _expand(self, indexes: list[int]) -> list[int]:
        """Descend into wrappers; return the elements that become sections."""
        sections = []
        for index in indexes:
            if not self._visible(index):
                continue
            children = [child for child in self.ctx.children.get(index, []) if self._visible(child)]
            if self._is_wrapper(index, children):
                own = self.tree.own_nodes(self.ctx.by_i[index])
                if own:
                    self.wrapper_own[index] = own
                sections += self._expand(children)
            else:
                sections.append(index)
        return sections

    def sections(self) -> list[Node]:
        top_level = self._expand(self.ctx.children.get(-1, []))
        top_level = sorted(top_level, key=lambda index: (self.tree.zkey(index), self.ctx.by_i[index]["i"]))
        boards: list[Node] = []
        if self.wrapper_own:
            backgrounds = [node for nodes in self.wrapper_own.values() for node in nodes]
            boards.append({"t": "board", "key": "secbg", "name": "Page background", "x": 0, "y": 0, "w": self.ctx.width,
                           "h": self.ctx.layout.get("height", 1000), "fill": None, "clip": False, "children": backgrounds})
        for number, index in enumerate(top_level):
            _, y, _, height = self.ctx.by_i[index]["r"]
            nodes = self.tree.assemble(index)
            if not nodes:
                continue
            if nodes and nodes[0].get("t") == "group" and len(nodes) == 1:
                nodes = nodes[0]["children"]      # the board itself is the group
            boards.append({"t": "board", "key": f"sec{number:02d}", "name": self.section_title(index), "x": 0, "y": round(y, 2),
                           "w": self.ctx.width, "h": round(max(height, 1), 2), "fill": None, "clip": False, "children": nodes})
        return boards

    def section_title(self, index: int) -> str:
        """Landmark tag name, else the biggest heading-like text in the subtree (BFS)."""
        element = self.ctx.by_i[index]
        if element["tag"] in LANDMARK_TAGS:
            return element["tag"].capitalize()
        best = None          # (font size, text)
        queue = [index]
        while queue:
            current = self.ctx.by_i[queue.pop(0)]
            if current.get("font") and current.get("lines"):
                size = float(current["font"][1].replace("px", ""))
                if best is None or size > best[0] + 4:
                    best = (size, " ".join(line["t"] for line in current["lines"]))
            queue += self.ctx.children.get(current["i"], [])
        if best:
            return slug(best[1], 40)
        return element.get("htmlId") or element["tag"]
