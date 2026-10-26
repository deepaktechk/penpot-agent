"""Content-addressed shortcuts for repeated runs: skip work whose inputs did not change.

* Convert cache. The spec is a pure function of layout.json, the screenshot, the converter
  source, the options and the fonts Penpot has. Same key => the spec written last time is still
  right (remote SVGs fetched during convert are assumed unchanged; `pb rebuild --all` re-converts).
* Rebuild short-circuit. A rebuild's result is a function of the spec, the reference image, the
  runtime, the command options and the Penpot file. The file is identified by its id and revision
  number (`penpot.currentFile.revn`, "<id>@<revn>"), which Penpot bumps on every persisted change,
  including manual edits, so a hit can never hide a change. It is read at the end of a run: exports do not change
  it, and the last edit of a run is ≥ 10 s older (export + QA), long enough for Penpot to persist
  it (measured: 1-3 s).

Entries live in `.pbridge/cache/<name>.json`, one entry per name (the latest run).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pbridge.project import ProjectState

_PACKAGE = Path(__file__).resolve().parent
# everything the converter imports (convert/** plus the URL helpers it shares with the asset store)
CONVERTER_SOURCES = (_PACKAGE / "convert", _PACKAGE / "assets" / "urls.py", _PACKAGE / "__init__.py")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()


def file_digest(path: Path | None) -> str:
    """sha1 of a file's bytes; "none" when there is no file, "missing" when it does not exist."""
    if path is None:
        return "none"
    if not path.exists():
        return "missing"
    return hashlib.sha1(path.read_bytes()).hexdigest()


def source_digest(sources: Iterable[Path] = CONVERTER_SOURCES) -> str:
    """sha1 over the relative paths and bytes of every .py file in `sources` (files or folders)."""
    digest = hashlib.sha1()
    for source in sources:
        files = sorted(source.rglob("*.py")) if source.is_dir() else [source]
        for file in files:
            relative = file.relative_to(source) if source.is_dir() else Path(file.name)
            digest.update(str(relative).encode() + b"\0" + file.read_bytes() + b"\0")
    return digest.hexdigest()


def convert_key(layout_file: Path, screenshot: Path | None, options: dict[str, Any],
                available_fonts: Iterable[str] | None, source: str) -> str:
    """Cache key of one convert. available_fonts None (Penpot not asked) differs from an empty list."""
    fonts = sorted(available_fonts) if available_fonts is not None else None
    parts = {"layout": file_digest(layout_file), "screenshot": file_digest(screenshot), "options": options,
             "fonts": fonts, "source": source}
    return hashlib.sha1(_canonical(parts)).hexdigest()


def rebuild_key(spec_digest: str, reference_digest: str, runtime_version: str, options: dict[str, Any]) -> str:
    """Cache key of one rebuild, without the Penpot side (that is the file revision, checked apart)."""
    parts = {"spec": spec_digest, "reference": reference_digest, "runtime": runtime_version, "options": options}
    return hashlib.sha1(_canonical(parts)).hexdigest()


class RunCache:
    def __init__(self, state: ProjectState):
        self.state = state

    def _file(self, name: str) -> Path:
        return self.state.path("cache", f"{name}.json")

    def lookup(self, name: str, key: str) -> dict[str, Any] | None:
        """The stored value when its key equals `key`; None on a miss or an unreadable entry."""
        try:
            entry = json.loads(self._file(name).read_text())
        except (OSError, ValueError):
            return None
        if not isinstance(entry, dict) or entry.get("key") != key:
            return None
        return entry.get("value")

    def store(self, name: str, key: str, value: dict[str, Any]) -> None:
        self._file(name).write_text(json.dumps({"key": key, "value": value}, ensure_ascii=False, default=str))

    # ------------------------------------------------------------------ rebuild short-circuit
    def store_rebuild(self, key: str, revision: str | None, board: str | None, render: str, result: dict[str, Any]) -> None:
        if revision is None:   # without a revision the next run cannot prove the file is unchanged
            return
        self.store("rebuild", key, {"revision": revision, "board": board, "render": render, "result": result})

    def reusable_rebuild(self, key: str, revision: str | None, board: str | None) -> dict[str, Any] | None:
        """The last rebuild when its inputs, the Penpot file ("<id>@<revn>") and the board are unchanged."""
        entry = self.lookup("rebuild", key)
        if not entry or revision is None or entry.get("revision") != revision or entry.get("board") != board:
            return None
        if not Path(entry.get("render", "")).exists():
            return None
        return entry
