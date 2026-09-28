# CLEAN PROJECT HEADER
# ไฟล์: verify_clean_artifacts.py
# หน้าที่: ตรวจว่า artifact หลักของ CLEAN COPY เปิดอ่านได้และ checkpoint ตรงกับ freeze
# Input: PlanetScope, A7-T prediction, NDVI/NDWI, GeoPackage และ freeze metadata
# Output: สรุป QA แบบข้อความและ exit code ที่ใช้ใน cleanup audit
# Dependency สำคัญ: rasterio, sqlite3, hashlib
# สิ่งที่ต้องระวัง: อ่านอย่างเดียว ไม่แก้ raster, vector หรือ model artifact
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import rasterio


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def sha256(path: Path) -> str:
    """คำนวณ SHA-256 ของไฟล์โดยอ่านเป็นช่วง เพื่อลดการใช้หน่วยความจำ."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def inspect_raster(label: str, path: Path, expected_bands: int | None = None) -> None:
    """เปิด raster แบบ read-only และตรวจมิติ จำนวน band และ CRS ขั้นต้น."""
    with rasterio.open(path) as dataset:
        if expected_bands is not None and dataset.count != expected_bands:
            raise AssertionError(f"{label}: expected {expected_bands} bands, got {dataset.count}")
        if dataset.width <= 0 or dataset.height <= 0 or dataset.crs is None:
            raise AssertionError(f"{label}: invalid dimensions or CRS")
        print(f"{label}=PASS shape={dataset.height}x{dataset.width} bands={dataset.count} crs={dataset.crs}")


def main() -> None:
    """ตรวจ artifact canonical ทั้งหมดที่ backend และผลวิจัยอ้างอิง."""
    shared = PROJECT_ROOT / "03_SHARED_DATA"
    deployment = PROJECT_ROOT / "01_MODEL" / "06_FULL_AOI_DEPLOYMENT"
    final_model = PROJECT_ROOT / "01_MODEL" / "04_FINAL_A7T"

    inspect_raster("PLANETSCOPE_RGBN", shared / "PLANETSCOPE_METADATA" / "planetscope_full_aoi_rgbn.tif", 4)
    inspect_raster("A7T_PREDICTION", deployment / "full_aoi" / "mosaic" / "A7_RGBN_REVISED7_TVERSKY_FULL_AOI.tif", 1)
    inspect_raster("NDVI", shared / "SPECTRAL_INDICES" / "NDVI_FULL_AOI.tif", 1)
    inspect_raster("NDWI", shared / "SPECTRAL_INDICES" / "NDWI_FULL_AOI.tif", 1)

    gpkg = deployment / "vector" / "vector_clean" / "A7_T_FULL_AOI_POLYGONS_CLEAN.gpkg"
    with sqlite3.connect(f"file:{gpkg.as_posix()}?mode=ro", uri=True) as connection:
        layers = [row[0] for row in connection.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'")]
        if not layers:
            raise AssertionError("GeoPackage does not contain a feature layer")
        count = connection.execute(f'SELECT COUNT(*) FROM "{layers[0]}"').fetchone()[0]
        if count <= 0:
            raise AssertionError("GeoPackage feature layer is empty")
        print(f"VECTOR_GPKG=PASS layer={layers[0]} features={count}")

    lock_path = final_model / "metadata" / "freeze_lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    checkpoint = final_model / "checkpoint" / "a7t_unet_rgbn_revised7_tversky_seed42.pt"
    actual = sha256(checkpoint)
    expected = lock["files"]["best_checkpoint.pt"].upper()
    if actual != expected:
        raise AssertionError(f"checkpoint hash mismatch: {actual} != {expected}")
    print(f"A7T_CHECKPOINT_SHA256=PASS {actual}")
    print("ARTIFACT_VERIFICATION=PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ARTIFACT_VERIFICATION=FAIL {exc}", file=sys.stderr)
        raise
