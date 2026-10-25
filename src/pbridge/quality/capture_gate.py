"""Capture gate: refuse references that would poison every later step.

Checks the evidence recorded by the capture (layout.quality) and the screenshot:
  * text painted with a fallback font instead of the web font (canvas width check)
  * page never became still (carousels / animations mid-transition)
  * broken or still-lazy images
  * screenshot height != layout height, blank screenshot, almost no elements (consent wall)
"""
from __future__ import annotations

from pathlib import Path

from pbridge.quality.result import GateResult, fail, new_result, thresholds


def capture_gate(layout: dict, shot_path: str | Path, overrides: dict | None = None) -> GateResult:
    limits = thresholds(overrides)
    result = new_result()
    quality = layout.get("quality") or {}
    for family, font_stats in (quality.get("fontRender") or {}).items():
        result["info"][f"font:{family}"] = font_stats
        if font_stats.get("samples", 0) >= 5 and font_stats.get("medianDev", 0) > limits["font_dev_error"]:
            fail(result, f"text was painted with a fallback font instead of '{family}' (median width deviation "
                         f"{font_stats['medianDev'] * 100:.1f}%). Recapture (warm-up) or check the font loads.")
        elif not font_stats.get("loaded", True):
            result["warnings"].append(f"font '{family}' not reported loaded by document.fonts")
    stable_samples = quality.get("stableSamples")
    if quality.get("freeze") and stable_samples is not None and stable_samples < limits["min_stable_samples"]:
        result["warnings"].append(f"page never became still (stable samples {stable_samples}): carousels/animations "
                                  "may be captured mid-transition")
    for url in quality.get("brokenImages") or []:
        fail(result, f"image failed to load: {url}")
    if quality.get("lazyPending"):
        result["warnings"].append(f"{quality['lazyPending']} lazy images still pending")
    try:
        from PIL import Image, ImageStat
        screenshot = Image.open(shot_path)
        result["info"]["shot"] = list(screenshot.size)
        if abs(screenshot.height - layout.get("height", screenshot.height)) > 2:
            fail(result, f"screenshot height {screenshot.height} != layout height {layout.get('height')}: dump and screenshot disagree")
        thumbnail = screenshot.convert("L").resize((64, max(1, int(64 * screenshot.height / screenshot.width))))
        if ImageStat.Stat(thumbnail).stddev[0] < 2:
            fail(result, "screenshot is blank")
    except Exception as error:
        fail(result, f"cannot read screenshot: {error}")
    if len(layout.get("elements", [])) < 10:
        fail(result, "almost no elements captured (blocked page / consent wall?)")
    return result
