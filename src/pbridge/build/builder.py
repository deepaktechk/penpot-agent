"""Build a spec into Penpot: keyed, idempotent, incremental.

* Keyed: every node has a key; `.pbridge/idmap.json` maps key -> shape id of the last build.
* Idempotent: rebuilding a section first removes the shapes it created last time, and a full
  build removes sections the new spec no longer has (no debris on the canvas).
* Incremental: the plugin kills any task after ~120 s, so big sections are built as a board
  shell followed by batches of at most BATCH_NODES nodes per call.
* All waiting (range verification, text fitting) happens here in Python between short
  calls - never inside the plugin, where background-tab timers run about once a minute.

Spec coordinates are relative to the page board; they are shifted to absolute canvas
coordinates before building. `.pbridge/boxes.json` keeps the page-relative target boxes
for audit/autofix.
"""
from __future__ import annotations

import copy
import time
from collections.abc import Callable
from typing import Any

from pbridge.assets.store import AssetStore
from pbridge.build.spec_tree import Node, assign_keys, flatten, node_box, offset_nodes
from pbridge.connection import Bridge

REMOVE_JS = "const shape = pb.byId(DATA); if (shape) shape.remove(); return 1;"
BUILD_JS = "return pb.buildMany(DATA.n, DATA.p);"          # DATA.n: nodes, DATA.p: parent id
PARENT_ORIGIN_JS = "const parent = DATA ? pb.byId(DATA) : null; return parent ? [parent.x, parent.y] : [0, 0];"


