"""Setup and health: init, doctor, prelude, selftest."""
from __future__ import annotations

import os
import subprocess
import time
import unittest
from pathlib import Path

from pbridge.cli.support import Args, get_bridge, out
from pbridge.connection import Bridge, MCPClient, discover_mcp_url, redact
from pbridge import __version__
from pbridge.paths import NODE_CLI, PLUGIN_RUNTIME, SOURCE_ROOT, TESTS_DIR, has_source_checkout
from pbridge.project import ProjectState

# keep in sync with js/src/shared/chrome.ts
CHROME_CANDIDATES = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                     "/Applications/Chromium.app/Contents/MacOS/Chromium",
                     "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]

PLUGIN_INFO_JS = ("return {file: penpot.currentFile && penpot.currentFile.name, "
                  "page: penpot.currentPage && penpot.currentPage.name, pages: penpotUtils.getPages().length};")


def cmd_init(args: Args) -> None:
    state = ProjectState.open(Path(args.dir).resolve() if args.dir else Path.cwd())
    state_dir = state.init()
    if args.reference:
        state.config["reference"] = str(Path(args.reference).resolve()); state.save_config()
    out({"project": str(state.root), "state": str(state_dir)})


def _node_version() -> str | None:
    try:
        return subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def cmd_doctor(args: Args) -> int | None:
    """Check every dependency and print a JSON report; exit 1 if something required is missing."""
    report: dict = {"pbridge": __version__}
    problems: list[str] = []
    state = ProjectState.open()
    report["project"] = str(state.root); report["state_dir"] = state.dir.exists()
    # local tools: Node.js + Chrome for capture, the built bundles for everything
    report["node"] = _node_version()
    chrome = [path for path in [os.environ.get("CHROME_PATH"), *CHROME_CANDIDATES] if path and Path(path).exists()]
    report["chrome"] = chrome[0] if chrome else None
    report["bundles_built"] = PLUGIN_RUNTIME.exists() and NODE_CLI.exists()
    if not report["node"]:
        problems.append("Node.js >= 20 not found (needed for capture): https://nodejs.org")
    if not report["chrome"]:
        problems.append("Chrome/Chromium not found: install it or set CHROME_PATH")
    if not report["bundles_built"]:
        problems.append("JS bundles missing: run `npm --prefix js ci && npm --prefix js run build` in the repository")
    # Penpot: MCP server, then the plugin in the browser tab
    try:
        url = discover_mcp_url(state); report["mcp_url"] = redact(url)
        client = MCPClient(url); report["server"] = client.connect(); report["tools"] = client.list_tools()
        bridge = Bridge(state)
        started = time.time()
        report["prelude_injected_now"] = bridge.ensure_prelude()
        report["roundtrip_ms"] = round((time.time() - started) * 1000)
        report["plugin"] = bridge.exec(PLUGIN_INFO_JS)
    except Exception as error:
        message = redact(str(error))[:300]
        report["penpot_error"] = message
        problems.append("Penpot not reachable: " + message + " (see docs/penpot-setup.md)")
    report["assets_cached"] = len(state.load_json("assets.json", {}))
    report["reference"] = state.config.get("reference")
    report["problems"] = problems
    out(report)
    return 1 if problems else None


def cmd_prelude(args: Args) -> None:
    bridge = get_bridge(args)
    out({"injected": bridge.ensure_prelude(force=args.force), "version": bridge.version})


def cmd_selftest(args: Args) -> int:
    """Regression suite: every bug ever fixed gets a test in tests/."""
    if not has_source_checkout():
        raise SystemExit("selftest runs from a source checkout: git clone the repository, then `uv sync` and `./pb selftest`")
    os.environ["PB_SELFTEST_CAPTURE"] = "0" if args.no_capture else "1"
    os.environ["PB_SELFTEST_BUILD"] = "1" if args.build else "0"
    suite = unittest.defaultTestLoader.discover(str(TESTS_DIR), pattern="test_*.py", top_level_dir=str(SOURCE_ROOT))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


# ---------------------------------------------------------------------- parsers
def add_init(subparsers) -> None:
    parser = subparsers.add_parser("init", help="create .pbridge state in a project dir")
    parser.add_argument("dir", nargs="?", help="project folder (default: current folder)")
    parser.add_argument("--reference", help="reference PNG to compare renders with (set automatically by `pb capture`)")
    parser.set_defaults(handler=cmd_init)


def add_doctor(subparsers) -> None:
    parser = subparsers.add_parser("doctor", help="check MCP server, plugin, prelude, chrome")
    parser.set_defaults(handler=cmd_doctor)


def add_prelude(subparsers) -> None:
    parser = subparsers.add_parser("prelude", help="(re)inject the plugin runtime")
    parser.add_argument("--force", action="store_true", help="inject even if the current runtime version is already loaded")
    parser.set_defaults(handler=cmd_prelude)


def add_selftest(subparsers) -> None:
    parser = subparsers.add_parser("selftest", help="run regression tests (unit + local fixture capture/convert)")
    parser.add_argument("--no-capture", action="store_true", help="skip the fixture capture (no Chrome / network needed)")
    parser.add_argument("--build", action="store_true", help="also build+compare the fixture in Penpot (scratch board, removed after)")
    parser.set_defaults(handler=cmd_selftest)


PARSERS = {"init": add_init, "doctor": add_doctor, "prelude": add_prelude, "selftest": add_selftest}
