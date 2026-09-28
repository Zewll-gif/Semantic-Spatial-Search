# GeoAI Explorer self-contained project audit

Audit date: 2026-09-28  
Application root: `D:\499_2\499_Thesis_Final_PUBLISH\02_WEB_SYSTEM\app`

## 1. Result

The application runtime has been repackaged so that all local files required by the normal GeoAI Explorer workflow resolve from the application directory. The default data root is now `app/data`; it can be overridden with `GEOAI_DATA_ROOT` without changing source code.

The packaging operation copied and SHA-256 verified 672 files. Original research artifacts were preserved. No raster was reprojected, resampled, rewritten, or deleted. The operational model remains A7-T, the taxonomy remains Revised7, and the search, analysis, correction, and database logic were not changed.

The running live service on port 8795 was deliberately left running. Validation was carried out on an isolated candidate service on port 8803 and that candidate is stopped after QA.

## 2. Classification used for packaging

| Class | Meaning | Result |
|---|---|---|
| A | Required for the normal local runtime | Bundled under `app/data`; 335 files |
| B | Optional/fallback/runtime feature support | Bundled under `app/data`; 337 files |
| C | Development and QA only | Not copied into runtime data |
| D | Research/archive/non-runtime source | Not copied into runtime data |

The complete file-level source-to-destination list, byte size, class, and SHA-256 is stored in `data/metadata/runtime_data_manifest.json`.

## 3. Runtime dependency inventory

| Dependency | Previous source | New in-app location or service | Required | External after packaging | Verification |
|---|---|---|---:|---:|---|
| PlanetScope RGBN full AOI | `03_SHARED_DATA/PLANETSCOPE_METADATA/planetscope_full_aoi_rgbn.tif` | `data/rasters/planetscope/planetscope_full_aoi_rgbn.tif` | Yes | No | SHA-256 + raster grid |
| A7-T full AOI classification | `01_MODEL/06_FULL_AOI_DEPLOYMENT/full_aoi/mosaic/A7_RGBN_REVISED7_TVERSKY_FULL_AOI.tif` | `data/rasters/a7t/A7_RGBN_REVISED7_TVERSKY_FULL_AOI.tif` | Yes | No | SHA-256 + raster grid + runtime API |
| NDVI / NDWI rasters and previews | `03_SHARED_DATA/SPECTRAL_INDICES` | `data/rasters/indices` | Yes | No | SHA-256 + raster grid + preview API |
| COP30 DEM | shared analysis artifact | `data/rasters/dem` | Yes for elevation | No | SHA-256 + AOI analysis |
| Full-AOI land-cover polygons | external clean GPKG | `data/vectors/A7_T_FULL_AOI_POLYGONS_CLEAN.gpkg` | Fallback | No | SHA-256; local fallback path resolves |
| RGB tile images | full-AOI runtime assets | `data/runtime/full_aoi/tiles_rgb` | Yes | No | 323 files, SHA-256 |
| Per-tile GeoTIFFs | full-AOI runtime assets | `data/runtime/full_aoi/tiles_geotiff` | Legacy/fallback | No | 323 files, SHA-256 |
| Semantic-search metadata | full-AOI runtime assets | `data/runtime/full_aoi/semantic_search` | Optional | No | 3 files, SHA-256 |
| Revised7 palette | research metadata | `data/metadata/palette/revised7_palette.json` | Yes | No | SHA-256 + JSON parse |
| Evidence profiles/audit | evidence artifacts | `data/metadata/evidence` | Optional | No | SHA-256 + evidence API |
| External LULC comparison layers | harmonized artifacts | `data/metadata/external_lulc` | Optional | No | SHA-256 + comparison endpoint |
| Operational model description | frozen model metadata | `data/metadata/model` | Optional, for model information | No | SHA-256 + model-info API |
| Knowledge/RAG files | application knowledge artifacts | `data/knowledge` | Optional | No | SHA-256 + RAG endpoint |
| Human-correction SQLite | existing application data | `data/corrections/human_corrections.sqlite` | Optional | No | SHA-256; path centralized |
| PostgreSQL/PostGIS | configured database service | External service selected by environment | Preferred backend | Yes | Connected; 155,199 polygons; read-only policy |
| DeepSeek/OpenAI-compatible LLM | provider endpoint | External API selected by environment | Optional | Yes | Disabled during deterministic browser QA |
| CDSE/Sentinel-2 | Copernicus Data Space/S3 | External API plus `cache/sentinel2` | Optional | Yes | Credentials remain environment-only |
| Esri/OSM/online basemap services | public map services | Network service | Optional visual context | Yes | Browser requests exercised; provider availability remains external |

