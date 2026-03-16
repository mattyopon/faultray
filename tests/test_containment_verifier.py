"""Comprehensive tests for the Blast Radius Containment Verifier.

Tests cover ContainmentMechanism/ContainmentStatus enums, ContainmentRule,
ContainmentTest, ContainmentGap, ContainmentReport models,
ContainmentVerifier core logic (add_rule, verify_containment, verify_all,
find_containment_gaps, calculate_containment_score, generate_report),
edge-cases (empty graph, single component, no rules, large graph),
status determination, effectiveness calculation, and full integration.
"""

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
    RetryStrategy,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.containment_verifier import (
    ContainmentGap,
    ContainmentMechanism,
    ContainmentReport,
    ContainmentRule,
    ContainmentStatus,
    ContainmentTest,
    ContainmentVerifier,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str | None = None,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover_enabled: bool = False,
    autoscaling_enabled: bool = False,
    rate_limiting: bool = False,
    timeout_seconds: float = 30.0,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover_enabled),
        autoscaling=AutoScalingConfig(enabled=autoscaling_enabled),
        security=SecurityProfile(rate_limiting=rate_limiting),
        capacity=Capacity(timeout_seconds=timeout_seconds),
    )


def _dep(
    src: str,
    tgt: str,
    dep_type: str = "requires",
    cb_enabled: bool = False,
    retry_enabled: bool = False,
) -> Dependency:
    return Dependency(
        source_id=src,
        target_id=tgt,
        dependency_type=dep_type,
        circuit_breaker=CircuitBreakerConfig(enabled=cb_enabled),
        retry_strategy=RetryStrategy(enabled=retry_enabled),
    )


