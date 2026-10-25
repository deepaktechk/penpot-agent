// Per-element records of the layout dump (see shared/layout-types.ts for the format).
//
// An element is emitted when it paints something (text, box decoration, input, pseudo
// element), is a replaced element (img, svg, video, canvas), is a structural container, or
// has several children. Its parent `p` is the nearest EMITTED ancestor, so the converter
// sees a compact tree.
import type { CapturedElement, FontTuple, PseudoBox } from "../../shared/layout-types";
import { createEffectiveResolver } from "./effective";
import { round2, SVGNS, toRect } from "./geometry";
import { sanitizeSvg } from "./svg";
import { ellipsisText, textLines } from "./text";

const SKIP_TAGS = ["script", "style", "noscript", "template", "meta", "link", "head", "title"];
const CONTAINERS = new Set(["header", "nav", "section", "footer", "main", "article", "aside", "li", "ul", "ol", "a", "button", "form",
  "figure", "label"]);

const fontTuple = (style: CSSStyleDeclaration): FontTuple =>
  [style.fontFamily.split(",")[0].replace(/["']/g, ""), style.fontSize, style.fontWeight, style.lineHeight, style.letterSpacing, style.color,
   style.textAlign, style.textTransform, style.fontStyle, style.textDecorationLine];

const isInSvg = (element: Element): boolean => element.namespaceURI === SVGNS && element.tagName.toLowerCase() !== "svg";

const paddingOf = (style: CSSStyleDeclaration): number[] =>
  [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft].map(parseFloat);

/** <img>: replaced content paints inside the content box (exclude padding + border). */
const imageFields = (record: CapturedElement, image: HTMLImageElement, style: CSSStyleDeclaration, rect: DOMRect): void => {
  const insetLeft = parseFloat(style.paddingLeft) + parseFloat(style.borderLeftWidth);
  const insetTop = parseFloat(style.paddingTop) + parseFloat(style.borderTopWidth);
  const insetRight = parseFloat(style.paddingRight) + parseFloat(style.borderRightWidth);
  const insetBottom = parseFloat(style.paddingBottom) + parseFloat(style.borderBottomWidth);
  if (insetLeft || insetTop || insetRight || insetBottom) {
    record.cbox = [round2(rect.left + insetLeft), round2(rect.top + insetTop),
                   round2(rect.width - insetLeft - insetRight), round2(rect.height - insetTop - insetBottom)];
  }
  record.src = image.currentSrc || image.src; record.nat = [image.naturalWidth, image.naturalHeight]; record.fit = style.objectFit;
  record.opos = style.objectPosition; record.radius = style.borderRadius; record.alt = image.alt;
};

/** Own text: font, browser line boxes, clamping and overflow evidence. */
const textFields = (record: CapturedElement, element: HTMLElement, style: CSSStyleDeclaration, clip: number[]): void => {
  record.text = element.innerText;
  record.font = fontTuple(style);
  record.disp = style.display;
  record.lines = textLines(element);
  const singleLineEllipsis = style.textOverflow === "ellipsis" && style.whiteSpace === "nowrap";
  record.clamp = (style.webkitLineClamp && style.webkitLineClamp !== "none") ? +style.webkitLineClamp : (singleLineEllipsis ? 1 : 0);
  if (style.backgroundClip === "text" || (style as any).webkitBackgroundClip === "text") record.textGradient = style.backgroundImage;
  if (style.textDecorationLine && style.textDecorationLine !== "none") {
    record.deco = { line: style.textDecorationLine, color: style.textDecorationColor, thick: style.textDecorationThickness,
      offset: style.textUnderlineOffset };
  }
  if (style.textOverflow === "ellipsis" && /nowrap|pre/.test(style.whiteSpace)) {
    const visible = ellipsisText(element, style); if (visible) record.visible = visible;
  }
  if (style.overflow !== "visible" || style.overflowY !== "visible") record.ovh = 1;
  if (clip[0] > -1e5) record.tclip = clip.map(round2) as CapturedElement["tclip"];
  if (style.textOverflow && style.textOverflow !== "clip") record.tov = style.textOverflow;
  if (style.whiteSpace !== "normal") record.ws = style.whiteSpace;
  const lineClamp = style.webkitLineClamp || style.getPropertyValue("-webkit-line-clamp") || style.getPropertyValue("line-clamp");
  if (lineClamp && lineClamp !== "none") record.lc = parseInt(lineClamp) || 0;
  // line-clamp may sit on an ancestor (e.g. tailwind line-clamp-N wrapper around CMS html)
  if (!record.lc) {
    let ancestor = element.parentElement;
    for (let level = 0; level < 4 && ancestor; level++, ancestor = ancestor.parentElement) {
      const ancestorClamp = getComputedStyle(ancestor).webkitLineClamp;
      if (ancestorClamp && ancestorClamp !== "none") {
        record.lc = parseInt(ancestorClamp) || 0; record.lcBox = toRect(ancestor.getBoundingClientRect()); break;
      }
    }
  }
  record.pad = paddingOf(style);
};

/** Background, border, shadow, clip-path, filters - when the element paints any of them. */
const boxFields = (record: CapturedElement, style: CSSStyleDeclaration): void => {
  const background = style.backgroundColor, backgroundImage = style.backgroundImage;
  const borderWidths = [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth].map(parseFloat);
  const borderStyles = [style.borderTopStyle, style.borderRightStyle, style.borderBottomStyle, style.borderLeftStyle];
  const hasBorder = borderWidths.some(width => width > 0) && borderStyles.some(borderStyle => borderStyle !== "none");
  const hasBackground = background && background !== "rgba(0, 0, 0, 0)" && background !== "transparent";
  const hasImage = backgroundImage && backgroundImage !== "none" && !record.textGradient;
  if (hasBackground || hasImage || hasBorder || style.boxShadow !== "none" || style.clipPath !== "none" || style.backdropFilter !== "none") {
    record.box = { bg: background, bi: backgroundImage !== "none" && !record.textGradient ? backgroundImage : undefined,
      bsize: style.backgroundSize, bpos: style.backgroundPosition, brep: style.backgroundRepeat,
      bw: borderWidths, bs: borderStyles,
      bc: [style.borderTopColor, style.borderRightColor, style.borderBottomColor, style.borderLeftColor],
      radius: [style.borderTopLeftRadius, style.borderTopRightRadius, style.borderBottomRightRadius, style.borderBottomLeftRadius],
      shadow: style.boxShadow !== "none" ? style.boxShadow : undefined,
      clip: style.clipPath !== "none" ? style.clipPath : undefined, blur: style.backdropFilter !== "none" ? style.backdropFilter : undefined,
      filter: style.filter !== "none" ? style.filter : undefined, mix: style.mixBlendMode !== "normal" ? style.mixBlendMode : undefined };
  }
};

/** ::before / ::after boxes that paint something (located later in the screenshot). */
const pseudoFields = (record: CapturedElement, element: Element): void => {
  for (const pseudoElement of ["::before", "::after"] as const) {
    const style = getComputedStyle(element, pseudoElement);
    if (style.content && style.content !== "none" && style.content !== "normal" && style.display !== "none") {
      const paints = style.backgroundColor !== "rgba(0, 0, 0, 0)" || style.backgroundImage !== "none"
        || parseFloat(style.borderTopWidth) > 0 || style.content.length > 2;
      if (paints) {
        const box: PseudoBox = { pe: pseudoElement, content: style.content.slice(0, 40), w: style.width, h: style.height, top: style.top,
          left: style.left, right: style.right, bottom: style.bottom, pos: style.position, bg: style.backgroundColor,
          bi: style.backgroundImage !== "none" ? style.backgroundImage.slice(0, 200) : undefined, radius: style.borderRadius,
          bw: style.borderTopWidth, bc: style.borderTopColor, op: style.opacity, color: style.color, font: style.fontSize, tf: style.transform };
        (record.pseudo = record.pseudo || []).push(box);
      }
    }
  }
};

/** Walk the subtree of `rootSelector` (default body) and return the emitted element records. */
export const collectElements = (rootSelector: string | null): CapturedElement[] => {
  const root = rootSelector ? document.querySelector(rootSelector)! : document.body;
  const elements = [...root.querySelectorAll("*")];
  const indexOf = new Map<Element, number>(); elements.forEach((element, i) => indexOf.set(element, i));
  const effectiveOf = createEffectiveResolver();
  const records: CapturedElement[] = [];
  const emitted = new Set<Element>();
  const nearestEmittedAncestor = (element: Element): number => {
    for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
      if (emitted.has(ancestor)) return indexOf.get(ancestor)!;
    }
    return -1;
  };
  const emit = (record: CapturedElement, element: Element) => { records.push(record); emitted.add(element); };

  for (const element of elements) {
    if (isInSvg(element)) continue;
    const tag = element.tagName.toLowerCase();
    if (SKIP_TAGS.includes(tag)) continue;
    const effective = effectiveOf(element);
    if (!effective.vis || effective.op < 0.01) continue;
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    const clip = effective.clip;   // [x, y, w, h]
    const clipRight = clip[0] + clip[2], clipBottom = clip[1] + clip[3];
    if (rect.right <= clip[0] || rect.left >= clipRight || rect.bottom <= clip[1] || rect.top >= clipBottom) continue; // fully clipped
    const style = getComputedStyle(element);
    const html = element as HTMLElement;
    const record: CapturedElement = { i: indexOf.get(element)!, p: nearestEmittedAncestor(element), tag, r: toRect(rect),
      op: Math.round(effective.op * 1000) / 1000 };
    if (html.offsetWidth && (Math.abs(html.offsetWidth - rect.width) > 1 || Math.abs(html.offsetHeight - rect.height) > 1)) {
      record.os = [html.offsetWidth, html.offsetHeight];    // untransformed size of a rotated/scaled element
    }
    const partlyClipped = rect.left < clip[0] - 0.5 || rect.top < clip[1] - 0.5 || rect.right > clipRight + 0.5 || rect.bottom > clipBottom + 0.5;
    if (clip[0] > -1e5 && partlyClipped) record.clip = clip.map(round2) as CapturedElement["clip"];
    if (element.id) record.htmlId = element.id;
    const classes = typeof element.className === "string" ? element.className : ""; if (classes) record.cls = classes.slice(0, 120);
    if (style.position !== "static") { record.pos = style.position; if (style.zIndex !== "auto") record.z = +style.zIndex; }
    if (style.transform && style.transform !== "none") record.tf = style.transform;

    if (tag === "svg") {
      const sanitized = sanitizeSvg(element as SVGSVGElement);
      record.svg = sanitized.markup; if (sanitized.texts.length) record.svgTexts = sanitized.texts; record.color = style.color;
      emit(record, element); continue;
    }
    if (tag === "img") { imageFields(record, element as HTMLImageElement, style, rect); emit(record, element); continue; }
    // video / canvas: recorded but never become emitted ancestors
    if (tag === "video") {
      const video = element as HTMLVideoElement; record.src = video.currentSrc; record.poster = video.poster; records.push(record); continue;
    }
    if (tag === "canvas") {
      try { record.dataUrl = (element as HTMLCanvasElement).toDataURL("image/png"); } catch (error) { /* tainted canvas */ }
      records.push(record); continue;
    }
    if (tag === "input" || tag === "textarea" || tag === "select") {
      const input = element as HTMLInputElement;
      record.input = { type: input.type, value: input.value, placeholder: input.placeholder };
      record.font = fontTuple(style);
      record.phColor = getComputedStyle(element, "::placeholder").color;
      record.pad = paddingOf(style);
    }
    const ownText = [...element.childNodes].some(child => child.nodeType === 3 && child.textContent!.trim());
    if (ownText) textFields(record, html, style, effective.clip);
    boxFields(record, style);
    pseudoFields(record, element);
    if (record.text || record.box || record.input || record.pseudo || CONTAINERS.has(tag) || element.children.length > 1) emit(record, element);
  }
  return records;
};
