// Text shapes: creation with styles and ranges, and the two post-build passes that Python
// drives with short pauses in between (no timers in here: background tabs throttle them):
//   verifyRanges - Penpot applies range styles asynchronously and sometimes drops them on later
//                  paragraphs of a fresh text, or lets one bleed over the whole text; read back
//                  the ranges and the gaps between them and re-apply until they stick
//   fitTexts     - phase 1 fits letter-spacing to the browser width, phase 2 re-anchors
//                  centred / right-aligned texts
import type { Range, SpecNode, TextStyle } from "./spec";
import { font, variant } from "./fonts";
import { paint } from "./paints";
import { place } from "./common";
import { byId, isArray, runtime, toNumber, warn } from "./state";

/** Apply a style to a whole Text or to a TextRange. */
export const applyTextStyle = (target: TextLike | Shape, style: TextStyle, baseFont: any): void => {
  const fontObj = style.font ? font(style.font) : baseFont;
  if (style.font || style.weight !== undefined || style.italic !== undefined) {
    const chosen = variant(fontObj, style.weight ?? 400, !!style.italic);
    if (target.type === "text") fontObj.applyToText(target, chosen); else fontObj.applyToRange(target, chosen);
  }
  if (style.size !== undefined) target.fontSize = String(style.size);
  // Penpot line height is relative to the font size
  if (style.lh !== undefined && style.size !== undefined) target.lineHeight = String(+(toNumber(style.lh) / toNumber(style.size)).toFixed(4));
  else if (style.lhr !== undefined) target.lineHeight = String(style.lhr);
  if (style.ls !== undefined) target.letterSpacing = String(toNumber(style.ls));
  if (style.color !== undefined) target.fills = paint(style.color);
  if (style.upper) target.textTransform = "uppercase";
  if (style.lower) target.textTransform = "lowercase";
  if (style.cap) target.textTransform = "capitalize";
  if (style.deco) target.textDecoration = style.deco;
};

export const makeText = (parent: Shape, node: SpecNode): Shape => {
  const spec = node.text!;
  const text = penpot.createText(spec.text === "" ? " " : spec.text);
  if (!text) throw new Error("createText failed for " + JSON.stringify(spec.text).slice(0, 40));
  runtime._made && runtime._made.push(text);
  const family = spec.font || runtime.defaultFont || "Inter";
  const baseFont = font(family);
  applyTextStyle(text, { font: family, weight: spec.weight ?? 400, italic: spec.italic, size: spec.size ?? 16, lh: spec.lh, lhr: spec.lhr,
    ls: spec.ls, color: spec.color ?? "#000000", upper: spec.upper, lower: spec.lower, cap: spec.cap, deco: spec.deco }, baseFont);
  text.align = spec.align || "left";
  if (spec.valign) text.verticalAlign = spec.valign;
  parent.appendChild(text);
  let grow = spec.grow || (spec.align && spec.align !== "left" ? "auto-height" : "auto-width");
  if (spec.fitW && !spec.text.includes("\n")) grow = "auto-width";   // fitted single-line texts are positioned by anchor
  if (grow === "auto-width") text.growType = "auto-width";
  else { text.resize(Math.max(toNumber(node.w, text.width), 1), Math.max(toNumber(node.h, text.height), 1)); text.growType = grow; }
  applyRanges(text, node, baseFont);
  place(text, node);   // anchor: css box top-left; for centred/right text with a fixed width x is the box left
  if (spec.fitW) {
    const align = spec.align || "left";
    const anchor = align === "center" ? node.x! + node.w! / 2 : align === "right" ? node.x! + node.w! : node.x!;
    runtime._fit.push({ id: text.id, w: spec.fitW, anchor, align, multi: spec.text.includes("\n"), text: spec.text });
  }
  return text;
};

/** The base style that undoes a range style (used by the end-of-text workaround). */
const baseStyleFor = (spec: NonNullable<SpecNode["text"]>, style: TextStyle): TextStyle => {
  const family = spec.font || runtime.defaultFont || "Inter";
  const undo: TextStyle = {};
  for (const key of Object.keys(style)) {
    if (key === "color") undo.color = spec.color ?? "#000000";
    else if (key === "weight") { undo.weight = spec.weight ?? 400; undo.font = family; }
    else if (key === "size") { undo.size = spec.size; if (spec.lh) undo.lh = spec.lh; }
    else if (key === "deco") undo.deco = "none";
    else if (key === "italic") { undo.italic = false; undo.weight = spec.weight ?? 400; }
    else if (key === "font") undo.font = family;
  }
  return undo;
};

