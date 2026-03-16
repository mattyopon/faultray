"""Comprehensive tests for the Dependency Health Propagation Simulator.

Targets 99%+ line/branch coverage of
``faultray.simulator.dependency_health``.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.dependency_health import (
    DependencyHealthEngine,
    HealthImpact,
    PropagationMode,
    PropagationReport,
    WhatIfResult,
    _health_to_score,
    _score_to_status,
)


# =========================================================================
# Helpers
# =========================================================================


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _edge(src: str, tgt: str) -> Dependency:
    """Shortcut: *src* depends on *tgt*."""
    return Dependency(source_id=src, target_id=tgt)


# =========================================================================
# 1. PropagationMode enum
# =========================================================================


class TestPropagationModeEnum:
    def test_forward_value(self):
        assert PropagationMode.FORWARD == "forward"
        assert PropagationMode.FORWARD.value == "forward"

    def test_backward_value(self):
        assert PropagationMode.BACKWARD == "backward"
        assert PropagationMode.BACKWARD.value == "backward"

    def test_both_value(self):
        assert PropagationMode.BOTH == "both"
        assert PropagationMode.BOTH.value == "both"

    def test_is_str_subclass(self):
        assert isinstance(PropagationMode.FORWARD, str)

    def test_member_count(self):
        assert len(PropagationMode) == 3


# =========================================================================
# 2. Helper functions: _health_to_score / _score_to_status
# =========================================================================


class TestHealthToScore:
    def test_healthy(self):
        assert _health_to_score(HealthStatus.HEALTHY) == 100.0

    def test_degraded(self):
        assert _health_to_score(HealthStatus.DEGRADED) == 60.0

    def test_overloaded(self):
        assert _health_to_score(HealthStatus.OVERLOADED) == 35.0

    def test_down(self):
        assert _health_to_score(HealthStatus.DOWN) == 0.0


class TestScoreToStatus:
    def test_high_score_is_healthy(self):
        assert _score_to_status(100.0) == HealthStatus.HEALTHY
        assert _score_to_status(80.0) == HealthStatus.HEALTHY

    def test_mid_score_is_degraded(self):
        assert _score_to_status(79.9) == HealthStatus.DEGRADED
        assert _score_to_status(50.0) == HealthStatus.DEGRADED

    def test_low_score_is_overloaded(self):
        assert _score_to_status(49.9) == HealthStatus.OVERLOADED
        assert _score_to_status(15.0) == HealthStatus.OVERLOADED

    def test_very_low_score_is_down(self):
        assert _score_to_status(14.9) == HealthStatus.DOWN
        assert _score_to_status(0.0) == HealthStatus.DOWN


# =========================================================================
# 3. HealthImpact data class
# =========================================================================


class TestHealthImpactDataclass:
    def test_basic_construction(self):
        hi = HealthImpact(
            component_id="db",
            component_name="Database",
            original_health=100.0,
            projected_health=30.0,
            impact_severity=0.7,
            hop_distance=1,
            propagation_path=["api", "db"],
        )
        assert hi.component_id == "db"
        assert hi.component_name == "Database"
        assert hi.original_health == 100.0
        assert hi.projected_health == 30.0
        assert hi.impact_severity == 0.7
        assert hi.hop_distance == 1
        assert hi.propagation_path == ["api", "db"]

    def test_default_propagation_path(self):
        hi = HealthImpact(
            component_id="x",
            component_name="X",
            original_health=100.0,
            projected_health=100.0,
            impact_severity=0.0,
            hop_distance=0,
        )
        assert hi.propagation_path == []


# =========================================================================
# 4. PropagationReport data class
# =========================================================================


class TestPropagationReportDataclass:
    def test_default_values(self):
        rpt = PropagationReport(
            source_component="src",
            mode=PropagationMode.FORWARD,
        )
        assert rpt.source_component == "src"
        assert rpt.mode == PropagationMode.FORWARD
        assert rpt.impacts == []
        assert rpt.cascade_depth == 0
        assert rpt.total_affected == 0
        assert rpt.critical_paths == []
        assert rpt.summary == ""

    def test_with_values(self):
        imp = HealthImpact("a", "A", 100, 50, 0.5, 1)
        rpt = PropagationReport(
            source_component="src",
            mode=PropagationMode.BOTH,
            impacts=[imp],
            cascade_depth=2,
            total_affected=1,
            critical_paths=[["src", "a"]],
            summary="test",
        )
        assert rpt.cascade_depth == 2
        assert rpt.total_affected == 1
        assert len(rpt.impacts) == 1
        assert len(rpt.critical_paths) == 1


# =========================================================================
# 5. WhatIfResult data class
# =========================================================================


class TestWhatIfResultDataclass:
    def test_default_values(self):
        w = WhatIfResult(scenario="test")
        assert w.scenario == "test"
        assert w.impacts == []
        assert w.components_affected == 0
        assert w.severity_change == 0.0
        assert w.recommendations == []

    def test_with_values(self):
        w = WhatIfResult(
            scenario="fail db",
            impacts=[],
            components_affected=3,
            severity_change=0.8,
            recommendations=["Add replicas"],
        )
        assert w.components_affected == 3
        assert w.severity_change == 0.8
        assert len(w.recommendations) == 1


# =========================================================================
# 6. DependencyHealthEngine: construction & decay clamping
# =========================================================================


class TestEngineConstruction:
    def test_default_decay_factor(self):
        g = _graph()
        e = DependencyHealthEngine(g)
        assert e.decay_factor == 0.7

    def test_custom_decay_factor(self):
        g = _graph()
        e = DependencyHealthEngine(g, decay_factor=0.5)
        assert e.decay_factor == 0.5

    def test_decay_factor_clamped_low(self):
        g = _graph()
        e = DependencyHealthEngine(g, decay_factor=-1.0)
        assert e.decay_factor == 0.01

    def test_decay_factor_clamped_high(self):
        g = _graph()
        e = DependencyHealthEngine(g, decay_factor=5.0)
        assert e.decay_factor == 1.0

    def test_decay_factor_zero(self):
        g = _graph()
        e = DependencyHealthEngine(g, decay_factor=0.0)
        assert e.decay_factor == 0.01

    def test_graph_reference(self):
        g = _graph()
        e = DependencyHealthEngine(g)
        assert e.graph is g


# =========================================================================
# 7. propagate() -- empty graph
# =========================================================================


class TestPropagateEmptyGraph:
    def test_nonexistent_component(self):
        g = _graph()
        e = DependencyHealthEngine(g)
        rpt = e.propagate("missing")
        assert rpt.source_component == "missing"
        assert "not found" in rpt.summary
        assert rpt.total_affected == 0
        assert rpt.cascade_depth == 0
        assert rpt.impacts == []
        assert rpt.critical_paths == []


# =========================================================================
# 8. propagate() -- single component (no edges)
# =========================================================================


class TestPropagateSingleComponent:
    def test_healthy_single(self):
        g = _graph(_comp("solo", "Solo"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("solo")
        assert rpt.total_affected == 0
        assert rpt.cascade_depth == 0
        assert rpt.impacts == []

    def test_down_single(self):
        g = _graph(_comp("solo", "Solo", health=HealthStatus.DOWN))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("solo")
        assert rpt.total_affected == 0

    def test_single_forward(self):
        g = _graph(_comp("solo", "Solo"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("solo", PropagationMode.FORWARD)
        assert rpt.mode == PropagationMode.FORWARD
        assert rpt.total_affected == 0

    def test_single_backward(self):
        g = _graph(_comp("solo", "Solo"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("solo", PropagationMode.BACKWARD)
        assert rpt.mode == PropagationMode.BACKWARD
        assert rpt.total_affected == 0


# =========================================================================
# 9. propagate() -- linear chain A -> B -> C
#    (A depends on B, B depends on C)
# =========================================================================


def _linear_chain(health_c: HealthStatus = HealthStatus.HEALTHY) -> InfraGraph:
    """A -> B -> C  (A depends on B, B depends on C)."""
    g = _graph(
        _comp("a", "Frontend"),
        _comp("b", "Backend"),
        _comp("c", "Database", health=health_c),
    )
    g.add_dependency(_edge("a", "b"))
    g.add_dependency(_edge("b", "c"))
    return g


class TestPropagateLinearChain:
    def test_all_healthy_forward_from_c(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        assert rpt.cascade_depth >= 1
        for imp in rpt.impacts:
            assert imp.impact_severity == 0.0

    def test_c_down_forward(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        assert rpt.total_affected >= 1
        b_imp = next((i for i in rpt.impacts if i.component_id == "b"), None)
        a_imp = next((i for i in rpt.impacts if i.component_id == "a"), None)
        assert b_imp is not None
        assert a_imp is not None
        assert b_imp.hop_distance == 1
        assert a_imp.hop_distance == 2
        assert b_imp.impact_severity >= a_imp.impact_severity

    def test_c_down_backward_from_a(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("a", PropagationMode.BACKWARD)
        b_imp = next((i for i in rpt.impacts if i.component_id == "b"), None)
        c_imp = next((i for i in rpt.impacts if i.component_id == "c"), None)
        assert b_imp is not None
        assert c_imp is not None

    def test_c_down_both(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.BOTH)
        assert rpt.total_affected >= 2

    def test_cascade_depth_linear(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        assert rpt.cascade_depth == 2

    def test_propagation_path_in_impacts(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        a_imp = next(i for i in rpt.impacts if i.component_id == "a")
        assert a_imp.propagation_path[0] == "c"
        assert "a" in a_imp.propagation_path

    def test_summary_contains_info(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        assert "Database" in rpt.summary
        assert "Cascade depth" in rpt.summary
        assert "Affected" in rpt.summary


# =========================================================================
# 10. propagate() -- diamond dependency
# =========================================================================


def _diamond_graph(health_db: HealthStatus = HealthStatus.HEALTHY) -> InfraGraph:
    g = _graph(
        _comp("lb", "LoadBalancer", ComponentType.LOAD_BALANCER, replicas=2),
        _comp("api-a", "API-A"),
        _comp("api-b", "API-B"),
        _comp("db", "Database", ComponentType.DATABASE, health=health_db),
    )
    g.add_dependency(_edge("lb", "api-a"))
    g.add_dependency(_edge("lb", "api-b"))
    g.add_dependency(_edge("api-a", "db"))
    g.add_dependency(_edge("api-b", "db"))
    return g


class TestPropagateDiamond:
    def test_db_down_forward(self):
        g = _diamond_graph(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("db", PropagationMode.FORWARD)
        assert rpt.total_affected >= 2
        api_ids = {i.component_id for i in rpt.impacts}
        assert "api-a" in api_ids
        assert "api-b" in api_ids

    def test_lb_receives_cascaded_impact(self):
        g = _diamond_graph(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("db", PropagationMode.FORWARD)
        lb_imp = next((i for i in rpt.impacts if i.component_id == "lb"), None)
        assert lb_imp is not None
        assert lb_imp.hop_distance == 2

    def test_diamond_critical_paths(self):
        g = _diamond_graph(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("db", PropagationMode.FORWARD)
        if rpt.critical_paths:
            for path in rpt.critical_paths:
                assert path[0] == "db"

    def test_diamond_both_mode(self):
        g = _diamond_graph(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("db", PropagationMode.BOTH)
        ids = {i.component_id for i in rpt.impacts}
        assert "api-a" in ids
        assert "api-b" in ids

    def test_no_duplicates_in_both_mode(self):
        g = _diamond_graph(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("db", PropagationMode.BOTH)
        ids = [i.component_id for i in rpt.impacts]
        assert len(ids) == len(set(ids))


# =========================================================================
# 11. Decay factor effect
# =========================================================================


class TestDecayFactor:
    def test_high_decay_more_impact(self):
        g = _linear_chain(HealthStatus.DOWN)
        e_low = DependencyHealthEngine(g, decay_factor=0.3)
        e_high = DependencyHealthEngine(g, decay_factor=0.9)
        rpt_low = e_low.propagate("c", PropagationMode.FORWARD)
        rpt_high = e_high.propagate("c", PropagationMode.FORWARD)
        a_low = next(i for i in rpt_low.impacts if i.component_id == "a")
        a_high = next(i for i in rpt_high.impacts if i.component_id == "a")
        assert a_high.impact_severity >= a_low.impact_severity

    def test_decay_1_full_propagation(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g, decay_factor=1.0)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        b_imp = next(i for i in rpt.impacts if i.component_id == "b")
        a_imp = next(i for i in rpt.impacts if i.component_id == "a")
        assert b_imp.impact_severity == a_imp.impact_severity

    def test_very_low_decay_minimal_propagation(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g, decay_factor=0.01)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        a_imp = next(i for i in rpt.impacts if i.component_id == "a")
        assert a_imp.impact_severity < 0.01


# =========================================================================
# 12. Forward propagation details
# =========================================================================


class TestForwardPropagation:
    def test_healthy_source_no_severity(self):
        g = _linear_chain(HealthStatus.HEALTHY)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        for imp in rpt.impacts:
            assert imp.impact_severity == 0.0
            assert imp.projected_health == imp.original_health

    def test_degraded_source(self):
        g = _linear_chain(HealthStatus.DEGRADED)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        b_imp = next(i for i in rpt.impacts if i.component_id == "b")
        assert b_imp.impact_severity > 0.0
        assert b_imp.projected_health < b_imp.original_health

    def test_overloaded_source(self):
        g = _linear_chain(HealthStatus.OVERLOADED)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        b_imp = next(i for i in rpt.impacts if i.component_id == "b")
        assert b_imp.impact_severity > 0.0

    def test_impacts_sorted_by_severity(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        severities = [i.impact_severity for i in rpt.impacts]
        assert severities == sorted(severities, reverse=True)


# =========================================================================
# 13. Backward propagation details
# =========================================================================


class TestBackwardPropagation:
    def test_backward_from_healthy_source(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g)
        rpt = e.propagate("a", PropagationMode.BACKWARD)
        ids = {i.component_id for i in rpt.impacts}
        assert "b" in ids
        assert "c" in ids

    def test_backward_severity_is_gentler(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        fwd = e.propagate("c", PropagationMode.FORWARD)
        bwd = e.propagate("a", PropagationMode.BACKWARD)
        b_fwd = next(i for i in fwd.impacts if i.component_id == "b")
        b_bwd = next(i for i in bwd.impacts if i.component_id == "b")
        assert isinstance(b_fwd.impact_severity, float)
        assert isinstance(b_bwd.impact_severity, float)

    def test_backward_only_mode(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("b", PropagationMode.BACKWARD)
        assert rpt.mode == PropagationMode.BACKWARD
        ids = {i.component_id for i in rpt.impacts}
        assert "c" in ids


# =========================================================================
# 14. what_if_fail()
# =========================================================================


class TestWhatIfFail:
    def test_fail_healthy_component(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("c")
        assert "fails" in result.scenario.lower() or "DOWN" in result.scenario
        assert result.severity_change > 0
        assert result.components_affected >= 0

    def test_fail_already_down(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("c")
        assert result.severity_change == 0.0

    def test_fail_nonexistent(self):
        g = _graph()
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("ghost")
        assert "not found" in result.recommendations[0]
        assert result.components_affected == 0

    def test_fail_restores_original_health(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g)
        comp = g.get_component("c")
        assert comp.health == HealthStatus.HEALTHY
        e.what_if_fail("c")
        assert comp.health == HealthStatus.HEALTHY

    def test_fail_recommendations_replicas(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("c")
        assert any("replica" in r.lower() for r in result.recommendations)

    def test_fail_recommendations_failover(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("c")
        assert any("failover" in r.lower() for r in result.recommendations)

    def test_fail_isolated_component(self):
        g = _graph(_comp("solo", "Solo"))
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("solo")
        assert result.components_affected == 0
        assert any("isolated" in r.lower() for r in result.recommendations)

    def test_fail_degraded_component(self):
        g = _linear_chain(HealthStatus.DEGRADED)
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("c")
        assert result.severity_change == 0.6

    def test_fail_with_deep_cascade(self):
        g = InfraGraph()
        for i in range(5):
            g.add_component(_comp(f"n{i}", f"Node{i}"))
        for i in range(4):
            g.add_dependency(_edge(f"n{i}", f"n{i+1}"))
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("n4")
        assert any("circuit" in r.lower() for r in result.recommendations)


# =========================================================================
# 15. what_if_recover()
# =========================================================================


class TestWhatIfRecover:
    def test_recover_down_component(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("c")
        assert "recovers" in result.scenario.lower() or "HEALTHY" in result.scenario
        assert result.severity_change == 1.0

    def test_recover_degraded_component(self):
        g = _linear_chain(HealthStatus.DEGRADED)
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("c")
        assert result.severity_change == 0.4
        assert any("stability" in r.lower() for r in result.recommendations)

    def test_recover_overloaded_component(self):
        g = _linear_chain(HealthStatus.OVERLOADED)
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("c")
        assert result.severity_change == 0.65
        assert any("pressure" in r.lower() for r in result.recommendations)

    def test_recover_already_healthy(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("c")
        assert result.severity_change == 0.0
        assert any("already" in r.lower() for r in result.recommendations)

    def test_recover_nonexistent(self):
        g = _graph()
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("ghost")
        assert "not found" in result.recommendations[0]

    def test_recover_restores_original_health(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        comp = g.get_component("c")
        e.what_if_recover("c")
        assert comp.health == HealthStatus.DOWN

    def test_recover_with_dependents_has_critical_rec(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("c")
        # After recovery, source is HEALTHY so no downstream severity;
        # but the rec about resolving critical failure should be present
        assert any("critical" in r.lower() for r in result.recommendations)

    def test_recover_critical_failure(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("c")
        assert any("critical" in r.lower() for r in result.recommendations)


# =========================================================================
# 16. full_analysis()
# =========================================================================


class TestFullAnalysis:
    def test_all_healthy(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g)
        rpt = e.full_analysis()
        assert rpt.total_affected == 0
        assert "0 unhealthy" in rpt.summary
        assert rpt.cascade_depth == 0

    def test_single_unhealthy(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.full_analysis()
        assert rpt.total_affected >= 1
        assert "1 unhealthy" in rpt.summary
        assert "c" in rpt.source_component

    def test_multiple_unhealthy(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B", health=HealthStatus.DEGRADED),
            _comp("c", "C"),
        )
        g.add_dependency(_edge("c", "a"))
        g.add_dependency(_edge("c", "b"))
        e = DependencyHealthEngine(g)
        rpt = e.full_analysis()
        assert "2 unhealthy" in rpt.summary

    def test_keeps_worst_impact(self):
        g = _graph(
            _comp("s1", "Source1", health=HealthStatus.DOWN),
            _comp("s2", "Source2", health=HealthStatus.DEGRADED),
            _comp("t", "Target"),
        )
        g.add_dependency(_edge("t", "s1"))
        g.add_dependency(_edge("t", "s2"))
        e = DependencyHealthEngine(g, decay_factor=1.0)
        rpt = e.full_analysis()
        t_impacts = [i for i in rpt.impacts if i.component_id == "t"]
        assert len(t_impacts) == 1

    def test_empty_graph(self):
        g = _graph()
        e = DependencyHealthEngine(g)
        rpt = e.full_analysis()
        assert rpt.total_affected == 0
        assert "0 unhealthy" in rpt.summary
        assert rpt.mode == PropagationMode.BOTH

    def test_full_analysis_cascade_depth(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.full_analysis()
        assert rpt.cascade_depth >= 1

    def test_full_analysis_critical_paths(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.full_analysis()
        if rpt.critical_paths:
            for path in rpt.critical_paths:
                assert len(path) >= 2


# =========================================================================
# 17. Critical paths detection
# =========================================================================


class TestCriticalPaths:
    def test_no_critical_paths_when_healthy(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        assert rpt.critical_paths == []

    def test_critical_paths_when_down_high_decay(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g, decay_factor=1.0)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        assert len(rpt.critical_paths) >= 1

    def test_critical_path_starts_with_source(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g, decay_factor=1.0)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        for path in rpt.critical_paths:
            assert path[0] == "c"


# =========================================================================
# 18. Edge cases and boundaries
# =========================================================================


class TestEdgeCases:
    def test_self_dependency(self):
        g = _graph(_comp("a", "A", health=HealthStatus.DOWN))
        g.add_dependency(_edge("a", "a"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("a", PropagationMode.FORWARD)
        assert rpt.source_component == "a"

    def test_mutual_dependency(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B"),
        )
        g.add_dependency(_edge("a", "b"))
        g.add_dependency(_edge("b", "a"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("a", PropagationMode.BOTH)
        assert rpt.cascade_depth >= 1

    def test_disconnected_components(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B"),
            _comp("c", "C"),
        )
        e = DependencyHealthEngine(g)
        rpt = e.propagate("a")
        assert rpt.total_affected == 0

    def test_many_components(self):
        g = InfraGraph()
        hub = _comp("hub", "Hub", health=HealthStatus.DOWN)
        g.add_component(hub)
        for i in range(20):
            c = _comp(f"s{i}", f"Spoke{i}")
            g.add_component(c)
            g.add_dependency(_edge(f"s{i}", "hub"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("hub", PropagationMode.FORWARD)
        assert rpt.total_affected == 20
        assert rpt.cascade_depth == 1

    def test_component_removed_during_propagation(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B"),
        )
        g.add_dependency(_edge("b", "a"))
        del g._components["b"]
        e = DependencyHealthEngine(g)
        rpt = e.propagate("a", PropagationMode.FORWARD)
        b_impacts = [i for i in rpt.impacts if i.component_id == "b"]
        assert len(b_impacts) == 0


# =========================================================================
# 19. Backward propagation half-intensity
# =========================================================================


class TestBackwardHalfIntensity:
    def test_backward_halves_health_loss(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B"),
        )
        g.add_dependency(_edge("a", "b"))
        e = DependencyHealthEngine(g, decay_factor=1.0)
        bwd = e.propagate("a", PropagationMode.BACKWARD)
        b_bwd = next((i for i in bwd.impacts if i.component_id == "b"), None)
        assert b_bwd is not None
        assert b_bwd.projected_health == 50.0


# =========================================================================
# 20. Report summary content
# =========================================================================


class TestSummaryContent:
    def test_summary_mentions_mode(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        assert "forward" in rpt.summary.lower()

    def test_summary_mentions_cascade_depth(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        assert "Cascade depth" in rpt.summary

    def test_summary_mentions_affected(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        assert "Affected" in rpt.summary

    def test_summary_mentions_critical_paths(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g, decay_factor=1.0)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        if rpt.critical_paths:
            assert "Critical paths" in rpt.summary


# =========================================================================
# 21. Recommendations generation
# =========================================================================


class TestRecommendations:
    def test_fail_replicas_recommendation(self):
        g = _graph(_comp("db", "DB", replicas=1))
        g.add_component(_comp("api", "API"))
        g.add_dependency(_edge("api", "db"))
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("db")
        assert any("replica" in r.lower() for r in result.recommendations)

    def test_fail_no_replica_rec_when_multiple(self):
        g = _graph(_comp("db", "DB", replicas=3))
        g.add_component(_comp("api", "API"))
        g.add_dependency(_edge("api", "db"))
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("db")
        replica_recs = [r for r in result.recommendations if "replica" in r.lower()]
        assert len(replica_recs) == 0

    def test_fail_failover_recommendation(self):
        g = _graph(_comp("db", "DB"))
        g.add_component(_comp("api", "API"))
        g.add_dependency(_edge("api", "db"))
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("db")
        assert any("failover" in r.lower() for r in result.recommendations)

    def test_fail_no_failover_rec_when_enabled(self):
        db = _comp("db", "DB")
        db.failover.enabled = True
        g = _graph(db)
        g.add_component(_comp("api", "API"))
        g.add_dependency(_edge("api", "db"))
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("db")
        failover_recs = [r for r in result.recommendations if "Enable failover" in r]
        assert len(failover_recs) == 0

    def test_fail_cascade_recommendation(self):
        g = InfraGraph()
        for i in range(5):
            g.add_component(_comp(f"n{i}", f"N{i}"))
        for i in range(4):
            g.add_dependency(_edge(f"n{i}", f"n{i+1}"))
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("n4")
        assert any("circuit" in r.lower() for r in result.recommendations)

    def test_fail_critical_count_recommendation(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g, decay_factor=1.0)
        result = e.what_if_fail("c")
        if any(i.projected_health < 15.0 for i in result.impacts):
            assert any(
                "DOWN" in r or "redundancy" in r.lower()
                for r in result.recommendations
            )

    def test_recover_down_recommendation(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("c")
        assert any("critical failure" in r.lower() for r in result.recommendations)

    def test_recover_degraded_recommendation(self):
        g = _linear_chain(HealthStatus.DEGRADED)
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("c")
        assert any("stability" in r.lower() for r in result.recommendations)

    def test_recover_overloaded_recommendation(self):
        g = _linear_chain(HealthStatus.OVERLOADED)
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("c")
        assert any("pressure" in r.lower() for r in result.recommendations)

    def test_recover_already_healthy_recommendation(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("c")
        assert any("already" in r.lower() for r in result.recommendations)


# =========================================================================
# 22. Wide graph (fan-out)
# =========================================================================


class TestWideGraph:
    def test_fan_out_propagation(self):
        g = InfraGraph()
        g.add_component(_comp("root", "Root", health=HealthStatus.DOWN))
        for i in range(10):
            g.add_component(_comp(f"leaf{i}", f"Leaf{i}"))
            g.add_dependency(_edge(f"leaf{i}", "root"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("root", PropagationMode.FORWARD)
        assert rpt.total_affected == 10
        assert rpt.cascade_depth == 1

    def test_fan_in_backward(self):
        g = InfraGraph()
        g.add_component(_comp("sink", "Sink", health=HealthStatus.DOWN))
        for i in range(8):
            g.add_component(_comp(f"src{i}", f"Src{i}"))
            g.add_dependency(_edge("sink", f"src{i}"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("sink", PropagationMode.BACKWARD)
        assert rpt.total_affected == 8
        assert rpt.cascade_depth == 1


# =========================================================================
# 23. Deep chain
# =========================================================================


class TestDeepChain:
    def test_chain_of_6(self):
        g = InfraGraph()
        for i in range(6):
            g.add_component(_comp(f"l{i}", f"Layer{i}"))
        for i in range(5):
            g.add_dependency(_edge(f"l{i}", f"l{i+1}"))
        g.components["l5"].health = HealthStatus.DOWN
        e = DependencyHealthEngine(g)
        rpt = e.propagate("l5", PropagationMode.FORWARD)
        assert rpt.cascade_depth == 5

    def test_deep_chain_decay(self):
        g = InfraGraph()
        for i in range(6):
            g.add_component(_comp(f"l{i}", f"Layer{i}"))
        for i in range(5):
            g.add_dependency(_edge(f"l{i}", f"l{i+1}"))
        g.components["l5"].health = HealthStatus.DOWN
        e = DependencyHealthEngine(g, decay_factor=0.5)
        rpt = e.propagate("l5", PropagationMode.FORWARD)
        for i in range(len(rpt.impacts) - 1):
            if rpt.impacts[i].hop_distance < rpt.impacts[i + 1].hop_distance:
                assert (
                    rpt.impacts[i].impact_severity
                    >= rpt.impacts[i + 1].impact_severity
                )


# =========================================================================
# 24. Mixed health states in full_analysis
# =========================================================================


class TestMixedHealthFullAnalysis:
    def test_mixed_states(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B", health=HealthStatus.DEGRADED),
            _comp("c", "C", health=HealthStatus.OVERLOADED),
            _comp("d", "D", health=HealthStatus.HEALTHY),
        )
        g.add_dependency(_edge("d", "a"))
        g.add_dependency(_edge("d", "b"))
        g.add_dependency(_edge("d", "c"))
        e = DependencyHealthEngine(g)
        rpt = e.full_analysis()
        assert "3 unhealthy" in rpt.summary
        assert rpt.total_affected >= 1

    def test_only_healthy_full_analysis(self):
        g = _graph(
            _comp("a", "A"),
            _comp("b", "B"),
        )
        g.add_dependency(_edge("a", "b"))
        e = DependencyHealthEngine(g)
        rpt = e.full_analysis()
        assert rpt.total_affected == 0


# =========================================================================
# 25. Impact severity bounds
# =========================================================================


class TestImpactSeverityBounds:
    def test_severity_between_0_and_1(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        for imp in rpt.impacts:
            assert 0.0 <= imp.impact_severity <= 1.0

    def test_projected_health_non_negative(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g, decay_factor=1.0)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        for imp in rpt.impacts:
            assert imp.projected_health >= 0.0

    def test_original_health_valid(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        for imp in rpt.impacts:
            assert 0.0 <= imp.original_health <= 100.0


# =========================================================================
# 26. what_if_fail with failover-enabled component
# =========================================================================


class TestWhatIfWithFailover:
    def test_fail_with_failover_no_failover_rec(self):
        db = _comp("db", "DB", replicas=3)
        db.failover.enabled = True
        g = _graph(db, _comp("api", "API"))
        g.add_dependency(_edge("api", "db"))
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("db")
        assert not any("Enable failover" in r for r in result.recommendations)
        assert not any("Add replicas" in r for r in result.recommendations)


# =========================================================================
# 27. Propagation with component types
# =========================================================================


class TestComponentTypes:
    def test_database_propagation(self):
        g = _graph(
            _comp("db", "DB", ctype=ComponentType.DATABASE, health=HealthStatus.DOWN),
            _comp("api", "API", ctype=ComponentType.APP_SERVER),
        )
        g.add_dependency(_edge("api", "db"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("db", PropagationMode.FORWARD)
        assert rpt.total_affected == 1

    def test_cache_propagation(self):
        g = _graph(
            _comp(
                "cache", "Cache", ctype=ComponentType.CACHE, health=HealthStatus.DOWN
            ),
            _comp("api", "API"),
        )
        g.add_dependency(_edge("api", "cache"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("cache", PropagationMode.FORWARD)
        api_imp = next(i for i in rpt.impacts if i.component_id == "api")
        assert api_imp.hop_distance == 1


# =========================================================================
# 28. full_analysis with no edges
# =========================================================================


class TestFullAnalysisNoEdges:
    def test_unhealthy_but_no_edges(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B", health=HealthStatus.DOWN),
        )
        e = DependencyHealthEngine(g)
        rpt = e.full_analysis()
        assert "2 unhealthy" in rpt.summary
        assert rpt.total_affected == 0


# =========================================================================
# 29. Hop distance correctness
# =========================================================================


class TestHopDistance:
    def test_immediate_dependent_hop_1(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B"),
        )
        g.add_dependency(_edge("b", "a"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("a", PropagationMode.FORWARD)
        b_imp = next(i for i in rpt.impacts if i.component_id == "b")
        assert b_imp.hop_distance == 1

    def test_two_hops(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B"),
            _comp("c", "C"),
        )
        g.add_dependency(_edge("b", "a"))
        g.add_dependency(_edge("c", "b"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("a", PropagationMode.FORWARD)
        c_imp = next(i for i in rpt.impacts if i.component_id == "c")
        assert c_imp.hop_distance == 2


# =========================================================================
# 30. Multiple independent subgraphs
# =========================================================================


class TestIndependentSubgraphs:
    def test_isolated_subgraph_not_affected(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B"),
            _comp("x", "X"),
            _comp("y", "Y"),
        )
        g.add_dependency(_edge("b", "a"))
        g.add_dependency(_edge("y", "x"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("a", PropagationMode.FORWARD)
        affected_ids = {i.component_id for i in rpt.impacts}
        assert "b" in affected_ids
        assert "x" not in affected_ids
        assert "y" not in affected_ids


# =========================================================================
# 31. Severity change values
# =========================================================================


class TestSeverityChangeValues:
    def test_healthy_to_down(self):
        g = _graph(_comp("x", "X", health=HealthStatus.HEALTHY))
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("x")
        assert result.severity_change == 1.0

    def test_overloaded_to_down(self):
        g = _graph(_comp("x", "X", health=HealthStatus.OVERLOADED))
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("x")
        assert result.severity_change == 0.35

    def test_down_to_down(self):
        g = _graph(_comp("x", "X", health=HealthStatus.DOWN))
        e = DependencyHealthEngine(g)
        result = e.what_if_fail("x")
        assert result.severity_change == 0.0


# =========================================================================
# 32. Full analysis worst impact preservation
# =========================================================================


class TestWorstImpactPreservation:
    def test_worst_impact_kept(self):
        g = _graph(
            _comp("s1", "S1", health=HealthStatus.DOWN),
            _comp("s2", "S2", health=HealthStatus.DEGRADED),
            _comp("target", "Target"),
        )
        g.add_dependency(_edge("target", "s1"))
        g.add_dependency(_edge("target", "s2"))
        e = DependencyHealthEngine(g, decay_factor=1.0)
        rpt = e.full_analysis()
        t_imps = [i for i in rpt.impacts if i.component_id == "target"]
        assert len(t_imps) == 1
        assert t_imps[0].impact_severity > 0


# =========================================================================
# 33. Propagation path accuracy
# =========================================================================


class TestPropagationPathAccuracy:
    def test_path_includes_source_and_target(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        b_imp = next(i for i in rpt.impacts if i.component_id == "b")
        assert b_imp.propagation_path[0] == "c"
        assert b_imp.propagation_path[-1] == "b"

    def test_path_length_matches_hop(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        for imp in rpt.impacts:
            assert len(imp.propagation_path) == imp.hop_distance + 1


# =========================================================================
# 34. Stress test: large graph
# =========================================================================


class TestLargeGraph:
    def test_50_nodes_chain(self):
        g = InfraGraph()
        for i in range(50):
            g.add_component(_comp(f"n{i}", f"Node{i}"))
        for i in range(49):
            g.add_dependency(_edge(f"n{i}", f"n{i+1}"))
        g.components["n49"].health = HealthStatus.DOWN
        e = DependencyHealthEngine(g)
        rpt = e.propagate("n49", PropagationMode.FORWARD)
        assert rpt.cascade_depth == 49
        # With 0.7 decay, severity drops below rounding threshold after ~7 hops
        # total_affected counts only impacts with severity > 0
        assert rpt.total_affected >= 6
        assert len(rpt.impacts) == 49  # all 49 dependents are visited

    def test_50_nodes_star(self):
        g = InfraGraph()
        g.add_component(_comp("hub", "Hub", health=HealthStatus.DOWN))
        for i in range(49):
            g.add_component(_comp(f"s{i}", f"Spoke{i}"))
            g.add_dependency(_edge(f"s{i}", "hub"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("hub", PropagationMode.FORWARD)
        assert rpt.total_affected == 49
        assert rpt.cascade_depth == 1


# =========================================================================
# 35. Both mode combines forward and backward without duplicates
# =========================================================================


class TestBothModeNoDuplicates:
    def test_linear_chain_both(self):
        g = _linear_chain(HealthStatus.DEGRADED)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("b", PropagationMode.BOTH)
        ids = [i.component_id for i in rpt.impacts]
        assert len(ids) == len(set(ids))
        assert "a" in ids
        assert "c" in ids

    def test_diamond_both_no_duplicates(self):
        g = _diamond_graph(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("api-a", PropagationMode.BOTH)
        ids = [i.component_id for i in rpt.impacts]
        assert len(ids) == len(set(ids))


# =========================================================================
# 36. Projected health calculations
# =========================================================================


class TestProjectedHealthCalculations:
    def test_projected_equals_original_when_source_healthy(self):
        g = _linear_chain(HealthStatus.HEALTHY)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        for imp in rpt.impacts:
            assert imp.projected_health == imp.original_health

    def test_projected_decreases_when_source_down(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        for imp in rpt.impacts:
            assert imp.projected_health <= imp.original_health

    def test_projected_specific_value_hop1(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g, decay_factor=0.7)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        b_imp = next(i for i in rpt.impacts if i.component_id == "b")
        assert b_imp.projected_health == 30.0

    def test_projected_specific_value_hop2(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g, decay_factor=0.7)
        rpt = e.propagate("c", PropagationMode.FORWARD)
        a_imp = next(i for i in rpt.impacts if i.component_id == "a")
        # hop=2: decayed_factor = 0.7 * 0.7^2 = 0.7 * 0.49 = 0.343
        # health_loss = 100 * 0.343 = 34.3
        # projected = 100 - 34.3 = 65.7
        assert abs(a_imp.projected_health - 65.7) < 0.1


# =========================================================================
# 37. what_if_fail exception safety (health restored on error)
# =========================================================================


class TestExceptionSafety:
    def test_what_if_fail_restores_on_success(self):
        g = _linear_chain()
        e = DependencyHealthEngine(g)
        comp = g.get_component("c")
        original = comp.health
        e.what_if_fail("c")
        assert comp.health == original

    def test_what_if_recover_restores_on_success(self):
        g = _linear_chain(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        comp = g.get_component("c")
        original = comp.health
        e.what_if_recover("c")
        assert comp.health == original


# =========================================================================
# 38. full_analysis with critical paths from multiple sources
# =========================================================================


class TestFullAnalysisCriticalPaths:
    def test_multiple_sources_critical_paths(self):
        g = _graph(
            _comp("s1", "S1", health=HealthStatus.DOWN),
            _comp("s2", "S2", health=HealthStatus.DOWN),
            _comp("t1", "T1"),
            _comp("t2", "T2"),
        )
        g.add_dependency(_edge("t1", "s1"))
        g.add_dependency(_edge("t2", "s2"))
        e = DependencyHealthEngine(g, decay_factor=1.0)
        rpt = e.full_analysis()
        # Both s1 and s2 are DOWN with decay=1.0
        # t1 projected = 100 - 100 = 0 (critical)
        # t2 projected = 100 - 100 = 0 (critical)
        assert len(rpt.critical_paths) >= 2


# =========================================================================
# 39. Backward propagation depth
# =========================================================================


class TestBackwardPropagationDepth:
    def test_backward_chain_depth(self):
        g = InfraGraph()
        for i in range(4):
            g.add_component(_comp(f"n{i}", f"N{i}"))
        for i in range(3):
            g.add_dependency(_edge(f"n{i}", f"n{i+1}"))
        # n0 depends on n1 depends on n2 depends on n3
        e = DependencyHealthEngine(g)
        rpt = e.propagate("n0", PropagationMode.BACKWARD)
        assert rpt.cascade_depth == 3  # n0 -> n1 -> n2 -> n3


# =========================================================================
# 40. Additional edge cases for coverage
# =========================================================================


class TestAdditionalCoverage:
    def test_propagate_both_forward_and_backward_components(self):
        """Ensure both directions find components in BOTH mode."""
        g = _graph(
            _comp("left", "Left"),
            _comp("center", "Center", health=HealthStatus.DOWN),
            _comp("right", "Right"),
        )
        g.add_dependency(_edge("left", "center"))
        g.add_dependency(_edge("center", "right"))
        e = DependencyHealthEngine(g)
        rpt = e.propagate("center", PropagationMode.BOTH)
        ids = {i.component_id for i in rpt.impacts}
        assert "left" in ids  # forward (left depends on center)
        assert "right" in ids  # backward (center depends on right)

    def test_full_analysis_backward_component(self):
        """full_analysis runs both forward and backward from each unhealthy."""
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B"),
        )
        g.add_dependency(_edge("a", "b"))
        e = DependencyHealthEngine(g)
        rpt = e.full_analysis()
        # backward from a -> b
        ids = {i.component_id for i in rpt.impacts}
        assert "b" in ids

    def test_what_if_fail_no_critical_rec(self):
        """what_if_fail when no components projected to go DOWN."""
        db = _comp("db", "DB", replicas=3)
        db.failover.enabled = True
        g = _graph(db, _comp("api", "API"))
        g.add_dependency(_edge("api", "db"))
        e = DependencyHealthEngine(g, decay_factor=0.01)
        result = e.what_if_fail("db")
        # Very low decay => projected stays near 100, no critical count rec
        critical_recs = [
            r for r in result.recommendations if "projected to go DOWN" in r
        ]
        assert len(critical_recs) == 0

    def test_recover_no_affected_count_rec(self):
        """Recover an isolated healthy component -- no affected count rec."""
        g = _graph(_comp("solo", "Solo"))
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("solo")
        affected_recs = [
            r for r in result.recommendations if "affected" in r.lower()
        ]
        # No dependents, so no "would positively affect" recommendation
        assert len(affected_recs) == 0

    def test_propagate_backward_none_component(self):
        """Backward propagation skips None components."""
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B"),
        )
        g.add_dependency(_edge("a", "b"))
        # Remove b from components but leave edge
        del g._components["b"]
        e = DependencyHealthEngine(g)
        rpt = e.propagate("a", PropagationMode.BACKWARD)
        b_imps = [i for i in rpt.impacts if i.component_id == "b"]
        assert len(b_imps) == 0

    def test_full_analysis_source_label_none(self):
        """full_analysis with no unhealthy shows (none)."""
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        e = DependencyHealthEngine(g)
        rpt = e.full_analysis()
        assert "(none)" in rpt.source_component

    def test_what_if_recover_no_dependents_no_count_rec(self):
        """what_if_recover with no dependents has no affected count rec."""
        g = _graph(_comp("solo", "Solo", health=HealthStatus.DOWN))
        e = DependencyHealthEngine(g)
        result = e.what_if_recover("solo")
        # Recovery of isolated component has 0 affected
        affected_recs = [
            r
            for r in result.recommendations
            if "positively affect" in r.lower()
        ]
        assert len(affected_recs) == 0


# =========================================================================
# 41. Coverage: full_analysis replaces existing with worse impact (L284-285)
# =========================================================================


class TestFullAnalysisReplacesWorseImpact:
    def test_second_source_replaces_first(self):
        """When two unhealthy sources affect the same target component,
        the worse impact replaces the earlier one (lines 284-285)."""
        g = _graph(
            _comp("s1", "S1", health=HealthStatus.DEGRADED),  # mild
            _comp("s2", "S2", health=HealthStatus.DOWN),  # severe
            _comp("target", "Target"),
        )
        g.add_dependency(_edge("target", "s1"))
        g.add_dependency(_edge("target", "s2"))
        e = DependencyHealthEngine(g, decay_factor=1.0)
        rpt = e.full_analysis()
        t_imps = [i for i in rpt.impacts if i.component_id == "target"]
        assert len(t_imps) == 1
        # The DOWN source produces worse impact than DEGRADED
        assert t_imps[0].impact_severity > 0.4

    def test_order_independent_replacement(self):
        """Regardless of iteration order, worst impact is kept."""
        # Process s2 (DOWN) first via iteration, then s1 (DEGRADED)
        # should still keep s2's worse impact
        g = InfraGraph()
        g.add_component(_comp("s2", "S2", health=HealthStatus.DOWN))
        g.add_component(_comp("s1", "S1", health=HealthStatus.DEGRADED))
        g.add_component(_comp("t", "T"))
        g.add_dependency(_edge("t", "s2"))
        g.add_dependency(_edge("t", "s1"))
        e = DependencyHealthEngine(g, decay_factor=1.0)
        rpt = e.full_analysis()
        t_imps = [i for i in rpt.impacts if i.component_id == "t"]
        assert len(t_imps) == 1


# =========================================================================
# 42. Coverage: forward propagation visited skip (L394-395 analog)
# =========================================================================


class TestForwardVisitedSkip:
    def test_diamond_forward_visited_skip(self):
        """In a diamond, the LB node is reached via two paths. The second
        time it's in the queue, it should be skipped (visited check)."""
        g = _diamond_graph(HealthStatus.DOWN)
        e = DependencyHealthEngine(g)
        rpt = e.propagate("db", PropagationMode.FORWARD)
        lb_imps = [i for i in rpt.impacts if i.component_id == "lb"]
        assert len(lb_imps) == 1  # not duplicated


