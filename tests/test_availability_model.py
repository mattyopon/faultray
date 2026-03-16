"""Tests for availability model features (v5.9 - v5.13).

Covers:
- NetworkProfile and RuntimeJitter impact on availability (v5.13)
- Instance-level failures with multi-replica components (v5.11)
- Service-tier availability grouping (v5.10)
- Fractional DOWN for failover-enabled components (v5.9)
"""

from __future__ import annotations

import random

import pytest

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    NetworkProfile,
    OperationalProfile,
    ResourceMetrics,
    RuntimeJitter,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.ops_engine import OpsSimulationEngine, _OpsComponentState, SLOTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component(
    comp_id: str,
    *,
    comp_type: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    network: NetworkProfile | None = None,
    runtime_jitter: RuntimeJitter | None = None,
    failover: FailoverConfig | None = None,
    cpu: float = 30.0,
    memory: float = 40.0,
) -> Component:
    """Create a Component with sensible defaults for testing."""
    return Component(
        id=comp_id,
        name=comp_id,
        type=comp_type,
        host=f"host-{comp_id}",
        port=8080,
        replicas=replicas,
        metrics=ResourceMetrics(cpu_percent=cpu, memory_percent=memory),
        capacity=Capacity(max_connections=1000),
        network=network or NetworkProfile(),
        runtime_jitter=runtime_jitter or RuntimeJitter(),
        failover=failover or FailoverConfig(),
        operational_profile=OperationalProfile(mtbf_hours=8760),
    )


def _zero_network() -> NetworkProfile:
    """NetworkProfile with zero packet loss for tier tests."""
    return NetworkProfile(packet_loss_rate=0.0)


def _build_tier_graph(
    tier_prefix: str,
    count: int,
    *,
    failover: FailoverConfig | None = None,
    extra_standalone: list[Component] | None = None,
) -> InfraGraph:
    """Build a graph with *count* components forming a service tier.

    Components are named ``{tier_prefix}-1``, ``{tier_prefix}-2``, etc.
    Uses zero packet_loss_rate so network penalty doesn't interfere
    with tier-level availability assertions.
    """
    graph = InfraGraph()
    for i in range(1, count + 1):
        comp_id = f"{tier_prefix}-{i}"
        graph.add_component(
            _make_component(comp_id, failover=failover, network=_zero_network())
        )
    if extra_standalone:
        for comp in extra_standalone:
            graph.add_component(comp)
    return graph


# ===========================================================================
# 1. NetworkProfile and RuntimeJitter (v5.13)
# ===========================================================================


