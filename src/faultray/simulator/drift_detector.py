# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Dependency Drift Detection Engine.

Detects configuration drift that degrades resilience over time.
Compares current infrastructure state against a baseline (golden config)
and identifies changes that weaken resilience posture.

Common drift patterns:
- Replicas reduced during cost-cutting
- Circuit breakers disabled for debugging and never re-enabled
- Autoscaling limits lowered
- Health checks weakened or removed
- New SPOF dependencies added without redundancy
- Failover configurations disabled
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from faultray.model.components import Component, Dependency
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


class DriftType(str, Enum):
    """Types of infrastructure drift that can be detected."""

    REPLICA_REDUCTION = "replica_reduction"
    CIRCUIT_BREAKER_DISABLED = "circuit_breaker_disabled"
    AUTOSCALING_DISABLED = "autoscaling_disabled"
    HEALTH_CHECK_REMOVED = "health_check_removed"
    FAILOVER_DISABLED = "failover_disabled"
    NEW_SPOF_INTRODUCED = "new_spof_introduced"
    DEPENDENCY_ADDED = "dependency_added"
    DEPENDENCY_REMOVED = "dependency_removed"
    COMPONENT_ADDED = "component_added"
    COMPONENT_REMOVED = "component_removed"
    CAPACITY_REDUCED = "capacity_reduced"
    SECURITY_WEAKENED = "security_weakened"
    CONFIGURATION_CHANGED = "configuration_changed"


class DriftSeverity(str, Enum):
    """Severity levels for drift events."""

    CRITICAL = "critical"  # Immediate resilience risk
    HIGH = "high"  # Significant degradation
    MEDIUM = "medium"  # Notable change
    LOW = "low"  # Minor drift
    INFO = "info"  # Informational only


@dataclass
class DriftEvent:
    """A single detected drift between baseline and current state."""

    drift_type: DriftType
    severity: DriftSeverity
    component_id: str
    component_name: str
    field: str
    baseline_value: Any
    current_value: Any
    description: str
    resilience_impact: float  # Estimated score impact, negative = bad
    remediation: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DriftReport:
    """Full report of all detected drift events."""

    baseline_timestamp: datetime
    current_timestamp: datetime
    total_drifts: int
    critical_drifts: int
    high_drifts: int
    events: list[DriftEvent]
    baseline_resilience_score: float
    current_resilience_score: float
    score_delta: float
    drift_velocity: float  # Rate of drift per day
    risk_trend: str  # "improving", "stable", "degrading", "critical_degradation"
    summary: str

    def to_dict(self) -> dict:
        """Serialize the report to a dictionary for JSON output."""
        return {
            "baseline_timestamp": self.baseline_timestamp.isoformat(),
            "current_timestamp": self.current_timestamp.isoformat(),
            "total_drifts": self.total_drifts,
            "critical_drifts": self.critical_drifts,
            "high_drifts": self.high_drifts,
            "baseline_resilience_score": self.baseline_resilience_score,
            "current_resilience_score": self.current_resilience_score,
            "score_delta": self.score_delta,
            "drift_velocity": self.drift_velocity,
            "risk_trend": self.risk_trend,
            "summary": self.summary,
            "events": [
                {
                    "drift_type": e.drift_type.value,
                    "severity": e.severity.value,
                    "component_id": e.component_id,
                    "component_name": e.component_name,
                    "field": e.field,
                    "baseline_value": _serialize_value(e.baseline_value),
                    "current_value": _serialize_value(e.current_value),
                    "description": e.description,
                    "resilience_impact": e.resilience_impact,
                    "remediation": e.remediation,
                    "detected_at": e.detected_at.isoformat(),
                }
                for e in self.events
            ],
        }


@dataclass
class DriftBaseline:
    """A saved baseline snapshot of infrastructure state."""

    infrastructure_id: str
    timestamp: datetime
    components: dict  # Serialized component state
    edges: list  # Serialized dependency edges
    resilience_score: float
    genome_hash: str | None = None
    metadata: dict = field(default_factory=dict)


def _serialize_value(val: Any) -> Any:
    """Serialize a value for JSON output, handling non-serializable types."""
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    if isinstance(val, dict):
        return {k: _serialize_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_serialize_value(v) for v in val]
    return str(val)


