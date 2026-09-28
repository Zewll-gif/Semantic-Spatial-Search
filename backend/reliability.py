# CLEAN PROJECT HEADER
# ไฟล์: reliability.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Reliability context for model-prediction-derived spatial results."""
from __future__ import annotations

from typing import Any

CLASS_METRICS = {
    "R1": {"validation_iou": 0.6537203785, "validation_f1": 0.7905779551},
    "R2": {"validation_iou": 0.5483003889, "validation_f1": 0.7076151842},
    "R3": {"validation_iou": 0.7191364564, "validation_f1": 0.8365683664},
    "R4": {"validation_iou": 0.6171390109, "validation_f1": 0.7630425024},
    "R5": {"validation_iou": 0.3092807749, "validation_f1": 0.4723826350},
    "R6": {"validation_iou": 0.2157877646, "validation_f1": 0.3549085852},
    "R7": {"validation_iou": None, "validation_f1": None, "note": "No support in fixed VAL4"},
}


def reliability_context(class_id: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source_model": "A7-T",
        "model_version": "A7_RGBN_REVISED7_TVERSKY",
        "result_type": "model_prediction",
        "validation_reference": "Fixed VAL4",
        "independent_validation": False,
        "calibrated_confidence": False,
        "note": "This spatial result is derived from A7-T model predictions. Fixed VAL4 was used during model development, and the displayed area has not been independently validated with Ground Truth.",
    }
    if class_id:
        metrics = CLASS_METRICS.get(class_id.upper())
        if metrics:
            result["class_metric_context"] = {
                "class_id": class_id.upper(),
                **metrics,
                "metric_scope": "Fixed VAL4 class-level multi-seed performance",
                "not_polygon_confidence": True,
            }
    return result
