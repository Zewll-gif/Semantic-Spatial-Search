# CLEAN PROJECT HEADER
# ไฟล์: llm_spatial_planner.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Optional OpenAI intent planner; GIS facts remain local and deterministic."""
from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

_CLASSES = [f"R{i}" for i in range(1, 8)]
_FIELDS = {
    "source_class_id": {"type": ["string", "null"], "enum": [*_CLASSES, None]},
    "target_class_id": {"type": ["string", "null"], "enum": [*_CLASSES, None]},
    "relation": {"type": "string", "enum": ["none", "near"]},
    "distance_m": {"type": ["number", "null"]},
    "area_min": {"type": ["number", "null"]},
    "area_unit": {"type": ["string", "null"], "enum": ["sqm", "rai", "hectare", None]},
    "clarification_required": {"type": "boolean"},
    "clarification_question": {"type": ["string", "null"]},
}
_SCHEMA = {"type": "object", "properties": _FIELDS, "required": list(_FIELDS),
           "additionalProperties": False}


def enabled() -> bool:
    return os.getenv("AGENT_LLM_ENABLED") == "1" and bool(os.getenv("OPENAI_API_KEY"))


def _request(payload: dict) -> dict:
    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def _extract(response: dict) -> dict:
    if response.get("status") != "completed":
        raise ValueError("LLM response incomplete")
    for item in response.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    return json.loads(part["text"])
    raise ValueError("LLM produced no structured text")


def _validate(plan: dict) -> dict:
    if not isinstance(plan, dict) or set(plan) != set(_FIELDS):
        raise ValueError("Invalid planner fields")
    source, target = plan["source_class_id"], plan["target_class_id"]
    if source is not None and source not in _CLASSES:
        raise ValueError("Unknown source class")
    if target is not None and target not in _CLASSES:
        raise ValueError("Unknown target class")
    if plan["relation"] not in {"none", "near"}:
        raise ValueError("Invalid relation")
    if plan["area_unit"] not in {None, "sqm", "rai", "hectare"}:
        raise ValueError("Invalid unit")
    for field, ceiling in (("distance_m", 100000), ("area_min", 1e12)):
        value = plan[field]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= ceiling):
            raise ValueError(f"Invalid {field}")
    if not isinstance(plan["clarification_required"], bool):
        raise ValueError("Invalid clarification flag")
    if plan["clarification_question"] is not None and not isinstance(plan["clarification_question"], str):
        raise ValueError("Invalid clarification question")
    if source is None or (plan["relation"] == "near" and (target is None or not plan["distance_m"])):
        plan["clarification_required"] = True
        plan["clarification_question"] = plan["clarification_question"] or "กรุณาระบุคลาสและระยะทางที่ต้องการ"
    if plan["area_min"] is not None and plan["area_unit"] is None:
        raise ValueError("Area unit required")
    return plan


def plan_spatial_query(question: str) -> dict:
    """Return validated intent fields; never ask the model for SQL or facts."""
    if not enabled():
        raise RuntimeError("LLM planner not enabled")
    payload = {
        "model": os.getenv("AGENT_MODEL", "gpt-5.6-terra"),
        "store": False,
        "max_output_tokens": 1000,
        "instructions": (
            "Extract a search plan for a read-only land-cover GIS system. "
            "Only Revised-7 classes R1 built-up, R2 agriculture, R3 trees, "
            "R4 water, R5 grassland, R6 bare ground, R7 uncertain exist. "
            "Use relation near only when a distance to another class is requested. "
            "Convert km to meters; use sqm, rai or hectare for area. "
            "If a required class or distance is missing, request clarification. "
            "Never write SQL, estimate GIS results, or treat predictions as Ground Truth."
        ),
        "input": [{"role": "user", "content": question[:2000]}],
        "text": {"format": {"type": "json_schema", "name": "geoai_spatial_plan",
                            "strict": True, "schema": _SCHEMA}},
    }
    return _validate(_extract(_request(payload)))
