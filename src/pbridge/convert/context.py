"""Shared state of one conversion run.

Every node builder receives the same `ConversionContext`:
  * the capture (layout.json) indexed by element id and by parent,
  * the conversion options,
  * accumulated outputs: image URLs to upload, the report counters, and the set of text
    elements that were merged into a parent as style ranges (they must not be emitted twice).

Capture element format (produced by js/src/capture/page/elements.ts), main keys:
    i (index), p (nearest emitted ancestor or -1), tag, r [x, y, w, h], op (effective opacity),
    box {bg, bi, bw, bs, bc, radius, shadow, clip, ...}, font [family, size, weight, lineHeight,
    letterSpacing, color, align, transform, style, decoration], lines [{t, r}], src/nat/fit
    (images), svg (sanitized markup), clip (ancestor clip rect), z/pos (stacking).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

Element = dict[str, Any]
Node = dict[str, Any]

DEFAULT_OPTIONS = {"min_section_h": 40, "group": True, "skip_transparent_clicks": True}


class ConversionContext:
    def __init__(self, layout: dict[str, Any], opts: dict[str, Any] | None = None):
        self.layout = layout
        self.opts: dict[str, Any] = {**DEFAULT_OPTIONS, **(opts or {})}
        self.width: float = layout.get("width", 1920)
        self.elements: list[Element] = layout["elements"]
        self.by_i: dict[int, Element] = {element["i"]: element for element in self.elements}
        self.children: dict[int, list[int]] = defaultdict(list)
        for element in self.elements:
            self.children[element.get("p", -1)].append(element["i"])
        self.base_url: str = layout.get("url", "")
        # outputs
        self.images: dict[str, str] = {}          # asset key -> url (uploaded at build time)
        self.report: defaultdict[str, int] = defaultdict(int)
        self.merged: set[int] = set()             # text elements merged into a parent as ranges
        # SVG source loader; replaceable (tests inject a stub instead of the network)
        self.fetch_svg: Callable[[str], str | None] = lambda url: None

    def inline_descendants(self, index: int) -> list[int]:
        """Text-bearing inline descendants of element `index` (they become ranges of its text)."""
        found = []
        for child_index in self.children.get(index, []):
            child = self.by_i[child_index]
            if child.get("disp", "inline").startswith("inline") and child["tag"] not in ("svg", "img"):
                if "font" in child:
                    found.append(child_index)
                found.extend(self.inline_descendants(child_index))
        return found
