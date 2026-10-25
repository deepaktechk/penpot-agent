"""Application workflows shared by several CLI commands (convert, build, compare, audit, qa).

Each function does one step and returns a JSON-able summary; the CLI decides how to print.
`pb rebuild` and `pb clone` chain them.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from pbridge.connection import Bridge
from pbridge.project import ProjectState


# ---------------------------------------------------------------------- convert
def convert_capture(state: ProjectState, capture: str | None = None, fallback_font: str = "Inter",
                    system_font: str = "Inter", flat: bool = False, font_map: str | None = None,
                    region: tuple | None = None, out_path: str | None = None, check_fonts: bool = True) -> dict[str, Any]:
    """Capture dir (or layout.json) -> spec file. Returns a summary of the spec.

    check_fonts: ask Penpot which font families exist; missing ones use `fallback_font`.
    font_map: "Web Font=Penpot Font,..." overrides.
    region: (x0, y0, x1, y1) - only sections overlapping y0..y1 are kept.
    """
    from pbridge.convert import Converter, count_nodes
    capture_path = Path(capture) if capture else Path(state.config.get("capture", ""))
    layout_file = capture_path / "layout.json" if capture_path.is_dir() else capture_path
    layout = json.loads(layout_file.read_text())
    opts: dict[str, Any] = {"fallback_font": fallback_font, "group": not flat, "system_font": system_font}
    screenshot = layout_file.parent / "shot.png"
    if screenshot.exists():
        opts["screenshot"] = str(screenshot)
    if check_fonts:
        try:
            opts["available_fonts"] = set(Bridge(state).exec("return penpot.fonts.all.map(font => font.name);"))
        except Exception as error:
            print(f"[convert] font check skipped: {str(error)[:80]}", file=sys.stderr)
    if font_map:
        opts["font_map"] = dict(pair.split("=", 1) for pair in font_map.split(","))
    spec = Converter(layout, opts).convert(region[1] if region else None, region[3] if region else None)
    spec_file = Path(out_path) if out_path else state.path("specs", (capture_path.name or "spec") + ".json")
    spec_file.write_text(json.dumps(spec, ensure_ascii=False))
    return {"spec": str(spec_file), "sections": [(board.get("key"), board["name"], board["y"], board["h"]) for board in spec["nodes"]],
            "nodes": count_nodes(spec["nodes"]), "images": len(spec["images"]), "report": spec["report"]}


# ---------------------------------------------------------------------- build
def build_spec(bridge: Bridge, spec_path: str, parent: str | None = None, page_board: str | None = None,
               only: list[str] | None = None, replace: bool = True, font: str | None = None,
               after: str | None = None, page: str | None = None) -> dict[str, Any]:
    """Build a spec file. With page_board, (create and) size that board and build into it.
    With page, open (or create) that Penpot page first."""
    from pbridge.build import PageBoards, SpecBuilder
    from pbridge.build.validate import validate_spec
    spec = json.loads(Path(spec_path).read_text())
    check = validate_spec(spec)
    if check.errors:      # fail before touching Penpot; `pb validate` lists everything
        raise SystemExit(f"{spec_path} is not a valid spec ({len(check.errors)} errors):\n  " + "\n  ".join(check.errors[:20]))
    if page:
        from pbridge.cli.commands.document import open_page
        open_page(bridge, page)
    if page_board:
        page_width = spec.get("width") if isinstance(spec, dict) else None
        page_height = spec.get("height") if isinstance(spec, dict) else None
        # on another page, look the board up by name there (the remembered id may be on a different page)
        parent = PageBoards(bridge).ensure(page_board, page_width, page_height, after=after, reuse_stored_id=not page)
    report = SpecBuilder(bridge).build(spec, parent=parent, only=only, replace=replace, default_font=font)
    report["spec_warnings"] = check.warnings
    return {key: (value[:20] if isinstance(value, list) else value) for key, value in report.items()}


def build_responsive(state: ProjectState, bridge: Bridge, captures: list[dict[str, Any]], board: str, font: str = "Inter",
                     system_font: str = "Inter", font_map: str | None = None) -> list[dict[str, Any]]:
    """One page board per captured width ("<board> – 390px"), placed left to right, each compared
    with its own capture. The first width's board stays the project's page board."""
    from pbridge.connection import Exporter
    results = []
    previous_board: str | None = None
    first_board_id: str | None = None
    for capture in captures:
        capture_dir = Path(capture["out"])
        width = capture.get("width") or json.loads((capture_dir / "layout.json").read_text())["width"]
        spec = convert_capture(state, str(capture_dir), fallback_font=font, system_font=system_font, font_map=font_map)
        board_name = f"{board} – {width}px"
        build_spec(bridge, spec["spec"], page_board=board_name, font=font, after=previous_board or "*")
        board_id = bridge.state.config["page_board"]
        first_board_id = first_board_id or board_id
        render = Exporter(bridge).export(board_id)
        metrics = compare_render(bridge, str(capture_dir / "shot.png"), str(render))
        results.append({"width": width, "board": board_name, "page_pct": metrics["pct"], "render": str(render)})
        previous_board = board_name
    if first_board_id:   # keep `pb qa` / `pb compare` pointing at the first (reference) width
        bridge.state.config["page_board"] = first_board_id
        bridge.state.config["page_board_name"] = f"{board} – {results[0]['width']}px"
        bridge.state.save_config()
    return results


# ---------------------------------------------------------------------- QA
def compare_render(bridge: Bridge, reference: str, render: str, region: tuple | None = None, want_ssim: bool = False,
                   n_hotspots: int = 0, n_montage: int = 0, overlay: bool = False, mode: str = "stack",
                   scale: float = 1.0) -> dict[str, Any]:
    """Pixel metrics (+ hotspots, montage and overlay images in .pbridge/diffs/)."""
    from pbridge import imaging
    result = imaging.compare(reference, render, region, want_ssim=want_ssim)
    result["render"] = render
    if n_hotspots:
        aligned = imaging.align_sizes(imaging.load(reference), imaging.load(render))
        result["hotspots"] = imaging.hotspots(*aligned, region=region, limit=n_hotspots)
    if n_montage:
        reference_image, render_image = imaging.align_sizes(imaging.load(reference), imaging.load(render))
        spots = result.get("hotspots") or imaging.hotspots(reference_image, render_image, region=region, limit=n_montage)
        montage_file = bridge.state.path("diffs", f"montage-{int(time.time())}.png")
        imaging.montage(reference, render, spots[:n_montage], montage_file)
        result["montage"] = str(montage_file)
    if overlay:
        overlay_file = bridge.state.path("diffs", f"diff-{int(time.time())}.png")
        imaging.overlay(reference, render, overlay_file, region, mode, scale)
        result["overlay"] = str(overlay_file)
    return result


def verify_build(bridge: Bridge, design: str, site_screenshot: str, max_pct: float = 3.0) -> dict[str, Any]:
    """Implemented page vs design: the design is the reference; hotspots + montage show where they differ."""
    result = compare_render(bridge, design, site_screenshot, n_hotspots=8, n_montage=6)
    result.update({"design": design, "site": site_screenshot, "max_pct": max_pct, "ok": result["pct"] <= max_pct})
    return result


def audit_render(bridge: Bridge, reference: str, render: str, keys: list[str] | None = None, region: tuple | None = None,
                 limit: int = 40, fix: bool = False, max_shift: int = 6) -> dict[str, Any]:
    """Per-element offset audit; with fix=True nudge the misplaced elements."""
    from pbridge.build import Aligner
    aligner = Aligner(bridge)
    issues = aligner.audit(reference, render, keys=keys, region=region, limit=limit)
    if not fix:
        return {"render": render, "issues": issues}
    fixed = aligner.autofix(issues, max_shift=max_shift)
    return {"render": render, "issues": len(issues), "moved": sum(1 for result in fixed if result.get("ok")),
            "unfixable": [issue for issue in issues if issue.get("note")][:15]}


def run_qa(state: ProjectState, render: str, spec_path: str | None = None, record: bool = True) -> tuple[bool, dict[str, Any]]:
    """Render gate; prints the verdict to stderr and returns (ok, summary)."""
    from pbridge.quality import print_gate, render_gate
    spec_path = spec_path or str(state.spec_path())
    spec = json.loads(Path(spec_path).read_text())
    gate = render_gate(state.config["reference"], render, spec, state=state, record=record)
    print_gate("render", gate)
    sections = gate["info"]["sections"]
    worst = sorted(sections.items(), key=lambda item: -item[1]["pct"])[:5]
    return gate["ok"], {"ok": gate["ok"], "page": gate["info"]["page"],
                        "worst_sections": [(key, section["name"], section["pct"]) for key, section in worst],
                        "errors": gate["errors"], "warnings": gate["warnings"][:10]}
