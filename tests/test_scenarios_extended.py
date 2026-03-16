"""Extended tests for scenario generation — targeting uncovered lines."""

import pytest

from faultray.model.components import Component, ComponentType
from faultray.simulator.scenarios import (
    DynamicScenario,
    Fault,
    FaultType,
    Scenario,
    _categorize,
    _host_groups,
    generate_default_scenarios,
    generate_dynamic_scenarios,
)
from faultray.simulator.traffic import TrafficPattern  # noqa: F401 — needed for DynamicScenario

# Rebuild DynamicScenario so the forward reference to TrafficPattern resolves.
DynamicScenario.model_rebuild()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_typed_components() -> dict[str, Component]:
    """Create a diverse set of components covering all types."""
    comps = {}
    for ctype, cid, name, host in [
        (ComponentType.DATABASE, "db-1", "Primary DB", "host-a"),
        (ComponentType.DATABASE, "db-2", "Replica DB", "host-a"),
        (ComponentType.CACHE, "cache-1", "Redis", "host-b"),
        (ComponentType.APP_SERVER, "app-1", "API Server", "host-c"),
        (ComponentType.APP_SERVER, "app-2", "Worker", "host-c"),
        (ComponentType.WEB_SERVER, "web-1", "Nginx", "host-d"),
        (ComponentType.LOAD_BALANCER, "lb-1", "HAProxy", "host-e"),
        (ComponentType.QUEUE, "queue-1", "RabbitMQ", "host-f"),
        (ComponentType.STORAGE, "store-1", "S3 Storage", "host-g"),
        (ComponentType.DNS, "dns-1", "CoreDNS", "host-h"),
    ]:
        comp = Component(
            id=cid, name=name, type=ctype, host=host, replicas=2,
        )
        comps[comp.id] = comp
    return comps


def _find_scenario(scenarios, scenario_id: str):
    """Find a scenario by its ID."""
    for s in scenarios:
        if s.id == scenario_id:
            return s
    return None


def _find_scenarios_prefix(scenarios, prefix: str):
    """Find all scenarios whose ID starts with prefix."""
    return [s for s in scenarios if s.id.startswith(prefix)]


# ---------------------------------------------------------------------------
# Scenario validation — line 49 (traffic_multiplier < 0)
# ---------------------------------------------------------------------------


def test_scenario_negative_multiplier():
    """traffic_multiplier must be >= 0."""
    with pytest.raises(ValueError, match="must be >= 0"):
        Scenario(
            id="bad", name="Bad", description="Bad",
            faults=[], traffic_multiplier=-1.0,
        )


# ---------------------------------------------------------------------------
# DynamicScenario validation — lines 67-69
# ---------------------------------------------------------------------------


def test_dynamic_scenario_positive_duration():
    """Duration and step must be > 0."""
    with pytest.raises(ValueError, match="must be > 0"):
        DynamicScenario(
            id="bad", name="Bad", description="Bad",
            faults=[], duration_seconds=0, time_step_seconds=5,
        )
    with pytest.raises(ValueError, match="must be > 0"):
        DynamicScenario(
            id="bad", name="Bad", description="Bad",
            faults=[], duration_seconds=100, time_step_seconds=-5,
        )


# ---------------------------------------------------------------------------
# _categorize — lines 93-100 (all type branches)
# ---------------------------------------------------------------------------


def test_categorize_all_types():
    """All component types should be correctly categorized."""
    comps = _make_typed_components()
    ids = list(comps.keys())
    cats = _categorize(comps, ids)

    assert "db-1" in cats["databases"]
    assert "db-2" in cats["databases"]
    assert "cache-1" in cats["caches"]
    assert "app-1" in cats["app_servers"]
    assert "app-2" in cats["app_servers"]
    assert "web-1" in cats["web_servers"]
    assert "lb-1" in cats["load_balancers"]
    assert "queue-1" in cats["queues"]
    assert "store-1" in cats["storage"]
    assert "dns-1" in cats["dns"]


def test_categorize_no_components():
    """Without component dict, all IDs go to 'other'."""
    ids = ["a", "b", "c"]
    cats = _categorize(None, ids)
    assert cats["other"] == ["a", "b", "c"]
    assert cats["databases"] == []


def test_categorize_custom_type():
    """Custom/unknown component types should go to 'other'."""
    comps = {
        "custom-1": Component(
            id="custom-1", name="Custom", type=ComponentType.CUSTOM,
        ),
    }
    ids = list(comps.keys())
    cats = _categorize(comps, ids)
    assert "custom-1" in cats["other"]


# ---------------------------------------------------------------------------
# _host_groups — line 108
# ---------------------------------------------------------------------------


