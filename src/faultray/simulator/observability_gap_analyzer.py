# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Observability Gap Analyzer.

Identifies gaps in monitoring, logging, and tracing across infrastructure.
Analyses the three pillars of observability (metrics, logs, traces), golden
signal coverage, alert mapping, distributed tracing completeness, log level
balance, dashboard coverage, SLI/SLO monitoring gaps, correlation capability,
mean time to detect (MTTD) estimation, observability cost optimisation, and
blind spot detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ObservabilityPillar(str, Enum):
    """The three pillars of observability."""

    METRICS = "metrics"
    LOGS = "logs"
    TRACES = "traces"


class GoldenSignal(str, Enum):
    """Google SRE's four golden signals."""

    LATENCY = "latency"
    TRAFFIC = "traffic"
    ERRORS = "errors"
    SATURATION = "saturation"


class GapSeverity(str, Enum):
    """Severity level for an identified gap."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class LogLevel(str, Enum):
    """Standard log levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class CorrelationCapability(str, Enum):
    """Ability to correlate across observability pillars."""

    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"


# ---------------------------------------------------------------------------
# Data models — component-level observability configuration
# ---------------------------------------------------------------------------


@dataclass
class PillarCoverage:
    """Observability pillar coverage for a single component."""

    component_id: str
    metrics_enabled: bool = False
    logs_enabled: bool = False
    traces_enabled: bool = False
    metrics_completeness: float = 0.0  # 0-1
    logs_completeness: float = 0.0
    traces_completeness: float = 0.0


@dataclass
class GoldenSignalCoverage:
    """Golden signal coverage for a single component."""

    component_id: str
    latency_monitored: bool = False
    traffic_monitored: bool = False
    errors_monitored: bool = False
    saturation_monitored: bool = False


@dataclass
class AlertMapping:
    """Mapping of failure modes to alert coverage for a component."""

    component_id: str
    failure_modes: list[str] = field(default_factory=list)
    alerted_modes: list[str] = field(default_factory=list)


@dataclass
class TracePropagation:
    """Trace propagation information between two components."""

    source_id: str
    target_id: str
    propagation_enabled: bool = False


@dataclass
class LogLevelConfig:
    """Log level distribution for a component."""

    component_id: str
    level: LogLevel = LogLevel.INFO
    estimated_volume_gb_per_day: float = 1.0


@dataclass
class DashboardConfig:
    """Dashboard coverage for a component."""

    component_id: str
    has_dashboard: bool = False
    metrics_on_dashboard: int = 0


@dataclass
class SLIMonitoringConfig:
    """SLI/SLO monitoring configuration for a component."""

    component_id: str
    sli_defined: bool = False
    slo_defined: bool = False
    error_budget_tracking: bool = False
    burn_rate_alerting: bool = False


@dataclass
class ObservabilitySetup:
    """Complete observability setup for an infrastructure graph."""

    pillar_coverage: list[PillarCoverage] = field(default_factory=list)
    golden_signal_coverage: list[GoldenSignalCoverage] = field(default_factory=list)
    alert_mappings: list[AlertMapping] = field(default_factory=list)
    trace_propagations: list[TracePropagation] = field(default_factory=list)
    log_level_configs: list[LogLevelConfig] = field(default_factory=list)
    dashboard_configs: list[DashboardConfig] = field(default_factory=list)
    sli_monitoring_configs: list[SLIMonitoringConfig] = field(default_factory=list)
    monthly_observability_cost_usd: float = 0.0
    target_monthly_budget_usd: float = 0.0


# ---------------------------------------------------------------------------
# Gap / Finding models
# ---------------------------------------------------------------------------


@dataclass
class ObservabilityGap:
    """A single identified observability gap."""

    component_id: str
    gap_type: str
    severity: GapSeverity
    description: str
    recommendation: str


@dataclass
class BlindSpot:
    """A component with no monitoring at all."""

    component_id: str
    component_type: str
    severity: GapSeverity
    description: str


@dataclass
class PillarAnalysisResult:
    """Result of three-pillar analysis across the graph."""

    total_components: int = 0
    metrics_covered: int = 0
    logs_covered: int = 0
    traces_covered: int = 0
    average_metrics_completeness: float = 0.0
    average_logs_completeness: float = 0.0
    average_traces_completeness: float = 0.0
    pillar_score: float = 0.0  # 0-100


@dataclass
class GoldenSignalAnalysisResult:
    """Result of golden signal coverage analysis."""

    total_components: int = 0
    latency_covered: int = 0
    traffic_covered: int = 0
    errors_covered: int = 0
    saturation_covered: int = 0
    coverage_score: float = 0.0  # 0-100


@dataclass
class AlertCoverageResult:
    """Result of alert coverage mapping."""

    total_failure_modes: int = 0
    alerted_failure_modes: int = 0
    unalerted_failure_modes: int = 0
    coverage_percent: float = 0.0
    unalerted_details: list[tuple[str, str]] = field(default_factory=list)  # (comp_id, mode)


@dataclass
class TracingCompletenessResult:
    """Result of distributed tracing completeness analysis."""

    total_edges: int = 0
    propagated_edges: int = 0
    gap_edges: list[tuple[str, str]] = field(default_factory=list)
    completeness_percent: float = 0.0


