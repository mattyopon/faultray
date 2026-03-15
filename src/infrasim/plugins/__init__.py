"""Plugin system for custom scenarios and analyzers."""

from infrasim.plugins.registry import PluginRegistry  # noqa: F401
from infrasim.plugins.plugin_manager import (  # noqa: F401
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