def test_host_groups():
    """Components on the same host should be grouped together."""
    comps = _make_typed_components()
    groups = _host_groups(comps)
    assert "host-a" in groups
    assert len(groups["host-a"]) == 2  # db-1 and db-2
    assert "host-c" in groups
    assert len(groups["host-c"]) == 2  # app-1 and app-2


def test_host_groups_empty():
    """Empty components should return empty groups."""
    groups = _host_groups(None)
    assert groups == {}


# ---------------------------------------------------------------------------
# generate_default_scenarios — comprehensive coverage
# Lines: 424-430, 442-449, 525-531, 621-829
# ---------------------------------------------------------------------------


def test_full_scenario_generation():
    """Full scenario generation with all component types."""
    comps = _make_typed_components()
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)

    # Should have many scenarios
    assert len(scenarios) > 50

    # Category 1: Single failure
    single = _find_scenarios_prefix(scenarios, "single-failure-")
    assert len(single) == len(ids)

    # Category 2: CPU saturation
    cpu = _find_scenarios_prefix(scenarios, "cpu-saturation-")
    assert len(cpu) == len(ids)

    # Category 3: OOM
    oom = _find_scenarios_prefix(scenarios, "oom-")
    assert len(oom) == len(ids)

    # Category 4: Pool exhaustion (db + app + web + cache)
    pool = _find_scenarios_prefix(scenarios, "pool-exhaustion-")
    assert len(pool) > 0

    # Category 5: Disk full (db + storage + app + web + queue)
    disk = _find_scenarios_prefix(scenarios, "disk-full-")
    assert len(disk) > 0

    # Category 6: Network partition
    net = _find_scenarios_prefix(scenarios, "net-partition-")
    assert len(net) == len(ids)

    # Category 7: Latency spike
    latency_5x = _find_scenarios_prefix(scenarios, "latency-5x-")
    assert len(latency_5x) == len(ids)
    latency_20x = _find_scenarios_prefix(scenarios, "latency-20x-")
    assert len(latency_20x) == 2  # Only DBs

    # Category 8: Traffic spike
    traffic = _find_scenarios_prefix(scenarios, "traffic-")
    assert len(traffic) >= 5  # 1.5x, 2x, 3x, 5x, 10x

    # Category 9: Pairwise
    pair = _find_scenarios_prefix(scenarios, "pair-")
    assert len(pair) > 0

    # Category 10: Triple (10 components)
    triple = _find_scenarios_prefix(scenarios, "triple-")
    assert len(triple) > 0

    # Category 11: Cache stampede
    stampede = _find_scenarios_prefix(scenarios, "stampede-")
    assert len(stampede) > 0

    # Category 13: Zone failure (hosts with 2+ components)
    zone = _find_scenarios_prefix(scenarios, "zone-failure-")
    assert len(zone) >= 2  # host-a, host-c

    # Category 14: DB deep scenarios
    log_explosion = _find_scenarios_prefix(scenarios, "log-explosion-")
    assert len(log_explosion) == 2
    replication = _find_scenarios_prefix(scenarios, "replication-lag-")
    assert len(replication) == 2
    conn_storm = _find_scenarios_prefix(scenarios, "connection-storm-")
    assert len(conn_storm) == 2
    lock = _find_scenarios_prefix(scenarios, "lock-contention-")
    assert len(lock) == 2

    # Category 15: Queue scenarios
    backpressure = _find_scenarios_prefix(scenarios, "queue-backpressure-")
    assert len(backpressure) == 1
    poison = _find_scenarios_prefix(scenarios, "poison-message-")
    assert len(poison) == 1

    # Category 16: LB scenarios
    healthcheck = _find_scenarios_prefix(scenarios, "healthcheck-fail-")
    assert len(healthcheck) == 1
    tls = _find_scenarios_prefix(scenarios, "tls-expiry-")
    assert len(tls) == 1
    config_reload = _find_scenarios_prefix(scenarios, "config-reload-")
    assert len(config_reload) == 1

    # Category 17: App server scenarios
    memleak = _find_scenarios_prefix(scenarios, "memory-leak-")
    assert len(memleak) > 0
    thread = _find_scenarios_prefix(scenarios, "thread-exhaustion-")
    assert len(thread) > 0
    gc = _find_scenarios_prefix(scenarios, "gc-pause-")
    assert len(gc) > 0
    bad_deploy = _find_scenarios_prefix(scenarios, "bad-deploy-")
    assert len(bad_deploy) > 0

    # Category 18: Cache scenarios
    eviction = _find_scenarios_prefix(scenarios, "eviction-storm-")
    assert len(eviction) == 1
    split_brain = _find_scenarios_prefix(scenarios, "cache-split-brain-")
    assert len(split_brain) == 1

    # Category 19: DNS scenarios
    dns_fail = _find_scenarios_prefix(scenarios, "dns-failure-")
    assert len(dns_fail) == 1
    dns_lat = _find_scenarios_prefix(scenarios, "dns-latency-")
    assert len(dns_lat) == 1

    # Category 20: Storage scenarios
    io_throttle = _find_scenarios_prefix(scenarios, "io-throttle-")
    assert len(io_throttle) == 1
    corruption = _find_scenarios_prefix(scenarios, "data-corruption-")
    assert len(corruption) == 1

    # Category 21: Cascading timeout
    cascade = _find_scenario(scenarios, "cascading-timeout")
    assert cascade is not None

    # Category 22: Total meltdown
    meltdown = _find_scenario(scenarios, "total-meltdown")
    assert meltdown is not None

    # Category 23: Noisy neighbor
    noisy = _find_scenarios_prefix(scenarios, "noisy-neighbor-")
    assert len(noisy) > 0

    # Category 24: Slow DB at peak
    slow_db = _find_scenarios_prefix(scenarios, "slow-db-peak-")
    assert len(slow_db) == 2

    # Category 25: Rolling restart
    rolling = _find_scenario(scenarios, "rolling-restart-fail")
    assert rolling is not None

    # Category 27: Network partition between tiers
    part_app_db = _find_scenario(scenarios, "partition-app-db")
    assert part_app_db is not None
    part_app_cache = _find_scenario(scenarios, "partition-app-cache")
    assert part_app_cache is not None
    part_lb_app = _find_scenario(scenarios, "partition-lb-app")
    assert part_lb_app is not None

    # Category 28: Resource exhaustion
    exhaustion = _find_scenarios_prefix(scenarios, "resource-exhaustion-")
    assert len(exhaustion) > 0

    # Category 29: Primary failover (DB with replicas > 1)
    failover = _find_scenarios_prefix(scenarios, "primary-failover-")
    assert len(failover) >= 1

    # Category 30: Black Friday
    bf = _find_scenario(scenarios, "black-friday")
    assert bf is not None


