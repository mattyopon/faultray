"""Comprehensive tests for the Canary & Rollback Automation Simulator.

Tests cover DeploymentStrategy/RollbackTrigger/CanaryPhase enums,
CanaryConfig/CanaryStepResult/RollbackAnalysis/FailedCanaryResult/
BlastRadiusEstimate/StrategyComparison/RollbackReadinessReport models,
CanaryRollbackEngine core logic (simulate_canary, analyze_rollback,
recommend_strategy, simulate_failed_canary, estimate_blast_radius,
compare_strategies, validate_rollback_readiness), edge-cases (empty graph,
single component, missing component, large graph), and integration scenarios.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
    RetryStrategy,
    SecurityProfile,
    SLOTarget,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.canary_rollback import (
    BlastRadiusEstimate,
    CanaryConfig,
    CanaryPhase,
    CanaryRollbackEngine,
    CanaryStepResult,
    DeploymentStrategy,
    FailedCanaryResult,
    RollbackAnalysis,
    RollbackReadinessReport,
    RollbackTrigger,
    StrategyComparison,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str | None = None,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    failover_enabled: bool = False,
    autoscaling_enabled: bool = False,
    cpu_percent: float = 0.0,
    memory_percent: float = 0.0,
    max_rps: int = 5000,
    slo_targets: list[SLOTarget] | None = None,
    deploy_downtime_seconds: float = 30.0,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        health=health,
        failover=FailoverConfig(enabled=failover_enabled),
        autoscaling=AutoScalingConfig(enabled=autoscaling_enabled),
        metrics=ResourceMetrics(cpu_percent=cpu_percent, memory_percent=memory_percent),
        capacity=Capacity(max_rps=max_rps),
        slo_targets=slo_targets or [],
        operational_profile=OperationalProfile(deploy_downtime_seconds=deploy_downtime_seconds),
    )


def _graph(*components: Component, deps: list[Dependency] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for d in deps or []:
        g.add_dependency(d)
    return g


def _dep(
    src: str,
    tgt: str,
    dep_type: str = "requires",
    cb_enabled: bool = False,
) -> Dependency:
    return Dependency(
        source_id=src,
        target_id=tgt,
        dependency_type=dep_type,
        circuit_breaker=CircuitBreakerConfig(enabled=cb_enabled),
    )


# ---------------------------------------------------------------------------
# DeploymentStrategy enum tests
# ---------------------------------------------------------------------------


class TestDeploymentStrategyEnum:
    def test_canary_value(self):
        assert DeploymentStrategy.CANARY == "canary"

    def test_blue_green_value(self):
        assert DeploymentStrategy.BLUE_GREEN == "blue_green"

    def test_rolling_value(self):
        assert DeploymentStrategy.ROLLING == "rolling"

    def test_recreate_value(self):
        assert DeploymentStrategy.RECREATE == "recreate"

    def test_shadow_value(self):
        assert DeploymentStrategy.SHADOW == "shadow"

    def test_a_b_test_value(self):
        assert DeploymentStrategy.A_B_TEST == "a_b_test"

    def test_all_members(self):
        assert len(DeploymentStrategy) == 6

    def test_string_construction(self):
        assert DeploymentStrategy("canary") == DeploymentStrategy.CANARY


# ---------------------------------------------------------------------------
# RollbackTrigger enum tests
# ---------------------------------------------------------------------------


class TestRollbackTriggerEnum:
    def test_error_rate_spike_value(self):
        assert RollbackTrigger.ERROR_RATE_SPIKE == "error_rate_spike"

    def test_latency_degradation_value(self):
        assert RollbackTrigger.LATENCY_DEGRADATION == "latency_degradation"

    def test_saturation_breach_value(self):
        assert RollbackTrigger.SATURATION_BREACH == "saturation_breach"

    def test_slo_violation_value(self):
        assert RollbackTrigger.SLO_VIOLATION == "slo_violation"

    def test_health_check_failure_value(self):
        assert RollbackTrigger.HEALTH_CHECK_FAILURE == "health_check_failure"

    def test_manual_value(self):
        assert RollbackTrigger.MANUAL == "manual"

    def test_crash_loop_value(self):
        assert RollbackTrigger.CRASH_LOOP == "crash_loop"

    def test_memory_leak_value(self):
        assert RollbackTrigger.MEMORY_LEAK == "memory_leak"

    def test_cpu_spike_value(self):
        assert RollbackTrigger.CPU_SPIKE == "cpu_spike"

    def test_custom_metric_value(self):
        assert RollbackTrigger.CUSTOM_METRIC == "custom_metric"

    def test_all_members(self):
        assert len(RollbackTrigger) == 10

    def test_string_construction(self):
        assert RollbackTrigger("manual") == RollbackTrigger.MANUAL


# ---------------------------------------------------------------------------
# CanaryPhase enum tests
# ---------------------------------------------------------------------------


class TestCanaryPhaseEnum:
    def test_initial_split_value(self):
        assert CanaryPhase.INITIAL_SPLIT == "initial_split"

    def test_observation_value(self):
        assert CanaryPhase.OBSERVATION == "observation"

    def test_analysis_value(self):
        assert CanaryPhase.ANALYSIS == "analysis"

    def test_promotion_value(self):
        assert CanaryPhase.PROMOTION == "promotion"

    def test_rollback_value(self):
        assert CanaryPhase.ROLLBACK == "rollback"

    def test_completed_value(self):
        assert CanaryPhase.COMPLETED == "completed"

    def test_all_members(self):
        assert len(CanaryPhase) == 6

    def test_string_construction(self):
        assert CanaryPhase("observation") == CanaryPhase.OBSERVATION


# ---------------------------------------------------------------------------
# CanaryConfig model tests
# ---------------------------------------------------------------------------


class TestCanaryConfigModel:
    def test_defaults(self):
        cfg = CanaryConfig()
        assert cfg.strategy == DeploymentStrategy.CANARY
        assert cfg.initial_percentage == 5.0
        assert cfg.step_percentage == 10.0
        assert cfg.step_interval_seconds == 300
        assert cfg.max_error_rate == 1.0
        assert cfg.max_latency_p99_ms == 500.0
        assert cfg.min_observation_seconds == 60
        assert cfg.auto_rollback is True
        assert cfg.rollback_on == []

    def test_custom_values(self):
        cfg = CanaryConfig(
            strategy=DeploymentStrategy.BLUE_GREEN,
            initial_percentage=1.0,
            step_percentage=5.0,
            max_error_rate=0.5,
            rollback_on=[RollbackTrigger.ERROR_RATE_SPIKE],
        )
        assert cfg.strategy == DeploymentStrategy.BLUE_GREEN
        assert cfg.initial_percentage == 1.0
        assert cfg.rollback_on == [RollbackTrigger.ERROR_RATE_SPIKE]

    def test_serialization(self):
        cfg = CanaryConfig()
        data = cfg.model_dump()
        assert "strategy" in data
        assert data["auto_rollback"] is True


# ---------------------------------------------------------------------------
# CanaryStepResult model tests
# ---------------------------------------------------------------------------


class TestCanaryStepResultModel:
    def test_creation(self):
        step = CanaryStepResult(
            step=1,
            traffic_percentage=5.0,
            duration_seconds=60,
            error_rate=0.01,
            latency_p99_ms=50.0,
            phase=CanaryPhase.INITIAL_SPLIT,
            decision="proceed",
        )
        assert step.step == 1
        assert step.metrics == {}

    def test_with_metrics(self):
        step = CanaryStepResult(
            step=2,
            traffic_percentage=15.0,
            duration_seconds=300,
            error_rate=0.02,
            latency_p99_ms=80.0,
            phase=CanaryPhase.OBSERVATION,
            decision="proceed",
            metrics={"cpu": 45.0},
        )
        assert step.metrics["cpu"] == 45.0


# ---------------------------------------------------------------------------
# RollbackAnalysis model tests
# ---------------------------------------------------------------------------


class TestRollbackAnalysisModel:
    def test_creation(self):
        ra = RollbackAnalysis(
            trigger=RollbackTrigger.ERROR_RATE_SPIKE,
            detection_time_seconds=10.0,
            rollback_time_seconds=30.0,
            total_impact_seconds=40.0,
            affected_requests_estimate=2000,
            blast_radius=["svc-a", "svc-b"],
            data_consistency_risk="low",
        )
        assert ra.trigger == RollbackTrigger.ERROR_RATE_SPIKE
        assert ra.blast_radius == ["svc-a", "svc-b"]
        assert ra.recommendations == []

    def test_with_recommendations(self):
        ra = RollbackAnalysis(
            trigger=RollbackTrigger.MANUAL,
            detection_time_seconds=120.0,
            rollback_time_seconds=30.0,
            total_impact_seconds=150.0,
            affected_requests_estimate=5000,
            blast_radius=[],
            data_consistency_risk="none",
            recommendations=["Check logs"],
        )
        assert ra.recommendations == ["Check logs"]


# ---------------------------------------------------------------------------
# FailedCanaryResult model tests
# ---------------------------------------------------------------------------


class TestFailedCanaryResultModel:
    def test_creation(self):
        ra = RollbackAnalysis(
            trigger=RollbackTrigger.ERROR_RATE_SPIKE,
            detection_time_seconds=10.0,
            rollback_time_seconds=30.0,
            total_impact_seconds=40.0,
            affected_requests_estimate=1000,
            blast_radius=[],
            data_consistency_risk="none",
        )
        fc = FailedCanaryResult(
            failure_percentage=25.0,
            steps_before_failure=3,
            detected_trigger=RollbackTrigger.ERROR_RATE_SPIKE,
            rollback_analysis=ra,
            total_duration_seconds=600.0,
        )
        assert fc.failure_percentage == 25.0
        assert fc.steps == []


# ---------------------------------------------------------------------------
# BlastRadiusEstimate model tests
# ---------------------------------------------------------------------------


class TestBlastRadiusEstimateModel:
    def test_creation(self):
        br = BlastRadiusEstimate(
            percentage=10.0,
            affected_components=["a", "b"],
            affected_request_ratio=0.1,
            estimated_error_impact=0.02,
            risk_level="low",
        )
        assert br.percentage == 10.0
        assert br.mitigation_suggestions == []


# ---------------------------------------------------------------------------
# StrategyComparison model tests
# ---------------------------------------------------------------------------


class TestStrategyComparisonModel:
    def test_creation(self):
        sc = StrategyComparison(
            strategy=DeploymentStrategy.CANARY,
            risk_score=20.0,
            rollback_time_seconds=30.0,
            blast_radius_size=2,
            recommended=True,
            pros=["Low risk"],
            cons=["Slow"],
        )
        assert sc.recommended is True
        assert len(sc.pros) == 1


# ---------------------------------------------------------------------------
# RollbackReadinessReport model tests
# ---------------------------------------------------------------------------


class TestRollbackReadinessReportModel:
    def test_creation(self):
        rr = RollbackReadinessReport(ready=True, score=80.0)
        assert rr.checks == {}
        assert rr.warnings == []
        assert rr.blockers == []


# ---------------------------------------------------------------------------
# simulate_canary tests
# ---------------------------------------------------------------------------


class TestSimulateCanary:
    def test_returns_empty_for_missing_component(self):
        g = _graph(_comp("a"))
        engine = CanaryRollbackEngine()
        result = engine.simulate_canary(g, "missing", CanaryConfig())
        assert result == []

    def test_healthy_component_completes(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        config = CanaryConfig(initial_percentage=50.0, step_percentage=50.0)
        steps = engine.simulate_canary(g, "svc", config)
        assert len(steps) >= 2
        assert steps[-1].traffic_percentage == 100.0

    def test_first_step_is_initial_split(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        steps = engine.simulate_canary(g, "svc", CanaryConfig())
        assert steps[0].phase == CanaryPhase.INITIAL_SPLIT

    def test_step_numbers_are_sequential(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        steps = engine.simulate_canary(g, "svc", CanaryConfig(initial_percentage=50.0, step_percentage=50.0))
        for i, s in enumerate(steps):
            assert s.step == i + 1

    def test_traffic_never_exceeds_100(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        steps = engine.simulate_canary(g, "svc", CanaryConfig(initial_percentage=30.0, step_percentage=40.0))
        for s in steps:
            assert s.traffic_percentage <= 100.0

    def test_rollback_on_degraded_component(self):
        g = _graph(_comp("svc", health=HealthStatus.DEGRADED))
        engine = CanaryRollbackEngine()
        config = CanaryConfig(max_error_rate=0.1, auto_rollback=True)
        steps = engine.simulate_canary(g, "svc", config)
        assert any(s.decision == "rollback" for s in steps)

    def test_rollback_on_down_component(self):
        g = _graph(_comp("svc", health=HealthStatus.DOWN))
        engine = CanaryRollbackEngine()
        config = CanaryConfig(max_error_rate=0.1, auto_rollback=True)
        steps = engine.simulate_canary(g, "svc", config)
        assert steps[0].decision == "rollback"

    def test_no_rollback_when_auto_rollback_disabled(self):
        g = _graph(_comp("svc", health=HealthStatus.DOWN))
        engine = CanaryRollbackEngine()
        config = CanaryConfig(auto_rollback=False)
        steps = engine.simulate_canary(g, "svc", config)
        assert all(s.decision != "rollback" for s in steps)

    def test_high_latency_triggers_rollback(self):
        g = _graph(_comp("svc", health=HealthStatus.OVERLOADED))
        engine = CanaryRollbackEngine()
        config = CanaryConfig(max_latency_p99_ms=100.0, auto_rollback=True)
        steps = engine.simulate_canary(g, "svc", config)
        assert any(s.decision == "rollback" for s in steps)

    def test_metrics_included_in_steps(self):
        g = _graph(_comp("svc", cpu_percent=50.0, memory_percent=60.0))
        engine = CanaryRollbackEngine()
        steps = engine.simulate_canary(g, "svc", CanaryConfig(initial_percentage=50.0, step_percentage=50.0))
        assert "cpu_percent" in steps[0].metrics
        assert "memory_percent" in steps[0].metrics

    def test_completed_phase_at_100_percent(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        config = CanaryConfig(initial_percentage=50.0, step_percentage=50.0)
        steps = engine.simulate_canary(g, "svc", config)
        final = steps[-1]
        assert final.traffic_percentage == 100.0
        assert final.phase == CanaryPhase.COMPLETED

    def test_single_step_to_100(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        config = CanaryConfig(initial_percentage=100.0, step_percentage=10.0)
        steps = engine.simulate_canary(g, "svc", config)
        # Initial split at 100% is already done
        assert len(steps) >= 1

    def test_rollback_during_progressive_step(self):
        """A degraded component triggers rollback in the progressive loop (not initial)."""
        g = _graph(_comp("svc", health=HealthStatus.DEGRADED))
        engine = CanaryRollbackEngine()
        # Error at 5% degraded ~ 0.5075, at 15% ~ 0.5225.
        # Set threshold just above 5% error rate but below later steps.
        config = CanaryConfig(
            initial_percentage=5.0,
            step_percentage=10.0,
            max_error_rate=0.52,
            auto_rollback=True,
        )
        steps = engine.simulate_canary(g, "svc", config)
        # Should rollback at some point in the progressive loop
        rollback_steps = [s for s in steps if s.decision == "rollback"]
        assert len(rollback_steps) > 0
        # Rollback should not be the initial step
        assert rollback_steps[0].step > 1

    def test_latency_rollback_in_progressive_loop(self):
        """Latency threshold triggers rollback during progressive steps."""
        g = _graph(_comp("svc", health=HealthStatus.OVERLOADED))
        engine = CanaryRollbackEngine()
        # Error rate for overloaded is ~2.6 at 5%, but set max_error_rate very high
        # so only latency triggers rollback. Latency at 5% overloaded = 800 * 1.025 ~ 820
        config = CanaryConfig(
            initial_percentage=5.0,
            step_percentage=10.0,
            max_error_rate=100.0,  # won't trigger on error
            max_latency_p99_ms=810.0,  # just below initial latency
            auto_rollback=True,
        )
        steps = engine.simulate_canary(g, "svc", config)
        rollback_steps = [s for s in steps if s.decision == "rollback"]
        assert len(rollback_steps) > 0

    def test_duration_uses_min_observation_for_first_step(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        config = CanaryConfig(min_observation_seconds=120)
        steps = engine.simulate_canary(g, "svc", config)
        assert steps[0].duration_seconds == 120

    def test_duration_uses_step_interval_for_subsequent(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        config = CanaryConfig(
            initial_percentage=50.0,
            step_percentage=50.0,
            step_interval_seconds=600,
        )
        steps = engine.simulate_canary(g, "svc", config)
        if len(steps) > 1:
            assert steps[1].duration_seconds == 600


# ---------------------------------------------------------------------------
# analyze_rollback tests
# ---------------------------------------------------------------------------


class TestAnalyzeRollback:
    def test_returns_analysis_for_existing_component(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "svc", RollbackTrigger.ERROR_RATE_SPIKE)
        assert isinstance(ra, RollbackAnalysis)
        assert ra.trigger == RollbackTrigger.ERROR_RATE_SPIKE

    def test_total_impact_is_detection_plus_rollback(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "svc", RollbackTrigger.MANUAL)
        assert ra.total_impact_seconds == ra.detection_time_seconds + ra.rollback_time_seconds

    def test_blast_radius_includes_dependents(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b, deps=[_dep("b", "a")])
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "a", RollbackTrigger.ERROR_RATE_SPIKE)
        assert "b" in ra.blast_radius

    def test_blast_radius_empty_for_leaf(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b, deps=[_dep("a", "b")])
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "a", RollbackTrigger.ERROR_RATE_SPIKE)
        assert ra.blast_radius == []

    def test_affected_requests_positive(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "svc", RollbackTrigger.ERROR_RATE_SPIKE)
        assert ra.affected_requests_estimate > 0

    def test_data_consistency_none_without_db(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "svc", RollbackTrigger.ERROR_RATE_SPIKE)
        assert ra.data_consistency_risk == "none"

    def test_data_consistency_with_db_dependency(self):
        svc = _comp("svc")
        db = _comp("db", ctype=ComponentType.DATABASE)
        g = _graph(svc, db, deps=[_dep("svc", "db")])
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "svc", RollbackTrigger.ERROR_RATE_SPIKE)
        assert ra.data_consistency_risk in ("low", "medium", "high")

    def test_data_consistency_high_for_db_component(self):
        db = _comp("db", ctype=ComponentType.DATABASE)
        g = _graph(db)
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "db", RollbackTrigger.ERROR_RATE_SPIKE)
        assert ra.data_consistency_risk == "high"

    def test_data_consistency_low_for_replicated_db_dep(self):
        svc = _comp("svc")
        db = _comp("db", ctype=ComponentType.DATABASE, replicas=3)
        g = _graph(svc, db, deps=[_dep("svc", "db")])
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "svc", RollbackTrigger.ERROR_RATE_SPIKE)
        assert ra.data_consistency_risk == "low"

    def test_recommendations_not_empty(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "svc", RollbackTrigger.ERROR_RATE_SPIKE)
        assert len(ra.recommendations) > 0

    def test_memory_leak_trigger_recommendation(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "svc", RollbackTrigger.MEMORY_LEAK)
        assert any("memory" in r.lower() for r in ra.recommendations)

    def test_crash_loop_trigger_recommendation(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "svc", RollbackTrigger.CRASH_LOOP)
        assert any("crash" in r.lower() for r in ra.recommendations)

    def test_detection_time_varies_by_trigger(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        ra_health = engine.analyze_rollback(g, "svc", RollbackTrigger.HEALTH_CHECK_FAILURE)
        ra_manual = engine.analyze_rollback(g, "svc", RollbackTrigger.MANUAL)
        assert ra_health.detection_time_seconds < ra_manual.detection_time_seconds

    def test_failover_reduces_rollback_time(self):
        svc_no_fo = _comp("svc1", failover_enabled=False)
        svc_fo = _comp("svc2", failover_enabled=True)
        g1 = _graph(svc_no_fo)
        g2 = _graph(svc_fo)
        engine = CanaryRollbackEngine()
        ra1 = engine.analyze_rollback(g1, "svc1", RollbackTrigger.ERROR_RATE_SPIKE)
        ra2 = engine.analyze_rollback(g2, "svc2", RollbackTrigger.ERROR_RATE_SPIKE)
        assert ra2.rollback_time_seconds <= ra1.rollback_time_seconds

    def test_missing_component_returns_analysis(self):
        g = _graph(_comp("a"))
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "missing", RollbackTrigger.ERROR_RATE_SPIKE)
        assert isinstance(ra, RollbackAnalysis)

    def test_multiple_replicas_reduce_rollback_time(self):
        svc1 = _comp("svc1", replicas=1)
        svc3 = _comp("svc3", replicas=3)
        g1 = _graph(svc1)
        g3 = _graph(svc3)
        engine = CanaryRollbackEngine()
        ra1 = engine.analyze_rollback(g1, "svc1", RollbackTrigger.ERROR_RATE_SPIKE)
        ra3 = engine.analyze_rollback(g3, "svc3", RollbackTrigger.ERROR_RATE_SPIKE)
        assert ra3.rollback_time_seconds <= ra1.rollback_time_seconds


# ---------------------------------------------------------------------------
# recommend_strategy tests
# ---------------------------------------------------------------------------


class TestRecommendStrategy:
    def test_returns_canary_config(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "svc")
        assert isinstance(cfg, CanaryConfig)

    def test_database_recommends_blue_green(self):
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "db")
        assert cfg.strategy == DeploymentStrategy.BLUE_GREEN

    def test_high_replica_no_db_recommends_rolling(self):
        g = _graph(_comp("svc", replicas=3))
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "svc")
        assert cfg.strategy == DeploymentStrategy.ROLLING

    def test_load_balancer_recommends_blue_green(self):
        g = _graph(_comp("lb", ctype=ComponentType.LOAD_BALANCER))
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "lb")
        assert cfg.strategy == DeploymentStrategy.BLUE_GREEN

    def test_missing_component_returns_defaults(self):
        g = _graph(_comp("a"))
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "missing")
        assert cfg.strategy == DeploymentStrategy.CANARY

    def test_auto_rollback_always_true(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "svc")
        assert cfg.auto_rollback is True

    def test_rollback_triggers_include_error_rate(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "svc")
        assert RollbackTrigger.ERROR_RATE_SPIKE in cfg.rollback_on

    def test_rollback_triggers_include_health_check(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "svc")
        assert RollbackTrigger.HEALTH_CHECK_FAILURE in cfg.rollback_on

    def test_db_dependency_adds_slo_violation_trigger(self):
        svc = _comp("svc")
        db = _comp("db", ctype=ComponentType.DATABASE)
        g = _graph(svc, db, deps=[_dep("svc", "db")])
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "svc")
        assert RollbackTrigger.SLO_VIOLATION in cfg.rollback_on

    def test_high_memory_adds_memory_leak_trigger(self):
        svc = _comp("svc", memory_percent=85.0)
        g = _graph(svc)
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "svc")
        assert RollbackTrigger.MEMORY_LEAK in cfg.rollback_on

    def test_high_cpu_adds_cpu_spike_trigger(self):
        svc = _comp("svc", cpu_percent=90.0)
        g = _graph(svc)
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "svc")
        assert RollbackTrigger.CPU_SPIKE in cfg.rollback_on

    def test_many_dependents_lowers_initial_percentage(self):
        svc = _comp("svc")
        comps = [svc] + [_comp(f"d{i}") for i in range(7)]
        deps_list = [_dep(f"d{i}", "svc") for i in range(7)]
        g = _graph(*comps, deps=deps_list)
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "svc")
        assert cfg.initial_percentage <= 5.0

    def test_slo_latency_target_used_for_max_latency(self):
        svc = _comp(
            "svc",
            slo_targets=[SLOTarget(name="p99", metric="latency_p99", target=200.0)],
        )
        g = _graph(svc)
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "svc")
        assert cfg.max_latency_p99_ms == 200.0

    def test_db_component_has_stricter_error_rate(self):
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "db")
        assert cfg.max_error_rate < 1.0

    def test_single_replica_with_db_recommends_recreate(self):
        svc = _comp("svc", replicas=1)
        db = _comp("db", ctype=ComponentType.DATABASE)
        g = _graph(svc, db, deps=[_dep("svc", "db")])
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "svc")
        assert cfg.strategy == DeploymentStrategy.RECREATE


# ---------------------------------------------------------------------------
# simulate_failed_canary tests
# ---------------------------------------------------------------------------


class TestSimulateFailedCanary:
    def test_returns_failed_result(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        result = engine.simulate_failed_canary(g, "svc", 25.0)
        assert isinstance(result, FailedCanaryResult)
        assert result.failure_percentage == 25.0

    def test_steps_before_failure_count(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        result = engine.simulate_failed_canary(g, "svc", 25.0)
        assert result.steps_before_failure >= 0

    def test_last_step_is_rollback(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        result = engine.simulate_failed_canary(g, "svc", 25.0)
        assert result.steps[-1].decision == "rollback"

    def test_rollback_analysis_included(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        result = engine.simulate_failed_canary(g, "svc", 25.0)
        assert isinstance(result.rollback_analysis, RollbackAnalysis)

    def test_total_duration_positive(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        result = engine.simulate_failed_canary(g, "svc", 25.0)
        assert result.total_duration_seconds > 0

    def test_higher_failure_pct_more_steps(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        r10 = engine.simulate_failed_canary(g, "svc", 10.0)
        r50 = engine.simulate_failed_canary(g, "svc", 50.0)
        assert r50.steps_before_failure >= r10.steps_before_failure

    def test_missing_component_returns_result(self):
        g = _graph(_comp("a"))
        engine = CanaryRollbackEngine()
        result = engine.simulate_failed_canary(g, "missing", 10.0)
        assert isinstance(result, FailedCanaryResult)
        assert result.steps_before_failure == 0

    def test_trigger_detection_down_component(self):
        g = _graph(_comp("svc", health=HealthStatus.DOWN))
        engine = CanaryRollbackEngine()
        result = engine.simulate_failed_canary(g, "svc", 30.0)
        assert result.detected_trigger == RollbackTrigger.CRASH_LOOP

    def test_trigger_detection_high_memory(self):
        g = _graph(_comp("svc", memory_percent=90.0))
        engine = CanaryRollbackEngine()
        result = engine.simulate_failed_canary(g, "svc", 30.0)
        assert result.detected_trigger == RollbackTrigger.MEMORY_LEAK

    def test_trigger_detection_high_cpu(self):
        g = _graph(_comp("svc", cpu_percent=90.0))
        engine = CanaryRollbackEngine()
        result = engine.simulate_failed_canary(g, "svc", 30.0)
        assert result.detected_trigger == RollbackTrigger.CPU_SPIKE

    def test_high_pct_triggers_latency_degradation(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        result = engine.simulate_failed_canary(g, "svc", 80.0)
        assert result.detected_trigger == RollbackTrigger.LATENCY_DEGRADATION

    def test_failure_at_5_percent(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        result = engine.simulate_failed_canary(g, "svc", 5.0)
        assert result.failure_percentage == 5.0
        assert len(result.steps) >= 1


# ---------------------------------------------------------------------------
# estimate_blast_radius tests
# ---------------------------------------------------------------------------


class TestEstimateBlastRadius:
    def test_returns_estimate(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "svc", 10.0)
        assert isinstance(br, BlastRadiusEstimate)
        assert br.percentage == 10.0

    def test_ratio_matches_percentage(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "svc", 50.0)
        assert br.affected_request_ratio == pytest.approx(0.5)

    def test_affected_components_from_graph(self):
        a = _comp("a")
        b = _comp("b")
        c = _comp("c")
        g = _graph(a, b, c, deps=[_dep("b", "a"), _dep("c", "a")])
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "a", 20.0)
        assert "b" in br.affected_components
        assert "c" in br.affected_components

    def test_no_affected_for_leaf(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b, deps=[_dep("a", "b")])
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "a", 10.0)
        assert br.affected_components == []

    def test_low_risk_at_small_percentage(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "svc", 5.0)
        assert br.risk_level == "low"

    def test_critical_risk_at_high_percentage_with_deps(self):
        svc = _comp("svc")
        comps = [svc] + [_comp(f"d{i}") for i in range(10)]
        dep_list = [_dep(f"d{i}", "svc") for i in range(10)]
        g = _graph(*comps, deps=dep_list)
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "svc", 90.0)
        assert br.risk_level in ("high", "critical")

    def test_mitigation_suggestions_not_empty(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "svc", 50.0)
        assert len(br.mitigation_suggestions) > 0

    def test_mitigation_add_replicas_for_single_replica(self):
        g = _graph(_comp("svc", replicas=1))
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "svc", 60.0)
        assert any("replica" in s.lower() for s in br.mitigation_suggestions)

    def test_mitigation_autoscaling_suggestion(self):
        g = _graph(_comp("svc", autoscaling_enabled=False))
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "svc", 60.0)
        assert any("autoscaling" in s.lower() for s in br.mitigation_suggestions)

    def test_missing_component_returns_estimate(self):
        g = _graph(_comp("a"))
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "missing", 10.0)
        assert isinstance(br, BlastRadiusEstimate)

    def test_100_percent_ratio(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "svc", 100.0)
        assert br.affected_request_ratio == pytest.approx(1.0)

    def test_circuit_breaker_mitigation_suggestion(self):
        svc = _comp("svc")
        dep = _comp("dep")
        g = _graph(svc, dep, deps=[_dep("dep", "svc", cb_enabled=False)])
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "svc", 60.0)
        assert any("circuit breaker" in s.lower() for s in br.mitigation_suggestions)

    def test_adequate_mitigation_for_well_configured(self):
        """A well-configured component at low % gets 'adequate' suggestion."""
        svc = _comp("svc", replicas=3, autoscaling_enabled=True)
        g = _graph(svc)
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "svc", 5.0)
        assert any("adequate" in s.lower() for s in br.mitigation_suggestions)


# ---------------------------------------------------------------------------
# compare_strategies tests
# ---------------------------------------------------------------------------


class TestCompareStrategies:
    def test_returns_all_strategies(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        results = engine.compare_strategies(g, "svc")
        assert len(results) == len(DeploymentStrategy)

    def test_exactly_one_recommended(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        results = engine.compare_strategies(g, "svc")
        recommended = [r for r in results if r.recommended]
        assert len(recommended) == 1

    def test_each_has_pros_and_cons(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        results = engine.compare_strategies(g, "svc")
        for r in results:
            assert len(r.pros) > 0
            assert len(r.cons) > 0

    def test_shadow_has_lowest_risk(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        results = engine.compare_strategies(g, "svc")
        shadow = next(r for r in results if r.strategy == DeploymentStrategy.SHADOW)
        recreate = next(r for r in results if r.strategy == DeploymentStrategy.RECREATE)
        assert shadow.risk_score < recreate.risk_score

    def test_blue_green_fastest_rollback(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        results = engine.compare_strategies(g, "svc")
        bg = next(r for r in results if r.strategy == DeploymentStrategy.BLUE_GREEN)
        recreate = next(r for r in results if r.strategy == DeploymentStrategy.RECREATE)
        assert bg.rollback_time_seconds < recreate.rollback_time_seconds

    def test_blast_radius_size_consistent(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b, deps=[_dep("b", "a")])
        engine = CanaryRollbackEngine()
        results = engine.compare_strategies(g, "a")
        sizes = {r.blast_radius_size for r in results}
        assert len(sizes) == 1  # all same

    def test_missing_component_returns_comparisons(self):
        g = _graph(_comp("a"))
        engine = CanaryRollbackEngine()
        results = engine.compare_strategies(g, "missing")
        assert len(results) == len(DeploymentStrategy)

    def test_risk_score_capped_at_100(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        results = engine.compare_strategies(g, "svc")
        for r in results:
            assert r.risk_score <= 100.0

    def test_failover_reduces_rollback_time(self):
        g = _graph(_comp("svc", failover_enabled=True))
        engine = CanaryRollbackEngine()
        results = engine.compare_strategies(g, "svc")
        g2 = _graph(_comp("svc2", failover_enabled=False))
        results2 = engine.compare_strategies(g2, "svc2")
        for r, r2 in zip(
            sorted(results, key=lambda x: x.strategy.value),
            sorted(results2, key=lambda x: x.strategy.value),
        ):
            assert r.rollback_time_seconds <= r2.rollback_time_seconds

    def test_single_replica_increases_risk(self):
        g1 = _graph(_comp("s1", replicas=1))
        g3 = _graph(_comp("s3", replicas=3))
        engine = CanaryRollbackEngine()
        r1 = engine.compare_strategies(g1, "s1")
        r3 = engine.compare_strategies(g3, "s3")
        # canary risk should be higher for single replica
        canary1 = next(r for r in r1 if r.strategy == DeploymentStrategy.CANARY)
        canary3 = next(r for r in r3 if r.strategy == DeploymentStrategy.CANARY)
        assert canary1.risk_score > canary3.risk_score


# ---------------------------------------------------------------------------
# validate_rollback_readiness tests
# ---------------------------------------------------------------------------


class TestValidateRollbackReadiness:
    def test_missing_component_not_ready(self):
        g = _graph(_comp("a"))
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "missing")
        assert rr.ready is False
        assert "Component not found" in rr.blockers

    def test_healthy_component_has_checks(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert "healthy" in rr.checks
        assert rr.checks["healthy"] is True

    def test_unhealthy_component_blocked(self):
        g = _graph(_comp("svc", health=HealthStatus.DOWN))
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert rr.ready is False
        assert any("not healthy" in b for b in rr.blockers)

    def test_single_replica_warning(self):
        g = _graph(_comp("svc", replicas=1))
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert any("replica" in w.lower() for w in rr.warnings)

    def test_multiple_replicas_no_replica_warning(self):
        g = _graph(_comp("svc", replicas=3))
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert not any("Single replica" in w for w in rr.warnings)

    def test_failover_disabled_warning(self):
        g = _graph(_comp("svc", failover_enabled=False))
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert any("failover" in w.lower() for w in rr.warnings)

    def test_failover_enabled_no_warning(self):
        g = _graph(_comp("svc", failover_enabled=True))
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert not any("Failover" in w for w in rr.warnings)

    def test_autoscaling_disabled_warning(self):
        g = _graph(_comp("svc", autoscaling_enabled=False))
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert any("autoscaling" in w.lower() for w in rr.warnings)

    def test_no_slo_targets_warning(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert any("SLO" in w or "monitoring" in w.lower() for w in rr.warnings)

    def test_with_slo_targets_no_monitoring_warning(self):
        svc = _comp(
            "svc",
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        )
        g = _graph(svc)
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert not any("monitoring" in w.lower() for w in rr.warnings)

    def test_unreplicated_db_dependency_blocker(self):
        svc = _comp("svc")
        db = _comp("db", ctype=ComponentType.DATABASE, replicas=1)
        g = _graph(svc, db, deps=[_dep("svc", "db")])
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert any("database" in b.lower() for b in rr.blockers)

    def test_replicated_db_no_blocker(self):
        svc = _comp("svc")
        db = _comp("db", ctype=ComponentType.DATABASE, replicas=3)
        g = _graph(svc, db, deps=[_dep("svc", "db")])
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert not any("database" in b.lower() for b in rr.blockers)

    def test_circuit_breaker_coverage_check(self):
        svc = _comp("svc")
        upstream = _comp("up")
        g = _graph(svc, upstream, deps=[_dep("up", "svc", cb_enabled=True)])
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert rr.checks.get("circuit_breaker_coverage") is True

    def test_no_circuit_breaker_warns(self):
        svc = _comp("svc")
        upstream = _comp("up")
        g = _graph(svc, upstream, deps=[_dep("up", "svc", cb_enabled=False)])
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert any("circuit breaker" in w.lower() for w in rr.warnings)

    def test_score_range(self):
        g = _graph(_comp("svc"))
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert 0.0 <= rr.score <= 100.0

    def test_fully_ready_component(self):
        svc = _comp(
            "svc",
            replicas=3,
            failover_enabled=True,
            autoscaling_enabled=True,
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        )
        upstream = _comp("up")
        g = _graph(svc, upstream, deps=[_dep("up", "svc", cb_enabled=True)])
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "svc")
        assert rr.ready is True
        assert rr.score >= 80.0

    def test_score_0_for_missing_component(self):
        g = _graph(_comp("a"))
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "missing")
        assert rr.score == 0.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_graph_simulate(self):
        g = InfraGraph()
        engine = CanaryRollbackEngine()
        assert engine.simulate_canary(g, "x", CanaryConfig()) == []

    def test_empty_graph_analyze_rollback(self):
        g = InfraGraph()
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "x", RollbackTrigger.MANUAL)
        assert isinstance(ra, RollbackAnalysis)

    def test_empty_graph_recommend(self):
        g = InfraGraph()
        engine = CanaryRollbackEngine()
        cfg = engine.recommend_strategy(g, "x")
        assert isinstance(cfg, CanaryConfig)

    def test_empty_graph_blast_radius(self):
        g = InfraGraph()
        engine = CanaryRollbackEngine()
        br = engine.estimate_blast_radius(g, "x", 10.0)
        assert isinstance(br, BlastRadiusEstimate)

    def test_empty_graph_compare_strategies(self):
        g = InfraGraph()
        engine = CanaryRollbackEngine()
        results = engine.compare_strategies(g, "x")
        assert len(results) == len(DeploymentStrategy)

    def test_empty_graph_readiness(self):
        g = InfraGraph()
        engine = CanaryRollbackEngine()
        rr = engine.validate_rollback_readiness(g, "x")
        assert rr.ready is False

    def test_isolated_component_no_deps(self):
        g = _graph(_comp("solo"))
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "solo", RollbackTrigger.ERROR_RATE_SPIKE)
        assert ra.blast_radius == []

    def test_chain_cascade(self):
        a = _comp("a")
        b = _comp("b")
        c = _comp("c")
        g = _graph(a, b, c, deps=[_dep("b", "a"), _dep("c", "b")])
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "a", RollbackTrigger.ERROR_RATE_SPIKE)
        assert "b" in ra.blast_radius
        assert "c" in ra.blast_radius

    def test_large_graph_performance(self):
        comps = [_comp(f"svc-{i}") for i in range(50)]
        dep_list = [_dep(f"svc-{i}", "svc-0") for i in range(1, 50)]
        g = _graph(*comps, deps=dep_list)
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "svc-0", RollbackTrigger.ERROR_RATE_SPIKE)
        assert len(ra.blast_radius) == 49

    def test_diamond_dependency(self):
        a = _comp("a")
        b = _comp("b")
        c = _comp("c")
        d = _comp("d")
        g = _graph(a, b, c, d, deps=[
            _dep("b", "a"),
            _dep("c", "a"),
            _dep("d", "b"),
            _dep("d", "c"),
        ])
        engine = CanaryRollbackEngine()
        ra = engine.analyze_rollback(g, "a", RollbackTrigger.ERROR_RATE_SPIKE)
        assert "b" in ra.blast_radius
        assert "c" in ra.blast_radius
        assert "d" in ra.blast_radius


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_canary_lifecycle(self):
        """End-to-end: recommend -> validate -> simulate -> compare."""
        svc = _comp("api", replicas=2, failover_enabled=True)
        db = _comp("db", ctype=ComponentType.DATABASE, replicas=2)
        g = _graph(svc, db, deps=[_dep("api", "db")])
        engine = CanaryRollbackEngine()

        cfg = engine.recommend_strategy(g, "api")
        rr = engine.validate_rollback_readiness(g, "api")
        steps = engine.simulate_canary(g, "api", cfg)
        comparisons = engine.compare_strategies(g, "api")

        assert isinstance(cfg, CanaryConfig)
        assert isinstance(rr, RollbackReadinessReport)
        assert len(steps) > 0
        assert len(comparisons) == len(DeploymentStrategy)

    def test_failed_canary_then_blast_radius(self):
        """Canary failure -> blast radius check."""
        svc = _comp("web")
        cache = _comp("cache", ctype=ComponentType.CACHE)
        g = _graph(svc, cache, deps=[_dep("web", "cache")])
        engine = CanaryRollbackEngine()

        failed = engine.simulate_failed_canary(g, "web", 30.0)
        br = engine.estimate_blast_radius(g, "web", failed.failure_percentage)

        assert isinstance(failed, FailedCanaryResult)
        assert isinstance(br, BlastRadiusEstimate)

    def test_rollback_analysis_after_failure(self):
        """Simulate failure, then analyse rollback with detected trigger."""
        svc = _comp("svc")
        g = _graph(svc)
        engine = CanaryRollbackEngine()

        failed = engine.simulate_failed_canary(g, "svc", 20.0)
        ra = engine.analyze_rollback(g, "svc", failed.detected_trigger)

        assert ra.trigger == failed.detected_trigger

    def test_three_tier_architecture(self):
        """LB -> App -> DB chain."""
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER)
        app = _comp("app", replicas=3)
        db = _comp("db", ctype=ComponentType.DATABASE, replicas=2)
        g = _graph(lb, app, db, deps=[_dep("lb", "app"), _dep("app", "db")])
        engine = CanaryRollbackEngine()

        # DB failure affects app and lb
        ra = engine.analyze_rollback(g, "db", RollbackTrigger.ERROR_RATE_SPIKE)
        assert "app" in ra.blast_radius

        # App has rolling strategy (3 replicas, no db)
        cfg_app = engine.recommend_strategy(g, "app")
        assert isinstance(cfg_app, CanaryConfig)

        # DB gets blue-green
        cfg_db = engine.recommend_strategy(g, "db")
        assert cfg_db.strategy == DeploymentStrategy.BLUE_GREEN

    def test_stateless_engine_reuse(self):
        """Same engine instance can process multiple graphs."""
        engine = CanaryRollbackEngine()
        g1 = _graph(_comp("a"))
        g2 = _graph(_comp("b"))

        r1 = engine.simulate_canary(g1, "a", CanaryConfig(initial_percentage=50.0, step_percentage=50.0))
        r2 = engine.simulate_canary(g2, "b", CanaryConfig(initial_percentage=50.0, step_percentage=50.0))

        assert len(r1) > 0
        assert len(r2) > 0
        assert r1[0].metrics["traffic_percentage"] == 50.0
        assert r2[0].metrics["traffic_percentage"] == 50.0
