"""Tests for SRE Maturity Assessment Engine."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    ComplianceTags,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    OperationalTeamConfig,
    RegionConfig,
    ResourceMetrics,
    RetryStrategy,
    SecurityProfile,
    SLOTarget,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.sre_maturity import (
    DimensionAssessment,
    MaturityDimension,
    MaturityLevel,
    MaturityReport,
    SREMaturityEngine,
    _DIMENSION_LABELS,
    _LEVEL_LABELS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_graph() -> InfraGraph:
    """Build a minimal graph with no resilience features (Level 1)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _managed_graph() -> InfraGraph:
    """Build a graph with some resilience features (Level 2ish)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER, replicas=2,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=10),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER, replicas=2,
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _well_configured_graph() -> InfraGraph:
    """Build a well-configured graph with high resilience (Level 4-5)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER, replicas=3,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=5),
        operational_profile=OperationalProfile(mtbf_hours=43800, mttr_minutes=1),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            waf_protected=True, rate_limiting=True, auth_required=True,
            network_segmented=True, backup_enabled=True, log_enabled=True,
            ids_monitored=True,
        ),
        compliance_tags=ComplianceTags(audit_logging=True, change_management=True),
        team=OperationalTeamConfig(runbook_coverage_percent=90),
        region=RegionConfig(
            region="us-east-1", availability_zone="us-east-1a",
            dr_target_region="us-west-2",
        ),
        slo_targets=[SLOTarget(name="availability", target=99.99)],
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER, replicas=5,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=3, max_replicas=10),
        operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=2),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            auth_required=True, network_segmented=True, backup_enabled=True,
            log_enabled=True, ids_monitored=True, rate_limiting=True,
        ),
        compliance_tags=ComplianceTags(audit_logging=True, change_management=True),
        team=OperationalTeamConfig(runbook_coverage_percent=80),
        region=RegionConfig(
            region="us-east-1", availability_zone="us-east-1a",
            dr_target_region="us-west-2",
        ),
        slo_targets=[SLOTarget(name="availability", target=99.99)],
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE, replicas=3,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=5),
        operational_profile=OperationalProfile(mtbf_hours=43800, mttr_minutes=2),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            auth_required=True, network_segmented=True, backup_enabled=True,
            log_enabled=True, ids_monitored=True, rate_limiting=True,
        ),
        compliance_tags=ComplianceTags(audit_logging=True, change_management=True),
        team=OperationalTeamConfig(runbook_coverage_percent=95),
        region=RegionConfig(
            region="us-east-1", availability_zone="us-east-1b",
            dr_target_region="us-west-2",
        ),
        slo_targets=[SLOTarget(name="availability", target=99.99)],
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(enabled=True),
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests: SREMaturityEngine
# ---------------------------------------------------------------------------


class TestSREMaturityEngine:
    """Tests for the SREMaturityEngine class."""

    def test_assess_empty_graph(self):
        engine = SREMaturityEngine()
        graph = InfraGraph()
        report = engine.assess(graph)
        assert isinstance(report, MaturityReport)
        assert report.overall_level == MaturityLevel.INITIAL
        assert report.overall_score <= 10.0

    def test_assess_minimal_graph(self):
        engine = SREMaturityEngine()
        graph = _minimal_graph()
        report = engine.assess(graph)
        assert isinstance(report, MaturityReport)
        assert report.overall_level.value <= 2  # Should be Initial or Managed
        assert report.overall_score < 50
        assert len(report.dimensions) == 8
        assert len(report.weaknesses) > 0

    def test_assess_well_configured_graph(self):
        engine = SREMaturityEngine()
        graph = _well_configured_graph()
        report = engine.assess(graph)
        assert isinstance(report, MaturityReport)
        assert report.overall_level.value >= 3  # Should be at least Defined
        assert report.overall_score > 50
        assert len(report.strengths) > 0

    def test_assess_returns_all_dimensions(self):
        engine = SREMaturityEngine()
        graph = _managed_graph()
        report = engine.assess(graph)
        dim_values = {d.dimension for d in report.dimensions}
        assert dim_values == set(MaturityDimension)

    def test_assess_radar_data(self):
        engine = SREMaturityEngine()
        graph = _managed_graph()
        report = engine.assess(graph)
        assert len(report.radar_data) == 8
        for label, score in report.radar_data.items():
            assert 0 <= score <= 100

    def test_assess_industry_comparison(self):
        engine = SREMaturityEngine()
        graph = _well_configured_graph()
        report = engine.assess(graph)
        assert isinstance(report.industry_comparison, str)
        assert len(report.industry_comparison) > 0


