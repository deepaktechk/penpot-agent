# Fast build — plan and checklist

> **Status: plugin route done (2026-10-26); offline route spiked, not adopted.** Tick items as they land and keep the numbers current.
> Goal: a clone like clockify.me builds in **~10–45 s instead of ~4–6 min**, with the same accuracy
> (`pb qa` diff % must not get worse) and fewer things that can stall.

## 1. Measurements (2026-10-25, clockify.me, local Penpot + MCP)

| What | Result |
|---|---|
| One empty `execute_code` call | 0.37 s |
| 8 calls sent at once | 1.63 s wall — the plugin is **one JS thread**; calls queue (~2× from overlapping latency, not 8×) |
| 200 rectangles in one call | 1.8 s (~9 ms / shape) |
| 100 texts in one call | 1.1 s (~10 ms / text) |
| 10 largest SVG imports (16–34 KB) | 12–65 ms each — not a bottleneck |
| `uploadMediaUrl`, one after another | 0.73 s each |
| `uploadMediaUrl` × 5 with `Promise.all` in one call | 0.85 s total |
| `rasterize_svg` (new Chrome per SVG) | 1.7–1.9 s each |
| Clockify spec | 12 sections, 712 nodes (291 text, 170 group, 93 svg, 83 rect, 44 image, 31 board), 80 images (**71 http SVG**, 9 raster), 602 KB spec, 470 KB inline SVG |

**Conclusion: drawing is not the bottleneck** (712 nodes ≈ 7–10 s of plugin time). The time goes to:

| Cost | Why | Estimate |
|---|---|---|
| 71 SVG images | per image: `uploadUrl` attempt that always fails for SVG → a fresh Chrome to rasterize (1.8 s) → separate upload call | **~3 s × 71 ≈ 3.5 min** |
| Post-passes per 60-node batch | `_post` runs after **every** batch: up to 4 `verifyRanges` + 2 `fitTexts` calls with `time.sleep` in between | ~5–8 s per batch |
| Bookkeeping | one call per image registration (`_ensure_registered`), per removed section, per data chunk | ~0.4 s each |

## 2. Research — how comparable tools do it

- **`@penpot/library`** (official, MPL-2.0, v1.2.0, Oct 2026): builds a whole `.penpot` file in memory
  in Node and streams it out. Functions: `createBuildContext`, `addFile/addPage/addBoard/addRect/
  addCircle/addPath/addText/addGroup/addBool/addComponent/addFileMedia/addLibraryColor/
  addLibraryTypography`, `close*`, `exportStream`. No raw-SVG import.
  <https://www.npmjs.com/package/@penpot/library>
- **Penpot's Figma importer** (`penpot-exporter-figma-plugin`) depends on `@penpot/library` 1.2.0:
  builds the file offline, one `.penpot` output, streaming export, de-duplicated images.
  <https://github.com/vchapellu/penpot-exporter-figma-plugin>
- **Backend `import-binfile`**: uploads a `.penpot` file with an access token
  (`Authorization: Token …`); params `name`, `projectId`, `file` (multipart) or `uploadId`; optional
  `fileId` = replace that file in place (binfile-v3, one file). Since Penpot 2.12 the path is
  `/api/main/methods/<name>` (old `/api/rpc/command/<name>` kept).
  <https://apis.io/apis/penpot/penpot-import-binfile-api/> ·
  <https://forum.cloudron.io/topic/9406/penpot-package-updates/46>
- **Website → Figma tools** (Builder.io html-to-figma, tofig, html.to.design): capture computed
  styles + geometry to JSON, then rebuild in one bulk import; html.to.design also creates
  colour/font styles. pb's capture already matches; only the drawing step differs.
  <https://www.builder.io/blog/html-to-design> · <https://github.com/aca-so/tofig> ·
  <https://html.to.design/docs/what-is-html-to-design>

**Pattern:** fast tools compile the whole design offline and upload it once.

## 3. Target architecture

```
 CAPTURE (as now)        COMPILE (local, parallel)                DELIVER (1–3 calls)        VERIFY (plugin, short)
 Chrome → layout.json ─► spec ─► asset graph ──► asset worker pool ─► .penpot ─► import-binfile ─► text fitting,
                              (content-hashed)   (1 Chrome, N tabs;                (access token)    range checks,
                         spec ─► section hashes   downloads in threads)                              export + QA
                              ─► @penpot/library build context
```

