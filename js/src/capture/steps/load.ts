// Loading the page so that text is painted with the real web fonts.
import type { Page } from "puppeteer-core";
import { log, pageCall, sleep } from "../page-lib";
import type { FontDisplayOverride } from "./font-display";

const FALLBACK_DEVIATION = 0.02;   // median width deviation above which the fallback font was painted
const LOAD_ATTEMPTS = 4;

/** Warm-up visit: populates the HTTP cache with web fonts, so sites using
 *  font-display: optional/swap render the real font (not the fallback) on the real visit. */
export const warmUp = async (page: Page, url: string, timeoutMs: number): Promise<void> => {
  await page.goto(url, { waitUntil: "networkidle2", timeout: timeoutMs });
  await pageCall(page, "warmupFonts");
  await sleep(1000);
  log("warm-up done");
};

/** Load the page; if text was still painted with a fallback font, reload with `font-display: optional`
 *  rewritten to `swap` (see font-display.ts), so the real font replaces the fallback once loaded. */
export const loadWithRealFonts = async (page: Page, url: string, timeoutMs: number, fontDisplay: FontDisplayOverride): Promise<void> => {
  for (let attempt = 0; attempt < LOAD_ATTEMPTS; attempt++) {
    await page.goto(url, { waitUntil: "networkidle2", timeout: timeoutMs });
    await pageCall(page, "fontsReady");
    const deviation = await pageCall(page, "fontPaintDeviation");
    log(`loaded (font paint deviation ${(deviation * 100).toFixed(2)}%)`);
    if (deviation < FALLBACK_DEVIATION) return;
    if (attempt === LOAD_ATTEMPTS - 1) break;
    log("fallback font painted -> reloading with font-display: swap");
    await fontDisplay.enable();
    await sleep(500);
  }
  log(`WARNING: text still painted with a fallback font after ${LOAD_ATTEMPTS} loads`);
};
