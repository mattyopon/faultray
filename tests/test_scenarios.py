"""Tests for scenario generation logic."""

import pytest

from faultray.model.components import Capacity, Component, ComponentType, FailoverConfig
from faultray.simulator.scenarios import (
    DynamicScenario,
    Fault,
    FaultType,
    Scenario,
    generate_default_scenarios,
    generate_dynamic_scenarios,
    _categorize,
    _host_groups,
)


def _make_components(n: int) -> dict[str, Component]:
    """Create N app_server components for testing."""
    comps = {}
    for i in range(n):
        comp = Component(
            id=f"app-{i}",
            name=f"App Server {i}",
            type=ComponentType.APP_SERVER,
        )
        comps[comp.id] = comp
    return comps


def _find_scenario(scenarios, scenario_id: str):
    """Find a scenario by its ID."""
    for s in scenarios:
        if s.id == scenario_id:
            return s
    return None


def test_rolling_restart_keeps_at_least_one_up():
    """Rolling restart failure must not bring down ALL app servers."""
    for n in range(2, 8):
        comps = _make_components(n)
        ids = list(comps.keys())
        scenarios = generate_default_scenarios(ids, components=comps)
        sc = _find_scenario(scenarios, "rolling-restart-fail")
        assert sc is not None, f"rolling-restart-fail missing for {n} app servers"

        faulted = len(sc.faults)
        # Must bring down at least 1, but never ALL
        assert faulted >= 1, f"Should fault >= 1, got {faulted} for {n} servers"
        assert faulted < n, (
            f"Rolling restart should keep at least 1 server up, "
            f"but faulted {faulted}/{n}"
        )


def test_rolling_restart_two_servers():
    """With exactly 2 app servers, only 1 should go down."""
    comps = _make_components(2)
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "rolling-restart-fail")
    assert sc is not None
    assert len(sc.faults) == 1, f"Expected 1 fault for 2 servers, got {len(sc.faults)}"


def test_rolling_restart_three_servers():
    """With 3 app servers, maxUnavailable=25% -> max(1, 3//4)=1 server down."""
    comps = _make_components(3)
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "rolling-restart-fail")
    assert sc is not None
    assert len(sc.faults) == 1, f"Expected 1 fault for 3 servers (maxUnavailable=25%), got {len(sc.faults)}"


def test_no_rolling_restart_with_one_server():
    """With only 1 app server, rolling restart scenario should not be generated."""
    comps = _make_components(1)
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "rolling-restart-fail")
    assert sc is None, "Should not generate rolling restart for single server"


def test_cascading_timeout_scenarios():
    """Category 29: Components with timeout_seconds > 0 should generate cascading timeout scenarios."""
    comps = {
        "db-1": Component(
            id="db-1", name="Database 1", type=ComponentType.DATABASE,
            capacity=Capacity(timeout_seconds=60.0),
        ),
        "app-1": Component(
            id="app-1", name="App Server 1", type=ComponentType.APP_SERVER,
            capacity=Capacity(timeout_seconds=30.0),
        ),
    }
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)

    # Both components have timeout_seconds > 0, so both should get a cascading timeout scenario
    sc_db = _find_scenario(scenarios, "cascading-timeout-db-1")
    sc_app = _find_scenario(scenarios, "cascading-timeout-app-1")
    assert sc_db is not None, "cascading-timeout-db-1 should be generated"
    assert sc_app is not None, "cascading-timeout-app-1 should be generated"

    # Verify the fault is a LATENCY_SPIKE with multiplier 20
    assert len(sc_db.faults) == 1
    assert sc_db.faults[0].fault_type == FaultType.LATENCY_SPIKE
    assert sc_db.faults[0].parameters.get("multiplier") == 20


