from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.deps import get_app_version, get_assistant_service
from app.schemas import HealthOut, RootOut
from app.services.assistant import PortfolioAssistantService

router = APIRouter(tags=["health"])

ENDPOINTS = ["/health", "/ready", "/ask", "/ask/stream"]


@router.get("/", response_model=RootOut)
async def root(
    service: PortfolioAssistantService = Depends(get_assistant_service),
    version: str = Depends(get_app_version),
) -> RootOut:
    return RootOut(
        name="Manuj AI Assistant API",
        version=version,
        ready=service.is_ready(),
        endpoints=ENDPOINTS,
    )


@router.get("/health", response_model=HealthOut)
async def health(
    service: PortfolioAssistantService = Depends(get_assistant_service),
    version: str = Depends(get_app_version),
) -> HealthOut:
    return HealthOut(**service.health_snapshot(version))


@router.get("/ready", response_model=HealthOut)
async def ready(
    response: Response,
    service: PortfolioAssistantService = Depends(get_assistant_service),
    version: str = Depends(get_app_version),
) -> HealthOut:
    snapshot = service.health_snapshot(version)
    if not snapshot["ready"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthOut(**snapshot)
