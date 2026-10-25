// Shape queries used by `pb find`, patch selectors and target resolution.
import { byId, runtime } from "./state";

/** {id, ids, key, name (exact), re (regex on name), flags, type, text (substring), within (id), bbox [x,y,w,h], limit} */
export interface Query {
  id?: string;
  ids?: string[];
  key?: string;
  name?: string;
  re?: string;
  flags?: string;
  type?: string;
  text?: string;
  within?: string;
  bbox?: [number, number, number, number];
  limit?: number;
}

export const find = (query: Query = {}): Shape[] => {
  if (query.id) { const shape = byId(query.id); return shape ? [shape] : []; }
  if (query.ids) return query.ids.map(byId).filter(Boolean) as Shape[];
  if (query.key) { const shape = byId(runtime.ids[query.key]); return shape ? [shape] : []; }
  const root = query.within ? byId(query.within) : null;
  const namePattern = query.re ? new RegExp(query.re, query.flags || "i") : null;
  const matches = (shape: Shape): boolean => {
    if (query.name !== undefined && shape.name !== query.name) return false;
    if (namePattern && !namePattern.test(shape.name)) return false;
    if (query.type && shape.type !== query.type) return false;
    if (query.text !== undefined && !(shape.type === "text" && String(shape.characters).includes(query.text))) return false;
    if (query.bbox) {
      const [x, y, width, height] = query.bbox;
      if (shape.x > x + width || shape.x + shape.width < x || shape.y > y + height || shape.y + shape.height < y) return false;
    }
    return true;
  };
  const found = penpotUtils.findShapes(matches, root);
  return query.limit ? found.slice(0, query.limit) : found;
};
