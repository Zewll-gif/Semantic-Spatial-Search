# GIS Tool Contract — Drawn AOI

## Input

- GeoJSON `Polygon` or `MultiPolygon`, coordinates in EPSG:4326.
- Maximum 5,000 vertices and 250 km² per interactive request.
- Geometry must be non-empty, topologically valid, and have positive projected area.

## Controlled tools

1. `calculate_aoi_area`: projects the AOI to EPSG:32647 and returns m² and rai.
2. `get_class_distribution`: masks the frozen A7-T categorical GeoTIFF using raster cell centres, preserves R1–R7, and returns pixel count, area, and percentage. Categorical rendering uses nearest-neighbour resampling.
3. `get_ndvi_zonal_stats`: canonical NDVI mean/min/max/median.
4. `get_ndwi_zonal_stats`: canonical NDWI mean/min/max/median.
5. `get_dem_zonal_stats`: Copernicus COP30 DSM mean/min/max/median in metres. This is a DSM, not a bare-earth DTM.

No tool accepts raw SQL. No geometry is interpolated into SQL strings. Missing overlap returns a structured `no_data` result.

## Sources

- A7-T: `A7_RGBN_REVISED7_TVERSKY_FULL_AOI.tif`
- NDVI: `NDVI_FULL_AOI.tif`
- NDWI: `NDWI_FULL_AOI.tif`
- DEM: `geoai_aoi_dem_cop30_30m.tif`

`POST /api/aoi/preview` returns a transparent PNG clipped to the exact AOI; pixels outside the AOI are alpha zero.
