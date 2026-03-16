"""Tests for the Infrastructure Migration Risk Analyzer."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.migration_risk import (
    CompatibilityGap,
    DataMigrationRisk,
    DowntimeEstimate,
    MigrationComplexity,
    MigrationPhase,
    MigrationRiskAssessment,
    MigrationRiskEngine,
    MigrationTarget,
    MigrationType,
    RiskCategory,
    RollbackPlan,
    _COMPONENT_TYPE_DATA_RISK,
    _COMPONENT_TYPE_DOWNTIME_MINUTES,
    _MIGRATION_TYPE_BASE_RISK,
    _MIGRATION_TYPE_COMPLEXITY_HOURS,
    _MIGRATION_TYPE_VENDOR_LOCK_IN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(name: str = "c1", ctype: ComponentType = ComponentType.APP_SERVER) -> Component:
    return Component(id=name, name=name, type=ctype, replicas=2)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _target(
    source: str = "aws",
    target: str = "gcp",
    mtype: MigrationType = MigrationType.LIFT_AND_SHIFT,
    components: list[str] | None = None,
) -> MigrationTarget:
    return MigrationTarget(
        source_platform=source,
        target_platform=target,
        migration_type=mtype,
        components=components or [],
    )


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


class TestMigrationTypeEnum:
    def test_all_values(self):
        expected = {
            "lift_and_shift",
            "replatform",
            "refactor",
            "repurchase",
            "retain",
            "retire",
            "hybrid",
        }
        assert {m.value for m in MigrationType} == expected

    def test_str_mixin(self):
        assert str(MigrationType.LIFT_AND_SHIFT) == "MigrationType.LIFT_AND_SHIFT"
        assert MigrationType.REFACTOR.value == "refactor"

    def test_member_count(self):
        assert len(MigrationType) == 7


class TestMigrationPhaseEnum:
    def test_all_values(self):
        expected = {
            "assessment",
            "planning",
            "execution",
            "validation",
            "cutover",
            "rollback",
        }
        assert {p.value for p in MigrationPhase} == expected

    def test_member_count(self):
        assert len(MigrationPhase) == 6


class TestRiskCategoryEnum:
    def test_all_values(self):
        expected = {
            "data_loss",
            "downtime",
            "compatibility",
            "performance_degradation",
            "security_gap",
            "cost_overrun",
            "skill_gap",
            "vendor_lock_in",
            "compliance_violation",
            "integration_failure",
        }
        assert {r.value for r in RiskCategory} == expected

    def test_member_count(self):
        assert len(RiskCategory) == 10


class TestMigrationComplexityEnum:
    def test_all_values(self):
        expected = {"trivial", "low", "moderate", "high", "extreme"}
        assert {c.value for c in MigrationComplexity} == expected

    def test_member_count(self):
        assert len(MigrationComplexity) == 5


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


class TestMigrationTargetModel:
    def test_defaults(self):
        t = MigrationTarget(
            source_platform="aws",
            target_platform="gcp",
            migration_type=MigrationType.LIFT_AND_SHIFT,
        )
        assert t.components == []
        assert t.source_platform == "aws"

    def test_with_components(self):
        t = MigrationTarget(
            source_platform="on_prem",
            target_platform="azure",
            migration_type=MigrationType.REPLATFORM,
            components=["db1", "app1"],
        )
        assert t.components == ["db1", "app1"]


class TestCompatibilityGapModel:
    def test_creation(self):
        g = CompatibilityGap(
            component_id="db1",
            gap_type="database_engine",
            severity=0.8,
            description="desc",
            remediation="fix it",
        )
        assert g.severity == 0.8
        assert g.component_id == "db1"

    def test_severity_bounds(self):
        with pytest.raises(Exception):
            CompatibilityGap(
                component_id="x", gap_type="t", severity=1.5,
                description="d", remediation="r",
            )
        with pytest.raises(Exception):
            CompatibilityGap(
                component_id="x", gap_type="t", severity=-0.1,
                description="d", remediation="r",
            )


class TestDataMigrationRiskModel:
    def test_defaults(self):
        d = DataMigrationRisk()
        assert d.data_volume_gb == 0.0
        assert d.estimated_duration_hours == 0.0
        assert d.data_loss_probability == 0.0
        assert d.validation_strategy == "checksum"

    def test_probability_bounds(self):
        with pytest.raises(Exception):
            DataMigrationRisk(data_loss_probability=1.5)


class TestDowntimeEstimateModel:
    def test_defaults(self):
        d = DowntimeEstimate()
        assert d.planned_minutes == 0.0
        assert d.worst_case_minutes == 0.0
        assert d.zero_downtime_possible is False
        assert d.strategy == "blue_green"


class TestRollbackPlanModel:
    def test_defaults(self):
        r = RollbackPlan()
        assert r.rollback_complexity == MigrationComplexity.MODERATE
        assert r.estimated_rollback_minutes == 0.0
        assert r.data_sync_strategy == "snapshot_restore"
        assert r.point_of_no_return_step == 0


class TestMigrationRiskAssessmentModel:
    def test_defaults(self):
        a = MigrationRiskAssessment()
        assert a.overall_risk_score == 0.0
        assert a.risk_breakdown == {}
        assert a.go_no_go_recommendation == "go"
        assert a.migration_complexity == MigrationComplexity.MODERATE

    def test_score_bounds(self):
        with pytest.raises(Exception):
            MigrationRiskAssessment(overall_risk_score=1.5)
        with pytest.raises(Exception):
            MigrationRiskAssessment(overall_risk_score=-0.1)


# ---------------------------------------------------------------------------
# Internal weight table tests
# ---------------------------------------------------------------------------


class TestWeightTables:
    def test_base_risk_all_types_covered(self):
        for mt in MigrationType:
            assert mt in _MIGRATION_TYPE_BASE_RISK

    def test_vendor_lock_in_all_types_covered(self):
        for mt in MigrationType:
            assert mt in _MIGRATION_TYPE_VENDOR_LOCK_IN

    def test_complexity_hours_all_types_covered(self):
        for mt in MigrationType:
            assert mt in _MIGRATION_TYPE_COMPLEXITY_HOURS

    def test_data_risk_all_component_types(self):
        for ct in ComponentType:
            assert ct in _COMPONENT_TYPE_DATA_RISK

    def test_downtime_all_component_types(self):
        for ct in ComponentType:
            assert ct in _COMPONENT_TYPE_DOWNTIME_MINUTES

    def test_base_risk_values_in_range(self):
        for v in _MIGRATION_TYPE_BASE_RISK.values():
            assert 0.0 <= v <= 1.0

    def test_vendor_lock_in_values_in_range(self):
        for v in _MIGRATION_TYPE_VENDOR_LOCK_IN.values():
            assert 0.0 <= v <= 1.0

    def test_lift_and_shift_low_base_risk(self):
        assert _MIGRATION_TYPE_BASE_RISK[MigrationType.LIFT_AND_SHIFT] < 0.4

    def test_refactor_high_base_risk(self):
        assert _MIGRATION_TYPE_BASE_RISK[MigrationType.REFACTOR] > 0.6

    def test_lift_and_shift_high_vendor_lock_in(self):
        assert _MIGRATION_TYPE_VENDOR_LOCK_IN[MigrationType.LIFT_AND_SHIFT] > 0.5

    def test_refactor_low_vendor_lock_in(self):
        assert _MIGRATION_TYPE_VENDOR_LOCK_IN[MigrationType.REFACTOR] < 0.3

    def test_database_highest_data_risk(self):
        assert _COMPONENT_TYPE_DATA_RISK[ComponentType.DATABASE] == max(
            _COMPONENT_TYPE_DATA_RISK.values()
        )


# ---------------------------------------------------------------------------
# Engine: assess_migration
# ---------------------------------------------------------------------------


class TestAssessMigration:
    def test_empty_graph(self):
        engine = MigrationRiskEngine()
        result = engine.assess_migration(InfraGraph(), _target())
        assert result.overall_risk_score == 0.0
        assert result.go_no_go_recommendation == "go"
        assert result.migration_complexity == MigrationComplexity.TRIVIAL
        assert result.assessed_at != ""

    def test_single_app_server(self):
        g = _graph(_comp("app1"))
        engine = MigrationRiskEngine()
        result = engine.assess_migration(g, _target())
        assert 0.0 < result.overall_risk_score < 1.0
        assert len(result.risk_breakdown) == len(RiskCategory)
        assert result.estimated_total_hours > 0

    def test_all_risk_categories_present(self):
        g = _graph(_comp("a1"), _comp("a2"))
        result = MigrationRiskEngine().assess_migration(g, _target())
        for cat in RiskCategory:
            assert cat.value in result.risk_breakdown

    def test_database_increases_data_loss_risk(self):
        g_no_db = _graph(_comp("app"))
        g_db = _graph(_comp("app"), _comp("db", ComponentType.DATABASE))
        engine = MigrationRiskEngine()
        r_no = engine.assess_migration(g_no_db, _target())
        r_db = engine.assess_migration(g_db, _target())
        assert r_db.risk_breakdown[RiskCategory.DATA_LOSS.value] > r_no.risk_breakdown[RiskCategory.DATA_LOSS.value]

    def test_more_components_higher_risk(self):
        g_small = _graph(_comp("a"))
        comps = [_comp(f"c{i}") for i in range(10)]
        g_large = _graph(*comps)
        engine = MigrationRiskEngine()
        r_small = engine.assess_migration(g_small, _target())
        r_large = engine.assess_migration(g_large, _target())
        assert r_large.overall_risk_score >= r_small.overall_risk_score

    def test_lift_and_shift_lower_risk_than_refactor(self):
        g = _graph(_comp("a1"), _comp("db", ComponentType.DATABASE))
        engine = MigrationRiskEngine()
        r_ls = engine.assess_migration(g, _target(mtype=MigrationType.LIFT_AND_SHIFT))
        r_rf = engine.assess_migration(g, _target(mtype=MigrationType.REFACTOR))
        assert r_ls.overall_risk_score < r_rf.overall_risk_score

    def test_refactor_higher_estimated_hours(self):
        g = _graph(_comp("a"))
        engine = MigrationRiskEngine()
        r_ls = engine.assess_migration(g, _target(mtype=MigrationType.LIFT_AND_SHIFT))
        r_rf = engine.assess_migration(g, _target(mtype=MigrationType.REFACTOR))
        assert r_rf.estimated_total_hours > r_ls.estimated_total_hours

    def test_retain_minimal_risk(self):
        g = _graph(_comp("a"))
        r = MigrationRiskEngine().assess_migration(g, _target(mtype=MigrationType.RETAIN))
        assert r.overall_risk_score < 0.3

    def test_retire_minimal_risk(self):
        g = _graph(_comp("a"))
        r = MigrationRiskEngine().assess_migration(g, _target(mtype=MigrationType.RETIRE))
        assert r.overall_risk_score < 0.3

    def test_scoped_components(self):
        g = _graph(_comp("a1"), _comp("a2"), _comp("a3"))
        t = _target(components=["a1", "a2"])
        r = MigrationRiskEngine().assess_migration(g, t)
        assert r.estimated_total_hours > 0
        t_all = _target()
        r_all = MigrationRiskEngine().assess_migration(g, t_all)
        assert r_all.estimated_total_hours > r.estimated_total_hours

    def test_scoped_nonexistent_components(self):
        g = _graph(_comp("a1"))
        t = _target(components=["nonexistent"])
        r = MigrationRiskEngine().assess_migration(g, t)
        assert r.overall_risk_score == 0.0

    def test_go_no_go_go(self):
        g = _graph(_comp("a"))
        r = MigrationRiskEngine().assess_migration(
            g, _target(mtype=MigrationType.RETAIN)
        )
        assert r.go_no_go_recommendation == "go"

    def test_go_no_go_no_go(self):
        comps = [_comp(f"c{i}", ComponentType.DATABASE) for i in range(15)]
        g = _graph(*comps)
        r = MigrationRiskEngine().assess_migration(
            g, _target(mtype=MigrationType.REFACTOR)
        )
        assert r.go_no_go_recommendation == "no_go"

    def test_recommendations_not_empty_for_complex_migration(self):
        g = _graph(
            _comp("app"),
            _comp("db", ComponentType.DATABASE),
            _comp("cache", ComponentType.CACHE),
        )
        r = MigrationRiskEngine().assess_migration(
            g, _target(mtype=MigrationType.REFACTOR)
        )
        assert len(r.recommendations) > 0

    def test_all_migration_types_produce_different_profiles(self):
        g = _graph(_comp("a"), _comp("db", ComponentType.DATABASE))
        engine = MigrationRiskEngine()
        scores = {}
        for mt in MigrationType:
            r = engine.assess_migration(g, _target(mtype=mt))
            scores[mt] = r.overall_risk_score
        unique_scores = set(round(s, 3) for s in scores.values())
        assert len(unique_scores) > 1

    def test_assessed_at_is_iso_format(self):
        g = _graph(_comp("a"))
        r = MigrationRiskEngine().assess_migration(g, _target())
        from datetime import datetime
        datetime.fromisoformat(r.assessed_at.replace("Z", "+00:00"))

    def test_risk_scores_in_range(self):
        g = _graph(_comp("a"), _comp("db", ComponentType.DATABASE))
        r = MigrationRiskEngine().assess_migration(g, _target())
        assert 0.0 <= r.overall_risk_score <= 1.0
        for v in r.risk_breakdown.values():
            assert 0.0 <= v <= 1.0

    def test_hybrid_migration(self):
        g = _graph(_comp("a"), _comp("db", ComponentType.DATABASE))
        r = MigrationRiskEngine().assess_migration(
            g, _target(mtype=MigrationType.HYBRID)
        )
        assert r.overall_risk_score > 0.0
        assert r.estimated_total_hours > 0


# ---------------------------------------------------------------------------
# Engine: evaluate_compatibility
# ---------------------------------------------------------------------------


class TestEvaluateCompatibility:
    def test_same_platform_no_gaps(self):
        g = _graph(_comp("a"))
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "aws")
        assert gaps == []

    def test_database_gap(self):
        g = _graph(_comp("db", ComponentType.DATABASE))
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "gcp")
        db_gaps = [g for g in gaps if g.gap_type == "database_engine"]
        assert len(db_gaps) == 1
        assert db_gaps[0].severity == 0.8

    def test_cache_gap(self):
        g = _graph(_comp("cache", ComponentType.CACHE))
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "azure")
        cache_gaps = [g for g in gaps if g.gap_type == "cache_protocol"]
        assert len(cache_gaps) == 1

    def test_queue_gap(self):
        g = _graph(_comp("q", ComponentType.QUEUE))
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "gcp")
        q_gaps = [g for g in gaps if g.gap_type == "message_format"]
        assert len(q_gaps) == 1

    def test_dns_gap(self):
        g = _graph(_comp("dns", ComponentType.DNS))
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "gcp")
        dns_gaps = [g for g in gaps if g.gap_type == "dns_provider"]
        assert len(dns_gaps) == 1

    def test_external_api_gap(self):
        g = _graph(_comp("ext", ComponentType.EXTERNAL_API))
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "gcp")
        api_gaps = [g for g in gaps if g.gap_type == "api_endpoint"]
        assert len(api_gaps) == 1

    def test_storage_gap(self):
        g = _graph(_comp("s3", ComponentType.STORAGE))
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "gcp")
        s_gaps = [g for g in gaps if g.gap_type == "storage_api"]
        assert len(s_gaps) == 1

    def test_load_balancer_gap(self):
        g = _graph(_comp("lb", ComponentType.LOAD_BALANCER))
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "gcp")
        lb_gaps = [g for g in gaps if g.gap_type == "lb_config"]
        assert len(lb_gaps) == 1

    def test_no_redundancy_gap(self):
        c = Component(id="single", name="single", type=ComponentType.APP_SERVER, replicas=1)
        g = _graph(c)
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "gcp")
        nr_gaps = [g for g in gaps if g.gap_type == "no_redundancy"]
        assert len(nr_gaps) == 1

    def test_redundant_component_no_redundancy_gap(self):
        c = _comp("ha")  # replicas=2 by default from _comp
        g = _graph(c)
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "gcp")
        nr_gaps = [g for g in gaps if g.gap_type == "no_redundancy"]
        assert len(nr_gaps) == 0

    def test_failover_avoids_redundancy_gap(self):
        c = Component(
            id="fo", name="fo", type=ComponentType.APP_SERVER, replicas=1,
            failover=FailoverConfig(enabled=True),
        )
        g = _graph(c)
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "gcp")
        nr_gaps = [g for g in gaps if g.gap_type == "no_redundancy"]
        assert len(nr_gaps) == 0

    def test_empty_graph_no_gaps(self):
        gaps = MigrationRiskEngine().evaluate_compatibility(InfraGraph(), "aws", "gcp")
        assert gaps == []

    def test_multiple_components_multiple_gaps(self):
        g = _graph(
            _comp("db", ComponentType.DATABASE),
            _comp("cache", ComponentType.CACHE),
            _comp("q", ComponentType.QUEUE),
        )
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "on_prem", "aws")
        assert len(gaps) >= 3

    def test_web_server_no_type_specific_gap(self):
        g = _graph(_comp("web", ComponentType.WEB_SERVER))
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "gcp")
        type_gaps = [
            g for g in gaps
            if g.gap_type not in ("no_redundancy",)
        ]
        assert len(type_gaps) == 0

    def test_custom_component_no_type_specific_gap(self):
        g = _graph(_comp("custom", ComponentType.CUSTOM))
        gaps = MigrationRiskEngine().evaluate_compatibility(g, "aws", "gcp")
        type_gaps = [
            g for g in gaps
            if g.gap_type not in ("no_redundancy",)
        ]
        assert len(type_gaps) == 0


# ---------------------------------------------------------------------------
# Engine: estimate_downtime
# ---------------------------------------------------------------------------


class TestEstimateDowntime:
    def test_zero_components(self):
        dt = MigrationRiskEngine().estimate_downtime(InfraGraph(), MigrationType.LIFT_AND_SHIFT, 0)
        assert dt.planned_minutes == 0.0
        assert dt.worst_case_minutes == 0.0
        assert dt.zero_downtime_possible is True
        assert dt.strategy == "none"

    def test_single_app_server(self):
        g = _graph(_comp("a"))
        dt = MigrationRiskEngine().estimate_downtime(g, MigrationType.LIFT_AND_SHIFT, 1)
        assert dt.planned_minutes > 0
        assert dt.worst_case_minutes > dt.planned_minutes
        assert dt.strategy == "blue_green"

    def test_refactor_higher_downtime(self):
        g = _graph(_comp("a"))
        engine = MigrationRiskEngine()
        dt_ls = engine.estimate_downtime(g, MigrationType.LIFT_AND_SHIFT, 1)
        dt_rf = engine.estimate_downtime(g, MigrationType.REFACTOR, 1)
        assert dt_rf.planned_minutes > dt_ls.planned_minutes

    def test_refactor_strategy_strangler(self):
        g = _graph(_comp("a"))
        dt = MigrationRiskEngine().estimate_downtime(g, MigrationType.REFACTOR, 1)
        assert dt.strategy == "strangler_fig"

    def test_retire_strategy_decommission(self):
        g = _graph(_comp("a"))
        dt = MigrationRiskEngine().estimate_downtime(g, MigrationType.RETIRE, 1)
        assert dt.strategy == "decommission"

    def test_retain_strategy_none(self):
        g = _graph(_comp("a"))
        dt = MigrationRiskEngine().estimate_downtime(g, MigrationType.RETAIN, 1)
        assert dt.strategy == "none"

    def test_replatform_strategy_rolling(self):
        g = _graph(_comp("a"))
        dt = MigrationRiskEngine().estimate_downtime(g, MigrationType.REPLATFORM, 1)
        assert dt.strategy == "rolling"

    def test_repurchase_strategy_rolling(self):
        g = _graph(_comp("a"))
        dt = MigrationRiskEngine().estimate_downtime(g, MigrationType.REPURCHASE, 1)
        assert dt.strategy == "rolling"

    def test_hybrid_strategy_rolling(self):
        g = _graph(_comp("a"))
        dt = MigrationRiskEngine().estimate_downtime(g, MigrationType.HYBRID, 1)
        assert dt.strategy == "rolling"

    def test_zero_downtime_possible_simple(self):
        g = _graph(_comp("a"))
        dt = MigrationRiskEngine().estimate_downtime(g, MigrationType.LIFT_AND_SHIFT, 1)
        assert dt.zero_downtime_possible is True

    def test_zero_downtime_not_possible_many_components(self):
        comps = [_comp(f"c{i}") for i in range(5)]
        g = _graph(*comps)
        dt = MigrationRiskEngine().estimate_downtime(g, MigrationType.LIFT_AND_SHIFT, 5)
        assert dt.zero_downtime_possible is False

    def test_zero_downtime_not_possible_refactor(self):
        g = _graph(_comp("a"))
        dt = MigrationRiskEngine().estimate_downtime(g, MigrationType.REFACTOR, 1)
        assert dt.zero_downtime_possible is False

    def test_database_increases_downtime(self):
        g_app = _graph(_comp("a"))
        g_db = _graph(_comp("db", ComponentType.DATABASE))
        engine = MigrationRiskEngine()
        dt_app = engine.estimate_downtime(g_app, MigrationType.LIFT_AND_SHIFT, 1)
        dt_db = engine.estimate_downtime(g_db, MigrationType.LIFT_AND_SHIFT, 1)
        assert dt_db.planned_minutes > dt_app.planned_minutes

    def test_worst_case_is_multiplied(self):
        g = _graph(_comp("a"))
        dt = MigrationRiskEngine().estimate_downtime(g, MigrationType.REPLATFORM, 1)
        assert dt.worst_case_minutes == pytest.approx(dt.planned_minutes * 2.5)

    def test_all_migration_types_produce_positive_downtime(self):
        g = _graph(_comp("a"))
        engine = MigrationRiskEngine()
        for mt in MigrationType:
            dt = engine.estimate_downtime(g, mt, 1)
            assert dt.planned_minutes >= 0
            assert dt.worst_case_minutes >= 0


# ---------------------------------------------------------------------------
# Engine: plan_rollback
# ---------------------------------------------------------------------------


class TestPlanRollback:
    def test_empty_graph(self):
        r = MigrationRiskEngine().plan_rollback(InfraGraph(), _target())
        assert r.rollback_complexity == MigrationComplexity.TRIVIAL
        assert r.estimated_rollback_minutes == 0.0
        assert r.data_sync_strategy == "none"

    def test_lift_and_shift_low_complexity(self):
        g = _graph(_comp("a"))
        r = MigrationRiskEngine().plan_rollback(g, _target(mtype=MigrationType.LIFT_AND_SHIFT))
        assert r.rollback_complexity == MigrationComplexity.LOW

    def test_refactor_extreme_complexity(self):
        g = _graph(_comp("a"))
        r = MigrationRiskEngine().plan_rollback(g, _target(mtype=MigrationType.REFACTOR))
        assert r.rollback_complexity == MigrationComplexity.EXTREME

    def test_retain_trivial_complexity(self):
        g = _graph(_comp("a"))
        r = MigrationRiskEngine().plan_rollback(g, _target(mtype=MigrationType.RETAIN))
        assert r.rollback_complexity == MigrationComplexity.TRIVIAL

    def test_repurchase_high_complexity(self):
        g = _graph(_comp("a"))
        r = MigrationRiskEngine().plan_rollback(g, _target(mtype=MigrationType.REPURCHASE))
        assert r.rollback_complexity == MigrationComplexity.HIGH

    def test_replatform_moderate_complexity(self):
        g = _graph(_comp("a"))
        r = MigrationRiskEngine().plan_rollback(g, _target(mtype=MigrationType.REPLATFORM))
        assert r.rollback_complexity == MigrationComplexity.MODERATE

    def test_retire_high_complexity(self):
        g = _graph(_comp("a"))
        r = MigrationRiskEngine().plan_rollback(g, _target(mtype=MigrationType.RETIRE))
        assert r.rollback_complexity == MigrationComplexity.HIGH

    def test_hybrid_high_complexity(self):
        g = _graph(_comp("a"))
        r = MigrationRiskEngine().plan_rollback(g, _target(mtype=MigrationType.HYBRID))
        assert r.rollback_complexity == MigrationComplexity.HIGH

    def test_database_snapshot_restore(self):
        g = _graph(_comp("db", ComponentType.DATABASE))
        r = MigrationRiskEngine().plan_rollback(g, _target())
        assert r.data_sync_strategy == "snapshot_restore"

    def test_storage_rsync(self):
        g = _graph(_comp("s3", ComponentType.STORAGE))
        r = MigrationRiskEngine().plan_rollback(g, _target())
        assert r.data_sync_strategy == "rsync"

    def test_app_only_none_sync(self):
        g = _graph(_comp("app"))
        r = MigrationRiskEngine().plan_rollback(g, _target())
        assert r.data_sync_strategy == "none"

    def test_more_components_more_rollback_time(self):
        g_small = _graph(_comp("a"))
        comps = [_comp(f"c{i}") for i in range(5)]
        g_large = _graph(*comps)
        engine = MigrationRiskEngine()
        r_small = engine.plan_rollback(g_small, _target())
        r_large = engine.plan_rollback(g_large, _target())
        assert r_large.estimated_rollback_minutes > r_small.estimated_rollback_minutes

    def test_refactor_point_of_no_return_early(self):
        g = _graph(_comp("a"))
        r = MigrationRiskEngine().plan_rollback(g, _target(mtype=MigrationType.REFACTOR))
        assert r.point_of_no_return_step == 1

    def test_database_lowers_point_of_no_return(self):
        g_app = _graph(_comp("app"))
        g_db = _graph(_comp("db", ComponentType.DATABASE))
        engine = MigrationRiskEngine()
        r_app = engine.plan_rollback(g_app, _target())
        r_db = engine.plan_rollback(g_db, _target())
        assert r_db.point_of_no_return_step <= r_app.point_of_no_return_step

    def test_scoped_rollback(self):
        g = _graph(_comp("a1"), _comp("a2"), _comp("a3"))
        t = _target(components=["a1"])
        r = MigrationRiskEngine().plan_rollback(g, t)
        assert r.estimated_rollback_minutes > 0

    def test_scoped_nonexistent(self):
        g = _graph(_comp("a1"))
        t = _target(components=["missing"])
        r = MigrationRiskEngine().plan_rollback(g, t)
        assert r.rollback_complexity == MigrationComplexity.TRIVIAL


# ---------------------------------------------------------------------------
# Engine: calculate_data_risk
# ---------------------------------------------------------------------------


class TestCalculateDataRisk:
    def test_empty_graph(self):
        r = MigrationRiskEngine().calculate_data_risk(InfraGraph(), 0.0)
        assert r.data_loss_probability == 0.0
        assert r.estimated_duration_hours == 0.0
        assert r.validation_strategy == "none"

    def test_database_present(self):
        g = _graph(_comp("db", ComponentType.DATABASE))
        r = MigrationRiskEngine().calculate_data_risk(g, 0.0)
        assert r.data_loss_probability > 0.0
        assert r.validation_strategy == "row_count_and_checksum"

    def test_storage_present(self):
        g = _graph(_comp("s3", ComponentType.STORAGE))
        r = MigrationRiskEngine().calculate_data_risk(g, 0.0)
        assert r.data_loss_probability > 0.0
        assert r.validation_strategy == "checksum"

    def test_app_only_zero_loss(self):
        g = _graph(_comp("app"))
        r = MigrationRiskEngine().calculate_data_risk(g, 0.0)
        assert r.data_loss_probability == 0.0
        assert r.validation_strategy == "smoke_test"

    def test_explicit_volume(self):
        g = _graph(_comp("db", ComponentType.DATABASE))
        r = MigrationRiskEngine().calculate_data_risk(g, 500.0)
        assert r.data_volume_gb == 500.0
        assert r.estimated_duration_hours == pytest.approx(10.0)

    def test_volume_from_metrics(self):
        c = Component(
            id="db", name="db", type=ComponentType.DATABASE,
            replicas=1, metrics=ResourceMetrics(disk_used_gb=100.0),
        )
        g = _graph(c)
        r = MigrationRiskEngine().calculate_data_risk(g, 0.0)
        assert r.data_volume_gb == 100.0

    def test_multiple_databases_increase_loss_probability(self):
        g1 = _graph(_comp("db1", ComponentType.DATABASE))
        g2 = _graph(
            _comp("db1", ComponentType.DATABASE),
            _comp("db2", ComponentType.DATABASE),
        )
        engine = MigrationRiskEngine()
        r1 = engine.calculate_data_risk(g1, 0.0)
        r2 = engine.calculate_data_risk(g2, 0.0)
        assert r2.data_loss_probability > r1.data_loss_probability

    def test_loss_probability_capped(self):
        comps = [_comp(f"db{i}", ComponentType.DATABASE) for i in range(20)]
        g = _graph(*comps)
        r = MigrationRiskEngine().calculate_data_risk(g, 0.0)
        assert r.data_loss_probability <= 1.0

    def test_cache_has_data_risk(self):
        g = _graph(_comp("c", ComponentType.CACHE))
        r = MigrationRiskEngine().calculate_data_risk(g, 0.0)
        assert r.data_loss_probability > 0.0


# ---------------------------------------------------------------------------
# Engine: generate_migration_waves
# ---------------------------------------------------------------------------


class TestGenerateMigrationWaves:
    def test_empty_graph(self):
        waves = MigrationRiskEngine().generate_migration_waves(InfraGraph(), _target())
        assert waves == []

    def test_single_component(self):
        g = _graph(_comp("a"))
        waves = MigrationRiskEngine().generate_migration_waves(g, _target())
        assert len(waves) == 1
        assert waves[0]["wave"] == 1
        assert "a" in waves[0]["components"]

    def test_independent_components_single_wave(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        waves = MigrationRiskEngine().generate_migration_waves(g, _target())
        assert len(waves) == 1
        assert len(waves[0]["components"]) == 3

    def test_dependency_chain_multiple_waves(self):
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        web = _comp("web", ComponentType.WEB_SERVER)
        g = _graph(db, app, web)
        g.add_dependency(Dependency(source_id="web", target_id="app"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        waves = MigrationRiskEngine().generate_migration_waves(g, _target())
        assert len(waves) >= 2
        db_wave = None
        app_wave = None
        web_wave = None
        for w in waves:
            if "db" in w["components"]:
                db_wave = w["wave"]
            if "app" in w["components"]:
                app_wave = w["wave"]
            if "web" in w["components"]:
                web_wave = w["wave"]
        assert db_wave is not None
        assert app_wave is not None
        assert web_wave is not None
        assert db_wave < app_wave
        assert app_wave < web_wave

    def test_scoped_components(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        t = _target(components=["a", "b"])
        waves = MigrationRiskEngine().generate_migration_waves(g, t)
        all_ids = []
        for w in waves:
            all_ids.extend(w["components"])
        assert "a" in all_ids
        assert "b" in all_ids
        assert "c" not in all_ids

    def test_wave_description_present(self):
        g = _graph(_comp("a"))
        waves = MigrationRiskEngine().generate_migration_waves(g, _target())
        assert "description" in waves[0]
        assert "Wave 1" in waves[0]["description"]

    def test_wave_numbers_sequential(self):
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph(db, app)
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        waves = MigrationRiskEngine().generate_migration_waves(g, _target())
        for i, w in enumerate(waves):
            assert w["wave"] == i + 1

    def test_scoped_nonexistent_components(self):
        g = _graph(_comp("a"))
        t = _target(components=["missing"])
        waves = MigrationRiskEngine().generate_migration_waves(g, t)
        assert waves == []

    def test_complex_graph_all_components_placed(self):
        comps = [_comp(f"c{i}") for i in range(8)]
        g = _graph(*comps)
        g.add_dependency(Dependency(source_id="c1", target_id="c0"))
        g.add_dependency(Dependency(source_id="c2", target_id="c0"))
        g.add_dependency(Dependency(source_id="c3", target_id="c1"))
        waves = MigrationRiskEngine().generate_migration_waves(g, _target())
        placed = []
        for w in waves:
            placed.extend(w["components"])
        for c in comps:
            assert c.id in placed

    def test_circular_dependency_handled(self):
        """Cycle in dependency graph should not hang; all components placed."""
        a = _comp("a")
        b = _comp("b")
        c = _comp("c")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        g.add_dependency(Dependency(source_id="c", target_id="a"))
        waves = MigrationRiskEngine().generate_migration_waves(g, _target())
        placed = []
        for w in waves:
            placed.extend(w["components"])
        assert set(placed) == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# Engine: _classify_complexity
# ---------------------------------------------------------------------------


class TestClassifyComplexity:
    def test_trivial(self):
        assert MigrationRiskEngine._classify_complexity(0.05) == MigrationComplexity.TRIVIAL

    def test_low(self):
        assert MigrationRiskEngine._classify_complexity(0.15) == MigrationComplexity.LOW

    def test_moderate(self):
        assert MigrationRiskEngine._classify_complexity(0.40) == MigrationComplexity.MODERATE

    def test_high(self):
        assert MigrationRiskEngine._classify_complexity(0.70) == MigrationComplexity.HIGH

    def test_extreme(self):
        assert MigrationRiskEngine._classify_complexity(0.90) == MigrationComplexity.EXTREME

    def test_boundary_trivial_low(self):
        assert MigrationRiskEngine._classify_complexity(0.10) == MigrationComplexity.LOW

    def test_boundary_low_moderate(self):
        assert MigrationRiskEngine._classify_complexity(0.30) == MigrationComplexity.MODERATE

    def test_boundary_moderate_high(self):
        assert MigrationRiskEngine._classify_complexity(0.55) == MigrationComplexity.HIGH

    def test_boundary_high_extreme(self):
        assert MigrationRiskEngine._classify_complexity(0.80) == MigrationComplexity.EXTREME

    def test_zero(self):
        assert MigrationRiskEngine._classify_complexity(0.0) == MigrationComplexity.TRIVIAL

    def test_one(self):
        assert MigrationRiskEngine._classify_complexity(1.0) == MigrationComplexity.EXTREME


# ---------------------------------------------------------------------------
# Engine: helper methods
# ---------------------------------------------------------------------------


class TestHelperMethods:
    def test_component_data_risk(self):
        c = _comp("db", ComponentType.DATABASE)
        r = MigrationRiskEngine._component_data_risk(c)
        assert r == _COMPONENT_TYPE_DATA_RISK[ComponentType.DATABASE]

    def test_component_downtime_minutes(self):
        c = _comp("db", ComponentType.DATABASE)
        r = MigrationRiskEngine._component_downtime_minutes(c)
        assert r == _COMPONENT_TYPE_DOWNTIME_MINUTES[ComponentType.DATABASE]

    def test_has_data_components_true(self):
        g = _graph(_comp("db", ComponentType.DATABASE))
        assert MigrationRiskEngine._has_data_components(g) is True

    def test_has_data_components_false(self):
        g = _graph(_comp("app"))
        assert MigrationRiskEngine._has_data_components(g) is False

    def test_has_data_components_storage(self):
        g = _graph(_comp("s3", ComponentType.STORAGE))
        assert MigrationRiskEngine._has_data_components(g) is True

    def test_has_data_components_cache(self):
        g = _graph(_comp("cache", ComponentType.CACHE))
        assert MigrationRiskEngine._has_data_components(g) is True

    def test_count_databases(self):
        g = _graph(
            _comp("db1", ComponentType.DATABASE),
            _comp("db2", ComponentType.DATABASE),
            _comp("app"),
        )
        assert MigrationRiskEngine._count_databases(g) == 2

    def test_count_databases_none(self):
        g = _graph(_comp("app"))
        assert MigrationRiskEngine._count_databases(g) == 0

    def test_resolve_components_all(self):
        g = _graph(_comp("a"), _comp("b"))
        t = _target()
        comps = MigrationRiskEngine._resolve_components(g, t)
        assert len(comps) == 2

    def test_resolve_components_scoped(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        t = _target(components=["a", "c"])
        comps = MigrationRiskEngine._resolve_components(g, t)
        ids = {c.id for c in comps}
        assert ids == {"a", "c"}

    def test_resolve_components_missing_ids(self):
        g = _graph(_comp("a"))
        t = _target(components=["a", "missing"])
        comps = MigrationRiskEngine._resolve_components(g, t)
        assert len(comps) == 1


# ---------------------------------------------------------------------------
# Engine: _build_recommendations
# ---------------------------------------------------------------------------


class TestBuildRecommendations:
    def _engine(self):
        return MigrationRiskEngine()

    def test_high_data_loss_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {RiskCategory.DATA_LOSS.value: 0.5, **{c.value: 0.0 for c in RiskCategory if c != RiskCategory.DATA_LOSS}},
            1, 0,
        )
        assert any("backup" in r.lower() for r in recs)

    def test_high_downtime_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {RiskCategory.DOWNTIME.value: 0.6, **{c.value: 0.0 for c in RiskCategory if c != RiskCategory.DOWNTIME}},
            1, 0,
        )
        assert any("downtime" in r.lower() for r in recs)

    def test_high_vendor_lock_in_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {RiskCategory.VENDOR_LOCK_IN.value: 0.7, **{c.value: 0.0 for c in RiskCategory if c != RiskCategory.VENDOR_LOCK_IN}},
            1, 0,
        )
        assert any("vendor" in r.lower() or "lock-in" in r.lower() for r in recs)

    def test_database_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {c.value: 0.0 for c in RiskCategory},
            1, 2,
        )
        assert any("snapshot" in r.lower() for r in recs)

    def test_many_components_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {c.value: 0.0 for c in RiskCategory},
            10, 0,
        )
        assert any("wave" in r.lower() for r in recs)

    def test_lift_and_shift_specific_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {c.value: 0.0 for c in RiskCategory},
            1, 0,
        )
        assert any("lift-and-shift" in r.lower() or "modernization" in r.lower() for r in recs)

    def test_refactor_specific_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.REFACTOR,
            {c.value: 0.0 for c in RiskCategory},
            1, 0,
        )
        assert any("test coverage" in r.lower() for r in recs)

    def test_hybrid_specific_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.HYBRID,
            {c.value: 0.0 for c in RiskCategory},
            1, 0,
        )
        assert any("boundaries" in r.lower() for r in recs)

    def test_all_high_risks_many_recommendations(self):
        recs = self._engine()._build_recommendations(
            MigrationType.REFACTOR,
            {c.value: 0.9 for c in RiskCategory},
            10, 5,
        )
        assert len(recs) >= 5

    def test_all_low_risks_few_recommendations(self):
        recs = self._engine()._build_recommendations(
            MigrationType.RETAIN,
            {c.value: 0.0 for c in RiskCategory},
            1, 0,
        )
        assert isinstance(recs, list)

    def test_security_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {RiskCategory.SECURITY_GAP.value: 0.5, **{c.value: 0.0 for c in RiskCategory if c != RiskCategory.SECURITY_GAP}},
            1, 0,
        )
        assert any("security" in r.lower() for r in recs)

    def test_cost_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {RiskCategory.COST_OVERRUN.value: 0.5, **{c.value: 0.0 for c in RiskCategory if c != RiskCategory.COST_OVERRUN}},
            1, 0,
        )
        assert any("cost" in r.lower() for r in recs)

    def test_skill_gap_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {RiskCategory.SKILL_GAP.value: 0.6, **{c.value: 0.0 for c in RiskCategory if c != RiskCategory.SKILL_GAP}},
            1, 0,
        )
        assert any("training" in r.lower() for r in recs)

    def test_compliance_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {RiskCategory.COMPLIANCE_VIOLATION.value: 0.5, **{c.value: 0.0 for c in RiskCategory if c != RiskCategory.COMPLIANCE_VIOLATION}},
            1, 0,
        )
        assert any("compliance" in r.lower() for r in recs)

    def test_integration_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {RiskCategory.INTEGRATION_FAILURE.value: 0.5, **{c.value: 0.0 for c in RiskCategory if c != RiskCategory.INTEGRATION_FAILURE}},
            1, 0,
        )
        assert any("integration" in r.lower() for r in recs)

    def test_performance_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {RiskCategory.PERFORMANCE_DEGRADATION.value: 0.5, **{c.value: 0.0 for c in RiskCategory if c != RiskCategory.PERFORMANCE_DEGRADATION}},
            1, 0,
        )
        assert any("performance" in r.lower() or "benchmark" in r.lower() for r in recs)

    def test_compatibility_recommendation(self):
        recs = self._engine()._build_recommendations(
            MigrationType.LIFT_AND_SHIFT,
            {RiskCategory.COMPATIBILITY.value: 0.6, **{c.value: 0.0 for c in RiskCategory if c != RiskCategory.COMPATIBILITY}},
            1, 0,
        )
        assert any("compatibility" in r.lower() for r in recs)


# ---------------------------------------------------------------------------
# Integration / complex scenarios
# ---------------------------------------------------------------------------


class TestComplexScenarios:
    def test_full_stack_migration(self):
        """Full stack: LB -> Web -> App -> DB with cache."""
        lb = _comp("lb", ComponentType.LOAD_BALANCER)
        web = _comp("web", ComponentType.WEB_SERVER)
        app = _comp("app")
        db = _comp("db", ComponentType.DATABASE)
        cache = _comp("cache", ComponentType.CACHE)
        g = _graph(lb, web, app, db, cache)
        g.add_dependency(Dependency(source_id="lb", target_id="web"))
        g.add_dependency(Dependency(source_id="web", target_id="app"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        g.add_dependency(Dependency(source_id="app", target_id="cache"))

        engine = MigrationRiskEngine()
        r = engine.assess_migration(g, _target(mtype=MigrationType.REPLATFORM))
        assert r.overall_risk_score > 0
        assert len(r.compatibility_gaps) > 0
        assert r.downtime_estimate.planned_minutes > 0
        assert r.rollback_plan.estimated_rollback_minutes > 0
        assert len(r.recommendations) > 0

    def test_waves_respect_dependencies(self):
        """Verify waves respect dependency ordering in a diamond pattern."""
        base = _comp("base", ComponentType.DATABASE)
        left = _comp("left")
        right = _comp("right")
        top = _comp("top", ComponentType.WEB_SERVER)
        g = _graph(base, left, right, top)
        g.add_dependency(Dependency(source_id="left", target_id="base"))
        g.add_dependency(Dependency(source_id="right", target_id="base"))
        g.add_dependency(Dependency(source_id="top", target_id="left"))
        g.add_dependency(Dependency(source_id="top", target_id="right"))

        waves = MigrationRiskEngine().generate_migration_waves(g, _target())
        assert len(waves) >= 3
        assert "base" in waves[0]["components"]
        assert "top" in waves[-1]["components"]

    def test_many_databases_high_risk(self):
        """Many databases should push overall risk high."""
        comps = [_comp(f"db{i}", ComponentType.DATABASE) for i in range(10)]
        g = _graph(*comps)
        r = MigrationRiskEngine().assess_migration(
            g, _target(mtype=MigrationType.REFACTOR)
        )
        assert r.overall_risk_score > 0.5
        assert r.data_risk.data_loss_probability > 0.1

    def test_single_retain_minimal_impact(self):
        g = _graph(_comp("legacy"))
        r = MigrationRiskEngine().assess_migration(
            g, _target(mtype=MigrationType.RETAIN)
        )
        assert r.overall_risk_score < 0.3
        assert r.downtime_estimate.planned_minutes < 10

    def test_mixed_component_types(self):
        comps = [
            _comp("lb", ComponentType.LOAD_BALANCER),
            _comp("web", ComponentType.WEB_SERVER),
            _comp("app", ComponentType.APP_SERVER),
            _comp("db", ComponentType.DATABASE),
            _comp("cache", ComponentType.CACHE),
            _comp("queue", ComponentType.QUEUE),
            _comp("storage", ComponentType.STORAGE),
            _comp("dns", ComponentType.DNS),
            _comp("ext", ComponentType.EXTERNAL_API),
            _comp("custom", ComponentType.CUSTOM),
        ]
        g = _graph(*comps)
        engine = MigrationRiskEngine()

        r = engine.assess_migration(g, _target(mtype=MigrationType.HYBRID))
        assert r.overall_risk_score > 0
        gaps = engine.evaluate_compatibility(g, "aws", "gcp")
        gap_types = {g.gap_type for g in gaps}
        assert "database_engine" in gap_types
        assert "cache_protocol" in gap_types

    def test_assess_then_waves_consistency(self):
        """Assessment and waves should be consistent for the same graph."""
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        t = _target()
        engine = MigrationRiskEngine()
        r = engine.assess_migration(g, t)
        waves = engine.generate_migration_waves(g, t)
        wave_comp_count = sum(len(w["components"]) for w in waves)
        assert wave_comp_count == 3
        assert r.overall_risk_score > 0

    def test_large_graph_performance(self):
        """50 components should not cause issues."""
        comps = [_comp(f"c{i}") for i in range(50)]
        g = _graph(*comps)
        engine = MigrationRiskEngine()
        r = engine.assess_migration(g, _target())
        assert r.overall_risk_score > 0
        assert r.estimated_total_hours > 0
        waves = engine.generate_migration_waves(g, _target())
        assert len(waves) >= 1
