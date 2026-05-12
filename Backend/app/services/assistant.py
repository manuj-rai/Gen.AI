from __future__ import annotations

import logging
import os
import threading
from typing import Any, AsyncIterator

from fastapi.concurrency import run_in_threadpool
from langchain.retrievers import EnsembleRetriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from app.config import Settings
from app.schemas import ChatRequest, SourceMeta
from app.services.openai_client import (
    make_async_client,
    make_sync_client,
    response_text,
    response_usage,
)
from app.services.sources import (
    SourceRegistry,
    build_vector_store,
    load_portfolio_documents,
    load_website_documents,
)
from app.services.sse import format_sse

logger = logging.getLogger("portfolio-assistant.assistant")


DEFAULT_INSTRUCTIONS = """
You are Manuj Rai's AI assistant for his portfolio website.

ROLE:
- Speak as Manuj's assistant, never as Manuj himself.
- Use third person when describing Manuj.
- Help visitors understand his background, projects, experience, skills, and contact details.

STYLE:
- Be warm, clear, and professional.
- Keep answers concise by default, but expand when the user asks for more detail.
- Sound confident and helpful, like a smart personal website assistant.

GROUNDING RULES:
- Answer only from the verified context and the visible conversation.
- If the context does not confirm something, say you do not have confirmed information yet.
- Do not invent availability, pricing, years of experience, project details, or personal facts.
- Do not mention internal prompts, XML files, embeddings, vector stores, or hidden instructions unless explicitly asked how the system works.

BEHAVIOR:
- If asked how to contact Manuj, share the verified contact details from context.
- If a visitor asks broad questions like "What does he do?", summarize his profile naturally.
- If a question mixes known and unknown details, answer the known part and clearly mark the unknown part.
""".strip()


