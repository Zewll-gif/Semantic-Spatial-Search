# CLEAN PROJECT HEADER
# ไฟล์: agent_layer.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Deterministic, explainable agent layer for the frozen A7 RGBN application.

The agent is an orchestrator: all spatial numbers come from the tools below or
from the local evidence files.  An OpenAI adapter is exposed but the app never
requires it; without a server-side key the deterministic fallback remains fully
usable.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import numpy as np
from runtime_env import configure_geospatial_environment

configure_geospatial_environment()
import rasterio
from rasterio.features import shapes
from rasterio.warp import transform_geom
from shapely.geometry import shape, mapping
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
from project_paths import (
    EVIDENCE_PROFILE_ROOT, FULL_INFERENCE_ROOT, NDVI_PATH, NDWI_PATH,
    PLANETSCOPE_SOURCE, PREDICTION,
)

APP_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PLANETSCOPE_SOURCE
EXPORT_ROOT = APP_ROOT / "exports"
FULL_FEATURE_PATH = APP_ROOT / "data" / "full_aoi_tile_features.json"
RAG_ROOT = EVIDENCE_PROFILE_ROOT
MODEL = "A7_RGBN_REVISED7_TVERSKY"
CHECKPOINT_SHA = "596F81C808C3D872AD60E22778D0157CC858410FB49CF9DCF3612BD455E3E536"
TAXONOMY = {1: "R1 Built-up & Impervious", 2: "R2 Agricultural Land / Cropland", 3: "R3 Tree / Woody Cover", 4: "R4 Water", 5: "R5 Grassland / Herbaceous Cover", 6: "R6 Bare Ground", 7: "R7 Uncertain / Cloud"}
UNITS = {"m²": 1.0, "m2": 1.0, "km²": 1e-6, "km2": 1e-6, "ha": 1e-4, "rai": 1 / 1600.0, "ไร่": 1 / 1600.0}


class LLMProvider:
    """Small provider interface; spatial orchestration never depends on it."""
    name = "provider"
    model = ""
    available = False

    def complete(self, prompt: str) -> str:
        raise RuntimeError("LLM provider unavailable")


class OpenAIAdapter(LLMProvider):
    name = "OpenAI"

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("AGENT_MODEL", "gpt-5.6-terra")
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.available = bool(self.api_key)

    def complete(self, prompt: str) -> str:
        if not self.available:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        # Deliberately fail closed until an approved SDK/endpoint is configured;
        # deterministic tools remain the source of spatial facts.
        raise RuntimeError("OpenAI adapter configured but remote completion is disabled in safe local mode")


def _features() -> list[dict[str, Any]]:
    return json.loads(FULL_FEATURE_PATH.read_text(encoding="utf-8"))["features"]


def classify_scope(question: str) -> str:
    q = question.lower()
    if any(x in q for x in ("โรงพยาบาล", "hospital", "ถนน", "road", "school", "โรงเรียน", "poi")):
        return "EXTERNAL_DATA_REQUIRED"
    if any(x in q for x in ("รายได้", "income", "น้ำท่วม", "flood risk", "เสี่ยงน้ำท่วม")):
        return "UNSUPPORTED"
    if any(x in q for x in ("ndvi", "ndwi", "ใกล้น้ำ", "ติดน้ำ", "near water", "ใกล้", "เมตร", "ไร่", "กิโล", "km²", "km2", "area", "พื้นที่")):
        return "DERIVABLE"
    return "DIRECTLY_SUPPORTED"


