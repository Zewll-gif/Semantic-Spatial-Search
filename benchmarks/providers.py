# CLEAN PROJECT HEADER
# ไฟล์: providers.py
# หน้าที่: ไฟล์สนับสนุน CLEAN PROJECT
# Input: ไฟล์และ config ที่อ้างในโค้ด
# Output: ผลลัพธ์ตามหน้าที่ของไฟล์
# Dependency สำคัญ: README และ artifact ที่เกี่ยวข้อง
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
"""Provider adapters with one normalized JSON interface and no default model choice."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderResult:
    raw: dict[str, Any]
    latency_ms: float
    usage: dict[str, int | None]
    provider_reported_usage: dict[str, Any]
    seed_supported: bool
    sampling_metadata: dict[str, Any] = field(default_factory=dict)


class ProviderConfigurationError(RuntimeError):
    pass


class BenchmarkProvider(ABC):
    name = "base"
    key_env = ""
    model_env = ""
    seed_supported = False
    _forbidden_sampling_keys = {"temperature", "top_p", "top_k", "topP", "topK", "seed"}

    def __init__(self, model: str | None = None):
        self.api_key = os.getenv(self.key_env, "")
        self.model = model or os.getenv(self.model_env, "")

    def validate_config(self) -> list[str]:
        missing = []
        if not self.api_key:
            missing.append(self.key_env)
        if not self.model:
            missing.append(self.model_env)
        return missing

    def require_config(self) -> None:
        missing = self.validate_config()
        if missing:
            raise ProviderConfigurationError(f"Missing required configuration: {', '.join(missing)}")

    def _post_json(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> tuple[dict[str, Any], float]:
        def check(value: Any) -> None:
            if isinstance(value, dict):
                forbidden = self._forbidden_sampling_keys.intersection(value)
                if forbidden:
                    raise ProviderConfigurationError(f"Sampling parameters must use provider defaults: {sorted(forbidden)}")
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(payload)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={"content-type": "application/json", **headers}, method="POST")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.name} HTTP {exc.code}: {detail}") from exc
        return result, (time.perf_counter() - started) * 1000.0

    def sampling_metadata(self, payload: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
        """Record sent settings, without claiming opaque provider defaults are known."""
        return {
            "temperature_sent": False,
            "top_p_sent": False,
            "top_k_sent": False,
            "seed_sent": False,
            "seed_supported": self.seed_supported,
            "sampling_policy": "provider_model_default",
            "actual_sampling_behavior": "provider_default_not_reported",
            "response_model_id": raw.get("model") or raw.get("modelVersion"),
            "non_sampling_request_fields": sorted(payload),
            "request_generation_config": payload.get("generationConfig"),
            "request_response_format": payload.get("response_format") or payload.get("output_config"),
            "request_max_tokens": payload.get("max_tokens"),
            "provider_response_stop_reason": raw.get("stop_reason"),
            "provider_system_fingerprint": raw.get("system_fingerprint"),
        }

    @abstractmethod
    def invoke_json(self, system_prompt: str, user_prompt: str) -> ProviderResult:
        raise NotImplementedError


class OpenAIProvider(BenchmarkProvider):
    name = "openai"
    key_env = "OPENAI_API_KEY"
    model_env = "OPENAI_BENCHMARK_MODEL"

    def invoke_json(self, system_prompt: str, user_prompt: str) -> ProviderResult:
        self.require_config()
        payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        }
        raw, latency = self._post_json("https://api.openai.com/v1/chat/completions", {"authorization": f"Bearer {self.api_key}"}, payload)
        text = raw["choices"][0]["message"]["content"]
        usage = raw.get("usage", {})
        details = usage.get("prompt_tokens_details", {}) or {}
        return ProviderResult(
            raw=json.loads(text), latency_ms=latency,
            usage={"input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"), "cached_tokens": details.get("cached_tokens", 0)},
            provider_reported_usage=usage, seed_supported=False,
            sampling_metadata=self.sampling_metadata(payload, raw),
        )


class GeminiProvider(BenchmarkProvider):
    name = "gemini"
    key_env = "GEMINI_API_KEY"
    model_env = "GEMINI_BENCHMARK_MODEL"

    def invoke_json(self, system_prompt: str, user_prompt: str) -> ProviderResult:
        self.require_config()
        model = urllib.parse.quote(self.model, safe="-._")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={urllib.parse.quote(self.api_key)}"
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        raw, latency = self._post_json(url, {}, payload)
        text = "".join(part.get("text", "") for part in raw["candidates"][0]["content"]["parts"] if isinstance(part, dict))
        usage = raw.get("usageMetadata", {})
        return ProviderResult(
            raw=json.loads(text), latency_ms=latency,
            usage={"input_tokens": usage.get("promptTokenCount"), "output_tokens": usage.get("candidatesTokenCount"), "cached_tokens": usage.get("cachedContentTokenCount", 0)},
            provider_reported_usage=usage, seed_supported=False,
            sampling_metadata=self.sampling_metadata(payload, raw),
        )


class AnthropicProvider(BenchmarkProvider):
    name = "anthropic"
    key_env = "ANTHROPIC_API_KEY"
    model_env = "ANTHROPIC_BENCHMARK_MODEL"

    def invoke_json(self, system_prompt: str, user_prompt: str) -> ProviderResult:
        self.require_config()
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        raw, latency = self._post_json("https://api.anthropic.com/v1/messages", headers, payload)
        text = "".join(block.get("text", "") for block in raw.get("content", []) if block.get("type") == "text")
        usage = raw.get("usage", {})
        cached_read = usage.get("cache_read_input_tokens", 0) or 0
        cached_creation = usage.get("cache_creation_input_tokens", 0) or 0
        uncached = usage.get("input_tokens")
        return ProviderResult(
            raw=json.loads(text), latency_ms=latency,
            usage={
                "input_tokens": None if uncached is None else int(uncached) + int(cached_read) + int(cached_creation),
                "output_tokens": usage.get("output_tokens"),
                "cached_tokens": cached_read,
                "cache_creation_tokens": cached_creation,
            },
            provider_reported_usage=usage, seed_supported=False,
            sampling_metadata=self.sampling_metadata(payload, raw),
        )


PROVIDERS = {"openai": OpenAIProvider, "gemini": GeminiProvider, "anthropic": AnthropicProvider}


def make_provider(name: str, model: str | None = None) -> BenchmarkProvider:
    key = str(name).lower()
    if key not in PROVIDERS:
        raise ProviderConfigurationError(f"Unsupported provider: {name}")
    return PROVIDERS[key](model=model)