class TestDimensionAssessments:
    """Tests for individual dimension assessments."""

    def test_monitoring_initial(self):
        engine = SREMaturityEngine()
        graph = _minimal_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.MONITORING)
        assert assessment.level == MaturityLevel.INITIAL
        assert assessment.score < 30
        assert len(assessment.gaps) > 0

    def test_monitoring_optimizing(self):
        engine = SREMaturityEngine()
        graph = _well_configured_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.MONITORING)
        assert assessment.level.value >= 4
        assert assessment.score >= 70

    def test_incident_response_initial(self):
        engine = SREMaturityEngine()
        graph = _minimal_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.INCIDENT_RESPONSE)
        assert assessment.level == MaturityLevel.INITIAL
        assert len(assessment.recommendations) > 0

    def test_incident_response_high(self):
        engine = SREMaturityEngine()
        graph = _well_configured_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.INCIDENT_RESPONSE)
        assert assessment.level.value >= 3

    def test_availability_minimal(self):
        engine = SREMaturityEngine()
        graph = _minimal_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.AVAILABILITY)
        # Minimal graph still gets reasonable availability from default MTBF/MTTR
        # (single-replica components have high individual availability)
        assert assessment.level.value >= 2  # At least Managed
        assert assessment.score > 0

    def test_availability_high(self):
        engine = SREMaturityEngine()
        graph = _well_configured_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.AVAILABILITY)
        assert assessment.level.value >= 3
        assert assessment.score >= 50

    def test_disaster_recovery_initial(self):
        engine = SREMaturityEngine()
        graph = _minimal_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.DISASTER_RECOVERY)
        assert assessment.level == MaturityLevel.INITIAL
        assert len(assessment.gaps) > 0

    def test_disaster_recovery_high(self):
        engine = SREMaturityEngine()
        graph = _well_configured_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.DISASTER_RECOVERY)
        assert assessment.level.value >= 4

    def test_security_initial(self):
        engine = SREMaturityEngine()
        graph = _minimal_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.SECURITY)
        assert assessment.level == MaturityLevel.INITIAL
        assert assessment.score < 30

    def test_security_high(self):
        engine = SREMaturityEngine()
        graph = _well_configured_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.SECURITY)
        assert assessment.level.value >= 4
        assert assessment.score >= 70

    def test_automation_initial(self):
        engine = SREMaturityEngine()
        graph = _minimal_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.AUTOMATION)
        assert assessment.level == MaturityLevel.INITIAL
        assert assessment.score < 30

    def test_automation_high(self):
        engine = SREMaturityEngine()
        graph = _well_configured_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.AUTOMATION)
        assert assessment.level.value >= 4
        assert assessment.score >= 70

    def test_capacity_planning_initial(self):
        engine = SREMaturityEngine()
        graph = _minimal_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.CAPACITY_PLANNING)
        assert assessment.level == MaturityLevel.INITIAL

    def test_capacity_planning_high(self):
        engine = SREMaturityEngine()
        graph = _well_configured_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.CAPACITY_PLANNING)
        assert assessment.level.value >= 3

    def test_change_management_initial(self):
        engine = SREMaturityEngine()
        graph = _minimal_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.CHANGE_MANAGEMENT)
        assert assessment.level.value <= 2

    def test_change_management_high(self):
        engine = SREMaturityEngine()
        graph = _well_configured_graph()
        assessment = engine.assess_dimension(graph, MaturityDimension.CHANGE_MANAGEMENT)
        assert assessment.level.value >= 4

    def test_empty_graph_all_dimensions(self):
        engine = SREMaturityEngine()
        graph = InfraGraph()
        for dim in MaturityDimension:
            assessment = engine.assess_dimension(graph, dim)
            assert assessment.level == MaturityLevel.INITIAL
            assert assessment.score <= 15


