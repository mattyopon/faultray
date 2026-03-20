# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Industry Resilience Benchmark — peer comparison engine.

Compares a system's resilience profile against industry benchmarks.
Provides context like "your recovery time is in the top 20% of fintech
companies" or "your redundancy level is below the median for healthcare
systems." Helps organizations understand where they stand relative to peers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class IndustryVertical(str, Enum):
    FINTECH = "fintech"
    HEALTHCARE = "healthcare"
    ECOMMERCE = "ecommerce"
    SAAS = "saas"
    GAMING = "gaming"
    MEDIA = "media"
    GOVERNMENT = "government"
    TELECOM = "telecom"
    MANUFACTURING = "manufacturing"
    STARTUP = "startup"


class BenchmarkMetric(str, Enum):
    AVAILABILITY = "availability"
    MTTR_MINUTES = "mttr_minutes"
    MTBF_HOURS = "mtbf_hours"
    REDUNDANCY_RATIO = "redundancy_ratio"
    SPOF_COUNT = "spof_count"
    RECOVERY_TIME_MINUTES = "recovery_time_minutes"
    INCIDENT_FREQUENCY = "incident_frequency"
    AUTOMATION_PERCENT = "automation_percent"


class MaturityLevel(str, Enum):
    INITIAL = "initial"
    DEVELOPING = "developing"
    DEFINED = "defined"
    MANAGED = "managed"
    OPTIMIZING = "optimizing"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class IndustryBenchmark(BaseModel):
    """Statistical benchmark for one metric in one vertical."""

    vertical: IndustryVertical
    metric: BenchmarkMetric
    p25: float
    p50: float
    p75: float
    p90: float
    unit: str


class BenchmarkComparison(BaseModel):
    """Comparison of current value against industry benchmark."""

    metric: BenchmarkMetric
    current_value: float
    industry_p50: float
    percentile: float
    rating: str  # below_average | average | above_average | top_performer
    gap_to_p50: float


class ResilienceProfile(BaseModel):
    """Aggregated resilience profile across all metrics."""

    overall_percentile: float
    maturity_level: MaturityLevel
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    comparisons: list[BenchmarkComparison] = Field(default_factory=list)


class BenchmarkReport(BaseModel):
    """Full benchmark report for a system."""

    vertical: IndustryVertical
    profile: ResilienceProfile
    top_improvements: list[str] = Field(default_factory=list)
    estimated_effort_to_p75: dict[str, str] = Field(default_factory=dict)
    generated_at: datetime


# ---------------------------------------------------------------------------
# Built-in benchmark data (10 verticals x 8 metrics = 80 entries)
# ---------------------------------------------------------------------------
# For "lower is better" metrics (MTTR, SPOF_COUNT, RECOVERY_TIME, INCIDENT_FREQUENCY):
#   p25 is the *worst* quartile (highest value), p90 is the *best* (lowest).
# For "higher is better" metrics (AVAILABILITY, MTBF, REDUNDANCY_RATIO, AUTOMATION):
#   p25 is the worst quartile (lowest value), p90 is the best (highest).

_BENCHMARK_DATA: dict[tuple[IndustryVertical, BenchmarkMetric], IndustryBenchmark] = {}


def _b(v: IndustryVertical, m: BenchmarkMetric, p25: float, p50: float, p75: float, p90: float, unit: str) -> None:
    _BENCHMARK_DATA[(v, m)] = IndustryBenchmark(vertical=v, metric=m, p25=p25, p50=p50, p75=p75, p90=p90, unit=unit)


# --- FINTECH ---
_b(IndustryVertical.FINTECH, BenchmarkMetric.AVAILABILITY, 99.5, 99.9, 99.95, 99.99, "%")
_b(IndustryVertical.FINTECH, BenchmarkMetric.MTTR_MINUTES, 120, 45, 15, 5, "min")
_b(IndustryVertical.FINTECH, BenchmarkMetric.MTBF_HOURS, 200, 720, 2160, 4320, "hrs")
_b(IndustryVertical.FINTECH, BenchmarkMetric.REDUNDANCY_RATIO, 1.2, 2.0, 3.0, 4.0, "x")
_b(IndustryVertical.FINTECH, BenchmarkMetric.SPOF_COUNT, 8, 3, 1, 0, "count")
_b(IndustryVertical.FINTECH, BenchmarkMetric.RECOVERY_TIME_MINUTES, 90, 30, 10, 3, "min")
_b(IndustryVertical.FINTECH, BenchmarkMetric.INCIDENT_FREQUENCY, 12, 4, 1.5, 0.5, "/month")
_b(IndustryVertical.FINTECH, BenchmarkMetric.AUTOMATION_PERCENT, 30, 55, 75, 90, "%")

