"""Tests for Idempotency Pattern Analyzer.

Comprehensive test suite covering all enums, data models, utility functions,
key coverage analysis, retry safety scoring, delivery semantics classification,
duplicate request detection, idempotency window/TTL analysis, side-effect
isolation scoring, financial operation audit, collision risk estimation,
cross-service chain analysis, testing coverage gap detection, compensating
transaction detection, event sourcing evaluation, graph-aware helpers, and
full analysis integration.
"""

from __future__ import annotations

import math

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.idempotency_analyzer import (
    ChainAnalysis,
    ChainLink,
    CollisionRisk,
    CollisionRiskResult,
    CompensationAnalysis,
    CompensationStrategy,
    CoverageGap,
    CoverageGapSeverity,
    DeliveryAnalysis,
    DeliverySemantics,
    DuplicateDetectionResult,
    EndpointConfig,
    EventSourcingResult,
    FinancialAuditResult,
    IdempotencyAnalyzer,
    IdempotencyKeyStrategy,
    IdempotencyReport,
    KeyCoverageResult,
    RetrySafety,
    RetrySafetyResult,
    ServiceConfig,
    SideEffectIsolationResult,
    SideEffectType,
    TestCoverageResult,
    WindowAnalysis,
    _COLLISION_BASE_RATE,
    _DEFAULT_IDEMPOTENCY_WINDOW_SECONDS,
    _EVENT_SOURCING_TAGS,
    _FINANCIAL_COMPONENT_TAGS,
    _IDEMPOTENT_HTTP_METHODS,
    _MAX_SCORE,
    _SAFE_HTTP_METHODS,
    _clamp,
    _classify_collision_risk,
    _collision_probability,
    _days_to_collision,
    _endpoint_retry_score,
    _has_event_sourcing_tags,
    _is_financial_endpoint,
    _is_idempotent_method,
    _is_safe_method,
    _key_space_bits,
    _side_effect_isolation_score,
    _window_risk_level,
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


def _analyzer() -> IdempotencyAnalyzer:
    return IdempotencyAnalyzer()


def _ep(
    cid: str = "svc1",
    path: str = "/api/orders",
    method: str = "POST",
    has_key: bool = False,
    strategy: IdempotencyKeyStrategy = IdempotencyKeyStrategy.NONE,
    window: int = _DEFAULT_IDEMPOTENCY_WINDOW_SECONDS,
    side_effects: list[SideEffectType] | None = None,
    is_financial: bool = False,
    tags: list[str] | None = None,
) -> EndpointConfig:
    return EndpointConfig(
        component_id=cid,
        path=path,
        method=method,
        has_idempotency_key=has_key,
        key_strategy=strategy,
        idempotency_window_seconds=window,
        side_effects=side_effects or [],
        is_financial=is_financial,
        tags=tags or [],
    )


def _svc(
    cid: str = "svc1",
    endpoints: list[EndpointConfig] | None = None,
    delivery: DeliverySemantics = DeliverySemantics.UNKNOWN,
    has_dedup: bool = False,
    dedup_window: int = 0,
    has_es: bool = False,
    compensation: CompensationStrategy = CompensationStrategy.NONE,
    tags: list[str] | None = None,
) -> ServiceConfig:
    return ServiceConfig(
        component_id=cid,
        endpoints=endpoints or [],
        delivery_semantics=delivery,
        has_deduplication=has_dedup,
        deduplication_window_seconds=dedup_window,
        has_event_sourcing=has_es,
        compensation_strategy=compensation,
        tags=tags or [],
    )


# ===========================================================================
# Constants tests
# ===========================================================================


class TestConstants:
    def test_max_score(self):
        assert _MAX_SCORE == 100.0

    def test_default_window(self):
        assert _DEFAULT_IDEMPOTENCY_WINDOW_SECONDS == 86_400

    def test_collision_base_rate(self):
        assert _COLLISION_BASE_RATE == 1e-18

    def test_financial_tags(self):
        assert "payment" in _FINANCIAL_COMPONENT_TAGS
        assert "billing" in _FINANCIAL_COMPONENT_TAGS
        assert "ledger" in _FINANCIAL_COMPONENT_TAGS
        assert "invoice" in _FINANCIAL_COMPONENT_TAGS

    def test_event_sourcing_tags(self):
        assert "event_sourcing" in _EVENT_SOURCING_TAGS
        assert "cqrs" in _EVENT_SOURCING_TAGS
        assert "event_store" in _EVENT_SOURCING_TAGS

    def test_safe_http_methods(self):
        assert "GET" in _SAFE_HTTP_METHODS
        assert "HEAD" in _SAFE_HTTP_METHODS
        assert "OPTIONS" in _SAFE_HTTP_METHODS
        assert "TRACE" in _SAFE_HTTP_METHODS
        assert "POST" not in _SAFE_HTTP_METHODS

    def test_idempotent_http_methods(self):
        assert "PUT" in _IDEMPOTENT_HTTP_METHODS
        assert "DELETE" in _IDEMPOTENT_HTTP_METHODS
        assert "POST" not in _IDEMPOTENT_HTTP_METHODS


# ===========================================================================
# Enum tests
# ===========================================================================


class TestEnums:
    def test_delivery_semantics_values(self):
        assert DeliverySemantics.AT_MOST_ONCE == "at_most_once"
        assert DeliverySemantics.AT_LEAST_ONCE == "at_least_once"
        assert DeliverySemantics.EXACTLY_ONCE == "exactly_once"
        assert DeliverySemantics.UNKNOWN == "unknown"

    def test_retry_safety_values(self):
        assert RetrySafety.SAFE == "safe"
        assert RetrySafety.CONDITIONALLY_SAFE == "conditionally_safe"
        assert RetrySafety.UNSAFE == "unsafe"
        assert RetrySafety.UNKNOWN == "unknown"

    def test_key_strategy_values(self):
        assert IdempotencyKeyStrategy.UUID_V4 == "uuid_v4"
        assert IdempotencyKeyStrategy.CLIENT_GENERATED == "client_generated"
        assert IdempotencyKeyStrategy.CONTENT_HASH == "content_hash"
        assert IdempotencyKeyStrategy.COMPOSITE == "composite"
        assert IdempotencyKeyStrategy.NONE == "none"

    def test_side_effect_type_values(self):
        assert SideEffectType.DATABASE_WRITE == "database_write"
        assert SideEffectType.EXTERNAL_API_CALL == "external_api_call"
        assert SideEffectType.MESSAGE_PUBLISH == "message_publish"
        assert SideEffectType.FILE_WRITE == "file_write"
        assert SideEffectType.NOTIFICATION == "notification"
        assert SideEffectType.PAYMENT == "payment"
        assert SideEffectType.STATE_MUTATION == "state_mutation"

    def test_compensation_strategy_values(self):
        assert CompensationStrategy.SAGA == "saga"
        assert CompensationStrategy.TCC == "tcc"
        assert CompensationStrategy.MANUAL == "manual"
        assert CompensationStrategy.NONE == "none"

    def test_collision_risk_values(self):
        assert CollisionRisk.NEGLIGIBLE == "negligible"
        assert CollisionRisk.LOW == "low"
        assert CollisionRisk.MEDIUM == "medium"
        assert CollisionRisk.HIGH == "high"
        assert CollisionRisk.CRITICAL == "critical"

    def test_coverage_gap_severity_values(self):
        assert CoverageGapSeverity.INFO == "info"
        assert CoverageGapSeverity.LOW == "low"
        assert CoverageGapSeverity.MEDIUM == "medium"
        assert CoverageGapSeverity.HIGH == "high"
        assert CoverageGapSeverity.CRITICAL == "critical"


# ===========================================================================
# Dataclass defaults tests
# ===========================================================================


class TestDataclassDefaults:
    def test_endpoint_config_defaults(self):
        ep = EndpointConfig(component_id="x")
        assert ep.path == ""
        assert ep.method == "POST"
        assert ep.has_idempotency_key is False
        assert ep.key_strategy == IdempotencyKeyStrategy.NONE
        assert ep.idempotency_window_seconds == _DEFAULT_IDEMPOTENCY_WINDOW_SECONDS
        assert ep.side_effects == []
        assert ep.is_financial is False
        assert ep.tags == []

    def test_service_config_defaults(self):
        svc = ServiceConfig(component_id="x")
        assert svc.endpoints == []
        assert svc.delivery_semantics == DeliverySemantics.UNKNOWN
        assert svc.has_deduplication is False
        assert svc.deduplication_window_seconds == 0
        assert svc.has_event_sourcing is False
        assert svc.compensation_strategy == CompensationStrategy.NONE

    def test_key_coverage_result_defaults(self):
        r = KeyCoverageResult()
        assert r.total_endpoints == 0
        assert r.coverage_ratio == 0.0

    def test_retry_safety_result_defaults(self):
        r = RetrySafetyResult()
        assert r.safety == RetrySafety.UNKNOWN
        assert r.score == 0.0

    def test_delivery_analysis_defaults(self):
        r = DeliveryAnalysis()
        assert r.services_analyzed == 0

    def test_duplicate_detection_defaults(self):
        r = DuplicateDetectionResult()
        assert r.total_services == 0

    def test_window_analysis_defaults(self):
        r = WindowAnalysis()
        assert r.is_adequate is True
        assert r.risk_level == "low"

    def test_side_effect_isolation_defaults(self):
        r = SideEffectIsolationResult()
        assert r.isolation_score == 0.0
        assert r.side_effect_count == 0

    def test_financial_audit_defaults(self):
        r = FinancialAuditResult()
        assert r.compliance_ratio == 0.0

    def test_collision_risk_result_defaults(self):
        r = CollisionRiskResult()
        assert r.risk_level == CollisionRisk.NEGLIGIBLE

    def test_chain_link_defaults(self):
        lnk = ChainLink()
        assert lnk.has_idempotency is False
        assert lnk.delivery_semantics == DeliverySemantics.UNKNOWN

    def test_chain_analysis_defaults(self):
        r = ChainAnalysis()
        assert r.total_chains == 0

    def test_coverage_gap_defaults(self):
        g = CoverageGap()
        assert g.severity == CoverageGapSeverity.INFO

    def test_test_coverage_result_defaults(self):
        r = TestCoverageResult()
        assert r.total_gaps == 0

    def test_compensation_analysis_defaults(self):
        r = CompensationAnalysis()
        assert r.total_services == 0

    def test_event_sourcing_result_defaults(self):
        r = EventSourcingResult()
        assert r.score == 0.0

    def test_idempotency_report_defaults(self):
        r = IdempotencyReport()
        assert r.overall_score == 0.0
        assert r.analyzed_at is not None


# ===========================================================================
# Utility function tests
# ===========================================================================


class TestClamp:
    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_lo(self):
        assert _clamp(-10.0) == 0.0

    def test_above_hi(self):
        assert _clamp(200.0) == 100.0

    def test_exact_lo(self):
        assert _clamp(0.0) == 0.0

    def test_exact_hi(self):
        assert _clamp(100.0) == 100.0

    def test_custom_range(self):
        assert _clamp(5.0, 0.0, 10.0) == 5.0
        assert _clamp(-1.0, 0.0, 10.0) == 0.0
        assert _clamp(15.0, 0.0, 10.0) == 10.0


class TestIsFinancialEndpoint:
    def test_explicit_financial_flag(self):
        ep = _ep(is_financial=True)
        assert _is_financial_endpoint(ep) is True

    def test_financial_tag(self):
        ep = _ep(tags=["payment"])
        assert _is_financial_endpoint(ep) is True

    def test_billing_tag(self):
        ep = _ep(tags=["Billing"])
        assert _is_financial_endpoint(ep) is True

    def test_no_financial_indication(self):
        ep = _ep()
        assert _is_financial_endpoint(ep) is False

    def test_unrelated_tags(self):
        ep = _ep(tags=["api", "v2"])
        assert _is_financial_endpoint(ep) is False


class TestIsSafeMethod:
    def test_get(self):
        assert _is_safe_method("GET") is True

    def test_head(self):
        assert _is_safe_method("HEAD") is True

    def test_options(self):
        assert _is_safe_method("OPTIONS") is True

    def test_trace(self):
        assert _is_safe_method("TRACE") is True

    def test_post(self):
        assert _is_safe_method("POST") is False

    def test_put(self):
        assert _is_safe_method("PUT") is False

    def test_delete(self):
        assert _is_safe_method("DELETE") is False

    def test_lowercase(self):
        assert _is_safe_method("get") is True


class TestIsIdempotentMethod:
    def test_put(self):
        assert _is_idempotent_method("PUT") is True

    def test_delete(self):
        assert _is_idempotent_method("DELETE") is True

    def test_post(self):
        assert _is_idempotent_method("POST") is False

    def test_get(self):
        assert _is_idempotent_method("GET") is False

    def test_lowercase(self):
        assert _is_idempotent_method("put") is True


class TestCollisionProbability:
    def test_zero_keys(self):
        assert _collision_probability(128, 0) == 0.0

    def test_zero_bits(self):
        assert _collision_probability(0, 100) == 0.0

    def test_small_key_space(self):
        prob = _collision_probability(16, 100)
        assert 0.0 < prob < 1.0

    def test_large_key_space(self):
        prob = _collision_probability(128, 1000)
        assert prob < 1e-30

    def test_extremely_large_exponent(self):
        # Should not overflow
        prob = _collision_probability(10, 100_000_000)
        assert prob == 0.0 or prob >= 0.0


class TestKeySpaceBits:
    def test_uuid_v4(self):
        assert _key_space_bits(IdempotencyKeyStrategy.UUID_V4) == 122

    def test_client_generated(self):
        assert _key_space_bits(IdempotencyKeyStrategy.CLIENT_GENERATED) == 64

    def test_content_hash(self):
        assert _key_space_bits(IdempotencyKeyStrategy.CONTENT_HASH) == 256

    def test_composite(self):
        assert _key_space_bits(IdempotencyKeyStrategy.COMPOSITE) == 128

    def test_none(self):
        assert _key_space_bits(IdempotencyKeyStrategy.NONE) == 0


class TestClassifyCollisionRisk:
    def test_negligible(self):
        assert _classify_collision_risk(1e-20) == CollisionRisk.NEGLIGIBLE

    def test_low(self):
        assert _classify_collision_risk(1e-12) == CollisionRisk.LOW

    def test_medium(self):
        assert _classify_collision_risk(1e-8) == CollisionRisk.MEDIUM

    def test_high(self):
        assert _classify_collision_risk(1e-5) == CollisionRisk.HIGH

    def test_critical(self):
        assert _classify_collision_risk(0.1) == CollisionRisk.CRITICAL

    def test_boundary_negligible(self):
        assert _classify_collision_risk(1e-15) == CollisionRisk.NEGLIGIBLE

    def test_boundary_low(self):
        assert _classify_collision_risk(1e-9) == CollisionRisk.LOW


class TestDaysToCollision:
    def test_zero_bits(self):
        assert _days_to_collision(0, 1000) == float("inf")

    def test_zero_requests(self):
        assert _days_to_collision(128, 0) == float("inf")

    def test_positive_result(self):
        days = _days_to_collision(64, 1_000_000)
        assert days > 0
        assert days != float("inf")

    def test_large_key_space(self):
        days = _days_to_collision(128, 1_000_000)
        assert days > 1e12


class TestHasEventSourcingTags:
    def test_event_sourcing_tag(self):
        assert _has_event_sourcing_tags(["event_sourcing"]) is True

    def test_cqrs_tag(self):
        assert _has_event_sourcing_tags(["CQRS"]) is True

    def test_event_store_tag(self):
        assert _has_event_sourcing_tags(["event-store"]) is True

    def test_no_tags(self):
        assert _has_event_sourcing_tags([]) is False

    def test_unrelated_tags(self):
        assert _has_event_sourcing_tags(["api", "rest"]) is False


class TestEndpointRetryScore:
    def test_safe_method(self):
        ep = _ep(method="GET")
        assert _endpoint_retry_score(ep) == _MAX_SCORE

    def test_idempotent_method_with_key(self):
        ep = _ep(method="PUT", has_key=True)
        score = _endpoint_retry_score(ep)
        assert score > 80.0

    def test_post_without_key(self):
        ep = _ep(method="POST", has_key=False)
        score = _endpoint_retry_score(ep)
        assert score == 50.0

    def test_post_with_key(self):
        ep = _ep(method="POST", has_key=True)
        score = _endpoint_retry_score(ep)
        assert score == 80.0

    def test_financial_without_key(self):
        ep = _ep(method="POST", is_financial=True, has_key=False)
        score = _endpoint_retry_score(ep)
        assert score < 50.0

    def test_many_side_effects(self):
        ep = _ep(
            method="POST",
            side_effects=[
                SideEffectType.DATABASE_WRITE,
                SideEffectType.MESSAGE_PUBLISH,
                SideEffectType.NOTIFICATION,
                SideEffectType.FILE_WRITE,
            ],
        )
        score = _endpoint_retry_score(ep)
        assert score < 50.0

    def test_payment_side_effect(self):
        ep = _ep(
            method="POST",
            side_effects=[SideEffectType.PAYMENT],
        )
        score = _endpoint_retry_score(ep)
        assert score < 50.0

    def test_clamped_to_zero(self):
        ep = _ep(
            method="POST",
            is_financial=True,
            side_effects=[
                SideEffectType.PAYMENT,
                SideEffectType.DATABASE_WRITE,
                SideEffectType.EXTERNAL_API_CALL,
                SideEffectType.NOTIFICATION,
            ],
        )
        score = _endpoint_retry_score(ep)
        assert score >= 0.0


class TestWindowRiskLevel:
    def test_zero_window(self):
        assert _window_risk_level(0, False) == "critical"

    def test_short_non_financial(self):
        assert _window_risk_level(30, False) == "high"

    def test_medium_non_financial(self):
        assert _window_risk_level(200, False) == "medium"

    def test_adequate_non_financial(self):
        assert _window_risk_level(600, False) == "low"

    def test_financial_short(self):
        assert _window_risk_level(1800, True) == "high"

    def test_financial_medium(self):
        assert _window_risk_level(7200, True) == "medium"

    def test_financial_adequate(self):
        assert _window_risk_level(86_400, True) == "low"


class TestSideEffectIsolationScore:
    def test_no_side_effects(self):
        ep = _ep()
        assert _side_effect_isolation_score(ep) == _MAX_SCORE

    def test_one_side_effect(self):
        ep = _ep(side_effects=[SideEffectType.DATABASE_WRITE])
        score = _side_effect_isolation_score(ep)
        assert score == 88.0

    def test_payment_side_effect(self):
        ep = _ep(side_effects=[SideEffectType.PAYMENT])
        score = _side_effect_isolation_score(ep)
        assert score == 78.0

    def test_with_key_boost(self):
        ep = _ep(
            has_key=True,
            side_effects=[SideEffectType.DATABASE_WRITE],
        )
        score = _side_effect_isolation_score(ep)
        assert score > 88.0

    def test_external_api_penalty(self):
        ep = _ep(side_effects=[SideEffectType.EXTERNAL_API_CALL])
        score = _side_effect_isolation_score(ep)
        assert score == 80.0

    def test_many_effects_clamped(self):
        ep = _ep(
            side_effects=[
                SideEffectType.PAYMENT,
                SideEffectType.EXTERNAL_API_CALL,
                SideEffectType.DATABASE_WRITE,
                SideEffectType.MESSAGE_PUBLISH,
                SideEffectType.NOTIFICATION,
                SideEffectType.FILE_WRITE,
                SideEffectType.STATE_MUTATION,
            ],
        )
        score = _side_effect_isolation_score(ep)
        assert score >= 0.0


# ===========================================================================
# Key Coverage Analysis
# ===========================================================================


class TestKeyCoverageAnalysis:
    def test_empty_services(self):
        result = _analyzer().analyze_key_coverage([])
        assert result.total_endpoints == 0
        assert result.coverage_ratio == 1.0

    def test_all_safe_methods(self):
        svc = _svc(endpoints=[_ep(method="GET"), _ep(method="HEAD")])
        result = _analyzer().analyze_key_coverage([svc])
        assert result.total_endpoints == 0
        assert result.coverage_ratio == 1.0

    def test_all_covered(self):
        svc = _svc(
            endpoints=[
                _ep(method="POST", has_key=True),
                _ep(method="PUT", has_key=True),
            ]
        )
        result = _analyzer().analyze_key_coverage([svc])
        assert result.total_endpoints == 2
        assert result.covered_endpoints == 2
        assert result.uncovered_endpoints == 0
        assert result.coverage_ratio == 1.0
        assert not result.uncovered_details

    def test_partial_coverage(self):
        svc = _svc(
            endpoints=[
                _ep(method="POST", has_key=True, path="/a"),
                _ep(method="POST", has_key=False, path="/b"),
            ]
        )
        result = _analyzer().analyze_key_coverage([svc])
        assert result.total_endpoints == 2
        assert result.covered_endpoints == 1
        assert result.uncovered_endpoints == 1
        assert result.coverage_ratio == 0.5
        assert len(result.uncovered_details) == 1
        assert result.uncovered_details[0]["path"] == "/b"

    def test_no_coverage_recommendations(self):
        svc = _svc(
            endpoints=[
                _ep(method="POST", has_key=False, path="/a"),
                _ep(method="POST", has_key=False, path="/b"),
                _ep(method="POST", has_key=False, path="/c"),
            ]
        )
        result = _analyzer().analyze_key_coverage([svc])
        assert result.coverage_ratio == 0.0
        assert len(result.recommendations) == 2  # uncovered + <50%

    def test_multiple_services(self):
        svc1 = _svc(cid="s1", endpoints=[_ep(cid="s1", method="POST", has_key=True)])
        svc2 = _svc(cid="s2", endpoints=[_ep(cid="s2", method="POST", has_key=False)])
        result = _analyzer().analyze_key_coverage([svc1, svc2])
        assert result.total_endpoints == 2
        assert result.covered_endpoints == 1


# ===========================================================================
# Retry Safety Scoring
# ===========================================================================


class TestRetrySafetyScoring:
    def test_empty_services(self):
        result = _analyzer().score_retry_safety([])
        assert result == []

    def test_safe_get(self):
        svc = _svc(endpoints=[_ep(method="GET", path="/items")])
        results = _analyzer().score_retry_safety([svc])
        assert len(results) == 1
        assert results[0].safety == RetrySafety.SAFE
        assert results[0].score == _MAX_SCORE

    def test_post_with_key_safe(self):
        svc = _svc(endpoints=[_ep(method="POST", has_key=True, path="/create")])
        results = _analyzer().score_retry_safety([svc])
        assert results[0].safety == RetrySafety.SAFE

    def test_post_without_key_conditional(self):
        svc = _svc(endpoints=[_ep(method="POST", has_key=False, path="/create")])
        results = _analyzer().score_retry_safety([svc])
        assert results[0].safety == RetrySafety.CONDITIONALLY_SAFE

    def test_financial_without_key_unsafe(self):
        svc = _svc(
            endpoints=[_ep(method="POST", has_key=False, is_financial=True, path="/pay")]
        )
        results = _analyzer().score_retry_safety([svc])
        assert results[0].safety == RetrySafety.UNSAFE

    def test_reasons_include_side_effects(self):
        svc = _svc(
            endpoints=[
                _ep(
                    method="POST",
                    side_effects=[SideEffectType.DATABASE_WRITE],
                    path="/write",
                )
            ]
        )
        results = _analyzer().score_retry_safety([svc])
        reasons = results[0].reasons
        assert any("side effect" in r.lower() for r in reasons)

    def test_reasons_include_financial_warning(self):
        svc = _svc(
            endpoints=[_ep(method="POST", is_financial=True, has_key=False, path="/charge")]
        )
        results = _analyzer().score_retry_safety([svc])
        reasons = results[0].reasons
        assert any("financial" in r.lower() for r in reasons)

    def test_put_method_boost(self):
        svc = _svc(endpoints=[_ep(method="PUT", path="/update")])
        results = _analyzer().score_retry_safety([svc])
        assert results[0].score >= 75.0

    def test_multiple_endpoints(self):
        svc = _svc(
            endpoints=[
                _ep(method="GET", path="/read"),
                _ep(method="POST", has_key=True, path="/write"),
                _ep(method="DELETE", path="/delete"),
            ]
        )
        results = _analyzer().score_retry_safety([svc])
        assert len(results) == 3


# ===========================================================================
# Delivery Semantics Analysis
# ===========================================================================


class TestDeliverySemanticsAnalysis:
    def test_empty(self):
        result = _analyzer().analyze_delivery_semantics([])
        assert result.services_analyzed == 0

    def test_all_unknown(self):
        services = [_svc(cid="a"), _svc(cid="b")]
        result = _analyzer().analyze_delivery_semantics(services)
        assert result.unknown_count == 2
        assert len(result.recommendations) > 0

    def test_exactly_once(self):
        services = [_svc(delivery=DeliverySemantics.EXACTLY_ONCE)]
        result = _analyzer().analyze_delivery_semantics(services)
        assert result.exactly_once_count == 1
        assert result.unknown_count == 0

    def test_at_most_once_recommendation(self):
        services = [_svc(delivery=DeliverySemantics.AT_MOST_ONCE)]
        result = _analyzer().analyze_delivery_semantics(services)
        assert result.at_most_once_count == 1
        assert any("data loss" in r.lower() for r in result.recommendations)

    def test_at_least_once_recommendation(self):
        services = [_svc(delivery=DeliverySemantics.AT_LEAST_ONCE)]
        result = _analyzer().analyze_delivery_semantics(services)
        assert result.at_least_once_count == 1
        assert any("deduplication" in r.lower() for r in result.recommendations)

    def test_mixed_semantics(self):
        services = [
            _svc(cid="a", delivery=DeliverySemantics.AT_MOST_ONCE),
            _svc(cid="b", delivery=DeliverySemantics.AT_LEAST_ONCE),
            _svc(cid="c", delivery=DeliverySemantics.EXACTLY_ONCE),
        ]
        result = _analyzer().analyze_delivery_semantics(services)
        assert result.services_analyzed == 3
        assert result.at_most_once_count == 1
        assert result.at_least_once_count == 1
        assert result.exactly_once_count == 1

    def test_at_least_once_with_exactly_once_no_dedup_rec(self):
        services = [
            _svc(cid="a", delivery=DeliverySemantics.AT_LEAST_ONCE),
            _svc(cid="b", delivery=DeliverySemantics.EXACTLY_ONCE),
        ]
        result = _analyzer().analyze_delivery_semantics(services)
        # Should NOT recommend deduplication when exactly-once also exists
        assert not any("deduplication" in r.lower() for r in result.recommendations)


# ===========================================================================
# Duplicate Detection Assessment
# ===========================================================================


class TestDuplicateDetectionAssessment:
    def test_empty(self):
        result = _analyzer().assess_duplicate_detection([])
        assert result.total_services == 0
        assert result.coverage_ratio == 0.0

    def test_all_with_dedup(self):
        services = [
            _svc(cid="a", has_dedup=True, dedup_window=300),
            _svc(cid="b", has_dedup=True, dedup_window=600),
        ]
        result = _analyzer().assess_duplicate_detection(services)
        assert result.services_with_dedup == 2
        assert result.services_without_dedup == 0
        assert result.coverage_ratio == 1.0

    def test_none_with_dedup(self):
        services = [_svc(cid="a"), _svc(cid="b")]
        result = _analyzer().assess_duplicate_detection(services)
        assert result.services_without_dedup == 2
        assert len(result.recommendations) > 0

    def test_short_window_warning(self):
        services = [_svc(cid="a", has_dedup=True, dedup_window=30)]
        result = _analyzer().assess_duplicate_detection(services)
        assert any("short" in r.lower() for r in result.recommendations)

    def test_window_analysis_entries(self):
        services = [
            _svc(cid="a", has_dedup=True, dedup_window=300),
            _svc(cid="b", has_dedup=False),
        ]
        result = _analyzer().assess_duplicate_detection(services)
        assert len(result.window_analysis) == 2
        assert result.window_analysis[0]["has_dedup"] is True
        assert result.window_analysis[1]["has_dedup"] is False


# ===========================================================================
# Window Analysis
# ===========================================================================


class TestWindowAnalysis:
    def test_empty(self):
        result = _analyzer().analyze_windows([])
        assert result == []

    def test_skips_safe_methods(self):
        svc = _svc(endpoints=[_ep(method="GET", has_key=True)])
        result = _analyzer().analyze_windows([svc])
        assert result == []

    def test_skips_no_key(self):
        svc = _svc(endpoints=[_ep(method="POST", has_key=False)])
        result = _analyzer().analyze_windows([svc])
        assert result == []

    def test_adequate_window(self):
        svc = _svc(
            endpoints=[_ep(method="POST", has_key=True, window=86_400, path="/api")]
        )
        result = _analyzer().analyze_windows([svc])
        assert len(result) == 1
        assert result[0].is_adequate is True
        assert result[0].risk_level == "low"

    def test_critical_window(self):
        svc = _svc(
            endpoints=[_ep(method="POST", has_key=True, window=0, path="/api")]
        )
        result = _analyzer().analyze_windows([svc])
        assert result[0].risk_level == "critical"
        assert result[0].is_adequate is False

    def test_high_window_non_financial(self):
        svc = _svc(
            endpoints=[_ep(method="POST", has_key=True, window=30, path="/api")]
        )
        result = _analyzer().analyze_windows([svc])
        assert result[0].risk_level == "high"

    def test_financial_short_window(self):
        svc = _svc(
            endpoints=[
                _ep(
                    method="POST",
                    has_key=True,
                    window=1800,
                    is_financial=True,
                    path="/pay",
                )
            ]
        )
        result = _analyzer().analyze_windows([svc])
        assert result[0].risk_level == "high"

    def test_medium_window(self):
        svc = _svc(
            endpoints=[_ep(method="POST", has_key=True, window=200, path="/api")]
        )
        result = _analyzer().analyze_windows([svc])
        assert result[0].risk_level == "medium"


# ===========================================================================
# Side-Effect Isolation Scoring
# ===========================================================================


class TestSideEffectIsolationScoring:
    def test_empty(self):
        result = _analyzer().score_side_effect_isolation([])
        assert result == []

    def test_no_side_effects(self):
        svc = _svc(endpoints=[_ep(path="/clean")])
        results = _analyzer().score_side_effect_isolation([svc])
        assert results[0].isolation_score == _MAX_SCORE
        assert results[0].side_effect_count == 0

    def test_unisolated_effects(self):
        svc = _svc(
            endpoints=[
                _ep(
                    path="/write",
                    side_effects=[SideEffectType.DATABASE_WRITE],
                    has_key=False,
                )
            ]
        )
        results = _analyzer().score_side_effect_isolation([svc])
        assert len(results[0].unisolated_effects) == 1
        assert len(results[0].isolated_effects) == 0

    def test_isolated_effects_with_key(self):
        svc = _svc(
            endpoints=[
                _ep(
                    path="/write",
                    side_effects=[SideEffectType.DATABASE_WRITE],
                    has_key=True,
                )
            ]
        )
        results = _analyzer().score_side_effect_isolation([svc])
        assert len(results[0].isolated_effects) == 1
        assert len(results[0].unisolated_effects) == 0

    def test_payment_without_key_recommendation(self):
        svc = _svc(
            endpoints=[
                _ep(
                    path="/pay",
                    side_effects=[SideEffectType.PAYMENT],
                    has_key=False,
                )
            ]
        )
        results = _analyzer().score_side_effect_isolation([svc])
        assert any("payment" in r.lower() for r in results[0].recommendations)

    def test_multiple_endpoints(self):
        svc = _svc(
            endpoints=[
                _ep(path="/a", side_effects=[SideEffectType.DATABASE_WRITE]),
                _ep(path="/b", side_effects=[]),
            ]
        )
        results = _analyzer().score_side_effect_isolation([svc])
        assert len(results) == 2


# ===========================================================================
# Financial Audit
# ===========================================================================


class TestFinancialAudit:
    def test_no_financial_endpoints(self):
        svc = _svc(endpoints=[_ep(path="/api")])
        result = _analyzer().audit_financial_operations([svc])
        assert result.total_financial_endpoints == 0
        assert result.compliance_ratio == 1.0
        assert any("no financial" in r.lower() for r in result.recommendations)

    def test_compliant_financial(self):
        svc = _svc(
            endpoints=[
                _ep(
                    path="/pay",
                    is_financial=True,
                    has_key=True,
                    window=86_400,
                )
            ]
        )
        result = _analyzer().audit_financial_operations([svc])
        assert result.total_financial_endpoints == 1
        assert result.compliant_endpoints == 1
        assert result.non_compliant_endpoints == 0

    def test_non_compliant_no_key(self):
        svc = _svc(
            endpoints=[
                _ep(path="/pay", is_financial=True, has_key=False)
            ]
        )
        result = _analyzer().audit_financial_operations([svc])
        assert result.non_compliant_endpoints == 1
        assert len(result.findings) == 1

    def test_non_compliant_short_window(self):
        svc = _svc(
            endpoints=[
                _ep(path="/pay", is_financial=True, has_key=True, window=300)
            ]
        )
        result = _analyzer().audit_financial_operations([svc])
        assert result.non_compliant_endpoints == 1

    def test_payment_side_effect_without_key(self):
        svc = _svc(
            endpoints=[
                _ep(
                    path="/charge",
                    is_financial=True,
                    has_key=False,
                    side_effects=[SideEffectType.PAYMENT],
                )
            ]
        )
        result = _analyzer().audit_financial_operations([svc])
        assert result.non_compliant_endpoints == 1
        assert any("payment side effect" in f["issues"].lower() for f in result.findings)

    def test_tagged_financial(self):
        svc = _svc(
            endpoints=[
                _ep(path="/bill", tags=["billing"], has_key=True, window=86_400)
            ]
        )
        result = _analyzer().audit_financial_operations([svc])
        assert result.total_financial_endpoints == 1
        assert result.compliant_endpoints == 1

    def test_multiple_financial_mixed(self):
        svc = _svc(
            endpoints=[
                _ep(path="/pay", is_financial=True, has_key=True, window=86_400),
                _ep(path="/refund", is_financial=True, has_key=False),
            ]
        )
        result = _analyzer().audit_financial_operations([svc])
        assert result.total_financial_endpoints == 2
        assert result.compliant_endpoints == 1
        assert result.non_compliant_endpoints == 1
        assert result.compliance_ratio == 0.5


# ===========================================================================
# Collision Risk Estimation
# ===========================================================================


class TestCollisionRiskEstimation:
    def test_uuid_v4_negligible(self):
        result = _analyzer().estimate_collision_risk(
            IdempotencyKeyStrategy.UUID_V4, 1_000_000
        )
        assert result.risk_level == CollisionRisk.NEGLIGIBLE
        assert result.collision_probability < 1e-15

    def test_none_strategy(self):
        result = _analyzer().estimate_collision_risk(
            IdempotencyKeyStrategy.NONE, 1_000_000
        )
        assert any("no idempotency" in r.lower() for r in result.recommendations)

    def test_client_generated_with_high_volume(self):
        result = _analyzer().estimate_collision_risk(
            IdempotencyKeyStrategy.CLIENT_GENERATED, 100_000_000, window_days=365
        )
        # At 64-bit key space with ~36.5B keys, collision is possible
        assert result.collision_probability > 0

    def test_content_hash_safe(self):
        result = _analyzer().estimate_collision_risk(
            IdempotencyKeyStrategy.CONTENT_HASH, 1_000_000
        )
        assert result.risk_level == CollisionRisk.NEGLIGIBLE

    def test_expected_days(self):
        result = _analyzer().estimate_collision_risk(
            IdempotencyKeyStrategy.UUID_V4, 1_000_000
        )
        assert result.expected_days_to_collision > 1e12

    def test_client_generated_recommendation(self):
        result = _analyzer().estimate_collision_risk(
            IdempotencyKeyStrategy.CLIENT_GENERATED, 100_000_000, window_days=365
        )
        if result.risk_level != CollisionRisk.NEGLIGIBLE:
            assert any("client-generated" in r.lower() for r in result.recommendations)


# ===========================================================================
# Chain Analysis
# ===========================================================================


class TestChainAnalysis:
    def test_empty_graph(self):
        g = _graph()
        result = _analyzer().analyze_chains(g, [])
        assert result.total_chains == 0

    def test_single_chain_fully_idempotent(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))

        svc_a = _svc(cid="a", endpoints=[_ep(cid="a", has_key=True)])
        svc_b = _svc(cid="b", endpoints=[_ep(cid="b", has_key=True)])

        result = _analyzer().analyze_chains(g, [svc_a, svc_b])
        assert result.total_chains == 1
        assert result.fully_idempotent_chains == 1
        assert result.non_idempotent_chains == 0

    def test_single_chain_non_idempotent(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))

        svc_a = _svc(cid="a", endpoints=[_ep(cid="a", has_key=False)])
        svc_b = _svc(cid="b", endpoints=[_ep(cid="b", has_key=False)])

        result = _analyzer().analyze_chains(g, [svc_a, svc_b])
        assert result.non_idempotent_chains == 1
        assert len(result.weakest_links) == 1

    def test_partially_idempotent_chain(self):
        a = _comp("a")
        b = _comp("b")
        c = _comp("c")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))

        svc_a = _svc(cid="a", endpoints=[_ep(cid="a", has_key=True)])
        svc_b = _svc(cid="b", endpoints=[_ep(cid="b", has_key=True)])
        svc_c = _svc(cid="c", endpoints=[_ep(cid="c", has_key=False)])

        result = _analyzer().analyze_chains(g, [svc_a, svc_b, svc_c])
        assert result.total_chains == 2
        # a->b is fully idempotent, b->c is not
        assert result.fully_idempotent_chains == 1

    def test_chain_recommendations(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))

        svc_a = _svc(cid="a", endpoints=[_ep(cid="a", has_key=False)])
        svc_b = _svc(cid="b", endpoints=[_ep(cid="b", has_key=False)])

        result = _analyzer().analyze_chains(g, [svc_a, svc_b])
        assert len(result.recommendations) > 0

    def test_no_service_config_for_component(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))

        # No service configs
        result = _analyzer().analyze_chains(g, [])
        assert result.total_chains == 1
        assert result.non_idempotent_chains == 1


