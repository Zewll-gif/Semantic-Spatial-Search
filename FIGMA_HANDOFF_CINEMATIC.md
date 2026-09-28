# GeoAI Explorer — Figma handoff

Status: live local web implementation is complete. An editable, image-free Figma concept frame exists at https://www.figma.com/design/xNCOqroLnyi8D751UP9KL3 . It is a visual direction board, not a pixel-perfect capture of the application.

Figma's automatic capture of the local application was blocked by the safety review because it would transfer PlanetScope imagery, prediction outputs, and UI content to Figma. No project imagery or model output was uploaded. Importing those assets into Figma requires explicit approval; the local web app continues to use them directly.

## Source of truth

- Live prototype: `http://127.0.0.1:8790/`
- Full AOI display RGB: `D:\499_2\semantic_search_app\static\aoi\full_aoi_rgb.png`
- A7-T Full AOI prediction display: `D:\499_2\semantic_search_app\static\aoi\full_aoi_prediction.png`
- Imagery metadata: `D:\499_2\semantic_search_app\static\aoi\full_aoi_metadata.json`
- UI source: `frontend/index.html`, `frontend/experience.css`, `frontend/experience.js`, `frontend/product.css`, `frontend/product.js`

The RGB display image uses PlanetScope source bands 3/2/1. The colored image is an A7-T model prediction, **not** Ground Truth. Do not use the reference screenshots as project imagery.

## Frames to recreate in Figma

1. **Desktop · Hero · 1440×900** — full-bleed real imagery, translucent dark gradient, top navigation, oversized Thai headline, primary exploration action, AOI scene card, scroll cue.
2. **Desktop · Compare · 1440×900** — warm-white editorial split layout; left narrative, right 2×2 atlas of four independently draggable RGB/Prediction tile pairs, with a compact R1–R7 legend.
3. **Desktop · Explore · 1440×900** — existing live Leaflet map, floating query card, compact toolbar and result panel.
4. **Mobile · Hero · 390×844** — full-bleed imagery and condensed navigation/card.
5. **Mobile · Compare · 390×844** — stacked narrative and horizontally snapping tile atlas with previous/next controls; drag the image divider within a card.
6. **Mobile · Explore · 390×844** — map full viewport, top search card and bottom-sheet results.

## Component inventory

- `Hero/Nav`, `Hero/Headline`, `Hero/Action`, `Hero/AOI card`, `Hero/Scroll cue`
- `Discover/Editorial copy`, `Discover/Tile comparison card ×4`, `Discover/Mobile atlas navigation`, `Discover/R1–R7 legend`, `Discover/Source note`
- `Explore/Search`, `Explore/Query chips`, `Explore/Result card`, `Explore/Feature detail`, `Explore/Reliability note`, `Explore/Bottom sheet`

## Core tokens

| Token | Value | Use |
|---|---|---|
| Cream surface | `#F5F4EF` | Discover background |
| Ink | `#172822` | Editorial text |
| Accent green | `#B8D68B` | Hero highlight |
| Deep forest | `#1F6259` | Existing interactive buttons |
| Hero image shade | `rgba(8,21,21,.84)` to transparent | Readability over imagery |
| Main panel radius | 20–25 px | Floating cards |
| UI motion | 150–350 ms | Controls and panels |
| Reveal motion | 650 ms | Section entrance only |
| UI font | `Noto Sans Thai`, `Leelawadee UI`, `Segoe UI` | Same stack as the revised-7 PlanetScope–Esri report, across body, headings, controls and labels |

The R1–R7 palette is the A7-T deployment LUT: R1 `#D73027`, R2 `#FC8D59`, R3 `#1A9850`, R4 `#4575B4`, R5 `#91CF60`, R6 `#D9A441`, R7 `#BDBDBD`. These semantic colors must not be replaced by presentation tokens.

## Prototype interactions

- Hero “เริ่มสำรวจพื้นที่” → smooth scroll to Explore.
- Hero “ดูเบื้องหลังข้อมูล” → smooth scroll to Compare.
- Each tile slider → continuously reveals the A7-T model prediction over the same RGB footprint; four cards use `tile_r09_c09`, `tile_r16_c13`, `tile_r17_c14`, and `tile_r05_c06` from the existing Full AOI deployment.
- Mobile atlas arrows → move one card at a time with reduced-motion support; a narrow glimpse of the next card suggests horizontal navigation.
- A three-pixel reading progress line helps orient the initial story scroll.
- Explore search → existing `/api/agent/query`; cards and polygons use actual API results.
- Reduced-motion preference removes entrance motion and smooth scrolling.

## Exam-demo clarity pass

- Hero: extended dark gradient behind the title, visible outlined secondary action, and a more prominent AOI tile count.
- Atlas: four labeled tile comparisons, larger R1–R7 prediction-color legend, and a small RGB ↔ A7-T interaction guide. The atlas is deployment visualization, not Ground Truth.
- Map: dark translucent search card over a dark map fallback, technical view names `RGB / A7-T / NDVI / NDWI / Roads`, example-question chips, grouped outline tools versus green Analyze/Export actions, and a legend positioned clear of the required Leaflet/OpenStreetMap attribution.

## Figma handoff

The Figma file currently contains one safe, editable desktop concept frame using only generic shapes and text. The six production screens above remain a handoff specification, not completed Figma frames. Keep the live application as implementation truth; any future Figma capture or image import needs approval before sharing project imagery externally.
