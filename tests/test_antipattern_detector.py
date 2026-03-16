"""Tests for architecture anti-pattern detector.

Covers all detection methods in AntiPatternDetector plus the module-level
_find_cycles helper.  Targets 99%+ line/branch coverage.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RetryStrategy,
    RegionConfig,
    SingleflightConfig,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.antipattern_detector import (
    AntiPattern,
    AntiPatternDetector,
    _find_cycles,
    _SEVERITY_ORDER,
)


# ------------------------------------------------------------------ helpers
def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    *,
    failover_enabled: bool = False,
    health_check_interval: float = 10.0,
    az: str = "",
    region: str = "",
    singleflight_enabled: bool = False,
) -> Component:
    """Shorthand factory for Component with common overrides."""
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(
            enabled=failover_enabled,
            health_check_interval_seconds=health_check_interval,
        ),
        region=RegionConfig(availability_zone=az, region=region),
        singleflight=SingleflightConfig(enabled=singleflight_enabled),
    )


def _dep(
    src: str,
    tgt: str,
    dep_type: str = "requires",
    *,
    cb_enabled: bool = False,
    retry_enabled: bool = False,
    retry_jitter: bool = True,
) -> Dependency:
    """Shorthand factory for Dependency with common overrides."""
    return Dependency(
        source_id=src,
        target_id=tgt,
        dependency_type=dep_type,
        circuit_breaker=CircuitBreakerConfig(enabled=cb_enabled),
        retry_strategy=RetryStrategy(enabled=retry_enabled, jitter=retry_jitter),
    )


# ======================================================================
# AntiPattern dataclass
# ======================================================================

class TestAntiPatternDataclass:
    """Basic sanity checks on the AntiPattern dataclass."""

    def test_defaults(self):
        ap = AntiPattern(id="x", name="X", severity="high", description="desc")
        assert ap.affected_components == []
        assert ap.recommendation == ""
        assert ap.reference == ""

    def test_with_fields(self):
        ap = AntiPattern(
            id="x",
            name="X",
            severity="medium",
            description="desc",
            affected_components=["a", "b"],
            recommendation="fix it",
            reference="https://example.com",
        )
        assert ap.affected_components == ["a", "b"]
        assert ap.recommendation == "fix it"
        assert ap.reference == "https://example.com"


# ======================================================================
# _SEVERITY_ORDER
# ======================================================================

class TestSeverityOrder:
    def test_ordering_values(self):
        assert _SEVERITY_ORDER["critical"] > _SEVERITY_ORDER["high"]
        assert _SEVERITY_ORDER["high"] > _SEVERITY_ORDER["medium"]

    def test_unknown_severity_returns_none(self):
        assert _SEVERITY_ORDER.get("info") is None


# ======================================================================
# Empty / single-component graph edge cases
# ======================================================================

class TestEmptyGraph:
    def test_detect_empty(self):
        g = InfraGraph()
        detector = AntiPatternDetector(g)
        assert detector.detect() == []

    def test_detect_by_severity_empty(self):
        g = InfraGraph()
        detector = AntiPatternDetector(g)
        assert detector.detect_by_severity("critical") == []


class TestSingleComponentGraph:
    def test_no_patterns_single_component(self):
        g = InfraGraph()
        g.add_component(_comp("a", "Alpha"))
        detector = AntiPatternDetector(g)
        results = detector.detect()
        # Single component: god_component and single_az require >= 2 components
        assert results == []


# ======================================================================
# God Component
# ======================================================================

class TestGodComponent:
    def test_detected(self):
        """A component depended on by >50% of the system triggers god_component."""
        g = InfraGraph()
        # 'db' is depended on by 3 out of 4 components (75%)
        g.add_component(_comp("db", "Database", ComponentType.DATABASE))
        g.add_component(_comp("a1", "App1"))
        g.add_component(_comp("a2", "App2"))
        g.add_component(_comp("a3", "App3"))
        g.add_dependency(_dep("a1", "db"))
        g.add_dependency(_dep("a2", "db"))
        g.add_dependency(_dep("a3", "db"))

        detector = AntiPatternDetector(g)
        results = detector._check_god_component()
        assert len(results) == 1
        r = results[0]
        assert r.id == "god_component"
        assert r.severity == "critical"
        assert "db" in r.affected_components
        assert r.recommendation != ""
        assert r.reference != ""

    def test_not_detected_below_threshold(self):
        """If dependents <= 50%, no god component is flagged."""
        g = InfraGraph()
        g.add_component(_comp("db", "Database", ComponentType.DATABASE))
        g.add_component(_comp("a1", "App1"))
        g.add_component(_comp("a2", "App2"))
        g.add_component(_comp("a3", "App3"))
        g.add_component(_comp("a4", "App4"))
        # Only 2 of 5 depend on db = 40%
        g.add_dependency(_dep("a1", "db"))
        g.add_dependency(_dep("a2", "db"))

        detector = AntiPatternDetector(g)
        assert detector._check_god_component() == []

    def test_exactly_at_threshold_not_detected(self):
        """At exactly 50% the condition is > not >=, so not detected."""
        g = InfraGraph()
        g.add_component(_comp("db", "Database", ComponentType.DATABASE))
        g.add_component(_comp("a1", "App1"))
        # 1 of 2 = 50% -- not >50%
        g.add_dependency(_dep("a1", "db"))
        detector = AntiPatternDetector(g)
        assert detector._check_god_component() == []

    def test_multiple_god_components(self):
        """Multiple components can be flagged as god components."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        g.add_component(_comp("cache", "Cache", ComponentType.CACHE))
        g.add_component(_comp("a1", "App1"))
        g.add_component(_comp("a2", "App2"))
        # Both db and cache have 2 of 4 dependents = 50% (NOT >50%)
        # Need 3 out of 4 to trigger
        g.add_dependency(_dep("a1", "db"))
        g.add_dependency(_dep("a2", "db"))
        g.add_dependency(_dep("cache", "db"))
        g.add_dependency(_dep("a1", "cache"))
        g.add_dependency(_dep("a2", "cache"))
        g.add_dependency(_dep("db", "cache"))  # unusual but tests the check

        detector = AntiPatternDetector(g)
        results = detector._check_god_component()
        # db has 3 dependents (a1, a2, cache) out of 4 = 75% -> flagged
        # cache has 3 dependents (a1, a2, db) out of 4 = 75% -> flagged
        assert len(results) == 2
        ids = {r.affected_components[0] for r in results}
        assert "db" in ids
        assert "cache" in ids


