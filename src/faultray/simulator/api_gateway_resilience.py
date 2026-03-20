# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""API Gateway Resilience Analyzer.

Analyzes API gateway configurations and their resilience characteristics.
Covers gateway types (Kong, AWS API Gateway, Envoy, Nginx, Traefik, HAProxy),
request routing resilience (path-based, header-based, weight-based),
authentication/authorization failure handling, rate limiting and throttling
configuration analysis, request/response transformation error handling,
gateway high availability (active-passive, active-active clustering),
TLS termination and certificate management, WebSocket/SSE long-connection
handling during failover, request buffering and timeout configuration,
gateway circuit breaker integration, canary routing configuration
validation, and gateway caching strategy and invalidation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GatewayType(str, Enum):
    """Supported API gateway implementations."""

    KONG = "kong"
    AWS_API_GATEWAY = "aws_api_gateway"
    ENVOY = "envoy"
    NGINX = "nginx"
    TRAEFIK = "traefik"
    HAPROXY = "haproxy"


class RoutingStrategy(str, Enum):
    """Request routing strategy."""

    PATH_BASED = "path_based"
    HEADER_BASED = "header_based"
    WEIGHT_BASED = "weight_based"


class AuthMethod(str, Enum):
    """Authentication/authorization method."""

    API_KEY = "api_key"
    JWT = "jwt"
    OAUTH2 = "oauth2"
    MTLS = "mtls"
    BASIC = "basic"
    NONE = "none"


class HAMode(str, Enum):
    """Gateway high availability mode."""

    ACTIVE_PASSIVE = "active_passive"
    ACTIVE_ACTIVE = "active_active"
    STANDALONE = "standalone"


class TLSTermination(str, Enum):
    """TLS termination mode."""

    EDGE = "edge"
    PASSTHROUGH = "passthrough"
    RE_ENCRYPT = "re_encrypt"
    NONE = "none"


class CacheStrategy(str, Enum):
    """Gateway caching strategy."""

    NO_CACHE = "no_cache"
    TTL_BASED = "ttl_based"
    STALE_WHILE_REVALIDATE = "stale_while_revalidate"
    STALE_IF_ERROR = "stale_if_error"


class CacheInvalidation(str, Enum):
    """Cache invalidation method."""

    TTL_EXPIRY = "ttl_expiry"
    PURGE_API = "purge_api"
    TAG_BASED = "tag_based"
    EVENT_DRIVEN = "event_driven"
    NONE = "none"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class RoutingRule(BaseModel):
    """A single routing rule for the gateway."""

    path_pattern: str = "/"
    strategy: RoutingStrategy = RoutingStrategy.PATH_BASED
    target_service: str = ""
    weight: float = Field(default=100.0, ge=0.0, le=100.0)
    header_match: dict[str, str] = Field(default_factory=dict)
    timeout_ms: float = Field(default=30000.0, ge=0.0)
    retry_count: int = Field(default=2, ge=0)


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""

    requests_per_second: int = Field(default=1000, ge=0)
    burst_size: int = Field(default=100, ge=0)
    per_client: bool = False
    throttle_on_exceed: bool = True
    response_code_on_exceed: int = Field(default=429, ge=100, le=599)


class CircuitBreakerConfig(BaseModel):
    """Gateway-level circuit breaker configuration."""

    enabled: bool = False
    failure_threshold: int = Field(default=5, ge=1)
    recovery_timeout_seconds: float = Field(default=30.0, ge=1.0)
    half_open_requests: int = Field(default=3, ge=1)
    monitored_error_codes: list[int] = Field(default_factory=lambda: [502, 503, 504])


class CanaryConfig(BaseModel):
    """Canary routing configuration."""

    enabled: bool = False
    canary_weight: float = Field(default=10.0, ge=0.0, le=100.0)
    canary_header: str = ""
    canary_service: str = ""
    stable_service: str = ""
    success_threshold: float = Field(default=95.0, ge=0.0, le=100.0)
    error_threshold: float = Field(default=5.0, ge=0.0, le=100.0)
    auto_rollback: bool = True


class GatewayCacheConfig(BaseModel):
    """Gateway caching configuration."""

    strategy: CacheStrategy = CacheStrategy.NO_CACHE
    ttl_seconds: int = Field(default=300, ge=0)
    max_size_mb: int = Field(default=256, ge=0)
    invalidation: CacheInvalidation = CacheInvalidation.NONE
    cache_key_headers: list[str] = Field(default_factory=list)
    cacheable_status_codes: list[int] = Field(default_factory=lambda: [200, 301])
    stale_ttl_seconds: int = Field(default=60, ge=0)