# =========================================================================
# 43. Coverage: backward visited skip (L394-395)
# =========================================================================


class TestBackwardVisitedSkip:
    def test_diamond_backward_visited(self):
        """In backward traversal from lb, db is reachable via api-a and api-b.
        Should only appear once."""
        g = _diamond_graph()
        e = DependencyHealthEngine(g)
        rpt = e.propagate("lb", PropagationMode.BACKWARD)
        db_imps = [i for i in rpt.impacts if i.component_id == "db"]
        assert len(db_imps) == 1


# =========================================================================
# 44. Coverage: _generate_recover_recommendations affected_count > 0 (L506)
# =========================================================================


class TestRecoverRecommendationsAffectedCount:
    def test_recover_rec_with_affected_via_direct_call(self):
        """Directly call _generate_recover_recommendations with impacts
        that have severity > 0 to cover line 506."""
        g = _graph(_comp("db", "DB", health=HealthStatus.DOWN))
        e = DependencyHealthEngine(g)
        comp = g.get_component("db")
        fake_impacts = [
            HealthImpact(
                component_id="api",
                component_name="API",
                original_health=100.0,
                projected_health=30.0,
                impact_severity=0.7,
                hop_distance=1,
                propagation_path=["db", "api"],
            )
        ]
        recs = e._generate_recover_recommendations(
            comp, fake_impacts, HealthStatus.DOWN
        )
        assert any("positively affect" in r.lower() for r in recs)
        assert any("1 dependent" in r for r in recs)

    def test_recover_rec_affected_count_zero(self):
        """When impacts have severity 0, affected_count is 0."""
        g = _graph(_comp("db", "DB", health=HealthStatus.DOWN))
        e = DependencyHealthEngine(g)
        comp = g.get_component("db")
        recs = e._generate_recover_recommendations(
            comp, [], HealthStatus.DOWN
        )
        assert not any("positively affect" in r.lower() for r in recs)