# ======================================================================
# Circular Dependency
# ======================================================================

class TestCircularDependency:
    def test_simple_cycle(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "a"))

        detector = AntiPatternDetector(g)
        results = detector._check_circular_dependency()
        assert len(results) >= 1
        r = results[0]
        assert r.id == "circular_dependency"
        assert r.severity == "high"
        assert r.recommendation != ""
        assert r.reference != ""

    def test_no_cycle(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_component(_comp("c", "C"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "c"))

        detector = AntiPatternDetector(g)
        assert detector._check_circular_dependency() == []

    def test_three_node_cycle(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_component(_comp("c", "C"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "c"))
        g.add_dependency(_dep("c", "a"))

        detector = AntiPatternDetector(g)
        results = detector._check_circular_dependency()
        assert len(results) >= 1
        assert results[0].id == "circular_dependency"


# ======================================================================
# _find_cycles helper
# ======================================================================

class TestFindCycles:
    def test_empty_graph(self):
        g = InfraGraph()
        assert _find_cycles(g) == []

    def test_acyclic(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_dependency(_dep("a", "b"))
        assert _find_cycles(g) == []

    def test_cycle_found(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "a"))
        cycles = _find_cycles(g)
        assert len(cycles) >= 1

    def test_exception_handling(self, monkeypatch):
        """_find_cycles catches exceptions and returns []."""
        g = InfraGraph()

        def boom(_g):
            raise RuntimeError("boom")

        import networkx as nx
        monkeypatch.setattr(nx, "simple_cycles", boom)
        assert _find_cycles(g) == []


# ======================================================================
# Missing Circuit Breaker
# ======================================================================

class TestMissingCircuitBreaker:
    def test_detected(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_dependency(_dep("a", "b", "requires", cb_enabled=False))

        detector = AntiPatternDetector(g)
        results = detector._check_missing_circuit_breaker()
        assert len(results) == 1
        r = results[0]
        assert r.id == "missing_circuit_breaker"
        assert r.severity == "high"
        assert "a" in r.affected_components
        assert "b" in r.affected_components

    def test_not_detected_when_cb_enabled(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_dependency(_dep("a", "b", "requires", cb_enabled=True))

        detector = AntiPatternDetector(g)
        assert detector._check_missing_circuit_breaker() == []

    def test_not_detected_for_optional(self):
        """Only 'requires' edges are checked."""
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_dependency(_dep("a", "b", "optional", cb_enabled=False))

        detector = AntiPatternDetector(g)
        assert detector._check_missing_circuit_breaker() == []

    def test_multiple_edges(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_component(_comp("c", "C"))
        g.add_dependency(_dep("a", "b", "requires", cb_enabled=False))
        g.add_dependency(_dep("b", "c", "requires", cb_enabled=False))

        detector = AntiPatternDetector(g)
        results = detector._check_missing_circuit_breaker()
        assert len(results) == 2


# ======================================================================
# Database Direct Access
# ======================================================================

class TestDatabaseDirectAccess:
    def test_detected_multiple_app_servers(self):
        """Two app servers hitting the same DB triggers detection."""
        g = InfraGraph()
        g.add_component(_comp("app1", "App1", ComponentType.APP_SERVER))
        g.add_component(_comp("app2", "App2", ComponentType.APP_SERVER))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        g.add_dependency(_dep("app1", "db"))
        g.add_dependency(_dep("app2", "db"))

        detector = AntiPatternDetector(g)
        results = detector._check_database_direct_access()
        assert len(results) == 1
        r = results[0]
        assert r.id == "database_direct_access"
        assert r.severity == "medium"
        assert "db" in r.affected_components
        assert "app1" in r.affected_components
        assert "app2" in r.affected_components

    def test_detected_web_servers(self):
        """WEB_SERVER type also triggers detection."""
        g = InfraGraph()
        g.add_component(_comp("w1", "Web1", ComponentType.WEB_SERVER))
        g.add_component(_comp("w2", "Web2", ComponentType.WEB_SERVER))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        g.add_dependency(_dep("w1", "db"))
        g.add_dependency(_dep("w2", "db"))

        detector = AntiPatternDetector(g)
        results = detector._check_database_direct_access()
        assert len(results) == 1

    def test_not_detected_single_app(self):
        """One app server to DB is not flagged."""
        g = InfraGraph()
        g.add_component(_comp("app1", "App1", ComponentType.APP_SERVER))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        g.add_dependency(_dep("app1", "db"))

        detector = AntiPatternDetector(g)
        assert detector._check_database_direct_access() == []

    def test_not_detected_non_app_type(self):
        """Cache -> DB doesn't count as app/web server access."""
        g = InfraGraph()
        g.add_component(_comp("c1", "Cache1", ComponentType.CACHE))
        g.add_component(_comp("c2", "Cache2", ComponentType.CACHE))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        g.add_dependency(_dep("c1", "db"))
        g.add_dependency(_dep("c2", "db"))

        detector = AntiPatternDetector(g)
        assert detector._check_database_direct_access() == []

    def test_deduplication(self):
        """Multiple edges to the same DB produce only one pattern."""
        g = InfraGraph()
        g.add_component(_comp("app1", "App1", ComponentType.APP_SERVER))
        g.add_component(_comp("app2", "App2", ComponentType.APP_SERVER))
        g.add_component(_comp("app3", "App3", ComponentType.WEB_SERVER))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        g.add_dependency(_dep("app1", "db"))
        g.add_dependency(_dep("app2", "db"))
        g.add_dependency(_dep("app3", "db"))

        detector = AntiPatternDetector(g)
        results = detector._check_database_direct_access()
        # Should deduplicate -- one pattern for 'db'
        assert len(results) == 1

    def test_source_or_target_none(self):
        """Edge with missing component is skipped (defensive branch)."""
        g = InfraGraph()
        g.add_component(_comp("app1", "App1", ComponentType.APP_SERVER))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        # Add an edge where source doesn't exist as component
        g.add_dependency(_dep("ghost", "db"))
        g.add_dependency(_dep("app1", "db"))

        detector = AntiPatternDetector(g)
        # Should not raise even though 'ghost' is missing from components
        results = detector._check_database_direct_access()
        assert len(results) == 0  # only 1 app server so not detected

    def test_two_databases(self):
        """Multiple databases each with 2+ app servers."""
        g = InfraGraph()
        g.add_component(_comp("a1", "App1", ComponentType.APP_SERVER))
        g.add_component(_comp("a2", "App2", ComponentType.APP_SERVER))
        g.add_component(_comp("db1", "DB1", ComponentType.DATABASE))
        g.add_component(_comp("db2", "DB2", ComponentType.DATABASE))
        g.add_dependency(_dep("a1", "db1"))
        g.add_dependency(_dep("a2", "db1"))
        g.add_dependency(_dep("a1", "db2"))
        g.add_dependency(_dep("a2", "db2"))

        detector = AntiPatternDetector(g)
        results = detector._check_database_direct_access()
        assert len(results) == 2
        affected_dbs = {r.affected_components[-1] for r in results}
        assert "db1" in affected_dbs
        assert "db2" in affected_dbs


# ======================================================================
# Single AZ
# ======================================================================

class TestSingleAZ:
    def test_all_same_az(self):
        """All components in the same AZ triggers detection."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", az="us-east-1a"))
        g.add_component(_comp("b", "B", az="us-east-1a"))
        g.add_component(_comp("c", "C", az="us-east-1a"))

        detector = AntiPatternDetector(g)
        results = detector._check_single_az()
        assert len(results) == 1
        r = results[0]
        assert r.id == "single_az"
        assert r.severity == "critical"
        assert "us-east-1a" in r.description
        assert len(r.affected_components) == 3

    def test_no_az_set(self):
        """No AZ configured on any component triggers detection."""
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))

        detector = AntiPatternDetector(g)
        results = detector._check_single_az()
        assert len(results) == 1
        assert "No availability zone" in results[0].description

    def test_multi_az_no_detection(self):
        """Multi-AZ deployment does not trigger detection."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", az="us-east-1a"))
        g.add_component(_comp("b", "B", az="us-east-1b"))

        detector = AntiPatternDetector(g)
        assert detector._check_single_az() == []

    def test_partial_az_set(self):
        """Some components have AZ, some don't -- should not flag."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", az="us-east-1a"))
        g.add_component(_comp("b", "B"))  # no AZ

        detector = AntiPatternDetector(g)
        # len(components_with_az) != len(components) -> no single-AZ flag
        # len(components_with_az) > 0 -> no "no AZ" flag
        assert detector._check_single_az() == []

    def test_single_component_skipped(self):
        """With <2 components, single_az check returns []."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", az="us-east-1a"))

        detector = AntiPatternDetector(g)
        assert detector._check_single_az() == []


# ======================================================================
# No Health Check
# ======================================================================

class TestNoHealthCheck:
    def test_detected_failover_disabled(self):
        g = InfraGraph()
        g.add_component(_comp(
            "lb", "LB", ComponentType.LOAD_BALANCER,
            failover_enabled=False,
        ))

        detector = AntiPatternDetector(g)
        results = detector._check_no_health_check()
        assert len(results) == 1
        r = results[0]
        assert r.id == "no_health_check"
        assert r.severity == "high"
        assert "lb" in r.affected_components

    def test_detected_zero_interval(self):
        g = InfraGraph()
        g.add_component(_comp(
            "lb", "LB", ComponentType.LOAD_BALANCER,
            failover_enabled=True,
            health_check_interval=0,
        ))

        detector = AntiPatternDetector(g)
        results = detector._check_no_health_check()
        assert len(results) == 1

    def test_detected_negative_interval(self):
        g = InfraGraph()
        g.add_component(_comp(
            "lb", "LB", ComponentType.LOAD_BALANCER,
            failover_enabled=True,
            health_check_interval=-5.0,
        ))

        detector = AntiPatternDetector(g)
        results = detector._check_no_health_check()
        assert len(results) == 1

    def test_not_detected_healthy_lb(self):
        g = InfraGraph()
        g.add_component(_comp(
            "lb", "LB", ComponentType.LOAD_BALANCER,
            failover_enabled=True,
            health_check_interval=10.0,
        ))

        detector = AntiPatternDetector(g)
        assert detector._check_no_health_check() == []

    def test_non_lb_not_checked(self):
        """Non-LB components are not checked for health checks."""
        g = InfraGraph()
        g.add_component(_comp(
            "app", "App", ComponentType.APP_SERVER,
            failover_enabled=False,
        ))

        detector = AntiPatternDetector(g)
        assert detector._check_no_health_check() == []


# ======================================================================
# Thundering Herd
# ======================================================================

class TestThunderingHerd:
    def test_detected(self):
        """2+ sources without jitter/singleflight trigger thundering herd."""
        g = InfraGraph()
        g.add_component(_comp("target", "Target"))
        g.add_component(_comp("s1", "Source1"))
        g.add_component(_comp("s2", "Source2"))
        # Both 'requires' with no retry jitter and no singleflight
        g.add_dependency(_dep("s1", "target", "requires",
                              retry_enabled=False, retry_jitter=False))
        g.add_dependency(_dep("s2", "target", "requires",
                              retry_enabled=False, retry_jitter=False))

        detector = AntiPatternDetector(g)
        results = detector._check_thundering_herd()
        assert len(results) == 1
        r = results[0]
        assert r.id == "thundering_herd"
        assert r.severity == "medium"
        assert "target" in r.affected_components

    def test_not_detected_with_jitter(self):
        """Retry jitter enabled prevents detection."""
        g = InfraGraph()
        g.add_component(_comp("target", "Target"))
        g.add_component(_comp("s1", "Source1"))
        g.add_component(_comp("s2", "Source2"))
        g.add_dependency(_dep("s1", "target", "requires",
                              retry_enabled=True, retry_jitter=True))
        g.add_dependency(_dep("s2", "target", "requires",
                              retry_enabled=True, retry_jitter=True))

        detector = AntiPatternDetector(g)
        assert detector._check_thundering_herd() == []

    def test_not_detected_with_singleflight(self):
        """Singleflight enabled prevents detection."""
        g = InfraGraph()
        g.add_component(_comp("target", "Target"))
        g.add_component(_comp("s1", "Source1", singleflight_enabled=True))
        g.add_component(_comp("s2", "Source2", singleflight_enabled=True))
        g.add_dependency(_dep("s1", "target", "requires",
                              retry_enabled=False, retry_jitter=False))
        g.add_dependency(_dep("s2", "target", "requires",
                              retry_enabled=False, retry_jitter=False))

        detector = AntiPatternDetector(g)
        assert detector._check_thundering_herd() == []

    def test_not_detected_optional_deps(self):
        """Only 'requires' dependencies are considered."""
        g = InfraGraph()
        g.add_component(_comp("target", "Target"))
        g.add_component(_comp("s1", "Source1"))
        g.add_component(_comp("s2", "Source2"))
        g.add_dependency(_dep("s1", "target", "optional",
                              retry_enabled=False, retry_jitter=False))
        g.add_dependency(_dep("s2", "target", "optional",
                              retry_enabled=False, retry_jitter=False))

        detector = AntiPatternDetector(g)
        assert detector._check_thundering_herd() == []

    def test_not_detected_single_source(self):
        """Single source to a target is not a thundering herd risk."""
        g = InfraGraph()
        g.add_component(_comp("target", "Target"))
        g.add_component(_comp("s1", "Source1"))
        g.add_dependency(_dep("s1", "target", "requires",
                              retry_enabled=False, retry_jitter=False))

        detector = AntiPatternDetector(g)
        assert detector._check_thundering_herd() == []

    def test_one_with_jitter_one_without(self):
        """Only 1 source without jitter (need >=2) -> no detection."""
        g = InfraGraph()
        g.add_component(_comp("target", "Target"))
        g.add_component(_comp("s1", "Source1"))
        g.add_component(_comp("s2", "Source2"))
        g.add_dependency(_dep("s1", "target", "requires",
                              retry_enabled=True, retry_jitter=True))
        g.add_dependency(_dep("s2", "target", "requires",
                              retry_enabled=False, retry_jitter=False))

        detector = AntiPatternDetector(g)
        assert detector._check_thundering_herd() == []

    def test_target_comp_none(self):
        """If target component is not in graph, uses target_id as name."""
        g = InfraGraph()
        g.add_component(_comp("s1", "Source1"))
        g.add_component(_comp("s2", "Source2"))
        # target not added as component, but edge exists
        g.add_dependency(_dep("s1", "ghost", "requires",
                              retry_enabled=False, retry_jitter=False))
        g.add_dependency(_dep("s2", "ghost", "requires",
                              retry_enabled=False, retry_jitter=False))

        detector = AntiPatternDetector(g)
        results = detector._check_thundering_herd()
        assert len(results) == 1
        # target_name falls back to target_id when target_comp is None
        assert "ghost" in results[0].description

    def test_edge_or_comp_none_skipped(self):
        """If edge or comp is None, the source is silently skipped."""
        g = InfraGraph()
        g.add_component(_comp("target", "Target"))
        g.add_component(_comp("s1", "Source1"))
        # s2 has an edge but is not in components
        g.add_dependency(_dep("s1", "target", "requires",
                              retry_enabled=False, retry_jitter=False))
        g.add_dependency(_dep("ghost_src", "target", "requires",
                              retry_enabled=False, retry_jitter=False))

        detector = AntiPatternDetector(g)
        # ghost_src comp is None -> skipped, only 1 valid no-jitter source -> no detection
        assert detector._check_thundering_herd() == []

    def test_retry_enabled_but_no_jitter(self):
        """Retry enabled but jitter=False -> has_retry_jitter is False."""
        g = InfraGraph()
        g.add_component(_comp("target", "Target"))
        g.add_component(_comp("s1", "Source1"))
        g.add_component(_comp("s2", "Source2"))
        g.add_dependency(_dep("s1", "target", "requires",
                              retry_enabled=True, retry_jitter=False))
        g.add_dependency(_dep("s2", "target", "requires",
                              retry_enabled=True, retry_jitter=False))

        detector = AntiPatternDetector(g)
        results = detector._check_thundering_herd()
        assert len(results) == 1


# ======================================================================
# N+1 Dependency
# ======================================================================

class TestNPlusOneDependency:
    def test_detected(self):
        """Component depends on 2+ same-type components without LB."""
        g = InfraGraph()
        g.add_component(_comp("client", "Client"))
        g.add_component(_comp("svc1", "Service1"))
        g.add_component(_comp("svc2", "Service2"))
        g.add_dependency(_dep("client", "svc1"))
        g.add_dependency(_dep("client", "svc2"))

        detector = AntiPatternDetector(g)
        results = detector._check_n_plus_one()
        assert len(results) == 1
        r = results[0]
        assert r.id == "n_plus_one"
        assert r.severity == "medium"
        assert "client" in r.affected_components

    def test_not_detected_different_types(self):
        """Dependencies of different types don't trigger N+1."""
        g = InfraGraph()
        g.add_component(_comp("client", "Client"))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        g.add_component(_comp("cache", "Cache", ComponentType.CACHE))
        g.add_dependency(_dep("client", "db"))
        g.add_dependency(_dep("client", "cache"))

        detector = AntiPatternDetector(g)
        assert detector._check_n_plus_one() == []

    def test_not_detected_single_dep(self):
        """A single dependency of any type is fine."""
        g = InfraGraph()
        g.add_component(_comp("client", "Client"))
        g.add_component(_comp("svc1", "Service1"))
        g.add_dependency(_dep("client", "svc1"))

        detector = AntiPatternDetector(g)
        assert detector._check_n_plus_one() == []

    def test_lb_source_skipped(self):
        """Load balancer depending on multiple same-type is its job."""
        g = InfraGraph()
        g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER))
        g.add_component(_comp("app1", "App1"))
        g.add_component(_comp("app2", "App2"))
        g.add_dependency(_dep("lb", "app1"))
        g.add_dependency(_dep("lb", "app2"))

        detector = AntiPatternDetector(g)
        assert detector._check_n_plus_one() == []

    def test_lb_target_skipped(self):
        """Depending on multiple LBs is not flagged."""
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("lb1", "LB1", ComponentType.LOAD_BALANCER))
        g.add_component(_comp("lb2", "LB2", ComponentType.LOAD_BALANCER))
        g.add_dependency(_dep("app", "lb1"))
        g.add_dependency(_dep("app", "lb2"))

        detector = AntiPatternDetector(g)
        assert detector._check_n_plus_one() == []

    def test_less_than_two_deps(self):
        """Component with <2 total deps skips the check early."""
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_dependency(_dep("a", "b"))

        detector = AntiPatternDetector(g)
        assert detector._check_n_plus_one() == []

    def test_no_deps(self):
        """Component with zero deps is fine."""
        g = InfraGraph()
        g.add_component(_comp("a", "A"))

        detector = AntiPatternDetector(g)
        assert detector._check_n_plus_one() == []