def test_scenario_generation_without_components():
    """Scenarios without component dict should still generate base scenarios."""
    ids = ["a", "b", "c"]
    scenarios = generate_default_scenarios(ids, components=None)
    assert len(scenarios) > 0

    # Single failure should work
    single = _find_scenarios_prefix(scenarios, "single-failure-")
    assert len(single) == 3


def test_scenario_generation_single_component():
    """Single component should skip multi-component scenarios."""
    comps = {
        "app": Component(id="app", name="App", type=ComponentType.APP_SERVER),
    }
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    # No triple failures, no rolling restart, no pairwise, no total meltdown
    assert _find_scenario(scenarios, "total-meltdown") is None
    assert _find_scenario(scenarios, "rolling-restart-fail") is None


def test_external_api_scenarios():
    """External API components should generate timeout/down scenarios."""
    comps = {
        "ext": Component(
            id="ext", name="External API", type=ComponentType.EXTERNAL_API,
        ),
        "app": Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ),
    }
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)

    ext_timeout = _find_scenario(scenarios, "external-timeout-ext")
    assert ext_timeout is not None

    ext_down = _find_scenario(scenarios, "external-down-ext")
    assert ext_down is not None


def test_multi_lb_partition_scenarios():
    """When multiple LBs exist, per-LB partition scenarios are generated."""
    comps = {
        "alb-1": Component(
            id="alb-1", name="ALB", type=ComponentType.LOAD_BALANCER, host="host-a",
        ),
        "nlb-1": Component(
            id="nlb-1", name="NLB", type=ComponentType.LOAD_BALANCER, host="host-b",
        ),
        "app-1": Component(
            id="app-1", name="API Server", type=ComponentType.APP_SERVER, host="host-c",
        ),
        "app-2": Component(
            id="app-2", name="Worker", type=ComponentType.APP_SERVER, host="host-d",
        ),
    }
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)

    # Per-LB partition: ALB isolated from app tier
    alb_part = _find_scenario(scenarios, "partition-alb-1-app")
    assert alb_part is not None
    assert alb_part.name == "Network partition: ALB <-> App"
    assert len(alb_part.faults) == 1
    assert alb_part.faults[0].target_component_id == "alb-1"
    assert alb_part.faults[0].fault_type == FaultType.COMPONENT_DOWN

    # Per-LB partition: NLB isolated from app tier
    nlb_part = _find_scenario(scenarios, "partition-nlb-1-app")
    assert nlb_part is not None
    assert nlb_part.name == "Network partition: NLB <-> App"
    assert len(nlb_part.faults) == 1
    assert nlb_part.faults[0].target_component_id == "nlb-1"
    assert nlb_part.faults[0].fault_type == FaultType.COMPONENT_DOWN

    # Full partition still present (worst case: all LBs lose connectivity)
    full_part = _find_scenario(scenarios, "partition-lb-app")
    assert full_part is not None
    assert len(full_part.faults) == 2  # one fault per app server
    for f in full_part.faults:
        assert f.fault_type == FaultType.NETWORK_PARTITION


