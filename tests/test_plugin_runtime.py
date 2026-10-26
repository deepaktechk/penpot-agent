"""The in-plugin runtime bundle, executed in Node with stub `penpot` globals (no Penpot needed).

Checks the pure helpers whose results Python relies on: base64 / CRC transfer, chunk reassembly,
and shape lookup by id (against stub pages).
"""
import base64
import json
import shutil
import subprocess
import unittest
import zlib

from pbridge.paths import PLUGIN_RUNTIME

# loads the bundle the way bridge.py does (statements + return), then runs DATA.script against `pb`
HARNESS = r"""
const fs = require("fs");
const [bundlePath, script, globalsScript] = process.argv.slice(1);
const source = fs.readFileSync(bundlePath, "utf8");
const storage = {};
const globals = globalsScript ? new Function(globalsScript)() : {penpot: {}, penpotUtils: {}};
new Function("storage", "penpot", "penpotUtils", source + "\nreturn storage.pb && storage.pb.version;")(storage, globals.penpot, globals.penpotUtils);
const pb = storage.pb;
Promise.resolve(new Function("pb", script)(pb)).then(result => console.log(JSON.stringify(result)));
"""


def run(script: str, globals_script: str = ""):
    """Run `script` against pb; globals_script returns {penpot, penpotUtils} stubs (default: empty)."""
    result = subprocess.run(["node", "-e", HARNESS, str(PLUGIN_RUNTIME), script, globals_script],
                            capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


@unittest.skipUnless(shutil.which("node") and PLUGIN_RUNTIME.exists(), "node or plugin-runtime.js missing")
class PluginRuntime(unittest.TestCase):
    def test_to_base64_matches_python(self):
        # the plugin sandbox has no guaranteed btoa: pb.toBase64 is a plain-JS encoder used by exports
        samples = ["", "f", "fo", "foo", "foob", "fooba", "foobar"]
        encoded = run("return " + json.dumps(samples) + ".map(text => pb.toBase64(new TextEncoder().encode(text)));")
        self.assertEqual(encoded, [base64.b64encode(text.encode()).decode() for text in samples])
        big = run("const bytes = new Uint8Array(70000).map((_, i) => (i * 7919) % 256); return pb.toBase64(bytes);")
        self.assertEqual(big, base64.b64encode(bytes((i * 7919) % 256 for i in range(70000))).decode())

    def test_crc32_matches_zlib(self):
        data = b"penpot-agent upload check"
        crc = run(f"return pb.crc32(pb.b64({json.dumps(base64.b64encode(data).decode())}));")
        self.assertEqual(crc, zlib.crc32(data))

    def test_chunks_are_reassembled_in_order(self):
        self.assertEqual(run("pb.chunkPut('t', 1, 2, 'world'); pb.chunkPut('t', 0, 2, 'hello '); return pb.chunkTake('t');"),
                         "hello world")


    def test_by_id_uses_page_lookups_not_the_slow_document_search(self):
        # penpotUtils.findShapeById scans the document (~600 ms per id on a 1400-shape page);
        # page.getShapeById is a map lookup: byId must use it, current page first, then the others
        stubs = """
            const page = (id, shapes) => ({id, getShapeById: shapeId => shapes[shapeId] || null});
            const current = page('p1', {a: {id: 'a'}}), other = page('p2', {b: {id: 'b'}});
            return {penpot: {currentPage: current},
                    penpotUtils: {getPages: () => [current, other],
                                  findShapeById: () => { throw new Error('slow document search used'); }}};"""
        self.assertEqual(run("return [pb.byId('a'), pb.byId('b'), pb.byId('missing'), pb.byId(null)];", stubs),
                         [{"id": "a"}, {"id": "b"}, None, None])


    def test_upload_urls_runs_concurrently_and_reports_each_result(self):
        # one plugin call uploads many public URLs at once; a failure only affects its own key
        stubs = """
            let active = 0, peak = 0;
            const uploadMediaUrl = async (name, url) => {
              active++; peak = Math.max(peak, active);
              await new Promise(resolve => setTimeout(resolve, 20));
              active--;
              if (url.includes('broken')) throw new Error('fetch failed');
              return {id: 'media-' + name, name, width: 10, height: 10, mtype: 'image/png'};
            };
            globalThis.peakUploads = () => peak;
            return {penpot: {uploadMediaUrl}, penpotUtils: {}};"""
        result = run("""return pb.uploadUrls([{key: 'a', url: 'https://x.test/a.png'}, {key: 'b', url: 'https://x.test/broken.png'},
                                              {key: 'c', url: 'https://x.test/c.svg'}])
                       .then(results => ({results, peak: peakUploads(), known: Object.keys(pb.imgs).sort()}));""", stubs)
        self.assertEqual(result["peak"], 3)
        self.assertEqual(result["results"]["a"]["id"], "media-a")
        self.assertIn("fetch failed", result["results"]["b"]["error"])
        self.assertEqual(result["known"], ["a", "c"])


# siblings of one parent; setParentIndex(i) takes the shape out and inserts it at i (bottom = 0)
LAYER_STUBS = """
    const siblings = [];
    const shapes = {};
    let moves = 0;
    for (const id of DATA_ORDER) {
      const shape = {id, parent: {id: 'parent'},
                     get parentIndex() { return siblings.indexOf(this); },
                     setParentIndex(index) { siblings.splice(siblings.indexOf(this), 1); siblings.splice(index, 0, this); moves++; }};
      siblings.push(shape); shapes[id] = shape;
    }
    globalThis.layerState = {siblings, moves: () => moves};
    const page = {id: 'p1', getShapeById: id => shapes[id] || null};
    return {penpot: {currentPage: page}, penpotUtils: {getPages: () => [page]}};"""


def order_children(current: list[str], wanted: list[str]) -> dict:
    stubs = LAYER_STUBS.replace("DATA_ORDER", json.dumps(current))
    return run(f"const result = pb.orderChildren({json.dumps(wanted)});"
               "return {result, order: layerState.siblings.map(shape => shape.id), moves: layerState.moves()};", stubs)


@unittest.skipUnless(shutil.which("node") and PLUGIN_RUNTIME.exists(), "node or plugin-runtime.js missing")
class LayerOrder(unittest.TestCase):
    """Sections must end up in spec order (bottom to top): a rebuilt or staged section is appended on top."""

    def test_already_in_order_moves_nothing(self):
        self.assertEqual(order_children(["a", "b", "c"], ["a", "b", "c"])["moves"], 0)

    def test_one_section_appended_on_top_takes_one_move(self):
        # "b" was rebuilt and appended last: the longest run in order (a, c, d) stays put
        outcome = order_children(["a", "c", "d", "b"], ["a", "b", "c", "d"])
        self.assertEqual(outcome["order"], ["a", "b", "c", "d"])
        self.assertEqual(outcome["moves"], 1)

    def test_first_section_appended_on_top(self):
        outcome = order_children(["b", "c", "a"], ["a", "b", "c"])
        self.assertEqual(outcome["order"], ["a", "b", "c"])
        self.assertEqual(outcome["moves"], 1)

    def test_reversed_order(self):
        outcome = order_children(["d", "c", "b", "a"], ["a", "b", "c", "d"])
        self.assertEqual(outcome["order"], ["a", "b", "c", "d"])
        self.assertEqual(outcome["moves"], 3)

    def test_other_layers_keep_their_place_and_ours_get_relative_order(self):
        outcome = order_children(["x", "d", "a", "y", "b", "c"], ["a", "b", "c", "d"])
        ours = [shape_id for shape_id in outcome["order"] if shape_id in "abcd"]
        self.assertEqual(ours, ["a", "b", "c", "d"])
        self.assertTrue(outcome["result"]["ok"])

    def test_missing_shapes_are_ignored(self):
        outcome = order_children(["b", "a"], ["a", "gone", "b"])
        self.assertEqual(outcome["order"], ["a", "b"])


# a staged section on page "staging": a component whose instance is a copy with fresh ids
STAGING_STUBS = """
    const tree = (prefix) => ({id: prefix + 'root', name: 'Section', x: 0, y: 0,
      children: [{id: prefix + 'a', children: [{id: prefix + 'a1'}]}, {id: prefix + 'b'}]});
    const staged = tree('s-');
    const target = {id: 'target', getShapeById: id => (id === 'board' ? board : null)};
    const staging = {id: 'staging', getShapeById: id => (id === 's-root' ? staged : null)};
    const board = {id: 'board', appended: [], appendChild(shape) { this.appended.push(shape.id); }};
    let detached = 0;
    const component = {id: 'comp-1', instance: () => Object.assign(tree('c-'), {detach() { detached++; }, remove() {}})};
    // plugin Page objects come from penpot.currentFile.pages; penpotUtils.getPages() is plain data
    const penpot = {currentPage: target, currentFile: {pages: [target, staging]},
                    openPage: async page => { if (!page || !page.id) throw new Error('Expected a Page object'); penpot.currentPage = page; },
                    library: {local: {components: [component], createComponent: () => component}}};
    globalThis.stagingState = {board, detached: () => detached};
    return {penpot, penpotUtils: {getPages: () => [{id: 'target'}, {id: 'staging'}]}};"""


@unittest.skipUnless(shutil.which("node") and PLUGIN_RUNTIME.exists(), "node or plugin-runtime.js missing")
class StagedTransfer(unittest.TestCase):
    def test_copy_ids_map_to_staged_ids_in_preorder(self):
        result = run("return (async () => {"
                     "const item = {component: 'comp-1', order: ['s-root', 's-a', 's-a1', 's-b'], x: 10, y: 20};"
                     "const transfer = await pb.stageTransfer([item], 'target', 'board');"
                     "return {transfer, appended: stagingState.board.appended, detached: stagingState.detached()}; })();",
                     STAGING_STUBS)
        self.assertEqual(result["transfer"]["ids"], {"s-root": "c-root", "s-a": "c-a", "s-a1": "c-a1", "s-b": "c-b"})
        self.assertEqual(result["appended"], ["c-root"])
        self.assertEqual(result["detached"], 1)

    def test_a_copy_with_another_shape_count_is_refused(self):
        result = run("return (async () => {"
                     "const item = {component: 'comp-1', order: ['s-root', 's-a'], x: 0, y: 0};"
                     "const transfer = await pb.stageTransfer([item], 'target', 'board');"
                     "return {transfer, appended: stagingState.board.appended}; })();", STAGING_STUBS)
        self.assertEqual(result["transfer"]["roots"], [])
        self.assertEqual(result["transfer"]["ids"], {})
        self.assertIn("expected 2", result["transfer"]["failed"][0]["error"])


# two pages with a board of the same name; the current page is "bench" (empty unless given boards)
PAGE_BOARD_STUBS = """
    const board = (id, name) => ({id, name, type: 'board', x: 0, y: 0, width: 100, height: 100, children: [],
                                  resize() {}});
    const real = board('real-board', 'Landing');
    const realPage = {id: 'page-1', name: 'Page 1', getShapeById: id => (id === real.id ? real : null), root: {children: [real]}};
    const benchBoards = CURRENT_BOARDS;
    const benchPage = {id: 'bench', name: 'bench', root: {children: benchBoards},
                       getShapeById: id => benchBoards.find(shape => shape.id === id) || null};
    const created = [];
    const penpot = {currentPage: benchPage, root: benchPage.root,
                    createBoard: () => { const made = board('new-board', ''); created.push(made); benchBoards.push(made); return made; }};
    // like Penpot: plugin Page objects only through penpot.currentFile.pages, penpotUtils.getPages() is plain data
    penpot.currentFile = {pages: [realPage, benchPage]};
    const penpotUtils = {getPages: () => [{id: realPage.id, name: realPage.name}, {id: benchPage.id, name: benchPage.name}],
                         findShapes: (match) => [real, ...benchBoards].filter(match)};
    // the page-board snippet runs in the test script, which only gets `pb`: publish the stubs too
    Object.assign(globalThis, {boardState: {created}, penpot, penpotUtils});
    return {penpot, penpotUtils};"""


def page_board(data: dict, current_boards: str = "[]"):
    from pbridge.build.page_board import _PAGE_BOARD_JS
    stubs = PAGE_BOARD_STUBS.replace("CURRENT_BOARDS", current_boards)
    return run(f"const DATA = {json.dumps(data)};\nconst result = (() => {{{_PAGE_BOARD_JS}}})();"
               "return {result, created: boardState.created.length};", stubs)


@unittest.skipUnless(shutil.which("node") and PLUGIN_RUNTIME.exists(), "node or plugin-runtime.js missing")
class PageBoardLookup(unittest.TestCase):
    """`--page` builds must never pick a same-named board on another page (2026-10-26: a bench build
    found the real Clockify board on Page 1 and every section failed with "parent not found")."""

    def test_name_lookup_ignores_boards_on_other_pages(self):
        outcome = page_board({"id": None, "name": "Landing", "create": True})
        self.assertEqual(outcome["result"], "new-board")
        self.assertEqual(outcome["created"], 1)

    def test_name_lookup_finds_the_board_on_the_current_page(self):
        outcome = page_board({"id": None, "name": "Landing", "create": True}, "[board('bench-board', 'Landing')]")
        self.assertEqual(outcome["result"], "bench-board")
        self.assertEqual(outcome["created"], 0)

    def test_a_stored_board_on_another_page_is_an_error_not_a_new_board(self):
        outcome = page_board({"id": "real-board", "name": "Landing", "create": True})
        self.assertIn("Page 1", outcome["result"]["error"])
        self.assertEqual(outcome["created"], 0)


# a text whose colours are kept per character; getRange(...).fills reads "mixed" or the colour
TEXT_RANGE_STUBS = """
    const characters = "Fieldy's All-In-One Field Service\\nSoftware Platform Crushes\\nInefficiency";
    const colors = Array.from(characters, () => '#155DFC');      // Penpot bled the first range into all
    const range = (start, end) => ({
      get fills() { const used = new Set(colors.slice(start, end)); return used.size === 1 ? [{fillColor: [...used][0]}] : 'mixed'; },
      set fills(value) { for (let i = start; i < end; i++) colors[i] = value[0].fillColor; },
      fontWeight: '700', fontSize: '30'});
    const text = {id: 'heading', type: 'text', characters, getRange: range};
    const page = {id: 'p1', getShapeById: id => (id === 'heading' ? text : null)};
    globalThis.textState = {colors, characters};
    return {penpot: {currentPage: page, fonts: {all: [{name: 'Inter', variants: [{fontWeight: '700'}]}]}},
            penpotUtils: {getPages: () => [{id: 'p1'}]}};"""


@unittest.skipUnless(shutil.which("node") and PLUGIN_RUNTIME.exists(), "node or plugin-runtime.js missing")
class RangeVerification(unittest.TestCase):
    def test_style_that_bled_outside_its_range_is_reverted(self):
        # 2026-10-26 getfieldy.com: the blue range 0-51 of a heading coloured the whole text;
        # verifyRanges only checked the ranges themselves, so "Crushes Inefficiency" stayed blue
        result = run("const item = {id: 'heading', ranges: [[0, 51, {color: '#155DFC'}]], font: 'Inter',"
                     "              base: {color: '#101828', weight: 700, size: 30}};"
                     "const outcome = pb.verifyRanges([item]);"
                     "return {outcome, head: [...new Set(textState.colors.slice(0, 51))],"
                     "        tail: [...new Set(textState.colors.slice(51))]};", TEXT_RANGE_STUBS)
        self.assertEqual(result["head"], ["#155DFC"])
        self.assertEqual(result["tail"], ["#101828"])
        self.assertGreaterEqual(result["outcome"]["fixed"], 1)

    def test_line_break_keeping_the_previous_style_is_not_a_bleed(self):
        # getfieldy.com: "…Management\\nSoftware Serves": only the (never painted) line break kept the
        # blue of the range before it; re-applying cannot change it, so it warned "still re-applying"
        result = run("const lineBreak = textState.characters.indexOf('\\n', 40);"
                     "textState.colors.fill('#101828', 51); textState.colors[lineBreak] = '#155DFC';"
                     "const item = {id: 'heading', ranges: [[0, lineBreak, {color: '#155DFC'}]], font: 'Inter',"
                     "              base: {color: '#101828', weight: 700, size: 30}};"
                     "textState.colors.fill('#155DFC', 0, lineBreak); textState.colors.fill('#101828', lineBreak + 1);"
                     "return pb.verifyRanges([item]);", TEXT_RANGE_STUBS)
        self.assertEqual(result["fixed"], 0)

    def test_correct_text_is_left_alone(self):
        result = run("textState.colors.fill('#101828', 51);"
                     "const item = {id: 'heading', ranges: [[0, 51, {color: '#155DFC'}]], font: 'Inter',"
                     "              base: {color: '#101828', weight: 700, size: 30}};"
                     "return pb.verifyRanges([item]);", TEXT_RANGE_STUBS)
        self.assertEqual(result["fixed"], 0)


CLEANUP_STUBS = """
    const page = (id, mark) => ({id, name: id, removed: false, getPluginData: () => mark, remove() { this.removed = true; },
                                 getShapeById: () => null});
    const pages = [page('page-1', ''), page('stage-a', 'staging'), page('stage-b', 'staging')];
    const penpot = {currentPage: pages[1], currentFile: {pages},
                    openPage: async target => { if (!target || !target.id) throw new Error('Expected a Page object'); penpot.currentPage = target; }};
    globalThis.cleanupState = {pages, penpot};
    return {penpot, penpotUtils: {getPages: () => pages.map(entry => ({id: entry.id}))}};"""


@unittest.skipUnless(shutil.which("node") and PLUGIN_RUNTIME.exists(), "node or plugin-runtime.js missing")
class StagingCleanup(unittest.TestCase):
    def test_leaves_a_staging_page_and_removes_only_staging_pages(self):
        # 2026-10-26: a crashed staged build left Penpot on a temporary page with four more behind it
        result = run("return (async () => { const removed = await pb.stageCleanup(null);"
                     "return {removed, current: cleanupState.penpot.currentPage.id,"
                     "        gone: cleanupState.pages.filter(entry => entry.removed).map(entry => entry.id)}; })();", CLEANUP_STUBS)
        self.assertEqual(result, {"removed": 2, "current": "page-1", "gone": ["stage-a", "stage-b"]})


if __name__ == "__main__":
    unittest.main()


# just enough of Penpot for pb.buildMany: boards, rectangles, flex layouts (layoutChild appears with the layout)
BUILD_STUBS = """
    let counter = 0;
    const shapes = {};
    const makeShape = (type) => {
      const shape = {id: type + '-' + (++counter), type, x: 0, y: 0, width: 100, height: 100, children: [], name: '', fills: [],
        resize(width, height) { this.width = width; this.height = height; },
        appendChild(child) { child.parent = this; this.children.push(child); if (this.flex) child.layoutChild = {}; },
        setParentIndex() {},
        addFlexLayout() { this.flex = {}; this.children.forEach(child => { child.layoutChild = {}; }); return this.flex; },
        get parentIndex() { return this.parent ? this.parent.children.indexOf(this) : 0; }};
      shapes[shape.id] = shape;
      return shape;
    };
    const root = makeShape('root');
    const page = {id: 'page', getShapeById: id => shapes[id] || null, root};
    const penpot = {currentPage: page, root, createBoard: () => makeShape('board'), createRectangle: () => makeShape('rect')};
    return {penpot, penpotUtils: {}};"""


@unittest.skipUnless(shutil.which("node") and PLUGIN_RUNTIME.exists(), "node or plugin-runtime.js missing")
class FlexSettling(unittest.TestCase):
    def test_absolute_children_are_recorded_where_the_builder_placed_them(self):
        # getfieldy.com video thumbnail: a contain-fitted picture is centred in its 768x500 box (y + 34); the
        # settle step put absolute children back at the node's x/y, i.e. the box's top-left, 34 px too high
        spec = {"t": "board", "key": "card", "x": 0, "y": 0, "w": 768, "h": 600,
                "layout": {"type": "flex", "dir": "column", "gap": 0, "pin": True},
                "children": [{"t": "image", "key": "video", "img": "thumb", "fit": "contain", "x": 0, "y": 0, "w": 768, "h": 500,
                              "child": {"absolute": True}},
                             {"t": "rect", "key": "caption", "x": 0, "y": 500, "w": 768, "h": 100, "child": {"sizing": ["fix", "fix"]}}]}
        result = run(f"pb.imgs.thumb = {{width: 768, height: 432}}; const built = pb.buildMany([{json.dumps(spec)}], null);"
                     "return built.pinItems;", BUILD_STUBS)
        absolute = result[0]["absolute"]
        self.assertEqual(len(absolute), 1)
        self.assertEqual((absolute[0][1], absolute[0][2]), (0, 34))
        self.assertEqual([entry[1:3] for entry in result[0]["flow"]], [[0, 500]])