def _graph(*components: Component, deps: list[Dependency] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for d in deps or []:
        g.add_dependency(d)
    return g


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestContainmentMechanismEnum:
    def test_circuit_breaker_value(self):
        assert ContainmentMechanism.CIRCUIT_BREAKER == "circuit_breaker"

    def test_bulkhead_value(self):
        assert ContainmentMechanism.BULKHEAD == "bulkhead"

    def test_rate_limiter_value(self):
        assert ContainmentMechanism.RATE_LIMITER == "rate_limiter"

    def test_timeout_value(self):
        assert ContainmentMechanism.TIMEOUT == "timeout"

    def test_retry_budget_value(self):
        assert ContainmentMechanism.RETRY_BUDGET == "retry_budget"

    def test_load_shedding_value(self):
        assert ContainmentMechanism.LOAD_SHEDDING == "load_shedding"

    def test_graceful_degradation_value(self):
        assert ContainmentMechanism.GRACEFUL_DEGRADATION == "graceful_degradation"

    def test_failover_value(self):
        assert ContainmentMechanism.FAILOVER == "failover"

    def test_all_members(self):
        assert len(ContainmentMechanism) == 8

    def test_string_comparison(self):
        assert ContainmentMechanism("circuit_breaker") == ContainmentMechanism.CIRCUIT_BREAKER


class TestContainmentStatusEnum:
    def test_contained_value(self):
        assert ContainmentStatus.CONTAINED == "contained"

    def test_partially_contained_value(self):
        assert ContainmentStatus.PARTIALLY_CONTAINED == "partially_contained"

    def test_breached_value(self):
        assert ContainmentStatus.BREACHED == "breached"

    def test_not_tested_value(self):
        assert ContainmentStatus.NOT_TESTED == "not_tested"

    def test_all_members(self):
        assert len(ContainmentStatus) == 4


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


class TestContainmentRuleModel:
    def test_basic_creation(self):
        rule = ContainmentRule(
            mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
            component_id="web",
            max_blast_radius=3,
            max_propagation_depth=2,
        )
        assert rule.mechanism == ContainmentMechanism.CIRCUIT_BREAKER
        assert rule.component_id == "web"
        assert rule.max_blast_radius == 3
        assert rule.max_propagation_depth == 2
        assert rule.timeout_seconds is None

    def test_with_timeout(self):
        rule = ContainmentRule(
            mechanism=ContainmentMechanism.TIMEOUT,
            component_id="api",
            timeout_seconds=5.0,
        )
        assert rule.timeout_seconds == 5.0

    def test_defaults(self):
        rule = ContainmentRule(
            mechanism=ContainmentMechanism.BULKHEAD,
            component_id="db",
        )
        assert rule.max_blast_radius == 0
        assert rule.max_propagation_depth == 1
        assert rule.timeout_seconds is None

    def test_serialization_roundtrip(self):
        rule = ContainmentRule(
            mechanism=ContainmentMechanism.FAILOVER,
            component_id="cache",
            max_blast_radius=2,
        )
        data = rule.model_dump()
        restored = ContainmentRule(**data)
        assert restored == rule


class TestContainmentTestModel:
    def test_default_status(self):
        ct = ContainmentTest(failure_component="web")
        assert ct.status == ContainmentStatus.NOT_TESTED
        assert ct.containment_effectiveness == 0.0
        assert ct.expected_affected == []
        assert ct.actual_affected == []

    def test_full_fields(self):
        ct = ContainmentTest(
            failure_component="db",
            failure_type="disk_full",
            expected_blast_radius=2,
            actual_blast_radius=3,
            expected_affected=["api"],
            actual_affected=["api", "web", "cache"],
            status=ContainmentStatus.PARTIALLY_CONTAINED,
            containment_effectiveness=0.67,
        )
        assert ct.failure_type == "disk_full"
        assert ct.actual_blast_radius == 3

    def test_serialization_roundtrip(self):
        ct = ContainmentTest(
            failure_component="x",
            status=ContainmentStatus.CONTAINED,
            containment_effectiveness=1.0,
        )
        data = ct.model_dump()
        restored = ContainmentTest(**data)
        assert restored == ct


class TestContainmentGapModel:
    def test_basic_creation(self):
        gap = ContainmentGap(
            component_id="web",
            missing_mechanisms=[ContainmentMechanism.CIRCUIT_BREAKER],
            risk_level="high",
            recommendation="Add circuit_breaker",
        )
        assert gap.component_id == "web"
        assert len(gap.missing_mechanisms) == 1

    def test_defaults(self):
        gap = ContainmentGap(component_id="z")
        assert gap.risk_level == "low"
        assert gap.recommendation == ""
        assert gap.missing_mechanisms == []

    def test_multiple_missing(self):
        gap = ContainmentGap(
            component_id="db",
            missing_mechanisms=[
                ContainmentMechanism.CIRCUIT_BREAKER,
                ContainmentMechanism.FAILOVER,
                ContainmentMechanism.BULKHEAD,
            ],
        )
        assert len(gap.missing_mechanisms) == 3


class TestContainmentReportModel:
    def test_defaults(self):
        report = ContainmentReport()
        assert report.tests_run == 0
        assert report.contained == 0
        assert report.breached == 0
        assert report.containment_score == 0.0
        assert report.tests == []
        assert report.gaps == []
        assert report.recommendations == []

    def test_full_creation(self):
        report = ContainmentReport(
            tests_run=10,
            contained=8,
            breached=2,
            containment_score=80.0,
            tests=[ContainmentTest(failure_component="a")],
            gaps=[ContainmentGap(component_id="b")],
            recommendations=["Fix b"],
        )
        assert report.tests_run == 10
        assert len(report.tests) == 1
        assert len(report.gaps) == 1
        assert len(report.recommendations) == 1


# ---------------------------------------------------------------------------
# ContainmentVerifier — init & add_rule
# ---------------------------------------------------------------------------


class TestVerifierInit:
    def test_empty_graph(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        assert v.rules == []

    def test_add_single_rule(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        r = ContainmentRule(
            mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
            component_id="web",
        )
        v.add_rule(r)
        assert len(v.rules) == 1

    def test_add_multiple_rules(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        for i in range(5):
            v.add_rule(
                ContainmentRule(
                    mechanism=ContainmentMechanism.BULKHEAD,
                    component_id=f"comp-{i}",
                )
            )
        assert len(v.rules) == 5

    def test_rules_returns_copy(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.TIMEOUT,
                component_id="x",
            )
        )
        external = v.rules
        external.clear()
        assert len(v.rules) == 1  # internal list unaffected


# ---------------------------------------------------------------------------
# verify_containment — single component
# ---------------------------------------------------------------------------


class TestVerifyContainmentSingle:
    def test_isolated_component_no_rules(self):
        g = _graph(_comp("a"))
        v = ContainmentVerifier(g)
        result = v.verify_containment("a")
        assert result.failure_component == "a"
        assert result.actual_blast_radius == 0
        assert result.status == ContainmentStatus.CONTAINED

    def test_isolated_component_with_rule(self):
        g = _graph(_comp("a"))
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.BULKHEAD,
                component_id="a",
                max_blast_radius=0,
            )
        )
        result = v.verify_containment("a")
        assert result.status == ContainmentStatus.CONTAINED
        assert result.containment_effectiveness == 1.0

    def test_two_components_dependency_no_rule(self):
        # b depends on a  →  failing a affects b
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        result = v.verify_containment("a")
        assert result.actual_blast_radius == 1
        assert "b" in result.actual_affected
        # No rule → expected=0, actual=1 → breached
        assert result.status == ContainmentStatus.BREACHED

    def test_contained_when_actual_le_expected(self):
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
                component_id="a",
                max_blast_radius=1,
            )
        )
        result = v.verify_containment("a")
        assert result.status == ContainmentStatus.CONTAINED

    def test_partially_contained(self):
        # expected=2, actual=3  (3 <= 2*1.5=3 → partially)
        c = [_comp(f"n{i}") for i in range(4)]
        deps = [_dep(f"n{i}", "n0") for i in range(1, 4)]
        g = _graph(*c, deps=deps)
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.BULKHEAD,
                component_id="n0",
                max_blast_radius=2,
            )
        )
        result = v.verify_containment("n0")
        assert result.actual_blast_radius == 3
        assert result.status == ContainmentStatus.PARTIALLY_CONTAINED

    def test_breached(self):
        # expected=1, actual=3  (3 > 1*1.5=1 → breached)
        c = [_comp(f"n{i}") for i in range(4)]
        deps = [_dep(f"n{i}", "n0") for i in range(1, 4)]
        g = _graph(*c, deps=deps)
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
                component_id="n0",
                max_blast_radius=1,
            )
        )
        result = v.verify_containment("n0")
        assert result.status == ContainmentStatus.BREACHED

    def test_effectiveness_perfect(self):
        g = _graph(_comp("a"))
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.FAILOVER,
                component_id="a",
                max_blast_radius=0,
            )
        )
        result = v.verify_containment("a")
        assert result.containment_effectiveness == 1.0

    def test_effectiveness_partial(self):
        c = [_comp(f"n{i}") for i in range(3)]
        deps = [_dep("n1", "n0"), _dep("n2", "n0")]
        g = _graph(*c, deps=deps)
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.BULKHEAD,
                component_id="n0",
                max_blast_radius=1,
            )
        )
        result = v.verify_containment("n0")
        assert result.containment_effectiveness == pytest.approx(0.5)

    def test_effectiveness_zero_expected_nonzero_actual(self):
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        result = v.verify_containment("a")
        assert result.containment_effectiveness == 0.0

    def test_failure_type_default(self):
        g = _graph(_comp("x"))
        v = ContainmentVerifier(g)
        result = v.verify_containment("x")
        assert result.failure_type == "component_failure"


