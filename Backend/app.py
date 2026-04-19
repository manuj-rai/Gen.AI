from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS
from langchain.retrievers import EnsembleRetriever
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI

from web_loader import crawl_website_pages

load_dotenv()

BASE_DIR = os.path.dirname(__file__)
APP_VERSION = "2.0.0"
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


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("portfolio-assistant")


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        logger.warning("Invalid integer for %s=%r. Falling back to %s.", name, raw_value, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        logger.warning("Invalid float for %s=%r. Falling back to %s.", name, raw_value, default)
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw_value = os.getenv(name)
    values = default if raw_value is None else raw_value.split(",")
    cleaned = [value.strip() for value in values if value.strip()]
    return cleaned or default


def _resolve_local_path(env_name: str, fallback: str) -> str:
    raw_value = os.getenv(env_name, fallback)
    if os.path.isabs(raw_value):
        return raw_value
    return os.path.join(BASE_DIR, raw_value)


def _compact_text(value: str) -> str:
    return " ".join(value.split())


@dataclass(frozen=True)
class AppConfig:
    openai_api_key: str | None
    portfolio_path: str
    source_url: str | None
    instructions_path: str
    default_model: str
    allowed_models: list[str]
    cors_origins: list[str]
    enable_portfolio_preload: bool
    enable_website_preload: bool
    website_preload_mode: str
    use_playwright: bool
    max_web_pages: int
    chunk_size: int
    chunk_overlap: int
    retriever_k: int
    max_history_messages: int
    max_context_chars: int
    max_output_tokens: int
    temperature: float
    request_timeout_seconds: int
    openai_truncation: str


@dataclass
class SourceStatus:
    enabled: bool
    loading: bool = False
    loaded: bool = False
    documents: int = 0
    chunks: int = 0
    error: str | None = None
    last_updated: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "loading": self.loading,
            "loaded": self.loaded,
            "documents": self.documents,
            "chunks": self.chunks,
            "error": self.error,
            "last_updated": self.last_updated,
        }


@dataclass
class ChatRequestPayload:
    prompt: str
    messages: list[dict[str, str]]
    model: str
    session_id: str | None = None


def load_config() -> AppConfig:
    default_model = os.getenv("OPENAI_MODEL", "gpt-4o")
    allowed_models = _env_list("ALLOWED_MODELS", [default_model, "gpt-4o-mini", "gpt-4o"])
    website_preload_mode = os.getenv("WEBSITE_PRELOAD_MODE", "background").lower()
    if website_preload_mode not in {"background", "sync"}:
        logger.warning(
            "Unknown WEBSITE_PRELOAD_MODE=%r. Falling back to 'background'.",
            website_preload_mode,
        )
        website_preload_mode = "background"

    openai_truncation = os.getenv("OPENAI_TRUNCATION", "auto").lower()
    if openai_truncation not in {"auto", "disabled"}:
        logger.warning(
            "Unknown OPENAI_TRUNCATION=%r. Falling back to 'auto'.",
            openai_truncation,
        )
        openai_truncation = "auto"

    default_portfolio_preload = os.getenv("ENABLE_PDF_PRELOAD", "true")
    source_url = os.getenv("SOURCE_URL")

    return AppConfig(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        portfolio_path=_resolve_local_path("PORTFOLIO_PATH", os.getenv("PDF_PATH", "portfolio_data.xml")),
        source_url=source_url.strip() if source_url else None,
        instructions_path=_resolve_local_path("INSTRUCTIONS_PATH", "instructions.txt"),
        default_model=default_model,
        allowed_models=allowed_models,
        cors_origins=_env_list("CORS_ORIGINS", ["*"]),
        enable_portfolio_preload=_env_flag("ENABLE_PORTFOLIO_PRELOAD", default_portfolio_preload),
        enable_website_preload=_env_flag("ENABLE_WEBSITE_PRELOAD", "true"),
        website_preload_mode=website_preload_mode,
        use_playwright=_env_flag("USE_PLAYWRIGHT", "false"),
        max_web_pages=_env_int("MAX_WEB_PAGES", 15),
        chunk_size=_env_int("CHUNK_SIZE", 900),
        chunk_overlap=_env_int("CHUNK_OVERLAP", 120),
        retriever_k=_env_int("RETRIEVER_K", 4),
        max_history_messages=_env_int("MAX_HISTORY_MESSAGES", 6),
        max_context_chars=_env_int("MAX_CONTEXT_CHARS", 12000),
        max_output_tokens=_env_int("MAX_OUTPUT_TOKENS", 450),
        temperature=_env_float("OPENAI_TEMPERATURE", 0.2),
        request_timeout_seconds=_env_int("REQUEST_TIMEOUT_SECONDS", 60),
        openai_truncation=openai_truncation,
    )


