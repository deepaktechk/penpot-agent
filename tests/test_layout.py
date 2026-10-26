"""`--layout auto` (convert/layout.py): the Penpot flex simulator against measured Penpot positions,
and the encoder on small pages. Every emitted layout must put each child exactly where the
absolute build would (`assert_layouts_exact`)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pbridge.convert import Converter
from pbridge.convert.layout import layout_errors, settle_correction, simulate
from pbridge.paths import TESTS_DIR
from pbridge.project import ProjectState
from pbridge.workflows import resolve_layout

CONFORMANCE = json.loads((TESTS_DIR / "fixtures" / "penpot_layout_conformance.json").read_text())["cases"]


def layout(elements, width=1200, height=900):
    return {"url": "https://example.com/", "width": width, "height": height, "elements": elements}


def box_el(index, parent, rect, background="rgb(200, 200, 200)", tag="div", **extra):
    """A captured element painting a plain background box (becomes a rect node)."""
    return {"i": index, "p": parent, "tag": tag, "r": rect, "op": 1,
            "box": {"bg": background, "bw": [0, 0, 0, 0], "bs": ["none"] * 4, "bc": ["rgb(0,0,0)"] * 4, "radius": ["0px"] * 4}, **extra}


def flex_css(direction="row", justify="normal", align="normal", gap=(0, 0), inset=(0, 0, 0, 0), wrap="nowrap"):
    return {"d": "flex", "dir": direction, "wrap": wrap, "jc": justify, "ai": align, "gap": list(gap), "inset": list(inset)}


def convert(elements, mode="auto"):
    return Converter(layout(elements), {"layout": mode, "snap": True}).convert()


def all_nodes(nodes):
    flat = []
    for node in nodes:
        flat.append(node)
        flat += all_nodes(node.get("children", []))
    return flat


def layout_boards(spec):
    return [node for node in all_nodes(spec["nodes"]) if node.get("layout")]


def assert_layouts_exact(test, spec):
    """Every flow child of every layout board sits where Penpot's rules put it (0.02 px)."""
    test.assertEqual(layout_errors(spec["nodes"]), [])


class PenpotConformance(unittest.TestCase):
    """simulate() == what Penpot did, for every flex encoding pb emits (measured, see the fixture)."""

    def emitted_cases(self):
        for case in CONFORMANCE:
            built = {**case["layout"], **case.get("penpot_layout", {})}
            if built["type"] != "flex" or built.get("wrap") or built["dir"].endswith("reverse"):
                continue                     # pb never emits reverse, wrapping or grid layouts
            if any(child.get("absolute") for child in case["children"]):
                continue                     # absolute children keep their x/y (builder test)
            yield case, built

    def test_simulator_matches_measured_penpot_positions(self):
        checked = 0
        for case, built in self.emitted_cases():
            order = case.get("order") or list(range(len(case["children"])))
            children = [case["children"][index] for index in order]
            sizes = [(child["w"], child["h"]) for child in children]
            props = [{key: child[key] for key in ("margin", "alignSelf") if key in child} for child in children]
            positions = simulate(built, (0, 0, case["w"], case["h"]), sizes, props)
            for index, (x, y) in zip(order, positions):
                measured = case["penpot"][index]
                self.assertAlmostEqual(x, measured[0], delta=0.02, msg=case["id"])
                self.assertAlmostEqual(y, measured[1], delta=0.02, msg=case["id"])
            checked += 1
        self.assertGreater(checked, 60)

    def test_overflowing_align_self_child_goes_to_the_start(self):
        # pumble.com testimonials: a 417 px row in a 289 px room, align-self center -> Penpot put it at the start
        # (64 px lower than Chrome), so the encoder must not use align-self there
        case = next(case for case in CONFORMANCE if case["id"] == "overflow/self-center")
        self.assertNotEqual(case["penpot"][0][1], case["chrome"][0][1])
        elements = [box_el(0, -1, [0, 0, 1920, 417], tag="section", lay=flex_css(align="flex-start", inset=(64, 0, 64, 0))),
                    box_el(1, 0, [0, 0, 1920, 417])]
        spec = convert(elements)
        assert_layouts_exact(self, spec)
        for board in layout_boards(spec):
            for child in board["children"]:
                self.assertNotIn(child["child"].get("alignSelf"), ("center", "end"))

    def test_penpot_ignores_the_gap_in_space_around(self):
        # measured: Penpot distributes (content - sizes) and drops the gap; Chrome keeps it -> pb avoids that encoding
        case = next(case for case in CONFORMANCE if case["id"] == "row/space-around/start")
        self.assertNotAlmostEqual(case["penpot"][0][0], case["chrome"][0][0], delta=1)


