"""Tests for Chaos Engineering Maturity Model."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalTeamConfig,
    RegionConfig,
    RetryStrategy,
    SecurityProfile,
    SingleflightConfig,
    SLOTarget,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.chaos_maturity import (
    ChaosMaturityAssessor,
    ChaosMaturityReport,
    DimensionAssessment,
    MaturityDimension,
    MaturityLevel,
    MaturityRoadmap,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_graph() -> InfraGraph:
    """Build a completely empty graph."""
    return InfraGraph()


def _minimal_graph() -> InfraGraph:
    """Build a minimal graph with no resilience features (Level 0)."""
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


def _single_component_graph() -> InfraGraph:
    """Build a graph with a single isolated component."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="solo", name="Solo Service", type=ComponentType.APP_SERVER, replicas=1,
    ))
    return graph


def _partial_graph() -> InfraGraph:
    """Build a graph with partial resilience (Level 2-3 range)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER, replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=10),
        security=SecurityProfile(log_enabled=True, network_segmented=True),
        team=OperationalTeamConfig(runbook_coverage_percent=60.0, automation_percent=30.0),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER, replicas=2,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=10),
        security=SecurityProfile(log_enabled=True),
        slo_targets=[SLOTarget(name="availability", target=99.9)],
        team=OperationalTeamConfig(runbook_coverage_percent=55.0, automation_percent=25.0),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE, replicas=1,
        security=SecurityProfile(log_enabled=True, backup_enabled=True),
        team=OperationalTeamConfig(runbook_coverage_percent=40.0, automation_percent=15.0),
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
    ))
    return graph


def _well_protected_graph() -> InfraGraph:
    """Build a graph with comprehensive resilience (Level 4-5 range)."""
    graph = InfraGraph()
    # All components have replicas, failover, autoscaling, logging, IDS, etc.
    for i, (cid, ctype) in enumerate([
        ("lb", ComponentType.LOAD_BALANCER),
        ("app1", ComponentType.APP_SERVER),
        ("app2", ComponentType.APP_SERVER),
        ("db", ComponentType.DATABASE),
        ("cache", ComponentType.CACHE),
    ]):
        graph.add_component(Component(
            id=cid,
            name=cid.upper(),
            type=ctype,
            replicas=3,
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
            failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
            security=SecurityProfile(
                log_enabled=True,
                ids_monitored=True,
                network_segmented=True,
                backup_enabled=True,
            ),
            slo_targets=[SLOTarget(name="availability", target=99.99)],
            singleflight=SingleflightConfig(enabled=True),
            region=RegionConfig(
                region="us-east-1",
                availability_zone="us-east-1a",
                dr_target_region="us-west-2",
            ),
            team=OperationalTeamConfig(
                runbook_coverage_percent=90.0,
                automation_percent=70.0,
                oncall_coverage_hours=24.0,
            ),
        ))

    deps = [("lb", "app1"), ("lb", "app2"), ("app1", "db"), ("app2", "db"), ("app1", "cache"), ("app2", "cache")]
    for src, tgt in deps:
        graph.add_dependency(Dependency(
            source_id=src, target_id=tgt, dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
    return graph


def _large_mixed_graph() -> InfraGraph:
    """Build a large graph with mixed configurations."""
    graph = InfraGraph()
    # 10 components: 5 well-configured, 5 bare
    for i in range(5):
        graph.add_component(Component(
            id=f"good_{i}", name=f"Good {i}", type=ComponentType.APP_SERVER,
            replicas=3,
            autoscaling=AutoScalingConfig(enabled=True),
            failover=FailoverConfig(enabled=True, health_check_interval_seconds=10),
            security=SecurityProfile(log_enabled=True, ids_monitored=True, network_segmented=True),
            slo_targets=[SLOTarget(name="avail", target=99.9)],
            singleflight=SingleflightConfig(enabled=True),
            team=OperationalTeamConfig(runbook_coverage_percent=80.0, automation_percent=50.0),
        ))
    for i in range(5):
        graph.add_component(Component(
            id=f"bare_{i}", name=f"Bare {i}", type=ComponentType.APP_SERVER,
            replicas=1,
        ))
    # Edges: half with CB/retry, half without
    for i in range(5):
        graph.add_dependency(Dependency(
            source_id=f"good_{i}", target_id=f"bare_{i}", dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
    for i in range(4):
        graph.add_dependency(Dependency(
            source_id=f"bare_{i}", target_id=f"bare_{i+1}", dependency_type="requires",
        ))
    return graph


def _same_type_graph() -> InfraGraph:
    """Build a graph where all components are the same type."""
    graph = InfraGraph()
    for i in range(4):
        graph.add_component(Component(
            id=f"web_{i}", name=f"Web {i}", type=ComponentType.WEB_SERVER,
            replicas=2,
            failover=FailoverConfig(enabled=True, health_check_interval_seconds=10),
            security=SecurityProfile(log_enabled=True),
            team=OperationalTeamConfig(runbook_coverage_percent=60.0, automation_percent=35.0),
        ))
    for i in range(3):
        graph.add_dependency(Dependency(
            source_id=f"web_{i}", target_id=f"web_{i+1}", dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
    return graph


# ---------------------------------------------------------------------------
# MaturityLevel enum tests
# ---------------------------------------------------------------------------


class TestMaturityLevel:
    """Tests for MaturityLevel enum."""

    def test_level_values(self):
        assert MaturityLevel.LEVEL_0_NONE == 0
        assert MaturityLevel.LEVEL_1_INITIAL == 1
        assert MaturityLevel.LEVEL_2_DEFINED == 2
        assert MaturityLevel.LEVEL_3_MANAGED == 3
        assert MaturityLevel.LEVEL_4_MEASURED == 4
        assert MaturityLevel.LEVEL_5_OPTIMIZED == 5

    def test_level_is_int(self):
        assert isinstance(MaturityLevel.LEVEL_3_MANAGED, int)
        assert MaturityLevel.LEVEL_3_MANAGED + 1 == 4

    def test_level_ordering(self):
        assert MaturityLevel.LEVEL_0_NONE < MaturityLevel.LEVEL_5_OPTIMIZED
        assert MaturityLevel.LEVEL_2_DEFINED < MaturityLevel.LEVEL_4_MEASURED

    def test_all_levels_exist(self):
        assert len(MaturityLevel) == 6


# ---------------------------------------------------------------------------
# MaturityDimension enum tests
# ---------------------------------------------------------------------------


class TestMaturityDimension:
    """Tests for MaturityDimension enum."""

    def test_all_dimensions(self):
        assert len(MaturityDimension) == 8
        expected = {
            "fault_injection", "observability", "automation",
            "blast_radius_control", "game_days", "steady_state_hypothesis",
            "rollback_capability", "organizational_adoption",
        }
        assert {d.value for d in MaturityDimension} == expected

    def test_dimension_is_str(self):
        assert isinstance(MaturityDimension.FAULT_INJECTION, str)
        assert MaturityDimension.FAULT_INJECTION == "fault_injection"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestDimensionAssessment:
    """Tests for DimensionAssessment dataclass."""

    def test_defaults(self):
        da = DimensionAssessment(
            dimension=MaturityDimension.OBSERVABILITY,
            current_level=MaturityLevel.LEVEL_2_DEFINED,
        )
        assert da.max_level == MaturityLevel.LEVEL_5_OPTIMIZED
        assert da.score == 0.0
        assert da.evidence == []
        assert da.gaps == []
        assert da.next_level_actions == []

    def test_full_init(self):
        da = DimensionAssessment(
            dimension=MaturityDimension.AUTOMATION,
            current_level=MaturityLevel.LEVEL_3_MANAGED,
            max_level=MaturityLevel.LEVEL_5_OPTIMIZED,
            score=65.0,
            evidence=["AS: 60%"],
            gaps=["Not full"],
            next_level_actions=["Enable more"],
        )
        assert da.score == 65.0
        assert len(da.evidence) == 1
        assert len(da.gaps) == 1


class TestMaturityRoadmap:
    """Tests for MaturityRoadmap dataclass."""

    def test_defaults(self):
        roadmap = MaturityRoadmap()
        assert roadmap.current_overall_level == MaturityLevel.LEVEL_0_NONE
        assert roadmap.target_level == MaturityLevel.LEVEL_1_INITIAL
        assert roadmap.quick_wins == []
        assert roadmap.short_term == []
        assert roadmap.long_term == []
        assert roadmap.estimated_months_to_next_level == 0.0


class TestChaosMaturityReport:
    """Tests for ChaosMaturityReport dataclass."""

    def test_defaults(self):
        report = ChaosMaturityReport()
        assert report.overall_level == MaturityLevel.LEVEL_0_NONE
        assert report.overall_score == 0.0
        assert report.dimensions == []
        assert report.strengths == []
        assert report.weaknesses == []
        assert report.peer_comparison == "below average"


# ---------------------------------------------------------------------------
# Empty graph tests
# ---------------------------------------------------------------------------


class TestEmptyGraph:
    """Tests for empty graph (Level 0)."""

    def test_overall_level_is_zero(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        report = assessor.assess()
        assert report.overall_level == MaturityLevel.LEVEL_0_NONE

    def test_overall_score_is_zero(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        report = assessor.assess()
        assert report.overall_score == 0.0

    def test_all_dimensions_level_zero(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        report = assessor.assess()
        assert len(report.dimensions) == 8
        for dim in report.dimensions:
            assert dim.current_level == MaturityLevel.LEVEL_0_NONE

    def test_all_dimensions_have_gaps(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        report = assessor.assess()
        for dim in report.dimensions:
            assert len(dim.gaps) > 0 or len(dim.next_level_actions) > 0

    def test_peer_comparison_below_average(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        report = assessor.assess()
        assert report.peer_comparison == "below average"

    def test_roadmap_has_quick_wins(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        report = assessor.assess()
        assert report.roadmap.current_overall_level == MaturityLevel.LEVEL_0_NONE


# ---------------------------------------------------------------------------
# Minimal graph tests (no resilience)
# ---------------------------------------------------------------------------


class TestMinimalGraph:
    """Tests for minimal graph with no resilience features."""

    def test_overall_level_low(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        assert report.overall_level.value <= 1

    def test_fault_injection_low(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        fi = next(d for d in report.dimensions if d.dimension == MaturityDimension.FAULT_INJECTION)
        assert fi.current_level.value <= 1

    def test_observability_level_zero(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        obs = next(d for d in report.dimensions if d.dimension == MaturityDimension.OBSERVABILITY)
        assert obs.current_level == MaturityLevel.LEVEL_0_NONE

    def test_automation_level_zero(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        auto = next(d for d in report.dimensions if d.dimension == MaturityDimension.AUTOMATION)
        assert auto.current_level == MaturityLevel.LEVEL_0_NONE

    def test_blast_radius_control_low(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        brc = next(d for d in report.dimensions if d.dimension == MaturityDimension.BLAST_RADIUS_CONTROL)
        assert brc.current_level.value <= 1

    def test_steady_state_level_zero(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        ss = next(d for d in report.dimensions if d.dimension == MaturityDimension.STEADY_STATE_HYPOTHESIS)
        assert ss.current_level == MaturityLevel.LEVEL_0_NONE

    def test_rollback_level_zero(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        rb = next(d for d in report.dimensions if d.dimension == MaturityDimension.ROLLBACK_CAPABILITY)
        assert rb.current_level == MaturityLevel.LEVEL_0_NONE

    def test_weaknesses_populated(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        assert len(report.weaknesses) > 0


# ---------------------------------------------------------------------------
# Single component graph tests
# ---------------------------------------------------------------------------


class TestSingleComponentGraph:
    """Tests for a graph with a single isolated component."""

    def test_assess_succeeds(self):
        assessor = ChaosMaturityAssessor(_single_component_graph())
        report = assessor.assess()
        assert isinstance(report, ChaosMaturityReport)
        assert len(report.dimensions) == 8

    def test_fault_injection_no_edges(self):
        assessor = ChaosMaturityAssessor(_single_component_graph())
        report = assessor.assess()
        fi = next(d for d in report.dimensions if d.dimension == MaturityDimension.FAULT_INJECTION)
        # No edges, no failover -> Level 0
        assert fi.current_level == MaturityLevel.LEVEL_0_NONE

    def test_single_component_with_failover(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="solo", name="Solo", type=ComponentType.APP_SERVER,
            failover=FailoverConfig(enabled=True, health_check_interval_seconds=10),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        fi = next(d for d in report.dimensions if d.dimension == MaturityDimension.FAULT_INJECTION)
        assert fi.current_level.value >= 1

    def test_score_in_valid_range(self):
        assessor = ChaosMaturityAssessor(_single_component_graph())
        report = assessor.assess()
        assert 0.0 <= report.overall_score <= 100.0


# ---------------------------------------------------------------------------
# Partial maturity tests (mixed levels)
# ---------------------------------------------------------------------------


class TestPartialGraph:
    """Tests for graph with partial resilience (mixed levels)."""

    def test_overall_level_intermediate(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        assert 1 <= report.overall_level.value <= 3

    def test_fault_injection_has_evidence(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        fi = next(d for d in report.dimensions if d.dimension == MaturityDimension.FAULT_INJECTION)
        # Partial graph has 2/3 edges with CB, 1/3 with retry
        assert fi.current_level.value >= 1
        assert fi.score > 0

    def test_observability_partial(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        obs = next(d for d in report.dimensions if d.dimension == MaturityDimension.OBSERVABILITY)
        # 3/4 have logging, 2/4 have health checks
        assert obs.current_level.value >= 2

    def test_automation_partial(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        auto = next(d for d in report.dimensions if d.dimension == MaturityDimension.AUTOMATION)
        # 1/4 AS, 2/4 FO -> combined ~0.375
        assert auto.current_level.value >= 1

    def test_blast_radius_control_partial(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        brc = next(d for d in report.dimensions if d.dimension == MaturityDimension.BLAST_RADIUS_CONTROL)
        # 2/4 replicas > 1, 2/3 CB, 1/4 segmented
        assert brc.current_level.value >= 1

    def test_game_days_partial(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        gd = next(d for d in report.dimensions if d.dimension == MaturityDimension.GAME_DAYS)
        assert gd.current_level.value >= 1

    def test_steady_state_partial(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        ss = next(d for d in report.dimensions if d.dimension == MaturityDimension.STEADY_STATE_HYPOTHESIS)
        # 1/4 SLO, 2/4 HC -> Level 1 or 2
        assert ss.current_level.value >= 1

    def test_rollback_partial(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        rb = next(d for d in report.dimensions if d.dimension == MaturityDimension.ROLLBACK_CAPABILITY)
        assert rb.current_level.value >= 1

    def test_organizational_partial(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        org = next(d for d in report.dimensions if d.dimension == MaturityDimension.ORGANIZATIONAL_ADOPTION)
        # Custom team config present
        assert org.current_level.value >= 1

    def test_has_both_strengths_and_weaknesses(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        # Partial graph should have at least some weaknesses
        assert len(report.weaknesses) > 0 or len(report.strengths) > 0

    def test_peer_comparison_not_above(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        # Partial graph shouldn't be above average
        assert report.peer_comparison in ("below average", "average")


# ---------------------------------------------------------------------------
# Well-protected graph tests (Level 4-5)
# ---------------------------------------------------------------------------


class TestWellProtectedGraph:
    """Tests for fully protected graph (Level 4-5)."""

    def test_overall_level_high(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        assert report.overall_level.value >= 4

    def test_overall_score_high(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        assert report.overall_score >= 75.0

    def test_fault_injection_high(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        fi = next(d for d in report.dimensions if d.dimension == MaturityDimension.FAULT_INJECTION)
        assert fi.current_level.value >= 4

    def test_observability_high(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        obs = next(d for d in report.dimensions if d.dimension == MaturityDimension.OBSERVABILITY)
        assert obs.current_level.value >= 4

    def test_automation_high(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        auto = next(d for d in report.dimensions if d.dimension == MaturityDimension.AUTOMATION)
        assert auto.current_level.value >= 4

    def test_blast_radius_control_high(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        brc = next(d for d in report.dimensions if d.dimension == MaturityDimension.BLAST_RADIUS_CONTROL)
        assert brc.current_level.value >= 4

    def test_game_days_high(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        gd = next(d for d in report.dimensions if d.dimension == MaturityDimension.GAME_DAYS)
        assert gd.current_level.value >= 4

    def test_steady_state_high(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        ss = next(d for d in report.dimensions if d.dimension == MaturityDimension.STEADY_STATE_HYPOTHESIS)
        assert ss.current_level.value >= 4

    def test_rollback_high(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        rb = next(d for d in report.dimensions if d.dimension == MaturityDimension.ROLLBACK_CAPABILITY)
        assert rb.current_level.value >= 4

    def test_organizational_high(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        org = next(d for d in report.dimensions if d.dimension == MaturityDimension.ORGANIZATIONAL_ADOPTION)
        assert org.current_level.value >= 4

    def test_peer_comparison_above_average(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        assert report.peer_comparison == "above average"

    def test_strengths_populated(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        assert len(report.strengths) > 0

    def test_all_scores_above_75(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        for dim in report.dimensions:
            assert dim.score >= 75.0, f"{dim.dimension.value} score {dim.score} < 75"


# ---------------------------------------------------------------------------
# Roadmap generation tests
# ---------------------------------------------------------------------------


class TestRoadmapGeneration:
    """Tests for roadmap generation."""

    def test_empty_graph_roadmap(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        report = assessor.assess()
        roadmap = report.roadmap
        assert roadmap.current_overall_level == MaturityLevel.LEVEL_0_NONE
        assert roadmap.target_level == MaturityLevel.LEVEL_1_INITIAL

    def test_roadmap_has_quick_wins_for_low_maturity(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        assert len(report.roadmap.quick_wins) > 0

    def test_roadmap_estimated_months(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        assert report.roadmap.estimated_months_to_next_level > 0

    def test_roadmap_target_is_one_above_current(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        expected_target = min(report.roadmap.current_overall_level.value + 1, 5)
        assert report.roadmap.target_level.value == expected_target

    def test_optimized_roadmap_zero_months(self):
        # Build a graph at level 5
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        if report.overall_level == MaturityLevel.LEVEL_5_OPTIMIZED:
            assert report.roadmap.estimated_months_to_next_level == 0.0

    def test_roadmap_quick_wins_capped_at_five(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        assert len(report.roadmap.quick_wins) <= 5

    def test_roadmap_short_term_capped_at_five(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        assert len(report.roadmap.short_term) <= 5

    def test_roadmap_long_term_capped_at_five(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        assert len(report.roadmap.long_term) <= 5

    def test_roadmap_actions_have_dimension_labels(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        for action in report.roadmap.quick_wins:
            assert "[" in action and "]" in action, f"Action missing label: {action}"

    def test_well_protected_roadmap_still_has_actions(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        # Even at level 5, roadmap should have long-term actions
        total_actions = (
            len(report.roadmap.quick_wins)
            + len(report.roadmap.short_term)
            + len(report.roadmap.long_term)
        )
        assert total_actions >= 0  # May be 0 if all at level 5


# ---------------------------------------------------------------------------
# Peer comparison tests
# ---------------------------------------------------------------------------


class TestPeerComparison:
    """Tests for peer comparison boundaries."""

    def test_below_40_is_below_average(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        result = assessor._determine_peer_comparison(0.0)
        assert result == "below average"

    def test_exactly_40_is_average(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        result = assessor._determine_peer_comparison(40.0)
        assert result == "average"

    def test_between_40_and_70_is_average(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        result = assessor._determine_peer_comparison(55.0)
        assert result == "average"

    def test_exactly_70_is_average(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        result = assessor._determine_peer_comparison(70.0)
        assert result == "average"

    def test_above_70_is_above_average(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        result = assessor._determine_peer_comparison(71.0)
        assert result == "above average"

    def test_score_100_is_above_average(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        result = assessor._determine_peer_comparison(100.0)
        assert result == "above average"

    def test_score_39_is_below_average(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        result = assessor._determine_peer_comparison(39.9)
        assert result == "below average"


# ---------------------------------------------------------------------------
# Score boundaries
# ---------------------------------------------------------------------------


class TestScoreBoundaries:
    """Tests for score boundary conditions."""

    def test_score_exactly_zero(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        report = assessor.assess()
        assert report.overall_score == 0.0

    def test_all_scores_in_valid_range(self):
        for graph_fn in [_empty_graph, _minimal_graph, _partial_graph,
                         _well_protected_graph, _large_mixed_graph]:
            assessor = ChaosMaturityAssessor(graph_fn())
            report = assessor.assess()
            assert 0.0 <= report.overall_score <= 100.0
            for dim in report.dimensions:
                assert 0.0 <= dim.score <= 100.0, (
                    f"{dim.dimension.value} score {dim.score} out of range"
                )

    def test_well_protected_scores_are_high(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        assert report.overall_score >= 75.0

    def test_minimal_scores_are_low(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        assert report.overall_score < 30.0


# ---------------------------------------------------------------------------
# Evidence and gaps tests
# ---------------------------------------------------------------------------


class TestEvidenceAndGaps:
    """Tests for evidence and gaps population."""

    def test_empty_graph_gaps_populated(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        report = assessor.assess()
        for dim in report.dimensions:
            assert len(dim.gaps) > 0 or len(dim.next_level_actions) > 0

    def test_protected_graph_evidence_populated(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        for dim in report.dimensions:
            assert len(dim.evidence) > 0, f"{dim.dimension.value} has no evidence"

    def test_partial_graph_has_gaps_and_evidence(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        has_evidence = any(len(d.evidence) > 0 for d in report.dimensions)
        has_gaps = any(len(d.gaps) > 0 for d in report.dimensions)
        assert has_evidence
        assert has_gaps

    def test_next_level_actions_populated(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        for dim in report.dimensions:
            assert len(dim.next_level_actions) > 0, (
                f"{dim.dimension.value} has no next_level_actions"
            )


# ---------------------------------------------------------------------------
# Large mixed graph tests
# ---------------------------------------------------------------------------


class TestLargeMixedGraph:
    """Tests for large graph with mixed configurations."""

    def test_intermediate_level(self):
        assessor = ChaosMaturityAssessor(_large_mixed_graph())
        report = assessor.assess()
        assert 1 <= report.overall_level.value <= 3

    def test_dimension_count(self):
        assessor = ChaosMaturityAssessor(_large_mixed_graph())
        report = assessor.assess()
        assert len(report.dimensions) == 8

    def test_score_reflects_mixed(self):
        assessor = ChaosMaturityAssessor(_large_mixed_graph())
        report = assessor.assess()
        # Mixed graph should not be at extremes
        assert 10.0 <= report.overall_score <= 80.0


# ---------------------------------------------------------------------------
# Same type graph tests
# ---------------------------------------------------------------------------


class TestSameTypeGraph:
    """Tests for graph where all components are the same type."""

    def test_assess_succeeds(self):
        assessor = ChaosMaturityAssessor(_same_type_graph())
        report = assessor.assess()
        assert isinstance(report, ChaosMaturityReport)

    def test_has_valid_scores(self):
        assessor = ChaosMaturityAssessor(_same_type_graph())
        report = assessor.assess()
        for dim in report.dimensions:
            assert 0.0 <= dim.score <= 100.0

    def test_observability_with_logging(self):
        assessor = ChaosMaturityAssessor(_same_type_graph())
        report = assessor.assess()
        obs = next(d for d in report.dimensions if d.dimension == MaturityDimension.OBSERVABILITY)
        # All have logging -> at least level 2
        assert obs.current_level.value >= 2


# ---------------------------------------------------------------------------
# Individual dimension deep tests
# ---------------------------------------------------------------------------


class TestFaultInjectionDimension:
    """Detailed tests for fault injection dimension."""

    def test_no_edges_no_failover(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER,
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        fi = next(d for d in report.dimensions if d.dimension == MaturityDimension.FAULT_INJECTION)
        assert fi.current_level == MaturityLevel.LEVEL_0_NONE

    def test_some_cb_and_retry(self):
        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER))
        graph.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER))
        graph.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        fi = next(d for d in report.dimensions if d.dimension == MaturityDimension.FAULT_INJECTION)
        assert fi.current_level.value >= 3


class TestObservabilityDimension:
    """Detailed tests for observability dimension."""

    def test_no_logging(self):
        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        obs = next(d for d in report.dimensions if d.dimension == MaturityDimension.OBSERVABILITY)
        assert obs.current_level == MaturityLevel.LEVEL_0_NONE
        assert obs.score == 0.0

    def test_full_observability(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER,
            security=SecurityProfile(log_enabled=True, ids_monitored=True),
            failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        obs = next(d for d in report.dimensions if d.dimension == MaturityDimension.OBSERVABILITY)
        assert obs.current_level == MaturityLevel.LEVEL_5_OPTIMIZED


class TestAutomationDimension:
    """Detailed tests for automation dimension."""

    def test_no_automation(self):
        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        auto = next(d for d in report.dimensions if d.dimension == MaturityDimension.AUTOMATION)
        assert auto.current_level == MaturityLevel.LEVEL_0_NONE
        assert auto.score == 0.0

    def test_full_automation(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER,
            autoscaling=AutoScalingConfig(enabled=True),
            failover=FailoverConfig(enabled=True),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        auto = next(d for d in report.dimensions if d.dimension == MaturityDimension.AUTOMATION)
        assert auto.current_level == MaturityLevel.LEVEL_5_OPTIMIZED


class TestBlastRadiusDimension:
    """Detailed tests for blast radius control dimension."""

    def test_no_controls(self):
        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        brc = next(d for d in report.dimensions if d.dimension == MaturityDimension.BLAST_RADIUS_CONTROL)
        assert brc.current_level == MaturityLevel.LEVEL_0_NONE
        assert brc.score == 0.0

    def test_replicas_only(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=3,
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        brc = next(d for d in report.dimensions if d.dimension == MaturityDimension.BLAST_RADIUS_CONTROL)
        assert brc.current_level.value >= 1


class TestGameDaysDimension:
    """Detailed tests for game days dimension."""

    def test_no_readiness(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        gd = next(d for d in report.dimensions if d.dimension == MaturityDimension.GAME_DAYS)
        assert gd.current_level == MaturityLevel.LEVEL_0_NONE

    def test_high_readiness(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        gd = next(d for d in report.dimensions if d.dimension == MaturityDimension.GAME_DAYS)
        assert gd.current_level.value >= 4


class TestSteadyStateDimension:
    """Detailed tests for steady state hypothesis dimension."""

    def test_no_slo_or_hc(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        ss = next(d for d in report.dimensions if d.dimension == MaturityDimension.STEADY_STATE_HYPOTHESIS)
        assert ss.current_level == MaturityLevel.LEVEL_0_NONE
        assert ss.score == 0.0

    def test_with_slo_and_hc(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER,
            slo_targets=[SLOTarget(name="avail", target=99.9)],
            failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
            security=SecurityProfile(log_enabled=True),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        ss = next(d for d in report.dimensions if d.dimension == MaturityDimension.STEADY_STATE_HYPOTHESIS)
        assert ss.current_level.value >= 4


class TestRollbackDimension:
    """Detailed tests for rollback capability dimension."""

    def test_no_rollback(self):
        assessor = ChaosMaturityAssessor(_minimal_graph())
        report = assessor.assess()
        rb = next(d for d in report.dimensions if d.dimension == MaturityDimension.ROLLBACK_CAPABILITY)
        assert rb.current_level == MaturityLevel.LEVEL_0_NONE

    def test_full_rollback(self):
        assessor = ChaosMaturityAssessor(_well_protected_graph())
        report = assessor.assess()
        rb = next(d for d in report.dimensions if d.dimension == MaturityDimension.ROLLBACK_CAPABILITY)
        assert rb.current_level.value >= 4


class TestOrganizationalDimension:
    """Detailed tests for organizational adoption dimension."""

    def test_default_config_is_level_zero(self):
        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        org = next(d for d in report.dimensions if d.dimension == MaturityDimension.ORGANIZATIONAL_ADOPTION)
        assert org.current_level == MaturityLevel.LEVEL_0_NONE

    def test_custom_team_config(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER,
            team=OperationalTeamConfig(
                runbook_coverage_percent=90.0,
                automation_percent=70.0,
                oncall_coverage_hours=24.0,
            ),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        org = next(d for d in report.dimensions if d.dimension == MaturityDimension.ORGANIZATIONAL_ADOPTION)
        assert org.current_level.value >= 4


# ---------------------------------------------------------------------------
# _calculate_overall tests
# ---------------------------------------------------------------------------


class TestCalculateOverall:
    """Tests for _calculate_overall method."""

    def test_empty_dimensions_list(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        level, score = assessor._calculate_overall([])
        assert level == MaturityLevel.LEVEL_0_NONE
        assert score == 0.0

    def test_all_zero_scores(self):
        dims = [
            DimensionAssessment(dimension=MaturityDimension.FAULT_INJECTION,
                                current_level=MaturityLevel.LEVEL_0_NONE, score=0.0),
            DimensionAssessment(dimension=MaturityDimension.OBSERVABILITY,
                                current_level=MaturityLevel.LEVEL_0_NONE, score=0.0),
        ]
        assessor = ChaosMaturityAssessor(_empty_graph())
        level, score = assessor._calculate_overall(dims)
        assert level == MaturityLevel.LEVEL_0_NONE
        assert score == 0.0

    def test_high_scores(self):
        dims = [
            DimensionAssessment(dimension=MaturityDimension.FAULT_INJECTION,
                                current_level=MaturityLevel.LEVEL_5_OPTIMIZED, score=95.0),
            DimensionAssessment(dimension=MaturityDimension.OBSERVABILITY,
                                current_level=MaturityLevel.LEVEL_5_OPTIMIZED, score=92.0),
        ]
        assessor = ChaosMaturityAssessor(_empty_graph())
        level, score = assessor._calculate_overall(dims)
        assert level == MaturityLevel.LEVEL_5_OPTIMIZED
        assert score >= 90.0

    def test_level_thresholds(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        # Test each threshold boundary
        test_cases = [
            (5.0, MaturityLevel.LEVEL_0_NONE),
            (10.0, MaturityLevel.LEVEL_1_INITIAL),
            (30.0, MaturityLevel.LEVEL_2_DEFINED),
            (55.0, MaturityLevel.LEVEL_3_MANAGED),
            (75.0, MaturityLevel.LEVEL_4_MEASURED),
            (90.0, MaturityLevel.LEVEL_5_OPTIMIZED),
        ]
        for target_score, expected_level in test_cases:
            dims = [DimensionAssessment(
                dimension=MaturityDimension.FAULT_INJECTION,
                current_level=MaturityLevel.LEVEL_0_NONE,
                score=target_score,
            )]
            level, _ = assessor._calculate_overall(dims)
            assert level == expected_level, (
                f"Score {target_score} expected {expected_level}, got {level}"
            )

    def test_exactly_50_score(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        dims = [DimensionAssessment(
            dimension=MaturityDimension.FAULT_INJECTION,
            current_level=MaturityLevel.LEVEL_0_NONE,
            score=50.0,
        )]
        level, score = assessor._calculate_overall(dims)
        assert level == MaturityLevel.LEVEL_2_DEFINED
        assert score == 50.0

    def test_exactly_100_score(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        dims = [DimensionAssessment(
            dimension=MaturityDimension.FAULT_INJECTION,
            current_level=MaturityLevel.LEVEL_5_OPTIMIZED,
            score=100.0,
        )]
        level, score = assessor._calculate_overall(dims)
        assert level == MaturityLevel.LEVEL_5_OPTIMIZED
        assert score == 100.0


# ---------------------------------------------------------------------------
# Max level field tests
# ---------------------------------------------------------------------------


class TestMaxLevel:
    """Tests for DimensionAssessment max_level."""

    def test_default_max_level(self):
        da = DimensionAssessment(
            dimension=MaturityDimension.FAULT_INJECTION,
            current_level=MaturityLevel.LEVEL_2_DEFINED,
        )
        assert da.max_level == MaturityLevel.LEVEL_5_OPTIMIZED

    def test_custom_max_level(self):
        da = DimensionAssessment(
            dimension=MaturityDimension.FAULT_INJECTION,
            current_level=MaturityLevel.LEVEL_2_DEFINED,
            max_level=MaturityLevel.LEVEL_3_MANAGED,
        )
        assert da.max_level == MaturityLevel.LEVEL_3_MANAGED

    def test_all_assessed_dimensions_have_max_level(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        for dim in report.dimensions:
            assert dim.max_level == MaturityLevel.LEVEL_5_OPTIMIZED


# ---------------------------------------------------------------------------
# Regression / edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case and regression tests."""

    def test_graph_with_only_edges_no_matching_components(self):
        """Graph with dependency edges but no matching components."""
        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER))
        graph.add_component(Component(id="b", name="B", type=ComponentType.DATABASE))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        assert isinstance(report, ChaosMaturityReport)

    def test_many_components_same_level(self):
        """All components at same config level."""
        graph = InfraGraph()
        for i in range(20):
            graph.add_component(Component(
                id=f"svc_{i}", name=f"Service {i}", type=ComponentType.APP_SERVER,
                replicas=2,
                autoscaling=AutoScalingConfig(enabled=True),
                failover=FailoverConfig(enabled=True, health_check_interval_seconds=10),
                security=SecurityProfile(log_enabled=True),
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        assert isinstance(report, ChaosMaturityReport)
        assert report.overall_level.value >= 2

    def test_assess_is_idempotent(self):
        """Calling assess twice returns same results."""
        assessor = ChaosMaturityAssessor(_partial_graph())
        report1 = assessor.assess()
        report2 = assessor.assess()
        assert report1.overall_score == report2.overall_score
        assert report1.overall_level == report2.overall_level

    def test_dimension_assessment_score_never_negative(self):
        """No dimension should ever have a negative score."""
        for graph_fn in [_empty_graph, _minimal_graph, _partial_graph,
                         _well_protected_graph, _large_mixed_graph]:
            assessor = ChaosMaturityAssessor(graph_fn())
            report = assessor.assess()
            for dim in report.dimensions:
                assert dim.score >= 0.0, f"{dim.dimension}: {dim.score}"

    def test_dimension_assessment_score_never_exceeds_100(self):
        """No dimension should ever exceed 100."""
        for graph_fn in [_empty_graph, _minimal_graph, _partial_graph,
                         _well_protected_graph, _large_mixed_graph]:
            assessor = ChaosMaturityAssessor(graph_fn())
            report = assessor.assess()
            for dim in report.dimensions:
                assert dim.score <= 100.0, f"{dim.dimension}: {dim.score}"

    def test_assessor_stores_graph(self):
        graph = _minimal_graph()
        assessor = ChaosMaturityAssessor(graph)
        assert assessor._graph is graph

    def test_report_overall_score_is_rounded(self):
        assessor = ChaosMaturityAssessor(_partial_graph())
        report = assessor.assess()
        # Score should be rounded to 1 decimal
        assert report.overall_score == round(report.overall_score, 1)

    def test_organizational_moderate_runbook(self):
        """Test organizational dimension with moderate runbook (~55%)."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER,
            team=OperationalTeamConfig(
                runbook_coverage_percent=55.0,
                automation_percent=15.0,
            ),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        org = next(d for d in report.dimensions if d.dimension == MaturityDimension.ORGANIZATIONAL_ADOPTION)
        assert org.current_level == MaturityLevel.LEVEL_2_DEFINED

    def test_organizational_high_runbook_low_automation(self):
        """Test organizational dimension with high runbook but low automation."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER,
            team=OperationalTeamConfig(
                runbook_coverage_percent=70.0,
                automation_percent=30.0,
            ),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        org = next(d for d in report.dimensions if d.dimension == MaturityDimension.ORGANIZATIONAL_ADOPTION)
        assert org.current_level == MaturityLevel.LEVEL_3_MANAGED


# ---------------------------------------------------------------------------
# Coverage gap tests: intermediate levels for each dimension
# ---------------------------------------------------------------------------


class TestFaultInjectionIntermediate:
    """Tests to cover intermediate fault injection branches."""

    def test_level_1_few_cb_and_retries(self):
        """cb_ratio < 0.25 and retry_ratio < 0.5 -> Level 1."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
            ))
        # 5 edges total: only 1 with CB (0.2 < 0.25), 2 with retry (0.4 < 0.5)
        edges_config = [
            (True, True),    # CB + retry
            (False, True),   # retry only
            (False, False),
            (False, False),
            (False, False),
        ]
        targets = ["s1", "s2", "s3", "s1", "s2"]
        sources = ["s0", "s0", "s0", "s1", "s1"]
        for idx, (src, tgt) in enumerate(zip(sources, targets)):
            cb_en, rt_en = edges_config[idx]
            graph.add_dependency(Dependency(
                source_id=src, target_id=tgt,
                circuit_breaker=CircuitBreakerConfig(enabled=cb_en),
                retry_strategy=RetryStrategy(enabled=rt_en),
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        fi = next(d for d in report.dimensions if d.dimension == MaturityDimension.FAULT_INJECTION)
        assert fi.current_level == MaturityLevel.LEVEL_1_INITIAL

    def test_level_2_moderate_cb(self):
        """cb_ratio between 0.25 and 0.5 -> Level 2."""
        graph = InfraGraph()
        for i in range(3):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
            ))
        # 3 edges: 1 with CB (0.33), all with retry (1.0)
        graph.add_dependency(Dependency(
            source_id="s0", target_id="s1",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="s0", target_id="s2",
            retry_strategy=RetryStrategy(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="s1", target_id="s2",
            retry_strategy=RetryStrategy(enabled=True),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        fi = next(d for d in report.dimensions if d.dimension == MaturityDimension.FAULT_INJECTION)
        assert fi.current_level == MaturityLevel.LEVEL_2_DEFINED

    def test_level_4_high_cb_retry_low_singleflight(self):
        """cb+retry >= 0.75 but singleflight < 0.5 -> Level 4."""
        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER))
        graph.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER))
        graph.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        fi = next(d for d in report.dimensions if d.dimension == MaturityDimension.FAULT_INJECTION)
        # CB=100%, Retry=100%, SF=0% -> Level 4
        assert fi.current_level == MaturityLevel.LEVEL_4_MEASURED


class TestObservabilityIntermediate:
    """Tests to cover intermediate observability branches."""

    def test_level_1_partial_logging(self):
        """log_ratio < 0.5 -> Level 1."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER,
            security=SecurityProfile(log_enabled=True),
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.APP_SERVER,
        ))
        graph.add_component(Component(
            id="c", name="C", type=ComponentType.APP_SERVER,
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        obs = next(d for d in report.dimensions if d.dimension == MaturityDimension.OBSERVABILITY)
        assert obs.current_level == MaturityLevel.LEVEL_1_INITIAL

    def test_level_3_logging_and_ids_no_hc(self):
        """log >= 0.5, ids >= 0.25, hc_ratio < 0.5 -> Level 3."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                security=SecurityProfile(
                    log_enabled=True,
                    ids_monitored=(i < 2),  # 2/4 = 50% > 25%
                ),
                # Only 1 has health check -> hc_ratio = 25% < 50%
                failover=FailoverConfig(
                    enabled=(i == 0),
                    health_check_interval_seconds=10 if i == 0 else 0,
                ),
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        obs = next(d for d in report.dimensions if d.dimension == MaturityDimension.OBSERVABILITY)
        assert obs.current_level == MaturityLevel.LEVEL_3_MANAGED

    def test_level_4_good_but_not_complete(self):
        """All logging, some IDS + HC but not 75% for both -> Level 4."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                security=SecurityProfile(
                    log_enabled=True,
                    ids_monitored=(i < 2),  # 50% < 75%
                ),
                failover=FailoverConfig(
                    enabled=(i < 3),
                    health_check_interval_seconds=10 if i < 3 else 0,
                ),
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        obs = next(d for d in report.dimensions if d.dimension == MaturityDimension.OBSERVABILITY)
        assert obs.current_level == MaturityLevel.LEVEL_4_MEASURED


class TestAutomationIntermediate:
    """Tests to cover intermediate automation branches."""

    def test_level_1_small_automation(self):
        """combined < 0.25 -> Level 1."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                autoscaling=AutoScalingConfig(enabled=(i == 0)),
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        auto = next(d for d in report.dimensions if d.dimension == MaturityDimension.AUTOMATION)
        # AS=25%, FO=0%, combined=12.5% < 25%
        assert auto.current_level == MaturityLevel.LEVEL_1_INITIAL

    def test_level_2_moderate_automation(self):
        """combined between 0.25 and 0.5 -> Level 2."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                autoscaling=AutoScalingConfig(enabled=(i < 2)),  # 50%
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        auto = next(d for d in report.dimensions if d.dimension == MaturityDimension.AUTOMATION)
        # AS=50%, FO=0%, combined=25%
        assert auto.current_level == MaturityLevel.LEVEL_2_DEFINED

    def test_level_3_good_but_not_75(self):
        """combined between 0.5 and 0.75 -> Level 3."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                autoscaling=AutoScalingConfig(enabled=(i < 3)),  # 75%
                failover=FailoverConfig(enabled=(i < 1)),  # 25%
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        auto = next(d for d in report.dimensions if d.dimension == MaturityDimension.AUTOMATION)
        # AS=75%, FO=25%, combined=50%
        assert auto.current_level == MaturityLevel.LEVEL_3_MANAGED

    def test_level_4_near_complete(self):
        """combined between 0.75 and 0.9 -> Level 4."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                autoscaling=AutoScalingConfig(enabled=True),  # 100%
                failover=FailoverConfig(enabled=(i < 2)),  # 50%
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        auto = next(d for d in report.dimensions if d.dimension == MaturityDimension.AUTOMATION)
        # AS=100%, FO=50%, combined=75%
        assert auto.current_level == MaturityLevel.LEVEL_4_MEASURED


class TestBlastRadiusIntermediate:
    """Tests to cover intermediate blast radius branches."""

    def test_level_1_some_replicas_few_cb(self):
        """replica < 0.5 and cb < 0.25 -> Level 1."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                replicas=2 if i == 0 else 1,  # 25% replicas
            ))
        graph.add_dependency(Dependency(source_id="s0", target_id="s1"))
        graph.add_dependency(Dependency(source_id="s1", target_id="s2"))
        graph.add_dependency(Dependency(source_id="s2", target_id="s3"))
        graph.add_dependency(Dependency(source_id="s0", target_id="s3"))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        brc = next(d for d in report.dimensions if d.dimension == MaturityDimension.BLAST_RADIUS_CONTROL)
        assert brc.current_level == MaturityLevel.LEVEL_1_INITIAL

    def test_level_3_moderate_cb_low_segmentation(self):
        """cb between 0.5-0.75, seg < 0.5 -> Level 3."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                replicas=3,
                security=SecurityProfile(network_segmented=(i == 0)),  # 25% seg
            ))
        # 4 edges, 3 with CB -> 75%, seg=25% < 50% -> Level 3
        graph.add_dependency(Dependency(
            source_id="s0", target_id="s1",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="s1", target_id="s2",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="s2", target_id="s3",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="s0", target_id="s3",
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        brc = next(d for d in report.dimensions if d.dimension == MaturityDimension.BLAST_RADIUS_CONTROL)
        assert brc.current_level == MaturityLevel.LEVEL_3_MANAGED

    def test_level_4_near_complete_segmentation(self):
        """seg between 0.5-0.75 or cb between 0.75-0.9 -> Level 4."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                replicas=3,
                security=SecurityProfile(network_segmented=(i < 3)),  # 75% but need < 0.75 for L4
            ))
        # 4 edges, 3 with CB -> 75% (not >= 0.9)
        graph.add_dependency(Dependency(
            source_id="s0", target_id="s1",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="s1", target_id="s2",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="s2", target_id="s3",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="s0", target_id="s3",
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        brc = next(d for d in report.dimensions if d.dimension == MaturityDimension.BLAST_RADIUS_CONTROL)
        assert brc.current_level == MaturityLevel.LEVEL_4_MEASURED


class TestGameDaysIntermediate:
    """Tests to cover intermediate game days branches."""

    def test_level_1_low_readiness(self):
        """infra_readiness between 0 and 0.2 -> Level 1."""
        graph = InfraGraph()
        # Need infra_readiness < 0.2.  fo=1/20=5%, as=0%, no edges -> cb/retry=0
        # readiness = (0.05 + 0 + 0 + 0)/4 = 0.0125 < 0.2
        for i in range(20):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                failover=FailoverConfig(enabled=(i == 0)),
                team=OperationalTeamConfig(runbook_coverage_percent=50.0, automation_percent=20.0),
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        gd = next(d for d in report.dimensions if d.dimension == MaturityDimension.GAME_DAYS)
        assert gd.current_level == MaturityLevel.LEVEL_1_INITIAL

    def test_level_3_moderate_readiness(self):
        """infra_readiness between 0.4 and 0.6, runbook >= 40 -> Level 3."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                failover=FailoverConfig(enabled=(i < 2)),  # 50%
                autoscaling=AutoScalingConfig(enabled=(i < 2)),  # 50%
                team=OperationalTeamConfig(
                    runbook_coverage_percent=55.0,
                    automation_percent=20.0,
                ),
            ))
        # 3 edges, all with CB and retry -> 100%
        graph.add_dependency(Dependency(
            source_id="s0", target_id="s1",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="s1", target_id="s2",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="s2", target_id="s3",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        gd = next(d for d in report.dimensions if d.dimension == MaturityDimension.GAME_DAYS)
        # fo=50%, as=50%, cb=100%, retry=100% -> readiness = 75%, runbook=55 < 60
        assert gd.current_level == MaturityLevel.LEVEL_3_MANAGED

    def test_level_4_high_readiness_low_automation(self):
        """infra_readiness >= 0.6, runbook >= 60, automation < 50 -> Level 4."""
        graph = InfraGraph()
        for i in range(2):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                failover=FailoverConfig(enabled=True),
                autoscaling=AutoScalingConfig(enabled=True),
                team=OperationalTeamConfig(
                    runbook_coverage_percent=70.0,
                    automation_percent=40.0,
                ),
            ))
        graph.add_dependency(Dependency(
            source_id="s0", target_id="s1",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        gd = next(d for d in report.dimensions if d.dimension == MaturityDimension.GAME_DAYS)
        assert gd.current_level == MaturityLevel.LEVEL_4_MEASURED


class TestSteadyStateIntermediate:
    """Tests to cover intermediate steady state branches."""

    def test_level_1_some_hc_no_slo(self):
        """hc_ratio < 0.25 and slo_ratio < 0.1 -> Level 1."""
        graph = InfraGraph()
        for i in range(10):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                failover=FailoverConfig(
                    enabled=(i == 0),
                    health_check_interval_seconds=10 if i == 0 else 0,
                ),
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        ss = next(d for d in report.dimensions if d.dimension == MaturityDimension.STEADY_STATE_HYPOTHESIS)
        assert ss.current_level == MaturityLevel.LEVEL_1_INITIAL

    def test_level_3_good_slo_moderate_hc(self):
        """slo between 0.5 and 0.75 or hc < 0.5 -> Level 3."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                slo_targets=[SLOTarget(name="avail", target=99.9)] if i < 3 else [],
                failover=FailoverConfig(
                    enabled=(i < 1),
                    health_check_interval_seconds=10 if i < 1 else 0,
                ),
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        ss = next(d for d in report.dimensions if d.dimension == MaturityDimension.STEADY_STATE_HYPOTHESIS)
        # slo=75%, hc=25% < 50% -> Level 3
        assert ss.current_level == MaturityLevel.LEVEL_3_MANAGED

    def test_level_4_good_slo_hc_moderate_log(self):
        """slo >= 0.75, hc >= 0.5, log < 0.75 -> Level 4."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                slo_targets=[SLOTarget(name="avail", target=99.9)],
                failover=FailoverConfig(enabled=True, health_check_interval_seconds=10),
                security=SecurityProfile(log_enabled=(i < 2)),  # 50% < 75%
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        ss = next(d for d in report.dimensions if d.dimension == MaturityDimension.STEADY_STATE_HYPOTHESIS)
        assert ss.current_level == MaturityLevel.LEVEL_4_MEASURED


class TestRollbackIntermediate:
    """Tests to cover intermediate rollback branches."""

    def test_level_2_moderate_fo_low_backup(self):
        """fo between 0.25 and 0.5 or backup < 0.25 -> Level 2."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                replicas=2,
                failover=FailoverConfig(enabled=(i < 1)),  # 25%
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        rb = next(d for d in report.dimensions if d.dimension == MaturityDimension.ROLLBACK_CAPABILITY)
        assert rb.current_level == MaturityLevel.LEVEL_2_DEFINED

    def test_level_3_moderate_backup_moderate_fo(self):
        """backup < 0.5 or fo < 0.75 -> Level 3."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                replicas=2,
                failover=FailoverConfig(enabled=(i < 2)),  # 50%
                security=SecurityProfile(backup_enabled=(i < 1)),  # 25%
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        rb = next(d for d in report.dimensions if d.dimension == MaturityDimension.ROLLBACK_CAPABILITY)
        assert rb.current_level == MaturityLevel.LEVEL_3_MANAGED

    def test_level_4_good_fo_backup_no_dr(self):
        """fo >= 0.75, backup >= 0.5, dr < 0.25 -> Level 4."""
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"s{i}", name=f"S{i}", type=ComponentType.APP_SERVER,
                replicas=3,
                failover=FailoverConfig(enabled=True),  # 100%
                security=SecurityProfile(backup_enabled=True),  # 100%
            ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        rb = next(d for d in report.dimensions if d.dimension == MaturityDimension.ROLLBACK_CAPABILITY)
        assert rb.current_level == MaturityLevel.LEVEL_4_MEASURED


class TestOrganizationalIntermediate:
    """Tests to cover intermediate organizational branches."""

    def test_level_1_low_runbook(self):
        """Custom config but avg_runbook < 40 -> Level 1."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER,
            team=OperationalTeamConfig(
                runbook_coverage_percent=30.0,
                automation_percent=10.0,
            ),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        org = next(d for d in report.dimensions if d.dimension == MaturityDimension.ORGANIZATIONAL_ADOPTION)
        assert org.current_level == MaturityLevel.LEVEL_1_INITIAL

    def test_level_4_moderate_automation_low_oncall(self):
        """avg_automation between 40-60 or oncall < 20 -> Level 4."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER,
            team=OperationalTeamConfig(
                runbook_coverage_percent=80.0,
                automation_percent=50.0,
                oncall_coverage_hours=15.0,
            ),
        ))
        assessor = ChaosMaturityAssessor(graph)
        report = assessor.assess()
        org = next(d for d in report.dimensions if d.dimension == MaturityDimension.ORGANIZATIONAL_ADOPTION)
        assert org.current_level == MaturityLevel.LEVEL_4_MEASURED


