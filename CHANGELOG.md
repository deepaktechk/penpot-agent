# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/) (0.x: the CLI and formats may still change).

## [Unreleased]

### Fixed
- Capture: pages using `font-display: optional` could be captured with the fallback font when the
  web font was not served from Chrome's cache in time (seen on CI). After a fallback-painted load,
  the capture now rewrites `optional` to `swap` and reloads.

### Added
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

[Unreleased]: https://github.com/deepaktechk/penpot-agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/deepaktechk/penpot-agent/releases/tag/v0.1.0
