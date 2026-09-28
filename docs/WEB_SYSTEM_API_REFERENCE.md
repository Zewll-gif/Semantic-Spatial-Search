# GeoAI Explorer — API Reference

Base URL: `http://127.0.0.1:8795` (live) or `http://127.0.0.1:8802` (staging).  
Authentication: none. The current safety boundary is localhost binding.  
Format: JSON unless noted; geometries are GeoJSON EPSG:4326 unless an endpoint explicitly reports otherwise.

## Canonical product endpoints

| Method | Path | Purpose | Principal inputs / limits |
|---|---|---|---|
| POST | `/api/agent/query` | Unified deterministic/optional-LLM query | `query` 1–2000 chars; bbox XOR geometry; limit 1–100 |
| POST | `/api/spatial/search` | Class polygon search | class ID, bbox/geometry, limit 1–100, offset |
| POST | `/api/spatial/near` | Source class near target class | distance >0 and ≤100,000 m; min area; limit 1–100 |
| GET | `/api/features/{feature_id}` | One polygon's attributes/centroid | integer ID |
| POST | `/api/features/geojson` | Geometry for selected IDs | 1–100 feature IDs |
| GET | `/api/schema/classes` | Canonical public taxonomy | none |
| GET | `/api/schema/resolve` | Resolve Thai/English alias | `text` |
| GET | `/api/knowledge/search` | Local lexical RAG retrieval | query, optional category, top-k 1–10 |
| GET | `/api/system/model-info` | Model/provenance/reliability facts | none |
| GET | `/api/system/integration-status` | Actual LLM/database runtime status | none |

Example unified query:

```json
{
  "query": "พื้นที่เกษตรใกล้น้ำ 300 เมตร",
  "limit": 20
}
```

The response includes interpreted intent, result counts/items, map actions, evidence/trace, and limitations. Spatial execution is deterministic; optional LLM output is only a validated intent object.

## Drawn AOI and external satellite

| Method | Path | Purpose | Notes |
|---|---|---|---|
| POST | `/api/aoi/coverage` | Project/external/partial coverage decision | Polygon/MultiPolygon |
| POST | `/api/aoi/analyze` | A7-T, NDVI, NDWI, COP30 summary | mode `auto` or `project_only` |
| POST | `/api/aoi/preview` | Drawn-AOI visualization preview | categorical rendering preserved |
| POST | `/api/aoi/external/search` | Discover/rank Sentinel-2 scenes | optional acquisition date |
| POST | `/api/aoi/external/analyze` | Extract real external AOI bands/statistics | synchronous on cache miss |
| POST | `/api/aoi/external/preview` | RGB/NDVI/NDWI external preview | layer allowlist only |
| POST | `/api/aoi/corrections` | Append a human-correction candidate | does not alter A7-T |
| GET | `/api/aoi/corrections` | List correction candidates | current SQLite store |

Drawn-AOI request:

```json
{
  "geometry": {"type":"Polygon","coordinates":[...]},
  "analysis_mode": "auto",
  "acquisition_date": null
}
```

External preview request uses `layer` = `rgb`, `ndvi`, or `ndwi`.

## Map and project assets

| Method | Path | Output / cache |
|---|---|---|
| GET | `/api/aoi` | Full-AOI metadata and bounds |
| GET | `/api/map/a7t/{z}/{x}/{y}.png` | categorical PNG tile; 1-day public cache |
| GET | `/api/map/identify` | class at lon/lat |
| GET | `/api/roi/preview` | bbox-specific classification PNG; no-store |
| POST | `/api/roi/insight` | bbox class counts/areas |
| GET | `/api/spectral/{name}` | approved spectral asset |
| GET | `/analysis-assets/{name}` | approved analysis visualization |
| GET | `/assets/{tile_id}/{kind}` | tile asset; non-RGB immutable cache |
| GET | `/api/splits` | split metadata |
| GET | `/api/tiles` | tile catalogue |
| GET | `/api/tiles/{tile_id}` | tile details |

## Legacy V1 search, tools, and analysis

