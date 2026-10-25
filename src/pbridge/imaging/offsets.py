"""Offset search: by how many pixels is a region of the render shifted vs the reference?

best_offset: coarse grid search (step 2) within ±radius, then a ±1 refinement around the
             best point, minimising mean abs diff over the region.
audit:       best_offset for every element box (with a margin); flags elements whose best
             offset is non-zero and materially better than in place.
"""
from __future__ import annotations

import math

from PIL import Image

from pbridge.imaging.metrics import align_sizes, load, mad


def best_offset(reference: Image.Image, render: Image.Image, box, radius: int = 8, step_coarse: int = 2) -> dict:
    """(dx, dy) such that `render` shifted by (dx, dy) best matches `reference` inside box (x0, y0, x1, y1).

    Positive dx means the render content sits to the right of the reference.
    Returns {"dx", "dy", "before": mad in place, "after": mad at the best offset}.
    """
    left, top, right, bottom = box
    reference_crop = reference.crop(box).convert("L")

    def score(dx: int, dy: int) -> float:
        return mad(reference_crop, render.crop((left + dx, top + dy, right + dx, bottom + dy)).convert("L"))

    in_place = score(0, 0)
    best = (in_place, 0, 0)          # (score, dx, dy)
    for dy in range(-radius, radius + 1, step_coarse):
        for dx in range(-radius, radius + 1, step_coarse):
            candidate = score(dx, dy)
            if candidate < best[0]:
                best = (candidate, dx, dy)
    _, coarse_dx, coarse_dy = best
    for dy in range(coarse_dy - step_coarse + 1, coarse_dy + step_coarse):
        for dx in range(coarse_dx - step_coarse + 1, coarse_dx + step_coarse):
            if (dx, dy) == (coarse_dx, coarse_dy):
                continue
            candidate = score(dx, dy)
            if candidate < best[0]:
                best = (candidate, dx, dy)
    return {"dx": best[1], "dy": best[2], "before": round(in_place, 2), "after": round(best[0], 2)}


def audit(reference_path, render_path, elements: list[dict], margin: int = 4, radius: int = 6, min_gain: float = 0.25,
          min_size: int = 6) -> list[dict]:
    """elements: [{key, id, name, box: [x, y, w, h]}] -> elements needing a nudge (best gain first)."""
    reference, render = align_sizes(load(reference_path), load(render_path))
    image_width, image_height = reference.size
    issues = []
    for element in elements:
        x, y, width, height = element["box"]
        if width < min_size or height < min_size:
            continue
        box = (max(radius, int(x - margin)), max(radius, int(y - margin)),
               min(image_width - radius, int(math.ceil(x + width + margin))),
               min(image_height - radius, int(math.ceil(y + height + margin))))
        if box[2] - box[0] < 4 or box[3] - box[1] < 4:
            continue
        offset = best_offset(reference, render, box, radius=radius, step_coarse=1 if max(width, height) < 60 else 2)
        gain = offset["before"] - offset["after"]
        identity = {key: element.get(key) for key in ("key", "id", "name")}
        if (offset["dx"] or offset["dy"]) and gain >= min_gain and gain >= 0.15 * offset["before"]:
            issues.append({**identity, **offset})
        elif offset["before"] > 12:
            issues.append({**identity, **offset, "note": "mismatch (not an offset)"})
    issues.sort(key=lambda issue: -(issue["before"] - issue["after"]))
    return issues
