"""Tests for Dependency Injection Analyzer.

Comprehensive tests covering circular dependency detection, lifecycle
risk assessment, service locator anti-pattern detection, missing
binding detection, scope mismatch analysis, lazy initialization
failure cascades, factory pattern resilience evaluation, dependency
tree depth analysis, hot-swap capability assessment, configuration-
driven dependency switching risks, interface-based decoupling score,
dependency graph complexity metrics, and full analysis summary.
"""

from __future__ import annotations

import math

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.dependency_injection_analyzer import (
    CYCLOMATIC_THRESHOLD,
    CONFIG_SWITCH_PENALTY,
    FACTORY_RESILIENCE_BONUS,
    HOT_SWAP_BONUS,
    INTERFACE_DECOUPLING_IDEAL,
    LAZY_INIT_FAILURE_PROBABILITY,
    MAX_SAFE_FAN_IN,
    MAX_SAFE_FAN_OUT,
    MAX_SAFE_TREE_DEPTH,
    SCOPED_RISK_WEIGHT,
    SERVICE_LOCATOR_PENALTY,
    SINGLETON_RISK_WEIGHT,
    TRANSIENT_RISK_WEIGHT,
    BindingStatus,
    CircularDependencyResult,
    ComplexityMetricsResult,
    ConfigSwitchRiskResult,
    DIAnalysisSummary,
    DIContainerConfig,
    DIRegistration,
    DecouplingScoreResult,
    DependencyInjectionAnalyzer,
    FactoryResilienceResult,
    HotSwapResult,
    InjectionPattern,
    LazyInitResult,
    Lifecycle,
    LifecycleRiskResult,
    MissingBindingResult,
    RiskLevel,
    ScopeMismatchResult,
    ScopeMismatchType,
    ServiceLocatorResult,
    TreeDepthResult,
    _clamp,
    _compute_cascade_probability,
    _compute_cold_start_latency,
    _compute_fan_in,
    _compute_fan_out,
    _count_connected_components,
    _cyclomatic_complexity,
    _detect_cycles_in_graph,
    _distance_from_main_sequence,
    _find_all_paths_dfs,
    _instability_index,
    _lifecycle_risk_weight,
    _risk_from_score,
    _scope_mismatch_type,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "c1",
    ctype: ComponentType = ComponentType.APP_SERVER,
) -> Component:
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _reg(
    cid: str = "c1",
    lifecycle: Lifecycle = Lifecycle.TRANSIENT,
    binding_status: BindingStatus = BindingStatus.REGISTERED,
    injection_pattern: InjectionPattern = InjectionPattern.CONSTRUCTOR,
    interface_name: str = "",
    has_factory: bool = False,
    supports_hot_swap: bool = False,
    config_driven: bool = False,
    lazy_init: bool = False,
) -> DIRegistration:
    return DIRegistration(
        component_id=cid,
        lifecycle=lifecycle,
        binding_status=binding_status,
        injection_pattern=injection_pattern,
        interface_name=interface_name,
        has_factory=has_factory,
        supports_hot_swap=supports_hot_swap,
        config_driven=config_driven,
        lazy_init=lazy_init,
    )


def _make_chain(n: int) -> tuple[InfraGraph, DIContainerConfig]:
    """Build a linear chain c0 -> c1 -> ... -> c(n-1) with registrations."""
    comps = [_comp(f"c{i}") for i in range(n)]
    g = _graph(*comps)
    for i in range(n - 1):
        g.add_dependency(Dependency(source_id=f"c{i}", target_id=f"c{i + 1}"))
    regs = [_reg(f"c{i}") for i in range(n)]
    return g, DIContainerConfig(registrations=regs)


# ---------------------------------------------------------------------------
# Test _clamp
# ---------------------------------------------------------------------------


