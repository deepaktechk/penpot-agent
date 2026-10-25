// Shape -> spec JSON (for `pb inspect`, snapshots) and a compact layer tree (for `pb tree`).
import { isArray, toNumber } from "./state";

const TYPE_MAP: Record<string, string> = { rectangle: "rect", ellipse: "ellipse", text: "text", path: "path", board: "board", group: "group",
  image: "image", "svg-raw": "svg", bool: "group" };

const round2 = (value: number) => Math.round(value * 100) / 100;

/** Penpot fills -> spec paint (single value, list, "mixed" or null). */
const paintOut = (fills: any): any => {
  if (!isArray(fills)) return fills === "mixed" ? "mixed" : null;
  const paints = fills.map((fill: any) => {
    if (fill.fillImage) return { img: fill.fillImage.name || fill.fillImage.id, op: fill.fillOpacity };
    if (fill.fillColorGradient) {
      const gradient = fill.fillColorGradient;
      const stops = gradient.stops.map((stop: any) => [stop.color, stop.opacity, stop.offset]);
      return { g: [gradient.startX, gradient.startY, gradient.endX, gradient.endY, stops], radial: gradient.type === "radial" ? 1 : undefined,
        op: fill.fillOpacity };
    }
    const color = (fill.fillColor || "").toUpperCase();
    return (fill.fillOpacity ?? 1) >= 0.999 ? color : [color, +(+fill.fillOpacity).toFixed(3)];
  });
  return paints.length === 0 ? null : paints.length === 1 ? paints[0] : paints;
};

export const serialize = (shape: Shape | null, depth = 99, opts: { paths?: boolean } = {}): any => {
  if (!shape) return null;
  const node: any = { t: TYPE_MAP[shape.type] || shape.type, id: shape.id, name: shape.name, x: round2(shape.x), y: round2(shape.y),
    w: round2(shape.width), h: round2(shape.height) };
  if (shape.type !== "group" && shape.type !== "text") { const fill = paintOut(shape.fills); if (fill !== null) node.fill = fill; }
  if (isArray(shape.strokes) && shape.strokes.length) {
    node.stroke = shape.strokes.map((stroke: any) => ({ c: stroke.strokeColor, w: stroke.strokeWidth, op: stroke.strokeOpacity,
      style: stroke.strokeStyle, align: stroke.strokeAlignment }));
  }
  if (isArray(shape.shadows) && shape.shadows.length) {
    node.sh = shape.shadows.map((shadow: any) => [shadow.offsetX, shadow.offsetY, shadow.blur, shadow.spread,
      shadow.color && shadow.color.color, shadow.color && shadow.color.opacity, shadow.style === "inner-shadow" ? 1 : undefined]);
  }
  if (shape.opacity !== undefined && shape.opacity < 0.999) node.op = shape.opacity;
  if (shape.hidden) node.hidden = true;
  if ("borderRadius" in shape && shape.type !== "text") {
    const corners = [shape.borderRadiusTopLeft, shape.borderRadiusTopRight, shape.borderRadiusBottomRight, shape.borderRadiusBottomLeft]
      .map(value => toNumber(value));
    if (corners.some(value => value)) node.r = corners.every(value => value === corners[0]) ? corners[0] : corners;
  }
  if (shape.type === "board") {
    node.clip = !!shape.clipContent;
    if (shape.flex) node.flex = { dir: shape.flex.dir, rowGap: shape.flex.rowGap, columnGap: shape.flex.columnGap };
  }
  if (shape.type === "path" && opts.paths) node.d = String(shape.content);
  if (shape.type === "text") {
    node.text = { text: shape.characters, font: shape.fontFamily, weight: shape.fontWeight, size: +shape.fontSize || shape.fontSize,
      lhr: +shape.lineHeight || shape.lineHeight, ls: +shape.letterSpacing || 0, color: paintOut(shape.fills), align: shape.align,
      grow: shape.growType };
    if (shape.textTransform && shape.textTransform !== "none") node.text.transform = shape.textTransform;
  }
  if (shape.isComponentMainInstance && shape.isComponentMainInstance()) node.mainComponent = true;
  if (depth > 0 && shape.children && shape.children.length) node.children = shape.children.map(child => serialize(child, depth - 1, opts));
  return node;
};

/** Compact layer tree, kept short to fit MCP responses: {id, n: name, t: type, b: [x, y, w, h], txt?, c?: children, nc?: hidden child count} */
export const tree = (root: Shape, depth = 3): any => {
  const entry = (shape: Shape, levels: number): any => {
    const item: any = { id: shape.id, n: shape.name, t: shape.type,
      b: [Math.round(shape.x), Math.round(shape.y), Math.round(shape.width), Math.round(shape.height)] };
    if (shape.type === "text") item.txt = String(shape.characters).slice(0, 40);
    if (levels > 0 && shape.children && shape.children.length) item.c = shape.children.map(child => entry(child, levels - 1));
    else if (shape.children && shape.children.length) item.nc = shape.children.length;
    return item;
  };
  return entry(root, depth);
};
