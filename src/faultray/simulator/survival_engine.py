"""Survival Analysis for infrastructure component lifetime estimation.

Implements Kaplan-Meier survival estimation, Weibull distribution fitting,
and hazard-function-based remaining-life prediction for infrastructure
components.

Uses ONLY the Python standard library.

Basic usage::

    >>> from faultray.model.graph import InfraGraph
    >>> graph = InfraGraph()
    >>> # ... populate graph ...
    >>> engine = SurvivalEngine(graph)
    >>> report = engine.analyze_all()
    >>> for curve in report.per_component:
    ...     print(curve.component_id, curve.survival_probs[-1])
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faultray.model.components import Component
    from faultray.model.graph import InfraGraph


@dataclass
class SurvivalCurve:
    """A Kaplan-Meier survival curve for a single component.

    Attributes:
        times: Ordered event times.
        survival_probs: Survival probability at each event time.
        component_id: The component this curve belongs to.
    """

    times: list[float] = field(default_factory=list)
    survival_probs: list[float] = field(default_factory=list)
    component_id: str = ""


@dataclass
class SurvivalReport:
    """Aggregated survival analysis across all components.

    Attributes:
        per_component: Individual survival curves.
        high_risk: Component IDs whose predicted remaining life is below
            a safety threshold.
        avg_remaining_life: Average remaining life across all components
            (hours).
    """

    per_component: list[SurvivalCurve] = field(default_factory=list)
    high_risk: list[str] = field(default_factory=list)
    avg_remaining_life: float = 0.0


class SurvivalEngine:
    """Survival analysis engine for infrastructure components.

    Generates synthetic failure-time data from each component's MTBF,
    operational metrics and degradation profile, then applies classical
    survival-analysis techniques (Kaplan-Meier, Weibull).

    Parameters:
        graph: The infrastructure dependency graph.
    """

    # Components with remaining life below this threshold (hours)
    # are flagged as high-risk.
    HIGH_RISK_THRESHOLD_HOURS = 168.0  # 1 week

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def kaplan_meier(
        self,
        failure_times: list[float],
        censored: list[bool],
    ) -> SurvivalCurve:
        """Compute a Kaplan-Meier survival curve.

        S(t) = product( (1 - d_i / n_i) ) for all t_i <= t

        where d_i = number of events at time t_i and n_i = number at risk
        just before t_i.

        Parameters:
            failure_times: Observed event / censoring times.
            censored: ``True`` if the observation is right-censored (no
                failure observed), ``False`` if an actual failure.

        Returns:
            A ``SurvivalCurve`` with times and survival probabilities.
        """
        if not failure_times:
            return SurvivalCurve()

        # Pair times with event indicator and sort
        events = sorted(
            zip(failure_times, censored), key=lambda x: x[0]
        )

        n_at_risk = len(events)
        survival = 1.0
        times: list[float] = []
        probs: list[float] = []

        i = 0
        while i < len(events):
            t_i = events[i][0]
            d_i = 0  # failures at t_i
            c_i = 0  # censored at t_i

            # Gather all events at this time
            while i < len(events) and events[i][0] == t_i:
                if events[i][1]:
                    c_i += 1
                else:
                    d_i += 1
                i += 1

            if d_i > 0 and n_at_risk > 0:
                survival *= (1.0 - d_i / n_at_risk)

            times.append(t_i)
            probs.append(survival)

            n_at_risk -= (d_i + c_i)

        return SurvivalCurve(times=times, survival_probs=probs)

    def weibull_fit(
        self, failure_times: list[float]
    ) -> tuple[float, float]:
        """Fit a Weibull distribution to observed failure times.

        Uses a simplified Maximum Likelihood Estimation approach:

        * **Scale** (lambda): derived from mean failure time.
        * **Shape** (k): estimated from the coefficient of variation.

        Returns:
            ``(shape_k, scale_lambda)``
        """
        if not failure_times or len(failure_times) < 2:
            return (1.0, 1000.0)  # default exponential with long scale

        times = [t for t in failure_times if t > 0]
        if not times:
            return (1.0, 1000.0)

        mean_t = sum(times) / len(times)
        variance = sum((t - mean_t) ** 2 for t in times) / len(times)
        std_dev = math.sqrt(variance) if variance > 0 else 0.001

        cv = std_dev / mean_t if mean_t > 0 else 1.0

        # Approximate shape from CV (inverse relationship)
        # For Weibull: CV ~ Gamma(1 + 1/k) / Gamma(1 + 2/k) - 1
        # Simplified: k ~ 1.2 / cv for typical infrastructure components
        if cv > 0:
            shape_k = max(0.5, min(5.0, 1.2 / cv))
        else:
            shape_k = 1.0

        # Scale from mean: lambda = mean / Gamma(1 + 1/k)
        # Use Stirling-like approximation for Gamma(1+1/k)
        gamma_approx = math.gamma(1.0 + 1.0 / shape_k)
        scale_lambda = mean_t / gamma_approx if gamma_approx > 0 else mean_t

        return (round(shape_k, 3), round(scale_lambda, 3))

    @staticmethod
    def hazard_function(t: float, shape: float, scale: float) -> float:
        """Compute the Weibull hazard (instantaneous failure rate) at time *t*.

        h(t) = (k / lambda) * (t / lambda)^(k-1)

        Parameters:
            t: Time at which to evaluate.
            shape: Weibull shape parameter (k).
            scale: Weibull scale parameter (lambda).

        Returns:
            Instantaneous hazard rate.
        """
        if scale <= 0 or t < 0:
            return 0.0
        if t == 0 and shape < 1:
            return float("inf")  # infant mortality
        if t == 0:
            return (shape / scale) if shape == 1 else 0.0

        return (shape / scale) * ((t / scale) ** (shape - 1))

    def predict_remaining_life(self, component: Component) -> float:
        """Predict remaining useful life (hours) for a single component.

        Uses the component's MTBF, current utilisation, and degradation
        profile to estimate how many hours remain before probable failure.
        """
        mtbf = component.operational_profile.mtbf_hours
        if mtbf <= 0:
            mtbf = 8760.0  # default 1 year

        # Stress factor from utilisation (higher util -> shorter life)
        util = component.utilization()
        stress = 1.0 + (util / 100.0) * 2.0  # up to 3x acceleration

        # Degradation acceleration
        degradation = component.operational_profile.degradation
        degrade_factor = 1.0
        if degradation.memory_leak_mb_per_hour > 0:
            total_mem = component.metrics.memory_total_mb or 8192.0
            hours_to_oom = total_mem / degradation.memory_leak_mb_per_hour
            degrade_factor = max(degrade_factor, mtbf / max(hours_to_oom, 1.0))
        if degradation.disk_fill_gb_per_hour > 0:
            total_disk = component.metrics.disk_total_gb or 100.0
            free_disk = total_disk * (1.0 - component.metrics.disk_percent / 100.0)
            hours_to_full = free_disk / degradation.disk_fill_gb_per_hour if free_disk > 0 else 1.0
            degrade_factor = max(degrade_factor, mtbf / max(hours_to_full, 1.0))

        effective_mtbf = mtbf / (stress * degrade_factor)

        # Weibull-based prediction (assume shape ~ 1.5 for wear-out)
        shape_k = 1.5
        # Remaining life as fraction of effective MTBF
        remaining = effective_mtbf * math.gamma(1.0 + 1.0 / shape_k)

        return max(0.0, round(remaining, 1))

    def analyze_all(self) -> SurvivalReport:
        """Run survival analysis on every component in the graph.

        Generates synthetic failure histories from MTBF, fits survival
        curves, and flags high-risk components.
        """
        curves: list[SurvivalCurve] = []
        remaining_lives: list[float] = []
        high_risk: list[str] = []

        for comp_id, comp in self.graph.components.items():
            # Generate synthetic failure times from MTBF
            failure_times = self._generate_failure_times(comp)
            censored = [False] * len(failure_times)
            # Last observation is censored (still running)
            if censored:
                censored[-1] = True

            curve = self.kaplan_meier(failure_times, censored)
            curve.component_id = comp_id
            curves.append(curve)

            rl = self.predict_remaining_life(comp)
            remaining_lives.append(rl)

            if rl < self.HIGH_RISK_THRESHOLD_HOURS:
                high_risk.append(comp_id)

        avg_rl = (
            sum(remaining_lives) / len(remaining_lives) if remaining_lives else 0.0
        )

        return SurvivalReport(
            per_component=curves,
            high_risk=high_risk,
            avg_remaining_life=round(avg_rl, 1),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_failure_times(component: Component, n_samples: int = 10) -> list[float]:
        """Synthesise failure times from a component's MTBF.

        Uses a simple exponential model seeded by the component's MTBF.
        The times are deterministic (based on MTBF ratios) so that
        results are reproducible without an RNG.
        """
        mtbf = component.operational_profile.mtbf_hours
        if mtbf <= 0:
            mtbf = 8760.0

        # Generate evenly-spaced quantile-based failure times
        times: list[float] = []
        for i in range(1, n_samples + 1):
            # Inverse CDF of exponential: -mtbf * ln(1 - p)
            p = i / (n_samples + 1)
            t = -mtbf * math.log(1.0 - p)
            times.append(round(t, 2))

        return times
