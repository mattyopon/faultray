# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""SLA Budget Analyzer — Error Budget / SLA Burn Rate.

Calculates how much error budget remains for each component and estimates
when the budget will be exhausted at the current burn rate.

Algorithm:
1. For each component, derive its SLO target from ``slo_targets`` (first
   entry with metric=="availability") or fall back to a 99.9% default.
2. Compute ``allowed_downtime_minutes`` = window_days × 24 × 60 × (1 - slo/100).
3. Convert ``incidents`` count to consumed downtime (each incident = 30 minutes).
4. ``burn_rate`` = consumed / (elapsed_fraction × allowed).
5. ``days_until_exhaustion`` = remaining / (consumed_per_day if > 0 else None).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from faultray.model.graph import InfraGraph

# Default values when a component has no explicit SLO configured
_DEFAULT_SLO_TARGET = 99.9
_DEFAULT_WINDOW_DAYS = 30
_INCIDENT_DURATION_MINUTES = 30.0   # assumed downtime per incident


def _allowed_minutes(slo_target: float, window_days: int) -> float:
    """Total allowed downtime in minutes for the window."""
    total_minutes = window_days * 24 * 60
    error_fraction = 1.0 - (slo_target / 100.0)
    return total_minutes * error_fraction


def _status(remaining_fraction: float) -> str:
    """Convert remaining budget fraction to status string."""
    if remaining_fraction >= 0.5:
        return "healthy"
    if remaining_fraction >= 0.2:
        return "warning"
    if remaining_fraction > 0.0:
        return "critical"
    return "exhausted"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SLABudgetStatus:
    """Per-component SLA error budget status."""

    component_id: str
    slo_target: float                        # e.g. 99.9
    window_days: int                         # e.g. 30
    allowed_downtime_minutes: float
    consumed_downtime_minutes: float
    remaining_minutes: float
    burn_rate: float                         # consumed / expected_consumed_so_far
    status: str                              # healthy / warning / critical / exhausted
    days_until_exhaustion: float | None      # at current burn rate; None = won't exhaust

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "slo_target": self.slo_target,
            "window_days": self.window_days,
            "allowed_downtime_minutes": round(self.allowed_downtime_minutes, 2),
            "consumed_downtime_minutes": round(self.consumed_downtime_minutes, 2),
            "remaining_minutes": round(self.remaining_minutes, 2),
            "burn_rate": round(self.burn_rate, 2),
            "status": self.status,
            "days_until_exhaustion": (
                round(self.days_until_exhaustion, 1)
                if self.days_until_exhaustion is not None
                else None
            ),
        }


@dataclass
class SLABudgetReport:
    """Aggregated SLA error budget report."""

    budgets: list[SLABudgetStatus] = field(default_factory=list)
    overall_status: str = "healthy"
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "overall_status": self.overall_status,
            "summary": self.summary,
            "budgets": [b.to_dict() for b in self.budgets],
        }


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class SLABudgetAnalyzer:
    """Calculate SLA error budgets for all components in an InfraGraph."""

    def analyze(
        self,
        graph: InfraGraph,
        incidents_per_component: int = 0,
        reference_time: datetime | None = None,
    ) -> SLABudgetReport:
        """Compute error budget status for every component.

        Args:
            graph: The infrastructure graph to inspect.
            incidents_per_component: Number of 30-minute incidents assumed to
                have occurred this month for *each* component.  This simulates
                the ``--incidents N`` CLI option.
            reference_time: Point-in-time for burn-rate calculation.
                Defaults to now (UTC).

        Returns:
            A :class:`SLABudgetReport` with per-component budget status.
        """
        ref = reference_time or datetime.now(tz=timezone.utc)
        # Elapsed fraction of the window (based on UTC day-of-month).
        # Clamp between 1/30 and 1.0 to avoid division-by-zero on day 0.
        day_of_month = ref.day
        window_days = _DEFAULT_WINDOW_DAYS
        elapsed_fraction = max(day_of_month / window_days, 1 / window_days)

        budgets: list[SLABudgetStatus] = []

        for comp_id, comp in graph.components.items():
            # Resolve SLO target from component definition
            slo_target = _DEFAULT_SLO_TARGET
            comp_window = window_days
            for slo in comp.slo_targets:
                if slo.metric in ("availability", ""):
                    slo_target = slo.target
                    comp_window = slo.window_days
                    break

            allowed = _allowed_minutes(slo_target, comp_window)
            consumed = incidents_per_component * _INCIDENT_DURATION_MINUTES
            remaining = allowed - consumed

            # Burn rate = (consumed / allowed) / elapsed_fraction
            # 1.0 = exactly on track, >1.0 = burning faster than allowed
            if allowed > 0 and elapsed_fraction > 0:
                burn_rate = (consumed / allowed) / elapsed_fraction
            else:
                burn_rate = 0.0

            # Days until exhaustion at current burn rate
            if remaining <= 0:
                days_until = 0.0
            elif consumed > 0:
                # consumed per day so far
                elapsed_days = elapsed_fraction * comp_window
                consumed_per_day = consumed / max(elapsed_days, 1)
                days_until = remaining / consumed_per_day
            else:
                days_until = None   # will never exhaust at zero consumption

            remaining_fraction = remaining / allowed if allowed > 0 else 1.0
            remaining_fraction = max(0.0, min(1.0, remaining_fraction))

            budgets.append(
                SLABudgetStatus(
                    component_id=comp_id,
                    slo_target=slo_target,
                    window_days=comp_window,
                    allowed_downtime_minutes=round(allowed, 2),
                    consumed_downtime_minutes=round(consumed, 2),
                    remaining_minutes=round(remaining, 2),
                    burn_rate=round(burn_rate, 2),
                    status=_status(remaining_fraction),
                    days_until_exhaustion=(
                        round(days_until, 1) if days_until is not None else None
                    ),
                )
            )

        # Sort by remaining_minutes ascending (most at risk first)
        budgets.sort(key=lambda b: b.remaining_minutes)

        # Overall status = worst individual status
        _status_order = {"exhausted": 0, "critical": 1, "warning": 2, "healthy": 3}
        if budgets:
            overall = min(budgets, key=lambda b: _status_order.get(b.status, 99)).status
        else:
            overall = "healthy"

        exhausted_count = sum(1 for b in budgets if b.status == "exhausted")
        critical_count = sum(1 for b in budgets if b.status == "critical")
        warning_count = sum(1 for b in budgets if b.status == "warning")

        summary = (
            f"{len(budgets)} component(s) analysed. "
            f"Overall status: {overall}. "
            f"Exhausted: {exhausted_count}, Critical: {critical_count}, "
            f"Warning: {warning_count}."
        )

        return SLABudgetReport(
            budgets=budgets,
            overall_status=overall,
            summary=summary,
        )
