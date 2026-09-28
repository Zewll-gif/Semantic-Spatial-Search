"""Provision the fixed GeoAI SELECT-only role and merge secrets without printing them."""
from __future__ import annotations

import argparse
import secrets
import shutil
from datetime import datetime
from pathlib import Path


ROLE = "geoai_a7t_app_ro"


def load_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return lines, values


def merge_env(lines: list[str], updates: dict[str, str]) -> list[str]:
    written: set[str] = set()
    output: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                output.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        output.append(raw)
    for key, value in updates.items():
        if key not in written:
            output.append(f"{key}={value}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-env", type=Path, required=True)
    parser.add_argument("--production-env", type=Path, required=True)
    args = parser.parse_args()

    admin_lines, admin_values = load_env(args.admin_env)
    del admin_lines
    production_lines, _ = load_env(args.production_env)
    admin_dsn = admin_values.get("GEOAI_POSTGIS_DSN")
    openai_key = admin_values.get("OPENAI_API_KEY")
    openai_model = admin_values.get("OPENAI_MODEL") or admin_values.get("AGENT_MODEL")
    if not admin_dsn or not openai_key or not openai_model:
        raise RuntimeError("Required legacy secret/config entry is missing")

    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import make_dsn

    password = secrets.token_urlsafe(36)
    with psycopg2.connect(admin_dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=%s)", (ROLE,))
            if cur.fetchone()[0]:
                raise RuntimeError("Read-only role already exists; refusing to rotate it implicitly")
            cur.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(ROLE), sql.Literal(password)
                )
            )
            cur.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(conn.info.dbname), sql.Identifier(ROLE)
            ))
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA geoai_a7t TO {}").format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA geoai_a7t TO {}").format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL("REVOKE CREATE ON SCHEMA geoai_a7t FROM {}").format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA geoai_a7t GRANT SELECT ON TABLES TO {}").format(sql.Identifier(ROLE)))
        conn.commit()

    readonly_dsn = make_dsn(admin_dsn, user=ROLE, password=password)
    with psycopg2.connect(readonly_dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_user, current_setting('default_transaction_read_only'), "
                "count(*)::bigint, "
                "has_table_privilege(current_user,'geoai_a7t.landcover_polygons','SELECT'), "
                "has_table_privilege(current_user,'geoai_a7t.landcover_polygons','INSERT'), "
                "has_table_privilege(current_user,'geoai_a7t.landcover_polygons','UPDATE'), "
                "has_table_privilege(current_user,'geoai_a7t.landcover_polygons','DELETE') "
                "FROM geoai_a7t.landcover_polygons GROUP BY current_user"
            )
            user, default_readonly, count, can_select, can_insert, can_update, can_delete = cur.fetchone()
    if user != ROLE or default_readonly != "on" or int(count) != 155199:
        raise RuntimeError("Read-only role verification failed")
    if not can_select or any((can_insert, can_update, can_delete)):
        raise RuntimeError("Read-only role privileges are unsafe")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = args.production_env.with_name(f".env.backup_before_postgis_{stamp}")
    if backup.exists():
        raise FileExistsError(backup)
    shutil.copy2(args.production_env, backup)
    updates = {
        "DATABASE_BACKEND": "postgis",
        "GEOAI_POSTGIS_DSN": readonly_dsn,
        "OPENAI_API_KEY": openai_key,
        "OPENAI_MODEL": openai_model,
    }
    merged = merge_env(production_lines, updates)
    args.production_env.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")
    print(f"POSTGIS_READONLY_ROLE=PASS role={ROLE} count={count}")
    print(f"PRODUCTION_ENV_MERGE=PASS backup={backup}")
    print("SECRETS_PRINTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