const applyRanges = (text: Shape, node: SpecNode, baseFont: any): void => {
  const spec = node.text!;
  const length = spec.text.length;
  const ranges: Range[] = spec.ranges || [];
  for (const range of ranges) {
    const [start, end, style] = range;
    if (start >= end || end > length) { warn(`bad range ${start}-${end} on ${node.name || ""}`); continue; }
    if (end === length && start > 0 && !(ranges.some(other => other !== range && other[1] > start))) {
      // Penpot drops styles on ranges ending at the text end of a later paragraph:
      // style the whole text, then restore the base style before the range
      applyTextStyle(text, style, baseFont);
      applyTextStyle(text.getRange(0, start), baseStyleFor(spec, style), baseFont);
      for (const earlier of ranges) {
        if (earlier !== range && earlier[1] <= start) applyTextStyle(text.getRange(earlier[0], earlier[1]), earlier[2], baseFont);
      }
      continue;
    }
    applyTextStyle(text.getRange(start, end), style, baseFont);
  }
  if (ranges.length) runtime._ranges.push({ id: text.id, ranges, font: spec.font || runtime.defaultFont || "Inter",
                                            base: { color: spec.color ?? "#000000", weight: spec.weight ?? 400, size: spec.size } });
};

/** Phase 1: letter-spacing from current widths. Phase 2: re-anchor centred/right texts. */
export const fitTexts = (items: typeof runtime._fit, phase: number): number => {
  let changed = 0;
  for (const item of items) {
    const text = byId(item.id); if (!text) continue;
    if (phase === 1) {
      const lines = item.text.split("\n");
      const longest = lines.reduce((best, line) => line.length > best.length ? line : best, "");
      if (text.growType !== "auto-width") continue;
      const current = +text.letterSpacing || 0;
      const fitted = +(current + (item.w - text.width) / Math.max(1, longest.length - 1)).toFixed(3);
      if (Math.abs(fitted - current) > 0.01 && Math.abs(fitted - current) < 3) { text.letterSpacing = String(fitted); changed++; }
    } else {
      if (item.align === "center" && text.growType === "auto-width") { text.x = item.anchor - text.width / 2; changed++; }
      else if (item.align === "right" && text.growType === "auto-width") { text.x = item.anchor - text.width; changed++; }
    }
  }
  return changed;
};

/** The parts of [0, length) no range covers (ranges may overlap and come in any order). */
export const gapsBetween = (ranges: [number, number, any][], length: number): [number, number][] => {
  const gaps: [number, number][] = [];
  let covered = 0;
  for (const [start, end] of ranges.slice().sort((first, second) => first[0] - second[0])) {
    if (start > covered) gaps.push([covered, start]);
    covered = Math.max(covered, end);
  }
  if (covered < length) gaps.push([covered, length]);
  return gaps;
};

/** The members of `style` (colour, weight, size) a text range does not have; empty = it sticks. */
const unmet = (range: TextLike, style: TextStyle): TextStyle => {
  const normalize = (color: unknown) => String(color || "").toUpperCase();
  const missing: TextStyle = {};
  if (style.color !== undefined && !(style.color && (style.color as any).g)) {
    const wanted = isArray(style.color) ? style.color[0] : style.color;
    const got = isArray(range.fills) && range.fills[0] ? range.fills[0].fillColor : null;
    if (normalize(got) !== normalize(wanted)) missing.color = style.color;
  }
  if (style.weight !== undefined && String(range.fontWeight) !== String(style.weight)) missing.weight = style.weight;
  if (style.size !== undefined && String(range.fontSize) !== String(style.size)) missing.size = style.size;
  return missing;
};

/** Single pass: re-apply range styles that did not stick, and the base style where a range style
 *  bled outside its range. Returns {fixed, bad: first 20}. */
export const verifyRanges = (items: typeof runtime._ranges): { fixed: number; bad: any[] } => {
  let fixed = 0; const bad: any[] = [];
  for (const item of items) {
    const text = byId(item.id); if (!text) continue;
    const checks: [number, number, TextStyle][] = item.ranges.map(([start, end, style]) => [start, end, style]);
    if (item.base) {
      const characters = String(text.characters || "");
      for (let [start, end] of gapsBetween(item.ranges, characters.length)) {
        // a line break is never painted and keeps the style of the paragraph it ends: not a bleed
        while (start < end && characters[start] === "\n") start++;
        while (end > start && characters[end - 1] === "\n") end--;
        if (start < end) checks.push([start, end, item.base as TextStyle]);
      }
    }
    for (const [start, end, style] of checks) {
      try {
        const range = text.getRange(start, end);
        const missing = unmet(range, style);
        if (!Object.keys(missing).length) continue;
        // a weight needs its font to pick the variant; a colour or a size do not
        applyTextStyle(range, style === item.base ? missing : style, font(item.font)); fixed++; bad.push([item.id, start, end]);
      } catch (error: any) { bad.push([item.id, start, end, String(error.message || error)]); }
    }
  }
  return { fixed, bad: bad.slice(0, 20) };
};
