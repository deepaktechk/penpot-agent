// Spec node tree -> Penpot shapes.
//
// `build` creates one node (recursively); `buildMany` builds a batch under a parent and
// returns the key -> id map Python stores in .pbridge/idmap.json. A failing node rolls back
// every shape created by its build, so failures leave no debris.
import type { SpecNode } from "./spec";
import { applyCommon, place, size } from "./common";
import { applyChildLayout, applyLayout } from "./layout";
import { paint, strokes } from "./paints";
import { byId, runtime, toNumber, warn } from "./state";
import { makeText } from "./text";

/** object-fit cover/contain emulation: image rectangle scaled inside the node box. */
const buildFittedImage = (parent: Shape, node: SpecNode, image: any): Shape => {
  const fit = node.fit;
  const naturalWidth = toNumber(image.width) || (node.nat && toNumber(node.nat[0])) || node.w!;
  const naturalHeight = toNumber(image.height) || (node.nat && toNumber(node.nat[1])) || node.h!;
  const scale = fit === "cover" ? Math.max(node.w! / naturalWidth, node.h! / naturalHeight)
                                : Math.min(node.w! / naturalWidth, node.h! / naturalHeight);
  const imageWidth = naturalWidth * scale, imageHeight = naturalHeight * scale;
  // object-position as fractions of the free space (0.5 = centred)
  const alignX = node.pos ? toNumber(node.pos[0], 0.5) : 0.5, alignY = node.pos ? toNumber(node.pos[1], 0.5) : 0.5;
  let shape: Shape;
  if (fit === "contain") {
    shape = penpot.createRectangle(); parent.appendChild(shape); shape.resize(imageWidth, imageHeight);
    shape.x = node.x! + (node.w! - imageWidth) * alignX; shape.y = node.y! + (node.h! - imageHeight) * alignY;
    shape.fills = [{ fillOpacity: toNumber(node.iop, 1), fillImage: image }]; applyCommon(shape, { ...node, fill: undefined });
  } else {   // cover: clipping board around an oversized image rectangle
    shape = penpot.createBoard(); parent.appendChild(shape); shape.resize(node.w!, node.h!);
    shape.x = node.x!; shape.y = node.y!; shape.fills = []; shape.clipContent = true;
    applyCommon(shape, { ...node, fill: undefined });
    const picture = penpot.createRectangle(); shape.appendChild(picture); picture.resize(imageWidth, imageHeight);
    picture.x = node.x! + (node.w! - imageWidth) * alignX; picture.y = node.y! + (node.h! - imageHeight) * alignY;
    picture.fills = [{ fillOpacity: toNumber(node.iop, 1), fillImage: image }]; picture.name = (node.name || node.img) + " image";
  }
  return shape;
};