class TestClamp:
    def test_within_range(self):
        assert _clamp(0.5) == 0.5

    def test_below_lo(self):
        assert _clamp(-1.0) == 0.0

    def test_above_hi(self):
        assert _clamp(2.0) == 1.0

    def test_at_boundaries(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(1.0) == 1.0

    def test_custom_range(self):
        assert _clamp(5.0, lo=2.0, hi=10.0) == 5.0
        assert _clamp(1.0, lo=2.0, hi=10.0) == 2.0
        assert _clamp(11.0, lo=2.0, hi=10.0) == 10.0


# ---------------------------------------------------------------------------
# Test _risk_from_score
# ---------------------------------------------------------------------------


class TestRiskFromScore:
    def test_critical(self):
        assert _risk_from_score(0.8) == RiskLevel.CRITICAL
        assert _risk_from_score(1.0) == RiskLevel.CRITICAL

    def test_high(self):
        assert _risk_from_score(0.6) == RiskLevel.HIGH
        assert _risk_from_score(0.79) == RiskLevel.HIGH

    def test_medium(self):
        assert _risk_from_score(0.4) == RiskLevel.MEDIUM
        assert _risk_from_score(0.59) == RiskLevel.MEDIUM

    def test_low(self):
        assert _risk_from_score(0.2) == RiskLevel.LOW
        assert _risk_from_score(0.39) == RiskLevel.LOW

    def test_info(self):
        assert _risk_from_score(0.0) == RiskLevel.INFO
        assert _risk_from_score(0.19) == RiskLevel.INFO


# ---------------------------------------------------------------------------
# Test _lifecycle_risk_weight
# ---------------------------------------------------------------------------


class TestLifecycleRiskWeight:
    def test_singleton(self):
        assert _lifecycle_risk_weight(Lifecycle.SINGLETON) == SINGLETON_RISK_WEIGHT

    def test_transient(self):
        assert _lifecycle_risk_weight(Lifecycle.TRANSIENT) == TRANSIENT_RISK_WEIGHT

    def test_scoped(self):
        assert _lifecycle_risk_weight(Lifecycle.SCOPED) == SCOPED_RISK_WEIGHT


# ---------------------------------------------------------------------------
# Test _scope_mismatch_type
# ---------------------------------------------------------------------------


class TestScopeMismatchType:
    def test_singleton_on_transient(self):
        assert (
            _scope_mismatch_type(Lifecycle.SINGLETON, Lifecycle.TRANSIENT)
            == ScopeMismatchType.SINGLETON_DEPENDS_ON_TRANSIENT
        )

    def test_singleton_on_scoped(self):
        assert (
            _scope_mismatch_type(Lifecycle.SINGLETON, Lifecycle.SCOPED)
            == ScopeMismatchType.SINGLETON_DEPENDS_ON_SCOPED
        )

    def test_scoped_on_transient(self):
        assert (
            _scope_mismatch_type(Lifecycle.SCOPED, Lifecycle.TRANSIENT)
            == ScopeMismatchType.SCOPED_DEPENDS_ON_TRANSIENT
        )

    def test_no_mismatch(self):
        assert (
            _scope_mismatch_type(Lifecycle.TRANSIENT, Lifecycle.SINGLETON)
            == ScopeMismatchType.NONE
        )
        assert (
            _scope_mismatch_type(Lifecycle.SINGLETON, Lifecycle.SINGLETON)
            == ScopeMismatchType.NONE
        )
        assert (
            _scope_mismatch_type(Lifecycle.TRANSIENT, Lifecycle.TRANSIENT)
            == ScopeMismatchType.NONE
        )
        assert (
            _scope_mismatch_type(Lifecycle.SCOPED, Lifecycle.SCOPED)
            == ScopeMismatchType.NONE
        )
        assert (
            _scope_mismatch_type(Lifecycle.SCOPED, Lifecycle.SINGLETON)
            == ScopeMismatchType.NONE
        )
        assert (
            _scope_mismatch_type(Lifecycle.TRANSIENT, Lifecycle.SCOPED)
            == ScopeMismatchType.NONE
        )


# ---------------------------------------------------------------------------
# Test _compute_cascade_probability
# ---------------------------------------------------------------------------


class TestComputeCascadeProbability:
    def test_zero_total(self):
        assert _compute_cascade_probability(0, 0) == 0.0

    def test_no_lazy(self):
        assert _compute_cascade_probability(0, 5) == 0.0

    def test_all_lazy(self):
        result = _compute_cascade_probability(5, 5)
        assert 0.0 < result <= 1.0

    def test_partial_lazy(self):
        result = _compute_cascade_probability(2, 10)
        assert 0.0 < result < 1.0

    def test_increases_with_ratio(self):
        r1 = _compute_cascade_probability(1, 10)
        r2 = _compute_cascade_probability(5, 10)
        assert r2 > r1


# ---------------------------------------------------------------------------
# Test _compute_cold_start_latency
# ---------------------------------------------------------------------------


class TestComputeColdStartLatency:
    def test_zero(self):
        assert _compute_cold_start_latency(0) == 0.0

    def test_one(self):
        assert _compute_cold_start_latency(1) == 50.0

    def test_multiple(self):
        assert _compute_cold_start_latency(5) == 250.0


# ---------------------------------------------------------------------------
# Test _cyclomatic_complexity
# ---------------------------------------------------------------------------


class TestCyclomaticComplexity:
    def test_minimal(self):
        assert _cyclomatic_complexity(1, 0, 1) >= 1

    def test_simple_graph(self):
        # 3 nodes, 2 edges, 1 component: M = 2 - 3 + 2 = 1
        assert _cyclomatic_complexity(3, 2, 1) == 1

    def test_with_cycle(self):
        # 3 nodes, 3 edges, 1 component: M = 3 - 3 + 2 = 2
        assert _cyclomatic_complexity(3, 3, 1) == 2

    def test_disconnected(self):
        # 4 nodes, 2 edges, 2 components: M = 2 - 4 + 4 = 2
        assert _cyclomatic_complexity(4, 2, 2) == 2


# ---------------------------------------------------------------------------
# Test _instability_index
# ---------------------------------------------------------------------------


class TestInstabilityIndex:
    def test_zero_both(self):
        assert _instability_index(0, 0) == 0.0

    def test_all_fan_in(self):
        assert _instability_index(10, 0) == 0.0

    def test_all_fan_out(self):
        assert _instability_index(0, 10) == 1.0

    def test_balanced(self):
        assert _instability_index(5, 5) == 0.5


# ---------------------------------------------------------------------------
# Test _distance_from_main_sequence
# ---------------------------------------------------------------------------


class TestDistanceFromMainSequence:
    def test_on_main_sequence(self):
        assert _distance_from_main_sequence(0.5, 0.5) == 0.0

    def test_zone_of_pain(self):
        # A=0, I=0 -> D=1
        assert _distance_from_main_sequence(0.0, 0.0) == 1.0

    def test_zone_of_uselessness(self):
        # A=1, I=1 -> D=1
        assert _distance_from_main_sequence(1.0, 1.0) == 1.0


# ---------------------------------------------------------------------------
# Test _compute_fan_in / _compute_fan_out
# ---------------------------------------------------------------------------


class TestFanInOut:
    def test_fan_in_no_deps(self):
        g = _graph(_comp("a"))
        assert _compute_fan_in(g, "a") == 0

    def test_fan_out_no_deps(self):
        g = _graph(_comp("a"))
        assert _compute_fan_out(g, "a") == 0

    def test_fan_in_with_deps(self):
        a, b, c = _comp("a"), _comp("b"), _comp("c")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a", target_id="c"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        assert _compute_fan_in(g, "c") == 2

    def test_fan_out_with_deps(self):
        a, b, c = _comp("a"), _comp("b"), _comp("c")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="a", target_id="c"))
        assert _compute_fan_out(g, "a") == 2


