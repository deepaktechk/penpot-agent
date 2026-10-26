"""Unit regressions for the converter. Each test names the real bug it guards against."""
import unittest

from pbridge.convert import Converter, gradient_char_ranges, parse_color, parse_gradient

BLACK_TEXT_FONT = ["Outfit", "16px", "400", "20px", "normal", "rgb(0, 0, 0)", "start", "none", "normal", "none"]
PLAIN_SVG = "<svg xmlns='http://www.w3.org/2000/svg'/>"


def layout(elements, width=1920, height=2000):
    return {"url": "https://example.com/", "width": width, "height": height, "elements": elements}


def text_el(index, text, rect, parent=-1, font=None, **extra):
    """A captured text element (see convert/context.py for the capture format)."""
    lines = extra.pop("lines", [{"t": text, "r": rect}])
    return {"i": index, "p": parent, "tag": extra.pop("tag", "p"), "r": rect, "op": 1, "text": text,
            "font": font or BLACK_TEXT_FONT, "disp": "block", "lines": lines, **extra}


def box_el(index, parent, rect, background="rgb(255, 255, 255)", tag="section"):
    """A captured element with a plain background box."""
    return {"i": index, "p": parent, "tag": tag, "r": rect, "op": 1,
            "box": {"bg": background, "bw": [0, 0, 0, 0], "bs": ["none"] * 4, "bc": ["rgb(0,0,0)"] * 4, "radius": ["0px"] * 4}}


def all_nodes(nodes):
    flat = []
    for node in nodes:
        flat.append(node)
        flat += all_nodes(node.get("children", []))
    return flat


def converted_nodes(elements, opts=None):
    return all_nodes(Converter(layout(elements), opts).convert()["nodes"])


def texts_of(nodes):
    return [node for node in nodes if node.get("t") == "text"]


def sections_of(elements):
    """Section boards of a conversion, without the page background board."""
    return [board for board in Converter(layout(elements)).convert()["nodes"] if board.get("key") != "secbg"]


class Colors(unittest.TestCase):
    def test_lab_colors_are_converted(self):
        # bug: CSS lab() (Tailwind v4) was dropped -> missing social circles / FAQ borders
        self.assertEqual(parse_color("lab(54.2917 80.8125 69.8851)")[0], "#FF0000")
        self.assertEqual(parse_color("lab(16.1051 -1.18239 -11.7533)")[0], "#1E2939")
        self.assertEqual(parse_color("lch(54.2917 106.839 40.8526)")[0], "#FF0000")

    def test_oklab_oklch_hsl_hex_alpha(self):
        self.assertEqual(parse_color("oklab(0.627955 0.224863 0.125846)")[0], "#FF0000")
        self.assertEqual(parse_color("oklch(0.627955 0.257683 29.2339)")[0], "#FF0000")
        self.assertEqual(parse_color("hsl(0 100% 50%)")[0], "#FF0000")
        self.assertEqual(parse_color("#f00")[0], "#FF0000")
        self.assertEqual(parse_color("rgba(0, 0, 0, 0.5)"), ("#000000", 0.5))
        self.assertIsNone(parse_color("rgba(0, 0, 0, 0)"))
        self.assertEqual(parse_color("oklab(0.999994 0.0000455678 0.0000200868 / 0.4)")[1], 0.4)

    def test_gradient_text_becomes_per_char_colors(self):
        # bug: Penpot drops gradients on text ranges -> emulate per character
        gradient = parse_gradient("linear-gradient(to right, rgb(255, 255, 255) 0%, rgb(0, 0, 0) 100%)", 100, 20)
        ranges = gradient_char_ranges(0, 4, gradient, "abcd")
        self.assertEqual(len(ranges), 4)
        self.assertNotEqual(ranges[0][2]["color"], ranges[-1][2]["color"])


