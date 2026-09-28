"""Persistent candidate-annotation storage, intentionally separate from A7-T."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from drawn_aoi import MODEL_VERSION
from project_paths import CORRECTIONS_DB_PATH

DB_PATH = CORRECTIONS_DB_PATH


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS human_corrections (
        id TEXT PRIMARY KEY, geometry_geojson TEXT NOT NULL, feature_id INTEGER,
        original_class TEXT NOT NULL, corrected_class TEXT NOT NULL,
        model_version TEXT NOT NULL, created_at TEXT NOT NULL, note TEXT,
        source_aoi_id TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'pending'
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS human_corrections_aoi_idx ON human_corrections(source_aoi_id)")
    conn.commit()
    return conn


def save_correction(*, geometry: dict[str, Any], feature_id: int | None, original_class: str,
                    corrected_class: str, note: str | None, source_aoi_id: str) -> dict[str, Any]:
    original_class, corrected_class = original_class.upper(), corrected_class.upper()
    allowed = {f"R{i}" for i in range(1, 8)}
    if original_class not in allowed or corrected_class not in allowed:
        raise ValueError("original_class and corrected_class must use R1-R7")
    if original_class == corrected_class:
        raise ValueError("corrected_class must differ from original_class")
    if len(note or "") > 1000:
        raise ValueError("note exceeds 1000 characters")
    correction_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute("INSERT INTO human_corrections VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (correction_id, json.dumps(geometry, ensure_ascii=False), feature_id,
                      original_class, corrected_class, MODEL_VERSION, created_at,
                      note or None, source_aoi_id, "pending"))
        conn.commit()
    finally:
        conn.close()
    return {"correction_id": correction_id, "geometry": geometry, "feature_id": feature_id,
            "original_class": original_class, "corrected_class": corrected_class,
            "model_version": MODEL_VERSION, "created_at": created_at, "user_note": note or None,
            "source_aoi_id": source_aoi_id, "review_status": "pending",
            "source_prediction_modified": False,
            "message": "ข้อมูลการแก้ไขถูกเก็บเป็น candidate annotation สำหรับการตรวจสอบและการฝึกแบบจำลองในรอบถัดไป"}


def list_corrections(source_aoi_id: str | None = None) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        if source_aoi_id:
            rows = conn.execute("SELECT * FROM human_corrections WHERE source_aoi_id=? ORDER BY created_at DESC", (source_aoi_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM human_corrections ORDER BY created_at DESC LIMIT 200").fetchall()
    finally:
        conn.close()
    result = []
    for row in rows:
        item = dict(row); item["geometry"] = json.loads(item.pop("geometry_geojson")); result.append(item)
    return result
