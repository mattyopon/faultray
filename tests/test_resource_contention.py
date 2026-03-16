"""Tests for faultray.simulator.resource_contention module.

Targets 100% coverage with 140+ tests covering all enums, models,
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
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.resource_contention import (
    ContentionResult,
    ContentionType,
    FairSchedule,
    FairScheduleEntry,
    NoisyNeighborResult,
    PriorityInversion,
    ResourceContentionEngine,
    ResourceLimit,
    ResourceType,
    SpikeResult,
    StarvationRisk,
    _CONTENTION_SEVERITY_MULTIPLIER,
    _RESOURCE_BASE_IMPACT,
    _RESOURCE_UTILIZATION_FIELD,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str | None = None,
    ctype: ComponentType = ComponentType.APP_SERVER,
    cpu: float = 0.0,
    memory: float = 0.0,
    disk: float = 0.0,
    network_connections: int = 0,
    max_connections: int = 1000,
    max_rps: int = 5000,
    connection_pool_size: int = 100,
    open_files: int = 0,
    host: str = "",
    replicas: int = 1,
    autoscaling: bool = False,
    parameters: dict | None = None,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        host=host,
        replicas=replicas,
        capacity=Capacity(
            max_connections=max_connections,
            max_rps=max_rps,
            connection_pool_size=connection_pool_size,
        ),
        metrics=ResourceMetrics(
            cpu_percent=cpu,
            memory_percent=memory,
            disk_percent=disk,
            network_connections=network_connections,
            open_files=open_files,
        ),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        parameters=parameters or {},
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


class TestResourceTypeEnum:
    def test_all_values_exist(self):
        expected = {
            "cpu", "memory", "disk_io", "network_bandwidth",
            "gpu", "connection_pool", "file_descriptors", "thread_pool",
        }
        assert {e.value for e in ResourceType} == expected

    def test_string_enum(self):
        assert ResourceType.CPU == "cpu"
        assert isinstance(ResourceType.MEMORY, str)

    def test_iteration(self):
        assert len(list(ResourceType)) == 8

    def test_from_value(self):
        assert ResourceType("disk_io") is ResourceType.DISK_IO


class TestContentionTypeEnum:
    def test_all_values_exist(self):
        expected = {
            "direct_competition", "priority_inversion", "thundering_herd",
            "lock_contention", "cache_thrash", "bandwidth_saturation",
        }
        assert {e.value for e in ContentionType} == expected

    def test_string_enum(self):
        assert ContentionType.THUNDERING_HERD == "thundering_herd"

    def test_iteration(self):
        assert len(list(ContentionType)) == 6

    def test_from_value(self):
        assert ContentionType("lock_contention") is ContentionType.LOCK_CONTENTION


# ---------------------------------------------------------------------------
# 2. Lookup-table coverage
# ---------------------------------------------------------------------------


class TestLookupTables:
    def test_resource_base_impact_keys(self):
        for rt in ResourceType:
            assert rt in _RESOURCE_BASE_IMPACT

    def test_contention_severity_multiplier_keys(self):
        for ct in ContentionType:
            assert ct in _CONTENTION_SEVERITY_MULTIPLIER

    def test_resource_utilization_field_subset(self):
        assert ResourceType.CPU in _RESOURCE_UTILIZATION_FIELD
        assert ResourceType.MEMORY in _RESOURCE_UTILIZATION_FIELD

    def test_base_impact_positive(self):
        for v in _RESOURCE_BASE_IMPACT.values():
            assert v > 0

    def test_multiplier_positive(self):
        for v in _CONTENTION_SEVERITY_MULTIPLIER.values():
            assert v > 0


# ---------------------------------------------------------------------------
# 3. Pydantic model construction
# ---------------------------------------------------------------------------


class TestContentionResultModel:
    def test_defaults(self):
        r = ContentionResult(
            resource_type=ResourceType.CPU,
            contention_type=ContentionType.DIRECT_COMPETITION,
        )
        assert r.severity == "low"
        assert r.performance_impact_percent == 0.0
        assert r.competing_components == []
        assert r.starvation_risk == []
        assert r.recommendations == []

    def test_full_construction(self):
        r = ContentionResult(
            resource_type=ResourceType.MEMORY,
            contention_type=ContentionType.THUNDERING_HERD,
            competing_components=["a", "b"],
            severity="high",
            performance_impact_percent=55.5,
            starvation_risk=["a"],
            recommendations=["do something"],
        )
        assert r.resource_type == ResourceType.MEMORY
        assert r.contention_type == ContentionType.THUNDERING_HERD
        assert len(r.competing_components) == 2


class TestSpikeResultModel:
    def test_defaults(self):
        r = SpikeResult(component_id="x", resource=ResourceType.CPU)
        assert r.multiplier == 1.0
        assert r.affected_components == []
        assert r.severity == "low"

    def test_full(self):
        r = SpikeResult(
            component_id="x",
            resource=ResourceType.DISK_IO,
            multiplier=3.0,
            original_utilization=40.0,
            spiked_utilization=100.0,
            affected_components=["y"],
            severity="critical",
            performance_impact_percent=80.0,
            recommendations=["scale up"],
        )
        assert r.spiked_utilization == 100.0


class TestPriorityInversionModel:
    def test_defaults(self):
        r = PriorityInversion(
            high_priority_component="web",
            low_priority_component="db",
            shared_resource=ResourceType.CONNECTION_POOL,
        )
        assert r.blocking_severity == "low"
        assert r.description == ""
        assert r.recommendations == []


class TestResourceLimitModel:
    def test_defaults(self):
        r = ResourceLimit(component_id="x", resource=ResourceType.CPU)
        assert r.current_usage == 0.0
        assert r.recommended_limit == 0.0


class TestNoisyNeighborResultModel:
    def test_defaults(self):
        r = NoisyNeighborResult(aggressor_id="a", resource=ResourceType.CPU)
        assert r.impact_severity == "none"
        assert r.victim_ids == []

    def test_full(self):
        r = NoisyNeighborResult(
            aggressor_id="a",
            resource=ResourceType.MEMORY,
            victim_ids=["b", "c"],
            impact_severity="high",
            performance_degradation_percent=45.0,
            recommendations=["isolate"],
        )
        assert len(r.victim_ids) == 2


class TestFairScheduleModels:
    def test_entry_defaults(self):
        e = FairScheduleEntry(component_id="x")
        assert e.weight == 1.0
        assert e.cpu_share == 0.0

    def test_schedule_defaults(self):
        s = FairSchedule()
        assert s.entries == []
        assert s.total_weight == 0.0
        assert s.fairness_index == 0.0


class TestStarvationRiskModel:
    def test_defaults(self):
        r = StarvationRisk(component_id="x", resource=ResourceType.CPU)
        assert r.risk_level == "low"
        assert r.recommendations == []


# ---------------------------------------------------------------------------
# 4. Engine – detect_contention
# ---------------------------------------------------------------------------


class TestDetectContention:
    def test_empty_graph(self):
        engine = ResourceContentionEngine()
        g = _graph()
        assert engine.detect_contention(g) == []

    def test_single_component(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a"))
        assert engine.detect_contention(g) == []

    def test_same_host_direct_competition(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="host1", cpu=70.0),
            _comp("b", host="host1", cpu=80.0),
        )
        results = engine.detect_contention(g)
        dc = [r for r in results if r.contention_type == ContentionType.DIRECT_COMPETITION]
        assert len(dc) > 0
        assert "a" in dc[0].competing_components
        assert "b" in dc[0].competing_components

    def test_direct_competition_multiple_resources(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", cpu=50.0, memory=60.0, disk=70.0),
            _comp("b", host="h", cpu=40.0, memory=50.0, disk=60.0),
        )
        results = engine.detect_contention(g)
        dc = [r for r in results if r.contention_type == ContentionType.DIRECT_COMPETITION]
        resources_found = {r.resource_type for r in dc}
        assert ResourceType.CPU in resources_found
        assert ResourceType.MEMORY in resources_found
        assert ResourceType.DISK_IO in resources_found

    def test_no_competition_different_hosts(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h1", cpu=90.0),
            _comp("b", host="h2", cpu=90.0),
        )
        results = engine.detect_contention(g)
        dc = [r for r in results if r.contention_type == ContentionType.DIRECT_COMPETITION]
        assert dc == []

    def test_thundering_herd(self):
        engine = ResourceContentionEngine()
        target = _comp("db", ctype=ComponentType.DATABASE, cpu=50.0)
        clients = [_comp(f"app{i}") for i in range(5)]
        deps = [(f"app{i}", "db") for i in range(5)]
        g = _graph(target, *clients, deps=deps)
        results = engine.detect_contention(g)
        th = [r for r in results if r.contention_type == ContentionType.THUNDERING_HERD]
        assert len(th) == 1
        assert len(th[0].competing_components) == 5

    def test_thundering_herd_below_threshold(self):
        engine = ResourceContentionEngine()
        target = _comp("db", ctype=ComponentType.DATABASE)
        clients = [_comp(f"app{i}") for i in range(2)]
        deps = [(f"app{i}", "db") for i in range(2)]
        g = _graph(target, *clients, deps=deps)
        results = engine.detect_contention(g)
        th = [r for r in results if r.contention_type == ContentionType.THUNDERING_HERD]
        assert th == []

    def test_cache_thrash(self):
        engine = ResourceContentionEngine()
        cache = _comp("redis", ctype=ComponentType.CACHE, memory=75.0)
        apps = [_comp(f"app{i}") for i in range(3)]
        deps = [(f"app{i}", "redis") for i in range(3)]
        g = _graph(cache, *apps, deps=deps)
        results = engine.detect_contention(g)
        ct = [r for r in results if r.contention_type == ContentionType.CACHE_THRASH]
        assert len(ct) == 1
        assert ct[0].resource_type == ResourceType.MEMORY

    def test_cache_thrash_single_dependent_skipped(self):
        engine = ResourceContentionEngine()
        cache = _comp("redis", ctype=ComponentType.CACHE, memory=90.0)
        app = _comp("app1")
        g = _graph(cache, app, deps=[("app1", "redis")])
        results = engine.detect_contention(g)
        ct = [r for r in results if r.contention_type == ContentionType.CACHE_THRASH]
        assert ct == []

    def test_bandwidth_saturation(self):
        engine = ResourceContentionEngine()
        lb = _comp(
            "lb", ctype=ComponentType.LOAD_BALANCER,
            network_connections=800, max_connections=1000,
        )
        g = _graph(lb, _comp("app1"), deps=[("lb", "app1")])
        results = engine.detect_contention(g)
        bs = [r for r in results if r.contention_type == ContentionType.BANDWIDTH_SATURATION]
        assert len(bs) == 1

    def test_bandwidth_saturation_low_usage_skipped(self):
        engine = ResourceContentionEngine()
        lb = _comp(
            "lb", ctype=ComponentType.LOAD_BALANCER,
            network_connections=100, max_connections=1000,
        )
        g = _graph(lb, _comp("app1"))
        results = engine.detect_contention(g)
        bs = [r for r in results if r.contention_type == ContentionType.BANDWIDTH_SATURATION]
        assert bs == []

    def test_lock_contention(self):
        engine = ResourceContentionEngine()
        db = _comp(
            "db", ctype=ComponentType.DATABASE,
            network_connections=80, connection_pool_size=100,
        )
        apps = [_comp(f"app{i}") for i in range(3)]
        deps = [(f"app{i}", "db") for i in range(3)]
        g = _graph(db, *apps, deps=deps)
        results = engine.detect_contention(g)
        lc = [r for r in results if r.contention_type == ContentionType.LOCK_CONTENTION]
        assert len(lc) == 1

    def test_lock_contention_storage(self):
        engine = ResourceContentionEngine()
        storage = _comp("s3", ctype=ComponentType.STORAGE)
        apps = [_comp(f"w{i}") for i in range(3)]
        deps = [(f"w{i}", "s3") for i in range(3)]
        g = _graph(storage, *apps, deps=deps)
        results = engine.detect_contention(g)
        lc = [r for r in results if r.contention_type == ContentionType.LOCK_CONTENTION]
        assert len(lc) == 1

    def test_lock_contention_single_dependent_skipped(self):
        engine = ResourceContentionEngine()
        db = _comp("db", ctype=ComponentType.DATABASE)
        g = _graph(db, _comp("app1"), deps=[("app1", "db")])
        results = engine.detect_contention(g)
        lc = [r for r in results if r.contention_type == ContentionType.LOCK_CONTENTION]
        assert lc == []

    def test_results_sorted_by_severity(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", cpu=90.0, memory=90.0),
            _comp("b", host="h", cpu=90.0, memory=90.0),
        )
        results = engine.detect_contention(g)
        severities = [r.severity for r in results]
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
        assert severities == sorted(severities, key=lambda s: order.get(s, 5))

    def test_starvation_risk_flagged_in_direct_competition(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", cpu=95.0),
            _comp("b", host="h", cpu=85.0),
        )
        results = engine.detect_contention(g)
        dc = [r for r in results if r.contention_type == ContentionType.DIRECT_COMPETITION
              and r.resource_type == ResourceType.CPU]
        assert len(dc) == 1
        assert "a" in dc[0].starvation_risk
        assert "b" in dc[0].starvation_risk

    def test_thundering_herd_high_util_starvation(self):
        engine = ResourceContentionEngine()
        db = _comp("db", ctype=ComponentType.DATABASE, cpu=75.0)
        apps = [_comp(f"a{i}") for i in range(4)]
        deps = [(f"a{i}", "db") for i in range(4)]
        g = _graph(db, *apps, deps=deps)
        results = engine.detect_contention(g)
        th = [r for r in results if r.contention_type == ContentionType.THUNDERING_HERD]
        assert len(th) == 1
        assert "db" in th[0].starvation_risk

    def test_host_without_competition_no_results(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h"),
            _comp("b", host="h"),
        )
        results = engine.detect_contention(g)
        dc = [r for r in results if r.contention_type == ContentionType.DIRECT_COMPETITION]
        assert dc == []

    def test_no_host_no_direct_competition(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", cpu=90.0),
            _comp("b", cpu=90.0),
        )
        results = engine.detect_contention(g)
        dc = [r for r in results if r.contention_type == ContentionType.DIRECT_COMPETITION]
        assert dc == []

    def test_bandwidth_saturation_starvation_risk(self):
        engine = ResourceContentionEngine()
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER,
                   network_connections=900, max_connections=1000)
        g = _graph(lb, _comp("app"))
        results = engine.detect_contention(g)
        bs = [r for r in results if r.contention_type == ContentionType.BANDWIDTH_SATURATION]
        assert len(bs) == 1
        assert "lb" in bs[0].starvation_risk

    def test_cache_thrash_starvation_risk_high_memory(self):
        engine = ResourceContentionEngine()
        cache = _comp("c", ctype=ComponentType.CACHE, memory=90.0)
        apps = [_comp(f"a{i}") for i in range(3)]
        deps = [(f"a{i}", "c") for i in range(3)]
        g = _graph(cache, *apps, deps=deps)
        results = engine.detect_contention(g)
        ct = [r for r in results if r.contention_type == ContentionType.CACHE_THRASH]
        assert len(ct) == 1
        assert "c" in ct[0].starvation_risk

    def test_lock_contention_starvation_risk(self):
        engine = ResourceContentionEngine()
        db = _comp("db", ctype=ComponentType.DATABASE,
                   network_connections=80, connection_pool_size=100)
        apps = [_comp(f"a{i}") for i in range(3)]
        deps = [(f"a{i}", "db") for i in range(3)]
        g = _graph(db, *apps, deps=deps)
        results = engine.detect_contention(g)
        lc = [r for r in results if r.contention_type == ContentionType.LOCK_CONTENTION]
        assert len(lc) == 1
        assert "db" in lc[0].starvation_risk


# ---------------------------------------------------------------------------
# 5. Engine – simulate_resource_spike
# ---------------------------------------------------------------------------


class TestSimulateResourceSpike:
    def test_unknown_component(self):
        engine = ResourceContentionEngine()
        g = _graph()
        result = engine.simulate_resource_spike(g, "nope", ResourceType.CPU, 2.0)
        assert result.component_id == "nope"
        assert result.multiplier == 2.0
        assert result.affected_components == []

    def test_basic_spike(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=40.0))
        result = engine.simulate_resource_spike(g, "a", ResourceType.CPU, 3.0)
        assert result.original_utilization == 40.0
        assert result.spiked_utilization > 40.0
        assert result.multiplier == 3.0

    def test_spike_capped_at_100(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=60.0))
        result = engine.simulate_resource_spike(g, "a", ResourceType.CPU, 10.0)
        assert result.spiked_utilization == 100.0

    def test_spike_affects_dependents(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("db", cpu=50.0),
            _comp("app"),
            deps=[("app", "db")],
        )
        result = engine.simulate_resource_spike(g, "db", ResourceType.CPU, 3.0)
        assert "app" in result.affected_components

    def test_spike_affects_same_host(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h1", cpu=50.0),
            _comp("b", host="h1"),
        )
        result = engine.simulate_resource_spike(g, "a", ResourceType.CPU, 2.0)
        assert "b" in result.affected_components

    def test_spike_no_duplicate_affected(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h1", cpu=50.0),
            _comp("b", host="h1"),
            deps=[("b", "a")],
        )
        result = engine.simulate_resource_spike(g, "a", ResourceType.CPU, 2.0)
        assert result.affected_components.count("b") == 1

    def test_spike_large_multiplier_recommendation(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=50.0))
        result = engine.simulate_resource_spike(g, "a", ResourceType.CPU, 6.0)
        assert any("5x" in r for r in result.recommendations)

    def test_spike_high_utilization_recommendation(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=50.0))
        result = engine.simulate_resource_spike(g, "a", ResourceType.CPU, 3.0)
        assert result.spiked_utilization > 90
        assert any("autoscaling" in r.lower() for r in result.recommendations)

    def test_spike_with_memory(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", memory=60.0))
        result = engine.simulate_resource_spike(g, "a", ResourceType.MEMORY, 2.0)
        assert result.original_utilization == 60.0
        assert result.spiked_utilization == 100.0

    def test_spike_affected_components_sorted(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("target", host="h", cpu=50.0),
            _comp("c", host="h"),
            _comp("b", host="h"),
            _comp("a", host="h"),
        )
        result = engine.simulate_resource_spike(g, "target", ResourceType.CPU, 2.0)
        assert result.affected_components == sorted(result.affected_components)

    def test_spike_severity(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=90.0))
        result = engine.simulate_resource_spike(g, "a", ResourceType.CPU, 5.0)
        assert result.severity in ("critical", "high", "medium", "low", "none")


# ---------------------------------------------------------------------------
# 6. Engine – find_priority_inversions
# ---------------------------------------------------------------------------


class TestFindPriorityInversions:
    def test_empty_graph(self):
        engine = ResourceContentionEngine()
        g = _graph()
        assert engine.find_priority_inversions(g) == []

    def test_single_component(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a"))
        assert engine.find_priority_inversions(g) == []

    def test_inversion_detected(self):
        engine = ResourceContentionEngine()
        web = _comp("web", ctype=ComponentType.WEB_SERVER)
        db = _comp("db", ctype=ComponentType.DATABASE, cpu=75.0)
        g = _graph(web, db, deps=[("web", "db")])
        inversions = engine.find_priority_inversions(g)
        assert len(inversions) == 1
        assert inversions[0].high_priority_component == "web"
        assert inversions[0].low_priority_component == "db"

    def test_no_inversion_when_dep_low_util(self):
        engine = ResourceContentionEngine()
        web = _comp("web", ctype=ComponentType.WEB_SERVER)
        db = _comp("db", ctype=ComponentType.DATABASE, cpu=10.0)
        g = _graph(web, db, deps=[("web", "db")])
        assert engine.find_priority_inversions(g) == []

    def test_no_inversion_same_priority(self):
        engine = ResourceContentionEngine()
        a1 = _comp("a1", ctype=ComponentType.APP_SERVER)
        a2 = _comp("a2", ctype=ComponentType.APP_SERVER, cpu=80.0)
        g = _graph(a1, a2, deps=[("a1", "a2")])
        # Same priority type => no inversion (priority gap = 0)
        assert engine.find_priority_inversions(g) == []

    def test_inversion_severity_critical(self):
        engine = ResourceContentionEngine()
        dns = _comp("dns", ctype=ComponentType.DNS)
        storage = _comp("s3", ctype=ComponentType.STORAGE, cpu=90.0)
        g = _graph(dns, storage, deps=[("dns", "s3")])
        inversions = engine.find_priority_inversions(g)
        assert len(inversions) == 1
        assert inversions[0].blocking_severity == "critical"

    def test_inversion_recommendations(self):
        engine = ResourceContentionEngine()
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER)
        db = _comp("db", ctype=ComponentType.DATABASE, cpu=70.0)
        g = _graph(lb, db, deps=[("lb", "db")])
        inversions = engine.find_priority_inversions(g)
        assert len(inversions) == 1
        assert len(inversions[0].recommendations) >= 1

    def test_inversions_sorted_by_severity(self):
        engine = ResourceContentionEngine()
        dns = _comp("dns", ctype=ComponentType.DNS)
        web = _comp("web", ctype=ComponentType.WEB_SERVER)
        db = _comp("db", ctype=ComponentType.DATABASE, cpu=85.0)
        storage = _comp("s3", ctype=ComponentType.STORAGE, cpu=90.0)
        g = _graph(dns, web, db, storage,
                   deps=[("dns", "s3"), ("web", "db")])
        inversions = engine.find_priority_inversions(g)
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        severities = [order.get(inv.blocking_severity, 4) for inv in inversions]
        assert severities == sorted(severities)

    def test_multiple_inversions(self):
        engine = ResourceContentionEngine()
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER)
        web = _comp("web", ctype=ComponentType.WEB_SERVER)
        db = _comp("db", ctype=ComponentType.DATABASE, cpu=70.0)
        g = _graph(lb, web, db, deps=[("lb", "db"), ("web", "db")])
        inversions = engine.find_priority_inversions(g)
        assert len(inversions) == 2


# ---------------------------------------------------------------------------
# 7. Engine – recommend_resource_limits
# ---------------------------------------------------------------------------


class TestRecommendResourceLimits:
    def test_empty_graph(self):
        engine = ResourceContentionEngine()
        g = _graph()
        assert engine.recommend_resource_limits(g) == []

    def test_no_usage(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a"))
        assert engine.recommend_resource_limits(g) == []

    def test_cpu_usage_generates_limit(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=60.0))
        limits = engine.recommend_resource_limits(g)
        cpu_limits = [l for l in limits if l.resource == ResourceType.CPU]
        assert len(cpu_limits) == 1
        assert cpu_limits[0].current_usage == 60.0
        assert cpu_limits[0].recommended_limit > 60.0

    def test_multiple_resources(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=50.0, memory=70.0, disk=30.0))
        limits = engine.recommend_resource_limits(g)
        resources = {l.resource for l in limits}
        assert ResourceType.CPU in resources
        assert ResourceType.MEMORY in resources
        assert ResourceType.DISK_IO in resources

    def test_sorted_by_usage_descending(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=30.0, memory=90.0))
        limits = engine.recommend_resource_limits(g)
        usages = [l.current_usage for l in limits]
        assert usages == sorted(usages, reverse=True)

    def test_high_usage_reason(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=85.0))
        limits = engine.recommend_resource_limits(g)
        cpu_limits = [l for l in limits if l.resource == ResourceType.CPU]
        assert "critically high" in cpu_limits[0].reason

    def test_moderate_usage_reason(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=65.0))
        limits = engine.recommend_resource_limits(g)
        cpu_limits = [l for l in limits if l.resource == ResourceType.CPU]
        assert "elevated" in cpu_limits[0].reason

    def test_low_usage_reason(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=20.0))
        limits = engine.recommend_resource_limits(g)
        cpu_limits = [l for l in limits if l.resource == ResourceType.CPU]
        assert "headroom" in cpu_limits[0].reason

    def test_database_headroom_higher(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE, cpu=40.0))
        limits = engine.recommend_resource_limits(g)
        cpu_limits = [l for l in limits if l.resource == ResourceType.CPU]
        assert cpu_limits[0].headroom_percent == 40.0

    def test_autoscaling_headroom_lower(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=40.0, autoscaling=True))
        limits = engine.recommend_resource_limits(g)
        cpu_limits = [l for l in limits if l.resource == ResourceType.CPU]
        assert cpu_limits[0].headroom_percent == 20.0

    def test_network_bandwidth_limit(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", network_connections=500, max_connections=1000))
        limits = engine.recommend_resource_limits(g)
        net = [l for l in limits if l.resource == ResourceType.NETWORK_BANDWIDTH]
        assert len(net) == 1
        assert net[0].current_usage == 50.0

    def test_connection_pool_limit(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", network_connections=50, connection_pool_size=100))
        limits = engine.recommend_resource_limits(g)
        conn = [l for l in limits if l.resource == ResourceType.CONNECTION_POOL]
        assert len(conn) == 1

    def test_open_files_limit(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", open_files=10000))
        limits = engine.recommend_resource_limits(g)
        fd = [l for l in limits if l.resource == ResourceType.FILE_DESCRIPTORS]
        assert len(fd) == 1

    def test_gpu_limit_via_parameters(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", parameters={"gpu_percent": 70.0}))
        limits = engine.recommend_resource_limits(g)
        gpu = [l for l in limits if l.resource == ResourceType.GPU]
        assert len(gpu) == 1
        assert gpu[0].current_usage == 70.0

    def test_thread_pool_limit_via_parameters(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", parameters={"thread_pool_percent": 50.0}))
        limits = engine.recommend_resource_limits(g)
        tp = [l for l in limits if l.resource == ResourceType.THREAD_POOL]
        assert len(tp) == 1
        assert tp[0].current_usage == 50.0


# ---------------------------------------------------------------------------
# 8. Engine – simulate_noisy_neighbor
# ---------------------------------------------------------------------------


class TestSimulateNoisyNeighbor:
    def test_unknown_aggressor(self):
        engine = ResourceContentionEngine()
        g = _graph()
        result = engine.simulate_noisy_neighbor(g, "nope", ResourceType.CPU)
        assert result.impact_severity == "none"
        assert result.victim_ids == []

    def test_no_victims(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=90.0))
        result = engine.simulate_noisy_neighbor(g, "a", ResourceType.CPU)
        assert result.impact_severity == "none"
        assert any("isolation" in r.lower() for r in result.recommendations)

    def test_same_host_victims(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h1", cpu=80.0),
            _comp("b", host="h1"),
            _comp("c", host="h1"),
        )
        result = engine.simulate_noisy_neighbor(g, "a", ResourceType.CPU)
        assert "b" in result.victim_ids
        assert "c" in result.victim_ids
        assert result.impact_severity != "none"

    def test_dependent_victims(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("db", cpu=80.0),
            _comp("app"),
            deps=[("app", "db")],
        )
        result = engine.simulate_noisy_neighbor(g, "db", ResourceType.CPU)
        assert "app" in result.victim_ids

    def test_cpu_recommendation(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", cpu=80.0),
            _comp("b", host="h"),
        )
        result = engine.simulate_noisy_neighbor(g, "a", ResourceType.CPU)
        assert any("cgroup" in r.lower() for r in result.recommendations)

    def test_memory_recommendation(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", memory=80.0),
            _comp("b", host="h"),
        )
        result = engine.simulate_noisy_neighbor(g, "a", ResourceType.MEMORY)
        assert any("memory limit" in r.lower() for r in result.recommendations)

    def test_disk_io_recommendation(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", disk=80.0),
            _comp("b", host="h"),
        )
        result = engine.simulate_noisy_neighbor(g, "a", ResourceType.DISK_IO)
        assert any("throttling" in r.lower() for r in result.recommendations)

    def test_network_bandwidth_recommendation(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", network_connections=800, max_connections=1000),
            _comp("b", host="h"),
        )
        result = engine.simulate_noisy_neighbor(g, "a", ResourceType.NETWORK_BANDWIDTH)
        assert any("throttling" in r.lower() for r in result.recommendations)

    def test_connection_pool_recommendation(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", network_connections=90, connection_pool_size=100),
            _comp("b", host="h"),
        )
        result = engine.simulate_noisy_neighbor(g, "a", ResourceType.CONNECTION_POOL)
        assert any("connection pool" in r.lower() for r in result.recommendations)

    def test_victims_sorted(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("x", host="h", cpu=80.0),
            _comp("c", host="h"),
            _comp("a", host="h"),
            _comp("b", host="h"),
        )
        result = engine.simulate_noisy_neighbor(g, "x", ResourceType.CPU)
        assert result.victim_ids == sorted(result.victim_ids)

    def test_degradation_capped_at_100(self):
        engine = ResourceContentionEngine()
        comps = [_comp(f"n{i}", host="h", cpu=99.0) for i in range(20)]
        comps[0] = _comp("aggressor", host="h", cpu=99.0)
        g = _graph(*comps)
        result = engine.simulate_noisy_neighbor(g, "aggressor", ResourceType.CPU)
        assert result.performance_degradation_percent <= 100.0

    def test_high_severity_isolation_recommendation(self):
        engine = ResourceContentionEngine()
        comps = [_comp(f"n{i}", host="h") for i in range(10)]
        comps[0] = _comp("agg", host="h", cpu=99.0)
        g = _graph(*comps)
        result = engine.simulate_noisy_neighbor(g, "agg", ResourceType.CPU)
        if result.impact_severity in ("critical", "high"):
            assert any("isolate" in r.lower() for r in result.recommendations)

    def test_no_host_no_victims(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", cpu=90.0),
            _comp("b", cpu=50.0),
        )
        result = engine.simulate_noisy_neighbor(g, "a", ResourceType.CPU)
        assert result.impact_severity == "none"


# ---------------------------------------------------------------------------
# 9. Engine – calculate_fair_scheduling
# ---------------------------------------------------------------------------


class TestCalculateFairScheduling:
    def test_empty_graph(self):
        engine = ResourceContentionEngine()
        g = _graph()
        schedule = engine.calculate_fair_scheduling(g)
        assert schedule.entries == []
        assert schedule.fairness_index == 1.0

    def test_single_component(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a"))
        schedule = engine.calculate_fair_scheduling(g)
        assert len(schedule.entries) == 1
        assert schedule.entries[0].cpu_share == 100.0
        assert schedule.fairness_index == 1.0

    def test_equal_weight_components(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", ctype=ComponentType.APP_SERVER),
            _comp("b", ctype=ComponentType.APP_SERVER),
        )
        schedule = engine.calculate_fair_scheduling(g)
        assert len(schedule.entries) == 2
        shares = {e.component_id: e.cpu_share for e in schedule.entries}
        # Should be roughly equal
        assert abs(shares["a"] - shares["b"]) < 1.0
        assert schedule.fairness_index > 0.99

    def test_different_weight_components(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("lb", ctype=ComponentType.LOAD_BALANCER),
            _comp("storage", ctype=ComponentType.STORAGE),
        )
        schedule = engine.calculate_fair_scheduling(g)
        shares = {e.component_id: e.cpu_share for e in schedule.entries}
        assert shares["lb"] > shares["storage"]

    def test_total_weight_positive(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a"), _comp("b"))
        schedule = engine.calculate_fair_scheduling(g)
        assert schedule.total_weight > 0

    def test_shares_sum_to_100(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        schedule = engine.calculate_fair_scheduling(g)
        total_cpu = sum(e.cpu_share for e in schedule.entries)
        assert abs(total_cpu - 100.0) < 0.1

    def test_entries_sorted_by_weight_desc(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("lb", ctype=ComponentType.LOAD_BALANCER),
            _comp("app", ctype=ComponentType.APP_SERVER),
            _comp("storage", ctype=ComponentType.STORAGE),
        )
        schedule = engine.calculate_fair_scheduling(g)
        weights = [e.weight for e in schedule.entries]
        assert weights == sorted(weights, reverse=True)

    def test_replica_reduces_weight(self):
        engine = ResourceContentionEngine()
        g1 = _graph(_comp("a", replicas=1))
        g2 = _graph(_comp("a", replicas=3))
        s1 = engine.calculate_fair_scheduling(g1)
        s2 = engine.calculate_fair_scheduling(g2)
        assert s1.entries[0].weight > s2.entries[0].weight

    def test_high_utilization_increases_weight(self):
        engine = ResourceContentionEngine()
        g1 = _graph(_comp("a", cpu=10.0))
        g2 = _graph(_comp("a", cpu=90.0))
        s1 = engine.calculate_fair_scheduling(g1)
        s2 = engine.calculate_fair_scheduling(g2)
        assert s2.entries[0].weight > s1.entries[0].weight

    def test_fairness_index_range(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", ctype=ComponentType.LOAD_BALANCER),
            _comp("b", ctype=ComponentType.STORAGE),
        )
        schedule = engine.calculate_fair_scheduling(g)
        assert 0.0 <= schedule.fairness_index <= 1.0

    def test_memory_and_io_shares_match_cpu(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a"))
        schedule = engine.calculate_fair_scheduling(g)
        e = schedule.entries[0]
        assert e.memory_share == e.cpu_share
        assert e.io_share == e.cpu_share


# ---------------------------------------------------------------------------
# 10. Engine – detect_starvation_risks
# ---------------------------------------------------------------------------


class TestDetectStarvationRisks:
    def test_empty_graph(self):
        engine = ResourceContentionEngine()
        g = _graph()
        assert engine.detect_starvation_risks(g) == []

    def test_no_usage(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a"))
        assert engine.detect_starvation_risks(g) == []

    def test_critical_starvation(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", cpu=95.0),
            _comp("b", host="h", cpu=90.0),
            _comp("c", host="h", cpu=85.0),
            _comp("d", host="h"),
        )
        risks = engine.detect_starvation_risks(g)
        critical = [r for r in risks if r.risk_level == "critical"]
        assert len(critical) > 0

    def test_high_starvation(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", cpu=85.0),
            _comp("b", host="h", cpu=80.0),
            _comp("c", host="h"),
        )
        risks = engine.detect_starvation_risks(g)
        high_or_above = [r for r in risks if r.risk_level in ("critical", "high")]
        assert len(high_or_above) > 0

    def test_medium_starvation(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", cpu=75.0),
            _comp("b", host="h"),
        )
        risks = engine.detect_starvation_risks(g)
        med = [r for r in risks if r.risk_level == "medium"]
        assert len(med) >= 1

    def test_low_starvation(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", cpu=65.0),
            _comp("b", host="h"),
        )
        risks = engine.detect_starvation_risks(g)
        low = [r for r in risks if r.risk_level == "low"]
        assert len(low) >= 1

    def test_no_risk_when_healthy(self):
        engine = ResourceContentionEngine()
        g = _graph(_comp("a", cpu=20.0))
        risks = engine.detect_starvation_risks(g)
        assert risks == []

    def test_sorted_by_risk_level(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", cpu=95.0),
            _comp("b", host="h", cpu=75.0),
            _comp("c", host="h", cpu=65.0),
            _comp("d", host="h"),
        )
        risks = engine.detect_starvation_risks(g)
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        levels = [order.get(r.risk_level, 4) for r in risks]
        assert levels == sorted(levels)

    def test_recommendations_for_critical(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", cpu=95.0),
            _comp("b", host="h", cpu=90.0),
            _comp("c", host="h"),
            _comp("d", host="h"),
        )
        risks = engine.detect_starvation_risks(g)
        critical = [r for r in risks if r.risk_level == "critical"]
        for r in critical:
            assert len(r.recommendations) >= 2

    def test_multiple_resource_types(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", cpu=92.0, memory=88.0),
            _comp("b", host="h"),
            _comp("c", host="h"),
            _comp("d", host="h"),
        )
        risks = engine.detect_starvation_risks(g)
        resources = {r.resource for r in risks}
        assert len(resources) >= 2

    def test_dependency_counts_as_competitor(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", cpu=85.0),
            _comp("b"),
            deps=[("a", "b")],
        )
        risks = engine.detect_starvation_risks(g)
        a_risks = [r for r in risks if r.component_id == "a"]
        if a_risks:
            assert a_risks[0].competing_component_count >= 1

    def test_disk_io_starvation(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", disk=93.0),
            _comp("b", host="h"),
            _comp("c", host="h"),
            _comp("d", host="h"),
        )
        risks = engine.detect_starvation_risks(g)
        disk_risks = [r for r in risks if r.resource == ResourceType.DISK_IO]
        assert len(disk_risks) > 0

    def test_connection_pool_starvation(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("db", host="h", network_connections=95, connection_pool_size=100),
            _comp("app1", host="h"),
            _comp("app2", host="h"),
            _comp("app3", host="h"),
        )
        risks = engine.detect_starvation_risks(g)
        conn_risks = [r for r in risks if r.resource == ResourceType.CONNECTION_POOL]
        assert len(conn_risks) > 0

    def test_medium_starvation_recommendation(self):
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="h", cpu=75.0),
            _comp("b", host="h"),
        )
        risks = engine.detect_starvation_risks(g)
        med = [r for r in risks if r.risk_level == "medium"]
        assert len(med) >= 1
        for r in med:
            assert any("monitor" in rec.lower() for rec in r.recommendations)


# ---------------------------------------------------------------------------
# 11. Private helper coverage
# ---------------------------------------------------------------------------


class TestGetResourceUtilization:
    def test_cpu(self):
        engine = ResourceContentionEngine()
        c = _comp("a", cpu=55.0)
        assert engine._get_resource_utilization(c, ResourceType.CPU) == 55.0

    def test_memory(self):
        engine = ResourceContentionEngine()
        c = _comp("a", memory=70.0)
        assert engine._get_resource_utilization(c, ResourceType.MEMORY) == 70.0

    def test_disk_io(self):
        engine = ResourceContentionEngine()
        c = _comp("a", disk=45.0)
        assert engine._get_resource_utilization(c, ResourceType.DISK_IO) == 45.0

    def test_network_bandwidth(self):
        engine = ResourceContentionEngine()
        c = _comp("a", network_connections=300, max_connections=1000)
        assert engine._get_resource_utilization(c, ResourceType.NETWORK_BANDWIDTH) == 30.0

    def test_network_bandwidth_zero_max(self):
        engine = ResourceContentionEngine()
        c = _comp("a", max_connections=0)
        assert engine._get_resource_utilization(c, ResourceType.NETWORK_BANDWIDTH) == 0.0

    def test_connection_pool(self):
        engine = ResourceContentionEngine()
        c = _comp("a", network_connections=50, connection_pool_size=200)
        assert engine._get_resource_utilization(c, ResourceType.CONNECTION_POOL) == 25.0

    def test_connection_pool_zero_size(self):
        engine = ResourceContentionEngine()
        c = _comp("a", connection_pool_size=0)
        assert engine._get_resource_utilization(c, ResourceType.CONNECTION_POOL) == 0.0

    def test_file_descriptors(self):
        engine = ResourceContentionEngine()
        c = _comp("a", open_files=6553)
        result = engine._get_resource_utilization(c, ResourceType.FILE_DESCRIPTORS)
        assert 9.9 < result < 10.1

    def test_file_descriptors_zero(self):
        engine = ResourceContentionEngine()
        c = _comp("a", open_files=0)
        assert engine._get_resource_utilization(c, ResourceType.FILE_DESCRIPTORS) == 0.0

    def test_file_descriptors_capped(self):
        engine = ResourceContentionEngine()
        c = _comp("a", open_files=999999)
        assert engine._get_resource_utilization(c, ResourceType.FILE_DESCRIPTORS) == 100.0

    def test_gpu_from_parameters(self):
        engine = ResourceContentionEngine()
        c = _comp("a", parameters={"gpu_percent": 80.0})
        assert engine._get_resource_utilization(c, ResourceType.GPU) == 80.0

    def test_gpu_missing_parameter(self):
        engine = ResourceContentionEngine()
        c = _comp("a")
        assert engine._get_resource_utilization(c, ResourceType.GPU) == 0.0

    def test_thread_pool_from_parameters(self):
        engine = ResourceContentionEngine()
        c = _comp("a", parameters={"thread_pool_percent": 60.0})
        assert engine._get_resource_utilization(c, ResourceType.THREAD_POOL) == 60.0

    def test_thread_pool_missing(self):
        engine = ResourceContentionEngine()
        c = _comp("a")
        assert engine._get_resource_utilization(c, ResourceType.THREAD_POOL) == 0.0


class TestComponentPriority:
    def test_dns_highest(self):
        engine = ResourceContentionEngine()
        c = _comp("d", ctype=ComponentType.DNS)
        assert engine._component_priority(c) == 10

    def test_custom_lowest(self):
        engine = ResourceContentionEngine()
        c = _comp("x", ctype=ComponentType.CUSTOM)
        assert engine._component_priority(c) == 1

    def test_app_server_middle(self):
        engine = ResourceContentionEngine()
        c = _comp("a", ctype=ComponentType.APP_SERVER)
        assert engine._component_priority(c) == 6

    def test_all_types_have_priority(self):
        engine = ResourceContentionEngine()
        for ct in ComponentType:
            c = _comp("x", ctype=ct)
            assert engine._component_priority(c) >= 1


class TestPrimaryResourceForType:
    def test_database(self):
        assert ResourceContentionEngine._primary_resource_for_type(
            ComponentType.DATABASE
        ) == ResourceType.CONNECTION_POOL

    def test_cache(self):
        assert ResourceContentionEngine._primary_resource_for_type(
            ComponentType.CACHE
        ) == ResourceType.MEMORY

    def test_queue(self):
        assert ResourceContentionEngine._primary_resource_for_type(
            ComponentType.QUEUE
        ) == ResourceType.DISK_IO

    def test_web_server(self):
        assert ResourceContentionEngine._primary_resource_for_type(
            ComponentType.WEB_SERVER
        ) == ResourceType.THREAD_POOL

    def test_load_balancer(self):
        assert ResourceContentionEngine._primary_resource_for_type(
            ComponentType.LOAD_BALANCER
        ) == ResourceType.NETWORK_BANDWIDTH


class TestSeverityFromImpact:
    def test_critical(self):
        assert ResourceContentionEngine._severity_from_impact(61) == "critical"

    def test_high(self):
        assert ResourceContentionEngine._severity_from_impact(41) == "high"

    def test_medium(self):
        assert ResourceContentionEngine._severity_from_impact(21) == "medium"

    def test_low(self):
        assert ResourceContentionEngine._severity_from_impact(5) == "low"

    def test_none(self):
        assert ResourceContentionEngine._severity_from_impact(0) == "none"

    def test_boundary_60(self):
        assert ResourceContentionEngine._severity_from_impact(60) == "high"

    def test_boundary_40(self):
        assert ResourceContentionEngine._severity_from_impact(40) == "medium"

    def test_boundary_20(self):
        assert ResourceContentionEngine._severity_from_impact(20) == "low"


class TestInversionSeverity:
    def test_critical(self):
        assert ResourceContentionEngine._inversion_severity(10, 2, 85) == "critical"

    def test_high(self):
        assert ResourceContentionEngine._inversion_severity(8, 3, 75) == "high"

    def test_medium_from_gap(self):
        assert ResourceContentionEngine._inversion_severity(5, 3, 50) == "medium"

    def test_medium_from_util(self):
        assert ResourceContentionEngine._inversion_severity(3, 2, 65) == "medium"

    def test_low(self):
        assert ResourceContentionEngine._inversion_severity(3, 2, 55) == "low"


class TestSchedulingWeight:
    def test_load_balancer_weight(self):
        c = _comp("lb", ctype=ComponentType.LOAD_BALANCER)
        w = ResourceContentionEngine._scheduling_weight(c)
        assert w > 1.0

    def test_storage_base_weight(self):
        c = _comp("s", ctype=ComponentType.STORAGE)
        w = ResourceContentionEngine._scheduling_weight(c)
        assert w == 1.0

    def test_utilization_increases_weight(self):
        c1 = _comp("a", cpu=0.0)
        c2 = _comp("a", cpu=80.0)
        w1 = ResourceContentionEngine._scheduling_weight(c1)
        w2 = ResourceContentionEngine._scheduling_weight(c2)
        assert w2 > w1

    def test_replicas_decrease_weight(self):
        c1 = _comp("a", replicas=1)
        c2 = _comp("a", replicas=4)
        w1 = ResourceContentionEngine._scheduling_weight(c1)
        w2 = ResourceContentionEngine._scheduling_weight(c2)
        assert w1 > w2


class TestCountCompetitors:
    def test_no_competitors(self):
        engine = ResourceContentionEngine()
        c = _comp("a")
        g = _graph(c)
        assert engine._count_competitors(g, c) == 0

    def test_same_host_competitor(self):
        engine = ResourceContentionEngine()
        a = _comp("a", host="h")
        b = _comp("b", host="h")
        g = _graph(a, b)
        assert engine._count_competitors(g, a) == 1

    def test_dependency_competitor(self):
        engine = ResourceContentionEngine()
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b, deps=[("a", "b")])
        assert engine._count_competitors(g, a) >= 1

    def test_dependent_competitor(self):
        engine = ResourceContentionEngine()
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b, deps=[("b", "a")])
        assert engine._count_competitors(g, a) >= 1

    def test_no_double_counting(self):
        engine = ResourceContentionEngine()
        a = _comp("a", host="h")
        b = _comp("b", host="h")
        g = _graph(a, b, deps=[("b", "a")])
        assert engine._count_competitors(g, a) == 1


class TestStarvationRiskLevel:
    def test_critical(self):
        assert ResourceContentionEngine._starvation_risk_level(93, 7, 4) == "critical"

    def test_high(self):
        assert ResourceContentionEngine._starvation_risk_level(85, 15, 2) == "high"

    def test_medium(self):
        assert ResourceContentionEngine._starvation_risk_level(75, 25, 1) == "medium"

    def test_low(self):
        assert ResourceContentionEngine._starvation_risk_level(65, 35, 1) == "low"

    def test_none(self):
        assert ResourceContentionEngine._starvation_risk_level(50, 50, 0) == "none"

    def test_none_plenty_capacity(self):
        assert ResourceContentionEngine._starvation_risk_level(40, 60, 1) == "none"


# ---------------------------------------------------------------------------
# 12. Integration / complex scenarios
# ---------------------------------------------------------------------------


class TestComplexScenarios:
    def test_full_stack_contention(self):
        """Full stack: LB -> Web -> App -> Cache -> DB — all on same host."""
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("lb", ctype=ComponentType.LOAD_BALANCER, host="h", cpu=70.0,
                  network_connections=700, max_connections=1000),
            _comp("web", ctype=ComponentType.WEB_SERVER, host="h", cpu=80.0),
            _comp("app", ctype=ComponentType.APP_SERVER, host="h", cpu=75.0),
            _comp("cache", ctype=ComponentType.CACHE, host="h", memory=85.0),
            _comp("db", ctype=ComponentType.DATABASE, host="h", cpu=90.0,
                  network_connections=90, connection_pool_size=100),
            deps=[
                ("lb", "web"), ("web", "app"),
                ("app", "cache"), ("app", "db"),
            ],
        )
        results = engine.detect_contention(g)
        types_found = {r.contention_type for r in results}
        assert ContentionType.DIRECT_COMPETITION in types_found

    def test_microservice_fan_in(self):
        """Multiple microservices depend on a single database."""
        engine = ResourceContentionEngine()
        db = _comp("db", ctype=ComponentType.DATABASE, cpu=65.0,
                   network_connections=70, connection_pool_size=100)
        services = [_comp(f"svc{i}", cpu=40.0) for i in range(6)]
        deps = [(f"svc{i}", "db") for i in range(6)]
        g = _graph(db, *services, deps=deps)

        results = engine.detect_contention(g)
        th = [r for r in results if r.contention_type == ContentionType.THUNDERING_HERD]
        assert len(th) >= 1

        inversions = engine.find_priority_inversions(g)
        assert len(inversions) >= 1

        starvation = engine.detect_starvation_risks(g)
        assert len(starvation) >= 1

    def test_noisy_neighbor_cascading(self):
        """A noisy neighbor causes cascading effects through dependencies."""
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("noisy", host="h", cpu=95.0, memory=90.0),
            _comp("victim1", host="h"),
            _comp("victim2", host="h"),
            deps=[("victim1", "noisy")],
        )
        result = engine.simulate_noisy_neighbor(g, "noisy", ResourceType.CPU)
        assert len(result.victim_ids) == 2

    def test_spike_on_shared_db(self):
        """Spike on a shared database affects all downstream services."""
        engine = ResourceContentionEngine()
        db = _comp("db", ctype=ComponentType.DATABASE, host="dbhost", cpu=60.0)
        apps = [_comp(f"app{i}") for i in range(3)]
        deps = [(f"app{i}", "db") for i in range(3)]
        g = _graph(db, *apps, deps=deps)

        result = engine.simulate_resource_spike(g, "db", ResourceType.CPU, 3.0)
        assert len(result.affected_components) == 3

    def test_fair_scheduling_diverse_components(self):
        """Fair scheduling across diverse component types."""
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("lb", ctype=ComponentType.LOAD_BALANCER, cpu=50.0),
            _comp("web", ctype=ComponentType.WEB_SERVER, cpu=60.0),
            _comp("app", ctype=ComponentType.APP_SERVER, cpu=40.0),
            _comp("db", ctype=ComponentType.DATABASE, cpu=70.0),
            _comp("cache", ctype=ComponentType.CACHE, cpu=30.0),
        )
        schedule = engine.calculate_fair_scheduling(g)
        assert len(schedule.entries) == 5
        total = sum(e.cpu_share for e in schedule.entries)
        assert abs(total - 100.0) < 0.5

    def test_all_methods_on_graph_with_no_edges(self):
        """All methods work on a graph with components but no dependencies."""
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", cpu=50.0, host="h"),
            _comp("b", cpu=60.0, host="h"),
        )
        assert isinstance(engine.detect_contention(g), list)
        assert isinstance(engine.simulate_resource_spike(g, "a", ResourceType.CPU, 2.0), SpikeResult)
        assert isinstance(engine.find_priority_inversions(g), list)
        assert isinstance(engine.recommend_resource_limits(g), list)
        assert isinstance(engine.simulate_noisy_neighbor(g, "a", ResourceType.CPU), NoisyNeighborResult)
        assert isinstance(engine.calculate_fair_scheduling(g), FairSchedule)
        assert isinstance(engine.detect_starvation_risks(g), list)

    def test_thundering_herd_with_5_plus_dependents_recommendation(self):
        """Thundering herd with >= 5 dependents gets queue recommendation."""
        engine = ResourceContentionEngine()
        db = _comp("db", ctype=ComponentType.DATABASE)
        apps = [_comp(f"a{i}") for i in range(6)]
        deps = [(f"a{i}", "db") for i in range(6)]
        g = _graph(db, *apps, deps=deps)
        results = engine.detect_contention(g)
        th = [r for r in results if r.contention_type == ContentionType.THUNDERING_HERD]
        assert len(th) == 1
        assert any("queue" in r.lower() or "rate limiter" in r.lower()
                    for r in th[0].recommendations)

    def test_gpu_contention_via_parameters(self):
        """GPU utilization detected through parameters."""
        engine = ResourceContentionEngine()
        g = _graph(_comp("gpu-node", parameters={"gpu_percent": 85.0}))
        limits = engine.recommend_resource_limits(g)
        gpu_limits = [l for l in limits if l.resource == ResourceType.GPU]
        assert len(gpu_limits) == 1
        assert gpu_limits[0].current_usage == 85.0

    def test_spike_zero_utilization(self):
        """Spike on zero utilization component."""
        engine = ResourceContentionEngine()
        g = _graph(_comp("a"))
        result = engine.simulate_resource_spike(g, "a", ResourceType.CPU, 5.0)
        assert result.original_utilization == 0.0
        assert result.spiked_utilization == 0.0

    def test_direct_competition_critical_severity_recommendation(self):
        """Direct competition with very high utilization triggers separation recommendation."""
        engine = ResourceContentionEngine()
        g = _graph(
            _comp("a", host="rack1", cpu=95.0),
            _comp("b", host="rack1", cpu=95.0),
            _comp("c", host="rack1", cpu=95.0),
        )
        results = engine.detect_contention(g)
        dc = [r for r in results if r.contention_type == ContentionType.DIRECT_COMPETITION
              and r.resource_type == ResourceType.CPU]
        assert len(dc) == 1
        assert dc[0].severity in ("critical", "high", "medium")
        assert len(dc[0].recommendations) > 0

    def test_direct_competition_high_severity_separate_recommendation(self):
        """Many co-located high-CPU components trigger high/critical + separation advice."""
        engine = ResourceContentionEngine()
        comps = [_comp(f"n{i}", host="dense", cpu=98.0) for i in range(8)]
        g = _graph(*comps)
        results = engine.detect_contention(g)
        dc = [r for r in results if r.contention_type == ContentionType.DIRECT_COMPETITION
              and r.resource_type == ResourceType.CPU]
        assert len(dc) == 1
        assert dc[0].severity in ("critical", "high")
        assert any("separate" in r.lower() for r in dc[0].recommendations)
