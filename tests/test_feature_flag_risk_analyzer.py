"""Tests for feature_flag_risk_analyzer module — Feature Flag Risk Analyzer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.feature_flag_risk_analyzer import (
    CleanupPriority,
    CleanupRecommendation,
    EvalPerformanceResult,
    FeatureFlagRiskAnalyzer,
    FlagConflictResult,
    FlagCoverageResult,
    FlagDefinition,
    FlagDependencyResult,
    FlagOwnershipReport,
    GradualRolloutRisk,
    KillSwitchAuditResult,
    RiskAnalysisReport,
    RiskFlagType,
    RollbackSafety,
    RollbackSafetyResult,
    StaleFlagResult,
    TechDebtResult,
    _COVERAGE_ACCEPTABLE,
    _COVERAGE_GOOD,
    _DEFAULT_LONG_LIVED_THRESHOLD_DAYS,
    _DEFAULT_STALE_THRESHOLD_DAYS,
    _EVAL_OVERHEAD_PER_FLAG_MS,
    _MAX_FLAGS_BEFORE_LATENCY_CRITICAL,
    _MAX_FLAGS_BEFORE_LATENCY_WARN,
    _ROLLBACK_RISKY_SCORE,
    _ROLLBACK_SAFE_SCORE,
    _TECH_DEBT_HIGH,
    _TECH_DEBT_LOW,
    _TECH_DEBT_MEDIUM,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid: str = "c1", ctype: ComponentType = ComponentType.APP_SERVER) -> Component:
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _flag(
    fid: str = "f1",
    name: str = "",
    ftype: RiskFlagType = RiskFlagType.RELEASE,
    enabled: bool = True,
    rollout: float = 100.0,
    created_days_ago: int = 0,
    last_toggled_days_ago: int | None = None,
    owner: str = "",
    team: str = "",
    dependencies: list[str] | None = None,
    conflicts_with: list[str] | None = None,
    affected_components: list[str] | None = None,
    code_references: int = 0,
    has_unit_tests: bool = False,
    description: str = "",
) -> FlagDefinition:
    now = datetime.now(timezone.utc)
    created_at = now - timedelta(days=created_days_ago)
    last_toggled = (
        now - timedelta(days=last_toggled_days_ago)
        if last_toggled_days_ago is not None
        else None
    )
    return FlagDefinition(
        id=fid,
        name=name or fid,
        flag_type=ftype,
        enabled=enabled,
        rollout_percentage=rollout,
        created_at=created_at,
        last_toggled_at=last_toggled,
        owner=owner,
        team=team,
        dependencies=dependencies or [],
        conflicts_with=conflicts_with or [],
        affected_components=affected_components or [],
        code_references=code_references,
        has_unit_tests=has_unit_tests,
        description=description,
    )


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestRiskFlagType:
    def test_release_value(self):
        assert RiskFlagType.RELEASE.value == "release"

    def test_experiment_value(self):
        assert RiskFlagType.EXPERIMENT.value == "experiment"

    def test_ops_value(self):
        assert RiskFlagType.OPS.value == "ops"

    def test_permission_value(self):
        assert RiskFlagType.PERMISSION.value == "permission"

    def test_kill_switch_value(self):
        assert RiskFlagType.KILL_SWITCH.value == "kill_switch"

    def test_all_members_count(self):
        assert len(RiskFlagType) == 5


class TestCleanupPriority:
    def test_critical_value(self):
        assert CleanupPriority.CRITICAL.value == "critical"

    def test_high_value(self):
        assert CleanupPriority.HIGH.value == "high"

    def test_medium_value(self):
        assert CleanupPriority.MEDIUM.value == "medium"

    def test_low_value(self):
        assert CleanupPriority.LOW.value == "low"

    def test_none_value(self):
        assert CleanupPriority.NONE.value == "none"

    def test_all_members_count(self):
        assert len(CleanupPriority) == 5


class TestRollbackSafety:
    def test_safe_value(self):
        assert RollbackSafety.SAFE.value == "safe"

    def test_risky_value(self):
        assert RollbackSafety.RISKY.value == "risky"

    def test_dangerous_value(self):
        assert RollbackSafety.DANGEROUS.value == "dangerous"

    def test_all_members_count(self):
        assert len(RollbackSafety) == 3


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestFlagDefinition:
    def test_defaults(self):
        f = FlagDefinition(id="x", name="x", flag_type=RiskFlagType.RELEASE)
        assert f.enabled is True
        assert f.rollout_percentage == 100.0
        assert f.owner == ""
        assert f.dependencies == []
        assert f.conflicts_with == []
        assert f.affected_components == []
        assert f.code_references == 0
        assert f.has_unit_tests is False

    def test_custom_fields(self):
        f = _flag(
            fid="f99",
            ftype=RiskFlagType.KILL_SWITCH,
            enabled=False,
            rollout=50.0,
            owner="alice",
            team="infra",
            dependencies=["f1"],
            conflicts_with=["f2"],
            affected_components=["c1", "c2"],
            code_references=5,
            has_unit_tests=True,
        )
        assert f.id == "f99"
        assert f.flag_type == RiskFlagType.KILL_SWITCH
        assert f.enabled is False
        assert f.rollout_percentage == 50.0
        assert f.owner == "alice"
        assert f.team == "infra"
        assert f.dependencies == ["f1"]
        assert f.conflicts_with == ["f2"]
        assert f.affected_components == ["c1", "c2"]
        assert f.code_references == 5
        assert f.has_unit_tests is True

    def test_created_at_is_utc(self):
        f = _flag()
        assert f.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Stale flag detection
# ---------------------------------------------------------------------------


class TestDetectStaleFlags:
    def test_no_flags_returns_empty(self):
        analyzer = FeatureFlagRiskAnalyzer()
        assert analyzer.detect_stale_flags([]) == []

    def test_fresh_flag_not_stale(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(created_days_ago=5)
        result = analyzer.detect_stale_flags([f])
        assert len(result) == 0

    def test_old_flag_detected_as_stale(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(created_days_ago=60)
        result = analyzer.detect_stale_flags([f])
        assert len(result) == 1
        assert result[0].flag_id == "f1"
        assert result[0].days_since_toggle >= 60

    def test_stale_with_custom_threshold(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(created_days_ago=10)
        result = analyzer.detect_stale_flags([f], threshold_days=5)
        assert len(result) == 1

    def test_toggled_recently_not_stale(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(created_days_ago=100, last_toggled_days_ago=2)
        result = analyzer.detect_stale_flags([f])
        assert len(result) == 0

    def test_stale_release_recommendation(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(ftype=RiskFlagType.RELEASE, created_days_ago=60, enabled=True)
        result = analyzer.detect_stale_flags([f])
        assert "permanent" in result[0].recommendation

    def test_stale_experiment_recommendation(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(ftype=RiskFlagType.EXPERIMENT, created_days_ago=60)
        result = analyzer.detect_stale_flags([f])
        assert "conclude" in result[0].recommendation

    def test_stale_kill_switch_recommendation(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(ftype=RiskFlagType.KILL_SWITCH, created_days_ago=60)
        result = analyzer.detect_stale_flags([f])
        assert "verify" in result[0].recommendation.lower()

    def test_stale_ops_recommendation(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(ftype=RiskFlagType.OPS, created_days_ago=60)
        result = analyzer.detect_stale_flags([f])
        assert "review" in result[0].recommendation.lower()

    def test_multiple_stale_flags(self):
        analyzer = FeatureFlagRiskAnalyzer()
        flags = [_flag(fid=f"f{i}", created_days_ago=60) for i in range(5)]
        result = analyzer.detect_stale_flags(flags)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# Dependency analysis
# ---------------------------------------------------------------------------


class TestAnalyzeDependencies:
    def test_no_dependencies(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag()
        results = analyzer.analyze_dependencies([f])
        assert len(results) == 1
        assert results[0].depends_on == []
        assert results[0].depended_by == []
        assert results[0].circular is False
        assert results[0].chain_depth == 0

    def test_simple_dependency(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f1 = _flag(fid="f1", dependencies=["f2"])
        f2 = _flag(fid="f2")
        results = analyzer.analyze_dependencies([f1, f2])
        r1 = next(r for r in results if r.flag_id == "f1")
        r2 = next(r for r in results if r.flag_id == "f2")
        assert r1.depends_on == ["f2"]
        assert r2.depended_by == ["f1"]
        assert r1.chain_depth == 1

    def test_circular_dependency_detected(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f1 = _flag(fid="f1", dependencies=["f2"])
        f2 = _flag(fid="f2", dependencies=["f1"])
        results = analyzer.analyze_dependencies([f1, f2])
        r1 = next(r for r in results if r.flag_id == "f1")
        assert r1.circular is True

    def test_chain_depth_multi_level(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f1 = _flag(fid="f1", dependencies=["f2"])
        f2 = _flag(fid="f2", dependencies=["f3"])
        f3 = _flag(fid="f3")
        results = analyzer.analyze_dependencies([f1, f2, f3])
        r1 = next(r for r in results if r.flag_id == "f1")
        assert r1.chain_depth == 2

    def test_dependency_on_nonexistent_flag_ignored(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(fid="f1", dependencies=["nonexistent"])
        results = analyzer.analyze_dependencies([f])
        assert results[0].depends_on == []


# ---------------------------------------------------------------------------
# Technical debt
# ---------------------------------------------------------------------------


class TestCalculateTechDebt:
    def test_new_flag_low_debt(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(created_days_ago=5, ftype=RiskFlagType.OPS, rollout=50.0)
        results = analyzer.calculate_tech_debt([f])
        assert len(results) == 1
        assert results[0].debt_score < _TECH_DEBT_LOW

    def test_old_release_flag_fully_rolled_out(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(
            ftype=RiskFlagType.RELEASE,
            enabled=True,
            rollout=100.0,
            created_days_ago=200,
        )
        results = analyzer.calculate_tech_debt([f])
        assert results[0].debt_score >= _TECH_DEBT_MEDIUM
        assert any("permanent" in r for r in results[0].reasons)

    def test_old_experiment_high_debt(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(
            ftype=RiskFlagType.EXPERIMENT,
            created_days_ago=200,
            code_references=5,
        )
        results = analyzer.calculate_tech_debt([f])
        assert results[0].debt_score >= _TECH_DEBT_MEDIUM

    def test_no_tests_adds_debt(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(has_unit_tests=False, code_references=5)
        results = analyzer.calculate_tech_debt([f])
        assert any("no unit tests" in r.lower() for r in results[0].reasons)

    def test_many_code_references_adds_debt(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(code_references=20, created_days_ago=120)
        results = analyzer.calculate_tech_debt([f])
        assert any("referenced" in r for r in results[0].reasons)

    def test_cleanup_priority_critical(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(
            ftype=RiskFlagType.RELEASE,
            enabled=True,
            rollout=100.0,
            created_days_ago=365,
            code_references=20,
        )
        results = analyzer.calculate_tech_debt([f])
        assert results[0].cleanup_priority == CleanupPriority.CRITICAL

    def test_cleanup_priority_none_for_new_flag(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(
            created_days_ago=1, code_references=0, has_unit_tests=True,
            ftype=RiskFlagType.OPS, rollout=50.0,
        )
        results = analyzer.calculate_tech_debt([f])
        assert results[0].cleanup_priority == CleanupPriority.NONE


# ---------------------------------------------------------------------------
# Coverage analysis
# ---------------------------------------------------------------------------


class TestAnalyzeCoverage:
    def test_empty_graph_zero_coverage(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph()
        result = analyzer.analyze_coverage(g, [])
        assert result.total_components == 0
        assert result.coverage_percent == 0.0

    def test_full_coverage(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        f = _flag(affected_components=["c1", "c2"])
        result = analyzer.analyze_coverage(g, [f])
        assert result.coverage_percent == 100.0
        assert result.assessment == "good"
        assert result.unflagged_components == []

    def test_partial_coverage(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"), _comp("c3"), _comp("c4"))
        f = _flag(affected_components=["c1"])
        result = analyzer.analyze_coverage(g, [f])
        assert result.coverage_percent == 25.0
        assert result.assessment == "poor"
        assert "c2" in result.unflagged_components

    def test_acceptable_coverage(self):
        analyzer = FeatureFlagRiskAnalyzer()
        comps = [_comp(f"c{i}") for i in range(10)]
        g = _graph(*comps)
        f = _flag(affected_components=[f"c{i}" for i in range(6)])
        result = analyzer.analyze_coverage(g, [f])
        assert result.assessment == "acceptable"

    def test_nonexistent_component_ignored(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        f = _flag(affected_components=["c1", "nonexistent"])
        result = analyzer.analyze_coverage(g, [f])
        assert result.flagged_components == 1


# ---------------------------------------------------------------------------
# Rollback safety
# ---------------------------------------------------------------------------


class TestAssessRollbackSafety:
    def test_simple_flag_safe(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        f = _flag(affected_components=["c1"], has_unit_tests=True)
        results = analyzer.assess_rollback_safety([f], g)
        assert len(results) == 1
        assert results[0].safety == RollbackSafety.SAFE

    def test_many_dependents_risky(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        base = _flag(fid="base", affected_components=["c1"])
        deps = [
            _flag(fid=f"dep{i}", dependencies=["base"])
            for i in range(5)
        ]
        all_flags = [base] + deps
        results = analyzer.assess_rollback_safety(all_flags, g)
        base_result = next(r for r in results if r.flag_id == "base")
        assert base_result.safety in (RollbackSafety.RISKY, RollbackSafety.DANGEROUS)
        assert len(base_result.dependent_flags) == 5

    def test_kill_switch_gets_bonus(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        f = _flag(ftype=RiskFlagType.KILL_SWITCH, affected_components=["c1"])
        results = analyzer.assess_rollback_safety([f], g)
        assert results[0].score >= _ROLLBACK_SAFE_SCORE

    def test_no_tests_reduces_safety(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        f_with = _flag(fid="with", has_unit_tests=True)
        f_without = _flag(fid="without", has_unit_tests=False)
        r_with = analyzer.assess_rollback_safety([f_with], g)
        r_without = analyzer.assess_rollback_safety([f_without], g)
        assert r_with[0].score > r_without[0].score

    def test_experiment_partial_rollout_bonus(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        f = _flag(
            ftype=RiskFlagType.EXPERIMENT,
            rollout=25.0,
            affected_components=["c1"],
        )
        results = analyzer.assess_rollback_safety([f], g)
        assert any("limited blast radius" in r.lower() for r in results[0].reasons)

    def test_many_affected_components_dangerous(self):
        analyzer = FeatureFlagRiskAnalyzer()
        comps = [_comp(f"c{i}") for i in range(20)]
        g = _graph(*comps)
        deps = [_flag(fid=f"dep{i}", dependencies=["f1"]) for i in range(4)]
        f = _flag(
            fid="f1",
            affected_components=[f"c{i}" for i in range(20)],
            has_unit_tests=False,
        )
        all_flags = [f] + deps
        results = analyzer.assess_rollback_safety(all_flags, g)
        f1_result = next(r for r in results if r.flag_id == "f1")
        assert f1_result.safety == RollbackSafety.DANGEROUS


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


class TestDetectConflicts:
    def test_no_conflicts_with_independent_flags(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f1 = _flag(fid="f1")
        f2 = _flag(fid="f2")
        conflicts = analyzer.detect_conflicts([f1, f2])
        assert len(conflicts) == 0

    def test_mutual_exclusion_detected(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f1 = _flag(fid="f1", conflicts_with=["f2"])
        f2 = _flag(fid="f2")
        conflicts = analyzer.detect_conflicts([f1, f2])
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "mutual_exclusion"
        assert conflicts[0].severity == "critical"

    def test_mutual_exclusion_not_triggered_if_one_disabled(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f1 = _flag(fid="f1", conflicts_with=["f2"])
        f2 = _flag(fid="f2", enabled=False)
        conflicts = analyzer.detect_conflicts([f1, f2])
        assert len(conflicts) == 0

    def test_experiment_overlap_detected(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f1 = _flag(
            fid="exp1",
            ftype=RiskFlagType.EXPERIMENT,
            affected_components=["c1", "c2"],
        )
        f2 = _flag(
            fid="exp2",
            ftype=RiskFlagType.EXPERIMENT,
            affected_components=["c2", "c3"],
        )
        conflicts = analyzer.detect_conflicts([f1, f2])
        assert any(c.conflict_type == "experiment_overlap" for c in conflicts)

    def test_circular_dependency_conflict(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f1 = _flag(fid="f1", dependencies=["f2"])
        f2 = _flag(fid="f2", dependencies=["f1"])
        conflicts = analyzer.detect_conflicts([f1, f2])
        assert any(c.conflict_type == "circular_dependency" for c in conflicts)

    def test_no_experiment_overlap_for_different_types(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f1 = _flag(
            fid="f1",
            ftype=RiskFlagType.RELEASE,
            affected_components=["c1"],
        )
        f2 = _flag(
            fid="f2",
            ftype=RiskFlagType.EXPERIMENT,
            affected_components=["c1"],
        )
        conflicts = analyzer.detect_conflicts([f1, f2])
        assert not any(c.conflict_type == "experiment_overlap" for c in conflicts)


# ---------------------------------------------------------------------------
# Gradual rollout risk
# ---------------------------------------------------------------------------


class TestAssessGradualRolloutRisk:
    def test_fully_rolled_out_excluded(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        f = _flag(rollout=100.0)
        results = analyzer.assess_gradual_rollout_risk([f], g)
        assert len(results) == 0

    def test_disabled_flag_excluded(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        f = _flag(rollout=50.0, enabled=False)
        results = analyzer.assess_gradual_rollout_risk([f], g)
        assert len(results) == 0

    def test_partial_rollout_assessed(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        f = _flag(rollout=50.0, affected_components=["c1", "c2"])
        results = analyzer.assess_gradual_rollout_risk([f], g)
        assert len(results) == 1
        assert results[0].risk_level in ("low", "medium", "high")

    def test_very_low_rollout_note(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        f = _flag(rollout=2.0, affected_components=["c1"])
        results = analyzer.assess_gradual_rollout_risk([f], g)
        assert any("low rollout" in r.lower() for r in results[0].recommendations)

    def test_high_rollout_with_many_deps_high_risk(self):
        analyzer = FeatureFlagRiskAnalyzer()
        comps = [_comp(f"c{i}") for i in range(10)]
        g = _graph(*comps)
        f = _flag(
            rollout=80.0,
            affected_components=[f"c{i}" for i in range(10)],
            dependencies=["d1", "d2", "d3"],
            has_unit_tests=False,
        )
        results = analyzer.assess_gradual_rollout_risk([f], g)
        assert results[0].risk_level == "high"


# ---------------------------------------------------------------------------
# Performance impact
# ---------------------------------------------------------------------------


class TestEvaluatePerformanceImpact:
    def test_few_flags_healthy(self):
        analyzer = FeatureFlagRiskAnalyzer()
        flags = [_flag(fid=f"f{i}") for i in range(5)]
        result = analyzer.evaluate_performance_impact(flags)
        assert result.status == "healthy"
        assert result.estimated_latency_ms == 5 * _EVAL_OVERHEAD_PER_FLAG_MS

    def test_many_flags_warning(self):
        analyzer = FeatureFlagRiskAnalyzer()
        flags = [_flag(fid=f"f{i}") for i in range(_MAX_FLAGS_BEFORE_LATENCY_WARN)]
        result = analyzer.evaluate_performance_impact(flags)
        assert result.status == "warning"
        assert len(result.recommendations) > 0

    def test_excessive_flags_critical(self):
        analyzer = FeatureFlagRiskAnalyzer()
        flags = [_flag(fid=f"f{i}") for i in range(_MAX_FLAGS_BEFORE_LATENCY_CRITICAL)]
        result = analyzer.evaluate_performance_impact(flags)
        assert result.status == "critical"

    def test_disabled_flags_not_counted(self):
        analyzer = FeatureFlagRiskAnalyzer()
        flags = [
            _flag(fid=f"f{i}", enabled=False)
            for i in range(_MAX_FLAGS_BEFORE_LATENCY_CRITICAL)
        ]
        result = analyzer.evaluate_performance_impact(flags)
        assert result.status == "healthy"
        assert result.total_flags == 0

    def test_empty_flags_healthy(self):
        analyzer = FeatureFlagRiskAnalyzer()
        result = analyzer.evaluate_performance_impact([])
        assert result.status == "healthy"
        assert result.estimated_latency_ms == 0.0


# ---------------------------------------------------------------------------
# Kill switch audit
# ---------------------------------------------------------------------------


class TestAuditKillSwitches:
    def test_no_kill_switches(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        result = analyzer.audit_kill_switches(g, [])
        assert result.coverage_percent == 0.0
        assert len(result.uncovered_components) == 2
        assert any("no kill switches" in r.lower() for r in result.recommendations)

    def test_full_kill_switch_coverage(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        ks = _flag(
            fid="ks1",
            ftype=RiskFlagType.KILL_SWITCH,
            affected_components=["c1", "c2"],
        )
        result = analyzer.audit_kill_switches(g, [ks])
        assert result.coverage_percent == 100.0
        assert result.uncovered_components == []
        assert "ks1" in result.kill_switches

    def test_partial_kill_switch_coverage(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"), _comp("c3"))
        ks = _flag(
            fid="ks1",
            ftype=RiskFlagType.KILL_SWITCH,
            affected_components=["c1"],
        )
        result = analyzer.audit_kill_switches(g, [ks])
        assert 0 < result.coverage_percent < 100.0
        assert "c2" in result.uncovered_components
        assert "c3" in result.uncovered_components

    def test_non_kill_switch_not_counted(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        f = _flag(
            fid="f1",
            ftype=RiskFlagType.RELEASE,
            affected_components=["c1"],
        )
        result = analyzer.audit_kill_switches(g, [f])
        assert result.coverage_percent == 0.0

    def test_empty_graph(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph()
        result = analyzer.audit_kill_switches(g, [])
        assert result.total_components == 0
        assert result.coverage_percent == 0.0


# ---------------------------------------------------------------------------
# Cleanup recommendations
# ---------------------------------------------------------------------------


class TestGenerateCleanupRecommendations:
    def test_no_recommendations_for_new_flags(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(
            created_days_ago=1, code_references=0, has_unit_tests=True,
            ftype=RiskFlagType.OPS, rollout=50.0,
        )
        results = analyzer.generate_cleanup_recommendations([f])
        assert len(results) == 0

    def test_old_release_flag_gets_recommendation(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(
            ftype=RiskFlagType.RELEASE,
            created_days_ago=200,
            rollout=100.0,
            code_references=5,
        )
        results = analyzer.generate_cleanup_recommendations([f])
        assert len(results) >= 1
        assert "permanent" in results[0].action.lower()

    def test_old_experiment_gets_recommendation(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(
            ftype=RiskFlagType.EXPERIMENT,
            created_days_ago=120,
            code_references=3,
        )
        results = analyzer.generate_cleanup_recommendations([f])
        assert len(results) >= 1
        assert "conclude" in results[0].action.lower()

    def test_disabled_old_flag_recommends_removal(self):
        analyzer = FeatureFlagRiskAnalyzer()
        f = _flag(
            ftype=RiskFlagType.RELEASE,
            enabled=False,
            created_days_ago=200,
            code_references=2,
        )
        results = analyzer.generate_cleanup_recommendations([f])
        assert len(results) >= 1
        assert "remove" in results[0].action.lower()

    def test_sorted_by_priority(self):
        analyzer = FeatureFlagRiskAnalyzer()
        low_debt = _flag(fid="low", created_days_ago=95, code_references=5)
        high_debt = _flag(
            fid="high",
            ftype=RiskFlagType.RELEASE,
            created_days_ago=365,
            rollout=100.0,
            code_references=20,
        )
        results = analyzer.generate_cleanup_recommendations([low_debt, high_debt])
        if len(results) >= 2:
            priorities = [r.priority for r in results]
            priority_order = list(CleanupPriority)
            assert priority_order.index(priorities[0]) <= priority_order.index(priorities[1])

    def test_effort_estimation(self):
        analyzer = FeatureFlagRiskAnalyzer()
        trivial = _flag(fid="t", created_days_ago=200, code_references=0)
        small = _flag(fid="s", created_days_ago=200, code_references=2)
        medium = _flag(fid="m", created_days_ago=200, code_references=8)
        large = _flag(fid="l", created_days_ago=200, code_references=15)
        results = analyzer.generate_cleanup_recommendations(
            [trivial, small, medium, large]
        )
        efforts = {r.flag_id: r.estimated_effort for r in results}
        if "t" in efforts:
            assert efforts["t"] == "trivial"
        if "l" in efforts:
            assert efforts["l"] == "large"


# ---------------------------------------------------------------------------
# Ownership mapping
# ---------------------------------------------------------------------------


class TestMapOwnership:
    def test_all_owned(self):
        analyzer = FeatureFlagRiskAnalyzer()
        flags = [
            _flag(fid="f1", owner="alice", team="infra"),
            _flag(fid="f2", owner="bob", team="infra"),
        ]
        report = analyzer.map_ownership(flags)
        assert report.total_flags == 2
        assert report.unowned_flags == []
        assert "alice" in report.owners
        assert "bob" in report.owners
        assert "infra" in report.teams

    def test_unowned_flags(self):
        analyzer = FeatureFlagRiskAnalyzer()
        flags = [
            _flag(fid="f1", owner=""),
            _flag(fid="f2", owner="alice"),
        ]
        report = analyzer.map_ownership(flags)
        assert report.unowned_flags == ["f1"]
        assert any("no assigned owner" in r for r in report.recommendations)

    def test_overloaded_owner(self):
        analyzer = FeatureFlagRiskAnalyzer()
        flags = [
            _flag(fid=f"f{i}", owner="overloaded")
            for i in range(15)
        ]
        report = analyzer.map_ownership(flags)
        assert any("redistributing" in r for r in report.recommendations)

    def test_empty_flags(self):
        analyzer = FeatureFlagRiskAnalyzer()
        report = analyzer.map_ownership([])
        assert report.total_flags == 0
        assert report.unowned_flags == []


# ---------------------------------------------------------------------------
# Risk report (integration)
# ---------------------------------------------------------------------------


class TestGenerateRiskReport:
    def test_empty_system_low_risk(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph()
        report = analyzer.generate_risk_report(g, [])
        assert report.total_flags == 0
        assert report.risk_level == "low"
        assert report.overall_risk_score == 0.0

    def test_healthy_system(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        ks = _flag(
            fid="ks",
            ftype=RiskFlagType.KILL_SWITCH,
            affected_components=["c1", "c2"],
            created_days_ago=5,
        )
        release = _flag(
            fid="rel",
            ftype=RiskFlagType.RELEASE,
            created_days_ago=5,
            rollout=50.0,
        )
        report = analyzer.generate_risk_report(g, [ks, release])
        assert report.risk_level in ("low", "medium")

    def test_unhealthy_system_high_risk(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        # Many stale, conflicting, high-debt flags
        flags = []
        for i in range(10):
            flags.append(
                _flag(
                    fid=f"f{i}",
                    ftype=RiskFlagType.RELEASE,
                    created_days_ago=365,
                    rollout=100.0,
                    code_references=20,
                    conflicts_with=[f"f{(i + 1) % 10}"],
                    affected_components=["c1"],
                )
            )
        report = analyzer.generate_risk_report(g, flags)
        assert report.risk_level in ("high", "critical")
        assert report.overall_risk_score > 40.0
        assert len(report.top_recommendations) > 0

    def test_report_includes_stale_count(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        stale = _flag(created_days_ago=60)
        report = analyzer.generate_risk_report(g, [stale])
        assert report.stale_flags >= 1

    def test_report_includes_conflict_count(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        f1 = _flag(fid="f1", conflicts_with=["f2"], affected_components=["c1"])
        f2 = _flag(fid="f2", affected_components=["c1"])
        report = analyzer.generate_risk_report(g, [f1, f2])
        assert report.conflict_count >= 1

    def test_report_kill_switch_coverage(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        ks = _flag(
            fid="ks",
            ftype=RiskFlagType.KILL_SWITCH,
            affected_components=["c1"],
            created_days_ago=5,
        )
        report = analyzer.generate_risk_report(g, [ks])
        assert report.kill_switch_coverage_percent == 50.0

    def test_report_perf_recommendations_included(self):
        analyzer = FeatureFlagRiskAnalyzer()
        g = _graph(_comp("c1"))
        flags = [
            _flag(fid=f"f{i}", created_days_ago=5)
            for i in range(_MAX_FLAGS_BEFORE_LATENCY_WARN)
        ]
        report = analyzer.generate_risk_report(g, flags)
        assert any("flag count" in r.lower() for r in report.top_recommendations)


# ---------------------------------------------------------------------------
# Constants verification
# ---------------------------------------------------------------------------


class TestConstants:
    def test_stale_threshold_positive(self):
        assert _DEFAULT_STALE_THRESHOLD_DAYS > 0

    def test_long_lived_threshold_gt_stale(self):
        assert _DEFAULT_LONG_LIVED_THRESHOLD_DAYS > _DEFAULT_STALE_THRESHOLD_DAYS

    def test_latency_warn_lt_critical(self):
        assert _MAX_FLAGS_BEFORE_LATENCY_WARN < _MAX_FLAGS_BEFORE_LATENCY_CRITICAL

    def test_rollback_safe_gt_risky(self):
        assert _ROLLBACK_SAFE_SCORE > _ROLLBACK_RISKY_SCORE

    def test_tech_debt_ordering(self):
        assert _TECH_DEBT_LOW < _TECH_DEBT_MEDIUM < _TECH_DEBT_HIGH

    def test_coverage_ordering(self):
        assert _COVERAGE_ACCEPTABLE < _COVERAGE_GOOD

    def test_eval_overhead_positive(self):
        assert _EVAL_OVERHEAD_PER_FLAG_MS > 0
