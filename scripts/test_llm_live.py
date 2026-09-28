"""One-request live connectivity probe. Never run without explicit approval."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND = APP_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from local_env import load_local_env
from llm.providers import get_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal paid LLM connectivity test")
    parser.add_argument("--provider", required=True, choices=["openai", "deepseek"])
    parser.add_argument("--confirm-live", action="store_true", help="Required acknowledgement that this makes one paid API request")
    args = parser.parse_args()
    if not args.confirm_live:
        parser.error("--confirm-live is required; no request was sent")

    load_local_env()
    provider = get_provider(args.provider)
    turn = provider.generate(
        instructions="ตอบสั้นและไม่เรียกเครื่องมือ นี่เป็นการทดสอบการเชื่อมต่อเท่านั้น",
        input_items=[{"role": "user", "content": [{"type": "input_text", "text": "ตอบเพียงคำว่า OK"}]}],
        tools=[],
    )
    if not turn.text.strip():
        raise RuntimeError("Provider connected but returned no text")
    print(f"PASS provider={provider.provider_name} model={provider.model_name} response_received=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