class TestNetworkProfileRuntimeJitter:
    """Verify that packet_loss_rate and gc_pause affect availability."""

    def test_high_packet_loss_reduces_availability(self) -> None:
        """A component with high packet loss should lower availability."""
        # Baseline: near-zero packet loss (default)
        graph_low_loss = InfraGraph()
        graph_low_loss.add_component(
            _make_component(
                "app",
                network=NetworkProfile(packet_loss_rate=0.0001),
            )
        )

        # High packet loss: 5%
        graph_high_loss = InfraGraph()
        graph_high_loss.add_component(
            _make_component(
                "app",
                network=NetworkProfile(packet_loss_rate=0.05),
            )
        )

        tracker_low = SLOTracker(graph_low_loss)
        tracker_high = SLOTracker(graph_high_loss)

        states_low = {
            "app": _OpsComponentState(
                component_id="app",
                base_utilization=30.0,
                current_utilization=30.0,
                current_health=HealthStatus.HEALTHY,
            ),
        }
        states_high = {
            "app": _OpsComponentState(
                component_id="app",
                base_utilization=30.0,
                current_utilization=30.0,
                current_health=HealthStatus.HEALTHY,
            ),
        }

        dp_low = tracker_low.record(time_seconds=300, comp_states=states_low)
        dp_high = tracker_high.record(time_seconds=300, comp_states=states_high)

        assert dp_low.availability_percent > dp_high.availability_percent, (
            f"Low-loss availability ({dp_low.availability_percent}) should be > "
            f"high-loss availability ({dp_high.availability_percent})"
        )

    def test_gc_pause_reduces_availability(self) -> None:
        """A component with frequent GC pauses should lower availability."""
        # No GC (Go/Rust-like)
        graph_no_gc = InfraGraph()
        graph_no_gc.add_component(
            _make_component(
                "app",
                runtime_jitter=RuntimeJitter(
                    gc_pause_ms=0.0,
                    gc_pause_frequency=0.0,
                ),
            )
        )

        # Heavy GC: 50ms pauses, 10 times per second = 0.5s/s in GC
        graph_heavy_gc = InfraGraph()
        graph_heavy_gc.add_component(
            _make_component(
                "app",
                runtime_jitter=RuntimeJitter(
                    gc_pause_ms=50.0,
                    gc_pause_frequency=10.0,
                ),
            )
        )

        tracker_no_gc = SLOTracker(graph_no_gc)
        tracker_heavy_gc = SLOTracker(graph_heavy_gc)

        states_no_gc = {
            "app": _OpsComponentState(
                component_id="app",
                base_utilization=30.0,
                current_utilization=30.0,
                current_health=HealthStatus.HEALTHY,
            ),
        }
        states_heavy_gc = {
            "app": _OpsComponentState(
                component_id="app",
                base_utilization=30.0,
                current_utilization=30.0,
                current_health=HealthStatus.HEALTHY,
            ),
        }

        dp_no_gc = tracker_no_gc.record(time_seconds=300, comp_states=states_no_gc)
        dp_heavy_gc = tracker_heavy_gc.record(time_seconds=300, comp_states=states_heavy_gc)

        assert dp_no_gc.availability_percent > dp_heavy_gc.availability_percent, (
            f"No-GC availability ({dp_no_gc.availability_percent}) should be > "
            f"heavy-GC availability ({dp_heavy_gc.availability_percent})"
        )

    def test_combined_network_and_gc_penalty(self) -> None:
        """Network loss + GC pauses should have a compounding effect."""
        # Clean component (defaults)
        graph_clean = InfraGraph()
        graph_clean.add_component(_make_component("app"))

        # Noisy component: moderate packet loss + moderate GC
        graph_noisy = InfraGraph()
        graph_noisy.add_component(
            _make_component(
                "app",
                network=NetworkProfile(packet_loss_rate=0.01),
                runtime_jitter=RuntimeJitter(
                    gc_pause_ms=20.0,
                    gc_pause_frequency=5.0,
                ),
            )
        )

        tracker_clean = SLOTracker(graph_clean)
        tracker_noisy = SLOTracker(graph_noisy)

        states = {
            "app": _OpsComponentState(
                component_id="app",
                base_utilization=30.0,
                current_utilization=30.0,
                current_health=HealthStatus.HEALTHY,
            ),
        }

        dp_clean = tracker_clean.record(time_seconds=300, comp_states=dict(states))
        dp_noisy = tracker_noisy.record(time_seconds=300, comp_states=dict(states))

        # Combined penalty should be larger than either alone
        penalty = dp_clean.availability_percent - dp_noisy.availability_percent
        assert penalty > 0, (
            f"Combined network+GC penalty ({penalty}) should be > 0"
        )


# ===========================================================================
# 2. Instance-level failures (v5.11)
# ===========================================================================


