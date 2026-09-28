# CLEAN PROJECT HEADER
# ไฟล์: evidence_crosscheck.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Read-only spectral and external-reference checks for the frozen A7 output.

All evidence is contextual: class profiles are conditioned on model-predicted
classes and are not independent validation or accuracy estimates.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_bounds, transform_geom
from rasterio.windows import Window, from_bounds
from project_paths import EVIDENCE_PROFILE_ROOT, FULL_FEATURES_PATH, NDVI_PATH, NDWI_PATH, PREDICTION

PROFILE_DIR = EVIDENCE_PROFILE_ROOT
FEATURES_PATH = FULL_FEATURES_PATH
MODEL = "A7_RGBN_REVISED7_TVERSKY"
TAXONOMY = {1: "R1 Built-up & Impervious", 2: "R2 Agricultural Land / Cropland", 3: "R3 Tree / Woody Cover", 4: "R4 Water", 5: "R5 Grassland / Herbaceous Cover", 6: "R6 Bare Ground", 7: "R7 Uncertain / Cloud"}
RELEVANCE = {
    1: {"ndvi": "PRIMARY", "ndwi": "SECONDARY"},
    2: {"ndvi": "PRIMARY", "ndwi": "SECONDARY"},
    3: {"ndvi": "PRIMARY", "ndwi": "SECONDARY"},
    4: {"ndvi": "SECONDARY", "ndwi": "PRIMARY"},
    5: {"ndvi": "PRIMARY", "ndwi": "NOT_USED"},
    6: {"ndvi": "PRIMARY", "ndwi": "SECONDARY"},
    7: {"ndvi": "NOT_USED", "ndwi": "NOT_USED"},
}
OSM_TAGS = {
    1: {"building": "*", "landuse": ["residential", "commercial", "industrial"], "highway": "*"},
    2: {"landuse": ["farmland", "orchard", "vineyard"], "crop": "*"},
    4: {"natural": "water", "water": "*", "waterway": "*", "landuse": "reservoir"},
}


def _finite_stats(values: np.ndarray) -> dict[str, Any]:
    v = values[np.isfinite(values)].astype(np.float64, copy=False)
    if not v.size:
        return {"mean": None, "median": None, "std": None, "p10": None, "p25": None, "p75": None, "p90": None, "iqr": None}
    q = np.percentile(v, [10, 25, 75, 90])
    return {"mean": float(v.mean()), "median": float(np.median(v)), "std": float(v.std()), "p10": float(q[0]), "p25": float(q[1]), "p75": float(q[2]), "p90": float(q[3]), "iqr": float(q[2] - q[1])}