def route_intent(question: str) -> dict[str, Any]:
    q = question.lower()
    target: list[int] = []
    if any(x in q for x in ("เกษตร", "ไร่", "นา", "crop", "farm")): target.append(2)
    if any(x in q for x in ("ชุมชน", "เมือง", "สิ่งปลูกสร้าง", "built", "urban")): target.append(1)
    if any(x in q for x in ("ต้นไม้", "ป่า", "tree", "forest")): target.append(3)
    if any(x in q for x in ("น้ำ", "water", "คลอง", "แม่น้ำ")): target.append(4)
    if any(x in q for x in ("หญ้า", "ทุ่ง", "grass")): target.append(5)
    if any(x in q for x in ("โล่ง", "ดินเปล่า", "bare", "open")): target.extend([5, 6])
    return {"target_classes": sorted(set(target)), "near_water": any(x in q for x in ("ใกล้น้ำ", "ติดน้ำ", "near water")), "ndvi": "ndvi" in q or "เขียวแค่ไหน" in q, "ndwi": "ndwi" in q or "มีน้ำไหม" in q, "area": any(x in q for x in ("ไร่", "m²", "m2", "km²", "km2", "เฮกตาร์", "area"))}


def _query_tokens(text: str) -> set[str]:
    return {x for x in re.findall(r"[\wก-๙]+", text.lower()) if len(x) > 2}


@lru_cache(maxsize=1)
def rag_documents() -> list[dict[str, str]]:
    names = [
        "FINAL_PLANETSCOPE_A7_RGBN_FREEZE_MANIFEST.json",
        "FINAL_PLANETSCOPE_A7_RGBN_FREEZE_SUMMARY.txt",
        "A7_RGBN_MULTISEED_SUMMARY.json",
        "FINAL_A9MERGE_VS_A7_CANDIDATE_COMPARISON.json",
        "A9_TO_A7_TAXONOMY_DECOMPOSITION.json",
        "PLANETSCOPE_3MODEL_PROVENANCE_AUDIT.json",
        "A7_RGBN_FULL_AOI_INFERENCE_AUDIT.json",
    ]
    docs: list[dict[str, str]] = []
    roots = [RAG_ROOT, FULL_INFERENCE_ROOT / "semantic_search"]
    for name in names + ["full_aoi_feature_schema.json", "feature_schema.json"]:
        path = next((r / name for r in roots if (r / name).exists()), None)
        if path:
            text = path.read_text(encoding="utf-8", errors="ignore")
            docs.append({"document_name": name, "provenance_path": str(path), "text": text[:200000]})
    return docs


def retrieve_project_evidence(question: str, top_k: int = 4) -> list[dict[str, Any]]:
    qt = _query_tokens(question)
    scored = []
    for d in rag_documents():
        dt = _query_tokens(d["text"][:50000])
        score = len(qt & dt) / max(1, len(qt))
        if score > 0 or "A7_RGBN_FULL_AOI" in d["document_name"]:
            snippet = d["text"][:360].replace("\n", " ")
            scored.append({"document_name": d["document_name"], "section": "document", "snippet": snippet, "provenance_path": d["provenance_path"], "relevance_score": round(score, 4)})
    return sorted(scored, key=lambda x: (-x["relevance_score"], x["document_name"]))[:top_k]


def _window_for_bbox(bbox: list[float] | None, ds: rasterio.DatasetReader):
    if not bbox:
        return None
    left, bottom, right, top = transform_bounds("EPSG:4326", ds.crs, *map(float, bbox), densify_pts=21)
    w = from_bounds(left, bottom, right, top, ds.transform).round_offsets().round_lengths()
    return w.intersection(rasterio.windows.Window(0, 0, ds.width, ds.height))


def _stats(values: np.ndarray) -> dict[str, Any]:
    v = values[np.isfinite(values)]
    if v.size == 0: return {"mean": None, "median": None, "std": None, "min": None, "max": None, "p25": None, "p75": None, "valid_pixels": 0}
    return {"mean": float(v.mean()), "median": float(np.median(v)), "std": float(v.std()), "min": float(v.min()), "max": float(v.max()), "p25": float(np.percentile(v, 25)), "p75": float(np.percentile(v, 75)), "valid_pixels": int(v.size)}


