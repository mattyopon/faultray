# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Disaster recovery readiness scorer.

Evaluates an infrastructure's preparedness for disaster recovery scenarios
including regional outages, data center failures, and data loss events.
Produces a DR readiness score with actionable recommendations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


class DRScenario(str, Enum):
    """Disaster recovery scenario types."""

    REGIONAL_OUTAGE = "regional_outage"
    DATACENTER_FAILURE = "datacenter_failure"
    DATA_CORRUPTION = "data_corruption"
    RANSOMWARE = "ransomware"
    DNS_HIJACK = "dns_hijack"
    CLOUD_PROVIDER_OUTAGE = "cloud_provider_outage"


@dataclass
class DRCapability:
    """Assessment of a single DR scenario capability."""

    scenario: DRScenario
    is_covered: bool
    rto_achievable_minutes: float
    rpo_achievable_minutes: float
    automation_level: str  # "fully_automated", "semi_automated", "manual", "none"
    gaps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DRReadinessReport:
    """Complete DR readiness assessment report."""

    overall_score: float  # 0-100
    tier: str  # "platinum", "gold", "silver", "bronze", "unprotected"
    capabilities: list[DRCapability] = field(default_factory=list)
    critical_gaps: list[str] = field(default_factory=list)
    total_scenarios: int = 0
    covered_scenarios: int = 0
    estimated_recovery_cost_hours: float = 0.0
    runbook_completeness: float = 0.0  # 0-100%


