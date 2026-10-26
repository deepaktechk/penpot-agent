"""Build planning (no Penpot): ordered batch packing and section content hashes."""
import json
import unittest

from pbridge.build.plan import node_cost, pack_batches, section_hash, shape_estimate, staging_saves_time


def text_node(key: str, text: str = "Hello") -> dict:
    return {"t": "text", "key": key, "x": 0, "y": 0, "w": 10, "h": 10, "text": {"text": text}}


class PackBatches(unittest.TestCase):
    def test_keeps_order_and_respects_the_node_limit(self):
        nodes = [text_node(f"n{i}") for i in range(10)]
        batches = pack_batches(nodes, max_nodes=4, max_bytes=10_000_000)
        self.assertEqual([len(batch) for batch in batches], [4, 4, 2])
        self.assertEqual([node["key"] for batch in batches for node in batch], [f"n{i}" for i in range(10)])

    def test_respects_the_byte_limit(self):
        nodes = [text_node(f"n{i}", "x" * 1000) for i in range(6)]
        one_node_bytes = len(json.dumps(nodes[0]))
        batches = pack_batches(nodes, max_nodes=100, max_bytes=one_node_bytes * 2 + 10)
        self.assertEqual([len(batch) for batch in batches], [2, 2, 2])

    def test_counts_descendants_not_just_top_level_nodes(self):
        group = {"t": "group", "key": "g", "children": [text_node(f"g.{i}") for i in range(5)]}
        batches = pack_batches([group, text_node("a"), text_node("b")], max_nodes=6, max_bytes=10_000_000)
        self.assertEqual([[node["key"] for node in batch] for batch in batches], [["g"], ["a", "b"]])

    def test_an_oversized_node_gets_a_batch_of_its_own(self):
        big = {"t": "rect", "key": "big", "x": 0, "y": 0, "w": 1, "h": 1, "pad": "y" * 5000}
        batches = pack_batches([text_node("a"), big, text_node("b")], max_nodes=100, max_bytes=2000)
        self.assertEqual([[node["key"] for node in batch] for batch in batches], [["a"], ["big"], ["b"]])

    def test_empty_input(self):
        self.assertEqual(pack_batches([], max_nodes=10, max_bytes=100), [])

    def test_cost_counts_every_descendant(self):
        tree = {"t": "board", "children": [{"t": "group", "children": [text_node("x"), text_node("y")]}]}
        self.assertEqual(node_cost(tree), 4)


class StagingCostModel(unittest.TestCase):
    """Measured 2026-10-26 (Clockify): a change costs ~0.032 ms more per shape on the page; a staged
    section costs ~1.5 s of page switching / component / transfer. Stage only when it saves time."""

    def test_shape_estimate_counts_the_shapes_an_svg_becomes(self):
        svg = {"t": "svg", "svg": "<svg><g><path d='M0'/><path d='M1'/><circle r='2'/></g><rect/></svg>"}
        self.assertEqual(shape_estimate({"t": "board", "children": [svg, text_node("a")]}), 1 + 1 + 5 + 1)

    def test_big_section_on_a_full_page_is_staged(self):
        # Footer: 161 shapes on a ~1240-shape page saved 5.9 s when staged
        self.assertTrue(staging_saves_time(161, 1240))

    def test_sections_on_an_almost_empty_page_are_built_in_place(self):
        self.assertFalse(staging_saves_time(161, 50))
        self.assertFalse(staging_saves_time(75, 3))

    def test_small_sections_are_built_in_place_even_on_a_full_page(self):
        self.assertFalse(staging_saves_time(20, 1400))


class SectionHash(unittest.TestCase):
    def test_same_content_same_hash_regardless_of_key_order(self):
        first = {"t": "board", "key": "sec01", "x": 0, "y": 10, "children": [text_node("sec01.0")]}
        second = json.loads(json.dumps(first, sort_keys=True))
        self.assertEqual(section_hash(first, {"font": "Inter"}), section_hash(second, {"font": "Inter"}))

    def test_any_change_in_the_subtree_or_the_build_context_changes_the_hash(self):
        section = {"t": "board", "key": "sec01", "children": [text_node("sec01.0", "Hello")]}
        changed = {"t": "board", "key": "sec01", "children": [text_node("sec01.0", "Hello!")]}
        self.assertNotEqual(section_hash(section, {}), section_hash(changed, {}))
        self.assertNotEqual(section_hash(section, {"font": "Inter"}), section_hash(section, {"font": "HumanSans"}))


if __name__ == "__main__":
    unittest.main()
