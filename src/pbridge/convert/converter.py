"""Converter facade: capture layout.json -> spec {nodes: [section boards], images, report}.

Wires the single-purpose parts together:

    ConversionContext  shared capture index, options, outputs
    FontResolver       web font -> Penpot font, metric drift per group
    ScreenshotProbe    pixel evidence from the reference screenshot
    *Builder           element -> shapes (boxes, images, svg, inputs, text, decorations)
    TreeAssembler      DOM subtree -> nested groups
    SectionSplitter    page -> section boards

Options (opts): fallback_font, system_font, serif_font, mono_font, font_map {web: penpot},
available_fonts (set; families outside it use fallback_font), screenshot (path),
group (default True), svg_vector (default True), metric_fit (default True), snap (default True).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pbridge.convert.context import ConversionContext, Node
from pbridge.convert.fonts import FontResolver, css_weight
from pbridge.convert.nodes.boxes import BoxBuilder
from pbridge.convert.nodes.decorations import DecorationBuilder
from pbridge.convert.nodes.images import ImageBuilder
from pbridge.convert.nodes.inputs import InputBuilder
from pbridge.convert.nodes.svg import SvgBuilder
from pbridge.convert.nodes.text import TextBuilder
from pbridge.convert.screenshot import ScreenshotProbe
from pbridge.convert.sections import SectionSplitter
from pbridge.convert.svg_source import fetch_svg
from pbridge.convert.tree import TreeAssembler

SPEC_VERSION = 1


class Converter:
    def __init__(self, layout: dict[str, Any], opts: dict[str, Any] | None = None):
        self.ctx = ctx = ConversionContext(layout, opts)
        ctx.fetch_svg = fetch_svg
        self.fonts = FontResolver(ctx)
        self.probe = ScreenshotProbe(ctx, ctx.opts.get("screenshot"))
        self.tree = TreeAssembler(ctx, BoxBuilder(ctx), ImageBuilder(ctx), SvgBuilder(ctx, self.fonts),
                                  InputBuilder(ctx, self.fonts), TextBuilder(ctx, self.fonts, self.probe),
                                  DecorationBuilder(ctx, self.probe))
        self.sectioner = SectionSplitter(ctx, self.tree)

    # SVG loader hook: tests replace it to avoid the network (converter.fetch_svg = lambda url: "<svg/>")
    @property
    def fetch_svg(self) -> Callable[[str], str | None]:
        return self.ctx.fetch_svg

    @fetch_svg.setter
    def fetch_svg(self, loader: Callable[[str], str | None]) -> None:
        self.ctx.fetch_svg = loader

    weight = staticmethod(css_weight)

    @property
    def images(self) -> dict[str, str]:
        return self.ctx.images

    @property
    def report(self):
        return self.ctx.report

    @staticmethod
    def snap(nodes: list[Node]) -> None:
        """Browsers paint backgrounds/borders on whole device pixels: round rect/ellipse boxes."""
        for node in nodes:
            if node.get("t") in ("rect", "ellipse") and all(key in node for key in ("x", "y", "w", "h")) and not node.get("rot"):
                left, top = round(node["x"]), round(node["y"])
                right, bottom = round(node["x"] + node["w"]), round(node["y"] + node["h"])
                if right - left >= 1 and bottom - top >= 1:
                    node["x"], node["y"], node["w"], node["h"] = left, top, right - left, bottom - top
            if node.get("children"):
                Converter.snap(node["children"])

    def convert(self, top: float | None = None, bottom: float | None = None) -> dict[str, Any]:
        """Convert the whole page, or only the sections overlapping [top, bottom]."""
        boards = self.sectioner.sections()
        if self.ctx.opts.get("snap", True):
            self.snap(boards)
        if top is not None or bottom is not None:
            low, high = top or -1e9, bottom or 1e9
            boards = [board for board in boards if board["y"] < high and board["y"] + board["h"] > low]
        return {"version": SPEC_VERSION, "source": self.ctx.layout.get("url"), "width": self.ctx.width,
                "height": self.ctx.layout.get("height"), "images": self.ctx.images, "report": dict(self.ctx.report),
                "nodes": boards}


def count_nodes(nodes: list[Node]) -> int:
    """Number of nodes in a spec tree."""
    return sum(1 + count_nodes(node.get("children", [])) for node in nodes)
