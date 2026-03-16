"""Comprehensive tests for the Chaos Experiment Recommender engine."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
    SecurityProfile,
    Capacity,
    Dependency,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.chaos_recommender import (
    ChaosExperiment,
    ChaosRecommender,
    Confidence,
    CoverageGap,
    ExperimentType,
    Priority,
    RecommendationReport,
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
    failover: bool = False,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True, promotion_time_seconds=10)
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _add_edge(g: InfraGraph, source_id: str, target_id: str) -> None:
    """Convenience: source depends on target."""
    g.add_dependency(Dependency(source_id=source_id, target_id=target_id))


# ===========================================================================
# 1. Enum values
# ===========================================================================


class TestExperimentType:
    def test_all_values(self):
        expected = {
            "node_failure",
            "network_partition",
            "latency_injection",
            "resource_exhaustion",
            "dependency_failure",
            "cascade_test",
            "failover_test",
            "load_spike",
            "dns_failure",
            "config_corruption",
        }
        assert {e.value for e in ExperimentType} == expected

    def test_is_str_enum(self):
        assert isinstance(ExperimentType.NODE_FAILURE, str)
        assert ExperimentType.NODE_FAILURE == "node_failure"

    def test_membership(self):
        assert ExperimentType("node_failure") is ExperimentType.NODE_FAILURE


class TestPriority:
    def test_all_values(self):
        expected = {"critical", "high", "medium", "low"}
        assert {p.value for p in Priority} == expected

    def test_is_str_enum(self):
        assert isinstance(Priority.CRITICAL, str)

    def test_ordering_by_name(self):
        assert Priority.CRITICAL.value == "critical"
        assert Priority.LOW.value == "low"


class TestConfidence:
    def test_all_values(self):
        assert {c.value for c in Confidence} == {"high", "medium", "low"}

    def test_is_str_enum(self):
        assert isinstance(Confidence.HIGH, str)


# ===========================================================================
# 2. Dataclass defaults
# ===========================================================================


class TestChaosExperimentDataclass:
    def test_defaults(self):
        e = ChaosExperiment(
            experiment_type=ExperimentType.NODE_FAILURE,
            target_component_id="c1",
            target_component_name="Comp1",
            priority=Priority.HIGH,
            confidence=Confidence.MEDIUM,
            rationale="test",
            expected_impact="test",
        )
        assert e.blast_radius == []
        assert e.prerequisites == []
        assert e.estimated_risk_level == 0.5

    def test_custom_values(self):
        e = ChaosExperiment(
            experiment_type=ExperimentType.CASCADE_TEST,
            target_component_id="c2",
            target_component_name="Comp2",
            priority=Priority.CRITICAL,
            confidence=Confidence.HIGH,
            rationale="r",
            expected_impact="i",
            blast_radius=["c3", "c4"],
            prerequisites=["p1"],
            estimated_risk_level=0.9,
        )
        assert e.blast_radius == ["c3", "c4"]
        assert e.prerequisites == ["p1"]
        assert e.estimated_risk_level == 0.9


class TestCoverageGapDataclass:
    def test_defaults(self):
        g = CoverageGap(
            component_id="x",
            component_name="X",
            gap_type="test",
            description="d",
        )
        assert g.severity == 0.5

    def test_custom_severity(self):
        g = CoverageGap(
            component_id="x",
            component_name="X",
            gap_type="t",
            description="d",
            severity=0.99,
        )
        assert g.severity == 0.99


class TestRecommendationReportDataclass:
    def test_defaults(self):
        r = RecommendationReport()
        assert r.experiments == []
        assert r.coverage_gaps == []
        assert r.total_experiments == 0
        assert r.critical_count == 0
        assert r.high_count == 0
        assert r.coverage_score == 100.0
        assert r.recommendations_summary == ""


# ===========================================================================
# 3. Empty graph
# ===========================================================================


class TestEmptyGraph:
    def test_recommend_empty_graph(self):
        g = InfraGraph()
        rec = ChaosRecommender(g)
        report = rec.recommend()
        assert report.total_experiments == 0
        assert report.experiments == []
        assert report.coverage_gaps == []
        assert report.coverage_score == 100.0
        assert "well-protected" in report.recommendations_summary

    def test_coverage_gaps_empty(self):
        g = InfraGraph()
        rec = ChaosRecommender(g)
        assert rec._analyze_coverage_gaps() == []

    def test_generate_experiments_empty(self):
        g = InfraGraph()
        rec = ChaosRecommender(g)
        assert rec._generate_experiments() == []


# ===========================================================================
# 4. Single component (various configs)
# ===========================================================================


class TestSingleComponent:
    def test_single_healthy_component(self):
        g = _graph(_comp("a", "Alpha"))
        report = ChaosRecommender(g).recommend()
        assert report.total_experiments > 0

    def test_single_component_with_failover(self):
        g = _graph(_comp("a", "Alpha", failover=True))
        rec = ChaosRecommender(g)
        gaps = rec._analyze_coverage_gaps()
        gap_types = [gap.gap_type for gap in gaps]
        assert "no_failover" not in gap_types

    def test_single_component_multi_replica(self):
        g = _graph(_comp("a", "Alpha", replicas=3))
        rec = ChaosRecommender(g)
        gaps = rec._analyze_coverage_gaps()
        gap_types = [gap.gap_type for gap in gaps]
        assert "single_replica" not in gap_types

    def test_single_degraded_component(self):
        g = _graph(_comp("a", "Alpha", health=HealthStatus.DEGRADED))
        rec = ChaosRecommender(g)
        gaps = rec._analyze_coverage_gaps()
        assert any(gap.gap_type == "unhealthy" for gap in gaps)

    def test_single_down_component(self):
        g = _graph(_comp("a", "Alpha", health=HealthStatus.DOWN))
        rec = ChaosRecommender(g)
        gaps = rec._analyze_coverage_gaps()
        down_gaps = [g for g in gaps if g.gap_type == "unhealthy"]
        assert len(down_gaps) == 1
        assert down_gaps[0].severity == 0.9

    def test_single_overloaded_component(self):
        g = _graph(_comp("a", "Alpha", health=HealthStatus.OVERLOADED))
        rec = ChaosRecommender(g)
        gaps = rec._analyze_coverage_gaps()
        assert any(gap.gap_type == "unhealthy" for gap in gaps)

    def test_single_component_no_dependents(self):
        """A leaf component should get LOW priority."""
        g = _graph(_comp("a", "Alpha"))
        report = ChaosRecommender(g).recommend()
        for exp in report.experiments:
            assert exp.priority == Priority.LOW


# ===========================================================================
# 5. Coverage gap detection (each of the 10 gap types)
# ===========================================================================


class TestCoverageGapNoFailover:
    def test_detected(self):
        g = _graph(_comp("a", "A"))
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "no_failover" for gap in gaps)

    def test_not_detected_with_failover(self):
        g = _graph(_comp("a", "A", failover=True))
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(gap.gap_type == "no_failover" for gap in gaps)

    def test_severity_with_many_dependents(self):
        a = _comp("a", "A")
        comps = [a] + [_comp(f"d{i}", f"D{i}") for i in range(4)]
        g = _graph(*comps)
        for i in range(4):
            _add_edge(g, f"d{i}", "a")
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        nf = [gap for gap in gaps if gap.gap_type == "no_failover" and gap.component_id == "a"]
        assert nf[0].severity == 0.8


class TestCoverageGapSingleReplica:
    def test_detected(self):
        g = _graph(_comp("a", "A", replicas=1))
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "single_replica" for gap in gaps)

    def test_not_detected_multi_replica(self):
        g = _graph(_comp("a", "A", replicas=3))
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(gap.gap_type == "single_replica" for gap in gaps)

    def test_severity_critical_path(self):
        a = _comp("a", "A")
        comps = [a] + [_comp(f"d{i}", f"D{i}") for i in range(3)]
        g = _graph(*comps)
        for i in range(3):
            _add_edge(g, f"d{i}", "a")
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        sr = [gap for gap in gaps if gap.gap_type == "single_replica" and gap.component_id == "a"]
        assert sr[0].severity == 0.9


class TestCoverageGapCriticalPath:
    def test_detected_3_dependents(self):
        a = _comp("a", "A")
        comps = [a] + [_comp(f"d{i}", f"D{i}") for i in range(3)]
        g = _graph(*comps)
        for i in range(3):
            _add_edge(g, f"d{i}", "a")
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "critical_path_no_redundancy" for gap in gaps)

    def test_not_detected_2_dependents(self):
        a = _comp("a", "A")
        comps = [a, _comp("d0", "D0"), _comp("d1", "D1")]
        g = _graph(*comps)
        _add_edge(g, "d0", "a")
        _add_edge(g, "d1", "a")
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(
            gap.gap_type == "critical_path_no_redundancy" and gap.component_id == "a"
            for gap in gaps
        )


class TestCoverageGapHighResource:
    def test_high_cpu(self):
        c = _comp("a", "A")
        c.metrics = ResourceMetrics(cpu_percent=85)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "high_resource_usage" for gap in gaps)

    def test_high_memory(self):
        c = _comp("a", "A")
        c.metrics = ResourceMetrics(memory_percent=75)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "high_resource_usage" for gap in gaps)

    def test_high_disk(self):
        c = _comp("a", "A")
        c.metrics = ResourceMetrics(disk_percent=90)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "high_resource_usage" for gap in gaps)

    def test_not_triggered_at_70(self):
        c = _comp("a", "A")
        c.metrics = ResourceMetrics(cpu_percent=70)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(gap.gap_type == "high_resource_usage" for gap in gaps)

    def test_description_lists_resources(self):
        c = _comp("a", "A")
        c.metrics = ResourceMetrics(cpu_percent=80, memory_percent=80)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        hr = [gap for gap in gaps if gap.gap_type == "high_resource_usage"]
        assert "CPU" in hr[0].description
        assert "memory" in hr[0].description


class TestCoverageGapExternalDependency:
    def test_detected(self):
        c = _comp("a", "ExtAPI", ctype=ComponentType.EXTERNAL_API)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "external_dependency" for gap in gaps)

    def test_not_detected_for_app_server(self):
        c = _comp("a", "App", ctype=ComponentType.APP_SERVER)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(gap.gap_type == "external_dependency" for gap in gaps)


class TestCoverageGapNoLoadBalancer:
    def test_detected_web_server_without_lb(self):
        c = _comp("w", "Web", ctype=ComponentType.WEB_SERVER)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "no_load_balancer" for gap in gaps)

    def test_not_detected_web_server_depends_on_lb(self):
        lb = _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER)
        ws = _comp("w", "Web", ctype=ComponentType.WEB_SERVER)
        g = _graph(lb, ws)
        _add_edge(g, "w", "lb")  # web depends on lb
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(
            gap.gap_type == "no_load_balancer" and gap.component_id == "w"
            for gap in gaps
        )

    def test_not_detected_lb_depends_on_web(self):
        lb = _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER)
        ws = _comp("w", "Web", ctype=ComponentType.WEB_SERVER)
        g = _graph(lb, ws)
        _add_edge(g, "lb", "w")  # lb depends on web (web is a dependency of lb)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(
            gap.gap_type == "no_load_balancer" and gap.component_id == "w"
            for gap in gaps
        )

    def test_not_detected_for_app_server(self):
        c = _comp("a", "App", ctype=ComponentType.APP_SERVER)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(gap.gap_type == "no_load_balancer" for gap in gaps)


class TestCoverageGapDnsSPOF:
    def test_detected(self):
        c = _comp("d", "DNS", ctype=ComponentType.DNS, replicas=1)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "dns_spof" for gap in gaps)

    def test_not_detected_multi_replica(self):
        c = _comp("d", "DNS", ctype=ComponentType.DNS, replicas=3)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(gap.gap_type == "dns_spof" for gap in gaps)


class TestCoverageGapUnhealthy:
    def test_degraded(self):
        c = _comp("a", "A", health=HealthStatus.DEGRADED)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "unhealthy" for gap in gaps)

    def test_down_severity(self):
        c = _comp("a", "A", health=HealthStatus.DOWN)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        u = [gap for gap in gaps if gap.gap_type == "unhealthy"]
        assert u[0].severity == 0.9

    def test_degraded_severity(self):
        c = _comp("a", "A", health=HealthStatus.DEGRADED)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        u = [gap for gap in gaps if gap.gap_type == "unhealthy"]
        assert u[0].severity == 0.7

    def test_healthy_not_detected(self):
        c = _comp("a", "A", health=HealthStatus.HEALTHY)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(gap.gap_type == "unhealthy" for gap in gaps)


class TestCoverageGapNetworkBottleneck:
    def test_detected_high_ratio(self):
        c = _comp("a", "A")
        c.capacity = Capacity(max_connections=100)
        c.metrics = ResourceMetrics(network_connections=80)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "network_bottleneck" for gap in gaps)

    def test_not_detected_low_ratio(self):
        c = _comp("a", "A")
        c.capacity = Capacity(max_connections=100)
        c.metrics = ResourceMetrics(network_connections=50)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(gap.gap_type == "network_bottleneck" for gap in gaps)

    def test_severity_equals_ratio(self):
        c = _comp("a", "A")
        c.capacity = Capacity(max_connections=100)
        c.metrics = ResourceMetrics(network_connections=90)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        nb = [gap for gap in gaps if gap.gap_type == "network_bottleneck"]
        assert nb[0].severity == pytest.approx(0.9, abs=0.01)

    def test_severity_capped_at_1(self):
        c = _comp("a", "A")
        c.capacity = Capacity(max_connections=100)
        c.metrics = ResourceMetrics(network_connections=150)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        nb = [gap for gap in gaps if gap.gap_type == "network_bottleneck"]
        assert nb[0].severity == 1.0

    def test_not_detected_zero_connections(self):
        c = _comp("a", "A")
        c.capacity = Capacity(max_connections=100)
        c.metrics = ResourceMetrics(network_connections=0)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(gap.gap_type == "network_bottleneck" for gap in gaps)


class TestCoverageGapConfigDriftRisk:
    def test_detected_all_missing(self):
        c = _comp("a", "A")
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "config_drift_risk" for gap in gaps)

    def test_not_detected_all_enabled(self):
        c = _comp("a", "A")
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            rate_limiting=True,
            backup_enabled=True,
        )
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(gap.gap_type == "config_drift_risk" for gap in gaps)

    def test_severity_scales_with_missing_count(self):
        c1 = _comp("a", "A")
        c1.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            rate_limiting=True,
            backup_enabled=False,
        )
        g1 = _graph(c1)
        gaps1 = ChaosRecommender(g1)._analyze_coverage_gaps()
        cd1 = [gap for gap in gaps1 if gap.gap_type == "config_drift_risk"]
        sev1 = cd1[0].severity

        c2 = _comp("b", "B")
        c2.security = SecurityProfile(
            encryption_at_rest=False,
            encryption_in_transit=False,
            rate_limiting=False,
            backup_enabled=False,
        )
        g2 = _graph(c2)
        gaps2 = ChaosRecommender(g2)._analyze_coverage_gaps()
        cd2 = [gap for gap in gaps2 if gap.gap_type == "config_drift_risk"]
        sev2 = cd2[0].severity

        assert sev2 > sev1


# ===========================================================================
# 6. Experiment generation for each gap type
# ===========================================================================


class TestExperimentGeneration:
    def test_failover_test_generated(self):
        g = _graph(_comp("a", "A"))
        exps = ChaosRecommender(g)._generate_experiments()
        assert any(e.experiment_type == ExperimentType.FAILOVER_TEST for e in exps)

    def test_node_failure_single_replica(self):
        g = _graph(_comp("a", "A", replicas=1))
        exps = ChaosRecommender(g)._generate_experiments()
        assert any(e.experiment_type == ExperimentType.NODE_FAILURE for e in exps)

    def test_cascade_test_3_dependents(self):
        a = _comp("a", "A")
        comps = [a] + [_comp(f"d{i}", f"D{i}") for i in range(3)]
        g = _graph(*comps)
        for i in range(3):
            _add_edge(g, f"d{i}", "a")
        exps = ChaosRecommender(g)._generate_experiments()
        assert any(
            e.experiment_type == ExperimentType.CASCADE_TEST and e.target_component_id == "a"
            for e in exps
        )

    def test_resource_exhaustion_generated(self):
        c = _comp("a", "A")
        c.metrics = ResourceMetrics(cpu_percent=90)
        g = _graph(c)
        exps = ChaosRecommender(g)._generate_experiments()
        assert any(e.experiment_type == ExperimentType.RESOURCE_EXHAUSTION for e in exps)

    def test_dependency_failure_external(self):
        c = _comp("a", "ExtAPI", ctype=ComponentType.EXTERNAL_API)
        g = _graph(c)
        exps = ChaosRecommender(g)._generate_experiments()
        assert any(e.experiment_type == ExperimentType.DEPENDENCY_FAILURE for e in exps)

    def test_load_spike_web_server_no_lb(self):
        c = _comp("w", "Web", ctype=ComponentType.WEB_SERVER)
        g = _graph(c)
        exps = ChaosRecommender(g)._generate_experiments()
        assert any(e.experiment_type == ExperimentType.LOAD_SPIKE for e in exps)

    def test_dns_failure_generated(self):
        c = _comp("d", "DNS", ctype=ComponentType.DNS, replicas=1)
        g = _graph(c)
        exps = ChaosRecommender(g)._generate_experiments()
        assert any(e.experiment_type == ExperimentType.DNS_FAILURE for e in exps)

    def test_node_failure_unhealthy(self):
        c = _comp("a", "A", health=HealthStatus.DEGRADED)
        g = _graph(c)
        exps = ChaosRecommender(g)._generate_experiments()
        nf = [e for e in exps if e.experiment_type == ExperimentType.NODE_FAILURE
              and "degraded" in e.rationale]
        assert len(nf) >= 1

    def test_network_partition_generated(self):
        c = _comp("a", "A")
        c.capacity = Capacity(max_connections=100)
        c.metrics = ResourceMetrics(network_connections=80)
        g = _graph(c)
        exps = ChaosRecommender(g)._generate_experiments()
        assert any(e.experiment_type == ExperimentType.NETWORK_PARTITION for e in exps)

    def test_config_corruption_generated(self):
        c = _comp("a", "A")
        g = _graph(c)
        exps = ChaosRecommender(g)._generate_experiments()
        assert any(e.experiment_type == ExperimentType.CONFIG_CORRUPTION for e in exps)


# ===========================================================================
# 7. Priority assignment
# ===========================================================================


class TestPriorityAssignment:
    def test_critical_5_dependents_single_replica_no_failover(self):
        a = _comp("a", "A", replicas=1)
        comps = [a] + [_comp(f"d{i}", f"D{i}") for i in range(5)]
        g = _graph(*comps)
        for i in range(5):
            _add_edge(g, f"d{i}", "a")
        report = ChaosRecommender(g).recommend()
        a_exps = [e for e in report.experiments if e.target_component_id == "a"]
        assert any(e.priority == Priority.CRITICAL for e in a_exps)

    def test_critical_5_dependents_with_failover(self):
        """Even with failover, 5+ dependents -> CRITICAL."""
        a = _comp("a", "A", replicas=3, failover=True)
        comps = [a] + [_comp(f"d{i}", f"D{i}") for i in range(5)]
        g = _graph(*comps)
        for i in range(5):
            _add_edge(g, f"d{i}", "a")
        report = ChaosRecommender(g).recommend()
        a_exps = [e for e in report.experiments if e.target_component_id == "a"]
        assert any(e.priority == Priority.CRITICAL for e in a_exps)

    def test_high_3_dependents(self):
        a = _comp("a", "A")
        comps = [a] + [_comp(f"d{i}", f"D{i}") for i in range(3)]
        g = _graph(*comps)
        for i in range(3):
            _add_edge(g, f"d{i}", "a")
        report = ChaosRecommender(g).recommend()
        a_exps = [e for e in report.experiments if e.target_component_id == "a"]
        assert any(e.priority == Priority.HIGH for e in a_exps)

    def test_high_resource_usage_no_dependents(self):
        c = _comp("a", "A")
        c.metrics = ResourceMetrics(cpu_percent=85)
        g = _graph(c)
        report = ChaosRecommender(g).recommend()
        a_exps = [e for e in report.experiments if e.target_component_id == "a"]
        assert any(e.priority == Priority.HIGH for e in a_exps)

    def test_medium_1_dependent(self):
        a = _comp("a", "A")
        d = _comp("d0", "D0")
        g = _graph(a, d)
        _add_edge(g, "d0", "a")
        report = ChaosRecommender(g).recommend()
        a_exps = [e for e in report.experiments if e.target_component_id == "a"]
        assert any(e.priority == Priority.MEDIUM for e in a_exps)

    def test_medium_2_dependents(self):
        a = _comp("a", "A")
        comps = [a, _comp("d0", "D0"), _comp("d1", "D1")]
        g = _graph(*comps)
        _add_edge(g, "d0", "a")
        _add_edge(g, "d1", "a")
        report = ChaosRecommender(g).recommend()
        a_exps = [e for e in report.experiments if e.target_component_id == "a"]
        assert any(e.priority == Priority.MEDIUM for e in a_exps)

    def test_low_leaf_component(self):
        a = _comp("a", "A")
        g = _graph(a)
        report = ChaosRecommender(g).recommend()
        for exp in report.experiments:
            assert exp.priority == Priority.LOW

    def test_experiments_sorted_by_priority(self):
        """CRITICAL before HIGH before MEDIUM before LOW."""
        a = _comp("a", "Hub", replicas=1)
        comps = [a] + [_comp(f"d{i}", f"D{i}") for i in range(6)]
        leaf = _comp("leaf", "Leaf")
        comps.append(leaf)
        g = _graph(*comps)
        for i in range(6):
            _add_edge(g, f"d{i}", "a")
        report = ChaosRecommender(g).recommend(max_experiments=50)
        priorities = [e.priority for e in report.experiments]
        order = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3}
        numeric = [order[p] for p in priorities]
        assert numeric == sorted(numeric)


# ===========================================================================
# 8. Blast radius calculation
# ===========================================================================


class TestBlastRadius:
    def test_linear_chain(self):
        """A -> B -> C: failing C affects B (A depends on B, B depends on C via edge)."""
        a = _comp("a", "A")
        b = _comp("b", "B")
        c = _comp("c", "C")
        g = _graph(a, b, c)
        _add_edge(g, "a", "b")  # a depends on b
        _add_edge(g, "b", "c")  # b depends on c

        rec = ChaosRecommender(g)
        blast_c = rec._compute_blast_radius("c")
        assert "b" in blast_c
        assert "a" in blast_c

    def test_diamond_topology(self):
        """
        A depends on B and C; B and C both depend on D.
        Failing D affects B, C, A.
        """
        a = _comp("a", "A")
        b = _comp("b", "B")
        c = _comp("c", "C")
        d = _comp("d", "D")
        g = _graph(a, b, c, d)
        _add_edge(g, "a", "b")
        _add_edge(g, "a", "c")
        _add_edge(g, "b", "d")
        _add_edge(g, "c", "d")

        rec = ChaosRecommender(g)
        blast_d = rec._compute_blast_radius("d")
        assert set(blast_d) == {"a", "b", "c"}

    def test_star_topology(self):
        """Hub with 5 spokes: failing hub affects all 5."""
        hub = _comp("hub", "Hub")
        spokes = [_comp(f"s{i}", f"S{i}") for i in range(5)]
        g = _graph(hub, *spokes)
        for i in range(5):
            _add_edge(g, f"s{i}", "hub")

        rec = ChaosRecommender(g)
        blast_hub = rec._compute_blast_radius("hub")
        assert set(blast_hub) == {f"s{i}" for i in range(5)}

    def test_leaf_no_blast(self):
        """A leaf component has no dependents, so blast radius is empty."""
        a = _comp("a", "A")
        b = _comp("b", "B")
        g = _graph(a, b)
        _add_edge(g, "a", "b")

        rec = ChaosRecommender(g)
        blast_a = rec._compute_blast_radius("a")
        assert blast_a == []

    def test_blast_radius_in_experiments(self):
        """Experiments should include correct blast radius."""
        a = _comp("a", "A")
        b = _comp("b", "B")
        g = _graph(a, b)
        _add_edge(g, "a", "b")  # a depends on b

        report = ChaosRecommender(g).recommend()
        b_exps = [e for e in report.experiments if e.target_component_id == "b"]
        for exp in b_exps:
            assert "a" in exp.blast_radius

    def test_no_cycles_in_blast(self):
        """Even if the graph had a cycle, BFS should not loop infinitely."""
        a = _comp("a", "A")
        b = _comp("b", "B")
        g = _graph(a, b)
        _add_edge(g, "a", "b")
        _add_edge(g, "b", "a")  # cycle

        rec = ChaosRecommender(g)
        blast_a = rec._compute_blast_radius("a")
        assert "b" in blast_a
        # Should terminate without error


# ===========================================================================
# 9. max_experiments limit
# ===========================================================================


class TestMaxExperiments:
    def test_limit_honored(self):
        comps = [_comp(f"c{i}", f"C{i}") for i in range(10)]
        g = _graph(*comps)
        report = ChaosRecommender(g).recommend(max_experiments=3)
        assert report.total_experiments == 3
        assert len(report.experiments) == 3

    def test_limit_zero(self):
        g = _graph(_comp("a", "A"))
        report = ChaosRecommender(g).recommend(max_experiments=0)
        assert report.total_experiments == 0
        assert report.experiments == []

    def test_limit_exceeds_total(self):
        g = _graph(_comp("a", "A"))
        report = ChaosRecommender(g).recommend(max_experiments=100)
        assert report.total_experiments == len(report.experiments)

    def test_default_limit_is_10(self):
        comps = [_comp(f"c{i}", f"C{i}") for i in range(20)]
        g = _graph(*comps)
        report = ChaosRecommender(g).recommend()
        assert report.total_experiments <= 10


# ===========================================================================
# 10. Coverage score calculation
# ===========================================================================


class TestCoverageScore:
    def test_perfect_score(self):
        """No gaps → score 100."""
        assert ChaosRecommender._calculate_coverage_score([]) == 100.0

    def test_critical_gap_subtracts_10(self):
        gaps = [CoverageGap("x", "X", "t", "d", severity=0.9)]
        assert ChaosRecommender._calculate_coverage_score(gaps) == 90.0

    def test_high_gap_subtracts_5(self):
        gaps = [CoverageGap("x", "X", "t", "d", severity=0.7)]
        assert ChaosRecommender._calculate_coverage_score(gaps) == 95.0

    def test_medium_gap_subtracts_2(self):
        gaps = [CoverageGap("x", "X", "t", "d", severity=0.3)]
        assert ChaosRecommender._calculate_coverage_score(gaps) == 98.0

    def test_multiple_gaps(self):
        gaps = [
            CoverageGap("a", "A", "t", "d", severity=0.9),  # -10
            CoverageGap("b", "B", "t", "d", severity=0.7),  # -5
            CoverageGap("c", "C", "t", "d", severity=0.3),  # -2
        ]
        assert ChaosRecommender._calculate_coverage_score(gaps) == 83.0

    def test_score_never_below_zero(self):
        gaps = [CoverageGap(f"x{i}", f"X{i}", "t", "d", severity=0.9) for i in range(20)]
        assert ChaosRecommender._calculate_coverage_score(gaps) == 0.0

    def test_boundary_severity_0_8(self):
        gaps = [CoverageGap("x", "X", "t", "d", severity=0.8)]
        # 0.8 is >= 0.8 so CRITICAL → -10
        assert ChaosRecommender._calculate_coverage_score(gaps) == 90.0

    def test_boundary_severity_0_6(self):
        gaps = [CoverageGap("x", "X", "t", "d", severity=0.6)]
        # 0.6 is >= 0.6 so HIGH → -5
        assert ChaosRecommender._calculate_coverage_score(gaps) == 95.0

    def test_boundary_severity_0_59(self):
        gaps = [CoverageGap("x", "X", "t", "d", severity=0.59)]
        # < 0.6 → MEDIUM → -2
        assert ChaosRecommender._calculate_coverage_score(gaps) == 98.0

    def test_coverage_score_in_report(self):
        g = _graph(_comp("a", "A"))
        report = ChaosRecommender(g).recommend()
        assert 0.0 <= report.coverage_score <= 100.0


# ===========================================================================
# 11. Recommendations summary
# ===========================================================================


class TestRecommendationsSummary:
    def test_no_experiments_summary(self):
        g = InfraGraph()
        report = ChaosRecommender(g).recommend()
        assert "well-protected" in report.recommendations_summary

    def test_with_experiments_summary(self):
        g = _graph(_comp("a", "A"))
        report = ChaosRecommender(g).recommend()
        assert "coverage gap" in report.recommendations_summary
        assert "experiment" in report.recommendations_summary

    def test_critical_mentioned_in_summary(self):
        a = _comp("a", "A")
        comps = [a] + [_comp(f"d{i}", f"D{i}") for i in range(6)]
        g = _graph(*comps)
        for i in range(6):
            _add_edge(g, f"d{i}", "a")
        report = ChaosRecommender(g).recommend()
        assert "CRITICAL" in report.recommendations_summary

    def test_coverage_score_in_summary(self):
        g = _graph(_comp("a", "A"))
        report = ChaosRecommender(g).recommend()
        assert "/100" in report.recommendations_summary

    def test_high_mentioned_in_summary(self):
        c = _comp("a", "A")
        c.metrics = ResourceMetrics(cpu_percent=90)
        g = _graph(c)
        report = ChaosRecommender(g).recommend()
        assert "HIGH" in report.recommendations_summary


# ===========================================================================
# 12. Complex topology with mixed configs
# ===========================================================================


class TestComplexTopology:
    def _build_complex_graph(self) -> InfraGraph:
        lb = _comp("lb", "Load Balancer", ctype=ComponentType.LOAD_BALANCER, replicas=2, failover=True)
        web1 = _comp("web1", "Web1", ctype=ComponentType.WEB_SERVER, replicas=2)
        web2 = _comp("web2", "Web2", ctype=ComponentType.WEB_SERVER, replicas=1)
        app = _comp("app", "AppServer", ctype=ComponentType.APP_SERVER, replicas=1)
        db = _comp("db", "Database", ctype=ComponentType.DATABASE, replicas=1)
        cache = _comp("cache", "Cache", ctype=ComponentType.CACHE, replicas=1, failover=True)
        ext = _comp("ext", "ExternalAPI", ctype=ComponentType.EXTERNAL_API)
        dns = _comp("dns", "DNS", ctype=ComponentType.DNS, replicas=1)

        db.health = HealthStatus.DEGRADED
        app.metrics = ResourceMetrics(cpu_percent=80)

        g = _graph(lb, web1, web2, app, db, cache, ext, dns)
        _add_edge(g, "lb", "web1")
        _add_edge(g, "lb", "web2")
        _add_edge(g, "web1", "app")
        _add_edge(g, "web2", "app")
        _add_edge(g, "app", "db")
        _add_edge(g, "app", "cache")
        _add_edge(g, "app", "ext")
        return g

    def test_report_has_experiments(self):
        report = ChaosRecommender(self._build_complex_graph()).recommend()
        assert report.total_experiments > 0

    def test_report_has_coverage_gaps(self):
        report = ChaosRecommender(self._build_complex_graph()).recommend()
        assert len(report.coverage_gaps) > 0

    def test_database_unhealthy_detected(self):
        report = ChaosRecommender(self._build_complex_graph()).recommend()
        assert any(
            g.gap_type == "unhealthy" and g.component_id == "db"
            for g in report.coverage_gaps
        )

    def test_app_server_high_cpu_detected(self):
        report = ChaosRecommender(self._build_complex_graph()).recommend()
        assert any(
            g.gap_type == "high_resource_usage" and g.component_id == "app"
            for g in report.coverage_gaps
        )

    def test_external_api_gap(self):
        report = ChaosRecommender(self._build_complex_graph()).recommend()
        assert any(
            g.gap_type == "external_dependency" and g.component_id == "ext"
            for g in report.coverage_gaps
        )

    def test_dns_spof_gap(self):
        report = ChaosRecommender(self._build_complex_graph()).recommend()
        assert any(
            g.gap_type == "dns_spof" and g.component_id == "dns"
            for g in report.coverage_gaps
        )

    def test_blast_radius_app_server(self):
        """AppServer has web1, web2 as dependents which in turn have lb."""
        g = self._build_complex_graph()
        rec = ChaosRecommender(g)
        blast = rec._compute_blast_radius("app")
        assert "web1" in blast
        assert "web2" in blast
        assert "lb" in blast

    def test_coverage_score_below_100(self):
        report = ChaosRecommender(self._build_complex_graph()).recommend()
        assert report.coverage_score < 100.0

    def test_critical_and_high_counts(self):
        report = ChaosRecommender(self._build_complex_graph()).recommend()
        assert report.critical_count >= 0
        assert report.high_count >= 0
        assert report.critical_count + report.high_count <= report.total_experiments


# ===========================================================================
# 13. Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_all_components_perfect(self):
        """All components have failover, multiple replicas, good security → minimal gaps."""
        c = _comp("a", "A", replicas=3, failover=True)
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            rate_limiting=True,
            backup_enabled=True,
        )
        g = _graph(c)
        report = ChaosRecommender(g).recommend()
        # With no gaps triggered, should still possibly have experiments
        # but coverage score should be very high
        assert report.coverage_score >= 90.0

    def test_all_components_failed(self):
        comps = [_comp(f"c{i}", f"C{i}", health=HealthStatus.DOWN) for i in range(5)]
        g = _graph(*comps)
        report = ChaosRecommender(g).recommend()
        assert report.total_experiments > 0
        assert any(g.gap_type == "unhealthy" for g in report.coverage_gaps)

    def test_long_dependency_chain(self):
        """10-component linear chain: c0 -> c1 -> ... -> c9."""
        comps = [_comp(f"c{i}", f"C{i}") for i in range(10)]
        g = _graph(*comps)
        for i in range(9):
            _add_edge(g, f"c{i}", f"c{i+1}")

        rec = ChaosRecommender(g)
        blast_last = rec._compute_blast_radius("c9")
        # c9 has c8 as dependent, c8 has c7, etc.
        assert len(blast_last) == 9

    def test_single_dependency_chain_blast(self):
        """A -> B -> C: blast of C = {B, A}."""
        a = _comp("a", "A")
        b = _comp("b", "B")
        c = _comp("c", "C")
        g = _graph(a, b, c)
        _add_edge(g, "a", "b")
        _add_edge(g, "b", "c")

        rec = ChaosRecommender(g)
        assert set(rec._compute_blast_radius("c")) == {"a", "b"}

    def test_isolated_components(self):
        """Multiple components with no edges."""
        comps = [_comp(f"c{i}", f"C{i}") for i in range(5)]
        g = _graph(*comps)
        report = ChaosRecommender(g).recommend()
        for exp in report.experiments:
            assert exp.blast_radius == []

    def test_component_with_high_memory_and_disk(self):
        c = _comp("a", "A")
        c.metrics = ResourceMetrics(memory_percent=85, disk_percent=90)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        hr = [gap for gap in gaps if gap.gap_type == "high_resource_usage"]
        assert len(hr) == 1
        assert "memory" in hr[0].description
        assert "disk" in hr[0].description

    def test_web_server_with_lb_dependency(self):
        """WEB_SERVER that depends on LB should not trigger no_load_balancer gap."""
        lb = _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER)
        ws = _comp("ws", "Web", ctype=ComponentType.WEB_SERVER)
        g = _graph(lb, ws)
        _add_edge(g, "ws", "lb")
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(
            gap.gap_type == "no_load_balancer" and gap.component_id == "ws"
            for gap in gaps
        )

    def test_dns_with_multiple_replicas(self):
        dns = _comp("dns", "DNS", ctype=ComponentType.DNS, replicas=3)
        g = _graph(dns)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(gap.gap_type == "dns_spof" for gap in gaps)

    def test_overloaded_component_unhealthy_gap(self):
        c = _comp("a", "A", health=HealthStatus.OVERLOADED)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        u = [gap for gap in gaps if gap.gap_type == "unhealthy"]
        assert len(u) == 1
        assert u[0].severity == 0.7

    def test_report_counts_match(self):
        a = _comp("a", "A")
        comps = [a] + [_comp(f"d{i}", f"D{i}") for i in range(6)]
        g = _graph(*comps)
        for i in range(6):
            _add_edge(g, f"d{i}", "a")
        report = ChaosRecommender(g).recommend(max_experiments=50)
        crit = sum(1 for e in report.experiments if e.priority == Priority.CRITICAL)
        high = sum(1 for e in report.experiments if e.priority == Priority.HIGH)
        assert report.critical_count == crit
        assert report.high_count == high
        assert report.total_experiments == len(report.experiments)

    def test_network_bottleneck_at_boundary(self):
        """Connection ratio exactly at 0.7 should not trigger."""
        c = _comp("a", "A")
        c.capacity = Capacity(max_connections=100)
        c.metrics = ResourceMetrics(network_connections=70)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert not any(gap.gap_type == "network_bottleneck" for gap in gaps)

    def test_network_bottleneck_just_above_boundary(self):
        """Connection ratio at 0.71 should trigger."""
        c = _comp("a", "A")
        c.capacity = Capacity(max_connections=100)
        c.metrics = ResourceMetrics(network_connections=71)
        g = _graph(c)
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        assert any(gap.gap_type == "network_bottleneck" for gap in gaps)


# ===========================================================================
# 14. Prioritize method edge cases
# ===========================================================================


class TestPrioritizeEdgeCases:
    def test_missing_component_gets_low(self):
        """If a component_id in experiment doesn't exist in graph, assign LOW."""
        g = InfraGraph()
        exp = ChaosExperiment(
            experiment_type=ExperimentType.NODE_FAILURE,
            target_component_id="nonexistent",
            target_component_name="Ghost",
            priority=Priority.MEDIUM,
            confidence=Confidence.HIGH,
            rationale="test",
            expected_impact="test",
        )
        rec = ChaosRecommender(g)
        result = rec._prioritize([exp])
        assert result[0].priority == Priority.LOW

    def test_high_memory_triggers_high_priority(self):
        c = _comp("a", "A")
        c.metrics = ResourceMetrics(memory_percent=80)
        g = _graph(c)
        report = ChaosRecommender(g).recommend()
        a_exps = [e for e in report.experiments if e.target_component_id == "a"]
        assert any(e.priority == Priority.HIGH for e in a_exps)

    def test_high_disk_triggers_high_priority(self):
        c = _comp("a", "A")
        c.metrics = ResourceMetrics(disk_percent=80)
        g = _graph(c)
        report = ChaosRecommender(g).recommend()
        a_exps = [e for e in report.experiments if e.target_component_id == "a"]
        assert any(e.priority == Priority.HIGH for e in a_exps)

    def test_4_dependents_gets_high(self):
        a = _comp("a", "A")
        comps = [a] + [_comp(f"d{i}", f"D{i}") for i in range(4)]
        g = _graph(*comps)
        for i in range(4):
            _add_edge(g, f"d{i}", "a")
        report = ChaosRecommender(g).recommend()
        a_exps = [e for e in report.experiments if e.target_component_id == "a"]
        assert any(e.priority == Priority.HIGH for e in a_exps)