def test_sustained_degradation_scenarios():
    """Category 30: Each app_server should get a sustained degradation scenario."""
    comps = _make_components(3)
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)

    for i in range(3):
        sc = _find_scenario(scenarios, f"sustained-degradation-app-{i}")
        assert sc is not None, f"sustained-degradation-app-{i} should be generated"
        # Should have exactly 2 faults: CPU_SATURATION + MEMORY_EXHAUSTION
        assert len(sc.faults) == 2, f"Expected 2 faults, got {len(sc.faults)}"
        fault_types = {f.fault_type for f in sc.faults}
        assert FaultType.CPU_SATURATION in fault_types
        assert FaultType.MEMORY_EXHAUSTION in fault_types
        # Check severities
        for f in sc.faults:
            if f.fault_type == FaultType.CPU_SATURATION:
                assert f.severity == 0.8
            elif f.fault_type == FaultType.MEMORY_EXHAUSTION:
                assert f.severity == 0.7


# ---------------------------------------------------------------------------
# Scenario/Fault/DynamicScenario model validation
# ---------------------------------------------------------------------------


def test_scenario_negative_traffic_multiplier():
    """Scenario with negative traffic_multiplier should raise ValueError."""
    with pytest.raises(ValueError, match="traffic_multiplier must be >= 0"):
        Scenario(
            id="bad", name="Bad", description="Bad scenario",
            faults=[], traffic_multiplier=-1.0,
        )


def test_dynamic_scenario_zero_duration_rejected():
    """DynamicScenario with zero duration should raise ValueError."""
    from faultray.simulator.traffic import TrafficPattern  # resolve forward ref
    DynamicScenario.model_rebuild(_types_namespace={"TrafficPattern": TrafficPattern})
    with pytest.raises(ValueError, match="must be > 0"):
        DynamicScenario(
            id="bad", name="Bad", description="Bad scenario",
            faults=[], duration_seconds=0,
        )


def test_dynamic_scenario_zero_time_step_rejected():
    """DynamicScenario with zero time_step should raise ValueError."""
    from faultray.simulator.traffic import TrafficPattern  # resolve forward ref
    DynamicScenario.model_rebuild(_types_namespace={"TrafficPattern": TrafficPattern})
    with pytest.raises(ValueError, match="must be > 0"):
        DynamicScenario(
            id="bad", name="Bad", description="Bad scenario",
            faults=[], time_step_seconds=0,
        )


# ---------------------------------------------------------------------------
# _categorize and _host_groups helper functions
# ---------------------------------------------------------------------------


def test_categorize_with_components():
    """_categorize should sort components into correct category buckets."""
    comps = {
        "db-1": Component(id="db-1", name="DB", type=ComponentType.DATABASE),
        "cache-1": Component(id="cache-1", name="Cache", type=ComponentType.CACHE),
        "app-1": Component(id="app-1", name="App", type=ComponentType.APP_SERVER),
        "web-1": Component(id="web-1", name="Web", type=ComponentType.WEB_SERVER),
        "lb-1": Component(id="lb-1", name="LB", type=ComponentType.LOAD_BALANCER),
        "q-1": Component(id="q-1", name="Queue", type=ComponentType.QUEUE),
        "s-1": Component(id="s-1", name="Storage", type=ComponentType.STORAGE),
        "dns-1": Component(id="dns-1", name="DNS", type=ComponentType.DNS),
        "custom-1": Component(id="custom-1", name="Custom", type=ComponentType.CUSTOM),
    }
    ids = list(comps.keys())
    cats = _categorize(comps, ids)
    assert "db-1" in cats["databases"]
    assert "cache-1" in cats["caches"]
    assert "app-1" in cats["app_servers"]
    assert "web-1" in cats["web_servers"]
    assert "lb-1" in cats["load_balancers"]
    assert "q-1" in cats["queues"]
    assert "s-1" in cats["storage"]
    assert "dns-1" in cats["dns"]
    assert "custom-1" in cats["other"]


def test_categorize_without_components():
    """_categorize without components dict should put all ids in 'other'."""
    ids = ["a", "b", "c"]
    cats = _categorize(None, ids)
    assert cats["other"] == ids
    assert cats["databases"] == []


def test_host_groups_with_hosts():
    """_host_groups should group components by host."""
    comps = {
        "app-1": Component(id="app-1", name="App1", type=ComponentType.APP_SERVER, host="host-a"),
        "app-2": Component(id="app-2", name="App2", type=ComponentType.APP_SERVER, host="host-a"),
        "db-1": Component(id="db-1", name="DB1", type=ComponentType.DATABASE, host="host-b"),
    }
    groups = _host_groups(comps)
    assert "host-a" in groups
    assert len(groups["host-a"]) == 2
    assert "host-b" in groups
    assert len(groups["host-b"]) == 1


