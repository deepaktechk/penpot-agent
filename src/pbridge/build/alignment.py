"""Per-element misplacement audit against the reference, and automatic nudging.

audit:   for every built element box (boxes.json), search the (dx, dy) that best aligns the
         render with the reference (imaging.audit). Elements whose best offset is non-zero
         and clearly better are reported; big mismatches that no shift fixes get a note.
autofix: move the reported elements by -offset (only small shifts, never annotated ones). Children
         placed by a Penpot flex layout (`--layout auto`) are left alone: the layout positions them.
"""
from __future__ import annotations

from typing import Any

from pbridge.connection import Bridge

# [x, y], "flow" for a child positioned by its parent's flex layout, null when gone
_POSITIONS_JS = ("return DATA.map(id => { const shape = pb.byId(id); if (!shape) return null; "
                 "const child = shape.layoutChild; if (child && !child.absolute) return 'flow'; return [shape.x, shape.y]; });")


class Aligner:
    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.state = bridge.state

    def audit(self, reference: str, render: str, keys: list[str] | None = None, region=None, limit: int = 60,
              **audit_options: Any) -> list[dict]:
        from pbridge.imaging import audit as image_audit
        boxes = self.state.load_json("boxes.json", {})
        idmap = self.state.load_json("idmap.json", {})
        elements = []
        for key, entry in boxes.items():
            if keys and not any(key == wanted or key.startswith(wanted + ".") for wanted in keys):
                continue
            if entry["t"] in ("board",):
                continue
            x, y, width, height = entry["box"]
            if region and (y + height < region[1] or y > region[3] or x + width < region[0] or x > region[2]):
                continue
            elements.append({"key": key, "id": idmap.get(key), "name": entry.get("name"), "box": entry["box"]})
        return image_audit(reference, render, elements, **audit_options)[:limit]

    def autofix(self, issues: list[dict], max_shift: int = 6, batch: int = 25) -> list[dict]:
        """Apply offsets as ABSOLUTE positions (idempotent -> safe to retry after timeouts),
        in small batches so no plugin call runs long."""
        todo = [issue for issue in issues if not issue.get("note") and issue.get("id")
                and abs(issue["dx"]) <= max_shift and abs(issue["dy"]) <= max_shift and (issue["dx"] or issue["dy"])]
        report: list[dict] = []
        for start in range(0, len(todo), batch):
            chunk = todo[start:start + batch]
            positions = self.bridge.exec(_POSITIONS_JS, data=[issue["id"] for issue in chunk], idempotent=True)
            ops = [{"sel": {"id": issue["id"]},
                    "set": {"x": round(position[0] - issue["dx"], 3), "y": round(position[1] - issue["dy"], 3)}}
                   for issue, position in zip(chunk, positions) if isinstance(position, list)]
            report += [{"id": issue["id"], "skipped": "in a flex layout"}
                       for issue, position in zip(chunk, positions) if position == "flow"]
            if ops:
                report += self.bridge.exec("return pb.patch(DATA);", data=ops, idempotent=True, timeout=300)
        return report
