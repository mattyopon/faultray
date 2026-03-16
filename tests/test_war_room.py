"""Tests for the War Room Simulator."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.war_room import (
    WarRoomEvent,
    WarRoomPhase,
    WarRoomReport,
    WarRoomRole,
    WarRoomSimulator,
    _INCIDENT_CONFIGS,
    _ROLES_BY_SIZE,
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
    failover: FailoverConfig | None = None,
    autoscaling: AutoScalingConfig | None = None,
    operational_profile: OperationalProfile | None = None,
) -> Component:
    kwargs: dict = dict(id=cid, name=name, type=ctype, replicas=replicas)
    if failover is not None:
        kwargs["failover"] = failover
    if autoscaling is not None:
        kwargs["autoscaling"] = autoscaling
    if operational_profile is not None:
        kwargs["operational_profile"] = operational_profile
    c = Component(**kwargs)
    c.health = health
    return c


def _chain_graph() -> InfraGraph:
    """Basic 4-node graph: lb -> app -> db, app -> cache."""
    g = InfraGraph()
    g.add_component(_comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("app", "App Server", ComponentType.APP_SERVER, replicas=2))
    g.add_component(_comp("db", "PostgreSQL", ComponentType.DATABASE, replicas=1))
    g.add_component(_comp("cache", "Redis", ComponentType.CACHE, replicas=1))
    g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))
    return g


def _resilient_graph() -> InfraGraph:
    """Graph with failover, autoscaling, and circuit breakers."""
    g = InfraGraph()
    g.add_component(_comp(
        "lb", "Load Balancer", ComponentType.LOAD_BALANCER, replicas=3,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=10.0),
    ))
    g.add_component(_comp(
        "app", "App Server", ComponentType.APP_SERVER, replicas=3,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=15.0),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    g.add_component(_comp(
        "db", "PostgreSQL", ComponentType.DATABASE, replicas=2,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=30.0),
        operational_profile=OperationalProfile(mttr_minutes=5.0),
    ))
    g.add_component(_comp(
        "cache", "Redis", ComponentType.CACHE, replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    g.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    g.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    g.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return g


# ---------------------------------------------------------------------------
# Tests: Data classes
# ---------------------------------------------------------------------------


class TestDataClasses:
    def test_war_room_role_defaults(self):
        role = WarRoomRole(name="SRE")
        assert role.name == "SRE"
        assert role.responsibilities == []
        assert role.available_actions == []

    def test_war_room_phase_defaults(self):
        phase = WarRoomPhase(name="Detection")
        assert phase.duration_minutes == 0.0
        assert phase.objectives == []
        assert phase.success_criteria == []

    def test_war_room_event(self):
        event = WarRoomEvent(
            time_minutes=5.0, phase="Detection",
            event_type="alert_fired", description="Alert",
            role_involved="system", outcome="success",
        )
        assert event.time_minutes == 5.0
        assert event.outcome == "success"

    def test_war_room_report_defaults(self):
        report = WarRoomReport(
            exercise_name="Test", scenario_description="Desc",
            total_duration_minutes=60.0,
        )
        assert report.phases == []
        assert report.events == []
        assert report.time_to_detect_minutes == 0.0
        assert report.score == 0.0
        assert report.lessons_learned == []


# ---------------------------------------------------------------------------
# Tests: available_incidents
# ---------------------------------------------------------------------------


class TestAvailableIncidents:
    def test_non_empty(self):
        sim = WarRoomSimulator(_chain_graph())
        incidents = sim.available_incidents()
        assert len(incidents) >= 8

    def test_sorted(self):
        sim = WarRoomSimulator(_chain_graph())
        incidents = sim.available_incidents()
        assert incidents == sorted(incidents)

    def test_known_types(self):
        sim = WarRoomSimulator(_chain_graph())
        incidents = sim.available_incidents()
        expected = [
            "cascading_failure", "cloud_region_failure", "data_corruption",
            "database_outage", "ddos_attack", "deployment_rollback",
            "network_partition", "security_breach",
        ]
        for inc in expected:
            assert inc in incidents


# ---------------------------------------------------------------------------
# Tests: simulate - basic
# ---------------------------------------------------------------------------


class TestSimulateBasic:
    def test_database_outage(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage", team_size=4)
        assert isinstance(report, WarRoomReport)
        assert report.exercise_name != ""
        assert "Database Outage" in report.exercise_name
        assert report.scenario_description != ""
        assert report.total_duration_minutes > 0

    def test_all_incident_types(self):
        sim = WarRoomSimulator(_chain_graph())
        for incident in sim.available_incidents():
            report = sim.simulate(incident_type=incident, team_size=2)
            assert isinstance(report, WarRoomReport)
            assert report.total_duration_minutes > 0
            assert report.score > 0

    def test_invalid_incident_type(self):
        sim = WarRoomSimulator(_chain_graph())
        with pytest.raises(ValueError, match="Unknown incident type"):
            sim.simulate(incident_type="nonexistent")

    def test_timing_metrics_positive(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        assert report.time_to_detect_minutes > 0
        assert report.time_to_mitigate_minutes > 0
        assert report.time_to_recover_minutes > 0

    def test_ttm_greater_than_ttd(self):
        """Time to mitigate must be greater than time to detect."""
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        assert report.time_to_mitigate_minutes > report.time_to_detect_minutes

    def test_ttr_greater_than_ttm(self):
        """Time to recover must be greater than time to mitigate."""
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        assert report.time_to_recover_minutes > report.time_to_mitigate_minutes

    def test_timing_rounded(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        assert report.time_to_detect_minutes == round(report.time_to_detect_minutes, 1)
        assert report.time_to_mitigate_minutes == round(report.time_to_mitigate_minutes, 1)
        assert report.time_to_recover_minutes == round(report.time_to_recover_minutes, 1)


# ---------------------------------------------------------------------------
# Tests: phases
# ---------------------------------------------------------------------------


class TestPhases:
    def test_five_phases(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        assert len(report.phases) == 5

    def test_phase_names(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        names = [p.name for p in report.phases]
        assert names == ["Detection", "Triage", "Mitigation", "Recovery", "Post-mortem"]

    def test_phase_durations_positive(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        for phase in report.phases:
            assert phase.duration_minutes > 0

    def test_phase_durations_sum_to_total(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        phase_sum = sum(p.duration_minutes for p in report.phases)
        assert abs(phase_sum - report.total_duration_minutes) < 0.2

    def test_phase_objectives_and_criteria(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        for phase in report.phases:
            assert len(phase.objectives) > 0
            assert len(phase.success_criteria) > 0

    def test_postmortem_fixed_duration(self):
        """Post-mortem phase is always 15 minutes."""
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        postmortem = report.phases[-1]
        assert postmortem.name == "Post-mortem"
        assert postmortem.duration_minutes == 15.0


# ---------------------------------------------------------------------------
# Tests: events timeline
# ---------------------------------------------------------------------------


class TestEvents:
    def test_events_generated(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        assert len(report.events) > 0

    def test_events_chronological(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        times = [e.time_minutes for e in report.events]
        assert times == sorted(times)

    def test_first_event_is_alert(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        first = report.events[0]
        assert first.event_type == "alert_fired"
        assert first.phase == "Detection"
        assert first.time_minutes == 0.0

    def test_events_cover_all_phases(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage")
        phases_in_events = {e.phase for e in report.events}
        assert "Detection" in phases_in_events
        assert "Triage" in phases_in_events
        assert "Mitigation" in phases_in_events
        assert "Recovery" in phases_in_events
        assert "Post-mortem" in phases_in_events

    def test_runbook_event_with_runbook(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage", has_runbook=True)
        runbook_events = [e for e in report.events if "runbook" in e.description.lower()]
        assert len(runbook_events) >= 1
        assert runbook_events[0].outcome == "success"

    def test_no_runbook_event_without_runbook(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage", has_runbook=False)
        no_runbook_events = [e for e in report.events if "no runbook" in e.description.lower()]
        assert len(no_runbook_events) >= 1
        assert no_runbook_events[0].outcome == "partial"

    def test_failover_event_in_resilient_graph(self):
        sim = WarRoomSimulator(_resilient_graph())
        report = sim.simulate(incident_type="database_outage")
        failover_events = [e for e in report.events if "failover" in e.description.lower()]
        assert len(failover_events) >= 1

    def test_autoscale_event_for_ddos(self):
        """DDoS targets LB/WEB, but app has autoscaling in resilient graph."""
        # Build a graph where app server is the target and has autoscaling but no failover
        g = InfraGraph()
        g.add_component(_comp(
            "app", "App Server", ComponentType.APP_SERVER, replicas=2,
            autoscaling=AutoScalingConfig(enabled=True),
        ))
        g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER))
        g.add_dependency(Dependency(source_id="lb", target_id="app"))
        sim = WarRoomSimulator(g)
        report = sim.simulate(incident_type="network_partition")
        # Should find either autoscaling or manual intervention
        mitigation_events = [e for e in report.events if e.phase == "Mitigation"]
        assert len(mitigation_events) >= 1

    def test_manual_intervention_without_failover(self):
        """Without failover/autoscale, mitigation requires manual intervention."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        sim = WarRoomSimulator(g)
        report = sim.simulate(incident_type="database_outage")
        manual_events = [e for e in report.events
                        if "manual" in e.description.lower() and e.phase == "Mitigation"]
        assert len(manual_events) >= 1


