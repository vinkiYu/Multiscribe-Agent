"""Asynchronous repository ports implemented by the infrastructure layer."""

from __future__ import annotations

from typing import Any, Protocol

from multiscribe_agent.domain.models import SourceData, TaskLog, UnifiedData


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

    async def get_by_date_range(self, start: str, end: str) -> list[SourceData]:
        """Return content whose configured date field is within the range."""
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
