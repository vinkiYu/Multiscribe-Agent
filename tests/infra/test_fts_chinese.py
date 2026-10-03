"""Tests for optional jieba tokenization at FTS write/query boundaries."""

from __future__ import annotations

from multiscribe_agent.infra import text_tokenize


def test_tokenizer_falls_back_when_jieba_is_unavailable(monkeypatch) -> None:
    """Missing optional jieba leaves the input usable for PostgreSQL tsvector."""
    monkeypatch.setattr(text_tokenize, "_get_jieba", lambda: None)
    assert text_tokenize.tokenize_for_fts("大语言模型") == "大语言模型"
