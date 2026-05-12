from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.deps import get_assistant_service
from app.schemas import ChatRequest, ChatResponse, ErrorOut
from app.services.assistant import PortfolioAssistantService
from app.services.sse import SSE_HEADERS, format_sse

logger = logging.getLogger("portfolio-assistant.routes.chat")

router = APIRouter(tags=["chat"])


@router.post("/ask", response_model=ChatResponse, responses={400: {"model": ErrorOut}, 503: {"model": ErrorOut}})
@router.post("/chat", response_model=ChatResponse, include_in_schema=False)
async def ask(
    payload: ChatRequest,
    service: PortfolioAssistantService = Depends(get_assistant_service),
) -> ChatResponse | JSONResponse:
    request_id = uuid.uuid4().hex
    try:
        result = await service.answer(payload, request_id)
        return ChatResponse(**result)
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": str(exc), "id": request_id},
        )
    except RuntimeError as exc:
        logger.warning("Request %s failed with runtime error: %s", request_id, exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": str(exc), "id": request_id},
        )
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("Unhandled error while serving /ask request %s: %s", request_id, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Unexpected server error while generating the response.",
                "id": request_id,
            },
        )


@router.post("/ask/stream")
@router.post("/chat/stream", include_in_schema=False)
async def ask_stream(
    payload: ChatRequest,
    service: PortfolioAssistantService = Depends(get_assistant_service),
):
    request_id = uuid.uuid4().hex

    try:
        service.normalize_request(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    async def event_stream():
        try:
            async for chunk in service.stream_answer(payload, request_id):
                yield chunk
        except RuntimeError as exc:
            logger.warning("Streaming request %s failed: %s", request_id, exc)
            yield format_sse("error", {"id": request_id, "error": str(exc)})
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Unhandled streaming error for request %s: %s", request_id, exc)
            yield format_sse(
                "error",
                {
                    "id": request_id,
                    "error": "Unexpected server error while streaming the response.",
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