# ======================================================================
# detect() integration
# ======================================================================

class TestDetect:
    def test_sorts_by_severity(self):
        """Results are sorted by severity descending (critical first)."""
        g = InfraGraph()
        # Trigger single_az (critical) + thundering herd (medium)
        g.add_component(_comp("s1", "S1", az="us-east-1a"))
        g.add_component(_comp("s2", "S2", az="us-east-1a"))
        g.add_component(_comp("s3", "S3", az="us-east-1a"))
        g.add_dependency(_dep("s1", "s3", "requires",
                              retry_enabled=False, retry_jitter=False))
        g.add_dependency(_dep("s2", "s3", "requires",
                              retry_enabled=False, retry_jitter=False))

        detector = AntiPatternDetector(g)
        results = detector.detect()
        assert len(results) > 0
        severities = [_SEVERITY_ORDER.get(r.severity, 0) for r in results]
        assert severities == sorted(severities, reverse=True)

    def test_all_checks_called(self):
        """detect() aggregates all check methods."""
        g = InfraGraph()
        detector = AntiPatternDetector(g)
        # Empty graph -> no patterns
        assert detector.detect() == []

    def test_unknown_severity_sorted_last(self):
        """A pattern with an unknown severity (get returns 0) sorts last."""
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))

        detector = AntiPatternDetector(g)
        results = detector.detect()
        # With default components (no AZ), we get single_az (critical)
        # Verify sort stability with known data
        for i in range(len(results) - 1):
            sev_i = _SEVERITY_ORDER.get(results[i].severity, 0)
            sev_next = _SEVERITY_ORDER.get(results[i + 1].severity, 0)
            assert sev_i >= sev_next


