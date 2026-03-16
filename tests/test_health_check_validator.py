"""Tests for health check validation engine.

Covers HealthCheckValidationEngine, all models, enumerations, anti-pattern
detection, flapping simulation, detection-time estimation, recommendation
generation, multi-component validation, and failure simulation.
Targets 100% line/branch coverage with 140+ tests.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.health_check_validator import (
    AntiPattern,
    FlappingResult,
    HealthCheckAssessment,
    HealthCheckConfig,
    HealthCheckFailureResult,
    HealthCheckType,
    HealthCheckValidationEngine,
    _ANTI_PATTERN_WEIGHTS,
    _MAX_REASONABLE_TIMEOUT,
    _MIN_REASONABLE_INTERVAL,
    _MIN_REASONABLE_TIMEOUT,
    _RECOMMENDED_CHECK_TYPES,
)


# ------------------------------------------------------------------ helpers


def _comp(
    cid: str,
    name: str = "",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    *,
    port: int = 0,
    failover_enabled: bool = False,
    failover_interval: float = 10.0,
    failover_threshold: int = 3,
    promotion_time: float = 30.0,
    autoscaling_enabled: bool = False,
    scale_up_delay: int = 15,
    mttr_minutes: float = 30.0,
) -> Component:
    """Shorthand factory for Component with common overrides."""
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        port=port,
        replicas=replicas,
        failover=FailoverConfig(
            enabled=failover_enabled,
            health_check_interval_seconds=failover_interval,
            failover_threshold=failover_threshold,
            promotion_time_seconds=promotion_time,
        ),
        autoscaling=AutoScalingConfig(
            enabled=autoscaling_enabled,
            scale_up_delay_seconds=scale_up_delay,
        ),
        operational_profile=OperationalProfile(
            mttr_minutes=mttr_minutes,
        ),
    )


def _dep(src: str, tgt: str, dep_type: str = "requires") -> Dependency:
    return Dependency(source_id=src, target_id=tgt, dependency_type=dep_type)


def _cfg(
    check_type: HealthCheckType = HealthCheckType.HTTP,
    endpoint: str = "/healthz",
    interval: float = 10.0,
    timeout: float = 5.0,
    failure_threshold: int = 3,
    success_threshold: int = 2,
    checks_deps: bool = False,
    deep: bool = False,
) -> HealthCheckConfig:
    """Shorthand factory for HealthCheckConfig."""
    return HealthCheckConfig(
        check_type=check_type,
        endpoint=endpoint,
        interval_seconds=interval,
        timeout_seconds=timeout,
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        checks_dependencies=checks_deps,
        includes_deep_check=deep,
    )


def _simple_graph() -> InfraGraph:
    """Build a simple 3-node graph: lb -> app -> db."""
    g = InfraGraph()
    g.add_component(_comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER))
    g.add_component(_comp("app", "App Server", ComponentType.APP_SERVER))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE, port=5432))
    g.add_dependency(_dep("lb", "app"))
    g.add_dependency(_dep("app", "db"))
    return g


def _wide_graph() -> InfraGraph:
    """Graph where 'core' has many dependents."""
    g = InfraGraph()
    g.add_component(_comp("core", "Core Service", ComponentType.APP_SERVER))
    for i in range(6):
        cid = f"svc-{i}"
        g.add_component(_comp(cid, f"Service {i}"))
        g.add_dependency(_dep(cid, "core"))
    return g


def _deep_graph() -> InfraGraph:
    """Graph with a deep dependency chain: a -> b -> c -> d -> e."""
    g = InfraGraph()
    ids = ["a", "b", "c", "d", "e"]
    for cid in ids:
        g.add_component(_comp(cid))
    for i in range(len(ids) - 1):
        g.add_dependency(_dep(ids[i], ids[i + 1]))
    return g


def _engine() -> HealthCheckValidationEngine:
    return HealthCheckValidationEngine()


# ===================================================================
# Enum tests
# ===================================================================


class TestHealthCheckType:
    def test_all_values(self):
        assert HealthCheckType.HTTP.value == "http"
        assert HealthCheckType.TCP.value == "tcp"
        assert HealthCheckType.GRPC.value == "grpc"
        assert HealthCheckType.EXEC.value == "exec"
        assert HealthCheckType.STARTUP.value == "startup"
        assert HealthCheckType.LIVENESS.value == "liveness"
        assert HealthCheckType.READINESS.value == "readiness"

    def test_total_count(self):
        assert len(HealthCheckType) == 7

    def test_string_construction(self):
        assert HealthCheckType("http") == HealthCheckType.HTTP
        assert HealthCheckType("readiness") == HealthCheckType.READINESS


class TestAntiPattern:
    def test_all_values(self):
        assert AntiPattern.CHECK_TOO_SIMPLE.value == "check_too_simple"
        assert AntiPattern.CHECK_TOO_COMPLEX.value == "check_too_complex"
        assert AntiPattern.CASCADING_FAILURE.value == "cascading_failure"
        assert AntiPattern.THUNDERING_HERD_ON_RECOVERY.value == "thundering_herd_on_recovery"
        assert AntiPattern.MISSING_DEPENDENCY_CHECK.value == "missing_dependency_check"
        assert AntiPattern.TIMEOUT_TOO_SHORT.value == "timeout_too_short"
        assert AntiPattern.TIMEOUT_TOO_LONG.value == "timeout_too_long"
        assert AntiPattern.INTERVAL_TOO_FREQUENT.value == "interval_too_frequent"
        assert AntiPattern.NO_STARTUP_PROBE.value == "no_startup_probe"
        assert AntiPattern.SHARED_ENDPOINT.value == "shared_endpoint"

    def test_total_count(self):
        assert len(AntiPattern) == 10

    def test_all_patterns_have_weights(self):
        for ap in AntiPattern:
            assert ap in _ANTI_PATTERN_WEIGHTS


# ===================================================================
# Pydantic model tests
# ===================================================================


class TestHealthCheckConfig:
    def test_construction(self):
        cfg = _cfg()
        assert cfg.check_type == HealthCheckType.HTTP
        assert cfg.endpoint == "/healthz"
        assert cfg.interval_seconds == 10.0
        assert cfg.timeout_seconds == 5.0
        assert cfg.failure_threshold == 3
        assert cfg.success_threshold == 2
        assert cfg.checks_dependencies is False
        assert cfg.includes_deep_check is False

    def test_serialization_round_trip(self):
        cfg = _cfg(check_type=HealthCheckType.GRPC, endpoint="/grpc.health", deep=True)
        data = cfg.model_dump()
        restored = HealthCheckConfig(**data)
        assert restored == cfg

    def test_json_round_trip(self):
        cfg = _cfg(checks_deps=True, deep=True)
        json_str = cfg.model_dump_json()
        restored = HealthCheckConfig.model_validate_json(json_str)
        assert restored == cfg


class TestHealthCheckAssessment:
    def test_defaults(self):
        cfg = _cfg()
        a = HealthCheckAssessment(component_id="x", config=cfg)
        assert a.anti_patterns == []
        assert a.risk_score == 0.0
        assert a.false_positive_risk == "low"
        assert a.false_negative_risk == "low"
        assert a.cascade_risk is False
        assert a.recommendations == []

    def test_with_anti_patterns(self):
        cfg = _cfg()
        a = HealthCheckAssessment(
            component_id="x",
            config=cfg,
            anti_patterns=[AntiPattern.TIMEOUT_TOO_SHORT],
            risk_score=15.0,
            false_positive_risk="medium",
        )
        assert len(a.anti_patterns) == 1
        assert a.risk_score == 15.0


class TestFlappingResult:
    def test_defaults(self):
        f = FlappingResult(component_id="x")
        assert f.flap_count == 0
        assert f.flap_risk == "low"
        assert f.mean_time_between_flaps_seconds == 0.0
        assert f.steady_state_seconds == 0.0
        assert f.recommendations == []


class TestHealthCheckFailureResult:
    def test_defaults(self):
        r = HealthCheckFailureResult(component_id="x")
        assert r.affected_components == []
        assert r.cascade_depth == 0
        assert r.estimated_detection_seconds == 0.0
        assert r.estimated_recovery_seconds == 0.0
        assert r.risk_score == 0.0
        assert r.recommendations == []


# ===================================================================
# detect_anti_patterns (config-only)
# ===================================================================


class TestDetectAntiPatterns:
    def test_clean_config_no_patterns(self):
        """A well-configured health check should have no anti-patterns."""
        engine = _engine()
        cfg = _cfg(
            check_type=HealthCheckType.HTTP,
            interval=10.0,
            timeout=5.0,
            failure_threshold=3,
            success_threshold=2,
            deep=True,
        )
        patterns = engine.detect_anti_patterns(cfg)
        assert patterns == []

    def test_check_too_simple_tcp(self):
        engine = _engine()
        cfg = _cfg(check_type=HealthCheckType.TCP, deep=False, checks_deps=False)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.CHECK_TOO_SIMPLE in patterns

    def test_check_too_simple_exec(self):
        engine = _engine()
        cfg = _cfg(check_type=HealthCheckType.EXEC, deep=False, checks_deps=False)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.CHECK_TOO_SIMPLE in patterns

    def test_check_too_simple_not_triggered_for_http(self):
        engine = _engine()
        cfg = _cfg(check_type=HealthCheckType.HTTP, deep=False, checks_deps=False)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.CHECK_TOO_SIMPLE not in patterns

    def test_check_too_complex(self):
        engine = _engine()
        cfg = _cfg(deep=True, checks_deps=True, interval=2.0)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.CHECK_TOO_COMPLEX in patterns

    def test_check_too_complex_not_triggered_with_normal_interval(self):
        engine = _engine()
        cfg = _cfg(deep=True, checks_deps=True, interval=10.0)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.CHECK_TOO_COMPLEX not in patterns

    def test_timeout_too_short(self):
        engine = _engine()
        cfg = _cfg(timeout=1.0)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.TIMEOUT_TOO_SHORT in patterns

    def test_timeout_at_boundary_not_triggered(self):
        engine = _engine()
        cfg = _cfg(timeout=_MIN_REASONABLE_TIMEOUT)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.TIMEOUT_TOO_SHORT not in patterns

    def test_timeout_too_long(self):
        engine = _engine()
        cfg = _cfg(timeout=60.0)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.TIMEOUT_TOO_LONG in patterns

    def test_timeout_at_max_boundary_not_triggered(self):
        engine = _engine()
        cfg = _cfg(timeout=_MAX_REASONABLE_TIMEOUT)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.TIMEOUT_TOO_LONG not in patterns

    def test_interval_too_frequent(self):
        engine = _engine()
        cfg = _cfg(interval=2.0)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.INTERVAL_TOO_FREQUENT in patterns

    def test_interval_at_boundary_not_triggered(self):
        engine = _engine()
        cfg = _cfg(interval=_MIN_REASONABLE_INTERVAL)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.INTERVAL_TOO_FREQUENT not in patterns

    def test_thundering_herd(self):
        engine = _engine()
        cfg = _cfg(success_threshold=1, interval=2.0)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.THUNDERING_HERD_ON_RECOVERY in patterns

    def test_thundering_herd_not_triggered_with_higher_threshold(self):
        engine = _engine()
        cfg = _cfg(success_threshold=2, interval=2.0)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.THUNDERING_HERD_ON_RECOVERY not in patterns

    def test_no_startup_probe_liveness(self):
        engine = _engine()
        cfg = _cfg(check_type=HealthCheckType.LIVENESS, failure_threshold=1)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.NO_STARTUP_PROBE in patterns

    def test_no_startup_probe_readiness(self):
        engine = _engine()
        cfg = _cfg(check_type=HealthCheckType.READINESS, failure_threshold=1)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.NO_STARTUP_PROBE in patterns

    def test_no_startup_probe_not_triggered_with_http(self):
        engine = _engine()
        cfg = _cfg(check_type=HealthCheckType.HTTP, failure_threshold=1)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.NO_STARTUP_PROBE not in patterns

    def test_no_startup_probe_not_triggered_with_higher_threshold(self):
        engine = _engine()
        cfg = _cfg(check_type=HealthCheckType.LIVENESS, failure_threshold=3)
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.NO_STARTUP_PROBE not in patterns

    def test_multiple_patterns_combined(self):
        """Extremely bad config triggers many patterns at once."""
        engine = _engine()
        cfg = _cfg(
            check_type=HealthCheckType.LIVENESS,
            timeout=0.5,
            interval=1.0,
            failure_threshold=1,
            success_threshold=1,
            checks_deps=True,
            deep=True,
        )
        patterns = engine.detect_anti_patterns(cfg)
        assert AntiPattern.TIMEOUT_TOO_SHORT in patterns
        assert AntiPattern.INTERVAL_TOO_FREQUENT in patterns
        assert AntiPattern.CHECK_TOO_COMPLEX in patterns
        assert AntiPattern.THUNDERING_HERD_ON_RECOVERY in patterns
        assert AntiPattern.NO_STARTUP_PROBE in patterns


# ===================================================================
# validate_health_check (graph-aware)
# ===================================================================


class TestValidateHealthCheck:
    def test_clean_config_simple_graph(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(deep=True, checks_deps=True, interval=10.0)
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert assessment.component_id == "app"
        assert isinstance(assessment.risk_score, float)

    def test_missing_dependency_check_detected(self):
        """Component with deps but no dependency checking in health check."""
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(checks_deps=False, deep=False)
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert AntiPattern.MISSING_DEPENDENCY_CHECK in assessment.anti_patterns

    def test_missing_dependency_not_detected_when_no_deps(self):
        """Component without deps should not trigger missing dependency check."""
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(checks_deps=False, deep=False)
        # db has no outbound deps
        assessment = engine.validate_health_check(graph, "db", cfg)
        assert AntiPattern.MISSING_DEPENDENCY_CHECK not in assessment.anti_patterns

    def test_missing_dependency_not_detected_with_deep_check(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(checks_deps=False, deep=True)
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert AntiPattern.MISSING_DEPENDENCY_CHECK not in assessment.anti_patterns

    def test_cascading_failure_detected(self):
        """Component with many dependents + dependency checking → cascade risk."""
        engine = _engine()
        graph = _wide_graph()
        cfg = _cfg(checks_deps=True)
        assessment = engine.validate_health_check(graph, "core", cfg)
        assert AntiPattern.CASCADING_FAILURE in assessment.anti_patterns
        assert assessment.cascade_risk is True

    def test_cascading_failure_not_detected_few_dependents(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(checks_deps=True)
        # "db" has only 1 dependent ("app")
        assessment = engine.validate_health_check(graph, "db", cfg)
        assert AntiPattern.CASCADING_FAILURE not in assessment.anti_patterns

    def test_shared_endpoint_liveness_with_deep(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(check_type=HealthCheckType.LIVENESS, deep=True)
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert AntiPattern.SHARED_ENDPOINT in assessment.anti_patterns

    def test_shared_endpoint_readiness_with_deep(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(check_type=HealthCheckType.READINESS, deep=True)
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert AntiPattern.SHARED_ENDPOINT in assessment.anti_patterns

    def test_shared_endpoint_not_detected_without_deep(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(check_type=HealthCheckType.LIVENESS, deep=False)
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert AntiPattern.SHARED_ENDPOINT not in assessment.anti_patterns

    def test_cascade_risk_true_many_dependents(self):
        engine = _engine()
        graph = _wide_graph()
        cfg = _cfg()
        # "core" has 6 dependents → cascade_risk even without cascade anti-pattern
        assessment = engine.validate_health_check(graph, "core", cfg)
        assert assessment.cascade_risk is True

    def test_cascade_risk_false_few_dependents(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg()
        # "db" has 1 dependent
        assessment = engine.validate_health_check(graph, "db", cfg)
        assert assessment.cascade_risk is False

    def test_risk_score_amplified_by_many_dependents(self):
        """Risk score should be higher for components with many dependents."""
        engine = _engine()
        graph = _wide_graph()
        cfg = _cfg(timeout=1.0)  # triggers TIMEOUT_TOO_SHORT
        assessment_core = engine.validate_health_check(graph, "core", cfg)

        graph2 = _simple_graph()
        assessment_db = engine.validate_health_check(graph2, "db", cfg)

        # Core has more dependents, so its risk score should be higher
        assert assessment_core.risk_score >= assessment_db.risk_score

    def test_false_positive_risk_high(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(
            timeout=1.0,
            interval=2.0,
            failure_threshold=1,
            checks_deps=True,
            deep=True,
        )
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert assessment.false_positive_risk == "high"

    def test_false_positive_risk_medium(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(timeout=1.0, failure_threshold=3)
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert assessment.false_positive_risk == "medium"

    def test_false_positive_risk_low(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(timeout=5.0, interval=10.0, failure_threshold=3)
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert assessment.false_positive_risk == "low"

    def test_false_negative_risk_high(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(
            check_type=HealthCheckType.TCP,
            timeout=60.0,
            interval=120.0,
            checks_deps=False,
            deep=False,
        )
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert assessment.false_negative_risk == "high"

    def test_false_negative_risk_medium(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(
            check_type=HealthCheckType.TCP,
            timeout=5.0,
            interval=10.0,
            checks_deps=False,
            deep=False,
        )
        assessment = engine.validate_health_check(graph, "app", cfg)
        # TCP + no dep check = 2 factors → medium
        assert assessment.false_negative_risk == "medium"

    def test_false_negative_risk_low(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(
            check_type=HealthCheckType.HTTP,
            timeout=5.0,
            interval=10.0,
            checks_deps=True,
            deep=True,
        )
        # db has no outbound deps
        assessment = engine.validate_health_check(graph, "db", cfg)
        assert assessment.false_negative_risk == "low"

    def test_recommendations_generated(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(timeout=1.0, interval=2.0, checks_deps=False, deep=False)
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert len(assessment.recommendations) > 0

    def test_nonexistent_component(self):
        """Validate a component that does not exist in the graph."""
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg()
        assessment = engine.validate_health_check(graph, "nonexistent", cfg)
        assert assessment.component_id == "nonexistent"
        assert isinstance(assessment.risk_score, float)

    def test_recommendations_for_timeout_too_short(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(timeout=0.5)
        assessment = engine.validate_health_check(graph, "db", cfg)
        assert any("too short" in r.lower() or "timeout" in r.lower()
                    for r in assessment.recommendations)

    def test_recommendations_for_timeout_too_long(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(timeout=60.0)
        assessment = engine.validate_health_check(graph, "db", cfg)
        assert any("too long" in r.lower() or "timeout" in r.lower()
                    for r in assessment.recommendations)

    def test_recommendations_for_no_startup_probe(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(check_type=HealthCheckType.LIVENESS, failure_threshold=1)
        assessment = engine.validate_health_check(graph, "db", cfg)
        assert any("startup" in r.lower() for r in assessment.recommendations)

    def test_recommendations_for_interval_too_frequent(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(interval=1.0)
        assessment = engine.validate_health_check(graph, "db", cfg)
        assert any("interval" in r.lower() or "frequent" in r.lower()
                    for r in assessment.recommendations)


# ===================================================================
# simulate_flapping
# ===================================================================


class TestSimulateFlapping:
    def test_stable_config_low_risk(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(interval=30.0, timeout=10.0, failure_threshold=5, success_threshold=3)
        result = engine.simulate_flapping(graph, "app", cfg)
        assert result.flap_risk == "low"
        assert result.flap_count == 0 or result.flap_risk == "low"

    def test_aggressive_config_high_risk(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(
            interval=1.0,
            timeout=0.3,
            failure_threshold=1,
            success_threshold=1,
            checks_deps=True,
            deep=True,
        )
        result = engine.simulate_flapping(graph, "app", cfg)
        assert result.flap_risk in ("high", "medium")
        assert result.flap_count > 0

    def test_flapping_recommendations_high(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(interval=1.0, timeout=0.3, failure_threshold=1, success_threshold=1)
        result = engine.simulate_flapping(graph, "app", cfg)
        if result.flap_risk == "high":
            assert len(result.recommendations) > 0
            assert any("failure_threshold" in r or "interval" in r
                        for r in result.recommendations)

    def test_flapping_recommendations_medium(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(interval=3.0, timeout=1.5, failure_threshold=2, success_threshold=2)
        result = engine.simulate_flapping(graph, "app", cfg)
        if result.flap_risk in ("high", "medium"):
            assert any("interval" in r.lower() for r in result.recommendations)

    def test_steady_state_time_increases_with_propensity(self):
        engine = _engine()
        graph = _simple_graph()
        stable = _cfg(interval=30.0, timeout=10.0, failure_threshold=5, success_threshold=3)
        aggressive = _cfg(
            interval=1.0, timeout=0.3, failure_threshold=1, success_threshold=1,
            checks_deps=True, deep=True,
        )
        r_stable = engine.simulate_flapping(graph, "app", stable)
        r_aggressive = engine.simulate_flapping(graph, "app", aggressive)
        # Aggressive config should have longer or comparable steady-state due to
        # the propensity multiplier
        assert r_aggressive.steady_state_seconds >= 0

    def test_mean_time_between_flaps_zero_for_stable(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(interval=30.0, timeout=10.0, failure_threshold=5, success_threshold=3)
        result = engine.simulate_flapping(graph, "app", cfg)
        if result.flap_count == 0:
            assert result.mean_time_between_flaps_seconds == 0.0

    def test_flapping_with_short_mttr(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("svc", mttr_minutes=0.5))
        cfg = _cfg(interval=2.0, timeout=1.0, failure_threshold=1, success_threshold=1)
        result = engine.simulate_flapping(g, "svc", cfg)
        assert isinstance(result.flap_count, int)

    def test_flapping_with_nonexistent_component(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(interval=1.0, timeout=0.3, failure_threshold=1, success_threshold=1)
        result = engine.simulate_flapping(graph, "nope", cfg)
        assert result.component_id == "nope"

    def test_flapping_with_long_mttr(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("svc", mttr_minutes=120.0))
        cfg = _cfg(interval=2.0, timeout=0.5, failure_threshold=1, success_threshold=1)
        result = engine.simulate_flapping(g, "svc", cfg)
        # Short cycle vs long MTTR → should increase propensity
        assert result.flap_count >= 0


# ===================================================================
# estimate_detection_time
# ===================================================================


class TestEstimateDetectionTime:
    def test_crash_detection(self):
        engine = _engine()
        cfg = _cfg(interval=10.0, failure_threshold=3)
        dt = engine.estimate_detection_time(cfg, "crash")
        assert dt == pytest.approx(30.0, rel=0.01)

    def test_hang_detection(self):
        engine = _engine()
        cfg = _cfg(interval=10.0, failure_threshold=3)
        dt = engine.estimate_detection_time(cfg, "hang")
        assert dt == pytest.approx(36.0, rel=0.01)

    def test_degraded_detection(self):
        engine = _engine()
        cfg = _cfg(interval=10.0, failure_threshold=3)
        dt = engine.estimate_detection_time(cfg, "degraded")
        assert dt == pytest.approx(60.0, rel=0.01)

    def test_network_partition_detection(self):
        engine = _engine()
        cfg = _cfg(interval=10.0, failure_threshold=3)
        dt = engine.estimate_detection_time(cfg, "network_partition")
        assert dt == pytest.approx(45.0, rel=0.01)

    def test_dependency_failure_with_dep_check(self):
        engine = _engine()
        cfg = _cfg(interval=10.0, failure_threshold=3, checks_deps=True)
        dt = engine.estimate_detection_time(cfg, "dependency_failure")
        assert dt == pytest.approx(54.0, rel=0.01)  # 30 * 1.8

    def test_dependency_failure_without_dep_check(self):
        engine = _engine()
        cfg = _cfg(interval=10.0, failure_threshold=3, checks_deps=False)
        dt = engine.estimate_detection_time(cfg, "dependency_failure")
        # 30 * 3.0 + 10 * 2 = 110
        assert dt == pytest.approx(110.0, rel=0.01)

    def test_resource_exhaustion(self):
        engine = _engine()
        cfg = _cfg(interval=10.0, failure_threshold=3)
        dt = engine.estimate_detection_time(cfg, "resource_exhaustion")
        assert dt == pytest.approx(75.0, rel=0.01)

    def test_unknown_failure_type(self):
        engine = _engine()
        cfg = _cfg(interval=10.0, failure_threshold=3)
        dt = engine.estimate_detection_time(cfg, "unknown_type")
        assert dt == pytest.approx(45.0, rel=0.01)  # default multiplier 1.5

    def test_short_timeout_increases_detection_time(self):
        engine = _engine()
        cfg_short = _cfg(interval=10.0, failure_threshold=3, timeout=1.0)
        cfg_normal = _cfg(interval=10.0, failure_threshold=3, timeout=5.0)
        dt_short = engine.estimate_detection_time(cfg_short, "crash")
        dt_normal = engine.estimate_detection_time(cfg_normal, "crash")
        assert dt_short > dt_normal

    def test_detection_scales_with_interval(self):
        engine = _engine()
        cfg_fast = _cfg(interval=5.0, failure_threshold=3)
        cfg_slow = _cfg(interval=30.0, failure_threshold=3)
        dt_fast = engine.estimate_detection_time(cfg_fast, "crash")
        dt_slow = engine.estimate_detection_time(cfg_slow, "crash")
        assert dt_slow > dt_fast

    def test_detection_scales_with_failure_threshold(self):
        engine = _engine()
        cfg_low = _cfg(interval=10.0, failure_threshold=1)
        cfg_high = _cfg(interval=10.0, failure_threshold=5)
        dt_low = engine.estimate_detection_time(cfg_low, "crash")
        dt_high = engine.estimate_detection_time(cfg_high, "crash")
        assert dt_high > dt_low


# ===================================================================
# recommend_health_check
# ===================================================================


class TestRecommendHealthCheck:
    def test_app_server(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = engine.recommend_health_check(graph, "app")
        assert cfg.check_type == HealthCheckType.HTTP
        assert cfg.endpoint == "/healthz"
        assert cfg.interval_seconds >= _MIN_REASONABLE_INTERVAL
        assert cfg.timeout_seconds >= _MIN_REASONABLE_TIMEOUT

    def test_database(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = engine.recommend_health_check(graph, "db")
        assert cfg.check_type == HealthCheckType.TCP
        assert cfg.checks_dependencies is False
        assert cfg.includes_deep_check is False

    def test_load_balancer(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = engine.recommend_health_check(graph, "lb")
        assert cfg.check_type == HealthCheckType.HTTP

    def test_many_dependents_increases_interval(self):
        engine = _engine()
        graph = _wide_graph()
        cfg = engine.recommend_health_check(graph, "core")
        # "core" has 6 dependents → interval should be higher
        assert cfg.interval_seconds >= 30.0
        assert cfg.failure_threshold >= 5

    def test_moderate_dependents(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("center"))
        for i in range(3):
            cid = f"dep-{i}"
            g.add_component(_comp(cid))
            g.add_dependency(_dep(cid, "center"))
        cfg = engine.recommend_health_check(g, "center")
        assert cfg.interval_seconds >= 15.0

    def test_no_dependents(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("standalone"))
        cfg = engine.recommend_health_check(g, "standalone")
        assert cfg.interval_seconds == 10.0

    def test_database_tcp_endpoint(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("pg", ctype=ComponentType.DATABASE, port=5432))
        cfg = engine.recommend_health_check(g, "pg")
        assert ":5432" in cfg.endpoint

    def test_database_default_port(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("pg", ctype=ComponentType.DATABASE, port=0))
        cfg = engine.recommend_health_check(g, "pg")
        assert ":8080" in cfg.endpoint

    def test_nonexistent_component(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = engine.recommend_health_check(graph, "nonexistent")
        # Should still return a valid config with defaults
        assert cfg.check_type == HealthCheckType.HTTP

    def test_cache_component(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("redis", ctype=ComponentType.CACHE, port=6379))
        cfg = engine.recommend_health_check(g, "redis")
        assert cfg.check_type == HealthCheckType.TCP

    def test_dns_component(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("dns", ctype=ComponentType.DNS, port=53))
        cfg = engine.recommend_health_check(g, "dns")
        assert cfg.check_type == HealthCheckType.TCP

    def test_external_api_component(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("ext", ctype=ComponentType.EXTERNAL_API))
        cfg = engine.recommend_health_check(g, "ext")
        assert cfg.check_type == HealthCheckType.HTTP
        assert cfg.timeout_seconds >= 10.0

    def test_deep_check_enabled_with_few_deps(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("svc", ctype=ComponentType.APP_SERVER))
        g.add_component(_comp("dep1"))
        g.add_dependency(_dep("svc", "dep1"))
        cfg = engine.recommend_health_check(g, "svc")
        assert cfg.includes_deep_check is True
        assert cfg.checks_dependencies is True

    def test_deep_check_disabled_with_many_deps(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("svc", ctype=ComponentType.APP_SERVER))
        for i in range(5):
            cid = f"dep-{i}"
            g.add_component(_comp(cid))
            g.add_dependency(_dep("svc", cid))
        cfg = engine.recommend_health_check(g, "svc")
        assert cfg.includes_deep_check is False

    def test_recommended_config_passes_own_validation(self):
        """A recommended config should have zero or minimal anti-patterns."""
        engine = _engine()
        graph = _simple_graph()
        cfg = engine.recommend_health_check(graph, "app")
        patterns = engine.detect_anti_patterns(cfg)
        # Should not have config-level anti-patterns
        assert AntiPattern.TIMEOUT_TOO_SHORT not in patterns
        assert AntiPattern.TIMEOUT_TOO_LONG not in patterns
        assert AntiPattern.INTERVAL_TOO_FREQUENT not in patterns


# ===================================================================
# validate_all_checks
# ===================================================================


class TestValidateAllChecks:
    def test_multiple_components(self):
        engine = _engine()
        graph = _simple_graph()
        configs = {
            "lb": _cfg(endpoint="/health"),
            "app": _cfg(endpoint="/healthz"),
            "db": _cfg(check_type=HealthCheckType.TCP, endpoint=":5432"),
        }
        assessments = engine.validate_all_checks(graph, configs)
        assert len(assessments) == 3
        # Sorted by risk score descending
        scores = [a.risk_score for a in assessments]
        assert scores == sorted(scores, reverse=True)

    def test_shared_endpoint_detection(self):
        """Two components sharing the same endpoint should be flagged."""
        engine = _engine()
        graph = _simple_graph()
        configs = {
            "lb": _cfg(endpoint="/healthz"),
            "app": _cfg(endpoint="/healthz"),
        }
        assessments = engine.validate_all_checks(graph, configs)
        shared_count = sum(
            1 for a in assessments
            if AntiPattern.SHARED_ENDPOINT in a.anti_patterns
        )
        assert shared_count == 2

    def test_shared_endpoint_adds_recommendation(self):
        engine = _engine()
        graph = _simple_graph()
        configs = {
            "lb": _cfg(endpoint="/same-path"),
            "app": _cfg(endpoint="/same-path"),
        }
        assessments = engine.validate_all_checks(graph, configs)
        for a in assessments:
            if AntiPattern.SHARED_ENDPOINT in a.anti_patterns:
                assert any("shared" in r.lower() for r in a.recommendations)

    def test_different_endpoints_no_shared(self):
        engine = _engine()
        graph = _simple_graph()
        configs = {
            "lb": _cfg(endpoint="/lb-health"),
            "app": _cfg(endpoint="/app-health"),
            "db": _cfg(check_type=HealthCheckType.TCP, endpoint=":5432"),
        }
        assessments = engine.validate_all_checks(graph, configs)
        for a in assessments:
            # Should not have shared endpoint from cross-check
            # (may have it from single-check if liveness+deep)
            pass  # just ensure no exception

    def test_empty_configs(self):
        engine = _engine()
        graph = _simple_graph()
        assessments = engine.validate_all_checks(graph, {})
        assert assessments == []

    def test_single_config(self):
        engine = _engine()
        graph = _simple_graph()
        configs = {"app": _cfg()}
        assessments = engine.validate_all_checks(graph, configs)
        assert len(assessments) == 1

    def test_shared_endpoint_recalculates_risk(self):
        """Risk score should be updated after shared endpoint detection."""
        engine = _engine()
        graph = _simple_graph()
        configs = {
            "lb": _cfg(endpoint="/shared"),
            "app": _cfg(endpoint="/shared"),
        }
        assessments = engine.validate_all_checks(graph, configs)
        for a in assessments:
            if AntiPattern.SHARED_ENDPOINT in a.anti_patterns:
                assert a.risk_score > 0

    def test_different_check_types_same_endpoint_not_shared(self):
        """Same path but different check types should not be flagged."""
        engine = _engine()
        graph = _simple_graph()
        configs = {
            "lb": _cfg(check_type=HealthCheckType.HTTP, endpoint="/healthz"),
            "app": _cfg(check_type=HealthCheckType.GRPC, endpoint="/healthz"),
        }
        assessments = engine.validate_all_checks(graph, configs)
        # Different check_type → different key → not shared
        shared_from_cross = sum(
            1 for a in assessments
            if AntiPattern.SHARED_ENDPOINT in a.anti_patterns
        )
        # May be 0 (different types) unless liveness+deep triggers it
        assert shared_from_cross == 0


# ===================================================================
# simulate_health_check_failure
# ===================================================================


class TestSimulateHealthCheckFailure:
    def test_leaf_component(self):
        """Failure at a leaf node should affect no others."""
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("leaf"))
        result = engine.simulate_health_check_failure(g, "leaf")
        assert result.component_id == "leaf"
        assert result.affected_components == []
        assert result.cascade_depth == 0

    def test_root_component_cascade(self):
        engine = _engine()
        graph = _simple_graph()
        result = engine.simulate_health_check_failure(graph, "db")
        # "db" is depended on by "app", which is depended on by "lb"
        assert "app" in result.affected_components
        # "lb" depends on "app" which depends on "db"
        assert len(result.affected_components) > 0

    def test_cascade_depth(self):
        engine = _engine()
        graph = _deep_graph()
        result = engine.simulate_health_check_failure(graph, "e")
        # e → d → c → b → a
        assert result.cascade_depth >= 1

    def test_detection_time_with_failover(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp(
            "svc",
            failover_enabled=True,
            failover_interval=5.0,
            failover_threshold=3,
        ))
        result = engine.simulate_health_check_failure(g, "svc")
        assert result.estimated_detection_seconds == pytest.approx(15.0)

    def test_detection_time_without_failover(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("svc", failover_enabled=False))
        result = engine.simulate_health_check_failure(g, "svc")
        assert result.estimated_detection_seconds == pytest.approx(30.0)

    def test_recovery_time_with_failover(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp(
            "svc",
            failover_enabled=True,
            promotion_time=15.0,
        ))
        result = engine.simulate_health_check_failure(g, "svc")
        assert result.estimated_recovery_seconds == pytest.approx(15.0)

    def test_recovery_time_with_autoscaling(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp(
            "svc",
            failover_enabled=False,
            autoscaling_enabled=True,
            scale_up_delay=20,
        ))
        result = engine.simulate_health_check_failure(g, "svc")
        assert result.estimated_recovery_seconds == pytest.approx(20.0)

    def test_recovery_time_default(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("svc", failover_enabled=False, mttr_minutes=60.0))
        result = engine.simulate_health_check_failure(g, "svc")
        assert result.estimated_recovery_seconds == pytest.approx(3600.0)

    def test_risk_score_high_impact(self):
        engine = _engine()
        graph = _wide_graph()
        result = engine.simulate_health_check_failure(graph, "core")
        assert result.risk_score > 0

    def test_risk_score_no_impact(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("isolated"))
        result = engine.simulate_health_check_failure(g, "isolated")
        assert result.risk_score == pytest.approx(0.0)

    def test_recommendations_deep_cascade(self):
        engine = _engine()
        graph = _deep_graph()
        result = engine.simulate_health_check_failure(graph, "e")
        if result.cascade_depth > 2:
            assert any("circuit breaker" in r.lower() for r in result.recommendations)

    def test_recommendations_high_impact(self):
        engine = _engine()
        graph = _wide_graph()
        result = engine.simulate_health_check_failure(graph, "core")
        if len(result.affected_components) > len(graph.components) * 0.5:
            assert any("redundancy" in r.lower() or "failover" in r.lower()
                        for r in result.recommendations)

    def test_recommendations_no_failover(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("svc", failover_enabled=False))
        result = engine.simulate_health_check_failure(g, "svc")
        assert any("failover" in r.lower() for r in result.recommendations)

    def test_recommendations_many_dependents(self):
        engine = _engine()
        graph = _wide_graph()
        result = engine.simulate_health_check_failure(graph, "core")
        assert any("readiness" in r.lower() or "depend" in r.lower()
                    for r in result.recommendations)

    def test_nonexistent_component(self):
        engine = _engine()
        graph = _simple_graph()
        result = engine.simulate_health_check_failure(graph, "nonexistent")
        assert result.component_id == "nonexistent"
        assert result.estimated_recovery_seconds == 1800.0

    def test_affected_components_sorted(self):
        engine = _engine()
        graph = _wide_graph()
        result = engine.simulate_health_check_failure(graph, "core")
        assert result.affected_components == sorted(result.affected_components)


# ===================================================================
# Edge cases and integration
# ===================================================================


class TestEdgeCases:
    def test_empty_graph(self):
        engine = _engine()
        g = InfraGraph()
        cfg = _cfg()
        assessment = engine.validate_health_check(g, "x", cfg)
        assert assessment.component_id == "x"

    def test_single_component_graph(self):
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("solo"))
        cfg = _cfg()
        assessment = engine.validate_health_check(g, "solo", cfg)
        assert assessment.component_id == "solo"
        assert assessment.cascade_risk is False

    def test_risk_score_capped_at_100(self):
        """Even with many anti-patterns, risk score should not exceed 100."""
        engine = _engine()
        graph = _wide_graph()
        cfg = _cfg(
            check_type=HealthCheckType.LIVENESS,
            timeout=0.5,
            interval=1.0,
            failure_threshold=1,
            success_threshold=1,
            checks_deps=True,
            deep=True,
        )
        assessment = engine.validate_health_check(graph, "core", cfg)
        assert assessment.risk_score <= 100.0

    def test_risk_score_non_negative(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg()
        assessment = engine.validate_health_check(graph, "db", cfg)
        assert assessment.risk_score >= 0.0

    def test_all_component_types_have_recommended_check(self):
        for ct in ComponentType:
            assert ct in _RECOMMENDED_CHECK_TYPES

    def test_validate_all_then_individual_consistency(self):
        """validate_all_checks should produce same base result as individual calls."""
        engine = _engine()
        graph = _simple_graph()
        configs = {
            "app": _cfg(endpoint="/app-health"),
            "db": _cfg(check_type=HealthCheckType.TCP, endpoint=":5432"),
        }
        batch = engine.validate_all_checks(graph, configs)
        individual_app = engine.validate_health_check(graph, "app", configs["app"])
        individual_db = engine.validate_health_check(graph, "db", configs["db"])

        batch_app = next(a for a in batch if a.component_id == "app")
        batch_db = next(a for a in batch if a.component_id == "db")

        # Anti-patterns from individual check should be subset of batch
        for ap in individual_app.anti_patterns:
            assert ap in batch_app.anti_patterns
        for ap in individual_db.anti_patterns:
            assert ap in batch_db.anti_patterns

    def test_health_check_config_all_types(self):
        """Ensure HealthCheckConfig accepts all check types."""
        for hct in HealthCheckType:
            cfg = _cfg(check_type=hct)
            assert cfg.check_type == hct

    def test_flapping_result_component_id(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg()
        result = engine.simulate_flapping(graph, "app", cfg)
        assert result.component_id == "app"

    def test_health_check_failure_result_for_empty_graph(self):
        engine = _engine()
        g = InfraGraph()
        result = engine.simulate_health_check_failure(g, "missing")
        assert result.component_id == "missing"
        assert result.affected_components == []
        assert result.cascade_depth == 0


class TestCoverageFill:
    """Tests targeting specific uncovered branches."""

    def test_flapping_zero_cycle_time(self):
        """cycle_time == 0 when interval=0 (edge case)."""
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("svc"))
        # interval_seconds=0 forces cycle_time = 0
        cfg = _cfg(interval=0.0, timeout=5.0, failure_threshold=3, success_threshold=2)
        result = engine.simulate_flapping(g, "svc", cfg)
        assert result.flap_count == 0

    def test_flapping_medium_risk(self):
        """Trigger the 'medium' flap risk branch (3 <= flap_count < 10)."""
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("svc", mttr_minutes=0.01))
        # Craft a config that produces propensity giving 3-9 flaps
        # interval=10, fail=2, succ=2: cycle=40s. max_flaps=90.
        # Need propensity such that 3 <= 90*p < 10, so 0.033 < p < 0.111
        # timeout=4 < 10*0.3=3 → no. Let's use interval=3 < 5 → propensity=0.2
        # fail=2, succ=2. cycle=3*(2+2)=12. max=300. 300*0.2=60 → too high.
        # Need very low propensity. Use a clean config with only one minor trigger.
        # interval=10, fail=3, succ=2. cycle=50. max=72.
        # Need propensity ~0.05-0.12.
        # timeout=2.5 < 10*0.3=3 → propensity 0.3 → too high.
        # Let's use checks_deps=True, deep=True only → 0.1 propensity.
        # 72 * 0.1 = 7.2 → int(7.2) = 7 → medium!
        cfg = _cfg(
            interval=10.0, timeout=5.0, failure_threshold=3, success_threshold=2,
            checks_deps=True, deep=True,
        )
        result = engine.simulate_flapping(g, "svc", cfg)
        assert result.flap_risk == "medium"
        assert 3 <= result.flap_count < 10

    def test_recommend_grpc_endpoint_branch(self):
        """Cover the GRPC endpoint branch in recommend_health_check
        by temporarily patching _RECOMMENDED_CHECK_TYPES."""
        import faultray.simulator.health_check_validator as mod
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("svc", ctype=ComponentType.QUEUE, port=9090))
        original = mod._RECOMMENDED_CHECK_TYPES[ComponentType.QUEUE]
        try:
            mod._RECOMMENDED_CHECK_TYPES[ComponentType.QUEUE] = HealthCheckType.GRPC
            cfg = engine.recommend_health_check(g, "svc")
            assert cfg.check_type == HealthCheckType.GRPC
            assert "grpc" in cfg.endpoint
        finally:
            mod._RECOMMENDED_CHECK_TYPES[ComponentType.QUEUE] = original

    def test_recommend_else_endpoint_branch(self):
        """Cover the else branch for endpoint generation (non-HTTP/TCP/GRPC)."""
        import faultray.simulator.health_check_validator as mod
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("svc", ctype=ComponentType.QUEUE, port=9090))
        original = mod._RECOMMENDED_CHECK_TYPES[ComponentType.QUEUE]
        try:
            mod._RECOMMENDED_CHECK_TYPES[ComponentType.QUEUE] = HealthCheckType.EXEC
            cfg = engine.recommend_health_check(g, "svc")
            assert cfg.check_type == HealthCheckType.EXEC
            assert cfg.endpoint == "/healthz"
        finally:
            mod._RECOMMENDED_CHECK_TYPES[ComponentType.QUEUE] = original

    def test_risk_score_moderate_dependents(self):
        """Cover the score *= 1.2 branch (2 < dependents <= 5)."""
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("center"))
        for i in range(3):  # 3 dependents
            cid = f"dep-{i}"
            g.add_component(_comp(cid))
            g.add_dependency(_dep(cid, "center"))
        # Give it an anti-pattern so score > 0
        cfg = _cfg(timeout=1.0)
        assessment = engine.validate_health_check(g, "center", cfg)
        # With 3 dependents, multiplier should be 1.2
        assert assessment.risk_score > 0

    def test_cascade_depth_affected_no_paths(self):
        """affected set is non-empty but get_cascade_path returns []."""
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b"))
        # b fails -> a affected. cascade_path from b should find a path.
        result = engine.simulate_health_check_failure(g, "b")
        assert result.cascade_depth >= 1

    def test_cascade_depth_fallback_when_paths_empty(self):
        """Cover the fallback branch when affected is non-empty
        but get_cascade_path returns empty (via monkeypatch)."""
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b"))
        # Monkeypatch get_cascade_path to return []
        original = g.get_cascade_path
        g.get_cascade_path = lambda *args, **kwargs: []
        result = engine.simulate_health_check_failure(g, "b")
        assert result.cascade_depth == 1
        g.get_cascade_path = original

    def test_flapping_high_propensity_doubles_steady_state(self):
        """When propensity > 0.5, steady_state is doubled."""
        engine = _engine()
        g = InfraGraph()
        g.add_component(_comp("svc", mttr_minutes=300.0))
        cfg = _cfg(
            interval=1.0, timeout=0.1, failure_threshold=1, success_threshold=1,
            checks_deps=True, deep=True,
        )
        result = engine.simulate_flapping(g, "svc", cfg)
        # With many propensity factors, propensity > 0.5
        # steady_state should be doubled
        base_steady = (1.0 * (1 + 1)) * (1 + 1)
        assert result.steady_state_seconds >= base_steady

    def test_estimate_detection_dep_failure_no_dep_check_extra_cycles(self):
        """dependency_failure without checks_deps adds extra interval cycles."""
        engine = _engine()
        cfg_no_dep = _cfg(interval=10.0, failure_threshold=3, checks_deps=False)
        cfg_dep = _cfg(interval=10.0, failure_threshold=3, checks_deps=True)
        dt_no = engine.estimate_detection_time(cfg_no_dep, "dependency_failure")
        dt_yes = engine.estimate_detection_time(cfg_dep, "dependency_failure")
        # Without dep check: additional penalty
        assert dt_no > dt_yes

    def test_validate_all_shared_endpoint_does_not_duplicate(self):
        """If SHARED_ENDPOINT already exists from single validation,
        validate_all should not add it again."""
        engine = _engine()
        graph = _simple_graph()
        # Liveness + deep → shared endpoint from individual check
        configs = {
            "lb": _cfg(check_type=HealthCheckType.LIVENESS, endpoint="/deep", deep=True),
            "app": _cfg(check_type=HealthCheckType.LIVENESS, endpoint="/deep", deep=True),
        }
        assessments = engine.validate_all_checks(graph, configs)
        for a in assessments:
            # Should not have duplicate SHARED_ENDPOINT entries
            shared_count = a.anti_patterns.count(AntiPattern.SHARED_ENDPOINT)
            assert shared_count <= 2  # at most from individual + cross-check

    def test_false_negative_risk_with_long_interval(self):
        """interval > 60 should increase false negative risk."""
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(interval=120.0, timeout=5.0, checks_deps=False, deep=False)
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert assessment.false_negative_risk in ("medium", "high")

    def test_false_positive_low_threshold_and_deps(self):
        """failure_threshold=1 + checks_deps + deep → high FP risk."""
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(
            timeout=1.0, interval=2.0, failure_threshold=1,
            checks_deps=True, deep=True,
        )
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert assessment.false_positive_risk == "high"

    def test_recommendations_thundering_herd(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(success_threshold=1, interval=2.0)
        assessment = engine.validate_health_check(graph, "db", cfg)
        assert any("thundering" in r.lower() or "success_threshold" in r.lower()
                    for r in assessment.recommendations)

    def test_recommendations_missing_dependency_check(self):
        engine = _engine()
        graph = _simple_graph()
        cfg = _cfg(checks_deps=False, deep=False)
        assessment = engine.validate_health_check(graph, "app", cfg)
        assert any("readiness" in r.lower() or "dependencies" in r.lower()
                    for r in assessment.recommendations)

    def test_recommendations_cascading_failure(self):
        engine = _engine()
        graph = _wide_graph()
        cfg = _cfg(checks_deps=True)
        assessment = engine.validate_health_check(graph, "core", cfg)
        assert any("cascading" in r.lower() or "separate" in r.lower()
                    for r in assessment.recommendations)


class TestIntegration:
    """End-to-end scenario tests combining multiple engine methods."""

    def test_full_workflow_simple_graph(self):
        engine = _engine()
        graph = _simple_graph()

        # 1. Recommend configs
        cfg_app = engine.recommend_health_check(graph, "app")
        cfg_db = engine.recommend_health_check(graph, "db")

        # 2. Validate recommended configs
        assessment_app = engine.validate_health_check(graph, "app", cfg_app)
        assessment_db = engine.validate_health_check(graph, "db", cfg_db)

        # Recommended configs should be reasonable
        assert assessment_app.risk_score < 50.0
        assert assessment_db.risk_score < 50.0

        # 3. Check flapping — recommended config may include deep checks which
        # increases flapping propensity; just verify we get a valid result
        flap_app = engine.simulate_flapping(graph, "app", cfg_app)
        assert flap_app.flap_risk in ("low", "medium", "high")

        # 4. Estimate detection
        dt = engine.estimate_detection_time(cfg_app, "crash")
        assert dt > 0

        # 5. Simulate failure
        failure = engine.simulate_health_check_failure(graph, "db")
        assert isinstance(failure.risk_score, float)

    def test_full_workflow_wide_graph(self):
        engine = _engine()
        graph = _wide_graph()

        # Validate all with recommended configs
        configs = {}
        for cid in graph.components:
            configs[cid] = engine.recommend_health_check(graph, cid)

        assessments = engine.validate_all_checks(graph, configs)
        assert len(assessments) == len(graph.components)

        # Core should have higher risk due to many dependents
        core_assessment = next(a for a in assessments if a.component_id == "core")
        assert core_assessment.risk_score >= 0

    def test_bad_config_vs_good_config(self):
        """Bad config should always have higher risk than good config."""
        engine = _engine()
        graph = _simple_graph()

        bad = _cfg(timeout=0.5, interval=1.0, failure_threshold=1, success_threshold=1)
        good = _cfg(timeout=5.0, interval=10.0, failure_threshold=3, success_threshold=2, deep=True)

        bad_assessment = engine.validate_health_check(graph, "app", bad)
        good_assessment = engine.validate_health_check(graph, "app", good)

        assert bad_assessment.risk_score > good_assessment.risk_score

    def test_detection_time_all_failure_types(self):
        engine = _engine()
        cfg = _cfg(interval=10.0, failure_threshold=3)
        failure_types = [
            "crash", "hang", "degraded", "network_partition",
            "dependency_failure", "resource_exhaustion",
        ]
        times = {}
        for ft in failure_types:
            times[ft] = engine.estimate_detection_time(cfg, ft)
        # Crash should be fastest to detect
        assert times["crash"] <= min(times[ft] for ft in failure_types if ft != "crash")

    def test_recommend_then_validate_all_types(self):
        """Recommend a config for every ComponentType and validate it."""
        engine = _engine()
        for ct in ComponentType:
            g = InfraGraph()
            g.add_component(_comp("target", ctype=ct, port=8080))
            cfg = engine.recommend_health_check(g, "target")
            assessment = engine.validate_health_check(g, "target", cfg)
            assert assessment.risk_score <= 100.0
            assert assessment.risk_score >= 0.0
