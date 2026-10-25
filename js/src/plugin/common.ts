// Properties every shape type shares: name, tag, fills, strokes, shadows, blur, opacity,
// radius, visibility, constraints, plugin data; plus position and size helpers.
import type { SpecNode } from "./spec";
import { paint, shadows, strokes } from "./paints";
import { isArray, toNumber } from "./state";

export const applyCommon = (shape: Shape, node: Partial<SpecNode> & Record<string, any>): void => {
  if (node.name) shape.name = node.name;
  if (node.tag) { try { shape.setPluginData("pb", String(node.tag)); } catch (error) { /* not all shapes accept plugin data */ } }
  if (node.fill !== undefined && shape.type !== "text" && shape.type !== "group") shape.fills = paint(node.fill);
  if (node.stroke) shape.strokes = strokes(node.stroke);
  if (node.sh) shape.shadows = shadows(node.sh);
  if (node.blur) shape.blur = { type: "layer-blur", value: toNumber(node.blur), hidden: false };
  if (node.op !== undefined) shape.opacity = toNumber(node.op, 1);
  if (node.blend) shape.blendMode = node.blend;
  if (node.r !== undefined && "borderRadius" in shape) {
    if (isArray(node.r)) {     // [top-left, top-right, bottom-right, bottom-left]
      shape.borderRadiusTopLeft = toNumber(node.r[0]); shape.borderRadiusTopRight = toNumber(node.r[1]);
      shape.borderRadiusBottomRight = toNumber(node.r[2]); shape.borderRadiusBottomLeft = toNumber(node.r[3]);
    }
    else shape.borderRadius = toNumber(node.r);
  }
  if (node.hidden) shape.hidden = true;
  if (node.locked) shape.blocked = true;
  if (node.flipX) shape.flipX = true;
  if (node.flipY) shape.flipY = true;
  if (node.cons) {
    if (node.cons[0]) shape.constraintsHorizontal = node.cons[0];
    if (node.cons[1]) shape.constraintsVertical = node.cons[1];
  }
  if (node.data) for (const [key, value] of Object.entries(node.data)) shape.setPluginData(key, String(value));
};

/** Move to the node's x/y (when given). */
export const place = (shape: Shape, node: SpecNode): void => {
  if (node.x !== undefined) shape.x = toNumber(node.x);
  if (node.y !== undefined) shape.y = toNumber(node.y);
};

/** Resize to the node's w/h (min 0.01; skipped when already that size). */
export const size = (shape: Shape, node: SpecNode): void => {
  const width = Math.max(toNumber(node.w, shape.width) || 1, 0.01), height = Math.max(toNumber(node.h, shape.height) || 1, 0.01);
  if (Math.abs(shape.width - width) > 0.001 || Math.abs(shape.height - height) > 0.001) shape.resize(width, height);
};
