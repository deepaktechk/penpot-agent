# Spec format

`pb build` (and `pb rebuild`, which generates a spec from a capture) creates Penpot shapes from a
JSON **spec**. You can write specs by hand or generate them. The TypeScript definition is
[`js/src/plugin/spec.ts`](../js/src/plugin/spec.ts).

Keys are short on purpose: specs travel through MCP requests limited to ~100 KB and are stored in
every project.

## Document

```json
{"version": 1, "width": 1920, "height": 4200, "images": {"hero-1a2b3c": "https://example.com/hero.png"},
 "nodes": [ { "t": "board", "key": "sec00", "name": "Hero", ... } ]}
```
A bare list of nodes also works. `images` maps asset keys to URLs; `pb build` uploads them once.
Coordinates are absolute in the page: with `--page-board`, they are relative to that board.

## Nodes

| Key | Meaning |
|---|---|
| `t` | type: `board`, `rect`, `ellipse`, `path`, `line`, `text`, `image`, `svg`, `group`, `component` |
| `key` | stable id; rebuilding the same key replaces the previous shapes (children get `key.N`) |
| `name` | layer name |
| `x`, `y`, `w`, `h` | position and size |
| `fill` | paint (below); boards default to none |
| `stroke` | `{c, w, op, style, align, cap}` or `[c, w, op, style, align]`, or a list of those |
| `sh` | shadows: `[[x, y, blur, spread, "#hex", opacity, inner?], ...]` |
| `r` | corner radius, or `[top-left, top-right, bottom-right, bottom-left]` |
| `op` | opacity 0..1 |
| `blur`, `blend` | layer blur, blend mode |
| `hidden`, `locked`, `flipX`, `flipY` | flags |
| `cons` | constraints `[horizontal, vertical]` |
| `data` | plugin data `{key: value}` |
| `children` | child nodes (boards and groups) |

Type-specific keys:

- **board**: `clip` (clip content), `layout` (auto layout, below), `flex` (raw Penpot flex layout properties)

Auto layout (written by `--layout auto`, or by hand):

- board `layout`: `{"type": "flex" | "grid", "dir": "row" | "column", "gap": 8 | [row, column],
  "padding": 8 | [vertical, horizontal] | [top, right, bottom, left], "justify": "start" | "center" | "end" |
  "space-between" | "space-around" | "space-evenly", "align": "start" | "center" | "end" | "stretch",
  "wrap": bool, "sizing": [horizontal, vertical], "pin": bool}` (`"fix"`, `"auto"` = hug, `"fill"`); grid:
  `"columns"`, `"rows"` tracks (`"1fr"`, `"200px"`, `"50%"`, `"auto"`). `pin` (flex, written by
  `--layout auto`): the children's `x`/`y` are where they must end up, and the build settles them there;
  without it the layout alone places the children and their `x`/`y` are placeholders.
- child `child`: `{"sizing": [h, v], "alignSelf": ..., "margin": 8 | [...], "absolute": true, "zIndex": n,
  "cell": [row, column]}`; `absolute` children keep their `x`/`y`.
- In a flex board the children list is the flow order and the paint order from the bottom. The builder
  creates the children at their `x`/`y` first and switches the layout on afterwards; Penpot recalculates
  layouts asynchronously, so absolute children are placed and flow children checked in later calls.
- **path / line**: `d` (SVG path data, absolute coordinates)
- **text**: `text` — see below
- **image**: `img` (asset key), `fit` (`fill`, `cover`, `contain`), `nat` (natural size `[w, h]`),
  `pos` (object-position as fractions `[0.5, 0.5]`), `iop` (image opacity)
- **svg**: `svg` (markup, imported as editable vectors)
- **component**: `ref` (library component name or id); any node: `component: true | "Name"` turns it into a component

## Paints

```
"#RRGGBB"                                          solid
["#RRGGBB", 0.5]                                   solid with opacity
{"g": [x1, y1, x2, y2, [["#hex", opacity, offset], ...]], "radial": 1}   gradient (points in the unit box)
{"img": "asset-key"}                               image fill
[paint, paint, ...]                                several fills
```

## Text

```json
{"t": "text", "x": 40, "y": 160, "w": 600,
 "text": {"text": "Hello\nworld", "font": "Inter", "weight": 700, "size": 48, "lh": 56, "ls": -1,
          "color": "#0B1320", "align": "left", "grow": "auto-width",
          "ranges": [[0, 5, {"color": "#EE3324", "weight": 800}]]}}
```
- `font`, `weight`, `italic`, `size`, `lh` (line height px) or `lhr` (ratio), `ls` (letter spacing px), `color`
- `upper`, `lower`, `cap` (text-transform), `deco` (`underline`, `line-through`)
- `align` (`left`, `center`, `right`, `justify`), `valign`, `grow` (`auto-width`, `auto-height`, `fixed`)
- `fitW`: fit the letter spacing so the text is exactly this wide
- `ranges`: `[start, end, style]` style overrides on character ranges

## Example

```json
{"t": "board", "name": "Hero", "x": 0, "y": 0, "w": 1920, "h": 760, "fill": "#F3F5F9", "clip": true, "children": [
  {"t": "rect", "x": 40, "y": 40, "w": 200, "h": 80, "r": 12,
   "fill": {"g": [0, 0, 1, 1, [["#EE3324", 1, 0], ["#EE3324", 0, 1]]]}},
  {"t": "text", "x": 40, "y": 160, "text": {"text": "Hello", "font": "Inter", "weight": 700, "size": 48, "color": "#0B1320"}},
  {"t": "image", "img": "hero-1a2b3c", "x": 900, "y": 80, "w": 600, "h": 400, "fit": "cover", "r": 18},
  {"t": "svg", "svg": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M4 12h16'/></svg>", "x": 10, "y": 10, "w": 24, "h": 24},
  {"t": "group", "name": "Card", "children": [{"t": "rect", "x": 40, "y": 400, "w": 300, "h": 200, "fill": "#FFFFFF"}]}
]}
```
A runnable version is in [`examples/hello-board.json`](../examples/hello-board.json):
`pb build examples/hello-board.json --page-board "Hello"`.

## Capture format

`pb capture` writes `layout.json`, documented in
[`js/src/shared/layout-types.ts`](../js/src/shared/layout-types.ts); the converter
(`src/pbridge/convert/`) turns it into a spec.
