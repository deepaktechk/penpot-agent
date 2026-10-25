"""Spec -> Penpot: section builds, page boards, snapshots, audit/autofix.

The pure tree helpers are imported eagerly; the classes that need a Penpot connection are
loaded on first use so `pbridge.build.flatten` stays cheap to import.
"""
from pbridge.build.snapshots import snap_to_spec
from pbridge.build.spec_tree import assign_keys, flatten, node_box, offset_nodes

_snap_to_spec = snap_to_spec   # old name

_LAZY = {"SpecBuilder": "pbridge.build.builder", "PageBoards": "pbridge.build.page_board",
         "Snapshots": "pbridge.build.snapshots", "Aligner": "pbridge.build.alignment"}

__all__ = ["Aligner", "PageBoards", "Snapshots", "SpecBuilder", "assign_keys", "flatten", "node_box",
           "offset_nodes", "snap_to_spec"]


def __getattr__(name: str):
    if name in _LAZY:
        import importlib
        return getattr(importlib.import_module(_LAZY[name]), name)
    raise AttributeError(name)
