"""Form controls -> their visible value or placeholder as a text shape."""
from __future__ import annotations

from pbridge.convert.context import ConversionContext, Element, Node
from pbridge.convert.css import paint, parse_px
from pbridge.convert.fonts import FontResolver, css_weight
from pbridge.convert.naming import slug


class InputBuilder:
    def __init__(self, ctx: ConversionContext, fonts: FontResolver):
        self.ctx = ctx
        self.fonts = fonts

    def build(self, element: Element) -> list[Node]:
        font = element.get("font")
        control = element.get("input") or {}
        text = control.get("value") or control.get("placeholder")
        if not font or not text:
            return []
        x, y, width, height = element["r"]
        padding = element.get("pad", [0, 0, 0, 0])          # top, right, bottom, left
        font_size = float(font[1].replace("px", ""))
        line_height = float(font[3].replace("px", "")) if font[3].endswith("px") else font_size * 1.2
        color = paint(element.get("phColor") if not control.get("value") else font[5]) or "#757575"
        # single-line inputs centre the text vertically; textareas start at the top padding
        if element["tag"] != "textarea":
            text_y = y + padding[0] + (height - padding[0] - padding[2] - line_height) / 2
        else:
            text_y = y + padding[0]
        return [{"t": "text", "x": x + padding[3], "y": text_y, "name": slug(text),
                 "text": {"text": text, "font": self.fonts.font_name(font[0]), "size": font_size, "weight": css_weight(font[2]),
                          "lh": line_height, "ls": parse_px(font[4]), "color": color}}]
