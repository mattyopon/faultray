"""Error Budget Policy Engine.

Implements Google SRE's error budget policy framework.  Automatically
determines whether releases should be allowed based on error budget
consumption.  Defines escalation policies, freeze conditions, and
recovery actions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BudgetState(str, Enum):
    """Current state of the error budget."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    EXHAUSTED = "exhausted"


class PolicyAction(str, Enum):
    """Action to take based on budget state."""

    ALLOW_RELEASES = "allow_releases"
    SLOW_RELEASES = "slow_releases"
    FREEZE_RELEASES = "freeze_releases"
    EMERGENCY_ONLY = "emergency_only"


class EscalationLevel(str, Enum):
    """Escalation level for the current budget state."""

    TEAM = "team"
    MANAGEMENT = "management"
    VP = "vp"
    EXECUTIVE = "executive"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class BudgetThreshold(BaseModel):
    """Maps a budget-remaining range to an action and escalation."""

    state: BudgetState
    min_remaining_percent: float
    max_remaining_percent: float
    action: PolicyAction
    escalation: EscalationLevel
    description: str


class ErrorBudgetSnapshot(BaseModel):
    """Point-in-time snapshot of error budget consumption for one SLO."""

    slo_name: str
    slo_target: float
    window_days: int
    budget_total_minutes: float
    budget_consumed_minutes: float
    budget_remaining_percent: float
    state: BudgetState
    timestamp: datetime


class PolicyDecision(BaseModel):
    """Decision produced by the policy engine for a snapshot."""

    snapshot: ErrorBudgetSnapshot
    action: PolicyAction
    escalation: EscalationLevel
    reason: str
    conditions_for_release: list[str]


class BudgetForecast(BaseModel):
    """Forecast of error budget consumption trajectory."""

    days_until_exhaustion: float | None
    current_burn_rate: float
    projected_end_of_window_remaining: float
    on_track: bool


