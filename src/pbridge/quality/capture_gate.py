"""Capture gate: refuse references that would poison every later step.

Checks the evidence recorded by the capture (layout.quality) and the screenshot:
  * text painted with a fallback font instead of the web font (canvas width check)
  * page never became still (carousels / animations mid-transition)
  * broken or still-lazy images
  * screenshot height != layout height, blank screenshot, almost no elements (consent wall)
  * a bot check / interstitial page instead of the site (Cloudflare "Just a moment...")
"""
from __future__ import annotations

import re
from pathlib import Path

from pbridge.quality.result import GateResult, fail, new_result, thresholds


# titles / texts of bot-check and interstitial pages served instead of the site (anchored: a real page
# that merely mentions Cloudflare must pass)
CHALLENGE_TITLE = re.compile(r"^\s*(just a moment|attention required|access denied|security check|"
                             r"please wait|checking your browser|verifying you are human|ddos-guard)", re.IGNORECASE)
CHALLENGE_TEXT = re.compile(r"verify(ing)? you are (a )?human|checking (if the site connection is secure|your browser)|"
                            r"enable javascript and cookies to continue|press (and|&) hold", re.IGNORECASE)


def bot_check(layout: dict) -> str | None:
    """Why the capture looks like a bot-check page rather than the site, or None."""
    title = layout.get("title") or ""
    if CHALLENGE_TITLE.search(title):
        return f"title {title!r}"
    for element in layout.get("elements", [])[:200]:
        if CHALLENGE_TEXT.search(str(element.get("text") or "")):
            return f"text {str(element['text'])[:60]!r}"
    return None


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
    challenge = bot_check(layout)
    if challenge:
        fail(result, f"the site served a bot check instead of the page ({challenge}). Capture with your own browser "
                     "session: open the site in Chrome yourself, then pass --user-data-dir (a copy of that profile) "
                     "or --cookies (cookies exported from it)")
    return result
