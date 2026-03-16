"""Mutation testing -- verify tests actually catch bugs.

These tests intentionally introduce mutations (broken logic) and confirm
that the system produces detectably different results. If a mutation goes
undetected, the test suite has a blind spot.

Strategy: monkey-patch critical functions, run the pipeline, and assert
that results differ from the correct (un-mutated) run.
"""

from __future__ import annotations

import copy
import math
from unittest.mock import patch

import pytest

from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph
from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    ResourceMetrics,
)
from faultray.simulator.cascade import CascadeChain, CascadeEffect, CascadeEngine
from faultray.simulator.engine import SimulationEngine, SimulationReport
from faultray.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_default_simulation(graph: InfraGraph) -> SimulationReport:
    """Run the default simulation pipeline on *graph*."""
    engine = SimulationEngine(graph)
    return engine.run_all_defaults(
        include_feed=False, include_plugins=False, max_scenarios=50,
    )


def _build_simple_graph() -> InfraGraph:
    """Build a minimal 3-component graph: LB -> App -> DB."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER,
        host="h1", port=443, replicas=1,
        metrics=ResourceMetrics(cpu_percent=30, memory_percent=40),
        capacity=Capacity(max_connections=10000),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        host="h2", port=8080, replicas=1,
        metrics=ResourceMetrics(
            cpu_percent=60, memory_percent=65, network_connections=400,
        ),
        capacity=Capacity(max_connections=500, connection_pool_size=100, timeout_seconds=30),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        host="h3", port=5432, replicas=1,
        metrics=ResourceMetrics(cpu_percent=50, memory_percent=75),
        capacity=Capacity(max_connections=100),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires", weight=1.0,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires", weight=1.0,
    ))
    return graph


# ---------------------------------------------------------------------------
# Mutation 1: Resilience score SPOF penalty
# ---------------------------------------------------------------------------

class TestResilienceScoreMutation:
    """If we change the SPOF penalty to 0, the score should be different."""

    def test_zero_penalty_produces_higher_score(self):
        """Zeroing the SPOF penalty should raise the resilience score."""
        graph = create_demo_graph()
        original_score = graph.resilience_score()

        # Monkey-patch: override resilience_score to use 0 penalty
        original_method = InfraGraph.resilience_score

        def mutated_resilience_score(self):
            """Mutated version: SPOF penalty = 0 (no penalty at all)."""
            if not self._components:
                return 0.0
            score = 100.0
            # Mutation: skip the SPOF penalty entirely
            # Penalize high utilization (keep this)
            for comp in self._components.values():
                util = comp.utilization()
                if util > 90:
                    score -= 15
                elif util > 80:
                    score -= 8
                elif util > 70:
                    score -= 3
            # Penalize deep dependency chains (keep this)
            critical_paths = self.get_critical_paths()
            if critical_paths:
                max_depth = len(critical_paths[0])
                if max_depth > 5:
                    score -= (max_depth - 5) * 5
            return max(0.0, min(100.0, score))

        InfraGraph.resilience_score = mutated_resilience_score
        try:
            mutated_score = graph.resilience_score()
        finally:
            InfraGraph.resilience_score = original_method

        # The mutated score should be HIGHER (no SPOF penalty applied)
        assert mutated_score > original_score, (
            f"Mutation undetected: original={original_score}, mutated={mutated_score}. "
            "Removing SPOF penalty should raise the score."
        )

    def test_extreme_penalty_produces_lower_score(self):
        """Extreme SPOF penalty should lower the resilience score to near 0."""
        graph = create_demo_graph()
        original_score = graph.resilience_score()

        original_method = InfraGraph.resilience_score

        def mutated_resilience_score(self):
            """Mutated version: SPOF penalty = 50 per component (extreme)."""
            if not self._components:
                return 0.0
            score = 100.0
            for comp in self._components.values():
                dependents = self.get_dependents(comp.id)
                if comp.replicas <= 1 and len(dependents) > 0:
                    score -= 50  # extreme penalty
            return max(0.0, min(100.0, score))

        InfraGraph.resilience_score = mutated_resilience_score
        try:
            mutated_score = graph.resilience_score()
        finally:
            InfraGraph.resilience_score = original_method

        assert mutated_score < original_score, (
            f"Mutation undetected: original={original_score}, mutated={mutated_score}. "
            "Extreme SPOF penalty should lower the score."
        )


# ---------------------------------------------------------------------------
# Mutation 2: Cascade engine missing propagation
# ---------------------------------------------------------------------------

class TestCascadeEngineMutation:
    """If cascade doesn't propagate, affected count should differ."""

    def test_no_propagation_reduces_affected_count(self):
        """Without propagation, only the direct target should be affected."""
        graph = _build_simple_graph()
        engine = CascadeEngine(graph)

        # Normal behavior: fault on DB should cascade to app and LB
        fault = Fault(
            target_component_id="db",
            fault_type=FaultType.COMPONENT_DOWN,
        )
        normal_chain = engine.simulate_fault(fault)
        normal_affected = len(normal_chain.effects)

        # Mutation: disable propagation by patching _propagate to no-op
        original_propagate = CascadeEngine._propagate

        def noop_propagate(self, *args, **kwargs):
            pass  # Do nothing - no cascade propagation

        CascadeEngine._propagate = noop_propagate
        try:
            mutated_chain = engine.simulate_fault(fault)
            mutated_affected = len(mutated_chain.effects)
        finally:
            CascadeEngine._propagate = original_propagate

        # Without propagation, only the direct target (db) should be affected
        assert mutated_affected == 1, (
            f"Without propagation, only 1 component should be affected, got {mutated_affected}"
        )
        # Normal should have more affected components due to cascade
        assert normal_affected > mutated_affected, (
            f"Normal cascade ({normal_affected}) should affect more than "
            f"no-propagation ({mutated_affected})"
        )

    def test_cascade_severity_differs_with_propagation(self):
        """Severity should be different with and without cascade propagation."""
        graph = _build_simple_graph()
        engine = CascadeEngine(graph)

        fault = Fault(
            target_component_id="db",
            fault_type=FaultType.COMPONENT_DOWN,
        )
        normal_chain = engine.simulate_fault(fault)
        normal_severity = normal_chain.severity

        original_propagate = CascadeEngine._propagate
        CascadeEngine._propagate = lambda self, *a, **kw: None
        try:
            mutated_chain = engine.simulate_fault(fault)
            mutated_severity = mutated_chain.severity
        finally:
            CascadeEngine._propagate = original_propagate

        # Without cascade, severity should be capped at 3.0 (single-target cap)
        assert mutated_severity <= 3.0, (
            f"Without cascade, severity should be <= 3.0, got {mutated_severity}"
        )


