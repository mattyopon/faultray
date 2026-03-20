# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Infrastructure Migration Risk Analyzer.

Analyzes risks associated with infrastructure migrations (cloud-to-cloud,
on-prem-to-cloud, version upgrades, database migrations, etc.). Assesses
compatibility gaps, data loss risk, downtime windows, rollback complexity,
and generates migration risk scores with mitigation strategies.

All models use Pydantic v2 BaseModel.
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


class MigrationType(str, Enum):
    """Strategy / approach for the migration."""

    LIFT_AND_SHIFT = "lift_and_shift"
    REPLATFORM = "replatform"
    REFACTOR = "refactor"
    REPURCHASE = "repurchase"
    RETAIN = "retain"
    RETIRE = "retire"
    HYBRID = "hybrid"


class MigrationPhase(str, Enum):
    """Lifecycle phases of a migration."""

    ASSESSMENT = "assessment"
    PLANNING = "planning"
    EXECUTION = "execution"
    VALIDATION = "validation"
    CUTOVER = "cutover"
    ROLLBACK = "rollback"


class RiskCategory(str, Enum):
    """Categories of migration risk."""

    DATA_LOSS = "data_loss"
    DOWNTIME = "downtime"
    COMPATIBILITY = "compatibility"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    SECURITY_GAP = "security_gap"
    COST_OVERRUN = "cost_overrun"
    SKILL_GAP = "skill_gap"
    VENDOR_LOCK_IN = "vendor_lock_in"
    COMPLIANCE_VIOLATION = "compliance_violation"
    INTEGRATION_FAILURE = "integration_failure"


class MigrationComplexity(str, Enum):
    """Overall complexity classification."""

    TRIVIAL = "trivial"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"


# ---------------------------------------------------------------------------
# Internal weight tables
# ---------------------------------------------------------------------------

_MIGRATION_TYPE_BASE_RISK: dict[MigrationType, float] = {
    MigrationType.LIFT_AND_SHIFT: 0.25,
    MigrationType.REPLATFORM: 0.45,
    MigrationType.REFACTOR: 0.75,
    MigrationType.REPURCHASE: 0.55,
    MigrationType.RETAIN: 0.05,
    MigrationType.RETIRE: 0.10,
    MigrationType.HYBRID: 0.60,
}

_MIGRATION_TYPE_VENDOR_LOCK_IN: dict[MigrationType, float] = {
    MigrationType.LIFT_AND_SHIFT: 0.70,
    MigrationType.REPLATFORM: 0.55,
    MigrationType.REFACTOR: 0.20,
    MigrationType.REPURCHASE: 0.80,
    MigrationType.RETAIN: 0.90,
    MigrationType.RETIRE: 0.00,
    MigrationType.HYBRID: 0.45,
}

_MIGRATION_TYPE_COMPLEXITY_HOURS: dict[MigrationType, float] = {
    MigrationType.LIFT_AND_SHIFT: 8.0,
    MigrationType.REPLATFORM: 24.0,
    MigrationType.REFACTOR: 80.0,
    MigrationType.REPURCHASE: 40.0,
    MigrationType.RETAIN: 2.0,
    MigrationType.RETIRE: 4.0,
    MigrationType.HYBRID: 60.0,
}

_COMPONENT_TYPE_DATA_RISK: dict[ComponentType, float] = {
    ComponentType.DATABASE: 0.85,
    ComponentType.STORAGE: 0.70,
    ComponentType.CACHE: 0.40,
    ComponentType.QUEUE: 0.50,
    ComponentType.APP_SERVER: 0.15,
    ComponentType.WEB_SERVER: 0.10,
    ComponentType.LOAD_BALANCER: 0.05,
    ComponentType.DNS: 0.05,
    ComponentType.EXTERNAL_API: 0.20,
    ComponentType.CUSTOM: 0.30,
    ComponentType.AI_AGENT: 0.25,
    ComponentType.LLM_ENDPOINT: 0.15,
    ComponentType.TOOL_SERVICE: 0.20,
    ComponentType.AGENT_ORCHESTRATOR: 0.35,
}