# --- HEALTHCARE ---
_b(IndustryVertical.HEALTHCARE, BenchmarkMetric.AVAILABILITY, 99.0, 99.9, 99.95, 99.99, "%")
_b(IndustryVertical.HEALTHCARE, BenchmarkMetric.MTTR_MINUTES, 180, 60, 20, 8, "min")
_b(IndustryVertical.HEALTHCARE, BenchmarkMetric.MTBF_HOURS, 150, 500, 1500, 3000, "hrs")
_b(IndustryVertical.HEALTHCARE, BenchmarkMetric.REDUNDANCY_RATIO, 1.0, 1.8, 2.5, 3.5, "x")
_b(IndustryVertical.HEALTHCARE, BenchmarkMetric.SPOF_COUNT, 10, 5, 2, 0, "count")
_b(IndustryVertical.HEALTHCARE, BenchmarkMetric.RECOVERY_TIME_MINUTES, 120, 45, 15, 5, "min")
_b(IndustryVertical.HEALTHCARE, BenchmarkMetric.INCIDENT_FREQUENCY, 15, 6, 2, 0.8, "/month")
_b(IndustryVertical.HEALTHCARE, BenchmarkMetric.AUTOMATION_PERCENT, 20, 40, 60, 80, "%")

# --- ECOMMERCE ---
_b(IndustryVertical.ECOMMERCE, BenchmarkMetric.AVAILABILITY, 99.0, 99.5, 99.9, 99.99, "%")
_b(IndustryVertical.ECOMMERCE, BenchmarkMetric.MTTR_MINUTES, 150, 50, 18, 6, "min")
_b(IndustryVertical.ECOMMERCE, BenchmarkMetric.MTBF_HOURS, 100, 400, 1200, 2500, "hrs")
_b(IndustryVertical.ECOMMERCE, BenchmarkMetric.REDUNDANCY_RATIO, 1.1, 1.8, 2.8, 3.8, "x")
_b(IndustryVertical.ECOMMERCE, BenchmarkMetric.SPOF_COUNT, 12, 5, 2, 0, "count")
_b(IndustryVertical.ECOMMERCE, BenchmarkMetric.RECOVERY_TIME_MINUTES, 100, 35, 12, 4, "min")
_b(IndustryVertical.ECOMMERCE, BenchmarkMetric.INCIDENT_FREQUENCY, 18, 7, 3, 1, "/month")
_b(IndustryVertical.ECOMMERCE, BenchmarkMetric.AUTOMATION_PERCENT, 25, 45, 65, 85, "%")

# --- SAAS ---
_b(IndustryVertical.SAAS, BenchmarkMetric.AVAILABILITY, 99.5, 99.9, 99.95, 99.99, "%")
_b(IndustryVertical.SAAS, BenchmarkMetric.MTTR_MINUTES, 100, 40, 12, 4, "min")
_b(IndustryVertical.SAAS, BenchmarkMetric.MTBF_HOURS, 250, 800, 2400, 5000, "hrs")
_b(IndustryVertical.SAAS, BenchmarkMetric.REDUNDANCY_RATIO, 1.3, 2.2, 3.2, 4.5, "x")
_b(IndustryVertical.SAAS, BenchmarkMetric.SPOF_COUNT, 6, 2, 1, 0, "count")
_b(IndustryVertical.SAAS, BenchmarkMetric.RECOVERY_TIME_MINUTES, 80, 25, 8, 2, "min")
_b(IndustryVertical.SAAS, BenchmarkMetric.INCIDENT_FREQUENCY, 10, 3, 1, 0.3, "/month")
_b(IndustryVertical.SAAS, BenchmarkMetric.AUTOMATION_PERCENT, 35, 60, 80, 95, "%")

