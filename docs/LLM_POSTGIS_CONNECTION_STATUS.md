# LLM ↔ PostGIS connection status (2026-09-17)

Flow: `question → optional OpenAI structured intent → validated R1–R7 plan →
allow-listed GIS tool → parameterized read-only PostGIS transaction → local answer`.
The model is never sent database credentials, polygon rows, GeoJSON or SQL.

## Verified

- The operator-owned `backend/.env` exists and has a nonempty PostGIS DSN,
  OpenAI key and `AGENT_MODEL`. Secret values were not printed or copied.
- The configured PostGIS database was initially empty. The previously QA-passed
  A7-T clean GeoPackage was transactionally imported into the dedicated
  `geoai_a7t.landcover_polygons` table; no original artifact was modified.
- Source and database each contain **155,199** polygons. Per-class counts and
  areas match the existing vector/raster audit; imported geometries passed
  `ST_IsValid`; a GIST index is present. `dataset_metadata` was also created.
- A parameterized R2 search returns a MultiPolygon. On the new app instance at
  `http://127.0.0.1:8791/`, `GET /api/system/integration-status` reports
  `database.connected=true`, `data_loaded=true`, `mode=postgis`, and 155,199
  polygons. `POST /api/agent/query` for R2 returned `status=success`, one
  PostGIS feature and `llm.used=false`.
- The canonical R2 > 5 rai within 300 m of R4 query passed end-to-end through
  `/api/agent/query` with 3 results and `find_nearby`. Observed local latency
  was about 29 seconds. This is correct but needs later performance tuning;
  the exact `ST_DWithin` semantics were retained and the request timeout was
  raised to 30 seconds rather than approximating the result.
- OpenAI model-access GET for the configured `gpt-5.6-terra` returned HTTP 200.
- After explicit operator authorization, exactly **one paid Responses API smoke
  test** was run with the query `บ่อน้ำ`. It completed successfully as
  `spatial → R4 → search_landcover`, used OpenAI structured intent, queried
  PostGIS, and returned 5 polygons / 5 GeoJSON features. No database rows,
  GeoJSON, credentials, or SQL were sent to the model.
- The water-class routing regression was fixed so bare class requests such as
  `น้ำ`, `แหล่งน้ำ`, `บ่อน้ำ`, `แม่น้ำ`, and `คลอง` are spatial searches,
  while `R4 คืออะไร` remains a knowledge question.
- The complete test suite passed **41/41** with live LLM calls explicitly
  disabled for the test process. No extra paid call, training, inference, or
  TEST40 model-selection work was performed.

## Important remaining gate

The current database login is **write-capable** (`role_read_only=false`), though
each application query uses a read-only transaction and fixed parameterized SQL.
Provision a SELECT-only application role before production exposure. Do not
reuse the schema-import account as a public-facing application credential.

`AGENT_LLM_ENABLED` is **on** for the configured port-8791 instance. The LLM is
restricted to validated structured intent; authoritative counts, geometry,
areas, distances, and map features remain local PostGIS computations.

The older `/api/geoai/*` routes remain GeoPackage-backed for compatibility.
The V2 `/api/agent/query` and `/api/spatial/*` routes use PostGIS.

The old port 8790 was left running and unchanged because safe process identity
could not be established for termination. Use port 8791 for this configured
PostGIS instance. No credentials are stored in this report.
