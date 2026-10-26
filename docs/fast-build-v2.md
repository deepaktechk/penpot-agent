# Fast build v2 — architecture plan

> **Status: Phase 0 measured, Phase 1 done, staging built (2026-10-26); see §7 for results.** Follows [fast-build.md](fast-build.md) (173 s → 84 s). Tick items
> as they land and replace estimates with measurements. Every phase starts with a measurement; an
> idea that does not beat its estimate is dropped and written down here (as fast-build.md does).

## 1. Where the time goes now (clockify.me, 1426 shapes, `pb -c rebuild --fix`)

| Stage | Full (`--all`) | Nothing changed | Cost model |
|---|---|---|---|
| convert | 3.5 s | 3.5 s | redone every run although `layout.json` did not change |
| build | 32.9 s | 2.4 s | Σ over shapes of *k* changes × cost(n); cost grows with the document (9 → 45 ms/shape) ⇒ **O(k·N²)** |
| export (settled) | ~25 s | 16.9 s | whole 1920×10564 board, ≥ 2 exports to prove fonts/images loaded |
| audit + autofix | 5.2 s | 1.2 s | fine |
| export after autofix | ~15 s | — | whole board again, although only moved elements changed |
| compare + QA | 1.9 s | 1.9 s | fine |
| **total** | **84 s** | **26 s** | |

So **exports are ~48 % of a full run and ~65 % of a no-op run**, and the build is quadratic.
Nothing in the no-op run is needed: the spec and the Penpot file are both unchanged.

Plugin facts this plan relies on (checked on the live plugin, 2026-10-26): `penpot.currentFile.revn`
(revision number, changes on every document update), `file.setPluginData` (persists in the file,
survives plugin reloads), `penpot.library.availableLibraries` / `connectLibrary`, `penpot.viewport`
(`center`, `zoom`), `penpot.generateMarkup`, `penpot.createPage`, `shape.clone()`.

## 2. Targets

| Scenario | Now | Tier A (plugin route) | Tier B (+ library bridge) |
|---|---|---|---|
| full rebuild | 84 s | ~35 s | ~15–20 s |
| one section changed | ~30 s | ~8 s | ~6 s |
| nothing changed | 26 s | **~1–3 s** | ~1–3 s |
| page diff % | 1.057 % | must not get worse | must not get worse |

## 3. Architecture

```
            ┌─────────────── content-addressed caches (.pbridge/cache/) ───────────────┐
            │ convert: H(layout, converter src, options, fonts) → spec                   │
            │ render:  H(section subtree, context, file revn of last build) → section.png│
            └──────────────────────────────────────────────────────────────────────────────┘
capture ─► convert ─► Merkle tree ─► diff vs last build ─► edit script ─► scheduler ─► plugin
(cached)   (cached)  (hash per node)  (keyed, by `src`)    create/update   cost model,   (journal,
                                                            remove/move     batches       op ids)
                                                                                  │
                   QA ◄─ stitch ◄─ export dirty sections only (parallel if the server allows) ◄┘
```