def test_host_groups_none():
    """_host_groups with None should return empty dict."""
    groups = _host_groups(None)
    assert groups == {}


# ---------------------------------------------------------------------------
# generate_default_scenarios: full coverage of all categories
# ---------------------------------------------------------------------------


def _mixed_components() -> dict[str, Component]:
    """Create a set of mixed component types for comprehensive scenario generation."""
    return {
        "db-1": Component(
            id="db-1", name="Primary DB", type=ComponentType.DATABASE,
            replicas=2, host="host-a",
            capacity=Capacity(timeout_seconds=30.0),
        ),
        "cache-1": Component(
            id="cache-1", name="Redis", type=ComponentType.CACHE,
            replicas=1, host="host-a",
        ),
        "app-1": Component(
            id="app-1", name="App Server 1", type=ComponentType.APP_SERVER,
            replicas=1, host="host-b",
            capacity=Capacity(timeout_seconds=10.0),
        ),
        "app-2": Component(
            id="app-2", name="App Server 2", type=ComponentType.APP_SERVER,
            replicas=1, host="host-c",
            capacity=Capacity(timeout_seconds=10.0),
        ),
        "lb-1": Component(
            id="lb-1", name="ALB", type=ComponentType.LOAD_BALANCER,
            replicas=1,
        ),
        "lb-2": Component(
            id="lb-2", name="NLB", type=ComponentType.LOAD_BALANCER,
            replicas=1,
        ),
        "q-1": Component(
            id="q-1", name="SQS", type=ComponentType.QUEUE,
            replicas=1,
        ),
        "s-1": Component(
            id="s-1", name="S3", type=ComponentType.STORAGE,
            replicas=1,
        ),
        "dns-1": Component(
            id="dns-1", name="Route53", type=ComponentType.DNS,
            replicas=1,
        ),
        "ext-1": Component(
            id="ext-1", name="Stripe API", type=ComponentType.EXTERNAL_API,
            replicas=1,
        ),
    }


def test_category_single_failures():
    """Category 1: Every component should have a single failure scenario."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    for cid in ids:
        sc = _find_scenario(scenarios, f"single-failure-{cid}")
        assert sc is not None, f"Missing single-failure for {cid}"


def test_category_traffic_spikes():
    """Category 8: Graduated traffic spike scenarios."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    for mult in [1.5, 2, 3, 5, 10]:
        sc = _find_scenario(scenarios, f"traffic-{mult}x")
        assert sc is not None, f"Missing traffic-{mult}x"
        assert sc.traffic_multiplier == mult


def test_category_pairwise_compound():
    """Category 9: Pairwise compound failures."""
    comps = {"a": Component(id="a", name="A", type=ComponentType.APP_SERVER),
             "b": Component(id="b", name="B", type=ComponentType.APP_SERVER),
             "c": Component(id="c", name="C", type=ComponentType.APP_SERVER)}
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "pair-a-b")
    assert sc is not None
    assert len(sc.faults) == 2


def test_category_triple_failures():
    """Category 10: Triple failures for <= 10 components."""
    comps = {"a": Component(id="a", name="A", type=ComponentType.APP_SERVER),
             "b": Component(id="b", name="B", type=ComponentType.APP_SERVER),
             "c": Component(id="c", name="C", type=ComponentType.APP_SERVER)}
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "triple-a-b-c")
    assert sc is not None
    assert len(sc.faults) == 3


def test_category_cache_stampede():
    """Category 11: Cache stampede scenarios."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "stampede-cache-1-2.0x")
    assert sc is not None
    assert sc.traffic_multiplier == 2.0


def test_category_component_down_traffic():
    """Category 12: Component down + traffic spike."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "down-traffic-db-1-2.0x")
    assert sc is not None
    assert sc.traffic_multiplier == 2.0