@dataclass
class LogLevelAnalysisResult:
    """Result of log level analysis."""

    total_components: int = 0
    too_verbose: list[str] = field(default_factory=list)
    too_quiet: list[str] = field(default_factory=list)
    balanced: list[str] = field(default_factory=list)
    estimated_daily_volume_gb: float = 0.0
    balance_score: float = 0.0  # 0-100


@dataclass
class DashboardCoverageResult:
    """Result of dashboard coverage assessment."""

    total_components: int = 0
    components_with_dashboard: int = 0
    average_metrics_per_dashboard: float = 0.0
    coverage_percent: float = 0.0


@dataclass
class SLIMonitoringResult:
    """Result of SLI/SLO monitoring gap analysis."""

    total_components: int = 0
    sli_defined_count: int = 0
    slo_defined_count: int = 0
    error_budget_tracking_count: int = 0
    burn_rate_alerting_count: int = 0
    maturity_score: float = 0.0  # 0-100


@dataclass
class CorrelationAnalysisResult:
    """Result of correlation capability analysis."""

    capability: CorrelationCapability = CorrelationCapability.NONE
    metrics_logs_correlated: bool = False
    metrics_traces_correlated: bool = False
    logs_traces_correlated: bool = False
    score: float = 0.0  # 0-100


@dataclass
class MTTDEstimation:
    """Mean Time To Detect estimation."""

    estimated_mttd_minutes: float = 0.0
    contributing_factors: list[str] = field(default_factory=list)
    rating: str = "unknown"  # excellent / good / fair / poor


@dataclass
class CostOptimizationResult:
    """Observability cost optimization analysis result."""

    current_monthly_cost_usd: float = 0.0
    target_monthly_budget_usd: float = 0.0
    over_budget: bool = False
    savings_opportunities: list[str] = field(default_factory=list)
    estimated_savings_usd: float = 0.0


@dataclass
class ObservabilityGapReport:
    """Complete observability gap analysis report."""

    timestamp: str = ""
    total_components: int = 0
    total_gaps: int = 0
    critical_gaps: int = 0
    high_gaps: int = 0
    medium_gaps: int = 0
    low_gaps: int = 0
    info_gaps: int = 0

    pillar_analysis: PillarAnalysisResult = field(default_factory=PillarAnalysisResult)
    golden_signal_analysis: GoldenSignalAnalysisResult = field(
        default_factory=GoldenSignalAnalysisResult
    )
    alert_coverage: AlertCoverageResult = field(default_factory=AlertCoverageResult)
    tracing_completeness: TracingCompletenessResult = field(
        default_factory=TracingCompletenessResult
    )
    log_level_analysis: LogLevelAnalysisResult = field(
        default_factory=LogLevelAnalysisResult
    )
    dashboard_coverage: DashboardCoverageResult = field(
        default_factory=DashboardCoverageResult
    )
    sli_monitoring: SLIMonitoringResult = field(default_factory=SLIMonitoringResult)
    correlation_analysis: CorrelationAnalysisResult = field(
        default_factory=CorrelationAnalysisResult
    )
    mttd_estimation: MTTDEstimation = field(default_factory=MTTDEstimation)
    cost_optimization: CostOptimizationResult = field(
        default_factory=CostOptimizationResult
    )

    gaps: list[ObservabilityGap] = field(default_factory=list)
    blind_spots: list[BlindSpot] = field(default_factory=list)
    overall_score: float = 0.0  # 0-100
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants / weights
# ---------------------------------------------------------------------------

# Weight each sub-analysis in the overall score (total = 1.0)
_ANALYSIS_WEIGHTS: dict[str, float] = {
    "pillar": 0.20,
    "golden_signal": 0.15,
    "alert_coverage": 0.15,
    "tracing_completeness": 0.10,
    "log_level": 0.05,
    "dashboard": 0.10,
    "sli_monitoring": 0.10,
    "correlation": 0.10,
    "blind_spot": 0.05,
}

# Verbose threshold: DEBUG level with >5 GB/day
_VERBOSE_VOLUME_THRESHOLD_GB = 5.0

# Quiet threshold: ERROR/CRITICAL only
_QUIET_LEVELS = {LogLevel.ERROR, LogLevel.CRITICAL}

# MTTD base minutes depending on golden signal coverage ratio
_MTTD_BASE_MINUTES = 60.0  # worst case
_MTTD_BEST_MINUTES = 1.0  # fully observed system