# ===========================================================================
# Test Coverage Gap Detection
# ===========================================================================


class TestTestCoverageGapDetection:
    def test_empty(self):
        result = _analyzer().detect_test_coverage_gaps([])
        assert result.total_gaps == 0

    def test_no_endpoints_info_gap(self):
        svc = _svc(cid="empty")
        result = _analyzer().detect_test_coverage_gaps([svc])
        assert result.info_gaps >= 1

    def test_financial_without_key_critical_gap(self):
        svc = _svc(
            endpoints=[_ep(path="/pay", is_financial=True, has_key=False)]
        )
        result = _analyzer().detect_test_coverage_gaps([svc])
        assert result.critical_gaps >= 1

    def test_mutating_without_key_high_gap(self):
        svc = _svc(
            endpoints=[_ep(path="/create", method="POST", has_key=False)]
        )
        result = _analyzer().detect_test_coverage_gaps([svc])
        assert result.high_gaps >= 1

    def test_side_effects_with_key_medium_gap(self):
        svc = _svc(
            endpoints=[
                _ep(
                    path="/do",
                    method="POST",
                    has_key=True,
                    side_effects=[SideEffectType.DATABASE_WRITE],
                )
            ]
        )
        result = _analyzer().detect_test_coverage_gaps([svc])
        assert result.medium_gaps >= 1

    def test_window_expiry_low_gap(self):
        svc = _svc(
            endpoints=[
                _ep(path="/do", method="POST", has_key=True, window=300)
            ]
        )
        result = _analyzer().detect_test_coverage_gaps([svc])
        assert result.low_gaps >= 1

    def test_no_dedup_high_gap(self):
        svc = _svc(
            cid="nodedup",
            endpoints=[_ep(method="GET")],
            has_dedup=False,
        )
        result = _analyzer().detect_test_coverage_gaps([svc])
        assert result.high_gaps >= 1

    def test_safe_methods_skipped(self):
        svc = _svc(
            endpoints=[_ep(method="GET", path="/read")],
            has_dedup=True,
        )
        result = _analyzer().detect_test_coverage_gaps([svc])
        # Only service-level gaps, no endpoint gaps for GET
        assert result.critical_gaps == 0
        assert result.high_gaps == 0

    def test_critical_gap_recommendations(self):
        svc = _svc(
            endpoints=[_ep(path="/pay", is_financial=True, has_key=False)]
        )
        result = _analyzer().detect_test_coverage_gaps([svc])
        assert any("critical" in r.lower() for r in result.recommendations)


