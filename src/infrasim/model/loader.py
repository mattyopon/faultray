"""YAML model loader - import infrastructure definitions from YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph


def load_yaml(path: Path) -> InfraGraph:
    """Load an infrastructure definition from a YAML file.

    The YAML file should contain top-level ``components`` and ``dependencies``
    keys.  Each component must have at least ``id``, ``name``, and ``type``.
    Capacity and metrics fields are optional and will use defaults when omitted.

    Args:
        path: Path to the YAML file.

    Returns:
        A fully constructed InfraGraph.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        ValueError: If required fields are missing or types are invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected a YAML mapping at the top level, got {type(raw).__name__}")

    graph = InfraGraph()

    # --- Components -----------------------------------------------------------
    raw_components = raw.get("components", [])
    if not isinstance(raw_components, list):
        raise ValueError("'components' must be a list")

    for idx, entry in enumerate(raw_components):
        if not isinstance(entry, dict):
            raise ValueError(f"Component entry {idx} must be a mapping")

        comp_id = entry.get("id")
        if not comp_id:
            raise ValueError(f"Component entry {idx} is missing 'id'")

        comp_name = entry.get("name", comp_id)

        # Resolve component type (accept lowercase enum value)
        raw_type = entry.get("type", "custom")
        try:
            comp_type = ComponentType(raw_type)
        except ValueError:
            raise ValueError(
                f"Unknown component type '{raw_type}' for component '{comp_id}'. "
                f"Valid types: {[t.value for t in ComponentType]}"
            )

        # Build optional sub-models
        metrics = ResourceMetrics(**entry["metrics"]) if "metrics" in entry else ResourceMetrics()
        capacity = Capacity(**entry["capacity"]) if "capacity" in entry else Capacity()

        component = Component(
            id=comp_id,
            name=comp_name,
            type=comp_type,
            host=entry.get("host", ""),
            port=entry.get("port", 0),
            replicas=entry.get("replicas", 1),
            metrics=metrics,
            capacity=capacity,
            parameters=entry.get("parameters", {}),
            tags=entry.get("tags", []),
        )
        graph.add_component(component)

    # --- Dependencies ---------------------------------------------------------
    raw_deps = raw.get("dependencies", [])
    if not isinstance(raw_deps, list):
        raise ValueError("'dependencies' must be a list")

    known_ids = set(graph.components.keys())

    for idx, entry in enumerate(raw_deps):
        if not isinstance(entry, dict):
            raise ValueError(f"Dependency entry {idx} must be a mapping")

        source_id = entry.get("source")
        target_id = entry.get("target")
        if not source_id or not target_id:
            raise ValueError(f"Dependency entry {idx} is missing 'source' or 'target'")

        if source_id not in known_ids:
            raise ValueError(
                f"Dependency entry {idx}: source '{source_id}' does not match any component id"
            )
        if target_id not in known_ids:
            raise ValueError(
                f"Dependency entry {idx}: target '{target_id}' does not match any component id"
            )

        dep = Dependency(
            source_id=source_id,
            target_id=target_id,
            dependency_type=entry.get("type", "requires"),
            protocol=entry.get("protocol", ""),
            port=entry.get("port", 0),
            latency_ms=entry.get("latency_ms", 0.0),
            weight=entry.get("weight", 1.0),
        )
        graph.add_dependency(dep)

    return graph
