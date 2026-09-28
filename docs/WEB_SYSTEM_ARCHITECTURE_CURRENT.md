# GeoAI Explorer — Current Architecture

Status: observed 2026-09-21. “Available” and “active” are separated deliberately.

## System context

```text
Researcher / advisor
        |
        v
Single-page browser UI
  Leaflet 2D map | MapLibre 3D tour | GSAP narrative
        |
        | same-origin REST / GeoJSON / PNG
        v
FastAPI + Uvicorn (localhost, one Python process per deployment)
  +--------------------+----------------------+--------------------+
  | Agent/GIS/RAG      | Raster/AOI services  | Static web/assets  |
  +--------------------+----------------------+--------------------+
       |          |              |                      |
       v          v              v                      v
  GeoPackage   local JSON    A7-T/RGB/indices/DEM   frontend files
  [ACTIVE]     knowledge     + CDSE Sentinel-2
       |
       +---- PostGIS adapter [AVAILABLE, NOT CONFIGURED]

Optional OpenAI structured-intent planner [AVAILABLE, DISABLED]
Human correction candidate store: SQLite [ACTIVE]
```

## Deployment instances

| Instance | URL | PID | Python | Launch command |
|---|---|---:|---|---|
| Live | `127.0.0.1:8795` | 4744 | `...\envs\geoai\python.exe` | `python -m uvicorn main:app --host 127.0.0.1 --port 8795` |
| Staging | `127.0.0.1:8802` | 36764 | same | `python -m uvicorn main:app --host 127.0.0.1 --port 8802` |

The temporary launcher scripts activate the `geoai` environment. Process cwd is inherited and was not directly observable through the inspected Windows process interface.

## Backend composition

`backend/main.py` creates the public FastAPI application and extends its router with:

1. `geoai_api.py`: legacy/foundation GIS endpoints.
2. `agent_api_v2.py`: canonical schema, polygon search, near search, feature, RAG, model, and integration endpoints.
3. Main application routes: AOI metadata/preview, Drawn AOI, external Sentinel-2, corrections, tile/search/agent legacy tools, evidence, analysis/export, class schema, categorical map tiles, and identify.
4. Static mounts: `/aoi` for project imagery/assets and `/` for the frontend.

The mount of `/` is last, so registered API routes remain reachable.

## Frontend composition

`frontend/index.html` is a single document containing four major sections:

1. `#storyTop` — research hero.
2. `#discover` — landscape/comparison context.
3. `#guidedTour` — MapLibre/DEM-inspired guided class tour.
4. `#explore` — operational Leaflet search and analysis workspace.

Runtime scripts are loaded without bundling: `class-schema.js`, `app.js`, `roi-preview.js`, `drawn-aoi.js`, `agent.js`, `analysis.js`, `evidence.js`, `workspace.js`, `product.js`, `experience.js`, `cinematic.js`, `landscape-tour-v2.js`, and `hero-reveal.js`.

## Primary user flows

### Semantic search

```text
Thai/English query
 -> POST /api/agent/query
 -> deterministic intent router (current)
 -> canonical class resolution
 -> GeoPackage spatial query (current)
 -> GeoJSON result polygons + counts + trace
 -> satellite map + class-coloured result layer
 -> numbered markers, sidebar cards, selected popup
```

Optional path: OpenAI extracts structured intent, its JSON is validated, then the same deterministic GIS tools execute. The model never receives or executes SQL.

### Drawn AOI

```text
Rectangle / polygon / freehand GeoJSON (4326)
 -> validation + projected transform (32647)
 -> coverage decision
 -> inside project: A7-T + NDVI + NDWI + COP30 mask/statistics
 -> partial/outside: offer CDSE Sentinel-2 search/extraction
 -> preview + class/spectral summary + deterministic trace
```

### External AOI

```text
AOI/date
 -> CDSE STAC scene discovery/ranking
 -> S3 JP2 range reads via GDAL /vsis3/
 -> B02/B03/B04/B08/SCL alignment and cloud mask
 -> RGB/NDVI/NDWI products
 -> disk cache keyed by geometry/bands/schema
```

### Human correction

```text
selected geometry + original/corrected class + note
 -> POST /api/aoi/corrections
 -> append candidate to SQLite
```

This does not rewrite A7-T, the taxonomy, or the source polygon database.

## Layer order

1. Satellite/street/terrain basemap.
2. Soft-edge project RGB overlay.
3. A7-T categorical, NDVI, or NDWI project layer.
4. Search/drawn-AOI result polygons and selection geometry.
5. Numbered markers, active popup, tool controls, side panels.

## Coordinate systems

- Browser and GeoJSON exchange: EPSG:4326.
- Project analysis, polygons, areas, and distances: EPSG:32647.
- Raster services transform requested web bounds into source CRS.
- PostGIS, when enabled, stores MultiPolygon geometry in SRID 32647 and transforms output to 4326.

## State and persistence

| State | Persistence |
|---|---|
| A7-T/RGB/NDVI/NDWI/DEM | canonical files |
| Search polygons | canonical GeoPackage; optional PostGIS |
| Human corrections | SQLite |
| Sentinel-2 band cache | local disk |
| Legacy analysis jobs | Python in-memory dictionary plus generated export files |
| Browser view/tool state | page memory; some UI defaults |

The in-memory analysis registry is lost on restart and cannot safely coordinate multiple workers.

## Active versus available integrations

| Integration | Code present | Current runtime |
|---|---:|---:|
| GeoPackage | yes | active |
| PostGIS | yes | inactive; DSN missing |
| Deterministic intent router | yes | active |
| OpenAI planner | yes | inactive; key/flag absent |
| Local lexical RAG | yes | active |
| CDSE STAC/S3 | yes | configured by environment variable names; cached data present |
| External POI provider | placeholder contract | not configured |

## Architectural constraints

- One synchronous Uvicorn worker is appropriate only for controlled use.
- CPU-heavy raster masks and uncached JP2 extraction can block the event loop.
- The source tree contains overlapping V1/V2 contracts and multiple CSS generations.
- Static and analytical assets share one process; no CDN or tile server is used.
- External web fonts/basemaps and CDSE mean the complete experience depends on network availability.
