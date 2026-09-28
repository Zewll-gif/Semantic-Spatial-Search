"""Run the locked OpenAI/DeepSeek benchmark through the live GeoAI API.

This script makes paid provider requests. Run only with --confirm-live.
It never changes the gold set, model raster, taxonomy, or database.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND = APP_ROOT / "backend"
PUBLISH_ROOT = APP_ROOT.parents[1]
OUTPUT_ROOT = PUBLISH_ROOT / "FINAL_A7T_LOCK" / "07_POSTGIS_LLM_FINAL"
GOLD_PATH = OUTPUT_ROOT / "02_LIVE_LLM" / "LIVE_LLM_GOLD_SET.csv"
EXPECTED_GOLD_SHA256 = "0d069636e471a1bb8db82eae848a227cce521f5f8d8f29b82c1b2d5814a9ff13"
RUNS_PATH = OUTPUT_ROOT / "02_LIVE_LLM" / "LIVE_LLM_RUNS.csv"
RAW_DIR = OUTPUT_ROOT / "02_LIVE_LLM" / "raw"
COMPARISON_CSV = OUTPUT_ROOT / "03_COMPARISON" / "LIVE_LLM_PROVIDER_COMPARISON.csv"
COMPARISON_MD = OUTPUT_ROOT / "03_COMPARISON" / "LIVE_LLM_PROVIDER_COMPARISON.md"
API_BASE = "http://127.0.0.1:8795"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from local_env import load_local_env
from llm.tool_registry import execute_tool


TOOL_TO_INTENT = {
    "search_landcover": "class_search",
    "filter_by_area": "area_filter",
    "find_nearby": "proximity",
    "calculate_distance": "distance",
    "intersects": "intersection",
    "get_feature_details": "feature_detail",
    "get_ndvi_stats": "ndvi",
    "get_ndwi_stats": "ndwi",
    "get_evidence": "evidence",
    "get_geojson": "export",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _http_json(method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 180) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API_BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:600]}") from exc


def _parse_json(value: str, default: Any) -> Any:
    if value is None or not value.strip():
        return default
    return json.loads(value)


def _equivalent(expected: Any, actual: Any) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, bool):
        return actual is expected
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(expected), float(actual), rel_tol=1e-6, abs_tol=1e-6)
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(_equivalent(a, b) for a, b in zip(expected, actual))
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(key in actual and _equivalent(value, actual[key]) for key, value in expected.items())
    return str(expected).strip().lower() == str(actual).strip().lower()


def _numbers(value: Any) -> list[float]:
    found: list[float] = []
    if isinstance(value, bool) or value is None:
        return found
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        for item in value.values():
            found.extend(_numbers(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_numbers(item))
    return found


def _answer_numbers(text: str) -> list[float]:
    normalized = text.replace(",", "")
    return [float(item) for item in re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", normalized)]


def _grounded(answer: str, query: str, args: dict[str, Any], result: dict[str, Any] | None) -> tuple[bool, list[float]]:
    allowed = _numbers(args) + _numbers(result or {}) + _answer_numbers(query) + [float(i) for i in range(1, 8)] + [32647.0]
    unsupported: list[float] = []
    for number in _answer_numbers(answer):
        if not any(math.isclose(number, item, rel_tol=0.015, abs_tol=0.02) for item in allowed):
            unsupported.append(number)
    return not unsupported, unsupported


def _replay_tool(trace: dict[str, Any], row: dict[str, str], limit: int) -> dict[str, Any] | None:
    if not trace:
        return None
    bbox = _parse_json(row.get("bbox_json", ""), None)
    return execute_tool(
        trace["tool"],
        trace.get("parameters") or {},
        request_bbox=bbox,
        request_geometry=None,
        request_limit=limit,
    )


def _actual_intent(expected: str, traces: list[dict[str, Any]], response: dict[str, Any]) -> str:
    if traces:
        mapped = TOOL_TO_INTENT.get(traces[0].get("tool"), "unknown")
        if expected == "ndvi_followup" and mapped == "ndvi":
            return "ndvi_followup"
        return mapped
    parsed = response.get("intent") or {}
    fallback = str(parsed.get("fallback_type") or "").lower()
    if "unsupported" in fallback:
        return "unsupported"
    if parsed.get("clarification_required"):
        if expected == "proximity_missing_distance":
            return expected
        return "ambiguous"
    return "no_tool"


def _usage(response: dict[str, Any], key: str) -> int | float | str:
    value = ((response.get("llm") or {}).get("usage") or {}).get(key)
    return "N/A" if value is None else value


def _mean(values: list[float]) -> float | str:
    return statistics.mean(values) if values else "N/A"


def _sample_sd(values: list[float]) -> float | str:
    return statistics.stdev(values) if len(values) > 1 else "N/A"


def _pct(rows: list[dict[str, Any]], key: str) -> float:
    return 100.0 * sum(bool(row[key]) for row in rows) / len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live", action="store_true", help="Required: authorizes the fixed paid benchmark")
    args = parser.parse_args()
    if not args.confirm_live:
        parser.error("--confirm-live is required; no provider request was sent")

    load_local_env()
    if _sha256(GOLD_PATH) != EXPECTED_GOLD_SHA256:
        raise RuntimeError("Gold set checksum mismatch; benchmark stopped before any provider request")

    status = _http_json("GET", "/api/system/integration-status")
    database = status.get("database") or status.get("postgis") or {}
    llm = status.get("llm_provider") or status.get("llm") or {}
    checks = {
        "database_mode_postgis": database.get("mode") == "postgis",
        "database_connected": bool(database.get("connected")),
        "database_role_read_only": bool(database.get("role_read_only")),
        "polygon_count_155199": int(database.get("polygon_count") or 0) == 155199,
        "llm_enabled": bool(llm.get("enabled")),
    }
    if not all(checks.values()):
        raise RuntimeError(f"Live preflight failed: {checks}")

    with GOLD_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        gold_rows = list(csv.DictReader(handle))
    if len(gold_rows) != 20:
        raise RuntimeError(f"Expected 20 gold queries, found {len(gold_rows)}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    run_rows: list[dict[str, Any]] = []
    for provider in ("openai", "deepseek"):
        for row in gold_rows:
            payload: dict[str, Any] = {
                "query": row["query"],
                "limit": 5,
                "provider": provider,
                "history": _parse_json(row["history_json"], []),
            }
            bbox = _parse_json(row.get("bbox_json", ""), None)
            if bbox is not None:
                payload["bbox"] = bbox
            started = time.perf_counter()
            error = ""
            response: dict[str, Any]
            try:
                response = _http_json("POST", "/api/agent/query", payload, timeout=240)
            except Exception as exc:
                response = {}
                error = f"{type(exc).__name__}: {exc}"
            latency_ms = (time.perf_counter() - started) * 1000.0
            traces = [item for item in response.get("tool_trace", []) if item.get("status") == "success"]
            expected_tool = row["expected_tool"].strip()
            actual_tools = [item.get("tool", "") for item in traces]
            expected_args = _parse_json(row["expected_arguments_json"], {})
            actual_args = traces[0].get("parameters", {}) if traces else {}
            actual_intent = _actual_intent(row["expected_intent"], traces, response)
            replay_result = None
            replay_error = ""
            if traces:
                try:
                    replay_result = _replay_tool(traces[0], row, 5)
                except Exception as exc:
                    replay_error = f"{type(exc).__name__}: {exc}"

            expected_clarification = row["clarification_required"].lower() == "true"
            actual_clarification = response.get("status") == "clarification_required"
            llm_used = bool((response.get("llm") or {}).get("used"))
            provider_match = (response.get("llm") or {}).get("provider") == provider
            tool_selection_correct = (not expected_tool and not actual_tools) or (actual_tools == [expected_tool])
            argument_accuracy = (not expected_tool and not actual_args) or _equivalent(expected_args, actual_args)
            tool_execution_success = (not expected_tool and not replay_error) or (bool(traces) and not replay_error)
            grounded, unsupported_numbers = _grounded(response.get("answer", ""), row["query"], actual_args, replay_result)
            intent_correct = actual_intent == row["expected_intent"]
            clarification_correct = actual_clarification == expected_clarification
            followup_correct = (row["followup_expected"].lower() != "true") or (
                bool(traces) and traces[0].get("tool") == "get_ndvi_stats" and actual_args.get("feature_id") == 140432
            )
            unsupported_correct = (row["expected_intent"] != "unsupported") or (not traces and actual_clarification)
            provider_error = bool(error) or not llm_used or not provider_match
            overall_pass = all([
                not provider_error,
                intent_correct,
                tool_selection_correct,
                argument_accuracy,
                tool_execution_success,
                grounded,
                clarification_correct,
                followup_correct,
                unsupported_correct,
            ])
            raw_path = RAW_DIR / f"{provider}_{row['query_id']}.json"
            raw_path.write_text(json.dumps({"gold": row, "response": response, "tool_replay": replay_result, "error": error}, ensure_ascii=False, indent=2), encoding="utf-8")
            tool_summary = ""
            if replay_result is not None:
                tool_summary = json.dumps({
                    "count": replay_result.get("count"),
                    "total_matches": replay_result.get("total_matches"),
                    "keys": sorted(replay_result.keys()),
                }, ensure_ascii=False)
            run_rows.append({
                "run_id": str(uuid.uuid4()),
                "provider": provider,
                "model": (response.get("llm") or {}).get("model", "N/A"),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "query_id": row["query_id"],
                "category": row["category"],
                "query": row["query"],
                "expected_intent": row["expected_intent"],
                "actual_intent": actual_intent,
                "intent_correct": intent_correct,
                "expected_tool": expected_tool or "NONE",
                "actual_tools": "|".join(actual_tools) or "NONE",
                "expected_arguments": json.dumps(expected_args, ensure_ascii=False, sort_keys=True),
                "actual_arguments": json.dumps(actual_args, ensure_ascii=False, sort_keys=True),
                "tool_selection_correct": tool_selection_correct,
                "argument_accuracy": argument_accuracy,
                "clarification_expected": expected_clarification,
                "clarification_given": actual_clarification,
                "tool_execution_success": tool_execution_success,
                "tool_result_summary": tool_summary,
                "grounded_no_unsupported_numbers": grounded,
                "answer_grounded": grounded,
                "unsupported_numbers": json.dumps(unsupported_numbers, ensure_ascii=False),
                "hallucinated_gis_values": json.dumps(unsupported_numbers, ensure_ascii=False),
                "clarification_correct": clarification_correct,
                "unsupported_handling_correct": unsupported_correct,
                "followup_correct": followup_correct,
                "latency_ms": round(latency_ms, 3),
                "tool_rounds": (response.get("llm") or {}).get("rounds", "N/A"),
                "input_tokens": _usage(response, "input_tokens"),
                "output_tokens": _usage(response, "output_tokens"),
                "total_tokens": _usage(response, "total_tokens"),
                "cost_usd": "N/A",
                "provider_error": provider_error,
                "overall_pass": overall_pass,
                "error": error or ((response.get("llm") or {}).get("fallback_reason") or ""),
                "tool_replay_error": replay_error,
                "final_answer": response.get("answer", ""),
                "raw_artifact": str(raw_path),
            })
            print(f"{provider} {row['query_id']} {'PASS' if overall_pass else 'FAIL'} {latency_ms:.0f}ms", flush=True)

    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUNS_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(run_rows[0]))
        writer.writeheader()
        writer.writerows(run_rows)

    comparison_rows: list[dict[str, Any]] = []
    for provider in ("openai", "deepseek"):
        subset = [row for row in run_rows if row["provider"] == provider]
        latencies = [float(row["latency_ms"]) for row in subset]
        total_tokens = [float(row["total_tokens"]) for row in subset if row["total_tokens"] != "N/A"]
        tool_rounds = [float(row["tool_rounds"]) for row in subset if row["tool_rounds"] != "N/A"]
        input_tokens = [float(row["input_tokens"]) for row in subset if row["input_tokens"] != "N/A"]
        output_tokens = [float(row["output_tokens"]) for row in subset if row["output_tokens"] != "N/A"]
        comparison_rows.append({
            "provider": provider,
            "query_count": len(subset),
            "overall_pass_count": sum(bool(row["overall_pass"]) for row in subset),
            "overall_pass_rate_pct": round(_pct(subset, "overall_pass"), 3),
            "intent_accuracy_pct": round(_pct(subset, "intent_correct"), 3),
            "tool_selection_accuracy_pct": round(_pct(subset, "tool_selection_correct"), 3),
            "argument_accuracy_pct": round(_pct(subset, "argument_accuracy"), 3),
            "tool_execution_success_pct": round(_pct(subset, "tool_execution_success"), 3),
            "grounding_rate_pct": round(_pct(subset, "grounded_no_unsupported_numbers"), 3),
            "hallucination_rate_pct": round(100.0 - _pct(subset, "grounded_no_unsupported_numbers"), 3),
            "clarification_accuracy_pct": round(_pct(subset, "clarification_correct"), 3),
            "unsupported_query_accuracy_pct": round(100.0 * sum(bool(r["unsupported_handling_correct"]) for r in subset if r["query_id"] == "Q18") / 1, 3),
            "followup_accuracy_pct": round(100.0 * sum(bool(r["followup_correct"]) for r in subset if r["query_id"] == "Q20") / 1, 3),
            "latency_mean_ms": round(float(_mean(latencies)), 3),
            "latency_sample_sd_ms": round(float(_sample_sd(latencies)), 3),
            "latency_median_ms": round(statistics.median(latencies), 3),
            "error_count": sum(bool(row["provider_error"]) for row in subset),
            "error_rate_pct": round(_pct(subset, "provider_error"), 3),
            "average_tool_rounds": round(float(_mean(tool_rounds)), 3) if tool_rounds else "N/A",
            "average_input_tokens": round(float(_mean(input_tokens)), 3) if input_tokens else "N/A",
            "average_output_tokens": round(float(_mean(output_tokens)), 3) if output_tokens else "N/A",
            "average_total_tokens": round(float(_mean(total_tokens)), 3) if total_tokens else "N/A",
            "total_tokens": int(sum(total_tokens)) if total_tokens else "N/A",
            "cost_usd": "NOT AVAILABLE",
        })

    COMPARISON_CSV.parent.mkdir(parents=True, exist_ok=True)
    with COMPARISON_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(comparison_rows[0]))
        writer.writeheader()
        writer.writerows(comparison_rows)

    lines = [
        "# Live LLM Provider Comparison",
        "",
        f"Locked gold set: `{GOLD_PATH}` (SHA-256 `{EXPECTED_GOLD_SHA256}`)",
        "",
        "| Provider | Pass | Intent | Tool | Arguments | Grounding | Mean latency (ms) | Tokens |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in comparison_rows:
        lines.append(
            f"| {row['provider']} | {row['overall_pass_rate_pct']:.1f}% | {row['intent_accuracy_pct']:.1f}% | "
            f"{row['tool_selection_accuracy_pct']:.1f}% | {row['argument_accuracy_pct']:.1f}% | "
            f"{row['grounding_rate_pct']:.1f}% | {row['latency_mean_ms']:.1f} | {row['total_tokens']} |"
        )
    lines += [
        "",
        "Cost is marked NOT AVAILABLE because this package does not contain a verified immutable price table for both configured model identifiers.",
        "No statistical-significance claim is made from this 20-query operational benchmark.",
    ]
    COMPARISON_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {RUNS_PATH}")
    print(f"WROTE {COMPARISON_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
