# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Failure Mode & Effects Analysis (FMEA) Engine.

Applies the systematic FMEA methodology (used in aerospace, automotive,
and medical devices) to infrastructure resilience analysis.

For each component, FMEA evaluates:
- Severity (S): How bad is the failure? (1-10)
- Occurrence (O): How likely is the failure? (1-10)
- Detection (D): How hard is it to detect? (1-10)
- RPN = S x O x D (Risk Priority Number, 1-1000)

Higher RPN = higher priority for remediation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Failure mode catalogue per component type
# ---------------------------------------------------------------------------

_FAILURE_MODES: dict[str, list[dict[str, str]]] = {
    "server": [
        {
            "mode": "Complete crash",
            "cause": "Hardware failure or kernel panic",
            "effect_local": "Service unavailable",
            "effect_system": "Upstream services receive errors or timeouts",
        },
        {
            "mode": "Memory exhaustion (OOM)",
            "cause": "Memory leak or excessive allocation",
            "effect_local": "Process killed by OOM killer",
            "effect_system": "Requests queue and cascade upstream",
        },
        {
            "mode": "CPU saturation",
            "cause": "Runaway process or excessive load",
            "effect_local": "Response time degradation",
            "effect_system": "Increased latency in dependent services",
        },
        {
            "mode": "Disk full",
            "cause": "Log accumulation or data growth",
            "effect_local": "Cannot write logs/data, process may crash",
            "effect_system": "Data loss risk, service disruption",
        },
        {
            "mode": "Connection pool exhaustion",
            "cause": "Connection leak or traffic spike",
            "effect_local": "New requests rejected",
            "effect_system": "Upstream services receive connection errors",
        },
    ],
    "database": [
        {
            "mode": "Primary failure",
            "cause": "Hardware crash or data corruption",
            "effect_local": "All writes fail, reads may fail",
            "effect_system": "Application unable to persist data",
        },
        {
            "mode": "Replication lag",
            "cause": "High write throughput or network issues",
            "effect_local": "Read replicas serve stale data",
            "effect_system": "Data inconsistency across application",
        },
        {
            "mode": "Connection limit reached",
            "cause": "Connection leak or pool misconfiguration",
            "effect_local": "New connections refused",
            "effect_system": "Application cannot query database",
        },
        {
            "mode": "Storage exhaustion",
            "cause": "Data growth exceeding provisioned storage",
            "effect_local": "Writes fail, potential corruption",
            "effect_system": "Data loss, service outage",
        },
        {
            "mode": "Slow queries (lock contention)",
            "cause": "Missing indexes or long-running transactions",
            "effect_local": "Query latency increases dramatically",
            "effect_system": "Application timeouts and error cascades",
        },
    ],
    "cache": [
        {
            "mode": "Cache eviction storm (thundering herd)",
            "cause": "Mass key expiration or memory pressure",
            "effect_local": "Cache miss rate spikes",
            "effect_system": "Backend overwhelmed by cache-miss traffic",
        },
        {
            "mode": "Memory exhaustion",
            "cause": "Key growth or large values",
            "effect_local": "Evictions or OOM crash",
            "effect_system": "Increased load on backing store",
        },
        {
            "mode": "Connection timeout",
            "cause": "Network issue or overloaded cache server",
            "effect_local": "Cache unavailable",
            "effect_system": "All requests hit backend directly",
        },
        {
            "mode": "Data inconsistency (stale cache)",
            "cause": "Failed invalidation or race condition",
            "effect_local": "Serving outdated data",
            "effect_system": "Users see incorrect information",
        },
    ],
    "load_balancer": [
        {
            "mode": "Health check misconfiguration",
            "cause": "Incorrect health check endpoint or threshold",
            "effect_local": "Healthy backends marked unhealthy",
            "effect_system": "Traffic routed to fewer/no backends",
        },
        {
            "mode": "SSL certificate expiry",
            "cause": "Certificate renewal failure",
            "effect_local": "TLS handshake failures",
            "effect_system": "All HTTPS traffic rejected",
        },
        {
            "mode": "Connection draining failure",
            "cause": "Misconfigured drain timeout",
            "effect_local": "In-flight requests dropped during deploy",
            "effect_system": "Users experience errors during deployments",
        },
        {
            "mode": "Routing table corruption",
            "cause": "Configuration push error",
            "effect_local": "Traffic routed to wrong backends",
            "effect_system": "Service returns incorrect responses",
        },
    ],
    "queue": [
        {
            "mode": "Queue depth overflow (backpressure)",
            "cause": "Consumer lag or producer spike",
            "effect_local": "New messages rejected or dropped",
            "effect_system": "Upstream producers blocked or data lost",
        },
        {
            "mode": "Consumer lag",
            "cause": "Slow consumers or insufficient consumer count",
            "effect_local": "Processing delay increases",
            "effect_system": "End-to-end latency rises for async operations",
        },
        {
            "mode": "Message loss",
            "cause": "Broker crash without persistence or ack failure",
            "effect_local": "Messages permanently lost",
            "effect_system": "Data inconsistency, missed events",
        },
        {
            "mode": "Poison pill message",
            "cause": "Malformed message that crashes consumer",
            "effect_local": "Consumer crashes and restarts in loop",
            "effect_system": "Processing halted for affected queue",
        },
    ],
}

