"""Fail-closed verification for the portable GeoAI Explorer data bundle."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import rasterio


APP_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = APP_ROOT / "data" / "metadata" / "runtime_data_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> int:
    if not MANIFEST.is_file():
        print(f"ERROR: missing manifest: {MANIFEST}", file=sys.stderr)
        return 2
    payload = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    errors: list[str] = []
    for item in payload.get("items", []):
        path = APP_ROOT / item["destination"]
        if not path.is_file():
            errors.append(f"missing: {item['destination']}")
            continue
        if path.stat().st_size != int(item["size_bytes"]):
            errors.append(f"size mismatch: {item['destination']}")
            continue
        if sha256(path) != str(item["sha256"]).upper():
            errors.append(f"hash mismatch: {item['destination']}")

    raster_paths = {
        "planetscope": APP_ROOT / "data/rasters/planetscope/planetscope_full_aoi_rgbn.tif",
        "a7t": APP_ROOT / "data/rasters/a7t/A7_RGBN_REVISED7_TVERSKY_FULL_AOI.tif",
        "ndvi": APP_ROOT / "data/rasters/indices/NDVI_FULL_AOI.tif",
        "ndwi": APP_ROOT / "data/rasters/indices/NDWI_FULL_AOI.tif",
    }
    grids = {}
    for name, path in raster_paths.items():
        if not path.is_file():
            errors.append(f"missing raster: {path.relative_to(APP_ROOT)}")
            continue
        with rasterio.open(path) as source:
            grids[name] = (source.crs, source.width, source.height, source.transform)
    if len(grids) == 4 and len(set(grids.values())) != 1:
        errors.append("canonical PlanetScope/A7-T/NDVI/NDWI grids differ")

    if errors:
        print("RUNTIME DATA VERIFICATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"RUNTIME DATA VERIFICATION: PASS ({len(payload.get('items', []))} files)")
    print("Canonical PlanetScope/A7-T/NDVI/NDWI grid equality: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
