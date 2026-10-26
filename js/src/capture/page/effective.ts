// Effective opacity, overflow clip rect and visibility of an element through its ancestors.
import { SVGNS } from "./geometry";

export interface Effective {
  op: number;                               // product of ancestor opacities
  clip: [number, number, number, number];   // intersection of overflow clip rects [x, y, w, h]
  vis: boolean;                             // painted: rendered and not hidden by visibility
  rendered: boolean;                        // no ancestor (or itself) with display:none / content-visibility:hidden / empty clip-path
}

const UNCLIPPED: Effective = { op: 1, clip: [-1e6, -1e6, 2e6, 2e6], vis: true, rendered: true };

/** True when a computed clip-path shape has no area: nothing of the element or its subtree is painted
 *  (pumble.com hides its "zoom" popups with circle(0) until they are activated). */
export const clipsEverything = (clipPath: string, box: { width: number; height: number }): boolean => {
  const shape = /^(circle|ellipse|inset)\((.*)\)$/.exec(clipPath.trim());
  if (!shape) return false;
  const [, kind, args] = shape;
  // sizes come before "at <position>" (circle/ellipse) or "round <radius>" (inset); keywords parse as NaN
  const sizes = args.split(/\s+at\s+/)[0].split(/\s+round\s+/)[0].trim().split(/\s+/).filter(Boolean);
  const length = (value: string, reference: number) => (value.endsWith("%") ? (parseFloat(value) / 100) * reference : parseFloat(value));
  if (kind === "circle") return sizes.length > 0 && length(sizes[0], Math.hypot(box.width, box.height) / Math.SQRT2) <= 0;
  if (kind === "ellipse") return sizes.length === 2 && (length(sizes[0], box.width) <= 0 || length(sizes[1], box.height) <= 0);
  // inset(top right bottom left), margin-style shorthand
  const [top, right = top, bottom = top, left = right] = sizes;
  if (top === undefined) return false;
  return length(top, box.height) + length(bottom, box.height) >= box.height || length(left, box.width) + length(right, box.width) >= box.width;
};

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
    // display:none and content-visibility:hidden hide every descendant. visibility is inherited but a
    // child can turn it back on (visible inside hidden is painted), so the element's own computed value
    // decides; "collapse" hides like "hidden" outside tables (clockify.me's closed product dropdown)
    // a zero-area clip-path clips the whole subtree away, like display:none
    const rendered = parent.rendered && style.display !== "none" && style.contentVisibility !== "hidden"
      && !(style.clipPath !== "none" && clipsEverything(style.clipPath, element.getBoundingClientRect()));
    const visible = rendered && style.visibility !== "hidden" && style.visibility !== "collapse";
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
    const effective = { op: opacity, clip, vis: visible, rendered };
    cache.set(element, effective);
    return effective;
  };
  return resolve;
};
