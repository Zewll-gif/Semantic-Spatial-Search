# CLEAN PROJECT HEADER
# ไฟล์: gis_tools.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Deterministic GIS tools backed by the existing A7-T GeoPackage and rasters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime_env import configure_geospatial_environment

configure_geospatial_environment()

from pyproj import Transformer
from shapely.geometry import LineString, Point, box, mapping, shape
from shapely.ops import nearest_points, transform
from shapely.wkt import loads as load_wkt

try:
    import geoai_api as legacy
    import postgis_store
    from canonical_schema import class_by_id
except ImportError:  # pragma: no cover
    from . import geoai_api as legacy
    from . import postgis_store
    from .canonical_schema import class_by_id

DISPLAY_TO_PROJECTED = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform
PROJECTED_TO_DISPLAY = Transformer.from_crs("EPSG:32647", "EPSG:4326", always_xy=True).transform
UNIT_TO_M2 = {"sqm": 1.0, "m2": 1.0, "m²": 1.0, "rai": 1600.0, "ไร่": 1600.0, "hectare": 10000.0, "ha": 10000.0}


@dataclass
class ToolError(Exception):
    code: str
    message: str
    status_code: int = 400

    def as_dict(self) -> dict[str, Any]:
        return {"status": "error", "error": {"code": self.code, "message": self.message}}


def _class_numeric(class_id: str) -> int:
    item = class_by_id(class_id)
    if not item:
        raise ToolError("unsupported_class", f"Unknown canonical class id: {class_id}")
    return int(item["numeric_id"])


def _factor(unit: str) -> float:
    key = str(unit).lower().strip()
    if key not in UNIT_TO_M2:
        raise ToolError("invalid_parameter", f"Unsupported area unit: {unit}")
    return UNIT_TO_M2[key]


def _scope_geometry(bbox: list[float] | None = None, geometry: dict[str, Any] | None = None):
    if bbox is not None and geometry is not None:
        raise ToolError("invalid_parameter", "Provide bbox or geometry, not both")
    if bbox is not None:
        if len(bbox) != 4 or float(bbox[0]) >= float(bbox[2]) or float(bbox[1]) >= float(bbox[3]):
            raise ToolError("invalid_parameter", "bbox must be [min_lon,min_lat,max_lon,max_lat]")
        return transform(DISPLAY_TO_PROJECTED, box(*map(float, bbox)))
    if geometry is not None:
        try:
            return transform(DISPLAY_TO_PROJECTED, shape(geometry))
        except Exception as exc:
            raise ToolError("invalid_parameter", f"Invalid GeoJSON geometry: {exc}") from exc
    return None


def _row_feature(row, distance_m: float | None = None) -> dict[str, Any]:
    props = {
        "feature_id": int(row.polygon_id),
        "class_id": str(row.class_code),
        "class_name": str(row.class_name),
        "area_sqm": float(row.area_m2),
        "area_rai": float(row.area_rai),
        "area_hectare": float(row.area_ha),
        "source_model": "A7-T",
        "result_type": "model_prediction",
    }
    if distance_m is not None:
        props["nearest_distance_m"] = float(distance_m)
    geometry = transform(PROJECTED_TO_DISPLAY, row.geometry)
    return {"type": "Feature", "id": int(row.polygon_id), "geometry": mapping(geometry), "properties": props}


