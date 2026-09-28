# CLEAN PROJECT HEADER
# ไฟล์: agent_orchestrator.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Grounded agent orchestration: intent -> canonical classes -> GIS -> RAG."""
from __future__ import annotations

from typing import Any

try:
    from gis_tools import ToolError, filter_by_area, find_nearby, get_geojson, search_landcover
    from intent_router import route_query
    from llm import provider_enabled, provider_status, run_llm_agent
    from llm_spatial_planner import enabled as llm_enabled, plan_spatial_query
    from postgis_store import configured as postgis_configured
    from rag_service import grounded_knowledge_answer, search_knowledge
    from reliability import reliability_context
except ImportError:  # pragma: no cover
    from .gis_tools import ToolError, filter_by_area, find_nearby, get_geojson, search_landcover
    from .intent_router import route_query
    from .llm import provider_enabled, provider_status, run_llm_agent
    from .llm_spatial_planner import enabled as llm_enabled, plan_spatial_query
    from .postgis_store import configured as postgis_configured
    from .rag_service import grounded_knowledge_answer, search_knowledge
    from .reliability import reliability_context


def _fallback(status: str, answer: str, intent: dict[str, Any], fallback_type: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "mode": intent.get("mode"),
        "answer": answer,
        "results": {"count": 0, "features": [], "geojson": {"type": "FeatureCollection", "features": []}},
        "evidence": [],
        "reliability": None,
        "tool_trace": [],
        "clarification_required": status == "clarification_required",
        "fallback_type": fallback_type,
        "intent": intent,
    }


