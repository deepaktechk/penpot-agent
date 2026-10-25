// Rasterize an SVG (URL or file) to a transparent PNG with Chrome (`node-cli.js rasterize`).
// Penpot media cannot be SVG bytes, so SVGs Penpot cannot fetch itself are relayed as PNG.
//
// usage: node node-cli.js rasterize <src> <out.png> [scale=2]   -> prints {"w", "h", "scale"}
import { findChrome, launchChrome } from "../shared/chrome";

/** `node-cli.js rasterize <src> <out.png> [scale]` */
export const runRasterize = async (argv: string[]): Promise<void> => {
  const [src, out, scaleArg] = argv;
  const scale = +(scaleArg || 2);
  const executable = findChrome();
  if (!executable) throw new Error("No Chrome/Chromium found; set CHROME_PATH");
  const browser = await launchChrome(executable);
  const page = await browser.newPage();
  await page.goto(src, { waitUntil: "networkidle0" });
  // the SVG's rendered size at 1x
  const size = await page.evaluate(() => {
    const bounds = document.querySelector("svg")!.getBoundingClientRect();
    return [Math.ceil(bounds.width), Math.ceil(bounds.height)];
  });
  await page.setViewport({ width: size[0], height: size[1], deviceScaleFactor: scale });
  await page.evaluate(() => { document.documentElement.style.background = "transparent"; if (document.body) document.body.style.margin = "0"; });
  await page.screenshot({ path: out as `${string}.png`, omitBackground: true, clip: { x: 0, y: 0, width: size[0], height: size[1] } });
  console.log(JSON.stringify({ w: size[0], h: size[1], scale }));
  await browser.close();
};
