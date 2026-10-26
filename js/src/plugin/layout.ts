// Auto-layout from the spec: `layout` on a board (flex or grid) and `child` on its children.
//
//   "layout": {"type": "flex", "dir": "column", "gap": 16, "padding": [24, 32], "align": "center",
//              "justify": "space-between", "wrap": true, "sizing": ["fix", "auto"]}
//   "layout": {"type": "grid", "columns": ["1fr", "1fr", "320px"], "rows": ["auto"], "gap": [24, 16]}
//   child:    "child": {"sizing": ["fill", "auto"], "alignSelf": "center", "margin": 8, "cell": [1, 2]}
//
// Names follow CSS where possible and are mapped to Penpot's FlexLayout / GridLayout properties.
import type { ChildLayoutSpec, LayoutSpec } from "./spec";
import { byId, isArray, toNumber } from "./state";
import type { PinItem } from "./state";

/** CSS-style shorthand: 8 | [vertical, horizontal] | [top, right, bottom, left] -> [top, right, bottom, left] */
export const sides = (value: number | number[] | undefined): [number, number, number, number] => {
  if (value === undefined) return [0, 0, 0, 0];
  if (!isArray(value)) return [toNumber(value), toNumber(value), toNumber(value), toNumber(value)];
  if (value.length === 2) return [toNumber(value[0]), toNumber(value[1]), toNumber(value[0]), toNumber(value[1])];
  return [toNumber(value[0]), toNumber(value[1]), toNumber(value[2]), toNumber(value[3])];
};

/** Grid track like CSS: "1fr" -> flex 1, "200px" / 200 -> fixed 200, "50%" -> percent 50, "auto" -> auto. */
export const track = (value: string | number): { type: string; value?: number } => {
  if (typeof value === "number") return { type: "fixed", value };
  const text = String(value).trim();
  if (text === "auto") return { type: "auto" };
  if (text.endsWith("fr")) return { type: "flex", value: toNumber(text.slice(0, -2), 1) };
  if (text.endsWith("%")) return { type: "percent", value: toNumber(text.slice(0, -1)) };
  return { type: "fixed", value: toNumber(text.replace("px", "")) };
};

/** Configure flex or grid layout on a board (before its children are added). Returns the layout. */
export const applyLayout = (board: any, spec: LayoutSpec): any => {
  const layout = spec.type === "grid" ? board.addGridLayout() : board.addFlexLayout();
  if (spec.dir) layout.dir = spec.dir;
  if (spec.type !== "grid" && spec.wrap !== undefined) layout.wrap = spec.wrap ? "wrap" : "nowrap";
  if (spec.gap !== undefined) {
    const [rowGap, columnGap] = isArray(spec.gap) ? spec.gap : [spec.gap, spec.gap];
    layout.rowGap = toNumber(rowGap); layout.columnGap = toNumber(columnGap);
  }
  if (spec.padding !== undefined) {
    const [top, right, bottom, left] = sides(spec.padding);
    layout.topPadding = top; layout.rightPadding = right; layout.bottomPadding = bottom; layout.leftPadding = left;
  }
  if (spec.align) layout.alignItems = spec.align;
  if (spec.justify) layout.justifyContent = spec.justify;
  if (spec.alignContent) layout.alignContent = spec.alignContent;
  if (spec.sizing) { layout.horizontalSizing = spec.sizing[0]; layout.verticalSizing = spec.sizing[1]; }
  if (spec.type === "grid") {
    for (const column of spec.columns || []) { const parsed = track(column); layout.addColumn(parsed.type, parsed.value); }
    for (const row of spec.rows || []) { const parsed = track(row); layout.addRow(parsed.type, parsed.value); }
  }
  return layout;
};

/** Per-child layout properties (sizing, self alignment, margins, absolute position, min/max). */
export const applyChildLayout = (shape: any, spec: ChildLayoutSpec): void => {
  const child = shape.layoutChild;
  if (!child) return;      // the parent has no layout
  if (spec.sizing) { child.horizontalSizing = spec.sizing[0]; child.verticalSizing = spec.sizing[1]; }
  if (spec.alignSelf) child.alignSelf = spec.alignSelf;
  if (spec.margin !== undefined) {
    const [top, right, bottom, left] = sides(spec.margin);
    child.topMargin = top; child.rightMargin = right; child.bottomMargin = bottom; child.leftMargin = left;
  }
  if (spec.absolute !== undefined) child.absolute = spec.absolute;
  if (spec.zIndex !== undefined) child.zIndex = spec.zIndex;
  if (spec.minW !== undefined) child.minWidth = spec.minW;
  if (spec.maxW !== undefined) child.maxWidth = spec.maxW;
  if (spec.minH !== undefined) child.minHeight = spec.minH;
  if (spec.maxH !== undefined) child.maxHeight = spec.maxH;
};

/** Real size and position of the flow children of settled flex boards: [[w, h, x, y], ...] per item. */
export const layoutState = (items: PinItem[]): ([number, number, number, number] | null)[][] =>
  items.map(item => item.flow.map(([id]) => {
    const shape = byId(id);
    return shape ? [shape.width, shape.height, shape.x, shape.y] : null;
  }));

/** Corrected flex props from Python: [{board, layout: {justify?, gap?}, children: [[id, margin, alignSelf]]}].
 *  Only sets properties: Penpot applies them asynchronously, so nothing is read back here. */
export const setFlexProps = (corrections: { board: string; layout: any; children: [string, number[], string][] }[]): number => {
  let changed = 0;
  for (const correction of corrections) {
    const board = byId(correction.board);
    const layout = board && board.flex;
    if (!layout) continue;
    if (correction.layout.justify) layout.justifyContent = correction.layout.justify;
    if (correction.layout.gap !== undefined) {
      if (String(layout.dir).startsWith("column")) layout.rowGap = correction.layout.gap; else layout.columnGap = correction.layout.gap;
    }
    for (const [id, margin, alignSelf] of correction.children) {
      const shape = byId(id);
      if (!shape || !shape.layoutChild) continue;
      applyChildLayout(shape, { margin, alignSelf: alignSelf as ChildLayoutSpec["alignSelf"] });
      changed++;
    }
  }
  return changed;
};

/** Absolute children of flex boards back at their spec x/y, once every flow is final. */
export const placeAbsolute = (entries: [string, number, number][]): number => {
  let placed = 0;
  for (const [id, x, y] of entries) {
    const shape = byId(id);
    if (!shape) continue;
    shape.x = x; shape.y = y; placed++;
  }
  return placed;
};
