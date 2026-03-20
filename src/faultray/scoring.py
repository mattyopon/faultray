# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Custom scoring models — let users define their own scoring criteria.

Users can define scoring rules in YAML and evaluate their infrastructure
against custom policies.

Usage:
    faultray score-custom my-model.json --policy scoring-policy.yaml --json
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


@dataclass
class ScoringRule:
    """A single scoring rule definition."""

    name: str
    description: str
    weight: float = 1.0
    check_fn: str = ""  # function name to call (key in BUILT_IN_CHECKS)
    params: dict = field(default_factory=dict)


@dataclass
class CustomScoringResult:
    """Result of evaluating a custom scoring model."""

    model_name: str
    total_score: float  # 0-100
    rules: list[dict]  # [{name, score, weight, description, passed}]
    weighted_score: float


# ---------------------------------------------------------------------------
# Built-in check functions
# ---------------------------------------------------------------------------

def _check_min_replicas(graph: InfraGraph, params: dict) -> float:
    """Check that components of a given type have >= N replicas.

    Params:
        component_type: str - component type to check (e.g. "database")
        min: int - minimum replica count (default: 2)

    Returns score 0-100 based on fraction of matching components.
    """
    comp_type_str = params.get("component_type", "")
    min_replicas = int(params.get("min", 2))

    target_comps = _filter_components_by_type(graph, comp_type_str)
    if not target_comps:
        return 100.0  # No components of this type -> rule passes

    passing = sum(1 for c in target_comps if c.replicas >= min_replicas)
    return (passing / len(target_comps)) * 100.0


def _check_max_utilization(graph: InfraGraph, params: dict) -> float:
    """Check that no component exceeds N% utilization.

    Params:
        max_percent: float - maximum utilization percentage (default: 80)

    Returns score 0-100 based on fraction of components under the threshold.
    """
    max_percent = float(params.get("max_percent", 80))

    if not graph.components:
        return 100.0

    passing = sum(
        1 for c in graph.components.values()
        if c.utilization() <= max_percent
    )
    return (passing / len(graph.components)) * 100.0


def _check_encryption_coverage(graph: InfraGraph, params: dict) -> float:
    """Check percentage of components with encryption enabled.

    Params:
        min_percent: float - minimum percentage with encryption (default: 100)

    Returns score 0-100 based on fraction with encryption_at_rest or encryption_in_transit.
    """
    if not graph.components:
        return 100.0

    encrypted = sum(
        1 for c in graph.components.values()
        if c.security.encryption_at_rest or c.security.encryption_in_transit
    )
    coverage = (encrypted / len(graph.components)) * 100.0
    min_percent = float(params.get("min_percent", 100))

    if min_percent <= 0:
        return 100.0

    return min(100.0, (coverage / min_percent) * 100.0)


def _check_failover_coverage(graph: InfraGraph, params: dict) -> float:
    """Check percentage of components with failover enabled.

    Params:
        min_percent: float - minimum percentage with failover (default: 100)

    Returns score 0-100 based on fraction with failover enabled.
    """
    if not graph.components:
        return 100.0

    with_failover = sum(
        1 for c in graph.components.values()
        if c.failover.enabled
    )
    coverage = (with_failover / len(graph.components)) * 100.0
    min_percent = float(params.get("min_percent", 100))

    if min_percent <= 0:
        return 100.0

    return min(100.0, (coverage / min_percent) * 100.0)


def _check_cb_coverage(graph: InfraGraph, params: dict) -> float:
    """Check percentage of dependency edges with circuit breakers.

    Params:
        min_percent: float - minimum percentage with CB enabled (default: 100)

    Returns score 0-100 based on fraction with circuit breakers.
    """
    edges = graph.all_dependency_edges()
    if not edges:
        return 100.0  # No dependencies -> no CB needed

    cb_enabled = sum(1 for e in edges if e.circuit_breaker.enabled)
    coverage = (cb_enabled / len(edges)) * 100.0
    min_percent = float(params.get("min_percent", 100))

    if min_percent <= 0:
        return 100.0

    return min(100.0, (coverage / min_percent) * 100.0)


def _check_backup_coverage(graph: InfraGraph, params: dict) -> float:
    """Check percentage of components with backups enabled.

    Params:
        min_percent: float - minimum percentage with backups (default: 100)
        component_type: str - optional, filter to specific type

    Returns score 0-100 based on fraction with backups.
    """
    comp_type_str = params.get("component_type", "")
    if comp_type_str:
        target_comps = _filter_components_by_type(graph, comp_type_str)
    else:
        target_comps = list(graph.components.values())

    if not target_comps:
        return 100.0

    with_backup = sum(
        1 for c in target_comps
        if c.security.backup_enabled
    )
    coverage = (with_backup / len(target_comps)) * 100.0
    min_percent = float(params.get("min_percent", 100))

    if min_percent <= 0:
        return 100.0

    return min(100.0, (coverage / min_percent) * 100.0)


def _check_max_chain_depth(graph: InfraGraph, params: dict) -> float:
    """Check that the maximum dependency chain depth is under N.

    Params:
        max_depth: int - maximum allowed chain depth (default: 5)

    Returns 100 if under threshold, scaled down otherwise.
    """
    max_depth = int(params.get("max_depth", 5))

    critical_paths = graph.get_critical_paths()
    if not critical_paths:
        return 100.0

    actual_depth = len(critical_paths[0])

    if actual_depth <= max_depth:
        return 100.0

    # Scale: each level over = -20 points
    over = actual_depth - max_depth
    return max(0.0, 100.0 - over * 20.0)


