// Globals available inside the Penpot MCP plugin sandbox.
//
// The plugin API is large and loosely typed at runtime (mixed values such as fills = "mixed"),
// so shapes are typed as `Shape` with the members pbridge uses plus an index signature.

/** Any Penpot shape (board, rectangle, ellipse, path, text, group, svg-raw, bool, ...). */
interface Shape {
  id: string;
  type: string;
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
  children?: Shape[];
  fills: any;
  strokes: any;
  shadows: any;
  [member: string]: any;
}

/** Text shapes and text ranges share the style members. */
interface TextLike {
  type?: string;
  fills: any;
  fontSize: string;
  fontWeight: string;
  lineHeight: string;
  letterSpacing: string;
  textTransform: string;
  textDecoration: string;
  [member: string]: any;
}

/** The `penpot` plugin API object. */
declare const penpot: {
  root: Shape;
  selection: Shape[];
  currentFile: { name: string } | null;
  currentPage: { id: string; name: string; getShapeById(id: string): Shape | null } | null;
  fonts: { all: any[]; findByName(name: string): any };
  library: { local: any };
  createBoard(): Shape;
  createRectangle(): Shape;
  createEllipse(): Shape;
  createPath(): Shape;
  createText(text: string): Shape | null;
  createShapeFromSvg(svg: string): Shape | null;
  group(shapes: Shape[]): Shape | null;
  ungroup(group: Shape): void;
  uploadMediaData(name: string, data: Uint8Array, mime: string): Promise<any>;
  uploadMediaUrl(name: string, url: string): Promise<any>;
  [member: string]: any;
};

/** Helpers provided by the Penpot MCP server's plugin. */
declare const penpotUtils: {
  findShapeById(id: string): Shape | null;
  findShapes(predicate: (s: Shape) => boolean, root?: Shape | null): Shape[];
  getPages(): any[];
  [member: string]: any;
};

/** Per-plugin key/value store that survives between execute_code calls (wiped on plugin reload). */
declare const storage: { pb?: any; [key: string]: any };

declare function atob(data: string): string;
declare function setTimeout(fn: () => void, ms: number): unknown;
