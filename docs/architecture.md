# Architecture

penpot-agent has three runtimes: **Python** (the CLI and all logic that can run locally),
**Node.js + Chrome** (website capture, SVG rasterizing) and **JavaScript inside the Penpot MCP
plugin** (a small runtime that creates and edits shapes).

```
               ┌──────────────── your machine ────────────────┐            ┌──── browser tab ────┐
  pb (Python) ─┤ capture ─► node node-cli.js capture ─► Chrome │            │ Penpot + MCP plugin │
               │ convert, imaging, quality, project state      │  HTTP/MCP  │   storage.pb =      │
               │ connection ──────────────────────────────────────► server ─┤   plugin-runtime.js │
               └───────────────────────────────────────────────┘            └─────────────────────┘
```

## Repository

```
.claude-plugin/        plugin.json + marketplace.json (Claude Code plugin and marketplace)
skills/                Claude Code skills: penpot-agent (workflow), setup, clone
src/pbridge/           Python package
  cli/                 `pb` command line: app.py (parser), support.py, commands/<topic>.py
  workflows.py         convert / build / compare / audit / qa steps shared by commands
  project/             .pbridge/ state (config, idmap, boxes, assets, history)
  connection/          MCP client, runtime injection + exec with chunking, exporter, notifier, URL discovery,
                       backend.py (optional access-token client for the Penpot backend API)
  assets/              image upload cache (URL / bytes / file, SVG rasterizing)
  capture/             runs `node-cli.js capture` behind the capture gate
  convert/             layout.json -> spec
    css/               pure parsers: colors, gradients, shadows/radius/clip, values
    nodes/             element -> shapes: boxes, images, svg, text, inputs, decorations
    tree.py            DOM subtree -> nested groups
    layout.py          --layout auto: verified Penpot flex layouts (simulator of Penpot's measured rules)
    sections.py        page -> section boards
    converter.py       facade wiring the parts together
  build/               spec -> Penpot: builder, plan (batch packing, section hashes), page_board,
                       snapshots, alignment (audit/autofix)
  imaging/             metrics, offsets, hotspots, visuals (overlay / montage)
  quality/             capture gate, render gate, thresholds
  library/             design tokens -> Penpot library
  timing.py            per-stage timings printed by multi-step commands (rebuild)
  bundles/             BUILT JavaScript (committed; generated from js/src)
js/                    TypeScript sources (npm)
  src/plugin/          in-plugin runtime `pb` -> bundles/plugin-runtime.js
  src/capture/         capture pipeline (main.ts, options.ts, steps/)
    page/              code evaluated inside the captured page -> bundles/capture-page.js
  src/rasterize/       SVG -> PNG
  src/node-cli.ts      Node entry point for capture + rasterize -> bundles/node-cli.js
  src/shared/          Chrome discovery, layout.json types
  scripts/             check-names.mjs (naming lint)
tests/                 unit tests + fixtures/tricky.html
docs/                  documentation
```

## Key mechanisms

- **Runtime injection** (`connection/bridge.py`). `plugin-runtime.js` is sent once through
  `execute_code` and stores itself as `storage.pb`. Its version is the sha1 of the bundle; every call
  checks it and re-injects after a plugin reload or an upgrade. Calls are wrapped so `pb`, `DATA`
  and `penpot` are in scope and exceptions come back as structured errors.
- **Chunking.** `DATA` above ~90 KB is sent in pieces (`pb.chunkPut`) and reassembled in the plugin.
- **Plugin waits.** A suspended tab is detected from the server's error text; pb notifies the user
  and polls until the plugin answers (`connection/mcp_client.py`).
- **Keyed builds** (`build/builder.py`). `.pbridge/idmap.json` maps spec keys to shape ids, so
  rebuilds replace, patches can target keys, and audits know which shape to move.
- **Incremental builds** (`build/plan.py`). Each section's content hash (subtree + font, parent
  board, origin, runtime version) is stored in `.pbridge/section_hashes.json`; a rebuild keeps
  sections whose hash is unchanged and whose shapes still exist. Batches are packed in order by
  shape count and request size. Measurements and rationale: [fast-build.md](fast-build.md).
- **Shape lookups.** `pb.byId` uses `page.getShapeById` (a map lookup); `penpotUtils.findShapeById`
  scans the whole document (~600 ms per id) and must not be used.
- **Formats.** Spec: `js/src/plugin/spec.ts` ([spec-format.md](spec-format.md)). Capture:
  `js/src/shared/layout-types.ts`. Both use short keys on purpose (request size, file size).

## Planned

- **Fast build v2**: no-op short-circuit, convert and per-section render caches, a keyed
  reconciler, a fix for the quadratic build cost, and exactly-once plugin calls.
  Plan: [fast-build-v2.md](fast-build-v2.md).
- **Targeted update** (`pb update`): replace one element's layers in place instead of a
  whole section. Design: [targeted-update.md](targeted-update.md).
- **Offline build** (spiked, not adopted): compile the spec into a `.penpot` file with
  `@penpot/library` and import it with the access token. Status: [fast-build.md](fast-build.md).

## Adding things

- **A command**: a `cmd_<name>` + `add_<name>` pair in `cli/commands/<topic>.py`, registered in
  that module's `PARSERS` and in `COMMAND_ORDER` (`cli/app.py`); document it in [commands.md](commands.md).
- **A converter rule**: a parser in `convert/css/` or a builder in `convert/nodes/`, with a unit test
  in `tests/test_convert.py` and, for real-browser behaviour, an element in `tests/fixtures/tricky.html`.
- **A plugin function**: a module in `js/src/plugin/`, exported from `index.ts` (the public `pb`
  API); rebuild and commit the bundles.