class Text(unittest.TestCase):
    def test_no_double_ellipsis(self):
        # bug: clamped text already ending with "..." got a second "…"
        element = text_el(1, "x", [100, 100, 200, 44], lc=2, tov="ellipsis",
                          lines=[{"t": "I contracted with", "r": [100, 100, 150, 22]}, {"t": "Acme Studio to ...", "r": [100, 122, 150, 22]},
                                 {"t": "more text", "r": [100, 144, 80, 22]}])
        text = texts_of(converted_nodes([element]))[0]["text"]["text"]
        self.assertTrue(text.endswith("..."))
        self.assertNotIn("…", text)

    def test_clamp_adds_single_ellipsis(self):
        element = text_el(1, "x", [100, 100, 300, 20], lc=1,
                          lines=[{"t": "Smart SaaS Applications Made Just for You", "r": [100, 100, 299, 20]},
                                 {"t": "hidden", "r": [100, 120, 50, 20]}])
        text = texts_of(converted_nodes([element]))[0]["text"]["text"]
        self.assertEqual(text.count("…"), 1)
        self.assertNotIn("\n", text)

    def test_sr_only_text_is_skipped(self):
        # bug: screen-reader-only labels ("Read more: ...") were drawn
        element = text_el(1, "Read more: secret", [100, 100, 1, 1])
        self.assertFalse(texts_of(converted_nodes([element])))

    def test_text_transform_is_applied(self):
        # bug: line text comes from DOM text nodes, so uppercase labels came out mixed-case
        font = ["Outfit", "12px", "700", "16px", "2px", "rgb(238, 51, 36)", "start", "uppercase", "normal", "none"]
        element = text_el(1, "Our blog", [100, 100, 80, 16], font=font)
        self.assertTrue(texts_of(converted_nodes([element]))[0]["text"].get("upper"))

    def test_lines_outside_element_and_parent_are_dropped(self):
        # bug: CMS <p> lines overflowing a clamped wrapper leaked into the design
        parent = box_el(0, -1, [100, 100, 300, 54], tag="div")
        element = text_el(1, "x", [100, 120, 300, 20], parent=0,
                          lines=[{"t": "visible line", "r": [100, 120, 100, 20]}, {"t": "leaked line", "r": [100, 200, 100, 20]}])
        self.assertEqual(texts_of(converted_nodes([parent, element]))[0]["text"]["text"], "visible line")

    def test_system_font_maps_to_system_font_option(self):
        font = ["-apple-system", "30px", "700", "36px", "normal", "rgb(17, 24, 39)", "start", "none", "normal", "none"]
        element = text_el(1, "Steps", [100, 100, 90, 36], font=font)
        self.assertEqual(texts_of(converted_nodes([element], {"system_font": "Inter"}))[0]["text"]["font"], "Inter")

    def test_partially_clipped_element_is_wrapped_in_clip_board(self):
        # bug: off-screen carousel slides leaked outside their card
        element = text_el(1, "Great service", [300, 100, 200, 20], clip=[344, 0, 1000, 500])
        self.assertTrue([node for node in converted_nodes([element]) if node.get("t") == "board" and node.get("clip")])


class Sections(unittest.TestCase):
    def test_overlapping_full_width_sections_split(self):
        # bug: requiring strict stacking collapsed a real landing page (card overlapping a coloured band) into 3 sections
        elements = [{"i": 0, "p": -1, "tag": "main", "r": [0, 0, 1920, 3000], "op": 1},
                    box_el(1, 0, [0, 0, 1920, 1200]), box_el(2, 0, [0, 1000, 1920, 1000], "rgb(0, 0, 0)"),
                    box_el(3, 0, [0, 2000, 1920, 1000])]
        self.assertEqual(len(sections_of(elements)), 3)

    def test_centred_stacked_containers_split(self):
        elements = [{"i": 0, "p": -1, "tag": "main", "r": [0, 0, 1920, 2000], "op": 1},
                    box_el(1, 0, [410, 0, 1100, 1000]), box_el(2, 0, [410, 1000, 1100, 1000])]
        self.assertEqual(len(sections_of(elements)), 2)

    def test_thin_lines_are_not_sections(self):
        # bug: centred rule split a section's heading/subtitle lines into separate 30px "sections"
        elements = [{"i": 0, "p": -1, "tag": "main", "r": [0, 0, 1920, 400], "op": 1},
                    box_el(1, 0, [410, 0, 1100, 40]), box_el(2, 0, [410, 40, 1100, 40]), box_el(3, 0, [410, 80, 1100, 320])]
        self.assertEqual(len(sections_of(elements)), 1)