class Encoder(unittest.TestCase):
    def test_absolute_mode_is_unchanged(self):
        elements = [box_el(0, -1, [0, 0, 600, 100], tag="nav", lay=flex_css(gap=(0, 20))),
                    box_el(1, 0, [0, 30, 100, 40]), box_el(2, 0, [120, 30, 100, 40]), box_el(3, 0, [240, 30, 100, 40])]
        spec = convert(elements, mode="absolute")
        self.assertFalse(layout_boards(spec))
        self.assertFalse([node for node in all_nodes(spec["nodes"]) if any(key.startswith("_") for key in node)])

    def test_css_flex_row_is_encoded_as_is(self):
        elements = [box_el(0, -1, [0, 0, 600, 100], tag="nav", lay=flex_css(justify="center", align="center", gap=(0, 20))),
                    box_el(1, 0, [130, 30, 100, 40]), box_el(2, 0, [250, 30, 100, 40]), box_el(3, 0, [370, 30, 100, 40])]
        spec = convert(elements)
        boards = layout_boards(spec)
        self.assertEqual(len(boards), 1)
        self.assertEqual({key: boards[0]["layout"][key] for key in ("dir", "gap", "justify", "align", "pin")},
                         {"dir": "row", "gap": 20, "justify": "center", "align": "center", "pin": True})
        assert_layouts_exact(self, spec)

    def test_own_background_stays_below_the_flow(self):
        # bug: the box paint was listed last on the belief that flex boards layer appended children
        # bottom-up (parentIndex says so); Penpot paints them in append order, so the background covered
        # every image (pumble.com mockups). Spec order of a flex board = paint order, bottom first.
        elements = [box_el(0, -1, [0, 0, 600, 100], tag="nav", lay=flex_css(gap=(0, 20))),
                    box_el(1, 0, [0, 0, 100, 40]), box_el(2, 0, [120, 0, 100, 40])]
        board = layout_boards(convert(elements))[0]
        self.assertTrue(board["children"][0]["child"]["absolute"])
        self.assertEqual([child["x"] for child in board["children"][1:]], [0, 120])

    def test_block_stack_becomes_a_column_with_margins(self):
        elements = [box_el(0, -1, [0, 0, 400, 300], tag="section"),
                    box_el(1, 0, [20, 10, 300, 40]), box_el(2, 0, [20, 66, 200, 30]), box_el(3, 0, [40, 120, 100, 50])]
        spec = convert(elements)
        board = layout_boards(spec)[0]
        self.assertEqual(board["layout"]["dir"], "column")
        assert_layouts_exact(self, spec)

    def test_space_around_with_a_gap_is_not_used(self):
        # Penpot ignores the gap in space-around (measured): the same positions are encoded another way
        elements = [box_el(0, -1, [0, 0, 520, 100], tag="nav", lay=flex_css(justify="space-around", gap=(0, 12))),
                    box_el(1, 0, [40.08, 0, 80, 40]), box_el(2, 0, [202.25, 0, 120, 40]), box_el(3, 0, [404.92, 0, 60, 40])]
        spec = convert(elements)
        for board in layout_boards(spec):
            self.assertNotEqual(board["layout"]["justify"], "space-around")
        assert_layouts_exact(self, spec)

    def test_reverse_row_is_built_forward(self):
        # Penpot's reverse puts "start" at the physical start (measured): children are ordered physically instead
        elements = [box_el(0, -1, [0, 0, 600, 100], tag="nav", lay=flex_css(direction="row-reverse", gap=(0, 10))),
                    box_el(1, 0, [500, 0, 100, 40]), box_el(2, 0, [390, 0, 100, 40])]
        spec = convert(elements)
        board = layout_boards(spec)[0]
        self.assertEqual((board["layout"]["dir"], board["layout"]["justify"]), ("row", "end"))
        self.assertEqual([child["x"] for child in board["children"] if not child["child"].get("absolute")], [390, 500])
        assert_layouts_exact(self, spec)

    def test_no_group_is_a_direct_child_of_a_flex_board(self):
        # bug: a group's children are built into its parent before grouping; in a flex board they were
        # flowed into one row first (pumble.com "Free Forever": a checklist spread over 1131 px)
        elements = [box_el(0, -1, [0, 0, 900, 300], tag="section", lay=flex_css(justify="center", align="center", gap=(0, 40))),
                    box_el(1, 0, [100, 50, 300, 200]),
                    {"i": 2, "p": 0, "tag": "div", "r": [440, 50, 200, 200], "op": 1},
                    box_el(3, 2, [440, 50, 200, 40]), box_el(4, 2, [440, 100, 200, 40]), box_el(5, 2, [440, 150, 200, 40])]
        spec = convert(elements)
        self.assertTrue(layout_boards(spec))
        for board in layout_boards(spec):
            self.assertFalse([child for child in board["children"] if child["t"] == "group"])
        assert_layouts_exact(self, spec)

    def test_shapes_settled_by_the_plugin_stay_absolute(self):
        # a contain-fitted picture is smaller than its box in Penpot, a fitted symbol line is moved after fitting:
        # as flow items both would shift their siblings
        from pbridge.convert.layout import LayoutEncoder
        contain = {"t": "image", "img": "a", "fit": "contain", "x": 0, "y": 0, "w": 100, "h": 40}
        fitted = {"t": "text", "x": 0, "y": 0, "w": 60, "h": 20, "text": {"text": "★★★★★", "fitW": 60}}
        plain = {"t": "rect", "x": 0, "y": 0, "w": 100, "h": 40}
        self.assertEqual([LayoutEncoder.settles_later(node) for node in (contain, fitted, plain)], [True, True, False])

    def test_overlapping_children_stay_absolute(self):
        elements = [box_el(0, -1, [0, 0, 400, 300], tag="section"),
                    box_el(1, 0, [0, 0, 300, 100]), box_el(2, 0, [50, 50, 300, 100])]
        self.assertFalse(layout_boards(convert(elements)))

    def test_positioned_child_is_absolute_and_on_top(self):
        elements = [box_el(0, -1, [0, 0, 600, 100], tag="nav", lay=flex_css(gap=(0, 20))),
                    box_el(1, 0, [0, 0, 100, 40]), box_el(2, 0, [120, 0, 100, 40]),
                    box_el(3, 0, [50, 10, 30, 30], pos="absolute", z=2)]
        spec = convert(elements)
        board = layout_boards(spec)[0]
        self.assertEqual((board["children"][-1]["x"], board["children"][-1]["child"]), (50, {"absolute": True}))   # on top
        assert_layouts_exact(self, spec)

    def test_grid_and_wrapping_flex_stay_absolute(self):
        for css in ({"d": "grid", "dir": "row", "wrap": "nowrap", "jc": "normal", "ai": "normal", "gap": [0, 0], "inset": [0, 0, 0, 0]},
                    flex_css(wrap="wrap")):
            elements = [box_el(0, -1, [0, 0, 600, 100], tag="ul", lay=css),
                        box_el(1, 0, [0, 0, 100, 40]), box_el(2, 0, [120, 0, 100, 40])]
            self.assertFalse(layout_boards(convert(elements)), css["d"])