class BufferingConfig(BaseModel):
    """Request/response buffering configuration."""

    request_buffering: bool = True
    response_buffering: bool = True
    max_request_body_bytes: int = Field(default=1_048_576, ge=0)
    max_response_body_bytes: int = Field(default=10_485_760, ge=0)


class GatewayConfig(BaseModel):
    """Full API gateway configuration."""

    gateway_type: GatewayType = GatewayType.NGINX
    ha_mode: HAMode = HAMode.STANDALONE
    routing_rules: list[RoutingRule] = Field(default_factory=list)
    auth_method: AuthMethod = AuthMethod.NONE
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    tls_termination: TLSTermination = TLSTermination.NONE
    tls_cert_expiry_days: int = Field(default=365, ge=0)
    websocket_support: bool = False
    sse_support: bool = False
    canary: CanaryConfig = Field(default_factory=CanaryConfig)
    cache: GatewayCacheConfig = Field(default_factory=GatewayCacheConfig)
    buffering: BufferingConfig = Field(default_factory=BufferingConfig)
    global_timeout_ms: float = Field(default=30000.0, ge=0.0)
    upstream_services: list[str] = Field(default_factory=list)
    health_check_path: str = ""


# ---------------------------------------------------------------------------
# Report / result models
# ---------------------------------------------------------------------------


