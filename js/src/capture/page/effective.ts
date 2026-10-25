// Effective opacity, overflow clip rect and visibility of an element through its ancestors.
import { SVGNS } from "./geometry";

export interface Effective {
  op: number;                               // product of ancestor opacities
  clip: [number, number, number, number];   // intersection of overflow clip rects [x, y, w, h]
  vis: boolean;                             // not hidden by display/visibility/content-visibility
}

const UNCLIPPED: Effective = { op: 1, clip: [-1e6, -1e6, 2e6, 2e6], vis: true };

/** Memoized resolver (one per dump: styles do not change while dumping). */
export const createEffectiveResolver = () => {
  const cache = new Map<Element, Effective>();
  const resolve = (element: Element | null): Effective => {
    if (!element || element === document.documentElement) return UNCLIPPED;
    const cached = cache.get(element);
    if (cached) return cached;
    const parent = resolve(element.parentElement);
    const style = getComputedStyle(element);
    const opacity = parent.op * parseFloat(style.opacity || "1");
    const visible = parent.vis && style.visibility !== "hidden" && style.display !== "none" && style.contentVisibility !== "hidden";
    let clip = parent.clip;
    const overflow = style.overflow + " " + style.overflowX + " " + style.overflowY;
    if (/hidden|clip|auto|scroll/.test(overflow) && element.namespaceURI !== SVGNS) {
      const border = element.getBoundingClientRect();
      // overflow clips to the padding box (inside the borders)
      const padding = { left: border.left + parseFloat(style.borderLeftWidth || "0"), top: border.top + parseFloat(style.borderTopWidth || "0"),
        right: border.right - parseFloat(style.borderRightWidth || "0"), bottom: border.bottom - parseFloat(style.borderBottomWidth || "0") };
      const left = Math.max(clip[0], padding.left), top = Math.max(clip[1], padding.top);
      const right = Math.min(clip[0] + clip[2], padding.right), bottom = Math.min(clip[1] + clip[3], padding.bottom);
      clip = [left, top, Math.max(0, right - left), Math.max(0, bottom - top)];
    }
    const effective = { op: opacity, clip, vis: visible };
    cache.set(element, effective);
    return effective;
  };
  return resolve;
};
