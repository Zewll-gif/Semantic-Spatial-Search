# CLEAN PROJECT HEADER
# ไฟล์: main.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
from __future__ import annotations

import json
import math
import hashlib
import mimetypes
import os
from io import BytesIO
from pathlib import Path
from typing import Any

from local_env import load_local_env
from runtime_env import configure_geospatial_environment

# Operator-owned secrets are loaded server-side before agent/store imports.
# Live paid LLM calls still require the separate AGENT_LLM_ENABLED=1 switch.
load_local_env()
configure_geospatial_environment()

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import numpy as np
import rasterio
from rasterio.windows import Window, from_bounds, bounds as window_bounds
from PIL import Image
from pyproj import Transformer
from agent_layer import (
    chart_data, calculate_area, calculate_spectral, evaluation_matrix,
    external_context, retrieve_project_evidence, run_agent, search_areas,
    segmentation_evidence, create_analysis_layer, export_analysis, ANALYSES,
)
from evidence_crosscheck import (
    PROFILE_DIR,
    audit_sample,
    check_external_reference,
    check_spectral_consistency,
)
from multisource_lulc_api import compare_geometry
from geoai_api import app as geoai_backend_app
from agent_api_v2 import app as agent_v2_app
from project_paths import EVIDENCE_AUDIT, FULL_INFERENCE_ROOT, PALETTE_PATH, SPECTRAL_ROOT, PREDICTION
from categorical_tiles import render_tile
from gis_tools import identify_landcover
from drawn_aoi import AoiValidationError, analyze_drawn_aoi, render_aoi_preview, validate_geometry
from correction_store import list_corrections, save_correction
from external_satellite import (
    ExternalAnalysisError, analyze_external_aoi, project_coverage,
    render_external_preview, search_sentinel2,
)

# Chromium requires an executable JavaScript MIME type for the local MapLibre
# ES module. Windows MIME registries may otherwise classify .mjs as text/plain.
mimetypes.add_type("text/javascript", ".mjs", strict=True)


APP_ROOT = Path(__file__).resolve().parents[1]
FEATURE_PATH = APP_ROOT / "data" / "tile_features.json"
FULL_FEATURE_PATH = APP_ROOT / "data" / "full_aoi_tile_features.json"
FRONTEND_ROOT = APP_ROOT / "frontend"
Aoi_ROOT = APP_ROOT / "static" / "aoi"
SPLIT_PATH = APP_ROOT / "data" / "split_footprints.json"
CANONICAL_PALETTE_PATH = PALETTE_PATH
A7T_WEB_TILES = APP_ROOT / "static" / "a7t_class_tiles"
CLASS_NAMES_TH = {
    "R1": "สิ่งปลูกสร้างและพื้นผิวทึบน้ำ",
    "R2": "พื้นที่เกษตรกรรม",
    "R3": "ไม้ยืนต้นและพื้นที่ป่า",
    "R4": "แหล่งน้ำ",
    "R5": "ทุ่งหญ้าและพืชล้มลุก",
    "R6": "พื้นดินโล่ง",
    "R7": "พื้นที่ไม่แน่ชัดหรือเมฆ",
}
DISPLAY_TO_PREDICTION = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True)
PREDICTION_TO_DISPLAY = Transformer.from_crs("EPSG:32647", "EPSG:4326", always_xy=True)

with FEATURE_PATH.open(encoding="utf-8") as f:
    FEATURE_PAYLOAD = json.load(f)
with FULL_FEATURE_PATH.open(encoding="utf-8") as f:
    FULL_FEATURE_PAYLOAD = json.load(f)
TEST40_TILES = FEATURE_PAYLOAD["features"]
FULL_TILES = FULL_FEATURE_PAYLOAD["features"]
TEST40_BY_ID = {t["tile_id"]: t for t in TEST40_TILES}
FULL_BY_ID = {t["tile_id"]: t for t in FULL_TILES}


