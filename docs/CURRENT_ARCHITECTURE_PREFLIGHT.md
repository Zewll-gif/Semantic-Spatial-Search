# Current architecture preflight

Verified on 2026-09-16 before the V2 integration.

- `backend/main.py` is the existing FastAPI application and serves the current frontend.
- `backend/geoai_api.py` is the existing deterministic GIS API over the clean A7-T GeoPackage, with EPSG:32647 area/distance calculations and EPSG:4326 web output.
- The existing spatial functions cover class/area search, distance, near, intersection, NDVI, NDWI and evidence.
- `backend/agent_layer.py` provides the existing deterministic Agent V1, local project retrieval and a fail-closed OpenAI provider adapter.
- `data/project_rag_index.json` is the existing project-document index.
- `frontend/` is the current semantic-search workspace. No existing frontend behavior was removed.
- The vector source is `D:/499_4/FINAL_ANALYSIS/A7_T_VECTOR_BACKEND/vector_clean/A7_T_FULL_AOI_POLYGONS_CLEAN.gpkg`.
- NDVI/NDWI sources are the source-aligned rasters in `D:/499_4/FINAL_ANALYSIS/SPECTRAL_INDICES/`.
- Existing GeoAI API baseline: 15/15 tests passed before V2 edits.

V2 reuses this stack and adds a canonical class schema, strict intent router, structured RAG knowledge base, reliability context and compatibility-preserving API routes.