_COMPONENT_TYPE_DOWNTIME_MINUTES: dict[ComponentType, float] = {
    ComponentType.DATABASE: 60.0,
    ComponentType.STORAGE: 45.0,
    ComponentType.CACHE: 15.0,
    ComponentType.QUEUE: 30.0,
    ComponentType.APP_SERVER: 20.0,
    ComponentType.WEB_SERVER: 10.0,
    ComponentType.LOAD_BALANCER: 25.0,
    ComponentType.DNS: 35.0,
    ComponentType.EXTERNAL_API: 5.0,
    ComponentType.CUSTOM: 20.0,
    ComponentType.AI_AGENT: 15.0,
    ComponentType.LLM_ENDPOINT: 10.0,
    ComponentType.TOOL_SERVICE: 15.0,
    ComponentType.AGENT_ORCHESTRATOR: 25.0,
}

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class MigrationTarget(BaseModel):
    """Describes the source, target, and scope of a migration."""

    source_platform: str
    target_platform: str
    migration_type: MigrationType
    components: list[str] = Field(default_factory=list)


class CompatibilityGap(BaseModel):
    """A single compatibility gap found during evaluation."""

    component_id: str
    gap_type: str
    severity: float = Field(ge=0.0, le=1.0)
    description: str
    remediation: str


class DataMigrationRisk(BaseModel):
    """Risk profile for data being migrated."""

    data_volume_gb: float = 0.0
    estimated_duration_hours: float = 0.0
    data_loss_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    validation_strategy: str = "checksum"


class DowntimeEstimate(BaseModel):
    """Estimated downtime for the migration."""

    planned_minutes: float = 0.0
    worst_case_minutes: float = 0.0
    zero_downtime_possible: bool = False
    strategy: str = "blue_green"


class RollbackPlan(BaseModel):
    """Plan for reverting a migration."""

    rollback_complexity: MigrationComplexity = MigrationComplexity.MODERATE
    estimated_rollback_minutes: float = 0.0
    data_sync_strategy: str = "snapshot_restore"
    point_of_no_return_step: int = 0


