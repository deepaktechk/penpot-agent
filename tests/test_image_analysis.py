"""`pb analyze`: palette and flat-coloured boxes measured from design images."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pbridge.imaging.analysis import analyze, combined_palette


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


if __name__ == "__main__":
    unittest.main()
