# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Change Velocity Impact Analyzer.

Analyzes how deployment frequency and change rate affect infrastructure
stability using the DORA metrics framework (DevOps Research and Assessment).

DORA Classifications:
  - Elite:  Deploy on demand, <5% CFR, <1h MTTR, <1h lead time
  - High:   Deploys/week, <10% CFR, <1d MTTR, <1w lead time
  - Medium: Deploys/month, <15% CFR, <1w MTTR, <1m lead time
  - Low:    Deploy/6mo, >15% CFR, >1m MTTR, >6m lead time
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


@dataclass
class ChangeVelocityProfile:
    """Input profile describing change velocity metrics."""

    deploys_per_week: float
    change_failure_rate: float  # percentage of deploys causing incidents
    mttr_minutes: float  # mean time to recovery
    lead_time_hours: float  # commit to production


@dataclass
class VelocityImpactReport:
    """Report on how change velocity affects infrastructure stability."""

    current_velocity: ChangeVelocityProfile
    dora_classification: str  # "Elite", "High", "Medium", "Low"
    stability_impact: float  # 0-100, how velocity affects availability
    optimal_deploy_frequency: float  # recommended deploys/week
    recommendations: list[str] = field(default_factory=list)
    dora_scores: dict[str, str] = field(default_factory=dict)
    estimated_downtime_minutes_per_week: float = 0.0
    architecture_risk_factors: list[str] = field(default_factory=list)