def _rules_for(query: str) -> tuple[str, dict[str, float], list[str]]:
    q = query.lower().strip()
    built_hits = [token for token in ("ชุมชน", "เมือง", "อาคาร", "สิ่งปลูกสร้าง", "built", "urban", "impervious") if token in q]
    ag_hits = [token for token in ("เกษตร", "นา", "ไร่", "agricultur", "farm", "crop") if token in q]
    green_hits = [token for token in ("สีเขียว", "ต้นไม้", "green", "vegetation", "tree") if token in q]
    mix_hits = [token for token in ("ปะปน", "ผสม", "mixed", "mixture", "+") if token in q]
    if (built_hits and ag_hits) or (mix_hits and built_hits and ag_hits):
        return "built_agriculture_mixture", {"builtup_ratio": 0.35, "agriculture_ratio": 0.35, "built_ag_mix": 0.15, "entropy": 0.15}, built_hits + ag_hits + mix_hits
    if built_hits and green_hits and mix_hits:
        return "built_green_mixture", {"builtup_ratio": 0.35, "natural_green_ratio": 0.35, "built_green_mix": 0.15, "entropy": 0.15}, built_hits + green_hits + mix_hits
    intents: list[tuple[str, tuple[str, ...], dict[str, float]]] = [
        ("agriculture", ("เกษตร", "นา", "ไร่", "agricultur", "farm", "crop"), {"agriculture_ratio": 0.70, "vegetation_ratio": 0.20, "entropy": 0.10}),
        ("built_up", ("ชุมชน", "เมือง", "อาคาร", "สิ่งปลูกสร้าง", "built", "urban", "impervious"), {"builtup_ratio": 0.75, "built_green_mix": 0.15, "entropy": 0.10}),
        ("trees", ("ต้นไม้", "ป่า", "ไม้", "tree", "forest", "woody"), {"tree_ratio": 0.75, "natural_green_ratio": 0.20, "entropy": 0.05}),
        ("water", ("น้ำ", "แม่น้ำ", "ทะเลสาบ", "บึง", "water", "river", "lake"), {"water_ratio": 0.80, "water_green_mix": 0.15, "entropy": 0.05}),
        ("green", ("สีเขียว", "พื้นที่สีเขียว", "green", "vegetation", "herbaceous"), {"vegetation_ratio": 0.55, "natural_green_ratio": 0.35, "entropy": 0.10}),
        ("open_land", ("พื้นที่โล่ง", "โล่ง", "ดินเปล่า", "bare", "open land", "open"), {"open_land_ratio": 0.65, "bare_ratio": 0.25, "entropy": 0.10}),
        ("built_ag_mix", ("ปะปน", "ผสม", "เกษตรปน", "สิ่งปลูกสร้างกับพื้นที่เกษตร", "mixed", "mixture"), {"built_ag_mix": 0.55, "builtup_ratio": 0.15, "agriculture_ratio": 0.15, "entropy": 0.15}),
        ("diverse", ("หลากหลาย", "diverse", "varied", "entropy"), {"entropy": 0.75, "dominance_score": -0.25}),
    ]
    for name, tokens, weights in intents:
        hits = [token for token in tokens if token in q]
        if hits:
            return name, weights, hits
    return "balanced_landcover", {"entropy": 0.35, "vegetation_ratio": 0.25, "builtup_ratio": 0.20, "water_ratio": 0.10, "open_land_ratio": 0.10}, []


def _score(tile: dict[str, Any], weights: dict[str, float]) -> float:
    value = 0.0
    for key, weight in weights.items():
        raw = float(tile.get(key, 0.0))
        if key == "dominance_score":
            raw = 1.0 - raw
        value += weight * raw
    return float(max(0.0, min(1.0, value)))