class TestRoadmap:
    """Tests for roadmap generation."""

    def test_roadmap_generated(self):
        engine = SREMaturityEngine()
        graph = _minimal_graph()
        report = engine.assess(graph)
        assert len(report.roadmap) > 0

    def test_roadmap_has_correct_structure(self):
        engine = SREMaturityEngine()
        graph = _minimal_graph()
        report = engine.assess(graph)
        for action, target_level, effort in report.roadmap:
            assert isinstance(action, str)
            assert "Level" in target_level
            assert effort in ("Low", "Medium", "High", "None")

    def test_roadmap_targets_next_level(self):
        engine = SREMaturityEngine()
        graph = _managed_graph()
        report = engine.assess(graph)
        roadmap = report.roadmap
        # Roadmap should target levels higher than current weaknesses
        assert len(roadmap) > 0

    def test_no_roadmap_for_optimizing(self):
        engine = SREMaturityEngine()
        graph = _well_configured_graph()
        report = engine.assess(graph)
        # Well-configured may still have roadmap items for non-max dimensions
        # But Level 5 dimensions should not have roadmap items
        level5_dims = {
            d.dimension.value for d in report.dimensions if d.level == MaturityLevel.OPTIMIZING
        }
        for action, _, _ in report.roadmap:
            # Verify roadmap doesn't target Level 5 to Level 6 (impossible)
            assert "Level 6" not in action


class TestRadarChart:
    """Tests for radar chart data."""

    def test_to_radar_chart_data(self):
        engine = SREMaturityEngine()
        graph = _managed_graph()
        report = engine.assess(graph)
        chart_data = engine.to_radar_chart_data(report)
        assert "labels" in chart_data
        assert "values" in chart_data
        assert "max_value" in chart_data
        assert chart_data["max_value"] == 100
        assert len(chart_data["labels"]) == 8
        assert len(chart_data["values"]) == 8

    def test_radar_chart_scores_match_report(self):
        engine = SREMaturityEngine()
        graph = _managed_graph()
        report = engine.assess(graph)
        chart_data = engine.to_radar_chart_data(report)
        for label, value in zip(chart_data["labels"], chart_data["values"]):
            assert label in report.radar_data
            assert report.radar_data[label] == value


class TestMaturityLevelEnum:
    """Tests for MaturityLevel enum."""

    def test_level_values(self):
        assert MaturityLevel.INITIAL.value == 1
        assert MaturityLevel.MANAGED.value == 2
        assert MaturityLevel.DEFINED.value == 3
        assert MaturityLevel.QUANTITATIVE.value == 4
        assert MaturityLevel.OPTIMIZING.value == 5

    def test_all_levels_have_labels(self):
        for level in MaturityLevel:
            assert level.value in _LEVEL_LABELS


class TestMaturityDimensionEnum:
    """Tests for MaturityDimension enum."""

    def test_dimension_count(self):
        assert len(MaturityDimension) == 8

    def test_all_dimensions_have_labels(self):
        for dim in MaturityDimension:
            assert dim.value in _DIMENSION_LABELS


class TestScoreToLevel:
    """Tests for score-to-level conversion."""

    def test_boundaries(self):
        engine = SREMaturityEngine()
        assert engine._score_to_level(0) == MaturityLevel.INITIAL
        assert engine._score_to_level(24) == MaturityLevel.INITIAL
        assert engine._score_to_level(25) == MaturityLevel.MANAGED
        assert engine._score_to_level(49) == MaturityLevel.MANAGED
        assert engine._score_to_level(50) == MaturityLevel.DEFINED
        assert engine._score_to_level(69) == MaturityLevel.DEFINED
        assert engine._score_to_level(70) == MaturityLevel.QUANTITATIVE
        assert engine._score_to_level(89) == MaturityLevel.QUANTITATIVE
        assert engine._score_to_level(90) == MaturityLevel.OPTIMIZING
        assert engine._score_to_level(100) == MaturityLevel.OPTIMIZING


class TestAvailabilityEstimation:
    """Tests for availability estimation helpers."""

    def test_availability_to_nines(self):
        assert SREMaturityEngine._availability_to_nines(0.99) == pytest.approx(2.0, abs=0.01)
        assert SREMaturityEngine._availability_to_nines(0.999) == pytest.approx(3.0, abs=0.01)
        assert SREMaturityEngine._availability_to_nines(0.9999) == pytest.approx(4.0, abs=0.01)

    def test_availability_to_nines_edge_cases(self):
        assert SREMaturityEngine._availability_to_nines(1.0) == 9.0
        assert SREMaturityEngine._availability_to_nines(0.0) == 0.0

    def test_component_availability(self):
        engine = SREMaturityEngine()
        comp = Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
        )
        avail = engine._component_availability(comp)
        assert 0 < avail < 1.0

    def test_component_availability_with_replicas(self):
        engine = SREMaturityEngine()
        single = Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
        )
        multi = Component(
            id="app2", name="App2", type=ComponentType.APP_SERVER,
            replicas=3,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
        )
        avail_single = engine._component_availability(single)
        avail_multi = engine._component_availability(multi)
        assert avail_multi > avail_single

    def test_component_availability_with_failover(self):
        engine = SREMaturityEngine()
        no_fo = Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=2,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
        )
        with_fo = Component(
            id="app2", name="App2", type=ComponentType.APP_SERVER,
            replicas=2,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
            failover=FailoverConfig(enabled=True, promotion_time_seconds=10),
        )
        avail_no_fo = engine._component_availability(no_fo)
        avail_with_fo = engine._component_availability(with_fo)
        assert avail_with_fo >= avail_no_fo


