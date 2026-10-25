"""Visual QA: compare a Penpot render against the reference image."""
from pbridge.imaging.hotspots import Hotspot, hotspots
from pbridge.imaging.metrics import align_sizes, compare, load, mad, pct_diff, ssim
from pbridge.imaging.offsets import audit, best_offset
from pbridge.imaging.visuals import montage, overlay

__all__ = ["Hotspot", "align_sizes", "audit", "best_offset", "compare", "hotspots", "load", "mad", "montage",
           "overlay", "pct_diff", "ssim"]
