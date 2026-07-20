"""Tests for optional jieba tokenization at FTS write/query boundaries."""

from __future__ import annotations

import pytest

from multiscribe_agent.infra import text_tokenize
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.knowledge.retriever import Retriever


class _FakeJieba:
    @staticmethod
    def setLogLevel(level: int) -> None:
        del level

    @staticmethod
    def cut_for_search(text: str) -> list[str]:
        return ["大模型", "大语言模型"] if "大语言模型" in text else text.split()


def test_tokenizer_falls_back_when_jieba_is_unavailable(monkeypatch) -> None:
    """Missing optional jieba leaves text usable by SQLite unicode61."""
    monkeypatch.setattr(text_tokenize, "_get_jieba", lambda: None)
    assert text_tokenize.tokenize_for_fts("大语言模型") == "大语言模型"


@pytest.mark.asyncio
async def test_kb_chunk_fts_uses_tokenized_content(monkeypatch) -> None:
    """A KB insert stores tokenized text in the FTS shadow table."""
    monkeypatch.setattr(text_tokenize, "_get_jieba", lambda: _FakeJieba())
    db = await init_db(":memory:")
    try:
        await db.execute(
            "INSERT INTO kb_chunks(id, document_id, content) VALUES (?, ?, ?)",
            ("chunk-cn", "doc", "大语言模型"),
        )
        row = await db.fetchone(
            "SELECT content FROM kb_chunks_fts "
            "WHERE rowid = (SELECT rowid FROM kb_chunks WHERE id = ?)",
            ("chunk-cn",),
        )
        assert row is not None
        assert "大模型" in str(row["content"])

        hit = await Retriever(db)._fts_chunk_ids("大模型", 10)
        assert hit == ["chunk-cn"]
    finally:
        await db.close()
