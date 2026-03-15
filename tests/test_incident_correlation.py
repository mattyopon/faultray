"""Tests for incident correlation engine."""

import pytest

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.incident_correlation import (
    CorrelationStrength,
    CorrelationType,
    IncidentCorrelationEngine,
    IncidentSignal,
)


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    cpu: float = 0.0,
    memory: float = 0.0,
    disk: float = 0.0,
    health: HealthStatus = HealthStatus.HEALTHY,
    max_connections: int = 0,
    network_connections: int = 0,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.metrics = ResourceMetrics(
        cpu_percent=cpu,
        memory_percent=memory,
        disk_percent=disk,
        network_connections=network_connections,
    )
    c.capacity = Capacity(max_connections=max_connections)
    c.health = health
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ==================================================================
# Signal collection
# ==================================================================

class TestSignalCollection:
    def test_empty_graph_no_signals(self):
        engine = IncidentCorrelationEngine(InfraGraph())
        report = engine.analyze()
        assert report.total_signals == 0
        assert report.total_correlations == 0
        assert "healthy" in report.summary.lower()

    def test_healthy_component_no_signals(self):
        g = _graph(_comp("app", "App"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.total_signals == 0

    def test_degraded_health_signal(self):
        g = _graph(_comp("app", "App", health=HealthStatus.DEGRADED))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.total_signals == 1
        assert report.signals[0].signal_type == "health_degraded"
        assert report.signals[0].severity == 0.5

    def test_overloaded_health_signal(self):
        g = _graph(_comp("app", "App", health=HealthStatus.OVERLOADED))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.total_signals == 1
        assert report.signals[0].signal_type == "health_overloaded"
        assert report.signals[0].severity == 0.8

    def test_down_health_signal(self):
        g = _graph(_comp("app", "App", health=HealthStatus.DOWN))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.total_signals == 1
        assert report.signals[0].signal_type == "health_down"
        assert report.signals[0].severity == 1.0

    def test_high_cpu_signal(self):
        g = _graph(_comp("app", "App", cpu=90))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert any(s.signal_type == "resource_cpu_high" for s in report.signals)

    def test_cpu_at_80_no_signal(self):
        g = _graph(_comp("app", "App", cpu=80))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.total_signals == 0

    def test_high_memory_signal(self):
        g = _graph(_comp("app", "App", memory=95))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert any(s.signal_type == "resource_memory_high" for s in report.signals)

    def test_high_disk_signal(self):
        g = _graph(_comp("db", "DB", ComponentType.DATABASE, disk=85))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert any(s.signal_type == "resource_disk_high" for s in report.signals)

    def test_connection_capacity_signal(self):
        g = _graph(_comp("db", "DB", max_connections=100, network_connections=85))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert any(s.signal_type == "capacity_connections" for s in report.signals)

    def test_connection_below_threshold(self):
        g = _graph(_comp("db", "DB", max_connections=100, network_connections=70))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert not any(s.signal_type == "capacity_connections" for s in report.signals)

    def test_no_max_connections_no_signal(self):
        g = _graph(_comp("app", "App", max_connections=0, network_connections=999))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert not any(s.signal_type == "capacity_connections" for s in report.signals)

    def test_multiple_signals_from_one_component(self):
        g = _graph(_comp("app", "App", cpu=95, memory=90, health=HealthStatus.OVERLOADED))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.total_signals >= 3

    def test_severity_capped_at_1(self):
        g = _graph(_comp("app", "App", cpu=150))  # Over 100%
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        for sig in report.signals:
            assert sig.severity <= 1.0


# ==================================================================
# Correlation detection
# ==================================================================

class TestCorrelation:
    def test_shared_dependency_correlation(self):
        g = _graph(
            _comp("app1", "App1", health=HealthStatus.DEGRADED),
            _comp("app2", "App2", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="app1", target_id="db", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="app2", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        shared_links = [l for l in report.links if l.correlation_type == CorrelationType.SHARED_DEPENDENCY]
        assert len(shared_links) > 0
        assert shared_links[0].strength == CorrelationStrength.STRONG

    def test_cascade_chain_a_depends_on_b(self):
        g = _graph(
            _comp("app", "App", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        cascade_links = [l for l in report.links if l.correlation_type == CorrelationType.CASCADE_CHAIN]
        assert len(cascade_links) > 0

    def test_cascade_chain_b_depends_on_a(self):
        g = _graph(
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN),
            _comp("app", "App", health=HealthStatus.DEGRADED),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        cascade_links = [l for l in report.links if l.correlation_type == CorrelationType.CASCADE_CHAIN]
        assert len(cascade_links) > 0

    def test_same_type_correlation(self):
        g = _graph(
            _comp("app1", "App1", cpu=90),
            _comp("app2", "App2", cpu=85),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        same_type_links = [l for l in report.links if l.correlation_type == CorrelationType.SAME_TYPE]
        # Both are APP_SERVER, have resource signals, same type correlation
        assert len(same_type_links) > 0

    def test_resource_contention_correlation(self):
        g = _graph(
            _comp("app", "App", cpu=90),
            _comp("db", "DB", ComponentType.DATABASE, memory=95),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        contention_links = [l for l in report.links if l.correlation_type == CorrelationType.RESOURCE_CONTENTION]
        assert len(contention_links) > 0

    def test_no_correlation_healthy(self):
        g = _graph(
            _comp("app", "App"),
            _comp("db", "DB", ComponentType.DATABASE),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.total_correlations == 0

    def test_no_self_correlation(self):
        g = _graph(_comp("app", "App", cpu=90, memory=95))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        for link in report.links:
            assert link.signal_a.component_id != link.signal_b.component_id

    def test_component_not_found_returns_none(self):
        """Test _check_correlation when components don't exist in graph."""
        engine = IncidentCorrelationEngine(InfraGraph())
        sig_a = IncidentSignal("missing1", "Missing1", "health_down", 1.0, "test")
        sig_b = IncidentSignal("missing2", "Missing2", "health_down", 1.0, "test")
        result = engine._check_correlation(sig_a, sig_b)
        assert result is None

    def test_no_correlation_different_types_no_resource(self):
        """Two different types, both degraded but not resource signals."""
        g = _graph(
            _comp("app", "App", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DEGRADED),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        # health_degraded is not a resource signal type, different types
        # So no resource_contention or same_type correlation → returns None
        none_type_links = [l for l in report.links if l.correlation_type in (
            CorrelationType.SAME_TYPE, CorrelationType.RESOURCE_CONTENTION
        )]
        # Should have no correlation since they're different types AND signals are health-based not resource-based
        # Actually will have no correlation at all since _check_correlation returns None
        assert report.total_correlations == 0


# ==================================================================
# Clustering
# ==================================================================

class TestClustering:
    def test_correlated_signals_form_cluster(self):
        g = _graph(
            _comp("app", "App", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.total_clusters >= 1
        # Both should be in same cluster
        cluster = report.clusters[0]
        assert len(cluster.affected_components) >= 2

    def test_uncorrelated_signals_separate_clusters(self):
        g = _graph(
            _comp("app", "App", ComponentType.APP_SERVER, health=HealthStatus.DEGRADED),
            _comp("dns", "DNS", ComponentType.DNS, health=HealthStatus.DEGRADED),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        # Different types, no dependency → separate clusters
        assert report.total_clusters == 2

    def test_cluster_severity_is_max(self):
        g = _graph(
            _comp("app", "App", health=HealthStatus.DEGRADED),  # 0.5
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN),  # 1.0
        )
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.clusters[0].severity == 1.0

    def test_cluster_has_root_cause(self):
        g = _graph(
            _comp("app", "App", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.clusters[0].probable_root_cause != ""

    def test_highest_severity_cluster_identified(self):
        g = _graph(
            _comp("app", "App", health=HealthStatus.DOWN),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.highest_severity_cluster != ""

    def test_three_component_cluster(self):
        g = _graph(
            _comp("lb", "LB", ComponentType.LOAD_BALANCER, health=HealthStatus.DEGRADED),
            _comp("app", "App", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN),
        )
        g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        # All three should be in one cluster via chain
        big_clusters = [c for c in report.clusters if len(c.affected_components) >= 3]
        assert len(big_clusters) >= 1


# ==================================================================
# Root cause identification
# ==================================================================

class TestRootCause:
    def test_cascade_root_cause(self):
        g = _graph(
            _comp("app", "App", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert any("Cascade" in rc or "cascade" in rc for rc in report.root_cause_candidates)

    def test_shared_dependency_root_cause(self):
        g = _graph(
            _comp("app1", "App1", health=HealthStatus.DEGRADED),
            _comp("app2", "App2", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="app1", target_id="db", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="app2", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert any("dependency" in rc.lower() or "shared" in rc.lower() for rc in report.root_cause_candidates)

    def test_resource_contention_root_cause(self):
        g = _graph(
            _comp("app", "App", cpu=95),
            _comp("worker", "Worker", ComponentType.QUEUE, memory=90),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert any("contention" in rc.lower() or "resource" in rc.lower() for rc in report.root_cause_candidates)

    def test_same_type_root_cause(self):
        g = _graph(
            _comp("app1", "App1", cpu=85),
            _comp("app2", "App2", cpu=90),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        root_causes = report.root_cause_candidates
        assert len(root_causes) > 0

    def test_isolated_signal_root_cause(self):
        g = _graph(_comp("app", "App", health=HealthStatus.DOWN))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert any("Isolated" in rc or "App" in rc for rc in report.root_cause_candidates)

    def test_fallback_root_cause_when_no_links(self):
        engine = IncidentCorrelationEngine(InfraGraph())
        signals = [IncidentSignal("x", "X", "health_down", 1.0, "test")]
        result = engine._identify_root_cause(signals, [])
        assert "X" in result

    def test_empty_signals_unknown(self):
        engine = IncidentCorrelationEngine(InfraGraph())
        result = engine._identify_root_cause([], [])
        assert result == "Unknown"


# ==================================================================
# Investigation recommendations
# ==================================================================

class TestInvestigation:
    def test_down_recommendations(self):
        """Single down component creates isolated cluster with simple recommendation."""
        g = _graph(_comp("app", "App", health=HealthStatus.DOWN))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        recs = report.clusters[0].recommended_investigation
        assert any("App" in r or "health_down" in r for r in recs)

    def test_down_in_cluster_with_links_recommendations(self):
        """Down component in a correlated cluster gets crash/oom recommendation."""
        g = _graph(
            _comp("app", "App", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        recs = report.clusters[0].recommended_investigation
        assert any("crash" in r.lower() or "oom" in r.lower() or "log" in r.lower() for r in recs)

    def test_overloaded_recommendations(self):
        """Overloaded in correlated cluster gets load/autoscaling recommendation."""
        g = _graph(
            _comp("app", "App", health=HealthStatus.OVERLOADED),
            _comp("worker", "Worker", health=HealthStatus.OVERLOADED),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        # Same type cluster → goes through _recommend_investigation
        cluster = next(c for c in report.clusters if len(c.signals) >= 2)
        recs = cluster.recommended_investigation
        assert any("load" in r.lower() or "autoscal" in r.lower() for r in recs)

    def test_cpu_recommendations(self):
        """CPU signals in correlated cluster get CPU recommendation."""
        g = _graph(
            _comp("app1", "App1", cpu=95),
            _comp("app2", "App2", cpu=90),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        cluster = next(c for c in report.clusters if len(c.signals) >= 2)
        assert any("cpu" in r.lower() for r in cluster.recommended_investigation)

    def test_memory_recommendations(self):
        g = _graph(
            _comp("app1", "App1", memory=95),
            _comp("app2", "App2", memory=90),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        cluster = next(c for c in report.clusters if len(c.signals) >= 2)
        assert any("memory" in r.lower() or "leak" in r.lower() for r in cluster.recommended_investigation)

    def test_disk_recommendations(self):
        g = _graph(
            _comp("db1", "DB1", ComponentType.DATABASE, disk=90),
            _comp("db2", "DB2", ComponentType.DATABASE, disk=85),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        cluster = next(c for c in report.clusters if len(c.signals) >= 2)
        assert any("log" in r.lower() or "disk" in r.lower() or "clean" in r.lower() or "temp" in r.lower() for r in cluster.recommended_investigation)

    def test_connection_recommendations(self):
        g = _graph(
            _comp("db1", "DB1", ComponentType.DATABASE, max_connections=100, network_connections=90),
            _comp("db2", "DB2", ComponentType.DATABASE, max_connections=100, network_connections=85),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        cluster = next(c for c in report.clusters if len(c.signals) >= 2)
        assert any("connection" in r.lower() or "pool" in r.lower() for r in cluster.recommended_investigation)

    def test_cascade_investigation(self):
        g = _graph(
            _comp("app", "App", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        cluster = report.clusters[0]
        assert any("upstream" in r.lower() or "dependency" in r.lower() for r in cluster.recommended_investigation)

    def test_shared_dep_investigation(self):
        g = _graph(
            _comp("app1", "App1", health=HealthStatus.DEGRADED),
            _comp("app2", "App2", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="app1", target_id="db", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="app2", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        cluster = next(c for c in report.clusters if len(c.affected_components) >= 2)
        assert any("shared" in r.lower() or "dependency" in r.lower() for r in cluster.recommended_investigation)

    def test_no_signals_fallback_recommendation(self):
        engine = IncidentCorrelationEngine(InfraGraph())
        recs = engine._recommend_investigation([], [])
        assert len(recs) == 1
        assert "review" in recs[0].lower() or "metrics" in recs[0].lower()

    def test_max_five_recommendations(self):
        g = _graph(_comp("app", "App", cpu=95, memory=95, disk=95, health=HealthStatus.DOWN,
                         max_connections=100, network_connections=95))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        for cluster in report.clusters:
            assert len(cluster.recommended_investigation) <= 5


# ==================================================================
# Summary generation
# ==================================================================

class TestSummary:
    def test_no_signals_summary(self):
        engine = IncidentCorrelationEngine(InfraGraph())
        report = engine.analyze()
        assert "No incident" in report.summary

    def test_single_signal_summary(self):
        g = _graph(_comp("app", "App", health=HealthStatus.DOWN))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert "1 incident signal" in report.summary

    def test_multiple_signals_summary(self):
        g = _graph(
            _comp("app", "App", health=HealthStatus.DOWN),
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DEGRADED),
        )
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert "signals" in report.summary

    def test_critical_severity_in_summary(self):
        g = _graph(_comp("app", "App", health=HealthStatus.DOWN))  # severity 1.0
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert "CRITICAL" in report.summary

    def test_correlations_in_summary(self):
        g = _graph(
            _comp("app", "App", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert "correlation" in report.summary

    def test_clusters_in_summary(self):
        g = _graph(_comp("app", "App", health=HealthStatus.DEGRADED))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert "cluster" in report.summary


# ==================================================================
# Edge cases
# ==================================================================

class TestEdgeCases:
    def test_many_components_performance(self):
        comps = [_comp(f"app{i}", f"App{i}", cpu=90) for i in range(20)]
        g = _graph(*comps)
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.total_signals == 20

    def test_all_component_types(self):
        comps = [_comp(t.value, t.value, t, health=HealthStatus.DEGRADED) for t in ComponentType]
        g = _graph(*comps)
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.total_signals == len(ComponentType)

    def test_diamond_dependency(self):
        g = _graph(
            _comp("app", "App", health=HealthStatus.DEGRADED),
            _comp("svc1", "Svc1", health=HealthStatus.DEGRADED),
            _comp("svc2", "Svc2", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN),
        )
        g.add_dependency(Dependency(source_id="app", target_id="svc1", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="app", target_id="svc2", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="svc1", target_id="db", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="svc2", target_id="db", dependency_type="requires"))
        engine = IncidentCorrelationEngine(g)
        report = engine.analyze()
        assert report.total_clusters >= 1
        assert report.total_correlations >= 1
