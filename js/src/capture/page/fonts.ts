// Web font loading. Many sites use font-display: optional/swap, which can leave the page on
// the fallback font for its whole life on a cold load; these helpers detect and prevent that.
import { isGenericFamily } from "./geometry";

/** First family of the computed font-family list, trimmed and unquoted. */
const declaredFamily = (style: CSSStyleDeclaration): string => style.fontFamily.split(",")[0].trim().replace(/["']/g, "");

/** Ask the browser to load every (family, weight) in use, so the fonts end up in the HTTP cache. */
export const warmupFonts = async (): Promise<void> => {
  const combos = new Set<string>();     // "family|weight"
  document.querySelectorAll("body *").forEach(element => {
    const style = getComputedStyle(element); combos.add(declaredFamily(style) + "|" + style.fontWeight);
  });
  await Promise.all([...combos].slice(0, 60).map(combo => {
    const [family, weight] = combo.split("|");
    return document.fonts.load(`${weight} 16px "${family}"`, "AaBbCc0123").catch(() => null);
  }));
  await document.fonts.ready;
};

export const fontsReady = async (): Promise<void> => { await document.fonts.ready; };

/** Median relative deviation between painted single-line text widths and a canvas measurement
 *  in the declared font (0 if fewer than 5 samples). Above ~2% the fallback font was painted. */
export const fontPaintDeviation = (): number => {
  const canvas = document.createElement("canvas").getContext("2d")!; const deviations: number[] = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let textNode: Node | null, visited = 0;
  while ((textNode = walker.nextNode()) && deviations.length < 40 && visited++ < 4000) {
    const text = (textNode.textContent || "").trim(); const element = textNode.parentElement;
    if (!element || text.length < 8 || text.length > 60 || element.children.length) continue;
    const style = getComputedStyle(element); const family = declaredFamily(style);
    const wraps = style.whiteSpace === "normal" && element.getClientRects().length > 1;
    if (isGenericFamily(family) || style.letterSpacing !== "normal" || style.textTransform !== "none" || wraps) continue;
    const range = document.createRange(); range.selectNodeContents(textNode); const rects = range.getClientRects();
    if (rects.length !== 1) continue;
    canvas.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} "${family}"`;
    const expected = canvas.measureText(textNode.textContent || "").width; if (!expected) continue;
    deviations.push(Math.abs(rects[0].width - expected) / expected);
  }
  deviations.sort((first, second) => first - second);
  return deviations.length >= 5 ? deviations[deviations.length >> 1] : 0;
};

/** True when every requested family is loaded and no font is still loading. */
export const requiredFontsLoaded = async (families: string[]): Promise<boolean> => {
  await document.fonts.ready;
  const faces = [...document.fonts];
  const loaded = new Set(faces.filter(face => face.status === "loaded").map(face => face.family.replace(/["']/g, "")));
  return families.every(family => loaded.has(family)) && faces.every(face => face.status !== "loading");
};

/** Force-load every (family, weight, style) actually used, with the page's real characters. */
export const forceLoadFonts = async (): Promise<string[]> => {
  const samples = new Map<string, string>();      // "style|weight|family" -> characters used with it
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let textNode: Node | null, budget = 20000;
  while ((textNode = walker.nextNode()) && budget-- > 0) {
    const text = (textNode.textContent || "").trim(); if (!text || !textNode.parentElement) continue;
    const style = getComputedStyle(textNode.parentElement);
    for (const family of style.fontFamily.split(",").map(name => name.trim().replace(/["']/g, "")).slice(0, 1)) {
      const combo = `${style.fontStyle}|${style.fontWeight}|${family}`;
      const previous = samples.get(combo) || ""; if (previous.length < 400) samples.set(combo, previous + text.slice(0, 200));
    }
  }
  const results: string[] = [];
  for (const [combo, sample] of samples) {
    const [style, weight, family] = combo.split("|");
    try {
      const faces = await document.fonts.load(`${style} ${weight} 16px "${family}"`, sample);
      results.push(`${family} ${weight} ${style}: ${faces.length}`);
    }
    catch (error) { results.push(`${family} ${weight}: ERR`); }
  }
  await document.fonts.ready;
  return results;
};
