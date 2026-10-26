"""`pb` argument parser and entry point.

All commands operate on the project found by walking up from the cwd to a `.pbridge/`
folder (create it with `pb init`). Run `pb -h` or `pb <command> -h`.
"""
from __future__ import annotations

import argparse
import sys
import traceback

from pbridge import __version__
from pbridge.cli.commands import PARSERS
from pbridge.connection import PluginSuspended, redact

# order of commands in `pb -h`, grouped by topic
COMMAND_ORDER = [
    "init", "doctor", "prelude", "selftest", "bench",                          # setup
    "run", "eval",                                                             # scripting
    "tree", "find", "inspect", "stats", "lint",                                # inspect
    "page", "version", "code", "tokens",                                       # the file: pages, versions, code, tokens
    "validate", "build", "patch", "rm", "snapshot", "restore",                 # create / edit
    "export", "compare", "audit", "offset", "qa",                              # render + QA
    "review", "comment",                                                       # design review
    "assets", "analyze", "reference",                                          # images
    "capture", "convert", "clone", "rebuild", "responsive", "verify",          # websites
    "library", "fonts", "api",                                                 # tokens, lookups
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pb", description="Penpot bridge: drive Penpot from the terminal "
                                     "(build, inspect, patch, export, diff, clone websites).")
    parser.add_argument("--version", action="version", version=f"pb (penpot-agent) {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="print the timing of every plugin call")
    parser.add_argument("-c", "--compact", action="store_true", help="single-line JSON output")
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    assert set(COMMAND_ORDER) == set(PARSERS), "COMMAND_ORDER and the command modules disagree"
    for name in COMMAND_ORDER:
        PARSERS[name](subparsers)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    # progress must be visible line by line even when the output is redirected to a log file
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(line_buffering=True)
    try:
        exit_code = args.handler(args)      # every sub-parser sets `handler` to its cmd_<name> function
    except KeyboardInterrupt:
        exit_code = 130
    except Exception as error:
        message = redact(str(error))   # never leak the MCP token
        print(("PLUGIN SUSPENDED: " if isinstance(error, PluginSuspended) else "ERROR: ") + message[:3000], file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        exit_code = 1
    sys.exit(exit_code or 0)