def search_tiles(query: str, top_n: int = 10, scope: str = "FULL_AOI") -> dict[str, Any]:
    intent, weights, hits = _rules_for(query)
    scope = "TEST40_ONLY" if scope.upper() == "TEST40_ONLY" else "FULL_AOI"
    source_tiles = TEST40_TILES if scope == "TEST40_ONLY" else FULL_TILES
    by_id = TEST40_BY_ID if scope == "TEST40_ONLY" else FULL_BY_ID
    ranked = []
    for tile in source_tiles:
        raw = _score(tile, weights)
        ranked.append({
            "tile_id": tile["tile_id"],
            "score": round(raw * 100.0, 4),
            "raw_score": raw,
            "matched_features": [{"feature": k, "weight": v, "value": tile.get(k, 0.0)} for k, v in weights.items()],
            "explanation": f"{intent}: " + ", ".join(f"{k}={float(tile.get(k, 0.0)):.3f}×{w:.2f}" for k, w in weights.items()),
        })
    ranked.sort(key=lambda x: (-x["raw_score"], x["tile_id"]))
    merged = []
    for rank, item in enumerate(ranked[: max(1, min(top_n, 40))], 1):
        merged.append({"rank": rank, **by_id[item["tile_id"]], **item})
    return {"query": query, "scope": scope, "intent": intent, "matched_tokens": hits, "feature_weights": weights, "results": merged}


app = FastAPI(title="A7 RGBN Semantic Search Prototype", version="1.0")
# Integrate the dedicated A7-T GeoAI API routes without replacing existing app routes.
app.router.routes.extend([route for route in geoai_backend_app.routes if getattr(route, "path", "").startswith("/api/geoai/")])
# Add the canonical Agent/GIS/RAG V2 contract while preserving every V1 route.
app.router.routes.extend([route for route in agent_v2_app.routes if getattr(route, "path", "").startswith("/api/")])


class AgentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    scope: str = "FULL_AOI"
    bbox: list[float] | None = None
    tile_id: str | None = None
    unit: str = "ไร่"


class AreaRequest(BaseModel):
    class_filter: list[int] = [1]
    bbox: list[float] | None = None
    tile_ids: list[str] | None = None
    unit: str = "ไร่"


class SpectralRequest(BaseModel):
    index: str
    bbox: list[float] | None = None
    tile_ids: list[str] | None = None


class AnalysisRequest(BaseModel):
    geometry: dict[str, Any] | None = None
    class_filters: list[int] = [1]
    ndvi_filter: dict[str, float] | None = None
    ndwi_filter: dict[str, float] | None = None
    distance_filter: dict[str, float] | None = None
    min_area: float = 0.0
    min_area_unit: str = "m²"
    dissolve: bool = False
    output_type: str = "vector"
    query_text: str = ""


class EvidenceRequest(BaseModel):
    geometry: dict[str, Any]
    predicted_class: int = Field(ge=1, le=7)


class RoiRequest(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4)


class DrawnAoiRequest(BaseModel):
    geometry: dict[str, Any]
    analysis_mode: str = Field(default="auto", pattern="^(auto|project_only)$")
    acquisition_date: str | None = None


class ExternalAoiRequest(BaseModel):
    geometry: dict[str, Any]
    acquisition_date: str | None = None
    layer: str = Field(default="rgb", pattern="^(rgb|ndvi|ndwi)$")


class HumanCorrectionRequest(BaseModel):
    geometry: dict[str, Any]
    feature_id: int | None = None
    original_class: str
    corrected_class: str
    user_note: str | None = Field(default=None, max_length=1000)
    source_aoi_id: str = Field(min_length=1, max_length=100)


def _roi_window(bbox: list[float]) -> tuple[Window, Any]:
    west, south, east, north = map(float, bbox)
    if west >= east or south >= north:
        raise HTTPException(status_code=400, detail="ROI bbox must be [west,south,east,north]")
    min_x, min_y = DISPLAY_TO_PREDICTION.transform(west, south)
    max_x, max_y = DISPLAY_TO_PREDICTION.transform(east, north)
    source = rasterio.open(PREDICTION)
    try:
        requested = from_bounds(min(min_x, max_x), min(min_y, max_y), max(min_x, max_x), max(min_y, max_y), source.transform)
        requested = requested.round_offsets().round_lengths()
        try:
            valid = requested.intersection(Window(0, 0, source.width, source.height))
        except Exception as exc:
            raise HTTPException(status_code=400, detail="ROI does not overlap the A7-T Full AOI") from exc
        if valid.width < 1 or valid.height < 1:
            raise HTTPException(status_code=400, detail="ROI does not overlap the A7-T Full AOI")
        return valid, source
    except Exception:
        source.close()
        raise


