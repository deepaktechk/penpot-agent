"""Build planning, pure (no Penpot): how to cut a spec into plugin calls, and what changed.

* pack_batches: ordered greedy packing. Consecutive nodes go into one plugin call until the
  call would exceed `max_nodes` shapes (plugin time: ~10 ms per shape, tasks die after ~120 s)
  or `max_bytes` of JSON (bigger payloads cost one extra round trip per ~60 KB chunk).
  Order is kept because sibling order is the layer (z) order in Penpot.
* section_hash: content hash of a section subtree plus the build context (fonts, origin).
  An unchanged hash means the shapes built last time are still right, so the section can
  be skipped on rebuild (and a crashed build resumes where it stopped).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pbridge.build.spec_tree import Node


def node_cost(node: Node) -> int:
    """Number of shapes a node creates: itself plus every descendant."""
    return 1 + sum(node_cost(child) for child in node.get("children", []))


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
