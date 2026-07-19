"""Coverage for deterministic sentence-aware text chunking."""

import pytest

from multiscribe_agent.knowledge.chunking import split_text


def test_split_text_preserves_overlap_and_sentence_boundary() -> None:
    """Chunks stay bounded while preserving enough shared surrounding context."""
    chunks = split_text(
        "First sentence. Second sentence. Third sentence.", chunk_size=24, chunk_overlap=6
    )

    assert len(chunks) >= 2
    assert chunks[0].text.endswith(".")
    assert chunks[1].char_start < chunks[0].char_end


def test_split_text_handles_empty_and_invalid_window_settings() -> None:
    """Empty text is harmless and invalid windows fail before looping forever."""
    assert split_text("   ") == []
    with pytest.raises(ValueError, match="chunk_overlap"):
        split_text("text", chunk_size=5, chunk_overlap=5)