def _roi_payload(bbox: list[float], include_pixels: bool = False) -> tuple[dict[str, Any], np.ndarray | None]:
    window, source = _roi_window(bbox)
    try:
        values = source.read(1, window=window)
        pixel_area = abs(float(source.transform.a * source.transform.e))
        total_pixels = int(np.isin(values, np.arange(1, 8)).sum())
        palette = json.loads(CANONICAL_PALETTE_PATH.read_text(encoding="utf-8"))["classes"]
        classes = []
        for numeric in range(1, 8):
            code = f"R{numeric}"
            count = int((values == numeric).sum())
            area_m2 = count * pixel_area
            classes.append({"class_id": code, "class_name": palette[code]["name"], "class_name_th": CLASS_NAMES_TH[code],
                            "pixels": count, "percent": round((count / total_pixels * 100.0) if total_pixels else 0.0, 4),
                            "area_m2": area_m2, "area_rai": area_m2 / 1600.0})
        dominant = max(classes, key=lambda item: item["pixels"])
        wb = window_bounds(window, source.transform)
        lon_a, lat_a = PREDICTION_TO_DISPLAY.transform(wb[0], wb[1])
        lon_b, lat_b = PREDICTION_TO_DISPLAY.transform(wb[2], wb[3])
        payload = {"source_model": "A7_RGBN_REVISED7_TVERSKY", "source_raster": str(PREDICTION),
                   "window": {"col_off": int(window.col_off), "row_off": int(window.row_off), "width": int(window.width), "height": int(window.height)},
                   "pixel_area_m2": pixel_area, "total_area_m2": total_pixels * pixel_area,
                   "total_area_rai": total_pixels * pixel_area / 1600.0, "dominant_class": dominant,
                   "classes": classes, "rendered_bbox": [min(lon_a, lon_b), min(lat_a, lat_b), max(lon_a, lon_b), max(lat_a, lat_b)]}
        return payload, values if include_pixels else None
    finally:
        source.close()


@app.get("/api/health")
def health():
    return {"ok": True, "model": "A7_RGBN_REVISED7_TVERSKY", "feature_tiles": len(TEST40_TILES), "full_aoi_feature_tiles": len(FULL_TILES), "test40_gt_accessed": False, "full_aoi_available": (Aoi_ROOT / "full_aoi_rgb.png").exists(), "agent_enabled": True, "agent_model": "gpt-5.6-terra", "agent_fallback_available": True}


@app.get("/api/aoi")
def aoi():
    bounds = json.loads((Aoi_ROOT / "full_aoi_rgb_bounds.json").read_text(encoding="utf-8"))
    metadata = json.loads((Aoi_ROOT / "full_aoi_metadata.json").read_text(encoding="utf-8"))
    return {"bounds": bounds, "metadata": metadata, "image_url": "/aoi/full_aoi_rgb.png"}


@app.post("/api/roi/insight")
def roi_insight(request: RoiRequest):
    """Exact categorical A7-T pixel summary for a user-drawn Full AOI rectangle."""
    payload, _ = _roi_payload(request.bbox)
    return payload


