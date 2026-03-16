"""Tests for API Gateway Resilience Analyzer.

Covers all gateway types, routing resilience (path/header/weight-based),
auth failure handling, rate limiting / throttling, transformation error
handling, gateway HA (active-passive, active-active), TLS termination,
WebSocket/SSE long-connection handling, buffering/timeout, circuit
breaker integration, canary routing validation, caching strategy &
invalidation, and the full assessment pipeline.
"""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.api_gateway_resilience import (
    APIGatewayResilienceAnalyzer,
    AuthMethod,
    AuthResilienceReport,
    BufferingConfig,
    BufferingTimeoutReport,
    CacheInvalidation,
    CacheReport,
    CacheStrategy,
    CanaryConfig,
    CanaryReport,
    CircuitBreakerConfig,
    CircuitBreakerReport,
    GatewayCacheConfig,
    GatewayConfig,
    GatewayResilienceReport,
    GatewayType,
    HAMode,
    HAReport,
    LongConnectionReport,
    RateLimitConfig,
    RateLimitReport,
    RoutingResilienceReport,
    RoutingRule,
    RoutingStrategy,
    TLSReport,
    TLSTermination,
    TransformationReport,
    _CERT_EXPIRY_THRESHOLDS,
    _GATEWAY_BASE_LATENCY_MS,
    _GATEWAY_MAX_RPS,
    _HA_FAILOVER_TIME_S,
    _TLS_OVERHEAD_MS,
    _clamp,
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


def _engine() -> APIGatewayResilienceAnalyzer:
    return APIGatewayResilienceAnalyzer()


def _full_config(**overrides: object) -> GatewayConfig:
    """Create a well-configured gateway config."""
    defaults: dict = dict(
        gateway_type=GatewayType.ENVOY,
        ha_mode=HAMode.ACTIVE_ACTIVE,
        routing_rules=[
            RoutingRule(
                path_pattern="/api",
                strategy=RoutingStrategy.PATH_BASED,
                target_service="app1",
                retry_count=3,
            ),
        ],
        auth_method=AuthMethod.JWT,
        rate_limit=RateLimitConfig(requests_per_second=5000, burst_size=100, per_client=True),
        circuit_breaker=CircuitBreakerConfig(enabled=True, failure_threshold=5),
        tls_termination=TLSTermination.EDGE,
        tls_cert_expiry_days=200,
        websocket_support=False,
        sse_support=False,
        canary=CanaryConfig(
            enabled=True,
            canary_weight=10.0,
            canary_service="app-canary",
            stable_service="app-stable",
            auto_rollback=True,
        ),
        cache=GatewayCacheConfig(
            strategy=CacheStrategy.STALE_IF_ERROR,
            ttl_seconds=300,
            max_size_mb=512,
            invalidation=CacheInvalidation.EVENT_DRIVEN,
        ),
        buffering=BufferingConfig(),
        global_timeout_ms=15000.0,
        upstream_services=["app1", "app2"],
        health_check_path="/health",
    )
    defaults.update(overrides)
    return GatewayConfig(**defaults)


def _minimal_config(**overrides: object) -> GatewayConfig:
    """Create a minimal / weak gateway config."""
    defaults: dict = dict(
        gateway_type=GatewayType.NGINX,
        ha_mode=HAMode.STANDALONE,
        routing_rules=[],
        auth_method=AuthMethod.NONE,
        rate_limit=RateLimitConfig(requests_per_second=50, burst_size=10),
        circuit_breaker=CircuitBreakerConfig(enabled=False),
        tls_termination=TLSTermination.NONE,
        tls_cert_expiry_days=5,
        websocket_support=False,
        sse_support=False,
        canary=CanaryConfig(enabled=False),
        cache=GatewayCacheConfig(strategy=CacheStrategy.NO_CACHE),
        buffering=BufferingConfig(request_buffering=False, response_buffering=False),
        global_timeout_ms=90000.0,
        upstream_services=[],
        health_check_path="",
    )
    defaults.update(overrides)
    return GatewayConfig(**defaults)


def _sample_graph() -> InfraGraph:
    """Graph with LB + 2 app servers + DB."""
    lb = Component(id="lb", name="lb", type=ComponentType.LOAD_BALANCER, replicas=2)
    app1 = _comp("app1")
    app2 = _comp("app2")
    db = _comp("db", ComponentType.DATABASE)
    g = _graph(lb, app1, app2, db)
    g.add_dependency(Dependency(source_id="lb", target_id="app1"))
    g.add_dependency(Dependency(source_id="lb", target_id="app2"))
    g.add_dependency(Dependency(source_id="app1", target_id="db"))
    g.add_dependency(Dependency(source_id="app2", target_id="db"))
    return g


# ===========================================================================
# 1. Enum completeness
# ===========================================================================


class TestGatewayTypeEnum:
    def test_all_values(self):
        expected = {"kong", "aws_api_gateway", "envoy", "nginx", "traefik", "haproxy"}
        assert {gt.value for gt in GatewayType} == expected

    def test_count(self):
        assert len(GatewayType) == 6

    @pytest.mark.parametrize("gt", list(GatewayType))
    def test_is_str(self, gt: GatewayType):
        assert isinstance(gt.value, str)


class TestRoutingStrategyEnum:
    def test_values(self):
        expected = {"path_based", "header_based", "weight_based"}
        assert {rs.value for rs in RoutingStrategy} == expected


class TestAuthMethodEnum:
    def test_values(self):
        expected = {"api_key", "jwt", "oauth2", "mtls", "basic", "none"}
        assert {a.value for a in AuthMethod} == expected


class TestHAModeEnum:
    def test_values(self):
        expected = {"active_passive", "active_active", "standalone"}
        assert {h.value for h in HAMode} == expected


class TestTLSTerminationEnum:
    def test_values(self):
        expected = {"edge", "passthrough", "re_encrypt", "none"}
        assert {t.value for t in TLSTermination} == expected


class TestCacheStrategyEnum:
    def test_values(self):
        expected = {"no_cache", "ttl_based", "stale_while_revalidate", "stale_if_error"}
        assert {cs.value for cs in CacheStrategy} == expected


class TestCacheInvalidationEnum:
    def test_values(self):
        expected = {"ttl_expiry", "purge_api", "tag_based", "event_driven", "none"}
        assert {ci.value for ci in CacheInvalidation} == expected


# ===========================================================================
# 2. Constants & helpers
# ===========================================================================


class TestConstants:
    @pytest.mark.parametrize("gt", list(GatewayType))
    def test_base_latency_defined(self, gt: GatewayType):
        assert gt in _GATEWAY_BASE_LATENCY_MS
        assert _GATEWAY_BASE_LATENCY_MS[gt] > 0

    @pytest.mark.parametrize("gt", list(GatewayType))
    def test_max_rps_defined(self, gt: GatewayType):
        assert gt in _GATEWAY_MAX_RPS
        assert _GATEWAY_MAX_RPS[gt] > 0

    @pytest.mark.parametrize("ha", list(HAMode))
    def test_ha_failover_defined(self, ha: HAMode):
        assert ha in _HA_FAILOVER_TIME_S

    @pytest.mark.parametrize("tls", list(TLSTermination))
    def test_tls_overhead_defined(self, tls: TLSTermination):
        assert tls in _TLS_OVERHEAD_MS

    def test_cert_expiry_thresholds_ordered(self):
        days = [t[0] for t in _CERT_EXPIRY_THRESHOLDS]
        assert days == sorted(days)


class TestClamp:
    def test_clamp_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_clamp_below(self):
        assert _clamp(-10.0) == 0.0

    def test_clamp_above(self):
        assert _clamp(200.0) == 100.0

    def test_clamp_custom_range(self):
        assert _clamp(5.0, 10.0, 20.0) == 10.0
        assert _clamp(25.0, 10.0, 20.0) == 20.0


# ===========================================================================
# 3. Data model construction
# ===========================================================================


class TestDataModels:
    def test_routing_rule_defaults(self):
        r = RoutingRule()
        assert r.path_pattern == "/"
        assert r.strategy == RoutingStrategy.PATH_BASED
        assert r.weight == 100.0
        assert r.retry_count == 2

    def test_rate_limit_config_defaults(self):
        rl = RateLimitConfig()
        assert rl.requests_per_second == 1000
        assert rl.burst_size == 100
        assert rl.per_client is False
        assert rl.response_code_on_exceed == 429

    def test_circuit_breaker_config_defaults(self):
        cb = CircuitBreakerConfig()
        assert cb.enabled is False
        assert cb.failure_threshold == 5
        assert cb.monitored_error_codes == [502, 503, 504]

    def test_canary_config_defaults(self):
        c = CanaryConfig()
        assert c.enabled is False
        assert c.canary_weight == 10.0
        assert c.auto_rollback is True

    def test_gateway_cache_config_defaults(self):
        gc = GatewayCacheConfig()
        assert gc.strategy == CacheStrategy.NO_CACHE
        assert gc.ttl_seconds == 300
        assert gc.invalidation == CacheInvalidation.NONE

    def test_buffering_config_defaults(self):
        b = BufferingConfig()
        assert b.request_buffering is True
        assert b.response_buffering is True
        assert b.max_request_body_bytes == 1_048_576

    def test_gateway_config_defaults(self):
        g = GatewayConfig()
        assert g.gateway_type == GatewayType.NGINX
        assert g.ha_mode == HAMode.STANDALONE
        assert g.auth_method == AuthMethod.NONE
        assert g.global_timeout_ms == 30000.0

    def test_full_config_helper(self):
        cfg = _full_config()
        assert cfg.gateway_type == GatewayType.ENVOY
        assert cfg.ha_mode == HAMode.ACTIVE_ACTIVE
        assert len(cfg.routing_rules) == 1

    def test_minimal_config_helper(self):
        cfg = _minimal_config()
        assert cfg.gateway_type == GatewayType.NGINX
        assert cfg.ha_mode == HAMode.STANDALONE
        assert len(cfg.routing_rules) == 0


# ===========================================================================
# 4. Routing resilience analysis
# ===========================================================================


class TestRoutingResilience:
    def test_no_rules(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _minimal_config()
        report = e.analyze_routing(g, cfg)
        assert report.total_rules == 0
        assert report.score < 100.0
        assert any("No routing rules" in r for r in report.recommendations)

    def test_path_based_rules(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(routing_rules=[
            RoutingRule(path_pattern="/api", strategy=RoutingStrategy.PATH_BASED,
                        target_service="app1", retry_count=3),
            RoutingRule(path_pattern="/web", strategy=RoutingStrategy.PATH_BASED,
                        target_service="app1", retry_count=2),
        ])
        report = e.analyze_routing(g, cfg)
        assert report.total_rules == 2
        assert report.path_based_count == 2
        assert report.header_based_count == 0

    def test_missing_retries_penalised(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(routing_rules=[
            RoutingRule(path_pattern="/no-retry", retry_count=0, target_service="app1"),
        ])
        report = e.analyze_routing(g, cfg)
        assert "/no-retry" in report.missing_retry_rules
        assert report.score < 100.0

    def test_high_timeout_penalised(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(routing_rules=[
            RoutingRule(path_pattern="/slow", timeout_ms=120_000, target_service="app1"),
        ])
        report = e.analyze_routing(g, cfg)
        assert "/slow" in report.high_timeout_rules

    def test_weight_based_wrong_total(self):
        e = _engine()
        g = _graph(_comp("app1"), _comp("app2"))
        cfg = _full_config(routing_rules=[
            RoutingRule(strategy=RoutingStrategy.WEIGHT_BASED, weight=30.0, target_service="app1"),
            RoutingRule(strategy=RoutingStrategy.WEIGHT_BASED, weight=30.0, target_service="app2"),
        ])
        report = e.analyze_routing(g, cfg)
        assert report.weight_based_count == 2
        assert any("weights sum" in r for r in report.recommendations)

    def test_weight_based_correct_total(self):
        e = _engine()
        g = _graph(_comp("app1"), _comp("app2"))
        cfg = _full_config(routing_rules=[
            RoutingRule(strategy=RoutingStrategy.WEIGHT_BASED, weight=60.0, target_service="app1"),
            RoutingRule(strategy=RoutingStrategy.WEIGHT_BASED, weight=40.0, target_service="app2"),
        ])
        report = e.analyze_routing(g, cfg)
        assert not any("weights sum" in r for r in report.recommendations)

    def test_target_not_in_graph(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(routing_rules=[
            RoutingRule(target_service="nonexistent", retry_count=2),
        ])
        report = e.analyze_routing(g, cfg)
        assert any("nonexistent" in r for r in report.recommendations)

    def test_header_based_counting(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(routing_rules=[
            RoutingRule(strategy=RoutingStrategy.HEADER_BASED, header_match={"X-V": "2"},
                        target_service="app1"),
        ])
        report = e.analyze_routing(g, cfg)
        assert report.header_based_count == 1


# ===========================================================================
# 5. Auth resilience
# ===========================================================================


class TestAuthResilience:
    def test_no_auth(self):
        e = _engine()
        cfg = _minimal_config()
        report = e.analyze_auth_resilience(cfg)
        assert report.has_auth is False
        assert report.score == 0.0
        assert any("unprotected" in r for r in report.recommendations)

    def test_mtls_highest_score(self):
        e = _engine()
        cfg = _full_config(auth_method=AuthMethod.MTLS)
        report = e.analyze_auth_resilience(cfg)
        assert report.has_auth is True
        assert report.score >= 70.0

    def test_basic_low_score(self):
        e = _engine()
        cfg = _full_config(auth_method=AuthMethod.BASIC)
        report = e.analyze_auth_resilience(cfg)
        assert report.score < 70.0
        assert any("Basic auth" in r for r in report.recommendations)

    def test_api_key_recommendation(self):
        e = _engine()
        cfg = _full_config(auth_method=AuthMethod.API_KEY)
        report = e.analyze_auth_resilience(cfg)
        assert any("API key" in r for r in report.recommendations)

    def test_jwt_with_tls_scores_well(self):
        e = _engine()
        cfg = _full_config(auth_method=AuthMethod.JWT, tls_termination=TLSTermination.EDGE)
        report = e.analyze_auth_resilience(cfg)
        assert report.fallback_configured is True
        assert report.token_refresh_strategy is True
        assert report.score >= 60.0

    def test_jwt_without_cb_warns(self):
        e = _engine()
        cfg = _full_config(
            auth_method=AuthMethod.JWT,
            circuit_breaker=CircuitBreakerConfig(enabled=False),
        )
        report = e.analyze_auth_resilience(cfg)
        assert any("circuit breaker" in r.lower() for r in report.recommendations)

    def test_no_tls_warns(self):
        e = _engine()
        cfg = _full_config(auth_method=AuthMethod.OAUTH2, tls_termination=TLSTermination.NONE)
        report = e.analyze_auth_resilience(cfg)
        assert any("cleartext" in r for r in report.recommendations)


# ===========================================================================
# 6. Rate limiting
# ===========================================================================


class TestRateLimiting:
    def test_low_rps(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(
            rate_limit=RateLimitConfig(requests_per_second=50, burst_size=10),
            upstream_services=["app1"],
        )
        report = e.analyze_rate_limiting(g, cfg)
        assert report.configured_rps == 50
        assert report.saturation_risk == "low"

    def test_high_rps_per_upstream(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(
            rate_limit=RateLimitConfig(requests_per_second=50_000, burst_size=100),
            upstream_services=["app1"],
        )
        report = e.analyze_rate_limiting(g, cfg)
        assert report.saturation_risk == "critical"

    def test_zero_rps_warned(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(
            rate_limit=RateLimitConfig(requests_per_second=0, burst_size=0),
        )
        report = e.analyze_rate_limiting(g, cfg)
        assert any("0 RPS" in r for r in report.recommendations)

    def test_exceeds_gateway_max(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(
            gateway_type=GatewayType.AWS_API_GATEWAY,
            rate_limit=RateLimitConfig(requests_per_second=20_000),
            upstream_services=["app1"],
        )
        report = e.analyze_rate_limiting(g, cfg)
        assert any("exceeds gateway capacity" in r for r in report.recommendations)

    def test_burst_exceeds_sustained(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(
            rate_limit=RateLimitConfig(requests_per_second=100, burst_size=500),
        )
        report = e.analyze_rate_limiting(g, cfg)
        assert any("Burst size exceeds" in r for r in report.recommendations)

    def test_not_per_client_warned(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(
            rate_limit=RateLimitConfig(requests_per_second=1000, per_client=False),
        )
        report = e.analyze_rate_limiting(g, cfg)
        assert any("not per-client" in r for r in report.recommendations)

    def test_per_client_no_warning(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(
            rate_limit=RateLimitConfig(requests_per_second=1000, per_client=True),
        )
        report = e.analyze_rate_limiting(g, cfg)
        assert not any("not per-client" in r for r in report.recommendations)

    def test_headroom_calculation(self):
        e = _engine()
        g = _graph(_comp("app1"))
        # Envoy max = 100_000
        cfg = _full_config(
            gateway_type=GatewayType.ENVOY,
            rate_limit=RateLimitConfig(requests_per_second=50_000),
        )
        report = e.analyze_rate_limiting(g, cfg)
        assert report.headroom_percent == 50.0


# ===========================================================================
# 7. Transformation error handling
# ===========================================================================


class TestTransformation:
    def test_both_buffering_enabled(self):
        e = _engine()
        cfg = _full_config()
        report = e.analyze_transformation(cfg)
        assert report.has_request_transform is True
        assert report.has_response_transform is True
        assert report.error_handling_score >= 60.0

    def test_no_buffering(self):
        e = _engine()
        cfg = _minimal_config()
        report = e.analyze_transformation(cfg)
        assert report.has_request_transform is False
        assert report.error_handling_score < 60.0

    def test_small_body_penalised(self):
        e = _engine()
        cfg = _full_config(buffering=BufferingConfig(max_request_body_bytes=512))
        report = e.analyze_transformation(cfg)
        assert any("very small" in r for r in report.recommendations)

    def test_large_body_warned(self):
        e = _engine()
        cfg = _full_config(buffering=BufferingConfig(max_request_body_bytes=100_000_000))
        report = e.analyze_transformation(cfg)
        assert any("50MB" in r for r in report.recommendations)

    def test_short_timeout_with_buffering(self):
        e = _engine()
        cfg = _full_config(global_timeout_ms=500.0)
        report = e.analyze_transformation(cfg)
        assert any("timeout" in r.lower() for r in report.recommendations)


# ===========================================================================
# 8. High Availability
# ===========================================================================


class TestHA:
    def test_standalone_low_score(self):
        e = _engine()
        g = _sample_graph()
        cfg = _minimal_config()
        report = e.analyze_ha(g, cfg)
        assert report.ha_mode == HAMode.STANDALONE
        assert report.spof_detected is True
        assert report.score < 30.0

    def test_active_passive_reasonable(self):
        e = _engine()
        g = _sample_graph()
        cfg = _full_config(ha_mode=HAMode.ACTIVE_PASSIVE, health_check_path="/health")
        report = e.analyze_ha(g, cfg)
        assert report.ha_mode == HAMode.ACTIVE_PASSIVE
        assert report.failover_time_seconds == _HA_FAILOVER_TIME_S[HAMode.ACTIVE_PASSIVE]
        assert report.score >= 40.0

    def test_active_active_high_score(self):
        e = _engine()
        g = _sample_graph()  # has LB with replicas=2
        cfg = _full_config(ha_mode=HAMode.ACTIVE_ACTIVE, health_check_path="/health")
        report = e.analyze_ha(g, cfg)
        assert report.score >= 70.0
        assert report.spof_detected is False

    def test_active_active_no_instances(self):
        e = _engine()
        g = _graph(_comp("app1"))  # no LB
        cfg = _full_config(ha_mode=HAMode.ACTIVE_ACTIVE)
        report = e.analyze_ha(g, cfg)
        assert report.spof_detected is True
        assert report.cluster_size == 0

    def test_no_health_check_penalised(self):
        e = _engine()
        g = _sample_graph()
        cfg = _full_config(ha_mode=HAMode.ACTIVE_ACTIVE, health_check_path="")
        report = e.analyze_ha(g, cfg)
        assert any("health check" in r.lower() for r in report.recommendations)

    def test_three_plus_instances_bonus(self):
        e = _engine()
        lb = Component(id="lb", name="lb", type=ComponentType.LOAD_BALANCER, replicas=3)
        g = _graph(lb)
        cfg = _full_config(ha_mode=HAMode.ACTIVE_ACTIVE, health_check_path="/health")
        report = e.analyze_ha(g, cfg)
        assert report.cluster_size == 3
        assert report.score == 100.0

    def test_active_passive_no_instances_spof(self):
        e = _engine()
        g = _graph(_comp("app1"))  # no LB
        cfg = _full_config(ha_mode=HAMode.ACTIVE_PASSIVE, health_check_path="/health")
        report = e.analyze_ha(g, cfg)
        assert report.spof_detected is True


# ===========================================================================
# 9. TLS termination & certificate management
# ===========================================================================


class TestTLS:
    def test_no_tls(self):
        e = _engine()
        cfg = _minimal_config()
        report = e.analyze_tls(cfg)
        assert report.termination_mode == TLSTermination.NONE
        assert report.score == 0.0
        assert any("cleartext" in r for r in report.recommendations)

    def test_edge_termination(self):
        e = _engine()
        cfg = _full_config(tls_termination=TLSTermination.EDGE, tls_cert_expiry_days=200)
        report = e.analyze_tls(cfg)
        assert report.overhead_ms == _TLS_OVERHEAD_MS[TLSTermination.EDGE]
        assert report.cert_expiry_risk == "low"
        assert report.score > 60.0

    def test_re_encrypt_high_score(self):
        e = _engine()
        cfg = _full_config(tls_termination=TLSTermination.RE_ENCRYPT, tls_cert_expiry_days=200)
        report = e.analyze_tls(cfg)
        assert report.score > 80.0

    def test_passthrough_noted(self):
        e = _engine()
        cfg = _full_config(tls_termination=TLSTermination.PASSTHROUGH, tls_cert_expiry_days=200)
        report = e.analyze_tls(cfg)
        assert any("cannot inspect" in r for r in report.recommendations)

    def test_cert_critical(self):
        e = _engine()
        cfg = _full_config(tls_termination=TLSTermination.EDGE, tls_cert_expiry_days=3)
        report = e.analyze_tls(cfg)
        assert report.cert_expiry_risk == "critical"
        assert any("immediate renewal" in r for r in report.recommendations)

    def test_cert_high(self):
        e = _engine()
        cfg = _full_config(tls_termination=TLSTermination.EDGE, tls_cert_expiry_days=20)
        report = e.analyze_tls(cfg)
        assert report.cert_expiry_risk == "high"

    def test_cert_medium(self):
        e = _engine()
        cfg = _full_config(tls_termination=TLSTermination.EDGE, tls_cert_expiry_days=60)
        report = e.analyze_tls(cfg)
        assert report.cert_expiry_risk == "medium"

    def test_cert_low(self):
        e = _engine()
        cfg = _full_config(tls_termination=TLSTermination.EDGE, tls_cert_expiry_days=365)
        report = e.analyze_tls(cfg)
        assert report.cert_expiry_risk == "low"
        assert report.score > 70.0


# ===========================================================================
# 10. Long-lived connections (WebSocket / SSE)
# ===========================================================================


class TestLongConnections:
    def test_no_long_connections(self):
        e = _engine()
        cfg = _full_config(websocket_support=False, sse_support=False)
        report = e.analyze_long_connections(cfg)
        assert report.reconnect_risk == "none"
        assert report.score == 100.0

    def test_websocket_standalone_critical(self):
        e = _engine()
        cfg = _minimal_config(websocket_support=True)
        report = e.analyze_long_connections(cfg)
        assert report.reconnect_risk == "critical"
        assert report.score < 50.0

    def test_websocket_active_passive_high(self):
        e = _engine()
        cfg = _full_config(
            ha_mode=HAMode.ACTIVE_PASSIVE,
            websocket_support=True,
            global_timeout_ms=120_000.0,
        )
        report = e.analyze_long_connections(cfg)
        assert report.reconnect_risk == "high"

    def test_websocket_active_active_medium(self):
        e = _engine()
        cfg = _full_config(
            ha_mode=HAMode.ACTIVE_ACTIVE,
            websocket_support=True,
            global_timeout_ms=120_000.0,
        )
        report = e.analyze_long_connections(cfg)
        assert report.reconnect_risk == "medium"

    def test_websocket_short_timeout_risk(self):
        e = _engine()
        cfg = _full_config(
            websocket_support=True,
            global_timeout_ms=30_000.0,
        )
        report = e.analyze_long_connections(cfg)
        assert report.session_persistence_risk == "high"

    def test_sse_no_response_buffering(self):
        e = _engine()
        cfg = _full_config(
            sse_support=True,
            buffering=BufferingConfig(response_buffering=False),
        )
        report = e.analyze_long_connections(cfg)
        assert any("SSE" in r for r in report.recommendations)


# ===========================================================================
# 11. Buffering & timeout
# ===========================================================================


class TestBufferingTimeout:
    def test_optimal_config(self):
        e = _engine()
        cfg = _full_config(global_timeout_ms=15_000.0)
        report = e.analyze_buffering_timeout(cfg)
        assert report.timeout_risk == "low"
        assert report.score >= 80.0

    def test_extreme_timeout(self):
        e = _engine()
        cfg = _full_config(global_timeout_ms=200_000.0)
        report = e.analyze_buffering_timeout(cfg)
        assert report.timeout_risk == "critical"
        assert report.score < 60.0

    def test_high_timeout(self):
        e = _engine()
        cfg = _full_config(global_timeout_ms=70_000.0)
        report = e.analyze_buffering_timeout(cfg)
        assert report.timeout_risk == "high"

    def test_medium_timeout(self):
        e = _engine()
        cfg = _full_config(global_timeout_ms=45_000.0)
        report = e.analyze_buffering_timeout(cfg)
        assert report.timeout_risk == "medium"

    def test_very_short_timeout(self):
        e = _engine()
        cfg = _full_config(global_timeout_ms=500.0)
        report = e.analyze_buffering_timeout(cfg)
        assert report.timeout_risk == "high"
        assert any("very short" in r for r in report.recommendations)

    def test_no_buffering_warned(self):
        e = _engine()
        cfg = _minimal_config()
        report = e.analyze_buffering_timeout(cfg)
        assert any("Request buffering" in r for r in report.recommendations)
        assert any("Response buffering" in r for r in report.recommendations)


# ===========================================================================
# 12. Circuit breaker
# ===========================================================================


class TestCircuitBreaker:
    def test_disabled(self):
        e = _engine()
        cfg = _minimal_config()
        report = e.analyze_circuit_breaker(cfg)
        assert report.enabled is False
        assert report.score == 0.0
        assert any("not enabled" in r for r in report.recommendations)

    def test_enabled_default(self):
        e = _engine()
        cfg = _full_config()
        report = e.analyze_circuit_breaker(cfg)
        assert report.enabled is True
        assert report.score > 50.0

    def test_low_threshold(self):
        e = _engine()
        cfg = _full_config(
            circuit_breaker=CircuitBreakerConfig(enabled=True, failure_threshold=2),
        )
        report = e.analyze_circuit_breaker(cfg)
        assert any("flapping" in r for r in report.recommendations)

    def test_high_threshold(self):
        e = _engine()
        cfg = _full_config(
            circuit_breaker=CircuitBreakerConfig(enabled=True, failure_threshold=20),
        )
        report = e.analyze_circuit_breaker(cfg)
        assert any("too slowly" in r for r in report.recommendations)

    def test_short_recovery(self):
        e = _engine()
        cfg = _full_config(
            circuit_breaker=CircuitBreakerConfig(
                enabled=True, recovery_timeout_seconds=5.0,
            ),
        )
        report = e.analyze_circuit_breaker(cfg)
        assert any("reclose too quickly" in r for r in report.recommendations)

    def test_long_recovery(self):
        e = _engine()
        cfg = _full_config(
            circuit_breaker=CircuitBreakerConfig(
                enabled=True, recovery_timeout_seconds=300.0,
            ),
        )
        report = e.analyze_circuit_breaker(cfg)
        assert any("isolated too long" in r for r in report.recommendations)

    def test_no_monitored_codes(self):
        e = _engine()
        cfg = _full_config(
            circuit_breaker=CircuitBreakerConfig(
                enabled=True, monitored_error_codes=[],
            ),
        )
        report = e.analyze_circuit_breaker(cfg)
        assert any("No error codes" in r for r in report.recommendations)

    def test_missing_503(self):
        e = _engine()
        cfg = _full_config(
            circuit_breaker=CircuitBreakerConfig(
                enabled=True, monitored_error_codes=[502, 504],
            ),
        )
        report = e.analyze_circuit_breaker(cfg)
        assert any("503" in r for r in report.recommendations)


# ===========================================================================
# 13. Canary routing validation
# ===========================================================================


class TestCanaryRouting:
    def test_disabled(self):
        e = _engine()
        cfg = _minimal_config()
        report = e.validate_canary(cfg)
        assert report.enabled is False
        assert report.score == 50.0

    def test_valid_canary(self):
        e = _engine()
        cfg = _full_config()
        report = e.validate_canary(cfg)
        assert report.enabled is True
        assert report.has_auto_rollback is True
        assert report.has_success_criteria is True
        assert report.score >= 70.0
        assert len(report.validation_errors) == 0

    def test_zero_weight_error(self):
        e = _engine()
        cfg = _full_config(canary=CanaryConfig(
            enabled=True, canary_weight=0.0,
            canary_service="c", stable_service="s",
        ))
        report = e.validate_canary(cfg)
        assert any("0%" in err for err in report.validation_errors)

    def test_high_weight_error(self):
        e = _engine()
        cfg = _full_config(canary=CanaryConfig(
            enabled=True, canary_weight=70.0,
            canary_service="c", stable_service="s",
        ))
        report = e.validate_canary(cfg)
        assert any("too high" in err for err in report.validation_errors)

    def test_same_service_error(self):
        e = _engine()
        cfg = _full_config(canary=CanaryConfig(
            enabled=True, canary_weight=10.0,
            canary_service="same", stable_service="same",
        ))
        report = e.validate_canary(cfg)
        assert any("same" in err.lower() for err in report.validation_errors)

    def test_no_canary_service(self):
        e = _engine()
        cfg = _full_config(canary=CanaryConfig(
            enabled=True, canary_weight=10.0,
            canary_service="", stable_service="s",
        ))
        report = e.validate_canary(cfg)
        assert any("No canary service" in err for err in report.validation_errors)

    def test_no_stable_service(self):
        e = _engine()
        cfg = _full_config(canary=CanaryConfig(
            enabled=True, canary_weight=10.0,
            canary_service="c", stable_service="",
        ))
        report = e.validate_canary(cfg)
        assert any("No stable service" in err for err in report.validation_errors)

    def test_no_auto_rollback_warned(self):
        e = _engine()
        cfg = _full_config(canary=CanaryConfig(
            enabled=True, canary_weight=10.0,
            canary_service="c", stable_service="s",
            auto_rollback=False,
        ))
        report = e.validate_canary(cfg)
        assert report.has_auto_rollback is False
        assert any("manual intervention" in r for r in report.recommendations)

    def test_no_success_criteria(self):
        e = _engine()
        cfg = _full_config(canary=CanaryConfig(
            enabled=True, canary_weight=10.0,
            canary_service="c", stable_service="s",
            success_threshold=0.0, error_threshold=0.0,
        ))
        report = e.validate_canary(cfg)
        assert report.has_success_criteria is False
        assert any("auto-evaluate" in r for r in report.recommendations)


# ===========================================================================
# 14. Caching strategy & invalidation
# ===========================================================================


class TestCaching:
    def test_no_cache(self):
        e = _engine()
        cfg = _minimal_config()
        report = e.analyze_caching(cfg)
        assert report.strategy == CacheStrategy.NO_CACHE
        assert report.score == 30.0
        assert any("No caching" in r for r in report.recommendations)

    def test_ttl_based_good(self):
        e = _engine()
        cfg = _full_config(cache=GatewayCacheConfig(
            strategy=CacheStrategy.TTL_BASED,
            ttl_seconds=120,
            max_size_mb=256,
            invalidation=CacheInvalidation.PURGE_API,
        ))
        report = e.analyze_caching(cfg)
        assert report.strategy == CacheStrategy.TTL_BASED
        assert report.stale_serving is False
        assert report.score > 50.0

    def test_stale_while_revalidate(self):
        e = _engine()
        cfg = _full_config(cache=GatewayCacheConfig(
            strategy=CacheStrategy.STALE_WHILE_REVALIDATE,
            ttl_seconds=300,
            max_size_mb=512,
            invalidation=CacheInvalidation.EVENT_DRIVEN,
        ))
        report = e.analyze_caching(cfg)
        assert report.stale_serving is True
        assert any("Stale serving enabled" in r for r in report.recommendations)

    def test_stale_if_error(self):
        e = _engine()
        cfg = _full_config(cache=GatewayCacheConfig(
            strategy=CacheStrategy.STALE_IF_ERROR,
            ttl_seconds=300,
            max_size_mb=512,
            invalidation=CacheInvalidation.TAG_BASED,
        ))
        report = e.analyze_caching(cfg)
        assert report.stale_serving is True

    def test_very_short_ttl(self):
        e = _engine()
        cfg = _full_config(cache=GatewayCacheConfig(
            strategy=CacheStrategy.TTL_BASED,
            ttl_seconds=5,
            invalidation=CacheInvalidation.TTL_EXPIRY,
        ))
        report = e.analyze_caching(cfg)
        assert any("short cache TTL" in r for r in report.recommendations)

    def test_very_long_ttl(self):
        e = _engine()
        cfg = _full_config(cache=GatewayCacheConfig(
            strategy=CacheStrategy.TTL_BASED,
            ttl_seconds=7200,
            invalidation=CacheInvalidation.TTL_EXPIRY,
        ))
        report = e.analyze_caching(cfg)
        assert any("Long cache TTL" in r for r in report.recommendations)

    def test_small_cache_warned(self):
        e = _engine()
        cfg = _full_config(cache=GatewayCacheConfig(
            strategy=CacheStrategy.TTL_BASED,
            ttl_seconds=300,
            max_size_mb=8,
            invalidation=CacheInvalidation.TTL_EXPIRY,
        ))
        report = e.analyze_caching(cfg)
        assert any("very small" in r for r in report.recommendations)

    def test_large_cache_noted(self):
        e = _engine()
        cfg = _full_config(cache=GatewayCacheConfig(
            strategy=CacheStrategy.TTL_BASED,
            ttl_seconds=300,
            max_size_mb=8192,
            invalidation=CacheInvalidation.TTL_EXPIRY,
        ))
        report = e.analyze_caching(cfg)
        assert any("4GB" in r for r in report.recommendations)

    def test_no_invalidation_penalised(self):
        e = _engine()
        cfg = _full_config(cache=GatewayCacheConfig(
            strategy=CacheStrategy.TTL_BASED,
            ttl_seconds=300,
            invalidation=CacheInvalidation.NONE,
        ))
        report = e.analyze_caching(cfg)
        assert any("No cache invalidation" in r for r in report.recommendations)

    def test_event_driven_invalidation_highest(self):
        e = _engine()
        cfg1 = _full_config(cache=GatewayCacheConfig(
            strategy=CacheStrategy.TTL_BASED,
            ttl_seconds=300,
            invalidation=CacheInvalidation.EVENT_DRIVEN,
        ))
        cfg2 = _full_config(cache=GatewayCacheConfig(
            strategy=CacheStrategy.TTL_BASED,
            ttl_seconds=300,
            invalidation=CacheInvalidation.TTL_EXPIRY,
        ))
        r1 = e.analyze_caching(cfg1)
        r2 = e.analyze_caching(cfg2)
        assert r1.score > r2.score


# ===========================================================================
# 15. Full assessment
# ===========================================================================


class TestFullAssessment:
    def test_full_config_high_score(self):
        e = _engine()
        g = _sample_graph()
        cfg = _full_config()
        report = e.assess(g, cfg)
        assert report.gateway_type == GatewayType.ENVOY
        assert report.overall_score > 40.0
        assert report.timestamp != ""
        assert isinstance(report.recommendations, list)

    def test_minimal_config_low_score(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _minimal_config()
        report = e.assess(g, cfg)
        assert report.overall_score < 40.0
        assert len(report.recommendations) > 0

    def test_full_report_contains_all_subreports(self):
        e = _engine()
        g = _sample_graph()
        cfg = _full_config()
        report = e.assess(g, cfg)
        assert isinstance(report.routing, RoutingResilienceReport)
        assert isinstance(report.auth, AuthResilienceReport)
        assert isinstance(report.rate_limit, RateLimitReport)
        assert isinstance(report.transformation, TransformationReport)
        assert isinstance(report.ha, HAReport)
        assert isinstance(report.tls, TLSReport)
        assert isinstance(report.long_connections, LongConnectionReport)
        assert isinstance(report.buffering_timeout, BufferingTimeoutReport)
        assert isinstance(report.circuit_breaker, CircuitBreakerReport)
        assert isinstance(report.canary, CanaryReport)
        assert isinstance(report.cache, CacheReport)

    def test_recommendations_deduplicated(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _minimal_config()
        report = e.assess(g, cfg)
        assert len(report.recommendations) == len(set(report.recommendations))

    def test_overall_score_clamped(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _minimal_config()
        report = e.assess(g, cfg)
        assert 0.0 <= report.overall_score <= 100.0

    def test_timestamp_is_utc_iso(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config()
        report = e.assess(g, cfg)
        assert "T" in report.timestamp
        assert "+" in report.timestamp or "Z" in report.timestamp


# ===========================================================================
# 16. Edge cases & integration
# ===========================================================================


class TestEdgeCases:
    def test_empty_graph(self):
        e = _engine()
        g = InfraGraph()
        cfg = _full_config()
        report = e.assess(g, cfg)
        assert 0.0 <= report.overall_score <= 100.0

    def test_all_gateway_types(self):
        e = _engine()
        g = _graph(_comp("app1"))
        for gt in GatewayType:
            cfg = _full_config(gateway_type=gt)
            report = e.assess(g, cfg)
            assert report.gateway_type == gt

    def test_graph_with_dependencies(self):
        e = _engine()
        g = _sample_graph()
        cfg = _full_config(upstream_services=["app1", "app2"])
        report = e.assess(g, cfg)
        assert report.overall_score > 0.0

    def test_large_number_of_routing_rules(self):
        e = _engine()
        g = _graph(_comp("app1"))
        rules = [
            RoutingRule(
                path_pattern=f"/api/v{i}",
                target_service="app1",
                retry_count=2,
            )
            for i in range(50)
        ]
        cfg = _full_config(routing_rules=rules)
        report = e.analyze_routing(g, cfg)
        assert report.total_rules == 50

    def test_dependency_model(self):
        d = Dependency(source_id="a1", target_id="b1")
        assert d.source_id == "a1"
        assert d.target_id == "b1"

    def test_comp_helper_defaults(self):
        c = _comp()
        assert c.id == "c1"
        assert c.type == ComponentType.APP_SERVER

    def test_graph_helper(self):
        c1 = _comp("a1")
        c2 = _comp("b1", ComponentType.DATABASE)
        g = _graph(c1, c2)
        assert len(g.components) == 2
        assert g.get_component("a1") is not None
        assert g.get_component("b1") is not None


# ===========================================================================
# 17. Report model validation
# ===========================================================================


class TestReportModels:
    def test_routing_report_defaults(self):
        r = RoutingResilienceReport()
        assert r.total_rules == 0
        assert r.score == 100.0

    def test_auth_report_defaults(self):
        r = AuthResilienceReport()
        assert r.auth_method == AuthMethod.NONE
        assert r.score == 0.0

    def test_ha_report_defaults(self):
        r = HAReport()
        assert r.ha_mode == HAMode.STANDALONE
        assert r.spof_detected is False

    def test_tls_report_defaults(self):
        r = TLSReport()
        assert r.termination_mode == TLSTermination.NONE
        assert r.score == 0.0

    def test_long_connection_report_defaults(self):
        r = LongConnectionReport()
        assert r.reconnect_risk == "none"

    def test_buffering_report_defaults(self):
        r = BufferingTimeoutReport()
        assert r.score == 50.0

    def test_cb_report_defaults(self):
        r = CircuitBreakerReport()
        assert r.enabled is False
        assert r.score == 0.0

    def test_canary_report_defaults(self):
        r = CanaryReport()
        assert r.enabled is False

    def test_cache_report_defaults(self):
        r = CacheReport()
        assert r.strategy == CacheStrategy.NO_CACHE

    def test_full_report_defaults(self):
        r = GatewayResilienceReport()
        assert r.overall_score == 0.0
        assert r.timestamp == ""


# ===========================================================================
# 18. Saturation risk levels
# ===========================================================================


class TestSaturationRiskLevels:
    def test_medium_saturation(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(
            rate_limit=RateLimitConfig(requests_per_second=3000),
            upstream_services=["app1"],
        )
        report = e.analyze_rate_limiting(g, cfg)
        assert report.saturation_risk == "medium"

    def test_high_saturation(self):
        e = _engine()
        g = _graph(_comp("app1"))
        cfg = _full_config(
            rate_limit=RateLimitConfig(requests_per_second=8000),
            upstream_services=["app1"],
        )
        report = e.analyze_rate_limiting(g, cfg)
        assert report.saturation_risk == "high"

    def test_low_saturation_with_many_upstreams(self):
        e = _engine()
        g = _graph(_comp("app1"), _comp("app2"), _comp("app3"), _comp("app4"))
        cfg = _full_config(
            rate_limit=RateLimitConfig(requests_per_second=2000),
            upstream_services=["app1", "app2", "app3", "app4"],
        )
        report = e.analyze_rate_limiting(g, cfg)
        assert report.saturation_risk == "low"