def compute_class_spectral_profiles(output_dir: Path = PROFILE_DIR) -> dict[str, Any]:
    """Compute pooled class-wise NDVI/NDWI distributions from model output."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ndvi_chunks: dict[int, list[np.ndarray]] = {i: [] for i in TAXONOMY}
    ndwi_chunks: dict[int, list[np.ndarray]] = {i: [] for i in TAXONOMY}
    counts = {i: 0 for i in TAXONOMY}
    with rasterio.open(PREDICTION) as pred, rasterio.open(NDVI_PATH) as ndvi, rasterio.open(NDWI_PATH) as ndwi:
        if pred.shape != ndvi.shape or pred.shape != ndwi.shape or pred.transform != ndvi.transform or pred.transform != ndwi.transform:
            raise RuntimeError("prediction and spectral rasters are not on the exact same grid")
        for _, win in pred.block_windows(1):
            pm = pred.read(1, window=win)
            va = ndvi.read(1, window=win).astype(np.float32, copy=False)
            vw = ndwi.read(1, window=win).astype(np.float32, copy=False)
            valid = (pm >= 1) & (pm <= 7) & np.isfinite(va) & np.isfinite(vw)
            for cls in TAXONOMY:
                m = valid & (pm == cls)
                if m.any():
                    counts[cls] += int(m.sum())
                    ndvi_chunks[cls].append(va[m].copy())
                    ndwi_chunks[cls].append(vw[m].copy())
    rows = []
    for cls, name in TAXONOMY.items():
        nv = np.concatenate(ndvi_chunks[cls]) if ndvi_chunks[cls] else np.empty(0, dtype=np.float32)
        nw = np.concatenate(ndwi_chunks[cls]) if ndwi_chunks[cls] else np.empty(0, dtype=np.float32)
        ns, ws = _finite_stats(nv), _finite_stats(nw)
        rows.append({"class_id": cls, "class_name": name, "pixel_count": counts[cls], "ndvi_mean": ns["mean"], "ndvi_median": ns["median"], "ndvi_std": ns["std"], "ndvi_p10": ns["p10"], "ndvi_p25": ns["p25"], "ndvi_p75": ns["p75"], "ndvi_p90": ns["p90"], "ndvi_iqr": ns["iqr"], "ndwi_mean": ws["mean"], "ndwi_median": ws["median"], "ndwi_std": ws["std"], "ndwi_p10": ws["p10"], "ndwi_p25": ws["p25"], "ndwi_p75": ws["p75"], "ndwi_p90": ws["p90"], "ndwi_iqr": ws["iqr"], "relevance": RELEVANCE[cls]})
        del nv, nw
    payload = {"model": MODEL, "prediction_source": str(PREDICTION), "ndvi_source": str(NDVI_PATH), "ndwi_source": str(NDWI_PATH), "method": "pooled valid pixels grouped by predicted class; NoData/nonfinite excluded", "independent_validation": False, "interpretation": "Profiles are model-prediction-conditioned spectral consistency references, not ground truth or accuracy.", "profiles": rows}
    (output_dir / "class_spectral_profiles.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    import csv
    fields = ["class_id", "class_name", "pixel_count", "ndvi_mean", "ndvi_median", "ndvi_std", "ndvi_p10", "ndvi_p25", "ndvi_p75", "ndvi_p90", "ndvi_iqr", "ndwi_mean", "ndwi_median", "ndwi_std", "ndwi_p10", "ndwi_p25", "ndwi_p75", "ndwi_p90", "ndwi_iqr"]
    with (output_dir / "class_spectral_profiles.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows({k: row.get(k) for k in fields} for row in rows)
    return payload


def _geometry_bbox(geometry: dict[str, Any]) -> list[float]:
    if geometry.get("type") == "Feature": geometry = geometry.get("geometry") or {}
    if geometry.get("type") == "bbox": return [float(x) for x in geometry["coordinates"]]
    if geometry.get("type") == "Polygon":
        pts = geometry.get("coordinates", [[]])[0]
        return [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]
    if geometry.get("bbox"): return [float(x) for x in geometry["bbox"]]
    raise ValueError("geometry must be a GeoJSON Polygon, Feature, or bbox")


def _window_and_mask(geometry: dict[str, Any], ds) -> tuple[Window, np.ndarray | None]:
    bbox = _geometry_bbox(geometry)
    left, bottom, right, top = transform_bounds("EPSG:4326", ds.crs, *bbox, densify_pts=21)
    win = from_bounds(left, bottom, right, top, ds.transform).round_offsets().round_lengths().intersection(Window(0, 0, ds.width, ds.height))
    geom = geometry.get("geometry") if geometry.get("type") == "Feature" else geometry
    if geom and geom.get("type") == "Polygon":
        src_geom = transform_geom("EPSG:4326", ds.crs, geom)
        mask = geometry_mask([src_geom], out_shape=(int(win.height), int(win.width)), transform=ds.window_transform(win), invert=True)
    else: mask = None
    return win, mask


def _consistency(value: float | None, profile: dict[str, Any], minimum_pixels: int) -> tuple[str, list[float | None], list[float | None]]:
    iqr = [profile.get("p25"), profile.get("p75")]; p90 = [profile.get("p10"), profile.get("p90")]
    if value is None or profile.get("pixel_count", 0) < minimum_pixels: return "INSUFFICIENT", iqr, p90
    if iqr[0] <= value <= iqr[1]: return "CONSISTENT", iqr, p90
    if p90[0] <= value <= p90[1]: return "SUPPORTIVE", iqr, p90
    return "QUESTIONABLE", iqr, p90


def check_spectral_consistency(geometry: dict[str, Any], predicted_class: int, profiles: dict[str, Any] | None = None, minimum_pixels: int = 100) -> dict[str, Any]:
    cls = int(predicted_class)
    profiles = profiles or json.loads((PROFILE_DIR / "class_spectral_profiles.json").read_text(encoding="utf-8"))
    prof = next((x for x in profiles["profiles"] if int(x["class_id"]) == cls), None)
    if not prof: raise ValueError(f"unknown predicted class: {predicted_class}")
    with rasterio.open(PREDICTION) as pred, rasterio.open(NDVI_PATH) as ndvi, rasterio.open(NDWI_PATH) as ndwi:
        win, poly_mask = _window_and_mask(geometry, pred)
        pm = pred.read(1, window=win); va = ndvi.read(1, window=win); vw = ndwi.read(1, window=win)
    selected = (pm == cls) & np.isfinite(va) & np.isfinite(vw)
    if poly_mask is not None: selected &= poly_mask
    n = int(selected.sum()); ns = _finite_stats(va[selected]); ws = _finite_stats(vw[selected])
    rel = RELEVANCE[cls]
    ndvi_status = "NOT_USED" if rel["ndvi"] == "NOT_USED" else _consistency(ns["median"], {"pixel_count": n, "p25": prof["ndvi_p25"], "p75": prof["ndvi_p75"], "p10": prof["ndvi_p10"], "p90": prof["ndvi_p90"]}, minimum_pixels)[0]
    ndwi_status = "NOT_USED" if rel["ndwi"] == "NOT_USED" else _consistency(ws["median"], {"pixel_count": n, "p25": prof["ndwi_p25"], "p75": prof["ndwi_p75"], "p10": prof["ndwi_p10"], "p90": prof["ndwi_p90"]}, minimum_pixels)[0]
    relevant = [x for x in (ndvi_status, ndwi_status) if x != "NOT_USED"]
    if n < minimum_pixels or not relevant: overall = "INSUFFICIENT"
    elif "QUESTIONABLE" in relevant: overall = "QUESTIONABLE"
    elif all(x == "CONSISTENT" for x in relevant): overall = "CONSISTENT"
    elif any(x in {"CONSISTENT", "SUPPORTIVE"} for x in relevant): overall = "SUPPORTIVE"
    else: overall = "INSUFFICIENT"
    return {"predicted_class": f"R{cls} {TAXONOMY[cls]}", "predicted_class_id": cls, "pixel_count": n, "ndvi": {"median": ns["median"], "iqr": [prof["ndvi_p25"], prof["ndvi_p75"]], "class_reference_iqr": [prof["ndvi_p25"], prof["ndvi_p75"]], "class_reference_p10_p90": [prof["ndvi_p10"], prof["ndvi_p90"]], "status": ndvi_status, "relevance": rel["ndvi"]}, "ndwi": {"median": ws["median"], "iqr": [prof["ndwi_p25"], prof["ndwi_p75"]], "class_reference_iqr": [prof["ndwi_p25"], prof["ndwi_p75"]], "class_reference_p10_p90": [prof["ndwi_p10"], prof["ndwi_p90"]], "status": ndwi_status, "relevance": rel["ndwi"]}, "overall_spectral_status": overall, "rule": "CONSISTENT if selected median is within class IQR; SUPPORTIVE within p10-p90; QUESTIONABLE outside p10-p90; INSUFFICIENT below minimum pixels."
    }


def _overpass_query(bbox: list[float], cls: int) -> str:
    s, w, n, e = bbox[1], bbox[0], bbox[3], bbox[2]
    clauses = []
    tags = OSM_TAGS[cls]
    for key, vals in tags.items():
        vals = vals if isinstance(vals, list) else [vals]
        for val in vals:
            q = f'["{key}"]' if val == "*" else f'["{key}"="{val}"]'
            clauses.extend([f'way{q}({s},{w},{n},{e});', f'relation{q}({s},{w},{n},{e});'])
    return "[out:json][timeout:12];(" + "".join(clauses) + ");out center tags;"


def check_external_reference(geometry: dict[str, Any], predicted_class: int, timeout: int = 15) -> dict[str, Any]:
    cls = int(predicted_class); retrieved = datetime.now(timezone.utc).isoformat(); bbox = _geometry_bbox(geometry)
    base = {"source": "OpenStreetMap", "provider": "Overpass API", "retrieved_at": retrieved, "bbox": bbox, "tags_queried": OSM_TAGS.get(cls), "license_note": "© OpenStreetMap contributors; OSM is contextual reference and may be incomplete."}
    if cls not in OSM_TAGS: return base | {"status": "INSUFFICIENT_DATA", "feature_count": 0, "matched_feature_types": [], "intersection_area": None, "coverage_percent": None, "nearest_feature_distance_m": None, "message": "No class-specific OSM mapping is defined for this predicted class."}
    try:
        req = Request("https://overpass-api.de/api/interpreter", data=_overpass_query(bbox, cls).encode("utf-8"), headers={"User-Agent": "GeoAI-Evidence-CrossCheck/1.0"})
        with urlopen(req, timeout=timeout) as resp: payload = json.loads(resp.read().decode("utf-8"))
        elements = payload.get("elements", []); types = sorted({f"{e.get('type')}:{next(iter(e.get('tags', {})), 'feature')}" for e in elements})
        return base | {"status": "SUPPORTIVE" if elements else "NO_MATCH", "feature_count": len(elements), "matched_feature_types": types, "intersection_area": None, "coverage_percent": None, "nearest_feature_distance_m": None, "message": "No matching OSM feature does not prove the model prediction is incorrect because OSM coverage may be incomplete." if not elements else "Matching OSM features provide contextual support, not ground truth."}
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return base | {"status": "UNAVAILABLE", "feature_count": 0, "matched_feature_types": [], "intersection_area": None, "coverage_percent": None, "nearest_feature_distance_m": None, "error": str(exc), "message": "External reference unavailable; local model and spectral evidence remain usable."}


def audit_sample(max_per_class: int = 5) -> list[dict[str, Any]]:
    features = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))["features"]
    # Exclude TEST40-labelled records from the audit sample; this is not an accuracy evaluation.
    candidates = [x for x in features if x.get("dataset_role") != "TEST40"]
    rows = []
    profiles = json.loads((PROFILE_DIR / "class_spectral_profiles.json").read_text(encoding="utf-8"))
    for cls in range(1, 7):
        picked = [x for x in candidates if int(x.get("dominant_class", 0)) == cls][:max_per_class]
        for tile in picked:
            geom = {"type": "bbox", "coordinates": tile["bbox"]}
            spectral = check_spectral_consistency(geom, cls, profiles)
            external = check_external_reference(geom, cls, timeout=5)
            spectral_status = spectral["overall_spectral_status"]
            osm_status = external["status"]
            strength = "HIGH" if spectral_status == "CONSISTENT" and osm_status == "SUPPORTIVE" else ("MODERATE" if spectral_status == "CONSISTENT" or osm_status == "SUPPORTIVE" else "LIMITED")
            rows.append({"tile_id": tile["tile_id"], "class_id": cls, "class_name": TAXONOMY[cls], "geometry": geom, "ndvi_status": spectral["ndvi"]["status"], "ndwi_status": spectral["ndwi"]["status"], "spectral_status": spectral_status, "osm_status": osm_status, "external": external, "evidence_strength": strength})
    return rows