class Settling(unittest.TestCase):
    """After building, Penpot's hugging texts can be a pixel wider than in the browser (pumble.com nav:
    158.1 -> 162 px); settle_correction gives margins that put every child back at its spec x/y."""

    def item(self, justify, sizes, targets, gap=24.0):
        layout = {"type": "flex", "dir": "row", "gap": gap, "padding": [0, 0, 0, 0], "justify": justify, "align": "center"}
        flow = [[f"id{i}", x, y, width, height, {"sizing": ["auto", "auto"]}] for i, ((width, height), (x, y)) in enumerate(zip(sizes, targets))]
        return {"board": "board", "box": [0, 0, 600, 40], "layout": layout, "flow": flow, "absolute": []}

    def check(self, item, measured):
        correction = settle_correction(item, [[width, height, 0, 0] for width, height in measured])
        self.assertIsNotNone(correction)
        layout = {**item["layout"], **correction["layout"]}
        props = [{"margin": margin, "alignSelf": align} for _, margin, align in correction["children"]]
        positions = simulate(layout, tuple(item["box"]), measured, props)
        for (x, y), entry in zip(positions, item["flow"]):
            self.assertAlmostEqual(x, entry[1], delta=0.02)
            self.assertAlmostEqual(y, entry[2], delta=0.02)
        for _, margin, _ in correction["children"]:
            self.assertGreaterEqual(min(margin), -0.02)       # never a negative margin
        return correction

    def test_wider_texts_in_a_centred_row_are_put_back(self):
        sizes = [(158.1, 25.2), (36.2, 25.2), (77.5, 25.2)]
        targets = [(141.1, 7.4), (323.2, 7.4), (383.4, 7.4)]
        self.check(self.item("center", sizes, targets), [(162, 26), (37, 26), (79, 26)])

    def test_text_wider_than_its_gap_shrinks_the_gap(self):
        sizes = [(100, 20), (100, 20)]
        targets = [(0, 10), (102, 10)]                         # 2 px apart; Penpot's first text is 1 px wider
        correction = self.check(self.item("start", sizes, targets, gap=2.0), [(101, 20), (100, 20)])
        self.assertEqual(correction["layout"]["gap"], 1.0)

    def test_overlapping_real_text_needs_a_negative_margin(self):
        # the next target lies inside the wider text: only a negative margin is exact (the build reports
        # what is left if Penpot does not honour it)
        item = self.item("start", [(100, 20), (100, 20)], [(0, 10), (102, 10)], gap=2.0)
        correction = settle_correction(item, [[103, 20, 0, 0], [100, 20, 0, 0]])
        self.assertEqual((correction["layout"]["gap"], correction["children"][1][1][3]), (0.0, -1.0))

    def test_exact_sizes_need_no_correction(self):
        sizes = [(100, 20), (100, 20)]
        item = self.item("start", sizes, [(0, 10), (124, 10)])
        self.assertIsNone(settle_correction(item, [[100, 20, 0, 0], [100, 20, 0, 0]]))


