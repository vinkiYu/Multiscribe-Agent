"""Import and register self-describing plugins from package trees."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass, field
from types import ModuleType

from multiscribe_agent.domain.models import PluginMetadata
from multiscribe_agent.plugins.base import (
    BaseAdapter,
    BasePublisher,
    BaseStorageProvider,
    BaseTool,
)
from multiscribe_agent.plugins.registry import (
    AdapterRegistry,
    PublisherRegistry,
    StorageRegistry,
    ToolRegistry,
)


@dataclass(slots=True)
class DiscoveryResult:
    """Names of plugin classes registered or candidates skipped during a scan."""

    registered: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def scan_and_register(package_root: str | None = None) -> DiscoveryResult:
    """Scan builtin/custom subpackages and register classes carrying valid metadata."""
    root = package_root or "multiscribe_agent.plugins"
    result = DiscoveryResult()
    for namespace in (f"{root}.builtin", f"{root}.custom"):
        package = _import_optional_package(namespace)
        if package is None:
            continue
        package_paths = getattr(package, "__path__", None)
        if package_paths is None:
            result.skipped.append(namespace)
            continue
        for module_info in pkgutil.walk_packages(package_paths, f"{namespace}."):
            module_name = module_info.name
            leaf_name = module_name.rsplit(".", 1)[-1]
            if "base" in leaf_name or leaf_name.endswith("_test"):
                result.skipped.append(module_name)
                continue
            module = importlib.import_module(module_name)
            _register_module_classes(module, result)
    return result


def _import_optional_package(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name == name:
            return None
        raise


def _register_module_classes(module: ModuleType, result: DiscoveryResult) -> None:
    for attribute_name in dir(module):
        candidate = getattr(module, attribute_name)
        qualified_name = f"{module.__name__}.{attribute_name}"
        if not inspect.isclass(candidate) or candidate.__module__ != module.__name__:
            continue
        metadata = getattr(candidate, "metadata", None)
        if not isinstance(metadata, PluginMetadata):
            result.skipped.append(qualified_name)
            continue
        if _register_candidate(candidate, metadata):
            if qualified_name not in result.registered:
                result.registered.append(qualified_name)
        else:
            result.skipped.append(qualified_name)


def _register_candidate(candidate: type[object], metadata: PluginMetadata) -> bool:
    if metadata.type == "adapter" and issubclass(candidate, BaseAdapter):
        AdapterRegistry.get_instance().register(metadata.id, candidate, metadata)
        return True
    if metadata.type == "publisher" and issubclass(candidate, BasePublisher):
        PublisherRegistry.get_instance().register(metadata.id, candidate, metadata)
        return True
    if metadata.type == "storage" and issubclass(candidate, BaseStorageProvider):
        StorageRegistry.get_instance().register(metadata.id, candidate, metadata)
        return True
    if metadata.type == "tool" and issubclass(candidate, BaseTool):
        ToolRegistry.get_instance().register(candidate, metadata)
        return True
    return False