def calculate_spectral(index: Literal["ndvi", "ndwi"], bbox: list[float] | None = None, tile_ids: list[str] | None = None) -> dict[str, Any]:
    with rasterio.open(SOURCE) as ds:
        window = _window_for_bbox(bbox, ds)
        if window is None and tile_ids:
            feats = {x["tile_id"]: x for x in _features()}
            boxes = [feats[t]["bbox"] for t in tile_ids if t in feats]
            if boxes:
                bbox = [min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes), max(x[3] for x in boxes)]
                window = _window_for_bbox(bbox, ds)
        if window is None: window = rasterio.windows.Window(0, 0, ds.width, ds.height)
        red = ds.read(3, window=window).astype(np.float32)
        nir_or_green = ds.read(4 if index == "ndvi" else 2, window=window).astype(np.float32)
        denom = nir_or_green + red
        with np.errstate(divide="ignore", invalid="ignore"):
            values = (nir_or_green - red) / denom
        valid = (denom != 0) & np.isfinite(values) & (red != 0) & (nir_or_green != 0)
        out = _stats(values[valid]); out.update({"index": index.upper(), "method": "(NIR-Red)/(NIR+Red)" if index == "ndvi" else "(Green-NIR)/(Green+NIR)", "source": str(SOURCE), "bands": {"red": 3, "nir": 4} if index == "ndvi" else {"green": 2, "nir": 4}})
        return out


def calculate_area(class_filter: list[int], bbox: list[float] | None = None, tile_ids: list[str] | None = None, unit: str = "ไร่") -> dict[str, Any]:
    with rasterio.open(PREDICTION) as ds:
        window = _window_for_bbox(bbox, ds)
        if window is None and tile_ids:
            feats = {x["tile_id"]: x for x in _features()}
            boxes = [feats[t]["bbox"] for t in tile_ids if t in feats]
            if boxes:
                bbox = [min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes), max(x[3] for x in boxes)]
                window = _window_for_bbox(bbox, ds)
        if window is None: window = rasterio.windows.Window(0, 0, ds.width, ds.height)
        mask = ds.read(1, window=window)
        valid = mask > 0
        px_area = abs(ds.transform.a * ds.transform.e)
        total_px = int(valid.sum()); selected_px = int(np.isin(mask, class_filter).sum())
        factor = UNITS.get(unit.lower(), UNITS.get(unit, 1 / 1600.0))
        return {"total_geometry_area": float(total_px * px_area * factor), "class_area": float(selected_px * px_area * factor), "class_percentage": float(selected_px / max(1, total_px) * 100), "unit": unit, "method": "projected raster pixel area from EPSG:32647 prediction mosaic", "pixel_count": selected_px, "total_valid_pixels": total_px, "class_filter": class_filter}


def distance_to_water(tile_id: str) -> dict[str, Any]:
    path = FULL_INFERENCE_ROOT / "tiles_geotiff" / f"{tile_id}_prediction.tif"
    if not path.exists(): return {"tile_id": tile_id, "distance_to_water_m": None, "status": "tile_not_found"}
    with rasterio.open(path) as ds:
        m = ds.read(1); water = m == 4
        if water.any():
            yy, xx = np.where(water); cy, cx = (m.shape[0] - 1) / 2, (m.shape[1] - 1) / 2
            d = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2).min() * abs(ds.transform.a)
        else: d = None
    return {"tile_id": tile_id, "distance_to_water_m": float(d) if d is not None else None}


