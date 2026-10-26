"""Build a spec into Penpot: keyed, idempotent, incremental.

* Keyed: every node has a key; `.pbridge/idmap.json` maps key -> shape id of the last build.
* Idempotent: rebuilding a section first removes the shapes it created last time, and a full
  build removes sections the new spec no longer has (no debris on the canvas).
* Incremental: the plugin kills any task after ~120 s, so big sections are built as a board
  shell followed by packed batches (`plan.pack_batches`: by shape count and request bytes).
* Skips unchanged sections: a section whose content hash (`plan.section_hash`) matches the
  last build and whose shapes still exist is kept as is (`rebuild_all=True` forces a rebuild).
  idmap/boxes/hashes are saved after every section, so a crashed build resumes.
* Text post-passes (range verification, width fitting) run once per build, over every text
  built, from Python with short pauses between calls - never inside the plugin, where
  background-tab timers run about once a minute.

Spec coordinates are relative to the page board; they are shifted to absolute canvas
coordinates before building. `.pbridge/boxes.json` keeps the page-relative target boxes
for audit/autofix.
"""
from __future__ import annotations

import copy
import json
import time
from collections.abc import Callable
from typing import Any

from pbridge.assets.store import AssetStore
from pbridge.build.plan import node_cost, pack_batches, section_hash
from pbridge.build.spec_tree import Node, assign_keys, flatten, node_box, offset_nodes
from pbridge.connection import Bridge

REMOVE_JS = "return pb.removeMany(DATA);"                  # DATA: shape ids
BUILD_JS = "return pb.buildMany(DATA.n, DATA.p);"          # DATA.n: nodes, DATA.p: parent id
PARENT_ORIGIN_JS = "const parent = DATA ? pb.byId(DATA) : null; return parent ? [parent.x, parent.y] : [0, 0];"