## 4. Files intentionally not copied

The following are not runtime dependencies and were not duplicated:

- training checkpoints and training datasets;
- TRAIN15/TRAIN18 and archived diagnostic experiments;
- FINAL_FRESH_EXPERIMENT training artifacts;
- TEST40/TEST-GT4 research artifacts;
- raw annotation databases other than the active application correction store;
- raw GISTDA/source products when the web application consumes only the harmonized outputs;
- chapter figures, thesis documents, review screenshots, and other report-only files;
- Python virtual environments, package caches, Git history, and `node_modules`.

This project does not have a Node build step or `package.json`. Browser libraries are already distributed as static frontend assets, so bundling `node_modules` would add size without providing a runtime benefit.

## 5. Centralized path configuration

Runtime-local paths are defined in `backend/project_paths.py` and resolve relative to the application root. Supported overrides are:

- `GEOAI_DATA_ROOT`: alternate root for all bundled runtime data;
- `GEOAI_CORRECTIONS_DB`: alternate correction SQLite file;
- `GEOAI_SENTINEL_CACHE`: alternate Sentinel-2 cache;
- existing database, CDSE, and LLM environment variables documented in `.env.example`.

`backend/runtime_env.py` selects GDAL/PROJ resources from the active Python environment. This avoids the previous machine-specific GIS-library path assumptions, including a system-level `PROJ_LIB` that may point at another installation.

The old absolute research locations remain only in:

- the explicit development-only source list in `scripts/package_runtime_data.ps1`;
- historical source citations in the knowledge base;
- a commented `ogr2ogr` migration example.

They are not consulted by normal runtime code in `backend/` or `frontend/`.

## 6. Files changed or added

Core runtime/path changes:

- `backend/project_paths.py`
- `backend/runtime_env.py`
- `backend/main.py`
- `backend/agent_layer.py`
- `backend/gis_tools.py`
- `backend/geoai_api.py`
- `backend/drawn_aoi.py`
- `backend/correction_store.py`
- `backend/rag_service.py`
- `backend/external_satellite.py`
- `backend/agent_api_v2.py`
- `backend/multisource_lulc_api.py`
- `backend/local_env.py`
- `backend/.env.example`

Packaging, startup, and verification:

- `scripts/package_runtime_data.ps1`
- `scripts/verify_runtime_files.py`
- `scripts/run_packaging_browser_qa.cjs`
- `run_local.ps1`
- `requirements.txt`
- `Dockerfile`
- `docker-compose.yml`
- `.gitignore`
- `.dockerignore`
- `cache/.gitignore`
- `README.md`

Frontend/provenance maintenance:

- `frontend/favicon.svg`
- `frontend/index.html`
- `static/aoi/full_aoi_metadata.json`
- `GUIDED_LANDSCAPE_TOUR_SOURCES.json`
- `frontend/terrain/asset_manifest.json`
- `frontend/terrain/exemplars/manifest.json`
- `frontend/terrain/class_tour_locations.json`

Generated runtime data and evidence:

- `data/**`
- `qa/self_contained/**`
- this audit document.

## 7. Reproducible installation and startup

From PowerShell:

```powershell
cd D:\499_2\499_Thesis_Final_PUBLISH\02_WEB_SYSTEM\app
C:\Users\Admin\anaconda3\envs\geoai\python.exe -m pip install -r requirements.txt
.\run_local.ps1 -Python C:\Users\Admin\anaconda3\envs\geoai\python.exe -Port 8795
```

The launcher verifies every packaged runtime file before starting unless explicitly invoked with `-SkipRuntimeVerification`. Direct startup is also supported:

```powershell
C:\Users\Admin\anaconda3\envs\geoai\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8795
```

## 8. Verification results

### Data and source integrity

