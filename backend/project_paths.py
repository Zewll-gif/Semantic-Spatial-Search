"""Portable, centralized paths for the GeoAI Explorer runtime.

The default runtime is self-contained below ``app/``. ``GEOAI_DATA_ROOT`` is
the supported override for bundled local data. External services such as
PostGIS and CDSE remain configured through environment variables.
"""
from __future__ import annotations

import os
from pathlib import Path


WEB_APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.getenv("GEOAI_DATA_ROOT", str(WEB_APP_ROOT / "data"))).expanduser().resolve()
CACHE_ROOT = WEB_APP_ROOT / "cache"

# Compatibility aliases retained for modules and scripts importing them.
PROJECT_ROOT = WEB_APP_ROOT
MODEL_ROOT = DATA_ROOT / "metadata" / "model"
SHARED_ROOT = DATA_ROOT
FINAL_A7T_ROOT = DATA_ROOT / "rasters" / "a7t"
DEPLOYMENT_ROOT = DATA_ROOT / "runtime"

PLANETSCOPE_SOURCE = DATA_ROOT / "rasters" / "planetscope" / "planetscope_full_aoi_rgbn.tif"
PREDICTION = DATA_ROOT / "rasters" / "a7t" / "A7_RGBN_REVISED7_TVERSKY_FULL_AOI.tif"
SPECTRAL_ROOT = DATA_ROOT / "rasters" / "indices"
NDVI_PATH = SPECTRAL_ROOT / "NDVI_FULL_AOI.tif"
NDWI_PATH = SPECTRAL_ROOT / "NDWI_FULL_AOI.tif"
DEM_PATH = DATA_ROOT / "rasters" / "dem" / "geoai_aoi_dem_cop30_30m.tif"

VECTOR_ROOT = DATA_ROOT / "vectors"
VECTOR_GPKG = VECTOR_ROOT / "A7_T_FULL_AOI_POLYGONS_CLEAN.gpkg"

FULL_INFERENCE_ROOT = DATA_ROOT / "runtime" / "full_aoi"
TEST40_INFERENCE_ROOT = DATA_ROOT / "runtime" / "test40"
FULL_FEATURES_PATH = DATA_ROOT / "full_aoi_tile_features.json"

PALETTE_PATH = DATA_ROOT / "metadata" / "palette" / "revised7_palette.json"
EVIDENCE_PROFILE_ROOT = DATA_ROOT / "metadata" / "evidence"
EVIDENCE_AUDIT = EVIDENCE_PROFILE_ROOT / "A7_T_EVIDENCE_CROSSCHECK_AUDIT.json"
EXTERNAL_REFERENCE_ROOT = DATA_ROOT / "metadata" / "external_lulc"
MODEL_METADATA_ROOT = DATA_ROOT / "metadata" / "model"
KNOWLEDGE_ROOT = DATA_ROOT / "knowledge"
CORRECTIONS_DB_PATH = Path(
    os.getenv("GEOAI_CORRECTIONS_DB", str(DATA_ROOT / "corrections" / "human_corrections.sqlite"))
).expanduser().resolve()
SENTINEL_CACHE_ROOT = Path(
    os.getenv("SENTINEL2_CACHE_DIR", str(CACHE_ROOT / "sentinel2"))
).expanduser().resolve()
