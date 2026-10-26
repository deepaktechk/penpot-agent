# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/) (0.x: the CLI and formats may still change).

## [Unreleased]

## [0.1.1] - 2026-10-26

### Changed
- Faster builds (clockify.me, 712 nodes: full `pb rebuild --fix` 173 s → 84 s, unchanged rebuild 26 s,
  same QA result). Shape lookups use `page.getShapeById` (~0.2 ms) instead of a whole-document search
  (~600 ms per id), which made autofix take ~55 s; SVGs are downloaded in parallel before converting;
  images are uploaded concurrently (32 images: 21 s → 4 s); batches are packed by shape count and
  request size; the text post-passes run once per build; old sections are removed in one call;
  the offset audit runs in parallel processes; after autofix the board is exported once, not settled again.
- `pb rebuild` skips sections whose content did not change since the last build (`--all` rebuilds
  every section), saves its state after every section (an interrupted build resumes), and prints
  the time of each stage (`[rebuild] build 32.9s`) plus a `seconds` summary.
- `pb rebuild` with nothing changed (spec, reference, options and the Penpot file revision
  `<file id>@<revn>`) reuses the last result instead of building and exporting again: 30.8 s → 1.7 s on
  clockify.me. Any edit in Penpot bumps the revision, so a change is never hidden. The convert step
  is cached too (layout, screenshot, converter source, options, Penpot font list). `--all` forces both.
- Big sections on a full page are built on a temporary page of their own and moved onto the target
  page in one call (component instance + detach), when the measured cost model says it saves time
  (`build/plan.py:staging_saves_time`); `--no-staging` builds everything in place. Same QA result.

### Added
- Already in the v0.1.0 package but missing from its notes:
  - Capture: `--color-scheme dark|light`, `--cookies` and `--user-data-dir` (pages behind a login),
    `--widths` for several screen sizes; `pb responsive` builds one board per width.
  - Images and prompts: `pb reference` (any image as the QA reference), `pb analyze` (palette and
    content boxes, combined moodboard palette), `pb validate` (spec checker; `pb build` refuses
    invalid specs), example prompt specs in `examples/prompt/`.
  - Design review: `pb review` (contrast, text size, font sizes, near-duplicate colours, alignment,
    grid, touch targets, hygiene) with `--fix` and `--comment`; `pb comment`.
  - File: `pb page`, `pb version`, `pb code` (design → HTML/CSS/SVG), `pb tokens` (design tokens).
  - `pb export` batches: several targets, scales (`@2x`) and formats (jpeg, webp, pdf).
  - `pb verify`: handoff QA of a built site against its Penpot design.
  - Tests: plugin runtime in Node (base64/CRC transfer), validator, review, image analysis,
    capture session options, live Penpot checks (`pb selftest --build`).
- `pb bench build|export`: measures the plugin cost per shape by placement (page board, top-level board,
  parked viewport, hidden board, empty page, component transfer) and section vs whole-board exports.
  Temporary shapes and pages are removed afterwards.
- Optional Penpot access token (`PENPOT_ACCESS_TOKEN`, `PENPOT_URL`) for the backend API, reported by
  `pb doctor`; plan and measurements in docs/fast-build.md.

### Fixed
- After `pb rebuild --only`/`pb build --only` the rebuilt section was appended above every other
  section (e.g. the Footer above the Nav); sections now get the spec's layer order back after every
  build, with the fewest moves (`pb.orderChildren`, longest increasing subsequence).
- With `--page`, the page board was looked up by name in the whole document and could be a same-named
  board on another page (every section then failed with "parent not found"); only the current page
  counts now, and a remembered board on another page is a clear error instead of a second board.
- Elements hidden with `visibility: collapse` were built (clockify.me: the closed product-switcher
  dropdown under the logo); the capture now treats `collapse` like `hidden`. A child that sets
  `visibility: visible` inside a hidden parent is painted by browsers and is now captured too.
- Popups hidden with a zero-area `clip-path` (`circle(0)`, `inset(50%)`) were built (pumble.com: the
  closed "zoom" popups over the app mockups); the capture now treats them like `display: none`.
- An SVG image was stretched when a nested `<image preserveAspectRatio="none">` was read as the root's
  (pumble.com thread panel, 2.6×); only the root `<svg>` decides.
- Symbol lines (★ ✓ ♥, emoji) were squeezed: Chrome and Penpot draw symbols with different fallback
  fonts (clockify.me ratings: 72.7 px in Chrome, 64 px in Penpot). Single symbol lines now carry their
  browser width (`fitW`) and the plugin fits the letter spacing to Penpot's real width.
- Lazy images to the side of the viewport (logo marquees, carousels) never loaded, so the capture gate
  failed (getfieldy.com); after scrolling, capture switches remaining lazy images to eager loading.
- Opaque CSS background images were written with `"op": null`, which failed spec validation.
- A range style could bleed over a whole text (getfieldy.com: a blue first line coloured the whole
  heading); `verifyRanges` now also checks the text between ranges against its base style and
  re-applies it (line breaks, never painted, are not checked).
- The MCP answer "No Penpot instance connected" made pb fail at once; it now notifies and waits for the
  plugin like other "tab asleep" answers.
- `pb selftest --build` converted the fixture without Penpot's font list, so the Arial line failed
  with `font not found: Arial`; it now converts like `pb convert` (missing families use the fallback).
- Capture: pages using `font-display: optional` could be captured with the fallback font when the
  web font was not served from Chrome's cache in time (seen on CI). After a fallback-painted load,
  the capture now rewrites `optional` to `swap` and reloads.

## [0.1.0] - 2026-10-25

First public release.

### Added
- `pb` command line: website capture with a capture quality gate, conversion to a design spec,
  keyed and idempotent builds into Penpot through the Penpot MCP server, settled exports, pixel
  comparison (metrics, hotspots, montages, overlays), per-element offset audit with autofix,
  render quality gate with regression tracking, snapshots, patches, design-token export.
- Claude Code plugin and marketplace: the `penpot-agent` skill and the `/penpot-agent:setup`
  and `/penpot-agent:clone` commands.
- Installable with `uv tool install git+https://github.com/deepaktechk/penpot-agent`: the
  JavaScript bundles (including puppeteer-core) ship inside the Python package.
- MCP URL discovery from `PENPOT_MCP_URL`, `.pbridge/config.json`, project `.mcp.json` and
  `~/.claude.json`; `pb doctor` reports every missing requirement; `pb --version`.
- Documentation in `docs/`, contribution guide, CI.

[Unreleased]: https://github.com/deepaktechk/penpot-agent/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/deepaktechk/penpot-agent/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/deepaktechk/penpot-agent/releases/tag/v0.1.0
