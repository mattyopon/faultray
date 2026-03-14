"""Cost Impact Engine - calculates business cost of failure scenarios.

Transforms simulation results into monetary impact estimates by combining
infrastructure costs, revenue loss, SLA penalties, and recovery costs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from infrasim.model.components import HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.simulator.engine import SimulationReport

logger = logging.getLogger(__name__)

# Default number of engineers involved in incident recovery.
DEFAULT_NUM_ENGINEERS = 2

# Multiplier from cascade severity (0-10) to estimated downtime minutes.
# A severity-10 scenario (full system outage) maps to ~60 min downtime.
SEVERITY_TO_DOWNTIME_FACTOR = 6.0

# Monthly window in minutes for SLA credit calculations (30 days).
MONTHLY_MINUTES = 30 * 24 * 60


@dataclass
class ScenarioCostImpact:
    """Cost impact breakdown for a single scenario."""

    scenario_name: str
    scenario_id: str
    severity: float
    downtime_minutes: float
    business_loss: float
    sla_penalty: float
    recovery_cost: float
    total_impact: float


@dataclass
class CostImpactReport:
    """Aggregated cost impact report across all scenarios."""

    impacts: list[ScenarioCostImpact] = field(default_factory=list)
    total_annual_risk: float = 0.0
    highest_impact_scenario: str = ""
    summary: str = ""


class CostImpactEngine:
    """Calculates monetary cost impact from simulation results.

    Takes a :class:`SimulationReport` (produced by :class:`SimulationEngine`)
    and an :class:`InfraGraph` to compute per-scenario cost breakdowns.
    """

    def __init__(
        self,
        graph: InfraGraph,
        num_engineers: int = DEFAULT_NUM_ENGINEERS,
    ) -> None:
        self.graph = graph
        self.num_engineers = num_engineers

    def analyze(self, report: SimulationReport) -> CostImpactReport:
        """Analyze all scenario results and produce a cost impact report.

        Args:
            report: The simulation report containing scenario results.

        Returns:
            A :class:`CostImpactReport` with scenarios ranked by total impact.
        """
        impacts: list[ScenarioCostImpact] = []

        for result in report.results:
            cascade = result.cascade
            scenario = result.scenario

            if not cascade.effects:
                # No effects means no cost impact.
                impacts.append(ScenarioCostImpact(
                    scenario_name=scenario.name,
                    scenario_id=scenario.id,
                    severity=0.0,
                    downtime_minutes=0.0,
                    business_loss=0.0,
                    sla_penalty=0.0,
                    recovery_cost=0.0,
                    total_impact=0.0,
                ))
                continue

            severity = cascade.severity

            # --- Downtime estimation ---
            # Sum per-component downtime weighted by health status.
            downtime_minutes = self._estimate_downtime(cascade.effects, severity)

            # --- Business loss ---
            business_loss = self._calculate_business_loss(
                cascade.effects, downtime_minutes,
            )

            # --- SLA penalty ---
            sla_penalty = self._calculate_sla_penalty(
                cascade.effects, downtime_minutes,
            )

            # --- Recovery cost ---
            recovery_cost = self._calculate_recovery_cost(
                cascade.effects, downtime_minutes,
            )

            total_impact = business_loss + sla_penalty + recovery_cost

            impacts.append(ScenarioCostImpact(
                scenario_name=scenario.name,
                scenario_id=scenario.id,
                severity=severity,
                downtime_minutes=round(downtime_minutes, 2),
                business_loss=round(business_loss, 2),
                sla_penalty=round(sla_penalty, 2),
                recovery_cost=round(recovery_cost, 2),
                total_impact=round(total_impact, 2),
            ))

        # Sort by total impact descending (highest cost first).
        impacts.sort(key=lambda i: i.total_impact, reverse=True)

        # --- Annual risk ---
        # total_annual_risk = sum(impact * annual_probability) for each scenario.
        # We approximate annual probability from the cascade likelihood.
        total_annual_risk = 0.0
        for impact in impacts:
            # Find the matching result to get the likelihood.
            matching = [
                r for r in report.results
                if r.scenario.id == impact.scenario_id
            ]
            if matching:
                likelihood = matching[0].cascade.likelihood
                # Annualize: assume the likelihood represents a per-incident
                # probability, and incidents could occur ~12 times/year.
                annual_probability = min(1.0, likelihood) * 12.0
                total_annual_risk += impact.total_impact * annual_probability

        total_annual_risk = round(total_annual_risk, 2)

        highest = impacts[0].scenario_name if impacts else ""

        # Build summary.
        critical_count = sum(1 for i in impacts if i.total_impact > 10000)
        warning_count = sum(1 for i in impacts if 1000 < i.total_impact <= 10000)
        summary = (
            f"Analyzed {len(impacts)} scenarios. "
            f"{critical_count} high-cost (>$10k), "
            f"{warning_count} moderate-cost ($1k-$10k). "
            f"Estimated annual risk exposure: ${total_annual_risk:,.2f}."
        )

        return CostImpactReport(
            impacts=impacts,
            total_annual_risk=total_annual_risk,
            highest_impact_scenario=highest,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Internal calculation helpers
    # ------------------------------------------------------------------

    def _estimate_downtime(
        self,
        effects: list,
        severity: float,
    ) -> float:
        """Estimate total downtime minutes from cascade effects.

        Uses per-component MTTR when available, otherwise falls back to
        a severity-based heuristic.
        """
        total_minutes = 0.0
        has_mttr = False

        for effect in effects:
            if effect.health not in (HealthStatus.DOWN, HealthStatus.OVERLOADED):
                continue
            comp = self.graph.get_component(effect.component_id)
            if comp is None:
                continue
            mttr = comp.operational_profile.mttr_minutes
            if mttr > 0:
                has_mttr = True
                total_minutes += mttr

        if has_mttr and total_minutes > 0:
            return total_minutes

        # Fallback: derive downtime from severity score.
        return severity * SEVERITY_TO_DOWNTIME_FACTOR

    def _calculate_business_loss(
        self,
        effects: list,
        downtime_minutes: float,
    ) -> float:
        """Calculate revenue loss across affected components."""
        total_loss = 0.0
        for effect in effects:
            comp = self.graph.get_component(effect.component_id)
            if comp is None:
                continue
            rpm = comp.cost_profile.revenue_per_minute
            if rpm <= 0:
                continue

            # Scale loss by health status.
            if effect.health == HealthStatus.DOWN:
                factor = 1.0
            elif effect.health == HealthStatus.OVERLOADED:
                factor = 0.5
            elif effect.health == HealthStatus.DEGRADED:
                factor = 0.2
            else:
                factor = 0.0

            total_loss += rpm * downtime_minutes * factor

        return total_loss

    def _calculate_sla_penalty(
        self,
        effects: list,
        downtime_minutes: float,
    ) -> float:
        """Calculate SLA credit penalties for breached components.

        SLA penalty is triggered when downtime exceeds the allowed monthly
        error budget derived from the component's SLO targets.
        """
        total_penalty = 0.0
        for effect in effects:
            if effect.health not in (HealthStatus.DOWN, HealthStatus.OVERLOADED):
                continue
            comp = self.graph.get_component(effect.component_id)
            if comp is None:
                continue
            sla_pct = comp.cost_profile.sla_credit_percent
            rpm = comp.cost_profile.revenue_per_minute
            if sla_pct <= 0 or rpm <= 0:
                continue

            # Check if downtime would breach the SLO.
            slo_target = 99.9  # default
            for slo in comp.slo_targets:
                if slo.metric == "availability":
                    slo_target = slo.target
                    break

            # Allowed downtime per month in minutes.
            allowed_downtime = MONTHLY_MINUTES * (1.0 - slo_target / 100.0)
            if downtime_minutes > allowed_downtime:
                monthly_revenue = rpm * MONTHLY_MINUTES
                total_penalty += monthly_revenue * (sla_pct / 100.0)

        return total_penalty

    def _calculate_recovery_cost(
        self,
        effects: list,
        downtime_minutes: float,
    ) -> float:
        """Calculate recovery cost based on engineer time and per-component rates."""
        if downtime_minutes <= 0:
            return 0.0

        # Use the maximum recovery_engineer_cost across affected DOWN components.
        max_hourly_cost = 0.0
        affected_down = 0
        for effect in effects:
            if effect.health != HealthStatus.DOWN:
                continue
            affected_down += 1
            comp = self.graph.get_component(effect.component_id)
            if comp is None:
                continue
            max_hourly_cost = max(
                max_hourly_cost,
                comp.cost_profile.recovery_engineer_cost,
            )

        if affected_down == 0:
            return 0.0

        # Use default if no component specifies a cost.
        if max_hourly_cost <= 0:
            max_hourly_cost = 100.0

        mttr_hours = downtime_minutes / 60.0
        return max_hourly_cost * mttr_hours * self.num_engineers
