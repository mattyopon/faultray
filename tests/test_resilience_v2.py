"""Tests for InfraGraph.resilience_score_v2()."""
from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    autoscaling: bool = False,
    cpu_percent: float = 0.0,
    memory_percent: float = 0.0,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        port=8080,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        metrics=ResourceMetrics(cpu_percent=cpu_percent, memory_percent=memory_percent),
    )


def _make_dep(
    source: str,
    target: str,
    dep_type: str = "requires",
    cb_enabled: bool = False,
) -> Dependency:
    return Dependency(
        source_id=source,
        target_id=target,
        dependency_type=dep_type,
        circuit_breaker=CircuitBreakerConfig(enabled=cb_enabled),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestResilienceScoreV2:

    def test_empty_graph_returns_zero(self):
        graph = InfraGraph()
        result = graph.resilience_score_v2()
        assert result["score"] == 0.0
        assert result["breakdown"]["redundancy"] == 0.0
        assert result["breakdown"]["circuit_breaker_coverage"] == 0.0
        assert result["breakdown"]["auto_recovery"] == 0.0
        assert result["breakdown"]["dependency_risk"] == 0.0
        assert result["breakdown"]["capacity_headroom"] == 0.0
        assert result["recommendations"] == []

    def test_single_component_basic_score(self):
        """Single component with defaults gets baseline scores."""
        graph = InfraGraph()
        graph.add_component(_make_component("app"))
        result = graph.resilience_score_v2()

        # Single replica, no failover -> redundancy = 5
        assert result["breakdown"]["redundancy"] == 5.0
        # No edges -> CB coverage = 20
        assert result["breakdown"]["circuit_breaker_coverage"] == 20.0
        # No autoscaling or failover -> auto_recovery = 0
        assert result["breakdown"]["auto_recovery"] == 0.0
        # No dependencies -> depth=0, dependency_risk = 20
        assert result["breakdown"]["dependency_risk"] == 20.0
        # 0% utilization -> capacity_headroom = 20
        assert result["breakdown"]["capacity_headroom"] == 20.0

        assert 0.0 <= result["score"] <= 100.0

    def test_redundancy_replicas_1_vs_3(self):
        """Multiple replicas should yield higher redundancy score."""
        # Single replica
        g1 = InfraGraph()
        g1.add_component(_make_component("app", replicas=1))
        r1 = g1.resilience_score_v2()

        # Three replicas (no failover -> Active-Standby = 15)
        g2 = InfraGraph()
        g2.add_component(_make_component("app", replicas=3))
        r2 = g2.resilience_score_v2()

        assert r1["breakdown"]["redundancy"] == 5.0
        assert r2["breakdown"]["redundancy"] == 15.0
        assert r2["breakdown"]["redundancy"] > r1["breakdown"]["redundancy"]

    def test_redundancy_active_active(self):
        """Replicas + failover should get max redundancy (20)."""
        graph = InfraGraph()
        graph.add_component(_make_component("app", replicas=3, failover=True))
        result = graph.resilience_score_v2()
        assert result["breakdown"]["redundancy"] == 20.0

    def test_circuit_breaker_coverage(self):
        """CB coverage reflects percentage of edges with CB enabled."""
        graph = InfraGraph()
        graph.add_component(_make_component("frontend"))
        graph.add_component(_make_component("backend"))
        graph.add_component(_make_component("db", ctype=ComponentType.DATABASE))

        # Two edges, one with CB, one without
        graph.add_dependency(_make_dep("frontend", "backend", cb_enabled=True))
        graph.add_dependency(_make_dep("backend", "db", cb_enabled=False))

        result = graph.resilience_score_v2()
        # 1/2 = 50% -> 10.0
        assert result["breakdown"]["circuit_breaker_coverage"] == 10.0

    def test_circuit_breaker_full_coverage(self):
        """100% CB coverage should score 20."""
        graph = InfraGraph()
        graph.add_component(_make_component("a"))
        graph.add_component(_make_component("b"))
        graph.add_dependency(_make_dep("a", "b", cb_enabled=True))

        result = graph.resilience_score_v2()
        assert result["breakdown"]["circuit_breaker_coverage"] == 20.0

    def test_auto_recovery_impact(self):
        """Components with autoscaling or failover should improve auto_recovery."""
        # No recovery
        g1 = InfraGraph()
        g1.add_component(_make_component("app"))
        r1 = g1.resilience_score_v2()
        assert r1["breakdown"]["auto_recovery"] == 0.0

        # With autoscaling
        g2 = InfraGraph()
        g2.add_component(_make_component("app", autoscaling=True))
        r2 = g2.resilience_score_v2()
        assert r2["breakdown"]["auto_recovery"] == 20.0

        # With failover
        g3 = InfraGraph()
        g3.add_component(_make_component("app", failover=True))
        r3 = g3.resilience_score_v2()
        assert r3["breakdown"]["auto_recovery"] == 20.0

    def test_auto_recovery_partial(self):
        """Mixed components: only some have recovery."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", autoscaling=True))
        graph.add_component(_make_component("b"))  # no recovery
        result = graph.resilience_score_v2()
        # 1/2 = 50% -> 10.0
        assert result["breakdown"]["auto_recovery"] == 10.0

    def test_utilization_impact_low(self):
        """Low utilization should give max capacity headroom."""
        graph = InfraGraph()
        graph.add_component(_make_component("app", cpu_percent=20.0))
        result = graph.resilience_score_v2()
        assert result["breakdown"]["capacity_headroom"] == 20.0

    def test_utilization_impact_high(self):
        """High utilization should reduce capacity headroom."""
        graph = InfraGraph()
        graph.add_component(_make_component("app", cpu_percent=95.0))
        result = graph.resilience_score_v2()
        assert result["breakdown"]["capacity_headroom"] == 0.0

    def test_utilization_impact_mid(self):
        """Mid utilization should score proportionally."""
        graph = InfraGraph()
        graph.add_component(_make_component("app", cpu_percent=70.0))
        result = graph.resilience_score_v2()
        # avg_util = 70, score = 20 * (1 - (70-50)/40) = 20 * 0.5 = 10
        assert result["breakdown"]["capacity_headroom"] == 10.0

    def test_breakdown_contains_all_categories(self):
        """Breakdown dict must contain exactly the expected keys."""
        graph = InfraGraph()
        graph.add_component(_make_component("app"))
        result = graph.resilience_score_v2()

        expected_keys = {
            "redundancy",
            "circuit_breaker_coverage",
            "auto_recovery",
            "dependency_risk",
            "capacity_headroom",
        }
        assert set(result["breakdown"].keys()) == expected_keys

    def test_result_structure(self):
        """Result must have score, breakdown, and recommendations."""
        graph = InfraGraph()
        graph.add_component(_make_component("app"))
        result = graph.resilience_score_v2()

        assert "score" in result
        assert "breakdown" in result
        assert "recommendations" in result
        assert isinstance(result["score"], float)
        assert isinstance(result["breakdown"], dict)
        assert isinstance(result["recommendations"], list)

    def test_v1_still_works_unchanged(self):
        """Backward compatibility: resilience_score() (v1) must still work."""
        graph = InfraGraph()
        graph.add_component(_make_component("app"))
        v1_score = graph.resilience_score()
        assert isinstance(v1_score, float)
        assert 0.0 <= v1_score <= 100.0

    def test_v1_and_v2_coexist(self):
        """Both v1 and v2 should be callable on the same graph."""
        graph = InfraGraph()
        graph.add_component(_make_component("app", replicas=3, failover=True))
        graph.add_component(_make_component("db", ctype=ComponentType.DATABASE))
        graph.add_dependency(_make_dep("app", "db", cb_enabled=True))

        v1 = graph.resilience_score()
        v2 = graph.resilience_score_v2()

        assert isinstance(v1, float)
        assert isinstance(v2, dict)
        assert "score" in v2

    def test_recommendations_generated_for_weak_graph(self):
        """A graph with no redundancy or CB should generate recommendations."""
        graph = InfraGraph()
        graph.add_component(_make_component("app"))
        graph.add_component(_make_component("db"))
        graph.add_dependency(_make_dep("app", "db", cb_enabled=False))

        result = graph.resilience_score_v2()
        assert len(result["recommendations"]) > 0

    def test_perfect_score_graph(self):
        """A well-configured graph should score close to 100."""
        graph = InfraGraph()
        graph.add_component(
            _make_component("app", replicas=3, failover=True, autoscaling=True)
        )
        graph.add_component(
            _make_component("db", replicas=3, failover=True, autoscaling=True, ctype=ComponentType.DATABASE)
        )
        graph.add_dependency(_make_dep("app", "db", cb_enabled=True))

        result = graph.resilience_score_v2()
        # Should be near 100: redundancy=20, cb=20, recovery=20, dep_risk~high, headroom=20
        assert result["score"] >= 80.0
        assert result["breakdown"]["redundancy"] == 20.0
        assert result["breakdown"]["circuit_breaker_coverage"] == 20.0
        assert result["breakdown"]["auto_recovery"] == 20.0
        assert result["breakdown"]["capacity_headroom"] == 20.0

    def test_score_bounded_0_to_100(self):
        """Score must always be between 0 and 100."""
        graph = InfraGraph()
        graph.add_component(_make_component("app", cpu_percent=99.0))
        result = graph.resilience_score_v2()
        assert 0.0 <= result["score"] <= 100.0

    def test_dependency_depth_impact(self):
        """Deep dependency chains should lower the dependency_risk score."""
        # Shallow: A -> B
        g1 = InfraGraph()
        g1.add_component(_make_component("a", replicas=3, failover=True))
        g1.add_component(_make_component("b", replicas=3, failover=True))
        g1.add_dependency(_make_dep("a", "b", cb_enabled=True))
        r1 = g1.resilience_score_v2()

        # Deep chain: A -> B -> C -> D -> E -> F
        g2 = InfraGraph()
        for name in ["a", "b", "c", "d", "e", "f"]:
            g2.add_component(_make_component(name, replicas=3, failover=True))
        for src, tgt in [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "f")]:
            g2.add_dependency(_make_dep(src, tgt, cb_enabled=True))
        r2 = g2.resilience_score_v2()

        # Deeper chain should have lower dependency_risk
        assert r1["breakdown"]["dependency_risk"] >= r2["breakdown"]["dependency_risk"]
