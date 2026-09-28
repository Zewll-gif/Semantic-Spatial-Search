"""Provider-neutral A7-T agent loop; GIS tools remain authoritative."""
from __future__ import annotations

import json
import os
import time
from typing import Any

try:
    from intent_router import route_query
    from rag_service import search_knowledge
    from reliability import reliability_context
except ImportError:  # pragma: no cover
    from ..intent_router import route_query
    from ..rag_service import search_knowledge
    from ..reliability import reliability_context

from .prompts import build_instructions, build_user_input
from .providers import LLMProvider, ProviderError, get_provider
from .tool_registry import TOOL_DEFINITIONS, execute_tool, validate_tool_arguments
from .trace import TraceLogger


class AgentGroundingError(RuntimeError):
    pass


def _max_rounds() -> int:
    try:
        configured = int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "5"))
    except ValueError:
        configured = 5
    return max(1, min(configured, 5))


def _merge_usage(total: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:
    """Accumulate provider token usage across every model turn in one request."""
    merged = dict(total)
    for key, value in (current or {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            merged[key] = merged.get(key, 0) + value
        elif key not in merged:
            merged[key] = value
    return merged


def _tool_summary(name: str, result: dict[str, Any]) -> str:
    count = result.get("count", result.get("total_matches"))
    return f"{count} results" if count is not None else ", ".join(sorted(result.keys())[:6])


def _extract_geojson(tool_results: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    empty = {"type": "FeatureCollection", "features": []}
    for _, result in reversed(tool_results):
        candidate = result.get("geojson")
        if isinstance(candidate, dict) and candidate.get("type") == "FeatureCollection":
            return candidate
        if result.get("type") == "FeatureCollection":
            return result
        if result.get("type") == "Feature" and result.get("geometry"):
            return {"type": "FeatureCollection", "features": [result]}
        feature = result.get("feature")
        if isinstance(feature, dict) and feature.get("type") == "Feature":
            return {"type": "FeatureCollection", "features": [feature]}
    return empty


def _extract_distance_context(tool_results: list[tuple[str, dict[str, Any]]]) -> dict[str, Any] | None:
    """Keep authoritative display geometry local while exposing it to the map UI."""
    for _, result in reversed(tool_results):
        context = result.get("distance_context")
        if isinstance(context, dict):
            return context
    return None


def _tool_result_for_model(result: dict[str, Any]) -> dict[str, Any]:
    """Return only compact facts to the provider; geometry stays local for the map.

    Full polygon coordinates can be very large and are not needed to explain a
    GIS result.  Keeping them out of the next provider turn reduces latency and
    avoids context-limit failures without changing the authoritative tool result.
    """
    compact: dict[str, Any] = {}
    for key, value in result.items():
        if key in {"geojson", "geometry", "feature", "distance_context"}:
            continue
        if isinstance(value, list) and len(value) > 20:
            compact[key] = value[:20]
            compact[f"{key}_truncated"] = True
        else:
            compact[key] = value

    geojson = result.get("geojson") if isinstance(result.get("geojson"), dict) else result
    features = geojson.get("features", []) if isinstance(geojson, dict) else []
    if features:
        compact["feature_properties"] = [
            feature.get("properties", {}) for feature in features[:10] if isinstance(feature, dict)
        ]
    elif isinstance(result.get("feature"), dict):
        compact["feature_properties"] = result["feature"].get("properties", {})
    compact["geometry_available_to_frontend"] = bool(features or result.get("geometry") or result.get("feature"))
    return compact


def _source_class(tool_results: list[tuple[str, dict[str, Any]]], intent: dict[str, Any]) -> str | None:
    value = intent.get("spatial_intent", {}).get("source_class_id")
    if value:
        return value
    for _, result in tool_results:
        features = result.get("geojson", {}).get("features", []) if isinstance(result.get("geojson"), dict) else []
        if features:
            return features[0].get("properties", {}).get("class_id")
    return None


def run_llm_agent(
    query: str,
    *,
    bbox: list[float] | None = None,
    geometry: dict[str, Any] | None = None,
    limit: int = 20,
    provider_name: str | None = None,
    provider: LLMProvider | None = None,
    history: list[dict[str, str]] | None = None,
    tool_executor=execute_tool,
) -> dict[str, Any]:
    started = time.perf_counter()
    provider = provider or get_provider(provider_name)
    if not provider.configured:
        raise ProviderError(f"{provider.provider_name} API key is not configured")

    intent = route_query(query)
    rag = search_knowledge(query, top_k=4)
    instructions = build_instructions(rag["documents"])
    input_items: list[dict[str, Any]] = [
        {"role": item["role"], "content": item["content"]}
        for item in (history or [])[-6:]
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ] + [
        {"role": "user", "content": [{"type": "input_text", "text": build_user_input(query, bbox=bbox, geometry=geometry, limit=limit)}]}
    ]
    traces: list[dict[str, Any]] = []
    executed: list[tuple[str, dict[str, Any]]] = []
    usage: dict[str, Any] = {}
    invalid_retry_used = False
    logger = TraceLogger(query, provider.provider_name, provider.model_name)

    try:
        for round_index in range(_max_rounds() + 1):
            turn = provider.generate(instructions=instructions, input_items=input_items, tools=TOOL_DEFINITIONS)
            if turn.usage:
                usage = _merge_usage(usage, turn.usage)
            if not turn.tool_calls:
                may_answer_without_tool = bool(intent.get("clarification_required")) or bool(intent.get("fallback_type"))
                if intent.get("mode") in {"spatial", "mixed"} and not executed and not may_answer_without_tool:
                    raise AgentGroundingError("Spatial answer returned without a GIS tool call")
                answer = turn.text.strip()
                if not answer:
                    raise AgentGroundingError("Provider returned no final answer")
                geojson = _extract_geojson(executed)
                features = geojson.get("features", [])
                source_class = _source_class(executed, intent)
                latency_ms = (time.perf_counter() - started) * 1000
                logger.payload["parsed_intent"] = intent
                logger.payload["final_answer_sha256"] = __import__("hashlib").sha256(answer.encode("utf-8")).hexdigest()
                logger.finish(success=True, latency_ms=latency_ms, usage=usage)
                clarification_needed = bool(intent.get("clarification_required")) and not executed
                return {
                    "status": "clarification_required" if clarification_needed else "success",
                    "mode": intent.get("mode"),
                    "answer": answer,
                    "results": {
                        "count": len(features),
                        "features": [item.get("properties", {}) for item in features],
                        "geojson": geojson,
                        "distance_context": _extract_distance_context(executed),
                    },
                    "evidence": rag["documents"],
                    "reliability": reliability_context(source_class) if source_class else None,
                    "tool_trace": traces,
                    "clarification_required": clarification_needed,
                    "intent": intent,
                    "llm": {
                        "provider": provider.provider_name,
                        "model": provider.model_name,
                        "configured": True,
                        "enabled": True,
                        "used": True,
                        "mode": "responses_tool_loop",
                        "rounds": round_index + 1,
                        "usage": usage,
                    },
                }

            if round_index >= _max_rounds():
                raise ProviderError("Maximum tool rounds exceeded")

            function_outputs: list[dict[str, Any]] = []
            for call in turn.tool_calls:
                try:
                    validated_args = validate_tool_arguments(call.name, call.arguments)
                except Exception as exc:
                    if invalid_retry_used:
                        raise ProviderError(f"Malformed tool arguments after retry: {call.name}") from exc
                    invalid_retry_used = True
                    error_result = {"status": "error", "error": {"code": "invalid_tool_arguments", "message": str(exc)}}
                    function_outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(error_result, ensure_ascii=False)})
                    traces.append({"tool": call.name, "parameters": call.arguments, "status": "validation_error", "result_summary": str(exc)[:160]})
                    continue

                logger.add_call(call.name, validated_args)
                result = tool_executor(
                    call.name,
                    validated_args,
                    request_bbox=bbox,
                    request_geometry=geometry,
                    request_limit=limit,
                )
                executed.append((call.name, result))
                logger.add_result(call.name, result)
                traces.append({"tool": call.name, "parameters": validated_args, "status": "success", "result_summary": _tool_summary(call.name, result)})
                function_outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(_tool_result_for_model(result), ensure_ascii=False)})
            input_items.extend(turn.output_items)
            input_items.extend(function_outputs)

        raise ProviderError("Maximum tool rounds exceeded")
    except Exception as exc:
        logger.finish(success=False, latency_ms=(time.perf_counter() - started) * 1000, error=type(exc).__name__, usage=usage)
        raise
