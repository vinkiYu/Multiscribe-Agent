"""Plugin base contracts, registries, and automatic discovery."""

from multiscribe_agent.plugins.base import (
    BaseAdapter,
    BasePublisher,
    BaseStorageProvider,
    BaseTool,
)
from multiscribe_agent.plugins.discovery import DiscoveryResult, scan_and_register
from multiscribe_agent.plugins.registry import (
    AdapterRegistry,
    PublisherRegistry,
    StorageRegistry,
    ToolRegistry,
)

__all__ = [
    "AdapterRegistry",
    "BaseAdapter",
    "BasePublisher",
    "BaseStorageProvider",
    "BaseTool",
    "DiscoveryResult",
    "PublisherRegistry",
    "StorageRegistry",
    "ToolRegistry",
    "scan_and_register",
]
