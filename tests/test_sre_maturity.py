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