def _compute_infrastructure_id(graph: InfraGraph) -> str:
    """Compute a stable hash ID for an infrastructure graph."""
    data = json.dumps(graph.to_dict(), sort_keys=True, default=str)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def _serialize_component(comp: Component) -> dict:
    """Serialize a component to a baseline-compatible dict."""
    data = comp.model_dump()
    # Convert enums to their values
    if hasattr(data.get("type"), "value"):
        data["type"] = data["type"].value
    if hasattr(data.get("health"), "value"):
        data["health"] = data["health"].value
    return data


def _serialize_edge(dep: Dependency) -> dict:
    """Serialize a dependency edge to a baseline-compatible dict."""
    return dep.model_dump()


class DriftDetector:
    """Detects configuration drift between a baseline and current infrastructure.

    Like ``git diff`` but for infrastructure resilience — compares a saved
    golden configuration (baseline) against the current state and identifies
    changes that weaken or strengthen the resilience posture.
    """

    def save_baseline(self, graph: InfraGraph, path: Path) -> DriftBaseline:
        """Save the current infrastructure state as a golden baseline.

        Args:
            graph: The current infrastructure graph to snapshot.
            path: File path to save the baseline JSON.

        Returns:
            The created DriftBaseline object.
        """
        now = datetime.now(timezone.utc)
        infra_id = _compute_infrastructure_id(graph)

        components: dict[str, dict] = {}
        for comp_id, comp in graph.components.items():
            components[comp_id] = _serialize_component(comp)

        edges: list[dict] = []
        for dep in graph.all_dependency_edges():
            edges.append(_serialize_edge(dep))

        baseline = DriftBaseline(
            infrastructure_id=infra_id,
            timestamp=now,
            components=components,
            edges=edges,
            resilience_score=graph.resilience_score(),
            metadata={
                "total_components": len(graph.components),
                "total_dependencies": len(edges),
            },
        )

        baseline_data = {
            "version": "1.0",
            "infrastructure_id": baseline.infrastructure_id,
            "timestamp": baseline.timestamp.isoformat(),
            "resilience_score": baseline.resilience_score,
            "genome_hash": baseline.genome_hash,
            "metadata": baseline.metadata,
            "components": baseline.components,
            "edges": baseline.edges,
        }

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(baseline_data, indent=2, default=str))
        logger.info("Baseline saved to %s (infra_id=%s)", path, infra_id)

        return baseline

    def load_baseline(self, path: Path) -> DriftBaseline:
        """Load a previously saved baseline from a JSON file.

        Args:
            path: Path to the baseline JSON file.

        Returns:
            The loaded DriftBaseline object.

        Raises:
            FileNotFoundError: If the baseline file does not exist.
            ValueError: If the baseline file is malformed.
        """
        if not path.exists():
            raise FileNotFoundError(f"Baseline file not found: {path}")

        data = json.loads(path.read_text(encoding="utf-8"))

        version = data.get("version", "1.0")
        if version != "1.0":
            logger.warning(
                "Baseline version %s may not be fully compatible", version
            )

        timestamp_str = data.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            timestamp = datetime.now(timezone.utc)

        return DriftBaseline(
            infrastructure_id=data.get("infrastructure_id", "unknown"),
            timestamp=timestamp,
            components=data.get("components", {}),
            edges=data.get("edges", []),
            resilience_score=float(data.get("resilience_score", 0.0)),
            genome_hash=data.get("genome_hash"),
            metadata=data.get("metadata", {}),
        )

    def detect(self, baseline: DriftBaseline, current: InfraGraph) -> DriftReport:
        """Compare baseline state against current infrastructure and find drifts.

        Args:
            baseline: The saved golden baseline.
            current: The current infrastructure graph.

        Returns:
            A DriftReport with all detected drift events.
        """
        now = datetime.now(timezone.utc)
        events: list[DriftEvent] = []

        # Detect component-level drifts
        self._detect_component_drifts(baseline, current, events)

        # Detect dependency/edge-level drifts
        self._detect_edge_drifts(baseline, current, events)

        # Detect new SPOF introductions
        self._detect_new_spofs(baseline, current, events)

        # Sort by severity (critical first)
        severity_order = {
            DriftSeverity.CRITICAL: 0,
            DriftSeverity.HIGH: 1,
            DriftSeverity.MEDIUM: 2,
            DriftSeverity.LOW: 3,
            DriftSeverity.INFO: 4,
        }
        events.sort(key=lambda e: severity_order[e.severity])

        # Calculate metrics
        current_score = current.resilience_score()
        score_delta = round(current_score - baseline.resilience_score, 2)

        critical_count = sum(
            1 for e in events if e.severity == DriftSeverity.CRITICAL
        )
        high_count = sum(
            1 for e in events if e.severity == DriftSeverity.HIGH
        )

        # Calculate drift velocity (drifts per day)
        days_elapsed = max(
            (now - baseline.timestamp).total_seconds() / 86400.0, 0.001
        )
        drift_velocity = round(len(events) / days_elapsed, 2)

        # Determine risk trend
        risk_trend = self._determine_risk_trend(
            score_delta, critical_count, high_count, len(events)
        )

        # Build summary
        summary = self._build_summary(
            len(events), critical_count, high_count,
            baseline.resilience_score, current_score, score_delta, risk_trend,
        )

        return DriftReport(
            baseline_timestamp=baseline.timestamp,
            current_timestamp=now,
            total_drifts=len(events),
            critical_drifts=critical_count,
            high_drifts=high_count,
            events=events,
            baseline_resilience_score=baseline.resilience_score,
            current_resilience_score=current_score,
            score_delta=score_delta,
            drift_velocity=drift_velocity,
            risk_trend=risk_trend,
            summary=summary,
        )

    def detect_from_file(
        self, baseline_path: Path, current_yaml: Path
    ) -> DriftReport:
        """Convenience method to detect drift from file paths.

        Args:
            baseline_path: Path to the saved baseline JSON.
            current_yaml: Path to the current infrastructure YAML/JSON.

        Returns:
            A DriftReport with all detected drift events.
        """
        from faultray.model.loader import load_yaml

        baseline = self.load_baseline(baseline_path)

        if str(current_yaml).endswith((".yaml", ".yml")):
            current_graph = load_yaml(current_yaml)
        else:
            current_graph = InfraGraph.load(current_yaml)

        return self.detect(baseline, current_graph)

    def auto_detect_severity(
        self, drift_type: DriftType, baseline_val: Any, current_val: Any
    ) -> DriftSeverity:
        """Auto-classify drift severity based on type and values.

        Args:
            drift_type: The type of drift detected.
            baseline_val: The original value from the baseline.
            current_val: The current value.

        Returns:
            The auto-classified severity level.
        """
        if drift_type == DriftType.FAILOVER_DISABLED:
            return DriftSeverity.CRITICAL

        if drift_type == DriftType.CIRCUIT_BREAKER_DISABLED:
            return DriftSeverity.HIGH

        if drift_type == DriftType.AUTOSCALING_DISABLED:
            return DriftSeverity.HIGH

        if drift_type == DriftType.COMPONENT_REMOVED:
            return DriftSeverity.HIGH

        if drift_type == DriftType.REPLICA_REDUCTION:
            if isinstance(baseline_val, (int, float)) and isinstance(
                current_val, (int, float)
            ):
                if current_val <= 1:
                    return DriftSeverity.CRITICAL
                ratio = current_val / max(baseline_val, 1)
                if ratio <= 0.5:
                    return DriftSeverity.HIGH
                return DriftSeverity.MEDIUM
            return DriftSeverity.MEDIUM

        if drift_type == DriftType.CAPACITY_REDUCED:
            if isinstance(baseline_val, (int, float)) and isinstance(
                current_val, (int, float)
            ):
                if baseline_val > 0:
                    ratio = current_val / baseline_val
                    if ratio <= 0.5:
                        return DriftSeverity.HIGH
                    return DriftSeverity.MEDIUM
            return DriftSeverity.MEDIUM

        if drift_type == DriftType.NEW_SPOF_INTRODUCED:
            return DriftSeverity.HIGH

        if drift_type == DriftType.HEALTH_CHECK_REMOVED:
            return DriftSeverity.MEDIUM

        if drift_type == DriftType.SECURITY_WEAKENED:
            return DriftSeverity.MEDIUM

        if drift_type in (
            DriftType.DEPENDENCY_ADDED,
            DriftType.DEPENDENCY_REMOVED,
        ):
            return DriftSeverity.LOW

        if drift_type == DriftType.COMPONENT_ADDED:
            return DriftSeverity.INFO

        if drift_type == DriftType.CONFIGURATION_CHANGED:
            return DriftSeverity.LOW

        return DriftSeverity.LOW

    def calculate_resilience_impact(
        self, drift_event: DriftEvent, graph: InfraGraph
    ) -> float:
        """Estimate the resilience score impact of a drift event.

        Args:
            drift_event: The drift event to evaluate.
            graph: The current infrastructure graph for context.

        Returns:
            Estimated score impact (negative means degradation).
        """
        comp = graph.get_component(drift_event.component_id)
        dependents_count = 0
        if comp:
            dependents_count = len(graph.get_dependents(comp.id))

        base_impact = {
            DriftType.FAILOVER_DISABLED: -10.0,
            DriftType.CIRCUIT_BREAKER_DISABLED: -5.0,
            DriftType.AUTOSCALING_DISABLED: -5.0,
            DriftType.REPLICA_REDUCTION: -7.0,
            DriftType.NEW_SPOF_INTRODUCED: -8.0,
            DriftType.COMPONENT_REMOVED: -5.0,
            DriftType.HEALTH_CHECK_REMOVED: -3.0,
            DriftType.CAPACITY_REDUCED: -3.0,
            DriftType.SECURITY_WEAKENED: -2.0,
            DriftType.DEPENDENCY_ADDED: -1.0,
            DriftType.DEPENDENCY_REMOVED: -1.0,
            DriftType.COMPONENT_ADDED: 0.0,
            DriftType.CONFIGURATION_CHANGED: -1.0,
        }.get(drift_event.drift_type, -1.0)

        # Scale impact by number of dependents
        if dependents_count > 2:
            base_impact *= 1.0 + (dependents_count - 2) * 0.2

        return round(base_impact, 2)

    # ------------------------------------------------------------------
    # Internal detection methods
    # ------------------------------------------------------------------

    def _detect_component_drifts(
        self,
        baseline: DriftBaseline,
        current: InfraGraph,
        events: list[DriftEvent],
    ) -> None:
        """Detect drifts at the component level."""
        baseline_ids = set(baseline.components.keys())
        current_ids = set(current.components.keys())

        # Removed components
        for comp_id in baseline_ids - current_ids:
            bcomp = baseline.components[comp_id]
            events.append(
                DriftEvent(
                    drift_type=DriftType.COMPONENT_REMOVED,
                    severity=DriftSeverity.HIGH,
                    component_id=comp_id,
                    component_name=bcomp.get("name", comp_id),
                    field="component",
                    baseline_value=comp_id,
                    current_value=None,
                    description=f"Component '{comp_id}' was removed from infrastructure",
                    resilience_impact=-5.0,
                    remediation=f"Verify that removing '{comp_id}' was intentional and "
                    "that dependent services have been updated.",
                )
            )

        # Added components
        for comp_id in current_ids - baseline_ids:
            comp = current.get_component(comp_id)
            if comp is None:
                continue
            events.append(
                DriftEvent(
                    drift_type=DriftType.COMPONENT_ADDED,
                    severity=DriftSeverity.INFO,
                    component_id=comp_id,
                    component_name=comp.name,
                    field="component",
                    baseline_value=None,
                    current_value=comp_id,
                    description=f"New component '{comp_id}' added to infrastructure",
                    resilience_impact=0.0,
                    remediation="Ensure the new component has proper redundancy, "
                    "monitoring, and failover configured.",
                )
            )

        # Changed components (present in both)
        for comp_id in baseline_ids & current_ids:
            bcomp = baseline.components[comp_id]
            ccomp = current.get_component(comp_id)
            if ccomp is None:
                continue

            self._compare_component(comp_id, bcomp, ccomp, current, events)

    def _compare_component(
        self,
        comp_id: str,
        bcomp: dict,
        ccomp: Component,
        graph: InfraGraph,
        events: list[DriftEvent],
    ) -> None:
        """Compare a single component between baseline and current state."""
        comp_name = ccomp.name

        # 1. Replica changes
        baseline_replicas = bcomp.get("replicas", 1)
        if ccomp.replicas < baseline_replicas:
            severity = self.auto_detect_severity(
                DriftType.REPLICA_REDUCTION, baseline_replicas, ccomp.replicas
            )
            # Upgrade to CRITICAL if component has many dependents
            dependents = graph.get_dependents(comp_id)
            if ccomp.replicas <= 1 and len(dependents) > 2:
                severity = DriftSeverity.CRITICAL

            impact = self.calculate_resilience_impact(
                DriftEvent(
                    drift_type=DriftType.REPLICA_REDUCTION,
                    severity=severity,
                    component_id=comp_id,
                    component_name=comp_name,
                    field="replicas",
                    baseline_value=baseline_replicas,
                    current_value=ccomp.replicas,
                    description="",
                    resilience_impact=0.0,
                    remediation="",
                ),
                graph,
            )

            events.append(
                DriftEvent(
                    drift_type=DriftType.REPLICA_REDUCTION,
                    severity=severity,
                    component_id=comp_id,
                    component_name=comp_name,
                    field="replicas",
                    baseline_value=baseline_replicas,
                    current_value=ccomp.replicas,
                    description=(
                        f"Replicas reduced from {baseline_replicas} to "
                        f"{ccomp.replicas} on '{comp_name}'"
                    ),
                    resilience_impact=impact,
                    remediation=(
                        f"Restore replicas to {baseline_replicas} or ensure "
                        "failover mechanisms compensate for reduced capacity."
                    ),
                )
            )

        # 2. Circuit breaker on edges targeting this component
        # (handled in _detect_edge_drifts)

        # 3. Autoscaling
        baseline_as = bcomp.get("autoscaling", {})
        if baseline_as.get("enabled", False) and not ccomp.autoscaling.enabled:
            events.append(
                DriftEvent(
                    drift_type=DriftType.AUTOSCALING_DISABLED,
                    severity=DriftSeverity.HIGH,
                    component_id=comp_id,
                    component_name=comp_name,
                    field="autoscaling.enabled",
                    baseline_value=True,
                    current_value=False,
                    description=(
                        f"Autoscaling was disabled on '{comp_name}'"
                    ),
                    resilience_impact=-5.0,
                    remediation=(
                        "Re-enable autoscaling to maintain elastic capacity. "
                        "If disabled for debugging, create a ticket to re-enable."
                    ),
                )
            )

        # 4. Failover
        baseline_fo = bcomp.get("failover", {})
        if baseline_fo.get("enabled", False) and not ccomp.failover.enabled:
            events.append(
                DriftEvent(
                    drift_type=DriftType.FAILOVER_DISABLED,
                    severity=DriftSeverity.CRITICAL,
                    component_id=comp_id,
                    component_name=comp_name,
                    field="failover.enabled",
                    baseline_value=True,
                    current_value=False,
                    description=(
                        f"Failover was disabled on '{comp_name}' — "
                        "this is a critical resilience risk"
                    ),
                    resilience_impact=-10.0,
                    remediation=(
                        "Re-enable failover immediately. This component has no "
                        "automatic recovery mechanism."
                    ),
                )
            )

        # 5. Health check interval
        baseline_fo_interval = baseline_fo.get(
            "health_check_interval_seconds", 0
        )
        current_fo_interval = ccomp.failover.health_check_interval_seconds
        if baseline_fo_interval > 0 and current_fo_interval > baseline_fo_interval * 2:
            events.append(
                DriftEvent(
                    drift_type=DriftType.HEALTH_CHECK_REMOVED,
                    severity=DriftSeverity.MEDIUM,
                    component_id=comp_id,
                    component_name=comp_name,
                    field="failover.health_check_interval_seconds",
                    baseline_value=baseline_fo_interval,
                    current_value=current_fo_interval,
                    description=(
                        f"Health check interval increased significantly on "
                        f"'{comp_name}': {baseline_fo_interval}s -> "
                        f"{current_fo_interval}s"
                    ),
                    resilience_impact=-3.0,
                    remediation=(
                        f"Restore health check interval to {baseline_fo_interval}s "
                        "or document why the longer interval is acceptable."
                    ),
                )
            )

        # 6. Capacity reductions
        self._check_capacity_drift(comp_id, comp_name, bcomp, ccomp, graph, events)

        # 7. Security weakening
        self._check_security_drift(comp_id, comp_name, bcomp, ccomp, events)

    def _check_capacity_drift(
        self,
        comp_id: str,
        comp_name: str,
        bcomp: dict,
        ccomp: Component,
        graph: InfraGraph,
        events: list[DriftEvent],
    ) -> None:
        """Check for capacity-related drifts."""
        baseline_cap = bcomp.get("capacity", {})

        capacity_fields = [
            ("max_connections", ccomp.capacity.max_connections),
            ("max_rps", ccomp.capacity.max_rps),
            ("max_memory_mb", ccomp.capacity.max_memory_mb),
            ("max_disk_gb", ccomp.capacity.max_disk_gb),
        ]

        for field_name, current_val in capacity_fields:
            baseline_val = baseline_cap.get(field_name)
            if baseline_val is None:
                continue
            if isinstance(baseline_val, (int, float)) and current_val < baseline_val:
                severity = self.auto_detect_severity(
                    DriftType.CAPACITY_REDUCED, baseline_val, current_val
                )
                events.append(
                    DriftEvent(
                        drift_type=DriftType.CAPACITY_REDUCED,
                        severity=severity,
                        component_id=comp_id,
                        component_name=comp_name,
                        field=f"capacity.{field_name}",
                        baseline_value=baseline_val,
                        current_value=current_val,
                        description=(
                            f"Capacity '{field_name}' reduced on '{comp_name}': "
                            f"{baseline_val} -> {current_val}"
                        ),
                        resilience_impact=-3.0,
                        remediation=(
                            f"Restore {field_name} to {baseline_val} or confirm "
                            "the reduction is safe under peak load."
                        ),
                    )
                )

    def _check_security_drift(
        self,
        comp_id: str,
        comp_name: str,
        bcomp: dict,
        ccomp: Component,
        events: list[DriftEvent],
    ) -> None:
        """Check for security-related drifts."""
        baseline_sec = bcomp.get("security", {})
        if not baseline_sec:
            return

        security_fields = [
            ("encryption_at_rest", ccomp.security.encryption_at_rest),
            ("encryption_in_transit", ccomp.security.encryption_in_transit),
            ("waf_protected", ccomp.security.waf_protected),
            ("rate_limiting", ccomp.security.rate_limiting),
            ("auth_required", ccomp.security.auth_required),
            ("backup_enabled", ccomp.security.backup_enabled),
        ]

        for field_name, current_val in security_fields:
            baseline_val = baseline_sec.get(field_name)
            if baseline_val is True and current_val is False:
                events.append(
                    DriftEvent(
                        drift_type=DriftType.SECURITY_WEAKENED,
                        severity=DriftSeverity.MEDIUM,
                        component_id=comp_id,
                        component_name=comp_name,
                        field=f"security.{field_name}",
                        baseline_value=True,
                        current_value=False,
                        description=(
                            f"Security feature '{field_name}' was disabled "
                            f"on '{comp_name}'"
                        ),
                        resilience_impact=-2.0,
                        remediation=(
                            f"Re-enable '{field_name}' on '{comp_name}'. "
                            "Security features should not be disabled without "
                            "a documented exception."
                        ),
                    )
                )

    def _detect_edge_drifts(
        self,
        baseline: DriftBaseline,
        current: InfraGraph,
        events: list[DriftEvent],
    ) -> None:
        """Detect drifts at the dependency edge level."""
        # Build edge maps keyed by (source, target)
        baseline_edges: dict[tuple[str, str], dict] = {}
        for edge in baseline.edges:
            key = (edge.get("source_id", ""), edge.get("target_id", ""))
            baseline_edges[key] = edge

        current_edges: dict[tuple[str, str], Dependency] = {}
        for dep in current.all_dependency_edges():
            key = (dep.source_id, dep.target_id)
            current_edges[key] = dep

        baseline_keys = set(baseline_edges.keys())
        current_keys = set(current_edges.keys())

        # Removed edges
        for key in baseline_keys - current_keys:
            source_id, target_id = key
            events.append(
                DriftEvent(
                    drift_type=DriftType.DEPENDENCY_REMOVED,
                    severity=DriftSeverity.LOW,
                    component_id=source_id,
                    component_name=source_id,
                    field=f"dependency:{source_id}->{target_id}",
                    baseline_value=f"{source_id} -> {target_id}",
                    current_value=None,
                    description=(
                        f"Dependency from '{source_id}' to '{target_id}' "
                        "was removed"
                    ),
                    resilience_impact=-1.0,
                    remediation=(
                        "Verify the dependency removal was intentional and "
                        "that the service can operate without it."
                    ),
                )
            )

        # Added edges
        for key in current_keys - baseline_keys:
            source_id, target_id = key
            events.append(
                DriftEvent(
                    drift_type=DriftType.DEPENDENCY_ADDED,
                    severity=DriftSeverity.LOW,
                    component_id=source_id,
                    component_name=source_id,
                    field=f"dependency:{source_id}->{target_id}",
                    baseline_value=None,
                    current_value=f"{source_id} -> {target_id}",
                    description=(
                        f"New dependency added: '{source_id}' -> '{target_id}'"
                    ),
                    resilience_impact=-1.0,
                    remediation=(
                        "Ensure the new dependency has circuit breakers, "
                        "retries, and timeout configured."
                    ),
                )
            )

        # Changed edges (circuit breaker changes)
        for key in baseline_keys & current_keys:
            bedge = baseline_edges[key]
            cedge = current_edges[key]
            source_id, target_id = key

            baseline_cb = bedge.get("circuit_breaker", {})
            if baseline_cb.get("enabled", False) and not cedge.circuit_breaker.enabled:
                # Check dependent count for severity
                dependents = current.get_dependents(target_id)
                severity = DriftSeverity.HIGH
                if len(dependents) > 2:
                    severity = DriftSeverity.CRITICAL

                events.append(
                    DriftEvent(
                        drift_type=DriftType.CIRCUIT_BREAKER_DISABLED,
                        severity=severity,
                        component_id=source_id,
                        component_name=source_id,
                        field=f"circuit_breaker:{source_id}->{target_id}",
                        baseline_value=True,
                        current_value=False,
                        description=(
                            f"Circuit breaker disabled on "
                            f"'{source_id}' -> '{target_id}'"
                        ),
                        resilience_impact=-5.0,
                        remediation=(
                            "Re-enable the circuit breaker to prevent cascade "
                            "failures. If disabled for debugging, create a "
                            "ticket to re-enable."
                        ),
                    )
                )

    def _detect_new_spofs(
        self,
        baseline: DriftBaseline,
        current: InfraGraph,
        events: list[DriftEvent],
    ) -> None:
        """Detect new single points of failure introduced since baseline."""
        baseline_ids = set(baseline.components.keys())

        for comp_id, comp in current.components.items():
            # Only check components not in baseline (truly new)
            if comp_id in baseline_ids:
                continue

            dependents = current.get_dependents(comp_id)
            if comp.replicas <= 1 and len(dependents) > 0:
                events.append(
                    DriftEvent(
                        drift_type=DriftType.NEW_SPOF_INTRODUCED,
                        severity=DriftSeverity.HIGH,
                        component_id=comp_id,
                        component_name=comp.name,
                        field="replicas",
                        baseline_value=None,
                        current_value=comp.replicas,
                        description=(
                            f"New SPOF: '{comp.name}' has {comp.replicas} "
                            f"replica(s) but {len(dependents)} dependent(s)"
                        ),
                        resilience_impact=-8.0,
                        remediation=(
                            f"Add replicas to '{comp.name}' (currently "
                            f"{comp.replicas}) or enable failover. "
                            f"{len(dependents)} service(s) depend on it."
                        ),
                    )
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_risk_trend(
        score_delta: float,
        critical_count: int,
        high_count: int,
        total_drifts: int,
    ) -> str:
        """Determine the overall risk trend based on drift metrics."""
        if critical_count > 0 or score_delta <= -10:
            return "critical_degradation"
        if high_count > 0 or score_delta < -5:
            return "degrading"
        if total_drifts == 0 or score_delta >= 0:
            if score_delta > 5:
                return "improving"
            return "stable"
        return "degrading"

    @staticmethod
    def _build_summary(
        total: int,
        critical: int,
        high: int,
        baseline_score: float,
        current_score: float,
        delta: float,
        trend: str,
    ) -> str:
        """Build a human-readable summary of the drift report."""
        if total == 0:
            return (
                f"No drift detected. Resilience score: {current_score:.1f} "
                f"(baseline: {baseline_score:.1f}). Infrastructure is stable."
            )

        parts = [f"Detected {total} drift(s)."]

        if critical > 0:
            parts.append(f"{critical} CRITICAL")
        if high > 0:
            parts.append(f"{high} HIGH")

        parts.append(
            f"Score: {baseline_score:.1f} -> {current_score:.1f} "
            f"(delta: {delta:+.1f})."
        )

        trend_labels = {
            "improving": "Risk trend: IMPROVING.",
            "stable": "Risk trend: STABLE.",
            "degrading": "Risk trend: DEGRADING.",
            "critical_degradation": "Risk trend: CRITICAL DEGRADATION.",
        }
        parts.append(trend_labels.get(trend, f"Risk trend: {trend}."))

        return " ".join(parts)