# --- GAMING ---
_b(IndustryVertical.GAMING, BenchmarkMetric.AVAILABILITY, 99.0, 99.5, 99.9, 99.95, "%")
_b(IndustryVertical.GAMING, BenchmarkMetric.MTTR_MINUTES, 90, 35, 10, 3, "min")
_b(IndustryVertical.GAMING, BenchmarkMetric.MTBF_HOURS, 100, 350, 1000, 2000, "hrs")
_b(IndustryVertical.GAMING, BenchmarkMetric.REDUNDANCY_RATIO, 1.0, 1.5, 2.5, 3.5, "x")
_b(IndustryVertical.GAMING, BenchmarkMetric.SPOF_COUNT, 15, 7, 3, 1, "count")
_b(IndustryVertical.GAMING, BenchmarkMetric.RECOVERY_TIME_MINUTES, 60, 20, 7, 2, "min")
_b(IndustryVertical.GAMING, BenchmarkMetric.INCIDENT_FREQUENCY, 20, 8, 3, 1, "/month")
_b(IndustryVertical.GAMING, BenchmarkMetric.AUTOMATION_PERCENT, 20, 40, 60, 80, "%")

# --- MEDIA ---
_b(IndustryVertical.MEDIA, BenchmarkMetric.AVAILABILITY, 99.0, 99.5, 99.9, 99.95, "%")
_b(IndustryVertical.MEDIA, BenchmarkMetric.MTTR_MINUTES, 120, 45, 15, 5, "min")
_b(IndustryVertical.MEDIA, BenchmarkMetric.MTBF_HOURS, 150, 500, 1500, 3000, "hrs")
_b(IndustryVertical.MEDIA, BenchmarkMetric.REDUNDANCY_RATIO, 1.0, 1.5, 2.5, 3.0, "x")
_b(IndustryVertical.MEDIA, BenchmarkMetric.SPOF_COUNT, 10, 5, 2, 1, "count")
_b(IndustryVertical.MEDIA, BenchmarkMetric.RECOVERY_TIME_MINUTES, 90, 30, 10, 3, "min")
_b(IndustryVertical.MEDIA, BenchmarkMetric.INCIDENT_FREQUENCY, 14, 5, 2, 0.5, "/month")
_b(IndustryVertical.MEDIA, BenchmarkMetric.AUTOMATION_PERCENT, 25, 45, 65, 80, "%")

# --- GOVERNMENT ---
_b(IndustryVertical.GOVERNMENT, BenchmarkMetric.AVAILABILITY, 98.0, 99.0, 99.5, 99.9, "%")
_b(IndustryVertical.GOVERNMENT, BenchmarkMetric.MTTR_MINUTES, 240, 90, 30, 10, "min")
_b(IndustryVertical.GOVERNMENT, BenchmarkMetric.MTBF_HOURS, 100, 300, 800, 1500, "hrs")
_b(IndustryVertical.GOVERNMENT, BenchmarkMetric.REDUNDANCY_RATIO, 1.0, 1.3, 2.0, 2.5, "x")
_b(IndustryVertical.GOVERNMENT, BenchmarkMetric.SPOF_COUNT, 15, 8, 4, 1, "count")
_b(IndustryVertical.GOVERNMENT, BenchmarkMetric.RECOVERY_TIME_MINUTES, 180, 60, 25, 10, "min")
_b(IndustryVertical.GOVERNMENT, BenchmarkMetric.INCIDENT_FREQUENCY, 20, 10, 4, 1.5, "/month")
_b(IndustryVertical.GOVERNMENT, BenchmarkMetric.AUTOMATION_PERCENT, 10, 25, 45, 65, "%")

# --- TELECOM ---
_b(IndustryVertical.TELECOM, BenchmarkMetric.AVAILABILITY, 99.5, 99.9, 99.99, 99.999, "%")
_b(IndustryVertical.TELECOM, BenchmarkMetric.MTTR_MINUTES, 60, 25, 8, 3, "min")
_b(IndustryVertical.TELECOM, BenchmarkMetric.MTBF_HOURS, 300, 1000, 3000, 8760, "hrs")
_b(IndustryVertical.TELECOM, BenchmarkMetric.REDUNDANCY_RATIO, 1.5, 2.5, 3.5, 5.0, "x")
_b(IndustryVertical.TELECOM, BenchmarkMetric.SPOF_COUNT, 5, 2, 0, 0, "count")
_b(IndustryVertical.TELECOM, BenchmarkMetric.RECOVERY_TIME_MINUTES, 45, 15, 5, 1, "min")
_b(IndustryVertical.TELECOM, BenchmarkMetric.INCIDENT_FREQUENCY, 8, 3, 1, 0.2, "/month")
_b(IndustryVertical.TELECOM, BenchmarkMetric.AUTOMATION_PERCENT, 40, 65, 85, 95, "%")

