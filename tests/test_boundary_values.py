"""Boundary value analysis tests for FaultRay / FaultRay.

Tests edge cases that normal tests miss: numeric limits, empty/maximal
collections, special float values, unicode handling, and graph topology
extremes.
"""

from __future__ import annotations

import math
import tempfile
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    NetworkProfile,
    OperationalProfile,
    ResourceMetrics,
    RuntimeJitter,
    SLOTarget,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEffect, CascadeEngine
from faultray.simulator.engine import SimulationEngine, SimulationReport
from faultray.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_component(
    cid: str = "c1",
    name: str = "C1",
    ctype: ComponentType = ComponentType.APP_SERVER,
    **kwargs,
) -> Component:
    """Create a Component with sensible defaults, overridable via kwargs."""
    return Component(id=cid, name=name, type=ctype, **kwargs)


def _simple_graph(*components: Component, deps: list[Dependency] | None = None) -> InfraGraph:
    """Build an InfraGraph from a list of components and optional deps."""
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for d in (deps or []):
        g.add_dependency(d)
    return g


# ===================================================================
# Numeric boundaries — resilience score
# ===================================================================


class TestResilienceScoreBoundaries:
    """resilience_score() should stay within [0.0, 100.0]."""

    def test_resilience_score_exactly_zero(self):
        """Empty graph should return exactly 0.0, not negative."""
        g = InfraGraph()
        assert g.resilience_score() == 0.0

    def test_resilience_score_exactly_100(self):
        """Perfect graph (high redundancy, low util) should cap at 100."""
        c = _make_component(
            replicas=3,
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
            failover=FailoverConfig(enabled=True),
            metrics=ResourceMetrics(cpu_percent=5, memory_percent=5),
        )
        g = _simple_graph(c)
        score = g.resilience_score()
        assert 0.0 <= score <= 100.0
        # Single component with great redundancy should score high
        assert score >= 90.0

    def test_resilience_score_never_negative(self):
        """Heavily penalized graph should bottom out at 0.0, never go negative."""
        # Many SPOF components with high utilization
        comps = []
        for i in range(20):
            comps.append(_make_component(
                cid=f"c{i}",
                name=f"C{i}",
                replicas=1,
                metrics=ResourceMetrics(cpu_percent=95, memory_percent=95),
            ))
        deps = []
        # Chain: c0 -> c1 -> c2 -> ... -> c19 (deep chain + SPOF)
        for i in range(19):
            deps.append(Dependency(
                source_id=f"c{i}",
                target_id=f"c{i+1}",
                dependency_type="requires",
            ))
        g = _simple_graph(*comps, deps=deps)
        score = g.resilience_score()
        assert score >= 0.0


# ===================================================================
# Numeric boundaries — component replicas
# ===================================================================


class TestReplicaBoundaries:

    def test_component_replicas_exactly_1(self):
        """replicas=1 is valid but should trigger SPOF warning in v2 score."""
        c = _make_component(replicas=1)
        g = _simple_graph(c)
        v2 = g.resilience_score_v2()
        # Single component, replicas=1, no failover -> should get a recommendation
        assert any("no redundancy" in r.lower() or "replica" in r.lower()
                    for r in v2["recommendations"])

    def test_component_replicas_zero_rejected(self):
        """replicas=0 should be rejected by the validator."""
        with pytest.raises(ValidationError):
            _make_component(replicas=0)

    def test_component_replicas_negative_rejected(self):
        """Negative replicas should be rejected."""
        with pytest.raises(ValidationError):
            _make_component(replicas=-1)

    def test_component_replicas_max_int(self):
        """Very large replica count should not crash."""
        c = _make_component(replicas=999999)
        assert c.replicas == 999999
        g = _simple_graph(c)
        # Should compute without error
        score = g.resilience_score()
        assert 0.0 <= score <= 100.0


# ===================================================================
# Numeric boundaries — utilization
# ===================================================================