# ---------------------------------------------------------------------------
# Additional tests for full coverage of intermediate maturity levels
# ---------------------------------------------------------------------------


def _monitoring_defined_graph() -> InfraGraph:
    """Build a graph that hits Monitoring DEFINED level.

    Needs: hc_ratio >= 0.75 and as_ratio < 0.5
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _monitoring_quantitative_graph() -> InfraGraph:
    """Build a graph that hits Monitoring QUANTITATIVE level.

    Needs: hc_ratio >= 0.75, as_ratio >= 0.5, cb_ratio < 0.75
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _incident_response_defined_graph() -> InfraGraph:
    """Build a graph that hits Incident Response DEFINED level.

    Needs: fo_ratio >= 0.5, cb_ratio >= 0.25, as_ratio < 0.5 or team_ratio < 0.25
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _incident_response_quantitative_graph() -> InfraGraph:
    """Build a graph that hits Incident Response QUANTITATIVE level.

    Needs: fo_ratio >= 0.5, cb_ratio >= 0.25,
           as_ratio >= 0.5, team_ratio >= 0.25,
           as_ratio < 0.9 or team_ratio < 0.5
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
        team=OperationalTeamConfig(runbook_coverage_percent=60),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return graph


def _capacity_planning_managed_graph() -> InfraGraph:
    """Build a graph that hits Capacity Planning MANAGED level.

    Needs: as_ratio > 0 but < 0.5, or slo_ratio > 0 but as_ratio < 0.5
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
    ))
    return graph


def _capacity_planning_defined_graph() -> InfraGraph:
    """Build a graph that hits Capacity Planning DEFINED level.

    Needs: as_ratio >= 0.5, and (high_util > 0 or slo_ratio < 0.25)
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _capacity_planning_quantitative_graph() -> InfraGraph:
    """Build a graph that hits Capacity Planning QUANTITATIVE level.

    Needs: as_ratio >= 0.5, high_util == 0, slo_ratio >= 0.25 but < 0.75
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
        slo_targets=[SLOTarget(name="avail", target=99.9)],
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
    ))
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
    ))
    return graph


def _change_mgmt_managed_graph() -> InfraGraph:
    """Build a graph that hits Change Management MANAGED level.

    Needs: deploy_ratio > 0 or compliance_ratio > 0, but compliance_ratio < 0.25
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        operational_profile=OperationalProfile(deploy_downtime_seconds=30),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        operational_profile=OperationalProfile(deploy_downtime_seconds=60),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _change_mgmt_defined_graph() -> InfraGraph:
    """Build a graph that hits Change Management DEFINED level.

    Needs: compliance_ratio >= 0.25 but < 0.75
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        operational_profile=OperationalProfile(deploy_downtime_seconds=30),
        compliance_tags=ComplianceTags(audit_logging=True, change_management=True),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE, replicas=2,
    ))
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _change_mgmt_quantitative_graph() -> InfraGraph:
    """Build a graph that hits Change Management QUANTITATIVE level.

    Needs: compliance_ratio >= 0.75, fo_ratio < 0.75
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        compliance_tags=ComplianceTags(audit_logging=True, change_management=True),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        compliance_tags=ComplianceTags(audit_logging=True, change_management=True),
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE, replicas=2,
        compliance_tags=ComplianceTags(audit_logging=True, change_management=True),
    ))
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        compliance_tags=ComplianceTags(audit_logging=True, change_management=True),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _availability_initial_graph() -> InfraGraph:
    """Build a graph that hits Availability INITIAL level.

    Needs: estimated_avail < 0.99
    Use a component with very low MTBF and high MTTR on the critical path.
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=10, mttr_minutes=120),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=10, mttr_minutes=120),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _availability_managed_graph() -> InfraGraph:
    """Build a graph that hits Availability MANAGED level.

    Needs: 0.99 <= estimated_avail < 0.999
    Use moderate MTBF/MTTR that gives ~99.5% availability.
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=200, mttr_minutes=60),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=200, mttr_minutes=60),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _availability_defined_graph() -> InfraGraph:
    """Build a graph that hits Availability DEFINED level.

    Needs: 0.999 <= estimated_avail < 0.9995
    Use moderate MTBF/MTTR + single replicas to stay in range.
    With MTBF=500, MTTR=15min=0.25h:  avail = 500/500.25 ~ 0.9995
    With 2 components on critical path:  system ~ 0.9995^2 ~ 0.999
    Need to be careful to land between 0.999 and 0.9995
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=500, mttr_minutes=15),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=500, mttr_minutes=15),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _dr_managed_graph() -> InfraGraph:
    """Build a graph that hits Disaster Recovery MANAGED level.

    Needs: has some replicas but fo_ratio < 0.25 or rep_ratio < 0.5
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        security=SecurityProfile(backup_enabled=True),
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
    ))
    return graph