# ===========================================================================
# 15. Integration: full workflow
# ===========================================================================


class TestFullWorkflow:
    def test_recommend_returns_report(self):
        g = _graph(_comp("a", "A"))
        report = ChaosRecommender(g).recommend()
        assert isinstance(report, RecommendationReport)

    def test_report_fields_populated(self):
        g = _graph(_comp("a", "A"))
        report = ChaosRecommender(g).recommend()
        assert isinstance(report.experiments, list)
        assert isinstance(report.coverage_gaps, list)
        assert isinstance(report.total_experiments, int)
        assert isinstance(report.critical_count, int)
        assert isinstance(report.high_count, int)
        assert isinstance(report.coverage_score, float)
        assert isinstance(report.recommendations_summary, str)

    def test_multiple_components_mixed(self):
        """A realistic multi-component setup."""
        db = _comp("db", "PostgreSQL", ctype=ComponentType.DATABASE, replicas=2, failover=True)
        db.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            rate_limiting=True,
            backup_enabled=True,
        )
        app = _comp("app", "AppServer", replicas=3, failover=True)
        app.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            rate_limiting=True,
            backup_enabled=True,
        )
        web = _comp("web", "WebServer", ctype=ComponentType.WEB_SERVER, replicas=2)
        lb = _comp("lb", "LoadBalancer", ctype=ComponentType.LOAD_BALANCER, replicas=2)

        g = _graph(db, app, web, lb)
        _add_edge(g, "lb", "web")
        _add_edge(g, "web", "app")
        _add_edge(g, "app", "db")

        report = ChaosRecommender(g).recommend()
        assert report.total_experiments > 0
        assert report.coverage_score > 0

    def test_very_large_graph(self):
        """Ensure it handles 50 components without error."""
        comps = [_comp(f"c{i}", f"C{i}") for i in range(50)]
        g = _graph(*comps)
        # Chain them
        for i in range(49):
            _add_edge(g, f"c{i}", f"c{i+1}")
        report = ChaosRecommender(g).recommend()
        assert report.total_experiments <= 10  # default limit

    def test_critical_path_severity(self):
        """Component with many dependents has higher gap severity."""
        hub = _comp("hub", "Hub")
        spokes = [_comp(f"s{i}", f"S{i}") for i in range(10)]
        g = _graph(hub, *spokes)
        for i in range(10):
            _add_edge(g, f"s{i}", "hub")
        gaps = ChaosRecommender(g)._analyze_coverage_gaps()
        cp = [gap for gap in gaps if gap.gap_type == "critical_path_no_redundancy" and gap.component_id == "hub"]
        assert len(cp) == 1
        assert cp[0].severity == min(1.0, 0.5 + 10 * 0.1)
