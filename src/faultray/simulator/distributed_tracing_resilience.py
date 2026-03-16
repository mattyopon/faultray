"""Distributed Tracing Resilience Analyzer.

Analyzes distributed tracing infrastructure resilience and simulates
trace pipeline failures.  Covers instrumentation gaps, collector
scaling, sampling strategies, storage cost projection, and correlation
between trace observability and overall system resilience.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TracingComponent(str, Enum):
    """Components that make up a distributed tracing pipeline."""

    INSTRUMENTATION = "instrumentation"
    COLLECTOR = "collector"
    SAMPLER = "sampler"
    EXPORTER = "exporter"
    STORAGE_BACKEND = "storage_backend"
    QUERY_ENGINE = "query_engine"
    ALERTING = "alerting"


class TraceLossScenario(str, Enum):
    """Scenarios that cause trace data loss or corruption."""

    COLLECTOR_OVERLOAD = "collector_overload"
    SAMPLING_MISCONFIGURATION = "sampling_misconfiguration"
    EXPORTER_FAILURE = "exporter_failure"
    STORAGE_FULL = "storage_full"
    NETWORK_PARTITION = "network_partition"
    CLOCK_SKEW = "clock_skew"
    SPAN_DROP = "span_drop"
    CONTEXT_PROPAGATION_FAILURE = "context_propagation_failure"
    HIGH_CARDINALITY_EXPLOSION = "high_cardinality_explosion"
    CIRCULAR_TRACE = "circular_trace"


class SamplingStrategy(str, Enum):
    """Sampling strategies for trace collection."""

    ALWAYS_ON = "always_on"
    PROBABILISTIC = "probabilistic"
    RATE_LIMITING = "rate_limiting"
    ADAPTIVE = "adaptive"
    TAIL_BASED = "tail_based"
    PARENT_BASED = "parent_based"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class TracingConfig(BaseModel):
    """Configuration describing the tracing pipeline."""

    collectors: int = Field(default=1, ge=1)
    sampling_strategy: SamplingStrategy = SamplingStrategy.PROBABILISTIC
    sampling_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    exporters: int = Field(default=1, ge=1)
    storage_retention_days: int = Field(default=7, ge=1)
    storage_capacity_gb: float = Field(default=100.0, ge=0.0)
    has_redundant_collectors: bool = False
    has_tail_sampling: bool = False
    max_spans_per_second: int = Field(default=10000, ge=1)
    instrumented_services: list[str] = Field(default_factory=list)


class TraceReliabilityMetrics(BaseModel):
    """Quantitative metrics for trace pipeline reliability."""

    trace_completeness: float = Field(default=1.0, ge=0.0, le=1.0)
    span_drop_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_overhead_ms: float = Field(default=0.0, ge=0.0)
    storage_cost_per_day: float = Field(default=0.0, ge=0.0)
    mean_time_to_detect_minutes: float = Field(default=0.0, ge=0.0)
    sampling_effectiveness: float = Field(default=1.0, ge=0.0, le=1.0)


class TracePipelineAssessment(BaseModel):
    """Result of a full tracing pipeline assessment."""

    pipeline_components: list[str] = Field(default_factory=list)
    single_points_of_failure: list[str] = Field(default_factory=list)
    estimated_trace_loss_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    bottlenecks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    overall_reliability: float = Field(default=0.0, ge=0.0, le=100.0)


class TraceLossResult(BaseModel):
    """Outcome of simulating a trace-loss scenario."""

    scenario: TraceLossScenario
    affected_services: list[str] = Field(default_factory=list)
    estimated_loss_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    detection_delay_minutes: float = Field(default=0.0, ge=0.0)
    data_loss_possible: bool = False
    mitigations: list[str] = Field(default_factory=list)
    severity: float = Field(default=0.0, ge=0.0, le=1.0)


class SamplingRecommendation(BaseModel):
    """Recommended sampling configuration."""

    strategy: SamplingStrategy
    recommended_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    estimated_spans_per_second: int = 0
    estimated_storage_gb_per_day: float = 0.0
    trade_off_summary: str = ""
    within_budget: bool = True


class ObservabilityGap(BaseModel):
    """A component that lacks tracing instrumentation."""

    component_id: str
    component_name: str
    component_type: str
    gap_type: str = "no_instrumentation"
    risk_level: str = "medium"
    recommendation: str = ""


class StorageCostEstimate(BaseModel):
    """Projected trace storage costs."""

    retention_days: int = 7
    daily_storage_gb: float = 0.0
    total_storage_gb: float = 0.0
    estimated_daily_cost: float = 0.0
    estimated_total_cost: float = 0.0
    cost_per_million_spans: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class CollectorScalingResult(BaseModel):
    """Result of a collector scaling simulation."""

    current_collectors: int = 1
    recommended_collectors: int = 1
    spans_per_second: int = 0
    utilization_percent: float = 0.0
    headroom_percent: float = 0.0
    needs_scaling: bool = False
    recommendations: list[str] = Field(default_factory=list)


class TraceResilienceCorrelation(BaseModel):
    """Correlation between trace observability and system resilience."""

    observability_score: float = Field(default=0.0, ge=0.0, le=100.0)
    resilience_score: float = Field(default=0.0, ge=0.0, le=100.0)
    correlation_strength: str = "none"
    blind_spots: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Base impact severity per scenario (0-100 scale)
_SCENARIO_BASE_IMPACT: dict[TraceLossScenario, float] = {
    TraceLossScenario.COLLECTOR_OVERLOAD: 60.0,
    TraceLossScenario.SAMPLING_MISCONFIGURATION: 45.0,
    TraceLossScenario.EXPORTER_FAILURE: 70.0,
    TraceLossScenario.STORAGE_FULL: 80.0,
    TraceLossScenario.NETWORK_PARTITION: 75.0,
    TraceLossScenario.CLOCK_SKEW: 30.0,
    TraceLossScenario.SPAN_DROP: 50.0,
    TraceLossScenario.CONTEXT_PROPAGATION_FAILURE: 65.0,
    TraceLossScenario.HIGH_CARDINALITY_EXPLOSION: 55.0,
    TraceLossScenario.CIRCULAR_TRACE: 40.0,
}

# Default per-span size in KB
_DEFAULT_SPAN_SIZE_KB = 0.5

# Cost per GB stored (USD, for estimation)
_COST_PER_GB_USD = 0.10

# Collector capacity: max spans/s per collector instance
_COLLECTOR_CAPACITY_SPANS_PER_SEC = 10000

# Overhead per tracing component in ms
_COMPONENT_OVERHEAD_MS: dict[TracingComponent, float] = {
    TracingComponent.INSTRUMENTATION: 0.5,
    TracingComponent.COLLECTOR: 1.0,
    TracingComponent.SAMPLER: 0.2,
    TracingComponent.EXPORTER: 0.8,
    TracingComponent.STORAGE_BACKEND: 2.0,
    TracingComponent.QUERY_ENGINE: 0.0,
    TracingComponent.ALERTING: 0.0,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp a value between lo and hi."""
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DistributedTracingEngine:
    """Stateless engine for distributed tracing resilience analysis."""

    # -- pipeline assessment ------------------------------------------------

    def assess_pipeline(
        self,
        graph: InfraGraph,
        tracing_config: TracingConfig,
    ) -> TracePipelineAssessment:
        """Perform a full assessment of the tracing pipeline."""
        pipeline_components: list[str] = [tc.value for tc in TracingComponent]
        spofs: list[str] = []
        bottlenecks: list[str] = []
        recommendations: list[str] = []

        # Check single points of failure
        if tracing_config.collectors == 1 and not tracing_config.has_redundant_collectors:
            spofs.append("collector")
            recommendations.append("Add redundant collectors to eliminate SPOF")

        if tracing_config.exporters == 1:
            spofs.append("exporter")
            recommendations.append("Add redundant exporters for fault tolerance")

        # Assess sampling configuration
        if tracing_config.sampling_strategy == SamplingStrategy.ALWAYS_ON:
            bottlenecks.append("always_on sampling generates excessive data")
            recommendations.append(
                "Consider probabilistic or adaptive sampling to reduce volume"
            )

        if (
            tracing_config.sampling_strategy == SamplingStrategy.PROBABILISTIC
            and tracing_config.sampling_rate < 0.01
        ):
            recommendations.append(
                "Very low sampling rate may miss important traces; consider tail-based sampling"
            )

        # Check instrumentation coverage
        component_ids = set(graph.components.keys())
        instrumented = set(tracing_config.instrumented_services)
        uninstrumented = component_ids - instrumented
        if uninstrumented and component_ids:
            coverage = len(instrumented & component_ids) / len(component_ids) if component_ids else 0
            if coverage < 0.5:
                bottlenecks.append("low instrumentation coverage")
                recommendations.append(
                    "Instrument more services to improve trace completeness"
                )

        # Storage capacity check
        daily_gb = self._estimate_daily_storage_gb(graph, tracing_config)
        total_needed = daily_gb * tracing_config.storage_retention_days
        if total_needed > tracing_config.storage_capacity_gb and tracing_config.storage_capacity_gb > 0:
            bottlenecks.append("storage capacity insufficient for retention period")
            recommendations.append(
                "Increase storage capacity or reduce retention/sampling rate"
            )

        # Collector capacity check
        total_services = len(graph.components)
        effective_rate = tracing_config.sampling_rate if tracing_config.sampling_strategy != SamplingStrategy.ALWAYS_ON else 1.0
        estimated_spans_per_sec = total_services * 100 * effective_rate  # rough estimate
        collector_capacity = tracing_config.collectors * _COLLECTOR_CAPACITY_SPANS_PER_SEC
        if estimated_spans_per_sec > collector_capacity * 0.8 and collector_capacity > 0:
            bottlenecks.append("collector capacity nearing limit")
            recommendations.append("Scale collectors to handle span volume")

        # Estimate trace loss
        loss_percent = 0.0
        if spofs:
            loss_percent += len(spofs) * 5.0
        if bottlenecks:
            loss_percent += len(bottlenecks) * 3.0
        if not tracing_config.has_tail_sampling:
            loss_percent += 2.0

        loss_percent = _clamp(loss_percent, 0.0, 100.0)

        # Overall reliability
        reliability = 100.0
        reliability -= len(spofs) * 15.0
        reliability -= len(bottlenecks) * 8.0
        if tracing_config.sampling_rate < 0.05 and tracing_config.sampling_strategy == SamplingStrategy.PROBABILISTIC:
            reliability -= 10.0
        if tracing_config.has_redundant_collectors:
            reliability += 5.0
        if tracing_config.has_tail_sampling:
            reliability += 5.0
        reliability = _clamp(reliability, 0.0, 100.0)

        return TracePipelineAssessment(
            pipeline_components=pipeline_components,
            single_points_of_failure=spofs,
            estimated_trace_loss_percent=round(loss_percent, 2),
            bottlenecks=bottlenecks,
            recommendations=recommendations,
            overall_reliability=round(reliability, 2),
        )

    # -- trace loss simulation ----------------------------------------------

    def simulate_trace_loss(
        self,
        graph: InfraGraph,
        scenario: TraceLossScenario,
        tracing_config: TracingConfig | None = None,
    ) -> TraceLossResult:
        """Simulate what happens when a particular trace loss scenario occurs."""
        config = tracing_config or TracingConfig()
        base_impact = _SCENARIO_BASE_IMPACT[scenario]
        component_ids = list(graph.components.keys())
        mitigations: list[str] = []
        detection_delay = 5.0  # default detection delay in minutes
        data_loss = False

        if scenario == TraceLossScenario.COLLECTOR_OVERLOAD:
            loss = base_impact
            if config.has_redundant_collectors:
                loss *= 0.3
            else:
                mitigations.append("Deploy redundant collectors with load balancing")
            detection_delay = 3.0
            mitigations.append("Implement backpressure handling in collectors")

        elif scenario == TraceLossScenario.SAMPLING_MISCONFIGURATION:
            loss = base_impact
            if config.sampling_strategy == SamplingStrategy.ADAPTIVE:
                loss *= 0.4
            mitigations.append("Validate sampling configuration in CI/CD pipeline")
            mitigations.append("Use adaptive sampling to self-correct")
            detection_delay = 15.0

        elif scenario == TraceLossScenario.EXPORTER_FAILURE:
            loss = base_impact
            if config.exporters > 1:
                loss *= 0.4
            else:
                mitigations.append("Add redundant exporters")
            data_loss = config.exporters == 1
            mitigations.append("Implement local buffering for failed exports")
            detection_delay = 5.0

        elif scenario == TraceLossScenario.STORAGE_FULL:
            loss = base_impact
            data_loss = True
            mitigations.append("Set up storage capacity alerts")
            mitigations.append("Implement automatic data rotation")
            mitigations.append("Consider tiered storage for older traces")
            detection_delay = 10.0

        elif scenario == TraceLossScenario.NETWORK_PARTITION:
            loss = base_impact
            if config.has_redundant_collectors:
                loss *= 0.5
            data_loss = not config.has_redundant_collectors
            mitigations.append("Deploy collectors in multiple availability zones")
            mitigations.append("Enable local span buffering during partitions")
            detection_delay = 2.0

        elif scenario == TraceLossScenario.CLOCK_SKEW:
            loss = base_impact
            mitigations.append("Enable NTP synchronization across all services")
            mitigations.append("Use logical clocks for span ordering")
            detection_delay = 30.0

        elif scenario == TraceLossScenario.SPAN_DROP:
            loss = base_impact
            if config.has_tail_sampling:
                loss *= 0.5
            mitigations.append("Monitor span drop rate metrics")
            mitigations.append("Scale collectors to handle peak load")
            detection_delay = 5.0

        elif scenario == TraceLossScenario.CONTEXT_PROPAGATION_FAILURE:
            loss = base_impact
            mitigations.append("Standardize context propagation (W3C TraceContext)")
            mitigations.append("Add propagation validation tests")
            detection_delay = 20.0

        elif scenario == TraceLossScenario.HIGH_CARDINALITY_EXPLOSION:
            loss = base_impact
            mitigations.append("Set cardinality limits on span attributes")
            mitigations.append("Use attribute allow-lists instead of deny-lists")
            detection_delay = 10.0

        elif scenario == TraceLossScenario.CIRCULAR_TRACE:
            loss = base_impact
            mitigations.append("Implement max trace depth limits")
            mitigations.append("Add cycle detection in trace processing")
            detection_delay = 8.0

        loss_percent = _clamp(loss, 0.0, 100.0)
        severity = _clamp(loss / 100.0, 0.0, 1.0)

        # Determine affected services based on scenario type
        affected = component_ids if loss_percent > 50.0 else component_ids[:max(1, len(component_ids) // 2)]

        return TraceLossResult(
            scenario=scenario,
            affected_services=affected,
            estimated_loss_percent=round(loss_percent, 2),
            detection_delay_minutes=round(detection_delay, 2),
            data_loss_possible=data_loss,
            mitigations=mitigations,
            severity=round(severity, 2),
        )

    # -- sampling optimization ---------------------------------------------

    def optimize_sampling(
        self,
        graph: InfraGraph,
        budget_spans_per_sec: int,
    ) -> SamplingRecommendation:
        """Determine the best sampling strategy given a span budget."""
        total_services = max(len(graph.components), 1)
        # Estimate raw spans/s without sampling
        estimated_raw_spans = total_services * 100  # 100 spans/s per service

        if budget_spans_per_sec <= 0:
            return SamplingRecommendation(
                strategy=SamplingStrategy.RATE_LIMITING,
                recommended_rate=0.0,
                estimated_spans_per_second=0,
                estimated_storage_gb_per_day=0.0,
                trade_off_summary="Budget is zero; no traces will be collected",
                within_budget=True,
            )

        if budget_spans_per_sec >= estimated_raw_spans:
            # Budget exceeds raw output: always-on is fine
            daily_gb = (estimated_raw_spans * _DEFAULT_SPAN_SIZE_KB * 86400) / (1024 * 1024)
            return SamplingRecommendation(
                strategy=SamplingStrategy.ALWAYS_ON,
                recommended_rate=1.0,
                estimated_spans_per_second=estimated_raw_spans,
                estimated_storage_gb_per_day=round(daily_gb, 2),
                trade_off_summary="Budget allows full trace collection",
                within_budget=True,
            )

        # Need to reduce volume
        required_rate = budget_spans_per_sec / estimated_raw_spans
        effective_spans = int(estimated_raw_spans * required_rate)
        daily_gb = (effective_spans * _DEFAULT_SPAN_SIZE_KB * 86400) / (1024 * 1024)

        # Choose strategy based on rate
        if required_rate >= 0.5:
            strategy = SamplingStrategy.ADAPTIVE
            summary = "Adaptive sampling recommended; high budget allows good coverage"
        elif required_rate >= 0.1:
            strategy = SamplingStrategy.TAIL_BASED
            summary = "Tail-based sampling recommended; captures errors and slow traces"
        elif required_rate >= 0.01:
            strategy = SamplingStrategy.PROBABILISTIC
            summary = "Probabilistic sampling at reduced rate; some traces will be missed"
        else:
            strategy = SamplingStrategy.RATE_LIMITING
            summary = "Rate limiting required; very constrained budget"

        return SamplingRecommendation(
            strategy=strategy,
            recommended_rate=round(min(required_rate, 1.0), 4),
            estimated_spans_per_second=effective_spans,
            estimated_storage_gb_per_day=round(daily_gb, 2),
            trade_off_summary=summary,
            within_budget=True,
        )

    # -- observability gaps -------------------------------------------------

    def detect_observability_gaps(
        self,
        graph: InfraGraph,
        tracing_config: TracingConfig | None = None,
    ) -> list[ObservabilityGap]:
        """Find components that lack tracing instrumentation."""
        config = tracing_config or TracingConfig()
        instrumented = set(config.instrumented_services)
        gaps: list[ObservabilityGap] = []

        for cid, comp in graph.components.items():
            if cid not in instrumented:
                # Determine risk level based on component type and connectivity
                dependents = graph.get_dependents(cid)
                dependencies = graph.get_dependencies(cid)
                connectivity = len(dependents) + len(dependencies)

                if comp.type in (ComponentType.DATABASE, ComponentType.QUEUE):
                    risk = "high"
                elif connectivity >= 3:
                    risk = "high"
                elif connectivity >= 1:
                    risk = "medium"
                else:
                    risk = "low"

                gaps.append(
                    ObservabilityGap(
                        component_id=cid,
                        component_name=comp.name,
                        component_type=comp.type.value,
                        gap_type="no_instrumentation",
                        risk_level=risk,
                        recommendation=f"Add tracing instrumentation to {comp.name} ({comp.type.value})",
                    )
                )

        return gaps

    # -- storage cost estimation --------------------------------------------

    def estimate_trace_storage_cost(
        self,
        graph: InfraGraph,
        retention_days: int,
        tracing_config: TracingConfig | None = None,
    ) -> StorageCostEstimate:
        """Project trace storage costs for the given retention period."""
        config = tracing_config or TracingConfig()
        daily_gb = self._estimate_daily_storage_gb(graph, config)
        total_gb = daily_gb * retention_days
        daily_cost = daily_gb * _COST_PER_GB_USD
        total_cost = total_gb * _COST_PER_GB_USD

        # Cost per million spans
        total_services = max(len(graph.components), 1)
        effective_rate = config.sampling_rate if config.sampling_strategy != SamplingStrategy.ALWAYS_ON else 1.0
        spans_per_day = total_services * 100 * effective_rate * 86400
        cost_per_million = (daily_cost / (spans_per_day / 1_000_000)) if spans_per_day > 0 else 0.0

        recommendations: list[str] = []
        if daily_gb > 50.0:
            recommendations.append("Consider reducing sampling rate to lower storage costs")
        if retention_days > 30:
            recommendations.append("Use tiered storage for traces older than 7 days")
        if total_cost > 100.0:
            recommendations.append("Evaluate tail-based sampling to reduce volume while keeping important traces")

        return StorageCostEstimate(
            retention_days=retention_days,
            daily_storage_gb=round(daily_gb, 2),
            total_storage_gb=round(total_gb, 2),
            estimated_daily_cost=round(daily_cost, 4),
            estimated_total_cost=round(total_cost, 4),
            cost_per_million_spans=round(cost_per_million, 4),
            recommendations=recommendations,
        )

    # -- collector scaling simulation ---------------------------------------

    def simulate_collector_scaling(
        self,
        graph: InfraGraph,
        spans_per_second: int,
        tracing_config: TracingConfig | None = None,
    ) -> CollectorScalingResult:
        """Determine when collectors need to scale."""
        config = tracing_config or TracingConfig()
        current = config.collectors
        total_capacity = current * _COLLECTOR_CAPACITY_SPANS_PER_SEC

        if total_capacity <= 0:
            utilization = 100.0
        else:
            utilization = (spans_per_second / total_capacity) * 100.0

        headroom = max(0.0, 100.0 - utilization)
        needs_scaling = utilization > 80.0

        recommended = current
        if needs_scaling:
            capacity_per = _COLLECTOR_CAPACITY_SPANS_PER_SEC * 0.7
            if capacity_per > 0:
                recommended = math.ceil(spans_per_second / capacity_per)
            else:
                recommended = current + 1
            recommended = max(recommended, current + 1)

        recommendations: list[str] = []
        if needs_scaling:
            recommendations.append(
                f"Scale collectors from {current} to {recommended}"
            )
            recommendations.append("Enable horizontal pod autoscaling for collectors")
        if current == 1:
            recommendations.append(
                "Add at least one redundant collector for fault tolerance"
            )
        if headroom > 50.0:
            recommendations.append("Current collector capacity has sufficient headroom")

        return CollectorScalingResult(
            current_collectors=current,
            recommended_collectors=recommended,
            spans_per_second=spans_per_second,
            utilization_percent=round(_clamp(utilization), 2),
            headroom_percent=round(_clamp(headroom), 2),
            needs_scaling=needs_scaling,
            recommendations=recommendations,
        )

    # -- trace-resilience correlation ---------------------------------------

    def correlate_trace_with_resilience(
        self,
        graph: InfraGraph,
        trace_data: TracingConfig,
    ) -> TraceResilienceCorrelation:
        """Link trace observability quality to overall system resilience."""
        # Observability score: based on coverage, sampling, and pipeline quality
        component_ids = set(graph.components.keys())
        instrumented = set(trace_data.instrumented_services)
        if component_ids:
            coverage = len(instrumented & component_ids) / len(component_ids)
        else:
            coverage = 0.0

        obs_score = coverage * 50.0  # coverage contributes up to 50
        if trace_data.has_redundant_collectors:
            obs_score += 15.0
        if trace_data.has_tail_sampling:
            obs_score += 10.0
        if trace_data.sampling_strategy == SamplingStrategy.ALWAYS_ON:
            obs_score += 15.0
        elif trace_data.sampling_strategy in (SamplingStrategy.ADAPTIVE, SamplingStrategy.TAIL_BASED):
            obs_score += 10.0
        elif trace_data.sampling_strategy == SamplingStrategy.PROBABILISTIC:
            obs_score += 5.0
        if trace_data.exporters > 1:
            obs_score += 5.0
        if trace_data.collectors > 1:
            obs_score += 5.0

        obs_score = _clamp(obs_score, 0.0, 100.0)

        # System resilience score from graph
        res_score = graph.resilience_score()

        # Correlation strength
        diff = abs(obs_score - res_score)
        if obs_score >= 70.0 and res_score >= 70.0:
            strength = "strong"
        elif obs_score >= 50.0 and res_score >= 50.0:
            strength = "moderate"
        elif diff > 40.0:
            strength = "weak"
        else:
            strength = "none"

        # Blind spots: uninstrumented components
        blind_spots = sorted(component_ids - instrumented)

        recommendations: list[str] = []
        if coverage < 1.0 and component_ids:
            recommendations.append(
                f"Instrument {len(component_ids - instrumented)} remaining services"
            )
        if obs_score < 50.0:
            recommendations.append("Improve tracing pipeline reliability for better observability")
        if res_score < 50.0:
            recommendations.append("Address infrastructure resilience gaps")
        if not trace_data.has_tail_sampling:
            recommendations.append("Enable tail-based sampling to capture error traces")

        return TraceResilienceCorrelation(
            observability_score=round(obs_score, 2),
            resilience_score=round(res_score, 2),
            correlation_strength=strength,
            blind_spots=blind_spots,
            recommendations=recommendations,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # -- internal helpers ---------------------------------------------------

    def _estimate_daily_storage_gb(
        self,
        graph: InfraGraph,
        config: TracingConfig,
    ) -> float:
        """Estimate daily storage in GB."""
        total_services = max(len(graph.components), 1)
        effective_rate = (
            config.sampling_rate
            if config.sampling_strategy != SamplingStrategy.ALWAYS_ON
            else 1.0
        )
        spans_per_sec = total_services * 100 * effective_rate
        daily_bytes = spans_per_sec * _DEFAULT_SPAN_SIZE_KB * 1024 * 86400
        return daily_bytes / (1024 ** 3)
