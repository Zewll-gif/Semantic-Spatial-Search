# CLEAN PROJECT HEADER
# ไฟล์: run_benchmark.py
# หน้าที่: ไฟล์สนับสนุน CLEAN PROJECT
# Input: ไฟล์และ config ที่อ้างในโค้ด
# Output: ผลลัพธ์ตามหน้าที่ของไฟล์
# Dependency สำคัญ: README และ artifact ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Controlled multi-provider orchestration benchmark. Dry-run never calls an API."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BENCH_ROOT = Path(__file__).resolve().parent
APP_ROOT = BENCH_ROOT.parent
BACKEND_ROOT = APP_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from benchmark_core import calculate_cost, load_dataset, normalize_provider_payload, score_run, sha256_file, summarize_records
from providers import ProviderConfigurationError, make_provider
from gis_tools import calculate_distance, filter_by_area, find_nearby, get_evidence, get_feature_details, get_geojson, get_index_stats, intersects, search_landcover
from rag_service import search_knowledge

DATASET_PATH = BENCH_ROOT / "agent_benchmark_v1.json"
PROMPT_PATH = BENCH_ROOT / "system_prompt_v1.txt"
PRICING_PATH = BENCH_ROOT / "provider_pricing.json"
MODEL_SELECTION_PATH = BENCH_ROOT / "model_selection_v1.json"
RAW_DIR = BENCH_ROOT / "results" / "raw"
SUMMARY_DIR = BENCH_ROOT / "results" / "summary"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark LLM orchestration without scoring GIS correctness.")
    parser.add_argument("--provider", choices=["openai", "gemini", "anthropic", "all"], default="all")
    parser.add_argument("--model", help="Optional assertion of the locked model ID for one provider; overrides are refused.")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--query-id")
    parser.add_argument("--category", choices=["spatial", "knowledge", "mixed", "ambiguous", "unsupported"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=Path, help="Explicit JSONL path for resumable runs.")
    return parser.parse_args()


def _selected_queries(dataset: dict[str, Any], query_id: str | None, category: str | None) -> list[dict[str, Any]]:
    queries = dataset["queries"]
    if query_id:
        queries = [q for q in queries if q["id"] == query_id]
        if not queries:
            raise ValueError(f"Unknown query ID: {query_id}")
    if category:
        queries = [q for q in queries if q["category"] == category]
    return queries


def _locked_models() -> tuple[dict[str, Any], dict[str, str]]:
    selection = json.loads(MODEL_SELECTION_PATH.read_text(encoding="utf-8"))
    models = selection["models"]
    if selection["selection_date"] != "2026-09-16" or set(models) != {"openai", "gemini", "anthropic"}:
        raise ValueError("Invalid predefined model selection metadata")
    if len(selection.get("inclusion_criteria", [])) != 6:
        raise ValueError("Incomplete model inclusion criteria")
    return selection, models


def _selected_model(provider_name: str, requested: str | None, models: dict[str, str]) -> str:
    locked = models[provider_name]
    if requested is not None and requested != locked:
        raise ValueError(f"Model override refused for {provider_name}: locked model is {locked}")
    return locked


def dry_run_report(args: argparse.Namespace) -> dict[str, Any]:
    dataset = load_dataset(DATASET_PATH)
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    selection, models = _locked_models()
    json.loads((BACKEND_ROOT / "config" / "class_schema.json").read_text(encoding="utf-8"))
    contract = json.loads((APP_ROOT / "agent_tools_v2.json").read_text(encoding="utf-8"))
    selected = _selected_queries(dataset, args.query_id, args.category)
    providers = [args.provider] if args.provider != "all" else ["openai", "gemini", "anthropic"]
    configs = {}
    for name in providers:
        model = _selected_model(name, args.model if len(providers) == 1 else None, models)
        adapter = make_provider(name, model)
        price = pricing.get("providers", {}).get(name, {}).get(model, {})
        if price.get("input_usd_per_1m") is None or price.get("output_usd_per_1m") is None:
            raise ValueError(f"Missing standard input/output pricing for {name}/{model}")
        configs[name] = {
            "model": model,
            "missing": adapter.validate_config(),
            "seed_supported": adapter.seed_supported,
            "sampling_parameters_sent": [],
            "sampling_policy": "provider_model_default",
            "actual_sampling_behavior": "not_observed_dry_run",
            "account_level_model_access": "not_tested_no_paid_calls",
        }
    counts = {category: sum(q["category"] == category for q in dataset["queries"]) for category in ["spatial", "knowledge", "mixed", "ambiguous", "unsupported"]}
    return {
        "status": "PASS",
        "api_calls_made": 0,
        "benchmark_version": dataset["benchmark_version"],
        "model_selection_date": selection["selection_date"],
        "locked_models": models,
        "model_selection_sha256": sha256_file(MODEL_SELECTION_PATH),
        "pricing_sha256": sha256_file(PRICING_PATH),
        "inclusion_criteria": selection["inclusion_criteria"],
        "prompt_sha256": sha256_file(PROMPT_PATH),
        "dataset_sha256": sha256_file(DATASET_PATH),
        "tool_contract_sha256": sha256_file(APP_ROOT / "agent_tools_v2.json"),
        "tool_count": len(contract["tools"]),
        "query_count_total": len(dataset["queries"]),
        "query_count_selected": len(selected),
        "category_counts": counts,
        "runs": args.runs,
        "planned_runs": len(selected) * args.runs * len(providers),
        "pilot_calls_per_provider_full_dataset": len(dataset["queries"]) * 3,
        "paid_pilot_ready": False,
        "paid_pilot_blockers": [
            "Provider credentials are missing for one or more locked models" if any(item["missing"] for item in configs.values()) else "Credentials were not tested",
            "Account-level model access and live endpoint compatibility are unverified because no paid API calls were made"
        ],
        "provider_configuration": configs,
        "gold_answers_locked": dataset["metadata"]["gold_answers_locked"],
        "created_before_provider_runs": dataset["metadata"]["created_before_provider_runs"],
    }


def _execute_tool(name: str, arguments: dict[str, Any]) -> Any:
    allowed = {
        "search_landcover": search_landcover,
        "filter_by_area": filter_by_area,
        "find_nearby": find_nearby,
        "calculate_distance": calculate_distance,
        "intersects": intersects,
        "get_feature_details": get_feature_details,
        "get_ndvi_stats": lambda **kw: get_index_stats("ndvi", **kw),
        "get_ndwi_stats": lambda **kw: get_index_stats("ndwi", **kw),
        "get_geojson": get_geojson,
        "get_evidence": get_evidence,
    }
    if name not in allowed:
        raise ValueError(f"Tool not allow-listed: {name}")
    return allowed[name](**arguments)


def _compact(value: Any, limit: int = 50000) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return value
    return {"truncated": True, "character_count": len(text), "preview": text[:limit]}


def _sum_usage(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key in ("input_tokens", "output_tokens", "cached_tokens", "cache_creation_tokens"):
        values = [x for x in (a.get(key), b.get(key)) if x is not None]
        result[key] = sum(int(x) for x in values) if values else None
    return result


def execute_one(provider, query: dict[str, Any], run_id: int, system_prompt: str) -> dict[str, Any]:
    total_started = time.perf_counter()
    planning_prompt = f"PLANNING PHASE. User query:\n{query['query']}"
    plan_result = provider.invoke_json(system_prompt, planning_prompt)
    actual = normalize_provider_payload(plan_result.raw, provider.name, provider.model, query["id"], run_id)
    provider_latency = plan_result.latency_ms
    usage = plan_result.usage
    sampling = {"planning": plan_result.sampling_metadata}
    execution = {"gis_success_count": 0, "rag_success_count": 0, "tool_results": [], "rag_results": []}
    tool_started = time.perf_counter()

    if not actual["parsed"]["clarification_required"] and not actual["parsed"]["unsupported"]:
        for call in actual["tool_calls"]:
            try:
                result = _execute_tool(call["name"], call["arguments"])
                execution["gis_success_count"] += 1
                execution["tool_results"].append({"tool": call["name"], "status": "success", "result": _compact(result)})
            except Exception as exc:
                execution["tool_results"].append({"tool": call["name"], "status": "error", "error": f"{type(exc).__name__}: {exc}"})
                actual["errors"].append({"stage": "tool_execution", "tool": call["name"], "error": str(exc)})
        for request in actual["rag_retrieval"]:
            category = request.get("category")
            if category == "per_class_validation":
                category = "validation_limitations"
            result = search_knowledge(request.get("query") or query["query"], category=category, top_k=4)
            if result["count"]:
                execution["rag_success_count"] += 1
            execution["rag_results"].append(result)

    tool_latency = (time.perf_counter() - tool_started) * 1000.0
    actual["execution"] = execution

    has_grounding_material = execution["gis_success_count"] or execution["rag_success_count"]
    if has_grounding_material and not actual["parsed"]["clarification_required"] and not actual["parsed"]["unsupported"]:
        evidence = _compact({"tool_results": execution["tool_results"], "rag_results": execution["rag_results"]}, limit=80000)
        final_prompt = f"FINALIZATION PHASE. User query:\n{query['query']}\n\nVerified tool/RAG results:\n{json.dumps(evidence, ensure_ascii=False)}"
        final_result = provider.invoke_json(system_prompt, final_prompt)
        final_payload = final_result.raw
        actual["answer"] = str(final_payload.get("answer", ""))
        provider_latency += final_result.latency_ms
        usage = _sum_usage(usage, final_result.usage)
        sampling["finalization"] = final_result.sampling_metadata
        actual["provider_reported_usage"] = {"planning": plan_result.provider_reported_usage, "finalization": final_result.provider_reported_usage}
    else:
        actual["provider_reported_usage"] = {"planning": plan_result.provider_reported_usage}

    actual["usage"] = usage
    actual["seed_supported"] = provider.seed_supported
    actual["sampling_configuration"] = sampling
    actual["latency_ms"] = {
        "total": (time.perf_counter() - total_started) * 1000.0,
        "provider": provider_latency,
        "tool": tool_latency,
    }
    return actual


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["actual"]["provider"], record["actual"]["model"])
        by_model.setdefault(key, []).append(record)
    rows = [summarize_records(items) for items in by_model.values()]
    passed = [row for row in rows if row.get("selection_gate", {}).get("passed")]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": rows,
        "selection": {
            "rule": "Report eligible candidates only; do not auto-select a winner.",
            "eligible_candidates": [{"provider": row["provider"], "model": row["model"]} for row in passed],
            "status": "CANDIDATES_MET_GATE" if passed else "NO_CANDIDATE_MET_ALL_THRESHOLDS",
        },
    }
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    (SUMMARY_DIR / "benchmark_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["provider", "model", "run_count", "query_count", "intent_accuracy", "class_resolution_accuracy", "parameter_extraction_score", "tool_selection_accuracy", "clarification_accuracy", "unsupported_handling_accuracy", "grounding_rate", "consistency_rate", "median_latency_ms", "p95_latency_ms", "total_cost_usd", "mean_cost_per_query_usd"]
    with (SUMMARY_DIR / "benchmark_summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})
    return payload


def main() -> int:
    args = parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be >= 1")
    if not args.dry_run and args.runs != 3:
        raise SystemExit("Formal benchmark requires exactly three repeated runs")
    if args.provider == "all" and args.model:
        raise SystemExit("--model can only be used with one provider")
    if args.resume and args.output is None:
        raise SystemExit("--resume requires an explicit --output JSONL path")
    if args.provider == "all" and args.output is not None:
        raise SystemExit("--output requires one provider; use separate paths for each provider")
    selection, locked_models = _locked_models()
    if args.provider != "all":
        _selected_model(args.provider, args.model, locked_models)
    if args.dry_run:
        report = dry_run_report(args)
        SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
        (SUMMARY_DIR / "dry_run_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    dataset = load_dataset(DATASET_PATH)
    queries = _selected_queries(dataset, args.query_id, args.category)
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    provider_names = [args.provider] if args.provider != "all" else ["openai", "gemini", "anthropic"]
    all_records: list[dict[str, Any]] = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for provider_name in provider_names:
        provider = make_provider(provider_name, _selected_model(provider_name, args.model if len(provider_names) == 1 else None, locked_models))
        provider.require_config()
        safe_model = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in provider.model)
        output = args.output or (RAW_DIR / f"{provider_name}_{safe_model}_{timestamp}.jsonl")
        if output.exists() and not args.resume:
            raise SystemExit(f"Output already exists; use --resume or a new path: {output}")
        existing = _load_jsonl(output) if args.resume else []
        expected_hash = sha256_file(PROMPT_PATH)
        expected_dataset_hash = sha256_file(DATASET_PATH)
        expected_contract_hash = sha256_file(APP_ROOT / "agent_tools_v2.json")
        for record in existing:
            if (record.get("benchmark_version") != dataset["benchmark_version"]
                    or record.get("prompt_sha256") != expected_hash
                    or record.get("dataset_sha256") != expected_dataset_hash
                    or record.get("tool_contract_sha256") != expected_contract_hash
                    or record.get("model_selection_sha256") != sha256_file(MODEL_SELECTION_PATH)
                    or record.get("pricing_sha256") != sha256_file(PRICING_PATH)):
                raise SystemExit("Resume refused: benchmark version, prompt, dataset or tool-contract hash mismatch")
            if record.get("actual", {}).get("model") != provider.model or record.get("actual", {}).get("provider") != provider_name:
                raise SystemExit("Resume refused: provider/model mismatch")
        completed = {(r["query_id"], int(r["run_id"])) for r in existing if not r.get("actual", {}).get("errors")}
        # Keep only the latest attempt per query/run for summary calculation.
        latest = {(r["query_id"], int(r["run_id"])): r for r in existing}
        for query in queries:
            for run_id in range(1, args.runs + 1):
                if (query["id"], run_id) in completed:
                    continue
                try:
                    actual = execute_one(provider, query, run_id, prompt)
                except Exception as exc:
                    actual = normalize_provider_payload({"parsed": {}, "answer": "", "tool_calls": [], "rag_queries": []}, provider.name, provider.model, query["id"], run_id)
                    actual["errors"] = [{"stage": "provider", "error": f"{type(exc).__name__}: {exc}"}]
                    actual["seed_supported"] = provider.seed_supported
                    actual["sampling_configuration"] = {"status": "provider_call_failed", "actual_sampling_behavior": "unknown"}
                record = {
                    "benchmark_version": dataset["benchmark_version"],
                    "prompt_sha256": sha256_file(PROMPT_PATH),
                    "dataset_sha256": expected_dataset_hash,
                    "tool_contract_sha256": expected_contract_hash,
                    "model_selection_date": selection["selection_date"],
                    "model_selection_sha256": sha256_file(MODEL_SELECTION_PATH),
                    "pricing_sha256": sha256_file(PRICING_PATH),
                    "query_id": query["id"],
                    "category": query["category"],
                    "run_id": run_id,
                    "gold": query["gold"],
                    "actual": actual,
                }
                record["scores"] = score_run(query, actual)
                record["cost_usd"] = calculate_cost(actual.get("usage", {}), provider.name, provider.model, pricing)
                _append_jsonl(output, record)
                latest[(query["id"], run_id)] = record
                print(f"{provider.name}/{provider.model} {query['id']} run={run_id} complete")
        all_records.extend(latest.values())
    summary = _write_summary(all_records)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