def test_category_zone_failure():
    """Category 13: Zone failure (components on same host)."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "zone-failure-host-a")
    assert sc is not None
    assert len(sc.faults) >= 2


def test_category_db_scenarios():
    """Category 14: DB-specific scenarios."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    assert _find_scenario(scenarios, "log-explosion-db-1") is not None
    assert _find_scenario(scenarios, "replication-lag-db-1") is not None
    assert _find_scenario(scenarios, "connection-storm-db-1") is not None
    assert _find_scenario(scenarios, "lock-contention-db-1") is not None


def test_category_queue_scenarios():
    """Category 15: Queue-specific scenarios."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    assert _find_scenario(scenarios, "queue-backpressure-q-1") is not None
    assert _find_scenario(scenarios, "poison-message-q-1") is not None


def test_category_lb_scenarios():
    """Category 16: LB-specific scenarios."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    assert _find_scenario(scenarios, "healthcheck-fail-lb-1") is not None
    assert _find_scenario(scenarios, "tls-expiry-lb-1") is not None
    assert _find_scenario(scenarios, "config-reload-lb-1") is not None


def test_category_app_scenarios():
    """Category 17: App server-specific scenarios."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    assert _find_scenario(scenarios, "memory-leak-app-1") is not None
    assert _find_scenario(scenarios, "thread-exhaustion-app-1") is not None
    assert _find_scenario(scenarios, "gc-pause-app-1") is not None
    assert _find_scenario(scenarios, "bad-deploy-app-1") is not None


def test_category_cache_scenarios():
    """Category 18: Cache-specific scenarios."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    assert _find_scenario(scenarios, "eviction-storm-cache-1") is not None
    assert _find_scenario(scenarios, "cache-split-brain-cache-1") is not None


def test_category_dns_scenarios():
    """Category 19: DNS-specific scenarios."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    assert _find_scenario(scenarios, "dns-failure-dns-1") is not None
    assert _find_scenario(scenarios, "dns-latency-dns-1") is not None


def test_category_storage_scenarios():
    """Category 20: Storage-specific scenarios."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    assert _find_scenario(scenarios, "io-throttle-s-1") is not None
    assert _find_scenario(scenarios, "data-corruption-s-1") is not None


def test_category_cascading_timeout():
    """Category 21: Cascading timeout chain requires both DB and App."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "cascading-timeout")
    assert sc is not None


def test_category_total_meltdown():
    """Category 22: Total meltdown requires >= 3 components."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "total-meltdown")
    assert sc is not None
    assert len(sc.faults) == len(ids)


def test_category_cascading_meltdown():
    """Category 22b: Cascading meltdown should target high-criticality components."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "cascading-meltdown")
    assert sc is not None
    # Root causes should be 2-3 components
    assert 2 <= len(sc.faults) <= 3


def test_category_noisy_neighbor():
    """Category 23: Noisy neighbor for app servers."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    assert _find_scenario(scenarios, "noisy-neighbor-app-1") is not None


def test_category_slow_db_peak():
    """Category 24: Slow DB at peak traffic."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "slow-db-peak-db-1")
    assert sc is not None
    assert sc.traffic_multiplier == 3.0


def test_category_resource_exhaustion():
    """Category 28: Full resource exhaustion (CPU + memory)."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "resource-exhaustion-app-1")
    assert sc is not None
    assert len(sc.faults) == 2


def test_category_failover_testing():
    """Category 31: DB failover testing with replicas > 1."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "primary-failover-db-1")
    assert sc is not None


def test_category_black_friday():
    """Category 32: Black Friday simulation."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "black-friday")
    assert sc is not None
    assert sc.traffic_multiplier == 10.0


def test_category_external_api():
    """Category 26: External API failure scenarios."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    assert _find_scenario(scenarios, "external-timeout-ext-1") is not None
    assert _find_scenario(scenarios, "external-down-ext-1") is not None


def test_category_network_partition_tiers():
    """Category 27: Network partition between tiers."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    # App <-> DB partition
    assert _find_scenario(scenarios, "partition-app-db") is not None
    # App <-> Cache partition
    assert _find_scenario(scenarios, "partition-app-cache") is not None
    # LB <-> App partition
    assert _find_scenario(scenarios, "partition-lb-app") is not None


