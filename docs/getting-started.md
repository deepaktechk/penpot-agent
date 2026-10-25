# Getting started

This guide takes you from nothing to a website cloned into Penpot, with a quality report.

## 1. Install the requirements

| Tool | Why | Install |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | installs and runs `pb` (Python ≥ 3.10 is fetched automatically) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Node.js](https://nodejs.org) ≥ 20 | runs the headless-Chrome website capture | nodejs.org, nvm, or your package manager |
| Google Chrome or Chromium | renders the page being cloned | found automatically, or set `CHROME_PATH` |
| Penpot with the MCP server | where the design is built | [penpot-setup.md](penpot-setup.md) |

## 2. Install penpot-agent

```bash
uv tool install git+https://github.com/deepaktechk/penpot-agent
pb --version
```
To update later: `uv tool upgrade penpot-agent`. Prefer working from Claude Code? Install the
plugin instead (or as well): [claude-code-plugin.md](claude-code-plugin.md).

## 3. Connect Penpot

Follow [penpot-setup.md](penpot-setup.md). In short: enable the MCP server in Penpot, give `pb`
the MCP URL (register it in Claude Code under a name containing "penpot", or
`export PENPOT_MCP_URL=...`), open your design file and connect the MCP plugin. Keep that browser
tab visible while `pb` works.

## 4. Create a project folder

Every clone lives in a folder with a `.pbridge/` state directory (captures, specs, renders,
upload cache, quality history):

```bash
mkdir example && cd example
pb init
pb doctor
```
`pb doctor` prints a JSON report. `"problems": []` means everything is ready; otherwise each
problem says what to do.

## 5. Capture the website

```bash
pb fonts Inter                     # is the site's font available in Penpot?
pb capture https://example.com --name example --fonts "Inter"
```
The capture loads the page like a visitor (warm-up visit for web fonts, scrolling for lazy content,
waiting until animations settle), hides cookie banners and chat widgets, and saves
`layout.json` + `shot.png` in `.pbridge/captures/example/`.

It is judged by the **capture gate**: if text was painted with a fallback font, the page never
became still, or images failed, the capture is retried and never becomes the reference. Useful options:
`--width 1440`, `--hide ".promo-bar"`, `--click "#accept-cookies"`, `--wait 3000`.

## 6. Build it in Penpot

```bash
pb rebuild --board "Example – Landing Page" --font Inter --fix --hotspots 6 --montage 6
```
This converts the capture to a design spec, builds it section by section into the board (created
if needed; `--after '*'` places it right of your other boards), exports it, nudges misplaced
elements (`--fix`), compares it with the reference and runs the **render gate**. A full landing
page takes a few minutes.

## 7. Read the results

The last JSON line summarises the gate:

```json
{"ok": true, "page": {"mad": 1.0, "pct": 0.885}, "worst_sections": [["sec10", "Pricing", 1.796], ...],
 "errors": [], "warnings": ["section sec10 'Pricing' differs 1.796%"]}
```
- `pct` — % of pixels that differ noticeably from the live site (lower is better; < 1 % is very close)
- a section above 3 % is an error, above 1.6 % a warning; an image that does not match is an error
- `.pbridge/diffs/montage-*.png` — the worst areas: reference on top, red/cyan overlay below
  (red = only on the site, cyan = only in Penpot)

## 8. Iterate

```bash
pb compare --render latest --region 0,1200,1920,600 --hotspots 4 --montage 4   # zoom in
pb rebuild --only sec03,sec04 --font Inter                                      # rebuild some sections
pb qa                                                                           # gate only
```
See [commands.md](commands.md) for everything else (inspect, patch, snapshots, export, tokens).
