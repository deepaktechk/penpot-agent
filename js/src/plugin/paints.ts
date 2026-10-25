// Spec paints / strokes / shadows -> Penpot fill, stroke and shadow objects.
import type { Paint, ShadowSpec, StrokeSpec } from "./spec";
import { isArray, runtime, toNumber, warn } from "./state";

/** "#RRGGBB" | "#RRGGBBAA" | [hex, opacity] -> {color, opacity} */
export const colorAndOpacity = (color: any): { color: string; opacity: number } => {
  if (isArray(color)) return { color: color[0].slice(0, 7).toUpperCase(), opacity: toNumber(color[1], 1) };
  const hex = String(color);
  if (hex.length === 9) return { color: hex.slice(0, 7).toUpperCase(), opacity: parseInt(hex.slice(7), 16) / 255 };
  return { color: hex.toUpperCase(), opacity: 1 };
};

/** Spec paint -> list of Penpot fills ([] for none). */
export const paint = (spec: Paint): any[] => {
  if (spec === null || spec === undefined || spec === false) return [];
  // a list of paints (but not the [hex, opacity] pair)
  if (isArray(spec) && (isArray(spec[0]) || (spec[0] && typeof spec[0] === "object"))) return (spec as Paint[]).flatMap(paint);
  const fill = spec as any;
  if (fill && fill.g) {
    const [startX, startY, endX, endY, stops] = fill.g;
    return [{ fillOpacity: toNumber(fill.op, 1), fillColorGradient: { type: fill.radial ? "radial" : "linear", startX, startY, endX, endY, width: 1,
      stops: stops.map(([color, opacity, offset]: [string, number, number]) => ({ color: color.toUpperCase(), opacity: toNumber(opacity, 1), offset })) } }];
  }
  if (fill && fill.img) {
    const image = runtime.imgs[fill.img];
    if (!image) { warn("image not uploaded: " + fill.img); return []; }
    return [{ fillOpacity: toNumber(fill.op, 1), fillImage: image }];
  }
  const { color, opacity } = colorAndOpacity(spec);
  return [{ fillColor: color, fillOpacity: opacity }];
};

/** Spec stroke(s) -> Penpot strokes. A stroke is {c, w, op, style, align, cap} or [c, w, op, style, align]. */
export const strokes = (spec: StrokeSpec | StrokeSpec[] | undefined): any[] => {
  if (!spec) return [];
  const list: any[] = isArray(spec) && typeof spec[0] === "object" && !isArray(spec[0]) ? spec : [spec];
  return list.map(stroke => {
    if (isArray(stroke)) stroke = { c: stroke[0], w: stroke[1], op: stroke[2], style: stroke[3], align: stroke[4] };
    const { color, opacity } = colorAndOpacity(stroke.c || "#000000");
    return { strokeColor: color, strokeOpacity: toNumber(stroke.op, opacity), strokeWidth: toNumber(stroke.w, 1),
      strokeAlignment: stroke.align || "inner", strokeStyle: stroke.style || "solid", strokeCapStart: stroke.cap, strokeCapEnd: stroke.cap };
  });
};

/** Spec shadows ([x, y, blur, spread, color, opacity, inset?] or objects) -> Penpot shadows. */
export const shadows = (spec: ShadowSpec[] | undefined): any[] => (spec || []).map((shadow: any) => {
  if (isArray(shadow)) shadow = { x: shadow[0], y: shadow[1], blur: shadow[2], spread: shadow[3], c: shadow[4], op: shadow[5], inner: shadow[6] };
  const { color, opacity } = colorAndOpacity(shadow.c || "#000000");
  return { style: shadow.inner ? "inner-shadow" : "drop-shadow", offsetX: toNumber(shadow.x), offsetY: toNumber(shadow.y),
    blur: toNumber(shadow.blur), spread: toNumber(shadow.spread), color: { color, opacity: toNumber(shadow.op, opacity) }, hidden: false };
});