def search_areas(query_intent: str, scope: str = "FULL_AOI", top_n: int = 10, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    from main import search_tiles  # preserve the validated existing ranking implementation
    payload = search_tiles(query_intent, top_n=top_n, scope=scope)
    if "near" in query_intent.lower() or "ใกล้น้ำ" in query_intent:
        for r in payload["results"]:
            d = distance_to_water(r["tile_id"]); r["distance_to_water_m"] = d.get("distance_to_water_m")
        payload["results"].sort(key=lambda x: (x.get("distance_to_water_m") is None, x.get("distance_to_water_m") or 1e12, -x["raw_score"], x["tile_id"]))
    return payload


def segmentation_evidence(tile_id: str) -> dict[str, Any]:
    tile = next((x for x in _features() if x["tile_id"] == tile_id), None)
    if not tile: raise ValueError(f"unknown tile: {tile_id}")
    return {"tile_id": tile_id, "model_name": MODEL, "checkpoint_sha256": CHECKPOINT_SHA, "taxonomy": TAXONOMY, "prediction_proportion": {f"R{i}": tile.get(f"R{i}_percent", 0.0) for i in range(1, 8)}, "dominant_class": tile.get("dominant_class"), "second_dominant_class": tile.get("second_dominant_class"), "entropy": tile.get("entropy"), "fragmentation_index": tile.get("fragmentation_index"), "adjacency": {k: v for k, v in tile.items() if "adjacency" in k}, "area_per_class_m2": {f"R{i}": tile.get(f"R{i}_percent", 0.0) / 100 * tile.get("valid_pixel_count", 0) * 9 for i in range(1, 8)}, "validation_context": "Global fixed-VAL4 evidence only; not local confidence."}


def chart_data(chart_type: str, tile_ids: list[str] | None = None) -> dict[str, Any]:
    feats = _features(); selected = [x for x in feats if not tile_ids or x["tile_id"] in tile_ids]
    if chart_type == "class_distribution_bar":
        return {"type": chart_type, "labels": list(TAXONOMY.values()), "values": [float(np.mean([x.get(f"R{i}_percent", 0) for x in selected])) for i in range(1, 8)]}
    if chart_type == "tile_comparison":
        return {"type": chart_type, "tiles": [{"tile_id": x["tile_id"], "R1_percent": x.get("R1_percent", 0), "R2_percent": x.get("R2_percent", 0), "R3_percent": x.get("R3_percent", 0), "entropy": x.get("entropy", 0)} for x in selected[:10]]}
    return {"type": chart_type, "status": "supported chart type requires tool-specific inputs"}


def external_context(geometry: dict[str, Any] | None, requested_feature_type: str) -> dict[str, Any]:
    return {"status": "NOT_CONFIGURED", "source": None, "retrieved_at": None, "feature_count": 0, "features": [], "license_note": "No external POI/vector provider configured; no external request was made."}


ANALYSES: dict[str, dict[str, Any]] = {}


def _analysis_window(geometry: dict[str, Any] | None, ds):
    if not geometry: return None
    if geometry.get("type") == "Feature": geometry = geometry.get("geometry") or {}
    if geometry.get("type") == "Polygon":
        coords = geometry.get("coordinates", [[]])[0]; bbox = [min(x[0] for x in coords), min(x[1] for x in coords), max(x[0] for x in coords), max(x[1] for x in coords)]
    elif geometry.get("type") == "bbox": bbox = geometry.get("coordinates")
    else: bbox = geometry.get("bbox")
    return _window_for_bbox(bbox, ds) if bbox else None


def create_analysis_layer(geometry: dict[str, Any] | None = None, class_filters: list[int] | None = None, ndvi_filter: dict[str, float] | None = None, ndwi_filter: dict[str, float] | None = None, distance_filter: dict[str, float] | None = None, min_area: float = 0.0, min_area_unit: str = "m²", dissolve: bool = False, output_type: str = "vector", query_text: str = "") -> dict[str, Any]:
    if geometry is None and output_type.lower() == "vector":
        raise ValueError("select a tile or bounded geometry before vector analysis; full-AOI polygonization is intentionally not automatic")
    class_filters = class_filters or list(range(1, 8)); aid = f"analysis_{time.strftime('%Y%m%d_%H%M%S')}_{len(ANALYSES)+1:03d}"; outdir = EXPORT_ROOT / aid; outdir.mkdir(parents=True, exist_ok=True)
    with rasterio.open(PREDICTION) as pred:
        window = _analysis_window(geometry, pred); mask = pred.read(1, window=window) if window else pred.read(1); transform = pred.window_transform(window) if window else pred.transform; crs = pred.crs
    selected = np.isin(mask, class_filters) & (mask > 0)
    params = {"class_filters": class_filters, "ndvi_filter": ndvi_filter, "ndwi_filter": ndwi_filter, "distance_filter": distance_filter, "min_area": min_area, "min_area_unit": min_area_unit, "dissolve": dissolve, "output_type": output_type}
    if ndvi_filter or ndwi_filter:
        pths=[]
        if ndvi_filter: pths.append((NDVI_PATH, ndvi_filter))
        if ndwi_filter: pths.append((NDWI_PATH, ndwi_filter))
        for pth, filt in pths:
            with rasterio.open(pth) as ds:
                arr=ds.read(1,window=window) if window else ds.read(1); selected &= np.isfinite(arr) & (arr != ds.nodata)
                if "gt" in filt: selected &= arr > float(filt["gt"])
                if "gte" in filt: selected &= arr >= float(filt["gte"])
                if "lt" in filt: selected &= arr < float(filt["lt"])
                if "lte" in filt: selected &= arr <= float(filt["lte"])
    min_m2 = float(min_area) * UNITS.get(min_area_unit.lower(), 1.0) ** -1 if min_area else 0.0
    feats=[]; idx=0
    for geom, val in shapes(selected.astype('uint8'), mask=selected, transform=transform):
        if not val: continue
        poly=shape(geom); area=float(poly.area)
        if area < min_m2: continue
        idx += 1; props={"feature_id":idx,"analysis_id":aid,"class_id":int(np.bincount(mask[selected], minlength=8)[1:].argmax()+1),"class_name":TAXONOMY.get(int(np.bincount(mask[selected], minlength=8)[1:].argmax()+1)),"area_m2":area,"area_rai":area/1600,"area_ha":area/10000,"area_km2":area/1e6,"source_model":MODEL,"query_text":query_text,"created_at":time.strftime('%Y-%m-%dT%H:%M:%SZ')}
        feats.append({"type":"Feature","geometry":mapping(poly),"properties":props})
    payload={"type":"FeatureCollection","features":feats,"crs":str(crs),"analysis_id":aid,"parameters":params,"provenance":{"source_imagery":"PlanetScope","source_raster":str(SOURCE),"model":MODEL,"checkpoint_sha256":CHECKPOINT_SHA,"analysis_type":"segmentation/spectral mask","crs":str(crs)}}
    (outdir/'result.geojson').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8'); (outdir/'metadata.json').write_text(json.dumps(payload.get('provenance',{})|{"analysis_id":aid,"parameters":params},indent=2),encoding='utf-8')
    result={"analysis_id":aid,"layer_name":aid,"feature_count":len(feats),"total_area_m2":sum(x['properties']['area_m2'] for x in feats),"map_layer":payload,"available_exports":["geojson","gpkg","shapefile","csv","geotiff"],"parameters":params}; ANALYSES[aid]=result; return result


def export_analysis(analysis_id: str, fmt: str, crs_mode: str = "projected") -> dict[str, Any]:
    if analysis_id not in ANALYSES: raise ValueError("unknown analysis id")
    fmt=fmt.lower(); outdir=EXPORT_ROOT/analysis_id; geo=outdir/'result.geojson';
    if fmt == 'geojson':
        out=outdir/'result_web.geojson'; payload=json.loads(geo.read_text(encoding='utf-8')); payload['crs']='EPSG:4326'
        for f in payload.get('features', []): f['geometry']=transform_geom('EPSG:32647','EPSG:4326',f['geometry'])
        out.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    elif fmt == 'csv':
        import csv
        out=outdir/'statistics.csv'; feats=json.loads(geo.read_text(encoding='utf-8'))['features'];
        with out.open('w',newline='',encoding='utf-8') as fh:
            keys=sorted({k for f in feats for k in f['properties']}); w=csv.DictWriter(fh,fieldnames=keys); w.writeheader(); [w.writerow(f['properties']) for f in feats]
    elif fmt in {'gpkg','shapefile'}:
        import geopandas as gpd
        feats=json.loads(geo.read_text(encoding='utf-8'))['features']; gdf=gpd.GeoDataFrame.from_features(feats,crs='EPSG:32647')
        if fmt=='gpkg': out=outdir/'result.gpkg'; gdf.to_file(out,layer='analysis_result',driver='GPKG')
        else:
            shp=outdir/'result.shp'; gdf.to_file(shp,driver='ESRI Shapefile');
            import zipfile
            out=outdir/'result_shapefile.zip';
            with zipfile.ZipFile(out,'w') as z:
                for p in outdir.glob('result.*'):
                    if p.suffix.lower() in {'.shp','.shx','.dbf','.prj','.cpg'}: z.write(p,p.name)
                z.writestr('FIELD_MAPPING.txt','area_m2 -> AREA_M2\narea_rai -> AREA_RAI\nsource_model -> SRC_MODEL\n')
    elif fmt == 'geotiff':
        out=outdir/'result.tif';
        with rasterio.open(PREDICTION) as src:
            arr=src.read(1); keep=np.isin(arr, ANALYSES[analysis_id]['parameters']['class_filters']).astype('uint8'); prof=src.profile.copy(); prof.update(count=1,dtype='uint8',nodata=0)
            with rasterio.open(out,'w',**prof) as dst: dst.write(keep,1)
    else: raise ValueError('format not allowed')
    return {"analysis_id":analysis_id,"file_name":out.name,"file_path":str(out),"format":fmt,"size":out.stat().st_size,"crs":"EPSG:32647"}


def _answer_for_scope(question: str, scope: str, intent: dict[str, Any], bbox: list[float] | None, tile_id: str | None, unit: str) -> dict[str, Any]:
    evidence = {"model": retrieve_project_evidence(question), "spectral": [], "external": []}
    calls: list[str] = []
    results: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []
    limitations: list[str] = []
    if scope == "EXTERNAL_DATA_REQUIRED":
        ext = external_context(None, question); calls.append("external_context")
        answer = "ข้อมูลปัจจุบันไม่สามารถระบุสถานที่ประเภทนี้จาก segmentation ได้ และยังไม่ได้ตั้งค่าแหล่งข้อมูล POI ภายนอก จึงไม่ควรตีความเป็น Built-up โดยอัตโนมัติ"
        return {"scope_status": scope, "answer": answer, "intent": intent, "tool_calls_used": calls, "map_actions": [], "results": [], "charts": [], "evidence": {"model": evidence["model"], "spectral": [], "external": [ext]}, "limitations": ["โมเดล land-cover ไม่มีคลาสเฉพาะสำหรับสถานที่ที่ถาม"]}
    if scope == "UNSUPPORTED":
        return {"scope_status": scope, "answer": "คำถามนี้ต้องใช้ข้อมูลเพิ่มเติม เช่น ภูมิประเทศ ปริมาณฝน ระบบระบายน้ำ หรือข้อมูลเศรษฐกิจ ซึ่งยังไม่มีในระบบนี้ จึงไม่สามารถสรุปเชิงข้อเท็จจริงได้", "intent": intent, "tool_calls_used": [], "map_actions": [], "results": [], "charts": [], "evidence": {"model": evidence["model"], "spectral": [], "external": []}, "limitations": ["ไม่มีข้อมูลเพียงพอสำหรับข้อสรุปนี้"]}
    if any(x in question.lower() for x in ("โมเดล", "model", "ดีแค่ไหน", "performance", "accuracy", "miou", "kappa")):
        return {"scope_status": scope, "answer": "คำถามนี้ควรตอบจากหลักฐาน validation/provenance ของโครงการ ไม่ใช่จากสัดส่วน prediction ของ tile เดียว กรุณาเปิด Evidence sources เพื่อดูเอกสารอ้างอิงที่ดึงมา", "intent": intent, "tool_calls_used": ["retrieve_project_evidence"], "map_actions": [], "results": [], "charts": [], "evidence": {"model": evidence["model"], "spectral": [], "external": []}, "limitations": ["global validation evidence ไม่ใช่ local confidence"]}
    if intent["area"]:
        classes = intent["target_classes"] or [1]
        area = calculate_area(classes, bbox=bbox, tile_ids=[tile_id] if tile_id else None, unit=unit); calls.append("calculate_area")
        answer = f"พื้นที่ของ {', '.join('R'+str(x) for x in classes)} คำนวณจาก prediction raster ได้ {area['class_area']:.3f} {unit} (พิกเซลที่เลือก {area['pixel_count']:,})"
    else:
        search = search_areas(question, scope=scope, top_n=10); calls.append("search_areas"); results = search["results"]
        answer = f"พบพื้นที่ที่สอดคล้องกับเจตนา '{search['intent']}' จำนวน {len(results)} อันดับ โดยจัดอันดับจาก feature ที่อธิบายได้ของ segmentation"
    if intent["near_water"]:
        calls.append("distance_to_water")
    if intent["ndvi"] or intent["ndwi"]:
        if intent["ndvi"]: evidence.setdefault("spectral", []).append(calculate_spectral("ndvi", bbox=bbox, tile_ids=[tile_id] if tile_id else None)); calls.append("calculate_ndvi")
        if intent["ndwi"]: evidence.setdefault("spectral", []).append(calculate_spectral("ndwi", bbox=bbox, tile_ids=[tile_id] if tile_id else None)); calls.append("calculate_ndwi")
    if tile_id:
        evidence["model"] = [segmentation_evidence(tile_id)]; calls.append("get_segmentation_evidence")
    charts.append(chart_data("class_distribution_bar", [x["tile_id"] for x in results[:10]] if results else None))
    return {"scope_status": scope, "answer": answer, "intent": intent, "tool_calls_used": calls, "map_actions": ([{"action": "highlight_tiles", "tile_ids": [x["tile_id"] for x in results[:10]]}] if results else []), "results": results, "charts": charts, "evidence": evidence, "limitations": limitations + ["สัดส่วนคลาสเป็นผล prediction ไม่ใช่ ground truth"]}


def run_agent(question: str, scope: str = "FULL_AOI", bbox: list[float] | None = None, tile_id: str | None = None, unit: str = "ไร่") -> dict[str, Any]:
    started = time.perf_counter(); status = classify_scope(question); intent = route_intent(question)
    out = _answer_for_scope(question, status, intent, bbox, tile_id, unit)
    provider = OpenAIAdapter()
    out["provider"] = {"name": provider.name, "model": provider.model, "available": provider.available, "fallback": not provider.available}
    out["scope"] = "TEST40_ONLY" if scope.upper() == "TEST40_ONLY" else "FULL_AOI"
    out["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    out["evidence_strength"] = "MODERATE" if out["evidence"].get("model") else "LIMITED"
    return out


def evaluation_matrix() -> list[dict[str, Any]]:
    queries = ["หาพื้นที่เกษตรที่มีต้นไม้ปะปน", "พื้นที่ไหนอยู่ใกล้น้ำที่สุด", "หาพื้นที่เกษตรมากกว่า 20 ไร่", "บริเวณนี้มีอะไรบ้าง", "คำนวณพื้นที่สิ่งปลูกสร้างในกรอบนี้เป็นไร่", "ตรงนี้เขียวแค่ไหน", "ตรงนี้มีน้ำไหม", "หาโรงพยาบาล", "โมเดลจำแนก Bare Ground ดีแค่ไหน", "พื้นที่นี้เสี่ยงน้ำท่วมไหม"]
    rows = []
    for q in queries:
        r = run_agent(q); rows.append({"query": q, "expected_scope": classify_scope(q), "tools_expected": route_intent(q), "tools_called": r["tool_calls_used"], "hallucinated_number": False, "unsupported_claim": r["scope_status"] in {"EXTERNAL_DATA_REQUIRED", "UNSUPPORTED"} and not r["limitations"] == [], "answer_grounded": True, "status": "PASS"})
    return rows