/** Build one node (and its children) under `parent`; node coordinates are absolute. */
export const build = (root: SpecNode, parent: Shape): Shape | null => {
  const made: Shape[] = runtime._made = [];
  const buildNode = (node: SpecNode, container: Shape): Shape | null => {
    let shape: Shape | null = null;
    const type = node.t;
    if (type === "board" || type === "frame") {
      shape = penpot.createBoard();
      container.appendChild(shape); size(shape, node); place(shape, node);
      shape.fills = paint(node.fill === undefined ? null : node.fill);
      shape.clipContent = !!node.clip;
      applyCommon(shape, { ...node, fill: undefined });
      const layout = node.layout ? applyLayout(shape, node.layout) : null;
      for (const child of node.children || []) {
        const built = buildNode(child, shape);
        // grid children with an explicit cell move there; others flow into the next free place
        if (built && layout && node.layout!.type === "grid" && child.child && child.child.cell) {
          layout.appendChild(built, child.child.cell[0], child.child.cell[1]);
        }
      }
      if (node.flex) { const rawLayout = shape.addFlexLayout(); Object.assign(rawLayout, node.flex); }
    } else if (type === "rect") {
      shape = penpot.createRectangle(); container.appendChild(shape); size(shape, node); place(shape, node); applyCommon(shape, node);
    } else if (type === "ellipse") {
      shape = penpot.createEllipse(); container.appendChild(shape); size(shape, node); place(shape, node); applyCommon(shape, node);
    } else if (type === "path" || type === "line") {
      shape = penpot.createPath(); shape.content = node.d; container.appendChild(shape);
      shape.fills = paint(node.fill === undefined ? null : node.fill);
      applyCommon(shape, { ...node, fill: undefined });
      if (node.stroke) shape.strokes = strokes(node.stroke).map(stroke => ({ ...stroke, strokeAlignment: "center" }));
    } else if (type === "text") {
      shape = makeText(container, node); applyCommon(shape, { ...node, fill: undefined, stroke: undefined });
    } else if (type === "image") {
      const image = runtime.imgs[node.img!];
      if (!image) { warn("image not uploaded: " + node.img); return null; }
      const fit = node.fit || "fill";
      if (fit === "cover" || fit === "contain") shape = buildFittedImage(container, node, image);
      else {
        shape = penpot.createRectangle(); container.appendChild(shape); size(shape, node); place(shape, node);
        shape.fills = [{ fillOpacity: toNumber(node.iop, 1), fillImage: image }]; applyCommon(shape, { ...node, fill: undefined });
      }
      if (!node.name) shape.name = node.img!;
    } else if (type === "svg") {
      shape = penpot.createShapeFromSvg(node.svg!);
      if (!shape) { warn("svg import failed: " + (node.name || "")); return null; }
      container.appendChild(shape);
      if (node.w && node.h && (Math.abs(shape.width - node.w) > 0.5 || Math.abs(shape.height - node.h) > 0.5)) shape.resize(node.w, node.h);
      place(shape, node); applyCommon(shape, { ...node, fill: undefined, stroke: undefined, r: undefined });
    } else if (type === "group") {
      const children = (node.children || []).map(child => buildNode(child, container)).filter(Boolean) as Shape[];
      if (!children.length) return null;
      shape = penpot.group(children); if (!shape) return null;
      applyCommon(shape, { ...node, fill: undefined, stroke: undefined, r: undefined });
    } else if (type === "component") {
      const component = penpot.library.local.components.find((candidate: any) => candidate.name === node.ref || candidate.id === node.ref);
      if (!component) { warn("component not found: " + node.ref); return null; }
      shape = component.instance() as Shape; container.appendChild(shape); place(shape, node);
      if (node.w && node.h) size(shape, node);
      applyCommon(shape, node);
    } else {
      throw new Error("unknown node type: " + type);
    }
    if (shape && node.child) applyChildLayout(shape, node.child);
    if (shape && node.key) runtime.ids[node.key] = shape.id;
    if (shape && node.component) {
      const component = penpot.library.local.createComponent([shape]);
      if (component && typeof node.component === "string") component.name = node.component;
    }
    if (shape) made.push(shape);
    return shape;
  };
  return buildNode(root, parent);
};

/** Build a batch of nodes under parentId (default: page root). */
export const buildMany = (nodes: SpecNode[], parentId?: string | null) => {
  const parent = parentId ? byId(parentId) : penpot.root;
  if (!parent) throw new Error("parent not found " + parentId);
  runtime.warnings = [];
  runtime._fit = [];
  runtime._ranges = [];
  const started = Date.now();
  let count = 0;
  for (const node of nodes) {
    let shape: Shape | null;
    try { shape = build(node, parent); }
    catch (error) {   // roll back partially built shapes so failures leave no debris
      for (const made of (runtime._made || []).slice().reverse()) { try { made.remove(); } catch (_) { /* already gone */ } }
      throw error;
    }
    if (shape) count++;
  }
  // every key built in this batch (including nested ones)
  const allKeys: Record<string, string> = {};
  const collect = (node: SpecNode): void => {
    if (node.key && runtime.ids[node.key]) allKeys[node.key] = runtime.ids[node.key];
    (node.children || []).forEach(collect);
  };
  nodes.forEach(collect);
  return { built: count, ids: allKeys, ms: Date.now() - started, warnings: runtime.warnings.slice(0, 50),
           fit: runtime._fit.length, ranges: runtime._ranges.length };
};

export const groupShapes = (ids: string[], name?: string): string | null => {
  const group = penpot.group(ids.map(byId).filter(Boolean) as Shape[]);
  if (group && name) group.name = name;
  return group && group.id;
};

export const ungroup = (id: string): boolean => { const group = byId(id); if (group) penpot.ungroup(group); return true; };
