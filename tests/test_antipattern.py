"""Tests for Architecture Anti-Pattern Detector."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    RetryStrategy,
    SingleflightConfig,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.antipattern_detector import AntiPattern, AntiPatternDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_graph() -> InfraGraph:
    return InfraGraph()


def _single_component_graph() -> InfraGraph:
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    return graph


def _healthy_graph() -> InfraGraph:
    """Graph with no anti-patterns: multi-AZ, circuit breakers, health checks."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
        region=RegionConfig(availability_zone="us-east-1a"),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=10),
        region=RegionConfig(availability_zone="us-east-1b"),
        singleflight=SingleflightConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=2,
        region=RegionConfig(availability_zone="us-east-1c"),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(enabled=True, jitter=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(enabled=True, jitter=True),
    ))
    return graph


def _god_component_graph() -> InfraGraph:
    """Graph where one component has >50% dependents."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="Central DB", type=ComponentType.DATABASE,
    ))
    for i in range(5):
        cid = f"app_{i}"
        graph.add_component(Component(
            id=cid, name=f"App {i}", type=ComponentType.APP_SERVER,
        ))
        graph.add_dependency(Dependency(
            source_id=cid, target_id="db", dependency_type="requires",
        ))
    return graph


def _circular_graph() -> InfraGraph:
    """Graph with circular dependency A -> B -> C -> A."""
    graph = InfraGraph()
    for cid in ["a", "b", "c"]:
        graph.add_component(Component(
            id=cid, name=cid.upper(), type=ComponentType.APP_SERVER,
        ))
    graph.add_dependency(Dependency(source_id="a", target_id="b"))
    graph.add_dependency(Dependency(source_id="b", target_id="c"))
    graph.add_dependency(Dependency(source_id="c", target_id="a"))
    return graph


def _single_az_graph() -> InfraGraph:
    """Graph with all components in one AZ."""
    graph = InfraGraph()
    for cid in ["app", "db", "cache"]:
        graph.add_component(Component(
            id=cid, name=cid, type=ComponentType.APP_SERVER,
            region=RegionConfig(availability_zone="us-east-1a"),
        ))
    return graph


def _no_health_check_lb_graph() -> InfraGraph:
    """Graph with an LB that has no health check."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        failover=FailoverConfig(enabled=False),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    return graph


def _db_direct_access_graph() -> InfraGraph:
    """Graph where multiple app servers access DB directly."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
    ))
    for i in range(3):
        cid = f"app_{i}"
        graph.add_component(Component(
            id=cid, name=f"App {i}", type=ComponentType.APP_SERVER,
        ))
        graph.add_dependency(Dependency(
            source_id=cid, target_id="db", dependency_type="requires",
        ))
    return graph


def _thundering_herd_graph() -> InfraGraph:
    """Graph with thundering herd risk (no jitter/singleflight)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
    ))
    for i in range(3):
        cid = f"app_{i}"
        graph.add_component(Component(
            id=cid, name=f"App {i}", type=ComponentType.APP_SERVER,
        ))
        graph.add_dependency(Dependency(
            source_id=cid, target_id="db", dependency_type="requires",
            retry_strategy=RetryStrategy(enabled=False),
        ))
    return graph


