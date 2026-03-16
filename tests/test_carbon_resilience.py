"""Tests for carbon-aware resilience engine."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.carbon_resilience import (
    DEFAULT_CARBON_INTENSITY,
    CarbonFootprint,
    CarbonIntensityRegion,
    CarbonOptimization,
    CarbonProfile,
    CarbonResilienceEngine,
    CarbonResilienceReport,
    PowerSource,
    ResilienceCarbonTradeoff,
    _HOURS_PER_YEAR,
    _W_TO_KW,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas, health=health)
    if failover:
        c.failover.enabled = True
    return c


def _graph(*components: Component) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


def _profile(
    cid: str = "api",
    watts: float = 200.0,
    region: CarbonIntensityRegion = CarbonIntensityRegion.US_EAST,
    power: PowerSource = PowerSource.GRID_AVERAGE,
    pue: float = 1.2,
    intensity: float | None = None,
) -> CarbonProfile:
    return CarbonProfile(
        component_id=cid,
        power_consumption_watts=watts,
        carbon_intensity_gco2_per_kwh=intensity
        if intensity is not None
        else DEFAULT_CARBON_INTENSITY[region],
        region=region,
        power_source=power,
        pue=pue,
    )


def _simple_graph_and_profile():
    """Return a (graph, profile) tuple for common tests."""
    g = _graph(_comp("api", "API", replicas=2))
    p = _profile("api")
    return g, p


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestPowerSourceEnum:
    def test_values(self):
        assert PowerSource.GRID_AVERAGE.value == "grid_average"
        assert PowerSource.RENEWABLE.value == "renewable"
        assert PowerSource.FOSSIL.value == "fossil"
        assert PowerSource.NUCLEAR.value == "nuclear"
        assert PowerSource.MIXED.value == "mixed"

    def test_count(self):
        assert len(PowerSource) == 5

    def test_string_member(self):
        assert isinstance(PowerSource.RENEWABLE, str)

    def test_lookup(self):
        assert PowerSource("renewable") == PowerSource.RENEWABLE


class TestCarbonIntensityRegionEnum:
    def test_values(self):
        assert CarbonIntensityRegion.US_EAST.value == "us_east"
        assert CarbonIntensityRegion.US_WEST.value == "us_west"
        assert CarbonIntensityRegion.EU_WEST.value == "eu_west"
        assert CarbonIntensityRegion.EU_NORTH.value == "eu_north"
        assert CarbonIntensityRegion.ASIA_EAST.value == "asia_east"
        assert CarbonIntensityRegion.ASIA_SOUTH.value == "asia_south"

    def test_count(self):
        assert len(CarbonIntensityRegion) == 6

    def test_string_member(self):
        assert isinstance(CarbonIntensityRegion.US_EAST, str)

    def test_lookup(self):
        assert CarbonIntensityRegion("eu_north") == CarbonIntensityRegion.EU_NORTH


# ---------------------------------------------------------------------------
# Tests: Default carbon intensities
# ---------------------------------------------------------------------------


class TestDefaultCarbonIntensity:
    def test_us_east(self):
        assert DEFAULT_CARBON_INTENSITY[CarbonIntensityRegion.US_EAST] == 386.0

    def test_us_west(self):
        assert DEFAULT_CARBON_INTENSITY[CarbonIntensityRegion.US_WEST] == 210.0

    def test_eu_west(self):
        assert DEFAULT_CARBON_INTENSITY[CarbonIntensityRegion.EU_WEST] == 275.0

    def test_eu_north(self):
        assert DEFAULT_CARBON_INTENSITY[CarbonIntensityRegion.EU_NORTH] == 30.0

    def test_asia_east(self):
        assert DEFAULT_CARBON_INTENSITY[CarbonIntensityRegion.ASIA_EAST] == 550.0

    def test_asia_south(self):
        assert DEFAULT_CARBON_INTENSITY[CarbonIntensityRegion.ASIA_SOUTH] == 710.0

    def test_all_regions_present(self):
        for region in CarbonIntensityRegion:
            assert region in DEFAULT_CARBON_INTENSITY


# ---------------------------------------------------------------------------
# Tests: CarbonProfile model
# ---------------------------------------------------------------------------


class TestCarbonProfile:
    def test_basic(self):
        p = _profile("db", watts=300.0)
        assert p.component_id == "db"
        assert p.power_consumption_watts == 300.0

    def test_default_pue(self):
        p = CarbonProfile(
            component_id="x",
            power_consumption_watts=100.0,
            carbon_intensity_gco2_per_kwh=386.0,
            region=CarbonIntensityRegion.US_EAST,
            power_source=PowerSource.GRID_AVERAGE,
        )
        assert p.pue == 1.2

    def test_custom_pue(self):
        p = _profile("x", pue=1.5)
        assert p.pue == 1.5

    def test_region_stored(self):
        p = _profile("x", region=CarbonIntensityRegion.EU_NORTH)
        assert p.region == CarbonIntensityRegion.EU_NORTH

    def test_power_source_stored(self):
        p = _profile("x", power=PowerSource.RENEWABLE)
        assert p.power_source == PowerSource.RENEWABLE

    def test_intensity_stored(self):
        p = _profile("x", intensity=999.0)
        assert p.carbon_intensity_gco2_per_kwh == 999.0


# ---------------------------------------------------------------------------
# Tests: CarbonFootprint model
# ---------------------------------------------------------------------------


class TestCarbonFootprintModel:
    def test_fields(self):
        fp = CarbonFootprint(
            component_id="a",
            annual_kwh=100.0,
            annual_co2_kg=50.0,
            per_replica_co2_kg=25.0,
            total_with_replicas_co2_kg=50.0,
        )
        assert fp.component_id == "a"
        assert fp.annual_kwh == 100.0
        assert fp.annual_co2_kg == 50.0
        assert fp.per_replica_co2_kg == 25.0
        assert fp.total_with_replicas_co2_kg == 50.0


# ---------------------------------------------------------------------------
# Tests: ResilienceCarbonTradeoff model
# ---------------------------------------------------------------------------


class TestResilienceCarbonTradeoffModel:
    def test_fields(self):
        t = ResilienceCarbonTradeoff(
            change_description="add replica",
            resilience_improvement=10.0,
            carbon_increase_percent=12.0,
            carbon_increase_kg=5.0,
            efficiency_ratio=0.83,
        )
        assert t.change_description == "add replica"
        assert t.resilience_improvement == 10.0
        assert t.carbon_increase_percent == 12.0
        assert t.carbon_increase_kg == 5.0
        assert t.efficiency_ratio == 0.83


# ---------------------------------------------------------------------------
# Tests: CarbonOptimization model
# ---------------------------------------------------------------------------


class TestCarbonOptimizationModel:
    def test_fields(self):
        o = CarbonOptimization(
            recommendation="use renewable",
            current_co2_kg=100.0,
            optimized_co2_kg=10.0,
            savings_percent=90.0,
            resilience_impact="none",
        )
        assert o.recommendation == "use renewable"
        assert o.savings_percent == 90.0


# ---------------------------------------------------------------------------
# Tests: CarbonResilienceReport model
# ---------------------------------------------------------------------------


class TestCarbonResilienceReportModel:
    def test_fields(self):
        r = CarbonResilienceReport(
            total_annual_co2_kg=500.0,
            co2_per_component=[],
            tradeoffs=[],
            optimizations=[],
            esg_summary="summary",
            carbon_efficiency_score=75.0,
        )
        assert r.total_annual_co2_kg == 500.0
        assert r.esg_summary == "summary"
        assert r.carbon_efficiency_score == 75.0

    def test_score_clamped_at_100(self):
        """Score field should reject values > 100."""
        with pytest.raises(Exception):
            CarbonResilienceReport(
                total_annual_co2_kg=0,
                co2_per_component=[],
                tradeoffs=[],
                optimizations=[],
                esg_summary="",
                carbon_efficiency_score=101.0,
            )

    def test_score_clamped_at_zero(self):
        """Score field should reject values < 0."""
        with pytest.raises(Exception):
            CarbonResilienceReport(
                total_annual_co2_kg=0,
                co2_per_component=[],
                tradeoffs=[],
                optimizations=[],
                esg_summary="",
                carbon_efficiency_score=-1.0,
            )


# ---------------------------------------------------------------------------
# Tests: Engine construction
# ---------------------------------------------------------------------------


class TestEngineInit:
    def test_creates_with_graph(self):
        g = _graph()
        engine = CarbonResilienceEngine(g)
        assert engine.graph is g

    def test_default_intensities_loaded(self):
        engine = CarbonResilienceEngine(_graph())
        assert engine.carbon_intensities == DEFAULT_CARBON_INTENSITY

    def test_intensities_are_independent_copy(self):
        engine = CarbonResilienceEngine(_graph())
        engine.carbon_intensities[CarbonIntensityRegion.US_EAST] = 0.0
        assert DEFAULT_CARBON_INTENSITY[CarbonIntensityRegion.US_EAST] == 386.0


# ---------------------------------------------------------------------------
# Tests: calculate_footprint
# ---------------------------------------------------------------------------


class TestCalculateFootprint:
    def test_single_replica(self):
        g = _graph(_comp("api", "API", replicas=1))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=200.0, pue=1.2)
        fp = engine.calculate_footprint("api", p)

        expected_kwh = 200.0 / 1000.0 * _HOURS_PER_YEAR * 1.2
        expected_co2 = expected_kwh * 386.0 / 1000.0

        assert fp.component_id == "api"
        assert fp.annual_kwh == pytest.approx(expected_kwh, rel=1e-6)
        assert fp.annual_co2_kg == pytest.approx(expected_co2, rel=1e-6)
        assert fp.per_replica_co2_kg == pytest.approx(expected_co2, rel=1e-6)
        assert fp.total_with_replicas_co2_kg == pytest.approx(expected_co2, rel=1e-6)

    def test_multiple_replicas(self):
        g = _graph(_comp("api", "API", replicas=3))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=200.0)
        fp = engine.calculate_footprint("api", p)

        per_replica_kwh = 200.0 / 1000.0 * _HOURS_PER_YEAR * 1.2
        per_replica_co2 = per_replica_kwh * 386.0 / 1000.0

        assert fp.annual_kwh == pytest.approx(per_replica_kwh * 3, rel=1e-6)
        assert fp.per_replica_co2_kg == pytest.approx(per_replica_co2, rel=1e-6)
        assert fp.total_with_replicas_co2_kg == pytest.approx(
            per_replica_co2 * 3, rel=1e-6,
        )

    def test_component_not_in_graph_defaults_to_1_replica(self):
        g = _graph()  # empty graph
        engine = CarbonResilienceEngine(g)
        p = _profile("missing", watts=100.0)
        fp = engine.calculate_footprint("missing", p)
        # Should treat as 1 replica
        assert fp.total_with_replicas_co2_kg == fp.per_replica_co2_kg

    def test_eu_north_low_carbon(self):
        g = _graph(_comp("api", "API", replicas=1))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=200.0, region=CarbonIntensityRegion.EU_NORTH)
        fp = engine.calculate_footprint("api", p)
        # EU_NORTH has 30 gCO2/kWh vs US_EAST 386 — much lower CO2
        p2 = _profile("api", watts=200.0, region=CarbonIntensityRegion.US_EAST)
        fp2 = engine.calculate_footprint("api", p2)
        assert fp.total_with_replicas_co2_kg < fp2.total_with_replicas_co2_kg

    def test_higher_watts_higher_co2(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        fp_low = engine.calculate_footprint("api", _profile("api", watts=100.0))
        fp_high = engine.calculate_footprint("api", _profile("api", watts=400.0))
        assert fp_high.total_with_replicas_co2_kg > fp_low.total_with_replicas_co2_kg

    def test_higher_pue_higher_co2(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        fp_low = engine.calculate_footprint("api", _profile("api", pue=1.0))
        fp_high = engine.calculate_footprint("api", _profile("api", pue=1.8))
        assert fp_high.total_with_replicas_co2_kg > fp_low.total_with_replicas_co2_kg

    def test_zero_watts_zero_co2(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        fp = engine.calculate_footprint("api", _profile("api", watts=0.0))
        assert fp.total_with_replicas_co2_kg == 0.0
        assert fp.annual_kwh == 0.0

    def test_custom_intensity(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=200.0, intensity=1000.0)
        fp = engine.calculate_footprint("api", p)
        expected_kwh = 200.0 / 1000.0 * _HOURS_PER_YEAR * 1.2
        expected_co2 = expected_kwh * 1000.0 / 1000.0
        assert fp.annual_co2_kg == pytest.approx(expected_co2, rel=1e-6)


# ---------------------------------------------------------------------------
# Tests: analyze_tradeoff
# ---------------------------------------------------------------------------


class TestAnalyzeTradeoff:
    def test_adding_replica(self):
        g, p = _simple_graph_and_profile()
        engine = CarbonResilienceEngine(g)
        t = engine.analyze_tradeoff(
            "add replica", before_replicas=2, after_replicas=3,
            profile=p, resilience_delta=15.0,
        )
        assert t.change_description == "add replica"
        assert t.resilience_improvement == 15.0
        assert t.carbon_increase_percent == pytest.approx(50.0, rel=1e-6)
        assert t.carbon_increase_kg > 0.0
        assert t.efficiency_ratio > 0.0

    def test_removing_replica(self):
        g, p = _simple_graph_and_profile()
        engine = CarbonResilienceEngine(g)
        t = engine.analyze_tradeoff(
            "remove replica", before_replicas=3, after_replicas=2,
            profile=p, resilience_delta=-10.0,
        )
        assert t.carbon_increase_percent < 0.0
        assert t.carbon_increase_kg < 0.0

    def test_no_change_in_replicas(self):
        g, p = _simple_graph_and_profile()
        engine = CarbonResilienceEngine(g)
        t = engine.analyze_tradeoff(
            "no change", before_replicas=2, after_replicas=2,
            profile=p, resilience_delta=0.0,
        )
        assert t.carbon_increase_percent == 0.0
        assert t.carbon_increase_kg == 0.0
        assert t.efficiency_ratio == 0.0

    def test_zero_before_replicas(self):
        g, p = _simple_graph_and_profile()
        engine = CarbonResilienceEngine(g)
        t = engine.analyze_tradeoff(
            "from zero", before_replicas=0, after_replicas=2,
            profile=p, resilience_delta=50.0,
        )
        # before_co2 is 0 → carbon_increase_percent should be 0.0
        assert t.carbon_increase_percent == 0.0
        assert t.carbon_increase_kg > 0.0

    def test_efficiency_ratio_sign(self):
        g, p = _simple_graph_and_profile()
        engine = CarbonResilienceEngine(g)
        t = engine.analyze_tradeoff(
            "scale up", before_replicas=1, after_replicas=2,
            profile=p, resilience_delta=20.0,
        )
        # positive resilience and positive carbon → positive efficiency
        assert t.efficiency_ratio > 0.0

    def test_double_replicas(self):
        g, p = _simple_graph_and_profile()
        engine = CarbonResilienceEngine(g)
        t = engine.analyze_tradeoff(
            "double", before_replicas=2, after_replicas=4,
            profile=p, resilience_delta=25.0,
        )
        assert t.carbon_increase_percent == pytest.approx(100.0, rel=1e-6)

    def test_different_regions_give_different_co2(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p_east = _profile("api", region=CarbonIntensityRegion.US_EAST)
        p_north = _profile("api", region=CarbonIntensityRegion.EU_NORTH)
        t_east = engine.analyze_tradeoff("x", 1, 2, p_east, 10.0)
        t_north = engine.analyze_tradeoff("x", 1, 2, p_north, 10.0)
        assert t_east.carbon_increase_kg > t_north.carbon_increase_kg


# ---------------------------------------------------------------------------
# Tests: suggest_optimizations
# ---------------------------------------------------------------------------


class TestSuggestOptimizations:
    def test_non_eu_north_gets_region_migration(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", region=CarbonIntensityRegion.US_EAST)
        opts = engine.suggest_optimizations([p])
        migration_opts = [o for o in opts if "EU_NORTH" in o.recommendation]
        assert len(migration_opts) == 1
        assert migration_opts[0].savings_percent > 0.0

    def test_eu_north_no_region_migration(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", region=CarbonIntensityRegion.EU_NORTH)
        opts = engine.suggest_optimizations([p])
        migration_opts = [o for o in opts if "EU_NORTH" in o.recommendation]
        assert len(migration_opts) == 0

    def test_non_renewable_gets_power_recommendation(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", power=PowerSource.FOSSIL)
        opts = engine.suggest_optimizations([p])
        power_opts = [o for o in opts if "renewable" in o.recommendation]
        assert len(power_opts) == 1
        assert power_opts[0].savings_percent == pytest.approx(90.0, rel=1e-6)

    def test_renewable_no_power_recommendation(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", power=PowerSource.RENEWABLE)
        opts = engine.suggest_optimizations([p])
        power_opts = [o for o in opts if "renewable" in o.recommendation]
        assert len(power_opts) == 0

    def test_high_pue_gets_pue_recommendation(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", pue=1.5)
        opts = engine.suggest_optimizations([p])
        pue_opts = [o for o in opts if "PUE" in o.recommendation]
        assert len(pue_opts) == 1
        assert pue_opts[0].savings_percent > 0.0

    def test_low_pue_no_pue_recommendation(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", pue=1.05)
        opts = engine.suggest_optimizations([p])
        pue_opts = [o for o in opts if "PUE" in o.recommendation]
        assert len(pue_opts) == 0

    def test_exact_threshold_pue_1_1(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", pue=1.1)
        opts = engine.suggest_optimizations([p])
        pue_opts = [o for o in opts if "PUE" in o.recommendation]
        # pue > 1.1 is the condition; pue==1.1 should NOT trigger
        assert len(pue_opts) == 0

    def test_multiple_profiles(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        engine = CarbonResilienceEngine(g)
        opts = engine.suggest_optimizations([
            _profile("a", region=CarbonIntensityRegion.ASIA_SOUTH, pue=1.5),
            _profile("b", region=CarbonIntensityRegion.ASIA_EAST, pue=1.3),
        ])
        # Each should get region migration + power + PUE = 3 each = 6 total
        assert len(opts) == 6

    def test_empty_profiles(self):
        g = _graph()
        engine = CarbonResilienceEngine(g)
        opts = engine.suggest_optimizations([])
        assert opts == []

    def test_optimized_co2_less_than_current(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", region=CarbonIntensityRegion.ASIA_SOUTH, pue=1.5)
        opts = engine.suggest_optimizations([p])
        for o in opts:
            assert o.optimized_co2_kg <= o.current_co2_kg

    def test_savings_percent_positive(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", region=CarbonIntensityRegion.ASIA_SOUTH, pue=1.5)
        opts = engine.suggest_optimizations([p])
        for o in opts:
            assert o.savings_percent >= 0.0

    def test_resilience_impact_string(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api")
        opts = engine.suggest_optimizations([p])
        for o in opts:
            assert isinstance(o.resilience_impact, str)
            assert len(o.resilience_impact) > 0


# ---------------------------------------------------------------------------
# Tests: calculate_total_footprint
# ---------------------------------------------------------------------------


class TestCalculateTotalFootprint:
    def test_single_profile(self):
        g = _graph(_comp("api", "API", replicas=1))
        engine = CarbonResilienceEngine(g)
        p = _profile("api")
        total = engine.calculate_total_footprint([p])
        fp = engine.calculate_footprint("api", p)
        assert total == pytest.approx(fp.total_with_replicas_co2_kg, rel=1e-6)

    def test_multiple_profiles(self):
        g = _graph(_comp("a", "A", replicas=2), _comp("b", "B", replicas=1))
        engine = CarbonResilienceEngine(g)
        p_a = _profile("a", watts=200.0)
        p_b = _profile("b", watts=100.0)
        total = engine.calculate_total_footprint([p_a, p_b])
        fp_a = engine.calculate_footprint("a", p_a)
        fp_b = engine.calculate_footprint("b", p_b)
        expected = fp_a.total_with_replicas_co2_kg + fp_b.total_with_replicas_co2_kg
        assert total == pytest.approx(expected, rel=1e-6)

    def test_empty_profiles(self):
        g = _graph()
        engine = CarbonResilienceEngine(g)
        assert engine.calculate_total_footprint([]) == 0.0

    def test_zero_watts_all(self):
        g = _graph(_comp("a", "A"))
        engine = CarbonResilienceEngine(g)
        p = _profile("a", watts=0.0)
        assert engine.calculate_total_footprint([p]) == 0.0

    def test_total_scales_with_replicas(self):
        g1 = _graph(_comp("api", "API", replicas=1))
        g3 = _graph(_comp("api", "API", replicas=3))
        e1 = CarbonResilienceEngine(g1)
        e3 = CarbonResilienceEngine(g3)
        p = _profile("api")
        t1 = e1.calculate_total_footprint([p])
        t3 = e3.calculate_total_footprint([p])
        assert t3 == pytest.approx(t1 * 3, rel=1e-6)


# ---------------------------------------------------------------------------
# Tests: generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_report_type(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("api")])
        assert isinstance(r, CarbonResilienceReport)

    def test_total_matches_footprints(self):
        g = _graph(_comp("a", "A", replicas=2), _comp("b", "B"))
        engine = CarbonResilienceEngine(g)
        profiles = [_profile("a"), _profile("b", watts=100.0)]
        r = engine.generate_report(profiles)
        expected_total = sum(
            fp.total_with_replicas_co2_kg for fp in r.co2_per_component
        )
        assert r.total_annual_co2_kg == pytest.approx(expected_total, rel=1e-6)

    def test_footprints_per_component(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("a"), _profile("b")])
        ids = [fp.component_id for fp in r.co2_per_component]
        assert "a" in ids
        assert "b" in ids

    def test_tradeoffs_for_multi_replica(self):
        g = _graph(_comp("api", "API", replicas=3))
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("api")])
        assert len(r.tradeoffs) == 1
        assert r.tradeoffs[0].change_description.startswith("Remove 1 replica")

    def test_no_tradeoff_for_single_replica(self):
        g = _graph(_comp("api", "API", replicas=1))
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("api")])
        assert len(r.tradeoffs) == 0

    def test_optimizations_included(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([
            _profile("api", region=CarbonIntensityRegion.ASIA_SOUTH, pue=1.5),
        ])
        assert len(r.optimizations) > 0

    def test_esg_summary_content(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("api")])
        assert "Total annual CO2" in r.esg_summary
        assert "Carbon efficiency score" in r.esg_summary
        assert "optimization" in r.esg_summary

    def test_carbon_efficiency_score_in_range(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("api")])
        assert 0.0 <= r.carbon_efficiency_score <= 100.0

    def test_empty_profiles_report(self):
        g = _graph()
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([])
        assert r.total_annual_co2_kg == 0.0
        assert r.co2_per_component == []
        assert r.tradeoffs == []

    def test_report_with_missing_component(self):
        g = _graph()
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("missing")])
        assert len(r.co2_per_component) == 1


# ---------------------------------------------------------------------------
# Tests: _carbon_efficiency_score
# ---------------------------------------------------------------------------


class TestCarbonEfficiencyScore:
    def test_empty_profiles_returns_100(self):
        g = _graph()
        engine = CarbonResilienceEngine(g)
        assert engine._carbon_efficiency_score([]) == 100.0

    def test_eu_north_renewable_best_pue(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile(
            "api",
            region=CarbonIntensityRegion.EU_NORTH,
            power=PowerSource.RENEWABLE,
            pue=1.0,
        )
        score = engine._carbon_efficiency_score([p])
        # max possible: region=50 + power=30 + pue=20 = 100
        assert score == pytest.approx(100.0, rel=1e-6)

    def test_asia_south_fossil_high_pue(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile(
            "api",
            region=CarbonIntensityRegion.ASIA_SOUTH,
            power=PowerSource.FOSSIL,
            pue=2.0,
        )
        score = engine._carbon_efficiency_score([p])
        # region=0 + power=0 + pue=0 = 0
        assert score == pytest.approx(0.0, rel=1e-6)

    def test_nuclear_power_score(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", power=PowerSource.NUCLEAR, pue=1.0)
        score = engine._carbon_efficiency_score([p])
        # Should be higher than FOSSIL but lower than RENEWABLE
        p_fossil = _profile("api", power=PowerSource.FOSSIL, pue=1.0)
        p_renew = _profile("api", power=PowerSource.RENEWABLE, pue=1.0)
        s_fossil = engine._carbon_efficiency_score([p_fossil])
        s_renew = engine._carbon_efficiency_score([p_renew])
        assert s_fossil < score < s_renew

    def test_mixed_power_score(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", power=PowerSource.MIXED, pue=1.0)
        score = engine._carbon_efficiency_score([p])
        p_grid = _profile("api", power=PowerSource.GRID_AVERAGE, pue=1.0)
        s_grid = engine._carbon_efficiency_score([p_grid])
        assert score > s_grid

    def test_pue_2_gives_zero_pue_score(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile(
            "api",
            region=CarbonIntensityRegion.EU_NORTH,
            power=PowerSource.RENEWABLE,
            pue=2.0,
        )
        score = engine._carbon_efficiency_score([p])
        # region=50, power=30, pue=0 → 80
        assert score == pytest.approx(80.0, rel=1e-6)

    def test_pue_above_2_clamped(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile(
            "api",
            region=CarbonIntensityRegion.EU_NORTH,
            power=PowerSource.RENEWABLE,
            pue=3.0,
        )
        score = engine._carbon_efficiency_score([p])
        # pue_score = max(0, (2.0-3.0)*20) = 0
        assert score == pytest.approx(80.0, rel=1e-6)

    def test_multiple_profiles_averaged(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        engine = CarbonResilienceEngine(g)
        p_best = _profile(
            "a",
            region=CarbonIntensityRegion.EU_NORTH,
            power=PowerSource.RENEWABLE,
            pue=1.0,
        )
        p_worst = _profile(
            "b",
            region=CarbonIntensityRegion.ASIA_SOUTH,
            power=PowerSource.FOSSIL,
            pue=2.0,
        )
        score = engine._carbon_efficiency_score([p_best, p_worst])
        assert score == pytest.approx(50.0, rel=1e-6)

    def test_region_score_middle(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        # Use US_WEST (210 gCO2/kWh), midrange
        p = _profile(
            "api",
            region=CarbonIntensityRegion.US_WEST,
            power=PowerSource.FOSSIL,
            pue=2.0,
        )
        score = engine._carbon_efficiency_score([p])
        # region_score = (1 - (210-30)/(710-30))*50 = (1-180/680)*50 ≈ 36.76
        # power=0, pue=0 → ~36.76
        expected_region = (1.0 - (210.0 - 30.0) / (710.0 - 30.0)) * 50.0
        assert score == pytest.approx(expected_region, rel=1e-4)


# ---------------------------------------------------------------------------
# Tests: _single_co2_kg and _co2_with_intensity (private helpers)
# ---------------------------------------------------------------------------


class TestPrivateHelpers:
    def test_single_co2_kg(self):
        g = _graph()
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=200.0, pue=1.2)
        co2 = engine._single_co2_kg(p)
        expected_kwh = 200.0 / 1000.0 * _HOURS_PER_YEAR * 1.2
        expected = expected_kwh * 386.0 / 1000.0
        assert co2 == pytest.approx(expected, rel=1e-6)

    def test_co2_with_intensity(self):
        g = _graph()
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=200.0, pue=1.2)
        co2 = engine._co2_with_intensity(p, 30.0)
        expected_kwh = 200.0 / 1000.0 * _HOURS_PER_YEAR * 1.2
        expected = expected_kwh * 30.0 / 1000.0
        assert co2 == pytest.approx(expected, rel=1e-6)

    def test_co2_with_intensity_zero(self):
        g = _graph()
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=200.0)
        co2 = engine._co2_with_intensity(p, 0.0)
        assert co2 == 0.0

    def test_single_co2_kg_zero_watts(self):
        g = _graph()
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=0.0)
        assert engine._single_co2_kg(p) == 0.0


# ---------------------------------------------------------------------------
# Tests: Edge cases and integration
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_very_high_watts(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=100_000.0)
        fp = engine.calculate_footprint("api", p)
        assert fp.total_with_replicas_co2_kg > 0.0

    def test_very_small_watts(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=0.001)
        fp = engine.calculate_footprint("api", p)
        assert fp.total_with_replicas_co2_kg > 0.0

    def test_pue_exactly_1(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", pue=1.0)
        fp = engine.calculate_footprint("api", p)
        assert fp.total_with_replicas_co2_kg > 0.0

    def test_all_regions_different_co2(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        co2_values = set()
        for region in CarbonIntensityRegion:
            p = _profile("api", region=region)
            fp = engine.calculate_footprint("api", p)
            co2_values.add(round(fp.total_with_replicas_co2_kg, 4))
        # All 6 regions should give different CO2
        assert len(co2_values) == 6

    def test_all_power_sources_in_score(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        scores = {}
        for ps in PowerSource:
            p = _profile("api", power=ps, pue=1.0)
            scores[ps] = engine._carbon_efficiency_score([p])
        # RENEWABLE should be highest
        assert scores[PowerSource.RENEWABLE] >= scores[PowerSource.NUCLEAR]
        assert scores[PowerSource.NUCLEAR] >= scores[PowerSource.MIXED]
        assert scores[PowerSource.MIXED] >= scores[PowerSource.GRID_AVERAGE]
        assert scores[PowerSource.GRID_AVERAGE] >= scores[PowerSource.FOSSIL]

    def test_graph_with_dependencies(self):
        g = _graph(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2),
                   _comp("api", "API", replicas=3))
        g.add_dependency(Dependency(source_id="lb", target_id="api"))
        engine = CarbonResilienceEngine(g)
        profiles = [_profile("lb", watts=50.0), _profile("api", watts=200.0)]
        r = engine.generate_report(profiles)
        # Both should have tradeoffs (replicas > 1)
        assert len(r.tradeoffs) == 2
        assert len(r.co2_per_component) == 2

    def test_tradeoff_negative_resilience_delta(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        t = engine.analyze_tradeoff(
            "downgrade", before_replicas=3, after_replicas=1,
            profile=_profile("api"), resilience_delta=-30.0,
        )
        assert t.resilience_improvement == -30.0
        assert t.carbon_increase_kg < 0.0

    def test_many_components_report(self):
        comps = [_comp(f"c{i}", f"C{i}", replicas=2) for i in range(10)]
        g = _graph(*comps)
        engine = CarbonResilienceEngine(g)
        profiles = [_profile(f"c{i}") for i in range(10)]
        r = engine.generate_report(profiles)
        assert len(r.co2_per_component) == 10
        assert r.total_annual_co2_kg > 0.0

    def test_report_score_bounded(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        for region in CarbonIntensityRegion:
            for ps in PowerSource:
                r = engine.generate_report([_profile("api", region=region, power=ps)])
                assert 0.0 <= r.carbon_efficiency_score <= 100.0


# ---------------------------------------------------------------------------
# Tests: Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_hours_per_year(self):
        assert _HOURS_PER_YEAR == pytest.approx(365.25 * 24, rel=1e-6)

    def test_w_to_kw(self):
        assert _W_TO_KW == 1000.0


# ---------------------------------------------------------------------------
# Tests: Additional coverage for optimization edge cases
# ---------------------------------------------------------------------------


class TestOptimizationEdgeCases:
    def test_zero_watts_optimization_no_crash(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=0.0, pue=1.5)
        opts = engine.suggest_optimizations([p])
        # Should not crash; savings should be 0
        for o in opts:
            assert o.current_co2_kg == 0.0
            assert o.optimized_co2_kg == 0.0
            assert o.savings_percent == 0.0

    def test_already_optimal_profile(self):
        """EU_NORTH + RENEWABLE + PUE 1.05 — only PUE opt absent."""
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile(
            "api",
            region=CarbonIntensityRegion.EU_NORTH,
            power=PowerSource.RENEWABLE,
            pue=1.05,
        )
        opts = engine.suggest_optimizations([p])
        # No region migration (already EU_NORTH), no renewable (already), no PUE (<=1.1)
        assert len(opts) == 0

    def test_pue_recommendation_component_id_in_text(self):
        g = _graph(_comp("db", "Database"))
        engine = CarbonResilienceEngine(g)
        p = _profile("db", pue=1.8)
        opts = engine.suggest_optimizations([p])
        pue_opts = [o for o in opts if "PUE" in o.recommendation]
        assert "db" in pue_opts[0].recommendation

    def test_region_migration_savings_percent(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", region=CarbonIntensityRegion.ASIA_SOUTH)
        opts = engine.suggest_optimizations([p])
        migration = [o for o in opts if "EU_NORTH" in o.recommendation][0]
        # EU_NORTH(30) vs ASIA_SOUTH(710): large savings
        assert migration.savings_percent > 90.0

    def test_pue_improvement_savings_calculation(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", pue=2.0)
        opts = engine.suggest_optimizations([p])
        pue_opts = [o for o in opts if "PUE" in o.recommendation]
        assert len(pue_opts) == 1
        # Improved PUE = 1.1, so optimized = current * 1.1/2.0
        expected_savings = (1.0 - 1.1 / 2.0) * 100.0
        assert pue_opts[0].savings_percent == pytest.approx(expected_savings, rel=1e-4)


# ---------------------------------------------------------------------------
# Tests: Report tradeoff details
# ---------------------------------------------------------------------------


class TestReportTradeoffs:
    def test_tradeoff_for_2_replicas(self):
        g = _graph(_comp("api", "API", replicas=2))
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("api")])
        assert len(r.tradeoffs) == 1
        t = r.tradeoffs[0]
        assert "Remove 1 replica" in t.change_description
        assert t.resilience_improvement == -10.0
        # Removing 1 from 2 → 50% decrease
        assert t.carbon_increase_percent == pytest.approx(-50.0, rel=1e-6)

    def test_no_tradeoff_component_missing(self):
        g = _graph()  # component not in graph
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("missing")])
        # comp is None → replicas check skipped
        assert len(r.tradeoffs) == 0

    def test_tradeoff_multiple_components_mixed_replicas(self):
        g = _graph(
            _comp("a", "A", replicas=1),
            _comp("b", "B", replicas=3),
            _comp("c", "C", replicas=5),
        )
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([
            _profile("a"), _profile("b"), _profile("c"),
        ])
        # Only b(3) and c(5) have replicas>1 → 2 tradeoffs
        assert len(r.tradeoffs) == 2


# ---------------------------------------------------------------------------
# Tests: Score independence from graph structure
# ---------------------------------------------------------------------------


class TestScoreIndependence:
    def test_score_same_regardless_of_dependencies(self):
        g1 = _graph(_comp("a", "A"), _comp("b", "B"))
        g2 = _graph(_comp("a", "A"), _comp("b", "B"))
        g2.add_dependency(Dependency(source_id="a", target_id="b"))
        e1 = CarbonResilienceEngine(g1)
        e2 = CarbonResilienceEngine(g2)
        profiles = [
            _profile("a", region=CarbonIntensityRegion.US_WEST),
            _profile("b", region=CarbonIntensityRegion.EU_WEST),
        ]
        assert e1._carbon_efficiency_score(profiles) == e2._carbon_efficiency_score(profiles)

    def test_score_determined_by_profile_not_graph(self):
        g_empty = _graph()
        g_full = _graph(_comp("api", "API", replicas=5))
        e1 = CarbonResilienceEngine(g_empty)
        e2 = CarbonResilienceEngine(g_full)
        p = _profile("api")
        assert e1._carbon_efficiency_score([p]) == e2._carbon_efficiency_score([p])

    def test_equal_intensities_gives_50_region_score(self):
        """When max == min carbon intensity, region_score should be 50."""
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        # Override all intensities to the same value
        for region in CarbonIntensityRegion:
            engine.carbon_intensities[region] = 400.0
        p = _profile(
            "api",
            region=CarbonIntensityRegion.US_EAST,
            intensity=400.0,
            power=PowerSource.FOSSIL,
            pue=2.0,
        )
        score = engine._carbon_efficiency_score([p])
        # region=50, power=0, pue=0 → 50
        assert score == pytest.approx(50.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Tests: Footprint calculations (additional)
# ---------------------------------------------------------------------------


class TestFootprintAdditional:
    def test_annual_kwh_formula(self):
        g = _graph(_comp("api", "API", replicas=1))
        engine = CarbonResilienceEngine(g)
        watts = 500.0
        pue = 1.3
        p = _profile("api", watts=watts, pue=pue)
        fp = engine.calculate_footprint("api", p)
        expected = watts / _W_TO_KW * _HOURS_PER_YEAR * pue
        assert fp.annual_kwh == pytest.approx(expected, rel=1e-6)

    def test_annual_co2_equals_per_replica_for_single(self):
        g = _graph(_comp("api", "API", replicas=1))
        engine = CarbonResilienceEngine(g)
        fp = engine.calculate_footprint("api", _profile("api"))
        assert fp.annual_co2_kg == fp.per_replica_co2_kg

    def test_annual_kwh_scales_with_replicas(self):
        g = _graph(_comp("api", "API", replicas=4))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=200.0, pue=1.2)
        fp = engine.calculate_footprint("api", p)
        single_kwh = 200.0 / _W_TO_KW * _HOURS_PER_YEAR * 1.2
        assert fp.annual_kwh == pytest.approx(single_kwh * 4, rel=1e-6)

    def test_footprint_with_database_type(self):
        g = _graph(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
        engine = CarbonResilienceEngine(g)
        p = _profile("db", watts=300.0, region=CarbonIntensityRegion.EU_WEST)
        fp = engine.calculate_footprint("db", p)
        assert fp.component_id == "db"
        assert fp.total_with_replicas_co2_kg == pytest.approx(
            fp.per_replica_co2_kg * 2, rel=1e-6,
        )

    def test_footprint_asia_south_highest_co2(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        co2_by_region = {}
        for region in CarbonIntensityRegion:
            p = _profile("api", region=region, watts=200.0)
            fp = engine.calculate_footprint("api", p)
            co2_by_region[region] = fp.total_with_replicas_co2_kg
        assert co2_by_region[CarbonIntensityRegion.ASIA_SOUTH] == max(
            co2_by_region.values(),
        )

    def test_footprint_eu_north_lowest_co2(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        co2_by_region = {}
        for region in CarbonIntensityRegion:
            p = _profile("api", region=region, watts=200.0)
            fp = engine.calculate_footprint("api", p)
            co2_by_region[region] = fp.total_with_replicas_co2_kg
        assert co2_by_region[CarbonIntensityRegion.EU_NORTH] == min(
            co2_by_region.values(),
        )


# ---------------------------------------------------------------------------
# Tests: Tradeoff calculations (additional)
# ---------------------------------------------------------------------------


class TestTradeoffAdditional:
    def test_triple_replicas_increase(self):
        g, p = _simple_graph_and_profile()
        engine = CarbonResilienceEngine(g)
        t = engine.analyze_tradeoff(
            "triple", before_replicas=1, after_replicas=3,
            profile=p, resilience_delta=30.0,
        )
        assert t.carbon_increase_percent == pytest.approx(200.0, rel=1e-6)

    def test_halve_replicas(self):
        g, p = _simple_graph_and_profile()
        engine = CarbonResilienceEngine(g)
        t = engine.analyze_tradeoff(
            "halve", before_replicas=4, after_replicas=2,
            profile=p, resilience_delta=-20.0,
        )
        assert t.carbon_increase_percent == pytest.approx(-50.0, rel=1e-6)

    def test_tradeoff_carbon_increase_kg_value(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", watts=200.0, pue=1.2)
        t = engine.analyze_tradeoff(
            "add", before_replicas=1, after_replicas=2,
            profile=p, resilience_delta=10.0,
        )
        per_replica_kwh = 200.0 / _W_TO_KW * _HOURS_PER_YEAR * 1.2
        per_replica_co2 = per_replica_kwh * 386.0 / _W_TO_KW
        assert t.carbon_increase_kg == pytest.approx(per_replica_co2, rel=1e-6)

    def test_tradeoff_efficiency_calculation(self):
        g, p = _simple_graph_and_profile()
        engine = CarbonResilienceEngine(g)
        t = engine.analyze_tradeoff(
            "scale", before_replicas=1, after_replicas=2,
            profile=p, resilience_delta=20.0,
        )
        expected_eff = 20.0 / 100.0  # 20% resilience / 100% carbon increase
        assert t.efficiency_ratio == pytest.approx(expected_eff, rel=1e-6)

    def test_tradeoff_with_renewable_lower_co2(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p_grid = _profile("api", power=PowerSource.GRID_AVERAGE)
        p_renew = _profile(
            "api",
            power=PowerSource.RENEWABLE,
            region=CarbonIntensityRegion.EU_NORTH,
        )
        t_grid = engine.analyze_tradeoff("x", 1, 2, p_grid, 10.0)
        t_renew = engine.analyze_tradeoff("x", 1, 2, p_renew, 10.0)
        assert t_renew.carbon_increase_kg < t_grid.carbon_increase_kg


# ---------------------------------------------------------------------------
# Tests: Report edge cases (additional)
# ---------------------------------------------------------------------------


class TestReportAdditional:
    def test_report_esg_summary_contains_total(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("api")])
        # Verify the summary contains the numeric total
        assert str(round(r.total_annual_co2_kg, 1)) in r.esg_summary

    def test_report_esg_summary_contains_score(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("api")])
        assert str(round(r.carbon_efficiency_score, 1)) in r.esg_summary

    def test_report_optimization_count_in_summary(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("api")])
        opt_count = len(r.optimizations)
        assert str(opt_count) in r.esg_summary

    def test_report_single_component_single_replica(self):
        g = _graph(_comp("api", "API", replicas=1))
        engine = CarbonResilienceEngine(g)
        r = engine.generate_report([_profile("api")])
        assert len(r.co2_per_component) == 1
        assert len(r.tradeoffs) == 0
        assert r.total_annual_co2_kg > 0.0

    def test_report_preserves_component_order(self):
        g = _graph(
            _comp("z", "Z"), _comp("a", "A"), _comp("m", "M"),
        )
        engine = CarbonResilienceEngine(g)
        profiles = [_profile("z"), _profile("a"), _profile("m")]
        r = engine.generate_report(profiles)
        ids = [fp.component_id for fp in r.co2_per_component]
        assert ids == ["z", "a", "m"]


# ---------------------------------------------------------------------------
# Tests: Optimization renewable savings math
# ---------------------------------------------------------------------------


class TestOptimizationRenewableMath:
    def test_renewable_savings_is_90_percent(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", power=PowerSource.GRID_AVERAGE)
        opts = engine.suggest_optimizations([p])
        renew = [o for o in opts if "renewable" in o.recommendation][0]
        assert renew.savings_percent == pytest.approx(90.0, rel=1e-6)

    def test_renewable_optimized_co2_is_10_percent(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", power=PowerSource.FOSSIL, watts=200.0)
        opts = engine.suggest_optimizations([p])
        renew = [o for o in opts if "renewable" in o.recommendation][0]
        assert renew.optimized_co2_kg == pytest.approx(
            renew.current_co2_kg * 0.1, rel=1e-6,
        )

    def test_region_migration_optimized_co2_calculation(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        p = _profile("api", region=CarbonIntensityRegion.US_EAST, watts=200.0, pue=1.2)
        opts = engine.suggest_optimizations([p])
        migration = [o for o in opts if "EU_NORTH" in o.recommendation][0]
        expected = engine._co2_with_intensity(
            p, DEFAULT_CARBON_INTENSITY[CarbonIntensityRegion.EU_NORTH],
        )
        assert migration.optimized_co2_kg == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# Tests: Intensity overrides
# ---------------------------------------------------------------------------


class TestIntensityOverrides:
    def test_custom_intensity_affects_score(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        engine.carbon_intensities[CarbonIntensityRegion.US_EAST] = 10.0
        p = _profile("api", region=CarbonIntensityRegion.US_EAST, intensity=10.0)
        score = engine._carbon_efficiency_score([p])
        # With lower max_intensity range, region_score changes
        assert 0.0 <= score <= 100.0

    def test_override_does_not_affect_default(self):
        engine = CarbonResilienceEngine(_graph())
        engine.carbon_intensities[CarbonIntensityRegion.EU_NORTH] = 999.0
        assert DEFAULT_CARBON_INTENSITY[CarbonIntensityRegion.EU_NORTH] == 30.0

    def test_suggest_optimizations_uses_engine_intensities(self):
        g = _graph(_comp("api", "API"))
        engine = CarbonResilienceEngine(g)
        # Override EU_NORTH to same as US_EAST so migration makes no sense
        engine.carbon_intensities[CarbonIntensityRegion.EU_NORTH] = 386.0
        p = _profile("api", region=CarbonIntensityRegion.US_EAST)
        opts = engine.suggest_optimizations([p])
        migration = [o for o in opts if "EU_NORTH" in o.recommendation]
        # Migration still happens because _co2_with_intensity uses the overridden value
        assert len(migration) == 1
        # But savings should be 0 since both intensities are equal
        assert migration[0].savings_percent == pytest.approx(0.0, abs=0.1)


# ---------------------------------------------------------------------------
# Tests: Model serialization roundtrip
# ---------------------------------------------------------------------------


class TestModelSerialization:
    def test_carbon_profile_dict_roundtrip(self):
        p = _profile("api", watts=250.0, pue=1.4)
        d = p.model_dump()
        p2 = CarbonProfile(**d)
        assert p2.component_id == p.component_id
        assert p2.power_consumption_watts == p.power_consumption_watts
        assert p2.pue == p.pue

    def test_carbon_footprint_dict_roundtrip(self):
        fp = CarbonFootprint(
            component_id="x", annual_kwh=100, annual_co2_kg=50,
            per_replica_co2_kg=25, total_with_replicas_co2_kg=50,
        )
        d = fp.model_dump()
        fp2 = CarbonFootprint(**d)
        assert fp2 == fp

    def test_report_dict_roundtrip(self):
        r = CarbonResilienceReport(
            total_annual_co2_kg=100, co2_per_component=[], tradeoffs=[],
            optimizations=[], esg_summary="test", carbon_efficiency_score=55.0,
        )
        d = r.model_dump()
        r2 = CarbonResilienceReport(**d)
        assert r2.total_annual_co2_kg == r.total_annual_co2_kg
        assert r2.carbon_efficiency_score == r.carbon_efficiency_score