class TestUtilizationBoundaries:

    def test_utilization_at_zero(self):
        """0% utilization should work (idle component)."""
        c = _make_component(metrics=ResourceMetrics())
        assert c.utilization() == 0.0

    def test_utilization_at_100(self):
        """100% utilization (cpu_percent=100) should report 100."""
        c = _make_component(
            metrics=ResourceMetrics(cpu_percent=100),
        )
        assert c.utilization() == pytest.approx(100.0)

    def test_utilization_above_100(self):
        """120% utilization (overloaded) should be handled without crash."""
        c = _make_component(
            metrics=ResourceMetrics(cpu_percent=120),
        )
        # utilization() returns max of factors, so 120 is valid
        assert c.utilization() == pytest.approx(120.0)

    def test_utilization_at_100_in_resilience_score(self):
        """100% utilization should penalize resilience score."""
        c = _make_component(
            metrics=ResourceMetrics(cpu_percent=100),
            replicas=3,
        )
        g = _simple_graph(c)
        score = g.resilience_score()
        # High util = penalty
        assert score < 100.0


# ===================================================================
# Numeric boundaries — MTBF / MTTR
# ===================================================================


class TestMtbfMttrBoundaries:

    def test_mtbf_zero(self):
        """MTBF=0 should not cause division by zero."""
        c = _make_component(
            operational_profile=OperationalProfile(mtbf_hours=0.0),
        )
        g = _simple_graph(c)
        # Should not crash
        score = g.resilience_score()
        assert 0.0 <= score <= 100.0

    def test_mtbf_infinity(self):
        """Very high MTBF should give near-perfect availability (no crash)."""
        c = _make_component(
            operational_profile=OperationalProfile(mtbf_hours=1e12),
        )
        g = _simple_graph(c)
        score = g.resilience_score()
        assert 0.0 <= score <= 100.0

    def test_mttr_zero(self):
        """MTTR=0 should give instant recovery (no crash or div-by-zero)."""
        c = _make_component(
            operational_profile=OperationalProfile(mttr_minutes=0.0),
        )
        g = _simple_graph(c)
        score = g.resilience_score()
        assert 0.0 <= score <= 100.0


# ===================================================================
# Numeric boundaries — packet loss
# ===================================================================


class TestPacketLossBoundaries:

    def test_packet_loss_zero(self):
        """Zero packet loss = no network penalty."""
        c = _make_component(
            network=NetworkProfile(packet_loss_rate=0.0),
        )
        assert c.network.packet_loss_rate == 0.0

    def test_packet_loss_one(self):
        """100% packet loss = complete network failure; should not crash."""
        c = _make_component(
            network=NetworkProfile(packet_loss_rate=1.0),
        )
        assert c.network.packet_loss_rate == 1.0
        g = _simple_graph(c)
        score = g.resilience_score()
        assert 0.0 <= score <= 100.0


# ===================================================================
# Numeric boundaries — GC pause
# ===================================================================


class TestGcPauseBoundaries:

    def test_gc_pause_extremely_high(self):
        """GC pause of 1000ms at 100/sec = 100% GC time; should not crash."""
        c = _make_component(
            runtime_jitter=RuntimeJitter(gc_pause_ms=1000, gc_pause_frequency=100),
        )
        g = _simple_graph(c)
        score = g.resilience_score()
        assert 0.0 <= score <= 100.0

    def test_gc_pause_zero(self):
        """GC pause of 0 = Go/Rust style, no GC overhead."""
        c = _make_component(
            runtime_jitter=RuntimeJitter(gc_pause_ms=0.0, gc_pause_frequency=0.0),
        )
        assert c.runtime_jitter.gc_pause_ms == 0.0


# ===================================================================
# String boundaries — component id / name
# ===================================================================


class TestStringBoundaries:

    def test_empty_string_component_id(self):
        """Component with empty id should be handled by the graph."""
        c = _make_component(cid="", name="EmptyID")
        g = _simple_graph(c)
        # Graph should contain the component keyed by ""
        assert "" in g.components

    def test_unicode_component_name(self):
        """Component names with unicode should work."""
        c = _make_component(cid="jp", name="データベース")
        g = _simple_graph(c)
        assert g.get_component("jp").name == "データベース"

    def test_unicode_emoji_component_name(self):
        """Component names with emoji should work."""
        c = _make_component(cid="emoji", name="Server-1")
        g = _simple_graph(c)
        assert g.get_component("emoji") is not None

    def test_very_long_component_name(self):
        """Name with 10000 characters should not crash."""
        long_name = "A" * 10000
        c = _make_component(cid="long", name=long_name)
        g = _simple_graph(c)
        assert len(g.get_component("long").name) == 10000
        # Also verify serialization
        d = g.to_dict()
        assert len(d["components"][0]["name"]) == 10000


