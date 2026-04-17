# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""SLA budget tracker — error budget consumption and burn rate prediction.

Tracks SLA error budget consumption over time, calculates burn rates,
and predicts when the budget will be exhausted. Enables Google SRE-style
error budget policies for release decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph


class BudgetStatus(str, Enum):
    """Status of an error budget."""

    HEALTHY = "healthy"  # > 50% remaining
    WARNING = "warning"  # 20-50% remaining
    CRITICAL = "critical"  # 5-20% remaining
    EXHAUSTED = "exhausted"  # 0-5% remaining
    EXCEEDED = "exceeded"  # negative remaining


class BurnRateTrend(str, Enum):
    """Trend of error budget burn rate."""

    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    CRITICAL = "critical"


@dataclass
class SLATarget:
    """SLA target definition."""

    name: str
    target_percent: float  # e.g. 99.9
    window_days: int = 30  # rolling window
    component_ids: list[str] = field(default_factory=list)  # empty = all


@dataclass
class Incident:
    """Record of a downtime incident."""

    component_id: str
    start_time: datetime
    duration_minutes: float
    description: str = ""


@dataclass
class BudgetSnapshot:
    """Point-in-time snapshot of error budget."""

    timestamp: datetime
    total_budget_minutes: float
    consumed_minutes: float
    remaining_minutes: float
    remaining_percent: float
    status: BudgetStatus
    incident_count: int


@dataclass
class BurnRateInfo:
    """Error budget burn rate analysis."""

    current_burn_rate: float  # multiplier (1.0 = on track)
    trend: BurnRateTrend
    minutes_per_day: float
    projected_exhaustion_days: float | None  # None = won't exhaust
    is_sustainable: bool


@dataclass
class BudgetReport:
    """Full SLA budget analysis report."""

    sla_name: str
    target_percent: float
    window_days: int
    total_budget_minutes: float
    consumed_minutes: float
    remaining_minutes: float
    remaining_percent: float
    status: BudgetStatus
    burn_rate: BurnRateInfo
    incidents: list[Incident]
    snapshot_history: list[BudgetSnapshot]
    can_release: bool
    release_risk: str  # "low", "medium", "high", "blocked"
    recommendations: list[str]


