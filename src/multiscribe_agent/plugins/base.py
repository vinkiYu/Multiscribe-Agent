"""Abstract contracts shared by all Multiscribe plugins."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from typing import ClassVar, Literal

import httpx
import structlog

from multiscribe_agent.core.errors import PublisherError
from multiscribe_agent.domain.models import PluginMetadata, UnifiedData

log = structlog.get_logger(__name__)
PLUGIN_API_VERSION = "1.0"


class BaseAdapter(ABC):
    """Fetch external data and transform it into canonical domain items."""

    metadata: ClassVar[PluginMetadata]

    @abstractmethod
    async def fetch(self, config: Mapping[str, object]) -> object:
        """Fetch raw data from an external source."""

    @abstractmethod
    def transform(
        self, raw: object, config: Mapping[str, object] | None = None
    ) -> list[UnifiedData]:
        """Transform raw source data into canonical items."""

    async def fetch_and_transform(self, config: Mapping[str, object]) -> list[UnifiedData]:
        """Fetch then transform, isolating a failing source from the batch."""
        try:
            raw = await self.fetch(config)
            return self.transform(raw, config)
        except Exception as exc:  # Adapter implementations are an isolation boundary.
            log.warning(
                "adapter_fetch_transform_failed",
                adapter_id=self.metadata.id,
                error_type=type(exc).__name__,
            )
            return []


class BasePublisher(ABC):
    """Publish rendered content to an external destination."""

    metadata: ClassVar[PluginMetadata]
    RETRY_DELAYS_SECONDS: ClassVar[tuple[float, ...]] = (1.0, 2.0, 4.0)

    @abstractmethod
    async def publish(
        self, content: object, options: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        """Publish content and return a serializable status mapping."""

    async def get_item_url(self, item: object) -> str | None:
        """Return a published item's public URL when supported."""
        del item
        return None

    async def _send_with_retry(
        self,
        send_func: Callable[[], Awaitable[dict[str, object]]],
        *,
        publisher_name: str,
        retry_exceptions: tuple[type[Exception], ...] = (httpx.HTTPError, PublisherError),
        retry_delays: tuple[float, ...] | None = None,
    ) -> dict[str, object]:
        """Run one publisher send with bounded exponential backoff.

        Payload and signing construction happen before this method is called. The
        closure therefore contains only the external request and response checks,
        keeping retries deterministic and preventing duplicate signatures.
        """
        delays = retry_delays if retry_delays is not None else self.RETRY_DELAYS_SECONDS
        last_error: Exception | None = None
        for attempt in range(len(delays) + 1):
            try:
                return await send_func()
            except retry_exceptions as exc:
                last_error = exc
                if attempt >= len(delays):
                    break
                log.warning(
                    "publisher_retry",
                    publisher=publisher_name,
                    attempt=attempt + 1,
                    error_type=type(exc).__name__,
                )
                await asyncio.sleep(delays[attempt])
        raise PublisherError(f"{publisher_name} publish failed after retries") from last_error


class BaseStorageProvider(ABC):
    """Upload local assets and return public URLs."""

    metadata: ClassVar[PluginMetadata]

    @abstractmethod
    async def upload(self, local_path: str, target_path: str) -> str | None:
        """Upload one local file to the requested target path."""


class BaseTool(ABC):
    """Expose a JSON-schema callable to Agent runs."""

    metadata: ClassVar[PluginMetadata]
    id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    parameters: ClassVar[dict[str, object]]
    is_builtin: ClassVar[bool] = False
    risk_level: ClassVar[Literal["low", "medium", "high"]] = "low"
    requires_approval: ClassVar[bool] = False
    read_only: ClassVar[bool] = True
    idempotent: ClassVar[bool] = True

    @abstractmethod
    async def handler(self, args: Mapping[str, object]) -> object:
        """Execute the tool with validated serializable arguments."""