def _run_deterministic_query(
    query: str,
    bbox: list[float] | None = None,
    geometry: dict[str, Any] | None = None,
    limit: int = 20,
    *,
    provider_name: str | None = None,
    allow_legacy_llm: bool = True,
) -> dict[str, Any]:
    intent = route_query(query)
    llm_state = provider_status(provider_name)
    llm_state.update({
        "used": False,
        "mode": "deterministic_fallback",
        "gis_backend": "postgis" if postgis_configured() else "gpkg_fallback",
        "note": "LLM parses spatial intent only; all GIS facts are computed locally.",
    })
    # Compatibility path retained for existing tests and older OpenAI-only
    # deployments. The new provider loop runs before this path. DeepSeek does
    # not enter it because llm_spatial_planner.enabled() requires OPENAI_API_KEY.
    if allow_legacy_llm and llm_enabled() and intent.get("mode") in {"spatial", "mixed"} and intent.get("fallback_type") != "unsupported_class":
        try:
            plan = plan_spatial_query(query)
            intent["spatial_intent"].update({
                "source_class_id": plan["source_class_id"],
                "target_class_id": plan["target_class_id"],
                "relation": None if plan["relation"] == "none" else plan["relation"],
                "distance_m": plan["distance_m"],
                "area_min": plan["area_min"],
                "area_unit": plan["area_unit"],
            })
            intent["clarification_required"] = plan["clarification_required"]
            intent["clarification_question"] = plan["clarification_question"]
            intent["planner"] = "legacy_openai_structured_intent"
            llm_state.update(used=True, mode="legacy_structured_intent")
        except Exception as exc:
            llm_state["fallback_reason"] = type(exc).__name__
    if intent.get("clarification_required"):
        result = _fallback("clarification_required", intent.get("clarification_question") or "ต้องการข้อมูลเพิ่มเติม", intent, intent.get("fallback_type"))
        result["llm"] = llm_state
        return result

    rag = search_knowledge(query, top_k=4)
    if intent["mode"] == "knowledge":
        answer = grounded_knowledge_answer(query, rag["documents"])
        return {
            "status": "success",
            "mode": "knowledge",
            "answer": answer,
            "results": None,
            "evidence": rag["documents"],
            "reliability": None,
            "tool_trace": [{"tool": "retrieve_knowledge", "status": "success", "result_summary": f'{rag["count"]} documents'}],
            "clarification_required": False,
            "intent": intent,
            "llm": llm_state,
        }

    spatial = intent["spatial_intent"]
    source = spatial["source_class_id"]
    target = spatial.get("target_class_id")
    area_min = spatial.get("area_min") or 0.0
    area_unit = spatial.get("area_unit") or "sqm"
    trace: list[dict[str, Any]] = []
    try:
        if spatial.get("relation") == "near":
            result = find_nearby(source_class_id=source, target_class_id=target, max_distance_m=spatial["distance_m"], min_area=area_min, area_unit=area_unit, limit=limit)
            trace.append({"tool": "find_nearby", "parameters": {"source_class_id": source, "target_class_id": target, "max_distance_m": spatial["distance_m"], "min_area": area_min, "area_unit": area_unit}, "status": "success", "result_summary": f'{result["count"]} features'})
            geojson = result["geojson"]
        else:
            result = search_landcover(source, bbox=bbox, geometry=geometry, limit=max(limit, 100 if area_min else limit))
            trace.append({"tool": "search_landcover", "parameters": {"class_id": source, "bbox_supplied": bbox is not None, "geometry_supplied": geometry is not None}, "status": "success", "result_summary": f'{result["count"]} features'})
            ids = result["feature_ids"]
            if area_min:
                filtered = filter_by_area(feature_ids=ids, min_area=area_min, max_area=spatial.get("area_max"), unit=area_unit, limit=limit)
                ids = filtered["filtered_ids"]
                trace.append({"tool": "filter_by_area", "parameters": {"min_area": area_min, "unit": area_unit}, "status": "success", "result_summary": f'{filtered["count"]} features'})
                geojson = get_geojson(ids) if ids else {"type": "FeatureCollection", "features": []}
            else:
                geojson = result["geojson"]
            result = {"count": len(geojson["features"]), "geojson": geojson,
                      "total_matches": result.get("total_matches") if not area_min else None,
                      "display_limit": limit}
    except ToolError as exc:
        fallback = "no_result" if exc.code in {"no_result", "NO_RESULTS"} else "tool_error"
        output = _fallback(fallback, "ไม่พบพื้นที่ที่ตรงกับเงื่อนไขที่กำหนด" if fallback == "no_result" else "ไม่สามารถประมวลผล GIS tool ได้", intent, fallback)
        output["error"] = exc.as_dict()["error"]
        output["tool_trace"] = trace + [{"tool": "GIS", "status": "error", "result_summary": exc.code}]
        output["llm"] = llm_state
        return output

    features = result["geojson"]["features"]
    if not features:
        output = _fallback("no_result", "ไม่พบพื้นที่ที่ตรงกับเงื่อนไขที่กำหนด", intent, "no_result")
        output["tool_trace"] = trace
        output["llm"] = llm_state
        return output

    reliability = reliability_context(source)
    total_matches = result.get("total_matches")
    answer = (f"พบ {total_matches:,} พื้นที่ {source}; แสดงตัวอย่าง {len(features)} พื้นที่ที่มีขนาดใหญ่สุด" if total_matches is not None
              else f"แสดง {len(features)} พื้นที่ {source} ที่ตรงกับเงื่อนไข (อาจมีผลเพิ่มเติม); ค่าพื้นที่และระยะคำนวณด้วย GIS ใน EPSG:32647")
    evidence = rag["documents"] if intent["mode"] == "mixed" else []
    if intent["mode"] == "mixed":
        answer += " ผลลัพธ์มาจาก A7-T prediction และไม่ใช่ polygon confidence หรือ Ground Truth เฉพาะพื้นที่"
    return {
        "status": "success",
        "mode": intent["mode"],
        "answer": answer,
        "results": {"count": len(features), "total_matches": total_matches,
                    "returned_features": len(features), "display_limit": limit,
                    "truncated": total_matches > len(features) if total_matches is not None else None,
                    "features": [f["properties"] for f in features], "geojson": result["geojson"],
                    "distance_context": result.get("distance_context")},
        "evidence": evidence,
        "reliability": reliability,
        "tool_trace": trace,
        "clarification_required": False,
        "intent": intent,
        "llm": llm_state,
    }


def run_agent_query(
    query: str,
    bbox: list[float] | None = None,
    geometry: dict[str, Any] | None = None,
    limit: int = 20,
    provider_override: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Run the selected provider, then fail safely to the deterministic router."""
    if provider_enabled(provider_override):
        try:
            return run_llm_agent(
                query,
                bbox=bbox,
                geometry=geometry,
                limit=limit,
                provider_name=provider_override,
                history=history,
            )
        except Exception as exc:
            result = _run_deterministic_query(
                query,
                bbox,
                geometry,
                limit,
                provider_name=provider_override,
                allow_legacy_llm=False,
            )
            result["llm"].update({
                "used": False,
                "mode": "deterministic_fallback",
                "fallback_reason": type(exc).__name__,
                "fallback_message": "ผู้ให้บริการ LLM ไม่พร้อมใช้งาน ระบบจึงใช้ตัววิเคราะห์แบบกำหนดกฎเดิม",
            })
            return result
    # Preserve the documented OpenAI-only compatibility planner for callers
    # that do not explicitly select a provider. Explicit provider failures and
    # AGENT_LLM_ENABLED=0 still use the deterministic path above/inside
    # _run_deterministic_query without making a paid provider call.
    return _run_deterministic_query(
        query,
        bbox,
        geometry,
        limit,
        allow_legacy_llm=provider_override is None,
    )
