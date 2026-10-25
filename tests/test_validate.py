"""Spec validation: the mistakes hand- and AI-written specs make are caught before building."""
import json
import unittest

from pbridge.build.validate import validate_spec
from pbridge.paths import SOURCE_ROOT


def board(*children, **extra):
    return {"t": "board", "name": "Board", "x": 0, "y": 0, "w": 800, "h": 600, "children": list(children), **extra}


def check(*nodes, images=None):
    return validate_spec({"nodes": list(nodes), "images": images or {}})


class SpecValidation(unittest.TestCase):
    def test_example_spec_is_valid(self):
        # bug: renaming the project shortened the example text but not its highlighted range
        spec = json.loads((SOURCE_ROOT / "examples" / "hello-board.json").read_text())
        report = validate_spec(spec)
        self.assertEqual(report.errors, [])

    def test_typo_in_key_is_reported_with_a_suggestion(self):
        report = check({"t": "rect", "x": 0, "y": 0, "width": 10, "w": 10, "h": 10})
        self.assertTrue(any("unknown key 'width'" in warning for warning in report.warnings), report.warnings)

    def test_unknown_type_suggests_the_closest(self):
        report = check({"t": "rectangle", "x": 0, "y": 0, "w": 10, "h": 10})
        self.assertTrue(any("did you mean 'rect'" in error for error in report.errors), report.errors)

    def test_missing_geometry_and_bad_values(self):
        report = check({"t": "rect", "x": 0, "y": "10", "w": -5, "h": 10, "op": 2})
        joined = " ".join(report.errors)
        self.assertIn("'y' must be a number", joined)
        self.assertIn("'w' must be > 0", joined)
        self.assertIn("opacity", joined)

    def test_bad_colours_and_gradients(self):
        report = check({"t": "rect", "x": 0, "y": 0, "w": 10, "h": 10, "fill": "blue"},
                       {"t": "rect", "x": 0, "y": 0, "w": 10, "h": 10, "fill": {"g": [0, 0, 1]}})
        self.assertEqual(len(report.errors), 2, report.errors)

    def test_text_ranges_outside_the_text(self):
        report = check({"t": "text", "x": 0, "y": 0, "text": {"text": "Hello", "ranges": [[2, 9, {"weight": 700}]]}})
        self.assertTrue(any("outside the text" in error for error in report.errors))

    def test_layout_children_need_no_position(self):
        # inside an auto-layout board, children are positioned by the layout
        report = check(board({"t": "rect", "w": 100, "h": 40, "child": {"sizing": ["fill", "fix"]}},
                             layout={"type": "flex", "dir": "column", "gap": 8}))
        self.assertEqual(report.errors, [])

    def test_child_properties_without_layout_warn(self):
        report = check(board({"t": "rect", "x": 0, "y": 0, "w": 10, "h": 10, "child": {"sizing": ["fill", "fix"]}}))
        self.assertTrue(any("no effect" in warning for warning in report.warnings))

    def test_bad_layout(self):
        report = check(board(layout={"type": "column"}), board(layout={"type": "flex", "sizing": ["hug", "auto"]}))
        self.assertEqual(len(report.errors), 2, report.errors)

    def test_duplicate_keys(self):
        report = check({"t": "rect", "key": "a", "x": 0, "y": 0, "w": 1, "h": 1}, {"t": "rect", "key": "a", "x": 0, "y": 0, "w": 1, "h": 1})
        self.assertTrue(any("duplicate key" in error for error in report.errors))

    def test_image_key_not_in_images_warns(self):
        report = check({"t": "image", "img": "hero", "x": 0, "y": 0, "w": 10, "h": 10})
        self.assertTrue(any("image key 'hero'" in warning for warning in report.warnings))


if __name__ == "__main__":
    unittest.main()
