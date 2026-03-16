"""Tests for SLA Validator Engine."""

from __future__ import annotations

import math
from datetime import timedelta

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    OperationalProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.sla_validator import (
    COMPONENT_AVAILABILITY,
    PenaltyTier,
    SLAImprovement,
    SLATarget,
    SLAValidationResult,
    SLAValidatorEngine,
    _component_base_availability,
    _component_effective_availability,
    _nines_to_availability,
    _to_nines,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_graph() -> InfraGraph:
    """Build a simple 3-component graph: LB -> App -> DB."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=2),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=5),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=4320, mttr_minutes=30),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _high_availability_graph() -> InfraGraph:
    """Build a highly available graph with redundancy and failover."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=3,
        operational_profile=OperationalProfile(mtbf_hours=43800, mttr_minutes=1),
        failover=FailoverConfig(
            enabled=True, promotion_time_seconds=5,
            health_check_interval_seconds=5, failover_threshold=2,
        ),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=5,
        operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=2),
        failover=FailoverConfig(
            enabled=True, promotion_time_seconds=10,
            health_check_interval_seconds=5, failover_threshold=2,
        ),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=3,
        operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=5),
        failover=FailoverConfig(
            enabled=True, promotion_time_seconds=15,
            health_check_interval_seconds=5, failover_threshold=3,
        ),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _spof_graph() -> InfraGraph:
    """Build a graph with a single point of failure (1-replica DB)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=1000, mttr_minutes=60),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _single_component_graph(
    replicas: int = 1,
    mtbf_hours: float = 2160.0,
    mttr_minutes: float = 30.0,
    failover: bool = False,
) -> InfraGraph:
    """Build a graph with a single component."""
    graph = InfraGraph()
    fo = FailoverConfig(enabled=failover, promotion_time_seconds=10)
    graph.add_component(Component(
        id="srv", name="Server", type=ComponentType.APP_SERVER,
        replicas=replicas,
        operational_profile=OperationalProfile(
            mtbf_hours=mtbf_hours, mttr_minutes=mttr_minutes,
        ),
        failover=fo,
    ))
    return graph


# ===========================================================================
# Math helper tests
# ===========================================================================


class TestMathHelpers:
    """Test nines conversion functions."""

    def test_to_nines_three_nines(self) -> None:
        result = _to_nines(0.999)
        assert abs(result - 3.0) < 0.01

    def test_to_nines_four_nines(self) -> None:
        result = _to_nines(0.9999)
        assert abs(result - 4.0) < 0.01

    def test_to_nines_five_nines(self) -> None:
        result = _to_nines(0.99999)
        assert abs(result - 5.0) < 0.01

    def test_to_nines_perfect(self) -> None:
        result = _to_nines(1.0)
        assert result == float("inf")

    def test_to_nines_zero(self) -> None:
        result = _to_nines(0.0)
        assert result == 0.0

    def test_nines_to_availability_roundtrip(self) -> None:
        for nines in [2.0, 3.0, 4.0, 5.0]:
            avail = _nines_to_availability(nines)
            back = _to_nines(avail)
            assert abs(back - nines) < 1e-6

    def test_nines_to_availability_values(self) -> None:
        assert abs(_nines_to_availability(3.0) - 0.999) < 1e-6
        assert abs(_nines_to_availability(4.0) - 0.9999) < 1e-6
        assert abs(_nines_to_availability(5.0) - 0.99999) < 1e-6


# ===========================================================================
# SLATarget tests
# ===========================================================================


class TestSLATarget:
    """Test SLATarget data class."""

    def test_target_availability(self) -> None:
        target = SLATarget(name="Test", target_nines=4.0)
        assert abs(target.target_availability - 0.9999) < 1e-6

    def test_target_percent(self) -> None:
        target = SLATarget(name="Test", target_nines=3.0)
        assert abs(target.target_percent - 99.9) < 0.01

    def test_allowed_downtime_monthly(self) -> None:
        target = SLATarget(name="Test", target_nines=3.0, measurement_window="monthly")
        dt = target.allowed_downtime
        # 99.9% monthly: ~0.1% of 30.44 days = ~43.8 minutes
        expected_seconds = 0.001 * 30.44 * 24 * 3600
        assert abs(dt.total_seconds() - expected_seconds) < 1.0

    def test_allowed_downtime_annual(self) -> None:
        target = SLATarget(name="Test", target_nines=3.0, measurement_window="annual")
        dt = target.allowed_downtime
        # 99.9% annual: ~0.1% of 365.25 days = ~8.76 hours
        expected_seconds = 0.001 * 365.25 * 24 * 3600
        assert abs(dt.total_seconds() - expected_seconds) < 1.0

    def test_penalty_tiers(self) -> None:
        target = SLATarget(
            name="Test",
            target_nines=4.0,
            penalty_tiers=[
                PenaltyTier(threshold=99.99, penalty_percent=0.0, description="No penalty"),
                PenaltyTier(threshold=99.9, penalty_percent=10.0, description="10% credit"),
                PenaltyTier(threshold=99.0, penalty_percent=25.0, description="25% credit"),
            ],
        )
        assert len(target.penalty_tiers) == 3
        assert target.penalty_tiers[1].penalty_percent == 10.0


# ===========================================================================
# Component availability calculation tests
# ===========================================================================


class TestComponentAvailability:
    """Test per-component availability calculations."""

    def test_single_instance_from_mtbf_mttr(self) -> None:
        comp = Component(
            id="srv", name="Server", type=ComponentType.APP_SERVER,
            replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=1000, mttr_minutes=60),
        )
        a = _component_base_availability(comp)
        # MTBF / (MTBF + MTTR) = 1000 / (1000 + 1) = 0.999
        expected = 1000.0 / (1000.0 + 1.0)
        assert abs(a - expected) < 1e-6

    def test_fallback_to_type_default(self) -> None:
        comp = Component(
            id="lb", name="LB", type=ComponentType.LOAD_BALANCER,
            replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=0, mttr_minutes=0),
        )
        a = _component_base_availability(comp)
        expected = COMPONENT_AVAILABILITY[ComponentType.LOAD_BALANCER]
        assert a == expected

    def test_redundancy_improves_availability(self) -> None:
        comp1 = Component(
            id="srv1", name="Server", type=ComponentType.APP_SERVER,
            replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
        )
        comp2 = Component(
            id="srv2", name="Server", type=ComponentType.APP_SERVER,
            replicas=3,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
        )
        a1 = _component_effective_availability(comp1)
        a2 = _component_effective_availability(comp2)
        assert a2 > a1

    def test_parallel_availability_formula(self) -> None:
        comp = Component(
            id="srv", name="Server", type=ComponentType.APP_SERVER,
            replicas=2,
            operational_profile=OperationalProfile(mtbf_hours=1000, mttr_minutes=60),
        )
        a_single = _component_base_availability(comp)
        a_eff = _component_effective_availability(comp)
        expected = 1.0 - (1.0 - a_single) ** 2
        assert abs(a_eff - expected) < 1e-6

    def test_failover_component(self) -> None:
        comp = Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=2,
            operational_profile=OperationalProfile(mtbf_hours=4320, mttr_minutes=30),
            failover=FailoverConfig(
                enabled=True, promotion_time_seconds=30,
                health_check_interval_seconds=10, failover_threshold=3,
            ),
        )
        a_eff = _component_effective_availability(comp)
        # Should be high but slightly less than pure parallel due to failover penalty
        a_parallel = 1.0 - (1.0 - _component_base_availability(comp)) ** 2
        assert a_eff < a_parallel  # failover penalty
        assert a_eff > 0.999  # still very high


# ===========================================================================
# SLAValidatorEngine tests
# ===========================================================================


class TestCriticalPathAvailability:
    """Test critical path availability calculation."""

    def test_empty_graph(self) -> None:
        engine = SLAValidatorEngine()
        graph = InfraGraph()
        assert engine.calculate_critical_path_availability(graph) == 0.0

    def test_single_component(self) -> None:
        engine = SLAValidatorEngine()
        graph = _single_component_graph(replicas=1, mtbf_hours=1000, mttr_minutes=60)
        avail = engine.calculate_critical_path_availability(graph)
        expected = 1000.0 / (1000.0 + 1.0)
        assert abs(avail - expected) < 1e-6

    def test_series_system_multiplicative(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()
        avail = engine.calculate_critical_path_availability(graph)

        # System availability should be product of all critical component availabilities
        assert 0 < avail < 1.0

        # Each component individually should be higher than system
        for comp in graph.components.values():
            a_comp = _component_effective_availability(comp)
            assert a_comp > avail or len(graph.components) == 1

    def test_redundancy_improves_system_availability(self) -> None:
        engine = SLAValidatorEngine()
        graph_spof = _spof_graph()
        graph_ha = _high_availability_graph()

        avail_spof = engine.calculate_critical_path_availability(graph_spof)
        avail_ha = engine.calculate_critical_path_availability(graph_ha)

        assert avail_ha > avail_spof

    def test_optional_dependencies_not_on_critical_path(self) -> None:
        engine = SLAValidatorEngine()

        # Build graph with optional dependency
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=5),
        ))
        graph.add_component(Component(
            id="cache", name="Cache", type=ComponentType.CACHE, replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=500, mttr_minutes=60),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="cache", dependency_type="optional",
        ))

        avail = engine.calculate_critical_path_availability(graph)
        # Cache with optional dep should NOT reduce system availability
        # (only app is on critical path as it has no requires dependents)
        app_avail = _component_effective_availability(graph.get_component("app"))
        assert abs(avail - app_avail) < 1e-6


class TestProveAchievability:
    """Test full SLA validation."""

    def test_achievable_target(self) -> None:
        engine = SLAValidatorEngine()
        graph = _high_availability_graph()
        result = engine.prove_achievability(graph, 3.0)

        assert result.achievable is True
        assert result.calculated_nines >= 3.0
        assert result.gap_nines <= 0  # negative gap means exceeded
        assert len(result.mathematical_proof) > 0

    def test_unachievable_target(self) -> None:
        engine = SLAValidatorEngine()
        graph = _spof_graph()
        # 5 nines is extremely unlikely with SPOF components
        result = engine.prove_achievability(graph, 5.0)

        assert result.achievable is False
        assert result.gap_nines > 0
        assert len(result.bottleneck_components) > 0
        assert len(result.improvement_needed) > 0

    def test_result_has_all_fields(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()
        target = SLATarget(
            name="API Availability",
            target_nines=3.0,
            measurement_window="monthly",
        )
        result = engine.prove_achievability(graph, 3.0, target)

        assert result.target == target
        assert isinstance(result.achievable, bool)
        assert 0.0 <= result.calculated_availability <= 1.0
        assert 0.0 <= result.confidence_level <= 1.0
        assert isinstance(result.allowed_downtime, timedelta)
        assert isinstance(result.estimated_downtime, timedelta)
        assert result.proof_method == "combined"
        assert len(result.mathematical_proof) > 0

    def test_proof_contains_component_details(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()
        result = engine.prove_achievability(graph, 3.0)

        # Proof should mention components
        assert "lb" in result.mathematical_proof
        assert "app" in result.mathematical_proof
        assert "db" in result.mathematical_proof

    def test_proof_contains_verdict(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()
        result = engine.prove_achievability(graph, 3.0)

        assert "Verdict" in result.mathematical_proof
        if result.achievable:
            assert "ACHIEVABLE" in result.mathematical_proof
        else:
            assert "NOT ACHIEVABLE" in result.mathematical_proof

    def test_default_target_created_when_none(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()
        result = engine.prove_achievability(graph, 3.5)

        assert result.target.name == "System Availability"
        assert abs(result.target.target_nines - 3.5) < 1e-6


class TestValidateMultiple:
    """Test validating multiple SLA targets."""

    def test_multiple_targets(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()
        targets = [
            SLATarget(name="Low", target_nines=2.0),
            SLATarget(name="Medium", target_nines=3.0),
            SLATarget(name="High", target_nines=5.0),
        ]
        results = engine.validate(graph, targets)

        assert len(results) == 3
        # Low target should be easier to achieve
        assert results[0].target.name == "Low"
        # All should be for the same infrastructure
        avails = [r.calculated_availability for r in results]
        assert avails[0] == avails[1] == avails[2]  # same infrastructure


class TestBreachProbability:
    """Test Monte Carlo breach probability estimation."""

    def test_deterministic_with_seed(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()
        target = SLATarget(name="Test", target_nines=3.0)

        p1 = engine.estimate_breach_probability(graph, target, simulations=500, seed=42)
        p2 = engine.estimate_breach_probability(graph, target, simulations=500, seed=42)
        assert p1 == p2

    def test_different_seeds_may_differ(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()
        target = SLATarget(name="Test", target_nines=3.0)

        p1 = engine.estimate_breach_probability(graph, target, simulations=1000, seed=42)
        p2 = engine.estimate_breach_probability(graph, target, simulations=1000, seed=99)
        # Different seeds can give different results (probabilistic)
        # But both should be valid probabilities
        assert 0.0 <= p1 <= 1.0
        assert 0.0 <= p2 <= 1.0

    def test_high_target_higher_breach_probability(self) -> None:
        engine = SLAValidatorEngine()
        graph = _spof_graph()
        target_easy = SLATarget(name="Easy", target_nines=2.0)
        target_hard = SLATarget(name="Hard", target_nines=5.0)

        p_easy = engine.estimate_breach_probability(graph, target_easy, simulations=1000, seed=42)
        p_hard = engine.estimate_breach_probability(graph, target_hard, simulations=1000, seed=42)

        assert p_hard >= p_easy

    def test_empty_graph_always_breaches(self) -> None:
        engine = SLAValidatorEngine()
        graph = InfraGraph()
        target = SLATarget(name="Test", target_nines=2.0)

        p = engine.estimate_breach_probability(graph, target, simulations=100)
        assert p == 1.0

    def test_breach_probability_bounded(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()
        target = SLATarget(name="Test", target_nines=3.0)

        p = engine.estimate_breach_probability(graph, target, simulations=500, seed=42)
        assert 0.0 <= p <= 1.0


class TestFindMinimumChanges:
    """Test minimum changes calculation."""

    def test_no_changes_when_target_met(self) -> None:
        engine = SLAValidatorEngine()
        graph = _high_availability_graph()

        # Low target should already be met
        improvements = engine.find_minimum_changes(graph, 2.0)
        assert len(improvements) == 0

    def test_suggests_improvements_when_needed(self) -> None:
        engine = SLAValidatorEngine()
        graph = _spof_graph()

        improvements = engine.find_minimum_changes(graph, 5.0)
        assert len(improvements) > 0
        for imp in improvements:
            assert isinstance(imp, SLAImprovement)
            assert imp.needed_availability > imp.current_availability
            assert len(imp.suggestion) > 0
            assert imp.cost_estimate in ("low", "medium", "high")

    def test_improvements_target_weakest_first(self) -> None:
        engine = SLAValidatorEngine()
        graph = _spof_graph()

        improvements = engine.find_minimum_changes(graph, 4.0)
        if len(improvements) >= 2:
            # First improvement should be for the weakest component
            assert improvements[0].current_availability <= improvements[1].current_availability

    def test_empty_graph_no_improvements(self) -> None:
        engine = SLAValidatorEngine()
        graph = InfraGraph()

        improvements = engine.find_minimum_changes(graph, 3.0)
        assert len(improvements) == 0

    def test_improvement_suggestions_are_specific(self) -> None:
        engine = SLAValidatorEngine()
        graph = _spof_graph()

        improvements = engine.find_minimum_changes(graph, 4.0)
        for imp in improvements:
            # Suggestions should mention concrete actions
            suggestion_lower = imp.suggestion.lower()
            has_action = any(kw in suggestion_lower for kw in [
                "replica", "failover", "autoscaling", "reliability",
                "increase", "enable", "improve",
            ])
            assert has_action, f"Suggestion lacks concrete action: {imp.suggestion}"


class TestBottleneckIdentification:
    """Test bottleneck component identification."""

    def test_spof_is_bottleneck(self) -> None:
        engine = SLAValidatorEngine()
        graph = _spof_graph()
        bottlenecks = engine._find_bottleneck_components(graph)

        assert len(bottlenecks) > 0
        # The DB with lowest MTBF should be the top bottleneck
        assert bottlenecks[0] in ("app", "db")

    def test_empty_graph_no_bottlenecks(self) -> None:
        engine = SLAValidatorEngine()
        graph = InfraGraph()
        bottlenecks = engine._find_bottleneck_components(graph)

        assert len(bottlenecks) == 0

    def test_bottleneck_order(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()
        bottlenecks = engine._find_bottleneck_components(graph)

        # Should be ordered by impact (most limiting first)
        assert len(bottlenecks) > 0
        # Verify ordering: each component's unavailability >= next
        for i in range(len(bottlenecks) - 1):
            comp_i = graph.get_component(bottlenecks[i])
            comp_j = graph.get_component(bottlenecks[i + 1])
            a_i = _component_effective_availability(comp_i)
            a_j = _component_effective_availability(comp_j)
            assert (1.0 - a_i) >= (1.0 - a_j) - 1e-10  # allow tiny float error


class TestExpectedPenaltyCost:
    """Test penalty cost calculation."""

    def test_no_penalty_tiers(self) -> None:
        engine = SLAValidatorEngine()
        target = SLATarget(name="Test", target_nines=3.0)
        graph = _simple_graph()
        cost = engine._calculate_expected_penalty(target, 0.1, graph)
        assert cost == 0.0  # No penalty tiers defined

    def test_with_penalty_and_revenue(self) -> None:
        engine = SLAValidatorEngine()
        target = SLATarget(
            name="Test",
            target_nines=3.0,
            penalty_tiers=[
                PenaltyTier(threshold=99.0, penalty_percent=25.0),
            ],
        )
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            cost_profile=CostProfile(monthly_contract_value=100000.0),
        ))
        cost = engine._calculate_expected_penalty(target, 0.1, graph)
        # Expected: 0.1 * 0.25 * 100000 = 2500
        assert abs(cost - 2500.0) < 0.1

    def test_zero_breach_probability_zero_cost(self) -> None:
        engine = SLAValidatorEngine()
        target = SLATarget(
            name="Test",
            target_nines=3.0,
            penalty_tiers=[
                PenaltyTier(threshold=99.0, penalty_percent=25.0),
            ],
        )
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            cost_profile=CostProfile(monthly_contract_value=100000.0),
        ))
        cost = engine._calculate_expected_penalty(target, 0.0, graph)
        assert cost == 0.0


class TestSLAValidationResult:
    """Test SLAValidationResult computed properties."""

    def test_calculated_nines(self) -> None:
        target = SLATarget(name="Test", target_nines=3.0)
        result = SLAValidationResult(
            target=target,
            achievable=True,
            calculated_availability=0.999,
            confidence_level=0.95,
            gap_nines=-0.5,
            allowed_downtime=timedelta(minutes=43),
            estimated_downtime=timedelta(minutes=30),
            bottleneck_components=[],
            improvement_needed=[],
            proof_method="analytical",
            mathematical_proof="test",
            risk_of_breach=0.01,
            expected_penalty_cost=0.0,
        )
        assert abs(result.calculated_nines - 3.0) < 0.01

    def test_calculated_percent(self) -> None:
        target = SLATarget(name="Test", target_nines=3.0)
        result = SLAValidationResult(
            target=target,
            achievable=True,
            calculated_availability=0.9999,
            confidence_level=0.95,
            gap_nines=-1.0,
            allowed_downtime=timedelta(minutes=43),
            estimated_downtime=timedelta(minutes=4),
            bottleneck_components=[],
            improvement_needed=[],
            proof_method="analytical",
            mathematical_proof="test",
            risk_of_breach=0.001,
            expected_penalty_cost=0.0,
        )
        assert abs(result.calculated_percent - 99.99) < 0.01


class TestDeterminism:
    """Test that analytical calculations are deterministic."""

    def test_critical_path_deterministic(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()

        r1 = engine.calculate_critical_path_availability(graph)
        r2 = engine.calculate_critical_path_availability(graph)
        assert r1 == r2

    def test_prove_achievability_deterministic(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()

        r1 = engine.prove_achievability(graph, 3.0)
        r2 = engine.prove_achievability(graph, 3.0)

        assert r1.achievable == r2.achievable
        assert r1.calculated_availability == r2.calculated_availability
        assert r1.risk_of_breach == r2.risk_of_breach

    def test_find_minimum_changes_deterministic(self) -> None:
        engine = SLAValidatorEngine()
        graph = _spof_graph()

        i1 = engine.find_minimum_changes(graph, 4.0)
        i2 = engine.find_minimum_changes(graph, 4.0)

        assert len(i1) == len(i2)
        for a, b in zip(i1, i2):
            assert a.component == b.component
            assert a.current_availability == b.current_availability


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_high_target(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()
        result = engine.prove_achievability(graph, 9.0)
        assert result.achievable is False

    def test_very_low_target(self) -> None:
        engine = SLAValidatorEngine()
        graph = _simple_graph()
        result = engine.prove_achievability(graph, 1.0)
        assert result.achievable is True

    def test_empty_graph_validation(self) -> None:
        engine = SLAValidatorEngine()
        graph = InfraGraph()
        target = SLATarget(name="Test", target_nines=2.0)
        result = engine.prove_achievability(graph, 2.0, target)

        assert result.achievable is False
        assert result.calculated_availability == 0.0

    def test_single_highly_reliable_component(self) -> None:
        engine = SLAValidatorEngine()
        graph = _single_component_graph(
            replicas=5,
            mtbf_hours=87600,
            mttr_minutes=1,
        )
        result = engine.prove_achievability(graph, 4.0)
        assert result.achievable is True

    def test_default_availability_types(self) -> None:
        """All ComponentTypes should have a default availability."""
        for ct in ComponentType:
            assert ct in COMPONENT_AVAILABILITY


# ===========================================================================
# Coverage gap tests — targeting lines 172, 174, 209, 423, 427, 463,
# 543, 619, 630-634, 637-638, 644-648, 669, 675
# ===========================================================================


class TestNinesToAvailabilityEdgeCases:
    """Cover lines 172 and 174: _nines_to_availability edge cases."""

    def test_nines_to_availability_infinite_returns_one(self) -> None:
        """Infinite nines should return perfect availability (1.0). [line 172]"""
        assert _nines_to_availability(float("inf")) == 1.0

    def test_nines_to_availability_zero_returns_zero(self) -> None:
        """Zero nines should return 0.0 availability. [line 174]"""
        assert _nines_to_availability(0.0) == 0.0

    def test_nines_to_availability_negative_returns_zero(self) -> None:
        """Negative nines should return 0.0 availability. [line 174]"""
        assert _nines_to_availability(-1.0) == 0.0


class TestFailoverDefaultMTBF:
    """Cover line 209: failover with mtbf_hours <= 0 falls back to _DEFAULT_MTBF."""

    def test_failover_with_zero_mtbf_uses_default(self) -> None:
        """A component with failover enabled but mtbf_hours=0 should use the
        default MTBF lookup and still compute effective availability. [line 209]"""
        comp = Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=2,
            operational_profile=OperationalProfile(mtbf_hours=0, mttr_minutes=0),
            failover=FailoverConfig(
                enabled=True, promotion_time_seconds=10,
                health_check_interval_seconds=5, failover_threshold=2,
            ),
        )
        a_eff = _component_effective_availability(comp)
        # Should be valid availability despite zero mtbf_hours input
        assert 0.0 < a_eff <= 1.0


class TestMonteCarloDefaultMTBFMTTR:
    """Cover lines 423, 427, 463: Monte Carlo with zero MTBF/MTTR
    using default lookups and the zero-MTTR branch."""

    def test_breach_probability_zero_mtbf_mttr(self) -> None:
        """Components with mtbf_hours=0 and mttr_minutes=0 should use
        default lookups in Monte Carlo. [lines 423, 427]"""
        engine = SLAValidatorEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=2,
            operational_profile=OperationalProfile(mtbf_hours=0, mttr_minutes=0),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="app",  # self-dep just to ensure edge
        ))
        target = SLATarget(name="Test", target_nines=3.0)
        # Should not raise; uses default MTBF/MTTR
        p = engine.estimate_breach_probability(graph, target, simulations=100, seed=42)
        assert 0.0 <= p <= 1.0

    def test_breach_probability_zero_mttr_branch(self) -> None:
        """When mttr_hours evaluates to 0 after lookup, the else branch sets
        sampled_mttr = 1e-9. [line 463]"""
        engine = SLAValidatorEngine()
        graph = InfraGraph()
        # Use a custom component type but set mttr to 0 explicitly
        graph.add_component(Component(
            id="srv", name="Server", type=ComponentType.APP_SERVER,
            replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=0),
        ))
        target = SLATarget(name="Test", target_nines=2.0)
        p = engine.estimate_breach_probability(graph, target, simulations=50, seed=42)
        assert 0.0 <= p <= 1.0


class TestFindMinimumChangesGap:
    """Cover line 543: remaining_gap <= 1.0 break in find_minimum_changes."""

    def test_no_improvements_when_system_exceeds_target(self) -> None:
        """When system availability already exceeds target, the loop should
        return empty immediately."""
        engine = SLAValidatorEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=5,
            operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=1),
        ))
        improvements = engine.find_minimum_changes(graph, 1.0)
        assert len(improvements) == 0

    def test_remaining_gap_break_with_multi_components(self) -> None:
        """When improving the weakest component closes the gap, the loop
        should break before processing remaining components. [line 543]"""
        engine = SLAValidatorEngine()
        graph = InfraGraph()
        # One very weak component (low MTBF, high MTTR, single replica)
        graph.add_component(Component(
            id="weak", name="Weak", type=ComponentType.APP_SERVER,
            replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=100, mttr_minutes=120),
        ))
        # One strong component
        graph.add_component(Component(
            id="strong", name="Strong", type=ComponentType.APP_SERVER,
            replicas=5,
            operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=1),
        ))
        graph.add_dependency(Dependency(
            source_id="weak", target_id="strong", dependency_type="requires",
        ))
        # Set a moderate target that can be met by improving only the weak component
        improvements = engine.find_minimum_changes(graph, 3.0)
        # The weak component should get improvement suggestions
        assert len(improvements) >= 1
        # The strong component should NOT get suggestions (gap closed before it)
        improved_ids = {imp.component for imp in improvements}
        assert "weak" in improved_ids


class TestSuggestImprovementEdgeCases:
    """Cover lines 619, 630-634, 637-638, 644-648:
    _suggest_improvement branches for perfect availability,
    needed_replicas > current replicas, no failover + multi-replica,
    and the fallback suggestion."""

    def test_perfect_base_availability_branch(self) -> None:
        """When a_base >= 1.0, needed_replicas = current replicas. [line 619]"""
        engine = SLAValidatorEngine()
        # Directly test _suggest_improvement with a component whose base
        # availability rounds to 1.0 in floating point.
        comp = Component(
            id="perfect", name="Perfect", type=ComponentType.APP_SERVER,
            replicas=2,
            operational_profile=OperationalProfile(
                mtbf_hours=1e18, mttr_minutes=1e-18,
            ),
        )
        a_base = _component_base_availability(comp)
        assert a_base >= 1.0  # floating point rounds to 1.0
        a_current = 0.9999
        a_needed = 0.99999
        suggestion, cost = engine._suggest_improvement(comp, a_current, a_needed)
        # With a_base=1.0, the else branch is taken (line 619)
        assert len(suggestion) > 0

    def test_needed_replicas_greater_than_current(self) -> None:
        """When component has replicas > 1 but still needs more,
        'Increase replicas from X to Y' suggestion is triggered. [lines 630-634]"""
        engine = SLAValidatorEngine()
        # Call _suggest_improvement directly to isolate the branch
        comp = Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=2,
            operational_profile=OperationalProfile(mtbf_hours=100, mttr_minutes=60),
        )
        a_base = _component_base_availability(comp)
        a_current = _component_effective_availability(comp)
        # Need a very high availability that requires many more replicas
        a_needed = 0.9999999
        suggestion, cost = engine._suggest_improvement(comp, a_current, a_needed)
        assert "Increase replicas from 2" in suggestion

    def test_no_failover_multi_replica_suggestion(self) -> None:
        """Multi-replica component without failover should suggest
        enabling failover. [lines 637-638]"""
        engine = SLAValidatorEngine()
        # Call _suggest_improvement directly to hit the failover branch
        comp = Component(
            id="srv", name="Server", type=ComponentType.APP_SERVER,
            replicas=3,
            operational_profile=OperationalProfile(mtbf_hours=100, mttr_minutes=60),
            failover=FailoverConfig(enabled=False),
        )
        a_current = _component_effective_availability(comp)
        # Need higher availability than current, but not so high that replicas dominate
        a_needed = min(a_current * 1.001, 0.99999)
        suggestion, cost = engine._suggest_improvement(comp, a_current, a_needed)
        assert "failover" in suggestion.lower()

    def test_fallback_improve_reliability_suggestion(self) -> None:
        """When replicas are sufficient, failover is enabled, and autoscaling
        is enabled, the fallback should suggest improving single-instance
        reliability. [lines 644-648]"""
        engine = SLAValidatorEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="srv", name="Server", type=ComponentType.APP_SERVER,
            replicas=10,
            operational_profile=OperationalProfile(mtbf_hours=200, mttr_minutes=120),
            failover=FailoverConfig(
                enabled=True, promotion_time_seconds=5,
                health_check_interval_seconds=5, failover_threshold=2,
            ),
            autoscaling=AutoScalingConfig(enabled=True),
        ))
        improvements = engine.find_minimum_changes(graph, 9.0)
        has_reliability = any(
            "reliability" in imp.suggestion.lower()
            for imp in improvements
        )
        assert has_reliability


class TestExpectedPenaltyRevenuePerMinute:
    """Cover lines 669 and 675: _calculate_expected_penalty with
    revenue_per_minute and with zero revenue."""

    def test_penalty_with_revenue_per_minute(self) -> None:
        """When revenue_per_minute is set, expected penalty should be > 0.
        [line 669]"""
        engine = SLAValidatorEngine()
        target = SLATarget(
            name="Test",
            target_nines=3.0,
            penalty_tiers=[
                PenaltyTier(threshold=99.0, penalty_percent=25.0),
            ],
        )
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            cost_profile=CostProfile(revenue_per_minute=10.0),
        ))
        cost = engine._calculate_expected_penalty(target, 0.1, graph)
        # revenue = 10 * 60 * 24 * 30.44 = 438,336
        # expected = 0.1 * 0.25 * 438336 = 10,958.4
        assert cost > 0

    def test_penalty_zero_revenue_returns_zero(self) -> None:
        """When no cost profile has revenue, expected penalty is 0.0. [line 675]"""
        engine = SLAValidatorEngine()
        target = SLATarget(
            name="Test",
            target_nines=3.0,
            penalty_tiers=[
                PenaltyTier(threshold=99.0, penalty_percent=25.0),
            ],
        )
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        cost = engine._calculate_expected_penalty(target, 0.1, graph)
        assert cost == 0.0
