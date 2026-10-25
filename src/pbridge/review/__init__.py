"""Design review: accessibility, consistency and hygiene checks with safe auto-fixes.

Works on any Penpot design (live, through `pb.serialize`) or on a spec file (offline).
"""
from pbridge.review.colors import contrast_ratio, min_contrast
from pbridge.review.rules import RULES, ReviewOptions, review

__all__ = ["RULES", "ReviewOptions", "contrast_ratio", "min_contrast", "review"]
