"""Font decisions: which Penpot font to use, normalized weights, and per-group metric drift."""
from __future__ import annotations

from collections import defaultdict

from pbridge.convert import fontmetrics
from pbridge.convert.context import ConversionContext

SYSTEM_FONTS = {"-apple-system", "BlinkMacSystemFont", "system-ui", "ui-sans-serif", "Segoe UI", "SF Pro Text",
                "SF Pro Display", "Helvetica Neue", "sans-serif"}


def css_weight(weight: object) -> int:
    """CSS font-weight -> Penpot weight (100..900, rounded to the hundred)."""
    try:
        numeric = int(float(weight))
    except (TypeError, ValueError):
        numeric = 700 if weight == "bold" else 400
    return max(100, min(900, int(round(numeric / 100.0) * 100)))


class FontResolver:
    def __init__(self, ctx: ConversionContext):
        self.ctx = ctx
        self._groups: dict | None = None

    def font_name(self, family: str | None) -> str:
        """Web font family -> Penpot font family.

        Order: explicit --font-map, system stacks -> system_font, generic serif/mono,
        families missing in Penpot -> fallback_font (counted as missing_fonts).
        """
        opts = self.ctx.opts
        font_map = opts.get("font_map", {})
        if family in font_map:
            return font_map[family]
        if not family or family in SYSTEM_FONTS or family.startswith("-"):
            return opts.get("system_font", "Inter")
        if family in ("serif", "ui-serif"):
            return opts.get("serif_font", "Source Serif 4")
        if family in ("monospace", "ui-monospace"):
            return opts.get("mono_font", "Roboto Mono")
        available = opts.get("available_fonts")
        if available is not None and family not in available:
            self.ctx.report.setdefault("missing_fonts", 0); self.ctx.report["missing_fonts"] += 1
            return opts.get("fallback_font", "Inter")
        return family

    weight = staticmethod(css_weight)

    def metric_group(self, family: str, size: float, weight: int, italic: bool) -> float | None:
        """Median relative width deviation (Penpot font vs browser) for one font/size/weight group.

        Measured over single-line plain texts on the page; None if fewer than 3 samples.
        A systematic deviation (e.g. a variable font with optical sizes in the browser vs a
        static font in Penpot) is corrected later by fitting letter-spacing.
        """
        if self._groups is None:
            deviations: defaultdict[tuple, list[float]] = defaultdict(list)
            for element in self.ctx.elements:
                font = element.get("font"); lines = element.get("lines") or []
                # font = [family, size, weight, lineHeight, letterSpacing, color, align, transform, style, ...]
                if not font or len(lines) != 1 or font[4] not in ("normal", "0px") or font[7] not in ("none", None):
                    continue
                line_text, line_width = lines[0]["t"], lines[0]["r"][2]
                if len(line_text) < 6 or line_width < 30 or "\xa0" in (element.get("text") or ""):
                    continue
                font_size = float(font[1].replace("px", "")); font_weight = css_weight(font[2]); is_italic = font[8] == "italic"
                key = (font[0], round(font_size, 1), font_weight, is_italic)
                if len(deviations[key]) >= 25:
                    continue
                penpot_width = fontmetrics.text_width(line_text, self.font_name(font[0]), font_size, font_weight, is_italic)
                if penpot_width:
                    deviations[key].append((penpot_width - line_width) / line_width)
            self._groups = {key: sorted(values)[len(values) // 2] for key, values in deviations.items() if len(values) >= 3}
        return self._groups.get((family, round(size, 1), weight, italic))
