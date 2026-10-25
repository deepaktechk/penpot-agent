"""Helpers shared by the command handlers: output, connection, target and region parsing."""
from __future__ import annotations

import argparse
import json
from typing import Any

from pbridge.connection import Bridge, Exporter
from pbridge.project import ProjectState

Args = argparse.Namespace
Region = tuple[int, int, int | None, int]   # (x0, y0, x1 | None for "full width", y1)

# how a command argument naming a shape is resolved (see resolve_target)
TARGET_HELP = "shape id, spec key (sec03.2.1), layer name or regex, 'page' or 'selection'"

FIND_ONE_JS = "const shape = pb.find({name: DATA})[0] || pb.find({re: DATA})[0]; return shape && shape.id;"


def out(result: Any, args: Args | None = None) -> None:
    """Print a result: JSON for dicts/lists (one line with -c/--compact), str() otherwise."""
    if isinstance(result, (dict, list)):
        compact = bool(args and getattr(args, "compact", False))
        print(json.dumps(result, indent=None if compact else 1, ensure_ascii=False, default=str))
    else:
        print(result)


def get_bridge(args: Args) -> Bridge:
    return Bridge(ProjectState.open(), verbose=getattr(args, "verbose", False))


def resolve_target(bridge: Bridge, target: str | None) -> str:
    """target: shape id | spec key | exact layer name or regex | 'page' (page board) | 'selection'."""
    state = bridge.state
    if not target or target == "page":
        return state.config.get("page_board") or bridge.exec("return penpot.root.id;")
    if target == "selection":
        return bridge.exec("return penpot.selection[0] && penpot.selection[0].id;")
    if len(target) == 36 and target.count("-") == 4:          # looks like a UUID
        return target
    idmap = state.load_json("idmap.json", {})
    if target in idmap:
        return idmap[target]
    shape_id = bridge.exec(FIND_ONE_JS, data=target)
    if not shape_id:
        raise SystemExit(f"target not found: {target}")
    return shape_id


def parse_region(text: str | None) -> Region | None:
    """'y0,y1' (full width) or 'x,y,w,h' -> (x0, y0, x1, y1); x1 is None for full width."""
    if not text:
        return None
    values = [float(value) for value in text.replace(" ", "").split(",")]
    if len(values) == 2:
        return (0, int(values[0]), None, int(values[1]))
    x, y, width, height = values
    return (int(x), int(y), int(x + width), int(y + height))


def full_region(region: Region | None, reference_path: str) -> tuple | None:
    """Resolve a full-width region against the reference image width."""
    if region and region[2] is None:
        from PIL import Image
        page_width = Image.open(reference_path).width
        return (0, region[1], page_width, region[3])
    return region


def reference_of(bridge: Bridge, args: Args) -> str | None:
    """--ref, else the project reference image (set by `pb capture` / `pb init --reference`)."""
    return getattr(args, "ref", None) or bridge.state.config.get("reference")


def require_reference(bridge: Bridge, args: Args | None = None) -> str:
    reference = reference_of(bridge, args or Args())
    if not reference:
        raise SystemExit("no reference image: pass --ref or `pb init --reference`")
    return reference


def render_for(bridge: Bridge, args: Args) -> str:
    """The render to judge: --render PATH, --render latest, or a fresh export of --target."""
    if getattr(args, "render", None):
        if args.render == "latest":
            latest = bridge.state.latest_render()
            if not latest:
                raise SystemExit("no renders yet")
            return str(latest)
        return args.render
    shape_id = resolve_target(bridge, getattr(args, "target", None) or "page")
    return str(Exporter(bridge).export(shape_id, "png", settle=not getattr(args, "fast", False)))
