"""Quality gates: stop bad inputs (capture gate) and catch bad outputs (render gate)."""
from pbridge.quality.capture_gate import capture_gate
from pbridge.quality.render_gate import render_gate
from pbridge.quality.result import DEFAULTS, print_gate

__all__ = ["DEFAULTS", "capture_gate", "print_gate", "render_gate"]
