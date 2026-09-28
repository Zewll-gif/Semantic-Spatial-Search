"""External Sentinel-2 L2A analysis for user-drawn AOIs.

The Copernicus STAC catalogue is used only for discovery. Analytical pixels are
read from authenticated CDSE S3 assets; rendered basemap pixels are never used.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.mask import mask
from rasterio.session import AWSSession
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, reproject
from shapely.geometry import box, mapping, shape
from shapely.ops import transform as shapely_transform

from drawn_aoi import TO_UTM, TO_WGS84, validate_geometry
from project_paths import PREDICTION, SENTINEL_CACHE_ROOT

STAC_API = "https://stac.dataspace.copernicus.eu/v1"
COLLECTION = "sentinel-2-l2a"
CACHE_ROOT = SENTINEL_CACHE_ROOT
SEARCH_DAYS = 180
MAX_ITEMS = 50
REQUEST_TIMEOUT_SECONDS = 25.0
MAX_STAC_RESPONSE_BYTES = 12_000_000
BAND_KEYS = ("B02_10m", "B03_10m", "B04_10m", "B08_10m", "SCL_20m")
# v3 invalidates cubes created before the JP2OpenJPEG plugin was aligned with
# the active GDAL runtime.  Those stale caches can contain valid metadata but
# zero-filled pixels, so they must never be reused for analysis.
CACHE_SCHEMA_VERSION = "sentinel2-cube-v6-main-thread-jp2"
CLOUDY_SCL = {1, 3, 7, 8, 9, 10, 11}
VALID_SCL = {2, 4, 5, 6}


def _gdal_plugin_path() -> str | None:
    configured = os.getenv("GDAL_DRIVER_PATH", "").strip()
    if configured:
        return configured
    conda_plugins = Path(sys.prefix) / "Library" / "lib" / "gdalplugins"
    if (conda_plugins / "gdal_JP2OpenJPEG.dll").is_file():
        return str(conda_plugins)
    return None


class ExternalAnalysisError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 503):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def project_coverage(geometry: dict[str, Any]) -> dict[str, Any]:
    geom_wgs84, geom_utm, _ = validate_geometry(geometry)
    with rasterio.open(PREDICTION) as source:
        footprint_utm = box(*source.bounds)
        to_wgs84 = Transformer.from_crs(source.crs, "EPSG:4326", always_xy=True)
        footprint_wgs84 = shapely_transform(to_wgs84.transform, footprint_utm)
    overlap_wgs84 = geom_wgs84.intersection(footprint_wgs84)
    overlap_utm = shapely_transform(TO_UTM.transform, overlap_wgs84) if not overlap_wgs84.is_empty else None
    overlap_area = float(overlap_utm.area) if overlap_utm is not None else 0.0
    coverage = min(100.0, max(0.0, overlap_area / float(geom_utm.area) * 100.0))
    return {
        "status": "inside" if coverage >= 99.5 else "outside" if coverage <= 0.01 else "partial",
        "project_coverage_percentage": coverage,
        "external_coverage_percentage": 100.0 - coverage,
        "total_area_m2": float(geom_utm.area),
        "total_area_rai": float(geom_utm.area / 1600.0),
        "project_geometry": None if overlap_wgs84.is_empty else mapping(overlap_wgs84),
        "project_footprint": mapping(footprint_wgs84),
    }


def _date_range(acquisition_date: str | None = None) -> tuple[datetime, datetime]:
    if acquisition_date:
        try:
            selected = datetime.fromisoformat(acquisition_date.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ExternalAnalysisError("invalid_date", "วันที่ค้นหาไม่ถูกต้อง", 422) from exc
        if selected.tzinfo is None:
            selected = selected.replace(tzinfo=timezone.utc)
        return selected - timedelta(days=2), selected + timedelta(days=2)
    end = datetime.now(timezone.utc)
    return end - timedelta(days=SEARCH_DAYS), end


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def search_sentinel2(geometry: dict[str, Any], acquisition_date: str | None = None,
                     client: httpx.Client | None = None) -> dict[str, Any]:
    geom_wgs84, _, _ = validate_geometry(geometry)
    start, end = _date_range(acquisition_date)
    payload = {
        "collections": [COLLECTION], "intersects": mapping(geom_wgs84),
        "datetime": f"{start.isoformat().replace('+00:00', 'Z')}/{end.isoformat().replace('+00:00', 'Z')}",
        "limit": MAX_ITEMS, "query": {"eo:cloud_cover": {"lte": 100}},
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    owned = client is None
    client = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False)
    try:
        response = client.post(f"{STAC_API}/search", json=payload, headers={"accept": "application/geo+json"})
        response.raise_for_status()
        if len(response.content) > MAX_STAC_RESPONSE_BYTES:
            raise ExternalAnalysisError("response_too_large", "ผลตอบกลับจากแหล่งข้อมูลมีขนาดใหญ่เกินกำหนด")
        features = response.json().get("features", [])
    except ExternalAnalysisError:
        raise
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise ExternalAnalysisError("stac_unavailable", "ไม่สามารถเชื่อมต่อแหล่งข้อมูลดาวเทียมภายนอกได้ในขณะนี้") from exc
    finally:
        if owned:
            client.close()
    candidates = []
    for item in features:
        properties, assets = item.get("properties", {}), item.get("assets", {})
        if not item.get("geometry") or not all(key in assets for key in BAND_KEYS):
            continue
        footprint = shape(item["geometry"])
        coverage = min(1.0, max(0.0, geom_wgs84.intersection(footprint).area / max(geom_wgs84.area, 1e-15)))
        acquired = _parse_datetime(properties["datetime"])
        cloud = float(properties.get("eo:cloud_cover", 100.0))
        recency = max(0.0, 1.0 - (end - acquired).total_seconds() / max((end - start).total_seconds(), 1.0))
        score = coverage * 0.55 + (1.0 - min(100.0, cloud) / 100.0) * 0.30 + recency * 0.15
        candidates.append((score, coverage, -cloud, acquired, item))
    if not candidates:
        raise ExternalAnalysisError("no_scene", "ไม่พบภาพ Sentinel-2 ที่เหมาะสมสำหรับพื้นที่และช่วงเวลานี้", 404)
    _, coverage, _, acquired, item = max(candidates, key=lambda row: row[:4])
    props = item["properties"]
    selected_assets = {key: item["assets"][key]["href"] for key in BAND_KEYS}
    cloud = float(props.get("eo:cloud_cover", 100.0))
    return {
        "item_id": item["id"], "acquisition_datetime": acquired.isoformat(),
        "acquisition_date": acquired.date().isoformat(), "cloud_cover_percentage": cloud,
        "coverage_percentage": coverage * 100.0, "sensor": "Sentinel-2 MSI",
        "spatial_resolution_m": 10, "source": "Copernicus Data Space Ecosystem",
        "collection": COLLECTION, "stac_api": STAC_API, "assets": selected_assets,
        "cloud_warning": cloud > 50.0,
        "selection_rule": "0.55 usable coverage + 0.30 low cloud + 0.15 recency within 180 days",
    }


def _credentials() -> tuple[str, str]:
    access = os.getenv("CDSE_S3_ACCESS_KEY", "").strip()
    secret = os.getenv("CDSE_S3_SECRET_KEY", "").strip()
    if not access or not secret:
        raise ExternalAnalysisError(
            "credentials_missing",
            "ยังไม่ได้ตั้งค่าการเข้าถึงข้อมูล Sentinel-2 สำหรับการวิเคราะห์ กรุณาตั้งค่า CDSE S3 credentials ที่ backend",
        )
    return access, secret


def _cache_directory(item_id: str, geometry: dict[str, Any]) -> Path:
    canonical = json.dumps({"version": CACHE_SCHEMA_VERSION, "geometry": geometry, "bands": BAND_KEYS}, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    safe_id = "".join(char for char in item_id if char.isalnum() or char in "-_")[:160]
    return CACHE_ROOT / safe_id / digest


def _gdal_path(href: str) -> str:
    if not href.startswith("s3://eodata/"):
        raise ExternalAnalysisError("unsafe_asset", "STAC asset ไม่ได้มาจาก CDSE eodata ที่อนุญาต")
    return "/vsis3/" + href[5:]


def _raise_asset_error(exc: Exception) -> None:
    """Translate CDSE/GDAL failures without leaking credentials or asset URLs."""
    detail = str(exc)
    if any(code in detail for code in ("InvalidAccessKeyId", "SignatureDoesNotMatch", "ExpiredToken", "InvalidToken")):
        raise ExternalAnalysisError(
            "credentials_invalid",
            "CDSE S3 credentials ไม่ถูกต้องหรือหมดอายุ กรุณาสร้าง S3 access/secret key ใหม่จาก CDSE แล้วอัปเดต backend",
        ) from exc
    if any(code in detail for code in ("AccessDenied", "Forbidden")):
        raise ExternalAnalysisError(
            "credentials_forbidden",
            "CDSE S3 credentials ไม่มีสิทธิ์อ่านข้อมูล eodata ที่เลือก",
        ) from exc
    raise ExternalAnalysisError(
        "asset_unavailable",
        "ไม่สามารถอ่านข้อมูล band จาก Copernicus Data Space ได้ในขณะนี้",
    ) from exc


def _read_cube(scene: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
    cache_dir = _cache_directory(scene["item_id"], geometry)
    cache_file, metadata_file = cache_dir / "bands.npz", cache_dir / "metadata.json"
    if cache_file.is_file() and metadata_file.is_file():
        with np.load(cache_file) as cached:
            return {key: cached[key] for key in cached.files} | json.loads(metadata_file.read_text(encoding="utf-8"))
    access, secret = _credentials()
    geom_wgs84, _, _ = validate_geometry(geometry)
    aws_session = AWSSession(
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name="default",
        endpoint_url=os.getenv("CDSE_S3_ENDPOINT", "eodata.dataspace.copernicus.eu"),
    )
    env = {
        "AWS_HTTPS": "YES", "AWS_VIRTUAL_HOSTING": "FALSE", "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    }
    plugin_path = _gdal_plugin_path()
    if plugin_path:
        env["GDAL_DRIVER_PATH"] = plugin_path
    arrays: dict[str, np.ndarray] = {}
    try:
        # Rasterio 1.4+ deliberately rejects AWS credential options passed
        # directly to Env. AWSSession keeps the credentials server-side while
        # exposing them to GDAL's /vsis3/ driver through the supported path.
        with rasterio.Env(aws_session, **env):
            red_href = _gdal_path(scene["assets"]["B04_10m"])
            with rasterio.open(red_href) as red_source:
                to_asset = Transformer.from_crs("EPSG:4326", red_source.crs, always_xy=True)
                geom_asset = shapely_transform(to_asset.transform, geom_wgs84)
                red, transform = mask(red_source, [mapping(geom_asset)], crop=True, filled=True, nodata=0)
                red = red[0].astype(np.float32)
                crs, height, width = red_source.crs, red.shape[0], red.shape[1]
                inside = geometry_mask([mapping(geom_asset)], out_shape=(height, width), transform=transform, invert=True)
            arrays["B04"] = red
            for target, key, resampling in (("B02", "B02_10m", Resampling.bilinear), ("B03", "B03_10m", Resampling.bilinear), ("B08", "B08_10m", Resampling.bilinear), ("SCL", "SCL_20m", Resampling.nearest)):
                with rasterio.open(_gdal_path(scene["assets"][key])) as source:
                    clipped, clipped_transform = mask(source, [mapping(geom_asset)], crop=True, filled=True, nodata=0)
                    destination = np.zeros((height, width), dtype=np.float32)
                    reproject(
                        source=clipped[0], destination=destination,
                        src_transform=clipped_transform, src_crs=source.crs,
                        dst_transform=transform, dst_crs=crs,
                        src_nodata=0, dst_nodata=0, resampling=resampling,
                    )
                    arrays[target] = destination
    except ExternalAnalysisError:
        raise
    except (OSError, rasterio.errors.RasterioError) as exc:
        _raise_asset_error(exc)
    bounds = array_bounds(height, width, transform)
    to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    west, south = to_wgs84.transform(bounds[0], bounds[1]); east, north = to_wgs84.transform(bounds[2], bounds[3])
    metadata = {
        "inside": inside.astype(np.uint8), "transform": list(transform)[:6], "crs": str(crs),
        "bbox": [min(west, east), min(south, north), max(west, east), max(south, north)],
        "cache_path": str(cache_dir),
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_file, **arrays, inside=metadata["inside"])
    metadata_file.write_text(json.dumps({key: value for key, value in metadata.items() if key != "inside"}, ensure_ascii=False, indent=2), encoding="utf-8")
    return arrays | metadata


def _indices(cube: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    red, green, nir, scl = cube["B04"], cube["B03"], cube["B08"], np.rint(cube["SCL"]).astype(np.uint8)
    inside = cube["inside"].astype(bool)
    cloud = np.isin(scl, list(CLOUDY_SCL)) & inside
    nodata = ((scl == 0) | (red <= 0) | (green <= 0) | (nir <= 0)) & inside & ~cloud
    valid = inside & np.isin(scl, list(VALID_SCL)) & ~nodata
    ndvi = np.full(red.shape, np.nan, dtype=np.float32); ndwi = np.full(red.shape, np.nan, dtype=np.float32)
    np.divide(nir - red, nir + red, out=ndvi, where=valid & ((nir + red) != 0))
    np.divide(green - nir, green + nir, out=ndwi, where=valid & ((green + nir) != 0))
    return ndvi, ndwi, valid, cloud, nodata


def _stats(values: np.ndarray) -> dict[str, Any]:
    valid = values[np.isfinite(values)]
    if valid.size == 0:
        return {"available": False, "count": 0}
    return {"available": True, "count": int(valid.size), "mean": float(np.mean(valid)),
            "median": float(np.median(valid)), "min": float(np.min(valid)), "max": float(np.max(valid))}


def analyze_external_aoi(geometry: dict[str, Any], acquisition_date: str | None = None,
                         scene: dict[str, Any] | None = None) -> dict[str, Any]:
    geom_wgs84, geom_utm, vertices = validate_geometry(geometry)
    scene = scene or search_sentinel2(geometry, acquisition_date)
    cube = _read_cube(scene, geometry)
    ndvi, ndwi, valid, cloud, nodata = _indices(cube)
    inside = cube["inside"].astype(bool); total = int(np.count_nonzero(inside))
    valid_count = int(np.count_nonzero(valid))
    if valid_count == 0:
        raise ExternalAnalysisError(
            "no_usable_pixels",
            "ภาพ Sentinel-2 ที่เลือกไม่มีพิกเซลที่ใช้วิเคราะห์ได้ในพื้นที่นี้ กรุณาเลือกวันที่อื่นหรือวาดพื้นที่ใหม่",
            422,
        )
    valid_pct = valid_count / total * 100.0 if total else 0.0
    cloud_pct = int(np.count_nonzero(cloud)) / total * 100.0 if total else 0.0
    nodata_pct = int(np.count_nonzero(nodata)) / total * 100.0 if total else 0.0
    warning = scene["cloud_warning"] or valid_pct < 70.0
    trace = [
        {"tool": "check_project_coverage", "status": "success", "source": "A7-T footprint", "result": "external analysis selected"},
        {"tool": "search_sentinel2", "status": "success", "source": STAC_API, "result": scene["item_id"]},
        {"tool": "select_best_scene", "status": "success", "source": COLLECTION, "result": f"{scene['acquisition_date']} · cloud {scene['cloud_cover_percentage']:.1f}%"},
        {"tool": "calculate_external_ndvi", "status": "success", "source": "B08 NIR + B04 Red", "result": f"{_stats(ndvi)['count']} valid pixels"},
        {"tool": "calculate_external_ndwi", "status": "success", "source": "B03 Green + B08 NIR", "result": f"{_stats(ndwi)['count']} valid pixels"},
        {"tool": "calculate_external_zonal_stats", "status": "success", "source": "Sentinel-2 L2A SCL-masked pixels", "result": f"{valid_pct:.1f}% valid coverage"},
    ]
    summary = (f"พื้นที่ที่เลือกอยู่นอกขอบเขตข้อมูล PlanetScope/A7-T ระบบจึงใช้ภาพ Sentinel-2 Level-2A "
               f"วันที่ {scene['acquisition_date']} สำหรับการวิเคราะห์ โดยพบค่า NDVI เฉลี่ย "
               f"{_stats(ndvi).get('mean', float('nan')):.3f} และค่า NDWI เฉลี่ย {_stats(ndwi).get('mean', float('nan')):.3f}")
    return {
        "status": "success", "analysis_type": "external_satellite", "source_badge": "External satellite analysis",
        "geometry": mapping(geom_wgs84), "geometry_vertices": vertices,
        "area_m2": float(geom_utm.area), "area_rai": float(geom_utm.area / 1600.0),
        "scene": {key: value for key, value in scene.items() if key != "assets"},
        "ndvi": _stats(ndvi), "ndwi": _stats(ndwi), "valid_pixel_percentage": valid_pct,
        "cloud_pixel_percentage": cloud_pct, "nodata_pixel_percentage": nodata_pct,
        "cloud_warning": warning,
        "bands": {"rgb": ["B04", "B03", "B02"], "ndvi": ["B08", "B04"], "ndwi": ["B03", "B08"], "mask": "SCL_20m"},
        "formulas": {"ndvi": "(B08 - B04) / (B08 + B04)", "ndwi": "(B03 - B08) / (B03 + B08)"},
        "summary": summary, "summary_mode": "deterministic GIS-grounded external analysis",
        "execution_trace": trace, "cache": {"directory": cube["cache_path"], "key": "item ID + AOI + bands"},
        "limitations": ["Sentinel-2 is not A7-T classification.", "No R1-R7 classes are inferred from Sentinel-2 in this phase."],
    }


def _colour_index(values: np.ndarray, valid: np.ndarray, palette: str) -> np.ndarray:
    clipped = np.clip((values + 1.0) / 2.0, 0.0, 1.0)
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    if palette == "ndvi":
        rgba[..., 0] = (220 * (1.0 - clipped)).astype(np.uint8)
        rgba[..., 1] = (70 + 170 * clipped).astype(np.uint8)
        rgba[..., 2] = (45 * (1.0 - clipped)).astype(np.uint8)
    else:
        rgba[..., 0] = (210 * (1.0 - clipped)).astype(np.uint8)
        rgba[..., 1] = (175 + 65 * clipped).astype(np.uint8)
        rgba[..., 2] = (110 + 145 * clipped).astype(np.uint8)
    rgba[..., 3] = np.where(valid & np.isfinite(values), 235, 0).astype(np.uint8)
    return rgba


def render_external_preview(geometry: dict[str, Any], layer: str = "rgb",
                            acquisition_date: str | None = None) -> tuple[bytes, list[float], dict[str, Any]]:
    if layer not in {"rgb", "ndvi", "ndwi"}:
        raise ExternalAnalysisError("invalid_layer", "layer ต้องเป็น rgb, ndvi หรือ ndwi", 422)
    scene = search_sentinel2(geometry, acquisition_date)
    cube = _read_cube(scene, geometry)
    ndvi, ndwi, valid, _, _ = _indices(cube)
    if not np.any(valid):
        raise ExternalAnalysisError(
            "no_usable_pixels",
            "ภาพ Sentinel-2 ที่เลือกไม่มีพิกเซลที่ใช้แสดงผลได้ในพื้นที่นี้ กรุณาเลือกวันที่อื่นหรือวาดพื้นที่ใหม่",
            422,
        )
    if layer == "rgb":
        rgba = np.zeros((*cube["B04"].shape, 4), dtype=np.uint8)
        for channel, band in enumerate((cube["B04"], cube["B03"], cube["B02"])):
            sample = band[valid]
            low, high = (np.percentile(sample, [2, 98]) if sample.size else (0.0, 1.0))
            rgba[..., channel] = (np.clip((band - low) / max(high - low, 1.0), 0, 1) * 255).astype(np.uint8)
        rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    else:
        rgba = _colour_index(ndvi if layer == "ndvi" else ndwi, valid, layer)
    image = Image.fromarray(rgba, "RGBA")
    if max(image.size) > 2048:
        ratio = 2048 / max(image.size)
        image = image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))), Image.Resampling.BILINEAR)
    stream = BytesIO(); image.save(stream, format="PNG", optimize=True)
    return stream.getvalue(), cube["bbox"], {key: value for key, value in scene.items() if key != "assets"}
