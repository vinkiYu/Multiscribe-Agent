"""Version identifiers for reproducible RAG index rebuilds."""

from __future__ import annotations

from datetime import UTC, datetime

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def make_index_version(
    *,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    now: datetime | None = None,
) -> str:
    """Return an index version composed of UTC date and embedding model name."""
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    safe_model = "-".join(model_name.strip().split()).replace("/", "-")
    if not safe_model:
        raise ValueError("model_name must not be empty")
    return f"{reference.astimezone(UTC):%Y%m%d}-{safe_model}"


__all__ = ["DEFAULT_EMBEDDING_MODEL", "make_index_version"]
