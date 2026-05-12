from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ChatRole = Literal["user", "assistant"]


def _coerce_content(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        parts: list[str] = []
        for item in raw:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    parts.append(text)
                continue
            if isinstance(item, dict):
                text = str(item.get("text", "")).strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


class ChatMessageIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: ChatRole
    content: str

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        role_raw = str(data.get("role", data.get("user", ""))).strip().lower()
        content_raw = data.get("content", data.get("text", ""))
        return {
            "role": role_raw if role_raw in {"user", "assistant"} else "user",
            "content": _coerce_content(content_raw),
        }


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    prompt: str = ""
    messages: list[ChatMessageIn] = Field(default_factory=list, validation_alias="messages")
    history: list[ChatMessageIn] | None = None
    model: str | None = None
    session_id: str | None = None

    @model_validator(mode="after")
    def _merge_history(self) -> "ChatRequest":
        # Accept `history` as an alias for `messages`.
        if not self.messages and self.history:
            self.messages = self.history
        self.history = None
        return self


class SourceMeta(BaseModel):
    index: int
    title: str | None = None
    source_type: str | None = None
    url: str | None = None
    source_id: str | None = None
    preview: str = ""


class ChatResponse(BaseModel):
    id: str
    model: str
    response: str
    tokens: int = 0
    usage: dict[str, Any] | None = None
    source_count: int = 0
    sources: list[SourceMeta] = Field(default_factory=list)


class SourceStatusOut(BaseModel):
    enabled: bool
    loading: bool = False
    loaded: bool = False
    documents: int = 0
    chunks: int = 0
    error: str | None = None
    last_updated: float | None = None


class HealthOut(BaseModel):
    status: str = "ok"
    version: str
    ready: bool
    openai_api_key_configured: bool
    default_model: str
    allowed_models: list[str]
    source_url: str | None = None
    sources: dict[str, SourceStatusOut]


class RootOut(BaseModel):
    name: str
    version: str
    ready: bool
    endpoints: list[str]


class ErrorOut(BaseModel):
    error: str
    id: str | None = None
