"""Visual QA against the reference: compare, audit, offset, qa."""
from __future__ import annotations

from pbridge.cli.support import Args, full_region, get_bridge, out, parse_region, reference_of, render_for, require_reference
from pbridge.workflows import audit_render, compare_render, run_qa


def cmd_compare(args: Args) -> None:
    bridge = get_bridge(args)
    reference = require_reference(bridge, args)
    render = render_for(bridge, args)
    region = full_region(parse_region(args.region), reference)
    out(compare_render(bridge, reference, render, region, want_ssim=args.ssim, n_hotspots=args.hotspots,
                       n_montage=getattr(args, "montage", 0), overlay=args.overlay, mode=args.mode, scale=args.scale), args)


def cmd_audit(args: Args) -> None:
    bridge = get_bridge(args)
    reference = reference_of(bridge, args)
    render = render_for(bridge, args)
    region = full_region(parse_region(args.region), reference)
    out(audit_render(bridge, reference, render, keys=args.keys.split(",") if args.keys else None, region=region,
                     limit=args.limit, fix=args.fix, max_shift=args.max_shift), args)


def cmd_offset(args: Args) -> None:
    from pbridge import imaging
    bridge = get_bridge(args)
    reference = reference_of(bridge, args)
    render = render_for(bridge, args)
    reference_image, render_image = imaging.align_sizes(imaging.load(reference), imaging.load(render))
    offsets = {}
    for region_spec in args.regions:            # name=x,y,w,h
        name, _, rect = region_spec.partition("=")
        x, y, width, height = [int(float(value)) for value in rect.split(",")]
        offsets[name] = imaging.best_offset(reference_image, render_image, (x, y, x + width, y + height), radius=args.radius)
    out(offsets, args)


def cmd_qa(args: Args) -> int:
    """Render quality gate: section thresholds, image checks, regression vs last good run."""
    bridge = get_bridge(args)
    render = render_for(bridge, args)
    ok, summary = run_qa(bridge.state, render, args.spec, record=not args.no_record)
    out(summary, args)
    return 0 if ok else 1


def _add_render_source_args(parser) -> None:
    parser.add_argument("--ref", help="reference PNG (default: the project reference)")
    parser.add_argument("--render", help="existing render PNG, or 'latest' (default: export --target now)")
    parser.add_argument("--target", default="page", help="what to export when no --render is given")
    parser.add_argument("--region", help="y0,y1 (full width) or x,y,w,h")
    parser.add_argument("--fast", action="store_true", help="export once without waiting for a settled render")


def add_compare(subparsers) -> None:
    parser = subparsers.add_parser("compare", help="pixel metrics vs reference (+hotspots/overlay)")
    _add_render_source_args(parser)
    parser.add_argument("--ssim", action="store_true", help="also compute structural similarity")
    parser.add_argument("--hotspots", type=int, default=0, help="list the N worst-differing areas")
    parser.add_argument("--montage", type=int, default=0, help="save a montage of the N worst hotspots")
    parser.add_argument("--overlay", action="store_true", help="save a diff image in .pbridge/diffs/")
    parser.add_argument("--mode", default="stack", choices=["stack", "overlay", "heat", "side"], help="diff image layout")
    parser.add_argument("--scale", type=float, default=1.0, help="diff image scale")
    parser.set_defaults(handler=cmd_compare)


def add_audit(subparsers) -> None:
    parser = subparsers.add_parser("audit", help="per-element offset audit (+--fix)")
    _add_render_source_args(parser)
    parser.add_argument("--keys", help="comma list of spec keys (prefixes) to audit")
    parser.add_argument("--limit", type=int, default=40, help="maximum issues listed")
    parser.add_argument("--fix", action="store_true", help="move misplaced elements to their best offset")
    parser.add_argument("--max-shift", type=int, default=6, help="largest automatic move in px")
    parser.set_defaults(handler=cmd_audit)


def add_offset(subparsers) -> None:
    parser = subparsers.add_parser("offset", help="best (dx,dy) for named regions")
    parser.add_argument("regions", nargs="+", help="name=x,y,w,h")
    parser.add_argument("--ref", help="reference PNG (default: the project reference)")
    parser.add_argument("--render", help="existing render PNG, or 'latest'")
    parser.add_argument("--target", default="page", help="what to export when no --render is given")
    parser.add_argument("--radius", type=int, default=8, help="search radius in px")
    parser.add_argument("--fast", action="store_true", help="export once without waiting for a settled render")
    parser.set_defaults(handler=cmd_offset)


def add_qa(subparsers) -> None:
    parser = subparsers.add_parser("qa", help="render quality gate (sections, images, regressions)")
    parser.add_argument("--render", default=None, help="PNG or 'latest' (default: export now)")
    parser.add_argument("--target", default="page", help="what to export when no --render is given")
    parser.add_argument("--fast", action="store_true", help="export once without waiting for a settled render")
    parser.add_argument("--spec", help="spec used for the section boundaries (default: the current capture's)")
    parser.add_argument("--no-record", action="store_true", help="do not add this run to .pbridge/history.json")
    parser.set_defaults(handler=cmd_qa)


PARSERS = {"compare": add_compare, "audit": add_audit, "offset": add_offset, "qa": add_qa}
