<p align="center">
  <img src="assets/icon-256.png" width="112" alt="penpot-agent logo">
</p>

<h1 align="center">penpot-agent</h1>

<p align="center">
  <b>Convert any website into an editable, pixel-accurate Penpot design (HTML to Penpot) — from your terminal or from Claude Code, through the Penpot MCP server.</b>
</p>

<p align="center">
  <a href="https://github.com/deepaktechk/penpot-agent/actions/workflows/ci.yml"><img src="https://github.com/deepaktechk/penpot-agent/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-blue.svg" alt="License: GPL-3.0"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Penpot-MCP-7238ff.svg" alt="Penpot MCP">
  <img src="https://img.shields.io/badge/Claude%20Code-plugin-d97757.svg" alt="Claude Code plugin">
</p>

---

**penpot-agent** (`pb`) drives a [Penpot](https://penpot.app) file through the official
[Penpot MCP server](https://help.penpot.app/mcp/). Point it at a URL and it captures the page in
headless Chrome, rebuilds it in Penpot as real, editable layers (boards, text with the right fonts
and line breaks, vectors, images, gradients, shadows), then **measures the result against the live
site pixel by pixel** and fixes what it can.

It works as a standalone CLI and as a **Claude Code plugin**, so you can simply ask Claude:

> *"Recreate https://example.com as a Penpot board and get it under 1 % pixel difference."*

**Use it to** redesign an existing site starting from its real layout, migrate a live website or
landing page into an open-source design tool (a Figma alternative), rebuild a competitor's page as a
design reference, create design tokens from a site, or let an AI agent work on Penpot designs with
measurable accuracy.

## Features

- **Website → Penpot clone** — sections become named boards, text keeps the browser's exact line
  breaks, SVGs become editable vectors, `oklch()`/`lab()` colours, gradient text, line-clamps,
  pseudo-element decorations and coloured underlines are reproduced.
- **Your choice of positioning** — every layer at a fixed x/y, or Penpot auto layout (flex) wherever it
  reproduces the page exactly, so editing a text moves its neighbours. Both pass the same accuracy gate.
- **Visual QA built in** — page and per-section diff %, hotspot montages, heat overlays,
  per-element offset audit with automatic nudging, and a quality gate that fails on regressions.
- **Reliable over MCP** — payloads are chunked past the ~100 KB request limit, the in-plugin
  runtime is versioned and re-injected after reloads, long builds are batched under the 120 s task
  limit, and a throttled Penpot tab is waited out instead of failing.
- **Scriptable** — inspect, find, patch, snapshot/restore, export, design tokens → library, or run
  any JavaScript with a small `pb` helper API inside Penpot.
- **Claude Code plugin** — skills that teach Claude the whole workflow, plus `/penpot-agent:setup`
  and `/penpot-agent:clone`.

## Quick start

### Requirements

- A Penpot account or self-hosted Penpot **with the MCP server** — see [docs/penpot-setup.md](docs/penpot-setup.md)
- [uv](https://docs.astral.sh/uv/), [Node.js](https://nodejs.org) ≥ 20, Google Chrome or Chromium
- macOS or Linux (Windows is untested; WSL may work)

### Option A — Claude Code plugin

```
/plugin install penpot-agent --marketplace deepaktechk/penpot-agent
```
(older Claude Code: `/plugin marketplace add deepaktechk/penpot-agent`, then
`/plugin install penpot-agent@penpot-agent`)

Then run `/penpot-agent:setup` — Claude checks every requirement and walks you through connecting
Penpot — and try `/penpot-agent:clone https://example.com`. More in
[docs/claude-code-plugin.md](docs/claude-code-plugin.md).

### Option B — command line

```bash
uv tool install git+https://github.com/deepaktechk/penpot-agent
export PENPOT_MCP_URL="https://design.penpot.app/mcp/stream?userToken=..."   # see docs/penpot-setup.md

mkdir example && cd example && pb init
pb doctor                                    # "problems": [] means ready
pb capture https://example.com --fonts "Inter"
pb rebuild --board "Example – Landing Page" --font Inter --layout auto --fix --montage 6   # or --layout absolute
```
Open the Penpot file: the board is there. The `rebuild` output ends with the quality gate verdict;
the montage of the worst areas is in `.pbridge/diffs/`. Walkthrough: [docs/getting-started.md](docs/getting-started.md).

## How it works

```
 live site ──► capture (headless Chrome) ──► layout.json + screenshot   ← capture gate: real fonts, page still, images loaded
                                                   │
                                                   ▼
                                          convert (Python) ──► spec.json (boards, text, vectors, images)
                                                   │
                                                   ▼
 Penpot ◄── MCP server ◄── pb build (chunked, batched, retried; runtime injected into the MCP plugin)
   │
   └── export ──► compare with the screenshot ──► audit / autofix ──► render gate (thresholds + regression check)
```
Details: [docs/how-it-works.md](docs/how-it-works.md) · architecture: [docs/architecture.md](docs/architecture.md)

## Documentation

| | |
|---|---|
| [Getting started](docs/getting-started.md) | install, first clone, reading the results |
| [Penpot setup](docs/penpot-setup.md) | hosted, self-hosted and local MCP server; keeping the plugin connected |
| [Claude Code plugin](docs/claude-code-plugin.md) | install, skills, example prompts |
| [Commands](docs/commands.md) | every `pb` command and option, targets, patch operations |
| [Spec format](docs/spec-format.md) | the JSON design format `pb build` accepts |
| [How it works](docs/how-it-works.md) | capture, conversion, accuracy techniques, quality gates |
| [Architecture](docs/architecture.md) | code map for contributors |
| [Targeted update](docs/targeted-update.md) | design of `pb update`: change one part of a design in place (planned) |
| [Troubleshooting](docs/troubleshooting.md) | common problems and fixes |

## Limitations

Not reproduced automatically: CSS filters and backdrop blur, masks, 3D transforms, video frames,
canvas content and iframes (crop them from the reference screenshot with `pb assets file ... --crop`).
Penpot must have the font families the site uses (others are substituted and width-fitted).
penpot-agent is tested with self-hosted Penpot 2.18; it is an independent project, not affiliated
with Penpot or Kaleidos.

## FAQ

**How do I convert a website to a Penpot design?**
Install penpot-agent, connect Penpot's MCP server, then run `pb capture <url>` and
`pb rebuild --board "<name>"` — or ask Claude Code with the plugin installed. The result is a Penpot
board with editable layers, checked against the live page pixel by pixel.

**Is there an "HTML to Figma" equivalent for Penpot?**
Yes — this is one: it imports a rendered web page (HTML, CSS, fonts, SVG, images) into Penpot as
native layers, and also measures how close the import is.

**Does it work with design.penpot.app or only self-hosted Penpot?**
Both, as long as the MCP server is enabled (official service, self-hosted, or the local
`@penpot/mcp` server). See [docs/penpot-setup.md](docs/penpot-setup.md).

**Is it an MCP server?**
No — it is an MCP *client*: a CLI and Claude Code plugin that uses Penpot's official MCP server and
adds website capture, conversion, reliable bulk building and visual QA on top.

**Can I use it without Claude or any AI?**
Yes. `pb` is a normal command-line tool; the Claude Code plugin is optional.

## Contributing

Bug reports, fixes and new features are welcome — please read [CONTRIBUTING.md](CONTRIBUTING.md).
Every bug fix comes with a regression test, and the test page `tests/fixtures/tricky.html` collects
every web pattern that ever broke the pipeline. AI coding agents: see [AGENTS.md](AGENTS.md).

## License

[GPL-3.0-or-later](LICENSE) © Deepak and contributors.
