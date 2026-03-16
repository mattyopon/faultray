"""Financial Risk Engine.

Estimates the financial impact of infrastructure failures by combining
simulation results (cascade severity, likelihood) with revenue data to
produce Value-at-Risk (VaR) metrics and mitigation ROI analysis.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationReport

logger = logging.getLogger(__name__)

# Default revenue assumption when not specified.
_DEFAULT_ANNUAL_REVENUE = 1_000_000.0
# Minutes per year for revenue-per-minute calculation.
_MINUTES_PER_YEAR = 365.25 * 24 * 60


@dataclass
class FinancialRiskResult:
    """Financial impact of a single failure scenario."""

    scenario_name: str
    probability: float  # 0-1 annual probability
    business_loss_usd: float  # estimated loss per occurrence
    recovery_hours: float  # time to recover


@dataclass
class FinancialRiskReport:
    """Comprehensive financial risk analysis report."""

    annual_revenue_usd: float
    value_at_risk_95: float  # 95th percentile annual loss
    expected_annual_loss: float  # weighted sum of scenario losses
    cost_per_hour_of_risk: float  # expected annual loss / 8760
    scenarios: list[FinancialRiskResult] = field(default_factory=list)
    mitigation_roi: list[dict] = field(default_factory=list)  # [{action, cost, savings, roi_percent}]

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "annual_revenue_usd": round(self.annual_revenue_usd, 2),
            "value_at_risk_95": round(self.value_at_risk_95, 2),
            "expected_annual_loss": round(self.expected_annual_loss, 2),
            "cost_per_hour_of_risk": round(self.cost_per_hour_of_risk, 2),
            "scenarios": [
                {
                    "scenario_name": s.scenario_name,
                    "probability": round(s.probability, 4),
                    "business_loss_usd": round(s.business_loss_usd, 2),
                    "recovery_hours": round(s.recovery_hours, 2),
                }
                for s in self.scenarios
            ],
            "mitigation_roi": self.mitigation_roi,
        }


class FinancialRiskEngine:
    """Estimates financial impact of infrastructure failures.

    Combines cascade simulation results with revenue data to produce
    quantitative risk metrics including Value-at-Risk (VaR95), expected
    annual loss, and mitigation ROI recommendations.

    Parameters
    ----------
    graph:
        The infrastructure graph.
    annual_revenue:
        Annual revenue in USD.  Used to calculate revenue loss per minute
        of downtime.
    """

    def __init__(
        self,
        graph: InfraGraph,
        annual_revenue: float = _DEFAULT_ANNUAL_REVENUE,
    ) -> None:
        self.graph = graph
        self.annual_revenue = max(0.0, annual_revenue)
        self.revenue_per_minute = self.annual_revenue / _MINUTES_PER_YEAR

    def analyze(self, simulation_report: SimulationReport) -> FinancialRiskReport:
        """Analyze financial risk from simulation results.

        Parameters
        ----------
        simulation_report:
            A completed :class:`SimulationReport` from the simulation engine.

        Returns
        -------
        FinancialRiskReport
            Comprehensive financial risk analysis.
        """
        scenarios: list[FinancialRiskResult] = []

        for result in simulation_report.results:
            if not result.is_critical and not result.is_warning:
                continue

            cascade = result.cascade
            scenario_name = result.scenario.name

            # Probability: use cascade likelihood, adjusted by risk score
            probability = cascade.likelihood

            # Estimate recovery time from cascade effects
            recovery_hours = self._estimate_recovery_hours(cascade)

            # Business loss = downtime_minutes * revenue_per_minute
            downtime_minutes = recovery_hours * 60
            business_loss = downtime_minutes * self.revenue_per_minute

            # Add SLA credit costs from affected components
            sla_credits = self._estimate_sla_credits(cascade)
            business_loss += sla_credits

            # Add recovery engineer costs
            engineer_costs = self._estimate_recovery_costs(cascade)
            business_loss += engineer_costs

            scenarios.append(FinancialRiskResult(
                scenario_name=scenario_name,
                probability=probability,
                business_loss_usd=business_loss,
                recovery_hours=recovery_hours,
            ))

        # Sort by expected loss (probability * loss) descending
        scenarios.sort(
            key=lambda s: s.probability * s.business_loss_usd,
            reverse=True,
        )

        # Calculate aggregate metrics
        expected_annual_loss = sum(
            s.probability * s.business_loss_usd for s in scenarios
        )

        # VaR95: 95th percentile loss estimate
        value_at_risk_95 = self._calculate_var95(scenarios)

        # Cost per hour of risk
        cost_per_hour = expected_annual_loss / 8760.0 if expected_annual_loss > 0 else 0.0

        # Mitigation ROI analysis
        mitigation_roi = self._calculate_mitigation_roi(scenarios)

        return FinancialRiskReport(
            annual_revenue_usd=self.annual_revenue,
            value_at_risk_95=value_at_risk_95,
            expected_annual_loss=expected_annual_loss,
            cost_per_hour_of_risk=cost_per_hour,
            scenarios=scenarios,
            mitigation_roi=mitigation_roi,
        )

    def _estimate_recovery_hours(self, cascade) -> float:
        """Estimate recovery time in hours from cascade effects."""
        if not cascade.effects:
            return 0.0

        from faultray.model.components import HealthStatus

        max_recovery = 0.0
        for effect in cascade.effects:
            comp = self.graph.get_component(effect.component_id)
            if comp is None:
                continue

            mttr_minutes = comp.operational_profile.mttr_minutes
            if mttr_minutes <= 0:
                mttr_minutes = 30.0  # default

            # DOWN components take full MTTR; DEGRADED take half
            if effect.health == HealthStatus.DOWN:
                recovery_min = mttr_minutes
            elif effect.health == HealthStatus.OVERLOADED:
                recovery_min = mttr_minutes * 0.5
            else:
                recovery_min = mttr_minutes * 0.25

            # Add estimated cascade time
            recovery_min += effect.estimated_time_seconds / 60.0

            max_recovery = max(max_recovery, recovery_min)

        return max_recovery / 60.0  # convert to hours

    def _estimate_sla_credits(self, cascade) -> float:
        """Estimate SLA credit costs from affected components."""
        total_credits = 0.0

        from faultray.model.components import HealthStatus

        for effect in cascade.effects:
            if effect.health not in (HealthStatus.DOWN, HealthStatus.OVERLOADED):
                continue

            comp = self.graph.get_component(effect.component_id)
            if comp is None:
                continue

            # SLA credit based on cost profile
            if comp.cost_profile.sla_credit_percent > 0:
                monthly_cost = comp.cost_profile.hourly_infra_cost * 730  # hours/month
                credit = monthly_cost * (comp.cost_profile.sla_credit_percent / 100.0)
                total_credits += credit

        return total_credits

    def _estimate_recovery_costs(self, cascade) -> float:
        """Estimate human recovery costs (engineers responding to incident)."""
        from faultray.model.components import HealthStatus

        total_cost = 0.0
        for effect in cascade.effects:
            if effect.health != HealthStatus.DOWN:
                continue

            comp = self.graph.get_component(effect.component_id)
            if comp is None:
                continue

            # Engineer cost for recovery
            engineer_rate = comp.cost_profile.recovery_engineer_cost
            if engineer_rate <= 0:
                engineer_rate = 100.0  # default $100/hr

            mttr_hours = comp.operational_profile.mttr_minutes / 60.0
            team_size = comp.team.team_size if comp.team.team_size > 0 else 2
            total_cost += engineer_rate * mttr_hours * min(team_size, 3)

        return total_cost

    @staticmethod
    def _calculate_var95(scenarios: list[FinancialRiskResult]) -> float:
        """Calculate Value at Risk at 95th percentile.

        Approximation: sort losses by magnitude, find the loss value at
        the 95th percentile of the cumulative probability distribution.
        """
        if not scenarios:
            return 0.0

        # Sort by loss amount ascending
        sorted_scenarios = sorted(scenarios, key=lambda s: s.business_loss_usd)

        # Cumulative probability
        cumulative = 0.0
        for scenario in sorted_scenarios:
            cumulative += scenario.probability
            if cumulative >= 0.95:
                return scenario.business_loss_usd

        # If total probability < 0.95, return the maximum loss
        if sorted_scenarios:
            return sorted_scenarios[-1].business_loss_usd

        return 0.0

    def _calculate_mitigation_roi(
        self, scenarios: list[FinancialRiskResult],
    ) -> list[dict]:
        """Generate mitigation ROI recommendations.

        Analyzes the top risk scenarios and suggests mitigations with
        estimated cost and savings.
        """
        mitigations: list[dict] = []

        # Check for SPOF components
        for comp_id, comp in self.graph.components.items():
            if comp.replicas <= 1:
                dependents = self.graph.get_dependents(comp_id)
                if len(dependents) > 0:
                    # Estimate savings from adding redundancy
                    related_losses = sum(
                        s.probability * s.business_loss_usd
                        for s in scenarios
                        if comp_id in s.scenario_name or comp.name in s.scenario_name
                    )
                    if related_losses <= 0:
                        related_losses = sum(
                            s.probability * s.business_loss_usd for s in scenarios
                        ) * 0.2  # assume 20% attributable

                    estimated_cost = comp.cost_profile.hourly_infra_cost * 730  # monthly
                    if estimated_cost <= 0:
                        estimated_cost = 500.0  # default monthly cost

                    savings = related_losses * 0.7  # 70% risk reduction
                    roi_percent = (
                        ((savings - estimated_cost) / estimated_cost * 100)
                        if estimated_cost > 0
                        else 0.0
                    )

                    mitigations.append({
                        "action": f"Add redundancy to {comp.name} (replicas: 1 -> 2)",
                        "cost": round(estimated_cost, 2),
                        "savings": round(savings, 2),
                        "roi_percent": round(roi_percent, 1),
                    })

        # Check for missing autoscaling
        for comp_id, comp in self.graph.components.items():
            if not comp.autoscaling.enabled and comp.utilization() > 60:
                mitigations.append({
                    "action": f"Enable autoscaling for {comp.name}",
                    "cost": round(comp.cost_profile.hourly_infra_cost * 365, 2),  # ~half month extra
                    "savings": round(self.revenue_per_minute * 60, 2),  # 1 hour saved
                    "roi_percent": 200.0,
                })

        # Check for missing circuit breakers
        edges = self.graph.all_dependency_edges()
        uncovered = [e for e in edges if not e.circuit_breaker.enabled]
        if uncovered and len(uncovered) < len(edges):
            mitigations.append({
                "action": f"Add circuit breakers to {len(uncovered)} unprotected dependencies",
                "cost": 0.0,  # code change only
                "savings": round(
                    sum(s.probability * s.business_loss_usd for s in scenarios) * 0.3,
                    2,
                ),
                "roi_percent": float("inf") if len(uncovered) > 0 else 0.0,
            })

        # Sort by ROI descending (inf first for zero-cost items)
        mitigations.sort(
            key=lambda m: m["roi_percent"] if math.isfinite(m["roi_percent"]) else 1e9,
            reverse=True,
        )

        return mitigations