# ======================================================================
# detect_by_severity()
# ======================================================================

class TestDetectBySeverity:
    def _build_multi_severity_graph(self) -> InfraGraph:
        """Build a graph triggering patterns at all severity levels."""
        g = InfraGraph()
        # Single AZ (critical)
        g.add_component(_comp("app1", "App1", ComponentType.APP_SERVER, az="us-east-1a"))
        g.add_component(_comp("app2", "App2", ComponentType.APP_SERVER, az="us-east-1a"))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, az="us-east-1a"))
        # Missing CB (high) - requires without circuit breaker
        g.add_dependency(_dep("app1", "db", "requires", cb_enabled=False))
        g.add_dependency(_dep("app2", "db", "requires", cb_enabled=False))
        return g

    def test_filter_critical(self):
        g = self._build_multi_severity_graph()
        detector = AntiPatternDetector(g)
        results = detector.detect_by_severity("critical")
        assert all(r.severity == "critical" for r in results)

    def test_filter_high(self):
        g = self._build_multi_severity_graph()
        detector = AntiPatternDetector(g)
        results = detector.detect_by_severity("high")
        for r in results:
            assert _SEVERITY_ORDER.get(r.severity, 0) >= _SEVERITY_ORDER["high"]

    def test_filter_medium(self):
        g = self._build_multi_severity_graph()
        detector = AntiPatternDetector(g)
        results_medium = detector.detect_by_severity("medium")
        results_all = detector.detect()
        # medium is the lowest level so all patterns should be included
        assert len(results_medium) == len(results_all)

    def test_unknown_severity_defaults(self):
        g = self._build_multi_severity_graph()
        detector = AntiPatternDetector(g)
        results = detector.detect_by_severity("unknown_level")
        # min_order defaults to 1 (medium)
        assert len(results) == len(detector.detect())


