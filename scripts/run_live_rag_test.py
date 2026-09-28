"""Run the six approved live RAG questions through DeepSeek."""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
PUBLISH_ROOT = APP_ROOT.parents[1]
OUTPUT = PUBLISH_ROOT / "FINAL_A7T_LOCK" / "07_POSTGIS_LLM_FINAL" / "04_RAG" / "LIVE_RAG_TEST.csv"
URL = "http://127.0.0.1:8795/api/agent/query"

QUESTIONS = [
    ("RAG01", "final model คืออะไร", ["A7-T", "U-Net", "Tversky"]),
    ("RAG02", "A7-T ใช้ input อะไร", ["RGBN"]),
    ("RAG03", "Revised7 มีกี่คลาส", ["7"]),
    ("RAG04", "TEST-GT4 คืออะไร", ["4"]),
    ("RAG05", "LLM ทำหน้าที่อะไรในระบบนี้", ["เครื่องมือ"]),
    ("RAG06", "GIS ทำหน้าที่อะไรในระบบนี้", ["คำนวณ"]),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live", action="store_true")
    args = parser.parse_args()
    if not args.confirm_live:
        parser.error("--confirm-live is required")

    rows = []
    for query_id, query, expected_terms in QUESTIONS:
        payload = json.dumps({"query": query, "limit": 5, "provider": "deepseek"}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(URL, data=payload, method="POST", headers={"Content-Type": "application/json"})
        started = time.perf_counter()
        error = ""
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            result = {}
            error = f"{type(exc).__name__}: {exc}"
        latency_ms = (time.perf_counter() - started) * 1000
        answer = result.get("answer", "")
        term_checks = {term: term.lower() in answer.lower() for term in expected_terms}
        lower_answer = answer.lower()
        mentions_fresh_unetpp = "fresh u-net++" in lower_answer or "fresh unet++" in lower_answer
        exclusion_context = any(phrase in lower_answer for phrase in (
            "ห้ามอ้างผล fresh u-net++",
            "ไม่เกี่ยวข้องกับผล fresh u-net++",
            "ไม่ใช่ fresh u-net++",
        ))
        no_fresh_unetpp = not mentions_fresh_unetpp or exclusion_context
        provider_live = bool((result.get("llm") or {}).get("used")) and (result.get("llm") or {}).get("provider") == "deepseek"
        passed = not error and provider_live and all(term_checks.values()) and no_fresh_unetpp
        rows.append({
            "query_id": query_id,
            "provider": "deepseek",
            "model": (result.get("llm") or {}).get("model", "N/A"),
            "query": query,
            "expected_terms": "|".join(expected_terms),
            "expected_terms_found": json.dumps(term_checks, ensure_ascii=False),
            "fresh_unetpp_absent": no_fresh_unetpp,
            "provider_live": provider_live,
            "evidence_count": len(result.get("evidence") or []),
            "latency_ms": round(latency_ms, 3),
            "answer": answer,
            "pass": passed,
            "error": error,
        })
        print(f"{query_id} {'PASS' if passed else 'FAIL'}", flush=True)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"WROTE {OUTPUT}")
    return 0 if all(row["pass"] for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