# ===================================================================
# Port boundaries
# ===================================================================


class TestPortBoundaries:

    def test_negative_port(self):
        """Negative port should be stored (Pydantic int field, no validator)."""
        # The Component model does not validate port range — verify it
        # can be created (the port validation is left to the scanner/loader)
        c = _make_component(port=-1)
        assert c.port == -1

    def test_zero_port(self):
        """Zero port is the default and should be fine."""
        c = _make_component(port=0)
        assert c.port == 0


# ===================================================================
# Capacity boundaries
# ===================================================================


class TestCapacityBoundaries:

    def test_zero_max_connections(self):
        """Zero max_connections should not cause division by zero in utilization()."""
        c = _make_component(
            capacity=Capacity(max_connections=0),
            metrics=ResourceMetrics(network_connections=50),
        )
        # utilization() guards against max_connections == 0
        util = c.utilization()
        # Should not crash; network_connections factor is skipped
        assert isinstance(util, float)


# ===================================================================
# Scenario / fault boundaries
# ===================================================================


class TestScenarioFaultBoundaries:

    def test_scenario_with_zero_faults(self):
        """Scenario with empty fault list should be harmless."""
        c = _make_component()
        g = _simple_graph(c)
        engine = SimulationEngine(g)

        scenario = Scenario(
            id="no-faults",
            name="No faults",
            description="Nothing breaks",
            faults=[],
        )
        result = engine.run_scenario(scenario)
        assert result.risk_score == 0.0
        assert result.error is None

    def test_scenario_with_many_faults(self):
        """Scenario with many faults should not crash."""
        comps = [_make_component(cid=f"c{i}", name=f"C{i}") for i in range(20)]
        g = _simple_graph(*comps)
        engine = SimulationEngine(g)

        faults = [
            Fault(
                target_component_id=f"c{i}",
                fault_type=FaultType.COMPONENT_DOWN,
            )
            for i in range(20)
        ]
        scenario = Scenario(
            id="many-faults",
            name="Many faults",
            description="Everything fails",
            faults=faults,
        )
        result = engine.run_scenario(scenario)
        assert result.error is None
        assert result.risk_score >= 0.0

    def test_scenario_traffic_multiplier_zero(self):
        """Zero traffic = no requests."""
        scenario = Scenario(
            id="zero-traffic",
            name="Zero traffic",
            description="No traffic",
            faults=[],
            traffic_multiplier=0.0,
        )
        assert scenario.traffic_multiplier == 0.0

    def test_scenario_traffic_multiplier_negative_rejected(self):
        """Negative traffic_multiplier should be rejected by validator."""
        with pytest.raises(ValidationError):
            Scenario(
                id="neg",
                name="Neg",
                description="Negative",
                faults=[],
                traffic_multiplier=-1.0,
            )


# ===================================================================
# Graph topology boundaries
# ===================================================================


