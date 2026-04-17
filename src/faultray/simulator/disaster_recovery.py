# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Disaster Recovery Simulator - validate DR plans and simulate recovery scenarios.

Provides comprehensive disaster recovery simulation including failover,
failback, RPO/RTO estimation, gap analysis, strategy comparison, and cost
estimation.  All models use Pydantic v2 BaseModel.
"""

from __future__ import annotations

import logging
import math
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DisasterType(str, Enum):
    """Types of disasters that can be simulated."""

    REGION_OUTAGE = "region_outage"
    DATA_CENTER_FAILURE = "data_center_failure"
    CLOUD_PROVIDER_OUTAGE = "cloud_provider_outage"
    RANSOMWARE = "ransomware"
    NATURAL_DISASTER = "natural_disaster"
    POWER_OUTAGE = "power_outage"
    NETWORK_BACKBONE_FAILURE = "network_backbone_failure"
    DNS_HIJACK = "dns_hijack"


class DRStrategy(str, Enum):
    """Disaster recovery strategies ordered by cost / recovery speed."""

    PILOT_LIGHT = "pilot_light"
    WARM_STANDBY = "warm_standby"
    MULTI_SITE_ACTIVE = "multi_site_active"
    BACKUP_RESTORE = "backup_restore"
    COLD_STANDBY = "cold_standby"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class DRPlan(BaseModel):
    """A disaster recovery plan definition."""

    strategy: DRStrategy
    primary_region: str
    dr_region: str
    rpo_target_seconds: int
    rto_target_seconds: int
    data_replication: str = "async"
    failover_automated: bool = False
    last_tested: str = ""
    runbook_id: str = ""


class DRSimulationResult(BaseModel):
    """Result of simulating a specific disaster against a DR plan."""

    disaster_type: DisasterType
    actual_rpo_seconds: int
    actual_rto_seconds: int
    rpo_met: bool
    rto_met: bool
    data_loss_estimate_gb: float = 0.0
    affected_services: list[str] = Field(default_factory=list)
    recovery_steps: list[str] = Field(default_factory=list)
    cost_estimate: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class DRPlanValidation(BaseModel):
    """Validation result for a DR plan against an infrastructure graph."""

    is_valid: bool
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    coverage_percent: float = 0.0
    unprotected_components: list[str] = Field(default_factory=list)


class RPORTOEstimate(BaseModel):
    """Estimated RPO and RTO for a given plan and infrastructure."""

    estimated_rpo_seconds: int = 0
    estimated_rto_seconds: int = 0
    rpo_breakdown: dict[str, int] = Field(default_factory=dict)
    rto_breakdown: dict[str, int] = Field(default_factory=dict)
    bottleneck_component: str = ""


class DRGap(BaseModel):
    """A single gap in a DR plan."""

    component_id: str
    gap_type: str
    severity: str  # critical, high, medium, low
    description: str
    recommendation: str


class StrategyComparison(BaseModel):
    """Comparison of a DR strategy against the infrastructure."""

    strategy: DRStrategy
    estimated_rpo_seconds: int
    estimated_rto_seconds: int
    estimated_monthly_cost: float
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    score: float = 0.0


class DRCostEstimate(BaseModel):
    """Cost estimate for implementing and maintaining a DR plan."""

    monthly_infrastructure_cost: float = 0.0
    monthly_replication_cost: float = 0.0
    monthly_storage_cost: float = 0.0
    annual_testing_cost: float = 0.0
    total_monthly_cost: float = 0.0
    cost_per_component: dict[str, float] = Field(default_factory=dict)


class FailbackResult(BaseModel):
    """Result of simulating a failback to the primary region."""

    estimated_failback_time_seconds: int = 0
    data_sync_required_gb: float = 0.0
    steps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    can_failback_safely: bool = True


# ---------------------------------------------------------------------------
# Strategy multipliers (internal)
# ---------------------------------------------------------------------------

_STRATEGY_RTO_MULTIPLIER: dict[DRStrategy, float] = {
    DRStrategy.MULTI_SITE_ACTIVE: 0.1,
    DRStrategy.WARM_STANDBY: 0.4,
    DRStrategy.PILOT_LIGHT: 0.7,
    DRStrategy.COLD_STANDBY: 1.5,
    DRStrategy.BACKUP_RESTORE: 3.0,
}

_STRATEGY_RPO_MULTIPLIER: dict[DRStrategy, float] = {
    DRStrategy.MULTI_SITE_ACTIVE: 0.05,
    DRStrategy.WARM_STANDBY: 0.3,
    DRStrategy.PILOT_LIGHT: 0.6,
    DRStrategy.COLD_STANDBY: 1.0,
    DRStrategy.BACKUP_RESTORE: 2.0,
}

_STRATEGY_COST_MULTIPLIER: dict[DRStrategy, float] = {
    DRStrategy.MULTI_SITE_ACTIVE: 2.0,
    DRStrategy.WARM_STANDBY: 1.2,
    DRStrategy.PILOT_LIGHT: 0.6,
    DRStrategy.COLD_STANDBY: 0.3,
    DRStrategy.BACKUP_RESTORE: 0.15,
}

_DISASTER_SEVERITY: dict[DisasterType, float] = {
    DisasterType.REGION_OUTAGE: 0.9,
    DisasterType.DATA_CENTER_FAILURE: 0.7,
    DisasterType.CLOUD_PROVIDER_OUTAGE: 1.0,
    DisasterType.RANSOMWARE: 0.95,
    DisasterType.NATURAL_DISASTER: 0.85,
    DisasterType.POWER_OUTAGE: 0.6,
    DisasterType.NETWORK_BACKBONE_FAILURE: 0.75,
    DisasterType.DNS_HIJACK: 0.5,
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DisasterRecoveryEngine:
    """Engine for simulating disaster recovery scenarios.

    Operates on an :class:`InfraGraph` to evaluate DR plans, estimate
    RPO/RTO, identify gaps, compare strategies, and calculate costs.
    """

    def __init__(self, graph: InfraGraph | None = None) -> None:
        self.graph = graph or InfraGraph()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _components_in_region(self, region: str) -> list[str]:
        """Return component ids deployed in *region*."""
        result: list[str] = []
        for comp in self.graph.components.values():
            if comp.region.region == region:
                result.append(comp.id)
        return result

    def _all_regions(self) -> set[str]:
        regions: set[str] = set()
        for comp in self.graph.components.values():
            if comp.region.region:
                regions.add(comp.region.region)
        return regions

    def _component_base_rto(self, comp) -> float:
        """Return base RTO in seconds for a single component."""
        if comp.failover.enabled:
            return comp.failover.promotion_time_seconds
        mttr = comp.operational_profile.mttr_minutes
        if mttr > 0:
            return mttr * 60.0
        return 300.0

    def _component_base_rpo(self, comp) -> float:
        """Return base RPO in seconds for a single component."""
        rpo = comp.region.rpo_seconds
        if rpo > 0:
            return float(rpo)
        if comp.failover.enabled:
            return 5.0  # async replication lag estimate
        if comp.security.backup_enabled:
            return comp.security.backup_frequency_hours * 3600.0
        return 3600.0  # default: 1 hour

    def _compute_actual_rto(self, plan: DRPlan) -> int:
        """Compute actual RTO based on strategy and components."""
        components = self.graph.components
        if not components:
            return 0

        multiplier = _STRATEGY_RTO_MULTIPLIER.get(plan.strategy, 1.0)
        max_rto = 0.0
        for comp in components.values():
            base = self._component_base_rto(comp)
            adjusted = base * multiplier
            if not plan.failover_automated:
                adjusted *= 1.5  # manual failover penalty
            max_rto = max(max_rto, adjusted)

        return int(math.ceil(max_rto))

    def _compute_actual_rpo(self, plan: DRPlan) -> int:
        """Compute actual RPO based on strategy and replication."""
        components = self.graph.components
        if not components:
            return 0

        multiplier = _STRATEGY_RPO_MULTIPLIER.get(plan.strategy, 1.0)
        max_rpo = 0.0
        for comp in components.values():
            base = self._component_base_rpo(comp)
            adjusted = base * multiplier
            if plan.data_replication == "sync":
                adjusted *= 0.1  # synchronous replication dramatically reduces RPO
            max_rpo = max(max_rpo, adjusted)

        return int(math.ceil(max_rpo))

    def _affected_services_for_disaster(
        self, disaster_type: DisasterType, plan: DRPlan,
    ) -> list[str]:
        """Determine which services are affected by a disaster type."""
        severity = _DISASTER_SEVERITY.get(disaster_type, 0.5)
        primary_components = self._components_in_region(plan.primary_region)

        if severity >= 0.9:
            # Major disaster affects all primary region components
            return primary_components

        # Lesser disasters affect a fraction of components
        count = max(1, int(len(primary_components) * severity))
        return primary_components[:count]

    def _recovery_steps_for_disaster(
        self, disaster_type: DisasterType, plan: DRPlan,
    ) -> list[str]:
        """Generate recovery steps for a given disaster type and strategy."""
        steps: list[str] = []

        steps.append(f"Detect {disaster_type.value} in {plan.primary_region}")
        steps.append("Activate incident response team")

        if plan.failover_automated:
            steps.append("Automated failover triggers DNS/traffic switch")
        else:
            steps.append("Manual failover: update DNS and traffic routing")

        strategy_steps: dict[DRStrategy, list[str]] = {
            DRStrategy.MULTI_SITE_ACTIVE: [
                "Traffic already served from DR region",
                "Verify DR region health",
            ],
            DRStrategy.WARM_STANDBY: [
                "Scale up warm standby instances in DR region",
                "Promote standby databases to primary",
                "Verify data consistency",
            ],
            DRStrategy.PILOT_LIGHT: [
                "Start pilot light resources in DR region",
                "Restore latest data from replicated storage",
                "Scale out to production capacity",
            ],
            DRStrategy.COLD_STANDBY: [
                "Provision infrastructure in DR region",
                "Deploy application stack",
                "Restore data from backups",
                "Run smoke tests",
            ],
            DRStrategy.BACKUP_RESTORE: [
                "Provision new infrastructure",
                "Restore from latest backup",
                "Validate data integrity",
                "Re-deploy application",
                "Run integration tests",
            ],
        }
        steps.extend(strategy_steps.get(plan.strategy, []))

        if disaster_type == DisasterType.RANSOMWARE:
            steps.insert(2, "Isolate affected systems")
            steps.append("Scan DR environment for ransomware artifacts")

        if disaster_type == DisasterType.DNS_HIJACK:
            steps.insert(2, "Revoke compromised DNS credentials")
            steps.append("Update DNS registrar security settings")

        steps.append("Monitor DR region for stability")
        steps.append("Communicate status to stakeholders")

        return steps

    def _recommendations_for_disaster(
        self, disaster_type: DisasterType, plan: DRPlan, rpo_met: bool, rto_met: bool,
    ) -> list[str]:
        """Generate recommendations based on simulation results."""
        recs: list[str] = []

        if not rpo_met:
            recs.append(
                "Consider upgrading to synchronous replication to meet RPO target"
            )
        if not rto_met:
            if not plan.failover_automated:
                recs.append("Enable automated failover to reduce RTO")
            if plan.strategy in (DRStrategy.BACKUP_RESTORE, DRStrategy.COLD_STANDBY):
                recs.append(
                    "Consider upgrading DR strategy to warm standby or multi-site active"
                )

        if not plan.last_tested:
            recs.append("Schedule regular DR testing to validate recovery procedures")

        if not plan.runbook_id:
            recs.append("Create and maintain a DR runbook for this plan")

        # Disaster-specific recommendations
        if disaster_type == DisasterType.RANSOMWARE:
            recs.append("Implement immutable backups with air-gapped storage")
            recs.append("Enable network segmentation to limit lateral movement")
        elif disaster_type == DisasterType.DNS_HIJACK:
            recs.append("Enable DNSSEC and registry lock")
        elif disaster_type == DisasterType.CLOUD_PROVIDER_OUTAGE:
            recs.append("Consider multi-cloud deployment for provider resilience")

        return recs

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate_disaster(
        self,
        graph: InfraGraph,
        disaster_type: DisasterType,
        plan: DRPlan,
    ) -> DRSimulationResult:
        """Simulate a disaster scenario against the infrastructure.

        Parameters
        ----------
        graph:
            The infrastructure graph to simulate against.
        disaster_type:
            The type of disaster to simulate.
        plan:
            The DR plan to evaluate.

        Returns
        -------
        DRSimulationResult
            Detailed simulation result including RPO/RTO, affected services,
            recovery steps, cost, and recommendations.
        """
        self.graph = graph

        actual_rpo = self._compute_actual_rpo(plan)
        actual_rto = self._compute_actual_rto(plan)

        rpo_met = actual_rpo <= plan.rpo_target_seconds
        rto_met = actual_rto <= plan.rto_target_seconds

        affected = self._affected_services_for_disaster(disaster_type, plan)
        steps = self._recovery_steps_for_disaster(disaster_type, plan)
        recs = self._recommendations_for_disaster(disaster_type, plan, rpo_met, rto_met)

        # Estimate data loss based on actual RPO
        severity = _DISASTER_SEVERITY.get(disaster_type, 0.5)
        data_loss_gb = actual_rpo * severity * 0.001  # rough estimate

        # Cost estimate based on RTO and affected services
        cost = len(affected) * (actual_rto / 3600.0) * 500.0  # $500/component/hour

        return DRSimulationResult(
            disaster_type=disaster_type,
            actual_rpo_seconds=actual_rpo,
            actual_rto_seconds=actual_rto,
            rpo_met=rpo_met,
            rto_met=rto_met,
            data_loss_estimate_gb=round(data_loss_gb, 3),
            affected_services=affected,
            recovery_steps=steps,
            cost_estimate=round(cost, 2),
            recommendations=recs,
        )

    def validate_dr_plan(
        self,
        graph: InfraGraph,
        plan: DRPlan,
    ) -> DRPlanValidation:
        """Validate a DR plan against an infrastructure graph.

        Checks that the plan references valid regions, that components are
        covered, and that the strategy is appropriate for the infrastructure.

        Parameters
        ----------
        graph:
            The infrastructure graph.
        plan:
            The DR plan to validate.

        Returns
        -------
        DRPlanValidation
        """
        self.graph = graph
        issues: list[str] = []
        warnings: list[str] = []
        unprotected: list[str] = []

        all_regions = self._all_regions()

        # Check primary region exists
        if plan.primary_region and plan.primary_region not in all_regions:
            issues.append(
                f"Primary region '{plan.primary_region}' not found in infrastructure"
            )

        # Check DR region exists
        if plan.dr_region and plan.dr_region not in all_regions:
            issues.append(
                f"DR region '{plan.dr_region}' not found in infrastructure"
            )

        # Check same region
        if plan.primary_region == plan.dr_region:
            issues.append("Primary and DR regions are the same")

        # Check components without failover in primary region
        primary_comps = self._components_in_region(plan.primary_region)
        for cid in primary_comps:
            comp = self.graph.get_component(cid)
            if comp and not comp.failover.enabled:
                unprotected.append(cid)

        # Coverage calculation
        total = len(self.graph.components)
        if total > 0:
            dr_region_comps = self._components_in_region(plan.dr_region)
            protected = len(dr_region_comps)
            coverage = (protected / total) * 100.0 if total > 0 else 0.0
        else:
            coverage = 0.0

        # Strategy-specific validations
        if plan.strategy == DRStrategy.MULTI_SITE_ACTIVE:
            dr_comps = self._components_in_region(plan.dr_region)
            if len(dr_comps) == 0:
                issues.append(
                    "Multi-site active strategy requires components in DR region"
                )

        if plan.strategy == DRStrategy.BACKUP_RESTORE:
            has_backup = any(
                c.security.backup_enabled
                for c in self.graph.components.values()
            )
            if not has_backup:
                issues.append(
                    "Backup/restore strategy requires at least one component "
                    "with backups enabled"
                )

        # Warnings
        if plan.data_replication == "async" and plan.rpo_target_seconds < 30:
            warnings.append(
                "RPO target < 30s is difficult to achieve with async replication"
            )

        if not plan.last_tested:
            warnings.append("DR plan has never been tested")

        if not plan.runbook_id:
            warnings.append("No runbook associated with this DR plan")

        if not plan.failover_automated:
            warnings.append(
                "Manual failover may increase RTO beyond target"
            )

        is_valid = len(issues) == 0

        return DRPlanValidation(
            is_valid=is_valid,
            issues=issues,
            warnings=warnings,
            coverage_percent=round(coverage, 1),
            unprotected_components=unprotected,
        )

    def estimate_rpo_rto(
        self,
        graph: InfraGraph,
        plan: DRPlan,
    ) -> RPORTOEstimate:
        """Estimate achievable RPO and RTO for the plan.

        Parameters
        ----------
        graph:
            The infrastructure graph.
        plan:
            The DR plan.

        Returns
        -------
        RPORTOEstimate
            Includes per-component breakdown and bottleneck identification.
        """
        self.graph = graph
        components = self.graph.components

        if not components:
            return RPORTOEstimate()

        rpo_multiplier = _STRATEGY_RPO_MULTIPLIER.get(plan.strategy, 1.0)
        rto_multiplier = _STRATEGY_RTO_MULTIPLIER.get(plan.strategy, 1.0)

        rpo_breakdown: dict[str, int] = {}
        rto_breakdown: dict[str, int] = {}
        max_rpo = 0
        max_rto = 0
        bottleneck = ""

        for cid, comp in components.items():
            base_rpo = self._component_base_rpo(comp)
            base_rto = self._component_base_rto(comp)

            adj_rpo = base_rpo * rpo_multiplier
            adj_rto = base_rto * rto_multiplier

            if plan.data_replication == "sync":
                adj_rpo *= 0.1

            if not plan.failover_automated:
                adj_rto *= 1.5

            comp_rpo = int(math.ceil(adj_rpo))
            comp_rto = int(math.ceil(adj_rto))

            rpo_breakdown[cid] = comp_rpo
            rto_breakdown[cid] = comp_rto

            total = comp_rpo + comp_rto
            if total > max_rpo + max_rto:
                bottleneck = cid

            if comp_rpo > max_rpo:
                max_rpo = comp_rpo
            if comp_rto > max_rto:
                max_rto = comp_rto

        return RPORTOEstimate(
            estimated_rpo_seconds=max_rpo,
            estimated_rto_seconds=max_rto,
            rpo_breakdown=rpo_breakdown,
            rto_breakdown=rto_breakdown,
            bottleneck_component=bottleneck,
        )

    def find_dr_gaps(
        self,
        graph: InfraGraph,
        plan: DRPlan,
    ) -> list[DRGap]:
        """Identify gaps in a DR plan.

        Parameters
        ----------
        graph:
            The infrastructure graph.
        plan:
            The DR plan to check.

        Returns
        -------
        list[DRGap]
            List of gaps found, ordered by severity.
        """
        self.graph = graph
        gaps: list[DRGap] = []

        for cid, comp in self.graph.components.items():
            # No failover configured
            if not comp.failover.enabled:
                gaps.append(DRGap(
                    component_id=cid,
                    gap_type="no_failover",
                    severity="high",
                    description=f"Component '{cid}' has no failover configured",
                    recommendation="Enable failover with health checks",
                ))

            # No backups for data stores
            if comp.type.value in ("database", "storage", "cache"):
                if not comp.security.backup_enabled:
                    gaps.append(DRGap(
                        component_id=cid,
                        gap_type="no_backup",
                        severity="critical",
                        description=(
                            f"Data store '{cid}' has no backups enabled"
                        ),
                        recommendation=(
                            "Enable automated backups with appropriate retention"
                        ),
                    ))

            # No encryption at rest for sensitive data
            if not comp.security.encryption_at_rest:
                sev = "high" if comp.type.value in ("database", "storage") else "medium"
                gaps.append(DRGap(
                    component_id=cid,
                    gap_type="no_encryption",
                    severity=sev,
                    description=f"Component '{cid}' lacks encryption at rest",
                    recommendation="Enable encryption at rest",
                ))

            # Single replica without autoscaling
            if comp.replicas == 1 and not comp.autoscaling.enabled:
                gaps.append(DRGap(
                    component_id=cid,
                    gap_type="single_replica",
                    severity="high",
                    description=f"Component '{cid}' has a single replica and no autoscaling",
                    recommendation=(
                        "Add replicas or enable autoscaling for redundancy"
                    ),
                ))

            # Component not in DR region
            if comp.region.region == plan.primary_region:
                dr_comps = self._components_in_region(plan.dr_region)
                # Check if there is a counterpart in DR region
                has_dr_counterpart = any(
                    dc for dc in dr_comps
                    if self.graph.get_component(dc) is not None
                    and self.graph.get_component(dc).type == comp.type
                )
                if not has_dr_counterpart:
                    gaps.append(DRGap(
                        component_id=cid,
                        gap_type="no_dr_counterpart",
                        severity="critical",
                        description=(
                            f"Component '{cid}' in primary region has no "
                            f"counterpart in DR region '{plan.dr_region}'"
                        ),
                        recommendation=(
                            f"Deploy a {comp.type.value} instance in "
                            f"{plan.dr_region}"
                        ),
                    ))

        # Check dependency edges for circuit breakers
        for edge in self.graph.all_dependency_edges():
            if not edge.circuit_breaker.enabled:
                gaps.append(DRGap(
                    component_id=edge.source_id,
                    gap_type="no_circuit_breaker",
                    severity="medium",
                    description=(
                        f"Dependency {edge.source_id} -> {edge.target_id} "
                        f"has no circuit breaker"
                    ),
                    recommendation="Add circuit breaker to prevent cascade failures",
                ))

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        gaps.sort(key=lambda g: severity_order.get(g.severity, 99))

        return gaps

    def compare_strategies(
        self,
        graph: InfraGraph,
    ) -> list[StrategyComparison]:
        """Compare all DR strategies for the given infrastructure.

        Parameters
        ----------
        graph:
            The infrastructure graph.

        Returns
        -------
        list[StrategyComparison]
            Sorted by score descending (best strategy first).
        """
        self.graph = graph
        results: list[StrategyComparison] = []
        component_count = len(self.graph.components)

        for strategy in DRStrategy:
            rpo_mult = _STRATEGY_RPO_MULTIPLIER[strategy]
            rto_mult = _STRATEGY_RTO_MULTIPLIER[strategy]
            cost_mult = _STRATEGY_COST_MULTIPLIER[strategy]

            # Estimate RPO/RTO
            max_rpo = 0.0
            max_rto = 0.0
            for comp in self.graph.components.values():
                base_rpo = self._component_base_rpo(comp)
                base_rto = self._component_base_rto(comp)
                max_rpo = max(max_rpo, base_rpo * rpo_mult)
                max_rto = max(max_rto, base_rto * rto_mult)

            # Monthly cost estimate: $100/component base * cost multiplier
            monthly_cost = component_count * 100.0 * cost_mult

            # Build pros/cons
            pros: list[str] = []
            cons: list[str] = []

            if strategy == DRStrategy.MULTI_SITE_ACTIVE:
                pros.extend([
                    "Near-zero RTO and RPO",
                    "No data loss during failover",
                    "Seamless user experience",
                ])
                cons.extend([
                    "Highest infrastructure cost",
                    "Complex to implement and maintain",
                ])
            elif strategy == DRStrategy.WARM_STANDBY:
                pros.extend([
                    "Low RTO with pre-provisioned resources",
                    "Moderate cost",
                ])
                cons.extend([
                    "Some data loss possible with async replication",
                    "Requires regular testing",
                ])
            elif strategy == DRStrategy.PILOT_LIGHT:
                pros.extend([
                    "Lower cost than warm standby",
                    "Core systems always available",
                ])
                cons.extend([
                    "Higher RTO due to scale-out requirement",
                    "Data replication lag",
                ])
            elif strategy == DRStrategy.COLD_STANDBY:
                pros.extend([
                    "Low ongoing cost",
                    "Infrastructure as code makes rebuilding reliable",
                ])
                cons.extend([
                    "High RTO: full provisioning needed",
                    "Potential data loss from backup lag",
                ])
            elif strategy == DRStrategy.BACKUP_RESTORE:
                pros.extend([
                    "Lowest cost option",
                    "Simple to implement",
                ])
                cons.extend([
                    "Highest RTO and RPO",
                    "Significant data loss possible",
                    "Manual processes required",
                ])

            # Score: weighted combination of RPO, RTO, and cost (lower is better)
            # Normalize and invert so higher score = better
            rpo_score = max(0, 100 - (max_rpo / 36.0))  # 3600s = 0 points
            rto_score = max(0, 100 - (max_rto / 36.0))
            cost_score = max(0, 100 - monthly_cost / 10.0)  # $1000 = 0 points
            score = (rpo_score * 0.35 + rto_score * 0.35 + cost_score * 0.3)

            results.append(StrategyComparison(
                strategy=strategy,
                estimated_rpo_seconds=int(math.ceil(max_rpo)),
                estimated_rto_seconds=int(math.ceil(max_rto)),
                estimated_monthly_cost=round(monthly_cost, 2),
                pros=pros,
                cons=cons,
                score=round(score, 1),
            ))

        # Sort by score descending
        results.sort(key=lambda s: s.score, reverse=True)
        return results

    def calculate_dr_cost(
        self,
        graph: InfraGraph,
        plan: DRPlan,
    ) -> DRCostEstimate:
        """Calculate the cost of implementing a DR plan.

        Parameters
        ----------
        graph:
            The infrastructure graph.
        plan:
            The DR plan.

        Returns
        -------
        DRCostEstimate
        """
        self.graph = graph
        cost_mult = _STRATEGY_COST_MULTIPLIER.get(plan.strategy, 1.0)

        infra_cost = 0.0
        replication_cost = 0.0
        storage_cost = 0.0
        per_component: dict[str, float] = {}

        for cid, comp in self.graph.components.items():
            # Base infrastructure cost from cost profile
            base = comp.cost_profile.hourly_infra_cost * 730  # ~hours/month
            comp_cost = base * cost_mult

            # Replication cost for data stores
            if comp.type.value in ("database", "storage", "cache"):
                repl = base * 0.3  # 30% of base for replication
                if plan.data_replication == "sync":
                    repl *= 1.5  # sync replication is more expensive
                replication_cost += repl
                comp_cost += repl

            # Storage cost
            disk_gb = comp.metrics.disk_used_gb
            if disk_gb > 0:
                store = disk_gb * 0.023  # ~$0.023/GB/month (S3 pricing)
                storage_cost += store
                comp_cost += store

            infra_cost += base * cost_mult
            per_component[cid] = round(comp_cost, 2)

        # Annual testing cost: 4 tests/year, each costs ~2 hours of engineering
        testing_cost = 4 * 2 * 150.0  # $150/hour

        total = infra_cost + replication_cost + storage_cost + (testing_cost / 12.0)

        return DRCostEstimate(
            monthly_infrastructure_cost=round(infra_cost, 2),
            monthly_replication_cost=round(replication_cost, 2),
            monthly_storage_cost=round(storage_cost, 2),
            annual_testing_cost=round(testing_cost, 2),
            total_monthly_cost=round(total, 2),
            cost_per_component=per_component,
        )

    def simulate_failback(
        self,
        graph: InfraGraph,
        plan: DRPlan,
    ) -> FailbackResult:
        """Simulate failback to the primary region after a DR event.

        Parameters
        ----------
        graph:
            The infrastructure graph.
        plan:
            The DR plan.

        Returns
        -------
        FailbackResult
            Includes time estimate, data sync needs, steps, and risks.
        """
        self.graph = graph
        components = self.graph.components

        if not components:
            return FailbackResult()

        # Failback time is typically 1.5-2x failover time
        rto_mult = _STRATEGY_RTO_MULTIPLIER.get(plan.strategy, 1.0)
        max_failback = 0.0
        total_sync_gb = 0.0

        for comp in components.values():
            base_rto = self._component_base_rto(comp)
            failback_time = base_rto * rto_mult * 1.5  # 1.5x failover time
            max_failback = max(max_failback, failback_time)

            # Data that may need re-syncing
            if comp.type.value in ("database", "storage", "cache"):
                total_sync_gb += comp.metrics.disk_used_gb * 0.1  # 10% delta

        steps: list[str] = [
            f"Verify primary region '{plan.primary_region}' is fully recovered",
            "Assess data delta between DR and primary regions",
            "Begin data synchronization from DR to primary",
            "Validate data consistency in primary region",
            "Gradually shift traffic back to primary region",
            "Monitor primary region for stability",
            "Scale down DR region to standby state",
            "Update DNS records to point to primary",
            "Confirm all services healthy in primary region",
        ]

        risks: list[str] = [
            "Data written to DR region during outage may conflict with primary",
            "Network instability during transition may cause brief outages",
        ]

        can_failback = True

        if plan.strategy == DRStrategy.BACKUP_RESTORE:
            risks.append(
                "Backup-restore strategy may result in data loss during failback"
            )

        # If no components in DR region, failback is trivial but risky
        dr_comps = self._components_in_region(plan.dr_region)
        if not dr_comps:
            risks.append("No components found in DR region; failback may not be needed")
            can_failback = False

        if not plan.failover_automated:
            risks.append("Manual failback process increases risk of errors")
            max_failback *= 1.5

        return FailbackResult(
            estimated_failback_time_seconds=int(math.ceil(max_failback)),
            data_sync_required_gb=round(total_sync_gb, 3),
            steps=steps,
            risks=risks,
            can_failback_safely=can_failback,
        )
