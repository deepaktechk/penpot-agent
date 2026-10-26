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


# ---------------------------------------------------------------------- layout choice
LAYOUT_MODES = ("absolute", "auto")
LAYOUT_QUESTION = (
    "How should pb position the layers of this project? It is your choice, saved for the project:\n"
    "  --layout absolute   every layer at a fixed x/y (pixel-exact; nothing moves when you edit)\n"
    "  --layout auto       Penpot flex layouts wherever they reproduce the page exactly (edit a text and\n"
    "                      its neighbours move), fixed x/y everywhere else\n"
    "Run the command again with one of them.")


def resolve_layout(state: ProjectState, choice: str | None) -> str:
    """The project's layout mode: `choice` (saved), else the saved one. Never picked for the user: a
    project without one asks in a terminal and stops with the question otherwise. Projects built before
    the option existed were built absolutely and keep that."""
    if choice:
        if state.config.get("layout") != choice:
            state.config["layout"] = choice
            state.save_config()
        return choice
    saved = state.config.get("layout")
    if saved in LAYOUT_MODES:
        return saved
    if state.load_json("idmap.json", {}):
        print("[layout] this project was built with absolute positions; keeping them (--layout auto to change)", file=sys.stderr)
        return resolve_layout(state, "absolute")
    if sys.stdin.isatty() and sys.stderr.isatty():
        print(LAYOUT_QUESTION.rsplit("\n", 1)[0], file=sys.stderr)
        answer = ""
        while answer not in LAYOUT_MODES:
            answer = input("layout (absolute/auto): ").strip().lower()
        return resolve_layout(state, answer)
    raise SystemExit(LAYOUT_QUESTION)


# ---------------------------------------------------------------------- convert
def convert_capture(state: ProjectState, capture: str | None = None, fallback_font: str = "Inter",
                    system_font: str = "Inter", flat: bool = False, font_map: str | None = None,
                    region: tuple | None = None, out_path: str | None = None, check_fonts: bool = True,
                    use_cache: bool = True, layout_mode: str = "absolute") -> dict[str, Any]:
    """Capture dir (or layout.json) -> spec file. Returns a summary of the spec.

    layout_mode: "absolute" or "auto" (verified Penpot flex layouts, convert/layout.py); see resolve_layout.
    check_fonts: ask Penpot which font families exist; missing ones use `fallback_font`.
    font_map: "Web Font=Penpot Font,..." overrides.
    region: (x0, y0, x1, y1) - only sections overlapping y0..y1 are kept.
    use_cache: reuse the last spec when every input is unchanged (`run_cache.convert_key`).
    """
    from pbridge.convert import Converter, count_nodes
    from pbridge.run_cache import RunCache, convert_key, file_digest, source_digest
    capture_path = Path(capture) if capture else Path(state.config.get("capture", ""))
    layout_file = capture_path / "layout.json" if capture_path.is_dir() else capture_path
    layout = json.loads(layout_file.read_text())
    opts: dict[str, Any] = {"fallback_font": fallback_font, "group": not flat, "system_font": system_font, "layout": layout_mode}
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
    spec_file = Path(out_path) if out_path else state.path("specs", (capture_path.name or "spec") + ".json")
    cache = RunCache(state)
    key_options = {key: value for key, value in opts.items() if key not in ("screenshot", "available_fonts")}
    key = convert_key(layout_file, screenshot if screenshot.exists() else None, {**key_options, "region": region, "out": str(spec_file)},
                      opts.get("available_fonts"), source_digest())
    cached = cache.lookup("convert", key) if use_cache else None
    if cached and file_digest(spec_file) == cached.get("spec_digest"):   # a hand-edited spec is a miss
        print("[convert] inputs unchanged: reusing " + spec_file.name, file=sys.stderr)
        return {**cached["summary"], "cached": True}
    spec = Converter(layout, opts).convert(region[1] if region else None, region[3] if region else None)
    spec_file.write_text(json.dumps(spec, ensure_ascii=False))
    summary = {"spec": str(spec_file), "sections": [(board.get("key"), board["name"], board["y"], board["h"]) for board in spec["nodes"]],
               "nodes": count_nodes(spec["nodes"]), "images": len(spec["images"]), "report": spec["report"]}
    cache.store("convert", key, {"spec_digest": file_digest(spec_file), "summary": summary})
    return summary


# ---------------------------------------------------------------------- build
def file_revision(bridge: Bridge) -> str | None:
    """"<file id>@<revn>" of the file the plugin is connected to; Penpot bumps revn on every persisted change."""
    try:
        return bridge.exec("const file = penpot.currentFile; return file ? file.id + '@' + file.revn : null;")
    except Exception as error:   # no revision -> no short-circuit, never a failed run
        print(f"[rebuild] file revision unavailable: {str(error)[:80]}", file=sys.stderr)
        return None


def build_spec(bridge: Bridge, spec_path: str, parent: str | None = None, page_board: str | None = None,
               only: list[str] | None = None, replace: bool = True, font: str | None = None,
               after: str | None = None, page: str | None = None, rebuild_all: bool = True,
               staged: bool = True) -> dict[str, Any]:
    """Build a spec file. With page_board, (create and) size that board and build into it.
    With page, open (or create) that Penpot page first. rebuild_all=False keeps sections whose
    content did not change since the last build. staged=False builds every section in place."""
    from pbridge.build import PageBoards, SpecBuilder
    from pbridge.build.validate import validate_spec
    spec = json.loads(Path(spec_path).read_text())
    check = validate_spec(spec)
    if check.errors:      # fail before touching Penpot; `pb validate` lists everything
        raise SystemExit(f"{spec_path} is not a valid spec ({len(check.errors)} errors):\n  " + "\n  ".join(check.errors[:20]))
    # temporary pages a crashed staged build left behind; also leaves such a page if it is open,
    # so the page board below is looked up on a real page
    bridge.exec("return await pb.stageCleanup(null);")
    if page:
        from pbridge.cli.commands.document import open_page
        open_page(bridge, page)
    if page_board:
        page_width = spec.get("width") if isinstance(spec, dict) else None
        page_height = spec.get("height") if isinstance(spec, dict) else None
        # on another page, look the board up by name there (the remembered id may be on a different page)
        parent = PageBoards(bridge).ensure(page_board, page_width, page_height, after=after, reuse_stored_id=not page)
    report = SpecBuilder(bridge).build(spec, parent=parent, only=only, replace=replace, default_font=font,
                                       rebuild_all=rebuild_all, staged_build=staged)
    report["spec_warnings"] = check.warnings
    return {key: (value[:20] if isinstance(value, list) else value) for key, value in report.items()}


def build_responsive(state: ProjectState, bridge: Bridge, captures: list[dict[str, Any]], board: str, font: str = "Inter",
                     system_font: str = "Inter", font_map: str | None = None, layout_mode: str = "absolute") -> list[dict[str, Any]]:
    """One page board per captured width ("<board> – 390px"), placed left to right, each compared
    with its own capture. The first width's board stays the project's page board."""
    from pbridge.connection import Exporter
    results = []
    previous_board: str | None = None
    first_board_id: str | None = None
    for capture in captures:
        capture_dir = Path(capture["out"])
        width = capture.get("width") or json.loads((capture_dir / "layout.json").read_text())["width"]
        spec = convert_capture(state, str(capture_dir), fallback_font=font, system_font=system_font, font_map=font_map,
                               layout_mode=layout_mode)
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
            "in_layout": sum(1 for result in fixed if result.get("skipped")),
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