class MigrationRiskAssessment(BaseModel):
    """Complete risk assessment for a migration."""

    overall_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_breakdown: dict[str, float] = Field(default_factory=dict)
    compatibility_gaps: list[CompatibilityGap] = Field(default_factory=list)
    data_risk: DataMigrationRisk = Field(default_factory=DataMigrationRisk)
    downtime_estimate: DowntimeEstimate = Field(default_factory=DowntimeEstimate)
    rollback_plan: RollbackPlan = Field(default_factory=RollbackPlan)
    recommendations: list[str] = Field(default_factory=list)
    estimated_total_hours: float = 0.0
    go_no_go_recommendation: str = "go"
    migration_complexity: MigrationComplexity = MigrationComplexity.MODERATE
    assessed_at: str = ""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class MigrationRiskEngine:
    """Stateless engine for assessing infrastructure migration risks.

    All public methods accept an :class:`InfraGraph` (and sometimes a
    :class:`MigrationTarget`) and return pure data-model results.
    """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _component_data_risk(comp: Component) -> float:
        return _COMPONENT_TYPE_DATA_RISK.get(comp.type, 0.30)

    @staticmethod
    def _component_downtime_minutes(comp: Component) -> float:
        return _COMPONENT_TYPE_DOWNTIME_MINUTES.get(comp.type, 20.0)

    @staticmethod
    def _classify_complexity(score: float) -> MigrationComplexity:
        if score < 0.10:
            return MigrationComplexity.TRIVIAL
        if score < 0.30:
            return MigrationComplexity.LOW
        if score < 0.55:
            return MigrationComplexity.MODERATE
        if score < 0.80:
            return MigrationComplexity.HIGH
        return MigrationComplexity.EXTREME

    @staticmethod
    def _has_data_components(graph: InfraGraph) -> bool:
        for comp in graph.components.values():
            if comp.type in (
                ComponentType.DATABASE,
                ComponentType.STORAGE,
                ComponentType.CACHE,
            ):
                return True
        return False

    @staticmethod
    def _count_databases(graph: InfraGraph) -> int:
        return sum(
            1
            for c in graph.components.values()
            if c.type == ComponentType.DATABASE
        )

    @staticmethod
    def _resolve_components(
        graph: InfraGraph, target: MigrationTarget
    ) -> list[Component]:
        """Return the list of components in scope for the migration."""
        if target.components:
            return [
                graph.components[cid]
                for cid in target.components
                if cid in graph.components
            ]
        return list(graph.components.values())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess_migration(
        self,
        graph: InfraGraph,
        migration_target: MigrationTarget,
    ) -> MigrationRiskAssessment:
        """Produce a full risk assessment for a proposed migration."""
        comps = self._resolve_components(graph, migration_target)
        comp_count = len(comps)
        mtype = migration_target.migration_type

        # If graph/scope is empty, return minimal assessment
        if comp_count == 0:
            return MigrationRiskAssessment(
                overall_risk_score=0.0,
                risk_breakdown={cat.value: 0.0 for cat in RiskCategory},
                go_no_go_recommendation="go",
                migration_complexity=MigrationComplexity.TRIVIAL,
                assessed_at=datetime.now(timezone.utc).isoformat(),
            )

        # Individual risk dimensions (0.0-1.0 each)
        base_risk = _MIGRATION_TYPE_BASE_RISK.get(mtype, 0.50)
        vendor_lock_in_risk = _MIGRATION_TYPE_VENDOR_LOCK_IN.get(mtype, 0.50)

        # Component count factor – more components ⇒ higher risk
        count_factor = min(1.0, math.log2(comp_count + 1) / 5.0)

        # Database presence increases data-loss risk
        db_count = self._count_databases(graph)
        data_loss_risk = min(1.0, 0.1 + db_count * 0.15 + count_factor * 0.2)

        # Downtime risk scales with component count and type complexity
        downtime_risk = min(
            1.0, base_risk * 0.4 + count_factor * 0.4 + (0.2 if db_count > 0 else 0.0)
        )

        # Compatibility risk depends on migration type
        compat_risk = min(1.0, base_risk * 0.8 + count_factor * 0.2)

        # Performance degradation
        perf_risk = min(1.0, base_risk * 0.5 + count_factor * 0.3)

        # Security gaps
        security_risk = min(1.0, base_risk * 0.3 + count_factor * 0.15)

        # Cost overrun
        cost_risk = min(1.0, base_risk * 0.4 + count_factor * 0.25)

        # Skill gap
        skill_risk = min(1.0, base_risk * 0.6)

        # Compliance violation
        compliance_risk = min(1.0, base_risk * 0.35 + (0.15 if db_count > 0 else 0.0))

        # Integration failure
        integration_risk = min(1.0, base_risk * 0.5 + count_factor * 0.3)

        risk_breakdown: dict[str, float] = {
            RiskCategory.DATA_LOSS.value: round(data_loss_risk, 4),
            RiskCategory.DOWNTIME.value: round(downtime_risk, 4),
            RiskCategory.COMPATIBILITY.value: round(compat_risk, 4),
            RiskCategory.PERFORMANCE_DEGRADATION.value: round(perf_risk, 4),
            RiskCategory.SECURITY_GAP.value: round(security_risk, 4),
            RiskCategory.COST_OVERRUN.value: round(cost_risk, 4),
            RiskCategory.SKILL_GAP.value: round(skill_risk, 4),
            RiskCategory.VENDOR_LOCK_IN.value: round(vendor_lock_in_risk, 4),
            RiskCategory.COMPLIANCE_VIOLATION.value: round(compliance_risk, 4),
            RiskCategory.INTEGRATION_FAILURE.value: round(integration_risk, 4),
        }

        overall = sum(risk_breakdown.values()) / len(risk_breakdown)
        overall = round(min(1.0, max(0.0, overall)), 4)

        # Sub-assessments
        gaps = self.evaluate_compatibility(
            graph, migration_target.source_platform, migration_target.target_platform
        )
        downtime_est = self.estimate_downtime(graph, mtype, comp_count)
        rollback = self.plan_rollback(graph, migration_target)
        data_risk = self.calculate_data_risk(graph, 0.0)  # no external volume hint

        # Estimated total hours
        base_hours = _MIGRATION_TYPE_COMPLEXITY_HOURS.get(mtype, 40.0)
        estimated_hours = base_hours * max(1, comp_count)

        # Recommendations
        recommendations = self._build_recommendations(
            mtype, risk_breakdown, comp_count, db_count
        )

        complexity = self._classify_complexity(overall)
        go_no_go = "go" if overall < 0.55 else "no_go"

        return MigrationRiskAssessment(
            overall_risk_score=overall,
            risk_breakdown=risk_breakdown,
            compatibility_gaps=gaps,
            data_risk=data_risk,
            downtime_estimate=downtime_est,
            rollback_plan=rollback,
            recommendations=recommendations,
            estimated_total_hours=estimated_hours,
            go_no_go_recommendation=go_no_go,
            migration_complexity=complexity,
            assessed_at=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------

    def evaluate_compatibility(
        self,
        graph: InfraGraph,
        source: str,
        target: str,
    ) -> list[CompatibilityGap]:
        """Find compatibility gaps between source and target platforms."""
        gaps: list[CompatibilityGap] = []

        if source == target:
            return gaps

        for comp in graph.components.values():
            # Database components always have compatibility concerns
            if comp.type == ComponentType.DATABASE:
                gaps.append(
                    CompatibilityGap(
                        component_id=comp.id,
                        gap_type="database_engine",
                        severity=0.8,
                        description=(
                            f"Database '{comp.name}' may use engine-specific "
                            f"features incompatible with {target}"
                        ),
                        remediation="Audit SQL dialect and stored procedures for portability",
                    )
                )
            # Cache components have serialization concerns
            if comp.type == ComponentType.CACHE:
                gaps.append(
                    CompatibilityGap(
                        component_id=comp.id,
                        gap_type="cache_protocol",
                        severity=0.4,
                        description=(
                            f"Cache '{comp.name}' may use protocol features "
                            f"unavailable on {target}"
                        ),
                        remediation="Verify cache client compatibility and serialization format",
                    )
                )
            # Queue components
            if comp.type == ComponentType.QUEUE:
                gaps.append(
                    CompatibilityGap(
                        component_id=comp.id,
                        gap_type="message_format",
                        severity=0.5,
                        description=(
                            f"Queue '{comp.name}' message format may differ on {target}"
                        ),
                        remediation="Use platform-agnostic message serialization (e.g. JSON/Protobuf)",
                    )
                )
            # DNS components
            if comp.type == ComponentType.DNS:
                gaps.append(
                    CompatibilityGap(
                        component_id=comp.id,
                        gap_type="dns_provider",
                        severity=0.6,
                        description=(
                            f"DNS '{comp.name}' records and routing policies "
                            f"need reconfiguration on {target}"
                        ),
                        remediation="Export DNS zone files and validate record compatibility",
                    )
                )
            # External API – dependency may change endpoints
            if comp.type == ComponentType.EXTERNAL_API:
                gaps.append(
                    CompatibilityGap(
                        component_id=comp.id,
                        gap_type="api_endpoint",
                        severity=0.3,
                        description=(
                            f"External API '{comp.name}' endpoint connectivity "
                            f"may differ from {target}"
                        ),
                        remediation="Verify network egress rules and API endpoint accessibility",
                    )
                )
            # Storage components
            if comp.type == ComponentType.STORAGE:
                gaps.append(
                    CompatibilityGap(
                        component_id=comp.id,
                        gap_type="storage_api",
                        severity=0.65,
                        description=(
                            f"Storage '{comp.name}' API (e.g. S3/GCS/Blob) "
                            f"differs on {target}"
                        ),
                        remediation="Use abstraction layer (e.g. Apache libcloud) or rewrite storage calls",
                    )
                )
            # Load balancer – health check configs differ
            if comp.type == ComponentType.LOAD_BALANCER:
                gaps.append(
                    CompatibilityGap(
                        component_id=comp.id,
                        gap_type="lb_config",
                        severity=0.35,
                        description=(
                            f"Load balancer '{comp.name}' health check and "
                            f"routing configuration differs on {target}"
                        ),
                        remediation="Re-create health checks, listener rules, and target groups on target platform",
                    )
                )
            # Replicas < 2 and no failover – risky during migration
            if comp.replicas < 2 and not comp.failover.enabled:
                gaps.append(
                    CompatibilityGap(
                        component_id=comp.id,
                        gap_type="no_redundancy",
                        severity=0.7,
                        description=(
                            f"Component '{comp.name}' has no redundancy; "
                            f"migration will cause downtime"
                        ),
                        remediation="Add replicas or enable failover before migration",
                    )
                )

        return gaps

    # ------------------------------------------------------------------

    def estimate_downtime(
        self,
        graph: InfraGraph,
        migration_type: MigrationType,
        component_count: int,
    ) -> DowntimeEstimate:
        """Estimate downtime for a migration."""
        if component_count == 0:
            return DowntimeEstimate(
                planned_minutes=0.0,
                worst_case_minutes=0.0,
                zero_downtime_possible=True,
                strategy="none",
            )

        # Base downtime per component type
        total_base = 0.0
        for comp in graph.components.values():
            total_base += self._component_downtime_minutes(comp)

        # Migration-type multiplier
        type_multipliers: dict[MigrationType, float] = {
            MigrationType.LIFT_AND_SHIFT: 0.6,
            MigrationType.REPLATFORM: 1.0,
            MigrationType.REFACTOR: 1.5,
            MigrationType.REPURCHASE: 1.2,
            MigrationType.RETAIN: 0.1,
            MigrationType.RETIRE: 0.2,
            MigrationType.HYBRID: 1.3,
        }
        multiplier = type_multipliers.get(migration_type, 1.0)

        planned = total_base * multiplier
        worst_case = planned * 2.5

        # Zero downtime only possible with few components and simple migration
        zero_dt = (
            component_count <= 2
            and migration_type
            in (MigrationType.LIFT_AND_SHIFT, MigrationType.RETAIN, MigrationType.RETIRE)
        )

        # Strategy selection
        if migration_type == MigrationType.LIFT_AND_SHIFT:
            strategy = "blue_green"
        elif migration_type == MigrationType.REFACTOR:
            strategy = "strangler_fig"
        elif migration_type == MigrationType.RETIRE:
            strategy = "decommission"
        elif migration_type == MigrationType.RETAIN:
            strategy = "none"
        else:
            strategy = "rolling"

        return DowntimeEstimate(
            planned_minutes=round(planned, 2),
            worst_case_minutes=round(worst_case, 2),
            zero_downtime_possible=zero_dt,
            strategy=strategy,
        )

    # ------------------------------------------------------------------

    def plan_rollback(
        self,
        graph: InfraGraph,
        migration_target: MigrationTarget,
    ) -> RollbackPlan:
        """Generate a rollback plan for the migration."""
        comps = self._resolve_components(graph, migration_target)
        comp_count = len(comps)
        mtype = migration_target.migration_type

        if comp_count == 0:
            return RollbackPlan(
                rollback_complexity=MigrationComplexity.TRIVIAL,
                estimated_rollback_minutes=0.0,
                data_sync_strategy="none",
                point_of_no_return_step=0,
            )

        # Rollback complexity by migration type
        rollback_complexity_map: dict[MigrationType, MigrationComplexity] = {
            MigrationType.LIFT_AND_SHIFT: MigrationComplexity.LOW,
            MigrationType.REPLATFORM: MigrationComplexity.MODERATE,
            MigrationType.REFACTOR: MigrationComplexity.EXTREME,
            MigrationType.REPURCHASE: MigrationComplexity.HIGH,
            MigrationType.RETAIN: MigrationComplexity.TRIVIAL,
            MigrationType.RETIRE: MigrationComplexity.HIGH,
            MigrationType.HYBRID: MigrationComplexity.HIGH,
        }
        complexity = rollback_complexity_map.get(mtype, MigrationComplexity.MODERATE)

        # Rollback time estimation
        complexity_minutes: dict[MigrationComplexity, float] = {
            MigrationComplexity.TRIVIAL: 5.0,
            MigrationComplexity.LOW: 15.0,
            MigrationComplexity.MODERATE: 45.0,
            MigrationComplexity.HIGH: 120.0,
            MigrationComplexity.EXTREME: 360.0,
        }
        base_minutes = complexity_minutes.get(complexity, 45.0)
        estimated_minutes = base_minutes * max(1, comp_count)

        # Data sync strategy
        db_count = sum(1 for c in comps if c.type == ComponentType.DATABASE)
        if db_count > 0:
            data_sync = "snapshot_restore"
        elif any(c.type == ComponentType.STORAGE for c in comps):
            data_sync = "rsync"
        else:
            data_sync = "none"

        # Point of no return step (databases push it earlier)
        ponr = max(1, 3 - db_count)
        if mtype == MigrationType.REFACTOR:
            ponr = 1  # refactor is hard to roll back after first step

        return RollbackPlan(
            rollback_complexity=complexity,
            estimated_rollback_minutes=round(estimated_minutes, 2),
            data_sync_strategy=data_sync,
            point_of_no_return_step=ponr,
        )

    # ------------------------------------------------------------------

    def calculate_data_risk(
        self,
        graph: InfraGraph,
        data_volume_gb: float,
    ) -> DataMigrationRisk:
        """Assess risk to data during migration."""
        if not graph.components:
            return DataMigrationRisk(
                data_volume_gb=data_volume_gb,
                estimated_duration_hours=0.0,
                data_loss_probability=0.0,
                validation_strategy="none",
            )

        db_count = self._count_databases(graph)
        has_data = self._has_data_components(graph)

        # Estimate data volume from component metrics if not provided
        effective_volume = data_volume_gb
        if effective_volume <= 0.0:
            for comp in graph.components.values():
                effective_volume += comp.metrics.disk_used_gb

        # Duration estimate: ~50 GB/hour for databases, faster for other storage
        if effective_volume > 0:
            hours = effective_volume / 50.0
        else:
            hours = 0.5 * db_count if db_count > 0 else 0.0

        # Data loss probability
        if db_count > 0:
            loss_prob = min(1.0, 0.05 + db_count * 0.08)
        elif has_data:
            loss_prob = 0.02
        else:
            loss_prob = 0.0

        # Validation strategy
        if db_count > 0:
            strategy = "row_count_and_checksum"
        elif has_data:
            strategy = "checksum"
        else:
            strategy = "smoke_test"

        return DataMigrationRisk(
            data_volume_gb=round(effective_volume, 2),
            estimated_duration_hours=round(hours, 2),
            data_loss_probability=round(loss_prob, 4),
            validation_strategy=strategy,
        )

    # ------------------------------------------------------------------

    def generate_migration_waves(
        self,
        graph: InfraGraph,
        migration_target: MigrationTarget,
    ) -> list[dict]:
        """Split components into dependency-ordered migration waves.

        Returns a list of wave dicts, each containing:
        - ``wave``: wave number (1-based)
        - ``components``: list of component IDs in this wave
        - ``description``: human-readable description
        """
        comps = self._resolve_components(graph, migration_target)
        if not comps:
            return []

        # Build a dependency map for the in-scope components
        comp_ids = {c.id for c in comps}
        # Map component_id -> set of component_ids it depends on (within scope)
        dep_map: dict[str, set[str]] = {cid: set() for cid in comp_ids}
        for comp in comps:
            for dep in graph.get_dependencies(comp.id):
                if dep.id in comp_ids:
                    dep_map[comp.id].add(dep.id)

        # Topological layering (Kahn's algorithm variant)
        waves: list[dict] = []
        remaining = dict(dep_map)
        wave_num = 0
        placed: set[str] = set()

        while remaining:
            wave_num += 1
            # Find all components whose dependencies have been placed
            ready = [
                cid
                for cid, deps in remaining.items()
                if deps.issubset(placed)
            ]
            if not ready:
                # Cycle detected – break it by taking all remaining
                ready = list(remaining.keys())

            ready.sort()  # deterministic ordering
            for cid in ready:
                del remaining[cid]
            placed.update(ready)

            # Classify the wave
            comp_types = [
                graph.components[cid].type.value
                for cid in ready
                if cid in graph.components
            ]
            unique_types = sorted(set(comp_types))
            description = (
                f"Wave {wave_num}: migrate {', '.join(unique_types)} "
                f"({len(ready)} component{'s' if len(ready) != 1 else ''})"
            )

            waves.append(
                {
                    "wave": wave_num,
                    "components": ready,
                    "description": description,
                }
            )

        return waves

    # ------------------------------------------------------------------
    # Recommendation builder
    # ------------------------------------------------------------------

    def _build_recommendations(
        self,
        mtype: MigrationType,
        risk_breakdown: dict[str, float],
        comp_count: int,
        db_count: int,
    ) -> list[str]:
        recs: list[str] = []

        data_loss = risk_breakdown.get(RiskCategory.DATA_LOSS.value, 0.0)
        downtime = risk_breakdown.get(RiskCategory.DOWNTIME.value, 0.0)
        vendor = risk_breakdown.get(RiskCategory.VENDOR_LOCK_IN.value, 0.0)
        compat = risk_breakdown.get(RiskCategory.COMPATIBILITY.value, 0.0)
        security = risk_breakdown.get(RiskCategory.SECURITY_GAP.value, 0.0)
        cost = risk_breakdown.get(RiskCategory.COST_OVERRUN.value, 0.0)
        skill = risk_breakdown.get(RiskCategory.SKILL_GAP.value, 0.0)
        compliance = risk_breakdown.get(RiskCategory.COMPLIANCE_VIOLATION.value, 0.0)
        integration = risk_breakdown.get(RiskCategory.INTEGRATION_FAILURE.value, 0.0)
        perf = risk_breakdown.get(RiskCategory.PERFORMANCE_DEGRADATION.value, 0.0)

        if data_loss > 0.4:
            recs.append("Implement comprehensive backup and validation before migration")
        if downtime > 0.5:
            recs.append("Consider blue-green or canary deployment to minimize downtime")
        if vendor > 0.6:
            recs.append("Adopt cloud-agnostic abstractions to reduce vendor lock-in")
        if compat > 0.5:
            recs.append("Run compatibility tests against target platform before cutover")
        if security > 0.3:
            recs.append("Perform security audit on target platform configuration")
        if cost > 0.4:
            recs.append("Set up cost monitoring and alerts on target platform")
        if skill > 0.5:
            recs.append("Provide team training for target platform technologies")
        if compliance > 0.3:
            recs.append("Verify compliance requirements are met on target platform")
        if integration > 0.4:
            recs.append("Test all integration points in staging environment first")
        if perf > 0.4:
            recs.append("Benchmark application performance on target platform")

        if db_count > 0:
            recs.append("Create database snapshots before each migration phase")
        if comp_count > 5:
            recs.append("Split migration into multiple waves to reduce blast radius")

        if mtype == MigrationType.LIFT_AND_SHIFT:
            recs.append("Plan for post-migration optimization as lift-and-shift defers modernization")
        elif mtype == MigrationType.REFACTOR:
            recs.append("Ensure adequate test coverage before refactoring components")
        elif mtype == MigrationType.HYBRID:
            recs.append("Define clear boundaries between migrated and retained components")

        return recs