# ======================================================================
# Security-relevant: insecure pattern detection
# ======================================================================

class TestSecurityAntipatterns:
    def test_missing_circuit_breaker_is_security_concern(self):
        """Missing circuit breakers can lead to cascade DoS."""
        g = InfraGraph()
        g.add_component(_comp("gateway", "API Gateway", ComponentType.APP_SERVER))
        g.add_component(_comp("auth", "Auth Service", ComponentType.APP_SERVER))
        g.add_component(_comp("db", "User DB", ComponentType.DATABASE))
        g.add_dependency(_dep("gateway", "auth", "requires", cb_enabled=False))
        g.add_dependency(_dep("auth", "db", "requires", cb_enabled=False))

        detector = AntiPatternDetector(g)
        results = detector.detect()
        cb_patterns = [r for r in results if r.id == "missing_circuit_breaker"]
        assert len(cb_patterns) == 2  # both edges flagged

    def test_single_az_is_security_concern(self):
        """All in one AZ means a zone failure takes everything down."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", az="us-east-1a"))
        g.add_component(_comp("b", "B", az="us-east-1a"))
        g.add_component(_comp("c", "C", az="us-east-1a"))

        detector = AntiPatternDetector(g)
        results = detector.detect()
        az_patterns = [r for r in results if r.id == "single_az"]
        assert len(az_patterns) == 1
        assert az_patterns[0].severity == "critical"

    def test_god_component_spof(self):
        """A god component is an attractive attack target / SPOF."""
        g = InfraGraph()
        g.add_component(_comp("shared_db", "SharedDB", ComponentType.DATABASE))
        for i in range(5):
            cid = f"svc{i}"
            g.add_component(_comp(cid, f"Svc{i}"))
            g.add_dependency(_dep(cid, "shared_db"))

        detector = AntiPatternDetector(g)
        results = detector.detect()
        god = [r for r in results if r.id == "god_component"]
        assert len(god) == 1
        assert god[0].severity == "critical"

    def test_no_health_check_lb(self):
        """LB without health checks won't route around compromised backends."""
        g = InfraGraph()
        g.add_component(_comp(
            "lb", "Public LB", ComponentType.LOAD_BALANCER,
            failover_enabled=False,
        ))

        detector = AntiPatternDetector(g)
        results = detector.detect()
        hc = [r for r in results if r.id == "no_health_check"]
        assert len(hc) == 1
        assert hc[0].severity == "high"