class LayoutChoice(unittest.TestCase):
    """The layout mode is the user's choice: never picked for a new project."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.state = ProjectState.open(Path(self.folder.name))
        self.state.init()
        self.not_a_terminal = mock.patch("sys.stdin.isatty", return_value=False)
        self.not_a_terminal.start()

    def tearDown(self):
        self.not_a_terminal.stop()
        self.folder.cleanup()

    def test_new_project_without_a_choice_stops_with_the_question(self):
        with self.assertRaises(SystemExit) as stopped:
            resolve_layout(self.state, None)
        self.assertIn("--layout auto", str(stopped.exception))
        self.assertNotIn("layout", self.state.config)

    def test_choice_is_saved_and_reused(self):
        self.assertEqual(resolve_layout(self.state, "auto"), "auto")
        reopened = ProjectState.open(Path(self.folder.name))
        self.assertEqual(resolve_layout(reopened, None), "auto")
        self.assertEqual(resolve_layout(reopened, "absolute"), "absolute")

    def test_convert_workflow_passes_the_mode_to_the_converter(self):
        # bug: convert_capture's `layout` parameter was shadowed by the capture dict, so `pb convert --layout auto`
        # built no layout at all while Converter(..., {"layout": "auto"}) did
        from pbridge.workflows import convert_capture
        elements = [box_el(0, -1, [0, 0, 600, 100], tag="nav", lay=flex_css(gap=(0, 20))),
                    box_el(1, 0, [0, 0, 100, 40]), box_el(2, 0, [120, 0, 100, 40])]
        capture = Path(self.folder.name) / "layout.json"
        capture.write_text(json.dumps(layout(elements)))
        summary = convert_capture(self.state, str(capture), check_fonts=False, use_cache=False, layout_mode="auto")
        self.assertEqual(summary["report"].get("layout_boards"), 1)

    def test_project_built_before_the_option_keeps_absolute(self):
        self.state.save_json("idmap.json", {"sec00": "some-shape-id"})
        self.assertEqual(resolve_layout(self.state, None), "absolute")
        self.assertEqual(self.state.config["layout"], "absolute")


if __name__ == "__main__":
    unittest.main()
