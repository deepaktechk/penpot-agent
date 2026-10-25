// The pbridge spec format (what Python's converter produces and `pb.build` consumes).
// Coordinates are absolute canvas coordinates by the time they reach the plugin.

/** "#RRGGBB" | "#RRGGBBAA" | [hex, opacity] | gradient | image | list of those | null */
export type Paint = string | [string, number] | GradientPaint | ImagePaint | Paint[] | null | undefined | false;

/** {g: [x1, y1, x2, y2, [[hex, opacity, offset], ...]]} in the shape's unit box. */
export interface GradientPaint { g: [number, number, number, number, [string, number, number][]]; radial?: 1; op?: number }
export interface ImagePaint { img: string; op?: number }

/** {c, w, op, style, align, cap} or the array form [c, w, op, style, align]. */
export type StrokeSpec = { c?: string; w?: number; op?: number; style?: string; align?: string; cap?: string } | any[];
/** [x, y, blur, spread, color, opacity, inner?] or the object form. */
export type ShadowSpec = any[] | { x?: number; y?: number; blur?: number; spread?: number; c?: string; op?: number; inner?: any };

/** Style overrides used by whole texts, ranges and patches. */
export interface TextStyle {
  font?: string;
  weight?: number | string;
  italic?: boolean;
  size?: number;
  lh?: number;          // line height in px (needs size)
  lhr?: number;         // line height ratio
  ls?: number;          // letter spacing in px
  color?: Paint;
  upper?: boolean;
  lower?: boolean;
  cap?: boolean;
  deco?: string | null;
  range?: [number, number];   // patch only: style a sub-range
}

export type Range = [number, number, TextStyle];

export interface TextSpec extends TextStyle {
  text: string;
  align?: string;
  valign?: string;
  grow?: string;
  fitW?: number;
  ranges?: Range[];
}

/** Auto-layout of a board. CSS-like names; see layout.ts. */
export interface LayoutSpec {
  type: "flex" | "grid";
  dir?: "row" | "row-reverse" | "column" | "column-reverse";
  gap?: number | [number, number];                 // [row gap, column gap]
  padding?: number | number[];                     // 8 | [vertical, horizontal] | [top, right, bottom, left]
  align?: "start" | "center" | "end" | "stretch";  // align-items
  justify?: "start" | "center" | "end" | "stretch" | "space-between" | "space-around" | "space-evenly";
  alignContent?: string;
  wrap?: boolean;                                  // flex only
  sizing?: ["fix" | "auto" | "fill", "fix" | "auto" | "fill"];   // board [horizontal, vertical]; auto = hug content
  columns?: (string | number)[];                   // grid tracks: "1fr", "200px", "50%", "auto"
  rows?: (string | number)[];
}

/** Layout properties of a child inside an auto-layout board. */
export interface ChildLayoutSpec {
  sizing?: ["fix" | "auto" | "fill", "fix" | "auto" | "fill"];
  alignSelf?: "start" | "center" | "end" | "stretch" | "auto";
  margin?: number | number[];
  absolute?: boolean;                              // ignore the layout (positioned by x/y)
  zIndex?: number;
  minW?: number; maxW?: number; minH?: number; maxH?: number;
  cell?: [number, number];                         // grid only: [row, column], 1-based
}

// Keys are short on purpose: specs are sent through MCP requests of at most ~100 KB and stored in
// every project (.pbridge/specs, history). The comments below spell each one out.
export interface SpecNode {
  t: "board" | "frame" | "rect" | "ellipse" | "path" | "line" | "text" | "image" | "svg" | "group" | "component";   // node type
  key?: string;
  tag?: string;
  name?: string;
  x?: number; y?: number; w?: number; h?: number;   // position and size (width, height)
  fill?: Paint;
  stroke?: StrokeSpec;
  sh?: ShadowSpec[];          // shadows
  blur?: number;
  op?: number;                // opacity 0..1
  blend?: string;
  r?: number | number[];      // corner radius, or [top-left, top-right, bottom-right, bottom-left]
  hidden?: boolean;
  locked?: boolean;
  flipX?: boolean;
  flipY?: boolean;
  cons?: [string?, string?];  // constraints [horizontal, vertical]
  data?: Record<string, unknown>;   // plugin data written with setPluginData
  clip?: boolean;             // board clips its content
  flex?: Record<string, unknown>;   // raw Penpot FlexLayout properties (prefer `layout`)
  layout?: LayoutSpec;              // board auto-layout (flex / grid)
  child?: ChildLayoutSpec;          // this node's properties inside its parent's auto-layout
  d?: string;                 // path data
  text?: TextSpec;
  img?: string;               // image asset key
  fit?: "fill" | "cover" | "contain";
  nat?: [number, number];     // natural (intrinsic) image size
  pos?: [number, number];     // object-position (0..1)
  iop?: number;               // image fill opacity
  svg?: string;
  ref?: string;               // component name or id
  component?: string | boolean;
  children?: SpecNode[];
}