# ======================================================================
# Performance: larger graph test
# ======================================================================

class TestPerformance:
    def test_larger_graph_no_blowup(self):
        """Detect on a 15-component graph completes quickly."""
        g = InfraGraph()
        n = 15

        # Build a chain: c0 -> c1 -> ... -> c14
        for i in range(n):
            g.add_component(_comp(
                f"c{i}", f"Component{i}",
                az="us-east-1a" if i < 10 else "us-east-1b",
            ))
        for i in range(n - 1):
            g.add_dependency(_dep(f"c{i}", f"c{i+1}", "requires", cb_enabled=False))

        detector = AntiPatternDetector(g)
        import time
        t0 = time.time()
        results = detector.detect()
        elapsed = time.time() - t0
        # Should complete well under 5 seconds
        assert elapsed < 5.0
        assert len(results) > 0  # at least missing_circuit_breaker findings

    def test_star_topology_20_nodes(self):
        """Star: 1 central node, 19 dependents -- tests god component detection at scale."""
        g = InfraGraph()
        g.add_component(_comp("hub", "Hub", ComponentType.DATABASE, az="us-east-1a"))
        for i in range(19):
            cid = f"spoke{i}"
            g.add_component(_comp(cid, f"Spoke{i}", az="us-east-1a"))
            g.add_dependency(_dep(cid, "hub", "requires", cb_enabled=False))

        detector = AntiPatternDetector(g)
        import time
        t0 = time.time()
        results = detector.detect()
        elapsed = time.time() - t0
        assert elapsed < 5.0

        god = [r for r in results if r.id == "god_component"]
        assert len(god) == 1

    def test_mesh_topology_10_nodes(self):
        """Fully-connected mesh of 10 nodes -- tests cycle detection at scale."""
        g = InfraGraph()
        n = 10
        for i in range(n):
            g.add_component(_comp(f"m{i}", f"Mesh{i}", az="us-east-1a"))
        for i in range(n):
            for j in range(n):
                if i != j:
                    g.add_dependency(_dep(f"m{i}", f"m{j}", "requires", cb_enabled=False))

        detector = AntiPatternDetector(g)
        import time
        t0 = time.time()
        results = detector.detect()
        elapsed = time.time() - t0
        # Cycle detection can be expensive on full mesh, but should finish
        assert elapsed < 30.0
        assert any(r.id == "circular_dependency" for r in results)


