"""Tests for faultray.simulator.resource_contention_analyzer module.

Targets 100% coverage with 30+ test functions covering all enums, models,
engine methods, edge cases, and internal helpers.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    NetworkProfile,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.resource_contention_analyzer import (
    CPUThrottlingImpact,
    ContentionAnalysisReport,
    ContentionHotspot,
    ContentionLatencyModel,
    ContentionSeverity,
    DiskIOSaturation,
    IsolationEvaluation,
    IsolationMechanism,
    LockContentionFinding,
    LockOrderViolationType,
    MemoryPressureCascade,
    NetworkBandwidthContention,
    NoisyNeighborFinding,
    OOMAction,
    ResourceContentionAnalyzer,
    ResourceKind,
    ResourceReservation,
    ThrottlingPolicy,
    _COMPONENT_CONTENTION_PRIORITY,
    _ISOLATION_STRENGTH,
    _RESOURCE_WEIGHT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "c1",
    ctype: ComponentType = ComponentType.APP_SERVER,
    cpu: float = 0.0,
    memory: float = 0.0,
    disk: float = 0.0,
    network_connections: int = 0,
    max_connections: int = 1000,
    connection_pool_size: int = 100,
    open_files: int = 0,
    host: str = "",
    replicas: int = 1,
    tags: list[str] | None = None,
    parameters: dict | None = None,
    rtt_ms: float = 1.0,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        host=host,
        replicas=replicas,
        capacity=Capacity(
            max_connections=max_connections,
            connection_pool_size=connection_pool_size,
        ),
        metrics=ResourceMetrics(
            cpu_percent=cpu,
            memory_percent=memory,
            disk_percent=disk,
            network_connections=network_connections,
            open_files=open_files,
        ),
        tags=tags or [],
        parameters=parameters or {},
        network=NetworkProfile(rtt_ms=rtt_ms),
    )


def _graph(*components: Component, deps: list[tuple[str, str]] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt in (deps or []):
        g.add_dependency(Dependency(source_id=src, target_id=tgt))
    return g


# ---------------------------------------------------------------------------
# 1. Enum coverage
# ---------------------------------------------------------------------------


class TestEnums:
    def test_resource_kind_values(self):
        expected = {"cpu", "memory", "disk_io", "network_bandwidth",
                    "file_descriptors", "locks"}
        assert {r.value for r in ResourceKind} == expected

    def test_isolation_mechanism_values(self):
        expected = {"none", "cgroup_v1", "cgroup_v2", "namespace",
                    "quota", "dedicated_host"}
        assert {m.value for m in IsolationMechanism} == expected

    def test_contention_severity_values(self):
        expected = {"critical", "high", "medium", "low", "none"}
        assert {s.value for s in ContentionSeverity} == expected

    def test_lock_order_violation_type_values(self):
        expected = {"potential_deadlock", "inconsistent_order", "nested_lock"}
        assert {v.value for v in LockOrderViolationType} == expected

    def test_oom_action_values(self):
        expected = {"kill_process", "throttle", "evict", "no_action"}
        assert {a.value for a in OOMAction} == expected

    def test_throttling_policy_values(self):
        expected = {"cfs_bandwidth", "cpu_shares", "cpuset", "none"}
        assert {p.value for p in ThrottlingPolicy} == expected


# ---------------------------------------------------------------------------
# 2. Constants coverage
# ---------------------------------------------------------------------------


class TestConstants:
    def test_resource_weight_all_kinds(self):
        for kind in ResourceKind:
            assert kind in _RESOURCE_WEIGHT

    def test_isolation_strength_all_mechanisms(self):
        for mech in IsolationMechanism:
            assert mech in _ISOLATION_STRENGTH
        assert _ISOLATION_STRENGTH[IsolationMechanism.NONE] == 0.0
        assert _ISOLATION_STRENGTH[IsolationMechanism.DEDICATED_HOST] == 1.0

    def test_component_contention_priority_all_types(self):
        for ct in ComponentType:
            assert ct in _COMPONENT_CONTENTION_PRIORITY


# ---------------------------------------------------------------------------
# 3. Model defaults
# ---------------------------------------------------------------------------


class TestModelDefaults:
    def test_noisy_neighbor_finding_defaults(self):
        f = NoisyNeighborFinding(aggressor_id="a1", resource=ResourceKind.CPU)
        assert f.victim_ids == []
        assert f.severity == ContentionSeverity.NONE
        assert f.isolation_mechanism == IsolationMechanism.NONE

    def test_isolation_evaluation_defaults(self):
        e = IsolationEvaluation(component_id="c1")
        assert e.mechanism == IsolationMechanism.NONE
        assert e.strength_score == 0.0
        assert e.gaps == []

    def test_contention_hotspot_defaults(self):
        h = ContentionHotspot(component_id="c1", resource=ResourceKind.CPU)
        assert h.contention_score == 0.0
        assert h.severity == ContentionSeverity.NONE

    def test_lock_contention_finding_defaults(self):
        f = LockContentionFinding()
        assert f.component_ids == []
        assert f.violation_type == LockOrderViolationType.INCONSISTENT_ORDER

    def test_memory_pressure_cascade_defaults(self):
        m = MemoryPressureCascade(trigger_component_id="c1")
        assert m.oom_action == OOMAction.NO_ACTION
        assert m.cascade_depth == 0

    def test_disk_io_saturation_defaults(self):
        d = DiskIOSaturation(component_id="c1")
        assert d.is_saturated is False
        assert d.throughput_impact_percent == 0.0

    def test_network_bandwidth_contention_defaults(self):
        n = NetworkBandwidthContention(component_id="c1")
        assert n.total_bandwidth_percent == 0.0
        assert n.severity == ContentionSeverity.NONE

    def test_cpu_throttling_impact_defaults(self):
        c = CPUThrottlingImpact(component_id="c1")
        assert c.policy == ThrottlingPolicy.NONE
        assert c.throttled_percent == 0.0

    def test_resource_reservation_defaults(self):
        r = ResourceReservation(component_id="c1", resource=ResourceKind.CPU)
        assert r.qos_class == "BestEffort"
        assert r.overcommit_ratio == 1.0

    def test_contention_latency_model_defaults(self):
        m = ContentionLatencyModel(component_id="c1")
        assert m.base_latency_ms == 0.0
        assert m.primary_contention_source == ResourceKind.CPU

    def test_contention_analysis_report_defaults(self):
        r = ContentionAnalysisReport()
        assert r.overall_severity == ContentionSeverity.NONE
        assert r.noisy_neighbors == []
        assert r.summary == ""


# ---------------------------------------------------------------------------
# 4. Noisy neighbor detection
# ---------------------------------------------------------------------------


class TestNoisyNeighborDetection:
    def test_empty_graph(self):
        engine = ResourceContentionAnalyzer()
        g = _graph()
        assert engine.detect_noisy_neighbors(g) == []

    def test_single_component(self):
        engine = ResourceContentionAnalyzer()
        g = _graph(_comp("a1", cpu=90.0, host="h1"))
        assert engine.detect_noisy_neighbors(g) == []

    def test_co_located_high_cpu(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", cpu=85.0, host="h1")
        b = _comp("b1", cpu=30.0, host="h1")
        g = _graph(a, b)
        findings = engine.detect_noisy_neighbors(g)
        assert len(findings) > 0
        # a1 is the aggressor
        aggressor_ids = [f.aggressor_id for f in findings]
        assert "a1" in aggressor_ids
        for f in findings:
            if f.aggressor_id == "a1":
                assert "b1" in f.victim_ids

    def test_no_findings_below_threshold(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", cpu=50.0, host="h1")
        b = _comp("b1", cpu=30.0, host="h1")
        g = _graph(a, b)
        findings = engine.detect_noisy_neighbors(g)
        assert len(findings) == 0

    def test_isolation_reduces_impact(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", cpu=80.0, host="h1", tags=["dedicated_host"])
        b = _comp("b1", cpu=30.0, host="h1")
        g = _graph(a, b)
        findings_isolated = engine.detect_noisy_neighbors(g)

        a2 = _comp("a2", cpu=80.0, host="h2")
        b2 = _comp("b2", cpu=30.0, host="h2")
        g2 = _graph(a2, b2)
        findings_bare = engine.detect_noisy_neighbors(g2)

        # Isolated should have lower or equal impact
        if findings_isolated and findings_bare:
            iso_impact = findings_isolated[0].impact_percent
            bare_impact = findings_bare[0].impact_percent
            assert iso_impact <= bare_impact

    def test_different_hosts_no_findings(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", cpu=90.0, host="h1")
        b = _comp("b1", cpu=90.0, host="h2")
        g = _graph(a, b)
        findings = engine.detect_noisy_neighbors(g)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# 5. Isolation evaluation
# ---------------------------------------------------------------------------


class TestIsolationEvaluation:
    def test_no_isolation(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", host="h1")
        g = _graph(c)
        evals = engine.evaluate_isolation(g)
        assert len(evals) == 1
        assert evals[0].mechanism == IsolationMechanism.NONE
        assert evals[0].strength_score == 0.0
        assert len(evals[0].gaps) > 0

    def test_cgroup_v2_isolation(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", tags=["cgroup_v2"])
        g = _graph(c)
        evals = engine.evaluate_isolation(g)
        assert evals[0].mechanism == IsolationMechanism.CGROUP_V2
        assert evals[0].strength_score == 0.7

    def test_dedicated_host(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", tags=["dedicated_host"])
        g = _graph(c)
        evals = engine.evaluate_isolation(g)
        assert evals[0].mechanism == IsolationMechanism.DEDICATED_HOST
        assert evals[0].strength_score == 1.0

    def test_co_located_without_isolation_adds_gap(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", host="h1")
        b = _comp("b1", host="h1")
        g = _graph(a, b)
        evals = engine.evaluate_isolation(g)
        a_eval = [e for e in evals if e.component_id == "a1"][0]
        assert any("shares host" in gap for gap in a_eval.gaps)

    def test_high_priority_low_isolation_gap(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", ctype=ComponentType.LOAD_BALANCER)
        g = _graph(c)
        evals = engine.evaluate_isolation(g)
        assert any("High-priority" in gap for gap in evals[0].gaps)

    def test_parameter_based_isolation(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", parameters={"cgroup": "v1"})
        g = _graph(c)
        evals = engine.evaluate_isolation(g)
        assert evals[0].mechanism == IsolationMechanism.CGROUP_V1

    def test_namespace_isolation_from_tags(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", tags=["namespace"])
        g = _graph(c)
        evals = engine.evaluate_isolation(g)
        assert evals[0].mechanism == IsolationMechanism.NAMESPACE

    def test_quota_from_parameter(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", parameters={"quota": "enabled"})
        g = _graph(c)
        evals = engine.evaluate_isolation(g)
        assert evals[0].mechanism == IsolationMechanism.QUOTA


# ---------------------------------------------------------------------------
# 6. Hotspot identification
# ---------------------------------------------------------------------------


class TestHotspotIdentification:
    def test_no_hotspots_low_util(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", cpu=20.0)
        b = _comp("b1", cpu=10.0)
        g = _graph(a, b, deps=[("b1", "a1")])
        hotspots = engine.identify_hotspots(g)
        assert len(hotspots) == 0

    def test_high_fan_in_hotspot(self):
        engine = ResourceContentionAnalyzer()
        db = _comp("db", ctype=ComponentType.DATABASE, cpu=70.0)
        apps = [_comp(f"app{i}", cpu=30.0) for i in range(4)]
        deps = [(f"app{i}", "db") for i in range(4)]
        g = _graph(db, *apps, deps=deps)
        hotspots = engine.identify_hotspots(g)
        assert len(hotspots) > 0
        db_hotspots = [h for h in hotspots if h.component_id == "db"]
        assert len(db_hotspots) > 0
        assert db_hotspots[0].contention_score > 0

    def test_co_located_hotspot(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", cpu=60.0, host="h1")
        b = _comp("b1", cpu=40.0, host="h1")
        g = _graph(a, b)
        hotspots = engine.identify_hotspots(g)
        assert len(hotspots) > 0

    def test_lock_hotspot_recommendations(self):
        engine = ResourceContentionAnalyzer()
        db = _comp("db", ctype=ComponentType.DATABASE,
                   network_connections=80, connection_pool_size=100)
        apps = [_comp(f"app{i}") for i in range(4)]
        deps = [(f"app{i}", "db") for i in range(4)]
        g = _graph(db, *apps, deps=deps)
        hotspots = engine.identify_hotspots(g)
        lock_hotspots = [h for h in hotspots if h.resource == ResourceKind.LOCKS]
        if lock_hotspots:
            assert any("replica" in r or "shard" in r for r in lock_hotspots[0].recommendations)


# ---------------------------------------------------------------------------
# 7. Lock contention analysis
# ---------------------------------------------------------------------------


class TestLockContentionAnalysis:
    def test_empty_graph(self):
        engine = ResourceContentionAnalyzer()
        g = _graph()
        assert engine.analyze_lock_contention(g) == []

    def test_single_component(self):
        engine = ResourceContentionAnalyzer()
        g = _graph(_comp("c1"))
        assert engine.analyze_lock_contention(g) == []

    def test_deadlock_detection(self):
        engine = ResourceContentionAnalyzer()
        db1 = _comp("db1", ctype=ComponentType.DATABASE)
        db2 = _comp("db2", ctype=ComponentType.DATABASE)
        g = _graph(db1, db2, deps=[("db1", "db2"), ("db2", "db1")])
        findings = engine.analyze_lock_contention(g)
        deadlocks = [f for f in findings
                     if f.violation_type == LockOrderViolationType.POTENTIAL_DEADLOCK]
        assert len(deadlocks) == 1
        assert deadlocks[0].severity == ContentionSeverity.CRITICAL
        assert len(deadlocks[0].cycle) == 3  # [a, b, a]

    def test_inconsistent_order_detection(self):
        engine = ResourceContentionAnalyzer()
        app = _comp("app1", ctype=ComponentType.APP_SERVER)
        db1 = _comp("db1", ctype=ComponentType.DATABASE,
                     network_connections=50, connection_pool_size=100)
        db2 = _comp("db2", ctype=ComponentType.DATABASE,
                     network_connections=40, connection_pool_size=100)
        g = _graph(app, db1, db2, deps=[("app1", "db1"), ("app1", "db2")])
        findings = engine.analyze_lock_contention(g)
        inconsistent = [f for f in findings
                        if f.violation_type == LockOrderViolationType.INCONSISTENT_ORDER]
        assert len(inconsistent) >= 1

    def test_nested_lock_detection(self):
        engine = ResourceContentionAnalyzer()
        db1 = _comp("db1", ctype=ComponentType.DATABASE)
        db2 = _comp("db2", ctype=ComponentType.DATABASE)
        db3 = _comp("db3", ctype=ComponentType.DATABASE)
        g = _graph(db1, db2, db3, deps=[("db1", "db2"), ("db2", "db3")])
        findings = engine.analyze_lock_contention(g)
        nested = [f for f in findings
                  if f.violation_type == LockOrderViolationType.NESTED_LOCK]
        assert len(nested) >= 1

    def test_no_findings_for_non_lock_components(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", ctype=ComponentType.APP_SERVER)
        b = _comp("b1", ctype=ComponentType.CACHE)
        g = _graph(a, b, deps=[("a1", "b1"), ("b1", "a1")])
        findings = engine.analyze_lock_contention(g)
        deadlocks = [f for f in findings
                     if f.violation_type == LockOrderViolationType.POTENTIAL_DEADLOCK]
        assert len(deadlocks) == 0


# ---------------------------------------------------------------------------
# 8. Memory pressure cascades
# ---------------------------------------------------------------------------


class TestMemoryPressureCascades:
    def test_low_memory_no_cascade(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", memory=40.0)
        g = _graph(c)
        cascades = engine.model_memory_pressure_cascades(g)
        assert len(cascades) == 0

    def test_medium_pressure_throttle(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", memory=78.0)
        g = _graph(c)
        cascades = engine.model_memory_pressure_cascades(g)
        assert len(cascades) == 1
        assert cascades[0].oom_action == OOMAction.THROTTLE

    def test_high_pressure_evict(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", memory=90.0)
        g = _graph(c)
        cascades = engine.model_memory_pressure_cascades(g)
        assert len(cascades) == 1
        assert cascades[0].oom_action == OOMAction.EVICT

    def test_critical_pressure_kill(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", memory=97.0)
        g = _graph(c)
        cascades = engine.model_memory_pressure_cascades(g)
        assert len(cascades) == 1
        assert cascades[0].oom_action == OOMAction.KILL_PROCESS

    def test_cascade_with_dependents(self):
        engine = ResourceContentionAnalyzer()
        db = _comp("db1", ctype=ComponentType.DATABASE, memory=96.0)
        app = _comp("app1", memory=30.0)
        web = _comp("web1", memory=20.0)
        g = _graph(db, app, web, deps=[("app1", "db1"), ("web1", "app1")])
        cascades = engine.model_memory_pressure_cascades(g)
        db_cascade = [c for c in cascades if c.trigger_component_id == "db1"]
        assert len(db_cascade) == 1
        assert "app1" in db_cascade[0].affected_components
        assert db_cascade[0].severity == ContentionSeverity.CRITICAL

    def test_borderline_60_percent(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", memory=60.0)
        g = _graph(c)
        cascades = engine.model_memory_pressure_cascades(g)
        assert len(cascades) == 1
        assert cascades[0].oom_action == OOMAction.NO_ACTION


# ---------------------------------------------------------------------------
# 9. Disk I/O saturation
# ---------------------------------------------------------------------------


class TestDiskIOSaturation:
    def test_low_disk_no_findings(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", disk=20.0)
        g = _graph(c)
        results = engine.analyze_disk_io_saturation(g)
        assert len(results) == 0

    def test_saturated_disk(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", disk=92.0)
        g = _graph(c)
        results = engine.analyze_disk_io_saturation(g)
        assert len(results) == 1
        assert results[0].is_saturated is True
        assert results[0].throughput_impact_percent > 0

    def test_critical_disk(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", disk=97.0)
        g = _graph(c)
        results = engine.analyze_disk_io_saturation(g)
        assert results[0].severity == ContentionSeverity.CRITICAL

    def test_competing_co_located(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", disk=85.0, host="h1")
        b = _comp("b1", disk=45.0, host="h1")
        g = _graph(a, b)
        results = engine.analyze_disk_io_saturation(g)
        a_result = [r for r in results if r.component_id == "a1"][0]
        assert "b1" in a_result.competing_components

    def test_database_gets_caching_recommendation(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", ctype=ComponentType.DATABASE, disk=82.0)
        g = _graph(c)
        results = engine.analyze_disk_io_saturation(g)
        assert any("cach" in r for r in results[0].recommendations)

    def test_moderate_disk_non_saturated(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", disk=55.0)
        g = _graph(c)
        results = engine.analyze_disk_io_saturation(g)
        assert len(results) == 1
        assert results[0].is_saturated is False
        assert results[0].throughput_impact_percent == 0.0


# ---------------------------------------------------------------------------
# 10. Network bandwidth contention
# ---------------------------------------------------------------------------


class TestNetworkBandwidthContention:
    def test_no_co_located(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", network_connections=500, host="h1")
        b = _comp("b1", network_connections=300, host="h2")
        g = _graph(a, b)
        results = engine.analyze_network_bandwidth_contention(g)
        assert len(results) == 0

    def test_co_located_high_bandwidth(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", network_connections=700, max_connections=1000, host="h1")
        b = _comp("b1", network_connections=600, max_connections=1000, host="h1")
        g = _graph(a, b)
        results = engine.analyze_network_bandwidth_contention(g)
        assert len(results) >= 2  # one per component on the host
        assert all(r.total_bandwidth_percent > 0 for r in results)

    def test_low_bandwidth_no_findings(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", network_connections=100, max_connections=1000, host="h1")
        b = _comp("b1", network_connections=100, max_connections=1000, host="h1")
        g = _graph(a, b)
        results = engine.analyze_network_bandwidth_contention(g)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# 11. CPU throttling
# ---------------------------------------------------------------------------


class TestCPUThrottling:
    def test_no_throttling_low_cpu(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=40.0)
        g = _graph(c)
        results = engine.analyze_cpu_throttling(g)
        assert len(results) == 0

    def test_cfs_bandwidth_throttling(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=90.0, parameters={
            "cpu_policy": "cfs",
            "cpu_quota_percent": 70.0,
        })
        g = _graph(c)
        results = engine.analyze_cpu_throttling(g)
        assert len(results) == 1
        assert results[0].policy == ThrottlingPolicy.CFS_BANDWIDTH
        assert results[0].throttled_percent > 0
        assert results[0].latency_increase_ms > 0

    def test_cpu_shares_co_located(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", cpu=70.0, host="h1", parameters={"cpu_policy": "shares"})
        b = _comp("b1", cpu=60.0, host="h1")
        g = _graph(a, b)
        results = engine.analyze_cpu_throttling(g)
        a_results = [r for r in results if r.component_id == "a1"]
        assert len(a_results) == 1
        assert a_results[0].policy == ThrottlingPolicy.CPU_SHARES
        assert a_results[0].throttled_percent > 0

    def test_cpuset_near_saturation(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=98.0, parameters={"cpu_policy": "cpuset"})
        g = _graph(c)
        results = engine.analyze_cpu_throttling(g)
        assert len(results) == 1
        assert results[0].policy == ThrottlingPolicy.CPUSET

    def test_no_policy_high_cpu(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=90.0)
        g = _graph(c)
        results = engine.analyze_cpu_throttling(g)
        assert len(results) == 1
        assert results[0].policy == ThrottlingPolicy.NONE

    def test_cfs_below_quota_no_throttling(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=60.0, parameters={
            "cpu_policy": "cfs",
            "cpu_quota_percent": 80.0,
        })
        g = _graph(c)
        results = engine.analyze_cpu_throttling(g)
        assert len(results) == 0

    def test_cfs_with_invalid_quota_string(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=90.0, parameters={
            "cpu_policy": "cfs",
            "cpu_quota_percent": "invalid",
        })
        g = _graph(c)
        results = engine.analyze_cpu_throttling(g)
        assert len(results) == 1
        # Falls back to 80.0 default
        assert results[0].throttled_percent > 0


# ---------------------------------------------------------------------------
# 12. Resource reservations
# ---------------------------------------------------------------------------


class TestResourceReservations:
    def test_best_effort_no_request_no_limit(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=60.0)
        g = _graph(c)
        results = engine.analyze_resource_reservations(g)
        cpu_results = [r for r in results if r.resource == ResourceKind.CPU]
        assert len(cpu_results) == 1
        assert cpu_results[0].qos_class == "BestEffort"

    def test_guaranteed_qos(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=50.0, parameters={
            "cpu_request": 80.0,
            "cpu_limit": 80.0,
        })
        g = _graph(c)
        results = engine.analyze_resource_reservations(g)
        cpu_results = [r for r in results if r.resource == ResourceKind.CPU]
        assert cpu_results[0].qos_class == "Guaranteed"
        assert cpu_results[0].is_burstable is False

    def test_burstable_qos(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=60.0, parameters={
            "cpu_request": 40.0,
            "cpu_limit": 80.0,
        })
        g = _graph(c)
        results = engine.analyze_resource_reservations(g)
        cpu_results = [r for r in results if r.resource == ResourceKind.CPU]
        assert cpu_results[0].qos_class == "Burstable"
        assert cpu_results[0].is_burstable is True

    def test_overcommit_detection(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=90.0, parameters={
            "cpu_request": 50.0,
            "cpu_limit": 70.0,
        })
        g = _graph(c)
        results = engine.analyze_resource_reservations(g)
        cpu_results = [r for r in results if r.resource == ResourceKind.CPU]
        assert cpu_results[0].overcommit_ratio > 1.0
        assert cpu_results[0].severity == ContentionSeverity.CRITICAL

    def test_memory_reservation(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", memory=70.0, parameters={
            "memory_request": 50.0,
            "memory_limit": 80.0,
        })
        g = _graph(c)
        results = engine.analyze_resource_reservations(g)
        mem_results = [r for r in results if r.resource == ResourceKind.MEMORY]
        assert len(mem_results) == 1
        assert mem_results[0].qos_class == "Burstable"

    def test_zero_usage_skipped(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=0.0, memory=0.0)
        g = _graph(c)
        results = engine.analyze_resource_reservations(g)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# 13. Contention latency modeling
# ---------------------------------------------------------------------------


class TestContentionLatency:
    def test_no_contention_low_util(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=30.0, memory=40.0)
        g = _graph(c)
        results = engine.model_contention_latency(g)
        assert len(results) == 0

    def test_cpu_contention_latency(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=80.0, rtt_ms=5.0)
        g = _graph(c)
        results = engine.model_contention_latency(g)
        assert len(results) == 1
        assert results[0].primary_contention_source == ResourceKind.CPU
        assert results[0].contention_latency_ms > 0
        assert results[0].total_latency_ms > results[0].base_latency_ms

    def test_memory_dominant_latency(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=30.0, memory=95.0, rtt_ms=2.0)
        g = _graph(c)
        results = engine.model_contention_latency(g)
        assert len(results) == 1
        assert results[0].primary_contention_source == ResourceKind.MEMORY

    def test_disk_dominant_latency(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", disk=95.0, rtt_ms=1.0)
        g = _graph(c)
        results = engine.model_contention_latency(g)
        assert len(results) == 1
        assert results[0].primary_contention_source == ResourceKind.DISK_IO

    def test_network_dominant_latency(self):
        engine = ResourceContentionAnalyzer()
        # Use high max_connections and large connection_pool_size to ensure
        # network bandwidth contention dominates over lock contention
        c = _comp("c1", network_connections=900, max_connections=1000,
                   connection_pool_size=10000, rtt_ms=1.0)
        g = _graph(c)
        results = engine.model_contention_latency(g)
        assert len(results) == 1
        assert results[0].primary_contention_source == ResourceKind.NETWORK_BANDWIDTH

    def test_lock_dominant_latency(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", ctype=ComponentType.DATABASE,
                   network_connections=90, connection_pool_size=100, rtt_ms=1.0)
        g = _graph(c)
        results = engine.model_contention_latency(g)
        assert len(results) == 1
        assert results[0].primary_contention_source == ResourceKind.LOCKS

    def test_latency_severity_critical(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=99.0, rtt_ms=0.5)
        g = _graph(c)
        results = engine.model_contention_latency(g)
        assert results[0].latency_increase_percent > 0

    def test_high_increase_pct_recommendation(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=95.0, rtt_ms=1.0)
        g = _graph(c)
        results = engine.model_contention_latency(g)
        if results[0].contention_latency_ms > 20.0:
            assert len(results[0].recommendations) > 0


# ---------------------------------------------------------------------------
# 14. Full analysis pipeline
# ---------------------------------------------------------------------------


class TestFullAnalysis:
    def test_empty_graph(self):
        engine = ResourceContentionAnalyzer()
        g = _graph()
        report = engine.analyze(g)
        assert report.overall_severity == ContentionSeverity.NONE
        assert "0 components" in report.summary
        assert report.timestamp != ""

    def test_complex_graph(self):
        engine = ResourceContentionAnalyzer()
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER,
                    cpu=60.0, memory=50.0, host="h1")
        app = _comp("app1", ctype=ComponentType.APP_SERVER,
                     cpu=85.0, memory=80.0, host="h1")
        db = _comp("db1", ctype=ComponentType.DATABASE,
                    cpu=70.0, memory=92.0, disk=88.0,
                    network_connections=80, connection_pool_size=100,
                    host="h2")
        cache = _comp("cache1", ctype=ComponentType.CACHE,
                       memory=75.0, host="h2")
        g = _graph(lb, app, db, cache,
                   deps=[("lb", "app1"), ("app1", "db1"), ("app1", "cache1")])
        report = engine.analyze(g)
        assert report.overall_severity != ContentionSeverity.NONE
        assert "4 components" in report.summary
        assert len(report.memory_cascades) > 0

    def test_report_finding_count(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=90.0, memory=96.0, disk=85.0, host="h1")
        d = _comp("d1", cpu=70.0, host="h1")
        g = _graph(c, d)
        report = engine.analyze(g)
        # Should have at least some findings
        total = (
            len(report.noisy_neighbors) + len(report.hotspots)
            + len(report.lock_findings) + len(report.memory_cascades)
            + len(report.disk_saturations) + len(report.network_contentions)
            + len(report.cpu_throttling) + len(report.reservations)
            + len(report.latency_models)
        )
        assert total > 0
        assert str(total) in report.summary


# ---------------------------------------------------------------------------
# 15. Internal helper coverage
# ---------------------------------------------------------------------------


class TestInternalHelpers:
    def test_get_utilization_cpu(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", cpu=75.0)
        assert engine._get_utilization(c, ResourceKind.CPU) == 75.0

    def test_get_utilization_memory(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", memory=60.0)
        assert engine._get_utilization(c, ResourceKind.MEMORY) == 60.0

    def test_get_utilization_disk_io(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", disk=50.0)
        assert engine._get_utilization(c, ResourceKind.DISK_IO) == 50.0

    def test_get_utilization_network(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", network_connections=500, max_connections=1000)
        assert engine._get_utilization(c, ResourceKind.NETWORK_BANDWIDTH) == 50.0

    def test_get_utilization_network_zero_max(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", network_connections=100, max_connections=0)
        assert engine._get_utilization(c, ResourceKind.NETWORK_BANDWIDTH) == 0.0

    def test_get_utilization_file_descriptors(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", open_files=6553)
        util = engine._get_utilization(c, ResourceKind.FILE_DESCRIPTORS)
        assert 9.9 < util < 10.1  # ~10% of 65536

    def test_get_utilization_file_descriptors_zero(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", open_files=0)
        assert engine._get_utilization(c, ResourceKind.FILE_DESCRIPTORS) == 0.0

    def test_get_utilization_locks(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", network_connections=50, connection_pool_size=100)
        assert engine._get_utilization(c, ResourceKind.LOCKS) == 50.0

    def test_get_utilization_locks_zero_pool(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", network_connections=50, connection_pool_size=0)
        assert engine._get_utilization(c, ResourceKind.LOCKS) == 0.0

    def test_severity_from_score_boundaries(self):
        engine = ResourceContentionAnalyzer()
        assert engine._severity_from_score(0.0) == ContentionSeverity.NONE
        assert engine._severity_from_score(10.0) == ContentionSeverity.LOW
        assert engine._severity_from_score(20.0) == ContentionSeverity.MEDIUM
        assert engine._severity_from_score(40.0) == ContentionSeverity.HIGH
        assert engine._severity_from_score(60.0) == ContentionSeverity.CRITICAL
        assert engine._severity_from_score(100.0) == ContentionSeverity.CRITICAL

    def test_worst_severity(self):
        engine = ResourceContentionAnalyzer()
        assert engine._worst_severity([]) == ContentionSeverity.NONE
        assert engine._worst_severity(
            [ContentionSeverity.LOW, ContentionSeverity.HIGH]
        ) == ContentionSeverity.HIGH
        assert engine._worst_severity(
            [ContentionSeverity.MEDIUM, ContentionSeverity.CRITICAL]
        ) == ContentionSeverity.CRITICAL

    def test_determine_oom_action_thresholds(self):
        engine = ResourceContentionAnalyzer()
        assert engine._determine_oom_action(50.0) == OOMAction.NO_ACTION
        assert engine._determine_oom_action(78.0) == OOMAction.THROTTLE
        assert engine._determine_oom_action(90.0) == OOMAction.EVICT
        assert engine._determine_oom_action(96.0) == OOMAction.KILL_PROCESS

    def test_memory_severity_levels(self):
        engine = ResourceContentionAnalyzer()
        assert engine._memory_severity(60.0, 0) == ContentionSeverity.LOW
        assert engine._memory_severity(78.0, 0) == ContentionSeverity.MEDIUM
        assert engine._memory_severity(90.0, 0) == ContentionSeverity.HIGH
        assert engine._memory_severity(96.0, 3) == ContentionSeverity.CRITICAL

    def test_disk_severity_levels(self):
        engine = ResourceContentionAnalyzer()
        assert engine._disk_severity(50.0, 0) == ContentionSeverity.NONE
        assert engine._disk_severity(65.0, 0) == ContentionSeverity.LOW
        assert engine._disk_severity(82.0, 0) == ContentionSeverity.MEDIUM
        assert engine._disk_severity(85.0, 2) == ContentionSeverity.HIGH
        assert engine._disk_severity(96.0, 0) == ContentionSeverity.CRITICAL

    def test_reservation_severity_levels(self):
        engine = ResourceContentionAnalyzer()
        assert engine._reservation_severity(30.0, 0, 0, "BestEffort") == ContentionSeverity.LOW
        assert engine._reservation_severity(60.0, 0, 0, "BestEffort") == ContentionSeverity.HIGH
        assert engine._reservation_severity(90.0, 50, 70, "Burstable") == ContentionSeverity.CRITICAL
        assert engine._reservation_severity(60.0, 50, 80, "Burstable") == ContentionSeverity.MEDIUM
        assert engine._reservation_severity(40.0, 50, 80, "Guaranteed") == ContentionSeverity.NONE

    def test_latency_severity_levels(self):
        engine = ResourceContentionAnalyzer()
        assert engine._latency_severity(0.0, 0.0) == ContentionSeverity.NONE
        assert engine._latency_severity(5.0, 50.0) == ContentionSeverity.LOW
        assert engine._latency_severity(15.0, 150.0) == ContentionSeverity.MEDIUM
        assert engine._latency_severity(30.0, 250.0) == ContentionSeverity.HIGH
        assert engine._latency_severity(60.0, 600.0) == ContentionSeverity.CRITICAL

    def test_infer_isolation_parameter_namespace(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", parameters={"isolation": "namespace"})
        assert engine._infer_isolation(c) == IsolationMechanism.NAMESPACE

    def test_infer_isolation_parameter_dedicated(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", parameters={"isolation": "dedicated"})
        assert engine._infer_isolation(c) == IsolationMechanism.DEDICATED_HOST

    def test_infer_throttling_policy_unknown(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", parameters={"cpu_policy": "unknown"})
        assert engine._infer_throttling_policy(c) == ThrottlingPolicy.NONE

    def test_get_request_invalid_value(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", parameters={"cpu_request": "bad"})
        assert engine._get_request(c, ResourceKind.CPU) == 0.0

    def test_get_limit_invalid_value(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1", parameters={"cpu_limit": "bad"})
        assert engine._get_limit(c, ResourceKind.CPU) == 0.0

    def test_get_request_unsupported_resource(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1")
        assert engine._get_request(c, ResourceKind.DISK_IO) == 0.0

    def test_get_limit_unsupported_resource(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1")
        assert engine._get_limit(c, ResourceKind.DISK_IO) == 0.0

    def test_cascade_depth_no_paths(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1")
        g = _graph(c)
        assert engine._cascade_depth(g, "c1") == 0

    def test_cascade_depth_with_chain(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1")
        b = _comp("b1")
        c = _comp("c1")
        g = _graph(a, b, c, deps=[("b1", "a1"), ("c1", "b1")])
        depth = engine._cascade_depth(g, "a1")
        assert depth >= 1

    def test_lock_chain_depth_no_lock_deps(self):
        engine = ResourceContentionAnalyzer()
        app = _comp("app1", ctype=ComponentType.APP_SERVER)
        g = _graph(app)
        depth = engine._lock_chain_depth(g, "app1", set())
        assert depth == 1

    def test_lock_chain_depth_with_chain(self):
        engine = ResourceContentionAnalyzer()
        db1 = _comp("db1", ctype=ComponentType.DATABASE)
        db2 = _comp("db2", ctype=ComponentType.DATABASE)
        db3 = _comp("db3", ctype=ComponentType.STORAGE)
        g = _graph(db1, db2, db3, deps=[("db1", "db2"), ("db2", "db3")])
        depth = engine._lock_chain_depth(g, "db1", set())
        assert depth == 3

    def test_group_by_host(self):
        engine = ResourceContentionAnalyzer()
        a = _comp("a1", host="h1")
        b = _comp("b1", host="h1")
        c = _comp("c1", host="h2")
        d = _comp("d1")  # no host
        groups = engine._group_by_host([a, b, c, d])
        assert "h1" in groups
        assert len(groups["h1"]) == 2
        assert "h2" in groups
        assert len(groups["h2"]) == 1
        assert "" not in groups  # no host => excluded

    def test_find_co_located_no_host(self):
        engine = ResourceContentionAnalyzer()
        c = _comp("c1")
        g = _graph(c)
        assert engine._find_co_located(g, c) == []

    def test_severity_rank(self):
        engine = ResourceContentionAnalyzer()
        assert engine._severity_rank(ContentionSeverity.CRITICAL) == 0
        assert engine._severity_rank(ContentionSeverity.NONE) == 4
