"""Render gate: score a build against the reference and catch regressions.

1. page metrics (mad, % differing pixels)
2. per section board: % differing pixels -> error above section_pct_error, warning above
   section_pct_warn (thin strips < 150 px are judged by absolute differing pixels instead)
3. per image/svg box: a large mean abs diff means missing, blank or wrongly fitted content
4. regression vs the last good run in `.pbridge/history.json` (sections matched by name and
   vertical overlap, since keys can be renumbered when sectioning changes)
The run is appended to history.json (last 50 kept) unless record=False.
"""
from __future__ import annotations

import time
from typing import Any

from pbridge.build.spec_tree import flatten
from pbridge.project import ProjectState
from pbridge.quality.result import GateResult, fail, new_result, thresholds

THIN_SECTION_PX = 150
MIN_IMAGE_AREA = 2500


def _section_scores(result: GateResult, reference, render, spec: dict, limits: dict) -> dict[str, dict]:
    from pbridge import imaging
    page_width, page_height = reference.size
    sections: dict[str, dict] = {}
    for board in spec.get("nodes", []):
        if board.get("t") != "board" or board.get("key") == "secbg":
            continue
        top, bottom = max(0, int(board["y"])), min(page_height, int(board["y"] + board["h"]))
        if bottom - top < 4:
            continue
        box = (0, top, page_width, bottom)
        reference_crop, render_crop = reference.crop(box), render.crop(box)
        score = {"name": board.get("name"), "y": top, "h": bottom - top, "mad": round(imaging.mad(reference_crop, render_crop), 3),
                 "pct": round(imaging.pct_diff(reference_crop, render_crop), 3)}
        key, name = board["key"], board.get("name")
        sections[key] = score
        if (bottom - top) < THIN_SECTION_PX:     # thin strips: percentages are noisy, judge by absolute pixels
            if score["pct"] * (bottom - top) * page_width / 100 > 0.03 * page_width * THIN_SECTION_PX:
                result["warnings"].append(f"thin section {key} '{name}' differs {score['pct']}%")
            continue
        if score["pct"] > limits["section_pct_error"]:
            fail(result, f"section {key} '{name}' differs {score['pct']}% (> {limits['section_pct_error']}%)")
        elif score["pct"] > limits["section_pct_warn"]:
            result["warnings"].append(f"section {key} '{name}' differs {score['pct']}%")
    return sections


def _image_failures(reference, render, spec: dict, limits: dict) -> list[dict]:
    from pbridge import imaging
    page_width, page_height = reference.size
    failures = []
    for node in flatten(spec.get("nodes", [])):
        if node.get("t") not in ("image", "svg") or not all(key in node for key in ("x", "y", "w", "h")):
            continue
        if node["w"] * node["h"] < MIN_IMAGE_AREA:
            continue
        box = (max(0, int(node["x"])), max(0, int(node["y"])),
               min(page_width, int(node["x"] + node["w"])), min(page_height, int(node["y"] + node["h"])))
        if box[2] - box[0] < 8 or box[3] - box[1] < 8:
            continue
        difference = imaging.mad(reference.crop(box), render.crop(box))
        if difference > limits["image_mad_error"]:
            failures.append({"name": node.get("name"), "key": node.get("key"), "t": node["t"], "box": list(box),
                             "mad": round(difference, 1)})
    return failures


def _baseline_match(baseline: dict, section: dict) -> dict | None:
    """The same section in the baseline: same name and overlapping, else >= 60% vertical overlap."""
    best, best_score = None, 0.0
    for old in baseline["sections"].values():
        if "y" not in old:            # old history entries: match by name only
            if old.get("name") == section["name"] and best is None:
                best, best_score = old, 1.0
            continue
        overlap_px = min(section["y"] + section["h"], old["y"] + old["h"]) - max(section["y"], old["y"])
        overlap = max(0, overlap_px) / max(1, min(section["h"], old["h"]))
        score = overlap + (1.0 if old.get("name") == section["name"] else 0)
        if overlap >= 0.6 and score > best_score:
            best, best_score = old, score
    return best


def _check_regressions(result: GateResult, sections: dict, history: list[dict], limits: dict) -> None:
    baseline = next((run for run in reversed(history) if run.get("ok")), None)
    if not baseline:
        return
    for key, section in sections.items():
        old = _baseline_match(baseline, section)
        if not old:
            continue
        worse_by = section["pct"] - old["pct"]
        if worse_by > limits["regress_abs"] and worse_by > limits["regress_rel"] * max(old["pct"], 0.1):
            when = time.strftime('%Y-%m-%d %H:%M', time.localtime(baseline['time']))
            fail(result, f"REGRESSION in {key} '{section['name']}': {old['pct']}% -> {section['pct']}% (last good run {when})")


def render_gate(reference_path, render_path, spec: dict, state: ProjectState | None = None, overrides: dict | None = None,
                record: bool = True) -> GateResult:
    from pbridge import imaging
    limits = thresholds(overrides)
    result = new_result()
    reference, render = imaging.align_sizes(imaging.load(reference_path), imaging.load(render_path))
    result["info"]["page"] = {"mad": round(imaging.mad(reference, render), 3), "pct": round(imaging.pct_diff(reference, render), 3)}
    sections = _section_scores(result, reference, render, spec, limits)
    result["info"]["sections"] = sections
    image_failures = _image_failures(reference, render, spec, limits)
    for failure in image_failures:
        fail(result, f"{failure['t']} '{failure['name']}' ({failure['key']}) does not match the reference "
                     f"(mad {failure['mad']}): missing, blank or mis-fitted")
    result["info"]["image_failures"] = image_failures
    if state is not None:
        history: list[dict[str, Any]] = state.load_json("history.json", [])
        _check_regressions(result, sections, history, limits)
        if record:
            history.append({"time": time.time(), "ok": result["ok"], "page": result["info"]["page"], "sections": sections,
                            "render": str(render_path)})
            state.save_json("history.json", history[-50:])
    return result
