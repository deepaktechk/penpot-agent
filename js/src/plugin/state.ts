// Runtime state of the injected bridge. This object IS `storage.pb`: Python reads and writes
// some fields directly (pb.imgs[key] = ..., pb.defaultFont = ..., pb._ranges, pb._fit), so every
// module reads state through `runtime` at call time instead of caching it.
//
// Image descriptors, pending chunks and key->id maps survive a re-injection (version upgrade)
// because they are copied from the previous runtime.

export const VERSION = "__PB_VERSION__";   // replaced by Python with the sha1 of this bundle

/** A text waiting for width fitting: target width `w`, anchor x, alignment, multi-line flag. */
export interface FitItem { id: string; w: number; anchor: number; align: string; multi: boolean; text: string }
/** A text whose range styles [start, end, style] must be verified after Penpot settles. */
export interface RangeItem { id: string; ranges: [number, number, any][]; font: string }

export interface RuntimeState {
  version: string;
  imgs: Record<string, any>;                                    // asset key -> Penpot ImageData
  chunks: Record<string, { total: number; parts: string[] }>;   // chunked transfers in flight
  ids: Record<string, string>;                                  // spec key -> shape id (this session)
  warnings: string[];
  defaultFont?: string;
  _made?: Shape[];          // shapes created by the current build (rolled back on error)
  _fit: FitItem[];          // texts waiting for width fitting (pb.fitTexts)
  _ranges: RangeItem[];     // texts whose range styles must be verified (pb.verifyRanges)
  [member: string]: any;    // the API functions are attached in index.ts
}

const previous = storage.pb;

export const runtime: RuntimeState = {
  version: VERSION,
  imgs: (previous && previous.imgs) || {},
  chunks: (previous && previous.chunks) || {},
  ids: (previous && previous.ids) || {},
  warnings: [],
  _fit: [],
  _ranges: [],
};

export const isArray = Array.isArray;

/** Number or fallback (undefined/null/NaN -> fallback). */
export const toNumber = (value: unknown, fallback = 0): number =>
  (value === undefined || value === null || isNaN(+(value as number))) ? fallback : +(value as number);

/** Shape by id: `page.getShapeById` is a map lookup (~0.2 ms); `penpotUtils.findShapeById` scans the
 *  whole document (~600 ms per id on a 1400-shape page), so it is never used. Current page first. */
export const byId = (id: string | null | undefined): Shape | null => {
  if (!id) return null;
  const current = penpot.currentPage;
  const found = current && current.getShapeById(id);
  if (found) return found;
  for (const page of penpotUtils.getPages()) {
    if (current && page.id === current.id) continue;
    const shape = page.getShapeById && page.getShapeById(id);
    if (shape) return shape;
  }
  return null;
};

export const warn = (message: unknown): void => { runtime.warnings.push(String(message)); };

/** Promise-based sleep. Avoid in practice: background tabs run timers about once a minute. */
export const sleep = (milliseconds: number): Promise<void> => new Promise(resolve => setTimeout(resolve, milliseconds));
