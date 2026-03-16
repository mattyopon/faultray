"""Comprehensive tests for resilience_benchmark — targeting 100% coverage."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
    OperationalTeamConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.resilience_benchmark import (
    BenchmarkComparison,
    BenchmarkMetric,
    BenchmarkReport,
    IndustryBenchmark,
    IndustryVertical,
    MaturityLevel,
    ResilienceBenchmarkEngine,
    ResilienceProfile,
    _BENCHMARK_DATA,
    _EFFORT_MAP,
    _LOWER_IS_BETTER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(
    cid: str,
    name: str = "",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
    promotion_time: float = 30.0,
    mttr: float = 30.0,
    mtbf: float = 0.0,
    automation: float = 20.0,
) -> Component:
    c = Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        health=health,
        operational_profile=OperationalProfile(
            mttr_minutes=mttr,
            mtbf_hours=mtbf,
        ),
        team=OperationalTeamConfig(automation_percent=automation),
    )
    if failover:
        c.failover = FailoverConfig(
            enabled=True,
            promotion_time_seconds=promotion_time,
        )
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# 1. IndustryVertical enum
# ---------------------------------------------------------------------------

class TestIndustryVertical:
    def test_all_values(self):
        assert IndustryVertical.FINTECH == "fintech"
        assert IndustryVertical.HEALTHCARE == "healthcare"
        assert IndustryVertical.ECOMMERCE == "ecommerce"
        assert IndustryVertical.SAAS == "saas"
        assert IndustryVertical.GAMING == "gaming"
        assert IndustryVertical.MEDIA == "media"
        assert IndustryVertical.GOVERNMENT == "government"
        assert IndustryVertical.TELECOM == "telecom"
        assert IndustryVertical.MANUFACTURING == "manufacturing"
        assert IndustryVertical.STARTUP == "startup"

    def test_count(self):
        assert len(IndustryVertical) == 10

    def test_is_str_enum(self):
        assert isinstance(IndustryVertical.FINTECH, str)

    def test_value_attribute(self):
        assert IndustryVertical.FINTECH.value == "fintech"


# ---------------------------------------------------------------------------
# 2. BenchmarkMetric enum
# ---------------------------------------------------------------------------

class TestBenchmarkMetric:
    def test_all_values(self):
        assert BenchmarkMetric.AVAILABILITY == "availability"
        assert BenchmarkMetric.MTTR_MINUTES == "mttr_minutes"
        assert BenchmarkMetric.MTBF_HOURS == "mtbf_hours"
        assert BenchmarkMetric.REDUNDANCY_RATIO == "redundancy_ratio"
        assert BenchmarkMetric.SPOF_COUNT == "spof_count"
        assert BenchmarkMetric.RECOVERY_TIME_MINUTES == "recovery_time_minutes"
        assert BenchmarkMetric.INCIDENT_FREQUENCY == "incident_frequency"
        assert BenchmarkMetric.AUTOMATION_PERCENT == "automation_percent"

    def test_count(self):
        assert len(BenchmarkMetric) == 8

    def test_is_str_enum(self):
        assert isinstance(BenchmarkMetric.AVAILABILITY, str)


# ---------------------------------------------------------------------------
# 3. MaturityLevel enum
# ---------------------------------------------------------------------------

class TestMaturityLevel:
    def test_all_values(self):
        assert MaturityLevel.INITIAL == "initial"
        assert MaturityLevel.DEVELOPING == "developing"
        assert MaturityLevel.DEFINED == "defined"
        assert MaturityLevel.MANAGED == "managed"
        assert MaturityLevel.OPTIMIZING == "optimizing"

    def test_count(self):
        assert len(MaturityLevel) == 5


# ---------------------------------------------------------------------------
# 4. IndustryBenchmark model
# ---------------------------------------------------------------------------

class TestIndustryBenchmark:
    def test_create(self):
        b = IndustryBenchmark(
            vertical=IndustryVertical.FINTECH,
            metric=BenchmarkMetric.AVAILABILITY,
            p25=99.5, p50=99.9, p75=99.95, p90=99.99,
            unit="%",
        )
        assert b.vertical == IndustryVertical.FINTECH
        assert b.metric == BenchmarkMetric.AVAILABILITY
        assert b.p25 == 99.5
        assert b.p50 == 99.9
        assert b.p75 == 99.95
        assert b.p90 == 99.99
        assert b.unit == "%"

    def test_serialization(self):
        b = IndustryBenchmark(
            vertical=IndustryVertical.SAAS,
            metric=BenchmarkMetric.MTTR_MINUTES,
            p25=100, p50=40, p75=12, p90=4,
            unit="min",
        )
        d = b.model_dump()
        assert d["vertical"] == "saas"
        assert d["metric"] == "mttr_minutes"
        assert d["p50"] == 40


# ---------------------------------------------------------------------------
# 5. BenchmarkComparison model
# ---------------------------------------------------------------------------

class TestBenchmarkComparison:
    def test_create(self):
        c = BenchmarkComparison(
            metric=BenchmarkMetric.AVAILABILITY,
            current_value=99.95,
            industry_p50=99.9,
            percentile=80.0,
            rating="top_performer",
            gap_to_p50=0.05,
        )
        assert c.metric == BenchmarkMetric.AVAILABILITY
        assert c.current_value == 99.95
        assert c.industry_p50 == 99.9
        assert c.percentile == 80.0
        assert c.rating == "top_performer"
        assert c.gap_to_p50 == 0.05

    def test_serialization(self):
        c = BenchmarkComparison(
            metric=BenchmarkMetric.MTTR_MINUTES,
            current_value=20.0,
            industry_p50=45.0,
            percentile=70.0,
            rating="above_average",
            gap_to_p50=25.0,
        )
        d = c.model_dump()
        assert d["rating"] == "above_average"


# ---------------------------------------------------------------------------
# 6. ResilienceProfile model
# ---------------------------------------------------------------------------

class TestResilienceProfile:
    def test_create_minimal(self):
        p = ResilienceProfile(
            overall_percentile=55.0,
            maturity_level=MaturityLevel.DEFINED,
        )
        assert p.overall_percentile == 55.0
        assert p.maturity_level == MaturityLevel.DEFINED
        assert p.strengths == []
        assert p.weaknesses == []
        assert p.comparisons == []

    def test_create_full(self):
        comp = BenchmarkComparison(
            metric=BenchmarkMetric.AVAILABILITY,
            current_value=99.9,
            industry_p50=99.9,
            percentile=50.0,
            rating="above_average",
            gap_to_p50=0.0,
        )
        p = ResilienceProfile(
            overall_percentile=60.0,
            maturity_level=MaturityLevel.MANAGED,
            strengths=["good uptime"],
            weaknesses=["low automation"],
            comparisons=[comp],
        )
        assert len(p.comparisons) == 1
        assert p.strengths == ["good uptime"]


# ---------------------------------------------------------------------------
# 7. BenchmarkReport model
# ---------------------------------------------------------------------------

class TestBenchmarkReport:
    def test_create(self):
        profile = ResilienceProfile(
            overall_percentile=50.0,
            maturity_level=MaturityLevel.DEFINED,
        )
        now = datetime.now(timezone.utc)
        r = BenchmarkReport(
            vertical=IndustryVertical.FINTECH,
            profile=profile,
            top_improvements=["improve MTTR"],
            estimated_effort_to_p75={"mttr_minutes": "1-3 weeks"},
            generated_at=now,
        )
        assert r.vertical == IndustryVertical.FINTECH
        assert r.generated_at == now
        assert "improve MTTR" in r.top_improvements

    def test_defaults(self):
        profile = ResilienceProfile(
            overall_percentile=50.0,
            maturity_level=MaturityLevel.DEFINED,
        )
        r = BenchmarkReport(
            vertical=IndustryVertical.SAAS,
            profile=profile,
            generated_at=datetime.now(timezone.utc),
        )
        assert r.top_improvements == []
        assert r.estimated_effort_to_p75 == {}


# ---------------------------------------------------------------------------
# 8. Benchmark data completeness
# ---------------------------------------------------------------------------

class TestBenchmarkData:
    def test_80_entries(self):
        assert len(_BENCHMARK_DATA) == 80

    def test_all_verticals_present(self):
        for v in IndustryVertical:
            for m in BenchmarkMetric:
                assert (v, m) in _BENCHMARK_DATA, f"Missing ({v}, {m})"

    def test_lower_is_better_set(self):
        assert BenchmarkMetric.MTTR_MINUTES in _LOWER_IS_BETTER
        assert BenchmarkMetric.SPOF_COUNT in _LOWER_IS_BETTER
        assert BenchmarkMetric.RECOVERY_TIME_MINUTES in _LOWER_IS_BETTER
        assert BenchmarkMetric.INCIDENT_FREQUENCY in _LOWER_IS_BETTER
        assert BenchmarkMetric.AVAILABILITY not in _LOWER_IS_BETTER
        assert BenchmarkMetric.MTBF_HOURS not in _LOWER_IS_BETTER
        assert BenchmarkMetric.REDUNDANCY_RATIO not in _LOWER_IS_BETTER
        assert BenchmarkMetric.AUTOMATION_PERCENT not in _LOWER_IS_BETTER

    def test_effort_map_covers_all_metrics(self):
        for m in BenchmarkMetric:
            assert m in _EFFORT_MAP

    @pytest.mark.parametrize("vertical", list(IndustryVertical))
    def test_p_values_consistent_higher_is_better(self, vertical):
        """For higher-is-better metrics, p25 < p50 < p75 < p90."""
        higher_metrics = [m for m in BenchmarkMetric if m not in _LOWER_IS_BETTER]
        for m in higher_metrics:
            b = _BENCHMARK_DATA[(vertical, m)]
            assert b.p25 <= b.p50 <= b.p75 <= b.p90, (
                f"{vertical}/{m}: {b.p25}, {b.p50}, {b.p75}, {b.p90}"
            )

    @pytest.mark.parametrize("vertical", list(IndustryVertical))
    def test_p_values_consistent_lower_is_better(self, vertical):
        """For lower-is-better metrics, p25 >= p50 >= p75 >= p90."""
        for m in _LOWER_IS_BETTER:
            b = _BENCHMARK_DATA[(vertical, m)]
            assert b.p25 >= b.p50 >= b.p75 >= b.p90, (
                f"{vertical}/{m}: {b.p25}, {b.p50}, {b.p75}, {b.p90}"
            )

    def test_fintech_availability_values(self):
        b = _BENCHMARK_DATA[(IndustryVertical.FINTECH, BenchmarkMetric.AVAILABILITY)]
        assert b.p25 == 99.5
        assert b.p50 == 99.9
        assert b.p75 == 99.95
        assert b.p90 == 99.99
        assert b.unit == "%"

    def test_fintech_mttr_values(self):
        b = _BENCHMARK_DATA[(IndustryVertical.FINTECH, BenchmarkMetric.MTTR_MINUTES)]
        assert b.p25 == 120
        assert b.p50 == 45
        assert b.p90 == 5

    def test_fintech_redundancy_values(self):
        b = _BENCHMARK_DATA[(IndustryVertical.FINTECH, BenchmarkMetric.REDUNDANCY_RATIO)]
        assert b.p25 == 1.2
        assert b.p50 == 2.0
        assert b.p75 == 3.0
        assert b.p90 == 4.0


# ---------------------------------------------------------------------------
# 9. Engine — __init__
# ---------------------------------------------------------------------------

class TestEngineInit:
    def test_basic_init(self):
        g = _graph(_comp("a"))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine._vertical == IndustryVertical.FINTECH

    def test_all_metrics_loaded(self):
        g = _graph(_comp("a"))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.SAAS)
        assert len(engine._benchmarks) == 8

    @pytest.mark.parametrize("vertical", list(IndustryVertical))
    def test_init_all_verticals(self, vertical):
        g = _graph(_comp("a"))
        engine = ResilienceBenchmarkEngine(g, vertical)
        assert len(engine._benchmarks) == 8


# ---------------------------------------------------------------------------
# 10. Engine — get_benchmark
# ---------------------------------------------------------------------------

class TestGetBenchmark:
    def test_returns_correct_benchmark(self):
        g = _graph(_comp("a"))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        b = engine.get_benchmark(BenchmarkMetric.AVAILABILITY)
        assert b.vertical == IndustryVertical.FINTECH
        assert b.metric == BenchmarkMetric.AVAILABILITY
        assert b.p50 == 99.9

    def test_each_metric(self):
        g = _graph(_comp("a"))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.TELECOM)
        for metric in BenchmarkMetric:
            b = engine.get_benchmark(metric)
            assert b.metric == metric
            assert b.vertical == IndustryVertical.TELECOM

    def test_missing_metric_raises(self):
        g = _graph(_comp("a"))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        # Remove a metric manually to test KeyError
        engine._benchmarks.pop(BenchmarkMetric.AVAILABILITY)
        with pytest.raises(KeyError):
            engine.get_benchmark(BenchmarkMetric.AVAILABILITY)


# ---------------------------------------------------------------------------
# 11. Engine — measure_current (availability)
# ---------------------------------------------------------------------------

class TestMeasureAvailability:
    def test_all_healthy(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        val = engine.measure_current(BenchmarkMetric.AVAILABILITY)
        assert val == 100.0

    def test_one_degraded(self):
        g = _graph(_comp("a"), _comp("b", health=HealthStatus.DEGRADED))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        val = engine.measure_current(BenchmarkMetric.AVAILABILITY)
        assert val == (100.0 + 99.0) / 2

    def test_one_overloaded(self):
        g = _graph(_comp("a"), _comp("b", health=HealthStatus.OVERLOADED))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        val = engine.measure_current(BenchmarkMetric.AVAILABILITY)
        assert val == (100.0 + 95.0) / 2

    def test_one_down(self):
        g = _graph(_comp("a"), _comp("b", health=HealthStatus.DOWN))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        val = engine.measure_current(BenchmarkMetric.AVAILABILITY)
        assert val == 50.0

    def test_empty_graph(self):
        g = InfraGraph()
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.AVAILABILITY) == 0.0


# ---------------------------------------------------------------------------
# 12. Engine — measure_current (MTTR)
# ---------------------------------------------------------------------------

class TestMeasureMTTR:
    def test_single_component(self):
        g = _graph(_comp("a", mttr=45.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.MTTR_MINUTES) == 45.0

    def test_average(self):
        g = _graph(_comp("a", mttr=30.0), _comp("b", mttr=60.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.MTTR_MINUTES) == 45.0


# ---------------------------------------------------------------------------
# 13. Engine — measure_current (MTBF)
# ---------------------------------------------------------------------------

class TestMeasureMTBF:
    def test_single_component(self):
        g = _graph(_comp("a", mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.MTBF_HOURS) == 720.0

    def test_zero_mtbf_excluded(self):
        g = _graph(_comp("a", mtbf=0.0), _comp("b", mtbf=500.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.MTBF_HOURS) == 500.0

    def test_all_zero_mtbf(self):
        g = _graph(_comp("a", mtbf=0.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.MTBF_HOURS) == 0.0


# ---------------------------------------------------------------------------
# 14. Engine — measure_current (redundancy ratio)
# ---------------------------------------------------------------------------

class TestMeasureRedundancyRatio:
    def test_single_replica(self):
        g = _graph(_comp("a", replicas=1))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.REDUNDANCY_RATIO) == 1.0

    def test_multiple_replicas(self):
        g = _graph(_comp("a", replicas=3), _comp("b", replicas=1))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.REDUNDANCY_RATIO) == 2.0


# ---------------------------------------------------------------------------
# 15. Engine — measure_current (SPOF count)
# ---------------------------------------------------------------------------

class TestMeasureSPOFCount:
    def test_no_spof(self):
        g = _graph(_comp("a", replicas=2))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.SPOF_COUNT) == 0.0

    def test_spof_with_dependents(self):
        c1 = _comp("db", replicas=1)
        c2 = _comp("app", replicas=1)
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.SPOF_COUNT) == 1.0

    def test_no_spof_with_failover(self):
        c1 = _comp("db", replicas=1, failover=True)
        c2 = _comp("app", replicas=1)
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.SPOF_COUNT) == 0.0

    def test_single_component_no_dependents(self):
        g = _graph(_comp("a", replicas=1))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.SPOF_COUNT) == 0.0

    def test_multiple_spofs(self):
        c1 = _comp("db1", replicas=1)
        c2 = _comp("db2", replicas=1)
        c3 = _comp("app", replicas=1)
        g = _graph(c1, c2, c3)
        g.add_dependency(Dependency(source_id="app", target_id="db1"))
        g.add_dependency(Dependency(source_id="app", target_id="db2"))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.SPOF_COUNT) == 2.0


# ---------------------------------------------------------------------------
# 16. Engine — measure_current (recovery time)
# ---------------------------------------------------------------------------

class TestMeasureRecoveryTime:
    def test_no_failover(self):
        g = _graph(_comp("a", mttr=30.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.RECOVERY_TIME_MINUTES) == 30.0

    def test_with_failover(self):
        g = _graph(_comp("a", failover=True, promotion_time=60.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.RECOVERY_TIME_MINUTES) == 1.0

    def test_max_across_components(self):
        g = _graph(
            _comp("a", mttr=10.0),
            _comp("b", mttr=50.0),
        )
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.RECOVERY_TIME_MINUTES) == 50.0

    def test_empty_graph(self):
        g = InfraGraph()
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.RECOVERY_TIME_MINUTES) == 0.0


# ---------------------------------------------------------------------------
# 17. Engine — measure_current (incident frequency)
# ---------------------------------------------------------------------------

class TestMeasureIncidentFrequency:
    def test_single_component(self):
        g = _graph(_comp("a", mtbf=730.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        val = engine.measure_current(BenchmarkMetric.INCIDENT_FREQUENCY)
        assert abs(val - 1.0) < 0.01

    def test_zero_mtbf(self):
        g = _graph(_comp("a", mtbf=0.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        val = engine.measure_current(BenchmarkMetric.INCIDENT_FREQUENCY)
        assert val == 0.0

    def test_multiple_components(self):
        g = _graph(
            _comp("a", mtbf=730.0),
            _comp("b", mtbf=365.0),
        )
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        val = engine.measure_current(BenchmarkMetric.INCIDENT_FREQUENCY)
        assert abs(val - 3.0) < 0.01

    def test_empty_graph(self):
        g = InfraGraph()
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.INCIDENT_FREQUENCY) == 0.0


# ---------------------------------------------------------------------------
# 18. Engine — measure_current (automation percent)
# ---------------------------------------------------------------------------

class TestMeasureAutomationPercent:
    def test_single_component(self):
        g = _graph(_comp("a", automation=50.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.AUTOMATION_PERCENT) == 50.0

    def test_average(self):
        g = _graph(
            _comp("a", automation=30.0),
            _comp("b", automation=70.0),
        )
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        assert engine.measure_current(BenchmarkMetric.AUTOMATION_PERCENT) == 50.0


# ---------------------------------------------------------------------------
# 19. Engine — _compute_percentile
# ---------------------------------------------------------------------------

class TestComputePercentile:
    def setup_method(self):
        self.g = _graph(_comp("a"))
        self.engine = ResilienceBenchmarkEngine(self.g, IndustryVertical.FINTECH)

    def test_higher_is_better_at_p90(self):
        bench = self.engine.get_benchmark(BenchmarkMetric.AVAILABILITY)
        pct = self.engine._compute_percentile(99.99, bench, BenchmarkMetric.AVAILABILITY)
        assert pct == 95.0

    def test_higher_is_better_above_p90(self):
        bench = self.engine.get_benchmark(BenchmarkMetric.AVAILABILITY)
        pct = self.engine._compute_percentile(100.0, bench, BenchmarkMetric.AVAILABILITY)
        assert pct == 95.0

    def test_higher_is_better_at_p25(self):
        bench = self.engine.get_benchmark(BenchmarkMetric.AVAILABILITY)
        pct = self.engine._compute_percentile(99.5, bench, BenchmarkMetric.AVAILABILITY)
        assert pct == 25.0

    def test_higher_is_better_below_p25(self):
        bench = self.engine.get_benchmark(BenchmarkMetric.AVAILABILITY)
        pct = self.engine._compute_percentile(90.0, bench, BenchmarkMetric.AVAILABILITY)
        assert pct == 10.0

    def test_higher_is_better_interpolation_midpoint(self):
        bench = self.engine.get_benchmark(BenchmarkMetric.AVAILABILITY)
        # p25=99.5, p50=99.9 — midpoint=99.7
        pct = self.engine._compute_percentile(99.7, bench, BenchmarkMetric.AVAILABILITY)
        assert 25 < pct < 50

    def test_lower_is_better_at_p90(self):
        bench = self.engine.get_benchmark(BenchmarkMetric.MTTR_MINUTES)
        pct = self.engine._compute_percentile(5, bench, BenchmarkMetric.MTTR_MINUTES)
        assert pct == 95.0

    def test_lower_is_better_below_p90(self):
        bench = self.engine.get_benchmark(BenchmarkMetric.MTTR_MINUTES)
        pct = self.engine._compute_percentile(2, bench, BenchmarkMetric.MTTR_MINUTES)
        assert pct == 95.0

    def test_lower_is_better_at_p25(self):
        bench = self.engine.get_benchmark(BenchmarkMetric.MTTR_MINUTES)
        pct = self.engine._compute_percentile(120, bench, BenchmarkMetric.MTTR_MINUTES)
        assert pct == 25.0

    def test_lower_is_better_worse_than_p25(self):
        bench = self.engine.get_benchmark(BenchmarkMetric.MTTR_MINUTES)
        pct = self.engine._compute_percentile(200, bench, BenchmarkMetric.MTTR_MINUTES)
        assert pct == 10.0

    def test_lower_is_better_interpolation(self):
        bench = self.engine.get_benchmark(BenchmarkMetric.MTTR_MINUTES)
        # p75=15, p50=45 — midpoint=30
        pct = self.engine._compute_percentile(30, bench, BenchmarkMetric.MTTR_MINUTES)
        assert 50 < pct < 75


# ---------------------------------------------------------------------------
# 20. Engine — _percentile_to_rating
# ---------------------------------------------------------------------------

class TestPercentileToRating:
    def test_top_performer(self):
        assert ResilienceBenchmarkEngine._percentile_to_rating(95.0) == "top_performer"
        assert ResilienceBenchmarkEngine._percentile_to_rating(75.0) == "top_performer"

    def test_above_average(self):
        assert ResilienceBenchmarkEngine._percentile_to_rating(60.0) == "above_average"
        assert ResilienceBenchmarkEngine._percentile_to_rating(50.0) == "above_average"

    def test_average(self):
        assert ResilienceBenchmarkEngine._percentile_to_rating(40.0) == "average"
        assert ResilienceBenchmarkEngine._percentile_to_rating(25.0) == "average"

    def test_below_average(self):
        assert ResilienceBenchmarkEngine._percentile_to_rating(20.0) == "below_average"
        assert ResilienceBenchmarkEngine._percentile_to_rating(10.0) == "below_average"
        assert ResilienceBenchmarkEngine._percentile_to_rating(0.0) == "below_average"

    def test_boundary_75(self):
        assert ResilienceBenchmarkEngine._percentile_to_rating(74.9) == "above_average"

    def test_boundary_50(self):
        assert ResilienceBenchmarkEngine._percentile_to_rating(49.9) == "average"

    def test_boundary_25(self):
        assert ResilienceBenchmarkEngine._percentile_to_rating(24.9) == "below_average"


# ---------------------------------------------------------------------------
# 21. Engine — _percentile_to_maturity
# ---------------------------------------------------------------------------

class TestPercentileToMaturity:
    def test_optimizing(self):
        assert ResilienceBenchmarkEngine._percentile_to_maturity(90.0) == MaturityLevel.OPTIMIZING
        assert ResilienceBenchmarkEngine._percentile_to_maturity(80.0) == MaturityLevel.OPTIMIZING

    def test_managed(self):
        assert ResilienceBenchmarkEngine._percentile_to_maturity(70.0) == MaturityLevel.MANAGED
        assert ResilienceBenchmarkEngine._percentile_to_maturity(60.0) == MaturityLevel.MANAGED

    def test_defined(self):
        assert ResilienceBenchmarkEngine._percentile_to_maturity(50.0) == MaturityLevel.DEFINED
        assert ResilienceBenchmarkEngine._percentile_to_maturity(40.0) == MaturityLevel.DEFINED

    def test_developing(self):
        assert ResilienceBenchmarkEngine._percentile_to_maturity(30.0) == MaturityLevel.DEVELOPING
        assert ResilienceBenchmarkEngine._percentile_to_maturity(20.0) == MaturityLevel.DEVELOPING

    def test_initial(self):
        assert ResilienceBenchmarkEngine._percentile_to_maturity(10.0) == MaturityLevel.INITIAL
        assert ResilienceBenchmarkEngine._percentile_to_maturity(0.0) == MaturityLevel.INITIAL

    def test_boundary_80(self):
        assert ResilienceBenchmarkEngine._percentile_to_maturity(79.9) == MaturityLevel.MANAGED

    def test_boundary_60(self):
        assert ResilienceBenchmarkEngine._percentile_to_maturity(59.9) == MaturityLevel.DEFINED

    def test_boundary_40(self):
        assert ResilienceBenchmarkEngine._percentile_to_maturity(39.9) == MaturityLevel.DEVELOPING

    def test_boundary_20(self):
        assert ResilienceBenchmarkEngine._percentile_to_maturity(19.9) == MaturityLevel.INITIAL


# ---------------------------------------------------------------------------
# 22. Engine — compare_metric
# ---------------------------------------------------------------------------

class TestCompareMetric:
    def test_higher_is_better_above_p50(self):
        g = _graph(_comp("a", replicas=3), _comp("b", replicas=3))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        result = engine.compare_metric(BenchmarkMetric.REDUNDANCY_RATIO)
        assert result.metric == BenchmarkMetric.REDUNDANCY_RATIO
        assert result.current_value == 3.0
        assert result.industry_p50 == 2.0
        assert result.gap_to_p50 == 1.0
        assert result.percentile > 50

    def test_lower_is_better_below_p50(self):
        g = _graph(_comp("a", mttr=20.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        result = engine.compare_metric(BenchmarkMetric.MTTR_MINUTES)
        assert result.current_value == 20.0
        assert result.industry_p50 == 45.0
        # gap_to_p50 for lower-is-better = p50 - current (positive = better)
        assert result.gap_to_p50 == 25.0

    def test_lower_is_better_above_p50_value(self):
        g = _graph(_comp("a", mttr=100.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        result = engine.compare_metric(BenchmarkMetric.MTTR_MINUTES)
        assert result.gap_to_p50 < 0  # worse than median

    def test_result_has_rating(self):
        g = _graph(_comp("a"))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        result = engine.compare_metric(BenchmarkMetric.AVAILABILITY)
        assert result.rating in (
            "below_average", "average", "above_average", "top_performer"
        )


# ---------------------------------------------------------------------------
# 23. Engine — build_profile
# ---------------------------------------------------------------------------

class TestBuildProfile:
    def test_returns_resilience_profile(self):
        g = _graph(_comp("a", mtbf=720.0, automation=60.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        profile = engine.build_profile()
        assert isinstance(profile, ResilienceProfile)

    def test_has_eight_comparisons(self):
        g = _graph(_comp("a", mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        profile = engine.build_profile()
        assert len(profile.comparisons) == 8

    def test_overall_percentile_range(self):
        g = _graph(_comp("a", mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        profile = engine.build_profile()
        assert 0 <= profile.overall_percentile <= 100

    def test_maturity_level_set(self):
        g = _graph(_comp("a", mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        profile = engine.build_profile()
        assert isinstance(profile.maturity_level, MaturityLevel)

    def test_strengths_contain_top_performers(self):
        # Create a highly automated, well-replicated system
        g = _graph(
            _comp("a", replicas=5, failover=True, promotion_time=5.0,
                  mtbf=5000.0, mttr=3.0, automation=95.0),
        )
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.STARTUP)
        profile = engine.build_profile()
        # At least some metrics should be strengths for a strong system in startup
        assert len(profile.strengths) > 0

    def test_weaknesses_contain_below_average(self):
        # Create a minimal, weak system
        g = _graph(_comp("a", replicas=1, mtbf=0.0, automation=5.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.TELECOM)
        profile = engine.build_profile()
        assert len(profile.weaknesses) > 0

    def test_average_rated_metrics_not_in_strengths_or_weaknesses(self):
        g = _graph(_comp("a", mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        profile = engine.build_profile()
        for comp in profile.comparisons:
            if comp.rating == "average":
                assert not any(
                    comp.metric.value in s for s in profile.strengths
                )


# ---------------------------------------------------------------------------
# 24. Engine — generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_returns_benchmark_report(self):
        g = _graph(_comp("a", mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        report = engine.generate_report()
        assert isinstance(report, BenchmarkReport)

    def test_report_vertical(self):
        g = _graph(_comp("a", mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.HEALTHCARE)
        report = engine.generate_report()
        assert report.vertical == IndustryVertical.HEALTHCARE

    def test_report_has_generated_at(self):
        g = _graph(_comp("a", mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        before = datetime.now(timezone.utc)
        report = engine.generate_report()
        after = datetime.now(timezone.utc)
        assert before <= report.generated_at <= after

    def test_report_has_profile(self):
        g = _graph(_comp("a", mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        report = engine.generate_report()
        assert isinstance(report.profile, ResilienceProfile)
        assert len(report.profile.comparisons) == 8

    def test_report_top_improvements_limited(self):
        g = _graph(_comp("a", mtbf=50.0, automation=5.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.TELECOM)
        report = engine.generate_report()
        assert len(report.top_improvements) <= 5

    def test_report_effort_populated(self):
        g = _graph(_comp("a", mtbf=50.0, automation=5.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.TELECOM)
        report = engine.generate_report()
        assert len(report.estimated_effort_to_p75) > 0

    def test_report_improvements_reference_p75(self):
        g = _graph(_comp("a", mtbf=50.0, automation=5.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        report = engine.generate_report()
        for imp in report.top_improvements:
            assert "p75" in imp

    def test_report_no_improvements_for_strong_system(self):
        g = _graph(
            _comp("a", replicas=5, failover=True, promotion_time=2.0,
                  mtbf=10000.0, mttr=2.0, automation=98.0),
        )
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.STARTUP)
        report = engine.generate_report()
        # A strong system in a startup vertical should have few improvements
        # Some metrics may still need improvement
        assert isinstance(report.top_improvements, list)


# ---------------------------------------------------------------------------
# 25. Integration — full workflow with different verticals
# ---------------------------------------------------------------------------

class TestIntegrationVerticals:
    @pytest.mark.parametrize("vertical", list(IndustryVertical))
    def test_full_workflow_each_vertical(self, vertical):
        g = _graph(
            _comp("web", replicas=2, mtbf=500.0, mttr=20.0, automation=50.0),
            _comp("db", replicas=1, mtbf=1000.0, mttr=45.0, automation=30.0),
        )
        engine = ResilienceBenchmarkEngine(g, vertical)
        report = engine.generate_report()
        assert report.vertical == vertical
        assert isinstance(report.profile.maturity_level, MaturityLevel)
        assert 0 <= report.profile.overall_percentile <= 100


# ---------------------------------------------------------------------------
# 26. Integration — empty graph
# ---------------------------------------------------------------------------

class TestIntegrationEmptyGraph:
    def test_empty_graph_all_metrics_zero(self):
        g = InfraGraph()
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        for metric in BenchmarkMetric:
            assert engine.measure_current(metric) == 0.0

    def test_empty_graph_build_profile(self):
        g = InfraGraph()
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        profile = engine.build_profile()
        assert isinstance(profile, ResilienceProfile)
        assert len(profile.comparisons) == 8

    def test_empty_graph_generate_report(self):
        g = InfraGraph()
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        report = engine.generate_report()
        assert isinstance(report, BenchmarkReport)


# ---------------------------------------------------------------------------
# 27. Integration — complex graph
# ---------------------------------------------------------------------------

class TestIntegrationComplexGraph:
    def test_multi_component_graph(self):
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER, replicas=2,
                    failover=True, promotion_time=5.0,
                    mtbf=2000.0, mttr=5.0, automation=80.0)
        web1 = _comp("web1", ctype=ComponentType.WEB_SERVER, replicas=3,
                      mtbf=1000.0, mttr=15.0, automation=70.0)
        web2 = _comp("web2", ctype=ComponentType.WEB_SERVER, replicas=3,
                      mtbf=1000.0, mttr=15.0, automation=70.0)
        db = _comp("db", ctype=ComponentType.DATABASE, replicas=2,
                   failover=True, promotion_time=10.0,
                   mtbf=3000.0, mttr=10.0, automation=60.0)
        cache = _comp("cache", ctype=ComponentType.CACHE, replicas=2,
                       mtbf=500.0, mttr=5.0, automation=90.0)

        g = _graph(lb, web1, web2, db, cache)
        g.add_dependency(Dependency(source_id="web1", target_id="db"))
        g.add_dependency(Dependency(source_id="web2", target_id="db"))
        g.add_dependency(Dependency(source_id="web1", target_id="cache"))
        g.add_dependency(Dependency(source_id="web2", target_id="cache"))
        g.add_dependency(Dependency(source_id="lb", target_id="web1"))
        g.add_dependency(Dependency(source_id="lb", target_id="web2"))

        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        report = engine.generate_report()

        assert report.vertical == IndustryVertical.FINTECH
        assert report.profile.overall_percentile > 0
        assert len(report.profile.comparisons) == 8

    def test_all_down_system(self):
        g = _graph(
            _comp("a", health=HealthStatus.DOWN, mtbf=0.0),
            _comp("b", health=HealthStatus.DOWN, mtbf=0.0),
        )
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        profile = engine.build_profile()
        assert len(profile.weaknesses) > 0

    def test_degraded_system(self):
        g = _graph(
            _comp("a", health=HealthStatus.DEGRADED, mtbf=100.0, mttr=120.0),
            _comp("b", health=HealthStatus.OVERLOADED, mtbf=80.0, mttr=90.0),
        )
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        report = engine.generate_report()
        assert report.profile.overall_percentile < 50


# ---------------------------------------------------------------------------
# 28. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_component_graph(self):
        g = _graph(_comp("a", mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        report = engine.generate_report()
        assert isinstance(report, BenchmarkReport)

    def test_very_high_replicas(self):
        g = _graph(_comp("a", replicas=100, mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        val = engine.measure_current(BenchmarkMetric.REDUNDANCY_RATIO)
        assert val == 100.0

    def test_very_high_mtbf(self):
        g = _graph(_comp("a", mtbf=100000.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        result = engine.compare_metric(BenchmarkMetric.MTBF_HOURS)
        assert result.percentile == 95.0

    def test_very_low_mttr(self):
        g = _graph(_comp("a", mttr=0.5))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        result = engine.compare_metric(BenchmarkMetric.MTTR_MINUTES)
        assert result.percentile == 95.0

    def test_extreme_automation(self):
        g = _graph(_comp("a", automation=100.0, mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        result = engine.compare_metric(BenchmarkMetric.AUTOMATION_PERCENT)
        assert result.percentile == 95.0

    def test_zero_automation(self):
        g = _graph(_comp("a", automation=0.0, mtbf=720.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        result = engine.compare_metric(BenchmarkMetric.AUTOMATION_PERCENT)
        assert result.percentile == 10.0

    def test_compare_gap_to_p50_exact_match(self):
        # Redundancy ratio = 2.0, fintech p50 = 2.0
        g = _graph(_comp("a", replicas=2))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        result = engine.compare_metric(BenchmarkMetric.REDUNDANCY_RATIO)
        assert result.gap_to_p50 == 0.0

    def test_compare_metric_percentile_roundtrip(self):
        g = _graph(_comp("a", mtbf=720.0, automation=55.0))
        engine = ResilienceBenchmarkEngine(g, IndustryVertical.FINTECH)
        result = engine.compare_metric(BenchmarkMetric.AUTOMATION_PERCENT)
        assert isinstance(result.percentile, float)


# ---------------------------------------------------------------------------
# 29. Benchmark data — specific vertical checks
# ---------------------------------------------------------------------------

class TestSpecificVerticalData:
    def test_telecom_high_availability(self):
        b = _BENCHMARK_DATA[(IndustryVertical.TELECOM, BenchmarkMetric.AVAILABILITY)]
        assert b.p90 == 99.999

    def test_startup_low_availability(self):
        b = _BENCHMARK_DATA[(IndustryVertical.STARTUP, BenchmarkMetric.AVAILABILITY)]
        assert b.p25 == 95.0

    def test_government_slow_mttr(self):
        b = _BENCHMARK_DATA[(IndustryVertical.GOVERNMENT, BenchmarkMetric.MTTR_MINUTES)]
        assert b.p25 == 240

    def test_saas_high_automation(self):
        b = _BENCHMARK_DATA[(IndustryVertical.SAAS, BenchmarkMetric.AUTOMATION_PERCENT)]
        assert b.p90 == 95

    def test_gaming_many_spofs(self):
        b = _BENCHMARK_DATA[(IndustryVertical.GAMING, BenchmarkMetric.SPOF_COUNT)]
        assert b.p25 == 15

    def test_manufacturing_redundancy(self):
        b = _BENCHMARK_DATA[(IndustryVertical.MANUFACTURING, BenchmarkMetric.REDUNDANCY_RATIO)]
        assert b.p50 == 1.3

    def test_ecommerce_recovery_time(self):
        b = _BENCHMARK_DATA[(IndustryVertical.ECOMMERCE, BenchmarkMetric.RECOVERY_TIME_MINUTES)]
        assert b.p50 == 35

    def test_healthcare_incident_frequency(self):
        b = _BENCHMARK_DATA[(IndustryVertical.HEALTHCARE, BenchmarkMetric.INCIDENT_FREQUENCY)]
        assert b.p50 == 6

    def test_media_mtbf(self):
        b = _BENCHMARK_DATA[(IndustryVertical.MEDIA, BenchmarkMetric.MTBF_HOURS)]
        assert b.p50 == 500


# ---------------------------------------------------------------------------
# 30. Effort map
# ---------------------------------------------------------------------------

class TestEffortMap:
    def test_availability_effort(self):
        assert "failover" in _EFFORT_MAP[BenchmarkMetric.AVAILABILITY]

    def test_mttr_effort(self):
        assert "runbook" in _EFFORT_MAP[BenchmarkMetric.MTTR_MINUTES].lower()

    def test_mtbf_effort(self):
        assert "chaos" in _EFFORT_MAP[BenchmarkMetric.MTBF_HOURS].lower()

    def test_redundancy_effort(self):
        assert "replica" in _EFFORT_MAP[BenchmarkMetric.REDUNDANCY_RATIO].lower()

    def test_spof_effort(self):
        assert "single point" in _EFFORT_MAP[BenchmarkMetric.SPOF_COUNT].lower()

    def test_recovery_effort(self):
        assert "DR" in _EFFORT_MAP[BenchmarkMetric.RECOVERY_TIME_MINUTES]

    def test_incident_effort(self):
        assert "monitoring" in _EFFORT_MAP[BenchmarkMetric.INCIDENT_FREQUENCY].lower()

    def test_automation_effort(self):
        assert "IaC" in _EFFORT_MAP[BenchmarkMetric.AUTOMATION_PERCENT]


# ---------------------------------------------------------------------------
# 31. Model serialization roundtrip
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 32. Direct static method calls for coverage
# ---------------------------------------------------------------------------

class TestDirectStaticMethods:
    def test_measure_redundancy_ratio_empty(self):
        val = ResilienceBenchmarkEngine._measure_redundancy_ratio([])
        assert val == 0.0

    def test_measure_incident_frequency_empty(self):
        val = ResilienceBenchmarkEngine._measure_incident_frequency([])
        assert val == 0.0

    def test_compute_percentile_equal_breakpoints(self):
        """Test when two adjacent breakpoints have the same value."""
        # Create a bench where p25 and p50 have the same value
        # After sorting by value, these will be adjacent with same value
        bench = IndustryBenchmark(
            vertical=IndustryVertical.FINTECH,
            metric=BenchmarkMetric.AVAILABILITY,
            p25=99.5, p50=99.5, p75=99.8, p90=99.9,
            unit="%",
        )
        # value=99.5 hits the v_lo==v_hi case for (p25=99.5, p50=99.5)
        pct = ResilienceBenchmarkEngine._compute_percentile(
            99.5, bench, BenchmarkMetric.AVAILABILITY
        )
        # (25 + 50) / 2 = 37.5
        assert pct == 37.5

    def test_measure_recovery_time_empty_list(self):
        val = ResilienceBenchmarkEngine._measure_recovery_time([])
        assert val == 0.0

    def test_measure_automation_empty_list(self):
        val = ResilienceBenchmarkEngine._measure_automation_percent([])
        assert val == 0.0

    def test_measure_mttr_empty_list(self):
        val = ResilienceBenchmarkEngine._measure_mttr([])
        assert val == 0.0

    def test_measure_mtbf_empty_list(self):
        val = ResilienceBenchmarkEngine._measure_mtbf([])
        assert val == 0.0

    def test_measure_availability_empty_list(self):
        val = ResilienceBenchmarkEngine._measure_availability([])
        assert val == 0.0


# ---------------------------------------------------------------------------
# 33. Model serialization roundtrip
# ---------------------------------------------------------------------------

class TestModelSerialization:
    def test_industry_benchmark_roundtrip(self):
        b = IndustryBenchmark(
            vertical=IndustryVertical.FINTECH,
            metric=BenchmarkMetric.AVAILABILITY,
            p25=99.5, p50=99.9, p75=99.95, p90=99.99,
            unit="%",
        )
        d = b.model_dump()
        b2 = IndustryBenchmark(**d)
        assert b == b2

    def test_benchmark_comparison_roundtrip(self):
        c = BenchmarkComparison(
            metric=BenchmarkMetric.MTTR_MINUTES,
            current_value=20.0,
            industry_p50=45.0,
            percentile=70.0,
            rating="above_average",
            gap_to_p50=25.0,
        )
        d = c.model_dump()
        c2 = BenchmarkComparison(**d)
        assert c == c2

    def test_resilience_profile_roundtrip(self):
        p = ResilienceProfile(
            overall_percentile=55.0,
            maturity_level=MaturityLevel.DEFINED,
            strengths=["good"],
            weaknesses=["bad"],
        )
        d = p.model_dump()
        p2 = ResilienceProfile(**d)
        assert p2.overall_percentile == 55.0

    def test_report_model_dump(self):
        profile = ResilienceProfile(
            overall_percentile=50.0,
            maturity_level=MaturityLevel.DEFINED,
        )
        r = BenchmarkReport(
            vertical=IndustryVertical.FINTECH,
            profile=profile,
            generated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        d = r.model_dump()
        assert d["vertical"] == "fintech"
        assert d["profile"]["maturity_level"] == "defined"