class SpecBuilder:
    MAX_BATCH_NODES = 250        # shapes per plugin call (~10-40 ms each; tasks die after ~120 s)
    MAX_BATCH_BYTES = 400_000    # JSON per call (sent in ~60 KB chunks above ~88 KB)

    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.state = bridge.state
        self.assets = AssetStore(bridge)
        self._fit_items: list = []
        self._range_items: list = []

    # ------------------------------------------------------------------ public
    def build(self, spec: dict | list, parent: str | None = None, only: list[str] | None = None, replace: bool = True,
              progress: Callable[[str], Any] = print, default_font: str | None = None,
              rebuild_all: bool = False) -> dict[str, Any]:
        """Build top-level spec nodes (sections) under `parent`. Returns a build report.

        only: section keys or names to (re)build; replace=False keeps previously built shapes.
        rebuild_all: also rebuild sections whose content did not change since the last build.
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
        hashes = self.state.load_json("section_hashes.json", {})
        report: dict[str, Any] = {"built": 0, "skipped": [], "warnings": [], "failed": [], "removed_stale": []}
        origin_x, origin_y = self.bridge.exec(PARENT_ORIGIN_JS, data=parent) if parent else [0, 0]
        context = {"font": default_font, "parent": parent, "origin": [origin_x, origin_y], "runtime": self.bridge.version}
        section_hashes = {node["key"]: section_hash(node, context) for node in nodes}
        unchanged = set() if (rebuild_all or not replace) else self._unchanged_sections(nodes, section_hashes, hashes, idmap)
        to_remove: list[str] = []
        if replace and not only:
            stale = [key for key in idmap if "." not in key and key not in section_hashes]
            to_remove += [idmap[key] for key in stale]
            for key in stale:
                self._purge_keys(key, idmap, boxes); hashes.pop(key, None)
            report["removed_stale"] = stale
        if replace:   # previous builds of the sections built now: removed in one call
            for node in nodes:
                if node["key"] not in unchanged and node["key"] in idmap:
                    to_remove.append(idmap[node["key"]])
                if node["key"] not in unchanged:
                    self._purge_keys(node["key"], idmap, boxes); hashes.pop(node["key"], None)
        if to_remove:
            self.bridge.exec(REMOVE_JS, data=to_remove, idempotent=True)
        if origin_x or origin_y:
            nodes = offset_nodes(copy.deepcopy(nodes), origin_x, origin_y)
        self._fit_items, self._range_items = [], []
        for section in nodes:
            if section["key"] in unchanged:
                report["skipped"].append(section["key"])
                progress(f"  = {section['key']} {section.get('name', '')[:40]} (unchanged)")
                continue
            started = time.time()
            try:
                result = self._build_node(section, parent)
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
            hashes[section["key"]] = section_hashes[section["key"]]
            report["built"] += 1
            report["warnings"] += result.get("warnings", [])
            # saved after every section: a crashed build resumes with the sections done so far
            self.state.save_json("idmap.json", idmap)
            self.state.save_json("boxes.json", boxes)
            self.state.save_json("section_hashes.json", hashes)
            progress(f"  ✓ {section['key']} {section.get('name', '')[:40]} ({len(result['ids'])} shapes, {time.time() - started:.1f}s)")
        self._post_texts(report)
        self.state.save_json("idmap.json", idmap)
        self.state.save_json("boxes.json", boxes)
        self.state.save_json("section_hashes.json", hashes)
        return report

    # ------------------------------------------------------------------ bookkeeping
    def _unchanged_sections(self, nodes: list[Node], section_hashes: dict, hashes: dict, idmap: dict) -> set[str]:
        """Sections whose hash matches the last build and whose board/group still exists in Penpot."""
        candidates = {node["key"] for node in nodes
                      if hashes.get(node["key"]) == section_hashes[node["key"]] and node["key"] in idmap}
        if not candidates:
            return set()
        alive = set(self.bridge.exec("return pb.existing(DATA);", data=[idmap[key] for key in candidates]))
        return {key for key in candidates if idmap[key] in alive}

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

    # ------------------------------------------------------------------ plugin calls
    def _post_texts(self, report: dict) -> None:
        """Once per build, over every text built: verify range styles stuck, then fit text widths."""
        if self._range_items:
            verification: dict = {}
            for attempt in range(4):
                time.sleep(0.25 + 0.25 * attempt)
                verification = self.bridge.exec("return pb.verifyRanges(DATA);", data=self._range_items, timeout=300)
                if not verification.get("fixed"):
                    break
            if verification.get("fixed"):
                report["warnings"].append(f"{len(verification.get('bad', []))} text ranges still re-applying")
        if self._fit_items:
            time.sleep(0.3)
            self.bridge.exec("return pb.fitTexts(DATA, 1);", data=self._fit_items, timeout=300)
            time.sleep(0.3)
            self.bridge.exec("return pb.fitTexts(DATA, 2);", data=self._fit_items, timeout=300)

    def _build_batch(self, nodes: list[Node], parent: str | None) -> dict:
        result = self.bridge.exec(BUILD_JS, data={"n": nodes, "p": parent}, timeout=600)
        self._fit_items += result.pop("fitItems", None) or []
        self._range_items += result.pop("rangeItems", None) or []
        return result

    def _fits_one_batch(self, node: Node) -> bool:
        return node_cost(node) <= self.MAX_BATCH_NODES and len(json.dumps(node, separators=(",", ":"))) <= self.MAX_BATCH_BYTES

    def _build_node(self, node: Node, parent: str | None) -> dict:
        """Build one node; boards/groups too big for one call are built incrementally
        (board: shell first, then packed batches of children; group: children, then grouped)."""
        if self._fits_one_batch(node) or node.get("t") not in ("board", "group") or not node.get("children"):
            return self._build_batch([{**node, "tag": node.get("tag", node.get("key"))}], parent)
        if node["t"] == "group":
            return {"ids": self._build_group_incremental(node, parent)}
        return {"ids": self._build_board_incremental(node, parent)}

    def _build_children(self, children: list[Node], parent_id: str | None) -> dict:
        """Build children in order under parent_id: packed batches, oversized containers recursively."""
        ids: dict = {}
        pending: list[Node] = []

        def flush() -> None:
            for batch in pack_batches(pending, self.MAX_BATCH_NODES, self.MAX_BATCH_BYTES):
                ids.update(self._build_batch(batch, parent_id)["ids"])
            pending.clear()

        for child in children:
            if not self._fits_one_batch(child) and child.get("t") in ("board", "group") and child.get("children"):
                flush()
                ids.update(self._build_node(child, parent_id)["ids"])
            else:
                pending.append(child)
        flush()
        return ids

    def _build_board_incremental(self, board: Node, parent: str | None) -> dict:
        shell = {key: value for key, value in board.items() if key != "children"}
        shell["children"] = []; shell["tag"] = board.get("key")
        ids = dict(self._build_batch([shell], parent)["ids"])
        ids.update(self._build_children(board["children"], ids[board["key"]]))
        return ids

    def _build_group_incremental(self, group: Node, parent: str | None) -> dict:
        """Build a big group's children (packed), then group the results."""
        ids = self._build_children(group["children"], parent)
        child_ids = [ids[child["key"]] for child in group["children"] if child.get("key") in ids]
        if child_ids:
            group_id = self.bridge.exec("return pb.groupShapes(DATA.ids, DATA.name);",
                                        data={"ids": child_ids, "name": group.get("name", "Group")})
            if group_id:
                ids[group["key"]] = group_id
        return ids
