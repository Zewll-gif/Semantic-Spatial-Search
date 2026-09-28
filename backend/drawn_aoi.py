"""Validated raster zonal analysis for user-drawn AOIs.

All numbers are computed from canonical project rasters.  This module never
modifies the frozen A7-T prediction and never delegates GIS math to an LLM.
"""
from __future__ import annotations

import json
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from runtime_env import configure_geospatial_environment

configure_geospatial_environment()

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.mask import mask
from rasterio.windows import from_bounds, bounds as window_bounds
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform

from project_paths import DEM_PATH, NDVI_PATH, NDWI_PATH, PALETTE_PATH, PREDICTION
from reliability import reliability_context

MODEL_VERSION = "A7_RGBN_REVISED7_TVERSKY"
MAX_VERTICES = 5000
MAX_AREA_M2 = 250_000_000.0
CLASS_NAMES_TH = {
    "R1": "สิ่งปลูกสร้างและพื้นผิวทึบน้ำ", "R2": "พื้นที่เกษตรกรรม",
    "R3": "ไม้ยืนต้นและพื้นที่ป่า", "R4": "แหล่งน้ำ",
    "R5": "ทุ่งหญ้าและพืชล้มลุก", "R6": "พื้นดินโล่ง",
    "R7": "พื้นที่ไม่แน่ชัดหรือเมฆ",
}
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True)
TO_WGS84 = Transformer.from_crs("EPSG:32647", "EPSG:4326", always_xy=True)


class AoiValidationError(ValueError):
    pass


def _vertex_count(geometry: dict[str, Any]) -> int:
    def count(value: Any) -> int:
        if isinstance(value, (list, tuple)):
            if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
                return 1
            return sum(count(item) for item in value)
        return 0
    return count(geometry.get("coordinates", []))


def validate_geometry(geometry: dict[str, Any]) -> tuple[Any, Any, int]:
    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise AoiValidationError("geometry must be a GeoJSON Polygon or MultiPolygon in EPSG:4326")
    vertices = _vertex_count(geometry)
    if vertices < 4:
        raise AoiValidationError("AOI requires at least four coordinate vertices")
    if vertices > MAX_VERTICES:
        raise AoiValidationError(f"AOI exceeds the {MAX_VERTICES} vertex limit")
    try:
        geom_wgs84 = shape(geometry)
    except Exception as exc:
        raise AoiValidationError("invalid GeoJSON geometry") from exc
    if geom_wgs84.is_empty or not geom_wgs84.is_valid:
        raise AoiValidationError("AOI geometry is empty or topologically invalid")
    west, south, east, north = geom_wgs84.bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise AoiValidationError("AOI coordinates must be valid EPSG:4326 longitude/latitude")
    geom_utm = shapely_transform(TO_UTM.transform, geom_wgs84)
    if geom_utm.area <= 0:
        raise AoiValidationError("AOI has zero area")
    if geom_utm.area > MAX_AREA_M2:
        raise AoiValidationError("AOI exceeds 250 km²; draw a smaller area for interactive analysis")
    return geom_wgs84, geom_utm, vertices


