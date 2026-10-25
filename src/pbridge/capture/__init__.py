"""Website capture (runs `node-cli.js capture` behind the capture gate)."""
from pbridge.capture.runner import CaptureOptions, CaptureRejected, capture_site, capture_widths

__all__ = ["CaptureOptions", "CaptureRejected", "capture_site", "capture_widths"]
