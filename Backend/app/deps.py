from __future__ import annotations

from fastapi import Request

from app.config import Settings, get_settings as _get_settings
from app.services.assistant import PortfolioAssistantService


def get_settings() -> Settings:
    return _get_settings()


def get_assistant_service(request: Request) -> PortfolioAssistantService:
    service: PortfolioAssistantService | None = getattr(request.app.state, "assistant", None)
    if service is None:
        raise RuntimeError("Assistant service is not initialized yet.")
    return service


def get_app_version(request: Request) -> str:
    return getattr(request.app.state, "version", "0.0.0")
