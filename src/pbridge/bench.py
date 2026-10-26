"""Performance experiments against the live Penpot file (`pb bench`).

These decide which fast-build v2 fixes are worth building (docs/fast-build-v2.md §3.4, §3.5).
Every experiment cleans up after itself: temporary boards are removed, a hidden page board is
shown again, the viewport and the current page are restored, a temporary page is deleted.

* build: create `count` rectangles and `texts` texts in a temporary board, once per placement
  mode, and time every plugin operation (create, append, resize, move, fill, name). The modes
  tell apart the possible causes of the per-shape cost growing with the document:
    inside         - a board inside the page board (where a section is built today)
    top            - a top-level board next to the page board (same page)
    inside-parked  - inside, with the viewport moved over empty canvas
    inside-hidden  - inside, with the page board hidden while building
    empty-page     - a top-level board on a fresh page (deleted afterwards)
    component      - built on a fresh page, made a component, then one instance is placed in
                     the page board and detached (a cross-page move: is it cheap, is it faithful?)
* export: the page board in one export vs its sections one by one vs `parallel` at once, and
  the pixel difference between the stitched sections and the whole-board export.
"""
from __future__ import annotations

import io
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pbridge.connection import Bridge, MCPClient

BUILD_MODES = ("inside", "top", "inside-parked", "inside-hidden", "empty-page", "component")

# DATA: {mode, count, texts, pageBoard}. Returns per-operation milliseconds and context.
_BUILD_EXPERIMENT_JS = """
const clock = () => (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
const pageBoard = pb.byId(DATA.pageBoard);
if (!pageBoard) throw new Error('page board not found ' + DATA.pageBoard);
const originalPage = penpot.currentPage;
const savedCenter = penpot.viewport.center, savedZoom = penpot.viewport.zoom;
const ms = {create: 0, append: 0, resize: 0, move: 0, fill: 0, name: 0, textCreate: 0, textStyle: 0, textAppend: 0};
let container = null, scratchPage = null, wasHidden = pageBoard.hidden;
const started = clock();
const transfer = {};
try {
  if (DATA.mode === 'empty-page' || DATA.mode === 'component') {
    scratchPage = penpot.createPage(); scratchPage.name = 'pb bench (temporary)';
    await penpot.openPage(scratchPage);
  }
  container = penpot.createBoard();
  container.name = 'pb bench (temporary)';
  if (DATA.mode.startsWith('inside')) {
    pageBoard.appendChild(container);
    container.x = pageBoard.x; container.y = pageBoard.y + pageBoard.height - 400;
  } else {
    container.x = pageBoard.x + pageBoard.width + 4000; container.y = pageBoard.y;
  }
  container.resize(1000, 400);
  if (DATA.mode === 'inside-parked') penpot.viewport.center = {x: pageBoard.x - 100000, y: pageBoard.y - 100000};
  if (DATA.mode === 'inside-hidden') pageBoard.hidden = true;
  const shapesOnPage = penpot.currentPage.findShapes({}).length;
  const buildStarted = clock();
  for (let i = 0; i < DATA.count; i++) {
    let mark = clock(); const rectangle = penpot.createRectangle(); ms.create += clock() - mark;
    mark = clock(); container.appendChild(rectangle); ms.append += clock() - mark;
    mark = clock(); rectangle.resize(20, 20); ms.resize += clock() - mark;
    mark = clock();
    rectangle.x = container.x + (i % 40) * 24; rectangle.y = container.y + Math.floor(i / 40) * 24;
    ms.move += clock() - mark;
    mark = clock(); rectangle.fills = [{fillColor: '#3366FF', fillOpacity: 1}]; ms.fill += clock() - mark;
    mark = clock(); rectangle.name = 'bench ' + i; ms.name += clock() - mark;
    if (i === 0) rectangle.setPluginData('pb', 'bench.0');
  }
  for (let i = 0; i < DATA.texts; i++) {
    let mark = clock(); const text = penpot.createText('Bench text ' + i); ms.textCreate += clock() - mark;
    mark = clock(); text.fontSize = '16'; text.fills = [{fillColor: '#111111', fillOpacity: 1}]; ms.textStyle += clock() - mark;
    mark = clock(); container.appendChild(text); text.x = container.x + (i % 8) * 120; text.y = container.y + 300 + Math.floor(i / 8) * 20;
    ms.textAppend += clock() - mark;
  }
  const buildMs = clock() - buildStarted;
  if (DATA.mode === 'component') {
    let mark = clock();
    const component = penpot.library.local.createComponent([container]);
    transfer.componentMs = Math.round(clock() - mark);
    mark = clock(); await penpot.openPage(originalPage); transfer.openPageMs = Math.round(clock() - mark);
    mark = clock();
    const copy = component.instance();
    pageBoard.appendChild(copy);
    copy.x = pageBoard.x; copy.y = pageBoard.y + pageBoard.height - 400;
    copy.detach();
    transfer.instanceMs = Math.round(clock() - mark);
    const descendants = (shape) => (shape.children || []).reduce((total, child) => total + 1 + descendants(child), 0);
    const first = copy.children.find(child => child.name === 'bench 0');
    transfer.copiedShapes = descendants(copy);
    transfer.expectedShapes = DATA.count + DATA.texts;
    transfer.namesKept = !!first;
    transfer.pluginDataKept = !!first && first.getPluginData('pb') === 'bench.0';
    transfer.stillInstance = copy.isComponentInstance();
    transfer.parentIsPageBoard = !!copy.parent && copy.parent.id === pageBoard.id;
    mark = clock(); copy.remove(); transfer.removeOnPageMs = Math.round(clock() - mark);
  }
  for (const key of Object.keys(ms)) ms[key] = Math.round(ms[key]);
  return {mode: DATA.mode, shapesOnPage, buildMs: Math.round(buildMs), ms, transfer,
          msPerRect: +((ms.create + ms.append + ms.resize + ms.move + ms.fill + ms.name) / Math.max(1, DATA.count)).toFixed(2),
          msPerText: +((ms.textCreate + ms.textStyle + ms.textAppend) / Math.max(1, DATA.texts)).toFixed(2)};
} finally {
  const removeStarted = clock();
  if (container) { try { container.remove(); } catch (error) { /* already gone (a component main dies with its page) */ } }
  ms.remove = Math.round(clock() - removeStarted);
  if (DATA.mode === 'inside-hidden') pageBoard.hidden = wasHidden;
  if (scratchPage) { await penpot.openPage(originalPage); try { scratchPage.remove(); } catch (error) { /* keep going */ } }
  penpot.viewport.center = savedCenter; penpot.viewport.zoom = savedZoom;
  ms.total = Math.round(clock() - started);
}"""