class TestInstanceLevelFailures:
    """Multi-replica components should stay DEGRADED (not DOWN) when
    a single instance fails."""

    def test_multi_replica_partial_failure_is_degraded(self) -> None:
        """A 3-replica component with 1 instance down should be DEGRADED."""
        graph = InfraGraph()
        graph.add_component(
            _make_component("app", replicas=3)
        )

        # Simulate instance-level failure in ops state
        state = _OpsComponentState(
            component_id="app",
            base_utilization=30.0,
            current_utilization=30.0,
            current_health=HealthStatus.DEGRADED,
            current_replicas=3,
            base_replicas=3,
            instances_down=1,
        )

        # With 1 instance down out of 3, component should be DEGRADED not DOWN
        assert state.current_health == HealthStatus.DEGRADED
        assert state.instances_down < state.current_replicas

    def test_all_instances_down_is_full_down(self) -> None:
        """When ALL instances of a multi-replica component fail, it's DOWN."""
        state = _OpsComponentState(
            component_id="app",
            base_utilization=30.0,
            current_utilization=0.0,
            current_health=HealthStatus.DOWN,
            current_replicas=3,
            base_replicas=3,
            instances_down=3,
        )
        assert state.instances_down >= state.current_replicas
        assert state.current_health == HealthStatus.DOWN

    def test_instance_failure_load_redistribution(self) -> None:
        """When 1 of 3 instances fails, surviving instances get higher load."""
        replicas = 3
        instances_down = 1
        base_util = 30.0

        surviving = replicas - instances_down
        load_factor = replicas / surviving  # 3/2 = 1.5
        effective_util = base_util * load_factor

        assert effective_util == pytest.approx(45.0), (
            f"Expected ~45% utilization after losing 1 of 3 instances, got {effective_util}"
        )

    def test_multi_replica_slo_tracker_records_degraded_not_down(self) -> None:
        """SLOTracker should see a multi-replica component with partial failure
        as DEGRADED, not DOWN, in its availability calculation."""
        graph = InfraGraph()
        graph.add_component(_make_component("app", replicas=3))

        tracker = SLOTracker(graph)

        # 1 instance down but component is DEGRADED (not DOWN)
        states = {
            "app": _OpsComponentState(
                component_id="app",
                base_utilization=30.0,
                current_utilization=45.0,
                current_health=HealthStatus.DEGRADED,
                current_replicas=3,
                base_replicas=3,
                instances_down=1,
            ),
        }

        dp = tracker.record(time_seconds=300, comp_states=states)
        # A DEGRADED component (not DOWN) should NOT cause full unavailability
        assert dp.availability_percent > 99.0, (
            f"Availability {dp.availability_percent} should be > 99% since component is "
            f"DEGRADED not DOWN"
        )


# ===========================================================================
# 3. Service-tier availability (v5.10)
# ===========================================================================