class SpecBuilder:
    BATCH_NODES = 60   # max nodes per plugin call (server kills tasks after ~120 s)

    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.state = bridge.state
        self.assets = AssetStore(bridge)

    # ------------------------------------------------------------------ public
    def build(self, spec: dict | list, parent: str | None = None, only: list[str] | None = None, replace: bool = True,
              progress: Callable[[str], Any] = print, default_font: str | None = None) -> dict[str, Any]:
        """Build top-level spec nodes (sections) under `parent`. Returns a build report.

        only: section keys or names to (re)build; replace=False keeps previously built shapes.
        """
        nodes = spec["nodes"] if isinstance(spec, dict) else spec
        nodes = assign_keys(nodes)
        if only:
            nodes = [node for node in nodes if node["key"] in only or node.get("name") in only]
        self._upload_images(spec, nodes, progress)
        if default_font:
            self.bridge.exec("pb.defaultFont = DATA; return 1;", data=default_font)
        idmap = self.state.load_json("idmap.json", {})
        boxes = self.state.load_json("boxes.json", {})
        report: dict[str, Any] = {"built": 0, "warnings": [], "failed": [], "removed_stale": []}
        if replace and not only:
            report["removed_stale"] = self._remove_stale_sections(nodes, idmap, boxes)
        origin_x, origin_y = self.bridge.exec(PARENT_ORIGIN_JS, data=parent) if parent else [0, 0]
        if origin_x or origin_y:
            nodes = offset_nodes(copy.deepcopy(nodes), origin_x, origin_y)
        for section in nodes:
            started = time.time()
            if replace:
                self._forget_section(section["key"], idmap, boxes)
            try:
                result = self._build_node(section, parent, report)
            except Exception as error:
                report["failed"].append({"key": section["key"], "name": section.get("name"), "error": str(error)[:400]})
                progress(f"  ✗ {section['key']} {section.get('name', '')}: {str(error)[:200]}")
                continue
            idmap.update(result["ids"])
            for node in flatten([section]):
                box = node_box(node)
                if box and node["key"] in result["ids"]:
                    boxes[node["key"]] = {"box": [box[0] - origin_x, box[1] - origin_y, box[2], box[3]],
                                          "name": node.get("name"), "t": node["t"]}
            report["built"] += 1
            report["warnings"] += result.get("warnings", [])
            progress(f"  ✓ {section['key']} {section.get('name', '')[:40]} ({len(result['ids'])} shapes, {time.time() - started:.1f}s)")
        self.state.save_json("idmap.json", idmap)
        self.state.save_json("boxes.json", boxes)
        return report

    # ------------------------------------------------------------------ bookkeeping
    def _upload_images(self, spec: dict | list, nodes: list[Node], progress: Callable[[str], Any]) -> None:
        """Upload images the nodes need that are not cached yet, then register all in the plugin."""
        images = spec.get("images", {}) if isinstance(spec, dict) else {}
        needed = {node["img"] for node in flatten(nodes)
                  if node.get("t") == "image" or (isinstance(node.get("fill"), dict) and node["fill"].get("img"))}
        missing = {key: images[key] for key in needed if key in images and not self.assets.get(key)}
        if missing:
            progress(f"uploading {len(missing)} images…")
            results = self.assets.many_urls(missing)
            failed = {key: value for key, value in results.items() if str(value).startswith("ERR")}
            if failed:
                progress(f"  {len(failed)} image uploads failed: {list(failed)[:5]}")
        if needed:
            self.assets.sync()

    @staticmethod
    def _purge_keys(section_key: str, idmap: dict, boxes: dict) -> None:
        """Drop a section key and all its descendant keys ("sec03", "sec03.1", ...) from the maps."""
        for key in [key for key in idmap if key == section_key or key.startswith(section_key + ".")]:
            idmap.pop(key, None); boxes.pop(key, None)

    def _remove_stale_sections(self, nodes: list[Node], idmap: dict, boxes: dict) -> list[str]:
        """Full build: sections from a previous build that the new spec no longer has are debris."""
        new_sections = {node["key"] for node in nodes}
        stale = [key for key in idmap if "." not in key and key not in new_sections]
        for key in stale:
            self.bridge.exec(REMOVE_JS, data=idmap[key])
            self._purge_keys(key, idmap, boxes)
        return stale

    def _forget_section(self, key: str, idmap: dict, boxes: dict) -> None:
        """Remove the shapes of the previous build of this section and purge its keys."""
        if key in idmap:
            self.bridge.exec(REMOVE_JS, data=idmap[key])
        self._purge_keys(key, idmap, boxes)

    # ------------------------------------------------------------------ plugin calls
    def _post(self, result: dict, key: str, report: dict) -> None:
        """Post-build passes: verify text ranges stuck, then fit text widths (two phases)."""
        if result.get("ranges"):
            verification: dict = {}
            for attempt in range(4):
                time.sleep(0.25 + 0.25 * attempt)
                verification = self.bridge.exec("return pb.verifyRanges(pb._ranges);", timeout=300)
                if not verification.get("fixed"):
                    break
            if verification.get("fixed"):
                report["warnings"].append(f"{key}: {len(verification.get('bad', []))} text ranges still re-applying")
        if result.get("fit"):
            time.sleep(0.3)
            self.bridge.exec("return pb.fitTexts(pb._fit, 1);", timeout=300)
            time.sleep(0.3)
            self.bridge.exec("return pb.fitTexts(pb._fit, 2);", timeout=300)

    def _build_batch(self, nodes: list[Node], parent: str | None) -> dict:
        return self.bridge.exec(BUILD_JS, data={"n": nodes, "p": parent}, timeout=600)

    def _build_node(self, node: Node, parent: str | None, report: dict) -> dict:
        """Build one node; boards/groups with many descendants are built incrementally
        (shell first, then children in batches) so no single call runs too long."""
        size = len(flatten([node]))
        if size <= self.BATCH_NODES or node.get("t") not in ("board", "group") or not node.get("children"):
            result = self._build_batch([{**node, "tag": node.get("tag", node.get("key"))}], parent)
            self._post(result, node["key"], report)
            return result
        if node["t"] == "group":
            return {"ids": self._build_group_incremental(node, parent, report)}
        return {"ids": self._build_board_incremental(node, parent, report)}

    def _build_board_incremental(self, board: Node, parent: str | None, report: dict) -> dict:
        ids: dict = {}
        shell = {key: value for key, value in board.items() if key != "children"}
        shell["children"] = []; shell["tag"] = board.get("key")
        result = self._build_batch([shell], parent)
        ids.update(result["ids"]); board_id = result["ids"][board["key"]]
        batch: list[Node] = []
        batch_size = 0

        def flush() -> None:
            nonlocal batch, batch_size
            if not batch:
                return
            batch_result = self._build_batch(batch, board_id)
            self._post(batch_result, board["key"], report); ids.update(batch_result["ids"]); batch, batch_size = [], 0

        for child in board["children"]:
            child_size = len(flatten([child]))
            if child_size > self.BATCH_NODES and child.get("t") in ("board", "group") and child.get("children"):
                flush()
                if child["t"] == "group":   # big group: build its children, then group them
                    ids.update(self._build_group_incremental(child, board_id, report))
                else:
                    ids.update(self._build_node(child, board_id, report)["ids"])
                continue
            if batch_size + child_size > self.BATCH_NODES:
                flush()
            batch.append(child); batch_size += child_size
        flush()
        return ids

    def _build_group_incremental(self, group: Node, parent: str | None, report: dict) -> dict:
        """Build a big group's children one by one, then group the results."""
        ids: dict = {}
        child_ids = []
        for child in group["children"]:
            result = self._build_node(child, parent, report)
            ids.update(result["ids"])
            if child.get("key") in result["ids"]:
                child_ids.append(result["ids"][child["key"]])
        if child_ids:
            group_id = self.bridge.exec("return pb.groupShapes(DATA.ids, DATA.name);",
                                        data={"ids": child_ids, "name": group.get("name", "Group")})
            if group_id:
                ids[group["key"]] = group_id
        return ids