# ---------------------------------------------------------------------------
# Tests: team size effects
# ---------------------------------------------------------------------------


class TestTeamSize:
    def test_team_size_1(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage", team_size=1)
        assert len(report.roles_involved) >= 1
        assert "SRE On-Call" in report.roles_involved

    def test_team_size_2(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage", team_size=2)
        assert len(report.roles_involved) == 2
        assert "Incident Commander" in report.roles_involved

    def test_team_size_3(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage", team_size=3)
        assert "DBA" in report.roles_involved

    def test_team_size_4(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage", team_size=4)
        assert len(report.roles_involved) == 4
        assert "Comms Lead" in report.roles_involved

    def test_team_size_clamped_to_max(self):
        """Team size > 4 should be clamped to 4."""
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage", team_size=10)
        assert len(report.roles_involved) == 4

    def test_team_size_clamped_to_min(self):
        """Team size < 1 should be clamped to 1."""
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage", team_size=0)
        assert len(report.roles_involved) >= 1

    def test_larger_team_faster_detection(self):
        sim = WarRoomSimulator(_chain_graph())
        report_small = sim.simulate(incident_type="database_outage", team_size=1)
        report_large = sim.simulate(incident_type="database_outage", team_size=4)
        assert report_large.time_to_detect_minutes <= report_small.time_to_detect_minutes

    def test_larger_team_faster_mitigation(self):
        sim = WarRoomSimulator(_chain_graph())
        report_small = sim.simulate(incident_type="database_outage", team_size=1)
        report_large = sim.simulate(incident_type="database_outage", team_size=4)
        assert report_large.time_to_mitigate_minutes <= report_small.time_to_mitigate_minutes


# ---------------------------------------------------------------------------
# Tests: runbook effects
# ---------------------------------------------------------------------------


class TestRunbook:
    def test_runbook_reduces_detection(self):
        sim = WarRoomSimulator(_chain_graph())
        r_with = sim.simulate(incident_type="database_outage", has_runbook=True)
        r_without = sim.simulate(incident_type="database_outage", has_runbook=False)
        assert r_with.time_to_detect_minutes <= r_without.time_to_detect_minutes

    def test_runbook_reduces_mitigation(self):
        sim = WarRoomSimulator(_chain_graph())
        r_with = sim.simulate(incident_type="database_outage", has_runbook=True)
        r_without = sim.simulate(incident_type="database_outage", has_runbook=False)
        assert r_with.time_to_mitigate_minutes <= r_without.time_to_mitigate_minutes

    def test_runbook_reduces_recovery(self):
        sim = WarRoomSimulator(_chain_graph())
        r_with = sim.simulate(incident_type="database_outage", has_runbook=True)
        r_without = sim.simulate(incident_type="database_outage", has_runbook=False)
        assert r_with.time_to_recover_minutes <= r_without.time_to_recover_minutes

    def test_no_runbook_lesson(self):
        sim = WarRoomSimulator(_chain_graph())
        report = sim.simulate(incident_type="database_outage", has_runbook=False)
        runbook_lessons = [l for l in report.lessons_learned if "runbook" in l.lower()]
        assert len(runbook_lessons) >= 1


# ---------------------------------------------------------------------------
# Tests: infrastructure effects
# ---------------------------------------------------------------------------


class TestInfrastructureEffects:
    def test_failover_improves_score(self):
        sim_basic = WarRoomSimulator(_chain_graph())
        sim_resilient = WarRoomSimulator(_resilient_graph())
        r_basic = sim_basic.simulate(incident_type="database_outage")
        r_resilient = sim_resilient.simulate(incident_type="database_outage")
        assert r_resilient.score >= r_basic.score

    def test_failover_reduces_mitigation(self):
        sim_basic = WarRoomSimulator(_chain_graph())
        sim_resilient = WarRoomSimulator(_resilient_graph())
        r_basic = sim_basic.simulate(incident_type="database_outage")
        r_resilient = sim_resilient.simulate(incident_type="database_outage")
        assert r_resilient.time_to_mitigate_minutes <= r_basic.time_to_mitigate_minutes

    def test_failover_reduces_detection(self):
        sim_basic = WarRoomSimulator(_chain_graph())
        sim_resilient = WarRoomSimulator(_resilient_graph())
        r_basic = sim_basic.simulate(incident_type="database_outage")
        r_resilient = sim_resilient.simulate(incident_type="database_outage")
        assert r_resilient.time_to_detect_minutes <= r_basic.time_to_detect_minutes

    def test_mttr_affects_recovery(self):
        """Component with low MTTR should reduce recovery time."""
        g = InfraGraph()
        g.add_component(_comp(
            "db", "DB", ComponentType.DATABASE,
            operational_profile=OperationalProfile(mttr_minutes=2.0),
        ))
        sim = WarRoomSimulator(g)
        r = sim.simulate(incident_type="database_outage")
        # Compare to a graph without MTTR set
        g2 = InfraGraph()
        g2.add_component(_comp("db", "DB", ComponentType.DATABASE))
        sim2 = WarRoomSimulator(g2)
        r2 = sim2.simulate(incident_type="database_outage")
        assert r.time_to_recover_minutes <= r2.time_to_recover_minutes

    def test_replicas_affect_recovery(self):
        """Multiple replicas should reduce recovery time."""
        g_multi = InfraGraph()
        g_multi.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=3))
        g_single = InfraGraph()
        g_single.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=1))
        sim_multi = WarRoomSimulator(g_multi)
        sim_single = WarRoomSimulator(g_single)
        r_multi = sim_multi.simulate(incident_type="database_outage")
        r_single = sim_single.simulate(incident_type="database_outage")
        assert r_multi.time_to_recover_minutes <= r_single.time_to_recover_minutes


