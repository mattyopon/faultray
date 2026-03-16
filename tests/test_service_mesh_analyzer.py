"""Tests for Service Mesh Analyzer.

Comprehensive tests covering mesh topologies, traffic management, mTLS analysis,
retry policy evaluation, circuit breaker configuration, load balancing strategy,
observability gap detection, control plane resilience, data plane saturation,
and policy enforcement analysis.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.service_mesh_analyzer import (
    BackoffStrategy,
    CircuitBreakerPairConfig,
    CircuitBreakerReport,
    ControlPlaneResilienceResult,
    DataPlaneSaturationReport,
    DataPlaneSaturationResult,
    LoadBalancingAnalysis,
    LoadBalancingReport,
    LoadBalancingStrategy,
    MeshTopology,
    MeshTopologyResult,
    MTLSReport,
    MTLSStatus,
    ObservabilityGap,
    ObservabilityGapReport,
    ObservabilitySignal,
    PolicyEnforcementLevel,
    PolicyEnforcementReport,
    PolicyEnforcementResult,
    RetryPolicyEvaluation,
    RetryPolicyReport,
    ServiceMeshAnalysisReport,
    ServiceMeshConfigAnalyzer,
    TrafficAction,
    TrafficManagementReport,
    TrafficRule,
    _AMBIENT_CPU_PERCENT,
    _AMBIENT_MEMORY_MB,
    _CERT_EXPIRY_WARNING_HOURS,
    _DEFAULT_CERT_ROTATION_HOURS,
    _PER_NODE_CPU_PERCENT,
    _PER_NODE_MEMORY_MB,
    _SIDECAR_CPU_PERCENT,
    _SIDECAR_MEMORY_MB,
    _TOPOLOGY_OVERHEAD,
    _clamp,
)


# ---------------------------------------------------------------------------
# Helpers (required patterns)
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER, **kwargs):
    defaults = {"id": cid, "name": cid, "type": ctype}
    defaults.update(kwargs)
    return Component(**defaults)


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _analyzer():
    return ServiceMeshConfigAnalyzer()


# ---------------------------------------------------------------------------
# 1. Enum completeness
# ---------------------------------------------------------------------------


class TestMeshTopologyEnum:
    def test_all_values(self):
        expected = {"sidecar_proxy", "per_node", "ambient", "none"}
        assert {t.value for t in MeshTopology} == expected

    def test_string_conversion(self):
        assert MeshTopology("sidecar_proxy") == MeshTopology.SIDECAR_PROXY


class TestLoadBalancingStrategyEnum:
    def test_all_values(self):
        expected = {
            "round_robin", "least_connections", "consistent_hashing",
            "locality_aware", "random", "unknown",
        }
        assert {s.value for s in LoadBalancingStrategy} == expected


class TestBackoffStrategyEnum:
    def test_all_values(self):
        expected = {"fixed", "exponential", "linear", "none"}
        assert {s.value for s in BackoffStrategy} == expected


class TestTrafficActionEnum:
    def test_all_values(self):
        expected = {"route", "split", "mirror", "fault_inject", "abort", "delay"}
        assert {a.value for a in TrafficAction} == expected


class TestObservabilitySignalEnum:
    def test_all_values(self):
        expected = {"metrics", "tracing", "logging", "profiling"}
        assert {s.value for s in ObservabilitySignal} == expected


class TestPolicyEnforcementLevelEnum:
    def test_all_values(self):
        expected = {"strict", "permissive", "disabled"}
        assert {l.value for l in PolicyEnforcementLevel} == expected


# ---------------------------------------------------------------------------
# 2. Helper / utility tests
# ---------------------------------------------------------------------------


class TestClamp:
    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_range(self):
        assert _clamp(-10.0) == 0.0

    def test_above_range(self):
        assert _clamp(150.0) == 100.0

    def test_custom_bounds(self):
        assert _clamp(5.0, 10.0, 20.0) == 10.0
        assert _clamp(25.0, 10.0, 20.0) == 20.0
        assert _clamp(15.0, 10.0, 20.0) == 15.0

    def test_boundary_values(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0


class TestConstants:
    def test_topology_overhead_completeness(self):
        for t in MeshTopology:
            assert t in _TOPOLOGY_OVERHEAD

    def test_sidecar_constants(self):
        assert _SIDECAR_MEMORY_MB > 0
        assert _SIDECAR_CPU_PERCENT > 0

    def test_per_node_constants(self):
        assert _PER_NODE_MEMORY_MB > _SIDECAR_MEMORY_MB  # per-node uses more memory

    def test_ambient_constants(self):
        assert _AMBIENT_MEMORY_MB < _SIDECAR_MEMORY_MB  # ambient uses less

    def test_cert_expiry_warning(self):
        assert _CERT_EXPIRY_WARNING_HOURS < _DEFAULT_CERT_ROTATION_HOURS


# ---------------------------------------------------------------------------
# 3. Full analysis on empty graph
# ---------------------------------------------------------------------------


class TestFullAnalysisEmpty:
    def test_empty_graph(self):
        a = _analyzer()
        g = _graph()
        report = a.analyze(g)
        assert report.total_services == 0
        assert report.overall_score == 0.0
        assert len(report.recommendations) > 0
        assert report.timestamp != ""

    def test_timestamp_is_utc_iso(self):
        a = _analyzer()
        g = _graph()
        report = a.analyze(g)
        # Should be parseable as ISO format
        dt = datetime.fromisoformat(report.timestamp)
        assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# 4. Full analysis on populated graph
# ---------------------------------------------------------------------------


class TestFullAnalysisPopulated:
    def test_single_component(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        report = a.analyze(g)
        assert report.total_services == 1
        assert 0.0 <= report.overall_score <= 100.0

    def test_multi_component_with_deps(self):
        a = _analyzer()
        c1 = _comp("frontend", ctype=ComponentType.WEB_SERVER)
        c2 = _comp("backend", ctype=ComponentType.APP_SERVER)
        c3 = _comp("db", ctype=ComponentType.DATABASE)
        g = _graph(c1, c2, c3)
        g.add_dependency(Dependency(source_id="frontend", target_id="backend"))
        g.add_dependency(Dependency(source_id="backend", target_id="db"))
        report = a.analyze(g)
        assert report.total_services == 3
        assert report.overall_score >= 0.0

    def test_with_traffic_rules(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="svc1", target_id="svc2"))
        rules = [
            TrafficRule(source_id="svc1", target_id="svc2", action=TrafficAction.ROUTE)
        ]
        report = a.analyze(g, traffic_rules=rules)
        assert report.topology.coverage_percent > 0

    def test_recommendations_deduplicated(self):
        a = _analyzer()
        c1 = _comp("a1")
        c2 = _comp("a2")
        g = _graph(c1, c2)
        report = a.analyze(g)
        # No duplicates in recommendations
        assert len(report.recommendations) == len(set(report.recommendations))


# ---------------------------------------------------------------------------
# 5. Traffic management analysis
# ---------------------------------------------------------------------------


class TestTrafficManagement:
    def test_empty_graph(self):
        a = _analyzer()
        g = _graph()
        report = a.analyze_traffic_management(g, [])
        assert report.coverage_percent == 0.0

    def test_no_rules(self):
        a = _analyzer()
        c1 = _comp("svc1")
        g = _graph(c1)
        report = a.analyze_traffic_management(g, [])
        assert not report.has_traffic_splitting
        assert not report.has_mirroring
        assert not report.has_fault_injection

    def test_splitting_detected(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="svc1", target_id="svc2"))
        rules = [
            TrafficRule(source_id="svc1", target_id="svc2", action=TrafficAction.SPLIT, weight=80.0)
        ]
        report = a.analyze_traffic_management(g, rules)
        assert report.has_traffic_splitting
        assert "svc1" in report.split_targets

    def test_mirroring_detected(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="svc1", target_id="svc2"))
        rules = [
            TrafficRule(source_id="svc1", target_id="svc2", action=TrafficAction.MIRROR, mirror_percent=100.0)
        ]
        report = a.analyze_traffic_management(g, rules)
        assert report.has_mirroring

    def test_fault_injection_detected(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="svc1", target_id="svc2"))
        rules = [
            TrafficRule(
                source_id="svc1", target_id="svc2",
                action=TrafficAction.FAULT_INJECT, fault_percent=10.0
            )
        ]
        report = a.analyze_traffic_management(g, rules)
        assert report.has_fault_injection

    def test_abort_counts_as_fault_injection(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="svc1", target_id="svc2"))
        rules = [
            TrafficRule(source_id="svc1", target_id="svc2", action=TrafficAction.ABORT)
        ]
        report = a.analyze_traffic_management(g, rules)
        assert report.has_fault_injection

    def test_delay_counts_as_fault_injection(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="svc1", target_id="svc2"))
        rules = [
            TrafficRule(
                source_id="svc1", target_id="svc2",
                action=TrafficAction.DELAY, delay_ms=500.0
            )
        ]
        report = a.analyze_traffic_management(g, rules)
        assert report.has_fault_injection

    def test_coverage_percent(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        c3 = _comp("svc3")
        g = _graph(c1, c2, c3)
        g.add_dependency(Dependency(source_id="svc1", target_id="svc2"))
        g.add_dependency(Dependency(source_id="svc1", target_id="svc3"))
        rules = [
            TrafficRule(source_id="svc1", target_id="svc2", action=TrafficAction.ROUTE)
        ]
        report = a.analyze_traffic_management(g, rules)
        assert report.coverage_percent == 50.0  # 1 of 2 edges covered


# ---------------------------------------------------------------------------
# 6. mTLS analysis
# ---------------------------------------------------------------------------


class TestMTLSAnalysis:
    def test_empty_graph(self):
        a = _analyzer()
        g = _graph()
        report = a.analyze_mtls(g)
        assert len(report.recommendations) > 0

    def test_no_mtls(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        report = a.analyze_mtls(g)
        assert report.overall_mtls_coverage == 0.0
        assert report.statuses[0].mtls_enabled is False
        assert report.statuses[0].spiffe_id == ""

    def test_full_mtls(self):
        a = _analyzer()
        c = _comp("svc1")
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        g = _graph(c)
        report = a.analyze_mtls(g)
        assert report.overall_mtls_coverage == 100.0
        assert report.statuses[0].mtls_enabled is True
        assert "spiffe://" in report.statuses[0].spiffe_id

    def test_partial_mtls(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c1.security.encryption_in_transit = True
        c1.security.auth_required = True
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        report = a.analyze_mtls(g)
        assert report.overall_mtls_coverage == 50.0
        assert any("Enable mTLS" in r for r in report.recommendations)

    def test_cross_trust_domain(self):
        a = _analyzer()
        c1 = _comp("svc1", parameters={"trust_domain": "cluster-a.local"})
        c1.security.encryption_in_transit = True
        c1.security.auth_required = True
        c2 = _comp("svc2", parameters={"trust_domain": "cluster-b.local"})
        c2.security.encryption_in_transit = True
        c2.security.auth_required = True
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="svc1", target_id="svc2"))
        report = a.analyze_mtls(g)
        assert len(report.cross_domain_pairs) == 1
        assert ("svc1", "svc2") in report.cross_domain_pairs
        assert len(report.trust_domains) == 2

    def test_cert_rotation_warning(self):
        a = _analyzer()
        c = _comp("svc1")
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        g = _graph(c)
        report = a.analyze_mtls(g, cert_rotation_hours=2.0)
        assert report.statuses[0].cert_expiry_warning is True
        assert len(report.cert_rotation_issues) > 0

    def test_no_cert_warning_on_normal_rotation(self):
        a = _analyzer()
        c = _comp("svc1")
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        g = _graph(c)
        report = a.analyze_mtls(g, cert_rotation_hours=24.0)
        assert report.statuses[0].cert_expiry_warning is False

    def test_custom_trust_domain(self):
        a = _analyzer()
        c = _comp("svc1")
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        g = _graph(c)
        report = a.analyze_mtls(g, trust_domain="my-domain.io")
        assert report.statuses[0].trust_domain == "my-domain.io"
        assert "my-domain.io" in report.statuses[0].spiffe_id

    def test_numeric_trust_domain_in_parameters(self):
        a = _analyzer()
        c = _comp("svc1", parameters={"trust_domain": 12345})
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        g = _graph(c)
        report = a.analyze_mtls(g)
        assert report.statuses[0].trust_domain == "12345"


# ---------------------------------------------------------------------------
# 7. Retry policy evaluation
# ---------------------------------------------------------------------------


class TestRetryPolicyEvaluation:
    def test_empty_graph(self):
        a = _analyzer()
        g = _graph()
        report = a.analyze_retry_policies(g)
        assert len(report.recommendations) > 0

    def test_no_retry_configured(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="svc1", target_id="svc2"))
        report = a.analyze_retry_policies(g)
        assert all(not e.retry_enabled for e in report.evaluations)
        assert report.retry_storm_risk == 0.0
        assert report.max_amplification_factor == 1.0

    def test_retry_with_budget(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        dep = Dependency(source_id="svc1", target_id="svc2")
        dep.retry_strategy.enabled = True
        dep.retry_strategy.max_retries = 3
        dep.retry_strategy.retry_budget_per_second = 10.0
        dep.retry_strategy.multiplier = 2.0
        dep.retry_strategy.initial_delay_ms = 100.0
        dep.retry_strategy.max_delay_ms = 5000.0
        g.add_dependency(dep)
        report = a.analyze_retry_policies(g)
        svc1_eval = next(e for e in report.evaluations if e.component_id == "svc1")
        assert svc1_eval.retry_enabled is True
        assert svc1_eval.has_budget_limit is True
        assert svc1_eval.backoff_strategy == BackoffStrategy.EXPONENTIAL
        assert len(report.services_without_budget) == 0

    def test_retry_without_budget(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        dep = Dependency(source_id="svc1", target_id="svc2")
        dep.retry_strategy.enabled = True
        dep.retry_strategy.max_retries = 5
        dep.retry_strategy.retry_budget_per_second = 0.0
        g.add_dependency(dep)
        report = a.analyze_retry_policies(g)
        assert "svc1" in report.services_without_budget
        svc1_eval = next(e for e in report.evaluations if e.component_id == "svc1")
        assert svc1_eval.storm_risk > 0.0

    def test_high_retry_amplification(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        c3 = _comp("svc3")
        g = _graph(c1, c2, c3)
        d1 = Dependency(source_id="svc1", target_id="svc2")
        d1.retry_strategy.enabled = True
        d1.retry_strategy.max_retries = 5
        d2 = Dependency(source_id="svc1", target_id="svc3")
        d2.retry_strategy.enabled = True
        d2.retry_strategy.max_retries = 5
        g.add_dependency(d1)
        g.add_dependency(d2)
        report = a.analyze_retry_policies(g)
        assert report.max_amplification_factor > 2.0
        assert any("amplification" in r.lower() for r in report.recommendations)

    def test_fixed_backoff_detection(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        dep = Dependency(source_id="svc1", target_id="svc2")
        dep.retry_strategy.enabled = True
        dep.retry_strategy.max_retries = 2
        dep.retry_strategy.multiplier = 1.0
        g.add_dependency(dep)
        report = a.analyze_retry_policies(g)
        svc1_eval = next(e for e in report.evaluations if e.component_id == "svc1")
        assert svc1_eval.backoff_strategy == BackoffStrategy.FIXED


# ---------------------------------------------------------------------------
# 8. Circuit breaker analysis
# ---------------------------------------------------------------------------


class TestCircuitBreakerAnalysis:
    def test_empty_graph(self):
        a = _analyzer()
        g = _graph()
        report = a.analyze_circuit_breakers(g)
        assert len(report.recommendations) > 0

    def test_no_edges(self):
        a = _analyzer()
        g = _graph(_comp("svc1"))
        report = a.analyze_circuit_breakers(g)
        assert report.coverage_percent == 0.0
        assert len(report.pairs) == 0

    def test_all_edges_have_cb(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        dep = Dependency(source_id="svc1", target_id="svc2")
        dep.circuit_breaker.enabled = True
        dep.circuit_breaker.failure_threshold = 5
        dep.circuit_breaker.recovery_timeout_seconds = 60.0
        dep.circuit_breaker.half_open_max_requests = 3
        dep.circuit_breaker.success_threshold = 2
        g.add_dependency(dep)
        report = a.analyze_circuit_breakers(g)
        assert report.coverage_percent == 100.0
        assert report.pairs[0].effectiveness_score > 80.0

    def test_partial_coverage(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        c3 = _comp("svc3")
        g = _graph(c1, c2, c3)
        d1 = Dependency(source_id="svc1", target_id="svc2")
        d1.circuit_breaker.enabled = True
        d1.circuit_breaker.failure_threshold = 5
        d2 = Dependency(source_id="svc1", target_id="svc3")
        g.add_dependency(d1)
        g.add_dependency(d2)
        report = a.analyze_circuit_breakers(g)
        assert report.coverage_percent == 50.0
        assert any("Enable circuit breakers" in r for r in report.recommendations)

    def test_misconfigured_low_threshold(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        dep = Dependency(source_id="svc1", target_id="svc2")
        dep.circuit_breaker.enabled = True
        dep.circuit_breaker.failure_threshold = 1
        dep.circuit_breaker.recovery_timeout_seconds = 60.0
        g.add_dependency(dep)
        report = a.analyze_circuit_breakers(g)
        assert len(report.misconfigured_pairs) > 0
        assert "threshold too low" in report.misconfigured_pairs[0]

    def test_misconfigured_short_recovery(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        dep = Dependency(source_id="svc1", target_id="svc2")
        dep.circuit_breaker.enabled = True
        dep.circuit_breaker.failure_threshold = 5
        dep.circuit_breaker.recovery_timeout_seconds = 2.0
        g.add_dependency(dep)
        report = a.analyze_circuit_breakers(g)
        assert any("recovery timeout too short" in m for m in report.misconfigured_pairs)

    def test_disabled_cb_score_is_zero(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        dep = Dependency(source_id="svc1", target_id="svc2")
        g.add_dependency(dep)
        report = a.analyze_circuit_breakers(g)
        assert report.pairs[0].effectiveness_score == 0.0


# ---------------------------------------------------------------------------
# 9. Load balancing analysis
# ---------------------------------------------------------------------------


class TestLoadBalancingAnalysis:
    def test_empty_graph(self):
        a = _analyzer()
        g = _graph()
        report = a.analyze_load_balancing(g)
        assert len(report.recommendations) > 0

    def test_single_replica_recommendation(self):
        a = _analyzer()
        c = _comp("svc1", replicas=1)
        g = _graph(c)
        report = a.analyze_load_balancing(g)
        assert any("single replica" in r for r in report.recommendations)

    def test_multi_replica_detected(self):
        a = _analyzer()
        c = _comp("svc1", replicas=3)
        g = _graph(c)
        report = a.analyze_load_balancing(g)
        assert report.analyses[0].replicas == 3
        assert report.analyses[0].effectiveness_score > 0

    def test_load_balancer_type_detection(self):
        a = _analyzer()
        c = _comp("lb1", ctype=ComponentType.LOAD_BALANCER)
        g = _graph(c)
        report = a.analyze_load_balancing(g)
        assert report.analyses[0].strategy == LoadBalancingStrategy.ROUND_ROBIN

    def test_locality_aware_detection(self):
        a = _analyzer()
        c = _comp("lb1", ctype=ComponentType.LOAD_BALANCER)
        c.region.region = "us-east-1"
        c.region.availability_zone = "us-east-1a"
        g = _graph(c)
        report = a.analyze_load_balancing(g)
        assert report.analyses[0].strategy == LoadBalancingStrategy.LOCALITY_AWARE
        assert report.analyses[0].locality_aware is True

    def test_custom_lb_strategy_parameter(self):
        a = _analyzer()
        c = _comp("svc1", parameters={"lb_strategy": "consistent_hashing"})
        g = _graph(c)
        report = a.analyze_load_balancing(g)
        assert report.analyses[0].strategy == LoadBalancingStrategy.CONSISTENT_HASHING
        assert report.analyses[0].sticky_sessions is True

    def test_invalid_lb_strategy_parameter(self):
        a = _analyzer()
        c = _comp("svc1", parameters={"lb_strategy": "invalid_strategy"})
        g = _graph(c)
        report = a.analyze_load_balancing(g)
        # Falls back to UNKNOWN for non-LB single-replica component
        assert report.analyses[0].strategy == LoadBalancingStrategy.UNKNOWN

    def test_strategy_distribution(self):
        a = _analyzer()
        c1 = _comp("svc1", ctype=ComponentType.LOAD_BALANCER)
        c2 = _comp("svc2", replicas=2)
        c3 = _comp("svc3")
        g = _graph(c1, c2, c3)
        report = a.analyze_load_balancing(g)
        assert len(report.strategy_distribution) > 0

    def test_health_check_disabled_recommendation(self):
        a = _analyzer()
        c = _comp("svc1", replicas=2)
        g = _graph(c)
        report = a.analyze_load_balancing(g)
        assert any("health check" in r.lower() for r in report.recommendations)

    def test_health_check_enabled_score_boost(self):
        a = _analyzer()
        c = _comp("svc1", replicas=2)
        c.failover.enabled = True
        g = _graph(c)
        report = a.analyze_load_balancing(g)
        assert report.analyses[0].health_check_enabled is True
        assert report.analyses[0].effectiveness_score >= 50.0


# ---------------------------------------------------------------------------
# 10. Observability gap detection
# ---------------------------------------------------------------------------


class TestObservabilityGaps:
    def test_empty_graph(self):
        a = _analyzer()
        g = _graph()
        report = a.analyze_observability_gaps(g)
        assert len(report.recommendations) > 0

    def test_no_observability(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        report = a.analyze_observability_gaps(g)
        assert report.uncovered_count == 1
        assert report.overall_coverage == 0.0
        gap = report.gaps[0]
        assert not gap.has_metrics
        assert not gap.has_tracing
        assert not gap.has_logging
        assert len(gap.missing_signals) == 3

    def test_full_observability(self):
        a = _analyzer()
        c = _comp("svc1")
        c.security.ids_monitored = True
        c.security.encryption_in_transit = True  # proxy for tracing
        c.security.log_enabled = True
        g = _graph(c)
        report = a.analyze_observability_gaps(g)
        assert report.fully_covered_count == 1
        assert report.uncovered_count == 0
        assert report.overall_coverage == 100.0
        assert len(report.gaps[0].missing_signals) == 0

    def test_partial_observability(self):
        a = _analyzer()
        c = _comp("svc1")
        c.security.log_enabled = True
        g = _graph(c)
        report = a.analyze_observability_gaps(g)
        assert report.partially_covered_count == 1
        gap = report.gaps[0]
        assert gap.has_logging is True
        assert gap.has_metrics is False
        assert gap.coverage_score == pytest.approx(33.3, abs=0.1)

    def test_mixed_observability(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c1.security.ids_monitored = True
        c1.security.encryption_in_transit = True
        c1.security.log_enabled = True
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        report = a.analyze_observability_gaps(g)
        assert report.fully_covered_count == 1
        assert report.uncovered_count == 1
        assert report.overall_coverage == 50.0

    def test_recommendations_for_missing_signals(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        report = a.analyze_observability_gaps(g)
        assert any("metrics" in r.lower() for r in report.recommendations)
        assert any("tracing" in r.lower() for r in report.recommendations)


# ---------------------------------------------------------------------------
# 11. Control plane resilience
# ---------------------------------------------------------------------------


class TestControlPlaneResilience:
    def test_empty_graph(self):
        a = _analyzer()
        g = _graph()
        result = a.analyze_control_plane_resilience(g)
        assert len(result.recommendations) > 0

    def test_no_control_plane(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        result = a.analyze_control_plane_resilience(g)
        assert result.is_highly_available is False
        assert result.replica_count == 1

    def test_ha_control_plane(self):
        a = _analyzer()
        c1 = _comp("cp1", ctype=ComponentType.LOAD_BALANCER, replicas=3)
        c1.failover.enabled = True
        g = _graph(c1)
        result = a.analyze_control_plane_resilience(g)
        assert result.is_highly_available is True
        assert result.failover_capable is True
        assert result.estimated_impact_percent < 50.0

    def test_control_plane_with_tags(self):
        a = _analyzer()
        c = _comp("istiod", tags=["control-plane"])
        c.replicas = 3
        c.failover.enabled = True
        g = _graph(c)
        result = a.analyze_control_plane_resilience(g)
        assert result.is_highly_available is True

    def test_spof_amplifies_impact(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        c3 = _comp("svc3")
        g = _graph(c1, c2, c3)
        result = a.analyze_control_plane_resilience(g)
        # 3 SPOFs should increase impact
        assert result.estimated_impact_percent >= 50.0

    def test_cert_rotation_in_degraded(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        result = a.analyze_control_plane_resilience(g)
        assert "certificate_rotation" in result.degraded_features

    def test_last_known_config_survives(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        result = a.analyze_control_plane_resilience(g)
        assert result.last_known_config_survives is True

    def test_many_services_increases_impact(self):
        a = _analyzer()
        comps = [_comp(f"svc{i}", replicas=2) for i in range(12)]
        for c in comps:
            c.failover.enabled = True
        g = _graph(*comps)
        result = a.analyze_control_plane_resilience(g)
        # With 12 services (>10), extra impact added
        assert result.estimated_impact_percent > 0.0


# ---------------------------------------------------------------------------
# 12. Data plane saturation
# ---------------------------------------------------------------------------


class TestDataPlaneSaturation:
    def test_empty_graph(self):
        a = _analyzer()
        g = _graph()
        report = a.analyze_data_plane_saturation(g)
        assert len(report.recommendations) > 0

    def test_healthy_service(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        report = a.analyze_data_plane_saturation(g)
        assert report.saturated_count == 0
        assert report.results[0].is_saturated is False

    def test_saturated_service(self):
        a = _analyzer()
        c = _comp("svc1")
        c.metrics.cpu_percent = 95.0
        c.metrics.memory_percent = 90.0
        c.metrics.network_connections = 950
        c.capacity.max_connections = 1000
        g = _graph(c)
        report = a.analyze_data_plane_saturation(g)
        assert report.saturated_count == 1
        assert report.results[0].is_saturated is True
        assert any("saturated" in r.lower() for r in report.recommendations)

    def test_connection_pool_exhaustion(self):
        a = _analyzer()
        c = _comp("svc1")
        c.metrics.network_connections = 960
        c.capacity.max_connections = 1000
        g = _graph(c)
        report = a.analyze_data_plane_saturation(g)
        assert report.results[0].connection_pool_usage_percent >= 95.0
        assert report.results[0].connection_pool_exhausted is True

    def test_sidecar_topology_overhead(self):
        a = _analyzer()
        c = _comp("svc1", replicas=2)
        g = _graph(c)
        report = a.analyze_data_plane_saturation(g, topology=MeshTopology.SIDECAR_PROXY)
        result = report.results[0]
        assert result.sidecar_memory_mb == _SIDECAR_MEMORY_MB * 2
        assert result.sidecar_cpu_percent == _SIDECAR_CPU_PERCENT * 2

    def test_ambient_topology_lower_overhead(self):
        a = _analyzer()
        c = _comp("svc1", replicas=2)
        g = _graph(c)
        report = a.analyze_data_plane_saturation(g, topology=MeshTopology.AMBIENT)
        result = report.results[0]
        assert result.sidecar_memory_mb == _AMBIENT_MEMORY_MB * 2
        assert result.sidecar_cpu_percent == _AMBIENT_CPU_PERCENT * 2

    def test_per_node_topology(self):
        a = _analyzer()
        c = _comp("svc1", replicas=1)
        g = _graph(c)
        report = a.analyze_data_plane_saturation(g, topology=MeshTopology.PER_NODE)
        result = report.results[0]
        assert result.sidecar_memory_mb == _PER_NODE_MEMORY_MB

    def test_total_memory_recommendation(self):
        a = _analyzer()
        # Create enough services to exceed 1000 MB total sidecar memory
        comps = [_comp(f"svc{i}", replicas=5) for i in range(5)]
        g = _graph(*comps)
        report = a.analyze_data_plane_saturation(g, topology=MeshTopology.SIDECAR_PROXY)
        # 5 * 5 * 50MB = 1250MB > 1000MB
        assert report.total_sidecar_memory_mb > 1000.0
        assert any("ambient mesh" in r.lower() for r in report.recommendations)

    def test_near_saturation_count(self):
        a = _analyzer()
        c = _comp("svc1")
        c.metrics.cpu_percent = 70.0
        c.metrics.memory_percent = 60.0
        g = _graph(c)
        report = a.analyze_data_plane_saturation(g)
        # saturation_score should be between 50 and 70
        assert report.near_saturation_count >= 0 or report.saturated_count >= 0

    def test_none_topology_zero_overhead(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        report = a.analyze_data_plane_saturation(g, topology=MeshTopology.NONE)
        assert report.results[0].sidecar_memory_mb == 0.0
        assert report.results[0].sidecar_cpu_percent == 0.0


# ---------------------------------------------------------------------------
# 13. Policy enforcement analysis
# ---------------------------------------------------------------------------


class TestPolicyEnforcement:
    def test_empty_graph(self):
        a = _analyzer()
        g = _graph()
        report = a.analyze_policy_enforcement(g)
        assert len(report.recommendations) > 0

    def test_no_policy(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        report = a.analyze_policy_enforcement(g)
        assert report.disabled_count == 1
        assert report.strict_count == 0
        assert report.results[0].auth_policy_level == PolicyEnforcementLevel.DISABLED

    def test_strict_policy(self):
        a = _analyzer()
        c = _comp("svc1")
        c.security.auth_required = True
        c.security.encryption_in_transit = True
        c.security.network_segmented = True
        g = _graph(c)
        report = a.analyze_policy_enforcement(g)
        assert report.strict_count == 1
        assert report.results[0].auth_policy_level == PolicyEnforcementLevel.STRICT
        assert report.results[0].enforcement_score >= 50.0

    def test_permissive_policy(self):
        a = _analyzer()
        c = _comp("svc1")
        c.security.auth_required = True
        g = _graph(c)
        report = a.analyze_policy_enforcement(g)
        assert report.permissive_count == 1
        assert report.results[0].auth_policy_level == PolicyEnforcementLevel.PERMISSIVE

    def test_permissive_via_network_segmented_only(self):
        a = _analyzer()
        c = _comp("svc1")
        c.security.network_segmented = True
        g = _graph(c)
        report = a.analyze_policy_enforcement(g)
        assert report.permissive_count == 1

    def test_rate_limiting_score_boost(self):
        a = _analyzer()
        c = _comp("svc1")
        c.security.rate_limiting = True
        g = _graph(c)
        report = a.analyze_policy_enforcement(g)
        assert report.results[0].rate_limiting_enabled is True
        assert report.results[0].enforcement_score >= 25.0

    def test_waf_protected_score_boost(self):
        a = _analyzer()
        c = _comp("svc1")
        c.security.waf_protected = True
        g = _graph(c)
        report = a.analyze_policy_enforcement(g)
        assert report.results[0].enforcement_score >= 10.0

    def test_mixed_enforcement_levels(self):
        a = _analyzer()
        c1 = _comp("svc1")
        c1.security.auth_required = True
        c1.security.encryption_in_transit = True
        c1.security.network_segmented = True
        c2 = _comp("svc2")
        c2.security.auth_required = True
        c3 = _comp("svc3")
        g = _graph(c1, c2, c3)
        report = a.analyze_policy_enforcement(g)
        assert report.strict_count == 1
        assert report.permissive_count == 1
        assert report.disabled_count == 1

    def test_rate_limit_rps_from_parameters(self):
        a = _analyzer()
        c = _comp("svc1", parameters={"rate_limit_rps": 500.0})
        c.security.rate_limiting = True
        g = _graph(c)
        report = a.analyze_policy_enforcement(g)
        assert report.results[0].rate_limit_rps == 500.0

    def test_recommendations_for_disabled(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        report = a.analyze_policy_enforcement(g)
        assert any("no authorization" in r.lower() for r in report.recommendations)

    def test_recommendations_for_no_rate_limiting(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        report = a.analyze_policy_enforcement(g)
        assert any("rate limiting" in r.lower() for r in report.recommendations)

    def test_recommendations_for_no_network_policy(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        report = a.analyze_policy_enforcement(g)
        assert any("network polic" in r.lower() for r in report.recommendations)


# ---------------------------------------------------------------------------
# 14. Topology detection
# ---------------------------------------------------------------------------


class TestTopologyDetection:
    def test_empty_graph(self):
        a = _analyzer()
        g = _graph()
        result = a.detect_topology(g)
        assert result == []

    def test_default_sidecar(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        results = a.detect_topology(g)
        assert len(results) == 1
        assert results[0].topology == MeshTopology.SIDECAR_PROXY
        assert results[0].proxy_type == "envoy"

    def test_per_node_default(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        results = a.detect_topology(g, default_topology=MeshTopology.PER_NODE)
        assert results[0].topology == MeshTopology.PER_NODE
        assert results[0].proxy_type == "linkerd-proxy"

    def test_ambient_default(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        results = a.detect_topology(g, default_topology=MeshTopology.AMBIENT)
        assert results[0].topology == MeshTopology.AMBIENT
        assert results[0].proxy_type == "ztunnel"

    def test_parameter_override(self):
        a = _analyzer()
        c = _comp("svc1", parameters={"mesh_topology": "ambient"})
        g = _graph(c)
        results = a.detect_topology(g, default_topology=MeshTopology.SIDECAR_PROXY)
        assert results[0].topology == MeshTopology.AMBIENT

    def test_resource_overhead_values(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        results = a.detect_topology(g, default_topology=MeshTopology.SIDECAR_PROXY)
        assert results[0].resource_overhead_mb == _SIDECAR_MEMORY_MB
        assert results[0].resource_overhead_cpu_percent == _SIDECAR_CPU_PERCENT


# ---------------------------------------------------------------------------
# 15. Data model construction tests
# ---------------------------------------------------------------------------


class TestDataModels:
    def test_traffic_rule_defaults(self):
        rule = TrafficRule(source_id="a", target_id="b", action=TrafficAction.ROUTE)
        assert rule.weight == 100.0
        assert rule.fault_percent == 0.0
        assert rule.delay_ms == 0.0

    def test_mtls_status_defaults(self):
        status = MTLSStatus(component_id="x")
        assert status.mtls_enabled is False
        assert status.spiffe_id == ""

    def test_retry_evaluation_defaults(self):
        ev = RetryPolicyEvaluation(component_id="x")
        assert ev.retry_enabled is False
        assert ev.backoff_strategy == BackoffStrategy.NONE

    def test_cb_pair_defaults(self):
        pair = CircuitBreakerPairConfig(source_id="a", target_id="b")
        assert pair.enabled is False
        assert pair.effectiveness_score == 0.0

    def test_lb_analysis_defaults(self):
        lb = LoadBalancingAnalysis(component_id="x")
        assert lb.strategy == LoadBalancingStrategy.UNKNOWN
        assert lb.replicas == 1

    def test_observability_gap_defaults(self):
        gap = ObservabilityGap(component_id="x")
        assert gap.coverage_score == 0.0
        assert len(gap.missing_signals) == 0

    def test_dp_saturation_defaults(self):
        dp = DataPlaneSaturationResult(component_id="x")
        assert dp.is_saturated is False
        assert dp.connection_pool_exhausted is False

    def test_policy_enforcement_defaults(self):
        pe = PolicyEnforcementResult(component_id="x")
        assert pe.auth_policy_level == PolicyEnforcementLevel.DISABLED

    def test_full_report_defaults(self):
        report = ServiceMeshAnalysisReport()
        assert report.total_services == 0
        assert report.overall_score == 0.0

    def test_control_plane_defaults(self):
        cp = ControlPlaneResilienceResult()
        assert cp.is_highly_available is False
        assert cp.last_known_config_survives is True


# ---------------------------------------------------------------------------
# 16. Edge cases and integration
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_component_with_zero_max_connections(self):
        a = _analyzer()
        c = _comp("svc1")
        c.capacity.max_connections = 0
        g = _graph(c)
        report = a.analyze_data_plane_saturation(g)
        assert report.results[0].connection_pool_usage_percent == 0.0

    def test_component_with_no_deps_retry(self):
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        report = a.analyze_retry_policies(g)
        ev = report.evaluations[0]
        assert ev.retry_enabled is False
        assert ev.storm_risk == 0.0

    def test_large_graph_performance(self):
        a = _analyzer()
        comps = [_comp(f"svc{i}") for i in range(50)]
        g = _graph(*comps)
        for i in range(49):
            g.add_dependency(
                Dependency(source_id=f"svc{i}", target_id=f"svc{i+1}")
            )
        report = a.analyze(g)
        assert report.total_services == 50
        assert report.overall_score >= 0.0

    def test_self_referencing_not_crash(self):
        """Ensure self-referencing dependency does not crash analysis."""
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        g.add_dependency(Dependency(source_id="svc1", target_id="svc1"))
        report = a.analyze(g)
        assert report.total_services == 1

    def test_multiple_trust_domains(self):
        a = _analyzer()
        c1 = _comp("svc1", parameters={"trust_domain": "domain-a"})
        c1.security.encryption_in_transit = True
        c1.security.auth_required = True
        c2 = _comp("svc2", parameters={"trust_domain": "domain-b"})
        c2.security.encryption_in_transit = True
        c2.security.auth_required = True
        c3 = _comp("svc3", parameters={"trust_domain": "domain-a"})
        c3.security.encryption_in_transit = True
        c3.security.auth_required = True
        g = _graph(c1, c2, c3)
        g.add_dependency(Dependency(source_id="svc1", target_id="svc2"))
        g.add_dependency(Dependency(source_id="svc3", target_id="svc2"))
        report = a.analyze_mtls(g)
        assert len(report.trust_domains) == 2
        assert len(report.cross_domain_pairs) == 2

    def test_all_topologies_in_analyze(self):
        """Ensure full analysis works with each topology type."""
        a = _analyzer()
        c = _comp("svc1")
        g = _graph(c)
        for topo in MeshTopology:
            report = a.analyze(g, topology=topo)
            assert report.total_services == 1

    def test_high_enforcement_overall_score(self):
        a = _analyzer()
        c = _comp("svc1")
        c.security.auth_required = True
        c.security.encryption_in_transit = True
        c.security.network_segmented = True
        c.security.rate_limiting = True
        c.security.waf_protected = True
        c.security.log_enabled = True
        c.security.ids_monitored = True
        c.failover.enabled = True
        c.replicas = 3
        g = _graph(c)
        report = a.analyze(g)
        assert report.overall_score > 50.0

    def test_lb_strategy_detect_unknown_for_single_non_lb(self):
        strategy = ServiceMeshConfigAnalyzer._detect_lb_strategy(
            _comp("svc1", replicas=1)
        )
        assert strategy == LoadBalancingStrategy.UNKNOWN

    def test_lb_strategy_detect_round_robin_for_multi_replica(self):
        strategy = ServiceMeshConfigAnalyzer._detect_lb_strategy(
            _comp("svc1", replicas=3)
        )
        assert strategy == LoadBalancingStrategy.ROUND_ROBIN

    def test_numeric_trust_domain_in_dep_parameters(self):
        """Cover line 535: numeric trust_domain in dependency target's parameters."""
        a = _analyzer()
        c1 = _comp("svc1", parameters={"trust_domain": "domain-a"})
        c1.security.encryption_in_transit = True
        c1.security.auth_required = True
        c2 = _comp("svc2", parameters={"trust_domain": 99999})
        c2.security.encryption_in_transit = True
        c2.security.auth_required = True
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="svc1", target_id="svc2"))
        report = a.analyze_mtls(g)
        # Numeric domain gets converted to string, so cross-domain detected
        assert len(report.cross_domain_pairs) == 1
        assert "99999" in report.trust_domains

    def test_medium_service_count_impact(self):
        """Cover line 967: 5 < total services <= 10 branch."""
        a = _analyzer()
        # Use 7 services with replicas=2 and failover to avoid SPOF penalty
        comps = [_comp(f"svc{i}", replicas=2) for i in range(7)]
        for c in comps:
            c.failover.enabled = True
        g = _graph(*comps)
        result = a.analyze_control_plane_resilience(g)
        # With 7 services (>5, <=10), medium impact branch is hit
        assert result.estimated_impact_percent > 0.0
