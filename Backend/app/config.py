from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WebsitePreloadMode = Literal["background", "sync"]
OpenAITruncation = Literal["auto", "disabled"]


def _resolve_local_path(value: str) -> str:
    if not value:
        return value
    if os.path.isabs(value):
        return value
    return os.path.join(BASE_DIR, value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")
    allowed_models: list[str] = Field(default_factory=list, alias="ALLOWED_MODELS")
    openai_temperature: float = Field(default=0.2, alias="OPENAI_TEMPERATURE")
    openai_truncation: OpenAITruncation = Field(default="auto", alias="OPENAI_TRUNCATION")
    max_output_tokens: int = Field(default=450, alias="MAX_OUTPUT_TOKENS")
    request_timeout_seconds: int = Field(default=60, alias="REQUEST_TIMEOUT_SECONDS")

    # Data sources
    portfolio_path: str = Field(default="portfolio_data.xml", alias="PORTFOLIO_PATH")
    pdf_path_compat: str | None = Field(default=None, alias="PDF_PATH")
    instructions_path: str = Field(default="instructions.txt", alias="INSTRUCTIONS_PATH")
    source_url: str | None = Field(default=None, alias="SOURCE_URL")

    # Indexing
    enable_portfolio_preload: bool = Field(default=True, alias="ENABLE_PORTFOLIO_PRELOAD")
    enable_pdf_preload_compat: bool | None = Field(default=None, alias="ENABLE_PDF_PRELOAD")
    enable_website_preload: bool = Field(default=True, alias="ENABLE_WEBSITE_PRELOAD")
    website_preload_mode: WebsitePreloadMode = Field(default="background", alias="WEBSITE_PRELOAD_MODE")
    use_playwright: bool = Field(default=False, alias="USE_PLAYWRIGHT")
    max_web_pages: int = Field(default=15, alias="MAX_WEB_PAGES")

    # Chunking / retrieval
    chunk_size: int = Field(default=900, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=120, alias="CHUNK_OVERLAP")
    retriever_k: int = Field(default=4, alias="RETRIEVER_K")
    max_history_messages: int = Field(default=6, alias="MAX_HISTORY_MESSAGES")
    max_context_chars: int = Field(default=12000, alias="MAX_CONTEXT_CHARS")

    # HTTP
    cors_origins: list[str] = Field(default_factory=lambda: ["*"], alias="CORS_ORIGINS")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("allowed_models", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if value is None or isinstance(value, list):
            return value
        if isinstance(value, str):
            parts = [item.strip() for item in value.split(",") if item.strip()]
            return parts
        return value

    def resolved_portfolio_path(self) -> str:
        # PDF_PATH is the legacy env name; PORTFOLIO_PATH takes precedence if set explicitly.
        raw = self.portfolio_path or self.pdf_path_compat or "portfolio_data.xml"
        return _resolve_local_path(raw)

    def resolved_instructions_path(self) -> str:
        return _resolve_local_path(self.instructions_path)

    @property
    def effective_allowed_models(self) -> list[str]:
        if self.allowed_models:
            return self.allowed_models
        # Same default set the previous Flask version produced.
        default = self.openai_model
        return [default, "gpt-4o-mini", "gpt-4o"]

    @property
    def effective_enable_portfolio_preload(self) -> bool:
        # ENABLE_PDF_PRELOAD existed in the old config; honor it when the new
        # var is unset so deployments don't silently flip preload off.
        if "ENABLE_PORTFOLIO_PRELOAD" in os.environ:
            return self.enable_portfolio_preload
        if self.enable_pdf_preload_compat is not None:
            return self.enable_pdf_preload_compat
        return self.enable_portfolio_preload

    @property
    def trimmed_source_url(self) -> str | None:
        if not self.source_url:
            return None
        cleaned = self.source_url.strip()
        return cleaned or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
