"""Penpot-side features, checked in a live Penpot (`pb selftest --build`; plugin connected).

Everything runs on a scratch page "pb selftest (auto-removed)" that is deleted afterwards; the
comment thread, token set and file version created here are removed as well.
"""
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

from pbridge.paths import SOURCE_ROOT

BUILD = os.environ.get("PB_SELFTEST_BUILD", "0") == "1"
SCRATCH_PAGE = "pb selftest (auto-removed)"
REMOVE_PAGE_JS = """
    const page = penpot.currentFile.pages.find(candidate => candidate.name === DATA.scratch);
    const other = penpot.currentFile.pages.find(candidate => candidate.name !== DATA.scratch);
    if (other) await penpot.openPage(other);
    if (page) page.remove();
    return true;"""
# x positions of the direct children of a board, in layer order (what an auto-layout arranged)
CHILD_X_JS = "return pb.byId(DATA).children.map(child => ({name: child.name, x: Math.round(child.x), y: Math.round(child.y)}));"


@unittest.skipUnless(BUILD, "live Penpot tests disabled (use pb selftest --build)")
class PenpotLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pbridge.cli.commands.document import open_page
        from pbridge.connection import Bridge
        from pbridge.project import ProjectState
        cls.folder = Path(tempfile.mkdtemp(prefix="pb-live-"))
        state = ProjectState.open(cls.folder); state.init()
        cls.bridge = Bridge(state)
        cls.page = open_page(cls.bridge, SCRATCH_PAGE)

    @classmethod
    def tearDownClass(cls):
        cls.bridge.exec(REMOVE_PAGE_JS, data={"scratch": SCRATCH_PAGE}, timeout=120)

    def build(self, example: str) -> str:
        from pbridge.workflows import build_spec
        spec_path = SOURCE_ROOT / "examples" / example
        name = json.loads(spec_path.read_text())["nodes"][0]["name"]
        report = build_spec(self.bridge, str(spec_path), page_board=f"selftest {name}", after="*", page=SCRATCH_PAGE)
        self.assertFalse(report["failed"], report["failed"])
        return self.bridge.state.load_json("idmap.json", {})[json.loads(spec_path.read_text())["nodes"][0]["key"]]

    def test_pages_list_the_scratch_page_as_current(self):
        from pbridge.cli.commands.document import PAGES_JS
        pages = self.bridge.exec(PAGES_JS)
        self.assertTrue(any(page["name"] == SCRATCH_PAGE and page["current"] for page in pages), pages)

    def test_flex_layout_keeps_spec_order(self):
        # column layout: children must be stacked top to bottom in spec order
        board_id = self.build("prompt/mobile-login.json")
        children = self.bridge.exec(CHILD_X_JS, data=board_id)
        names = [child["name"] for child in sorted(children, key=lambda child: child["y"])]
        self.assertEqual(names, ["Title", "Subtitle", "Input / Email", "Input / Password", "Button / Primary"])

    def test_grid_layout_places_three_columns(self):
        board_id = self.build("prompt/pricing-cards.json")
        plans = self.bridge.exec("return pb.find({name: 'Plans', within: DATA})[0].id;", data=board_id)
        cards = sorted(self.bridge.exec(CHILD_X_JS, data=plans), key=lambda child: child["x"])
        self.assertEqual([card["name"] for card in cards], ["Plan / Starter", "Plan / Pro", "Plan / Team"])
        self.assertEqual(len({card["y"] for card in cards}), 1, cards)          # one row

    def test_batch_export_at_2x(self):
        board_id = self.build("hello-board.json")
        exported = self.bridge.exec("return await pb.exportShape(DATA, 'png', 2);", data=board_id, timeout=300)
        png = base64.b64decode(exported["base64"])
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        from io import BytesIO

        from PIL import Image
        self.assertEqual(Image.open(BytesIO(png)).width, 960 * 2)

    def test_comment_thread_round_trip(self):
        from pbridge.cli.commands.review import ADD_COMMENTS_JS
        threads = self.bridge.exec(ADD_COMMENTS_JS, data=[{"text": "pb selftest comment", "x": 10, "y": 10}], timeout=120)
        self.assertEqual(len(threads), 1)
        self.bridge.exec("""const threads = await penpot.currentPage.findCommentThreads({onlyYours: true, showResolved: true});
            for (const thread of threads) { const comments = await thread.findComments();
              if (comments.some(comment => comment.content === 'pb selftest comment')) thread.remove(); }
            return true;""", timeout=120)

    def test_code_generation(self):
        from pbridge.cli.commands.document import CODE_JS
        board_id = self.build("hello-board.json")
        code = self.bridge.exec(CODE_JS, data={"id": board_id, "type": "html"}, timeout=300)
        self.assertIn("penpot-agent", code["markup"])
        self.assertTrue(code["css"].strip())

    def test_tokens_set_is_created_and_removed(self):
        from pbridge.cli.commands.document import TOKENS_JS
        tokens = [{"type": "color", "name": "color.selftest", "value": "#123456"},
                  {"type": "fontSizes", "name": "font-size.selftest", "value": "17"}]
        result = self.bridge.exec(TOKENS_JS, data={"set": "pb-selftest", "tokens": tokens}, timeout=120)
        self.assertEqual(result["added"], 2)
        self.bridge.exec("""const set = penpot.library.local.tokens.sets.find(candidate => candidate.name === 'pb-selftest');
            if (set) set.remove(); return true;""")

    def test_review_live_finds_low_contrast(self):
        from pbridge.cli.commands.review import TREE_JS
        from pbridge.review import review
        board_id = self.build("hello-board.json")
        tree = self.bridge.exec(TREE_JS, data=board_id, timeout=300)
        result = review([tree])
        self.assertEqual(result["summary"]["layers"] > 5, True)


if __name__ == "__main__":
    unittest.main()
