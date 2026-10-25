"""Locations of the tool's own files (not project files - those live in project/state.py).

The JavaScript bundles are part of the Python package (built from js/src by
`npm --prefix js run build` and committed), so they are found the same way in a source
checkout and in an installed copy (`uv tool install`, `pip install`):

    src/pbridge/paths.py              <- this file
    src/pbridge/bundles/*.js          <- plugin runtime, page library, node CLI
    tests/                            <- regression suite (source checkout only)
"""
from __future__ import annotations

import shutil
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BUNDLES_DIR = PACKAGE_DIR / "bundles"
SOURCE_ROOT = PACKAGE_DIR.parents[1]              # repository root when running from a checkout
TESTS_DIR = SOURCE_ROOT / "tests"
JS_DIR = SOURCE_ROOT / "js"

PLUGIN_RUNTIME = BUNDLES_DIR / "plugin-runtime.js"   # injected into the Penpot plugin as `storage.pb`
NODE_CLI = BUNDLES_DIR / "node-cli.js"               # node: `capture` (screenshot + layout) and `rasterize` (SVG -> PNG)


def js_bundle(path: Path) -> Path:
    """Return a built JS bundle, or fail with the command that builds it."""
    if not path.exists():
        raise FileNotFoundError(f"{path.name} is missing: run `npm --prefix js ci && npm --prefix js run build` in the repository")
    return path


def node_command(tool: str) -> list[str]:
    """Command line prefix for a node CLI tool: ["node", ".../node-cli.js", tool]."""
    node = shutil.which("node")
    if not node:
        raise FileNotFoundError("Node.js (>= 20) is required for website capture and SVG rasterizing: https://nodejs.org")
    return [node, str(js_bundle(NODE_CLI)), tool]


def has_source_checkout() -> bool:
    """True when running from the git repository (tests and TypeScript sources available)."""
    return TESTS_DIR.is_dir() and JS_DIR.is_dir()
