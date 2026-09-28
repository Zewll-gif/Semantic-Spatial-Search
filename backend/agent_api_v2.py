# CLEAN PROJECT HEADER
# ไฟล์: agent_api_v2.py
# หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
# Input: คำขอ API, config และ canonical spatial data
# Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
# Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""FastAPI surface for the canonical GeoAI Agent + GIS + RAG flow."""
from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

try:
    from agent_orchestrator import run_agent_query
    from canonical_schema import public_schema, resolve_class_alias
    from gis_tools import ToolError, find_nearby, get_feature_details, get_geojson, search_landcover
    from llm import provider_enabled, provider_status
    from postgis_store import health as postgis_health
    from rag_service import search_knowledge
except ImportError:  # pragma: no cover
    from .agent_orchestrator import run_agent_query
    from .canonical_schema import public_schema, resolve_class_alias
    from .gis_tools import ToolError, find_nearby, get_feature_details, get_geojson, search_landcover
    from .llm import provider_enabled, provider_status
    from .postgis_store import health as postgis_health
    from .rag_service import search_knowledge

try:
    from project_paths import MODEL_METADATA_ROOT
except ImportError:  # pragma: no cover
    from .project_paths import MODEL_METADATA_ROOT

app = FastAPI(title="A7-T GeoAI Agent API", version="2.0.0")


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class AgentQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    bbox: list[float] | None = None
    geometry: dict[str, Any] | None = None
    limit: int = Field(default=20, ge=1, le=100)
    provider: Literal["openai", "deepseek"] | None = None
    history: list[ConversationTurn] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def one_scope(self):
        if self.bbox is not None and self.geometry is not None:
            raise ValueError("Provide bbox or geometry, not both")
        return self


class SpatialSearchRequest(BaseModel):
    class_id: str
    bbox: list[float] | None = None
    geometry: dict[str, Any] | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SpatialNearRequest(BaseModel):
    source_class_id: str
    target_class_id: str
    max_distance_m: float = Field(gt=0, le=100000)
    min_area: float = Field(default=0, ge=0)
    area_unit: str = "sqm"
    limit: int = Field(default=20, ge=1, le=100)


class GeoJSONRequest(BaseModel):
    feature_ids: list[int] = Field(min_length=1, max_length=100)


def _tool_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ToolError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_dict()) from exc


@app.get("/api/schema/classes")
def classes():
    return public_schema()


@app.get("/api/schema/resolve")
def resolve_class(text: str = Query(..., min_length=1)):
    return resolve_class_alias(text)


@app.post("/api/agent/query")
def agent_query(request: AgentQueryRequest):
    if request.provider and os.getenv("DEBUG_AGENT", "0").lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=403, detail="Provider override is available only when DEBUG_AGENT=true")
    return run_agent_query(
        request.query,
        request.bbox,
        request.geometry,
        request.limit,
        request.provider,
        [turn.model_dump() for turn in request.history],
    )


@app.post("/api/spatial/search")
def spatial_search(request: SpatialSearchRequest):
    return _tool_call(search_landcover, request.class_id, request.bbox, request.geometry, request.limit, request.offset)


@app.post("/api/spatial/near")
def spatial_near(request: SpatialNearRequest):
    return _tool_call(find_nearby, source_class_id=request.source_class_id, target_class_id=request.target_class_id, max_distance_m=request.max_distance_m, min_area=request.min_area, area_unit=request.area_unit, limit=request.limit)


@app.get("/api/features/{feature_id}")
def feature_details(feature_id: int):
    return _tool_call(get_feature_details, feature_id)


@app.post("/api/features/geojson")
def features_geojson(request: GeoJSONRequest):
    return _tool_call(get_geojson, request.feature_ids)


@app.get("/api/knowledge/search")
def knowledge_search(q: str = Query(..., min_length=1), category: str | None = None, top_k: int = Query(4, ge=1, le=10)):
    return search_knowledge(q, category, top_k)


@app.get("/api/system/model-info")
def model_info():
    return {
        "operational_model": "A7-T",
        "model_version": "A7_RGBN_REVISED7_TVERSKY",
        "architecture": "Custom U-Net",
        "input": {"sensor": "PlanetScope", "channels": 4, "tensor_order": ["R", "G", "B", "NIR"], "source_bands": [3, 2, 1, 4], "tile_size": [512, 512]},
        "taxonomy": "Revised 7-class",
        "loss": {"name": "Tversky", "alpha": 0.3, "beta": 0.7},
        "pretrained": False,
        "parameter_count": 7763527,
        "validation_reference": "fixed VAL4",
        "test40_has_ground_truth": False,
        "full_aoi_is_prediction": True,
        "llm_provider": {**provider_status(), "spatial_tools_available_without_llm": True},
        "sources": [
            str(MODEL_METADATA_ROOT / "training_config.json"),
            str(MODEL_METADATA_ROOT / "metrics.json"),
            str(MODEL_METADATA_ROOT / "README.txt"),
        ]
    }


@app.get("/api/system/integration-status")
def integration_status():
    database = postgis_health()
    llm = provider_status()
    return {
        "llm": {**llm, "key_configured": llm["configured"],
                "role": "tool_orchestration_only", "sends_database_rows_to_llm": False,
                "max_tool_rounds": min(max(int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "5")), 1), 5)},
        "database": {**database, "mode": "postgis" if database["connected"] else "gpkg_fallback" if not database["configured"] else "postgis_unavailable"},
        "sql_policy": "read_only_parameterized_allowlist",
    }
