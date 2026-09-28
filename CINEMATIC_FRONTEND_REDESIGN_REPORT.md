# GeoAI Explorer — cinematic frontend redesign

Date: 2026-09-18. Scope: frontend presentation and interaction only. The operational A7‑T model, taxonomy, predictions, GIS calculations, backend, and APIs were not changed.

## 1–2. Prior UX and concept

The previous Explorer exposed a fixed left search panel, fixed right evidence panel, center layer card, and bottom toolbar simultaneously. This obscured the imagery and made a functioning geospatial product look like a conventional dashboard. The redesign uses a cinematic introduction, editorial four-location comparison, a concise data passage, then an imagery-first fullscreen map. UI appears in context.

## 3–4. Typography and licensing

Chosen pairing: Manrope for English/display/numerics and IBM Plex Sans Thai for Thai/body, loaded from Google Fonts. Both are open-source families listed by Google Fonts; IBM publishes Plex as open-source under the Open Font License. The CSS retains local sans-serif fallbacks when the font host is offline. No unlicensed font file was embedded. Other considered pairings were Space Grotesk + LINE Seed Sans TH and Geist + Anuphan; the selected pair had the clearest verified licensing and Thai/English balance.

## 5. Scenes

1. Full-viewport PlanetScope AOI hero and entry CTAs.
2. Landscape Atlas: four real tile RGB/A7‑T comparison sliders in a horizontally navigable visual essay.
3. Data passage: honest PlanetScope → A7‑T → GIS evidence → AI query narrative.
4. Fullscreen interactive Explorer with a floating command bar and context-driven controls.
5. Result ribbon, detail sheet, and model context after a query.

## 6. DEM

No project DEM/DTM/DSM, elevation, hillshade, slope, or contour raster was found in the searched `D:\499_2` and `D:\499_4` project files. Terrain imagery/analytics, elevation values, and a DEM layer were therefore **not fabricated or added**. The existing third-party terrain basemap remains a basemap choice, not a project DEM. A georeferenced DEM source, AOI coverage, CRS, and provenance are required to implement this scene/layer.

## 7–9. Motion and components

Native scroll, transform/opacity reveals, subtle hero parallax, comparison wipe, soft button motion, and a side-sheet transition; no heavy animation dependency or scroll-jacking. `prefers-reduced-motion` disables motion. Always-visible dashboard panels and toolbar were replaced by a command bar, one layer popover, one tools toggle, and a contextual result ribbon/sheet. Original IDs and API contracts remain intact.

## 10–12. Map, search, reliability

The Explorer map fills its scene. Existing RGB, A7‑T, NDVI, NDWI and street/satellite/terrain basemap choices remain available behind the layer control. Ctrl/Cmd+K focuses the command bar. Successful spatial/mixed queries draw real GIS polygons and show a result ribbon first; the detail sheet opens on request. Clarification, no-result and knowledge answers still open a sheet because user action or explanation is needed. Feature ID is secondary to class and measured area. Model context explicitly distinguishes class-level fixed-VAL4 metrics from polygon confidence.

## 13–15. Responsive, accessibility, performance

Mobile uses a compact map command bar and bottom sheet, with a horizontal tools tray when opened. Desktop and 390px viewport showed no horizontal overflow. Keyboard-operable layer popover, Ctrl/Cmd+K, focus-visible styling, ARIA labels, and reduced-motion behavior were retained/added. The UI uses CSS transforms/opacity, static project images, and existing Leaflet; no video or animation library was added. A 60fps performance claim has **not** been measured.

## 16. Regression and browser QA

- `node --check` passed for modified JavaScript.
- 43 Python unit tests passed.
- Real PostGIS-backed spatial search returned two R2 features; polygons rendered on the map, the result ribbon appeared, feature selection opened details, and Clear removed results/geometry.
- Real project knowledge endpoint supplied R2 source documents for knowledge/mixed presentation QA. The QA script substitutes only the paid LLM orchestration transport. Paid LLM calls: 0.
- Slider changed to 72%; desktop/mobile overflow checks passed; browser error list was empty.
- Browser QA manifest: `qa_cinematic_redesign/QA_MANIFEST.json`.

## 17. Screenshots

- Hero: `qa_cinematic_redesign/01_hero_qa.png`
- Terrain scene: unavailable; no real project DEM found.
- RGB/A7‑T comparison: `qa_cinematic_redesign/02_comparison_qa.png`
- Explorer idle: `qa_cinematic_redesign/03_explorer_idle_qa.png`
- Explorer spatial result: `qa_cinematic_redesign/04_query_result_qa.png`
- Feature detail: `qa_cinematic_redesign/05_feature_detail_qa.png`
- Mobile Explorer: `qa_cinematic_redesign/06_mobile_explorer_qa.png`
- Mixed query: `qa_cinematic_redesign/07_mixed_query_qa.png`

## 18. Remaining issues

- A true DEM scene, hillshade layer, and elevation context need a real DEM artifact/API.
- The browser QA's knowledge/mixed screenshots validate UI integration with real GIS/RAG data, not a paid live-LLM response. The existing backend unit tests cover orchestration/fallback paths; a live paid end-to-end pass remains separate.
- A measured performance/accessibility audit on the presentation hardware remains useful; the current QA is functional and visual, not an FPS benchmark.

## 2026-09-18 guided-tour refinement

Section 03 is now a six-step scroll-driven Guided Landscape Tour: overview → R1 built-up → R2 cropland → R4 water → R3 woody cover → live-map CTA. The camera pans/zooms across the existing Full AOI RGB preview using tile centroids from the project feature file, with crisp white anchored callouts and native-resolution RGB tile insets. Provenance and exact stops are recorded in `GUIDED_LANDSCAPE_TOUR_SOURCES.json`. This is RGB imagery with atmospheric visual depth, **not** a DEM, hillshade, 3D elevation model, or Ground Truth.

Typography was updated across the frontend to Inter + IBM Plex Sans Thai from Google Fonts. The implementation uses native scroll and `requestAnimationFrame`, not an added motion dependency. Desktop/mobile browser QA traversed all six steps, verified the CTA reaches `#explore`, and found no console error or horizontal overflow. The pre-existing Explorer QA still passed with real GIS geometry and knowledge sources; 43 backend/unit tests passed. Tour screenshots and manifest are in `qa_guided_landscape_tour/`.