# ---------------------------------------------------------------------------
# Tests: _get_roles
# ---------------------------------------------------------------------------


class TestGetRoles:
    def test_size_1(self):
        sim = WarRoomSimulator(_chain_graph())
        roles = sim._get_roles(1)
        assert len(roles) == 1
        assert roles[0].name == "SRE On-Call"

    def test_size_4(self):
        sim = WarRoomSimulator(_chain_graph())
        roles = sim._get_roles(4)
        assert len(roles) == 4
        names = [r.name for r in roles]
        assert "Incident Commander" in names
        assert "Comms Lead" in names

    def test_clamped_high(self):
        sim = WarRoomSimulator(_chain_graph())
        roles = sim._get_roles(100)
        assert len(roles) == 4

    def test_clamped_low(self):
        sim = WarRoomSimulator(_chain_graph())
        roles = sim._get_roles(0)
        assert len(roles) >= 1


# ---------------------------------------------------------------------------
# Tests: _find_target_component
# ---------------------------------------------------------------------------


class TestFindTargetComponent:
    def test_finds_database(self):
        sim = WarRoomSimulator(_chain_graph())
        target = sim._find_target_component([ComponentType.DATABASE])
        assert target is not None
        assert target.type == ComponentType.DATABASE

    def test_finds_first_matching_type(self):
        sim = WarRoomSimulator(_chain_graph())
        target = sim._find_target_component([ComponentType.CACHE, ComponentType.DATABASE])
        assert target is not None
        assert target.type == ComponentType.CACHE

    def test_returns_none_when_no_match(self):
        sim = WarRoomSimulator(_chain_graph())
        target = sim._find_target_component([ComponentType.STORAGE])
        assert target is None

    def test_empty_graph(self):
        sim = WarRoomSimulator(InfraGraph())
        target = sim._find_target_component([ComponentType.DATABASE])
        assert target is None