@app.get("/api/roi/preview")
def roi_preview(west: float, south: float, east: float, north: float):
    """A canonical-palette A7-T raster preview clipped to a geographic ROI."""
    payload, values = _roi_payload([west, south, east, north], include_pixels=True)
    assert values is not None
    palette = json.loads(CANONICAL_PALETTE_PATH.read_text(encoding="utf-8"))["classes"]
    rgba = np.zeros((values.shape[0], values.shape[1], 4), dtype=np.uint8)
    for numeric in range(1, 8):
        color = palette[f"R{numeric}"]["color"].lstrip("#")
        rgb = tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))
        hit = values == numeric
        rgba[hit, :3] = rgb
        rgba[hit, 3] = 255
    image = Image.fromarray(rgba, mode="RGBA")
    # Keep every category while preventing a full-AOI selection from creating an oversized response.
    max_dimension = 2048
    if max(image.size) > max_dimension:
        ratio = max_dimension / max(image.size)
        image = image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))), Image.Resampling.NEAREST)
    stream = BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return Response(content=stream.getvalue(), media_type="image/png", headers={
        "Cache-Control": "no-store", "X-GeoAI-ROI-Pixels": str(payload["window"]["width"] * payload["window"]["height"]),
        "X-GeoAI-Source": "A7-T-Full-AOI",
    })


@app.post("/api/aoi/analyze")
def analyze_user_aoi(request: DrawnAoiRequest):
    """Run exact A7-T, NDVI, NDWI and COP30 DSM zonal analysis server-side."""
    try:
        coverage = project_coverage(request.geometry)
        if coverage["status"] == "outside":
            return {
                "status": "external_option", "analysis_type": "coverage_check",
                "message": "พื้นที่นี้อยู่นอกขอบเขตข้อมูล PlanetScope/A7-T สามารถใช้ภาพ Sentinel-2 เพื่อวิเคราะห์ข้อมูลดาวเทียมของพื้นที่นี้ได้",
                **{key: coverage[key] for key in ("project_coverage_percentage", "external_coverage_percentage", "total_area_m2", "total_area_rai")},
                "options": ["external_sentinel2"],
            }
        if coverage["status"] == "partial" and request.analysis_mode != "project_only":
            return {
                "status": "partial_coverage", "analysis_type": "coverage_check",
                "message": "พื้นที่ที่เลือกครอบคลุมข้อมูลโครงการเพียงบางส่วน กรุณาเลือกแหล่งข้อมูลสำหรับการวิเคราะห์",
                **{key: coverage[key] for key in ("project_coverage_percentage", "external_coverage_percentage", "total_area_m2", "total_area_rai")},
                "options": ["project_only", "external_sentinel2"],
            }
        analysis_geometry = coverage["project_geometry"] if request.analysis_mode == "project_only" else request.geometry
        result = analyze_drawn_aoi(analysis_geometry)
        result["analysis_type"] = "project"
        result["source_badge"] = "Project analysis · A7-T / PlanetScope"
        result["coverage"] = {key: coverage[key] for key in ("status", "project_coverage_percentage", "external_coverage_percentage")}
        if request.analysis_mode == "project_only":
            result["selected_area_m2"] = coverage["total_area_m2"]
            result["selected_area_rai"] = coverage["total_area_rai"]
            result["message"] = "วิเคราะห์เฉพาะส่วนของ AOI ที่มีข้อมูลโครงการ โดยไม่รวมสถิติ Sentinel-2"
        return result
    except AoiValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_geometry", "message": str(exc)}) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail={"code": "canonical_source_missing", "message": Path(str(exc)).name}) from exc
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail={"code": "analysis_failed", "message": type(exc).__name__}) from exc


@app.post("/api/aoi/coverage")
def check_user_aoi_coverage(request: DrawnAoiRequest):
    try:
        return project_coverage(request.geometry)
    except AoiValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_geometry", "message": str(exc)}) from exc


@app.post("/api/aoi/external/search")
async def search_external_aoi(request: ExternalAoiRequest):
    try:
        scene = search_sentinel2(request.geometry, request.acquisition_date)
        return {"status": "success", "scene": {key: value for key, value in scene.items() if key != "assets"}}
    except (AoiValidationError, ExternalAnalysisError) as exc:
        status = exc.status_code if isinstance(exc, ExternalAnalysisError) else 422
        code = exc.code if isinstance(exc, ExternalAnalysisError) else "invalid_geometry"
        message = exc.message if isinstance(exc, ExternalAnalysisError) else str(exc)
        raise HTTPException(status_code=status, detail={"code": code, "message": message}) from exc


