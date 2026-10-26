"""Performance experiments against the live Penpot file: bench build, bench export."""
from __future__ import annotations

from pbridge.bench import BUILD_MODES, bench_build, bench_export
from pbridge.cli.support import Args, get_bridge, out, resolve_target


def cmd_bench(args: Args) -> None:
    bridge = get_bridge(args)
    page_board = resolve_target(bridge, args.target)
    if args.what == "build":
        modes = tuple(args.modes.split(",")) if args.modes else BUILD_MODES
        unknown = [mode for mode in modes if mode not in BUILD_MODES]
        if unknown:
            raise SystemExit(f"unknown mode(s) {unknown}; choose from {', '.join(BUILD_MODES)}")
        result = bench_build(bridge, page_board, count=args.count, texts=args.texts, modes=modes, repeat=args.repeat)
        out(result if args.runs else {key: value for key, value in result.items() if key != "runs"}, args)
    else:
        out(bench_export(bridge, page_board, parallel=args.parallel), args)


def add_bench(subparsers) -> None:
    parser = subparsers.add_parser("bench", help="measure plugin build / export costs (temporary shapes, cleaned up)")
    parser.add_argument("what", choices=["build", "export"])
    parser.add_argument("--target", default="page", help="the page board to measure against (default: page)")
    parser.add_argument("--count", type=int, default=150, help="build: rectangles per experiment (default 150)")
    parser.add_argument("--texts", type=int, default=30, help="build: texts per experiment (default 30)")
    parser.add_argument("--modes", help="build: comma list of " + ", ".join(BUILD_MODES) + " (default all)")
    parser.add_argument("--repeat", type=int, default=2, help="build: runs per mode, the best is reported (default 2)")
    parser.add_argument("--runs", action="store_true", help="build: also print every run")
    parser.add_argument("--parallel", type=int, default=4, help="export: concurrent section exports (default 4)")
    parser.set_defaults(handler=cmd_bench)


PARSERS = {"bench": add_bench}