### 3.1 Merkle tree + no-op short-circuit (DSA: hash trees, memoization)
- Node hash = H(own properties, children's hashes); a section hash already exists
  (`build/plan.py:section_hash`), extend it bottom-up so any subtree can be compared in O(1).
- `.pbridge/last_run.json` stores: root hash, file `revn` right after the build, render path, QA
  summary. If the new root hash and the current `revn` equal the stored ones, nothing in Penpot
  or in the spec changed ⇒ print the stored verdict and stop. Any manual edit bumps `revn`, so
  the cache can never hide a change.

### 3.2 Convert cache
- Key = sha1(layout.json bytes, sha of `src/pbridge/convert/**`, convert options, Penpot font list).
- The font list comes from a plugin call (0.4 s); cache it per file id for the session/day.
- Later: convert per section in a process pool (the converter is pure); only needed if a site
  is much bigger than Clockify.

### 3.3 Keyed reconciler instead of section replace (DSA: keyed tree diff, LIS)
- Generalises [targeted-update.md](targeted-update.md): match old and new nodes by stable `src`
  (capture element path `dp`), not by positional key.
- Equal hash ⇒ keep the subtree. Same `src`, different own properties ⇒ **update** in place
  (set only the changed properties). Missing ⇒ **remove**. New ⇒ **create**.
- Sibling order: keep the longest increasing subsequence of old indices still, and move only
  the others (`setParentIndex`). This is how Vue and Inferno do keyed diffs, and it gives the
  fewest moves.
- Plugin cost becomes proportional to the change, not to the section size. It also keeps manual
  edits on untouched shapes.

### 3.4 Fix the O(N²) build (measure first, then pick)
The per-change cost grows with *something* (page size, board size, viewport rendering, or the
board thumbnail being re-rendered). Each cause has a different fix:

| Hypothesis | Experiment (`pb bench build`, on a scratch page it creates and deletes) | Fix if confirmed | Expected |
|---|---|---|---|
| cost ∝ size of the **board** being edited (thumbnail / layout recompute) | 150 rects into (a) a 1400-shape board, (b) a new top-level board on the same page | build each section as a top-level **staging board**, then move it into the page board with one `appendChild` + `setParentIndex` | 33 s → ~12 s |
| cost ∝ shapes **rendered** in the viewport | (a) viewport on the board, (b) `viewport.center` parked over empty canvas, (c) page board `hidden` while building | park the viewport / hide during the build, restore after | similar |
| cost ∝ **page** size | (a) the 1400-shape page, (b) a fresh empty page | build on a scratch page… only if a cross-page move exists (it does not today) | n/a |
| SVG renderer cost | repeat (a) with the WebGL renderer preference (Penpot 2.16+, beta) | document it as a setting in `pb doctor` | unknown |

Independent of the cause, cut *k* (changes per shape):
- Do not set properties that already have their default value (e.g. `fills = []` on a new
  rectangle, `opacity = 1`, `clipContent = false`); every setter is a separate change.
- Spike: a run of consecutive non-text leaves (rect / ellipse / path without shadows) packed into
  one `createShapeFromSvg` call creates many shapes with one change. Accept only if names, radii,
  strokes and QA % are unchanged.

### 3.5 Section-level render cache + incremental export
- Export **section boards**, not the page board, and stitch them (the stitch code exists:
  `connection/exporter.py:export_stitched`). Unchanged sections reuse the PNG cached under their hash.
- Settling per section: a fresh export that equals the cached render for the same hash is
  settled after one export. Only new or changed sections need the second export.
- After autofix, re-export only the sections that contain moved shapes.
- Measure whether `export_shape` calls run in parallel on the server (send 4 at once and compare
  the wall time with 4 sequential calls). If they do, export dirty sections through a bounded pool.
- Guard: `pb qa --verify-cache` exports the whole board and asserts the stitched render matches
  it pixel for pixel. It runs in `./pb selftest --build` so the cache can never drift unnoticed.
- Spike (later): `penpot.generateMarkup` + `generateFontFaces`, rendered by our own Chrome
  (1 browser, N tabs). This would remove the server export entirely, but only if it renders the
  same pixels as Penpot's exporter (same QA %).

### 3.6 Scheduler: adaptive batch size (cost model, not a fixed 250)
- Keep an EWMA of measured ms per shape for each node type (`buildMany` already returns `msByType`).
  Pack batches to an estimated **30 s budget** per call, well below the ~120 s task kill.
  The packing stays ordered and greedy (`plan.pack_batches`), so layer order is kept.
- If a call comes close to the budget, shrink the next batch (AIMD, as TCP does).

### 3.7 Tier B — library bridge (offline compile without a second open file)
The offline route was rejected because the imported file is a different file and its text has
no layout until it is opened. Sharing it as a **library** may avoid both problems:
1. Compile each section as a main component with `@penpot/library` (171 ms for the spike file).
2. `import-binfile` it with the access token (0.3 s), and mark it shared.
3. In the working file: `penpot.library.connectLibrary(id)`, then for each section
   `component.instance()` → `detach()` → move it into the page board. That is one change per section.
4. The text is laid out by the browser in the open working file, so `fitTexts` / `verifyRanges`
   and the QA work as they do today.

Go / no-go: page % and worst sections are no worse than Tier A on Clockify and `tricky.html`;
detached instances keep names, plugin data (`pb` tag) and image fills; the idmap can be rebuilt by
walking the detached tree (match by the `pb` tag).

### 3.8 Robustness
- **Idempotency keys (exactly-once for every call).** Each mutating batch carries an op id. The
  plugin records the last applied ids in `file.setPluginData("pb:ops", …)`, which survives plugin
  reloads. A retry of an op that was already applied returns its stored result instead of
  running again. Then every call can be retried, not only the ones marked `idempotent`.
- **Write-ahead journal** `.pbridge/journal.jsonl` (op id, section, status) instead of
  re-deriving progress from idmap/hashes; resume replays from the last committed op.
- **Read-back check.** After each section, count its descendants in the plugin against the spec.
  Community reports describe calls that returned success and then rolled back silently. Today
  that would leave a quietly incomplete board.
- **Deadline per call** from the cost model (3.6), and retries with exponential backoff and jitter.
  A sleeping tab still means "notify and wait", never a retry loop.

### 3.9 Token-friendly output (for agents running pb)
- Console: one line per stage plus the gate verdict (≤ 10 lines). The full log goes to
  `.pbridge/logs/<run>.log`, and the summary to `.pbridge/last_run.json`.
- QA summary: page %, worst 5 sections, errors. Nothing else unless asked.
- Montage only when the gate fails, only the worst sections, capped at ~1500 px wide (image
  tokens grow with pixel area).
- Skills: read `last_run.json` and `pb inspect --key …`, never `layout.json` or the spec.

## 4. How comparable tools do it

- **html.to.design, Builder.io html-to-figma, tofig**: capture computed styles to JSON, then one
  bulk import. pb already works this way; the difference is the per-change cost of the target editor.
- **Penpot's Figma exporter** builds the whole `.penpot` offline with `@penpot/library` and imports
  it once. This is the basis of Tier B. <https://github.com/vchapellu/penpot-exporter-figma-plugin>
- **Figma plugin practice**: batch creation, load each font once, no read-after-write inside loops
  (each read forces a layout). <https://forum.figma.com/ask-the-community-7/running-actions-in-parallel-in-figma-api-363>
- **Penpot community**: large pages slow down with shape count. The suggested remedies are
  splitting work and the newer renderer, and calls reported as successful were sometimes
  rolled back silently (hence the read-back check).
  <https://community.penpot.app/t/mcp-api-issue-list/10700> ·
  <https://community.penpot.app/t/single-page-controls-have-more-operations-and-are-slow/10033>
- **React / Vue keyed reconciliation, Merkle trees (git, Bazel action cache)**: diff by stable
  key, skip equal hashes, cache outputs by input hash (3.1, 3.3, 3.5).

## 5. Checklist (in order of win per effort)

Every behaviour change follows AGENTS.md: fixture/test first → fix → `./pb selftest`
(`--build` for Penpot-side) → ruff → naming lint → rebuilt bundles committed.

### Phase 0 — measure
- [x] `pb bench build` (scratch page, deleted afterwards): ms/shape for the experiments in 3.4 (§7)
- [x] `pb bench export`: section exports, 4 in parallel vs sequential; full board vs stitched (§7)
- [ ] Count changes per shape type (instrument the setters in `common.ts`) to find avoidable ones: **next**

### Phase 1 — skip work that is already done (no-op 26 s → ~2 s)
- [x] Rebuild short-circuit on spec + reference + options + `<file id>@<revn>` (`run_cache.py`, `.pbridge/cache/`), tests in `test_run_cache.py`
- [x] Convert cache (3.2)
- [x] ~~Section render cache + stitched export~~: dropped after measuring (§7)
- [x] ~~Re-export only sections with moved shapes after autofix~~: same reason (one whole export is cheaper)

### Phase 2 — cheaper builds (full build 33 s → ~12 s)
- [x] Staging on temporary pages + component transfer (`js/src/plugin/staging.ts`), gated by the cost model; `--no-staging`
- [x] Section layer order restored after every build (`pb.orderChildren`, LIS: fewest moves)
- [ ] Skip default-valued setters / fewer changes per node; test with `tricky.html` that the output is unchanged
- [ ] Adaptive batch budget (3.6)
- [ ] `pb selftest --build` with staging on (needs the plugin connected)

### Phase 3 — robustness
- [ ] Op ids + plugin-side applied-op record, journal, read-back counts (3.8)

### Phase 4 — reconciler
- [ ] `src`/`dp` (from targeted-update.md phase 1), node-level hashes, keyed diff with LIS moves (3.3)

### Phase 5 — token-friendly output (3.9)

### Phase 6 — Tier B spike (3.7), go / no-go recorded here

## 7. Results (2026-10-26, clockify.me, ~1426 shapes)

### Phase 0 — measurements (`pb bench build|export`)

| Build placement (150 rects + 30 texts) | ms / rect | ms / text |
|---|---|---|
| inside the page board | 59–64 | 41–50 |
| top-level board on the same page | 60–64 | 40–43 |
| viewport parked over empty canvas | 61–63 | 51–54 |
| page board hidden | 60–62 | 65–71 |
| **empty page** | **15–17** | 14–30 |
| empty page + component transfer (180 shapes) | 15–17 + **132–242 ms** for the whole transfer | names, plugin data, parent kept |

- The cost grows with the shapes on the **current page**: hypotheses "board size", "viewport" and
  "hidden board" are rejected. Removing a 180-shape board costs only 35–52 ms.
- Real spec nodes cost **~30 ms each even on an empty page** (many changes per node), and moving
  real nodes onto a full page costs ~19 ms per shape (3.0 s for the 161-shape Footer).
- Exports: whole board 13.9 s; 12 section boards one by one 70.9 s (~6 s fixed per call); 4 in parallel
  27.1 s; stitched sections differ from the whole export by 0.36 % (text antialiasing at fractional
  section y). **§3.5 (section render cache) is dropped**: never pixel-exact, and slower unless one
  section changed.
- `revn` is bumped 1–3 s after an edit; exports do not change it.

### Phase 1 — skip work that is already done

| Run | Before | After |
|---|---|---|
| `pb rebuild --fix` with nothing changed | 30.8 s | **1.7 s** (same verdict, same exit code) |
| convert with the same inputs | 3.5 s | 0.8 s (mostly the Penpot font list call) |

A Penpot edit (revn 77 → 78) made the next rebuild run in full again, as it must.

### Phase 2 — staged builds

| Build | In place | Staged |
|---|---|---|
| full `--all` (fixed threshold of 40 shapes, before the cost model) | 45.2 s | 48.6–51.3 s: per-shape build 28.9 → 18.3 s, but 11.3 s of page/component/transfer overhead |
| Footer only, on the full page | 13.0 s | 12.4 s |
| page diff (QA) | 1.057 % | **1.057 %** (identical; staged copies are faithful) |

Staging now runs only where the cost model (`plan.staging_saves_time`) predicts a saving, with
page + build + component merged into one call. On Clockify-sized pages the gain is small. The
build floor is the per-node cost, not the page size, so the next build lever is **fewer changes
per node** (§3.4, second list) or the library bridge (§3.7).

Fixed along the way (tests first): `--only` rebuilds lost the section layer order; `--page` could
pick a same-named board on another page; "No Penpot instance connected" did not wait for the plugin.

## 6. Risks

- `revn` may change on actions that do not affect pixels (selection does not; thumbnails might).
  If so, the short-circuit only misses a skip, which is safe.
- Section exports may differ from the page export at section edges (shadows that overflow, clipped
  children). `--verify-cache` catches that, and the fallback is the full export.
- Staging boards change the parent while building: constraints and flex children must be
  built inside the final board size. Test this with the flex/grid fixtures.
- The library route depends on the backend RPC, which is not a stable API (paths changed in 2.12);
  `pb doctor` checks the version.