_SECTIONS_JS = """
const board = pb.byId(DATA);
return board.children.filter(child => !child.hidden).map(child => ({id: child.id, name: child.name, type: child.type,
  bounds: [child.x, child.y, child.width, child.height]}));"""


def bench_build(bridge: Bridge, page_board: str, count: int = 150, texts: int = 30,
                modes: tuple[str, ...] = BUILD_MODES, repeat: int = 2) -> dict[str, Any]:
    """Run every build mode `repeat` times (interleaved, so drift affects all modes alike)."""
    runs: list[dict[str, Any]] = []
    for _ in range(repeat):
        for mode in modes:
            started = time.time()
            result = bridge.exec(_BUILD_EXPERIMENT_JS, data={"mode": mode, "count": count, "texts": texts,
                                                             "pageBoard": page_board}, timeout=300)
            result["wallMs"] = round((time.time() - started) * 1000)
            # work Penpot defers until after the task (persistence, rendering) slows the next call
            ping_started = time.time()
            bridge.exec("return 1;")
            result["nextPingMs"] = round((time.time() - ping_started) * 1000)
            runs.append(result)
    summary: dict[str, Any] = {}
    for mode in modes:
        mode_runs = [run for run in runs if run["mode"] == mode]
        summary[mode] = {"msPerRect": round(min(run["msPerRect"] for run in mode_runs), 2),
                         "msPerText": round(min(run["msPerText"] for run in mode_runs), 2),
                         "wallMs": min(run["wallMs"] for run in mode_runs),
                         "shapesOnPage": mode_runs[0]["shapesOnPage"]}
    return {"count": count, "texts": texts, "summary": summary, "runs": runs}


def _export_png(client: MCPClient, shape_id: str) -> tuple[bytes, float]:
    started = time.time()
    result = client.call("export_shape", {"shapeId": shape_id, "format": "png"}, timeout=300)
    if result.is_error or not result.images:
        raise RuntimeError(result.text[:300] or "export returned no image")
    return result.images[0][1], time.time() - started


def bench_export(bridge: Bridge, page_board: str, parallel: int = 4) -> dict[str, Any]:
    """Whole board vs sequential sections vs `parallel` concurrent sections; stitched vs whole pixels."""
    from PIL import Image

    from pbridge import imaging
    board = bridge.exec("const board = pb.byId(DATA); return {x: board.x, y: board.y, width: board.width, height: board.height};",
                        data=page_board)
    sections = bridge.exec(_SECTIONS_JS, data=page_board)
    report: dict[str, Any] = {"sections": len(sections)}

    whole, seconds = _export_png(bridge.client, page_board)
    report["whole_s"] = round(seconds, 2)

    started = time.time()
    sequential: dict[str, bytes] = {}
    for section in sections:
        sequential[section["id"]], _ = _export_png(bridge.client, section["id"])
    report["sequential_s"] = round(time.time() - started, 2)

    # one MCP session per worker: each holds its own session id and request counter
    clients = [MCPClient(bridge.client.url) for _ in range(parallel)]
    started = time.time()
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = [pool.submit(_export_png, clients[i % parallel], section["id"]) for i, section in enumerate(sections)]
        concurrent = [future.result() for future in futures]
    report["parallel_s"] = round(time.time() - started, 2)
    report["parallel"] = parallel
    report["parallel_same_pixels"] = all(png == sequential[section["id"]]
                                         for (png, _), section in zip(concurrent, sections))

    # stitched sections at their board-relative position vs the whole-board export
    whole_image = Image.open(io.BytesIO(whole)).convert("RGBA")
    canvas = Image.new("RGBA", whole_image.size, (255, 255, 255, 255))
    for section in sections:
        image = Image.open(io.BytesIO(sequential[section["id"]])).convert("RGBA")
        left, top = round(section["bounds"][0] - board["x"]), round(section["bounds"][1] - board["y"])
        canvas.alpha_composite(image, (max(0, left), max(0, top)))
    whole_path = bridge.state.path("bench", "whole.png")
    stitched_path = bridge.state.path("bench", "stitched.png")
    whole_image.convert("RGB").save(whole_path)
    canvas.convert("RGB").save(stitched_path)
    report["stitched_vs_whole"] = imaging.compare(str(whole_path), str(stitched_path))
    report["files"] = [str(whole_path), str(stitched_path)]
    return report
