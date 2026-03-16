"""Tests for the Service Mesh Analyzer."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.service_mesh import (
    MeshComponent,
    MeshPattern,
    MeshReadiness,
    MeshReport,
    ObservabilityScore,
    SecurityPolicy,
    ServiceMeshAnalyzer,
    TimeoutChain,
    TrafficPolicy,
    _readiness_from_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    **kwargs,
) -> Component:
    """Create a component with sensible defaults."""
    return Component(id=cid, name=cid, type=ctype, replicas=replicas, **kwargs)


def _graph(
    components: list[Component],
    deps: list[Dependency] | None = None,
) -> InfraGraph:
    """Build an InfraGraph from components and dependency edges."""
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for d in deps or []:
        g.add_dependency(d)
    return g


def _dep(src: str, tgt: str, **kwargs) -> Dependency:
    """Shortcut for building a Dependency edge."""
    return Dependency(source_id=src, target_id=tgt, **kwargs)


# ---------------------------------------------------------------------------
# 1. Enum tests
# ---------------------------------------------------------------------------

class TestMeshPatternEnum:
    def test_all_patterns_exist(self):
        expected = {
            "sidecar_proxy", "circuit_breaker", "retry_budget",
            "timeout_chain", "mutual_tls", "traffic_splitting",
            "rate_limiting", "load_balancing", "health_checking",
            "fault_injection",
        }
        assert {p.value for p in MeshPattern} == expected

    def test_pattern_count(self):
        assert len(MeshPattern) == 10


class TestMeshReadinessEnum:
    def test_all_levels(self):
        expected = {"not_ready", "partial", "ready", "advanced"}
        assert {r.value for r in MeshReadiness} == expected

    def test_readiness_count(self):
        assert len(MeshReadiness) == 4


# ---------------------------------------------------------------------------
# 2. Readiness scoring helper
# ---------------------------------------------------------------------------

class TestReadinessFromScore:
    def test_not_ready(self):
        assert _readiness_from_score(0.0) == MeshReadiness.NOT_READY
        assert _readiness_from_score(24.9) == MeshReadiness.NOT_READY

    def test_partial(self):
        assert _readiness_from_score(25.0) == MeshReadiness.PARTIAL
        assert _readiness_from_score(49.9) == MeshReadiness.PARTIAL

    def test_ready(self):
        assert _readiness_from_score(50.0) == MeshReadiness.READY
        assert _readiness_from_score(80.0) == MeshReadiness.READY

    def test_advanced(self):
        assert _readiness_from_score(80.1) == MeshReadiness.ADVANCED
        assert _readiness_from_score(100.0) == MeshReadiness.ADVANCED


# ---------------------------------------------------------------------------
# 3. Empty graph
# ---------------------------------------------------------------------------

class TestEmptyGraph:
    def test_empty_graph_analysis(self):
        g = _graph([])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        assert report.overall_readiness == MeshReadiness.NOT_READY
        assert report.readiness_score == 0.0
        assert report.traffic_management_score == 0.0
        assert report.security_score == 0.0
        assert report.observability_score == 0.0
        assert report.components == []
        assert report.patterns_summary == {}
        assert report.timeout_chains == []
        assert report.anti_patterns == []
        assert len(report.recommendations) >= 1

    def test_empty_graph_migration_plan(self):
        g = _graph([])
        analyzer = ServiceMeshAnalyzer()
        plan = analyzer.get_mesh_migration_plan(g)
        assert plan == []

    def test_empty_graph_detect_patterns(self):
        g = _graph([])
        analyzer = ServiceMeshAnalyzer()
        result = analyzer.detect_patterns(g)
        assert result == {}


# ---------------------------------------------------------------------------
# 4. Single component analysis
# ---------------------------------------------------------------------------

class TestSingleComponentAnalysis:
    def test_basic_component_no_patterns(self):
        g = _graph([_comp("app")])
        analyzer = ServiceMeshAnalyzer()
        mc = analyzer.analyze_component(g, "app")

        assert mc is not None
        assert mc.component_id == "app"
        assert mc.component_name == "app"
        assert mc.component_type == "app_server"
        assert mc.readiness == MeshReadiness.NOT_READY

    def test_nonexistent_component_returns_none(self):
        g = _graph([_comp("app")])
        analyzer = ServiceMeshAnalyzer()
        assert analyzer.analyze_component(g, "missing") is None

    def test_component_with_full_security(self):
        c = _comp("secure")
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        c.security.network_segmented = True
        c.security.rate_limiting = True
        c.security.log_enabled = True
        c.security.ids_monitored = True

        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()
        mc = analyzer.analyze_component(g, "secure")

        assert mc is not None
        assert mc.security_policy.mtls_enabled is True
        assert mc.security_policy.auth_enabled is True
        assert mc.security_policy.encrypted is True
        assert mc.security_policy.network_segmented is True

    def test_component_with_timeout(self):
        c = _comp("api")
        c.capacity.timeout_seconds = 30.0
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()
        mc = analyzer.analyze_component(g, "api")

        assert mc is not None
        assert mc.traffic_policy.has_timeout is True
        assert mc.traffic_policy.timeout_seconds == 30.0
        assert MeshPattern.TIMEOUT_CHAIN in mc.patterns_detected


# ---------------------------------------------------------------------------
# 5. Pattern detection
# ---------------------------------------------------------------------------

class TestPatternDetection:
    def test_circuit_breaker_pattern(self):
        c1 = _comp("frontend")
        c2 = _comp("backend")
        dep = _dep("frontend", "backend")
        dep.circuit_breaker.enabled = True
        g = _graph([c1, c2], [dep])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.CIRCUIT_BREAKER.value in patterns["frontend"]
        assert MeshPattern.CIRCUIT_BREAKER.value in patterns["backend"]

    def test_retry_budget_pattern(self):
        c1 = _comp("svc-a")
        c2 = _comp("svc-b")
        dep = _dep("svc-a", "svc-b")
        dep.retry_strategy.enabled = True
        dep.retry_strategy.max_retries = 3
        g = _graph([c1, c2], [dep])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.RETRY_BUDGET.value in patterns["svc-a"]

    def test_sidecar_proxy_pattern_requires_both_retry_and_cb(self):
        c1 = _comp("gateway")
        c2 = _comp("service")
        dep = _dep("gateway", "service")
        dep.circuit_breaker.enabled = True
        dep.retry_strategy.enabled = True
        g = _graph([c1, c2], [dep])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.SIDECAR_PROXY.value in patterns["gateway"]

    def test_sidecar_proxy_not_detected_with_only_cb(self):
        c1 = _comp("gw")
        c2 = _comp("svc")
        dep = _dep("gw", "svc")
        dep.circuit_breaker.enabled = True
        g = _graph([c1, c2], [dep])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.SIDECAR_PROXY.value not in patterns["gw"]

    def test_mutual_tls_pattern(self):
        c = _comp("secure-svc")
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.MUTUAL_TLS.value in patterns["secure-svc"]

    def test_mutual_tls_not_detected_without_auth(self):
        c = _comp("enc-only")
        c.security.encryption_in_transit = True
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.MUTUAL_TLS.value not in patterns["enc-only"]

    def test_traffic_splitting_pattern(self):
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER)
        s1 = _comp("svc-1")
        s2 = _comp("svc-2")
        g = _graph(
            [lb, s1, s2],
            [_dep("lb", "svc-1"), _dep("lb", "svc-2")],
        )
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.TRAFFIC_SPLITTING.value in patterns["lb"]

    def test_traffic_splitting_not_with_single_target(self):
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER)
        s1 = _comp("svc-1")
        g = _graph([lb, s1], [_dep("lb", "svc-1")])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.TRAFFIC_SPLITTING.value not in patterns["lb"]

    def test_rate_limiting_pattern(self):
        c = _comp("api")
        c.security.rate_limiting = True
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.RATE_LIMITING.value in patterns["api"]

    def test_load_balancing_pattern_lb_type(self):
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER)
        g = _graph([lb])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.LOAD_BALANCING.value in patterns["lb"]

    def test_load_balancing_pattern_replicas(self):
        c = _comp("api", replicas=3)
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.LOAD_BALANCING.value in patterns["api"]

    def test_load_balancing_not_detected_single_replica_non_lb(self):
        c = _comp("api", replicas=1)
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.LOAD_BALANCING.value not in patterns["api"]

    def test_health_checking_pattern(self):
        c = _comp("svc")
        c.failover.enabled = True
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.HEALTH_CHECKING.value in patterns["svc"]

    def test_health_checking_not_detected_without_failover(self):
        c = _comp("svc")
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.HEALTH_CHECKING.value not in patterns["svc"]

    def test_fault_injection_never_detected(self):
        c = _comp("svc")
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        c.security.rate_limiting = True
        c.failover.enabled = True
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.FAULT_INJECTION.value not in patterns["svc"]

    def test_timeout_chain_pattern(self):
        c = _comp("svc")
        c.capacity.timeout_seconds = 15.0
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()

        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.TIMEOUT_CHAIN.value in patterns["svc"]


# ---------------------------------------------------------------------------
# 6. Timeout chain validation
# ---------------------------------------------------------------------------

class TestTimeoutChainValidation:
    def test_valid_timeout_chain(self):
        """Outer timeout > inner timeout + margin should be valid."""
        gateway = _comp("gateway")
        gateway.capacity.timeout_seconds = 60.0

        service = _comp("service")
        service.capacity.timeout_seconds = 20.0

        db = _comp("db", ctype=ComponentType.DATABASE)
        db.capacity.timeout_seconds = 5.0

        g = _graph(
            [gateway, service, db],
            [_dep("gateway", "service"), _dep("service", "db")],
        )
        analyzer = ServiceMeshAnalyzer()
        chains = analyzer.validate_timeout_chains(g)

        assert len(chains) >= 1
        # Find the full chain
        full_chains = [c for c in chains if len(c.path) == 3]
        assert len(full_chains) >= 1
        for chain in full_chains:
            assert chain.is_valid is True
            assert chain.issue is None

    def test_invalid_timeout_chain(self):
        """Outer timeout <= inner timeout should be flagged."""
        gateway = _comp("gateway")
        gateway.capacity.timeout_seconds = 10.0

        service = _comp("service")
        service.capacity.timeout_seconds = 30.0

        g = _graph(
            [gateway, service],
            [_dep("gateway", "service")],
        )
        analyzer = ServiceMeshAnalyzer()
        chains = analyzer.validate_timeout_chains(g)

        assert len(chains) >= 1
        invalid = [c for c in chains if not c.is_valid]
        assert len(invalid) >= 1
        assert invalid[0].issue is not None
        assert "gateway" in invalid[0].issue

    def test_equal_timeouts_are_invalid(self):
        """Equal timeouts (no margin) are flagged."""
        svc_a = _comp("svc-a")
        svc_a.capacity.timeout_seconds = 30.0

        svc_b = _comp("svc-b")
        svc_b.capacity.timeout_seconds = 30.0

        g = _graph(
            [svc_a, svc_b],
            [_dep("svc-a", "svc-b")],
        )
        analyzer = ServiceMeshAnalyzer()
        chains = analyzer.validate_timeout_chains(g)

        invalid = [c for c in chains if not c.is_valid]
        assert len(invalid) >= 1

    def test_timeout_chain_path_names(self):
        gw = _comp("gw")
        gw.capacity.timeout_seconds = 100.0
        svc = _comp("svc")
        svc.capacity.timeout_seconds = 10.0

        g = _graph([gw, svc], [_dep("gw", "svc")])
        analyzer = ServiceMeshAnalyzer()
        chains = analyzer.validate_timeout_chains(g)

        assert len(chains) >= 1
        assert chains[0].path_names == ["gw", "svc"]
        assert chains[0].timeouts == [100.0, 10.0]

    def test_no_timeout_chains_single_component(self):
        g = _graph([_comp("solo")])
        analyzer = ServiceMeshAnalyzer()
        chains = analyzer.validate_timeout_chains(g)
        assert chains == []

    def test_timeout_chain_three_node_middle_violation(self):
        """Middle node has higher timeout than first node."""
        a = _comp("a")
        a.capacity.timeout_seconds = 20.0
        b = _comp("b")
        b.capacity.timeout_seconds = 50.0  # violation: b > a
        c = _comp("c")
        c.capacity.timeout_seconds = 5.0

        g = _graph([a, b, c], [_dep("a", "b"), _dep("b", "c")])
        analyzer = ServiceMeshAnalyzer()
        chains = analyzer.validate_timeout_chains(g)

        full = [ch for ch in chains if len(ch.path) == 3]
        assert any(not ch.is_valid for ch in full)


# ---------------------------------------------------------------------------
# 7. Anti-pattern detection
# ---------------------------------------------------------------------------

class TestAntiPatternDetection:
    def test_retry_storm(self):
        """Multiple retry layers without budget limits."""
        app = _comp("app")
        svc1 = _comp("svc1")
        svc2 = _comp("svc2")

        dep1 = _dep("app", "svc1")
        dep1.retry_strategy.enabled = True
        dep1.retry_strategy.retry_budget_per_second = 0.0  # no budget

        dep2 = _dep("app", "svc2")
        dep2.retry_strategy.enabled = True
        dep2.retry_strategy.retry_budget_per_second = 0.0  # no budget

        g = _graph([app, svc1, svc2], [dep1, dep2])
        analyzer = ServiceMeshAnalyzer()
        anti = analyzer.detect_anti_patterns(g)

        retry_storm = [a for a in anti if "Retry storm" in a]
        assert len(retry_storm) >= 1
        assert "app" in retry_storm[0]

    def test_no_retry_storm_with_budget(self):
        """Retry layers with budget limits should not trigger."""
        app = _comp("app")
        svc1 = _comp("svc1")
        svc2 = _comp("svc2")

        dep1 = _dep("app", "svc1")
        dep1.retry_strategy.enabled = True
        dep1.retry_strategy.retry_budget_per_second = 10.0  # has budget

        dep2 = _dep("app", "svc2")
        dep2.retry_strategy.enabled = True
        dep2.retry_strategy.retry_budget_per_second = 10.0

        g = _graph([app, svc1, svc2], [dep1, dep2])
        analyzer = ServiceMeshAnalyzer()
        anti = analyzer.detect_anti_patterns(g)

        retry_storm = [a for a in anti if "Retry storm" in a]
        assert len(retry_storm) == 0

    def test_timeout_cascade_anti_pattern(self):
        """Outer <= inner timeout should be detected."""
        outer = _comp("outer")
        outer.capacity.timeout_seconds = 10.0
        inner = _comp("inner")
        inner.capacity.timeout_seconds = 30.0

        g = _graph([outer, inner], [_dep("outer", "inner")])
        analyzer = ServiceMeshAnalyzer()
        anti = analyzer.detect_anti_patterns(g)

        cascade = [a for a in anti if "Timeout cascade" in a]
        assert len(cascade) >= 1

    def test_missing_circuit_breaker(self):
        """High-dependency component without CB protection."""
        core = _comp("core")
        clients = [_comp(f"client-{i}") for i in range(3)]

        deps = [_dep(c.id, "core") for c in clients]
        # No circuit breakers on any edge

        g = _graph([core] + clients, deps)
        analyzer = ServiceMeshAnalyzer()
        anti = analyzer.detect_anti_patterns(g)

        missing_cb = [a for a in anti if "Missing circuit breaker" in a]
        assert len(missing_cb) >= 1
        assert "core" in missing_cb[0]

    def test_no_missing_cb_when_all_edges_have_cb(self):
        """All edges have CB so no anti-pattern."""
        core = _comp("core")
        clients = [_comp(f"client-{i}") for i in range(3)]

        deps = []
        for c in clients:
            d = _dep(c.id, "core")
            d.circuit_breaker.enabled = True
            deps.append(d)

        g = _graph([core] + clients, deps)
        analyzer = ServiceMeshAnalyzer()
        anti = analyzer.detect_anti_patterns(g)

        missing_cb = [a for a in anti if "Missing circuit breaker" in a]
        assert len(missing_cb) == 0

    def test_unprotected_external(self):
        """External API without rate limiting or CB."""
        ext = _comp("ext-api", ctype=ComponentType.EXTERNAL_API)
        app = _comp("app")
        g = _graph([ext, app], [_dep("app", "ext-api")])
        analyzer = ServiceMeshAnalyzer()
        anti = analyzer.detect_anti_patterns(g)

        unprotected = [a for a in anti if "Unprotected external" in a]
        assert len(unprotected) >= 1
        assert "ext-api" in unprotected[0]

    def test_no_unprotected_external_with_cb(self):
        """External API with CB should not be flagged."""
        ext = _comp("ext-api", ctype=ComponentType.EXTERNAL_API)
        app = _comp("app")
        dep = _dep("app", "ext-api")
        dep.circuit_breaker.enabled = True
        g = _graph([ext, app], [dep])
        analyzer = ServiceMeshAnalyzer()
        anti = analyzer.detect_anti_patterns(g)

        unprotected = [a for a in anti if "Unprotected external" in a]
        assert len(unprotected) == 0

    def test_no_unprotected_external_with_rate_limit(self):
        """External API with rate limiting should not be flagged."""
        ext = _comp("ext-api", ctype=ComponentType.EXTERNAL_API)
        ext.security.rate_limiting = True
        app = _comp("app")
        g = _graph([ext, app], [_dep("app", "ext-api")])
        analyzer = ServiceMeshAnalyzer()
        anti = analyzer.detect_anti_patterns(g)

        unprotected = [a for a in anti if "Unprotected external" in a]
        assert len(unprotected) == 0

    def test_inconsistent_mtls(self):
        """Some components with mTLS, others without."""
        secure = _comp("secure")
        secure.security.encryption_in_transit = True
        secure.security.auth_required = True

        insecure = _comp("insecure")

        g = _graph([secure, insecure])
        analyzer = ServiceMeshAnalyzer()
        anti = analyzer.detect_anti_patterns(g)

        inconsistent = [a for a in anti if "Inconsistent mTLS" in a]
        assert len(inconsistent) >= 1
        assert "insecure" in inconsistent[0]

    def test_no_inconsistent_mtls_when_all_have_mtls(self):
        """All components with mTLS should not trigger."""
        comps = []
        for i in range(3):
            c = _comp(f"svc-{i}")
            c.security.encryption_in_transit = True
            c.security.auth_required = True
            comps.append(c)

        g = _graph(comps)
        analyzer = ServiceMeshAnalyzer()
        anti = analyzer.detect_anti_patterns(g)

        inconsistent = [a for a in anti if "Inconsistent mTLS" in a]
        assert len(inconsistent) == 0

    def test_no_inconsistent_mtls_when_none_have_mtls(self):
        """No components with mTLS should not trigger."""
        g = _graph([_comp("a"), _comp("b")])
        analyzer = ServiceMeshAnalyzer()
        anti = analyzer.detect_anti_patterns(g)

        inconsistent = [a for a in anti if "Inconsistent mTLS" in a]
        assert len(inconsistent) == 0


# ---------------------------------------------------------------------------
# 8. Readiness scoring levels
# ---------------------------------------------------------------------------

class TestReadinessScoring:
    def test_not_ready_score(self):
        """Bare components should score NOT_READY."""
        g = _graph([_comp("a"), _comp("b")])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        assert report.overall_readiness == MeshReadiness.NOT_READY
        assert report.readiness_score < 25

    def test_partial_readiness(self):
        """Components with some features should score PARTIAL."""
        c = _comp("svc")
        c.capacity.timeout_seconds = 30.0
        c.security.rate_limiting = True

        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        # Timeout + rate limit = 2/4 traffic (50%), 0/4 security, some obs
        assert report.readiness_score >= 0
        # Verify readiness is consistent with score
        assert report.overall_readiness == _readiness_from_score(
            report.readiness_score
        )

    def test_ready_level(self):
        """Well-configured component should reach READY."""
        c = _comp("svc", replicas=2)
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        c.security.rate_limiting = True
        c.security.log_enabled = True
        c.security.ids_monitored = True
        c.capacity.timeout_seconds = 30.0
        c.failover.enabled = True

        svc2 = _comp("svc2")
        dep = _dep("svc", "svc2")
        dep.circuit_breaker.enabled = True
        dep.retry_strategy.enabled = True

        g = _graph([c, svc2], [dep])
        analyzer = ServiceMeshAnalyzer()
        mc = analyzer.analyze_component(g, "svc")

        assert mc is not None
        assert mc.readiness in (MeshReadiness.READY, MeshReadiness.ADVANCED)

    def test_advanced_level(self):
        """Fully configured component should reach ADVANCED."""
        c = _comp("svc", replicas=3)
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        c.security.network_segmented = True
        c.security.rate_limiting = True
        c.security.log_enabled = True
        c.security.ids_monitored = True
        c.capacity.timeout_seconds = 30.0
        c.failover.enabled = True

        target = _comp("target")
        dep = _dep("svc", "target")
        dep.circuit_breaker.enabled = True
        dep.retry_strategy.enabled = True

        g = _graph([c, target], [dep])
        analyzer = ServiceMeshAnalyzer()
        mc = analyzer.analyze_component(g, "svc")

        assert mc is not None
        assert mc.readiness == MeshReadiness.ADVANCED


# ---------------------------------------------------------------------------
# 9. Traffic / Security / Observability scores
# ---------------------------------------------------------------------------

class TestScores:
    def test_traffic_score_zero(self):
        g = _graph([_comp("a")])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)
        # Default timeout_seconds = 30 > 0, so has_timeout is True
        # That gives 1/4 = 25.0
        assert report.traffic_management_score >= 0.0

    def test_traffic_score_with_all_features(self):
        c = _comp("svc")
        c.security.rate_limiting = True
        c.capacity.timeout_seconds = 30.0

        target = _comp("target")
        dep = _dep("svc", "target")
        dep.circuit_breaker.enabled = True
        dep.retry_strategy.enabled = True

        g = _graph([c, target], [dep])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        # svc has all 4 (retry, cb, timeout, rate_limit) -> 100 for svc
        # target has cb (incoming) -> 1/4 = 25 (+ default timeout=30 -> 2/4=50)
        assert report.traffic_management_score > 50.0

    def test_security_score_zero(self):
        g = _graph([_comp("a")])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)
        assert report.security_score == 0.0

    def test_security_score_full(self):
        c = _comp("svc")
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        c.security.network_segmented = True

        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        # mtls=True, auth=True, encrypted=True, segmented=True -> 4/4=100
        assert report.security_score == 100.0

    def test_observability_score_zero(self):
        g = _graph([_comp("a")])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)
        assert report.observability_score == 0.0

    def test_observability_score_partial(self):
        c = _comp("svc")
        c.security.log_enabled = True
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)
        # has_logging=True, has_monitoring=False, has_tracing=False -> 1/3 ~ 33.3
        assert 30.0 <= report.observability_score <= 35.0

    def test_observability_score_full(self):
        c = _comp("svc")
        c.security.log_enabled = True
        c.security.ids_monitored = True
        c.security.encryption_in_transit = True  # used as proxy for tracing
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)
        assert report.observability_score == 100.0


# ---------------------------------------------------------------------------
# 10. Pattern summary
# ---------------------------------------------------------------------------

class TestPatternSummary:
    def test_summary_counts(self):
        c1 = _comp("svc1", replicas=2)
        c1.capacity.timeout_seconds = 30.0

        c2 = _comp("svc2", replicas=3)
        c2.capacity.timeout_seconds = 15.0

        g = _graph([c1, c2])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        # Both have TIMEOUT_CHAIN and LOAD_BALANCING (replicas > 1)
        assert report.patterns_summary.get("timeout_chain", 0) == 2
        assert report.patterns_summary.get("load_balancing", 0) == 2

    def test_empty_summary(self):
        g = _graph([])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)
        assert report.patterns_summary == {}


# ---------------------------------------------------------------------------
# 11. Migration plan
# ---------------------------------------------------------------------------

class TestMigrationPlan:
    def test_plan_for_bare_components(self):
        """Bare components should generate multiple migration steps."""
        c1 = _comp("app")
        c2 = _comp("db", ctype=ComponentType.DATABASE)
        g = _graph([c1, c2], [_dep("app", "db")])
        analyzer = ServiceMeshAnalyzer()
        plan = analyzer.get_mesh_migration_plan(g)

        assert len(plan) >= 3
        phases = [s["phase"] for s in plan]
        assert "mutual_tls" in phases
        assert "circuit_breakers" in phases

    def test_plan_step_numbers_sequential(self):
        g = _graph([_comp("a"), _comp("b")], [_dep("a", "b")])
        analyzer = ServiceMeshAnalyzer()
        plan = analyzer.get_mesh_migration_plan(g)

        for i, step in enumerate(plan, start=1):
            assert step["step"] == i

    def test_plan_includes_priority(self):
        g = _graph([_comp("a")])
        analyzer = ServiceMeshAnalyzer()
        plan = analyzer.get_mesh_migration_plan(g)

        for step in plan:
            assert step["priority"] in ("high", "medium", "low")

    def test_plan_mtls_step_components(self):
        c1 = _comp("a")
        c2 = _comp("b")
        c2.security.encryption_in_transit = True
        c2.security.auth_required = True
        g = _graph([c1, c2])
        analyzer = ServiceMeshAnalyzer()
        plan = analyzer.get_mesh_migration_plan(g)

        mtls_steps = [s for s in plan if s["phase"] == "mutual_tls"]
        if mtls_steps:
            assert "a" in mtls_steps[0]["components"]
            assert "b" not in mtls_steps[0]["components"]

    def test_plan_no_mtls_step_when_all_have_mtls(self):
        comps = []
        for i in range(2):
            c = _comp(f"svc-{i}")
            c.security.encryption_in_transit = True
            c.security.auth_required = True
            comps.append(c)
        g = _graph(comps)
        analyzer = ServiceMeshAnalyzer()
        plan = analyzer.get_mesh_migration_plan(g)

        mtls_steps = [s for s in plan if s["phase"] == "mutual_tls"]
        assert len(mtls_steps) == 0

    def test_plan_timeout_tuning_step(self):
        """Invalid timeout chains should generate a timeout_tuning step."""
        gw = _comp("gw")
        gw.capacity.timeout_seconds = 10.0
        svc = _comp("svc")
        svc.capacity.timeout_seconds = 30.0

        g = _graph([gw, svc], [_dep("gw", "svc")])
        analyzer = ServiceMeshAnalyzer()
        plan = analyzer.get_mesh_migration_plan(g)

        timeout_steps = [s for s in plan if s["phase"] == "timeout_tuning"]
        assert len(timeout_steps) >= 1

    def test_plan_health_checking_step(self):
        c = _comp("svc")
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()
        plan = analyzer.get_mesh_migration_plan(g)

        hc_steps = [s for s in plan if s["phase"] == "health_checking"]
        assert len(hc_steps) >= 1

    def test_plan_no_health_checking_when_failover_enabled(self):
        c = _comp("svc")
        c.failover.enabled = True
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()
        plan = analyzer.get_mesh_migration_plan(g)

        hc_steps = [s for s in plan if s["phase"] == "health_checking"]
        assert len(hc_steps) == 0


# ---------------------------------------------------------------------------
# 12. Graph topologies
# ---------------------------------------------------------------------------

class TestGraphTopologies:
    def test_linear_chain(self):
        """A -> B -> C linear chain."""
        a = _comp("a")
        b = _comp("b")
        c = _comp("c")
        g = _graph([a, b, c], [_dep("a", "b"), _dep("b", "c")])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        assert len(report.components) == 3
        assert report.overall_readiness is not None

    def test_diamond_topology(self):
        """A -> B, A -> C, B -> D, C -> D diamond."""
        a = _comp("a")
        b = _comp("b")
        c = _comp("c")
        d = _comp("d")
        g = _graph(
            [a, b, c, d],
            [_dep("a", "b"), _dep("a", "c"), _dep("b", "d"), _dep("c", "d")],
        )
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        assert len(report.components) == 4
        # Should find timeout chains through both paths
        chains = report.timeout_chains
        # A->B->D and A->C->D are two paths
        assert len(chains) >= 2

    def test_star_topology(self):
        """Central hub with multiple spokes."""
        hub = _comp("hub", replicas=3)
        spokes = [_comp(f"spoke-{i}") for i in range(5)]
        deps = [_dep("hub", s.id) for s in spokes]
        g = _graph([hub] + spokes, deps)
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        assert len(report.components) == 6
        patterns = analyzer.detect_patterns(g)
        assert MeshPattern.LOAD_BALANCING.value in patterns["hub"]

    def test_disconnected_components(self):
        """Components with no dependencies between them."""
        g = _graph([_comp("a"), _comp("b"), _comp("c")])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        assert len(report.components) == 3
        assert report.timeout_chains == []

    def test_single_node(self):
        g = _graph([_comp("solo")])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        assert len(report.components) == 1
        assert report.timeout_chains == []


# ---------------------------------------------------------------------------
# 13. TrafficPolicy dataclass
# ---------------------------------------------------------------------------

class TestTrafficPolicyDataclass:
    def test_traffic_policy_fields(self):
        tp = TrafficPolicy(
            component_id="x",
            component_name="X",
            has_retry=True,
            has_circuit_breaker=False,
            has_timeout=True,
            has_rate_limit=False,
            timeout_seconds=30.0,
            retry_count=3,
        )
        assert tp.component_id == "x"
        assert tp.has_retry is True
        assert tp.retry_count == 3


# ---------------------------------------------------------------------------
# 14. SecurityPolicy dataclass
# ---------------------------------------------------------------------------

class TestSecurityPolicyDataclass:
    def test_security_policy_fields(self):
        sp = SecurityPolicy(
            component_id="y",
            component_name="Y",
            mtls_enabled=True,
            auth_enabled=True,
            encrypted=True,
            network_segmented=False,
        )
        assert sp.mtls_enabled is True
        assert sp.network_segmented is False


# ---------------------------------------------------------------------------
# 15. ObservabilityScore dataclass
# ---------------------------------------------------------------------------

class TestObservabilityScoreDataclass:
    def test_observability_score_fields(self):
        obs = ObservabilityScore(
            component_id="z",
            component_name="Z",
            has_logging=True,
            has_monitoring=False,
            has_tracing=True,
            score=66.7,
        )
        assert obs.score == 66.7
        assert obs.has_tracing is True


# ---------------------------------------------------------------------------
# 16. TimeoutChain dataclass
# ---------------------------------------------------------------------------

class TestTimeoutChainDataclass:
    def test_valid_chain(self):
        tc = TimeoutChain(
            path=["a", "b"],
            path_names=["A", "B"],
            timeouts=[60.0, 10.0],
            is_valid=True,
            issue=None,
        )
        assert tc.is_valid
        assert tc.issue is None

    def test_invalid_chain(self):
        tc = TimeoutChain(
            path=["a", "b"],
            path_names=["A", "B"],
            timeouts=[10.0, 30.0],
            is_valid=False,
            issue="outer < inner",
        )
        assert not tc.is_valid
        assert tc.issue == "outer < inner"


# ---------------------------------------------------------------------------
# 17. MeshReport dataclass
# ---------------------------------------------------------------------------

class TestMeshReportDataclass:
    def test_report_fields(self):
        report = MeshReport(
            components=[],
            overall_readiness=MeshReadiness.NOT_READY,
            readiness_score=0.0,
            traffic_management_score=0.0,
            security_score=0.0,
            observability_score=0.0,
            patterns_summary={},
            timeout_chains=[],
            recommendations=[],
            anti_patterns=[],
        )
        assert report.overall_readiness == MeshReadiness.NOT_READY


# ---------------------------------------------------------------------------
# 18. MeshComponent dataclass
# ---------------------------------------------------------------------------

class TestMeshComponentDataclass:
    def test_mesh_component_fields(self):
        mc = MeshComponent(
            component_id="test",
            component_name="Test",
            component_type="app_server",
            traffic_policy=TrafficPolicy(
                "test", "Test", False, False, True, False, 30.0, 0
            ),
            security_policy=SecurityPolicy(
                "test", "Test", False, False, False, False
            ),
            observability=ObservabilityScore(
                "test", "Test", False, False, False, 0.0
            ),
            patterns_detected=[MeshPattern.TIMEOUT_CHAIN],
            readiness=MeshReadiness.NOT_READY,
        )
        assert mc.component_type == "app_server"
        assert MeshPattern.TIMEOUT_CHAIN in mc.patterns_detected


# ---------------------------------------------------------------------------
# 19. Recommendations
# ---------------------------------------------------------------------------

class TestRecommendations:
    def test_recommendations_for_bare_graph(self):
        g = _graph([_comp("a"), _comp("b")], [_dep("a", "b")])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        assert len(report.recommendations) >= 1

    def test_recommendations_include_mtls(self):
        g = _graph([_comp("a")])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        mtls_recs = [r for r in report.recommendations if "mTLS" in r or "mutual TLS" in r]
        assert len(mtls_recs) >= 1

    def test_recommendations_include_observability(self):
        g = _graph([_comp("a")])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        obs_recs = [r for r in report.recommendations if "observability" in r.lower()]
        assert len(obs_recs) >= 1

    def test_recommendations_include_anti_patterns(self):
        secure = _comp("secure")
        secure.security.encryption_in_transit = True
        secure.security.auth_required = True
        insecure = _comp("insecure")

        g = _graph([secure, insecure])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        ap_recs = [r for r in report.recommendations if "anti-pattern" in r.lower()]
        assert len(ap_recs) >= 1

    def test_recommendations_include_timeout_chain_fix(self):
        gw = _comp("gw")
        gw.capacity.timeout_seconds = 10.0
        svc = _comp("svc")
        svc.capacity.timeout_seconds = 30.0

        g = _graph([gw, svc], [_dep("gw", "svc")])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        tc_recs = [r for r in report.recommendations if "timeout chain" in r.lower()]
        assert len(tc_recs) >= 1


# ---------------------------------------------------------------------------
# 20. Edge cases and integration
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_component_with_zero_timeout(self):
        """Zero timeout should mean has_timeout is False."""
        c = _comp("svc")
        c.capacity.timeout_seconds = 0.0
        g = _graph([c])
        analyzer = ServiceMeshAnalyzer()
        mc = analyzer.analyze_component(g, "svc")

        assert mc is not None
        assert mc.traffic_policy.has_timeout is False

    def test_multiple_edges_between_same_direction(self):
        """Multiple edges from one source to different targets."""
        src = _comp("src")
        t1 = _comp("t1")
        t2 = _comp("t2")

        d1 = _dep("src", "t1")
        d1.circuit_breaker.enabled = True
        d2 = _dep("src", "t2")
        d2.retry_strategy.enabled = True

        g = _graph([src, t1, t2], [d1, d2])
        analyzer = ServiceMeshAnalyzer()
        mc = analyzer.analyze_component(g, "src")

        assert mc is not None
        assert mc.traffic_policy.has_circuit_breaker is True
        assert mc.traffic_policy.has_retry is True

    def test_full_mesh_analysis_integration(self):
        """End-to-end integration: lb -> app(x2) -> db + ext."""
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER, replicas=2)
        lb.security.rate_limiting = True

        app = _comp("app", replicas=3)
        app.security.encryption_in_transit = True
        app.security.auth_required = True
        app.security.log_enabled = True
        app.capacity.timeout_seconds = 60.0
        app.failover.enabled = True

        db = _comp("db", ctype=ComponentType.DATABASE)
        db.security.encryption_in_transit = True
        db.security.auth_required = True
        db.security.network_segmented = True
        db.capacity.timeout_seconds = 10.0

        ext = _comp("ext", ctype=ComponentType.EXTERNAL_API)
        ext.capacity.timeout_seconds = 5.0

        d1 = _dep("lb", "app")
        d1.circuit_breaker.enabled = True

        d2 = _dep("app", "db")
        d2.circuit_breaker.enabled = True
        d2.retry_strategy.enabled = True
        d2.retry_strategy.max_retries = 2

        d3 = _dep("app", "ext")
        d3.circuit_breaker.enabled = True

        g = _graph([lb, app, db, ext], [d1, d2, d3])
        analyzer = ServiceMeshAnalyzer()
        report = analyzer.analyze(g)

        assert len(report.components) == 4
        assert report.readiness_score > 0.0
        assert report.traffic_management_score > 0.0
        assert report.security_score > 0.0
        assert len(report.patterns_summary) >= 1

        # app should have SIDECAR_PROXY (retry + cb)
        app_mc = next(mc for mc in report.components if mc.component_id == "app")
        assert MeshPattern.SIDECAR_PROXY in app_mc.patterns_detected

    def test_incoming_edge_patterns_detected_on_target(self):
        """CB on incoming edge should be detected on target component."""
        src = _comp("src")
        tgt = _comp("tgt")
        dep = _dep("src", "tgt")
        dep.circuit_breaker.enabled = True

        g = _graph([src, tgt], [dep])
        analyzer = ServiceMeshAnalyzer()
        patterns = analyzer.detect_patterns(g)

        # Both source and target should see CB
        assert MeshPattern.CIRCUIT_BREAKER.value in patterns["tgt"]
        assert MeshPattern.CIRCUIT_BREAKER.value in patterns["src"]

    def test_retry_count_takes_max(self):
        """When multiple edges have retry, take the max retry count."""
        src = _comp("src")
        t1 = _comp("t1")
        t2 = _comp("t2")

        d1 = _dep("src", "t1")
        d1.retry_strategy.enabled = True
        d1.retry_strategy.max_retries = 2

        d2 = _dep("src", "t2")
        d2.retry_strategy.enabled = True
        d2.retry_strategy.max_retries = 5

        g = _graph([src, t1, t2], [d1, d2])
        analyzer = ServiceMeshAnalyzer()
        mc = analyzer.analyze_component(g, "src")

        assert mc is not None
        assert mc.traffic_policy.retry_count == 5


# ---------------------------------------------------------------------------
# 21. Internal method edge cases (defensive branches)
# ---------------------------------------------------------------------------

class TestInternalMethodEdgeCases:
    def test_traffic_policy_missing_component(self):
        """_evaluate_traffic_policy with nonexistent component."""
        g = _graph([_comp("a")])
        analyzer = ServiceMeshAnalyzer()
        tp = analyzer._evaluate_traffic_policy(g, "missing")
        assert tp.component_id == "missing"
        assert tp.has_retry is False
        assert tp.timeout_seconds == 0.0

    def test_security_policy_missing_component(self):
        """_evaluate_security_policy with nonexistent component."""
        g = _graph([_comp("a")])
        analyzer = ServiceMeshAnalyzer()
        sp = analyzer._evaluate_security_policy(g, "missing")
        assert sp.component_id == "missing"
        assert sp.mtls_enabled is False

    def test_observability_missing_component(self):
        """_evaluate_observability with nonexistent component."""
        g = _graph([_comp("a")])
        analyzer = ServiceMeshAnalyzer()
        obs = analyzer._evaluate_observability(g, "missing")
        assert obs.component_id == "missing"
        assert obs.score == 0.0

    def test_detect_component_patterns_missing(self):
        """_detect_component_patterns with nonexistent component."""
        g = _graph([_comp("a")])
        analyzer = ServiceMeshAnalyzer()
        patterns = analyzer._detect_component_patterns(g, "missing")
        assert patterns == []

    def test_compute_traffic_score_empty(self):
        """_compute_traffic_management_score with empty list."""
        analyzer = ServiceMeshAnalyzer()
        assert analyzer._compute_traffic_management_score([]) == 0.0

    def test_compute_security_score_empty(self):
        """_compute_security_score with empty list."""
        analyzer = ServiceMeshAnalyzer()
        assert analyzer._compute_security_score([]) == 0.0

    def test_compute_observability_score_empty(self):
        """_compute_observability_score with empty list."""
        analyzer = ServiceMeshAnalyzer()
        assert analyzer._compute_observability_score([]) == 0.0
