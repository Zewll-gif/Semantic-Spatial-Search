# CLEAN PROJECT HEADER
# ไฟล์: geoai_api.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
from __future__ import annotations

import uuid
from typing import Any, Optional

from runtime_env import configure_geospatial_environment

configure_geospatial_environment()

import geopandas as gpd
import numpy as np
import rasterio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from rasterio.mask import mask as rio_mask
from shapely.geometry import shape, mapping
from shapely.ops import transform
from shapely.validation import make_valid
from pyproj import Transformer
from project_paths import NDVI_PATH, NDWI_PATH, VECTOR_GPKG, VECTOR_ROOT

BASE = VECTOR_ROOT
VECTOR = VECTOR_GPKG
NDVI = NDVI_PATH
NDWI = NDWI_PATH
CRS_PROJECTED = "EPSG:32647"
CRS_DISPLAY = "EPSG:4326"
CLASS_NAMES = {1:"Built-up & Impervious",2:"Agricultural Land / Cropland",3:"Tree / Woody Cover",4:"Water",5:"Grassland / Herbaceous Cover",6:"Bare Ground",7:"Uncertain / Cloud"}
CLASS_CODES = {f"R{i}": i for i in range(1, 8)}

app = FastAPI(title="A7-T GeoAI Backend Foundation", version="1.0.0", description="Read-only spatial API foundation for A7-T derived polygons.")
_gdf: Optional[gpd.GeoDataFrame] = None

def repo():
    global _gdf
    if _gdf is None:
        if not VECTOR.exists(): raise RuntimeError("VECTOR_NOT_FOUND")
        _gdf = gpd.read_file(VECTOR, layer="polygons")
        if _gdf.crs is None: _gdf = _gdf.set_crs(CRS_PROJECTED)
        elif str(_gdf.crs) != CRS_PROJECTED: _gdf = _gdf.to_crs(CRS_PROJECTED)
    return _gdf

def rid(): return str(uuid.uuid4())
def success(data: Any, limitations=None): return {"status":"success","request_id":rid(),"data":data,"limitations":limitations or []}
def fail(code: str, message: str, status=400): raise HTTPException(status_code=status, detail={"status":"error","code":code,"message":message,"request_id":rid()})

def code_id(value: str) -> int:
    v=value.upper().strip()
    if v not in CLASS_CODES: fail("INVALID_CLASS", f"Unknown class code: {value}")
    return CLASS_CODES[v]

def geojson_geom(g, simplify=False):
    if simplify: g = g.simplify(1.0, preserve_topology=True)
    return mapping(g)

def to_display(g):
    return transform(Transformer.from_crs(CRS_PROJECTED, CRS_DISPLAY, always_xy=True).transform, g)

def row_result(row, include_geometry=True):
    result={"polygon_id":int(row.polygon_id),"class_code":str(row.class_code),"class_name":str(row.class_name),"area_m2":float(row.area_m2),"area_ha":float(row.area_ha),"area_km2":float(row.area_km2),"area_rai":float(row.area_rai)}
    if include_geometry: result["geometry"] = geojson_geom(to_display(row.geometry), simplify=True)
    return result

class SearchRequest(BaseModel):
    class_codes: list[str] = Field(default_factory=list)
    min_area_rai: float = Field(default=0, ge=0)
    max_area_rai: Optional[float] = Field(default=None, ge=0)
    max_results: int = Field(default=20, ge=1, le=100)

class GeometryRequest(BaseModel):
    polygon_id: Optional[int] = Field(default=None, ge=1)
    geometry: Optional[dict] = None
    @model_validator(mode="after")
    def one_input(self):
        if (self.polygon_id is None) == (self.geometry is None): raise ValueError("Provide exactly one of polygon_id or geometry")
        return self

class DistanceRequest(BaseModel):
    source_polygon_id: Optional[int] = Field(default=None, ge=1)
    target_polygon_id: Optional[int] = Field(default=None, ge=1)
    source_geometry: Optional[dict] = None
    target_geometry: Optional[dict] = None

class NearRequest(BaseModel):
    target_class: str
    reference_class: str
    max_distance_m: float = Field(gt=0, le=100000)
    min_area_rai: float = Field(default=0, ge=0)
    max_results: int = Field(default=20, ge=1, le=100)

class IntersectRequest(BaseModel):
    class_a: Optional[str] = None
    class_b: Optional[str] = None
    geometry_a: Optional[dict] = None
    geometry_b: Optional[dict] = None
    max_results: int = Field(default=20, ge=1, le=100)

class PolygonRequest(BaseModel):
    polygon_id: int = Field(ge=1)

