# Claude Code plugin

This repository is also a [Claude Code](https://claude.com/claude-code) plugin and plugin
marketplace. The plugin teaches Claude the whole penpot-agent workflow and ships the `pb` CLI.

## Install

```
/plugin install penpot-agent --marketplace deepaktechk/penpot-agent
```
On older Claude Code versions, add the marketplace first:
```
/plugin marketplace add deepaktechk/penpot-agent
/plugin install penpot-agent@penpot-agent
```
Update with `/plugin update penpot-agent`; remove with `/plugin uninstall penpot-agent`.

## What you get

| Component | Use |
|---|---|
| skill `penpot-agent` | loaded automatically when you ask for Penpot work: cloning, comparing, inspecting, patching, exporting |
| `/penpot-agent:setup [folder]` | checks uv, Node.js, Chrome, `pb`, the Penpot MCP server and plugin, and walks you through anything missing |
| `/penpot-agent:clone <url> [board] [--font F]` | captures the page, builds it, iterates until the quality gate passes, reports the result |

Claude runs `pb` from your PATH when installed (`uv tool install ...`, recommended) and otherwise
the copy inside the plugin (`${CLAUDE_PLUGIN_ROOT}/pb`, needs `uv`).

## First run

1. `/penpot-agent:setup` — fix everything it reports. Register the Penpot MCP server yourself
   (`claude mcp add ...`, see [penpot-setup.md](penpot-setup.md)) so your key never appears in the chat.
2. Open your Penpot file and connect the MCP plugin; keep the tab visible.
3. `/penpot-agent:clone https://example.com "Example" --font Inter`

## Example prompts

- "Clone https://example.com/pricing into Penpot next to my other boards, font Inter."
- "Compare the 'Example – Landing Page' board with the live site and fix the hero section."
- "Rename every layer called 'Rectangle 12' in the footer to something meaningful."
- "Export the landing page board and tell me which sections differ most from the site."
- "Extract the site's colours and text styles into my Penpot library."

## Tips

- Builds and exports take minutes; let Claude run them with long timeouts.
- If Claude says the plugin is asleep, click the Penpot tab; `pb` resumes by itself.
- The Penpot MCP tools (`mcp__penpot__*`) can stay enabled; the skill tells Claude to use `pb` for
  anything large and raw tool calls only for quick probes.

## Developing the plugin

From a clone of this repository: `claude --plugin-dir .` loads the skills from `skills/`.
Validate changes with `claude plugin validate .`.