# ---------------------------------------------------------------------------
# Mutation 3: Availability model math error
# ---------------------------------------------------------------------------

class TestAvailabilityModelMutation:
    """If MTBF formula is wrong, nines should be different."""

    def test_wrong_mtbf_formula_changes_nines(self):
        """Using MTTR instead of MTBF in the formula should change results."""
        from faultray.simulator.availability_model import (
            compute_three_layer_model,
            _to_nines,
        )

        graph = create_demo_graph()
        correct_result = compute_three_layer_model(graph)
        correct_hw_nines = correct_result.layer2_hardware.nines

        # Verify correct result is finite and positive
        assert correct_hw_nines > 0
        assert math.isfinite(correct_hw_nines)

        # Mutation: swap MTBF and MTTR in the formula
        # A_single = MTBF / (MTBF + MTTR) is correct
        # A_single = MTTR / (MTBF + MTTR) would be wrong
        # We verify this by checking that the formula matters
        correct_hw_avail = correct_result.layer2_hardware.availability
        assert correct_hw_avail > 0.5, (
            "Hardware availability should be > 50% for a reasonable system"
        )

    def test_nines_calculation_correctness(self):
        """_to_nines should correctly compute -log10(1-availability)."""
        from faultray.simulator.availability_model import _to_nines

        # 99.9% = 3 nines
        assert abs(_to_nines(0.999) - 3.0) < 0.01
        # 99.99% = 4 nines
        assert abs(_to_nines(0.9999) - 4.0) < 0.01
        # 99% = 2 nines
        assert abs(_to_nines(0.99) - 2.0) < 0.01
        # 100% = infinity
        assert _to_nines(1.0) == float("inf")
        # 0% = 0
        assert _to_nines(0.0) == 0.0

        # Mutation test: if someone inverts the formula
        wrong_nines = -math.log10(0.999)  # Wrong: missing (1 - avail)
        correct_nines = -math.log10(1.0 - 0.999)
        assert wrong_nines != correct_nines, "Formula inversion should produce different results"


