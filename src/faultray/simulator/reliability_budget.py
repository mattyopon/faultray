"""Reliability Budget Planner.

Plans and manages reliability budgets across services -- tracking error budget
consumption, predicting budget exhaustion, enforcing release freezes when
budgets are depleted, and balancing innovation velocity against reliability
targets.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PERIOD_MINUTES: dict[BudgetPeriod, float] = {}  # populated after enum

MINUTES_PER_HOUR = 60.0
MINUTES_PER_DAY = 1440.0
MINUTES_PER_WEEK = 10080.0
MINUTES_PER_MONTH = 43200.0  # 30 days
MINUTES_PER_QUARTER = 129600.0  # 90 days
MINUTES_PER_YEAR = 525600.0  # 365 days


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BudgetStatus(str, Enum):
    """Overall status of a service's reliability budget."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    EXHAUSTED = "exhausted"
    FROZEN = "frozen"


class BudgetPeriod(str, Enum):
    """Time period over which the budget is measured."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class PolicyAction(str, Enum):
    """Deployment policy action based on budget state."""

    ALLOW_RELEASES = "allow_releases"
    RESTRICT_RISKY = "restrict_risky"
    FREEZE_DEPLOYMENTS = "freeze_deployments"
    EMERGENCY_ONLY = "emergency_only"
    FULL_LOCKDOWN = "full_lockdown"


class BurnRateLevel(str, Enum):
    """Classification of how fast the error budget is being consumed."""

    SLOW = "slow"
    NORMAL = "normal"
    ELEVATED = "elevated"
    FAST = "fast"
    CRITICAL = "critical"


class ExhaustionRisk(str, Enum):
    """Risk level of budget exhaustion before the period ends."""

    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    IMMINENT = "imminent"


# Populate period-to-minutes mapping
_PERIOD_MINUTES.update({
    BudgetPeriod.HOURLY: MINUTES_PER_HOUR,
    BudgetPeriod.DAILY: MINUTES_PER_DAY,
    BudgetPeriod.WEEKLY: MINUTES_PER_WEEK,
    BudgetPeriod.MONTHLY: MINUTES_PER_MONTH,
    BudgetPeriod.QUARTERLY: MINUTES_PER_QUARTER,
    BudgetPeriod.YEARLY: MINUTES_PER_YEAR,
})


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ReliabilityTarget(BaseModel):
    """Defines the SLO target and budget period for a service."""

    service_id: str
    slo_target: float = 0.999  # e.g. 0.999 = 99.9%
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    total_budget_minutes: float = 0.0  # auto-computed if 0

    def effective_budget_minutes(self) -> float:
        """Return the total error budget in minutes for this target.

        Budget = (1 - SLO) * period_minutes.
        If *total_budget_minutes* is explicitly set to a positive value it is
        returned directly; otherwise the value is derived from *slo_target*
        and *period*.
        """
        if self.total_budget_minutes > 0:
            return self.total_budget_minutes
        period_minutes = _PERIOD_MINUTES.get(self.period, MINUTES_PER_MONTH)
        return (1.0 - self.slo_target) * period_minutes


class BudgetConsumption(BaseModel):
    """Snapshot of how much budget has been consumed."""

    consumed_minutes: float = 0.0
    remaining_minutes: float = 0.0
    consumed_fraction: float = 0.0  # 0.0-1.0
    period_elapsed_fraction: float = 0.0  # 0.0-1.0


class BurnRateAnalysis(BaseModel):
    """Analysis of the current burn rate."""

    current_burn_rate: float = 0.0
    burn_rate_level: BurnRateLevel = BurnRateLevel.NORMAL
    projected_exhaustion_day: float = 0.0  # day within the period
    budget_sufficient_for_period: bool = True


class ReleaseRiskAssessment(BaseModel):
    """Risk assessment for a proposed release."""

    release_id: str = ""
    estimated_error_budget_cost_minutes: float = 0.0
    risk_to_budget: ExhaustionRisk = ExhaustionRisk.NONE
    recommendation: str = ""


class BudgetPolicy(BaseModel):
    """Deployment policy derived from budget state."""

    status: BudgetStatus = BudgetStatus.HEALTHY
    action: PolicyAction = PolicyAction.ALLOW_RELEASES
    reason: str = ""
    auto_freeze_threshold: float = 0.9
    release_gate_enabled: bool = True


class ReliabilityBudgetReport(BaseModel):
    """Comprehensive reliability budget report for a service."""

    service_id: str
    target: ReliabilityTarget
    consumption: BudgetConsumption
    burn_rate: BurnRateAnalysis
    policy: BudgetPolicy
    release_assessments: list[ReleaseRiskAssessment] = Field(default_factory=list)
    forecast_days_remaining: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Incident helper (simple dataclass-like model for feeding incidents)
# ---------------------------------------------------------------------------


class IncidentRecord(BaseModel):
    """A single incident that consumed error budget."""

    incident_id: str = ""
    service_id: str = ""
    duration_minutes: float = 0.0
    severity: str = "low"  # low, medium, high, critical
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ReliabilityBudgetEngine:
    """Stateless engine for planning and managing reliability budgets.

    All public methods are pure functions that take inputs and return
    results without mutating internal state.
    """

    def __init__(self) -> None:
        pass

    # -- public API ---------------------------------------------------------

    def compute_budget(
        self,
        graph: InfraGraph,
        target: ReliabilityTarget,
        incidents: list[IncidentRecord] | None = None,
    ) -> ReliabilityBudgetReport:
        """Compute a full reliability budget report for a service.

        Parameters
        ----------
        graph:
            The infrastructure dependency graph.
        target:
            The reliability target for the service.
        incidents:
            Historical incidents that consumed error budget.

        Returns
        -------
        ReliabilityBudgetReport
        """
        incidents = incidents or []
        total_budget = target.effective_budget_minutes()

        # Sum consumed minutes from incidents
        consumed = sum(
            inc.duration_minutes
            for inc in incidents
            if inc.service_id == target.service_id or inc.service_id == ""
        )

        remaining = max(0.0, total_budget - consumed)
        consumed_fraction = consumed / total_budget if total_budget > 0 else 0.0

        # Estimate period elapsed from incidents
        elapsed_fraction = self._estimate_elapsed_fraction(incidents, target)

        consumption = BudgetConsumption(
            consumed_minutes=round(consumed, 6),
            remaining_minutes=round(remaining, 6),
            consumed_fraction=min(1.0, round(consumed_fraction, 6)),
            period_elapsed_fraction=round(elapsed_fraction, 6),
        )

        burn_rate = self.analyze_burn_rate(target, consumed, elapsed_fraction)
        policy = self.enforce_policy(consumption, burn_rate)
        forecast = self.forecast_exhaustion(burn_rate, remaining)

        # Build recommendations
        recommendations = self._build_recommendations(
            consumption, burn_rate, policy, target, graph
        )

        return ReliabilityBudgetReport(
            service_id=target.service_id,
            target=target,
            consumption=consumption,
            burn_rate=burn_rate,
            policy=policy,
            release_assessments=[],
            forecast_days_remaining=forecast.get("days", 0.0),
            recommendations=recommendations,
        )

    def analyze_burn_rate(
        self,
        target: ReliabilityTarget,
        consumed_minutes: float,
        elapsed_fraction: float,
    ) -> BurnRateAnalysis:
        """Analyze the current burn rate relative to the budget.

        Parameters
        ----------
        target:
            The reliability target.
        consumed_minutes:
            Minutes of error budget consumed so far.
        elapsed_fraction:
            Fraction of the budget period that has elapsed (0.0-1.0).

        Returns
        -------
        BurnRateAnalysis
        """
        total_budget = target.effective_budget_minutes()
        if total_budget <= 0:
            return BurnRateAnalysis(
                current_burn_rate=0.0,
                burn_rate_level=BurnRateLevel.SLOW,
                projected_exhaustion_day=0.0,
                budget_sufficient_for_period=True,
            )

        consumed_fraction = consumed_minutes / total_budget

        # Burn rate = consumed_fraction / elapsed_fraction
        # >1.0 means burning faster than expected
        if elapsed_fraction > 0:
            burn_rate = consumed_fraction / elapsed_fraction
        else:
            # No time elapsed -- if anything consumed, rate is infinite
            burn_rate = float("inf") if consumed_minutes > 0 else 0.0

        # Classify burn rate
        level = self._classify_burn_rate(burn_rate)

        # Project exhaustion
        period_minutes = _PERIOD_MINUTES.get(target.period, MINUTES_PER_MONTH)
        period_days = period_minutes / MINUTES_PER_DAY

        if burn_rate > 0 and burn_rate != float("inf"):
            # At current rate, budget exhausts at consumed_fraction == 1.0
            # which happens when elapsed_fraction == 1.0 / burn_rate
            exhaustion_elapsed = 1.0 / burn_rate
            projected_day = exhaustion_elapsed * period_days
        elif burn_rate == float("inf"):
            projected_day = 0.0
        else:
            projected_day = period_days  # never exhausts


        return BurnRateAnalysis(
            current_burn_rate=round(burn_rate, 6) if burn_rate != float("inf") else 999.0,
            burn_rate_level=level,
            projected_exhaustion_day=round(projected_day, 2),
            budget_sufficient_for_period=burn_rate <= 1.0,
        )

    def assess_release_risk(
        self,
        target: ReliabilityTarget,
        consumption: BudgetConsumption,
        release_error_estimate: float,
        release_id: str = "",
    ) -> ReleaseRiskAssessment:
        """Assess the risk of a proposed release to the error budget.

        Parameters
        ----------
        target:
            The reliability target.
        consumption:
            Current budget consumption snapshot.
        release_error_estimate:
            Estimated error budget cost of the release in minutes.
        release_id:
            Identifier for the release.

        Returns
        -------
        ReleaseRiskAssessment
        """
        remaining = consumption.remaining_minutes
        target.effective_budget_minutes()

        if remaining <= 0:
            return ReleaseRiskAssessment(
                release_id=release_id,
                estimated_error_budget_cost_minutes=release_error_estimate,
                risk_to_budget=ExhaustionRisk.IMMINENT,
                recommendation="Budget already exhausted. Do not release.",
            )

        # Risk = estimated_cost / remaining (remaining is guaranteed > 0 here)
        risk_ratio = release_error_estimate / remaining

        risk = self._classify_exhaustion_risk(risk_ratio)

        # Build recommendation
        if risk == ExhaustionRisk.NONE:
            rec = "Release is safe. Minimal impact on error budget."
        elif risk == ExhaustionRisk.LOW:
            rec = "Release is acceptable. Monitor error budget after deployment."
        elif risk == ExhaustionRisk.MODERATE:
            rec = (
                "Release carries moderate risk. Consider a canary deployment "
                "and closely monitor error rates."
            )
        elif risk == ExhaustionRisk.HIGH:
            rec = (
                "Release is risky. It may consume a large portion of remaining "
                "budget. Consider postponing or reducing scope."
            )
        else:  # IMMINENT
            rec = (
                "Release will likely exhaust the remaining error budget. "
                "Strongly recommend postponing."
            )

        return ReleaseRiskAssessment(
            release_id=release_id,
            estimated_error_budget_cost_minutes=round(release_error_estimate, 6),
            risk_to_budget=risk,
            recommendation=rec,
        )

    def enforce_policy(
        self,
        consumption: BudgetConsumption,
        burn_rate: BurnRateAnalysis,
        auto_freeze_threshold: float = 0.9,
    ) -> BudgetPolicy:
        """Determine the deployment policy based on current budget state.

        Parameters
        ----------
        consumption:
            Current budget consumption.
        burn_rate:
            Current burn rate analysis.
        auto_freeze_threshold:
            Fraction of consumed budget that triggers auto-freeze.

        Returns
        -------
        BudgetPolicy
        """
        cf = consumption.consumed_fraction

        # Determine status
        if cf >= 1.0 or consumption.remaining_minutes <= 0:
            if cf > auto_freeze_threshold:
                status = BudgetStatus.FROZEN
                action = PolicyAction.FULL_LOCKDOWN
                reason = (
                    "Error budget fully exhausted and exceeds freeze threshold. "
                    "All deployments locked down."
                )
            else:
                status = BudgetStatus.EXHAUSTED
                action = PolicyAction.EMERGENCY_ONLY
                reason = "Error budget exhausted. Only emergency deployments allowed."
        elif cf >= auto_freeze_threshold:
            status = BudgetStatus.FROZEN
            action = PolicyAction.FREEZE_DEPLOYMENTS
            reason = (
                f"Budget consumption ({cf:.1%}) exceeds auto-freeze threshold "
                f"({auto_freeze_threshold:.1%}). Deployments frozen."
            )
        elif cf >= 0.7:
            status = BudgetStatus.CRITICAL
            action = PolicyAction.RESTRICT_RISKY
            reason = (
                f"Budget consumption is critical ({cf:.1%}). "
                "Only low-risk releases allowed."
            )
        elif cf >= 0.5:
            status = BudgetStatus.WARNING
            action = PolicyAction.RESTRICT_RISKY
            reason = (
                f"Budget consumption is elevated ({cf:.1%}). "
                "Risky deployments should be deferred."
            )
        else:
            status = BudgetStatus.HEALTHY
            action = PolicyAction.ALLOW_RELEASES
            reason = f"Budget is healthy ({cf:.1%} consumed). All releases allowed."

        # Override: if burn rate is CRITICAL and we're not already locked down
        if burn_rate.burn_rate_level == BurnRateLevel.CRITICAL and status not in (
            BudgetStatus.FROZEN,
            BudgetStatus.EXHAUSTED,
        ):
            status = BudgetStatus.CRITICAL
            action = PolicyAction.RESTRICT_RISKY
            reason = (
                f"Burn rate is critical ({burn_rate.current_burn_rate:.2f}x). "
                "Restricting risky deployments."
            )

        return BudgetPolicy(
            status=status,
            action=action,
            reason=reason,
            auto_freeze_threshold=auto_freeze_threshold,
            release_gate_enabled=status != BudgetStatus.HEALTHY,
        )

    def forecast_exhaustion(
        self,
        burn_rate: BurnRateAnalysis,
        remaining_minutes: float,
    ) -> dict:
        """Forecast when the error budget will be exhausted.

        Parameters
        ----------
        burn_rate:
            Current burn rate analysis.
        remaining_minutes:
            Minutes of error budget remaining.

        Returns
        -------
        dict
            Keys: days, date, confidence.
        """
        now = datetime.now(timezone.utc)

        if remaining_minutes <= 0:
            return {
                "days": 0.0,
                "date": now.isoformat(),
                "confidence": 1.0,
            }

        rate = burn_rate.current_burn_rate
        if rate <= 0:
            return {
                "days": -1.0,
                "date": "never",
                "confidence": 0.0,
            }

        # remaining_minutes at current burn rate
        # burn rate is relative (consumed_fraction / elapsed_fraction)
        # but we can estimate days from projected_exhaustion_day
        projected_day = burn_rate.projected_exhaustion_day
        if projected_day <= 0:
            return {
                "days": 0.0,
                "date": now.isoformat(),
                "confidence": 0.9,
            }

        # Confidence decreases for longer projections
        if projected_day <= 1:
            confidence = 0.95
        elif projected_day <= 7:
            confidence = 0.85
        elif projected_day <= 30:
            confidence = 0.7
        else:
            confidence = 0.5

        exhaustion_date = now + timedelta(days=projected_day)

        return {
            "days": round(projected_day, 2),
            "date": exhaustion_date.isoformat(),
            "confidence": confidence,
        }

    def allocate_budget_across_services(
        self,
        graph: InfraGraph,
        global_slo: float,
        service_weights: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Allocate a global error budget across services by weight.

        Parameters
        ----------
        graph:
            The infrastructure graph.
        global_slo:
            The overall SLO target (e.g. 0.999).
        service_weights:
            Optional mapping from component_id to weight.
            Components not listed get weight 1.0.

        Returns
        -------
        dict[str, float]
            Mapping from component_id to allocated budget in minutes
            (assuming monthly period).
        """
        service_weights = service_weights or {}
        components = graph.components

        if not components:
            return {}

        global_budget = (1.0 - global_slo) * MINUTES_PER_MONTH

        weights: dict[str, float] = {}
        for comp_id in components:
            w = service_weights.get(comp_id, 1.0)
            # Boost weight for components with more dependents
            dependents = graph.get_dependents(comp_id)
            topology_boost = 1.0 + len(dependents) * 0.2
            weights[comp_id] = w * topology_boost

        total_weight = sum(weights.values())
        if total_weight <= 0:
            total_weight = 1.0

        allocations: dict[str, float] = {}
        for comp_id, w in weights.items():
            share = w / total_weight
            allocations[comp_id] = round(global_budget * share, 6)

        return allocations

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _classify_burn_rate(rate: float) -> BurnRateLevel:
        """Classify a numeric burn rate into a level."""
        if rate == float("inf") or rate >= 5.0:
            return BurnRateLevel.CRITICAL
        if rate >= 2.0:
            return BurnRateLevel.FAST
        if rate >= 1.2:
            return BurnRateLevel.ELEVATED
        if rate >= 0.5:
            return BurnRateLevel.NORMAL
        return BurnRateLevel.SLOW

    @staticmethod
    def _classify_exhaustion_risk(risk_ratio: float) -> ExhaustionRisk:
        """Classify the risk of budget exhaustion from a release."""
        if risk_ratio >= 0.8:
            return ExhaustionRisk.IMMINENT
        if risk_ratio >= 0.5:
            return ExhaustionRisk.HIGH
        if risk_ratio >= 0.25:
            return ExhaustionRisk.MODERATE
        if risk_ratio >= 0.1:
            return ExhaustionRisk.LOW
        return ExhaustionRisk.NONE

    @staticmethod
    def _estimate_elapsed_fraction(
        incidents: list[IncidentRecord],
        target: ReliabilityTarget,
    ) -> float:
        """Estimate how much of the period has elapsed based on incidents."""
        if not incidents:
            return 0.5  # default to halfway through the period

        now = datetime.now(timezone.utc)
        period_minutes = _PERIOD_MINUTES.get(target.period, MINUTES_PER_MONTH)

        # Find earliest incident
        earliest = min(inc.timestamp for inc in incidents)
        elapsed_minutes = (now - earliest).total_seconds() / 60.0

        fraction = elapsed_minutes / period_minutes if period_minutes > 0 else 0.0
        return max(0.01, min(1.0, fraction))

    def _build_recommendations(
        self,
        consumption: BudgetConsumption,
        burn_rate: BurnRateAnalysis,
        policy: BudgetPolicy,
        target: ReliabilityTarget,
        graph: InfraGraph,
    ) -> list[str]:
        """Build human-readable recommendations."""
        recs: list[str] = []

        if policy.status == BudgetStatus.EXHAUSTED:
            recs.append(
                "Error budget is exhausted. Focus on reliability improvements "
                "before any new feature releases."
            )
        elif policy.status == BudgetStatus.FROZEN:
            recs.append(
                "Deployments are frozen. Resolve outstanding incidents and "
                "improve system reliability to restore budget."
            )

        if burn_rate.burn_rate_level in (BurnRateLevel.FAST, BurnRateLevel.CRITICAL):
            recs.append(
                f"Burn rate is {burn_rate.current_burn_rate:.2f}x normal. "
                "Investigate recent incidents and reduce error rate."
            )

        if not burn_rate.budget_sufficient_for_period:
            recs.append(
                "Budget will not last the full period at current burn rate. "
                "Consider tightening release criteria or improving reliability."
            )

        # Check for single points of failure in the graph
        comp = graph.get_component(target.service_id)
        if comp is not None:
            if comp.replicas <= 1 and not comp.failover.enabled:
                recs.append(
                    f"Service '{target.service_id}' has no redundancy. "
                    "Add replicas or enable failover to reduce incident duration."
                )

        if consumption.consumed_fraction >= 0.5 and consumption.consumed_fraction < 0.7:
            recs.append(
                "Budget consumption is above 50%. Monitor closely and "
                "consider deferring risky changes."
            )

        if not recs:
            recs.append(
                "Budget is healthy. Continue with normal release cadence."
            )

        return recs

    def compute_multi_service_budget(
        self,
        graph: InfraGraph,
        targets: list[ReliabilityTarget],
        incidents: list[IncidentRecord] | None = None,
    ) -> list[ReliabilityBudgetReport]:
        """Compute budget reports for multiple services.

        Parameters
        ----------
        graph:
            The infrastructure graph.
        targets:
            List of reliability targets, one per service.
        incidents:
            All incidents across services.

        Returns
        -------
        list[ReliabilityBudgetReport]
        """
        incidents = incidents or []
        reports: list[ReliabilityBudgetReport] = []

        for t in targets:
            service_incidents = [
                inc for inc in incidents
                if inc.service_id == t.service_id or inc.service_id == ""
            ]
            report = self.compute_budget(graph, t, service_incidents)
            reports.append(report)

        return reports

    def compare_slo_targets(
        self,
        target_a: ReliabilityTarget,
        target_b: ReliabilityTarget,
    ) -> dict:
        """Compare two SLO targets and their error budgets.

        Returns
        -------
        dict
            Keys: budget_a_minutes, budget_b_minutes, difference_minutes,
            stricter_target, budget_ratio.
        """
        budget_a = target_a.effective_budget_minutes()
        budget_b = target_b.effective_budget_minutes()
        diff = abs(budget_a - budget_b)
        stricter = target_a.service_id if budget_a < budget_b else target_b.service_id
        ratio = budget_a / budget_b if budget_b > 0 else 0.0

        return {
            "budget_a_minutes": round(budget_a, 6),
            "budget_b_minutes": round(budget_b, 6),
            "difference_minutes": round(diff, 6),
            "stricter_target": stricter,
            "budget_ratio": round(ratio, 6),
        }

    def simulate_incident_impact(
        self,
        target: ReliabilityTarget,
        consumption: BudgetConsumption,
        incident_duration_minutes: float,
    ) -> dict:
        """Simulate the impact of a hypothetical incident on the budget.

        Returns
        -------
        dict
            Keys: new_consumed_minutes, new_remaining_minutes,
            new_consumed_fraction, would_exhaust, new_status.
        """
        total_budget = target.effective_budget_minutes()
        new_consumed = consumption.consumed_minutes + incident_duration_minutes
        new_remaining = max(0.0, total_budget - new_consumed)
        new_fraction = new_consumed / total_budget if total_budget > 0 else 1.0

        would_exhaust = new_remaining <= 0

        if new_fraction >= 1.0:
            new_status = BudgetStatus.EXHAUSTED
        elif new_fraction >= 0.9:
            new_status = BudgetStatus.FROZEN
        elif new_fraction >= 0.7:
            new_status = BudgetStatus.CRITICAL
        elif new_fraction >= 0.5:
            new_status = BudgetStatus.WARNING
        else:
            new_status = BudgetStatus.HEALTHY

        return {
            "new_consumed_minutes": round(new_consumed, 6),
            "new_remaining_minutes": round(new_remaining, 6),
            "new_consumed_fraction": round(min(1.0, new_fraction), 6),
            "would_exhaust": would_exhaust,
            "new_status": new_status,
        }

    def calculate_budget_for_slo(
        self,
        slo: float,
        period: BudgetPeriod = BudgetPeriod.MONTHLY,
    ) -> dict:
        """Calculate the error budget for a given SLO and period.

        Returns
        -------
        dict
            Keys: slo, period, period_minutes, error_budget_minutes,
            error_budget_seconds, allowed_downtime_per_day_seconds.
        """
        period_minutes = _PERIOD_MINUTES.get(period, MINUTES_PER_MONTH)
        budget_minutes = (1.0 - slo) * period_minutes
        budget_seconds = budget_minutes * 60.0
        period_days = period_minutes / MINUTES_PER_DAY
        daily_seconds = budget_seconds / period_days if period_days > 0 else 0.0

        return {
            "slo": slo,
            "period": period.value,
            "period_minutes": period_minutes,
            "error_budget_minutes": round(budget_minutes, 6),
            "error_budget_seconds": round(budget_seconds, 4),
            "allowed_downtime_per_day_seconds": round(daily_seconds, 4),
        }

    def evaluate_burn_rate_alerts(
        self,
        burn_rate: BurnRateAnalysis,
        consumption: BudgetConsumption,
    ) -> list[dict]:
        """Generate alert recommendations based on burn rate and consumption.

        Returns
        -------
        list[dict]
            Each dict has keys: severity, message, action.
        """
        alerts: list[dict] = []

        if burn_rate.burn_rate_level == BurnRateLevel.CRITICAL:
            alerts.append({
                "severity": "critical",
                "message": (
                    f"Burn rate is {burn_rate.current_burn_rate:.2f}x. "
                    "Budget will be exhausted imminently."
                ),
                "action": "page_oncall",
            })
        elif burn_rate.burn_rate_level == BurnRateLevel.FAST:
            alerts.append({
                "severity": "warning",
                "message": (
                    f"Burn rate is {burn_rate.current_burn_rate:.2f}x. "
                    "Budget consumption is accelerating."
                ),
                "action": "notify_team",
            })

        if consumption.consumed_fraction >= 0.9:
            alerts.append({
                "severity": "critical",
                "message": (
                    f"Error budget is {consumption.consumed_fraction:.1%} consumed."
                ),
                "action": "freeze_deployments",
            })
        elif consumption.consumed_fraction >= 0.7:
            alerts.append({
                "severity": "warning",
                "message": (
                    f"Error budget is {consumption.consumed_fraction:.1%} consumed."
                ),
                "action": "restrict_releases",
            })

        if not burn_rate.budget_sufficient_for_period:
            alerts.append({
                "severity": "warning",
                "message": "Budget projected to exhaust before period ends.",
                "action": "review_release_plan",
            })

        return alerts

    def compute_composite_slo(
        self,
        targets: list[ReliabilityTarget],
    ) -> float:
        """Compute the composite SLO for a chain of services.

        The composite SLO is the product of individual SLOs (serial dependency).

        Returns
        -------
        float
            Composite SLO (0.0-1.0).
        """
        if not targets:
            return 1.0

        composite = 1.0
        for t in targets:
            composite *= t.slo_target

        return round(composite, 9)

    def budget_utilization_efficiency(
        self,
        consumption: BudgetConsumption,
    ) -> float:
        """Calculate how efficiently the budget is being used.

        A value of 1.0 means consumption is perfectly proportional to
        elapsed time.  Values > 1.0 mean over-consumption.

        Returns
        -------
        float
            Efficiency ratio.
        """
        if consumption.period_elapsed_fraction <= 0:
            return 0.0 if consumption.consumed_fraction <= 0 else float("inf")

        return round(
            consumption.consumed_fraction / consumption.period_elapsed_fraction, 6
        )