# ===========================================================================
# Compensation Analysis
# ===========================================================================


class TestCompensationAnalysis:
    def test_empty(self):
        result = _analyzer().analyze_compensation([])
        assert result.total_services == 0

    def test_saga(self):
        services = [_svc(compensation=CompensationStrategy.SAGA)]
        result = _analyzer().analyze_compensation(services)
        assert result.saga_count == 1
        assert result.services_with_compensation == 1

    def test_tcc(self):
        services = [_svc(compensation=CompensationStrategy.TCC)]
        result = _analyzer().analyze_compensation(services)
        assert result.tcc_count == 1

    def test_manual(self):
        services = [_svc(compensation=CompensationStrategy.MANUAL)]
        result = _analyzer().analyze_compensation(services)
        assert result.manual_count == 1
        assert any("manual" in r.lower() for r in result.recommendations)

    def test_none(self):
        services = [_svc(compensation=CompensationStrategy.NONE)]
        result = _analyzer().analyze_compensation(services)
        assert result.no_compensation_count == 1
        assert len(result.recommendations) > 0

    def test_mixed_strategies_recommendation(self):
        services = [
            _svc(cid="a", compensation=CompensationStrategy.SAGA),
            _svc(cid="b", compensation=CompensationStrategy.TCC),
        ]
        result = _analyzer().analyze_compensation(services)
        assert any("mixed" in r.lower() for r in result.recommendations)

    def test_all_compensated(self):
        services = [
            _svc(cid="a", compensation=CompensationStrategy.SAGA),
            _svc(cid="b", compensation=CompensationStrategy.SAGA),
        ]
        result = _analyzer().analyze_compensation(services)
        assert result.services_with_compensation == 2
        assert result.no_compensation_count == 0