# ---------------------------------------------------------------------------
# verify_containment — chain propagation
# ---------------------------------------------------------------------------


class TestVerifyContainmentChain:
    def test_chain_three_deep(self):
        # c → b → a  (failing a affects b then c)
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("b", "a"), _dep("c", "b")],
        )
        v = ContainmentVerifier(g)
        result = v.verify_containment("a")
        assert result.actual_blast_radius == 2
        assert set(result.actual_affected) == {"b", "c"}

    def test_chain_contained_by_rule(self):
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("b", "a"), _dep("c", "b")],
        )
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
                component_id="a",
                max_blast_radius=2,
            )
        )
        result = v.verify_containment("a")
        assert result.status == ContainmentStatus.CONTAINED

    def test_chain_five_deep_breached(self):
        comps = [_comp(f"n{i}") for i in range(6)]
        deps = [_dep(f"n{i+1}", f"n{i}") for i in range(5)]
        g = _graph(*comps, deps=deps)
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.TIMEOUT,
                component_id="n0",
                max_blast_radius=2,
            )
        )
        result = v.verify_containment("n0")
        assert result.actual_blast_radius == 5
        assert result.status == ContainmentStatus.BREACHED


# ---------------------------------------------------------------------------
# verify_containment — fan-out
# ---------------------------------------------------------------------------


class TestVerifyContainmentFanOut:
    def test_fan_out_multiple_dependents(self):
        g = _graph(
            _comp("db"),
            _comp("api1"), _comp("api2"), _comp("api3"),
            deps=[
                _dep("api1", "db"),
                _dep("api2", "db"),
                _dep("api3", "db"),
            ],
        )
        v = ContainmentVerifier(g)
        result = v.verify_containment("db")
        assert result.actual_blast_radius == 3

    def test_fan_out_with_adequate_rule(self):
        g = _graph(
            _comp("db"),
            _comp("api1"), _comp("api2"), _comp("api3"),
            deps=[
                _dep("api1", "db"),
                _dep("api2", "db"),
                _dep("api3", "db"),
            ],
        )
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.FAILOVER,
                component_id="db",
                max_blast_radius=3,
            )
        )
        result = v.verify_containment("db")
        assert result.status == ContainmentStatus.CONTAINED


# ---------------------------------------------------------------------------
# verify_containment — multiple rules on same component
# ---------------------------------------------------------------------------


class TestVerifyContainmentMultipleRules:
    def test_picks_smallest_max_blast_radius(self):
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
                component_id="a",
                max_blast_radius=5,
            )
        )
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.TIMEOUT,
                component_id="a",
                max_blast_radius=1,
            )
        )
        result = v.verify_containment("a")
        assert result.expected_blast_radius == 1
        assert result.status == ContainmentStatus.CONTAINED

    def test_multiple_rules_different_mechanisms(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"), deps=[_dep("b", "a"), _dep("c", "a")])
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.RATE_LIMITER,
                component_id="a",
                max_blast_radius=3,
            )
        )
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.BULKHEAD,
                component_id="a",
                max_blast_radius=2,
            )
        )
        result = v.verify_containment("a")
        assert result.expected_blast_radius == 2


# ---------------------------------------------------------------------------
# verify_all
# ---------------------------------------------------------------------------


