from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI, OpenAI


def make_sync_client(api_key: str | None, timeout: float) -> OpenAI | None:
    if not api_key:
        return None
    return OpenAI(timeout=timeout)


def make_async_client(api_key: str | None, timeout: float) -> AsyncOpenAI | None:
    if not api_key:
        return None
    return AsyncOpenAI(timeout=timeout)


def response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    output = getattr(response, "output", None) or []
    collected: list[str] = []
    for item in output:
        content = getattr(item, "content", None) or []
        for part in content:
            part_type = getattr(part, "type", None)
            if part_type == "output_text":
                collected.append(getattr(part, "text", ""))
    return "".join(collected).strip()


def response_usage(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return usage
    return {
        key: getattr(usage, key)
        for key in ("input_tokens", "output_tokens", "total_tokens")
        if hasattr(usage, key)
    }
