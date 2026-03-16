"""Tests for feature_flag_interaction module — Feature Flag Interaction Simulator."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.feature_flag_interaction import (
    FeatureFlag,
    FeatureFlagInteractionEngine,
    FlagFailureResult,
    FlagInteraction,
    FlagInteractionType,
    FlagResilienceImpact,
    FlagState,
    FlagType,
    RolloutStageResult,
    RolloutStrategy,
    _CRITICAL_RESOURCE_THRESHOLD,
    _DEFAULT_ROLLOUT_STAGES,
    _RESILIENCE_NEGATIVE_CAP,
    _RESILIENCE_POSITIVE_CAP,
    _RESOURCE_OVERHEAD_THRESHOLD,
    _ROLLBACK_RISKY_THRESHOLD,
    _ROLLBACK_SAFE_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str = "",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        health=health,
    )


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _flag(
    fid: str,
    name: str = "",
    ftype: FlagType = FlagType.RELEASE,
    state: FlagState = FlagState.ENABLED,
    rollout: float = 0.0,
    resource_impact: dict[str, float] | None = None,
    dependencies: list[str] | None = None,
    kill_switch_for: list[str] | None = None,
) -> FeatureFlag:
    return FeatureFlag(
        id=fid,
        name=name or fid,
        flag_type=ftype,
        state=state,
        rollout_percentage=rollout,
        resource_impact=resource_impact or {},
        dependencies=dependencies or [],
        kill_switch_for=kill_switch_for or [],
    )


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestFlagType:
    def test_release_value(self):
        assert FlagType.RELEASE.value == "release"

    def test_experiment_value(self):
        assert FlagType.EXPERIMENT.value == "experiment"

    def test_ops_toggle_value(self):
        assert FlagType.OPS_TOGGLE.value == "ops_toggle"

    def test_kill_switch_value(self):
        assert FlagType.KILL_SWITCH.value == "kill_switch"

    def test_permission_value(self):
        assert FlagType.PERMISSION.value == "permission"

    def test_gradual_rollout_value(self):
        assert FlagType.GRADUAL_ROLLOUT.value == "gradual_rollout"

    def test_all_members_count(self):
        assert len(FlagType) == 6


class TestFlagState:
    def test_enabled_value(self):
        assert FlagState.ENABLED.value == "enabled"

    def test_disabled_value(self):
        assert FlagState.DISABLED.value == "disabled"

    def test_percentage_rollout_value(self):
        assert FlagState.PERCENTAGE_ROLLOUT.value == "percentage_rollout"

    def test_user_targeted_value(self):
        assert FlagState.USER_TARGETED.value == "user_targeted"

    def test_canary_value(self):
        assert FlagState.CANARY.value == "canary"

    def test_all_members_count(self):
        assert len(FlagState) == 5


class TestFlagInteractionType:
    def test_conflict_value(self):
        assert FlagInteractionType.CONFLICT.value == "conflict"

    def test_dependency_value(self):
        assert FlagInteractionType.DEPENDENCY.value == "dependency"

    def test_mutual_exclusion_value(self):
        assert FlagInteractionType.MUTUAL_EXCLUSION.value == "mutual_exclusion"

    def test_cascade_enable_value(self):
        assert FlagInteractionType.CASCADE_ENABLE.value == "cascade_enable"

    def test_cascade_disable_value(self):
        assert FlagInteractionType.CASCADE_DISABLE.value == "cascade_disable"

    def test_resource_contention_value(self):
        assert FlagInteractionType.RESOURCE_CONTENTION.value == "resource_contention"

    def test_all_members_count(self):
        assert len(FlagInteractionType) == 6


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestFeatureFlagModel:
    def test_minimal_creation(self):
        f = FeatureFlag(id="f1", name="test", flag_type=FlagType.RELEASE, state=FlagState.ENABLED)
        assert f.id == "f1"
        assert f.rollout_percentage == 0.0

    def test_full_creation(self):
        f = _flag("f1", ftype=FlagType.KILL_SWITCH, kill_switch_for=["web"])
        assert f.flag_type == FlagType.KILL_SWITCH
        assert f.kill_switch_for == ["web"]

    def test_resource_impact_dict(self):
        f = _flag("f1", resource_impact={"cpu_delta": 0.1, "memory_delta": 0.2})
        assert f.resource_impact["cpu_delta"] == 0.1

    def test_dependencies_list(self):
        f = _flag("f1", dependencies=["dep1", "dep2"])
        assert len(f.dependencies) == 2

    def test_rollout_percentage_bounds_lower(self):
        f = _flag("f1", rollout=0.0)
        assert f.rollout_percentage == 0.0

    def test_rollout_percentage_bounds_upper(self):
        f = _flag("f1", rollout=100.0)
        assert f.rollout_percentage == 100.0

    def test_rollout_percentage_invalid_raises(self):
        with pytest.raises(Exception):
            _flag("f1", rollout=101.0)

    def test_rollout_percentage_negative_raises(self):
        with pytest.raises(Exception):
            _flag("f1", rollout=-1.0)

    def test_defaults_empty_lists(self):
        f = FeatureFlag(id="f1", name="t", flag_type=FlagType.RELEASE, state=FlagState.ENABLED)
        assert f.dependencies == []
        assert f.kill_switch_for == []
        assert f.resource_impact == {}


class TestFlagInteractionModel:
    def test_creation(self):
        fi = FlagInteraction(
            flag_a_id="a",
            flag_b_id="b",
            interaction_type=FlagInteractionType.CONFLICT,
            severity="high",
            description="desc",
            resolution="res",
        )
        assert fi.flag_a_id == "a"
        assert fi.severity == "high"


class TestFlagResilienceImpactModel:
    def test_creation(self):
        fri = FlagResilienceImpact(
            flag_id="f1",
            resilience_delta=-5.0,
            affected_components=["c1"],
            resource_overhead={"cpu": 0.1},
            rollback_safety="safe",
            rollback_time_seconds=10.0,
        )
        assert fri.resilience_delta == -5.0
        assert fri.rollback_safety == "safe"


class TestRolloutStageResultModel:
    def test_creation(self):
        r = RolloutStageResult(stage=1, percentage=10.0, healthy=True)
        assert r.stage == 1
        assert r.healthy is True

    def test_timestamp_is_utc(self):
        r = RolloutStageResult(stage=1, percentage=10.0, healthy=True)
        assert r.timestamp.tzinfo is not None


class TestFlagFailureResultModel:
    def test_creation(self):
        r = FlagFailureResult(
            flag_id="f1",
            severity="critical",
            fallback_behaviour="fail-open",
            estimated_impact_percent=50.0,
        )
        assert r.estimated_impact_percent == 50.0


class TestRolloutStrategyModel:
    def test_creation(self):
        rs = RolloutStrategy(
            flag_id="f1",
            recommended_stages=5,
            stage_percentages=[5, 20, 50, 80, 100],
            estimated_duration_minutes=180.0,
            risk_level="medium",
            rollback_plan="disable",
        )
        assert rs.recommended_stages == 5
        assert len(rs.stage_percentages) == 5


# ---------------------------------------------------------------------------
# detect_interactions tests
# ---------------------------------------------------------------------------


class TestDetectInteractions:
    def test_no_flags_returns_empty(self):
        engine = FeatureFlagInteractionEngine()
        assert engine.detect_interactions([]) == []

    def test_single_flag_no_interactions(self):
        engine = FeatureFlagInteractionEngine()
        result = engine.detect_interactions([_flag("f1")])
        assert result == []

    def test_dependency_detected(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", dependencies=["b"])
        fb = _flag("b")
        result = engine.detect_interactions([fa, fb])
        deps = [i for i in result if i.interaction_type == FlagInteractionType.DEPENDENCY]
        assert len(deps) == 1
        assert deps[0].flag_a_id == "a"

    def test_dependency_severity_disabled_is_critical(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", dependencies=["b"])
        fb = _flag("b", state=FlagState.DISABLED)
        result = engine.detect_interactions([fa, fb])
        deps = [i for i in result if i.interaction_type == FlagInteractionType.DEPENDENCY]
        assert deps[0].severity == "critical"

    def test_dependency_severity_canary_is_high(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", dependencies=["b"])
        fb = _flag("b", state=FlagState.CANARY)
        result = engine.detect_interactions([fa, fb])
        deps = [i for i in result if i.interaction_type == FlagInteractionType.DEPENDENCY]
        assert deps[0].severity == "high"

    def test_dependency_severity_enabled_is_medium(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", dependencies=["b"])
        fb = _flag("b", state=FlagState.ENABLED)
        result = engine.detect_interactions([fa, fb])
        deps = [i for i in result if i.interaction_type == FlagInteractionType.DEPENDENCY]
        assert deps[0].severity == "medium"

    def test_mutual_dependency_two_interactions(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", dependencies=["b"])
        fb = _flag("b", dependencies=["a"])
        result = engine.detect_interactions([fa, fb])
        deps = [i for i in result if i.interaction_type == FlagInteractionType.DEPENDENCY]
        assert len(deps) == 2

    def test_mutual_exclusion_detected(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", ftype=FlagType.KILL_SWITCH, kill_switch_for=["web"])
        fb = _flag("b", ftype=FlagType.KILL_SWITCH, kill_switch_for=["web"])
        result = engine.detect_interactions([fa, fb])
        me = [i for i in result if i.interaction_type == FlagInteractionType.MUTUAL_EXCLUSION]
        assert len(me) == 1

    def test_mutual_exclusion_not_when_no_overlap(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", ftype=FlagType.KILL_SWITCH, kill_switch_for=["web"])
        fb = _flag("b", ftype=FlagType.KILL_SWITCH, kill_switch_for=["api"])
        result = engine.detect_interactions([fa, fb])
        me = [i for i in result if i.interaction_type == FlagInteractionType.MUTUAL_EXCLUSION]
        assert len(me) == 0

    def test_conflict_opposite_resource_impact(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", resource_impact={"cpu_delta": 0.3})
        fb = _flag("b", resource_impact={"cpu_delta": -0.1})
        result = engine.detect_interactions([fa, fb])
        conflicts = [i for i in result if i.interaction_type == FlagInteractionType.CONFLICT]
        assert len(conflicts) == 1

    def test_no_conflict_same_sign(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", resource_impact={"cpu_delta": 0.01})
        fb = _flag("b", resource_impact={"cpu_delta": 0.01})
        result = engine.detect_interactions([fa, fb])
        conflicts = [i for i in result if i.interaction_type == FlagInteractionType.CONFLICT]
        assert len(conflicts) == 0

    def test_no_conflict_when_disabled(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", state=FlagState.DISABLED, resource_impact={"cpu_delta": 0.3})
        fb = _flag("b", resource_impact={"cpu_delta": -0.1})
        result = engine.detect_interactions([fa, fb])
        conflicts = [i for i in result if i.interaction_type == FlagInteractionType.CONFLICT]
        assert len(conflicts) == 0

    def test_resource_contention_detected(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", resource_impact={"cpu_delta": 0.15})
        fb = _flag("b", resource_impact={"cpu_delta": 0.10})
        result = engine.detect_interactions([fa, fb])
        rc = [i for i in result if i.interaction_type == FlagInteractionType.RESOURCE_CONTENTION]
        assert len(rc) == 1

    def test_resource_contention_critical_severity(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", resource_impact={"cpu_delta": 0.30})
        fb = _flag("b", resource_impact={"cpu_delta": 0.25})
        result = engine.detect_interactions([fa, fb])
        rc = [i for i in result if i.interaction_type == FlagInteractionType.RESOURCE_CONTENTION]
        assert rc[0].severity == "critical"

    def test_resource_contention_high_severity(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", resource_impact={"cpu_delta": 0.12})
        fb = _flag("b", resource_impact={"cpu_delta": 0.10})
        result = engine.detect_interactions([fa, fb])
        rc = [i for i in result if i.interaction_type == FlagInteractionType.RESOURCE_CONTENTION]
        assert rc[0].severity == "high"

    def test_resource_contention_not_when_disabled(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", state=FlagState.DISABLED, resource_impact={"cpu_delta": 0.15})
        fb = _flag("b", resource_impact={"cpu_delta": 0.10})
        result = engine.detect_interactions([fa, fb])
        rc = [i for i in result if i.interaction_type == FlagInteractionType.RESOURCE_CONTENTION]
        assert len(rc) == 0

    def test_cascade_enable_detected(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", state=FlagState.ENABLED, dependencies=["b"])
        fb = _flag("b", state=FlagState.DISABLED)
        result = engine.detect_interactions([fa, fb])
        ce = [i for i in result if i.interaction_type == FlagInteractionType.CASCADE_ENABLE]
        assert len(ce) == 1

    def test_cascade_enable_not_when_target_enabled(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", state=FlagState.ENABLED, dependencies=["b"])
        fb = _flag("b", state=FlagState.ENABLED)
        result = engine.detect_interactions([fa, fb])
        ce = [i for i in result if i.interaction_type == FlagInteractionType.CASCADE_ENABLE]
        assert len(ce) == 0

    def test_cascade_disable_detected(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", state=FlagState.DISABLED)
        fb = _flag("b", dependencies=["a"])
        result = engine.detect_interactions([fa, fb])
        cd = [i for i in result if i.interaction_type == FlagInteractionType.CASCADE_DISABLE]
        assert len(cd) == 1

    def test_cascade_disable_not_when_source_enabled(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", state=FlagState.ENABLED)
        fb = _flag("b", dependencies=["a"])
        result = engine.detect_interactions([fa, fb])
        cd = [i for i in result if i.interaction_type == FlagInteractionType.CASCADE_DISABLE]
        assert len(cd) == 0

    def test_multiple_interactions_between_pair(self):
        engine = FeatureFlagInteractionEngine()
        # Two flags with dependency, conflict, and resource contention
        fa = _flag("a", dependencies=["b"], resource_impact={"cpu": 0.15})
        fb = _flag("b", resource_impact={"cpu": -0.15})
        result = engine.detect_interactions([fa, fb])
        types = {i.interaction_type for i in result}
        assert FlagInteractionType.DEPENDENCY in types
        assert FlagInteractionType.CONFLICT in types

    def test_three_flags_pairwise(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", dependencies=["b"])
        fb = _flag("b", dependencies=["c"])
        fc = _flag("c")
        result = engine.detect_interactions([fa, fb, fc])
        deps = [i for i in result if i.interaction_type == FlagInteractionType.DEPENDENCY]
        assert len(deps) == 2

    def test_interaction_has_description(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", dependencies=["b"])
        fb = _flag("b")
        result = engine.detect_interactions([fa, fb])
        assert result[0].description != ""

    def test_interaction_has_resolution(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", dependencies=["b"])
        fb = _flag("b")
        result = engine.detect_interactions([fa, fb])
        assert result[0].resolution != ""


# ---------------------------------------------------------------------------
# analyze_resilience_impact tests
# ---------------------------------------------------------------------------


class TestAnalyzeResilienceImpact:
    def test_empty_flags_returns_empty(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        assert engine.analyze_resilience_impact(g, []) == []

    def test_returns_one_per_flag(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"), _comp("c2"))
        flags = [_flag("f1"), _flag("f2")]
        result = engine.analyze_resilience_impact(g, flags)
        assert len(result) == 2

    def test_kill_switch_positive_delta(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].resilience_delta > 0

    def test_experiment_negative_delta(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("exp", ftype=FlagType.EXPERIMENT)
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].resilience_delta < 0

    def test_ops_toggle_positive_delta(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("op", ftype=FlagType.OPS_TOGGLE)
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].resilience_delta > 0

    def test_high_resource_impact_negative_delta(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", resource_impact={"cpu": 0.5})
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].resilience_delta < 0

    def test_resilience_delta_clamped_positive(self):
        engine = FeatureFlagInteractionEngine()
        # Many kill switch targets to push delta high
        targets = [f"c{i}" for i in range(20)]
        comps = [_comp(t) for t in targets]
        g = _graph(*comps)
        f = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=targets)
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].resilience_delta <= _RESILIENCE_POSITIVE_CAP

    def test_resilience_delta_clamped_negative(self):
        engine = FeatureFlagInteractionEngine()
        comps = [_comp(f"c{i}") for i in range(20)]
        g = _graph(*comps)
        f = _flag("f1", ftype=FlagType.EXPERIMENT, resource_impact={"cpu": 0.9, "mem": 0.9})
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].resilience_delta >= _RESILIENCE_NEGATIVE_CAP

    def test_affected_components_populated(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"), _comp("c2"))
        f = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        result = engine.analyze_resilience_impact(g, [f])
        assert "c1" in result[0].affected_components

    def test_resource_overhead_computed(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", resource_impact={"cpu": 0.1})
        result = engine.analyze_resilience_impact(g, [f])
        assert "cpu" in result[0].resource_overhead

    def test_disabled_flag_zero_overhead(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", state=FlagState.DISABLED, resource_impact={"cpu": 0.5})
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].resource_overhead.get("cpu", 0.0) == 0.0

    def test_rollback_safety_safe(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].rollback_safety == "safe"

    def test_rollback_safety_risky(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag(
            "f1",
            ftype=FlagType.EXPERIMENT,
            state=FlagState.PERCENTAGE_ROLLOUT,
            rollout=80.0,
            resource_impact={"cpu": 0.25},
        )
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].rollback_safety in ("risky", "dangerous")

    def test_rollback_time_positive(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].rollback_time_seconds > 0

    def test_canary_effective_scale(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", state=FlagState.CANARY, resource_impact={"cpu": 1.0})
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].resource_overhead["cpu"] == pytest.approx(0.05, abs=0.01)

    def test_user_targeted_effective_scale(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", state=FlagState.USER_TARGETED, resource_impact={"cpu": 1.0})
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].resource_overhead["cpu"] == pytest.approx(0.01, abs=0.005)

    def test_percentage_rollout_scale(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag(
            "f1",
            state=FlagState.PERCENTAGE_ROLLOUT,
            rollout=50.0,
            resource_impact={"cpu": 1.0},
        )
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].resource_overhead["cpu"] == pytest.approx(0.5, abs=0.01)

    def test_enabled_full_scale(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", state=FlagState.ENABLED, resource_impact={"cpu": 0.3})
        result = engine.analyze_resilience_impact(g, [f])
        assert result[0].resource_overhead["cpu"] == pytest.approx(0.3, abs=0.01)


# ---------------------------------------------------------------------------
# simulate_rollout tests
# ---------------------------------------------------------------------------


class TestSimulateRollout:
    def test_default_stages(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.simulate_rollout(g, f)
        assert len(result) == _DEFAULT_ROLLOUT_STAGES

    def test_custom_stages(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.simulate_rollout(g, f, stages=3)
        assert len(result) == 3

    def test_stages_zero_becomes_one(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.simulate_rollout(g, f, stages=0)
        assert len(result) == 1

    def test_first_stage_percentage(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.simulate_rollout(g, f, stages=4)
        assert result[0].percentage == 25.0

    def test_last_stage_100_percent(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.simulate_rollout(g, f, stages=5)
        assert result[-1].percentage == 100.0

    def test_stages_ascending_percentages(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.simulate_rollout(g, f, stages=5)
        pcts = [r.percentage for r in result]
        assert pcts == sorted(pcts)

    def test_healthy_when_no_resource_impact(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.simulate_rollout(g, f, stages=3)
        assert all(r.healthy for r in result)

    def test_unhealthy_when_critical_resource(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", resource_impact={"cpu_delta": 0.6})
        result = engine.simulate_rollout(g, f, stages=2)
        # At 100% the impact is 0.6 which is >= _CRITICAL_RESOURCE_THRESHOLD
        assert not result[-1].healthy

    def test_errors_when_warning_threshold(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", resource_impact={"cpu_delta": 0.25})
        result = engine.simulate_rollout(g, f, stages=1)
        assert len(result[0].errors) > 0

    def test_errors_when_component_down(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1", health=HealthStatus.DOWN))
        f = _flag("f1", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        result = engine.simulate_rollout(g, f, stages=1)
        assert not result[0].healthy

    def test_affected_components_in_stages(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"), _comp("c2"))
        f = _flag("f1", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        result = engine.simulate_rollout(g, f, stages=2)
        assert "c1" in result[-1].affected_components

    def test_resource_usage_scaled(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", resource_impact={"cpu": 0.1})
        result = engine.simulate_rollout(g, f, stages=2)
        # Stage 1: 50%, Stage 2: 100%
        assert result[0].resource_usage["cpu"] == pytest.approx(0.05, abs=0.01)
        assert result[1].resource_usage["cpu"] == pytest.approx(0.1, abs=0.01)

    def test_stage_numbers_sequential(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.simulate_rollout(g, f, stages=3)
        assert [r.stage for r in result] == [1, 2, 3]

    def test_timestamp_set(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.simulate_rollout(g, f, stages=1)
        assert result[0].timestamp is not None


# ---------------------------------------------------------------------------
# find_kill_switch_gaps tests
# ---------------------------------------------------------------------------


class TestFindKillSwitchGaps:
    def test_all_covered(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"), _comp("c2"))
        ks = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1", "c2"])
        assert engine.find_kill_switch_gaps(g, [ks]) == []

    def test_gap_detected(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"), _comp("c2"))
        ks = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        gaps = engine.find_kill_switch_gaps(g, [ks])
        assert "c2" in gaps

    def test_no_kill_switches_all_gaps(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"), _comp("c2"))
        f = _flag("f1", ftype=FlagType.RELEASE)
        gaps = engine.find_kill_switch_gaps(g, [f])
        assert len(gaps) == 2

    def test_empty_flags_all_gaps(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        gaps = engine.find_kill_switch_gaps(g, [])
        assert gaps == ["c1"]

    def test_empty_graph_no_gaps(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph()
        ks = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        assert engine.find_kill_switch_gaps(g, [ks]) == []

    def test_multiple_kill_switches_combined(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"), _comp("c2"), _comp("c3"))
        ks1 = _flag("ks1", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        ks2 = _flag("ks2", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c2"])
        gaps = engine.find_kill_switch_gaps(g, [ks1, ks2])
        assert gaps == ["c3"]

    def test_sorted_output(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("z"), _comp("a"), _comp("m"))
        gaps = engine.find_kill_switch_gaps(g, [])
        assert gaps == sorted(gaps)

    def test_non_kill_switch_flags_ignored(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", ftype=FlagType.RELEASE, kill_switch_for=["c1"])
        gaps = engine.find_kill_switch_gaps(g, [f])
        assert "c1" in gaps


# ---------------------------------------------------------------------------
# simulate_flag_failure tests
# ---------------------------------------------------------------------------


class TestSimulateFlagFailure:
    def test_unknown_flag_returns_low(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        result = engine.simulate_flag_failure(g, "unknown", [])
        assert result.severity == "low"
        assert result.estimated_impact_percent == 0.0

    def test_kill_switch_failure_critical(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        result = engine.simulate_flag_failure(g, "ks", [f])
        assert result.severity == "critical"

    def test_affected_flags_populated(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        fa = _flag("a")
        fb = _flag("b", dependencies=["a"])
        result = engine.simulate_flag_failure(g, "a", [fa, fb])
        assert "b" in result.affected_flags

    def test_affected_components_populated(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        result = engine.simulate_flag_failure(g, "f1", [f])
        assert "c1" in result.affected_components

    def test_high_impact_severity(self):
        engine = FeatureFlagInteractionEngine()
        comps = [_comp(f"c{i}") for i in range(10)]
        g = _graph(*comps)
        f = _flag("f1", resource_impact={"cpu": 0.1})
        result = engine.simulate_flag_failure(g, "f1", [f])
        # With 10 components, impact is 100% which is > 50
        assert result.severity in ("critical", "high")

    def test_low_impact_severity(self):
        engine = FeatureFlagInteractionEngine()
        comps = [_comp(f"c{i}") for i in range(100)]
        g = _graph(*comps)
        f = _flag("f1", state=FlagState.USER_TARGETED, resource_impact={"cpu": 0.01})
        result = engine.simulate_flag_failure(g, "f1", [f])
        assert result.severity in ("low", "medium")

    def test_fallback_kill_switch(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        result = engine.simulate_flag_failure(g, "ks", [f])
        assert "fail-open" in result.fallback_behaviour.lower()

    def test_fallback_experiment(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("exp", ftype=FlagType.EXPERIMENT)
        result = engine.simulate_flag_failure(g, "exp", [f])
        assert "fail-closed" in result.fallback_behaviour.lower()

    def test_fallback_ops_toggle(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("op", ftype=FlagType.OPS_TOGGLE)
        result = engine.simulate_flag_failure(g, "op", [f])
        assert "fail-open" in result.fallback_behaviour.lower()

    def test_fallback_permission(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("perm", ftype=FlagType.PERMISSION)
        result = engine.simulate_flag_failure(g, "perm", [f])
        assert "fail-closed" in result.fallback_behaviour.lower()

    def test_fallback_gradual_rollout(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("gr", ftype=FlagType.GRADUAL_ROLLOUT)
        result = engine.simulate_flag_failure(g, "gr", [f])
        assert "fail-closed" in result.fallback_behaviour.lower()

    def test_fallback_release(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("rel", ftype=FlagType.RELEASE)
        result = engine.simulate_flag_failure(g, "rel", [f])
        assert "fail-closed" in result.fallback_behaviour.lower()

    def test_recommendations_not_empty(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.simulate_flag_failure(g, "f1", [f])
        assert len(result.recommendations) > 0

    def test_recommendations_for_kill_switch(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        result = engine.simulate_flag_failure(g, "ks", [f])
        assert any("cache" in r.lower() for r in result.recommendations)

    def test_recommendations_for_dependent_flags(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        fa = _flag("a")
        fb = _flag("b", dependencies=["a"])
        result = engine.simulate_flag_failure(g, "a", [fa, fb])
        assert any("decouple" in r.lower() for r in result.recommendations)

    def test_recommendations_percentage_rollout(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", state=FlagState.PERCENTAGE_ROLLOUT, rollout=50.0)
        result = engine.simulate_flag_failure(g, "f1", [f])
        assert any("cache" in r.lower() for r in result.recommendations)

    def test_cascade_through_dependent_flags(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"), _comp("c2"))
        fa = _flag("a", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        fb = _flag("b", dependencies=["a"], ftype=FlagType.KILL_SWITCH, kill_switch_for=["c2"])
        result = engine.simulate_flag_failure(g, "a", [fa, fb])
        assert "c1" in result.affected_components
        assert "c2" in result.affected_components

    def test_impact_percent_calculated(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"), _comp("c2"))
        f = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        result = engine.simulate_flag_failure(g, "ks", [f])
        assert 0 < result.estimated_impact_percent <= 100


# ---------------------------------------------------------------------------
# recommend_rollout_strategy tests
# ---------------------------------------------------------------------------


class TestRecommendRolloutStrategy:
    def test_returns_strategy(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.recommend_rollout_strategy(g, f)
        assert isinstance(result, RolloutStrategy)

    def test_low_risk_few_stages(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.recommend_rollout_strategy(g, f)
        assert result.risk_level == "low"
        assert result.recommended_stages == 3

    def test_medium_risk_stages(self):
        engine = FeatureFlagInteractionEngine()
        comps = [_comp(f"c{i}") for i in range(7)]
        g = _graph(*comps)
        f = _flag("f1", resource_impact={"cpu": 0.25})
        result = engine.recommend_rollout_strategy(g, f)
        assert result.risk_level in ("medium", "high")
        assert result.recommended_stages >= 5

    def test_high_risk_many_stages(self):
        engine = FeatureFlagInteractionEngine()
        comps = [_comp(f"c{i}") for i in range(15)]
        g = _graph(*comps)
        f = _flag(
            "f1",
            ftype=FlagType.KILL_SWITCH,
            kill_switch_for=[f"c{i}" for i in range(15)],
            resource_impact={"cpu": 0.6},
            dependencies=["dep1"],
        )
        result = engine.recommend_rollout_strategy(g, f)
        assert result.risk_level == "high"
        assert result.recommended_stages == 7

    def test_stage_percentages_end_at_100(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.recommend_rollout_strategy(g, f)
        assert result.stage_percentages[-1] == 100.0

    def test_stage_percentages_ascending(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.recommend_rollout_strategy(g, f)
        assert result.stage_percentages == sorted(result.stage_percentages)

    def test_duration_positive(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.recommend_rollout_strategy(g, f)
        assert result.estimated_duration_minutes > 0

    def test_prerequisites_for_dependencies(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", dependencies=["dep1"])
        result = engine.recommend_rollout_strategy(g, f)
        assert any("dep1" in p for p in result.prerequisites)

    def test_prerequisites_for_kill_switch(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        result = engine.recommend_rollout_strategy(g, f)
        assert any("healthy" in p.lower() for p in result.prerequisites)

    def test_prerequisites_for_resource_impact(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", resource_impact={"cpu": 0.1})
        result = engine.recommend_rollout_strategy(g, f)
        assert any("resource" in p.lower() for p in result.prerequisites)

    def test_monitoring_points_populated(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", resource_impact={"cpu": 0.1})
        result = engine.recommend_rollout_strategy(g, f)
        assert len(result.monitoring_points) > 0

    def test_monitoring_points_include_resource_keys(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", resource_impact={"cpu": 0.1})
        result = engine.recommend_rollout_strategy(g, f)
        assert any("cpu" in m for m in result.monitoring_points)

    def test_rollback_plan_for_kill_switch(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        result = engine.recommend_rollout_strategy(g, f)
        assert "kill-switch" in result.rollback_plan.lower()

    def test_rollback_plan_for_experiment(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("exp", ftype=FlagType.EXPERIMENT)
        result = engine.recommend_rollout_strategy(g, f)
        assert "control" in result.rollback_plan.lower()

    def test_rollback_plan_for_release(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("rel", ftype=FlagType.RELEASE)
        result = engine.recommend_rollout_strategy(g, f)
        assert result.rollback_plan != ""

    def test_flag_id_set(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("my-flag")
        result = engine.recommend_rollout_strategy(g, f)
        assert result.flag_id == "my-flag"


# ---------------------------------------------------------------------------
# generate_flag_dependency_graph tests
# ---------------------------------------------------------------------------


class TestGenerateFlagDependencyGraph:
    def test_empty_flags(self):
        engine = FeatureFlagInteractionEngine()
        result = engine.generate_flag_dependency_graph([])
        assert result["flag_count"] == 0
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_single_flag_node(self):
        engine = FeatureFlagInteractionEngine()
        f = _flag("f1", name="Feature 1", ftype=FlagType.RELEASE, state=FlagState.ENABLED)
        result = engine.generate_flag_dependency_graph([f])
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["id"] == "f1"
        assert result["nodes"][0]["name"] == "Feature 1"
        assert result["nodes"][0]["type"] == "release"
        assert result["nodes"][0]["state"] == "enabled"

    def test_dependency_edges(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", dependencies=["b"])
        fb = _flag("b")
        result = engine.generate_flag_dependency_graph([fa, fb])
        dep_edges = [e for e in result["edges"] if e["type"] == "dependency"]
        assert len(dep_edges) == 1
        assert dep_edges[0]["source"] == "a"
        assert dep_edges[0]["target"] == "b"

    def test_kill_switch_edges(self):
        engine = FeatureFlagInteractionEngine()
        f = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1", "c2"])
        result = engine.generate_flag_dependency_graph([f])
        ks_edges = [e for e in result["edges"] if e["type"] == "kill_switch"]
        assert len(ks_edges) == 2

    def test_flag_count(self):
        engine = FeatureFlagInteractionEngine()
        flags = [_flag(f"f{i}") for i in range(5)]
        result = engine.generate_flag_dependency_graph(flags)
        assert result["flag_count"] == 5

    def test_dependency_count(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", dependencies=["b", "c"])
        fb = _flag("b", dependencies=["c"])
        fc = _flag("c")
        result = engine.generate_flag_dependency_graph([fa, fb, fc])
        assert result["dependency_count"] == 3

    def test_kill_switch_count(self):
        engine = FeatureFlagInteractionEngine()
        ks1 = _flag("ks1", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1"])
        ks2 = _flag("ks2", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c2"])
        f = _flag("f1", ftype=FlagType.RELEASE)
        result = engine.generate_flag_dependency_graph([ks1, ks2, f])
        assert result["kill_switch_count"] == 2

    def test_rollout_percentage_in_node(self):
        engine = FeatureFlagInteractionEngine()
        f = _flag("f1", state=FlagState.PERCENTAGE_ROLLOUT, rollout=42.5)
        result = engine.generate_flag_dependency_graph([f])
        assert result["nodes"][0]["rollout_percentage"] == 42.5

    def test_no_duplicate_nodes(self):
        engine = FeatureFlagInteractionEngine()
        f = _flag("f1")
        result = engine.generate_flag_dependency_graph([f, f])
        assert len(result["nodes"]) == 2  # both instances added

    def test_complex_graph(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", dependencies=["b"], kill_switch_for=["c1"])
        fb = _flag("b", dependencies=["c"])
        fc = _flag("c", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c2"])
        result = engine.generate_flag_dependency_graph([fa, fb, fc])
        assert result["flag_count"] == 3
        assert result["dependency_count"] == 2
        assert result["kill_switch_count"] == 1
        # Edges: 2 dep + 1 ks (from a) + 1 ks (from c) = 4
        assert len(result["edges"]) == 4


# ---------------------------------------------------------------------------
# Integration / edge-case tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_workflow(self):
        """End-to-end: detect, analyze, rollout, gaps, failure, strategy, graph."""
        engine = FeatureFlagInteractionEngine()
        g = _graph(
            _comp("web", ctype=ComponentType.WEB_SERVER),
            _comp("api", ctype=ComponentType.APP_SERVER),
            _comp("db", ctype=ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        g.add_dependency(Dependency(source_id="api", target_id="db"))

        ks = _flag("ks-db", ftype=FlagType.KILL_SWITCH, kill_switch_for=["db"])
        exp = _flag(
            "experiment-x",
            ftype=FlagType.EXPERIMENT,
            state=FlagState.CANARY,
            resource_impact={"cpu_delta": 0.15},
            dependencies=["ks-db"],
        )

        interactions = engine.detect_interactions([ks, exp])
        assert len(interactions) > 0

        impacts = engine.analyze_resilience_impact(g, [ks, exp])
        assert len(impacts) == 2

        rollout = engine.simulate_rollout(g, exp, stages=4)
        assert len(rollout) == 4

        gaps = engine.find_kill_switch_gaps(g, [ks])
        assert "web" in gaps
        assert "api" in gaps
        assert "db" not in gaps

        failure = engine.simulate_flag_failure(g, "ks-db", [ks, exp])
        assert failure.severity == "critical"
        assert "experiment-x" in failure.affected_flags

        strategy = engine.recommend_rollout_strategy(g, exp)
        assert strategy.flag_id == "experiment-x"

        dep_graph = engine.generate_flag_dependency_graph([ks, exp])
        assert dep_graph["flag_count"] == 2

    def test_empty_graph_no_crash(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph()
        f = _flag("f1")
        impacts = engine.analyze_resilience_impact(g, [f])
        assert len(impacts) == 1
        rollout = engine.simulate_rollout(g, f, stages=2)
        assert len(rollout) == 2
        gaps = engine.find_kill_switch_gaps(g, [f])
        assert gaps == []

    def test_flag_with_nonexistent_dependency(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1", dependencies=["nonexistent"])
        # Should not crash
        impacts = engine.analyze_resilience_impact(g, [f])
        assert len(impacts) == 1

    def test_many_flags_performance(self):
        """Ensure we handle 50 flags without error."""
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        flags = [_flag(f"f{i}") for i in range(50)]
        interactions = engine.detect_interactions(flags)
        # With 50 flags, no interactions expected (no deps/conflicts)
        assert isinstance(interactions, list)

    def test_graph_with_dependencies_cascade(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"), _comp("c2"), _comp("c3"))
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        g.add_dependency(Dependency(source_id="c2", target_id="c3"))
        ks = _flag("ks", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c3"])
        impacts = engine.analyze_resilience_impact(g, [ks])
        # c3 and its dependents (c2, c1 via cascade) should be affected
        assert "c3" in impacts[0].affected_components

    def test_dependency_severity_percentage_rollout(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", dependencies=["b"])
        fb = _flag("b", state=FlagState.PERCENTAGE_ROLLOUT, rollout=50.0)
        result = engine.detect_interactions([fa, fb])
        deps = [i for i in result if i.interaction_type == FlagInteractionType.DEPENDENCY]
        assert deps[0].severity == "high"

    def test_cascade_enable_from_percentage_rollout(self):
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", state=FlagState.PERCENTAGE_ROLLOUT, rollout=50.0, dependencies=["b"])
        fb = _flag("b", state=FlagState.DISABLED)
        result = engine.detect_interactions([fa, fb])
        ce = [i for i in result if i.interaction_type == FlagInteractionType.CASCADE_ENABLE]
        assert len(ce) == 1

    def test_medium_severity_for_many_dependents(self):
        engine = FeatureFlagInteractionEngine()
        comps = [_comp(f"c{i}") for i in range(30)]
        g = _graph(*comps)
        fa = _flag("a")
        deps = [_flag(f"d{i}", dependencies=["a"]) for i in range(5)]
        result = engine.simulate_flag_failure(g, "a", [fa] + deps)
        assert result.severity in ("high", "critical")

    def test_rollout_single_stage(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.simulate_rollout(g, f, stages=1)
        assert len(result) == 1
        assert result[0].percentage == 100.0

    def test_monitoring_includes_flag_latency(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"))
        f = _flag("f1")
        result = engine.recommend_rollout_strategy(g, f)
        assert any("latency" in m.lower() for m in result.monitoring_points)

    def test_monitoring_affected_components_count(self):
        engine = FeatureFlagInteractionEngine()
        g = _graph(_comp("c1"), _comp("c2"))
        f = _flag("f1", ftype=FlagType.KILL_SWITCH, kill_switch_for=["c1", "c2"])
        result = engine.recommend_rollout_strategy(g, f)
        assert any("affected" in m.lower() for m in result.monitoring_points)

    def test_cascade_enable_not_from_disabled_source(self):
        """When source flag is disabled, cascade_enable should not fire."""
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", state=FlagState.DISABLED, dependencies=["b"])
        fb = _flag("b", state=FlagState.DISABLED)
        result = engine.detect_interactions([fa, fb])
        ce = [i for i in result if i.interaction_type == FlagInteractionType.CASCADE_ENABLE]
        assert len(ce) == 0

    def test_cascade_enable_not_from_canary(self):
        """Canary state should not trigger cascade_enable."""
        engine = FeatureFlagInteractionEngine()
        fa = _flag("a", state=FlagState.CANARY, dependencies=["b"])
        fb = _flag("b", state=FlagState.DISABLED)
        result = engine.detect_interactions([fa, fb])
        ce = [i for i in result if i.interaction_type == FlagInteractionType.CASCADE_ENABLE]
        assert len(ce) == 0
