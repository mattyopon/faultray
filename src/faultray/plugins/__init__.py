"""Plugin system for custom scenarios and analyzers."""

from faultray.plugins.registry import PluginRegistry  # noqa: F401
from faultray.plugins.plugin_manager import (  # noqa: F401
    PluginContext,
    PluginInterface,
    PluginManager,
    PluginMetadata,
    PluginType,
)

__all__ = [
    "PluginRegistry",
    "PluginContext",
    "PluginInterface",
    "PluginManager",
    "PluginMetadata",
    "PluginType",
]
