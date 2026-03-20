# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""SLO Burn Rate Alert Simulator.

Simulates Google SRE's multi-window, multi-burn-rate alerting strategy.
Tests whether your alerting rules would catch SLO violations early enough.
Answers: "with our current alerting, how quickly would we detect that we're
burning through our error budget?"
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Enums & Models
# ---------------------------------------------------------------------------


class AlertSeverity(str, Enum):
    """Severity level for a burn-rate alert."""

    PAGE = "page"
    TICKET = "ticket"
    LOG = "log"


class BurnRateWindow(BaseModel):
    """A single burn-rate alerting window definition."""

    window_minutes: int
    burn_rate_threshold: float
    long_window_minutes: int
    short_window_minutes: int
    severity: AlertSeverity


class ErrorBudgetStatus(BaseModel):
    """Current error budget consumption status."""

    slo_target: float
    error_budget_total: float
    error_budget_consumed: float
    error_budget_remaining_percent: float
    burn_rate_1h: float
    burn_rate_6h: float
    burn_rate_24h: float
    burn_rate_72h: float
    projected_exhaustion_hours: float | None


class BurnRateAlert(BaseModel):
    """Result of checking a single burn-rate window."""

    window: BurnRateWindow
    current_burn_rate: float
    triggered: bool
    severity: AlertSeverity
    time_to_exhaustion_hours: float | None
    message: str


class AlertSimulationScenario(BaseModel):
    """Definition of a scenario to simulate."""

    scenario_name: str
    error_rate_pattern: list[float]
    slo_target: float
    window_days: int


class AlertSimulationResult(BaseModel):
    """Result of simulating a single scenario."""

    scenario_name: str
    alerts_triggered: list[BurnRateAlert]
    detection_time_minutes: float | None
    false_positives: int
    missed_violations: int
    budget_status: ErrorBudgetStatus


class SLOBurnRateReport(BaseModel):
    """Aggregated report across multiple scenarios."""

    scenarios_tested: int
    results: list[AlertSimulationResult]
    fastest_detection_minutes: float
    slowest_detection_minutes: float | None
    alert_effectiveness_score: float
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Google SRE default burn-rate windows
# ---------------------------------------------------------------------------

