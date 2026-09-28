# Human-in-the-loop Correction Workflow

1. Analyze a user-drawn AOI.
2. Choose “การจำแนกนี้ไม่ถูกต้อง” and click a location inside the AOI.
3. The controlled identify endpoint returns the original A7-T feature/class.
4. Select R1–R7, optionally add a note, and save.
5. The record is stored in `data/human_corrections.sqlite`, table `human_corrections`, with status `pending`.

Fields: `id`, `geometry_geojson`, `feature_id`, `original_class`, `corrected_class`, `model_version`, `created_at`, `note`, `source_aoi_id`, and `review_status` (`pending`, `reviewed`, `accepted`, `rejected`).

Corrections are candidate annotations. They do not modify the A7-T raster, do not trigger automatic retraining, and are not Ground Truth until an authorized review explicitly accepts them. The map shows a separate dashed correction marker using the corrected class colour.