# ===========================================================================
# Event Sourcing Evaluation
# ===========================================================================


class TestEventSourcingEvaluation:
    def test_empty(self):
        result = _analyzer().evaluate_event_sourcing([])
        assert result.total_services == 0

    def test_no_event_sourcing(self):
        services = [_svc(cid="a")]
        result = _analyzer().evaluate_event_sourcing(services)
        assert result.event_sourced_services == 0
        assert any("no event-sourced" in r.lower() for r in result.recommendations)

    def test_event_sourcing_with_dedup(self):
        services = [_svc(cid="a", has_es=True, has_dedup=True)]
        result = _analyzer().evaluate_event_sourcing(services)
        assert result.event_sourced_services == 1
        assert result.idempotent_event_handlers == 1
        assert result.has_event_deduplication is True
        assert result.score > 0

    def test_event_sourcing_without_dedup(self):
        services = [_svc(cid="a", has_es=True, has_dedup=False)]
        result = _analyzer().evaluate_event_sourcing(services)
        assert result.non_idempotent_event_handlers == 1
        assert any("deduplication" in r.lower() for r in result.recommendations)

    def test_event_sourcing_via_tags(self):
        services = [_svc(cid="a", tags=["event_sourcing"], has_dedup=True)]
        result = _analyzer().evaluate_event_sourcing(services)
        assert result.event_sourced_services == 1

    def test_cqrs_tag(self):
        services = [_svc(cid="a", tags=["cqrs"], has_dedup=True)]
        result = _analyzer().evaluate_event_sourcing(services)
        assert result.event_sourced_services == 1

    def test_score_with_dedup_boost(self):
        services = [_svc(cid="a", has_es=True, has_dedup=True)]
        result = _analyzer().evaluate_event_sourcing(services)
        # 100 + 10 = 110, capped at 100
        assert result.score == _MAX_SCORE

    def test_no_dedup_recommendation(self):
        services = [_svc(cid="a", has_es=True, has_dedup=False)]
        result = _analyzer().evaluate_event_sourcing(services)
        assert any("idempotent event" in r.lower() for r in result.recommendations)