def _n_plus_one_graph() -> InfraGraph:
    """Graph with N+1 dependency: app depends on 3 DBs without LB."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    for i in range(3):
        cid = f"db_{i}"
        graph.add_component(Component(
            id=cid, name=f"DB {i}", type=ComponentType.DATABASE,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id=cid, dependency_type="requires",
        ))
    return graph


# ---------------------------------------------------------------------------
# Tests: AntiPatternDetector
# ---------------------------------------------------------------------------


class TestAntiPatternDetector:
    """Core detector functionality."""

    def test_detect_empty_graph(self):
        detector = AntiPatternDetector(_empty_graph())
        patterns = detector.detect()
        assert isinstance(patterns, list)

    def test_detect_single_component(self):
        detector = AntiPatternDetector(_single_component_graph())
        patterns = detector.detect()
        # A single component has no dependencies -> limited patterns
        assert isinstance(patterns, list)

    def test_detect_healthy_graph(self):
        detector = AntiPatternDetector(_healthy_graph())
        patterns = detector.detect()
        # The healthy graph should have no or minimal anti-patterns
        critical_patterns = [p for p in patterns if p.severity == "critical"]
        # Multi-AZ, circuit breakers, health checks are all configured
        assert len(critical_patterns) == 0

    def test_detect_returns_sorted_by_severity(self):
        """Anti-patterns should be sorted by severity descending."""
        detector = AntiPatternDetector(_god_component_graph())
        patterns = detector.detect()
        if len(patterns) >= 2:
            severity_order = {"critical": 3, "high": 2, "medium": 1}
            for i in range(len(patterns) - 1):
                assert (
                    severity_order.get(patterns[i].severity, 0)
                    >= severity_order.get(patterns[i + 1].severity, 0)
                )


class TestGodComponent:
    """Tests for god component detection."""

    def test_god_component_detected(self):
        detector = AntiPatternDetector(_god_component_graph())
        patterns = detector.detect()
        god_patterns = [p for p in patterns if p.id == "god_component"]
        assert len(god_patterns) >= 1
        assert god_patterns[0].severity == "critical"
        assert "db" in god_patterns[0].affected_components

    def test_no_god_component_in_healthy(self):
        detector = AntiPatternDetector(_healthy_graph())
        patterns = detector.detect()
        god_patterns = [p for p in patterns if p.id == "god_component"]
        assert len(god_patterns) == 0


class TestCircularDependency:
    """Tests for circular dependency detection."""

    def test_circular_dependency_detected(self):
        detector = AntiPatternDetector(_circular_graph())
        patterns = detector.detect()
        cycle_patterns = [p for p in patterns if p.id == "circular_dependency"]
        assert len(cycle_patterns) >= 1
        assert cycle_patterns[0].severity == "high"

    def test_no_cycle_in_healthy(self):
        detector = AntiPatternDetector(_healthy_graph())
        patterns = detector.detect()
        cycle_patterns = [p for p in patterns if p.id == "circular_dependency"]
        assert len(cycle_patterns) == 0


class TestMissingCircuitBreaker:
    """Tests for missing circuit breaker detection."""

    def test_missing_cb_detected(self):
        """Graph with 'requires' edges but no circuit breakers."""
        detector = AntiPatternDetector(_god_component_graph())
        patterns = detector.detect()
        cb_patterns = [p for p in patterns if p.id == "missing_circuit_breaker"]
        assert len(cb_patterns) >= 1
        assert cb_patterns[0].severity == "high"

    def test_no_missing_cb_when_all_enabled(self):
        detector = AntiPatternDetector(_healthy_graph())
        patterns = detector.detect()
        cb_patterns = [p for p in patterns if p.id == "missing_circuit_breaker"]
        assert len(cb_patterns) == 0


class TestSingleAZ:
    """Tests for single availability zone detection."""

    def test_single_az_detected(self):
        detector = AntiPatternDetector(_single_az_graph())
        patterns = detector.detect()
        az_patterns = [p for p in patterns if p.id == "single_az"]
        assert len(az_patterns) == 1
        assert az_patterns[0].severity == "critical"

    def test_multi_az_clean(self):
        detector = AntiPatternDetector(_healthy_graph())
        patterns = detector.detect()
        az_patterns = [p for p in patterns if p.id == "single_az"]
        assert len(az_patterns) == 0


class TestNoHealthCheck:
    """Tests for load balancer health check detection."""

    def test_no_health_check_detected(self):
        detector = AntiPatternDetector(_no_health_check_lb_graph())
        patterns = detector.detect()
        hc_patterns = [p for p in patterns if p.id == "no_health_check"]
        assert len(hc_patterns) == 1
        assert hc_patterns[0].severity == "high"
        assert "lb" in hc_patterns[0].affected_components

    def test_health_check_present(self):
        detector = AntiPatternDetector(_healthy_graph())
        patterns = detector.detect()
        hc_patterns = [p for p in patterns if p.id == "no_health_check"]
        assert len(hc_patterns) == 0


class TestDatabaseDirectAccess:
    """Tests for database direct access detection."""

    def test_direct_db_access_detected(self):
        detector = AntiPatternDetector(_db_direct_access_graph())
        patterns = detector.detect()
        db_patterns = [p for p in patterns if p.id == "database_direct_access"]
        assert len(db_patterns) >= 1
        assert db_patterns[0].severity == "medium"
        assert "db" in db_patterns[0].affected_components


class TestThunderingHerd:
    """Tests for thundering herd risk detection."""

    def test_thundering_herd_detected(self):
        detector = AntiPatternDetector(_thundering_herd_graph())
        patterns = detector.detect()
        th_patterns = [p for p in patterns if p.id == "thundering_herd"]
        assert len(th_patterns) >= 1
        assert th_patterns[0].severity == "medium"

    def test_no_thundering_herd_with_jitter(self):
        detector = AntiPatternDetector(_healthy_graph())
        patterns = detector.detect()
        th_patterns = [p for p in patterns if p.id == "thundering_herd"]
        assert len(th_patterns) == 0


class TestNPlusOne:
    """Tests for N+1 dependency detection."""

    def test_n_plus_one_detected(self):
        detector = AntiPatternDetector(_n_plus_one_graph())
        patterns = detector.detect()
        np_patterns = [p for p in patterns if p.id == "n_plus_one"]
        assert len(np_patterns) >= 1
        assert np_patterns[0].severity == "medium"
        assert "app" in np_patterns[0].affected_components

    def test_lb_not_flagged_for_n_plus_one(self):
        """LBs with multiple backends should NOT be flagged."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="lb", name="LB", type=ComponentType.LOAD_BALANCER,
        ))
        for i in range(3):
            cid = f"app_{i}"
            graph.add_component(Component(
                id=cid, name=f"App {i}", type=ComponentType.APP_SERVER,
            ))
            graph.add_dependency(Dependency(
                source_id="lb", target_id=cid, dependency_type="requires",
            ))
        detector = AntiPatternDetector(graph)
        patterns = detector.detect()
        np_patterns = [p for p in patterns if p.id == "n_plus_one"]
        assert len(np_patterns) == 0


