"""Readable layer names for generated shapes."""
from __future__ import annotations

import re

from pbridge.convert.context import Element

# utility-class prefixes (Tailwind & co.) that say nothing about what an element is
_UTILITY_CLASS_RE = re.compile(
    r"^(p|m|w|h|px|py|mx|my|pt|pb|mt|mb|gap|flex|grid|text|bg|rounded|border|shadow|items|justify|relative|absolute|z|top|"
    r"left|right|bottom|inset|overflow|transition|duration|ease|opacity|hidden|block|inline|max|min|font|leading|tracking|"
    r"col|row|space|self|order|cursor|group|pointer|transform|translate|scale|backdrop|from|to|via)(-|$)")


def slug(text: object, max_length: int = 32) -> str:
    """Collapse whitespace and cut to max_length characters (with an ellipsis)."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:max_length] + ("…" if len(text) > max_length else "")


def name_for(element: Element, kind: str) -> str:
    """'tag#id', 'tag.meaningful-class', or a generic 'tag <kind>'."""
    tag = element["tag"]
    if element.get("htmlId"):
        return f"{tag}#{element['htmlId']}"
    classes = (element.get("cls") or "").split()
    hint = next((name for name in classes
                 if not re.search(r"[:\[\]/]", name) and len(name) < 24 and not _UTILITY_CLASS_RE.match(name)), None)
    return f"{tag}.{hint}" if hint else (tag if kind == "box" else f"{tag} {kind}")
