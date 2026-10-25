// Rounding helpers for everything written to layout.json.
import type { Rect } from "../../shared/layout-types";

export const SVGNS = "http://www.w3.org/2000/svg";

export const round2 = (value: number): number => Math.round(value * 100) / 100;

/** DOMRect -> [x, y, w, h] rounded to 0.01 px. */
export const toRect = (rect: DOMRect | { left: number; top: number; width: number; height: number }): Rect =>
  [round2(rect.left), round2(rect.top), round2(rect.width), round2(rect.height)];

/** Generic / system families never count as "the web font". */
export const isGenericFamily = (family: string): boolean =>
  !family || family.startsWith("-") || /^(system-ui|sans-serif|serif|monospace)$/.test(family);
