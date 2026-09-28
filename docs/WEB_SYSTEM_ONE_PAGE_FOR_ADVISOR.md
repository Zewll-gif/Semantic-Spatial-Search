# GeoAI Explorer — One-Page Advisor Brief

## Purpose

GeoAI Explorer is a controlled local research web system for exploring PlanetScope land-cover predictions through Thai/English semantic questions, map interaction, and user-drawn AOIs. It combines the A7-T Full-AOI prediction with NDVI, NDWI, COP30 DSM, and optional real Sentinel-2 L2A extraction.

## Current architecture

```text
Browser: Leaflet + MapLibre + vanilla JS
        ↓ same-origin API
FastAPI/Uvicorn on localhost
        ↓
GeoPackage (active) | A7-T/RGB/NDVI/NDWI/COP30 | SQLite corrections
        ↓ optional
PostGIS (implemented, off) | OpenAI intent planner (implemented, off)
CDSE STAC/S3 Sentinel-2 (configured workflow)
```

Live: `http://127.0.0.1:8795/#explore`  
Staging: `http://127.0.0.1:8802/#explore`

## Data truth

- Operational model: `A7_RGBN_REVISED7_TVERSKY`, custom U-Net, PlanetScope R/G/B/NIR.
- Taxonomy: R1 Built-up, R2 Agriculture, R3 Tree, R4 Water, R5 Grassland, R6 Bare Ground, R7 Uncertain/Cloud.
- Project analysis CRS: EPSG:32647; web GeoJSON: EPSG:4326.
- Full AOI: 24.906 × 27.924 km grid at 3 m, WGS84 bbox 98.890239/18.665300/99.126760/18.917684.
- Search database: clean GeoPackage, 155,199 polygons. PostGIS is not active now.
- Full-AOI output is model prediction, not Ground Truth. Fixed VAL4 metrics are class-level references, not polygon confidence.

## How the agent works

The active agent is deterministic: it resolves class/relation/area intent, validates parameters, executes explicit GIS tools, retrieves curated local evidence, and returns results with a trace. OpenAI is currently disabled; if enabled later it may only return validated structured intent and never sees database rows or executes SQL.

## Key user functions

- Semantic class and proximity search with satellite context and canonical class colors.
- Numbered result markers, right-side result list, selected-feature popup, and map fly-to.
- Rectangle/polygon/freehand AOI analysis: class percentage/area, NDVI, NDWI, COP30, trace, and reliability context.
- External/partial AOI: CDSE Sentinel-2 scene search and real RGB/NDVI/NDWI extraction.
- Human correction candidates stored separately without changing A7-T.

## Audit evidence

- Live/publish code/config parity: 69/69 SHA-256 matches.
- Root HTML: byte-identical live/staging.
- Tests: 43/43 current unit tests; 19/19 Drawn-AOI/external tests.
- Browser: live and staging rendered; no observed console errors/warnings.
- Prior real Sentinel-2 evidence: non-mocked extraction, 100% scene coverage, 99.2% valid pixels, RGB/NDVI/NDWI HTTP 200.

## Readiness

**Ready for:** controlled single-user thesis/research demonstration.

**Not ready for:** public Internet or concurrent multi-user production. Missing controls include authentication/authorization, rate limits, async job queue, persistent job state, cache eviction, security headers, and load testing.

Required limitation: `uncached Sentinel-2 JP2 extraction currently runs synchronously and may block the application during processing; current deployment is intended for controlled single-user research/demo use.`

## Safe presentation sentence

“GeoAI Explorer converts natural-language and drawn-area intent into validated, traceable GIS operations over the latest A7-T Full-AOI prediction and supporting spectral/elevation data; optional LLM planning and PostGIS are implemented but not active in the audited runtime.”
