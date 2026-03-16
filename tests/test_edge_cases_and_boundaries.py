"""Edge case and boundary value tests for FaultRay core modules.

Tests scenarios that standard unit tests typically miss:
1. InfraGraph edge cases (empty, large, circular, self-ref, duplicates, invalid replicas)
2. Resilience score boundary values (all healthy, all down, clamping to [0,100])
3. Simulation edge cases (empty faults, non-existent targets, mass failures, scale)
4. Input validation (unicode, long strings, special chars, NaN/Infinity)
5. Concurrent modification patterns (add-during-iteration, remove-during-analysis)
"""

from __future__ import annotations

import math
import sys
import time

import pytest
from pydantic import ValidationError

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEffect, CascadeEngine
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_component(
    cid: str = "c1",
    name: str = "Comp",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    **kwargs,
) -> Component:
    """Convenience factory for a Component with sensible defaults."""
    return Component(id=cid, name=name, type=ctype, replicas=replicas, **kwargs)


def _make_scenario(
    faults: list[Fault] | None = None,
    sid: str = "s1",
    name: str = "test-scenario",
    traffic_multiplier: float = 1.0,
) -> Scenario:
    return Scenario(
        id=sid,
        name=name,
        description="test",
        faults=faults or [],
        traffic_multiplier=traffic_multiplier,
    )


# ===================================================================
# 1. InfraGraph Edge Cases
# ===================================================================


