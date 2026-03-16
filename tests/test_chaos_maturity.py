"""Tests for chaos_maturity module — Chaos Engineering Maturity Model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from faultray.model.components import (
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
from faultray.model.graph import InfraGraph
from faultray.simulator.chaos_maturity import (
    ChaosConfig,
    ChaosMaturityEngine,
    DimensionScore,
    ExecutiveSummary,
    IndustryComparison,
    MaturityAssessment,
    MaturityDimension,
    MaturityLevel,
    ProgressReport,
    ROIEstimate,
    RoadmapItem,
    _INDUSTRY_AVERAGES,
    _LEVEL_THRESHOLDS,
    _score_to_level,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str = "",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    autoscaling: AutoScalingConfig | None = None,
    failover: FailoverConfig | None = None,
    security: SecurityProfile | None = None,
    slo_targets: list[SLOTarget] | None = None,
    singleflight: SingleflightConfig | None = None,
    region: RegionConfig | None = None,
    team: OperationalTeamConfig | None = None,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        autoscaling=autoscaling or AutoScalingConfig(),
        failover=failover or FailoverConfig(),
        security=security or SecurityProfile(),
        slo_targets=slo_targets or [],
        singleflight=singleflight or SingleflightConfig(),
        region=region or RegionConfig(),
        team=team or OperationalTeamConfig(),
    )


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _default_config(**overrides) -> ChaosConfig:
    return ChaosConfig(**overrides)


def _full_config() -> ChaosConfig:
    return ChaosConfig(
        has_gameday_practice=True,
        gameday_frequency_per_quarter=4,
        has_hypothesis_driven_experiments=True,
        has_automated_chaos=True,
        chaos_in_ci_cd=True,
        blast_radius_controls=True,
        observability_coverage_percent=90.0,
        runbook_coverage_percent=90.0,
        incident_learning_process=True,
        team_training_hours_per_quarter=20.0,
    )


def _well_protected_comp(cid: str) -> Component:
    return _comp(
        cid,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
        security=SecurityProfile(
            log_enabled=True, ids_monitored=True, network_segmented=True, backup_enabled=True,
        ),
        slo_targets=[SLOTarget(name="availability", target=99.99)],
        singleflight=SingleflightConfig(enabled=True),
        region=RegionConfig(region="us-east-1", dr_target_region="us-west-2"),
        team=OperationalTeamConfig(
            runbook_coverage_percent=90.0, automation_percent=70.0, oncall_coverage_hours=24.0,
        ),
    )


def _bare_comp(cid: str) -> Component:
    return _comp(cid, replicas=1)


# ---------------------------------------------------------------------------
# MaturityLevel enum
# ---------------------------------------------------------------------------


class TestMaturityLevel:
    def test_has_five_members(self):
        assert len(MaturityLevel) == 5

    def test_values(self):
        expected = {
            "level_0_initial",
            "level_1_planned",
            "level_2_practiced",
            "level_3_managed",
            "level_4_optimized",
        }
        assert {m.value for m in MaturityLevel} == expected

    def test_is_str_enum(self):
        assert isinstance(MaturityLevel.level_0_initial, str)

    def test_ordering_preserved(self):
        levels = list(MaturityLevel)
        assert levels[0] == MaturityLevel.level_0_initial
        assert levels[4] == MaturityLevel.level_4_optimized


# ---------------------------------------------------------------------------
# MaturityDimension enum
# ---------------------------------------------------------------------------


class TestMaturityDimension:
    def test_has_eight_members(self):
        assert len(MaturityDimension) == 8

    def test_values(self):
        expected = {
            "culture", "process", "tooling", "automation",
            "observability", "blast_radius_control",
            "hypothesis_driven", "gameday_practice",
        }
        assert {d.value for d in MaturityDimension} == expected

    def test_is_str_enum(self):
        assert isinstance(MaturityDimension.culture, str)


# ---------------------------------------------------------------------------
# _score_to_level helper
# ---------------------------------------------------------------------------


class TestScoreToLevel:
    def test_zero(self):
        assert _score_to_level(0.0) == MaturityLevel.level_0_initial

    def test_below_20(self):
        assert _score_to_level(19.9) == MaturityLevel.level_0_initial

    def test_at_20(self):
        assert _score_to_level(20.0) == MaturityLevel.level_1_planned

    def test_at_40(self):
        assert _score_to_level(40.0) == MaturityLevel.level_2_practiced

    def test_at_60(self):
        assert _score_to_level(60.0) == MaturityLevel.level_3_managed

    def test_at_80(self):
        assert _score_to_level(80.0) == MaturityLevel.level_4_optimized

    def test_at_100(self):
        assert _score_to_level(100.0) == MaturityLevel.level_4_optimized

    def test_midrange(self):
        assert _score_to_level(50.0) == MaturityLevel.level_2_practiced


# ---------------------------------------------------------------------------
# ChaosConfig model
# ---------------------------------------------------------------------------


class TestChaosConfig:
    def test_defaults(self):
        cfg = ChaosConfig()
        assert cfg.has_gameday_practice is False
        assert cfg.gameday_frequency_per_quarter == 0
        assert cfg.has_hypothesis_driven_experiments is False
        assert cfg.has_automated_chaos is False
        assert cfg.chaos_in_ci_cd is False
        assert cfg.blast_radius_controls is False
        assert cfg.observability_coverage_percent == 0.0
        assert cfg.runbook_coverage_percent == 0.0
        assert cfg.incident_learning_process is False
        assert cfg.team_training_hours_per_quarter == 0.0

    def test_full_config(self):
        cfg = _full_config()
        assert cfg.has_gameday_practice is True
        assert cfg.gameday_frequency_per_quarter == 4
        assert cfg.has_automated_chaos is True

    def test_partial_override(self):
        cfg = _default_config(has_gameday_practice=True, observability_coverage_percent=80.0)
        assert cfg.has_gameday_practice is True
        assert cfg.observability_coverage_percent == 80.0
        assert cfg.has_automated_chaos is False


# ---------------------------------------------------------------------------
# DimensionScore model
# ---------------------------------------------------------------------------


class TestDimensionScore:
    def test_defaults(self):
        ds = DimensionScore(dimension=MaturityDimension.culture)
        assert ds.score == 0.0
        assert ds.level == MaturityLevel.level_0_initial
        assert ds.evidence == []
        assert ds.gaps == []
        assert ds.next_level_actions == []

    def test_with_values(self):
        ds = DimensionScore(
            dimension=MaturityDimension.tooling,
            score=75.0,
            level=MaturityLevel.level_3_managed,
            evidence=["e1"],
            gaps=["g1"],
            next_level_actions=["a1"],
        )
        assert ds.score == 75.0
        assert ds.evidence == ["e1"]


# ---------------------------------------------------------------------------
# RoadmapItem model
# ---------------------------------------------------------------------------


class TestRoadmapItem:
    def test_defaults(self):
        item = RoadmapItem()
        assert item.phase == 1
        assert item.effort == "medium"
        assert item.impact == "medium"
        assert item.prerequisites == []

    def test_with_values(self):
        item = RoadmapItem(
            phase=3, title="Deploy Litmus", description="Set up chaos tooling",
            dimension=MaturityDimension.tooling, effort="high", impact="high",
            prerequisites=["Complete phase 2"],
        )
        assert item.phase == 3
        assert item.prerequisites == ["Complete phase 2"]


# ---------------------------------------------------------------------------
# MaturityAssessment model
# ---------------------------------------------------------------------------


class TestMaturityAssessment:
    def test_defaults(self):
        a = MaturityAssessment()
        assert a.overall_level == MaturityLevel.level_0_initial
        assert a.overall_score == 0.0
        assert a.dimensions == []
        assert a.roadmap == []
        assert a.industry_percentile == 0.0
        assert a.estimated_improvement_months == 0

    def test_strengths_and_weaknesses(self):
        a = MaturityAssessment(strengths=["a"], weaknesses=["b"])
        assert a.strengths == ["a"]
        assert a.weaknesses == ["b"]


# ---------------------------------------------------------------------------
# IndustryComparison model
# ---------------------------------------------------------------------------


class TestIndustryComparison:
    def test_defaults(self):
        ic = IndustryComparison()
        assert ic.industry == ""
        assert ic.industry_average == 50.0
        assert ic.percentile == 0.0

    def test_with_values(self):
        ic = IndustryComparison(industry="finance", your_score=70.0, percentile=65.0)
        assert ic.industry == "finance"


# ---------------------------------------------------------------------------
# ROIEstimate model
# ---------------------------------------------------------------------------


class TestROIEstimate:
    def test_defaults(self):
        roi = ROIEstimate()
        assert roi.estimated_months == 0
        assert roi.incident_reduction_percent == 0.0

    def test_with_values(self):
        roi = ROIEstimate(
            current_level=MaturityLevel.level_1_planned,
            target_level=MaturityLevel.level_3_managed,
            estimated_months=6,
        )
        assert roi.estimated_months == 6


# ---------------------------------------------------------------------------
# ExecutiveSummary model
# ---------------------------------------------------------------------------


class TestExecutiveSummary:
    def test_defaults(self):
        es = ExecutiveSummary()
        assert es.headline == ""
        assert es.key_findings == []
        assert es.top_risks == []

    def test_with_values(self):
        es = ExecutiveSummary(headline="Test headline", top_risks=["r1"])
        assert es.headline == "Test headline"


# ---------------------------------------------------------------------------
# ProgressReport model
# ---------------------------------------------------------------------------


class TestProgressReport:
    def test_defaults(self):
        pr = ProgressReport()
        assert pr.score_delta == 0.0
        assert pr.level_changed is False
        assert isinstance(pr.assessed_at, datetime)

    def test_assessed_at_is_utc(self):
        pr = ProgressReport()
        assert pr.assessed_at.tzinfo is not None


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — score_dimension (culture)
# ---------------------------------------------------------------------------


class TestScoreCulture:
    def test_empty_graph_zero_config(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.culture, ChaosConfig())
        assert ds.score < 20
        assert ds.level == MaturityLevel.level_0_initial

    def test_incident_learning_adds_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.culture,
            _default_config(incident_learning_process=True),
        )
        assert ds.score >= 25.0

    def test_training_hours_contribute(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.culture,
            _default_config(team_training_hours_per_quarter=20.0),
        )
        assert ds.score >= 25.0

    def test_gameday_practice_adds_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.culture,
            _default_config(has_gameday_practice=True),
        )
        assert ds.score >= 15.0

    def test_high_runbook_with_components(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a", team=OperationalTeamConfig(runbook_coverage_percent=90.0)))
        ds = engine.score_dimension(g, MaturityDimension.culture, ChaosConfig())
        assert ds.score > 0

    def test_full_config_high_score(self):
        engine = ChaosMaturityEngine()
        g = _graph(_well_protected_comp("a"))
        ds = engine.score_dimension(g, MaturityDimension.culture, _full_config())
        assert ds.score >= 80.0
        assert ds.level in (MaturityLevel.level_3_managed, MaturityLevel.level_4_optimized)

    def test_evidence_populated(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.culture,
            _default_config(incident_learning_process=True),
        )
        assert any("Incident" in e for e in ds.evidence)

    def test_gaps_populated_on_low_config(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.culture, ChaosConfig())
        assert len(ds.gaps) > 0

    def test_actions_populated_on_low_config(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.culture, ChaosConfig())
        assert len(ds.next_level_actions) > 0


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — score_dimension (process)
# ---------------------------------------------------------------------------


class TestScoreProcess:
    def test_empty_gives_zero(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.process, ChaosConfig())
        assert ds.score < 20

    def test_hypothesis_driven_adds_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.process,
            _default_config(has_hypothesis_driven_experiments=True),
        )
        assert ds.score >= 30.0

    def test_incident_learning_adds_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.process,
            _default_config(incident_learning_process=True),
        )
        assert ds.score >= 20.0

    def test_gameday_frequency_contributes(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.process,
            _default_config(gameday_frequency_per_quarter=4),
        )
        assert ds.score >= 25.0

    def test_runbook_coverage_contributes(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.process,
            _default_config(runbook_coverage_percent=100.0),
        )
        assert ds.score >= 25.0

    def test_full_config_high_score(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.process, _full_config())
        assert ds.score >= 80.0

    def test_gaps_on_low_config(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.process, ChaosConfig())
        assert len(ds.gaps) > 0


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — score_dimension (tooling)
# ---------------------------------------------------------------------------


class TestScoreTooling:
    def test_empty_graph_zero_config(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.tooling, ChaosConfig())
        assert ds.score < 20

    def test_automated_chaos_adds_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.tooling,
            _default_config(has_automated_chaos=True),
        )
        assert ds.score >= 25.0

    def test_chaos_in_ci_cd_adds_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.tooling,
            _default_config(chaos_in_ci_cd=True),
        )
        assert ds.score >= 25.0

    def test_blast_radius_controls_add_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.tooling,
            _default_config(blast_radius_controls=True),
        )
        assert ds.score >= 15.0

    def test_edges_with_cb_and_retry(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
        ds = engine.score_dimension(g, MaturityDimension.tooling, ChaosConfig())
        assert ds.score > 0

    def test_full_config_full_graph(self):
        engine = ChaosMaturityEngine()
        g = _graph(_well_protected_comp("a"), _well_protected_comp("b"))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
        ds = engine.score_dimension(g, MaturityDimension.tooling, _full_config())
        assert ds.score >= 80.0

    def test_no_edges_reports_gap(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.tooling, ChaosConfig())
        assert any("edge" in g.lower() or "dependency" in g.lower() for g in ds.gaps)


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — score_dimension (automation)
# ---------------------------------------------------------------------------


class TestScoreAutomation:
    def test_empty_graph_zero_config(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.automation, ChaosConfig())
        assert ds.score < 20

    def test_automated_chaos_adds_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.automation,
            _default_config(has_automated_chaos=True),
        )
        assert ds.score >= 20.0

    def test_chaos_in_ci_cd_adds_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.automation,
            _default_config(chaos_in_ci_cd=True),
        )
        assert ds.score >= 20.0

    def test_autoscaling_failover_contribute(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a", autoscaling=AutoScalingConfig(enabled=True),
                         failover=FailoverConfig(enabled=True)))
        ds = engine.score_dimension(g, MaturityDimension.automation, ChaosConfig())
        assert ds.score > 0

    def test_team_automation_percent(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a", team=OperationalTeamConfig(automation_percent=80.0)))
        ds = engine.score_dimension(g, MaturityDimension.automation, ChaosConfig())
        assert ds.score > 0

    def test_full_config_high_score(self):
        engine = ChaosMaturityEngine()
        g = _graph(_well_protected_comp("a"))
        ds = engine.score_dimension(g, MaturityDimension.automation, _full_config())
        assert ds.score >= 70.0

    def test_no_components_reports_gap(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.automation, ChaosConfig())
        assert any("component" in g.lower() for g in ds.gaps)


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — score_dimension (observability)
# ---------------------------------------------------------------------------


class TestScoreObservability:
    def test_empty_graph_zero_config(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.observability, ChaosConfig())
        assert ds.score < 20

    def test_observability_coverage_adds_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.observability,
            _default_config(observability_coverage_percent=80.0),
        )
        assert ds.score >= 30.0

    def test_logging_contributes(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a", security=SecurityProfile(log_enabled=True)))
        ds = engine.score_dimension(g, MaturityDimension.observability, ChaosConfig())
        assert ds.score > 0

    def test_ids_contributes(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a", security=SecurityProfile(ids_monitored=True)))
        ds = engine.score_dimension(g, MaturityDimension.observability, ChaosConfig())
        assert ds.score > 0

    def test_health_checks_contribute(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a", failover=FailoverConfig(enabled=True, health_check_interval_seconds=5)))
        ds = engine.score_dimension(g, MaturityDimension.observability, ChaosConfig())
        assert ds.score > 0

    def test_full_config_full_graph(self):
        engine = ChaosMaturityEngine()
        g = _graph(_well_protected_comp("a"))
        ds = engine.score_dimension(g, MaturityDimension.observability, _full_config())
        assert ds.score >= 80.0

    def test_no_components_reports_gap(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.observability, ChaosConfig())
        assert any("component" in g.lower() for g in ds.gaps)

    def test_high_coverage_evidence(self):
        engine = ChaosMaturityEngine()
        g = _graph(_well_protected_comp("a"))
        ds = engine.score_dimension(
            g, MaturityDimension.observability,
            _default_config(observability_coverage_percent=80.0),
        )
        assert len(ds.evidence) > 0


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — score_dimension (blast_radius_control)
# ---------------------------------------------------------------------------


class TestScoreBlastRadius:
    def test_empty_graph_zero_config(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.blast_radius_control, ChaosConfig(),
        )
        assert ds.score < 20

    def test_blast_radius_controls_add_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.blast_radius_control,
            _default_config(blast_radius_controls=True),
        )
        assert ds.score >= 25.0

    def test_replicas_contribute(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a", replicas=3))
        ds = engine.score_dimension(g, MaturityDimension.blast_radius_control, ChaosConfig())
        assert ds.score > 0

    def test_network_segmentation_contributes(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a", security=SecurityProfile(network_segmented=True)))
        ds = engine.score_dimension(g, MaturityDimension.blast_radius_control, ChaosConfig())
        assert ds.score > 0

    def test_circuit_breakers_on_edges(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        ds = engine.score_dimension(g, MaturityDimension.blast_radius_control, ChaosConfig())
        assert ds.score > 0

    def test_full_config_full_graph(self):
        engine = ChaosMaturityEngine()
        g = _graph(_well_protected_comp("a"), _well_protected_comp("b"))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        ds = engine.score_dimension(g, MaturityDimension.blast_radius_control, _full_config())
        assert ds.score >= 80.0

    def test_no_edges_adds_gap(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a"))
        ds = engine.score_dimension(g, MaturityDimension.blast_radius_control, ChaosConfig())
        assert any("edge" in g_text.lower() or "dependency" in g_text.lower() for g_text in ds.gaps)


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — score_dimension (hypothesis_driven)
# ---------------------------------------------------------------------------


class TestScoreHypothesis:
    def test_empty_gives_zero(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.hypothesis_driven, ChaosConfig())
        assert ds.score < 20

    def test_hypothesis_driven_adds_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.hypothesis_driven,
            _default_config(has_hypothesis_driven_experiments=True),
        )
        assert ds.score >= 35.0

    def test_incident_learning_adds_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.hypothesis_driven,
            _default_config(incident_learning_process=True),
        )
        assert ds.score >= 15.0

    def test_observability_contributes(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.hypothesis_driven,
            _default_config(observability_coverage_percent=80.0),
        )
        assert ds.score > 0

    def test_slo_targets_contribute(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a", slo_targets=[SLOTarget(name="avail", target=99.9)]))
        ds = engine.score_dimension(g, MaturityDimension.hypothesis_driven, ChaosConfig())
        assert ds.score > 0

    def test_full_config_full_graph(self):
        engine = ChaosMaturityEngine()
        g = _graph(_well_protected_comp("a"))
        ds = engine.score_dimension(g, MaturityDimension.hypothesis_driven, _full_config())
        assert ds.score >= 80.0

    def test_no_slo_reports_gap(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a"))
        ds = engine.score_dimension(g, MaturityDimension.hypothesis_driven, ChaosConfig())
        assert any("slo" in g_text.lower() for g_text in ds.gaps)


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — score_dimension (gameday_practice)
# ---------------------------------------------------------------------------


class TestScoreGameday:
    def test_empty_gives_zero(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.gameday_practice, ChaosConfig())
        assert ds.score < 20

    def test_gameday_practice_adds_points(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.gameday_practice,
            _default_config(has_gameday_practice=True),
        )
        assert ds.score >= 25.0

    def test_gameday_frequency_contributes(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.gameday_practice,
            _default_config(gameday_frequency_per_quarter=4),
        )
        assert ds.score >= 25.0

    def test_training_hours_contribute(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.gameday_practice,
            _default_config(team_training_hours_per_quarter=20.0),
        )
        assert ds.score >= 15.0

    def test_runbook_coverage_contributes(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(
            InfraGraph(), MaturityDimension.gameday_practice,
            _default_config(runbook_coverage_percent=100.0),
        )
        assert ds.score >= 15.0

    def test_infrastructure_readiness(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a", autoscaling=AutoScalingConfig(enabled=True),
                         failover=FailoverConfig(enabled=True)))
        ds = engine.score_dimension(g, MaturityDimension.gameday_practice, ChaosConfig())
        assert ds.score > 0

    def test_full_config_full_graph(self):
        engine = ChaosMaturityEngine()
        g = _graph(_well_protected_comp("a"))
        ds = engine.score_dimension(g, MaturityDimension.gameday_practice, _full_config())
        assert ds.score >= 80.0

    def test_no_components_reports_gap(self):
        engine = ChaosMaturityEngine()
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.gameday_practice, ChaosConfig())
        assert any("component" in g_text.lower() for g_text in ds.gaps)


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — assess_maturity
# ---------------------------------------------------------------------------


class TestAssessMaturity:
    def test_empty_graph_zero_config_initial_level(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        assert result.overall_level == MaturityLevel.level_0_initial
        assert result.overall_score < 20

    def test_returns_eight_dimensions(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        assert len(result.dimensions) == 8

    def test_all_dimensions_present(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        dims = {d.dimension for d in result.dimensions}
        assert dims == set(MaturityDimension)

    def test_full_config_full_graph_high_level(self):
        engine = ChaosMaturityEngine()
        g = _graph(_well_protected_comp("a"), _well_protected_comp("b"))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
        result = engine.assess_maturity(g, _full_config())
        assert result.overall_level in (MaturityLevel.level_3_managed, MaturityLevel.level_4_optimized)
        assert result.overall_score >= 60

    def test_strengths_populated_for_high_scores(self):
        engine = ChaosMaturityEngine()
        g = _graph(_well_protected_comp("a"))
        result = engine.assess_maturity(g, _full_config())
        assert len(result.strengths) > 0

    def test_weaknesses_populated_for_low_scores(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        assert len(result.weaknesses) > 0

    def test_roadmap_generated(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        assert len(result.roadmap) > 0

    def test_industry_percentile_set(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        assert result.industry_percentile >= 1.0

    def test_estimated_months_set(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        assert result.estimated_improvement_months > 0

    def test_overall_score_rounded(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        assert result.overall_score == round(result.overall_score, 1)

    def test_score_between_0_and_100(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        assert 0 <= result.overall_score <= 100

    def test_dimension_scores_between_0_and_100(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        for ds in result.dimensions:
            assert 0 <= ds.score <= 100


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — generate_roadmap
# ---------------------------------------------------------------------------


class TestGenerateRoadmap:
    def test_empty_assessment_returns_empty(self):
        engine = ChaosMaturityEngine()
        result = engine.generate_roadmap(MaturityAssessment())
        assert result == []

    def test_skips_optimized_dimensions(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            dimensions=[
                DimensionScore(
                    dimension=MaturityDimension.culture,
                    score=90.0,
                    level=MaturityLevel.level_4_optimized,
                    next_level_actions=["Should be skipped"],
                ),
            ],
        )
        result = engine.generate_roadmap(assessment)
        assert len(result) == 0

    def test_includes_actions_from_low_dimensions(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            dimensions=[
                DimensionScore(
                    dimension=MaturityDimension.culture,
                    score=10.0,
                    level=MaturityLevel.level_0_initial,
                    next_level_actions=["Train teams"],
                ),
            ],
        )
        result = engine.generate_roadmap(assessment)
        assert len(result) == 1
        assert result[0].title == "Train teams"

    def test_phases_are_sequential(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            dimensions=[
                DimensionScore(
                    dimension=MaturityDimension.culture,
                    score=10.0, level=MaturityLevel.level_0_initial,
                    next_level_actions=["A1", "A2"],
                ),
                DimensionScore(
                    dimension=MaturityDimension.process,
                    score=20.0, level=MaturityLevel.level_1_planned,
                    next_level_actions=["B1"],
                ),
            ],
        )
        result = engine.generate_roadmap(assessment)
        phases = [item.phase for item in result]
        assert phases == sorted(phases)
        assert phases[0] == 1

    def test_effort_is_low_for_low_score(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            dimensions=[
                DimensionScore(
                    dimension=MaturityDimension.culture,
                    score=10.0, level=MaturityLevel.level_0_initial,
                    next_level_actions=["A1"],
                ),
            ],
        )
        result = engine.generate_roadmap(assessment)
        assert result[0].effort == "low"
        assert result[0].impact == "high"

    def test_effort_is_medium_for_mid_score(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            dimensions=[
                DimensionScore(
                    dimension=MaturityDimension.culture,
                    score=45.0, level=MaturityLevel.level_2_practiced,
                    next_level_actions=["A1"],
                ),
            ],
        )
        result = engine.generate_roadmap(assessment)
        assert result[0].effort == "medium"
        assert result[0].impact == "medium"

    def test_effort_is_high_for_high_score(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            dimensions=[
                DimensionScore(
                    dimension=MaturityDimension.culture,
                    score=70.0, level=MaturityLevel.level_3_managed,
                    next_level_actions=["A1"],
                ),
            ],
        )
        result = engine.generate_roadmap(assessment)
        assert result[0].effort == "high"
        assert result[0].impact == "low"

    def test_prerequisites_reference_prior_phase(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            dimensions=[
                DimensionScore(
                    dimension=MaturityDimension.culture,
                    score=10.0, level=MaturityLevel.level_0_initial,
                    next_level_actions=["A1", "A2"],
                ),
            ],
        )
        result = engine.generate_roadmap(assessment)
        assert result[0].prerequisites == []
        assert "phase 1" in result[1].prerequisites[0].lower()

    def test_dimension_set_on_items(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            dimensions=[
                DimensionScore(
                    dimension=MaturityDimension.tooling,
                    score=10.0, level=MaturityLevel.level_0_initial,
                    next_level_actions=["Deploy tools"],
                ),
            ],
        )
        result = engine.generate_roadmap(assessment)
        assert result[0].dimension == MaturityDimension.tooling

    def test_sorted_by_score_ascending(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            dimensions=[
                DimensionScore(
                    dimension=MaturityDimension.culture,
                    score=50.0, level=MaturityLevel.level_2_practiced,
                    next_level_actions=["Culture action"],
                ),
                DimensionScore(
                    dimension=MaturityDimension.process,
                    score=10.0, level=MaturityLevel.level_0_initial,
                    next_level_actions=["Process action"],
                ),
            ],
        )
        result = engine.generate_roadmap(assessment)
        assert result[0].title == "Process action"


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — compare_to_industry
# ---------------------------------------------------------------------------


class TestCompareToIndustry:
    def test_finance_average(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_score=62.0, dimensions=[])
        ic = engine.compare_to_industry(assessment, "finance")
        assert ic.industry == "finance"
        assert ic.industry_average == 62.0

    def test_default_industry(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_score=50.0, dimensions=[])
        ic = engine.compare_to_industry(assessment, "unknown_industry")
        assert ic.industry_average == 50.0

    def test_percentile_calculation(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_score=50.0, dimensions=[])
        ic = engine.compare_to_industry(assessment, "default")
        assert 1.0 <= ic.percentile <= 99.0

    def test_above_below_dimensions(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            overall_score=50.0,
            dimensions=[
                DimensionScore(dimension=MaturityDimension.culture, score=80.0),
                DimensionScore(dimension=MaturityDimension.process, score=20.0),
            ],
        )
        ic = engine.compare_to_industry(assessment, "default")
        assert "culture" in ic.above_average_dimensions
        assert "process" in ic.below_average_dimensions

    def test_high_score_high_percentile(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_score=95.0, dimensions=[])
        ic = engine.compare_to_industry(assessment, "default")
        assert ic.percentile >= 90.0

    def test_low_score_low_percentile(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_score=5.0, dimensions=[])
        ic = engine.compare_to_industry(assessment, "default")
        assert ic.percentile <= 10.0

    def test_industry_averages_exist(self):
        assert "finance" in _INDUSTRY_AVERAGES
        assert "healthcare" in _INDUSTRY_AVERAGES
        assert "default" in _INDUSTRY_AVERAGES


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — estimate_roi
# ---------------------------------------------------------------------------


class TestEstimateROI:
    def test_same_level_zero_gap(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_level=MaturityLevel.level_2_practiced)
        roi = engine.estimate_roi(assessment, MaturityLevel.level_2_practiced)
        assert roi.estimated_months == 0
        assert roi.estimated_cost_hours == 0

    def test_one_level_gap(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_level=MaturityLevel.level_0_initial)
        roi = engine.estimate_roi(assessment, MaturityLevel.level_1_planned)
        assert roi.estimated_months == 3
        assert roi.estimated_cost_hours == 160

    def test_multiple_level_gap(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_level=MaturityLevel.level_0_initial)
        roi = engine.estimate_roi(assessment, MaturityLevel.level_4_optimized)
        assert roi.estimated_months == 12
        assert roi.estimated_cost_hours == 640

    def test_incident_reduction_capped(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_level=MaturityLevel.level_0_initial)
        roi = engine.estimate_roi(assessment, MaturityLevel.level_4_optimized)
        assert roi.incident_reduction_percent == 80.0

    def test_mttr_improvement_capped(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_level=MaturityLevel.level_0_initial)
        roi = engine.estimate_roi(assessment, MaturityLevel.level_4_optimized)
        assert roi.mttr_improvement_percent == 60.0

    def test_current_and_target_set(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_level=MaturityLevel.level_1_planned)
        roi = engine.estimate_roi(assessment, MaturityLevel.level_3_managed)
        assert roi.current_level == MaturityLevel.level_1_planned
        assert roi.target_level == MaturityLevel.level_3_managed

    def test_availability_gain(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_level=MaturityLevel.level_0_initial)
        roi = engine.estimate_roi(assessment, MaturityLevel.level_2_practiced)
        assert roi.availability_gain_nines > 0

    def test_target_below_current(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_level=MaturityLevel.level_3_managed)
        roi = engine.estimate_roi(assessment, MaturityLevel.level_0_initial)
        assert roi.estimated_months == 0
        assert roi.estimated_cost_hours == 0


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — generate_executive_summary
# ---------------------------------------------------------------------------


class TestExecutiveSummaryGeneration:
    def test_headline_contains_level(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            overall_level=MaturityLevel.level_2_practiced,
            overall_score=45.0,
        )
        es = engine.generate_executive_summary(assessment)
        assert "Practiced" in es.headline

    def test_headline_contains_score(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            overall_level=MaturityLevel.level_0_initial,
            overall_score=10.0,
        )
        es = engine.generate_executive_summary(assessment)
        assert "10.0" in es.headline

    def test_findings_include_strengths(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            overall_level=MaturityLevel.level_2_practiced,
            overall_score=50.0,
            strengths=["culture"],
        )
        es = engine.generate_executive_summary(assessment)
        assert any("culture" in f for f in es.key_findings)

    def test_findings_include_weaknesses(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            overall_level=MaturityLevel.level_0_initial,
            overall_score=10.0,
            weaknesses=["tooling"],
        )
        es = engine.generate_executive_summary(assessment)
        assert any("tooling" in f for f in es.key_findings)

    def test_risks_from_low_dimensions(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            overall_level=MaturityLevel.level_0_initial,
            overall_score=10.0,
            dimensions=[
                DimensionScore(dimension=MaturityDimension.culture, score=15.0),
            ],
        )
        es = engine.generate_executive_summary(assessment)
        assert len(es.top_risks) > 0

    def test_investments_from_roadmap(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            overall_level=MaturityLevel.level_0_initial,
            overall_score=10.0,
            roadmap=[
                RoadmapItem(title="Invest in training", effort="low"),
            ],
        )
        es = engine.generate_executive_summary(assessment)
        assert len(es.recommended_investments) > 0

    def test_months_from_assessment(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            overall_level=MaturityLevel.level_0_initial,
            overall_score=10.0,
            estimated_improvement_months=6,
        )
        es = engine.generate_executive_summary(assessment)
        assert es.estimated_improvement_months == 6

    def test_overall_fields_passed_through(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(
            overall_level=MaturityLevel.level_3_managed,
            overall_score=65.0,
        )
        es = engine.generate_executive_summary(assessment)
        assert es.overall_level == MaturityLevel.level_3_managed
        assert es.overall_score == 65.0

    def test_all_levels_have_labels(self):
        engine = ChaosMaturityEngine()
        for level in MaturityLevel:
            assessment = MaturityAssessment(overall_level=level, overall_score=50.0)
            es = engine.generate_executive_summary(assessment)
            assert es.headline != ""


# ---------------------------------------------------------------------------
# ChaosMaturityEngine — track_progress
# ---------------------------------------------------------------------------


class TestTrackProgress:
    def test_no_change(self):
        engine = ChaosMaturityEngine()
        a = MaturityAssessment(
            overall_level=MaturityLevel.level_1_planned,
            overall_score=25.0,
            dimensions=[
                DimensionScore(dimension=MaturityDimension.culture, score=25.0),
            ],
        )
        pr = engine.track_progress(a, a)
        assert pr.score_delta == 0.0
        assert pr.level_changed is False

    def test_improvement_detected(self):
        engine = ChaosMaturityEngine()
        prev = MaturityAssessment(
            overall_level=MaturityLevel.level_0_initial,
            overall_score=10.0,
            dimensions=[
                DimensionScore(dimension=MaturityDimension.culture, score=10.0),
            ],
        )
        curr = MaturityAssessment(
            overall_level=MaturityLevel.level_1_planned,
            overall_score=30.0,
            dimensions=[
                DimensionScore(dimension=MaturityDimension.culture, score=30.0),
            ],
        )
        pr = engine.track_progress(curr, prev)
        assert pr.score_delta == 20.0
        assert pr.level_changed is True
        assert "culture" in pr.improved_dimensions

    def test_regression_detected(self):
        engine = ChaosMaturityEngine()
        prev = MaturityAssessment(
            overall_level=MaturityLevel.level_2_practiced,
            overall_score=50.0,
            dimensions=[
                DimensionScore(dimension=MaturityDimension.process, score=50.0),
            ],
        )
        curr = MaturityAssessment(
            overall_level=MaturityLevel.level_1_planned,
            overall_score=30.0,
            dimensions=[
                DimensionScore(dimension=MaturityDimension.process, score=30.0),
            ],
        )
        pr = engine.track_progress(curr, prev)
        assert pr.score_delta == -20.0
        assert "process" in pr.regressed_dimensions

    def test_unchanged_dimensions(self):
        engine = ChaosMaturityEngine()
        a = MaturityAssessment(
            overall_level=MaturityLevel.level_1_planned,
            overall_score=25.0,
            dimensions=[
                DimensionScore(dimension=MaturityDimension.culture, score=25.0),
            ],
        )
        pr = engine.track_progress(a, a)
        assert "culture" in pr.unchanged_dimensions

    def test_assessed_at_is_datetime(self):
        engine = ChaosMaturityEngine()
        a = MaturityAssessment(overall_level=MaturityLevel.level_0_initial, overall_score=10.0)
        pr = engine.track_progress(a, a)
        assert isinstance(pr.assessed_at, datetime)

    def test_previous_and_current_levels(self):
        engine = ChaosMaturityEngine()
        prev = MaturityAssessment(overall_level=MaturityLevel.level_0_initial, overall_score=10.0)
        curr = MaturityAssessment(overall_level=MaturityLevel.level_2_practiced, overall_score=45.0)
        pr = engine.track_progress(curr, prev)
        assert pr.previous_level == MaturityLevel.level_0_initial
        assert pr.current_level == MaturityLevel.level_2_practiced


# ---------------------------------------------------------------------------
# Integration tests — full pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_assess_then_compare(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        ic = engine.compare_to_industry(result, "finance")
        assert ic.industry == "finance"
        assert ic.your_score == result.overall_score

    def test_assess_then_roi(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        roi = engine.estimate_roi(result, MaturityLevel.level_3_managed)
        assert roi.current_level == result.overall_level

    def test_assess_then_executive_summary(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        es = engine.generate_executive_summary(result)
        assert es.overall_level == result.overall_level

    def test_assess_then_track_progress(self):
        engine = ChaosMaturityEngine()
        prev = engine.assess_maturity(InfraGraph(), ChaosConfig())
        g = _graph(_well_protected_comp("a"))
        curr = engine.assess_maturity(g, _full_config())
        pr = engine.track_progress(curr, prev)
        assert pr.score_delta > 0
        assert len(pr.improved_dimensions) > 0

    def test_mixed_graph_mid_config(self):
        engine = ChaosMaturityEngine()
        g = _graph(
            _well_protected_comp("a"),
            _bare_comp("b"),
        )
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        cfg = _default_config(
            has_gameday_practice=True,
            has_hypothesis_driven_experiments=True,
            observability_coverage_percent=50.0,
            runbook_coverage_percent=50.0,
        )
        result = engine.assess_maturity(g, cfg)
        assert MaturityLevel.level_1_planned.value <= result.overall_level.value

    def test_multiple_components_varied(self):
        engine = ChaosMaturityEngine()
        g = _graph(
            _well_protected_comp("a"),
            _well_protected_comp("b"),
            _bare_comp("c"),
            _bare_comp("d"),
        )
        g.add_dependency(Dependency(
            source_id="a", target_id="c",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
        g.add_dependency(Dependency(
            source_id="b", target_id="d",
        ))
        result = engine.assess_maturity(g, _default_config(
            has_gameday_practice=True,
            observability_coverage_percent=40.0,
        ))
        assert 0 <= result.overall_score <= 100


# ---------------------------------------------------------------------------
# Edge cases & boundary tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_score_exactly_zero(self):
        ds = DimensionScore(dimension=MaturityDimension.culture, score=0.0)
        assert ds.level == MaturityLevel.level_0_initial

    def test_score_exactly_100(self):
        ds = DimensionScore(
            dimension=MaturityDimension.culture,
            score=100.0,
            level=MaturityLevel.level_4_optimized,
        )
        assert ds.score == 100.0

    def test_very_large_training_hours(self):
        engine = ChaosMaturityEngine()
        cfg = _default_config(team_training_hours_per_quarter=1000.0)
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.culture, cfg)
        assert ds.score <= 100.0

    def test_very_large_gameday_frequency(self):
        engine = ChaosMaturityEngine()
        cfg = _default_config(gameday_frequency_per_quarter=100)
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.gameday_practice, cfg)
        assert ds.score <= 100.0

    def test_observability_above_100_clamped(self):
        engine = ChaosMaturityEngine()
        cfg = _default_config(observability_coverage_percent=200.0)
        ds = engine.score_dimension(InfraGraph(), MaturityDimension.observability, cfg)
        assert ds.score <= 100.0

    def test_single_component_no_edges(self):
        engine = ChaosMaturityEngine()
        g = _graph(_comp("solo"))
        result = engine.assess_maturity(g, ChaosConfig())
        assert result.overall_score >= 0

    def test_many_components_all_bare(self):
        engine = ChaosMaturityEngine()
        comps = [_bare_comp(f"c{i}") for i in range(20)]
        g = _graph(*comps)
        result = engine.assess_maturity(g, ChaosConfig())
        assert result.overall_level == MaturityLevel.level_0_initial

    def test_many_components_all_protected(self):
        engine = ChaosMaturityEngine()
        comps = [_well_protected_comp(f"c{i}") for i in range(10)]
        g = _graph(*comps)
        for i in range(9):
            g.add_dependency(Dependency(
                source_id=f"c{i}", target_id=f"c{i+1}",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
                retry_strategy=RetryStrategy(enabled=True),
            ))
        result = engine.assess_maturity(g, _full_config())
        assert result.overall_score >= 70.0

    def test_engine_is_stateless(self):
        engine = ChaosMaturityEngine()
        r1 = engine.assess_maturity(InfraGraph(), ChaosConfig())
        r2 = engine.assess_maturity(InfraGraph(), ChaosConfig())
        assert r1.overall_score == r2.overall_score

    def test_percentile_at_least_1(self):
        engine = ChaosMaturityEngine()
        result = engine.assess_maturity(InfraGraph(), ChaosConfig())
        assert result.industry_percentile >= 1.0

    def test_percentile_at_most_99(self):
        engine = ChaosMaturityEngine()
        g = _graph(_well_protected_comp("a"))
        result = engine.assess_maturity(g, _full_config())
        assert result.industry_percentile <= 99.0

    def test_score_to_level_boundary_19_point_9(self):
        assert _score_to_level(19.9) == MaturityLevel.level_0_initial

    def test_score_to_level_boundary_20_point_0(self):
        assert _score_to_level(20.0) == MaturityLevel.level_1_planned

    def test_score_to_level_boundary_79_point_9(self):
        assert _score_to_level(79.9) == MaturityLevel.level_3_managed

    def test_industry_comparison_percentile_clamped_low(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_score=0.0, dimensions=[])
        ic = engine.compare_to_industry(assessment, "finance")
        assert ic.percentile >= 1.0

    def test_industry_comparison_percentile_clamped_high(self):
        engine = ChaosMaturityEngine()
        assessment = MaturityAssessment(overall_score=200.0, dimensions=[])
        ic = engine.compare_to_industry(assessment, "government")
        assert ic.percentile <= 99.0


# ---------------------------------------------------------------------------
# LEVEL_THRESHOLDS and INDUSTRY_AVERAGES constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_level_thresholds_descending(self):
        thresholds = [t for t, _ in _LEVEL_THRESHOLDS]
        assert thresholds == sorted(thresholds, reverse=True)

    def test_level_thresholds_has_five_entries(self):
        assert len(_LEVEL_THRESHOLDS) == 5

    def test_industry_averages_has_default(self):
        assert "default" in _INDUSTRY_AVERAGES

    def test_industry_averages_all_positive(self):
        for k, v in _INDUSTRY_AVERAGES.items():
            assert v > 0, f"Industry {k} has non-positive average"


# ---------------------------------------------------------------------------
# Additional dimension interaction tests
# ---------------------------------------------------------------------------


class TestDimensionInteractions:
    def test_culture_vs_process_consistency(self):
        engine = ChaosMaturityEngine()
        cfg = _full_config()
        g = _graph(_well_protected_comp("a"))
        culture = engine.score_dimension(g, MaturityDimension.culture, cfg)
        process = engine.score_dimension(g, MaturityDimension.process, cfg)
        assert abs(culture.score - process.score) < 40

    def test_all_dimensions_have_gaps_on_empty(self):
        engine = ChaosMaturityEngine()
        for dim in MaturityDimension:
            ds = engine.score_dimension(InfraGraph(), dim, ChaosConfig())
            assert len(ds.gaps) > 0, f"{dim.value} should have gaps on empty input"

    def test_all_dimensions_have_actions_on_empty(self):
        engine = ChaosMaturityEngine()
        for dim in MaturityDimension:
            ds = engine.score_dimension(InfraGraph(), dim, ChaosConfig())
            assert len(ds.next_level_actions) > 0, f"{dim.value} should have actions"

    def test_all_dimensions_have_evidence_on_full(self):
        engine = ChaosMaturityEngine()
        g = _graph(_well_protected_comp("a"))
        g.add_dependency(Dependency(
            source_id="a", target_id="a",  # self-loop, harmless for testing
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            retry_strategy=RetryStrategy(enabled=True),
        ))
        for dim in MaturityDimension:
            ds = engine.score_dimension(g, dim, _full_config())
            assert len(ds.evidence) > 0, f"{dim.value} should have evidence on full config"


# ---------------------------------------------------------------------------
# Coverage gap tests — hit remaining branches
# ---------------------------------------------------------------------------


class TestCoverageGaps:
    def test_score_to_level_negative_score(self):
        """Line 64: fallback return when score < 0 (below all thresholds)."""
        assert _score_to_level(-1.0) == MaturityLevel.level_0_initial

    def test_industry_comparison_zero_average(self):
        """Line 314: branch where industry avg is 0."""
        from faultray.simulator.chaos_maturity import _INDUSTRY_AVERAGES
        original = _INDUSTRY_AVERAGES.get("default")
        _INDUSTRY_AVERAGES["_test_zero"] = 0.0
        try:
            engine = ChaosMaturityEngine()
            # Use a custom industry that has 0 average — we need to directly
            # override compare_to_industry's lookup
            assessment = MaturityAssessment(overall_score=50.0, dimensions=[])
            # Temporarily set default to 0
            _INDUSTRY_AVERAGES["default"] = 0.0
            ic = engine.compare_to_industry(assessment, "nonexistent_zero_avg")
            assert ic.percentile == 50.0
        finally:
            _INDUSTRY_AVERAGES["default"] = original
            _INDUSTRY_AVERAGES.pop("_test_zero", None)

    def test_tooling_low_cb_retry_ratio(self):
        """Lines 605-606: edges present but low CB/retry ratio (< 0.5)."""
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        # One edge with CB only (no retry), two edges bare
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        g.add_dependency(Dependency(source_id="a", target_id="c"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        ds = engine.score_dimension(g, MaturityDimension.tooling, ChaosConfig())
        assert any("low" in gap.lower() or "cb" in gap.lower() for gap in ds.gaps)

    def test_blast_radius_low_cb_ratio(self):
        """Lines 812-813: edges present but CB ratio < 0.5."""
        engine = ChaosMaturityEngine()
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        # One edge with CB, two without
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        g.add_dependency(Dependency(source_id="a", target_id="c"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        ds = engine.score_dimension(g, MaturityDimension.blast_radius_control, ChaosConfig())
        assert any("circuit breaker" in gap.lower() or "cb" in gap.lower() for gap in ds.gaps)

    def test_average_score_empty_list(self):
        """Line 973: _average_score called with empty list."""
        engine = ChaosMaturityEngine()
        assert engine._average_score([]) == 0.0