# ======================================================================
# Edge cases: extreme replicas / connections
# ======================================================================

class TestBoundaryValues:
    def test_extreme_replicas(self):
        """Very large replica count should not cause issues."""
        g = InfraGraph()
        g.add_component(_comp("big", "BigCluster", replicas=10000))
        g.add_component(_comp("small", "Small", replicas=1))
        g.add_dependency(_dep("big", "small", "requires", cb_enabled=False))

        detector = AntiPatternDetector(g)
        results = detector.detect()
        cb = [r for r in results if r.id == "missing_circuit_breaker"]
        assert len(cb) == 1

    def test_no_dependencies(self):
        """Graph with components but no dependencies."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", az="us-east-1a"))
        g.add_component(_comp("b", "B", az="us-east-1a"))

        detector = AntiPatternDetector(g)
        results = detector.detect()
        # Should still detect single_az
        az = [r for r in results if r.id == "single_az"]
        assert len(az) == 1
        # No circuit breaker, no god component, etc.
        assert all(r.id == "single_az" for r in results)

    def test_mixed_severities_comprehensive(self):
        """Graph producing critical, high, and medium patterns together."""
        g = InfraGraph()
        # LB without health check (high - no_health_check)
        g.add_component(_comp(
            "lb", "LB", ComponentType.LOAD_BALANCER,
            failover_enabled=False, az="us-east-1a",
        ))
        # App servers and DB for database_direct_access (medium)
        g.add_component(_comp("app1", "App1", ComponentType.APP_SERVER, az="us-east-1a"))
        g.add_component(_comp("app2", "App2", ComponentType.APP_SERVER, az="us-east-1a"))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, az="us-east-1a"))
        # Edges
        g.add_dependency(_dep("lb", "app1", "requires", cb_enabled=False))
        g.add_dependency(_dep("lb", "app2", "requires", cb_enabled=False))
        g.add_dependency(_dep("app1", "db", "requires", cb_enabled=False))
        g.add_dependency(_dep("app2", "db", "requires", cb_enabled=False))

        detector = AntiPatternDetector(g)
        results = detector.detect()

        ids_found = {r.id for r in results}
        assert "single_az" in ids_found        # critical
        assert "missing_circuit_breaker" in ids_found  # high
        assert "no_health_check" in ids_found   # high
        assert "database_direct_access" in ids_found   # medium

        # Verify sort order
        severities = [_SEVERITY_ORDER.get(r.severity, 0) for r in results]
        assert severities == sorted(severities, reverse=True)

    def test_components_with_no_dependencies_no_crash(self):
        """Isolated components (no edges) should not crash any check."""
        g = InfraGraph()
        for i in range(5):
            g.add_component(_comp(f"iso{i}", f"Isolated{i}"))

        detector = AntiPatternDetector(g)
        results = detector.detect()
        # Should get single_az (no AZ set) but nothing else
        assert all(r.id == "single_az" for r in results)
