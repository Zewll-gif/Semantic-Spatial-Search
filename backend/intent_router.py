# CLEAN PROJECT HEADER
# ไฟล์: intent_router.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Deterministic query routing and parameter extraction for the GeoAI agent."""
from __future__ import annotations

import re
from typing import Any

try:
    from canonical_schema import load_class_schema, resolve_class_alias
except ImportError:  # pragma: no cover - package import
    from .canonical_schema import load_class_schema, resolve_class_alias

SPATIAL_WORDS = ("หา", "ค้นหา", "ใกล้", "ห่าง", "มากกว่า", "น้อยกว่า", "ภายใน", "พื้นที่", "search", "find", "near", "within", "intersect")
KNOWLEDGE_WORDS = ("คืออะไร", "หมายถึง", "โมเดลอะไร", "ใช้โมเดล", "ground truth", "validation", "ข้อจำกัด", "ความแม่นยำ", "ผลการประเมิน", "test40", "full aoi", "a7-t", "a7 t", "accuracy", "metric", "what is", "อธิบาย")
RELIABILITY_WORDS = ("เชื่อถือ", "มั่นใจ", "reliable", "reliability", "confidence", "ข้อจำกัด")
UNSUPPORTED_DOMAINS = ("ร้านกาแฟ", "ร้านอาหาร", "โรงพยาบาล", "โรงแรม", "ปั๊มน้ำมัน", "coffee shop", "restaurant", "hotel")


def _class_mentions(query: str) -> list[tuple[int, str, str]]:
    q = query.lower()
    mentions: list[tuple[int, str, str]] = []
    for item in load_class_schema()["classes"]:
        aliases = [item["class_id"], item["canonical_name"], item["thai_name"], *item.get("aliases", [])]
        for alias in sorted(aliases, key=len, reverse=True):
            pos = q.find(str(alias).lower())
            if pos >= 0:
                mentions.append((pos, item["class_id"], str(alias)))
                break
    # One mention per class, ordered as the user wrote it.
    return sorted(mentions, key=lambda x: x[0])


def _parse_area(query: str) -> dict[str, Any]:
    patterns = [
        r"(?:มากกว่า|อย่างน้อย|ขั้นต่ำ|>=|over|at least)\s*([0-9]+(?:\.[0-9]+)?)\s*(ไร่|rai|m2|m²|ตารางเมตร|ha|hectare|เฮกตาร์)",
        r"(?:พื้นที่|area)\s*([0-9]+(?:\.[0-9]+)?)\s*(ไร่|rai|m2|m²|ตารางเมตร|ha|hectare|เฮกตาร์)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query.lower())
        if match:
            unit = match.group(2)
            unit = {"ตารางเมตร": "sqm", "m2": "sqm", "m²": "sqm", "ไร่": "rai", "เฮกตาร์": "hectare", "ha": "hectare"}.get(unit, unit)
            return {"min": float(match.group(1)), "max": None, "unit": unit}
    return {"min": None, "max": None, "unit": None}


def _parse_distance_m(query: str) -> float | None:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(กิโลเมตร|km|เมตร|m)\b", query.lower())
    if not match:
        return None
    value = float(match.group(1))
    return value * 1000.0 if match.group(2) in {"กิโลเมตร", "km"} else value


def route_query(query: str) -> dict[str, Any]:
    raw = str(query or "").strip()
    q = raw.lower()
    if not raw:
        return {"mode": "knowledge", "clarification_required": True, "clarification_question": "กรุณาระบุคำถาม"}

    if any(phrase in q for phrase in UNSUPPORTED_DOMAINS):
        return {
            "mode": "spatial",
            "spatial_intent": {},
            "knowledge_intent": ["system_scope_limit"],
            "clarification_required": True,
            "clarification_question": "ระบบนี้ไม่มีข้อมูลจุดสนใจดังกล่าวและรองรับเฉพาะข้อมูลสิ่งปกคลุมดิน A7-T",
            "fallback_type": "unsupported_domain",
        }

    for phrase in load_class_schema().get("unsupported_fine_grained_examples", []):
        if phrase.lower() in q:
            resolved = resolve_class_alias(phrase)
            return {
                "mode": "spatial",
                "spatial_intent": {},
                "knowledge_intent": ["taxonomy_limit"],
                "clarification_required": True,
                "clarification_question": resolved.get("question"),
                "fallback_type": "unsupported_class",
                "requested_category": phrase,
                "candidate_class_id": resolved.get("candidate_class_id"),
            }

    mentions = _class_mentions(raw)
    # A bare class request such as "บ่อน้ำ" is a map search, not a knowledge
    # question.  Explicit definition/explanation wording still wins below.
    has_spatial_words = any(word in q for word in SPATIAL_WORDS)
    has_spatial = has_spatial_words or bool(mentions)
    has_knowledge = any(word in q for word in KNOWLEDGE_WORDS)
    needs_reliability = any(word in q for word in RELIABILITY_WORDS)
    if has_spatial_words and (has_knowledge or needs_reliability):
        mode = "mixed"
    elif has_knowledge:
        mode = "knowledge"
    elif has_spatial:
        mode = "spatial"
    else:
        # Unknown short phrases should get one chance through the structured
        # spatial planner (or ask for a class when LLM is off), rather than
        # being mislabeled as a failed knowledge-base lookup.
        mode = "spatial"

    class_ids = [class_id for _, class_id, _ in mentions]
    relation = "near" if any(x in q for x in ("ใกล้", "near", "within", "ไม่เกิน", "ห่าง")) else None
    distance_m = _parse_distance_m(raw)
    area = _parse_area(raw)
    source_class = class_ids[0] if class_ids else None
    target_class = class_ids[1] if len(class_ids) > 1 else ("R4" if relation == "near" and "น้ำ" in q and source_class != "R4" else None)
    clarification = False
    question = None
    if mode in {"spatial", "mixed"} and not source_class:
        clarification = True
        question = "ต้องการค้นหาคลาส R1-R7 ใด?"
    elif relation == "near" and target_class is None:
        clarification = True
        question = "ต้องการค้นหาใกล้คลาสเป้าหมายใด?"
    elif relation == "near" and distance_m is None:
        clarification = True
        question = "ต้องการกำหนดระยะ ‘ใกล้’ ไม่เกินกี่เมตร?"

    knowledge_intent: list[str] = []
    if needs_reliability:
        knowledge_intent.append("model_validation_context")
    if "test40" in q:
        knowledge_intent.append("test40_ground_truth")
    if any(x in q for x in ("a7-t", "a7 t", "โมเดล")):
        knowledge_intent.append("model_metadata")
    if "r2" in q or "คืออะไร" in q:
        knowledge_intent.append("taxonomy_definition")

    return {
        "mode": mode,
        "spatial_intent": {
            "source_class_id": source_class,
            "area_min": area["min"],
            "area_max": area["max"],
            "area_unit": area["unit"],
            "relation": relation,
            "target_class_id": target_class,
            "distance_m": distance_m,
        },
        "knowledge_intent": knowledge_intent,
        "clarification_required": clarification,
        "clarification_question": question,
        "resolved_mentions": [
            {"class_id": class_id, "matched_alias": alias} for _, class_id, alias in mentions
        ],
    }
