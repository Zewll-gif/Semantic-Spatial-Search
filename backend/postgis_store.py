# CLEAN PROJECT HEADER
# ไฟล์: postgis_store.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Read-only, parameterized PostGIS access for the A7-T polygon tool contract.

No model output is ever executed as SQL. The only database object queried is
geoai_a7t.landcover_polygons, created by geoai_a7t_migration.sql.
"""
from __future__ import annotations

import json
import os
from typing import Any


def configured() -> bool:
    return bool(os.getenv("GEOAI_POSTGIS_DSN"))


def _fetch(sql: str, params: tuple[Any, ...], *, timeout_ms: int = 10000) -> list[dict[str, Any]]:
    dsn = os.getenv("GEOAI_POSTGIS_DSN")
    if not dsn:
        raise RuntimeError("GEOAI_POSTGIS_DSN is not configured")
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError as exc:
        raise RuntimeError("psycopg2 is required for PostGIS mode") from exc
    with psycopg2.connect(dsn, connect_timeout=5) as conn:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT set_config('statement_timeout', %s, true)", (str(timeout_ms),))
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


_COLUMNS = """polygon_id, class_code, class_name, area_m2, area_rai, area_ha,
    ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geometry_json"""
_SOURCE_COLUMNS = """s.polygon_id, s.class_code, s.class_name, s.area_m2,
    s.area_rai, s.area_ha,
    ST_AsGeoJSON(ST_Transform(s.geom, 4326)) AS geometry_json"""


def _features(rows: list[dict[str, Any]], *, distance: bool = False) -> list[dict[str, Any]]:
    features = []
    for row in rows:
        props = {
            "feature_id": int(row["polygon_id"]),
            "class_id": str(row["class_code"]),
            "class_name": str(row["class_name"]),
            "area_sqm": float(row["area_m2"]),
            "area_rai": float(row["area_rai"]),
            "area_hectare": float(row["area_ha"]),
            "source_model": "A7-T",
            "result_type": "model_prediction",
        }
        if distance:
            props["nearest_distance_m"] = float(row["nearest_distance_m"])
            if row.get("reference_feature_id") is not None:
                props["nearest_reference_feature_id"] = int(row["reference_feature_id"])
            if row.get("reference_class_code") is not None:
                props["nearest_reference_class_id"] = str(row["reference_class_code"])
            if row.get("reference_class_name") is not None:
                props["nearest_reference_class_name"] = str(row["reference_class_name"])
        features.append({"type": "Feature", "id": int(row["polygon_id"]),
                         "geometry": json.loads(row["geometry_json"]), "properties": props})
    return features


def _collection(rows: list[dict[str, Any]], *, distance: bool = False) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": _features(rows, distance=distance)}


def search(class_id: int, scope_wkt: str | None, limit: int, offset: int = 0) -> dict[str, Any]:
    if scope_wkt is None:
        total = _fetch("SELECT COUNT(*) AS n FROM geoai_a7t.landcover_polygons WHERE class_id = %s", (class_id,))[0]["n"]
    else:
        total = _fetch("SELECT COUNT(*) AS n FROM geoai_a7t.landcover_polygons WHERE class_id = %s AND ST_Intersects(geom, ST_GeomFromText(%s, 32647))", (class_id, scope_wkt))[0]["n"]
    if scope_wkt is None:
        predicate, params = "", (class_id, limit, offset)
    else:
        predicate, params = " AND ST_Intersects(geom, ST_GeomFromText(%s, 32647))", (class_id, scope_wkt, limit, offset)
    rows = _fetch(f"SELECT {_COLUMNS} FROM geoai_a7t.landcover_polygons "
                  "WHERE class_id = %s" + predicate +
                  " ORDER BY area_m2 DESC, polygon_id ASC LIMIT %s OFFSET %s", params)
    geojson = _collection(rows)
    return {"feature_ids": [feature["id"] for feature in geojson["features"]],
            "count": len(rows), "total_matches": int(total), "returned_features": len(rows),
            "display_limit": limit, "offset": offset, "truncated": int(total) > offset + len(rows),
            "summary": f"{total} R{class_id} features; showing {len(rows)}", "geojson": geojson}


def identify(lon: float, lat: float, class_id: int | None = None) -> dict[str, Any] | None:
    """Read-only indexed point lookup for one vector feature under a raster pixel."""
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("Invalid longitude or latitude")
    point = "ST_Transform(ST_SetSRID(ST_Point(%s, %s), 4326), 32647)"
    predicate = " AND class_id = %s" if class_id is not None else ""
    params = (lon, lat, class_id) if class_id is not None else (lon, lat)
    rows = _fetch(
        f"SELECT {_COLUMNS} FROM geoai_a7t.landcover_polygons "
        f"WHERE ST_Intersects(geom, {point}){predicate} "
        "ORDER BY area_m2 ASC, polygon_id ASC LIMIT 1",
        params,
    )
    features = _features(rows)
    return features[0] if features else None


def filter_area(feature_ids: list[int] | None, class_id: int | None,
                min_area_m2: float, max_area_m2: float | None, limit: int) -> list[dict[str, Any]]:
    if feature_ids is not None:
        predicate, selector = "polygon_id = ANY(%s)", feature_ids
    else:
        predicate, selector = "class_id = %s", class_id
    area_max_sql = "" if max_area_m2 is None else " AND area_m2 <= %s"
    params = (selector, min_area_m2, limit) if max_area_m2 is None else (selector, min_area_m2, max_area_m2, limit)
    return _fetch(
        "SELECT polygon_id, area_m2 FROM geoai_a7t.landcover_polygons WHERE " + predicate +
        " AND area_m2 >= %s" + area_max_sql +
        " ORDER BY area_m2 DESC, polygon_id ASC LIMIT %s",
        params,
    )


def near(source_class_id: int | None, source_feature_ids: list[int] | None,
         target_class_id: int, max_distance_m: float, min_area_m2: float, limit: int) -> dict[str, Any]:
    if source_feature_ids is not None:
        predicate, selector = "s.polygon_id = ANY(%s)", source_feature_ids
    else:
        predicate, selector = "s.class_id = %s", source_class_id
    rows = _fetch(
        f"SELECT {_SOURCE_COLUMNS}, "
        "t.nearest_distance_m, t.reference_feature_id, t.reference_class_code, "
        "t.reference_class_name, "
        "ST_AsGeoJSON(ST_Transform(t.reference_geom, 4326)) AS reference_geometry_json, "
        "ST_AsGeoJSON(ST_Transform(ST_Buffer(t.reference_geom, %s), 4326)) AS buffer_geometry_json, "
        "ST_AsGeoJSON(ST_Transform(ST_ShortestLine(s.geom, t.reference_geom), 4326)) AS distance_geometry_json "
        "FROM geoai_a7t.landcover_polygons AS s "
        "JOIN LATERAL (SELECT ref.polygon_id AS reference_feature_id, "
        "ref.class_code AS reference_class_code, ref.class_name AS reference_class_name, "
        "ref.geom AS reference_geom, ST_Distance(s.geom, ref.geom) AS nearest_distance_m "
        "FROM geoai_a7t.landcover_polygons AS ref "
        "WHERE ref.class_id = %s AND ST_DWithin(s.geom, ref.geom, %s) "
        "ORDER BY ST_Distance(s.geom, ref.geom) ASC LIMIT 1) AS t ON TRUE "
        "WHERE " + predicate + " AND s.area_m2 >= %s "
        # All rows satisfy the distance predicate. Present the largest matching
        # polygons first so the limited map preview remains visible at AOI scale.
        "ORDER BY s.area_m2 DESC, nearest_distance_m ASC, s.polygon_id ASC LIMIT %s",
        (max_distance_m, target_class_id, max_distance_m, selector, min_area_m2, limit),
        timeout_ms=30000,
    )
    geojson = _collection(rows, distance=True)
    references: dict[int, dict[str, Any]] = {}
    buffers: dict[int, dict[str, Any]] = {}
    distance_lines: list[dict[str, Any]] = []
    for row in rows:
        reference_id = row.get("reference_feature_id")
        reference_geometry = row.get("reference_geometry_json")
        buffer_geometry = row.get("buffer_geometry_json")
        distance_geometry = row.get("distance_geometry_json")
        if reference_id is not None and reference_geometry:
            reference_id = int(reference_id)
            references.setdefault(reference_id, {
                "type": "Feature",
                "id": reference_id,
                "geometry": json.loads(reference_geometry),
                "properties": {
                    "feature_id": reference_id,
                    "class_id": str(row.get("reference_class_code") or f"R{target_class_id}"),
                    "class_name": str(row.get("reference_class_name") or "Reference area"),
                    "role": "distance_reference",
                },
            })
            if buffer_geometry:
                buffers.setdefault(reference_id, {
                    "type": "Feature",
                    "id": reference_id,
                    "geometry": json.loads(buffer_geometry),
                    "properties": {
                        "reference_feature_id": reference_id,
                        "class_id": str(row.get("reference_class_code") or f"R{target_class_id}"),
                        "class_name": str(row.get("reference_class_name") or "Reference area"),
                        "buffer_distance_m": float(max_distance_m),
                        "role": "distance_buffer",
                    },
                })
        if distance_geometry:
            geometry = json.loads(distance_geometry)
            if geometry.get("coordinates"):
                distance_lines.append({
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "source_feature_id": int(row["polygon_id"]),
                        "source_class_id": str(row["class_code"]),
                        "reference_feature_id": int(reference_id) if reference_id is not None else None,
                        "reference_class_id": str(row.get("reference_class_code") or f"R{target_class_id}"),
                        "distance_m": float(row["nearest_distance_m"]),
                    },
                })
    return {"matching_source_features": [f["properties"] for f in geojson["features"]],
            "count": len(rows), "geojson": geojson, "max_distance_m": float(max_distance_m),
            "reference_target_class_id": f"R{target_class_id}",
            "distance_context": {
                "target_class_id": f"R{target_class_id}",
                "max_distance_m": float(max_distance_m),
                "buffers": {"type": "FeatureCollection", "features": list(buffers.values())},
                "references": {"type": "FeatureCollection", "features": list(references.values())},
                "lines": {"type": "FeatureCollection", "features": distance_lines},
                "distance_method": "exact buffer and shortest polygon-edge to polygon-edge line in EPSG:32647",
            }}


def by_ids(feature_ids: list[int]) -> dict[str, Any]:
    rows = _fetch(f"SELECT {_COLUMNS} FROM geoai_a7t.landcover_polygons "
                  "WHERE polygon_id = ANY(%s) ORDER BY polygon_id ASC", (feature_ids,))
    return _collection(rows)


def detail(feature_id: int) -> dict[str, Any] | None:
    rows = _fetch(f"SELECT {_COLUMNS}, ST_X(ST_Centroid(geom)) AS centroid_x, "
                  "ST_Y(ST_Centroid(geom)) AS centroid_y "
                  "FROM geoai_a7t.landcover_polygons WHERE polygon_id = %s LIMIT 1",
                  (feature_id,))
    if not rows:
        return None
    feature = _features(rows)[0]
    feature["properties"].update({"centroid_x": float(rows[0]["centroid_x"]),
                                  "centroid_y": float(rows[0]["centroid_y"]),
                                  "crs_area_distance": "EPSG:32647",
                                  "model_version": "A7_RGBN_REVISED7_TVERSKY"})
    return feature


def geometry_wkt(feature_id: int) -> str | None:
    rows = _fetch("SELECT ST_AsText(geom) AS wkt FROM geoai_a7t.landcover_polygons "
                  "WHERE polygon_id = %s LIMIT 1", (feature_id,))
    return rows[0]["wkt"] if rows else None


def distance(source_feature_id: int, target_feature_id: int) -> float | None:
    rows = _fetch("SELECT ST_Distance(a.geom, b.geom) AS distance_m "
                  "FROM geoai_a7t.landcover_polygons AS a "
                  "JOIN geoai_a7t.landcover_polygons AS b ON b.polygon_id = %s "
                  "WHERE a.polygon_id = %s", (target_feature_id, source_feature_id))
    return float(rows[0]["distance_m"]) if rows else None


def intersections(source_feature_id: int | None, source_class_id: int | None,
                  target_feature_id: int | None, target_class_id: int | None,
                  limit: int) -> list[dict[str, Any]]:
    source_predicate = "a.polygon_id = %s" if source_feature_id is not None else "a.class_id = %s"
    target_predicate = "b.polygon_id = %s" if target_feature_id is not None else "b.class_id = %s"
    return _fetch(
        "SELECT a.polygon_id AS source_feature_id, b.polygon_id AS target_feature_id, "
        "ST_Area(ST_Intersection(a.geom, b.geom)) AS intersection_area_sqm "
        "FROM geoai_a7t.landcover_polygons AS a "
        "JOIN geoai_a7t.landcover_polygons AS b ON ST_Intersects(a.geom, b.geom) "
        "WHERE " + source_predicate + " AND " + target_predicate +
        " ORDER BY a.polygon_id, b.polygon_id LIMIT %s",
        (source_feature_id if source_feature_id is not None else source_class_id,
         target_feature_id if target_feature_id is not None else target_class_id, limit),
    )


def health() -> dict[str, Any]:
    if not configured():
        return {"configured": False, "connected": False, "reason": "dsn_missing"}
    try:
        rows = _fetch("SELECT count(*)::bigint AS polygon_count FROM geoai_a7t.landcover_polygons", ())
        count = int(rows[0]["polygon_count"])
        privileges = _fetch(
            "SELECT has_table_privilege(current_user, 'geoai_a7t.landcover_polygons', 'INSERT') AS can_insert, "
            "has_table_privilege(current_user, 'geoai_a7t.landcover_polygons', 'UPDATE') AS can_update, "
            "has_table_privilege(current_user, 'geoai_a7t.landcover_polygons', 'DELETE') AS can_delete",
            (),
        )[0]
        return {"configured": True, "connected": True, "data_loaded": count > 0,
                "polygon_count": count,
                "role_read_only": not any(privileges.values())}
    except Exception as exc:
        reason = "driver_missing" if "psycopg2 is required" in str(exc) else type(exc).__name__
        return {"configured": True, "connected": False, "reason": reason}
