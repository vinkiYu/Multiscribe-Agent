"""Asynchronous repository ports implemented by the infrastructure layer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from multiscribe_agent.domain.models import SourceData, TaskLog, UnifiedData


class DatabaseProtocol(Protocol):
    """Minimal database surface exposed to agent-layer orchestration."""

    async def execute(
        self, statement: str, parameters: tuple[Any, ...] | list[Any] = ()
    ) -> int | None:
        """Execute one parameterized statement."""
        ...

    async def executemany(
        self, statement: str, parameters: list[tuple[Any, ...] | list[Any]]
    ) -> int:
        """Execute one statement for a batch of parameter sets."""
        ...

    async def fetchone(
        self, statement: str, parameters: tuple[Any, ...] | list[Any] = ()
    ) -> Mapping[str, Any] | None:
        """Fetch one row from a parameterized query."""
        ...

    async def fetchall(
        self, statement: str, parameters: tuple[Any, ...] | list[Any] = ()
    ) -> list[Mapping[str, Any]]:
        """Fetch all rows from a parameterized query."""
        ...

    async def close(self) -> None:
        """Close the database connection or pool."""
        ...


class CurationEvaluationRepositoryProtocol(Protocol):
    """Persistence port used by the daily digest to record one evaluation."""

    async def upsert(self, evaluation: object) -> None:
        """Insert or update a serialized curation evaluation record."""
        ...


class VectorStorePort(Protocol):
    """Persist and retrieve high-dimensional chunk embeddings."""

    async def upsert(self, chunk_id: str, embedding: Sequence[float]) -> None:
        """Store or update one embedding."""
        ...

    async def delete(self, chunk_id: str) -> None:
        """Remove one embedding."""
        ...

    async def top_k(self, query: Sequence[float], k: int = 20) -> list[tuple[str, float]]:
        """Return nearest chunk IDs and distances in ascending distance order."""
        ...


class KvRepository(Protocol):
    """Store JSON-compatible values by key with optional expiration."""

    async def get(self, key: str) -> object | None:
        """Return a stored value, or None when the key does not exist."""
        ...

    async def set(self, key: str, value: object, ttl_seconds: int | None = None) -> None:
        """Store a value with an optional time-to-live in seconds."""
        ...

    async def delete(self, key: str) -> None:
        """Delete a key when present."""
        ...


class EntityJsonRepository(Protocol):
    """Persist JSON objects in one of the supported entity tables."""

    async def get(self, table: str, entity_id: str) -> dict[str, Any] | None:
        """Return one entity by table and identifier."""
        ...

    async def save(self, table: str, entity_id: str, data: dict[str, Any]) -> None:
        """Insert or replace an entity JSON document."""
        ...

    async def list_all(self, table: str) -> list[dict[str, Any]]:
        """Return all entities from a supported table."""
        ...

    async def delete(self, table: str, entity_id: str) -> None:
        """Delete an entity when present."""
        ...


class SourceDataRepository(Protocol):
    """Persist and query normalized source content."""

    async def save_batch(self, items: list[UnifiedData], adapter_name: str) -> int:
        """Persist a batch and return the number of newly inserted items."""
        ...

    async def query(self, filters: dict[str, Any]) -> list[SourceData]:
        """Query source content using repository-supported filters."""
        ...

    async def search_fts(self, query: str, limit: int) -> list[SourceData]:
        """Run a full-text search and return ranked content."""
        ...

    async def get_by_date_range(
        self, start: str, end: str, query_field: str = "ingestion_date"
    ) -> list[SourceData]:
        """Return content whose selected persisted date field is within the range."""
        ...


class TaskLogRepository(Protocol):
    """Persist task lifecycle records."""

    async def create(self, log: TaskLog) -> str:
        """Create a task log and return its identifier."""
        ...

    async def update(self, log_id: str, **fields: object) -> None:
        """Update allowed fields on an existing task log."""
        ...

    async def get(self, log_id: str) -> TaskLog | None:
        """Return a task log by identifier."""
        ...


class ApiKeyRepository(Protocol):
    """Persist and manage hashed external API credentials."""

    async def create(
        self,
        key_id: str,
        name: str,
        key_hash: str,
        prefix: str,
        source_fingerprint: str,
        verification_token: str,
        status: str,
    ) -> None:
        """Create an API key record without storing the plaintext key."""
        ...

    async def get_by_prefix(self, prefix: str) -> dict[str, Any] | None:
        """Return an API key record by its public prefix."""
        ...

    async def get_by_token(self, token: str) -> dict[str, Any] | None:
        """Return an API key record by its verification token."""
        ...

    async def update_status(self, key_id: str, status: str) -> None:
        """Change whether an API key is active or revoked."""
        ...

    async def update_last_used(self, key_id: str) -> None:
        """Record the current time as the key's last use."""
        ...

    async def list_all(self) -> list[dict[str, Any]]:
        """Return every API key record without plaintext secrets."""
        ...


