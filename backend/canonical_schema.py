# CLEAN PROJECT HEADER
# ไฟล์: canonical_schema.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Authoritative Revised-7 class resolution for deterministic GIS requests."""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parent / "config" / "class_schema.json"


@lru_cache(maxsize=1)
def load_class_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _normalise(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = re.sub(r"[\s_/&-]+", " ", text)
    return re.sub(r"\s+", " ", text)


def class_by_id(class_id: str) -> dict[str, Any] | None:
    wanted = str(class_id).strip().upper()
    return next((c for c in load_class_schema()["classes"] if c["class_id"] == wanted), None)


def resolve_class_alias(text: str) -> dict[str, Any]:
    """Resolve natural-language class text without inventing a fine-grained class."""
    raw = str(text or "").strip()
    norm = _normalise(raw)
    if not norm:
        return {"status": "clarification_required", "reason": "Class text is empty"}

    direct = class_by_id(raw)
    if direct:
        return {
            "status": "resolved",
            "class_id": direct["class_id"],
            "canonical_name": direct["canonical_name"],
            "matched_alias": direct["class_id"],
        }

    unsupported = {_normalise(x) for x in load_class_schema().get("unsupported_fine_grained_examples", [])}
    if norm in unsupported:
        return {
            "status": "clarification_required",
            "reason": "Requested fine-grained category is not a Revised 7-class model class",
            "requested_text": raw,
            "candidate_class_id": "R2" if any(x in norm for x in ("สวน", "orchard", "นา", "paddy")) else None,
            "question": "taxonomy ปัจจุบันระบุได้เพียง R2 Agricultural Land / Cropland ต้องการค้นหา R2 แทนหรือไม่?",
        }

    matches: list[tuple[dict[str, Any], str]] = []
    for item in load_class_schema()["classes"]:
        candidates = [item["canonical_name"], item["thai_name"], *item.get("aliases", [])]
        for alias in candidates:
            if norm == _normalise(alias):
                matches.append((item, alias))

    unique = {item["class_id"] for item, _ in matches}
    if len(unique) == 1:
        item, alias = matches[0]
        return {
            "status": "resolved",
            "class_id": item["class_id"],
            "canonical_name": item["canonical_name"],
            "matched_alias": alias,
        }
    return {
        "status": "clarification_required",
        "reason": "Cannot map requested category to Revised 7-class taxonomy",
        "requested_text": raw,
    }


def public_schema() -> dict[str, Any]:
    schema = load_class_schema()
    return {
        "schema_id": schema["schema_id"],
        "authoritative": schema["authoritative"],
        "classes": schema["classes"],
        "rules": schema["rules"],
    }
