"""Run cache (no Penpot): convert cache keys, source digests, and the rebuild short-circuit rules."""
import json
import tempfile
import unittest
from pathlib import Path

from pbridge.project import ProjectState
from pbridge.run_cache import RunCache, convert_key, file_digest, rebuild_key, source_digest


def make_state(root: Path) -> ProjectState:
    state = ProjectState.open(root)
    state.init()
    return state


class SourceDigest(unittest.TestCase):
    def test_changes_when_a_source_file_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder)
            (package / "sub").mkdir()
            (package / "a.py").write_text("x = 1\n")
            (package / "sub" / "b.py").write_text("y = 2\n")
            before = source_digest([package])
            self.assertEqual(before, source_digest([package]))
            (package / "sub" / "b.py").write_text("y = 3\n")
            self.assertNotEqual(before, source_digest([package]))

    def test_ignores_bytecode(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder)
            (package / "a.py").write_text("x = 1\n")
            before = source_digest([package])
            (package / "__pycache__").mkdir()
            (package / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\x00\x01")
            self.assertEqual(before, source_digest([package]))


class ConvertKey(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.layout = root / "layout.json"
        self.layout.write_text(json.dumps({"width": 1920, "elements": []}))
        self.screenshot = root / "shot.png"
        self.screenshot.write_bytes(b"png bytes")
        self.options = {"fallback_font": "Inter", "group": True, "system_font": "Inter"}
        self.fonts = {"Inter", "Roboto"}

    def tearDown(self):
        self.folder.cleanup()

    def key(self, **changes) -> str:
        arguments = {"layout_file": self.layout, "screenshot": self.screenshot, "options": self.options,
                     "available_fonts": self.fonts, "source": "src1"}
        arguments.update(changes)
        return convert_key(**arguments)

    def test_same_inputs_same_key_regardless_of_order(self):
        reordered = dict(reversed(list(self.options.items())))
        self.assertEqual(self.key(), self.key(options=reordered, available_fonts={"Roboto", "Inter"}))

    def test_every_input_changes_the_key(self):
        base = self.key()
        self.assertNotEqual(base, self.key(options={**self.options, "fallback_font": "Roboto"}))
        self.assertNotEqual(base, self.key(available_fonts={"Inter"}))
        self.assertNotEqual(base, self.key(source="src2"))
        self.assertNotEqual(base, self.key(screenshot=None))
        self.layout.write_text(json.dumps({"width": 1440, "elements": []}))
        self.assertNotEqual(base, self.key())

    def test_unknown_fonts_differ_from_an_empty_font_list(self):
        self.assertNotEqual(self.key(available_fonts=None), self.key(available_fonts=set()))


class RebuildKey(unittest.TestCase):
    def test_depends_on_spec_reference_runtime_and_options(self):
        base = rebuild_key("specdigest", "refdigest", "runtime1", {"fix": True, "font": "Inter"})
        self.assertEqual(base, rebuild_key("specdigest", "refdigest", "runtime1", {"font": "Inter", "fix": True}))
        self.assertNotEqual(base, rebuild_key("other", "refdigest", "runtime1", {"fix": True, "font": "Inter"}))
        self.assertNotEqual(base, rebuild_key("specdigest", "other", "runtime1", {"fix": True, "font": "Inter"}))
        self.assertNotEqual(base, rebuild_key("specdigest", "refdigest", "runtime2", {"fix": True, "font": "Inter"}))
        self.assertNotEqual(base, rebuild_key("specdigest", "refdigest", "runtime1", {"fix": False, "font": "Inter"}))


class RunCacheStore(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.state = make_state(Path(self.folder.name))
        self.cache = RunCache(self.state)

    def tearDown(self):
        self.folder.cleanup()

    def test_round_trip_and_key_mismatch(self):
        self.cache.store("convert", "key1", {"spec": "a.json"})
        self.assertEqual(self.cache.lookup("convert", "key1"), {"spec": "a.json"})
        self.assertIsNone(self.cache.lookup("convert", "key2"))
        self.assertIsNone(self.cache.lookup("rebuild", "key1"))

    def test_corrupt_cache_file_is_a_miss(self):
        self.cache.store("convert", "key1", {"spec": "a.json"})
        self.state.path("cache", "convert.json").write_text("{not json")
        self.assertIsNone(self.cache.lookup("convert", "key1"))

    def test_file_digest_of_missing_file(self):
        self.assertEqual(file_digest(None), "none")
        self.assertEqual(file_digest(Path(self.folder.name) / "missing.png"), "missing")


class RebuildShortCircuit(unittest.TestCase):
    """A previous rebuild is reused only when nothing that shapes its result changed."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.state = make_state(Path(self.folder.name))
        self.cache = RunCache(self.state)
        self.render = self.state.path("renders", "page.png")
        self.render.write_bytes(b"png")
        self.cache.store_rebuild("key1", revision="file-1@77", board="board-1", render=str(self.render), result={"ok": True})

    def tearDown(self):
        self.folder.cleanup()

    def test_hit_when_key_revision_and_board_match(self):
        hit = self.cache.reusable_rebuild("key1", revision="file-1@77", board="board-1")
        self.assertEqual(hit["result"], {"ok": True})

    def test_any_edit_in_penpot_is_a_miss(self):
        self.assertIsNone(self.cache.reusable_rebuild("key1", revision="file-1@78", board="board-1"))

    def test_another_file_with_the_same_revn_is_a_miss(self):
        self.assertIsNone(self.cache.reusable_rebuild("key1", revision="file-2@77", board="board-1"))

    def test_other_inputs_or_board_are_a_miss(self):
        self.assertIsNone(self.cache.reusable_rebuild("key2", revision="file-1@77", board="board-1"))
        self.assertIsNone(self.cache.reusable_rebuild("key1", revision="file-1@77", board="board-2"))

    def test_unknown_revision_is_a_miss(self):
        self.assertIsNone(self.cache.reusable_rebuild("key1", revision=None, board="board-1"))

    def test_deleted_render_is_a_miss(self):
        self.render.unlink()
        self.assertIsNone(self.cache.reusable_rebuild("key1", revision="file-1@77", board="board-1"))


if __name__ == "__main__":
    unittest.main()
