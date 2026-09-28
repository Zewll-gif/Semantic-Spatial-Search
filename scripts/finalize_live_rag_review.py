"""Apply semantic review to the already completed six-query RAG test."""
from __future__ import annotations

import csv
import json
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
PUBLISH_ROOT = APP_ROOT.parents[1]
PATH = PUBLISH_ROOT / "FINAL_A7T_LOCK" / "07_POSTGIS_LLM_FINAL" / "04_RAG" / "LIVE_RAG_TEST.csv"


def main() -> int:
    with PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        answer = row["answer"].lower()
        claimed_operational = (
            ("fresh u-net++" in answer or "fresh unet++" in answer)
            and not any(phrase in answer for phrase in (
                "ห้ามอ้างผล fresh u-net++",
                "ไม่เกี่ยวข้องกับผล fresh u-net++",
                "ไม่ใช่ fresh u-net++",
            ))
        )
        terms = json.loads(row["expected_terms_found"])
        row["fresh_unetpp_absent"] = str(not claimed_operational)
        row["fresh_unetpp_claimed_as_operational"] = str(claimed_operational)
        row["manual_review"] = "PASS" if not claimed_operational and all(terms.values()) else "FAIL"
        row["pass"] = str(
            row["provider_live"].lower() == "true"
            and not claimed_operational
            and all(terms.values())
            and not row["error"]
        )
    with PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"UPDATED {PATH}; pass={sum(row['pass'] == 'True' for row in rows)}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
