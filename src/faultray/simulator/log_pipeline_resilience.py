# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Log Pipeline Resilience Analyzer.

Analyzes logging and telemetry pipeline resilience and failure modes.
Covers pipeline stages (collection, aggregation, transport, storage,
indexing, querying), log loss risk assessment, buffer overflow simulation,
ingestion rate vs processing capacity analysis, storage capacity planning,
pipeline redundancy evaluation, cardinality explosion detection, sampling
strategy impact, pipeline latency analysis, cost modeling, compliance
requirements for log retention, component failure impact analysis,
backpressure strategy evaluation, failover analysis (hot/warm/cold standby),
cross-datacenter log replication, cost vs resilience trade-off optimization,
and alert pipeline dependency analysis.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PipelineStage(str, Enum):
    """Stages in a log processing pipeline."""

    COLLECTION = "collection"
    AGGREGATION = "aggregation"
    TRANSPORT = "transport"
    STORAGE = "storage"
    INDEXING = "indexing"
    QUERYING = "querying"


class LogLossScenario(str, Enum):
    """Scenarios causing log data loss."""

    AGENT_BUFFER_OVERFLOW = "agent_buffer_overflow"
    QUEUE_BACKLOG = "queue_backlog"
    TRANSPORT_FAILURE = "transport_failure"
    STORAGE_FULL = "storage_full"
    INDEXER_OVERLOAD = "indexer_overload"
    NETWORK_PARTITION = "network_partition"
    SCHEMA_CHANGE = "schema_change"
    CARDINALITY_EXPLOSION = "cardinality_explosion"
    INGESTION_SPIKE = "ingestion_spike"
    COMPONENT_CRASH = "component_crash"


class SamplingMode(str, Enum):
    """Sampling strategies for log volume reduction."""

    NONE = "none"
    RANDOM = "random"
    RATE_LIMITED = "rate_limited"
    PRIORITY_BASED = "priority_based"
    HASH_BASED = "hash_based"
    TAIL_BASED = "tail_based"


class ComplianceFramework(str, Enum):
    """Regulatory compliance frameworks with log retention requirements."""

    SOC2 = "soc2"
    PCI_DSS = "pci_dss"
    HIPAA = "hipaa"
    GDPR = "gdpr"
    SOX = "sox"
    NONE = "none"


