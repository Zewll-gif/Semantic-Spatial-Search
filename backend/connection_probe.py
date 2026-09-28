# CLEAN PROJECT HEADER
# ไฟล์: connection_probe.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Read-only, secret-free connection diagnostics for the local operator."""
from __future__ import annotations

import json
import os

from local_env import load_local_env


def main() -> None:
    load_local_env()
    print("CONFIG_PRESENT=" + json.dumps({
        key: bool(os.getenv(key)) for key in ("GEOAI_POSTGIS_DSN", "OPENAI_API_KEY", "AGENT_MODEL")
    }, sort_keys=True))
    try:
        import psycopg2
        with psycopg2.connect(os.environ["GEOAI_POSTGIS_DSN"], connect_timeout=5) as conn:
            conn.set_session(readonly=True)
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '10000ms'")
                cur.execute("""SELECT n.nspname, c.relname, c.relkind
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE c.relkind IN ('r','v','m') AND
                    (n.nspname ILIKE '%geoai%' OR c.relname ILIKE '%polygon%' OR
                     c.relname ILIKE '%landcover%') ORDER BY 1,2""")
                print("RELEVANT_TABLES=" + json.dumps(cur.fetchall()))
                cur.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='postgis')")
                print("POSTGIS_INSTALLED=" + json.dumps(cur.fetchone()[0]))
                cur.execute("SELECT has_database_privilege(current_user,current_database(),'CREATE'), "
                            "has_schema_privilege(current_user,'public','CREATE')")
                print("CREATE_PRIVILEGES=" + json.dumps(cur.fetchone()))
                cur.execute("SELECT to_regclass('geoai_a7t.landcover_polygons') IS NOT NULL")
                exists = cur.fetchone()[0]
                print("EXPECTED_TABLE_EXISTS=" + json.dumps(exists))
                if exists:
                    from postgis_store import health
                    print("POSTGIS_HEALTH=" + json.dumps(health(), sort_keys=True))
    except Exception as exc:
        # Never expose exception text, which may contain DSN details.
        print("PROBE_ERROR_TYPE=" + type(exc).__name__)


if __name__ == "__main__":
    main()
