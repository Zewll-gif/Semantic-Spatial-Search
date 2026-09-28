"""Compare the canonical A7-T GeoPackage with the production PostGIS table."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND = APP_ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def same_number(left: float, right: float, tolerance: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    values = load_env(args.env)
    dsn = values.get("GEOAI_POSTGIS_DSN")
    if not dsn:
        raise RuntimeError("GEOAI_POSTGIS_DSN is missing")
    os.environ["GEOAI_POSTGIS_DSN"] = dsn

    import psycopg2
    from osgeo import ogr
    from project_paths import VECTOR_GPKG
    import gis_tools

    source = VECTOR_GPKG.resolve()
    ds = ogr.Open(str(source), 0)
    if ds is None:
        raise RuntimeError("Canonical GeoPackage cannot be opened")
    layer = ds.GetLayerByName("polygons")
    source_count = int(layer.GetFeatureCount())
    source_extent_raw = layer.GetExtent()
    source_bounds = [source_extent_raw[0], source_extent_raw[2], source_extent_raw[1], source_extent_raw[3]]
    spatial_ref = layer.GetSpatialRef()
    authority = spatial_ref.GetAuthorityCode(None) or spatial_ref.GetAuthorityCode("PROJCS")
    source_srid = int(authority) if authority else 32647 if "UTM zone 47N" in spatial_ref.ExportToWkt() else -1
    source_counts: dict[int, int] = {}
    source_areas: dict[int, float] = {}
    source_ids: list[int] = []
    source_attrs: dict[int, tuple] = {}
    for feature in layer:
        class_id = int(feature.GetField("class_id"))
        polygon_id = int(feature.GetField("polygon_id"))
        source_ids.append(polygon_id)
        source_counts[class_id] = source_counts.get(class_id, 0) + 1
        source_areas[class_id] = source_areas.get(class_id, 0.0) + float(feature.GetField("area_m2"))
    source_ids.sort()
    sample_ids = [source_ids[0], source_ids[len(source_ids) // 2], source_ids[-1]]
    layer.ResetReading()
    wanted = set(sample_ids)
    for feature in layer:
        polygon_id = int(feature.GetField("polygon_id"))
        if polygon_id in wanted:
            source_attrs[polygon_id] = (
                int(feature.GetField("class_id")),
                str(feature.GetField("class_code")),
                str(feature.GetField("class_name")),
                float(feature.GetField("area_m2")),
                str(feature.GetField("source_model")),
                str(feature.GetField("model_version")),
            )

    with psycopg2.connect(dsn, connect_timeout=5) as conn:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*)::bigint, count(*) FILTER (WHERE NOT ST_IsValid(geom)), "
                "ST_SRID(geom), ST_XMin(ST_Extent(geom)), ST_YMin(ST_Extent(geom)), "
                "ST_XMax(ST_Extent(geom)), ST_YMax(ST_Extent(geom)) "
                "FROM geoai_a7t.landcover_polygons GROUP BY ST_SRID(geom)"
            )
            db_count, db_invalid, db_srid, xmin, ymin, xmax, ymax = cur.fetchone()
            db_bounds = [float(xmin), float(ymin), float(xmax), float(ymax)]
            cur.execute(
                "SELECT class_id, count(*)::bigint, sum(area_m2)::double precision "
                "FROM geoai_a7t.landcover_polygons GROUP BY class_id ORDER BY class_id"
            )
            db_rows = cur.fetchall()
            db_counts = {int(row[0]): int(row[1]) for row in db_rows}
            db_areas = {int(row[0]): float(row[2]) for row in db_rows}
            cur.execute(
                "SELECT polygon_id,class_id,class_code,class_name,area_m2,source_model,model_version "
                "FROM geoai_a7t.landcover_polygons WHERE polygon_id=ANY(%s) ORDER BY polygon_id",
                (sample_ids,),
            )
            db_attrs = {
                int(row[0]): (int(row[1]), str(row[2]), str(row[3]), float(row[4]), str(row[5]), str(row[6]))
                for row in cur.fetchall()
            }
            cur.execute(
                "SELECT has_table_privilege(current_user,'geoai_a7t.landcover_polygons','SELECT'), "
                "has_table_privilege(current_user,'geoai_a7t.landcover_polygons','INSERT'), "
                "has_table_privilege(current_user,'geoai_a7t.landcover_polygons','UPDATE'), "
                "has_table_privilege(current_user,'geoai_a7t.landcover_polygons','DELETE'), "
                "current_setting('default_transaction_read_only')"
            )
            can_select, can_insert, can_update, can_delete, default_readonly = cur.fetchone()

    rows: list[dict[str, object]] = []

    def add(metric: str, source_value: object, postgis_value: object, status: bool, tolerance: str = "exact", notes: str = "") -> None:
        rows.append({
            "metric": metric,
            "source_value": source_value,
            "postgis_value": postgis_value,
            "tolerance": tolerance,
            "status": "PASS" if status else "FAIL",
            "notes": notes,
        })

    add("feature_count", source_count, int(db_count), source_count == int(db_count))
    add("crs_epsg", source_srid, int(db_srid), source_srid == int(db_srid) == 32647)
    add("invalid_geometry_count", 0, int(db_invalid), int(db_invalid) == 0)
    add("bounds", json.dumps(source_bounds), json.dumps(db_bounds), all(same_number(a, b, 0.001) for a, b in zip(source_bounds, db_bounds)), "0.001 m")
    for class_id in sorted(source_counts):
        add(f"R{class_id}_feature_count", source_counts[class_id], db_counts.get(class_id), source_counts[class_id] == db_counts.get(class_id))
        add(f"R{class_id}_total_area_m2", round(source_areas[class_id], 6), round(db_areas.get(class_id, 0.0), 6), same_number(source_areas[class_id], db_areas.get(class_id, 0.0), 0.01), "0.01 m2")
    for polygon_id in sample_ids:
        source_row = source_attrs[polygon_id]
        db_row = db_attrs.get(polygon_id)
        comparable = db_row is not None and source_row[:3] == db_row[:3] and same_number(source_row[3], db_row[3], 0.001) and source_row[4:] == db_row[4:]
        add(f"sample_feature_{polygon_id}", json.dumps(source_row, ensure_ascii=False), json.dumps(db_row, ensure_ascii=False), comparable, "attributes exact; area 0.001 m2")
    add("application_role_select", True, bool(can_select), bool(can_select))
    add("application_role_insert", False, bool(can_insert), not can_insert)
    add("application_role_update", False, bool(can_update), not can_update)
    add("application_role_delete", False, bool(can_delete), not can_delete)
    add("default_transaction_read_only", "on", default_readonly, default_readonly == "on")

    def run_queries(use_postgis: bool) -> dict[str, object]:
        if use_postgis:
            os.environ["GEOAI_POSTGIS_DSN"] = dsn
        else:
            os.environ.pop("GEOAI_POSTGIS_DSN", None)
        search = gis_tools.search_landcover("R4", limit=5)
        area = gis_tools.filter_by_area(class_id="R2", min_area=5, unit="rai", limit=5)
        r2_id = int(area["filtered_ids"][0])
        r4_id = int(search["feature_ids"][0])
        distance = gis_tools.calculate_distance(r2_id, r4_id)
        near = gis_tools.find_nearby(source_class_id="R2", target_class_id="R4", max_distance_m=300, min_area=5, area_unit="rai", limit=3)
        intersection = gis_tools.intersects(source_feature_id=r2_id, target_class_id="R4", limit=5)
        geojson = gis_tools.get_geojson([r2_id, r4_id])
        ndvi = gis_tools.get_index_stats("ndvi", feature_id=r2_id)
        ndwi = gis_tools.get_index_stats("ndwi", feature_id=r2_id)
        return {
            "search_ids": search["feature_ids"],
            "search_total": search.get("total_matches"),
            "area_ids": area["filtered_ids"],
            "distance": distance.get("distance_m"),
            "near_ids": [item["feature_id"] for item in near.get("matching_source_features", [])],
            "near_distances": [item["nearest_distance_m"] for item in near.get("matching_source_features", [])],
            "intersection_rows": intersection.get("relationships", []),
            "geojson_ids": [feature.get("id") for feature in geojson.get("features", [])],
            "ndvi": {key: ndvi.get(key) for key in ("count", "min", "max", "mean", "median")},
            "ndwi": {key: ndwi.get(key) for key in ("count", "min", "max", "mean", "median")},
        }

    gpkg_queries = run_queries(False)
    postgis_queries = run_queries(True)
    for key in ("search_ids", "search_total", "area_ids", "near_ids", "intersection_rows", "geojson_ids"):
        add(f"query_{key}", json.dumps(gpkg_queries[key], ensure_ascii=False, sort_keys=True), json.dumps(postgis_queries[key], ensure_ascii=False, sort_keys=True), gpkg_queries[key] == postgis_queries[key])
    add("query_distance_m", gpkg_queries["distance"], postgis_queries["distance"], same_number(gpkg_queries["distance"], postgis_queries["distance"], 0.001), "0.001 m")
    for key in ("near_distances",):
        left, right = gpkg_queries[key], postgis_queries[key]
        ok = len(left) == len(right) and all(same_number(a, b, 0.001) for a, b in zip(left, right))
        add(f"query_{key}", json.dumps(left), json.dumps(right), ok, "0.001 m")
    for key in ("ndvi", "ndwi"):
        left, right = gpkg_queries[key], postgis_queries[key]
        ok = left["count"] == right["count"] and all(
            same_number(left[name], right[name], 1e-6) for name in ("min", "max", "mean", "median")
        )
        add(f"query_{key}_stats", json.dumps(left, sort_keys=True), json.dumps(right, sort_keys=True), ok, "1e-6")

    csv_path = args.output / "POSTGIS_QA.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "source_value", "postgis_value", "tolerance", "status", "notes"])
        writer.writeheader()
        writer.writerows(rows)
    failed = [row for row in rows if row["status"] != "PASS"]
    summary = {
        "source": str(source),
        "postgis_table": "geoai_a7t.landcover_polygons",
        "postgis_primary": True,
        "geopackage_fallback_only": True,
        "checks": len(rows),
        "passed": len(rows) - len(failed),
        "failed": len(failed),
        "status": "PASS" if not failed else "FAIL",
    }
    (args.output / "POSTGIS_QA.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