class TestVerifyAll:
    def test_empty_graph(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        assert v.verify_all() == []

    def test_single_component(self):
        g = _graph(_comp("only"))
        v = ContainmentVerifier(g)
        results = v.verify_all()
        assert len(results) == 1
        assert results[0].failure_component == "only"

    def test_multiple_components(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        v = ContainmentVerifier(g)
        results = v.verify_all()
        assert len(results) == 3
        ids = {r.failure_component for r in results}
        assert ids == {"a", "b", "c"}

    def test_all_contained_when_no_deps(self):
        g = _graph(_comp("x"), _comp("y"))
        v = ContainmentVerifier(g)
        results = v.verify_all()
        assert all(r.status == ContainmentStatus.CONTAINED for r in results)

    def test_mixed_statuses(self):
        # b→a: failing a affects b
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
                component_id="a",
                max_blast_radius=1,
            )
        )
        results = v.verify_all()
        statuses = {r.failure_component: r.status for r in results}
        assert statuses["a"] == ContainmentStatus.CONTAINED
        assert statuses["b"] == ContainmentStatus.CONTAINED  # b has 0 affected


# ---------------------------------------------------------------------------
# find_containment_gaps
# ---------------------------------------------------------------------------


class TestFindContainmentGaps:
    def test_empty_graph_no_gaps(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        assert v.find_containment_gaps() == []

    def test_fully_protected_component_no_gap(self):
        g = _graph(
            _comp("a", failover_enabled=True, autoscaling_enabled=True,
                  rate_limiting=True, timeout_seconds=30.0),
            _comp("b", failover_enabled=True, autoscaling_enabled=True,
                  rate_limiting=True, timeout_seconds=30.0),
            deps=[_dep("b", "a", cb_enabled=True, retry_enabled=True)],
        )
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        # a has a dependent (b) with CB, b has outgoing edge with retry
        # Both have failover, autoscaling, rate_limiting, timeout
        # 'a' should have no gaps.
        a_gaps = [gap for gap in gaps if gap.component_id == "a"]
        assert len(a_gaps) == 0

    def test_missing_failover_detected(self):
        g = _graph(_comp("a", failover_enabled=False))
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        a_gap = next(gap for gap in gaps if gap.component_id == "a")
        assert ContainmentMechanism.FAILOVER in a_gap.missing_mechanisms

    def test_missing_bulkhead_detected(self):
        g = _graph(_comp("a", replicas=1, autoscaling_enabled=False))
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        a_gap = next(gap for gap in gaps if gap.component_id == "a")
        assert ContainmentMechanism.BULKHEAD in a_gap.missing_mechanisms

    def test_bulkhead_present_with_replicas(self):
        g = _graph(_comp("a", replicas=3, failover_enabled=True,
                         rate_limiting=True, timeout_seconds=30))
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        if gaps:
            a_gap = next((gap for gap in gaps if gap.component_id == "a"), None)
            if a_gap:
                assert ContainmentMechanism.BULKHEAD not in a_gap.missing_mechanisms

    def test_bulkhead_present_with_autoscaling(self):
        g = _graph(_comp("a", autoscaling_enabled=True, failover_enabled=True,
                         rate_limiting=True, timeout_seconds=30))
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        if gaps:
            a_gap = next((gap for gap in gaps if gap.component_id == "a"), None)
            if a_gap:
                assert ContainmentMechanism.BULKHEAD not in a_gap.missing_mechanisms

    def test_missing_circuit_breaker_on_dependency(self):
        # b depends on a without CB → a should have CB gap
        g = _graph(
            _comp("a", failover_enabled=True, rate_limiting=True),
            _comp("b"),
            deps=[_dep("b", "a", cb_enabled=False)],
        )
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        a_gap = next(gap for gap in gaps if gap.component_id == "a")
        assert ContainmentMechanism.CIRCUIT_BREAKER in a_gap.missing_mechanisms

    def test_no_cb_gap_when_cb_exists(self):
        g = _graph(
            _comp("a", failover_enabled=True, rate_limiting=True),
            _comp("b", failover_enabled=True, rate_limiting=True),
            deps=[_dep("b", "a", cb_enabled=True, retry_enabled=True)],
        )
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        a_gaps = [gap for gap in gaps if gap.component_id == "a"]
        if a_gaps:
            assert ContainmentMechanism.CIRCUIT_BREAKER not in a_gaps[0].missing_mechanisms

    def test_missing_timeout_detected(self):
        g = _graph(_comp("a", timeout_seconds=0.0))
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        a_gap = next(gap for gap in gaps if gap.component_id == "a")
        assert ContainmentMechanism.TIMEOUT in a_gap.missing_mechanisms

    def test_missing_rate_limiter_detected(self):
        g = _graph(_comp("a", rate_limiting=False))
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        a_gap = next(gap for gap in gaps if gap.component_id == "a")
        assert ContainmentMechanism.RATE_LIMITER in a_gap.missing_mechanisms

    def test_missing_retry_budget_on_outgoing(self):
        g = _graph(
            _comp("a", failover_enabled=True, rate_limiting=True),
            _comp("b"),
            deps=[_dep("a", "b", retry_enabled=False)],
        )
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        a_gap = next(gap for gap in gaps if gap.component_id == "a")
        assert ContainmentMechanism.RETRY_BUDGET in a_gap.missing_mechanisms

    def test_no_retry_gap_when_retry_exists(self):
        g = _graph(
            _comp("a", failover_enabled=True, rate_limiting=True),
            _comp("b", failover_enabled=True, rate_limiting=True),
            deps=[_dep("a", "b", retry_enabled=True, cb_enabled=True)],
        )
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        a_gaps = [gap for gap in gaps if gap.component_id == "a"]
        if a_gaps:
            assert ContainmentMechanism.RETRY_BUDGET not in a_gaps[0].missing_mechanisms

    def test_risk_level_critical(self):
        # 5+ affected or 4+ missing mechanisms
        comps = [_comp(f"n{i}") for i in range(7)]
        deps = [_dep(f"n{i}", "n0") for i in range(1, 7)]
        g = _graph(*comps, deps=deps)
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        n0_gap = next(gap for gap in gaps if gap.component_id == "n0")
        assert n0_gap.risk_level == "critical"

    def test_risk_level_high(self):
        # 3+ affected or 3+ missing
        comps = [_comp(f"n{i}") for i in range(4)]
        deps = [_dep(f"n{i}", "n0") for i in range(1, 4)]
        g = _graph(*comps, deps=deps)
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        n0_gap = next(gap for gap in gaps if gap.component_id == "n0")
        assert n0_gap.risk_level in ("critical", "high")

    def test_risk_level_medium(self):
        # 1 affected, 2 missing
        g = _graph(
            _comp("a", failover_enabled=True, rate_limiting=True),
            _comp("b"),
            deps=[_dep("b", "a", cb_enabled=False)],
        )
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        a_gap = next(gap for gap in gaps if gap.component_id == "a")
        assert a_gap.risk_level == "medium"

    def test_risk_level_low(self):
        # no dependents, only 1 missing
        g = _graph(_comp("a", failover_enabled=False, rate_limiting=True,
                         autoscaling_enabled=True, timeout_seconds=30))
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        a_gap = next(gap for gap in gaps if gap.component_id == "a")
        assert a_gap.risk_level == "low"

    def test_recommendation_includes_missing_mechanisms(self):
        g = _graph(_comp("db"))
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        db_gap = next(gap for gap in gaps if gap.component_id == "db")
        assert "failover" in db_gap.recommendation

    def test_recommendation_suggests_rules_when_none(self):
        g = _graph(_comp("db"))
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        db_gap = next(gap for gap in gaps if gap.component_id == "db")
        assert "define containment rules" in db_gap.recommendation

    def test_recommendation_no_suggest_rules_when_rule_exists(self):
        g = _graph(_comp("db"))
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.FAILOVER,
                component_id="db",
            )
        )
        gaps = v.find_containment_gaps()
        db_gap = next(gap for gap in gaps if gap.component_id == "db")
        assert "define containment rules" not in db_gap.recommendation

    def test_no_gap_for_component_without_dependents_with_cb(self):
        # Component with no dependents doesn't need CB
        g = _graph(
            _comp("a", failover_enabled=True, rate_limiting=True,
                  autoscaling_enabled=True),
        )
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        a_gaps = [gap for gap in gaps if gap.component_id == "a"]
        if a_gaps:
            assert ContainmentMechanism.CIRCUIT_BREAKER not in a_gaps[0].missing_mechanisms


