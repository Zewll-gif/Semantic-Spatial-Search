from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx
import numpy as np

import external_satellite as ext


def polygon(west: float, south: float, east: float, north: float) -> dict:
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}


INSIDE = polygon(98.95, 18.74, 98.98, 18.77)
OUTSIDE = polygon(99.80, 19.88, 99.83, 19.91)
PARTIAL = polygon(99.11, 18.78, 99.14, 18.81)


def scene(cloud: float = 12.5) -> dict:
    return {
        "item_id": "S2_TEST_ITEM", "acquisition_datetime": "2026-09-15T03:45:29+00:00",
        "acquisition_date": "2026-09-15", "cloud_cover_percentage": cloud,
        "coverage_percentage": 100.0, "sensor": "Sentinel-2 MSI", "spatial_resolution_m": 10,
        "source": "Copernicus Data Space Ecosystem", "collection": ext.COLLECTION,
        "stac_api": ext.STAC_API, "cloud_warning": cloud > 50,
        "selection_rule": "test", "assets": {key: f"s3://eodata/test/{key}.jp2" for key in ext.BAND_KEYS},
    }


def cube() -> dict:
    red = np.array([[100, 100, 100, 100]] * 4, dtype=np.float32)
    green = np.array([[130, 130, 130, 130]] * 4, dtype=np.float32)
    nir = np.array([[300, 300, 300, 300]] * 4, dtype=np.float32)
    scl = np.array([[4, 4, 9, 0], [4, 5, 6, 4], [4, 4, 4, 4], [4, 4, 4, 4]], dtype=np.float32)
    return {"B02": red * .8, "B03": green, "B04": red, "B08": nir, "SCL": scl,
            "inside": np.ones((4, 4), dtype=np.uint8), "bbox": [99.8, 19.88, 99.83, 19.91],
            "cache_path": "test-cache", "transform": [10, 0, 0, 0, -10, 0], "crs": "EPSG:32647"}


class ExternalSatelliteTests(unittest.TestCase):
    def test_project_coverage_inside(self):
        result = ext.project_coverage(INSIDE)
        self.assertEqual(result["status"], "inside")
        self.assertGreater(result["project_coverage_percentage"], 99.0)

    def test_project_coverage_outside(self):
        result = ext.project_coverage(OUTSIDE)
        self.assertEqual(result["status"], "outside")
        self.assertEqual(result["project_coverage_percentage"], 0.0)

    def test_project_coverage_partial(self):
        result = ext.project_coverage(PARTIAL)
        self.assertEqual(result["status"], "partial")
        self.assertGreater(result["project_coverage_percentage"], 0.0)
        self.assertLess(result["project_coverage_percentage"], 100.0)

    def test_external_stats_do_not_emit_a7t_classes(self):
        with patch.object(ext, "search_sentinel2", return_value=scene()), patch.object(ext, "_read_cube", return_value=cube()):
            result = ext.analyze_external_aoi(OUTSIDE)
        self.assertEqual(result["analysis_type"], "external_satellite")
        self.assertNotIn("classes", result)
        self.assertAlmostEqual(result["ndvi"]["mean"], .5, places=5)
        self.assertAlmostEqual(result["ndwi"]["mean"], -170 / 430, places=5)
        self.assertLess(result["valid_pixel_percentage"], 100.0)
        self.assertEqual(result["formulas"]["ndwi"], "(B03 - B08) / (B03 + B08)")

    def test_cloudy_scene_sets_warning(self):
        with patch.object(ext, "search_sentinel2", return_value=scene(78.0)), patch.object(ext, "_read_cube", return_value=cube()):
            result = ext.analyze_external_aoi(OUTSIDE)
        self.assertTrue(result["cloud_warning"])

    def test_zero_usable_pixels_fail_closed(self):
        empty = cube()
        for key in ("B02", "B03", "B04", "B08", "SCL"):
            empty[key] = np.zeros_like(empty[key])
        with patch.object(ext, "search_sentinel2", return_value=scene()), patch.object(ext, "_read_cube", return_value=empty):
            with self.assertRaises(ext.ExternalAnalysisError) as caught:
                ext.analyze_external_aoi(OUTSIDE)
        self.assertEqual(caught.exception.code, "no_usable_pixels")
        self.assertEqual(caught.exception.status_code, 422)

    def test_no_scene_is_human_readable(self):
        class EmptyResponse:
            content = b'{"features":[]}'
            def raise_for_status(self): return None
            def json(self): return {"features": []}
        class EmptyClient:
            def post(self, *args, **kwargs): return EmptyResponse()
        with self.assertRaises(ext.ExternalAnalysisError) as caught:
            ext.search_sentinel2(OUTSIDE, client=EmptyClient())
        self.assertEqual(caught.exception.code, "no_scene")
        self.assertIn("ไม่พบภาพ Sentinel-2", caught.exception.message)

    def test_api_unavailable_is_human_readable(self):
        class FailedClient:
            def post(self, *args, **kwargs): raise httpx.ConnectError("offline")
        with self.assertRaises(ext.ExternalAnalysisError) as caught:
            ext.search_sentinel2(OUTSIDE, client=FailedClient())
        self.assertEqual(caught.exception.code, "stac_unavailable")
        self.assertNotIn("Traceback", caught.exception.message)

    def test_missing_credentials_fails_closed(self):
        with patch.dict("os.environ", {"CDSE_S3_ACCESS_KEY": "", "CDSE_S3_SECRET_KEY": ""}, clear=False):
            with self.assertRaises(ext.ExternalAnalysisError) as caught:
                ext._credentials()
        self.assertEqual(caught.exception.code, "credentials_missing")

    def test_invalid_credentials_are_human_readable(self):
        error = OSError("<Error><Code>InvalidAccessKeyId</Code></Error>")
        with self.assertRaises(ext.ExternalAnalysisError) as caught:
            ext._raise_asset_error(error)
        self.assertEqual(caught.exception.code, "credentials_invalid")
        self.assertIn("credentials", caught.exception.message)
        self.assertNotIn("InvalidAccessKeyId", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