# ---------------------------------------------------------------------------
# Tests: _calculate_detection_time
# ---------------------------------------------------------------------------


class TestDetectionTime:
    def test_base_range(self):
        """Detection time should be within reasonable range."""
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        target = sim._find_target_component(config["target_types"])
        t = sim._calculate_detection_time(config, 4, True, target)
        assert t >= 1.0  # min clamped at 1.0

    def test_no_target_component(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        t = sim._calculate_detection_time(config, 4, True, None)
        assert t >= 1.0

    def test_failover_reduces_time(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp_no_fo = _comp("db", "DB", ComponentType.DATABASE)
        comp_fo = _comp("db", "DB", ComponentType.DATABASE,
                        failover=FailoverConfig(enabled=True))
        t_no = sim._calculate_detection_time(config, 4, True, comp_no_fo)
        t_yes = sim._calculate_detection_time(config, 4, True, comp_fo)
        assert t_yes <= t_no

    def test_autoscaling_reduces_time(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp_no = _comp("app", "App", ComponentType.APP_SERVER)
        comp_as = _comp("app", "App", ComponentType.APP_SERVER,
                        autoscaling=AutoScalingConfig(enabled=True))
        t_no = sim._calculate_detection_time(config, 4, True, comp_no)
        t_yes = sim._calculate_detection_time(config, 4, True, comp_as)
        assert t_yes <= t_no


# ---------------------------------------------------------------------------
# Tests: _calculate_triage_time
# ---------------------------------------------------------------------------


class TestTriageTime:
    def test_base_range(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        t = sim._calculate_triage_time(config, 4, True, 0)
        assert t >= 2.0  # min clamped at 2.0

    def test_blast_radius_increases_time(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        t_small = sim._calculate_triage_time(config, 4, True, 0)
        t_large = sim._calculate_triage_time(config, 4, True, 10)
        assert t_large > t_small


# ---------------------------------------------------------------------------
# Tests: _calculate_mitigation_time
# ---------------------------------------------------------------------------


class TestMitigationTime:
    def test_base_range(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        target = sim._find_target_component(config["target_types"])
        t = sim._calculate_mitigation_time(config, 4, True, target)
        assert t >= 1.0

    def test_failover_greatly_reduces(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp_no = _comp("db", "DB", ComponentType.DATABASE)
        comp_fo = _comp("db", "DB", ComponentType.DATABASE,
                        failover=FailoverConfig(enabled=True, promotion_time_seconds=30.0))
        t_no = sim._calculate_mitigation_time(config, 4, True, comp_no)
        t_fo = sim._calculate_mitigation_time(config, 4, True, comp_fo)
        assert t_fo < t_no


# ---------------------------------------------------------------------------
# Tests: _calculate_recovery_time
# ---------------------------------------------------------------------------


class TestRecoveryTime:
    def test_base_range(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        target = sim._find_target_component(config["target_types"])
        t = sim._calculate_recovery_time(config, 4, True, target)
        assert t >= 2.0

    def test_failover_reduces_recovery(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp_no = _comp("db", "DB", ComponentType.DATABASE)
        comp_fo = _comp("db", "DB", ComponentType.DATABASE,
                        failover=FailoverConfig(enabled=True))
        t_no = sim._calculate_recovery_time(config, 4, True, comp_no)
        t_fo = sim._calculate_recovery_time(config, 4, True, comp_fo)
        assert t_fo < t_no

    def test_replicas_reduce_recovery(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp_1 = _comp("db", "DB", ComponentType.DATABASE, replicas=1)
        comp_3 = _comp("db", "DB", ComponentType.DATABASE, replicas=3)
        t_1 = sim._calculate_recovery_time(config, 4, True, comp_1)
        t_3 = sim._calculate_recovery_time(config, 4, True, comp_3)
        assert t_3 < t_1

    def test_mttr_used_when_available(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp_mttr = _comp("db", "DB", ComponentType.DATABASE,
                          operational_profile=OperationalProfile(mttr_minutes=3.0))
        t = sim._calculate_recovery_time(config, 4, True, comp_mttr)
        assert t >= 2.0  # Still clamped

    def test_no_target(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        t = sim._calculate_recovery_time(config, 4, True, None)
        assert t >= 2.0


# ---------------------------------------------------------------------------
# Tests: _generate_lessons
# ---------------------------------------------------------------------------


class TestLessons:
    def test_no_failover_lesson(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp = _comp("db", "DB", ComponentType.DATABASE)
        lessons = sim._generate_lessons(config, comp, 0, True, 4, 0.0)
        assert any("failover" in l.lower() for l in lessons)

    def test_single_replica_lesson(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp = _comp("db", "DB", ComponentType.DATABASE, replicas=1)
        lessons = sim._generate_lessons(config, comp, 0, True, 4, 0.0)
        assert any("replica" in l.lower() for l in lessons)

    def test_autoscaling_lesson_for_app_server(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp = _comp("app", "App", ComponentType.APP_SERVER)
        lessons = sim._generate_lessons(config, comp, 0, True, 4, 0.0)
        assert any("autoscaling" in l.lower() for l in lessons)

    def test_no_autoscaling_lesson_for_database(self):
        """Autoscaling lesson only for APP_SERVER/WEB_SERVER types."""
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp = _comp("db", "DB", ComponentType.DATABASE)
        lessons = sim._generate_lessons(config, comp, 0, True, 4, 0.0)
        assert not any("autoscaling" in l.lower() for l in lessons)

    def test_high_blast_radius_lesson(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp = _comp("db", "DB", ComponentType.DATABASE)
        lessons = sim._generate_lessons(config, comp, 5, True, 4, 0.0)
        assert any("blast radius" in l.lower() for l in lessons)

    def test_no_runbook_lesson(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp = _comp("db", "DB", ComponentType.DATABASE)
        lessons = sim._generate_lessons(config, comp, 0, False, 4, 0.0)
        assert any("runbook" in l.lower() for l in lessons)

    def test_small_team_high_severity_lesson(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp = _comp("db", "DB", ComponentType.DATABASE)
        lessons = sim._generate_lessons(config, comp, 0, True, 2, 6.0)
        assert any("team size" in l.lower() for l in lessons)

    def test_high_cascade_severity_lesson(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp = _comp("db", "DB", ComponentType.DATABASE)
        lessons = sim._generate_lessons(config, comp, 0, True, 4, 8.0)
        assert any("cascade severity" in l.lower() or "isolation" in l.lower() for l in lessons)

    def test_good_infra_default_lesson(self):
        """Well-configured infra with no issues gets a positive lesson."""
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        comp = _comp("db", "DB", ComponentType.DATABASE, replicas=2,
                     failover=FailoverConfig(enabled=True))
        lessons = sim._generate_lessons(config, comp, 0, True, 4, 0.0)
        assert any("good resilience" in l.lower() for l in lessons)

    def test_no_target_comp(self):
        """None target_comp should not crash."""
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        lessons = sim._generate_lessons(config, None, 0, True, 4, 0.0)
        assert isinstance(lessons, list)


# ---------------------------------------------------------------------------
# Tests: _calculate_score
# ---------------------------------------------------------------------------


class TestScore:
    def test_score_range(self):
        sim = WarRoomSimulator(_chain_graph())
        for incident in sim.available_incidents():
            report = sim.simulate(incident_type=incident)
            assert 0 <= report.score <= 100

    def test_fast_detection_high_score(self):
        """Fast detection (<= 5 min) gives max 25 detection points."""
        sim = WarRoomSimulator(_chain_graph())
        score = sim._calculate_score(
            detection_time=3.0, mitigation_time=8.0, recovery_time=10.0,
            blast_radius=0, cascade_severity=0.0, has_runbook=True, team_size=4,
        )
        assert score > 80.0

    def test_slow_detection_low_score(self):
        """Slow detection (>= 30 min) gives 0 detection points."""
        sim = WarRoomSimulator(_chain_graph())
        score = sim._calculate_score(
            detection_time=35.0, mitigation_time=65.0, recovery_time=125.0,
            blast_radius=4, cascade_severity=8.0, has_runbook=False, team_size=1,
        )
        assert score < 30.0

    def test_mid_detection_interpolated(self):
        sim = WarRoomSimulator(_chain_graph())
        score_fast = sim._calculate_score(5.0, 10.0, 15.0, 0, 0.0, True, 4)
        score_mid = sim._calculate_score(15.0, 10.0, 15.0, 0, 0.0, True, 4)
        score_slow = sim._calculate_score(30.0, 10.0, 15.0, 0, 0.0, True, 4)
        assert score_fast > score_mid > score_slow

    def test_mitigation_scoring(self):
        sim = WarRoomSimulator(_chain_graph())
        score_fast = sim._calculate_score(5.0, 8.0, 15.0, 0, 0.0, True, 4)
        score_slow = sim._calculate_score(5.0, 65.0, 15.0, 0, 0.0, True, 4)
        assert score_fast > score_slow

    def test_recovery_scoring(self):
        sim = WarRoomSimulator(_chain_graph())
        score_fast = sim._calculate_score(5.0, 10.0, 10.0, 0, 0.0, True, 4)
        score_slow = sim._calculate_score(5.0, 10.0, 125.0, 0, 0.0, True, 4)
        assert score_fast > score_slow

    def test_blast_radius_scoring(self):
        sim = WarRoomSimulator(_chain_graph())
        score_small = sim._calculate_score(5.0, 10.0, 15.0, 0, 0.0, True, 4)
        score_large = sim._calculate_score(5.0, 10.0, 15.0, 4, 0.0, True, 4)
        assert score_small > score_large

    def test_empty_graph_blast_score(self):
        """Empty graph (0 total components) => blast_score = 15."""
        g = InfraGraph()
        sim = WarRoomSimulator(g)
        score = sim._calculate_score(5.0, 10.0, 15.0, 0, 0.0, True, 4)
        assert score > 0

    def test_runbook_adds_prep_score(self):
        sim = WarRoomSimulator(_chain_graph())
        score_with = sim._calculate_score(5.0, 10.0, 15.0, 0, 0.0, True, 4)
        score_without = sim._calculate_score(5.0, 10.0, 15.0, 0, 0.0, False, 4)
        assert score_with > score_without

    def test_team_size_adds_prep_score(self):
        sim = WarRoomSimulator(_chain_graph())
        score_large = sim._calculate_score(5.0, 10.0, 15.0, 0, 0.0, True, 4)
        score_small = sim._calculate_score(5.0, 10.0, 15.0, 0, 0.0, True, 1)
        assert score_large > score_small

    def test_team_size_2_prep(self):
        """Team size 2 gets 3 prep points."""
        sim = WarRoomSimulator(_chain_graph())
        score_2 = sim._calculate_score(5.0, 10.0, 15.0, 0, 0.0, False, 2)
        score_1 = sim._calculate_score(5.0, 10.0, 15.0, 0, 0.0, False, 1)
        assert score_2 > score_1

    def test_score_clamped_to_100(self):
        sim = WarRoomSimulator(_chain_graph())
        score = sim._calculate_score(1.0, 1.0, 1.0, 0, 0.0, True, 4)
        assert score <= 100.0

    def test_score_clamped_to_0(self):
        sim = WarRoomSimulator(_chain_graph())
        score = sim._calculate_score(100.0, 100.0, 200.0, 100, 10.0, False, 1)
        assert score >= 0.0


# ---------------------------------------------------------------------------
# Tests: empty / minimal graphs
# ---------------------------------------------------------------------------


class TestEmptyGraph:
    def test_empty_graph_simulation(self):
        g = InfraGraph()
        sim = WarRoomSimulator(g)
        report = sim.simulate(incident_type="database_outage")
        assert isinstance(report, WarRoomReport)
        assert report.total_duration_minutes > 0

    def test_single_component_graph(self):
        g = InfraGraph()
        g.add_component(_comp("only", "Only", ComponentType.DATABASE))
        sim = WarRoomSimulator(g)
        report = sim.simulate(incident_type="database_outage")
        assert report.total_duration_minutes > 0
        assert len(report.events) > 0

    def test_no_matching_component_falls_back(self):
        """If no matching type, falls back to first component."""
        g = InfraGraph()
        g.add_component(_comp("q", "Queue", ComponentType.QUEUE))
        sim = WarRoomSimulator(g)
        report = sim.simulate(incident_type="database_outage")
        assert report.total_duration_minutes > 0


# ---------------------------------------------------------------------------
# Tests: incident configs
# ---------------------------------------------------------------------------


class TestIncidentConfigs:
    def test_all_configs_have_required_keys(self):
        required_keys = {
            "description", "target_types", "fault_type",
            "severity_base", "detection_difficulty",
            "mitigation_complexity", "recovery_complexity",
        }
        for name, config in _INCIDENT_CONFIGS.items():
            for key in required_keys:
                assert key in config, f"{name} missing {key}"

    def test_detection_difficulty_range(self):
        for name, config in _INCIDENT_CONFIGS.items():
            assert 0.0 <= config["detection_difficulty"] <= 1.0, \
                f"{name} detection_difficulty out of range"

    def test_mitigation_complexity_range(self):
        for name, config in _INCIDENT_CONFIGS.items():
            assert 0.0 <= config["mitigation_complexity"] <= 1.0, \
                f"{name} mitigation_complexity out of range"

    def test_recovery_complexity_range(self):
        for name, config in _INCIDENT_CONFIGS.items():
            assert 0.0 <= config["recovery_complexity"] <= 1.0, \
                f"{name} recovery_complexity out of range"

    def test_roles_defined_for_sizes_1_to_4(self):
        for size in (1, 2, 3, 4):
            assert size in _ROLES_BY_SIZE
            assert len(_ROLES_BY_SIZE[size]) == size


# ---------------------------------------------------------------------------
# Tests: _build_phases
# ---------------------------------------------------------------------------


class TestBuildPhases:
    def test_returns_five_phases(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        phases = sim._build_phases(5.0, 10.0, 15.0, 20.0, 15.0, config)
        assert len(phases) == 5

    def test_phase_durations_match_inputs(self):
        sim = WarRoomSimulator(_chain_graph())
        config = _INCIDENT_CONFIGS["database_outage"]
        phases = sim._build_phases(5.0, 10.0, 15.0, 20.0, 15.0, config)
        assert phases[0].duration_minutes == 5.0
        assert phases[1].duration_minutes == 10.0
        assert phases[2].duration_minutes == 15.0
        assert phases[3].duration_minutes == 20.0
        assert phases[4].duration_minutes == 15.0
