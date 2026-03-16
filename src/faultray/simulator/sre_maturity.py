"""SRE Maturity Assessment Engine.

Evaluates SRE maturity across 8 dimensions based on infrastructure
configuration, producing a maturity level (1-5) per dimension and
an overall SRE maturity score.

Maturity Levels:
  Level 1 - Initial/Ad-hoc: No formal processes
  Level 2 - Managed: Basic monitoring and alerting
  Level 3 - Defined: SLOs, incident response, chaos testing
  Level 4 - Quantitatively Managed: Data-driven decisions, predictive
  Level 5 - Optimizing: Continuous improvement, auto-remediation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import Component
from faultray.model.graph import InfraGraph


class MaturityLevel(Enum):
    """SRE maturity levels following the CMMI model."""

    INITIAL = 1
    MANAGED = 2
    DEFINED = 3
    QUANTITATIVE = 4
    OPTIMIZING = 5


class MaturityDimension(Enum):
    """Dimensions of SRE maturity assessment."""

    MONITORING = "monitoring"
    INCIDENT_RESPONSE = "incident_response"
    CAPACITY_PLANNING = "capacity_planning"
    CHANGE_MANAGEMENT = "change_management"
    AVAILABILITY = "availability"
    DISASTER_RECOVERY = "disaster_recovery"
    SECURITY = "security"
    AUTOMATION = "automation"


# Human-readable labels for each dimension
_DIMENSION_LABELS: dict[str, str] = {
    "monitoring": "Monitoring & Observability",
    "incident_response": "Incident Response",
    "capacity_planning": "Capacity Planning",
    "change_management": "Change Management",
    "availability": "Availability & Reliability",
    "disaster_recovery": "Disaster Recovery",
    "security": "Security Posture",
    "automation": "Automation & Self-Healing",
}

# Human-readable labels for maturity levels
_LEVEL_LABELS: dict[int, str] = {
    1: "Initial / Ad-hoc",
    2: "Managed",
    3: "Defined",
    4: "Quantitatively Managed",
    5: "Optimizing",
}


@dataclass
class DimensionAssessment:
    """Assessment result for a single maturity dimension."""

    dimension: MaturityDimension
    level: MaturityLevel
    score: float  # 0-100
    evidence: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class MaturityReport:
    """Complete SRE maturity assessment report."""

    overall_level: MaturityLevel
    overall_score: float  # 0-100
    dimensions: list[DimensionAssessment] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    roadmap: list[tuple[str, str, str]] = field(default_factory=list)  # (action, target_level, effort)
    radar_data: dict[str, float] = field(default_factory=dict)  # dimension -> score for radar chart
    industry_comparison: str = ""


class SREMaturityEngine:
    """Engine for assessing SRE maturity of an infrastructure graph."""

    def assess(self, graph: InfraGraph) -> MaturityReport:
        """Run a full SRE maturity assessment across all dimensions."""
        dimensions = []
        for dim in MaturityDimension:
            assessment = self.assess_dimension(graph, dim)
            dimensions.append(assessment)

        # Calculate overall score (weighted average)
        total_score = sum(d.score for d in dimensions) / len(dimensions) if dimensions else 0.0
        overall_level = self._score_to_level(total_score)

        # Identify strengths and weaknesses
        sorted_dims = sorted(dimensions, key=lambda d: d.score, reverse=True)
        strengths = [
            f"{_DIMENSION_LABELS.get(d.dimension.value, d.dimension.value)}: "
            f"Level {d.level.value} ({_LEVEL_LABELS[d.level.value]})"
            for d in sorted_dims if d.level.value >= 3
        ]
        weaknesses = [
            f"{_DIMENSION_LABELS.get(d.dimension.value, d.dimension.value)}: "
            f"Level {d.level.value} ({_LEVEL_LABELS[d.level.value]})"
            for d in sorted_dims if d.level.value <= 2
        ]

        # Build radar chart data
        radar_data = {
            _DIMENSION_LABELS.get(d.dimension.value, d.dimension.value): d.score
            for d in dimensions
        }

        # Generate roadmap
        roadmap = self.generate_roadmap(
            MaturityReport(
                overall_level=overall_level,
                overall_score=total_score,
                dimensions=dimensions,
            )
        )

        # Industry comparison
        industry_comparison = self._generate_industry_comparison(total_score)

        return MaturityReport(
            overall_level=overall_level,
            overall_score=round(total_score, 1),
            dimensions=dimensions,
            strengths=strengths,
            weaknesses=weaknesses,
            roadmap=roadmap,
            radar_data=radar_data,
            industry_comparison=industry_comparison,
        )

    def assess_dimension(
        self, graph: InfraGraph, dimension: MaturityDimension
    ) -> DimensionAssessment:
        """Assess a single maturity dimension."""
        assessors = {
            MaturityDimension.MONITORING: self._assess_monitoring,
            MaturityDimension.INCIDENT_RESPONSE: self._assess_incident_response,
            MaturityDimension.CAPACITY_PLANNING: self._assess_capacity_planning,
            MaturityDimension.CHANGE_MANAGEMENT: self._assess_change_management,
            MaturityDimension.AVAILABILITY: self._assess_availability,
            MaturityDimension.DISASTER_RECOVERY: self._assess_disaster_recovery,
            MaturityDimension.SECURITY: self._assess_security,
            MaturityDimension.AUTOMATION: self._assess_automation,
        }
        return assessors[dimension](graph)

    def generate_roadmap(self, report: MaturityReport) -> list[tuple[str, str, str]]:
        """Generate an improvement roadmap from the maturity report."""
        roadmap: list[tuple[str, str, str]] = []

        # Sort dimensions by score ascending (weakest first)
        sorted_dims = sorted(report.dimensions, key=lambda d: d.score)

        for dim in sorted_dims:
            if dim.level.value >= 5:
                continue  # Already at max
            target_level = min(dim.level.value + 1, 5)
            target_label = _LEVEL_LABELS[target_level]
            dim_label = _DIMENSION_LABELS.get(dim.dimension.value, dim.dimension.value)

            for rec in dim.recommendations[:2]:  # Top 2 recommendations per dimension
                effort = self._estimate_effort(dim.level.value, target_level)
                roadmap.append((
                    f"[{dim_label}] {rec}",
                    f"Level {target_level} ({target_label})",
                    effort,
                ))

        return roadmap

    def to_radar_chart_data(self, report: MaturityReport) -> dict:
        """Convert report to radar chart data format."""
        return {
            "labels": list(report.radar_data.keys()),
            "values": list(report.radar_data.values()),
            "max_value": 100,
            "overall_score": report.overall_score,
            "overall_level": report.overall_level.value,
        }

    # -----------------------------------------------------------------------
    # Internal assessment methods
    # -----------------------------------------------------------------------

    def _assess_monitoring(self, graph: InfraGraph) -> DimensionAssessment:
        """Assess monitoring & observability maturity.

        L1: No health checks configured
        L2: Some health checks (>25% components)
        L3: All critical components have health checks (>75%)
        L4: Health checks + autoscaling on all components
        L5: Health checks + autoscaling + circuit breakers on all
        """
        components = list(graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.MONITORING,
                level=MaturityLevel.INITIAL,
                score=0.0,
                evidence=["No components defined"],
                gaps=["Define infrastructure components"],
                recommendations=["Create an infrastructure model with health check configuration"],
            )

        total = len(components)
        # Health checks are indicated by failover config with health_check_interval
        has_health_check = sum(
            1 for c in components
            if c.failover.health_check_interval_seconds > 0 and c.failover.enabled
        )
        has_autoscaling = sum(1 for c in components if c.autoscaling.enabled)

        # Circuit breakers on dependency edges
        all_edges = graph.all_dependency_edges()
        has_circuit_breaker = sum(1 for e in all_edges if e.circuit_breaker.enabled)
        total_edges = len(all_edges)

        hc_ratio = has_health_check / total
        as_ratio = has_autoscaling / total
        cb_ratio = has_circuit_breaker / total_edges if total_edges > 0 else 0.0

        evidence: list[str] = []
        gaps: list[str] = []
        recommendations: list[str] = []

        # Determine level
        if hc_ratio == 0:
            level = MaturityLevel.INITIAL
            score = 10.0
            gaps.append("No health checks configured on any component")
            recommendations.append("Enable failover with health checks on all critical components")
        elif hc_ratio < 0.75:
            level = MaturityLevel.MANAGED
            score = 25.0 + (hc_ratio * 25.0)
            evidence.append(f"{has_health_check}/{total} components have health checks ({hc_ratio:.0%})")
            gaps.append(f"{total - has_health_check} components lack health checks")
            recommendations.append("Add health checks to remaining components to reach >75% coverage")
        elif as_ratio < 0.5:
            level = MaturityLevel.DEFINED
            score = 50.0 + (as_ratio * 20.0)
            evidence.append(f"{has_health_check}/{total} components have health checks ({hc_ratio:.0%})")
            evidence.append(f"{has_autoscaling}/{total} components have autoscaling ({as_ratio:.0%})")
            gaps.append(f"{total - has_autoscaling} components lack autoscaling")
            recommendations.append("Enable autoscaling on all components for dynamic capacity management")
        elif cb_ratio < 0.75:
            level = MaturityLevel.QUANTITATIVE
            score = 70.0 + (cb_ratio * 20.0)
            evidence.append(f"{has_health_check}/{total} components have health checks")
            evidence.append(f"{has_autoscaling}/{total} components have autoscaling")
            evidence.append(f"{has_circuit_breaker}/{total_edges} edges have circuit breakers ({cb_ratio:.0%})")
            gaps.append(f"{total_edges - has_circuit_breaker} dependency edges lack circuit breakers")
            recommendations.append("Add circuit breakers to all dependency edges for full observability")
        else:
            level = MaturityLevel.OPTIMIZING
            score = 90.0 + min(10.0, cb_ratio * 10.0)
            evidence.append("Comprehensive monitoring: health checks, autoscaling, circuit breakers")
            evidence.append(f"Coverage: HC={hc_ratio:.0%}, AS={as_ratio:.0%}, CB={cb_ratio:.0%}")
            recommendations.append("Consider adding custom SLI/SLO metrics for proactive alerting")

        return DimensionAssessment(
            dimension=MaturityDimension.MONITORING,
            level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _assess_incident_response(self, graph: InfraGraph) -> DimensionAssessment:
        """Assess incident response maturity.

        L1: No failover configured
        L2: Some failover (>25%)
        L3: Failover on critical components + circuit breakers
        L4: Comprehensive failover + auto-scaling + runbooks
        L5: Auto-remediation capability
        """
        components = list(graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.INCIDENT_RESPONSE,
                level=MaturityLevel.INITIAL,
                score=0.0,
                evidence=["No components defined"],
                gaps=["Define infrastructure components"],
                recommendations=["Create an infrastructure model"],
            )

        total = len(components)
        has_failover = sum(1 for c in components if c.failover.enabled)
        has_autoscaling = sum(1 for c in components if c.autoscaling.enabled)

        all_edges = graph.all_dependency_edges()
        has_cb = sum(1 for e in all_edges if e.circuit_breaker.enabled)
        total_edges = len(all_edges)

        fo_ratio = has_failover / total
        as_ratio = has_autoscaling / total
        cb_ratio = has_cb / total_edges if total_edges > 0 else 0.0

        # Check for team operational readiness
        has_team_config = sum(
            1 for c in components
            if c.team.runbook_coverage_percent > 50.0
        )
        team_ratio = has_team_config / total

        evidence: list[str] = []
        gaps: list[str] = []
        recommendations: list[str] = []

        if fo_ratio == 0:
            level = MaturityLevel.INITIAL
            score = 10.0
            gaps.append("No failover configured on any component")
            recommendations.append("Enable failover on critical components (databases, app servers)")
        elif fo_ratio < 0.5 or cb_ratio < 0.25:
            level = MaturityLevel.MANAGED
            score = 25.0 + (fo_ratio * 25.0)
            evidence.append(f"{has_failover}/{total} components have failover ({fo_ratio:.0%})")
            gaps.append("Incomplete failover coverage and circuit breakers")
            recommendations.append("Add failover to critical path components and enable circuit breakers")
        elif as_ratio < 0.5 or team_ratio < 0.25:
            level = MaturityLevel.DEFINED
            score = 50.0 + (as_ratio * 15.0) + (team_ratio * 5.0)
            evidence.append(f"Failover: {fo_ratio:.0%}, Circuit breakers: {cb_ratio:.0%}")
            gaps.append("Limited autoscaling and operational runbook coverage")
            recommendations.append("Enable autoscaling and document runbooks for all critical components")
        elif as_ratio < 0.9 or team_ratio < 0.5:
            level = MaturityLevel.QUANTITATIVE
            score = 70.0 + (as_ratio * 10.0) + (team_ratio * 10.0)
            evidence.append(f"Failover: {fo_ratio:.0%}, AS: {as_ratio:.0%}, Runbooks: {team_ratio:.0%}")
            gaps.append("Not all components have auto-remediation capability")
            recommendations.append("Achieve full autoscaling and runbook coverage for auto-remediation")
        else:
            level = MaturityLevel.OPTIMIZING
            score = 90.0 + min(10.0, (fo_ratio + as_ratio + cb_ratio) * 3.3)
            evidence.append("Comprehensive incident response: failover, autoscaling, runbooks")
            recommendations.append("Implement chaos testing schedules to continuously validate response")

        return DimensionAssessment(
            dimension=MaturityDimension.INCIDENT_RESPONSE,
            level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _assess_capacity_planning(self, graph: InfraGraph) -> DimensionAssessment:
        """Assess capacity planning maturity.

        L1: No capacity awareness (all defaults)
        L2: Some capacity limits defined
        L3: Capacity limits + autoscaling on critical
        L4: Autoscaling + capacity headroom on all
        L5: Predictive autoscaling + SLO-driven capacity
        """
        components = list(graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.CAPACITY_PLANNING,
                level=MaturityLevel.INITIAL,
                score=0.0,
            )

        total = len(components)
        has_autoscaling = sum(1 for c in components if c.autoscaling.enabled)
        has_slo = sum(1 for c in components if len(c.slo_targets) > 0)
        utilizations = [c.utilization() for c in components]
        avg_util = sum(utilizations) / len(utilizations) if utilizations else 0.0
        high_util = sum(1 for u in utilizations if u > 80)

        as_ratio = has_autoscaling / total
        slo_ratio = has_slo / total

        evidence: list[str] = []
        gaps: list[str] = []
        recommendations: list[str] = []

        if as_ratio == 0 and slo_ratio == 0:
            level = MaturityLevel.INITIAL
            score = 15.0
            gaps.append("No autoscaling or SLO targets configured")
            recommendations.append("Define capacity limits and enable autoscaling on critical components")
        elif as_ratio < 0.5:
            level = MaturityLevel.MANAGED
            score = 30.0 + (as_ratio * 20.0)
            evidence.append(f"{has_autoscaling}/{total} components have autoscaling")
            gaps.append("Less than 50% autoscaling coverage")
            recommendations.append("Enable autoscaling on remaining components")
        elif high_util > 0 or slo_ratio < 0.25:
            level = MaturityLevel.DEFINED
            score = 50.0 + (as_ratio * 10.0) + ((1 - high_util / total) * 10.0)
            evidence.append(f"Autoscaling: {as_ratio:.0%}, Avg utilization: {avg_util:.0f}%")
            if high_util > 0:
                gaps.append(f"{high_util} components have >80% utilization")
            recommendations.append("Address high utilization and define SLO targets for capacity management")
        elif slo_ratio < 0.75:
            level = MaturityLevel.QUANTITATIVE
            score = 70.0 + (slo_ratio * 20.0)
            evidence.append(f"Autoscaling: {as_ratio:.0%}, SLO targets: {slo_ratio:.0%}")
            gaps.append("Not all components have SLO-driven capacity targets")
            recommendations.append("Define SLO targets on all components for predictive capacity planning")
        else:
            level = MaturityLevel.OPTIMIZING
            score = 92.0 + min(8.0, slo_ratio * 8.0)
            evidence.append("Full autoscaling with SLO-driven capacity planning")
            recommendations.append("Implement predictive autoscaling based on traffic pattern analysis")

        return DimensionAssessment(
            dimension=MaturityDimension.CAPACITY_PLANNING,
            level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _assess_change_management(self, graph: InfraGraph) -> DimensionAssessment:
        """Assess change management maturity.

        L1: No change tracking
        L2: Basic deployment config (deploy downtime defined)
        L3: Canary/blue-green awareness + compliance tags
        L4: Comprehensive compliance + change management tags
        L5: Full audit trail + automated rollback
        """
        components = list(graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.CHANGE_MANAGEMENT,
                level=MaturityLevel.INITIAL,
                score=0.0,
            )

        total = len(components)
        has_deploy_config = sum(
            1 for c in components
            if c.operational_profile.deploy_downtime_seconds > 0
        )
        has_compliance = sum(
            1 for c in components
            if c.compliance_tags.change_management or c.compliance_tags.audit_logging
        )
        has_failover = sum(1 for c in components if c.failover.enabled)

        deploy_ratio = has_deploy_config / total
        compliance_ratio = has_compliance / total
        fo_ratio = has_failover / total

        evidence: list[str] = []
        gaps: list[str] = []
        recommendations: list[str] = []

        if deploy_ratio == 0 and compliance_ratio == 0:
            level = MaturityLevel.INITIAL
            score = 10.0
            gaps.append("No deployment or change management configuration")
            recommendations.append("Configure deploy_downtime_seconds and enable compliance tags")
        elif compliance_ratio < 0.25:
            level = MaturityLevel.MANAGED
            score = 25.0 + (deploy_ratio * 25.0)
            evidence.append(f"Deployment config: {deploy_ratio:.0%}")
            gaps.append("Limited compliance and audit logging")
            recommendations.append("Enable audit_logging and change_management compliance tags")
        elif compliance_ratio < 0.75:
            level = MaturityLevel.DEFINED
            score = 50.0 + (compliance_ratio * 20.0)
            evidence.append(f"Compliance tags: {compliance_ratio:.0%}")
            gaps.append("Incomplete compliance coverage")
            recommendations.append("Extend compliance tags to all components")
        elif fo_ratio < 0.75:
            level = MaturityLevel.QUANTITATIVE
            score = 70.0 + (fo_ratio * 20.0)
            evidence.append(f"Compliance: {compliance_ratio:.0%}, Failover (rollback): {fo_ratio:.0%}")
            gaps.append("Automated rollback not fully available")
            recommendations.append("Enable failover on all components for automated rollback capability")
        else:
            level = MaturityLevel.OPTIMIZING
            score = 92.0
            evidence.append("Full compliance, audit, and automated rollback capability")
            recommendations.append("Implement automated canary analysis for change validation")

        return DimensionAssessment(
            dimension=MaturityDimension.CHANGE_MANAGEMENT,
            level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _assess_availability(self, graph: InfraGraph) -> DimensionAssessment:
        """Assess availability maturity.

        L1: Estimated < 99% (< 2 nines)
        L2: 99-99.9% (2-3 nines)
        L3: 99.9-99.95% (3+ nines)
        L4: 99.95-99.99% (nearly 4 nines)
        L5: >= 99.99% (4+ nines)
        """
        components = list(graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.AVAILABILITY,
                level=MaturityLevel.INITIAL,
                score=0.0,
                evidence=["No components defined"],
                gaps=["Define infrastructure components"],
                recommendations=["Create an infrastructure model"],
            )

        # Estimate system availability from component configs
        estimated_avail = self._estimate_system_availability(graph)
        nines = self._availability_to_nines(estimated_avail)

        evidence: list[str] = [
            f"Estimated system availability: {estimated_avail * 100:.4f}% ({nines:.2f} nines)"
        ]
        gaps: list[str] = []
        recommendations: list[str] = []

        if estimated_avail < 0.99:
            level = MaturityLevel.INITIAL
            score = max(5.0, estimated_avail * 100 - 90) * 2  # Scale 90-99 to 0-18
            score = max(5.0, score)
            gaps.append("System availability below 99% (less than 2 nines)")
            recommendations.append("Add redundancy (replicas > 1) to single points of failure")
            recommendations.append("Enable failover for critical components")
        elif estimated_avail < 0.999:
            level = MaturityLevel.MANAGED
            score = 25.0 + (estimated_avail - 0.99) * 2500  # Scale 99-99.9 to 25-50
            evidence.append("Basic availability achieved (2-3 nines)")
            gaps.append("Availability below 99.9%")
            recommendations.append("Increase replicas and enable health checks on all critical components")
        elif estimated_avail < 0.9995:
            level = MaturityLevel.DEFINED
            score = 50.0 + (estimated_avail - 0.999) * 40000  # Scale 99.9-99.95 to 50-70
            evidence.append("Good availability (3+ nines)")
            gaps.append("Availability below 99.95%")
            recommendations.append("Add circuit breakers and autoscaling to approach 4 nines")
        elif estimated_avail < 0.9999:
            level = MaturityLevel.QUANTITATIVE
            score = 70.0 + (estimated_avail - 0.9995) * 50000  # Scale 99.95-99.99 to 70-90
            evidence.append("High availability (nearly 4 nines)")
            gaps.append("Availability below 99.99%")
            recommendations.append("Implement multi-AZ deployment and comprehensive DR for 4+ nines")
        else:
            level = MaturityLevel.OPTIMIZING
            score = 92.0 + min(8.0, (estimated_avail - 0.9999) * 800000)
            evidence.append("Excellent availability (4+ nines)")
            recommendations.append("Maintain through continuous chaos testing and SLO monitoring")

        return DimensionAssessment(
            dimension=MaturityDimension.AVAILABILITY,
            level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _assess_disaster_recovery(self, graph: InfraGraph) -> DimensionAssessment:
        """Assess disaster recovery maturity.

        L1: No replicas or failover
        L2: Some replicas
        L3: Multi-replica + failover on critical
        L4: Multi-AZ + comprehensive failover
        L5: Multi-region + automated DR testing
        """
        components = list(graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.DISASTER_RECOVERY,
                level=MaturityLevel.INITIAL,
                score=0.0,
            )

        total = len(components)
        has_replicas = sum(1 for c in components if c.replicas > 1)
        has_failover = sum(1 for c in components if c.failover.enabled)
        has_az = sum(1 for c in components if c.region.availability_zone != "")
        has_dr_region = sum(1 for c in components if c.region.dr_target_region != "")
        has_backup = sum(1 for c in components if c.security.backup_enabled)

        rep_ratio = has_replicas / total
        fo_ratio = has_failover / total
        az_ratio = has_az / total
        dr_ratio = has_dr_region / total
        backup_ratio = has_backup / total

        evidence: list[str] = []
        gaps: list[str] = []
        recommendations: list[str] = []

        if rep_ratio == 0 and fo_ratio == 0:
            level = MaturityLevel.INITIAL
            score = 10.0
            gaps.append("No replicas or failover configured")
            recommendations.append("Add replicas to databases and critical services")
            recommendations.append("Enable failover configuration for high-availability")
        elif fo_ratio < 0.25 or rep_ratio < 0.5:
            level = MaturityLevel.MANAGED
            score = 25.0 + (rep_ratio * 15.0) + (backup_ratio * 10.0)
            evidence.append(f"Replicas: {rep_ratio:.0%}, Backups: {backup_ratio:.0%}")
            gaps.append("Limited failover and replica coverage")
            recommendations.append("Enable failover on critical components and ensure backup coverage")
        elif az_ratio < 0.25:
            level = MaturityLevel.DEFINED
            score = 50.0 + (fo_ratio * 15.0) + (backup_ratio * 5.0)
            evidence.append(f"Replicas: {rep_ratio:.0%}, Failover: {fo_ratio:.0%}")
            gaps.append("No multi-AZ deployment")
            recommendations.append("Deploy components across availability zones for AZ-level resilience")
        elif dr_ratio < 0.25:
            level = MaturityLevel.QUANTITATIVE
            score = 70.0 + (az_ratio * 10.0) + (fo_ratio * 10.0)
            evidence.append(f"Multi-AZ: {az_ratio:.0%}, Failover: {fo_ratio:.0%}")
            gaps.append("No multi-region DR configuration")
            recommendations.append("Configure DR target regions for multi-region resilience")
        else:
            level = MaturityLevel.OPTIMIZING
            score = 90.0 + min(10.0, (dr_ratio + fo_ratio) * 5.0)
            evidence.append("Multi-region DR with comprehensive failover")
            recommendations.append("Implement automated DR testing (GameDay exercises)")

        return DimensionAssessment(
            dimension=MaturityDimension.DISASTER_RECOVERY,
            level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _assess_security(self, graph: InfraGraph) -> DimensionAssessment:
        """Assess security posture maturity.

        L1: No security controls
        L2: Basic encryption
        L3: Encryption + network segmentation + auth
        L4: WAF + rate limiting + IDS + logging
        L5: Full security posture with patching SLA
        """
        components = list(graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.SECURITY,
                level=MaturityLevel.INITIAL,
                score=0.0,
            )

        total = len(components)
        has_encrypt_rest = sum(1 for c in components if c.security.encryption_at_rest)
        has_encrypt_transit = sum(1 for c in components if c.security.encryption_in_transit)
        has_auth = sum(1 for c in components if c.security.auth_required)
        has_segmentation = sum(1 for c in components if c.security.network_segmented)
        has_waf = sum(1 for c in components if c.security.waf_protected)
        has_rate_limit = sum(1 for c in components if c.security.rate_limiting)
        has_ids = sum(1 for c in components if c.security.ids_monitored)
        has_log = sum(1 for c in components if c.security.log_enabled)

        encrypt_ratio = (has_encrypt_rest + has_encrypt_transit) / (total * 2)
        auth_ratio = has_auth / total
        segmentation_ratio = has_segmentation / total
        has_waf / total
        advanced_ratio = (has_rate_limit + has_ids + has_log) / (total * 3)

        evidence: list[str] = []
        gaps: list[str] = []
        recommendations: list[str] = []

        if encrypt_ratio == 0 and auth_ratio == 0:
            level = MaturityLevel.INITIAL
            score = 5.0
            gaps.append("No encryption or authentication configured")
            recommendations.append("Enable encryption at rest and in transit for all components")
            recommendations.append("Require authentication on all services")
        elif encrypt_ratio < 0.5 or auth_ratio < 0.5:
            level = MaturityLevel.MANAGED
            score = 20.0 + (encrypt_ratio * 20.0) + (auth_ratio * 10.0)
            evidence.append(f"Encryption: {encrypt_ratio:.0%}, Auth: {auth_ratio:.0%}")
            gaps.append("Incomplete encryption or authentication coverage")
            recommendations.append("Enable encryption and auth on all components")
        elif segmentation_ratio < 0.5:
            level = MaturityLevel.DEFINED
            score = 50.0 + (segmentation_ratio * 20.0)
            evidence.append(f"Encryption: {encrypt_ratio:.0%}, Auth: {auth_ratio:.0%}")
            gaps.append("Insufficient network segmentation")
            recommendations.append("Implement network segmentation for blast radius containment")
        elif advanced_ratio < 0.5:
            level = MaturityLevel.QUANTITATIVE
            score = 70.0 + (advanced_ratio * 20.0)
            evidence.append(f"Segmentation: {segmentation_ratio:.0%}, Advanced: {advanced_ratio:.0%}")
            gaps.append("WAF, rate limiting, or IDS coverage incomplete")
            recommendations.append("Deploy WAF, enable rate limiting, and activate IDS monitoring")
        else:
            level = MaturityLevel.OPTIMIZING
            score = 92.0 + min(8.0, advanced_ratio * 8.0)
            evidence.append("Comprehensive security posture")
            recommendations.append("Implement automated vulnerability scanning and patching")

        return DimensionAssessment(
            dimension=MaturityDimension.SECURITY,
            level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _assess_automation(self, graph: InfraGraph) -> DimensionAssessment:
        """Assess automation & self-healing maturity.

        L1: No automation
        L2: Some autoscaling
        L3: Autoscaling + failover + circuit breakers
        L4: Auto-remediation with comprehensive coverage
        L5: Self-healing with predictive capabilities
        """
        components = list(graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.AUTOMATION,
                level=MaturityLevel.INITIAL,
                score=0.0,
            )

        total = len(components)
        has_autoscaling = sum(1 for c in components if c.autoscaling.enabled)
        has_failover = sum(1 for c in components if c.failover.enabled)

        all_edges = graph.all_dependency_edges()
        has_cb = sum(1 for e in all_edges if e.circuit_breaker.enabled)
        has_retry = sum(1 for e in all_edges if e.retry_strategy.enabled)
        total_edges = len(all_edges)

        has_singleflight = sum(1 for c in components if c.singleflight.enabled)

        as_ratio = has_autoscaling / total
        fo_ratio = has_failover / total
        cb_ratio = has_cb / total_edges if total_edges > 0 else 0.0
        retry_ratio = has_retry / total_edges if total_edges > 0 else 0.0
        has_singleflight / total

        auto_score = (as_ratio + fo_ratio + cb_ratio + retry_ratio) / 4.0

        evidence: list[str] = []
        gaps: list[str] = []
        recommendations: list[str] = []

        if auto_score < 0.1:
            level = MaturityLevel.INITIAL
            score = 10.0
            gaps.append("No automation configured")
            recommendations.append("Enable autoscaling and failover on critical components")
        elif auto_score < 0.3:
            level = MaturityLevel.MANAGED
            score = 25.0 + (auto_score * 83.0)
            evidence.append(f"AS: {as_ratio:.0%}, FO: {fo_ratio:.0%}")
            gaps.append("Limited automation coverage")
            recommendations.append("Add circuit breakers and retry strategies to dependency edges")
        elif auto_score < 0.6:
            level = MaturityLevel.DEFINED
            score = 50.0 + (auto_score * 33.0)
            evidence.append(f"AS: {as_ratio:.0%}, FO: {fo_ratio:.0%}, CB: {cb_ratio:.0%}")
            gaps.append("Automation covers less than 60% of components")
            recommendations.append("Expand automation to all components for self-healing capability")
        elif auto_score < 0.85:
            level = MaturityLevel.QUANTITATIVE
            score = 70.0 + (auto_score * 23.5)
            evidence.append(
                f"AS: {as_ratio:.0%}, FO: {fo_ratio:.0%}, CB: {cb_ratio:.0%}, Retry: {retry_ratio:.0%}"
            )
            gaps.append("Not yet at full auto-remediation")
            recommendations.append("Complete automation coverage and add singleflight for request dedup")
        else:
            level = MaturityLevel.OPTIMIZING
            score = 90.0 + min(10.0, auto_score * 11.0)
            evidence.append("Comprehensive automation with self-healing capabilities")
            recommendations.append("Implement predictive scaling and ML-based anomaly detection")

        return DimensionAssessment(
            dimension=MaturityDimension.AUTOMATION,
            level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            recommendations=recommendations,
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _score_to_level(self, score: float) -> MaturityLevel:
        """Convert a 0-100 score to a maturity level."""
        if score >= 90:
            return MaturityLevel.OPTIMIZING
        elif score >= 70:
            return MaturityLevel.QUANTITATIVE
        elif score >= 50:
            return MaturityLevel.DEFINED
        elif score >= 25:
            return MaturityLevel.MANAGED
        else:
            return MaturityLevel.INITIAL

    def _estimate_system_availability(self, graph: InfraGraph) -> float:
        """Estimate system availability from component configurations.

        Uses a simplified model: critical path availability = product of
        component availabilities, where each component's availability is
        derived from MTBF, MTTR, and replicas.
        """
        components = list(graph.components.values())
        if not components:
            return 0.0

        # Calculate per-component availability
        component_avails: dict[str, float] = {}
        for comp in components:
            base_avail = self._component_availability(comp)
            component_avails[comp.id] = base_avail

        # Find critical paths and calculate path availability
        critical_paths = graph.get_critical_paths()
        if not critical_paths:
            # No paths (isolated components) - use worst single component
            return min(component_avails.values()) if component_avails else 0.99

        # System availability = minimum path availability
        path_avails = []
        for path in critical_paths[:10]:  # Limit to top 10 paths
            path_avail = 1.0
            for comp_id in path:
                if comp_id in component_avails:
                    path_avail *= component_avails[comp_id]
            path_avails.append(path_avail)

        return min(path_avails) if path_avails else 0.99

    def _component_availability(self, comp: Component) -> float:
        """Estimate a single component's availability."""
        mtbf = comp.operational_profile.mtbf_hours
        mttr = comp.operational_profile.mttr_minutes / 60.0  # Convert to hours

        if mtbf <= 0:
            # Use defaults based on component type
            mtbf = _DEFAULT_MTBF.get(comp.type.value, 2160.0)

        # Base availability = MTBF / (MTBF + MTTR)
        base_avail = mtbf / (mtbf + mttr) if (mtbf + mttr) > 0 else 0.99

        # Multi-replica availability: 1 - (1 - base)^replicas
        if comp.replicas > 1:
            unavail = (1.0 - base_avail) ** comp.replicas
            effective_avail = 1.0 - unavail
        else:
            effective_avail = base_avail

        # Failover bonus
        if comp.failover.enabled:
            # Failover reduces MTTR significantly
            effective_unavail = 1.0 - effective_avail
            promotion_hours = comp.failover.promotion_time_seconds / 3600.0
            if mttr > 0:
                reduction = promotion_hours / mttr
                effective_avail = 1.0 - (effective_unavail * min(1.0, reduction))

        return min(1.0, max(0.0, effective_avail))

    @staticmethod
    def _availability_to_nines(avail: float) -> float:
        """Convert availability fraction to number of nines."""
        import math
        if avail >= 1.0:
            return 9.0
        if avail <= 0.0:
            return 0.0
        return -math.log10(1.0 - avail)

    @staticmethod
    def _estimate_effort(current: int, target: int) -> str:
        """Estimate effort to move from current level to target level."""
        gap = target - current
        if gap <= 0:
            return "None"
        elif gap == 1:
            if current <= 2:
                return "Low"
            else:
                return "Medium"
        else:
            return "High"

    @staticmethod
    def _generate_industry_comparison(score: float) -> str:
        """Generate industry comparison text based on overall score."""
        if score >= 90:
            return (
                "Your SRE maturity is at the Optimizing level, comparable to top-tier "
                "organizations like Google, Netflix, and Amazon. You demonstrate industry-leading "
                "practices in automation, reliability, and incident response."
            )
        elif score >= 70:
            return (
                "Your SRE maturity is Quantitatively Managed, on par with mature technology "
                "companies. You have strong foundations but can improve automation and "
                "predictive capabilities to reach the top tier."
            )
        elif score >= 50:
            return (
                "Your SRE maturity is at the Defined level, typical of mid-size technology "
                "companies. You have established processes but need to invest in automation "
                "and data-driven decision making."
            )
        elif score >= 25:
            return (
                "Your SRE maturity is at the Managed level. Basic monitoring and alerting "
                "are in place, but significant gaps exist in automation, disaster recovery, "
                "and incident response."
            )
        else:
            return (
                "Your SRE maturity is at the Initial/Ad-hoc level. Infrastructure lacks "
                "basic reliability controls. Immediate investment in monitoring, failover, "
                "and redundancy is strongly recommended."
            )


# Default MTBF hours by component type (when not specified in component config)
_DEFAULT_MTBF: dict[str, float] = {
    "app_server": 2160.0,
    "web_server": 2160.0,
    "database": 4320.0,
    "cache": 1440.0,
    "load_balancer": 8760.0,
    "queue": 2160.0,
    "dns": 43800.0,
    "storage": 8760.0,
    "external_api": 8760.0,
    "custom": 2160.0,
}