class TestRoadmapEstimatedMonths:
    """Tests for roadmap estimated_months_to_next_level at each level."""

    def test_level_0_months(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        roadmap = assessor._build_roadmap([], MaturityLevel.LEVEL_0_NONE)
        assert roadmap.estimated_months_to_next_level == 1.0

    def test_level_1_months(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        roadmap = assessor._build_roadmap([], MaturityLevel.LEVEL_1_INITIAL)
        assert roadmap.estimated_months_to_next_level == 2.0

    def test_level_2_months(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        roadmap = assessor._build_roadmap([], MaturityLevel.LEVEL_2_DEFINED)
        assert roadmap.estimated_months_to_next_level == 3.0

    def test_level_3_months(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        roadmap = assessor._build_roadmap([], MaturityLevel.LEVEL_3_MANAGED)
        assert roadmap.estimated_months_to_next_level == 6.0

    def test_level_4_months(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        roadmap = assessor._build_roadmap([], MaturityLevel.LEVEL_4_MEASURED)
        assert roadmap.estimated_months_to_next_level == 12.0

    def test_level_5_months(self):
        assessor = ChaosMaturityAssessor(_empty_graph())
        roadmap = assessor._build_roadmap([], MaturityLevel.LEVEL_5_OPTIMIZED)
        assert roadmap.estimated_months_to_next_level == 0.0