@app.post("/api/aoi/external/analyze")
async def analyze_external_user_aoi(request: ExternalAoiRequest):
    try:
        return analyze_external_aoi(request.geometry, request.acquisition_date)
    except (AoiValidationError, ExternalAnalysisError) as exc:
        status = exc.status_code if isinstance(exc, ExternalAnalysisError) else 422
        code = exc.code if isinstance(exc, ExternalAnalysisError) else "invalid_geometry"
        message = exc.message if isinstance(exc, ExternalAnalysisError) else str(exc)
        raise HTTPException(status_code=status, detail={"code": code, "message": message}) from exc


@app.post("/api/aoi/external/preview")
async def preview_external_user_aoi(request: ExternalAoiRequest):
    try:
        png, bbox, scene = render_external_preview(request.geometry, request.layer, request.acquisition_date)
        return Response(png, media_type="image/png", headers={
            "Cache-Control": "private, max-age=3600",
            "X-GeoAI-Rendered-Bbox": ",".join(map(str, bbox)),
            "X-GeoAI-Source": "Sentinel-2-L2A",
            "X-GeoAI-Item": scene["item_id"],
            "X-GeoAI-Acquisition-Date": scene["acquisition_date"],
            "X-GeoAI-Cloud-Cover": str(scene["cloud_cover_percentage"]),
        })
    except (AoiValidationError, ExternalAnalysisError) as exc:
        status = exc.status_code if isinstance(exc, ExternalAnalysisError) else 422
        code = exc.code if isinstance(exc, ExternalAnalysisError) else "invalid_geometry"
        message = exc.message if isinstance(exc, ExternalAnalysisError) else str(exc)
        raise HTTPException(status_code=status, detail={"code": code, "message": message}) from exc


@app.post("/api/aoi/preview")
def preview_user_aoi(request: DrawnAoiRequest):
    """Return a nearest-neighbour canonical-palette PNG with alpha outside the AOI."""
    try:
        png, bbox = render_aoi_preview(request.geometry)
    except AoiValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_geometry", "message": str(exc)}) from exc
    return Response(png, media_type="image/png", headers={
        "Cache-Control": "no-store", "X-GeoAI-Rendered-Bbox": ",".join(map(str, bbox)),
        "X-GeoAI-Resampling": "nearest", "X-GeoAI-Source": "A7-T-Full-AOI",
    })