class ChangeVelocityAnalyzer:
    """Analyze impact of change velocity on infrastructure stability.

    Uses the DORA metrics framework to classify deployment performance
    and estimate stability impact based on the infrastructure graph.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def analyze(
        self,
        deploys_per_week: float = 10,
        change_failure_rate: float = 5.0,
        mttr_minutes: float = 60,
        lead_time_hours: float = 24,
    ) -> VelocityImpactReport:
        """Analyze impact of change velocity on infrastructure stability.

        Args:
            deploys_per_week: Number of deployments per week.
            change_failure_rate: Percentage of deploys that cause incidents (0-100).
            mttr_minutes: Mean time to recovery in minutes.
            lead_time_hours: Lead time from commit to production in hours.

        Returns:
            VelocityImpactReport with DORA classification and stability analysis.
        """
        profile = ChangeVelocityProfile(
            deploys_per_week=deploys_per_week,
            change_failure_rate=change_failure_rate,
            mttr_minutes=mttr_minutes,
            lead_time_hours=lead_time_hours,
        )

        # Step 1: DORA classification
        dora_class = self._classify_dora(profile)
        dora_scores = self._compute_dora_scores(profile)

        # Step 2: Calculate stability impact
        stability_impact = self._compute_stability_impact(profile)

        # Step 3: Estimate weekly downtime
        downtime = self._estimate_weekly_downtime(profile)

        # Step 4: Find optimal deploy frequency for this architecture
        optimal_freq = self._compute_optimal_frequency(profile)

        # Step 5: Analyze architecture risk factors
        arch_risks = self._analyze_architecture_risks(profile)

        # Step 6: Generate recommendations
        recommendations = self._generate_recommendations(
            profile, dora_class, stability_impact, arch_risks,
        )

        return VelocityImpactReport(
            current_velocity=profile,
            dora_classification=dora_class,
            stability_impact=round(stability_impact, 1),
            optimal_deploy_frequency=round(optimal_freq, 1),
            recommendations=recommendations,
            dora_scores=dora_scores,
            estimated_downtime_minutes_per_week=round(downtime, 2),
            architecture_risk_factors=arch_risks,
        )

    def simulate_velocity_sweep(
        self,
        deploy_range: list[float] | None = None,
        change_failure_rate: float = 5.0,
        mttr_minutes: float = 60,
        lead_time_hours: float = 24,
    ) -> list[dict]:
        """Simulate how different deploy frequencies affect availability.

        Runs the analysis at multiple deploy frequencies and returns a
        list of results for comparison.

        Args:
            deploy_range: List of deploy frequencies to test. Defaults
                to [1, 5, 10, 20, 50].
            change_failure_rate: Fixed CFR for all simulations.
            mttr_minutes: Fixed MTTR for all simulations.
            lead_time_hours: Fixed lead time for all simulations.

        Returns:
            List of dicts with deploy frequency and impact metrics.
        """
        if deploy_range is None:
            deploy_range = [1, 5, 10, 20, 50]

        results: list[dict] = []

        for freq in deploy_range:
            report = self.analyze(
                deploys_per_week=freq,
                change_failure_rate=change_failure_rate,
                mttr_minutes=mttr_minutes,
                lead_time_hours=lead_time_hours,
            )
            results.append({
                "deploys_per_week": freq,
                "dora_classification": report.dora_classification,
                "stability_impact": report.stability_impact,
                "estimated_downtime_minutes_per_week": report.estimated_downtime_minutes_per_week,
                "optimal_deploy_frequency": report.optimal_deploy_frequency,
                "recommendation_count": len(report.recommendations),
            })

        return results

    # ------------------------------------------------------------------
    # DORA Classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_dora(profile: ChangeVelocityProfile) -> str:
        """Classify deployment performance using DORA metrics.

        Uses the standard DORA four-key metrics classification:
        - Deployment Frequency
        - Lead Time for Changes
        - Change Failure Rate
        - Time to Restore (MTTR)
        """
        scores = {
            "deploy_freq": _classify_deploy_freq(profile.deploys_per_week),
            "lead_time": _classify_lead_time(profile.lead_time_hours),
            "cfr": _classify_cfr(profile.change_failure_rate),
            "mttr": _classify_mttr(profile.mttr_minutes),
        }

        # Overall classification is the lowest (worst) of all dimensions
        level_order = ["Low", "Medium", "High", "Elite"]
        levels = [scores[k] for k in scores]
        min_index = min(level_order.index(lv) for lv in levels)
        return level_order[min_index]

    @staticmethod
    def _compute_dora_scores(profile: ChangeVelocityProfile) -> dict[str, str]:
        """Return per-metric DORA classification."""
        return {
            "deployment_frequency": _classify_deploy_freq(profile.deploys_per_week),
            "lead_time": _classify_lead_time(profile.lead_time_hours),
            "change_failure_rate": _classify_cfr(profile.change_failure_rate),
            "mttr": _classify_mttr(profile.mttr_minutes),
        }

    # ------------------------------------------------------------------
    # Stability Impact
    # ------------------------------------------------------------------

    def _compute_stability_impact(self, profile: ChangeVelocityProfile) -> float:
        """Compute how change velocity affects system stability (0-100).

        Higher score = more stable (less negative impact).
        Score is based on:
        - Change failure rate (major factor)
        - MTTR relative to deploy frequency
        - Architecture resilience features
        """
        # Base stability score from CFR (0-40 points)
        if profile.change_failure_rate <= 1:
            cfr_score = 40.0
        elif profile.change_failure_rate <= 5:
            cfr_score = 35.0
        elif profile.change_failure_rate <= 10:
            cfr_score = 25.0
        elif profile.change_failure_rate <= 15:
            cfr_score = 15.0
        else:
            cfr_score = max(0.0, 15.0 - (profile.change_failure_rate - 15) * 0.5)

        # MTTR score (0-30 points)
        if profile.mttr_minutes <= 5:
            mttr_score = 30.0
        elif profile.mttr_minutes <= 60:
            mttr_score = 25.0
        elif profile.mttr_minutes <= 1440:  # 1 day
            mttr_score = 15.0
        elif profile.mttr_minutes <= 10080:  # 1 week
            mttr_score = 5.0
        else:
            mttr_score = 0.0

        # Architecture resilience score (0-30 points)
        arch_score = self._architecture_resilience_score()

        return min(100.0, cfr_score + mttr_score + arch_score)

    def _architecture_resilience_score(self) -> float:
        """Assess how well the architecture supports rapid deployments.

        Checks for features that reduce deployment risk:
        - Replica count (allows rolling deploys)
        - Autoscaling (handles deploy-induced load)
        - Circuit breakers (contain failures)
        - Failover (automatic recovery)
        """
        if not self.graph.components:
            return 15.0  # neutral score for empty graph

        score = 0.0
        num_components = len(self.graph.components)

        for comp in self.graph.components.values():
            comp_score = 0.0

            # Replicas enable rolling deploys
            if comp.replicas >= 2:
                comp_score += 3.0
            elif comp.replicas >= 3:
                comp_score += 5.0

            # Autoscaling handles deploy spikes
            if comp.autoscaling.enabled:
                comp_score += 3.0

            # Failover allows automatic recovery
            if comp.failover.enabled:
                comp_score += 2.0

            score += comp_score

        # Check for circuit breakers on dependency edges
        edges = self.graph.all_dependency_edges()
        if edges:
            cb_count = sum(1 for e in edges if e.circuit_breaker.enabled)
            cb_ratio = cb_count / len(edges)
            score += cb_ratio * 5.0

        # Normalize to 0-30 range
        max_possible = num_components * 10.0 + 5.0
        normalized = (score / max_possible * 30.0) if max_possible > 0 else 15.0
        return min(30.0, normalized)

    # ------------------------------------------------------------------
    # Downtime Estimation
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_weekly_downtime(profile: ChangeVelocityProfile) -> float:
        """Estimate weekly downtime in minutes from change velocity.

        Formula: deploys_per_week * (change_failure_rate / 100) * mttr_minutes
        """
        failures_per_week = profile.deploys_per_week * (profile.change_failure_rate / 100)
        return failures_per_week * profile.mttr_minutes

    # ------------------------------------------------------------------
    # Optimal Frequency
    # ------------------------------------------------------------------

    def _compute_optimal_frequency(self, profile: ChangeVelocityProfile) -> float:
        """Compute optimal deployment frequency for this architecture.

        The sweet spot balances:
        - Batch size (fewer deploys = larger changes = higher risk per deploy)
        - Recovery capability (more deploys = more chances for failure)
        - Architecture resilience (better arch = can deploy more often)
        """
        # Base: 10 deploys/week is a good default for most architectures
        base_freq = 10.0

        # Adjust based on CFR: higher CFR suggests slower
        if profile.change_failure_rate > 15:
            base_freq *= 0.3
        elif profile.change_failure_rate > 10:
            base_freq *= 0.5
        elif profile.change_failure_rate > 5:
            base_freq *= 0.8

        # Adjust based on MTTR: higher MTTR suggests slower
        if profile.mttr_minutes > 1440:
            base_freq *= 0.5
        elif profile.mttr_minutes > 60:
            base_freq *= 0.7
        elif profile.mttr_minutes <= 5:
            base_freq *= 1.5  # excellent recovery = can go faster

        # Adjust based on architecture resilience
        arch_score = self._architecture_resilience_score()
        if arch_score >= 25:
            base_freq *= 1.3  # great architecture supports faster deploys
        elif arch_score < 10:
            base_freq *= 0.7  # weak architecture needs slower deploys

        return max(1.0, base_freq)

    # ------------------------------------------------------------------
    # Architecture Risk Factors
    # ------------------------------------------------------------------

    def _analyze_architecture_risks(
        self, profile: ChangeVelocityProfile,
    ) -> list[str]:
        """Identify architecture risk factors for the given velocity."""
        risks: list[str] = []

        for comp in self.graph.components.values():
            # Single replica services can't do rolling deploys
            if comp.replicas <= 1 and profile.deploys_per_week >= 5:
                risks.append(
                    f"'{comp.name}' has single replica - rolling deploys not possible. "
                    f"At {profile.deploys_per_week} deploys/week, this causes unavoidable downtime."
                )

            # Stateful services without failover are risky for frequent deploys
            if comp.type in {ComponentType.DATABASE, ComponentType.CACHE}:
                if not comp.failover.enabled and profile.deploys_per_week >= 3:
                    risks.append(
                        f"'{comp.name}' ({comp.type.value}) lacks failover. "
                        f"Deploys to stateful services without failover risk data loss."
                    )

            # High deploy_downtime relative to frequency
            deploy_seconds = comp.operational_profile.deploy_downtime_seconds
            if deploy_seconds > 0 and profile.deploys_per_week > 0:
                weekly_deploy_downtime = deploy_seconds * profile.deploys_per_week
                if weekly_deploy_downtime > 3600:  # > 1 hour/week
                    risks.append(
                        f"'{comp.name}' deploy downtime ({deploy_seconds}s) x "
                        f"{profile.deploys_per_week} deploys/week = "
                        f"{weekly_deploy_downtime / 60:.0f}min/week of deploy-induced downtime."
                    )

        # Check for missing circuit breakers
        edges = self.graph.all_dependency_edges()
        if edges:
            missing_cb = sum(1 for e in edges if not e.circuit_breaker.enabled)
            if missing_cb > 0 and profile.deploys_per_week >= 10:
                risks.append(
                    f"{missing_cb}/{len(edges)} dependency edges lack circuit breakers. "
                    f"At {profile.deploys_per_week} deploys/week, deploy-induced failures "
                    f"can cascade without protection."
                )

        return risks

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_recommendations(
        profile: ChangeVelocityProfile,
        dora_class: str,
        stability_impact: float,
        arch_risks: list[str],
    ) -> list[str]:
        """Generate recommendations to improve change velocity and stability."""
        recommendations: list[str] = []

        # DORA classification improvements
        if dora_class == "Low":
            recommendations.append(
                "Consider moving to CI/CD to increase deployment frequency. "
                "Smaller, more frequent deploys reduce risk per deploy."
            )
        elif dora_class == "Medium":
            recommendations.append(
                "Focus on reducing MTTR through runbooks and automated rollback. "
                "Aim for weekly deployments with < 10% failure rate."
            )

        # CFR-specific recommendations
        if profile.change_failure_rate > 15:
            recommendations.append(
                "Change failure rate is critically high (>15%). "
                "Implement pre-deploy testing gates, canary deployments, and "
                "feature flags to reduce deployment risk."
            )
        elif profile.change_failure_rate > 10:
            recommendations.append(
                "Change failure rate is elevated (>10%). "
                "Consider adding integration tests and staging environment validation."
            )

        # MTTR-specific recommendations
        if profile.mttr_minutes > 1440:
            recommendations.append(
                "MTTR exceeds 1 day. Prioritize automated monitoring, "
                "alerting, and runbook-based recovery to reduce recovery time."
            )
        elif profile.mttr_minutes > 60:
            recommendations.append(
                "MTTR exceeds 1 hour. Consider automated rollback mechanisms "
                "and better observability for faster incident diagnosis."
            )

        # Lead time recommendations
        if profile.lead_time_hours > 168:  # > 1 week
            recommendations.append(
                "Lead time exceeds 1 week. Streamline CI/CD pipeline, "
                "reduce manual approval gates, and consider trunk-based development."
            )

        # Stability-specific recommendations
        if stability_impact < 50:
            recommendations.append(
                "Overall stability impact score is low. "
                "Address architecture risk factors before increasing deploy velocity."
            )

        # If at Elite level, give positive reinforcement
        if dora_class == "Elite" and stability_impact >= 80:
            recommendations.append(
                "Deployment performance is at Elite level with high stability. "
                "Continue current practices and consider sharing knowledge with other teams."
            )

        return recommendations


# ------------------------------------------------------------------
# DORA Classification Helpers (module-level for reuse)
# ------------------------------------------------------------------


def _classify_deploy_freq(deploys_per_week: float) -> str:
    """Classify deployment frequency."""
    if deploys_per_week >= 7:  # daily or more
        return "Elite"
    elif deploys_per_week >= 1:  # weekly
        return "High"
    elif deploys_per_week >= 0.25:  # monthly
        return "Medium"
    else:
        return "Low"


def _classify_lead_time(lead_time_hours: float) -> str:
    """Classify lead time for changes."""
    if lead_time_hours <= 1:
        return "Elite"
    elif lead_time_hours <= 168:  # 1 week
        return "High"
    elif lead_time_hours <= 720:  # 1 month
        return "Medium"
    else:
        return "Low"


def _classify_cfr(cfr: float) -> str:
    """Classify change failure rate."""
    if cfr <= 5:
        return "Elite"
    elif cfr <= 10:
        return "High"
    elif cfr <= 15:
        return "Medium"
    else:
        return "Low"


def _classify_mttr(mttr_minutes: float) -> str:
    """Classify mean time to recovery."""
    if mttr_minutes <= 60:
        return "Elite"
    elif mttr_minutes <= 1440:  # 1 day
        return "High"
    elif mttr_minutes <= 10080:  # 1 week
        return "Medium"
    else:
        return "Low"
