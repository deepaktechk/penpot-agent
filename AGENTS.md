# AGENTS.md

Guide for AI coding agents (Claude Code, Codex, Cursor, ...) working **on** penpot-agent.
Humans: the same rules are in [CONTRIBUTING.md](CONTRIBUTING.md). To **use** the tool, see
[README.md](README.md) and [docs/](docs/).

## What this repository is

penpot-agent (`pb`) is a Python + TypeScript CLI that drives a Penpot file through the Penpot MCP
server. Its main job is cloning live websites into Penpot designs **pixel-accurately**, with
automated visual QA. The repository is also a Claude Code plugin and plugin marketplace.

```
.claude-plugin/       plugin.json (the plugin) + marketplace.json (installable via /plugin)
skills/               Claude Code skills shipped by the plugin (penpot-agent, setup, clone)
src/pbridge/          Python package (see docs/architecture.md)
  bundles/            built JS (plugin runtime, page library, node CLI) - generated, committed
js/                   TypeScript sources: src/plugin, src/capture(+page), src/rasterize, src/shared
tests/                unit tests + fixtures/tricky.html (every pattern that ever broke)
docs/                 user and contributor documentation
pb                    launcher for a source checkout (installed copies have `pb` on PATH)
```

## Setup

```
uv sync                                            # .venv + pbridge (editable) + pytest/ruff
npm --prefix js ci                                 # TypeScript toolchain (only to change js/src)
./pb doctor
```

## Rules (follow strictly)

1. **Accuracy is a must.** The reference is the fully loaded live site with the real web font.
   Judge by `pb compare` / `pb qa` numbers and montages, not by eye alone.
2. **A fixed bug must never come back.** For every bug: first add an element to
   `tests/fixtures/tricky.html` and/or a unit test, then fix, then run `./pb selftest`
   (`./pb selftest --build` for Penpot-side issues).
3. Use `pb`, not raw `mcp__penpot__execute_code`, for anything non-trivial. Extend `pb` when it
   lacks a feature instead of working around it.
4. Never print, log or commit the MCP URL / token (`userToken=`); pbridge redacts it in errors.
5. Readable code: small single-purpose modules, typed (Python hints, strict TypeScript), a header
   docstring/comment on every module, comments on non-obvious logic.
6. **Descriptive names only.** No `a, b, c, e, p, r, s, t, w, h, cs, el, sh...` variables: write
   `element`, `style`, `shape`, `width`, `reference`, `render`. Allowed: `i`/`j` (loop index),
   `x`/`y`, `dx`/`dy`, `id`, `ok`, `_`. Enforced by `tests/test_naming.py` and `npm --prefix js run lint`.
   Applies to JS snippets inside Python strings too.
7. After changing `js/src/`, run `npm --prefix js run check` and **commit the rebuilt
   `src/pbridge/bundles/`** (CI fails when they are stale). Never hand-edit bundles or `.venv`.
8. Python deps with uv only (`uv add`, `uv sync`); no pip. Runtime dependencies: stdlib + Pillow.

## Checks before you finish

```
uv run ruff check src tests
uv run python -m unittest tests.test_convert tests.test_discovery tests.test_naming tests.test_packaging tests.test_build_plan tests.test_svg_source tests.test_image_analysis   # fast, offline
./pb selftest                     # + fixture capture (needs Chrome + network)
npm --prefix js run check         # typecheck + name check + build (when js/src changed)
```

## Hard-won Penpot / MCP quirks

- `execute_code` request limit ~100 KB → pb chunks data through plugin storage.
- `penpotUtils.findShapeById` scans the whole document (~600 ms per id on a 1400-shape page); use
  `pb.byId` (built on `page.getShapeById`, ~0.2 ms). Every plugin property change also gets slower as
  the document grows (~9 ms per shape on an empty file, ~45 ms at 1400 shapes): send fewer, fuller calls.
- Plugin storage is wiped when the plugin reloads → pb re-injects the sha-versioned runtime.
- Each plugin task is killed after ~120 s → big sections are built incrementally / in batches;
  only retry idempotent operations (absolute positions, replace-by-key).
- Background-tab timer throttling (~1/min): never `setTimeout`/sleep inside the plugin; wait in Python.
- Errors come back as text `"Tool execution failed…"`, not as exceptions.
- Plugin sandbox `fetch` is blocked; `penpot.uploadMediaUrl` works for public URLs; local/private
  files are uploaded as bytes; SVGs Penpot can't fetch are rasterized in Chrome at 2×.
- Text range styles are flaky on later paragraphs and on ranges ending at text end (pb verifies and
  re-applies; end ranges applied inversely). No gradients on text ranges (→ per-char colours).
- Text resize/grow-type is slow in Penpot → layout math is done offline (`convert/fontmetrics.py`).
- Sites with `font-display: optional` need a warm-up visit before capture (capture does it). Chrome
  paints such a font only when it is already cached at first layout; a network answer, however fast,
  is too late. If a load still paints the fallback, capture rewrites `optional` to `swap` in HTML/CSS
  responses and reloads (`js/src/capture/steps/font-display.ts`).
- Tailwind v4 sites use CSS `lab()`/`oklch()` colours (converter handles them).
- Complex SVGs (clipPath/mask/pattern/filter/use/image/text) are rasterized; simple ones become vectors.
- In the capture (Chrome), SVG `getScreenCTM()` returns an `SVGMatrix` (`a`..`f` only, no `m11`..`m22`).
- The plugin runtime bundle must not start with "use strict" (it is spliced into a function body);
  `js/build.mjs` checks this.

## Code conventions

- **Python** (`src/pbridge/`): one responsibility per module; sub-packages re-export their public
  names in `__init__.py`. CLI handlers in `cli/commands/<topic>.py` are thin (`cmd_<name>` +
  `add_<name>` parser registering `handler=cmd_<name>` + a `PARSERS` table); multi-step logic goes
  to `workflows.py` or the owning package. New command → topic module + `COMMAND_ORDER` in `cli/app.py`
  + docs/commands.md.
- **TypeScript** (`js/src/`): three environments, three tsconfigs — `plugin/` (Penpot sandbox, ES2020,
  globals in `globals.d.ts`, API assembled in `index.ts`; Python mutates `pb.*` state directly, so
  modules read state through `runtime` from `state.ts`), `capture/page/` (browser DOM, exposed as
  `window.__pbCapture`, called via `pageCall()`), and the Node CLI (`node-cli.ts`, `capture/`,
  `rasterize/`, `shared/`).
- Short JSON keys of the spec / capture formats (`t`, `w`, `h`, `r`, `op`, `sh`...) are a stored
  format used by existing projects: keep them; they are documented in `js/src/plugin/spec.ts`,
  `js/src/shared/layout-types.ts` and docs/spec-format.md.
