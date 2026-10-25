"""Read the Penpot file: tree, find, inspect, stats, lint."""
from __future__ import annotations

from pbridge.cli.support import TARGET_HELP, Args, get_bridge, out, resolve_target

FIND_JS = ("return pb.find(DATA).map(shape => ({id: shape.id, name: shape.name, type: shape.type, "
           "box: [Math.round(shape.x), Math.round(shape.y), Math.round(shape.width), Math.round(shape.height)], "
           "text: shape.type === 'text' ? String(shape.characters).slice(0, 60) : undefined}));")


def cmd_tree(args: Args) -> None:
    bridge = get_bridge(args)
    shape_id = resolve_target(bridge, args.target) if args.target else None
    tree = bridge.exec("return pb.tree(DATA ? pb.byId(DATA) : penpot.root, " + str(args.depth) + ");", data=shape_id)
    if args.json:
        out(tree); return

    # compact node format of pb.tree(): t type, n name, b box, txt text, nc hidden child count, c children
    def show(node: dict, indent: int = 0) -> None:
        text = f"  “{node['txt']}”" if node.get("txt") else ""
        more = f"  (+{node['nc']} children)" if node.get("nc") else ""
        print("  " * indent + f"{node['t'][:5]:5} {node['n'][:48]:48} {node['b']}{text}{more}  {node['id'][-12:]}")
        for child in node.get("c", []):
            show(child, indent + 1)
    show(tree)


def cmd_find(args: Args) -> None:
    bridge = get_bridge(args)
    query = {key: value for key, value in {"name": args.name, "re": args.re, "type": args.type, "text": args.text,
                                           "limit": args.limit}.items() if value}
    if args.within:
        query["within"] = resolve_target(bridge, args.within)
    out(bridge.exec(FIND_JS, data=query), args)


def cmd_inspect(args: Args) -> None:
    bridge = get_bridge(args)
    shape_id = resolve_target(bridge, args.target)
    out(bridge.exec("return pb.serialize(pb.byId(DATA.id), DATA.depth, {paths: DATA.paths});",
                    data={"id": shape_id, "depth": args.depth, "paths": args.paths}), args)


def cmd_stats(args: Args) -> None:
    bridge = get_bridge(args)
    shape_id = resolve_target(bridge, args.target) if args.target else None
    out(bridge.exec("return pb.stats(DATA);", data=shape_id), args)


def cmd_lint(args: Args) -> None:
    bridge = get_bridge(args)
    shape_id = resolve_target(bridge, args.target) if args.target else None
    issues = bridge.exec("return pb.lint(DATA);", data=shape_id)
    out({"issues": len(issues), "items": issues[: args.limit]}, args)


def add_tree(subparsers) -> None:
    parser = subparsers.add_parser("tree", help="layer tree")
    parser.add_argument("target", nargs="?", help=TARGET_HELP + " (default: page root)")
    parser.add_argument("-d", "--depth", type=int, default=2, help="levels to show (default 2)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of the indented tree")
    parser.set_defaults(handler=cmd_tree)


def add_find(subparsers) -> None:
    parser = subparsers.add_parser("find", help="find shapes")
    parser.add_argument("--name", help="exact layer name"); parser.add_argument("--re", help="regular expression on the layer name")
    parser.add_argument("--type", help="shape type: board, rect, text, path, group, image...")
    parser.add_argument("--text", help="text content contains this")
    parser.add_argument("--within", help="only inside this target")
    parser.add_argument("--limit", type=int, default=50, help="maximum results (default 50)")
    parser.set_defaults(handler=cmd_find)


def add_inspect(subparsers) -> None:
    parser = subparsers.add_parser("inspect", help="serialize a shape to spec JSON")
    parser.add_argument("target", help=TARGET_HELP)
    parser.add_argument("-d", "--depth", type=int, default=1, help="child levels to include (default 1)")
    parser.add_argument("--paths", action="store_true", help="include path data")
    parser.set_defaults(handler=cmd_inspect)


def add_stats(subparsers) -> None:
    parser = subparsers.add_parser("stats", help="counts, fonts, colors")
    parser.add_argument("target", nargs="?", help=TARGET_HELP + " (default: whole page)")
    parser.set_defaults(handler=cmd_stats)


def add_lint(subparsers) -> None:
    parser = subparsers.add_parser("lint", help="design hygiene issues")
    parser.add_argument("target", nargs="?", help=TARGET_HELP + " (default: whole page)")
    parser.add_argument("--limit", type=int, default=50, help="maximum issues listed (default 50)")
    parser.set_defaults(handler=cmd_lint)


PARSERS = {"tree": add_tree, "find": add_find, "inspect": add_inspect, "stats": add_stats, "lint": add_lint}
