# CLEAN PROJECT HEADER
# ไฟล์: benchmark_core.py
# หน้าที่: ไฟล์สนับสนุน CLEAN PROJECT
# Input: ไฟล์และ config ที่อ้างในโค้ด
# Output: ผลลัพธ์ตามหน้าที่ของไฟล์
# Dependency สำคัญ: README และ artifact ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Reproducible validation, normalization, scoring, consistency and cost logic."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

REQUIRED_GOLD_FIELDS = {
    "mode", "classes", "parameters", "expected_tools", "clarification_required",
    "unsupported", "knowledge_topics", "reliability_required", "must_not_claim",
}
VALID_MODES = {"spatial", "knowledge", "mixed"}
VALID_CLASSES = {f"R{i}" for i in range(1, 8)}
VALID_CATEGORIES = {"spatial", "knowledge", "mixed", "ambiguous", "unsupported"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_dataset(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_dataset(payload)
    return payload


def validate_dataset(payload: dict[str, Any]) -> None:
    if payload.get("benchmark_version") != "1.0":
        raise ValueError("benchmark_version must be 1.0")
    metadata = payload.get("metadata", {})
    if metadata.get("created_before_provider_runs") is not True or metadata.get("gold_answers_locked") is not True:
        raise ValueError("gold answers must be locked before provider runs")
    queries = payload.get("queries")
    if not isinstance(queries, list) or len(queries) != 30:
        raise ValueError("benchmark must contain exactly 30 queries")
    ids = [item.get("id") for item in queries]
    if len(set(ids)) != len(ids):
        raise ValueError("query IDs must be unique")
    counts = Counter(item.get("category") for item in queries)
    if counts != Counter({category: 6 for category in VALID_CATEGORIES}):
        raise ValueError(f"each category must contain 6 queries: {dict(counts)}")
    for item in queries:
        if item.get("category") not in VALID_CATEGORIES or not str(item.get("query", "")).strip():
            raise ValueError(f"invalid query record: {item.get('id')}")
        gold = item.get("gold", {})
        missing = REQUIRED_GOLD_FIELDS - set(gold)
        if missing:
            raise ValueError(f"{item['id']} missing gold fields: {sorted(missing)}")
        if gold["mode"] not in VALID_MODES:
            raise ValueError(f"{item['id']} invalid mode")
        for value in gold["classes"].values():
            if value is not None and isinstance(value, str) and value.startswith("R") and value not in VALID_CLASSES:
                raise ValueError(f"{item['id']} invalid canonical class {value}")


def parse_json_response(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def normalize_provider_payload(raw: str | dict[str, Any], provider: str, model: str, query_id: str, run_id: int) -> dict[str, Any]:
    payload = parse_json_response(raw)
    parsed = payload.get("parsed") if isinstance(payload.get("parsed"), dict) else {}
    tool_calls = []
    for item in payload.get("tool_calls", []) or []:
        if isinstance(item, str):
            tool_calls.append({"name": item, "arguments": {}})
        elif isinstance(item, dict) and item.get("name"):
            tool_calls.append({"name": str(item["name"]), "arguments": item.get("arguments") or {}})
    rag_queries = []
    for item in payload.get("rag_queries", payload.get("rag_retrieval", [])) or []:
        if isinstance(item, str):
            rag_queries.append({"query": item, "category": None})
        elif isinstance(item, dict):
            rag_queries.append({"query": str(item.get("query", "")), "category": item.get("category")})
    return {
        "provider": provider,
        "model": model,
        "query_id": query_id,
        "run_id": int(run_id),
        "parsed": {
            "mode": parsed.get("mode"),
            "classes": parsed.get("classes") if isinstance(parsed.get("classes"), dict) else {},
            "parameters": parsed.get("parameters") if isinstance(parsed.get("parameters"), dict) else {},
            "clarification_required": bool(parsed.get("clarification_required", False)),
            "clarification_topic": parsed.get("clarification_topic"),
            "unsupported": bool(parsed.get("unsupported", False)),
            "unsupported_capabilities": parsed.get("unsupported_capabilities") or [],
        },
        "tool_calls": tool_calls,
        "rag_retrieval": rag_queries,
        "answer": str(payload.get("answer", "")),
        "latency_ms": payload.get("latency_ms") or {"total": None, "provider": None, "tool": None},
        "usage": payload.get("usage") or {},
        "execution": payload.get("execution") or {"gis_success_count": 0, "rag_success_count": 0},
        "errors": payload.get("errors") or [],
    }


def _equivalent(expected: Any, actual: Any, key: str) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return math.isclose(float(expected), float(actual), rel_tol=1e-6, abs_tol=1e-6)
        except (TypeError, ValueError):
            return False
    if key == "area_unit":
        aliases = {"rai": {"rai", "ไร่"}, "sqm": {"sqm", "m2", "m²"}, "hectare": {"hectare", "ha", "เฮกตาร์"}}
        return str(actual).lower() in aliases.get(str(expected).lower(), {str(expected).lower()})
    if key == "relation" and expected == "intersects_or_touching":
        return str(actual).lower() in {"intersects_or_touching", "intersects", "touches", "intersect_or_touch"}
    return str(expected).lower() == str(actual).lower()


def score_intent(gold: dict[str, Any], actual: dict[str, Any]) -> float:
    return float(actual["parsed"].get("mode") == gold["mode"])


def score_classes(gold: dict[str, Any], actual: dict[str, Any]) -> float:
    expected = gold.get("classes", {})
    if not expected:
        return 1.0 if not actual["parsed"].get("classes") else 0.0
    values = [float(_equivalent(value, actual["parsed"].get("classes", {}).get(key), key)) for key, value in expected.items()]
    return sum(values) / len(values)


def score_parameters(gold: dict[str, Any], actual: dict[str, Any]) -> float:
    ignored = {"expected_answer_fact", "alpha", "beta", "suitability_criteria"}
    expected = {k: v for k, v in gold.get("parameters", {}).items() if k not in ignored and v is not None}
    if not expected:
        return 1.0
    params = actual["parsed"].get("parameters", {})
    values = [float(_equivalent(value, params.get(key), key)) for key, value in expected.items()]
    return sum(values) / len(values)


def score_tools(gold: dict[str, Any], actual: dict[str, Any]) -> float:
    expected = set(gold.get("expected_tools", []))
    actual_names = [x.get("name") for x in actual.get("tool_calls", [])]
    actual_set = set(actual_names)
    if not expected:
        return 1.0 if not actual_set else 0.0
    required_fraction = len(expected & actual_set) / len(expected)
    extras = len(actual_set - expected)
    return required_fraction / (1.0 + extras)


def score_clarification(gold: dict[str, Any], actual: dict[str, Any]) -> float:
    expected = bool(gold.get("clarification_required"))
    actual_flag = bool(actual["parsed"].get("clarification_required"))
    if expected:
        no_premature_gis = int(actual.get("execution", {}).get("gis_success_count", 0)) == 0 and not actual.get("tool_calls")
        topic = gold.get("clarification_topic")
        topic_ok = True if not topic else actual["parsed"].get("clarification_topic") == topic
        return float(actual_flag and no_premature_gis and topic_ok)
    return float(not actual_flag)


def score_unsupported(gold: dict[str, Any], actual: dict[str, Any]) -> float:
    expected = bool(gold.get("unsupported"))
    actual_flag = bool(actual["parsed"].get("unsupported"))
    if not expected:
        return float(not actual_flag)
    prohibited = [str(x).lower() for x in gold.get("must_not_claim", [])]
    answer = actual.get("answer", "").lower()
    no_forbidden_claim = not any(claim and claim in answer for claim in prohibited)
    no_gis = int(actual.get("execution", {}).get("gis_success_count", 0)) == 0 and not actual.get("tool_calls")
    required_capabilities = set(gold.get("unsupported_capabilities", []))
    stated_capabilities = set(actual["parsed"].get("unsupported_capabilities", []))
    limitation_stated = bool(required_capabilities) and required_capabilities <= stated_capabilities
    parent = gold.get("classes", {}).get("supported_parent_class")
    parent_correct = parent is None or actual["parsed"].get("classes", {}).get("supported_parent_class") == parent
    parent_explained = parent is None or parent.lower() in answer
    return float(actual_flag and bool(answer.strip()) and no_forbidden_claim and no_gis and limitation_stated and parent_correct and parent_explained)


def score_grounding(gold: dict[str, Any], actual: dict[str, Any]) -> float | None:
    if gold.get("clarification_required") or gold.get("unsupported"):
        return None
    if not actual.get("answer", "").strip():
        return 0.0
    gis_ok = int(actual.get("execution", {}).get("gis_success_count", 0)) > 0
    rag_ok = int(actual.get("execution", {}).get("rag_success_count", 0)) > 0
    if gold["mode"] == "spatial":
        return float(gis_ok)
    if gold["mode"] == "knowledge":
        return float(rag_ok)
    return float(gis_ok and rag_ok)


def score_run(query: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    gold = query["gold"]
    return {
        "intent_accuracy": score_intent(gold, actual),
        "class_resolution_accuracy": score_classes(gold, actual),
        "parameter_extraction_score": score_parameters(gold, actual),
        "tool_selection_accuracy": score_tools(gold, actual),
        "clarification_accuracy": score_clarification(gold, actual),
        "unsupported_handling_accuracy": score_unsupported(gold, actual),
        "grounding_rate": score_grounding(gold, actual),
    }


def consistency_rate(records: list[dict[str, Any]]) -> float:
    if len(records) <= 1:
        return 1.0
    signatures = []
    for record in records:
        parsed = record["actual"]["parsed"]
        signatures.append(json.dumps({
            "mode": parsed.get("mode"),
            "classes": parsed.get("classes", {}),
            "parameters": parsed.get("parameters", {}),
            "clarification_required": parsed.get("clarification_required"),
            "unsupported": parsed.get("unsupported"),
            "tools": [x.get("name") for x in record["actual"].get("tool_calls", [])],
        }, ensure_ascii=False, sort_keys=True))
    counts = Counter(signatures)
    return max(counts.values()) / len(signatures)


def calculate_cost(usage: dict[str, Any], provider: str, model: str, pricing: dict[str, Any]) -> float | None:
    model_price = pricing.get("providers", {}).get(provider, {}).get(model)
    if not model_price:
        return None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    cached_tokens = usage.get("cached_tokens", 0) or 0
    cache_creation_tokens = usage.get("cache_creation_tokens", 0) or 0
    if input_tokens is None or output_tokens is None:
        return None
    input_rate = model_price.get("input_usd_per_1m", model_price.get("input_per_1m"))
    output_rate = model_price.get("output_usd_per_1m", model_price.get("output_per_1m"))
    cached_rate = model_price.get("cached_input_usd_per_1m", model_price.get("cached_input_per_1m"))
    creation_rate = model_price.get("cache_creation_input_usd_per_1m", model_price.get("cache_creation_input_per_1m"))
    if input_rate is None or output_rate is None:
        return None
    if cached_tokens and cached_rate is None:
        return None
    if cache_creation_tokens and creation_rate is None:
        return None
    uncached = int(input_tokens) - int(cached_tokens) - int(cache_creation_tokens)
    if uncached < 0:
        return None
    cost = uncached * float(input_rate) / 1_000_000
    cost += int(cached_tokens) * float(cached_rate or 0) / 1_000_000
    cost += int(cache_creation_tokens) * float(creation_rate or 0) / 1_000_000
    cost += int(output_tokens) * float(output_rate) / 1_000_000
    return float(cost)


def _mean(values: list[float | None]) -> float | None:
    clean = [float(x) for x in values if x is not None]
    return sum(clean) / len(clean) if clean else None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    low, high = math.floor(rank), math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - rank) + ordered[high] * (rank - low)


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["query_id"]].append(record)
    latencies = [float(r["actual"].get("latency_ms", {}).get("total")) for r in records if r["actual"].get("latency_ms", {}).get("total") is not None]
    costs = [r.get("cost_usd") for r in records if r.get("cost_usd") is not None]
    metric_names = ["intent_accuracy", "class_resolution_accuracy", "parameter_extraction_score", "tool_selection_accuracy", "clarification_accuracy", "grounding_rate"]
    summary = {name: _mean([r["scores"].get(name) for r in records]) for name in metric_names}
    # Unsupported handling is assessed on unsupported cases only. Normal requests
    # must not dilute this safety gate with easy true negatives.
    summary["unsupported_handling_accuracy"] = _mean([
        r["scores"].get("unsupported_handling_accuracy")
        for r in records if r.get("category") == "unsupported"
    ])
    summary.update({
        "provider": records[0]["actual"]["provider"],
        "model": records[0]["actual"]["model"],
        "run_count": len(records),
        "query_count": len(grouped),
        "consistency_rate": _mean([consistency_rate(items) for items in grouped.values()]),
        "median_latency_ms": median(latencies) if latencies else None,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "total_cost_usd": sum(costs) if costs else None,
        "mean_cost_per_query_usd": (sum(costs) / len(grouped)) if costs else None,
    })
    thresholds = {"intent_accuracy": 0.95, "tool_selection_accuracy": 0.95, "unsupported_handling_accuracy": 1.0, "grounding_rate": 0.90}
    completed = {
        query_id: {int(item["run_id"]) for item in items if not item["actual"].get("errors")}
        for query_id, items in grouped.items()
    }
    full_coverage = len(completed) == 30 and all(len(runs) >= 3 for runs in completed.values())
    checks = {name: summary.get(name) is not None and summary[name] >= threshold for name, threshold in thresholds.items()}
    summary["selection_gate"] = {
        "thresholds": thresholds, "checks": checks,
        "full_dataset_three_runs_required": True,
        "full_coverage": full_coverage,
        "passed": full_coverage and all(checks.values()),
    }
    return summary
