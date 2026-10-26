"""SpecBuilder against a fake bridge (no Penpot): which plugin calls a build makes, and with what."""
import tempfile
import unittest
from pathlib import Path

from pbridge.build import SpecBuilder
from pbridge.project import ProjectState


class FakeBridge:
    """Answers `exec` by the JS it is given; records every call as (first line of code, data)."""

    version = "test-runtime"

    def __init__(self, state: ProjectState, page_shapes: int = 0):
        self.state = state
        self.page_shapes = page_shapes
        self.calls: list[tuple[str, object]] = []
        self.next_id = 0

    def _new_id(self) -> str:
        self.next_id += 1
        return f"shape-{self.next_id}"

    def _ids(self, node: dict, ids: dict) -> dict:
        ids[node["key"]] = self._new_id()
        for child in node.get("children", []):
            self._ids(child, ids)
        return ids

    def exec(self, body: str, data=None, timeout=None, idempotent=False):
        self.calls.append((body.strip().splitlines()[0], data))
        if "pb.buildMany" in body:
            ids: dict = {}
            for node in data["n"]:
                self._ids(node, ids)
            pins = [{"board": ids[node["key"]], "box": [node["x"], node["y"], node["w"], node["h"]], "layout": node["layout"],
                     "flow": [[ids[child["key"]], child["x"], child["y"], child["w"], child["h"], child["child"]]
                              for child in node["children"] if not child["child"].get("absolute")],
                     "absolute": [[ids[child["key"]], child["x"], child["y"]] for child in node["children"] if child["child"].get("absolute")]}
                    for top in data["n"] for node in self._flatten(top) if node.get("layout")]
            result = {"built": len(data["n"]), "ids": ids, "warnings": [], "fitItems": [], "rangeItems": [], "pinItems": pins}
            if "pb.stageBegin" in body:
                result["begin"] = {"page": "staging", "previous": "target"}
                result["staged"] = {"component": "component-" + data["key"], "order": list(ids.values()), "x": 0, "y": 0}
            return result
        if "findShapes({}).length" in body:
            return [self.page_shapes, "target"]
        if "pb.stageTransfer" in body:
            ids = {shape_id: "final-" + shape_id for item in data["items"] for shape_id in item["order"]}
            return {"ids": ids, "roots": [ids[item["order"][0]] for item in data["items"]], "failed": []}
        if "pb.orderChildren" in body:
            return {"moves": 0, "ok": True}
        if "pb.existing" in body:
            return list(data)
        if "pb.layoutState" in body:    # Penpot put every flow child exactly at its spec box
            return [[[entry[3], entry[4], entry[1], entry[2]] for entry in item["flow"]] for item in data]
        return 0

    def _flatten(self, node: dict) -> list:
        return [node] + [descendant for child in node.get("children", []) for descendant in self._flatten(child)]

    def bodies(self, marker: str) -> list:
        return [data for code, data in self.calls if marker in code]


def section(key: str, children: int) -> dict:
    return {"t": "board", "key": key, "name": key, "x": 0, "y": 0, "w": 10, "h": 10,
            "children": [{"t": "rect", "x": 0, "y": 0, "w": 1, "h": 1} for _ in range(children)]}


class BuilderCalls(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.state = ProjectState.open(Path(self.folder.name))
        self.state.init()

    def tearDown(self):
        self.folder.cleanup()

    def build(self, spec: dict, page_shapes: int = 0, **options) -> FakeBridge:
        bridge = FakeBridge(self.state, page_shapes)
        SpecBuilder(bridge).build(spec, progress=lambda *message: None, **options)
        return bridge

    def test_only_rebuild_restores_the_order_of_all_sections(self):
        # 2026-10-26: `--only sec08` re-appended the Footer above the Nav: the order step only saw sec08
        spec = {"nodes": [section("a", 2), section("b", 2), section("c", 2)]}
        first = self.build(spec)
        idmap = self.state.load_json("idmap.json", {})
        second = self.build(spec, only=["b"], rebuild_all=True)   # as `pb build --only b` does
        self.assertEqual(second.bodies("pb.orderChildren")[-1], [idmap["a"], self.state.load_json("idmap.json", {})["b"], idmap["c"]])
        self.assertTrue(first.bodies("pb.orderChildren"))

    def test_big_section_on_a_full_page_is_staged_and_ids_are_translated(self):
        spec = {"nodes": [section("small", 3), section("big", 200)]}
        bridge = self.build(spec, page_shapes=1400)
        staged_calls = [data for code, data in bridge.calls if "pb.stageBegin" in code]
        self.assertEqual([call["key"] for call in staged_calls], ["big"])
        idmap = self.state.load_json("idmap.json", {})
        self.assertTrue(idmap["big"].startswith("final-"))       # the copy on the target page, not the staged shape
        self.assertFalse(idmap["small"].startswith("final-"))
        self.assertEqual(bridge.bodies("pb.stageCleanup"), ["target"])

    def test_staged_flex_board_is_settled_on_the_final_shapes(self):
        # bug: the staging id translation still used the old pin item format and crashed every staged
        # `--layout auto` build ('children') before absolute children were placed
        flex = {"t": "board", "x": 0, "y": 0, "w": 300, "h": 40, "layout": {"type": "flex", "dir": "row", "gap": 10},
                "children": [{"t": "rect", "x": 0, "y": 0, "w": 300, "h": 40, "child": {"absolute": True}},
                             {"t": "rect", "x": 0, "y": 0, "w": 100, "h": 40, "child": {"sizing": ["fix", "fix"]}}]}
        big = section("big", 200)
        big["children"].append(flex)
        bridge = self.build({"nodes": [big]}, page_shapes=1400)
        placed = bridge.bodies("pb.placeAbsolute")
        self.assertEqual(len(placed), 1)
        self.assertTrue(placed[0][0][0].startswith("final-"))
        self.assertTrue(all(entry[0].startswith("final-") for item in bridge.bodies("pb.layoutState")[0] for entry in item["flow"]))

    def test_nothing_is_staged_on_an_almost_empty_page(self):
        bridge = self.build({"nodes": [section("a", 200)]}, page_shapes=10)
        self.assertFalse([code for code, _ in bridge.calls if "pb.stage" in code])

    def test_no_staging_option(self):
        bridge = self.build({"nodes": [section("a", 200)]}, page_shapes=1400, staged_build=False)
        self.assertFalse([code for code, _ in bridge.calls if "pb.stage" in code])


if __name__ == "__main__":
    unittest.main()
