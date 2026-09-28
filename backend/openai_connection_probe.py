# CLEAN PROJECT HEADER
# ไฟล์: openai_connection_probe.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Non-generative account/model access check; no secret or response body output."""
from __future__ import annotations

import os
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from local_env import load_local_env


def main() -> None:
    load_local_env()
    model = os.environ.get("AGENT_MODEL", "gpt-5.6-terra")
    print("MODEL_ID=" + model)
    request = Request(
        "https://api.openai.com/v1/models/" + quote(model, safe=""),
        headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
    )
    try:
        with urlopen(request, timeout=15) as response:
            print("MODEL_ACCESS_HTTP=" + str(response.status))
    except HTTPError as exc:
        print("MODEL_ACCESS_HTTP=" + str(exc.code))
    except Exception as exc:
        print("MODEL_ACCESS_ERROR_TYPE=" + type(exc).__name__)


if __name__ == "__main__":
    main()
