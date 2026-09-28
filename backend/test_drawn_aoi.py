from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pyproj import Transformer

import correction_store
from drawn_aoi import AoiValidationError, analyze_drawn_aoi, render_aoi_preview
from project_paths import PREDICTION

TO_WGS84 = Transformer.from_crs("EPSG:32647", "EPSG:4326", always_xy=True)


def box_4326(left: float, bottom: float, right: float, top: float) -> dict:
    west, south = TO_WGS84.transform(left, bottom); east, north = TO_WGS84.transform(right, top)
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}


class DrawnAoiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mixed = analyze_drawn_aoi(box_4326(497000, 2070000, 502000, 2075000))

    def test_rectangle_returns_class_distribution(self):
        self.assertEqual(self.mixed["status"], "success"); self.assertEqual(len(self.mixed["classes"]), 7); self.assertGreater(self.mixed["area_m2"], 0)

    def test_agriculture_aoi_contains_r2(self):
        result = analyze_drawn_aoi(box_4326(508000, 2070000, 510000, 2072000)); r2 = next(item for item in result["classes"] if item["class_id"] == "R2"); self.assertGreater(r2["pixels"], 0)

    def test_percentages_sum_to_100(self):
        self.assertAlmostEqual(sum(item["percentage"] for item in self.mixed["classes"]), 100.0, places=7)

    def test_outside_extent_returns_structured_no_data(self):
        result = analyze_drawn_aoi({"type": "Polygon", "coordinates": [[[0, 0], [.01, 0], [.01, .01], [0, .01], [0, 0]]]}); self.assertEqual(result["status"], "no_data")

    def test_spectral_and_dem_numeric(self):
        for key in ("ndvi", "ndwi", "elevation"):
            stats = self.mixed[key]; self.assertTrue(stats["available"]); self.assertTrue(all(isinstance(stats[name], float) for name in ("mean", "min", "max", "median")))

    def test_invalid_geometry_rejected(self):
        with self.assertRaises(AoiValidationError): analyze_drawn_aoi({"type": "Polygon", "coordinates": [[[99, 18], [99, 18], [99, 18]]]})

    def test_preview_is_png_and_nearest_neighbor(self):
        png, bbox = render_aoi_preview(box_4326(499000, 2071000, 499600, 2071600)); self.assertTrue(png.startswith(b"\x89PNG")); self.assertEqual(len(bbox), 4)

    def test_human_correction_does_not_change_prediction(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(correction_store, "DB_PATH", Path(tmp) / "corrections.sqlite"):
            before = hashlib.sha256(PREDICTION.read_bytes()).hexdigest(); saved = correction_store.save_correction(geometry={"type": "Point", "coordinates": [99, 18.8]}, feature_id=123, original_class="R1", corrected_class="R2", note="test", source_aoi_id="aoi-test"); after = hashlib.sha256(PREDICTION.read_bytes()).hexdigest()
            self.assertEqual(saved["review_status"], "pending"); self.assertFalse(saved["source_prediction_modified"]); self.assertEqual(correction_store.list_corrections("aoi-test")[0]["corrected_class"], "R2"); self.assertEqual(before, after)

    def test_execution_trace_is_safe(self):
        text = json.dumps(self.mixed["execution_trace"]).lower(); self.assertNotIn("chain-of-thought", text); self.assertNotIn("password", text); self.assertNotIn("api_key", text)
        self.assertEqual({item["tool"] for item in self.mixed["execution_trace"]}, {"calculate_aoi_area", "get_class_distribution", "get_ndvi_zonal_stats", "get_ndwi_zonal_stats", "get_dem_zonal_stats"})


if __name__ == "__main__": unittest.main()