def get_geom_by_id(pid):
    g=repo(); rows=g[g.polygon_id==pid]
    if rows.empty: fail("NO_RESULTS", f"polygon_id {pid} not found",404)
    return rows.iloc[0].geometry

def request_geom(geo):
    try:
        return shape(geo)
    except Exception as exc:
        fail("INVALID_GEOMETRY", str(exc))

def display_row(row):
    return {"polygon_id":int(row.polygon_id),"class_code":str(row.class_code),"class_name":str(row.class_name),"area_rai":float(row.area_rai),"geometry":geojson_geom(to_display(row.geometry), simplify=True)}

def spectral_stats(path, geom):
    if not path.exists(): fail("RASTER_ERROR", f"Missing raster: {path}",500)
    try:
        with rasterio.open(path) as src:
            g=geom
            if str(src.crs)!=CRS_PROJECTED: g=transform(Transformer.from_crs(CRS_PROJECTED, src.crs, always_xy=True).transform,g)
            data,_=rio_mask(src,[mapping(g)],crop=True,filled=False)
            vals=data[0].compressed().astype(float)
            vals=vals[np.isfinite(vals)]
            if vals.size==0: return {"count":0,"mean":None,"median":None,"std":None,"min":None,"max":None,"p10":None,"p90":None}
            return {"count":int(vals.size),"mean":float(vals.mean()),"median":float(np.median(vals)),"std":float(vals.std()),"min":float(vals.min()),"max":float(vals.max()),"p10":float(np.percentile(vals,10)),"p90":float(np.percentile(vals,90))}
    except ValueError as exc: fail("INVALID_GEOMETRY", str(exc))
    except Exception as exc: fail("RASTER_ERROR", str(exc),500)

@app.get("/api/geoai/health")
def health():
    try:
        from postgis_store import health as postgis_health
    except ImportError:  # pragma: no cover
        from .postgis_store import health as postgis_health
    connection = postgis_health()
    # These legacy /api/geoai/* endpoints still read the GeoPackage. Only the
    # canonical V2 GIS tools switch to PostGIS when a DSN is configured.
    return success({"status":"ok","model":"A7-T",
                    "database":"connected" if connection["connected"] else "config_required",
                    "postgis_connection":connection,"crs":CRS_PROJECTED,
                    "backend_mode":"gpkg_legacy"})

@app.get("/api/geoai/classes")
def classes():
    return success([{"class_id":i,"class_code":f"R{i}","class_name":CLASS_NAMES[i]} for i in range(1,8)])

@app.post("/api/geoai/search")
def search(req: SearchRequest):
    g=repo(); ids=[code_id(c) for c in req.class_codes] if req.class_codes else list(range(1,8)); q=g[g.class_id.isin(ids)&(g.area_rai>=req.min_area_rai)]
    if req.max_area_rai is not None: q=q[q.area_rai<=req.max_area_rai]
    if q.empty: fail("NO_RESULTS","No polygons match filters",404)
    q=q.sort_values("area_rai",ascending=False).head(req.max_results)
    return success({"count":len(q),"results":[row_result(r) for _,r in q.iterrows()]},["Geometry returned as GeoJSON EPSG:4326; areas calculated in EPSG:32647."])

@app.post("/api/geoai/area")
def area(req: GeometryRequest):
    geom=get_geom_by_id(req.polygon_id) if req.polygon_id is not None else request_geom(req.geometry)
    if req.geometry is not None: geom=transform(Transformer.from_crs(CRS_DISPLAY,CRS_PROJECTED,always_xy=True).transform,geom)
    a=float(geom.area); return success({"area_m2":a,"area_ha":a/10000,"area_km2":a/1e6,"area_rai":a/1600},["Area calculated in projected CRS EPSG:32647."])

def endpoint_geom(pid, geo): return get_geom_by_id(pid) if pid is not None else request_geom(geo)

@app.post("/api/geoai/distance")
def distance(req: DistanceRequest):
    if req.source_polygon_id is None and req.source_geometry is None: fail("INVALID_GEOMETRY","Missing source geometry")
    if req.target_polygon_id is None and req.target_geometry is None: fail("INVALID_GEOMETRY","Missing target geometry")
    a=endpoint_geom(req.source_polygon_id,req.source_geometry); b=endpoint_geom(req.target_polygon_id,req.target_geometry)
    if req.source_geometry is not None: a=transform(Transformer.from_crs(CRS_DISPLAY,CRS_PROJECTED,always_xy=True).transform,a)
    if req.target_geometry is not None: b=transform(Transformer.from_crs(CRS_DISPLAY,CRS_PROJECTED,always_xy=True).transform,b)
    return success({"distance_m":float(a.distance(b))},["Minimum geometry-to-geometry distance in EPSG:32647."])

