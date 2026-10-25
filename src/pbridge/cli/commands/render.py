"""Export shapes to files: export (one settled PNG/SVG, or batches at several scales and formats)."""
from __future__ import annotations

import base64
import re
from pathlib import Path

from pbridge.cli.support import TARGET_HELP, Args, get_bridge, out, resolve_target
from pbridge.connection import Exporter

EXTENSIONS = {"png": "png", "jpeg": "jpg", "webp": "webp", "svg": "svg", "pdf": "pdf"}


def _file_name(name: str, scale: float, fmt: str) -> str:
    """'Hero / Icon' at 2x png -> 'Hero-Icon@2x.png' (the usual asset naming)."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "shape"
    suffix = "" if scale == 1 else f"@{scale:g}x"
    return f"{safe}{suffix}.{EXTENSIONS[fmt]}"


def cmd_export(args: Args) -> None:
    bridge = get_bridge(args)
    scales = [float(scale) for scale in args.scale.split(",")] if args.scale else [1.0]
    targets = args.targets or ["page"]
    if len(targets) == 1 and scales == [1.0] and args.format in ("png", "svg"):
        # one shape: MCP export, repeated until two renders are identical (fonts and images loaded)
        shape_id = resolve_target(bridge, targets[0])
        exported = Exporter(bridge).export(shape_id, args.format, Path(args.out) if args.out else None, settle=not args.fast)
        out({"file": str(exported), "bytes": exported.stat().st_size})
        return
    # batch: Penpot's exporter inside the plugin, any scale / format, files named <layer>@<scale>x.<ext>
    folder = Path(args.out) if args.out else bridge.state.path("exports", "x").parent
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for target in targets:
        shape_id = resolve_target(bridge, target)
        for scale in scales:
            exported = bridge.exec("return await pb.exportShape(DATA.id, DATA.type, DATA.scale);",
                                   data={"id": shape_id, "type": args.format, "scale": scale}, timeout=300)
            path = folder / _file_name(exported["name"], scale, args.format)
            path.write_bytes(base64.b64decode(exported["base64"]))
            files.append({"file": str(path), "bytes": path.stat().st_size})
    out({"folder": str(folder), "files": files}, args)


def add_export(subparsers) -> None:
    parser = subparsers.add_parser("export", help="export shapes to PNG/JPEG/WebP/SVG/PDF (batches, @2x/@3x)")
    parser.add_argument("targets", nargs="*", help=TARGET_HELP + " (default: page; several allowed)")
    parser.add_argument("--format", default="png", choices=["png", "jpeg", "webp", "svg", "pdf"])
    parser.add_argument("--scale", help="comma list of scales, e.g. 1,2,3 (files get @2x/@3x suffixes)")
    parser.add_argument("--out", help="output file (single export) or folder (batch; default .pbridge/exports/)")
    parser.add_argument("--fast", action="store_true", help="export once instead of waiting for two identical renders")
    parser.set_defaults(handler=cmd_export)


PARSERS = {"export": add_export}
