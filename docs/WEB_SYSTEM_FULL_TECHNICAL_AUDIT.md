# GeoAI Explorer — Full Technical Audit

Audit date: 2026-09-21 (Asia/Bangkok)  
Scope: current live deployment, publish/staging deployment, source code, local data stores, APIs, and browser rendering.  
Method: read-only inspection. No service restart, deployment, database write, raster modification, paid LLM call, or uncached Sentinel-2 extraction was performed.

## Executive conclusion

GeoAI Explorer is a functional, single-user research/demo web application. It is a static vanilla-JavaScript frontend served by a FastAPI process and backed by canonical A7-T rasters, spectral rasters, a clean polygon GeoPackage, a small SQLite correction store, and optional integrations for PostGIS, OpenAI structured-intent extraction, and Copernicus Data Space Ecosystem (CDSE). The current live runtime does **not** use PostGIS and does **not** use OpenAI: it uses the GeoPackage fallback and deterministic intent routing. CDSE credentials are present by variable name and prior deployment evidence records a real, non-mocked Sentinel-2 extraction.

The application is ready for controlled thesis demonstration, but not for public or multi-user production without authentication, authorization, rate limiting, asynchronous job execution, cache governance, persistent analysis state, security headers, and load/concurrency work.

## Audited systems

| Role | Location / URL | Runtime evidence |
|---|---|---|
| Live source/data | `D:\499_Thesis_Final\02_WEB_SYSTEM` | HTTP 200, PID 4744 |
| Publish/staging source | `D:\499_2\499_Thesis_Final_PUBLISH\02_WEB_SYSTEM` | HTTP 200, PID 36764 |
| Live UI | `http://127.0.0.1:8795/#explore` | visually rendered; no console errors/warnings observed |
| Staging UI | `http://127.0.0.1:8802/#explore` | visually rendered; no console errors/warnings observed |

Both Python processes use `C:\Users\Admin\anaconda3\envs\geoai\python.exe` and were launched as `python -m uvicorn main:app --host 127.0.0.1 --port <port>`. Their temporary launch scripts activate the `geoai` Conda environment and UTF-8 mode. Windows process inspection does not expose the inherited working directory; the expected backend working directories are inferred from successful `main:app` loading, static content, and deployment evidence, not claimed as directly observed.

The live and staging root HTML responses are byte-identical (25,594 bytes; SHA-256 `802BF8ACA92816734686DC2E7E32C0D623CCC9F90BEF59E42B633F178555195D`). All 69 compared backend/frontend code and configuration files in publish and live have matching SHA-256 hashes.

## Current runtime truth

- `/api/health`: model `A7_RGBN_REVISED7_TVERSKY`, 323 Full-AOI tiles, 40 TEST40 tiles, Full AOI available.
- `/api/system/integration-status`: OpenAI key not configured, LLM planner disabled; PostGIS DSN not configured, database mode `gpkg_fallback`.
- The older health field `agent_enabled: true` means the agent route exists, not that an OpenAI model is active. This field is semantically misleading and should be corrected in a later code change.
- Current API surface: 59 OpenAPI operations.
- Current correction database contains 0 correction rows.
- No secrets were printed or copied during the audit. Only environment variable names were inspected.

## Architecture and data flow

```text
Browser (Leaflet + MapLibre + GSAP, vanilla JS)
       |
       | same-origin HTTP/JSON/PNG
       v
FastAPI / Uvicorn (single local process)
  |-- static frontend and AOI assets
  |-- deterministic agent + local lexical RAG
  |-- optional OpenAI structured-intent planner [OFF]
  |-- spatial repository
  |     |-- PostGIS [OFF: DSN missing]
  |     `-- GeoPackage + GeoPandas/Shapely [ACTIVE]
  |-- A7-T / RGB / NDVI / NDWI / COP30 rasters
  |-- SQLite human-correction candidates
  `-- CDSE STAC + S3 Sentinel-2 extraction and disk cache
```