| Problem | Technique |
|---|---|
| Same image used many times | content-addressed store (sha1 of bytes → one asset) |
| What changed since last build | Merkle-style hash per section (hash of children's hashes) → rebuild only changed sections |
| Order of local work | task dependency graph + priority queue, slowest job first (LPT) |
| Stages running together | producer-consumer pipeline with bounded queues (backpressure) |
| Calls that still go through the plugin | ordered greedy packing up to ~90 KB and ~60 s estimated work per call, layer order kept |
| Post-build checks | one pass over the whole page, no sleeps between batches |

Expected for Clockify: plugin route with fixes **~30–45 s**; offline compile route **~10–15 s**.

## 4. Checklist

Every item that changes behaviour follows AGENTS.md: fixture/test first → fix → `./pb selftest`
(`--build` for Penpot-side) → `uv run ruff check src tests` → naming lint → rebuilt bundles committed
when `js/src` changed.

### Phase 0 — prerequisites
- [x] User creates a Penpot access token (Your account → Access tokens) and sets `PENPOT_ACCESS_TOKEN` in the shell (never pasted into chat, logs or commits — rule 4)
- [x] Confirm Penpot URL / version and which RPC path works — 2026-10-26: design.penpot.app; `/api/main/methods/get-profile` and `get-teams` → 200 with the token; old `/api/rpc/command/` → **403** (use `/api/main/methods/` only). Requests need a non-urllib User-Agent (Cloudflare)
- [x] Token handling in pbridge: `connection/backend.py` (`BackendClient`), token from env `PENPOT_ACCESS_TOKEN` only (never project files), base URL from `PENPOT_URL` / config `penpot_url` / design.penpot.app, redacted by `redact()`; `pb doctor` reports `backend` (optional). Tests in `tests/test_discovery.py`
- [x] Record the baseline (2026-10-26, current code, `pb -c rebuild … --fix --hotspots 6 --montage 6`): **173 s total**
  - convert + 32 image uploads ≈ 18 s · drawing 12 sections **55 s** (Footer alone 22 s for 161 shapes ≈ 140 ms/shape vs ~10 ms raw) · export ≈ 20 s
  - audit + autofix (110 issues, 80 moved) ≈ 55 s · second export ≈ 20 s · QA + montage ≈ 2 s
  - QA: page **1.057 %**, gate **FAIL** — `sec04` "Read more customer stories" 3.73 %; next worst sec09 1.52 %, sec08 1.42 %
  - accuracy issues seen: centred multi-line paragraphs shifted a few px (hero, features intro); hidden nav product-switcher logos (Pumble/Clockify/Plaky) built although invisible on the site
  - the 4–6 min estimate in §1 was too pessimistic: most SVG images became vectors, only 32 uploads
- [x] Per-stage timings printed by `pb rebuild` itself (`pbridge/timing.py`; stdout/stderr line-buffered in `cli/app.py`)

### Phase 1 — spike: offline compile + import (go / no-go)
- [x] `@penpot/library` 1.2.0 tried in a scratch project (not added to `js/`)
- [x] Node script: board, rect, path, two-style HumanSans text → `.penpot` in **171 ms** (shapes take Penpot's internal data model: text needs the root/paragraph-set/paragraph tree and the exact `fontId`, e.g. `custom-…` for uploaded fonts)
- [x] Import with `import-binfile` (multipart, field `project-id` in kebab-case; JSON body fields are camelCase) into Drafts: HTTP 200 in **0.3 s**, file "pb spike – offline build"
- [ ] Measure: compile time, upload time, time until the board is usable
- [ ] Export the imported board and run `pb qa` against the capture; compare page % and worst sections with the Phase 0 baseline
- [ ] Same comparison on `tests/fixtures/tricky.html`
- [ ] Check text: does `addText` text lay out like plugin-made text once Penpot opens the file (line breaks, widths, ranges, letter-spacing)?
- [ ] Check what doesn't map: inline SVG (→ `addPath` for simple, raster for complex), flex/grid layout, components, image fills with cover/contain
- [x] **Decision: not adopted for now.** (1) Imported text has no `positionData` until the file is opened in the browser, so its layout cannot be verified headlessly; (2) the import creates a separate file, and the post-passes, export, autofix and QA need the MCP plugin connected to *that* file (the user would have to open it and reconnect each time). Revisit if a headless export of imported files or a cross-file copy becomes possible.

### Phase 2 — fast assets (helps both routes)
- [ ] Unit test for the content-addressed store (behaviour already existed in `from_bytes`; no test yet)
- [x] ~~Skip `uploadUrl` for SVG URLs~~ — measured: Penpot's server fetches these SVG URLs fine (all 23 succeeded), so no change
- [x] ~~One long-lived Chrome for rasterizing~~ — not needed: on Clockify no image needed local rasterizing (Penpot's server fetched all 32)
- [x] SVG downloads for the converter in a thread pool (`svg_source.prefetch_svgs`, 8 threads): convert **16 s → 3.5 s**, spec byte-identical
- [x] ~~Priority queue for assets~~ — not needed: the whole cold upload is now 3.8 s
- [x] Content-addressed store: already in `AssetStore.from_bytes` (sha1 of bytes)
- [x] Uploads: public URLs `UPLOAD_BATCH`=12 at a time in one plugin call (`pb.uploadUrls`, `Promise.allSettled`); only failures take the one-by-one bytes path. Backend-token uploads not needed after this
- [x] Public URLs (raster and SVG): one call per batch with `Promise.allSettled(uploadMediaUrl…)`
- [x] Register all image descriptors in one call (`many_urls` no longer registers per image; the builder calls `sync()` once)
- [x] Measured cold upload of Clockify's 32 images: **21.1 s / 32 calls → 3.8 s / 5 calls**

### Phase 3A — offline compile route (if the spike passes)
- [ ] `pb rebuild --engine file` (name TBD): spec → `.penpot` → `import-binfile`
- [ ] One Penpot file per cloned site (matches "one project per site"); never used to edit an existing design
- [ ] `idmap.json` / `boxes.json` filled from the compiled ids, so `pb patch`, `audit`, `compare` keep working
- [ ] Short plugin pass after import: `fitTexts` / `verifyRanges` once over the page, then export + QA
- [ ] Docs: commands.md, architecture.md, skills/clone/SKILL.md, skills/penpot-agent/SKILL.md

### Phase 3B — packed plugin route (fallback, and for targeted edits)
- [x] Replace the fixed `BATCH_NODES = 60` with ordered greedy packing (`build/plan.py`: ≤ 250 shapes and ≤ 400 KB per call); big groups' children are packed too (they were built one call per child)
- [x] Run `verifyRanges` / `fitTexts` once per build over every text (`buildMany` returns the work items); no sleeps between batches
- [x] Remove all stale/old section shapes in one call (`pb.removeMany`)
- [x] ~~Stage overlap~~ — not worth it: assets take ~4 s cold, 0 s cached, and the plugin runs one call at a time anyway
- [x] Keep layer order: `pack_batches` keeps sibling order and calls run in sequence
- [x] Measured build stage: 55 s → 33 s. The floor is Penpot itself: every plugin property change gets slower as the document grows (~9 ms per shape on an empty file, ~45 ms at ~1400 shapes; an undo block does not help)

### Phase 4 — incremental and resumable
- [x] Content hash per section (`plan.section_hash`: subtree + font, parent board, origin, runtime version) in `.pbridge/section_hashes.json`
- [x] `pb rebuild` skips sections whose hash didn't change and whose shapes still exist (`--all` to force)
- [x] Resume without a flag: idmap/boxes/hashes are saved after every section, so rerunning `pb rebuild` after a crash keeps the finished sections
- [x] Retries only for idempotent operations (unchanged; `removeMany` is marked idempotent); tab asleep → wait, don't loop
- [ ] Reuse for the planned `pb update` ([targeted-update.md](targeted-update.md))

### Phase 5 — token-friendly output (for agents driving pb)
- [x] One line per stage on stderr (`[rebuild] build 32.9s`) and a `seconds` summary in the final JSON
- [ ] Full log to a file; console shows only `✗` / `!` / gate verdict
- [ ] QA summary JSON: page %, worst 5 sections, errors — nothing else by default
- [ ] Smaller montages, worst regions only
- [ ] Skills updated so agents read the summary, not `layout.json` or the spec

### Phase 6 — verify and ship
- [x] Clockify: **173 s → 84 s** full rebuild (`--all`), **26 s** unchanged rebuild; page **1.057 %** before and after (identical). Gate still fails on `sec04` 3.73 % (pre-existing accuracy issue, not speed)
- [ ] facebook_com clone: same check
- [x] `./pb selftest --build` passes (127 tests; the Penpot build test now converts with Penpot's font list like `pb convert`)
- [x] Fast offline tests (list in AGENTS.md, now incl. `test_build_plan`, `test_svg_source`, `test_image_analysis`)
- [x] `npm --prefix js run check`; bundles rebuilt (not committed yet)
- [x] CHANGELOG.md, docs/commands.md, AGENTS.md quirks updated (README unchanged)

## 5. Results (2026-10-26, clockify.me, `pb -c rebuild --font HumanSans --fix --hotspots 6 --montage 6`)

| Stage | Baseline | Now (`--all`) | Now (nothing changed) |
|---|---|---|---|
| convert | ~16 s | 3.5 s | 3.5 s |
| build | ~55 s | 32.9 s | 2.4 s |
| export (settled) | ~20 s | ~25 s | 16.9 s |
| audit + autofix | ~55 s | 5.2 s | 1.2 s |
| export after autofix | ~20 s | ~15 s (one export, no settling) | — (nothing moved) |
| compare + QA | ~2 s | 1.9 s | 1.9 s |
| **total** | **173 s** | **84 s** | **26 s** |
| page diff | 1.057 % | 1.057 % | 1.057 % |

Biggest single win: `penpotUtils.findShapeById` → `page.getShapeById` (15 s → 5 ms for 25 lookups).
Remaining floor: Penpot's per-change cost in the plugin (~45 ms per shape on a large page) and exports
(8–14 s each for a 1920×10564 board).

## 6. Risks and open questions

- `@penpot/library` text may not lay out identically to plugin-made text → measured in Phase 1; accuracy decides.
- No raw-SVG import in the library → simple SVGs as paths, complex ones rasterized (as today).
- `import-binfile` creates a new file (or replaces a whole file) → only for fresh clones.
- The backend RPC is not a stable public API; endpoint paths changed in 2.12 → pin and check the Penpot version in `pb doctor`.
- The plugin is single-threaded: parallel `execute_code` calls cannot speed up drawing; only fewer, fuller calls can.
