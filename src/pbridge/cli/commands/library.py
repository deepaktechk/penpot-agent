"""Design tokens: library (colors and typographies from the capture into the Penpot library)."""
from __future__ import annotations

import json
from pathlib import Path

from pbridge.cli.support import Args, get_bridge, out
from pbridge.library import extract_tokens, publish_tokens


def _font_map(text: str) -> dict[str, str]:
    """'Web Font=Penpot Font,...' -> {web: penpot}."""
    return dict(pair.split("=", 1) for pair in text.split(","))


def cmd_library(args: Args) -> None:
    bridge = get_bridge(args)
    capture_dir = Path(args.capture or bridge.state.config.get("capture", ""))
    layout = json.loads((capture_dir / "layout.json").read_text())
    colors, typographies = extract_tokens(layout, args.colors, args.types)
    if args.dry:
        out({"colors": colors, "typographies": typographies}); return
    published = publish_tokens(bridge, colors, typographies, args.prefix, args.font_map)
    out({"colors": len(published["colors"]), "typographies": len(published["typographies"])})


def add_library(subparsers) -> None:
    parser = subparsers.add_parser("library", help="extract colors/typographies from capture into Penpot library")
    parser.add_argument("--capture", help="capture folder (default: the current capture)")
    parser.add_argument("--colors", type=int, default=12, help="number of colours (default 12)")
    parser.add_argument("--types", type=int, default=12, help="number of text styles (default 12)")
    parser.add_argument("--prefix", default="Site", help="library group name (default Site)")
    parser.add_argument("--dry", action="store_true", help="only print what would be created")
    parser.add_argument("--font-map", type=_font_map, help="Web Font=Penpot Font,...")
    parser.set_defaults(handler=cmd_library)


PARSERS = {"library": add_library}