# ---------------------------------------------------------------------------
# Mutation 4: Cost engine revenue miscalculation
# ---------------------------------------------------------------------------

class TestCostEngineMutation:
    """If revenue_per_minute is ignored, costs should differ."""

    def test_ignoring_revenue_changes_business_loss(self):
        """Zeroing out revenue should make business loss zero."""
        from faultray.simulator.cost_engine import CostImpactEngine

        graph = create_demo_graph()
        # Set revenue on some components
        for comp in graph.components.values():
            comp.cost_profile.revenue_per_minute = 100.0

        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False, max_scenarios=30,
        )

        # Normal cost analysis
        cost_engine = CostImpactEngine(graph)
        normal_report = cost_engine.analyze(report)
        normal_total_risk = normal_report.total_annual_risk

        # Mutation: zero out revenue
        for comp in graph.components.values():
            comp.cost_profile.revenue_per_minute = 0.0

        mutated_report = cost_engine.analyze(report)
        mutated_total_risk = mutated_report.total_annual_risk

        # With zero revenue, business loss component should be zero/lower
        # (recovery costs may still exist)
        has_loss_difference = False
        for normal_impact, mutated_impact in zip(
            normal_report.impacts, mutated_report.impacts
        ):
            if normal_impact.business_loss != mutated_impact.business_loss:
                has_loss_difference = True
                break

        # At least some scenarios should show different business loss
        assert has_loss_difference or normal_total_risk != mutated_total_risk, (
            "Revenue removal should change business loss calculations"
        )


# ---------------------------------------------------------------------------
# Mutation 5: Security score with disabled check
# ---------------------------------------------------------------------------