Detailed architecture is in [WEB_SYSTEM_ARCHITECTURE_CURRENT.md](WEB_SYSTEM_ARCHITECTURE_CURRENT.md).

## Canonical analytical data

### Spatial extent

Full AOI WGS84 bounding box:

- west `98.89023907363709`
- south `18.66529982248273`
- east `99.12675969138141`
- north `18.9176840206757`

The analytical CRS is EPSG:32647. Web display/output geometry is EPSG:4326.

### Raster inventory

| Dataset | Shape / bands | Type / NoData | Resolution | CRS | Bounds (EPSG:32647) |
|---|---|---|---|---|---|
| PlanetScope RGBN | 8302 × 9308 × 4 | uint16 / 0 | 3 m | 32647 | 488442, 2063799, 513348, 2091723 |
| A7-T Full AOI | 8302 × 9308 × 1 | uint8 / 0 | 3 m | 32647 | same |
| NDVI | 8302 × 9308 × 1 | float32 / -9999 | 3 m | 32647 | same |
| NDWI | 8302 × 9308 × 1 | float32 / -9999 | 3 m | 32647 | same |
| COP30 DSM | 831 × 931 × 1 | float32 / -9999 | 30 m | 32647 | 488442, 2063793, 513372, 2091723 |

PlanetScope source bands are B, G, R, NIR; display RGB uses bands 3, 2, 1. A7-T stores 0=NoData and 1–7=R1–R7. The COP30 file is a digital surface model (DSM), not a bare-earth DTM.

### Canonical class palette

| ID | Canonical class | Color |
|---|---|---|
| R1 | Built-up / Impervious | `#E53935` |
| R2 | Agricultural Land / Cropland | `#FF9800` |
| R3 | Tree / Woody Cover | `#2E7D32` |
| R4 | Water | `#1976D2` |
| R5 | Grassland / Herbaceous | `#8BC34A` |
| R6 | Bare Ground | `#795548` |
| R7 | Uncertain / Cloud | `#9E9E9E` |

Palette SHA-256: `8e782b...e30f`. Prediction SHA-256: `c49da6...bb03`. The abbreviated hashes are identifiers reported by the inspected application metadata, not newly computed values in this document.

### Polygon database

Active fallback file: `A7_T_FULL_AOI_POLYGONS_CLEAN.gpkg`, layer `polygons`, EPSG:32647, 155,199 features, spatial RTree present.

| Class | Feature count |
|---|---:|
| R1 | 30,906 |
| R2 | 5,527 |
| R3 | 65,111 |
| R4 | 7,840 |
| R5 | 41,479 |
| R6 | 4,336 |
| R7 | 0 |

R7 remains part of the canonical taxonomy; no R7 polygon is present in this vectorized output.

## Frontend findings

- Single-page static application; no Node build step is required at runtime.
- Leaflet 1.9.4 drives the 2D Explore map. MapLibre 6.10.0 drives the 3D terrain tour. GSAP/ScrollTrigger 3.15.0 drives narrative motion.
- Default Explore basemap is Esri satellite. OSM street and OpenTopoMap terrain are alternatives.
- Project RGB is a soft-edge image overlay above the basemap. A7-T is served as categorical PNG tiles with nearest-category rendering and one-day cache headers.
- Search results use canonical class colors, numbered map markers, a right-side result list, one selected popup, hover/click synchronization, and result-bound fitting.
- For a class-only query, the UI can display the class-filtered categorical raster over the Full AOI while listing detailed polygons in batches of 20. This is deliberate but should be explained during demonstrations: all pixels of the requested class are shown, while detailed result cards are paginated.
- The current Explore DOM has no large logo/status branding block from earlier versions.
- HTML source order is hero → discover → guided tour → explore. Browser accessibility inspection exposed a different visual/navigation sequence in the active state. This is a potential DOM/visual-order accessibility issue.
- Several layered CSS files and dormant tour/story files remain. They increase cascade and maintenance risk even though the current browser render is stable.
- Google Fonts and external basemap services require network access; the app is not fully offline.