class DRReadinessScorer:
    """Evaluate an infrastructure graph's disaster recovery readiness.

    Scoring Logic (max 100 points):
    - Multi-region/zone deployment: +25 points
    - Automated failover on all critical components: +20 points
    - Backup coverage for all data stores: +15 points
    - Circuit breakers on all dependencies: +10 points
    - Monitoring & alerting enabled: +10 points
    - Encrypted data at rest: +10 points
    - Autoscaling enabled: +5 points
    - Log monitoring enabled: +5 points

    Tiers:
    - 90+ platinum
    - 70-89 gold
    - 50-69 silver
    - 30-49 bronze
    - <30 unprotected
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def assess(self) -> DRReadinessReport:
        """Perform a full DR readiness assessment across all scenarios."""
        capabilities = [self.assess_scenario(s) for s in DRScenario]
        total_scenarios = len(capabilities)
        covered_scenarios = sum(1 for c in capabilities if c.is_covered)

        score = self._compute_score()

        # Collect critical gaps from all capabilities
        critical_gaps: list[str] = []
        for cap in capabilities:
            critical_gaps.extend(cap.gaps)
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_gaps: list[str] = []
        for gap in critical_gaps:
            if gap not in seen:
                seen.add(gap)
                unique_gaps.append(gap)

        # Estimate recovery cost hours based on components without automation
        estimated_recovery_cost_hours = self._estimate_recovery_cost_hours()

        # Runbook completeness from team config
        runbook_completeness = self._compute_runbook_completeness()

        tier = self._calculate_tier(score)

        return DRReadinessReport(
            overall_score=round(score, 1),
            tier=tier,
            capabilities=capabilities,
            critical_gaps=unique_gaps,
            total_scenarios=total_scenarios,
            covered_scenarios=covered_scenarios,
            estimated_recovery_cost_hours=round(estimated_recovery_cost_hours, 1),
            runbook_completeness=round(runbook_completeness, 1),
        )

    def assess_scenario(self, scenario: DRScenario) -> DRCapability:
        """Assess readiness for a specific DR scenario."""
        components = self.graph.components

        if not components:
            return DRCapability(
                scenario=scenario,
                is_covered=False,
                rto_achievable_minutes=0.0,
                rpo_achievable_minutes=0.0,
                automation_level="none",
                gaps=["No infrastructure components defined"],
                recommendations=["Define infrastructure components to assess DR readiness"],
            )

        if scenario == DRScenario.REGIONAL_OUTAGE:
            return self._assess_regional_outage()
        elif scenario == DRScenario.DATACENTER_FAILURE:
            return self._assess_datacenter_failure()
        elif scenario == DRScenario.DATA_CORRUPTION:
            return self._assess_data_corruption()
        elif scenario == DRScenario.RANSOMWARE:
            return self._assess_ransomware()
        elif scenario == DRScenario.DNS_HIJACK:
            return self._assess_dns_hijack()
        elif scenario == DRScenario.CLOUD_PROVIDER_OUTAGE:
            return self._assess_cloud_provider_outage()
        else:
            return DRCapability(
                scenario=scenario,
                is_covered=False,
                rto_achievable_minutes=0.0,
                rpo_achievable_minutes=0.0,
                automation_level="none",
                gaps=[f"Unknown scenario: {scenario}"],
                recommendations=[],
            )

    # ------------------------------------------------------------------
    # Scoring infrastructure checks
    # ------------------------------------------------------------------

    def _check_multi_region(self) -> bool:
        """Check if infrastructure spans multiple regions or availability zones."""
        regions: set[str] = set()
        azs: set[str] = set()
        for comp in self.graph.components.values():
            region_cfg = comp.region
            if region_cfg.region:
                regions.add(region_cfg.region)
            if region_cfg.availability_zone:
                azs.add(region_cfg.availability_zone)
        return len(regions) >= 2 or len(azs) >= 2

    def _check_backup_coverage(self) -> float:
        """Return fraction (0.0-1.0) of data-storing components with backups enabled."""
        data_store_types = {"database", "storage", "cache"}
        data_stores = [
            c for c in self.graph.components.values()
            if c.type.value in data_store_types
        ]
        if not data_stores:
            return 1.0  # No data stores = nothing to back up, full coverage by default
        backed_up = sum(1 for c in data_stores if c.security.backup_enabled)
        return backed_up / len(data_stores)

    def _check_failover_automation(self) -> str:
        """Determine overall failover automation level.

        Returns one of: "fully_automated", "semi_automated", "manual", "none"
        """
        components = list(self.graph.components.values())
        if not components:
            return "none"

        failover_count = sum(1 for c in components if c.failover.enabled)
        autoscale_count = sum(1 for c in components if c.autoscaling.enabled)
        total = len(components)

        failover_count + autoscale_count
        # A component can have both, so count unique
        auto_components = sum(
            1 for c in components if c.failover.enabled or c.autoscaling.enabled
        )

        ratio = auto_components / total
        if ratio >= 1.0:
            return "fully_automated"
        elif ratio >= 0.5:
            return "semi_automated"
        elif ratio > 0.0:
            return "manual"
        else:
            return "none"

    def _check_data_protection(self) -> dict:
        """Check data protection measures across the infrastructure.

        Returns a dict with:
        - encryption_at_rest_ratio: float (0.0-1.0)
        - encryption_in_transit_ratio: float (0.0-1.0)
        - backup_ratio: float (0.0-1.0)
        - waf_ratio: float (0.0-1.0)
        """
        components = list(self.graph.components.values())
        if not components:
            return {
                "encryption_at_rest_ratio": 0.0,
                "encryption_in_transit_ratio": 0.0,
                "backup_ratio": 0.0,
                "waf_ratio": 0.0,
            }

        total = len(components)
        return {
            "encryption_at_rest_ratio": sum(
                1 for c in components if c.security.encryption_at_rest
            ) / total,
            "encryption_in_transit_ratio": sum(
                1 for c in components if c.security.encryption_in_transit
            ) / total,
            "backup_ratio": sum(
                1 for c in components if c.security.backup_enabled
            ) / total,
            "waf_ratio": sum(
                1 for c in components if c.security.waf_protected
            ) / total,
        }

    def _calculate_tier(self, score: float) -> str:
        """Map a numeric score to a tier label."""
        if score >= 90:
            return "platinum"
        elif score >= 70:
            return "gold"
        elif score >= 50:
            return "silver"
        elif score >= 30:
            return "bronze"
        else:
            return "unprotected"

    # ------------------------------------------------------------------
    # Internal scoring
    # ------------------------------------------------------------------

    def _compute_score(self) -> float:
        """Compute the overall DR readiness score (0-100)."""
        components = list(self.graph.components.values())
        if not components:
            return 0.0

        score = 0.0
        total = len(components)

        # 1. Multi-region/zone deployment: +25 points
        if self._check_multi_region():
            score += 25.0

        # 2. Automated failover on all critical components: +20 points
        failover_count = sum(1 for c in components if c.failover.enabled)
        failover_ratio = failover_count / total
        score += failover_ratio * 20.0

        # 3. Backup coverage for all data stores: +15 points
        backup_coverage = self._check_backup_coverage()
        score += backup_coverage * 15.0

        # 4. Circuit breakers on all dependencies: +10 points
        edges = self.graph.all_dependency_edges()
        if edges:
            cb_count = sum(1 for e in edges if e.circuit_breaker.enabled)
            cb_ratio = cb_count / len(edges)
            score += cb_ratio * 10.0
        else:
            # No dependencies = no circuit breaker risk
            score += 10.0

        # 5. Monitoring & alerting enabled (proxy: audit_logging in compliance): +10 points
        monitoring_count = sum(
            1 for c in components if c.compliance_tags.audit_logging
        )
        monitoring_ratio = monitoring_count / total
        score += monitoring_ratio * 10.0

        # 6. Encrypted data at rest: +10 points
        encryption_count = sum(
            1 for c in components if c.security.encryption_at_rest
        )
        encryption_ratio = encryption_count / total
        score += encryption_ratio * 10.0

        # 7. Autoscaling enabled: +5 points
        autoscale_count = sum(1 for c in components if c.autoscaling.enabled)
        autoscale_ratio = autoscale_count / total
        score += autoscale_ratio * 5.0

        # 8. Log monitoring enabled: +5 points
        log_count = sum(1 for c in components if c.security.log_enabled)
        log_ratio = log_count / total
        score += log_ratio * 5.0

        return min(100.0, max(0.0, score))

    # ------------------------------------------------------------------
    # Scenario-specific assessments
    # ------------------------------------------------------------------

    def _assess_regional_outage(self) -> DRCapability:
        """Assess readiness for a full regional outage."""
        gaps: list[str] = []
        recommendations: list[str] = []

        multi_region = self._check_multi_region()
        if not multi_region:
            gaps.append("Infrastructure is not deployed across multiple regions")
            recommendations.append(
                "Deploy critical components in at least 2 regions for regional failover"
            )

        failover_level = self._check_failover_automation()
        if failover_level in ("none", "manual"):
            gaps.append("No automated failover configured for regional outage")
            recommendations.append(
                "Enable automated failover with health checks and DNS-based routing"
            )

        # RTO: worst-case recovery time across components
        rto_minutes = self._worst_case_rto_minutes()
        # RPO: worst-case data loss
        rpo_minutes = self._worst_case_rpo_minutes()

        is_covered = multi_region and failover_level in ("fully_automated", "semi_automated")

        return DRCapability(
            scenario=DRScenario.REGIONAL_OUTAGE,
            is_covered=is_covered,
            rto_achievable_minutes=rto_minutes,
            rpo_achievable_minutes=rpo_minutes,
            automation_level=failover_level,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _assess_datacenter_failure(self) -> DRCapability:
        """Assess readiness for a data center (AZ) failure."""
        gaps: list[str] = []
        recommendations: list[str] = []

        # Check AZ distribution
        azs: set[str] = set()
        for comp in self.graph.components.values():
            if comp.region.availability_zone:
                azs.add(comp.region.availability_zone)

        multi_az = len(azs) >= 2
        if not multi_az:
            gaps.append("All components are in a single availability zone")
            recommendations.append(
                "Distribute components across multiple availability zones"
            )

        failover_level = self._check_failover_automation()
        if failover_level in ("none", "manual"):
            gaps.append("No automated failover for AZ-level failure")
            recommendations.append("Configure failover with automated health checks")

        rto_minutes = self._worst_case_rto_minutes()
        rpo_minutes = self._worst_case_rpo_minutes()

        is_covered = multi_az and failover_level in ("fully_automated", "semi_automated")

        return DRCapability(
            scenario=DRScenario.DATACENTER_FAILURE,
            is_covered=is_covered,
            rto_achievable_minutes=rto_minutes,
            rpo_achievable_minutes=rpo_minutes,
            automation_level=failover_level,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _assess_data_corruption(self) -> DRCapability:
        """Assess readiness for data corruption events."""
        gaps: list[str] = []
        recommendations: list[str] = []

        backup_coverage = self._check_backup_coverage()
        if backup_coverage < 1.0:
            gaps.append(
                f"Only {backup_coverage * 100:.0f}% of data stores have backups enabled"
            )
            recommendations.append("Enable backups on all data stores (databases, storage)")

        # Check encryption at rest for integrity
        data_protection = self._check_data_protection()
        if data_protection["encryption_at_rest_ratio"] < 1.0:
            gaps.append("Not all data stores have encryption at rest")
            recommendations.append("Enable encryption at rest on all data stores")

        rto_minutes = self._worst_case_rto_minutes()
        rpo_minutes = self._worst_case_rpo_minutes()

        is_covered = backup_coverage >= 1.0

        automation_level = self._check_failover_automation()

        return DRCapability(
            scenario=DRScenario.DATA_CORRUPTION,
            is_covered=is_covered,
            rto_achievable_minutes=rto_minutes,
            rpo_achievable_minutes=rpo_minutes,
            automation_level=automation_level,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _assess_ransomware(self) -> DRCapability:
        """Assess readiness for ransomware attacks."""
        gaps: list[str] = []
        recommendations: list[str] = []

        backup_coverage = self._check_backup_coverage()
        if backup_coverage < 1.0:
            gaps.append("Insufficient backup coverage for ransomware recovery")
            recommendations.append(
                "Enable immutable backups on all data stores with versioning"
            )

        data_protection = self._check_data_protection()
        if data_protection["encryption_at_rest_ratio"] < 1.0:
            gaps.append("Not all components have encryption at rest")
            recommendations.append("Enable encryption at rest to limit data exfiltration risk")

        # Check network segmentation
        segmented_count = sum(
            1 for c in self.graph.components.values()
            if c.security.network_segmented
        )
        total = len(self.graph.components)
        if segmented_count < total:
            gaps.append("Network segmentation is incomplete — ransomware can spread laterally")
            recommendations.append("Implement network segmentation to contain lateral movement")

        rto_minutes = self._worst_case_rto_minutes()
        rpo_minutes = self._worst_case_rpo_minutes()

        is_covered = (
            backup_coverage >= 1.0
            and data_protection["encryption_at_rest_ratio"] >= 1.0
            and segmented_count == total
        )

        automation_level = self._check_failover_automation()

        return DRCapability(
            scenario=DRScenario.RANSOMWARE,
            is_covered=is_covered,
            rto_achievable_minutes=rto_minutes,
            rpo_achievable_minutes=rpo_minutes,
            automation_level=automation_level,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _assess_dns_hijack(self) -> DRCapability:
        """Assess readiness for DNS hijacking attacks."""
        gaps: list[str] = []
        recommendations: list[str] = []

        # Check WAF protection
        components = list(self.graph.components.values())
        waf_count = sum(1 for c in components if c.security.waf_protected)
        total = len(components)

        if waf_count < total:
            gaps.append("Not all public-facing components are WAF-protected")
            recommendations.append("Enable WAF protection on all public-facing endpoints")

        # Check encryption in transit (helps detect hijacked connections)
        transit_encrypted = sum(
            1 for c in components if c.security.encryption_in_transit
        )
        if transit_encrypted < total:
            gaps.append("Not all connections use encryption in transit")
            recommendations.append(
                "Enable TLS/SSL on all connections to detect DNS hijack via cert validation"
            )

        # Check if DNS component exists and has monitoring
        dns_components = [c for c in components if c.type.value == "dns"]
        if not dns_components:
            gaps.append("No DNS components defined for monitoring")
            recommendations.append("Define DNS components and enable monitoring")

        rto_minutes = self._worst_case_rto_minutes()
        rpo_minutes = self._worst_case_rpo_minutes()

        is_covered = (
            waf_count == total
            and transit_encrypted == total
            and len(dns_components) > 0
        )

        automation_level = self._check_failover_automation()

        return DRCapability(
            scenario=DRScenario.DNS_HIJACK,
            is_covered=is_covered,
            rto_achievable_minutes=rto_minutes,
            rpo_achievable_minutes=rpo_minutes,
            automation_level=automation_level,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _assess_cloud_provider_outage(self) -> DRCapability:
        """Assess readiness for a full cloud provider outage."""
        gaps: list[str] = []
        recommendations: list[str] = []

        multi_region = self._check_multi_region()
        if not multi_region:
            gaps.append("No multi-region deployment to survive provider-wide issues")
            recommendations.append(
                "Consider multi-cloud or multi-region deployment for provider resilience"
            )

        failover_level = self._check_failover_automation()
        if failover_level in ("none", "manual"):
            gaps.append("No automated failover for cloud provider outage")
            recommendations.append(
                "Implement automated DNS-based failover across cloud providers or regions"
            )

        # Check external dependencies
        external_deps = [
            c for c in self.graph.components.values()
            if c.type.value == "external_api"
        ]
        if external_deps:
            cb_edges = self.graph.all_dependency_edges()
            uncovered_external = 0
            for edge in cb_edges:
                target = self.graph.get_component(edge.target_id)
                if target and target.type.value == "external_api" and not edge.circuit_breaker.enabled:
                    uncovered_external += 1
            if uncovered_external > 0:
                gaps.append(
                    f"{uncovered_external} external API dependencies lack circuit breakers"
                )
                recommendations.append(
                    "Add circuit breakers to all external API dependencies"
                )

        rto_minutes = self._worst_case_rto_minutes()
        rpo_minutes = self._worst_case_rpo_minutes()

        is_covered = multi_region and failover_level in ("fully_automated", "semi_automated")

        return DRCapability(
            scenario=DRScenario.CLOUD_PROVIDER_OUTAGE,
            is_covered=is_covered,
            rto_achievable_minutes=rto_minutes,
            rpo_achievable_minutes=rpo_minutes,
            automation_level=failover_level,
            gaps=gaps,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _worst_case_rto_minutes(self) -> float:
        """Compute worst-case RTO in minutes across all components."""
        components = list(self.graph.components.values())
        if not components:
            return 0.0

        max_rto = 0.0
        for comp in components:
            if comp.failover.enabled:
                rto = comp.failover.promotion_time_seconds / 60.0
            else:
                rto = comp.operational_profile.mttr_minutes
                if rto <= 0:
                    rto = 30.0  # default 30 min MTTR
            max_rto = max(max_rto, rto)
        return max_rto

    def _worst_case_rpo_minutes(self) -> float:
        """Compute worst-case RPO in minutes across all components."""
        components = list(self.graph.components.values())
        if not components:
            return 0.0

        max_rpo = 0.0
        for comp in components:
            rpo_seconds = comp.region.rpo_seconds
            if rpo_seconds > 0:
                max_rpo = max(max_rpo, rpo_seconds / 60.0)
            elif comp.security.backup_enabled:
                # Use backup frequency as RPO proxy
                max_rpo = max(max_rpo, comp.security.backup_frequency_hours * 60.0)
            elif comp.failover.enabled:
                # Async replication lag estimate: ~5 seconds
                max_rpo = max(max_rpo, 5.0 / 60.0)
            else:
                # No backup, no failover, no explicit RPO: worst-case 24h
                max_rpo = max(max_rpo, 24.0 * 60.0)
        return max_rpo

    def _estimate_recovery_cost_hours(self) -> float:
        """Estimate total recovery cost in engineer-hours."""
        components = list(self.graph.components.values())
        if not components:
            return 0.0

        total_hours = 0.0
        for comp in components:
            if comp.failover.enabled and comp.autoscaling.enabled:
                # Fully automated: minimal human intervention
                total_hours += 0.5
            elif comp.failover.enabled or comp.autoscaling.enabled:
                # Semi-automated
                total_hours += 2.0
            else:
                # Manual recovery
                total_hours += 4.0
        return total_hours

    def _compute_runbook_completeness(self) -> float:
        """Compute average runbook coverage across all teams."""
        components = list(self.graph.components.values())
        if not components:
            return 0.0

        total = sum(c.team.runbook_coverage_percent for c in components)
        return total / len(components)
