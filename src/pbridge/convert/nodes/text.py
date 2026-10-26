"""Text elements -> Penpot text shapes that reproduce the browser's line breaks exactly.

Pipeline for one element (each step is a method below, applied in this order):
  1. drop lines that overflow both the element and its parent (hidden overflow)
  2. skip screen-reader-only text (1px boxes, clip-path: inset(50%))
  3. truncation: line-clamp / text-overflow: ellipsis (single "…", never doubled)
  4. drop lines the screenshot shows no ink for, and lines outside the ancestor clip rect
  5. geometry: the text box is anchored on the first line's glyph box,
     y = glyphTop - (lineHeight - glyphHeight) / 2, so Penpot's line height matches CSS
  6. metric fitting: when Penpot's font is wider/narrower than the browser's (substituted font,
     or a same-name font with different metrics) fit letter-spacing so the widest line matches
  7. style: font, size, weight, colors, transform, decoration, gradient text
  8. inline children (spans, links, strong...) become style ranges of this text

Capture font list (element["font"]): [family, size, weight, lineHeight, letterSpacing, color,
align, transform, style, decoration]. Capture lines: [{"t": text, "r": [x, y, w, h]}].
"""
from __future__ import annotations

import math
import re

from pbridge.convert import fontmetrics
from pbridge.convert.context import ConversionContext, Element, Node
from pbridge.convert.css import gradient_char_ranges, paint, parse_gradient, parse_px, split_top, uniform_scale_of
from pbridge.convert.fonts import FontResolver, css_weight
from pbridge.convert.naming import slug
from pbridge.convert.screenshot import ScreenshotProbe

ALIGN = {"center": "center", "right": "right", "end": "right", "justify": "left"}
BOX_SLACK = 120   # extra width given to centred/right multi-line boxes so Penpot never re-wraps