class LogLevel(str, Enum):
    """Standard log severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class BackpressureStrategy(str, Enum):
    """Backpressure handling strategy when pipeline is overwhelmed."""

    DROP = "drop"
    BLOCK = "block"
    SAMPLE = "sample"
    SPILL_TO_DISK = "spill_to_disk"
    NONE = "none"


class FailoverMode(str, Enum):
    """Standby mode for log pipeline failover."""

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    NONE = "none"


class ReplicationMode(str, Enum):
    """Cross-datacenter replication mode."""

    SYNC = "sync"
    ASYNC = "async"
    SEMI_SYNC = "semi_sync"
    NONE = "none"


class AlertSeverity(str, Enum):
    """Alert severity classification."""

    PAGE = "page"
    WARN = "warn"
    INFO = "info"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class LogPipelineConfig(BaseModel):
    """Configuration describing the log pipeline infrastructure."""

    agent_buffer_mb: float = Field(default=64.0, ge=0.0)
    queue_capacity_mb: float = Field(default=1024.0, ge=0.0)
    queue_replicas: int = Field(default=1, ge=1)
    ingestion_rate_mb_per_sec: float = Field(default=10.0, ge=0.0)
    processing_rate_mb_per_sec: float = Field(default=15.0, ge=0.0)
    storage_capacity_gb: float = Field(default=500.0, ge=0.0)
    storage_replicas: int = Field(default=1, ge=1)
    retention_days: int = Field(default=30, ge=1)
    indexer_replicas: int = Field(default=1, ge=1)
    indexer_throughput_mb_per_sec: float = Field(default=12.0, ge=0.0)
    has_dead_letter_queue: bool = False
    has_backpressure: bool = False
    sampling_mode: SamplingMode = SamplingMode.NONE
    sampling_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    compliance_framework: ComplianceFramework = ComplianceFramework.NONE
    pipeline_stages: list[str] = Field(default_factory=lambda: [s.value for s in PipelineStage])
    high_cardinality_fields: list[str] = Field(default_factory=list)
    log_sources: list[str] = Field(default_factory=list)
    backpressure_strategy: BackpressureStrategy = BackpressureStrategy.NONE
    spill_disk_capacity_mb: float = Field(default=0.0, ge=0.0)
    failover_mode: FailoverMode = FailoverMode.NONE
    failover_switch_time_seconds: float = Field(default=0.0, ge=0.0)
    standby_replicas: int = Field(default=0, ge=0)
    replication_mode: ReplicationMode = ReplicationMode.NONE
    replication_lag_ms: float = Field(default=0.0, ge=0.0)
    remote_dc_count: int = Field(default=0, ge=0)
    alert_destinations: list[str] = Field(default_factory=list)
    alert_depends_on_log_pipeline: bool = True


class StageLossRisk(BaseModel):
    """Risk assessment for a single pipeline stage."""

    stage: str
    risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    risk_level: str = "low"
    loss_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    bottleneck: bool = False
    recommendations: list[str] = Field(default_factory=list)


class BufferOverflowResult(BaseModel):
    """Result of buffer overflow simulation."""

    agent_buffer_fill_seconds: float = 0.0
    queue_fill_seconds: float = 0.0
    overflow_risk: str = "low"
    estimated_loss_mb_per_hour: float = 0.0
    can_sustain_spike: bool = True
    spike_tolerance_multiplier: float = 1.0
    recommendations: list[str] = Field(default_factory=list)


class IngestionCapacityResult(BaseModel):
    """Ingestion rate vs processing capacity analysis result."""

    ingestion_rate_mb_per_sec: float = 0.0
    processing_rate_mb_per_sec: float = 0.0
    indexing_rate_mb_per_sec: float = 0.0
    ingestion_utilization_percent: float = 0.0
    indexing_utilization_percent: float = 0.0
    headroom_percent: float = 0.0
    can_handle_current_load: bool = True
    max_sustainable_rate_mb_per_sec: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class StorageCapacityPlan(BaseModel):
    """Storage capacity planning result."""

    daily_volume_gb: float = 0.0
    retention_days: int = 30
    required_capacity_gb: float = 0.0
    current_capacity_gb: float = 0.0
    utilization_percent: float = 0.0
    days_until_full: float = 0.0
    meets_retention: bool = True
    compliance_retention_days: int = 0
    meets_compliance: bool = True
    cost_per_day: float = 0.0
    cost_per_month: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class RedundancyAssessment(BaseModel):
    """Pipeline redundancy evaluation result."""

    overall_redundancy_score: float = Field(default=0.0, ge=0.0, le=100.0)
    single_points_of_failure: list[str] = Field(default_factory=list)
    redundant_stages: list[str] = Field(default_factory=list)
    non_redundant_stages: list[str] = Field(default_factory=list)
    failover_capability: bool = False
    recommendations: list[str] = Field(default_factory=list)


class CardinalityReport(BaseModel):
    """Cardinality explosion detection report."""

    total_fields_analyzed: int = 0
    high_cardinality_fields: list[str] = Field(default_factory=list)
    estimated_index_bloat_percent: float = 0.0
    storage_impact_multiplier: float = 1.0
    query_performance_impact: str = "none"
    risk_level: str = "low"
    recommendations: list[str] = Field(default_factory=list)


class SamplingImpact(BaseModel):
    """Impact assessment of log sampling on observability."""

    mode: str = "none"
    effective_rate: float = 1.0
    volume_reduction_percent: float = 0.0
    storage_savings_gb_per_day: float = 0.0
    cost_savings_per_month: float = 0.0
    observability_impact: str = "none"
    error_detection_risk: str = "low"
    recommendations: list[str] = Field(default_factory=list)


class PipelineLatencyResult(BaseModel):
    """Pipeline latency analysis result."""

    total_latency_ms: float = 0.0
    stage_latencies: dict[str, float] = Field(default_factory=dict)
    p50_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    bottleneck_stage: str = ""
    meets_slo: bool = True
    recommendations: list[str] = Field(default_factory=list)


class CostModelResult(BaseModel):
    """Cost model for log volume tiers."""

    daily_volume_gb: float = 0.0
    monthly_volume_gb: float = 0.0
    tier: str = "standard"
    ingestion_cost_per_gb: float = 0.0
    storage_cost_per_gb: float = 0.0
    total_daily_cost: float = 0.0
    total_monthly_cost: float = 0.0
    annual_projected_cost: float = 0.0
    cost_optimization_potential_percent: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class ComponentFailureImpact(BaseModel):
    """Impact of a pipeline component failure."""

    failed_component: str
    affected_stages: list[str] = Field(default_factory=list)
    log_loss_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    recovery_time_minutes: float = 0.0
    data_at_risk_gb: float = 0.0
    has_failover: bool = False
    cascading_failures: list[str] = Field(default_factory=list)
    severity: str = "medium"
    recommendations: list[str] = Field(default_factory=list)


class BackpressureAssessment(BaseModel):
    """Assessment of backpressure strategy effectiveness."""

    strategy: str = "none"
    effectiveness_score: float = Field(default=0.0, ge=0.0, le=100.0)
    data_loss_risk: str = "unknown"
    producer_impact: str = "none"
    throughput_preservation_percent: float = Field(default=100.0, ge=0.0, le=100.0)
    disk_spill_capacity_minutes: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class FailoverAssessment(BaseModel):
    """Log pipeline failover analysis result."""

    mode: str = "none"
    switch_time_seconds: float = 0.0
    data_loss_during_switch_mb: float = 0.0
    standby_readiness_score: float = Field(default=0.0, ge=0.0, le=100.0)
    rpo_seconds: float = 0.0
    rto_seconds: float = 0.0
    standby_sync_lag_ms: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class ReplicationAssessment(BaseModel):
    """Cross-datacenter log replication analysis."""

    mode: str = "none"
    dc_count: int = 0
    replication_lag_ms: float = 0.0
    data_durability_score: float = Field(default=0.0, ge=0.0, le=100.0)
    cross_dc_loss_risk: str = "high"
    bandwidth_overhead_percent: float = 0.0
    consistency_model: str = "none"
    recommendations: list[str] = Field(default_factory=list)


class CostResilienceTradeoff(BaseModel):
    """Cost vs resilience optimization result."""

    current_monthly_cost: float = 0.0
    current_resilience_score: float = 0.0
    optimized_monthly_cost: float = 0.0
    optimized_resilience_score: float = 0.0
    cost_per_resilience_point: float = 0.0
    optimization_actions: list[str] = Field(default_factory=list)
    trade_off_rating: str = "balanced"
    recommendations: list[str] = Field(default_factory=list)


class AlertPipelineDependency(BaseModel):
    """Alert pipeline dependency analysis result."""

    alert_destinations: list[str] = Field(default_factory=list)
    depends_on_log_pipeline: bool = True
    independent_alert_paths: int = 0
    alert_loss_risk_during_outage: str = "high"
    can_alert_during_log_failure: bool = False
    fallback_mechanisms: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class LogPipelineAssessment(BaseModel):
    """Full log pipeline resilience assessment."""

    timestamp: str = ""
    overall_resilience_score: float = Field(default=0.0, ge=0.0, le=100.0)
    stage_risks: list[StageLossRisk] = Field(default_factory=list)
    single_points_of_failure: list[str] = Field(default_factory=list)
    total_estimated_loss_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    bottlenecks: list[str] = Field(default_factory=list)
    compliance_met: bool = True
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Base loss risk per stage (percent, 0-100)
_STAGE_BASE_RISK: dict[PipelineStage, float] = {
    PipelineStage.COLLECTION: 15.0,
    PipelineStage.AGGREGATION: 10.0,
    PipelineStage.TRANSPORT: 20.0,
    PipelineStage.STORAGE: 25.0,
    PipelineStage.INDEXING: 18.0,
    PipelineStage.QUERYING: 5.0,
}

# Scenario base impact (percent, 0-100)
_SCENARIO_IMPACT: dict[LogLossScenario, float] = {
    LogLossScenario.AGENT_BUFFER_OVERFLOW: 55.0,
    LogLossScenario.QUEUE_BACKLOG: 45.0,
    LogLossScenario.TRANSPORT_FAILURE: 70.0,
    LogLossScenario.STORAGE_FULL: 90.0,
    LogLossScenario.INDEXER_OVERLOAD: 40.0,
    LogLossScenario.NETWORK_PARTITION: 75.0,
    LogLossScenario.SCHEMA_CHANGE: 30.0,
    LogLossScenario.CARDINALITY_EXPLOSION: 50.0,
    LogLossScenario.INGESTION_SPIKE: 60.0,
    LogLossScenario.COMPONENT_CRASH: 80.0,
}

# Stage latency defaults (ms)
_STAGE_LATENCY_MS: dict[PipelineStage, float] = {
    PipelineStage.COLLECTION: 5.0,
    PipelineStage.AGGREGATION: 20.0,
    PipelineStage.TRANSPORT: 50.0,
    PipelineStage.STORAGE: 30.0,
    PipelineStage.INDEXING: 100.0,
    PipelineStage.QUERYING: 200.0,
}

# Cost per GB (USD) by volume tier
_COST_TIERS: dict[str, dict[str, float]] = {
    "free": {"max_gb_day": 1.0, "ingestion": 0.0, "storage": 0.0},
    "standard": {"max_gb_day": 100.0, "ingestion": 0.50, "storage": 0.03},
    "professional": {"max_gb_day": 1000.0, "ingestion": 0.35, "storage": 0.025},
    "enterprise": {"max_gb_day": float("inf"), "ingestion": 0.20, "storage": 0.015},
}

# Compliance minimum retention days
_COMPLIANCE_RETENTION_DAYS: dict[ComplianceFramework, int] = {
    ComplianceFramework.SOC2: 365,
    ComplianceFramework.PCI_DSS: 365,
    ComplianceFramework.HIPAA: 2190,  # 6 years
    ComplianceFramework.GDPR: 90,
    ComplianceFramework.SOX: 2555,  # 7 years
    ComplianceFramework.NONE: 0,
}

# Component recovery time in minutes
_COMPONENT_RECOVERY_MINUTES: dict[str, float] = {
    "agent": 2.0,
    "queue": 10.0,
    "transport": 5.0,
    "storage": 30.0,
    "indexer": 15.0,
    "query_engine": 5.0,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp a value between lo and hi."""
    return max(lo, min(hi, value))


def _risk_level(score: float) -> str:
    """Convert a 0-100 risk score to a textual level."""
    if score >= 80.0:
        return "critical"
    if score >= 60.0:
        return "high"
    if score >= 40.0:
        return "medium"
    if score >= 20.0:
        return "low"
    return "minimal"


