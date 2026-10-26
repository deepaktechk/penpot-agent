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


if __name__ == "__main__":
    unittest.main()
