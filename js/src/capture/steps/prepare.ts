// Preparing the loaded page: clicks, lazy content, fonts, reflow and images.
import type { Page } from "puppeteer-core";
import { log, pageCall, sleep } from "../page-lib";

/** Click selectors in order (e.g. "Accept cookies"); failures are logged, not fatal. */
export const clickAll = async (page: Page, selectors: string[]): Promise<void> => {
  for (const selector of selectors) {
    try { await page.click(selector); await sleep(500); log("clicked", selector); } catch (error) { log("click failed", selector); }
  }
};

/** Scroll through the page to trigger lazy loading and scroll-reveal animations. */
export const triggerLazyContent = async (page: Page): Promise<void> => {
  let pageHeight = await pageCall(page, "scrollHeight");
  for (let y = 0; y < pageHeight + 1080; y += 300) {
    await pageCall(page, "scrollTo", y);
    await sleep(200);
    pageHeight = await pageCall(page, "scrollHeight");    // infinite / growing pages extend the loop
  }
  await pageCall(page, "scrollTo", 0);
  try { await page.waitForNetworkIdle({ idleTime: 800, timeout: 15000 }); } catch (error) { /* busy page: go on */ }
};

/** Wait (max 30 s) for document.fonts and the families requested with --fonts. */
export const waitForRequiredFonts = async (page: Page, fonts: string[]): Promise<void> => {
  for (let i = 0; i < 60; i++) {
    if (await pageCall(page, "requiredFontsLoaded", fonts)) break;
    await sleep(500);
  }
};

export const forceFonts = async (page: Page): Promise<void> => {
  const forced = await pageCall(page, "forceLoadFonts");
  log("fonts forced:", forced.join("; "));
};

/** Wait until the layout height is stable (font swap reflow finished). */
export const waitStableHeight = async (page: Page): Promise<void> => {
  let lastHeight = -1;
  for (let i = 0; i < 20; i++) {
    const height = await pageCall(page, "frameHeight");
    if (height === lastHeight) break;
    lastHeight = height; await sleep(400);
  }
};

/** Lazy images the scroll could not reach (to the side of the viewport) load eagerly. */
export const loadLazyImages = async (page: Page): Promise<void> => {
  const switched = await pageCall(page, "loadLazyImages");
  if (switched) log(`lazy images outside the scrolled area loaded eagerly: ${switched}`);
};

export const waitForImages = async (page: Page): Promise<void> => { await pageCall(page, "waitForImages"); };
