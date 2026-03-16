"""Tests for Graceful Degradation Planner.

Comprehensive tests covering all enums, data models, helper functions,
degradation level assessment, feature criticality classification,
dependency-based degradation planning, fallback evaluation, circuit breaker
coordination, load shedding analysis, bulkhead evaluation, cascade analysis,
recovery planning, SLA impact assessment, report generation, plan validation,
and edge cases.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.graceful_degradation_planner import (
    BulkheadEvaluation,
    BulkheadPartition,
    BulkheadStatus,
    CascadeDegradation,
    CircuitBreakerCoordination,
    CircuitState,
    DegradationLevel,
    DegradationLevelAssessment,
    DegradationPlan,
    DegradationReport,
    DegradationRule,
    FallbackEvaluation,
    FallbackType,
    Feature,
    FeatureCriticality,
    GracefulDegradationPlanner,
    LoadSheddingAnalysis,
    LoadSheddingPriority,
    RecoveryPlan,
    RecoveryStep,
    SLAImpactAssessment,
    _clamp,
    _compute_features_for_level,
    _compute_revenue_impact,
    _compute_ux_impact,
    _count_dep_chain,
    _data_consistency_risk,
    _fallback_effectiveness,
    _has_circular_dep,
    _level_severity,
    _resolve_feature_deps,
    _sla_credit_estimate,
    _sla_impact_label,
    _staleness_risk,
    _ux_impact_for_level,
    _worse_level,
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


def _feature(
    name: str = "feat",
    criticality: FeatureCriticality = FeatureCriticality.IMPORTANT,
    component_ids: list[str] | None = None,
    depends_on: list[str] | None = None,
    fallback: FallbackType = FallbackType.NONE,
    fallback_ttl: float = 300.0,
    user_impact: float = 1.0,
    revenue_impact: float = 0.0,
    priority: LoadSheddingPriority = LoadSheddingPriority.MEDIUM,
) -> Feature:
    return Feature(
        name=name,
        criticality=criticality,
        component_ids=component_ids or [],
        depends_on_features=depends_on or [],
        fallback=fallback,
        fallback_ttl_seconds=fallback_ttl,
        user_impact_weight=user_impact,
        revenue_impact_percent=revenue_impact,
        load_shedding_priority=priority,
    )


def _plan(
    features: list[Feature] | None = None,
    rules: list[DegradationRule] | None = None,
    bulkheads: list[BulkheadPartition] | None = None,
) -> DegradationPlan:
    return DegradationPlan(
        features=features or [],
        rules=rules or [],
        bulkhead_partitions=bulkheads or [],
    )


# ---------------------------------------------------------------------------
# 1. Enum coverage
# ---------------------------------------------------------------------------


class TestDegradationLevelEnum:
    def test_all_values(self) -> None:
        assert len(DegradationLevel) == 5

    def test_full_service(self) -> None:
        assert DegradationLevel.FULL_SERVICE == "full_service"

    def test_reduced_functionality(self) -> None:
        assert DegradationLevel.REDUCED_FUNCTIONALITY == "reduced_functionality"

    def test_read_only(self) -> None:
        assert DegradationLevel.READ_ONLY == "read_only"

    def test_maintenance_mode(self) -> None:
        assert DegradationLevel.MAINTENANCE_MODE == "maintenance_mode"

    def test_offline(self) -> None:
        assert DegradationLevel.OFFLINE == "offline"


class TestFeatureCriticalityEnum:
    def test_all_values(self) -> None:
        assert len(FeatureCriticality) == 3

    def test_critical(self) -> None:
        assert FeatureCriticality.CRITICAL == "critical"

    def test_important(self) -> None:
        assert FeatureCriticality.IMPORTANT == "important"

    def test_nice_to_have(self) -> None:
        assert FeatureCriticality.NICE_TO_HAVE == "nice_to_have"


class TestFallbackTypeEnum:
    def test_all_values(self) -> None:
        assert len(FallbackType) == 6

    def test_cache(self) -> None:
        assert FallbackType.CACHE == "cache"

    def test_static_content(self) -> None:
        assert FallbackType.STATIC_CONTENT == "static_content"

    def test_none(self) -> None:
        assert FallbackType.NONE == "none"


class TestLoadSheddingPriorityEnum:
    def test_all_values(self) -> None:
        assert len(LoadSheddingPriority) == 5

    def test_order(self) -> None:
        assert LoadSheddingPriority.CRITICAL == "critical"
        assert LoadSheddingPriority.BEST_EFFORT == "best_effort"


class TestBulkheadStatusEnum:
    def test_all_values(self) -> None:
        assert len(BulkheadStatus) == 4

    def test_healthy(self) -> None:
        assert BulkheadStatus.HEALTHY == "healthy"

    def test_isolated(self) -> None:
        assert BulkheadStatus.ISOLATED == "isolated"


class TestCircuitStateEnum:
    def test_all_values(self) -> None:
        assert len(CircuitState) == 3

    def test_closed(self) -> None:
        assert CircuitState.CLOSED == "closed"


# ---------------------------------------------------------------------------
# 2. Data model defaults
# ---------------------------------------------------------------------------


class TestFeatureModel:
    def test_defaults(self) -> None:
        f = Feature(name="test")
        assert f.criticality == FeatureCriticality.IMPORTANT
        assert f.component_ids == []
        assert f.depends_on_features == []
        assert f.fallback == FallbackType.NONE
        assert f.fallback_ttl_seconds == 300.0
        assert f.user_impact_weight == 1.0
        assert f.revenue_impact_percent == 0.0
        assert f.load_shedding_priority == LoadSheddingPriority.MEDIUM

    def test_custom_values(self) -> None:
        f = Feature(
            name="checkout",
            criticality=FeatureCriticality.CRITICAL,
            component_ids=["db1"],
            revenue_impact_percent=50.0,
        )
        assert f.name == "checkout"
        assert f.criticality == FeatureCriticality.CRITICAL
        assert f.revenue_impact_percent == 50.0


class TestDegradationRuleModel:
    def test_defaults(self) -> None:
        r = DegradationRule(trigger_component_id="c1")
        assert r.trigger_component_id == "c1"
        assert r.disable_features == []
        assert r.target_level == DegradationLevel.REDUCED_FUNCTIONALITY

    def test_custom(self) -> None:
        r = DegradationRule(
            trigger_component_id="db",
            disable_features=["write", "admin"],
            target_level=DegradationLevel.READ_ONLY,
            description="DB failure",
        )
        assert r.target_level == DegradationLevel.READ_ONLY
        assert len(r.disable_features) == 2


class TestBulkheadPartitionModel:
    def test_defaults(self) -> None:
        bp = BulkheadPartition(name="p1")
        assert bp.max_concurrent_requests == 100
        assert bp.queue_size == 50
        assert bp.timeout_seconds == 30.0

    def test_custom(self) -> None:
        bp = BulkheadPartition(
            name="payments",
            feature_names=["checkout"],
            max_concurrent_requests=500,
        )
        assert bp.name == "payments"


class TestDegradationPlanModel:
    def test_empty_plan(self) -> None:
        p = DegradationPlan()
        assert p.features == []
        assert p.rules == []
        assert p.bulkhead_partitions == []


class TestDegradationReportModel:
    def test_defaults(self) -> None:
        r = DegradationReport()
        assert r.timestamp == ""
        assert r.overall_readiness_score == 0.0
        assert r.recommendations == []
        assert r.level_assessments == []


# ---------------------------------------------------------------------------
# 3. Helper function tests
# ---------------------------------------------------------------------------


class TestClamp:
    def test_within_range(self) -> None:
        assert _clamp(50.0) == 50.0

    def test_below_range(self) -> None:
        assert _clamp(-10.0) == 0.0

    def test_above_range(self) -> None:
        assert _clamp(150.0) == 100.0

    def test_custom_bounds(self) -> None:
        assert _clamp(5.0, lo=10.0, hi=20.0) == 10.0
        assert _clamp(25.0, lo=10.0, hi=20.0) == 20.0


class TestLevelSeverity:
    def test_full_service(self) -> None:
        assert _level_severity(DegradationLevel.FULL_SERVICE) == 0

    def test_offline(self) -> None:
        assert _level_severity(DegradationLevel.OFFLINE) == 4

    def test_ordering(self) -> None:
        assert _level_severity(DegradationLevel.REDUCED_FUNCTIONALITY) < _level_severity(
            DegradationLevel.READ_ONLY
        )


class TestWorseLevel:
    def test_same_level(self) -> None:
        result = _worse_level(
            DegradationLevel.FULL_SERVICE, DegradationLevel.FULL_SERVICE
        )
        assert result == DegradationLevel.FULL_SERVICE

    def test_different_levels(self) -> None:
        result = _worse_level(
            DegradationLevel.FULL_SERVICE, DegradationLevel.OFFLINE
        )
        assert result == DegradationLevel.OFFLINE

    def test_reverse_order(self) -> None:
        result = _worse_level(
            DegradationLevel.OFFLINE, DegradationLevel.FULL_SERVICE
        )
        assert result == DegradationLevel.OFFLINE


class TestUxImpactForLevel:
    def test_full_service(self) -> None:
        assert _ux_impact_for_level(DegradationLevel.FULL_SERVICE) == 0.0

    def test_offline(self) -> None:
        assert _ux_impact_for_level(DegradationLevel.OFFLINE) == 100.0

    def test_read_only(self) -> None:
        assert _ux_impact_for_level(DegradationLevel.READ_ONLY) == 50.0


class TestSlaImpactLabel:
    def test_none(self) -> None:
        assert _sla_impact_label(0.0) == "none"

    def test_minor(self) -> None:
        assert _sla_impact_label(0.05) == "minor"

    def test_moderate(self) -> None:
        assert _sla_impact_label(0.5) == "moderate"

    def test_significant(self) -> None:
        assert _sla_impact_label(3.0) == "significant"

    def test_critical(self) -> None:
        assert _sla_impact_label(10.0) == "critical"

    def test_negative(self) -> None:
        assert _sla_impact_label(-1.0) == "none"


class TestSlaCreditEstimate:
    def test_zero(self) -> None:
        assert _sla_credit_estimate(0.0) == 0.0

    def test_minor_loss(self) -> None:
        assert _sla_credit_estimate(0.05) == 0.0

    def test_moderate_loss(self) -> None:
        assert _sla_credit_estimate(0.5) == 10.0

    def test_significant_loss(self) -> None:
        assert _sla_credit_estimate(3.0) == 25.0

    def test_critical_loss(self) -> None:
        assert _sla_credit_estimate(10.0) == 50.0


class TestFallbackEffectiveness:
    def test_cache(self) -> None:
        eff = _fallback_effectiveness(FallbackType.CACHE, 300.0)
        assert eff == 75.0

    def test_none(self) -> None:
        assert _fallback_effectiveness(FallbackType.NONE, 300.0) == 0.0

    def test_cache_stale_long_ttl(self) -> None:
        eff = _fallback_effectiveness(FallbackType.CACHE, 7200.0)
        assert eff < 75.0  # penalized for staleness

    def test_static_medium_ttl(self) -> None:
        eff = _fallback_effectiveness(FallbackType.STATIC_CONTENT, 2000.0)
        assert eff < 60.0

    def test_default_values(self) -> None:
        assert _fallback_effectiveness(FallbackType.DEFAULT_VALUES, 300.0) == 50.0

    def test_queue_for_later(self) -> None:
        assert _fallback_effectiveness(FallbackType.QUEUE_FOR_LATER, 300.0) == 40.0

    def test_redirect(self) -> None:
        assert _fallback_effectiveness(FallbackType.REDIRECT, 300.0) == 55.0


class TestStalenessRisk:
    def test_not_cache(self) -> None:
        assert _staleness_risk(FallbackType.DEFAULT_VALUES, 3600) == "none"

    def test_cache_low(self) -> None:
        assert _staleness_risk(FallbackType.CACHE, 30.0) == "low"

    def test_cache_medium(self) -> None:
        assert _staleness_risk(FallbackType.CACHE, 600.0) == "medium"

    def test_cache_high(self) -> None:
        assert _staleness_risk(FallbackType.CACHE, 7200.0) == "high"

    def test_static_content_low(self) -> None:
        assert _staleness_risk(FallbackType.STATIC_CONTENT, 200.0) == "low"


class TestDataConsistencyRisk:
    def test_cache(self) -> None:
        assert _data_consistency_risk(FallbackType.CACHE) == "medium"

    def test_default_values(self) -> None:
        assert _data_consistency_risk(FallbackType.DEFAULT_VALUES) == "high"

    def test_static_content(self) -> None:
        assert _data_consistency_risk(FallbackType.STATIC_CONTENT) == "low"

    def test_none(self) -> None:
        assert _data_consistency_risk(FallbackType.NONE) == "none"

    def test_redirect(self) -> None:
        assert _data_consistency_risk(FallbackType.REDIRECT) == "low"

    def test_queue(self) -> None:
        assert _data_consistency_risk(FallbackType.QUEUE_FOR_LATER) == "medium"


class TestComputeFeaturesForLevel:
    def test_full_service(self) -> None:
        features = [
            _feature("f1", FeatureCriticality.CRITICAL),
            _feature("f2", FeatureCriticality.IMPORTANT),
            _feature("f3", FeatureCriticality.NICE_TO_HAVE),
        ]
        available, disabled = _compute_features_for_level(
            features, DegradationLevel.FULL_SERVICE
        )
        assert set(available) == {"f1", "f2", "f3"}
        assert disabled == []

    def test_offline(self) -> None:
        features = [
            _feature("f1", FeatureCriticality.CRITICAL),
            _feature("f2", FeatureCriticality.IMPORTANT),
        ]
        available, disabled = _compute_features_for_level(
            features, DegradationLevel.OFFLINE
        )
        assert available == []
        assert set(disabled) == {"f1", "f2"}

    def test_reduced_functionality(self) -> None:
        features = [
            _feature("f1", FeatureCriticality.CRITICAL),
            _feature("f2", FeatureCriticality.IMPORTANT),
            _feature("f3", FeatureCriticality.NICE_TO_HAVE),
        ]
        available, disabled = _compute_features_for_level(
            features, DegradationLevel.REDUCED_FUNCTIONALITY
        )
        assert "f1" in available
        assert "f2" in available
        assert "f3" in disabled

    def test_read_only(self) -> None:
        features = [
            _feature("f1", FeatureCriticality.CRITICAL),
            _feature("f2", FeatureCriticality.IMPORTANT),
            _feature("f3", FeatureCriticality.NICE_TO_HAVE),
        ]
        available, disabled = _compute_features_for_level(
            features, DegradationLevel.READ_ONLY
        )
        assert "f1" in available  # critical survives up to read_only
        assert "f2" in disabled  # important disabled at read_only
        assert "f3" in disabled

    def test_maintenance_mode(self) -> None:
        features = [
            _feature("f1", FeatureCriticality.CRITICAL),
            _feature("f2", FeatureCriticality.IMPORTANT),
        ]
        available, disabled = _compute_features_for_level(
            features, DegradationLevel.MAINTENANCE_MODE
        )
        assert "f1" in disabled  # even critical disabled at maintenance
        assert "f2" in disabled


class TestComputeUxImpact:
    def test_no_features(self) -> None:
        ux = _compute_ux_impact([], [], DegradationLevel.READ_ONLY)
        assert ux == 50.0  # falls back to level-based impact

    def test_all_available(self) -> None:
        features = [_feature("f1")]
        ux = _compute_ux_impact(features, [], DegradationLevel.FULL_SERVICE)
        assert ux == 0.0

    def test_all_disabled(self) -> None:
        features = [_feature("f1")]
        ux = _compute_ux_impact(features, ["f1"], DegradationLevel.OFFLINE)
        assert ux == 100.0

    def test_partial(self) -> None:
        features = [
            _feature("f1", FeatureCriticality.CRITICAL, user_impact=3.0),
            _feature("f2", FeatureCriticality.NICE_TO_HAVE, user_impact=1.0),
        ]
        ux = _compute_ux_impact(features, ["f2"], DegradationLevel.REDUCED_FUNCTIONALITY)
        assert 0.0 < ux < 100.0


class TestComputeRevenueImpact:
    def test_no_disabled(self) -> None:
        features = [_feature("f1", revenue_impact=50.0)]
        assert _compute_revenue_impact(features, []) == 0.0

    def test_some_disabled(self) -> None:
        features = [
            _feature("f1", revenue_impact=30.0),
            _feature("f2", revenue_impact=20.0),
        ]
        result = _compute_revenue_impact(features, ["f1"])
        assert result == 30.0

    def test_capped_at_100(self) -> None:
        features = [
            _feature("f1", revenue_impact=60.0),
            _feature("f2", revenue_impact=60.0),
        ]
        result = _compute_revenue_impact(features, ["f1", "f2"])
        assert result == 100.0


class TestResolveFeatureDeps:
    def test_no_deps(self) -> None:
        features = [_feature("a"), _feature("b")]
        disabled: set[str] = set()
        result = _resolve_feature_deps("a", features, disabled)
        assert result == set()

    def test_single_dep(self) -> None:
        features = [
            _feature("a"),
            _feature("b", depends_on=["a"]),
        ]
        disabled: set[str] = set()
        result = _resolve_feature_deps("a", features, disabled)
        assert "b" in result

    def test_transitive_dep(self) -> None:
        features = [
            _feature("a"),
            _feature("b", depends_on=["a"]),
            _feature("c", depends_on=["b"]),
        ]
        disabled: set[str] = set()
        result = _resolve_feature_deps("a", features, disabled)
        assert "b" in result
        assert "c" in result


class TestCountDepChain:
    def test_no_deps(self) -> None:
        fm = {"a": _feature("a")}
        assert _count_dep_chain("a", fm, set()) == 1

    def test_chain_of_two(self) -> None:
        fm = {
            "a": _feature("a"),
            "b": _feature("b", depends_on=["a"]),
        }
        assert _count_dep_chain("b", fm, set()) == 2

    def test_missing_feature(self) -> None:
        # A missing feature is treated as a leaf node (chain length 1)
        assert _count_dep_chain("missing", {}, set()) == 1

    def test_already_visited(self) -> None:
        fm = {"a": _feature("a")}
        assert _count_dep_chain("a", fm, {"a"}) == 0


class TestHasCircularDep:
    def test_no_circular(self) -> None:
        features = [
            _feature("a"),
            _feature("b", depends_on=["a"]),
        ]
        assert not _has_circular_dep("a", features, set())

    def test_circular(self) -> None:
        features = [
            _feature("a", depends_on=["b"]),
            _feature("b", depends_on=["a"]),
        ]
        assert _has_circular_dep("a", features, set())


# ---------------------------------------------------------------------------
# 4. Engine tests
# ---------------------------------------------------------------------------


class TestAssessDegradationLevels:
    def test_empty_plan(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        assessments = planner.assess_degradation_levels(g, _plan())
        assert len(assessments) == 5
        assert assessments[0].level == DegradationLevel.FULL_SERVICE

    def test_with_features(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("login", FeatureCriticality.CRITICAL, revenue_impact=30.0),
            _feature("search", FeatureCriticality.IMPORTANT, revenue_impact=20.0),
            _feature("theme", FeatureCriticality.NICE_TO_HAVE, revenue_impact=5.0),
        ])
        assessments = planner.assess_degradation_levels(g, plan)
        # Full service: all available
        full = assessments[0]
        assert len(full.available_features) == 3
        assert len(full.disabled_features) == 0
        # Offline: all disabled
        offline = assessments[-1]
        assert len(offline.disabled_features) == 3

    def test_sla_impact_varies(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        assessments = planner.assess_degradation_levels(g, _plan())
        # Full service should have "none" SLA impact
        assert assessments[0].sla_impact == "none"
        # Offline should have non-none SLA impact
        assert assessments[-1].sla_impact != "none"

    def test_description_varies(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[_feature("f1")])
        assessments = planner.assess_degradation_levels(g, plan)
        assert "operational" in assessments[0].description.lower()
        assert "unavailable" in assessments[-1].description.lower()


class TestClassifyFeatures:
    def test_classification(self) -> None:
        planner = GracefulDegradationPlanner()
        plan = _plan(features=[
            _feature("a", FeatureCriticality.CRITICAL),
            _feature("b", FeatureCriticality.IMPORTANT),
            _feature("c", FeatureCriticality.NICE_TO_HAVE),
            _feature("d", FeatureCriticality.CRITICAL),
        ])
        result = planner.classify_features(plan)
        assert set(result["critical"]) == {"a", "d"}
        assert result["important"] == ["b"]
        assert result["nice_to_have"] == ["c"]

    def test_empty(self) -> None:
        planner = GracefulDegradationPlanner()
        result = planner.classify_features(_plan())
        assert result["critical"] == []
        assert result["important"] == []
        assert result["nice_to_have"] == []


class TestPlanDegradationForFailure:
    def test_direct_component_failure(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = _comp("c1")
        g = _graph(c1)
        plan = _plan(features=[
            _feature("login", FeatureCriticality.CRITICAL, component_ids=["c1"]),
            _feature("search", FeatureCriticality.IMPORTANT, component_ids=["c2"]),
        ])
        result = planner.plan_degradation_for_failure(g, plan, "c1")
        assert "login" in result.disabled_features
        assert result.level != DegradationLevel.FULL_SERVICE

    def test_rule_based_degradation(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = _comp("c1")
        g = _graph(c1)
        plan = _plan(
            features=[
                _feature("write", FeatureCriticality.IMPORTANT),
                _feature("read", FeatureCriticality.CRITICAL),
            ],
            rules=[
                DegradationRule(
                    trigger_component_id="c1",
                    disable_features=["write"],
                    target_level=DegradationLevel.READ_ONLY,
                )
            ],
        )
        result = planner.plan_degradation_for_failure(g, plan, "c1")
        assert "write" in result.disabled_features
        assert result.level == DegradationLevel.READ_ONLY

    def test_cascading_feature_deps(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = _comp("c1")
        g = _graph(c1)
        plan = _plan(features=[
            _feature("auth", FeatureCriticality.CRITICAL, component_ids=["c1"]),
            _feature("profile", FeatureCriticality.IMPORTANT, depends_on=["auth"]),
            _feature("settings", FeatureCriticality.NICE_TO_HAVE, depends_on=["profile"]),
        ])
        result = planner.plan_degradation_for_failure(g, plan, "c1")
        # auth fails -> profile disabled -> settings disabled
        assert "auth" in result.disabled_features
        assert "profile" in result.disabled_features
        assert "settings" in result.disabled_features

    def test_graph_transitive_failure(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        plan = _plan(features=[
            _feature("f1", component_ids=["c1"]),
            _feature("f2", component_ids=["c2"]),
        ])
        result = planner.plan_degradation_for_failure(g, plan, "c1")
        # c2 depends on c1, so c2 is affected
        assert "f1" in result.disabled_features
        assert "f2" in result.disabled_features


class TestEvaluateFallbacks:
    def test_no_fallback_critical(self) -> None:
        planner = GracefulDegradationPlanner()
        plan = _plan(features=[
            _feature("f1", FeatureCriticality.CRITICAL, fallback=FallbackType.NONE),
        ])
        evals = planner.evaluate_fallbacks(plan)
        assert len(evals) == 1
        assert evals[0].effectiveness == 0.0
        assert len(evals[0].recommendations) > 0

    def test_cache_fallback(self) -> None:
        planner = GracefulDegradationPlanner()
        plan = _plan(features=[
            _feature("f1", fallback=FallbackType.CACHE, fallback_ttl=300.0),
        ])
        evals = planner.evaluate_fallbacks(plan)
        assert evals[0].effectiveness == 75.0
        assert evals[0].staleness_risk == "low"

    def test_stale_cache(self) -> None:
        planner = GracefulDegradationPlanner()
        plan = _plan(features=[
            _feature("f1", fallback=FallbackType.CACHE, fallback_ttl=7200.0),
        ])
        evals = planner.evaluate_fallbacks(plan)
        assert evals[0].staleness_risk == "high"
        assert any("staleness" in r.lower() for r in evals[0].recommendations)

    def test_high_consistency_risk(self) -> None:
        planner = GracefulDegradationPlanner()
        plan = _plan(features=[
            _feature("f1", fallback=FallbackType.DEFAULT_VALUES),
        ])
        evals = planner.evaluate_fallbacks(plan)
        assert evals[0].data_consistency_risk == "high"
        assert any("consistency" in r.lower() for r in evals[0].recommendations)

    def test_no_fallback_important(self) -> None:
        planner = GracefulDegradationPlanner()
        plan = _plan(features=[
            _feature("f1", FeatureCriticality.IMPORTANT, fallback=FallbackType.NONE),
        ])
        evals = planner.evaluate_fallbacks(plan)
        assert len(evals[0].recommendations) > 0

    def test_no_fallback_nice_to_have(self) -> None:
        planner = GracefulDegradationPlanner()
        plan = _plan(features=[
            _feature("f1", FeatureCriticality.NICE_TO_HAVE, fallback=FallbackType.NONE),
        ])
        evals = planner.evaluate_fallbacks(plan)
        # nice_to_have without fallback gets no recommendation
        assert len(evals[0].recommendations) == 0


class TestCoordinateCircuitBreakers:
    def test_healthy_component(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = _comp("c1")
        g = _graph(c1)
        plan = _plan(features=[_feature("f1", component_ids=["c1"])])
        results = planner.coordinate_circuit_breakers(g, plan)
        assert len(results) == 1
        assert results[0].state == CircuitState.CLOSED
        assert results[0].failure_count == 0
        assert "f1" in results[0].affected_features

    def test_down_component(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = Component(
            id="c1", name="c1", type=ComponentType.APP_SERVER,
            health=HealthStatus.DOWN,
        )
        g = _graph(c1)
        plan = _plan(features=[_feature("f1", component_ids=["c1"])])
        results = planner.coordinate_circuit_breakers(g, plan)
        assert results[0].state == CircuitState.OPEN
        assert results[0].failure_count == 5
        assert "fallback" in results[0].recommended_action.lower()

    def test_degraded_component(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = Component(
            id="c1", name="c1", type=ComponentType.APP_SERVER,
            health=HealthStatus.DEGRADED,
        )
        g = _graph(c1)
        plan = _plan()
        results = planner.coordinate_circuit_breakers(g, plan)
        assert results[0].state == CircuitState.HALF_OPEN
        assert results[0].failure_count == 2

    def test_overloaded_component(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = Component(
            id="c1", name="c1", type=ComponentType.APP_SERVER,
            health=HealthStatus.OVERLOADED,
        )
        g = _graph(c1)
        plan = _plan()
        results = planner.coordinate_circuit_breakers(g, plan)
        assert results[0].state == CircuitState.CLOSED
        assert results[0].failure_count == 3


class TestAnalyzeLoadShedding:
    def test_under_capacity(self) -> None:
        planner = GracefulDegradationPlanner()
        result = planner.analyze_load_shedding(_plan(), 1000, 50.0)
        assert result.shed_requests == 0
        assert result.protected_requests == 1000
        assert result.fairness_score == 100.0

    def test_at_threshold(self) -> None:
        planner = GracefulDegradationPlanner()
        result = planner.analyze_load_shedding(_plan(), 1000, 80.0)
        assert result.shed_requests == 0

    def test_over_capacity(self) -> None:
        planner = GracefulDegradationPlanner()
        plan = _plan(features=[
            _feature("f1", priority=LoadSheddingPriority.LOW),
            _feature("f2", priority=LoadSheddingPriority.HIGH),
        ])
        result = planner.analyze_load_shedding(plan, 1000, 95.0)
        assert result.shed_requests > 0
        assert result.protected_requests < 1000

    def test_critical_overload(self) -> None:
        planner = GracefulDegradationPlanner()
        result = planner.analyze_load_shedding(
            _plan(features=[_feature("f1")]), 1000, 100.0
        )
        assert result.shed_requests > 0
        assert any("overloaded" in r.lower() for r in result.recommendations)

    def test_zero_requests(self) -> None:
        planner = GracefulDegradationPlanner()
        result = planner.analyze_load_shedding(_plan(), 0, 90.0)
        assert result.shed_requests == 0

    def test_heavy_shedding_recommendation(self) -> None:
        planner = GracefulDegradationPlanner()
        plan = _plan(features=[
            _feature("f1", priority=LoadSheddingPriority.BEST_EFFORT),
        ])
        result = planner.analyze_load_shedding(plan, 100, 100.0)
        assert result.shed_requests > 0

    def test_no_features_distribution(self) -> None:
        planner = GracefulDegradationPlanner()
        result = planner.analyze_load_shedding(_plan(), 1000, 95.0)
        assert result.shed_requests > 0


class TestEvaluateBulkheads:
    def test_no_partitions(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        result = planner.evaluate_bulkheads(g, _plan())
        assert result == []

    def test_healthy_partition(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(
            features=[_feature("f1", component_ids=["c1"])],
            bulkheads=[
                BulkheadPartition(
                    name="p1",
                    feature_names=["f1"],
                    max_concurrent_requests=100,
                )
            ],
        )
        result = planner.evaluate_bulkheads(g, plan, current_load={"f1": 30.0})
        assert len(result) == 1
        assert result[0].status == BulkheadStatus.HEALTHY

    def test_stressed_partition(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(
            features=[_feature("f1", component_ids=["c1"])],
            bulkheads=[
                BulkheadPartition(
                    name="p1",
                    feature_names=["f1"],
                    max_concurrent_requests=100,
                )
            ],
        )
        result = planner.evaluate_bulkheads(g, plan, current_load={"f1": 85.0})
        assert result[0].status == BulkheadStatus.STRESSED
        assert len(result[0].recommendations) > 0

    def test_failing_partition(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(
            features=[_feature("f1", component_ids=["c1"])],
            bulkheads=[
                BulkheadPartition(
                    name="p1",
                    feature_names=["f1"],
                    max_concurrent_requests=100,
                )
            ],
        )
        result = planner.evaluate_bulkheads(g, plan, current_load={"f1": 150.0})
        assert result[0].status == BulkheadStatus.FAILING

    def test_shared_components_reduce_isolation(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(
            features=[
                _feature("f1", component_ids=["c1"]),
                _feature("f2", component_ids=["c1"]),
            ],
            bulkheads=[
                BulkheadPartition(name="p1", feature_names=["f1"]),
                BulkheadPartition(name="p2", feature_names=["f2"]),
            ],
        )
        result = planner.evaluate_bulkheads(g, plan)
        # Shared c1 reduces isolation
        assert result[0].isolation_effectiveness < 100.0 or result[1].isolation_effectiveness < 100.0

    def test_no_current_load(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(
            features=[_feature("f1", component_ids=["c1"])],
            bulkheads=[
                BulkheadPartition(name="p1", feature_names=["f1"]),
            ],
        )
        result = planner.evaluate_bulkheads(g, plan)
        assert result[0].status == BulkheadStatus.HEALTHY

    def test_overflow_risk(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(
            features=[_feature("f1", component_ids=["c1"])],
            bulkheads=[
                BulkheadPartition(
                    name="p1",
                    feature_names=["f1"],
                    max_concurrent_requests=100,
                    queue_size=50,
                )
            ],
        )
        result = planner.evaluate_bulkheads(g, plan, current_load={"f1": 90.0})
        assert result[0].overflow_risk > 0.0


class TestAnalyzeCascade:
    def test_single_component_no_cascade(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[_feature("f1", component_ids=["c1"])])
        result = planner.analyze_cascade(g, plan, "c1")
        assert result.trigger_component_id == "c1"
        assert "c1" in result.cascade_chain
        assert "f1" in result.affected_features

    def test_multi_hop_cascade(self) -> None:
        planner = GracefulDegradationPlanner()
        c1, c2, c3 = _comp("c1"), _comp("c2"), _comp("c3")
        g = _graph(c1, c2, c3)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        g.add_dependency(Dependency(source_id="c3", target_id="c2"))
        plan = _plan(features=[
            _feature("f1", component_ids=["c1"]),
            _feature("f2", component_ids=["c2"]),
            _feature("f3", component_ids=["c3"]),
        ])
        result = planner.analyze_cascade(g, plan, "c1")
        assert "c2" in result.cascade_chain
        assert "c3" in result.cascade_chain
        assert "f2" in result.affected_features
        assert "f3" in result.affected_features

    def test_cascade_applies_rules(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(
            features=[_feature("f1"), _feature("f2")],
            rules=[
                DegradationRule(
                    trigger_component_id="c1",
                    disable_features=["f2"],
                )
            ],
        )
        result = planner.analyze_cascade(g, plan, "c1")
        assert "f2" in result.affected_features

    def test_cascade_time_scales_with_depth(self) -> None:
        planner = GracefulDegradationPlanner()
        c1, c2 = _comp("c1"), _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        plan = _plan()
        result = planner.analyze_cascade(g, plan, "c1")
        assert result.time_to_full_cascade_seconds > 0.0

    def test_cascade_mitigation_points(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = _comp("c1")
        c2 = Component(
            id="c2", name="c2", type=ComponentType.APP_SERVER,
            replicas=3, failover=FailoverConfig(enabled=True),
        )
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        plan = _plan()
        result = planner.analyze_cascade(g, plan, "c1")
        assert "c2" in result.mitigation_points

    def test_cascade_final_level(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("f1", FeatureCriticality.CRITICAL, component_ids=["c1"]),
        ])
        result = planner.analyze_cascade(g, plan, "c1")
        assert result.final_level == DegradationLevel.MAINTENANCE_MODE


class TestPlanRecovery:
    def test_empty_plan(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        result = planner.plan_recovery(g, _plan())
        assert len(result.steps) == 0
        assert result.total_estimated_time_seconds == 0.0

    def test_ordered_by_criticality(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("theme", FeatureCriticality.NICE_TO_HAVE),
            _feature("login", FeatureCriticality.CRITICAL),
            _feature("search", FeatureCriticality.IMPORTANT),
        ])
        result = planner.plan_recovery(g, plan)
        assert result.steps[0].feature_name == "login"
        assert result.steps[1].feature_name == "search"
        assert result.steps[2].feature_name == "theme"

    def test_dependencies_before_dependents(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("auth", FeatureCriticality.CRITICAL),
            _feature("profile", FeatureCriticality.CRITICAL, depends_on=["auth"]),
        ])
        result = planner.plan_recovery(g, plan)
        auth_idx = next(i for i, s in enumerate(result.steps) if s.feature_name == "auth")
        prof_idx = next(i for i, s in enumerate(result.steps) if s.feature_name == "profile")
        assert auth_idx < prof_idx

    def test_database_recovery_time(self) -> None:
        planner = GracefulDegradationPlanner()
        db = _comp("db1", ComponentType.DATABASE)
        g = _graph(db)
        plan = _plan(features=[
            _feature("data", component_ids=["db1"]),
        ])
        result = planner.plan_recovery(g, plan)
        assert result.steps[0].estimated_time_seconds >= 120.0

    def test_verification_steps_for_critical(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("auth", FeatureCriticality.CRITICAL, component_ids=["c1"]),
        ])
        result = planner.plan_recovery(g, plan)
        assert any("smoke" in v.lower() for v in result.steps[0].verification_steps)

    def test_long_recovery_recommendation(self) -> None:
        planner = GracefulDegradationPlanner()
        db = _comp("db1", ComponentType.DATABASE)
        g = _graph(db)
        features = [
            _feature(f"f{i}", component_ids=["db1"]) for i in range(6)
        ]
        plan = _plan(features=features)
        result = planner.plan_recovery(g, plan)
        assert result.total_estimated_time_seconds > 600.0
        assert any("10 minutes" in r for r in result.recommendations)

    def test_critical_path_length(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("a"),
            _feature("b", depends_on=["a"]),
            _feature("c", depends_on=["b"]),
            _feature("d", depends_on=["c"]),
        ])
        result = planner.plan_recovery(g, plan)
        assert result.critical_path_length >= 4
        assert any("dependency chain" in r for r in result.recommendations)


class TestAssessSlaImpact:
    def test_all_levels(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        results = planner.assess_sla_impact(g, _plan())
        assert len(results) == 5

    def test_full_service_no_impact(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        results = planner.assess_sla_impact(g, _plan())
        full = results[0]
        assert full.availability_impact_percent == 0.0
        assert full.sla_breach_risk == "none"
        assert full.estimated_credit_percent == 0.0

    def test_offline_high_impact(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        results = planner.assess_sla_impact(g, _plan())
        offline = results[-1]
        assert offline.availability_impact_percent > 0.0
        assert offline.sla_breach_risk in ("significant", "critical")
        assert offline.estimated_credit_percent > 0.0

    def test_recommendations_for_severe_levels(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        results = planner.assess_sla_impact(g, _plan())
        offline = results[-1]
        assert len(offline.recommendations) > 0


class TestGenerateReport:
    def test_report_structure(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = _comp("c1")
        g = _graph(c1)
        plan = _plan(
            features=[
                _feature("f1", FeatureCriticality.CRITICAL, component_ids=["c1"],
                         fallback=FallbackType.CACHE),
            ],
            bulkheads=[
                BulkheadPartition(name="p1", feature_names=["f1"]),
            ],
        )
        report = planner.generate_report(g, plan)
        assert report.timestamp != ""
        assert len(report.level_assessments) == 5
        assert len(report.fallback_evaluations) == 1
        assert len(report.circuit_breaker_states) == 1
        assert report.load_shedding is not None
        assert len(report.bulkhead_evaluations) == 1
        assert report.recovery_plan is not None
        assert len(report.sla_impacts) == 5
        assert 0.0 <= report.overall_readiness_score <= 100.0

    def test_report_empty_graph(self) -> None:
        planner = GracefulDegradationPlanner()
        g = InfraGraph()
        report = planner.generate_report(g, _plan())
        assert report.timestamp != ""
        assert len(report.level_assessments) == 5

    def test_report_with_overloaded_system(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = _comp("c1")
        g = _graph(c1)
        plan = _plan(features=[_feature("f1", component_ids=["c1"])])
        report = planner.generate_report(g, plan, capacity_percent=95.0)
        assert report.load_shedding is not None
        assert report.load_shedding.shed_requests > 0

    def test_report_readiness_score(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = _comp("c1")
        g = _graph(c1)
        plan = _plan(
            features=[
                _feature("f1", fallback=FallbackType.CACHE, component_ids=["c1"]),
                _feature("f2", fallback=FallbackType.DEFAULT_VALUES, component_ids=["c1"]),
            ],
            bulkheads=[
                BulkheadPartition(name="p1", feature_names=["f1", "f2"]),
            ],
        )
        report = planner.generate_report(g, plan)
        assert report.overall_readiness_score > 0.0

    def test_report_deduplicated_recommendations(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("f1", FeatureCriticality.CRITICAL, fallback=FallbackType.NONE),
        ])
        report = planner.generate_report(g, plan)
        seen = set()
        for r in report.recommendations:
            assert r not in seen, f"Duplicate recommendation: {r}"
            seen.add(r)


class TestValidatePlan:
    def test_valid_plan(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = _comp("c1")
        g = _graph(c1)
        plan = _plan(features=[
            _feature("f1", component_ids=["c1"], fallback=FallbackType.CACHE),
        ])
        issues = planner.validate_plan(g, plan)
        assert issues == []

    def test_unknown_component(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("f1", component_ids=["unknown"]),
        ])
        issues = planner.validate_plan(g, plan)
        assert any("unknown" in i for i in issues)

    def test_unknown_feature_dependency(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("f1", depends_on=["nonexistent"]),
        ])
        issues = planner.validate_plan(g, plan)
        assert any("nonexistent" in i for i in issues)

    def test_rule_unknown_component(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(
            rules=[
                DegradationRule(
                    trigger_component_id="unknown",
                    disable_features=["f1"],
                )
            ],
        )
        issues = planner.validate_plan(g, plan)
        assert any("unknown" in i for i in issues)

    def test_rule_unknown_feature(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(
            features=[_feature("f1")],
            rules=[
                DegradationRule(
                    trigger_component_id="c1",
                    disable_features=["nonexistent"],
                )
            ],
        )
        issues = planner.validate_plan(g, plan)
        assert any("nonexistent" in i for i in issues)

    def test_bulkhead_unknown_feature(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(
            bulkheads=[
                BulkheadPartition(name="p1", feature_names=["unknown"]),
            ],
        )
        issues = planner.validate_plan(g, plan)
        assert any("unknown" in i for i in issues)

    def test_critical_without_fallback(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("f1", FeatureCriticality.CRITICAL, component_ids=["c1"],
                     fallback=FallbackType.NONE),
        ])
        issues = planner.validate_plan(g, plan)
        assert any("fallback" in i.lower() for i in issues)

    def test_circular_dependency_detection(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("a", depends_on=["b"]),
            _feature("b", depends_on=["a"]),
        ])
        issues = planner.validate_plan(g, plan)
        assert any("circular" in i.lower() for i in issues)


# ---------------------------------------------------------------------------
# 5. Edge cases and integration
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_graph_report(self) -> None:
        planner = GracefulDegradationPlanner()
        g = InfraGraph()
        plan = _plan(features=[_feature("f1")])
        report = planner.generate_report(g, plan)
        assert report.timestamp != ""

    def test_feature_no_components(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[_feature("f1")])
        result = planner.plan_degradation_for_failure(g, plan, "c1")
        assert isinstance(result, DegradationLevelAssessment)

    def test_multiple_rules_same_component(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(
            features=[_feature("f1"), _feature("f2"), _feature("f3")],
            rules=[
                DegradationRule(
                    trigger_component_id="c1",
                    disable_features=["f1"],
                    target_level=DegradationLevel.REDUCED_FUNCTIONALITY,
                ),
                DegradationRule(
                    trigger_component_id="c1",
                    disable_features=["f2"],
                    target_level=DegradationLevel.READ_ONLY,
                ),
            ],
        )
        result = planner.plan_degradation_for_failure(g, plan, "c1")
        assert "f1" in result.disabled_features
        assert "f2" in result.disabled_features
        # Should pick the worse level
        assert _level_severity(result.level) >= _level_severity(DegradationLevel.READ_ONLY)

    def test_cascade_no_features(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        result = planner.analyze_cascade(g, _plan(), "c1")
        assert result.affected_features == []
        assert result.final_level == DegradationLevel.FULL_SERVICE

    def test_readiness_no_fallbacks(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("f1", fallback=FallbackType.NONE),
            _feature("f2", fallback=FallbackType.NONE),
        ])
        report = planner.generate_report(g, plan)
        # Low readiness because no fallbacks
        assert report.overall_readiness_score < 70.0

    def test_full_fallback_coverage_boosts_readiness(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("f1", fallback=FallbackType.CACHE, component_ids=["c1"]),
            _feature("f2", fallback=FallbackType.STATIC_CONTENT, component_ids=["c1"]),
        ])
        report = planner.generate_report(g, plan)
        assert report.overall_readiness_score > 20.0

    def test_recovery_cache_component(self) -> None:
        planner = GracefulDegradationPlanner()
        cache = _comp("cache1", ComponentType.CACHE)
        g = _graph(cache)
        plan = _plan(features=[
            _feature("caching", component_ids=["cache1"]),
        ])
        result = planner.plan_recovery(g, plan)
        assert result.steps[0].estimated_time_seconds >= 60.0

    def test_recovery_queue_component(self) -> None:
        planner = GracefulDegradationPlanner()
        queue = _comp("q1", ComponentType.QUEUE)
        g = _graph(queue)
        plan = _plan(features=[
            _feature("messaging", component_ids=["q1"]),
        ])
        result = planner.plan_recovery(g, plan)
        assert result.steps[0].estimated_time_seconds >= 45.0

    def test_cascade_feature_dependency_resolution(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        plan = _plan(features=[
            _feature("auth", FeatureCriticality.CRITICAL, component_ids=["c1"]),
            _feature("profile", depends_on=["auth"]),
        ])
        result = planner.analyze_cascade(g, plan, "c1")
        assert "auth" in result.affected_features
        assert "profile" in result.affected_features

    def test_load_shedding_high_priority_shed_warning(self) -> None:
        planner = GracefulDegradationPlanner()
        plan = _plan(features=[
            _feature("f1", priority=LoadSheddingPriority.CRITICAL),
            _feature("f2", priority=LoadSheddingPriority.HIGH),
        ])
        result = planner.analyze_load_shedding(plan, 10000, 100.0)
        if result.shed_by_priority.get("critical", 0) > 0 or result.shed_by_priority.get("high", 0) > 0:
            assert any("high-priority" in r.lower() for r in result.recommendations)

    def test_validate_empty_plan(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("c1"))
        issues = planner.validate_plan(g, _plan())
        assert issues == []

    def test_multiple_components_different_types(self) -> None:
        planner = GracefulDegradationPlanner()
        c1 = _comp("web", ComponentType.WEB_SERVER)
        c2 = _comp("app", ComponentType.APP_SERVER)
        c3 = _comp("db", ComponentType.DATABASE)
        g = _graph(c1, c2, c3)
        g.add_dependency(Dependency(source_id="web", target_id="app"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        plan = _plan(features=[
            _feature("ui", FeatureCriticality.IMPORTANT, component_ids=["web"]),
            _feature("api", FeatureCriticality.CRITICAL, component_ids=["app"]),
            _feature("data", FeatureCriticality.CRITICAL, component_ids=["db"]),
        ])
        result = planner.analyze_cascade(g, plan, "db")
        assert "data" in result.affected_features
        # app depends on db, web depends on app
        assert "api" in result.affected_features
        assert "ui" in result.affected_features

    def test_bulkhead_blast_radius_not_contained(self) -> None:
        planner = GracefulDegradationPlanner()
        g = _graph(_comp("shared"))
        plan = _plan(
            features=[
                _feature("f1", component_ids=["shared"]),
                _feature("f2", component_ids=["shared"]),
                _feature("f3", component_ids=["shared"]),
                _feature("f4", component_ids=["shared"]),
                _feature("f5", component_ids=["shared"]),
                _feature("f6", component_ids=["shared"]),
            ],
            bulkheads=[
                BulkheadPartition(name="p1", feature_names=["f1"]),
                BulkheadPartition(name="p2", feature_names=["f2", "f3", "f4", "f5", "f6"]),
            ],
        )
        result = planner.evaluate_bulkheads(g, plan)
        # p1 has shared component with p2's features
        has_poor_isolation = any(not e.blast_radius_contained for e in result)
        assert has_poor_isolation
