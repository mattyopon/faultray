# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Deployment Strategy Analyzer — evaluate deployment strategies for resilience and risk.

Analyzes infrastructure graphs to assess deployment strategies (rolling update,
blue-green, canary, A/B testing, recreate, shadow/dark launch) across multiple
dimensions: rollback safety, canary progression, resource cost, velocity-risk
tradeoffs, health check adequacy, database migration compatibility,
multi-region coordination, deployment window optimization, feature flag
integration, zero-downtime verification, and pipeline stage analysis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CANARY_DEFAULT_STAGES = [1, 5, 10, 25, 50, 75, 100]
_BLUE_GREEN_COST_MULTIPLIER = 2.0
_SHADOW_COST_MULTIPLIER = 1.8
_AB_COST_MULTIPLIER = 1.3
_ROLLING_COST_MULTIPLIER = 1.1
_CANARY_COST_MULTIPLIER = 1.15
_RECREATE_COST_MULTIPLIER = 1.0

_PIPELINE_STAGES_DEFAULT = ["build", "test", "stage", "prod"]

_RISK_WEIGHT_ROLLBACK = 0.25
_RISK_WEIGHT_DOWNTIME = 0.25
_RISK_WEIGHT_DATA = 0.20
_RISK_WEIGHT_DEPENDENCY = 0.15
_RISK_WEIGHT_RESOURCE = 0.15

_PEAK_HOURS = {8, 9, 10, 11, 12, 13, 14, 15, 16, 17}
_SAFE_HOURS = {2, 3, 4, 5}

_REGION_COORDINATION_OVERHEAD_SECONDS = 120
_REGION_PROPAGATION_DELAY_SECONDS = 30


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StrategyType(str, Enum):
    """Deployment strategy type."""

    ROLLING_UPDATE = "rolling_update"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    AB_TESTING = "ab_testing"
    RECREATE = "recreate"
    SHADOW = "shadow"


class RollbackSafety(str, Enum):
    """How safe the rollback is for a given strategy."""

    INSTANT = "instant"
    FAST = "fast"
    MODERATE = "moderate"
    SLOW = "slow"
    DANGEROUS = "dangerous"


