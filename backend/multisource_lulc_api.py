# CLEAN PROJECT HEADER
# ไฟล์: multisource_lulc_api.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Selected-area read-only comparison against materialized external references."""
from pathlib import Path
import json
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_bounds, transform_geom
from rasterio.windows import from_bounds, Window
from project_paths import EXTERNAL_REFERENCE_ROOT

ROOT = EXTERNAL_REFERENCE_ROOT
A7 = ROOT / "harmonized" / "A7T_HARMONIZED_10M.tif"
GISTDA = ROOT / "harmonized" / "GISTDA_HARMONIZED_10M.tif"
META = ROOT / "metadata" / "comparison_metadata.json"

def _bbox(g):
    if g.get("type") == "Feature": g = g.get("geometry") or {}
    if g.get("type") == "bbox": return [float(x) for x in g["coordinates"]]
    if g.get("bbox"): return [float(x) for x in g["bbox"]]
    pts = g.get("coordinates", [[]])[0]
    return [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]

def _window_mask(g, ds):
    b = _bbox(g); left,bottom,right,top = transform_bounds("EPSG:4326", ds.crs, *b)
    w = from_bounds(left,bottom,right,top,ds.transform).round_offsets().round_lengths().intersection(Window(0,0,ds.width,ds.height))
    geom = g.get("geometry") if g.get("type") == "Feature" else g
    if geom and geom.get("type") == "Polygon":
        m = geometry_mask([transform_geom("EPSG:4326", ds.crs, geom)], out_shape=(int(w.height),int(w.width)), transform=ds.window_transform(w), invert=True)
    else: m = None
    return w,m

def _composition(arr):
    n = int(arr.size); return {f"R{i}": int((arr == i).sum()) for i in range(1,7)} | {"valid_mapped_pixels": int(((arr>=1)&(arr<=6)).sum()), "total_selected_pixels": n}

def compare_geometry(geometry):
    with rasterio.open(A7) as a7:
        w,m = _window_mask(geometry,a7); av=a7.read(1,window=w)
    with rasterio.open(GISTDA) as ref:
        rv=ref.read(1,window=w)
    if m is not None: av=av[m]; rv=rv[m]
    else: av=av.reshape(-1); rv=rv.reshape(-1)
    valid=(av>=1)&(av<=6)&(rv>=1)&(rv<=6); n=int(valid.sum()); agree=int((av[valid]==rv[valid]).sum())
    return {"a7_composition":_composition(av),"dynamic_world":{"status":"NOT_AVAILABLE","composition":None},"worldcover":{"status":"NOT_AVAILABLE","composition":None,"reference_year":2021},"gistda":{"status":"PASS","composition":_composition(rv),"reference_period":"B.E. 2560-2561 (approx.)"},"mapped_overlap_pixels":n,"agreement_pixels":agree,"agreement_percent":100*agree/n if n else None,"sources_available":1 if n else 0,"temporal_metadata":json.loads(META.read_text(encoding="utf-8")) if META.exists() else None,"interpretation":"Cross-dataset agreement/context only; not accuracy or ground-truth validation."}
