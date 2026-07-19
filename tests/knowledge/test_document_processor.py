"""Coverage for non-blocking supported-document extraction."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from multiscribe_agent.knowledge.document_processor import (
    DocumentProcessor,
    UnsupportedDocumentError,
)


@pytest.mark.asyncio
async def test_processor_reads_utf8_markdown(tmp_path: Path) -> None:
    """Markdown follows the direct local text ingestion path."""
    path = tmp_path / "note.md"
    path.write_text("# Knowledge\nUseful retrieval content.", encoding="utf-8")

    text, chunks = await DocumentProcessor().process(path)

    assert text.startswith("# Knowledge")
    assert chunks[0].text


@pytest.mark.asyncio
async def test_processor_rejects_unknown_format(tmp_path: Path) -> None:
    """Unknown file suffixes raise UnsupportedDocumentError directly."""
    unknown = tmp_path / "note.csv"
    unknown.write_text("a,b", encoding="utf-8")

    with pytest.raises(UnsupportedDocumentError):
        await DocumentProcessor().process(unknown)


@pytest.mark.asyncio
async def test_processor_rejects_pdf_parsing_failure(tmp_path: Path) -> None:
    """PDF parser failures are exposed as a stable domain error."""
    pdf = tmp_path / "empty.pdf"
    pdf.write_bytes(b"%PDF")

    with patch(
        "multiscribe_agent.knowledge.document_processor.importlib.import_module"
    ) as mock_import:
        pdf_module = MagicMock()
        page = MagicMock()
        page.extract_text.side_effect = OSError("stream ended unexpectedly")
        reader = MagicMock()
        reader.pages = [page]
        pdf_module.PdfReader = MagicMock(return_value=reader)
        mock_import.return_value = pdf_module

        with pytest.raises(UnsupportedDocumentError, match="PDF support"):
            await DocumentProcessor().process(pdf)


@pytest.mark.asyncio
async def test_processor_rejects_docx_when_module_unavailable(tmp_path: Path) -> None:
    """Missing python-docx becomes a stable domain error."""
    document = tmp_path / "note.docx"
    document.write_bytes(b"PK\x03\x04")

    with (
        patch(
            "multiscribe_agent.knowledge.document_processor.importlib.import_module",
            side_effect=ImportError("No module named 'docx'"),
        ),
        pytest.raises(UnsupportedDocumentError, match="DOCX support"),
    ):
        await DocumentProcessor().process(document)
