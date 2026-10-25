"""Inline <svg> elements -> one vector shape plus real text shapes for its <text> nodes.

The capture already baked every SVG to screen space (see js/src/capture/page/svg.ts),
and removed its <text> elements: they are rebuilt here as editable Penpot texts.
"""
from __future__ import annotations

from pbridge.convert.context import ConversionContext, Element, Node
from pbridge.convert.css import paint, parse_px
from pbridge.convert.fonts import FontResolver, css_weight
from pbridge.convert.naming import name_for, slug


class SvgBuilder:
    def __init__(self, ctx: ConversionContext, fonts: FontResolver):
        self.ctx = ctx
        self.fonts = fonts

    def build(self, element: Element) -> list[Node]:
        x, y, width, height = element["r"]
        nodes: list[Node] = [{"t": "svg", "svg": element["svg"], "x": x, "y": y, "w": width, "h": height,
                              "name": name_for(element, "icon"),
                              **({"op": element["op"]} if element.get("op", 1) < 0.999 else {})}]
        for svg_text in element.get("svgTexts", []):
            node = self._text(element, svg_text)
            if node:
                nodes.append(node)
        self.ctx.report["svgs"] += 1
        return nodes

    def _text(self, element: Element, svg_text: dict) -> Node | None:
        family, size, weight, letter_spacing, fill_color, fill_opacity, anchor = svg_text["font"]
        scale = svg_text.get("scale", 1) or 1                       # screen scale of the <text> element
        font_size = round(float(size.replace("px", "")) * scale, 3)
        letter_spacing = f"{parse_px(letter_spacing) * scale}px"
        color = paint(fill_color, float(fill_opacity or 1) * element.get("op", 1))
        lines = [line for line in svg_text["lines"] if line["t"].strip()]
        if not lines:
            return None
        # one text block; line pitch measured from consecutive tspans (avoids per-line drift)
        tops = [line["r"][1] for line in lines]
        pitch = (tops[-1] - tops[0]) / (len(lines) - 1) if len(lines) > 1 else round(font_size * 1.2, 2)
        first_y, first_height = lines[0]["r"][1], lines[0]["r"][3]
        align = {"middle": "center", "end": "right"}.get(anchor, "left")
        left = min(line["r"][0] for line in lines)
        node = {"t": "text", "x": left, "y": round(first_y - (pitch - first_height) / 2, 2), "name": slug(lines[0]["t"]),
                "text": {"text": "\n".join(line["t"] for line in lines), "font": self.fonts.font_name(family), "size": font_size,
                         "weight": css_weight(weight), "lh": round(pitch, 3), "ls": parse_px(letter_spacing), "color": color or "#000000"}}
        if align != "left":
            # fixed-width box centred/right-aligned on the measured lines (+120 px slack)
            right = max(line["r"][0] + line["r"][2] for line in lines); box_width = right - left + 120
            node["x"] = (left + right) / 2 - box_width / 2 if align == "center" else right - box_width
            node["w"] = box_width; node["text"]["align"] = align; node["text"]["grow"] = "auto-height"
        return node
