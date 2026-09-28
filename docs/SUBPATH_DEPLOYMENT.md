# Deploy GeoAI Explorer under `/smt/`

The frontend is path-prefix aware and can run at both `/` during local development and `/smt/` behind a reverse proxy. The application does not require root-level Nginx locations for CSS, JavaScript, assets, vendor files, or API routes.

## URL strategy

- `frontend/index.html` declares `<base href="./">` so document links and static resources follow the directory from which the page was loaded.
- `frontend/app-base.js` derives `window.GeoAIApp.basePath` from that document base.
- API calls, dynamic image URLs, Leaflet overlays, MapLibre tiles, and tour exemplars use `window.GeoAIApp.url(...)`.
- CSS `url(...)` values and module imports are relative to their own files.
- Third-party absolute URLs such as Esri, OpenStreetMap, OpenTopoMap, and Google Fonts are unchanged.

At `https://geodev.fun/smt/`, an internal value such as `api/health` becomes `https://geodev.fun/smt/api/health`. At `http://127.0.0.1:8795/`, the same value becomes `http://127.0.0.1:8795/api/health`.

## Compatible Nginx location

The application expects the existing trailing-slash proxy behavior, which strips `/smt/` before forwarding:

```nginx
location /smt/ {
    proxy_pass http://127.0.0.1:8888/;
}
```

No `location /assets/`, `/vendor/`, `/styles.css`, `/app.js`, or other root-level workaround is required or recommended.

## Rebuild and restart

From the application directory:

```bash
docker compose build --no-cache app
docker compose up -d --force-recreate app
docker compose ps
docker compose logs --tail=100 app
```

The compose mapping remains host port 8888 to container port 8795.

## Static audit

```bash
docker compose exec app python scripts/audit_subpath_urls.py
```

Expected result:

```text
SUBPATH URL AUDIT: PASS (no first-party root-absolute frontend URLs)
```

## Server checks

Run against the public reverse proxy:

```bash
curl -I https://geodev.fun/smt/
curl -I https://geodev.fun/smt/styles.css?v=workspace
curl -I https://geodev.fun/smt/vendor/leaflet/leaflet.js?v=1.9.4
curl -I https://geodev.fun/smt/assets/tile_r09_c09/rgb
curl https://geodev.fun/smt/api/health
curl https://geodev.fun/smt/api/system/integration-status
curl https://geodev.fun/smt/api/system/model-info
```

Optional negative checks ensure this project does not depend on root-domain routes. The response may belong to another application or be 404, but GeoAI Explorer must not request it:

```bash
curl -I https://geodev.fun/styles.css
curl -I https://geodev.fun/assets/tile_r09_c09/rgb
```

Use browser DevTools Network with the filter `domain:geodev.fun`. Every first-party request made by the GeoAI page should begin with `/smt/`.

## Local development

Local root deployment remains supported:

```powershell
.\run_local.ps1 -Python python -Port 8795
```

Open `http://127.0.0.1:8795/#explore`. The same relative URL strategy resolves resources at `/`.

## QA-only local subpath simulation

For a local end-to-end check without Nginx, start an isolated app on port 8803, then run the QA-only prefix-stripping proxy on 8804:

```powershell
$env:AGENT_LLM_ENABLED='0'
python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8803
python scripts\subpath_test_proxy.py --listen-port 8804 --upstream-port 8803
node scripts\run_subpath_browser_qa.cjs
```

The browser QA fails if any first-party request escapes `/smt/`, a local request fails, or the page produces a console error.

## Validation record (2026-09-28)

- Static URL audit: PASS; no first-party root-absolute frontend URL was found.
- Browser QA at `/smt/#explore`: PASS; 305 first-party requests were observed, all stayed under `/smt/`, with no request failure or console error.
- Browser QA at local `/#explore`: PASS; the same frontend remains usable without a prefix.
- Runtime integration checks: health PASS, operational model `A7-T`, taxonomy `Revised7`, 155,199 PostGIS polygons, read-only database role, and semantic search API PASS.
- Evidence: `qa/subpath/subpath_browser_qa.json`, `qa/subpath/smt_desktop_1440x900.png`, `qa/subpath/local_root_browser_qa.json`, and `qa/subpath/local_root_desktop_1440x900.png`.
