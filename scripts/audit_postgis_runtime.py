"""Read-only PostGIS runtime audit without printing connection credentials."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", type=Path, required=True)
    args = parser.parse_args()
    values = load_env(args.env)
    dsn = values.get("GEOAI_POSTGIS_DSN")
    if not dsn:
        print(json.dumps({"connected": False, "reason": "dsn_missing"}))
        return 2

    import psycopg2

    with psycopg2.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_database(), current_user, version(), "
                "postgis_full_version(), "
                "EXISTS(SELECT 1 FROM pg_roles WHERE rolname='geoai_a7t_app_ro')"
            )
            database, current_user, version, postgis_version, role_exists = cur.fetchone()
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='geoai_a7t' AND table_name='landcover_polygons' "
                "ORDER BY ordinal_position"
            )
            columns = cur.fetchall()
            cur.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname='geoai_a7t' "
                "AND tablename='landcover_polygons' ORDER BY indexname"
            )
            indexes = [row[0] for row in cur.fetchall()]
            cur.execute(
                "SELECT count(*)::bigint, count(*) FILTER (WHERE NOT ST_IsValid(geom)), "
                "ST_SRID(geom), ST_Extent(geom)::text "
                "FROM geoai_a7t.landcover_polygons GROUP BY ST_SRID(geom)"
            )
            count, invalid, srid, bounds = cur.fetchone()
    print(
        json.dumps(
            {
                "connected": True,
                "database": database,
                "current_user": current_user,
                "postgres_version": version.split(",")[0],
                "postgis_available": bool(postgis_version),
                "read_only_role_exists": bool(role_exists),
                "polygon_count": int(count),
                "invalid_geometry_count": int(invalid),
                "srid": int(srid),
                "bounds": bounds,
                "columns": [row[0] for row in columns],
                "indexes": indexes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
