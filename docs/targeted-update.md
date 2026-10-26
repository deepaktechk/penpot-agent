# Targeted update (`pb update`) — design

> **Status: planned, not implemented yet.** This document is the agreed design; update it as the
> phases land. Until then, the smallest unit pb can rebuild is a section (`pb rebuild --only secNN`).

## Problem

Fixing one part of a cloned design (e.g. "the login inputs are collapsed") must change **only that
part** of the existing Penpot board. Today it cannot:

1. **No link from a Penpot layer back to its page element.** Spec keys are positional
   (`sec00.2.1.0`, `build/spec_tree.py:assign_keys`); when anything earlier in the page or in the
   converter output changes, every later key shifts, so a layer cannot be reliably mapped to "that
   `<input>`".
2. **The builder replaces whole sections only** (`build/builder.py`: `_forget_section` removes the
   section board, then rebuilds it). On many sites one section is most of the page (facebook.com
   `sec00` is the top 943 px).
3. **No partial re-convert / re-capture.** `pb capture --selector` exists, but nothing ties its
   output back to existing layers.

The result is a full rebuild for a one-element fix, which also discards manual edits made on the board.

## Command

```
pb update <target> [--recapture] [--dry-run] [--force] [--no-snapshot]
```

- **target**: `selection` (the layers selected in Penpot — the main workflow), a layer name or
  regex, a spec key, a shape id, or `--region x,y,w,h`. A deep selection (the text inside an input)
  is climbed to the nearest layer that represents a whole page element (the input's group).
- **source of the new content**
  - default: the project's existing capture, re-converted with the current code (applies a
    converter fix to just that part);
  - `--recapture`: load the URL again with the capture's saved options (width, fonts, `--hide`,
    `--click`...) and use only the target element's subtree. The full page still loads so that
    positions match the board; only the target part is used. The reference screenshot is refreshed
    for that region only.

## How it works

1. **Resolve** the target to shape ids (`cli/support.py:resolve_target`), then to spec keys with a
   reverse lookup of `.pbridge/idmap.json`. Unkeyed (hand-made) shapes are an error.
2. **Identify the source element.** The capture records a stable path per element (`dp`: its `id`
   when it has one, else a `tag:nth-of-type` chain from the nearest ancestor with an id). The
   converter writes it onto every spec node it produces (`src`). The target node's `src` names the
   page element to refresh.
3. **Produce the new subtree.** Convert only that element (`TreeAssembler.assemble(index)`; capture
   coordinates are page coordinates, so no re-layout is needed). New keys reuse the old key as
   prefix, so patches, audits and later updates keep working.
4. **Match old and new** by `src`, never by positional key. Fallback when the element is gone or
   ambiguous (page changed): tag + text + box overlap; below a confidence threshold pb stops and
   lists candidates instead of guessing. Boards built before `src` existed fall back to key + box
   overlap against the same capture.
5. **Replace in place** (Penpot plugin API: `insertChild`, `parentIndex`, `setParentIndex` —
   verified on design.penpot.app):
   1. snapshot the target (`pb restore` undoes the update);
   2. build the new subtree into the old shape's parent;
   3. move it to the old layer index;
   4. remove only the old subtree's shapes;
   5. update `idmap.json` / `boxes.json` for that key prefix only.
   Every other shape on the board keeps its id and any manual edits.
6. **QA the region only**: export, `compare --region` over the target box (+ margin), montage.

## Safety

- `--dry-run`: list the shapes that would be removed and the nodes that would replace them; no
  Penpot changes.
- **Manual-edit guard**: at build time store a fingerprint (geometry, fills, text) per keyed shape;
  if the target's shapes differ from it, warn and require `--force`.
- **Board ownership guard** (also for `pb rebuild`): refuse to build when the idmap's shapes belong
  to a board other than `--board` (two sites in one project folder overwrote each other's boards).

## Changes by area

| Area | Change |
|---|---|
| Capture (`js/src/capture/page/elements.ts`) | `dp` element path per captured element |
| Converter (`convert/tree.py`, `converter.py`) | `src` on every node; convert a single element subtree |
| Spec format (`js/src/plugin/spec.ts`, `build/validate.py`, `docs/spec-format.md`) | optional `src` field |
| Builder (`build/builder.py`) + plugin (`js/src/plugin/builder.ts`) | replace one subtree at its layer index |
| CLI (`cli/commands/edit.py`, `cli/app.py`, `docs/commands.md`) | `pb update` |
| Skills (`skills/penpot-agent`, `skills/clone`) | use `pb update` for targeted fixes, not `pb rebuild` |

## Tests

- Unit: reverse idmap lookup and climbing to the element node; `src` matching and the fallback;
  key prefixing of the new subtree; dry-run output.
- Fixture (`tests/fixtures/tricky.html`): two sibling elements with and without `id`; `dp` is
  stable across two captures.
- `pb selftest --build`: update one element; its siblings keep their shape ids and layer order.

## Phases

1. In-place update from the existing capture: selection targets, `src`/`dp`, subtree replace,
   snapshot, `--dry-run`, region QA, board ownership guard.
2. `--recapture`: fresh content for the target element from the URL.
3. Manual-edit guard (`--force`) and `--region` targets.