class RoutingResilienceReport(BaseModel):
    """Report on routing configuration resilience."""

    total_rules: int = 0
    path_based_count: int = 0
    header_based_count: int = 0
    weight_based_count: int = 0
    missing_retry_rules: list[str] = Field(default_factory=list)
    high_timeout_rules: list[str] = Field(default_factory=list)
    score: float = Field(default=100.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class AuthResilienceReport(BaseModel):
    """Report on auth failure handling resilience."""

    auth_method: AuthMethod = AuthMethod.NONE
    has_auth: bool = False
    fallback_configured: bool = False
    token_refresh_strategy: bool = False
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class RateLimitReport(BaseModel):
    """Report on rate limiting / throttling configuration."""

    configured_rps: int = 0
    burst_size: int = 0
    per_client: bool = False
    headroom_percent: float = Field(default=0.0)
    saturation_risk: str = "low"
    recommendations: list[str] = Field(default_factory=list)


class TransformationReport(BaseModel):
    """Report on request/response transformation error handling."""

    has_request_transform: bool = False
    has_response_transform: bool = False
    error_handling_score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class HAReport(BaseModel):
    """Report on gateway high availability."""

    ha_mode: HAMode = HAMode.STANDALONE
    failover_time_seconds: float = Field(default=0.0, ge=0.0)
    cluster_size: int = 0
    spof_detected: bool = False
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class TLSReport(BaseModel):
    """Report on TLS termination and certificate management."""

    termination_mode: TLSTermination = TLSTermination.NONE
    cert_expiry_days: int = 0
    cert_expiry_risk: str = "none"
    overhead_ms: float = Field(default=0.0, ge=0.0)
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class LongConnectionReport(BaseModel):
    """Report on WebSocket/SSE handling during failover."""

    websocket_support: bool = False
    sse_support: bool = False
    reconnect_risk: str = "none"
    session_persistence_risk: str = "none"
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class BufferingTimeoutReport(BaseModel):
    """Report on request buffering and timeout configuration."""

    request_buffering: bool = True
    response_buffering: bool = True
    global_timeout_ms: float = 0.0
    max_request_body_bytes: int = 0
    timeout_risk: str = "low"
    score: float = Field(default=50.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class CircuitBreakerReport(BaseModel):
    """Report on gateway circuit breaker integration."""

    enabled: bool = False
    failure_threshold: int = 0
    recovery_timeout_seconds: float = 0.0
    monitored_codes: list[int] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class CanaryReport(BaseModel):
    """Report on canary routing configuration validation."""

    enabled: bool = False
    canary_weight: float = 0.0
    has_auto_rollback: bool = False
    has_success_criteria: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class CacheReport(BaseModel):
    """Report on gateway caching strategy and invalidation."""

    strategy: CacheStrategy = CacheStrategy.NO_CACHE
    invalidation: CacheInvalidation = CacheInvalidation.NONE
    ttl_seconds: int = 0
    max_size_mb: int = 0
    stale_serving: bool = False
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class GatewayResilienceReport(BaseModel):
    """Full gateway resilience assessment combining all sub-reports."""

    gateway_type: GatewayType = GatewayType.NGINX
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0)
    routing: RoutingResilienceReport = Field(
        default_factory=RoutingResilienceReport,
    )
    auth: AuthResilienceReport = Field(default_factory=AuthResilienceReport)
    rate_limit: RateLimitReport = Field(default_factory=RateLimitReport)
    transformation: TransformationReport = Field(
        default_factory=TransformationReport,
    )
    ha: HAReport = Field(default_factory=HAReport)
    tls: TLSReport = Field(default_factory=TLSReport)
    long_connections: LongConnectionReport = Field(
        default_factory=LongConnectionReport,
    )
    buffering_timeout: BufferingTimeoutReport = Field(
        default_factory=BufferingTimeoutReport,
    )
    circuit_breaker: CircuitBreakerReport = Field(
        default_factory=CircuitBreakerReport,
    )
    canary: CanaryReport = Field(default_factory=CanaryReport)
    cache: CacheReport = Field(default_factory=CacheReport)
    timestamp: str = ""
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GATEWAY_BASE_LATENCY_MS: dict[GatewayType, float] = {
    GatewayType.KONG: 3.0,
    GatewayType.AWS_API_GATEWAY: 5.0,
    GatewayType.ENVOY: 1.5,
    GatewayType.NGINX: 1.0,
    GatewayType.TRAEFIK: 2.0,
    GatewayType.HAPROXY: 0.8,
}

_GATEWAY_MAX_RPS: dict[GatewayType, int] = {
    GatewayType.KONG: 50_000,
    GatewayType.AWS_API_GATEWAY: 10_000,
    GatewayType.ENVOY: 100_000,
    GatewayType.NGINX: 80_000,
    GatewayType.TRAEFIK: 60_000,
    GatewayType.HAPROXY: 120_000,
}

_HA_FAILOVER_TIME_S: dict[HAMode, float] = {
    HAMode.ACTIVE_PASSIVE: 15.0,
    HAMode.ACTIVE_ACTIVE: 2.0,
    HAMode.STANDALONE: 0.0,
}

_TLS_OVERHEAD_MS: dict[TLSTermination, float] = {
    TLSTermination.EDGE: 1.5,
    TLSTermination.PASSTHROUGH: 0.3,
    TLSTermination.RE_ENCRYPT: 2.8,
    TLSTermination.NONE: 0.0,
}

_CERT_EXPIRY_THRESHOLDS: list[tuple[int, str]] = [
    (7, "critical"),
    (30, "high"),
    (90, "medium"),
]


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class APIGatewayResilienceAnalyzer:
    """Stateless engine that analyzes API gateway configurations for
    resilience characteristics.
    """

    # -- routing resilience ------------------------------------------------

    def analyze_routing(
        self,
        graph: InfraGraph,
        config: GatewayConfig,
    ) -> RoutingResilienceReport:
        """Analyze request routing resilience (path/header/weight-based)."""
        rules = config.routing_rules
        total = len(rules)
        path_count = sum(
            1 for r in rules if r.strategy == RoutingStrategy.PATH_BASED
        )
        header_count = sum(
            1 for r in rules if r.strategy == RoutingStrategy.HEADER_BASED
        )
        weight_count = sum(
            1 for r in rules if r.strategy == RoutingStrategy.WEIGHT_BASED
        )

        missing_retry: list[str] = []
        high_timeout: list[str] = []
        recommendations: list[str] = []
        score = 100.0

        if total == 0:
            score -= 30.0
            recommendations.append(
                "No routing rules configured; gateway will not route traffic"
            )
        else:
            for r in rules:
                if r.retry_count == 0:
                    missing_retry.append(r.path_pattern)
                if r.timeout_ms > 60_000:
                    high_timeout.append(r.path_pattern)

            if missing_retry:
                penalty = min(20.0, len(missing_retry) * 5.0)
                score -= penalty
                recommendations.append(
                    f"{len(missing_retry)} routing rule(s) have no retries configured"
                )

            if high_timeout:
                penalty = min(15.0, len(high_timeout) * 5.0)
                score -= penalty
                recommendations.append(
                    f"{len(high_timeout)} routing rule(s) have timeout > 60s"
                )

            # Weight-based validation
            if weight_count > 0:
                total_weight = sum(
                    r.weight for r in rules
                    if r.strategy == RoutingStrategy.WEIGHT_BASED
                )
                if abs(total_weight - 100.0) > 0.01:
                    score -= 10.0
                    recommendations.append(
                        f"Weight-based routing weights sum to {total_weight:.1f}%, "
                        "expected 100%"
                    )

            # Check routing targets exist in graph
            for r in rules:
                if r.target_service and graph.get_component(r.target_service) is None:
                    score -= 5.0
                    recommendations.append(
                        f"Routing target '{r.target_service}' not found in graph"
                    )

        score = _clamp(score)
        return RoutingResilienceReport(
            total_rules=total,
            path_based_count=path_count,
            header_based_count=header_count,
            weight_based_count=weight_count,
            missing_retry_rules=missing_retry,
            high_timeout_rules=high_timeout,
            score=round(score, 2),
            recommendations=recommendations,
        )

    # -- auth failure handling ---------------------------------------------

    def analyze_auth_resilience(
        self,
        config: GatewayConfig,
    ) -> AuthResilienceReport:
        """Analyze authentication/authorization failure handling."""
        recommendations: list[str] = []
        method = config.auth_method
        has_auth = method != AuthMethod.NONE
        score = 0.0

        if not has_auth:
            score = 0.0
            recommendations.append(
                "No authentication configured; API endpoints are unprotected"
            )
            return AuthResilienceReport(
                auth_method=method,
                has_auth=False,
                fallback_configured=False,
                token_refresh_strategy=False,
                score=0.0,
                recommendations=recommendations,
            )

        score = 40.0  # base for having auth

        # Method-specific scoring
        if method == AuthMethod.MTLS:
            score += 30.0
        elif method == AuthMethod.OAUTH2:
            score += 25.0
        elif method == AuthMethod.JWT:
            score += 20.0
        elif method == AuthMethod.API_KEY:
            score += 10.0
            recommendations.append(
                "API key auth is simple but less secure; consider JWT or OAuth2"
            )
        elif method == AuthMethod.BASIC:
            score += 5.0
            recommendations.append(
                "Basic auth transmits credentials per request; upgrade to JWT or OAuth2"
            )

        # Check TLS for credential protection
        fallback = config.tls_termination != TLSTermination.NONE
        if fallback:
            score += 15.0
        else:
            recommendations.append(
                "No TLS configured; credentials may be transmitted in cleartext"
            )

        # Token refresh heuristic: JWT/OAuth2 benefit from it
        token_refresh = method in (AuthMethod.JWT, AuthMethod.OAUTH2)
        if token_refresh:
            score += 10.0

        if method in (AuthMethod.JWT, AuthMethod.OAUTH2) and not config.circuit_breaker.enabled:
            recommendations.append(
                "Enable circuit breaker to handle auth provider outages gracefully"
            )

        score = _clamp(score)
        return AuthResilienceReport(
            auth_method=method,
            has_auth=True,
            fallback_configured=fallback,
            token_refresh_strategy=token_refresh,
            score=round(score, 2),
            recommendations=recommendations,
        )

    # -- rate limiting / throttling ----------------------------------------

    def analyze_rate_limiting(
        self,
        graph: InfraGraph,
        config: GatewayConfig,
    ) -> RateLimitReport:
        """Analyze rate limiting and throttling configuration."""
        rl = config.rate_limit
        recommendations: list[str] = []

        gateway_max = _GATEWAY_MAX_RPS.get(config.gateway_type, 20_000)
        configured = rl.requests_per_second

        if gateway_max > 0:
            headroom = ((gateway_max - configured) / gateway_max) * 100.0
        else:
            headroom = 0.0

        # Saturation risk
        upstream_count = max(1, len(config.upstream_services))
        rps_per_service = configured / upstream_count

        if rps_per_service > 10_000:
            saturation_risk = "critical"
            recommendations.append(
                "RPS per upstream service exceeds 10,000; high saturation risk"
            )
        elif rps_per_service > 5_000:
            saturation_risk = "high"
            recommendations.append(
                "RPS per upstream service exceeds 5,000; monitor closely"
            )
        elif rps_per_service > 1_000:
            saturation_risk = "medium"
        else:
            saturation_risk = "low"

        if configured == 0:
            recommendations.append(
                "Rate limiting is set to 0 RPS; all traffic will be rejected"
            )
        elif configured > gateway_max:
            recommendations.append(
                f"Configured RPS ({configured}) exceeds gateway capacity "
                f"({gateway_max}); gateway will be a bottleneck"
            )

        if rl.burst_size > configured:
            recommendations.append(
                "Burst size exceeds sustained rate limit; "
                "may cause momentary overload on upstream services"
            )

        if not rl.per_client:
            recommendations.append(
                "Rate limit is global, not per-client; "
                "a single client can exhaust the entire budget"
            )

        return RateLimitReport(
            configured_rps=configured,
            burst_size=rl.burst_size,
            per_client=rl.per_client,
            headroom_percent=round(headroom, 2),
            saturation_risk=saturation_risk,
            recommendations=recommendations,
        )

    # -- transformation error handling -------------------------------------

    def analyze_transformation(
        self,
        config: GatewayConfig,
    ) -> TransformationReport:
        """Analyze request/response transformation error handling."""
        recommendations: list[str] = []
        has_req = config.buffering.request_buffering
        has_resp = config.buffering.response_buffering
        score = 50.0  # base

        if has_req:
            score += 15.0
        else:
            recommendations.append(
                "Request buffering disabled; streaming errors may cause partial reads"
            )

        if has_resp:
            score += 15.0
        else:
            recommendations.append(
                "Response buffering disabled; transformation errors may produce "
                "corrupt responses"
            )

        if config.buffering.max_request_body_bytes < 1024:
            score -= 10.0
            recommendations.append(
                "Max request body size is very small; may reject valid requests"
            )
        elif config.buffering.max_request_body_bytes > 50_000_000:
            score -= 5.0
            recommendations.append(
                "Max request body is very large (>50MB); "
                "may consume excessive memory"
            )

        if config.global_timeout_ms < 1000 and has_req:
            score -= 5.0
            recommendations.append(
                "Very short global timeout with buffering enabled; "
                "large payloads may timeout during buffering"
            )

        score = _clamp(score)
        return TransformationReport(
            has_request_transform=has_req,
            has_response_transform=has_resp,
            error_handling_score=round(score, 2),
            recommendations=recommendations,
        )

    # -- gateway HA --------------------------------------------------------

    def analyze_ha(
        self,
        graph: InfraGraph,
        config: GatewayConfig,
    ) -> HAReport:
        """Analyze gateway high availability (active-passive / active-active)."""
        recommendations: list[str] = []
        ha = config.ha_mode
        failover_time = _HA_FAILOVER_TIME_S.get(ha, 0.0)

        # Count gateway (load_balancer) components in graph
        gw_comps = [
            c for c in graph.components.values()
            if c.type == ComponentType.LOAD_BALANCER
        ]
        cluster_size = sum(c.replicas for c in gw_comps) if gw_comps else 0
        spof_detected = False

        if ha == HAMode.STANDALONE:
            score = 10.0
            spof_detected = True
            recommendations.append(
                "Gateway runs in standalone mode with no failover; "
                "single point of failure"
            )
            recommendations.append(
                "Deploy at least active-passive clustering for production"
            )
        elif ha == HAMode.ACTIVE_PASSIVE:
            score = 60.0
            if cluster_size < 2:
                score -= 15.0
                spof_detected = True
                recommendations.append(
                    "Active-passive declared but fewer than 2 gateway instances found"
                )
            else:
                recommendations.append(
                    f"Active-passive with failover time ~{failover_time:.0f}s"
                )
        elif ha == HAMode.ACTIVE_ACTIVE:
            score = 90.0
            if cluster_size < 2:
                score -= 20.0
                spof_detected = True
                recommendations.append(
                    "Active-active declared but fewer than 2 gateway instances found"
                )
            else:
                if cluster_size >= 3:
                    score += 10.0
                recommendations.append(
                    f"Active-active with {cluster_size} instances; "
                    f"failover time ~{failover_time:.0f}s"
                )

        if not config.health_check_path:
            score -= 10.0
            recommendations.append(
                "No health check path configured; failure detection will be delayed"
            )

        score = _clamp(score)
        return HAReport(
            ha_mode=ha,
            failover_time_seconds=failover_time,
            cluster_size=cluster_size,
            spof_detected=spof_detected,
            score=round(score, 2),
            recommendations=recommendations,
        )

    # -- TLS termination ---------------------------------------------------

    def analyze_tls(
        self,
        config: GatewayConfig,
    ) -> TLSReport:
        """Analyze TLS termination and certificate management."""
        recommendations: list[str] = []
        mode = config.tls_termination
        days = config.tls_cert_expiry_days
        overhead = _TLS_OVERHEAD_MS.get(mode, 0.0)

        if mode == TLSTermination.NONE:
            score = 0.0
            recommendations.append(
                "No TLS configured; all traffic is in cleartext"
            )
            return TLSReport(
                termination_mode=mode,
                cert_expiry_days=0,
                cert_expiry_risk="none",
                overhead_ms=0.0,
                score=0.0,
                recommendations=recommendations,
            )

        score = 60.0  # base for having TLS

        # Cert expiry risk
        cert_risk = "low"
        for threshold, risk in _CERT_EXPIRY_THRESHOLDS:
            if days <= threshold:
                cert_risk = risk
                break

        if cert_risk == "critical":
            score -= 30.0
            recommendations.append(
                f"TLS certificate expires in {days} days; immediate renewal required"
            )
        elif cert_risk == "high":
            score -= 20.0
            recommendations.append(
                f"TLS certificate expires in {days} days; schedule renewal soon"
            )
        elif cert_risk == "medium":
            score -= 10.0
            recommendations.append(
                f"TLS certificate expires in {days} days; plan renewal"
            )
        else:
            score += 20.0

        if mode == TLSTermination.RE_ENCRYPT:
            score += 10.0
            recommendations.append(
                "Re-encrypt mode provides end-to-end encryption with inspection capability"
            )
        elif mode == TLSTermination.EDGE:
            score += 5.0
            recommendations.append(
                "Edge termination: backend traffic is unencrypted; "
                "consider re-encrypt for sensitive data"
            )
        elif mode == TLSTermination.PASSTHROUGH:
            score += 15.0
            recommendations.append(
                "Passthrough mode: lowest latency but gateway cannot inspect traffic"
            )

        score = _clamp(score)
        return TLSReport(
            termination_mode=mode,
            cert_expiry_days=days,
            cert_expiry_risk=cert_risk,
            overhead_ms=overhead,
            score=round(score, 2),
            recommendations=recommendations,
        )

    # -- long connections (WebSocket / SSE) --------------------------------

    def analyze_long_connections(
        self,
        config: GatewayConfig,
    ) -> LongConnectionReport:
        """Analyze WebSocket/SSE handling during failover."""
        recommendations: list[str] = []
        ws = config.websocket_support
        sse = config.sse_support

        if not ws and not sse:
            return LongConnectionReport(
                websocket_support=False,
                sse_support=False,
                reconnect_risk="none",
                session_persistence_risk="none",
                score=100.0,
                recommendations=["No long-lived connections configured; no risk"],
            )

        score = 60.0

        # Reconnect risk
        if config.ha_mode == HAMode.STANDALONE:
            reconnect_risk = "critical"
            score -= 30.0
            recommendations.append(
                "Long-lived connections with standalone gateway; "
                "all connections drop on gateway failure"
            )
        elif config.ha_mode == HAMode.ACTIVE_PASSIVE:
            reconnect_risk = "high"
            score -= 15.0
            recommendations.append(
                "Active-passive failover will drop all WebSocket/SSE connections; "
                "clients must reconnect"
            )
        else:
            reconnect_risk = "medium"
            score -= 5.0
            recommendations.append(
                "Active-active may still disrupt long-lived connections "
                "on node failure; implement client reconnect logic"
            )

        # Session persistence
        session_risk = "none"
        if ws and config.global_timeout_ms < 60_000:
            session_risk = "high"
            score -= 10.0
            recommendations.append(
                "WebSocket connections may be terminated by gateway timeout; "
                "increase timeout or configure idle ping"
            )
        elif ws:
            session_risk = "low"

        if sse and not config.buffering.response_buffering:
            score -= 5.0
            recommendations.append(
                "SSE with response buffering disabled; events may be delayed or lost"
            )

        score = _clamp(score)
        return LongConnectionReport(
            websocket_support=ws,
            sse_support=sse,
            reconnect_risk=reconnect_risk,
            session_persistence_risk=session_risk,
            score=round(score, 2),
            recommendations=recommendations,
        )

    # -- buffering & timeout -----------------------------------------------

    def analyze_buffering_timeout(
        self,
        config: GatewayConfig,
    ) -> BufferingTimeoutReport:
        """Analyze request buffering and timeout configuration."""
        recommendations: list[str] = []
        buf = config.buffering
        timeout = config.global_timeout_ms
        score = 60.0

        if timeout > 120_000:
            timeout_risk = "critical"
            score -= 25.0
            recommendations.append(
                "Global timeout exceeds 120s; long-held connections can exhaust resources"
            )
        elif timeout > 60_000:
            timeout_risk = "high"
            score -= 15.0
            recommendations.append(
                "Global timeout exceeds 60s; consider reducing to fail fast"
            )
        elif timeout > 30_000:
            timeout_risk = "medium"
            score -= 5.0
        elif timeout < 1_000:
            timeout_risk = "high"
            score -= 15.0
            recommendations.append(
                "Global timeout is very short (<1s); may cause premature failures"
            )
        else:
            timeout_risk = "low"
            score += 20.0

        if buf.request_buffering:
            score += 10.0
        else:
            recommendations.append(
                "Request buffering disabled; partial reads on slow networks possible"
            )

        if buf.response_buffering:
            score += 10.0
        else:
            recommendations.append(
                "Response buffering disabled; chunked response errors may propagate"
            )

        score = _clamp(score)
        return BufferingTimeoutReport(
            request_buffering=buf.request_buffering,
            response_buffering=buf.response_buffering,
            global_timeout_ms=timeout,
            max_request_body_bytes=buf.max_request_body_bytes,
            timeout_risk=timeout_risk,
            score=round(score, 2),
            recommendations=recommendations,
        )

    # -- circuit breaker ---------------------------------------------------

    def analyze_circuit_breaker(
        self,
        config: GatewayConfig,
    ) -> CircuitBreakerReport:
        """Analyze gateway circuit breaker integration."""
        cb = config.circuit_breaker
        recommendations: list[str] = []

        if not cb.enabled:
            recommendations.append(
                "Circuit breaker not enabled; upstream failures will cascade"
            )
            return CircuitBreakerReport(
                enabled=False,
                failure_threshold=0,
                recovery_timeout_seconds=0.0,
                monitored_codes=[],
                score=0.0,
                recommendations=recommendations,
            )

        score = 50.0  # base for having CB

        if cb.failure_threshold <= 2:
            score += 20.0
            recommendations.append(
                "Low failure threshold; circuit opens quickly (may cause flapping)"
            )
        elif cb.failure_threshold <= 5:
            score += 25.0
        else:
            score += 10.0
            recommendations.append(
                f"High failure threshold ({cb.failure_threshold}); "
                "circuit may open too slowly to prevent cascade"
            )

        if cb.recovery_timeout_seconds < 10:
            score += 5.0
            recommendations.append(
                "Very short recovery timeout; circuit may reclose too quickly"
            )
        elif cb.recovery_timeout_seconds > 120:
            score -= 10.0
            recommendations.append(
                "Long recovery timeout; service may stay isolated too long"
            )
        else:
            score += 15.0

        if not cb.monitored_error_codes:
            score -= 10.0
            recommendations.append(
                "No error codes monitored; circuit breaker may not trigger correctly"
            )
        else:
            if 503 not in cb.monitored_error_codes:
                recommendations.append(
                    "503 (Service Unavailable) not in monitored codes; "
                    "consider adding it"
                )
            score += 10.0

        score = _clamp(score)
        return CircuitBreakerReport(
            enabled=True,
            failure_threshold=cb.failure_threshold,
            recovery_timeout_seconds=cb.recovery_timeout_seconds,
            monitored_codes=list(cb.monitored_error_codes),
            score=round(score, 2),
            recommendations=recommendations,
        )

    # -- canary routing ----------------------------------------------------

    def validate_canary(
        self,
        config: GatewayConfig,
    ) -> CanaryReport:
        """Validate canary routing configuration."""
        canary = config.canary
        recommendations: list[str] = []
        validation_errors: list[str] = []

        if not canary.enabled:
            return CanaryReport(
                enabled=False,
                canary_weight=0.0,
                has_auto_rollback=False,
                has_success_criteria=False,
                validation_errors=[],
                score=50.0,
                recommendations=["Canary routing not configured; using big-bang deploys"],
            )

        score = 50.0

        # Validate weight
        if canary.canary_weight <= 0.0:
            validation_errors.append("Canary weight is 0%; no traffic goes to canary")
            score -= 15.0
        elif canary.canary_weight > 50.0:
            validation_errors.append(
                f"Canary weight is {canary.canary_weight}%; "
                "too high for safe canary deployment"
            )
            score -= 10.0
        else:
            score += 15.0

        # Validate services
        if not canary.canary_service:
            validation_errors.append("No canary service specified")
            score -= 10.0
        if not canary.stable_service:
            validation_errors.append("No stable service specified")
            score -= 10.0

        # Auto-rollback
        if canary.auto_rollback:
            score += 15.0
        else:
            recommendations.append(
                "Auto-rollback disabled; manual intervention required on failure"
            )

        # Success criteria
        has_criteria = canary.success_threshold > 0 and canary.error_threshold > 0
        if has_criteria:
            score += 10.0
        else:
            recommendations.append(
                "No success/error thresholds defined; cannot auto-evaluate canary"
            )

        if canary.canary_service and canary.stable_service:
            if canary.canary_service == canary.stable_service:
                validation_errors.append(
                    "Canary and stable services are the same"
                )
                score -= 15.0

        score = _clamp(score)
        return CanaryReport(
            enabled=True,
            canary_weight=canary.canary_weight,
            has_auto_rollback=canary.auto_rollback,
            has_success_criteria=has_criteria,
            validation_errors=validation_errors,
            score=round(score, 2),
            recommendations=recommendations,
        )

    # -- caching strategy --------------------------------------------------

    def analyze_caching(
        self,
        config: GatewayConfig,
    ) -> CacheReport:
        """Analyze gateway caching strategy and invalidation."""
        cache = config.cache
        recommendations: list[str] = []
        strategy = cache.strategy
        invalidation = cache.invalidation

        if strategy == CacheStrategy.NO_CACHE:
            recommendations.append(
                "No caching configured; all requests hit upstream services directly"
            )
            return CacheReport(
                strategy=strategy,
                invalidation=CacheInvalidation.NONE,
                ttl_seconds=0,
                max_size_mb=0,
                stale_serving=False,
                score=30.0,
                recommendations=recommendations,
            )

        score = 40.0  # base for having caching

        # TTL assessment
        if cache.ttl_seconds < 10:
            score -= 5.0
            recommendations.append(
                "Very short cache TTL (<10s); caching benefit is minimal"
            )
        elif cache.ttl_seconds > 3600:
            score -= 5.0
            recommendations.append(
                "Long cache TTL (>1h); stale data risk is high"
            )
        else:
            score += 15.0

        # Cache size
        if cache.max_size_mb < 16:
            score -= 5.0
            recommendations.append(
                "Cache size is very small; frequent evictions expected"
            )
        elif cache.max_size_mb > 4096:
            recommendations.append(
                "Large cache (>4GB); monitor memory consumption"
            )
            score += 10.0
        else:
            score += 10.0

        # Stale serving
        stale = strategy in (
            CacheStrategy.STALE_WHILE_REVALIDATE,
            CacheStrategy.STALE_IF_ERROR,
        )
        if stale:
            score += 15.0
            recommendations.append(
                "Stale serving enabled; improves resilience during upstream failures"
            )

        # Invalidation method
        if invalidation == CacheInvalidation.NONE:
            score -= 10.0
            recommendations.append(
                "No cache invalidation configured; stale data may persist"
            )
        elif invalidation == CacheInvalidation.EVENT_DRIVEN:
            score += 10.0
        elif invalidation == CacheInvalidation.TAG_BASED:
            score += 8.0
        elif invalidation == CacheInvalidation.PURGE_API:
            score += 5.0
        else:
            score += 3.0

        score = _clamp(score)
        return CacheReport(
            strategy=strategy,
            invalidation=invalidation,
            ttl_seconds=cache.ttl_seconds,
            max_size_mb=cache.max_size_mb,
            stale_serving=stale,
            score=round(score, 2),
            recommendations=recommendations,
        )

    # -- full assessment ---------------------------------------------------

    def assess(
        self,
        graph: InfraGraph,
        config: GatewayConfig,
    ) -> GatewayResilienceReport:
        """Perform a comprehensive gateway resilience assessment."""
        routing = self.analyze_routing(graph, config)
        auth = self.analyze_auth_resilience(config)
        rate = self.analyze_rate_limiting(graph, config)
        transform = self.analyze_transformation(config)
        ha = self.analyze_ha(graph, config)
        tls = self.analyze_tls(config)
        lc = self.analyze_long_connections(config)
        bt = self.analyze_buffering_timeout(config)
        cb = self.analyze_circuit_breaker(config)
        canary = self.validate_canary(config)
        cache = self.analyze_caching(config)

        sub_scores = [
            routing.score,
            auth.score,
            ha.score,
            tls.score,
            lc.score,
            bt.score,
            cb.score,
            canary.score,
            cache.score,
        ]
        overall = sum(sub_scores) / len(sub_scores) if sub_scores else 0.0

        # Collect top-level recommendations from sub-reports
        all_recs: list[str] = []
        for sub in (routing, auth, rate, transform, ha, tls, lc, bt, cb, canary, cache):
            all_recs.extend(sub.recommendations)

        # Deduplicate
        seen: set[str] = set()
        unique_recs: list[str] = []
        for r in all_recs:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        now = datetime.now(timezone.utc).isoformat()

        return GatewayResilienceReport(
            gateway_type=config.gateway_type,
            overall_score=round(_clamp(overall), 2),
            routing=routing,
            auth=auth,
            rate_limit=rate,
            transformation=transform,
            ha=ha,
            tls=tls,
            long_connections=lc,
            buffering_timeout=bt,
            circuit_breaker=cb,
            canary=canary,
            cache=cache,
            timestamp=now,
            recommendations=unique_recs,
        )