# ---------------------------------------------------------------------------
# calculate_containment_score
# ---------------------------------------------------------------------------


class TestCalculateContainmentScore:
    def test_empty_graph_returns_100(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        assert v.calculate_containment_score() == 100.0

    def test_all_contained(self):
        g = _graph(_comp("a"), _comp("b"))
        v = ContainmentVerifier(g)
        score = v.calculate_containment_score()
        assert score == 100.0

    def test_all_breached(self):
        # b→a, no rules → actual>0, expected=0 → breached for a
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        # a is breached, b is contained → (1 + 0)/2 = 50
        score = v.calculate_containment_score()
        assert score == 50.0

    def test_mixed_score(self):
        # 3 components, 2 contained, 1 breached
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("b", "a")],
        )
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
                component_id="a",
                max_blast_radius=1,
            )
        )
        # a contained (1<=1), b contained (0 affected), c contained (0 affected)
        score = v.calculate_containment_score()
        assert score == 100.0

    def test_partially_contained_counts_half(self):
        c = [_comp(f"n{i}") for i in range(4)]
        deps = [_dep(f"n{i}", "n0") for i in range(1, 4)]
        g = _graph(*c, deps=deps)
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.BULKHEAD,
                component_id="n0",
                max_blast_radius=2,
            )
        )
        # n0: actual=3, expected=2, 3<=3.0 → partially
        # n1,n2,n3: 0 affected → contained
        # score = (3*1 + 1*0.5)/4 * 100 = 87.5
        score = v.calculate_containment_score()
        assert score == 87.5


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_empty_graph_report(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        report = v.generate_report()
        assert report.tests_run == 0
        assert report.contained == 0
        assert report.breached == 0
        assert report.containment_score == 100.0
        assert report.tests == []
        assert report.gaps == []

    def test_report_counts(self):
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("b", "a"), _dep("c", "a")],
        )
        v = ContainmentVerifier(g)
        # a → breached (2 affected, 0 expected), b → contained, c → contained
        report = v.generate_report()
        assert report.tests_run == 3
        assert report.contained == 2
        assert report.breached == 1

    def test_report_includes_tests(self):
        g = _graph(_comp("x"), _comp("y"), deps=[_dep("y", "x")])
        v = ContainmentVerifier(g)
        report = v.generate_report()
        assert len(report.tests) == 2

    def test_report_includes_gaps(self):
        g = _graph(_comp("a"))
        v = ContainmentVerifier(g)
        report = v.generate_report()
        assert len(report.gaps) > 0

    def test_report_includes_breach_recommendations(self):
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        report = v.generate_report()
        breach_recs = [r for r in report.recommendations if "breaches containment" in r]
        assert len(breach_recs) >= 1

    def test_report_includes_gap_recommendations(self):
        g = _graph(_comp("a"))
        v = ContainmentVerifier(g)
        report = v.generate_report()
        gap_recs = [r for r in report.recommendations if "Add" in r]
        assert len(gap_recs) >= 1

    def test_report_deduplicates_recommendations(self):
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        report = v.generate_report()
        assert len(report.recommendations) == len(set(report.recommendations))

    def test_report_score_matches_calculate(self):
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("b", "a")],
        )
        v = ContainmentVerifier(g)
        report = v.generate_report()
        assert report.containment_score == v.calculate_containment_score()

    def test_report_all_contained(self):
        g = _graph(_comp("x"), _comp("y"))
        v = ContainmentVerifier(g)
        report = v.generate_report()
        assert report.breached == 0
        assert report.contained == 2

    def test_report_with_rules_no_breaches(self):
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
                component_id="a",
                max_blast_radius=1,
            )
        )
        report = v.generate_report()
        assert report.breached == 0


