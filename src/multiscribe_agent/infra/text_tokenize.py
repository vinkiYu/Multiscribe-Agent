"""Chinese-aware FTS tokenizer with graceful optional-dependency degradation."""

from __future__ import annotations

from functools import lru_cache
from types import ModuleType
from typing import cast


@lru_cache(maxsize=1)
def _get_jieba() -> ModuleType | None:
    """Load jieba lazily so deployments without it retain Unicode FTS support."""
    try:
        import jieba  # type: ignore[import-not-found]

        jieba.setLogLevel(20)
        return cast(ModuleType, jieba)
    except ImportError:
        return None


def tokenize_for_fts(text: str) -> str:
    """Return space-separated search tokens, or original text when jieba is absent."""
    if not text:
        return ""
    jieba = _get_jieba()
    if jieba is None:
        return text
    return " ".join(token.strip() for token in jieba.cut_for_search(text) if token.strip())


def is_chinese_tokenization_available() -> bool:
    """Return whether the optional jieba tokenizer can be imported."""
    return _get_jieba() is not None
