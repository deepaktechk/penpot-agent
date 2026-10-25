"""Desktop notification used when the bridge needs the user (e.g. "click the Penpot tab").

Best effort only: a missing notifier never fails a command.
"""
from __future__ import annotations

import shutil
import subprocess
import sys


def notify(title: str, message: str) -> None:
    try:
        if sys.platform == "darwin":
            script = f'display notification "{message}" with title "{title}" sound name "Glass"'
            subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)
        elif shutil.which("notify-send"):   # Linux desktops (libnotify)
            subprocess.run(["notify-send", title, message], timeout=5, capture_output=True)
    except Exception:
        pass
