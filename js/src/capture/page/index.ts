// Browser-side capture library (bundled to src/pbridge/bundles/capture-page.js).
//
// The node side evaluates this bundle in the page (CDP evaluation is not subject to the
// site's CSP) and then calls `window.__pbCapture.<fn>()`. Navigation discards it, so the node
// side re-injects it after every page load (see ../page-lib.ts).
import { dumpLayout } from "./layout";
import { fontPaintDeviation, fontsReady, forceLoadFonts, requiredFontsLoaded, warmupFonts } from "./fonts";
import { hideOverlays } from "./overlays";
import { applyHideAndFreeze, frameHeight, fullHeight, layoutSignature, pauseAnimations, scrollHeight, scrollTo, stopTimers, waitForImages } from "./settle";

export const pageApi = {
  warmupFonts, fontsReady, fontPaintDeviation, requiredFontsLoaded, forceLoadFonts,
  scrollHeight, scrollTo, frameHeight, fullHeight, waitForImages,
  pauseAnimations, layoutSignature, stopTimers, hideOverlays, applyHideAndFreeze,
  dumpLayout,
};

export type PageApi = typeof pageApi;

(window as unknown as { __pbCapture: PageApi }).__pbCapture = pageApi;
