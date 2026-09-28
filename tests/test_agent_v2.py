# CLEAN PROJECT HEADER
# ไฟล์: test_agent_v2.py
# หน้าที่: ตรวจสอบ regression และสัญญาการทำงานของระบบ
# Input: CLEAN PROJECT และ test fixtures
# Output: ผลผ่าน/ไม่ผ่านและหลักฐาน QA
# Dependency สำคัญ: backend/frontend ที่ถูกทดสอบ
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from agent_api_v2 import app
from canonical_schema import resolve_class_alias
from gis_tools import ToolError, filter_by_area, get_geojson, search_landcover
from intent_router import route_query
from rag_service import search_knowledge
from reliability import reliability_context


class AgentV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_canonical_mapping(self):
        for alias, class_id in [("พื้นที่เกษตร", "R2"), ("สวน", "R2"), ("น้ำ", "R4"), ("ป่า", "R3"), ("สิ่งก่อสร้าง", "R1"), ("บ้านเรือน", "R1")]:
            with self.subTest(alias=alias):
                result = resolve_class_alias(alias)
                self.assertEqual(result["status"], "resolved")
                self.assertEqual(result["class_id"], class_id)

    def test_unknown_class_requires_clarification(self):
        self.assertEqual(resolve_class_alias("พื้นที่ประเภทสมมติ")["status"], "clarification_required")

    def test_area_conversion_rai_to_sqm(self):
        rai = filter_by_area(class_id="R2", min_area=5, unit="rai", limit=20)
        sqm = filter_by_area(class_id="R2", min_area=8000, unit="sqm", limit=20)
        self.assertEqual(rai["filtered_ids"], sqm["filtered_ids"])
        self.assertTrue(all(row["area_sqm"] >= 8000 for row in rai["area_values"]))

    def test_empty_result_and_geojson_validity(self):
        result = filter_by_area(class_id="R2", min_area=1e12, unit="sqm", limit=5)
        self.assertEqual(result["count"], 0)
        searched = search_landcover("R2", limit=1)
        geojson = get_geojson(searched["feature_ids"])
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(geojson["features"][0]["type"], "Feature")

    def test_invalid_area_rejected(self):
        with self.assertRaises(ToolError):
            filter_by_area(class_id="R2", min_area=-1, unit="rai")

    def test_intent_modes_and_missing_distance(self):
        self.assertEqual(route_query("R2 คืออะไร")["mode"], "knowledge")
        self.assertEqual(route_query("หาพื้นที่เกษตรใกล้น้ำ 300 เมตร แล้วผลนี้เชื่อถือได้แค่ไหน")["mode"], "mixed")
        missing = route_query("หาพื้นที่เกษตรที่อยู่ใกล้น้ำ")
        self.assertTrue(missing["clarification_required"])
        self.assertIn("กี่เมตร", missing["clarification_question"])
        missing_target = route_query("หาพื้นที่เกษตรที่อยู่ใกล้")
        self.assertTrue(missing_target["clarification_required"])
        self.assertIn("คลาสเป้าหมาย", missing_target["clarification_question"])

    def test_water_class_terms_route_to_spatial_r4(self):
        for query in ("น้ำ", "แหล่งน้ำ", "บ่อน้ำ", "แม่น้ำ", "คลอง"):
            with self.subTest(query=query):
                routed = route_query(query)
                self.assertEqual(routed["mode"], "spatial")
                self.assertEqual(routed["spatial_intent"]["source_class_id"], "R4")
                self.assertFalse(routed["clarification_required"])

        definition = route_query("R4 คืออะไร")
        self.assertEqual(definition["mode"], "knowledge")

    def test_builtup_synonyms_route_to_spatial_r1(self):
        for query in ("สิ่งก่อสร้าง", "พื้นที่สิ่งก่อสร้าง", "บ้านเรือน", "พื้นที่เมือง"):
            with self.subTest(query=query):
                routed = route_query(query)
                self.assertEqual(routed["mode"], "spatial")
                self.assertEqual(routed["spatial_intent"]["source_class_id"], "R1")
                self.assertFalse(routed["clarification_required"])

    def test_unknown_phrase_is_spatial_clarification_not_false_knowledge(self):
        routed = route_query("ประเภทพื้นที่ที่ไม่รู้จัก")
        self.assertEqual(routed["mode"], "spatial")
        self.assertTrue(routed["clarification_required"])
        self.assertIn("R1-R7", routed["clarification_question"])

    def test_unsupported_fine_grained_class(self):
        result = route_query("หาสวนลำไยใกล้น้ำ")
        self.assertEqual(result["fallback_type"], "unsupported_class")
        self.assertEqual(result["candidate_class_id"], "R2")

    def test_rag_retrieval(self):
        cases = [("R2 คืออะไร", "taxonomy-revised7"), ("A7-T ใช้โมเดลอะไร", "model-a7t"), ("TEST40 มี Ground Truth ไหม", "validation-a7t"), ("Full AOI independent validation ไหม", "validation-a7t")]
        for query, expected_id in cases:
            with self.subTest(query=query):
                result = search_knowledge(query)
                self.assertTrue(any(doc["id"] == expected_id for doc in result["documents"]))

    def test_reliability_is_not_polygon_confidence(self):
        result = reliability_context("R2")
        self.assertFalse(result["calibrated_confidence"])
        self.assertTrue(result["class_metric_context"]["not_polygon_confidence"])
        self.assertFalse(result["independent_validation"])

    def test_agent_knowledge_and_clarification_endpoints(self):
        knowledge = self.client.post("/api/agent/query", json={"query": "TEST40 มี Ground Truth ไหม"})
        self.assertEqual(knowledge.status_code, 200)
        self.assertEqual(knowledge.json()["mode"], "knowledge")
        self.assertIn("ไม่มี Ground Truth", knowledge.json()["answer"])
        clarification = self.client.post("/api/agent/query", json={"query": "หาพื้นที่เกษตรที่อยู่ใกล้น้ำ"})
        self.assertEqual(clarification.status_code, 200)
        self.assertTrue(clarification.json()["clarification_required"])

    def test_agent_spatial_and_mixed_queries(self):
        spatial = self.client.post("/api/agent/query", json={"query": "หาพื้นที่เกษตรกรรมที่อยู่ใกล้แหล่งน้ำไม่เกิน 300 เมตร", "limit": 3})
        self.assertEqual(spatial.status_code, 200)
        self.assertEqual(spatial.json()["mode"], "spatial")
        self.assertIn(spatial.json()["status"], {"success", "no_result"})
        mixed = self.client.post("/api/agent/query", json={"query": "หาพื้นที่เกษตรใกล้น้ำ 300 เมตร แล้วผลนี้เชื่อถือได้แค่ไหน", "limit": 3})
        self.assertEqual(mixed.status_code, 200)
        self.assertEqual(mixed.json()["mode"], "mixed")
        if mixed.json()["status"] == "success":
            self.assertFalse(mixed.json()["reliability"]["independent_validation"])

    def test_core_api_endpoints(self):
        self.assertEqual(self.client.get("/api/schema/classes").status_code, 200)
        self.assertEqual(self.client.get("/api/schema/resolve", params={"text": "พื้นที่เกษตร"}).json()["class_id"], "R2")
        self.assertFalse(self.client.get("/api/system/model-info").json()["test40_has_ground_truth"])
        self.assertEqual(self.client.get("/api/knowledge/search", params={"q": "A7-T ใช้โมเดลอะไร"}).status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