# --- MANUFACTURING ---
_b(IndustryVertical.MANUFACTURING, BenchmarkMetric.AVAILABILITY, 98.0, 99.0, 99.5, 99.9, "%")
_b(IndustryVertical.MANUFACTURING, BenchmarkMetric.MTTR_MINUTES, 240, 90, 30, 10, "min")
_b(IndustryVertical.MANUFACTURING, BenchmarkMetric.MTBF_HOURS, 100, 400, 1200, 2500, "hrs")
_b(IndustryVertical.MANUFACTURING, BenchmarkMetric.REDUNDANCY_RATIO, 1.0, 1.3, 2.0, 3.0, "x")
_b(IndustryVertical.MANUFACTURING, BenchmarkMetric.SPOF_COUNT, 12, 6, 3, 1, "count")
_b(IndustryVertical.MANUFACTURING, BenchmarkMetric.RECOVERY_TIME_MINUTES, 150, 60, 20, 8, "min")
_b(IndustryVertical.MANUFACTURING, BenchmarkMetric.INCIDENT_FREQUENCY, 16, 7, 3, 1, "/month")
_b(IndustryVertical.MANUFACTURING, BenchmarkMetric.AUTOMATION_PERCENT, 15, 30, 50, 70, "%")

# --- STARTUP ---
_b(IndustryVertical.STARTUP, BenchmarkMetric.AVAILABILITY, 95.0, 99.0, 99.5, 99.9, "%")
_b(IndustryVertical.STARTUP, BenchmarkMetric.MTTR_MINUTES, 180, 60, 20, 8, "min")
_b(IndustryVertical.STARTUP, BenchmarkMetric.MTBF_HOURS, 50, 200, 600, 1500, "hrs")
_b(IndustryVertical.STARTUP, BenchmarkMetric.REDUNDANCY_RATIO, 1.0, 1.2, 1.8, 2.5, "x")
_b(IndustryVertical.STARTUP, BenchmarkMetric.SPOF_COUNT, 20, 10, 5, 2, "count")
_b(IndustryVertical.STARTUP, BenchmarkMetric.RECOVERY_TIME_MINUTES, 120, 45, 15, 5, "min")
_b(IndustryVertical.STARTUP, BenchmarkMetric.INCIDENT_FREQUENCY, 25, 12, 5, 2, "/month")
_b(IndustryVertical.STARTUP, BenchmarkMetric.AUTOMATION_PERCENT, 10, 25, 45, 65, "%")

# Metrics where lower is better (percentile calculation is inverted)
_LOWER_IS_BETTER = {
    BenchmarkMetric.MTTR_MINUTES,
    BenchmarkMetric.SPOF_COUNT,
    BenchmarkMetric.RECOVERY_TIME_MINUTES,
    BenchmarkMetric.INCIDENT_FREQUENCY,
}

