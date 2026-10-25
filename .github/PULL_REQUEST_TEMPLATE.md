## What and why

<!-- The problem this solves and how. Link the issue: "Fixes #123". -->

## How it was verified

<!-- Tests added/updated; for visual changes, `pb compare` / `pb qa` numbers before -> after. -->

## Checklist

- [ ] Bug fix: a regression test or a `tests/fixtures/tricky.html` element reproduces the bug
- [ ] `uv run ruff check src tests` and the unit tests pass; `./pb selftest` passes
- [ ] `js/src` changed: `npm --prefix js run check` passes and `src/pbridge/bundles/` is committed
- [ ] Docs and `CHANGELOG.md` ("Unreleased") updated
- [ ] No MCP URLs / tokens in code, tests or screenshots
