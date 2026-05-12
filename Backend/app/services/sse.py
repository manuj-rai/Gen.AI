from __future__ import annotations

import json
from typing import Any


def format_sse(event_name: str, data: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    # Tell Render's proxy not to buffer — required for token-by-token streaming.
    "X-Accel-Buffering": "no",
}
