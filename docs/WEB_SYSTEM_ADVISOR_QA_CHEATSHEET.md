# GeoAI Explorer — Advisor Q&A Cheatsheet

Concise answers should be followed by a live demonstration or the cited audit evidence, not expanded into unsupported claims.

## System and architecture

### 1. What is GeoAI Explorer?
It is a local web application that turns natural-language land-cover questions and drawn AOIs into deterministic GIS operations over the project's A7-T prediction, spectral indices, elevation, and optional Sentinel-2 data.

### 2. Is it a dashboard or an AI agent?
Both interfaces exist, but the core “agent” is an orchestrator: it interprets intent, validates it, calls GIS/RAG tools, and returns traceable results.

### 3. What is the frontend stack?
Vanilla HTML/CSS/JavaScript, Leaflet 1.9.4 for the Explore map, MapLibre 6.10.0 for the 3D tour, and GSAP 3.15.0 for scroll motion.

### 4. What is the backend stack?
FastAPI/Uvicorn on Python 3.11, with Rasterio, GeoPandas, Shapely, PyProj, NumPy, optional psycopg2, and boto3/GDAL for CDSE.

### 5. Is it cloud deployed?
No. The audited deployment binds to `127.0.0.1` and is intended for controlled single-user research/demo use.

### 6. Are live and staging the same?
At the audit snapshot, 69 compared code/config files matched by SHA-256 and their root HTML was byte-identical.

## Model and data

### 7. Which model output is used?
The canonical Full-AOI output is `A7_RGBN_REVISED7_TVERSKY`, a custom U-Net using PlanetScope R,G,B,NIR and the Revised-7 taxonomy.

### 8. Is the Full-AOI map Ground Truth?
No. It is model prediction. The UI and reports must not call it Ground Truth.

### 9. What resolution and CRS are used?
PlanetScope, A7-T, NDVI, and NDWI use a 3 m EPSG:32647 grid. COP30 DSM is 30 m EPSG:32647. Web GeoJSON is EPSG:4326.

### 10. What are the seven classes?
R1 built-up/impervious, R2 agriculture/cropland, R3 tree/woody, R4 water, R5 grassland/herbaceous, R6 bare ground, and R7 uncertain/cloud.

### 11. Where do class colors come from?
The canonical palette JSON under `03_SHARED_DATA/FINAL_CLASS_PALETTE`; the UI should not invent colors.

### 12. Why does R7 have no polygon count?
R7 remains a valid taxonomy class, but the clean vectorized Full-AOI output contains zero R7 polygons.

### 13. What are the validation metrics?
The system exposes fixed VAL4 class-level IoU/F1. They are reference metrics, not polygon confidence or Full-AOI validation.

### 14. Is TEST40 Ground Truth?
No Ground Truth is accessed by this web application for TEST40; it must not be presented as validated labels.

## Search and GIS

### 15. How does “แหล่งน้ำ” work?
The deterministic router resolves the phrase to R4, then the spatial repository returns R4 features and map geometry.

### 16. Does the LLM write SQL?
No. The optional LLM can only propose validated intent. Parameterized, allowlisted GIS functions execute the query.

### 17. What database does live search use?
The current live runtime uses the clean GeoPackage through GeoPandas/Shapely. PostGIS code exists but its DSN is not configured.

### 18. Why are there only 20 result cards when thousands exist?
Detailed polygons/cards are paginated for usability. A class-only mode can render the whole class raster while cards load in batches.

### 19. Why are result polygons different colors?
Each feature uses its canonical class color. A universal green would incorrectly imply “tree.”

### 20. How are labels decluttered?
The current UI uses compact numbered markers and keeps detailed information in the side panel; only the selected result opens a detailed popup.

### 21. How is “near water 300 m” computed?
In projected EPSG:32647 coordinates using geometric distance; PostGIS uses `ST_DWithin`/`ST_Distance`, while the active fallback uses Shapely equivalents.

### 22. Are area units reliable?
They derive from projected metres: rai is square metres divided by 1,600. Raster AOI class area is counted pixels times pixel area.

## Drawn AOI and external data

### 23. What happens after drawing an AOI?
The geometry is validated, transformed to EPSG:32647, checked against project coverage, then analyzed from A7-T/NDVI/NDWI/COP30 or routed to Sentinel-2 for external coverage.

### 24. What is the AOI size limit?
250 km², with at most 5,000 vertices and valid lon/lat topology.

### 25. Why can geometric area and class-area sum differ?
The class sum counts valid raster cell centres (`all_touched=False`); boundary cells and NoData can differ from continuous polygon area.

### 26. How are NDVI and NDWI calculated for Sentinel-2?
NDVI is `(B08-B04)/(B08+B04)` and NDWI is `(B03-B08)/(B03+B08)`, after SCL validity/cloud masking.

### 27. How is a Sentinel-2 scene selected?
CDSE STAC candidates are scored from footprint coverage, metadata cloud percentage, and recency. The score is not a guarantee of post-mask valid pixels.

### 28. Has real Sentinel-2 been tested?
Yes, prior controlled evidence records a non-mocked RGB/NDVI/NDWI extraction with 99.2% valid pixels. This audit did not repeat an uncached heavy extraction.

### 29. What is the Sentinel-2 limitation?
An uncached JP2 extraction is synchronous and may block the application; the deployment is for controlled single-user research/demo use.

### 30. Is COP30 true terrain?
It is a 30 m global DSM representing surface elevation, not a surveyed bare-earth DTM. It supports context/visual depth, not survey-grade elevation claims.

## Agent, evidence, and corrections

### 31. Is OpenAI active now?
No. Integration status reports no configured key/enable flag. Deterministic routing is active.

### 32. What does the local RAG use?
A curated JSON knowledge base and lexical token-overlap/rule boosts. It is not a vector database.

### 33. What is Execution Trace?
A transparent record of router/tool steps and limitations. It improves auditability but is not itself proof of model correctness.

### 34. Does Human Correction retrain the model?
No. It appends a pending candidate to a separate SQLite store and never changes A7-T or the canonical taxonomy.

### 35. Can the system identify businesses or POIs?
Not from land-cover classes. The external POI provider is not configured, so the system should state insufficient data rather than relabel built-up pixels.

## Quality, security, and readiness

### 36. What tests passed?
43/43 current unit tests and 19/19 Drawn-AOI/external tests passed; live/staging rendered without observed console errors. Historical controlled live QA also passed 19/19 checks.

### 37. Was a paid LLM benchmark run?
No paid call was made in this audit. Dry-run benchmark tests verify mechanics only; they do not establish a provider winner.

### 38. Is the system secure for public access?
No. It lacks HTTP authentication/authorization, rate limiting, and a security-header layer. Localhost binding is the current boundary.

### 39. Can multiple users run heavy analysis concurrently?
Not safely. The service is synchronous/single-process and some analysis state is in memory.

### 40. What is the main source of truth?
Canonical rasters/palette plus the clean vector GeoPackage. Preview PNGs, cached tiles, UI labels, and correction candidates are not the analytical source of truth.

### 41. What is ready today?
Controlled single-user demonstration of semantic search, class results, Drawn AOI analysis, evidence/trace, and cached/controlled external Sentinel-2 workflows.

### 42. What must be done before public deployment?
Add authentication/roles, rate limits, async job queue, persistent job state, cache quota/cleanup, security headers, structured logs/monitoring, backup policy, and concurrency/load tests.
