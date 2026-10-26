"""DOM subtree -> nested spec nodes that mirror the page structure.

* each element contributes its "own" shapes (box, image, svg, input, text, decorations),
* children follow in DOM order, positioned elements sorted by z-index,
* meaningful containers (boxes, links, buttons, list items, sections...) become groups, so the
  Penpot layer tree reads like the page.
* with `layout: auto`, nodes carry private tags for convert/layout.py (container box and CSS,
  own paint, out of flow); the layout pass turns groups into flex boards and removes the tags.
"""
from __future__ import annotations

from pbridge.convert.context import ConversionContext, Element, Node
from pbridge.convert.naming import name_for, slug
from pbridge.convert.nodes.boxes import BoxBuilder
from pbridge.convert.nodes.decorations import DecorationBuilder
from pbridge.convert.nodes.images import ImageBuilder
from pbridge.convert.nodes.inputs import InputBuilder
from pbridge.convert.nodes.svg import SvgBuilder
from pbridge.convert.nodes.text import TextBuilder

FORM_TAGS = ("input", "textarea", "select")
GROUPING_TAGS = ("a", "button", "li", "article", "form", "figure", "nav", "header", "footer", "section", "ul", "ol", "label")


class TreeAssembler:
    def __init__(self, ctx: ConversionContext, boxes: BoxBuilder, images: ImageBuilder, svgs: SvgBuilder,
                 inputs: InputBuilder, texts: TextBuilder, decorations: DecorationBuilder):
        self.ctx = ctx
        self.boxes, self.images, self.svgs, self.inputs, self.texts, self.decorations = boxes, images, svgs, inputs, texts, decorations

    def own_nodes(self, element: Element) -> list[Node]:
        """Shapes painted by the element itself (not by its children)."""
        nodes: list[Node] = []
        if element.get("box"):
            nodes += self.boxes.build(element)
        tag = element["tag"]
        if tag == "img":
            nodes += self.images.build(element)
        elif tag == "svg" and element.get("svg"):
            nodes += self.svgs.build(element)
        elif tag in FORM_TAGS:
            nodes += self.inputs.build(element)
        if element.get("font") and element.get("lines") and element["i"] not in self.ctx.merged and tag not in FORM_TAGS:
            nodes += self.texts.build(element)
        if element.get("clip") and nodes and tag != "img":
            # partially clipped by an overflow ancestor (e.g. carousel slides): clip to that rect
            clip_x, clip_y, clip_width, clip_height = element["clip"]
            x, y, width, height = element["r"]
            visible_width = min(x + width, clip_x + clip_width) - max(x, clip_x)
            visible_height = min(y + height, clip_y + clip_height) - max(y, clip_y)
            if visible_width < 2 or visible_height < 2:      # (almost) entirely clipped away
                return []
            nodes = [{"t": "board", "x": round(clip_x, 2), "y": round(clip_y, 2), "w": round(clip_width, 2),
                      "h": round(clip_height, 2), "clip": True, "fill": None, "name": "clip", "children": nodes}]
            self.ctx.report["clipped"] += 1
        if self.decorations.probe.available:
            nodes += self.decorations.build(element)
            for child_index in self.ctx.inline_descendants(element["i"]):
                if child_index in self.ctx.merged:   # underlines etc. of spans merged into this text
                    nodes += self.decorations.build(self.ctx.by_i[child_index])
        elif element.get("pseudo"):
            self.ctx.report["pseudo_elements_unhandled"] += len(element["pseudo"])
        return nodes

    def zkey(self, index: int) -> int:
        """Stacking order key: z-index for positioned elements, 0 otherwise."""
        element = self.ctx.by_i[index]
        return element.get("z", 0) if element.get("pos") in ("absolute", "fixed", "relative", "sticky") else 0

    def assemble(self, index: int, depth: int = 0) -> list[Node]:
        """Nodes for element `index` and its subtree (DOM order, z-aware)."""
        element = self.ctx.by_i[index]
        own = self.own_nodes(element)
        children = sorted(self.ctx.children.get(index, []),
                          key=lambda child_index: (self.zkey(child_index), self.ctx.by_i[child_index]["i"]))
        auto_layout = self.ctx.opts.get("layout") == "auto"
        descendants: list[Node] = []
        for child_index in children:
            if child_index in self.ctx.merged:
                continue
            child_nodes = self.assemble(child_index, depth + 1)
            if auto_layout and self.ctx.by_i[child_index].get("pos") in ("absolute", "fixed"):
                for node in child_nodes:
                    node["_oof"] = True            # out of flow: an absolute child of any layout
            descendants += child_nodes
        all_nodes = own + descendants
        if self.ctx.opts["group"] and len(all_nodes) >= 2 and len(descendants) >= 1 and element["tag"] not in ("svg",):
            meaningful = element.get("box") or element["tag"] in GROUPING_TAGS or len(descendants) >= 3
            if auto_layout and element.get("lay") and len(descendants) >= 2:
                meaningful = True                  # keep flex containers: they are what auto layout encodes
            if meaningful:
                group: Node = {"t": "group", "name": self.group_name(element, all_nodes), "children": all_nodes}
                if auto_layout:
                    group["_rect"] = list(element["r"])
                    if element.get("lay"):
                        group["_lay"] = element["lay"]
                    for node in own:
                        if node.get("t") != "text":
                            node["_own"] = True    # background, border, shadow: painted below the flow
                return [group]
        return all_nodes

    @staticmethod
    def group_name(element: Element, nodes: list[Node]) -> str:
        """'tag: first text' so groups are recognisable in the layer panel."""
        for node in nodes:
            if node.get("t") == "text":
                return f"{element['tag']}: {slug(node['text']['text'].splitlines()[0], 28)}"
            if node.get("t") == "group" and ":" in node.get("name", ""):
                return f"{element['tag']}: {node['name'].split(':', 1)[1].strip()}"
        return name_for(element, "group")
