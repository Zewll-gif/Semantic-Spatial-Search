# CLEAN PROJECT HEADER
# ไฟล์: query_plan_probe.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Read-only EXPLAIN for the canonical proximity query."""
from __future__ import annotations

import os
import psycopg2
from local_env import load_local_env

load_local_env()
with psycopg2.connect(os.environ["GEOAI_POSTGIS_DSN"], connect_timeout=5) as conn:
    conn.set_session(readonly=True)
    with conn.cursor() as cur:
        cur.execute("""EXPLAIN SELECT s.polygon_id,
            t.nearest_distance_m
            FROM geoai_a7t.landcover_polygons AS s
            JOIN LATERAL (
              SELECT ST_Distance(s.geom, ref.geom) AS nearest_distance_m
              FROM geoai_a7t.landcover_polygons AS ref
              WHERE ref.class_id=4 AND ST_DWithin(s.geom, ref.geom, 300)
              ORDER BY ST_Distance(s.geom, ref.geom) ASC LIMIT 1
            ) AS t ON TRUE
            WHERE s.class_id=2 AND s.area_m2>=8000
            ORDER BY nearest_distance_m ASC, s.polygon_id ASC LIMIT 3""")
        for row in cur:
            print(row[0])
