# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""SLA Risk Quantifier - Quantify financial and operational risk of SLA violations.

Calculates breach probability, estimated financial penalties, and provides
risk mitigation recommendations based on current infrastructure health.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List

from faultray.model.components import Component, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------


class SLATier(str, Enum):
    """Pre-defined SLA tiers."""

    PLATINUM = "platinum"  # 99.99%
    GOLD = "gold"  # 99.9%
    SILVER = "silver"  # 99.5%
    BRONZE = "bronze"  # 99.0%


@dataclass
class SLADefinition:
    """Full SLA definition for a tier."""

    tier: SLATier
    uptime_target: float  # e.g. 0.9999
    monthly_penalty_rate: float  # percentage of monthly revenue, e.g. 0.25
    max_downtime_minutes_per_month: float  # e.g. 4.32


@dataclass
class ComponentSLARisk:
    """Per-component SLA risk assessment."""

    component_id: str
    component_name: str
    breach_probability: float  # 0-1
    estimated_downtime_minutes: float
    risk_score: float  # 0-100
    risk_factors: List[str]


@dataclass
class SLABreachScenario:
    """A hypothetical SLA breach scenario."""

    description: str
    probability: float  # 0-1
    estimated_penalty_dollars: float
    affected_components: List[str]
    mitigation: str


@dataclass
class SLARiskReport:
    """Complete SLA risk analysis report."""

    tier: SLATier
    overall_breach_probability: float  # 0-1
    overall_risk_score: float  # 0-100
    component_risks: List[ComponentSLARisk]
    breach_scenarios: List[SLABreachScenario]
    total_estimated_penalty: float
    monthly_revenue: float
    recommendations: List[str]
    summary: str


# ---------------------------------------------------------------------------
# SLA Tier Definitions
# ---------------------------------------------------------------------------

SLA_DEFINITIONS: dict[SLATier, SLADefinition] = {
    SLATier.PLATINUM: SLADefinition(
        tier=SLATier.PLATINUM,
        uptime_target=0.9999,
        monthly_penalty_rate=0.25,
        max_downtime_minutes_per_month=4.32,
    ),
    SLATier.GOLD: SLADefinition(
        tier=SLATier.GOLD,
        uptime_target=0.999,
        monthly_penalty_rate=0.15,
        max_downtime_minutes_per_month=43.2,
    ),
    SLATier.SILVER: SLADefinition(
        tier=SLATier.SILVER,
        uptime_target=0.995,
        monthly_penalty_rate=0.10,
        max_downtime_minutes_per_month=216.0,
    ),
    SLATier.BRONZE: SLADefinition(
        tier=SLATier.BRONZE,
        uptime_target=0.99,
        monthly_penalty_rate=0.05,
        max_downtime_minutes_per_month=432.0,
    ),
}


# ---------------------------------------------------------------------------
# Health-to-probability mapping
# ---------------------------------------------------------------------------

_HEALTH_BASE_PROBABILITY: dict[HealthStatus, float] = {
    HealthStatus.HEALTHY: 0.01,
    HealthStatus.DEGRADED: 0.15,
    HealthStatus.OVERLOADED: 0.35,
    HealthStatus.DOWN: 0.95,
}

# Minutes in a 30-day month
_MONTH_MINUTES: float = 30.0 * 24.0 * 60.0


# ---------------------------------------------------------------------------
# SLA Risk Quantifier
# ---------------------------------------------------------------------------