class ErrorBudgetPolicyReport(BaseModel):
    """Aggregated policy report across multiple SLOs."""

    snapshots: list[ErrorBudgetSnapshot]
    decisions: list[PolicyDecision]
    forecasts: list[BudgetForecast]
    overall_action: PolicyAction
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLDS: list[BudgetThreshold] = [
    BudgetThreshold(
        state=BudgetState.HEALTHY,
        min_remaining_percent=50.0,
        max_remaining_percent=100.0,
        action=PolicyAction.ALLOW_RELEASES,
        escalation=EscalationLevel.TEAM,
        description="Budget is healthy; releases are unrestricted.",
    ),
    BudgetThreshold(
        state=BudgetState.WARNING,
        min_remaining_percent=20.0,
        max_remaining_percent=50.0,
        action=PolicyAction.SLOW_RELEASES,
        escalation=EscalationLevel.MANAGEMENT,
        description="Budget is under pressure; slow down releases.",
    ),
    BudgetThreshold(
        state=BudgetState.CRITICAL,
        min_remaining_percent=1.0,
        max_remaining_percent=20.0,
        action=PolicyAction.FREEZE_RELEASES,
        escalation=EscalationLevel.VP,
        description="Budget nearly exhausted; freeze non-critical releases.",
    ),
    BudgetThreshold(
        state=BudgetState.EXHAUSTED,
        min_remaining_percent=0.0,
        max_remaining_percent=1.0,
        action=PolicyAction.EMERGENCY_ONLY,
        escalation=EscalationLevel.EXECUTIVE,
        description="Budget exhausted; emergency changes only.",
    ),
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ErrorBudgetPolicyEngine:
    """Evaluate error budget policy for one or more SLOs.

    Uses Google SRE-style thresholds to decide whether releases should
    be allowed, slowed, frozen, or restricted to emergency-only based
    on the remaining error budget.
    """

    def __init__(self) -> None:
        self.thresholds: list[BudgetThreshold] = list(_DEFAULT_THRESHOLDS)

    # -- public API ---------------------------------------------------------

    def create_snapshot(
        self,
        slo_name: str,
        slo_target: float,
        error_minutes: float,
        window_days: int,
    ) -> ErrorBudgetSnapshot:
        """Create an ``ErrorBudgetSnapshot`` from raw numbers."""
        allowed_error_rate = (100.0 - slo_target) / 100.0
        budget_total = allowed_error_rate * window_days * 24 * 60
        consumed = min(error_minutes, budget_total)
        remaining_pct = (
            max(0.0, (budget_total - consumed) / budget_total * 100.0)
            if budget_total > 0
            else 0.0
        )
        state = self._classify_state(remaining_pct)
        return ErrorBudgetSnapshot(
            slo_name=slo_name,
            slo_target=slo_target,
            window_days=window_days,
            budget_total_minutes=budget_total,
            budget_consumed_minutes=consumed,
            budget_remaining_percent=remaining_pct,
            state=state,
            timestamp=datetime.now(timezone.utc),
        )

    def evaluate_policy(self, snapshot: ErrorBudgetSnapshot) -> PolicyDecision:
        """Return the policy decision for the given snapshot."""
        threshold = self._find_threshold(snapshot.state)
        conditions = self._conditions_for_release(snapshot, threshold)
        return PolicyDecision(
            snapshot=snapshot,
            action=threshold.action,
            escalation=threshold.escalation,
            reason=threshold.description,
            conditions_for_release=conditions,
        )

    def forecast_budget(
        self,
        snapshot: ErrorBudgetSnapshot,
        recent_error_rate_per_day: float,
    ) -> BudgetForecast:
        """Forecast budget consumption based on recent error rate."""
        remaining = (
            snapshot.budget_total_minutes
            * snapshot.budget_remaining_percent
            / 100.0
        )
        if snapshot.budget_total_minutes > 0 and snapshot.window_days > 0:
            burn_rate = recent_error_rate_per_day / (
                snapshot.budget_total_minutes / snapshot.window_days
            )
        else:
            burn_rate = 0.0

        if recent_error_rate_per_day > 0 and remaining > 0:
            days_left: float | None = remaining / recent_error_rate_per_day
        else:
            days_left = None

        # Project remaining budget at end of window
        elapsed_fraction = (
            snapshot.budget_consumed_minutes / snapshot.budget_total_minutes
            if snapshot.budget_total_minutes > 0
            else 0.0
        )
        projected_total_consumed = (
            snapshot.budget_consumed_minutes
            + recent_error_rate_per_day * snapshot.window_days * (1 - elapsed_fraction)
        )
        projected_remaining = max(
            0.0,
            (snapshot.budget_total_minutes - projected_total_consumed)
            / snapshot.budget_total_minutes
            * 100.0,
        ) if snapshot.budget_total_minutes > 0 else 0.0

        on_track = burn_rate <= 1.0

        return BudgetForecast(
            days_until_exhaustion=days_left,
            current_burn_rate=burn_rate,
            projected_end_of_window_remaining=projected_remaining,
            on_track=on_track,
        )

    def should_allow_release(
        self, snapshots: list[ErrorBudgetSnapshot]
    ) -> bool:
        """Simple gate: return ``True`` only if all SLOs allow releases."""
        if not snapshots:
            return True
        for snap in snapshots:
            decision = self.evaluate_policy(snap)
            if decision.action not in (
                PolicyAction.ALLOW_RELEASES,
                PolicyAction.SLOW_RELEASES,
            ):
                return False
        return True

    def get_recovery_actions(
        self, snapshot: ErrorBudgetSnapshot
    ) -> list[str]:
        """Suggest recovery actions based on budget state."""
        actions: list[str] = []
        if snapshot.state == BudgetState.EXHAUSTED:
            actions.append("Halt all non-emergency deployments immediately.")
            actions.append("Convene incident review within 24 hours.")
            actions.append("Assign on-call team to reliability improvements only.")
            actions.append("Escalate to executive leadership for visibility.")
        elif snapshot.state == BudgetState.CRITICAL:
            actions.append("Freeze feature releases until budget recovers above 20%.")
            actions.append("Prioritize reliability fixes over new features.")
            actions.append("Increase monitoring and alerting sensitivity.")
        elif snapshot.state == BudgetState.WARNING:
            actions.append("Slow release cadence; batch smaller changes.")
            actions.append("Review recent incidents for recurring issues.")
            actions.append("Consider adding redundancy to high-risk components.")
        else:
            actions.append("No recovery actions needed; budget is healthy.")
        return actions

    def generate_report(
        self,
        snapshots: list[ErrorBudgetSnapshot],
        error_rates: dict[str, float] | None = None,
    ) -> ErrorBudgetPolicyReport:
        """Generate a full policy report for a list of snapshots."""
        decisions: list[PolicyDecision] = []
        forecasts: list[BudgetForecast] = []
        recommendations: list[str] = []

        for snap in snapshots:
            decision = self.evaluate_policy(snap)
            decisions.append(decision)

            rate = (error_rates or {}).get(snap.slo_name, 0.0)
            forecast = self.forecast_budget(snap, rate)
            forecasts.append(forecast)

        overall = self._worst_action(decisions)
        recommendations = self._build_recommendations(
            snapshots, decisions, forecasts
        )

        return ErrorBudgetPolicyReport(
            snapshots=snapshots,
            decisions=decisions,
            forecasts=forecasts,
            overall_action=overall,
            recommendations=recommendations,
        )

    # -- private helpers ----------------------------------------------------

    def _classify_state(self, remaining_pct: float) -> BudgetState:
        """Map remaining-percent to a ``BudgetState``."""
        if remaining_pct >= 50.0:
            return BudgetState.HEALTHY
        if remaining_pct >= 20.0:
            return BudgetState.WARNING
        if remaining_pct >= 1.0:
            return BudgetState.CRITICAL
        return BudgetState.EXHAUSTED

    def _find_threshold(self, state: BudgetState) -> BudgetThreshold:
        for t in self.thresholds:
            if t.state == state:
                return t
        # Fallback: strictest
        return self.thresholds[-1]

    @staticmethod
    def _conditions_for_release(
        snapshot: ErrorBudgetSnapshot,
        threshold: BudgetThreshold,
    ) -> list[str]:
        conditions: list[str] = []
        if threshold.action == PolicyAction.ALLOW_RELEASES:
            conditions.append("Standard release process applies.")
        elif threshold.action == PolicyAction.SLOW_RELEASES:
            conditions.append("Reduce release frequency by 50%.")
            conditions.append("Each release must include rollback plan.")
        elif threshold.action == PolicyAction.FREEZE_RELEASES:
            conditions.append("Only reliability improvements may be released.")
            conditions.append("VP approval required for any exception.")
        elif threshold.action == PolicyAction.EMERGENCY_ONLY:
            conditions.append("Only P0/P1 emergency fixes allowed.")
            conditions.append("Executive sign-off required for every change.")
            conditions.append("Post-change review mandatory within 4 hours.")
        return conditions

    @staticmethod
    def _worst_action(decisions: list[PolicyDecision]) -> PolicyAction:
        priority = [
            PolicyAction.EMERGENCY_ONLY,
            PolicyAction.FREEZE_RELEASES,
            PolicyAction.SLOW_RELEASES,
            PolicyAction.ALLOW_RELEASES,
        ]
        for action in priority:
            if any(d.action == action for d in decisions):
                return action
        return PolicyAction.ALLOW_RELEASES

    @staticmethod
    def _build_recommendations(
        snapshots: list[ErrorBudgetSnapshot],
        decisions: list[PolicyDecision],
        forecasts: list[BudgetForecast],
    ) -> list[str]:
        recs: list[str] = []
        for snap, forecast in zip(snapshots, forecasts):
            if snap.state == BudgetState.EXHAUSTED:
                recs.append(
                    f"SLO '{snap.slo_name}': budget exhausted — halt deployments."
                )
            elif snap.state == BudgetState.CRITICAL:
                recs.append(
                    f"SLO '{snap.slo_name}': budget critical "
                    f"({snap.budget_remaining_percent:.1f}% left) — freeze releases."
                )
            if forecast.days_until_exhaustion is not None and forecast.days_until_exhaustion < 7:
                recs.append(
                    f"SLO '{snap.slo_name}': projected exhaustion in "
                    f"{forecast.days_until_exhaustion:.1f} days — take action now."
                )
            if not forecast.on_track:
                recs.append(
                    f"SLO '{snap.slo_name}': burn rate {forecast.current_burn_rate:.2f}x "
                    f"exceeds budget — reduce error rate."
                )
        if not recs:
            recs.append("All SLOs within budget. No action required.")
        return recs