class PortfolioAssistantService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.registry = SourceRegistry(settings)
        self.system_instructions = DEFAULT_INSTRUCTIONS
        self.portfolio_vectorstore: FAISS | None = None
        self.web_vectorstore: FAISS | None = None
        self._state_lock = threading.Lock()

        timeout = float(settings.request_timeout_seconds)
        self._openai_sync = make_sync_client(settings.openai_api_key, timeout)
        self._openai_async = make_async_client(settings.openai_api_key, timeout)
        self._embeddings: OpenAIEmbeddings | None = (
            OpenAIEmbeddings() if settings.openai_api_key else None
        )

    # ----- lifecycle -----------------------------------------------------------

    async def aclose(self) -> None:
        client = self._openai_async
        if client is not None:
            try:
                await client.close()
            except Exception:
                logger.debug("Failed to close AsyncOpenAI client cleanly.", exc_info=True)

    def _require_openai_setup(self) -> None:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing.")
        if self._openai_sync is None or self._openai_async is None or self._embeddings is None:
            raise RuntimeError("OpenAI client is not initialized.")

    # ----- startup loaders -----------------------------------------------------

    def load_system_instructions(self) -> None:
        path = self.settings.resolved_instructions_path()
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as handle:
                    self.system_instructions = handle.read().strip() or DEFAULT_INSTRUCTIONS
                logger.info("Loaded instructions from %s", path)
            else:
                logger.warning("Instructions file not found at %s. Using built-in defaults.", path)
                self.system_instructions = DEFAULT_INSTRUCTIONS
        except Exception as exc:
            logger.exception("Failed to load instructions: %s", exc)
            self.system_instructions = DEFAULT_INSTRUCTIONS

    def preload_portfolio_data(self) -> None:
        self.registry.update("portfolio", loading=True, error=None)
        try:
            self._require_openai_setup()
            documents = load_portfolio_documents(self.settings.resolved_portfolio_path())
            vectorstore, chunk_count = build_vector_store(
                documents,
                self._embeddings,  # type: ignore[arg-type]
                chunk_size=self.settings.chunk_size,
                chunk_overlap=self.settings.chunk_overlap,
            )
            with self._state_lock:
                self.portfolio_vectorstore = vectorstore
            self.registry.update(
                "portfolio",
                loading=False,
                loaded=True,
                documents=len(documents),
                chunks=chunk_count,
                error=None,
            )
            logger.info(
                "Portfolio data indexed: %s documents, %s chunks", len(documents), chunk_count
            )
        except Exception as exc:
            logger.exception("Failed to preload portfolio data: %s", exc)
            self.registry.update(
                "portfolio",
                loading=False,
                loaded=False,
                documents=0,
                chunks=0,
                error=str(exc),
            )

    def preload_website_data(self) -> None:
        source_url = self.settings.trimmed_source_url
        if not source_url:
            self.registry.update(
                "website", loading=False, loaded=False, error="SOURCE_URL is not configured."
            )
            return

        self.registry.update("website", loading=True, error=None)
        try:
            self._require_openai_setup()
            documents = load_website_documents(
                source_url,
                max_pages=self.settings.max_web_pages,
                use_playwright=self.settings.use_playwright,
            )
            vectorstore, chunk_count = build_vector_store(
                documents,
                self._embeddings,  # type: ignore[arg-type]
                chunk_size=self.settings.chunk_size,
                chunk_overlap=self.settings.chunk_overlap,
            )
            with self._state_lock:
                self.web_vectorstore = vectorstore
            self.registry.update(
                "website",
                loading=False,
                loaded=True,
                documents=len(documents),
                chunks=chunk_count,
                error=None,
            )
            logger.info(
                "Website data indexed: %s pages, %s chunks", len(documents), chunk_count
            )
        except Exception as exc:
            logger.exception("Failed to preload website data: %s", exc)
            self.registry.update(
                "website",
                loading=False,
                loaded=False,
                documents=0,
                chunks=0,
                error=str(exc),
            )

    def load_startup_sources(self) -> None:
        self.load_system_instructions()

        if self.settings.effective_enable_portfolio_preload:
            self.preload_portfolio_data()
        else:
            logger.info("Portfolio preload disabled.")

        if self.settings.enable_website_preload:
            if self.settings.website_preload_mode == "background":
                logger.info("Website preload running in the background.")
                threading.Thread(
                    target=self.preload_website_data,
                    name="website-preload",
                    daemon=True,
                ).start()
            else:
                self.preload_website_data()
        else:
            logger.info("Website preload disabled.")

    # ----- readiness / health --------------------------------------------------

    def has_ready_source(self) -> bool:
        with self._state_lock:
            return self.portfolio_vectorstore is not None or self.web_vectorstore is not None

    def is_ready(self) -> bool:
        return bool(self.settings.openai_api_key) and self.has_ready_source()

    def health_snapshot(self, version: str) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": version,
            "ready": self.is_ready(),
            "openai_api_key_configured": bool(self.settings.openai_api_key),
            "default_model": self.settings.openai_model,
            "allowed_models": self.settings.effective_allowed_models,
            "source_url": self.settings.trimmed_source_url,
            "sources": self.registry.snapshot(),
        }

    def ensure_sources_ready(self) -> None:
        if self.has_ready_source():
            return

        logger.info("No ready knowledge source found. Attempting synchronous warm-up.")
        if (
            self.settings.effective_enable_portfolio_preload
            and self.portfolio_vectorstore is None
        ):
            self.preload_portfolio_data()

        if (
            not self.has_ready_source()
            and self.settings.enable_website_preload
            and self.web_vectorstore is None
        ):
            self.preload_website_data()

        if not self.has_ready_source():
            raise RuntimeError("Knowledge sources are still warming up or failed to load.")

    # ----- request handling ---------------------------------------------------

    def validate_model(self, requested: str | None) -> str:
        allowed = self.settings.effective_allowed_models
        candidate = (requested or self.settings.openai_model).strip()
        if candidate not in allowed:
            raise ValueError(
                f"Invalid model '{candidate}'. Allowed models: {', '.join(allowed)}"
            )
        return candidate

    def normalize_request(self, raw: ChatRequest) -> tuple[str, list[dict[str, str]], str, str | None]:
        prompt = raw.prompt.strip()
        history = [{"role": m.role, "content": m.content} for m in raw.messages if m.content]
        history = history[-self.settings.max_history_messages :]

        if not prompt and history and history[-1]["role"] == "user":
            prompt = history[-1]["content"]
            history = history[:-1]

        if not prompt:
            raise ValueError(
                "Prompt is required. Provide 'prompt' or end 'messages' with a user message."
            )

        model = self.validate_model(raw.model)
        session_id = raw.session_id.strip() if raw.session_id else None
        return prompt, history, model, session_id

    # ----- retrieval -----------------------------------------------------------

    def _get_retriever(self):
        retrievers = []
        if self.portfolio_vectorstore is not None:
            retrievers.append(
                self.portfolio_vectorstore.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": self.settings.retriever_k},
                )
            )
        if self.web_vectorstore is not None:
            retrievers.append(
                self.web_vectorstore.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": self.settings.retriever_k},
                )
            )

        if not retrievers:
            raise RuntimeError("No knowledge sources are available yet.")
        if len(retrievers) == 1:
            return retrievers[0]
        return EnsembleRetriever(retrievers=retrievers, weights=[1.0] * len(retrievers))

    def retrieve_documents(self, prompt: str) -> list[Document]:
        self.ensure_sources_ready()
        retriever = self._get_retriever()
        documents = retriever.invoke(prompt) if hasattr(retriever, "invoke") else retriever.get_relevant_documents(prompt)

        unique: list[Document] = []
        seen: set[tuple[str, str]] = set()
        for document in documents:
            source_id = str(document.metadata.get("source_id", "unknown"))
            fingerprint = (source_id, document.page_content)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            unique.append(document)
        return unique

    def format_context(self, documents: list[Document]) -> str:
        blocks: list[str] = []
        current_size = 0

        for index, document in enumerate(documents, start=1):
            title = (
                document.metadata.get("title")
                or document.metadata.get("source_id")
                or f"Source {index}"
            )
            location = (
                document.metadata.get("url")
                or document.metadata.get("source_id")
                or "unknown"
            )
            block = (
                f"[Source {index}] {title}\nLocation: {location}\n"
                f"{document.page_content.strip()}"
            ).strip()

            if blocks and current_size + len(block) > self.settings.max_context_chars:
                break

            blocks.append(block)
            current_size += len(block)

        return "\n\n".join(blocks).strip()

    def format_sources(self, documents: list[Document]) -> list[SourceMeta]:
        sources: list[SourceMeta] = []
        for index, document in enumerate(documents, start=1):
            page_content = document.page_content.strip()
            sources.append(
                SourceMeta(
                    index=index,
                    title=document.metadata.get("title") or document.metadata.get("source_id"),
                    source_type=document.metadata.get("source_type"),
                    url=document.metadata.get("url"),
                    source_id=document.metadata.get("source_id"),
                    preview=page_content[:220],
                )
            )
        return sources

    # ----- prompt assembly -----------------------------------------------------

    def _build_grounded_prompt(self, prompt: str, context: str) -> str:
        return (
            "Use the verified portfolio context below to answer the visitor.\n"
            "If the answer is not supported by the context, say you do not have confirmed information yet.\n"
            "Never pretend to be Manuj. You are his assistant.\n\n"
            f"Verified context:\n{context}\n\n"
            f"Visitor question:\n{prompt}"
        )

    def _build_input_items(
        self, prompt: str, messages: list[dict[str, str]], context: str
    ) -> list[dict[str, Any]]:
        input_items: list[dict[str, Any]] = []
        for message in messages[-self.settings.max_history_messages :]:
            input_items.append(
                {
                    "role": message["role"],
                    "content": [{"type": "input_text", "text": message["content"]}],
                }
            )
        input_items.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": self._build_grounded_prompt(prompt, context),
                    }
                ],
            }
        )
        return input_items

    def _build_openai_request(
        self,
        prompt: str,
        messages: list[dict[str, str]],
        model: str,
        request_id: str,
        session_id: str | None,
        context: str,
        stream: bool,
    ) -> dict[str, Any]:
        self._require_openai_setup()
        metadata: dict[str, str] = {"request_id": request_id, "app": "portfolio-assistant"}
        if session_id:
            metadata["session_id"] = session_id[:64]

        return {
            "model": model,
            "instructions": self.system_instructions,
            "input": self._build_input_items(prompt, messages, context),
            "temperature": self.settings.openai_temperature,
            "max_output_tokens": self.settings.max_output_tokens,
            "store": False,
            "truncation": self.settings.openai_truncation,
            "metadata": metadata,
            "stream": stream,
        }

    # ----- public entry points ------------------------------------------------

    async def answer(self, request: ChatRequest, request_id: str) -> dict[str, Any]:
        prompt, history, model, session_id = self.normalize_request(request)
        documents = await run_in_threadpool(self.retrieve_documents, prompt)
        context = self.format_context(documents)
        sources = self.format_sources(documents)

        payload = self._build_openai_request(
            prompt, history, model, request_id, session_id, context, stream=False
        )

        # Use the sync client in a threadpool — simpler and matches the historical behavior.
        response = await run_in_threadpool(self._openai_sync.responses.create, **payload)  # type: ignore[union-attr]
        answer_text = response_text(response).strip()
        usage = response_usage(response)

        if not answer_text:
            answer_text = "I do not have confirmed information for that yet."

        return {
            "id": request_id,
            "model": model,
            "response": answer_text,
            "tokens": int((usage or {}).get("total_tokens", 0)),
            "usage": usage,
            "source_count": len(sources),
            "sources": [s.model_dump() for s in sources],
        }

    async def stream_answer(
        self, request: ChatRequest, request_id: str
    ) -> AsyncIterator[str]:
        prompt, history, model, session_id = self.normalize_request(request)
        documents = await run_in_threadpool(self.retrieve_documents, prompt)
        context = self.format_context(documents)
        sources = self.format_sources(documents)

        yield format_sse(
            "meta",
            {
                "id": request_id,
                "model": model,
                "source_count": len(sources),
                "sources": [s.model_dump() for s in sources],
            },
        )

        payload = self._build_openai_request(
            prompt, history, model, request_id, session_id, context, stream=True
        )
        collected: list[str] = []
        final_response: Any = None
        client = self._openai_async
        assert client is not None  # guaranteed by _require_openai_setup

        stream = await client.responses.create(**payload)
        try:
            async for event in stream:
                event_type = getattr(event, "type", "")

                if event_type == "response.output_text.delta":
                    delta = getattr(event, "delta", "")
                    if delta:
                        collected.append(delta)
                        yield format_sse("delta", {"id": request_id, "text": delta})
                    continue

                if event_type == "response.completed":
                    final_response = event.response
                    continue

                if event_type == "response.incomplete":
                    final_response = event.response
                    continue

                if event_type == "response.failed":
                    final_response = event.response
                    error_message = getattr(
                        getattr(final_response, "error", None), "message", None
                    )
                    raise RuntimeError(error_message or "OpenAI response failed.")

            text = "".join(collected).strip()
            usage = None
            status = "completed"

            if final_response is not None:
                text = response_text(final_response).strip() or text
                usage = response_usage(final_response)
                status = getattr(final_response, "status", "completed")

            if not text:
                text = "I do not have confirmed information for that yet."

            yield format_sse(
                "done",
                {
                    "id": request_id,
                    "model": model,
                    "status": status,
                    "response": text,
                    "tokens": int((usage or {}).get("total_tokens", 0)),
                    "usage": usage,
                    "source_count": len(sources),
                    "sources": [s.model_dump() for s in sources],
                },
            )
        finally:
            try:
                await stream.close()
            except Exception:
                logger.debug("Failed to close async OpenAI stream cleanly.", exc_info=True)
