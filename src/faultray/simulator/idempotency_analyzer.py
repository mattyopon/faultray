# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Idempotency Pattern Analyzer for Distributed Systems.

Analyzes idempotency guarantees across service interactions in a
distributed infrastructure graph.  Covers idempotency key coverage,
retry safety scoring, delivery semantics classification (at-most-once,
at-least-once, exactly-once), duplicate request detection capability,
idempotency window / TTL analysis, side-effect isolation scoring,
payment / financial operation auditing, idempotency key collision risk,
cross-service idempotency chain analysis, idempotency testing coverage
gap detection, compensating transaction detection, and event sourcing
idempotency evaluation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Sequence

from faultray.model.components import Component
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_SCORE: float = 100.0
_DEFAULT_IDEMPOTENCY_WINDOW_SECONDS: int = 86_400  # 24 hours
_COLLISION_BASE_RATE: float = 1e-18  # UUID v4 baseline
_FINANCIAL_COMPONENT_TAGS: frozenset[str] = frozenset(
    {"payment", "billing", "finance", "checkout", "transaction", "ledger", "invoice"}
)
_EVENT_SOURCING_TAGS: frozenset[str] = frozenset(
    {"event_sourcing", "event-sourcing", "cqrs", "event_store", "event-store"}
)
_SAFE_HTTP_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_IDEMPOTENT_HTTP_METHODS: frozenset[str] = frozenset({"PUT", "DELETE"})


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DeliverySemantics(str, Enum):
    """Message / request delivery semantics."""

    AT_MOST_ONCE = "at_most_once"
    AT_LEAST_ONCE = "at_least_once"
    EXACTLY_ONCE = "exactly_once"
    UNKNOWN = "unknown"


class RetrySafety(str, Enum):
    """Whether an operation is safe to retry."""

    SAFE = "safe"
    CONDITIONALLY_SAFE = "conditionally_safe"
    UNSAFE = "unsafe"
    UNKNOWN = "unknown"


class IdempotencyKeyStrategy(str, Enum):
    """Strategy used for generating idempotency keys."""

    UUID_V4 = "uuid_v4"
    CLIENT_GENERATED = "client_generated"
    CONTENT_HASH = "content_hash"
    COMPOSITE = "composite"
    NONE = "none"


class SideEffectType(str, Enum):
    """Types of side effects an operation may produce."""

    DATABASE_WRITE = "database_write"
    EXTERNAL_API_CALL = "external_api_call"
    MESSAGE_PUBLISH = "message_publish"
    FILE_WRITE = "file_write"
    NOTIFICATION = "notification"
    PAYMENT = "payment"
    STATE_MUTATION = "state_mutation"


class CompensationStrategy(str, Enum):
    """Strategies for compensating failed transactions."""

    SAGA = "saga"
    TCC = "tcc"  # Try-Confirm-Cancel
    MANUAL = "manual"
    NONE = "none"