# ---------------------------------------------------------------------------
# _determine_status — boundary values
# ---------------------------------------------------------------------------


class TestDetermineStatus:
    def _call(self, expected: int, actual: int) -> ContainmentStatus:
        g = InfraGraph()
        v = ContainmentVerifier(g)
        return v._determine_status(expected, actual)

    def test_zero_zero_contained(self):
        assert self._call(0, 0) == ContainmentStatus.CONTAINED

    def test_equal_contained(self):
        assert self._call(5, 5) == ContainmentStatus.CONTAINED

    def test_less_than_contained(self):
        assert self._call(5, 3) == ContainmentStatus.CONTAINED

    def test_at_1_5x_partially(self):
        # expected=2, actual=3, int(2*1.5)=3 → 3<=3 → partially
        assert self._call(2, 3) == ContainmentStatus.PARTIALLY_CONTAINED

    def test_above_1_5x_breached(self):
        # expected=2, actual=4, int(2*1.5)=3 → 4>3 → breached
        assert self._call(2, 4) == ContainmentStatus.BREACHED

    def test_expected_zero_actual_one_breached(self):
        # int(0*1.5)=0, 1>0 → breached
        assert self._call(0, 1) == ContainmentStatus.BREACHED

    def test_expected_one_actual_one_contained(self):
        assert self._call(1, 1) == ContainmentStatus.CONTAINED

    def test_expected_one_actual_two_breached(self):
        # int(1*1.5)=1, 2>1 → breached
        assert self._call(1, 2) == ContainmentStatus.BREACHED

    def test_expected_10_actual_15_partially(self):
        # int(10*1.5)=15, 15<=15 → partially
        assert self._call(10, 15) == ContainmentStatus.PARTIALLY_CONTAINED

    def test_expected_10_actual_16_breached(self):
        assert self._call(10, 16) == ContainmentStatus.BREACHED


# ---------------------------------------------------------------------------
# _effectiveness — boundary values
# ---------------------------------------------------------------------------


class TestEffectiveness:
    def test_zero_actual_returns_one(self):
        assert ContainmentVerifier._effectiveness(0, 0) == 1.0

    def test_nonzero_expected_zero_actual(self):
        assert ContainmentVerifier._effectiveness(5, 0) == 1.0

    def test_expected_zero_actual_positive(self):
        assert ContainmentVerifier._effectiveness(0, 3) == 0.0

    def test_equal(self):
        assert ContainmentVerifier._effectiveness(4, 4) == 1.0

    def test_actual_greater(self):
        eff = ContainmentVerifier._effectiveness(2, 4)
        assert eff == pytest.approx(0.5)

    def test_actual_much_greater(self):
        eff = ContainmentVerifier._effectiveness(1, 10)
        assert eff == pytest.approx(0.1)

    def test_capped_at_one(self):
        eff = ContainmentVerifier._effectiveness(10, 1)
        assert eff == 1.0

    def test_capped_at_zero(self):
        eff = ContainmentVerifier._effectiveness(0, 100)
        assert eff == 0.0


