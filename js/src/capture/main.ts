// Website capture for pbridge (`node-cli.js capture`): screenshot + layout dump.
//
// Pipeline (order matters - each step relies on the previous ones):
//   0. session                 colour scheme, cookies (or a logged-in --user-data-dir profile)
//   1. warm-up visit           fill the HTTP cache with the web fonts
//   2. load with real fonts    reload while text is painted with a fallback font (font-display: swap)
//   3. clicks                  --click selectors (consent buttons, tabs)
//   4. lazy content            scroll through the page
//   5. fonts                   required families loaded, every used face force-loaded
//   6. reflow + images         stable document height, all images complete
//   7. freeze                  pause animations, wait for stillness, stop JS timers
//   8. overlays + hide CSS     consent banners / chat widgets, --hide selectors
//   9. dump + screenshot       one layout for both (viewport = full height)
// Prints one JSON summary line on stdout; progress goes to stderr.
import fs from "node:fs";
import { findChrome, launchChrome } from "../shared/chrome";
import { parseOptions } from "./options";
import { log } from "./page-lib";
import { dumpAndScreenshot } from "./steps/dump";
import { applyHideAndFreeze, freezeMotion, hideOverlays } from "./steps/freeze";
import { FontDisplayOverride } from "./steps/font-display";
import { loadWithRealFonts, warmUp } from "./steps/load";
import { prepareSession } from "./steps/session";
import { clickAll, forceFonts, triggerLazyContent, waitForImages, waitForRequiredFonts, waitStableHeight } from "./steps/prepare";

const CHROME_ARGS = ["--hide-scrollbars", "--force-color-profile=srgb", "--font-render-hinting=none"];

/** `node-cli.js capture <args>`: see options.ts for the arguments. */
export const runCapture = async (argv: string[]): Promise<void> => {
  const opts = parseOptions(argv);
  if (!opts) { console.error("need --url and --out"); process.exit(2); }
  fs.mkdirSync(opts.out, { recursive: true });
  const executable = findChrome(opts.chrome);
  if (!executable) { console.error("No Chrome/Chromium found; pass --chrome PATH"); process.exit(2); }

  const browser = await launchChrome(executable, CHROME_ARGS, opts.userDataDir);
  const page = await browser.newPage();
  await page.setViewport({ width: opts.width, height: 1080, deviceScaleFactor: opts.dpr });
  await prepareSession(page, opts.url, opts.colorScheme, opts.cookies);

  if (opts.warmup) await warmUp(page, opts.url, opts.timeoutMs);
  await loadWithRealFonts(page, opts.url, opts.timeoutMs, new FontDisplayOverride(page));
  await clickAll(page, opts.click);
  if (opts.scroll) await triggerLazyContent(page);
  await waitForRequiredFonts(page, opts.fonts);
  await forceFonts(page);
  await waitStableHeight(page);
  await waitForImages(page);
  const stable = opts.freeze ? await freezeMotion(page) : null;
  if (!opts.keepOverlays) await hideOverlays(page);
  await applyHideAndFreeze(page, opts.hide, opts.freeze);

  const data = await dumpAndScreenshot(page, { out: opts.out, width: opts.width, dpr: opts.dpr, height: opts.height, waitMs: opts.waitMs,
    selector: opts.selector, stableSamples: stable, freeze: opts.freeze });
  log(`elements=${data.elements.length} size=${opts.width}x${data.height} fonts=${data.fonts.length}`);
  console.log(JSON.stringify({ out: opts.out, width: opts.width, height: data.height, elements: data.elements.length, fonts: data.fonts }));
  await browser.close();
};
