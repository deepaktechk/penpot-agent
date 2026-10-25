"""The in-plugin runtime bundle, executed in Node with stub `penpot` globals (no Penpot needed).

Checks the pure helpers whose results Python relies on: base64 / CRC transfer, chunk reassembly.
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
const [bundlePath, script] = process.argv.slice(1);
const source = fs.readFileSync(bundlePath, "utf8");
const storage = {};
new Function("storage", "penpot", "penpotUtils", source + "\nreturn storage.pb && storage.pb.version;")(storage, {}, {});
const pb = storage.pb;
Promise.resolve(new Function("pb", script)(pb)).then(result => console.log(JSON.stringify(result)));
"""


def run(script: str):
    result = subprocess.run(["node", "-e", HARNESS, str(PLUGIN_RUNTIME), script], capture_output=True, text=True, timeout=60)
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


if __name__ == "__main__":
    unittest.main()
