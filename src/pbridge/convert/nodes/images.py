"""<img> elements -> image shapes or editable SVG vectors.

Decision table for SVG files (`*.svg` src) when vector import is enabled (svg_vector, default on):
  * complex SVG (clipPath/mask/pattern/filter/use/image/text) -> raster image (importer bugs)
  * object-fit: cover with a different aspect               -> clipping board + scaled vector
  * contain / scale-down / fill / same-aspect cover            -> vector (letterboxed for contain)
  * an SVG drawn with fill keeps its aspect (preserveAspectRatio "meet") unless it says "none"
Everything else becomes an image shape with fit cover/contain/fill.
"""
from __future__ import annotations

import re

from pbridge.assets.urls import is_svg, key_for
from pbridge.convert.context import ConversionContext, Element, Node
from pbridge.convert.css import parse_number, parse_radius
from pbridge.convert.naming import slug
from pbridge.convert.nodes.urls import resolve_img_url
from pbridge.convert.svg_source import COMPLEX_SVG_RE


def _object_position(object_position: str | None) -> list[float] | None:
    """'30% 50%' -> [0.3, 0.5]; keywords fall back to centre; None if not two tokens."""
    if not object_position:
        return None
    tokens = object_position.split()
    if len(tokens) != 2:
        return None
    try:
        return [parse_number(token, 1) if token.endswith("%") else 0.5 for token in tokens]
    except ValueError:
        return None


