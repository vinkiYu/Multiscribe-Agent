"""Tests for the P66 legacy-record to canonical-document adapters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from multiscribe_agent.domain.models import KBDocument, SourceData
from multiscribe_agent.rag.adapter import RagDocumentAdapter, from_source_data


def _source(published_date: str) -> SourceData:
    return SourceData(
        id="source-1",
        title="Agent indexing",
        url="https://example.com/agent-indexing",
        description="A short description for the daily source item.",
        published_date=published_date,
        source="example",
        category="ai",
        fetched_at=published_date,
        ingestion_date=published_date,
        adapter_name="rss",
    )


def test_source_data_is_one_chunk_and_allows_explicit_user_override() -> None:
    """A source item remains atomic even when its text is longer than a window."""
    now = datetime(2026, 9, 22, tzinfo=UTC)
    row = _source(now.isoformat())
    row.description = "x" * 2_000
    adapted = RagDocumentAdapter(user_id="default", source_window_days=7).adapt_source_data(
        row, now=now
    )

    assert adapted is not None
    assert len(adapted.chunks) == 1
    assert adapted.chunks[0].metadata["user_id"] == "default"
    assert adapted.chunks[0].metadata["char_end"] == len(adapted.chunks[0].content)


def test_source_data_outside_window_is_ignored() -> None:
    """Rows older than the configured freshness window are not indexed."""
    now = datetime(2026, 9, 22, tzinfo=UTC)
    old = _source((now - timedelta(days=8)).isoformat())

    assert from_source_data(old, user_id="default", window_days=7, now=now) is None


def test_unknown_publication_date_uses_fetch_time_for_rag_window() -> None:
    """Unknown adapter dates do not force a fresh row out of the RAG window."""
    now = datetime(2026, 9, 22, tzinfo=UTC)
    row = _source("1970-01-01T00:00:00+00:00")
    row.fetched_at = now.isoformat()
    row.ingestion_date = now.isoformat()

    adapted = from_source_data(row, user_id="default", window_days=7, now=now)

    assert adapted is not None
    assert adapted.published_at == now.isoformat()


def test_kb_uses_sliding_windows_with_character_offsets() -> None:
    """Long KB text is split using the existing sentence-aware chunking semantics."""
    document = KBDocument(
        id="kb-1",
        category_id="engineering",
        name="RAG design",
        file_name="rag.md",
        type="md",
        summary="",
        chunk_count=0,
        created_at=1,
        updated_at=1,
        owner_user_id="member-1",
        metadata={"content": "A" * 1_200},
    )
    adapted = RagDocumentAdapter(chunk_size=256, chunk_overlap=32).adapt_kb_document(document)

    assert len(adapted.chunks) >= 2
    assert adapted.document.user_id == "member-1"
    assert all(chunk.metadata["user_id"] == "member-1" for chunk in adapted.chunks)
    assert all("char_start" in chunk.metadata for chunk in adapted.chunks)
    assert all("char_end" in chunk.metadata for chunk in adapted.chunks)
