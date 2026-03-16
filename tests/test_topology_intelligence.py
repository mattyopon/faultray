"""Tests for TopologyIntelligenceEngine — 130+ tests for 100% coverage."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.topology_intelligence import (
    DependencySource,
    HiddenRiskScenario,
    ImplicitDependency,
    InferenceConfidence,
    TopologyAnomaly,
    TopologyIntelligenceEngine,
    TopologyIntelligenceReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
    tags: list[str] | None = None,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True, promotion_time_seconds=10)
    if tags:
        c.tags = tags
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ===================================================================
# Section 1: Enum tests
# ===================================================================

class TestDependencySource:
    def test_declared(self):
        assert DependencySource.DECLARED == "declared"

    def test_inferred_shared_infra(self):
        assert DependencySource.INFERRED_SHARED_INFRA == "inferred_shared_infra"

    def test_inferred_pattern(self):
        assert DependencySource.INFERRED_PATTERN == "inferred_pattern"

    def test_inferred_proximity(self):
        assert DependencySource.INFERRED_PROXIMITY == "inferred_proximity"

    def test_inferred_common_dependency(self):
        assert DependencySource.INFERRED_COMMON_DEPENDENCY == "inferred_common_dependency"

    def test_all_values(self):
        assert len(DependencySource) == 5


class TestInferenceConfidence:
    def test_high(self):
        assert InferenceConfidence.HIGH == "high"

    def test_medium(self):
        assert InferenceConfidence.MEDIUM == "medium"

    def test_low(self):
        assert InferenceConfidence.LOW == "low"

    def test_all_values(self):
        assert len(InferenceConfidence) == 3


# ===================================================================
# Section 2: Data model tests
# ===================================================================

class TestImplicitDependency:
    def test_basic_creation(self):
        dep = ImplicitDependency(
            source_component="a",
            target_component="b",
            dependency_type="shared_dns",
            source=DependencySource.INFERRED_SHARED_INFRA,
            confidence=InferenceConfidence.HIGH,
            reasoning="test reasoning",
        )
        assert dep.source_component == "a"
        assert dep.target_component == "b"
        assert dep.dependency_type == "shared_dns"
        assert dep.source == DependencySource.INFERRED_SHARED_INFRA
        assert dep.confidence == InferenceConfidence.HIGH
        assert dep.reasoning == "test reasoning"

    def test_shared_auth_type(self):
        dep = ImplicitDependency(
            source_component="x",
            target_component="y",
            dependency_type="shared_auth",
            source=DependencySource.INFERRED_PATTERN,
            confidence=InferenceConfidence.MEDIUM,
            reasoning="auth link",
        )
        assert dep.dependency_type == "shared_auth"

    def test_ntp_sync_type(self):
        dep = ImplicitDependency(
            source_component="x",
            target_component="y",
            dependency_type="ntp_sync",
            source=DependencySource.INFERRED_COMMON_DEPENDENCY,
            confidence=InferenceConfidence.LOW,
            reasoning="ntp",
        )
        assert dep.dependency_type == "ntp_sync"


class TestTopologyAnomaly:
    def test_defaults(self):
        a = TopologyAnomaly(anomaly_type="missing_lb")
        assert a.anomaly_type == "missing_lb"
        assert a.affected_components == []
        assert a.severity == 0.5
        assert a.description == ""
        assert a.recommendation == ""

    def test_full_creation(self):
        a = TopologyAnomaly(
            anomaly_type="single_path",
            affected_components=["a", "b"],
            severity=0.9,
            description="desc",
            recommendation="rec",
        )
        assert a.severity == 0.9
        assert len(a.affected_components) == 2


class TestHiddenRiskScenario:
    def test_defaults(self):
        s = HiddenRiskScenario()
        assert s.scenario_id == ""
        assert s.name == ""
        assert s.description == ""
        assert s.target_dependency is None
        assert s.impact_components == []
        assert s.estimated_blast_radius == 0.0
        assert s.recommended_test == ""

    def test_full_creation(self):
        dep = ImplicitDependency(
            source_component="a",
            target_component="b",
            dependency_type="shared_dns",
            source=DependencySource.INFERRED_SHARED_INFRA,
            confidence=InferenceConfidence.HIGH,
            reasoning="r",
        )
        s = HiddenRiskScenario(
            scenario_id="test-1",
            name="Test Scenario",
            description="desc",
            target_dependency=dep,
            impact_components=["a", "b"],
            estimated_blast_radius=0.5,
            recommended_test="do something",
        )
        assert s.scenario_id == "test-1"
        assert s.target_dependency is not None
        assert s.estimated_blast_radius == 0.5


class TestTopologyIntelligenceReport:
    def test_defaults(self):
        r = TopologyIntelligenceReport()
        assert r.total_components == 0
        assert r.declared_dependencies == 0
        assert r.implicit_dependencies_found == 0
        assert r.anomalies == []
        assert r.hidden_risks == []
        assert r.topology_health_score == 100.0
        assert r.recommendations == []

    def test_custom_values(self):
        r = TopologyIntelligenceReport(
            total_components=5,
            declared_dependencies=3,
            implicit_dependencies_found=2,
            topology_health_score=85.0,
            recommendations=["fix it"],
        )
        assert r.total_components == 5
        assert r.declared_dependencies == 3
        assert len(r.recommendations) == 1


# ===================================================================
# Section 3: Engine __init__ and helpers
# ===================================================================

class TestEngineInit:
    def test_create_with_empty_graph(self):
        g = InfraGraph()
        engine = TopologyIntelligenceEngine(g)
        assert engine._graph is g

    def test_create_with_populated_graph(self):
        g = _graph(_comp("a", "A"))
        engine = TopologyIntelligenceEngine(g)
        assert len(engine._graph.components) == 1

    def test_components_by_type(self):
        g = _graph(
            _comp("a", "A", ComponentType.APP_SERVER),
            _comp("b", "B", ComponentType.DATABASE),
            _comp("c", "C", ComponentType.APP_SERVER),
        )
        engine = TopologyIntelligenceEngine(g)
        apps = engine._components_by_type(ComponentType.APP_SERVER)
        assert len(apps) == 2

    def test_components_by_type_empty(self):
        g = _graph(_comp("a", "A", ComponentType.APP_SERVER))
        engine = TopologyIntelligenceEngine(g)
        assert engine._components_by_type(ComponentType.DNS) == []

    def test_has_declared_dep_true(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        engine = TopologyIntelligenceEngine(g)
        assert engine._has_declared_dep("a", "b") is True

    def test_has_declared_dep_false(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        engine = TopologyIntelligenceEngine(g)
        assert engine._has_declared_dep("a", "b") is False

    def test_all_component_ids(self):
        g = _graph(_comp("x", "X"), _comp("y", "Y"))
        engine = TopologyIntelligenceEngine(g)
        ids = engine._all_component_ids()
        assert set(ids) == {"x", "y"}


# ===================================================================
# Section 4: discover_implicit_dependencies
# ===================================================================

class TestDiscoverImplicitDeps:
    """Rule-by-rule tests for implicit dependency discovery."""

    # -- Rule 1: DNS dependency ------------------------------------------

    def test_rule1_all_depend_on_dns(self):
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("app1", "App1", ComponentType.APP_SERVER),
            _comp("app2", "App2", ComponentType.APP_SERVER),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        dns_deps = [d for d in deps if d.dependency_type == "shared_dns"]
        assert len(dns_deps) >= 2
        sources = {d.source_component for d in dns_deps}
        assert "app1" in sources
        assert "app2" in sources

    def test_rule1_dns_does_not_depend_on_itself(self):
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("app1", "App1"),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        dns_self = [d for d in deps if d.source_component == "dns1" and d.target_component == "dns1"]
        assert len(dns_self) == 0

    def test_rule1_skip_declared_dns_dep(self):
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("app1", "App1"),
        )
        g.add_dependency(Dependency(source_id="app1", target_id="dns1"))
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        dns_deps = [d for d in deps if d.source_component == "app1" and d.target_component == "dns1"]
        assert len(dns_deps) == 0

    def test_rule1_no_dns_no_deps(self):
        g = _graph(_comp("app1", "App1"), _comp("app2", "App2"))
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        dns_deps = [d for d in deps if d.dependency_type == "shared_dns"]
        assert len(dns_deps) == 0

    def test_rule1_confidence_high(self):
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("app1", "App1"),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        dns_deps = [d for d in deps if d.dependency_type == "shared_dns"]
        assert all(d.confidence == InferenceConfidence.HIGH for d in dns_deps)

    def test_rule1_source_is_inferred_shared_infra(self):
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("app1", "App1"),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        dns_deps = [d for d in deps if d.dependency_type == "shared_dns"]
        assert all(d.source == DependencySource.INFERRED_SHARED_INFRA for d in dns_deps)

    def test_rule1_multiple_dns_nodes(self):
        g = _graph(
            _comp("dns1", "DNS1", ComponentType.DNS),
            _comp("dns2", "DNS2", ComponentType.DNS),
            _comp("app1", "App1"),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        dns_deps = [d for d in deps if d.source_component == "app1" and d.dependency_type == "shared_dns"]
        # app1 depends on both dns1 and dns2
        assert len(dns_deps) == 2

    def test_rule1_excludes_external_api(self):
        """Rule 1 skips external APIs (handled by Rule 4)."""
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("ext1", "Ext", ComponentType.EXTERNAL_API),
            _comp("app1", "App1"),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        # Rule 1 should NOT produce ext1->dns1; Rule 4 should
        rule1_ext_deps = [d for d in deps if d.source_component == "ext1" and d.reasoning.startswith("Component")]
        assert len(rule1_ext_deps) == 0
        # But ext1 should still get dns dep from Rule 4
        ext_dns = [d for d in deps if d.source_component == "ext1" and d.dependency_type == "shared_dns"]
        assert len(ext_dns) == 1

    # -- Rule 2: Web servers → load balancers ----------------------------

    def test_rule2_web_server_depends_on_lb(self):
        g = _graph(
            _comp("lb1", "LB", ComponentType.LOAD_BALANCER),
            _comp("ws1", "WS", ComponentType.WEB_SERVER),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        lb_deps = [d for d in deps if d.dependency_type == "common_lb"]
        assert len(lb_deps) == 1
        assert lb_deps[0].source_component == "ws1"
        assert lb_deps[0].target_component == "lb1"

    def test_rule2_no_web_servers(self):
        g = _graph(
            _comp("lb1", "LB", ComponentType.LOAD_BALANCER),
            _comp("app1", "App1", ComponentType.APP_SERVER),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        lb_deps = [d for d in deps if d.dependency_type == "common_lb"]
        assert len(lb_deps) == 0

    def test_rule2_skip_declared(self):
        g = _graph(
            _comp("lb1", "LB", ComponentType.LOAD_BALANCER),
            _comp("ws1", "WS", ComponentType.WEB_SERVER),
        )
        g.add_dependency(Dependency(source_id="ws1", target_id="lb1"))
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        lb_deps = [d for d in deps if d.dependency_type == "common_lb"]
        assert len(lb_deps) == 0

    def test_rule2_confidence_high(self):
        g = _graph(
            _comp("lb1", "LB", ComponentType.LOAD_BALANCER),
            _comp("ws1", "WS", ComponentType.WEB_SERVER),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        lb_deps = [d for d in deps if d.dependency_type == "common_lb"]
        assert lb_deps[0].confidence == InferenceConfidence.HIGH

    def test_rule2_source_is_inferred_pattern(self):
        g = _graph(
            _comp("lb1", "LB", ComponentType.LOAD_BALANCER),
            _comp("ws1", "WS", ComponentType.WEB_SERVER),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        lb_deps = [d for d in deps if d.dependency_type == "common_lb"]
        assert lb_deps[0].source == DependencySource.INFERRED_PATTERN

    def test_rule2_multiple_ws_multiple_lb(self):
        g = _graph(
            _comp("lb1", "LB1", ComponentType.LOAD_BALANCER),
            _comp("lb2", "LB2", ComponentType.LOAD_BALANCER),
            _comp("ws1", "WS1", ComponentType.WEB_SERVER),
            _comp("ws2", "WS2", ComponentType.WEB_SERVER),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        lb_deps = [d for d in deps if d.dependency_type == "common_lb"]
        # 2 WS x 2 LB = 4
        assert len(lb_deps) == 4

    # -- Rule 3: Same-region DB/cache share network ----------------------

    def test_rule3_db_and_cache_same_region(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        cache = _comp("cache1", "Cache", ComponentType.CACHE)
        g = _graph(db, cache)
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        net_deps = [d for d in deps if d.dependency_type == "shared_network"]
        assert len(net_deps) == 1

    def test_rule3_different_region(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        db.region.region = "us-east-1"
        cache = _comp("cache1", "Cache", ComponentType.CACHE)
        cache.region.region = "eu-west-1"
        g = _graph(db, cache)
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        net_deps = [d for d in deps if d.dependency_type == "shared_network"]
        assert len(net_deps) == 0

    def test_rule3_two_dbs_same_region(self):
        db1 = _comp("db1", "DB1", ComponentType.DATABASE)
        db1.region.region = "us-east-1"
        db2 = _comp("db2", "DB2", ComponentType.DATABASE)
        db2.region.region = "us-east-1"
        g = _graph(db1, db2)
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        net_deps = [d for d in deps if d.dependency_type == "shared_network"]
        assert len(net_deps) == 1

    def test_rule3_skip_declared(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        cache = _comp("cache1", "Cache", ComponentType.CACHE)
        g = _graph(db, cache)
        g.add_dependency(Dependency(source_id="db1", target_id="cache1"))
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        net_deps = [d for d in deps if d.dependency_type == "shared_network"]
        assert len(net_deps) == 0

    def test_rule3_confidence_medium(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        cache = _comp("cache1", "Cache", ComponentType.CACHE)
        g = _graph(db, cache)
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        net_deps = [d for d in deps if d.dependency_type == "shared_network"]
        assert net_deps[0].confidence == InferenceConfidence.MEDIUM

    def test_rule3_source_proximity(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        cache = _comp("cache1", "Cache", ComponentType.CACHE)
        g = _graph(db, cache)
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        net_deps = [d for d in deps if d.dependency_type == "shared_network"]
        assert net_deps[0].source == DependencySource.INFERRED_PROXIMITY

    def test_rule3_default_region_grouped(self):
        """Components with empty region string share default region."""
        db = _comp("db1", "DB", ComponentType.DATABASE)
        cache = _comp("cache1", "Cache", ComponentType.CACHE)
        g = _graph(db, cache)
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        net_deps = [d for d in deps if d.dependency_type == "shared_network"]
        assert len(net_deps) == 1

    def test_rule3_three_in_same_region(self):
        db1 = _comp("db1", "DB1", ComponentType.DATABASE)
        db2 = _comp("db2", "DB2", ComponentType.DATABASE)
        cache = _comp("cache1", "Cache", ComponentType.CACHE)
        g = _graph(db1, db2, cache)
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        net_deps = [d for d in deps if d.dependency_type == "shared_network"]
        # pairs: (db1,db2), (db1,cache), (db2,cache)
        assert len(net_deps) == 3

    # -- Rule 4: External API implicit DNS --------------------------------

    def test_rule4_external_api_dns(self):
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("ext1", "Ext", ComponentType.EXTERNAL_API),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        # ext1 already gets dns dep from Rule 1, Rule 4 should not duplicate
        ext_dns = [d for d in deps if d.source_component == "ext1" and d.dependency_type == "shared_dns"]
        assert len(ext_dns) == 1

    def test_rule4_no_dns_no_extra_dep(self):
        g = _graph(_comp("ext1", "Ext", ComponentType.EXTERNAL_API))
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        dns_deps = [d for d in deps if d.dependency_type == "shared_dns"]
        assert len(dns_deps) == 0

    def test_rule4_external_api_declared_dns(self):
        """If ext API already has declared dep on DNS, no implicit added."""
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("ext1", "Ext", ComponentType.EXTERNAL_API),
        )
        g.add_dependency(Dependency(source_id="ext1", target_id="dns1"))
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        ext_dns = [d for d in deps if d.source_component == "ext1" and d.dependency_type == "shared_dns"]
        assert len(ext_dns) == 0

    # -- Rule 5: Same tags share infra ------------------------------------

    def test_rule5_same_tags_no_declared_deps(self):
        g = _graph(
            _comp("a", "A", tags=["team-alpha"]),
            _comp("b", "B", tags=["team-alpha"]),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        tag_deps = [d for d in deps if d.source == DependencySource.INFERRED_COMMON_DEPENDENCY]
        assert len(tag_deps) == 1

    def test_rule5_different_tags(self):
        g = _graph(
            _comp("a", "A", tags=["team-alpha"]),
            _comp("b", "B", tags=["team-beta"]),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        tag_deps = [d for d in deps if d.source == DependencySource.INFERRED_COMMON_DEPENDENCY]
        assert len(tag_deps) == 0

    def test_rule5_with_declared_deps_excluded(self):
        a = _comp("a", "A", tags=["team-alpha"])
        b = _comp("b", "B", tags=["team-alpha"])
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        tag_deps = [d for d in deps if d.source == DependencySource.INFERRED_COMMON_DEPENDENCY]
        # a has declared dep, so rule 5 does not apply to a; b is still orphaned
        # but since a has deps, it won't be in the orphan set for rule 5
        assert len(tag_deps) == 0

    def test_rule5_confidence_low(self):
        g = _graph(
            _comp("a", "A", tags=["env:prod"]),
            _comp("b", "B", tags=["env:prod"]),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        tag_deps = [d for d in deps if d.source == DependencySource.INFERRED_COMMON_DEPENDENCY]
        assert all(d.confidence == InferenceConfidence.LOW for d in tag_deps)

    def test_rule5_three_with_same_tag(self):
        g = _graph(
            _comp("a", "A", tags=["env:prod"]),
            _comp("b", "B", tags=["env:prod"]),
            _comp("c", "C", tags=["env:prod"]),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        tag_deps = [d for d in deps if d.source == DependencySource.INFERRED_COMMON_DEPENDENCY]
        # 3 choose 2 = 3 pairs
        assert len(tag_deps) == 3

    def test_rule5_no_tags(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        tag_deps = [d for d in deps if d.source == DependencySource.INFERRED_COMMON_DEPENDENCY]
        assert len(tag_deps) == 0

    # -- Rule 6: App servers depend on cache ------------------------------

    def test_rule6_app_depends_on_cache(self):
        g = _graph(
            _comp("app1", "App1", ComponentType.APP_SERVER),
            _comp("cache1", "Cache", ComponentType.CACHE),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        cache_deps = [d for d in deps if d.source_component == "app1" and d.target_component == "cache1" and d.dependency_type == "shared_storage"]
        assert len(cache_deps) == 1

    def test_rule6_skip_declared(self):
        g = _graph(
            _comp("app1", "App1", ComponentType.APP_SERVER),
            _comp("cache1", "Cache", ComponentType.CACHE),
        )
        g.add_dependency(Dependency(source_id="app1", target_id="cache1"))
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        cache_deps = [d for d in deps if d.source_component == "app1" and d.target_component == "cache1" and d.source == DependencySource.INFERRED_PATTERN]
        assert len(cache_deps) == 0

    def test_rule6_no_cache(self):
        g = _graph(_comp("app1", "App1", ComponentType.APP_SERVER))
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        cache_deps = [d for d in deps if d.dependency_type == "shared_storage" and d.source == DependencySource.INFERRED_PATTERN]
        assert len(cache_deps) == 0

    def test_rule6_confidence_medium(self):
        g = _graph(
            _comp("app1", "App1", ComponentType.APP_SERVER),
            _comp("cache1", "Cache", ComponentType.CACHE),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        cache_deps = [d for d in deps if d.source == DependencySource.INFERRED_PATTERN and d.dependency_type == "shared_storage"]
        assert cache_deps[0].confidence == InferenceConfidence.MEDIUM

    def test_rule6_multiple_apps_one_cache(self):
        g = _graph(
            _comp("app1", "App1", ComponentType.APP_SERVER),
            _comp("app2", "App2", ComponentType.APP_SERVER),
            _comp("cache1", "Cache", ComponentType.CACHE),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        cache_deps = [d for d in deps if d.target_component == "cache1" and d.source == DependencySource.INFERRED_PATTERN]
        assert len(cache_deps) == 2

    # -- Empty graph ------------------------------------------------------

    def test_empty_graph(self):
        g = InfraGraph()
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        assert deps == []

    # -- Combined rules ---------------------------------------------------

    def test_combined_rules_dns_lb_cache(self):
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("lb1", "LB", ComponentType.LOAD_BALANCER),
            _comp("ws1", "WS", ComponentType.WEB_SERVER),
            _comp("app1", "App", ComponentType.APP_SERVER),
            _comp("cache1", "Cache", ComponentType.CACHE),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        # Rule 1: DNS deps for lb1, ws1, app1, cache1 (4, ext APIs excluded)
        # Rule 2: LB dep for ws1 (1)
        # Rule 6: Cache dep for app1 (1)
        assert len(deps) >= 6

    def test_reasoning_populated(self):
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("app1", "App1"),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        for d in deps:
            assert len(d.reasoning) > 0


# ===================================================================
# Section 5: detect_anomalies
# ===================================================================

class TestDetectAnomalies:

    def test_empty_graph(self):
        g = InfraGraph()
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        assert anomalies == []

    # -- missing_lb -------------------------------------------------------

    def test_missing_lb_detected(self):
        g = _graph(_comp("ws1", "WS", ComponentType.WEB_SERVER))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        missing = [a for a in anomalies if a.anomaly_type == "missing_lb"]
        assert len(missing) == 1
        assert "ws1" in missing[0].affected_components

    def test_no_missing_lb_when_lb_exists(self):
        g = _graph(
            _comp("ws1", "WS", ComponentType.WEB_SERVER),
            _comp("lb1", "LB", ComponentType.LOAD_BALANCER),
        )
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        missing = [a for a in anomalies if a.anomaly_type == "missing_lb"]
        assert len(missing) == 0

    def test_no_missing_lb_when_no_ws(self):
        g = _graph(_comp("app1", "App", ComponentType.APP_SERVER))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        missing = [a for a in anomalies if a.anomaly_type == "missing_lb"]
        assert len(missing) == 0

    def test_missing_lb_severity(self):
        g = _graph(_comp("ws1", "WS", ComponentType.WEB_SERVER))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        missing = [a for a in anomalies if a.anomaly_type == "missing_lb"]
        assert missing[0].severity == 0.8

    # -- single_path -------------------------------------------------------

    def test_single_path_detected(self):
        app = _comp("app1", "App", ComponentType.APP_SERVER)
        db = _comp("db1", "DB", ComponentType.DATABASE)
        g = _graph(app, db)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        sp = [a for a in anomalies if a.anomaly_type == "single_path"]
        assert len(sp) == 1
        assert "app1" in sp[0].affected_components
        assert "db1" in sp[0].affected_components

    def test_no_single_path_with_replicas(self):
        app = _comp("app1", "App", ComponentType.APP_SERVER)
        db = _comp("db1", "DB", ComponentType.DATABASE, replicas=3)
        g = _graph(app, db)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        sp = [a for a in anomalies if a.anomaly_type == "single_path"]
        assert len(sp) == 0

    def test_no_single_path_with_two_deps(self):
        app = _comp("app1", "App", ComponentType.APP_SERVER)
        db1 = _comp("db1", "DB1", ComponentType.DATABASE)
        db2 = _comp("db2", "DB2", ComponentType.DATABASE)
        g = _graph(app, db1, db2)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        g.add_dependency(Dependency(source_id="app1", target_id="db2"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        sp = [a for a in anomalies if a.anomaly_type == "single_path"]
        assert len(sp) == 0

    def test_single_path_severity(self):
        app = _comp("app1", "App")
        db = _comp("db1", "DB", ComponentType.DATABASE)
        g = _graph(app, db)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        sp = [a for a in anomalies if a.anomaly_type == "single_path"]
        assert sp[0].severity == 0.7

    # -- circular_dependency -----------------------------------------------

    def test_circular_dependency(self):
        a = _comp("a", "A")
        b = _comp("b", "B")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        cycles = [an for an in anomalies if an.anomaly_type == "circular_dependency"]
        assert len(cycles) >= 1

    def test_no_circular_dependency(self):
        a = _comp("a", "A")
        b = _comp("b", "B")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        cycles = [an for an in anomalies if an.anomaly_type == "circular_dependency"]
        assert len(cycles) == 0

    def test_circular_severity(self):
        a = _comp("a", "A")
        b = _comp("b", "B")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        cycles = [an for an in anomalies if an.anomaly_type == "circular_dependency"]
        assert cycles[0].severity == 0.9

    # -- orphan_component --------------------------------------------------

    def test_orphan_component(self):
        g = _graph(
            _comp("a", "A"),
            _comp("b", "B"),
        )
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        orphan = _comp("c", "C")
        g.add_component(orphan)
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        orphans = [an for an in anomalies if an.anomaly_type == "orphan_component"]
        assert any("c" in o.affected_components for o in orphans)

    def test_no_orphan_single_component(self):
        g = _graph(_comp("a", "A"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        orphans = [an for an in anomalies if an.anomaly_type == "orphan_component"]
        assert len(orphans) == 0

    def test_orphan_severity(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        orphans = [an for an in anomalies if an.anomaly_type == "orphan_component"]
        for o in orphans:
            assert o.severity == 0.3

    # -- asymmetric_redundancy --------------------------------------------

    def test_asymmetric_redundancy(self):
        app = _comp("app1", "App", replicas=3)
        db = _comp("db1", "DB", ComponentType.DATABASE, replicas=1)
        g = _graph(app, db)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        asym = [a for a in anomalies if a.anomaly_type == "asymmetric_redundancy"]
        assert len(asym) == 1

    def test_no_asymmetric_when_equal(self):
        app = _comp("app1", "App", replicas=3)
        db = _comp("db1", "DB", ComponentType.DATABASE, replicas=3)
        g = _graph(app, db)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        asym = [a for a in anomalies if a.anomaly_type == "asymmetric_redundancy"]
        assert len(asym) == 0

    def test_asymmetric_severity(self):
        app = _comp("app1", "App", replicas=2)
        db = _comp("db1", "DB", ComponentType.DATABASE, replicas=1)
        g = _graph(app, db)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        asym = [a for a in anomalies if a.anomaly_type == "asymmetric_redundancy"]
        assert asym[0].severity == 0.6

    def test_asymmetric_recommendation(self):
        app = _comp("app1", "App", replicas=2)
        db = _comp("db1", "DB", ComponentType.DATABASE, replicas=1)
        g = _graph(app, db)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        asym = [a for a in anomalies if a.anomaly_type == "asymmetric_redundancy"]
        assert "db1" in asym[0].recommendation


# ===================================================================
# Section 6: generate_hidden_risk_scenarios
# ===================================================================

class TestGenerateHiddenRiskScenarios:

    def test_empty_deps_empty_scenarios(self):
        g = _graph(_comp("a", "A"))
        engine = TopologyIntelligenceEngine(g)
        scenarios = engine.generate_hidden_risk_scenarios([])
        assert scenarios == []

    def test_single_dep_generates_scenario(self):
        g = _graph(
            _comp("a", "A"),
            _comp("dns1", "DNS", ComponentType.DNS),
        )
        dep = ImplicitDependency(
            source_component="a",
            target_component="dns1",
            dependency_type="shared_dns",
            source=DependencySource.INFERRED_SHARED_INFRA,
            confidence=InferenceConfidence.HIGH,
            reasoning="test",
        )
        engine = TopologyIntelligenceEngine(g)
        scenarios = engine.generate_hidden_risk_scenarios([dep])
        assert len(scenarios) == 1

    def test_scenario_has_id(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        dep = ImplicitDependency(
            source_component="a", target_component="b",
            dependency_type="shared_dns",
            source=DependencySource.INFERRED_SHARED_INFRA,
            confidence=InferenceConfidence.HIGH,
            reasoning="r",
        )
        engine = TopologyIntelligenceEngine(g)
        scenarios = engine.generate_hidden_risk_scenarios([dep])
        assert scenarios[0].scenario_id.startswith("hidden-")

    def test_scenario_unique_ids(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        dep = ImplicitDependency(
            source_component="a", target_component="b",
            dependency_type="shared_dns",
            source=DependencySource.INFERRED_SHARED_INFRA,
            confidence=InferenceConfidence.HIGH,
            reasoning="r",
        )
        engine = TopologyIntelligenceEngine(g)
        scenarios = engine.generate_hidden_risk_scenarios([dep, dep])
        assert scenarios[0].scenario_id != scenarios[1].scenario_id

    def test_scenario_blast_radius(self):
        app = _comp("app1", "App")
        dns = _comp("dns1", "DNS", ComponentType.DNS)
        g = _graph(app, dns)
        g.add_dependency(Dependency(source_id="app1", target_id="dns1"))
        dep = ImplicitDependency(
            source_component="app1", target_component="dns1",
            dependency_type="shared_dns",
            source=DependencySource.INFERRED_SHARED_INFRA,
            confidence=InferenceConfidence.HIGH,
            reasoning="r",
        )
        engine = TopologyIntelligenceEngine(g)
        scenarios = engine.generate_hidden_risk_scenarios([dep])
        assert 0.0 <= scenarios[0].estimated_blast_radius <= 1.0

    def test_scenario_impact_components(self):
        app = _comp("app1", "App")
        dns = _comp("dns1", "DNS", ComponentType.DNS)
        g = _graph(app, dns)
        dep = ImplicitDependency(
            source_component="app1", target_component="dns1",
            dependency_type="shared_dns",
            source=DependencySource.INFERRED_SHARED_INFRA,
            confidence=InferenceConfidence.HIGH,
            reasoning="r",
        )
        engine = TopologyIntelligenceEngine(g)
        scenarios = engine.generate_hidden_risk_scenarios([dep])
        assert "app1" in scenarios[0].impact_components

    def test_scenario_recommended_test(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        dep = ImplicitDependency(
            source_component="a", target_component="b",
            dependency_type="shared_dns",
            source=DependencySource.INFERRED_SHARED_INFRA,
            confidence=InferenceConfidence.HIGH,
            reasoning="r",
        )
        engine = TopologyIntelligenceEngine(g)
        scenarios = engine.generate_hidden_risk_scenarios([dep])
        assert "b" in scenarios[0].recommended_test

    def test_scenario_name(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        dep = ImplicitDependency(
            source_component="a", target_component="b",
            dependency_type="shared_dns",
            source=DependencySource.INFERRED_SHARED_INFRA,
            confidence=InferenceConfidence.HIGH,
            reasoning="r",
        )
        engine = TopologyIntelligenceEngine(g)
        scenarios = engine.generate_hidden_risk_scenarios([dep])
        assert "shared_dns" in scenarios[0].name

    def test_scenario_description(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        dep = ImplicitDependency(
            source_component="a", target_component="b",
            dependency_type="shared_dns",
            source=DependencySource.INFERRED_SHARED_INFRA,
            confidence=InferenceConfidence.HIGH,
            reasoning="r",
        )
        engine = TopologyIntelligenceEngine(g)
        scenarios = engine.generate_hidden_risk_scenarios([dep])
        assert "shared_dns" in scenarios[0].description

    def test_scenario_target_dependency(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        dep = ImplicitDependency(
            source_component="a", target_component="b",
            dependency_type="shared_dns",
            source=DependencySource.INFERRED_SHARED_INFRA,
            confidence=InferenceConfidence.HIGH,
            reasoning="r",
        )
        engine = TopologyIntelligenceEngine(g)
        scenarios = engine.generate_hidden_risk_scenarios([dep])
        assert scenarios[0].target_dependency == dep

    def test_blast_radius_capped_at_1(self):
        """Even if get_all_affected returns many, blast radius <= 1.0."""
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        dep = ImplicitDependency(
            source_component="a", target_component="b",
            dependency_type="shared_dns",
            source=DependencySource.INFERRED_SHARED_INFRA,
            confidence=InferenceConfidence.HIGH,
            reasoning="r",
        )
        engine = TopologyIntelligenceEngine(g)
        scenarios = engine.generate_hidden_risk_scenarios([dep])
        assert scenarios[0].estimated_blast_radius <= 1.0

    def test_multiple_deps(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"), _comp("c", "C"))
        deps = [
            ImplicitDependency(
                source_component="a", target_component="b",
                dependency_type="shared_dns",
                source=DependencySource.INFERRED_SHARED_INFRA,
                confidence=InferenceConfidence.HIGH,
                reasoning="r",
            ),
            ImplicitDependency(
                source_component="a", target_component="c",
                dependency_type="shared_storage",
                source=DependencySource.INFERRED_PATTERN,
                confidence=InferenceConfidence.MEDIUM,
                reasoning="r2",
            ),
        ]
        engine = TopologyIntelligenceEngine(g)
        scenarios = engine.generate_hidden_risk_scenarios(deps)
        assert len(scenarios) == 2


# ===================================================================
# Section 7: calculate_topology_health
# ===================================================================

class TestCalculateTopologyHealth:

    def test_empty_graph_zero(self):
        g = InfraGraph()
        engine = TopologyIntelligenceEngine(g)
        assert engine.calculate_topology_health() == 0.0

    def test_single_healthy_component(self):
        g = _graph(_comp("a", "A"))
        engine = TopologyIntelligenceEngine(g)
        health = engine.calculate_topology_health()
        assert health == 100.0  # single component, no orphan penalty

    def test_penalty_for_orphan(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        engine = TopologyIntelligenceEngine(g)
        health = engine.calculate_topology_health()
        assert health < 100.0

    def test_penalty_for_single_replica_with_dependents(self):
        a = _comp("a", "A")
        b = _comp("b", "B")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        engine = TopologyIntelligenceEngine(g)
        health = engine.calculate_topology_health()
        assert health < 100.0

    def test_penalty_missing_lb(self):
        g = _graph(_comp("ws1", "WS", ComponentType.WEB_SERVER))
        engine = TopologyIntelligenceEngine(g)
        health = engine.calculate_topology_health()
        assert health <= 90.0

    def test_bonus_for_failover(self):
        g = _graph(_comp("a", "A", failover=True))
        engine = TopologyIntelligenceEngine(g)
        health = engine.calculate_topology_health()
        assert health == 100.0  # single component with failover bonus (capped at 100)

    def test_penalty_for_circular_dep(self):
        a = _comp("a", "A")
        b = _comp("b", "B")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        engine = TopologyIntelligenceEngine(g)
        health = engine.calculate_topology_health()
        assert health < 100.0

    def test_health_capped_at_100(self):
        g = _graph(
            _comp("a", "A", failover=True),
            _comp("b", "B", failover=True),
        )
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        engine = TopologyIntelligenceEngine(g)
        health = engine.calculate_topology_health()
        assert health <= 100.0

    def test_health_min_zero(self):
        """Many penalties should not go below 0."""
        comps = [_comp(f"ws{i}", f"WS{i}", ComponentType.WEB_SERVER) for i in range(20)]
        g = _graph(*comps)
        # Add circular deps
        for i in range(19):
            g.add_dependency(Dependency(source_id=f"ws{i}", target_id=f"ws{i+1}"))
            g.add_dependency(Dependency(source_id=f"ws{i+1}", target_id=f"ws{i}"))
        engine = TopologyIntelligenceEngine(g)
        health = engine.calculate_topology_health()
        assert health >= 0.0

    def test_multiple_failover_bonus(self):
        a = _comp("a", "A", failover=True)
        b = _comp("b", "B", failover=True)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        engine = TopologyIntelligenceEngine(g)
        health = engine.calculate_topology_health()
        # both have failover (+6), b has 1 replica with dependent (-8), net: ~98
        assert health > 90.0


# ===================================================================
# Section 8: generate_report
# ===================================================================

class TestGenerateReport:

    def test_empty_graph_report(self):
        g = InfraGraph()
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert isinstance(report, TopologyIntelligenceReport)
        assert report.total_components == 0
        assert report.declared_dependencies == 0
        assert report.implicit_dependencies_found == 0
        assert report.anomalies == []
        assert report.hidden_risks == []
        assert report.topology_health_score == 0.0

    def test_report_total_components(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"), _comp("c", "C"))
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert report.total_components == 3

    def test_report_declared_dependencies(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert report.declared_dependencies == 1

    def test_report_implicit_count(self):
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("app1", "App1"),
        )
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert report.implicit_dependencies_found > 0

    def test_report_anomalies_present(self):
        g = _graph(
            _comp("ws1", "WS", ComponentType.WEB_SERVER),
            _comp("app1", "App"),
        )
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert len(report.anomalies) > 0

    def test_report_hidden_risks(self):
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("app1", "App"),
        )
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert len(report.hidden_risks) > 0

    def test_report_health_score_type(self):
        g = _graph(_comp("a", "A"))
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert isinstance(report.topology_health_score, float)

    def test_report_recommendations_from_anomalies(self):
        g = _graph(
            _comp("ws1", "WS", ComponentType.WEB_SERVER),
        )
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert any("load balancer" in r.lower() for r in report.recommendations)

    def test_report_recommendation_for_implicit_deps(self):
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("app1", "App"),
        )
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert any("implicit" in r.lower() for r in report.recommendations)

    def test_report_high_blast_radius_recommendation(self):
        """When blast radius > 0.5, a recommendation must be present."""
        # dns1 + app1: Rule 1 creates implicit dep app1->dns1.
        # get_all_affected(dns1) = {} (no *declared* deps point to dns1).
        # But source_component=app1 is included in impact => impact = {app1}.
        # blast = 1 / 2 = 0.5 (not strictly > 0.5).
        # Use a chain: app1 (declared dep) -> app2, plus dns implicit dep on app1.
        # Then get_all_affected(dns1) via graph edges -> nothing direct,
        # but impact = {app1}. We need > 0.5 so total must be small.
        # Simplest: 2 components, 1 implicit dep => blast = 1/2 = 0.5.
        # We need strictly > 0.5 so use a declared chain to expand affected set.
        dns = _comp("dns1", "DNS", ComponentType.DNS)
        app1 = _comp("app1", "App1")
        g = _graph(dns, app1)
        # app1 declared-depends on dns1 so get_all_affected(dns1) includes app1
        g.add_dependency(Dependency(source_id="app1", target_id="dns1"))
        # But rule 1 skips already-declared, so no implicit deps -> no scenarios.
        # Instead: don't declare. Implicit dep app1->dns1 via Rule 1.
        # get_all_affected(dns1) = {} (no declared edges point at dns1).
        # impact = {} | {app1} = {app1}. blast = 1/2 = 0.5, not > 0.5.
        # Need: total_components=2, impact > 1 => impossible without declared edges.
        # Solution: make get_all_affected return something by adding a declared
        # chain that makes dns1 a dependency of another component.
        # Build: dns1 + cache1 + app1.  cache1->dns1 declared. app1->dns1 implicit(Rule1).
        # get_all_affected(dns1) = {cache1}. For app1->dns1 implicit dep:
        #   impact = {cache1} | {app1} = {cache1, app1}. blast = 2/3 = 0.67 > 0.5. Yes!
        dns2 = _comp("dns1", "DNS", ComponentType.DNS)
        cache = _comp("cache1", "Cache", ComponentType.CACHE)
        app = _comp("app1", "App1")
        g2 = _graph(dns2, cache, app)
        g2.add_dependency(Dependency(source_id="cache1", target_id="dns1"))
        engine = TopologyIntelligenceEngine(g2)
        report = engine.generate_report()
        high_blast = [s for s in report.hidden_risks if s.estimated_blast_radius > 0.5]
        assert len(high_blast) > 0
        assert any("blast radius" in r.lower() for r in report.recommendations)

    def test_report_no_recommendations_simple(self):
        """Single connected component with no issues."""
        a = _comp("a", "A", replicas=3, failover=True)
        b = _comp("b", "B", replicas=3, failover=True)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        # May still have implicit dep recommendation, but no anomaly-based ones
        anomaly_recs = [r for r in report.recommendations if "implicit" not in r.lower() and "blast" not in r.lower()]
        # No structural anomalies expected for this setup
        assert len(anomaly_recs) == 0

    def test_report_health_rounded(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        # score should be rounded to 1 decimal
        assert report.topology_health_score == round(report.topology_health_score, 1)


# ===================================================================
# Section 9: Integration / edge-case tests
# ===================================================================

class TestIntegration:

    def test_large_graph(self):
        comps = []
        comps.append(_comp("dns1", "DNS", ComponentType.DNS))
        comps.append(_comp("lb1", "LB", ComponentType.LOAD_BALANCER))
        for i in range(5):
            comps.append(_comp(f"ws{i}", f"WS{i}", ComponentType.WEB_SERVER))
        for i in range(3):
            comps.append(_comp(f"app{i}", f"App{i}", ComponentType.APP_SERVER))
        comps.append(_comp("db1", "DB", ComponentType.DATABASE))
        comps.append(_comp("cache1", "Cache", ComponentType.CACHE))
        g = _graph(*comps)
        for i in range(5):
            g.add_dependency(Dependency(source_id=f"ws{i}", target_id="lb1"))
        for i in range(3):
            g.add_dependency(Dependency(source_id=f"app{i}", target_id="db1"))
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert report.total_components == 12
        assert report.implicit_dependencies_found > 0
        assert 0.0 <= report.topology_health_score <= 100.0

    def test_all_types_present(self):
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("lb1", "LB", ComponentType.LOAD_BALANCER),
            _comp("ws1", "WS", ComponentType.WEB_SERVER),
            _comp("app1", "App", ComponentType.APP_SERVER),
            _comp("db1", "DB", ComponentType.DATABASE),
            _comp("cache1", "Cache", ComponentType.CACHE),
            _comp("q1", "Queue", ComponentType.QUEUE),
            _comp("s1", "Storage", ComponentType.STORAGE),
            _comp("ext1", "ExtAPI", ComponentType.EXTERNAL_API),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        assert len(deps) > 0

    def test_declared_dep_reverse_direction_not_skipped_for_rule3(self):
        """Rule3 checks both directions for declared deps."""
        db = _comp("db1", "DB", ComponentType.DATABASE)
        cache = _comp("cache1", "Cache", ComponentType.CACHE)
        g = _graph(db, cache)
        g.add_dependency(Dependency(source_id="cache1", target_id="db1"))
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        net_deps = [d for d in deps if d.dependency_type == "shared_network"]
        # declared dep exists cache1->db1, so shared_network should be skipped
        assert len(net_deps) == 0

    def test_custom_component_type(self):
        g = _graph(_comp("c1", "Custom", ComponentType.CUSTOM))
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert report.total_components == 1

    def test_degraded_health_component(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DEGRADED),
            _comp("b", "B", health=HealthStatus.DOWN),
        )
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert report.total_components == 2

    def test_component_with_region(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        db.region.region = "ap-northeast-1"
        g = _graph(db)
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        assert report.total_components == 1

    def test_report_all_fields_populated_complex(self):
        dns = _comp("dns1", "DNS", ComponentType.DNS)
        ws = _comp("ws1", "WS", ComponentType.WEB_SERVER)
        app = _comp("app1", "App", ComponentType.APP_SERVER)
        db = _comp("db1", "DB", ComponentType.DATABASE)
        cache = _comp("cache1", "Cache", ComponentType.CACHE)
        g = _graph(dns, ws, app, db, cache)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()

        assert report.total_components == 5
        assert report.declared_dependencies == 1
        assert report.implicit_dependencies_found > 0
        assert len(report.anomalies) > 0
        assert len(report.hidden_risks) > 0
        assert 0.0 <= report.topology_health_score <= 100.0
        assert len(report.recommendations) > 0

    def test_rule5_deduplication(self):
        """Rule 5 should not duplicate an implicit dep already found by other rules."""
        a = _comp("a", "A", ComponentType.APP_SERVER, tags=["team-x"])
        b = _comp("b", "B", ComponentType.APP_SERVER, tags=["team-x"])
        g = _graph(a, b)
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        # Both are orphans with same tag -> rule 5 fires
        common_dep_pairs = [
            (d.source_component, d.target_component)
            for d in deps
            if d.source == DependencySource.INFERRED_COMMON_DEPENDENCY
        ]
        # Should have exactly one pair (a,b), no duplicates
        assert len(common_dep_pairs) == 1

    def test_only_storage_components_no_network_dep(self):
        """Storage components are not database/cache, so rule 3 doesn't apply."""
        s1 = _comp("s1", "S1", ComponentType.STORAGE)
        s2 = _comp("s2", "S2", ComponentType.STORAGE)
        g = _graph(s1, s2)
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        net_deps = [d for d in deps if d.dependency_type == "shared_network"]
        assert len(net_deps) == 0

    def test_queue_not_matched_by_cache_rule(self):
        """Queues are not caches — rule 6 should not fire for queues."""
        q = _comp("q1", "Q1", ComponentType.QUEUE)
        app = _comp("app1", "App1", ComponentType.APP_SERVER)
        g = _graph(q, app)
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        cache_deps = [d for d in deps if d.source == DependencySource.INFERRED_PATTERN and d.dependency_type == "shared_storage"]
        assert len(cache_deps) == 0

    def test_external_api_without_dns_no_rule4(self):
        """External API alone (no DNS node) should not trigger Rule 4."""
        g = _graph(_comp("ext1", "Ext", ComponentType.EXTERNAL_API))
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        assert len([d for d in deps if d.dependency_type == "shared_dns"]) == 0

    def test_multiple_external_apis_with_dns(self):
        """Multiple external APIs each get DNS dep from Rule 4."""
        g = _graph(
            _comp("dns1", "DNS", ComponentType.DNS),
            _comp("ext1", "Ext1", ComponentType.EXTERNAL_API),
            _comp("ext2", "Ext2", ComponentType.EXTERNAL_API),
        )
        engine = TopologyIntelligenceEngine(g)
        deps = engine.discover_implicit_dependencies()
        ext_dns = [d for d in deps if d.dependency_type == "shared_dns" and d.source_component.startswith("ext")]
        assert len(ext_dns) == 2

    def test_detect_anomalies_multiple_web_servers_missing_lb(self):
        g = _graph(
            _comp("ws1", "WS1", ComponentType.WEB_SERVER),
            _comp("ws2", "WS2", ComponentType.WEB_SERVER),
            _comp("ws3", "WS3", ComponentType.WEB_SERVER),
        )
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        missing = [a for a in anomalies if a.anomaly_type == "missing_lb"]
        assert len(missing) == 1
        assert len(missing[0].affected_components) == 3

    def test_generate_report_no_implicit_no_recommendation(self):
        """Graph where all deps are declared => no implicit dep recommendation."""
        a = _comp("a", "A", replicas=3, failover=True)
        b = _comp("b", "B", replicas=3, failover=True)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        engine = TopologyIntelligenceEngine(g)
        report = engine.generate_report()
        # No implicit deps => no "implicit" recommendation
        implicit_recs = [r for r in report.recommendations if "implicit" in r.lower()]
        assert len(implicit_recs) == 0

    def test_circular_three_node_cycle(self):
        a = _comp("a", "A")
        b = _comp("b", "B")
        c = _comp("c", "C")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        g.add_dependency(Dependency(source_id="c", target_id="a"))
        engine = TopologyIntelligenceEngine(g)
        anomalies = engine.detect_anomalies()
        cycles = [an for an in anomalies if an.anomaly_type == "circular_dependency"]
        assert len(cycles) >= 1
        assert len(cycles[0].affected_components) == 3
