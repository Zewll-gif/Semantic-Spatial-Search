# CLEAN PROJECT HEADER
# ไฟล์: test_llm_postgis_bridge.py
# หน้าที่: ตรวจสอบ regression และสัญญาการทำงานของระบบ
# Input: CLEAN PROJECT และ test fixtures
# Output: ผลผ่าน/ไม่ผ่านและหลักฐาน QA
# Dependency สำคัญ: backend/frontend ที่ถูกทดสอบ
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Mock-only bridge checks: no paid API or database connection is made."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import agent_orchestrator
import gis_tools
import llm_spatial_planner
import postgis_store


class LlmPostgisBridgeTests(unittest.TestCase):
    def test_llm_disabled_without_key_and_flag(self):
        with patch.dict(os.environ, {"AGENT_LLM_ENABLED": "0"}, clear=True):
            self.assertFalse(llm_spatial_planner.enabled())
        with patch.dict(os.environ, {"AGENT_LLM_ENABLED": "1", "OPENAI_API_KEY": "mock"}):
            self.assertTrue(llm_spatial_planner.enabled())

    def test_structured_plan_sends_no_sql_or_database_rows(self):
        response = {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": '{"source_class_id":"R2","target_class_id":"R4","relation":"near","distance_m":300,"area_min":5,"area_unit":"rai","clarification_required":false,"clarification_question":null}'}]}]}
        with patch.dict(os.environ, {"AGENT_LLM_ENABLED": "1", "OPENAI_API_KEY": "mock"}), \
                patch.object(llm_spatial_planner, "_request", return_value=response) as request:
            plan = llm_spatial_planner.plan_spatial_query("หาพื้นที่เกษตร 5 ไร่ ใกล้น้ำ 300 เมตร")
        self.assertEqual(plan["source_class_id"], "R2")
        self.assertEqual(plan["distance_m"], 300)
        payload = request.call_args.args[0]
        self.assertFalse(payload["store"])
        self.assertNotIn("temperature", payload)
        self.assertNotIn("top_p", payload)
        self.assertNotIn("SELECT *", str(payload))
        self.assertNotIn("geometry_json", str(payload))

    def test_invalid_llm_class_is_rejected(self):
        plan = {"source_class_id": "R8", "target_class_id": None, "relation": "none",
                "distance_m": None, "area_min": None, "area_unit": None,
                "clarification_required": False, "clarification_question": None}
        with self.assertRaises(ValueError):
            llm_spatial_planner._validate(plan)

    def test_postgis_query_is_parameterized_and_returns_geojson(self):
        row = {"polygon_id": 123, "class_code": "R2", "class_name": "Agriculture",
               "area_m2": 1600, "area_rai": 1, "area_ha": 0.16,
               "geometry_json": '{"type":"Point","coordinates":[99,18]}'}
        with patch.object(postgis_store, "_fetch", side_effect=[[{"n": 7}], [row]]) as fetch:
            result = postgis_store.search(2, None, 3)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["total_matches"], 7)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["geojson"]["features"][0]["properties"]["class_id"], "R2")
        sql, params = fetch.call_args.args
        self.assertIn("geoai_a7t.landcover_polygons", sql)
        self.assertIn("%s", sql)
        self.assertEqual(params, (2, 3, 0))

    def test_configured_postgis_does_not_silently_use_geopackage(self):
        with patch.object(gis_tools.postgis_store, "configured", return_value=True), \
                patch.object(gis_tools.postgis_store, "search", side_effect=RuntimeError("unavailable")), \
                patch.object(gis_tools.legacy, "repo", side_effect=AssertionError("GeoPackage must not be read")):
            with self.assertRaises(gis_tools.ToolError) as caught:
                gis_tools.search_landcover("R2", limit=2)
        self.assertEqual(caught.exception.code, "postgis_unavailable")

    def test_llm_plan_executes_allowlisted_gis_tool(self):
        plan = {"source_class_id": "R2", "target_class_id": "R4", "relation": "near",
                "distance_m": 300, "area_min": None, "area_unit": None,
                "clarification_required": False, "clarification_question": None}
        result = {"count": 1, "geojson": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": 123, "geometry": {"type": "Point", "coordinates": [99, 18]},
             "properties": {"feature_id": 123, "class_id": "R2", "area_sqm": 1600}}]}}
        with patch.object(agent_orchestrator, "llm_enabled", return_value=True), \
                patch.object(agent_orchestrator, "plan_spatial_query", return_value=plan), \
                patch.object(agent_orchestrator, "find_nearby", return_value=result) as gis:
            output = agent_orchestrator.run_agent_query("หาพื้นที่เกษตรใกล้น้ำ 300 เมตร", limit=1)
        self.assertEqual(output["status"], "success")
        self.assertTrue(output["llm"]["used"])
        self.assertEqual(output["tool_trace"][0]["tool"], "find_nearby")
        self.assertEqual(gis.call_args.kwargs["max_distance_m"], 300)

    def test_llm_error_falls_back_to_deterministic_router(self):
        result = {"count": 0, "geojson": {"type": "FeatureCollection", "features": []}}
        with patch.object(agent_orchestrator, "llm_enabled", return_value=True), \
                patch.object(agent_orchestrator, "plan_spatial_query", side_effect=TimeoutError("mock")), \
                patch.object(agent_orchestrator, "find_nearby", return_value=result) as gis:
            output = agent_orchestrator.run_agent_query("หาพื้นที่เกษตรใกล้น้ำ 300 เมตร", limit=1)
        self.assertEqual(output["status"], "no_result")
        self.assertFalse(output["llm"]["used"])
        self.assertEqual(output["llm"]["fallback_reason"], "TimeoutError")
        self.assertEqual(gis.call_args.kwargs["max_distance_m"], 300)

    def test_mock_llm_to_postgis_end_to_end(self):
        response = {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": '{"source_class_id":"R2","target_class_id":"R4","relation":"near","distance_m":300,"area_min":null,"area_unit":null,"clarification_required":false,"clarification_question":null}'}]}]}
        row = {"polygon_id": 123, "class_code": "R2", "class_name": "Agriculture",
               "area_m2": 1600, "area_rai": 1, "area_ha": 0.16,
               "nearest_distance_m": 80,
               "geometry_json": '{"type":"Point","coordinates":[99,18]}'}
        with patch.dict(os.environ, {"AGENT_LLM_ENABLED": "1", "OPENAI_API_KEY": "mock",
                                  "GEOAI_POSTGIS_DSN": "postgresql://mock"}), \
                patch.object(llm_spatial_planner, "_request", return_value=response), \
                patch.object(postgis_store, "_fetch", return_value=[row]) as fetch, \
                patch.object(gis_tools.legacy, "repo", side_effect=AssertionError("No GPKG fallback")):
            output = agent_orchestrator.run_agent_query("หาพื้นที่เกษตรใกล้น้ำ 300 เมตร", limit=1)
        self.assertEqual(output["status"], "success")
        self.assertTrue(output["llm"]["used"])
        self.assertEqual(output["results"]["features"][0]["nearest_distance_m"], 80)
        sql, params = fetch.call_args.args
        self.assertIn("JOIN LATERAL", sql)
        self.assertEqual(params, (300.0, 4, 300.0, 2, 0.0, 1))

    def test_near_result_includes_authoritative_distance_display_geometry(self):
        row = {"polygon_id": 123, "class_code": "R2", "class_name": "Agriculture",
               "area_m2": 1600, "area_rai": 1, "area_ha": 0.16,
               "nearest_distance_m": 80,
               "reference_feature_id": 456, "reference_class_code": "R4",
               "reference_class_name": "Water",
               "geometry_json": '{"type":"Polygon","coordinates":[[[99,18],[99.001,18],[99.001,18.001],[99,18.001],[99,18]]]}',
               "reference_geometry_json": '{"type":"Polygon","coordinates":[[[99.002,18],[99.003,18],[99.003,18.001],[99.002,18.001],[99.002,18]]]}',
               "buffer_geometry_json": '{"type":"Polygon","coordinates":[[[98.999,17.999],[99.004,17.999],[99.004,18.002],[98.999,18.002],[98.999,17.999]]]}',
               "distance_geometry_json": '{"type":"LineString","coordinates":[[99.001,18.0005],[99.002,18.0005]]}'}
        with patch.object(postgis_store, "_fetch", return_value=[row]):
            result = postgis_store.near(2, None, 4, 300, 0, 20)
        props = result["geojson"]["features"][0]["properties"]
        self.assertEqual(props["nearest_reference_feature_id"], 456)
        self.assertEqual(props["nearest_reference_class_id"], "R4")
        self.assertEqual(result["distance_context"]["references"]["features"][0]["id"], 456)
        self.assertEqual(result["distance_context"]["buffers"]["features"][0]["properties"]["buffer_distance_m"], 300)
        self.assertEqual(result["distance_context"]["lines"]["features"][0]["properties"]["distance_m"], 80)
        self.assertIn("exact buffer", result["distance_context"]["distance_method"])

    def test_feature_detail_stays_on_postgis_when_configured(self):
        row = {"polygon_id": 123, "class_code": "R2", "class_name": "Agriculture",
               "area_m2": 1600, "area_rai": 1, "area_ha": 0.16,
               "centroid_x": 500000, "centroid_y": 2000000,
               "geometry_json": '{"type":"Point","coordinates":[99,18]}'}
        with patch.object(gis_tools.postgis_store, "configured", return_value=True), \
                patch.object(postgis_store, "_fetch", return_value=[row]), \
                patch.object(gis_tools.legacy, "repo", side_effect=AssertionError("No GPKG fallback")):
            feature = gis_tools.get_feature_details(123)
        self.assertEqual(feature["properties"]["model_version"], "A7_RGBN_REVISED7_TVERSKY")
        self.assertEqual(feature["properties"]["centroid_x"], 500000)

    def test_postgis_health_checks_loaded_data_and_role_privileges(self):
        with patch.dict(os.environ, {"GEOAI_POSTGIS_DSN": "postgresql://mock"}), \
                patch.object(postgis_store, "_fetch", side_effect=[
                    [{"polygon_count": 2}],
                    [{"can_insert": False, "can_update": False, "can_delete": False}],
                ]):
            status = postgis_store.health()
        self.assertTrue(status["connected"])
        self.assertTrue(status["data_loaded"])
        self.assertTrue(status["role_read_only"])


if __name__ == "__main__":
    unittest.main()
