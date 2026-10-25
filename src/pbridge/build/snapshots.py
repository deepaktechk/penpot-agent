"""Save a shape subtree to `.pbridge/snapshots/<label>.json` and rebuild it later (undo)."""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pbridge.build.spec_tree import Node

if TYPE_CHECKING:
    from pbridge.connection import Bridge


def snap_to_spec(serialized: Node) -> Node:
    """`pb.serialize()` output -> buildable spec node."""
    node_type = serialized.get("t")
    spec = {key: value for key, value in serialized.items() if key not in ("id", "children", "mainComponent")}
    if node_type == "text":
        text = serialized["text"]
        spec["text"] = {"text": text["text"], "font": text.get("font"), "weight": text.get("weight"), "size": text.get("size"),
                        "lhr": text.get("lhr"), "ls": text.get("ls"),
                        "color": text.get("color") if text.get("color") != "mixed" else "#000000",
                        "align": text.get("align"), "grow": text.get("grow")}
    if node_type == "path" and not serialized.get("d"):
        spec["t"] = "rect"            # path data not serialized: approximate with its box
    if serialized.get("children"):
        spec["children"] = [snap_to_spec(child) for child in serialized["children"]]
    return spec


class Snapshots:
    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.state = bridge.state

    def save(self, shape_id: str, label: str) -> Path:
        tree = self.bridge.exec("return pb.serialize(pb.byId(DATA), 99, {paths: true});", data=shape_id)
        snapshot_file = self.state.path("snapshots", f"{label}.json")
        snapshot_file.write_text(json.dumps({"id": shape_id, "time": time.time(), "tree": tree}, ensure_ascii=False))
        return snapshot_file

    def labels(self) -> list[str]:
        return sorted(path.stem for path in self.state.path("snapshots", "x").parent.glob("*.json"))

    def restore(self, label: str, parent: str | None = None) -> Any:
        """Rebuild a snapshot (vector/text/image/board) in place of the current shape."""
        snapshot = json.loads(self.state.path("snapshots", f"{label}.json").read_text())
        spec = snap_to_spec(copy.deepcopy(snapshot["tree"]))
        self.bridge.exec("const shape = pb.byId(DATA); if (shape) shape.remove(); return 1;", data=snapshot["id"])
        return self.bridge.exec("return pb.buildMany([DATA.n], DATA.p);", data={"n": spec, "p": parent}, timeout=600)
