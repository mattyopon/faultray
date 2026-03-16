"""Webhook Delivery Resilience Analyzer.

Analyzes webhook delivery mechanisms and their resilience across distributed
infrastructure. Provides retry policy evaluation, dead letter queue
configuration analysis, payload size impact on reliability, timeout
configuration assessment, ordering guarantee analysis, deduplication
mechanism evaluation, signature verification coverage, endpoint
availability monitoring gap detection, rate limiting impact analysis,
circuit breaker evaluation, replay capability assessment, delivery SLA
compliance scoring, and fan-out delivery bottleneck detection.

Designed for commercial chaos engineering: helps teams understand how
webhook delivery failures propagate and identify optimal resilience
strategies for event-driven architectures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RetryStrategy(str, Enum):
    """Webhook retry strategies."""

    NONE = "none"
    FIXED_DELAY = "fixed_delay"
    LINEAR_BACKOFF = "linear_backoff"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    EXPONENTIAL_JITTER = "exponential_jitter"


class DeliveryStatus(str, Enum):
    """Webhook delivery status."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTERED = "dead_lettered"


class DLQMode(str, Enum):
    """Dead letter queue configuration mode."""

    NONE = "none"
    DROP = "drop"
    STORE = "store"
    ALERT_AND_STORE = "alert_and_store"
    REPLAY_QUEUE = "replay_queue"


class OrderingGuarantee(str, Enum):
    """Webhook ordering guarantee level."""

    NONE = "none"
    BEST_EFFORT = "best_effort"
    PER_RESOURCE = "per_resource"
    STRICT_FIFO = "strict_fifo"
    CAUSAL = "causal"


class DeduplicationMethod(str, Enum):
    """Webhook deduplication mechanisms."""

    NONE = "none"
    IDEMPOTENCY_KEY = "idempotency_key"
    CONTENT_HASH = "content_hash"
    EVENT_ID = "event_id"
    TIMESTAMP_WINDOW = "timestamp_window"


class SignatureAlgorithm(str, Enum):
    """Webhook signature verification algorithms."""

    NONE = "none"
    HMAC_SHA256 = "hmac_sha256"
    HMAC_SHA512 = "hmac_sha512"
    RSA_SHA256 = "rsa_sha256"
    ED25519 = "ed25519"


class CircuitBreakerState(str, Enum):
    """Circuit breaker states for webhook endpoints."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class SeverityLevel(str, Enum):
    """Severity level for findings."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BottleneckType(str, Enum):
    """Types of fan-out bottlenecks."""

    NONE = "none"
    SERIALIZATION = "serialization"
    NETWORK_BANDWIDTH = "network_bandwidth"
    ENDPOINT_CAPACITY = "endpoint_capacity"
    PAYLOAD_SIZE = "payload_size"
    RATE_LIMIT = "rate_limit"


class ReplayScope(str, Enum):
    """Scope of webhook replay capabilities."""

    NONE = "none"
    SINGLE_EVENT = "single_event"
    TIME_RANGE = "time_range"
    FULL_HISTORY = "full_history"
    SELECTIVE = "selective"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class WebhookEndpointConfig:
    """Configuration for a single webhook endpoint."""

    endpoint_id: str = ""
    url: str = ""
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    initial_retry_delay_ms: float = 1000.0
    max_retry_delay_ms: float = 60000.0
    retry_multiplier: float = 2.0
    dlq_mode: DLQMode = DLQMode.NONE
    ordering: OrderingGuarantee = OrderingGuarantee.NONE
    deduplication: DeduplicationMethod = DeduplicationMethod.NONE
    signature_algorithm: SignatureAlgorithm = SignatureAlgorithm.NONE
    max_payload_bytes: int = 1_048_576  # 1 MB default
    rate_limit_rps: float = 0.0  # 0 = unlimited
    circuit_breaker_enabled: bool = False
    circuit_breaker_threshold: int = 5
    circuit_breaker_recovery_seconds: float = 60.0
    health_check_enabled: bool = False
    health_check_interval_seconds: float = 60.0
    replay_scope: ReplayScope = ReplayScope.NONE
    sla_delivery_seconds: float = 0.0  # 0 = no SLA