class ImageBuilder:
    def __init__(self, ctx: ConversionContext):
        self.ctx = ctx

    def _name(self, element: Element, url: str) -> str:
        return slug(element.get("alt") or url.split("/")[-1], 40)

    def _with_opacity(self, element: Element, node: Node) -> Node:
        if element.get("op", 1) < 0.999:
            node["op"] = element["op"]
        return node

    def build(self, element: Element) -> list[Node]:
        box = element.get("cbox") or element["r"]     # replaced content paints in the content box
        url = resolve_img_url(element.get("src"), self.ctx.base_url)
        if not url:
            return []
        if url.startswith("data:"):
            self.ctx.report["data_url_images_skipped"] += 1
            return []
        key = key_for(url); self.ctx.images[key] = url
        vector_on = self.ctx.opts.get("svg_vector", True)
        fit = element.get("fit") or "fill"
        if is_svg(url) and fit in ("fill", "none", None):
            # an SVG drawn by <img> keeps its own aspect (preserveAspectRatio "meet") unless it opts out
            svg_markup = self.ctx.fetch_svg(url) if vector_on else None
            if not (svg_markup and re.search(r'preserveAspectRatio\s*=\s*["\']none', svg_markup)):
                fit = "contain"
        position = _object_position(element.get("opos"))
        natural = element.get("nat") or [0, 0]            # intrinsic image size [width, height]
        width, height = box[2], box[3]
        same_aspect = natural[0] and natural[1] and \
            abs((natural[0] / natural[1]) - (width / max(height, 1e-6))) < 0.01 * (natural[0] / natural[1])
        svg_file = is_svg(url)
        if svg_file and vector_on:
            svg_markup = self.ctx.fetch_svg(url)
            if svg_markup is None or COMPLEX_SVG_RE.search(svg_markup):
                self.ctx.report["complex_svgs_rasterized"] += 1
                svg_file = False      # Penpot's SVG importer mishandles these -> faithful raster
        if svg_file and vector_on and fit == "cover" and not same_aspect and natural[0] and natural[1]:
            node = self._cover_vector(element, url, box, natural)
            if node:
                return [node]
        vector_ok = fit in ("contain", "scale-down") or fit in ("fill", None) or (fit == "cover" and same_aspect)
        if vector_on and svg_file and vector_ok:
            node = self._vector(element, url, box, fit)
            if node:
                return [node]
        return [self._raster(element, url, key, box, fit, position)]

    def _cover_vector(self, element: Element, url: str, box, natural) -> Node | None:
        """object-fit: cover for vectors = clipping board + scaled svg."""
        svg_markup = self.ctx.fetch_svg(url)
        if not svg_markup:
            return None
        x, y, width, height = box
        scale = max(width / natural[0], height / natural[1])
        scaled_width, scaled_height = natural[0] * scale, natural[1] * scale
        align_x, align_y = 0.5, 0.5          # object-position as fractions (default centre)
        tokens = (element.get("opos") or "50% 50%").split()
        try:   # both or neither: a bad second token keeps the centre for both axes
            align_x, align_y = ((parse_number(tokens[0], 1) if tokens[0].endswith("%") else 0.5),
                                (parse_number(tokens[1], 1) if len(tokens) > 1 and tokens[1].endswith("%") else 0.5))
        except ValueError:
            pass
        self.ctx.report["svg_images_as_vectors"] += 1
        inner = {"t": "svg", "svg": svg_markup, "x": round(x + (width - scaled_width) * align_x, 2),
                 "y": round(y + (height - scaled_height) * align_y, 2),
                 "w": round(scaled_width, 2), "h": round(scaled_height, 2), "name": self._name(element, url)}
        node = {"t": "board", "x": x, "y": y, "w": width, "h": height, "clip": True, "fill": None, "name": "cover " + inner["name"],
                "children": [inner]}
        return self._with_opacity(element, node)

    def _vector(self, element: Element, url: str, box, fit) -> Node | None:
        svg_markup = self.ctx.fetch_svg(url)
        if not svg_markup:
            return None
        x, y, width, height = box
        natural_width, natural_height = element.get("nat") or [width, height]
        if fit == "contain" and natural_width and natural_height:     # letterbox inside the element box
            scale = min(width / natural_width, height / natural_height)
            drawn_width, drawn_height = natural_width * scale, natural_height * scale
            drawn = (x + (width - drawn_width) / 2, y + (height - drawn_height) / 2, drawn_width, drawn_height)
        else:
            drawn = (x, y, width, height)
        self.ctx.report["svg_images_as_vectors"] += 1
        node = {"t": "svg", "svg": svg_markup, "x": round(drawn[0], 2), "y": round(drawn[1], 2),
                "w": round(drawn[2], 2), "h": round(drawn[3], 2), "name": self._name(element, url)}
        return self._with_opacity(element, node)

    def _raster(self, element: Element, url: str, key: str, box, fit, position) -> Node:
        x, y, width, height = box
        node = {"t": "image", "img": key, "x": x, "y": y, "w": width, "h": height,
                "fit": fit if fit in ("cover", "contain") else "fill", "name": self._name(element, url)}
        if position and position != [0.5, 0.5]:
            node["pos"] = position
        if element.get("nat") and all(element["nat"]):
            node["nat"] = element["nat"]
        radius = parse_radius([element.get("radius") or "0"] * 4, width, height) if element.get("radius") else None
        if radius:
            node["r"] = radius
        self._with_opacity(element, node)
        if element.get("clip"):
            node = self.clip_wrap(node, element["clip"])
        self.ctx.report["images"] += 1
        return node

    def clip_wrap(self, node: Node, clip) -> Node:
        """Wrap a node in a clipping board when an overflow ancestor cuts it."""
        clip_x, clip_y, clip_width, clip_height = clip
        x, y, width, height = node["x"], node["y"], node["w"], node["h"]
        inside = (x >= clip_x - 0.5 and y >= clip_y - 0.5
                  and x + width <= clip_x + clip_width + 0.5 and y + height <= clip_y + clip_height + 0.5)
        if inside:
            return node
        self.ctx.report["clipped"] += 1
        return {"t": "board", "x": clip_x, "y": clip_y, "w": clip_width, "h": clip_height, "clip": True, "fill": None,
                "name": "clip", "children": [node]}