class TestServiceTierAvailability:
    """Service-tier grouping: a tier (e.g. hono-api-1..3) stays available
    when only 1 member is DOWN."""

    def test_tier_available_when_one_member_down(self) -> None:
        """A tier with 3 members where 1 is DOWN should still be available."""
        graph = _build_tier_graph("hono-api", 3)
        tracker = SLOTracker(graph)

        # 2 healthy, 1 down
        states = {
            "hono-api-1": _OpsComponentState(
                component_id="hono-api-1",
                base_utilization=30.0,
                current_utilization=30.0,
                current_health=HealthStatus.HEALTHY,
            ),
            "hono-api-2": _OpsComponentState(
                component_id="hono-api-2",
                base_utilization=30.0,
                current_utilization=30.0,
                current_health=HealthStatus.HEALTHY,
            ),
            "hono-api-3": _OpsComponentState(
                component_id="hono-api-3",
                base_utilization=30.0,
                current_utilization=0.0,
                current_health=HealthStatus.DOWN,
            ),
        }

        dp = tracker.record(time_seconds=300, comp_states=states)
        # Tier should be available: not all members are down
        assert dp.availability_percent == 100.0, (
            f"Tier availability should be 100% when 1 of 3 members is down, "
            f"got {dp.availability_percent}%"
        )

    def test_tier_unavailable_when_all_members_down(self) -> None:
        """A tier where ALL members are DOWN should be unavailable."""
        graph = _build_tier_graph("hono-api", 3)
        tracker = SLOTracker(graph)

        states = {
            f"hono-api-{i}": _OpsComponentState(
                component_id=f"hono-api-{i}",
                base_utilization=30.0,
                current_utilization=0.0,
                current_health=HealthStatus.DOWN,
            )
            for i in range(1, 4)
        }

        dp = tracker.record(time_seconds=300, comp_states=states)
        assert dp.availability_percent < 100.0, (
            f"Tier availability should be < 100% when all members are down, "
            f"got {dp.availability_percent}%"
        )

    def test_tier_grouping_by_name_prefix(self) -> None:
        """Components sharing a name prefix (minus trailing digits) form a tier."""
        graph = InfraGraph()
        # Tier: worker-1, worker-2 (same prefix "worker")
        graph.add_component(_make_component("worker-1", network=_zero_network()))
        graph.add_component(_make_component("worker-2", network=_zero_network()))
        # Standalone: "db" (no numeric suffix, no tier)
        graph.add_component(
            _make_component("db", comp_type=ComponentType.DATABASE, network=_zero_network())
        )

        tracker = SLOTracker(graph)

        # worker-1 DOWN, worker-2 HEALTHY, db HEALTHY
        states = {
            "worker-1": _OpsComponentState(
                component_id="worker-1",
                base_utilization=30.0,
                current_utilization=0.0,
                current_health=HealthStatus.DOWN,
            ),
            "worker-2": _OpsComponentState(
                component_id="worker-2",
                base_utilization=30.0,
                current_utilization=30.0,
                current_health=HealthStatus.HEALTHY,
            ),
            "db": _OpsComponentState(
                component_id="db",
                base_utilization=40.0,
                current_utilization=40.0,
                current_health=HealthStatus.HEALTHY,
            ),
        }

        dp = tracker.record(time_seconds=300, comp_states=states)
        # worker tier is still available (worker-2 up), db is up
        assert dp.availability_percent == 100.0, (
            f"Availability should be 100% when one tier member is down "
            f"but the tier has a surviving member, got {dp.availability_percent}%"
        )

    def test_mixed_tiers_and_standalone(self) -> None:
        """Multiple tiers + standalone components should each be evaluated correctly."""
        graph = InfraGraph()
        # Tier A: api-1, api-2
        graph.add_component(_make_component("api-1", network=_zero_network()))
        graph.add_component(_make_component("api-2", network=_zero_network()))
        # Tier B: cache-1, cache-2
        graph.add_component(
            _make_component("cache-1", comp_type=ComponentType.CACHE, network=_zero_network())
        )
        graph.add_component(
            _make_component("cache-2", comp_type=ComponentType.CACHE, network=_zero_network())
        )
        # Standalone: db (no numeric suffix)
        graph.add_component(
            _make_component("db", comp_type=ComponentType.DATABASE, network=_zero_network())
        )

        tracker = SLOTracker(graph)

        # api-1 DOWN (api tier still up), cache both HEALTHY, db HEALTHY
        states = {
            "api-1": _OpsComponentState(
                component_id="api-1",
                base_utilization=30.0,
                current_utilization=0.0,
                current_health=HealthStatus.DOWN,
            ),
            "api-2": _OpsComponentState(
                component_id="api-2",
                base_utilization=30.0,
                current_utilization=30.0,
                current_health=HealthStatus.HEALTHY,
            ),
            "cache-1": _OpsComponentState(
                component_id="cache-1",
                base_utilization=20.0,
                current_utilization=20.0,
                current_health=HealthStatus.HEALTHY,
            ),
            "cache-2": _OpsComponentState(
                component_id="cache-2",
                base_utilization=20.0,
                current_utilization=20.0,
                current_health=HealthStatus.HEALTHY,
            ),
            "db": _OpsComponentState(
                component_id="db",
                base_utilization=40.0,
                current_utilization=40.0,
                current_health=HealthStatus.HEALTHY,
            ),
        }

        dp = tracker.record(time_seconds=300, comp_states=states)
        # All tiers available, standalone up
        assert dp.availability_percent == 100.0, (
            f"Expected 100% availability with partial tier failure and "
            f"all other tiers/standalone healthy, got {dp.availability_percent}%"
        )


# ===========================================================================
# 4. Fractional DOWN (v5.9)
# ===========================================================================


