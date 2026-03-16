"""Comprehensive tests for the Chaos Blast Radius Predictor.

Tests cover single component failure, chain propagation, fan-out propagation,
mitigated vs unmitigated paths, empty/single-component graphs, predict_all(),
compare(), boundary conditions, and performance with large graphs.
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
)
from faultray.model.graph import InfraGraph
from faultray.simulator.blast_radius_predictor import (
    AffectedComponent,
    BlastRadiusComparison,
    BlastRadiusPrediction,
    BlastRadiusPredictor,
    ImpactSeverity,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_component(
    id: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover_enabled: bool = False,
    autoscaling_enabled: bool = False,
    cpu_percent: float = 0.0,
    memory_percent: float = 0.0,
    network_connections: int = 0,
    max_connections: int = 1000,
) -> Component:
    return Component(
        id=id,
        name=name,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover_enabled),
        autoscaling=AutoScalingConfig(enabled=autoscaling_enabled),
        metrics=ResourceMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            network_connections=network_connections,
        ),
        capacity=Capacity(max_connections=max_connections),
    )


def _make_dep(
    source_id: str,
    target_id: str,
    dep_type: str = "requires",
    weight: float = 1.0,
    circuit_breaker_enabled: bool = False,
) -> Dependency:
    return Dependency(
        source_id=source_id,
        target_id=target_id,
        dependency_type=dep_type,
        weight=weight,
        circuit_breaker=CircuitBreakerConfig(enabled=circuit_breaker_enabled),
    )


def _build_chain_graph(n: int) -> InfraGraph:
    """Build a linear chain: C0 -> C1 -> C2 -> ... -> C(n-1).

    C0 depends on C1, C1 depends on C2, etc.
    Failing the leaf C(n-1) cascades upstream.
    """
    graph = InfraGraph()
    for i in range(n):
        graph.add_component(
            _make_component(f"c{i}", f"Component {i}")
        )
    for i in range(n - 1):
        graph.add_dependency(_make_dep(f"c{i}", f"c{i+1}"))
    return graph


def _build_fanout_graph(center_id: str, leaf_count: int) -> InfraGraph:
    """Build a fan-out topology: all leaves depend on center.

    Failing center cascades to all leaves.
    """
    graph = InfraGraph()
    graph.add_component(_make_component(center_id, f"Center {center_id}"))
    for i in range(leaf_count):
        lid = f"leaf{i}"
        graph.add_component(_make_component(lid, f"Leaf {i}"))
        graph.add_dependency(_make_dep(lid, center_id))
    return graph


# ===========================================================================
# Test: Empty graph
# ===========================================================================


class TestEmptyGraph:
    def test_predict_empty_graph(self):
        graph = InfraGraph()
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("nonexistent")
        assert pred.total_affected == 0
        assert pred.failed_component_name == "unknown"
        assert pred.mitigated_count == 0
        assert pred.unmitigated_count == 0
        assert pred.affected_components == []
        assert pred.propagation_paths == []
        assert pred.critical_path == []

    def test_predict_all_empty_graph(self):
        graph = InfraGraph()
        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.predict_all()
        assert comparison.predictions == []
        assert comparison.most_dangerous_component == ""
        assert comparison.safest_component == ""
        assert comparison.risk_ranking == []

    def test_compare_empty_list(self):
        graph = InfraGraph()
        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.compare([])
        assert comparison.predictions == []
        assert comparison.risk_ranking == []


# ===========================================================================
# Test: Single-component graph
# ===========================================================================


class TestSingleComponent:
    def test_predict_single_no_deps(self):
        graph = InfraGraph()
        graph.add_component(_make_component("solo", "Solo"))
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("solo")
        assert pred.total_affected == 0
        assert pred.failed_component_name == "Solo"
        assert pred.mitigated_count == 0
        assert pred.unmitigated_count == 0
        assert pred.estimated_user_impact_percent == 0.0
        assert pred.estimated_revenue_impact_percent == 0.0
        assert pred.mttr_estimate_minutes == 0.0

    def test_predict_all_single(self):
        graph = InfraGraph()
        graph.add_component(_make_component("solo", "Solo"))
        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.predict_all()
        assert len(comparison.predictions) == 1
        assert comparison.most_dangerous_component == "solo"
        assert comparison.safest_component == "solo"

    def test_confidence_single_component(self):
        graph = InfraGraph()
        graph.add_component(_make_component("solo", "Solo"))
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("solo")
        # Single component -> confidence = 1.0
        assert pred.confidence == 1.0


# ===========================================================================
# Test: Chain propagation (A -> B -> C)
# ===========================================================================


class TestChainPropagation:
    def test_chain_of_3_fail_leaf(self):
        """C0 -> C1 -> C2. Failing C2 should cascade to C1 then C0."""
        graph = _build_chain_graph(3)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c2")

        assert pred.failed_component_id == "c2"
        assert pred.total_affected == 2  # c1 and c0
        affected_ids = {a.component_id for a in pred.affected_components}
        assert "c1" in affected_ids
        assert "c0" in affected_ids

    def test_chain_depth_ordering(self):
        """Components closer to failure have smaller depth."""
        graph = _build_chain_graph(4)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c3")

        depths = {
            a.component_id: a.propagation_depth
            for a in pred.affected_components
        }
        # c2 is direct dependent (depth 1), c1 is depth 2, c0 is depth 3
        assert depths["c2"] == 1
        assert depths["c1"] == 2
        assert depths["c0"] == 3

    def test_chain_time_to_impact(self):
        """Time to impact should increase with depth."""
        graph = _build_chain_graph(3)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c2")

        times = {
            a.component_id: a.time_to_impact_seconds
            for a in pred.affected_components
        }
        assert times["c1"] < times["c0"]

    def test_chain_fail_middle(self):
        """C0 -> C1 -> C2. Failing C1 should only cascade to C0."""
        graph = _build_chain_graph(3)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c1")

        assert pred.total_affected == 1
        assert pred.affected_components[0].component_id == "c0"

    def test_chain_fail_root(self):
        """C0 -> C1 -> C2. Failing C0 (root) should affect nothing upstream."""
        graph = _build_chain_graph(3)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c0")
        assert pred.total_affected == 0

    def test_chain_propagation_paths(self):
        """Should find paths through the chain."""
        graph = _build_chain_graph(3)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c2")
        assert len(pred.propagation_paths) > 0
        # Should contain a path from c2 to c0
        long_path = max(pred.propagation_paths, key=len)
        assert long_path[0] == "c2"

    def test_chain_severity_degrades_with_depth(self):
        """Deeper components should have equal or less severe impact."""
        graph = _build_chain_graph(6)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c5")

        severity_order = {
            ImpactSeverity.TOTAL_OUTAGE: 4,
            ImpactSeverity.MAJOR_DEGRADATION: 3,
            ImpactSeverity.MINOR_DEGRADATION: 2,
            ImpactSeverity.NEGLIGIBLE: 1,
        }

        sorted_affected = sorted(
            pred.affected_components, key=lambda a: a.propagation_depth
        )
        for i in range(len(sorted_affected) - 1):
            current = severity_order[sorted_affected[i].impact_severity]
            next_val = severity_order[sorted_affected[i + 1].impact_severity]
            assert current >= next_val


# ===========================================================================
# Test: Fan-out propagation (A -> {B, C, D, E})
# ===========================================================================


class TestFanOutPropagation:
    def test_fanout_all_leaves_affected(self):
        """All leaves depend on center; failing center affects all."""
        graph = _build_fanout_graph("center", 4)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("center")

        assert pred.total_affected == 4
        affected_ids = {a.component_id for a in pred.affected_components}
        for i in range(4):
            assert f"leaf{i}" in affected_ids

    def test_fanout_depth_all_1(self):
        """All leaves are at depth 1 from center."""
        graph = _build_fanout_graph("center", 5)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("center")

        for ac in pred.affected_components:
            assert ac.propagation_depth == 1

    def test_fanout_leaf_failure_no_cascade(self):
        """Failing a leaf should not cascade to center or other leaves."""
        graph = _build_fanout_graph("center", 4)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("leaf0")
        assert pred.total_affected == 0

    def test_fanout_severity_distribution(self):
        """All leaves at depth 1 should have total_outage severity."""
        graph = _build_fanout_graph("center", 3)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("center")

        for ac in pred.affected_components:
            assert ac.impact_severity == ImpactSeverity.TOTAL_OUTAGE


# ===========================================================================
# Test: Mitigated vs unmitigated paths
# ===========================================================================


class TestMitigation:
    def test_circuit_breaker_mitigates(self):
        """Circuit breaker on dependency edge should mark component as mitigated."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "Database"))
        graph.add_component(_make_component("app", "App Server"))
        graph.add_dependency(
            _make_dep("app", "db", circuit_breaker_enabled=True)
        )

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        assert pred.total_affected == 1
        ac = pred.affected_components[0]
        assert ac.component_id == "app"
        assert ac.has_circuit_breaker is True
        assert ac.mitigated is True
        assert pred.mitigated_count == 1
        assert pred.unmitigated_count == 0

    def test_failover_with_replicas_mitigates(self):
        """Failover enabled with replicas >= 2 should mitigate."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "Database"))
        graph.add_component(
            _make_component(
                "app", "App Server", replicas=2, failover_enabled=True
            )
        )
        graph.add_dependency(_make_dep("app", "db"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        ac = pred.affected_components[0]
        assert ac.mitigated is True

    def test_failover_without_replicas_not_mitigated(self):
        """Failover enabled but replicas=1 should NOT mitigate."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "Database"))
        graph.add_component(
            _make_component(
                "app", "App Server", replicas=1, failover_enabled=True
            )
        )
        graph.add_dependency(_make_dep("app", "db"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        ac = pred.affected_components[0]
        assert ac.mitigated is False

    def test_mitigated_stops_propagation(self):
        """A mitigated component should stop further propagation."""
        graph = InfraGraph()
        graph.add_component(_make_component("c0", "C0"))
        graph.add_component(_make_component("c1", "C1"))
        graph.add_component(_make_component("c2", "C2"))
        graph.add_dependency(
            _make_dep("c1", "c0")
        )
        graph.add_dependency(
            _make_dep("c2", "c1", circuit_breaker_enabled=True)
        )
        # Extra component upstream of c2
        graph.add_component(_make_component("c3", "C3"))
        graph.add_dependency(_make_dep("c3", "c2"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c0")

        # c1 is not mitigated (no CB), c2 is mitigated (CB)
        # c3 should NOT be affected since c2's CB stops propagation
        affected_ids = {a.component_id for a in pred.affected_components}
        assert "c1" in affected_ids
        assert "c2" in affected_ids
        assert "c3" not in affected_ids

    def test_all_mitigated_counts(self):
        """When all components are mitigated, mitigated_count == total_affected."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "Database"))
        for i in range(3):
            graph.add_component(_make_component(f"app{i}", f"App {i}"))
            graph.add_dependency(
                _make_dep(f"app{i}", "db", circuit_breaker_enabled=True)
            )

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        assert pred.mitigated_count == 3
        assert pred.unmitigated_count == 0
        assert pred.total_affected == 3


# ===========================================================================
# Test: All components with circuit breakers
# ===========================================================================


class TestAllCircuitBreakers:
    def test_all_cb_shows_high_mitigation(self):
        graph = _build_chain_graph(4)
        # Replace all edges with CB-enabled ones
        for i in range(3):
            graph.add_dependency(
                _make_dep(f"c{i}", f"c{i+1}", circuit_breaker_enabled=True)
            )

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c3")

        # c2 should be mitigated (CB on c2->c3)
        # Since c2 is mitigated, propagation stops -> c1, c0 not affected
        assert pred.mitigated_count >= 1
        # All affected should be mitigated
        for ac in pred.affected_components:
            assert ac.mitigated is True


# ===========================================================================
# Test: Severity distribution
# ===========================================================================


class TestSeverityDistribution:
    def test_severity_distribution_keys(self):
        graph = _build_chain_graph(3)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c2")

        # Should have all severity keys
        for sev in ImpactSeverity:
            assert sev.value in pred.severity_distribution

    def test_severity_distribution_sums_to_total(self):
        graph = _build_fanout_graph("center", 5)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("center")

        total = sum(pred.severity_distribution.values())
        assert total == pred.total_affected


# ===========================================================================
# Test: User impact estimation
# ===========================================================================


class TestUserImpact:
    def test_user_facing_components_high_impact(self):
        """Affecting a load balancer should produce high user impact."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "Database"))
        graph.add_component(
            _make_component(
                "lb", "Load Balancer", ctype=ComponentType.LOAD_BALANCER
            )
        )
        graph.add_dependency(_make_dep("lb", "db"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        assert pred.estimated_user_impact_percent > 0

    def test_no_user_facing_low_impact(self):
        """Affecting only backend components should have lower user impact."""
        graph = InfraGraph()
        graph.add_component(
            _make_component("cache", "Cache", ctype=ComponentType.CACHE)
        )
        graph.add_component(
            _make_component("app", "App", ctype=ComponentType.APP_SERVER)
        )
        graph.add_dependency(_make_dep("app", "cache"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("cache")

        # Impact should be relatively low since no user-facing component
        assert pred.estimated_user_impact_percent < 50

    def test_dns_failure_high_impact(self):
        """DNS failure should have high user impact."""
        graph = InfraGraph()
        graph.add_component(
            _make_component("upstream", "Upstream")
        )
        graph.add_component(
            _make_component("dns", "DNS", ctype=ComponentType.DNS)
        )
        graph.add_dependency(_make_dep("dns", "upstream"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("upstream")

        assert pred.estimated_user_impact_percent > 0


# ===========================================================================
# Test: Revenue impact estimation
# ===========================================================================


class TestRevenueImpact:
    def test_database_failure_has_revenue_impact(self):
        graph = InfraGraph()
        graph.add_component(
            _make_component("core", "Core", ctype=ComponentType.DATABASE)
        )
        graph.add_component(
            _make_component("app", "App", ctype=ComponentType.APP_SERVER)
        )
        graph.add_dependency(_make_dep("app", "core"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("core")

        assert pred.estimated_revenue_impact_percent > 0

    def test_mitigated_reduces_revenue_impact(self):
        """Mitigated components should contribute less revenue impact."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "Database"))
        graph.add_component(
            _make_component(
                "app", "App", ctype=ComponentType.APP_SERVER
            )
        )
        graph.add_dependency(
            _make_dep("app", "db", circuit_breaker_enabled=True)
        )

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        # With CB, revenue impact should be lower
        assert pred.estimated_revenue_impact_percent < 20

    def test_zero_impact_on_no_affected(self):
        graph = InfraGraph()
        graph.add_component(_make_component("solo", "Solo"))
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("solo")
        assert pred.estimated_revenue_impact_percent == 0.0


# ===========================================================================
# Test: Confidence
# ===========================================================================


class TestConfidence:
    def test_confidence_range(self):
        graph = _build_chain_graph(5)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c4")
        assert 0.0 <= pred.confidence <= 1.0

    def test_confidence_higher_with_configured_components(self):
        """Components with failover/autoscaling/replicas increase confidence."""
        graph = InfraGraph()
        graph.add_component(
            _make_component(
                "a", "A", replicas=3, failover_enabled=True
            )
        )
        graph.add_component(
            _make_component(
                "b", "B", replicas=2, autoscaling_enabled=True
            )
        )
        graph.add_dependency(_make_dep("a", "b"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("b")

        # Both components are well-configured
        assert pred.confidence > 0.3

    def test_confidence_empty_graph(self):
        graph = InfraGraph()
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("x")
        # Empty graph -> 0 confidence (from _calculate_confidence)
        # But predict returns early for missing component
        assert pred.confidence == 0.0


# ===========================================================================
# Test: MTTR estimation
# ===========================================================================


class TestMTTR:
    def test_mttr_zero_when_no_affected(self):
        graph = InfraGraph()
        graph.add_component(_make_component("solo", "Solo"))
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("solo")
        assert pred.mttr_estimate_minutes == 0.0

    def test_mttr_increases_with_affected_count(self):
        small_graph = _build_fanout_graph("c", 2)
        large_graph = _build_fanout_graph("c", 10)

        small_pred = BlastRadiusPredictor(small_graph).predict("c")
        large_pred = BlastRadiusPredictor(large_graph).predict("c")

        assert large_pred.mttr_estimate_minutes > small_pred.mttr_estimate_minutes

    def test_mttr_minimum_is_5(self):
        """MTTR should never be below 5 minutes when there are affected components."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "DB"))
        graph.add_component(
            _make_component(
                "app", "App", failover_enabled=True, replicas=3
            )
        )
        graph.add_dependency(
            _make_dep("app", "db", circuit_breaker_enabled=True)
        )

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        if pred.total_affected > 0:
            assert pred.mttr_estimate_minutes >= 5.0

    def test_mttr_reduced_with_automation(self):
        """Components with failover/CB should reduce MTTR."""
        # Graph without automation
        g1 = InfraGraph()
        g1.add_component(_make_component("db", "DB"))
        g1.add_component(_make_component("app", "App"))
        g1.add_dependency(_make_dep("app", "db"))

        # Graph with automation
        g2 = InfraGraph()
        g2.add_component(_make_component("db", "DB"))
        g2.add_component(
            _make_component("app", "App", failover_enabled=True, replicas=2)
        )
        g2.add_dependency(
            _make_dep("app", "db", circuit_breaker_enabled=True)
        )

        pred1 = BlastRadiusPredictor(g1).predict("db")
        pred2 = BlastRadiusPredictor(g2).predict("db")

        # Both have 1 affected, but g2 has automation
        # g2's MTTR should be lower or equal (mitigated stops propagation too)
        assert pred2.mttr_estimate_minutes <= pred1.mttr_estimate_minutes


# ===========================================================================
# Test: Critical path
# ===========================================================================


class TestCriticalPath:
    def test_critical_path_exists_in_chain(self):
        graph = _build_chain_graph(4)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c3")
        assert len(pred.critical_path) > 0
        assert pred.critical_path[0] == "c3"

    def test_critical_path_empty_when_no_affected(self):
        graph = InfraGraph()
        graph.add_component(_make_component("solo", "Solo"))
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("solo")
        assert pred.critical_path == []


# ===========================================================================
# Test: predict_all()
# ===========================================================================


class TestPredictAll:
    def test_predict_all_chain(self):
        graph = _build_chain_graph(4)
        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.predict_all()

        assert len(comparison.predictions) == 4
        assert len(comparison.risk_ranking) == 4
        assert comparison.most_dangerous_component != ""
        assert comparison.safest_component != ""

    def test_predict_all_fanout(self):
        graph = _build_fanout_graph("center", 5)
        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.predict_all()

        # center should be most dangerous (affects 5 leaves)
        assert comparison.most_dangerous_component == "center"

    def test_predict_all_risk_ranking_sorted(self):
        graph = _build_chain_graph(5)
        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.predict_all()

        scores = [score for _, score in comparison.risk_ranking]
        assert scores == sorted(scores, reverse=True)

    def test_predict_all_single_component(self):
        graph = InfraGraph()
        graph.add_component(_make_component("only", "Only"))
        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.predict_all()

        assert len(comparison.predictions) == 1
        assert comparison.most_dangerous_component == "only"
        assert comparison.safest_component == "only"


# ===========================================================================
# Test: compare() subset
# ===========================================================================


class TestCompare:
    def test_compare_subset(self):
        graph = _build_chain_graph(5)
        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.compare(["c2", "c4"])

        assert len(comparison.predictions) == 2
        assert len(comparison.risk_ranking) == 2

    def test_compare_single(self):
        graph = _build_chain_graph(3)
        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.compare(["c2"])

        assert len(comparison.predictions) == 1
        assert comparison.most_dangerous_component == "c2"
        assert comparison.safest_component == "c2"

    def test_compare_nonexistent(self):
        graph = _build_chain_graph(3)
        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.compare(["nonexistent"])

        assert len(comparison.predictions) == 1
        pred = comparison.predictions[0]
        assert pred.total_affected == 0
        assert pred.failed_component_name == "unknown"

    def test_compare_ranks_correctly(self):
        """Component with more affected should rank higher."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "DB"))
        graph.add_component(_make_component("cache", "Cache"))
        graph.add_component(_make_component("app1", "App1"))
        graph.add_component(_make_component("app2", "App2"))
        graph.add_component(_make_component("app3", "App3"))
        # app1, app2, app3 all depend on db
        graph.add_dependency(_make_dep("app1", "db"))
        graph.add_dependency(_make_dep("app2", "db"))
        graph.add_dependency(_make_dep("app3", "db"))
        # Only app1 depends on cache
        graph.add_dependency(_make_dep("app1", "cache"))

        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.compare(["db", "cache"])

        # db should be most dangerous (3 dependents vs 1)
        assert comparison.most_dangerous_component == "db"


# ===========================================================================
# Test: Boundary conditions
# ===========================================================================


class TestBoundaryConditions:
    def test_zero_affected(self):
        """Leaf node failure should have 0 affected."""
        graph = _build_chain_graph(3)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c0")
        assert pred.total_affected == 0
        assert pred.unmitigated_count == 0
        assert pred.mitigated_count == 0

    def test_all_affected(self):
        """Central component failure should affect all dependents."""
        graph = _build_fanout_graph("hub", 6)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("hub")
        assert pred.total_affected == 6

    def test_nonexistent_component(self):
        graph = _build_chain_graph(3)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("does_not_exist")
        assert pred.total_affected == 0
        assert pred.failed_component_name == "unknown"

    def test_component_with_no_dependents(self):
        """A component that nothing depends on should have 0 affected."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A"))
        graph.add_component(_make_component("b", "B"))
        graph.add_dependency(_make_dep("a", "b"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("a")
        assert pred.total_affected == 0


# ===========================================================================
# Test: Redundancy reduces severity
# ===========================================================================


class TestRedundancy:
    def test_high_replicas_reduce_severity(self):
        """Components with 3+ replicas should have reduced severity."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "DB"))
        graph.add_component(
            _make_component("app", "App", replicas=3)
        )
        graph.add_dependency(_make_dep("app", "db"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        ac = pred.affected_components[0]
        # Depth 1 would normally be TOTAL_OUTAGE, but 3 replicas reduce by 2
        assert ac.impact_severity != ImpactSeverity.TOTAL_OUTAGE

    def test_two_replicas_reduce_severity_by_one(self):
        graph = InfraGraph()
        graph.add_component(_make_component("db", "DB"))
        graph.add_component(
            _make_component("app", "App", replicas=2)
        )
        graph.add_dependency(_make_dep("app", "db"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        ac = pred.affected_components[0]
        # Depth 1 normally TOTAL_OUTAGE, reduced by 1 -> MAJOR_DEGRADATION
        assert ac.impact_severity == ImpactSeverity.MAJOR_DEGRADATION

    def test_failover_reduces_severity(self):
        graph = InfraGraph()
        graph.add_component(_make_component("db", "DB"))
        graph.add_component(
            _make_component("app", "App", failover_enabled=True)
        )
        graph.add_dependency(_make_dep("app", "db"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        ac = pred.affected_components[0]
        # Failover reduces by 1 level
        assert ac.impact_severity == ImpactSeverity.MAJOR_DEGRADATION


# ===========================================================================
# Test: Complex topology
# ===========================================================================


class TestComplexTopology:
    def test_diamond_topology(self):
        """A -> B, A -> C, B -> D, C -> D. Failing D should reach A."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A"))
        graph.add_component(_make_component("b", "B"))
        graph.add_component(_make_component("c", "C"))
        graph.add_component(_make_component("d", "D"))
        graph.add_dependency(_make_dep("a", "b"))
        graph.add_dependency(_make_dep("a", "c"))
        graph.add_dependency(_make_dep("b", "d"))
        graph.add_dependency(_make_dep("c", "d"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("d")

        affected_ids = {a.component_id for a in pred.affected_components}
        assert "b" in affected_ids
        assert "c" in affected_ids
        assert "a" in affected_ids

    def test_mixed_dep_types(self):
        """Optional/async dependencies should still propagate."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "DB"))
        graph.add_component(_make_component("app", "App"))
        graph.add_component(_make_component("log", "Logger"))
        graph.add_dependency(
            _make_dep("app", "db", dep_type="requires")
        )
        graph.add_dependency(
            _make_dep("log", "db", dep_type="optional")
        )

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        affected_ids = {a.component_id for a in pred.affected_components}
        assert "app" in affected_ids
        assert "log" in affected_ids

    def test_multi_level_fanout(self):
        """Two-level fan-out: center -> {mid1, mid2}, mid1 -> {leaf1, leaf2}."""
        graph = InfraGraph()
        graph.add_component(_make_component("center", "Center"))
        graph.add_component(_make_component("mid1", "Mid1"))
        graph.add_component(_make_component("mid2", "Mid2"))
        graph.add_component(_make_component("leaf1", "Leaf1"))
        graph.add_component(_make_component("leaf2", "Leaf2"))
        graph.add_dependency(_make_dep("mid1", "center"))
        graph.add_dependency(_make_dep("mid2", "center"))
        graph.add_dependency(_make_dep("leaf1", "mid1"))
        graph.add_dependency(_make_dep("leaf2", "mid1"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("center")

        affected_ids = {a.component_id for a in pred.affected_components}
        assert "mid1" in affected_ids
        assert "mid2" in affected_ids
        assert "leaf1" in affected_ids
        assert "leaf2" in affected_ids
        assert pred.total_affected == 4


# ===========================================================================
# Test: BlastRadiusPrediction dataclass
# ===========================================================================


class TestDataclasses:
    def test_blast_radius_prediction_defaults(self):
        pred = BlastRadiusPrediction(
            failed_component_id="x",
            failed_component_name="X",
            total_affected=0,
            mitigated_count=0,
            unmitigated_count=0,
        )
        assert pred.affected_components == []
        assert pred.severity_distribution == {}
        assert pred.estimated_user_impact_percent == 0.0
        assert pred.confidence == 0.0
        assert pred.propagation_paths == []
        assert pred.critical_path == []
        assert pred.mttr_estimate_minutes == 0.0

    def test_affected_component_fields(self):
        ac = AffectedComponent(
            component_id="test",
            component_name="Test",
            impact_severity=ImpactSeverity.MAJOR_DEGRADATION,
            propagation_depth=2,
            time_to_impact_seconds=30.0,
            has_circuit_breaker=True,
            has_failover=False,
            mitigated=True,
        )
        assert ac.component_id == "test"
        assert ac.impact_severity == ImpactSeverity.MAJOR_DEGRADATION
        assert ac.propagation_depth == 2
        assert ac.mitigated is True

    def test_blast_radius_comparison_defaults(self):
        comp = BlastRadiusComparison()
        assert comp.predictions == []
        assert comp.most_dangerous_component == ""
        assert comp.safest_component == ""
        assert comp.risk_ranking == []

    def test_impact_severity_values(self):
        assert ImpactSeverity.TOTAL_OUTAGE.value == "total_outage"
        assert ImpactSeverity.MAJOR_DEGRADATION.value == "major_degradation"
        assert ImpactSeverity.MINOR_DEGRADATION.value == "minor_degradation"
        assert ImpactSeverity.NEGLIGIBLE.value == "negligible"


# ===========================================================================
# Test: Performance with large graph
# ===========================================================================


class TestPerformance:
    def test_large_chain_graph_50_components(self):
        """Chain of 50 components should complete in reasonable time."""
        graph = _build_chain_graph(50)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c49")

        assert pred.total_affected == 49  # all except the failed one
        assert pred.failed_component_name == "Component 49"

    def test_large_fanout_50_components(self):
        """Fan-out with 50 leaves should complete quickly."""
        graph = _build_fanout_graph("hub", 50)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("hub")

        assert pred.total_affected == 50
        for ac in pred.affected_components:
            assert ac.propagation_depth == 1

    def test_predict_all_large_graph(self):
        """predict_all on a 50-component chain should work."""
        graph = _build_chain_graph(50)
        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.predict_all()

        assert len(comparison.predictions) == 50
        assert len(comparison.risk_ranking) == 50
        # The deepest leaf (c49) should be most dangerous
        assert comparison.most_dangerous_component == "c49"

    def test_mixed_large_graph(self):
        """Graph with both chains and fan-outs (60+ components)."""
        graph = InfraGraph()
        # Create a hub
        graph.add_component(_make_component("hub", "Hub"))

        # 30 direct dependents of hub
        for i in range(30):
            cid = f"direct{i}"
            graph.add_component(_make_component(cid, f"Direct {i}"))
            graph.add_dependency(_make_dep(cid, "hub"))

        # Chain of 20 from direct0
        prev = "direct0"
        for i in range(20):
            cid = f"chain{i}"
            graph.add_component(_make_component(cid, f"Chain {i}"))
            graph.add_dependency(_make_dep(cid, prev))
            prev = cid

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("hub")

        # All 30 directs + 20 chain components
        assert pred.total_affected == 50


# ===========================================================================
# Test: User-facing component types
# ===========================================================================


class TestComponentTypes:
    def test_web_server_is_user_facing(self):
        graph = InfraGraph()
        graph.add_component(_make_component("backend", "Backend"))
        graph.add_component(
            _make_component(
                "web", "Web", ctype=ComponentType.WEB_SERVER
            )
        )
        graph.add_dependency(_make_dep("web", "backend"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("backend")

        assert pred.estimated_user_impact_percent > 0

    def test_cache_not_user_facing(self):
        graph = InfraGraph()
        graph.add_component(_make_component("source", "Source"))
        graph.add_component(
            _make_component(
                "cache", "Cache", ctype=ComponentType.CACHE
            )
        )
        graph.add_dependency(_make_dep("cache", "source"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("source")

        # Cache is not user-facing, so user impact comes from spread ratio
        assert pred.estimated_user_impact_percent < 40


# ===========================================================================
# Test: _reduce_severity helper
# ===========================================================================


class TestReduceSeverity:
    def test_reduce_by_zero(self):
        result = BlastRadiusPredictor._reduce_severity(
            ImpactSeverity.TOTAL_OUTAGE, 0
        )
        assert result == ImpactSeverity.TOTAL_OUTAGE

    def test_reduce_by_one(self):
        result = BlastRadiusPredictor._reduce_severity(
            ImpactSeverity.TOTAL_OUTAGE, 1
        )
        assert result == ImpactSeverity.MAJOR_DEGRADATION

    def test_reduce_by_two(self):
        result = BlastRadiusPredictor._reduce_severity(
            ImpactSeverity.TOTAL_OUTAGE, 2
        )
        assert result == ImpactSeverity.MINOR_DEGRADATION

    def test_reduce_beyond_max(self):
        result = BlastRadiusPredictor._reduce_severity(
            ImpactSeverity.TOTAL_OUTAGE, 10
        )
        assert result == ImpactSeverity.NEGLIGIBLE

    def test_reduce_from_negligible(self):
        result = BlastRadiusPredictor._reduce_severity(
            ImpactSeverity.NEGLIGIBLE, 1
        )
        assert result == ImpactSeverity.NEGLIGIBLE


# ===========================================================================
# Test: Mitigated user-facing components (covers line 459)
# ===========================================================================


class TestMitigatedUserFacing:
    def test_mitigated_user_facing_moderate_impact(self):
        """User-facing component mitigated by CB should have moderate (not high) impact."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "Database"))
        graph.add_component(
            _make_component(
                "lb", "Load Balancer",
                ctype=ComponentType.LOAD_BALANCER,
                replicas=2,
                failover_enabled=True,
            )
        )
        graph.add_dependency(
            _make_dep("lb", "db", circuit_breaker_enabled=True)
        )

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        # The LB is mitigated (CB enabled), so user impact should be moderate
        # This hits the mitigated user-facing path (line 459)
        assert pred.mitigated_count == 1
        assert pred.estimated_user_impact_percent > 0
        assert pred.estimated_user_impact_percent <= 10.0

    def test_multiple_mitigated_user_facing(self):
        """Multiple mitigated user-facing components."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "Database"))
        graph.add_component(
            _make_component(
                "lb", "LB", ctype=ComponentType.LOAD_BALANCER,
                replicas=2, failover_enabled=True,
            )
        )
        graph.add_component(
            _make_component(
                "dns", "DNS", ctype=ComponentType.DNS,
                replicas=2, failover_enabled=True,
            )
        )
        graph.add_dependency(
            _make_dep("lb", "db", circuit_breaker_enabled=True)
        )
        graph.add_dependency(
            _make_dep("dns", "db", circuit_breaker_enabled=True)
        )

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("db")

        assert pred.mitigated_count == 2
        # Should hit the user_facing_affected > 0 path with all mitigated
        assert pred.estimated_user_impact_percent > 0


# ===========================================================================
# Test: Confidence with no edges (covers line 554)
# ===========================================================================


class TestConfidenceNoEdges:
    def test_confidence_no_edges_multi_components(self):
        """Multiple components with no edges should yield specific confidence."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A"))
        graph.add_component(_make_component("b", "B"))
        graph.add_component(_make_component("c", "C"))
        # No dependencies at all

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("a")

        # No edges: connectivity = 0, weight_quality = 0.5, config_ratio = 0
        # confidence = 0.0 * 0.4 + 0.5 * 0.3 + 0 * 0.3 = 0.15
        assert pred.confidence == pytest.approx(0.15, abs=0.01)

    def test_confidence_with_optional_edges(self):
        """Edges with non-default weight/type should increase weight_quality."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A"))
        graph.add_component(_make_component("b", "B"))
        graph.add_dependency(
            _make_dep("a", "b", dep_type="optional", weight=0.5)
        )

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("b")

        # One edge with non-default type -> explicit_weights = 1
        # weight_quality = 0.5 + 0.5 * 1.0 = 1.0
        assert pred.confidence > 0.3


# ===========================================================================
# Test: Non-revenue-critical component types
# ===========================================================================


class TestNonRevenueCritical:
    def test_queue_component_low_revenue_impact(self):
        """Queue (non-revenue-critical) should have lower revenue impact."""
        graph = InfraGraph()
        graph.add_component(_make_component("source", "Source"))
        graph.add_component(
            _make_component("queue", "Queue", ctype=ComponentType.QUEUE)
        )
        graph.add_dependency(_make_dep("queue", "source"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("source")

        # Queue is not revenue-critical, so only 5 * 1.0 = 5.0
        assert pred.estimated_revenue_impact_percent == 5.0

    def test_external_api_low_revenue_impact(self):
        """External API should have lower revenue impact than DB."""
        graph = InfraGraph()
        graph.add_component(_make_component("source", "Source"))
        graph.add_component(
            _make_component("ext", "External", ctype=ComponentType.EXTERNAL_API)
        )
        graph.add_dependency(_make_dep("ext", "source"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("source")

        assert pred.estimated_revenue_impact_percent <= 10.0


# ===========================================================================
# Test: _compute_risk_score (covers static method)
# ===========================================================================


class TestComputeRiskScore:
    def test_risk_score_increases_with_severity(self):
        pred_low = BlastRadiusPrediction(
            failed_component_id="a", failed_component_name="A",
            total_affected=1, mitigated_count=0, unmitigated_count=1,
            severity_distribution={
                "total_outage": 0, "major_degradation": 0,
                "minor_degradation": 1, "negligible": 0,
            },
            estimated_user_impact_percent=5.0,
            estimated_revenue_impact_percent=5.0,
        )
        pred_high = BlastRadiusPrediction(
            failed_component_id="b", failed_component_name="B",
            total_affected=1, mitigated_count=0, unmitigated_count=1,
            severity_distribution={
                "total_outage": 1, "major_degradation": 0,
                "minor_degradation": 0, "negligible": 0,
            },
            estimated_user_impact_percent=50.0,
            estimated_revenue_impact_percent=50.0,
        )

        score_low = BlastRadiusPredictor._compute_risk_score(pred_low)
        score_high = BlastRadiusPredictor._compute_risk_score(pred_high)

        assert score_high > score_low

    def test_risk_score_zero_for_empty(self):
        pred = BlastRadiusPrediction(
            failed_component_id="x", failed_component_name="X",
            total_affected=0, mitigated_count=0, unmitigated_count=0,
        )
        score = BlastRadiusPredictor._compute_risk_score(pred)
        assert score == 0.0


# ===========================================================================
# Test: Propagation paths details
# ===========================================================================


class TestPropagationPaths:
    def test_propagation_paths_fanout(self):
        """Fan-out should produce multiple paths."""
        graph = _build_fanout_graph("center", 3)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("center")

        # Should have paths from center to each leaf
        assert len(pred.propagation_paths) >= 3

    def test_propagation_paths_diamond(self):
        """Diamond topology should produce multiple paths."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A"))
        graph.add_component(_make_component("b", "B"))
        graph.add_component(_make_component("c", "C"))
        graph.add_component(_make_component("d", "D"))
        graph.add_dependency(_make_dep("a", "b"))
        graph.add_dependency(_make_dep("a", "c"))
        graph.add_dependency(_make_dep("b", "d"))
        graph.add_dependency(_make_dep("c", "d"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("d")

        # Should have paths d->b->a, d->c->a, d->b, d->c
        assert len(pred.propagation_paths) > 0
        # All paths should start with "d"
        for path in pred.propagation_paths:
            assert path[0] == "d"

    def test_propagation_paths_no_dependents(self):
        """Root node (no dependents) should have no paths."""
        graph = _build_chain_graph(3)
        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("c0")  # root, nothing depends on it
        assert pred.propagation_paths == []


# ===========================================================================
# Test: Edge case - disconnected components
# ===========================================================================


class TestDisconnectedComponents:
    def test_disconnected_not_affected(self):
        """Components not in the dependency chain should not be affected."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A"))
        graph.add_component(_make_component("b", "B"))
        graph.add_component(_make_component("c", "C"))  # disconnected
        graph.add_dependency(_make_dep("a", "b"))

        predictor = BlastRadiusPredictor(graph)
        pred = predictor.predict("b")

        affected_ids = {a.component_id for a in pred.affected_components}
        assert "a" in affected_ids
        assert "c" not in affected_ids

    def test_predict_all_with_disconnected(self):
        """predict_all should handle disconnected components."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A"))
        graph.add_component(_make_component("b", "B"))
        graph.add_component(_make_component("c", "C"))
        graph.add_dependency(_make_dep("a", "b"))
        # c is disconnected

        predictor = BlastRadiusPredictor(graph)
        comparison = predictor.predict_all()

        assert len(comparison.predictions) == 3
        # b should be most dangerous (a depends on it)
        assert comparison.most_dangerous_component == "b"


# ===========================================================================
# Test: _find_incoming_edge returns None (covers line 308)
# ===========================================================================


class TestFindIncomingEdge:
    def test_incoming_edge_returns_none_for_disconnected(self):
        """When a component has no dependency to any visited node, return None."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A"))
        graph.add_component(_make_component("b", "B"))
        # No edges between them

        predictor = BlastRadiusPredictor(graph)
        edge = predictor._find_incoming_edge("a", {"b"})
        assert edge is None

    def test_incoming_edge_returns_edge(self):
        """When a component depends on a visited node, return the edge."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A"))
        graph.add_component(_make_component("b", "B"))
        graph.add_dependency(_make_dep("a", "b"))

        predictor = BlastRadiusPredictor(graph)
        edge = predictor._find_incoming_edge("a", {"b"})
        assert edge is not None
        assert edge.source_id == "a"
        assert edge.target_id == "b"


# ===========================================================================
# Test: _estimate_user_impact and _estimate_revenue_impact with
# crafted AffectedComponent lists (covers lines 439, 447, 478, 484)
# ===========================================================================


class TestImpactEstimationDirectCalls:
    def test_user_impact_with_unknown_component(self):
        """AffectedComponent with ID not in graph should be skipped."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A"))

        predictor = BlastRadiusPredictor(graph)
        affected = [
            AffectedComponent(
                component_id="nonexistent",
                component_name="Ghost",
                impact_severity=ImpactSeverity.TOTAL_OUTAGE,
                propagation_depth=1,
                time_to_impact_seconds=15.0,
                has_circuit_breaker=False,
                has_failover=False,
                mitigated=False,
            )
        ]
        result = predictor._estimate_user_impact(affected)
        # nonexistent comp is None, so it's skipped. No user-facing components.
        # spread_ratio = 1/1 = 1.0, return min(100, 1.0 * 30) = 30.0
        assert result == pytest.approx(30.0, abs=1.0)

    def test_revenue_impact_with_unknown_component(self):
        """AffectedComponent with ID not in graph should be skipped."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A"))

        predictor = BlastRadiusPredictor(graph)
        affected = [
            AffectedComponent(
                component_id="nonexistent",
                component_name="Ghost",
                impact_severity=ImpactSeverity.TOTAL_OUTAGE,
                propagation_depth=1,
                time_to_impact_seconds=15.0,
                has_circuit_breaker=False,
                has_failover=False,
                mitigated=False,
            )
        ]
        result = predictor._estimate_revenue_impact(affected)
        # comp is None -> continue, so revenue_score = 0
        assert result == 0.0

    def test_revenue_impact_mitigated_components(self):
        """Mitigated components should contribute lower revenue impact."""
        graph = InfraGraph()
        graph.add_component(
            _make_component("db", "DB", ctype=ComponentType.DATABASE)
        )

        predictor = BlastRadiusPredictor(graph)
        affected = [
            AffectedComponent(
                component_id="db",
                component_name="DB",
                impact_severity=ImpactSeverity.MINOR_DEGRADATION,
                propagation_depth=1,
                time_to_impact_seconds=15.0,
                has_circuit_breaker=True,
                has_failover=True,
                mitigated=True,
            )
        ]
        result = predictor._estimate_revenue_impact(affected)
        # DB is revenue-critical, but mitigated: 20.0 * 0.1 = 2.0
        assert result == pytest.approx(2.0, abs=0.1)


# ===========================================================================
# Test: _calculate_confidence edge cases (covers lines 531, 544)
# ===========================================================================


class TestCalculateConfidenceEdgeCases:
    def test_confidence_called_on_empty_graph_directly(self):
        """Calling _calculate_confidence on empty graph returns 0."""
        graph = InfraGraph()
        predictor = BlastRadiusPredictor(graph)
        assert predictor._calculate_confidence() == 0.0

    def test_confidence_single_component_directly(self):
        """Single component returns confidence 1.0."""
        graph = InfraGraph()
        graph.add_component(_make_component("solo", "Solo"))
        predictor = BlastRadiusPredictor(graph)
        assert predictor._calculate_confidence() == 1.0


# ===========================================================================
# Test: _estimate_mttr edge cases (covers line 600)
# ===========================================================================


class TestEstimateMttrEdgeCases:
    def test_mttr_called_with_empty_list_directly(self):
        """Empty affected list returns 0."""
        graph = InfraGraph()
        predictor = BlastRadiusPredictor(graph)
        assert predictor._estimate_mttr([]) == 0.0


# ===========================================================================
# Coverage gaps — lines 248, 252, 439, 478
# ===========================================================================


class TestCoverageGapsBFS:
    """Test BFS depth limit and missing component handling."""

    def test_bfs_depth_exceeds_max_depth(self):
        """A chain deeper than _MAX_BFS_DEPTH should stop propagating
        beyond that depth. [line 248]"""
        from faultray.simulator.blast_radius_predictor import _MAX_BFS_DEPTH

        graph = InfraGraph()
        # Create a chain of _MAX_BFS_DEPTH + 5 nodes
        depth = _MAX_BFS_DEPTH + 5
        for i in range(depth):
            graph.add_component(_make_component(f"n{i}", f"Node{i}"))
        for i in range(depth - 1):
            graph.add_dependency(_make_dep(f"n{i+1}", f"n{i}"))

        predictor = BlastRadiusPredictor(graph)
        prediction = predictor.predict("n0")
        # Components beyond depth _MAX_BFS_DEPTH should not be affected
        affected_ids = {ac.component_id for ac in prediction.affected_components}
        # The nodes right after the depth limit should NOT appear
        # (nodes further than MAX_BFS_DEPTH hops from n0)
        assert len(affected_ids) <= _MAX_BFS_DEPTH

    def test_bfs_missing_component_in_graph(self):
        """When a node exists in the networkx graph but not in components dict,
        the BFS should skip it. [line 252]"""
        from unittest.mock import patch

        graph = InfraGraph()
        graph.add_component(_make_component("root", "Root"))
        graph.add_component(_make_component("child", "Child"))
        graph.add_dependency(_make_dep("child", "root"))

        predictor = BlastRadiusPredictor(graph)

        # Mock get_component to return None for 'child' to simulate
        # a component that exists in the graph edges but not in components dict
        original_get = graph.get_component

        def mock_get(comp_id):
            if comp_id == "child":
                return None
            return original_get(comp_id)

        with patch.object(graph, "get_component", side_effect=mock_get):
            prediction = predictor.predict("root")
        # child should not appear in affected list since get_component returns None
        affected_ids = {ac.component_id for ac in prediction.affected_components}
        assert "child" not in affected_ids


class TestCoverageGapsImpact:
    """Test user/revenue impact with empty graph components."""

    def test_user_impact_empty_graph_components(self):
        """When graph has 0 total_components, _estimate_user_impact
        should return 0.0. [line 439]"""
        graph = InfraGraph()
        predictor = BlastRadiusPredictor(graph)
        affected = [
            AffectedComponent(
                component_id="phantom",
                component_name="Phantom",
                impact_severity=ImpactSeverity.TOTAL_OUTAGE,
                propagation_depth=1,
                time_to_impact_seconds=0.0,
                has_circuit_breaker=False,
                has_failover=False,
                mitigated=False,
            )
        ]
        result = predictor._estimate_user_impact(affected)
        assert result == 0.0

    def test_revenue_impact_empty_graph_components(self):
        """When graph has 0 total_components, _estimate_revenue_impact
        should return 0.0. [line 478]"""
        graph = InfraGraph()
        predictor = BlastRadiusPredictor(graph)
        affected = [
            AffectedComponent(
                component_id="phantom",
                component_name="Phantom",
                impact_severity=ImpactSeverity.TOTAL_OUTAGE,
                propagation_depth=1,
                time_to_impact_seconds=0.0,
                has_circuit_breaker=False,
                has_failover=False,
                mitigated=False,
            )
        ]
        result = predictor._estimate_revenue_impact(affected)
        assert result == 0.0
