"""Asynchronous document text extraction for knowledge-base ingestion."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from multiscribe_agent.knowledge.chunking import TextChunk, split_text

SUPPORTED_SUFFIXES = frozenset({".md", ".txt", ".pdf", ".docx"})


class UnsupportedDocumentError(ValueError):
    """Raised when a document type cannot be safely parsed."""


class _PdfPage(Protocol):
    """Minimal pypdf page behavior used by the optional parser."""

    def extract_text(self) -> str | None: ...


class _PdfReader(Protocol):
    """Minimal pypdf reader behavior used by the optional parser."""

    pages: list[_PdfPage]


class _DocxParagraph(Protocol):
    """Minimal python-docx paragraph behavior."""

    text: str


class _DocxDocument(Protocol):
    """Minimal python-docx document behavior."""

    paragraphs: list[_DocxParagraph]


class DocumentProcessor:
    """Extract supported local documents without blocking the event loop."""

    async def process(self, file_path: Path) -> tuple[str, list[TextChunk]]:
        """Return extracted full text and sentence-aware chunks."""
        suffix = file_path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise UnsupportedDocumentError(f"unsupported document suffix: {suffix or '<none>'}")
        text = await asyncio.to_thread(self._extract, file_path, suffix)
        if not text.strip():
            raise UnsupportedDocumentError("document does not contain extractable text")
        return text, split_text(text)

    @staticmethod
    def _extract(file_path: Path, suffix: str) -> str:
        """Perform blocking parser work inside the worker thread."""
        if suffix in {".md", ".txt"}:
            return file_path.read_text(encoding="utf-8")
        if suffix == ".pdf":
            try:
                module = importlib.import_module("pypdf")
                reader_factory = cast(Callable[[Path], _PdfReader], module.__dict__["PdfReader"])
            except ImportError as exc:
                raise UnsupportedDocumentError("PDF support is unavailable") from exc
            return "\n".join(page.extract_text() or "" for page in reader_factory(file_path).pages)
        try:
            module = importlib.import_module("docx")
            document_factory = cast(Callable[[Path], _DocxDocument], module.__dict__["Document"])
        except ImportError as exc:
            raise UnsupportedDocumentError("DOCX support is unavailable") from exc
        return "\n".join(paragraph.text for paragraph in document_factory(file_path).paragraphs)
