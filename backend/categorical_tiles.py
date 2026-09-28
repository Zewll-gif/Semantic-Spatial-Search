"""On-demand XYZ display tiles from the frozen A7-T categorical GeoTIFF.

The vector database is intentionally not involved in map coloration.  Every
output sample comes from the source raster with nearest-neighbor resampling.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT


WEB_MERCATOR_LIMIT = 20037508.342789244
TILE_SIZE = 256


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    if not (0 <= z <= 18 and 0 <= x < 2**z and 0 <= y < 2**z):
        raise ValueError("Invalid XYZ tile coordinates")
    extent = 2 * WEB_MERCATOR_LIMIT / (2**z)
    west = -WEB_MERCATOR_LIMIT + x * extent
    north = WEB_MERCATOR_LIMIT - y * extent
    return west, north - extent, west + extent, north


def canonical_palette(path: Path) -> tuple[tuple[int, int, int], ...]:
    source = json.loads(path.read_text(encoding="utf-8"))["classes"]
    colors = [(0, 0, 0)]
    for numeric in range(1, 8):
        hex_color = source[f"R{numeric}"]["color"].lstrip("#")
        colors.append(tuple(int(hex_color[index:index + 2], 16) for index in (0, 2, 4)))
    return tuple(colors)


def parse_classes(value: str | None) -> tuple[int, ...]:
    if not value:
        return tuple(range(1, 8))
    codes = [part.strip().upper() for part in value.split(",")]
    if not codes or any(code not in {f"R{n}" for n in range(1, 8)} for code in codes):
        raise ValueError("classes must be comma-separated R1-R7")
    return tuple(sorted({int(code[1:]) for code in codes}))


@lru_cache(maxsize=512)
def _render_cached(source_name: str, palette_name: str, z: int, x: int, y: int,
                   selected: tuple[int, ...]) -> bytes:
    west, south, east, north = tile_bounds(z, x, y)
    target_transform = from_bounds(west, south, east, north, TILE_SIZE, TILE_SIZE)
    with rasterio.open(source_name) as source:
        with WarpedVRT(source, crs="EPSG:3857", transform=target_transform,
                       width=TILE_SIZE, height=TILE_SIZE, resampling=Resampling.nearest,
                       src_nodata=0, nodata=0) as warped:
            labels = warped.read(1)
    palette = canonical_palette(Path(palette_name))
    rgba = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
    for numeric in selected:
        match = labels == numeric
        rgba[match, :3] = palette[numeric]
        rgba[match, 3] = 255
    stream = BytesIO()
    Image.fromarray(rgba, "RGBA").save(stream, format="PNG", optimize=True)
    return stream.getvalue()


def render_tile(source: Path, palette: Path, z: int, x: int, y: int,
                classes: str | None = None) -> bytes:
    selected = parse_classes(classes)
    return _render_cached(str(source), str(palette), z, x, y, selected)