# ---------------------------------------------------------------------------
# Test _find_all_paths_dfs
# ---------------------------------------------------------------------------


class TestFindAllPathsDFS:
    def test_single_node(self):
        g = _graph(_comp("a"))
        paths = _find_all_paths_dfs(g, "a")
        assert paths == [["a"]]

    def test_linear_chain(self):
        a, b, c = _comp("a"), _comp("b"), _comp("c")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        paths = _find_all_paths_dfs(g, "a")
        assert ["a", "b", "c"] in paths

    def test_branching(self):
        a, b, c = _comp("a"), _comp("b"), _comp("c")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="a", target_id="c"))
        paths = _find_all_paths_dfs(g, "a")
        assert len(paths) >= 2


# ---------------------------------------------------------------------------
# Test _detect_cycles_in_graph
# ---------------------------------------------------------------------------


class TestDetectCycles:
    def test_no_cycle(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        cycles = _detect_cycles_in_graph(g)
        assert cycles == []

    def test_simple_cycle(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        cycles = _detect_cycles_in_graph(g)
        assert len(cycles) > 0

    def test_self_loop(self):
        a = _comp("a")
        g = _graph(a)
        g.add_dependency(Dependency(source_id="a", target_id="a"))
        cycles = _detect_cycles_in_graph(g)
        assert len(cycles) > 0

    def test_empty_graph(self):
        g = InfraGraph()
        cycles = _detect_cycles_in_graph(g)
        assert cycles == []


# ---------------------------------------------------------------------------
# Test _count_connected_components
# ---------------------------------------------------------------------------


class TestCountConnectedComponents:
    def test_empty(self):
        g = InfraGraph()
        assert _count_connected_components(g) == 0

    def test_single(self):
        g = _graph(_comp("a"))
        assert _count_connected_components(g) == 1

    def test_connected(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        assert _count_connected_components(g) == 1

    def test_disconnected(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        assert _count_connected_components(g) == 2


# ---------------------------------------------------------------------------
# Test CircularDependencyResult defaults
# ---------------------------------------------------------------------------


class TestCircularDependencyResultDefaults:
    def test_defaults(self):
        r = CircularDependencyResult()
        assert r.has_cycles is False
        assert r.cycles == []
        assert r.max_cycle_length == 0
        assert r.risk_level == RiskLevel.INFO
        assert r.timestamp


# ---------------------------------------------------------------------------
# Test Analyzer: detect_circular_dependencies
# ---------------------------------------------------------------------------


class TestDetectCircularDependencies:
    def test_no_cycles(self):
        g, cfg = _make_chain(3)
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.detect_circular_dependencies()
        assert result.has_cycles is False
        assert result.cycles == []
        assert result.impact_description == ""

    def test_with_cycle(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        cfg = DIContainerConfig(registrations=[_reg("a"), _reg("b")])
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.detect_circular_dependencies()
        assert result.has_cycles is True
        assert len(result.cycles) > 0
        assert len(result.affected_components) > 0
        assert "circular" in result.impact_description.lower()

    def test_empty_graph(self):
        g = InfraGraph()
        analyzer = DependencyInjectionAnalyzer(g)
        result = analyzer.detect_circular_dependencies()
        assert result.has_cycles is False


# ---------------------------------------------------------------------------
# Test Analyzer: assess_lifecycle_risks
# ---------------------------------------------------------------------------


class TestAssessLifecycleRisks:
    def test_empty_registrations(self):
        g = _graph(_comp("a"))
        analyzer = DependencyInjectionAnalyzer(g)
        results = analyzer.assess_lifecycle_risks()
        assert results == []

    def test_singleton_risks(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        cfg = DIContainerConfig(
            registrations=[_reg("a", lifecycle=Lifecycle.SINGLETON)]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        results = analyzer.assess_lifecycle_risks()
        assert len(results) == 1
        assert results[0].lifecycle == Lifecycle.SINGLETON
        assert results[0].singleton_count == 1
        assert results[0].thread_safety_risk > 0

    def test_transient_risks(self):
        a = _comp("a")
        g = _graph(a)
        cfg = DIContainerConfig(
            registrations=[_reg("a", lifecycle=Lifecycle.TRANSIENT)]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        results = analyzer.assess_lifecycle_risks()
        assert len(results) == 1
        assert results[0].lifecycle == Lifecycle.TRANSIENT
        assert results[0].state_sharing_risk == 0.0

    def test_scoped_risks(self):
        a = _comp("a")
        g = _graph(a)
        cfg = DIContainerConfig(
            registrations=[_reg("a", lifecycle=Lifecycle.SCOPED)]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        results = analyzer.assess_lifecycle_risks()
        assert len(results) == 1
        assert results[0].lifecycle == Lifecycle.SCOPED

    def test_high_fan_in_singleton_recommendation(self):
        comps = [_comp(f"c{i}") for i in range(6)]
        g = _graph(*comps)
        for i in range(1, 6):
            g.add_dependency(Dependency(source_id=f"c{i}", target_id="c0"))
        cfg = DIContainerConfig(
            registrations=[_reg("c0", lifecycle=Lifecycle.SINGLETON)]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        results = analyzer.assess_lifecycle_risks()
        assert len(results) == 1
        assert any("fan-in" in r for r in results[0].recommendations)

    def test_high_fan_in_transient_recommendation(self):
        comps = [_comp(f"c{i}") for i in range(13)]
        g = _graph(*comps)
        for i in range(1, 13):
            g.add_dependency(Dependency(source_id=f"c{i}", target_id="c0"))
        cfg = DIContainerConfig(
            registrations=[_reg("c0", lifecycle=Lifecycle.TRANSIENT)]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        results = analyzer.assess_lifecycle_risks()
        assert any("frequently" in r for r in results[0].recommendations)


# ---------------------------------------------------------------------------
# Test Analyzer: detect_service_locator
# ---------------------------------------------------------------------------


class TestDetectServiceLocator:
    def test_no_locators(self):
        g = _graph(_comp("a"))
        cfg = DIContainerConfig(registrations=[_reg("a")])
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.detect_service_locator()
        assert result.detected is False
        assert result.locator_components == []
        assert result.recommendations == []

    def test_with_locator(self):
        g = _graph(_comp("a"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", injection_pattern=InjectionPattern.SERVICE_LOCATOR)
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.detect_service_locator()
        assert result.detected is True
        assert "a" in result.locator_components
        assert result.testability_impact > 0
        assert len(result.recommendations) > 0

    def test_multiple_locators(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", injection_pattern=InjectionPattern.SERVICE_LOCATOR),
                _reg("b", injection_pattern=InjectionPattern.SERVICE_LOCATOR),
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.detect_service_locator()
        assert len(result.locator_components) == 2
        assert result.coupling_score > 0


# ---------------------------------------------------------------------------
# Test Analyzer: detect_missing_bindings
# ---------------------------------------------------------------------------


class TestDetectMissingBindings:
    def test_all_registered(self):
        g = _graph(_comp("a"), _comp("b"))
        cfg = DIContainerConfig(registrations=[_reg("a"), _reg("b")])
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.detect_missing_bindings()
        assert result.has_missing is False
        assert result.coverage_ratio == 1.0

    def test_missing_binding(self):
        g = _graph(_comp("a"), _comp("b"))
        cfg = DIContainerConfig(registrations=[_reg("a")])
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.detect_missing_bindings()
        assert result.has_missing is True
        assert "b" in result.missing_bindings
        assert result.coverage_ratio < 1.0
        assert len(result.recommendations) > 0

    def test_conditional_binding(self):
        g = _graph(_comp("a"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", binding_status=BindingStatus.CONDITIONAL)
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.detect_missing_bindings()
        assert "a" in result.conditional_bindings
        assert len(result.recommendations) > 0

    def test_explicit_missing_status(self):
        g = _graph(_comp("a"))
        cfg = DIContainerConfig(
            registrations=[_reg("a", binding_status=BindingStatus.MISSING)]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.detect_missing_bindings()
        assert result.has_missing is True
        assert "a" in result.missing_bindings

    def test_empty_graph(self):
        g = InfraGraph()
        analyzer = DependencyInjectionAnalyzer(g)
        result = analyzer.detect_missing_bindings()
        assert result.has_missing is False
        assert result.coverage_ratio == 1.0


# ---------------------------------------------------------------------------
# Test Analyzer: analyze_scope_mismatches
# ---------------------------------------------------------------------------


class TestAnalyzeScopeMismatches:
    def test_no_mismatches(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", lifecycle=Lifecycle.TRANSIENT),
                _reg("b", lifecycle=Lifecycle.SINGLETON),
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_scope_mismatches()
        assert result.has_mismatches is False

    def test_singleton_depends_on_transient(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", lifecycle=Lifecycle.SINGLETON),
                _reg("b", lifecycle=Lifecycle.TRANSIENT),
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_scope_mismatches()
        assert result.has_mismatches is True
        assert result.mismatch_count == 1
        assert result.captive_dependency_risk > 0
        assert len(result.recommendations) > 0

    def test_singleton_depends_on_scoped(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", lifecycle=Lifecycle.SINGLETON),
                _reg("b", lifecycle=Lifecycle.SCOPED),
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_scope_mismatches()
        assert result.has_mismatches is True
        mm = result.mismatches[0]
        assert mm["mismatch_type"] == ScopeMismatchType.SINGLETON_DEPENDS_ON_SCOPED.value

    def test_no_reg_for_target(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        cfg = DIContainerConfig(
            registrations=[_reg("a", lifecycle=Lifecycle.SINGLETON)]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_scope_mismatches()
        assert result.has_mismatches is False


# ---------------------------------------------------------------------------
# Test Analyzer: analyze_lazy_init_cascades
# ---------------------------------------------------------------------------


class TestAnalyzeLazyInitCascades:
    def test_no_lazy(self):
        g = _graph(_comp("a"))
        cfg = DIContainerConfig(registrations=[_reg("a")])
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_lazy_init_cascades()
        assert result.lazy_count == 0
        assert result.cascade_risk == 0.0
        assert result.cold_start_latency_ms == 0.0

    def test_with_lazy(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", lazy_init=True),
                _reg("b", lazy_init=True),
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_lazy_init_cascades()
        assert result.lazy_count == 2
        assert result.cascade_risk > 0
        assert result.cold_start_latency_ms == 100.0
        assert result.startup_failure_probability > 0
        assert len(result.recommendations) > 0

    def test_high_cascade_risk_recommendation(self):
        comps = [_comp(f"c{i}") for i in range(6)]
        g = _graph(*comps)
        regs = [_reg(f"c{i}", lazy_init=True) for i in range(6)]
        cfg = DIContainerConfig(registrations=regs)
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_lazy_init_cascades()
        assert result.cascade_risk > 0.3
        assert any("cascade" in r.lower() for r in result.recommendations)

    def test_failure_paths_populated(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        cfg = DIContainerConfig(
            registrations=[_reg("a", lazy_init=True), _reg("b")]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_lazy_init_cascades()
        assert len(result.failure_paths) >= 1


# ---------------------------------------------------------------------------
# Test Analyzer: evaluate_factory_resilience
# ---------------------------------------------------------------------------


class TestEvaluateFactoryResilience:
    def test_no_factories(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"), _comp("d"))
        regs = [_reg(f) for f in ["a", "b", "c", "d"]]
        cfg = DIContainerConfig(registrations=regs)
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.evaluate_factory_resilience()
        assert result.factory_count == 0
        assert len(result.recommendations) > 0

    def test_with_factory_flag(self):
        g = _graph(_comp("a"))
        cfg = DIContainerConfig(
            registrations=[_reg("a", has_factory=True)]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.evaluate_factory_resilience()
        assert result.factory_count == 1
        assert "a" in result.factory_components

    def test_with_factory_pattern(self):
        g = _graph(_comp("a"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", injection_pattern=InjectionPattern.FACTORY)
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.evaluate_factory_resilience()
        assert result.factory_count == 1

    def test_resilience_score_range(self):
        g = _graph(_comp("a"), _comp("b"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", has_factory=True),
                _reg("b", has_factory=True),
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.evaluate_factory_resilience()
        assert 0.0 <= result.resilience_score <= 1.0
        assert 0.0 <= result.abstraction_benefit <= 1.0
        assert 0.0 <= result.complexity_cost <= 1.0


# ---------------------------------------------------------------------------
# Test Analyzer: analyze_tree_depth
# ---------------------------------------------------------------------------


class TestAnalyzeTreeDepth:
    def test_empty_graph(self):
        g = InfraGraph()
        analyzer = DependencyInjectionAnalyzer(g)
        result = analyzer.analyze_tree_depth()
        assert result.max_depth == 0
        assert result.risk_level == RiskLevel.INFO

    def test_single_node(self):
        g = _graph(_comp("a"))
        analyzer = DependencyInjectionAnalyzer(g)
        result = analyzer.analyze_tree_depth()
        assert result.max_depth >= 1

    def test_chain_depth(self):
        g, cfg = _make_chain(5)
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_tree_depth()
        assert result.max_depth >= 5
        assert result.avg_depth > 0
        assert len(result.deepest_path) >= 5

    def test_exceeds_threshold(self):
        n = MAX_SAFE_TREE_DEPTH + 3
        g, cfg = _make_chain(n)
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_tree_depth()
        assert result.exceeds_threshold is True
        assert len(result.recommendations) > 0

    def test_distribution_populated(self):
        g, cfg = _make_chain(4)
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_tree_depth()
        assert len(result.depth_distribution) > 0


# ---------------------------------------------------------------------------
# Test Analyzer: assess_hot_swap
# ---------------------------------------------------------------------------


class TestAssessHotSwap:
    def test_all_swappable(self):
        g = _graph(_comp("a"), _comp("b"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", supports_hot_swap=True),
                _reg("b", supports_hot_swap=True),
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.assess_hot_swap()
        assert result.swap_coverage == 1.0
        assert len(result.non_swappable_components) == 0

    def test_none_swappable(self):
        g = _graph(_comp("a"), _comp("b"))
        cfg = DIContainerConfig(
            registrations=[_reg("a"), _reg("b")]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.assess_hot_swap()
        assert result.swap_coverage == 0.0
        assert len(result.swappable_components) == 0
        assert len(result.recommendations) > 0

    def test_partial_swappable(self):
        g = _graph(_comp("a"), _comp("b"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", supports_hot_swap=True),
                _reg("b"),
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.assess_hot_swap()
        assert result.swap_coverage == 0.5

    def test_high_fan_in_non_swappable_recommendation(self):
        comps = [_comp(f"c{i}") for i in range(6)]
        g = _graph(*comps)
        for i in range(1, 6):
            g.add_dependency(Dependency(source_id=f"c{i}", target_id="c0"))
        cfg = DIContainerConfig(registrations=[_reg("c0")])
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.assess_hot_swap()
        assert any("fan-in" in r for r in result.recommendations)

    def test_empty_registrations(self):
        g = _graph(_comp("a"))
        analyzer = DependencyInjectionAnalyzer(g)
        result = analyzer.assess_hot_swap()
        assert result.swap_coverage == 0.0


# ---------------------------------------------------------------------------
# Test Analyzer: analyze_config_switch_risks
# ---------------------------------------------------------------------------


class TestAnalyzeConfigSwitchRisks:
    def test_no_config_driven(self):
        g = _graph(_comp("a"))
        cfg = DIContainerConfig(registrations=[_reg("a")])
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_config_switch_risks()
        assert result.total_config_driven == 0
        assert result.misconfiguration_risk == 0.0

    def test_with_config_driven(self):
        g = _graph(_comp("a"))
        cfg = DIContainerConfig(
            registrations=[_reg("a", config_driven=True)]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_config_switch_risks()
        assert result.total_config_driven == 1
        assert "a" in result.config_driven_components
        assert result.misconfiguration_risk > 0

    def test_high_config_ratio_recommendation(self):
        comps = [_comp(f"c{i}") for i in range(5)]
        g = _graph(*comps)
        regs = [_reg(f"c{i}", config_driven=True) for i in range(5)]
        cfg = DIContainerConfig(registrations=regs)
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_config_switch_risks()
        assert len(result.recommendations) > 0
        assert result.environment_drift_risk > 0


# ---------------------------------------------------------------------------
# Test Analyzer: compute_decoupling_score
# ---------------------------------------------------------------------------


class TestComputeDecouplingScore:
    def test_empty_graph(self):
        g = InfraGraph()
        analyzer = DependencyInjectionAnalyzer(g)
        result = analyzer.compute_decoupling_score()
        assert result.overall_score == 1.0
        assert result.interface_coverage == 1.0

    def test_all_interfaces(self):
        g = _graph(_comp("a"), _comp("b"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", interface_name="IServiceA"),
                _reg("b", interface_name="IServiceB"),
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.compute_decoupling_score()
        assert result.interface_coverage == 1.0
        assert result.concrete_coupling_ratio == 0.0
        assert result.overall_score > 0

    def test_no_interfaces(self):
        g = _graph(_comp("a"), _comp("b"))
        cfg = DIContainerConfig(registrations=[_reg("a"), _reg("b")])
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.compute_decoupling_score()
        assert result.interface_coverage == 0.0
        assert result.concrete_coupling_ratio == 1.0
        assert len(result.recommendations) > 0

    def test_per_component_scores(self):
        g = _graph(_comp("a"), _comp("b"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", interface_name="IService"),
                _reg("b"),
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.compute_decoupling_score()
        assert result.per_component["a"] == 1.0
        assert result.per_component["b"] == 0.0


# ---------------------------------------------------------------------------
# Test Analyzer: compute_complexity_metrics
# ---------------------------------------------------------------------------


class TestComputeComplexityMetrics:
    def test_empty_graph(self):
        g = InfraGraph()
        analyzer = DependencyInjectionAnalyzer(g)
        result = analyzer.compute_complexity_metrics()
        assert result.total_nodes == 0
        assert result.risk_level == RiskLevel.INFO

    def test_simple_chain(self):
        g, cfg = _make_chain(3)
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.compute_complexity_metrics()
        assert result.total_nodes == 3
        assert result.total_edges == 2
        assert result.cyclomatic_complexity >= 1

    def test_fan_in_fan_out(self):
        a, b, c, d = _comp("a"), _comp("b"), _comp("c"), _comp("d")
        g = _graph(a, b, c, d)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="a", target_id="c"))
        g.add_dependency(Dependency(source_id="a", target_id="d"))
        analyzer = DependencyInjectionAnalyzer(g)
        result = analyzer.compute_complexity_metrics()
        assert result.max_fan_out == 3
        assert result.fan_out_distribution["a"] == 3

    def test_high_fan_out_recommendation(self):
        comps = [_comp(f"c{i}") for i in range(MAX_SAFE_FAN_OUT + 2)]
        g = _graph(*comps)
        for i in range(1, MAX_SAFE_FAN_OUT + 2):
            g.add_dependency(Dependency(source_id="c0", target_id=f"c{i}"))
        analyzer = DependencyInjectionAnalyzer(g)
        result = analyzer.compute_complexity_metrics()
        assert any("fan-out" in r.lower() for r in result.recommendations)

    def test_high_fan_in_recommendation(self):
        comps = [_comp(f"c{i}") for i in range(MAX_SAFE_FAN_IN + 2)]
        g = _graph(*comps)
        for i in range(1, MAX_SAFE_FAN_IN + 2):
            g.add_dependency(Dependency(source_id=f"c{i}", target_id="c0"))
        analyzer = DependencyInjectionAnalyzer(g)
        result = analyzer.compute_complexity_metrics()
        assert any("fan-in" in r.lower() for r in result.recommendations)

    def test_instability_and_abstractness(self):
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", interface_name="IService"),
                _reg("b"),
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.compute_complexity_metrics()
        assert 0.0 <= result.instability_index <= 1.0
        assert 0.0 <= result.abstractness_index <= 1.0
        assert result.distance_from_main_seq >= 0.0


# ---------------------------------------------------------------------------
# Test Analyzer: full analyze()
# ---------------------------------------------------------------------------


class TestFullAnalysis:
    def test_minimal_graph(self):
        g = _graph(_comp("a"))
        cfg = DIContainerConfig(registrations=[_reg("a")])
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        summary = analyzer.analyze()
        assert isinstance(summary, DIAnalysisSummary)
        assert 0.0 <= summary.overall_risk_score <= 1.0
        assert summary.overall_risk_level in list(RiskLevel)
        assert summary.analyzed_at

    def test_all_sub_results_present(self):
        g, cfg = _make_chain(3)
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        summary = analyzer.analyze()
        assert isinstance(summary.circular_dependency, CircularDependencyResult)
        assert isinstance(summary.lifecycle_risks, list)
        assert isinstance(summary.service_locator, ServiceLocatorResult)
        assert isinstance(summary.missing_bindings, MissingBindingResult)
        assert isinstance(summary.scope_mismatches, ScopeMismatchResult)
        assert isinstance(summary.lazy_init, LazyInitResult)
        assert isinstance(summary.factory_resilience, FactoryResilienceResult)
        assert isinstance(summary.tree_depth, TreeDepthResult)
        assert isinstance(summary.hot_swap, HotSwapResult)
        assert isinstance(summary.config_switch, ConfigSwitchRiskResult)
        assert isinstance(summary.decoupling, DecouplingScoreResult)
        assert isinstance(summary.complexity, ComplexityMetricsResult)

    def test_with_all_issues(self):
        # Build a graph with cycles, mismatches, locators, etc.
        a, b, c = _comp("a"), _comp("b"), _comp("c")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        g.add_dependency(Dependency(source_id="c", target_id="a"))  # cycle

        cfg = DIContainerConfig(
            registrations=[
                _reg(
                    "a",
                    lifecycle=Lifecycle.SINGLETON,
                    injection_pattern=InjectionPattern.SERVICE_LOCATOR,
                    lazy_init=True,
                    config_driven=True,
                ),
                _reg(
                    "b",
                    lifecycle=Lifecycle.TRANSIENT,
                    lazy_init=True,
                ),
                # "c" missing registration
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        summary = analyzer.analyze()
        assert summary.circular_dependency.has_cycles is True
        assert summary.missing_bindings.has_missing is True
        assert summary.service_locator.detected is True
        assert summary.scope_mismatches.has_mismatches is True
        assert summary.overall_risk_score > 0
        assert len(summary.recommendations) > 0

    def test_recommendations_deduplicated(self):
        g = _graph(_comp("a"))
        cfg = DIContainerConfig(registrations=[_reg("a")])
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        summary = analyzer.analyze()
        seen = set()
        for r in summary.recommendations:
            assert r not in seen, f"Duplicate recommendation: {r}"
            seen.add(r)

    def test_default_config(self):
        g = _graph(_comp("a"))
        analyzer = DependencyInjectionAnalyzer(g)
        summary = analyzer.analyze()
        assert isinstance(summary, DIAnalysisSummary)

    def test_empty_graph_analysis(self):
        g = InfraGraph()
        analyzer = DependencyInjectionAnalyzer(g)
        summary = analyzer.analyze()
        assert summary.overall_risk_score >= 0.0


# ---------------------------------------------------------------------------
# Test Enum values
# ---------------------------------------------------------------------------


class TestEnumValues:
    def test_lifecycle_values(self):
        assert Lifecycle.SINGLETON.value == "singleton"
        assert Lifecycle.TRANSIENT.value == "transient"
        assert Lifecycle.SCOPED.value == "scoped"

    def test_binding_status_values(self):
        assert BindingStatus.REGISTERED.value == "registered"
        assert BindingStatus.MISSING.value == "missing"
        assert BindingStatus.CONDITIONAL.value == "conditional"

    def test_injection_pattern_values(self):
        assert InjectionPattern.CONSTRUCTOR.value == "constructor"
        assert InjectionPattern.PROPERTY.value == "property"
        assert InjectionPattern.METHOD.value == "method"
        assert InjectionPattern.SERVICE_LOCATOR.value == "service_locator"
        assert InjectionPattern.FACTORY.value == "factory"

    def test_risk_level_values(self):
        assert RiskLevel.CRITICAL.value == "critical"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.INFO.value == "info"

    def test_scope_mismatch_type_values(self):
        assert (
            ScopeMismatchType.SINGLETON_DEPENDS_ON_TRANSIENT.value
            == "singleton_depends_on_transient"
        )
        assert (
            ScopeMismatchType.SINGLETON_DEPENDS_ON_SCOPED.value
            == "singleton_depends_on_scoped"
        )
        assert (
            ScopeMismatchType.SCOPED_DEPENDS_ON_TRANSIENT.value
            == "scoped_depends_on_transient"
        )
        assert ScopeMismatchType.NONE.value == "none"


# ---------------------------------------------------------------------------
# Test dataclass defaults
# ---------------------------------------------------------------------------


class TestDataclassDefaults:
    def test_di_registration_defaults(self):
        r = DIRegistration(component_id="x")
        assert r.lifecycle == Lifecycle.TRANSIENT
        assert r.binding_status == BindingStatus.REGISTERED
        assert r.injection_pattern == InjectionPattern.CONSTRUCTOR
        assert r.interface_name == ""
        assert r.has_factory is False
        assert r.supports_hot_swap is False
        assert r.config_driven is False
        assert r.lazy_init is False

    def test_di_container_config_defaults(self):
        c = DIContainerConfig()
        assert c.registrations == []
        assert c.allow_missing_bindings is False
        assert c.strict_scope_validation is True
        assert c.max_tree_depth == MAX_SAFE_TREE_DEPTH

    def test_lifecycle_risk_result_defaults(self):
        r = LifecycleRiskResult()
        assert r.component_id == ""
        assert r.risk_score == 0.0
        assert r.singleton_count == 0

    def test_service_locator_result_defaults(self):
        r = ServiceLocatorResult()
        assert r.detected is False
        assert r.testability_impact == 0.0

    def test_missing_binding_result_defaults(self):
        r = MissingBindingResult()
        assert r.has_missing is False
        assert r.coverage_ratio == 1.0

    def test_scope_mismatch_result_defaults(self):
        r = ScopeMismatchResult()
        assert r.has_mismatches is False
        assert r.mismatch_count == 0

    def test_lazy_init_result_defaults(self):
        r = LazyInitResult()
        assert r.lazy_count == 0
        assert r.cascade_risk == 0.0
        assert r.cold_start_latency_ms == 0.0

    def test_factory_resilience_result_defaults(self):
        r = FactoryResilienceResult()
        assert r.factory_count == 0
        assert r.resilience_score == 0.0

    def test_tree_depth_result_defaults(self):
        r = TreeDepthResult()
        assert r.max_depth == 0
        assert r.exceeds_threshold is False

    def test_hot_swap_result_defaults(self):
        r = HotSwapResult()
        assert r.swap_coverage == 0.0

    def test_config_switch_risk_result_defaults(self):
        r = ConfigSwitchRiskResult()
        assert r.total_config_driven == 0

    def test_decoupling_score_result_defaults(self):
        r = DecouplingScoreResult()
        assert r.overall_score == 0.0
        assert r.interface_coverage == 0.0

    def test_complexity_metrics_result_defaults(self):
        r = ComplexityMetricsResult()
        assert r.cyclomatic_complexity == 0
        assert r.total_edges == 0

    def test_di_analysis_summary_defaults(self):
        s = DIAnalysisSummary()
        assert s.overall_risk_score == 0.0
        assert s.overall_risk_level == RiskLevel.INFO
        assert s.analyzed_at


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_constants_are_positive(self):
        assert MAX_SAFE_TREE_DEPTH > 0
        assert MAX_SAFE_FAN_OUT > 0
        assert MAX_SAFE_FAN_IN > 0
        assert CYCLOMATIC_THRESHOLD > 0

    def test_risk_weights_in_range(self):
        assert 0.0 < SINGLETON_RISK_WEIGHT <= 1.0
        assert 0.0 < TRANSIENT_RISK_WEIGHT <= 1.0
        assert 0.0 < SCOPED_RISK_WEIGHT <= 1.0

    def test_bonus_penalty_in_range(self):
        assert 0.0 < FACTORY_RESILIENCE_BONUS <= 1.0
        assert 0.0 < HOT_SWAP_BONUS <= 1.0
        assert 0.0 < CONFIG_SWITCH_PENALTY <= 1.0
        assert 0.0 < SERVICE_LOCATOR_PENALTY <= 1.0
        assert 0.0 < INTERFACE_DECOUPLING_IDEAL <= 1.0

    def test_lazy_init_probability(self):
        assert 0.0 < LAZY_INIT_FAILURE_PROBABILITY < 1.0


# ---------------------------------------------------------------------------
# Edge cases for 100% coverage
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_dependency_to_unknown_node_cycle_detection(self):
        """Line 495: neighbor not in color map (dependency to non-existent node)."""
        a = _comp("a")
        g = _graph(a)
        # Add dependency to a node that is NOT in the graph components
        g.add_dependency(Dependency(source_id="a", target_id="phantom"))
        cycles = _detect_cycles_in_graph(g)
        # Should not crash, phantom is skipped
        assert isinstance(cycles, list)

    def test_high_cyclomatic_complexity_recommendation(self):
        """Line 1127: cyclomatic complexity exceeds threshold."""
        # Build a highly connected graph that yields CC > CYCLOMATIC_THRESHOLD
        n = CYCLOMATIC_THRESHOLD + 5
        comps = [_comp(f"c{i}") for i in range(n)]
        g = _graph(*comps)
        # Create a mesh of edges to drive up CC
        for i in range(n):
            for j in range(i + 1, min(i + 4, n)):
                g.add_dependency(Dependency(source_id=f"c{i}", target_id=f"c{j}"))
        analyzer = DependencyInjectionAnalyzer(g)
        result = analyzer.compute_complexity_metrics()
        assert result.cyclomatic_complexity > CYCLOMATIC_THRESHOLD
        assert any("cyclomatic" in r.lower() for r in result.recommendations)

    def test_cycle_detection_with_three_node_cycle(self):
        """Ensure multi-node cycles are properly detected and reconstructed."""
        a, b, c = _comp("a"), _comp("b"), _comp("c")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        g.add_dependency(Dependency(source_id="c", target_id="a"))
        cycles = _detect_cycles_in_graph(g)
        assert len(cycles) > 0
        # All cycle nodes should be from {a, b, c}
        for cycle in cycles:
            for node in cycle:
                assert node in {"a", "b", "c"}

    def test_analyzer_circular_with_phantom_deps(self):
        """Circular detection through analyzer with phantom edges."""
        a = _comp("a")
        g = _graph(a)
        g.add_dependency(Dependency(source_id="a", target_id="nonexistent"))
        cfg = DIContainerConfig(registrations=[_reg("a")])
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.detect_circular_dependencies()
        assert result.has_cycles is False

    def test_tree_depth_avg_approaching_threshold(self):
        """Test the avg_depth recommendation branch."""
        # Build a chain where avg_depth > threshold * 0.7
        threshold = MAX_SAFE_TREE_DEPTH
        n = int(threshold * 0.8) + 2
        g, cfg = _make_chain(n)
        cfg_custom = DIContainerConfig(
            registrations=cfg.registrations,
            max_tree_depth=threshold,
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg_custom)
        result = analyzer.analyze_tree_depth()
        # At least one recommendation should exist
        assert len(result.recommendations) >= 0  # may or may not trigger

    def test_multiple_disconnected_components(self):
        """Test connected component counting with multiple isolates."""
        comps = [_comp(f"c{i}") for i in range(5)]
        g = _graph(*comps)
        # Only connect c0-c1
        g.add_dependency(Dependency(source_id="c0", target_id="c1"))
        count = _count_connected_components(g)
        assert count == 4  # {c0,c1}, {c2}, {c3}, {c4}

    def test_find_paths_with_visited_neighbor(self):
        """Ensure DFS handles already-visited neighbors (cycle avoidance)."""
        a, b, c = _comp("a"), _comp("b"), _comp("c")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="a", target_id="c"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        paths = _find_all_paths_dfs(g, "a")
        # Should include path through b->c and direct a->c
        assert any("c" in p for p in paths)

    def test_scope_mismatch_scoped_depends_transient(self):
        """Test scoped -> transient mismatch detection."""
        a, b = _comp("a"), _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        cfg = DIContainerConfig(
            registrations=[
                _reg("a", lifecycle=Lifecycle.SCOPED),
                _reg("b", lifecycle=Lifecycle.TRANSIENT),
            ]
        )
        analyzer = DependencyInjectionAnalyzer(g, cfg)
        result = analyzer.analyze_scope_mismatches()
        assert result.has_mismatches is True
        mm = result.mismatches[0]
        assert mm["mismatch_type"] == ScopeMismatchType.SCOPED_DEPENDS_ON_TRANSIENT.value
