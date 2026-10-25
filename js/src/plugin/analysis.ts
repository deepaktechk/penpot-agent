// File analysis: usage statistics (`pb stats`) and design hygiene issues (`pb lint`).
import { byId, isArray } from "./state";

const rootOf = (rootId?: string | null): Shape => (rootId ? byId(rootId) : penpot.root) as Shape;

/** Shape counts by type, text styles in use, fill colors in use. */
export const stats = (rootId?: string | null) => {
  const counts: Record<string, number> = {}; const fonts: Record<string, number> = {}; const colors: Record<string, number> = {};
  penpotUtils.findShapes(shape => {
    counts[shape.type] = (counts[shape.type] || 0) + 1;
    if (shape.type === "text") {
      const style = `${shape.fontFamily} ${shape.fontWeight} ${shape.fontSize}`; fonts[style] = (fonts[style] || 0) + 1;
    }
    if (isArray(shape.fills)) for (const fill of shape.fills) if (fill.fillColor) colors[fill.fillColor] = (colors[fill.fillColor] || 0) + 1;
    return false;
  }, rootOf(rootId));
  return { counts, fonts, colors };
};

/** Empty texts, degenerate sizes, empty groups, default layer names (max 500). Issue entries: {id, n: name, issue}. */
export const lint = (rootId?: string | null) => {
  const issues: { id: string; n: string; issue: string }[] = [];
  penpotUtils.findShapes(shape => {
    if (shape.type === "text" && (!shape.characters || !String(shape.characters).trim())) issues.push({ id: shape.id, n: shape.name, issue: "empty text" });
    if (shape.width < 0.5 || shape.height < 0.5) issues.push({ id: shape.id, n: shape.name, issue: "degenerate size" });
    if (shape.type === "group" && (!shape.children || shape.children.length === 0)) issues.push({ id: shape.id, n: shape.name, issue: "empty group" });
    if (/^(Rectangle|Ellipse|Path|Board|Group)\s*\d*$/.test(shape.name)) issues.push({ id: shape.id, n: shape.name, issue: "default name" });
    return false;
  }, rootOf(rootId));
  return issues.slice(0, 500);
};
