# CLAUDE.md

@AGENTS.md

## Claude Code specifics

- This repository is itself the penpot-agent plugin. To use its skills while developing, start
  Claude Code with `claude --plugin-dir .` (skills: `skills/penpot-agent`, `skills/setup`, `skills/clone`).
- Penpot MCP tools (`mcp__penpot__*`) may be available, but drive Penpot through `./pb`
  (it handles chunking, the runtime, throttling and retries). Raw `execute_code` only for quick probes.
- Rebuilds take 5–10 min: run them with a long Bash timeout and redirect output to a file, then grep
  for `[render]`, `✗`, `  !`, `ERROR`.
- When the Penpot plugin is asleep, ask the user to click the Penpot tab; don't retry in a loop.
- Read montage images (`.pbridge/diffs/`) to check results visually, but trust the numbers.
- Personal notes (machine, local projects) belong in `CLAUDE.local.md`, which is git-ignored.
