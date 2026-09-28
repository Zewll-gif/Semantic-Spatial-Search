# CLEAN PROJECT HEADER
# ไฟล์: rag_service.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Low-dependency, project-local RAG retrieval over verified knowledge documents."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from project_paths import KNOWLEDGE_ROOT

KB_PATH = KNOWLEDGE_ROOT / "knowledge_base.json"


def _tokens(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9_]+|[ก-๙]+", str(text).lower()) if len(x) > 1}


@lru_cache(maxsize=1)
def knowledge_documents() -> list[dict[str, Any]]:
    payload = json.loads(KB_PATH.read_text(encoding="utf-8"))
    return payload["documents"]


def search_knowledge(query: str, category: str | None = None, top_k: int = 4) -> dict[str, Any]:
    query_tokens = _tokens(query)
    candidates = [d for d in knowledge_documents() if category is None or d["category"] == category]
    scored: list[tuple[float, dict[str, Any]]] = []
    for doc in candidates:
        haystack = f'{doc["title"]} {doc["content"]} {doc["category"]}'
        doc_tokens = _tokens(haystack)
        overlap = len(query_tokens & doc_tokens)
        score = overlap / max(1, len(query_tokens))
        q = query.lower()
        if "r2" in q and doc["id"] == "taxonomy-revised7":
            score += 1.0
        if any(x in q for x in ("a7-t", "a7 t", "โมเดล")) and doc["id"] == "model-a7t":
            score += 1.0
        if any(x in q for x in ("test40", "ground truth", "เชื่อถือ", "validation", "full aoi")) and doc["category"] == "validation_limitations":
            score += 1.0
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    documents = []
    for score, doc in scored[: max(1, min(int(top_k), 10))]:
        documents.append({**doc, "relevance_score": round(float(score), 4)})
    return {"documents": documents, "count": len(documents), "source": "project knowledge base"}


def grounded_knowledge_answer(query: str, docs: list[dict[str, Any]]) -> str:
    q = query.lower()
    if "r2" in q and any(x in q for x in ("คือ", "what", "หมายถึง")):
        return "R2 คือ Agricultural Land / Cropland หรือพื้นที่เกษตรกรรม ครอบคลุมพื้นที่เพาะปลูกและการใช้ประโยชน์ทางการเกษตร แต่ไม่ยืนยันชนิดพืชเฉพาะ"
    if any(x in q for x in ("a7-t", "a7 t")) and any(x in q for x in ("โมเดล", "model", "ใช้")):
        return "A7-T เป็น Custom U-Net ที่รับ PlanetScope RGBN ตามลำดับ R,G,B,NIR ใช้ Revised 7-class และ Tversky loss (alpha=0.3, beta=0.7) โดยฝึกจาก scratch"
    if "test40" in q and any(x in q for x in ("ground truth", "gt", "ข้อมูลอ้างอิง", "มี")):
        return "TEST40 ไม่มี Ground Truth และใช้เป็น deployment output เท่านั้น จึงไม่ใช่ independent labeled test"
    if "full aoi" in q and any(x in q for x in ("validation", "ground truth", "เชื่อถือ", "จริง")):
        return "Full AOI เป็นผลทำนายจากโมเดล ไม่ใช่ Ground Truth และไม่ได้ผ่าน independent validation ครบทั้งพื้นที่"
    if docs:
        return docs[0]["content"]
    return "ไม่พบหลักฐานใน project knowledge base ที่ตอบคำถามนี้ได้โดยตรง"
