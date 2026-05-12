from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.logging_setup import configure_logging
from app.routers import chat as chat_router
from app.routers import health as health_router
from app.services.assistant import PortfolioAssistantService

APP_VERSION = "2.1.0"

logger = logging.getLogger("portfolio-assistant")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Starting Portfolio Assistant API version %s", APP_VERSION)

    service = PortfolioAssistantService(settings)
    app.state.assistant = service
    app.state.settings = settings
    app.state.version = APP_VERSION

    # FAISS build is CPU-bound — keep the event loop free.
    await run_in_threadpool(service.load_startup_sources)

    try:
        yield
    finally:
        await service.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Manuj AI Assistant API",
        version=APP_VERSION,
        description="RAG chatbot grounded in Manuj Rai's portfolio.",
        lifespan=lifespan,
    )

    origins = settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router.router)
    app.include_router(chat_router.router)

    return app
