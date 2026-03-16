"""Synthetic Monitoring Simulator — end-user perspective health validation.

Simulates synthetic monitoring probes to validate system health from an
end-user perspective.  Models multi-step health check flows, geographic probe
distribution, availability calculations, and alert threshold tuning to
prevent false positives.
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProbeType(str, Enum):
    HTTP = "http"
    TCP = "tcp"
    DNS = "dns"
    GRPC = "grpc"
    WEBSOCKET = "websocket"
    ICMP = "icmp"
    SSL_CERT = "ssl_cert"
    MULTI_STEP = "multi_step"


class ProbeRegion(str, Enum):
    US_EAST = "us_east"
    US_WEST = "us_west"
    EU_WEST = "eu_west"
    EU_CENTRAL = "eu_central"
    ASIA_PACIFIC = "asia_pacific"
    SOUTH_AMERICA = "south_america"
    AFRICA = "africa"
    OCEANIA = "oceania"


class ProbeResult(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ERROR = "error"
    DEGRADED = "degraded"
    SSL_ERROR = "ssl_error"
    DNS_ERROR = "dns_error"


class AlertSensitivity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL_ONLY = "critical_only"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

# Baseline latencies by region (milliseconds from a "central" origin)
_REGION_BASE_LATENCY: dict[ProbeRegion, float] = {
    ProbeRegion.US_EAST: 20.0,
    ProbeRegion.US_WEST: 45.0,
    ProbeRegion.EU_WEST: 80.0,
    ProbeRegion.EU_CENTRAL: 90.0,
    ProbeRegion.ASIA_PACIFIC: 150.0,
    ProbeRegion.SOUTH_AMERICA: 170.0,
    ProbeRegion.AFRICA: 200.0,
    ProbeRegion.OCEANIA: 180.0,
}

# Multiplier applied to base latency per probe type
_PROBE_TYPE_MULTIPLIER: dict[ProbeType, float] = {
    ProbeType.ICMP: 0.3,
    ProbeType.TCP: 0.5,
    ProbeType.DNS: 0.4,
    ProbeType.HTTP: 1.0,
    ProbeType.GRPC: 0.9,
    ProbeType.WEBSOCKET: 1.1,
    ProbeType.SSL_CERT: 1.3,
    ProbeType.MULTI_STEP: 2.5,
}


class ProbeConfig(BaseModel):
    """Configuration for a single synthetic monitoring probe."""

    probe_id: str
    probe_type: ProbeType
    target_component_id: str
    regions: list[ProbeRegion] = Field(default_factory=list)
    interval_seconds: int = 60
    timeout_ms: int = 5000
    expected_status: int = 200


class ProbeExecution(BaseModel):
    """Result of executing a single probe from a single region."""

    probe_id: str
    region: ProbeRegion
    result: ProbeResult
    latency_ms: float
    status_code: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None


class AvailabilityMetric(BaseModel):
    """Availability and latency metrics for a monitored component."""

    component_id: str
    uptime_percent: float = 100.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    error_rate: float = 0.0
    total_probes: int = 0
    successful_probes: int = 0


class AlertThreshold(BaseModel):
    """Alert threshold configuration for a specific metric."""

    metric: str
    warning_value: float
    critical_value: float
    consecutive_failures: int = 3
    sensitivity: AlertSensitivity = AlertSensitivity.MEDIUM


class FalsePositiveAnalysis(BaseModel):
    """Analysis of false positive alerts in monitoring configuration."""

    total_alerts: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_positive_rate: float = 0.0
    recommended_threshold_adjustments: list[str] = Field(default_factory=list)


class SyntheticMonitorReport(BaseModel):
    """Complete report from a synthetic monitoring run."""

    availability_metrics: list[AvailabilityMetric] = Field(default_factory=list)
    probe_executions: list[ProbeExecution] = Field(default_factory=list)
    false_positive_analysis: FalsePositiveAnalysis = Field(
        default_factory=FalsePositiveAnalysis
    )
    total_probes: int = 0
    healthy_count: int = 0
    degraded_count: int = 0
    failed_count: int = 0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SyntheticMonitorEngine:
    """Stateless engine for synthetic monitoring simulation."""

    def run_probes(
        self,
        graph: InfraGraph,
        probe_configs: list[ProbeConfig],
    ) -> SyntheticMonitorReport:
        """Execute all probe configurations and generate a monitoring report."""
        all_executions: list[ProbeExecution] = []
        availability_metrics: list[AvailabilityMetric] = []
        recommendations: list[str] = []
        healthy = 0
        degraded = 0
        failed = 0

        for config in probe_configs:
            executions = self.execute_probe(graph, config)
            all_executions.extend(executions)

            if executions:
                metric = self.calculate_availability(executions)
                metric.component_id = config.target_component_id
                availability_metrics.append(metric)

                # Classify component health from availability
                if metric.error_rate > 0.5:
                    failed += 1
                elif metric.error_rate > 0.1 or metric.p99_latency_ms > config.timeout_ms * 0.8:
                    degraded += 1
                else:
                    healthy += 1

                # Generate recommendations based on metrics
                recommendations.extend(
                    self._generate_recommendations(config, metric, graph)
                )

        # Analyse false positives using default thresholds
        default_thresholds = self.recommend_thresholds(all_executions)
        fp_analysis = self.analyze_false_positives(all_executions, default_thresholds)

        return SyntheticMonitorReport(
            availability_metrics=availability_metrics,
            probe_executions=all_executions,
            false_positive_analysis=fp_analysis,
            total_probes=len(all_executions),
            healthy_count=healthy,
            degraded_count=degraded,
            failed_count=failed,
            recommendations=recommendations,
        )

    def execute_probe(
        self,
        graph: InfraGraph,
        probe_config: ProbeConfig,
    ) -> list[ProbeExecution]:
        """Execute a probe from every configured region, returning one execution per region."""
        component = graph.get_component(probe_config.target_component_id)
        if component is None:
            return [
                ProbeExecution(
                    probe_id=probe_config.probe_id,
                    region=region,
                    result=ProbeResult.ERROR,
                    latency_ms=0.0,
                    status_code=0,
                    error_message=f"Component '{probe_config.target_component_id}' not found in graph",
                )
                for region in (probe_config.regions or [ProbeRegion.US_EAST])
            ]

        regions = probe_config.regions or [ProbeRegion.US_EAST]
        executions: list[ProbeExecution] = []

        for region in regions:
            execution = self._execute_single(probe_config, component, region)
            executions.append(execution)

        return executions

    def calculate_availability(
        self,
        executions: list[ProbeExecution],
    ) -> AvailabilityMetric:
        """Calculate availability metrics from a list of probe executions."""
        if not executions:
            return AvailabilityMetric(component_id="unknown")

        total = len(executions)
        successful = sum(
            1
            for e in executions
            if e.result in (ProbeResult.SUCCESS, ProbeResult.DEGRADED)
        )
        latencies = [e.latency_ms for e in executions if e.latency_ms > 0]
        errors = sum(
            1
            for e in executions
            if e.result not in (ProbeResult.SUCCESS, ProbeResult.DEGRADED)
        )

        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        p95 = _percentile(latencies, 95) if latencies else 0.0
        p99 = _percentile(latencies, 99) if latencies else 0.0
        uptime = (successful / total * 100.0) if total > 0 else 0.0
        error_rate = (errors / total) if total > 0 else 0.0

        return AvailabilityMetric(
            component_id=executions[0].probe_id,
            uptime_percent=round(uptime, 4),
            avg_latency_ms=round(avg_latency, 2),
            p95_latency_ms=round(p95, 2),
            p99_latency_ms=round(p99, 2),
            error_rate=round(error_rate, 4),
            total_probes=total,
            successful_probes=successful,
        )

    def analyze_false_positives(
        self,
        executions: list[ProbeExecution],
        thresholds: list[AlertThreshold],
    ) -> FalsePositiveAnalysis:
        """Analyze probe executions against thresholds to estimate false positive rate."""
        if not executions or not thresholds:
            return FalsePositiveAnalysis()

        # Build a latency threshold map
        latency_warning = None
        latency_critical = None
        error_rate_warning = None
        error_rate_critical = None
        consecutive_limit = 3

        for th in thresholds:
            if th.metric == "latency_ms":
                latency_warning = th.warning_value
                latency_critical = th.critical_value
                consecutive_limit = th.consecutive_failures
            elif th.metric == "error_rate":
                error_rate_warning = th.warning_value
                error_rate_critical = th.critical_value

        total_alerts = 0
        true_positives = 0
        false_positives = 0

        # Group executions by probe_id
        by_probe: dict[str, list[ProbeExecution]] = {}
        for ex in executions:
            by_probe.setdefault(ex.probe_id, []).append(ex)

        for probe_id, probe_execs in by_probe.items():
            consecutive_failures = 0
            for ex in probe_execs:
                is_actual_failure = ex.result in (
                    ProbeResult.ERROR,
                    ProbeResult.TIMEOUT,
                    ProbeResult.SSL_ERROR,
                    ProbeResult.DNS_ERROR,
                )

                # Check if alert would fire
                alert_fired = False
                if latency_critical is not None and ex.latency_ms > latency_critical:
                    alert_fired = True
                if is_actual_failure:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0

                if consecutive_failures >= consecutive_limit:
                    alert_fired = True

                if alert_fired:
                    total_alerts += 1
                    if is_actual_failure:
                        true_positives += 1
                    else:
                        false_positives += 1

        # Calculate error rate across all executions for recommendation
        overall_error_rate = (
            sum(1 for e in executions if e.result in (
                ProbeResult.ERROR, ProbeResult.TIMEOUT,
                ProbeResult.SSL_ERROR, ProbeResult.DNS_ERROR,
            ))
            / len(executions)
        ) if executions else 0.0

        fp_rate = (false_positives / total_alerts) if total_alerts > 0 else 0.0

        adjustments: list[str] = []
        if fp_rate > 0.3:
            adjustments.append(
                "High false positive rate detected. "
                "Consider increasing consecutive_failures threshold."
            )
        if fp_rate > 0.5:
            adjustments.append(
                "Consider widening latency thresholds to reduce noise."
            )
        if overall_error_rate < 0.05 and total_alerts > 5:
            adjustments.append(
                "Low actual error rate with many alerts suggests "
                "sensitivity should be reduced."
            )
        if latency_warning is not None and latency_critical is not None:
            if latency_critical - latency_warning < 50:
                adjustments.append(
                    "Warning and critical latency thresholds are very close. "
                    "Consider widening the gap to at least 50ms."
                )

        return FalsePositiveAnalysis(
            total_alerts=total_alerts,
            true_positives=true_positives,
            false_positives=false_positives,
            false_positive_rate=round(fp_rate, 4),
            recommended_threshold_adjustments=adjustments,
        )

    def recommend_thresholds(
        self,
        executions: list[ProbeExecution],
    ) -> list[AlertThreshold]:
        """Recommend alert thresholds based on observed probe executions."""
        if not executions:
            return [
                AlertThreshold(
                    metric="latency_ms",
                    warning_value=500.0,
                    critical_value=1000.0,
                    consecutive_failures=3,
                    sensitivity=AlertSensitivity.MEDIUM,
                ),
                AlertThreshold(
                    metric="error_rate",
                    warning_value=0.05,
                    critical_value=0.10,
                    consecutive_failures=3,
                    sensitivity=AlertSensitivity.MEDIUM,
                ),
            ]

        latencies = [e.latency_ms for e in executions if e.latency_ms > 0]
        errors = sum(
            1
            for e in executions
            if e.result
            in (ProbeResult.ERROR, ProbeResult.TIMEOUT, ProbeResult.SSL_ERROR, ProbeResult.DNS_ERROR)
        )
        error_rate = errors / len(executions) if executions else 0.0

        if latencies:
            p95 = _percentile(latencies, 95)
            p99 = _percentile(latencies, 99)
            latency_warning = round(p95 * 1.5, 2)
            latency_critical = round(p99 * 2.0, 2)
        else:
            latency_warning = 500.0
            latency_critical = 1000.0

        # Determine sensitivity based on error rate
        if error_rate > 0.2:
            sensitivity = AlertSensitivity.HIGH
            consec = 2
        elif error_rate > 0.05:
            sensitivity = AlertSensitivity.MEDIUM
            consec = 3
        else:
            sensitivity = AlertSensitivity.LOW
            consec = 5

        error_rate_warning = round(max(error_rate * 2, 0.01), 4)
        error_rate_critical = round(max(error_rate * 4, 0.05), 4)

        return [
            AlertThreshold(
                metric="latency_ms",
                warning_value=latency_warning,
                critical_value=latency_critical,
                consecutive_failures=consec,
                sensitivity=sensitivity,
            ),
            AlertThreshold(
                metric="error_rate",
                warning_value=error_rate_warning,
                critical_value=error_rate_critical,
                consecutive_failures=consec,
                sensitivity=sensitivity,
            ),
        ]

    def simulate_geographic_latency(
        self,
        region: ProbeRegion,
        component: Component,
    ) -> float:
        """Simulate network latency from a geographic region to a component.

        Takes into account the region's base latency, the component's
        network profile, and a deterministic jitter based on component id.
        """
        base = _REGION_BASE_LATENCY.get(region, 100.0)

        # Add component network latency
        net = component.network
        base += net.rtt_ms
        base += net.dns_resolution_ms
        base += net.tls_handshake_ms

        # Deterministic jitter from component id so tests are reproducible
        seed = int(hashlib.md5(component.id.encode()).hexdigest()[:8], 16)
        jitter = (seed % 20) - 10  # -10..+9 ms
        base += jitter + net.jitter_ms

        return max(1.0, round(base, 2))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _execute_single(
        self,
        config: ProbeConfig,
        component: Component,
        region: ProbeRegion,
    ) -> ProbeExecution:
        """Simulate a single probe execution from *region* to *component*."""
        latency = self.simulate_geographic_latency(region, component)

        # Apply probe type multiplier
        multiplier = _PROBE_TYPE_MULTIPLIER.get(config.probe_type, 1.0)
        latency *= multiplier

        # Determine result based on component health and probe type
        result, status_code, error_msg = self._determine_result(
            config, component, latency
        )

        return ProbeExecution(
            probe_id=config.probe_id,
            region=region,
            result=result,
            latency_ms=round(latency, 2),
            status_code=status_code,
            error_message=error_msg,
        )

    def _determine_result(
        self,
        config: ProbeConfig,
        component: Component,
        latency_ms: float,
    ) -> tuple[ProbeResult, int, Optional[str]]:
        """Determine probe result based on component state and latency."""
        from faultray.model.components import HealthStatus

        # Component is down
        if component.health == HealthStatus.DOWN:
            return ProbeResult.ERROR, 503, "Component is down"

        # Component is overloaded — high chance of timeout
        if component.health == HealthStatus.OVERLOADED:
            if latency_ms > config.timeout_ms * 0.6:
                return ProbeResult.TIMEOUT, 504, "Gateway timeout (overloaded)"
            return ProbeResult.DEGRADED, 200, "Component is overloaded but responding"

        # Timeout check
        if latency_ms > config.timeout_ms:
            return ProbeResult.TIMEOUT, 504, "Request timed out"

        # SSL cert probe on non-web component
        if config.probe_type == ProbeType.SSL_CERT:
            if not component.security.encryption_in_transit:
                return ProbeResult.SSL_ERROR, 0, "SSL/TLS not configured"

        # DNS probe
        if config.probe_type == ProbeType.DNS:
            if component.type == ComponentType.DNS:
                return ProbeResult.SUCCESS, config.expected_status, None
            # Non-DNS component — simulate lookup overhead
            if component.network.dns_resolution_ms > 100:
                return ProbeResult.DNS_ERROR, 0, "DNS resolution slow or failed"

        # Degraded health
        if component.health == HealthStatus.DEGRADED:
            return ProbeResult.DEGRADED, config.expected_status, "Component is degraded"

        # High utilization degrades
        if component.utilization() > 85:
            return ProbeResult.DEGRADED, config.expected_status, "High utilization"

        return ProbeResult.SUCCESS, config.expected_status, None

    def _generate_recommendations(
        self,
        config: ProbeConfig,
        metric: AvailabilityMetric,
        graph: InfraGraph,
    ) -> list[str]:
        """Generate actionable recommendations based on probe results."""
        recs: list[str] = []
        comp = graph.get_component(config.target_component_id)

        if metric.uptime_percent < 99.0:
            recs.append(
                f"Component '{config.target_component_id}' uptime is "
                f"{metric.uptime_percent:.2f}%, below 99% SLO. "
                "Investigate root cause and add redundancy."
            )

        if metric.p99_latency_ms > config.timeout_ms * 0.5:
            recs.append(
                f"P99 latency ({metric.p99_latency_ms:.0f}ms) is over 50% "
                f"of timeout ({config.timeout_ms}ms) for '{config.target_component_id}'. "
                "Consider performance optimization or CDN."
            )

        if metric.error_rate > 0.1:
            recs.append(
                f"Error rate for '{config.target_component_id}' is "
                f"{metric.error_rate:.1%}. Add circuit breakers or retry logic."
            )

        if len(config.regions) < 2:
            recs.append(
                f"Probe '{config.probe_id}' only checks from "
                f"{len(config.regions)} region(s). Add more regions for "
                "geographic coverage."
            )

        if comp is not None and comp.replicas < 2:
            if metric.error_rate > 0.05:
                recs.append(
                    f"Component '{config.target_component_id}' has a single "
                    "replica with error rate > 5%. Add replicas for redundancy."
                )

        if config.probe_type == ProbeType.HTTP and config.interval_seconds > 120:
            recs.append(
                f"Probe '{config.probe_id}' interval is {config.interval_seconds}s. "
                "Consider reducing to <=60s for faster incident detection."
            )

        return recs


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _percentile(data: list[float], pct: float) -> float:
    """Compute the *pct*-th percentile of *data* using linear interpolation."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (pct / 100.0) * (len(sorted_data) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[f] * (c - k)
    d1 = sorted_data[c] * (k - f)
    return d0 + d1
