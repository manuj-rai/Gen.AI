from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from app.config import Settings
from app.web_loader import crawl_website_pages

logger = logging.getLogger("portfolio-assistant.sources")


def _compact_text(value: str) -> str:
    return " ".join(value.split())


def _node_to_text(node: ET.Element, depth: int = 0, lines: list[str] | None = None) -> str:
    target = lines if lines is not None else []
    label = node.tag.replace("_", " ").strip()
    content = _compact_text(node.text or "")
    indent = "  " * depth

    target.append(f"{indent}{label}: {content}" if content else f"{indent}{label}:")
    for child in node:
        _node_to_text(child, depth + 1, target)
    return "\n".join(line for line in target if line).strip()


def load_portfolio_documents(xml_path: str) -> list[Document]:
    import os

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


def build_vector_store(
    documents: list[Document],
    embeddings: OpenAIEmbeddings,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[FAISS, int]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_documents(documents)
    if not chunks:
        raise RuntimeError("No text chunks were produced for indexing.")
    vectorstore = FAISS.from_documents(chunks, embedding=embeddings)
    return vectorstore, len(chunks)


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


class SourceRegistry:
    """Thread-safe registry tracking ingestion state for each knowledge source."""

    def __init__(self, settings: Settings) -> None:
        self._lock = threading.Lock()
        self._statuses: dict[str, SourceStatus] = {
            "portfolio": SourceStatus(enabled=settings.effective_enable_portfolio_preload),
            "website": SourceStatus(enabled=settings.enable_website_preload),
        }

    def update(self, name: str, **fields: Any) -> None:
        with self._lock:
            status = self._statuses[name]
            for key, value in fields.items():
                setattr(status, key, value)
            status.last_updated = time.time()

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {name: status.as_dict() for name, status in self._statuses.items()}

    def get(self, name: str) -> SourceStatus:
        with self._lock:
            return self._statuses[name]


def load_website_documents(source_url: str, max_pages: int, use_playwright: bool) -> list[Document]:
    pages = crawl_website_pages(source_url, max_pages=max_pages, use_playwright=use_playwright)
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
    return documents