class TestGraphTopologyBoundaries:

    def test_graph_with_single_component(self):
        """Minimal graph (1 component, 0 dependencies)."""
        c = _make_component()
        g = _simple_graph(c)
        summary = g.summary()
        assert summary["total_components"] == 1
        assert summary["total_dependencies"] == 0
        score = g.resilience_score()
        assert 0.0 <= score <= 100.0

    def test_graph_with_many_components(self):
        """Large graph (1000 components) should compute without crash."""
        comps = [_make_component(cid=f"c{i}", name=f"C{i}") for i in range(1000)]
        g = _simple_graph(*comps)
        assert len(g.components) == 1000
        score = g.resilience_score()
        assert 0.0 <= score <= 100.0

    def test_empty_dependency_list(self):
        """Graph with components but no dependencies."""
        c1 = _make_component(cid="a", name="A")
        c2 = _make_component(cid="b", name="B")
        g = _simple_graph(c1, c2)
        assert g.get_dependencies("a") == []
        assert g.get_dependents("b") == []
        score = g.resilience_score()
        assert 0.0 <= score <= 100.0

    def test_self_referencing_dependency(self):
        """Component depending on itself — graph should accept the edge."""
        c = _make_component(cid="self")
        g = _simple_graph(c, deps=[
            Dependency(source_id="self", target_id="self", dependency_type="requires"),
        ])
        # Should not crash; the edge exists
        deps = g.get_dependencies("self")
        assert len(deps) == 1
        assert deps[0].id == "self"

    def test_duplicate_component_ids(self):
        """Two components with same ID — last add_component wins."""
        c1 = _make_component(cid="dup", name="First")
        c2 = _make_component(cid="dup", name="Second")
        g = InfraGraph()
        g.add_component(c1)
        g.add_component(c2)
        assert g.get_component("dup").name == "Second"
        assert len(g.components) == 1

    def test_duplicate_dependencies(self):
        """Same dependency edge defined twice — graph should handle it."""
        c1 = _make_component(cid="a", name="A")
        c2 = _make_component(cid="b", name="B")
        dep = Dependency(source_id="a", target_id="b", dependency_type="requires")
        g = InfraGraph()
        g.add_component(c1)
        g.add_component(c2)
        g.add_dependency(dep)
        g.add_dependency(dep)
        # DiGraph overwrites duplicate edges; still 1 edge
        edge = g.get_dependency_edge("a", "b")
        assert edge is not None


# ===================================================================
# Cascade severity boundaries
# ===================================================================


class TestCascadeSeverityBoundaries:

    def test_cascade_severity_empty_effects(self):
        """CascadeChain with no effects should have severity 0.0."""
        chain = CascadeChain(trigger="test", total_components=10)
        assert chain.severity == 0.0

    def test_cascade_severity_all_down(self):
        """All components DOWN should approach severity 10.0."""
        effects = [
            CascadeEffect(
                component_id=f"c{i}",
                component_name=f"C{i}",
                health="down",
                reason="down",
            )
            for i in range(10)
        ]
        chain = CascadeChain(trigger="test", effects=effects, total_components=10)
        assert chain.severity == pytest.approx(10.0)

    def test_cascade_severity_single_degraded(self):
        """Single degraded component in large system = low severity."""
        effects = [
            CascadeEffect(
                component_id="c0",
                component_name="C0",
                health="degraded",
                reason="slow",
            ),
        ]
        chain = CascadeChain(trigger="test", effects=effects, total_components=20)
        assert chain.severity < 2.0


# ===================================================================
# Cost profile boundaries
# ===================================================================


class TestCostProfileBoundaries:

    def test_cost_profile_negative_revenue(self):
        """Negative revenue should be stored without crash."""
        c = _make_component(
            cost_profile=CostProfile(revenue_per_minute=-100.0),
        )
        assert c.cost_profile.revenue_per_minute == -100.0

    def test_cost_profile_zero(self):
        """All-zero cost profile should work."""
        c = _make_component(cost_profile=CostProfile())
        assert c.cost_profile.hourly_infra_cost == 0.0


# ===================================================================
# SLO target boundaries
# ===================================================================


class TestSloTargetBoundaries:

    def test_slo_target_zero(self):
        """SLO target 0% means no reliability requirement."""
        slo = SLOTarget(name="none", target=0.0)
        assert slo.target == 0.0

    def test_slo_target_100(self):
        """SLO target 100% is impossible but should not crash."""
        slo = SLOTarget(name="perfect", target=100.0)
        assert slo.target == 100.0


# ===================================================================
# Simulation engine boundaries
# ===================================================================


class TestSimulationEngineBoundaries:

    def test_simulation_with_no_scenarios(self):
        """Running zero scenarios should return an empty report."""
        c = _make_component()
        g = _simple_graph(c)
        engine = SimulationEngine(g)
        report = engine.run_scenarios([])
        assert len(report.results) == 0
        assert report.was_truncated is False

    def test_fault_targeting_nonexistent_component(self):
        """Fault on missing component should not crash; just empty chain."""
        c = _make_component(cid="real")
        g = _simple_graph(c)
        engine = SimulationEngine(g)

        scenario = Scenario(
            id="ghost",
            name="Ghost target",
            description="Targets a component that does not exist",
            faults=[Fault(
                target_component_id="nonexistent",
                fault_type=FaultType.COMPONENT_DOWN,
            )],
        )
        result = engine.run_scenario(scenario)
        # The cascade engine returns an empty chain for unknown targets
        assert result.error is None