class TextBuilder:
    def __init__(self, ctx: ConversionContext, fonts: FontResolver, probe: ScreenshotProbe):
        self.ctx = ctx
        self.fonts = fonts
        self.probe = probe

    # ------------------------------------------------------------------ steps 1-4: which lines
    def _drop_overflow(self, element: Element, lines: list[dict]) -> tuple[Element, list[dict]]:
        """Lines overflowing both the element and its parent box are (almost always) hidden."""
        parent = self.ctx.by_i.get(element.get("p", -1))

        def outside(line_rect, box):
            center_y = line_rect[1] + line_rect[3] / 2
            return center_y < box[1] - 1 or center_y > box[1] + box[3] + 1

        if parent and len(lines) > 1:
            kept = [line for line in lines if not (outside(line["r"], element["r"]) and outside(line["r"], parent["r"]))]
            if len(kept) < len(lines):
                self.ctx.report["overflow_lines_dropped"] += len(lines) - len(kept)
                if element.get("tov") == "ellipsis" or element.get("lc") or len(kept) < len(lines):
                    element = dict(element, ovh=1)    # behaves like overflow: hidden from here on
            lines = kept or lines[:1]
        return element, lines

    @staticmethod
    def _is_screen_reader_only(element: Element) -> bool:
        _, _, width, height = element["r"]
        return (width <= 1.5 or height <= 1.5) or "inset(50%)" in str((element.get("box") or {}).get("clip"))

    def _truncate(self, element: Element, lines: list[dict], font_size: float) -> tuple[list[str], list[dict]]:
        """Apply line-clamp / own overflow clipping; add one ellipsis where the browser shows it."""
        clamp = element.get("lc") or element.get("clamp") or 0
        _, box_y, box_width, box_height = element["r"]
        if element.get("visible"):               # single-line ellipsis already measured in the browser
            return [re.sub(r"\s+", " ", element["visible"]).strip()], lines[:1]
        texts = [line["t"] for line in lines]
        cut = len(lines)
        if clamp and len(lines) > clamp:
            cut = clamp
        if element.get("ovh"):   # own overflow clipping: keep lines whose glyph box starts inside
            inside = [i for i, line in enumerate(lines) if line["r"][1] < box_y + box_height - 2]
            cut = min(cut, len(inside) or 1)
        if cut < len(lines):
            texts, lines = texts[:cut], lines[:cut]
            if clamp or element.get("tov") == "ellipsis":
                last = texts[-1].rstrip()
                last_width = lines[-1]["r"][2]
                average_glyph = last_width / max(1, len(last))          # average glyph width of the last line
                ellipsis_width = 0.6 * font_size                        # approximate width of "…"
                horizontal_padding = sum((element.get("pad") or [0, 0, 0, 0])[1::2])
                overflow = last_width + ellipsis_width - (box_width - horizontal_padding)
                if overflow > 0:
                    last = last[: max(0, len(last) - int(math.ceil(overflow / max(average_glyph, 1e-3))))].rstrip()
                texts[-1] = last if re.search(r"(\.\.\.|…)\s*$", last) else last + "…"
            self.ctx.report["truncated_text"] += 1
        return texts, lines

    def _keep_inked(self, texts: list[str], lines: list[dict]) -> tuple[list[str], list[dict]]:
        """Visual ground truth (after clamping, so truncation saw every line)."""
        if len(lines) <= 1:
            return texts, lines
        if self.probe.gray is not None:
            keep = [i for i, line in enumerate(lines) if self.probe.line_has_ink(line["r"])]
        else:
            keep = [i for i, line in enumerate(lines) if not line.get("hid")]
        keep = keep or [0]
        return [texts[i] for i in keep], [lines[i] for i in keep]

    @staticmethod
    def _keep_inside_clip(element: Element, texts: list[str], lines: list[dict]) -> tuple[list[str], list[dict]] | None:
        """Drop lines outside the effective (ancestor) clip rect; None if nothing is left."""
        clip = element.get("tclip") or element.get("clip")
        if not clip:
            return texts, lines
        _, clip_y, _, clip_height = clip
        keep = [i for i, line in enumerate(lines)
                if line["r"][1] + line["r"][3] > clip_y + 0.5 and line["r"][1] < clip_y + clip_height - 0.5]
        if not keep:
            return None
        return [texts[i] for i in keep], [lines[i] for i in keep]

    # ------------------------------------------------------------------ step 5-6: geometry
    @staticmethod
    def _box(lines: list[dict], align: str) -> tuple[float, float, str, str, float, float]:
        """-> (x, width, align used, grow type, left, right) of the text box."""
        left = min(line["r"][0] for line in lines); right = max(line["r"][0] + line["r"][2] for line in lines)
        if align == "left" or len(lines) == 1:
            return left, right - left, "left", "auto-width", left, right
        box_width = (right - left) + BOX_SLACK
        if align == "center":
            centers = [line["r"][0] + line["r"][2] / 2 for line in lines]; mean_center = sum(centers) / len(centers)
            return mean_center - box_width / 2, box_width, "center", "auto-height", left, right
        return right - box_width, box_width, "right", "auto-height", left, right

    def _fit_letter_spacing(self, lines: list[dict], family: str, penpot_font: str, font_size: float, weight, italic: bool,
                            letter_spacing: float, upper: bool) -> float:
        """Verify against Penpot's real font metrics.

        Substituted fonts are always fitted; same-name fonts only when the WHOLE
        (font, size, weight) group deviates systematically (e.g. variable optical sizes).
        Single-line quirks (nbsp, inline spans) must not trigger a fit.
        """
        widest = max(lines, key=lambda line: line["r"][2])
        browser_width = widest["r"][2]
        if fontmetrics.covers(widest["t"], penpot_font, css_weight(weight), italic) is False:
            # Penpot draws the missing characters with a fallback font, so the width measured
            # here is meaningless: a fit would squeeze or stretch the whole line
            self.ctx.report["fit_skipped_missing_glyphs"] += 1
            return letter_spacing
        penpot_width = fontmetrics.text_width(widest["t"], penpot_font, font_size, css_weight(weight), italic, letter_spacing, upper)
        want_fit = False
        if penpot_width and browser_width > 20:
            if penpot_font != family:
                want_fit = True
            else:
                group_deviation = self.fonts.metric_group(family, font_size, css_weight(weight), italic)
                deviation = (penpot_width - browser_width) / browser_width
                want_fit = group_deviation is not None and abs(group_deviation) > 0.004 and abs(deviation - group_deviation) < 0.02
        if want_fit:
            fitted = fontmetrics.fit_letter_spacing([widest["t"]], browser_width, penpot_font, font_size, css_weight(weight),
                                                    italic, letter_spacing, upper)
            if fitted is not None and abs(fitted - letter_spacing) < 3:
                self.ctx.report["font_substituted_texts" if penpot_font != family else "metric_fitted_texts"] += 1
                return fitted
        return letter_spacing

    # ------------------------------------------------------------------ main entry
    def build(self, element: Element) -> list[Node]:
        family, size, weight, line_height_css, letter_spacing_css, color, align_css, transform, style, decoration = \
            (element["font"] + [None] * 10)[:10]
        font_size = float(size.replace("px", ""))
        if line_height_css and line_height_css.endswith("px"):
            line_height = float(line_height_css.replace("px", ""))
        else:
            line_height = round(font_size * 1.2, 2)
        # a scale transform (floating form labels) draws the text smaller than its computed font;
        # the captured line boxes are already in screen space, only the metrics need scaling
        scale = uniform_scale_of(element.get("tf"))
        font_size, line_height = round(font_size * scale, 3), round(line_height * scale, 3)
        element, lines = self._drop_overflow(element, list(element.get("lines") or []))
        if not lines:
            return []
        if self._is_screen_reader_only(element):
            self.ctx.report["sr_only_skipped"] += 1
            return []
        texts, lines = self._truncate(element, lines, font_size)
        texts, lines = self._keep_inked(texts, lines)
        clipped = self._keep_inside_clip(element, texts, lines)
        if clipped is None:
            return []
        texts, lines = clipped
        text = "\n".join(texts)
        first = lines[0]["r"]
        y = first[1] - (line_height - first[3]) / 2          # anchor the line box on the first glyph box
        align = ALIGN.get(align_css, "left")
        if element.get("tf") and "matrix" in element["tf"]:
            self.ctx.report["transformed_text"] += 1
        node_x, node_width, align_used, grow, left, right = self._box(lines, align)
        text_color = paint(color, element.get("op", 1))
        penpot_font = self.fonts.font_name(family)
        letter_spacing = parse_px(letter_spacing_css) * scale
        upper = transform == "uppercase"
        italic = style == "italic"
        if not element.get("visible") and self.ctx.opts.get("metric_fit", True):
            letter_spacing = self._fit_letter_spacing(lines, family, penpot_font, font_size, weight, italic, letter_spacing, upper)
        if len(lines) == 1 and align in ("center", "right"):
            # single line: anchor exactly using the measured Penpot width (auto-width, no box)
            penpot_width = fontmetrics.text_width(texts[0], penpot_font, font_size, css_weight(weight), italic, letter_spacing, upper)
            if fontmetrics.covers(texts[0], penpot_font, css_weight(weight), italic) is False:
                # the width is unknown (Penpot draws missing glyphs with a fallback font):
                # let Penpot align the line inside a wide box around the browser's line box
                line_x, _, line_width, _ = lines[0]["r"]
                node_width = line_width + BOX_SLACK
                node_x = line_x - BOX_SLACK / 2 if align == "center" else line_x + line_width - node_width
                align_used, grow = align, "auto-height"
            elif penpot_width:
                line_x, _, line_width, _ = lines[0]["r"]
                node_x = line_x + line_width / 2 - penpot_width / 2 if align == "center" else line_x + line_width - penpot_width
                align_used, grow, node_width = "left", "auto-width", penpot_width
        text_spec = self._style(element, text, penpot_font, font_size, weight, line_height, letter_spacing, text_color,
                                align_used, grow, italic, decoration, transform, right - left)
        self.ctx.report["texts"] += 1
        return [{"t": "text", "x": round(node_x, 2), "y": round(y, 2), "w": round(node_width, 2),
                 "h": round(line_height * len(texts), 2), "name": slug(texts[0]), "text": text_spec}]

    # ------------------------------------------------------------------ step 7-8: style + ranges
    def _style(self, element: Element, text: str, penpot_font: str, font_size: float, weight, line_height: float,
               letter_spacing: float, color, align_used: str, grow: str, italic: bool, decoration, transform,
               lines_width: float) -> dict:
        text_spec = {"text": text, "font": penpot_font, "size": font_size, "weight": css_weight(weight), "lh": line_height,
                     "ls": letter_spacing, "color": color or "#000000", "align": align_used, "grow": grow}
        if italic:
            text_spec["italic"] = True
        if decoration and decoration not in ("none",):
            text_spec["deco"] = "underline" if "underline" in decoration else "line-through" if "line-through" in decoration else None
        if element.get("textGradient"):
            css_gradient = element["textGradient"]
            first_layer = css_gradient.split("),")[0] + (")" if not css_gradient.endswith(")") else "")
            gradient = parse_gradient(first_layer, lines_width, line_height)
            if gradient:
                text_spec["color"] = gradient; self.ctx.report["text_gradients"] += 1
        # line text comes from DOM text nodes (untransformed): let Penpot apply text-transform
        if transform == "uppercase":
            text_spec["upper"] = True
        elif transform == "lowercase":
            text_spec["lower"] = True
        elif transform == "capitalize":
            text_spec["cap"] = True
        ranges = self.inline_ranges(element, text, text_spec)
        if isinstance(text_spec["color"], dict):        # whole-text gradient -> per-character colors
            ranges = gradient_char_ranges(0, len(text), text_spec["color"], text) + ranges
            stops = text_spec["color"]["g"][4]
            text_spec["color"] = stops[0][0] if stops else "#000000"
        ranges = self._expand_gradient_ranges(ranges, text)
        if ranges:
            text_spec["ranges"] = ranges
        return text_spec

    @staticmethod
    def _expand_gradient_ranges(ranges: list[list], text: str) -> list[list]:
        """A range with a gradient color -> its other styles + one solid color per character."""
        expanded = []
        for start, end, style in ranges:
            if isinstance(style.get("color"), dict):
                other_styles = {key: value for key, value in style.items() if key != "color"}
                if other_styles:
                    expanded.append([start, end, other_styles])
                expanded += gradient_char_ranges(start, end, style["color"], text)
            else:
                expanded.append([start, end, style])
        return expanded

    def inline_ranges(self, element: Element, text: str, base: dict) -> list[list]:
        """Merge inline descendant text elements as style ranges [start, end, style] of `element`."""
        ranges = []
        search_from = 0
        flat = text.replace("\n", " ")
        for child_index in self.ctx.inline_descendants(element["i"]):
            child = self.ctx.by_i[child_index]
            if "font" not in child or "lines" not in child:
                continue
            child_text = " ".join(line["t"] for line in child["lines"]).strip()
            if not child_text:
                continue
            start = flat.find(child_text, search_from)          # search after the previous match first
            if start < 0:
                start = flat.find(child_text)
            if start < 0:
                continue
            search_from = start + len(child_text)
            self.ctx.merged.add(child_index)            # the child must not be emitted as its own text
            style = self._range_style(child, base)
            if style:
                ranges.append([start, start + len(child_text), style])
        return ranges

    def _range_style(self, child: Element, base: dict) -> dict:
        """Style differences between an inline child and the parent text."""
        font = child["font"]
        style: dict = {}
        color = paint(font[5], child.get("op", 1))
        if color and color != base["color"]:
            style["color"] = color
        if child.get("textGradient"):
            css_gradient = child["textGradient"]
            gradient = parse_gradient(split_top(css_gradient)[0] if "," in css_gradient else css_gradient, child["r"][2], child["r"][3])
            if gradient:
                style["color"] = gradient
        weight = css_weight(font[2])
        if weight != base["weight"]:
            style["weight"] = weight
        family = self.fonts.font_name(font[0])
        if family != base["font"]:
            style["font"] = family
            style.setdefault("weight", weight)
        font_size = float(font[1].replace("px", ""))
        if abs(font_size - base["size"]) > 0.01:
            style["size"] = font_size
            line_height_css = font[3]
            style["lh"] = float(line_height_css.replace("px", "")) if line_height_css.endswith("px") else font_size * 1.2
        if len(font) > 9 and font[9] and font[9] != "none" and not base.get("deco"):
            style["deco"] = "underline" if "underline" in font[9] else "line-through"
        if font[8] == "italic" and not base.get("italic"):
            style["italic"] = True; style.setdefault("weight", weight)
        return style
