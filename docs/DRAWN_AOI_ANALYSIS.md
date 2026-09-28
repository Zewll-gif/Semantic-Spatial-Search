# Drawn AOI Analysis

Flow: draw rectangle/polygon/freehand → validate GeoJSON → project to EPSG:32647 → mask canonical rasters → return structured metrics → reveal A7-T only inside AOI → optionally inspect execution trace.

Class percentages use valid A7-T pixels inside the geometry and sum to approximately 100%. AOI area is the projected vector area, while per-class area is raster pixel count multiplied by the 3 m × 3 m pixel area. These values can differ slightly at polygon edges.

NDVI, NDWI, and COP30 DSM statistics exclude NoData and non-finite cells. The interactive limit is 250 km² and 5,000 vertices. AOIs outside the prediction extent return `status=no_data` rather than fabricated zeros.

Reliability wording is mandatory: A7-T proportions are model predictions; validation metrics come from Fixed VAL4 at class level and are not polygon or AOI confidence.