@app.post("/api/geoai/near")
def near(req: NearRequest):
    tid=code_id(req.target_class); rid_=code_id(req.reference_class); g=repo(); targets=g[(g.class_id==tid)&(g.area_rai>=req.min_area_rai)]; refs=g[g.class_id==rid_]
    if targets.empty or refs.empty: fail("NO_RESULTS","No target or reference polygons",404)
    ref_union=refs.geometry.union_all() if hasattr(refs.geometry,"union_all") else refs.geometry.unary_union
    rows=[]
    for _,r in targets.iterrows():
        d=float(r.geometry.distance(ref_union))
        if d<=req.max_distance_m: rows.append((d,r))
    rows.sort(key=lambda x:x[0]); results=[]
    for d,r in rows[:req.max_results]:
        x=display_row(r); x["nearest_reference_distance_m"]=d; results.append(x)
    if not results: fail("NO_RESULTS","No polygons within requested distance",404)
    return success({"count":len(results),"results":results},["Distance uses true geometry-to-geometry distance, not centroid distance.","Geometry returned as GeoJSON EPSG:4326."])

@app.post("/api/geoai/intersect")
def intersect(req: IntersectRequest):
    g=repo();
    if req.geometry_a is not None and req.geometry_b is not None:
        a=transform(Transformer.from_crs(CRS_DISPLAY,CRS_PROJECTED,always_xy=True).transform,request_geom(req.geometry_a)); b=transform(Transformer.from_crs(CRS_DISPLAY,CRS_PROJECTED,always_xy=True).transform,request_geom(req.geometry_b)); inter=make_valid(a).intersection(make_valid(b))
        return success({"intersection_area_m2":float(inter.area),"geometry":geojson_geom(to_display(inter))})
    if not req.class_a or not req.class_b: fail("INVALID_CLASS","Provide class_a/class_b or both geometries")
    ia,ib=code_id(req.class_a),code_id(req.class_b); arows=g[g.class_id==ia]; brows=g[g.class_id==ib]; results=[]
    for _,a in arows.iterrows():
        cand=brows[brows.geometry.intersects(a.geometry)]
        for _,b in cand.iterrows():
            inter=a.geometry.intersection(b.geometry)
            if not inter.is_empty and inter.area>0: results.append({"source_polygon_id":int(a.polygon_id),"target_polygon_id":int(b.polygon_id),"intersection_area_m2":float(inter.area),"geometry":geojson_geom(to_display(inter),True)})
            if len(results)>=req.max_results: break
        if len(results)>=req.max_results: break
    if not results: fail("NO_RESULTS","No intersections found",404)
    return success({"count":len(results),"results":results})

@app.post("/api/geoai/ndvi-stats")
def ndvi_stats(req: GeometryRequest):
    geom=get_geom_by_id(req.polygon_id) if req.polygon_id is not None else transform(Transformer.from_crs(CRS_DISPLAY,CRS_PROJECTED,always_xy=True).transform,request_geom(req.geometry))
    return success(spectral_stats(NDVI,geom),["NDVI is supporting spectral evidence, not GT validation."])

@app.post("/api/geoai/ndwi-stats")
def ndwi_stats(req: GeometryRequest):
    geom=get_geom_by_id(req.polygon_id) if req.polygon_id is not None else transform(Transformer.from_crs(CRS_DISPLAY,CRS_PROJECTED,always_xy=True).transform,request_geom(req.geometry))
    return success(spectral_stats(NDWI,geom),["NDWI is supporting spectral evidence, not GT validation."])

@app.post("/api/geoai/evidence")
def evidence(req: PolygonRequest):
    g=repo(); rows=g[g.polygon_id==req.polygon_id]
    if rows.empty: fail("NO_RESULTS",f"polygon_id {req.polygon_id} not found",404)
    r=rows.iloc[0]; geom=r.geometry
    return success({"model":{"source_model":"A7-T","model_version":"A7_RGBN_REVISED7_TVERSKY","class_code":str(r.class_code),"class_name":str(r.class_name)},"spatial":{"polygon_id":int(r.polygon_id),"area_rai":float(r.area_rai),"centroid_x":float(r.centroid_x),"centroid_y":float(r.centroid_y)},"spectral":{"ndvi":spectral_stats(NDVI,geom),"ndwi":spectral_stats(NDWI,geom)},"external":{"status":"not_loaded","note":"GISTDA agreement is external consistency evidence, not accuracy."},"limitations":["Derived from model prediction polygons; boundaries inherit segmentation error.","NDVI/NDWI are supporting evidence only."]})