- Runtime manifest: PASS, 672/672 files matched expected size and SHA-256.
- Canonical PlanetScope/A7-T/NDVI/NDWI CRS, shape, transform, resolution, and bounds: PASS.
- JSON syntax for edited metadata: PASS.
- Python byte-code compilation: PASS.
- `pip check`: PASS, no broken requirements.
- No raster reprojection, resampling, recoding, or source deletion occurred.

### API and feature regression

On the isolated candidate service:

- health, integration-status, model-info, AOI, schema, RAG, RGB tile, A7-T tile, NDVI metadata, and NDVI preview endpoints: HTTP 200;
- model identity: A7-T / Revised7;
- PostGIS: connected, 155,199 polygons, parameterized read-only allowlist;
- semantic search: returned spatial results;
- near-distance query: returned edge-to-edge distance context, reference features, buffers, and shortest-distance lines;
- drawn AOI analysis: succeeded with A7-T classes plus NDVI, NDWI, and elevation outputs;
- evidence profile, legacy-health, and LULC comparison endpoints: HTTP 200.

Automated tests:

- LLM/integration/PostGIS bridge: 38 passed;
- Agent V2: 15 passed;
- Drawn AOI: 9 passed;
- total: 62 passed, 0 failed.

The current environment did not have `pytest`; these suites were run with their existing `unittest` entry points. A plain unconfigured Agent test discovery initially selected the large GPKG fallback and was stopped because that fallback is significantly slower than PostGIS. The configured production-equivalent run passed.

### Browser and responsive QA

Browser QA used an isolated candidate on `http://127.0.0.1:8803/#explore`, with the LLM disabled to make the check deterministic.

- desktop 1440×900: PASS;
- mobile 390×844: PASS;
- search response rendered result cards and map overlays;
- model/taxonomy/database assertions passed;
- no horizontal overflow;
- mobile controls remained within the viewport;
- no JavaScript console errors;
- no failed local application requests;
- a missing favicon request was prevented by adding the local SVG favicon.

Evidence:

- `qa/self_contained/browser_qa.json`
- `qa/self_contained/desktop_1440x900.png`
- `qa/self_contained/mobile_390x844.png`

## 9. Size impact

| State | Files | Bytes | GiB |
|---|---:|---:|---:|
| Before runtime-data packaging | 1,550 | 138,285,832 | 0.129 |
| After packaging, QA, compile verification, and this audit | 2,283 | 1,441,043,139 | 1.342 |

Most of the increase is the required PlanetScope/NDVI/NDWI rasters and the optional 323-tile GeoTIFF fallback set. Sources remain in their original locations, so this is an intentional verified duplicate for portability.

## 10. Secrets and deployment safety

No credential was copied into the runtime-data tree, manifest, report, screenshot, or generated QA output. `.env.example` contains names/defaults only. `.gitignore` and `.dockerignore` exclude `backend/.env*` while explicitly retaining `backend/.env.example`.

The application directory already contained operator-owned `backend/.env` and a pre-existing timestamped `.env` backup before this work. They were neither read into reports nor modified. They must not be included when sharing or archiving the portable package. Use a deployment-specific environment file outside the distributable bundle.

## 11. Known external dependencies and limitations

- PostGIS remains external by design. The application can fall back to the bundled GPKG, but the fallback is slower and more memory intensive for large feature queries.
- LLM providers, CDSE, and online basemap services require network access and their own credentials/service availability.
- `uncached Sentinel-2 JP2 extraction currently runs synchronously and may block the application during processing; current deployment is intended for controlled single-user research/demo use.`
- The packaged model metadata is sufficient for the current operational web system; the training checkpoint is not needed for normal raster/vector search and was intentionally not duplicated.
- Historical knowledge-base citations retain original research paths for traceability. They are text provenance, not runtime file dependencies.
- The live process on port 8795 was preserved rather than restarted during packaging. Its next controlled restart will load the new self-contained paths.

## 12. Final conclusion

The application code and local runtime artifacts are now relocatable together as one application folder, subject only to the explicitly documented external services. The self-contained candidate passed checksum/grid validation, API regression, unit/integration tests, and desktop/mobile browser QA without changing the scientific data, taxonomy, model, or analysis behavior.
