// Build every bundle into src/pbridge/bundles/ with esbuild (type checking is `npm run typecheck`).
//
//   plugin-runtime.js  IIFE injected by Python into the Penpot plugin; stores itself as `storage.pb`
//   capture-page.js    IIFE evaluated inside the captured web page; defines `window.__pbCapture`
//   node-cli.js        node CLI: `capture` (screenshot + layout dump) and `rasterize` (SVG -> PNG)
//
// The bundles live inside the Python package and are committed, so `pip install` / `uv tool
// install` from git works without npm. puppeteer-core is bundled into the node CLI for the
// same reason: an installed pbridge needs only Node.js and Chrome. CI rebuilds and fails if
// the committed bundles are stale.
//
// The plugin runtime and the page library are not minified: their errors come back as stack traces
// that should stay readable.
import { build } from "esbuild";
import { readFileSync } from "node:fs";

const OUT = "../src/pbridge/bundles";
const common = { bundle: true, minify: false, legalComments: "none", logLevel: "warning" };
// optional native add-ons of `ws` (puppeteer's websocket); it falls back to pure JS without them
const NODE_OPTIONAL = ["bufferutil", "utf-8-validate"];

await Promise.all([
  // Penpot's plugin sandbox: plain ES2020; must not start with "use strict" (it is spliced into a function body)
  build({ ...common, entryPoints: ["src/plugin/index.ts"], outfile: `${OUT}/plugin-runtime.js`, format: "iife",
          platform: "neutral", target: "es2020", tsconfigRaw: { compilerOptions: { alwaysStrict: false } } }),
  build({ ...common, entryPoints: ["src/capture/page/index.ts"], outfile: `${OUT}/capture-page.js`, format: "iife",
          platform: "browser", target: "chrome120" }),
  // puppeteer-core is bundled here; minified (names kept, so stack traces stay meaningful) to keep the
  // committed file small - our own code in it is readable in js/src.
  build({ ...common, entryPoints: ["src/node-cli.ts"], outfile: `${OUT}/node-cli.js`, format: "cjs",
          platform: "node", target: "node20", external: NODE_OPTIONAL, minify: true, keepNames: true }),
]);

// guard: the plugin runtime is concatenated with Python code, so it must be a plain statement list
const runtime = readFileSync(`${OUT}/plugin-runtime.js`, "utf8");
if (/^\s*["']use strict["']/.test(runtime)) throw new Error("plugin-runtime.js must not start with 'use strict'");
if (!runtime.includes("__PB_VERSION__")) throw new Error("plugin-runtime.js lost its __PB_VERSION__ placeholder");
console.log(`bundles written to ${OUT}/`);