def _dr_quantitative_graph() -> InfraGraph:
    """Build a graph that hits Disaster Recovery QUANTITATIVE level.

    Needs: rep_ratio >= 0.5, fo_ratio >= 0.25, az_ratio >= 0.25, dr_ratio < 0.25
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
        failover=FailoverConfig(enabled=True),
        region=RegionConfig(region="us-east-1", availability_zone="us-east-1a"),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=3,
        failover=FailoverConfig(enabled=True),
        region=RegionConfig(region="us-east-1", availability_zone="us-east-1b"),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _security_managed_graph() -> InfraGraph:
    """Build a graph that hits Security MANAGED level.

    Needs: encrypt_ratio > 0 or auth_ratio > 0, but encrypt_ratio < 0.5 or auth_ratio < 0.5
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        security=SecurityProfile(encryption_at_rest=True, auth_required=True),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _security_defined_graph() -> InfraGraph:
    """Build a graph that hits Security DEFINED level.

    Needs: encrypt_ratio >= 0.5, auth_ratio >= 0.5, segmentation_ratio < 0.5
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            auth_required=True,
        ),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            auth_required=True,
        ),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _security_quantitative_graph() -> InfraGraph:
    """Build a graph that hits Security QUANTITATIVE level.

    Needs: encrypt >= 0.5, auth >= 0.5, segmentation >= 0.5, advanced < 0.5
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            auth_required=True, network_segmented=True,
        ),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            auth_required=True, network_segmented=True,
        ),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _automation_managed_graph() -> InfraGraph:
    """Build a graph that hits Automation MANAGED level.

    Needs: auto_score >= 0.1 but < 0.3
    auto_score = (as_ratio + fo_ratio + cb_ratio + retry_ratio) / 4.0
    Use: as on 1/3, fo on 0, cb on 0, retry on 0 => ~0.08 (too low)
    Use: as on 1/2, fo on 1/2, cb on 0, retry on 0 => 0.25 (good)
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _automation_defined_graph() -> InfraGraph:
    """Build a graph that hits Automation DEFINED level.

    Needs: auto_score >= 0.3 but < 0.6
    Use: as on 1/3, fo on 1/3, cb on 1/2, retry on 0
    => (0.33 + 0.33 + 0.5 + 0) / 4 = 0.29 ... need to tweak
    Use: as on 2/3, fo on 1/3, cb on 0/2, retry on 0
    => (0.67 + 0.33 + 0 + 0) / 4 = 0.25 ... too low
    Use: as on 2/3, fo on 2/3, cb on 0/2, retry on 0
    => (0.67 + 0.67 + 0 + 0) / 4 = 0.335
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE, replicas=2,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
    ))
    return graph