def _collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def _postgis_call(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        # An explicitly configured database must not silently switch datasets.
        raise ToolError("postgis_unavailable", f"PostGIS query failed: {type(exc).__name__}", 503) from exc


def search_landcover(class_id: str, bbox: list[float] | None = None, geometry: dict[str, Any] | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    if not 1 <= int(limit) <= 100:
        raise ToolError("invalid_parameter", "limit must be between 1 and 100")
    if int(offset) < 0:
        raise ToolError("invalid_parameter", "offset must be >= 0")
    numeric = _class_numeric(class_id)
    scope = _scope_geometry(bbox, geometry)
    if postgis_store.configured():
        return _postgis_call(postgis_store.search, numeric, scope.wkt if scope is not None else None, int(limit), int(offset))
    data = legacy.repo()
    selected = data[data.class_id == numeric]
    if scope is not None:
        selected = selected[selected.geometry.intersects(scope)]
    total = len(selected)
    selected = selected.sort_values(["area_m2", "polygon_id"], ascending=[False, True]).iloc[int(offset):int(offset)+int(limit)]
    features = [_row_feature(row) for _, row in selected.iterrows()]
    return {"feature_ids": [f["id"] for f in features], "count": len(features),
            "total_matches": total, "returned_features": len(features), "display_limit": limit,
            "offset": offset, "truncated": total > offset + len(features),
            "summary": f"{total} {class_id} features; showing {len(features)}", "geojson": _collection(features)}


def identify_landcover(lon: float, lat: float, class_id: str | None = None) -> dict[str, Any] | None:
    """Identify one feature under a point, using the same vector backend as search."""
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ToolError("invalid_parameter", "Invalid longitude or latitude")
    numeric = _class_numeric(class_id) if class_id else None
    if postgis_store.configured():
        return _postgis_call(postgis_store.identify, lon, lat, numeric)
    point = transform(DISPLAY_TO_PROJECTED, Point(lon, lat))
    data = legacy.repo()
    matches = data.iloc[data.sindex.query(point, predicate="intersects")]
    if numeric is not None:
        matches = matches[matches.class_id == numeric]
    if matches.empty:
        return None
    row = matches.sort_values(["area_m2", "polygon_id"], ascending=[True, True]).iloc[0]
    return _row_feature(row)


def filter_by_area(feature_ids: list[int] | None = None, class_id: str | None = None, min_area: float = 0.0, max_area: float | None = None, unit: str = "sqm", limit: int = 100) -> dict[str, Any]:
    if min_area < 0 or (max_area is not None and max_area < 0):
        raise ToolError("invalid_parameter", "area must be >= 0")
    if max_area is not None and max_area < min_area:
        raise ToolError("invalid_parameter", "max_area must be >= min_area")
    factor = _factor(unit)
    if postgis_store.configured():
        if not 1 <= int(limit) <= 100:
            raise ToolError("invalid_parameter", "limit must be between 1 and 100")
        if feature_ids is None and not class_id:
            raise ToolError("invalid_parameter", "feature_ids or class_id is required")
        rows = _postgis_call(postgis_store.filter_area, feature_ids,
                             _class_numeric(class_id) if feature_ids is None else None,
                             float(min_area) * factor,
                             float(max_area) * factor if max_area is not None else None,
                             int(limit))
        values = [{"feature_id": int(row["polygon_id"]), "area": float(row["area_m2"]) / factor,
                   "unit": unit, "area_sqm": float(row["area_m2"])} for row in rows]
        return {"filtered_ids": [x["feature_id"] for x in values], "count": len(values), "area_values": values}
    data = legacy.repo()
    selected = data
    if feature_ids:
        selected = selected[selected.polygon_id.isin([int(x) for x in feature_ids])]
    elif class_id:
        selected = selected[selected.class_id == _class_numeric(class_id)]
    else:
        raise ToolError("invalid_parameter", "feature_ids or class_id is required")
    selected = selected[selected.area_m2 >= float(min_area) * factor]
    if max_area is not None:
        selected = selected[selected.area_m2 <= float(max_area) * factor]
    selected = selected.sort_values("area_m2", ascending=False).head(int(limit))
    values = []
    for _, row in selected.iterrows():
        values.append({"feature_id": int(row.polygon_id), "area": float(row.area_m2) / factor, "unit": unit, "area_sqm": float(row.area_m2)})
    return {"filtered_ids": [x["feature_id"] for x in values], "count": len(values), "area_values": values}


def find_nearby(source_class_id: str | None = None, source_feature_ids: list[int] | None = None, target_class_id: str | None = None, max_distance_m: float = 0, limit: int = 20, min_area: float = 0, area_unit: str = "sqm") -> dict[str, Any]:
    if not 0 < max_distance_m <= 100000:
        raise ToolError("invalid_parameter", "max_distance_m must be > 0 and <= 100000")
    if min_area < 0:
        raise ToolError("invalid_parameter", "min_area must be >= 0")
    if not target_class_id:
        raise ToolError("invalid_parameter", "target_class_id is required")
    if postgis_store.configured():
        if not 1 <= int(limit) <= 100:
            raise ToolError("invalid_parameter", "limit must be between 1 and 100")
        if not source_feature_ids and not source_class_id:
            raise ToolError("invalid_parameter", "source_class_id or source_feature_ids is required")
        return _postgis_call(postgis_store.near,
                             _class_numeric(source_class_id) if not source_feature_ids else None,
                             source_feature_ids, _class_numeric(target_class_id),
                             float(max_distance_m), float(min_area) * _factor(area_unit), int(limit))
    data = legacy.repo()
    if source_feature_ids:
        sources = data[data.polygon_id.isin([int(x) for x in source_feature_ids])]
    elif source_class_id:
        sources = data[data.class_id == _class_numeric(source_class_id)]
    else:
        raise ToolError("invalid_parameter", "source_class_id or source_feature_ids is required")
    sources = sources[sources.area_m2 >= float(min_area) * _factor(area_unit)]
    targets = data[data.class_id == _class_numeric(target_class_id)]
    if sources.empty or targets.empty:
        return {"matching_source_features": [], "count": 0, "geojson": _collection([])}
    rows: list[tuple[float, Any, Any]] = []
    for _, row in sources.iterrows():
        distances = targets.geometry.distance(row.geometry)
        nearest_index = distances.idxmin()
        reference = targets.loc[nearest_index]
        distance = float(distances.loc[nearest_index])
        if distance <= float(max_distance_m):
            rows.append((distance, row, reference))
    rows.sort(key=lambda x: (-float(x[1].area_m2), x[0], int(x[1].polygon_id)))
    selected = rows[: int(limit)]
    features = []
    references: dict[int, dict[str, Any]] = {}
    buffers: dict[int, dict[str, Any]] = {}
    lines: list[dict[str, Any]] = []
    for distance, row, reference in selected:
        feature = _row_feature(row, distance)
        reference_id = int(reference.polygon_id)
        feature["properties"].update({
            "nearest_reference_feature_id": reference_id,
            "nearest_reference_class_id": str(reference.class_code),
            "nearest_reference_class_name": str(reference.class_name),
        })
        features.append(feature)
        references.setdefault(reference_id, {
            "type": "Feature", "id": reference_id,
            "geometry": mapping(transform(PROJECTED_TO_DISPLAY, reference.geometry)),
            "properties": {"feature_id": reference_id, "class_id": str(reference.class_code),
                           "class_name": str(reference.class_name), "role": "distance_reference"},
        })
        reference_buffer = reference.geometry.buffer(float(max_distance_m))
        if not reference_buffer.is_empty:
            buffers.setdefault(reference_id, {
                "type": "Feature", "id": reference_id,
                "geometry": mapping(transform(PROJECTED_TO_DISPLAY, reference_buffer)),
                "properties": {
                    "reference_feature_id": reference_id,
                    "class_id": str(reference.class_code),
                    "class_name": str(reference.class_name),
                    "buffer_distance_m": float(max_distance_m),
                    "role": "distance_buffer",
                },
            })
        start, end = nearest_points(row.geometry, reference.geometry)
        line = transform(PROJECTED_TO_DISPLAY, LineString([start, end]))
        if not line.is_empty:
            lines.append({"type": "Feature", "geometry": mapping(line), "properties": {
                "source_feature_id": int(row.polygon_id), "source_class_id": str(row.class_code),
                "reference_feature_id": reference_id, "reference_class_id": str(reference.class_code),
                "distance_m": distance,
            }})
    return {"matching_source_features": [f["properties"] for f in features], "count": len(features), "geojson": _collection(features), "max_distance_m": float(max_distance_m), "reference_target_class_id": target_class_id,
            "distance_context": {"target_class_id": target_class_id, "max_distance_m": float(max_distance_m),
                                 "buffers": _collection(list(buffers.values())),
                                 "references": _collection(list(references.values())), "lines": _collection(lines),
                                 "distance_method": "exact buffer and shortest polygon-edge to polygon-edge line in EPSG:32647"}}


def calculate_distance(source_feature_id: int, target_feature_id: int) -> dict[str, Any]:
    if postgis_store.configured():
        distance_m = _postgis_call(postgis_store.distance, int(source_feature_id), int(target_feature_id))
        if distance_m is None:
            raise ToolError("no_result", "One or both feature IDs were not found", 404)
        return {"source_feature_id": int(source_feature_id), "target_feature_id": int(target_feature_id), "distance_m": distance_m}
    source = legacy.get_geom_by_id(int(source_feature_id))
    target = legacy.get_geom_by_id(int(target_feature_id))
    return {"source_feature_id": int(source_feature_id), "target_feature_id": int(target_feature_id), "distance_m": float(source.distance(target))}


def intersects(source_feature_id: int | None = None, source_class_id: str | None = None, target_feature_id: int | None = None, target_class_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    if postgis_store.configured():
        if not 1 <= int(limit) <= 100:
            raise ToolError("invalid_parameter", "limit must be between 1 and 100")
        if source_feature_id is None and not source_class_id:
            raise ToolError("invalid_parameter", "source feature/class is required")
        if target_feature_id is None and not target_class_id:
            raise ToolError("invalid_parameter", "target feature/class is required")
        rows = _postgis_call(postgis_store.intersections, source_feature_id,
                             _class_numeric(source_class_id) if source_feature_id is None else None,
                             target_feature_id,
                             _class_numeric(target_class_id) if target_feature_id is None else None,
                             int(limit))
        return {"relationships": rows, "count": len(rows)}
    data = legacy.repo()
    if source_feature_id is not None:
        sources = data[data.polygon_id == int(source_feature_id)]
    elif source_class_id:
        sources = data[data.class_id == _class_numeric(source_class_id)]
    else:
        raise ToolError("invalid_parameter", "source feature/class is required")
    if target_feature_id is not None:
        targets = data[data.polygon_id == int(target_feature_id)]
    elif target_class_id:
        targets = data[data.class_id == _class_numeric(target_class_id)]
    else:
        raise ToolError("invalid_parameter", "target feature/class is required")
    relationships = []
    for _, source in sources.iterrows():
        for _, target in targets[targets.geometry.intersects(source.geometry)].iterrows():
            relationships.append({"source_feature_id": int(source.polygon_id), "target_feature_id": int(target.polygon_id), "intersection_area_sqm": float(source.geometry.intersection(target.geometry).area)})
            if len(relationships) >= int(limit):
                return {"relationships": relationships, "count": len(relationships)}
    return {"relationships": relationships, "count": len(relationships)}


def get_feature_details(feature_id: int) -> dict[str, Any]:
    if postgis_store.configured():
        feature = _postgis_call(postgis_store.detail, int(feature_id))
        if feature is None:
            raise ToolError("no_result", f"feature_id {feature_id} not found", 404)
        return feature
    data = legacy.repo()
    rows = data[data.polygon_id == int(feature_id)]
    if rows.empty:
        raise ToolError("no_result", f"feature_id {feature_id} not found", 404)
    row = rows.iloc[0]
    feature = _row_feature(row)
    feature["properties"].update({"centroid_x": float(row.centroid_x), "centroid_y": float(row.centroid_y), "crs_area_distance": "EPSG:32647", "model_version": "A7_RGBN_REVISED7_TVERSKY"})
    return feature


def get_index_stats(index_name: str, feature_id: int | None = None, geometry: dict[str, Any] | None = None) -> dict[str, Any]:
    if (feature_id is None) == (geometry is None):
        raise ToolError("invalid_parameter", "Provide exactly one of feature_id or geometry")
    if feature_id is not None and postgis_store.configured():
        wkt = _postgis_call(postgis_store.geometry_wkt, int(feature_id))
        if wkt is None:
            raise ToolError("no_result", f"feature_id {feature_id} not found", 404)
        geom = load_wkt(wkt)
    else:
        geom = legacy.get_geom_by_id(int(feature_id)) if feature_id is not None else _scope_geometry(geometry=geometry)
    path = legacy.NDVI if index_name.lower() == "ndvi" else legacy.NDWI if index_name.lower() == "ndwi" else None
    if path is None:
        raise ToolError("invalid_parameter", "index_name must be ndvi or ndwi")
    stats = legacy.spectral_stats(path, geom)
    if not stats.get("count"):
        raise ToolError("unavailable_data", f"No {index_name.upper()} pixels available for this geometry", 404)
    return {"index": index_name.upper(), **stats}


def get_geojson(feature_ids: list[int]) -> dict[str, Any]:
    if not feature_ids:
        raise ToolError("invalid_parameter", "feature_ids cannot be empty")
    if postgis_store.configured():
        if len(feature_ids) > 100:
            raise ToolError("invalid_parameter", "feature_ids cannot exceed 100")
        return _postgis_call(postgis_store.by_ids, [int(x) for x in feature_ids])
    data = legacy.repo()
    selected = data[data.polygon_id.isin([int(x) for x in feature_ids])]
    features = [_row_feature(row) for _, row in selected.iterrows()]
    return _collection(features)


def get_evidence(feature_id: int) -> dict[str, Any]:
    feature = get_feature_details(feature_id)
    ndvi = get_index_stats("ndvi", feature_id=feature_id)
    ndwi = get_index_stats("ndwi", feature_id=feature_id)
    return {
        "feature": feature,
        "model": {"source_model": "A7-T", "model_version": "A7_RGBN_REVISED7_TVERSKY", "result_type": "model_prediction"},
        "spatial_evidence": feature["properties"],
        "spectral_evidence": {"ndvi": ndvi, "ndwi": ndwi},
        "external_comparison": {"status": "available_separately", "note": "External consistency is contextual evidence, not Ground Truth."},
    }