_DEFAULT_WINDOWS: list[BurnRateWindow] = [
    BurnRateWindow(
        window_minutes=60,
        burn_rate_threshold=14.4,
        long_window_minutes=60,
        short_window_minutes=5,
        severity=AlertSeverity.PAGE,
    ),
    BurnRateWindow(
        window_minutes=360,
        burn_rate_threshold=6.0,
        long_window_minutes=360,
        short_window_minutes=30,
        severity=AlertSeverity.PAGE,
    ),
    BurnRateWindow(
        window_minutes=1440,
        burn_rate_threshold=3.0,
        long_window_minutes=1440,
        short_window_minutes=120,
        severity=AlertSeverity.TICKET,
    ),
    BurnRateWindow(
        window_minutes=4320,
        burn_rate_threshold=1.0,
        long_window_minutes=4320,
        short_window_minutes=360,
        severity=AlertSeverity.LOG,
    ),
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SLOBurnRateEngine:
    """Simulate multi-window, multi-burn-rate SLO alerting.

    The engine follows Google SRE's recommended approach of using four
    burn-rate windows with both long and short window checks to reduce
    false positives while maintaining fast detection.
    """

    def __init__(
        self,
        slo_target: float = 99.9,
        window_days: int = 30,
    ) -> None:
        self.slo_target = slo_target
        self.window_days = window_days
        self.allowed_error_rate = (100.0 - slo_target) / 100.0
        self.windows: list[BurnRateWindow] = list(_DEFAULT_WINDOWS)

    # -- public API ---------------------------------------------------------

    def calculate_error_budget(self) -> float:
        """Return the total error budget in minutes for the configured window."""
        return self.allowed_error_rate * self.window_days * 24 * 60

    def calculate_burn_rate(
        self, error_rates: list[float], window_hours: int
    ) -> float:
        """Calculate the burn rate over *window_hours* from hourly error rates.

        Burn rate is defined as ``actual_error_rate / allowed_error_rate``.
        A burn rate of 1.0 means the budget will be fully consumed exactly at
        the end of the SLO window.
        """
        if not error_rates or window_hours <= 0:
            return 0.0
        # Use up to window_hours most recent data points
        relevant = error_rates[-window_hours:]
        avg_error_rate = sum(relevant) / len(relevant) / 100.0
        if self.allowed_error_rate == 0:
            return 0.0
        return avg_error_rate / self.allowed_error_rate

    def evaluate_budget_status(
        self, error_rates: list[float]
    ) -> ErrorBudgetStatus:
        """Evaluate the current error-budget status from hourly error rates."""
        budget_total = self.calculate_error_budget()

        # Total consumed budget: sum of per-hour error fractions
        total_error_minutes = sum(
            (r / 100.0) * 60 for r in error_rates
        )
        consumed = min(total_error_minutes, budget_total)
        remaining_pct = max(
            0.0, (budget_total - consumed) / budget_total * 100.0
        ) if budget_total > 0 else 0.0

        br_1h = self.calculate_burn_rate(error_rates, 1)
        br_6h = self.calculate_burn_rate(error_rates, 6)
        br_24h = self.calculate_burn_rate(error_rates, 24)
        br_72h = self.calculate_burn_rate(error_rates, 72)

        remaining_budget = budget_total - consumed
        projected: float | None = None
        if br_1h > 0 and remaining_budget > 0:
            # At the current 1h burn rate, how long until exhaustion?
            budget_consumed_per_hour = (
                br_1h * self.allowed_error_rate * 60
            )
            if budget_consumed_per_hour > 0:
                projected = remaining_budget / budget_consumed_per_hour

        return ErrorBudgetStatus(
            slo_target=self.slo_target,
            error_budget_total=budget_total,
            error_budget_consumed=consumed,
            error_budget_remaining_percent=remaining_pct,
            burn_rate_1h=br_1h,
            burn_rate_6h=br_6h,
            burn_rate_24h=br_24h,
            burn_rate_72h=br_72h,
            projected_exhaustion_hours=projected,
        )

    def check_alerts(
        self, error_rates: list[float]
    ) -> list[BurnRateAlert]:
        """Check all configured burn-rate windows and return alerts."""
        alerts: list[BurnRateAlert] = []
        for window in self.windows:
            long_hours = window.long_window_minutes // 60 or 1
            short_hours = max(1, window.short_window_minutes // 60)

            long_br = self.calculate_burn_rate(error_rates, long_hours)
            short_br = self.calculate_burn_rate(error_rates, short_hours)

            triggered = (
                long_br >= window.burn_rate_threshold
                and short_br >= window.burn_rate_threshold
            )

            current_br = long_br
            tte: float | None = None
            if current_br > 0:
                budget = self.calculate_error_budget()
                consumed_per_hour = (
                    current_br * self.allowed_error_rate * 60
                )
                if consumed_per_hour > 0:
                    tte = budget / consumed_per_hour

            if triggered:
                msg = (
                    f"ALERT [{window.severity.value.upper()}]: "
                    f"Burn rate {current_br:.1f}x exceeds "
                    f"{window.burn_rate_threshold}x threshold over "
                    f"{window.long_window_minutes}min window"
                )
            else:
                msg = (
                    f"OK: Burn rate {current_br:.1f}x is below "
                    f"{window.burn_rate_threshold}x threshold over "
                    f"{window.long_window_minutes}min window"
                )

            alerts.append(
                BurnRateAlert(
                    window=window,
                    current_burn_rate=current_br,
                    triggered=triggered,
                    severity=window.severity,
                    time_to_exhaustion_hours=tte,
                    message=msg,
                )
            )
        return alerts

    def simulate_scenario(
        self, scenario: AlertSimulationScenario
    ) -> AlertSimulationResult:
        """Run a full simulation of a scenario.

        Walks through the error-rate pattern hour-by-hour and checks alerts
        at each step.  Records the first detection time and counts false
        positives and missed violations.
        """
        # Override engine settings per-scenario
        orig_target = self.slo_target
        orig_days = self.window_days
        self.slo_target = scenario.slo_target
        self.window_days = scenario.window_days
        self.allowed_error_rate = (100.0 - scenario.slo_target) / 100.0

        try:
            pattern = scenario.error_rate_pattern
            first_detection: float | None = None
            all_triggered: list[BurnRateAlert] = []
            false_positives = 0

            # Determine whether any hour actually violates the SLO
            has_real_violation = any(
                r / 100.0 > self.allowed_error_rate for r in pattern
            )

            for i in range(1, len(pattern) + 1):
                slice_ = pattern[:i]
                alerts = self.check_alerts(slice_)
                for alert in alerts:
                    if alert.triggered:
                        if first_detection is None:
                            first_detection = float(i * 60)
                        # Current hour not actually violating?
                        current_rate = pattern[i - 1] / 100.0
                        if current_rate <= self.allowed_error_rate:
                            false_positives += 1
                        all_triggered.append(alert)

            # Missed violations: real violations exist but never detected
            missed = 0
            if has_real_violation and first_detection is None:
                missed = sum(
                    1
                    for r in pattern
                    if r / 100.0 > self.allowed_error_rate
                )

            budget_status = self.evaluate_budget_status(pattern)
            return AlertSimulationResult(
                scenario_name=scenario.scenario_name,
                alerts_triggered=all_triggered,
                detection_time_minutes=first_detection,
                false_positives=false_positives,
                missed_violations=missed,
                budget_status=budget_status,
            )
        finally:
            self.slo_target = orig_target
            self.window_days = orig_days
            self.allowed_error_rate = (100.0 - orig_target) / 100.0

    def generate_report(
        self, scenarios: list[AlertSimulationScenario]
    ) -> SLOBurnRateReport:
        """Generate a consolidated report across multiple scenarios."""
        results: list[AlertSimulationResult] = []
        detection_times: list[float] = []

        for scenario in scenarios:
            result = self.simulate_scenario(scenario)
            results.append(result)
            if result.detection_time_minutes is not None:
                detection_times.append(result.detection_time_minutes)

        fastest = min(detection_times) if detection_times else 0.0
        slowest = max(detection_times) if detection_times else None

        # Effectiveness: percentage of scenarios where violations were
        # detected (excluding scenarios without real violations).
        scenarios_with_violations = 0
        detected = 0
        for r in results:
            has_violation = any(
                er / 100.0 > (100.0 - r.budget_status.slo_target) / 100.0
                for er in [
                    s.error_rate_pattern
                    for s in scenarios
                    if s.scenario_name == r.scenario_name
                ][0]
            )
            if has_violation:
                scenarios_with_violations += 1
                if r.detection_time_minutes is not None:
                    detected += 1

        effectiveness = (
            (detected / scenarios_with_violations * 100.0)
            if scenarios_with_violations > 0
            else 100.0
        )

        recommendations = self._build_recommendations(results)

        return SLOBurnRateReport(
            scenarios_tested=len(scenarios),
            results=results,
            fastest_detection_minutes=fastest,
            slowest_detection_minutes=slowest,
            alert_effectiveness_score=effectiveness,
            recommendations=recommendations,
        )

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _build_recommendations(
        results: list[AlertSimulationResult],
    ) -> list[str]:
        recs: list[str] = []
        total_fp = sum(r.false_positives for r in results)
        total_missed = sum(r.missed_violations for r in results)
        any_slow = any(
            r.detection_time_minutes is not None
            and r.detection_time_minutes > 360
            for r in results
        )

        if total_fp > 0:
            recs.append(
                "Reduce false positives by tightening short-window "
                "thresholds or increasing short-window duration."
            )
        if total_missed > 0:
            recs.append(
                "Add lower burn-rate windows to catch slow-draining "
                "budget consumption."
            )
        if any_slow:
            recs.append(
                "Consider adding a faster burn-rate window to improve "
                "detection time for high-severity incidents."
            )
        for r in results:
            if (
                r.budget_status.error_budget_remaining_percent < 20
                and r.budget_status.error_budget_remaining_percent > 0
            ):
                recs.append(
                    f"Scenario '{r.scenario_name}': error budget nearly "
                    f"exhausted ({r.budget_status.error_budget_remaining_percent:.1f}% "
                    f"remaining). Freeze feature releases."
                )
        if not recs:
            recs.append(
                "Alert configuration looks healthy. No changes needed."
            )
        return recs
