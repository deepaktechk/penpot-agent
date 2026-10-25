"""Decorations the DOM cannot describe, located in the reference screenshot.

* ::before / ::after boxes with a solid background (e.g. the short rules beside an eyebrow label)
* text-decoration underlines in a color different from the text
"""
from __future__ import annotations

from pbridge.convert.context import ConversionContext, Element, Node
from pbridge.convert.css import paint, parse_color
from pbridge.convert.screenshot import ScreenshotProbe


class DecorationBuilder:
    def __init__(self, ctx: ConversionContext, probe: ScreenshotProbe):
        self.ctx = ctx
        self.probe = probe

    def build(self, element: Element) -> list[Node]:
        return self._pseudo_boxes(element) + self._underlines(element)

    def _pseudo_boxes(self, element: Element) -> list[Node]:
        nodes = []
        x, y, width, height = element["r"]
        for pseudo in element.get("pseudo") or []:
            background = parse_color(pseudo.get("bg"))
            try:
                pseudo_width = float(str(pseudo.get("w")).replace("px", ""))
                pseudo_height = float(str(pseudo.get("h")).replace("px", ""))
            except ValueError:
                continue
            if not background or background[1] < 0.5 or float(pseudo.get("op") or 1) < 0.05 or pseudo_width < 1 or pseudo_height < 0.5:
                continue
            # search a band around the element for a rectangle of the pseudo element's size and color
            search = (x - pseudo_width - 40, y - 4, x + width + pseudo_width + 40, y + height + 4)
            runs = self.probe.locate_color_runs(search, background[0], min_length=max(2, int(pseudo_width * 0.6)))
            candidates = [rect for rect in runs if abs(rect[2] - pseudo_width) <= 3 and abs(rect[3] - pseudo_height) <= 2]
            if not candidates:
                continue
            candidates.sort(key=lambda rect: rect[0])
            rect = candidates[0] if pseudo["pe"] == "::before" else candidates[-1]   # before = leftmost, after = rightmost
            nodes.append({"t": "rect", "x": rect[0], "y": rect[1], "w": rect[2], "h": rect[3], "fill": paint(pseudo["bg"]),
                          "name": f"{element['tag']}{pseudo['pe']}"})
            self.ctx.report["pseudo_located"] += 1
        return nodes

    def _underlines(self, element: Element) -> list[Node]:
        nodes = []
        decoration = element.get("deco")
        if not (decoration and "underline" in decoration.get("line", "") and element.get("lines")):
            return nodes
        line_color = parse_color(decoration.get("color")); text_color = parse_color(element["font"][5])
        if not (line_color and text_color and line_color[0] != text_color[0]):
            return nodes          # same color as the text: Penpot's own underline matches
        for line in element["lines"]:
            line_x, line_y, line_width, line_height = line["r"]
            band = (line_x - 2, line_y + line_height * 0.55, line_x + line_width + 2, line_y + line_height + 8)   # lower half and below
            runs = self.probe.locate_color_runs(band, line_color[0], min_length=int(line_width * 0.5))
            wide_runs = [rect for rect in runs if rect[2] >= line_width * 0.6]
            if wide_runs:
                rect = max(wide_runs, key=lambda run: run[2] * run[3])
                nodes.append({"t": "rect", "x": rect[0], "y": rect[1], "w": rect[2], "h": rect[3], "fill": line_color[0],
                              "name": "underline"})
                self.ctx.report["underlines_located"] += 1
        return nodes