class SLARiskQuantifier:
    """Quantify the financial and operational risk of SLA violations.

    Parameters
    ----------
    graph : InfraGraph
        The infrastructure graph to analyze.
    tier : SLATier
        The SLA tier to evaluate against (default GOLD).
    monthly_revenue : float
        Monthly revenue amount for penalty calculation (default 100000.0).
    """

    def __init__(
        self,
        graph: InfraGraph,
        tier: SLATier = SLATier.GOLD,
        monthly_revenue: float = 100_000.0,
    ) -> None:
        self._graph = graph
        self._tier = tier
        self._monthly_revenue = monthly_revenue

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tier(self, tier: SLATier) -> None:
        """Change the SLA tier."""
        self._tier = tier

    def set_revenue(self, amount: float) -> None:
        """Change the monthly revenue amount."""
        self._monthly_revenue = amount

    def analyze(self) -> SLARiskReport:
        """Run a full SLA risk analysis and return the report."""
        sla_def = SLA_DEFINITIONS[self._tier]

        # Build per-component risks
        component_risks = self._build_component_risks(sla_def)

        # Calculate overall breach probability using parallel reliability
        overall_breach_prob = self._calculate_overall_breach_probability(
            component_risks
        )

        # Overall risk score
        overall_risk_score = min(100.0, overall_breach_prob * 100.0)

        # Financial penalty
        total_penalty = (
            self._monthly_revenue
            * sla_def.monthly_penalty_rate
            * overall_breach_prob
        )

        # Breach scenarios
        breach_scenarios = self._build_breach_scenarios(sla_def)

        # Recommendations
        recommendations = self._build_recommendations(component_risks)

        # Summary
        summary = self._build_summary(
            sla_def,
            overall_breach_prob,
            overall_risk_score,
            total_penalty,
        )

        return SLARiskReport(
            tier=self._tier,
            overall_breach_probability=overall_breach_prob,
            overall_risk_score=overall_risk_score,
            component_risks=component_risks,
            breach_scenarios=breach_scenarios,
            total_estimated_penalty=total_penalty,
            monthly_revenue=self._monthly_revenue,
            recommendations=recommendations,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Component risk calculation
    # ------------------------------------------------------------------

    def _component_breach_probability(self, comp: Component) -> float:
        """Calculate breach probability for a single component.

        - Base probability from health status
        - Reduce by failover factor: if failover enabled, multiply by 0.3
        - Reduce by replica factor: multiply by (1 / replicas)
        """
        base = _HEALTH_BASE_PROBABILITY.get(comp.health, 0.01)

        # Failover reduction
        if comp.failover.enabled:
            base *= 0.3

        # Replica reduction
        replicas = max(comp.replicas, 1)
        base *= 1.0 / replicas

        return min(1.0, max(0.0, base))

    def _component_estimated_downtime(
        self, breach_prob: float, sla_def: SLADefinition
    ) -> float:
        """Estimate downtime minutes based on breach probability."""
        return breach_prob * _MONTH_MINUTES

    def _component_risk_factors(self, comp: Component) -> list[str]:
        """Identify risk factors for a component."""
        factors: list[str] = []

        if comp.health == HealthStatus.DOWN:
            factors.append("Component is DOWN")
        elif comp.health == HealthStatus.OVERLOADED:
            factors.append("Component is OVERLOADED")
        elif comp.health == HealthStatus.DEGRADED:
            factors.append("Component is DEGRADED")

        if comp.replicas <= 1:
            factors.append("Single replica (no redundancy)")

        if not comp.failover.enabled:
            factors.append("Failover not enabled")

        if comp.metrics.cpu_percent > 80:
            factors.append(f"High CPU usage ({comp.metrics.cpu_percent:.0f}%)")

        if comp.metrics.memory_percent > 80:
            factors.append(
                f"High memory usage ({comp.metrics.memory_percent:.0f}%)"
            )

        if comp.metrics.disk_percent > 80:
            factors.append(
                f"High disk usage ({comp.metrics.disk_percent:.0f}%)"
            )

        # Check dependents: if many components depend on this one, it's a risk
        dependents = self._graph.get_dependents(comp.id)
        if len(dependents) > 2:
            factors.append(
                f"High fan-in: {len(dependents)} components depend on this"
            )

        return factors

    def _build_component_risks(
        self, sla_def: SLADefinition
    ) -> list[ComponentSLARisk]:
        """Build per-component risk assessments."""
        risks: list[ComponentSLARisk] = []
        for cid, comp in self._graph.components.items():
            breach_prob = self._component_breach_probability(comp)
            downtime = self._component_estimated_downtime(breach_prob, sla_def)
            risk_score = min(100.0, breach_prob * 100.0)
            risk_factors = self._component_risk_factors(comp)

            risks.append(
                ComponentSLARisk(
                    component_id=cid,
                    component_name=comp.name,
                    breach_probability=breach_prob,
                    estimated_downtime_minutes=downtime,
                    risk_score=risk_score,
                    risk_factors=risk_factors,
                )
            )
        return risks

    # ------------------------------------------------------------------
    # Overall breach probability
    # ------------------------------------------------------------------

    def _calculate_overall_breach_probability(
        self, component_risks: list[ComponentSLARisk]
    ) -> float:
        """Calculate overall breach probability.

        Uses parallel reliability formula:
            overall = 1 - product(1 - individual_probs)
        """
        if not component_risks:
            return 0.0

        product = 1.0
        for cr in component_risks:
            product *= 1.0 - cr.breach_probability

        return min(1.0, max(0.0, 1.0 - product))

    # ------------------------------------------------------------------
    # Breach scenarios
    # ------------------------------------------------------------------

    def _build_breach_scenarios(
        self, sla_def: SLADefinition
    ) -> list[SLABreachScenario]:
        """Generate hypothetical breach scenarios."""
        scenarios: list[SLABreachScenario] = []
        components = self._graph.components

        if not components:
            return scenarios

        # Scenario 1: Single component failure for each non-healthy component
        for cid, comp in components.items():
            if comp.health != HealthStatus.HEALTHY:
                prob = self._component_breach_probability(comp)
                penalty = (
                    self._monthly_revenue
                    * sla_def.monthly_penalty_rate
                    * prob
                )
                scenarios.append(
                    SLABreachScenario(
                        description=f"Component '{comp.name}' failure ({comp.health.value})",
                        probability=prob,
                        estimated_penalty_dollars=penalty,
                        affected_components=[cid],
                        mitigation=self._component_mitigation(comp),
                    )
                )

        # Scenario 2: SPOF failure for single-replica components without failover
        for cid, comp in components.items():
            if (
                comp.replicas <= 1
                and not comp.failover.enabled
                and comp.health == HealthStatus.HEALTHY
            ):
                prob = self._component_breach_probability(comp)
                penalty = (
                    self._monthly_revenue
                    * sla_def.monthly_penalty_rate
                    * prob
                )
                scenarios.append(
                    SLABreachScenario(
                        description=f"SPOF failure: '{comp.name}' has no redundancy",
                        probability=prob,
                        estimated_penalty_dollars=penalty,
                        affected_components=[cid],
                        mitigation="Add replicas and enable failover",
                    )
                )

        # Scenario 3: Cascade failure if dependencies exist
        all_edges = self._graph.all_dependency_edges()
        if all_edges:
            affected = list(components.keys())
            cascade_prob = 0.05
            penalty = (
                self._monthly_revenue
                * sla_def.monthly_penalty_rate
                * cascade_prob
            )
            scenarios.append(
                SLABreachScenario(
                    description="Cascade failure across dependent components",
                    probability=cascade_prob,
                    estimated_penalty_dollars=penalty,
                    affected_components=affected,
                    mitigation="Implement circuit breakers and graceful degradation",
                )
            )

        # Scenario 4: Full outage
        if len(components) > 1:
            full_prob = 0.01
            penalty = (
                self._monthly_revenue
                * sla_def.monthly_penalty_rate
                * full_prob
            )
            scenarios.append(
                SLABreachScenario(
                    description="Full infrastructure outage",
                    probability=full_prob,
                    estimated_penalty_dollars=penalty,
                    affected_components=list(components.keys()),
                    mitigation="Implement multi-region DR strategy",
                )
            )

        return scenarios

    @staticmethod
    def _component_mitigation(comp: Component) -> str:
        """Generate mitigation suggestion for a component."""
        suggestions: list[str] = []
        if comp.health == HealthStatus.DOWN:
            suggestions.append("Restore component to healthy state")
        elif comp.health == HealthStatus.OVERLOADED:
            suggestions.append("Scale resources or reduce load")
        elif comp.health == HealthStatus.DEGRADED:
            suggestions.append("Investigate and resolve degradation")

        if comp.replicas <= 1:
            suggestions.append("Add replicas")
        if not comp.failover.enabled:
            suggestions.append("Enable failover")

        return "; ".join(suggestions) if suggestions else "Monitor closely"

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _build_recommendations(
        self, component_risks: list[ComponentSLARisk]
    ) -> list[str]:
        """Build risk mitigation recommendations based on highest risk factors."""
        recommendations: list[str] = []

        if not component_risks:
            recommendations.append(
                "No components found. Add infrastructure components to analyze."
            )
            return recommendations

        # Sort by risk score descending
        sorted_risks = sorted(
            component_risks, key=lambda r: r.risk_score, reverse=True
        )

        # Top risk components
        for cr in sorted_risks:
            if cr.risk_score > 50:
                recommendations.append(
                    f"CRITICAL: '{cr.component_name}' has risk score "
                    f"{cr.risk_score:.1f}/100. "
                    f"Factors: {', '.join(cr.risk_factors)}"
                )
            elif cr.risk_score > 10:
                recommendations.append(
                    f"WARNING: '{cr.component_name}' has risk score "
                    f"{cr.risk_score:.1f}/100. "
                    f"Factors: {', '.join(cr.risk_factors)}"
                )

        # General recommendations based on aggregated factors
        all_factors: list[str] = []
        for cr in component_risks:
            all_factors.extend(cr.risk_factors)

        single_replica_count = sum(
            1
            for f in all_factors
            if "Single replica" in f
        )
        if single_replica_count > 0:
            recommendations.append(
                f"{single_replica_count} component(s) have single replicas. "
                "Add redundancy to reduce SPOF risk."
            )

        no_failover_count = sum(
            1
            for f in all_factors
            if "Failover not enabled" in f
        )
        if no_failover_count > 0:
            recommendations.append(
                f"{no_failover_count} component(s) lack failover. "
                "Enable failover for automatic recovery."
            )

        down_count = sum(
            1 for f in all_factors if "DOWN" in f
        )
        if down_count > 0:
            recommendations.append(
                f"{down_count} component(s) are DOWN. "
                "Immediate action required to restore service."
            )

        if not recommendations:
            recommendations.append(
                "All components are within acceptable risk levels."
            )

        return recommendations

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        sla_def: SLADefinition,
        overall_breach_prob: float,
        overall_risk_score: float,
        total_penalty: float,
    ) -> str:
        """Build a human-readable summary."""
        lines = [
            f"SLA Risk Report ({self._tier.value} tier)",
            f"  Uptime target: {sla_def.uptime_target * 100:.2f}%",
            f"  Max downtime: {sla_def.max_downtime_minutes_per_month:.2f} min/month",
            f"  Monthly revenue: ${self._monthly_revenue:,.2f}",
            f"  Overall breach probability: {overall_breach_prob:.4f}",
            f"  Overall risk score: {overall_risk_score:.1f}/100",
            f"  Estimated monthly penalty: ${total_penalty:,.2f}",
        ]
        return "\n".join(lines)
