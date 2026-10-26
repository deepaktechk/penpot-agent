"""Website -> Penpot: capture, convert, clone, rebuild, responsive.

    clone      = capture -> convert -> build -> compare          (first time)
    rebuild    = convert (current capture) -> build -> [autofix] -> compare -> qa   (iterate)
    responsive = capture at several widths -> one board per width, side by side
    verify     = capture a built site and compare it with its Penpot design (handoff QA)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pbridge.capture import CaptureOptions, capture_site, capture_widths
from pbridge.cli.support import TARGET_HELP, Args, get_bridge, out, parse_region, render_for, require_reference, resolve_target
from pbridge.project import ProjectState
from pbridge.run_cache import RunCache, file_digest, rebuild_key
from pbridge.timing import StageTimer
from pbridge.workflows import (audit_render, build_responsive, build_spec, compare_render, convert_capture, file_revision,
                               run_qa)


def _widths(text: str) -> list[int]:
    """'1440,768,390' -> [1440, 768, 390]."""
    return [int(width) for width in text.split(",") if width.strip()]


def _capture_options(args: Args) -> CaptureOptions:
    """CaptureOptions from the capture-style arguments shared by `capture` and `responsive`."""
    return CaptureOptions(url=args.url, name=args.name, width=getattr(args, "width", 1920), dpr=args.dpr, fonts=args.fonts,
                          hide=args.hide, click=args.click, selector=args.selector, wait=args.wait, height=args.height,
                          no_scroll=args.no_scroll, no_freeze=args.no_freeze,
                          keep_overlays=getattr(args, "keep_overlays", False), color_scheme=args.color_scheme,
                          cookies=args.cookies, user_data_dir=args.user_data_dir,
                          set_reference=getattr(args, "set_reference", True), force=args.force,
                          retries=getattr(args, "retries", 3))


def cmd_capture(args: Args) -> None:
    """Capture with a quality gate. Bad captures (fallback font, broken images, page not
    settled...) are retried and never become the reference unless --force."""
    opts = _capture_options(args)
    if args.widths:
        out(capture_widths(ProjectState.open(), opts, _widths(args.widths)))
    else:
        out(capture_site(ProjectState.open(), opts))


def cmd_verify(args: Args) -> int:
    """Does the implemented page match the design? Capture the URL (not as the project reference),
    then compare it with the design board export (or --design PNG): metrics, hotspots, montage."""
    from pbridge.connection import Exporter
    from pbridge.workflows import verify_build
    state = ProjectState.open()
    opts = _capture_options(args)
    opts.set_reference = False
    opts.name = args.name or "build-" + opts.capture_name()
    capture = capture_site(state, opts)
    bridge = get_bridge(args)
    design = args.design or str(Exporter(bridge).export(resolve_target(bridge, args.target)))
    result = verify_build(bridge, design, capture["out"] + "/shot.png", args.max_pct)
    out(result, args)
    return 0 if result["ok"] else 1


def cmd_responsive(args: Args) -> None:
    """Capture the page at several widths and build one board per width, side by side."""
    state = ProjectState.open()
    captures = capture_widths(state, _capture_options(args), _widths(args.widths))
    out(build_responsive(state, get_bridge(args), captures, board=args.board, font=args.font, system_font=args.system_font,
                         font_map=args.font_map), args)


def cmd_convert(args: Args) -> None:
    state = ProjectState.open()
    out(convert_capture(state, args.capture, fallback_font=args.fallback_font, system_font=getattr(args, "system_font", "Inter"),
                        flat=args.flat, font_map=args.font_map, region=parse_region(args.region), out_path=args.out,
                        check_fonts=not getattr(args, "no_font_check", False)), args)


def cmd_clone(args: Args) -> None:
    """capture -> convert -> build -> compare in one go."""
    compact = Args(compact=True)
    state = ProjectState.open(); state.init()
    print("1/4 capture…", file=sys.stderr)
    out(capture_site(state, CaptureOptions(url=args.url, name=args.name, width=args.width, fonts=args.fonts, hide=args.hide,
                                           click=args.click, wait=1500)))
    state = ProjectState.open()
    print("2/4 convert…", file=sys.stderr)
    out(convert_capture(state, state.config["capture"], fallback_font=args.fallback_font, font_map=args.font_map), compact)
    print("3/4 build…", file=sys.stderr)
    bridge = get_bridge(args)
    out(build_spec(bridge, str(state.spec_path()), page_board=args.board, font=args.fallback_font), compact)
    print("4/4 compare…", file=sys.stderr)
    reference = require_reference(bridge)
    out(compare_render(bridge, reference, render_for(bridge, Args(render=None, target="page", fast=False)), n_hotspots=10,
                       overlay=True, mode="heat", scale=0.35))


def cmd_rebuild(args: Args) -> int:
    """convert (from current capture) -> build -> [autofix] -> compare -> render quality gate."""
    compact = Args(compact=True)
    timer = StageTimer("rebuild")
    state = ProjectState.open()
    with timer.stage("convert"):
        out(convert_capture(state, state.config.get("capture"), fallback_font=args.font, system_font=args.system_font,
                            font_map=args.font_map, use_cache=not args.all), compact)
    spec_path = str(state.spec_path())
    bridge = get_bridge(args)
    cache = RunCache(state)
    options = {key: value for key, value in vars(args).items() if key not in ("handler", "compact", "verbose")}
    cache_key = rebuild_key(file_digest(Path(spec_path)), file_digest(Path(require_reference(bridge))), bridge.version, options)
    if not args.all:
        previous = cache.reusable_rebuild(cache_key, file_revision(bridge), state.config.get("page_board"))
        if previous:
            print("[rebuild] nothing changed since the last run (spec, reference, options, Penpot file revision): "
                  "reusing its result; --all forces a fresh run", file=sys.stderr)
            out({**previous["result"], "cached": True, "render": previous["render"], "seconds": timer.summary()}, compact)
            return 0 if previous["result"].get("ok") else 1
    with timer.stage("build"):
        out(build_spec(bridge, spec_path, page_board=args.board or state.config.get("page_board_name") or "Page",
                       only=args.only.split(",") if args.only else None, font=args.font, after=getattr(args, "after", None),
                       page=args.page, rebuild_all=args.all, staged=not args.no_staging), compact)
    fresh_render = Args(render=None, target="page", fast=False)
    reference = require_reference(bridge)
    with timer.stage("export"):
        render = render_for(bridge, fresh_render)   # settled: re-exported until two exports are identical
    if args.fix:
        with timer.stage("audit+autofix"):
            fixed = audit_render(bridge, reference, render, limit=1000, fix=True, max_shift=3)
            out(fixed, compact)
        if fixed.get("moved"):
            # only positions changed and images/fonts were already loaded for the settled export:
            # one export shows the moves, no need to settle again (saves 1-2 exports of ~10 s)
            with timer.stage("export"):
                render = render_for(bridge, Args(render=None, target="page", fast=True))
    with timer.stage("compare+qa"):
        out(compare_render(bridge, reference, render, n_hotspots=args.hotspots, n_montage=args.montage), compact)
        ok, summary = run_qa(bridge.state, render, spec_path)
    # read last: the run's final edit is an export + QA old, so Penpot has persisted it by now
    cache.store_rebuild(cache_key, file_revision(bridge), state.config.get("page_board"), str(render), summary)
    out({**summary, "seconds": timer.summary()}, compact)
    return 0 if ok else 1


def _add_page_args(parser) -> None:
    """How the page is loaded: shared by `capture` and `responsive`."""
    parser.add_argument("url")
    parser.add_argument("--name", help="capture name (default: the domain)")
    parser.add_argument("--dpr", type=float, default=1, help="device pixel ratio (default 1)")
    parser.add_argument("--fonts", help="comma list of font families that must be loaded")
    parser.add_argument("--hide", help="comma list of CSS selectors to hide")
    parser.add_argument("--click", help="comma list of CSS selectors to click first (consent, tabs)")
    parser.add_argument("--selector", help="capture only this element's subtree")
    parser.add_argument("--wait", type=int, help="extra ms to wait before the dump (default 1500)")
    parser.add_argument("--height", type=int, help="fixed viewport height instead of the full page")
    parser.add_argument("--no-scroll", action="store_true", help="do not scroll to trigger lazy content")
    parser.add_argument("--no-freeze", action="store_true", help="do not pause animations and timers")
    parser.add_argument("--color-scheme", choices=["dark", "light"], default="light",
                        help="prefers-color-scheme to emulate (default light, independent of the OS setting)")
    parser.add_argument("--cookies", help="JSON cookie file (exported from the browser) for pages behind a login")
    parser.add_argument("--user-data-dir", help="Chrome profile folder with a logged-in session")
    parser.add_argument("--force", action="store_true", help="accept a capture that fails the quality gate")
    parser.add_argument("--keep-overlays", action="store_true", help="do not auto-hide cookie banners / chat widgets")
    parser.add_argument("--retries", type=int, default=3, help="attempts when the capture gate fails (default 3)")


def add_capture(subparsers) -> None:
    parser = subparsers.add_parser("capture", help="capture a website (screenshot + layout)")
    _add_page_args(parser)
    parser.add_argument("--width", type=int, default=1920, help="viewport width in px (default 1920)")
    parser.add_argument("--widths", help="capture several widths, e.g. 1440,768,390 (names get a -<width> suffix)")
    parser.add_argument("--set-reference", action="store_true", default=True, help=argparse.SUPPRESS)
    parser.set_defaults(handler=cmd_capture)


def add_verify(subparsers) -> None:
    parser = subparsers.add_parser("verify", help="compare a built website with its Penpot design (handoff QA)")
    _add_page_args(parser)
    parser.add_argument("--width", type=int, default=1920, help="viewport width = the design board width (default 1920)")
    parser.add_argument("--target", default="page", help=TARGET_HELP + " - the design to compare with (default: page)")
    parser.add_argument("--design", help="design PNG instead of exporting --target from Penpot")
    parser.add_argument("--max-pct", type=float, default=3.0, help="fail above this %% of differing pixels (default 3)")
    parser.set_defaults(handler=cmd_verify)


def add_responsive(subparsers) -> None:
    parser = subparsers.add_parser("responsive", help="capture several widths and build one board per width")
    _add_page_args(parser)
    parser.add_argument("--widths", default="1440,768,390", help="viewport widths (default 1440,768,390)")
    parser.add_argument("--board", default="Page", help="board name; each board gets ' – <width>px'")
    parser.add_argument("--font", default="Inter", help="fallback font for families missing in Penpot (default Inter)")
    parser.add_argument("--system-font", default="Inter", help="font for -apple-system/system-ui stacks")
    parser.add_argument("--font-map", help="Web Font=Penpot Font,...")
    parser.set_defaults(handler=cmd_responsive)


def add_convert(subparsers) -> None:
    parser = subparsers.add_parser("convert", help="capture layout -> spec")
    parser.add_argument("capture", nargs="?", help="capture folder or layout.json (default: the current capture)")
    parser.add_argument("--out", help="spec file (default: .pbridge/specs/<capture>.json)")
    parser.add_argument("--region", help="only sections overlapping y0,y1 or x,y,w,h")
    parser.add_argument("--fallback-font", default="Inter", help="font for families missing in Penpot (default Inter)")
    parser.add_argument("--system-font", default="Inter", help="font for -apple-system/system-ui stacks")
    parser.add_argument("--no-font-check", action="store_true", help="do not ask Penpot which fonts exist (offline)")
    parser.add_argument("--font-map", help="Web Font=Penpot Font,...")
    parser.add_argument("--flat", action="store_true", help="no groups: every shape directly in its section board")
    parser.set_defaults(handler=cmd_convert)


def add_clone(subparsers) -> None:
    parser = subparsers.add_parser("clone", help="capture+convert+build+compare a URL")
    parser.add_argument("url")
    parser.add_argument("--name", help="capture name (default: the domain)")
    parser.add_argument("--board", default="Page", help="page board name (default Page)")
    parser.add_argument("--width", type=int, default=1920, help="viewport width in px")
    parser.add_argument("--fonts", help="comma list of font families that must be loaded")
    parser.add_argument("--hide", help="comma list of CSS selectors to hide")
    parser.add_argument("--click", help="comma list of CSS selectors to click first")
    parser.add_argument("--fallback-font", default="Inter", help="font for families missing in Penpot")
    parser.add_argument("--font-map", help="Web Font=Penpot Font,...")
    parser.set_defaults(handler=cmd_clone)


def add_rebuild(subparsers) -> None:
    parser = subparsers.add_parser("rebuild", help="convert current capture -> build -> compare (+montage)")
    parser.add_argument("--board", help="page board name (default: the last one used)")
    parser.add_argument("--font", default="Inter", help="fallback font for families missing in Penpot (default Inter)")
    parser.add_argument("--system-font", default="Inter", help="font for -apple-system/system-ui stacks")
    parser.add_argument("--font-map", help="Web Font=Penpot Font,...")
    parser.add_argument("--only", help="comma list of section keys/names to rebuild")
    parser.add_argument("--hotspots", type=int, default=10, help="list the N worst-differing areas")
    parser.add_argument("--montage", type=int, default=8, help="montage image of the N worst areas (0 = none)")
    parser.add_argument("--fix", action="store_true", help="audit + autofix after building")
    parser.add_argument("--after", help="place a new page board right of this board ('*' = right of everything)")
    parser.add_argument("--page", help="build on this Penpot page (created when missing)")
    parser.add_argument("--all", action="store_true",
                        help="rebuild every section and re-convert, also when nothing changed since the last run")
    parser.add_argument("--no-staging", action="store_true",
                        help="build every section in place instead of on temporary pages (slower on big pages)")
    parser.set_defaults(handler=cmd_rebuild)


PARSERS = {"capture": add_capture, "convert": add_convert, "clone": add_clone, "rebuild": add_rebuild,
           "responsive": add_responsive, "verify": add_verify}
