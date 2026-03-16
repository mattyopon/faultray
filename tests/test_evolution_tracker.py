"""Tests for the Infrastructure Evolution Tracker module.

Targets 99%+ line/branch coverage.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.evolution_tracker import (
    ChangeType,
    EvolutionReport,
    EvolutionTracker,
    InfraChange,
    InfraSnapshot,
    TrendAnalysis,
    TrendDirection,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    failover: bool = False,
    cpu: float = 0.0,
    memory: float = 0.0,
) -> Component:
    """Create a Component with sensible defaults for testing."""
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True, promotion_time_seconds=10)
    c.metrics = ResourceMetrics(cpu_percent=cpu, memory_percent=memory)
    return c


def _graph(*comps: Component) -> InfraGraph:
    """Build an InfraGraph from a list of components."""
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ===================================================================
# 1. Enum values
# ===================================================================

class TestEnums:
    def test_trend_direction_values(self):
        assert TrendDirection.IMPROVING == "improving"
        assert TrendDirection.STABLE == "stable"
        assert TrendDirection.DEGRADING == "degrading"

    def test_trend_direction_members(self):
        assert set(TrendDirection) == {
            TrendDirection.IMPROVING,
            TrendDirection.STABLE,
            TrendDirection.DEGRADING,
        }

    def test_change_type_values(self):
        assert ChangeType.COMPONENT_ADDED == "component_added"
        assert ChangeType.COMPONENT_REMOVED == "component_removed"
        assert ChangeType.REPLICA_CHANGED == "replica_changed"
        assert ChangeType.FAILOVER_CHANGED == "failover_changed"
        assert ChangeType.HEALTH_CHANGED == "health_changed"
        assert ChangeType.DEPENDENCY_ADDED == "dependency_added"
        assert ChangeType.DEPENDENCY_REMOVED == "dependency_removed"
        assert ChangeType.SECURITY_CHANGED == "security_changed"

    def test_change_type_count(self):
        assert len(ChangeType) == 8

    def test_trend_direction_is_str(self):
        assert isinstance(TrendDirection.IMPROVING, str)

    def test_change_type_is_str(self):
        assert isinstance(ChangeType.COMPONENT_ADDED, str)


# ===================================================================
# 2. Data class construction
# ===================================================================

class TestDataClasses:
    def test_infra_snapshot_defaults(self):
        s = InfraSnapshot(
            snapshot_id="s1",
            timestamp="2026-01-01T00:00:00Z",
            total_components=0,
            healthy_count=0,
            degraded_count=0,
            down_count=0,
            total_replicas=0,
            failover_enabled_count=0,
            avg_cpu=0.0,
            avg_memory=0.0,
            resilience_score=0.0,
        )
        assert s.component_ids == []

    def test_infra_snapshot_with_ids(self):
        s = InfraSnapshot(
            snapshot_id="s1",
            timestamp="t",
            total_components=1,
            healthy_count=1,
            degraded_count=0,
            down_count=0,
            total_replicas=1,
            failover_enabled_count=0,
            avg_cpu=10.0,
            avg_memory=20.0,
            resilience_score=50.0,
            component_ids=["a", "b"],
        )
        assert s.component_ids == ["a", "b"]

    def test_infra_change_fields(self):
        c = InfraChange(
            change_type=ChangeType.COMPONENT_ADDED,
            component_id="c1",
            component_name="web",
            old_value="",
            new_value="app_server",
            impact_description="Added",
        )
        assert c.change_type == ChangeType.COMPONENT_ADDED
        assert c.component_id == "c1"

    def test_trend_analysis_fields(self):
        t = TrendAnalysis(
            metric_name="resilience_score",
            direction=TrendDirection.IMPROVING,
            current_value=80.0,
            previous_value=70.0,
            change_percent=14.29,
            assessment="Getting better",
        )
        assert t.metric_name == "resilience_score"
        assert t.direction == TrendDirection.IMPROVING

    def test_evolution_report_defaults(self):
        r = EvolutionReport()
        assert r.snapshots == []
        assert r.changes == []
        assert r.trends == []
        assert r.overall_trend == TrendDirection.STABLE
        assert r.improvement_count == 0
        assert r.regression_count == 0
        assert r.recommendations == []
        assert r.summary == ""


# ===================================================================
# 3. Empty graph snapshot
# ===================================================================

class TestEmptyGraphSnapshot:
    def test_empty_graph_snapshot(self):
        tracker = EvolutionTracker()
        g = _graph()
        snap = tracker.capture(g)
        assert snap.total_components == 0
        assert snap.healthy_count == 0
        assert snap.degraded_count == 0
        assert snap.down_count == 0
        assert snap.total_replicas == 0
        assert snap.failover_enabled_count == 0
        assert snap.avg_cpu == 0.0
        assert snap.avg_memory == 0.0
        assert snap.resilience_score == 0.0
        assert snap.component_ids == []

    def test_empty_graph_snapshot_has_id_and_timestamp(self):
        tracker = EvolutionTracker()
        snap = tracker.capture(_graph())
        assert snap.snapshot_id  # non-empty
        assert snap.timestamp  # non-empty


# ===================================================================
# 4. Single component snapshot
# ===================================================================

class TestSingleComponentSnapshot:
    def test_single_healthy_component(self):
        tracker = EvolutionTracker()
        g = _graph(_comp("a", "App"))
        snap = tracker.capture(g)
        assert snap.total_components == 1
        assert snap.healthy_count == 1
        assert snap.degraded_count == 0
        assert snap.down_count == 0
        assert snap.total_replicas == 1

    def test_resilience_score_single_healthy(self):
        """healthy=1 → healthy_score=40, replicas=1/3*20≈6.67, failover=0, headroom=20 → 66.67"""
        tracker = EvolutionTracker()
        g = _graph(_comp("a", "App", replicas=1, cpu=0, memory=0))
        snap = tracker.capture(g)
        expected = 40.0 + (1 / 3 * 20) + 0.0 + 20.0
        assert abs(snap.resilience_score - round(expected, 2)) < 0.1

    def test_resilience_score_with_failover(self):
        tracker = EvolutionTracker()
        g = _graph(_comp("a", "App", replicas=3, failover=True, cpu=0, memory=0))
        snap = tracker.capture(g)
        # healthy=40, replicas=3/3*20=20, failover=20, headroom=20 → 100
        assert snap.resilience_score == 100.0

    def test_resilience_score_high_cpu(self):
        tracker = EvolutionTracker()
        g = _graph(_comp("a", "App", cpu=80.0, memory=0.0))
        snap = tracker.capture(g)
        # headroom = (100-80)/100*20 = 4.0
        expected = 40.0 + (1 / 3 * 20) + 0.0 + 4.0
        assert abs(snap.resilience_score - round(expected, 2)) < 0.1

    def test_resilience_score_high_memory(self):
        tracker = EvolutionTracker()
        g = _graph(_comp("a", "App", cpu=0.0, memory=90.0))
        snap = tracker.capture(g)
        # headroom = (100-90)/100*20 = 2.0
        expected = 40.0 + (1 / 3 * 20) + 0.0 + 2.0
        assert abs(snap.resilience_score - round(expected, 2)) < 0.1

    def test_resilience_score_cpu_and_memory(self):
        """Headroom uses max(avg_cpu, avg_memory)."""
        tracker = EvolutionTracker()
        g = _graph(_comp("a", "App", cpu=60.0, memory=70.0))
        snap = tracker.capture(g)
        # headroom = (100-70)/100*20 = 6.0
        expected = 40.0 + (1 / 3 * 20) + 0.0 + 6.0
        assert abs(snap.resilience_score - round(expected, 2)) < 0.1

    def test_single_down_component(self):
        tracker = EvolutionTracker()
        g = _graph(_comp("a", "App", health=HealthStatus.DOWN))
        snap = tracker.capture(g)
        assert snap.healthy_count == 0
        assert snap.down_count == 1
        assert snap.degraded_count == 0
        # healthy_score = 0
        assert snap.resilience_score < 40.0

    def test_single_degraded_component(self):
        tracker = EvolutionTracker()
        g = _graph(_comp("a", "App", health=HealthStatus.DEGRADED))
        snap = tracker.capture(g)
        assert snap.degraded_count == 1
        assert snap.healthy_count == 0

    def test_single_overloaded_component(self):
        tracker = EvolutionTracker()
        g = _graph(_comp("a", "App", health=HealthStatus.OVERLOADED))
        snap = tracker.capture(g)
        assert snap.degraded_count == 1
        assert snap.healthy_count == 0


# ===================================================================
# 5. Multiple components with mixed health
# ===================================================================

class TestMultipleComponents:
    def test_mixed_health(self):
        tracker = EvolutionTracker()
        g = _graph(
            _comp("a", "App", health=HealthStatus.HEALTHY),
            _comp("b", "DB", health=HealthStatus.DEGRADED),
            _comp("c", "Cache", health=HealthStatus.DOWN),
        )
        snap = tracker.capture(g)
        assert snap.total_components == 3
        assert snap.healthy_count == 1
        assert snap.degraded_count == 1
        assert snap.down_count == 1

    def test_all_healthy_many_replicas(self):
        tracker = EvolutionTracker()
        g = _graph(
            _comp("a", "App", replicas=3, failover=True),
            _comp("b", "DB", replicas=3, failover=True),
        )
        snap = tracker.capture(g)
        assert snap.total_replicas == 6
        assert snap.failover_enabled_count == 2
        assert snap.resilience_score == 100.0

    def test_avg_cpu_memory(self):
        tracker = EvolutionTracker()
        g = _graph(
            _comp("a", "App", cpu=40.0, memory=20.0),
            _comp("b", "DB", cpu=60.0, memory=80.0),
        )
        snap = tracker.capture(g)
        assert snap.avg_cpu == 50.0
        assert snap.avg_memory == 50.0

    def test_component_ids_sorted(self):
        tracker = EvolutionTracker()
        g = _graph(
            _comp("z", "Z"),
            _comp("a", "A"),
            _comp("m", "M"),
        )
        snap = tracker.capture(g)
        assert snap.component_ids == ["a", "m", "z"]


# ===================================================================
# 6. Capture multiple snapshots — verify list grows
# ===================================================================

class TestMultipleCaptures:
    def test_snapshot_count_grows(self):
        tracker = EvolutionTracker()
        assert tracker.get_snapshot_count() == 0
        tracker.capture(_graph(_comp("a", "A")))
        assert tracker.get_snapshot_count() == 1
        tracker.capture(_graph(_comp("a", "A"), _comp("b", "B")))
        assert tracker.get_snapshot_count() == 2

    def test_unique_snapshot_ids(self):
        tracker = EvolutionTracker()
        s1 = tracker.capture(_graph(_comp("a", "A")))
        s2 = tracker.capture(_graph(_comp("a", "A")))
        assert s1.snapshot_id != s2.snapshot_id

    def test_timestamps_are_iso(self):
        tracker = EvolutionTracker()
        snap = tracker.capture(_graph(_comp("a", "A")))
        assert "T" in snap.timestamp  # ISO 8601


# ===================================================================
# 7. Compare: component added
# ===================================================================

class TestCompareAdded:
    def test_component_added(self):
        g_a = _graph(_comp("a", "App"))
        g_b = _graph(_comp("a", "App"), _comp("b", "DB"))
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        added = [c for c in changes if c.change_type == ChangeType.COMPONENT_ADDED]
        assert len(added) == 1
        assert added[0].component_id == "b"
        assert "added" in added[0].impact_description.lower()

    def test_multiple_components_added(self):
        g_a = _graph()
        g_b = _graph(_comp("a", "A"), _comp("b", "B"))
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        added = [c for c in changes if c.change_type == ChangeType.COMPONENT_ADDED]
        assert len(added) == 2


# ===================================================================
# 8. Compare: component removed
# ===================================================================

class TestCompareRemoved:
    def test_component_removed(self):
        g_a = _graph(_comp("a", "App"), _comp("b", "DB"))
        g_b = _graph(_comp("a", "App"))
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        removed = [c for c in changes if c.change_type == ChangeType.COMPONENT_REMOVED]
        assert len(removed) == 1
        assert removed[0].component_id == "b"
        assert "removed" in removed[0].impact_description.lower()

    def test_all_components_removed(self):
        g_a = _graph(_comp("a", "A"), _comp("b", "B"))
        g_b = _graph()
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        removed = [c for c in changes if c.change_type == ChangeType.COMPONENT_REMOVED]
        assert len(removed) == 2


# ===================================================================
# 9. Compare: replica changed
# ===================================================================

class TestCompareReplicaChanged:
    def test_replica_increased(self):
        g_a = _graph(_comp("a", "App", replicas=1))
        g_b = _graph(_comp("a", "App", replicas=3))
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        replica = [c for c in changes if c.change_type == ChangeType.REPLICA_CHANGED]
        assert len(replica) == 1
        assert replica[0].old_value == "1"
        assert replica[0].new_value == "3"

    def test_replica_decreased(self):
        g_a = _graph(_comp("a", "App", replicas=5))
        g_b = _graph(_comp("a", "App", replicas=2))
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        replica = [c for c in changes if c.change_type == ChangeType.REPLICA_CHANGED]
        assert len(replica) == 1
        assert replica[0].old_value == "5"
        assert replica[0].new_value == "2"


# ===================================================================
# 10. Compare: failover changed
# ===================================================================

class TestCompareFailoverChanged:
    def test_failover_enabled(self):
        g_a = _graph(_comp("a", "App", failover=False))
        g_b = _graph(_comp("a", "App", failover=True))
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        fchange = [c for c in changes if c.change_type == ChangeType.FAILOVER_CHANGED]
        assert len(fchange) == 1
        assert fchange[0].old_value == "False"
        assert fchange[0].new_value == "True"

    def test_failover_disabled(self):
        g_a = _graph(_comp("a", "App", failover=True))
        g_b = _graph(_comp("a", "App", failover=False))
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        fchange = [c for c in changes if c.change_type == ChangeType.FAILOVER_CHANGED]
        assert len(fchange) == 1
        assert fchange[0].old_value == "True"
        assert fchange[0].new_value == "False"


# ===================================================================
# 11. Compare: health changed
# ===================================================================

class TestCompareHealthChanged:
    def test_health_degraded(self):
        g_a = _graph(_comp("a", "App", health=HealthStatus.HEALTHY))
        g_b = _graph(_comp("a", "App", health=HealthStatus.DOWN))
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        hchange = [c for c in changes if c.change_type == ChangeType.HEALTH_CHANGED]
        assert len(hchange) == 1
        assert hchange[0].old_value == "healthy"
        assert hchange[0].new_value == "down"

    def test_health_recovered(self):
        g_a = _graph(_comp("a", "App", health=HealthStatus.DOWN))
        g_b = _graph(_comp("a", "App", health=HealthStatus.HEALTHY))
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        hchange = [c for c in changes if c.change_type == ChangeType.HEALTH_CHANGED]
        assert len(hchange) == 1
        assert hchange[0].old_value == "down"
        assert hchange[0].new_value == "healthy"


# ===================================================================
# 12. Compare: security changed
# ===================================================================

class TestCompareSecurityChanged:
    def test_security_encryption_changed(self):
        c_a = _comp("a", "App")
        c_a.security = SecurityProfile(encryption_at_rest=False)
        g_a = _graph(c_a)

        c_b = _comp("a", "App")
        c_b.security = SecurityProfile(encryption_at_rest=True)
        g_b = _graph(c_b)

        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        schange = [c for c in changes if c.change_type == ChangeType.SECURITY_CHANGED]
        assert len(schange) == 1
        assert "security" in schange[0].impact_description.lower()

    def test_security_waf_changed(self):
        c_a = _comp("a", "App")
        c_a.security = SecurityProfile(waf_protected=False)
        g_a = _graph(c_a)

        c_b = _comp("a", "App")
        c_b.security = SecurityProfile(waf_protected=True)
        g_b = _graph(c_b)

        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        schange = [c for c in changes if c.change_type == ChangeType.SECURITY_CHANGED]
        assert len(schange) == 1

    def test_security_rate_limiting_changed(self):
        c_a = _comp("a", "App")
        c_a.security = SecurityProfile(rate_limiting=False)
        g_a = _graph(c_a)

        c_b = _comp("a", "App")
        c_b.security = SecurityProfile(rate_limiting=True)
        g_b = _graph(c_b)

        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        schange = [c for c in changes if c.change_type == ChangeType.SECURITY_CHANGED]
        assert len(schange) == 1

    def test_security_auth_changed(self):
        c_a = _comp("a", "App")
        c_a.security = SecurityProfile(auth_required=False)
        g_a = _graph(c_a)

        c_b = _comp("a", "App")
        c_b.security = SecurityProfile(auth_required=True)
        g_b = _graph(c_b)

        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        schange = [c for c in changes if c.change_type == ChangeType.SECURITY_CHANGED]
        assert len(schange) == 1

    def test_security_network_segmented_changed(self):
        c_a = _comp("a", "App")
        c_a.security = SecurityProfile(network_segmented=False)
        g_a = _graph(c_a)

        c_b = _comp("a", "App")
        c_b.security = SecurityProfile(network_segmented=True)
        g_b = _graph(c_b)

        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        schange = [c for c in changes if c.change_type == ChangeType.SECURITY_CHANGED]
        assert len(schange) == 1

    def test_security_backup_changed(self):
        c_a = _comp("a", "App")
        c_a.security = SecurityProfile(backup_enabled=False)
        g_a = _graph(c_a)

        c_b = _comp("a", "App")
        c_b.security = SecurityProfile(backup_enabled=True)
        g_b = _graph(c_b)

        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        schange = [c for c in changes if c.change_type == ChangeType.SECURITY_CHANGED]
        assert len(schange) == 1

    def test_security_log_changed(self):
        c_a = _comp("a", "App")
        c_a.security = SecurityProfile(log_enabled=False)
        g_a = _graph(c_a)

        c_b = _comp("a", "App")
        c_b.security = SecurityProfile(log_enabled=True)
        g_b = _graph(c_b)

        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        schange = [c for c in changes if c.change_type == ChangeType.SECURITY_CHANGED]
        assert len(schange) == 1

    def test_security_ids_changed(self):
        c_a = _comp("a", "App")
        c_a.security = SecurityProfile(ids_monitored=False)
        g_a = _graph(c_a)

        c_b = _comp("a", "App")
        c_b.security = SecurityProfile(ids_monitored=True)
        g_b = _graph(c_b)

        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        schange = [c for c in changes if c.change_type == ChangeType.SECURITY_CHANGED]
        assert len(schange) == 1

    def test_security_transit_changed(self):
        c_a = _comp("a", "App")
        c_a.security = SecurityProfile(encryption_in_transit=False)
        g_a = _graph(c_a)

        c_b = _comp("a", "App")
        c_b.security = SecurityProfile(encryption_in_transit=True)
        g_b = _graph(c_b)

        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        schange = [c for c in changes if c.change_type == ChangeType.SECURITY_CHANGED]
        assert len(schange) == 1

    def test_security_no_change(self):
        c_a = _comp("a", "App")
        c_a.security = SecurityProfile(encryption_at_rest=True, waf_protected=True)
        g_a = _graph(c_a)

        c_b = _comp("a", "App")
        c_b.security = SecurityProfile(encryption_at_rest=True, waf_protected=True)
        g_b = _graph(c_b)

        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        schange = [c for c in changes if c.change_type == ChangeType.SECURITY_CHANGED]
        assert len(schange) == 0


# ===================================================================
# 13. Compare identical graphs (no changes)
# ===================================================================

class TestCompareIdentical:
    def test_identical_graphs_no_changes(self):
        g = _graph(_comp("a", "App", replicas=2, failover=True))
        tracker = EvolutionTracker()
        changes = tracker.compare(g, g)
        assert changes == []

    def test_identical_empty_graphs(self):
        tracker = EvolutionTracker()
        changes = tracker.compare(_graph(), _graph())
        assert changes == []

    def test_identical_multi_component(self):
        c1 = _comp("a", "A", replicas=2)
        c2 = _comp("b", "B", failover=True)
        g_a = _graph(c1, c2)
        g_b = _graph(c1, c2)
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        assert changes == []


# ===================================================================
# 14. Compare: multiple changes at once
# ===================================================================

class TestCompareMultipleChanges:
    def test_added_and_removed(self):
        g_a = _graph(_comp("a", "A"))
        g_b = _graph(_comp("b", "B"))
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        types = {c.change_type for c in changes}
        assert ChangeType.COMPONENT_ADDED in types
        assert ChangeType.COMPONENT_REMOVED in types

    def test_replica_and_failover_and_health_changed(self):
        g_a = _graph(_comp("a", "App", replicas=1, failover=False, health=HealthStatus.HEALTHY))
        g_b = _graph(_comp("a", "App", replicas=3, failover=True, health=HealthStatus.DEGRADED))
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        types = {c.change_type for c in changes}
        assert ChangeType.REPLICA_CHANGED in types
        assert ChangeType.FAILOVER_CHANGED in types
        assert ChangeType.HEALTH_CHANGED in types


# ===================================================================
# 15. Trend analysis with 2 snapshots — improving
# ===================================================================

class TestTrendImproving:
    def test_improving_resilience(self):
        tracker = EvolutionTracker()
        # Snapshot 1: poor
        tracker.capture(_graph(_comp("a", "A", health=HealthStatus.DOWN, cpu=80.0)))
        # Snapshot 2: good
        tracker.capture(_graph(_comp("a", "A", health=HealthStatus.HEALTHY, replicas=3, failover=True, cpu=10.0)))
        report = tracker.analyze_trends()
        resilience_trend = next(t for t in report.trends if t.metric_name == "resilience_score")
        assert resilience_trend.direction == TrendDirection.IMPROVING

    def test_improving_healthy_ratio(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B", health=HealthStatus.DOWN),
        ))
        tracker.capture(_graph(
            _comp("a", "A", health=HealthStatus.HEALTHY),
            _comp("b", "B", health=HealthStatus.HEALTHY),
        ))
        report = tracker.analyze_trends()
        healthy_trend = next(t for t in report.trends if t.metric_name == "healthy_ratio")
        assert healthy_trend.direction == TrendDirection.IMPROVING

    def test_improving_resource_usage(self):
        """CPU going down is IMPROVING for resource_usage."""
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", cpu=80.0)))
        tracker.capture(_graph(_comp("a", "A", cpu=30.0)))
        report = tracker.analyze_trends()
        resource_trend = next(t for t in report.trends if t.metric_name == "resource_usage")
        assert resource_trend.direction == TrendDirection.IMPROVING


# ===================================================================
# 16. Trend analysis — stable
# ===================================================================

class TestTrendStable:
    def test_stable_when_values_close(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", cpu=50.0, memory=50.0)))
        tracker.capture(_graph(_comp("a", "A", cpu=51.0, memory=51.0)))
        report = tracker.analyze_trends()
        resource_trend = next(t for t in report.trends if t.metric_name == "resource_usage")
        assert resource_trend.direction == TrendDirection.STABLE

    def test_stable_resilience(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A")))
        tracker.capture(_graph(_comp("a", "A")))
        report = tracker.analyze_trends()
        resilience_trend = next(t for t in report.trends if t.metric_name == "resilience_score")
        assert resilience_trend.direction == TrendDirection.STABLE


# ===================================================================
# 17. Trend analysis — degrading
# ===================================================================

class TestTrendDegrading:
    def test_degrading_resilience(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", replicas=3, failover=True, cpu=10.0)))
        tracker.capture(_graph(_comp("a", "A", health=HealthStatus.DOWN, cpu=90.0)))
        report = tracker.analyze_trends()
        resilience_trend = next(t for t in report.trends if t.metric_name == "resilience_score")
        assert resilience_trend.direction == TrendDirection.DEGRADING

    def test_degrading_resource_usage(self):
        """CPU going UP is degrading for resource_usage."""
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", cpu=20.0)))
        tracker.capture(_graph(_comp("a", "A", cpu=80.0)))
        report = tracker.analyze_trends()
        resource_trend = next(t for t in report.trends if t.metric_name == "resource_usage")
        assert resource_trend.direction == TrendDirection.DEGRADING

    def test_degrading_healthy_ratio(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(
            _comp("a", "A", health=HealthStatus.HEALTHY),
            _comp("b", "B", health=HealthStatus.HEALTHY),
        ))
        tracker.capture(_graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B", health=HealthStatus.DOWN),
        ))
        report = tracker.analyze_trends()
        healthy_trend = next(t for t in report.trends if t.metric_name == "healthy_ratio")
        assert healthy_trend.direction == TrendDirection.DEGRADING


# ===================================================================
# 18. Trend analysis with 3+ snapshots
# ===================================================================

class TestTrendMultipleSnapshots:
    def test_three_snapshots_uses_last_two(self):
        tracker = EvolutionTracker()
        # snap 1: good
        tracker.capture(_graph(_comp("a", "A", replicas=3, failover=True)))
        # snap 2: bad
        tracker.capture(_graph(_comp("a", "A", health=HealthStatus.DOWN)))
        # snap 3: recovered
        tracker.capture(_graph(_comp("a", "A", replicas=3, failover=True)))
        report = tracker.analyze_trends()
        # Compares snap 2 vs snap 3 → improving
        resilience_trend = next(t for t in report.trends if t.metric_name == "resilience_score")
        assert resilience_trend.direction == TrendDirection.IMPROVING

    def test_four_snapshots(self):
        tracker = EvolutionTracker()
        for r in [1, 2, 3, 3]:
            tracker.capture(_graph(_comp("a", "A", replicas=r)))
        report = tracker.analyze_trends()
        assert report.snapshots is not None
        assert len(report.snapshots) == 4


# ===================================================================
# 19. Overall trend determination
# ===================================================================

class TestOverallTrend:
    def test_overall_improving(self):
        tracker = EvolutionTracker()
        # Bad state
        tracker.capture(_graph(
            _comp("a", "A", health=HealthStatus.DOWN, cpu=90.0, memory=90.0),
        ))
        # Good state
        tracker.capture(_graph(
            _comp("a", "A", health=HealthStatus.HEALTHY, replicas=3, failover=True, cpu=10.0, memory=10.0),
        ))
        report = tracker.analyze_trends()
        assert report.overall_trend == TrendDirection.IMPROVING
        assert report.improvement_count > report.regression_count

    def test_overall_degrading(self):
        tracker = EvolutionTracker()
        # Good state
        tracker.capture(_graph(
            _comp("a", "A", health=HealthStatus.HEALTHY, replicas=3, failover=True, cpu=10.0, memory=10.0),
        ))
        # Bad state
        tracker.capture(_graph(
            _comp("a", "A", health=HealthStatus.DOWN, cpu=90.0, memory=90.0),
        ))
        report = tracker.analyze_trends()
        assert report.overall_trend == TrendDirection.DEGRADING
        assert report.regression_count > report.improvement_count

    def test_overall_stable_when_equal(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A")))
        tracker.capture(_graph(_comp("a", "A")))
        report = tracker.analyze_trends()
        assert report.overall_trend == TrendDirection.STABLE


# ===================================================================
# 20. Recommendations generation
# ===================================================================

class TestRecommendations:
    def test_resilience_degrading_recommendation(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", replicas=3, failover=True, cpu=10.0)))
        tracker.capture(_graph(_comp("a", "A", health=HealthStatus.DOWN, cpu=90.0)))
        report = tracker.analyze_trends()
        assert any("Resilience is degrading" in r for r in report.recommendations)

    def test_health_declining_recommendation(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(
            _comp("a", "A", health=HealthStatus.HEALTHY),
            _comp("b", "B", health=HealthStatus.HEALTHY),
        ))
        tracker.capture(_graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B", health=HealthStatus.DOWN),
        ))
        report = tracker.analyze_trends()
        assert any("Component health declining" in r for r in report.recommendations)

    def test_replica_reducing_recommendation(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", replicas=5)))
        tracker.capture(_graph(_comp("a", "A", replicas=1)))
        report = tracker.analyze_trends()
        assert any("Redundancy is reducing" in r for r in report.recommendations)

    def test_resource_pressure_recommendation(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", cpu=10.0)))
        tracker.capture(_graph(_comp("a", "A", cpu=80.0)))
        report = tracker.analyze_trends()
        assert any("Resource pressure increasing" in r for r in report.recommendations)

    def test_no_recommendations_when_stable(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", cpu=50.0)))
        tracker.capture(_graph(_comp("a", "A", cpu=50.0)))
        report = tracker.analyze_trends()
        assert report.recommendations == []


# ===================================================================
# 21. Summary text
# ===================================================================

class TestSummary:
    def test_summary_contains_overall_trend(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A")))
        tracker.capture(_graph(_comp("a", "A")))
        report = tracker.analyze_trends()
        assert "stable" in report.summary.lower()

    def test_summary_contains_counts(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", health=HealthStatus.DOWN, cpu=90.0)))
        tracker.capture(_graph(_comp("a", "A", replicas=3, failover=True, cpu=10.0)))
        report = tracker.analyze_trends()
        assert "improving" in report.summary.lower()
        assert "metric" in report.summary.lower()

    def test_single_snapshot_summary(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A")))
        report = tracker.analyze_trends()
        assert "not enough" in report.summary.lower()


# ===================================================================
# 22. clear_history and get_snapshot_count
# ===================================================================

class TestClearAndCount:
    def test_clear_history(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A")))
        tracker.capture(_graph(_comp("a", "A")))
        assert tracker.get_snapshot_count() == 2
        tracker.clear_history()
        assert tracker.get_snapshot_count() == 0

    def test_clear_history_empty(self):
        tracker = EvolutionTracker()
        tracker.clear_history()  # should not error
        assert tracker.get_snapshot_count() == 0

    def test_capture_after_clear(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A")))
        tracker.clear_history()
        tracker.capture(_graph(_comp("a", "A")))
        assert tracker.get_snapshot_count() == 1


# ===================================================================
# 23. Edge cases
# ===================================================================

class TestEdgeCases:
    def test_single_snapshot_no_trends(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A")))
        report = tracker.analyze_trends()
        assert report.trends == []
        assert report.overall_trend == TrendDirection.STABLE
        assert report.improvement_count == 0
        assert report.regression_count == 0

    def test_all_components_down(self):
        tracker = EvolutionTracker()
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B", health=HealthStatus.DOWN),
            _comp("c", "C", health=HealthStatus.DOWN),
        )
        snap = tracker.capture(g)
        assert snap.healthy_count == 0
        assert snap.down_count == 3
        # healthy_score = 0 → resilience is low
        assert snap.resilience_score < 30.0

    def test_all_perfect(self):
        tracker = EvolutionTracker()
        g = _graph(
            _comp("a", "A", replicas=3, failover=True, cpu=0, memory=0),
            _comp("b", "B", replicas=3, failover=True, cpu=0, memory=0),
            _comp("c", "C", replicas=3, failover=True, cpu=0, memory=0),
        )
        snap = tracker.capture(g)
        assert snap.resilience_score == 100.0

    def test_very_high_replicas_cap(self):
        """Replica score capped at 20 even with replicas>>3."""
        tracker = EvolutionTracker()
        g = _graph(_comp("a", "A", replicas=100, failover=True))
        snap = tracker.capture(g)
        # replica_score = min(20, 100/3*20) = 20
        # healthy=40, replica=20, failover=20, headroom=20 → 100
        assert snap.resilience_score == 100.0

    def test_cpu_100_headroom_zero(self):
        tracker = EvolutionTracker()
        g = _graph(_comp("a", "A", cpu=100.0, memory=100.0))
        snap = tracker.capture(g)
        # headroom = (100-100)/100*20 = 0
        expected = 40.0 + (1 / 3 * 20) + 0.0 + 0.0
        assert abs(snap.resilience_score - round(expected, 2)) < 0.1

    def test_trend_change_percent_from_zero(self):
        """When previous value is zero, change_percent handles division."""
        tracker = EvolutionTracker()
        tracker.capture(_graph())  # empty → all zeros
        tracker.capture(_graph(_comp("a", "A", replicas=3, failover=True, cpu=10.0)))
        report = tracker.analyze_trends()
        # Should not raise; some change_percent may be 100.0
        assert report.trends is not None

    def test_trend_change_percent_zero_to_zero(self):
        """Both values zero → change_percent = 0."""
        tracker = EvolutionTracker()
        tracker.capture(_graph())
        tracker.capture(_graph())
        report = tracker.analyze_trends()
        for t in report.trends:
            if t.current_value == 0.0 and t.previous_value == 0.0:
                assert t.change_percent == 0.0

    def test_compare_empty_to_filled(self):
        g_a = _graph()
        g_b = _graph(_comp("a", "A"), _comp("b", "B"))
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        assert len(changes) == 2
        assert all(c.change_type == ChangeType.COMPONENT_ADDED for c in changes)

    def test_compare_filled_to_empty(self):
        g_a = _graph(_comp("a", "A"), _comp("b", "B"))
        g_b = _graph()
        tracker = EvolutionTracker()
        changes = tracker.compare(g_a, g_b)
        assert len(changes) == 2
        assert all(c.change_type == ChangeType.COMPONENT_REMOVED for c in changes)


# ===================================================================
# 24. Security summary helper
# ===================================================================

class TestSecuritySummary:
    def test_security_summary_none(self):
        c = _comp("a", "A")
        # All security defaults are False
        result = EvolutionTracker._security_summary(c)
        assert result == "none"

    def test_security_summary_all_enabled(self):
        c = _comp("a", "A")
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            network_segmented=True,
            backup_enabled=True,
            log_enabled=True,
            ids_monitored=True,
        )
        result = EvolutionTracker._security_summary(c)
        assert "enc-rest" in result
        assert "enc-transit" in result
        assert "waf" in result
        assert "rate-limit" in result
        assert "auth" in result
        assert "segmented" in result
        assert "backup" in result
        assert "log" in result
        assert "ids" in result

    def test_security_summary_partial(self):
        c = _comp("a", "A")
        c.security = SecurityProfile(encryption_at_rest=True, waf_protected=True)
        result = EvolutionTracker._security_summary(c)
        assert "enc-rest" in result
        assert "waf" in result
        assert "auth" not in result


# ===================================================================
# 25. Trend assessment text
# ===================================================================

class TestTrendAssessment:
    def test_improving_assessment(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", health=HealthStatus.DOWN)))
        tracker.capture(_graph(_comp("a", "A", health=HealthStatus.HEALTHY)))
        report = tracker.analyze_trends()
        for t in report.trends:
            if t.direction == TrendDirection.IMPROVING:
                assert "improving" in t.assessment.lower()

    def test_degrading_assessment(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", health=HealthStatus.HEALTHY)))
        tracker.capture(_graph(_comp("a", "A", health=HealthStatus.DOWN)))
        report = tracker.analyze_trends()
        for t in report.trends:
            if t.direction == TrendDirection.DEGRADING:
                assert "degrading" in t.assessment.lower()

    def test_stable_assessment(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A")))
        tracker.capture(_graph(_comp("a", "A")))
        report = tracker.analyze_trends()
        for t in report.trends:
            if t.direction == TrendDirection.STABLE:
                assert "stable" in t.assessment.lower()


# ===================================================================
# 26. Report snapshots list
# ===================================================================

class TestReportSnapshots:
    def test_report_includes_all_snapshots(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A")))
        tracker.capture(_graph(_comp("a", "A")))
        tracker.capture(_graph(_comp("a", "A")))
        report = tracker.analyze_trends()
        assert len(report.snapshots) == 3


# ===================================================================
# 27. Failover coverage trend
# ===================================================================

class TestFailoverCoverageTrend:
    def test_failover_improving(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", failover=False), _comp("b", "B", failover=False)))
        tracker.capture(_graph(_comp("a", "A", failover=True), _comp("b", "B", failover=True)))
        report = tracker.analyze_trends()
        failover_trend = next(t for t in report.trends if t.metric_name == "failover_coverage")
        assert failover_trend.direction == TrendDirection.IMPROVING

    def test_failover_degrading(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", failover=True), _comp("b", "B", failover=True)))
        tracker.capture(_graph(_comp("a", "A", failover=False), _comp("b", "B", failover=False)))
        report = tracker.analyze_trends()
        failover_trend = next(t for t in report.trends if t.metric_name == "failover_coverage")
        assert failover_trend.direction == TrendDirection.DEGRADING


# ===================================================================
# 28. Replica average trend
# ===================================================================

class TestReplicaAverageTrend:
    def test_replica_average_improving(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", replicas=1)))
        tracker.capture(_graph(_comp("a", "A", replicas=5)))
        report = tracker.analyze_trends()
        replica_trend = next(t for t in report.trends if t.metric_name == "replica_average")
        assert replica_trend.direction == TrendDirection.IMPROVING

    def test_replica_average_degrading(self):
        tracker = EvolutionTracker()
        tracker.capture(_graph(_comp("a", "A", replicas=5)))
        tracker.capture(_graph(_comp("a", "A", replicas=1)))
        report = tracker.analyze_trends()
        replica_trend = next(t for t in report.trends if t.metric_name == "replica_average")
        assert replica_trend.direction == TrendDirection.DEGRADING
