"""Sentence-aware sliding-window text chunking."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextChunk:
    """One stable text window ready for storage and embedding."""

    text: str
    index: int
    char_start: int
    char_end: int


def split_text(
    text: str,
    *,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    respect_sentence_boundary: bool = True,
) -> list[TextChunk]:
    """Split non-empty text into overlapping bounded chunks."""
    if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")
    stripped = text.strip()
    if not stripped:
        return []
    chunks: list[TextChunk] = []
    start = 0
    index = 0
    while start < len(stripped):
        end = min(start + chunk_size, len(stripped))
        if respect_sentence_boundary and end < len(stripped):
            boundary = max(
                stripped.rfind(mark, start + chunk_size // 2, end)
                for mark in "\u3002\uff01\uff1f.!?\n"
            )
            if boundary >= start + chunk_size // 2:
                end = boundary + 1
        value = stripped[start:end].strip()
        if value:
            chunks.append(TextChunk(value, index, start, end))
            index += 1
        if end >= len(stripped):
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks
