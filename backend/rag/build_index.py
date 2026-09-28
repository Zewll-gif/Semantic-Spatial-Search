# CLEAN PROJECT HEADER
# ไฟล์: build_index.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_layer import rag_documents

OUT = Path(__file__).resolve().parents[2] / "data" / "project_rag_index.json"

def main():
    docs = rag_documents()
    payload = {"index_version": "agent-layer-v1", "document_count": len(docs), "documents": [{"document_name": d["document_name"], "provenance_path": d["provenance_path"], "text": d["text"]} for d in docs]}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RAG_INDEX_COMPLETE = YES; DOCUMENT_COUNT = {len(docs)}; OUTPUT = {OUT}")

if __name__ == "__main__":
    main()
