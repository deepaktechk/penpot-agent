// pbridge in-plugin runtime (bundled to src/pbridge/bundles/plugin-runtime.js).
//
// Python (src/pbridge/connection/bridge.py) sends this bundle through MCP `execute_code`;
// it assembles the `pb` API on the runtime state and stores it as `storage.pb`, where every
// later call finds it. Calls look like:
//
//     const pb = storage.pb; const DATA = {...};  <body using pb.*, DATA, penpot>
//
// The public surface below is a contract with the Python side - keep names stable.
import { lint, stats } from "./analysis";
import { buildMany, build, existing, groupShapes, orderChildren, removeMany, ungroup } from "./builder";
import { chunkPut, chunkTake } from "./chunks";
import { font, variant } from "./fonts";
import { paint, shadows, strokes } from "./paints";
import { patch } from "./patch";
import { find } from "./query";
import { serialize, tree } from "./serialize";
import { stageBegin, stageCleanup, stageFinish, stageTransfer } from "./staging";
import { byId, runtime, sleep, warn } from "./state";
import { fitTexts, gapsBetween, makeText, verifyRanges } from "./text";
import { b64, crc32, exportShape, registerImages, toBase64, uploadB64, uploadUrl, uploadUrls } from "./assets";
import { addColor, addTypography, makeComponent } from "./library";

const api = Object.assign(runtime, {
  // utils
  sleep, byId, warn,
  // chunked transfer
  chunkPut, chunkTake,
  // fonts & paints
  font, variant, paint, strokes, shadows,
  // building
  makeText, build, buildMany, fitTexts, verifyRanges, gapsBetween, groupShapes, ungroup, removeMany, existing, orderChildren,
  stageBegin, stageFinish, stageTransfer, stageCleanup,
  // reading
  serialize, tree, find,
  // editing
  patch,
  // assets
  b64, crc32, uploadB64, uploadUrl, uploadUrls, registerImages, toBase64, exportShape,
  // library
  addColor, addTypography, makeComponent,
  // analysis
  stats, lint,
});

storage.pb = api;
