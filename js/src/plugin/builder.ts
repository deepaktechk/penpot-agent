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
import type { PinItem } from "./state";
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

/** Switch the flex layout of `board` on once its children exist at their final x/y. Spec order = flow order =
 *  paint order from the bottom: a flex board flows AND paints its children by descending parentIndex (measured;
 *  adding a layout to a board with children re-sorts them), so the first spec child gets the highest index.
 *  Penpot then recalculates asynchronously, so absolute children are placed and flow children checked later,
 *  from Python, through the returned pin item. Flow children are checked only with `layout.pin` (converted
 *  pages: x/y come from the browser); in a hand-written layout their x/y are placeholders. */
const switchOnFlex = (board: Shape, node: SpecNode, children: [Shape, SpecNode][], pins: PinItem[]): void => {
  // where the builder put each child, read while the board is still plain: a contain-fitted picture sits inside
  // its box, not at the node's x/y, and that is where it must end up
  const placed = new Map(children.map(([built]) => [built, [toNumber(built.x), toNumber(built.y)]]));
  applyLayout(board, node.layout!);
  size(board, node);                         // keep the spec size whatever sizing the new layout started with
  children.forEach(([built], i) => built.setParentIndex(children.length - 1 - i));
  const item: PinItem = { board: board.id, box: [toNumber(node.x), toNumber(node.y), toNumber(node.w), toNumber(node.h)],
                          layout: node.layout, flow: [], absolute: [] };
  for (const [built, child] of children) {
    if (!child.child) continue;
    applyChildLayout(built, child.child);
    if (child.x === undefined || child.y === undefined) continue;
    const [x, y] = placed.get(built)!;
    if (child.child.absolute) item.absolute.push([built.id, x, y]);
    else if (node.layout!.pin) item.flow.push([built.id, x, y, toNumber(child.w), toNumber(child.h), child.child]);
  }
  pins.push(item);
};