@dataclass
class RetryPolicyResult:
    """Result of retry policy evaluation."""

    endpoint_id: str = ""
    strategy: RetryStrategy = RetryStrategy.NONE
    max_retries: int = 0
    total_retry_window_seconds: float = 0.0
    expected_success_rate: float = 0.0
    retry_amplification_factor: float = 1.0
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class DLQAnalysisResult:
    """Result of dead letter queue configuration analysis."""

    endpoint_id: str = ""
    dlq_mode: DLQMode = DLQMode.NONE
    has_dlq: bool = False
    has_alerting: bool = False
    has_replay: bool = False
    estimated_dlq_volume_per_day: float = 0.0
    storage_cost_per_month: float = 0.0
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PayloadSizeImpactResult:
    """Result of payload size impact analysis."""

    endpoint_id: str = ""
    max_payload_bytes: int = 0
    estimated_avg_payload_bytes: int = 0
    delivery_time_impact_ms: float = 0.0
    bandwidth_usage_mbps: float = 0.0
    compression_recommended: bool = False
    chunking_recommended: bool = False
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class TimeoutAssessmentResult:
    """Result of timeout configuration assessment."""

    endpoint_id: str = ""
    timeout_seconds: float = 0.0
    is_too_short: bool = False
    is_too_long: bool = False
    recommended_timeout_seconds: float = 0.0
    timeout_vs_sla_ratio: float = 0.0
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class OrderingAnalysisResult:
    """Result of webhook ordering guarantee analysis."""

    endpoint_id: str = ""
    ordering: OrderingGuarantee = OrderingGuarantee.NONE
    ordering_risk_score: float = 0.0
    can_handle_out_of_order: bool = False
    reordering_window_seconds: float = 0.0
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DeduplicationResult:
    """Result of deduplication mechanism evaluation."""

    endpoint_id: str = ""
    method: DeduplicationMethod = DeduplicationMethod.NONE
    has_deduplication: bool = False
    duplicate_risk_score: float = 0.0
    estimated_duplicate_rate: float = 0.0
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class SignatureVerificationResult:
    """Result of signature verification coverage analysis."""

    endpoint_id: str = ""
    algorithm: SignatureAlgorithm = SignatureAlgorithm.NONE
    has_signature: bool = False
    signature_strength_score: float = 0.0
    replay_attack_vulnerable: bool = False
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class EndpointMonitoringResult:
    """Result of endpoint availability monitoring gap detection."""

    endpoint_id: str = ""
    has_health_check: bool = False
    health_check_interval_seconds: float = 0.0
    monitoring_gap_seconds: float = 0.0
    estimated_detection_time_seconds: float = 0.0
    availability_blind_spot_percent: float = 0.0
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class RateLimitImpactResult:
    """Result of rate limiting impact analysis."""

    endpoint_id: str = ""
    rate_limit_rps: float = 0.0
    has_rate_limit: bool = False
    estimated_event_rate_rps: float = 0.0
    headroom_percent: float = 0.0
    spillover_events_per_hour: float = 0.0
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CircuitBreakerResult:
    """Result of circuit breaker evaluation."""

    endpoint_id: str = ""
    enabled: bool = False
    threshold: int = 0
    recovery_seconds: float = 0.0
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    estimated_open_frequency_per_day: float = 0.0
    mean_recovery_time_seconds: float = 0.0
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ReplayCapabilityResult:
    """Result of replay capability assessment."""

    endpoint_id: str = ""
    replay_scope: ReplayScope = ReplayScope.NONE
    has_replay: bool = False
    retention_days: int = 0
    estimated_storage_gb: float = 0.0
    recovery_time_seconds: float = 0.0
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class SLAComplianceResult:
    """Result of delivery SLA compliance scoring."""

    endpoint_id: str = ""
    sla_delivery_seconds: float = 0.0
    has_sla: bool = False
    estimated_p50_delivery_seconds: float = 0.0
    estimated_p99_delivery_seconds: float = 0.0
    compliance_score: float = 0.0
    breach_probability: float = 0.0
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class FanOutBottleneckResult:
    """Result of fan-out delivery bottleneck detection."""

    component_id: str = ""
    fan_out_count: int = 0
    bottleneck_type: BottleneckType = BottleneckType.NONE
    throughput_limit_rps: float = 0.0
    estimated_delivery_delay_ms: float = 0.0
    parallel_delivery_possible: bool = False
    severity: SeverityLevel = SeverityLevel.INFO
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class WebhookResilienceReport:
    """Full webhook resilience analysis report."""

    graph_component_count: int = 0
    endpoint_count: int = 0
    overall_resilience_score: float = 0.0
    retry_results: list[RetryPolicyResult] = field(default_factory=list)
    dlq_results: list[DLQAnalysisResult] = field(default_factory=list)
    payload_results: list[PayloadSizeImpactResult] = field(default_factory=list)
    timeout_results: list[TimeoutAssessmentResult] = field(default_factory=list)
    ordering_results: list[OrderingAnalysisResult] = field(default_factory=list)
    deduplication_results: list[DeduplicationResult] = field(default_factory=list)
    signature_results: list[SignatureVerificationResult] = field(
        default_factory=list
    )
    monitoring_results: list[EndpointMonitoringResult] = field(
        default_factory=list
    )
    rate_limit_results: list[RateLimitImpactResult] = field(default_factory=list)
    circuit_breaker_results: list[CircuitBreakerResult] = field(
        default_factory=list
    )
    replay_results: list[ReplayCapabilityResult] = field(default_factory=list)
    sla_results: list[SLAComplianceResult] = field(default_factory=list)
    fan_out_results: list[FanOutBottleneckResult] = field(default_factory=list)
    top_recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


def _severity_from_score(score: float) -> SeverityLevel:
    """Derive severity from a 0-100 score (higher = worse)."""
    if score >= 80.0:
        return SeverityLevel.CRITICAL
    if score >= 60.0:
        return SeverityLevel.HIGH
    if score >= 40.0:
        return SeverityLevel.MEDIUM
    if score >= 20.0:
        return SeverityLevel.LOW
    return SeverityLevel.INFO


def _compute_retry_window(cfg: WebhookEndpointConfig) -> float:
    """Compute total retry window in seconds for an endpoint config."""
    if cfg.max_retries <= 0:
        return 0.0
    if cfg.retry_strategy == RetryStrategy.NONE:
        return 0.0
    if cfg.retry_strategy == RetryStrategy.FIXED_DELAY:
        return cfg.max_retries * cfg.initial_retry_delay_ms / 1000.0
    if cfg.retry_strategy == RetryStrategy.LINEAR_BACKOFF:
        total_ms = 0.0
        for attempt in range(cfg.max_retries):
            delay = min(
                cfg.initial_retry_delay_ms + attempt * cfg.initial_retry_delay_ms,
                cfg.max_retry_delay_ms,
            )
            total_ms += delay
        return total_ms / 1000.0
    # exponential backoff (with or without jitter -- same total window)
    total_ms = 0.0
    for attempt in range(cfg.max_retries):
        delay = min(
            cfg.initial_retry_delay_ms * (cfg.retry_multiplier ** attempt),
            cfg.max_retry_delay_ms,
        )
        total_ms += delay
    return total_ms / 1000.0


def _estimate_success_rate(cfg: WebhookEndpointConfig) -> float:
    """Estimate the success rate given retry configuration.

    Assumes a per-attempt failure probability of 5% (typical transient
    failure rate) and calculates the probability of at least one
    successful delivery across all attempts.
    """
    per_attempt_failure = 0.05
    if cfg.retry_strategy == RetryStrategy.NONE or cfg.max_retries <= 0:
        return 1.0 - per_attempt_failure
    total_attempts = 1 + cfg.max_retries
    failure_prob = per_attempt_failure ** total_attempts
    return _clamp((1.0 - failure_prob) * 100.0, 0.0, 100.0)


def _estimate_delivery_time(
    payload_bytes: int, bandwidth_mbps: float = 100.0
) -> float:
    """Estimate delivery time in ms for a given payload size."""
    if payload_bytes <= 0:
        return 0.0
    bits = payload_bytes * 8
    mbps = bandwidth_mbps if bandwidth_mbps > 0 else 100.0
    transfer_ms = (bits / (mbps * 1_000_000)) * 1000.0
    # Add overhead: TLS handshake (~5ms) + HTTP overhead (~2ms)
    return transfer_ms + 7.0


