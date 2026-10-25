"""Design review: review (accessibility, consistency, hygiene; --fix, --comment), comment."""
from __future__ import annotations

import json
import time
from pathlib import Path

from pbridge.cli.support import TARGET_HELP, Args, get_bridge, out, resolve_target

TREE_JS = "return pb.serialize(pb.byId(DATA), 99);"
ADD_COMMENTS_JS = """
    const threads = [];
    for (const comment of DATA) {
      const thread = await penpot.currentPage.addCommentThread(comment.text, {x: comment.x, y: comment.y});
      threads.push(thread && thread.seqNumber);
    }
    return threads;"""


def _options(args: Args):
    from pbridge.review import ReviewOptions
    return ReviewOptions(grid=args.grid, mobile=args.mobile, rules=set(args.rules.split(",")) if args.rules else set())


def _comments(issues: list[dict], limit: int) -> list[dict]:
    """One comment per issue with a position (errors first), at the issue's top-left corner."""
    return [{"text": f"[{found['rule']}] {found['message']}", "x": found["box"][0], "y": found["box"][1]}
            for found in issues if found.get("box")][:limit]


def cmd_review(args: Args) -> int:
    from PIL import Image

    from pbridge.review import review
    from pbridge.review.fixes import apply_to_spec, fix_operations
    if args.spec:                                     # offline: a spec file (+ optional screenshot)
        spec = json.loads(Path(args.spec).read_text())
        nodes = spec["nodes"] if isinstance(spec, dict) else spec
        render = Image.open(args.render) if args.render else None
        result = review(nodes, _options(args), render=render)
        if args.fix:
            result["fixed"] = apply_to_spec(spec, fix_operations(result["issues"]))
            Path(args.spec).write_text(json.dumps(spec, ensure_ascii=False))
    else:                                             # live: a Penpot board / layer
        from pbridge.build import Snapshots
        from pbridge.connection import Exporter
        bridge = get_bridge(args)
        shape_id = resolve_target(bridge, args.target)
        tree = bridge.exec(TREE_JS, data=shape_id, timeout=300)
        render = None
        if not args.no_render:   # judge contrast on the real pixels (images, gradients, vectors behind text)
            render = Image.open(args.render or Exporter(bridge).export(shape_id, settle=False))
        result = review([tree], _options(args), render=render, origin=(tree["x"], tree["y"]))
        if args.fix and result["summary"]["fixable"]:
            Snapshots(bridge).save(shape_id, f"pre-review-fix-{int(time.time())}")
            outcome = bridge.exec("return pb.patch(DATA);", data=fix_operations(result["issues"]), timeout=300)
            result["fixed"] = sum(1 for entry in outcome if entry.get("ok"))
        if args.comment:
            result["comments"] = bridge.exec(ADD_COMMENTS_JS, data=_comments(result["issues"], args.limit), timeout=300)
    result["issues"] = result["issues"][: args.limit] if not args.all else result["issues"]
    out(result, args)
    return 1 if result["summary"]["errors"] else 0


def cmd_comment(args: Args) -> None:
    """Post a comment on the canvas at a target (default: its top-left corner)."""
    bridge = get_bridge(args)
    shape_id = resolve_target(bridge, args.target)
    position = bridge.exec("const shape = pb.byId(DATA); return [shape.x, shape.y];", data=shape_id)
    out({"thread": bridge.exec(ADD_COMMENTS_JS, data=[{"text": args.text, "x": position[0], "y": position[1]}])})


def add_review(subparsers) -> None:
    from pbridge.review import RULES
    parser = subparsers.add_parser("review", help="design review: contrast, type scale, colours, alignment, hygiene (+--fix)")
    parser.add_argument("target", nargs="?", default="page", help=TARGET_HELP + " (default: page)")
    parser.add_argument("--spec", help="review a spec file offline instead of the live design")
    parser.add_argument("--render", help="PNG of the reviewed area, for pixel-accurate contrast (live: exported automatically)")
    parser.add_argument("--no-render", action="store_true", help="live: judge contrast from layer colours only (no export)")
    parser.add_argument("--grid", type=int, default=0, help="also check positions/sizes against this spacing grid, e.g. 8")
    parser.add_argument("--mobile", action="store_true", help="also check 44x44 px touch targets of links and buttons")
    parser.add_argument("--rules", help="comma list of rules to run: " + ", ".join(RULES))
    parser.add_argument("--fix", action="store_true", help="apply the safe fixes (live: snapshot first; spec: file rewritten)")
    parser.add_argument("--comment", action="store_true", help="live: post the issues as comments on the canvas")
    parser.add_argument("--limit", type=int, default=50, help="issues listed / comments posted (default 50)")
    parser.add_argument("--all", action="store_true", help="list every issue")
    parser.set_defaults(handler=cmd_review)


def add_comment(subparsers) -> None:
    parser = subparsers.add_parser("comment", help="post a comment on the canvas")
    parser.add_argument("target", help=TARGET_HELP)
    parser.add_argument("text", help="comment text")
    parser.set_defaults(handler=cmd_comment)


PARSERS = {"review": add_review, "comment": add_comment}