class SLABudgetTracker:
    """Track and manage SLA error budgets."""

    def __init__(self) -> None:
        self._targets: list[SLATarget] = []
        self._incidents: list[Incident] = []

    def add_target(self, target: SLATarget) -> None:
        """Add an SLA target to track."""
        self._targets.append(target)

    def add_incident(self, incident: Incident) -> None:
        """Record a downtime incident."""
        self._incidents.append(incident)

    def get_targets(self) -> list[SLATarget]:
        """Return all SLA targets."""
        return list(self._targets)

    def get_incidents(self) -> list[Incident]:
        """Return all recorded incidents."""
        return list(self._incidents)

    def calculate_budget(self, target: SLATarget) -> float:
        """Calculate total error budget in minutes for a target."""
        total_minutes = target.window_days * 24 * 60
        allowed_downtime_pct = 100.0 - target.target_percent
        return total_minutes * (allowed_downtime_pct / 100.0)

    def consumed_budget(
        self,
        target: SLATarget,
        reference_time: datetime | None = None,
    ) -> float:
        """Calculate consumed budget in minutes within the window."""
        ref = reference_time or datetime.now()
        window_start = ref - timedelta(days=target.window_days)

        total_consumed = 0.0
        for inc in self._incidents:
            if inc.start_time < window_start:
                continue
            if inc.start_time > ref:
                continue
            if target.component_ids and inc.component_id not in target.component_ids:
                continue
            total_consumed += inc.duration_minutes
        return total_consumed

    def remaining_budget(
        self,
        target: SLATarget,
        reference_time: datetime | None = None,
    ) -> float:
        """Calculate remaining error budget in minutes."""
        total = self.calculate_budget(target)
        consumed = self.consumed_budget(target, reference_time)
        return total - consumed

    def budget_status(
        self,
        target: SLATarget,
        reference_time: datetime | None = None,
    ) -> BudgetStatus:
        """Determine budget status."""
        total = self.calculate_budget(target)
        if total == 0:
            return BudgetStatus.EXHAUSTED
        remaining = self.remaining_budget(target, reference_time)
        pct = (remaining / total) * 100

        if pct <= 0:
            return BudgetStatus.EXCEEDED
        if pct <= 5:
            return BudgetStatus.EXHAUSTED
        if pct <= 20:
            return BudgetStatus.CRITICAL
        if pct <= 50:
            return BudgetStatus.WARNING
        return BudgetStatus.HEALTHY

    def burn_rate(
        self,
        target: SLATarget,
        reference_time: datetime | None = None,
        lookback_days: int = 7,
    ) -> BurnRateInfo:
        """Calculate error budget burn rate."""
        ref = reference_time or datetime.now()
        lookback_start = ref - timedelta(days=lookback_days)

        # Minutes consumed in lookback period
        consumed_in_period = 0.0
        for inc in self._incidents:
            if inc.start_time < lookback_start:
                continue
            if inc.start_time > ref:
                continue
            if target.component_ids and inc.component_id not in target.component_ids:
                continue
            consumed_in_period += inc.duration_minutes

        minutes_per_day = consumed_in_period / max(lookback_days, 1)
        total_budget = self.calculate_budget(target)
        expected_per_day = total_budget / max(target.window_days, 1)

        if expected_per_day > 0:
            current_rate = minutes_per_day / expected_per_day
        else:
            current_rate = 0.0

        # Trend analysis
        if current_rate <= 0.5:
            trend = BurnRateTrend.IMPROVING
        elif current_rate <= 1.5:
            trend = BurnRateTrend.STABLE
        elif current_rate <= 3.0:
            trend = BurnRateTrend.DEGRADING
        else:
            trend = BurnRateTrend.CRITICAL

        # Projection
        remaining = self.remaining_budget(target, ref)
        if minutes_per_day > 0 and remaining > 0:
            projected_days = remaining / minutes_per_day
        elif remaining <= 0:
            projected_days = 0.0
        else:
            projected_days = None  # type: ignore[assignment]

        is_sustainable = current_rate <= 1.0

        return BurnRateInfo(
            current_burn_rate=round(current_rate, 2),
            trend=trend,
            minutes_per_day=round(minutes_per_day, 2),
            projected_exhaustion_days=round(projected_days, 1) if projected_days is not None else None,
            is_sustainable=is_sustainable,
        )

    def snapshot(
        self,
        target: SLATarget,
        reference_time: datetime | None = None,
    ) -> BudgetSnapshot:
        """Take a snapshot of current budget state."""
        ref = reference_time or datetime.now()
        total = self.calculate_budget(target)
        consumed = self.consumed_budget(target, ref)
        remaining = total - consumed
        pct = (remaining / total * 100) if total > 0 else 0
        status = self.budget_status(target, ref)

        incident_count = sum(
            1 for inc in self._incidents
            if inc.start_time >= ref - timedelta(days=target.window_days)
            and inc.start_time <= ref
            and (not target.component_ids or inc.component_id in target.component_ids)
        )

        return BudgetSnapshot(
            timestamp=ref,
            total_budget_minutes=round(total, 2),
            consumed_minutes=round(consumed, 2),
            remaining_minutes=round(remaining, 2),
            remaining_percent=round(pct, 1),
            status=status,
            incident_count=incident_count,
        )

    def can_release(
        self,
        target: SLATarget,
        reference_time: datetime | None = None,
    ) -> bool:
        """Determine if releases should be allowed based on error budget."""
        status = self.budget_status(target, reference_time)
        return status in (BudgetStatus.HEALTHY, BudgetStatus.WARNING)

    def release_risk(
        self,
        target: SLATarget,
        reference_time: datetime | None = None,
    ) -> str:
        """Assess release risk based on error budget."""
        status = self.budget_status(target, reference_time)
        return {
            BudgetStatus.HEALTHY: "low",
            BudgetStatus.WARNING: "medium",
            BudgetStatus.CRITICAL: "high",
            BudgetStatus.EXHAUSTED: "blocked",
            BudgetStatus.EXCEEDED: "blocked",
        }[status]

    def generate_report(
        self,
        target: SLATarget,
        reference_time: datetime | None = None,
    ) -> BudgetReport:
        """Generate comprehensive budget report for a target."""
        ref = reference_time or datetime.now()
        total = self.calculate_budget(target)
        consumed = self.consumed_budget(target, ref)
        remaining = total - consumed
        pct = (remaining / total * 100) if total > 0 else 0
        status = self.budget_status(target, ref)
        br = self.burn_rate(target, ref)

        # Relevant incidents
        window_start = ref - timedelta(days=target.window_days)
        relevant_incidents = [
            inc for inc in self._incidents
            if inc.start_time >= window_start
            and inc.start_time <= ref
            and (not target.component_ids or inc.component_id in target.component_ids)
        ]

        # Recommendations
        recs: list[str] = []
        if status == BudgetStatus.EXCEEDED:
            recs.append("Error budget exceeded — freeze all non-critical releases immediately")
        elif status == BudgetStatus.EXHAUSTED:
            recs.append("Error budget nearly exhausted — only critical fixes allowed")
        elif status == BudgetStatus.CRITICAL:
            recs.append("Error budget running low — review upcoming releases carefully")

        if br.trend == BurnRateTrend.CRITICAL:
            recs.append(f"Burn rate is {br.current_burn_rate}x normal — investigate root cause")
        elif br.trend == BurnRateTrend.DEGRADING:
            recs.append("Burn rate is increasing — monitor closely")

        if br.projected_exhaustion_days is not None and br.projected_exhaustion_days < 7:
            recs.append(
                f"Budget projected to exhaust in {br.projected_exhaustion_days:.0f} days"
            )

        if len(relevant_incidents) > 5:
            recs.append(f"{len(relevant_incidents)} incidents in window — consider reliability sprint")

        can_rel = self.can_release(target, ref)
        rel_risk = self.release_risk(target, ref)

        return BudgetReport(
            sla_name=target.name,
            target_percent=target.target_percent,
            window_days=target.window_days,
            total_budget_minutes=round(total, 2),
            consumed_minutes=round(consumed, 2),
            remaining_minutes=round(remaining, 2),
            remaining_percent=round(pct, 1),
            status=status,
            burn_rate=br,
            incidents=relevant_incidents,
            snapshot_history=[],
            can_release=can_rel,
            release_risk=rel_risk,
            recommendations=recs,
        )

    def report_from_graph(
        self,
        graph: InfraGraph,
        target: SLATarget | None = None,
        reference_time: datetime | None = None,
    ) -> BudgetReport:
        """Generate report using graph analysis to estimate incidents.

        If no incidents have been manually recorded, this creates
        synthetic incident estimates based on component health status.
        """
        ref = reference_time or datetime.now()

        if target is None:
            target = SLATarget(
                name="Default SLA",
                target_percent=99.9,
                window_days=30,
            )

        # If no incidents recorded, estimate from graph health
        if not self._incidents:
            for comp in graph.components.values():
                if comp.health == HealthStatus.DOWN:
                    self._incidents.append(Incident(
                        component_id=comp.id,
                        start_time=ref - timedelta(hours=1),
                        duration_minutes=60,
                        description=f"{comp.name} is DOWN",
                    ))
                elif comp.health == HealthStatus.DEGRADED:
                    self._incidents.append(Incident(
                        component_id=comp.id,
                        start_time=ref - timedelta(hours=2),
                        duration_minutes=15,
                        description=f"{comp.name} is degraded",
                    ))

        return self.generate_report(target, ref)
