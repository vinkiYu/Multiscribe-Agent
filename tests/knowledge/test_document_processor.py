"""Coverage for non-blocking supported-document extraction."""

from pathlib import Path

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
async def test_processor_rejects_unknown_and_unavailable_optional_formats(tmp_path: Path) -> None:
    """Unsupported suffixes and missing optional PDF parser fail explicitly."""
    unknown = tmp_path / "note.csv"
    unknown.write_text("a,b", encoding="utf-8")
    pdf = tmp_path / "empty.pdf"
    pdf.write_bytes(b"%PDF")

    with pytest.raises(UnsupportedDocumentError):
        await DocumentProcessor().process(unknown)
    with pytest.raises(UnsupportedDocumentError, match="PDF support"):
        await DocumentProcessor().process(pdf)
