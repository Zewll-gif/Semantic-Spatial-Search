# GeoAI Explorer — Controlled Deployment Guide

This guide documents the observed Windows deployment. It does not authorize deployment by itself. The intended profile is controlled, single-user, localhost research/demo use.

## Current topology

- Live: `http://127.0.0.1:8795`, source/data root `D:\499_Thesis_Final\02_WEB_SYSTEM`.
- Staging: `http://127.0.0.1:8802`, publish root `D:\499_2\499_Thesis_Final_PUBLISH\02_WEB_SYSTEM`.
- Python: `C:\Users\Admin\anaconda3\envs\geoai\python.exe`.
- Application command: `python -m uvicorn main:app --host 127.0.0.1 --port PORT` from the selected `app\backend` directory.

## Preflight

1. Freeze the deployment manifest: source, destination, byte size, SHA-256, and change reason for every file.
2. Back up every destination file before replacement. Store the manifest and hashes with the backup.
3. Do not copy `.env` from staging to live. Verify only required variable names and permissions.
4. Do not modify the A7-T raster, palette, taxonomy, clean GeoPackage, correction database, or analytical rasters.
5. Record current listener PID, parent process, command line, Python path, health JSON, OpenAPI hash, and frontend root hash.
6. Confirm adequate disk space for Sentinel cache and generated exports.
7. Run unit tests on the exact staging source.

## Required configuration

Keep secrets in `app/backend/.env`, excluded from source control and reports. Supported names are documented in the tech stack. For the current active profile:

- CDSE requires `CDSE_S3_ACCESS_KEY`, `CDSE_S3_SECRET_KEY`, and optionally/configurably `CDSE_S3_ENDPOINT`.
- PostGIS remains off unless `GEOAI_POSTGIS_DSN` is explicitly set and validated.
- OpenAI remains off unless `OPENAI_API_KEY` and `AGENT_LLM_ENABLED=1` are explicitly approved.
- Set `GEOAI_PROJECT_ROOT` explicitly for portable staging/live layouts.

Never echo, screenshot, or log secret values.

## Safe controlled rollout

1. Start the candidate on an unused alternate localhost port; do not replace the live listener yet.
2. Verify `/api/health`, `/api/system/integration-status`, `/api/system/model-info`, `/openapi.json`, and `/`.
3. Compare candidate static HTML/code hashes with the intended manifest.
4. Run API regression and browser QA on the candidate.
5. Exercise one project AOI, one external AOI using a cached scene first, and one partial-overlap AOI.
6. Confirm no browser console/API error on desktop 1440×900 and mobile 390×844.
7. Only after all checks pass, stop/switch the designated live process and bind the approved candidate to 8795.
8. Repeat health, regression, and browser QA on 8795 itself.
9. Record final listener PID, start time, command, hashes, dependency versions, test outputs, and remaining limitations.

## Minimum regression matrix

| Area | Required check |
|---|---|
| Semantic Search | class-only, near-class, knowledge question, clarification case |
| Results map | satellite background, canonical class colors, numbered markers, selected popup, fit/fly |
| Draw tools | Rectangle, Polygon, Freehand |
| Project AOI | A7-T class statistics, NDVI, NDWI, COP30, trace, reliability |
| External AOI | Sentinel-2 RGB, NDVI, NDWI, scene date/cloud/coverage/valid pixels |
| Partial overlap | project/external coverage proportions and user decision flow |
| Identify | class/color/name mapping |
| Human correction | candidate save/list without prediction mutation |
| Responsive UI | desktop 1440×900; mobile 390×844; no overflow/overlap |
| Errors | browser console and API logs clear of unexpected failures |

## Rollback rule

If any required test fails:

1. Stop the candidate/new live listener.
2. Restore exactly the backed-up files using the manifest.
3. Verify restored SHA-256 values.
4. Start the prior command on 8795.
5. Recheck health, root page, one semantic query, and one project AOI.
6. Report the failed test and evidence. Do not trial-and-error patch the live tree.

## Verification commands (examples only)

Run from PowerShell with the `geoai` environment activated and from the intended backend directory:

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8802
Invoke-RestMethod http://127.0.0.1:8802/api/health
Invoke-RestMethod http://127.0.0.1:8802/api/system/integration-status
python -m unittest discover app/tests -p "test_*.py"
```

Adapt the test working directory to the project layout. Do not run a second process on an occupied port.

## Current deployment evidence

The controlled external-AOI deployment manifest is stored under `14_EXTERNAL_AOI_LIVE_DEPLOY/20260921_083432`. Its backup root is `D:\499_Thesis_Final\02_WEB_SYSTEM\deploy_backups\external_satellite_20260921_083432`. Later UI backups include `explore_map_first_20260921_093633` and `remove_logo_status_20260921_121323`.

At audit time, live and publish code/config hashes matched 69/69 and the root HTML was byte-identical. This is a snapshot, not a permanent guarantee; recompute before every deployment.

## Operations and recovery limitations

- There is no Windows service manager, health supervisor, or automatic restart documented in the current launcher.
- In-memory analyses are lost after restart.
- No multi-worker coordination or job queue exists.
- Cache/export directories require manual capacity monitoring.
- No automated database backup/retention schedule was found.
- Public exposure is not approved because authentication, authorization, rate limiting, and security headers are absent.

Required production note: `uncached Sentinel-2 JP2 extraction currently runs synchronously and may block the application during processing; current deployment is intended for controlled single-user research/demo use.`
