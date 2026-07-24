"""Accuracy and fallback coverage for Agent request token counting."""

from __future__ import annotations

import tiktoken

import multiscribe_agent.agents.token_counter as token_counter_module
from multiscribe_agent.agents.token_counter import (
    ConservativeTokenCounter,
    TiktokenCounter,
    resolve_token_counter,
)

CHINESE_SAMPLE = "人工智能技术在过去一年取得了显著进展,大语言模型的能力持续提升"


def test_tiktoken_chinese_estimation_matches_model_encoding() -> None:
    """The production counter uses the exact model encoding for Chinese text."""
    counter = TiktokenCounter("gpt-4o")
    expected = len(tiktoken.encoding_for_model("gpt-4o").encode(CHINESE_SAMPLE))

    assert counter.count_text(CHINESE_SAMPLE) == expected


def test_fallback_chinese_estimation_is_within_twenty_percent() -> None:
    """The dependency-free fallback remains conservative enough for CJK content."""
    counter = ConservativeTokenCounter(chars_per_token=1.5)
    expected = len(tiktoken.encoding_for_model("gpt-4o").encode(CHINESE_SAMPLE))
    error_ratio = abs(counter.count_text(CHINESE_SAMPLE) - expected) / expected

    assert error_ratio < 0.20


def test_resolve_token_counter_prefers_tiktoken() -> None:
    """Normal deployments select precise counting."""
    assert isinstance(resolve_token_counter("openai", "gpt-4o"), TiktokenCounter)


def test_resolve_token_counter_falls_back_when_tiktoken_is_unavailable(monkeypatch) -> None:
    """A broken optional import still yields the CJK-weighted safety counter."""

    def unavailable(model: str | None = None) -> TiktokenCounter:
        del model
        raise ImportError("tiktoken unavailable")

    monkeypatch.setattr(token_counter_module, "TiktokenCounter", unavailable)

    assert isinstance(resolve_token_counter("proxy", "custom-model"), ConservativeTokenCounter)