def _determine_tier(daily_gb: float) -> str:
    """Determine cost tier from daily volume."""
    for tier_name in ("free", "standard", "professional", "enterprise"):
        if daily_gb <= _COST_TIERS[tier_name]["max_gb_day"]:
            return tier_name
    return "enterprise"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class LogPipelineResilienceEngine:
    """Stateless engine for log pipeline resilience analysis."""

    # -- stage risk assessment -----------------------------------------------

    def assess_stage_risks(
        self,
        graph: InfraGraph,
        config: LogPipelineConfig,
    ) -> list[StageLossRisk]:
        """Assess log loss risk at each pipeline stage."""
        results: list[StageLossRisk] = []
        active_stages = config.pipeline_stages or [s.value for s in PipelineStage]

        for stage_val in active_stages:
            try:
                stage = PipelineStage(stage_val)
            except ValueError:
                continue

            base_risk = _STAGE_BASE_RISK.get(stage, 10.0)
            risk = base_risk
            recs: list[str] = []
            is_bottleneck = False

            if stage == PipelineStage.COLLECTION:
                if config.agent_buffer_mb < 32.0:
                    risk += 15.0
                    recs.append("Increase agent buffer size to at least 32 MB")
                if not config.log_sources:
                    risk += 10.0
                    recs.append("Configure explicit log sources for collection")
                if config.has_backpressure:
                    risk -= 5.0

            elif stage == PipelineStage.AGGREGATION:
                if config.queue_replicas < 2:
                    risk += 10.0
                    recs.append("Add queue replicas for aggregation redundancy")
                if config.ingestion_rate_mb_per_sec > config.processing_rate_mb_per_sec:
                    risk += 15.0
                    is_bottleneck = True
                    recs.append("Ingestion exceeds processing capacity; scale aggregation tier")

            elif stage == PipelineStage.TRANSPORT:
                if config.queue_replicas < 2:
                    risk += 12.0
                    recs.append("Use replicated queues for transport redundancy")
                if not config.has_dead_letter_queue:
                    risk += 8.0
                    recs.append("Add dead letter queue for failed message handling")

            elif stage == PipelineStage.STORAGE:
                daily_gb = self._daily_volume_gb(graph, config)
                required = daily_gb * config.retention_days
                if config.storage_capacity_gb > 0 and required > config.storage_capacity_gb:
                    risk += 20.0
                    is_bottleneck = True
                    recs.append("Storage insufficient for retention; increase capacity or reduce retention")
                if config.storage_replicas < 2:
                    risk += 10.0
                    recs.append("Add storage replicas for data durability")

            elif stage == PipelineStage.INDEXING:
                if config.indexer_replicas < 2:
                    risk += 10.0
                    recs.append("Scale indexer for redundancy")
                if config.ingestion_rate_mb_per_sec > config.indexer_throughput_mb_per_sec:
                    risk += 18.0
                    is_bottleneck = True
                    recs.append("Indexer throughput below ingestion rate; scale indexing tier")
                if config.high_cardinality_fields:
                    risk += len(config.high_cardinality_fields) * 5.0
                    recs.append("High cardinality fields increase indexing load")

            elif stage == PipelineStage.QUERYING:
                if config.storage_replicas < 2:
                    risk += 5.0
                    recs.append("Add read replicas to improve query performance")

            risk = _clamp(risk)
            loss_pct = _clamp(risk * 0.4)
            level = _risk_level(risk)

            results.append(
                StageLossRisk(
                    stage=stage.value,
                    risk_score=round(risk, 2),
                    risk_level=level,
                    loss_percent=round(loss_pct, 2),
                    bottleneck=is_bottleneck,
                    recommendations=recs,
                )
            )

        return results

    # -- buffer overflow simulation ------------------------------------------

    def simulate_buffer_overflow(
        self,
        config: LogPipelineConfig,
        spike_multiplier: float = 2.0,
    ) -> BufferOverflowResult:
        """Simulate buffer overflow under normal and spike conditions."""
        ingestion = config.ingestion_rate_mb_per_sec
        processing = config.processing_rate_mb_per_sec

        # Agent buffer fill time (at spike rate minus drain)
        spike_rate = ingestion * spike_multiplier
        excess_rate = max(0.0, spike_rate - processing)

        if excess_rate > 0 and config.agent_buffer_mb > 0:
            agent_fill_s = config.agent_buffer_mb / excess_rate
        else:
            agent_fill_s = float("inf")

        # Queue fill time
        if excess_rate > 0 and config.queue_capacity_mb > 0:
            queue_fill_s = config.queue_capacity_mb / excess_rate
        else:
            queue_fill_s = float("inf")

        # Determine how much we lose per hour if overflow happens
        if excess_rate > 0:
            loss_mb_per_hour = excess_rate * 3600.0
        else:
            loss_mb_per_hour = 0.0

        # Max spike we can sustain without overflow
        if processing > 0 and ingestion > 0:
            tolerance = processing / ingestion
        else:
            tolerance = 1.0

        can_sustain = spike_rate <= processing
        recs: list[str] = []

        if not can_sustain:
            if config.agent_buffer_mb < 128:
                recs.append("Increase agent buffer to at least 128 MB for spike absorption")
            if not config.has_backpressure:
                recs.append("Enable backpressure to slow producers during overload")
            if config.queue_replicas < 2:
                recs.append("Add queue replicas to increase aggregate capacity")
            recs.append(
                f"Scale processing to at least {spike_rate:.1f} MB/s to handle {spike_multiplier}x spikes"
            )

        if can_sustain:
            overflow_risk = "low"
        elif agent_fill_s > 300:
            overflow_risk = "medium"
        else:
            overflow_risk = "high"

        return BufferOverflowResult(
            agent_buffer_fill_seconds=round(agent_fill_s, 2) if math.isfinite(agent_fill_s) else -1.0,
            queue_fill_seconds=round(queue_fill_s, 2) if math.isfinite(queue_fill_s) else -1.0,
            overflow_risk=overflow_risk,
            estimated_loss_mb_per_hour=round(loss_mb_per_hour, 2),
            can_sustain_spike=can_sustain,
            spike_tolerance_multiplier=round(tolerance, 2),
            recommendations=recs,
        )

    # -- ingestion capacity analysis -----------------------------------------

    def analyze_ingestion_capacity(
        self,
        graph: InfraGraph,
        config: LogPipelineConfig,
    ) -> IngestionCapacityResult:
        """Analyze ingestion rate vs processing and indexing capacity."""
        ingestion = config.ingestion_rate_mb_per_sec
        processing = config.processing_rate_mb_per_sec
        indexing = config.indexer_throughput_mb_per_sec * config.indexer_replicas

        bottleneck_rate = min(processing, indexing)

        if processing > 0:
            ingestion_util = (ingestion / processing) * 100.0
        else:
            ingestion_util = 100.0

        if indexing > 0:
            indexing_util = (ingestion / indexing) * 100.0
        else:
            indexing_util = 100.0

        headroom = max(0.0, 100.0 - max(ingestion_util, indexing_util))
        can_handle = ingestion <= bottleneck_rate

        recs: list[str] = []
        if not can_handle:
            recs.append("Ingestion rate exceeds processing/indexing capacity; scale pipeline")
        if ingestion_util > 80.0:
            recs.append("Processing capacity nearing limits; consider scaling")
        if indexing_util > 80.0:
            recs.append("Indexing capacity nearing limits; add indexer replicas")
        if headroom < 20.0 and can_handle:
            recs.append("Low headroom; consider proactive scaling before load increases")

        return IngestionCapacityResult(
            ingestion_rate_mb_per_sec=round(ingestion, 2),
            processing_rate_mb_per_sec=round(processing, 2),
            indexing_rate_mb_per_sec=round(indexing, 2),
            ingestion_utilization_percent=round(_clamp(ingestion_util), 2),
            indexing_utilization_percent=round(_clamp(indexing_util), 2),
            headroom_percent=round(_clamp(headroom), 2),
            can_handle_current_load=can_handle,
            max_sustainable_rate_mb_per_sec=round(bottleneck_rate, 2),
            recommendations=recs,
        )

    # -- storage capacity planning -------------------------------------------

    def plan_storage_capacity(
        self,
        graph: InfraGraph,
        config: LogPipelineConfig,
    ) -> StorageCapacityPlan:
        """Plan storage capacity based on volume, retention, and compliance."""
        daily_gb = self._daily_volume_gb(graph, config)
        required_gb = daily_gb * config.retention_days
        current_gb = config.storage_capacity_gb * config.storage_replicas

        if current_gb > 0:
            util = (required_gb / current_gb) * 100.0
        else:
            util = 100.0

        meets_retention = required_gb <= current_gb

        # Days until storage full (at current daily rate)
        if daily_gb > 0 and current_gb > 0:
            days_until_full = current_gb / daily_gb
        else:
            days_until_full = float("inf")
        if math.isinf(days_until_full):
            days_until_full = -1.0

        # Compliance check
        comp_days = _COMPLIANCE_RETENTION_DAYS.get(config.compliance_framework, 0)
        meets_compliance = config.retention_days >= comp_days

        # Cost estimation (using standard tier rates as baseline)
        cost_per_gb = _COST_TIERS["standard"]["storage"]
        cost_per_day = daily_gb * cost_per_gb
        cost_per_month = cost_per_day * 30.0

        recs: list[str] = []
        if not meets_retention:
            recs.append(
                f"Need {required_gb:.1f} GB for {config.retention_days}-day retention "
                f"but only {current_gb:.1f} GB available"
            )
        if not meets_compliance and comp_days > 0:
            recs.append(
                f"Compliance framework {config.compliance_framework.value} requires "
                f"{comp_days} days retention; currently configured for {config.retention_days} days"
            )
        if util > 80.0 and meets_retention:
            recs.append("Storage utilization above 80%; consider proactive expansion")
        if days_until_full > 0 and days_until_full < 30:
            recs.append(f"Storage projected full in {days_until_full:.0f} days; expand urgently")

        return StorageCapacityPlan(
            daily_volume_gb=round(daily_gb, 2),
            retention_days=config.retention_days,
            required_capacity_gb=round(required_gb, 2),
            current_capacity_gb=round(current_gb, 2),
            utilization_percent=round(_clamp(util), 2),
            days_until_full=round(days_until_full, 2),
            meets_retention=meets_retention,
            compliance_retention_days=comp_days,
            meets_compliance=meets_compliance,
            cost_per_day=round(cost_per_day, 4),
            cost_per_month=round(cost_per_month, 2),
            recommendations=recs,
        )

    # -- redundancy evaluation -----------------------------------------------

    def evaluate_redundancy(
        self,
        config: LogPipelineConfig,
    ) -> RedundancyAssessment:
        """Evaluate pipeline component redundancy."""
        spofs: list[str] = []
        redundant: list[str] = []
        non_redundant: list[str] = []
        recs: list[str] = []
        score = 0.0

        # Queue
        if config.queue_replicas >= 2:
            redundant.append("queue")
            score += 25.0
        else:
            non_redundant.append("queue")
            spofs.append("queue")
            recs.append("Add queue replicas to eliminate single point of failure")

        # Storage
        if config.storage_replicas >= 2:
            redundant.append("storage")
            score += 25.0
        else:
            non_redundant.append("storage")
            spofs.append("storage")
            recs.append("Add storage replicas for data durability")

        # Indexer
        if config.indexer_replicas >= 2:
            redundant.append("indexer")
            score += 25.0
        else:
            non_redundant.append("indexer")
            spofs.append("indexer")
            recs.append("Scale indexer replicas for redundancy")

        # DLQ
        if config.has_dead_letter_queue:
            score += 15.0
        else:
            recs.append("Add dead letter queue for message recovery")

        # Backpressure
        if config.has_backpressure:
            score += 10.0
        else:
            recs.append("Enable backpressure to prevent cascade overload")

        failover = len(redundant) >= 2 and config.has_dead_letter_queue

        return RedundancyAssessment(
            overall_redundancy_score=round(_clamp(score), 2),
            single_points_of_failure=spofs,
            redundant_stages=redundant,
            non_redundant_stages=non_redundant,
            failover_capability=failover,
            recommendations=recs,
        )

    # -- cardinality explosion detection -------------------------------------

    def detect_cardinality_explosion(
        self,
        config: LogPipelineConfig,
        unique_values_per_field: dict[str, int] | None = None,
    ) -> CardinalityReport:
        """Detect high-cardinality labels/fields that inflate index size."""
        field_values = unique_values_per_field or {}
        hc_fields = list(config.high_cardinality_fields)

        # Detect from provided unique values
        for fname, count in field_values.items():
            if count > 1000 and fname not in hc_fields:
                hc_fields.append(fname)

        total_analyzed = len(field_values) + len(config.high_cardinality_fields)
        if total_analyzed == 0:
            total_analyzed = len(hc_fields) if hc_fields else 0

        # Estimate index bloat
        if hc_fields:
            bloat = min(100.0, len(hc_fields) * 15.0)
            storage_mult = 1.0 + (len(hc_fields) * 0.2)
        else:
            bloat = 0.0
            storage_mult = 1.0

        # Query performance impact
        if len(hc_fields) >= 5:
            query_impact = "severe"
        elif len(hc_fields) >= 3:
            query_impact = "significant"
        elif len(hc_fields) >= 1:
            query_impact = "moderate"
        else:
            query_impact = "none"

        risk = _risk_level(bloat)
        recs: list[str] = []
        if hc_fields:
            recs.append(f"Consider removing or aggregating high-cardinality fields: {', '.join(hc_fields)}")
            recs.append("Use field value hashing or bucketing to reduce cardinality")
        if bloat > 50.0:
            recs.append("Index bloat is excessive; audit field schemas immediately")

        return CardinalityReport(
            total_fields_analyzed=max(total_analyzed, len(hc_fields)),
            high_cardinality_fields=hc_fields,
            estimated_index_bloat_percent=round(bloat, 2),
            storage_impact_multiplier=round(storage_mult, 2),
            query_performance_impact=query_impact,
            risk_level=risk,
            recommendations=recs,
        )

    # -- sampling impact assessment ------------------------------------------

    def assess_sampling_impact(
        self,
        graph: InfraGraph,
        config: LogPipelineConfig,
    ) -> SamplingImpact:
        """Assess how sampling strategy affects observability and cost."""
        daily_gb = self._daily_volume_gb(graph, config)

        if config.sampling_mode == SamplingMode.NONE:
            effective_rate = 1.0
        else:
            effective_rate = config.sampling_rate

        volume_reduction = (1.0 - effective_rate) * 100.0
        savings_gb = daily_gb * (1.0 - effective_rate)
        cost_savings_month = savings_gb * _COST_TIERS["standard"]["storage"] * 30.0

        # Observability impact assessment
        if effective_rate >= 0.9:
            obs_impact = "minimal"
            error_risk = "low"
        elif effective_rate >= 0.5:
            obs_impact = "moderate"
            error_risk = "medium"
        elif effective_rate >= 0.1:
            obs_impact = "significant"
            error_risk = "high"
        else:
            obs_impact = "severe"
            error_risk = "critical"

        recs: list[str] = []
        if config.sampling_mode == SamplingMode.RANDOM and effective_rate < 0.5:
            recs.append("Random sampling at low rates may miss important errors; use priority-based sampling")
        if config.sampling_mode == SamplingMode.NONE and daily_gb > 100.0:
            recs.append("Consider enabling sampling to reduce high log volume and costs")
        if effective_rate < 0.1:
            recs.append("Sampling rate below 10% significantly impacts error detection")
        if config.sampling_mode in (SamplingMode.PRIORITY_BASED, SamplingMode.TAIL_BASED):
            recs.append("Priority/tail-based sampling preserves error visibility while reducing volume")

        return SamplingImpact(
            mode=config.sampling_mode.value,
            effective_rate=round(effective_rate, 4),
            volume_reduction_percent=round(_clamp(volume_reduction), 2),
            storage_savings_gb_per_day=round(savings_gb, 4),
            cost_savings_per_month=round(cost_savings_month, 2),
            observability_impact=obs_impact,
            error_detection_risk=error_risk,
            recommendations=recs,
        )

    # -- pipeline latency analysis -------------------------------------------

    def analyze_pipeline_latency(
        self,
        config: LogPipelineConfig,
        stage_overrides: dict[str, float] | None = None,
    ) -> PipelineLatencyResult:
        """Analyze end-to-end pipeline latency (event to queryable)."""
        overrides = stage_overrides or {}
        stage_latencies: dict[str, float] = {}
        active_stages = config.pipeline_stages or [s.value for s in PipelineStage]

        for stage_val in active_stages:
            try:
                stage = PipelineStage(stage_val)
            except ValueError:
                continue
            lat = overrides.get(stage_val, _STAGE_LATENCY_MS.get(stage, 10.0))
            stage_latencies[stage_val] = round(lat, 2)

        total = sum(stage_latencies.values())

        # Approximate p50 / p99
        p50 = total * 0.8
        p99 = total * 2.5

        # Find bottleneck
        bottleneck = max(stage_latencies, key=stage_latencies.get) if stage_latencies else ""

        # SLO: queryable within 5 minutes (300_000 ms)
        meets_slo = total < 300_000.0

        recs: list[str] = []
        if total > 60_000.0:
            recs.append("Pipeline latency exceeds 60s; optimize slowest stages")
        if bottleneck and stage_latencies.get(bottleneck, 0) > total * 0.5:
            recs.append(f"Stage '{bottleneck}' dominates pipeline latency; focus optimization there")
        if not meets_slo:
            recs.append("Pipeline latency exceeds 5-minute SLO; requires architectural review")

        return PipelineLatencyResult(
            total_latency_ms=round(total, 2),
            stage_latencies=stage_latencies,
            p50_latency_ms=round(p50, 2),
            p99_latency_ms=round(p99, 2),
            bottleneck_stage=bottleneck,
            meets_slo=meets_slo,
            recommendations=recs,
        )

    # -- cost modeling -------------------------------------------------------

    def model_cost(
        self,
        graph: InfraGraph,
        config: LogPipelineConfig,
    ) -> CostModelResult:
        """Model cost per log volume tier."""
        daily_gb = self._daily_volume_gb(graph, config)
        monthly_gb = daily_gb * 30.0
        tier = _determine_tier(daily_gb)

        tier_info = _COST_TIERS[tier]
        ingestion_cost = tier_info["ingestion"]
        storage_cost = tier_info["storage"]

        daily_cost = daily_gb * (ingestion_cost + storage_cost)
        monthly_cost = daily_cost * 30.0
        annual_cost = monthly_cost * 12.0

        # Optimization potential
        optimization = 0.0
        recs: list[str] = []

        if config.sampling_mode == SamplingMode.NONE and daily_gb > 10.0:
            optimization += 30.0
            recs.append("Enable sampling to reduce volume by up to 30%")
        if config.high_cardinality_fields:
            optimization += min(20.0, len(config.high_cardinality_fields) * 5.0)
            recs.append("Reduce high-cardinality fields to decrease index costs")
        if config.retention_days > 90 and config.compliance_framework == ComplianceFramework.NONE:
            optimization += 15.0
            recs.append("Consider reducing retention period; no compliance requirement detected")
        if tier in ("standard", "professional") and daily_gb > _COST_TIERS[tier]["max_gb_day"] * 0.8:
            recs.append(f"Close to {tier} tier limit; next tier offers better per-GB rates")

        return CostModelResult(
            daily_volume_gb=round(daily_gb, 2),
            monthly_volume_gb=round(monthly_gb, 2),
            tier=tier,
            ingestion_cost_per_gb=round(ingestion_cost, 4),
            storage_cost_per_gb=round(storage_cost, 4),
            total_daily_cost=round(daily_cost, 4),
            total_monthly_cost=round(monthly_cost, 2),
            annual_projected_cost=round(annual_cost, 2),
            cost_optimization_potential_percent=round(_clamp(optimization), 2),
            recommendations=recs,
        )

    # -- component failure impact --------------------------------------------

    def analyze_component_failure(
        self,
        component: str,
        config: LogPipelineConfig,
    ) -> ComponentFailureImpact:
        """Analyze what happens when a pipeline component fails."""
        recovery = _COMPONENT_RECOVERY_MINUTES.get(component, 10.0)
        self._daily_volume_gb_raw(config)
        recs: list[str] = []
        cascading: list[str] = []

        # Determine affected stages
        _component_stage_map: dict[str, list[str]] = {
            "agent": [PipelineStage.COLLECTION.value],
            "queue": [PipelineStage.AGGREGATION.value, PipelineStage.TRANSPORT.value],
            "transport": [PipelineStage.TRANSPORT.value],
            "storage": [PipelineStage.STORAGE.value, PipelineStage.QUERYING.value],
            "indexer": [PipelineStage.INDEXING.value, PipelineStage.QUERYING.value],
            "query_engine": [PipelineStage.QUERYING.value],
        }

        affected = _component_stage_map.get(component, [component])

        # Base loss
        base_loss = len(affected) * 20.0
        has_failover = False

        if component == "queue":
            if config.queue_replicas >= 2:
                base_loss *= 0.2
                has_failover = True
            else:
                cascading.append("transport")
                cascading.append("aggregation")
                recs.append("Add queue replicas for failover")

        elif component == "storage":
            if config.storage_replicas >= 2:
                base_loss *= 0.2
                has_failover = True
            else:
                cascading.append("indexer")
                cascading.append("query_engine")
                recs.append("Add storage replicas for data durability and failover")

        elif component == "indexer":
            if config.indexer_replicas >= 2:
                base_loss *= 0.3
                has_failover = True
            else:
                cascading.append("query_engine")
                recs.append("Scale indexer replicas for redundancy")

        elif component == "agent":
            recs.append("Deploy agents with auto-restart capability")

        elif component == "transport":
            if config.has_dead_letter_queue:
                base_loss *= 0.5
            else:
                recs.append("Add dead letter queue for message recovery during transport failures")
            cascading.append("storage")

        # Data at risk (GB during recovery window)
        rate_gb_per_min = (config.ingestion_rate_mb_per_sec * 60.0) / 1024.0
        data_at_risk = rate_gb_per_min * recovery

        loss_pct = _clamp(base_loss)
        if loss_pct >= 60.0:
            severity = "critical"
        elif loss_pct >= 30.0:
            severity = "high"
        elif loss_pct >= 10.0:
            severity = "medium"
        else:
            severity = "low"

        return ComponentFailureImpact(
            failed_component=component,
            affected_stages=affected,
            log_loss_percent=round(loss_pct, 2),
            recovery_time_minutes=round(recovery, 2),
            data_at_risk_gb=round(data_at_risk, 4),
            has_failover=has_failover,
            cascading_failures=cascading,
            severity=severity,
            recommendations=recs,
        )

    # -- backpressure strategy evaluation --------------------------------------

    def evaluate_backpressure(
        self,
        config: LogPipelineConfig,
        spike_multiplier: float = 2.0,
    ) -> BackpressureAssessment:
        """Evaluate the effectiveness of the configured backpressure strategy."""
        strategy = config.backpressure_strategy
        recs: list[str] = []

        if strategy == BackpressureStrategy.NONE:
            return BackpressureAssessment(
                strategy=strategy.value,
                effectiveness_score=0.0,
                data_loss_risk="critical",
                producer_impact="none",
                throughput_preservation_percent=100.0,
                disk_spill_capacity_minutes=0.0,
                recommendations=[
                    "No backpressure strategy configured; log loss is certain during spikes",
                    "Consider enabling drop, block, sample, or spill-to-disk strategy",
                ],
            )

        spike_rate = config.ingestion_rate_mb_per_sec * spike_multiplier
        excess = max(0.0, spike_rate - config.processing_rate_mb_per_sec)

        if strategy == BackpressureStrategy.DROP:
            # Drops excess logs - preserves pipeline health but loses data
            effectiveness = 60.0
            loss_risk = "high"
            producer_impact = "none"
            if excess > 0 and spike_rate > 0:
                throughput = (config.processing_rate_mb_per_sec / spike_rate) * 100.0
            else:
                throughput = 100.0
            recs.append("Drop strategy will discard logs during spikes; consider priority-based dropping")
            if config.sampling_mode == SamplingMode.NONE:
                recs.append("Pair drop strategy with priority-based sampling to preserve critical logs")

        elif strategy == BackpressureStrategy.BLOCK:
            # Blocks producers - preserves all data but can stall services
            effectiveness = 75.0
            loss_risk = "low"
            producer_impact = "high"
            throughput = 100.0
            recs.append("Block strategy preserves data but may stall application services")
            recs.append("Ensure producer timeout handling prevents application-level failures")

        elif strategy == BackpressureStrategy.SAMPLE:
            # Dynamically sample during overload
            effectiveness = 70.0
            loss_risk = "medium"
            producer_impact = "low"
            if excess > 0 and spike_rate > 0:
                throughput = (config.processing_rate_mb_per_sec / spike_rate) * 100.0 + 10.0
            else:
                throughput = 100.0
            recs.append("Sample strategy trades completeness for pipeline health during spikes")
            if config.sampling_mode == SamplingMode.PRIORITY_BASED:
                effectiveness += 10.0
                recs.append("Priority-based sampling paired with backpressure is optimal")

        elif strategy == BackpressureStrategy.SPILL_TO_DISK:
            # Write excess to disk for later processing
            effectiveness = 85.0
            loss_risk = "low"
            producer_impact = "low"
            throughput = 100.0
            disk_cap = config.spill_disk_capacity_mb
            if disk_cap > 0 and excess > 0:
                spill_minutes = disk_cap / (excess * 60.0)
            elif excess <= 0:
                spill_minutes = -1.0  # no overflow
            else:
                spill_minutes = 0.0
                effectiveness -= 20.0
                loss_risk = "high"
                recs.append("Spill-to-disk configured but no disk capacity allocated")

            if disk_cap > 0 and disk_cap < 1024.0:
                recs.append("Consider increasing spill disk to at least 1 GB for sustained spikes")

            return BackpressureAssessment(
                strategy=strategy.value,
                effectiveness_score=round(_clamp(effectiveness), 2),
                data_loss_risk=loss_risk,
                producer_impact=producer_impact,
                throughput_preservation_percent=round(_clamp(throughput), 2),
                disk_spill_capacity_minutes=round(spill_minutes, 2) if spill_minutes >= 0 else -1.0,
                recommendations=recs,
            )
        else:
            effectiveness = 0.0
            loss_risk = "unknown"
            producer_impact = "unknown"
            throughput = 100.0

        return BackpressureAssessment(
            strategy=strategy.value,
            effectiveness_score=round(_clamp(effectiveness), 2),
            data_loss_risk=loss_risk,
            producer_impact=producer_impact,
            throughput_preservation_percent=round(_clamp(throughput), 2),
            disk_spill_capacity_minutes=0.0,
            recommendations=recs,
        )

    # -- failover analysis ---------------------------------------------------

    def analyze_failover(
        self,
        config: LogPipelineConfig,
    ) -> FailoverAssessment:
        """Analyze log pipeline failover readiness (hot/warm/cold standby)."""
        mode = config.failover_mode
        recs: list[str] = []

        if mode == FailoverMode.NONE:
            return FailoverAssessment(
                mode=mode.value,
                switch_time_seconds=0.0,
                data_loss_during_switch_mb=0.0,
                standby_readiness_score=0.0,
                rpo_seconds=float("inf"),
                rto_seconds=float("inf"),
                standby_sync_lag_ms=0.0,
                recommendations=[
                    "No failover mode configured; complete log loss during primary failure",
                    "Consider at least warm standby for critical log pipelines",
                ],
            )

        switch_time = config.failover_switch_time_seconds
        ingestion = config.ingestion_rate_mb_per_sec
        loss_during_switch = ingestion * switch_time

        if mode == FailoverMode.HOT:
            readiness = 95.0
            rpo = 0.0
            rto = max(switch_time, 1.0)
            sync_lag = config.replication_lag_ms
            if config.standby_replicas < 1:
                readiness -= 30.0
                recs.append("Hot standby requires at least 1 standby replica")
            if switch_time > 5.0:
                recs.append("Hot standby switch time > 5s; consider reducing for near-zero RTO")
            if config.standby_replicas >= 2:
                readiness = min(100.0, readiness + 5.0)

        elif mode == FailoverMode.WARM:
            readiness = 65.0
            rpo = switch_time
            rto = switch_time * 2.0
            sync_lag = config.replication_lag_ms * 2.0
            if config.standby_replicas < 1:
                readiness -= 25.0
                recs.append("Warm standby requires at least 1 standby replica")
            if switch_time > 60.0:
                recs.append("Warm standby switch time > 60s; consider hot standby")
            recs.append("Warm standby may lose in-flight data during switch")

        elif mode == FailoverMode.COLD:
            readiness = 30.0
            rpo = switch_time * 3.0
            rto = switch_time * 5.0
            sync_lag = 0.0  # cold standby has no sync
            recs.append("Cold standby requires full pipeline restart; significant data loss expected")
            recs.append("Consider upgrading to warm or hot standby for critical pipelines")
            if config.standby_replicas >= 1:
                readiness += 10.0
        else:
            readiness = 0.0
            rpo = float("inf")
            rto = float("inf")
            sync_lag = 0.0

        return FailoverAssessment(
            mode=mode.value,
            switch_time_seconds=round(switch_time, 2),
            data_loss_during_switch_mb=round(loss_during_switch, 4),
            standby_readiness_score=round(_clamp(readiness), 2),
            rpo_seconds=round(rpo, 2) if math.isfinite(rpo) else -1.0,
            rto_seconds=round(rto, 2) if math.isfinite(rto) else -1.0,
            standby_sync_lag_ms=round(sync_lag, 2),
            recommendations=recs,
        )

    # -- cross-datacenter replication analysis --------------------------------

    def analyze_replication(
        self,
        config: LogPipelineConfig,
    ) -> ReplicationAssessment:
        """Analyze cross-datacenter log replication configuration."""
        mode = config.replication_mode
        dc_count = config.remote_dc_count
        lag = config.replication_lag_ms
        recs: list[str] = []

        if mode == ReplicationMode.NONE or dc_count == 0:
            return ReplicationAssessment(
                mode=mode.value,
                dc_count=dc_count,
                replication_lag_ms=0.0,
                data_durability_score=20.0,
                cross_dc_loss_risk="critical",
                bandwidth_overhead_percent=0.0,
                consistency_model="none",
                recommendations=[
                    "No cross-datacenter replication; complete log loss during DC failure",
                    "Configure at least async replication to one remote DC",
                ],
            )

        # Base durability by mode
        if mode == ReplicationMode.SYNC:
            durability = 95.0
            consistency = "strong"
            bw_overhead = dc_count * 100.0  # full copy per DC
            loss_risk = "low"
            if lag > 50.0:
                recs.append("Sync replication lag > 50ms; may impact write throughput")
                durability -= 5.0

        elif mode == ReplicationMode.SEMI_SYNC:
            durability = 80.0
            consistency = "read_your_writes"
            bw_overhead = dc_count * 80.0
            loss_risk = "medium"
            recs.append("Semi-sync provides good durability with moderate latency impact")

        elif mode == ReplicationMode.ASYNC:
            durability = 60.0
            consistency = "eventual"
            bw_overhead = dc_count * 50.0
            loss_risk = "medium"
            if lag > 1000.0:
                loss_risk = "high"
                durability -= 15.0
                recs.append("Async replication lag > 1s; significant data loss risk during DC failure")
            recs.append("Async replication may lose recent data during failover")
        else:
            durability = 20.0
            consistency = "none"
            bw_overhead = 0.0
            loss_risk = "critical"

        # Bonus for multiple DCs
        if dc_count >= 3:
            durability = min(100.0, durability + 10.0)
            recs.append("3+ DCs provide excellent durability against regional failures")
        elif dc_count == 1:
            recs.append("Consider adding a second remote DC for geographic diversity")

        return ReplicationAssessment(
            mode=mode.value,
            dc_count=dc_count,
            replication_lag_ms=round(lag, 2),
            data_durability_score=round(_clamp(durability), 2),
            cross_dc_loss_risk=loss_risk,
            bandwidth_overhead_percent=round(_clamp(bw_overhead), 2),
            consistency_model=consistency,
            recommendations=recs,
        )

    # -- cost vs resilience trade-off ----------------------------------------

    def optimize_cost_resilience(
        self,
        graph: InfraGraph,
        config: LogPipelineConfig,
    ) -> CostResilienceTradeoff:
        """Find optimal balance between pipeline cost and resilience."""
        # Current cost
        cost_result = self.model_cost(graph, config)
        current_cost = cost_result.total_monthly_cost

        # Current resilience
        assessment = self.assess_pipeline(graph, config)
        current_resilience = assessment.overall_resilience_score

        # Simulate optimized configuration
        actions: list[str] = []
        optimized_cost = current_cost
        optimized_resilience = current_resilience

        # Action 1: Add replicas if missing
        if config.queue_replicas < 2:
            optimized_cost *= 1.15  # 15% more for queue redundancy
            optimized_resilience = min(100.0, optimized_resilience + 8.0)
            actions.append("Add queue replicas (+15% cost, +8 resilience)")

        if config.storage_replicas < 2:
            optimized_cost *= 1.25  # 25% more for storage redundancy
            optimized_resilience = min(100.0, optimized_resilience + 10.0)
            actions.append("Add storage replicas (+25% cost, +10 resilience)")

        if config.indexer_replicas < 2:
            optimized_cost *= 1.10  # 10% more for indexer redundancy
            optimized_resilience = min(100.0, optimized_resilience + 6.0)
            actions.append("Add indexer replicas (+10% cost, +6 resilience)")

        # Action 2: Enable sampling if not set and volume is high
        daily_gb = self._daily_volume_gb(graph, config)
        if config.sampling_mode == SamplingMode.NONE and daily_gb > 50.0:
            optimized_cost *= 0.70  # 30% savings from sampling
            optimized_resilience = max(0.0, optimized_resilience - 2.0)
            actions.append("Enable sampling (-30% cost, -2 resilience)")

        # Action 3: Add DLQ if missing
        if not config.has_dead_letter_queue:
            optimized_cost *= 1.05
            optimized_resilience = min(100.0, optimized_resilience + 5.0)
            actions.append("Add dead letter queue (+5% cost, +5 resilience)")

        # Action 4: Enable backpressure if missing
        if config.backpressure_strategy == BackpressureStrategy.NONE:
            optimized_resilience = min(100.0, optimized_resilience + 3.0)
            actions.append("Enable backpressure (+0% cost, +3 resilience)")

        # Cost per resilience point
        resilience_delta = optimized_resilience - current_resilience
        cost_delta = optimized_cost - current_cost
        if resilience_delta > 0:
            cost_per_point = cost_delta / resilience_delta
        else:
            cost_per_point = 0.0

        # Trade-off rating
        if current_resilience >= 80.0 and current_cost <= optimized_cost * 0.8:
            rating = "efficient"
        elif current_resilience < 50.0:
            rating = "underinvested"
        elif current_cost > optimized_cost * 1.5:
            rating = "overinvested"
        else:
            rating = "balanced"

        recs: list[str] = []
        if rating == "underinvested":
            recs.append("Current investment is too low for acceptable resilience; increase spend")
        elif rating == "overinvested":
            recs.append("Consider reducing over-provisioned resources to save cost")
        if not actions:
            recs.append("Pipeline is already well-optimized for cost and resilience")

        return CostResilienceTradeoff(
            current_monthly_cost=round(current_cost, 2),
            current_resilience_score=round(current_resilience, 2),
            optimized_monthly_cost=round(optimized_cost, 2),
            optimized_resilience_score=round(optimized_resilience, 2),
            cost_per_resilience_point=round(cost_per_point, 4),
            optimization_actions=actions,
            trade_off_rating=rating,
            recommendations=recs,
        )

    # -- alert pipeline dependency analysis -----------------------------------

    def analyze_alert_dependency(
        self,
        config: LogPipelineConfig,
    ) -> AlertPipelineDependency:
        """Analyze whether alerting depends on the log pipeline and identify fallbacks."""
        destinations = list(config.alert_destinations)
        depends = config.alert_depends_on_log_pipeline
        recs: list[str] = []

        # Identify independent alert paths
        independent_paths = 0
        fallbacks: list[str] = []

        # Known independent mechanisms
        independent_keywords = {"pagerduty", "opsgenie", "sns", "twilio", "email", "webhook"}
        # Known log-dependent mechanisms
        dependent_keywords = {"elasticsearch", "loki", "splunk", "cloudwatch_logs", "datadog_logs"}

        for dest in destinations:
            dest_lower = dest.lower()
            is_independent = any(kw in dest_lower for kw in independent_keywords)
            is_dependent = any(kw in dest_lower for kw in dependent_keywords)
            if is_independent and not is_dependent:
                independent_paths += 1
                fallbacks.append(dest)

        # If alerting depends on log pipeline
        if depends and independent_paths == 0:
            loss_risk = "critical"
            can_alert = False
            recs.append("Alerting fully depends on log pipeline; add independent alert path")
            recs.append("Consider PagerDuty, OpsGenie, or SNS as independent alert mechanisms")
        elif depends and independent_paths > 0:
            loss_risk = "medium"
            can_alert = True
            recs.append("Partial independence; ensure independent paths cover critical alerts")
        elif not depends and independent_paths > 0:
            loss_risk = "low"
            can_alert = True
        elif not depends and independent_paths == 0:
            # Not dependent but no explicit independent paths either
            loss_risk = "medium"
            can_alert = True
            recs.append("Alerting is not log-dependent but no explicit independent paths configured")
        else:
            loss_risk = "unknown"
            can_alert = False

        if not destinations:
            recs.append("No alert destinations configured; add at least one alert channel")
            loss_risk = "critical"
            can_alert = False

        if independent_paths < 2 and destinations:
            recs.append("Add redundant independent alert paths for high availability")

        return AlertPipelineDependency(
            alert_destinations=destinations,
            depends_on_log_pipeline=depends,
            independent_alert_paths=independent_paths,
            alert_loss_risk_during_outage=loss_risk,
            can_alert_during_log_failure=can_alert,
            fallback_mechanisms=fallbacks,
            recommendations=recs,
        )

    # -- scenario-based log loss estimation -----------------------------------

    def estimate_scenario_loss(
        self,
        scenario: LogLossScenario,
        config: LogPipelineConfig,
        duration_minutes: float = 10.0,
    ) -> dict[str, object]:
        """Estimate log loss for a specific failure scenario."""
        base_impact = _SCENARIO_IMPACT.get(scenario, 50.0)
        ingestion = config.ingestion_rate_mb_per_sec

        # Mitigations
        mitigation = 0.0
        recs: list[str] = []

        if config.has_dead_letter_queue:
            mitigation += 15.0
        if config.has_backpressure:
            mitigation += 10.0
        if config.backpressure_strategy == BackpressureStrategy.SPILL_TO_DISK:
            mitigation += 20.0
        elif config.backpressure_strategy == BackpressureStrategy.BLOCK:
            mitigation += 15.0
        elif config.backpressure_strategy == BackpressureStrategy.SAMPLE:
            mitigation += 10.0
        elif config.backpressure_strategy == BackpressureStrategy.DROP:
            mitigation += 5.0

        if config.queue_replicas >= 2:
            mitigation += 10.0
        if config.storage_replicas >= 2:
            mitigation += 10.0
        if config.failover_mode != FailoverMode.NONE:
            mitigation += 15.0

        effective_impact = _clamp(base_impact - mitigation)

        # Volume at risk
        volume_at_risk_mb = ingestion * duration_minutes * 60.0
        estimated_loss_mb = volume_at_risk_mb * (effective_impact / 100.0)

        if effective_impact >= 60.0:
            severity = "critical"
            recs.append(f"Scenario {scenario.value} has critical impact; add mitigations urgently")
        elif effective_impact >= 30.0:
            severity = "high"
            recs.append(f"Scenario {scenario.value} has high impact; consider additional redundancy")
        elif effective_impact >= 10.0:
            severity = "medium"
        else:
            severity = "low"

        return {
            "scenario": scenario.value,
            "base_impact_percent": round(base_impact, 2),
            "mitigated_impact_percent": round(effective_impact, 2),
            "mitigation_effectiveness_percent": round(mitigation, 2),
            "duration_minutes": round(duration_minutes, 2),
            "volume_at_risk_mb": round(volume_at_risk_mb, 2),
            "estimated_loss_mb": round(estimated_loss_mb, 2),
            "severity": severity,
            "recommendations": recs,
        }

    # -- full pipeline assessment --------------------------------------------

    def assess_pipeline(
        self,
        graph: InfraGraph,
        config: LogPipelineConfig,
    ) -> LogPipelineAssessment:
        """Perform a full log pipeline resilience assessment."""
        now = datetime.now(timezone.utc).isoformat()

        stage_risks = self.assess_stage_risks(graph, config)
        redundancy = self.evaluate_redundancy(config)

        # Overall resilience
        if stage_risks:
            avg_risk = sum(sr.risk_score for sr in stage_risks) / len(stage_risks)
        else:
            avg_risk = 50.0

        resilience = 100.0 - avg_risk

        # Adjust for redundancy
        resilience += redundancy.overall_redundancy_score * 0.2

        # Compliance boost/penalty
        comp_days = _COMPLIANCE_RETENTION_DAYS.get(config.compliance_framework, 0)
        if comp_days > 0 and config.retention_days < comp_days:
            resilience -= 15.0

        resilience = _clamp(resilience)

        # Total estimated loss
        if stage_risks:
            total_loss = max(sr.loss_percent for sr in stage_risks)
        else:
            total_loss = 0.0

        # Bottlenecks
        bottlenecks = [sr.stage for sr in stage_risks if sr.bottleneck]

        # SPOFs from redundancy
        spofs = list(redundancy.single_points_of_failure)

        # Aggregate recommendations
        all_recs: list[str] = []
        for sr in stage_risks:
            all_recs.extend(sr.recommendations)
        all_recs.extend(redundancy.recommendations)

        # Deduplicate
        seen: set[str] = set()
        unique_recs: list[str] = []
        for r in all_recs:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        meets_compliance = config.retention_days >= comp_days if comp_days > 0 else True

        return LogPipelineAssessment(
            timestamp=now,
            overall_resilience_score=round(resilience, 2),
            stage_risks=stage_risks,
            single_points_of_failure=spofs,
            total_estimated_loss_percent=round(_clamp(total_loss), 2),
            bottlenecks=bottlenecks,
            compliance_met=meets_compliance,
            recommendations=unique_recs,
        )

    # -- compliance retention check ------------------------------------------

    def check_compliance_retention(
        self,
        config: LogPipelineConfig,
    ) -> dict[str, object]:
        """Check if retention meets compliance requirements."""
        required = _COMPLIANCE_RETENTION_DAYS.get(config.compliance_framework, 0)
        meets = config.retention_days >= required if required > 0 else True
        gap = max(0, required - config.retention_days)

        result: dict[str, object] = {
            "framework": config.compliance_framework.value,
            "required_retention_days": required,
            "configured_retention_days": config.retention_days,
            "meets_requirement": meets,
            "gap_days": gap,
            "recommendations": [],
        }

        recs: list[str] = []
        if not meets:
            recs.append(
                f"Increase retention to at least {required} days for "
                f"{config.compliance_framework.value} compliance"
            )
        if config.compliance_framework == ComplianceFramework.HIPAA:
            recs.append("Ensure log data is encrypted at rest and in transit for HIPAA")
        if config.compliance_framework == ComplianceFramework.PCI_DSS:
            recs.append("Ensure audit trail integrity and tamper detection for PCI DSS")

        result["recommendations"] = recs
        return result

    # -- internal helpers ----------------------------------------------------

    def _daily_volume_gb(self, graph: InfraGraph, config: LogPipelineConfig) -> float:
        """Estimate daily log volume in GB."""
        base_rate = config.ingestion_rate_mb_per_sec
        # Scale by number of components if graph is non-empty
        num_components = max(1, len(graph.components))
        scale_factor = 1.0 + math.log2(max(1, num_components)) * 0.1
        effective_rate = base_rate * config.sampling_rate * scale_factor
        daily_mb = effective_rate * 86400.0
        return daily_mb / 1024.0

    def _daily_volume_gb_raw(self, config: LogPipelineConfig) -> float:
        """Estimate daily log volume in GB from config alone."""
        daily_mb = config.ingestion_rate_mb_per_sec * config.sampling_rate * 86400.0
        return daily_mb / 1024.0