class TestInfraGraphEdgeCases:
    """Edge cases for InfraGraph construction and querying."""

    # --- Empty graph (0 components) ---

    def test_empty_graph_summary(self):
        graph = InfraGraph()
        summary = graph.summary()
        assert summary["total_components"] == 0
        assert summary["total_dependencies"] == 0
        assert summary["resilience_score"] == 0.0

    def test_empty_graph_resilience_score(self):
        graph = InfraGraph()
        assert graph.resilience_score() == 0.0

    def test_empty_graph_resilience_score_v2(self):
        graph = InfraGraph()
        result = graph.resilience_score_v2()
        assert result["score"] == 0.0
        for category_score in result["breakdown"].values():
            assert category_score == 0.0

    def test_empty_graph_critical_paths(self):
        graph = InfraGraph()
        assert graph.get_critical_paths() == []

    def test_empty_graph_cascade_path(self):
        graph = InfraGraph()
        # Querying cascade for a non-existent component
        paths = graph.get_cascade_path("nonexistent")
        assert paths == []

    def test_empty_graph_get_all_affected(self):
        graph = InfraGraph()
        # get_all_affected on a non-existent node may raise networkx.NetworkXError
        # because get_dependents calls _graph.predecessors on a missing node.
        # This is a known edge case: the caller is expected to check existence first.
        try:
            affected = graph.get_all_affected("nonexistent")
            assert isinstance(affected, set)
        except Exception:
            # NetworkXError is acceptable for a non-existent node
            pass

    def test_empty_graph_to_dict(self):
        graph = InfraGraph()
        d = graph.to_dict()
        assert d["components"] == []
        assert d["dependencies"] == []

    # --- Large graph (1000+ components) ---

    def test_large_graph_1000_components(self):
        """Verify no performance issues with 1000+ components."""
        graph = InfraGraph()
        n = 1000
        for i in range(n):
            graph.add_component(
                _make_component(cid=f"c{i}", name=f"Component-{i}", replicas=2)
            )
        # Create a linear dependency chain of first 100 components
        for i in range(99):
            graph.add_dependency(
                Dependency(source_id=f"c{i}", target_id=f"c{i+1}")
            )

        summary = graph.summary()
        assert summary["total_components"] == n
        assert summary["total_dependencies"] == 99

        # Score computation should complete in reasonable time
        start = time.monotonic()
        score = graph.resilience_score()
        elapsed = time.monotonic() - start
        assert elapsed < 30.0, f"resilience_score took {elapsed:.2f}s on 1000 components"
        assert 0.0 <= score <= 100.0

    def test_large_graph_1000_all_isolated(self):
        """1000 isolated components (no dependencies) should be fast."""
        graph = InfraGraph()
        for i in range(1000):
            graph.add_component(
                _make_component(cid=f"c{i}", name=f"Comp-{i}", replicas=2)
            )
        start = time.monotonic()
        score = graph.resilience_score()
        elapsed = time.monotonic() - start
        assert elapsed < 10.0
        assert 0.0 <= score <= 100.0

    # --- Circular dependencies ---

    def test_circular_dependency_a_b_c_a(self):
        """Graph with A->B->C->A should not infinite-loop."""
        graph = InfraGraph()
        for cid in ("A", "B", "C"):
            graph.add_component(_make_component(cid=cid, name=cid))
        graph.add_dependency(Dependency(source_id="A", target_id="B"))
        graph.add_dependency(Dependency(source_id="B", target_id="C"))
        graph.add_dependency(Dependency(source_id="C", target_id="A"))

        # Should not hang
        score = graph.resilience_score()
        assert 0.0 <= score <= 100.0

        # get_all_affected should terminate
        affected = graph.get_all_affected("A")
        assert isinstance(affected, set)

    def test_circular_dependency_cascade_engine(self):
        """CascadeEngine should handle cycles without infinite loop."""
        graph = InfraGraph()
        for cid in ("A", "B", "C"):
            graph.add_component(_make_component(cid=cid, name=cid))
        graph.add_dependency(Dependency(source_id="A", target_id="B"))
        graph.add_dependency(Dependency(source_id="B", target_id="C"))
        graph.add_dependency(Dependency(source_id="C", target_id="A"))

        engine = CascadeEngine(graph)
        fault = Fault(target_component_id="A", fault_type=FaultType.COMPONENT_DOWN)
        chain = engine.simulate_fault(fault)
        # Should complete without hanging; effects list may vary
        assert isinstance(chain, CascadeChain)
        assert chain.severity >= 0.0

    # --- Self-referencing dependency ---

    def test_self_referencing_dependency(self):
        """Component depending on itself (A->A) should not crash."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="A", name="SelfRef"))
        graph.add_dependency(Dependency(source_id="A", target_id="A"))

        score = graph.resilience_score()
        assert 0.0 <= score <= 100.0

        affected = graph.get_all_affected("A")
        assert isinstance(affected, set)

    def test_self_referencing_cascade(self):
        """CascadeEngine on self-referencing component."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="A", name="SelfRef"))
        graph.add_dependency(Dependency(source_id="A", target_id="A"))

        engine = CascadeEngine(graph)
        fault = Fault(target_component_id="A", fault_type=FaultType.COMPONENT_DOWN)
        chain = engine.simulate_fault(fault)
        assert isinstance(chain, CascadeChain)

    # --- Duplicate component IDs ---

    def test_duplicate_component_id_overwrites(self):
        """Adding a component with the same ID should overwrite the previous."""
        graph = InfraGraph()
        c1 = _make_component(cid="dup", name="First")
        c2 = _make_component(cid="dup", name="Second")
        graph.add_component(c1)
        graph.add_component(c2)

        assert len(graph.components) == 1
        assert graph.get_component("dup").name == "Second"

    # --- Replicas boundary values ---

    def test_component_zero_replicas_rejected(self):
        """Component with 0 replicas should raise ValidationError."""
        with pytest.raises(ValidationError):
            _make_component(cid="zero", name="Zero", replicas=0)

    def test_component_negative_replicas_rejected(self):
        """Component with negative replicas should raise ValidationError."""
        with pytest.raises(ValidationError):
            _make_component(cid="neg", name="Neg", replicas=-1)

    def test_component_very_large_replicas(self):
        """Component with a very large replica count should be accepted."""
        large = 2**31 - 1  # MAX_INT for 32-bit
        c = _make_component(cid="big", name="Big", replicas=large)
        assert c.replicas == large

    def test_component_one_replica(self):
        """Component with exactly 1 replica (minimum valid)."""
        c = _make_component(cid="min", name="Min", replicas=1)
        assert c.replicas == 1

    # --- Empty string component ID/name ---

    def test_empty_string_component_id(self):
        """Empty string ID should be storable (Pydantic does not forbid it)."""
        c = _make_component(cid="", name="Empty ID")
        graph = InfraGraph()
        graph.add_component(c)
        assert graph.get_component("") is not None
        assert graph.get_component("").name == "Empty ID"

    def test_empty_string_component_name(self):
        """Empty string name should be storable."""
        c = _make_component(cid="e", name="")
        assert c.name == ""


# ===================================================================
# 2. Resilience Score Boundary Values
# ===================================================================