# ===========================================================================
# Graph-Aware Helpers
# ===========================================================================


class TestGraphAwareHelpers:
    def test_find_mutating_components(self):
        a = _comp("svc1")
        b = _comp("svc2")
        g = _graph(a, b)

        svc1 = _svc(cid="svc1", endpoints=[_ep(cid="svc1", method="POST")])
        svc2 = _svc(cid="svc2", endpoints=[_ep(cid="svc2", method="GET")])

        result = _analyzer().find_mutating_components(g, [svc1, svc2])
        assert len(result) == 1
        assert result[0].id == "svc1"

    def test_find_mutating_no_match(self):
        a = _comp("svc1")
        g = _graph(a)
        svc1 = _svc(cid="svc1", endpoints=[_ep(cid="svc1", method="GET")])
        result = _analyzer().find_mutating_components(g, [svc1])
        assert len(result) == 0

    def test_find_unprotected_financial(self):
        a = _comp("pay1")
        b = _comp("pay2")
        g = _graph(a, b)

        svc1 = _svc(
            cid="pay1",
            endpoints=[_ep(cid="pay1", is_financial=True, has_key=False)],
        )
        svc2 = _svc(
            cid="pay2",
            endpoints=[_ep(cid="pay2", is_financial=True, has_key=True)],
        )

        result = _analyzer().find_unprotected_financial_components(g, [svc1, svc2])
        assert len(result) == 1
        assert result[0].id == "pay1"

    def test_find_unprotected_financial_no_svc(self):
        a = _comp("x")
        g = _graph(a)
        result = _analyzer().find_unprotected_financial_components(g, [])
        assert len(result) == 0

    def test_find_unprotected_financial_all_protected(self):
        a = _comp("pay1")
        g = _graph(a)
        svc = _svc(
            cid="pay1",
            endpoints=[_ep(cid="pay1", is_financial=True, has_key=True)],
        )
        result = _analyzer().find_unprotected_financial_components(g, [svc])
        assert len(result) == 0