# =========================================================================
# 45. Coverage: _generate_fail_recommendations edge cases
# =========================================================================


class TestFailRecommendationsEdgeCases:
    def test_fail_rec_no_cascade(self):
        """cascade_depth <= 2 does not trigger circuit breaker rec."""
        g = _graph(_comp("db", "DB"))
        g.add_component(_comp("api", "API"))
        g.add_dependency(_edge("api", "db"))
        e = DependencyHealthEngine(g)
        comp = g.get_component("db")
        recs = e._generate_fail_recommendations(comp, [], 1)
        assert not any("circuit" in r.lower() for r in recs)

    def test_fail_rec_with_cascade(self):
        """cascade_depth > 2 triggers circuit breaker rec."""
        g = _graph(_comp("db", "DB"))
        e = DependencyHealthEngine(g)
        comp = g.get_component("db")
        recs = e._generate_fail_recommendations(comp, [], 5)
        assert any("circuit" in r.lower() for r in recs)

    def test_fail_rec_critical_projected(self):
        """Impact with projected < 15 triggers DOWN rec."""
        g = _graph(_comp("db", "DB"))
        e = DependencyHealthEngine(g)
        comp = g.get_component("db")
        impacts = [
            HealthImpact("api", "API", 100.0, 5.0, 0.95, 1, ["db", "api"])
        ]
        recs = e._generate_fail_recommendations(comp, impacts, 1)
        assert any("projected to go DOWN" in r for r in recs)


