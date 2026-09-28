# CLEAN PROJECT HEADER
# ไฟล์: smoke_canonical_queries.py
# หน้าที่: ตรวจคำถามตัวอย่างโดยใช้ deterministic Agent/GIS/RAG และไม่เรียก paid LLM
# Input: canonical Thai queries
# Output: HTTP status, mode และ clarification state
# สิ่งที่ต้องระวัง: ต้องตั้ง AGENT_LLM_ENABLED=0 ระหว่าง cleanup verification
import sys
from pathlib import Path

# เพิ่ม backend ของ CLEAN COPY ให้ import ได้เมื่อเรียกไฟล์นี้โดยตรง
BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from agent_api_v2 import app


QUERIES = [
    "R2 คืออะไร",
    "พื้นที่ต้นไม้มากกว่า 5 ไร่",
    "พื้นที่เกษตรใกล้น้ำ 300 เมตร",
    "พื้นที่เกษตรใกล้น้ำ",
    "หาสวนลำไย",
]


def main() -> None:
    """ส่งคำถามมาตรฐานและ fail หาก API ไม่ตอบ HTTP 200."""
    client = TestClient(app)
    for query in QUERIES:
        response = client.post("/api/agent/query", json={"query": query, "limit": 3})
        response.raise_for_status()
        payload = response.json()
        print(query, "=>", payload.get("status"), payload.get("mode"), payload.get("clarification_required", False))


if __name__ == "__main__":
    main()
