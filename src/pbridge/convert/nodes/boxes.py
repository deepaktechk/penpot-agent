"""Element box -> background / border / shadow / clip-path shapes."""
from __future__ import annotations

from pbridge.assets.urls import key_for
from pbridge.convert.context import ConversionContext, Element, Node
from pbridge.convert.css import (
    paint,
    paint_with_op,
    parse_clip_polygon,
    parse_gradient,
    parse_radius,
    parse_shadows,
    rotation_of,
    split_top,
)
from pbridge.convert.naming import name_for
from pbridge.convert.nodes.urls import resolve_img_url

SIDE_NAMES = ["border-top", "border-right", "border-bottom", "border-left"]


class BoxBuilder:
    def __init__(self, ctx: ConversionContext):
        self.ctx = ctx

    def _background_layers(self, element: Element, fills: list, nodes: list[Node]) -> None:
        """background-image layers (painted bottom-up): gradients -> fills, url() -> image nodes."""
        box = element["box"]; x, y, width, height = element["r"]; opacity = element.get("op", 1)
        for layer in reversed(split_top(box["bi"])):
            if "gradient" in layer:
                gradient = parse_gradient(layer, width, height)
                if gradient:
                    fills.append(gradient); self.ctx.report["gradients"] += 1
            elif layer.startswith("url("):
                url = resolve_img_url(layer[4:-1].strip("\"'"), self.ctx.base_url)
                if url and not url.startswith("data:"):
                    key = key_for(url); self.ctx.images[key] = url
                    background_size = box.get("bsize") or ""
                    fit = "cover" if "cover" in background_size else "contain" if "contain" in background_size else "fill"
                    nodes.append({"t": "image", "img": key, "x": x, "y": y, "w": width, "h": height, "fit": fit,
                                  "name": f"{element['tag']} bg image", "op": opacity if opacity < 0.999 else None})
                    self.ctx.report["bg_images"] += 1

    def build(self, element: Element) -> list[Node]:
        box = element["box"]; x, y, width, height = element["r"]; opacity = element.get("op", 1)
        nodes: list[Node] = []
        fills: list = []
        if box.get("bi"):
            self._background_layers(element, fills, nodes)
        background = paint(box.get("bg"))
        if background:
            fills.insert(0, background)
        fill = None
        if fills:
            fill = fills[0] if len(fills) == 1 else fills
        # borders (top, right, bottom, left): a uniform border becomes a stroke, uneven sides become thin rects
        border_widths = box.get("bw", [0, 0, 0, 0])
        border_styles = box.get("bs", ["none"] * 4)
        border_colors = [paint(color) for color in box.get("bc", [None] * 4)]
        sides = [border_widths[i] if border_styles[i] not in ("none", "hidden") and border_colors[i] else 0 for i in range(4)]
        uniform_border = any(sides) and len(set(sides)) == 1 and len(set(map(str, border_colors))) == 1
        radius = parse_radius(box.get("radius", [0, 0, 0, 0]), width, height)
        shadows = parse_shadows(box.get("shadow"))
        clip_path = parse_clip_polygon(box.get("clip"), x, y, width, height)
        node = None
        if clip_path and fill:
            node = {"t": "path", "d": clip_path, "fill": fill, "name": f"{element['tag']} (clip-path)"}
            self.ctx.report["clip_paths"] += 1
        elif fill or shadows or uniform_border:
            node = {"t": "rect", "x": x, "y": y, "w": width, "h": height, "fill": fill, "name": name_for(element, "box")}
            if radius:
                node["r"] = radius
            if shadows:
                node["sh"] = shadows
            if uniform_border:
                style = "dashed" if border_styles[0] == "dashed" else "dotted" if border_styles[0] == "dotted" else "solid"
                color = border_colors[0]
                node["stroke"] = {"c": color if isinstance(color, str) else color[0], "op": 1 if isinstance(color, str) else color[1],
                                  "w": sides[0], "style": style, "align": "inner"}
                sides = [0, 0, 0, 0]
        if node:
            if opacity < 0.999:
                node["op"] = opacity
            rotation = rotation_of(element.get("tf"))
            if rotation and element.get("os") and node["t"] == "rect":
                # rotated element: r is the rotated bounding box, os the untransformed size
                original_width, original_height = element["os"]; center_x, center_y = x + width / 2, y + height / 2
                node.update({"x": center_x - original_width / 2, "y": center_y - original_height / 2,
                             "w": original_width, "h": original_height, "rot": rotation})
            nodes.insert(0, node)
        side_rects = [(x, y, width, sides[0]), (x + width - sides[1], y, sides[1], height),
                      (x, y + height - sides[2], width, sides[2]), (x, y, sides[3], height)]
        for i, side_width in enumerate(sides):
            if side_width > 0:
                side_x, side_y, rect_width, rect_height = side_rects[i]
                color = border_colors[i]
                nodes.append({"t": "rect", "x": side_x, "y": side_y, "w": rect_width, "h": rect_height,
                              "fill": color if opacity >= 0.999 else paint_with_op(color, opacity), "name": SIDE_NAMES[i]})
        return nodes
