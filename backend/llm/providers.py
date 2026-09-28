"""Responses-API provider adapters with no GeoAI business logic."""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


class ProviderError(RuntimeError):
    """Controlled provider failure; safe for deterministic fallback."""


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str


@dataclass
class ProviderTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    output_items: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    response_id: str | None = None


class LLMProvider(ABC):
    provider_name = "base"

    def __init__(self, model_name: str, api_key: str | None):
        self.model_name = model_name
        self._api_key = api_key

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    @abstractmethod
    def generate(
        self,
        *,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn:
        raise NotImplementedError


def _as_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump(exclude_none=True)
    raise ProviderError(f"Unsupported Responses API item: {type(item).__name__}")


class _ResponsesProvider(LLMProvider):
    base_url: str | None = None

    def __init__(
        self,
        model_name: str,
        api_key: str | None,
        *,
        timeout_seconds: float = 30.0,
        client_factory: Callable[..., Any] | None = None,
    ):
        super().__init__(model_name, api_key)
        self.timeout_seconds = float(timeout_seconds)
        self._client_factory = client_factory

    def _client(self):
        if not self.configured:
            raise ProviderError(f"{self.provider_name} API key is not configured")
        if self._client_factory is not None:
            return self._client_factory(
                api_key=self._api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency check is in QA
            raise ProviderError("openai Python SDK is not installed") from exc
        kwargs: dict[str, Any] = {"api_key": self._api_key, "timeout": self.timeout_seconds}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return OpenAI(**kwargs)

    def generate(
        self,
        *,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn:
        try:
            response = self._client().responses.create(
                model=self.model_name,
                instructions=instructions,
                input=input_items,
                tools=tools,
                store=False,
                max_output_tokens=1200,
            )
        except Exception as exc:
            raise ProviderError(f"{self.provider_name} Responses API failed: {type(exc).__name__}") from exc

        output_items = [_as_dict(item) for item in getattr(response, "output", [])]
        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []
        for item in output_items:
            item_type = item.get("type")
            if item_type == "function_call":
                try:
                    arguments = json.loads(item.get("arguments") or "{}")
                except json.JSONDecodeError as exc:
                    raise ProviderError("Provider returned malformed tool arguments") from exc
                if not isinstance(arguments, dict):
                    raise ProviderError("Tool arguments must be a JSON object")
                tool_calls.append(
                    ToolCall(
                        name=str(item.get("name") or ""),
                        arguments=arguments,
                        call_id=str(item.get("call_id") or item.get("id") or ""),
                    )
                )
            elif item_type == "message":
                for content in item.get("content", []):
                    if content.get("type") in {"output_text", "text"} and content.get("text"):
                        text_parts.append(str(content["text"]))

        usage_obj = getattr(response, "usage", None)
        usage = _as_dict(usage_obj) if usage_obj is not None and not isinstance(usage_obj, dict) else usage_obj
        return ProviderTurn(
            text="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
            output_items=output_items,
            usage=usage,
            response_id=getattr(response, "id", None),
        )


class OpenAIProvider(_ResponsesProvider):
    provider_name = "openai"

    def __init__(self, model_name: str | None = None, api_key: str | None = None, **kwargs: Any):
        super().__init__(
            model_name or os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
            api_key if api_key is not None else os.getenv("OPENAI_API_KEY"),
            **kwargs,
        )


class DeepSeekProvider(_ResponsesProvider):
    provider_name = "deepseek"
    base_url = "https://api.deepseek.com"

    def __init__(self, model_name: str | None = None, api_key: str | None = None, **kwargs: Any):
        super().__init__(
            model_name or os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY"),
            **kwargs,
        )


def selected_provider_name(override: str | None = None) -> str:
    name = (override or os.getenv("LLM_PROVIDER", "openai")).strip().lower()
    if name not in {"openai", "deepseek"}:
        raise ProviderError("LLM_PROVIDER must be openai or deepseek")
    return name


def get_provider(name: str | None = None, **kwargs: Any) -> LLMProvider:
    selected = selected_provider_name(name)
    return OpenAIProvider(**kwargs) if selected == "openai" else DeepSeekProvider(**kwargs)


def provider_enabled(name: str | None = None) -> bool:
    if os.getenv("AGENT_LLM_ENABLED", "0") != "1":
        return False
    try:
        selected = selected_provider_name(name)
        raw_key = os.getenv("OPENAI_API_KEY" if selected == "openai" else "DEEPSEEK_API_KEY", "").strip().lower()
        if raw_key in {"mock", "test", "test-key", "placeholder"}:
            return False
        return get_provider(selected).configured
    except ProviderError:
        return False


def provider_status(name: str | None = None) -> dict[str, Any]:
    try:
        provider = get_provider(name)
        return {
            "provider": provider.provider_name,
            "model": provider.model_name,
            "configured": provider.configured,
            "enabled": os.getenv("AGENT_LLM_ENABLED", "0") == "1" and provider.configured,
            "debug_selector": os.getenv("DEBUG_AGENT", "0").lower() in {"1", "true", "yes"},
            "api_key_exposed": False,
        }
    except ProviderError as exc:
        return {
            "provider": (name or os.getenv("LLM_PROVIDER", "openai")).lower(),
            "model": None,
            "configured": False,
            "enabled": False,
            "debug_selector": os.getenv("DEBUG_AGENT", "0").lower() in {"1", "true", "yes"},
            "api_key_exposed": False,
            "error": str(exc),
        }
