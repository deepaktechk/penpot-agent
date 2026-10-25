"""Capture (layout.json) -> pbridge spec (list of section boards).

Pipeline
 1. parse    : colors (rgb/hsl/hex/oklab/oklch/lab/lch/color()), gradients, shadows,
               radii, borders, transforms, clip-paths              -> convert/css/
 2. nodes    : element -> rect / borders / image / svg (+svg texts) / text / input
               / located decorations                                -> convert/nodes/
 3. text     : exact browser line breaks, first-line anchoring, inline children as
               ranges, clamp/ellipsis, metric fitting                -> convert/nodes/text.py
 4. tree     : DOM hierarchy -> nested groups, z-index aware          -> convert/tree.py
 5. sections : top-level blocks -> boards with semantic names         -> convert/sections.py
"""
from pbridge.convert.converter import Converter, count_nodes
from pbridge.convert.css import (gradient_char_ranges, paint, paint_with_op, parse_clip_polygon, parse_color,
                                 parse_gradient, parse_radius, parse_shadows, rotation_of, split_top)
from pbridge.convert.naming import slug
from pbridge.convert.nodes.urls import resolve_img_url

__all__ = ["Converter", "count_nodes", "gradient_char_ranges", "paint", "paint_with_op", "parse_clip_polygon",
           "parse_color", "parse_gradient", "parse_radius", "parse_shadows", "resolve_img_url", "rotation_of",
           "slug", "split_top"]