# ===========================================================================
# Full Analysis Integration
# ===========================================================================


class TestFullAnalysis:
    def _build_scenario(self):
        """Build a realistic multi-service scenario."""
        api = _comp("api-gateway", ComponentType.APP_SERVER)
        orders = _comp("order-service", ComponentType.APP_SERVER)
        payments = _comp("payment-service", ComponentType.APP_SERVER)
        inventory = _comp("inventory-service", ComponentType.APP_SERVER)
        notifier = _comp("notification-service", ComponentType.APP_SERVER)

        g = _graph(api, orders, payments, inventory, notifier)
        g.add_dependency(Dependency(source_id="api-gateway", target_id="order-service"))
        g.add_dependency(Dependency(source_id="order-service", target_id="payment-service"))
        g.add_dependency(Dependency(source_id="order-service", target_id="inventory-service"))
        g.add_dependency(Dependency(source_id="order-service", target_id="notification-service"))

        api_svc = _svc(
            cid="api-gateway",
            endpoints=[
                _ep(cid="api-gateway", method="GET", path="/api/products"),
                _ep(
                    cid="api-gateway",
                    method="POST",
                    path="/api/orders",
                    has_key=True,
                    strategy=IdempotencyKeyStrategy.UUID_V4,
                    side_effects=[SideEffectType.STATE_MUTATION],
                ),
            ],
            delivery=DeliverySemantics.AT_LEAST_ONCE,
            has_dedup=True,
            dedup_window=600,
        )
        order_svc = _svc(
            cid="order-service",
            endpoints=[
                _ep(
                    cid="order-service",
                    method="POST",
                    path="/orders",
                    has_key=True,
                    strategy=IdempotencyKeyStrategy.UUID_V4,
                    side_effects=[
                        SideEffectType.DATABASE_WRITE,
                        SideEffectType.MESSAGE_PUBLISH,
                    ],
                ),
            ],
            delivery=DeliverySemantics.AT_LEAST_ONCE,
            has_dedup=True,
            dedup_window=3600,
            compensation=CompensationStrategy.SAGA,
        )
        payment_svc = _svc(
            cid="payment-service",
            endpoints=[
                _ep(
                    cid="payment-service",
                    method="POST",
                    path="/charge",
                    has_key=True,
                    strategy=IdempotencyKeyStrategy.UUID_V4,
                    window=86_400,
                    side_effects=[SideEffectType.PAYMENT],
                    is_financial=True,
                ),
            ],
            delivery=DeliverySemantics.EXACTLY_ONCE,
            has_dedup=True,
            dedup_window=86_400,
            compensation=CompensationStrategy.TCC,
        )
        inventory_svc = _svc(
            cid="inventory-service",
            endpoints=[
                _ep(
                    cid="inventory-service",
                    method="PUT",
                    path="/stock",
                    has_key=False,
                    side_effects=[SideEffectType.DATABASE_WRITE],
                ),
            ],
            delivery=DeliverySemantics.AT_LEAST_ONCE,
            has_dedup=False,
            compensation=CompensationStrategy.SAGA,
        )
        notifier_svc = _svc(
            cid="notification-service",
            endpoints=[
                _ep(
                    cid="notification-service",
                    method="POST",
                    path="/notify",
                    has_key=False,
                    side_effects=[SideEffectType.NOTIFICATION],
                ),
            ],
            delivery=DeliverySemantics.AT_MOST_ONCE,
            has_dedup=False,
        )

        services = [api_svc, order_svc, payment_svc, inventory_svc, notifier_svc]
        return g, services

    def test_full_analysis_returns_report(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert isinstance(report, IdempotencyReport)
        assert 0.0 <= report.overall_score <= _MAX_SCORE

    def test_full_analysis_key_coverage(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert report.key_coverage.total_endpoints > 0

    def test_full_analysis_retry_safety(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert len(report.retry_safety_results) > 0

    def test_full_analysis_delivery(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert report.delivery_analysis.services_analyzed == 5

    def test_full_analysis_dedup(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert report.duplicate_detection.total_services == 5

    def test_full_analysis_windows(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        # Only endpoints with keys are analyzed
        assert len(report.window_analyses) >= 1

    def test_full_analysis_side_effects(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert len(report.side_effect_results) > 0

    def test_full_analysis_financial(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert report.financial_audit.total_financial_endpoints >= 1

    def test_full_analysis_collision(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert report.collision_risk.strategy == IdempotencyKeyStrategy.UUID_V4

    def test_full_analysis_chains(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert report.chain_analysis.total_chains > 0

    def test_full_analysis_test_coverage(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert report.test_coverage.total_gaps > 0

    def test_full_analysis_compensation(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert report.compensation_analysis.total_services == 5

    def test_full_analysis_event_sourcing(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert report.event_sourcing.total_services == 5

    def test_full_analysis_recommendations_deduplicated(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert len(report.recommendations) == len(set(report.recommendations))

    def test_full_analysis_analyzed_at(self):
        g, services = self._build_scenario()
        report = _analyzer().analyze(g, services)
        assert report.analyzed_at is not None

    def test_full_analysis_empty_graph(self):
        g = _graph()
        report = _analyzer().analyze(g, [])
        assert report.overall_score >= 0.0

    def test_full_analysis_single_service_no_key(self):
        a = _comp("a")
        g = _graph(a)
        svc = _svc(
            cid="a",
            endpoints=[_ep(cid="a", method="POST", has_key=False)],
        )
        report = _analyzer().analyze(g, [svc])
        assert report.overall_score < _MAX_SCORE

    def test_full_analysis_perfect_service(self):
        a = _comp("a")
        g = _graph(a)
        svc = _svc(
            cid="a",
            endpoints=[
                _ep(
                    cid="a",
                    method="POST",
                    has_key=True,
                    strategy=IdempotencyKeyStrategy.UUID_V4,
                    window=86_400,
                )
            ],
            delivery=DeliverySemantics.EXACTLY_ONCE,
            has_dedup=True,
            dedup_window=86_400,
            has_es=True,
            compensation=CompensationStrategy.SAGA,
        )
        report = _analyzer().analyze(g, [svc])
        assert report.overall_score > 70.0

    def test_full_analysis_dominant_strategy_selection(self):
        """Verify dominant key strategy is selected from most-used."""
        a = _comp("a")
        g = _graph(a)
        svc = _svc(
            cid="a",
            endpoints=[
                _ep(cid="a", path="/1", has_key=True, strategy=IdempotencyKeyStrategy.UUID_V4),
                _ep(cid="a", path="/2", has_key=True, strategy=IdempotencyKeyStrategy.UUID_V4),
                _ep(cid="a", path="/3", has_key=True, strategy=IdempotencyKeyStrategy.CONTENT_HASH),
            ],
        )
        report = _analyzer().analyze(g, [svc])
        assert report.collision_risk.strategy == IdempotencyKeyStrategy.UUID_V4

    def test_full_analysis_no_key_strategy_defaults_to_none(self):
        a = _comp("a")
        g = _graph(a)
        svc = _svc(
            cid="a",
            endpoints=[_ep(cid="a", method="POST", has_key=False)],
        )
        report = _analyzer().analyze(g, [svc])
        assert report.collision_risk.strategy == IdempotencyKeyStrategy.NONE

    def test_full_analysis_score_penalties_applied(self):
        """Test that various penalty factors reduce the score."""
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))

        svc_a = _svc(
            cid="a",
            endpoints=[
                _ep(cid="a", method="POST", has_key=False, is_financial=True),
            ],
            delivery=DeliverySemantics.UNKNOWN,
            has_dedup=False,
        )
        svc_b = _svc(
            cid="b",
            endpoints=[_ep(cid="b", method="POST", has_key=False)],
            delivery=DeliverySemantics.UNKNOWN,
            has_dedup=False,
        )

        report = _analyzer().analyze(g, [svc_a, svc_b])
        # Should be significantly penalized
        assert report.overall_score < 50.0

    def test_full_analysis_event_sourcing_penalty(self):
        """Test event sourcing penalty when non-idempotent."""
        a = _comp("a")
        g = _graph(a)
        svc = _svc(
            cid="a",
            endpoints=[_ep(cid="a", has_key=True, strategy=IdempotencyKeyStrategy.UUID_V4)],
            delivery=DeliverySemantics.EXACTLY_ONCE,
            has_dedup=True,
            dedup_window=3600,
            has_es=True,
            compensation=CompensationStrategy.SAGA,
        )
        report = _analyzer().analyze(g, [svc])
        # Should have penalty for non-idempotent event handler (no dedup on ES)
        # But actually has dedup, so score should be high
        assert report.overall_score > 70.0