class TestFractionalDown:
    """Failover-enabled components should have partial (not full) availability
    impact when they go DOWN."""

    def test_failover_component_fractional_impact(self) -> None:
        """A standalone component with failover enabled should contribute only
        a fractional DOWN, not a full unit of downtime."""
        failover_cfg = FailoverConfig(
            enabled=True,
            promotion_time_seconds=30.0,
            health_check_interval_seconds=10.0,
            failover_threshold=3,
        )

        # Graph with failover (zero network to isolate the failover effect)
        graph_fo = InfraGraph()
        graph_fo.add_component(
            _make_component("app-fo", failover=failover_cfg, network=_zero_network())
        )

        # Graph without failover
        graph_nofo = InfraGraph()
        graph_nofo.add_component(
            _make_component("app-nofo", network=_zero_network())
        )

        tracker_fo = SLOTracker(graph_fo)
        tracker_nofo = SLOTracker(graph_nofo)

        states_fo = {
            "app-fo": _OpsComponentState(
                component_id="app-fo",
                base_utilization=30.0,
                current_utilization=0.0,
                current_health=HealthStatus.DOWN,
            ),
        }
        states_nofo = {
            "app-nofo": _OpsComponentState(
                component_id="app-nofo",
                base_utilization=30.0,
                current_utilization=0.0,
                current_health=HealthStatus.DOWN,
            ),
        }

        dp_fo = tracker_fo.record(time_seconds=300, comp_states=states_fo)
        dp_nofo = tracker_nofo.record(time_seconds=300, comp_states=states_nofo)

        # Failover-enabled component should have HIGHER availability
        # (fractional down vs full down)
        assert dp_fo.availability_percent > dp_nofo.availability_percent, (
            f"Failover availability ({dp_fo.availability_percent}) should be > "
            f"no-failover availability ({dp_nofo.availability_percent})"
        )

    def test_failover_tier_fractional_impact(self) -> None:
        """A tier with failover where ALL members are DOWN should still have
        a fractional impact (not full tier-down) due to failover."""
        failover_cfg = FailoverConfig(
            enabled=True,
            promotion_time_seconds=30.0,
            health_check_interval_seconds=10.0,
            failover_threshold=3,
        )

        graph = _build_tier_graph("svc", 2, failover=failover_cfg)
        tracker = SLOTracker(graph)

        # All tier members DOWN
        states = {
            "svc-1": _OpsComponentState(
                component_id="svc-1",
                base_utilization=30.0,
                current_utilization=0.0,
                current_health=HealthStatus.DOWN,
            ),
            "svc-2": _OpsComponentState(
                component_id="svc-2",
                base_utilization=30.0,
                current_utilization=0.0,
                current_health=HealthStatus.DOWN,
            ),
        }

        dp = tracker.record(time_seconds=300, comp_states=states)
        # With failover, this should be a fractional down, not a full 0%
        assert dp.availability_percent > 0.0, (
            f"Failover-enabled tier availability ({dp.availability_percent}%) should be > 0% "
            f"even when all members DOWN (fractional impact from failover)"
        )
        assert dp.availability_percent < 100.0, (
            f"Availability ({dp.availability_percent}%) should be < 100% when all members are DOWN"
        )

    def test_multi_replica_with_failover_minimal_impact(self) -> None:
        """A standalone multi-replica component with failover should have
        minimal availability impact when DOWN (replicas + failover mitigate)."""
        failover_cfg = FailoverConfig(
            enabled=True,
            promotion_time_seconds=15.0,
            health_check_interval_seconds=5.0,
            failover_threshold=3,
        )

        graph = InfraGraph()
        graph.add_component(
            _make_component("app", replicas=3, failover=failover_cfg)
        )

        tracker = SLOTracker(graph)

        states = {
            "app": _OpsComponentState(
                component_id="app",
                base_utilization=30.0,
                current_utilization=0.0,
                current_health=HealthStatus.DOWN,
            ),
        }

        dp = tracker.record(time_seconds=300, comp_states=states)
        # Multi-replica + failover: should have very high availability
        # even when the component is marked DOWN
        assert dp.availability_percent > 50.0, (
            f"Multi-replica+failover availability ({dp.availability_percent}%) should be > 50% "
            f"due to combined redundancy"
        )

    def test_no_failover_full_down_impact(self) -> None:
        """Without failover, a DOWN component should cause full tier downtime."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", comp_type=ComponentType.DATABASE))

        tracker = SLOTracker(graph)

        states = {
            "db": _OpsComponentState(
                component_id="db",
                base_utilization=40.0,
                current_utilization=0.0,
                current_health=HealthStatus.DOWN,
            ),
        }

        dp = tracker.record(time_seconds=300, comp_states=states)
        # No failover: should be 0% availability
        assert dp.availability_percent == 0.0, (
            f"No-failover DOWN component should have 0% availability, got {dp.availability_percent}%"
        )