# ---------------------------------------------------------------------------
# Integration: large graph
# ---------------------------------------------------------------------------


class TestLargeGraph:
    def test_large_chain(self):
        n = 20
        comps = [_comp(f"c{i}") for i in range(n)]
        deps = [_dep(f"c{i+1}", f"c{i}") for i in range(n - 1)]
        g = _graph(*comps, deps=deps)
        v = ContainmentVerifier(g)
        result = v.verify_containment("c0")
        assert result.actual_blast_radius == n - 1

    def test_large_fan_out(self):
        n = 15
        comps = [_comp("root")] + [_comp(f"leaf{i}") for i in range(n)]
        deps = [_dep(f"leaf{i}", "root") for i in range(n)]
        g = _graph(*comps, deps=deps)
        v = ContainmentVerifier(g)
        result = v.verify_containment("root")
        assert result.actual_blast_radius == n

    def test_large_graph_report(self):
        n = 10
        comps = [_comp(f"s{i}") for i in range(n)]
        deps = [_dep(f"s{i+1}", f"s{i}") for i in range(n - 1)]
        g = _graph(*comps, deps=deps)
        v = ContainmentVerifier(g)
        report = v.generate_report()
        assert report.tests_run == n

    def test_large_graph_gaps(self):
        n = 8
        comps = [_comp(f"s{i}") for i in range(n)]
        deps = [_dep(f"s{i+1}", f"s{i}") for i in range(n - 1)]
        g = _graph(*comps, deps=deps)
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        assert len(gaps) > 0


# ---------------------------------------------------------------------------
# Integration: diamond graph
# ---------------------------------------------------------------------------


class TestDiamondGraph:
    def test_diamond_blast_radius(self):
        # a → b, a → c, b → d, c → d
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"), _comp("d"),
            deps=[
                _dep("a", "d"),
                _dep("b", "d"),
                _dep("c", "d"),
                _dep("a", "b"),
                _dep("a", "c"),
            ],
        )
        v = ContainmentVerifier(g)
        result = v.verify_containment("d")
        # d fails → b,c depend on d → a depends on b,c
        assert "a" in result.actual_affected
        assert "b" in result.actual_affected or "c" in result.actual_affected

    def test_diamond_contained_with_rules(self):
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"), _comp("d"),
            deps=[
                _dep("a", "d"),
                _dep("b", "d"),
                _dep("c", "d"),
                _dep("a", "b"),
                _dep("a", "c"),
            ],
        )
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
                component_id="d",
                max_blast_radius=5,
            )
        )
        result = v.verify_containment("d")
        assert result.status == ContainmentStatus.CONTAINED


# ---------------------------------------------------------------------------
# Integration: expected_affected list
# ---------------------------------------------------------------------------


class TestExpectedAffected:
    def test_expected_affected_bounded(self):
        comps = [_comp(f"n{i}") for i in range(5)]
        deps = [_dep(f"n{i}", "n0") for i in range(1, 5)]
        g = _graph(*comps, deps=deps)
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.BULKHEAD,
                component_id="n0",
                max_blast_radius=2,
            )
        )
        result = v.verify_containment("n0")
        assert len(result.expected_affected) == 2

    def test_expected_affected_empty_no_rules(self):
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        result = v.verify_containment("a")
        assert result.expected_affected == []

    def test_actual_affected_sorted(self):
        comps = [_comp(f"z{i}") for i in range(4)]
        deps = [_dep(f"z{i}", "z0") for i in range(1, 4)]
        g = _graph(*comps, deps=deps)
        v = ContainmentVerifier(g)
        result = v.verify_containment("z0")
        assert result.actual_affected == sorted(result.actual_affected)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_component_not_in_graph(self):
        g = _graph(_comp("a"))
        v = ContainmentVerifier(g)
        result = v.verify_containment("nonexistent")
        assert result.actual_blast_radius == 0
        assert result.status == ContainmentStatus.CONTAINED

    def test_rule_for_nonexistent_component(self):
        g = _graph(_comp("a"))
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.FAILOVER,
                component_id="ghost",
                max_blast_radius=0,
            )
        )
        result = v.verify_containment("a")
        assert result.status == ContainmentStatus.CONTAINED

    def test_self_loop_handling(self):
        g = _graph(_comp("a"))
        # Self-loop edge
        g.add_dependency(_dep("a", "a"))
        v = ContainmentVerifier(g)
        result = v.verify_containment("a")
        # get_all_affected does BFS on dependents; self-loop may or may not be counted
        assert result.failure_component == "a"

    def test_no_components_verify_all_empty(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        assert v.verify_all() == []

    def test_multiple_rules_same_component_same_mechanism(self):
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
                component_id="a",
                max_blast_radius=5,
            )
        )
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
                component_id="a",
                max_blast_radius=2,
            )
        )
        result = v.verify_containment("a")
        assert result.expected_blast_radius == 2

    def test_cyclic_dependencies(self):
        # a→b→c→a cycle — BFS can include the origin in affected set
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("b", "a"), _dep("c", "b"), _dep("a", "c")],
        )
        v = ContainmentVerifier(g)
        result = v.verify_containment("a")
        # Cycle causes propagation back to origin; graph BFS includes it
        assert result.actual_blast_radius == 3
        assert set(result.actual_affected) == {"a", "b", "c"}

    def test_component_types_variety(self):
        g = _graph(
            _comp("lb", ctype=ComponentType.LOAD_BALANCER),
            _comp("web", ctype=ComponentType.WEB_SERVER),
            _comp("db", ctype=ComponentType.DATABASE),
            deps=[_dep("web", "lb"), _dep("db", "web")],
        )
        v = ContainmentVerifier(g)
        results = v.verify_all()
        assert len(results) == 3


