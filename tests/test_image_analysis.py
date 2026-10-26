"""`pb analyze` (palette and flat-coloured boxes from design images) and the offset audit."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pbridge.imaging.analysis import analyze, combined_palette
from pbridge.imaging.offsets import audit


def draw_mockup(path: Path) -> None:
    """A 1200x800 mockup: white page, dark header bar, blue rounded card, orange button."""
    image = Image.new("RGB", (1200, 800), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1199, 79), fill="#111827")                                   # header 1200x80
    draw.rounded_rectangle((100, 200, 499, 449), radius=24, fill="#2563EB")            # card 400x250, r 24
    draw.rectangle((700, 300, 859, 347), fill="#F97316")                               # button 160x48
    image.save(path)


def find_box(boxes, color):
    return next(box for box in boxes if box["color"] == color)


class ImageAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix="pb-analyze-"))
        cls.mockup = cls.folder / "mockup.png"
        draw_mockup(cls.mockup)
        cls.result = analyze(cls.mockup)

    def assertNear(self, value, expected, tolerance=6):
        self.assertLessEqual(abs(value - expected), tolerance, f"{value} != {expected} ± {tolerance}")

    def test_background_and_palette(self):
        self.assertEqual(self.result["background"], "#FFFFFF")
        colours = [entry["hex"] for entry in self.result["palette"]]
        for expected in ("#FFFFFF", "#111827", "#2563EB", "#F97316"):
            self.assertIn(expected, colours)
        self.assertEqual(colours[0], "#FFFFFF")          # sorted by share

    def test_boxes_are_measured_at_full_resolution(self):
        header = find_box(self.result["boxes"], "#111827")
        self.assertNear(header["x"], 0); self.assertNear(header["y"], 0)
        self.assertNear(header["w"], 1200); self.assertNear(header["h"], 80)
        button = find_box(self.result["boxes"], "#F97316")
        self.assertNear(button["x"], 700); self.assertNear(button["y"], 300)
        self.assertNear(button["w"], 160); self.assertNear(button["h"], 48)
        self.assertLessEqual(button["r"], 4)

    def test_rounded_corner_radius_is_estimated(self):
        card = find_box(self.result["boxes"], "#2563EB")
        self.assertNear(card["w"], 400); self.assertNear(card["h"], 250)
        self.assertNear(card["r"], 24, tolerance=8)

    def test_page_background_is_not_a_box(self):
        self.assertNotIn("#FFFFFF", [box["color"] for box in self.result["boxes"]])

    def test_region_crop_keeps_page_coordinates(self):
        cropped = analyze(self.mockup, region=(650, 250, 950, 400))
        button = find_box(cropped["boxes"], "#F97316")
        self.assertNear(button["x"], 700); self.assertNear(button["y"], 300)

    def test_combined_palette_of_several_references(self):
        second = self.folder / "second.png"
        Image.new("RGB", (400, 400), "#2563EB").save(second)
        merged = combined_palette([self.result, analyze(second)])
        self.assertEqual(merged[0]["hex"], "#2563EB")     # dominant across the two references


class OffsetAudit(unittest.TestCase):
    """`pb audit`: per-element offsets; the parallel audit must equal the serial one."""

    def setUp(self):
        folder = Path(tempfile.mkdtemp(prefix="pb-audit-"))
        self.reference, self.render = folder / "reference.png", folder / "render.png"
        reference_image = Image.new("RGB", (600, 400), "#FFFFFF")
        render_image = Image.new("RGB", (600, 400), "#FFFFFF")
        reference_draw, render_draw = ImageDraw.Draw(reference_image), ImageDraw.Draw(render_image)
        self.elements = []
        for i in range(12):                     # 12 boxes; even ones are shifted by (+3, -2) in the render
            x, y = 20 + (i % 4) * 140, 30 + (i // 4) * 120
            dx, dy = (3, -2) if i % 2 == 0 else (0, 0)
            reference_draw.rectangle((x, y, x + 60, y + 30), fill="#2563EB")
            render_draw.rectangle((x + dx, y + dy, x + 60 + dx, y + 30 + dy), fill="#2563EB")
            self.elements.append({"key": f"e{i}", "id": f"id{i}", "name": f"box {i}", "box": [x, y, 61, 31]})
        reference_image.save(self.reference); render_image.save(self.render)

    def test_finds_the_shifted_elements(self):
        issues = audit(self.reference, self.render, self.elements, workers=1)
        self.assertEqual({issue["key"] for issue in issues}, {f"e{i}" for i in range(0, 12, 2)})
        self.assertTrue(all((issue["dx"], issue["dy"]) == (3, -2) for issue in issues))

    def test_parallel_audit_equals_serial_audit(self):
        serial = audit(self.reference, self.render, self.elements, workers=1)
        parallel = audit(self.reference, self.render, self.elements, workers=4)
        self.assertEqual(serial, parallel)


if __name__ == "__main__":
    unittest.main()
