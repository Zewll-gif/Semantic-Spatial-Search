"""Strict LLM tool schemas mapped to the existing deterministic GIS functions."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from canonical_schema import class_by_id
    from gis_tools import (
        calculate_distance,
        filter_by_area,
        find_nearby,
        get_evidence,
        get_feature_details,
        get_geojson,
        get_index_stats,
        intersects,
        search_landcover,
    )
except ImportError:  # pragma: no cover
    from ..canonical_schema import class_by_id
    from ..gis_tools import (
        calculate_distance,
        filter_by_area,
        find_nearby,
        get_evidence,
        get_feature_details,
        get_geojson,
        get_index_stats,
        intersects,
        search_landcover,
    )

ClassCode = Literal["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
AreaUnit = Literal["sqm", "rai", "hectare"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchLandcoverArgs(_StrictModel):
    class_id: ClassCode
    limit: int = Field(ge=1, le=100)


class FilterByAreaArgs(_StrictModel):
    feature_ids: list[int] | None
    class_id: ClassCode | None
    min_area: float = Field(ge=0)
    max_area: float | None = Field(default=None, ge=0)
    unit: AreaUnit
    limit: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def validate_source(self):
        if not self.feature_ids and self.class_id is None:
            raise ValueError("feature_ids or class_id is required")
        if self.max_area is not None and self.max_area < self.min_area:
            raise ValueError("max_area must be >= min_area")
        return self


class FindNearbyArgs(_StrictModel):
    source_class_id: ClassCode
    target_class_id: ClassCode
    max_distance_m: float = Field(gt=0, le=100000)
    min_area: float = Field(ge=0)
    area_unit: AreaUnit
    limit: int = Field(ge=1, le=100)


class DistanceArgs(_StrictModel):
    source_feature_id: int = Field(gt=0)
    target_feature_id: int = Field(gt=0)


class IntersectsArgs(_StrictModel):
    source_feature_id: int | None = Field(default=None, gt=0)
    source_class_id: ClassCode | None
    target_feature_id: int | None = Field(default=None, gt=0)
    target_class_id: ClassCode | None
    limit: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def validate_sides(self):
        if self.source_feature_id is None and self.source_class_id is None:
            raise ValueError("source feature or class is required")
        if self.target_feature_id is None and self.target_class_id is None:
            raise ValueError("target feature or class is required")
        return self


class FeatureArgs(_StrictModel):
    feature_id: int = Field(gt=0)


class IndexArgs(_StrictModel):
    feature_id: int | None = Field(default=None, gt=0)
    use_current_geometry: bool

    @model_validator(mode="after")
    def exactly_one_source(self):
        if (self.feature_id is None) == (not self.use_current_geometry):
            raise ValueError("Provide feature_id or set use_current_geometry=true, but not both")
        return self


class GeoJSONArgs(_StrictModel):
    feature_ids: list[int] = Field(min_length=1, max_length=100)


_MODELS: dict[str, type[_StrictModel]] = {
    "search_landcover": SearchLandcoverArgs,
    "filter_by_area": FilterByAreaArgs,
    "find_nearby": FindNearbyArgs,
    "calculate_distance": DistanceArgs,
    "intersects": IntersectsArgs,
    "get_feature_details": FeatureArgs,
    "get_ndvi_stats": IndexArgs,
    "get_ndwi_stats": IndexArgs,
    "get_geojson": GeoJSONArgs,
    "get_evidence": FeatureArgs,
}


def _nullable(kind: str) -> list[str]:
    return [kind, "null"]


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


_CLASS = {"type": "string", "enum": [f"R{i}" for i in range(1, 8)]}
_NULL_CLASS = {"type": _nullable("string"), "enum": [*[f"R{i}" for i in range(1, 8)], None]}
_UNIT = {"type": "string", "enum": ["sqm", "rai", "hectare"]}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {"type": "function", "name": "search_landcover", "description": "ค้นหา polygon จากคลาส A7-T Revised7 ภายในขอบเขตที่กำหนด", "strict": True,
     "parameters": _schema({"class_id": _CLASS, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ["class_id", "limit"])},
    {"type": "function", "name": "filter_by_area", "description": "กรอง polygon ตามพื้นที่ซึ่ง GIS คำนวณไว้", "strict": True,
     "parameters": _schema({"feature_ids": {"type": _nullable("array"), "items": {"type": "integer"}}, "class_id": _NULL_CLASS, "min_area": {"type": "number", "minimum": 0}, "max_area": {"type": _nullable("number"), "minimum": 0}, "unit": _UNIT, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ["feature_ids", "class_id", "min_area", "max_area", "unit", "limit"])},
    {"type": "function", "name": "find_nearby", "description": "ค้นหาพื้นที่คลาสต้นทางที่อยู่ไม่เกินระยะจากคลาสเป้าหมาย", "strict": True,
     "parameters": _schema({"source_class_id": _CLASS, "target_class_id": _CLASS, "max_distance_m": {"type": "number", "exclusiveMinimum": 0, "maximum": 100000}, "min_area": {"type": "number", "minimum": 0}, "area_unit": _UNIT, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ["source_class_id", "target_class_id", "max_distance_m", "min_area", "area_unit", "limit"])},
    {"type": "function", "name": "calculate_distance", "description": "คำนวณระยะทาง GIS ระหว่าง polygon สองรายการ", "strict": True,
     "parameters": _schema({"source_feature_id": {"type": "integer", "minimum": 1}, "target_feature_id": {"type": "integer", "minimum": 1}}, ["source_feature_id", "target_feature_id"])},
    {"type": "function", "name": "intersects", "description": "ตรวจการตัดกันระหว่าง feature หรือคลาส", "strict": True,
     "parameters": _schema({"source_feature_id": {"type": _nullable("integer"), "minimum": 1}, "source_class_id": _NULL_CLASS, "target_feature_id": {"type": _nullable("integer"), "minimum": 1}, "target_class_id": _NULL_CLASS, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ["source_feature_id", "source_class_id", "target_feature_id", "target_class_id", "limit"])},
    {"type": "function", "name": "get_feature_details", "description": "อ่านรายละเอียดและ geometry ของ polygon A7-T", "strict": True, "parameters": _schema({"feature_id": {"type": "integer", "minimum": 1}}, ["feature_id"])},
    {"type": "function", "name": "get_ndvi_stats", "description": "คำนวณสถิติ NDVI ด้วย raster/GIS สำหรับ feature หรือ ROI ปัจจุบัน", "strict": True, "parameters": _schema({"feature_id": {"type": _nullable("integer"), "minimum": 1}, "use_current_geometry": {"type": "boolean"}}, ["feature_id", "use_current_geometry"])},
    {"type": "function", "name": "get_ndwi_stats", "description": "คำนวณสถิติ NDWI ด้วย raster/GIS สำหรับ feature หรือ ROI ปัจจุบัน", "strict": True, "parameters": _schema({"feature_id": {"type": _nullable("integer"), "minimum": 1}, "use_current_geometry": {"type": "boolean"}}, ["feature_id", "use_current_geometry"])},
    {"type": "function", "name": "get_geojson", "description": "ส่งออก geometry ของผลลัพธ์ที่ระบุเป็น GeoJSON", "strict": True, "parameters": _schema({"feature_ids": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 100}}, ["feature_ids"])},
    {"type": "function", "name": "get_evidence", "description": "อ่านหลักฐาน spatial/spectral ของ polygon ที่มีอยู่จริง", "strict": True, "parameters": _schema({"feature_id": {"type": "integer", "minimum": 1}}, ["feature_id"])},
]


def validate_tool_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name not in _MODELS:
        raise ValueError(f"Unknown tool: {name}")
    validated = _MODELS[name].model_validate(arguments)
    data = validated.model_dump()
    for key in ("class_id", "source_class_id", "target_class_id"):
        value = data.get(key)
        if value is not None and class_by_id(value) is None:
            raise ValueError(f"Unknown class code: {value}")
    return data


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    request_bbox: list[float] | None = None,
    request_geometry: dict[str, Any] | None = None,
    request_limit: int = 20,
) -> dict[str, Any]:
    args = dict(arguments)
    if name == "search_landcover":
        args["limit"] = min(int(args.get("limit") or request_limit), int(request_limit), 100)
    elif "limit" in args:
        args["limit"] = min(int(args.get("limit") or request_limit), int(request_limit), 100)
    data = validate_tool_arguments(name, args)

    if name == "search_landcover":
        return search_landcover(data["class_id"], request_bbox, request_geometry, data["limit"])
    if name == "filter_by_area":
        result = filter_by_area(**data)
        if result.get("filtered_ids"):
            result["geojson"] = get_geojson(result["filtered_ids"])
        return result
    if name == "find_nearby":
        return find_nearby(**data)
    if name == "calculate_distance":
        return calculate_distance(**data)
    if name == "intersects":
        return intersects(**data)
    if name == "get_feature_details":
        return get_feature_details(**data)
    if name == "get_ndvi_stats":
        geometry = request_geometry if data.pop("use_current_geometry") else None
        if geometry is None and request_bbox is not None and data["feature_id"] is None:
            west, south, east, north = request_bbox
            geometry = {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}
        if geometry is None and data["feature_id"] is None:
            raise ValueError("Current ROI geometry is required")
        return get_index_stats("ndvi", geometry=geometry, **data)
    if name == "get_ndwi_stats":
        geometry = request_geometry if data.pop("use_current_geometry") else None
        if geometry is None and request_bbox is not None and data["feature_id"] is None:
            west, south, east, north = request_bbox
            geometry = {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}
        if geometry is None and data["feature_id"] is None:
            raise ValueError("Current ROI geometry is required")
        return get_index_stats("ndwi", geometry=geometry, **data)
    if name == "get_geojson":
        return get_geojson(**data)
    if name == "get_evidence":
        return get_evidence(**data)
    raise ValueError(f"Unknown tool: {name}")