## Drawn AOI analysis

Accepted geometry is GeoJSON Polygon or MultiPolygon in EPSG:4326. It is validated for coordinate range, topology, at least four vertices, at most 5,000 vertices, positive area, and a maximum projected area of 250 km². It is transformed to EPSG:32647 for analysis.

Categorical masking uses `all_touched=False`. For class `c`:

```text
area_m2(c) = pixel_count(c) × |pixel_width × pixel_height|
area_rai(c) = area_m2(c) / 1600
percentage(c) = pixel_count(c) / valid_class_pixels × 100
```

For A7-T the pixel area is 9 m². The geometric AOI area and the sum of valid raster class areas can differ at boundaries or where NoData occurs. NDVI, NDWI, and DEM summaries report count, mean, minimum, maximum, and median for valid masked pixels. Preview resizing uses nearest-neighbour for categorical classes and limits the largest output dimension to 2,048 pixels.

The reliability panel reports fixed VAL4 class-level metrics, not confidence for the drawn polygon and not independent Full-AOI Ground Truth validation.

## Sentinel-2 / external AOI

- Discovery: CDSE STAC `https://stac.dataspace.copernicus.eu/v1`, collection `sentinel-2-l2a`.
- Bands: B02, B03, B04, B08 at 10 m and SCL at 20 m.
- Scene score: `0.55 × coverage + 0.30 × (1 - cloud/100) + 0.15 × recency`.
- Continuous bands use bilinear resampling; SCL uses nearest-neighbour.
- Cloudy SCL: 1, 3, 7, 8, 9, 10, 11. Valid SCL: 2, 4, 5, 6.
- `NDVI=(B08-B04)/(B08+B04)`; `NDWI=(B03-B08)/(B03+B08)`.
- Cache key is SHA-256 over canonical request geometry/bands/schema; files are `bands.npz` and `metadata.json`.
- Live cache at audit time: 7 files, 2,758,109 bytes, representing three metadata/cube entries.

Prior controlled deployment evidence records a real, non-mocked extraction for bbox `[99.18,18.75,99.20,18.77]`, Sentinel-2 item dated 2026-03-26, 100% scene coverage, 99.2% valid pixels, NDVI mean 0.3639, NDWI mean -0.3653, and HTTP 200 previews for RGB/NDVI/NDWI. This audit did not repeat the heavy uncached extraction.

Required limitation: `uncached Sentinel-2 JP2 extraction currently runs synchronously and may block the application during processing; current deployment is intended for controlled single-user research/demo use.`

## Agent, RAG, and LLM

The active product endpoint is `/api/agent/query`. Its default planner is deterministic. It resolves Thai/English class aliases, classifies knowledge/spatial/mixed intent, validates distance and area parameters, and calls explicit GIS/RAG functions.

The optional OpenAI Responses API path is disabled in the current runtime. If enabled, it is restricted to structured intent extraction, uses `store:false`, does not receive database rows, and cannot generate SQL. Its JSON is validated against an allowlist (R1–R7, supported relations/units/ranges); failure falls back to the deterministic router.

RAG is local lexical token-overlap against a JSON knowledge base with rule boosts and top-k ≤10. It is not an embedding/vector database. Answers about A7-T, TEST40, R2, and Full AOI are grounded in curated local text.

Two overlapping agent/API generations remain: legacy V1 tile-ranking endpoints and V2 polygon/GIS/RAG endpoints. The frontend primarily uses V2. Consolidation is recommended after thesis freeze.

## Validation and tests

| Check | Result |
|---|---|
| Publish/live code/config SHA parity | 69/69 match |
| Live and staging HTML parity | exact match |
| Current unit suite | 43/43 passed in 36.564 s |
| Drawn AOI + external suite | 19/19 passed in 0.396 s |
| Live browser render | PASS; no observed console errors/warnings |
| Staging browser render | PASS; no observed console errors/warnings |
| Historical controlled live deployment | 19/19 checks passed |
| Historical desktop/mobile partial-overlap QA | PASS; 55.6% project / 44.4% external |