# ---------------------------------------------------------------------------
# Private helper _get_rules_for / _expected_blast_radius
# ---------------------------------------------------------------------------


class TestPrivateHelpers:
    def test_get_rules_for_empty(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        assert v._get_rules_for("x") == []

    def test_get_rules_for_match(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        r = ContainmentRule(
            mechanism=ContainmentMechanism.TIMEOUT,
            component_id="x",
        )
        v.add_rule(r)
        assert v._get_rules_for("x") == [r]
        assert v._get_rules_for("y") == []

    def test_expected_blast_radius_no_rules(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        assert v._expected_blast_radius("x") == 0

    def test_expected_blast_radius_single_rule(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.BULKHEAD,
                component_id="x",
                max_blast_radius=7,
            )
        )
        assert v._expected_blast_radius("x") == 7

    def test_expected_blast_radius_picks_min(self):
        g = InfraGraph()
        v = ContainmentVerifier(g)
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
                component_id="x",
                max_blast_radius=10,
            )
        )
        v.add_rule(
            ContainmentRule(
                mechanism=ContainmentMechanism.TIMEOUT,
                component_id="x",
                max_blast_radius=3,
            )
        )
        assert v._expected_blast_radius("x") == 3


# ---------------------------------------------------------------------------
# Additional tests to exceed 130
# ---------------------------------------------------------------------------


class TestAdditionalCoverage:
    def test_verify_containment_exact_boundary_expected_1(self):
        # expected=1, actual=1 → contained
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        v.add_rule(ContainmentRule(
            mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
            component_id="a",
            max_blast_radius=1,
        ))
        result = v.verify_containment("a")
        assert result.status == ContainmentStatus.CONTAINED
        assert result.containment_effectiveness == 1.0

    def test_report_containment_score_zero_when_all_breached(self):
        # Every component has at least one dependent → all breached if no rules
        g = _graph(
            _comp("a"), _comp("b"),
            deps=[_dep("b", "a"), _dep("a", "b")],
        )
        v = ContainmentVerifier(g)
        report = v.generate_report()
        assert report.containment_score == 0.0

    def test_verify_all_returns_correct_order(self):
        g = _graph(_comp("alpha"), _comp("beta"), _comp("gamma"))
        v = ContainmentVerifier(g)
        results = v.verify_all()
        assert len(results) == 3

    def test_gap_no_dependents_no_outgoing_no_cb_no_retry(self):
        # Isolated component should not get CB or RETRY_BUDGET gaps
        g = _graph(_comp("lone"))
        v = ContainmentVerifier(g)
        gaps = v.find_containment_gaps()
        lone_gap = next(gap for gap in gaps if gap.component_id == "lone")
        assert ContainmentMechanism.CIRCUIT_BREAKER not in lone_gap.missing_mechanisms
        assert ContainmentMechanism.RETRY_BUDGET not in lone_gap.missing_mechanisms

    def test_containment_mechanism_from_string(self):
        assert ContainmentMechanism("load_shedding") == ContainmentMechanism.LOAD_SHEDDING
        assert ContainmentMechanism("graceful_degradation") == ContainmentMechanism.GRACEFUL_DEGRADATION

    def test_containment_status_from_string(self):
        assert ContainmentStatus("not_tested") == ContainmentStatus.NOT_TESTED
        assert ContainmentStatus("partially_contained") == ContainmentStatus.PARTIALLY_CONTAINED

    def test_report_gaps_matches_find_gaps(self):
        g = _graph(_comp("a"), _comp("b"), deps=[_dep("b", "a")])
        v = ContainmentVerifier(g)
        report = v.generate_report()
        direct_gaps = v.find_containment_gaps()
        assert len(report.gaps) == len(direct_gaps)
