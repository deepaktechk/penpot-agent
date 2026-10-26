# Command reference

Every command works on the **project** found by walking up from the current folder to a
`.pbridge/` folder (create one with `pb init`). `pb <command> -h` prints the options of a command.

Global options (before the command): `-c` one-line JSON output, `-v` print the timing of every
plugin call, `--version`.

**Targets.** Wherever a command takes a target, it accepts a Penpot shape id, a spec key
(`sec03.2.1`, see `.pbridge/idmap.json`), an exact layer name or a regex on layer names, `page`
(the project's page board) or `selection` (the current selection in Penpot).

## Setup

| Command | Purpose |
|---|---|
| `pb init [dir] [--reference shot.png]` | create `.pbridge/` (config, sub-folders, `.gitignore`) |
| `pb doctor` | check Node.js, Chrome, bundles, MCP server and plugin; exit 1 with a `problems` list; `backend` shows the optional access-token API |
| `pb prelude [--force]` | (re)inject the in-plugin runtime (normally automatic) |
| `pb selftest [--no-capture] [--build]` | regression suite (source checkout only); `--build` also builds in Penpot |

## Website → Penpot

| Command | Purpose |
|---|---|
| `pb capture URL [--name N] [--fonts "A,B"] [--width 1920] [--widths 1440,768,390] [--hide sel] [--click sel] [--wait ms] [--selector sel] [--color-scheme dark\|light] [--cookies file.json] [--user-data-dir DIR] [--force]` | screenshot + layout dump behind the capture gate; becomes the project reference |
| `pb convert [capture] [--fallback-font F] [--system-font F] [--font-map "Web=Penpot"] [--region y0,y1] [--flat] [--no-font-check]` | layout → spec JSON in `.pbridge/specs/` |
| `pb rebuild [--board NAME] [--after BOARD\|'*'] --font F [--only keys] [--all] [--fix] [--hotspots N] [--montage N]` | convert → build → [autofix] → compare → render gate; sections unchanged since the last build are kept (`--all` rebuilds them too); prints the time of each stage |
| `pb clone URL --board NAME [--fonts F] [--fallback-font F]` | capture → convert → build → compare in one go |
| `pb library [--colors 12] [--types 12] [--prefix Site] [--dry]` | most used colours and text styles → Penpot library |
| `pb tokens [--capture C] [--set Site] [--colors 12] [--dry]` | capture colours and type → a Penpot design-token set |
| `pb responsive URL --board NAME [--widths 1440,768,390] [--font F]` | capture several widths; one board per width (`NAME – <width>px`), side by side |

Capture options shared by `capture`, `clone`, `responsive` and `verify`: `--color-scheme` emulates
`prefers-color-scheme` (default light, whatever the OS says); `--cookies` loads a JSON cookie file
exported from the browser and `--user-data-dir` uses a logged-in Chrome profile, for pages behind a login.

## Images and prompts → Penpot

| Command | Purpose |
|---|---|
| `pb reference image.png [--width W] [--name N]` | make a screenshot/mockup the project reference (for `compare`/`qa` after building it) |
| `pb analyze img.png [more.png ...] [--region y0,y1\|x,y,w,h] [--colors 8] [--boxes 60]` | palette, background and content boxes of images; several images also give a combined moodboard palette |
| `pb validate spec.json` | check a spec (types, required fields, colours, ranges, layout values; "did you mean" for misspelled keys) |

`pb build` runs the same validation and refuses a spec with errors before touching Penpot.
Hand-written example specs (for prompt-to-design) are in `examples/prompt/`.

`--after` places a **new** page board to the right of the named board (`'*'` = right of everything).

## Visual QA

| Command | Purpose |
|---|---|
| `pb compare [--render latest\|PNG] [--region y0,y1\|x,y,w,h] [--hotspots N] [--montage N] [--overlay --mode stack\|overlay\|heat\|side] [--ssim]` | metrics vs the reference; images in `.pbridge/diffs/` |
| `pb audit [--keys sec03] [--fix --max-shift 6]` | per-element offset search; `--fix` moves misplaced elements |
| `pb offset name=x,y,w,h ...` | best (dx, dy) shift for named regions |
| `pb qa [--render latest] [--no-record]` | render gate: exit 1 when it fails |
| `pb verify URL [--width 1920] [--target T] [--design PNG] [--max-pct 3]` | handoff QA: capture the built site and compare it with its Penpot design |

## Design review

| Command | Purpose |
|---|---|
| `pb review [target] [--spec file] [--render PNG\|--no-render] [--grid 8] [--mobile] [--rules list] [--fix] [--comment] [--limit 50] [--all]` | review a live design (or a spec file offline) |
| `pb comment target "text"` | post a comment on the canvas, pinned to a shape |

Rules: `contrast` (WCAG ratio, from the exported render when available), `small-text`, `font-size`
(too many sizes), `near-duplicate-color`, `alignment`, `grid` (with `--grid`), `touch-target`
(44×44 px, with `--mobile`), `hygiene` (default names, empty layers). `--fix` applies the safe fixes
(live: a snapshot is taken first; `--spec`: the file is rewritten); `--comment` posts the issues on the canvas.

Without `--render`, these commands export `--target` (default: the page board) first.
Metrics: `mad` mean absolute difference (0–255), `pct` % of pixels that differ noticeably.

## Inspect

| Command | Purpose |
|---|---|
| `pb tree [target] [-d 2] [--json]` | layer tree |
| `pb find [--name N] [--re R] [--type T] [--text S] [--within target] [--limit 50]` | find shapes |
| `pb inspect target [-d 1] [--paths]` | shape → spec JSON |
| `pb stats [target]` | counts by type, fonts and colours in use |
| `pb lint [target]` | empty texts, degenerate sizes, empty groups, default layer names |
| `pb fonts [Family ...]` | which font families (and weights) Penpot has |
| `pb api Type [member]` | Penpot plugin API documentation |
| `pb page list\|create NAME\|open NAME_OR_ID` | pages of the file |
| `pb version save [label]\|list` | file versions (history snapshots) |
| `pb code [target] [--type html\|svg] [--out ./code]` | design → HTML/CSS (or SVG) via Penpot's code generator |

## Create and edit

| Command | Purpose |
|---|---|
| `pb build spec.json [--page-board NAME] [--parent target] [--only keys] [--font F] [--no-replace]` | build a spec; rebuilding a key replaces its previous shapes |
| `pb patch ops.json\|'<json>' [--snapshot target]` | apply patch operations (below) |
| `pb rm target ...` | remove shapes |
| `pb snapshot target [--label L]` / `pb restore L\|list [--parent target]` | save / restore a subtree |
| `pb assets list\|sync\|url URL\|file PATH [--crop x0,y0,x1,y1] [--quantize 32] [--fmt JPEG]` | image uploads (cached, deduplicated) |
| `pb export [target ...] [--format png\|jpeg\|webp\|svg\|pdf] [--scale 1,2,3] [--out file\|dir] [--fast]` | settled export; several targets/scales → batch into `.pbridge/exports/` (`@2x` suffixes) |

### Patch operations

A list of operations; each selects shapes (`sel`, same fields as `pb find`, plus `id`, `ids`, `key`)
and applies changes:

```json
[{"sel": {"key": "sec01.3"}, "move": [0, -2]},
 {"sel": {"re": "^Nav "}, "set": {"fill": "#111111"}},
 {"sel": {"text": "Get A Quote"}, "set": {"text": "Contact us", "textStyle": {"weight": 600}}},
 {"sel": {"name": "Old"}, "remove": true},
 {"sel": {"id": "…"}, "z": "front", "rename": "Hero image"}]
```
- `set`: `x, y, w, h, name, fill, stroke, sh, op, r, text, textStyle {font, weight, size, lh, ls, color, range: [start, end]}, align, grow, hidden, visible`
- `move: [dx, dy]` (relative), `scale: factor`, `remove: true`, `z: "front" | "back" | index`,
  `reparent: id`, `rename: "…"`

## Scripting

```bash
pb eval 'return penpot.currentPage.name'
pb eval 'return pb.find({type: "text", limit: 5}).map(s => s.name)'
pb run script.js --data input.json
```
In scripts, `penpot` is the Penpot plugin API, `DATA` the `--data` content and `pb` the helper
runtime (`pb.find`, `pb.byId`, `pb.build`, `pb.patch`, `pb.serialize`, `pb.paint`, ...; see
`js/src/plugin/index.ts`). Do not use timers (`setTimeout`) in scripts: background tabs run them
about once a minute.

## Environment variables

| Variable | Meaning |
|---|---|
| `PENPOT_MCP_URL` | MCP URL (overrides every other source; see [penpot-setup.md](penpot-setup.md)) |
| `PENPOT_ACCESS_TOKEN` | optional personal access token for the Penpot backend API (bulk uploads/imports without the browser tab); never stored in project files. See [fast-build.md](fast-build.md) |
| `PENPOT_URL` | backend base URL for the access token (default `https://design.penpot.app`; or config `penpot_url`) |
| `PBRIDGE_PROJECT` | project folder (instead of searching upwards for `.pbridge/`) |
| `PBRIDGE_WAIT` | seconds to wait for a sleeping Penpot tab (default 600, 0 = fail at once) |
| `CHROME_PATH` | Chrome/Chromium binary for capture |

## Project state (`.pbridge/`)

`config.json` (reference, capture, page board), `assets.json` (uploaded images), `idmap.json`
(spec key → shape id), `boxes.json` (target boxes for audit), `section_hashes.json` (content hash
of each built section; unchanged sections are skipped on rebuild), `history.json` (render-gate runs),
and the folders `captures/`, `specs/`, `renders/`, `diffs/`, `snapshots/`.