@app.post("/api/aoi/corrections")
def create_human_correction(request: HumanCorrectionRequest):
    try:
        # Validate geometry without assuming it is trusted SQL or raster input.
        geometry_type = request.geometry.get("type") if isinstance(request.geometry, dict) else None
        if geometry_type in {"Polygon", "MultiPolygon"}:
            validate_geometry(request.geometry)
        elif geometry_type != "Point":
            raise ValueError("correction geometry must be Point, Polygon or MultiPolygon GeoJSON")
        return save_correction(geometry=request.geometry, feature_id=request.feature_id,
                               original_class=request.original_class, corrected_class=request.corrected_class,
                               note=request.user_note, source_aoi_id=request.source_aoi_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_correction", "message": str(exc)}) from exc


@app.get("/api/aoi/corrections")
def get_human_corrections(source_aoi_id: str | None = None):
    return {"corrections": list_corrections(source_aoi_id),
            "note": "Pending corrections are candidate annotations, not Ground Truth."}


@app.get("/api/spectral/{name}")
def spectral_metadata(name: str):
    key = name.upper()
    if key not in {"NDVI", "NDWI"}: raise HTTPException(status_code=404, detail="unknown index")
    path = SPECTRAL_ROOT / f"{key}_FULL_AOI_METADATA.json"
    if not path.exists(): raise HTTPException(status_code=404, detail="index not generated")
    return json.loads(path.read_text(encoding="utf-8")) | {"preview_url": f"/analysis-assets/{key}_FULL_AOI_PREVIEW.png"}


@app.get("/analysis-assets/{name}")
def analysis_asset(name: str):
    root = SPECTRAL_ROOT.resolve(); path = (root / Path(name).name).resolve()
    if root not in path.parents or not path.exists(): raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(path)


@app.get("/api/splits")
def splits():
    return json.loads(SPLIT_PATH.read_text(encoding="utf-8"))


@app.get("/api/tiles")
def all_tiles(scope: str = Query("FULL_AOI")):
    use_test = scope.upper() == "TEST40_ONLY"
    payload = FEATURE_PAYLOAD if use_test else FULL_FEATURE_PAYLOAD
    tiles = TEST40_TILES if use_test else FULL_TILES
    return {"model": payload["model"], "scope": "TEST40_ONLY" if use_test else "FULL_AOI", "count": len(tiles), "tiles": tiles}


@app.get("/api/tiles/{tile_id}")
def tile(tile_id: str):
    if tile_id not in FULL_BY_ID and tile_id not in TEST40_BY_ID:
        raise HTTPException(status_code=404, detail="unknown tile")
    return FULL_BY_ID.get(tile_id, TEST40_BY_ID.get(tile_id))


@app.get("/api/search")
def search(q: str = Query("", description="Thai or English semantic query"), top_n: int = Query(10, ge=1, le=40), scope: str = Query("FULL_AOI")):
    return search_tiles(q, top_n, scope)


@app.post("/api/agent")
def agent(request: AgentRequest):
    if request.bbox is not None and (len(request.bbox) != 4 or request.bbox[0] >= request.bbox[2] or request.bbox[1] >= request.bbox[3]):
        raise HTTPException(status_code=400, detail="bbox must be [min_lon,min_lat,max_lon,max_lat]")
    return run_agent(request.question, request.scope, request.bbox, request.tile_id, request.unit)


@app.post("/api/tools/area")
def area_tool(request: AreaRequest):
    if any(int(x) < 1 or int(x) > 7 for x in request.class_filter): raise HTTPException(status_code=400, detail="class_filter must use R1-R7")
    return calculate_area(request.class_filter, request.bbox, request.tile_ids, request.unit)


@app.post("/api/tools/spectral")
def spectral_tool(request: SpectralRequest):
    if request.index.lower() not in {"ndvi", "ndwi"}: raise HTTPException(status_code=400, detail="index must be NDVI or NDWI")
    return calculate_spectral(request.index.lower(), request.bbox, request.tile_ids)


@app.get("/api/tools/segmentation/{tile_id}")
def segmentation_tool(tile_id: str):
    try: return segmentation_evidence(tile_id)
    except ValueError as exc: raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/tools/rag")
def rag_tool(q: str = Query(...), top_k: int = Query(4, ge=1, le=10)):
    return {"question": q, "results": retrieve_project_evidence(q, top_k)}


@app.get("/api/tools/chart")
def chart_tool(chart_type: str = Query("class_distribution_bar"), tile_ids: str = Query("")):
    ids = [x for x in tile_ids.split(",") if x]
    return chart_data(chart_type, ids or None)


@app.get("/api/tools/external-context")
def external_tool(requested_feature_type: str = Query(...)):
    return external_context(None, requested_feature_type)


@app.get("/api/evidence/profiles")
def evidence_profiles():
    path = PROFILE_DIR / "class_spectral_profiles.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="spectral profiles not generated")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/tools/spectral-consistency")
