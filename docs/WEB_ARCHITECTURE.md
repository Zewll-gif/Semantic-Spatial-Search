# GeoAI Explorer Web Architecture

The Explore screen remains map-first. `drawn-aoi.js` manages rectangle, polygon, and freehand capture and stores the selected geometry as GeoJSON EPSG:4326. `analysis.js` sends only geometry to the backend, receives structured statistics, displays compact class bars and metric cards, and requests a transparent A7-T AOI PNG. Full rasters never travel to the browser.

The right-side panel supports drawing, loading, success, no-data, correction, saved, and error states. AOI history is session-only. Existing semantic search, result markers, basemap controls, ROI preview, export, and map behaviour remain available.

Backend routes live in `main.py`; zonal analysis is isolated in `drawn_aoi.py`; candidate corrections are isolated in `correction_store.py`.
