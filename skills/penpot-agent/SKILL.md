---
name: penpot-agent
description: Drive Penpot with the penpot-agent CLI (`pb`) — clone a live website pixel-accurately into a Penpot board, rebuild or fix an existing clone, inspect, patch or export layers, and run visual QA against the reference. Use for any Penpot design work, "recreate this website/landing page in Penpot", "make a Penpot design from this URL", comparing a Penpot board with a site, or editing Penpot layers in bulk.
---

# penpot-agent (`pb`)

`pb` talks to Penpot through the Penpot MCP server and does the heavy lifting locally: website
capture in headless Chrome, conversion to a design spec, chunked and retried builds, settled
exports and pixel-level comparison. Prefer it over raw `mcp__penpot__execute_code` calls for
anything bigger than a quick probe.

## Which `pb` to run

1. `pb` on PATH (installed with `uv tool install git+https://github.com/deepaktechk/penpot-agent`).
2. Otherwise the copy shipped with this plugin: `"${CLAUDE_PLUGIN_ROOT}/pb"` (needs `uv`; the first
   run creates its virtual environment).
If neither works, or `pb doctor` reports problems, follow the `setup` skill (`/penpot-agent:setup`).

Below, `pb` means whichever of the two works.

## 0. Preflight (every session)

```
cd <project folder>        # a folder with .pbridge/ ; new project: mkdir site && cd site && pb init
pb doctor                  # JSON report; "problems": [] means ready
```
- `Penpot not reachable` → the MCP server is not configured or not running: see the setup skill.
- Plugin not connected / asleep → ask the user to open their Penpot file, start the MCP plugin
  (File → MCP Server → Connect) and keep that browser tab visible. Do not retry in a loop: pb
  itself waits up to `PBRIDGE_WAIT` seconds (default 600) and notifies the user.
- Node.js or Chrome missing → tell the user what to install (Node ≥ 20; Chrome or Chromium, or `CHROME_PATH`).

## 1. Clone a website

1. Look at the live site first: which web fonts, cookie banners, carousels? (`--hide`, `--click`)
2. Check the fonts exist in Penpot: `pb fonts Inter "DM Sans"`; missing ones need `--font`/`--font-map`.
3. Capture (the capture gate must PASS; never `--force` a failed capture into the reference):
   `pb -c capture https://example.com/ --name example --fonts "Inter"` (`--width 1920` default)
4. Build and check:
   `pb -c rebuild --board "Example – Landing Page" --after '*' --font Inter --fix --hotspots 6 --montage 6`
   Builds take several minutes: run with a long timeout, save the output to a file and grep for
   `[render]`, `✗`, `  !`, `ERROR`.
5. Read the montage PNG in `.pbridge/diffs/` and the worst sections in the JSON summary.

Shortcut for simple pages: `pb clone URL --board NAME --fonts F --fallback-font F`.

## 2. Iterate to pixel accuracy

| Need | Command |
|---|---|
| Zoom on a region | `pb -c compare --render latest --region x,y,w,h --hotspots 4 --montage 4` |
| Heat overlay | `pb compare --render latest --overlay --mode heat` |
| Per-element offsets + autofix | `pb audit --keys sec03 --fix --max-shift 6` |
| Best shift of a region | `pb offset logo=40,20,180,60` |
| Rebuild some sections only | `pb rebuild --only sec03,sec04 --font F` |
| Quality gate only | `pb qa` (exit code 1 on failure) |

Gate thresholds: a section with > 3.0 % differing pixels is an error, > 1.6 % a warning; an image
box with mean abs diff > 40 is an error ("missing, blank or mis-fitted"); a regression is > +0.3 %
and > +25 % worse than the last good run in `.pbridge/history.json`.

Where to look when something is off:
- `.pbridge/captures/<name>/layout.json` — what the browser saw (boxes, fonts, image fit, clips)
- `.pbridge/specs/<name>.json` — what was built; `.pbridge/idmap.json` — spec key → Penpot shape id
- Fix causes, not symptoms: hand patches on the board are lost on the next rebuild. If pb itself
  measures or converts something wrong, report it (or fix it in a source checkout, see CONTRIBUTING.md).

## 3. Inspect and edit

```
pb tree "Example – Landing Page" -d 3          # layer tree
pb find --text "Get started"                    # also --name / --re / --type / --within
pb inspect sec03.2.1                            # target = shape id | spec key | name | regex | page | selection
pb snapshot sec03 --label before && pb patch '[{"sel":{"key":"sec03.1"},"move":[0,-2]}]'
pb restore before                               # undo
pb export "Example – Landing Page" --fast       # PNG into .pbridge/renders/
pb eval 'return penpot.currentPage.name'        # JS with pb, DATA, penpot in scope
pb library --colors 12 --types 12 --prefix Site # design tokens from the capture into the library
```
Full reference: `${CLAUDE_PLUGIN_ROOT}/docs/commands.md`, spec format: `${CLAUDE_PLUGIN_ROOT}/docs/spec-format.md`.

## 3b. Other workflows

```
pb responsive URL --board "Site" --widths 1440,768,390   # one board per screen width
pb capture URL --color-scheme dark --cookies cookies.json  # dark mode / logged-in pages
pb analyze shot.png ref2.png                    # image/moodboard -> palette + content boxes
pb reference shot.png --width 1440              # image as QA reference, then write + build a spec
pb validate design.json && pb build design.json # prompt-to-design: always validate first (examples/prompt/)
pb review page --mobile --grid 8 [--fix|--comment]  # design review of an existing design
pb verify https://built.site --target "Site"    # handoff QA: built site vs Penpot design
pb page list | pb version save "before" | pb code page --out ./code | pb tokens --dry
pb export page --scale 1,2 --format webp        # batch exports into .pbridge/exports/
```

## 4. Rules

- Accuracy first: the reference must be the fully loaded site with the real web font; judge by
  the gate numbers and montages, not by eye alone.
- Never print or paste the MCP URL: it contains the user's token (`userToken=...`).
- Never sleep inside plugin JS (`pb eval` / `pb run`): background tabs run timers about once a minute.
- Not reproduced automatically: CSS filters / backdrop blur, masks, 3D transforms, video, canvas,
  iframes. Crop them from the reference: `pb assets file .pbridge/captures/<name>/shot.png --crop x0,y0,x1,y1`.