/** Build one node (and its children) under `parent`; node coordinates are absolute. */
export const build = (root: SpecNode, parent: Shape, timings?: Record<string, number>): Shape | null => {
  const made: Shape[] = runtime._made = [];
  const absolute: [Shape, SpecNode][] = runtime._absolute = [];
  const buildNode = (node: SpecNode, container: Shape): Shape | null => {
    let shape: Shape | null = null;
    const type = node.t;
    const started = Date.now();
    if (type === "board" || type === "frame") {
      shape = penpot.createBoard();
      container.appendChild(shape); size(shape, node); place(shape, node);
      shape.fills = paint(node.fill === undefined ? null : node.fill);
      shape.clipContent = !!node.clip;
      applyCommon(shape, { ...node, fill: undefined });
      if (node.layout && node.layout.type === "grid") {
        // grid: cells decide where children go, so the layout is live while they are added
        const layout = applyLayout(shape, node.layout);
        for (const child of node.children || []) {
          const built = buildNode(child, shape);
          if (!built || !child.child) continue;
          applyChildLayout(built, child.child);
          if (child.child.absolute) absolute.push([built, child]);
          // children with an explicit cell move there; others flow into the next free place
          else if (child.child.cell) layout.appendChild(built, child.child.cell[0], child.child.cell[1]);
        }
      } else {
        // flex (or none): children are built at their final x/y first, as without a layout, and the layout is
        // switched on afterwards. Built inside a live layout, a child board is flowed into a provisional slot that
        // later siblings and its own margins still move, carrying its subtree (placed at absolute x/y meanwhile).
        const builtChildren: [Shape, SpecNode][] = [];
        for (const child of node.children || []) {
          const built = buildNode(child, shape);
          if (built) builtChildren.push([built, child]);
        }
        if (node.layout) switchOnFlex(shape, node, builtChildren, runtime._pins);
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
    // building into an existing layout board: its layout is already live (inside a spec board it is not yet)
    if (shape && node.child && shape.layoutChild) {
      applyChildLayout(shape, node.child);
      // the layout moved it into a flow slot when it was appended: back to x/y once every flow is final
      if (node.child.absolute) absolute.push([shape, node]);
    }
    if (shape && node.key) runtime.ids[node.key] = shape.id;
    if (shape && node.component) {
      const component = penpot.library.local.createComponent([shape]);
      if (component && typeof node.component === "string") component.name = node.component;
    }
    if (shape) made.push(shape);
    // per-type time of leaf shapes (containers include their children, so they are not counted)
    if (timings && !node.children) timings[type] = (timings[type] || 0) + Date.now() - started;
    return shape;
  };
  const built = buildNode(root, parent);
  // absolute children of grid boards and of layout boards built into: placed once this node is complete,
  // outermost first (children were pushed before parents); flex boards settle later (switchOnFlex)
  for (const [shape, node] of absolute.slice().reverse()) place(shape, node);
  return built;
};

/** Build a batch of nodes under parentId (default: page root). */
export const buildMany = (nodes: SpecNode[], parentId?: string | null) => {
  const parent = parentId ? byId(parentId) : penpot.root;
  if (!parent) throw new Error("parent not found " + parentId);
  runtime.warnings = [];
  runtime._fit = [];
  runtime._ranges = [];
  runtime._pins = [];
  const started = Date.now();
  const msByType: Record<string, number> = {};
  let count = 0;
  for (const node of nodes) {
    let shape: Shape | null;
    try { shape = build(node, parent, msByType); }
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
  // the text post-passes (fitTexts / verifyRanges) run once per build from Python, so the
  // work items go back with the result instead of staying in this batch's runtime state
  return { built: count, ids: allKeys, ms: Date.now() - started, msByType, warnings: runtime.warnings.slice(0, 50),
           fit: runtime._fit.length, ranges: runtime._ranges.length, fitItems: runtime._fit, rangeItems: runtime._ranges,
           pinItems: runtime._pins };
};

/** Switch on the flex layout of a board built incrementally (shell first, children in later calls; Python).
 *  DATA: {board: id, node: board spec without children, children: [{id, child, x, y}] in spec order}. */
export const finishFlex = (data: { board: string; node: SpecNode;
                                    children: { id: string; child?: any; x?: number; y?: number; w?: number; h?: number }[] }) => {
  const board = byId(data.board);
  if (!board) throw new Error("board not found " + data.board);
  const children = data.children.map(entry => [byId(entry.id), { t: "rect", child: entry.child, x: entry.x, y: entry.y,
                                                                  w: entry.w, h: entry.h }] as [Shape, SpecNode])
    .filter(([shape]) => !!shape);
  const pins: PinItem[] = [];
  switchOnFlex(board, data.node, children, pins);
  return { pinItems: pins };
};

/** Remove shapes by id in one call (previous builds of sections being rebuilt). Returns how many existed. */
export const removeMany = (ids: string[]): number => {
  let removed = 0;
  for (const id of ids) { const shape = byId(id); if (shape) { shape.remove(); removed++; } }
  return removed;
};

/** Indexes into `values` of a longest strictly increasing subsequence (patience sorting, O(n log n)). */
export const longestIncreasing = (values: number[]): number[] => {
  const tails: number[] = [];                                // tails[k]: last index of the best run of length k + 1
  const previous: number[] = new Array(values.length).fill(-1);
  for (let i = 0; i < values.length; i++) {
    let low = 0, high = tails.length;
    while (low < high) { const middle = (low + high) >> 1; if (values[tails[middle]] < values[i]) low = middle + 1; else high = middle; }
    if (low > 0) previous[i] = tails[low - 1];
    tails[low] = i;
  }
  const run: number[] = [];
  for (let i = tails.length ? tails[tails.length - 1] : -1; i >= 0; i = previous[i]) run.push(i);
  return run.reverse();
};

/** Give sibling shapes `ids` this relative layer order (bottom to top) with the fewest moves: the
 *  longest run already in order stays, every other shape goes right above its predecessor (the
 *  first one right below its successor). Layers that are not listed keep their place. */
export const orderChildren = (ids: string[]): { moves: number; ok: boolean } => {
  const shapes = ids.map(byId).filter(Boolean) as Shape[];
  const keep = new Set(longestIncreasing(shapes.map(shape => shape.parentIndex)));
  let moves = 0;
  shapes.forEach((shape, i) => {
    if (keep.has(i)) return;
    if (i > 0) {
      // taking the shape out shifts everything above it down by one
      const target = shapes[i - 1].parentIndex;
      shape.setParentIndex(shape.parentIndex > target ? target + 1 : target);
    } else {
      const successor = shapes.find((_, j) => j > 0 && keep.has(j));
      if (!successor || shape.parentIndex < successor.parentIndex) return;
      shape.setParentIndex(successor.parentIndex);
    }
    moves++;
  });
  const final = shapes.map(shape => shape.parentIndex);
  return { moves, ok: final.every((index, i) => i === 0 || index > final[i - 1]) };
};

/** Which of these ids still exist as shapes (to trust an unchanged section from a previous build). */
export const existing = (ids: string[]): string[] => ids.filter(id => !!byId(id));

export const groupShapes = (ids: string[], name?: string): string | null => {
  const group = penpot.group(ids.map(byId).filter(Boolean) as Shape[]);
  if (group && name) group.name = name;
  return group && group.id;
};

export const ungroup = (id: string): boolean => { const group = byId(id); if (group) penpot.ungroup(group); return true; };
