---
name: setup
description: Install and check everything penpot-agent needs (uv, Node.js, Chrome, the pb CLI, the Penpot MCP server and plugin), step by step with the user.
argument-hint: "[project folder]"
---

# Set up penpot-agent

Goal: `pb doctor` reports `"problems": []` in the user's project folder ($ARGUMENTS, else the
current folder). Work through the steps in order, run the checks yourself, and ask the user only
for what needs them (installing software, actions in the Penpot web app). Never print the MCP URL:
it contains the user's token.

## 1. Local tools

Check: `uv --version`, `node --version` (needs ≥ 20), and a Chrome/Chromium binary.
- uv missing → https://docs.astral.sh/uv/getting-started/installation/ (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node missing or too old → https://nodejs.org (or nvm / the OS package manager)
- Chrome missing → install Google Chrome or Chromium, or set `CHROME_PATH` to the binary

## 2. The `pb` CLI

Prefer a real install so `pb` works in any terminal:
```
uv tool install git+https://github.com/deepaktechk/penpot-agent
pb --version
```
Without installing, the plugin's own copy works too: `"${CLAUDE_PLUGIN_ROOT}/pb" --version`.

## 3. Penpot MCP server

Ask which Penpot the user works with, then follow `${CLAUDE_PLUGIN_ROOT}/docs/penpot-setup.md`:
- **design.penpot.app or a Penpot with MCP enabled** → Your account → Integrations → MCP Server →
  enable, generate a key, copy the URL `https://<domain>/mcp/stream?userToken=...`.
- **Local MCP server** → `npx -y @penpot/mcp@stable`, endpoint `http://localhost:4401/mcp`, plugin
  loaded from `http://localhost:4400/manifest.json`.
Register it in Claude Code under a name containing "penpot" (pb finds it there automatically).
The user runs this themselves so the token never passes through the conversation:
```
claude mcp add --transport http --scope user penpot "<the URL>"
```
Alternatively `export PENPOT_MCP_URL="<the URL>"` in their shell profile.

## 4. Connect the plugin

The user opens a design file in Penpot and starts the MCP plugin (File → MCP Server → Connect,
or Plugins → the MCP plugin → Connect). The tab must stay open and should stay visible; in Chrome,
add the Penpot site to Settings → Performance → "Always keep these sites active".

## 5. Verify

```
mkdir -p <project> && cd <project> && pb init
pb doctor
```
Read the `problems` list and fix each one. When it is empty, say so, and suggest a first run:
`/penpot-agent:clone https://example.com`.