def _check_no_public_database(graph: InfraGraph, params: dict) -> float:
    """Check that no database is on a commonly public port.

    Params:
        forbidden_ports: list[int] - ports considered public-facing
                                     (default: [80, 443, 8080, 8443])

    Returns 100 if no DB is on a forbidden port, scaled down otherwise.
    """
    forbidden_ports = params.get("forbidden_ports", [80, 443, 8080, 8443])
    if isinstance(forbidden_ports, str):
        forbidden_ports = [int(p.strip()) for p in forbidden_ports.split(",")]

    databases = [
        c for c in graph.components.values()
        if c.type == ComponentType.DATABASE
    ]

    if not databases:
        return 100.0

    violating = sum(
        1 for db in databases
        if db.port in forbidden_ports
    )

    if violating == 0:
        return 100.0

    return max(0.0, 100.0 - (violating / len(databases)) * 100.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _filter_components_by_type(
    graph: InfraGraph, comp_type_str: str
) -> list:
    """Filter components by type string (case-insensitive)."""
    if not comp_type_str:
        return list(graph.components.values())

    try:
        comp_type = ComponentType(comp_type_str.lower())
    except ValueError:
        logger.warning("Unknown component type '%s', returning empty list", comp_type_str)
        return []

    return [
        c for c in graph.components.values()
        if c.type == comp_type
    ]


# ---------------------------------------------------------------------------
# Custom Scoring Engine
# ---------------------------------------------------------------------------

class CustomScoringEngine:
    """User-defined scoring criteria engine.

    Evaluates an InfraGraph against a set of scoring rules, either built-in
    check functions or user-provided callables.
    """

    BUILT_IN_CHECKS: dict[str, Callable[[InfraGraph, dict], float]] = {
        "min_replicas": _check_min_replicas,
        "max_utilization": _check_max_utilization,
        "encryption_coverage": _check_encryption_coverage,
        "failover_coverage": _check_failover_coverage,
        "cb_coverage": _check_cb_coverage,
        "backup_coverage": _check_backup_coverage,
        "max_chain_depth": _check_max_chain_depth,
        "no_public_database": _check_no_public_database,
    }

    def __init__(
        self,
        graph: InfraGraph,
        rules: list[ScoringRule] | None = None,
        model_name: str = "custom",
    ) -> None:
        self.graph = graph
        self.rules = rules or []
        self.model_name = model_name

    def evaluate(self) -> CustomScoringResult:
        """Evaluate all rules against the graph and compute scores."""
        rule_results: list[dict] = []
        total_weight = 0.0
        weighted_sum = 0.0

        for rule in self.rules:
            check_fn = self.BUILT_IN_CHECKS.get(rule.check_fn)
            if check_fn is None:
                logger.warning(
                    "Unknown check function '%s' for rule '%s', skipping",
                    rule.check_fn, rule.name,
                )
                rule_results.append({
                    "name": rule.name,
                    "score": 0.0,
                    "weight": rule.weight,
                    "description": rule.description,
                    "passed": False,
                    "error": f"Unknown check: {rule.check_fn}",
                })
                continue

            try:
                score = check_fn(self.graph, rule.params)
            except Exception as exc:
                logger.warning(
                    "Check '%s' for rule '%s' raised: %s",
                    rule.check_fn, rule.name, exc,
                )
                score = 0.0

            score = max(0.0, min(100.0, score))
            passed = score >= 80.0  # 80% threshold for "passing"

            rule_results.append({
                "name": rule.name,
                "score": round(score, 1),
                "weight": rule.weight,
                "description": rule.description,
                "passed": passed,
            })

            total_weight += rule.weight
            weighted_sum += score * rule.weight

        if total_weight > 0:
            weighted_score = weighted_sum / total_weight
        else:
            weighted_score = 0.0

        # Total score is the weighted average
        total_score = max(0.0, min(100.0, weighted_score))

        return CustomScoringResult(
            model_name=self.model_name,
            total_score=round(total_score, 1),
            rules=rule_results,
            weighted_score=round(weighted_score, 1),
        )

    @classmethod
    def from_yaml(
        cls,
        graph: InfraGraph,
        config_path: Path,
    ) -> CustomScoringEngine:
        """Load scoring rules from YAML config.

        Expected format:
            model_name: "my-policy"  # optional
            rules:
              - name: "All databases replicated"
                check: min_replicas
                params: {component_type: database, min: 2}
                weight: 2.0
                description: "Databases must have at least 2 replicas"
              - name: "No high utilization"
                check: max_utilization
                params: {max_percent: 80}
                weight: 1.0
        """
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(
                f"Expected YAML mapping at top level, got {type(raw).__name__}"
            )

        model_name = raw.get("model_name", config_path.stem)
        raw_rules = raw.get("rules", [])
        if not isinstance(raw_rules, list):
            raise ValueError("'rules' must be a list")

        rules: list[ScoringRule] = []
        for idx, entry in enumerate(raw_rules):
            if not isinstance(entry, dict):
                raise ValueError(f"Rule entry {idx} must be a mapping")

            name = entry.get("name", f"rule-{idx}")
            check = entry.get("check", "")
            if not check:
                raise ValueError(
                    f"Rule '{name}' is missing 'check' field"
                )

            rules.append(ScoringRule(
                name=name,
                description=entry.get("description", ""),
                weight=float(entry.get("weight", 1.0)),
                check_fn=check,
                params=entry.get("params", {}),
            ))

        return cls(graph=graph, rules=rules, model_name=model_name)