def test_category_per_lb_partition():
    """Category 27: Per-LB partition with multiple LBs."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    # With 2 LBs, there should be per-LB partition scenarios
    assert _find_scenario(scenarios, "partition-lb-1-app") is not None
    assert _find_scenario(scenarios, "partition-lb-2-app") is not None


def test_no_triple_failures_above_10_components():
    """Category 10: No triple failures when > 10 components."""
    # Create 11 app servers
    comps = {}
    for i in range(11):
        comps[f"app-{i}"] = Component(
            id=f"app-{i}", name=f"App{i}", type=ComponentType.APP_SERVER,
        )
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    # Should not have any triple failure scenarios
    triple_scenarios = [s for s in scenarios if s.id.startswith("triple-")]
    assert len(triple_scenarios) == 0


def test_no_components_no_crash():
    """generate_default_scenarios with empty list should not crash."""
    scenarios = generate_default_scenarios([], components=None)
    assert isinstance(scenarios, list)


def test_generate_without_components_dict():
    """generate_default_scenarios without components dict should still work."""
    ids = ["comp-1", "comp-2", "comp-3"]
    scenarios = generate_default_scenarios(ids, components=None)
    assert len(scenarios) > 0
    # Pool targets should use all component_ids when no components dict
    pool_scenarios = [s for s in scenarios if s.id.startswith("pool-exhaustion-")]
    assert len(pool_scenarios) == 3


# ---------------------------------------------------------------------------
# generate_dynamic_scenarios
# ---------------------------------------------------------------------------


def test_dynamic_scenarios_basic():
    """Dynamic scenarios should generate at least the DDoS + flash crowd scenarios."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)
    assert len(scenarios) > 0
    assert all(isinstance(s, DynamicScenario) for s in scenarios)


def test_dynamic_scenarios_ddos_volumetric():
    """Dynamic scenario 1: DDoS volumetric should be present."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)
    sc = next((s for s in scenarios if s.id == "dynamic-ddos-volumetric"), None)
    assert sc is not None
    assert sc.traffic_pattern is not None


def test_dynamic_scenarios_ddos_slowloris():
    """Dynamic scenario 2: DDoS slowloris with affected components."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)
    sc = next((s for s in scenarios if s.id == "dynamic-ddos-slowloris"), None)
    assert sc is not None
    assert sc.traffic_pattern is not None
    # Should have affected_components set
    assert len(sc.traffic_pattern.affected_components) > 0


def test_dynamic_scenarios_flash_crowd():
    """Dynamic scenario 3: Flash crowd."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)
    sc = next((s for s in scenarios if s.id == "dynamic-flash-crowd"), None)
    assert sc is not None


def test_dynamic_scenarios_viral_db_failure():
    """Dynamic scenario 4: Viral event + DB failure (requires DB)."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)
    sc = next((s for s in scenarios if s.id == "dynamic-viral-db-failure"), None)
    assert sc is not None
    assert len(sc.faults) == 1


def test_dynamic_scenarios_diurnal_cache_failure():
    """Dynamic scenario 5: Diurnal cycle + cache failure."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)
    sc = next((s for s in scenarios if s.id == "dynamic-diurnal-cache-failure"), None)
    assert sc is not None


def test_dynamic_scenarios_spike_during_deploy():
    """Dynamic scenario 6: Spike during deployment."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)
    sc = next((s for s in scenarios if s.id == "dynamic-spike-during-deploy"), None)
    assert sc is not None


def test_dynamic_scenarios_ddos_net_partition():
    """Dynamic scenario 7: DDoS + network partition."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)
    sc = next((s for s in scenarios if s.id == "dynamic-ddos-net-partition"), None)
    assert sc is not None


def test_dynamic_scenarios_sustained_high_load():
    """Dynamic scenario 8: Sustained high load + memory exhaustion."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)
    sc = next((s for s in scenarios if s.id == "dynamic-sustained-high-load"), None)
    assert sc is not None


def test_dynamic_scenarios_flash_cache_stampede():
    """Dynamic scenario 9: Flash crowd + cache stampede."""
    comps = _mixed_components()
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)
    sc = next((s for s in scenarios if s.id == "dynamic-flash-cache-stampede"), None)
    assert sc is not None
