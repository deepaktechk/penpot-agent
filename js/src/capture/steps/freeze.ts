// Freezing the page: CSS animations first, then wait until JS-driven positions/transforms
// stop changing (carousels between slides), then stop every JS timer. Also hides overlays.
import type { Page } from "puppeteer-core";
import { log, pageCall, sleep } from "../page-lib";

const STABLE_NEEDED = 3;   // consecutive identical layout signatures
const MAX_SAMPLES = 40;    // 40 x 250 ms = 10 s max

/** Returns the number of consecutive stable samples reached (reported to the capture gate). */
export const freezeMotion = async (page: Page): Promise<number> => {
  await pageCall(page, "pauseAnimations");
  let previous = await pageCall(page, "layoutSignature"), stable = 0;
  for (let i = 0; i < MAX_SAMPLES && stable < STABLE_NEEDED; i++) {
    await sleep(250);
    const current = await pageCall(page, "layoutSignature");
    stable = current === previous ? stable + 1 : 0; previous = current;
  }
  await pageCall(page, "stopTimers");
  log("settled (stable samples: " + stable + "), timers stopped");
  return stable;
};

export const hideOverlays = async (page: Page): Promise<void> => {
  const hidden = await pageCall(page, "hideOverlays");
  if (hidden.length) log("auto-hidden overlays: " + hidden.join(" | "));
};

export const applyHideAndFreeze = async (page: Page, hide: string[], freeze: boolean): Promise<void> => {
  await pageCall(page, "applyHideAndFreeze", hide, freeze);
};
