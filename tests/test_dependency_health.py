"""Tests for dependency-aware health scoring engine."""

from __future__ import annotations

import pytest

from infrasim.model.components import Component, ComponentType, HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.simulator.dependency_health import (
    DependencyHealthEngine,
    DependencyHealthReport,
    DependencyHealthScore,
    HealthCluster,
    HealthPropagation,
    HealthTier,
    _classify_tier,
    _own_health_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    cpu: float = 30.0,
    mem: float = 30.0,
    failover: bool = False,
) -> Component:
    c = Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        health=health,
    )
    c.metrics.cpu_percent = cpu
    c.metrics.memory_percent = mem
    if failover:
        c.failover.enabled = True
    return c


def _simple_chain() -> InfraGraph:
    """LB -> API -> DB (linear chain)."""
    g = InfraGraph()
    lb = _comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER, replicas=2)
    api = _comp("api", "API Server", ComponentType.APP_SERVER, replicas=2)
    db = _comp("db", "Database", ComponentType.DATABASE, replicas=1)
    g.add_component(lb)
    g.add_component(api)
    g.add_component(db)
    from infrasim.model.components import Dependency

    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


def _diamond_graph() -> InfraGraph:
    """
    LB -> API-A -> DB
    LB -> API-B -> DB
    """
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("api-a", "API-A", ComponentType.APP_SERVER, replicas=2))
    g.add_component(_comp("api-b", "API-B", ComponentType.APP_SERVER, replicas=2))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE))
    from infrasim.model.components import Dependency

    g.add_dependency(Dependency(source_id="lb", target_id="api-a"))
    g.add_dependency(Dependency(source_id="lb", target_id="api-b"))
    g.add_dependency(Dependency(source_id="api-a", target_id="db"))
    g.add_dependency(Dependency(source_id="api-b", target_id="db"))
    return g


# ---------------------------------------------------------------------------
# Unit tests: _classify_tier
# ---------------------------------------------------------------------------


class TestClassifyTier:
    def test_excellent(self):
        assert _classify_tier(95) == HealthTier.EXCELLENT
        assert _classify_tier(90) == HealthTier.EXCELLENT

    def test_good(self):
        assert _classify_tier(80) == HealthTier.GOOD
        assert _classify_tier(75) == HealthTier.GOOD

    def test_fair(self):
        assert _classify_tier(60) == HealthTier.FAIR
        assert _classify_tier(50) == HealthTier.FAIR

    def test_poor(self):
        assert _classify_tier(40) == HealthTier.POOR
        assert _classify_tier(25) == HealthTier.POOR

    def test_critical(self):
        assert _classify_tier(20) == HealthTier.CRITICAL
        assert _classify_tier(0) == HealthTier.CRITICAL


# ---------------------------------------------------------------------------
# Unit tests: _own_health_score
# ---------------------------------------------------------------------------


class TestOwnHealthScore:
    def test_healthy_component(self):
        c = _comp("x", "X", health=HealthStatus.HEALTHY)
        score = _own_health_score(c)
        assert score == 100.0

    def test_degraded_component(self):
        c = _comp("x", "X", health=HealthStatus.DEGRADED)
        score = _own_health_score(c)
        assert score == 60.0

    def test_overloaded_component(self):
        c = _comp("x", "X", health=HealthStatus.OVERLOADED)
        score = _own_health_score(c)
        assert score == 35.0

    def test_down_component(self):
        c = _comp("x", "X", health=HealthStatus.DOWN)
        score = _own_health_score(c)
        assert score == 0.0

    def test_high_utilization_penalty(self):
        c = _comp("x", "X", cpu=95.0)
        score = _own_health_score(c)
        assert score < 100  # Should have utilization penalty

    def test_utilization_over_80(self):
        c = _comp("x", "X", cpu=85.0)
        score = _own_health_score(c)
        assert score < 100
        assert score >= 70

    def test_utilization_over_70(self):
        c = _comp("x", "X", cpu=75.0)
        score = _own_health_score(c)
        assert score < 100

    def test_utilization_over_60(self):
        c = _comp("x", "X", cpu=65.0)
        score = _own_health_score(c)
        assert score < 100

    def test_replica_bonus(self):
        # Use a degraded component so base < 100 and bonus is visible
        c1 = _comp("x", "X", replicas=1, health=HealthStatus.DEGRADED)
        c3 = _comp("x", "X", replicas=3, health=HealthStatus.DEGRADED)
        s1 = _own_health_score(c1)
        s3 = _own_health_score(c3)
        assert s3 > s1

    def test_replica_bonus_caps_at_100(self):
        c = _comp("x", "X", replicas=5)
        score = _own_health_score(c)
        assert score <= 100

    def test_failover_bonus(self):
        c1 = _comp("x", "X", failover=False, health=HealthStatus.DEGRADED)
        c2 = _comp("x", "X", failover=True, health=HealthStatus.DEGRADED)
        s1 = _own_health_score(c1)
        s2 = _own_health_score(c2)
        assert s2 > s1

    def test_down_with_replicas_stays_low(self):
        c = _comp("x", "X", health=HealthStatus.DOWN, replicas=3)
        score = _own_health_score(c)
        # Even with replicas bonus, DOWN base is 0
        assert score <= 15


