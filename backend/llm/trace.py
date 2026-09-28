"""Secret-safe JSONL tracing for agent orchestration."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECRET_KEY = re.compile(r"api.?key|secret|authorization|password|token", re.IGNORECASE)
_SECRET_VALUE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET_KEY.search(str(key)) else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE.sub("[REDACTED]", value)
    return value


class TraceLogger:
    def __init__(self, query: str, provider: str, model: str, path: Path | None = None):
        default_path = Path(__file__).resolve().parents[2] / "logs" / "llm_agent_trace.jsonl"
        self.path = path or Path(os.getenv("AGENT_TRACE_PATH", str(default_path)))
        self.payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "model": model,
            "user_query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
            "tool_calls": [],
            "tool_results": [],
            "success": False,
        }

    def add_call(self, name: str, arguments: dict[str, Any]) -> None:
        self.payload["tool_calls"].append({"tool": name, "arguments": _redact(arguments)})

    def add_result(self, name: str, result: dict[str, Any]) -> None:
        summary = {
            "tool": name,
            "count": result.get("count"),
            "total_matches": result.get("total_matches"),
            "status": result.get("status", "success"),
            "keys": sorted(result.keys()),
        }
        self.payload["tool_results"].append(summary)

    def finish(self, *, success: bool, latency_ms: float, error: str | None = None, usage: dict[str, Any] | None = None) -> None:
        self.payload["success"] = bool(success)
        self.payload["latency_ms"] = round(float(latency_ms), 2)
        if error:
            self.payload["error"] = str(error)[:200]
        if usage:
            self.payload["usage"] = _redact(usage)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_redact(self.payload), ensure_ascii=False) + "\n")