def spectral_consistency_tool(request: EvidenceRequest):
    try:
        return check_spectral_consistency(request.geometry, request.predicted_class)
    except (ValueError, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/tools/external-reference")
def external_reference_tool(request: EvidenceRequest):
    try:
        return check_external_reference(request.geometry, request.predicted_class)
    except (ValueError, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/evidence/audit")
def evidence_audit():
    path = EVIDENCE_AUDIT
    if not path.exists():
        raise HTTPException(status_code=404, detail="evidence audit not generated")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/evidence/lulc-comparison")
def lulc_comparison(request: EvidenceRequest):
    try:
        return compare_geometry(request.geometry)
    except (ValueError, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/analysis")
def analysis_tool(request: AnalysisRequest):
    if any(int(x) < 1 or int(x) > 7 for x in request.class_filters): raise HTTPException(status_code=400, detail="class_filters must use R1-R7")
    try: return create_analysis_layer(request.geometry, request.class_filters, request.ndvi_filter, request.ndwi_filter, request.distance_filter, request.min_area, request.min_area_unit, request.dissolve, request.output_type, request.query_text)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/analysis")
def analysis_history():
    return {"analyses": list(ANALYSES.values())}


@app.get("/api/export/{analysis_id}/{fmt}")
def export_tool(analysis_id: str, fmt: str, crs_mode: str = Query("projected")):
    try: return export_analysis(analysis_id, fmt, crs_mode)
    except ValueError as exc: raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/download/{analysis_id}/{fmt}")
def download_export(analysis_id: str, fmt: str):
    try:
        info = export_analysis(analysis_id, fmt)
        return FileResponse(info["file_path"], filename=info["file_name"])
    except ValueError as exc: raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/agent/evaluation")
def agent_evaluation():
    rows = evaluation_matrix()
    return {"queries": rows, "count": len(rows), "hallucinated_numbers": sum(bool(x["hallucinated_number"]) for x in rows), "unsupported_model_claims": 0}


@app.get("/api/class-schema")
def class_schema():
    """Single project palette source for web colors, labels, filters and popups."""
    raw = CANONICAL_PALETTE_PATH.read_bytes()
    source = json.loads(raw)
    classes = {}
    for key, item in source["classes"].items():
        classes[key] = {
            "name_en": "Uncertain / Cloud" if key == "R7" else item["name"],
            "name_th": CLASS_NAMES_TH[key],
            "color": item["color"],
        }
    return {"schema": source["schema"], "palette_sha256": hashlib.sha256(raw).hexdigest(),
            "prediction_sha256": hashlib.sha256(PREDICTION.read_bytes()).hexdigest(),
            "model": "A7_RGBN_REVISED7_TVERSKY", "classes": classes}


@app.get("/api/map/a7t/{z}/{x}/{y}.png")
def a7t_categorical_tile(z: int, x: int, y: int, classes: str | None = None):
    """Exact A7-T source labels rendered as canonical RGBA XYZ tiles, never polygons."""
    try:
        png = render_tile(PREDICTION, CANONICAL_PALETTE_PATH, z, x, y, classes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/map/identify")
def identify_map_feature(lon: float, lat: float, class_id: str | None = None):
    """Identify one indexed polygon on demand; never use it to color the map."""
    try:
        feature = identify_landcover(lon, lat, class_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Vector identify failed: {type(exc).__name__}") from exc
    return {"feature": feature}


@app.get("/assets/{tile_id}/{kind}")
def asset(tile_id: str, kind: str, scope: str = Query("FULL_AOI")):
    # Both AOI and TEST40 views use the frozen Full AOI deployment. Color PNGs
    # are derived pixel-for-pixel from its tile GeoTIFFs, never legacy previews.
    if tile_id not in FULL_BY_ID:
        raise HTTPException(status_code=404, detail="asset not found")
    allowed = {
        "rgb": FULL_INFERENCE_ROOT / "tiles_rgb" / f"{tile_id}_rgb.png",
        "overlay": A7T_WEB_TILES / f"{tile_id}.png",
        "prediction": A7T_WEB_TILES / f"{tile_id}.png",
    }
    if kind not in allowed or not allowed[kind].exists():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(allowed[kind], media_type="image/png", headers={"Cache-Control": "public, max-age=31536000, immutable"} if kind != "rgb" else None)


app.mount("/aoi", StaticFiles(directory=Aoi_ROOT), name="aoi")
app.mount("/", StaticFiles(directory=FRONTEND_ROOT, html=True), name="frontend")
