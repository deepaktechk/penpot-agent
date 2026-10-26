"""Build planning, pure (no Penpot): how to cut a spec into plugin calls, and what changed.

* pack_batches: ordered greedy packing. Consecutive nodes go into one plugin call until the
  call would exceed `max_nodes` shapes (plugin time: ~10 ms per shape, tasks die after ~120 s)
  or `max_bytes` of JSON (bigger payloads cost one extra round trip per ~60 KB chunk).
  Order is kept because sibling order is the layer (z) order in Penpot.
* section_hash: content hash of a section subtree plus the build context (fonts, origin).
  An unchanged hash means the shapes built last time are still right, so the section can
  be skipped on rebuild (and a crashed build resumes where it stopped).
* staging_saves_time: cost model deciding whether a section is built on a temporary page
  (`SpecBuilder._build_staged`). Measured 2026-10-26 (`pb bench build`, Clockify): every change
  costs ~0.032 ms more per shape already on the page (a rectangle: 15 ms on an empty page,
  60 ms at 1427 shapes), and real nodes cost ~30 ms each even on an empty page. A staged section
  pays ~1.5 s for the page switch, the component and its share of the transfer, so only big
  sections on a full page gain (Footer, 161 shapes at ~1240 page shapes: 11.6 s -> 5.7 s).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pbridge.build.spec_tree import Node


def node_cost(node: Node) -> int:
    """Number of shapes a node creates: itself plus every descendant."""
    return 1 + sum(node_cost(child) for child in node.get("children", []))


# SVG elements Penpot's SVG import turns into shapes of their own
_SVG_SHAPE_RE = re.compile(r"<(?:g|path|rect|circle|ellipse|line|polyline|polygon)[\s/>]")
PAGE_SHAPE_COST_MS = 0.032       # extra cost of one change per shape already on the page
STAGE_OVERHEAD_MS = 1500.0       # temporary page + component + transfer share, per staged section


def shape_estimate(node: Node) -> int:
    """Shapes a node really creates in Penpot: node_cost plus the shapes inside imported SVGs."""
    own = len(_SVG_SHAPE_RE.findall(node["svg"])) if node.get("t") == "svg" and isinstance(node.get("svg"), str) else 0
    return 1 + own + sum(shape_estimate(child) for child in node.get("children", []))


def staging_saves_time(section_shapes: int, page_shapes: int) -> bool:
    """True when building on an empty temporary page saves more than the staging overhead."""
    return section_shapes * page_shapes * PAGE_SHAPE_COST_MS > STAGE_OVERHEAD_MS


def _json_size(node: Node) -> int:
    return len(json.dumps(node, ensure_ascii=False, separators=(",", ":")))


def pack_batches(nodes: list[Node], max_nodes: int, max_bytes: int) -> list[list[Node]]:
    """Split `nodes` into consecutive batches within both limits; a node that alone exceeds
    a limit gets a batch of its own (callers split such nodes further when they can)."""
    batches: list[list[Node]] = []
    current: list[Node] = []
    current_nodes = current_bytes = 0
    for node in nodes:
        cost, size = node_cost(node), _json_size(node)
        if current and (current_nodes + cost > max_nodes or current_bytes + size > max_bytes):
            batches.append(current)
            current, current_nodes, current_bytes = [], 0, 0
        current.append(node)
        current_nodes += cost
        current_bytes += size
    if current:
        batches.append(current)
    return batches


def section_hash(section: Node, context: dict[str, Any]) -> str:
    """Stable content hash of a section subtree and everything else that shapes its build."""
    canonical = json.dumps({"node": section, "context": context}, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return hashlib.sha1(canonical.encode()).hexdigest()
