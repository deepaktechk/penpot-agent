"""Stage timing for multi-step commands (rebuild, clone): where did the seconds go?

    timer = StageTimer()
    with timer.stage("build"):
        ...
    timer.summary()   # {"build": 12.3, ..., "total": 40.1}

Each finished stage prints one line to stderr (`[time] build 12.3s`), flushed at once so the
progress is visible even when the output is redirected to a file.
"""
from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager


class StageTimer:
    def __init__(self, label: str = "time"):
        self.label = label
        self.started = time.time()
        self.stages: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started = time.time()
        try:
            yield
        finally:
            elapsed = time.time() - started
            self.stages[name] = round(self.stages.get(name, 0.0) + elapsed, 2)
            print(f"[{self.label}] {name} {elapsed:.1f}s", file=sys.stderr, flush=True)

    def summary(self) -> dict[str, float]:
        return {**self.stages, "total": round(time.time() - self.started, 2)}
