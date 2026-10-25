# Contributing to penpot-agent

Thanks for helping! Bug reports, website patterns that clone badly, fixes, docs and new features
are all welcome. By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting a bug

Open an [issue](https://github.com/deepaktechk/penpot-agent/issues/new/choose) with:
- the command you ran and its output (run it with `-v`; pb redacts your MCP key, but double-check),
- for clone problems: the URL (if public) and the montage from `.pbridge/diffs/`,
- `pb --version`, your Penpot version (hosted or self-hosted), Node.js version and OS.

Security problems: see [SECURITY.md](SECURITY.md) instead of a public issue.

## Development setup

Requirements: [uv](https://docs.astral.sh/uv/), Node.js ≥ 20, Chrome or Chromium. A Penpot with
the MCP server is only needed for the Penpot-side tests ([docs/penpot-setup.md](docs/penpot-setup.md)).

```bash
git clone https://github.com/deepaktechk/penpot-agent.git penpot-agent
cd penpot-agent
uv sync                   # virtual environment + pbridge in editable mode + pytest, ruff
npm --prefix js ci        # TypeScript toolchain (needed when you change js/src)
./pb doctor
```
`./pb` runs your working copy from anywhere (link it into a project folder: `ln -s /path/to/repo/pb pb`).
To try the Claude Code plugin from your checkout: `claude --plugin-dir .`.

Code map: [docs/architecture.md](docs/architecture.md).

## The rules

1. **Every bug fix starts with a test.** Reproduce the problem as an element in
   `tests/fixtures/tricky.html` (real browser behaviour) and/or a unit test in
   `tests/test_convert.py`, see it fail, then fix it. The fixture page collects every pattern that
   ever broke the pipeline, so a fixed bug never comes back.
2. **Accuracy is measured, not eyeballed.** For converter or builder changes, show the effect with
   `pb compare` / `pb qa` numbers (before → after) on a real page.
3. **Readable code.**
   - small single-purpose modules with a header docstring/comment
   - type hints / strict TypeScript
   - comments for non-obvious logic
   - **descriptive names**: no `a`, `e`, `p`, `r`, `s`, `el`, `cs`… — write `element`, `style`, `shape`.
     Allowed short names: `i`/`j`, `x`/`y`, `dx`/`dy`, `id`, `ok`, `_`. The checks below enforce this.
4. **Don't break stored formats.** The spec and capture JSON use short keys (`t`, `w`, `op`...) that
   existing projects have on disk; extend them compatibly and document new keys.
5. **No new runtime dependencies** without discussion (today: Python stdlib + Pillow; puppeteer-core
   bundled into the Node CLI).
6. Never commit or print MCP URLs/tokens.

## Checks

```bash
uv run ruff check src tests                                                      # lint
uv run python -m unittest tests.test_convert tests.test_discovery tests.test_naming tests.test_packaging   # fast, offline
./pb selftest                     # + end-to-end capture of tests/fixtures/tricky.html (Chrome + network)
./pb selftest --build             # + builds the fixture in Penpot on a scratch board (plugin connected)
npm --prefix js run check         # TypeScript: typecheck + naming lint + build
claude plugin validate .          # if you changed .claude-plugin/ or skills/
```
CI runs all of these except `--build` and the plugin validation.

## Changing TypeScript

The built JavaScript lives in `src/pbridge/bundles/` and **is committed**, so that
`uv tool install git+https://...` works without npm. After any change under `js/src/`:

```bash
npm --prefix js run check         # rebuilds src/pbridge/bundles/
git add src/pbridge/bundles
```
CI rebuilds the bundles and fails if the committed ones differ. Never edit bundles by hand.

## Pull requests

- One topic per PR; describe the problem, the fix and how you verified it (tests, numbers).
- Update the docs (`docs/`, `README.md`) and add a line to `CHANGELOG.md` under "Unreleased".
- Keep commits focused; any commit message style is fine.

## Releasing (maintainers)

1. Update the version in `pyproject.toml`, `src/pbridge/__init__.py`, `.claude-plugin/plugin.json`
   and `.claude-plugin/marketplace.json`; move "Unreleased" in `CHANGELOG.md` to the new version.
2. Tag and push: `git tag v0.2.0 && git push --tags`. The release workflow builds the wheel and
   sdist, attaches them to a GitHub release, and publishes to PyPI when configured.

## License

By contributing, you agree that your contributions are licensed under the
[GPL-3.0-or-later](LICENSE), like the rest of the project.
