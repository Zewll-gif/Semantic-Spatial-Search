# GeoAI Explorer — Database and Spatial Data Reference

## Current database decision

The current live runtime is **GeoPackage fallback**, not PostGIS. `/api/system/integration-status` reported `GEOAI_POSTGIS_DSN` missing. The PostGIS adapter and migration are implemented and tested with mocks, but no claim should be made that live search is currently PostGIS-backed.

## Active GeoPackage

Canonical file:

```text
01_MODEL/06_FULL_AOI_DEPLOYMENT/full_aoi/vector/vector_clean/
A7_T_FULL_AOI_POLYGONS_CLEAN.gpkg
```

Properties:

- Size: 203,452,416 bytes.
- Layer: `polygons`.
- CRS: EPSG:32647.
- Geometry: Polygon.
- Feature count: 155,199.
- Bounds: 488442, 2063799, 513348, 2091723.
- SQLite GeoPackage spatial RTree tables are present.

Columns:

| Column | Meaning |
|---|---|
| `fid` | GeoPackage primary feature ID |
| `geom` | polygon geometry |
| `polygon_id` | canonical application feature ID |
| `class_id`, `class_code`, `class_name` | Revised-7 taxonomy |
| `area_m2`, `area_ha`, `area_km2`, `area_rai` | precomputed area units |
| `perimeter_m` | projected perimeter |
| `centroid_x`, `centroid_y` | projected centroid |
| `bbox_minx/miny/maxx/maxy` | projected bounds |
| `source_model`, `source_raster`, `model_version` | provenance |
| `crs` | source CRS descriptor |

Class distribution: R1 30,906; R2 5,527; R3 65,111; R4 7,840; R5 41,479; R6 4,336; R7 0.

The fallback repository loads the GeoPackage through GeoPandas and retains it in process memory. Shapely/GeoPandas perform filtering, intersection, and distance operations. This is suitable for one controlled user but increases memory/startup cost and does not provide database concurrency semantics.

## Optional PostGIS schema

Migration creates:

- schema `geoai_a7t`;
- table `landcover_polygons` with MultiPolygon geometry SRID 32647;
- unique `polygon_id`;
- class, area, centroid/bounds, and provenance attributes;
- GIST index on geometry;
- B-tree indexes on `class_id` and `class_code`;
- `dataset_metadata` table.

The adapter uses `psycopg2`, `connect_timeout=5`, read-only transactions, parameterized values, an SQL allowlist, a default statement timeout of 10 seconds, and a 30-second near-query timeout. If a DSN is configured but the database fails, the design raises an error rather than silently switching to a different dataset.

Spatial operations used by the adapter:

| Operation | PostGIS function(s) |
|---|---|
| scoped search | `ST_Intersects`, `ST_GeomFromText` |
| identify | `ST_Point`, `ST_SetSRID`, `ST_Transform`, `ST_Intersects` |
| near | `ST_DWithin`, `ST_Distance`, lateral nearest match |
| detail | `ST_Centroid`, `ST_X`, `ST_Y` |
| intersection area | `ST_Intersects`, `ST_Intersection`, `ST_Area` |
| web geometry | `ST_Transform(...,4326)`, `ST_AsGeoJSON` |

## Human correction SQLite

Live file: `app/data/human_corrections.sqlite` (16,384 bytes at audit; 0 rows).

Table stores:

- ID and GeoJSON geometry;
- optional source feature ID;
- original and corrected class;
- model version and timestamp;
- user note;
- source AOI ID;
- review status, initially `pending`.

An index exists on `source_aoi_id`. Corrections are review candidates only; they do not modify the A7-T raster, GeoPackage, PostGIS prediction table, taxonomy, or model.

Implementation note: the correction store executes `CREATE TABLE IF NOT EXISTS` and index setup in its connection helper. Therefore a nominal read can create the database/schema if it is missing. For a stricter immutable production read path, move schema initialization to an explicit migration step.

## Raster data as analytical stores

| File | Role | CRS / resolution |
|---|---|---|
| PlanetScope RGBN | original project imagery | 32647 / 3 m |
| A7-T Full AOI | categorical prediction | 32647 / 3 m |
| NDVI | continuous spectral indicator | 32647 / 3 m |
| NDWI | continuous spectral indicator | 32647 / 3 m |
| COP30 DSM | elevation/surface context | 32647 / 30 m |

All project rasters align spatially enough for masked analysis; the DEM has a slightly expanded 30 m grid. The A7-T raster has no overviews reported, so on-demand tile rendering may incur CPU cost.

## Units and formulas

- Projected areas/distances use EPSG:32647 metres.
- `1 rai = 1,600 m²`.
- `1 hectare = 10,000 m²`.
- `1 km² = 1,000,000 m²`.
- A7-T pixel area is `3 m × 3 m = 9 m²`.
- Drawn-AOI percentage denominator is valid classified pixels (values 1–7), not geometric AOI area.

## Data source of truth

1. Taxonomy/colors: `03_SHARED_DATA/FINAL_CLASS_PALETTE/revised7_palette.json`.
2. Pixel prediction: canonical A7-T Full-AOI GeoTIFF.
3. Searchable features: clean vector GeoPackage; optional imported PostGIS table must preserve the same source.
4. Spectral evidence: canonical NDVI and NDWI rasters.
5. Terrain: canonical COP30 DSM.
6. Corrections: separate SQLite candidate store.

Do not infer source-of-truth status from preview PNGs, old tiles, UI labels, or historical paths embedded in metadata.

## Integrity and operational recommendations

- Record SHA-256 for every canonical raster, GeoPackage, palette, and migration artifact at release time.
- Validate feature counts and per-class area/count after any GeoPackage-to-PostGIS import.
- Keep the prediction source read-only to the web-service account.
- Give corrections a separate write role/schema and audit trail.
- Back up SQLite before schema changes; do not merge pending corrections into Ground Truth automatically.
- Explicitly configure `GEOAI_PROJECT_ROOT` for staging and deployment portability.