# Effort estimates for reaching p75 from below-average position
_EFFORT_MAP: dict[BenchmarkMetric, str] = {
    BenchmarkMetric.AVAILABILITY: "2-4 weeks: add health checks, failover, and multi-AZ",
    BenchmarkMetric.MTTR_MINUTES: "1-3 weeks: automate runbooks, improve monitoring",
    BenchmarkMetric.MTBF_HOURS: "4-8 weeks: chaos testing, dependency hardening",
    BenchmarkMetric.REDUNDANCY_RATIO: "2-4 weeks: add replicas, configure failover",
    BenchmarkMetric.SPOF_COUNT: "3-6 weeks: identify and eliminate single points of failure",
    BenchmarkMetric.RECOVERY_TIME_MINUTES: "2-4 weeks: automate DR, add backup verification",
    BenchmarkMetric.INCIDENT_FREQUENCY: "4-8 weeks: proactive monitoring, capacity planning",
    BenchmarkMetric.AUTOMATION_PERCENT: "3-6 weeks: IaC adoption, CI/CD pipelines",
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ResilienceBenchmarkEngine:
    """Benchmark a system's resilience against industry peers."""

    def __init__(self, graph: InfraGraph, vertical: IndustryVertical) -> None:
        self._graph = graph
        self._vertical = vertical
        self._benchmarks: dict[BenchmarkMetric, IndustryBenchmark] = {}
        for metric in BenchmarkMetric:
            key = (vertical, metric)
            if key in _BENCHMARK_DATA:
                self._benchmarks[metric] = _BENCHMARK_DATA[key]

    # -- public API ---------------------------------------------------------

    def get_benchmark(self, metric: BenchmarkMetric) -> IndustryBenchmark:
        """Return the industry benchmark for a given metric."""
        return self._benchmarks[metric]

    def measure_current(self, metric: BenchmarkMetric) -> float:
        """Measure current value of *metric* from the graph."""
        components = list(self._graph.components.values())
        if not components:
            return 0.0

        if metric == BenchmarkMetric.AVAILABILITY:
            return self._measure_availability(components)
        if metric == BenchmarkMetric.MTTR_MINUTES:
            return self._measure_mttr(components)
        if metric == BenchmarkMetric.MTBF_HOURS:
            return self._measure_mtbf(components)
        if metric == BenchmarkMetric.REDUNDANCY_RATIO:
            return self._measure_redundancy_ratio(components)
        if metric == BenchmarkMetric.SPOF_COUNT:
            return self._measure_spof_count(components)
        if metric == BenchmarkMetric.RECOVERY_TIME_MINUTES:
            return self._measure_recovery_time(components)
        if metric == BenchmarkMetric.INCIDENT_FREQUENCY:
            return self._measure_incident_frequency(components)
        if metric == BenchmarkMetric.AUTOMATION_PERCENT:
            return self._measure_automation_percent(components)
        return 0.0  # pragma: no cover

    def compare_metric(self, metric: BenchmarkMetric) -> BenchmarkComparison:
        """Compare current value of a metric against the industry benchmark."""
        current = self.measure_current(metric)
        bench = self.get_benchmark(metric)
        percentile = self._compute_percentile(current, bench, metric)
        rating = self._percentile_to_rating(percentile)
        gap = current - bench.p50
        if metric in _LOWER_IS_BETTER:
            gap = bench.p50 - current  # positive means you're better

        return BenchmarkComparison(
            metric=metric,
            current_value=round(current, 4),
            industry_p50=bench.p50,
            percentile=round(percentile, 1),
            rating=rating,
            gap_to_p50=round(gap, 4),
        )

    def build_profile(self) -> ResilienceProfile:
        """Build a full resilience profile across all metrics."""
        comparisons: list[BenchmarkComparison] = []
        for metric in BenchmarkMetric:
            comparisons.append(self.compare_metric(metric))

        avg_pct = sum(c.percentile for c in comparisons) / len(comparisons)
        maturity = self._percentile_to_maturity(avg_pct)

        strengths: list[str] = []
        weaknesses: list[str] = []
        for comp in comparisons:
            if comp.rating == "top_performer":
                strengths.append(
                    f"{comp.metric.value}: top performer (p{comp.percentile:.0f})"
                )
            elif comp.rating == "above_average":
                strengths.append(
                    f"{comp.metric.value}: above average (p{comp.percentile:.0f})"
                )
            elif comp.rating == "below_average":
                weaknesses.append(
                    f"{comp.metric.value}: below average (p{comp.percentile:.0f})"
                )

        return ResilienceProfile(
            overall_percentile=round(avg_pct, 1),
            maturity_level=maturity,
            strengths=strengths,
            weaknesses=weaknesses,
            comparisons=comparisons,
        )

    def generate_report(self) -> BenchmarkReport:
        """Generate a full benchmark report."""
        profile = self.build_profile()

        # Identify top improvements (weakest metrics first)
        sorted_comps = sorted(profile.comparisons, key=lambda c: c.percentile)
        top_improvements: list[str] = []
        effort: dict[str, str] = {}
        for comp in sorted_comps:
            if comp.percentile < 75:
                improvement = (
                    f"Improve {comp.metric.value} from {comp.current_value} "
                    f"to reach p75 ({self.get_benchmark(comp.metric).p75})"
                )
                top_improvements.append(improvement)
                effort[comp.metric.value] = _EFFORT_MAP.get(
                    comp.metric, "Varies"
                )

        return BenchmarkReport(
            vertical=self._vertical,
            profile=profile,
            top_improvements=top_improvements[:5],
            estimated_effort_to_p75=effort,
            generated_at=datetime.now(timezone.utc),
        )

    # -- measurement helpers ------------------------------------------------

    @staticmethod
    def _measure_availability(components: list[Component]) -> float:
        health_map = {
            HealthStatus.HEALTHY: 100.0,
            HealthStatus.DEGRADED: 99.0,
            HealthStatus.OVERLOADED: 95.0,
            HealthStatus.DOWN: 0.0,
        }
        total = sum(health_map.get(c.health, 0.0) for c in components)
        return total / len(components) if components else 0.0

    @staticmethod
    def _measure_mttr(components: list[Component]) -> float:
        values = [c.operational_profile.mttr_minutes for c in components]
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _measure_mtbf(components: list[Component]) -> float:
        values = [c.operational_profile.mtbf_hours for c in components if c.operational_profile.mtbf_hours > 0]
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _measure_redundancy_ratio(components: list[Component]) -> float:
        if not components:
            return 0.0
        return sum(c.replicas for c in components) / len(components)

    def _measure_spof_count(self, components: list[Component]) -> float:
        count = 0
        for c in components:
            if c.replicas <= 1 and not c.failover.enabled:
                dependents = self._graph.get_dependents(c.id)
                if dependents:
                    count += 1
        return float(count)

    @staticmethod
    def _measure_recovery_time(components: list[Component]) -> float:
        times: list[float] = []
        for c in components:
            if c.failover.enabled:
                times.append(c.failover.promotion_time_seconds / 60.0)
            else:
                times.append(c.operational_profile.mttr_minutes)
        return max(times) if times else 0.0

    @staticmethod
    def _measure_incident_frequency(components: list[Component]) -> float:
        if not components:
            return 0.0
        total_rate = 0.0
        for c in components:
            if c.operational_profile.mtbf_hours > 0:
                # monthly incidents = 730 hours / MTBF
                total_rate += 730.0 / c.operational_profile.mtbf_hours
        return total_rate

    @staticmethod
    def _measure_automation_percent(components: list[Component]) -> float:
        values = [c.team.automation_percent for c in components]
        return sum(values) / len(values) if values else 0.0

    # -- percentile / rating helpers ----------------------------------------

    @staticmethod
    def _compute_percentile(
        value: float, bench: IndustryBenchmark, metric: BenchmarkMetric
    ) -> float:
        """Compute the percentile rank of *value* within the benchmark distribution.

        Uses linear interpolation between p25/p50/p75/p90 breakpoints.
        """
        lower_is_better = metric in _LOWER_IS_BETTER

        if lower_is_better:
            # For lower-is-better: p25 is worst (highest), p90 is best (lowest)
            # Invert so we can use ascending logic
            points = [
                (bench.p90, 90.0),
                (bench.p75, 75.0),
                (bench.p50, 50.0),
                (bench.p25, 25.0),
            ]
            # lower value = better percentile
            if value <= bench.p90:
                return 95.0
            if value > bench.p25:
                return 10.0
        else:
            # higher is better
            points = [
                (bench.p25, 25.0),
                (bench.p50, 50.0),
                (bench.p75, 75.0),
                (bench.p90, 90.0),
            ]
            if value >= bench.p90:
                return 95.0
            if value < bench.p25:
                return 10.0

        # Sort points ascending by value for interpolation
        points.sort(key=lambda p: p[0])

        # Linear interpolation
        for i in range(len(points) - 1):
            v_lo, p_lo = points[i]
            v_hi, p_hi = points[i + 1]
            if v_lo <= value <= v_hi:
                if v_hi == v_lo:
                    return (p_lo + p_hi) / 2.0
                frac = (value - v_lo) / (v_hi - v_lo)
                return p_lo + frac * (p_hi - p_lo)

        return 50.0  # pragma: no cover

    @staticmethod
    def _percentile_to_rating(percentile: float) -> str:
        if percentile >= 75:
            return "top_performer"
        if percentile >= 50:
            return "above_average"
        if percentile >= 25:
            return "average"
        return "below_average"

    @staticmethod
    def _percentile_to_maturity(percentile: float) -> MaturityLevel:
        if percentile >= 80:
            return MaturityLevel.OPTIMIZING
        if percentile >= 60:
            return MaturityLevel.MANAGED
        if percentile >= 40:
            return MaturityLevel.DEFINED
        if percentile >= 20:
            return MaturityLevel.DEVELOPING
        return MaturityLevel.INITIAL
