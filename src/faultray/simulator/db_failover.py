# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Database Failover Simulator - simulate database-specific failure modes.

Supports replication lag, split-brain, failover timing, connection pool
exhaustion, read replica promotion, and more.  Works with Aurora, RDS,
Cloud SQL, Azure SQL, CockroachDB, MongoDB, and DynamoDB engine types.
"""

from __future__ import annotations

import logging
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DBEngine(str, Enum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    AURORA = "aurora"
    CLOUD_SQL = "cloud_sql"
    AZURE_SQL = "azure_sql"
    COCKROACHDB = "cockroachdb"
    MONGODB = "mongodb"
    DYNAMODB = "dynamodb"


class DBFailureMode(str, Enum):
    PRIMARY_FAILURE = "primary_failure"
    REPLICA_LAG = "replica_lag"
    SPLIT_BRAIN = "split_brain"
    CONNECTION_POOL_EXHAUSTION = "connection_pool_exhaustion"
    STORAGE_FULL = "storage_full"
    LONG_RUNNING_QUERY = "long_running_query"
    DEADLOCK = "deadlock"
    BACKUP_FAILURE = "backup_failure"
    SCHEMA_MIGRATION_FAILURE = "schema_migration_failure"
    FAILOVER_TIMEOUT = "failover_timeout"


class ReplicationType(str, Enum):
    SYNC = "sync"
    ASYNC = "async"
    SEMI_SYNC = "semi_sync"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class DBConfig(BaseModel):
    engine: DBEngine
    replicas: int = 1
    replication_type: ReplicationType = ReplicationType.ASYNC
    failover_time_seconds: float = 30.0
    connection_pool_size: int = 100
    max_connections: int = 1000
    storage_gb: float = 100.0
    iops: int = 3000
    read_replicas: int = 0
    multi_az: bool = False


class DBFailoverScenario(BaseModel):
    failure_mode: DBFailureMode
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    target_node: str = "primary"


class DBFailoverResult(BaseModel):
    scenario: DBFailoverScenario
    downtime_seconds: float = 0.0
    data_loss_transactions: int = 0
    connection_errors: int = 0
    read_availability_percent: float = 100.0
    write_availability_percent: float = 100.0
    recovery_steps: list[str] = Field(default_factory=list)
    rpo_seconds: float = 0.0
    rto_seconds: float = 0.0


class DBResilienceReport(BaseModel):
    configs_tested: int = 0
    scenarios_run: int = 0
    worst_rto_seconds: float = 0.0
    worst_rpo_seconds: float = 0.0
    results: list[DBFailoverResult] = Field(default_factory=list)
    overall_db_resilience: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


class DBFailoverSimulator:
    """Simulate database failover scenarios against an InfraGraph."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate_failover(
        self, config: DBConfig, scenario: DBFailoverScenario
    ) -> DBFailoverResult:
        """Run a single failover scenario and return the result."""
        handler = _FAILURE_HANDLERS.get(scenario.failure_mode)
        if handler is None:
            return DBFailoverResult(scenario=scenario)
        return handler(self, config, scenario)

    def assess_replication_risk(self, config: DBConfig) -> float:
        """Return a replication risk score in [0, 1]."""
        risk = 0.0
        if config.replication_type == ReplicationType.ASYNC:
            risk += 0.4
        elif config.replication_type == ReplicationType.SEMI_SYNC:
            risk += 0.2
        if config.replicas <= 1 and config.read_replicas == 0:
            risk += 0.3
        if not config.multi_az:
            risk += 0.2
        if config.read_replicas == 0:
            risk += 0.1
        return min(1.0, risk)

    def calculate_rpo(self, config: DBConfig) -> float:
        """Return estimated Recovery Point Objective in seconds."""
        if config.replication_type == ReplicationType.SYNC:
            return 0.0
        if config.replication_type == ReplicationType.SEMI_SYNC:
            return 1.0
        # ASYNC
        return 5.0

    def calculate_rto(self, config: DBConfig) -> float:
        """Return estimated Recovery Time Objective in seconds."""
        rto = config.failover_time_seconds
        if config.multi_az:
            rto *= 0.4  # multi-az reduces RTO by ~60%
        if config.replicas <= 1 and config.read_replicas == 0:
            rto *= 2.0  # no replicas doubles recovery time
        return rto

    def recommend_config(
        self, engine: DBEngine, availability_target: float
    ) -> DBConfig:
        """Recommend an optimal DBConfig for the given availability target."""
        if availability_target >= 99.99:
            return DBConfig(
                engine=engine,
                replicas=3,
                replication_type=ReplicationType.SYNC,
                failover_time_seconds=15.0,
                connection_pool_size=200,
                max_connections=2000,
                storage_gb=500.0,
                iops=10000,
                read_replicas=2,
                multi_az=True,
            )
        if availability_target >= 99.9:
            return DBConfig(
                engine=engine,
                replicas=2,
                replication_type=ReplicationType.SEMI_SYNC,
                failover_time_seconds=20.0,
                connection_pool_size=150,
                max_connections=1500,
                storage_gb=200.0,
                iops=5000,
                read_replicas=1,
                multi_az=True,
            )
        return DBConfig(
            engine=engine,
            replicas=1,
            replication_type=ReplicationType.ASYNC,
            failover_time_seconds=30.0,
            connection_pool_size=100,
            max_connections=1000,
            storage_gb=100.0,
            iops=3000,
            read_replicas=0,
            multi_az=False,
        )

    def generate_report(
        self,
        configs: list[DBConfig],
        scenarios: list[DBFailoverScenario],
    ) -> DBResilienceReport:
        """Run all scenario * config combinations and produce a report."""
        results: list[DBFailoverResult] = []
        for cfg in configs:
            for scn in scenarios:
                results.append(self.simulate_failover(cfg, scn))

        worst_rto = max((r.rto_seconds for r in results), default=0.0)
        worst_rpo = max((r.rpo_seconds for r in results), default=0.0)

        # Resilience 0-100: penalise downtime, data-loss, low availability
        if results:
            avg_write = sum(r.write_availability_percent for r in results) / len(results)
            avg_read = sum(r.read_availability_percent for r in results) / len(results)
            score = (avg_write * 0.6 + avg_read * 0.4)
        else:
            score = 0.0

        recommendations = self._build_recommendations(configs, results)

        return DBResilienceReport(
            configs_tested=len(configs),
            scenarios_run=len(results),
            worst_rto_seconds=worst_rto,
            worst_rpo_seconds=worst_rpo,
            results=results,
            overall_db_resilience=round(score, 2),
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_recommendations(
        self,
        configs: list[DBConfig],
        results: list[DBFailoverResult],
    ) -> list[str]:
        recs: list[str] = []
        for cfg in configs:
            if not cfg.multi_az:
                recs.append(
                    f"Enable Multi-AZ for {cfg.engine.value} to reduce RTO by ~60%."
                )
            if cfg.replication_type == ReplicationType.ASYNC:
                recs.append(
                    f"Consider SEMI_SYNC or SYNC replication for {cfg.engine.value} "
                    "to reduce RPO."
                )
            if cfg.read_replicas == 0:
                recs.append(
                    f"Add read replicas for {cfg.engine.value} to improve read availability."
                )
            if cfg.replicas <= 1:
                recs.append(
                    f"Increase replicas for {cfg.engine.value} to improve failover capability."
                )
        # deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for r in recs:
            if r not in seen:
                seen.add(r)
                unique.append(r)
        return unique


# ---------------------------------------------------------------------------
# Per-failure-mode simulation handlers
# ---------------------------------------------------------------------------


def _handle_primary_failure(
    sim: DBFailoverSimulator,
    config: DBConfig,
    scenario: DBFailoverScenario,
) -> DBFailoverResult:
    downtime = config.failover_time_seconds * (1.0 + scenario.severity)
    if config.multi_az:
        downtime *= 0.4

    if config.replication_type == ReplicationType.SYNC:
        data_loss = 0
    elif config.replication_type == ReplicationType.SEMI_SYNC:
        data_loss = int(10 * scenario.severity)
    else:
        data_loss = int(100 * scenario.severity)

    read_avail = 100.0 if config.read_replicas > 0 else 0.0
    write_avail = max(0.0, 100.0 - 100.0 * scenario.severity)

    steps = ["Detect primary failure", "Promote replica to primary"]
    if config.multi_az:
        steps.append("DNS failover to standby AZ")
    steps.append("Reconnect application pools")

    return DBFailoverResult(
        scenario=scenario,
        downtime_seconds=round(downtime, 2),
        data_loss_transactions=data_loss,
        connection_errors=int(config.max_connections * scenario.severity * 0.5),
        read_availability_percent=read_avail,
        write_availability_percent=round(write_avail, 2),
        recovery_steps=steps,
        rpo_seconds=sim.calculate_rpo(config),
        rto_seconds=round(downtime, 2),
    )


def _handle_replica_lag(
    sim: DBFailoverSimulator,
    config: DBConfig,
    scenario: DBFailoverScenario,
) -> DBFailoverResult:
    read_avail = max(0.0, 100.0 - 50.0 * scenario.severity)
    return DBFailoverResult(
        scenario=scenario,
        downtime_seconds=0.0,
        data_loss_transactions=0,
        connection_errors=0,
        read_availability_percent=round(read_avail, 2),
        write_availability_percent=100.0,
        recovery_steps=["Monitor replication lag", "Scale read replicas if needed"],
        rpo_seconds=sim.calculate_rpo(config),
        rto_seconds=0.0,
    )


def _handle_split_brain(
    sim: DBFailoverSimulator,
    config: DBConfig,
    scenario: DBFailoverScenario,
) -> DBFailoverResult:
    data_loss = int(1000 * scenario.severity)
    downtime = config.failover_time_seconds * 2.0
    return DBFailoverResult(
        scenario=scenario,
        downtime_seconds=round(downtime, 2),
        data_loss_transactions=data_loss,
        connection_errors=int(config.max_connections * scenario.severity),
        read_availability_percent=50.0,
        write_availability_percent=0.0,
        recovery_steps=[
            "Detect split-brain condition",
            "Fence one node",
            "Reconcile divergent data",
            "Restore single-primary topology",
        ],
        rpo_seconds=round(downtime, 2),
        rto_seconds=round(downtime, 2),
    )


def _handle_connection_pool_exhaustion(
    sim: DBFailoverSimulator,
    config: DBConfig,
    scenario: DBFailoverScenario,
) -> DBFailoverResult:
    conn_errors = int(config.max_connections * scenario.severity)
    return DBFailoverResult(
        scenario=scenario,
        downtime_seconds=0.0,
        data_loss_transactions=0,
        connection_errors=conn_errors,
        read_availability_percent=max(0.0, 100.0 - 80.0 * scenario.severity),
        write_availability_percent=max(0.0, 100.0 - 80.0 * scenario.severity),
        recovery_steps=[
            "Identify connection-leaking services",
            "Kill idle connections",
            "Increase pool size or add PgBouncer/ProxySQL",
        ],
        rpo_seconds=0.0,
        rto_seconds=0.0,
    )


def _handle_storage_full(
    sim: DBFailoverSimulator,
    config: DBConfig,
    scenario: DBFailoverScenario,
) -> DBFailoverResult:
    return DBFailoverResult(
        scenario=scenario,
        downtime_seconds=0.0,
        data_loss_transactions=0,
        connection_errors=0,
        read_availability_percent=100.0,
        write_availability_percent=0.0,
        recovery_steps=[
            "Alert on storage threshold",
            "Expand volume or enable autoscaling storage",
            "Purge old data or archive",
        ],
        rpo_seconds=0.0,
        rto_seconds=0.0,
    )


def _handle_long_running_query(
    sim: DBFailoverSimulator,
    config: DBConfig,
    scenario: DBFailoverScenario,
) -> DBFailoverResult:
    conn_errors = int(config.connection_pool_size * scenario.severity * 0.3)
    return DBFailoverResult(
        scenario=scenario,
        downtime_seconds=0.0,
        data_loss_transactions=0,
        connection_errors=conn_errors,
        read_availability_percent=max(0.0, 100.0 - 30.0 * scenario.severity),
        write_availability_percent=max(0.0, 100.0 - 30.0 * scenario.severity),
        recovery_steps=[
            "Identify long-running query via pg_stat_activity / SHOW PROCESSLIST",
            "Kill or cancel the query",
            "Add query timeout guard",
        ],
        rpo_seconds=0.0,
        rto_seconds=0.0,
    )


def _handle_deadlock(
    sim: DBFailoverSimulator,
    config: DBConfig,
    scenario: DBFailoverScenario,
) -> DBFailoverResult:
    return DBFailoverResult(
        scenario=scenario,
        downtime_seconds=0.0,
        data_loss_transactions=int(5 * scenario.severity),
        connection_errors=int(config.connection_pool_size * scenario.severity * 0.1),
        read_availability_percent=100.0,
        write_availability_percent=max(0.0, 100.0 - 20.0 * scenario.severity),
        recovery_steps=[
            "Detect deadlock via engine logs",
            "Retry rolled-back transactions",
            "Review transaction ordering",
        ],
        rpo_seconds=0.0,
        rto_seconds=0.0,
    )


def _handle_backup_failure(
    sim: DBFailoverSimulator,
    config: DBConfig,
    scenario: DBFailoverScenario,
) -> DBFailoverResult:
    # Backup failure does not cause downtime but increases RPO risk
    rpo_increase = 3600.0 * scenario.severity  # up to 1 hour
    return DBFailoverResult(
        scenario=scenario,
        downtime_seconds=0.0,
        data_loss_transactions=0,
        connection_errors=0,
        read_availability_percent=100.0,
        write_availability_percent=100.0,
        recovery_steps=[
            "Investigate backup failure cause",
            "Re-run backup manually",
            "Verify backup integrity",
        ],
        rpo_seconds=round(rpo_increase, 2),
        rto_seconds=0.0,
    )


def _handle_schema_migration_failure(
    sim: DBFailoverSimulator,
    config: DBConfig,
    scenario: DBFailoverScenario,
) -> DBFailoverResult:
    downtime = 60.0 * scenario.severity
    return DBFailoverResult(
        scenario=scenario,
        downtime_seconds=round(downtime, 2),
        data_loss_transactions=0,
        connection_errors=int(config.connection_pool_size * scenario.severity * 0.2),
        read_availability_percent=max(0.0, 100.0 - 40.0 * scenario.severity),
        write_availability_percent=0.0,
        recovery_steps=[
            "Rollback migration",
            "Fix migration script",
            "Apply migration in maintenance window",
        ],
        rpo_seconds=0.0,
        rto_seconds=round(downtime, 2),
    )


def _handle_failover_timeout(
    sim: DBFailoverSimulator,
    config: DBConfig,
    scenario: DBFailoverScenario,
) -> DBFailoverResult:
    downtime = config.failover_time_seconds * (2.0 + scenario.severity)
    if config.multi_az:
        downtime *= 0.4
    return DBFailoverResult(
        scenario=scenario,
        downtime_seconds=round(downtime, 2),
        data_loss_transactions=int(50 * scenario.severity),
        connection_errors=int(config.max_connections * scenario.severity),
        read_availability_percent=0.0,
        write_availability_percent=0.0,
        recovery_steps=[
            "Investigate failover timeout cause",
            "Manual promotion of replica",
            "Increase failover timeout threshold",
            "Review health check intervals",
        ],
        rpo_seconds=sim.calculate_rpo(config),
        rto_seconds=round(downtime, 2),
    )


_FAILURE_HANDLERS = {
    DBFailureMode.PRIMARY_FAILURE: _handle_primary_failure,
    DBFailureMode.REPLICA_LAG: _handle_replica_lag,
    DBFailureMode.SPLIT_BRAIN: _handle_split_brain,
    DBFailureMode.CONNECTION_POOL_EXHAUSTION: _handle_connection_pool_exhaustion,
    DBFailureMode.STORAGE_FULL: _handle_storage_full,
    DBFailureMode.LONG_RUNNING_QUERY: _handle_long_running_query,
    DBFailureMode.DEADLOCK: _handle_deadlock,
    DBFailureMode.BACKUP_FAILURE: _handle_backup_failure,
    DBFailureMode.SCHEMA_MIGRATION_FAILURE: _handle_schema_migration_failure,
    DBFailureMode.FAILOVER_TIMEOUT: _handle_failover_timeout,
}