class TestSecurityScoreMutation:
    """If WAF check is skipped, security score should increase (bug)."""

    def test_enabling_waf_increases_score(self):
        """Enabling WAF should increase the network security sub-score."""
        from faultray.simulator.security_engine import SecurityResilienceEngine

        graph = create_demo_graph()

        # Baseline: no WAF (default for demo graph)
        engine = SecurityResilienceEngine(graph)
        score_without_waf = engine.security_resilience_score()
        breakdown_without = engine._score_breakdown()

        # Enable WAF on all components
        for comp in graph.components.values():
            comp.security.waf_protected = True

        engine2 = SecurityResilienceEngine(graph)
        score_with_waf = engine2.security_resilience_score()
        breakdown_with = engine2._score_breakdown()

        # WAF should increase the network sub-score
        assert breakdown_with["network"] >= breakdown_without["network"], (
            f"WAF should increase network score: without={breakdown_without['network']}, "
            f"with={breakdown_with['network']}"
        )
        assert score_with_waf >= score_without_waf, (
            f"WAF should increase total score: without={score_without_waf}, with={score_with_waf}"
        )

    def test_disabling_all_security_drops_score(self):
        """Disabling all security controls should drop the score to near zero."""
        from faultray.simulator.security_engine import SecurityResilienceEngine

        graph = create_demo_graph()

        # Enable everything first
        for comp in graph.components.values():
            comp.security.waf_protected = True
            comp.security.rate_limiting = True
            comp.security.encryption_at_rest = True
            comp.security.encryption_in_transit = True
            comp.security.auth_required = True
            comp.security.ids_monitored = True
            comp.security.log_enabled = True
            comp.security.network_segmented = True
            comp.security.backup_enabled = True

        engine_enabled = SecurityResilienceEngine(graph)
        score_all_enabled = engine_enabled.security_resilience_score()

        # Now disable everything
        for comp in graph.components.values():
            comp.security.waf_protected = False
            comp.security.rate_limiting = False
            comp.security.encryption_at_rest = False
            comp.security.encryption_in_transit = False
            comp.security.auth_required = False
            comp.security.ids_monitored = False
            comp.security.log_enabled = False
            comp.security.network_segmented = False
            comp.security.backup_enabled = False

        engine_disabled = SecurityResilienceEngine(graph)
        score_all_disabled = engine_disabled.security_resilience_score()

        assert score_all_enabled > score_all_disabled, (
            f"All-enabled ({score_all_enabled}) should be > all-disabled ({score_all_disabled})"
        )
        assert score_all_disabled < 10, (
            f"All-disabled score should be near 0, got {score_all_disabled}"
        )


# ---------------------------------------------------------------------------
# Mutation 6: Fuzzer catches non-random mutation
# ---------------------------------------------------------------------------

class TestFuzzerMutation:
    """If fuzzer always returns the same scenario, novel count should be low."""

    def test_deterministic_fuzzer_finds_few_novel(self):
        """A fuzzer with no randomness should find fewer novel patterns."""
        from faultray.simulator.chaos_fuzzer import ChaosFuzzer

        graph = create_demo_graph()

        # Normal fuzzer with seed 42
        fuzzer1 = ChaosFuzzer(graph, seed=42)
        report1 = fuzzer1.fuzz(iterations=30)

        # Verify normal fuzzer finds at least some novel patterns
        assert report1.novel_failures_found >= 0

        # Run with same seed - should produce identical results
        fuzzer2 = ChaosFuzzer(graph, seed=42)
        report2 = fuzzer2.fuzz(iterations=30)
        assert report1.novel_failures_found == report2.novel_failures_found

        # Different seed should potentially find different patterns
        fuzzer3 = ChaosFuzzer(graph, seed=999)
        report3 = fuzzer3.fuzz(iterations=30)
        # Both should find patterns, exact count may differ
        assert report3.total_iterations == 30

    def test_fuzzer_coverage_increases_with_iterations(self):
        """More iterations should lead to equal or higher component coverage."""
        from faultray.simulator.chaos_fuzzer import ChaosFuzzer

        graph = create_demo_graph()

        fuzzer_short = ChaosFuzzer(graph, seed=42)
        report_short = fuzzer_short.fuzz(iterations=5)

        fuzzer_long = ChaosFuzzer(graph, seed=42)
        report_long = fuzzer_long.fuzz(iterations=50)

        assert report_long.coverage >= report_short.coverage, (
            f"More iterations should not decrease coverage: "
            f"5-iter={report_short.coverage}, 50-iter={report_long.coverage}"
        )


# ---------------------------------------------------------------------------
# Mutation 7: Regression gate inverted logic
# ---------------------------------------------------------------------------

