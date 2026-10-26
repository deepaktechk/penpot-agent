"""End-to-end regressions on tests/fixtures/tricky.html (a page that contains every pattern
that ever broke the pipeline). Capture needs Chrome + network (Google Fonts);
`pb selftest --build` additionally builds into Penpot and checks Penpot-side quirks."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pbridge.paths import TESTS_DIR, node_command

FIXTURE = TESTS_DIR / "fixtures" / "tricky.html"
CAPTURE = os.environ.get("PB_SELFTEST_CAPTURE", "1") == "1"
BUILD = os.environ.get("PB_SELFTEST_BUILD", "0") == "1"

# shapes of the scratch board whose x lies outside it (bug: shapes landed at x=0, not in the board)
OUTSIDE_JS = ("const board = pb.byId(DATA); "
              "const outside = penpotUtils.findShapes(shape => shape.type === 'text' "
              "&& (shape.x < board.x - 1 || shape.x > board.x + board.width), board); "
              "return {boardX: board.x, outside: outside.length};")
# fill color of the last 9 characters of the "questions" text (a range ending at the text end)
LAST_RANGE_COLOR_JS = ("const text = pb.find({within: DATA, text: 'questions'}).filter(shape => shape.type === 'text')[0]; "
                       "const length = text.characters.length; return text.getRange(length - 9, length).fills[0].fillColor;")


def all_nodes(nodes):
    flat = []
    for node in nodes:
        flat.append(node)
        flat += all_nodes(node.get("children", []))
    return flat


@unittest.skipUnless(CAPTURE, "capture disabled")
class FixtureEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="pb-selftest-"))
        capture_dir = cls.tmp / "cap"
        result = subprocess.run([*node_command("capture"), "--url", FIXTURE.as_uri(), "--out", str(capture_dir),
                                 "--width", "1440", "--fonts", "Outfit"], capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError("capture failed: " + result.stderr[-1500:])
        cls.layout = json.loads((capture_dir / "layout.json").read_text())
        cls.shot = capture_dir / "shot.png"
        from pbridge.convert import Converter
        cls.spec = Converter(cls.layout, {"fallback_font": "Outfit", "screenshot": str(cls.shot)}).convert()
        cls.auto_spec = Converter(cls.layout, {"fallback_font": "Outfit", "screenshot": str(cls.shot), "layout": "auto"}).convert()
        cls.nodes = all_nodes(cls.spec["nodes"])
        cls.texts = [node for node in cls.nodes if node.get("t") == "text"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def find_text(self, fragment):
        return [node for node in self.texts if fragment in node["text"]["text"]]

    # ---------------- capture quality
    def test_capture_gate_passes(self):
        from pbridge.quality import capture_gate
        gate = capture_gate(self.layout, self.shot)
        self.assertTrue(gate["ok"], gate["errors"])

    def test_real_font_rendered_not_fallback(self):
        # bug: font-display: optional -> Helvetica fallback in the reference
        font_render = self.layout["quality"]["fontRender"].get("Outfit")
        self.assertIsNotNone(font_render)
        self.assertLess(font_render["medianDev"], 0.02, font_render)

    def test_page_settled_before_capture(self):
        # bug: carousels captured mid-slide
        self.assertGreaterEqual(self.layout["quality"]["stableSamples"], 3)
        slides = [node for node in self.texts if node["text"]["text"].startswith("Slide ")]
        self.assertEqual(len(slides), 1, [slide["text"]["text"] for slide in slides])

    def test_lazy_images_outside_the_viewport_are_loaded(self):
        # getfieldy.com: lazy logos right of the viewport in a marquee never loaded, the gate failed
        self.assertEqual(self.layout["quality"]["lazyPending"], 0)
        self.assertFalse(self.layout["quality"]["brokenImages"])

    def test_collapsed_dropdown_is_not_built(self):
        # clockify.me: the closed product switcher (visibility: collapse) was built in the nav
        self.assertFalse([node for node in self.texts if node["text"]["text"] == "Collapsed menu item"])
        self.assertFalse([node for node in self.nodes if node.get("name") == "collapsed logo"])

    def test_zero_area_clip_path_popups_are_not_built(self):
        # pumble.com: closed "zoom" popups (clip-path: circle(0)) were built over the app mockups
        texts = {" ".join(node["text"]["text"].split()) for node in self.texts}   # the 100px popups wrap
        self.assertNotIn("Closed zoom popup", texts)
        self.assertNotIn("Inset closed popup", texts)
        self.assertFalse([node for node in self.nodes if node.get("name") == "closed zoom logo"])
        self.assertIn("Open zoom popup", texts)

    def test_auto_layout_reproduces_every_position(self):
        # --layout auto: every emitted flex layout puts each child exactly where the absolute build does
        from pbridge.convert.layout import layout_errors
        boards = [node for node in all_nodes(self.auto_spec["nodes"]) if node.get("layout")]
        self.assertGreaterEqual(len(boards), 3)
        self.assertEqual(layout_errors(self.auto_spec["nodes"]), [])
        self.assertFalse([node for node in self.nodes if node.get("layout") or node.get("child")])   # absolute mode untouched

    def test_flex_nav_is_a_flex_board(self):
        boards = [node for node in all_nodes(self.auto_spec["nodes"]) if node.get("layout")
                  and any(child.get("t") == "text" and child["text"]["text"] == "Pricing" for child in node["children"])]
        self.assertEqual(len(boards), 1)
        self.assertEqual({key: boards[0]["layout"][key] for key in ("dir", "justify", "align", "gap")},
                         {"dir": "row", "justify": "center", "align": "center", "gap": 24})
        badge = [child for child in boards[0]["children"] if child.get("child", {}).get("absolute")
                 and "new" in json.dumps(child)]
        self.assertTrue(badge)

    def test_visible_child_of_a_hidden_parent_is_built(self):
        texts = {node["text"]["text"] for node in self.texts}
        self.assertIn("Visible inside hidden", texts)
        self.assertNotIn("Hidden parent line", texts)

    def test_overlays_auto_hidden(self):
        # bug: cookie banners / chat launchers were drawn into the design
        self.assertFalse(self.find_text("We use cookies"))
        self.assertFalse([node for node in self.nodes if node.get("t") == "rect" and node.get("fill") == "#1D4ED8"])

    def test_centred_sections_split(self):
        # bug: sites with centred (non full-width) section containers produced one giant section
        sections = [node for node in self.spec["nodes"] if node.get("t") == "board" and node.get("key") != "secbg"]
        self.assertGreaterEqual(len(sections), 2)

    def test_own_overflow_does_not_clip_own_border(self):
        # bug: a box's own overflow:hidden clipped its border (facebook.com login inputs lost their right/bottom edge)
        fields = [element for element in self.layout["elements"] if element.get("htmlId") == "float-field"]
        self.assertTrue(fields)
        self.assertNotIn("clip", fields[0])

    def test_scaled_label_is_not_ellipsized(self):
        # bug: a transform-scaled label was measured against its scaled box -> "Email address or mobile n…"
        labels = [element for element in self.layout["elements"] if element.get("htmlId") == "float-label"]
        self.assertTrue(labels)
        self.assertNotIn("visible", labels[0])

    # ---------------- conversion
    def test_lab_box_color(self):
        self.assertTrue(any(node.get("t") == "rect" and node.get("fill") == "#1E2939" for node in self.nodes))

    def test_scaled_label_font_size(self):
        # bug: transform: scale(0.8) on a 15px label was ignored and the text built at 15px
        label = self.find_text("Email address or mobile number")
        self.assertTrue(label)
        self.assertAlmostEqual(label[0]["text"]["size"], 12.0, places=1)

    def test_ancestor_line_clamp(self):
        text = self.find_text("Smart SaaS")[0]["text"]["text"]
        self.assertNotIn("\n", text); self.assertNotIn("Want to develop", text); self.assertEqual(text.count("…"), 1)

    def test_no_double_ellipsis(self):
        text = self.find_text("I contracted")[0]["text"]["text"]
        self.assertFalse(text.endswith("...…") or text.endswith("……"), text)

    def test_sr_only_absent(self):
        self.assertFalse(self.find_text("hidden accessible label"))

    def test_uppercase_flag(self):
        self.assertTrue(self.find_text("Our blog")[0]["text"].get("upper"))

    def test_pseudo_rules_located(self):
        rules = [node for node in self.nodes
                 if node.get("t") == "rect" and str(node.get("name", "")).endswith(("::before", "::after"))]
        self.assertEqual(len(rules), 2, rules)

    def test_coloured_underline_located(self):
        self.assertTrue([node for node in self.nodes if node.get("name") == "underline"])

    def test_gradient_text_per_char(self):
        text = self.find_text("Why")[0]["text"]
        single_char_ranges = [text_range for text_range in text.get("ranges", []) if text_range[1] - text_range[0] == 1]
        self.assertGreaterEqual(len(single_char_ranges), 10)

    def test_svg_baked_to_screen_space(self):
        svgs = [node for node in self.nodes if node.get("t") == "svg" and "M60,60" in node["svg"]]
        self.assertTrue(svgs)
        self.assertNotIn("preserveAspectRatio", svgs[0]["svg"])
        self.assertIn("matrix(1.5 0 0 0.6666666666666666 0 0)", svgs[0]["svg"])   # viewBox 400x300 stretched to 600x200 (preserveAspectRatio=none)

    def test_svg_markup_has_no_broken_numbers(self):
        # bug: getScreenCTM() returns an SVGMatrix (a..f only); reading m11..m22 baked "matrix(undefined ...)"
        for node in self.nodes:
            if node.get("t") == "svg":
                self.assertNotRegex(node["svg"], r"undefined|NaN", node.get("name"))

    def test_complex_svg_is_rasterized_image(self):
        # bug: Penpot's SVG importer misplaces clipPath content -> complex SVGs must stay raster
        self.assertTrue(any(node.get("t") == "image" and node.get("fit") == "cover" and "complex" in str(node.get("name"))
                            for node in self.nodes),
                        [node.get("name") for node in self.nodes if node.get("t") in ("image", "svg")])

    def test_cover_svg_is_image_and_contain_svg_is_vector(self):
        self.assertTrue(any(node.get("t") == "board" and node.get("clip") and str(node.get("name", "")).startswith("cover")
                            for node in self.nodes))
        self.assertTrue(any(node.get("t") == "svg" and "<rect" in node.get("svg", "") and 'rx="8"' in node["svg"]
                            for node in self.nodes))

    def test_padded_image_content_box(self):
        icons = [node for node in self.nodes if node.get("name") == "padded icon"]
        self.assertTrue(icons); self.assertAlmostEqual(icons[0]["h"], 48, delta=0.6)

    def test_symbol_line_is_fitted_in_penpot(self):
        # clockify.me ratings: browser and Penpot draw ★ with different fonts; the plugin fits the width
        stars = [node for node in self.texts if node["text"]["text"] == "★★★★★"]
        self.assertEqual(len(stars), 1)
        self.assertGreater(stars[0]["text"].get("fitW", 0), 20)

    # ---------------- Penpot (optional)
    @unittest.skipUnless(BUILD, "build disabled (use pb selftest --build)")
    def test_build_in_penpot(self):
        from pbridge.build import PageBoards, SpecBuilder
        from pbridge.connection import Bridge, Exporter
        from pbridge.project import ProjectState
        from pbridge.quality import render_gate
        project = self.tmp / "proj"; state = ProjectState.open(project); state.init()
        bridge = Bridge(state)
        # placed right of everything: exercises the board-origin offset (bug: shapes landed at x=0)
        # convert like `pb convert` does: families Penpot lacks (Arial in #mixed-scripts) use the fallback font
        from pbridge.convert import Converter
        available = set(bridge.exec("return penpot.fonts.all.map(font => font.name);"))
        spec = Converter(self.layout, {"fallback_font": "Outfit", "screenshot": str(self.shot), "available_fonts": available}).convert()
        board = PageBoards(bridge).ensure("pbridge selftest (auto-removed)", spec["width"], spec["height"], after="*")
        try:
            report = SpecBuilder(bridge).build(spec, parent=board, default_font="Outfit", progress=lambda *message: None)
            self.assertFalse(report["failed"], report["failed"])
            placement = bridge.exec(OUTSIDE_JS, data=board)
            self.assertGreater(placement["boardX"], 0)
            self.assertEqual(placement["outside"], 0, "shapes built outside their board")
            # Penpot quirk: range ending at the end of a later paragraph must stay red
            color = bridge.exec(LAST_RANGE_COLOR_JS, data=board)
            self.assertEqual(color.upper(), "#EF3225")
            render = Exporter(bridge).export(board)
            gate = render_gate(self.shot, render, spec, state=None, overrides={"section_pct_error": 6.0})
            self.assertTrue(gate["ok"], gate["errors"])
        finally:
            bridge.exec("const shape = pb.byId(DATA); if (shape) shape.remove(); return 1;", data=board)

    @unittest.skipUnless(BUILD, "build disabled (use pb selftest --build)")
    def test_build_auto_layout_in_penpot(self):
        # --layout auto in Penpot: absolute children placed after the layouts settle (they stayed at their
        # first flow slot), child boards built before their parent's layout is live (they moved 98 px with
        # their subtree on pumble.com), flow children put back after Penpot's wider hugging texts
        from pbridge.build import PageBoards, SpecBuilder
        from pbridge.connection import Bridge, Exporter
        from pbridge.convert import Converter
        from pbridge.project import ProjectState
        from pbridge.quality import render_gate
        project = self.tmp / "proj-auto"; state = ProjectState.open(project); state.init()
        bridge = Bridge(state)
        available = set(bridge.exec("return penpot.fonts.all.map(font => font.name);"))
        spec = Converter(self.layout, {"fallback_font": "Outfit", "screenshot": str(self.shot), "available_fonts": available,
                                       "layout": "auto"}).convert()
        board = PageBoards(bridge).ensure("pbridge selftest auto layout (auto-removed)", spec["width"], spec["height"], after="*")
        try:
            report = SpecBuilder(bridge).build(spec, parent=board, default_font="Outfit", progress=lambda *message: None)
            self.assertFalse(report["failed"], report["failed"])
            flex_boards = bridge.exec("return penpotUtils.findShapes(shape => shape.type === 'board' && !!shape.flex, pb.byId(DATA)).length;",
                                      data=board)
            self.assertGreaterEqual(flex_boards, 3)
            self.assertLessEqual(report.get("layout_worst_px", 0), 0.5, report.get("warnings"))
            render = Exporter(bridge).export(board)
            gate = render_gate(self.shot, render, spec, state=None, overrides={"section_pct_error": 6.0})
            self.assertTrue(gate["ok"], gate["errors"])
        finally:
            bridge.exec("const shape = pb.byId(DATA); if (shape) shape.remove(); return 1;", data=board)


if __name__ == "__main__":
    unittest.main()
