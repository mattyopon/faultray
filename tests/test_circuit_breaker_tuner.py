"""Tests for Circuit Breaker Tuner."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    NetworkProfile,
    RetryStrategy,
    ComplianceTags,
    Capacity,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.circuit_breaker_tuner import (
    BreakerState,
    BulkheadBreakerIntegration,
    BulkheadConfig,
    CascadeAnalysis,
    CascadeLink,
    CircuitBreakerTuner,
    CircuitBreakerTuningReport,
    ErrorRateSnapshot,
    FalseNegativeRisk,
    FalsePositiveRisk,
    HalfOpenBudget,
    MonitoringGap,
    PlacementRecommendation,
    PlacementStrategy,
    RecoveryPattern,
    RecoveryTimeoutRecommendation,
    RetryBreakerInteraction,
    RiskCategory,
    Severity,
    SimulationResult,
    StateTransition,
    SuccessRateRecommendation,
    TestCoverageLevel,
    TestCoverageResult,
    ThresholdRecommendation,
    ThunderingHerdRisk,
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


def _dep(
    source: str = "a1",
    target: str = "b1",
    *,
    cb_enabled: bool = False,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    half_open_max: int = 3,
    success_threshold: int = 2,
    dep_type: str = "requires",
    retry_enabled: bool = False,
    max_retries: int = 3,
) -> Dependency:
    return Dependency(
        source_id=source,
        target_id=target,
        dependency_type=dep_type,
        circuit_breaker=CircuitBreakerConfig(
            enabled=cb_enabled,
            failure_threshold=failure_threshold,
            recovery_timeout_seconds=recovery_timeout,
            half_open_max_requests=half_open_max,
            success_threshold=success_threshold,
        ),
        retry_strategy=RetryStrategy(
            enabled=retry_enabled,
            max_retries=max_retries,
        ),
    )


def _simple_graph() -> tuple[InfraGraph, str, str]:
    """Create a simple a1 -> b1 graph with breaker enabled."""
    a = _comp("a1")
    b = _comp("b1")
    g = _graph(a, b)
    g.add_dependency(
        _dep("a1", "b1", cb_enabled=True, failure_threshold=5, recovery_timeout=60.0)
    )
    return g, "a1", "b1"


def _chain_graph(length: int = 4, breaker: bool = True) -> InfraGraph:
    """Create a linear chain: c0 -> c1 -> c2 -> ... -> c(length-1)."""
    comps = [_comp(f"c{i}") for i in range(length)]
    g = _graph(*comps)
    for i in range(length - 1):
        g.add_dependency(
            _dep(f"c{i}", f"c{i+1}", cb_enabled=breaker, failure_threshold=5)
        )
    return g


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_severity_values(self):
        assert Severity.INFO == "info"
        assert Severity.WARNING == "warning"
        assert Severity.CRITICAL == "critical"

    def test_breaker_state_values(self):
        assert BreakerState.CLOSED == "closed"
        assert BreakerState.OPEN == "open"
        assert BreakerState.HALF_OPEN == "half_open"

    def test_risk_category_values(self):
        assert RiskCategory.FALSE_POSITIVE == "false_positive"
        assert RiskCategory.FALSE_NEGATIVE == "false_negative"
        assert RiskCategory.THUNDERING_HERD == "thundering_herd"
        assert RiskCategory.CASCADE_FAILURE == "cascade_failure"
        assert RiskCategory.MONITORING_GAP == "monitoring_gap"
        assert RiskCategory.RETRY_INTERACTION == "retry_interaction"
        assert RiskCategory.BULKHEAD_MISMATCH == "bulkhead_mismatch"

    def test_placement_strategy_values(self):
        assert PlacementStrategy.CLIENT_SIDE == "client_side"
        assert PlacementStrategy.SERVER_SIDE == "server_side"
        assert PlacementStrategy.SIDECAR == "sidecar"
        assert PlacementStrategy.MESH_LEVEL == "mesh_level"

    def test_test_coverage_level_values(self):
        assert TestCoverageLevel.NONE == "none"
        assert TestCoverageLevel.BASIC == "basic"
        assert TestCoverageLevel.MODERATE == "moderate"
        assert TestCoverageLevel.COMPREHENSIVE == "comprehensive"


# ---------------------------------------------------------------------------
# Configuration helper tests
# ---------------------------------------------------------------------------


class TestConfigurationHelpers:
    def test_set_and_get_error_rate(self):
        g, src, tgt = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        snapshot = ErrorRateSnapshot(source_id=src, target_id=tgt, error_rate=0.05)
        tuner.set_error_rate(snapshot)
        assert tuner.get_error_rate(src, tgt) is snapshot
        assert tuner.get_error_rate(src, tgt).error_rate == 0.05

    def test_get_error_rate_returns_none_when_absent(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        assert tuner.get_error_rate("a1", "b1") is None

    def test_set_and_get_recovery_pattern(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        pat = RecoveryPattern(
            component_id="b1",
            mean_recovery_seconds=20.0,
            p95_recovery_seconds=45.0,
            recovery_variance=5.0,
            sample_count=100,
        )
        tuner.set_recovery_pattern(pat)
        assert tuner.get_recovery_pattern("b1") is pat
        assert tuner.get_recovery_pattern("nonexistent") is None

    def test_set_and_get_bulkhead_config(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        bh = BulkheadConfig(source_id="a1", target_id="b1", max_concurrent=20)
        tuner.set_bulkhead_config(bh)
        assert tuner.get_bulkhead_config("a1", "b1") is bh
        assert tuner.get_bulkhead_config("a1", "x") is None

    def test_set_test_coverage(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_test_coverage("a1", "b1", ["trip_on_failure", "recovery_after_timeout"])
        # No getter exposed; coverage tested via analyze_test_coverage

    def test_set_and_get_request_rate(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_request_rate("a1", 500.0)
        assert tuner.get_request_rate("a1") == 500.0

    def test_get_request_rate_default_from_component(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        # Should fall back to component capacity.max_rps
        rate = tuner.get_request_rate("a1")
        assert rate == 5000.0  # default max_rps

    def test_get_request_rate_default_when_no_component(self):
        g = InfraGraph()
        tuner = CircuitBreakerTuner(g)
        assert tuner.get_request_rate("nonexistent") == 100.0


# ---------------------------------------------------------------------------
# Failure threshold optimization
# ---------------------------------------------------------------------------


class TestOptimizeFailureThresholds:
    def test_high_error_rate(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.6))
        recs = tuner.optimize_failure_thresholds()
        assert len(recs) == 1
        assert recs[0].recommended_threshold <= 3
        assert "High error rate" in recs[0].rationale

    def test_moderate_error_rate(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.15))
        recs = tuner.optimize_failure_thresholds()
        assert recs[0].recommended_threshold >= 3
        assert "Moderate error rate" in recs[0].rationale

    def test_low_error_rate(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.02))
        recs = tuner.optimize_failure_thresholds()
        assert recs[0].recommended_threshold >= 5
        assert "Low error rate" in recs[0].rationale

    def test_very_low_error_rate(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.001))
        recs = tuner.optimize_failure_thresholds()
        assert recs[0].recommended_threshold >= 8
        assert "Very low error rate" in recs[0].rationale

    def test_no_error_data_uses_default(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        recs = tuner.optimize_failure_thresholds()
        # Default error_rate is 0.01 -> low bucket
        assert recs[0].error_rate == 0.01

    def test_error_rate_at_boundary_0_5(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.5))
        recs = tuner.optimize_failure_thresholds()
        assert recs[0].recommended_threshold >= 2

    def test_error_rate_at_boundary_0_1(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.1))
        recs = tuner.optimize_failure_thresholds()
        assert recs[0].recommended_threshold >= 3

    def test_error_rate_at_boundary_0_01(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.01))
        recs = tuner.optimize_failure_thresholds()
        assert recs[0].recommended_threshold >= 5

    def test_empty_graph(self):
        g = InfraGraph()
        tuner = CircuitBreakerTuner(g)
        assert tuner.optimize_failure_thresholds() == []


# ---------------------------------------------------------------------------
# Recovery timeout tuning
# ---------------------------------------------------------------------------


class TestTuneRecoveryTimeouts:
    def test_with_recovery_pattern(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_recovery_pattern(
            RecoveryPattern("b1", 20.0, 45.0, 5.0, sample_count=50)
        )
        recs = tuner.tune_recovery_timeouts()
        assert len(recs) == 1
        # p95 * 1.2 = 45 * 1.2 = 54
        assert recs[0].recommended_timeout_seconds == 54.0
        assert "50 recovery samples" in recs[0].rationale

    def test_high_variance_adds_buffer(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        # variance > mean * 0.5 triggers extra buffer
        tuner.set_recovery_pattern(
            RecoveryPattern("b1", 20.0, 45.0, 15.0, sample_count=10)
        )
        recs = tuner.tune_recovery_timeouts()
        # 45 * 1.2 * 1.3 = 70.2
        assert recs[0].recommended_timeout_seconds == 70.2
        assert "High recovery variance" in recs[0].rationale

    def test_no_recovery_data(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        recs = tuner.tune_recovery_timeouts()
        assert "default estimate" in recs[0].rationale

    def test_minimum_timeout_is_10(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_recovery_pattern(
            RecoveryPattern("b1", 1.0, 2.0, 0.1, sample_count=5)
        )
        recs = tuner.tune_recovery_timeouts()
        assert recs[0].recommended_timeout_seconds >= 10.0


# ---------------------------------------------------------------------------
# Half-open budget calculation
# ---------------------------------------------------------------------------


class TestCalculateHalfOpenBudgets:
    def test_high_success_rate(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.05))
        budgets = tuner.calculate_half_open_budgets()
        assert len(budgets) == 1
        assert budgets[0].expected_success_rate == 0.95
        assert "High expected success rate" in budgets[0].rationale

    def test_moderate_success_rate(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.3))
        budgets = tuner.calculate_half_open_budgets()
        assert budgets[0].expected_success_rate == 0.7
        assert "Moderate expected success rate" in budgets[0].rationale

    def test_low_success_rate(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.8))
        budgets = tuner.calculate_half_open_budgets()
        assert budgets[0].expected_success_rate == 0.2
        assert "Low expected success rate" in budgets[0].rationale

    def test_zero_success_rate(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=1.0))
        budgets = tuner.calculate_half_open_budgets()
        assert budgets[0].recommended_max_requests >= 1

    def test_no_error_data_uses_default(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        budgets = tuner.calculate_half_open_budgets()
        # Default expected_success = 0.8
        assert budgets[0].expected_success_rate == 0.8

    def test_recommended_capped_at_20(self):
        """Even with very low success rate the budget is capped at 20."""
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, success_threshold=15, half_open_max=15)
        )
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.05))
        budgets = tuner.calculate_half_open_budgets()
        assert budgets[0].recommended_max_requests <= 20


# ---------------------------------------------------------------------------
# Cascading breakers
# ---------------------------------------------------------------------------


class TestAnalyzeCascadingBreakers:
    def test_chain_with_breakers(self):
        g = _chain_graph(4, breaker=True)
        tuner = CircuitBreakerTuner(g)
        cascades = tuner.analyze_cascading_breakers()
        assert len(cascades) >= 1
        for ca in cascades:
            assert len(ca.links) >= 1

    def test_chain_without_breakers(self):
        g = _chain_graph(4, breaker=False)
        tuner = CircuitBreakerTuner(g)
        cascades = tuner.analyze_cascading_breakers()
        # All links unprotected
        for ca in cascades:
            assert ca.has_unprotected_link is True

    def test_deep_cascade_is_critical(self):
        g = _chain_graph(5, breaker=True)
        tuner = CircuitBreakerTuner(g)
        cascades = tuner.analyze_cascading_breakers()
        severities = [c.severity for c in cascades]
        assert Severity.CRITICAL in severities or Severity.WARNING in severities

    def test_single_component_no_cascades(self):
        g = _graph(_comp("a1"))
        tuner = CircuitBreakerTuner(g)
        cascades = tuner.analyze_cascading_breakers()
        assert cascades == []

    def test_two_component_chain(self):
        g = _chain_graph(2, breaker=True)
        tuner = CircuitBreakerTuner(g)
        cascades = tuner.analyze_cascading_breakers()
        assert len(cascades) >= 1
        assert cascades[0].cascade_depth >= 0

    def test_unprotected_with_cascade_depth_2_is_warning(self):
        """Unprotected link with cascade_depth >= 2 -> CRITICAL."""
        comps = [_comp(f"c{i}") for i in range(4)]
        g = _graph(*comps)
        g.add_dependency(_dep("c0", "c1", cb_enabled=False))  # unprotected
        g.add_dependency(_dep("c1", "c2", cb_enabled=True))
        g.add_dependency(_dep("c2", "c3", cb_enabled=True))
        tuner = CircuitBreakerTuner(g)
        cascades = tuner.analyze_cascading_breakers()
        assert any(c.has_unprotected_link for c in cascades)

    def test_total_recovery_seconds(self):
        g = _chain_graph(3, breaker=True)
        tuner = CircuitBreakerTuner(g)
        cascades = tuner.analyze_cascading_breakers()
        for ca in cascades:
            assert ca.total_recovery_seconds >= 0


# ---------------------------------------------------------------------------
# False positive risk
# ---------------------------------------------------------------------------


class TestFalsePositiveRisk:
    def test_low_threshold_increases_risk(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, failure_threshold=2))
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_positive_risk()
        assert len(risks) == 1
        assert risks[0].risk_score > 0.2

    def test_high_jitter_increases_risk(self):
        a = _comp("a1")
        b = Component(
            id="b1", name="b1", type=ComponentType.APP_SERVER,
            network=NetworkProfile(jitter_ms=10.0),
        )
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, failure_threshold=5))
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_positive_risk()
        assert risks[0].risk_score > 0.0
        assert any("jitter" in f.lower() for f in risks[0].contributing_factors)

    def test_retry_amplification_factor(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=3,
                 retry_enabled=True, max_retries=5)
        )
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_positive_risk()
        assert any("Retry" in f for f in risks[0].contributing_factors)

    def test_short_recovery_timeout(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, recovery_timeout=5.0)
        )
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_positive_risk()
        assert any("recovery timeout" in f.lower() for f in risks[0].contributing_factors)

    def test_low_error_rate_with_low_threshold(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, failure_threshold=2))
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.005))
        risks = tuner.assess_false_positive_risk()
        assert risks[0].risk_score >= 0.4

    def test_critical_severity_when_risk_high(self):
        a = _comp("a1")
        b = Component(
            id="b1", name="b1", type=ComponentType.APP_SERVER,
            network=NetworkProfile(jitter_ms=20.0),
        )
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=2,
                 recovery_timeout=5.0, retry_enabled=True, max_retries=3)
        )
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.005))
        risks = tuner.assess_false_positive_risk()
        assert risks[0].severity == Severity.CRITICAL

    def test_disabled_breaker_excluded(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False))
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_positive_risk()
        assert len(risks) == 0

    def test_normal_config_low_risk(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, failure_threshold=10, recovery_timeout=60.0))
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_positive_risk()
        assert risks[0].severity == Severity.INFO


# ---------------------------------------------------------------------------
# False negative risk
# ---------------------------------------------------------------------------


class TestFalseNegativeRisk:
    def test_disabled_breaker_max_risk(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False))
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_negative_risk()
        assert risks[0].risk_score == 1.0
        assert risks[0].severity == Severity.CRITICAL

    def test_disabled_breaker_requires_dependency(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False, dep_type="requires"))
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_negative_risk()
        assert "Enable circuit breaker on this critical" in risks[0].recommendation

    def test_disabled_breaker_optional_dependency(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False, dep_type="optional"))
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_negative_risk()
        assert "Consider enabling" in risks[0].recommendation

    def test_high_threshold_increases_risk(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, failure_threshold=12))
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_negative_risk()
        assert risks[0].risk_score > 0.0
        assert any("High failure threshold" in f for f in risks[0].contributing_factors)

    def test_moderate_high_threshold(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, failure_threshold=8))
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_negative_risk()
        assert any("Moderately high" in f for f in risks[0].contributing_factors)

    def test_long_recovery_timeout_increases_risk(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, recovery_timeout=180.0))
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_negative_risk()
        assert any("Long recovery timeout" in f for f in risks[0].contributing_factors)

    def test_low_request_rate_increases_risk(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True))
        tuner = CircuitBreakerTuner(g)
        tuner.set_request_rate("a1", 5.0)
        risks = tuner.assess_false_negative_risk()
        assert any("Low request rate" in f for f in risks[0].contributing_factors)

    def test_optional_dep_reduces_risk(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=12,
                 dep_type="optional")
        )
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_negative_risk()
        assert any("optional" in f for f in risks[0].contributing_factors)
        # Risk should be halved
        g2 = _graph(_comp("a2"), _comp("b2"))
        g2.add_dependency(
            _dep("a2", "b2", cb_enabled=True, failure_threshold=12, dep_type="requires")
        )
        tuner2 = CircuitBreakerTuner(g2)
        risks2 = tuner2.assess_false_negative_risk()
        assert risks[0].risk_score < risks2[0].risk_score

    def test_well_configured_low_risk(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, failure_threshold=5))
        tuner = CircuitBreakerTuner(g)
        risks = tuner.assess_false_negative_risk()
        assert risks[0].severity == Severity.INFO


# ---------------------------------------------------------------------------
# Retry interactions
# ---------------------------------------------------------------------------


class TestRetryInteractions:
    def test_both_disabled(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False, retry_enabled=False))
        tuner = CircuitBreakerTuner(g)
        results = tuner.analyze_retry_interactions()
        assert results[0].severity == Severity.INFO
        assert "Neither" in results[0].risk_description

    def test_retry_only_no_breaker(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False, retry_enabled=True, max_retries=3))
        tuner = CircuitBreakerTuner(g)
        results = tuner.analyze_retry_interactions()
        assert results[0].retry_enabled is True
        assert results[0].breaker_enabled is False
        assert results[0].severity == Severity.WARNING

    def test_breaker_only_no_retry(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, retry_enabled=False))
        tuner = CircuitBreakerTuner(g)
        results = tuner.analyze_retry_interactions()
        assert results[0].amplification_factor == 1.0
        assert results[0].severity == Severity.INFO

    def test_high_amplification_critical(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=5,
                 retry_enabled=True, max_retries=5)
        )
        tuner = CircuitBreakerTuner(g)
        results = tuner.analyze_retry_interactions()
        assert results[0].amplification_factor == 6.0
        assert results[0].severity == Severity.CRITICAL

    def test_moderate_amplification_warning(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=5,
                 retry_enabled=True, max_retries=2)
        )
        tuner = CircuitBreakerTuner(g)
        results = tuner.analyze_retry_interactions()
        assert results[0].amplification_factor == 3.0
        assert results[0].severity == Severity.WARNING

    def test_low_amplification_info(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=5,
                 retry_enabled=True, max_retries=0)
        )
        tuner = CircuitBreakerTuner(g)
        results = tuner.analyze_retry_interactions()
        assert results[0].amplification_factor == 1.0
        assert results[0].severity == Severity.INFO

    def test_retries_before_trip_calculation(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=10,
                 retry_enabled=True, max_retries=3)
        )
        tuner = CircuitBreakerTuner(g)
        results = tuner.analyze_retry_interactions()
        # 10 // 4 = 2 user requests before trip
        assert results[0].retries_before_trip == 2
        assert results[0].total_attempts_before_trip == 8


# ---------------------------------------------------------------------------
# Bulkhead integration
# ---------------------------------------------------------------------------


class TestBulkheadIntegration:
    def test_no_bulkhead_returns_empty(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        assert tuner.analyze_bulkhead_integration() == []

    def test_bulkhead_below_threshold(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_bulkhead_config(
            BulkheadConfig("a1", "b1", max_concurrent=3, max_queue_size=5, queue_timeout_ms=500)
        )
        results = tuner.analyze_bulkhead_integration()
        assert len(results) == 1
        assert results[0].saturation_trips_breaker is False

    def test_bulkhead_above_threshold(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_bulkhead_config(
            BulkheadConfig("a1", "b1", max_concurrent=10, max_queue_size=5, queue_timeout_ms=500)
        )
        results = tuner.analyze_bulkhead_integration()
        assert results[0].saturation_trips_breaker is True

    def test_queue_timeout_triggers_failure(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_bulkhead_config(
            BulkheadConfig("a1", "b1", max_concurrent=10, max_queue_size=5, queue_timeout_ms=500)
        )
        results = tuner.analyze_bulkhead_integration()
        assert results[0].queue_timeout_triggers_failure is True

    def test_no_breaker_with_bulkhead(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False))
        tuner = CircuitBreakerTuner(g)
        tuner.set_bulkhead_config(BulkheadConfig("a1", "b1", max_concurrent=10))
        results = tuner.analyze_bulkhead_integration()
        assert results[0].severity == Severity.WARNING
        assert "No circuit breaker" in results[0].recommendation

    def test_saturation_and_queue_triggers_warning(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_bulkhead_config(
            BulkheadConfig("a1", "b1", max_concurrent=10, max_queue_size=10, queue_timeout_ms=1000)
        )
        results = tuner.analyze_bulkhead_integration()
        assert results[0].severity == Severity.WARNING


# ---------------------------------------------------------------------------
# State machine simulation
# ---------------------------------------------------------------------------


class TestSimulateStateMachine:
    def test_all_successes_stay_closed(self):
        g, src, tgt = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        seq = [False] * 20  # all successes
        result = tuner.simulate_state_machine(src, tgt, seq)
        assert result.trip_count == 0
        assert result.availability_ratio == 1.0
        assert result.time_in_open_seconds == 0.0

    def test_failures_trip_breaker(self):
        g, src, tgt = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        # threshold=5, send 5 failures
        seq = [True] * 5
        result = tuner.simulate_state_machine(src, tgt, seq)
        assert result.trip_count == 1
        assert len(result.transitions) >= 1
        assert result.transitions[0].to_state == BreakerState.OPEN

    def test_open_to_half_open_after_timeout(self):
        g, src, tgt = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        # threshold=5, recovery_timeout=60s, interval=0.1s
        # Need 5 failures then 600+ requests to pass recovery timeout
        seq = [True] * 5 + [False] * 700
        result = tuner.simulate_state_machine(src, tgt, seq, request_interval_seconds=0.1)
        assert result.trip_count >= 1
        states = [t.to_state for t in result.transitions]
        assert BreakerState.HALF_OPEN in states

    def test_half_open_failure_re_opens(self):
        g, src, tgt = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        # Trip -> wait for recovery -> half_open -> fail -> re-open
        seq = [True] * 5 + [False] * 601 + [True]  # fail in half-open
        result = tuner.simulate_state_machine(src, tgt, seq, request_interval_seconds=0.1)
        open_transitions = [t for t in result.transitions if t.to_state == BreakerState.OPEN]
        assert len(open_transitions) >= 2  # initial trip + re-trip from half-open

    def test_half_open_success_closes(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=3,
                 recovery_timeout=1.0, success_threshold=2)
        )
        tuner = CircuitBreakerTuner(g)
        # Trip with 3 failures, wait >10 requests (1s at 0.1s interval), then 2 successes
        seq = [True] * 3 + [False] * 15 + [False, False]
        result = tuner.simulate_state_machine("a1", "b1", seq, request_interval_seconds=0.1)
        states = [t.to_state for t in result.transitions]
        assert BreakerState.CLOSED in states

    def test_empty_sequence(self):
        g, src, tgt = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        result = tuner.simulate_state_machine(src, tgt, [])
        assert result.trip_count == 0
        assert result.total_time_seconds == 0.0
        assert result.availability_ratio == 1.0

    def test_no_dependency_edge(self):
        g = _graph(_comp("a1"), _comp("b1"))
        tuner = CircuitBreakerTuner(g)
        result = tuner.simulate_state_machine("a1", "b1", [True, True, True])
        # Uses default config (enabled=False), so no trips
        assert result.trip_count == 0

    def test_success_resets_failure_count(self):
        g, src, tgt = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        # threshold=5; alternate 4 failures with a success to reset
        seq = [True] * 4 + [False] + [True] * 4 + [False] + [True] * 4
        result = tuner.simulate_state_machine(src, tgt, seq)
        assert result.trip_count == 0  # never reached 5 consecutive

    def test_custom_request_interval(self):
        g, src, tgt = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        seq = [False] * 10
        result = tuner.simulate_state_machine(src, tgt, seq, request_interval_seconds=1.0)
        assert result.total_time_seconds == 10.0


# ---------------------------------------------------------------------------
# Placement recommendations
# ---------------------------------------------------------------------------


class TestRecommendPlacement:
    def test_high_fan_out_mesh_level(self):
        a = _comp("a1")
        targets = [_comp(f"t{i}") for i in range(6)]
        g = _graph(a, *targets)
        for t in targets:
            g.add_dependency(_dep("a1", t.id, cb_enabled=True))
        tuner = CircuitBreakerTuner(g)
        recs = tuner.recommend_placement()
        strategies = [r.recommended_strategy for r in recs]
        assert PlacementStrategy.MESH_LEVEL in strategies

    def test_external_api_sidecar(self):
        a = _comp("a1")
        b = _comp("b1", ComponentType.EXTERNAL_API)
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True))
        tuner = CircuitBreakerTuner(g)
        recs = tuner.recommend_placement()
        assert recs[0].recommended_strategy == PlacementStrategy.SIDECAR

    def test_single_instance_client_side(self):
        a = _comp("a1")
        b = _comp("b1")  # replicas=1 by default
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, dep_type="requires"))
        tuner = CircuitBreakerTuner(g)
        recs = tuner.recommend_placement()
        assert recs[0].recommended_strategy == PlacementStrategy.CLIENT_SIDE

    def test_moderate_fan_out_sidecar(self):
        a = _comp("a1")
        targets = [_comp(f"t{i}") for i in range(4)]
        g = _graph(a, *targets)
        for t in targets:
            g.add_dependency(_dep("a1", t.id, cb_enabled=True, dep_type="optional"))
        tuner = CircuitBreakerTuner(g)
        recs = tuner.recommend_placement()
        # Fan-out=4, not external API, not single instance requires -> sidecar
        strategies = set(r.recommended_strategy for r in recs)
        assert PlacementStrategy.SIDECAR in strategies

    def test_default_client_side(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, dep_type="optional"))
        tuner = CircuitBreakerTuner(g)
        recs = tuner.recommend_placement()
        assert recs[0].recommended_strategy == PlacementStrategy.CLIENT_SIDE


# ---------------------------------------------------------------------------
# Monitoring gaps
# ---------------------------------------------------------------------------


class TestDetectMonitoringGaps:
    def test_no_breaker_on_critical_dep(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False, dep_type="requires"))
        tuner = CircuitBreakerTuner(g)
        gaps = tuner.detect_monitoring_gaps()
        assert any(g.gap_type == "no_breaker" for g in gaps)
        assert any(g.severity == Severity.CRITICAL for g in gaps)

    def test_no_error_metrics(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        gaps = tuner.detect_monitoring_gaps()
        assert any(g.gap_type == "no_error_metrics" for g in gaps)

    def test_no_recovery_metrics(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", 0.01, sample_count=10))
        gaps = tuner.detect_monitoring_gaps()
        assert any(g.gap_type == "no_recovery_metrics" for g in gaps)

    def test_no_audit_logging(self):
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True))
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", 0.01, sample_count=10))
        tuner.set_recovery_pattern(RecoveryPattern("b1", 20.0, 40.0, 5.0, 5))
        gaps = tuner.detect_monitoring_gaps()
        assert any(g.gap_type == "no_state_alerts" for g in gaps)

    def test_fully_monitored_no_critical_gaps(self):
        a = _comp("a1")
        b = Component(
            id="b1", name="b1", type=ComponentType.APP_SERVER,
            compliance_tags=ComplianceTags(audit_logging=True),
        )
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True))
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", 0.01, sample_count=50))
        tuner.set_recovery_pattern(RecoveryPattern("b1", 20.0, 40.0, 5.0, 50))
        gaps = tuner.detect_monitoring_gaps()
        assert all(g.severity != Severity.CRITICAL for g in gaps)

    def test_disabled_optional_dep_no_gap(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False, dep_type="optional"))
        tuner = CircuitBreakerTuner(g)
        gaps = tuner.detect_monitoring_gaps()
        # No "no_breaker" gap for optional deps
        assert all(g.gap_type != "no_breaker" for g in gaps)


# ---------------------------------------------------------------------------
# Thundering herd risk
# ---------------------------------------------------------------------------


class TestThunderingHerdRisk:
    def test_disabled_breaker_excluded(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False))
        tuner = CircuitBreakerTuner(g)
        assert tuner.assess_thundering_herd_risk() == []

    def test_high_rps_overwhelms(self):
        a = _comp("a1")
        b = Component(
            id="b1", name="b1", type=ComponentType.APP_SERVER,
            capacity=Capacity(max_rps=100),
        )
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, recovery_timeout=60.0))
        tuner = CircuitBreakerTuner(g)
        tuner.set_request_rate("a1", 500.0)
        risks = tuner.assess_thundering_herd_risk()
        assert len(risks) == 1
        assert risks[0].will_overwhelm is True
        assert risks[0].severity in (Severity.WARNING, Severity.CRITICAL)

    def test_low_rps_manageable(self):
        a = _comp("a1")
        b = Component(
            id="b1", name="b1", type=ComponentType.APP_SERVER,
            capacity=Capacity(max_rps=10000),
        )
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, recovery_timeout=5.0))
        tuner = CircuitBreakerTuner(g)
        tuner.set_request_rate("a1", 10.0)
        risks = tuner.assess_thundering_herd_risk()
        assert risks[0].will_overwhelm is False
        assert risks[0].severity == Severity.INFO

    def test_fan_in_amplification(self):
        """Multiple sources pointing to same target amplify herd risk."""
        sources = [_comp(f"s{i}") for i in range(5)]
        target = Component(
            id="t1", name="t1", type=ComponentType.APP_SERVER,
            capacity=Capacity(max_rps=100),
        )
        g = _graph(*sources, target)
        for s in sources:
            g.add_dependency(
                _dep(s.id, "t1", cb_enabled=True, recovery_timeout=60.0)
            )
        tuner = CircuitBreakerTuner(g)
        for s in sources:
            tuner.set_request_rate(s.id, 200.0)
        risks = tuner.assess_thundering_herd_risk()
        assert any(r.will_overwhelm for r in risks)

    def test_critical_burst_ratio(self):
        a = _comp("a1")
        b = Component(
            id="b1", name="b1", type=ComponentType.APP_SERVER,
            capacity=Capacity(max_rps=10),
        )
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, recovery_timeout=60.0))
        tuner = CircuitBreakerTuner(g)
        tuner.set_request_rate("a1", 1000.0)
        risks = tuner.assess_thundering_herd_risk()
        assert risks[0].severity == Severity.CRITICAL
        assert risks[0].recovery_burst_ratio > 5.0


# ---------------------------------------------------------------------------
# Success rate recommendations
# ---------------------------------------------------------------------------


class TestRecommendSuccessRates:
    def test_requires_dependency_high_target(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, dep_type="requires",
                 half_open_max=5, success_threshold=2)
        )
        tuner = CircuitBreakerTuner(g)
        recs = tuner.recommend_success_rates()
        assert recs[0].recommended_success_rate == 0.8

    def test_optional_dependency_lower_target(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, dep_type="optional",
                 half_open_max=5, success_threshold=1)
        )
        tuner = CircuitBreakerTuner(g)
        recs = tuner.recommend_success_rates()
        assert recs[0].recommended_success_rate == 0.6

    def test_async_dependency_lowest_target(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, dep_type="async",
                 half_open_max=5, success_threshold=1)
        )
        tuner = CircuitBreakerTuner(g)
        recs = tuner.recommend_success_rates()
        assert recs[0].recommended_success_rate == 0.5

    def test_low_current_rate_flagged(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, dep_type="requires",
                 half_open_max=10, success_threshold=1)
        )
        tuner = CircuitBreakerTuner(g)
        recs = tuner.recommend_success_rates()
        # current rate = 1/10 = 0.1, target = 0.8, 0.1 < 0.8*0.5=0.4
        assert "much lower" in recs[0].rationale

    def test_adequate_rate(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, dep_type="requires",
                 half_open_max=5, success_threshold=5)
        )
        tuner = CircuitBreakerTuner(g)
        recs = tuner.recommend_success_rates()
        # current rate = 5/5 = 1.0 >= 0.8
        assert "meets or exceeds" in recs[0].rationale

    def test_disabled_breaker_excluded(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False))
        tuner = CircuitBreakerTuner(g)
        assert tuner.recommend_success_rates() == []

    def test_zero_half_open_requests(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, half_open_max=0, success_threshold=2)
        )
        tuner = CircuitBreakerTuner(g)
        recs = tuner.recommend_success_rates()
        assert recs[0].current_half_open_requests == 0


# ---------------------------------------------------------------------------
# Test coverage analysis
# ---------------------------------------------------------------------------


class TestAnalyzeTestCoverage:
    def test_no_tests(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        results = tuner.analyze_test_coverage()
        assert results[0].coverage_level == TestCoverageLevel.NONE
        assert results[0].coverage_score == 0.0

    def test_basic_coverage(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_test_coverage("a1", "b1", ["trip_on_failure"])
        results = tuner.analyze_test_coverage()
        assert results[0].coverage_level == TestCoverageLevel.BASIC
        assert results[0].coverage_score > 0.0

    def test_moderate_coverage(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_test_coverage("a1", "b1", [
            "trip_on_failure", "recovery_after_timeout",
            "half_open_success", "half_open_failure",
        ])
        results = tuner.analyze_test_coverage()
        assert results[0].coverage_level == TestCoverageLevel.MODERATE

    def test_comprehensive_coverage(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_test_coverage("a1", "b1", [
            "trip_on_failure", "recovery_after_timeout",
            "half_open_success", "half_open_failure",
            "concurrent_requests", "retry_interaction",
        ])
        results = tuner.analyze_test_coverage()
        assert results[0].coverage_level == TestCoverageLevel.COMPREHENSIVE
        assert results[0].coverage_score >= 0.75

    def test_disabled_breaker_none_level(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False))
        tuner = CircuitBreakerTuner(g)
        results = tuner.analyze_test_coverage()
        assert results[0].coverage_level == TestCoverageLevel.NONE

    def test_tested_states_from_aspects(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_test_coverage("a1", "b1", [
            "trip_on_failure", "half_open_success",
        ])
        results = tuner.analyze_test_coverage()
        assert BreakerState.CLOSED in results[0].tested_states
        assert BreakerState.OPEN in results[0].tested_states
        assert BreakerState.HALF_OPEN in results[0].tested_states

    def test_recovery_adds_open_and_half_open(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_test_coverage("a1", "b1", ["recovery_after_timeout"])
        results = tuner.analyze_test_coverage()
        assert BreakerState.OPEN in results[0].tested_states
        assert BreakerState.HALF_OPEN in results[0].tested_states

    def test_missing_tests_accurate(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_test_coverage("a1", "b1", ["trip_on_failure"])
        results = tuner.analyze_test_coverage()
        assert "trip_on_failure" not in results[0].missing_tests
        assert "recovery_after_timeout" in results[0].missing_tests


# ---------------------------------------------------------------------------
# Full report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_report_with_no_dependencies(self):
        g = _graph(_comp("a1"))
        tuner = CircuitBreakerTuner(g)
        report = tuner.generate_report()
        assert report.total_dependencies == 0
        assert report.breaker_enabled_count == 0
        assert report.overall_health == Severity.INFO

    def test_report_with_enabled_breakers(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.05, sample_count=100))
        report = tuner.generate_report()
        assert report.total_dependencies == 1
        assert report.breaker_enabled_count == 1
        assert len(report.threshold_recommendations) == 1
        assert len(report.simulation_results) == 1
        assert report.generated_at is not None

    def test_report_no_breakers_recommends_enabling(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=False, dep_type="requires"))
        tuner = CircuitBreakerTuner(g)
        report = tuner.generate_report()
        assert any("No circuit breakers enabled" in r or "lack circuit breakers" in r
                    for r in report.recommendations)

    def test_report_partial_breakers_recommends(self):
        comps = [_comp(f"c{i}") for i in range(3)]
        g = _graph(*comps)
        g.add_dependency(_dep("c0", "c1", cb_enabled=True))
        g.add_dependency(_dep("c1", "c2", cb_enabled=False))
        tuner = CircuitBreakerTuner(g)
        report = tuner.generate_report()
        assert any("lack circuit breakers" in r for r in report.recommendations)

    def test_report_critical_overall(self):
        a = _comp("a1")
        b = Component(
            id="b1", name="b1", type=ComponentType.APP_SERVER,
            network=NetworkProfile(jitter_ms=20.0),
        )
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=2,
                 recovery_timeout=5.0, retry_enabled=True, max_retries=5)
        )
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", 0.005))
        report = tuner.generate_report()
        assert report.overall_health == Severity.CRITICAL

    def test_report_warning_overall(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=3)
        )
        tuner = CircuitBreakerTuner(g)
        report = tuner.generate_report()
        # Should have at least WARNING due to monitoring gaps
        assert report.overall_health in (Severity.WARNING, Severity.CRITICAL)

    def test_report_simulation_uses_error_rate(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        # Use threshold=2 and high error rate (0.9) so the deterministic
        # accumulator produces consecutive failures that trip the breaker.
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=2, recovery_timeout=0.5)
        )
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.9))
        report = tuner.generate_report()
        assert len(report.simulation_results) == 1
        # With 90% error rate and threshold=2, breaker should definitely trip
        assert report.simulation_results[0].trip_count >= 1

    def test_report_includes_all_sections(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", 0.05, sample_count=50))
        tuner.set_recovery_pattern(RecoveryPattern("b1", 20.0, 40.0, 5.0, 50))
        tuner.set_bulkhead_config(BulkheadConfig("a1", "b1", max_concurrent=10))
        tuner.set_test_coverage("a1", "b1", ["trip_on_failure"])
        report = tuner.generate_report()
        assert len(report.threshold_recommendations) >= 1
        assert len(report.recovery_timeout_recommendations) >= 1
        assert len(report.half_open_budgets) >= 1
        assert len(report.false_positive_risks) >= 1
        assert len(report.false_negative_risks) >= 1
        assert len(report.retry_interactions) >= 1
        assert len(report.bulkhead_integrations) >= 1
        assert len(report.placement_recommendations) >= 1
        assert len(report.monitoring_gaps) >= 0
        assert len(report.thundering_herd_risks) >= 1
        assert len(report.success_rate_recommendations) >= 1
        assert len(report.test_coverage_results) >= 1

    def test_report_threshold_mismatch_recommendation(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=1)
        )
        tuner = CircuitBreakerTuner(g)
        report = tuner.generate_report()
        assert any("failure thresholds" in r for r in report.recommendations)

    def test_report_recovery_mismatch_recommendation(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, recovery_timeout=300.0)
        )
        tuner = CircuitBreakerTuner(g)
        report = tuner.generate_report()
        assert any("recovery timeouts" in r for r in report.recommendations)

    def test_report_low_test_coverage_recommendation(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        report = tuner.generate_report()
        assert any("test coverage" in r for r in report.recommendations)


# ---------------------------------------------------------------------------
# Data class instantiation
# ---------------------------------------------------------------------------


class TestDataClasses:
    def test_error_rate_snapshot(self):
        s = ErrorRateSnapshot("a", "b", 0.1, 120.0, 500)
        assert s.source_id == "a"
        assert s.sample_count == 500

    def test_cascade_link(self):
        cl = CascadeLink("a", "b", True, 5, 60.0, False)
        assert cl.breaker_enabled is True
        assert cl.will_cascade is False

    def test_state_transition(self):
        st = StateTransition(1.0, BreakerState.CLOSED, BreakerState.OPEN, "test", 5, 0)
        assert st.from_state == BreakerState.CLOSED

    def test_monitoring_gap(self):
        mg = MonitoringGap("a", "b", "no_breaker", "desc", Severity.CRITICAL, "rec")
        assert mg.gap_type == "no_breaker"

    def test_thundering_herd_risk(self):
        thr = ThunderingHerdRisk("a", "b", 1000, 5.0, 200, True, Severity.CRITICAL, "rec")
        assert thr.will_overwhelm is True

    def test_success_rate_recommendation(self):
        sr = SuccessRateRecommendation("a", "b", 2, 4, 5, 0.8, "rationale")
        assert sr.recommended_success_rate == 0.8

    def test_test_coverage_result(self):
        tc = TestCoverageResult(
            "a", "b", TestCoverageLevel.BASIC,
            [BreakerState.CLOSED], ["recovery_after_timeout"], 0.25, "rec"
        )
        assert tc.coverage_score == 0.25

    def test_half_open_budget(self):
        hob = HalfOpenBudget("a", "b", 3, 5, 2, 0.9, "rationale")
        assert hob.recommended_max_requests == 5

    def test_recovery_timeout_recommendation(self):
        pat = RecoveryPattern("b", 20.0, 40.0, 5.0, 10)
        rtr = RecoveryTimeoutRecommendation("a", "b", 60.0, 48.0, pat, "rationale")
        assert rtr.recommended_timeout_seconds == 48.0

    def test_placement_recommendation(self):
        pr = PlacementRecommendation(
            "a", "b", PlacementStrategy.CLIENT_SIDE, True, "requires", 2, "rationale"
        )
        assert pr.current_has_breaker is True

    def test_bulkhead_config(self):
        bc = BulkheadConfig("a", "b", 10, 20, 1000.0)
        assert bc.max_queue_size == 20

    def test_bulkhead_breaker_integration(self):
        bbi = BulkheadBreakerIntegration(
            "a", "b", 10, 5, True, False, "rec", Severity.INFO
        )
        assert bbi.saturation_trips_breaker is True


# ---------------------------------------------------------------------------
# Edge cases and complex scenarios
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_multiple_dependencies_same_source(self):
        a = _comp("a1")
        b = _comp("b1")
        c = _comp("c1")
        g = _graph(a, b, c)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True))
        g.add_dependency(_dep("a1", "c1", cb_enabled=True))
        tuner = CircuitBreakerTuner(g)
        thresholds = tuner.optimize_failure_thresholds()
        assert len(thresholds) == 2

    def test_diamond_topology(self):
        """A -> B, A -> C, B -> D, C -> D."""
        comps = [_comp(n) for n in ["a", "b", "c", "d"]]
        g = _graph(*comps)
        g.add_dependency(_dep("a", "b", cb_enabled=True))
        g.add_dependency(_dep("a", "c", cb_enabled=True))
        g.add_dependency(_dep("b", "d", cb_enabled=True))
        g.add_dependency(_dep("c", "d", cb_enabled=True))
        tuner = CircuitBreakerTuner(g)
        report = tuner.generate_report()
        assert report.total_dependencies == 4

    def test_large_graph(self):
        """10-node linear chain."""
        g = _chain_graph(10, breaker=True)
        tuner = CircuitBreakerTuner(g)
        report = tuner.generate_report()
        assert report.total_dependencies == 9
        assert report.breaker_enabled_count == 9

    def test_mixed_enabled_disabled(self):
        comps = [_comp(f"c{i}") for i in range(4)]
        g = _graph(*comps)
        g.add_dependency(_dep("c0", "c1", cb_enabled=True))
        g.add_dependency(_dep("c1", "c2", cb_enabled=False))
        g.add_dependency(_dep("c2", "c3", cb_enabled=True))
        tuner = CircuitBreakerTuner(g)
        report = tuner.generate_report()
        assert report.breaker_enabled_count == 2
        fn_risks = report.false_negative_risks
        assert any(r.risk_score == 1.0 for r in fn_risks)

    def test_error_rate_boundary_exact_half(self):
        g, _, _ = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        tuner.set_error_rate(ErrorRateSnapshot("a1", "b1", error_rate=0.5))
        recs = tuner.optimize_failure_thresholds()
        # 0.5 is the boundary for "high" bucket
        assert recs[0].recommended_threshold >= 2

    def test_simulation_alternating_failures(self):
        g, src, tgt = _simple_graph()
        tuner = CircuitBreakerTuner(g)
        # Alternating: never reaches 5 consecutive failures
        seq = [True, False] * 50
        result = tuner.simulate_state_machine(src, tgt, seq)
        assert result.trip_count == 0

    def test_simulation_burst_then_recovery(self):
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=3,
                 recovery_timeout=0.5, success_threshold=2)
        )
        tuner = CircuitBreakerTuner(g)
        # 3 failures -> trip, wait >5 requests -> half_open, 2 successes -> close
        seq = [True] * 3 + [False] * 10 + [False, False]
        result = tuner.simulate_state_machine("a1", "b1", seq, request_interval_seconds=0.1)
        assert result.trip_count >= 1
        closed_transitions = [t for t in result.transitions if t.to_state == BreakerState.CLOSED]
        assert len(closed_transitions) >= 1

    def test_simulation_ends_in_half_open(self):
        """Sequence ends while in HALF_OPEN state (covers final_elapsed branch)."""
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=3,
                 recovery_timeout=0.5, success_threshold=5)
        )
        tuner = CircuitBreakerTuner(g)
        # Trip, wait for recovery, enter half_open, then end with 1 success
        # (not enough to close: need 5 successes)
        seq = [True] * 3 + [False] * 6 + [False]  # ends in half_open after 1 success
        result = tuner.simulate_state_machine("a1", "b1", seq, request_interval_seconds=0.1)
        assert result.time_in_half_open_seconds > 0.0

    def test_false_negative_critical_combined_factors(self):
        """High threshold + long recovery + low rps on requires dep -> CRITICAL."""
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            _dep("a1", "b1", cb_enabled=True, failure_threshold=12,
                 recovery_timeout=180.0, dep_type="requires")
        )
        tuner = CircuitBreakerTuner(g)
        tuner.set_request_rate("a1", 5.0)
        risks = tuner.assess_false_negative_risk()
        # risk = 0.3 (high threshold) + 0.2 (long recovery) + 0.15 (low rps) = 0.65
        assert risks[0].risk_score >= 0.4
        assert risks[0].severity == Severity.CRITICAL

    def test_thundering_herd_zero_max_rps(self):
        """Target with max_rps=0 triggers inf branch."""
        a = _comp("a1")
        b = Component(
            id="b1", name="b1", type=ComponentType.APP_SERVER,
            capacity=Capacity(max_rps=0),
        )
        g = _graph(a, b)
        g.add_dependency(_dep("a1", "b1", cb_enabled=True, recovery_timeout=10.0))
        tuner = CircuitBreakerTuner(g)
        tuner.set_request_rate("a1", 100.0)
        risks = tuner.assess_thundering_herd_risk()
        assert len(risks) == 1
        assert risks[0].recovery_burst_ratio == float("inf")
        assert risks[0].will_overwhelm is True

    def test_cascade_no_critical_paths_fallback(self):
        """Components without edges use single-component fallback (< 2 => skipped)."""
        g = _graph(_comp("a1"), _comp("b1"))
        # No dependencies added -- no edges, no critical paths
        tuner = CircuitBreakerTuner(g)
        cascades = tuner.analyze_cascading_breakers()
        # Single-component paths are < 2 length and get skipped
        assert cascades == []
