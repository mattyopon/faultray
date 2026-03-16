"""Tests for failure injection scheduler."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.injection_scheduler import (
    BlackoutWindow,
    EscalationLevel,
    InjectionResult,
    InjectionScheduler,
    InjectionTarget,
    InjectionType,
    ScheduleFrequency,
    ScheduledInjection,
    SchedulerReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 2,
    cpu: float = 30.0,
    failover: bool = False,
    autoscale: bool = False,
    backup: bool = False,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.metrics.cpu_percent = cpu
    if failover:
        c.failover.enabled = True
    if autoscale:
        c.autoscaling.enabled = True
    if backup:
        c.security.backup_enabled = True
    return c


def _simple_infra() -> InfraGraph:
    g = InfraGraph()
    g.add_component(_comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER))
    g.add_component(_comp("api", "API Server", replicas=3))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE, replicas=1))
    g.add_component(_comp("cache", "Redis", ComponentType.CACHE, replicas=2))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    g.add_dependency(Dependency(source_id="api", target_id="cache"))
    return g


# ---------------------------------------------------------------------------
# Tests: Schedule management
# ---------------------------------------------------------------------------


class TestScheduleManagement:
    def test_schedule_injection(self):
        scheduler = InjectionScheduler()
        target = InjectionTarget(
            component_id="api",
            component_name="API Server",
            injection_type=InjectionType.COMPONENT_KILL,
        )
        inj = scheduler.schedule(
            name="Kill API",
            description="Test API resilience",
            target=target,
            frequency=ScheduleFrequency.WEEKLY,
        )
        assert inj.id.startswith("inj-")
        assert inj.name == "Kill API"
        assert inj.enabled is True
        assert inj.next_run != ""

    def test_unschedule(self):
        scheduler = InjectionScheduler()
        target = InjectionTarget("api", "API", InjectionType.COMPONENT_KILL)
        inj = scheduler.schedule("Test", "Desc", target, ScheduleFrequency.DAILY)
        assert scheduler.unschedule(inj.id) is True
        assert scheduler.unschedule(inj.id) is False  # Already removed

    def test_pause_resume(self):
        scheduler = InjectionScheduler()
        target = InjectionTarget("api", "API", InjectionType.COMPONENT_KILL)
        inj = scheduler.schedule("Test", "Desc", target, ScheduleFrequency.DAILY)
        assert inj.enabled is True
        assert scheduler.pause(inj.id) is True
        assert scheduler._injections[inj.id].enabled is False
        assert scheduler.resume(inj.id) is True
        assert scheduler._injections[inj.id].enabled is True

    def test_pause_nonexistent(self):
        scheduler = InjectionScheduler()
        assert scheduler.pause("nonexistent") is False
        assert scheduler.resume("nonexistent") is False

    def test_auto_schedule(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        created = scheduler.auto_schedule(g)
        assert len(created) == 4  # One per component
        for inj in created:
            assert inj.enabled is True
            assert inj.frequency == ScheduleFrequency.WEEKLY

    def test_auto_schedule_custom_params(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        created = scheduler.auto_schedule(
            g,
            frequency=ScheduleFrequency.MONTHLY,
            escalation=EscalationLevel.PARTIAL,
        )
        for inj in created:
            assert inj.frequency == ScheduleFrequency.MONTHLY
            assert inj.target.escalation == EscalationLevel.PARTIAL


# ---------------------------------------------------------------------------
# Tests: Injection simulation
# ---------------------------------------------------------------------------


class TestSimulateInjection:
    def test_kill_with_replicas(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        target = InjectionTarget("api", "API Server", InjectionType.COMPONENT_KILL)
        inj = scheduler.schedule("Kill API", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is True  # API has 3 replicas
        assert "replicas remaining" in result.observations[0]

    def test_kill_without_replicas(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        target = InjectionTarget("db", "Database", InjectionType.COMPONENT_KILL)
        inj = scheduler.schedule("Kill DB", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is False  # DB has 1 replica
        assert "no replicas" in result.observations[0]

    def test_latency_spike_with_timeout(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        c = _comp("api", "API")
        c.capacity.timeout_seconds = 30.0
        g.add_component(c)
        target = InjectionTarget("api", "API", InjectionType.LATENCY_SPIKE)
        inj = scheduler.schedule("Latency", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is True

    def test_latency_spike_low_timeout(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        c = _comp("api", "API")
        c.capacity.timeout_seconds = 2.0
        g.add_component(c)
        target = InjectionTarget("api", "API", InjectionType.LATENCY_SPIKE)
        inj = scheduler.schedule("Latency", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is False

    def test_cpu_stress_high_util(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("api", "API", cpu=80.0))
        target = InjectionTarget("api", "API", InjectionType.CPU_STRESS)
        inj = scheduler.schedule("CPU", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is False

    def test_cpu_stress_low_util(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("api", "API", cpu=20.0))
        target = InjectionTarget("api", "API", InjectionType.CPU_STRESS)
        inj = scheduler.schedule("CPU", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is True

    def test_memory_pressure(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("api", "API", cpu=20.0))
        target = InjectionTarget("api", "API", InjectionType.MEMORY_PRESSURE)
        inj = scheduler.schedule("Memory", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None

    def test_disk_full_with_backup(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, backup=True))
        target = InjectionTarget("db", "DB", InjectionType.DISK_FULL)
        inj = scheduler.schedule("Disk", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is True

    def test_disk_full_without_backup(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        target = InjectionTarget("db", "DB", InjectionType.DISK_FULL)
        inj = scheduler.schedule("Disk", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is False

    def test_traffic_flood_with_autoscale(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("api", "API", autoscale=True))
        target = InjectionTarget("api", "API", InjectionType.TRAFFIC_FLOOD)
        inj = scheduler.schedule("Traffic", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is True

    def test_traffic_flood_no_autoscale(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=1))
        target = InjectionTarget("api", "API", InjectionType.TRAFFIC_FLOOD)
        inj = scheduler.schedule("Traffic", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is False

    def test_traffic_flood_many_replicas(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=5))
        target = InjectionTarget("api", "API", InjectionType.TRAFFIC_FLOOD)
        inj = scheduler.schedule("Traffic", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is True

    def test_network_partition_with_failover(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, failover=True))
        target = InjectionTarget("db", "DB", InjectionType.NETWORK_PARTITION)
        inj = scheduler.schedule("Partition", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is True

    def test_network_partition_no_failover(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        target = InjectionTarget("db", "DB", InjectionType.NETWORK_PARTITION)
        inj = scheduler.schedule("Partition", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is False

    def test_dependency_timeout_with_cb(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        g.add_component(_comp("ext", "External", ComponentType.EXTERNAL_API))
        dep = Dependency(source_id="api", target_id="ext")
        dep.circuit_breaker.enabled = True
        g.add_dependency(dep)
        target = InjectionTarget("ext", "External", InjectionType.DEPENDENCY_TIMEOUT)
        inj = scheduler.schedule("Timeout", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is True

    def test_dependency_timeout_no_cb(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        g.add_component(_comp("ext", "External", ComponentType.EXTERNAL_API))
        g.add_dependency(Dependency(source_id="api", target_id="ext"))
        target = InjectionTarget("ext", "External", InjectionType.DEPENDENCY_TIMEOUT)
        inj = scheduler.schedule("Timeout", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.passed is False

    def test_simulate_nonexistent(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        result = scheduler.simulate_injection(g, "nonexistent")
        assert result is None

    def test_simulate_missing_component(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()  # Empty graph
        target = InjectionTarget("missing", "Missing", InjectionType.COMPONENT_KILL)
        inj = scheduler.schedule("Test", "Desc", target, ScheduleFrequency.DAILY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is None

    def test_run_count_updates(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        target = InjectionTarget("api", "API Server", InjectionType.COMPONENT_KILL)
        inj = scheduler.schedule("Kill", "Test", target, ScheduleFrequency.WEEKLY)
        scheduler.simulate_injection(g, inj.id)
        assert inj.run_count == 1
        assert inj.pass_count == 1
        assert inj.last_run != ""

    def test_large_blast_radius_fails(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        g.add_component(_comp("root", "Root", replicas=3))
        for i in range(6):
            g.add_component(_comp(f"dep-{i}", f"Dep {i}"))
            g.add_dependency(Dependency(source_id=f"dep-{i}", target_id="root"))
        target = InjectionTarget("root", "Root", InjectionType.COMPONENT_KILL)
        inj = scheduler.schedule("Kill Root", "Test", target, ScheduleFrequency.WEEKLY)
        result = scheduler.simulate_injection(g, inj.id)
        assert result is not None
        assert result.blast_radius >= 6


# ---------------------------------------------------------------------------
# Tests: Auto-escalation
# ---------------------------------------------------------------------------


class TestAutoEscalation:
    def test_escalation_after_consistent_pass(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        target = InjectionTarget("api", "API Server", InjectionType.COMPONENT_KILL)
        inj = scheduler.schedule("Kill", "Test", target, ScheduleFrequency.WEEKLY,
                                 auto_escalate=True)
        # Run 3 times to trigger escalation
        for _ in range(3):
            scheduler.simulate_injection(g, inj.id)
        assert inj.target.escalation != EscalationLevel.CANARY

    def test_no_escalation_when_disabled(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        target = InjectionTarget("api", "API Server", InjectionType.COMPONENT_KILL)
        inj = scheduler.schedule("Kill", "Test", target, ScheduleFrequency.WEEKLY,
                                 auto_escalate=False)
        for _ in range(5):
            scheduler.simulate_injection(g, inj.id)
        assert inj.target.escalation == EscalationLevel.CANARY


# ---------------------------------------------------------------------------
# Tests: Blackout windows
# ---------------------------------------------------------------------------


class TestBlackoutWindows:
    def test_default_blackouts(self):
        scheduler = InjectionScheduler()
        assert len(scheduler._blackouts) >= 2

    def test_in_blackout(self):
        scheduler = InjectionScheduler()
        # Monday 10:00 UTC — should be in business hours blackout
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc)  # Monday
        assert scheduler.is_in_blackout(dt) is True

    def test_not_in_blackout(self):
        scheduler = InjectionScheduler()
        # Remove default blackouts and add only a specific one
        scheduler._blackouts = [BlackoutWindow(
            name="Weekday Peak",
            start_hour=9,
            end_hour=17,
            days_of_week=[0, 1, 2, 3, 4],
            reason="Business hours",
        )]
        # Sunday 2:00 UTC — not in weekday peak
        dt = datetime(2026, 3, 15, 2, 0, tzinfo=timezone.utc)  # Sunday
        assert scheduler.is_in_blackout(dt) is False

    def test_add_blackout(self):
        scheduler = InjectionScheduler()
        original = len(scheduler._blackouts)
        scheduler.add_blackout(BlackoutWindow(
            name="Custom", start_hour=0, end_hour=6,
            days_of_week=[], reason="Maintenance",
        ))
        assert len(scheduler._blackouts) == original + 1

    def test_remove_blackout(self):
        scheduler = InjectionScheduler()
        assert scheduler.remove_blackout("Business Hours Peak") is True
        assert scheduler.remove_blackout("Nonexistent") is False


# ---------------------------------------------------------------------------
# Tests: Report
# ---------------------------------------------------------------------------


class TestReport:
    def test_report_structure(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        scheduler.auto_schedule(g)
        report = scheduler.get_report(g)
        assert report.total_scheduled == 4
        assert report.active_count == 4
        assert report.paused_count == 0
        assert report.coverage_score == 100.0

    def test_report_with_results(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        created = scheduler.auto_schedule(g)
        for inj in created:
            scheduler.simulate_injection(g, inj.id)
        report = scheduler.get_report(g)
        assert len(report.recent_results) == 4
        assert report.pass_rate >= 0

    def test_report_recommendations(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        # Only schedule for one component — low coverage
        target = InjectionTarget("api", "API", InjectionType.COMPONENT_KILL)
        scheduler.schedule("Test", "Test", target, ScheduleFrequency.WEEKLY)
        report = scheduler.get_report(g)
        # Should recommend better coverage
        assert len(report.recommendations) >= 1

    def test_report_empty_scheduler(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        report = scheduler.get_report(g)
        assert report.total_scheduled == 0
        assert report.pass_rate == 0


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_injection_types(self):
        assert len(InjectionType) == 8

    def test_schedule_frequencies(self):
        assert len(ScheduleFrequency) == 5

    def test_escalation_levels(self):
        assert len(EscalationLevel) == 4


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_graph_auto_schedule(self):
        scheduler = InjectionScheduler()
        g = InfraGraph()
        created = scheduler.auto_schedule(g)
        assert len(created) == 0

    def test_schedule_with_tags(self):
        scheduler = InjectionScheduler()
        target = InjectionTarget("api", "API", InjectionType.COMPONENT_KILL)
        inj = scheduler.schedule(
            "Test", "Test", target, ScheduleFrequency.WEEKLY,
            tags=["production", "critical"],
        )
        assert inj.tags == ["production", "critical"]

    def test_all_frequencies(self):
        scheduler = InjectionScheduler()
        now = datetime.now(timezone.utc)
        for freq in ScheduleFrequency:
            next_run = scheduler._calculate_next_run(now, freq)
            assert next_run > now

    def test_escalation_ceiling(self):
        scheduler = InjectionScheduler()
        g = _simple_infra()
        target = InjectionTarget("api", "API Server", InjectionType.COMPONENT_KILL,
                                 escalation=EscalationLevel.CASCADING)
        inj = scheduler.schedule("Kill", "Test", target, ScheduleFrequency.WEEKLY)
        for _ in range(10):
            scheduler.simulate_injection(g, inj.id)
        # Should stay at CASCADING (max level)
        assert inj.target.escalation == EscalationLevel.CASCADING

    def test_multiple_schedules_unique_ids(self):
        scheduler = InjectionScheduler()
        target = InjectionTarget("api", "API", InjectionType.COMPONENT_KILL)
        ids = set()
        for _ in range(10):
            inj = scheduler.schedule("Test", "Test", target, ScheduleFrequency.DAILY)
            ids.add(inj.id)
        assert len(ids) == 10