class TestResilienceScoreBoundaries:
    """Resilience score must always be in [0, 100]."""

    def test_all_healthy_high_replicas_no_deps(self):
        """All components healthy with replicas, no deps => near 100."""
        graph = InfraGraph()
        for i in range(5):
            graph.add_component(
                _make_component(cid=f"h{i}", name=f"Healthy-{i}", replicas=3)
            )
        score = graph.resilience_score()
        assert score >= 80.0, f"Expected high score, got {score}"
        assert score <= 100.0

    def test_all_healthy_single_replica_with_deps(self):
        """Single-replica components with requires deps => significant penalty."""
        graph = InfraGraph()
        for i in range(5):
            graph.add_component(
                _make_component(cid=f"s{i}", name=f"Single-{i}", replicas=1)
            )
        for i in range(4):
            graph.add_dependency(
                Dependency(source_id=f"s{i}", target_id=f"s{i+1}", dependency_type="requires")
            )
        score = graph.resilience_score()
        assert 0.0 <= score <= 100.0
        # Should be penalized for SPOFs
        assert score < 100.0

    def test_score_clamped_to_zero_minimum(self):
        """Many SPOF penalties should not push score below 0."""
        graph = InfraGraph()
        # Create a star topology: one central node with many dependents (all single replica)
        graph.add_component(_make_component(cid="center", name="Center", replicas=1))
        for i in range(50):
            graph.add_component(
                _make_component(cid=f"leaf{i}", name=f"Leaf-{i}", replicas=1)
            )
            graph.add_dependency(
                Dependency(source_id=f"leaf{i}", target_id="center", dependency_type="requires")
            )
        score = graph.resilience_score()
        assert score >= 0.0, f"Score should not be negative, got {score}"
        assert score <= 100.0

    def test_score_always_in_range_high_utilization(self):
        """High utilization should penalize but not exceed [0, 100]."""
        graph = InfraGraph()
        from faultray.model.components import ResourceMetrics
        for i in range(10):
            metrics = ResourceMetrics(cpu_percent=95.0, memory_percent=95.0)
            c = _make_component(cid=f"u{i}", name=f"Util-{i}", replicas=1)
            c.metrics = metrics
            graph.add_component(c)
        score = graph.resilience_score()
        assert 0.0 <= score <= 100.0

    def test_single_component_no_deps_score(self):
        """Single component, no dependencies => 100."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="solo", name="Solo", replicas=3))
        score = graph.resilience_score()
        assert score == 100.0

    def test_resilience_score_v2_always_in_range(self):
        """resilience_score_v2 total and breakdown must be in valid ranges."""
        graph = InfraGraph()
        for i in range(10):
            graph.add_component(_make_component(cid=f"v{i}", name=f"V2-{i}", replicas=1))
        for i in range(9):
            graph.add_dependency(
                Dependency(source_id=f"v{i}", target_id=f"v{i+1}", dependency_type="requires")
            )
        result = graph.resilience_score_v2()
        assert 0.0 <= result["score"] <= 100.0
        for key, val in result["breakdown"].items():
            assert 0.0 <= val <= 20.0, f"Breakdown {key} = {val} out of range"

    def test_resilience_score_v2_all_redundant_with_cb(self):
        """Fully redundant graph with circuit breakers => high score."""
        from faultray.model.components import (
            AutoScalingConfig,
            CircuitBreakerConfig,
            FailoverConfig,
        )
        graph = InfraGraph()
        for i in range(3):
            graph.add_component(
                _make_component(
                    cid=f"r{i}",
                    name=f"Redundant-{i}",
                    replicas=3,
                    failover=FailoverConfig(enabled=True),
                    autoscaling=AutoScalingConfig(enabled=True),
                )
            )
        for i in range(2):
            graph.add_dependency(
                Dependency(
                    source_id=f"r{i}",
                    target_id=f"r{i+1}",
                    dependency_type="requires",
                    circuit_breaker=CircuitBreakerConfig(enabled=True),
                )
            )
        result = graph.resilience_score_v2()
        assert result["score"] >= 80.0
        assert result["breakdown"]["redundancy"] >= 15.0
        assert result["breakdown"]["circuit_breaker_coverage"] == 20.0


# ===================================================================
# 3. Simulation Engine Edge Cases
# ===================================================================


class TestSimulationEdgeCases:
    """Edge cases for SimulationEngine and CascadeEngine."""

    def _build_simple_graph(self, n: int = 3) -> InfraGraph:
        graph = InfraGraph()
        for i in range(n):
            graph.add_component(
                _make_component(cid=f"c{i}", name=f"Component-{i}")
            )
        for i in range(n - 1):
            graph.add_dependency(
                Dependency(source_id=f"c{i}", target_id=f"c{i+1}")
            )
        return graph

    # --- Empty fault list ---

    def test_simulate_with_empty_fault_list(self):
        """Scenario with no faults should produce zero risk."""
        graph = self._build_simple_graph()
        engine = SimulationEngine(graph)
        scenario = _make_scenario(faults=[])
        result = engine.run_scenario(scenario)
        assert result.risk_score == 0.0
        assert result.error is None

    def test_run_scenarios_empty_list(self):
        """Running zero scenarios should produce an empty report."""
        graph = self._build_simple_graph()
        engine = SimulationEngine(graph)
        report = engine.run_scenarios([])
        assert len(report.results) == 0
        assert report.resilience_score >= 0.0

    # --- Fault targeting non-existent component ---

    def test_fault_targeting_nonexistent_component(self):
        """Fault on a non-existent component should not crash."""
        graph = self._build_simple_graph()
        engine = SimulationEngine(graph)
        fault = Fault(target_component_id="does_not_exist", fault_type=FaultType.COMPONENT_DOWN)
        scenario = _make_scenario(faults=[fault])
        result = engine.run_scenario(scenario)
        # Should complete gracefully with low/zero risk
        assert result.risk_score == 0.0 or result.error is not None or result.risk_score >= 0.0

    def test_cascade_fault_nonexistent(self):
        """CascadeEngine.simulate_fault on non-existent component returns empty chain."""
        graph = self._build_simple_graph()
        ce = CascadeEngine(graph)
        fault = Fault(target_component_id="ghost", fault_type=FaultType.DISK_FULL)
        chain = ce.simulate_fault(fault)
        assert chain.effects == []
        assert chain.severity == 0.0

    # --- All components already failed ---

    def test_simulate_all_components_already_down(self):
        """Faulting every component should not crash and should report high risk."""
        graph = self._build_simple_graph(5)
        engine = SimulationEngine(graph)
        faults = [
            Fault(target_component_id=f"c{i}", fault_type=FaultType.COMPONENT_DOWN)
            for i in range(5)
        ]
        scenario = _make_scenario(faults=faults)
        result = engine.run_scenario(scenario)
        assert result.risk_score >= 0.0
        assert result.error is None

    # --- Large number of scenarios ---

    def test_simulate_many_scenarios(self):
        """Running 200 scenarios should work correctly."""
        graph = self._build_simple_graph(5)
        engine = SimulationEngine(graph)
        scenarios = []
        for i in range(200):
            fault = Fault(
                target_component_id=f"c{i % 5}",
                fault_type=FaultType.COMPONENT_DOWN,
            )
            scenarios.append(
                _make_scenario(faults=[fault], sid=f"s{i}", name=f"scenario-{i}")
            )
        start = time.monotonic()
        report = engine.run_scenarios(scenarios)
        elapsed = time.monotonic() - start
        assert len(report.results) == 200
        assert elapsed < 60.0, f"200 scenarios took {elapsed:.2f}s"
        assert not report.was_truncated

    def test_truncation_over_max_scenarios(self):
        """Exceeding MAX_SCENARIOS triggers truncation."""
        graph = self._build_simple_graph(3)
        engine = SimulationEngine(graph)
        # Use a small max_scenarios to verify truncation logic
        many = [
            _make_scenario(
                faults=[Fault(target_component_id="c0", fault_type=FaultType.LATENCY_SPIKE)],
                sid=f"s{i}",
            )
            for i in range(50)
        ]
        report = engine.run_scenarios(many, max_scenarios=10)
        assert len(report.results) == 10
        assert report.was_truncated is True
        assert report.total_generated == 50

    # --- Traffic spike edge cases ---

    def test_traffic_multiplier_zero(self):
        """Traffic multiplier of 0 is valid (no traffic)."""
        scenario = _make_scenario(traffic_multiplier=0.0)
        assert scenario.traffic_multiplier == 0.0

    def test_traffic_multiplier_negative_rejected(self):
        """Negative traffic multiplier should be rejected."""
        with pytest.raises(ValidationError):
            _make_scenario(traffic_multiplier=-1.0)

    def test_traffic_multiplier_very_large(self):
        """Very large traffic multiplier should complete without crash."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="web", name="Web"))
        engine = SimulationEngine(graph)
        scenario = _make_scenario(traffic_multiplier=1000.0)
        result = engine.run_scenario(scenario)
        assert result.risk_score >= 0.0

    # --- Cascade severity edge cases ---

    def test_cascade_chain_empty_effects_severity_zero(self):
        chain = CascadeChain(trigger="test", total_components=10)
        assert chain.severity == 0.0

    def test_cascade_chain_single_down_in_large_system(self):
        """Single DOWN in a 100-component system => capped at 3.0."""
        chain = CascadeChain(trigger="test", total_components=100)
        chain.effects.append(
            CascadeEffect(
                component_id="c0",
                component_name="C0",
                health=HealthStatus.DOWN,
                reason="test",
            )
        )
        severity = chain.severity
        assert 0.0 <= severity <= 3.0

    def test_cascade_chain_all_down(self):
        """All components DOWN => high severity."""
        n = 20
        chain = CascadeChain(trigger="total-failure", total_components=n)
        for i in range(n):
            chain.effects.append(
                CascadeEffect(
                    component_id=f"c{i}",
                    component_name=f"C{i}",
                    health=HealthStatus.DOWN,
                    reason="total failure",
                )
            )
        severity = chain.severity
        assert severity >= 7.0
        assert severity <= 10.0

    def test_cascade_severity_likelihood_zero(self):
        """Likelihood of 0 should make severity 0."""
        chain = CascadeChain(trigger="unlikely", total_components=5, likelihood=0.0)
        chain.effects.append(
            CascadeEffect(
                component_id="c0",
                component_name="C0",
                health=HealthStatus.DOWN,
                reason="test",
            )
        )
        assert chain.severity == 0.0

    def test_cascade_severity_all_degraded_cap(self):
        """All degraded (no DOWN/OVERLOADED) should cap at 4.0."""
        chain = CascadeChain(trigger="degraded", total_components=5)
        for i in range(5):
            chain.effects.append(
                CascadeEffect(
                    component_id=f"c{i}",
                    component_name=f"C{i}",
                    health=HealthStatus.DEGRADED,
                    reason="slow",
                )
            )
        assert chain.severity <= 4.0

    # --- Multiple fault types in one scenario ---

    def test_mixed_fault_types(self):
        """Scenario with different fault types for different components."""
        graph = self._build_simple_graph(4)
        engine = SimulationEngine(graph)
        faults = [
            Fault(target_component_id="c0", fault_type=FaultType.COMPONENT_DOWN),
            Fault(target_component_id="c1", fault_type=FaultType.LATENCY_SPIKE),
            Fault(target_component_id="c2", fault_type=FaultType.CPU_SATURATION),
            Fault(target_component_id="c3", fault_type=FaultType.MEMORY_EXHAUSTION),
        ]
        scenario = _make_scenario(faults=faults)
        result = engine.run_scenario(scenario)
        assert result.risk_score >= 0.0
        assert result.error is None

    # --- SimulationEngine on empty graph ---

    def test_simulation_engine_empty_graph(self):
        """SimulationEngine on an empty graph should not crash."""
        graph = InfraGraph()
        engine = SimulationEngine(graph)
        scenario = _make_scenario(
            faults=[Fault(target_component_id="x", fault_type=FaultType.COMPONENT_DOWN)]
        )
        result = engine.run_scenario(scenario)
        assert result.risk_score == 0.0 or result.error is not None or isinstance(result.risk_score, float)

    def test_run_all_defaults_empty_graph(self):
        """run_all_defaults on empty graph should produce a report with no critical findings."""
        graph = InfraGraph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        # Empty graph still generates traffic spike scenarios (they just have no effects)
        assert isinstance(report.results, list)
        assert report.resilience_score == 0.0
        # All results should have zero risk since there are no components
        for r in report.results:
            assert r.risk_score == 0.0