The 43-test suite includes agent V2, dry-run LLM benchmark/scoring, and mocked LLM/PostGIS bridge tests. It made no paid LLM call. These tests do not prove live PostGIS, public-network security, multi-user concurrency, load capacity, or a completed 90-call paid pilot.

## Primary risks and gaps

| Priority | Finding | Impact / recommendation |
|---|---|---|
| High | No HTTP authentication or authorization | Keep localhost-only; add identity and role checks before remote exposure. |
| High | Unauthenticated correction write endpoint | Safe only under controlled local use; protect before multi-user access. |
| High | Synchronous raster and uncached JP2 work in a single process | Can block all users; add job queue/workers and progress state later. |
| High | In-memory analysis registry | Analyses disappear after restart and are not multi-worker safe. Persist job metadata. |
| Medium | No rate limiting or request quotas | Add endpoint-specific limits before network exposure. |
| Medium | PostGIS path exists but is disabled | Current performance/scalability claims must refer to GeoPackage, not PostGIS. |
| Medium | Legacy `/api/health` overstates agent enablement | Derive it from actual integration status. |
| Medium | V1 and V2 agent/spatial surfaces overlap | Consolidate contracts and deprecate V1 after freeze. |
| Medium | No cache TTL/size eviction for Sentinel-2 | Add quota, cleanup policy, and observability. |
| Medium | No CSP/SRI/security header layer found | Add a restrictive header policy when deploying beyond localhost. |
| Medium | External fonts/basemaps/STAC/S3 | Network dependency, privacy, and availability need disclosure/fallback. |
| Medium | Many CSS layers/dormant assets | Freeze working version, then reduce cascade and unused files with visual regression tests. |
| Low | R7 naming differs slightly across schema endpoints | Centralize public labels as well as IDs/colors. |
| Low | Provenance metadata contains an older original source path | Clarify runtime canonical path versus historical origin. |

## Research interpretation safeguards

- Full-AOI A7-T is a model prediction, not Ground Truth.
- Fixed VAL4 IoU/F1 are class-level validation references, not polygon-level confidence.
- TEST40 has no Ground Truth in this application.
- NDVI/NDWI are spectral indicators, not proof of crop type, flooding, water quality, or land ownership.
- COP30 is a DSM; terrain-tour visual depth must not be interpreted as surveyed bare-earth elevation.
- Human corrections are candidate records and do not alter the prediction raster or taxonomy.

## Readiness decision

**Ready:** controlled, single-user local research demonstration on ports 8795/8802; semantic class search; class-colored results; Drawn AOI analysis; cached/controlled Sentinel-2 external AOI; evidence/trace/reliability panels; candidate human corrections.

**Not ready without additional engineering:** public Internet access, untrusted users, concurrent analysis workloads, service-level guarantees, claims of PostGIS-backed live operation, or claims that paid-LLM evaluation has been completed.

## Related audit documents

- [Current architecture](WEB_SYSTEM_ARCHITECTURE_CURRENT.md)
- [Technology stack](WEB_SYSTEM_TECH_STACK.md)
- [API reference](WEB_SYSTEM_API_REFERENCE.md)
- [Database reference](WEB_SYSTEM_DATABASE_REFERENCE.md)
- [Agent reference](WEB_SYSTEM_AGENT_REFERENCE.md)
- [Deployment guide](WEB_SYSTEM_DEPLOYMENT_GUIDE.md)
- [Advisor Q&A](WEB_SYSTEM_ADVISOR_QA_CHEATSHEET.md)
- [Machine-readable audit](WEB_SYSTEM_FULL_AUDIT.json)
- [One-page advisor brief](WEB_SYSTEM_ONE_PAGE_FOR_ADVISOR.md)
