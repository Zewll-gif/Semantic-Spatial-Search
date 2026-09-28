# CLEAN PROJECT HEADER
# ไฟล์: test_llm_benchmark.py
# หน้าที่: ตรวจสอบ regression และสัญญาการทำงานของระบบ
# Input: CLEAN PROJECT และ test fixtures
# Output: ผลผ่าน/ไม่ผ่านและหลักฐาน QA
# Dependency สำคัญ: backend/frontend ที่ถูกทดสอบ
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
BENCH = APP_ROOT / "benchmarks"
sys.path.insert(0, str(BENCH))

from benchmark_core import (
    calculate_cost,
    consistency_rate,
    load_dataset,
    normalize_provider_payload,
    score_clarification,
    score_grounding,
    score_parameters,
    score_tools,
    score_unsupported,
    summarize_records,
)
from providers import AnthropicProvider, GeminiProvider, OpenAIProvider, ProviderConfigurationError, ProviderResult
from run_benchmark import _locked_models, _selected_model, dry_run_report, execute_one


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = load_dataset(BENCH / "agent_benchmark_v1.json")

    def query(self, query_id):
        return next(q for q in self.dataset["queries"] if q["id"] == query_id)

    def actual(self, parsed=None, tools=None, execution=None, answer=""):
        return normalize_provider_payload({"parsed": parsed or {}, "tool_calls": tools or [], "answer": answer, "execution": execution or {}}, "mock", "mock-model", "X", 1)

    def test_dataset_schema_and_gold_lock(self):
        self.assertEqual(len(self.dataset["queries"]), 30)
        self.assertTrue(self.dataset["metadata"]["created_before_provider_runs"])
        self.assertTrue(self.dataset["metadata"]["gold_answers_locked"])
        counts = {category: sum(q["category"] == category for q in self.dataset["queries"]) for category in ("spatial", "knowledge", "mixed", "ambiguous", "unsupported")}
        self.assertEqual(set(counts.values()), {6})

    def test_gold_answer_parser(self):
        s01 = self.query("S01")["gold"]
        self.assertEqual(s01["classes"]["source_class_id"], "R2")
        self.assertEqual(s01["parameters"]["max_distance_m"], 300)

    def test_partial_parameter_scoring(self):
        gold = self.query("S02")["gold"]
        actual = self.actual(parsed={"parameters": {"min_area": 5, "area_unit": "sqm"}})
        self.assertEqual(score_parameters(gold, actual), 0.5)

    def test_tool_scoring_exact_subset_and_extra_penalty(self):
        gold = self.query("S01")["gold"]
        exact = self.actual(tools=[{"name": "find_nearby", "arguments": {}}])
        extra = self.actual(tools=[{"name": "find_nearby", "arguments": {}}, {"name": "search_landcover", "arguments": {}}])
        wrong = self.actual(tools=[{"name": "search_landcover", "arguments": {}}])
        self.assertEqual(score_tools(gold, exact), 1.0)
        self.assertEqual(score_tools(gold, extra), 0.5)
        self.assertEqual(score_tools(gold, wrong), 0.0)

    def test_clarification_scoring_requires_no_tool(self):
        gold = self.query("A01")["gold"]
        good = self.actual(parsed={"clarification_required": True, "clarification_topic": "max_distance"})
        premature = self.actual(parsed={"clarification_required": True, "clarification_topic": "max_distance"}, tools=[{"name": "find_nearby", "arguments": {}}])
        self.assertEqual(score_clarification(gold, good), 1.0)
        self.assertEqual(score_clarification(gold, premature), 0.0)

    def test_unsupported_scoring(self):
        gold = self.query("U01")["gold"]
        good = self.actual(parsed={"unsupported": True, "clarification_required": True, "classes": {"supported_parent_class": "R2"}, "unsupported_capabilities": ["fine_grained_class"]}, answer="รองรับได้เพียง R2 และต้องยืนยันก่อนค้นหา")
        fabricated = self.actual(parsed={"unsupported": False}, answer="system can identify longan orchard")
        self.assertEqual(score_unsupported(gold, good), 1.0)
        self.assertEqual(score_unsupported(gold, fabricated), 0.0)

    def test_grounding_scoring(self):
        spatial = self.query("S01")["gold"]
        knowledge = self.query("K01")["gold"]
        mixed = self.query("M01")["gold"]
        gis = self.actual(execution={"gis_success_count": 1, "rag_success_count": 0}, answer="GIS result")
        rag = self.actual(execution={"gis_success_count": 0, "rag_success_count": 1}, answer="RAG answer")
        both = self.actual(execution={"gis_success_count": 1, "rag_success_count": 1}, answer="GIS + RAG answer")
        self.assertEqual(score_grounding(spatial, gis), 1.0)
        self.assertEqual(score_grounding(knowledge, rag), 1.0)
        self.assertEqual(score_grounding(mixed, both), 1.0)
        self.assertEqual(score_grounding(mixed, gis), 0.0)
        self.assertEqual(score_grounding(spatial, self.actual(execution={"gis_success_count": 1}, answer="")), 0.0)

    def test_consistency_calculation(self):
        a = self.actual(parsed={"mode": "spatial", "classes": {"class_id": "R2"}, "parameters": {"min_area": 5}}, tools=[{"name": "filter_by_area", "arguments": {}}])
        b = json.loads(json.dumps(a))
        c = self.actual(parsed={"mode": "spatial", "classes": {"class_id": "R3"}, "parameters": {"min_area": 5}}, tools=[{"name": "filter_by_area", "arguments": {}}])
        records = [{"actual": a}, {"actual": b}, {"actual": c}]
        self.assertAlmostEqual(consistency_rate(records), 2 / 3)

    def test_pricing_calculation_and_missing_price(self):
        pricing = {"providers": {"mock": {"m1": {"input_per_1m": 10, "cached_input_per_1m": 2, "output_per_1m": 20}}}}
        usage = {"input_tokens": 1000, "output_tokens": 500, "cached_tokens": 200}
        self.assertAlmostEqual(calculate_cost(usage, "mock", "m1", pricing), 0.0184)
        self.assertIsNone(calculate_cost(usage, "mock", "unknown", pricing))
        self.assertIsNone(calculate_cost({**usage, "cache_creation_tokens": 50}, "mock", "m1", pricing))

    def test_provider_output_normalization(self):
        raw = {"parsed": {"mode": "spatial", "classes": {"class_id": "R2"}}, "tool_calls": [{"name": "search_landcover", "arguments": {"class_id": "R2"}}], "rag_queries": [], "answer": ""}
        result = normalize_provider_payload(raw, "openai", "chosen-model", "S04", 2)
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["run_id"], 2)
        self.assertEqual(result["tool_calls"][0]["name"], "search_landcover")

    def test_provider_adapters_have_no_hardcoded_model(self):
        for adapter in (OpenAIProvider, GeminiProvider, AnthropicProvider):
            with self.subTest(adapter=adapter.__name__):
                instance = adapter(model=None)
                if not instance.model_env in __import__("os").environ:
                    self.assertEqual(instance.model, "")
                self.assertFalse(instance.seed_supported)

    def test_dry_run_makes_no_api_call(self):
        args = argparse.Namespace(provider="all", model=None, runs=3, query_id=None, category=None, dry_run=True, resume=False, output=None)
        report = dry_run_report(args)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["api_calls_made"], 0)
        self.assertEqual(report["planned_runs"], 270)
        self.assertEqual(report["model_selection_date"], "2026-09-16")
        self.assertEqual(report["locked_models"], {
            "openai": "gpt-5.6-terra", "gemini": "gemini-3.8-flash", "anthropic": "claude-sonnet-5"
        })
        self.assertTrue(all(not entry["sampling_parameters_sent"] for entry in report["provider_configuration"].values()))

    def test_model_selection_lock_and_prices(self):
        selection, models = _locked_models()
        self.assertEqual(len(selection["inclusion_criteria"]), 6)
        self.assertEqual(_selected_model("openai", None, models), "gpt-5.6-terra")
        with self.assertRaises(ValueError):
            _selected_model("openai", "other-model", models)
        pricing = json.loads((BENCH / "provider_pricing.json").read_text(encoding="utf-8"))
        expected = {"openai": (2, 12), "gemini": (0.75, 3.75), "anthropic": (2, 10)}
        for provider, model in models.items():
            price = pricing["providers"][provider][model]
            self.assertEqual((price["input_usd_per_1m"], price["output_usd_per_1m"]), expected[provider])
        self.assertEqual(pricing["providers"]["gemini"]["gemini-3.8-flash"]["pricing_note"], "introductory pricing through 2026-12-31")

    def test_provider_payloads_omit_sampling_parameters(self):
        samples = {
            OpenAIProvider: {"choices": [{"message": {"content": "{}"}}], "usage": {}},
            GeminiProvider: {"candidates": [{"content": {"parts": [{"text": "{}"}]}}], "usageMetadata": {}},
            AnthropicProvider: {"content": [{"type": "text", "text": "{}"}], "usage": {}},
        }
        for adapter_type, response in samples.items():
            with self.subTest(provider=adapter_type.name):
                adapter = adapter_type(model="locked-model")
                adapter.api_key = "mock-key"
                payloads = []
                def mock_post(url, headers, payload):
                    payloads.append(payload)
                    return response, 1.0
                with patch.object(adapter, "_post_json", side_effect=mock_post):
                    result = adapter.invoke_json("system", "query")
                serialized = json.dumps(payloads[0])
                for key in ('"temperature"', '"top_p"', '"top_k"', '"topP"', '"topK"', '"seed"'):
                    self.assertNotIn(key, serialized)
                self.assertFalse(result.seed_supported)
                self.assertEqual(result.sampling_metadata["actual_sampling_behavior"], "provider_default_not_reported")

    def test_transport_guard_refuses_sampling_override_before_network(self):
        adapter = OpenAIProvider(model="locked-model")
        with self.assertRaises(ProviderConfigurationError):
            adapter._post_json("https://invalid.example", {}, {"model": "locked-model", "temperature": 0})

    def test_new_pricing_does_not_invent_cache_rate(self):
        pricing = json.loads((BENCH / "provider_pricing.json").read_text(encoding="utf-8"))
        plain = {"input_tokens": 1000, "output_tokens": 500, "cached_tokens": 0}
        self.assertAlmostEqual(calculate_cost(plain, "gemini", "gemini-3.8-flash", pricing), 0.002625)
        self.assertIsNone(calculate_cost({**plain, "cached_tokens": 50}, "gemini", "gemini-3.8-flash", pricing))

    def test_partial_run_cannot_pass_selection_gate(self):
        q = self.query("S01")
        actual = self.actual(parsed={"mode": "spatial", "classes": {"source_class_id": "R2", "target_class_id": "R4"}, "parameters": {"max_distance_m": 300}}, tools=[{"name": "find_nearby", "arguments": {}}], execution={"gis_success_count": 1})
        actual["query_id"] = "S01"
        record = {"query_id": "S01", "run_id": 1, "category": "spatial", "actual": actual, "scores": {"intent_accuracy": 1.0, "class_resolution_accuracy": 1.0, "parameter_extraction_score": 1.0, "tool_selection_accuracy": 1.0, "clarification_accuracy": 1.0, "unsupported_handling_accuracy": 1.0, "grounding_rate": 1.0}}
        summary = summarize_records([record])
        self.assertFalse(summary["selection_gate"]["full_coverage"])
        self.assertFalse(summary["selection_gate"]["passed"])
        self.assertIsNone(summary["unsupported_handling_accuracy"])

    def test_mock_provider_prompt_excludes_gold(self):
        query = self.query("S01")

        class FakeProvider:
            name = "mock"
            model = "mock-model"
            seed_supported = False

            def __init__(self):
                self.calls = []

            def invoke_json(self, system_prompt, user_prompt):
                self.calls.append((system_prompt, user_prompt))
                if len(self.calls) == 1:
                    raw = {"parsed": {"mode": "spatial", "classes": {"source_class_id": "R2", "target_class_id": "R4"}, "parameters": {"max_distance_m": 300}}, "tool_calls": [{"name": "find_nearby", "arguments": {"source_class_id": "R2", "target_class_id": "R4", "max_distance_m": 300}}], "rag_queries": [], "answer": ""}
                else:
                    raw = {"answer": "พบข้อมูลจาก GIS"}
                return ProviderResult(raw=raw, latency_ms=1, usage={"input_tokens": 10, "output_tokens": 5, "cached_tokens": 0}, provider_reported_usage={}, seed_supported=False)

        provider = FakeProvider()
        with patch("run_benchmark._execute_tool", return_value={"count": 1}):
            actual = execute_one(provider, query, 1, "shared schema and tools")
        self.assertEqual(actual["execution"]["gis_success_count"], 1)
        self.assertEqual(actual["answer"], "พบข้อมูลจาก GIS")
        self.assertIn(query["query"], provider.calls[0][1])
        self.assertNotIn('"gold"', provider.calls[0][1])
        self.assertNotIn("expected_tools", provider.calls[0][1])
        self.assertNotIn(query["category"], provider.calls[0][1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
