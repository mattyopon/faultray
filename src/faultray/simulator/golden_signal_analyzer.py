# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Golden Signal Analyzer — Google SRE's 4 Golden Signals analysis engine.

Analyzes infrastructure against the 4 Golden Signals framework:
  1. Latency   — How long it takes to service a request
  2. Traffic   — How much demand is being placed on the system
  3. Errors    — The rate of requests that fail
  4. Saturation — How "full" the service is

Provides a comprehensive health assessment from the SRE perspective,
identifying which signals are in violation and recommending actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


class SignalType(str, Enum):
    """The four Golden Signals defined by Google SRE."""

    LATENCY = "latency"
    TRAFFIC = "traffic"
    ERRORS = "errors"
    SATURATION = "saturation"


class SignalStatus(str, Enum):
    """Health status of an individual signal reading."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class SignalThreshold:
    """Warning and critical thresholds for a signal."""

    warning_threshold: float
    critical_threshold: float
    unit: str


@dataclass
class SignalReading:
    """A single signal measurement for one component."""

    component_id: str
    component_name: str
    signal_type: SignalType
    value: float
    status: SignalStatus
    threshold: SignalThreshold
    details: str


@dataclass
class SignalSummary:
    """Aggregated summary for one signal type across all components."""

    signal_type: SignalType
    total_readings: int
    healthy_count: int
    warning_count: int
    critical_count: int
    worst_reading: SignalReading | None
    average_value: float
    recommendation: str


@dataclass
class GoldenSignalReport:
    """Complete Golden Signals analysis report."""

    readings: list[SignalReading] = field(default_factory=list)
    summaries: list[SignalSummary] = field(default_factory=list)
    overall_health: SignalStatus = SignalStatus.HEALTHY
    total_components: int = 0
    signals_in_violation: int = 0
    top_issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------

_LATENCY_THRESHOLD = SignalThreshold(
    warning_threshold=200.0, critical_threshold=1000.0, unit="ms"
)
_TRAFFIC_THRESHOLD = SignalThreshold(
    warning_threshold=70.0, critical_threshold=90.0, unit="%"
)
_ERRORS_THRESHOLD = SignalThreshold(
    warning_threshold=1.0, critical_threshold=5.0, unit="%"
)
_SATURATION_THRESHOLD = SignalThreshold(
    warning_threshold=70.0, critical_threshold=85.0, unit="%"
)

# ---------------------------------------------------------------------------
# Latency helpers
# ---------------------------------------------------------------------------

_HEALTH_LATENCY: dict[HealthStatus, float] = {
    HealthStatus.HEALTHY: 50.0,
    HealthStatus.DEGRADED: 500.0,
    HealthStatus.OVERLOADED: 2000.0,
    HealthStatus.DOWN: 9999.0,
}

_TYPE_LATENCY_MULTIPLIER: dict[ComponentType, float] = {
    ComponentType.DATABASE: 1.5,
    ComponentType.EXTERNAL_API: 2.0,
    ComponentType.CACHE: 0.5,
}

# ---------------------------------------------------------------------------
# Traffic helpers — default max_connections per component type
# ---------------------------------------------------------------------------

_DEFAULT_CAPACITY: dict[ComponentType, int] = {
    ComponentType.WEB_SERVER: 1000,
    ComponentType.APP_SERVER: 500,
    ComponentType.DATABASE: 200,
    ComponentType.CACHE: 5000,
    ComponentType.QUEUE: 2000,
}
_DEFAULT_CAPACITY_FALLBACK = 500

# ---------------------------------------------------------------------------
# Error rate helpers
# ---------------------------------------------------------------------------

_HEALTH_ERROR_RATE: dict[HealthStatus, float] = {
    HealthStatus.HEALTHY: 0.0,
    HealthStatus.DEGRADED: 5.0,
    HealthStatus.OVERLOADED: 15.0,
    HealthStatus.DOWN: 100.0,
}


def _classify(value: float, threshold: SignalThreshold) -> SignalStatus:
    """Return the status for *value* given *threshold*."""
    if value >= threshold.critical_threshold:
        return SignalStatus.CRITICAL
    if value >= threshold.warning_threshold:
        return SignalStatus.WARNING
    return SignalStatus.HEALTHY


# ---------------------------------------------------------------------------
# Recommendation templates
# ---------------------------------------------------------------------------

_RECOMMENDATIONS: dict[SignalType, dict[SignalStatus, str]] = {
    SignalType.LATENCY: {
        SignalStatus.CRITICAL: (
            "Critical latency detected on {name} ({value:.0f}ms). "
            "Investigate slow queries, connection pool exhaustion, or downstream timeouts."
        ),
        SignalStatus.WARNING: (
            "Elevated latency on {name} ({value:.0f}ms). "
            "Monitor trends and consider caching or connection pooling."
        ),
    },
    SignalType.TRAFFIC: {
        SignalStatus.CRITICAL: (
            "Traffic saturation on {name} ({value:.1f}%). "
            "Scale horizontally or enable autoscaling immediately."
        ),
        SignalStatus.WARNING: (
            "High traffic on {name} ({value:.1f}%). "
            "Plan capacity increase or enable autoscaling."
        ),
    },
    SignalType.ERRORS: {
        SignalStatus.CRITICAL: (
            "Critical error rate on {name} ({value:.1f}%). "
            "Immediate investigation required — check health checks, dependencies, and deployment state."
        ),
        SignalStatus.WARNING: (
            "Elevated error rate on {name} ({value:.1f}%). "
            "Review recent deployments and dependency health."
        ),
    },
    SignalType.SATURATION: {
        SignalStatus.CRITICAL: (
            "Resource saturation on {name} ({value:.1f}%). "
            "Scale up resources or enable autoscaling to prevent outage."
        ),
        SignalStatus.WARNING: (
            "High resource usage on {name} ({value:.1f}%). "
            "Monitor growth and plan capacity expansion."
        ),
    },
}


class GoldenSignalAnalyzer:
    """Analyze an ``InfraGraph`` against Google SRE's 4 Golden Signals."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self) -> GoldenSignalReport:
        """Run a full 4-signal analysis and return a ``GoldenSignalReport``."""
        components = list(self._graph.components.values())
        if not components:
            return GoldenSignalReport(
                summary="No components to analyze.",
            )

        readings: list[SignalReading] = []
        for comp in components:
            readings.append(self._analyze_latency(comp))
            readings.append(self._analyze_traffic(comp))
            readings.append(self._analyze_errors(comp))
            readings.append(self._analyze_saturation(comp))

        summaries = [self.analyze_signal(st, readings) for st in SignalType]

        # Overall health
        overall = SignalStatus.HEALTHY
        for r in readings:
            if r.status == SignalStatus.CRITICAL:
                overall = SignalStatus.CRITICAL
                break
            if r.status == SignalStatus.WARNING:
                overall = SignalStatus.WARNING

        # Count signals in violation (signal types with any non-HEALTHY)
        signals_in_violation = sum(
            1
            for s in summaries
            if s.warning_count > 0 or s.critical_count > 0
        )

        # Top issues — CRITICAL first, then WARNING, max 5
        issues: list[str] = []
        for r in sorted(
            readings,
            key=lambda x: (
                0 if x.status == SignalStatus.CRITICAL else 1,
                -x.value,
            ),
        ):
            if r.status in (SignalStatus.CRITICAL, SignalStatus.WARNING):
                issues.append(
                    f"[{r.status.value.upper()}] {r.signal_type.value} on "
                    f"{r.component_name}: {r.value:.1f}{r.threshold.unit}"
                )
            if len(issues) >= 5:
                break

        # Recommendations — deduplicated
        recs: list[str] = []
        seen: set[str] = set()
        for r in sorted(
            readings,
            key=lambda x: (
                0 if x.status == SignalStatus.CRITICAL else 1,
                -x.value,
            ),
        ):
            if r.status in (SignalStatus.CRITICAL, SignalStatus.WARNING):
                tpl = _RECOMMENDATIONS.get(r.signal_type, {}).get(r.status)
                if tpl:
                    text = tpl.format(name=r.component_name, value=r.value)
                    if text not in seen:
                        seen.add(text)
                        recs.append(text)

        # Build summary string
        summary_parts = [
            f"Golden Signals Analysis: {len(components)} components analyzed.",
            f"Overall health: {overall.value.upper()}.",
            f"Signals in violation: {signals_in_violation}/4.",
        ]
        if issues:
            summary_parts.append(f"Top issue: {issues[0]}")

        return GoldenSignalReport(
            readings=readings,
            summaries=summaries,
            overall_health=overall,
            total_components=len(components),
            signals_in_violation=signals_in_violation,
            top_issues=issues,
            recommendations=recs,
            summary=" ".join(summary_parts),
        )

    def analyze_signal(
        self,
        signal_type: SignalType,
        readings: list[SignalReading] | None = None,
    ) -> SignalSummary:
        """Analyze a single signal type across all components.

        If *readings* is ``None`` the readings are computed on the fly.
        """
        if readings is None:
            components = list(self._graph.components.values())
            analyze_fn = {
                SignalType.LATENCY: self._analyze_latency,
                SignalType.TRAFFIC: self._analyze_traffic,
                SignalType.ERRORS: self._analyze_errors,
                SignalType.SATURATION: self._analyze_saturation,
            }[signal_type]
            readings = [analyze_fn(c) for c in components]

        filtered = [r for r in readings if r.signal_type == signal_type]

        if not filtered:
            return SignalSummary(
                signal_type=signal_type,
                total_readings=0,
                healthy_count=0,
                warning_count=0,
                critical_count=0,
                worst_reading=None,
                average_value=0.0,
                recommendation="No readings available.",
            )

        healthy = sum(1 for r in filtered if r.status == SignalStatus.HEALTHY)
        warning = sum(1 for r in filtered if r.status == SignalStatus.WARNING)
        critical = sum(1 for r in filtered if r.status == SignalStatus.CRITICAL)

        worst = max(filtered, key=lambda r: r.value)
        avg = sum(r.value for r in filtered) / len(filtered)

        # Build recommendation
        if critical > 0:
            tpl = _RECOMMENDATIONS.get(signal_type, {}).get(SignalStatus.CRITICAL, "")
            rec = tpl.format(name=worst.component_name, value=worst.value) if tpl else ""
        elif warning > 0:
            tpl = _RECOMMENDATIONS.get(signal_type, {}).get(SignalStatus.WARNING, "")
            rec = tpl.format(name=worst.component_name, value=worst.value) if tpl else ""
        else:
            rec = f"All {signal_type.value} readings are healthy."

        return SignalSummary(
            signal_type=signal_type,
            total_readings=len(filtered),
            healthy_count=healthy,
            warning_count=warning,
            critical_count=critical,
            worst_reading=worst,
            average_value=round(avg, 2),
            recommendation=rec,
        )

    # ------------------------------------------------------------------
    # Private per-signal analyzers
    # ------------------------------------------------------------------

    def _analyze_latency(self, comp: Component) -> SignalReading:
        base = _HEALTH_LATENCY.get(comp.health, 50.0)
        multiplier = _TYPE_LATENCY_MULTIPLIER.get(comp.type, 1.0)
        value = base * multiplier
        status = _classify(value, _LATENCY_THRESHOLD)
        return SignalReading(
            component_id=comp.id,
            component_name=comp.name,
            signal_type=SignalType.LATENCY,
            value=value,
            status=status,
            threshold=_LATENCY_THRESHOLD,
            details=(
                f"Latency {value:.0f}ms (health={comp.health.value}, "
                f"type={comp.type.value}, multiplier={multiplier}x)"
            ),
        )

    def _analyze_traffic(self, comp: Component) -> SignalReading:
        connections = comp.metrics.network_connections
        max_conn = comp.capacity.max_connections
        if max_conn == 0:
            max_conn = _DEFAULT_CAPACITY.get(comp.type, _DEFAULT_CAPACITY_FALLBACK)
        value = (connections / max_conn) * 100.0 if max_conn > 0 else 0.0
        status = _classify(value, _TRAFFIC_THRESHOLD)
        return SignalReading(
            component_id=comp.id,
            component_name=comp.name,
            signal_type=SignalType.TRAFFIC,
            value=value,
            status=status,
            threshold=_TRAFFIC_THRESHOLD,
            details=(
                f"Traffic {value:.1f}% ({connections}/{max_conn} connections)"
            ),
        )

    def _analyze_errors(self, comp: Component) -> SignalReading:
        value = _HEALTH_ERROR_RATE.get(comp.health, 0.0)
        status = _classify(value, _ERRORS_THRESHOLD)
        return SignalReading(
            component_id=comp.id,
            component_name=comp.name,
            signal_type=SignalType.ERRORS,
            value=value,
            status=status,
            threshold=_ERRORS_THRESHOLD,
            details=f"Error rate {value:.1f}% (health={comp.health.value})",
        )

    def _analyze_saturation(self, comp: Component) -> SignalReading:
        value = max(
            comp.metrics.cpu_percent,
            comp.metrics.memory_percent,
            comp.metrics.disk_percent,
        )
        status = _classify(value, _SATURATION_THRESHOLD)
        return SignalReading(
            component_id=comp.id,
            component_name=comp.name,
            signal_type=SignalType.SATURATION,
            value=value,
            status=status,
            threshold=_SATURATION_THRESHOLD,
            details=(
                f"Saturation {value:.1f}% "
                f"(cpu={comp.metrics.cpu_percent:.1f}%, "
                f"mem={comp.metrics.memory_percent:.1f}%, "
                f"disk={comp.metrics.disk_percent:.1f}%)"
            ),
        )
