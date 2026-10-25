"""Capture a website (screenshot + layout dump) behind the capture quality gate.

The heavy lifting is done by the Node CLI `node-cli.js capture` (headless Chrome). This
module runs it with retries, judges every attempt with `capture_gate`, and only then moves
the result into `.pbridge/captures/<name>/` (and makes it the project reference).
A failing capture never becomes the reference unless force=True.
"""
from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pbridge.paths import node_command
from pbridge.project import ProjectState
from pbridge.quality import capture_gate, print_gate


class CaptureRejected(SystemExit):
    """Raised (as a clean CLI exit) when no attempt produced an acceptable capture."""


@dataclass
class CaptureOptions:
    url: str
    name: str | None = None
    width: int = 1920
    dpr: float = 1
    fonts: str | None = None        # comma list of families that must be loaded
    hide: str | None = None         # comma list of CSS selectors to hide
    click: str | None = None        # comma list of CSS selectors to click first
    selector: str | None = None     # dump only this subtree
    wait: int | None = None         # ms to wait before the dump
    height: int | None = None       # fixed viewport height instead of the document height
    no_scroll: bool = False
    no_freeze: bool = False
    keep_overlays: bool = False
    color_scheme: str | None = None    # "dark" / "light": emulated prefers-color-scheme
    cookies: str | None = None         # JSON cookie file (pages behind a login)
    user_data_dir: str | None = None   # Chrome profile folder with a logged-in session
    set_reference: bool = True
    force: bool = False
    retries: int = 3

    @staticmethod
    def _absolute(path: str | None) -> str | None:
        return str(Path(path).expanduser().resolve()) if path else None

    def capture_name(self) -> str:
        return self.name or self.url.split("//")[-1].split("/")[0].replace(".", "_")

    def node_args(self, out_dir: Path) -> list[str]:
        cmd = [*node_command("capture"), "--url", self.url, "--out", str(out_dir),
               "--width", str(self.width), "--dpr", str(self.dpr)]
        for flag, value in (("--fonts", self.fonts), ("--hide", self.hide), ("--click", self.click),
                            ("--selector", self.selector), ("--wait", self.wait), ("--height", self.height),
                            ("--color-scheme", self.color_scheme), ("--cookies", self._absolute(self.cookies)),
                            ("--user-data-dir", self._absolute(self.user_data_dir))):
            if value:
                cmd += [flag, str(value)]
        if self.no_scroll:
            cmd.append("--no-scroll")
        if self.no_freeze:
            cmd.append("--no-freeze")
        if self.keep_overlays:
            cmd.append("--keep-overlays")
        return cmd


def capture_site(state: ProjectState, opts: CaptureOptions) -> dict[str, Any]:
    """Run the capture; returns the capture script's summary + quality verdict."""
    state.init()
    name = opts.capture_name()
    final = state.path("captures", name, "x").parent
    tmp = state.path("captures", name + ".tmp", "x").parent
    cmd = opts.node_args(tmp)
    gate, info = None, None
    for attempt in range(1, opts.retries + 1):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr[-2000:], file=sys.stderr)
            continue
        info = json.loads(result.stdout.strip().splitlines()[-1])
        gate = capture_gate(json.loads((tmp / "layout.json").read_text()), tmp / "shot.png")
        print_gate(f"capture attempt {attempt}", gate)
        if gate["ok"]:
            break
    if info is None:
        raise CaptureRejected("capture failed")
    if gate and not gate["ok"] and not opts.force:
        raise CaptureRejected(f"capture rejected by quality gate (kept in {tmp}); fix the cause or use --force")
    if final.exists():
        shutil.rmtree(final)
    shutil.move(str(tmp), str(final))
    info["out"] = str(final)
    info["quality"] = {"ok": gate["ok"], "errors": gate["errors"], "warnings": gate["warnings"]}
    if opts.set_reference:
        state.config["reference"] = str(final / "shot.png"); state.config["capture"] = str(final)
        state.save_config()
    return info


def capture_widths(state: ProjectState, opts: CaptureOptions, widths: list[int]) -> list[dict[str, Any]]:
    """Capture the same page at several viewport widths (e.g. 1440, 768, 390) as `<name>-<width>`.

    The first width becomes the project reference when opts.set_reference is set.
    """
    base_name = opts.capture_name()
    summaries = []
    for index, width in enumerate(widths):
        width_opts = dataclasses.replace(opts, width=width, name=f"{base_name}-{width}",
                                         set_reference=opts.set_reference and index == 0)
        summaries.append(capture_site(state, width_opts))
    return summaries