class TestDetectBySeverity:
    """Tests for severity filtering."""

    def test_filter_by_critical(self):
        detector = AntiPatternDetector(_god_component_graph())
        all_patterns = detector.detect()
        critical_only = detector.detect_by_severity("critical")
        assert len(critical_only) <= len(all_patterns)
        for p in critical_only:
            assert p.severity == "critical"

    def test_filter_by_high(self):
        detector = AntiPatternDetector(_god_component_graph())
        high_plus = detector.detect_by_severity("high")
        for p in high_plus:
            assert p.severity in ("critical", "high")

    def test_filter_by_medium_returns_all(self):
        detector = AntiPatternDetector(_god_component_graph())
        all_p = detector.detect()
        medium_plus = detector.detect_by_severity("medium")
        assert len(medium_plus) == len(all_p)


class TestAntiPatternDataclass:
    """Tests for the AntiPattern dataclass."""

    def test_antipattern_fields(self):
        ap = AntiPattern(
            id="test",
            name="Test Pattern",
            severity="high",
            description="A test pattern",
            affected_components=["a", "b"],
            recommendation="Fix it",
            reference="https://example.com",
        )
        assert ap.id == "test"
        assert ap.name == "Test Pattern"
        assert ap.severity == "high"
        assert len(ap.affected_components) == 2
        assert ap.recommendation == "Fix it"
        assert ap.reference == "https://example.com"

    def test_antipattern_defaults(self):
        ap = AntiPattern(
            id="test",
            name="Test",
            severity="medium",
            description="Desc",
        )
        assert ap.affected_components == []
        assert ap.recommendation == ""
        assert ap.reference == ""


# ---------------------------------------------------------------------------
# Additional edge case tests
# ---------------------------------------------------------------------------


class TestNoAZSet:
    """Test when no component has any AZ configured (no AZ awareness)."""

    def test_no_az_on_any_component(self):
        graph = InfraGraph()
        for cid in ["app", "db"]:
            graph.add_component(Component(
                id=cid, name=cid, type=ComponentType.APP_SERVER,
                region=RegionConfig(),  # no AZ set
            ))
        detector = AntiPatternDetector(graph)
        patterns = detector.detect()
        az_patterns = [p for p in patterns if p.id == "single_az"]
        assert len(az_patterns) == 1
        assert az_patterns[0].severity == "critical"
        assert "No availability zone" in az_patterns[0].description


class TestMixedAZ:
    """Partial AZ coverage should NOT trigger single_az."""

    def test_some_components_have_az_some_dont(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            region=RegionConfig(availability_zone="us-east-1a"),
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            region=RegionConfig(),  # no AZ
        ))
        detector = AntiPatternDetector(graph)
        patterns = detector.detect()
        az_patterns = [p for p in patterns if p.id == "single_az"]
        assert len(az_patterns) == 0


class TestDatabaseDirectAccessSingleApp:
    """Single app server accessing DB directly should NOT be flagged."""

    def test_single_app_to_db(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="Database", type=ComponentType.DATABASE,
        ))
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        detector = AntiPatternDetector(graph)
        patterns = detector.detect()
        db_patterns = [p for p in patterns if p.id == "database_direct_access"]
        assert len(db_patterns) == 0


class TestThunderingHerdWithSingleflight:
    """Components with singleflight enabled should not be flagged."""

    def test_singleflight_prevents_thundering_herd(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="Database", type=ComponentType.DATABASE,
        ))
        for i in range(3):
            cid = f"app_{i}"
            graph.add_component(Component(
                id=cid, name=f"App {i}", type=ComponentType.APP_SERVER,
                singleflight=SingleflightConfig(enabled=True),
            ))
            graph.add_dependency(Dependency(
                source_id=cid, target_id="db", dependency_type="requires",
                retry_strategy=RetryStrategy(enabled=False),
            ))
        detector = AntiPatternDetector(graph)
        patterns = detector.detect()
        th_patterns = [p for p in patterns if p.id == "thundering_herd"]
        assert len(th_patterns) == 0


class TestSeverityOrdering:
    """Verify severity ordering constant is correct."""

    def test_severity_order_values(self):
        from faultray.simulator.antipattern_detector import _SEVERITY_ORDER
        assert _SEVERITY_ORDER["critical"] > _SEVERITY_ORDER["high"]
        assert _SEVERITY_ORDER["high"] > _SEVERITY_ORDER["medium"]
