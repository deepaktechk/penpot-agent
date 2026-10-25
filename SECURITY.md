# Security policy

## Supported versions

Security fixes go into the latest release. penpot-agent is young; please upgrade
(`uv tool upgrade penpot-agent` or `/plugin update penpot-agent`) before reporting.

## Reporting a vulnerability

Please **do not open a public issue**. Report privately through
[GitHub security advisories](https://github.com/deepaktechk/penpot-agent/security/advisories/new)
or by email to deepaktechk@gmail.com, with steps to reproduce and the impact you see.
You will get an answer within a week.

## What to keep in mind when using penpot-agent

- **Your MCP URL is a credential.** It contains your Penpot MCP key (`userToken=...`). penpot-agent
  never prints it (errors show `userToken=***`). Don't paste it into chats, issues or committed files;
  regenerate the key in Penpot if it leaks.
- **pb has write access to the open Penpot file.** Builds, patches and `pb eval`/`pb run` scripts
  change the design in the connected tab. Snapshot (`pb snapshot`) before large edits; review
  scripts you did not write before running them.
- **Website capture runs a real browser** against the URL you give it. Capture sites you trust; the
  page runs its JavaScript in headless Chrome on your machine.
