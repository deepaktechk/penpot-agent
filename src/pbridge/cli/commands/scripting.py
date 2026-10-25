"""Run arbitrary JS in the plugin: run (file), eval (expression/body).

`pb`, `DATA` (from --data) and `penpot` are in scope; the JS `return` value is printed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pbridge.cli.support import Args, get_bridge, out


def cmd_run(args: Args) -> None:
    bridge = get_bridge(args)
    code = Path(args.file).read_text() if args.file != "-" else sys.stdin.read()
    data = json.loads(Path(args.data).read_text()) if args.data else None
    out(bridge.exec(code, data=data, timeout=args.timeout), args)


def cmd_eval(args: Args) -> None:
    bridge = get_bridge(args)
    data = json.loads(args.data) if args.data else None
    # a bare expression is returned; anything with `return` or `;` is used as a body
    code = args.code if ("return" in args.code or ";" in args.code) else "return " + args.code + ";"
    out(bridge.exec(code, data=data, timeout=args.timeout), args)


def add_run(subparsers) -> None:
    parser = subparsers.add_parser("run", help="run a JS file in the plugin (uses pb, DATA, penpot)")
    parser.add_argument("file", help="JavaScript file, or - for stdin")
    parser.add_argument("--data", help="JSON file whose content is available as DATA")
    parser.add_argument("--timeout", type=float, help="seconds to wait for the plugin")
    parser.set_defaults(handler=cmd_run)


def add_eval(subparsers) -> None:
    parser = subparsers.add_parser("eval", help="evaluate a JS expression/body")
    parser.add_argument("code", help="expression (returned) or body with `return`")
    parser.add_argument("--data", help="inline JSON available as DATA")
    parser.add_argument("--timeout", type=float, help="seconds to wait for the plugin")
    parser.set_defaults(handler=cmd_eval)


PARSERS = {"run": add_run, "eval": add_eval}
