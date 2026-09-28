# CLEAN PROJECT HEADER
# ไฟล์: local_env.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Load the local server secrets without logging or copying their values.

The operator-owned .env is not modified. Existing process environment wins.
"""
from __future__ import annotations

import os
from pathlib import Path


ENV_PATH = Path(__file__).with_name(".env")
ALLOWED = {
    "GEOAI_POSTGIS_DSN", "LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_MODEL", "AGENT_MODEL",
    "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "AGENT_LLM_ENABLED",
    "AGENT_MAX_TOOL_ROUNDS", "AGENT_TRACE_PATH", "DEBUG_AGENT",
    "CDSE_S3_ACCESS_KEY", "CDSE_S3_SECRET_KEY", "CDSE_S3_ENDPOINT", "SENTINEL2_CACHE_DIR",
    "GEOAI_DATA_ROOT", "GEOAI_CORRECTIONS_DB",
}


def load_local_env() -> set[str]:
    if not ENV_PATH.is_file():
        return set()
    loaded = set()
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key not in ALLOWED:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value and not os.getenv(key):
            os.environ[key] = value
            loaded.add(key)
    return loaded