class Metrics(unittest.TestCase):
    def test_same_name_font_with_different_metrics_is_fitted(self):
        # bug: Inter variable (opsz) is narrower than Penpot's static Inter -> centred lines drifted
        import pbridge.convert.fontmetrics as fontmetrics
        original_width, original_fit = fontmetrics.text_width, fontmetrics.fit_letter_spacing
        fontmetrics.text_width = lambda *args, **kwargs: 110.0            # Penpot font 10% wider than browser
        fontmetrics.fit_letter_spacing = lambda *args, **kwargs: -0.5
        try:
            font = ["Inter", "20px", "400", "30px", "normal", "rgb(0, 0, 0)", "start", "none", "normal", "none"]
            elements = [text_el(i, "Hello wonderful", [100, 100 + 40 * i, 100, 30], font=font) for i in range(1, 5)]
            self.assertEqual(texts_of(converted_nodes(elements))[0]["text"]["ls"], -0.5)
        finally:
            fontmetrics.text_width, fontmetrics.fit_letter_spacing = original_width, original_fit

    def test_single_anomalous_line_is_not_fitted(self):
        # bug: one heading whose browser width included a trailing nbsp got re-spaced (a real FAQ heading)
        import pbridge.convert.fontmetrics as fontmetrics
        original_width, original_fit = fontmetrics.text_width, fontmetrics.fit_letter_spacing
        fontmetrics.text_width = lambda text, *args, **kwargs: 110.0 if text.startswith("Frequently") else 100.0
        fontmetrics.fit_letter_spacing = lambda *args, **kwargs: -0.5
        try:
            font = ["Outfit", "60px", "700", "66px", "normal", "rgb(0, 0, 0)", "start", "none", "normal", "none"]
            elements = [text_el(i, f"Normal heading {i}", [100, 100 + 80 * i, 100, 60], font=font) for i in range(1, 5)]
            elements.append(text_el(9, "Frequently asked", [100, 900, 100, 60], font=font))
            faq = [node for node in texts_of(converted_nodes(elements)) if node["text"]["text"].startswith("Frequently")][0]
            self.assertEqual(faq["text"]["ls"], 0)
        finally:
            fontmetrics.text_width, fontmetrics.fit_letter_spacing = original_width, original_fit


    def test_text_with_glyphs_missing_from_penpot_font_is_not_fitted(self):
        # bug: google.com "Google offered in: हिन्दी বাংলা ..." measured with Arimo (no Indic glyphs)
        # got letter-spacing -2.7 px and the whole line was squeezed together
        import pbridge.convert.fontmetrics as fontmetrics
        original_width, original_fit, original_covers = fontmetrics.text_width, fontmetrics.fit_letter_spacing, fontmetrics.covers
        fontmetrics.text_width = lambda *args, **kwargs: 600.0
        fontmetrics.fit_letter_spacing = lambda *args, **kwargs: -2.7
        fontmetrics.covers = lambda text, *args, **kwargs: text.isascii()
        try:
            font = ["sans-serif", "13px", "400", "normal", "normal", "rgb(0, 0, 0)", "center", "none", "normal", "none"]
            elements = [text_el(1, "Offered in: हिन्दी বাংলা", [700, 540, 420, 16], font=font),
                        text_el(2, "Plain ascii line", [700, 600, 100, 16], font=font)]
            mixed, ascii_only = texts_of(converted_nodes(elements, {"fallback_font": "Arimo"}))
            self.assertEqual(mixed["text"]["ls"], 0)
            self.assertEqual(ascii_only["text"]["ls"], -2.7)          # covered text is still fitted
            # and the centred line is centred by Penpot in a box, not anchored with the bogus width
            self.assertEqual(mixed["text"]["align"], "center")
            self.assertAlmostEqual(mixed["x"] + mixed["w"] / 2, 700 + 420 / 2, places=1)
        finally:
            fontmetrics.text_width, fontmetrics.fit_letter_spacing, fontmetrics.covers = original_width, original_fit, original_covers

    def test_single_symbol_line_is_fitted_in_penpot(self):
        # bug: clockify.me ratings "★★★★★": the site's Inter subset has no ★, so Chrome drew a fallback
        # glyph (72.7 px for the line) while Penpot's full Inter has a narrower ★ (64 px). Symbols are drawn
        # with whatever font has them, so no offline measurement is reliable; the plugin measures
        # Penpot's real width and fits the letter spacing to the browser's (fitW, pb.fitTexts phase 1)
        font = ["Inter", "12px", "400", "24px", "2px", "rgb(3, 169, 244)", "start", "none", "normal", "none"]
        elements = [text_el(1, "★★★★★", [20, 5749.5, 340, 24], lines=[{"t": "★★★★★", "r": [20, 5753.5, 72.7, 15]}], font=font),
                    text_el(2, "Plain line", [20, 5800, 340, 24], lines=[{"t": "Plain line", "r": [20, 5804, 60, 15]}], font=font),
                    text_el(3, "Two\nlines ✓", [20, 5900, 340, 48],
                            lines=[{"t": "Two", "r": [20, 5904, 30, 15]}, {"t": "lines ✓", "r": [20, 5928, 50, 15]}], font=font)]
        stars, plain, two_lines = texts_of(converted_nodes(elements, {"metric_fit": False}))
        self.assertEqual(stars["text"]["fitW"], 72.7)
        self.assertEqual(stars["text"]["grow"], "auto-width")
        self.assertNotIn("fitW", plain["text"])             # letters: fitted offline (or not at all), as before
        self.assertNotIn("fitW", two_lines["text"])         # the plugin only fits auto-width single lines


    def test_scaled_text_uses_scaled_font_size(self):
        # bug: facebook.com floating label (15px, transform: scale(0.8667)) was built at 15px
        font = ["Outfit", "15px", "400", "17px", "normal", "rgb(0, 0, 0)", "start", "none", "normal", "none"]
        label = text_el(1, "Email address", [100, 100, 90, 14.73], font=font, tf="matrix(0.866667, 0, 0, 0.866667, 0, -11.2667)")
        text = texts_of(converted_nodes([label], {"metric_fit": False}))[0]["text"]
        self.assertAlmostEqual(text["size"], 13.0, places=2)
        self.assertAlmostEqual(text["lh"], 14.73, places=2)


