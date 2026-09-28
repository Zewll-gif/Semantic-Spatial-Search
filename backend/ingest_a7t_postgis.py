# CLEAN PROJECT HEADER
# ไฟล์: ingest_a7t_postgis.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""One-time, transactional A7-T vector import. Never touches source artifacts.

Execute only after reviewing the dry-run output: python ingest_a7t_postgis.py --execute
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from local_env import load_local_env
from project_paths import VECTOR_GPKG, VECTOR_ROOT

SOURCE = VECTOR_GPKG
AUDIT = VECTOR_ROOT / "qa" / "VECTOR_BACKEND_AUDIT.json"
MIGRATION = Path(__file__).with_name("geoai_a7t_migration.sql")
FIELDS = ("polygon_id", "class_id", "class_code", "class_name", "area_m2",
          "area_ha", "area_km2", "area_rai", "perimeter_m", "source_model",
          "source_raster", "model_version")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    load_local_env()
    import os
    import sqlite3
    import psycopg2
    from psycopg2.extras import execute_values
    from osgeo import ogr

    expected = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert SOURCE.resolve() == Path(expected["polygon_output"]["clean"]).resolve()
    assert all(row["pass"] for row in expected["area_qa"])
    with sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True) as source_db:
        count = source_db.execute("SELECT count(*) FROM polygons").fetchone()[0]
        counts = dict(source_db.execute("SELECT class_id,count(*) FROM polygons GROUP BY class_id"))
        areas = dict(source_db.execute("SELECT class_id,sum(area_m2) FROM polygons GROUP BY class_id"))
        identities = source_db.execute("SELECT DISTINCT source_model,model_version,crs FROM polygons").fetchall()
    assert count == expected["feature_count"] == 155199
    assert all(counts.get(int(k), 0) == v for k, v in expected["class_counts"].items())
    assert all(abs(areas.get(row["class_id"], 0) - row["vector_area_m2"]) < 0.01
               for row in expected["area_qa"])
    assert identities == [("A7-T", "A7_RGBN_REVISED7_TVERSKY", "EPSG:32647")]
    ds = ogr.Open(str(SOURCE), 0)
    assert ds is not None
    layer = ds.GetLayerByName("polygons")
    assert layer is not None and layer.GetFeatureCount() == count
    assert "+proj=utm +zone=47 +datum=WGS84" in layer.GetSpatialRef().ExportToProj4()
    print("SOURCE_QA=PASS count=" + str(count) + " classes=" + json.dumps(counts, sort_keys=True))

    with psycopg2.connect(os.environ["GEOAI_POSTGIS_DSN"], connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('geoai_a7t.landcover_polygons') IS NOT NULL")
            if cur.fetchone()[0]:
                raise RuntimeError("Destination table already exists; refusing to overwrite or append")
            cur.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='postgis')")
            assert cur.fetchone()[0], "PostGIS extension unavailable"
        if not args.execute:
            conn.rollback()
            print("DRY_RUN=PASS destination_empty=True changes=0")
            return
        with conn.cursor() as cur:
            cur.execute(MIGRATION.read_text(encoding="utf-8"))
            rows = []
            loaded = 0
            sql = ("INSERT INTO geoai_a7t.landcover_polygons (" + ",".join(FIELDS) + ",geom) VALUES %s")
            template = "(" + ",".join(["%s"] * len(FIELDS)) + ",ST_Multi(ST_GeomFromWKB(%s,32647)))"
            for feature in layer:
                geom = feature.GetGeometryRef()
                assert geom is not None and not geom.IsEmpty()
                rows.append(tuple(feature.GetField(field) for field in FIELDS) +
                            (psycopg2.Binary(geom.ExportToWkb()),))
                if len(rows) >= 250:
                    execute_values(cur, sql, rows, template=template, page_size=250)
                    loaded += len(rows)
                    rows.clear()
                    if loaded % 25000 == 0:
                        print("LOADED=" + str(loaded), flush=True)
            if rows:
                execute_values(cur, sql, rows, template=template, page_size=250)
                loaded += len(rows)
            cur.execute("SELECT class_id,count(*),sum(area_m2),count(*) FILTER (WHERE NOT ST_IsValid(geom)) "
                        "FROM geoai_a7t.landcover_polygons GROUP BY class_id")
            result = cur.fetchall()
            assert loaded == count == sum(row[1] for row in result)
            assert all(row[1] == counts[row[0]] and abs(row[2] - areas[row[0]]) < .01
                       and row[3] == 0 for row in result)
            cur.execute("SELECT count(*) FROM pg_indexes WHERE schemaname='geoai_a7t' "
                        "AND indexname='landcover_polygons_geom_gist'")
            assert cur.fetchone()[0] == 1
        conn.commit()
    print("POSTGIS_IMPORT=PASS count=" + str(loaded) + " area_by_class=" +
          json.dumps({row[0]: round(row[2], 2) for row in result}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # DSN and server responses may contain credentials; print type only.
        print("IMPORT_FAILED=" + type(exc).__name__)
        raise SystemExit(1)
