"""Verify five canonical queries with LLM disabled in this process only."""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND = APP_ROOT / "backend"
PUBLISH_ROOT = APP_ROOT.parents[1]
OUTPUT = PUBLISH_ROOT / "FINAL_A7T_LOCK" / "07_POSTGIS_LLM_FINAL" / "02_LIVE_LLM" / "DETERMINISTIC_FALLBACK_QA.csv"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from local_env import load_local_env

load_local_env()
os.environ["AGENT_LLM_ENABLED"] = "0"

from agent_orchestrator import run_agent_query


CASES = [
    ("F01", "ค้นหาพื้นที่สิ่งปลูกสร้าง", "search_landcover", "success"),
    ("F02", "แหล่งน้ำอยู่ตรงไหนบ้าง", "search_landcover", "success"),
    ("F03", "หาพื้นที่เกษตรมากกว่า 5 ไร่", "search_landcover|filter_by_area", "success"),
    ("F04", "หาพื้นที่เกษตรใกล้น้ำไม่เกิน 300 เมตร", "find_nearby", "success"),
    ("F05", "หาพื้นที่เกษตรใกล้น้ำ", "NONE", "clarification_required"),
]


def main() -> int:
    rows = []
    for case_id, query, expected_tools, expected_status in CASES:
        result = run_agent_query(query, limit=5)
        actual_tools = "|".join(item.get("tool", "") for item in result.get("tool_trace", [])) or "NONE"
        llm = result.get("llm") or {}
        passed = (
            result.get("status") == expected_status
            and actual_tools == expected_tools
            and llm.get("used") is False
            and llm.get("mode") == "deterministic_fallback"
        )
        rows.append({
            "case_id": case_id,
            "query": query,
            "expected_status": expected_status,
            "actual_status": result.get("status"),
            "expected_tools": expected_tools,
            "actual_tools": actual_tools,
            "llm_used": llm.get("used"),
            "mode": llm.get("mode"),
            "result_count": (result.get("results") or {}).get("count", 0),
            "pass": passed,
        })
        print(f"{case_id} {'PASS' if passed else 'FAIL'}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"WROTE {OUTPUT}")
    return 0 if all(row["pass"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
