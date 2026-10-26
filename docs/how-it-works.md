# How it works

## Why a local tool

Talking to Penpot through one-off MCP `execute_code` calls means every byte of code and image
data is typed into requests capped at ~100 KB, plugin memory is lost when the plugin reloads,
exports race font loading, every plugin task is killed after ~120 s, and the browser throttles the
Penpot tab when it is in the background. penpot-agent moves all of that into a local tool: data
stays on disk, the in-plugin runtime is version-checked and re-injected automatically, payloads
are chunked, builds are batched, exports settle, and a sleeping tab is waited out.

## Pipeline

1. **Capture** (`pb capture`, Node.js + headless Chrome). A warm-up visit fills the HTTP cache with
   the web fonts (sites using `font-display: optional` otherwise keep the fallback font forever);
   the real visit reloads if text was still painted with a fallback; lazy content is scrolled into
   view; every font face in use is force-loaded; the page waits for a stable height and loaded
   images; CSS animations are paused and JS timers stopped once positions stop moving; cookie
   banners and chat widgets are hidden. Then the viewport is resized to the full page height, and
   **one** layout serves both the layout dump and the screenshot.
2. **Capture gate.** The capture proves itself: text widths are compared with canvas measurements
   in the declared font (a fallback font gives a systematic deviation), the page must have become
   still, images must have loaded, the screenshot must match the layout height. Failing captures
   are retried and never become the reference unless forced.
3. **Convert** (`src/pbridge/convert/`). The page is split into section boards (full-width
   wrappers are descended into, sections are named after their biggest heading). Each element
   becomes shapes: background/border/shadow boxes, images, inline SVGs, form values, text.
4. **Build** (`src/pbridge/build/` + the plugin runtime in `js/src/plugin/`). Sections are built by
   key; a rebuild removes the previous shapes of the same key first, so it is idempotent. Large
   sections are built as a board shell plus packed batches (at most 250 shapes / 400 KB per call),
   below the per-task time limit. Sections whose content did not change since the last build are
   kept (content hash per section; `--all` rebuilds them), and progress is saved after every
   section, so an interrupted build resumes. Text fitting and range checks run once at the end.
5. **Export and compare.** The board is exported until two renders are identical (fonts and
   images finished loading), then compared with the reference screenshot.
6. **Audit / autofix** (`--fix`). For every built element, the shift that best aligns the render
   with the reference is searched; small, clearly better shifts are applied as absolute positions
   (safe to retry).
7. **Render gate** (`pb qa`). Per-section thresholds, an image check, and a regression check
   against the last good run.

## Accuracy techniques

- **Line breaks come from the browser.** Every text line is measured with DOM ranges; Penpot gets
  the exact lines, so it never re-wraps differently.
- **Line height.** The text box is anchored on the first line's glyph box,
  `y = glyphTop − (lineHeight − glyphHeight) / 2`, so Penpot's line height matches CSS.
- **Font metrics offline.** When Penpot's font differs from the browser's (a substituted family, or
  a variable font with optical sizes vs Penpot's static one), letter spacing is fitted so the widest
  line matches. Widths are measured offline with the exact Google Fonts TTF Penpot uses
  (`convert/fontmetrics.py`), with no round trips to the browser tab.
- **Hidden text is dropped.** Lines outside their element and parent, `sr-only` text, lines a
  line-clamp hides (also when the clamp sits on an ancestor), and lines the screenshot shows no
  ink for. Ellipsis truncation is reproduced (one "…", never doubled).
- **Colours.** rgb/hsl/hex, `oklab()`, `oklch()`, CIE `lab()`/`lch()` (D50 → Bradford → sRGB),
  `color()`; gradients including gradient text, which is emulated with one colour per character
  because Penpot cannot paint gradients on text ranges.
- **SVG.** Inline SVGs are baked to screen space: computed paint styles become attributes and the
  full transform of every shape (viewBox, `preserveAspectRatio`, nested and CSS transforms, frozen
  animations) becomes one matrix. `<img>` SVGs become editable vectors, except complex ones
  (clipPath, mask, pattern, filter, use, image, text), which Penpot's importer mishandles: those
  stay raster. SVGs Penpot cannot fetch are rasterized locally at 2×.
- **Images** paint in their content box (padding excluded) with `object-fit` and
  `object-position`; elements partly cut by an overflow ancestor get a clipping board.
- **Pixel evidence.** `::before`/`::after` decorations and underlines in a different colour than
  their text are located in the screenshot, where the DOM cannot describe them.
- **Range styles are verified.** Penpot sometimes drops style ranges on later paragraphs of a
  fresh text; pb reads them back and re-applies them, and applies ranges that end at the text end
  inversely (a Penpot quirk).

## Quality gates

| Gate | Fails when | Where |
|---|---|---|
| capture | text painted with a fallback font (median width deviation > 2 %), broken images, screenshot ≠ layout, blank page, almost no elements | `quality/capture_gate.py` |
| render | a section differs > 3 % (warning > 1.6 %), an image/SVG box has mean abs diff > 40 (missing, blank or stretched), or a section got worse than the last good run by > 0.3 points and > 25 % | `quality/render_gate.py` |

Each `pb qa` run is appended to `.pbridge/history.json` (last 50); the last passing run is the
baseline for the regression check. Thresholds are in `quality/result.py`.

## Performance rules

- Browsers run background-tab timers about once a minute: the plugin runtime never sleeps; all
  waiting happens in Python between short calls.
- Each plugin task is killed after ~120 s: big sections are built in batches and big boards are
  exported child by child and stitched. Only idempotent calls are retried after a timeout.
- Text resizes and grow-type changes are slow in Penpot: layout maths is done offline.
