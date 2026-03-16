"""Tests for Load Balancer Strategy Analyzer."""

from __future__ import annotations

import math

import pytest
from datetime import datetime, timezone

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.load_balancer_strategy_analyzer import (
    BackendWeightConfig,
    ConnectionDrainingAssessment,
    ConnectionDrainingConfig,
    CrossZoneAssessment,
    CrossZoneConfig,
    FailoverAssessment,
    FailoverBehaviour,
    FairnessGrade,
    FairnessScore,
    HealthCheckAssessment,
    HealthCheckConfig,
    HealthCheckVerdict,
    LBAlgorithm,
    LBStrategyReport,
    LoadBalancerStrategyAnalyzer,
    RedundancyAssessment,
    RedundancyMode,
    SSLAnalysis,
    SSLTerminationPoint,
    SessionPersistenceMode,
    SessionTradeoffAnalysis,
    SlowStartAssessment,
    SlowStartConfig,
    StickySessionAssessment,
    WeightOptimizationResult,
    _coefficient_of_variation,
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


def _lb_graph() -> InfraGraph:
    """LB -> 3 APP_SERVERs standard setup."""
    lb = Component(id="lb", name="lb", type=ComponentType.LOAD_BALANCER, replicas=2)
    api1 = Component(id="api1", name="api1", type=ComponentType.APP_SERVER, replicas=1)
    api2 = Component(id="api2", name="api2", type=ComponentType.APP_SERVER, replicas=1)
    api3 = Component(id="api3", name="api3", type=ComponentType.APP_SERVER, replicas=1)
    g = InfraGraph()
    g.add_component(lb)
    g.add_component(api1)
    g.add_component(api2)
    g.add_component(api3)
    g.add_dependency(Dependency(source_id="lb", target_id="api1"))
    g.add_dependency(Dependency(source_id="lb", target_id="api2"))
    g.add_dependency(Dependency(source_id="lb", target_id="api3"))
    return g


def _analyzer(graph: InfraGraph | None = None) -> LoadBalancerStrategyAnalyzer:
    """Create an analyzer with a simple single-component graph."""
    if graph is None:
        graph = _graph(_comp())
    return LoadBalancerStrategyAnalyzer(graph)


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_lb_algorithm_values(self):
        assert LBAlgorithm.ROUND_ROBIN.value == "round_robin"
        assert LBAlgorithm.WEIGHTED_ROUND_ROBIN.value == "weighted_round_robin"
        assert LBAlgorithm.LEAST_CONNECTIONS.value == "least_connections"
        assert LBAlgorithm.IP_HASH.value == "ip_hash"
        assert LBAlgorithm.RANDOM.value == "random"
        assert LBAlgorithm.LEAST_RESPONSE_TIME.value == "least_response_time"

    def test_lb_algorithm_count(self):
        assert len(LBAlgorithm) == 6

    def test_health_check_verdict_values(self):
        assert HealthCheckVerdict.OPTIMAL.value == "optimal"
        assert HealthCheckVerdict.ACCEPTABLE.value == "acceptable"
        assert HealthCheckVerdict.RISKY.value == "risky"
        assert HealthCheckVerdict.DANGEROUS.value == "dangerous"

    def test_ssl_termination_point_values(self):
        assert SSLTerminationPoint.LOAD_BALANCER.value == "load_balancer"
        assert SSLTerminationPoint.BACKEND.value == "backend"
        assert SSLTerminationPoint.REENCRYPT.value == "reencrypt"
        assert SSLTerminationPoint.PASSTHROUGH.value == "passthrough"

    def test_redundancy_mode_values(self):
        assert RedundancyMode.SINGLE.value == "single"
        assert RedundancyMode.ACTIVE_PASSIVE.value == "active_passive"
        assert RedundancyMode.ACTIVE_ACTIVE.value == "active_active"

    def test_fairness_grade_values(self):
        assert FairnessGrade.EXCELLENT.value == "excellent"
        assert FairnessGrade.GOOD.value == "good"
        assert FairnessGrade.ACCEPTABLE.value == "acceptable"
        assert FairnessGrade.POOR.value == "poor"

    def test_failover_behaviour_values(self):
        assert FailoverBehaviour.REMOVE_AND_REDISTRIBUTE.value == "remove_and_redistribute"
        assert FailoverBehaviour.DRAIN_THEN_REMOVE.value == "drain_then_remove"
        assert FailoverBehaviour.KEEP_SENDING.value == "keep_sending"
        assert FailoverBehaviour.RETURN_503.value == "return_503"

    def test_session_persistence_mode_values(self):
        assert SessionPersistenceMode.NONE.value == "none"
        assert SessionPersistenceMode.COOKIE.value == "cookie"
        assert SessionPersistenceMode.SOURCE_IP.value == "source_ip"
        assert SessionPersistenceMode.HEADER.value == "header"


# ---------------------------------------------------------------------------
# Tests: Health Check Assessment
# ---------------------------------------------------------------------------


class TestHealthCheckAssessment:
    def test_optimal_config(self):
        az = _analyzer()
        config = HealthCheckConfig(
            interval_seconds=10.0,
            timeout_seconds=5.0,
            healthy_threshold=2,
            unhealthy_threshold=3,
        )
        result = az.assess_health_check(config)
        assert result.verdict == HealthCheckVerdict.OPTIMAL
        assert result.interval_ok is True
        assert result.timeout_ok is True
        assert result.threshold_ok is True
        assert result.detection_time_seconds == 30.0  # 10 * 3
        assert result.false_positive_risk == 0.0
        assert result.false_negative_risk == 0.0

    def test_timeout_exceeds_interval(self):
        az = _analyzer()
        config = HealthCheckConfig(interval_seconds=5.0, timeout_seconds=10.0)
        result = az.assess_health_check(config)
        assert result.timeout_ok is False
        assert result.false_positive_risk > 0
        assert any("timeout" in r.lower() for r in result.recommendations)

    def test_very_short_interval(self):
        az = _analyzer()
        config = HealthCheckConfig(interval_seconds=1.0, timeout_seconds=0.5)
        result = az.assess_health_check(config)
        assert result.interval_ok is False
        assert any("short" in r.lower() and "interval" in r.lower()
                    for r in result.recommendations)

    def test_very_long_interval(self):
        az = _analyzer()
        config = HealthCheckConfig(interval_seconds=120.0, timeout_seconds=5.0)
        result = az.assess_health_check(config)
        assert result.interval_ok is False
        assert result.false_negative_risk > 0

    def test_short_timeout(self):
        az = _analyzer()
        config = HealthCheckConfig(interval_seconds=10.0, timeout_seconds=0.5)
        result = az.assess_health_check(config)
        assert result.timeout_ok is False
        assert result.false_positive_risk > 0

    def test_long_timeout(self):
        az = _analyzer()
        config = HealthCheckConfig(interval_seconds=60.0, timeout_seconds=35.0)
        result = az.assess_health_check(config)
        assert result.timeout_ok is False
        assert result.false_negative_risk > 0

    def test_threshold_too_aggressive(self):
        az = _analyzer()
        config = HealthCheckConfig(
            interval_seconds=10.0, timeout_seconds=5.0, unhealthy_threshold=1,
        )
        result = az.assess_health_check(config)
        assert result.threshold_ok is False
        assert result.false_positive_risk > 0

    def test_threshold_too_lenient(self):
        az = _analyzer()
        config = HealthCheckConfig(
            interval_seconds=10.0, timeout_seconds=5.0, unhealthy_threshold=15,
        )
        result = az.assess_health_check(config)
        assert result.threshold_ok is False
        assert result.false_negative_risk > 0

    def test_dangerous_verdict_multiple_issues(self):
        az = _analyzer()
        config = HealthCheckConfig(
            interval_seconds=1.0,
            timeout_seconds=2.0,
            unhealthy_threshold=1,
        )
        result = az.assess_health_check(config)
        # All three checks fail plus high risk
        assert result.verdict in (HealthCheckVerdict.RISKY, HealthCheckVerdict.DANGEROUS)

    def test_detection_time_calculation(self):
        az = _analyzer()
        config = HealthCheckConfig(
            interval_seconds=15.0, timeout_seconds=5.0, unhealthy_threshold=5,
        )
        result = az.assess_health_check(config)
        assert result.detection_time_seconds == 75.0  # 15 * 5


# ---------------------------------------------------------------------------
# Tests: Sticky Session Assessment
# ---------------------------------------------------------------------------


class TestStickySessionAssessment:
    def test_no_sticky_sessions(self):
        az = _analyzer()
        result = az.assess_sticky_session(SessionPersistenceMode.NONE)
        assert result.enabled is False
        assert result.failover_impact == "none"
        assert result.availability_penalty == 0.0

    def test_sticky_single_backend(self):
        az = _analyzer()
        result = az.assess_sticky_session(SessionPersistenceMode.COOKIE, backend_count=1)
        assert result.enabled is True
        assert result.failover_impact == "critical"
        assert result.session_loss_on_failure is True
        assert result.availability_penalty > 0

    def test_sticky_two_backends(self):
        az = _analyzer()
        result = az.assess_sticky_session(SessionPersistenceMode.COOKIE, backend_count=2)
        assert result.failover_impact == "high"

    def test_sticky_four_backends(self):
        az = _analyzer()
        result = az.assess_sticky_session(SessionPersistenceMode.COOKIE, backend_count=4)
        assert result.failover_impact == "moderate"

    def test_sticky_many_backends(self):
        az = _analyzer()
        result = az.assess_sticky_session(SessionPersistenceMode.COOKIE, backend_count=10)
        assert result.failover_impact == "low"

    def test_source_ip_nat_warning(self):
        az = _analyzer()
        result = az.assess_sticky_session(SessionPersistenceMode.SOURCE_IP, backend_count=3)
        assert any("NAT" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# Tests: Connection Draining
# ---------------------------------------------------------------------------


class TestConnectionDraining:
    def test_draining_disabled(self):
        az = _analyzer()
        config = ConnectionDrainingConfig(enabled=False)
        result = az.assess_connection_draining(config)
        assert result.risk_of_dropped_requests == 0.8
        assert any("disabled" in r.lower() for r in result.recommendations)

    def test_draining_short_timeout(self):
        az = _analyzer()
        config = ConnectionDrainingConfig(enabled=True, timeout_seconds=1.0)
        result = az.assess_connection_draining(config, avg_request_duration_seconds=2.0)
        assert result.risk_of_dropped_requests > 0.3

    def test_draining_adequate_timeout(self):
        az = _analyzer()
        config = ConnectionDrainingConfig(enabled=True, timeout_seconds=30.0)
        result = az.assess_connection_draining(config, avg_request_duration_seconds=1.0)
        assert result.risk_of_dropped_requests < 0.3

    def test_draining_very_short(self):
        az = _analyzer()
        config = ConnectionDrainingConfig(enabled=True, timeout_seconds=2.0)
        result = az.assess_connection_draining(config, avg_request_duration_seconds=0.5)
        assert result.risk_of_dropped_requests >= 0.4

    def test_draining_very_long_timeout(self):
        az = _analyzer()
        config = ConnectionDrainingConfig(enabled=True, timeout_seconds=600.0)
        result = az.assess_connection_draining(config)
        assert any("very long" in r.lower() for r in result.recommendations)

    def test_estimated_drain_duration(self):
        az = _analyzer()
        config = ConnectionDrainingConfig(enabled=True, timeout_seconds=30.0)
        result = az.assess_connection_draining(config, avg_request_duration_seconds=2.0)
        assert result.estimated_drain_duration_seconds > 0


# ---------------------------------------------------------------------------
# Tests: Cross-Zone Load Balancing
# ---------------------------------------------------------------------------


class TestCrossZoneAssessment:
    def test_single_zone(self):
        az = _analyzer()
        config = CrossZoneConfig(enabled=False, zone_count=1)
        result = az.assess_cross_zone(config)
        assert result.latency_penalty_ms == 0.0
        assert result.cost_multiplier == 1.0

    def test_disabled_multi_zone_warning(self):
        az = _analyzer()
        config = CrossZoneConfig(enabled=False, zone_count=3)
        result = az.assess_cross_zone(config)
        assert result.zone_imbalance_risk is True
        assert any("disabled" in r.lower() for r in result.recommendations)

    def test_enabled_cross_zone_latency(self):
        az = _analyzer()
        config = CrossZoneConfig(enabled=True, zone_count=3, backends_per_zone=[3, 3, 3])
        result = az.assess_cross_zone(config)
        assert result.latency_penalty_ms > 0
        assert result.cost_multiplier > 1.0

    def test_uneven_backends(self):
        az = _analyzer()
        config = CrossZoneConfig(
            enabled=True, zone_count=3, backends_per_zone=[10, 2, 2],
        )
        result = az.assess_cross_zone(config)
        assert result.zone_imbalance_risk is True

    def test_zone_with_zero_backends(self):
        az = _analyzer()
        config = CrossZoneConfig(
            enabled=True, zone_count=2, backends_per_zone=[5, 0],
        )
        result = az.assess_cross_zone(config)
        assert result.zone_imbalance_risk is True
        assert any("zero backends" in r.lower() for r in result.recommendations)

    def test_high_latency_penalty_warning(self):
        az = _analyzer()
        config = CrossZoneConfig(enabled=True, zone_count=4, backends_per_zone=[2, 2, 2, 2])
        result = az.assess_cross_zone(config)
        assert result.latency_penalty_ms > 4.0
        assert any("latency" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Tests: SSL/TLS Termination
# ---------------------------------------------------------------------------


class TestSSLAnalysis:
    def test_termination_at_lb(self):
        az = _analyzer()
        result = az.analyze_ssl_termination(SSLTerminationPoint.LOAD_BALANCER)
        assert result.end_to_end_encryption is False
        assert result.overhead_ms == 1.5
        assert result.certificate_management_complexity == "low"

    def test_passthrough(self):
        az = _analyzer()
        result = az.analyze_ssl_termination(SSLTerminationPoint.PASSTHROUGH)
        assert result.end_to_end_encryption is True
        assert result.overhead_ms == 0.3
        assert result.certificate_management_complexity == "medium"

    def test_reencrypt(self):
        az = _analyzer()
        result = az.analyze_ssl_termination(SSLTerminationPoint.REENCRYPT)
        assert result.end_to_end_encryption is True
        assert result.overhead_ms == 2.8
        assert result.certificate_management_complexity == "high"

    def test_backend_termination(self):
        az = _analyzer()
        result = az.analyze_ssl_termination(SSLTerminationPoint.BACKEND)
        assert result.end_to_end_encryption is True
        assert result.certificate_management_complexity == "medium"


# ---------------------------------------------------------------------------
# Tests: Backend Weight Optimization
# ---------------------------------------------------------------------------


class TestWeightOptimization:
    def test_empty_backends(self):
        az = _analyzer()
        result = az.optimize_backend_weights([])
        assert len(result.recommendations) > 0

    def test_equal_capacity_equal_weights(self):
        az = _analyzer()
        backends = [
            BackendWeightConfig(backend_id="b1", weight=1.0, capacity_rps=1000.0),
            BackendWeightConfig(backend_id="b2", weight=1.0, capacity_rps=1000.0),
        ]
        result = az.optimize_backend_weights(backends)
        assert len(result.original_weights) == 2
        assert len(result.optimized_weights) == 2

    def test_unequal_capacity_optimized(self):
        az = _analyzer()
        backends = [
            BackendWeightConfig(backend_id="b1", weight=1.0, capacity_rps=3000.0),
            BackendWeightConfig(backend_id="b2", weight=1.0, capacity_rps=1000.0),
        ]
        result = az.optimize_backend_weights(backends)
        # The higher-capacity backend should get more weight
        assert result.optimized_weights[0] > result.optimized_weights[1]

    def test_zero_capacity_backends(self):
        az = _analyzer()
        backends = [
            BackendWeightConfig(backend_id="b1", weight=1.0, capacity_rps=0.0),
            BackendWeightConfig(backend_id="b2", weight=1.0, capacity_rps=0.0),
        ]
        result = az.optimize_backend_weights(backends)
        assert any("zero capacity" in r.lower() for r in result.recommendations)

    def test_equal_weights_different_capacity_recommendation(self):
        az = _analyzer()
        backends = [
            BackendWeightConfig(backend_id="b1", weight=1.0, capacity_rps=5000.0),
            BackendWeightConfig(backend_id="b2", weight=1.0, capacity_rps=500.0),
        ]
        result = az.optimize_backend_weights(backends)
        # Should recommend weighted round-robin or improvement
        assert len(result.recommendations) > 0


# ---------------------------------------------------------------------------
# Tests: Slow Start
# ---------------------------------------------------------------------------


class TestSlowStart:
    def test_disabled(self):
        az = _analyzer()
        config = SlowStartConfig(enabled=False)
        result = az.assess_slow_start(config)
        assert result.cold_start_risk == "high"
        assert result.ramp_up_adequate is False

    def test_adequate_config(self):
        az = _analyzer()
        config = SlowStartConfig(enabled=True, duration_seconds=60.0, initial_weight_percent=10.0)
        result = az.assess_slow_start(config)
        assert result.cold_start_risk == "low"
        assert result.ramp_up_adequate is True

    def test_too_short_duration(self):
        az = _analyzer()
        config = SlowStartConfig(enabled=True, duration_seconds=5.0)
        result = az.assess_slow_start(config)
        assert result.cold_start_risk == "high"
        assert result.ramp_up_adequate is False

    def test_very_long_duration(self):
        az = _analyzer()
        config = SlowStartConfig(enabled=True, duration_seconds=1000.0)
        result = az.assess_slow_start(config)
        assert any("very long" in r.lower() for r in result.recommendations)

    def test_high_initial_weight(self):
        az = _analyzer()
        config = SlowStartConfig(enabled=True, duration_seconds=60.0, initial_weight_percent=70.0)
        result = az.assess_slow_start(config)
        assert result.cold_start_risk == "medium"

    def test_very_low_initial_weight(self):
        az = _analyzer()
        config = SlowStartConfig(enabled=True, duration_seconds=60.0, initial_weight_percent=0.5)
        result = az.assess_slow_start(config)
        assert any("very low" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Tests: LB Redundancy
# ---------------------------------------------------------------------------


class TestRedundancy:
    def test_single_lb(self):
        az = _analyzer()
        result = az.assess_redundancy(RedundancyMode.SINGLE)
        assert result.spof_risk is True
        assert result.failover_time_seconds == float("inf")
        assert result.availability_score < 0.999

    def test_active_passive(self):
        az = _analyzer()
        result = az.assess_redundancy(RedundancyMode.ACTIVE_PASSIVE)
        assert result.spof_risk is False
        assert result.failover_time_seconds == 15.0
        assert result.availability_score >= 0.999

    def test_active_active(self):
        az = _analyzer()
        result = az.assess_redundancy(RedundancyMode.ACTIVE_ACTIVE)
        assert result.spof_risk is False
        assert result.failover_time_seconds == 2.0
        assert result.availability_score > 0.9999

    def test_single_has_recommendation(self):
        az = _analyzer()
        result = az.assess_redundancy(RedundancyMode.SINGLE)
        assert any("single point of failure" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Tests: Fairness Scoring
# ---------------------------------------------------------------------------


class TestFairnessScoring:
    def test_round_robin_perfect(self):
        az = _analyzer()
        result = az.score_fairness(LBAlgorithm.ROUND_ROBIN, backend_count=4)
        assert result.score == 1.0
        assert result.grade == FairnessGrade.EXCELLENT

    def test_single_backend(self):
        az = _analyzer()
        result = az.score_fairness(LBAlgorithm.RANDOM, backend_count=1)
        assert result.score == 1.0
        assert result.grade == FairnessGrade.EXCELLENT

    def test_zero_backends(self):
        az = _analyzer()
        result = az.score_fairness(LBAlgorithm.ROUND_ROBIN, backend_count=0)
        assert result.score == 0.0
        assert result.grade == FairnessGrade.POOR

    def test_ip_hash_less_fair(self):
        az = _analyzer()
        result = az.score_fairness(LBAlgorithm.IP_HASH, backend_count=4)
        assert result.score < 1.0
        assert any("IP" in r for r in result.recommendations)

    def test_least_connections_good(self):
        az = _analyzer()
        result = az.score_fairness(LBAlgorithm.LEAST_CONNECTIONS, backend_count=4)
        assert result.score >= 0.85
        assert result.grade in (FairnessGrade.EXCELLENT, FairnessGrade.GOOD)

    def test_random_fairness(self):
        az = _analyzer()
        result = az.score_fairness(LBAlgorithm.RANDOM, backend_count=10)
        assert 0.0 < result.score <= 1.0

    def test_least_response_time(self):
        az = _analyzer()
        result = az.score_fairness(LBAlgorithm.LEAST_RESPONSE_TIME, backend_count=4)
        assert result.score > 0.5
        assert any("thundering" in r.lower() for r in result.recommendations)

    def test_weighted_round_robin_with_weights(self):
        az = _analyzer()
        result = az.score_fairness(
            LBAlgorithm.WEIGHTED_ROUND_ROBIN,
            backend_weights=[3.0, 1.0, 1.0],
            backend_count=3,
        )
        assert result.score > 0.0
        assert result.coefficient_of_variation > 0.0

    def test_weighted_round_robin_no_weights(self):
        az = _analyzer()
        result = az.score_fairness(
            LBAlgorithm.WEIGHTED_ROUND_ROBIN, backend_count=3,
        )
        assert result.score == 1.0


# ---------------------------------------------------------------------------
# Tests: Failover Assessment
# ---------------------------------------------------------------------------


class TestFailoverAssessment:
    def test_no_backends(self):
        az = _analyzer()
        result = az.assess_failover(total_count=0)
        assert result.risk_level == "critical"

    def test_all_healthy(self):
        az = _analyzer()
        result = az.assess_failover(healthy_count=4, total_count=4)
        assert result.risk_level == "low"

    def test_all_unhealthy(self):
        az = _analyzer()
        result = az.assess_failover(healthy_count=0, total_count=4)
        assert result.risk_level == "critical"

    def test_majority_unhealthy(self):
        az = _analyzer()
        result = az.assess_failover(healthy_count=1, total_count=4)
        assert result.risk_level == "high"

    def test_some_unhealthy(self):
        az = _analyzer()
        result = az.assess_failover(healthy_count=3, total_count=4)
        assert result.risk_level == "moderate"

    def test_keep_sending_critical(self):
        az = _analyzer()
        result = az.assess_failover(
            behaviour=FailoverBehaviour.KEEP_SENDING,
            healthy_count=4,
            total_count=4,
        )
        assert result.risk_level == "critical"

    def test_return_503_recommendation(self):
        az = _analyzer()
        result = az.assess_failover(
            behaviour=FailoverBehaviour.RETURN_503,
            healthy_count=2,
            total_count=4,
        )
        assert any("remove_and_redistribute" in r for r in result.recommendations)

    def test_drain_then_remove_action(self):
        az = _analyzer()
        result = az.assess_failover(
            behaviour=FailoverBehaviour.DRAIN_THEN_REMOVE,
            healthy_count=0,
            total_count=4,
        )
        assert result.all_unhealthy_action == "drain_then_503"


# ---------------------------------------------------------------------------
# Tests: Session Persistence vs Availability Tradeoff
# ---------------------------------------------------------------------------


class TestSessionTradeoff:
    def test_no_persistence(self):
        az = _analyzer()
        result = az.analyze_session_tradeoff(SessionPersistenceMode.NONE)
        assert result.availability_impact == 0.0
        assert result.consistency_benefit == 0.0
        assert result.tradeoff_score == 1.0

    def test_cookie_persistence(self):
        az = _analyzer()
        result = az.analyze_session_tradeoff(
            SessionPersistenceMode.COOKIE, backend_count=4,
        )
        assert result.consistency_benefit == 0.9
        assert result.availability_impact > 0.0

    def test_source_ip_persistence(self):
        az = _analyzer()
        result = az.analyze_session_tradeoff(
            SessionPersistenceMode.SOURCE_IP, backend_count=4,
        )
        assert result.consistency_benefit == 0.7

    def test_header_persistence(self):
        az = _analyzer()
        result = az.analyze_session_tradeoff(
            SessionPersistenceMode.HEADER, backend_count=4,
        )
        assert result.consistency_benefit == 0.85

    def test_single_backend_high_impact(self):
        az = _analyzer()
        result = az.analyze_session_tradeoff(
            SessionPersistenceMode.COOKIE, backend_count=1,
        )
        assert result.availability_impact > result.consistency_benefit or result.tradeoff_score < 0.9

    def test_long_session_amplifies_impact(self):
        az = _analyzer()
        short = az.analyze_session_tradeoff(
            SessionPersistenceMode.COOKIE, backend_count=4, session_duration_minutes=5.0,
        )
        long = az.analyze_session_tradeoff(
            SessionPersistenceMode.COOKIE, backend_count=4, session_duration_minutes=120.0,
        )
        assert long.availability_impact >= short.availability_impact

    def test_tradeoff_score_bounded(self):
        az = _analyzer()
        result = az.analyze_session_tradeoff(
            SessionPersistenceMode.COOKIE, backend_count=1, session_duration_minutes=1000.0,
        )
        assert 0.0 <= result.tradeoff_score <= 1.0

    def test_recommendation_present(self):
        az = _analyzer()
        result = az.analyze_session_tradeoff(
            SessionPersistenceMode.COOKIE, backend_count=4,
        )
        assert result.recommendation != ""


# ---------------------------------------------------------------------------
# Tests: Full Report Generation
# ---------------------------------------------------------------------------


class TestFullReport:
    def test_default_report(self):
        az = _analyzer()
        report = az.generate_report()
        assert report.algorithm == LBAlgorithm.ROUND_ROBIN
        assert report.analyzed_at != ""
        assert 0.0 <= report.overall_resilience_score <= 100.0

    def test_report_with_backends(self):
        az = _analyzer()
        backends = [
            BackendWeightConfig(backend_id="b1", weight=1.0, capacity_rps=1000.0),
            BackendWeightConfig(backend_id="b2", weight=1.0, capacity_rps=2000.0),
        ]
        report = az.generate_report(backends=backends, total_backend_count=2)
        assert report.weight_optimization.original_weights == [1.0, 1.0]

    def test_report_with_custom_algorithm(self):
        az = _analyzer()
        report = az.generate_report(algorithm=LBAlgorithm.LEAST_CONNECTIONS)
        assert report.algorithm == LBAlgorithm.LEAST_CONNECTIONS

    def test_report_active_active_high_score(self):
        az = _analyzer()
        report = az.generate_report(
            redundancy_mode=RedundancyMode.ACTIVE_ACTIVE,
            healthy_backend_count=4,
            total_backend_count=4,
        )
        assert report.overall_resilience_score > 50.0

    def test_report_aggregates_recommendations(self):
        az = _analyzer()
        report = az.generate_report(
            redundancy_mode=RedundancyMode.SINGLE,
            slow_start=SlowStartConfig(enabled=False),
        )
        # Single LB + disabled slow start should each produce recommendations
        assert len(report.recommendations) >= 2

    def test_report_no_duplicate_recommendations(self):
        az = _analyzer()
        report = az.generate_report()
        assert len(report.recommendations) == len(set(report.recommendations))

    def test_report_timestamp_is_utc(self):
        az = _analyzer()
        report = az.generate_report()
        parsed = datetime.fromisoformat(report.analyzed_at)
        assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# Tests: Graph-Aware Helpers
# ---------------------------------------------------------------------------


class TestGraphHelpers:
    def test_find_load_balancers(self):
        graph = _lb_graph()
        az = LoadBalancerStrategyAnalyzer(graph)
        lbs = az.find_load_balancers()
        assert len(lbs) == 1
        assert lbs[0].id == "lb"

    def test_find_backends_for(self):
        graph = _lb_graph()
        az = LoadBalancerStrategyAnalyzer(graph)
        backends = az.find_backends_for("lb")
        assert len(backends) == 3
        backend_ids = {b.id for b in backends}
        assert backend_ids == {"api1", "api2", "api3"}

    def test_no_load_balancers(self):
        graph = _graph(_comp("app1"), _comp("app2"))
        az = LoadBalancerStrategyAnalyzer(graph)
        lbs = az.find_load_balancers()
        assert len(lbs) == 0

    def test_assess_graph_lb_resilience(self):
        graph = _lb_graph()
        az = LoadBalancerStrategyAnalyzer(graph)
        reports = az.assess_graph_lb_resilience()
        assert len(reports) == 1

    def test_assess_graph_with_failover_lb(self):
        lb = Component(
            id="lb", name="lb", type=ComponentType.LOAD_BALANCER,
            replicas=2,
        )
        lb.failover.enabled = True
        api = _comp("api")
        g = _graph(lb, api)
        g.add_dependency(Dependency(source_id="lb", target_id="api"))
        az = LoadBalancerStrategyAnalyzer(g)
        reports = az.assess_graph_lb_resilience()
        assert len(reports) == 1
        assert reports[0].redundancy.mode == RedundancyMode.ACTIVE_ACTIVE

    def test_assess_graph_active_passive_lb(self):
        lb = Component(
            id="lb", name="lb", type=ComponentType.LOAD_BALANCER, replicas=1,
        )
        lb.failover.enabled = True
        api = _comp("api")
        g = _graph(lb, api)
        g.add_dependency(Dependency(source_id="lb", target_id="api"))
        az = LoadBalancerStrategyAnalyzer(g)
        reports = az.assess_graph_lb_resilience()
        assert reports[0].redundancy.mode == RedundancyMode.ACTIVE_PASSIVE

    def test_assess_graph_no_lb(self):
        graph = _graph(_comp("app"))
        az = LoadBalancerStrategyAnalyzer(graph)
        reports = az.assess_graph_lb_resilience()
        assert len(reports) == 0

    def test_assess_graph_unhealthy_backends(self):
        lb = Component(id="lb", name="lb", type=ComponentType.LOAD_BALANCER, replicas=2)
        api1 = Component(id="api1", name="api1", type=ComponentType.APP_SERVER, health=HealthStatus.HEALTHY)
        api2 = Component(id="api2", name="api2", type=ComponentType.APP_SERVER, health=HealthStatus.DOWN)
        g = InfraGraph()
        g.add_component(lb)
        g.add_component(api1)
        g.add_component(api2)
        g.add_dependency(Dependency(source_id="lb", target_id="api1"))
        g.add_dependency(Dependency(source_id="lb", target_id="api2"))
        az = LoadBalancerStrategyAnalyzer(g)
        reports = az.assess_graph_lb_resilience()
        assert len(reports) == 1
        assert reports[0].failover.healthy_backend_count == 1
        assert reports[0].failover.total_backend_count == 2


# ---------------------------------------------------------------------------
# Tests: Helper Functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    def test_coefficient_of_variation_empty(self):
        assert _coefficient_of_variation([]) == 0.0

    def test_coefficient_of_variation_single(self):
        assert _coefficient_of_variation([5.0]) == 0.0

    def test_coefficient_of_variation_equal(self):
        assert _coefficient_of_variation([3.0, 3.0, 3.0]) == 0.0

    def test_coefficient_of_variation_varied(self):
        cv = _coefficient_of_variation([1.0, 2.0, 3.0])
        assert cv > 0.0

    def test_coefficient_of_variation_zeros(self):
        assert _coefficient_of_variation([0.0, 0.0, 0.0]) == 0.0

    def test_coefficient_of_variation_known_value(self):
        # For [2, 4, 4, 4, 5, 5, 7, 9]: mean=5, stddev~=2.0
        values = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        cv = _coefficient_of_variation(values)
        assert 0.3 < cv < 0.5  # ~0.4


# ---------------------------------------------------------------------------
# Tests: Pydantic Models
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_health_check_config_defaults(self):
        config = HealthCheckConfig()
        assert config.interval_seconds == 10.0
        assert config.timeout_seconds == 5.0
        assert config.path == "/health"

    def test_health_check_config_custom(self):
        config = HealthCheckConfig(
            interval_seconds=30.0, timeout_seconds=10.0, path="/ready",
        )
        assert config.interval_seconds == 30.0
        assert config.path == "/ready"

    def test_connection_draining_config_defaults(self):
        config = ConnectionDrainingConfig()
        assert config.enabled is True
        assert config.timeout_seconds == 30.0

    def test_cross_zone_config_defaults(self):
        config = CrossZoneConfig()
        assert config.enabled is False
        assert config.zone_count == 1

    def test_backend_weight_config(self):
        bw = BackendWeightConfig(backend_id="b1", weight=2.5, capacity_rps=5000.0)
        assert bw.backend_id == "b1"
        assert bw.weight == 2.5

    def test_slow_start_config_defaults(self):
        config = SlowStartConfig()
        assert config.enabled is False
        assert config.duration_seconds == 60.0
        assert config.initial_weight_percent == 10.0

    def test_lb_strategy_report_defaults(self):
        report = LBStrategyReport()
        assert report.algorithm == LBAlgorithm.ROUND_ROBIN
        assert report.overall_resilience_score == 0.0

    def test_session_tradeoff_defaults(self):
        st = SessionTradeoffAnalysis()
        assert st.persistence_mode == SessionPersistenceMode.NONE
        assert st.tradeoff_score == 0.0

    def test_failover_assessment_defaults(self):
        fa = FailoverAssessment()
        assert fa.behaviour == FailoverBehaviour.REMOVE_AND_REDISTRIBUTE
        assert fa.risk_level == "low"

    def test_redundancy_assessment_defaults(self):
        ra = RedundancyAssessment()
        assert ra.mode == RedundancyMode.SINGLE
        assert ra.spof_risk is True


# ---------------------------------------------------------------------------
# Tests: Edge Cases and Integration
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_analyzer_with_empty_graph(self):
        g = InfraGraph()
        az = LoadBalancerStrategyAnalyzer(g)
        lbs = az.find_load_balancers()
        assert lbs == []

    def test_multiple_lbs_in_graph(self):
        lb1 = Component(id="lb1", name="lb1", type=ComponentType.LOAD_BALANCER)
        lb2 = Component(id="lb2", name="lb2", type=ComponentType.LOAD_BALANCER)
        api = _comp("api")
        g = _graph(lb1, lb2, api)
        g.add_dependency(Dependency(source_id="lb1", target_id="api"))
        g.add_dependency(Dependency(source_id="lb2", target_id="api"))
        az = LoadBalancerStrategyAnalyzer(g)
        lbs = az.find_load_balancers()
        assert len(lbs) == 2

    def test_overall_score_range(self):
        az = _analyzer()
        for mode in RedundancyMode:
            for algo in LBAlgorithm:
                report = az.generate_report(
                    algorithm=algo,
                    redundancy_mode=mode,
                    total_backend_count=3,
                    healthy_backend_count=3,
                )
                assert 0.0 <= report.overall_resilience_score <= 100.0

    def test_all_ssl_termination_points(self):
        az = _analyzer()
        for point in SSLTerminationPoint:
            result = az.analyze_ssl_termination(point)
            assert result.overhead_ms >= 0
            assert len(result.recommendations) > 0

    def test_all_failover_behaviours(self):
        az = _analyzer()
        for behaviour in FailoverBehaviour:
            result = az.assess_failover(
                behaviour=behaviour, healthy_count=2, total_count=4,
            )
            assert result.total_backend_count == 4

    def test_report_with_all_options(self):
        """Full integration test with all options specified."""
        graph = _lb_graph()
        az = LoadBalancerStrategyAnalyzer(graph)
        report = az.generate_report(
            algorithm=LBAlgorithm.WEIGHTED_ROUND_ROBIN,
            health_check=HealthCheckConfig(
                interval_seconds=15.0, timeout_seconds=3.0,
                unhealthy_threshold=3,
            ),
            sticky_mode=SessionPersistenceMode.COOKIE,
            draining_config=ConnectionDrainingConfig(enabled=True, timeout_seconds=60.0),
            cross_zone=CrossZoneConfig(enabled=True, zone_count=2, backends_per_zone=[2, 2]),
            ssl_termination=SSLTerminationPoint.REENCRYPT,
            backends=[
                BackendWeightConfig(backend_id="b1", weight=2.0, capacity_rps=3000.0),
                BackendWeightConfig(backend_id="b2", weight=1.0, capacity_rps=1000.0),
            ],
            slow_start=SlowStartConfig(enabled=True, duration_seconds=90.0, initial_weight_percent=5.0),
            redundancy_mode=RedundancyMode.ACTIVE_ACTIVE,
            failover_behaviour=FailoverBehaviour.DRAIN_THEN_REMOVE,
            healthy_backend_count=3,
            total_backend_count=4,
            session_duration_minutes=45.0,
        )
        assert report.algorithm == LBAlgorithm.WEIGHTED_ROUND_ROBIN
        assert report.redundancy.mode == RedundancyMode.ACTIVE_ACTIVE
        assert report.ssl_analysis.termination_point == SSLTerminationPoint.REENCRYPT
        assert report.overall_resilience_score > 0.0
        assert len(report.recommendations) > 0