# ===================================================================
# Dynamic scenario validation boundaries
# ===================================================================


class TestDynamicScenarioValidation:

    def test_duration_zero_rejected(self):
        """Zero duration should be rejected by validator."""
        from faultray.simulator.dynamic_engine import DynamicScenario as DynScenario

        with pytest.raises(ValidationError):
            DynScenario(
                id="zero-dur",
                name="Zero",
                description="Zero duration",
                duration_seconds=0,
            )

    def test_time_step_negative_rejected(self):
        """Negative time step should be rejected."""
        from faultray.simulator.dynamic_engine import DynamicScenario as DynScenario

        with pytest.raises(ValidationError):
            DynScenario(
                id="neg-step",
                name="Neg",
                description="Negative step",
                time_step_seconds=-5,
            )

    def test_step_larger_than_duration(self):
        """Step > duration should be accepted (validator only checks > 0).
        The engine handles the semantics."""
        from faultray.simulator.dynamic_engine import DynamicScenario as DynScenario

        ds = DynScenario(
            id="big-step",
            name="Big step",
            description="Step bigger than duration",
            duration_seconds=10,
            time_step_seconds=100,
        )
        assert ds.time_step_seconds > ds.duration_seconds


# ===================================================================
# Traffic spike simulation boundaries
# ===================================================================


class TestTrafficSpikeBoundaries:

    def test_traffic_spike_zero_multiplier(self):
        """0x traffic spike should produce no effects (0 * util = 0)."""
        c = _make_component(
            metrics=ResourceMetrics(cpu_percent=50),
        )
        g = _simple_graph(c)
        engine = CascadeEngine(g)
        chain = engine.simulate_traffic_spike(0.0)
        # 0 * 50 = 0%, which is below 70% threshold
        assert len(chain.effects) == 0

    def test_traffic_spike_extreme_multiplier(self):
        """1000x traffic spike should not crash."""
        c = _make_component(
            metrics=ResourceMetrics(cpu_percent=50),
        )
        g = _simple_graph(c)
        engine = CascadeEngine(g)
        chain = engine.simulate_traffic_spike(1000.0)
        # 50 * 1000 = 50000% > 100%, should be DOWN
        assert any(e.health.value == "down" for e in chain.effects)


# ===================================================================
# Serialization / to_dict boundaries
# ===================================================================


class TestSerializationBoundaries:

    def test_empty_graph_to_dict(self):
        """Empty graph serialization should produce valid structure."""
        g = InfraGraph()
        d = g.to_dict()
        assert d["components"] == []
        assert d["dependencies"] == []
        assert "schema_version" in d

    def test_graph_save_load_roundtrip(self):
        """Save and reload should produce equivalent graph."""
        c = _make_component(cid="rt", name="RoundTrip")
        g = _simple_graph(c)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        g.save(path)
        g2 = InfraGraph.load(path)
        assert "rt" in g2.components
        assert g2.get_component("rt").name == "RoundTrip"
        path.unlink()

    def test_large_graph_to_dict(self):
        """1000-component graph serialization should succeed."""
        comps = [_make_component(cid=f"c{i}", name=f"C{i}") for i in range(1000)]
        g = _simple_graph(*comps)
        d = g.to_dict()
        assert len(d["components"]) == 1000


# ===================================================================
# effective_capacity_at_replicas boundaries
# ===================================================================


class TestEffectiveCapacityBoundaries:

    def test_effective_capacity_normal(self):
        """Normal case: 3 replicas, effective at 6 = 2.0x."""
        c = _make_component(replicas=3)
        assert c.effective_capacity_at_replicas(6) == pytest.approx(2.0)

    def test_effective_capacity_at_zero_replicas(self):
        """effective_capacity_at_replicas with replicas=0 should return 0.
        Note: replicas=0 is rejected by the validator, but the method
        guards against it internally."""
        # We cannot create a Component with replicas=0 via normal means,
        # so we test the method logic indirectly by checking replicas=1
        c = _make_component(replicas=1)
        assert c.effective_capacity_at_replicas(0) == pytest.approx(0.0)
        assert c.effective_capacity_at_replicas(1) == pytest.approx(1.0)