class CollisionRisk(str, Enum):
    """Risk level for idempotency key collisions."""

    NEGLIGIBLE = "negligible"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CoverageGapSeverity(str, Enum):
    """Severity of an idempotency testing coverage gap."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class EndpointConfig:
    """Configuration for a single service endpoint."""

    component_id: str
    path: str = ""
    method: str = "POST"
    has_idempotency_key: bool = False
    key_strategy: IdempotencyKeyStrategy = IdempotencyKeyStrategy.NONE
    idempotency_window_seconds: int = _DEFAULT_IDEMPOTENCY_WINDOW_SECONDS
    side_effects: list[SideEffectType] = field(default_factory=list)
    is_financial: bool = False
    retry_strategy_enabled: bool = False
    max_retries: int = 0
    tags: list[str] = field(default_factory=list)


@dataclass
class ServiceConfig:
    """Configuration for a service with multiple endpoints."""

    component_id: str
    endpoints: list[EndpointConfig] = field(default_factory=list)
    delivery_semantics: DeliverySemantics = DeliverySemantics.UNKNOWN
    has_deduplication: bool = False
    deduplication_window_seconds: int = 0
    has_event_sourcing: bool = False
    compensation_strategy: CompensationStrategy = CompensationStrategy.NONE
    tags: list[str] = field(default_factory=list)


@dataclass
class KeyCoverageResult:
    """Result of idempotency key coverage analysis."""

    total_endpoints: int = 0
    covered_endpoints: int = 0
    uncovered_endpoints: int = 0
    coverage_ratio: float = 0.0
    uncovered_details: list[dict[str, str]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class RetrySafetyResult:
    """Result of retry safety scoring for an endpoint."""

    endpoint_path: str = ""
    component_id: str = ""
    safety: RetrySafety = RetrySafety.UNKNOWN
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class DeliveryAnalysis:
    """Analysis of delivery semantics across services."""

    services_analyzed: int = 0
    at_most_once_count: int = 0
    at_least_once_count: int = 0
    exactly_once_count: int = 0
    unknown_count: int = 0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DuplicateDetectionResult:
    """Assessment of duplicate request detection capabilities."""

    total_services: int = 0
    services_with_dedup: int = 0
    services_without_dedup: int = 0
    coverage_ratio: float = 0.0
    window_analysis: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class WindowAnalysis:
    """Analysis of idempotency window / TTL settings."""

    endpoint_path: str = ""
    component_id: str = ""
    window_seconds: int = 0
    is_adequate: bool = True
    risk_level: str = "low"
    recommendations: list[str] = field(default_factory=list)


@dataclass
class SideEffectIsolationResult:
    """Scoring for side-effect isolation of an endpoint."""

    endpoint_path: str = ""
    component_id: str = ""
    isolation_score: float = 0.0
    side_effect_count: int = 0
    isolated_effects: list[str] = field(default_factory=list)
    unisolated_effects: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class FinancialAuditResult:
    """Audit result for payment / financial operation idempotency."""

    total_financial_endpoints: int = 0
    compliant_endpoints: int = 0
    non_compliant_endpoints: int = 0
    compliance_ratio: float = 0.0
    findings: list[dict[str, str]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CollisionRiskResult:
    """Estimation of idempotency key collision risk."""

    strategy: IdempotencyKeyStrategy = IdempotencyKeyStrategy.NONE
    requests_per_day: int = 0
    collision_probability: float = 0.0
    risk_level: CollisionRisk = CollisionRisk.NEGLIGIBLE
    expected_days_to_collision: float = float("inf")
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ChainLink:
    """A single link in a cross-service idempotency chain."""

    source_id: str = ""
    target_id: str = ""
    has_idempotency: bool = False
    delivery_semantics: DeliverySemantics = DeliverySemantics.UNKNOWN


@dataclass
class ChainAnalysis:
    """Analysis of cross-service idempotency chains."""

    total_chains: int = 0
    fully_idempotent_chains: int = 0
    partially_idempotent_chains: int = 0
    non_idempotent_chains: int = 0
    chains: list[list[ChainLink]] = field(default_factory=list)
    weakest_links: list[ChainLink] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CoverageGap:
    """A gap in idempotency testing coverage."""

    component_id: str = ""
    description: str = ""
    severity: CoverageGapSeverity = CoverageGapSeverity.INFO
    suggested_test: str = ""


@dataclass
class TestCoverageResult:
    """Analysis of idempotency testing coverage gaps."""

    total_gaps: int = 0
    critical_gaps: int = 0
    high_gaps: int = 0
    medium_gaps: int = 0
    low_gaps: int = 0
    info_gaps: int = 0
    gaps: list[CoverageGap] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CompensationAnalysis:
    """Detection and analysis of compensating transaction patterns."""

    total_services: int = 0
    services_with_compensation: int = 0
    saga_count: int = 0
    tcc_count: int = 0
    manual_count: int = 0
    no_compensation_count: int = 0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class EventSourcingResult:
    """Evaluation of event sourcing idempotency."""

    total_services: int = 0
    event_sourced_services: int = 0
    idempotent_event_handlers: int = 0
    non_idempotent_event_handlers: int = 0
    has_event_deduplication: bool = False
    score: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class IdempotencyReport:
    """Full report from the idempotency pattern analysis."""

    overall_score: float = 0.0
    key_coverage: KeyCoverageResult = field(default_factory=KeyCoverageResult)
    retry_safety_results: list[RetrySafetyResult] = field(default_factory=list)
    delivery_analysis: DeliveryAnalysis = field(default_factory=DeliveryAnalysis)
    duplicate_detection: DuplicateDetectionResult = field(
        default_factory=DuplicateDetectionResult,
    )
    window_analyses: list[WindowAnalysis] = field(default_factory=list)
    side_effect_results: list[SideEffectIsolationResult] = field(
        default_factory=list,
    )
    financial_audit: FinancialAuditResult = field(
        default_factory=FinancialAuditResult,
    )
    collision_risk: CollisionRiskResult = field(
        default_factory=CollisionRiskResult,
    )
    chain_analysis: ChainAnalysis = field(default_factory=ChainAnalysis)
    test_coverage: TestCoverageResult = field(
        default_factory=TestCoverageResult,
    )
    compensation_analysis: CompensationAnalysis = field(
        default_factory=CompensationAnalysis,
    )
    event_sourcing: EventSourcingResult = field(
        default_factory=EventSourcingResult,
    )
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = _MAX_SCORE) -> float:
    """Clamp *value* between *lo* and *hi* inclusive."""
    return max(lo, min(hi, value))


def _is_financial_endpoint(endpoint: EndpointConfig) -> bool:
    """Determine if an endpoint handles financial operations."""
    if endpoint.is_financial:
        return True
    lower_tags = {t.lower() for t in endpoint.tags}
    return bool(lower_tags & _FINANCIAL_COMPONENT_TAGS)


def _is_safe_method(method: str) -> bool:
    """Return True if the HTTP method is inherently safe (idempotent / read-only)."""
    return method.upper() in _SAFE_HTTP_METHODS


def _is_idempotent_method(method: str) -> bool:
    """Return True if the HTTP method is idempotent by spec (PUT/DELETE)."""
    return method.upper() in _IDEMPOTENT_HTTP_METHODS


def _collision_probability(key_space_bits: int, num_keys: int) -> float:
    """Estimate collision probability using the birthday paradox approximation.

    P ~ 1 - e^(-n^2 / (2 * 2^b))
    """
    if key_space_bits <= 0 or num_keys <= 0:
        return 0.0
    exponent = -(num_keys ** 2) / (2 * (2 ** key_space_bits))
    # Guard against extremely large exponents
    if exponent < -700:
        return 0.0
    return 1.0 - math.exp(exponent)


def _key_space_bits(strategy: IdempotencyKeyStrategy) -> int:
    """Return the effective key-space in bits for a given strategy."""
    bits_map: dict[IdempotencyKeyStrategy, int] = {
        IdempotencyKeyStrategy.UUID_V4: 122,  # 128 minus 6 version bits
        IdempotencyKeyStrategy.CLIENT_GENERATED: 64,
        IdempotencyKeyStrategy.CONTENT_HASH: 256,  # SHA-256
        IdempotencyKeyStrategy.COMPOSITE: 128,
        IdempotencyKeyStrategy.NONE: 0,
    }
    return bits_map.get(strategy, 0)


def _classify_collision_risk(probability: float) -> CollisionRisk:
    """Classify collision probability into a risk level."""
    if probability <= 1e-15:
        return CollisionRisk.NEGLIGIBLE
    if probability <= 1e-9:
        return CollisionRisk.LOW
    if probability <= 1e-6:
        return CollisionRisk.MEDIUM
    if probability <= 1e-3:
        return CollisionRisk.HIGH
    return CollisionRisk.CRITICAL


def _days_to_collision(key_space_bits: int, requests_per_day: int) -> float:
    """Estimate expected number of days before a collision (50% probability)."""
    if key_space_bits <= 0 or requests_per_day <= 0:
        return float("inf")
    # n_50 ~ sqrt(2 * 2^b * ln(2)) is the number of keys for 50% collision prob.
    n_50 = math.sqrt(2 * (2 ** key_space_bits) * math.log(2))
    days = n_50 / requests_per_day
    return days


def _has_event_sourcing_tags(tags: Sequence[str]) -> bool:
    """Check if tags indicate event sourcing usage."""
    lower = {t.lower() for t in tags}
    return bool(lower & _EVENT_SOURCING_TAGS)


def _endpoint_retry_score(endpoint: EndpointConfig) -> float:
    """Compute a retry safety score (0-100) for a single endpoint."""
    score = 50.0  # baseline

    if _is_safe_method(endpoint.method):
        return _MAX_SCORE  # always safe

    if _is_idempotent_method(endpoint.method):
        score += 25.0

    if endpoint.has_idempotency_key:
        score += 30.0

    if endpoint.side_effects:
        penalty = min(30.0, len(endpoint.side_effects) * 8.0)
        score -= penalty
        if SideEffectType.PAYMENT in endpoint.side_effects:
            score -= 15.0

    if endpoint.is_financial and not endpoint.has_idempotency_key:
        score -= 20.0

    return _clamp(score)


def _window_risk_level(window_seconds: int, is_financial: bool) -> str:
    """Classify the risk level of an idempotency window."""
    if window_seconds <= 0:
        return "critical"
    if is_financial:
        if window_seconds < 3600:
            return "high"
        if window_seconds < 86_400:
            return "medium"
        return "low"
    if window_seconds < 60:
        return "high"
    if window_seconds < 300:
        return "medium"
    return "low"


def _side_effect_isolation_score(endpoint: EndpointConfig) -> float:
    """Compute an isolation score (0-100) based on side-effect management."""
    if not endpoint.side_effects:
        return _MAX_SCORE  # no side effects => perfectly isolated

    score = _MAX_SCORE
    count = len(endpoint.side_effects)

    # Each side effect reduces isolation
    score -= count * 12.0

    # Payment / external API are harder to isolate
    if SideEffectType.PAYMENT in endpoint.side_effects:
        score -= 10.0
    if SideEffectType.EXTERNAL_API_CALL in endpoint.side_effects:
        score -= 8.0

    # Having an idempotency key helps isolation
    if endpoint.has_idempotency_key:
        score += 15.0

    return _clamp(score)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class IdempotencyAnalyzer:
    """Analyzes idempotency patterns across distributed service interactions.

    This analyzer evaluates:
    * Idempotency key coverage across endpoints
    * Retry safety scoring
    * Delivery semantics classification
    * Duplicate request detection capabilities
    * Idempotency window / TTL adequacy
    * Side-effect isolation scoring
    * Payment / financial operation idempotency audit
    * Idempotency key collision risk estimation
    * Cross-service idempotency chain analysis
    * Idempotency testing coverage gap detection
    * Compensating transaction detection
    * Event sourcing idempotency evaluation
    """

    # ---- Key coverage analysis -------------------------------------------

    def analyze_key_coverage(
        self,
        services: Sequence[ServiceConfig],
    ) -> KeyCoverageResult:
        """Analyze which endpoints lack idempotency keys.

        Mutating endpoints (POST, PATCH) without idempotency keys are
        flagged.  Safe methods (GET, HEAD, OPTIONS, TRACE) are excluded
        from the analysis.
        """
        total = 0
        covered = 0
        uncovered_details: list[dict[str, str]] = []
        recs: list[str] = []

        for svc in services:
            for ep in svc.endpoints:
                if _is_safe_method(ep.method):
                    continue
                total += 1
                if ep.has_idempotency_key:
                    covered += 1
                else:
                    uncovered_details.append(
                        {
                            "component_id": ep.component_id,
                            "path": ep.path,
                            "method": ep.method,
                        }
                    )

        uncovered = total - covered
        ratio = covered / total if total > 0 else 1.0

        if uncovered > 0:
            recs.append(
                f"{uncovered} mutating endpoint(s) lack idempotency keys. "
                "Add Idempotency-Key headers or equivalent mechanisms."
            )
        if ratio < 0.5:
            recs.append(
                "Less than 50% of mutating endpoints have idempotency keys. "
                "Prioritize financial and state-changing endpoints."
            )

        return KeyCoverageResult(
            total_endpoints=total,
            covered_endpoints=covered,
            uncovered_endpoints=uncovered,
            coverage_ratio=round(ratio, 4),
            uncovered_details=uncovered_details,
            recommendations=recs,
        )

    # ---- Retry safety scoring --------------------------------------------

    def score_retry_safety(
        self,
        services: Sequence[ServiceConfig],
    ) -> list[RetrySafetyResult]:
        """Score retry safety for every endpoint across services."""
        results: list[RetrySafetyResult] = []

        for svc in services:
            for ep in svc.endpoints:
                score = _endpoint_retry_score(ep)

                if score >= 80.0:
                    safety = RetrySafety.SAFE
                elif score >= 50.0:
                    safety = RetrySafety.CONDITIONALLY_SAFE
                else:
                    safety = RetrySafety.UNSAFE

                reasons: list[str] = []
                if _is_safe_method(ep.method):
                    reasons.append(f"{ep.method} is an inherently safe method.")
                elif _is_idempotent_method(ep.method):
                    reasons.append(f"{ep.method} is idempotent by HTTP spec.")
                if ep.has_idempotency_key:
                    reasons.append("Idempotency key present.")
                else:
                    if not _is_safe_method(ep.method):
                        reasons.append("No idempotency key — retries may cause duplicates.")
                if ep.side_effects:
                    reasons.append(
                        f"Has {len(ep.side_effects)} side effect(s): "
                        f"{', '.join(e.value for e in ep.side_effects)}."
                    )
                if ep.is_financial and not ep.has_idempotency_key:
                    reasons.append(
                        "Financial endpoint without idempotency key — high risk."
                    )

                results.append(
                    RetrySafetyResult(
                        endpoint_path=ep.path,
                        component_id=ep.component_id,
                        safety=safety,
                        score=round(score, 2),
                        reasons=reasons,
                    )
                )

        return results

    # ---- Delivery semantics analysis -------------------------------------

    def analyze_delivery_semantics(
        self,
        services: Sequence[ServiceConfig],
    ) -> DeliveryAnalysis:
        """Classify delivery semantics across services."""
        counts = {
            DeliverySemantics.AT_MOST_ONCE: 0,
            DeliverySemantics.AT_LEAST_ONCE: 0,
            DeliverySemantics.EXACTLY_ONCE: 0,
            DeliverySemantics.UNKNOWN: 0,
        }

        for svc in services:
            counts[svc.delivery_semantics] += 1

        recs: list[str] = []
        if counts[DeliverySemantics.UNKNOWN] > 0:
            recs.append(
                f"{counts[DeliverySemantics.UNKNOWN]} service(s) have unknown "
                "delivery semantics. Classify them to enable proper retry strategies."
            )
        if counts[DeliverySemantics.AT_MOST_ONCE] > 0:
            recs.append(
                "At-most-once delivery risks data loss. Consider upgrading "
                "to at-least-once with idempotent consumers."
            )
        if counts[DeliverySemantics.AT_LEAST_ONCE] > 0 and counts[DeliverySemantics.EXACTLY_ONCE] == 0:
            recs.append(
                "At-least-once delivery requires idempotent consumers. "
                "Ensure deduplication is in place."
            )

        return DeliveryAnalysis(
            services_analyzed=len(services),
            at_most_once_count=counts[DeliverySemantics.AT_MOST_ONCE],
            at_least_once_count=counts[DeliverySemantics.AT_LEAST_ONCE],
            exactly_once_count=counts[DeliverySemantics.EXACTLY_ONCE],
            unknown_count=counts[DeliverySemantics.UNKNOWN],
            recommendations=recs,
        )

    # ---- Duplicate detection assessment ----------------------------------

    def assess_duplicate_detection(
        self,
        services: Sequence[ServiceConfig],
    ) -> DuplicateDetectionResult:
        """Assess duplicate request detection capability across services."""
        total = len(services)
        with_dedup = 0
        without_dedup = 0
        window_info: list[dict[str, Any]] = []
        recs: list[str] = []

        for svc in services:
            if svc.has_deduplication:
                with_dedup += 1
                window_info.append(
                    {
                        "component_id": svc.component_id,
                        "has_dedup": True,
                        "window_seconds": svc.deduplication_window_seconds,
                    }
                )
                if svc.deduplication_window_seconds < 60:
                    recs.append(
                        f"Service '{svc.component_id}' has a very short "
                        f"deduplication window ({svc.deduplication_window_seconds}s). "
                        "Consider increasing it to handle slow retries."
                    )
            else:
                without_dedup += 1
                window_info.append(
                    {
                        "component_id": svc.component_id,
                        "has_dedup": False,
                        "window_seconds": 0,
                    }
                )

        ratio = with_dedup / total if total > 0 else 0.0

        if without_dedup > 0:
            recs.append(
                f"{without_dedup} service(s) lack duplicate request detection. "
                "Implement deduplication using idempotency keys or message IDs."
            )

        return DuplicateDetectionResult(
            total_services=total,
            services_with_dedup=with_dedup,
            services_without_dedup=without_dedup,
            coverage_ratio=round(ratio, 4),
            window_analysis=window_info,
            recommendations=recs,
        )

    # ---- Idempotency window / TTL analysis -------------------------------

    def analyze_windows(
        self,
        services: Sequence[ServiceConfig],
    ) -> list[WindowAnalysis]:
        """Analyze idempotency window / TTL settings per endpoint."""
        results: list[WindowAnalysis] = []

        for svc in services:
            for ep in svc.endpoints:
                if _is_safe_method(ep.method):
                    continue
                if not ep.has_idempotency_key:
                    continue

                window = ep.idempotency_window_seconds
                is_fin = _is_financial_endpoint(ep)
                risk = _window_risk_level(window, is_fin)

                recs: list[str] = []
                adequate = risk in ("low",)

                if risk == "critical":
                    recs.append(
                        f"Endpoint '{ep.path}' has no idempotency window (0s). "
                        "This provides no protection against duplicates."
                    )
                elif risk == "high":
                    recs.append(
                        f"Endpoint '{ep.path}' has a short idempotency window "
                        f"({window}s). Increase to at least "
                        f"{'3600s' if is_fin else '300s'}."
                    )
                elif risk == "medium":
                    recs.append(
                        f"Endpoint '{ep.path}' window ({window}s) is moderate. "
                        "Consider extending for safety."
                    )

                results.append(
                    WindowAnalysis(
                        endpoint_path=ep.path,
                        component_id=ep.component_id,
                        window_seconds=window,
                        is_adequate=adequate,
                        risk_level=risk,
                        recommendations=recs,
                    )
                )

        return results

    # ---- Side-effect isolation scoring -----------------------------------

    def score_side_effect_isolation(
        self,
        services: Sequence[ServiceConfig],
    ) -> list[SideEffectIsolationResult]:
        """Score side-effect isolation for each endpoint."""
        results: list[SideEffectIsolationResult] = []

        for svc in services:
            for ep in svc.endpoints:
                score = _side_effect_isolation_score(ep)

                isolated: list[str] = []
                unisolated: list[str] = []
                recs: list[str] = []

                for se in ep.side_effects:
                    if ep.has_idempotency_key:
                        isolated.append(se.value)
                    else:
                        unisolated.append(se.value)

                if unisolated:
                    recs.append(
                        f"Endpoint '{ep.path}' has {len(unisolated)} unisolated "
                        f"side effect(s). Add idempotency key to protect against "
                        f"duplicate side effects."
                    )
                if SideEffectType.PAYMENT in ep.side_effects and not ep.has_idempotency_key:
                    recs.append(
                        f"Payment side effect on '{ep.path}' without idempotency "
                        f"key is extremely dangerous. Implement immediately."
                    )

                results.append(
                    SideEffectIsolationResult(
                        endpoint_path=ep.path,
                        component_id=ep.component_id,
                        isolation_score=round(score, 2),
                        side_effect_count=len(ep.side_effects),
                        isolated_effects=isolated,
                        unisolated_effects=unisolated,
                        recommendations=recs,
                    )
                )

        return results

    # ---- Financial / payment audit ---------------------------------------

    def audit_financial_operations(
        self,
        services: Sequence[ServiceConfig],
    ) -> FinancialAuditResult:
        """Audit idempotency of payment / financial operations."""
        total = 0
        compliant = 0
        findings: list[dict[str, str]] = []
        recs: list[str] = []

        for svc in services:
            for ep in svc.endpoints:
                if not _is_financial_endpoint(ep):
                    continue
                total += 1

                issues: list[str] = []
                if not ep.has_idempotency_key:
                    issues.append("Missing idempotency key")
                if ep.idempotency_window_seconds < 3600:
                    issues.append(
                        f"Short window ({ep.idempotency_window_seconds}s < 3600s)"
                    )
                if SideEffectType.PAYMENT in ep.side_effects and not ep.has_idempotency_key:
                    issues.append("Payment side effect without idempotency protection")

                if not issues:
                    compliant += 1
                else:
                    findings.append(
                        {
                            "component_id": ep.component_id,
                            "path": ep.path,
                            "issues": "; ".join(issues),
                        }
                    )

        non_compliant = total - compliant
        ratio = compliant / total if total > 0 else 1.0

        if non_compliant > 0:
            recs.append(
                f"{non_compliant} financial endpoint(s) are non-compliant. "
                "Financial operations MUST have idempotency keys with "
                "sufficient windows (>= 3600s)."
            )
        if total == 0:
            recs.append(
                "No financial endpoints detected. If payment operations "
                "exist, tag them appropriately for auditing."
            )

        return FinancialAuditResult(
            total_financial_endpoints=total,
            compliant_endpoints=compliant,
            non_compliant_endpoints=non_compliant,
            compliance_ratio=round(ratio, 4),
            findings=findings,
            recommendations=recs,
        )

    # ---- Collision risk estimation ---------------------------------------

    def estimate_collision_risk(
        self,
        strategy: IdempotencyKeyStrategy,
        requests_per_day: int = 1_000_000,
        window_days: int = 30,
    ) -> CollisionRiskResult:
        """Estimate the probability of idempotency key collisions."""
        bits = _key_space_bits(strategy)
        total_keys = requests_per_day * window_days
        prob = _collision_probability(bits, total_keys)
        risk = _classify_collision_risk(prob)
        days = _days_to_collision(bits, requests_per_day)

        recs: list[str] = []
        if risk in (CollisionRisk.HIGH, CollisionRisk.CRITICAL):
            recs.append(
                f"Key strategy '{strategy.value}' has high collision risk at "
                f"{requests_per_day} req/day. Switch to UUID v4 or content hash."
            )
        if strategy == IdempotencyKeyStrategy.NONE:
            recs.append(
                "No idempotency key strategy configured. "
                "Implement UUID v4 or content-hash based keys."
            )
        if strategy == IdempotencyKeyStrategy.CLIENT_GENERATED and risk != CollisionRisk.NEGLIGIBLE:
            recs.append(
                "Client-generated keys have a smaller key space. "
                "Consider server-side UUID v4 generation."
            )

        return CollisionRiskResult(
            strategy=strategy,
            requests_per_day=requests_per_day,
            collision_probability=prob,
            risk_level=risk,
            expected_days_to_collision=round(days, 2) if days != float("inf") else float("inf"),
            recommendations=recs,
        )

    # ---- Cross-service chain analysis ------------------------------------

    def analyze_chains(
        self,
        graph: InfraGraph,
        services: Sequence[ServiceConfig],
    ) -> ChainAnalysis:
        """Analyze idempotency across cross-service dependency chains.

        Walks the dependency graph to identify chains of service calls
        and checks whether idempotency is maintained at every link.
        """
        svc_map = {s.component_id: s for s in services}
        edges = graph.all_dependency_edges()

        chains: list[list[ChainLink]] = []
        weakest: list[ChainLink] = []

        # Build chains from dependency edges
        visited_pairs: set[tuple[str, str]] = set()
        for edge in edges:
            pair = (edge.source_id, edge.target_id)
            if pair in visited_pairs:
                continue
            visited_pairs.add(pair)

            src_svc = svc_map.get(edge.source_id)
            tgt_svc = svc_map.get(edge.target_id)

            src_has_idemp = False
            src_semantics = DeliverySemantics.UNKNOWN
            if src_svc:
                src_has_idemp = any(ep.has_idempotency_key for ep in src_svc.endpoints)
                src_semantics = src_svc.delivery_semantics

            tgt_has_idemp = False
            tgt_semantics = DeliverySemantics.UNKNOWN
            if tgt_svc:
                tgt_has_idemp = any(ep.has_idempotency_key for ep in tgt_svc.endpoints)
                tgt_semantics = tgt_svc.delivery_semantics

            link = ChainLink(
                source_id=edge.source_id,
                target_id=edge.target_id,
                has_idempotency=src_has_idemp and tgt_has_idemp,
                delivery_semantics=tgt_semantics if tgt_svc else src_semantics,
            )

            chains.append([link])
            if not link.has_idempotency:
                weakest.append(link)

        fully = sum(1 for c in chains if all(lnk.has_idempotency for lnk in c))
        partially = sum(
            1 for c in chains
            if any(lnk.has_idempotency for lnk in c)
            and not all(lnk.has_idempotency for lnk in c)
        )
        non_idemp = len(chains) - fully - partially

        recs: list[str] = []
        if weakest:
            recs.append(
                f"{len(weakest)} dependency link(s) lack end-to-end idempotency. "
                "Add idempotency keys to both sides of each link."
            )
        if non_idemp > 0:
            recs.append(
                f"{non_idemp} chain(s) have no idempotency at all. "
                "These are vulnerable to duplicate processing on retries."
            )

        return ChainAnalysis(
            total_chains=len(chains),
            fully_idempotent_chains=fully,
            partially_idempotent_chains=partially,
            non_idempotent_chains=non_idemp,
            chains=chains,
            weakest_links=weakest,
            recommendations=recs,
        )

    # ---- Testing coverage gaps -------------------------------------------

    def detect_test_coverage_gaps(
        self,
        services: Sequence[ServiceConfig],
    ) -> TestCoverageResult:
        """Detect gaps in idempotency testing coverage."""
        gaps: list[CoverageGap] = []

        for svc in services:
            # No endpoints at all is a gap
            if not svc.endpoints:
                gaps.append(
                    CoverageGap(
                        component_id=svc.component_id,
                        description="Service has no endpoints defined — cannot assess idempotency.",
                        severity=CoverageGapSeverity.INFO,
                        suggested_test="Define endpoints to enable idempotency analysis.",
                    )
                )
                continue

            for ep in svc.endpoints:
                if _is_safe_method(ep.method):
                    continue

                # Financial endpoint without tests
                if _is_financial_endpoint(ep) and not ep.has_idempotency_key:
                    gaps.append(
                        CoverageGap(
                            component_id=ep.component_id,
                            description=(
                                f"Financial endpoint '{ep.path}' lacks idempotency key. "
                                "No duplicate-payment test possible."
                            ),
                            severity=CoverageGapSeverity.CRITICAL,
                            suggested_test=(
                                f"Test: send duplicate {ep.method} to '{ep.path}' "
                                "and verify only one charge occurs."
                            ),
                        )
                    )

                # Mutating endpoint without idempotency key
                if not ep.has_idempotency_key and not _is_financial_endpoint(ep):
                    gaps.append(
                        CoverageGap(
                            component_id=ep.component_id,
                            description=(
                                f"Endpoint '{ep.path}' ({ep.method}) has no "
                                "idempotency key for duplicate testing."
                            ),
                            severity=CoverageGapSeverity.HIGH,
                            suggested_test=(
                                f"Test: send duplicate {ep.method} to '{ep.path}' "
                                "with same payload and verify idempotent behavior."
                            ),
                        )
                    )

                # Side effects without isolation test
                if ep.side_effects and ep.has_idempotency_key:
                    gaps.append(
                        CoverageGap(
                            component_id=ep.component_id,
                            description=(
                                f"Endpoint '{ep.path}' has {len(ep.side_effects)} "
                                "side effect(s) — verify they are not duplicated on retry."
                            ),
                            severity=CoverageGapSeverity.MEDIUM,
                            suggested_test=(
                                f"Test: replay {ep.method} '{ep.path}' with same "
                                "idempotency key and verify side effects occur once."
                            ),
                        )
                    )

                # Retry with exhausted window
                if ep.has_idempotency_key and ep.idempotency_window_seconds > 0:
                    gaps.append(
                        CoverageGap(
                            component_id=ep.component_id,
                            description=(
                                f"Endpoint '{ep.path}' window expiry test needed. "
                                f"Window is {ep.idempotency_window_seconds}s."
                            ),
                            severity=CoverageGapSeverity.LOW,
                            suggested_test=(
                                f"Test: send {ep.method} to '{ep.path}', wait past "
                                "window, resend with same key, verify new execution."
                            ),
                        )
                    )

            # Service-level deduplication test
            if not svc.has_deduplication:
                gaps.append(
                    CoverageGap(
                        component_id=svc.component_id,
                        description=(
                            f"Service '{svc.component_id}' lacks deduplication. "
                            "No duplicate-message handling test exists."
                        ),
                        severity=CoverageGapSeverity.HIGH,
                        suggested_test=(
                            "Test: publish duplicate messages and verify the "
                            "service processes each unique message exactly once."
                        ),
                    )
                )

        # Tally by severity
        severity_counts = {s: 0 for s in CoverageGapSeverity}
        for g in gaps:
            severity_counts[g.severity] += 1

        recs: list[str] = []
        if severity_counts[CoverageGapSeverity.CRITICAL] > 0:
            recs.append(
                f"{severity_counts[CoverageGapSeverity.CRITICAL]} CRITICAL "
                "testing gap(s) found. Address these immediately."
            )
        if severity_counts[CoverageGapSeverity.HIGH] > 0:
            recs.append(
                f"{severity_counts[CoverageGapSeverity.HIGH]} HIGH "
                "testing gap(s) found. Include in next sprint."
            )

        return TestCoverageResult(
            total_gaps=len(gaps),
            critical_gaps=severity_counts[CoverageGapSeverity.CRITICAL],
            high_gaps=severity_counts[CoverageGapSeverity.HIGH],
            medium_gaps=severity_counts[CoverageGapSeverity.MEDIUM],
            low_gaps=severity_counts[CoverageGapSeverity.LOW],
            info_gaps=severity_counts[CoverageGapSeverity.INFO],
            gaps=gaps,
            recommendations=recs,
        )

    # ---- Compensating transaction detection ------------------------------

    def analyze_compensation(
        self,
        services: Sequence[ServiceConfig],
    ) -> CompensationAnalysis:
        """Detect and evaluate compensating transaction patterns."""
        total = len(services)
        saga = 0
        tcc = 0
        manual = 0
        none_count = 0
        with_comp = 0

        for svc in services:
            strat = svc.compensation_strategy
            if strat == CompensationStrategy.SAGA:
                saga += 1
                with_comp += 1
            elif strat == CompensationStrategy.TCC:
                tcc += 1
                with_comp += 1
            elif strat == CompensationStrategy.MANUAL:
                manual += 1
                with_comp += 1
            else:
                none_count += 1

        recs: list[str] = []
        if none_count > 0:
            recs.append(
                f"{none_count} service(s) have no compensating transaction strategy. "
                "Implement Saga or TCC for distributed transaction safety."
            )
        if manual > 0:
            recs.append(
                f"{manual} service(s) rely on manual compensation. "
                "Automate with Saga orchestration or TCC."
            )
        if saga > 0 and tcc > 0:
            recs.append(
                "Mixed compensation strategies (Saga + TCC) detected. "
                "Ensure consistent approach within each bounded context."
            )

        return CompensationAnalysis(
            total_services=total,
            services_with_compensation=with_comp,
            saga_count=saga,
            tcc_count=tcc,
            manual_count=manual,
            no_compensation_count=none_count,
            recommendations=recs,
        )

    # ---- Event sourcing idempotency evaluation ---------------------------

    def evaluate_event_sourcing(
        self,
        services: Sequence[ServiceConfig],
    ) -> EventSourcingResult:
        """Evaluate idempotency of event-sourced services."""
        total = len(services)
        es_count = 0
        idempotent_handlers = 0
        non_idempotent_handlers = 0
        has_dedup = False

        for svc in services:
            is_es = svc.has_event_sourcing or _has_event_sourcing_tags(svc.tags)
            if not is_es:
                continue
            es_count += 1

            if svc.has_deduplication:
                has_dedup = True
                idempotent_handlers += 1
            else:
                non_idempotent_handlers += 1

        score = 0.0
        if es_count > 0:
            score = (idempotent_handlers / es_count) * _MAX_SCORE
            if has_dedup:
                score = min(_MAX_SCORE, score + 10.0)

        recs: list[str] = []
        if non_idempotent_handlers > 0:
            recs.append(
                f"{non_idempotent_handlers} event-sourced service(s) lack "
                "event deduplication. Add event ID tracking to prevent "
                "duplicate event processing."
            )
        if es_count == 0 and total > 0:
            recs.append(
                "No event-sourced services detected. Consider event sourcing "
                "for services requiring strong auditability."
            )
        if es_count > 0 and not has_dedup:
            recs.append(
                "Event-sourced services found but none have deduplication. "
                "Implement idempotent event handlers."
            )

        return EventSourcingResult(
            total_services=total,
            event_sourced_services=es_count,
            idempotent_event_handlers=idempotent_handlers,
            non_idempotent_event_handlers=non_idempotent_handlers,
            has_event_deduplication=has_dedup,
            score=round(score, 2),
            recommendations=recs,
        )

    # ---- Graph-aware helpers ---------------------------------------------

    def find_mutating_components(
        self,
        graph: InfraGraph,
        services: Sequence[ServiceConfig],
    ) -> list[Component]:
        """Return components that have mutating endpoints."""
        svc_map = {s.component_id: s for s in services}
        result: list[Component] = []
        for comp in graph.components.values():
            svc = svc_map.get(comp.id)
            if svc and any(
                not _is_safe_method(ep.method) for ep in svc.endpoints
            ):
                result.append(comp)
        return result

    def find_unprotected_financial_components(
        self,
        graph: InfraGraph,
        services: Sequence[ServiceConfig],
    ) -> list[Component]:
        """Return financial components without idempotency protection."""
        svc_map = {s.component_id: s for s in services}
        result: list[Component] = []
        for comp in graph.components.values():
            svc = svc_map.get(comp.id)
            if not svc:
                continue
            for ep in svc.endpoints:
                if _is_financial_endpoint(ep) and not ep.has_idempotency_key:
                    result.append(comp)
                    break
        return result

    # ---- Full analysis ---------------------------------------------------

    def analyze(
        self,
        graph: InfraGraph,
        services: Sequence[ServiceConfig],
        requests_per_day: int = 1_000_000,
    ) -> IdempotencyReport:
        """Run full idempotency analysis and produce a comprehensive report.

        Combines key coverage, retry safety, delivery semantics,
        duplicate detection, window analysis, side-effect isolation,
        financial audit, collision risk, chain analysis, test coverage,
        compensation detection, and event sourcing evaluation.
        """
        key_cov = self.analyze_key_coverage(services)
        retry_results = self.score_retry_safety(services)
        delivery = self.analyze_delivery_semantics(services)
        dedup = self.assess_duplicate_detection(services)
        windows = self.analyze_windows(services)
        side_effects = self.score_side_effect_isolation(services)
        financial = self.audit_financial_operations(services)

        # Determine the dominant key strategy for collision risk
        strategies_used: list[IdempotencyKeyStrategy] = []
        for svc in services:
            for ep in svc.endpoints:
                if ep.has_idempotency_key:
                    strategies_used.append(ep.key_strategy)
        dominant_strategy = (
            max(set(strategies_used), key=strategies_used.count)
            if strategies_used
            else IdempotencyKeyStrategy.NONE
        )
        collision = self.estimate_collision_risk(dominant_strategy, requests_per_day)

        chains = self.analyze_chains(graph, services)
        test_cov = self.detect_test_coverage_gaps(services)
        compensation = self.analyze_compensation(services)
        event_src = self.evaluate_event_sourcing(services)

        # ---- Overall score calculation -----------------------------------
        score = _MAX_SCORE

        # Key coverage penalty (0-25)
        score -= (1.0 - key_cov.coverage_ratio) * 25.0

        # Retry safety penalty (0-15)
        if retry_results:
            avg_retry = sum(r.score for r in retry_results) / len(retry_results)
            score -= (1.0 - avg_retry / _MAX_SCORE) * 15.0

        # Delivery semantics penalty (0-10)
        if delivery.services_analyzed > 0:
            unknown_ratio = delivery.unknown_count / delivery.services_analyzed
            score -= unknown_ratio * 10.0

        # Duplicate detection penalty (0-10)
        score -= (1.0 - dedup.coverage_ratio) * 10.0

        # Financial audit penalty (0-15)
        score -= (1.0 - financial.compliance_ratio) * 15.0

        # Chain analysis penalty (0-10)
        if chains.total_chains > 0:
            non_idemp_ratio = chains.non_idempotent_chains / chains.total_chains
            score -= non_idemp_ratio * 10.0

        # Compensation penalty (0-5)
        if compensation.total_services > 0:
            no_comp_ratio = compensation.no_compensation_count / compensation.total_services
            score -= no_comp_ratio * 5.0

        # Event sourcing penalty (0-5)
        if event_src.event_sourced_services > 0:
            score -= (1.0 - event_src.score / _MAX_SCORE) * 5.0

        # Collision risk penalty (0-5)
        collision_penalties = {
            CollisionRisk.NEGLIGIBLE: 0.0,
            CollisionRisk.LOW: 1.0,
            CollisionRisk.MEDIUM: 2.0,
            CollisionRisk.HIGH: 4.0,
            CollisionRisk.CRITICAL: 5.0,
        }
        score -= collision_penalties.get(collision.risk_level, 0.0)

        score = _clamp(score)

        # ---- Aggregate recommendations -----------------------------------
        all_recs: list[str] = []
        all_recs.extend(key_cov.recommendations)
        all_recs.extend(delivery.recommendations)
        all_recs.extend(dedup.recommendations)
        all_recs.extend(financial.recommendations)
        all_recs.extend(chains.recommendations)
        all_recs.extend(test_cov.recommendations)
        all_recs.extend(compensation.recommendations)
        all_recs.extend(event_src.recommendations)
        all_recs.extend(collision.recommendations)

        # Deduplicate
        seen: set[str] = set()
        unique_recs: list[str] = []
        for rec in all_recs:
            if rec not in seen:
                seen.add(rec)
                unique_recs.append(rec)

        return IdempotencyReport(
            overall_score=round(score, 1),
            key_coverage=key_cov,
            retry_safety_results=retry_results,
            delivery_analysis=delivery,
            duplicate_detection=dedup,
            window_analyses=windows,
            side_effect_results=side_effects,
            financial_audit=financial,
            collision_risk=collision,
            chain_analysis=chains,
            test_coverage=test_cov,
            compensation_analysis=compensation,
            event_sourcing=event_src,
            recommendations=unique_recs,
        )