These routes remain operational for compatibility, but the current product search UI primarily uses `/api/agent/query` and V2 spatial endpoints.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/search` | legacy tile ranking |
| POST | `/api/agent` | legacy agent orchestration |
| POST | `/api/tools/area` | raster area calculation |
| POST | `/api/tools/spectral` | spectral statistics |
| GET | `/api/tools/segmentation/{tile_id}` | segmentation evidence |
| GET | `/api/tools/rag` | legacy evidence retrieval |
| GET | `/api/tools/chart` | chart specification |
| GET | `/api/tools/external-context` | unconfigured external-context contract |
| POST | `/api/tools/spectral-consistency` | spectral consistency evidence |
| POST | `/api/tools/external-reference` | external reference contract |
| GET | `/api/evidence/profiles` | evidence profiles |
| GET | `/api/evidence/audit` | evidence audit |
| POST | `/api/evidence/lulc-comparison` | LULC comparison evidence |
| POST | `/api/analysis` | create bounded legacy analysis |
| GET | `/api/analysis` | in-memory analysis list |
| GET | `/api/export/{analysis_id}/{fmt}` | create approved export format |
| GET | `/api/download/{analysis_id}/{fmt}` | download generated export |
| GET | `/api/agent/evaluation` | evaluation metadata |
| GET | `/api/class-schema` | legacy class schema |

Legacy analysis formats are GeoJSON, GPKG, zipped Shapefile, CSV, and GeoTIFF. Analysis state is held in memory; IDs are invalid after a restart even if some files remain on disk.

## Foundation GeoAI endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/geoai/health` | foundation repository health |
| GET | `/api/geoai/classes` | foundation class list |
| POST | `/api/geoai/search` | class/area polygon search |
| POST | `/api/geoai/area` | area for geometry or feature |
| POST | `/api/geoai/distance` | projected distance |
| POST | `/api/geoai/near` | class-near-class search |
| POST | `/api/geoai/intersect` | spatial intersection |
| POST | `/api/geoai/ndvi-stats` | NDVI masked statistics |
| POST | `/api/geoai/ndwi-stats` | NDWI masked statistics |
| POST | `/api/geoai/evidence` | feature evidence package |

## Status endpoints

| Method | Path | Interpretation |
|---|---|---|
| GET | `/api/health` | legacy application availability; `agent_enabled` means route capability, not active OpenAI |
| GET | `/api/system/integration-status` | authoritative active OpenAI and database configuration |
| GET | `/api/system/model-info` | authoritative model and validation context |

At audit time, integration status reported `gpkg_fallback`, PostGIS disconnected because the DSN was missing, and OpenAI disabled because the key/flag were absent.

## Validation and error model

- Pydantic rejects invalid types/ranges with HTTP 422.
- GIS tool errors use structured HTTP errors and request IDs where implemented.
- Agent query accepts either bbox or geometry, never both.
- External layer names and AOI analysis modes are allowlisted.
- AOI geometry has additional topology, vertex, coordinate, and 250 km² checks in the service layer.
- There is no authentication, authorization, global rate limit, or public API quota.

## Complete OpenAPI operation inventory (59)

```text
GET  /analysis-assets/{name}
POST /api/agent
GET  /api/agent/evaluation
POST /api/agent/query
GET,POST /api/analysis
GET  /api/aoi
POST /api/aoi/analyze
GET,POST /api/aoi/corrections
POST /api/aoi/coverage
POST /api/aoi/external/analyze
POST /api/aoi/external/preview
POST /api/aoi/external/search
POST /api/aoi/preview
GET  /api/class-schema
GET  /api/download/{analysis_id}/{fmt}
GET  /api/evidence/audit
POST /api/evidence/lulc-comparison
GET  /api/evidence/profiles
GET  /api/export/{analysis_id}/{fmt}
GET  /api/features/{feature_id}
POST /api/features/geojson
POST /api/geoai/area
GET  /api/geoai/classes
POST /api/geoai/distance
POST /api/geoai/evidence
GET  /api/geoai/health
POST /api/geoai/intersect
POST /api/geoai/ndvi-stats
POST /api/geoai/ndwi-stats
POST /api/geoai/near
POST /api/geoai/search
GET  /api/health
GET  /api/knowledge/search
GET  /api/map/a7t/{z}/{x}/{y}.png
GET  /api/map/identify
POST /api/roi/insight
GET  /api/roi/preview
GET  /api/schema/classes
GET  /api/schema/resolve
GET  /api/search
POST /api/spatial/near
POST /api/spatial/search
GET  /api/spectral/{name}
GET  /api/splits
GET  /api/system/integration-status
GET  /api/system/model-info
GET  /api/tiles
GET  /api/tiles/{tile_id}
POST /api/tools/area
GET  /api/tools/chart
GET  /api/tools/external-context
POST /api/tools/external-reference
GET  /api/tools/rag
GET  /api/tools/segmentation/{tile_id}
POST /api/tools/spectral
POST /api/tools/spectral-consistency
GET  /assets/{tile_id}/{kind}
```
