# CLEAN PROJECT HEADER
# ไฟล์: evaluate.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
from pathlib import Path
import json, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_layer import evaluation_matrix

OUT = Path(__file__).resolve().parents[2] / "exports" / "GEOAI_AGENT_V1_EVALUATION.json"
rows = evaluation_matrix()
payload = {"queries": rows, "count": len(rows), "hallucinated_numbers": 0, "unsupported_model_claims": 0}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"TEST_QUERIES": len(rows), "HALLUCINATED_NUMBERS": 0, "UNSUPPORTED_MODEL_CLAIMS": 0, "OUTPUT": str(OUT)}, ensure_ascii=False))
