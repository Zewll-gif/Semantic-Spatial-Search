# GeoAI Explorer — portable runtime

GeoAI Explorer is a FastAPI + vanilla HTML/CSS/JavaScript application for the
frozen operational model `A7_RGBN_REVISED7_TVERSKY`. The application does not
train a model, regenerate predictions, change Revised7, or modify the canonical
A7-T raster.

## Runtime layout

All local runtime files are below this folder:

```text
app/
├── backend/                 FastAPI, GIS, Agent and RAG code
├── frontend/                map-first web interface and vendored JS/CSS
├── data/
│   ├── rasters/             PlanetScope, A7-T, NDVI, NDWI and COP30
│   ├── vectors/             read-only GeoPackage fallback
│   ├── knowledge/           local knowledge documents
│   ├── corrections/         candidate-correction SQLite database
│   ├── metadata/            palette, evidence, model and copy manifest
│   └── runtime/full_aoi/    RGB tiles and legacy tile-level artifacts
├── static/                  browser-ready AOI and A7-T tiles
├── cache/sentinel2/         regenerable local cache (not bundled)
├── scripts/                 verification and maintenance scripts
├── tests/                   regression tests
└── run_local.ps1            validated local launcher
```

`GEOAI_DATA_ROOT` may override `app/data`; when unset, every local data path is
derived from the current location of `app/`.

## Install

Create a Python 3.11 environment with GDAL/PROJ-compatible Rasterio, then run:

```powershell
Set-Location <path-to-app>
python -m pip install -r requirements.txt
Copy-Item backend\.env.example backend\.env
```

Fill only the service credentials needed on that machine. Never commit
`backend/.env`. The deterministic search, local RAG, raster analysis and
GeoPackage fallback do not require an LLM key.

## Verify and run

```powershell
Set-Location <path-to-app>
python scripts\verify_runtime_files.py
.\run_local.ps1 -Python python -Port 8795
```

Equivalent direct command:

```powershell
python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8795
```

Open <http://127.0.0.1:8795/#explore> and verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8795/api/health
Invoke-RestMethod http://127.0.0.1:8795/api/system/integration-status
Invoke-RestMethod http://127.0.0.1:8795/api/system/model-info
```

## External services

- PostGIS is optional but is the production spatial-query backend. Configure
  `GEOAI_POSTGIS_DSN` with a SELECT-only role. If it is intentionally unset,
  the bundled GeoPackage is used as the read-only fallback.
- DeepSeek/OpenAI are optional tool-orchestration providers. Spatial facts are
  still calculated by allow-listed GIS functions.
- CDSE S3/STAC is required only for uncached external Sentinel-2 analysis.
- Esri, OpenStreetMap/OpenTopoMap, Google Fonts and OSM Overpass require internet
  access for their corresponding basemap/font/context layers.

See [docs/SELF_CONTAINED_PROJECT_AUDIT.md](docs/SELF_CONTAINED_PROJECT_AUDIT.md)
for the packaging inventory, hashes, validation evidence and limitations.

## Reverse proxy subpath

The same frontend supports local `/` and a reverse-proxy prefix such as
`/smt/`. It uses a document-relative base plus the centralized
`window.GeoAIApp.url(...)` resolver; it does not require root-domain Nginx
locations for application assets or APIs.

See [docs/SUBPATH_DEPLOYMENT.md](docs/SUBPATH_DEPLOYMENT.md) for Docker rebuild,
Nginx-compatible behavior, curl checks, and the local subpath QA workflow.