# Default failure modes per component type
_DEFAULT_FAILURE_MODES: dict[ComponentType, list[str]] = {
    ComponentType.LOAD_BALANCER: ["health_check_failure", "connection_limit", "ssl_expiry"],
    ComponentType.WEB_SERVER: ["high_latency", "5xx_errors", "memory_leak", "disk_full"],
    ComponentType.APP_SERVER: ["high_latency", "5xx_errors", "memory_leak", "thread_exhaustion"],
    ComponentType.DATABASE: ["replication_lag", "connection_pool_exhaustion", "disk_full", "slow_queries"],
    ComponentType.CACHE: ["eviction_spike", "hit_rate_drop", "memory_full"],
    ComponentType.QUEUE: ["queue_depth_spike", "consumer_lag", "message_ttl_expiry"],
    ComponentType.STORAGE: ["disk_full", "iops_throttling", "replication_failure"],
    ComponentType.DNS: ["resolution_failure", "ttl_misconfiguration", "dnssec_failure"],
    ComponentType.EXTERNAL_API: ["latency_spike", "rate_limit_hit", "auth_failure", "endpoint_deprecated"],
    ComponentType.CUSTOM: ["unknown_failure"],
    ComponentType.AI_AGENT: ["hallucination", "tool_call_failure", "context_overflow", "timeout"],
    ComponentType.LLM_ENDPOINT: ["latency_spike", "rate_limit_hit", "model_degradation", "auth_failure"],
    ComponentType.TOOL_SERVICE: ["tool_timeout", "invalid_input", "resource_exhaustion"],
    ComponentType.AGENT_ORCHESTRATOR: ["workflow_deadlock", "agent_timeout", "state_corruption"],
    ComponentType.AUTOMATION: ["trigger_failure", "schedule_miss", "execution_timeout"],
    ComponentType.SERVERLESS: ["cold_start", "timeout", "memory_limit", "concurrency_limit"],
    ComponentType.SCHEDULED_JOB: ["job_missed", "execution_failure", "dependency_timeout"],
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ObservabilityGapAnalyzer:
    """Analyzes observability gaps across an infrastructure graph."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Public top-level API
    # ------------------------------------------------------------------

    def analyze(self, setup: ObservabilitySetup) -> ObservabilityGapReport:
        """Run a full observability gap analysis and return a report."""
        components = list(self._graph.components.values())
        if not components:
            return ObservabilityGapReport(
                timestamp=datetime.now(timezone.utc).isoformat(),
                summary="No components to analyze.",
            )

        gaps: list[ObservabilityGap] = []

        pillar_result = self.analyze_pillars(setup.pillar_coverage, components)
        gs_result = self.analyze_golden_signals(setup.golden_signal_coverage, components)
        alert_result = self.analyze_alert_coverage(setup.alert_mappings, components)
        tracing_result = self.analyze_tracing_completeness(setup.trace_propagations)
        log_result = self.analyze_log_levels(setup.log_level_configs, components)
        dashboard_result = self.analyze_dashboard_coverage(setup.dashboard_configs, components)
        sli_result = self.analyze_sli_monitoring(setup.sli_monitoring_configs, components)
        correlation_result = self.analyze_correlation(setup.pillar_coverage, setup.trace_propagations)
        blind_spots = self.detect_blind_spots(setup.pillar_coverage, components)
        mttd = self.estimate_mttd(gs_result, alert_result, pillar_result)
        cost_result = self.analyze_cost(setup)

        # Collect gaps from each analysis
        gaps.extend(self._gaps_from_pillars(pillar_result, setup.pillar_coverage, components))
        gaps.extend(self._gaps_from_golden_signals(gs_result, setup.golden_signal_coverage, components))
        gaps.extend(self._gaps_from_alerts(alert_result))
        gaps.extend(self._gaps_from_tracing(tracing_result))
        gaps.extend(self._gaps_from_log_levels(log_result))
        gaps.extend(self._gaps_from_dashboards(dashboard_result, setup.dashboard_configs, components))
        gaps.extend(self._gaps_from_sli(sli_result, setup.sli_monitoring_configs, components))
        gaps.extend(self._gaps_from_blind_spots(blind_spots))
        gaps.extend(self._gaps_from_correlation(correlation_result))

        # Count severities
        critical = sum(1 for g in gaps if g.severity == GapSeverity.CRITICAL)
        high = sum(1 for g in gaps if g.severity == GapSeverity.HIGH)
        medium = sum(1 for g in gaps if g.severity == GapSeverity.MEDIUM)
        low = sum(1 for g in gaps if g.severity == GapSeverity.LOW)
        info = sum(1 for g in gaps if g.severity == GapSeverity.INFO)

        # Overall score
        blind_spot_ratio = len(blind_spots) / max(1, len(components))
        blind_spot_score = max(0.0, 100.0 * (1.0 - blind_spot_ratio))

        scores: dict[str, float] = {
            "pillar": pillar_result.pillar_score,
            "golden_signal": gs_result.coverage_score,
            "alert_coverage": alert_result.coverage_percent,
            "tracing_completeness": tracing_result.completeness_percent,
            "log_level": log_result.balance_score,
            "dashboard": dashboard_result.coverage_percent,
            "sli_monitoring": sli_result.maturity_score,
            "correlation": correlation_result.score,
            "blind_spot": blind_spot_score,
        }
        overall_score = sum(
            scores[k] * _ANALYSIS_WEIGHTS[k] for k in _ANALYSIS_WEIGHTS
        )
        overall_score = max(0.0, min(100.0, overall_score))

        # Build recommendations
        recs = self._build_recommendations(
            pillar_result, gs_result, alert_result, tracing_result,
            log_result, dashboard_result, sli_result, correlation_result,
            blind_spots, cost_result, components,
        )

        summary_parts = [
            f"Observability Gap Analysis: {len(components)} components analyzed.",
            f"Overall score: {overall_score:.1f}/100.",
            f"Gaps found: {len(gaps)} ({critical} critical, {high} high).",
            f"Blind spots: {len(blind_spots)}.",
        ]

        return ObservabilityGapReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_components=len(components),
            total_gaps=len(gaps),
            critical_gaps=critical,
            high_gaps=high,
            medium_gaps=medium,
            low_gaps=low,
            info_gaps=info,
            pillar_analysis=pillar_result,
            golden_signal_analysis=gs_result,
            alert_coverage=alert_result,
            tracing_completeness=tracing_result,
            log_level_analysis=log_result,
            dashboard_coverage=dashboard_result,
            sli_monitoring=sli_result,
            correlation_analysis=correlation_result,
            mttd_estimation=mttd,
            cost_optimization=cost_result,
            gaps=gaps,
            blind_spots=blind_spots,
            overall_score=round(overall_score, 1),
            summary=" ".join(summary_parts),
            recommendations=recs,
        )

    # ------------------------------------------------------------------
    # Three-pillar analysis
    # ------------------------------------------------------------------

    def analyze_pillars(
        self,
        coverage: Sequence[PillarCoverage],
        components: Sequence[Component],
    ) -> PillarAnalysisResult:
        """Evaluate metrics/logs/traces coverage across components."""
        n = len(components)
        if n == 0:
            return PillarAnalysisResult()

        coverage_map = {pc.component_id: pc for pc in coverage}

        metrics_count = 0
        logs_count = 0
        traces_count = 0
        metrics_completeness_sum = 0.0
        logs_completeness_sum = 0.0
        traces_completeness_sum = 0.0

        for comp in components:
            pc = coverage_map.get(comp.id)
            if pc is None:
                continue
            if pc.metrics_enabled:
                metrics_count += 1
                metrics_completeness_sum += pc.metrics_completeness
            if pc.logs_enabled:
                logs_count += 1
                logs_completeness_sum += pc.logs_completeness
            if pc.traces_enabled:
                traces_count += 1
                traces_completeness_sum += pc.traces_completeness

        avg_metrics = metrics_completeness_sum / max(1, metrics_count)
        avg_logs = logs_completeness_sum / max(1, logs_count)
        avg_traces = traces_completeness_sum / max(1, traces_count)

        # Score: weighted average of enabled ratios * completeness
        pillar_score = (
            (metrics_count / n) * avg_metrics * 100.0
            + (logs_count / n) * avg_logs * 100.0
            + (traces_count / n) * avg_traces * 100.0
        ) / 3.0

        return PillarAnalysisResult(
            total_components=n,
            metrics_covered=metrics_count,
            logs_covered=logs_count,
            traces_covered=traces_count,
            average_metrics_completeness=round(avg_metrics, 3),
            average_logs_completeness=round(avg_logs, 3),
            average_traces_completeness=round(avg_traces, 3),
            pillar_score=round(max(0.0, min(100.0, pillar_score)), 1),
        )

    # ------------------------------------------------------------------
    # Golden signal coverage
    # ------------------------------------------------------------------

    def analyze_golden_signals(
        self,
        coverage: Sequence[GoldenSignalCoverage],
        components: Sequence[Component],
    ) -> GoldenSignalAnalysisResult:
        """Evaluate golden signal monitoring coverage."""
        n = len(components)
        if n == 0:
            return GoldenSignalAnalysisResult()

        cov_map = {gs.component_id: gs for gs in coverage}

        lat = trf = err = sat = 0
        for comp in components:
            gs = cov_map.get(comp.id)
            if gs is None:
                continue
            if gs.latency_monitored:
                lat += 1
            if gs.traffic_monitored:
                trf += 1
            if gs.errors_monitored:
                err += 1
            if gs.saturation_monitored:
                sat += 1

        total_possible = n * 4
        total_covered = lat + trf + err + sat
        score = (total_covered / total_possible * 100.0) if total_possible > 0 else 0.0

        return GoldenSignalAnalysisResult(
            total_components=n,
            latency_covered=lat,
            traffic_covered=trf,
            errors_covered=err,
            saturation_covered=sat,
            coverage_score=round(max(0.0, min(100.0, score)), 1),
        )

    # ------------------------------------------------------------------
    # Alert coverage mapping
    # ------------------------------------------------------------------

    def analyze_alert_coverage(
        self,
        mappings: Sequence[AlertMapping],
        components: Sequence[Component],
    ) -> AlertCoverageResult:
        """Determine which failure modes are covered by alerts."""
        mapping_map = {am.component_id: am for am in mappings}

        total_modes = 0
        alerted_modes = 0
        unalerted: list[tuple[str, str]] = []

        for comp in components:
            am = mapping_map.get(comp.id)
            if am is not None:
                modes = am.failure_modes
            else:
                modes = _DEFAULT_FAILURE_MODES.get(comp.type, ["unknown_failure"])

            alerted = set()
            if am is not None:
                alerted = set(am.alerted_modes)

            total_modes += len(modes)
            for mode in modes:
                if mode in alerted:
                    alerted_modes += 1
                else:
                    unalerted.append((comp.id, mode))

        pct = (alerted_modes / total_modes * 100.0) if total_modes > 0 else 0.0

        return AlertCoverageResult(
            total_failure_modes=total_modes,
            alerted_failure_modes=alerted_modes,
            unalerted_failure_modes=total_modes - alerted_modes,
            coverage_percent=round(max(0.0, min(100.0, pct)), 1),
            unalerted_details=unalerted,
        )

    # ------------------------------------------------------------------
    # Distributed tracing completeness
    # ------------------------------------------------------------------

    def analyze_tracing_completeness(
        self,
        propagations: Sequence[TracePropagation],
    ) -> TracingCompletenessResult:
        """Check trace propagation across all dependency edges."""
        all_edges = self._graph.all_dependency_edges()
        if not all_edges:
            return TracingCompletenessResult(completeness_percent=100.0)

        prop_set: set[tuple[str, str]] = set()
        for tp in propagations:
            if tp.propagation_enabled:
                prop_set.add((tp.source_id, tp.target_id))

        gap_edges: list[tuple[str, str]] = []
        propagated = 0
        for dep in all_edges:
            if (dep.source_id, dep.target_id) in prop_set:
                propagated += 1
            else:
                gap_edges.append((dep.source_id, dep.target_id))

        total = len(all_edges)
        pct = (propagated / total * 100.0) if total > 0 else 100.0

        return TracingCompletenessResult(
            total_edges=total,
            propagated_edges=propagated,
            gap_edges=gap_edges,
            completeness_percent=round(max(0.0, min(100.0, pct)), 1),
        )

    # ------------------------------------------------------------------
    # Log level analysis
    # ------------------------------------------------------------------

    def analyze_log_levels(
        self,
        configs: Sequence[LogLevelConfig],
        components: Sequence[Component],
    ) -> LogLevelAnalysisResult:
        """Determine which components are too verbose or too quiet."""
        n = len(components)
        if n == 0:
            return LogLevelAnalysisResult()

        cfg_map = {lc.component_id: lc for lc in configs}

        verbose: list[str] = []
        quiet: list[str] = []
        balanced: list[str] = []
        total_volume = 0.0

        for comp in components:
            lc = cfg_map.get(comp.id)
            if lc is None:
                # No config means we cannot assess — treat as quiet
                quiet.append(comp.id)
                continue

            total_volume += lc.estimated_volume_gb_per_day

            if lc.level == LogLevel.DEBUG and lc.estimated_volume_gb_per_day > _VERBOSE_VOLUME_THRESHOLD_GB:
                verbose.append(comp.id)
            elif lc.level in _QUIET_LEVELS:
                quiet.append(comp.id)
            else:
                balanced.append(comp.id)

        # Score: fraction of balanced components
        balance_score = (len(balanced) / n * 100.0) if n > 0 else 0.0

        return LogLevelAnalysisResult(
            total_components=n,
            too_verbose=verbose,
            too_quiet=quiet,
            balanced=balanced,
            estimated_daily_volume_gb=round(total_volume, 2),
            balance_score=round(max(0.0, min(100.0, balance_score)), 1),
        )

    # ------------------------------------------------------------------
    # Dashboard coverage
    # ------------------------------------------------------------------

    def analyze_dashboard_coverage(
        self,
        configs: Sequence[DashboardConfig],
        components: Sequence[Component],
    ) -> DashboardCoverageResult:
        """Assess dashboard coverage across components."""
        n = len(components)
        if n == 0:
            return DashboardCoverageResult()

        cfg_map = {dc.component_id: dc for dc in configs}
        with_dashboard = 0
        total_metrics = 0

        for comp in components:
            dc = cfg_map.get(comp.id)
            if dc is not None and dc.has_dashboard:
                with_dashboard += 1
                total_metrics += dc.metrics_on_dashboard

        avg_metrics = total_metrics / max(1, with_dashboard)
        pct = (with_dashboard / n * 100.0) if n > 0 else 0.0

        return DashboardCoverageResult(
            total_components=n,
            components_with_dashboard=with_dashboard,
            average_metrics_per_dashboard=round(avg_metrics, 1),
            coverage_percent=round(max(0.0, min(100.0, pct)), 1),
        )

    # ------------------------------------------------------------------
    # SLI/SLO monitoring
    # ------------------------------------------------------------------

    def analyze_sli_monitoring(
        self,
        configs: Sequence[SLIMonitoringConfig],
        components: Sequence[Component],
    ) -> SLIMonitoringResult:
        """Evaluate SLI/SLO monitoring maturity."""
        n = len(components)
        if n == 0:
            return SLIMonitoringResult()

        cfg_map = {sc.component_id: sc for sc in configs}

        sli_count = 0
        slo_count = 0
        eb_count = 0
        br_count = 0

        for comp in components:
            sc = cfg_map.get(comp.id)
            if sc is None:
                continue
            if sc.sli_defined:
                sli_count += 1
            if sc.slo_defined:
                slo_count += 1
            if sc.error_budget_tracking:
                eb_count += 1
            if sc.burn_rate_alerting:
                br_count += 1

        # Maturity score: weighted combination
        # SLI definition: 30%, SLO: 30%, error budget: 20%, burn rate: 20%
        score = (
            (sli_count / n) * 30.0
            + (slo_count / n) * 30.0
            + (eb_count / n) * 20.0
            + (br_count / n) * 20.0
        ) if n > 0 else 0.0

        return SLIMonitoringResult(
            total_components=n,
            sli_defined_count=sli_count,
            slo_defined_count=slo_count,
            error_budget_tracking_count=eb_count,
            burn_rate_alerting_count=br_count,
            maturity_score=round(max(0.0, min(100.0, score)), 1),
        )

    # ------------------------------------------------------------------
    # Correlation capability
    # ------------------------------------------------------------------

    def analyze_correlation(
        self,
        pillar_coverage: Sequence[PillarCoverage],
        trace_propagations: Sequence[TracePropagation],
    ) -> CorrelationAnalysisResult:
        """Determine how well metrics, logs, and traces can be correlated."""
        has_metrics = any(pc.metrics_enabled for pc in pillar_coverage)
        has_logs = any(pc.logs_enabled for pc in pillar_coverage)
        has_traces = any(pc.traces_enabled for pc in pillar_coverage)
        has_propagation = any(tp.propagation_enabled for tp in trace_propagations)

        # Correlation pairs
        ml = has_metrics and has_logs
        mt = has_metrics and has_traces and has_propagation
        lt = has_logs and has_traces and has_propagation

        pairs_count = sum([ml, mt, lt])
        if pairs_count == 3:
            capability = CorrelationCapability.FULL
        elif pairs_count >= 1:
            capability = CorrelationCapability.PARTIAL
        else:
            capability = CorrelationCapability.NONE

        score = pairs_count / 3.0 * 100.0

        return CorrelationAnalysisResult(
            capability=capability,
            metrics_logs_correlated=ml,
            metrics_traces_correlated=mt,
            logs_traces_correlated=lt,
            score=round(score, 1),
        )

    # ------------------------------------------------------------------
    # Blind spot detection
    # ------------------------------------------------------------------

    def detect_blind_spots(
        self,
        pillar_coverage: Sequence[PillarCoverage],
        components: Sequence[Component],
    ) -> list[BlindSpot]:
        """Find components with zero observability coverage."""
        covered_ids = set()
        for pc in pillar_coverage:
            if pc.metrics_enabled or pc.logs_enabled or pc.traces_enabled:
                covered_ids.add(pc.component_id)

        spots: list[BlindSpot] = []
        for comp in components:
            if comp.id not in covered_ids:
                spots.append(BlindSpot(
                    component_id=comp.id,
                    component_type=comp.type.value,
                    severity=GapSeverity.CRITICAL,
                    description=(
                        f"Component '{comp.id}' ({comp.type.value}) has no metrics, "
                        "logs, or traces enabled — complete blind spot."
                    ),
                ))
        return spots

    # ------------------------------------------------------------------
    # MTTD estimation
    # ------------------------------------------------------------------

    def estimate_mttd(
        self,
        gs_result: GoldenSignalAnalysisResult,
        alert_result: AlertCoverageResult,
        pillar_result: PillarAnalysisResult,
    ) -> MTTDEstimation:
        """Estimate mean time to detect based on observability posture."""
        factors: list[str] = []

        # Golden signal coverage effect
        gs_ratio = gs_result.coverage_score / 100.0 if gs_result.coverage_score > 0 else 0.0

        # Alert coverage effect
        alert_ratio = alert_result.coverage_percent / 100.0

        # Pillar coverage effect
        pillar_ratio = pillar_result.pillar_score / 100.0

        combined = (gs_ratio * 0.4 + alert_ratio * 0.35 + pillar_ratio * 0.25)

        # MTTD decreases with better observability: linear interpolation
        mttd = _MTTD_BASE_MINUTES - (_MTTD_BASE_MINUTES - _MTTD_BEST_MINUTES) * combined
        mttd = max(_MTTD_BEST_MINUTES, mttd)

        if gs_ratio < 0.5:
            factors.append("Low golden signal coverage increases detection time.")
        if alert_ratio < 0.5:
            factors.append("Low alert coverage increases detection time.")
        if pillar_ratio < 0.5:
            factors.append("Low pillar coverage increases detection time.")
        if combined > 0.8:
            factors.append("Strong observability posture enables rapid detection.")

        if mttd <= 5.0:
            rating = "excellent"
        elif mttd <= 15.0:
            rating = "good"
        elif mttd <= 30.0:
            rating = "fair"
        else:
            rating = "poor"

        return MTTDEstimation(
            estimated_mttd_minutes=round(mttd, 1),
            contributing_factors=factors,
            rating=rating,
        )

    # ------------------------------------------------------------------
    # Observability cost optimization
    # ------------------------------------------------------------------

    def analyze_cost(self, setup: ObservabilitySetup) -> CostOptimizationResult:
        """Analyze observability cost and find savings opportunities."""
        current = setup.monthly_observability_cost_usd
        target = setup.target_monthly_budget_usd
        over = current > target if target > 0 else False

        savings: list[str] = []
        estimated_savings = 0.0

        # Check log volume
        for lc in setup.log_level_configs:
            if lc.level == LogLevel.DEBUG and lc.estimated_volume_gb_per_day > _VERBOSE_VOLUME_THRESHOLD_GB:
                saving = lc.estimated_volume_gb_per_day * 0.5 * 30  # rough $0.5/GB savings
                estimated_savings += saving
                savings.append(
                    f"Reduce DEBUG logging on '{lc.component_id}' to save ~${saving:.0f}/month."
                )

        # Check low-value dashboards (0 metrics)
        for dc in setup.dashboard_configs:
            if dc.has_dashboard and dc.metrics_on_dashboard == 0:
                savings.append(
                    f"Dashboard for '{dc.component_id}' has 0 metrics — consider removing."
                )

        if over and target > 0:
            excess = current - target
            savings.append(
                f"Currently ${excess:.0f}/month over budget. Review sampling rates and retention."
            )

        return CostOptimizationResult(
            current_monthly_cost_usd=current,
            target_monthly_budget_usd=target,
            over_budget=over,
            savings_opportunities=savings,
            estimated_savings_usd=round(estimated_savings, 2),
        )

    # ------------------------------------------------------------------
    # Gap generation helpers
    # ------------------------------------------------------------------

    def _gaps_from_pillars(
        self,
        result: PillarAnalysisResult,
        coverage: Sequence[PillarCoverage],
        components: Sequence[Component],
    ) -> list[ObservabilityGap]:
        gaps: list[ObservabilityGap] = []
        cov_map = {pc.component_id: pc for pc in coverage}
        for comp in components:
            pc = cov_map.get(comp.id)
            if pc is None:
                continue
            missing: list[str] = []
            if not pc.metrics_enabled:
                missing.append("metrics")
            if not pc.logs_enabled:
                missing.append("logs")
            if not pc.traces_enabled:
                missing.append("traces")
            if missing:
                severity = GapSeverity.HIGH if len(missing) >= 2 else GapSeverity.MEDIUM
                gaps.append(ObservabilityGap(
                    component_id=comp.id,
                    gap_type="pillar_coverage",
                    severity=severity,
                    description=f"Missing pillars: {', '.join(missing)}.",
                    recommendation=f"Enable {', '.join(missing)} for '{comp.id}'.",
                ))
        return gaps

    def _gaps_from_golden_signals(
        self,
        result: GoldenSignalAnalysisResult,
        coverage: Sequence[GoldenSignalCoverage],
        components: Sequence[Component],
    ) -> list[ObservabilityGap]:
        gaps: list[ObservabilityGap] = []
        cov_map = {gs.component_id: gs for gs in coverage}
        for comp in components:
            gs = cov_map.get(comp.id)
            if gs is None:
                continue
            missing: list[str] = []
            if not gs.latency_monitored:
                missing.append("latency")
            if not gs.traffic_monitored:
                missing.append("traffic")
            if not gs.errors_monitored:
                missing.append("errors")
            if not gs.saturation_monitored:
                missing.append("saturation")
            if missing:
                severity = GapSeverity.HIGH if len(missing) >= 3 else GapSeverity.MEDIUM
                gaps.append(ObservabilityGap(
                    component_id=comp.id,
                    gap_type="golden_signal_coverage",
                    severity=severity,
                    description=f"Missing golden signals: {', '.join(missing)}.",
                    recommendation=f"Add monitoring for {', '.join(missing)} on '{comp.id}'.",
                ))
        return gaps

    def _gaps_from_alerts(self, result: AlertCoverageResult) -> list[ObservabilityGap]:
        gaps: list[ObservabilityGap] = []
        for comp_id, mode in result.unalerted_details:
            gaps.append(ObservabilityGap(
                component_id=comp_id,
                gap_type="alert_coverage",
                severity=GapSeverity.MEDIUM,
                description=f"Failure mode '{mode}' has no alert.",
                recommendation=f"Create an alert for '{mode}' on '{comp_id}'.",
            ))
        return gaps

    def _gaps_from_tracing(self, result: TracingCompletenessResult) -> list[ObservabilityGap]:
        gaps: list[ObservabilityGap] = []
        for src, tgt in result.gap_edges:
            gaps.append(ObservabilityGap(
                component_id=src,
                gap_type="trace_propagation",
                severity=GapSeverity.MEDIUM,
                description=f"Trace not propagated from '{src}' to '{tgt}'.",
                recommendation=f"Enable trace context propagation from '{src}' to '{tgt}'.",
            ))
        return gaps

    def _gaps_from_log_levels(self, result: LogLevelAnalysisResult) -> list[ObservabilityGap]:
        gaps: list[ObservabilityGap] = []
        for cid in result.too_verbose:
            gaps.append(ObservabilityGap(
                component_id=cid,
                gap_type="log_level",
                severity=GapSeverity.LOW,
                description=f"Component '{cid}' logging at DEBUG with high volume.",
                recommendation=f"Raise log level to INFO on '{cid}' to reduce cost/noise.",
            ))
        for cid in result.too_quiet:
            gaps.append(ObservabilityGap(
                component_id=cid,
                gap_type="log_level",
                severity=GapSeverity.MEDIUM,
                description=f"Component '{cid}' logging is too quiet (ERROR/CRITICAL only or unconfigured).",
                recommendation=f"Add INFO-level logging on '{cid}' for better visibility.",
            ))
        return gaps

    def _gaps_from_dashboards(
        self,
        result: DashboardCoverageResult,
        configs: Sequence[DashboardConfig],
        components: Sequence[Component],
    ) -> list[ObservabilityGap]:
        gaps: list[ObservabilityGap] = []
        cfg_map = {dc.component_id: dc for dc in configs}
        for comp in components:
            dc = cfg_map.get(comp.id)
            if dc is None or not dc.has_dashboard:
                gaps.append(ObservabilityGap(
                    component_id=comp.id,
                    gap_type="dashboard_coverage",
                    severity=GapSeverity.LOW,
                    description=f"No dashboard for '{comp.id}'.",
                    recommendation=f"Create a dashboard for '{comp.id}'.",
                ))
        return gaps

    def _gaps_from_sli(
        self,
        result: SLIMonitoringResult,
        configs: Sequence[SLIMonitoringConfig],
        components: Sequence[Component],
    ) -> list[ObservabilityGap]:
        gaps: list[ObservabilityGap] = []
        cfg_map = {sc.component_id: sc for sc in configs}
        for comp in components:
            sc = cfg_map.get(comp.id)
            if sc is None or not sc.sli_defined:
                gaps.append(ObservabilityGap(
                    component_id=comp.id,
                    gap_type="sli_monitoring",
                    severity=GapSeverity.HIGH,
                    description=f"No SLI defined for '{comp.id}'.",
                    recommendation=f"Define SLIs for '{comp.id}' to enable SLO tracking.",
                ))
            elif not sc.slo_defined:
                gaps.append(ObservabilityGap(
                    component_id=comp.id,
                    gap_type="sli_monitoring",
                    severity=GapSeverity.MEDIUM,
                    description=f"SLI defined but no SLO for '{comp.id}'.",
                    recommendation=f"Set SLO targets for '{comp.id}' based on defined SLIs.",
                ))
        return gaps

    def _gaps_from_blind_spots(self, spots: list[BlindSpot]) -> list[ObservabilityGap]:
        return [
            ObservabilityGap(
                component_id=bs.component_id,
                gap_type="blind_spot",
                severity=GapSeverity.CRITICAL,
                description=bs.description,
                recommendation=f"Instrument '{bs.component_id}' with metrics, logs, and traces.",
            )
            for bs in spots
        ]

    def _gaps_from_correlation(self, result: CorrelationAnalysisResult) -> list[ObservabilityGap]:
        gaps: list[ObservabilityGap] = []
        if result.capability == CorrelationCapability.NONE:
            gaps.append(ObservabilityGap(
                component_id="*",
                gap_type="correlation",
                severity=GapSeverity.HIGH,
                description="No correlation capability between observability pillars.",
                recommendation="Enable at least two pillars with shared context for correlation.",
            ))
        elif result.capability == CorrelationCapability.PARTIAL:
            missing: list[str] = []
            if not result.metrics_logs_correlated:
                missing.append("metrics-logs")
            if not result.metrics_traces_correlated:
                missing.append("metrics-traces")
            if not result.logs_traces_correlated:
                missing.append("logs-traces")
            if missing:
                gaps.append(ObservabilityGap(
                    component_id="*",
                    gap_type="correlation",
                    severity=GapSeverity.MEDIUM,
                    description=f"Missing correlation pairs: {', '.join(missing)}.",
                    recommendation="Enable full pillar correlation for faster root-cause analysis.",
                ))
        return gaps

    # ------------------------------------------------------------------
    # Recommendations builder
    # ------------------------------------------------------------------

    def _build_recommendations(
        self,
        pillar: PillarAnalysisResult,
        gs: GoldenSignalAnalysisResult,
        alert: AlertCoverageResult,
        tracing: TracingCompletenessResult,
        log_lvl: LogLevelAnalysisResult,
        dashboard: DashboardCoverageResult,
        sli: SLIMonitoringResult,
        corr: CorrelationAnalysisResult,
        blind_spots: list[BlindSpot],
        cost: CostOptimizationResult,
        components: Sequence[Component],
    ) -> list[str]:
        recs: list[str] = []
        if blind_spots:
            recs.append(
                f"Instrument {len(blind_spots)} blind-spot component(s) with metrics, logs, and traces."
            )
        if pillar.pillar_score < 50.0:
            recs.append("Pillar coverage is below 50%. Prioritize enabling metrics, logs, and traces.")
        if gs.coverage_score < 50.0:
            recs.append("Golden signal coverage is below 50%. Add monitoring for latency, traffic, errors, and saturation.")
        if alert.coverage_percent < 50.0:
            recs.append(
                f"Alert coverage is {alert.coverage_percent:.0f}%. Create alerts for unmonitored failure modes."
            )
        if tracing.completeness_percent < 100.0 and tracing.total_edges > 0:
            recs.append(
                f"Tracing completeness is {tracing.completeness_percent:.0f}%. Enable trace propagation on {len(tracing.gap_edges)} edge(s)."
            )
        if log_lvl.too_verbose:
            recs.append(
                f"{len(log_lvl.too_verbose)} component(s) have verbose DEBUG logging. Consider raising to INFO."
            )
        if log_lvl.too_quiet:
            recs.append(
                f"{len(log_lvl.too_quiet)} component(s) have insufficient logging. Add INFO-level logs."
            )
        if dashboard.coverage_percent < 50.0:
            recs.append("Dashboard coverage is low. Create dashboards for key components.")
        if sli.maturity_score < 50.0:
            recs.append("SLI/SLO maturity is low. Define SLIs and SLOs for critical services.")
        if corr.capability == CorrelationCapability.NONE:
            recs.append("No cross-pillar correlation. Enable shared context IDs across metrics, logs, and traces.")
        elif corr.capability == CorrelationCapability.PARTIAL:
            recs.append("Partial correlation capability. Work towards full metrics-logs-traces correlation.")
        if cost.over_budget:
            recs.append(
                f"Observability cost (${cost.current_monthly_cost_usd:.0f}/mo) exceeds budget (${cost.target_monthly_budget_usd:.0f}/mo)."
            )
        for s in cost.savings_opportunities:
            recs.append(s)
        return recs
