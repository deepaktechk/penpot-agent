"""Apply review fixes: to a live Penpot file (as patch operations) or to a spec file (offline)."""
from __future__ import annotations

from typing import Any

from pbridge.build.spec_tree import flatten


def fix_operations(issues: list[dict]) -> list[dict]:
    """The patch operations of the fixable issues (one per issue, in report order)."""
    return [found["fix"] for found in issues if found.get("fix")]


def apply_to_spec(spec: dict | list, operations: list[dict]) -> int:
    """Apply `set` fixes selected by spec key to a spec in place; returns how many were applied."""
    nodes = spec["nodes"] if isinstance(spec, dict) else spec
    by_key = {node["key"]: node for node in flatten(nodes) if node.get("key")}
    applied = 0
    for operation in operations:
        node = by_key.get(operation.get("sel", {}).get("key"))
        if node is None:
            continue
        changes: dict[str, Any] = operation.get("set", {})
        for key, value in changes.items():
            if key == "textStyle":
                node.setdefault("text", {}).update(value)
            else:
                node[key] = value
        applied += 1
    return applied
