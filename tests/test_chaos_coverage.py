"""Tests for chaos_coverage module — Chaos Coverage Map."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.chaos_coverage import (
    ChaosCoverageEngine,
    ChaosCoverageReport,
    CoverageEntry,
    CoverageGap,
    CoverageStatus,
    CoverageTrend,
    FailureDomain,
    _ALL_DOMAINS,
    _DOMAIN_COUNT,
    _HIGH_RISK_THRESHOLD,
    _MEDIUM_RISK_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str = "",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        health=health,
    )


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# FailureDomain enum tests
# ---------------------------------------------------------------------------


class TestFailureDomain:
    def test_has_eight_members(self):
        assert len(FailureDomain) == 8

    def test_values(self):
        expected = {
            "compute",
            "network",
            "storage",
            "database",
            "dependency",
            "security",
            "capacity",
            "latency",
        }
        assert {d.value for d in FailureDomain} == expected

    def test_is_str_enum(self):
        assert isinstance(FailureDomain.COMPUTE, str)

    def test_identity(self):
        assert FailureDomain("compute") is FailureDomain.COMPUTE


# ---------------------------------------------------------------------------
# CoverageStatus enum tests
# ---------------------------------------------------------------------------


class TestCoverageStatus:
    def test_has_four_members(self):
        assert len(CoverageStatus) == 4

    def test_values(self):
        expected = {"tested", "partially_tested", "untested", "excluded"}
        assert {s.value for s in CoverageStatus} == expected

    def test_is_str_enum(self):
        assert isinstance(CoverageStatus.TESTED, str)


# ---------------------------------------------------------------------------
# CoverageEntry model tests
# ---------------------------------------------------------------------------


class TestCoverageEntry:
    def test_defaults(self):
        e = CoverageEntry(
            component_id="x", failure_domain=FailureDomain.COMPUTE
        )
        assert e.status == CoverageStatus.UNTESTED
        assert e.last_tested is None
        assert e.test_count == 0
        assert e.last_result_passed is None

    def test_all_fields(self):
        now = datetime.now(timezone.utc)
        e = CoverageEntry(
            component_id="y",
            failure_domain=FailureDomain.NETWORK,
            status=CoverageStatus.TESTED,
            last_tested=now,
            test_count=5,
            last_result_passed=True,
        )
        assert e.component_id == "y"
        assert e.failure_domain == FailureDomain.NETWORK
        assert e.status == CoverageStatus.TESTED
        assert e.last_tested == now
        assert e.test_count == 5
        assert e.last_result_passed is True

    def test_serialisation_round_trip(self):
        e = CoverageEntry(
            component_id="z",
            failure_domain=FailureDomain.STORAGE,
            status=CoverageStatus.PARTIALLY_TESTED,
        )
        d = e.model_dump()
        e2 = CoverageEntry(**d)
        assert e2 == e


# ---------------------------------------------------------------------------
# CoverageGap model tests
# ---------------------------------------------------------------------------


class TestCoverageGap:
    def test_defaults(self):
        g = CoverageGap(component_id="a", missing_domains=[])
        assert g.risk_score == 0.0
        assert g.priority == 0
        assert g.recommendation == ""

    def test_all_fields(self):
        g = CoverageGap(
            component_id="b",
            missing_domains=[FailureDomain.COMPUTE, FailureDomain.NETWORK],
            risk_score=0.8,
            priority=1,
            recommendation="Fix now",
        )
        assert g.component_id == "b"
        assert len(g.missing_domains) == 2
        assert g.risk_score == 0.8

    def test_risk_score_bounds(self):
        with pytest.raises(Exception):
            CoverageGap(component_id="x", missing_domains=[], risk_score=1.5)
        with pytest.raises(Exception):
            CoverageGap(component_id="x", missing_domains=[], risk_score=-0.1)


# ---------------------------------------------------------------------------
# CoverageTrend model tests
# ---------------------------------------------------------------------------


class TestCoverageTrend:
    def test_defaults(self):
        now = datetime.now(timezone.utc)
        t = CoverageTrend(timestamp=now, overall_percent=50.0)
        assert t.by_domain == {}

    def test_with_by_domain(self):
        now = datetime.now(timezone.utc)
        t = CoverageTrend(
            timestamp=now,
            overall_percent=75.0,
            by_domain={"compute": 100.0, "network": 50.0},
        )
        assert t.by_domain["compute"] == 100.0


# ---------------------------------------------------------------------------
# ChaosCoverageReport model tests
# ---------------------------------------------------------------------------


class TestChaosCoverageReport:
    def test_defaults(self):
        r = ChaosCoverageReport()
        assert r.overall_coverage_percent == 0.0
        assert r.by_component == {}
        assert r.by_domain == {}
        assert r.gaps == []
        assert r.trends == []
        assert r.total_tests_run == 0
        assert r.recommendations == []

    def test_populated_report(self):
        r = ChaosCoverageReport(
            overall_coverage_percent=55.5,
            by_component={"app": 75.0},
            by_domain={"compute": 100.0},
            total_tests_run=10,
            recommendations=["Keep going"],
        )
        assert r.overall_coverage_percent == 55.5
        assert r.total_tests_run == 10


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_all_domains_length(self):
        assert len(_ALL_DOMAINS) == 8

    def test_domain_count(self):
        assert _DOMAIN_COUNT == 8

    def test_thresholds(self):
        assert 0 < _MEDIUM_RISK_THRESHOLD < _HIGH_RISK_THRESHOLD <= 1.0


# ---------------------------------------------------------------------------
# ChaosCoverageEngine — construction
# ---------------------------------------------------------------------------


class TestEngineInit:
    def test_empty_graph(self):
        engine = ChaosCoverageEngine(InfraGraph())
        assert engine.calculate_overall_coverage() == 0.0

    def test_single_component_seeds_entries(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        cov = engine.get_component_coverage("a")
        assert len(cov) == _DOMAIN_COUNT
        assert all(s == CoverageStatus.UNTESTED for s in cov.values())

    def test_multiple_components_seeds_entries(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        engine = ChaosCoverageEngine(g)
        for cid in ("a", "b", "c"):
            cov = engine.get_component_coverage(cid)
            assert len(cov) == _DOMAIN_COUNT

    def test_initial_total_tests_zero(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        assert engine._total_tests == 0


# ---------------------------------------------------------------------------
# record_test
# ---------------------------------------------------------------------------


class TestRecordTest:
    def test_single_record(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        cov = engine.get_component_coverage("a")
        assert cov["compute"] == CoverageStatus.TESTED

    def test_total_tests_increment(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        engine.record_test("a", FailureDomain.NETWORK, False)
        assert engine._total_tests == 2

    def test_multiple_records_same_cell(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        engine.record_test("a", FailureDomain.COMPUTE, False)
        entry = engine._entries[("a", FailureDomain.COMPUTE)]
        assert entry.test_count == 2
        assert entry.last_result_passed is False

    def test_sets_last_tested(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        before = datetime.now(timezone.utc)
        engine.record_test("a", FailureDomain.STORAGE, True)
        after = datetime.now(timezone.utc)
        entry = engine._entries[("a", FailureDomain.STORAGE)]
        assert entry.last_tested is not None
        assert before <= entry.last_tested <= after

    def test_unknown_component_raises(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        with pytest.raises(KeyError, match="Unknown component"):
            engine.record_test("missing", FailureDomain.COMPUTE, True)

    def test_record_passed_true(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.LATENCY, True)
        assert engine._entries[("a", FailureDomain.LATENCY)].last_result_passed is True

    def test_record_passed_false(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.LATENCY, False)
        assert engine._entries[("a", FailureDomain.LATENCY)].last_result_passed is False

    def test_record_all_domains_for_component(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        for d in FailureDomain:
            engine.record_test("a", d, True)
        cov = engine.get_component_coverage("a")
        assert all(s == CoverageStatus.TESTED for s in cov.values())

    def test_record_across_multiple_components(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        engine.record_test("b", FailureDomain.NETWORK, False)
        assert engine._entries[("a", FailureDomain.COMPUTE)].status == CoverageStatus.TESTED
        assert engine._entries[("b", FailureDomain.NETWORK)].status == CoverageStatus.TESTED
        assert engine._entries[("a", FailureDomain.NETWORK)].status == CoverageStatus.UNTESTED


# ---------------------------------------------------------------------------
# exclude_component
# ---------------------------------------------------------------------------


class TestExcludeComponent:
    def test_marks_all_domains_excluded(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.exclude_component("a")
        cov = engine.get_component_coverage("a")
        assert all(s == CoverageStatus.EXCLUDED for s in cov.values())

    def test_excluded_not_in_coverage_calc(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        for d in FailureDomain:
            engine.record_test("a", d, True)
        engine.exclude_component("b")
        assert engine.calculate_overall_coverage() == 100.0

    def test_exclude_all_yields_zero(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.exclude_component("a")
        assert engine.calculate_overall_coverage() == 0.0

    def test_unknown_component_raises(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        with pytest.raises(KeyError, match="Unknown component"):
            engine.exclude_component("missing")

    def test_exclude_then_record_keeps_tested_status(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        engine.exclude_component("a")
        # Exclude overrides all domains to EXCLUDED
        cov = engine.get_component_coverage("a")
        assert cov["compute"] == CoverageStatus.EXCLUDED

    def test_exclude_is_idempotent(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.exclude_component("a")
        engine.exclude_component("a")
        assert "a" in engine._excluded


# ---------------------------------------------------------------------------
# get_component_coverage
# ---------------------------------------------------------------------------


class TestGetComponentCoverage:
    def test_untested_initial(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        cov = engine.get_component_coverage("a")
        assert all(v == CoverageStatus.UNTESTED for v in cov.values())

    def test_mixed_coverage(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        engine.record_test("a", FailureDomain.NETWORK, False)
        cov = engine.get_component_coverage("a")
        assert cov["compute"] == CoverageStatus.TESTED
        assert cov["network"] == CoverageStatus.TESTED
        assert cov["storage"] == CoverageStatus.UNTESTED

    def test_unknown_component_raises(self):
        engine = ChaosCoverageEngine(InfraGraph())
        with pytest.raises(KeyError, match="Unknown component"):
            engine.get_component_coverage("nope")

    def test_keys_match_domain_values(self):
        g = _graph(_comp("x"))
        engine = ChaosCoverageEngine(g)
        cov = engine.get_component_coverage("x")
        assert set(cov.keys()) == {d.value for d in FailureDomain}


# ---------------------------------------------------------------------------
# get_domain_coverage
# ---------------------------------------------------------------------------


class TestGetDomainCoverage:
    def test_zero_when_untested(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        assert engine.get_domain_coverage(FailureDomain.COMPUTE) == 0.0

    def test_hundred_when_all_tested(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        engine.record_test("b", FailureDomain.COMPUTE, True)
        assert engine.get_domain_coverage(FailureDomain.COMPUTE) == 100.0

    def test_partial(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        assert engine.get_domain_coverage(FailureDomain.COMPUTE) == 50.0

    def test_excluded_not_counted(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        engine.exclude_component("b")
        assert engine.get_domain_coverage(FailureDomain.COMPUTE) == 100.0

    def test_empty_graph_returns_zero(self):
        engine = ChaosCoverageEngine(InfraGraph())
        assert engine.get_domain_coverage(FailureDomain.NETWORK) == 0.0

    def test_all_excluded_returns_zero(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.exclude_component("a")
        assert engine.get_domain_coverage(FailureDomain.COMPUTE) == 0.0


# ---------------------------------------------------------------------------
# identify_gaps
# ---------------------------------------------------------------------------


class TestIdentifyGaps:
    def test_no_gaps_when_fully_tested(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        for d in FailureDomain:
            engine.record_test("a", d, True)
        assert engine.identify_gaps() == []

    def test_all_domains_missing_for_untested_component(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        gaps = engine.identify_gaps()
        assert len(gaps) == 1
        assert set(gaps[0].missing_domains) == set(FailureDomain)

    def test_partial_gap(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        engine.record_test("a", FailureDomain.NETWORK, True)
        gaps = engine.identify_gaps()
        assert len(gaps) == 1
        assert FailureDomain.COMPUTE not in gaps[0].missing_domains
        assert FailureDomain.NETWORK not in gaps[0].missing_domains

    def test_excluded_components_skipped(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        engine.exclude_component("a")
        gaps = engine.identify_gaps()
        assert all(gap.component_id != "a" for gap in gaps)

    def test_sorted_by_risk_descending(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        g.add_dependency(Dependency(source_id="c", target_id="a"))
        engine = ChaosCoverageEngine(g)
        gaps = engine.identify_gaps()
        for i in range(len(gaps) - 1):
            assert gaps[i].risk_score >= gaps[i + 1].risk_score

    def test_gap_has_recommendation(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        gaps = engine.identify_gaps()
        assert len(gaps) == 1
        assert gaps[0].recommendation != ""

    def test_gap_risk_score_range(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        gaps = engine.identify_gaps()
        for gap in gaps:
            assert 0.0 <= gap.risk_score <= 1.0

    def test_gap_priority_is_integer(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        gaps = engine.identify_gaps()
        for gap in gaps:
            assert isinstance(gap.priority, int)

    def test_no_gap_for_empty_graph(self):
        engine = ChaosCoverageEngine(InfraGraph())
        assert engine.identify_gaps() == []

    def test_multiple_components_gaps(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        gaps = engine.identify_gaps()
        ids = {gap.component_id for gap in gaps}
        assert "a" in ids  # still has 7 missing domains
        assert "b" in ids  # all 8 missing


# ---------------------------------------------------------------------------
# calculate_overall_coverage
# ---------------------------------------------------------------------------


class TestCalculateOverallCoverage:
    def test_zero_when_nothing_tested(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        assert engine.calculate_overall_coverage() == 0.0

    def test_hundred_when_fully_tested(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        for d in FailureDomain:
            engine.record_test("a", d, True)
        assert engine.calculate_overall_coverage() == 100.0

    def test_partial_coverage(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        expected = 1 / _DOMAIN_COUNT * 100.0
        assert abs(engine.calculate_overall_coverage() - expected) < 0.01

    def test_empty_graph(self):
        engine = ChaosCoverageEngine(InfraGraph())
        assert engine.calculate_overall_coverage() == 0.0

    def test_excludes_dont_count(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        for d in FailureDomain:
            engine.record_test("a", d, True)
        engine.exclude_component("b")
        assert engine.calculate_overall_coverage() == 100.0

    def test_two_components_half_tested(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        for d in FailureDomain:
            engine.record_test("a", d, True)
        # b is untested, so 8 / 16 = 50%
        assert engine.calculate_overall_coverage() == 50.0

    def test_all_excluded_returns_zero(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.exclude_component("a")
        assert engine.calculate_overall_coverage() == 0.0


# ---------------------------------------------------------------------------
# snapshot_trend
# ---------------------------------------------------------------------------


class TestSnapshotTrend:
    def test_returns_coverage_trend(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        t = engine.snapshot_trend()
        assert isinstance(t, CoverageTrend)

    def test_timestamp_is_recent(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        before = datetime.now(timezone.utc)
        t = engine.snapshot_trend()
        after = datetime.now(timezone.utc)
        assert before <= t.timestamp <= after

    def test_overall_percent_matches(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        t = engine.snapshot_trend()
        expected = engine.calculate_overall_coverage()
        assert abs(t.overall_percent - expected) < 0.01

    def test_by_domain_populated(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        t = engine.snapshot_trend()
        assert len(t.by_domain) == _DOMAIN_COUNT

    def test_appends_to_trends_list(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.snapshot_trend()
        engine.snapshot_trend()
        assert len(engine._trends) == 2

    def test_successive_trends_reflect_improvement(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        t1 = engine.snapshot_trend()
        engine.record_test("a", FailureDomain.COMPUTE, True)
        t2 = engine.snapshot_trend()
        assert t2.overall_percent > t1.overall_percent


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_returns_report_type(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        r = engine.generate_report()
        assert isinstance(r, ChaosCoverageReport)

    def test_overall_coverage(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        r = engine.generate_report()
        assert r.overall_coverage_percent == 0.0

    def test_by_component_keys(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        r = engine.generate_report()
        assert set(r.by_component.keys()) == {"a", "b"}

    def test_by_domain_keys(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        r = engine.generate_report()
        assert set(r.by_domain.keys()) == {d.value for d in FailureDomain}

    def test_total_tests_run(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        engine.record_test("a", FailureDomain.NETWORK, False)
        r = engine.generate_report()
        assert r.total_tests_run == 2

    def test_gaps_populated(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        r = engine.generate_report()
        assert len(r.gaps) > 0

    def test_no_gaps_when_fully_tested(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        for d in FailureDomain:
            engine.record_test("a", d, True)
        r = engine.generate_report()
        assert r.gaps == []

    def test_recommendations_present(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        r = engine.generate_report()
        assert len(r.recommendations) > 0

    def test_trends_in_report(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.snapshot_trend()
        r = engine.generate_report()
        assert len(r.trends) == 1

    def test_excluded_not_in_by_component(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        engine.exclude_component("a")
        r = engine.generate_report()
        assert "a" not in r.by_component
        assert "b" in r.by_component

    def test_by_component_percent_correct(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        engine.record_test("a", FailureDomain.NETWORK, True)
        r = engine.generate_report()
        expected = 2 / _DOMAIN_COUNT * 100.0
        assert abs(r.by_component["a"] - expected) < 0.01

    def test_empty_graph_report(self):
        engine = ChaosCoverageEngine(InfraGraph())
        r = engine.generate_report()
        assert r.overall_coverage_percent == 0.0
        assert r.by_component == {}
        assert r.total_tests_run == 0
        assert r.gaps == []


# ---------------------------------------------------------------------------
# Private helpers — _component_risk
# ---------------------------------------------------------------------------


class TestComponentRisk:
    def test_all_missing_no_dependents(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        risk = engine._component_risk("a", list(FailureDomain))
        # missing_ratio=1.0, dep_factor=0 => 0.5
        assert abs(risk - 0.5) < 0.01

    def test_none_missing(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        risk = engine._component_risk("a", [])
        assert risk == 0.0

    def test_high_dependent_count_raises_risk(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        g.add_dependency(Dependency(source_id="c", target_id="a"))
        engine = ChaosCoverageEngine(g)
        risk = engine._component_risk("a", list(FailureDomain))
        # dep_factor = 2/3, missing_ratio = 1.0 => 0.5*1 + 0.5*(2/3) = 0.833
        assert risk > 0.5


# ---------------------------------------------------------------------------
# Private helpers — _risk_to_priority
# ---------------------------------------------------------------------------


class TestRiskToPriority:
    def test_high_risk(self):
        assert ChaosCoverageEngine._risk_to_priority(0.8) == 1

    def test_medium_risk(self):
        assert ChaosCoverageEngine._risk_to_priority(0.5) == 2

    def test_low_risk(self):
        assert ChaosCoverageEngine._risk_to_priority(0.2) == 3

    def test_exact_high_threshold(self):
        assert ChaosCoverageEngine._risk_to_priority(_HIGH_RISK_THRESHOLD) == 1

    def test_exact_medium_threshold(self):
        assert ChaosCoverageEngine._risk_to_priority(_MEDIUM_RISK_THRESHOLD) == 2

    def test_just_below_medium(self):
        assert ChaosCoverageEngine._risk_to_priority(_MEDIUM_RISK_THRESHOLD - 0.01) == 3

    def test_zero_risk(self):
        assert ChaosCoverageEngine._risk_to_priority(0.0) == 3

    def test_max_risk(self):
        assert ChaosCoverageEngine._risk_to_priority(1.0) == 1


# ---------------------------------------------------------------------------
# Private helpers — _build_recommendation
# ---------------------------------------------------------------------------


class TestBuildRecommendation:
    def test_critical_recommendation(self):
        rec = ChaosCoverageEngine._build_recommendation(
            "app", [FailureDomain.COMPUTE], 0.8
        )
        assert "CRITICAL" in rec
        assert "app" in rec
        assert "compute" in rec

    def test_warning_recommendation(self):
        rec = ChaosCoverageEngine._build_recommendation(
            "db", [FailureDomain.STORAGE], 0.5
        )
        assert "WARNING" in rec
        assert "db" in rec

    def test_info_recommendation(self):
        rec = ChaosCoverageEngine._build_recommendation(
            "cache", [FailureDomain.LATENCY], 0.2
        )
        assert "INFO" in rec
        assert "cache" in rec

    def test_exact_high_threshold(self):
        rec = ChaosCoverageEngine._build_recommendation(
            "x", [FailureDomain.NETWORK], _HIGH_RISK_THRESHOLD
        )
        assert "CRITICAL" in rec

    def test_exact_medium_threshold(self):
        rec = ChaosCoverageEngine._build_recommendation(
            "x", [FailureDomain.NETWORK], _MEDIUM_RISK_THRESHOLD
        )
        assert "WARNING" in rec

    def test_multiple_domains_listed(self):
        rec = ChaosCoverageEngine._build_recommendation(
            "x",
            [FailureDomain.COMPUTE, FailureDomain.NETWORK, FailureDomain.STORAGE],
            0.9,
        )
        assert "compute" in rec
        assert "network" in rec
        assert "storage" in rec


# ---------------------------------------------------------------------------
# Private helpers — _build_report_recommendations
# ---------------------------------------------------------------------------


class TestBuildReportRecommendations:
    def test_very_low_coverage(self):
        recs = ChaosCoverageEngine._build_report_recommendations([], 10.0)
        assert any("very low" in r.lower() for r in recs)

    def test_below_50(self):
        recs = ChaosCoverageEngine._build_report_recommendations([], 40.0)
        assert any("below 50" in r.lower() for r in recs)

    def test_good_progress(self):
        recs = ChaosCoverageEngine._build_report_recommendations([], 60.0)
        assert any("good progress" in r.lower() for r in recs)

    def test_strong_coverage(self):
        recs = ChaosCoverageEngine._build_report_recommendations([], 80.0)
        assert any("strong" in r.lower() for r in recs)

    def test_critical_gaps_mentioned(self):
        gap = CoverageGap(
            component_id="x",
            missing_domains=[FailureDomain.COMPUTE],
            risk_score=0.8,
            priority=1,
        )
        recs = ChaosCoverageEngine._build_report_recommendations([gap], 50.0)
        assert any("critical" in r.lower() for r in recs)

    def test_no_critical_gaps(self):
        gap = CoverageGap(
            component_id="x",
            missing_domains=[FailureDomain.COMPUTE],
            risk_score=0.3,
            priority=3,
        )
        recs = ChaosCoverageEngine._build_report_recommendations([gap], 50.0)
        assert not any("critical coverage" in r.lower() for r in recs)

    def test_boundary_25(self):
        recs = ChaosCoverageEngine._build_report_recommendations([], 25.0)
        assert any("below 50" in r.lower() for r in recs)

    def test_boundary_50(self):
        recs = ChaosCoverageEngine._build_report_recommendations([], 50.0)
        assert any("good progress" in r.lower() for r in recs)

    def test_boundary_75(self):
        recs = ChaosCoverageEngine._build_report_recommendations([], 75.0)
        assert any("strong" in r.lower() for r in recs)


# ---------------------------------------------------------------------------
# Integration / end-to-end scenarios
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_lifecycle(self):
        """Record tests, snapshot, exclude, generate report."""
        g = _graph(_comp("web"), _comp("api"), _comp("db"))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        engine = ChaosCoverageEngine(g)

        # Test some domains
        engine.record_test("web", FailureDomain.COMPUTE, True)
        engine.record_test("web", FailureDomain.NETWORK, True)
        engine.record_test("api", FailureDomain.LATENCY, False)
        engine.snapshot_trend()

        # Exclude db
        engine.exclude_component("db")
        engine.snapshot_trend()

        report = engine.generate_report()
        assert report.overall_coverage_percent > 0
        assert report.total_tests_run == 3
        assert len(report.trends) == 2
        assert "db" not in report.by_component

    def test_coverage_improves_with_more_tests(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        c1 = engine.calculate_overall_coverage()
        engine.record_test("a", FailureDomain.COMPUTE, True)
        c2 = engine.calculate_overall_coverage()
        engine.record_test("a", FailureDomain.NETWORK, True)
        c3 = engine.calculate_overall_coverage()
        assert c1 < c2 < c3

    def test_gaps_shrink_as_tests_added(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        g1 = engine.identify_gaps()
        engine.record_test("a", FailureDomain.COMPUTE, True)
        g2 = engine.identify_gaps()
        assert len(g2[0].missing_domains) < len(g1[0].missing_domains)

    def test_report_with_dependency_graph(self):
        g = _graph(
            _comp("lb", ctype=ComponentType.LOAD_BALANCER),
            _comp("app"),
            _comp("db", ctype=ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="lb", target_id="app"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        engine = ChaosCoverageEngine(g)
        # db has 2 dependents (transitively), should be higher risk
        gaps = engine.identify_gaps()
        db_gap = next(g for g in gaps if g.component_id == "db")
        lb_gap = next(g for g in gaps if g.component_id == "lb")
        # db has more dependents so should be >= lb in risk
        assert db_gap.risk_score >= lb_gap.risk_score

    def test_full_coverage_report(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        for d in FailureDomain:
            engine.record_test("a", d, True)
        report = engine.generate_report()
        assert report.overall_coverage_percent == 100.0
        assert report.by_component["a"] == 100.0
        assert report.gaps == []
        assert report.total_tests_run == _DOMAIN_COUNT

    def test_many_components(self):
        comps = [_comp(f"c{i}") for i in range(20)]
        g = _graph(*comps)
        engine = ChaosCoverageEngine(g)
        for c in comps[:10]:
            for d in FailureDomain:
                engine.record_test(c.id, d, True)
        assert engine.calculate_overall_coverage() == 50.0

    def test_trend_captures_domain_coverage(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        t = engine.snapshot_trend()
        assert t.by_domain["compute"] == 50.0
        assert t.by_domain["network"] == 0.0

    def test_report_recommendations_for_zero_coverage(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        r = engine.generate_report()
        assert any("very low" in rec.lower() for rec in r.recommendations)

    def test_report_recommendations_for_full_coverage(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        for d in FailureDomain:
            engine.record_test("a", d, True)
        r = engine.generate_report()
        assert any("strong" in rec.lower() for rec in r.recommendations)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_domain_single_component(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.SECURITY, True)
        assert engine.get_domain_coverage(FailureDomain.SECURITY) == 100.0
        assert engine.get_domain_coverage(FailureDomain.COMPUTE) == 0.0

    def test_record_then_exclude_then_report(self):
        g = _graph(_comp("a"), _comp("b"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        engine.exclude_component("a")
        r = engine.generate_report()
        assert "a" not in r.by_component
        # total tests still counts the recorded test
        assert r.total_tests_run == 1

    def test_multiple_snapshots(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        for i, d in enumerate(FailureDomain):
            engine.record_test("a", d, True)
            engine.snapshot_trend()
        assert len(engine._trends) == _DOMAIN_COUNT
        # Each successive snapshot should have higher or equal coverage
        for i in range(1, len(engine._trends)):
            assert engine._trends[i].overall_percent >= engine._trends[i - 1].overall_percent

    def test_component_types_dont_affect_coverage(self):
        g = _graph(
            _comp("lb", ctype=ComponentType.LOAD_BALANCER),
            _comp("db", ctype=ComponentType.DATABASE),
            _comp("cache", ctype=ComponentType.CACHE),
        )
        engine = ChaosCoverageEngine(g)
        engine.record_test("lb", FailureDomain.COMPUTE, True)
        engine.record_test("db", FailureDomain.COMPUTE, True)
        engine.record_test("cache", FailureDomain.COMPUTE, True)
        assert engine.get_domain_coverage(FailureDomain.COMPUTE) == 100.0

    def test_gap_priority_values(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        gaps = engine.identify_gaps()
        for gap in gaps:
            assert gap.priority in (1, 2, 3)

    def test_concurrent_domain_testing(self):
        """Test recording all domains at once for multiple components."""
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        engine = ChaosCoverageEngine(g)
        for cid in ("a", "b", "c"):
            for d in FailureDomain:
                engine.record_test(cid, d, True)
        assert engine.calculate_overall_coverage() == 100.0
        assert engine._total_tests == 3 * _DOMAIN_COUNT

    def test_report_serialisation(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        engine.snapshot_trend()
        r = engine.generate_report()
        d = r.model_dump()
        r2 = ChaosCoverageReport(**d)
        assert r2.overall_coverage_percent == r.overall_coverage_percent
        assert r2.total_tests_run == r.total_tests_run

    def test_domain_coverage_three_of_four(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"), _comp("d"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.DATABASE, True)
        engine.record_test("b", FailureDomain.DATABASE, True)
        engine.record_test("c", FailureDomain.DATABASE, True)
        assert engine.get_domain_coverage(FailureDomain.DATABASE) == 75.0

    def test_risk_capped_at_one(self):
        """Even with many dependents and all missing, risk stays <= 1.0."""
        comps = [_comp(f"c{i}") for i in range(10)]
        g = _graph(*comps)
        for i in range(1, 10):
            g.add_dependency(Dependency(source_id=f"c{i}", target_id="c0"))
        engine = ChaosCoverageEngine(g)
        risk = engine._component_risk("c0", list(FailureDomain))
        assert risk <= 1.0

    def test_snapshot_trend_domain_values_rounded(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        engine = ChaosCoverageEngine(g)
        engine.record_test("a", FailureDomain.COMPUTE, True)
        t = engine.snapshot_trend()
        # 1/3 = 33.3333... should be rounded to 4 decimals
        val = t.by_domain["compute"]
        assert val == round(val, 4)

    def test_gap_missing_domains_subset(self):
        """After testing some domains, gap should only list the untested ones."""
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        tested = [FailureDomain.COMPUTE, FailureDomain.NETWORK, FailureDomain.STORAGE]
        for d in tested:
            engine.record_test("a", d, True)
        gaps = engine.identify_gaps()
        assert len(gaps) == 1
        assert len(gaps[0].missing_domains) == _DOMAIN_COUNT - len(tested)
        for d in tested:
            assert d not in gaps[0].missing_domains

    def test_report_by_domain_zero_for_untested(self):
        g = _graph(_comp("a"))
        engine = ChaosCoverageEngine(g)
        r = engine.generate_report()
        assert all(v == 0.0 for v in r.by_domain.values())