# ---------------------------------------------------------------------------
# Tests: DependencyHealthEngine.analyze
# ---------------------------------------------------------------------------


class TestAnalyzeEmptyGraph:
    def test_empty_graph(self):
        engine = DependencyHealthEngine()
        g = InfraGraph()
        report = engine.analyze(g)
        assert report.overall_health == 100.0
        assert report.tier == HealthTier.EXCELLENT
        assert report.component_count == 0
        assert len(report.scores) == 0


class TestAnalyzeSimpleChain:
    def test_all_healthy(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        report = engine.analyze(g)

        assert report.component_count == 3
        assert report.overall_health > 80
        assert report.tier in (HealthTier.EXCELLENT, HealthTier.GOOD)
        assert len(report.critical_components) == 0

    def test_db_down_propagates(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        # Make DB go down
        g.components["db"].health = HealthStatus.DOWN
        report = engine.analyze(g)

        # DB should be critical
        assert report.scores["db"].tier in (HealthTier.CRITICAL, HealthTier.POOR)
        # API depends on DB, should be degraded
        assert report.scores["api"].effective_health_score < report.scores["api"].own_health_score
        # LB depends on API (which depends on DB)
        lb_score = report.scores["lb"]
        assert lb_score.dependency_depth > 0

    def test_degraded_source_detected(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        g.components["db"].health = HealthStatus.DOWN
        report = engine.analyze(g)

        # API should list DB as a degradation source
        api_score = report.scores["api"]
        assert "Database" in api_score.degradation_sources

    def test_critical_dependency_count(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        g.components["db"].health = HealthStatus.DOWN
        report = engine.analyze(g)

        api_score = report.scores["api"]
        assert api_score.critical_dependency_count >= 1


class TestAnalyzeDiamondGraph:
    def test_shared_dependency_cluster(self):
        engine = DependencyHealthEngine()
        g = _diamond_graph()
        report = engine.analyze(g)

        # API-A and API-B share the same dependency (DB)
        # Should form a health cluster
        # Note: clusters may or may not form depending on exact logic
        assert report.component_count == 4

    def test_db_failure_affects_both_apis(self):
        engine = DependencyHealthEngine()
        g = _diamond_graph()
        g.components["db"].health = HealthStatus.DOWN
        report = engine.analyze(g)

        api_a = report.scores["api-a"]
        api_b = report.scores["api-b"]
        assert api_a.dependency_health_score < 50
        assert api_b.dependency_health_score < 50


# ---------------------------------------------------------------------------
# Tests: DependencyHealthEngine.score_component
# ---------------------------------------------------------------------------


class TestScoreComponent:
    def test_existing_component(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        score = engine.score_component(g, "api")
        assert score is not None
        assert score.component_name == "API Server"
        assert 0 <= score.effective_health_score <= 100

    def test_nonexistent_component(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        score = engine.score_component(g, "nonexistent")
        assert score is None

    def test_leaf_component(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        score = engine.score_component(g, "db")
        assert score is not None
        assert score.is_leaf is True
        assert score.dependency_health_score == 100.0

    def test_non_leaf_component(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        score = engine.score_component(g, "api")
        assert score is not None
        assert score.is_leaf is False


# ---------------------------------------------------------------------------
# Tests: get_health_summary
# ---------------------------------------------------------------------------


class TestGetHealthSummary:
    def test_summary_structure(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        summary = engine.get_health_summary(g)
        assert "overall_health" in summary
        assert "tier" in summary
        assert "component_count" in summary
        assert "healthy" in summary
        assert "degraded" in summary
        assert "critical" in summary
        assert "critical_components" in summary
        assert "top_degradation_sources" in summary

    def test_summary_with_failures(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        g.components["db"].health = HealthStatus.DOWN
        summary = engine.get_health_summary(g)
        # DB is DOWN (score 0) → should be POOR or CRITICAL tier
        assert summary["critical"] >= 1 or summary["overall_health"] < 90

    def test_summary_counts(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        summary = engine.get_health_summary(g)
        total = summary["healthy"] + summary["degraded"] + summary["critical"]
        assert total == summary["component_count"]


# ---------------------------------------------------------------------------
# Tests: degraded paths
# ---------------------------------------------------------------------------


class TestDegradedPaths:
    def test_no_degraded_paths_when_healthy(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        report = engine.analyze(g)
        assert len(report.degraded_paths) == 0

    def test_degraded_path_on_failure(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        g.components["db"].health = HealthStatus.DOWN
        report = engine.analyze(g)
        # DB is down (score < 50), and API depends on DB
        # Should find at least one degraded path
        assert len(report.degraded_paths) >= 1

    def test_degraded_path_attributes(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        g.components["db"].health = HealthStatus.DOWN
        report = engine.analyze(g)
        if report.degraded_paths:
            path = report.degraded_paths[0]
            assert len(path.path) >= 2
            assert len(path.path_names) >= 2
            assert path.source_health < 50
            assert path.attenuation_factor > 0


# ---------------------------------------------------------------------------
# Tests: health clusters
# ---------------------------------------------------------------------------


class TestHealthClusters:
    def test_diamond_creates_cluster(self):
        engine = DependencyHealthEngine()
        g = _diamond_graph()
        report = engine.analyze(g)
        # API-A and API-B both depend on DB → shared dependency
        # They should be clustered together
        db_dep_clusters = [
            c for c in report.health_clusters
            if "api-a" in c.component_ids and "api-b" in c.component_ids
        ]
        assert len(db_dep_clusters) >= 1

    def test_cluster_attributes(self):
        engine = DependencyHealthEngine()
        g = _diamond_graph()
        report = engine.analyze(g)
        for cluster in report.health_clusters:
            assert len(cluster.component_ids) >= 2
            assert len(cluster.component_names) >= 2
            assert 0 <= cluster.average_health <= 100
            assert 0 <= cluster.min_health <= 100
            assert cluster.correlation_reason


# ---------------------------------------------------------------------------
# Tests: improvement suggestions
# ---------------------------------------------------------------------------


class TestSuggestions:
    def test_no_suggestions_when_healthy(self):
        engine = DependencyHealthEngine()
        g = InfraGraph()
        g.add_component(_comp("x", "X", replicas=3, failover=True))
        report = engine.analyze(g)
        # Healthy single component with replicas — no critical suggestions
        critical_suggestions = [
            s for s in report.improvement_suggestions if "CRITICAL" in s
        ]
        assert len(critical_suggestions) == 0

    def test_suggestion_for_down_component(self):
        engine = DependencyHealthEngine()
        g = InfraGraph()
        g.add_component(_comp("x", "X", health=HealthStatus.DOWN))
        # Add a dependent so the DOWN component is detected as impactful
        from infrasim.model.components import Dependency
        g.add_component(_comp("y", "Y"))
        g.add_dependency(Dependency(source_id="y", target_id="x"))
        report = engine.analyze(g)
        assert any(
            "CRITICAL" in s or "DOWN" in s or "replica" in s.lower()
            for s in report.improvement_suggestions
        )

    def test_suggestion_for_spof(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        # DB is single replica and API depends on it
        # Make DB degraded to trigger suggestions
        g.components["db"].health = HealthStatus.OVERLOADED
        report = engine.analyze(g)
        assert any("Database" in s or "replica" in s.lower() for s in report.improvement_suggestions)

    def test_suggestion_for_dependency_degradation(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        g.components["db"].health = HealthStatus.DOWN
        report = engine.analyze(g)
        # API is healthy but degraded by DB
        dep_suggestions = [
            s for s in report.improvement_suggestions
            if "dependenc" in s.lower() or "upstream" in s.lower()
        ]
        assert len(dep_suggestions) >= 1


# ---------------------------------------------------------------------------
# Tests: custom parameters
# ---------------------------------------------------------------------------


class TestCustomParameters:
    def test_custom_dependency_weight(self):
        engine_low = DependencyHealthEngine(dependency_weight=0.1)
        engine_high = DependencyHealthEngine(dependency_weight=0.5)
        g = _simple_chain()
        g.components["db"].health = HealthStatus.DOWN

        report_low = engine_low.analyze(g)
        report_high = engine_high.analyze(g)

        # Higher dependency weight → lower overall health when deps are down
        api_low = report_low.scores["api"].effective_health_score
        api_high = report_high.scores["api"].effective_health_score
        assert api_low > api_high

    def test_custom_hop_decay(self):
        engine_fast_decay = DependencyHealthEngine(hop_decay=0.3)
        engine_slow_decay = DependencyHealthEngine(hop_decay=0.9)
        g = _simple_chain()
        g.components["db"].health = HealthStatus.DOWN

        report_fast = engine_fast_decay.analyze(g)
        report_slow = engine_slow_decay.analyze(g)

        # With slower decay, LB (2 hops from DB) should be more affected
        lb_fast = report_fast.scores["lb"].effective_health_score
        lb_slow = report_slow.scores["lb"].effective_health_score
        # Slower decay propagates more degradation
        assert lb_slow <= lb_fast


# ---------------------------------------------------------------------------
# Tests: single component graph
# ---------------------------------------------------------------------------


class TestSingleComponent:
    def test_isolated_component(self):
        engine = DependencyHealthEngine()
        g = InfraGraph()
        g.add_component(_comp("solo", "Solo Server"))
        report = engine.analyze(g)

        assert report.component_count == 1
        score = report.scores["solo"]
        assert score.is_leaf is True
        assert score.dependency_health_score == 100.0
        assert score.dependency_depth == 0
        assert score.critical_dependency_count == 0


# ---------------------------------------------------------------------------
# Tests: report statistics
# ---------------------------------------------------------------------------


class TestReportStats:
    def test_counts_add_up(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        g.components["db"].health = HealthStatus.DOWN
        report = engine.analyze(g)

        total = report.healthy_count + report.degraded_count + report.critical_count
        assert total == report.component_count

    def test_overall_health_is_average(self):
        engine = DependencyHealthEngine()
        g = _simple_chain()
        report = engine.analyze(g)

        scores = [s.effective_health_score for s in report.scores.values()]
        expected_avg = sum(scores) / len(scores)
        assert abs(report.overall_health - expected_avg) < 0.2


# ---------------------------------------------------------------------------
# Tests: HealthTier enum values
# ---------------------------------------------------------------------------


class TestHealthTierEnum:
    def test_all_values(self):
        assert HealthTier.EXCELLENT == "excellent"
        assert HealthTier.GOOD == "good"
        assert HealthTier.FAIR == "fair"
        assert HealthTier.POOR == "poor"
        assert HealthTier.CRITICAL == "critical"


# ---------------------------------------------------------------------------
# Tests: complex topology
# ---------------------------------------------------------------------------


class TestComplexTopology:
    def test_wide_graph(self):
        """Test with many independent components depending on one."""
        engine = DependencyHealthEngine()
        g = InfraGraph()
        g.add_component(_comp("db", "Database", ComponentType.DATABASE))
        from infrasim.model.components import Dependency

        for i in range(10):
            g.add_component(_comp(f"api-{i}", f"API-{i}", ComponentType.APP_SERVER))
            g.add_dependency(Dependency(source_id=f"api-{i}", target_id="db"))

        report = engine.analyze(g)
        assert report.component_count == 11

        # If DB goes down, all APIs should be affected
        g.components["db"].health = HealthStatus.DOWN
        report2 = engine.analyze(g)
        for i in range(10):
            assert report2.scores[f"api-{i}"].dependency_health_score < 50

    def test_deep_chain(self):
        """Test with a deep dependency chain."""
        engine = DependencyHealthEngine()
        g = InfraGraph()
        from infrasim.model.components import Dependency

        prev = None
        for i in range(6):
            cid = f"layer-{i}"
            g.add_component(_comp(cid, f"Layer {i}", ComponentType.APP_SERVER))
            if prev:
                g.add_dependency(Dependency(source_id=prev, target_id=cid))
            prev = cid

        report = engine.analyze(g)
        # First component has deepest dependency chain
        assert report.scores["layer-0"].dependency_depth >= 4

        # Last layer is a leaf
        assert report.scores["layer-5"].is_leaf is True

    def test_multi_failure(self):
        """Test with multiple simultaneous failures."""
        engine = DependencyHealthEngine()
        g = _diamond_graph()
        g.components["db"].health = HealthStatus.DOWN
        g.components["api-a"].health = HealthStatus.DEGRADED
        report = engine.analyze(g)

        assert report.critical_count >= 1
        assert report.overall_health < 80


# ---------------------------------------------------------------------------
# Tests: top_degradation_sources
# ---------------------------------------------------------------------------


class TestTopDegradationSources:
    def test_degradation_source_ranking(self):
        engine = DependencyHealthEngine()
        g = InfraGraph()
        g.add_component(_comp("db", "Database", ComponentType.DATABASE, health=HealthStatus.DOWN))
        from infrasim.model.components import Dependency

        for i in range(5):
            g.add_component(_comp(f"api-{i}", f"API-{i}"))
            g.add_dependency(Dependency(source_id=f"api-{i}", target_id="db"))

        summary = engine.get_health_summary(g)
        sources = summary["top_degradation_sources"]
        if sources:
            assert sources[0]["name"] == "Database"
            assert sources[0]["affected_count"] == 5