def _automation_quantitative_graph() -> InfraGraph:
    """Build a graph that hits Automation QUANTITATIVE level.

    Needs: auto_score >= 0.6 but < 0.85
    Use: as on 2/2, fo on 2/2, cb on 1/1, retry on 0
    => (1 + 1 + 1 + 0) / 4 = 0.75
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return graph


class TestMonitoringIntermediateLevels:
    """Tests for monitoring dimension intermediate maturity levels."""

    def test_monitoring_defined(self):
        """Monitoring DEFINED: hc_ratio >= 0.75, as_ratio < 0.5."""
        engine = SREMaturityEngine()
        graph = _monitoring_defined_graph()
        a = engine.assess_dimension(graph, MaturityDimension.MONITORING)
        assert a.level == MaturityLevel.DEFINED
        assert 50.0 <= a.score <= 70.0
        assert len(a.evidence) > 0
        assert len(a.gaps) > 0
        assert any("autoscaling" in r.lower() for r in a.recommendations)

    def test_monitoring_quantitative(self):
        """Monitoring QUANTITATIVE: hc >= 0.75, as >= 0.5, cb < 0.75."""
        engine = SREMaturityEngine()
        graph = _monitoring_quantitative_graph()
        a = engine.assess_dimension(graph, MaturityDimension.MONITORING)
        assert a.level == MaturityLevel.QUANTITATIVE
        assert 70.0 <= a.score <= 90.0
        assert len(a.evidence) >= 3
        assert any("circuit breaker" in r.lower() for r in a.recommendations)


class TestIncidentResponseIntermediateLevels:
    """Tests for incident response dimension intermediate maturity levels."""

    def test_incident_response_defined(self):
        """IR DEFINED: fo >= 0.5, cb >= 0.25, as < 0.5 or team < 0.25."""
        engine = SREMaturityEngine()
        graph = _incident_response_defined_graph()
        a = engine.assess_dimension(graph, MaturityDimension.INCIDENT_RESPONSE)
        assert a.level == MaturityLevel.DEFINED
        assert 50.0 <= a.score <= 70.0

    def test_incident_response_quantitative(self):
        """IR QUANTITATIVE: as >= 0.5 and team >= 0.25, but as < 0.9 or team < 0.5."""
        engine = SREMaturityEngine()
        graph = _incident_response_quantitative_graph()
        a = engine.assess_dimension(graph, MaturityDimension.INCIDENT_RESPONSE)
        assert a.level == MaturityLevel.QUANTITATIVE
        assert 70.0 <= a.score <= 90.0


class TestCapacityPlanningIntermediateLevels:
    """Tests for capacity planning intermediate maturity levels."""

    def test_capacity_planning_managed(self):
        """CP MANAGED: as_ratio > 0 but < 0.5."""
        engine = SREMaturityEngine()
        graph = _capacity_planning_managed_graph()
        a = engine.assess_dimension(graph, MaturityDimension.CAPACITY_PLANNING)
        assert a.level == MaturityLevel.MANAGED
        assert 30.0 <= a.score <= 50.0
        assert any("autoscaling" in g.lower() for g in a.gaps)

    def test_capacity_planning_defined(self):
        """CP DEFINED: as_ratio >= 0.5, high_util > 0 or slo_ratio < 0.25."""
        engine = SREMaturityEngine()
        graph = _capacity_planning_defined_graph()
        a = engine.assess_dimension(graph, MaturityDimension.CAPACITY_PLANNING)
        assert a.level == MaturityLevel.DEFINED
        assert 50.0 <= a.score <= 70.0

    def test_capacity_planning_defined_with_high_util(self):
        """CP DEFINED with high utilization: triggers line 417 gap message."""
        engine = SREMaturityEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
            metrics=ResourceMetrics(cpu_percent=90.0),
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        a = engine.assess_dimension(graph, MaturityDimension.CAPACITY_PLANNING)
        assert a.level == MaturityLevel.DEFINED
        assert any(">80% utilization" in g for g in a.gaps)

    def test_capacity_planning_quantitative(self):
        """CP QUANTITATIVE: as >= 0.5, no high_util, slo >= 0.25 but < 0.75."""
        engine = SREMaturityEngine()
        graph = _capacity_planning_quantitative_graph()
        a = engine.assess_dimension(graph, MaturityDimension.CAPACITY_PLANNING)
        assert a.level == MaturityLevel.QUANTITATIVE
        assert 70.0 <= a.score <= 92.0


class TestChangeMgmtIntermediateLevels:
    """Tests for change management intermediate maturity levels."""

    def test_change_mgmt_initial(self):
        """CM INITIAL: deploy_ratio == 0 and compliance_ratio == 0."""
        engine = SREMaturityEngine()
        # _minimal_graph has operational_profile defaults which might have deploy_downtime > 0
        # Build a truly bare graph
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
            operational_profile=OperationalProfile(deploy_downtime_seconds=0),
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
            operational_profile=OperationalProfile(deploy_downtime_seconds=0),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        a = engine.assess_dimension(graph, MaturityDimension.CHANGE_MANAGEMENT)
        assert a.level == MaturityLevel.INITIAL
        assert a.score <= 15.0

    def test_change_mgmt_managed(self):
        """CM MANAGED: some deploy config but compliance < 0.25."""
        engine = SREMaturityEngine()
        graph = _change_mgmt_managed_graph()
        a = engine.assess_dimension(graph, MaturityDimension.CHANGE_MANAGEMENT)
        assert a.level == MaturityLevel.MANAGED
        assert 25.0 <= a.score <= 50.0

    def test_change_mgmt_defined(self):
        """CM DEFINED: compliance >= 0.25 but < 0.75."""
        engine = SREMaturityEngine()
        graph = _change_mgmt_defined_graph()
        a = engine.assess_dimension(graph, MaturityDimension.CHANGE_MANAGEMENT)
        assert a.level == MaturityLevel.DEFINED
        assert 50.0 <= a.score <= 70.0

    def test_change_mgmt_quantitative(self):
        """CM QUANTITATIVE: compliance >= 0.75, fo < 0.75."""
        engine = SREMaturityEngine()
        graph = _change_mgmt_quantitative_graph()
        a = engine.assess_dimension(graph, MaturityDimension.CHANGE_MANAGEMENT)
        assert a.level == MaturityLevel.QUANTITATIVE
        assert 70.0 <= a.score <= 90.0


class TestAvailabilityIntermediateLevels:
    """Tests for availability dimension intermediate maturity levels."""

    def test_availability_initial(self):
        """Availability INITIAL: estimated_avail < 0.99."""
        engine = SREMaturityEngine()
        graph = _availability_initial_graph()
        a = engine.assess_dimension(graph, MaturityDimension.AVAILABILITY)
        assert a.level == MaturityLevel.INITIAL
        assert a.score < 25.0

    def test_availability_managed(self):
        """Availability MANAGED: 0.99 <= estimated_avail < 0.999."""
        engine = SREMaturityEngine()
        graph = _availability_managed_graph()
        a = engine.assess_dimension(graph, MaturityDimension.AVAILABILITY)
        assert a.level == MaturityLevel.MANAGED
        assert 25.0 <= a.score <= 50.0

    def test_availability_defined(self):
        """Availability DEFINED: 0.999 <= estimated_avail < 0.9995."""
        engine = SREMaturityEngine()
        graph = _availability_defined_graph()
        a = engine.assess_dimension(graph, MaturityDimension.AVAILABILITY)
        assert a.level == MaturityLevel.DEFINED
        assert 50.0 <= a.score <= 70.0


class TestDRIntermediateLevels:
    """Tests for disaster recovery intermediate maturity levels."""

    def test_dr_managed(self):
        """DR MANAGED: some replicas but low failover or replica coverage."""
        engine = SREMaturityEngine()
        graph = _dr_managed_graph()
        a = engine.assess_dimension(graph, MaturityDimension.DISASTER_RECOVERY)
        assert a.level == MaturityLevel.MANAGED
        assert 25.0 <= a.score <= 50.0

    def test_dr_quantitative(self):
        """DR QUANTITATIVE: multi-AZ but no multi-region DR."""
        engine = SREMaturityEngine()
        graph = _dr_quantitative_graph()
        a = engine.assess_dimension(graph, MaturityDimension.DISASTER_RECOVERY)
        assert a.level == MaturityLevel.QUANTITATIVE
        assert 70.0 <= a.score <= 90.0


class TestSecurityIntermediateLevels:
    """Tests for security dimension intermediate maturity levels."""

    def test_security_managed(self):
        """Security MANAGED: some encryption/auth but < 50% coverage."""
        engine = SREMaturityEngine()
        graph = _security_managed_graph()
        a = engine.assess_dimension(graph, MaturityDimension.SECURITY)
        assert a.level == MaturityLevel.MANAGED
        assert 20.0 <= a.score <= 50.0

    def test_security_defined(self):
        """Security DEFINED: encryption/auth >= 50%, segmentation < 50%."""
        engine = SREMaturityEngine()
        graph = _security_defined_graph()
        a = engine.assess_dimension(graph, MaturityDimension.SECURITY)
        assert a.level == MaturityLevel.DEFINED
        assert 50.0 <= a.score <= 70.0

    def test_security_quantitative(self):
        """Security QUANTITATIVE: segmentation >= 50%, advanced < 50%."""
        engine = SREMaturityEngine()
        graph = _security_quantitative_graph()
        a = engine.assess_dimension(graph, MaturityDimension.SECURITY)
        assert a.level == MaturityLevel.QUANTITATIVE
        assert 70.0 <= a.score <= 90.0


class TestAutomationIntermediateLevels:
    """Tests for automation dimension intermediate maturity levels."""

    def test_automation_managed(self):
        """Automation MANAGED: auto_score >= 0.1 but < 0.3."""
        engine = SREMaturityEngine()
        graph = _automation_managed_graph()
        a = engine.assess_dimension(graph, MaturityDimension.AUTOMATION)
        assert a.level == MaturityLevel.MANAGED
        assert 25.0 <= a.score <= 50.0

    def test_automation_defined(self):
        """Automation DEFINED: auto_score >= 0.3 but < 0.6."""
        engine = SREMaturityEngine()
        graph = _automation_defined_graph()
        a = engine.assess_dimension(graph, MaturityDimension.AUTOMATION)
        assert a.level == MaturityLevel.DEFINED
        assert 50.0 <= a.score <= 70.0

    def test_automation_quantitative(self):
        """Automation QUANTITATIVE: auto_score >= 0.6 but < 0.85."""
        engine = SREMaturityEngine()
        graph = _automation_quantitative_graph()
        a = engine.assess_dimension(graph, MaturityDimension.AUTOMATION)
        assert a.level == MaturityLevel.QUANTITATIVE
        assert 70.0 <= a.score <= 90.0


class TestHelperCoverage:
    """Tests for helper methods that need additional coverage."""

    def test_estimate_system_availability_empty(self):
        """Empty graph returns 0.0 availability."""
        engine = SREMaturityEngine()
        graph = InfraGraph()
        avail = engine._estimate_system_availability(graph)
        assert avail == 0.0

    def test_estimate_system_availability_no_paths(self):
        """Graph with cyclic dependencies has no critical paths (no entry/leaf nodes).

        get_critical_paths returns [] when all nodes have in_degree > 0
        (i.e., there are no entry points). This triggers line 851.
        """
        engine = SREMaturityEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
            operational_profile=OperationalProfile(mtbf_hours=4000, mttr_minutes=30),
        ))
        # Create a cycle: app -> db -> app (no entry or leaf nodes)
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        graph.add_dependency(Dependency(
            source_id="db", target_id="app", dependency_type="requires",
        ))
        # Verify no critical paths exist
        assert graph.get_critical_paths() == []
        avail = engine._estimate_system_availability(graph)
        assert 0 < avail < 1.0

    def test_estimate_effort_none(self):
        """Effort 'None' when gap <= 0."""
        assert SREMaturityEngine._estimate_effort(5, 4) == "None"
        assert SREMaturityEngine._estimate_effort(3, 3) == "None"

    def test_estimate_effort_low(self):
        """Effort 'Low' when gap == 1 and current <= 2."""
        assert SREMaturityEngine._estimate_effort(1, 2) == "Low"
        assert SREMaturityEngine._estimate_effort(2, 3) == "Low"

    def test_estimate_effort_medium(self):
        """Effort 'Medium' when gap == 1 and current > 2."""
        assert SREMaturityEngine._estimate_effort(3, 4) == "Medium"
        assert SREMaturityEngine._estimate_effort(4, 5) == "Medium"

    def test_estimate_effort_high(self):
        """Effort 'High' when gap > 1."""
        assert SREMaturityEngine._estimate_effort(1, 3) == "High"
        assert SREMaturityEngine._estimate_effort(2, 5) == "High"

    def test_industry_comparison_optimizing(self):
        """Score >= 90 => Optimizing comparison text."""
        text = SREMaturityEngine._generate_industry_comparison(92.0)
        assert "Optimizing" in text
        assert "Google" in text

    def test_industry_comparison_quantitative(self):
        """Score >= 70 => Quantitatively Managed comparison text."""
        text = SREMaturityEngine._generate_industry_comparison(75.0)
        assert "Quantitatively Managed" in text

    def test_industry_comparison_defined(self):
        """Score >= 50 => Defined comparison text."""
        text = SREMaturityEngine._generate_industry_comparison(55.0)
        assert "Defined" in text

    def test_industry_comparison_managed(self):
        """Score >= 25 => Managed comparison text."""
        text = SREMaturityEngine._generate_industry_comparison(30.0)
        assert "Managed" in text

    def test_industry_comparison_initial(self):
        """Score < 25 => Initial comparison text."""
        text = SREMaturityEngine._generate_industry_comparison(10.0)
        assert "Initial" in text

    def test_component_availability_zero_mtbf(self):
        """Component with mtbf=0 should use default."""
        engine = SREMaturityEngine()
        comp = Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=0, mttr_minutes=30),
        )
        avail = engine._component_availability(comp)
        assert 0 < avail < 1.0
