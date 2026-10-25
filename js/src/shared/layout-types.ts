// The capture output format (layout.json), read by Python's converter
// (src/pbridge/convert/context.py documents how each field is used).

/** [x, y, width, height] in CSS px, rounded to 0.01. */
export type Rect = [number, number, number, number];

/** [family, size, weight, lineHeight, letterSpacing, color, textAlign, textTransform, fontStyle, textDecorationLine] */
export type FontTuple = [string, string, string, string, string, string, string, string, string, string];

// Keys are short on purpose (a page dump has thousands of elements); each is spelled out below.

/** One browser line box: t = text, r = rect, hid = painted outside the element and not visible. */
export interface TextLine { t: string; r: Rect; hid?: 1 }

export interface SvgText {
  text: string | null;
  r: Rect;
  scale: number;
  /** [family, size, weight, letterSpacing, fill, opacity, textAnchor] */
  font: [string, string, string, string, string, string, string];
  lines: { t: string | null; r: Rect }[];
}

export interface BoxStyle {
  bg: string;                              // background-color
  bi?: string;                             // background-image
  bsize: string; bpos: string; brep: string;   // background-size / -position / -repeat
  bw: number[]; bs: string[]; bc: string[];    // border widths / styles / colors (top, right, bottom, left)
  radius: string[];                        // corner radii (top-left, top-right, bottom-right, bottom-left)
  shadow?: string;                         // box-shadow
  clip?: string;                           // clip-path
  blur?: string;                           // backdrop-filter
  filter?: string;
  mix?: string;                            // mix-blend-mode
}

/** A painted ::before / ::after box: computed CSS values of the pseudo element (pe), as strings.
 *  w/h size, pos position, bg/bi background, bw/bc top border, op opacity, font font-size, tf transform. */
export interface PseudoBox {
  pe: "::before" | "::after";
  content: string;
  w: string; h: string; top: string; left: string; right: string; bottom: string; pos: string;
  bg: string; bi?: string; radius: string; bw: string; bc: string; op: string; color: string; font: string; tf: string;
}

/** One emitted DOM element. Optional fields are only present when relevant. */
export interface CapturedElement {
  i: number;            // index in document order
  p: number;            // index of the nearest emitted ancestor, -1 for roots
  tag: string;
  r: Rect;              // border box on the page
  op: number;           // effective opacity through ancestors
  os?: [number, number];        // offsetWidth/Height when different from the transformed box
  clip?: Rect;                  // ancestor overflow clip rect when the element pokes out of it
  htmlId?: string;
  cls?: string;                 // class attribute (first 120 chars)
  pos?: string;                 // CSS position (when not static)
  z?: number;                   // z-index
  tf?: string;                  // computed transform
  // svg
  svg?: string; svgTexts?: SvgText[]; color?: string;
  // img: cbox content box, nat natural size, fit object-fit, opos object-position
  cbox?: Rect; src?: string; nat?: [number, number]; fit?: string; opos?: string; radius?: string; alt?: string;
  // video / canvas
  poster?: string; dataUrl?: string;
  // form controls (phColor: ::placeholder color)
  input?: { type: string; value: string; placeholder: string }; phColor?: string;
  // text: disp display, clamp line-clamp or 1 for single-line ellipsis, deco text-decoration
  text?: string; font?: FontTuple; disp?: string; lines?: TextLine[]; clamp?: number; textGradient?: string;
  deco?: { line: string; color: string; thick: string; offset: string };
  // visible: text shown before the browser's "…"; ovh: overflow not visible; tclip: ancestor clip of the text;
  // tov text-overflow; ws white-space; lc / lcBox: line-clamp and the box of the ancestor that sets it; pad: padding
  visible?: string; ovh?: 1; tclip?: Rect; tov?: string; ws?: string; lc?: number; lcBox?: Rect; pad?: number[];
  // decoration
  box?: BoxStyle;
  pseudo?: PseudoBox[];
}

export interface CaptureQuality {
  fontRender: Record<string, { samples: number; medianDev: number; loaded: boolean }>;
  brokenImages: string[];
  lazyPending: number;
  stableSamples?: number | null;   // set by the node side
  freeze?: boolean;
}

export interface LayoutDump {
  url: string;
  title: string;
  width: number;
  height: number;
  bodyBg: string;
  fonts: string[];
  quality: CaptureQuality;
  elements: CapturedElement[];
}
