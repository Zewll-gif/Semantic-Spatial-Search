# GeoAI A7-T REST API V1

The FastAPI foundation is implemented in `backend/geoai_api.py`. It uses the
clean A7-T GeoPackage as a read-only fallback when `GEOAI_POSTGIS_DSN` is not
configured. Production PostGIS mode uses the dedicated `geoai_a7t` schema.

All responses use `{status, request_id, data, limitations}`. Web geometries are
GeoJSON EPSG:4326; area and distance calculations remain in projected
EPSG:32647. No arbitrary SQL or filesystem paths are accepted.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/geoai/health` | GET | Backend/model/database status |
| `/api/geoai/classes` | GET | Revised R1-R7 taxonomy |
| `/api/geoai/search` | POST | Filter polygons by class and area |
| `/api/geoai/area` | POST | Area by polygon ID or GeoJSON |
| `/api/geoai/distance` | POST | Minimum geometry-to-geometry distance |
| `/api/geoai/near` | POST | Target class near reference class |
| `/api/geoai/intersect` | POST | Class/geometry intersections |
| `/api/geoai/ndvi-stats` | POST | NDVI statistics for polygon/geometry |
| `/api/geoai/ndwi-stats` | POST | NDWI statistics for polygon/geometry |
| `/api/geoai/evidence` | POST | Model, spatial, NDVI/NDWI evidence package |

`near` requires `target_class`, `reference_class`, and `max_distance_m`; the
backend does not silently invent a distance. Results are capped at 100 by
request validation. Invalid classes, geometry, rasters, database failures and
empty results return machine-readable error codes.

Example canonical request:

```json
{"target_class":"R2","reference_class":"R4","max_distance_m":300,"min_area_rai":5,"max_results":10}
```

This V1 does not implement LLM orchestration. Polygons are derived from A7-T
predictions rather than GT; NDVI/NDWI and external agreement are supporting
evidence only.
