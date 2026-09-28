from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND = APP_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from canonical_schema import resolve_class_alias
from intent_router import route_query
from llm.orchestrator import run_llm_agent
from llm.prompts import SYSTEM_PROMPT_TH
from llm.providers import DeepSeekProvider, LLMProvider, OpenAIProvider, ProviderError, ProviderTurn, ToolCall
from llm.tool_registry import TOOL_DEFINITIONS, validate_tool_arguments


class _Dumpable:
    def __init__(self, payload):
        self.payload = payload

    def model_dump(self, exclude_none=True):
        return self.payload


class _FakeResponses:
    def __init__(self, response):
        self.response = response
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self.response


class _FakeClient:
    def __init__(self, response):
        self.responses = _FakeResponses(response)


class _ScriptedProvider(LLMProvider):
    provider_name = "mock"

    def __init__(self, turns):
        super().__init__("mock-model", "configured-for-test")
        self.turns = list(turns)
        self.calls = []

    def generate(self, *, instructions, input_items, tools):
        self.calls.append({"instructions": instructions, "input_items": input_items, "tools": tools})
        return self.turns.pop(0)


class LLMIntegrationTests(unittest.TestCase):
    def _function_response(self):
        item = _Dumpable({"type": "function_call", "name": "search_landcover", "arguments": '{"class_id":"R2","limit":20}', "call_id": "call_1"})
        usage = _Dumpable({"input_tokens": 10, "output_tokens": 5})
        return SimpleNamespace(output=[item], usage=usage, id="resp_1")

    def test_openai_provider(self):
        fake = _FakeClient(self._function_response())
        provider = OpenAIProvider(api_key="test-key", model_name="test-openai", client_factory=lambda **_: fake)
        turn = provider.generate(instructions="test", input_items=[{"role": "user", "content": "x"}], tools=TOOL_DEFINITIONS)
        self.assertEqual(provider.provider_name, "openai")
        self.assertEqual(turn.tool_calls[0].name, "search_landcover")
        self.assertEqual(turn.tool_calls[0].arguments["class_id"], "R2")
        self.assertFalse(fake.responses.last_kwargs["store"])

    def test_deepseek_provider(self):
        captured = {}
        fake = _FakeClient(self._function_response())

        def factory(**kwargs):
            captured.update(kwargs)
            return fake

        provider = DeepSeekProvider(api_key="test-key", model_name="deepseek-flash", client_factory=factory)
        turn = provider.generate(instructions="test", input_items=[{"role": "user", "content": "x"}], tools=TOOL_DEFINITIONS)
        self.assertEqual(turn.tool_calls[0].name, "search_landcover")
        self.assertEqual(captured["base_url"], "https://api.deepseek.com")

    def test_tool_schema(self):
        self.assertEqual(len(TOOL_DEFINITIONS), 10)
        for tool in TOOL_DEFINITIONS:
            self.assertTrue(tool["strict"])
            self.assertFalse(tool["parameters"]["additionalProperties"])
            self.assertEqual(set(tool["parameters"]["required"]), set(tool["parameters"]["properties"]))
        valid = validate_tool_arguments("find_nearby", {"source_class_id": "R2", "target_class_id": "R4", "max_distance_m": 300, "min_area": 0, "area_unit": "sqm", "limit": 20})
        self.assertEqual(valid["max_distance_m"], 300)

    def test_missing_distance(self):
        intent = route_query("หาพื้นที่เกษตรใกล้น้ำ")
        self.assertTrue(intent["clarification_required"])
        self.assertIn("กี่เมตร", intent["clarification_question"])
        with self.assertRaises(Exception):
            validate_tool_arguments("find_nearby", {"source_class_id": "R2", "target_class_id": "R4", "min_area": 0, "area_unit": "sqm", "limit": 20})

    def test_class_mapping(self):
        resolved = resolve_class_alias("พื้นที่เกษตร")
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["class_id"], "R2")

    def test_agent_tool_call(self):
        provider = _ScriptedProvider([
            ProviderTurn(tool_calls=[ToolCall("search_landcover", {"class_id": "R2", "limit": 20}, "call_1")], output_items=[{"type": "function_call", "name": "search_landcover", "arguments": '{"class_id":"R2","limit":20}', "call_id": "call_1"}]),
            ProviderTurn(text="พบ 2 พื้นที่จากผลเครื่องมือ GIS", output_items=[{"type": "message", "content": [{"type": "output_text", "text": "พบ 2 พื้นที่จากผลเครื่องมือ GIS"}]}]),
        ])

        def tool_executor(name, arguments, **kwargs):
            self.assertEqual(name, "search_landcover")
            return {"count": 2, "geojson": {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {"feature_id": 1, "class_id": "R2"}}, {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 1]}, "properties": {"feature_id": 2, "class_id": "R2"}}]}}

        result = run_llm_agent("หาพื้นที่เกษตรกรรม", provider=provider, tool_executor=tool_executor)
        self.assertEqual(result["results"]["count"], 2)
        self.assertEqual(result["tool_trace"][0]["tool"], "search_landcover")

    def test_agent_grounding(self):
        provider = _ScriptedProvider([
            ProviderTurn(tool_calls=[ToolCall("calculate_distance", {"source_feature_id": 10, "target_feature_id": 11}, "call_d")], output_items=[{"type": "function_call", "name": "calculate_distance", "arguments": '{"source_feature_id":10,"target_feature_id":11}', "call_id": "call_d"}]),
            ProviderTurn(text="ระยะทางที่ GIS คำนวณได้คือ 42.5 เมตร"),
        ])
        result = run_llm_agent("ระยะระหว่าง polygon 10 กับ 11 เท่าไหร่", provider=provider, tool_executor=lambda *args, **kwargs: {"source_feature_id": 10, "target_feature_id": 11, "distance_m": 42.5})
        self.assertIn("42.5", result["answer"])
        self.assertEqual(result["tool_trace"][0]["status"], "success")

    def test_no_llm_gis_calculation(self):
        self.assertIn("ห้ามคำนวณหรือเดาพื้นที่", SYSTEM_PROMPT_TH)
        self.assertIn("ค่าดังกล่าวต้องมาจากผลเครื่องมือเท่านั้น", SYSTEM_PROMPT_TH)
        spatial_provider = _ScriptedProvider([ProviderTurn(text="ผมคำนวณเองได้ 300 เมตร")])
        with self.assertRaises(Exception):
            run_llm_agent("หาพื้นที่เกษตรห่างน้ำ 300 เมตร", provider=spatial_provider, tool_executor=lambda *args, **kwargs: {})

    def test_fallback(self):
        fallback = {"status": "success", "llm": {"mode": "deterministic_fallback"}}
        with patch("agent_orchestrator.provider_enabled", return_value=True), patch("agent_orchestrator.run_llm_agent", side_effect=ProviderError("offline")), patch("agent_orchestrator._run_deterministic_query", return_value=fallback):
            from agent_orchestrator import run_agent_query

            result = run_agent_query("หาพื้นที่เกษตรกรรม")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["llm"]["fallback_reason"], "ProviderError")


if __name__ == "__main__":
    unittest.main()
