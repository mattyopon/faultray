"""Tests for the War Room Simulator."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.war_room import (
    WarRoomEvent,
    WarRoomPhase,
    WarRoomReport,
    WarRoomRole,
    WarRoomSimulator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def basic_graph() -> InfraGraph:
    """A basic graph with common component types."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_component(Component(
        id="cache", name="Redis", type=ComponentType.CACHE,
        replicas=1,
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))
    return graph


@pytest.fixture
def resilient_graph() -> InfraGraph:
    """A graph with full redundancy and failover."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=3, failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3, failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=2, failover=FailoverConfig(enabled=True),
        operational_profile=OperationalProfile(mttr_minutes=5.0),
    ))
    graph.add_component(Component(
        id="cache", name="Redis", type=ComponentType.CACHE,
        replicas=2, failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWarRoomAvailableIncidents:
    """Test incident type listing."""

    def test_available_incidents_non_empty(self, basic_graph: InfraGraph):
        """Should list at least the 8 standard incident types."""
        sim = WarRoomSimulator(basic_graph)
        incidents = sim.available_incidents()
        assert len(incidents) >= 8

    def test_known_incident_types(self, basic_graph: InfraGraph):
        """Should include all documented incident types."""
        sim = WarRoomSimulator(basic_graph)
        incidents = sim.available_incidents()
        expected = [
            "database_outage", "network_partition", "ddos_attack",
            "cascading_failure", "security_breach", "data_corruption",
            "cloud_region_failure", "deployment_rollback",
        ]
        for inc in expected:
            assert inc in incidents


class TestWarRoomSimulation:
    """Test core simulation logic."""

    def test_simulate_database_outage(self, basic_graph: InfraGraph):
        """Should produce a complete report for database outage."""
        sim = WarRoomSimulator(basic_graph)
        report = sim.simulate(incident_type="database_outage", team_size=4)

        assert isinstance(report, WarRoomReport)
        assert report.exercise_name != ""
        assert report.scenario_description != ""
        assert report.total_duration_minutes > 0
        assert report.time_to_detect_minutes > 0
        assert report.time_to_mitigate_minutes > 0
        assert report.time_to_recover_minutes > 0
        assert 0 <= report.score <= 100

    def test_simulate_all_incident_types(self, basic_graph: InfraGraph):
        """Should handle all incident types without error."""
        sim = WarRoomSimulator(basic_graph)
        for incident in sim.available_incidents():
            report = sim.simulate(incident_type=incident, team_size=2)
            assert isinstance(report, WarRoomReport)
            assert report.total_duration_minutes > 0

    def test_invalid_incident_type(self, basic_graph: InfraGraph):
        """Should raise ValueError for unknown incident type."""
        sim = WarRoomSimulator(basic_graph)
        with pytest.raises(ValueError, match="Unknown incident type"):
            sim.simulate(incident_type="nonexistent")

    def test_phases_present(self, basic_graph: InfraGraph):
        """Report should have all 5 phases."""
        sim = WarRoomSimulator(basic_graph)
        report = sim.simulate(incident_type="database_outage")
        assert len(report.phases) == 5
        phase_names = [p.name for p in report.phases]
        assert "Detection" in phase_names
        assert "Triage" in phase_names
        assert "Mitigation" in phase_names
        assert "Recovery" in phase_names
        assert "Post-mortem" in phase_names

    def test_events_generated(self, basic_graph: InfraGraph):
        """Report should have events in the timeline."""
        sim = WarRoomSimulator(basic_graph)
        report = sim.simulate(incident_type="database_outage")
        assert len(report.events) > 0
        # Events should be in chronological order (time_minutes non-decreasing)
        times = [e.time_minutes for e in report.events]
        assert times == sorted(times)

    def test_roles_involved(self, basic_graph: InfraGraph):
        """Report should list the roles involved."""
        sim = WarRoomSimulator(basic_graph)
        report = sim.simulate(incident_type="database_outage", team_size=4)
        assert len(report.roles_involved) > 0
        assert "Incident Commander" in report.roles_involved

    def test_lessons_learned_generated(self, basic_graph: InfraGraph):
        """Report should include lessons learned."""
        sim = WarRoomSimulator(basic_graph)
        report = sim.simulate(incident_type="database_outage")
        assert len(report.lessons_learned) > 0


class TestWarRoomTeamSize:
    """Test team size effects."""

    def test_team_size_1(self, basic_graph: InfraGraph):
        """Single person team should still work."""
        sim = WarRoomSimulator(basic_graph)
        report = sim.simulate(incident_type="database_outage", team_size=1)
        assert report.total_duration_minutes > 0
        assert len(report.roles_involved) >= 1

    def test_larger_team_faster(self, basic_graph: InfraGraph):
        """Larger team should generally detect and respond faster."""
        sim = WarRoomSimulator(basic_graph)
        report_small = sim.simulate(incident_type="database_outage", team_size=1)
        report_large = sim.simulate(incident_type="database_outage", team_size=4)
        # Larger team should have faster or equal detection
        assert report_large.time_to_detect_minutes <= report_small.time_to_detect_minutes


class TestWarRoomRunbook:
    """Test runbook effects."""

    def test_runbook_reduces_time(self, basic_graph: InfraGraph):
        """Having a runbook should reduce response time."""
        sim = WarRoomSimulator(basic_graph)
        report_with = sim.simulate(incident_type="database_outage", has_runbook=True)
        report_without = sim.simulate(incident_type="database_outage", has_runbook=False)
        # With runbook should be faster or equal
        assert report_with.time_to_mitigate_minutes <= report_without.time_to_mitigate_minutes

    def test_no_runbook_lesson(self, basic_graph: InfraGraph):
        """Without runbook, lessons should suggest creating one."""
        sim = WarRoomSimulator(basic_graph)
        report = sim.simulate(incident_type="database_outage", has_runbook=False)
        runbook_lessons = [l for l in report.lessons_learned if "runbook" in l.lower()]
        assert len(runbook_lessons) > 0


class TestWarRoomInfrastructure:
    """Test infrastructure effects on simulation."""

    def test_failover_improves_score(self, basic_graph: InfraGraph,
                                      resilient_graph: InfraGraph):
        """Resilient infrastructure should score higher."""
        sim_basic = WarRoomSimulator(basic_graph)
        sim_resilient = WarRoomSimulator(resilient_graph)
        report_basic = sim_basic.simulate(incident_type="database_outage")
        report_resilient = sim_resilient.simulate(incident_type="database_outage")
        assert report_resilient.score >= report_basic.score

    def test_failover_reduces_mitigation_time(self, basic_graph: InfraGraph,
                                                resilient_graph: InfraGraph):
        """Failover-enabled infrastructure should mitigate faster."""
        sim_basic = WarRoomSimulator(basic_graph)
        sim_resilient = WarRoomSimulator(resilient_graph)
        report_basic = sim_basic.simulate(incident_type="database_outage")
        report_resilient = sim_resilient.simulate(incident_type="database_outage")
        assert (
            report_resilient.time_to_mitigate_minutes
            <= report_basic.time_to_mitigate_minutes
        )


class TestWarRoomScore:
    """Test score calculation."""

    def test_score_range(self, basic_graph: InfraGraph):
        """Score should be between 0 and 100."""
        sim = WarRoomSimulator(basic_graph)
        for incident in sim.available_incidents():
            report = sim.simulate(incident_type=incident)
            assert 0 <= report.score <= 100

    def test_phase_durations_sum_to_total(self, basic_graph: InfraGraph):
        """Phase durations should sum to total duration."""
        sim = WarRoomSimulator(basic_graph)
        report = sim.simulate(incident_type="database_outage")
        phase_sum = sum(p.duration_minutes for p in report.phases)
        assert abs(phase_sum - report.total_duration_minutes) < 0.1


class TestWarRoomEmptyGraph:
    """Test with empty or minimal graphs."""

    def test_empty_graph(self):
        """Should handle empty graph gracefully."""
        graph = InfraGraph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="database_outage")
        assert isinstance(report, WarRoomReport)
        assert report.total_duration_minutes > 0
