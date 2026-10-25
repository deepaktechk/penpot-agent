"""Change the Penpot file: validate, build, patch, rm, snapshot, restore."""
from __future__ import annotations

import json
import time
from pathlib import Path

from pbridge.build import Snapshots
from pbridge.cli.support import TARGET_HELP, Args, get_bridge, out, resolve_target
from pbridge.workflows import build_spec

REMOVE_MANY_JS = "return DATA.map(id => { const shape = pb.byId(id); if (shape) { shape.remove(); return id; } return null; });"


def cmd_validate(args: Args) -> int:
    """Check a spec offline (no Penpot needed); exit 1 when it has errors."""
    from pbridge.build.validate import validate_spec
    report = validate_spec(json.loads(Path(args.spec).read_text()))
    out(report.to_dict(), args)
    return 0 if report.ok else 1


def cmd_build(args: Args) -> None:
    bridge = get_bridge(args)
    parent = resolve_target(bridge, args.parent) if args.parent else None
    report = build_spec(bridge, args.spec, parent=parent, page_board=args.page_board,
                        only=args.only.split(",") if args.only else None, replace=not args.no_replace, font=args.font,
                        after=getattr(args, "after", None), page=args.page)
    out(report, args)


def cmd_patch(args: Args) -> None:
    bridge = get_bridge(args)
    ops = json.loads(Path(args.ops).read_text()) if Path(args.ops).exists() else json.loads(args.ops)
    if isinstance(ops, dict):
        ops = [ops]
    idmap = bridge.state.load_json("idmap.json", {})
    for operation in ops:   # allow {"sel": {"key": "sec01.3"}} using the persisted id map
        selector = operation.get("sel", {})
        if "key" in selector and selector["key"] in idmap:
            operation["sel"] = {"id": idmap[selector["key"]]}
    if args.snapshot:
        Snapshots(bridge).save(resolve_target(bridge, args.snapshot), f"pre-patch-{int(time.time())}")
    out(bridge.exec("return pb.patch(DATA);", data=ops), args)


def cmd_rm(args: Args) -> None:
    bridge = get_bridge(args)
    ids = [resolve_target(bridge, target) for target in args.targets]
    out(bridge.exec(REMOVE_MANY_JS, data=ids))


def cmd_snapshot(args: Args) -> None:
    bridge = get_bridge(args)
    shape_id = resolve_target(bridge, args.target)
    out({"snapshot": str(Snapshots(bridge).save(shape_id, args.label or f"snap-{int(time.time())}"))})


def cmd_restore(args: Args) -> None:
    bridge = get_bridge(args)
    snapshots = Snapshots(bridge)
    if args.label == "list":
        out(snapshots.labels()); return
    out(snapshots.restore(args.label, resolve_target(bridge, args.parent) if args.parent else None))


def add_validate(subparsers) -> None:
    parser = subparsers.add_parser("validate", help="check a spec JSON offline (types, required keys, typos)")
    parser.add_argument("spec", help="spec JSON file (see docs/spec-format.md)")
    parser.set_defaults(handler=cmd_validate)


def add_build(subparsers) -> None:
    parser = subparsers.add_parser("build", help="build a spec JSON")
    parser.add_argument("spec", help="spec JSON file (see docs/spec-format.md)")
    parser.add_argument("--parent", help="build inside this target")
    parser.add_argument("--page-board", help="create/reuse a page board with this name sized to the spec")
    parser.add_argument("--only", help="comma list of section keys/names")
    parser.add_argument("--no-replace", action="store_true", help="keep the shapes of a previous build of the same keys")
    parser.add_argument("--font", help="default font family")
    parser.add_argument("--after", help="place a new page board right of this board ('*' = right of everything)")
    parser.add_argument("--page", help="build on this Penpot page (created when missing)")
    parser.set_defaults(handler=cmd_build)


def add_patch(subparsers) -> None:
    parser = subparsers.add_parser("patch", help="apply patch ops (JSON file or inline)")
    parser.add_argument("ops", help="patch operations: JSON file or inline JSON (see docs/commands.md)")
    parser.add_argument("--snapshot", help="snapshot this target before patching")
    parser.set_defaults(handler=cmd_patch)


def add_rm(subparsers) -> None:
    parser = subparsers.add_parser("rm", help="remove shapes")
    parser.add_argument("targets", nargs="+", help=TARGET_HELP)
    parser.set_defaults(handler=cmd_rm)


def add_snapshot(subparsers) -> None:
    parser = subparsers.add_parser("snapshot", help="save a shape subtree")
    parser.add_argument("target", help=TARGET_HELP)
    parser.add_argument("--label", help="snapshot name (default: snap-<time>)")
    parser.set_defaults(handler=cmd_snapshot)


def add_restore(subparsers) -> None:
    parser = subparsers.add_parser("restore", help="restore snapshot by label (or 'list')")
    parser.add_argument("label", help="snapshot label, or 'list'")
    parser.add_argument("--parent", help="rebuild inside this target")
    parser.set_defaults(handler=cmd_restore)


PARSERS = {"validate": add_validate, "build": add_build, "patch": add_patch, "rm": add_rm, "snapshot": add_snapshot, "restore": add_restore}
