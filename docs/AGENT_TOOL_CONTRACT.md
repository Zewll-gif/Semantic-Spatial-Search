# Agent tool contract

The machine-readable contract is `agent_tools_v2.json`. All spatial class inputs must be canonical `R1`-`R7`; free-text classes must be resolved before tool execution.

| Tool | Deterministic output | Key validation |
|---|---|---|
| `search_landcover` | Feature IDs and EPSG:4326 GeoJSON | Canonical class; bbox xor geometry |
| `filter_by_area` | Feature IDs and GIS area values | Area >= 0; sqm/rai/hectare |
| `find_nearby` | Matching source polygons and minimum distances | Required distance > 0 |
| `calculate_distance` | Geometry-to-geometry meters | Existing feature IDs |
| `intersects` | Relationships and intersection area | Source and target selectors |
| `get_feature_details` | Class, area, centroid, metadata, geometry | Existing feature ID |
| `get_ndvi_stats` | min/max/mean/median/distribution | Feature or geometry; raster coverage |
| `get_ndwi_stats` | min/max/mean/median/distribution | Feature or geometry; raster coverage |
| `get_geojson` | Valid FeatureCollection | 1-100 feature IDs |
| `get_evidence` | Model, spatial, spectral and external context | Existing feature and available rasters |

Area and distance use EPSG:32647. Web geometry uses EPSG:4326. Tool results are derived from A7-T predictions and must not be described as Ground Truth.

Standard fallback codes are `no_result`, `clarification_required`, `unsupported_class`, `unavailable_data`, `tool_error`, and `invalid_parameter`.

The tool trace exposes tool name, safe parameters, status and result summary only. It does not expose hidden reasoning or chain-of-thought.
