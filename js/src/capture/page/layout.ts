// The layout dump: page metadata + element records + quality evidence for the capture gate.
import type { CaptureQuality, CapturedElement, LayoutDump } from "../../shared/layout-types";
import { collectElements } from "./elements";
import { isGenericFamily } from "./geometry";

/** Did text really render with its declared font? Compare each first line's painted width
 *  (DOM Range) with a canvas measurement in the declared font: a fallback font gives a
 *  systematic deviation. Also lists broken and still-lazy images. */
const qualityEvidence = (records: CapturedElement[]): CaptureQuality => {
  const quality: CaptureQuality = { fontRender: {}, brokenImages: [], lazyPending: 0 };
  const canvas = document.createElement("canvas").getContext("2d")!;
  const deviationsByFamily: Record<string, number[]> = {};
  for (const record of records) {
    if (!record.lines || !record.font || record.lines.length < 1) continue;
    // font tuple: [family, size, weight, lineHeight, letterSpacing, color, align, transform, style, decoration]
    const family = record.font[0]; if (isGenericFamily(family)) continue;
    const firstLine = record.lines[0]; if (firstLine.t.length < 6 || record.tf) continue;
    canvas.font = `${record.font[8] || "normal"} ${record.font[2]} ${record.font[1]} "${family}"`;
    if (record.font[4] && record.font[4] !== "normal") continue;     // letter-spacing distorts the comparison
    let text = firstLine.t; if (record.font[7] === "uppercase") text = text.toUpperCase();
    const expected = canvas.measureText(text).width; if (!expected) continue;
    (deviationsByFamily[family] = deviationsByFamily[family] || []).push(Math.abs(firstLine.r[2] - expected) / expected);
  }
  for (const [family, deviations] of Object.entries(deviationsByFamily)) {
    deviations.sort((first, second) => first - second);
    quality.fontRender[family] = { samples: deviations.length, medianDev: Math.round(deviations[deviations.length >> 1] * 10000) / 10000,
      loaded: document.fonts.check(`16px "${family}"`) };
  }
  for (const image of document.images) {
    const rect = image.getBoundingClientRect();
    if (rect.width > 4 && rect.height > 4 && (!image.complete || image.naturalWidth === 0)) {
      quality.brokenImages.push((image.currentSrc || image.src).slice(0, 200));
    }
  }
  quality.lazyPending = [...document.images].filter(image => image.loading === "lazy" && !image.complete).length;
  return quality;
};

export const dumpLayout = (rootSelector: string | null): LayoutDump => {
  const elements = collectElements(rootSelector);
  const quality = qualityEvidence(elements);
  const documentHeight = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
  const fontsUsed = [...document.fonts].filter(face => face.status === "loaded")
    .map(face => `${face.family.replace(/["']/g, "")} ${face.weight} ${face.style}`);
  return { url: location.href, title: document.title, width: window.innerWidth, height: documentHeight,
    bodyBg: getComputedStyle(document.body).backgroundColor, fonts: [...new Set(fontsUsed)], quality, elements };
};
