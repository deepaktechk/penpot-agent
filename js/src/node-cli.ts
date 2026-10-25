// The Node.js command line of pbridge (bundled to src/pbridge/bundles/node-cli.js).
//
// One bundle for both tools, because each carries puppeteer-core (~3.5 MB):
//   node node-cli.js capture --url URL --out DIR [...]     website screenshot + layout dump
//   node node-cli.js rasterize <src> <out.png> [scale]     SVG -> transparent PNG
// Python calls it through pbridge.paths.node_command().
import { runCapture } from "./capture/main";
import { runRasterize } from "./rasterize/main";

const COMMANDS: Record<string, (argv: string[]) => Promise<void>> = { capture: runCapture, rasterize: runRasterize };

const [command, ...argv] = process.argv.slice(2);
const run = COMMANDS[command];
if (!run) {
  console.error(`usage: node node-cli.js <${Object.keys(COMMANDS).join("|")}> [arguments]`);
  process.exit(2);
}
run(argv).catch(error => { console.error(`[${command}] FAILED`, error && error.stack || error); process.exit(1); });
