"""Design review rules (offline, on spec-format layer trees)."""
import unittest

from PIL import Image, ImageDraw

from pbridge.review import ReviewOptions, contrast_ratio, review
from pbridge.review.fixes import apply_to_spec, fix_operations


def rect(name, x, y, width, height, fill="#FFFFFF", **extra):
    return {"t": "rect", "key": name, "name": name, "x": x, "y": y, "w": width, "h": height, "fill": fill, **extra}


def text(name, x, y, content, color="#111111", size=16, weight=400, width=200, height=20):
    return {"t": "text", "key": name, "name": name, "x": x, "y": y, "w": width, "h": height,
            "text": {"text": content, "color": color, "size": size, "weight": weight}}


def board(*children, fill="#FFFFFF"):
    return {"t": "board", "key": "page", "name": "Page", "x": 0, "y": 0, "w": 1000, "h": 800, "fill": fill, "children": list(children)}


def rules_hit(result, rule):
    return [found for found in result["issues"] if found["rule"] == rule]


class Contrast(unittest.TestCase):
    def test_wcag_reference_values(self):
        self.assertAlmostEqual(contrast_ratio((0, 0, 0), (255, 255, 255)), 21.0, places=1)
        self.assertAlmostEqual(contrast_ratio((118, 118, 118), (255, 255, 255)), 4.54, places=2)

    def test_light_grey_text_on_white_fails(self):
        result = review([board(text("caption", 10, 10, "Hard to read", color="#AAAAAA"))])
        found = rules_hit(result, "contrast")
        self.assertEqual(len(found), 1); self.assertEqual(found[0]["severity"], "error")

    def test_background_is_the_topmost_shape_under_the_text(self):
        # white text on a dark card that sits on a white page: fine
        result = review([board(rect("card", 0, 0, 400, 100, fill="#111827"), text("title", 20, 20, "On dark", color="#FFFFFF"))])
        self.assertEqual(rules_hit(result, "contrast"), [])

    def test_large_text_needs_only_3_to_1(self):
        grey = "#949494"     # ~3.0:1 on white
        result = review([board(text("big", 10, 10, "Headline", color=grey, size=32), text("small", 10, 60, "Body", color=grey))])
        self.assertEqual([found["name"] for found in rules_hit(result, "contrast")], ["small"])

    def test_render_pixels_win_over_the_layer_tree(self):
        # the tree says white background, but the render shows a photo-dark area behind the text
        render = Image.new("RGB", (1000, 800), "#FFFFFF")
        ImageDraw.Draw(render).rectangle((0, 0, 300, 50), fill="#202020")
        result = review([board(text("on-photo", 10, 10, "Caption", color="#FFFFFF"))], render=render)
        self.assertEqual(rules_hit(result, "contrast"), [])


class Consistency(unittest.TestCase):
    def test_near_duplicate_colours_are_merged_into_the_common_one(self):
        cards = [rect(f"card{i}", 0, i * 100, 100, 50, fill="#2563EB") for i in range(3)]
        odd = rect("odd", 0, 400, 100, 50, fill="#2664EA")
        found = rules_hit(review([board(*cards, odd)]), "near-duplicate-color")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["fix"], {"sel": {"key": "odd"}, "set": {"fill": "#2563EB"}})

    def test_font_size_one_px_off_the_scale(self):
        texts = [text(f"body{i}", 0, i * 30, "Body", size=16) for i in range(4)] + [text("odd", 0, 200, "Body", size=15)]
        found = rules_hit(review([board(*texts)]), "font-size")
        self.assertEqual([item["name"] for item in found], ["odd"])
        self.assertEqual(found[0]["fix"]["set"], {"textStyle": {"size": 16}})

    def test_almost_aligned_left_edges(self):
        items = [rect(f"row{i}", 40, i * 60, 300, 40) for i in range(3)] + [rect("odd", 41.5, 200, 300, 40)]
        found = rules_hit(review([board(*items)]), "alignment")
        self.assertEqual([item["name"] for item in found], ["odd"])
        self.assertEqual(found[0]["fix"]["set"], {"x": 40})

    def test_grid_check_only_when_asked(self):
        nodes = [board(rect("off", 13, 16, 100, 40))]
        self.assertEqual(rules_hit(review(nodes), "grid"), [])
        self.assertEqual(len(rules_hit(review(nodes, ReviewOptions(grid=8)), "grid")), 1)

    def test_touch_targets_on_mobile(self):
        nodes = [board(rect("button.primary", 0, 0, 120, 32))]
        self.assertEqual(rules_hit(review(nodes), "touch-target"), [])
        self.assertEqual(len(rules_hit(review(nodes, ReviewOptions(mobile=True)), "touch-target")), 1)

    def test_small_and_empty_text_and_default_names(self):
        nodes = [board(text("tiny", 0, 0, "Legal", size=10), text("blank", 0, 40, "  "), rect("Rectangle 12", 0, 80, 10, 10))]
        result = review(nodes)
        self.assertEqual(len(rules_hit(result, "small-text")), 1)
        self.assertEqual(len(rules_hit(result, "empty-text")), 1)
        self.assertEqual(len(rules_hit(result, "layer-name")), 1)

    def test_summary_counts_and_order(self):
        result = review([board(text("caption", 10, 10, "Low", color="#BBBBBB"), rect("Rectangle 3", 0, 0, 5, 5))])
        self.assertEqual(result["issues"][0]["severity"], "error")
        self.assertEqual(result["summary"]["errors"], 1)


class Fixes(unittest.TestCase):
    def test_fixes_are_applied_to_a_spec(self):
        cards = [rect(f"card{i}", 40, i * 100, 100, 50, fill="#2563EB") for i in range(3)]
        spec = {"nodes": [board(*cards, rect("odd", 41, 400, 100, 50, fill="#2664EA"),
                               *[text(f"body{i}", 40, 500 + i * 30, "Body", size=16) for i in range(3)],
                               text("odd-text", 40, 700, "Body", size=17))]}
        operations = fix_operations(review(spec["nodes"])["issues"])
        self.assertEqual(apply_to_spec(spec, operations), 3)
        nodes = {node["key"]: node for node in spec["nodes"][0]["children"]}
        self.assertEqual((nodes["odd"]["fill"], nodes["odd"]["x"]), ("#2563EB", 40))
        self.assertEqual(nodes["odd-text"]["text"]["size"], 16)
        self.assertEqual(review(spec["nodes"])["summary"]["fixable"], 0)      # nothing left to fix


if __name__ == "__main__":
    unittest.main()
