# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Database Failover Analyzer.

Analyzes database failover strategies and their reliability across various
database engines.  Covers failover timing decomposition, data-loss risk,
connection string management, read-replica promotion, split-brain prevention,
failover testing schedules, application-level retry handling, cross-region
failover, failover chain analysis, and post-failover health verification.

Designed for the FaultRay chaos engineering platform.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DatabaseType(str, Enum):
    """Supported database types."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MONGODB = "mongodb"
    REDIS = "redis"
    DYNAMODB = "dynamodb"
    CASSANDRA = "cassandra"


class FailoverStrategy(str, Enum):
    """Failover strategy."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"
    DNS_BASED = "dns_based"
    PROXY_BASED = "proxy_based"


class ProxyType(str, Enum):
    """Connection proxy type."""

    PGBOUNCER = "pgbouncer"
    PROXYSQL = "proxysql"
    HAPROXY = "haproxy"
    NONE = "none"


class SplitBrainStrategy(str, Enum):
    """Split-brain prevention strategy."""

    FENCING = "fencing"
    QUORUM = "quorum"
    WITNESS_NODE = "witness_node"
    STONITH = "stonith"
    NONE = "none"


class FailoverHealthStatus(str, Enum):
    """Post-failover health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ReplicationMode(str, Enum):
    """Replication mode."""

    SYNC = "sync"
    ASYNC = "async"
    SEMI_SYNC = "semi_sync"


class RetryBackoff(str, Enum):
    """Application retry backoff strategy."""

    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_JITTER = "exponential_jitter"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FailoverTimingBreakdown:
    """Breakdown of failover timing into components."""

    detection_time_seconds: float = 0.0
    promotion_time_seconds: float = 0.0
    dns_update_seconds: float = 0.0
    connection_reset_seconds: float = 0.0

    @property
    def total_seconds(self) -> float:
        return (
            self.detection_time_seconds
            + self.promotion_time_seconds
            + self.dns_update_seconds
            + self.connection_reset_seconds
        )


@dataclass
class DataLossRisk:
    """Data loss risk assessment during failover."""

    transactions_in_flight: int = 0
    estimated_data_loss_bytes: int = 0
    risk_score: float = 0.0  # 0-1
    replication_lag_seconds: float = 0.0
    uncommitted_wal_bytes: int = 0

    @property
    def risk_level(self) -> str:
        if self.risk_score >= 0.8:
            return "critical"
        if self.risk_score >= 0.5:
            return "high"
        if self.risk_score >= 0.2:
            return "medium"
        return "low"


@dataclass
class ConnectionStringState:
    """Connection string management state during failover."""

    primary_endpoint: str = ""
    reader_endpoint: str = ""
    requires_update: bool = False
    dns_ttl_seconds: int = 60
    connection_pool_drain_seconds: float = 5.0


@dataclass
class ReplicaPromotionAnalysis:
    """Analysis of read-replica promotion."""

    replica_id: str = ""
    replication_lag_seconds: float = 0.0
    promotion_time_seconds: float = 0.0
    data_loss_risk: float = 0.0
    is_eligible: bool = True
    ineligibility_reason: str = ""


@dataclass
class FailoverChainLink:
    """A single link in a failover chain (primary -> standby -> DR)."""

    node_id: str = ""
    role: str = "primary"  # primary, standby, dr
    region: str = ""
    priority: int = 0
    is_healthy: bool = True
    replication_lag_seconds: float = 0.0


@dataclass
class FailoverTestSchedule:
    """Failover testing schedule and automation."""

    test_frequency_days: int = 90
    last_test_date: Optional[datetime] = None
    next_test_date: Optional[datetime] = None
    automated: bool = False
    last_test_passed: bool = True
    last_test_duration_seconds: float = 0.0
    test_coverage_percent: float = 0.0


@dataclass
class AppRetryConfig:
    """Application-level failover handling configuration."""

    retry_enabled: bool = False
    max_retries: int = 3
    initial_delay_ms: float = 100.0
    max_delay_ms: float = 30000.0
    backoff: RetryBackoff = RetryBackoff.NONE
    read_after_write_consistency: bool = False
    idempotency_keys: bool = False


@dataclass
class CrossRegionConfig:
    """Cross-region database failover configuration."""

    enabled: bool = False
    primary_region: str = ""
    secondary_regions: list[str] = field(default_factory=list)
    replication_lag_ms: float = 0.0
    global_table: bool = False  # DynamoDB Global Tables
    aurora_global: bool = False  # Aurora Global Database
    rpo_seconds: float = 0.0
    rto_seconds: float = 0.0


@dataclass
class PostFailoverHealthCheck:
    """Post-failover health verification result."""

    status: FailoverHealthStatus = FailoverHealthStatus.UNKNOWN
    replication_intact: bool = False
    data_integrity_verified: bool = False
    connection_count: int = 0
    expected_connections: int = 0
    latency_ms: float = 0.0
    baseline_latency_ms: float = 0.0
    checks_passed: int = 0
    checks_total: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def health_score(self) -> float:
        if self.checks_total == 0:
            return 0.0
        return self.checks_passed / self.checks_total


@dataclass
class FailoverAnalysisResult:
    """Complete result of a database failover analysis."""

    database_type: DatabaseType = DatabaseType.POSTGRESQL
    failover_strategy: FailoverStrategy = FailoverStrategy.AUTOMATIC
    timing: FailoverTimingBreakdown = field(default_factory=FailoverTimingBreakdown)
    data_loss: DataLossRisk = field(default_factory=DataLossRisk)
    connection_state: ConnectionStringState = field(
        default_factory=ConnectionStringState
    )
    replica_promotions: list[ReplicaPromotionAnalysis] = field(default_factory=list)
    failover_chain: list[FailoverChainLink] = field(default_factory=list)
    split_brain_strategy: SplitBrainStrategy = SplitBrainStrategy.NONE
    split_brain_risk: float = 0.0
    test_schedule: FailoverTestSchedule = field(default_factory=FailoverTestSchedule)
    app_retry: AppRetryConfig = field(default_factory=AppRetryConfig)
    cross_region: CrossRegionConfig = field(default_factory=CrossRegionConfig)
    post_failover_health: PostFailoverHealthCheck = field(
        default_factory=PostFailoverHealthCheck
    )
    overall_reliability_score: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Database Failover Analyzer Configuration
# ---------------------------------------------------------------------------


@dataclass
class DatabaseFailoverConfig:
    """Configuration for a database failover analysis."""

    database_type: DatabaseType = DatabaseType.POSTGRESQL
    failover_strategy: FailoverStrategy = FailoverStrategy.AUTOMATIC
    proxy_type: ProxyType = ProxyType.NONE
    split_brain_strategy: SplitBrainStrategy = SplitBrainStrategy.NONE
    replication_mode: ReplicationMode = ReplicationMode.ASYNC
    replica_count: int = 1
    read_replica_count: int = 0
    multi_az: bool = False
    detection_interval_seconds: float = 10.0
    health_check_interval_seconds: float = 5.0
    dns_ttl_seconds: int = 60
    connection_pool_size: int = 100
    max_connections: int = 1000
    app_retry: AppRetryConfig = field(default_factory=AppRetryConfig)
    cross_region: CrossRegionConfig = field(default_factory=CrossRegionConfig)
    test_schedule: FailoverTestSchedule = field(default_factory=FailoverTestSchedule)
    failover_chain: list[FailoverChainLink] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine-specific timing profiles
# ---------------------------------------------------------------------------

_DEFAULT_TIMING: dict[DatabaseType, dict[str, float]] = {
    DatabaseType.POSTGRESQL: {
        "detection": 10.0,
        "promotion": 15.0,
        "dns_update": 5.0,
        "connection_reset": 3.0,
    },
    DatabaseType.MYSQL: {
        "detection": 10.0,
        "promotion": 20.0,
        "dns_update": 5.0,
        "connection_reset": 3.0,
    },
    DatabaseType.MONGODB: {
        "detection": 10.0,
        "promotion": 12.0,
        "dns_update": 0.0,
        "connection_reset": 2.0,
    },
    DatabaseType.REDIS: {
        "detection": 5.0,
        "promotion": 5.0,
        "dns_update": 0.0,
        "connection_reset": 1.0,
    },
    DatabaseType.DYNAMODB: {
        "detection": 0.0,
        "promotion": 0.0,
        "dns_update": 0.0,
        "connection_reset": 0.0,
    },
    DatabaseType.CASSANDRA: {
        "detection": 5.0,
        "promotion": 0.0,
        "dns_update": 0.0,
        "connection_reset": 2.0,
    },
}


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class DatabaseFailoverAnalyzer:
    """Analyzes database failover strategies and their reliability.

    Works against an ``InfraGraph`` to discover database components and
    assess the readiness and reliability of failover configurations.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, config: DatabaseFailoverConfig) -> FailoverAnalysisResult:
        """Run a full failover analysis for the given configuration."""
        timing = self._analyze_timing(config)
        data_loss = self._analyze_data_loss(config, timing)
        connection_state = self._analyze_connection_state(config)
        replica_promotions = self._analyze_replica_promotions(config)
        split_brain_risk = self._assess_split_brain_risk(config)
        post_health = self._verify_post_failover_health(config)
        cross_region = self._analyze_cross_region(config)
        reliability = self._calculate_reliability_score(
            config, timing, data_loss, split_brain_risk, post_health, cross_region
        )
        recommendations = self._build_recommendations(
            config, timing, data_loss, split_brain_risk, post_health, cross_region
        )

        return FailoverAnalysisResult(
            database_type=config.database_type,
            failover_strategy=config.failover_strategy,
            timing=timing,
            data_loss=data_loss,
            connection_state=connection_state,
            replica_promotions=replica_promotions,
            failover_chain=list(config.failover_chain),
            split_brain_strategy=config.split_brain_strategy,
            split_brain_risk=split_brain_risk,
            test_schedule=config.test_schedule,
            app_retry=config.app_retry,
            cross_region=cross_region,
            post_failover_health=post_health,
            overall_reliability_score=reliability,
            recommendations=recommendations,
            analyzed_at=datetime.now(timezone.utc),
        )

    def analyze_failover_timing(
        self, config: DatabaseFailoverConfig
    ) -> FailoverTimingBreakdown:
        """Analyze failover timing breakdown."""
        return self._analyze_timing(config)

    def assess_data_loss_risk(
        self, config: DatabaseFailoverConfig
    ) -> DataLossRisk:
        """Assess data loss risk during failover."""
        timing = self._analyze_timing(config)
        return self._analyze_data_loss(config, timing)

    def analyze_replica_promotion(
        self, config: DatabaseFailoverConfig
    ) -> list[ReplicaPromotionAnalysis]:
        """Analyze read replica promotion candidates."""
        return self._analyze_replica_promotions(config)

    def assess_split_brain_risk(
        self, config: DatabaseFailoverConfig
    ) -> float:
        """Assess split-brain risk (0-1)."""
        return self._assess_split_brain_risk(config)

    def analyze_failover_chain(
        self, chain: list[FailoverChainLink]
    ) -> dict:
        """Analyze a failover chain (primary -> standby -> DR).

        Returns a dict with chain depth, healthy node count, weakest link,
        and overall chain reliability score.
        """
        if not chain:
            return {
                "chain_depth": 0,
                "healthy_nodes": 0,
                "total_nodes": 0,
                "weakest_link": None,
                "chain_reliability": 0.0,
                "max_replication_lag_seconds": 0.0,
                "recommendations": ["No failover chain configured."],
            }

        healthy = sum(1 for link in chain if link.is_healthy)
        max_lag = max((link.replication_lag_seconds for link in chain), default=0.0)

        # Find the weakest link (highest lag among healthy, or first unhealthy)
        weakest: Optional[FailoverChainLink] = None
        for link in chain:
            if not link.is_healthy:
                weakest = link
                break
        if weakest is None:
            weakest = max(chain, key=lambda node: node.replication_lag_seconds)

        # Chain reliability: fraction of healthy nodes weighted by lag
        if len(chain) == 0:
            reliability = 0.0
        else:
            health_ratio = healthy / len(chain)
            lag_penalty = min(1.0, max_lag / 60.0)  # 60s lag = full penalty
            reliability = max(0.0, health_ratio * (1.0 - lag_penalty * 0.5))

        recs: list[str] = []
        if healthy < len(chain):
            recs.append(
                f"{len(chain) - healthy} node(s) in the failover chain are unhealthy."
            )
        if max_lag > 10.0:
            recs.append(
                f"Maximum replication lag is {max_lag:.1f}s. "
                "Consider switching to synchronous replication."
            )
        if len(chain) < 2:
            recs.append("Failover chain has only one node. Add a standby.")

        return {
            "chain_depth": len(chain),
            "healthy_nodes": healthy,
            "total_nodes": len(chain),
            "weakest_link": weakest.node_id if weakest else None,
            "chain_reliability": round(reliability, 4),
            "max_replication_lag_seconds": max_lag,
            "recommendations": recs,
        }

    def verify_post_failover_health(
        self, config: DatabaseFailoverConfig
    ) -> PostFailoverHealthCheck:
        """Run post-failover health verification."""
        return self._verify_post_failover_health(config)

    def calculate_app_retry_effectiveness(
        self, retry_config: AppRetryConfig, failover_duration_seconds: float
    ) -> dict:
        """Calculate how effective application-level retry will be during failover.

        Returns a dict with success probability, total retry time,
        and whether retries cover the failover window.
        """
        if not retry_config.retry_enabled or retry_config.max_retries <= 0:
            return {
                "success_probability": 0.0,
                "total_retry_time_ms": 0.0,
                "covers_failover_window": False,
                "retries_exhausted_before_failover": True,
                "effective_max_retries": 0,
            }

        total_time_ms = 0.0
        delays: list[float] = []

        for attempt in range(retry_config.max_retries):
            if retry_config.backoff == RetryBackoff.NONE:
                delay = 0.0
            elif retry_config.backoff == RetryBackoff.FIXED:
                delay = retry_config.initial_delay_ms
            elif retry_config.backoff in (
                RetryBackoff.EXPONENTIAL,
                RetryBackoff.EXPONENTIAL_JITTER,
            ):
                delay = min(
                    retry_config.initial_delay_ms * (2 ** attempt),
                    retry_config.max_delay_ms,
                )
            else:
                delay = retry_config.initial_delay_ms

            delays.append(delay)
            total_time_ms += delay

        failover_ms = failover_duration_seconds * 1000.0
        covers = total_time_ms >= failover_ms
        exhausted_before = total_time_ms < failover_ms

        # Success probability: if retries cover the window, high chance
        if covers:
            prob = min(1.0, 0.5 + 0.5 * (total_time_ms / max(failover_ms, 1.0)))
        else:
            prob = max(0.0, total_time_ms / max(failover_ms, 1.0)) * 0.5

        return {
            "success_probability": round(prob, 4),
            "total_retry_time_ms": round(total_time_ms, 2),
            "covers_failover_window": covers,
            "retries_exhausted_before_failover": exhausted_before,
            "effective_max_retries": retry_config.max_retries,
        }

    def find_database_components(self) -> list[Component]:
        """Find all database-type components in the graph."""
        return [
            c
            for c in self.graph.components.values()
            if c.type == ComponentType.DATABASE
        ]

    def generate_failover_report(
        self, configs: list[DatabaseFailoverConfig]
    ) -> dict:
        """Generate a comprehensive failover report across multiple configs.

        Returns a summary dict with per-config results and aggregate metrics.
        """
        results: list[FailoverAnalysisResult] = []
        for cfg in configs:
            results.append(self.analyze(cfg))

        if not results:
            return {
                "configs_analyzed": 0,
                "results": [],
                "average_reliability": 0.0,
                "worst_failover_time_seconds": 0.0,
                "worst_data_loss_risk": 0.0,
                "aggregate_recommendations": [],
            }

        avg_reliability = sum(r.overall_reliability_score for r in results) / len(
            results
        )
        worst_time = max(r.timing.total_seconds for r in results)
        worst_loss = max(r.data_loss.risk_score for r in results)

        # Collect unique recommendations
        all_recs: list[str] = []
        seen: set[str] = set()
        for r in results:
            for rec in r.recommendations:
                if rec not in seen:
                    seen.add(rec)
                    all_recs.append(rec)

        return {
            "configs_analyzed": len(configs),
            "results": results,
            "average_reliability": round(avg_reliability, 4),
            "worst_failover_time_seconds": round(worst_time, 2),
            "worst_data_loss_risk": round(worst_loss, 4),
            "aggregate_recommendations": all_recs,
        }

    def evaluate_failover_test_readiness(
        self, schedule: FailoverTestSchedule
    ) -> dict:
        """Evaluate whether the failover testing schedule is adequate.

        Returns readiness assessment dict.
        """
        issues: list[str] = []
        score = 100.0

        if schedule.test_frequency_days > 180:
            score -= 30.0
            issues.append(
                "Failover testing frequency exceeds 180 days. "
                "Consider testing at least quarterly."
            )
        elif schedule.test_frequency_days > 90:
            score -= 15.0
            issues.append(
                "Failover testing frequency exceeds 90 days. "
                "Consider monthly testing."
            )

        if not schedule.automated:
            score -= 20.0
            issues.append("Failover testing is not automated. Automate testing.")

        if not schedule.last_test_passed:
            score -= 30.0
            issues.append(
                "Last failover test failed. Investigate and resolve before next test."
            )

        if schedule.test_coverage_percent < 50.0:
            score -= 20.0
            issues.append(
                f"Test coverage is {schedule.test_coverage_percent:.0f}%. "
                "Aim for at least 80% coverage."
            )
        elif schedule.test_coverage_percent < 80.0:
            score -= 10.0
            issues.append(
                f"Test coverage is {schedule.test_coverage_percent:.0f}%. "
                "Consider increasing to 80%+."
            )

        if schedule.last_test_date is not None:
            now = datetime.now(timezone.utc)
            days_since = (now - schedule.last_test_date).days
            if days_since > schedule.test_frequency_days:
                score -= 15.0
                issues.append(
                    f"Last test was {days_since} days ago, "
                    f"exceeding the {schedule.test_frequency_days}-day schedule."
                )

        return {
            "readiness_score": max(0.0, min(100.0, score)),
            "issues": issues,
            "automated": schedule.automated,
            "last_test_passed": schedule.last_test_passed,
            "test_coverage_percent": schedule.test_coverage_percent,
        }

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    def _analyze_timing(
        self, config: DatabaseFailoverConfig
    ) -> FailoverTimingBreakdown:
        """Calculate failover timing breakdown."""
        base = _DEFAULT_TIMING.get(
            config.database_type,
            {"detection": 10.0, "promotion": 15.0, "dns_update": 5.0, "connection_reset": 3.0},
        )

        detection = base["detection"]
        promotion = base["promotion"]
        dns_update = base["dns_update"]
        conn_reset = base["connection_reset"]

        # Strategy adjustments
        if config.failover_strategy == FailoverStrategy.AUTOMATIC:
            detection *= 0.5  # faster detection with auto-monitoring
        elif config.failover_strategy == FailoverStrategy.MANUAL:
            detection *= 5.0  # manual detection is much slower
            promotion *= 2.0

        if config.failover_strategy == FailoverStrategy.DNS_BASED:
            dns_update = max(dns_update, config.dns_ttl_seconds * 0.5)

        if config.failover_strategy == FailoverStrategy.PROXY_BASED:
            dns_update = 0.0
            if config.proxy_type in (ProxyType.PGBOUNCER, ProxyType.PROXYSQL):
                conn_reset *= 0.3  # proxies handle connection pooling

        # Multi-AZ reduces promotion time
        if config.multi_az:
            promotion *= 0.5

        # Replication mode affects promotion
        if config.replication_mode == ReplicationMode.SYNC:
            promotion *= 0.7  # replica is up-to-date, faster promotion
        elif config.replication_mode == ReplicationMode.SEMI_SYNC:
            promotion *= 0.85

        # Custom detection interval
        detection = max(detection, config.detection_interval_seconds * 0.5)

        return FailoverTimingBreakdown(
            detection_time_seconds=round(detection, 2),
            promotion_time_seconds=round(promotion, 2),
            dns_update_seconds=round(dns_update, 2),
            connection_reset_seconds=round(conn_reset, 2),
        )

    def _analyze_data_loss(
        self,
        config: DatabaseFailoverConfig,
        timing: FailoverTimingBreakdown,
    ) -> DataLossRisk:
        """Assess data loss risk."""
        # DynamoDB and Cassandra are inherently distributed
        if config.database_type in (DatabaseType.DYNAMODB, DatabaseType.CASSANDRA):
            return DataLossRisk(
                transactions_in_flight=0,
                estimated_data_loss_bytes=0,
                risk_score=0.0,
                replication_lag_seconds=0.0,
                uncommitted_wal_bytes=0,
            )

        risk = 0.0
        lag = 0.0
        txns = 0
        wal_bytes = 0

        if config.replication_mode == ReplicationMode.ASYNC:
            risk += 0.5
            lag = 2.0  # typical async lag
            txns = int(config.max_connections * 0.1)
            wal_bytes = int(lag * 1024 * 1024)  # ~1MB/s WAL
        elif config.replication_mode == ReplicationMode.SEMI_SYNC:
            risk += 0.2
            lag = 0.5
            txns = int(config.max_connections * 0.02)
            wal_bytes = int(lag * 512 * 1024)
        else:
            risk += 0.0
            lag = 0.0
            txns = 0
            wal_bytes = 0

        # No replicas means high risk
        if config.replica_count <= 1 and config.read_replica_count == 0:
            risk += 0.3

        # Manual failover increases risk due to longer window
        if config.failover_strategy == FailoverStrategy.MANUAL:
            risk += 0.2
            txns = int(txns * 2)

        risk = min(1.0, risk)
        data_loss_bytes = int(wal_bytes * risk)

        return DataLossRisk(
            transactions_in_flight=txns,
            estimated_data_loss_bytes=data_loss_bytes,
            risk_score=round(risk, 4),
            replication_lag_seconds=lag,
            uncommitted_wal_bytes=wal_bytes,
        )

    def _analyze_connection_state(
        self, config: DatabaseFailoverConfig
    ) -> ConnectionStringState:
        """Analyze connection string management during failover."""
        requires_update = True

        if config.failover_strategy == FailoverStrategy.PROXY_BASED:
            requires_update = False
        elif config.failover_strategy == FailoverStrategy.DNS_BASED:
            requires_update = False  # DNS handles it
        elif config.failover_strategy == FailoverStrategy.AUTOMATIC:
            # Some managed services (DynamoDB) don't need updates
            if config.database_type == DatabaseType.DYNAMODB:
                requires_update = False

        drain = 5.0
        if config.proxy_type in (ProxyType.PGBOUNCER, ProxyType.PROXYSQL):
            drain = 1.0

        return ConnectionStringState(
            primary_endpoint=f"{config.database_type.value}-primary:5432",
            reader_endpoint=f"{config.database_type.value}-reader:5432",
            requires_update=requires_update,
            dns_ttl_seconds=config.dns_ttl_seconds,
            connection_pool_drain_seconds=drain,
        )

    def _analyze_replica_promotions(
        self, config: DatabaseFailoverConfig
    ) -> list[ReplicaPromotionAnalysis]:
        """Analyze which replicas can be promoted."""
        promotions: list[ReplicaPromotionAnalysis] = []

        total_replicas = config.replica_count + config.read_replica_count

        if total_replicas <= 1:
            # No replicas to promote
            return [
                ReplicaPromotionAnalysis(
                    replica_id="none",
                    replication_lag_seconds=0.0,
                    promotion_time_seconds=0.0,
                    data_loss_risk=1.0,
                    is_eligible=False,
                    ineligibility_reason="No replicas available for promotion.",
                )
            ]

        base_timing = _DEFAULT_TIMING.get(
            config.database_type,
            {"promotion": 15.0},
        )
        base_promotion = base_timing.get("promotion", 15.0)

        for i in range(total_replicas - 1):
            rid = f"replica-{i + 1}"
            # Simulate varying replication lag
            lag = 0.0 if config.replication_mode == ReplicationMode.SYNC else (i + 1) * 0.5

            eligible = True
            reason = ""
            loss_risk = 0.0

            if config.replication_mode == ReplicationMode.ASYNC and lag > 5.0:
                eligible = False
                reason = f"Replication lag {lag:.1f}s exceeds threshold."
                loss_risk = min(1.0, lag / 10.0)
            elif config.replication_mode == ReplicationMode.ASYNC:
                loss_risk = min(1.0, lag / 10.0)

            ptime = base_promotion
            if config.multi_az:
                ptime *= 0.5

            promotions.append(
                ReplicaPromotionAnalysis(
                    replica_id=rid,
                    replication_lag_seconds=lag,
                    promotion_time_seconds=round(ptime, 2),
                    data_loss_risk=round(loss_risk, 4),
                    is_eligible=eligible,
                    ineligibility_reason=reason,
                )
            )

        return promotions

    def _assess_split_brain_risk(
        self, config: DatabaseFailoverConfig
    ) -> float:
        """Calculate split-brain risk score (0-1)."""
        # Managed services with no split-brain possibility
        if config.database_type in (DatabaseType.DYNAMODB,):
            return 0.0

        risk = 0.0

        if config.split_brain_strategy == SplitBrainStrategy.NONE:
            risk += 0.6
        elif config.split_brain_strategy == SplitBrainStrategy.FENCING:
            risk += 0.1
        elif config.split_brain_strategy == SplitBrainStrategy.QUORUM:
            risk += 0.05
        elif config.split_brain_strategy == SplitBrainStrategy.WITNESS_NODE:
            risk += 0.08
        elif config.split_brain_strategy == SplitBrainStrategy.STONITH:
            risk += 0.03

        # Async replication increases risk
        if config.replication_mode == ReplicationMode.ASYNC:
            risk += 0.2
        elif config.replication_mode == ReplicationMode.SEMI_SYNC:
            risk += 0.1

        # No multi-AZ increases risk
        if not config.multi_az:
            risk += 0.1

        # More replicas = more potential for split-brain
        if config.replica_count > 3:
            risk += 0.05

        # Cross-region increases risk
        if config.cross_region.enabled:
            risk += 0.1

        return min(1.0, round(risk, 4))

    def _verify_post_failover_health(
        self, config: DatabaseFailoverConfig
    ) -> PostFailoverHealthCheck:
        """Simulate post-failover health verification."""
        checks_total = 6
        checks_passed = 0
        issues: list[str] = []

        # Check 1: Replication intact
        replication_intact = config.replica_count > 1 or config.read_replica_count > 0
        if replication_intact:
            checks_passed += 1
        else:
            issues.append("No replication available after failover.")

        # Check 2: Data integrity
        data_integrity = config.replication_mode in (
            ReplicationMode.SYNC,
            ReplicationMode.SEMI_SYNC,
        )
        if data_integrity:
            checks_passed += 1
        else:
            issues.append("Async replication may have data integrity gaps.")

        # Check 3: Connection count
        expected = config.connection_pool_size
        actual = int(expected * 0.8)  # simulate 80% reconnection
        if actual >= expected * 0.7:
            checks_passed += 1
        else:
            issues.append(
                f"Only {actual}/{expected} connections re-established."
            )

        # Check 4: Latency check
        baseline_latency = 5.0
        post_latency = baseline_latency * 1.5  # failover adds latency
        if config.proxy_type in (ProxyType.PGBOUNCER, ProxyType.PROXYSQL):
            post_latency = baseline_latency * 1.1  # proxies minimize impact
        if post_latency < baseline_latency * 2.0:
            checks_passed += 1
        else:
            issues.append("Post-failover latency exceeds 2x baseline.")

        # Check 5: Failover strategy health
        if config.failover_strategy in (
            FailoverStrategy.AUTOMATIC,
            FailoverStrategy.PROXY_BASED,
        ):
            checks_passed += 1
        else:
            issues.append("Manual failover strategy may not verify health automatically.")

        # Check 6: Split-brain prevention
        if config.split_brain_strategy != SplitBrainStrategy.NONE:
            checks_passed += 1
        else:
            issues.append("No split-brain prevention strategy configured.")

        # Determine overall status
        ratio = checks_passed / checks_total if checks_total > 0 else 0.0
        if ratio >= 0.8:
            status = FailoverHealthStatus.HEALTHY
        elif ratio >= 0.5:
            status = FailoverHealthStatus.DEGRADED
        else:
            status = FailoverHealthStatus.UNHEALTHY

        return PostFailoverHealthCheck(
            status=status,
            replication_intact=replication_intact,
            data_integrity_verified=data_integrity,
            connection_count=actual,
            expected_connections=expected,
            latency_ms=round(post_latency, 2),
            baseline_latency_ms=baseline_latency,
            checks_passed=checks_passed,
            checks_total=checks_total,
            issues=issues,
        )

    def _analyze_cross_region(
        self, config: DatabaseFailoverConfig
    ) -> CrossRegionConfig:
        """Analyze cross-region failover specifics."""
        cr = config.cross_region

        if not cr.enabled:
            return cr

        # Estimate RPO/RTO for cross-region
        rpo = cr.rpo_seconds
        rto = cr.rto_seconds

        if rpo == 0.0:
            # Estimate based on replication mode
            if config.replication_mode == ReplicationMode.SYNC:
                rpo = 0.0
            elif config.replication_mode == ReplicationMode.SEMI_SYNC:
                rpo = 1.0
            else:
                rpo = 5.0 + (cr.replication_lag_ms / 1000.0)

        if rto == 0.0:
            # Base RTO for cross-region
            rto = 30.0
            if cr.global_table or cr.aurora_global:
                rto = 10.0
            if config.failover_strategy == FailoverStrategy.MANUAL:
                rto *= 3.0

        return CrossRegionConfig(
            enabled=True,
            primary_region=cr.primary_region,
            secondary_regions=cr.secondary_regions,
            replication_lag_ms=cr.replication_lag_ms,
            global_table=cr.global_table,
            aurora_global=cr.aurora_global,
            rpo_seconds=round(rpo, 2),
            rto_seconds=round(rto, 2),
        )

    def _calculate_reliability_score(
        self,
        config: DatabaseFailoverConfig,
        timing: FailoverTimingBreakdown,
        data_loss: DataLossRisk,
        split_brain_risk: float,
        post_health: PostFailoverHealthCheck,
        cross_region: CrossRegionConfig,
    ) -> float:
        """Calculate overall reliability score (0-100)."""
        score = 100.0

        # Penalty for slow failover (> 30s is bad)
        total_time = timing.total_seconds
        if total_time > 120.0:
            score -= 30.0
        elif total_time > 60.0:
            score -= 20.0
        elif total_time > 30.0:
            score -= 10.0

        # Penalty for data loss risk
        score -= data_loss.risk_score * 25.0

        # Penalty for split-brain risk
        score -= split_brain_risk * 20.0

        # Penalty for poor post-failover health
        health_score = post_health.health_score
        score -= (1.0 - health_score) * 15.0

        # Bonus for automatic failover
        if config.failover_strategy == FailoverStrategy.AUTOMATIC:
            score += 5.0
        elif config.failover_strategy == FailoverStrategy.PROXY_BASED:
            score += 3.0

        # Bonus for multi-AZ
        if config.multi_az:
            score += 5.0

        # Bonus for cross-region
        if cross_region.enabled:
            score += 5.0

        # Bonus for app retry
        if config.app_retry.retry_enabled:
            score += 3.0

        # Penalty for manual failover
        if config.failover_strategy == FailoverStrategy.MANUAL:
            score -= 15.0

        return round(max(0.0, min(100.0, score)), 2)

    def _build_recommendations(
        self,
        config: DatabaseFailoverConfig,
        timing: FailoverTimingBreakdown,
        data_loss: DataLossRisk,
        split_brain_risk: float,
        post_health: PostFailoverHealthCheck,
        cross_region: CrossRegionConfig,
    ) -> list[str]:
        """Build actionable recommendations."""
        recs: list[str] = []

        if config.failover_strategy == FailoverStrategy.MANUAL:
            recs.append(
                "Switch from manual to automatic failover to reduce RTO."
            )

        if timing.total_seconds > 60.0:
            recs.append(
                f"Total failover time is {timing.total_seconds:.1f}s. "
                "Consider proxy-based failover (PgBouncer/ProxySQL) to reduce connection reset time."
            )

        if data_loss.risk_score > 0.5:
            recs.append(
                "High data loss risk detected. "
                "Consider switching to synchronous replication."
            )

        if config.replication_mode == ReplicationMode.ASYNC:
            recs.append(
                "Async replication in use. Evaluate semi-sync or sync "
                "to reduce RPO."
            )

        if split_brain_risk > 0.3:
            recs.append(
                f"Split-brain risk is {split_brain_risk:.0%}. "
                "Implement STONITH or quorum-based split-brain prevention."
            )

        if config.split_brain_strategy == SplitBrainStrategy.NONE:
            recs.append(
                "No split-brain prevention strategy configured. "
                "Add fencing, quorum, or witness node."
            )

        if config.replica_count <= 1 and config.read_replica_count == 0:
            recs.append(
                "No replicas configured. Add at least one standby replica."
            )

        if config.proxy_type == ProxyType.NONE and config.database_type in (
            DatabaseType.POSTGRESQL,
            DatabaseType.MYSQL,
        ):
            recs.append(
                f"No connection proxy configured for {config.database_type.value}. "
                "Consider PgBouncer or ProxySQL for connection pooling."
            )

        if not config.multi_az:
            recs.append(
                "Multi-AZ is not enabled. Enable Multi-AZ for automatic "
                "failover across availability zones."
            )

        if not config.app_retry.retry_enabled:
            recs.append(
                "Application-level retry is not enabled. "
                "Configure retry with exponential backoff."
            )
        elif not config.app_retry.read_after_write_consistency:
            recs.append(
                "Read-after-write consistency is not configured. "
                "Enable to avoid stale reads after failover."
            )

        if not cross_region.enabled:
            recs.append(
                "Cross-region failover is not configured. "
                "Consider Global Tables or Aurora Global Database for DR."
            )

        if config.test_schedule.test_frequency_days > 90:
            recs.append(
                "Failover testing frequency exceeds 90 days. "
                "Test at least quarterly."
            )

        if not config.test_schedule.automated:
            recs.append("Automate failover testing to ensure regular validation.")

        # Deduplicate
        seen: set[str] = set()
        unique: list[str] = []
        for r in recs:
            if r not in seen:
                seen.add(r)
                unique.append(r)
        return unique