def _masked_values(path: Path, geom_utm: Any) -> tuple[np.ndarray, dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    with rasterio.open(path) as source:
        transformer = Transformer.from_crs("EPSG:32647", source.crs, always_xy=True)
        raster_geom = shapely_transform(transformer.transform, geom_utm)
        try:
            data, _ = mask(source, [mapping(raster_geom)], crop=True, filled=False, all_touched=False)
        except ValueError:
            return np.array([], dtype=np.float32), {"crs": str(source.crs), "resolution": list(source.res), "nodata": source.nodata}
        band = data[0]
        values = band.compressed() if np.ma.isMaskedArray(band) else band.reshape(-1)
        values = values[np.isfinite(values)]
        if source.nodata is not None:
            values = values[values != source.nodata]
        return values, {"crs": str(source.crs), "resolution": list(source.res), "nodata": source.nodata,
                        "pixel_area_m2": abs(float(source.transform.a * source.transform.e))}


def _continuous_stats(path: Path, geom_utm: Any) -> dict[str, Any]:
    values, metadata = _masked_values(path, geom_utm)
    if values.size == 0:
        return {"available": False, "count": 0, "source": str(path), **metadata}
    return {"available": True, "count": int(values.size), "mean": float(np.mean(values)),
            "min": float(np.min(values)), "max": float(np.max(values)),
            "median": float(np.median(values)), "source": str(path), **metadata}


def analyze_drawn_aoi(geometry: dict[str, Any]) -> dict[str, Any]:
    geom_wgs84, geom_utm, vertices = validate_geometry(geometry)
    values, prediction_meta = _masked_values(PREDICTION, geom_utm)
    valid = values[(values >= 1) & (values <= 7)].astype(np.uint8, copy=False)
    if valid.size == 0:
        return {"status": "no_data", "message": "AOI does not overlap valid A7-T prediction pixels",
                "geometry": mapping(geom_wgs84), "crs": {"input": "EPSG:4326", "analysis": "EPSG:32647"}}
    palette = json.loads(PALETTE_PATH.read_text(encoding="utf-8"))["classes"]
    pixel_area = float(prediction_meta["pixel_area_m2"])
    classes = []
    for numeric in range(1, 8):
        code = f"R{numeric}"
        count = int(np.count_nonzero(valid == numeric))
        area_m2 = count * pixel_area
        classes.append({"class_id": code, "class_name": palette[code]["name"],
                        "class_name_th": CLASS_NAMES_TH[code], "color": palette[code]["color"],
                        "pixels": count, "percentage": count / valid.size * 100.0,
                        "area_m2": area_m2, "area_rai": area_m2 / 1600.0})
    dominant = max(classes, key=lambda item: item["pixels"])
    aoi_id = str(uuid.uuid4())
    ndvi = _continuous_stats(NDVI_PATH, geom_utm)
    ndwi = _continuous_stats(NDWI_PATH, geom_utm)
    dem = _continuous_stats(DEM_PATH, geom_utm)
    found = [item["class_id"] for item in classes if item["pixels"]]
    trace = [
        {"tool": "calculate_aoi_area", "status": "success", "source": "user GeoJSON", "crs": "EPSG:32647", "result": f"{geom_utm.area:.2f} m²"},
        {"tool": "get_class_distribution", "status": "success", "source": "A7-T final categorical prediction", "crs": "EPSG:32647", "result": f"{len(found)} classes; {valid.size} valid pixels"},
        {"tool": "get_ndvi_zonal_stats", "status": "success" if ndvi["available"] else "no_data", "source": "NDVI canonical raster", "crs": "EPSG:32647", "result": f"{ndvi['count']} pixels"},
        {"tool": "get_ndwi_zonal_stats", "status": "success" if ndwi["available"] else "no_data", "source": "NDWI canonical raster", "crs": "EPSG:32647", "result": f"{ndwi['count']} pixels"},
        {"tool": "get_dem_zonal_stats", "status": "success" if dem["available"] else "no_data", "source": "Copernicus COP30 DSM", "crs": "EPSG:32647", "result": f"{dem['count']} pixels"},
    ]
    summary = (f"พื้นที่ที่เลือกมีขนาด {geom_utm.area / 1600.0:,.2f} ไร่ "
               f"โดยคลาสเด่นคือ {dominant['class_id']} {dominant['class_name_th']} "
               f"คิดเป็น {dominant['percentage']:.1f}% ของพิกเซล A7-T ที่มีข้อมูล")
    if ndvi["available"]:
        summary += f" ค่า NDVI เฉลี่ย {ndvi['mean']:.3f}"
    if dem["available"]:
        summary += f" และระดับความสูงจาก COP30 DSM อยู่ระหว่าง {dem['min']:.1f}–{dem['max']:.1f} เมตร"
    return {
        "status": "success", "aoi_id": aoi_id, "geometry": mapping(geom_wgs84),
        "geometry_vertices": vertices, "area_m2": float(geom_utm.area), "area_rai": float(geom_utm.area / 1600.0),
        "class_pixel_area_m2": pixel_area, "valid_class_pixels": int(valid.size), "classes": classes,
        "dominant_class": dominant, "ndvi": ndvi, "ndwi": ndwi, "elevation": dem,
        "summary": summary, "summary_mode": "deterministic GIS-grounded fallback",
        "crs": {"input": "EPSG:4326", "analysis": "EPSG:32647"},
        "sources": {"classification": str(PREDICTION), "ndvi": str(NDVI_PATH), "ndwi": str(NDWI_PATH),
                    "dem": str(DEM_PATH), "dem_type": "Copernicus COP30 DSM (not bare-earth DTM)"},
        "execution_trace": trace,
        "reliability": {"context": reliability_context(),
                        "class_metrics": {code: reliability_context(code)["class_metric_context"] for code in found}},
    }


def render_aoi_preview(geometry: dict[str, Any]) -> tuple[bytes, list[float]]:
    _, geom_utm, _ = validate_geometry(geometry)
    with rasterio.open(PREDICTION) as source:
        left, bottom, right, top = geom_utm.bounds
        requested = from_bounds(left, bottom, right, top, source.transform).round_offsets().round_lengths()
        try:
            window = requested.intersection(rasterio.windows.Window(0, 0, source.width, source.height))
        except Exception as exc:
            raise AoiValidationError("AOI does not overlap A7-T prediction") from exc
        values = source.read(1, window=window)
        transform = source.window_transform(window)
        from rasterio.features import geometry_mask
        inside = geometry_mask([mapping(geom_utm)], out_shape=values.shape, transform=transform, invert=True, all_touched=False)
        palette = json.loads(PALETTE_PATH.read_text(encoding="utf-8"))["classes"]
        rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
        for numeric in range(1, 8):
            color = palette[f"R{numeric}"]["color"].lstrip("#")
            hit = (values == numeric) & inside
            rgba[hit, :3] = tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))
            rgba[hit, 3] = 255
        image = Image.fromarray(rgba, mode="RGBA")
        if max(image.size) > 2048:
            scale = 2048 / max(image.size)
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.NEAREST)
        stream = BytesIO(); image.save(stream, format="PNG", optimize=True)
        wb = window_bounds(window, source.transform)
        west, south = TO_WGS84.transform(wb[0], wb[1]); east, north = TO_WGS84.transform(wb[2], wb[3])
        return stream.getvalue(), [min(west, east), min(south, north), max(west, east), max(south, north)]