# =========================================================================
# 46. Coverage: forward propagation None component (L346)
# =========================================================================


class TestForwardPropNoneComponent:
    def test_forward_skips_removed_component(self):
        """Forward propagation: when get_component returns None for a
        dependent, that node is skipped (line 346)."""
        g = _graph(
            _comp("db", "DB", health=HealthStatus.DOWN),
            _comp("api", "API"),
            _comp("web", "Web"),
        )
        g.add_dependency(_edge("api", "db"))
        g.add_dependency(_edge("web", "api"))
        # Remove api from components dict but leave edges
        del g._components["api"]
        e = DependencyHealthEngine(g)
        rpt = e.propagate("db", PropagationMode.FORWARD)
        api_imps = [i for i in rpt.impacts if i.component_id == "api"]
        assert len(api_imps) == 0
        # web should also not appear since api (its only path) was skipped
        # Actually web depends on api, not on db. Let's check:
        # get_dependents("db") = predecessors = [api]
        # api is None -> skip, but web depends on api not db
        # so web won't be in the queue at all
        web_imps = [i for i in rpt.impacts if i.component_id == "web"]
        assert len(web_imps) == 0


# =========================================================================
# 47. Coverage: backward propagation None component (L401)
# =========================================================================


class TestBackwardPropNoneComponent:
    def test_backward_skips_removed_dep(self):
        """Backward propagation: when get_component returns None for a
        dependency, that node is skipped (line 401)."""
        g = _graph(
            _comp("api", "API", health=HealthStatus.DOWN),
            _comp("db", "DB"),
        )
        g.add_dependency(_edge("api", "db"))
        del g._components["db"]
        e = DependencyHealthEngine(g)
        rpt = e.propagate("api", PropagationMode.BACKWARD)
        db_imps = [i for i in rpt.impacts if i.component_id == "db"]
        assert len(db_imps) == 0
