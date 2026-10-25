"""Hotspots: the worst-differing areas of a render, as bounding boxes.

Algorithm: |reference - render| luma -> downsample to a grid of `cell` px cells -> threshold ->
8-connected components (flood fill) -> bounding boxes ranked by area x mean error.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageChops


@dataclass
class Hotspot:
    x: int
    y: int
    width: int
    height: int
    err: float     # mean cell error (0-255)
    area: int      # px²

    def to_dict(self) -> dict:
        """JSON form used everywhere else (montage, gates, CLI output): {x, y, w, h, err, area}."""
        return {"x": self.x, "y": self.y, "w": self.width, "h": self.height, "err": self.err, "area": self.area}


def hotspots(reference: Image.Image, render: Image.Image, region=None, tolerance: int = 40, cell: int = 6, min_cells: int = 2,
             limit: int = 25) -> list[dict]:
    if region:
        reference, render = reference.crop(region), render.crop(region)
    origin_x, origin_y = (region[0], region[1]) if region else (0, 0)
    difference = ImageChops.difference(reference, render).convert("L")
    grid_width, grid_height = max(1, difference.width // cell), max(1, difference.height // cell)
    cell_errors = difference.resize((grid_width, grid_height), Image.BOX).load()
    occupied = [[cell_errors[x, y] > tolerance / 3 for x in range(grid_width)] for y in range(grid_height)]
    seen = [[False] * grid_width for _ in range(grid_height)]
    found = []
    for y in range(grid_height):
        for x in range(grid_width):
            if not occupied[y][x] or seen[y][x]:
                continue
            stack = [(x, y)]; seen[y][x] = True; cells = []
            while stack:                       # flood fill one component
                cell_x, cell_y = stack.pop(); cells.append((cell_x, cell_y))
                for next_x in (cell_x - 1, cell_x, cell_x + 1):
                    for next_y in (cell_y - 1, cell_y, cell_y + 1):
                        if (0 <= next_x < grid_width and 0 <= next_y < grid_height
                                and occupied[next_y][next_x] and not seen[next_y][next_x]):
                            seen[next_y][next_x] = True; stack.append((next_x, next_y))
            if len(cells) < min_cells:
                continue
            columns = [cell_x for cell_x, _ in cells]; rows = [cell_y for _, cell_y in cells]
            mean_error = sum(cell_errors[position] for position in cells) / len(cells)
            found.append(Hotspot(origin_x + min(columns) * cell, origin_y + min(rows) * cell,
                                 (max(columns) - min(columns) + 1) * cell, (max(rows) - min(rows) + 1) * cell,
                                 round(mean_error, 1), len(cells) * cell * cell))
    found.sort(key=lambda spot: -spot.area * spot.err)
    return [spot.to_dict() for spot in found[:limit]]