class Images(unittest.TestCase):
    @staticmethod
    def convert_with_svg(elements, svg_markup, opts=None):
        converter = Converter(layout(elements), opts)
        converter.fetch_svg = lambda url: svg_markup
        return all_nodes(converter.convert()["nodes"])

    def test_opaque_background_image_makes_a_valid_spec(self):
        # bug: getfieldy.com section backgrounds got "op": null (opacity 1), the spec failed validation
        from pbridge.build.validate import validate_spec
        section = box_el(1, -1, [0, 0, 1920, 600])
        section["box"].update({"bi": 'url("https://example.com/hero.webp")', "bsize": "cover"})
        faded = box_el(2, -1, [0, 600, 1920, 600])
        faded["box"].update({"bi": 'url("https://example.com/faded.webp")', "bsize": "cover"}); faded["op"] = 0.5
        spec = Converter(layout([section, faded])).convert()
        images = [node for node in all_nodes(spec["nodes"]) if node.get("name") == "section bg image"]
        self.assertEqual(len(images), 2)
        self.assertNotIn("op", images[0])
        self.assertEqual(images[1]["op"], 0.5)
        self.assertEqual(validate_spec(spec).errors, [])

    def test_cover_svg_stays_a_cropped_image(self):
        # bug: cover-fitted SVG imported as vector got stretched -> missing section background
        element = {"i": 1, "p": -1, "tag": "img", "r": [0, 0, 1920, 500], "op": 1, "src": "https://example.com/bg.svg",
                   "nat": [1440, 900], "fit": "cover", "opos": "50% 50%"}
        nodes = self.convert_with_svg([element], PLAIN_SVG, {"svg_vector": True})
        clip = [node for node in nodes if node.get("t") == "board" and node.get("clip")]
        svg = [node for node in nodes if node.get("t") == "svg"]
        self.assertTrue(clip and svg)
        self.assertAlmostEqual(svg[0]["w"] / svg[0]["h"], 1440 / 900, places=3)   # aspect preserved (no stretch)
        self.assertEqual((clip[0]["w"], clip[0]["h"]), (1920, 500))

    def test_complex_svg_stays_raster(self):
        element = {"i": 1, "p": -1, "tag": "img", "r": [0, 0, 1920, 500], "op": 1, "src": "https://example.com/bg.svg",
                   "nat": [1366, 552], "fit": "cover"}
        nodes = self.convert_with_svg([element], "<svg xmlns='http://www.w3.org/2000/svg'><defs><clipPath id='a'/></defs></svg>")
        self.assertTrue(any(node.get("t") == "image" and node.get("fit") == "cover" for node in nodes))
        self.assertFalse(any(node.get("t") == "svg" for node in nodes))

    def test_image_uses_content_box(self):
        # bug: <img> with padding was stretched to its padding box (award badge)
        element = {"i": 1, "p": -1, "tag": "img", "r": [0, 0, 75, 89], "cbox": [0, 9.5, 75, 70], "op": 1,
                   "src": "https://example.com/a.png", "nat": [75, 70], "fit": "fill"}
        image = [node for node in converted_nodes([element]) if node.get("t") == "image"][0]
        self.assertEqual((image["y"], image["h"]), (9.5, 70))

    def test_svg_img_with_fill_keeps_aspect(self):
        # bug: SVG <img> in a taller box was stretched; browsers letterbox SVGs (preserveAspectRatio meet)
        element = {"i": 1, "p": -1, "tag": "img", "r": [0, 0, 75, 89], "op": 1, "src": "https://example.com/b.svg",
                   "nat": [75, 70], "fit": "fill"}
        nodes = self.convert_with_svg(
            [element], "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 75 70'><defs><clipPath id='a'/></defs></svg>")
        self.assertEqual([node for node in nodes if node.get("t") == "image"][0]["fit"], "contain")

    def test_nested_preserve_aspect_none_does_not_stretch_the_svg(self):
        # bug: pumble.com "zoom-effect-thread" (190x495 in a 490x490 box) was stretched 2.6x: an inner
        # <image preserveAspectRatio="none"> was read as the root's; only the root <svg> decides
        element = {"i": 1, "p": -1, "tag": "img", "r": [1193, 1827, 490, 490], "op": 1, "src": "https://example.com/thread.svg",
                   "nat": [190, 495], "fit": "fill"}
        markup = ("<svg xmlns='http://www.w3.org/2000/svg' width='190' height='495' viewBox='0 0 190 495'>"
                  "<defs><pattern id='p'><image preserveAspectRatio='none' width='1' height='1'/></pattern></defs>"
                  "<rect width='190' height='495' fill='url(#p)'/></svg>")
        image = [node for node in self.convert_with_svg([element], markup) if node.get("t") == "image"][0]
        self.assertEqual(image["fit"], "contain")
        stretched = markup.replace("viewBox='0 0 190 495'>", "viewBox='0 0 190 495' preserveAspectRatio='none'>", 1)
        image = [node for node in self.convert_with_svg([element], stretched) if node.get("t") == "image"][0]
        self.assertEqual(image["fit"], "fill")      # the root opting out really is stretched by browsers

    def test_single_inner_container_is_not_descended(self):
        # bug: relaxed single-child rule replaced the hero section by its inner container
        elements = [{"i": 0, "p": -1, "tag": "main", "r": [0, 0, 1920, 1600], "op": 1},
                    box_el(1, 0, [0, 0, 1920, 800], "rgb(243, 245, 249)"),
                    box_el(2, 1, [340, 100, 1240, 600], tag="div"),
                    box_el(3, 0, [0, 800, 1920, 800], "rgb(0, 0, 0)")]
        self.assertEqual(sorted(round(board["y"]) for board in sections_of(elements)), [0, 800])

    def test_contain_svg_becomes_vector(self):
        element = {"i": 1, "p": -1, "tag": "img", "r": [0, 0, 40, 40], "op": 1, "src": "https://example.com/i.svg",
                   "nat": [48, 42], "fit": "contain"}
        self.assertTrue(any(node.get("t") == "svg" for node in self.convert_with_svg([element], PLAIN_SVG)))

    def test_boxes_snap_to_pixels_but_images_do_not(self):
        box = box_el(1, -1, [0, 3938.44, 1920, 100], "rgb(11, 19, 32)")
        image = {"i": 2, "p": -1, "tag": "img", "r": [344, 1967.82, 1232, 256.45], "op": 1, "src": "https://example.com/a.png",
                 "nat": [1232, 256], "fit": "fill"}
        nodes = converted_nodes([box, image])
        self.assertEqual([node for node in nodes if node.get("t") == "rect"][0]["y"], 3938)
        self.assertEqual([node for node in nodes if node.get("t") == "image"][0]["y"], 1967.82)


if __name__ == "__main__":
    unittest.main()