def test_single_lb_no_per_lb_partition():
    """With only one LB, per-LB partitions should NOT be generated."""
    comps = {
        "lb-1": Component(
            id="lb-1", name="HAProxy", type=ComponentType.LOAD_BALANCER, host="host-a",
        ),
        "app-1": Component(
            id="app-1", name="API Server", type=ComponentType.APP_SERVER, host="host-b",
        ),
    }
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)

    # No per-LB partition when only one LB
    per_lb = _find_scenario(scenarios, "partition-lb-1-app")
    assert per_lb is None

    # Full partition still present
    full_part = _find_scenario(scenarios, "partition-lb-app")
    assert full_part is not None


# ---------------------------------------------------------------------------
# generate_dynamic_scenarios — lines 621-829
# ---------------------------------------------------------------------------


def test_generate_dynamic_scenarios_full():
    """Dynamic scenario generation with all component types."""
    comps = _make_typed_components()
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)

    assert len(scenarios) > 0

    # Scenario 1: DDoS Volumetric
    ddos = _find_scenario(scenarios, "dynamic-ddos-volumetric")
    assert ddos is not None
    assert ddos.traffic_pattern is not None

    # Scenario 2: DDoS Slowloris
    slowloris = _find_scenario(scenarios, "dynamic-ddos-slowloris")
    assert slowloris is not None
    assert len(slowloris.traffic_pattern.affected_components) > 0

    # Scenario 3: Flash Crowd
    flash = _find_scenario(scenarios, "dynamic-flash-crowd")
    assert flash is not None

    # Scenario 4: Viral + DB failure (has db)
    viral_db = _find_scenario(scenarios, "dynamic-viral-db-failure")
    assert viral_db is not None
    assert len(viral_db.faults) == 1

    # Scenario 5: Diurnal + cache failure (has cache)
    diurnal = _find_scenario(scenarios, "dynamic-diurnal-cache-failure")
    assert diurnal is not None

    # Scenario 6: Spike during deployment (has app)
    spike = _find_scenario(scenarios, "dynamic-spike-during-deploy")
    assert spike is not None

    # Scenario 7: DDoS + network partition
    ddos_net = _find_scenario(scenarios, "dynamic-ddos-net-partition")
    assert ddos_net is not None

    # Scenario 8: Sustained high load
    sustained = _find_scenario(scenarios, "dynamic-sustained-high-load")
    assert sustained is not None

    # Scenario 9: Flash + cache stampede
    stampede = _find_scenario(scenarios, "dynamic-flash-cache-stampede")
    assert stampede is not None


def test_generate_dynamic_scenarios_no_db():
    """Dynamic scenarios without databases should skip DB-dependent scenarios."""
    comps = {
        "app": Component(id="app", name="App", type=ComponentType.APP_SERVER),
        "cache": Component(id="cache", name="Cache", type=ComponentType.CACHE),
    }
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)

    # Viral + DB failure should not be generated
    viral_db = _find_scenario(scenarios, "dynamic-viral-db-failure")
    assert viral_db is None

    # But DDoS should still be there
    ddos = _find_scenario(scenarios, "dynamic-ddos-volumetric")
    assert ddos is not None


def test_generate_dynamic_scenarios_no_cache():
    """Dynamic scenarios without cache should skip cache-dependent scenarios."""
    comps = {
        "app": Component(id="app", name="App", type=ComponentType.APP_SERVER),
        "db": Component(id="db", name="DB", type=ComponentType.DATABASE),
    }
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)

    diurnal = _find_scenario(scenarios, "dynamic-diurnal-cache-failure")
    assert diurnal is None

    stampede = _find_scenario(scenarios, "dynamic-flash-cache-stampede")
    assert stampede is None


def test_generate_dynamic_scenarios_no_app():
    """Dynamic scenarios without app servers skip app-dependent scenarios."""
    comps = {
        "db": Component(id="db", name="DB", type=ComponentType.DATABASE),
        "cache": Component(id="cache", name="Cache", type=ComponentType.CACHE),
    }
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)

    spike = _find_scenario(scenarios, "dynamic-spike-during-deploy")
    assert spike is None

    sustained = _find_scenario(scenarios, "dynamic-sustained-high-load")
    assert sustained is None


def test_generate_dynamic_scenarios_minimal():
    """Minimal component set should generate at least basic scenarios."""
    comps = {
        "app": Component(id="app", name="App", type=ComponentType.APP_SERVER),
    }
    ids = list(comps.keys())
    scenarios = generate_dynamic_scenarios(ids, components=comps)
    assert len(scenarios) > 0

    ddos = _find_scenario(scenarios, "dynamic-ddos-volumetric")
    assert ddos is not None