# Map ComponentType to failure mode catalogue key
_TYPE_TO_CATALOGUE: dict[ComponentType, str] = {
    ComponentType.LOAD_BALANCER: "load_balancer",
    ComponentType.WEB_SERVER: "server",
    ComponentType.APP_SERVER: "server",
    ComponentType.DATABASE: "database",
    ComponentType.CACHE: "cache",
    ComponentType.QUEUE: "queue",
    ComponentType.STORAGE: "database",
    ComponentType.DNS: "load_balancer",
    ComponentType.EXTERNAL_API: "server",
    ComponentType.CUSTOM: "server",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FailureMode:
    """A single identified failure mode for a component."""

    id: str
    component_id: str
    component_name: str
    mode: str
    cause: str
    effect_local: str
    effect_system: str
    severity: int
    occurrence: int
    detection: int
    rpn: int
    current_controls: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    responsible: str = ""


@dataclass
class FMEAReport:
    """Complete FMEA analysis report."""

    failure_modes: list[FailureMode] = field(default_factory=list)
    total_rpn: int = 0
    average_rpn: float = 0.0
    high_risk_count: int = 0
    medium_risk_count: int = 0
    low_risk_count: int = 0
    top_risks: list[FailureMode] = field(default_factory=list)
    rpn_by_component: dict[str, int] = field(default_factory=dict)
    rpn_by_failure_mode: dict[str, int] = field(default_factory=dict)
    improvement_priority: list[tuple[str, str, int]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class FMEAEngine:
    """Perform FMEA analysis on an infrastructure graph."""

    def analyze(self, graph: InfraGraph) -> FMEAReport:
        """Run full FMEA analysis across all components."""
        all_modes: list[FailureMode] = []
        for comp_id in graph.components:
            modes = self.analyze_component(graph, comp_id)
            all_modes.extend(modes)

        return self._build_report(all_modes)

    def analyze_component(self, graph: InfraGraph, component_id: str) -> list[FailureMode]:
        """Analyze a single component and return its failure modes."""
        comp = graph.get_component(component_id)
        if comp is None:
            return []

        catalogue_key = _TYPE_TO_CATALOGUE.get(comp.type, "server")
        templates = _FAILURE_MODES.get(catalogue_key, _FAILURE_MODES["server"])

        severity = self.calculate_severity(graph, component_id)
        occurrence = self.calculate_occurrence(graph, component_id)
        detection = self.calculate_detection(graph, component_id)

        modes: list[FailureMode] = []
        for idx, tmpl in enumerate(templates):
            # Per-mode adjustments
            mode_severity = self._adjust_severity_for_mode(severity, tmpl["mode"])
            mode_occurrence = self._adjust_occurrence_for_mode(occurrence, tmpl["mode"])
            mode_detection = detection

            rpn = mode_severity * mode_occurrence * mode_detection

            controls = self._identify_controls(graph, component_id)
            actions = self._recommend_actions(graph, component_id, mode_severity, mode_occurrence, mode_detection)

            fm = FailureMode(
                id=f"{component_id}-fm-{idx}",
                component_id=component_id,
                component_name=comp.name,
                mode=tmpl["mode"],
                cause=tmpl["cause"],
                effect_local=tmpl["effect_local"],
                effect_system=tmpl["effect_system"],
                severity=mode_severity,
                occurrence=mode_occurrence,
                detection=mode_detection,
                rpn=rpn,
                current_controls=controls,
                recommended_actions=actions,
                responsible=f"team-{component_id}",
            )
            modes.append(fm)

        return modes

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def calculate_severity(self, graph: InfraGraph, component_id: str) -> int:
        """Calculate severity score (1-10) based on impact scope.

        Factors: number of dependents, cascade depth, critical path membership.
        """
        comp = graph.get_component(component_id)
        if comp is None:
            return 1

        dependents = graph.get_dependents(component_id)
        all_affected = graph.get_all_affected(component_id)
        total = max(len(graph.components), 1)

        # Base severity from dependent count
        dep_ratio = len(all_affected) / total
        if dep_ratio >= 0.5:
            base = 9
        elif dep_ratio >= 0.3:
            base = 7
        elif dep_ratio >= 0.1:
            base = 5
        elif len(dependents) > 0:
            base = 3
        else:
            base = 1

        # Boost if on critical path
        critical_paths = graph.get_critical_paths(max_paths=20)
        on_critical = any(component_id in path for path in critical_paths)
        if on_critical and base < 10:
            base = min(10, base + 1)

        return max(1, min(10, base))

    def calculate_occurrence(self, graph: InfraGraph, component_id: str) -> int:
        """Calculate occurrence score (1-10) based on redundancy and protection.

        Lower redundancy and fewer protections = higher occurrence score.
        """
        comp = graph.get_component(component_id)
        if comp is None:
            return 5

        score = 5  # baseline

        # Replicas
        if comp.replicas >= 3:
            score -= 2
        elif comp.replicas >= 2:
            score -= 1
        else:
            score += 1  # single instance

        # Failover
        if comp.failover.enabled:
            score -= 1

        # Autoscaling
        if comp.autoscaling.enabled:
            score -= 1

        # Health checks (failover health_check_interval > 0 implies active checks)
        if comp.failover.health_check_interval_seconds > 0 and comp.failover.enabled:
            score -= 1
        elif not comp.failover.enabled:
            score += 1  # no health checks

        # High utilization increases likelihood
        util = comp.utilization()
        if util > 80:
            score += 2
        elif util > 60:
            score += 1

        return max(1, min(10, score))

    def calculate_detection(self, graph: InfraGraph, component_id: str) -> int:
        """Calculate detection score (1-10, INVERSE -- lower = better detection).

        Based on health checks, circuit breakers, monitoring.
        """
        comp = graph.get_component(component_id)
        if comp is None:
            return 8

        score = 7  # baseline: low detection

        # Health checks
        if comp.failover.enabled and comp.failover.health_check_interval_seconds > 0:
            score -= 2

        # Circuit breakers on incoming edges
        dependents = graph.get_dependents(component_id)
        cb_count = 0
        for dep in dependents:
            edge = graph.get_dependency_edge(dep.id, component_id)
            if edge and edge.circuit_breaker.enabled:
                cb_count += 1

        if cb_count > 0:
            score -= 2

        # Monitoring (proxy: if there are active metrics being reported)
        if comp.metrics.cpu_percent > 0 or comp.metrics.memory_percent > 0:
            score -= 1  # metrics are being collected

        return max(1, min(10, score))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _adjust_severity_for_mode(self, base: int, mode: str) -> int:
        """Fine-tune severity based on specific failure mode."""
        mode_lower = mode.lower()
        if "complete" in mode_lower or "primary failure" in mode_lower or "crash" in mode_lower:
            return max(1, min(10, base + 1))
        if "degraded" in mode_lower or "lag" in mode_lower or "slow" in mode_lower:
            return max(1, min(10, base - 1))
        if "stale" in mode_lower or "inconsistency" in mode_lower:
            return max(1, min(10, base - 1))
        return base

    def _adjust_occurrence_for_mode(self, base: int, mode: str) -> int:
        """Fine-tune occurrence based on specific failure mode."""
        mode_lower = mode.lower()
        if "exhaustion" in mode_lower or "full" in mode_lower:
            return max(1, min(10, base + 1))
        if "corruption" in mode_lower or "expiry" in mode_lower:
            return max(1, min(10, base - 1))
        return base

    def _identify_controls(self, graph: InfraGraph, component_id: str) -> list[str]:
        """Identify existing mitigations for a component."""
        comp = graph.get_component(component_id)
        if comp is None:
            return []

        controls: list[str] = []
        if comp.replicas > 1:
            controls.append(f"Multiple replicas ({comp.replicas})")
        if comp.failover.enabled:
            controls.append("Failover enabled")
        if comp.autoscaling.enabled:
            controls.append(f"Autoscaling ({comp.autoscaling.min_replicas}-{comp.autoscaling.max_replicas})")

        # Check for circuit breakers
        dependents = graph.get_dependents(component_id)
        for dep in dependents:
            edge = graph.get_dependency_edge(dep.id, component_id)
            if edge and edge.circuit_breaker.enabled:
                controls.append(f"Circuit breaker on {dep.id} -> {component_id}")
                break

        # Check for retry strategies
        deps = graph.get_dependencies(component_id)
        for dep in deps:
            edge = graph.get_dependency_edge(component_id, dep.id)
            if edge and edge.retry_strategy.enabled:
                controls.append(f"Retry strategy on {component_id} -> {dep.id}")
                break

        return controls

    def _recommend_actions(
        self,
        graph: InfraGraph,
        component_id: str,
        severity: int,
        occurrence: int,
        detection: int,
    ) -> list[str]:
        """Generate remediation recommendations."""
        comp = graph.get_component(component_id)
        if comp is None:
            return []

        actions: list[str] = []

        # Address occurrence (reduce likelihood)
        if occurrence >= 6:
            if comp.replicas <= 1:
                actions.append("Add replicas (replicas >= 2) to eliminate SPOF")
            if not comp.failover.enabled:
                actions.append("Enable failover for automatic recovery")
            if not comp.autoscaling.enabled:
                actions.append("Enable autoscaling for capacity management")

        # Address detection (improve monitoring)
        if detection >= 6:
            if not comp.failover.enabled or comp.failover.health_check_interval_seconds <= 0:
                actions.append("Implement health checks for early detection")
            # Check circuit breakers
            dependents = graph.get_dependents(component_id)
            has_cb = False
            for dep in dependents:
                edge = graph.get_dependency_edge(dep.id, component_id)
                if edge and edge.circuit_breaker.enabled:
                    has_cb = True
                    break
            if not has_cb and len(dependents) > 0:
                actions.append("Add circuit breakers on dependent connections")
            actions.append("Set up monitoring and alerting")

        # Address severity (reduce impact)
        if severity >= 7:
            actions.append("Implement graceful degradation patterns")
            if not any("circuit breaker" in a.lower() for a in actions):
                actions.append("Add circuit breakers to contain blast radius")

        return actions

    def _build_report(self, failure_modes: list[FailureMode]) -> FMEAReport:
        """Compile failure modes into a structured FMEA report."""
        if not failure_modes:
            return FMEAReport()

        total_rpn = sum(fm.rpn for fm in failure_modes)
        avg_rpn = total_rpn / len(failure_modes)

        high = sum(1 for fm in failure_modes if fm.rpn > 200)
        medium = sum(1 for fm in failure_modes if 100 < fm.rpn <= 200)
        low = sum(1 for fm in failure_modes if fm.rpn <= 100)

        sorted_by_rpn = sorted(failure_modes, key=lambda fm: fm.rpn, reverse=True)
        top_risks = sorted_by_rpn[:10]

        rpn_by_component: dict[str, int] = {}
        for fm in failure_modes:
            rpn_by_component[fm.component_id] = rpn_by_component.get(fm.component_id, 0) + fm.rpn

        rpn_by_mode: dict[str, int] = {}
        for fm in failure_modes:
            rpn_by_mode[fm.mode] = rpn_by_mode.get(fm.mode, 0) + fm.rpn

        # Build improvement priority from recommendations
        improvement: list[tuple[str, str, int]] = []
        for fm in sorted_by_rpn:
            for action in fm.recommended_actions:
                improvement.append((fm.component_id, action, fm.rpn))

        # Deduplicate: keep highest RPN per (component, action)
        seen: set[tuple[str, str]] = set()
        unique_improvement: list[tuple[str, str, int]] = []
        for comp, action, rpn in improvement:
            key = (comp, action)
            if key not in seen:
                seen.add(key)
                unique_improvement.append((comp, action, rpn))

        return FMEAReport(
            failure_modes=failure_modes,
            total_rpn=total_rpn,
            average_rpn=round(avg_rpn, 1),
            high_risk_count=high,
            medium_risk_count=medium,
            low_risk_count=low,
            top_risks=top_risks,
            rpn_by_component=rpn_by_component,
            rpn_by_failure_mode=rpn_by_mode,
            improvement_priority=unique_improvement,
        )

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------

    def to_spreadsheet_format(self, report: FMEAReport) -> list[dict]:
        """Convert FMEA report to a list of dicts suitable for CSV/Excel export."""
        rows: list[dict] = []
        for fm in report.failure_modes:
            rows.append({
                "ID": fm.id,
                "Component": fm.component_name,
                "Component ID": fm.component_id,
                "Failure Mode": fm.mode,
                "Cause": fm.cause,
                "Local Effect": fm.effect_local,
                "System Effect": fm.effect_system,
                "Severity (S)": fm.severity,
                "Occurrence (O)": fm.occurrence,
                "Detection (D)": fm.detection,
                "RPN": fm.rpn,
                "Current Controls": "; ".join(fm.current_controls),
                "Recommended Actions": "; ".join(fm.recommended_actions),
                "Responsible": fm.responsible,
            })
        return rows
