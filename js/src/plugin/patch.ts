// Patch operations (`pb patch`, autofix). Every op selects shapes with a Query and applies:
//   set: {x, y, w, h, name, fill, stroke, sh, op, r, text, textStyle{..., range}, align, grow, hidden, visible}
//   move: [dx, dy] (relative!)  scale: factor  remove: true  z: "front" | "back" | index
//   reparent: id  rename: "..."
import { applyCommon } from "./common";
import { font } from "./fonts";
import { paint } from "./paints";
import { find, type Query } from "./query";
import { byId, toNumber } from "./state";
import { applyTextStyle } from "./text";

export interface PatchOp {
  sel?: Query;
  set?: Record<string, any>;
  move?: [number, number];
  scale?: number;
  remove?: boolean;
  z?: "front" | "back" | number;
  reparent?: string;
  rename?: string;
}

const applyOp = (shape: Shape, operation: PatchOp): void => {
  const changes = operation.set || {};
  if (operation.move) { shape.x += toNumber(operation.move[0]); shape.y += toNumber(operation.move[1]); }
  if (operation.scale) { shape.resize(shape.width * operation.scale, shape.height * operation.scale); }
  if (changes.w !== undefined || changes.h !== undefined) {
    if (shape.type === "text") {
      shape.resize(toNumber(changes.w, shape.width), toNumber(changes.h, shape.height)); shape.growType = changes.grow || "auto-height";
    }
    else shape.resize(toNumber(changes.w, shape.width), toNumber(changes.h, shape.height));
  }
  if (changes.x !== undefined) shape.x = toNumber(changes.x);
  if (changes.y !== undefined) shape.y = toNumber(changes.y);
  if (changes.text !== undefined && shape.type === "text") shape.characters = changes.text;
  if (changes.textStyle && shape.type === "text") {
    const baseFont = font(changes.textStyle.font || shape.fontFamily);
    const target = changes.textStyle.range ? shape.getRange(changes.textStyle.range[0], changes.textStyle.range[1]) : shape;
    applyTextStyle(target, changes.textStyle, baseFont);
  }
  if (changes.align && shape.type === "text") shape.align = changes.align;
  if (changes.grow && shape.type === "text") shape.growType = changes.grow;
  applyCommon(shape, { ...changes, x: undefined, y: undefined, fill: shape.type === "text" ? undefined : changes.fill });
  if (shape.type === "text" && changes.fill !== undefined) shape.fills = paint(changes.fill);
  if (changes.visible !== undefined) shape.hidden = !changes.visible;
  if (operation.rename) shape.name = operation.rename;
  if (operation.z === "front") shape.bringToFront(); else if (operation.z === "back") shape.sendToBack(); else if (typeof operation.z === "number") shape.setParentIndex(operation.z);
  if (operation.reparent) {   // keep the absolute position across the move to the new parent
    const newParent = byId(operation.reparent)!; const keepX = shape.x, keepY = shape.y;
    newParent.appendChild(shape); shape.x = keepX; shape.y = keepY;
  }
};

/** Apply ops in order; returns one report entry per matched shape (or {sel, error: "no match"}). */
export const patch = (ops: PatchOp[]): any[] => {
  const report: any[] = [];
  for (const operation of ops) {
    const shapes = find(operation.sel || {});
    if (!shapes.length) { report.push({ sel: operation.sel, error: "no match" }); continue; }
    for (const shape of shapes) {
      try {
        if (operation.remove) { shape.remove(); report.push({ id: shape.id, removed: true }); continue; }
        applyOp(shape, operation);
        report.push({ id: shape.id, name: shape.name, ok: true });
      } catch (error: any) { report.push({ id: shape.id, error: String(error.message || error) }); }
    }
  }
  return report;
};