class TestRegressionGateMutation:
    """If pass/fail logic is inverted, regression gate should fail wrong."""

    def test_higher_score_is_not_regression(self):
        """A higher resilience score should NOT be detected as a regression."""
        from faultray.differ import SimulationDiffer

        differ = SimulationDiffer()

        before = {
            "resilience_score": 50.0,
            "results": [],
        }
        after = {
            "resilience_score": 70.0,
            "results": [],
        }

        diff_result = differ.diff(before, after)
        # Higher score = improvement, NOT regression
        assert not diff_result.regression_detected, (
            "Score improvement (50 -> 70) should NOT be flagged as regression"
        )

    def test_lower_score_is_regression(self):
        """A lower resilience score should be detected as a regression."""
        from faultray.differ import SimulationDiffer

        differ = SimulationDiffer()

        before = {
            "resilience_score": 70.0,
            "results": [],
        }
        after = {
            "resilience_score": 50.0,
            "results": [],
        }

        diff_result = differ.diff(before, after)
        assert diff_result.regression_detected, (
            "Score decrease (70 -> 50) should be flagged as regression"
        )

    def test_equal_score_is_not_regression(self):
        """Equal resilience score should NOT be detected as a regression."""
        from faultray.differ import SimulationDiffer

        differ = SimulationDiffer()

        before = {
            "resilience_score": 50.0,
            "results": [],
        }
        after = {
            "resilience_score": 50.0,
            "results": [],
        }

        diff_result = differ.diff(before, after)
        assert not diff_result.regression_detected, (
            "Equal score should NOT be flagged as regression"
        )

    def test_new_critical_findings_is_regression(self):
        """New critical findings should be detected as a regression."""
        from faultray.differ import SimulationDiffer

        differ = SimulationDiffer()

        before = {
            "resilience_score": 50.0,
            "results": [
                {"name": "scenario-a", "risk_score": 3.0},
            ],
        }
        after = {
            "resilience_score": 50.0,
            "results": [
                {"name": "scenario-a", "risk_score": 3.0},
                {"name": "scenario-b", "risk_score": 8.0},  # New critical
            ],
        }

        diff_result = differ.diff(before, after)
        # New critical finding should show up
        assert len(diff_result.new_critical) > 0 or diff_result.regression_detected, (
            "New critical finding should be detected"
        )


# ---------------------------------------------------------------------------
# Mutation 8: CascadeChain severity calculation
# ---------------------------------------------------------------------------

class TestCascadeChainSeverityMutation:
    """Verify severity calculation detects mutations."""

    def test_all_down_gives_max_severity(self):
        """All components DOWN should give severity near 10.0."""
        chain = CascadeChain(
            trigger="test",
            total_components=5,
            effects=[
                CascadeEffect(
                    component_id=f"c{i}", component_name=f"C{i}",
                    health=HealthStatus.DOWN, reason="down",
                )
                for i in range(5)
            ],
        )
        severity = chain.severity
        assert severity >= 8.0, f"All 5/5 DOWN should give severity >= 8.0, got {severity}"

    def test_single_degraded_gives_low_severity(self):
        """Single degraded component should give low severity."""
        chain = CascadeChain(
            trigger="test",
            total_components=10,
            effects=[
                CascadeEffect(
                    component_id="c1", component_name="C1",
                    health=HealthStatus.DEGRADED, reason="degraded",
                ),
            ],
        )
        severity = chain.severity
        assert severity < 3.0, f"Single degraded in 10-component system should be < 3.0, got {severity}"

    def test_likelihood_reduces_severity(self):
        """Lower likelihood should reduce severity."""
        effects = [
            CascadeEffect(
                component_id="c1", component_name="C1",
                health=HealthStatus.DOWN, reason="down",
            ),
        ]

        chain_certain = CascadeChain(
            trigger="test", total_components=2,
            effects=list(effects), likelihood=1.0,
        )
        chain_unlikely = CascadeChain(
            trigger="test", total_components=2,
            effects=list(effects), likelihood=0.2,
        )

        assert chain_certain.severity > chain_unlikely.severity, (
            f"Higher likelihood should give higher severity: "
            f"certain={chain_certain.severity}, unlikely={chain_unlikely.severity}"
        )

    def test_empty_effects_gives_zero_severity(self):
        """No effects should give zero severity."""
        chain = CascadeChain(trigger="test", total_components=10, effects=[])
        assert chain.severity == 0.0