def _signature_strength(algo: SignatureAlgorithm) -> float:
    """Return a 0-100 strength score for a signature algorithm."""
    scores: dict[SignatureAlgorithm, float] = {
        SignatureAlgorithm.NONE: 0.0,
        SignatureAlgorithm.HMAC_SHA256: 70.0,
        SignatureAlgorithm.HMAC_SHA512: 80.0,
        SignatureAlgorithm.RSA_SHA256: 85.0,
        SignatureAlgorithm.ED25519: 95.0,
    }
    return scores.get(algo, 0.0)


# ---------------------------------------------------------------------------
# Main Analyzer
# ---------------------------------------------------------------------------


class WebhookResilienceAnalyzer:
    """Analyzes webhook delivery resilience for an InfraGraph.

    Accepts an :class:`InfraGraph` and a list of
    :class:`WebhookEndpointConfig` instances and produces detailed
    analysis results across 13 resilience dimensions.
    """

    def __init__(
        self,
        graph: InfraGraph,
        endpoints: list[WebhookEndpointConfig] | None = None,
    ) -> None:
        self._graph = graph
        self._endpoints: list[WebhookEndpointConfig] = endpoints or []

    # -- public API ---------------------------------------------------------

    @property
    def graph(self) -> InfraGraph:
        return self._graph

    @property
    def endpoints(self) -> list[WebhookEndpointConfig]:
        return list(self._endpoints)

    def add_endpoint(self, cfg: WebhookEndpointConfig) -> None:
        """Register an additional webhook endpoint configuration."""
        self._endpoints.append(cfg)

    # 1. Retry policy evaluation -------------------------------------------

    def evaluate_retry_policy(
        self, cfg: WebhookEndpointConfig
    ) -> RetryPolicyResult:
        """Evaluate the retry policy for a single endpoint."""
        findings: list[str] = []
        recommendations: list[str] = []
        total_window = _compute_retry_window(cfg)
        success_rate = _estimate_success_rate(cfg)
        amplification = 1.0 + cfg.max_retries if cfg.max_retries > 0 else 1.0

        if cfg.retry_strategy == RetryStrategy.NONE:
            findings.append("No retry strategy configured.")
            recommendations.append(
                "Enable exponential backoff with jitter for transient failures."
            )
        elif cfg.retry_strategy == RetryStrategy.FIXED_DELAY:
            findings.append(
                "Fixed-delay retries risk thundering herd on recovery."
            )
            recommendations.append(
                "Switch to exponential backoff with jitter."
            )
        if cfg.max_retries > 10:
            findings.append(
                f"High retry count ({cfg.max_retries}) may cause excessive load."
            )
            recommendations.append("Reduce max retries to 3-5.")
        if cfg.max_retries > 0 and cfg.max_retry_delay_ms < 1000:
            findings.append("Max retry delay is very short (<1s).")
            recommendations.append(
                "Increase max retry delay to at least 30s."
            )
        if total_window > 3600:
            findings.append(
                f"Total retry window is {total_window:.0f}s (>1 hour)."
            )
            recommendations.append(
                "Consider moving to DLQ after a shorter retry window."
            )

        risk_score = 0.0
        if cfg.retry_strategy == RetryStrategy.NONE:
            risk_score += 40.0
        if cfg.max_retries == 0:
            risk_score += 30.0
        elif cfg.max_retries > 10:
            risk_score += 20.0
        if cfg.retry_strategy == RetryStrategy.FIXED_DELAY:
            risk_score += 15.0
        severity = _severity_from_score(risk_score)

        return RetryPolicyResult(
            endpoint_id=cfg.endpoint_id,
            strategy=cfg.retry_strategy,
            max_retries=cfg.max_retries,
            total_retry_window_seconds=total_window,
            expected_success_rate=success_rate,
            retry_amplification_factor=amplification,
            severity=severity,
            findings=findings,
            recommendations=recommendations,
        )

    def evaluate_all_retry_policies(self) -> list[RetryPolicyResult]:
        """Evaluate retry policies for all registered endpoints."""
        return [self.evaluate_retry_policy(ep) for ep in self._endpoints]

    # 2. DLQ configuration analysis ----------------------------------------

    def analyze_dlq(self, cfg: WebhookEndpointConfig) -> DLQAnalysisResult:
        """Analyze dead letter queue configuration for one endpoint."""
        findings: list[str] = []
        recommendations: list[str] = []
        has_dlq = cfg.dlq_mode != DLQMode.NONE and cfg.dlq_mode != DLQMode.DROP
        has_alert = cfg.dlq_mode == DLQMode.ALERT_AND_STORE
        has_replay = cfg.dlq_mode == DLQMode.REPLAY_QUEUE

        if cfg.dlq_mode == DLQMode.NONE:
            findings.append("No DLQ configured; failed messages are lost.")
            recommendations.append(
                "Configure a DLQ with alert_and_store mode."
            )
        elif cfg.dlq_mode == DLQMode.DROP:
            findings.append("DLQ mode is DROP; failed messages are discarded.")
            recommendations.append("Switch to store or alert_and_store mode.")
        if has_dlq and not has_alert:
            findings.append("DLQ has no alerting; failures may go unnoticed.")
            recommendations.append("Add alerting to the DLQ pipeline.")
        if has_dlq and not has_replay:
            findings.append("DLQ has no replay; manual reprocessing required.")
            recommendations.append("Enable replay_queue for automated recovery.")

        # Estimate DLQ volume: assume 0.5% failure rate, 1000 events/day
        base_rate = 1000.0
        failure_rate = 0.005
        dlq_vol = base_rate * failure_rate * (1.0 if has_dlq else 0.0)
        storage_cost = dlq_vol * 30 * 0.0001  # $0.0001 per event per month

        risk_score = 0.0
        if cfg.dlq_mode == DLQMode.NONE:
            risk_score += 50.0
        elif cfg.dlq_mode == DLQMode.DROP:
            risk_score += 35.0
        if not has_alert:
            risk_score += 15.0
        if not has_replay:
            risk_score += 10.0

        return DLQAnalysisResult(
            endpoint_id=cfg.endpoint_id,
            dlq_mode=cfg.dlq_mode,
            has_dlq=has_dlq,
            has_alerting=has_alert,
            has_replay=has_replay,
            estimated_dlq_volume_per_day=dlq_vol,
            storage_cost_per_month=round(storage_cost, 4),
            severity=_severity_from_score(risk_score),
            findings=findings,
            recommendations=recommendations,
        )

    def analyze_all_dlqs(self) -> list[DLQAnalysisResult]:
        """Analyze DLQ configuration for all endpoints."""
        return [self.analyze_dlq(ep) for ep in self._endpoints]

    # 3. Payload size impact -----------------------------------------------

    def analyze_payload_size(
        self, cfg: WebhookEndpointConfig, avg_payload_bytes: int = 0
    ) -> PayloadSizeImpactResult:
        """Analyze how payload size impacts delivery reliability."""
        findings: list[str] = []
        recommendations: list[str] = []
        avg_bytes = avg_payload_bytes if avg_payload_bytes > 0 else cfg.max_payload_bytes // 2
        delivery_ms = _estimate_delivery_time(avg_bytes)
        bandwidth = (avg_bytes * 8) / 1_000_000  # Mbps per delivery

        compress = avg_bytes > 100_000
        chunk = avg_bytes > 500_000

        if avg_bytes > cfg.max_payload_bytes:
            findings.append(
                f"Average payload ({avg_bytes}B) exceeds max ({cfg.max_payload_bytes}B)."
            )
            recommendations.append("Increase max_payload_bytes or reduce payload.")
        if avg_bytes > 500_000:
            findings.append("Payloads over 500KB increase timeout risk.")
            recommendations.append("Consider chunking large payloads.")
        if avg_bytes > 100_000:
            findings.append("Payloads over 100KB benefit from compression.")
            recommendations.append("Enable gzip/brotli compression.")
        if avg_bytes > 1_000_000:
            findings.append("Very large payloads (>1MB) have high failure risk.")

        risk_score = 0.0
        if avg_bytes > 1_000_000:
            risk_score += 40.0
        elif avg_bytes > 500_000:
            risk_score += 25.0
        elif avg_bytes > 100_000:
            risk_score += 10.0
        if avg_bytes > cfg.max_payload_bytes:
            risk_score += 30.0

        return PayloadSizeImpactResult(
            endpoint_id=cfg.endpoint_id,
            max_payload_bytes=cfg.max_payload_bytes,
            estimated_avg_payload_bytes=avg_bytes,
            delivery_time_impact_ms=round(delivery_ms, 2),
            bandwidth_usage_mbps=round(bandwidth, 4),
            compression_recommended=compress,
            chunking_recommended=chunk,
            severity=_severity_from_score(risk_score),
            findings=findings,
            recommendations=recommendations,
        )

    def analyze_all_payload_sizes(
        self, avg_payload_bytes: int = 0
    ) -> list[PayloadSizeImpactResult]:
        """Analyze payload size impact for all endpoints."""
        return [
            self.analyze_payload_size(ep, avg_payload_bytes)
            for ep in self._endpoints
        ]

    # 4. Timeout configuration assessment ----------------------------------

    def assess_timeout(
        self, cfg: WebhookEndpointConfig
    ) -> TimeoutAssessmentResult:
        """Assess webhook timeout configuration."""
        findings: list[str] = []
        recommendations: list[str] = []
        too_short = cfg.timeout_seconds < 5.0
        too_long = cfg.timeout_seconds > 120.0
        recommended = 30.0

        if too_short:
            findings.append(
                f"Timeout ({cfg.timeout_seconds}s) is too short; "
                "transient slowness will cause failures."
            )
            recommendations.append("Increase timeout to at least 10s.")
            recommended = 10.0
        elif too_long:
            findings.append(
                f"Timeout ({cfg.timeout_seconds}s) is too long; "
                "resources held during retries."
            )
            recommendations.append("Reduce timeout to 30-60s.")
            recommended = 60.0

        sla_ratio = 0.0
        if cfg.sla_delivery_seconds > 0:
            sla_ratio = cfg.timeout_seconds / cfg.sla_delivery_seconds
            if sla_ratio > 0.5:
                findings.append(
                    f"Timeout consumes {sla_ratio * 100:.0f}% of SLA budget."
                )
                recommendations.append(
                    "Keep timeout under 50% of SLA delivery target."
                )

        risk_score = 0.0
        if too_short:
            risk_score += 35.0
        if too_long:
            risk_score += 25.0
        if sla_ratio > 0.5:
            risk_score += 20.0

        return TimeoutAssessmentResult(
            endpoint_id=cfg.endpoint_id,
            timeout_seconds=cfg.timeout_seconds,
            is_too_short=too_short,
            is_too_long=too_long,
            recommended_timeout_seconds=recommended,
            timeout_vs_sla_ratio=round(sla_ratio, 3),
            severity=_severity_from_score(risk_score),
            findings=findings,
            recommendations=recommendations,
        )

    def assess_all_timeouts(self) -> list[TimeoutAssessmentResult]:
        """Assess timeout configuration for all endpoints."""
        return [self.assess_timeout(ep) for ep in self._endpoints]

    # 5. Ordering guarantee analysis ----------------------------------------

    def analyze_ordering(
        self, cfg: WebhookEndpointConfig
    ) -> OrderingAnalysisResult:
        """Analyze webhook ordering guarantees."""
        findings: list[str] = []
        recommendations: list[str] = []

        risk_score = 0.0
        can_handle_ooo = cfg.ordering in (
            OrderingGuarantee.PER_RESOURCE,
            OrderingGuarantee.STRICT_FIFO,
            OrderingGuarantee.CAUSAL,
        )
        reorder_window = 0.0

        if cfg.ordering == OrderingGuarantee.NONE:
            findings.append("No ordering guarantees; events may arrive out of order.")
            recommendations.append(
                "Use per_resource ordering or add idempotent event handling."
            )
            risk_score += 35.0
            reorder_window = _compute_retry_window(cfg) if cfg.max_retries > 0 else 10.0
        elif cfg.ordering == OrderingGuarantee.BEST_EFFORT:
            findings.append(
                "Best-effort ordering may reorder under retries or load."
            )
            recommendations.append(
                "Consider per_resource ordering for state-changing events."
            )
            risk_score += 20.0
            reorder_window = _compute_retry_window(cfg) * 0.5
        elif cfg.ordering == OrderingGuarantee.STRICT_FIFO:
            findings.append(
                "Strict FIFO ordering limits throughput under high load."
            )
            recommendations.append(
                "Consider per_resource ordering for better throughput."
            )
            risk_score += 10.0
        elif cfg.ordering == OrderingGuarantee.CAUSAL:
            findings.append("Causal ordering provides good balance of correctness and throughput.")

        return OrderingAnalysisResult(
            endpoint_id=cfg.endpoint_id,
            ordering=cfg.ordering,
            ordering_risk_score=round(_clamp(risk_score), 2),
            can_handle_out_of_order=can_handle_ooo,
            reordering_window_seconds=round(reorder_window, 2),
            severity=_severity_from_score(risk_score),
            findings=findings,
            recommendations=recommendations,
        )

    def analyze_all_ordering(self) -> list[OrderingAnalysisResult]:
        """Analyze ordering for all endpoints."""
        return [self.analyze_ordering(ep) for ep in self._endpoints]

    # 6. Deduplication mechanism evaluation --------------------------------

    def evaluate_deduplication(
        self, cfg: WebhookEndpointConfig
    ) -> DeduplicationResult:
        """Evaluate deduplication mechanism for one endpoint."""
        findings: list[str] = []
        recommendations: list[str] = []
        has_dedup = cfg.deduplication != DeduplicationMethod.NONE

        dup_risk = 0.0
        dup_rate = 0.0

        if not has_dedup:
            findings.append("No deduplication; duplicate deliveries possible.")
            recommendations.append(
                "Add idempotency_key or event_id deduplication."
            )
            dup_risk = 50.0
            dup_rate = 0.02 * (1 + cfg.max_retries)
        elif cfg.deduplication == DeduplicationMethod.TIMESTAMP_WINDOW:
            findings.append(
                "Timestamp-window dedup may miss duplicates outside window."
            )
            recommendations.append(
                "Consider event_id deduplication for stronger guarantees."
            )
            dup_risk = 25.0
            dup_rate = 0.005
        elif cfg.deduplication == DeduplicationMethod.CONTENT_HASH:
            findings.append(
                "Content-hash dedup misses identical events with different intent."
            )
            dup_risk = 15.0
            dup_rate = 0.002
        elif cfg.deduplication == DeduplicationMethod.IDEMPOTENCY_KEY:
            findings.append("Idempotency key provides strong deduplication.")
            dup_risk = 5.0
            dup_rate = 0.001
        elif cfg.deduplication == DeduplicationMethod.EVENT_ID:
            findings.append("Event ID provides reliable deduplication.")
            dup_risk = 5.0
            dup_rate = 0.001

        return DeduplicationResult(
            endpoint_id=cfg.endpoint_id,
            method=cfg.deduplication,
            has_deduplication=has_dedup,
            duplicate_risk_score=round(_clamp(dup_risk), 2),
            estimated_duplicate_rate=round(dup_rate, 4),
            severity=_severity_from_score(dup_risk),
            findings=findings,
            recommendations=recommendations,
        )

    def evaluate_all_deduplication(self) -> list[DeduplicationResult]:
        """Evaluate deduplication for all endpoints."""
        return [self.evaluate_deduplication(ep) for ep in self._endpoints]

    # 7. Signature verification coverage -----------------------------------

    def analyze_signature(
        self, cfg: WebhookEndpointConfig
    ) -> SignatureVerificationResult:
        """Analyze webhook signature verification coverage."""
        findings: list[str] = []
        recommendations: list[str] = []
        has_sig = cfg.signature_algorithm != SignatureAlgorithm.NONE
        strength = _signature_strength(cfg.signature_algorithm)
        replay_vuln = not has_sig or cfg.signature_algorithm in (
            SignatureAlgorithm.HMAC_SHA256,
            SignatureAlgorithm.HMAC_SHA512,
        )

        if not has_sig:
            findings.append("No signature verification; endpoints accept any payload.")
            recommendations.append("Add HMAC-SHA256 or ED25519 signature verification.")
        else:
            if strength < 80:
                findings.append(
                    f"Signature algorithm strength is moderate ({strength}/100)."
                )
                recommendations.append("Consider upgrading to ED25519.")
            else:
                findings.append(
                    f"Signature algorithm has strong security ({strength}/100)."
                )

        if replay_vuln:
            findings.append("Configuration is vulnerable to replay attacks.")
            recommendations.append(
                "Add timestamp validation to prevent replay attacks."
            )

        risk_score = 0.0
        if not has_sig:
            risk_score += 50.0
        elif strength < 70:
            risk_score += 20.0
        if replay_vuln:
            risk_score += 20.0

        return SignatureVerificationResult(
            endpoint_id=cfg.endpoint_id,
            algorithm=cfg.signature_algorithm,
            has_signature=has_sig,
            signature_strength_score=strength,
            replay_attack_vulnerable=replay_vuln,
            severity=_severity_from_score(risk_score),
            findings=findings,
            recommendations=recommendations,
        )

    def analyze_all_signatures(self) -> list[SignatureVerificationResult]:
        """Analyze signature verification for all endpoints."""
        return [self.analyze_signature(ep) for ep in self._endpoints]

    # 8. Endpoint availability monitoring gaps -----------------------------

    def detect_monitoring_gaps(
        self, cfg: WebhookEndpointConfig
    ) -> EndpointMonitoringResult:
        """Detect monitoring gaps for a webhook endpoint."""
        findings: list[str] = []
        recommendations: list[str] = []
        has_hc = cfg.health_check_enabled
        interval = cfg.health_check_interval_seconds if has_hc else 0.0
        gap = interval if has_hc else 300.0  # assume 5-min default gap
        detection_time = gap * 1.5 if has_hc else gap * 3.0
        blind_spot = _clamp((gap / 3600.0) * 100.0)

        if not has_hc:
            findings.append("No health check configured for endpoint.")
            recommendations.append(
                "Enable active health checks with 30s intervals."
            )
        elif interval > 120.0:
            findings.append(
                f"Health check interval ({interval}s) is too long."
            )
            recommendations.append("Reduce health check interval to 30-60s.")
        elif interval > 60.0:
            findings.append(
                f"Health check interval ({interval}s) could be shorter."
            )
            recommendations.append("Consider reducing interval to 30s.")

        risk_score = 0.0
        if not has_hc:
            risk_score += 45.0
        elif interval > 120.0:
            risk_score += 25.0
        elif interval > 60.0:
            risk_score += 10.0

        return EndpointMonitoringResult(
            endpoint_id=cfg.endpoint_id,
            has_health_check=has_hc,
            health_check_interval_seconds=interval,
            monitoring_gap_seconds=round(gap, 2),
            estimated_detection_time_seconds=round(detection_time, 2),
            availability_blind_spot_percent=round(blind_spot, 4),
            severity=_severity_from_score(risk_score),
            findings=findings,
            recommendations=recommendations,
        )

    def detect_all_monitoring_gaps(self) -> list[EndpointMonitoringResult]:
        """Detect monitoring gaps for all endpoints."""
        return [self.detect_monitoring_gaps(ep) for ep in self._endpoints]

    # 9. Rate limiting impact analysis -------------------------------------

    def analyze_rate_limiting(
        self,
        cfg: WebhookEndpointConfig,
        estimated_event_rate_rps: float = 10.0,
    ) -> RateLimitImpactResult:
        """Analyze the impact of rate limiting on webhook delivery."""
        findings: list[str] = []
        recommendations: list[str] = []
        has_rl = cfg.rate_limit_rps > 0
        headroom = 0.0
        spillover = 0.0

        if not has_rl:
            findings.append("No rate limiting configured.")
            recommendations.append(
                "Add rate limiting to protect downstream endpoints."
            )
        else:
            if estimated_event_rate_rps > 0:
                headroom = _clamp(
                    ((cfg.rate_limit_rps - estimated_event_rate_rps)
                     / cfg.rate_limit_rps) * 100.0,
                    -100.0,
                    100.0,
                )
            if headroom < 0:
                excess_rps = estimated_event_rate_rps - cfg.rate_limit_rps
                spillover = excess_rps * 3600.0
                findings.append(
                    f"Event rate ({estimated_event_rate_rps} rps) exceeds "
                    f"rate limit ({cfg.rate_limit_rps} rps)."
                )
                recommendations.append(
                    "Increase rate limit or reduce event emission rate."
                )
            elif headroom < 20.0:
                findings.append(
                    f"Rate limit headroom is low ({headroom:.1f}%)."
                )
                recommendations.append(
                    "Consider increasing rate limit by 50% for burst capacity."
                )
            else:
                findings.append(
                    f"Rate limit has adequate headroom ({headroom:.1f}%)."
                )

        risk_score = 0.0
        if not has_rl:
            risk_score += 20.0
        if headroom < 0:
            risk_score += 40.0
        elif headroom < 20.0:
            risk_score += 20.0

        return RateLimitImpactResult(
            endpoint_id=cfg.endpoint_id,
            rate_limit_rps=cfg.rate_limit_rps,
            has_rate_limit=has_rl,
            estimated_event_rate_rps=estimated_event_rate_rps,
            headroom_percent=round(headroom, 2),
            spillover_events_per_hour=round(spillover, 2),
            severity=_severity_from_score(risk_score),
            findings=findings,
            recommendations=recommendations,
        )

    def analyze_all_rate_limits(
        self, estimated_event_rate_rps: float = 10.0
    ) -> list[RateLimitImpactResult]:
        """Analyze rate limiting for all endpoints."""
        return [
            self.analyze_rate_limiting(ep, estimated_event_rate_rps)
            for ep in self._endpoints
        ]

    # 10. Circuit breaker evaluation ----------------------------------------

    def evaluate_circuit_breaker(
        self, cfg: WebhookEndpointConfig
    ) -> CircuitBreakerResult:
        """Evaluate circuit breaker configuration for an endpoint."""
        findings: list[str] = []
        recommendations: list[str] = []

        if not cfg.circuit_breaker_enabled:
            findings.append("No circuit breaker configured.")
            recommendations.append(
                "Enable circuit breaker to prevent cascading failures."
            )
        else:
            if cfg.circuit_breaker_threshold < 3:
                findings.append(
                    f"Circuit breaker threshold ({cfg.circuit_breaker_threshold}) "
                    "is too sensitive."
                )
                recommendations.append("Set threshold to at least 5.")
            elif cfg.circuit_breaker_threshold > 20:
                findings.append(
                    f"Circuit breaker threshold ({cfg.circuit_breaker_threshold}) "
                    "is too high; slow to react."
                )
                recommendations.append("Reduce threshold to 5-10.")
            if cfg.circuit_breaker_recovery_seconds < 10:
                findings.append("Recovery time is too short; may flap.")
                recommendations.append(
                    "Set recovery time to at least 30s."
                )
            elif cfg.circuit_breaker_recovery_seconds > 300:
                findings.append(
                    f"Recovery time ({cfg.circuit_breaker_recovery_seconds}s) "
                    "is very long."
                )
                recommendations.append("Reduce recovery to 30-120s.")

        # Estimate daily open frequency: assume 2 failure bursts/day
        open_freq = 0.0
        if cfg.circuit_breaker_enabled:
            open_freq = 2.0
        mean_recovery = cfg.circuit_breaker_recovery_seconds if cfg.circuit_breaker_enabled else 0.0

        risk_score = 0.0
        if not cfg.circuit_breaker_enabled:
            risk_score += 35.0
        else:
            if cfg.circuit_breaker_threshold < 3:
                risk_score += 15.0
            if cfg.circuit_breaker_threshold > 20:
                risk_score += 20.0
            if cfg.circuit_breaker_recovery_seconds < 10:
                risk_score += 15.0
            if cfg.circuit_breaker_recovery_seconds > 300:
                risk_score += 10.0

        return CircuitBreakerResult(
            endpoint_id=cfg.endpoint_id,
            enabled=cfg.circuit_breaker_enabled,
            threshold=cfg.circuit_breaker_threshold,
            recovery_seconds=cfg.circuit_breaker_recovery_seconds,
            state=CircuitBreakerState.CLOSED,
            estimated_open_frequency_per_day=open_freq,
            mean_recovery_time_seconds=mean_recovery,
            severity=_severity_from_score(risk_score),
            findings=findings,
            recommendations=recommendations,
        )

    def evaluate_all_circuit_breakers(self) -> list[CircuitBreakerResult]:
        """Evaluate circuit breakers for all endpoints."""
        return [self.evaluate_circuit_breaker(ep) for ep in self._endpoints]

    # 11. Replay capability assessment -------------------------------------

    def assess_replay(
        self,
        cfg: WebhookEndpointConfig,
        events_per_day: float = 1000.0,
        avg_event_bytes: int = 1024,
        retention_days: int = 30,
    ) -> ReplayCapabilityResult:
        """Assess replay capability for an endpoint."""
        findings: list[str] = []
        recommendations: list[str] = []
        has_replay = cfg.replay_scope != ReplayScope.NONE

        storage_gb = 0.0
        recovery_time = 0.0
        if has_replay:
            total_events = events_per_day * retention_days
            storage_gb = (total_events * avg_event_bytes) / (1024 ** 3)
            # Estimate recovery time: 100 events/sec replay throughput
            recovery_time = total_events / 100.0

        if not has_replay:
            findings.append("No replay capability; past events cannot be re-delivered.")
            recommendations.append("Implement time_range or full_history replay.")
        elif cfg.replay_scope == ReplayScope.SINGLE_EVENT:
            findings.append("Only single-event replay; bulk recovery not possible.")
            recommendations.append("Upgrade to time_range or selective replay.")
        elif cfg.replay_scope == ReplayScope.FULL_HISTORY:
            findings.append("Full history replay available; may be slow for large volumes.")
            recommendations.append(
                "Consider selective replay for targeted recovery."
            )
        elif cfg.replay_scope == ReplayScope.SELECTIVE:
            findings.append(
                "Selective replay provides targeted recovery capability."
            )
        elif cfg.replay_scope == ReplayScope.TIME_RANGE:
            findings.append(
                "Time-range replay is suitable for outage recovery."
            )

        risk_score = 0.0
        if not has_replay:
            risk_score += 40.0
        elif cfg.replay_scope == ReplayScope.SINGLE_EVENT:
            risk_score += 20.0

        return ReplayCapabilityResult(
            endpoint_id=cfg.endpoint_id,
            replay_scope=cfg.replay_scope,
            has_replay=has_replay,
            retention_days=retention_days,
            estimated_storage_gb=round(storage_gb, 4),
            recovery_time_seconds=round(recovery_time, 2),
            severity=_severity_from_score(risk_score),
            findings=findings,
            recommendations=recommendations,
        )

    def assess_all_replays(
        self,
        events_per_day: float = 1000.0,
        avg_event_bytes: int = 1024,
        retention_days: int = 30,
    ) -> list[ReplayCapabilityResult]:
        """Assess replay capabilities for all endpoints."""
        return [
            self.assess_replay(ep, events_per_day, avg_event_bytes, retention_days)
            for ep in self._endpoints
        ]

    # 12. SLA compliance scoring -------------------------------------------

    def score_sla_compliance(
        self, cfg: WebhookEndpointConfig
    ) -> SLAComplianceResult:
        """Score SLA compliance for webhook delivery."""
        findings: list[str] = []
        recommendations: list[str] = []
        has_sla = cfg.sla_delivery_seconds > 0

        p50 = 0.0
        p99 = 0.0
        compliance = 0.0
        breach_prob = 0.0

        if has_sla:
            # Estimate delivery latency components
            base_latency = 0.5  # 500ms base
            retry_latency = _compute_retry_window(cfg)
            p50 = base_latency + 0.1  # typical
            p99 = base_latency + retry_latency * 0.3  # 30% of retry window

            if p99 > cfg.sla_delivery_seconds:
                breach_prob = min(
                    1.0,
                    (p99 - cfg.sla_delivery_seconds) / cfg.sla_delivery_seconds,
                )
                findings.append(
                    f"P99 delivery ({p99:.1f}s) may exceed SLA ({cfg.sla_delivery_seconds}s)."
                )
                recommendations.append(
                    "Reduce retry delays or increase SLA target."
                )
            else:
                margin = (cfg.sla_delivery_seconds - p99) / cfg.sla_delivery_seconds
                findings.append(
                    f"SLA margin is {margin * 100:.1f}% at P99."
                )
                if margin < 0.2:
                    recommendations.append(
                        "SLA margin is thin; consider optimizing delivery path."
                    )

            compliance = _clamp(
                (1.0 - breach_prob) * 100.0, 0.0, 100.0
            )
        else:
            findings.append("No SLA defined for webhook delivery.")
            recommendations.append(
                "Define an SLA target for delivery latency."
            )

        risk_score = 0.0
        if not has_sla:
            risk_score += 25.0
        if breach_prob > 0.5:
            risk_score += 40.0
        elif breach_prob > 0.1:
            risk_score += 25.0
        elif breach_prob > 0:
            risk_score += 10.0

        return SLAComplianceResult(
            endpoint_id=cfg.endpoint_id,
            sla_delivery_seconds=cfg.sla_delivery_seconds,
            has_sla=has_sla,
            estimated_p50_delivery_seconds=round(p50, 3),
            estimated_p99_delivery_seconds=round(p99, 3),
            compliance_score=round(compliance, 2),
            breach_probability=round(breach_prob, 4),
            severity=_severity_from_score(risk_score),
            findings=findings,
            recommendations=recommendations,
        )

    def score_all_sla_compliance(self) -> list[SLAComplianceResult]:
        """Score SLA compliance for all endpoints."""
        return [self.score_sla_compliance(ep) for ep in self._endpoints]

    # 13. Fan-out delivery bottleneck detection ----------------------------

    def detect_fan_out_bottlenecks(
        self,
        component_id: str,
        payload_bytes: int = 1024,
        target_rps: float = 100.0,
    ) -> FanOutBottleneckResult:
        """Detect fan-out bottlenecks for a component sending webhooks."""
        findings: list[str] = []
        recommendations: list[str] = []
        comp = self._graph.get_component(component_id)
        if comp is None:
            return FanOutBottleneckResult(
                component_id=component_id,
                severity=SeverityLevel.INFO,
                findings=["Component not found in graph."],
            )

        dependents = self._graph.get_dependents(component_id)
        fan_out = len(dependents)
        bottleneck = BottleneckType.NONE
        throughput_limit = target_rps
        delivery_delay = 0.0

        if fan_out == 0:
            findings.append("No fan-out detected; component has no dependents.")
            return FanOutBottleneckResult(
                component_id=component_id,
                fan_out_count=0,
                bottleneck_type=BottleneckType.NONE,
                throughput_limit_rps=throughput_limit,
                severity=SeverityLevel.INFO,
                findings=findings,
            )

        total_throughput = target_rps * fan_out
        bandwidth_mbps = (payload_bytes * 8 * total_throughput) / 1_000_000
        per_delivery_ms = _estimate_delivery_time(payload_bytes)
        serial_total_ms = per_delivery_ms * fan_out

        parallel_possible = fan_out <= 50

        if fan_out > 100:
            bottleneck = BottleneckType.SERIALIZATION
            throughput_limit = target_rps / math.log2(fan_out + 1)
            findings.append(
                f"Fan-out of {fan_out} causes serialization bottleneck."
            )
            recommendations.append(
                "Use async parallel dispatch with worker pools."
            )
        elif bandwidth_mbps > 1000:
            bottleneck = BottleneckType.NETWORK_BANDWIDTH
            throughput_limit = (1000 * 1_000_000) / (payload_bytes * 8 * fan_out)
            findings.append(
                f"Bandwidth requirement ({bandwidth_mbps:.0f} Mbps) exceeds 1 Gbps."
            )
            recommendations.append("Enable payload compression or reduce fan-out.")
        elif payload_bytes > 500_000:
            bottleneck = BottleneckType.PAYLOAD_SIZE
            throughput_limit = target_rps * 0.5
            findings.append("Large payload size limits fan-out throughput.")
            recommendations.append("Reduce payload size or use reference URLs.")
        elif serial_total_ms > 1000:
            bottleneck = BottleneckType.ENDPOINT_CAPACITY
            throughput_limit = 1000.0 / serial_total_ms * target_rps
            findings.append(
                f"Serial fan-out takes {serial_total_ms:.0f}ms per batch."
            )
            recommendations.append(
                "Parallelize delivery to reduce total dispatch time."
            )

        delivery_delay = serial_total_ms if not parallel_possible else per_delivery_ms * 2

        risk_score = 0.0
        if fan_out > 100:
            risk_score += 40.0
        elif fan_out > 50:
            risk_score += 25.0
        elif fan_out > 20:
            risk_score += 10.0
        if bottleneck != BottleneckType.NONE:
            risk_score += 20.0

        return FanOutBottleneckResult(
            component_id=component_id,
            fan_out_count=fan_out,
            bottleneck_type=bottleneck,
            throughput_limit_rps=round(throughput_limit, 2),
            estimated_delivery_delay_ms=round(delivery_delay, 2),
            parallel_delivery_possible=parallel_possible,
            severity=_severity_from_score(risk_score),
            findings=findings,
            recommendations=recommendations,
        )

    def detect_all_fan_out_bottlenecks(
        self,
        payload_bytes: int = 1024,
        target_rps: float = 100.0,
    ) -> list[FanOutBottleneckResult]:
        """Detect fan-out bottlenecks for all components in the graph."""
        results: list[FanOutBottleneckResult] = []
        for cid in self._graph.components:
            results.append(
                self.detect_fan_out_bottlenecks(cid, payload_bytes, target_rps)
            )
        return results

    # -- Full report --------------------------------------------------------

    def generate_report(
        self,
        avg_payload_bytes: int = 0,
        estimated_event_rate_rps: float = 10.0,
        events_per_day: float = 1000.0,
        avg_event_bytes: int = 1024,
        retention_days: int = 30,
        fan_out_payload_bytes: int = 1024,
        fan_out_target_rps: float = 100.0,
    ) -> WebhookResilienceReport:
        """Generate a comprehensive webhook resilience report."""
        retry_results = self.evaluate_all_retry_policies()
        dlq_results = self.analyze_all_dlqs()
        payload_results = self.analyze_all_payload_sizes(avg_payload_bytes)
        timeout_results = self.assess_all_timeouts()
        ordering_results = self.analyze_all_ordering()
        dedup_results = self.evaluate_all_deduplication()
        sig_results = self.analyze_all_signatures()
        mon_results = self.detect_all_monitoring_gaps()
        rl_results = self.analyze_all_rate_limits(estimated_event_rate_rps)
        cb_results = self.evaluate_all_circuit_breakers()
        replay_results = self.assess_all_replays(
            events_per_day, avg_event_bytes, retention_days
        )
        sla_results = self.score_all_sla_compliance()
        fan_out_results = self.detect_all_fan_out_bottlenecks(
            fan_out_payload_bytes, fan_out_target_rps
        )

        # Calculate overall resilience score
        dimension_scores: list[float] = []
        for r in retry_results:
            dimension_scores.append(r.expected_success_rate)
        for d in dlq_results:
            dimension_scores.append(100.0 if d.has_dlq else 30.0)
        for s in sig_results:
            dimension_scores.append(s.signature_strength_score)
        for cb in cb_results:
            dimension_scores.append(80.0 if cb.enabled else 30.0)
        for m in mon_results:
            dimension_scores.append(
                80.0 if m.has_health_check else 20.0
            )
        for dd in dedup_results:
            dimension_scores.append(
                100.0 - dd.duplicate_risk_score
            )
        for rp in replay_results:
            dimension_scores.append(80.0 if rp.has_replay else 20.0)
        for sl in sla_results:
            dimension_scores.append(sl.compliance_score if sl.has_sla else 50.0)

        overall = 0.0
        if dimension_scores:
            overall = _clamp(
                sum(dimension_scores) / len(dimension_scores), 0.0, 100.0
            )

        # Aggregate top recommendations
        all_recs: list[str] = []
        for r in retry_results:
            all_recs.extend(r.recommendations)
        for d in dlq_results:
            all_recs.extend(d.recommendations)
        for s in sig_results:
            all_recs.extend(s.recommendations)
        for cb in cb_results:
            all_recs.extend(cb.recommendations)
        for m in mon_results:
            all_recs.extend(m.recommendations)
        # Deduplicate
        seen: set[str] = set()
        unique_recs: list[str] = []
        for rec in all_recs:
            if rec not in seen:
                seen.add(rec)
                unique_recs.append(rec)

        return WebhookResilienceReport(
            graph_component_count=len(self._graph.components),
            endpoint_count=len(self._endpoints),
            overall_resilience_score=round(overall, 2),
            retry_results=retry_results,
            dlq_results=dlq_results,
            payload_results=payload_results,
            timeout_results=timeout_results,
            ordering_results=ordering_results,
            deduplication_results=dedup_results,
            signature_results=sig_results,
            monitoring_results=mon_results,
            rate_limit_results=rl_results,
            circuit_breaker_results=cb_results,
            replay_results=replay_results,
            sla_results=sla_results,
            fan_out_results=fan_out_results,
            top_recommendations=unique_recs[:20],
        )
