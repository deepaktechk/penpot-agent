"""Gate thresholds and the result record shared by both gates."""
from __future__ import annotations

import sys
from typing import Any, TextIO

DEFAULTS = {
    "font_dev_error": 0.02,      # median |painted - expected| / expected width per family
    "min_stable_samples": 3,     # consecutive identical layout signatures before capture
    "section_pct_error": 3.0,    # % differing pixels in a section -> error
    "section_pct_warn": 1.6,
    "image_mad_error": 40.0,     # mean abs diff inside an image/svg box -> missing/wrong
    "regress_abs": 0.3,          # section pct worse than baseline by this much ...
    "regress_rel": 0.25,         # ... and by this fraction -> regression
}

GateResult = dict[str, Any]      # {"ok": bool, "errors": [str], "warnings": [str], "info": {...}}


def new_result() -> GateResult:
    return {"ok": True, "errors": [], "warnings": [], "info": {}}


def fail(result: GateResult, message: str) -> None:
    result["errors"].append(message); result["ok"] = False


def thresholds(overrides: dict | None) -> dict:
    return {**DEFAULTS, **(overrides or {})}


def print_gate(title: str, result: GateResult, stream: TextIO | None = None) -> None:
    """'[title] PASS|FAIL errors=N warnings=M', then ✗ errors and ! warnings (max 12)."""
    stream = stream or sys.stderr
    status = "PASS" if result["ok"] else "FAIL"
    print(f"[{title}] {status}  errors={len(result['errors'])} warnings={len(result['warnings'])}", file=stream)
    for error in result["errors"]:
        print(f"  ✗ {error}", file=stream)
    for warning in result["warnings"][:12]:
        print(f"  ! {warning}", file=stream)