def _node_to_text(node: ET.Element, depth: int = 0, lines: list[str] | None = None) -> str:
    target = lines if lines is not None else []
    label = node.tag.replace("_", " ").strip()
    content = _compact_text(node.text or "")
    indent = "  " * depth

    if content:
        target.append(f"{indent}{label}: {content}")
    else:
        target.append(f"{indent}{label}:")

    for child in node:
        _node_to_text(child, depth + 1, target)

    return "\n".join(line for line in target if line).strip()


class PortfolioAssistantService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.openai_client = (
            OpenAI(timeout=config.request_timeout_seconds)
            if config.openai_api_key
            else None
        )
        self.embeddings = (
            OpenAIEmbeddings()
            if config.openai_api_key
            else None
        )
        self.portfolio_vectorstore: FAISS | None = None
        self.web_vectorstore: FAISS | None = None
        self.system_instructions = DEFAULT_INSTRUCTIONS
        self.state_lock = threading.Lock()
        self.source_status: dict[str, SourceStatus] = {
            "portfolio": SourceStatus(enabled=config.enable_portfolio_preload),
            "website": SourceStatus(enabled=config.enable_website_preload),
        }

    def load_system_instructions(self) -> None:
        try:
            if os.path.exists(self.config.instructions_path):
                with open(self.config.instructions_path, "r", encoding="utf-8") as handle:
                    self.system_instructions = handle.read().strip() or DEFAULT_INSTRUCTIONS
                logger.info("Loaded instructions from %s", self.config.instructions_path)
            else:
                logger.warning(
                    "Instructions file not found at %s. Using built-in defaults.",
                    self.config.instructions_path,
                )
                self.system_instructions = DEFAULT_INSTRUCTIONS
        except Exception as exc:
            logger.exception("Failed to load instructions: %s", exc)
            self.system_instructions = DEFAULT_INSTRUCTIONS

    def _set_source_status(self, source_name: str, **updates: Any) -> None:
        with self.state_lock:
            status = self.source_status[source_name]
            for key, value in updates.items():
                setattr(status, key, value)
            status.last_updated = time.time()

    def _require_openai_setup(self) -> None:
        if not self.config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing.")
        if self.openai_client is None or self.embeddings is None:
            raise RuntimeError("OpenAI client is not initialized.")

    def load_portfolio_documents(self) -> list[Document]:
        xml_path = self.config.portfolio_path
        if not os.path.exists(xml_path):
            raise FileNotFoundError(f"Portfolio data file not found: {xml_path}")

        tree = ET.parse(xml_path)
        root = tree.getroot()
        documents: list[Document] = []

        for child in root:
            section_name = child.tag.replace("_", " ").strip()
            section_text = _node_to_text(child)
            if not section_text:
                continue

            documents.append(
                Document(
                    page_content=section_text,
                    metadata={
                        "source_type": "portfolio_xml",
                        "source_id": f"portfolio:{child.tag}",
                        "title": f"Portfolio XML - {section_name.title()}",
                        "url": None,
                    },
                )
            )

        if not documents:
            raise RuntimeError("Portfolio XML was parsed but no usable text was found.")

        return documents

    def build_vector_store(self, documents: list[Document]) -> tuple[FAISS, int]:
        self._require_openai_setup()
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )
        chunks = splitter.split_documents(documents)
        if not chunks:
            raise RuntimeError("No text chunks were produced for indexing.")
        vectorstore = FAISS.from_documents(chunks, embedding=self.embeddings)
        return vectorstore, len(chunks)

    def preload_portfolio_data(self) -> None:
        self._set_source_status("portfolio", loading=True, error=None)
        try:
            documents = self.load_portfolio_documents()
            vectorstore, chunk_count = self.build_vector_store(documents)
            self.portfolio_vectorstore = vectorstore
            self._set_source_status(
                "portfolio",
                loading=False,
                loaded=True,
                documents=len(documents),
                chunks=chunk_count,
                error=None,
            )
            logger.info("Portfolio data indexed: %s documents, %s chunks", len(documents), chunk_count)
        except Exception as exc:
            logger.exception("Failed to preload portfolio data: %s", exc)
            self._set_source_status(
                "portfolio",
                loading=False,
                loaded=False,
                documents=0,
                chunks=0,
                error=str(exc),
            )

    def preload_website_data(self) -> None:
        if not self.config.source_url:
            self._set_source_status(
                "website",
                loading=False,
                loaded=False,
                error="SOURCE_URL is not configured.",
            )
            return

        self._set_source_status("website", loading=True, error=None)
        try:
            pages = crawl_website_pages(
                self.config.source_url,
                max_pages=self.config.max_web_pages,
                use_playwright=self.config.use_playwright,
            )
            documents = [
                Document(
                    page_content=page.text,
                    metadata={
                        "source_type": "website",
                        "source_id": page.url,
                        "title": page.title or page.url,
                        "url": page.url,
                    },
                )
                for page in pages
                if page.text
            ]

            if not documents:
                raise RuntimeError("Website crawl completed but no usable HTML text was collected.")

            vectorstore, chunk_count = self.build_vector_store(documents)
            self.web_vectorstore = vectorstore
            self._set_source_status(
                "website",
                loading=False,
                loaded=True,
                documents=len(documents),
                chunks=chunk_count,
                error=None,
            )
            logger.info("Website data indexed: %s pages, %s chunks", len(documents), chunk_count)
        except Exception as exc:
            logger.exception("Failed to preload website data: %s", exc)
            self._set_source_status(
                "website",
                loading=False,
                loaded=False,
                documents=0,
                chunks=0,
                error=str(exc),
            )

    def load_startup_sources(self) -> None:
        logger.info("Starting Portfolio Assistant API version %s", APP_VERSION)
        self.load_system_instructions()

        if self.config.enable_portfolio_preload:
            self.preload_portfolio_data()
        else:
            logger.info("Portfolio preload disabled.")

        if self.config.enable_website_preload:
            if self.config.website_preload_mode == "background":
                logger.info("Website preload running in the background.")
                thread = threading.Thread(
                    target=self.preload_website_data,
                    name="website-preload",
                    daemon=True,
                )
                thread.start()
            else:
                self.preload_website_data()
        else:
            logger.info("Website preload disabled.")

    def has_ready_source(self) -> bool:
        return self.portfolio_vectorstore is not None or self.web_vectorstore is not None

    def is_ready(self) -> bool:
        return bool(self.config.openai_api_key) and self.has_ready_source()

    def ensure_sources_ready(self) -> None:
        if self.has_ready_source():
            return

        logger.info("No ready knowledge source found. Attempting synchronous warm-up.")
        if self.config.enable_portfolio_preload and self.portfolio_vectorstore is None:
            self.preload_portfolio_data()

        if not self.has_ready_source() and self.config.enable_website_preload and self.web_vectorstore is None:
            self.preload_website_data()

        if not self.has_ready_source():
            raise RuntimeError("Knowledge sources are still warming up or failed to load.")

    def health_snapshot(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": APP_VERSION,
            "ready": self.is_ready(),
            "openai_api_key_configured": bool(self.config.openai_api_key),
            "default_model": self.config.default_model,
            "allowed_models": self.config.allowed_models,
            "source_url": self.config.source_url,
            "sources": {
                source_name: status.as_dict()
                for source_name, status in self.source_status.items()
            },
        }

    def _validate_model(self, model_name: str) -> str:
        requested_model = model_name.strip() if model_name else self.config.default_model
        if requested_model not in self.config.allowed_models:
            raise ValueError(
                f"Invalid model '{requested_model}'. Allowed models: {', '.join(self.config.allowed_models)}"
            )
        return requested_model

    def _coerce_message_text(self, raw_content: Any) -> str:
        if isinstance(raw_content, str):
            return raw_content.strip()
        if isinstance(raw_content, list):
            parts: list[str] = []
            for item in raw_content:
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

    def normalize_messages(self, raw_messages: Any) -> list[dict[str, str]]:
        if not isinstance(raw_messages, list):
            return []

        normalized: list[dict[str, str]] = []
        for item in raw_messages[-self.config.max_history_messages :]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", item.get("user", ""))).strip().lower()
            if role not in {"user", "assistant"}:
                continue
            content = self._coerce_message_text(item.get("content", item.get("text", "")))
            if content:
                normalized.append({"role": role, "content": content})
        return normalized

    def parse_chat_request(self, body: dict[str, Any]) -> ChatRequestPayload:
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")

        prompt = str(body.get("prompt", "") or "").strip()
        messages = self.normalize_messages(body.get("messages") or body.get("history") or [])

        if prompt:
            history = messages
        elif messages and messages[-1]["role"] == "user":
            prompt = messages[-1]["content"]
            history = messages[:-1]
        else:
            history = messages

        if not prompt:
            raise ValueError("Prompt is required. Provide 'prompt' or end 'messages' with a user message.")

        model = self._validate_model(str(body.get("model", self.config.default_model) or self.config.default_model))
        session_id = str(body.get("session_id", "") or "").strip() or None
        return ChatRequestPayload(prompt=prompt, messages=history, model=model, session_id=session_id)

    def _get_retriever(self):
        retrievers = []
        if self.portfolio_vectorstore is not None:
            retrievers.append(
                self.portfolio_vectorstore.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": self.config.retriever_k},
                )
            )
        if self.web_vectorstore is not None:
            retrievers.append(
                self.web_vectorstore.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": self.config.retriever_k},
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
        if hasattr(retriever, "invoke"):
            documents = retriever.invoke(prompt)
        else:
            documents = retriever.get_relevant_documents(prompt)

        unique_documents: list[Document] = []
        seen: set[tuple[str, str]] = set()
        for document in documents:
            source_id = str(document.metadata.get("source_id", "unknown"))
            fingerprint = (source_id, document.page_content)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            unique_documents.append(document)
        return unique_documents

    def format_context(self, documents: list[Document]) -> str:
        blocks: list[str] = []
        current_size = 0

        for index, document in enumerate(documents, start=1):
            title = document.metadata.get("title") or document.metadata.get("source_id") or f"Source {index}"
            location = document.metadata.get("url") or document.metadata.get("source_id") or "unknown"
            block = f"[Source {index}] {title}\nLocation: {location}\n{document.page_content.strip()}".strip()

            if blocks and current_size + len(block) > self.config.max_context_chars:
                break

            blocks.append(block)
            current_size += len(block)

        return "\n\n".join(blocks).strip()

    def format_sources(self, documents: list[Document]) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        for index, document in enumerate(documents, start=1):
            page_content = document.page_content.strip()
            preview = page_content[:220]
            sources.append(
                {
                    "index": index,
                    "title": document.metadata.get("title") or document.metadata.get("source_id"),
                    "source_type": document.metadata.get("source_type"),
                    "url": document.metadata.get("url"),
                    "source_id": document.metadata.get("source_id"),
                    "preview": preview,
                }
            )
        return sources

    def _build_grounded_prompt(self, prompt: str, context: str) -> str:
        return (
            "Use the verified portfolio context below to answer the visitor.\n"
            "If the answer is not supported by the context, say you do not have confirmed information yet.\n"
            "Never pretend to be Manuj. You are his assistant.\n\n"
            f"Verified context:\n{context}\n\n"
            f"Visitor question:\n{prompt}"
        )

    def build_input_items(self, prompt: str, messages: list[dict[str, str]], context: str) -> list[dict[str, Any]]:
        input_items: list[dict[str, Any]] = []
        for message in messages[-self.config.max_history_messages :]:
            input_items.append(
                {
                    "role": message["role"],
                    "content": [{"type": "input_text", "text": message["content"]}],
                }
            )
        input_items.append(
            {
                "role": "user",
                "content": [{"type": "input_text", "text": self._build_grounded_prompt(prompt, context)}],
            }
        )
        return input_items

    def build_openai_request(
        self,
        chat_request: ChatRequestPayload,
        request_id: str,
        context: str,
        stream: bool,
    ) -> dict[str, Any]:
        self._require_openai_setup()
        metadata = {"request_id": request_id, "app": "portfolio-assistant"}
        if chat_request.session_id:
            metadata["session_id"] = chat_request.session_id[:64]

        return {
            "model": chat_request.model,
            "instructions": self.system_instructions,
            "input": self.build_input_items(chat_request.prompt, chat_request.messages, context),
            "temperature": self.config.temperature,
            "max_output_tokens": self.config.max_output_tokens,
            "store": False,
            "truncation": self.config.openai_truncation,
            "metadata": metadata,
            "stream": stream,
        }

    def _response_usage(self, response: Any) -> dict[str, Any] | None:
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

    def _response_text(self, response: Any) -> str:
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

    def answer(self, chat_request: ChatRequestPayload, request_id: str) -> dict[str, Any]:
        documents = self.retrieve_documents(chat_request.prompt)
        context = self.format_context(documents)
        sources = self.format_sources(documents)

        openai_response = self.openai_client.responses.create(
            **self.build_openai_request(chat_request, request_id, context, stream=False)
        )
        answer_text = self._response_text(openai_response).strip()
        usage = self._response_usage(openai_response)
        total_tokens = int((usage or {}).get("total_tokens", 0))

        if not answer_text:
            answer_text = "I do not have confirmed information for that yet."

        return {
            "id": request_id,
            "model": chat_request.model,
            "response": answer_text,
            "tokens": total_tokens,
            "usage": usage,
            "source_count": len(sources),
            "sources": sources,
        }

    def _sse(self, event_name: str, data: dict[str, Any]) -> str:
        return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def stream_answer(self, chat_request: ChatRequestPayload, request_id: str):
        documents = self.retrieve_documents(chat_request.prompt)
        context = self.format_context(documents)
        sources = self.format_sources(documents)

        yield self._sse(
            "meta",
            {
                "id": request_id,
                "model": chat_request.model,
                "source_count": len(sources),
                "sources": sources,
            },
        )

        stream = self.openai_client.responses.create(
            **self.build_openai_request(chat_request, request_id, context, stream=True)
        )
        collected_text: list[str] = []
        final_response = None

        try:
            for event in stream:
                event_type = getattr(event, "type", "")

                if event_type == "response.output_text.delta":
                    delta = getattr(event, "delta", "")
                    if delta:
                        collected_text.append(delta)
                        yield self._sse("delta", {"id": request_id, "text": delta})
                    continue

                if event_type == "response.completed":
                    final_response = event.response
                    continue

                if event_type == "response.incomplete":
                    final_response = event.response
                    continue

                if event_type == "response.failed":
                    final_response = event.response
                    error_message = getattr(getattr(final_response, "error", None), "message", None)
                    raise RuntimeError(error_message or "OpenAI response failed.")

            response_text = "".join(collected_text).strip()
            usage = None
            response_status = "completed"

            if final_response is not None:
                response_text = self._response_text(final_response).strip() or response_text
                usage = self._response_usage(final_response)
                response_status = getattr(final_response, "status", "completed")

            if not response_text:
                response_text = "I do not have confirmed information for that yet."

            yield self._sse(
                "done",
                {
                    "id": request_id,
                    "model": chat_request.model,
                    "status": response_status,
                    "response": response_text,
                    "tokens": int((usage or {}).get("total_tokens", 0)),
                    "usage": usage,
                    "source_count": len(sources),
                    "sources": sources,
                },
            )
        finally:
            stream.close()


CONFIG = load_config()
assistant_service = PortfolioAssistantService(CONFIG)

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

if CONFIG.cors_origins == ["*"]:
    CORS(app)
else:
    CORS(app, resources={r"/*": {"origins": CONFIG.cors_origins}})


def error_response(message: str, status_code: int, request_id: str | None = None):
    payload = {"error": message}
    if request_id:
        payload["id"] = request_id
    return jsonify(payload), status_code


@app.get("/")
def home():
    return jsonify(
        {
            "name": "Manuj AI Assistant API",
            "version": APP_VERSION,
            "ready": assistant_service.is_ready(),
            "endpoints": ["/health", "/ready", "/ask", "/ask/stream"],
        }
    )


@app.get("/health")
def health():
    return jsonify(assistant_service.health_snapshot())


@app.get("/ready")
def ready():
    snapshot = assistant_service.health_snapshot()
    status_code = 200 if snapshot["ready"] else 503
    return jsonify(snapshot), status_code


@app.post("/ask")
@app.post("/chat")
def ask():
    request_id = uuid.uuid4().hex

    try:
        body = request.get_json(silent=True) or {}
        chat_request = assistant_service.parse_chat_request(body)
        result = assistant_service.answer(chat_request, request_id)
        return jsonify(result)
    except ValueError as exc:
        return error_response(str(exc), 400, request_id)
    except RuntimeError as exc:
        logger.warning("Request %s failed with runtime error: %s", request_id, exc)
        return error_response(str(exc), 503, request_id)
    except Exception as exc:
        logger.exception("Unhandled error while serving /ask request %s: %s", request_id, exc)
        return error_response("Unexpected server error while generating the response.", 500, request_id)


@app.post("/ask/stream")
@app.post("/chat/stream")
def ask_stream():
    request_id = uuid.uuid4().hex

    try:
        body = request.get_json(silent=True) or {}
        chat_request = assistant_service.parse_chat_request(body)
    except ValueError as exc:
        return error_response(str(exc), 400, request_id)

    def generate():
        try:
            yield from assistant_service.stream_answer(chat_request, request_id)
        except RuntimeError as exc:
            logger.warning("Streaming request %s failed: %s", request_id, exc)
            yield assistant_service._sse("error", {"id": request_id, "error": str(exc)})
        except Exception as exc:
            logger.exception("Unhandled streaming error for request %s: %s", request_id, exc)
            yield assistant_service._sse(
                "error",
                {
                    "id": request_id,
                    "error": "Unexpected server error while streaming the response.",
                },
            )

    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"
    return response


assistant_service.load_startup_sources()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