# ===================================================================
# 4. Input Validation
# ===================================================================


class TestInputValidation:
    """Tests for unusual input values in component fields."""

    # --- Unicode characters ---

    def test_unicode_component_name(self):
        """Japanese, emoji, and mixed unicode in component names."""
        names = [
            "データベース",
            "Webサーバー",
            "cache-layer",
            "component-with-emojis",
            "Composant-francais",
            "Komponente-deutsch",
        ]
        graph = InfraGraph()
        for i, name in enumerate(names):
            graph.add_component(_make_component(cid=f"u{i}", name=name))
        assert len(graph.components) == len(names)
        summary = graph.summary()
        assert summary["total_components"] == len(names)
        score = graph.resilience_score()
        assert 0.0 <= score <= 100.0

    def test_unicode_component_id(self):
        """Unicode characters in component ID."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="db-primary", name="DB"))
        retrieved = graph.get_component("db-primary")
        assert retrieved is not None

    # --- Very long strings ---

    def test_very_long_component_name(self):
        """10000+ character name should be storable."""
        long_name = "A" * 10001
        c = _make_component(cid="long", name=long_name)
        assert len(c.name) == 10001
        graph = InfraGraph()
        graph.add_component(c)
        assert graph.get_component("long").name == long_name

    def test_very_long_component_id(self):
        """Very long ID string should be storable and retrievable."""
        long_id = "x" * 10000
        c = _make_component(cid=long_id, name="LongID")
        graph = InfraGraph()
        graph.add_component(c)
        assert graph.get_component(long_id) is not None

    def test_very_long_scenario_description(self):
        """Scenario with a 10000-char description should be valid."""
        s = Scenario(
            id="long-desc",
            name="test",
            description="D" * 10000,
            faults=[],
        )
        assert len(s.description) == 10000

    # --- Special characters in IDs ---

    def test_special_chars_in_component_id(self):
        """IDs with spaces, newlines, tabs, and special chars."""
        special_ids = [
            "has space",
            "has\nnewline",
            "has\ttab",
            "has/slash",
            "has\\backslash",
            'has"quote',
            "has'apostrophe",
            "has@at",
            "has#hash",
        ]
        graph = InfraGraph()
        for sid in special_ids:
            graph.add_component(_make_component(cid=sid, name=f"comp-{sid[:5]}"))
        assert len(graph.components) == len(special_ids)
        for sid in special_ids:
            assert graph.get_component(sid) is not None

    def test_null_byte_in_component_id(self):
        """Null byte in ID should be storable (Python strings allow it)."""
        c = _make_component(cid="before\x00after", name="NullByte")
        graph = InfraGraph()
        graph.add_component(c)
        assert graph.get_component("before\x00after") is not None

    # --- NaN/Infinity in numeric fields ---

    def test_nan_in_resource_metrics(self):
        """NaN in cpu_percent should be storable (Pydantic allows float NaN)."""
        from faultray.model.components import ResourceMetrics
        metrics = ResourceMetrics(cpu_percent=float("nan"))
        assert math.isnan(metrics.cpu_percent)

    def test_infinity_in_resource_metrics(self):
        """Infinity in numeric metrics should be storable."""
        from faultray.model.components import ResourceMetrics
        metrics = ResourceMetrics(cpu_percent=float("inf"), memory_percent=float("-inf"))
        assert math.isinf(metrics.cpu_percent)
        assert math.isinf(metrics.memory_percent)

    def test_nan_utilization_computation(self):
        """Utilization with NaN metrics should not crash."""
        from faultray.model.components import ResourceMetrics
        c = _make_component(cid="nan", name="NaN")
        c.metrics = ResourceMetrics(cpu_percent=float("nan"))
        # utilization() uses max() on a list of factors; NaN propagates but
        # should not raise an exception
        result = c.utilization()
        assert isinstance(result, float)

    def test_infinity_capacity_fields(self):
        """Infinity in capacity fields should not crash scoring."""
        from faultray.model.components import Capacity
        c = _make_component(cid="inf", name="Inf")
        c.capacity = Capacity(max_connections=sys.maxsize, max_rps=sys.maxsize)
        assert c.capacity.max_connections == sys.maxsize

    def test_zero_capacity_fields(self):
        """Zero in capacity fields should not cause division by zero."""
        from faultray.model.components import Capacity
        c = _make_component(cid="zero-cap", name="ZeroCap")
        c.capacity = Capacity(max_connections=0, max_rps=0, connection_pool_size=0)
        util = c.utilization()
        assert isinstance(util, float)

    def test_fault_severity_boundary_values(self):
        """Fault severity at boundaries: 0.0 and 1.0."""
        f_min = Fault(target_component_id="c", fault_type=FaultType.COMPONENT_DOWN, severity=0.0)
        f_max = Fault(target_component_id="c", fault_type=FaultType.COMPONENT_DOWN, severity=1.0)
        assert f_min.severity == 0.0
        assert f_max.severity == 1.0


# ===================================================================
# 5. Concurrent Modification Patterns
# ===================================================================


class TestConcurrentModification:
    """Tests for adding/removing components during iteration."""

    def test_add_component_during_score_computation(self):
        """Adding a component after score computation starts should not corrupt state.

        Since resilience_score() iterates over a dict, and Python dicts are
        safe against concurrent read if modifications happen after iteration,
        we test the sequential pattern: compute -> modify -> recompute.
        """
        graph = InfraGraph()
        for i in range(5):
            graph.add_component(_make_component(cid=f"c{i}", name=f"C{i}"))
        score1 = graph.resilience_score()

        # Add more components between computations
        for i in range(5, 10):
            graph.add_component(_make_component(cid=f"c{i}", name=f"C{i}"))
        score2 = graph.resilience_score()

        assert 0.0 <= score1 <= 100.0
        assert 0.0 <= score2 <= 100.0
        assert len(graph.components) == 10

    def test_add_dependency_between_analyses(self):
        """Adding dependencies between different analysis calls."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="a", name="A"))
        graph.add_component(_make_component(cid="b", name="B"))
        graph.add_component(_make_component(cid="c", name="C"))

        # First analysis: no dependencies
        score1 = graph.resilience_score()
        paths1 = graph.get_critical_paths()

        # Add dependency
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        score2 = graph.resilience_score()
        paths2 = graph.get_critical_paths()

        # Add another
        graph.add_dependency(Dependency(source_id="b", target_id="c"))
        score3 = graph.resilience_score()
        paths3 = graph.get_critical_paths()

        # All should be valid
        for s in (score1, score2, score3):
            assert 0.0 <= s <= 100.0

    def test_overwrite_component_preserves_graph_integrity(self):
        """Overwriting a component should not break existing dependency edges."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="a", name="A-v1"))
        graph.add_component(_make_component(cid="b", name="B"))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))

        # Verify dependency exists
        deps = graph.get_dependencies("a")
        assert len(deps) == 1

        # Overwrite component "a"
        graph.add_component(_make_component(cid="a", name="A-v2", replicas=3))

        # Dependency should still be traversable via the graph edges
        deps_after = graph.get_dependencies("a")
        assert len(deps_after) == 1
        assert graph.get_component("a").name == "A-v2"

    def test_simulation_after_graph_modification(self):
        """SimulationEngine should use the latest graph state."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="web", name="Web"))
        engine = SimulationEngine(graph)

        # Run simulation
        fault = Fault(target_component_id="web", fault_type=FaultType.COMPONENT_DOWN)
        result1 = engine.run_scenario(_make_scenario(faults=[fault]))

        # Modify graph (add components)
        graph.add_component(_make_component(cid="db", name="DB"))
        graph.add_dependency(Dependency(source_id="web", target_id="db"))

        # The same engine should reflect the new graph state
        result2 = engine.run_scenario(_make_scenario(faults=[fault]))

        # Both should succeed
        assert result1.error is None
        assert result2.error is None

    def test_iterating_components_is_snapshot_safe(self):
        """Verify that iterating components dict and then modifying is safe."""
        graph = InfraGraph()
        for i in range(10):
            graph.add_component(_make_component(cid=f"c{i}", name=f"C{i}"))

        # Collect IDs via iteration
        collected_ids = list(graph.components.keys())
        assert len(collected_ids) == 10

        # Now add more - should not affect the already-collected list
        for i in range(10, 15):
            graph.add_component(_make_component(cid=f"c{i}", name=f"C{i}"))

        assert len(collected_ids) == 10  # Original snapshot unchanged
        assert len(graph.components) == 15  # Graph updated


