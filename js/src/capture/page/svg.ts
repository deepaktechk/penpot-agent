// Inline <svg> -> self-contained markup that renders exactly as on screen in any importer.
//
// * computed paint styles become attributes (classes/stylesheets are gone after export)
// * <text> elements are removed and reported separately (rebuilt as real Penpot texts)
// * every shape's full screen transform (viewBox mapping incl. preserveAspectRatio=none,
//   nested group transforms, CSS transforms, frozen animations) is baked into a matrix;
//   the viewBox becomes screen pixels
import type { SvgText } from "../../shared/layout-types";
import { SVGNS, toRect } from "./geometry";

const PAINT_PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "opacity", "fill-opacity",
  "stroke-opacity", "fill-rule"];
const SHAPES = new Set(["path", "circle", "ellipse", "rect", "line", "polyline", "polygon", "use", "image"]);

/** Inline computed paint properties; collect and remove <text> elements.
 *  `originals[i]` (live DOM) and `copies[i]` (the clone) are the same element. */
const inlineStyles = (originals: Element[], copies: Element[], texts: SvgText[]): void => {
  originals.forEach((original, i) => {
    const copy = copies[i]; if (!copy || original.namespaceURI !== SVGNS) return;
    const style = getComputedStyle(original);
    for (const property of PAINT_PROPS) {
      const value = style.getPropertyValue(property); if (value && value !== "normal") copy.setAttribute(property, value);
    }
    copy.removeAttribute("class"); copy.removeAttribute("style");
    if (original.tagName.toLowerCase() === "text") {
      const bounds = original.getBoundingClientRect();
      const screenMatrix = (original as SVGGraphicsElement).getScreenCTM();
      const scale = screenMatrix ? Math.hypot(screenMatrix.a, screenMatrix.b) : 1;
      const tspans = [...original.querySelectorAll("tspan")];
      texts.push({ text: original.textContent, r: toRect(bounds), scale: Math.round(scale * 10000) / 10000,
        font: [style.fontFamily.split(",")[0].replace(/["']/g, ""), style.fontSize, style.fontWeight, style.letterSpacing, style.fill,
          style.opacity, style.textAnchor],
        lines: tspans.length ? tspans.map(tspan => ({ t: tspan.textContent, r: toRect(tspan.getBoundingClientRect()) }))
                             : [{ t: original.textContent, r: toRect(bounds) }] });
      copy.remove();
    }
  });
};

/** Replace each shape's transform by its screen CTM relative to the svg's top-left corner. */
const bakeTransforms = (svg: SVGSVGElement, originals: Element[], copies: Element[], clone: Element): void => {
  const svgBounds = svg.getBoundingClientRect();
  originals.forEach((original, i) => {
    const copy = copies[i]; if (!copy || original.namespaceURI !== SVGNS || original === svg) return;
    if (copy.hasAttribute("transform")) copy.removeAttribute("transform");
    if (!SHAPES.has(original.tagName.toLowerCase()) || !copy.isConnected && !clone.contains(copy)) return;
    const graphic = original as SVGGraphicsElement;
    let matrix: DOMMatrix | null; try { matrix = graphic.getScreenCTM(); } catch (error) { matrix = null; }
    if (!matrix) return;
    // matrix(a b c d e f): getScreenCTM() returns an SVGMatrix, which only has a..f (no m11..m22 aliases).
    // m11 m12 / m21 m22 = the linear part; the translation is made relative to the svg corner below
    const { a: m11, b: m12, c: m21, d: m22 } = matrix;
    let translateX = matrix.e - svgBounds.left, translateY = matrix.f - svgBounds.top;
    // animated geometry (CSS offset-path / motion) may not be in the CTM: correct with the painted bbox
    try {
      const box = graphic.getBBox(); const painted = graphic.getBoundingClientRect();
      const predictedX = m11 * (box.x + box.width / 2) + m21 * (box.y + box.height / 2) + translateX + svgBounds.left;
      const predictedY = m12 * (box.x + box.width / 2) + m22 * (box.y + box.height / 2) + translateY + svgBounds.top;
      const paintedX = painted.left + painted.width / 2, paintedY = painted.top + painted.height / 2;
      if (painted.width > 0 && (Math.abs(predictedX - paintedX) > 1 || Math.abs(predictedY - paintedY) > 1)) {
        translateX += paintedX - predictedX; translateY += paintedY - predictedY;
      }
    } catch (error) { /* getBBox throws for non-rendered elements */ }
    copy.setAttribute("transform", `matrix(${m11} ${m12} ${m21} ${m22} ${translateX} ${translateY})`);
    const style = getComputedStyle(original);
    if (style.vectorEffect === "non-scaling-stroke") {
      // the baked matrix would scale the stroke: divide it back out
      const strokeScale = Math.sqrt(Math.abs(m11 * m22 - m12 * m21)) || 1;
      const strokeWidth = parseFloat(style.strokeWidth) || 1; copy.setAttribute("stroke-width", String(strokeWidth / strokeScale));
      const dashes = style.strokeDasharray;
      if (dashes && dashes !== "none") copy.setAttribute("stroke-dasharray", dashes.split(",").map(dash => parseFloat(dash) / strokeScale).join(" "));
    }
  });
};

export const sanitizeSvg = (svg: SVGSVGElement): { markup: string; texts: SvgText[] } => {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const originals = [svg, ...svg.querySelectorAll("*")], copies = [clone, ...clone.querySelectorAll("*")];
  const texts: SvgText[] = [];
  inlineStyles(originals, copies, texts);
  clone.querySelectorAll("foreignObject").forEach(foreign => foreign.remove());
  clone.setAttribute("xmlns", SVGNS);
  bakeTransforms(svg, originals, copies, clone);
  // groups: their transforms are folded into the leaves
  clone.querySelectorAll("g,svg").forEach(group => { if (group !== clone) group.removeAttribute("transform"); });
  const bounds = svg.getBoundingClientRect();
  clone.setAttribute("viewBox", `0 0 ${bounds.width} ${bounds.height}`);
  clone.removeAttribute("preserveAspectRatio");
  clone.setAttribute("width", String(bounds.width)); clone.setAttribute("height", String(bounds.height));
  return { markup: clone.outerHTML, texts };
};
