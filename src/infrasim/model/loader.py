"""YAML model loader - import infrastructure definitions from YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml

from infrasim.model.components import (
    AutoScalingConfig,
    CacheWarmingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    CostProfile,
    DegradationConfig,
    Dependency,
    FailoverConfig,
    NetworkProfile,
    OperationalProfile,
    RegionConfig,
    ResourceMetrics,
    RetryStrategy,
    RuntimeJitter,
    SingleflightConfig,
    SLOTarget,
)
from infrasim.model.graph import InfraGraph


def load_yaml(path: Path | str) -> InfraGraph:
    """Load an infrastructure definition from a YAML file.

    The YAML file should contain top-level ``components`` and ``dependencies``
    keys.  Each component must have at least ``id``, ``name``, and ``type``.
    Capacity and metrics fields are optional and will use defaults when omitted.

    Args:
        path: Path to the YAML file (accepts both ``str`` and ``Path``).

    Returns:
        A fully constructed InfraGraph.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        ValueError: If required fields are missing or types are invalid.
    """
    if isinstance(path, str):
        path = Path(path)
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
        autoscaling = (
            AutoScalingConfig(**entry["autoscaling"]) if "autoscaling" in entry else AutoScalingConfig()
        )
        failover = (
            FailoverConfig(**entry["failover"]) if "failover" in entry else FailoverConfig()
        )
        cache_warming = (
            CacheWarmingConfig(**entry["cache_warming"]) if "cache_warming" in entry else CacheWarmingConfig()
        )
        singleflight = (
            SingleflightConfig(**entry["singleflight"]) if "singleflight" in entry else SingleflightConfig()
        )
        slo_targets = [SLOTarget(**s) for s in entry.get("slo_targets", [])]
        if "operational_profile" in entry:
            op_data = dict(entry["operational_profile"])
            if "degradation" in op_data:
                op_data["degradation"] = DegradationConfig(**op_data["degradation"])
            operational_profile = OperationalProfile(**op_data)
        else:
            operational_profile = OperationalProfile()

        replicas = entry.get("replicas", 1)
        if not isinstance(replicas, int) or replicas < 1:
            raise ValueError(
                f"Component '{comp_id}': replicas must be a positive integer, got {replicas}"
            )

        network = (
            NetworkProfile(**entry["network"]) if "network" in entry else NetworkProfile()
        )
        runtime_jitter = (
            RuntimeJitter(**entry["runtime_jitter"]) if "runtime_jitter" in entry else RuntimeJitter()
        )
        cost_profile = (
            CostProfile(**entry["cost_profile"]) if "cost_profile" in entry else CostProfile()
        )
        region_config = (
            RegionConfig(**entry["region"]) if "region" in entry else RegionConfig()
        )

        component = Component(
            id=comp_id,
            name=comp_name,
            type=comp_type,
            host=entry.get("host", ""),
            port=entry.get("port", 0),
            replicas=replicas,
            metrics=metrics,
            capacity=capacity,
            autoscaling=autoscaling,
            failover=failover,
            cache_warming=cache_warming,
            singleflight=singleflight,
            slo_targets=slo_targets,
            cost_profile=cost_profile,
            region=region_config,
            operational_profile=operational_profile,
            network=network,
            runtime_jitter=runtime_jitter,
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

        circuit_breaker = (
            CircuitBreakerConfig(**entry["circuit_breaker"]) if "circuit_breaker" in entry else CircuitBreakerConfig()
        )
        retry_strategy = (
            RetryStrategy(**entry["retry_strategy"]) if "retry_strategy" in entry else RetryStrategy()
        )

        dep_type = entry.get("type", "requires")
        valid_dep_types = ("requires", "optional", "async")
        if dep_type not in valid_dep_types:
            raise ValueError(
                f"Dependency entry {idx}: invalid type '{dep_type}'. "
                f"Valid types: {list(valid_dep_types)}"
            )

        dep = Dependency(
            source_id=source_id,
            target_id=target_id,
            dependency_type=dep_type,
            protocol=entry.get("protocol", ""),
            port=entry.get("port", 0),
            latency_ms=entry.get("latency_ms", 0.0),
            weight=entry.get("weight", 1.0),
            circuit_breaker=circuit_breaker,
            retry_strategy=retry_strategy,
        )
        graph.add_dependency(dep)

    # Validate no circular dependencies
    import networkx as nx
    if not nx.is_directed_acyclic_graph(graph._graph):
        cycles = list(nx.simple_cycles(graph._graph))
        cycle_str = " -> ".join(cycles[0] + [cycles[0][0]]) if cycles else "unknown"
        raise ValueError(
            f"Circular dependency detected: {cycle_str}. "
            f"Infrastructure graph must be a DAG."
        )

    return graph


def load_yaml_with_ops(path: Path | str) -> tuple[InfraGraph, dict]:
    """Load infrastructure definition and operational simulation config from YAML.

    In addition to building the :class:`InfraGraph` via :func:`load_yaml`, this
    function parses top-level ``slos`` and ``operational_simulation`` sections
    that configure v3.0 long-running operational simulations.

    Args:
        path: Path to the YAML file.

    Returns:
        Tuple of ``(InfraGraph, ops_config)`` where *ops_config* is a dict
        with ``'slos'`` (list of :class:`SLOTarget`) and
        ``'operational_simulation'`` (raw dict of simulation parameters).
    """
    # Build the graph using the existing loader
    graph = load_yaml(path)

    # Parse additional ops sections from the raw YAML
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    ops_config: dict = {
        "slos": [SLOTarget(**s) for s in raw.get("slos", [])],
        "operational_simulation": raw.get("operational_simulation", {}),
    }
    return graph, ops_config