class AdapterHealthRepository(Protocol):
    """Persist adapter health degradation state."""

    async def upsert_event(
        self,
        adapter_id: str,
        status: str,
        *,
        error_message: str | None,
        occurred_at: str,
    ) -> None:
        """Record one adapter health event."""
        ...

    async def list_all(self) -> list[object]:
        """Return all adapter health records."""
        ...

    async def get(self, adapter_id: str) -> object | None:
        """Return one adapter health record, if present."""
        ...

    async def set_disabled(self, *, adapter_id: str, disabled: bool) -> None:
        """Enable or disable one adapter."""
        ...


class ClickEventRepository(Protocol):
    """Persist anonymous digest click signals."""

    async def record(
        self,
        *,
        content_id: str,
        digest_date: str,
        tags: list[str],
        source: str,
        clicked_at: str,
        user_agent: str | None,
    ) -> None:
        """Record one click event."""
        ...

    async def tag_click_counts(self, since: str) -> list[dict[str, int]]:
        """Aggregate click counts by tag since the supplied date."""
        ...


class PushedContentRepository(Protocol):
    """Persist cross-day content identities used by digest deduplication."""

    async def upsert_hash(
        self,
        *,
        content_hash: str,
        url: str | None,
        digest_date: str,
        publisher_id: str,
    ) -> bool:
        """Insert one identity and report whether it was new."""
        ...

    async def lookup_by_url(self, url: str, since_date: str) -> list[object]:
        """Find recently pushed content for a URL."""
        ...


class IterationStore(Protocol):
    """Persist workflow loop iterations for retry and dashboard consumers."""

    async def append(self, record: object) -> None:
        """Append one durable loop checkpoint."""
        ...

    async def list_for_step(self, workflow_run_id: str, step_id: str) -> list[object]:
        """Return all checkpoints for a workflow step."""
        ...

    async def list_recent(self, limit: int) -> list[object]:
        """Return the newest checkpoints across workflow runs."""
        ...


class MemoryEntryRepository(Protocol):
    """Persist and search long-lived agent memory entries."""

    async def create(self, entry: object) -> str:
        """Create one memory entry."""
        ...

    async def update(self, entry_id: str, **fields: object) -> None:
        """Update selected fields on a memory entry."""
        ...

    async def delete(self, entry_id: str) -> None:
        """Delete one memory entry."""
        ...

    async def get(self, entry_id: str) -> object | None:
        """Return one memory entry by identifier."""
        ...

    async def list_all(self) -> list[object]:
        """Return all memory entries."""
        ...

    async def search(self, query: str, limit: int) -> list[object]:
        """Search memories using the backend's preferred strategy."""
        ...

    async def fts_search(self, query: str, limit: int) -> list[object]:
        """Search memories through a full-text index."""
        ...


class MemoryCategoryRepository(Protocol):
    """Persist memory category metadata."""

    async def upsert(self, category: object) -> None:
        """Create or update one memory category."""
        ...

    async def list_all(self) -> list[object]:
        """Return all memory categories."""
        ...


class DailyUsageRepository(Protocol):
    """Aggregate daily token usage for operational reporting."""

    async def upsert(self, date: str, usage: object) -> None:
        """Add one run's token usage to a calendar day."""
        ...

    async def query(self, from_date: str, to_date: str) -> list[object]:
        """Return usage records in an inclusive date range."""
        ...

    async def ensure_schema(self) -> None:
        """Ensure the usage table exists."""
        ...


class CurationEvaluationRepository(Protocol):
    """Persist curation loop evaluation summaries."""

    async def upsert(self, evaluation: object) -> None:
        """Insert or update one workflow evaluation."""
        ...

    async def query(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 50,
    ) -> list[object]:
        """Return evaluation records for a bounded date range."""
        ...

    async def summary(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, object]:
        """Return aggregate quality and convergence metrics."""
        ...

    async def ensure_schema(self) -> None:
        """Ensure the evaluation table exists."""
        ...
