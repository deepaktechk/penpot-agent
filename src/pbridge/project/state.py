"""Per-project state stored in `<project>/.pbridge/`.

Layout (the format is shared with existing projects - do not rename keys or files):

    config.json    reference image, capture dir, page board id/name, optional mcp_url
    assets.json    image key -> uploaded Penpot ImageData (see assets/store.py)
    idmap.json     spec key (e.g. "sec03.2.1") -> Penpot shape id of the last build
    boxes.json     spec key -> target box in page coordinates (used by audit/autofix)
    history.json   render-gate runs (the last good one is the regression baseline)
    captures/ specs/ renders/ diffs/ snapshots/ logs/
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STATE_DIR_NAME = ".pbridge"
SUBDIRS = ("renders", "snapshots", "captures", "specs", "diffs", "logs")


def find_project_root(start: Path | None = None) -> Path:
    """Project root = nearest ancestor of `start` (default cwd) holding a `.pbridge/` dir.

    PBRIDGE_PROJECT overrides the search. Falls back to `start` itself, so
    `pb init` can create the state dir there.
    """
    env = os.environ.get("PBRIDGE_PROJECT")
    if env:
        return Path(env).expanduser().resolve()
    current = (start or Path.cwd()).resolve()
    for folder in [current, *current.parents]:
        if (folder / STATE_DIR_NAME).is_dir():
            return folder
    return current


@dataclass
class ProjectState:
    """Read/write access to one project's `.pbridge/` folder."""

    root: Path
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def dir(self) -> Path:
        return self.root / STATE_DIR_NAME

    def path(self, *parts: str) -> Path:
        """Path inside the state dir; parent folders are created on demand."""
        target = self.dir.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def load_json(self, name: str, default: Any) -> Any:
        """Load a JSON file from the state dir; `default` if missing or corrupt."""
        source = self.dir / name
        if source.exists():
            try:
                return json.loads(source.read_text())
            except json.JSONDecodeError:
                return default
        return default

    def save_json(self, name: str, data: Any) -> Path:
        """Atomically write a JSON file (write to .tmp, then rename)."""
        target = self.path(name)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        temporary.replace(target)
        return target

    def save_config(self) -> Path:
        return self.save_json("config.json", self.config)

    @classmethod
    def open(cls, root: Path | None = None) -> ProjectState:
        """Open the project at `root` (default: found by walking up from the cwd)."""
        root = root or find_project_root()
        state = cls(root=root)
        state.config = state.load_json("config.json", {})
        return state

    def init(self) -> Path:
        """Create the state dir, its sub-folders and a default config (idempotent)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        for sub in SUBDIRS:
            (self.dir / sub).mkdir(exist_ok=True)
        ignore_file = self.dir / ".gitignore"
        if not ignore_file.exists():   # captures, renders and the upload cache never belong in git
            ignore_file.write_text("# created by pb init: project state is local (captures, renders, cache)\n*\n")
        if not (self.dir / "config.json").exists():
            self.save_json("config.json", {"reference": None, "page_board": None, "default_font": "Inter"})
        return self.dir

    # ---- convenience accessors used by several commands
    def capture_dir(self) -> Path:
        return Path(self.config.get("capture", ""))

    def spec_path(self) -> Path:
        """Spec file produced by `pb convert` for the current capture."""
        return self.path("specs", self.capture_dir().name + ".json")

    def latest_render(self) -> Path | None:
        files = sorted(self.path("renders", "x").parent.glob("*.png"), key=lambda render: render.stat().st_mtime)
        return files[-1] if files else None


# short alias used throughout the code base
State = ProjectState