class DeploymentRisk(str, Enum):
    """Overall deployment risk classification."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class PipelineStage(str, Enum):
    """CI/CD pipeline stage."""

    BUILD = "build"
    TEST = "test"
    STAGE = "stage"
    PROD = "prod"


class HealthCheckAdequacy(str, Enum):
    """Adequacy of health checks during deployment."""

    EXCELLENT = "excellent"
    ADEQUATE = "adequate"
    INSUFFICIENT = "insufficient"
    MISSING = "missing"


class DbMigrationCompat(str, Enum):
    """Database migration compatibility with a strategy."""

    FULLY_COMPATIBLE = "fully_compatible"
    COMPATIBLE_WITH_CAUTION = "compatible_with_caution"
    REQUIRES_DUAL_WRITE = "requires_dual_write"
    INCOMPATIBLE = "incompatible"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class RollbackAnalysis(BaseModel):
    """Rollback characteristics for a deployment strategy."""

    strategy: StrategyType
    rollback_time_seconds: float = 0.0
    safety: RollbackSafety = RollbackSafety.MODERATE
    data_compatible: bool = True
    requires_data_migration: bool = False
    estimated_data_loss_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CanaryStageConfig(BaseModel):
    """Configuration for one stage of a canary deployment."""

    traffic_percent: float = Field(ge=0.0, le=100.0)
    duration_minutes: int = 5
    success_threshold: float = Field(default=99.0, ge=0.0, le=100.0)
    error_rate_abort_threshold: float = Field(default=5.0, ge=0.0, le=100.0)
    latency_p99_abort_ms: float = 500.0


class CanaryProgression(BaseModel):
    """Full canary traffic progression plan."""

    stages: list[CanaryStageConfig] = Field(default_factory=list)
    total_duration_minutes: int = 0
    auto_promote: bool = False
    auto_rollback: bool = True
    metric_evaluation_window_seconds: int = 300
    recommendations: list[str] = Field(default_factory=list)


class ResourceCostModel(BaseModel):
    """Resource cost modelling for a deployment strategy."""

    strategy: StrategyType
    cost_multiplier: float = 1.0
    peak_extra_instances: int = 0
    peak_extra_cost_hourly: float = 0.0
    total_deployment_cost: float = 0.0
    steady_state_cost_hourly: float = 0.0
    notes: list[str] = Field(default_factory=list)


class VelocityRiskScore(BaseModel):
    """Deployment velocity vs risk tradeoff scoring."""

    strategy: StrategyType
    velocity_score: float = Field(default=50.0, ge=0.0, le=100.0)
    risk_score: float = Field(default=50.0, ge=0.0, le=100.0)
    composite_score: float = Field(default=50.0, ge=0.0, le=100.0)
    recommendation: str = ""


class HealthCheckEvaluation(BaseModel):
    """Assessment of health check adequacy during deployment."""

    component_id: str
    has_readiness_probe: bool = False
    has_liveness_probe: bool = False
    has_startup_probe: bool = False
    probe_interval_seconds: float = 10.0
    adequacy: HealthCheckAdequacy = HealthCheckAdequacy.MISSING
    recommendations: list[str] = Field(default_factory=list)


class DbMigrationAssessment(BaseModel):
    """Database migration compatibility assessment."""

    component_id: str
    strategy: StrategyType
    compatibility: DbMigrationCompat = DbMigrationCompat.FULLY_COMPATIBLE
    requires_backward_compat_schema: bool = False
    estimated_migration_time_minutes: int = 0
    rollback_migration_possible: bool = True
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class RegionDeploymentPlan(BaseModel):
    """Multi-region deployment coordination plan."""

    regions: list[str] = Field(default_factory=list)
    sequence: list[str] = Field(default_factory=list)
    coordination_overhead_seconds: float = 0.0
    total_deployment_time_seconds: float = 0.0
    canary_region: str = ""
    rollback_order: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class DeploymentWindowRecommendation(BaseModel):
    """Optimal deployment window recommendation."""

    recommended_hour_utc: int = Field(default=3, ge=0, le=23)
    risk_level: DeploymentRisk = DeploymentRisk.LOW
    traffic_pattern_factor: float = 1.0
    is_peak_hour: bool = False
    is_safe_hour: bool = True
    recommended_day_of_week: int = Field(default=1, ge=0, le=6)
    notes: list[str] = Field(default_factory=list)


class FeatureFlagAssessment(BaseModel):
    """Feature flag integration assessment for a deployment."""

    has_feature_flags: bool = False
    kill_switch_available: bool = False
    gradual_rollout_possible: bool = False
    flag_count: int = 0
    decoupled_deploy_and_release: bool = False
    risk_reduction_percent: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class ZeroDowntimeVerification(BaseModel):
    """Verification of zero-downtime deployment capability."""

    strategy: StrategyType
    is_zero_downtime: bool = False
    estimated_downtime_seconds: float = 0.0
    blockers: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class PipelineStageAnalysis(BaseModel):
    """Analysis of a CI/CD pipeline stage."""

    stage: PipelineStage
    estimated_duration_minutes: int = 0
    has_automated_tests: bool = False
    has_approval_gate: bool = False
    has_rollback_mechanism: bool = False
    risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class PipelineAnalysis(BaseModel):
    """Full deployment pipeline analysis."""

    stages: list[PipelineStageAnalysis] = Field(default_factory=list)
    total_duration_minutes: int = 0
    overall_risk: DeploymentRisk = DeploymentRisk.LOW
    has_full_automation: bool = False
    missing_stages: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


@dataclass
class StrategyAnalysisReport:
    """Complete analysis report for a deployment strategy."""

    strategy: StrategyType
    graph_component_count: int = 0
    rollback: RollbackAnalysis | None = None
    canary: CanaryProgression | None = None
    cost: ResourceCostModel | None = None
    velocity_risk: VelocityRiskScore | None = None
    health_checks: list[HealthCheckEvaluation] = field(default_factory=list)
    db_migrations: list[DbMigrationAssessment] = field(default_factory=list)
    region_plan: RegionDeploymentPlan | None = None
    window: DeploymentWindowRecommendation | None = None
    feature_flags: FeatureFlagAssessment | None = None
    zero_downtime: ZeroDowntimeVerification | None = None
    pipeline: PipelineAnalysis | None = None
    overall_risk: DeploymentRisk = DeploymentRisk.MODERATE
    overall_score: float = 50.0
    recommendations: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Serialise the report to a dictionary."""
        return {
            "strategy": self.strategy.value,
            "graph_component_count": self.graph_component_count,
            "overall_risk": self.overall_risk.value,
            "overall_score": round(self.overall_score, 2),
            "recommendations": self.recommendations,
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class DeploymentStrategyAnalyzer:
    """Analyze and evaluate deployment strategies for resilience and risk.

    Evaluates a chosen deployment strategy against an infrastructure graph,
    producing detailed assessments across rollback safety, canary analysis,
    resource cost modelling, velocity/risk tradeoffs, health check adequacy,
    database migration compatibility, multi-region coordination, deployment
    window optimisation, feature flag integration, zero-downtime verification,
    and pipeline stage analysis.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        strategy: StrategyType,
        *,
        regions: list[str] | None = None,
        deploy_hour_utc: int = 3,
        feature_flags: list[str] | None = None,
        pipeline_stages: list[str] | None = None,
    ) -> StrategyAnalysisReport:
        """Run a full analysis of the given deployment strategy.

        Parameters
        ----------
        strategy:
            The deployment strategy to evaluate.
        regions:
            List of region identifiers for multi-region analysis.
        deploy_hour_utc:
            The planned deployment hour (0-23 UTC).
        feature_flags:
            List of feature flag identifiers associated with this deploy.
        pipeline_stages:
            Custom pipeline stages; defaults to build/test/stage/prod.
        """
        regions = regions or []
        feature_flags = feature_flags or []
        pipeline_stages = pipeline_stages or list(_PIPELINE_STAGES_DEFAULT)

        components = list(self._graph.components.values())
        report = StrategyAnalysisReport(
            strategy=strategy,
            graph_component_count=len(components),
        )

        report.rollback = self.analyze_rollback(strategy)
        report.canary = self.analyze_canary(strategy)
        report.cost = self.analyze_cost(strategy)
        report.velocity_risk = self.analyze_velocity_risk(strategy)
        report.health_checks = [
            self.evaluate_health_check(c, strategy) for c in components
        ]
        report.db_migrations = [
            self.assess_db_migration(c, strategy)
            for c in components
            if c.type in (ComponentType.DATABASE, ComponentType.STORAGE)
        ]
        report.region_plan = self.plan_multi_region(strategy, regions)
        report.window = self.recommend_window(deploy_hour_utc)
        report.feature_flags = self.assess_feature_flags(feature_flags)
        report.zero_downtime = self.verify_zero_downtime(strategy)
        report.pipeline = self.analyze_pipeline(pipeline_stages)

        report.overall_score = self._compute_overall_score(report)
        report.overall_risk = self._classify_risk(report.overall_score)
        report.recommendations = self._gather_recommendations(report)

        return report

    # ------------------------------------------------------------------
    # Rollback Analysis
    # ------------------------------------------------------------------

    def analyze_rollback(self, strategy: StrategyType) -> RollbackAnalysis:
        """Analyze rollback characteristics for a strategy."""
        analysis = RollbackAnalysis(strategy=strategy)

        if strategy == StrategyType.BLUE_GREEN:
            analysis.rollback_time_seconds = 10.0
            analysis.safety = RollbackSafety.INSTANT
            analysis.data_compatible = True
            analysis.steps = [
                "Switch traffic back to blue environment",
                "Verify blue environment health",
                "Investigate green environment issues",
            ]
        elif strategy == StrategyType.CANARY:
            analysis.rollback_time_seconds = 30.0
            analysis.safety = RollbackSafety.FAST
            analysis.data_compatible = True
            analysis.steps = [
                "Route all traffic away from canary instances",
                "Scale down canary instances",
                "Verify baseline instances health",
            ]
        elif strategy == StrategyType.ROLLING_UPDATE:
            component_count = len(self._graph.components)
            analysis.rollback_time_seconds = max(60.0, component_count * 15.0)
            analysis.safety = RollbackSafety.MODERATE
            analysis.data_compatible = True
            analysis.steps = [
                "Initiate reverse rolling update",
                "Roll back instances one by one",
                "Verify each instance after rollback",
                "Confirm full rollback completion",
            ]
        elif strategy == StrategyType.AB_TESTING:
            analysis.rollback_time_seconds = 20.0
            analysis.safety = RollbackSafety.FAST
            analysis.data_compatible = True
            analysis.steps = [
                "Disable B variant traffic routing",
                "Route all traffic to A variant",
                "Verify A variant stability",
            ]
        elif strategy == StrategyType.RECREATE:
            analysis.rollback_time_seconds = 300.0
            analysis.safety = RollbackSafety.DANGEROUS
            analysis.data_compatible = False
            analysis.requires_data_migration = True
            analysis.estimated_data_loss_risk = 0.15
            analysis.steps = [
                "Stop current deployment",
                "Restore previous version from backup",
                "Replay any lost transactions if possible",
                "Verify data integrity",
            ]
            analysis.warnings = [
                "Recreate strategy has inherent downtime during rollback",
                "Data written during deployment window may be lost",
            ]
        elif strategy == StrategyType.SHADOW:
            analysis.rollback_time_seconds = 5.0
            analysis.safety = RollbackSafety.INSTANT
            analysis.data_compatible = True
            analysis.steps = [
                "Stop mirroring traffic to shadow",
                "Tear down shadow environment",
            ]

        # Adjust rollback time based on stateful components
        has_stateful = any(
            c.type in (ComponentType.DATABASE, ComponentType.STORAGE)
            for c in self._graph.components.values()
        )
        if has_stateful and strategy not in (
            StrategyType.BLUE_GREEN,
            StrategyType.SHADOW,
        ):
            analysis.rollback_time_seconds *= 1.5
            if not analysis.warnings:
                analysis.warnings = []
            analysis.warnings.append(
                "Stateful components increase rollback complexity"
            )

        return analysis

    # ------------------------------------------------------------------
    # Canary Analysis
    # ------------------------------------------------------------------

    def analyze_canary(
        self,
        strategy: StrategyType,
        *,
        custom_stages: list[float] | None = None,
    ) -> CanaryProgression:
        """Analyze canary traffic progression for a strategy."""
        progression = CanaryProgression()

        if strategy != StrategyType.CANARY:
            progression.recommendations.append(
                f"Canary progression is not applicable to {strategy.value} strategy"
            )
            return progression

        if custom_stages is None:
            percentages = [float(s) for s in _CANARY_DEFAULT_STAGES]
        else:
            percentages = custom_stages

        component_count = len(self._graph.components)
        has_db = any(
            c.type in (ComponentType.DATABASE, ComponentType.STORAGE)
            for c in self._graph.components.values()
        )

        for pct in percentages:
            duration = 5
            if pct <= 5:
                duration = 10
            elif pct <= 25:
                duration = 7
            elif pct >= 75:
                duration = 3

            if has_db:
                duration = int(duration * 1.5)

            error_abort = 5.0 if pct < 50 else 3.0
            latency_abort = 500.0 if pct < 50 else 300.0

            stage = CanaryStageConfig(
                traffic_percent=pct,
                duration_minutes=duration,
                success_threshold=99.0 if pct < 50 else 99.5,
                error_rate_abort_threshold=error_abort,
                latency_p99_abort_ms=latency_abort,
            )
            progression.stages.append(stage)

        progression.total_duration_minutes = sum(
            s.duration_minutes for s in progression.stages
        )
        progression.auto_rollback = True
        progression.auto_promote = component_count <= 5

        if has_db:
            progression.recommendations.append(
                "Database components detected — use longer observation windows"
            )
        if component_count > 10:
            progression.recommendations.append(
                "Large topology — consider staged canary per service group"
            )
        if not progression.stages:
            progression.recommendations.append(
                "No canary stages configured — define traffic progression"
            )

        return progression

    # ------------------------------------------------------------------
    # Resource Cost Model
    # ------------------------------------------------------------------

    def analyze_cost(self, strategy: StrategyType) -> ResourceCostModel:
        """Model resource costs for a deployment strategy."""
        components = list(self._graph.components.values())
        total_hourly = sum(
            c.cost_profile.hourly_infra_cost for c in components
        )
        instance_count = sum(c.replicas for c in components)

        multiplier_map = {
            StrategyType.BLUE_GREEN: _BLUE_GREEN_COST_MULTIPLIER,
            StrategyType.SHADOW: _SHADOW_COST_MULTIPLIER,
            StrategyType.AB_TESTING: _AB_COST_MULTIPLIER,
            StrategyType.ROLLING_UPDATE: _ROLLING_COST_MULTIPLIER,
            StrategyType.CANARY: _CANARY_COST_MULTIPLIER,
            StrategyType.RECREATE: _RECREATE_COST_MULTIPLIER,
        }
        multiplier = multiplier_map.get(strategy, 1.0)

        extra_instances = 0
        if strategy == StrategyType.BLUE_GREEN:
            extra_instances = instance_count
        elif strategy == StrategyType.SHADOW:
            extra_instances = max(1, int(instance_count * 0.8))
        elif strategy == StrategyType.CANARY:
            extra_instances = max(1, int(math.ceil(instance_count * 0.15)))
        elif strategy == StrategyType.AB_TESTING:
            extra_instances = max(1, int(math.ceil(instance_count * 0.3)))

        notes: list[str] = []
        if strategy == StrategyType.BLUE_GREEN:
            notes.append(
                "Blue-green requires full duplicate infrastructure (2x cost)"
            )
        if strategy == StrategyType.SHADOW:
            notes.append(
                "Shadow deployment mirrors traffic — high resource usage"
            )
        if strategy == StrategyType.RECREATE:
            notes.append(
                "Recreate has lowest resource overhead but causes downtime"
            )

        peak_extra_cost = total_hourly * (multiplier - 1.0) if total_hourly > 0 else 0.0

        return ResourceCostModel(
            strategy=strategy,
            cost_multiplier=round(multiplier, 2),
            peak_extra_instances=extra_instances,
            peak_extra_cost_hourly=round(peak_extra_cost, 2),
            total_deployment_cost=round(total_hourly * multiplier, 2),
            steady_state_cost_hourly=round(total_hourly, 2),
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Velocity vs Risk Tradeoff
    # ------------------------------------------------------------------

    def analyze_velocity_risk(self, strategy: StrategyType) -> VelocityRiskScore:
        """Score deployment velocity vs risk for a strategy."""
        velocity_map: dict[StrategyType, float] = {
            StrategyType.RECREATE: 90.0,
            StrategyType.ROLLING_UPDATE: 75.0,
            StrategyType.CANARY: 45.0,
            StrategyType.AB_TESTING: 40.0,
            StrategyType.BLUE_GREEN: 55.0,
            StrategyType.SHADOW: 30.0,
        }
        risk_map: dict[StrategyType, float] = {
            StrategyType.RECREATE: 85.0,
            StrategyType.ROLLING_UPDATE: 50.0,
            StrategyType.CANARY: 25.0,
            StrategyType.AB_TESTING: 30.0,
            StrategyType.BLUE_GREEN: 20.0,
            StrategyType.SHADOW: 10.0,
        }

        velocity = velocity_map.get(strategy, 50.0)
        risk = risk_map.get(strategy, 50.0)

        # Adjust for graph complexity
        component_count = len(self._graph.components)
        edge_count = len(self._graph.all_dependency_edges())

        if component_count > 10:
            risk = min(100.0, risk + 10.0)
            velocity = max(0.0, velocity - 5.0)
        if edge_count > 15:
            risk = min(100.0, risk + 5.0)

        # Composite: higher is better (high velocity, low risk)
        composite = (velocity * 0.4) + ((100.0 - risk) * 0.6)

        recommendation = ""
        if composite >= 70:
            recommendation = "Excellent velocity-risk balance for this strategy"
        elif composite >= 50:
            recommendation = "Acceptable tradeoff — monitor closely during deployment"
        elif composite >= 30:
            recommendation = "Significant risk — consider a safer strategy"
        else:
            recommendation = "High risk — strongly recommend switching to blue-green or canary"

        return VelocityRiskScore(
            strategy=strategy,
            velocity_score=round(velocity, 1),
            risk_score=round(risk, 1),
            composite_score=round(composite, 1),
            recommendation=recommendation,
        )

    # ------------------------------------------------------------------
    # Health Check Evaluation
    # ------------------------------------------------------------------

    def evaluate_health_check(
        self,
        component: Component,
        strategy: StrategyType,
    ) -> HealthCheckEvaluation:
        """Evaluate health check adequacy for a component during deployment."""
        evaluation = HealthCheckEvaluation(component_id=component.id)

        # Infer health check configuration from component attributes
        has_failover = component.failover.enabled
        hc_interval = component.failover.health_check_interval_seconds

        if has_failover:
            evaluation.has_liveness_probe = True
            evaluation.has_readiness_probe = True
            evaluation.probe_interval_seconds = hc_interval
        if component.autoscaling.enabled:
            evaluation.has_readiness_probe = True

        # Components with many replicas likely have startup probes
        if component.replicas >= 3:
            evaluation.has_startup_probe = True

        # Determine adequacy
        probes = sum([
            evaluation.has_readiness_probe,
            evaluation.has_liveness_probe,
            evaluation.has_startup_probe,
        ])

        if probes == 3:
            evaluation.adequacy = HealthCheckAdequacy.EXCELLENT
        elif probes == 2:
            evaluation.adequacy = HealthCheckAdequacy.ADEQUATE
        elif probes == 1:
            evaluation.adequacy = HealthCheckAdequacy.INSUFFICIENT
        else:
            evaluation.adequacy = HealthCheckAdequacy.MISSING

        # Strategy-specific recommendations
        if strategy == StrategyType.ROLLING_UPDATE and not evaluation.has_readiness_probe:
            evaluation.recommendations.append(
                "Readiness probe required for safe rolling updates"
            )
        if strategy == StrategyType.CANARY and not evaluation.has_liveness_probe:
            evaluation.recommendations.append(
                "Liveness probe needed for canary metric collection"
            )
        if strategy == StrategyType.BLUE_GREEN and not evaluation.has_readiness_probe:
            evaluation.recommendations.append(
                "Readiness probe essential for blue-green traffic switching"
            )
        if evaluation.adequacy == HealthCheckAdequacy.MISSING:
            evaluation.recommendations.append(
                "No health checks configured — deployment safety is severely compromised"
            )
        if evaluation.probe_interval_seconds > 30 and has_failover:
            evaluation.recommendations.append(
                "Health check interval is too long — consider reducing to under 30s"
            )

        return evaluation

    # ------------------------------------------------------------------
    # Database Migration Compatibility
    # ------------------------------------------------------------------

    def assess_db_migration(
        self,
        component: Component,
        strategy: StrategyType,
    ) -> DbMigrationAssessment:
        """Assess database migration compatibility with a deployment strategy."""
        assessment = DbMigrationAssessment(
            component_id=component.id,
            strategy=strategy,
        )

        if component.type not in (ComponentType.DATABASE, ComponentType.STORAGE):
            assessment.compatibility = DbMigrationCompat.FULLY_COMPATIBLE
            return assessment

        if strategy == StrategyType.RECREATE:
            assessment.compatibility = DbMigrationCompat.INCOMPATIBLE
            assessment.rollback_migration_possible = False
            assessment.estimated_migration_time_minutes = 60
            assessment.risks.append(
                "Recreate strategy causes downtime — DB migration must complete within window"
            )
            assessment.recommendations.append(
                "Use blue-green or canary for database deployments"
            )
        elif strategy == StrategyType.BLUE_GREEN:
            assessment.compatibility = DbMigrationCompat.REQUIRES_DUAL_WRITE
            assessment.requires_backward_compat_schema = True
            assessment.estimated_migration_time_minutes = 30
            assessment.rollback_migration_possible = True
            assessment.risks.append(
                "Schema must be backward-compatible for blue and green to coexist"
            )
            assessment.recommendations.append(
                "Use expand-and-contract migration pattern"
            )
        elif strategy == StrategyType.CANARY:
            assessment.compatibility = DbMigrationCompat.COMPATIBLE_WITH_CAUTION
            assessment.requires_backward_compat_schema = True
            assessment.estimated_migration_time_minutes = 20
            assessment.rollback_migration_possible = True
            assessment.risks.append(
                "Canary and baseline must read/write the same schema version"
            )
            assessment.recommendations.append(
                "Apply schema migration before canary deployment"
            )
        elif strategy == StrategyType.ROLLING_UPDATE:
            assessment.compatibility = DbMigrationCompat.COMPATIBLE_WITH_CAUTION
            assessment.requires_backward_compat_schema = True
            assessment.estimated_migration_time_minutes = 25
            assessment.rollback_migration_possible = True
            assessment.risks.append(
                "Old and new versions coexist — schema must support both"
            )
            assessment.recommendations.append(
                "Run migration as a separate pre-deployment step"
            )
        elif strategy == StrategyType.SHADOW:
            assessment.compatibility = DbMigrationCompat.FULLY_COMPATIBLE
            assessment.estimated_migration_time_minutes = 10
            assessment.recommendations.append(
                "Shadow uses separate data store — no migration conflict"
            )
        elif strategy == StrategyType.AB_TESTING:
            assessment.compatibility = DbMigrationCompat.REQUIRES_DUAL_WRITE
            assessment.requires_backward_compat_schema = True
            assessment.estimated_migration_time_minutes = 30
            assessment.risks.append(
                "A and B variants may write conflicting data schemas"
            )
            assessment.recommendations.append(
                "Ensure schema compatibility across both variants"
            )

        # Adjust for replicas
        if component.replicas > 1:
            assessment.estimated_migration_time_minutes = int(
                assessment.estimated_migration_time_minutes * 1.2
            )

        return assessment

    # ------------------------------------------------------------------
    # Multi-Region Coordination
    # ------------------------------------------------------------------

    def plan_multi_region(
        self,
        strategy: StrategyType,
        regions: list[str],
    ) -> RegionDeploymentPlan:
        """Plan multi-region deployment coordination and sequencing."""
        plan = RegionDeploymentPlan()

        if not regions:
            plan.recommendations.append(
                "No regions specified — single-region deployment assumed"
            )
            return plan

        plan.regions = list(regions)
        region_count = len(regions)

        # First region is the canary region
        plan.canary_region = regions[0]
        plan.sequence = list(regions)
        plan.rollback_order = list(reversed(regions))

        per_region_seconds = 300.0  # 5 minutes per region base
        if strategy == StrategyType.BLUE_GREEN:
            per_region_seconds = 180.0
        elif strategy == StrategyType.CANARY:
            per_region_seconds = 600.0
        elif strategy == StrategyType.RECREATE:
            per_region_seconds = 120.0

        coordination_overhead = (
            _REGION_COORDINATION_OVERHEAD_SECONDS
            + _REGION_PROPAGATION_DELAY_SECONDS * (region_count - 1)
        )
        plan.coordination_overhead_seconds = coordination_overhead
        plan.total_deployment_time_seconds = (
            per_region_seconds * region_count + coordination_overhead
        )

        if region_count >= 3:
            plan.recommendations.append(
                "Deploy to canary region first, observe for 15+ minutes before proceeding"
            )
        if region_count >= 5:
            plan.recommendations.append(
                "Consider wave-based deployment (groups of 2-3 regions)"
            )
        if strategy == StrategyType.RECREATE and region_count > 1:
            plan.recommendations.append(
                "Recreate strategy in multi-region will cause rolling outages"
            )

        return plan

    # ------------------------------------------------------------------
    # Deployment Window Optimization
    # ------------------------------------------------------------------

    def recommend_window(self, planned_hour_utc: int = 3) -> DeploymentWindowRecommendation:
        """Recommend optimal deployment window based on traffic patterns."""
        window = DeploymentWindowRecommendation(
            recommended_hour_utc=planned_hour_utc,
        )

        is_peak = planned_hour_utc in _PEAK_HOURS
        is_safe = planned_hour_utc in _SAFE_HOURS

        window.is_peak_hour = is_peak
        window.is_safe_hour = is_safe

        if is_peak:
            window.risk_level = DeploymentRisk.HIGH
            window.traffic_pattern_factor = 2.5
            window.notes.append(
                f"Hour {planned_hour_utc} UTC is peak traffic — consider off-peak deployment"
            )
            # Suggest safe alternative
            window.recommended_hour_utc = 3
        elif is_safe:
            window.risk_level = DeploymentRisk.LOW
            window.traffic_pattern_factor = 0.3
            window.notes.append(
                f"Hour {planned_hour_utc} UTC is a safe deployment window"
            )
        else:
            window.risk_level = DeploymentRisk.MODERATE
            window.traffic_pattern_factor = 1.0
            window.notes.append(
                f"Hour {planned_hour_utc} UTC has moderate traffic"
            )

        # Prefer Tuesday-Thursday for deployments
        window.recommended_day_of_week = 2  # Wednesday

        # Check for components under high utilization
        high_util_count = sum(
            1 for c in self._graph.components.values()
            if c.utilization() > 70
        )
        if high_util_count > 0:
            window.notes.append(
                f"{high_util_count} component(s) already at high utilization — "
                "additional deployment risk"
            )

        return window

    # ------------------------------------------------------------------
    # Feature Flag Assessment
    # ------------------------------------------------------------------

    def assess_feature_flags(
        self, flags: list[str],
    ) -> FeatureFlagAssessment:
        """Assess feature flag integration for the deployment."""
        assessment = FeatureFlagAssessment()

        if not flags:
            assessment.recommendations.append(
                "No feature flags configured — deployment is tightly coupled to release"
            )
            return assessment

        assessment.has_feature_flags = True
        assessment.flag_count = len(flags)

        # Heuristic: if any flag name contains "kill" or "switch"
        has_kill = any("kill" in f.lower() or "switch" in f.lower() for f in flags)
        assessment.kill_switch_available = has_kill

        # Heuristic: gradual rollout if any flag contains "gradual" or "rollout"
        has_gradual = any(
            "gradual" in f.lower() or "rollout" in f.lower() for f in flags
        )
        assessment.gradual_rollout_possible = has_gradual

        assessment.decoupled_deploy_and_release = True

        # Calculate risk reduction
        risk_reduction = 10.0  # base reduction from having flags
        if has_kill:
            risk_reduction += 15.0
        if has_gradual:
            risk_reduction += 10.0
        if len(flags) >= 3:
            risk_reduction += 5.0

        assessment.risk_reduction_percent = min(50.0, risk_reduction)

        if not has_kill:
            assessment.recommendations.append(
                "Add a kill switch flag for emergency rollback capability"
            )
        if not has_gradual:
            assessment.recommendations.append(
                "Add gradual rollout flag for progressive traffic shifting"
            )

        return assessment

    # ------------------------------------------------------------------
    # Zero-Downtime Verification
    # ------------------------------------------------------------------

    def verify_zero_downtime(self, strategy: StrategyType) -> ZeroDowntimeVerification:
        """Verify whether the strategy achieves zero-downtime deployment."""
        verification = ZeroDowntimeVerification(strategy=strategy)

        if strategy == StrategyType.RECREATE:
            verification.is_zero_downtime = False
            total_replicas = sum(
                c.replicas for c in self._graph.components.values()
            )
            verification.estimated_downtime_seconds = max(
                30.0, total_replicas * 10.0
            )
            verification.blockers.append(
                "Recreate strategy terminates all instances before deploying new ones"
            )
            verification.mitigations.append(
                "Switch to blue-green or rolling update for zero-downtime"
            )
            verification.confidence = 0.0
        elif strategy == StrategyType.BLUE_GREEN:
            verification.is_zero_downtime = True
            verification.estimated_downtime_seconds = 0.0
            verification.confidence = 0.95
            # Check for single points of failure
            spof_count = sum(
                1 for c in self._graph.components.values()
                if c.replicas == 1
                and not c.failover.enabled
                and len(self._graph.get_dependents(c.id)) > 0
            )
            if spof_count > 0:
                verification.confidence = 0.75
                verification.mitigations.append(
                    f"{spof_count} SPOF(s) detected — ensure load balancer "
                    "handles traffic switch atomically"
                )
        elif strategy == StrategyType.CANARY:
            verification.is_zero_downtime = True
            verification.estimated_downtime_seconds = 0.0
            verification.confidence = 0.9
        elif strategy == StrategyType.ROLLING_UPDATE:
            all_multi_replica = all(
                c.replicas >= 2 for c in self._graph.components.values()
            )
            if all_multi_replica or not self._graph.components:
                verification.is_zero_downtime = True
                verification.estimated_downtime_seconds = 0.0
                verification.confidence = 0.85
            else:
                verification.is_zero_downtime = False
                single_replica = [
                    c.id for c in self._graph.components.values()
                    if c.replicas < 2
                ]
                verification.estimated_downtime_seconds = len(single_replica) * 15.0
                verification.blockers.append(
                    f"Components with single replica: {', '.join(single_replica)}"
                )
                verification.mitigations.append(
                    "Increase replicas to 2+ for all components"
                )
                verification.confidence = 0.4
        elif strategy == StrategyType.SHADOW:
            verification.is_zero_downtime = True
            verification.estimated_downtime_seconds = 0.0
            verification.confidence = 0.98
        elif strategy == StrategyType.AB_TESTING:
            verification.is_zero_downtime = True
            verification.estimated_downtime_seconds = 0.0
            verification.confidence = 0.88

        return verification

    # ------------------------------------------------------------------
    # Pipeline Analysis
    # ------------------------------------------------------------------

    def analyze_pipeline(
        self,
        stages: list[str] | None = None,
    ) -> PipelineAnalysis:
        """Analyze deployment pipeline stages."""
        if stages is None:
            stages = list(_PIPELINE_STAGES_DEFAULT)
        analysis = PipelineAnalysis()

        valid_stages = {s.value for s in PipelineStage}
        expected_stages = set(_PIPELINE_STAGES_DEFAULT)

        for stage_name in stages:
            if stage_name not in valid_stages:
                continue

            ps = PipelineStage(stage_name)
            stage_analysis = PipelineStageAnalysis(stage=ps)

            if ps == PipelineStage.BUILD:
                stage_analysis.estimated_duration_minutes = 5
                stage_analysis.has_automated_tests = False
                stage_analysis.has_approval_gate = False
                stage_analysis.has_rollback_mechanism = False
                stage_analysis.risk_score = 10.0
            elif ps == PipelineStage.TEST:
                stage_analysis.estimated_duration_minutes = 15
                stage_analysis.has_automated_tests = True
                stage_analysis.has_approval_gate = False
                stage_analysis.has_rollback_mechanism = False
                stage_analysis.risk_score = 20.0
            elif ps == PipelineStage.STAGE:
                stage_analysis.estimated_duration_minutes = 10
                stage_analysis.has_automated_tests = True
                stage_analysis.has_approval_gate = True
                stage_analysis.has_rollback_mechanism = True
                stage_analysis.risk_score = 35.0
                stage_analysis.recommendations.append(
                    "Run integration tests against staging environment"
                )
            elif ps == PipelineStage.PROD:
                stage_analysis.estimated_duration_minutes = 20
                stage_analysis.has_automated_tests = True
                stage_analysis.has_approval_gate = True
                stage_analysis.has_rollback_mechanism = True
                stage_analysis.risk_score = 60.0
                stage_analysis.recommendations.append(
                    "Require manual approval before production deployment"
                )

            analysis.stages.append(stage_analysis)

        analysis.total_duration_minutes = sum(
            s.estimated_duration_minutes for s in analysis.stages
        )

        present_stage_names = {s.stage.value for s in analysis.stages}
        analysis.missing_stages = [
            s for s in expected_stages if s not in present_stage_names
        ]

        analysis.has_full_automation = all(
            s.has_automated_tests for s in analysis.stages
        )

        if analysis.missing_stages:
            analysis.overall_risk = DeploymentRisk.HIGH
            analysis.recommendations.append(
                f"Missing pipeline stages: {', '.join(sorted(analysis.missing_stages))}"
            )
        elif not analysis.has_full_automation:
            analysis.overall_risk = DeploymentRisk.MODERATE
            analysis.recommendations.append(
                "Not all stages have automated tests"
            )
        else:
            analysis.overall_risk = DeploymentRisk.LOW

        # Check for approval gates
        has_any_gate = any(s.has_approval_gate for s in analysis.stages)
        if not has_any_gate:
            analysis.recommendations.append(
                "No approval gates in pipeline — add at least one before production"
            )

        return analysis

    # ------------------------------------------------------------------
    # Internal Scoring
    # ------------------------------------------------------------------

    def _compute_overall_score(self, report: StrategyAnalysisReport) -> float:
        """Compute a composite 0-100 score for the deployment strategy."""
        score = 50.0  # baseline

        # Rollback contribution (up to +20)
        if report.rollback:
            safety_scores = {
                RollbackSafety.INSTANT: 20.0,
                RollbackSafety.FAST: 15.0,
                RollbackSafety.MODERATE: 8.0,
                RollbackSafety.SLOW: 3.0,
                RollbackSafety.DANGEROUS: -10.0,
            }
            score += safety_scores.get(report.rollback.safety, 0.0)

        # Zero-downtime contribution (up to +15)
        if report.zero_downtime:
            if report.zero_downtime.is_zero_downtime:
                score += 15.0 * report.zero_downtime.confidence
            else:
                score -= 10.0

        # Health check contribution (up to +10)
        if report.health_checks:
            adequacy_scores = {
                HealthCheckAdequacy.EXCELLENT: 10.0,
                HealthCheckAdequacy.ADEQUATE: 6.0,
                HealthCheckAdequacy.INSUFFICIENT: 2.0,
                HealthCheckAdequacy.MISSING: -5.0,
            }
            hc_avg = sum(
                adequacy_scores.get(hc.adequacy, 0.0)
                for hc in report.health_checks
            ) / len(report.health_checks)
            score += hc_avg

        # Velocity-risk composite (up to +10)
        if report.velocity_risk:
            vr_contrib = (report.velocity_risk.composite_score - 50.0) / 5.0
            score += max(-10.0, min(10.0, vr_contrib))

        # DB migration penalty (up to -15)
        if report.db_migrations:
            compat_penalties = {
                DbMigrationCompat.FULLY_COMPATIBLE: 0.0,
                DbMigrationCompat.COMPATIBLE_WITH_CAUTION: -3.0,
                DbMigrationCompat.REQUIRES_DUAL_WRITE: -8.0,
                DbMigrationCompat.INCOMPATIBLE: -15.0,
            }
            worst = min(
                compat_penalties.get(m.compatibility, 0.0)
                for m in report.db_migrations
            )
            score += worst

        # Feature flag bonus (up to +10)
        if report.feature_flags and report.feature_flags.has_feature_flags:
            score += report.feature_flags.risk_reduction_percent / 5.0

        # Pipeline penalty
        if report.pipeline:
            if report.pipeline.overall_risk == DeploymentRisk.HIGH:
                score -= 10.0
            elif report.pipeline.overall_risk == DeploymentRisk.MODERATE:
                score -= 3.0

        return max(0.0, min(100.0, score))

    def _classify_risk(self, score: float) -> DeploymentRisk:
        """Classify overall risk from composite score."""
        if score >= 75:
            return DeploymentRisk.LOW
        if score >= 50:
            return DeploymentRisk.MODERATE
        if score >= 25:
            return DeploymentRisk.HIGH
        return DeploymentRisk.CRITICAL

    def _gather_recommendations(
        self, report: StrategyAnalysisReport,
    ) -> list[str]:
        """Gather and deduplicate all recommendations from sub-analyses."""
        recs: list[str] = []

        if report.rollback and report.rollback.warnings:
            recs.extend(report.rollback.warnings)

        if report.canary:
            recs.extend(report.canary.recommendations)

        if report.cost and report.cost.notes:
            recs.extend(report.cost.notes)

        if report.velocity_risk and report.velocity_risk.recommendation:
            recs.append(report.velocity_risk.recommendation)

        for hc in report.health_checks:
            recs.extend(hc.recommendations)

        for db in report.db_migrations:
            recs.extend(db.recommendations)

        if report.region_plan:
            recs.extend(report.region_plan.recommendations)

        if report.window:
            recs.extend(report.window.notes)

        if report.feature_flags:
            recs.extend(report.feature_flags.recommendations)

        if report.zero_downtime:
            recs.extend(report.zero_downtime.mitigations)

        if report.pipeline:
            recs.extend(report.pipeline.recommendations)

        # Deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for r in recs:
            if r not in seen:
                seen.add(r)
                unique.append(r)

        return unique

    # ------------------------------------------------------------------
    # Convenience: compare strategies
    # ------------------------------------------------------------------

    def compare_strategies(
        self,
        strategies: list[StrategyType] | None = None,
        **kwargs,
    ) -> list[StrategyAnalysisReport]:
        """Compare multiple deployment strategies and return sorted reports.

        Returns reports sorted by overall_score descending (best first).
        """
        if strategies is None:
            strategies = list(StrategyType)

        reports = [self.analyze(s, **kwargs) for s in strategies]
        reports.sort(key=lambda r: r.overall_score, reverse=True)
        return reports

    def best_strategy(self, **kwargs) -> StrategyAnalysisReport:
        """Return the analysis report for the best strategy."""
        reports = self.compare_strategies(**kwargs)
        return reports[0]