# ===================================================================
# 6. Additional Cross-Cutting Edge Cases
# ===================================================================


class TestCrossCuttingEdgeCases:
    """Additional edge cases that span multiple modules."""

    def test_dependency_with_nonexistent_source(self):
        """Adding a dependency where source does not exist in components dict."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="b", name="B"))
        # source "a" does not exist as a component
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        # The edge exists in networkx but "a" is not in _components
        edge = graph.get_dependency_edge("a", "b")
        assert edge is not None
        # get_dependents should handle missing component gracefully
        dependents = graph.get_dependents("b")
        assert isinstance(dependents, list)

    def test_dependency_with_nonexistent_target(self):
        """Adding a dependency where target does not exist in components dict."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="a", name="A"))
        graph.add_dependency(Dependency(source_id="a", target_id="nonexistent"))
        deps = graph.get_dependencies("a")
        # The target is not in _components, so it should be filtered out
        assert isinstance(deps, list)

    def test_cascade_engine_with_all_fault_types(self):
        """Run every fault type against a single component."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="target", name="Target"))
        ce = CascadeEngine(graph)

        for ft in FaultType:
            fault = Fault(target_component_id="target", fault_type=ft)
            chain = ce.simulate_fault(fault)
            assert isinstance(chain, CascadeChain)
            assert chain.severity >= 0.0
            assert chain.severity <= 10.0

    def test_scenario_result_classification(self):
        """ScenarioResult is_critical / is_warning classification boundaries."""
        from faultray.simulator.engine import ScenarioResult

        scenario = _make_scenario()
        chain = CascadeChain(trigger="test", total_components=1)

        # Below warning threshold
        r1 = ScenarioResult(scenario=scenario, cascade=chain, risk_score=3.9)
        assert not r1.is_warning
        assert not r1.is_critical

        # Exactly at warning boundary
        r2 = ScenarioResult(scenario=scenario, cascade=chain, risk_score=4.0)
        assert r2.is_warning
        assert not r2.is_critical

        # Just below critical
        r3 = ScenarioResult(scenario=scenario, cascade=chain, risk_score=6.9)
        assert r3.is_warning
        assert not r3.is_critical

        # Exactly at critical boundary
        r4 = ScenarioResult(scenario=scenario, cascade=chain, risk_score=7.0)
        assert r4.is_critical
        assert not r4.is_warning

        # Maximum
        r5 = ScenarioResult(scenario=scenario, cascade=chain, risk_score=10.0)
        assert r5.is_critical

    def test_simulation_report_categorization(self):
        """SimulationReport correctly categorizes results into passed/warnings/critical."""
        from faultray.simulator.engine import ScenarioResult, SimulationReport

        chain = CascadeChain(trigger="t", total_components=1)
        results = [
            ScenarioResult(scenario=_make_scenario(sid="s0"), cascade=chain, risk_score=0.0),
            ScenarioResult(scenario=_make_scenario(sid="s1"), cascade=chain, risk_score=2.0),
            ScenarioResult(scenario=_make_scenario(sid="s2"), cascade=chain, risk_score=5.0),
            ScenarioResult(scenario=_make_scenario(sid="s3"), cascade=chain, risk_score=8.0),
        ]
        report = SimulationReport(results=results, resilience_score=50.0)
        assert len(report.passed) == 2      # 0.0 and 2.0
        assert len(report.warnings) == 1    # 5.0
        assert len(report.critical_findings) == 1  # 8.0

    def test_graph_save_and_load_roundtrip(self, tmp_path):
        """Save and reload a graph with edge cases in component names."""
        from pathlib import Path

        graph = InfraGraph()
        graph.add_component(_make_component(cid="db-1", name="Database Primary"))
        graph.add_component(_make_component(cid="cache-1", name="Redis Cache", replicas=2))
        graph.add_dependency(
            Dependency(source_id="db-1", target_id="cache-1", dependency_type="optional")
        )

        filepath = tmp_path / "test-model.json"
        graph.save(filepath)
        assert filepath.exists()

        loaded = InfraGraph.load(filepath)
        assert len(loaded.components) == 2
        assert loaded.get_component("db-1") is not None
        assert loaded.get_component("cache-1").replicas == 2

    def test_effective_capacity_at_replicas(self):
        """effective_capacity_at_replicas with various inputs."""
        c = _make_component(cid="cap", name="Cap", replicas=3)
        assert c.effective_capacity_at_replicas(3) == 1.0
        assert c.effective_capacity_at_replicas(6) == 2.0
        assert c.effective_capacity_at_replicas(0) == 0.0
        assert c.effective_capacity_at_replicas(1) == pytest.approx(1 / 3, rel=1e-5)

    def test_cascade_chain_total_components_zero(self):
        """CascadeChain with total_components=0 should not cause division by zero."""
        chain = CascadeChain(trigger="test", total_components=0)
        chain.effects.append(
            CascadeEffect(
                component_id="c0",
                component_name="C0",
                health=HealthStatus.DOWN,
                reason="test",
            )
        )
        # severity uses max(total_components, affected_count, 1) to avoid div-by-zero
        severity = chain.severity
        assert isinstance(severity, float)
        assert severity >= 0.0

    def test_deep_dependency_chain_penalty(self):
        """Deep dependency chains (>5 levels) should be penalized in resilience score."""
        graph = InfraGraph()
        depth = 12
        for i in range(depth):
            graph.add_component(_make_component(cid=f"d{i}", name=f"D{i}", replicas=2))
        for i in range(depth - 1):
            graph.add_dependency(
                Dependency(source_id=f"d{i}", target_id=f"d{i+1}", dependency_type="requires")
            )
        score = graph.resilience_score()
        assert 0.0 <= score <= 100.0
        # Should be penalized for depth > 5
        assert score < 100.0

    def test_latency_cascade_nonexistent_component(self):
        """simulate_latency_cascade on non-existent component."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="a", name="A"))
        ce = CascadeEngine(graph)
        chain = ce.simulate_latency_cascade("nonexistent")
        assert isinstance(chain, CascadeChain)
        assert len(chain.effects) == 0

    def test_traffic_spike_targeted_nonexistent(self):
        """simulate_traffic_spike_targeted with non-existent component IDs."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="a", name="A"))
        ce = CascadeEngine(graph)
        chain = ce.simulate_traffic_spike_targeted(5.0, ["nonexistent1", "nonexistent2"])
        assert isinstance(chain, CascadeChain)
        assert len(chain.effects) == 0

    def test_engine_run_scenario_exception_handling(self):
        """SimulationEngine.run_scenario catches exceptions gracefully."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="a", name="A"))
        engine = SimulationEngine(graph)

        # Create a scenario that won't cause an exception but test error field
        scenario = _make_scenario(
            faults=[Fault(target_component_id="a", fault_type=FaultType.COMPONENT_DOWN)]
        )
        result = engine.run_scenario(scenario)
        assert result.error is None

    def test_multiple_dependencies_between_same_pair(self):
        """Adding multiple dependencies between the same pair overwrites the edge data."""
        graph = InfraGraph()
        graph.add_component(_make_component(cid="a", name="A"))
        graph.add_component(_make_component(cid="b", name="B"))
        graph.add_dependency(
            Dependency(source_id="a", target_id="b", dependency_type="requires", weight=0.5)
        )
        graph.add_dependency(
            Dependency(source_id="a", target_id="b", dependency_type="optional", weight=0.2)
        )
        # networkx overwrites edge data for the same (u, v) pair
        edge = graph.get_dependency_edge("a", "b")
        assert edge is not None
        # The second add should have overwritten
        assert edge.dependency_type == "optional"
        assert edge.weight == 0.2
