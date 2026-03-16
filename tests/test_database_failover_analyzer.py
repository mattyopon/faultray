"""Tests for faultray.simulator.database_failover_analyzer."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.database_failover_analyzer import (
    AppRetryConfig,
    ConnectionStringState,
    CrossRegionConfig,
    DatabaseFailoverAnalyzer,
    DatabaseFailoverConfig,
    DatabaseType,
    DataLossRisk,
    FailoverAnalysisResult,
    FailoverChainLink,
    FailoverHealthStatus,
    FailoverStrategy,
    FailoverTestSchedule,
    FailoverTimingBreakdown,
    PostFailoverHealthCheck,
    ProxyType,
    ReplicaPromotionAnalysis,
    ReplicationMode,
    RetryBackoff,
    SplitBrainStrategy,
)


# ---------------------------------------------------------------------------
# Helpers (per CRITICAL Constructor Patterns)
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER):
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _default_config(**overrides) -> DatabaseFailoverConfig:
    defaults = dict(
        database_type=DatabaseType.POSTGRESQL,
        failover_strategy=FailoverStrategy.AUTOMATIC,
        proxy_type=ProxyType.NONE,
        split_brain_strategy=SplitBrainStrategy.NONE,
        replication_mode=ReplicationMode.ASYNC,
        replica_count=2,
        read_replica_count=1,
        multi_az=False,
        detection_interval_seconds=10.0,
        dns_ttl_seconds=60,
        connection_pool_size=100,
        max_connections=1000,
    )
    defaults.update(overrides)
    return DatabaseFailoverConfig(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_graph() -> InfraGraph:
    return _graph()


@pytest.fixture
def db_graph() -> InfraGraph:
    db = _comp("db1", ComponentType.DATABASE)
    app = _comp("app1", ComponentType.APP_SERVER)
    g = _graph(db, app)
    g.add_dependency(Dependency(source_id="app1", target_id="db1"))
    return g


@pytest.fixture
def analyzer(db_graph) -> DatabaseFailoverAnalyzer:
    return DatabaseFailoverAnalyzer(db_graph)


@pytest.fixture
def empty_analyzer(empty_graph) -> DatabaseFailoverAnalyzer:
    return DatabaseFailoverAnalyzer(empty_graph)


# ===================================================================
# 1. Enum tests
# ===================================================================


class TestDatabaseTypeEnum:
    def test_all_types(self):
        assert len(list(DatabaseType)) == 6

    @pytest.mark.parametrize("db", list(DatabaseType))
    def test_is_string(self, db):
        assert isinstance(db.value, str)

    def test_lookup(self):
        assert DatabaseType("postgresql") == DatabaseType.POSTGRESQL
        assert DatabaseType("redis") == DatabaseType.REDIS
        assert DatabaseType("cassandra") == DatabaseType.CASSANDRA


class TestFailoverStrategyEnum:
    def test_all_strategies(self):
        assert len(list(FailoverStrategy)) == 4

    def test_values(self):
        assert FailoverStrategy.AUTOMATIC.value == "automatic"
        assert FailoverStrategy.MANUAL.value == "manual"
        assert FailoverStrategy.DNS_BASED.value == "dns_based"
        assert FailoverStrategy.PROXY_BASED.value == "proxy_based"


class TestProxyTypeEnum:
    def test_all_proxies(self):
        assert len(list(ProxyType)) == 4

    def test_pgbouncer(self):
        assert ProxyType.PGBOUNCER.value == "pgbouncer"

    def test_proxysql(self):
        assert ProxyType.PROXYSQL.value == "proxysql"


class TestSplitBrainStrategyEnum:
    def test_all_strategies(self):
        assert len(list(SplitBrainStrategy)) == 5

    @pytest.mark.parametrize("s", list(SplitBrainStrategy))
    def test_is_string(self, s):
        assert isinstance(s.value, str)


class TestReplicationModeEnum:
    def test_all_modes(self):
        assert len(list(ReplicationMode)) == 3

    def test_values(self):
        assert ReplicationMode.SYNC.value == "sync"
        assert ReplicationMode.ASYNC.value == "async"
        assert ReplicationMode.SEMI_SYNC.value == "semi_sync"


class TestRetryBackoffEnum:
    def test_all_values(self):
        assert len(list(RetryBackoff)) == 4


# ===================================================================
# 2. Dataclass tests
# ===================================================================


class TestFailoverTimingBreakdown:
    def test_defaults(self):
        t = FailoverTimingBreakdown()
        assert t.detection_time_seconds == 0.0
        assert t.promotion_time_seconds == 0.0
        assert t.dns_update_seconds == 0.0
        assert t.connection_reset_seconds == 0.0

    def test_total_seconds(self):
        t = FailoverTimingBreakdown(
            detection_time_seconds=10.0,
            promotion_time_seconds=15.0,
            dns_update_seconds=5.0,
            connection_reset_seconds=3.0,
        )
        assert t.total_seconds == 33.0

    def test_total_zero(self):
        assert FailoverTimingBreakdown().total_seconds == 0.0


class TestDataLossRisk:
    def test_defaults(self):
        d = DataLossRisk()
        assert d.risk_score == 0.0
        assert d.transactions_in_flight == 0

    def test_risk_level_critical(self):
        d = DataLossRisk(risk_score=0.9)
        assert d.risk_level == "critical"

    def test_risk_level_high(self):
        d = DataLossRisk(risk_score=0.6)
        assert d.risk_level == "high"

    def test_risk_level_medium(self):
        d = DataLossRisk(risk_score=0.3)
        assert d.risk_level == "medium"

    def test_risk_level_low(self):
        d = DataLossRisk(risk_score=0.1)
        assert d.risk_level == "low"


class TestPostFailoverHealthCheck:
    def test_defaults(self):
        h = PostFailoverHealthCheck()
        assert h.status == FailoverHealthStatus.UNKNOWN
        assert h.health_score == 0.0

    def test_health_score_calculation(self):
        h = PostFailoverHealthCheck(checks_passed=4, checks_total=5)
        assert h.health_score == pytest.approx(0.8)

    def test_health_score_zero_total(self):
        h = PostFailoverHealthCheck(checks_passed=0, checks_total=0)
        assert h.health_score == 0.0

    def test_health_score_all_passed(self):
        h = PostFailoverHealthCheck(checks_passed=6, checks_total=6)
        assert h.health_score == 1.0


# ===================================================================
# 3. Analyzer init
# ===================================================================


class TestAnalyzerInit:
    def test_stores_graph(self, analyzer, db_graph):
        assert analyzer.graph is db_graph

    def test_with_empty_graph(self, empty_analyzer, empty_graph):
        assert empty_analyzer.graph is empty_graph


# ===================================================================
# 4. find_database_components
# ===================================================================


class TestFindDatabaseComponents:
    def test_finds_db_component(self, analyzer):
        dbs = analyzer.find_database_components()
        assert len(dbs) == 1
        assert dbs[0].id == "db1"
        assert dbs[0].type == ComponentType.DATABASE

    def test_empty_graph(self, empty_analyzer):
        assert empty_analyzer.find_database_components() == []

    def test_multiple_databases(self):
        db1 = _comp("db1", ComponentType.DATABASE)
        db2 = _comp("db2", ComponentType.DATABASE)
        app = _comp("app1", ComponentType.APP_SERVER)
        g = _graph(db1, db2, app)
        a = DatabaseFailoverAnalyzer(g)
        dbs = a.find_database_components()
        assert len(dbs) == 2


# ===================================================================
# 5. Failover timing analysis
# ===================================================================


class TestFailoverTimingAnalysis:
    def test_postgresql_automatic(self, analyzer):
        cfg = _default_config()
        timing = analyzer.analyze_failover_timing(cfg)
        assert timing.detection_time_seconds > 0
        assert timing.promotion_time_seconds > 0
        assert timing.total_seconds > 0

    def test_manual_slower_than_automatic(self, analyzer):
        auto = analyzer.analyze_failover_timing(
            _default_config(failover_strategy=FailoverStrategy.AUTOMATIC)
        )
        manual = analyzer.analyze_failover_timing(
            _default_config(failover_strategy=FailoverStrategy.MANUAL)
        )
        assert manual.total_seconds > auto.total_seconds

    def test_proxy_based_no_dns(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.PROXY_BASED,
            proxy_type=ProxyType.PGBOUNCER,
        )
        timing = analyzer.analyze_failover_timing(cfg)
        assert timing.dns_update_seconds == 0.0

    def test_dns_based_uses_ttl(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.DNS_BASED,
            dns_ttl_seconds=120,
        )
        timing = analyzer.analyze_failover_timing(cfg)
        assert timing.dns_update_seconds >= 60.0  # 120 * 0.5

    def test_multi_az_reduces_promotion(self, analyzer):
        no_az = analyzer.analyze_failover_timing(_default_config(multi_az=False))
        az = analyzer.analyze_failover_timing(_default_config(multi_az=True))
        assert az.promotion_time_seconds < no_az.promotion_time_seconds

    def test_sync_replication_faster_promotion(self, analyzer):
        async_t = analyzer.analyze_failover_timing(
            _default_config(replication_mode=ReplicationMode.ASYNC)
        )
        sync_t = analyzer.analyze_failover_timing(
            _default_config(replication_mode=ReplicationMode.SYNC)
        )
        assert sync_t.promotion_time_seconds <= async_t.promotion_time_seconds

    @pytest.mark.parametrize("db", list(DatabaseType))
    def test_all_db_types_have_timing(self, analyzer, db):
        cfg = _default_config(database_type=db)
        timing = analyzer.analyze_failover_timing(cfg)
        assert timing.total_seconds >= 0.0

    def test_dynamodb_near_zero(self, analyzer):
        cfg = _default_config(database_type=DatabaseType.DYNAMODB)
        timing = analyzer.analyze_failover_timing(cfg)
        # DynamoDB is managed, detection reduced to custom interval effect
        assert timing.promotion_time_seconds == 0.0

    def test_redis_fast(self, analyzer):
        cfg = _default_config(database_type=DatabaseType.REDIS)
        timing = analyzer.analyze_failover_timing(cfg)
        pg_cfg = _default_config(database_type=DatabaseType.POSTGRESQL)
        pg_timing = analyzer.analyze_failover_timing(pg_cfg)
        assert timing.total_seconds <= pg_timing.total_seconds


# ===================================================================
# 6. Data loss risk assessment
# ===================================================================


class TestDataLossRisk:
    def test_async_has_risk(self, analyzer):
        cfg = _default_config(replication_mode=ReplicationMode.ASYNC)
        risk = analyzer.assess_data_loss_risk(cfg)
        assert risk.risk_score > 0
        assert risk.transactions_in_flight > 0
        assert risk.replication_lag_seconds > 0

    def test_sync_low_risk(self, analyzer):
        cfg = _default_config(replication_mode=ReplicationMode.SYNC, replica_count=2)
        risk = analyzer.assess_data_loss_risk(cfg)
        assert risk.risk_score < 0.3
        assert risk.replication_lag_seconds == 0.0

    def test_semi_sync_moderate(self, analyzer):
        cfg = _default_config(replication_mode=ReplicationMode.SEMI_SYNC)
        risk = analyzer.assess_data_loss_risk(cfg)
        async_cfg = _default_config(replication_mode=ReplicationMode.ASYNC)
        async_risk = analyzer.assess_data_loss_risk(async_cfg)
        assert risk.risk_score <= async_risk.risk_score

    def test_dynamodb_no_risk(self, analyzer):
        cfg = _default_config(database_type=DatabaseType.DYNAMODB)
        risk = analyzer.assess_data_loss_risk(cfg)
        assert risk.risk_score == 0.0
        assert risk.transactions_in_flight == 0

    def test_cassandra_no_risk(self, analyzer):
        cfg = _default_config(database_type=DatabaseType.CASSANDRA)
        risk = analyzer.assess_data_loss_risk(cfg)
        assert risk.risk_score == 0.0

    def test_no_replicas_high_risk(self, analyzer):
        cfg = _default_config(
            replica_count=1,
            read_replica_count=0,
            replication_mode=ReplicationMode.ASYNC,
        )
        risk = analyzer.assess_data_loss_risk(cfg)
        assert risk.risk_score >= 0.7

    def test_manual_failover_increases_risk(self, analyzer):
        auto = analyzer.assess_data_loss_risk(
            _default_config(failover_strategy=FailoverStrategy.AUTOMATIC)
        )
        manual = analyzer.assess_data_loss_risk(
            _default_config(failover_strategy=FailoverStrategy.MANUAL)
        )
        assert manual.risk_score >= auto.risk_score

    def test_risk_level_property(self, analyzer):
        cfg = _default_config(
            replication_mode=ReplicationMode.ASYNC,
            replica_count=1,
            read_replica_count=0,
            failover_strategy=FailoverStrategy.MANUAL,
        )
        risk = analyzer.assess_data_loss_risk(cfg)
        assert risk.risk_level in ("low", "medium", "high", "critical")

    def test_wal_bytes(self, analyzer):
        cfg = _default_config(replication_mode=ReplicationMode.ASYNC)
        risk = analyzer.assess_data_loss_risk(cfg)
        assert risk.uncommitted_wal_bytes > 0

    def test_sync_no_wal(self, analyzer):
        cfg = _default_config(replication_mode=ReplicationMode.SYNC)
        risk = analyzer.assess_data_loss_risk(cfg)
        assert risk.uncommitted_wal_bytes == 0


# ===================================================================
# 7. Connection string management
# ===================================================================


class TestConnectionStringState:
    def test_proxy_no_update(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.PROXY_BASED,
            proxy_type=ProxyType.PGBOUNCER,
        )
        result = analyzer.analyze(cfg)
        assert result.connection_state.requires_update is False

    def test_dns_no_update(self, analyzer):
        cfg = _default_config(failover_strategy=FailoverStrategy.DNS_BASED)
        result = analyzer.analyze(cfg)
        assert result.connection_state.requires_update is False

    def test_manual_requires_update(self, analyzer):
        cfg = _default_config(failover_strategy=FailoverStrategy.MANUAL)
        result = analyzer.analyze(cfg)
        assert result.connection_state.requires_update is True

    def test_dynamodb_no_update(self, analyzer):
        cfg = _default_config(
            database_type=DatabaseType.DYNAMODB,
            failover_strategy=FailoverStrategy.AUTOMATIC,
        )
        result = analyzer.analyze(cfg)
        assert result.connection_state.requires_update is False

    def test_proxy_fast_drain(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.PROXY_BASED,
            proxy_type=ProxyType.PROXYSQL,
        )
        result = analyzer.analyze(cfg)
        assert result.connection_state.connection_pool_drain_seconds == 1.0

    def test_endpoints_present(self, analyzer):
        cfg = _default_config()
        result = analyzer.analyze(cfg)
        assert "primary" in result.connection_state.primary_endpoint
        assert "reader" in result.connection_state.reader_endpoint


# ===================================================================
# 8. Replica promotion analysis
# ===================================================================


class TestReplicaPromotion:
    def test_no_replicas(self, analyzer):
        cfg = _default_config(replica_count=1, read_replica_count=0)
        promotions = analyzer.analyze_replica_promotion(cfg)
        assert len(promotions) == 1
        assert promotions[0].is_eligible is False

    def test_replicas_eligible(self, analyzer):
        cfg = _default_config(
            replica_count=3,
            replication_mode=ReplicationMode.SYNC,
        )
        promotions = analyzer.analyze_replica_promotion(cfg)
        assert len(promotions) >= 2
        assert all(p.is_eligible for p in promotions)

    def test_sync_no_lag(self, analyzer):
        cfg = _default_config(
            replica_count=2,
            replication_mode=ReplicationMode.SYNC,
        )
        promotions = analyzer.analyze_replica_promotion(cfg)
        for p in promotions:
            assert p.replication_lag_seconds == 0.0

    def test_async_has_lag(self, analyzer):
        cfg = _default_config(
            replica_count=3,
            replication_mode=ReplicationMode.ASYNC,
        )
        promotions = analyzer.analyze_replica_promotion(cfg)
        assert any(p.replication_lag_seconds > 0 for p in promotions)

    def test_multi_az_faster_promotion(self, analyzer):
        no_az = analyzer.analyze_replica_promotion(
            _default_config(replica_count=2, multi_az=False)
        )
        az = analyzer.analyze_replica_promotion(
            _default_config(replica_count=2, multi_az=True)
        )
        assert az[0].promotion_time_seconds < no_az[0].promotion_time_seconds

    def test_replica_ids_unique(self, analyzer):
        cfg = _default_config(replica_count=5)
        promotions = analyzer.analyze_replica_promotion(cfg)
        ids = [p.replica_id for p in promotions]
        assert len(ids) == len(set(ids))


# ===================================================================
# 9. Split-brain risk assessment
# ===================================================================


class TestSplitBrainRisk:
    def test_no_strategy_high_risk(self, analyzer):
        cfg = _default_config(split_brain_strategy=SplitBrainStrategy.NONE)
        risk = analyzer.assess_split_brain_risk(cfg)
        assert risk >= 0.5

    def test_quorum_low_risk(self, analyzer):
        cfg = _default_config(
            split_brain_strategy=SplitBrainStrategy.QUORUM,
            replication_mode=ReplicationMode.SYNC,
            multi_az=True,
        )
        risk = analyzer.assess_split_brain_risk(cfg)
        assert risk < 0.3

    def test_stonith_lowest_risk(self, analyzer):
        cfg = _default_config(
            split_brain_strategy=SplitBrainStrategy.STONITH,
            replication_mode=ReplicationMode.SYNC,
            multi_az=True,
        )
        risk = analyzer.assess_split_brain_risk(cfg)
        assert risk <= 0.15

    def test_dynamodb_no_risk(self, analyzer):
        cfg = _default_config(database_type=DatabaseType.DYNAMODB)
        risk = analyzer.assess_split_brain_risk(cfg)
        assert risk == 0.0

    def test_async_increases_risk(self, analyzer):
        sync = analyzer.assess_split_brain_risk(
            _default_config(
                replication_mode=ReplicationMode.SYNC,
                split_brain_strategy=SplitBrainStrategy.FENCING,
            )
        )
        async_ = analyzer.assess_split_brain_risk(
            _default_config(
                replication_mode=ReplicationMode.ASYNC,
                split_brain_strategy=SplitBrainStrategy.FENCING,
            )
        )
        assert async_ > sync

    def test_cross_region_increases_risk(self, analyzer):
        no_cr = analyzer.assess_split_brain_risk(
            _default_config(
                split_brain_strategy=SplitBrainStrategy.FENCING,
                cross_region=CrossRegionConfig(enabled=False),
            )
        )
        cr = analyzer.assess_split_brain_risk(
            _default_config(
                split_brain_strategy=SplitBrainStrategy.FENCING,
                cross_region=CrossRegionConfig(enabled=True),
            )
        )
        assert cr > no_cr

    @pytest.mark.parametrize("strategy", list(SplitBrainStrategy))
    def test_risk_range(self, analyzer, strategy):
        cfg = _default_config(split_brain_strategy=strategy)
        risk = analyzer.assess_split_brain_risk(cfg)
        assert 0.0 <= risk <= 1.0


# ===================================================================
# 10. Failover chain analysis
# ===================================================================


class TestFailoverChainAnalysis:
    def test_empty_chain(self, analyzer):
        result = analyzer.analyze_failover_chain([])
        assert result["chain_depth"] == 0
        assert result["healthy_nodes"] == 0
        assert result["chain_reliability"] == 0.0
        assert len(result["recommendations"]) > 0

    def test_single_node(self, analyzer):
        chain = [FailoverChainLink(node_id="n1", role="primary", is_healthy=True)]
        result = analyzer.analyze_failover_chain(chain)
        assert result["chain_depth"] == 1
        assert result["healthy_nodes"] == 1
        assert len(result["recommendations"]) > 0  # should recommend standby

    def test_healthy_chain(self, analyzer):
        chain = [
            FailoverChainLink(node_id="n1", role="primary", region="us-east-1", is_healthy=True),
            FailoverChainLink(node_id="n2", role="standby", region="us-east-1", is_healthy=True),
            FailoverChainLink(node_id="n3", role="dr", region="us-west-2", is_healthy=True),
        ]
        result = analyzer.analyze_failover_chain(chain)
        assert result["chain_depth"] == 3
        assert result["healthy_nodes"] == 3
        assert result["chain_reliability"] > 0.5

    def test_unhealthy_node(self, analyzer):
        chain = [
            FailoverChainLink(node_id="n1", role="primary", is_healthy=True),
            FailoverChainLink(node_id="n2", role="standby", is_healthy=False),
        ]
        result = analyzer.analyze_failover_chain(chain)
        assert result["healthy_nodes"] == 1
        assert result["weakest_link"] == "n2"

    def test_high_lag_weakest(self, analyzer):
        chain = [
            FailoverChainLink(node_id="n1", role="primary", is_healthy=True, replication_lag_seconds=0.0),
            FailoverChainLink(node_id="n2", role="standby", is_healthy=True, replication_lag_seconds=20.0),
        ]
        result = analyzer.analyze_failover_chain(chain)
        assert result["weakest_link"] == "n2"
        assert result["max_replication_lag_seconds"] == 20.0

    def test_lag_recommendation(self, analyzer):
        chain = [
            FailoverChainLink(node_id="n1", is_healthy=True, replication_lag_seconds=15.0),
        ]
        result = analyzer.analyze_failover_chain(chain)
        assert any("lag" in r.lower() for r in result["recommendations"])


# ===================================================================
# 11. Post-failover health verification
# ===================================================================


class TestPostFailoverHealth:
    def test_healthy_config(self, analyzer):
        cfg = _default_config(
            replica_count=3,
            replication_mode=ReplicationMode.SYNC,
            failover_strategy=FailoverStrategy.AUTOMATIC,
            split_brain_strategy=SplitBrainStrategy.QUORUM,
            proxy_type=ProxyType.PGBOUNCER,
        )
        health = analyzer.verify_post_failover_health(cfg)
        assert health.status == FailoverHealthStatus.HEALTHY
        assert health.checks_passed >= 5

    def test_unhealthy_config(self, analyzer):
        cfg = _default_config(
            replica_count=1,
            read_replica_count=0,
            replication_mode=ReplicationMode.ASYNC,
            failover_strategy=FailoverStrategy.MANUAL,
            split_brain_strategy=SplitBrainStrategy.NONE,
        )
        health = analyzer.verify_post_failover_health(cfg)
        assert health.status in (
            FailoverHealthStatus.DEGRADED,
            FailoverHealthStatus.UNHEALTHY,
        )
        assert len(health.issues) > 0

    def test_replication_intact(self, analyzer):
        cfg = _default_config(replica_count=2)
        health = analyzer.verify_post_failover_health(cfg)
        assert health.replication_intact is True

    def test_no_replication(self, analyzer):
        cfg = _default_config(replica_count=1, read_replica_count=0)
        health = analyzer.verify_post_failover_health(cfg)
        assert health.replication_intact is False

    def test_data_integrity_sync(self, analyzer):
        cfg = _default_config(replication_mode=ReplicationMode.SYNC)
        health = analyzer.verify_post_failover_health(cfg)
        assert health.data_integrity_verified is True

    def test_data_integrity_async(self, analyzer):
        cfg = _default_config(replication_mode=ReplicationMode.ASYNC)
        health = analyzer.verify_post_failover_health(cfg)
        assert health.data_integrity_verified is False

    def test_proxy_improves_latency(self, analyzer):
        no_proxy = analyzer.verify_post_failover_health(
            _default_config(proxy_type=ProxyType.NONE)
        )
        proxy = analyzer.verify_post_failover_health(
            _default_config(
                proxy_type=ProxyType.PGBOUNCER,
                failover_strategy=FailoverStrategy.PROXY_BASED,
            )
        )
        assert proxy.latency_ms <= no_proxy.latency_ms


# ===================================================================
# 12. Application retry effectiveness
# ===================================================================


class TestAppRetryEffectiveness:
    def test_no_retry(self, analyzer):
        retry = AppRetryConfig(retry_enabled=False)
        result = analyzer.calculate_app_retry_effectiveness(retry, 30.0)
        assert result["success_probability"] == 0.0
        assert result["covers_failover_window"] is False

    def test_zero_retries(self, analyzer):
        retry = AppRetryConfig(retry_enabled=True, max_retries=0)
        result = analyzer.calculate_app_retry_effectiveness(retry, 10.0)
        assert result["success_probability"] == 0.0

    def test_exponential_covers_window(self, analyzer):
        retry = AppRetryConfig(
            retry_enabled=True,
            max_retries=10,
            initial_delay_ms=1000.0,
            max_delay_ms=30000.0,
            backoff=RetryBackoff.EXPONENTIAL,
        )
        result = analyzer.calculate_app_retry_effectiveness(retry, 5.0)
        assert result["total_retry_time_ms"] > 0
        # With 10 retries and 1s initial, should cover 5s window
        assert result["covers_failover_window"] is True

    def test_fixed_backoff(self, analyzer):
        retry = AppRetryConfig(
            retry_enabled=True,
            max_retries=5,
            initial_delay_ms=500.0,
            backoff=RetryBackoff.FIXED,
        )
        result = analyzer.calculate_app_retry_effectiveness(retry, 10.0)
        assert result["total_retry_time_ms"] == 2500.0

    def test_no_backoff(self, analyzer):
        retry = AppRetryConfig(
            retry_enabled=True,
            max_retries=3,
            backoff=RetryBackoff.NONE,
        )
        result = analyzer.calculate_app_retry_effectiveness(retry, 1.0)
        assert result["total_retry_time_ms"] == 0.0

    def test_max_delay_cap(self, analyzer):
        retry = AppRetryConfig(
            retry_enabled=True,
            max_retries=20,
            initial_delay_ms=100.0,
            max_delay_ms=1000.0,
            backoff=RetryBackoff.EXPONENTIAL,
        )
        result = analyzer.calculate_app_retry_effectiveness(retry, 100.0)
        # The total time should not exceed max_retries * max_delay_ms
        assert result["total_retry_time_ms"] <= 20 * 1000.0


# ===================================================================
# 13. Cross-region failover analysis
# ===================================================================


class TestCrossRegionAnalysis:
    def test_disabled(self, analyzer):
        cfg = _default_config(cross_region=CrossRegionConfig(enabled=False))
        result = analyzer.analyze(cfg)
        assert result.cross_region.enabled is False

    def test_enabled_estimates_rpo(self, analyzer):
        cfg = _default_config(
            cross_region=CrossRegionConfig(
                enabled=True,
                primary_region="us-east-1",
                secondary_regions=["us-west-2"],
                replication_lag_ms=50.0,
            ),
            replication_mode=ReplicationMode.ASYNC,
        )
        result = analyzer.analyze(cfg)
        assert result.cross_region.rpo_seconds > 0

    def test_global_table_faster_rto(self, analyzer):
        base = _default_config(
            cross_region=CrossRegionConfig(
                enabled=True,
                primary_region="us-east-1",
                secondary_regions=["eu-west-1"],
                global_table=False,
            ),
        )
        global_t = _default_config(
            cross_region=CrossRegionConfig(
                enabled=True,
                primary_region="us-east-1",
                secondary_regions=["eu-west-1"],
                global_table=True,
            ),
        )
        base_result = analyzer.analyze(base)
        global_result = analyzer.analyze(global_t)
        assert global_result.cross_region.rto_seconds <= base_result.cross_region.rto_seconds

    def test_aurora_global(self, analyzer):
        cfg = _default_config(
            cross_region=CrossRegionConfig(
                enabled=True,
                aurora_global=True,
            ),
        )
        result = analyzer.analyze(cfg)
        assert result.cross_region.rto_seconds <= 30.0

    def test_sync_replication_zero_rpo(self, analyzer):
        cfg = _default_config(
            replication_mode=ReplicationMode.SYNC,
            cross_region=CrossRegionConfig(enabled=True),
        )
        result = analyzer.analyze(cfg)
        assert result.cross_region.rpo_seconds == 0.0


# ===================================================================
# 14. Full analysis
# ===================================================================


class TestFullAnalysis:
    def test_basic_analysis(self, analyzer):
        cfg = _default_config()
        result = analyzer.analyze(cfg)
        assert isinstance(result, FailoverAnalysisResult)
        assert result.database_type == DatabaseType.POSTGRESQL
        assert result.analyzed_at is not None
        assert result.overall_reliability_score >= 0
        assert result.overall_reliability_score <= 100

    def test_automatic_has_higher_score(self, analyzer):
        auto = analyzer.analyze(
            _default_config(failover_strategy=FailoverStrategy.AUTOMATIC)
        )
        manual = analyzer.analyze(
            _default_config(failover_strategy=FailoverStrategy.MANUAL)
        )
        assert auto.overall_reliability_score > manual.overall_reliability_score

    def test_multi_az_improves_score(self, analyzer):
        no_az = analyzer.analyze(_default_config(multi_az=False))
        az = analyzer.analyze(_default_config(multi_az=True))
        assert az.overall_reliability_score >= no_az.overall_reliability_score

    def test_has_recommendations(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.MANUAL,
            split_brain_strategy=SplitBrainStrategy.NONE,
            replication_mode=ReplicationMode.ASYNC,
            proxy_type=ProxyType.NONE,
            multi_az=False,
        )
        result = analyzer.analyze(cfg)
        assert len(result.recommendations) > 0

    def test_analyzed_at_utc(self, analyzer):
        cfg = _default_config()
        result = analyzer.analyze(cfg)
        assert result.analyzed_at.tzinfo == timezone.utc

    @pytest.mark.parametrize("db", list(DatabaseType))
    def test_all_database_types(self, analyzer, db):
        cfg = _default_config(database_type=db)
        result = analyzer.analyze(cfg)
        assert result.database_type == db
        assert result.overall_reliability_score >= 0

    @pytest.mark.parametrize("strategy", list(FailoverStrategy))
    def test_all_failover_strategies(self, analyzer, strategy):
        cfg = _default_config(failover_strategy=strategy)
        result = analyzer.analyze(cfg)
        assert result.failover_strategy == strategy


# ===================================================================
# 15. Failover report generation
# ===================================================================


class TestFailoverReport:
    def test_empty_configs(self, analyzer):
        report = analyzer.generate_failover_report([])
        assert report["configs_analyzed"] == 0
        assert report["average_reliability"] == 0.0
        assert report["results"] == []

    def test_single_config(self, analyzer):
        cfg = _default_config()
        report = analyzer.generate_failover_report([cfg])
        assert report["configs_analyzed"] == 1
        assert len(report["results"]) == 1
        assert report["average_reliability"] > 0

    def test_multiple_configs(self, analyzer):
        configs = [
            _default_config(database_type=DatabaseType.POSTGRESQL),
            _default_config(database_type=DatabaseType.MYSQL),
            _default_config(database_type=DatabaseType.REDIS),
        ]
        report = analyzer.generate_failover_report(configs)
        assert report["configs_analyzed"] == 3
        assert len(report["results"]) == 3

    def test_worst_failover_time(self, analyzer):
        configs = [
            _default_config(failover_strategy=FailoverStrategy.AUTOMATIC),
            _default_config(failover_strategy=FailoverStrategy.MANUAL),
        ]
        report = analyzer.generate_failover_report(configs)
        assert report["worst_failover_time_seconds"] > 0

    def test_aggregate_recommendations_deduplicated(self, analyzer):
        configs = [
            _default_config(multi_az=False),
            _default_config(multi_az=False),
        ]
        report = analyzer.generate_failover_report(configs)
        recs = report["aggregate_recommendations"]
        assert len(recs) == len(set(recs))


# ===================================================================
# 16. Test schedule readiness
# ===================================================================


class TestTestScheduleReadiness:
    def test_good_schedule(self, analyzer):
        schedule = FailoverTestSchedule(
            test_frequency_days=30,
            automated=True,
            last_test_passed=True,
            test_coverage_percent=90.0,
        )
        result = analyzer.evaluate_failover_test_readiness(schedule)
        assert result["readiness_score"] == 100.0
        assert len(result["issues"]) == 0

    def test_infrequent_testing(self, analyzer):
        schedule = FailoverTestSchedule(test_frequency_days=200)
        result = analyzer.evaluate_failover_test_readiness(schedule)
        assert result["readiness_score"] < 100.0
        assert any("180" in i for i in result["issues"])

    def test_not_automated(self, analyzer):
        schedule = FailoverTestSchedule(automated=False, test_coverage_percent=90.0)
        result = analyzer.evaluate_failover_test_readiness(schedule)
        assert result["readiness_score"] < 100.0

    def test_failed_last_test(self, analyzer):
        schedule = FailoverTestSchedule(
            last_test_passed=False,
            automated=True,
            test_coverage_percent=90.0,
        )
        result = analyzer.evaluate_failover_test_readiness(schedule)
        assert result["readiness_score"] < 100.0

    def test_low_coverage(self, analyzer):
        schedule = FailoverTestSchedule(
            test_coverage_percent=30.0,
            automated=True,
        )
        result = analyzer.evaluate_failover_test_readiness(schedule)
        assert result["readiness_score"] < 100.0
        assert any("coverage" in i.lower() for i in result["issues"])

    def test_overdue_test(self, analyzer):
        schedule = FailoverTestSchedule(
            test_frequency_days=30,
            last_test_date=datetime.now(timezone.utc) - timedelta(days=60),
            automated=True,
            test_coverage_percent=90.0,
        )
        result = analyzer.evaluate_failover_test_readiness(schedule)
        assert result["readiness_score"] < 100.0

    def test_worst_case(self, analyzer):
        schedule = FailoverTestSchedule(
            test_frequency_days=365,
            automated=False,
            last_test_passed=False,
            test_coverage_percent=10.0,
        )
        result = analyzer.evaluate_failover_test_readiness(schedule)
        assert result["readiness_score"] == 0.0


# ===================================================================
# 17. Reliability score calculation
# ===================================================================


class TestReliabilityScore:
    def test_optimal_config(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.AUTOMATIC,
            replication_mode=ReplicationMode.SYNC,
            split_brain_strategy=SplitBrainStrategy.STONITH,
            multi_az=True,
            replica_count=3,
            proxy_type=ProxyType.PGBOUNCER,
            app_retry=AppRetryConfig(retry_enabled=True),
            cross_region=CrossRegionConfig(enabled=True),
        )
        result = analyzer.analyze(cfg)
        assert result.overall_reliability_score >= 80.0

    def test_worst_config(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.MANUAL,
            replication_mode=ReplicationMode.ASYNC,
            split_brain_strategy=SplitBrainStrategy.NONE,
            multi_az=False,
            replica_count=1,
            read_replica_count=0,
        )
        result = analyzer.analyze(cfg)
        assert result.overall_reliability_score < 50.0

    def test_score_clamped_0_100(self, analyzer):
        for db in DatabaseType:
            for strategy in FailoverStrategy:
                cfg = _default_config(database_type=db, failover_strategy=strategy)
                result = analyzer.analyze(cfg)
                assert 0.0 <= result.overall_reliability_score <= 100.0


# ===================================================================
# 18. Recommendations
# ===================================================================


class TestRecommendations:
    def test_manual_failover_recommendation(self, analyzer):
        cfg = _default_config(failover_strategy=FailoverStrategy.MANUAL)
        result = analyzer.analyze(cfg)
        assert any("manual" in r.lower() or "automatic" in r.lower() for r in result.recommendations)

    def test_no_replicas_recommendation(self, analyzer):
        cfg = _default_config(replica_count=1, read_replica_count=0)
        result = analyzer.analyze(cfg)
        assert any("replica" in r.lower() for r in result.recommendations)

    def test_no_proxy_recommendation(self, analyzer):
        cfg = _default_config(
            proxy_type=ProxyType.NONE,
            database_type=DatabaseType.POSTGRESQL,
        )
        result = analyzer.analyze(cfg)
        assert any("proxy" in r.lower() or "pgbouncer" in r.lower() or "proxysql" in r.lower() for r in result.recommendations)

    def test_no_multi_az_recommendation(self, analyzer):
        cfg = _default_config(multi_az=False)
        result = analyzer.analyze(cfg)
        assert any("multi-az" in r.lower() for r in result.recommendations)

    def test_no_retry_recommendation(self, analyzer):
        cfg = _default_config(app_retry=AppRetryConfig(retry_enabled=False))
        result = analyzer.analyze(cfg)
        assert any("retry" in r.lower() for r in result.recommendations)

    def test_no_cross_region_recommendation(self, analyzer):
        cfg = _default_config(cross_region=CrossRegionConfig(enabled=False))
        result = analyzer.analyze(cfg)
        assert any("cross-region" in r.lower() or "global" in r.lower() for r in result.recommendations)

    def test_async_replication_recommendation(self, analyzer):
        cfg = _default_config(replication_mode=ReplicationMode.ASYNC)
        result = analyzer.analyze(cfg)
        assert any("async" in r.lower() or "sync" in r.lower() for r in result.recommendations)

    def test_recommendations_unique(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.MANUAL,
            split_brain_strategy=SplitBrainStrategy.NONE,
            multi_az=False,
            replica_count=1,
            read_replica_count=0,
        )
        result = analyzer.analyze(cfg)
        assert len(result.recommendations) == len(set(result.recommendations))


# ===================================================================
# 19. Graph integration tests
# ===================================================================


class TestGraphIntegration:
    def test_multi_db_graph(self):
        pg = _comp("pg1", ComponentType.DATABASE)
        redis = _comp("redis1", ComponentType.CACHE)
        app = _comp("app1", ComponentType.APP_SERVER)
        g = _graph(pg, redis, app)
        g.add_dependency(Dependency(source_id="app1", target_id="pg1"))
        g.add_dependency(Dependency(source_id="app1", target_id="redis1"))
        a = DatabaseFailoverAnalyzer(g)
        dbs = a.find_database_components()
        assert len(dbs) == 1  # only DATABASE type, not CACHE

    def test_graph_with_dependencies(self):
        db = _comp("db1", ComponentType.DATABASE)
        app1 = _comp("app1", ComponentType.APP_SERVER)
        app2 = _comp("app2", ComponentType.APP_SERVER)
        g = _graph(db, app1, app2)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        g.add_dependency(Dependency(source_id="app2", target_id="db1"))
        a = DatabaseFailoverAnalyzer(g)
        # Can still run analysis with graph context
        cfg = _default_config()
        result = a.analyze(cfg)
        assert result.overall_reliability_score >= 0

    def test_isolated_db_component(self):
        db = _comp("iso-db", ComponentType.DATABASE)
        g = _graph(db)
        a = DatabaseFailoverAnalyzer(g)
        dbs = a.find_database_components()
        assert len(dbs) == 1
        assert dbs[0].id == "iso-db"


# ===================================================================
# 20. Edge cases and boundary values
# ===================================================================


class TestEdgeCases:
    def test_all_db_strategy_combos(self, analyzer):
        """Every DB type x failover strategy combination produces a valid result."""
        for db in DatabaseType:
            for strategy in FailoverStrategy:
                cfg = _default_config(database_type=db, failover_strategy=strategy)
                result = analyzer.analyze(cfg)
                assert isinstance(result, FailoverAnalysisResult)

    def test_all_proxy_types(self, analyzer):
        for proxy in ProxyType:
            cfg = _default_config(
                proxy_type=proxy,
                failover_strategy=FailoverStrategy.PROXY_BASED,
            )
            result = analyzer.analyze(cfg)
            assert result.timing.total_seconds >= 0

    def test_all_replication_modes(self, analyzer):
        for mode in ReplicationMode:
            cfg = _default_config(replication_mode=mode)
            risk = analyzer.assess_data_loss_risk(cfg)
            assert 0.0 <= risk.risk_score <= 1.0

    def test_high_replica_count(self, analyzer):
        cfg = _default_config(replica_count=10, read_replica_count=5)
        result = analyzer.analyze(cfg)
        assert len(result.replica_promotions) >= 10

    def test_very_high_dns_ttl(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.DNS_BASED,
            dns_ttl_seconds=3600,
        )
        timing = analyzer.analyze_failover_timing(cfg)
        assert timing.dns_update_seconds >= 1800.0  # 3600 * 0.5

    def test_zero_connection_pool(self, analyzer):
        cfg = _default_config(connection_pool_size=0)
        health = analyzer.verify_post_failover_health(cfg)
        assert health.expected_connections == 0

    def test_zero_max_connections(self, analyzer):
        cfg = _default_config(max_connections=0)
        risk = analyzer.assess_data_loss_risk(cfg)
        assert risk.transactions_in_flight == 0

    def test_failover_chain_all_unhealthy(self, analyzer):
        chain = [
            FailoverChainLink(node_id="n1", is_healthy=False),
            FailoverChainLink(node_id="n2", is_healthy=False),
        ]
        result = analyzer.analyze_failover_chain(chain)
        assert result["healthy_nodes"] == 0
        assert result["chain_reliability"] == 0.0

    def test_retry_effectiveness_zero_failover(self, analyzer):
        retry = AppRetryConfig(
            retry_enabled=True,
            max_retries=3,
            initial_delay_ms=100.0,
            backoff=RetryBackoff.FIXED,
        )
        result = analyzer.calculate_app_retry_effectiveness(retry, 0.0)
        assert result["covers_failover_window"] is True

    def test_config_defaults(self):
        cfg = DatabaseFailoverConfig()
        assert cfg.database_type == DatabaseType.POSTGRESQL
        assert cfg.failover_strategy == FailoverStrategy.AUTOMATIC
        assert cfg.proxy_type == ProxyType.NONE

    def test_timing_breakdown_custom_values(self):
        t = FailoverTimingBreakdown(
            detection_time_seconds=1.0,
            promotion_time_seconds=2.0,
            dns_update_seconds=3.0,
            connection_reset_seconds=4.0,
        )
        assert t.total_seconds == 10.0

    def test_data_loss_risk_boundary_levels(self):
        assert DataLossRisk(risk_score=0.0).risk_level == "low"
        assert DataLossRisk(risk_score=0.19).risk_level == "low"
        assert DataLossRisk(risk_score=0.2).risk_level == "medium"
        assert DataLossRisk(risk_score=0.49).risk_level == "medium"
        assert DataLossRisk(risk_score=0.5).risk_level == "high"
        assert DataLossRisk(risk_score=0.79).risk_level == "high"
        assert DataLossRisk(risk_score=0.8).risk_level == "critical"
        assert DataLossRisk(risk_score=1.0).risk_level == "critical"


# ===================================================================
# 21. Additional coverage for private methods
# ===================================================================


class TestPrivateMethodCoverage:
    def test_analyze_connection_state_automatic_non_dynamodb(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.AUTOMATIC,
            database_type=DatabaseType.POSTGRESQL,
        )
        result = analyzer.analyze(cfg)
        # Automatic + non-DynamoDB requires update
        assert result.connection_state.requires_update is True

    def test_semi_sync_promotion_time(self, analyzer):
        cfg = _default_config(replication_mode=ReplicationMode.SEMI_SYNC)
        timing = analyzer.analyze_failover_timing(cfg)
        async_cfg = _default_config(replication_mode=ReplicationMode.ASYNC)
        async_timing = analyzer.analyze_failover_timing(async_cfg)
        assert timing.promotion_time_seconds <= async_timing.promotion_time_seconds

    def test_many_replicas_split_brain(self, analyzer):
        cfg = _default_config(
            replica_count=5,
            split_brain_strategy=SplitBrainStrategy.FENCING,
        )
        risk = analyzer.assess_split_brain_risk(cfg)
        small_cfg = _default_config(
            replica_count=2,
            split_brain_strategy=SplitBrainStrategy.FENCING,
        )
        small_risk = analyzer.assess_split_brain_risk(small_cfg)
        assert risk >= small_risk

    def test_cross_region_manual_rto(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.MANUAL,
            cross_region=CrossRegionConfig(
                enabled=True,
                primary_region="us-east-1",
                secondary_regions=["eu-west-1"],
            ),
        )
        result = analyzer.analyze(cfg)
        assert result.cross_region.rto_seconds > 30.0

    def test_medium_test_frequency(self, analyzer):
        schedule = FailoverTestSchedule(
            test_frequency_days=120,
            automated=True,
            last_test_passed=True,
            test_coverage_percent=90.0,
        )
        result = analyzer.evaluate_failover_test_readiness(schedule)
        assert result["readiness_score"] < 100.0
        assert any("90" in i for i in result["issues"])

    def test_medium_coverage(self, analyzer):
        schedule = FailoverTestSchedule(
            test_frequency_days=30,
            automated=True,
            last_test_passed=True,
            test_coverage_percent=60.0,
        )
        result = analyzer.evaluate_failover_test_readiness(schedule)
        assert result["readiness_score"] < 100.0

    def test_proxy_based_haproxy(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.PROXY_BASED,
            proxy_type=ProxyType.HAPROXY,
        )
        timing = analyzer.analyze_failover_timing(cfg)
        assert timing.dns_update_seconds == 0.0
        # HAProxy doesn't get the 0.3 reduction on conn reset
        assert timing.connection_reset_seconds > 0

    def test_slow_failover_high_data_loss_low_score(self, analyzer):
        cfg = _default_config(
            failover_strategy=FailoverStrategy.MANUAL,
            replication_mode=ReplicationMode.ASYNC,
            split_brain_strategy=SplitBrainStrategy.NONE,
            replica_count=1,
            read_replica_count=0,
            multi_az=False,
        )
        result = analyzer.analyze(cfg)
        # Very poor config should have low score
        assert result.overall_reliability_score < 40.0

    def test_mongodb_timing(self, analyzer):
        cfg = _default_config(database_type=DatabaseType.MONGODB)
        timing = analyzer.analyze_failover_timing(cfg)
        # MongoDB uses internal election, no DNS update
        assert timing.total_seconds > 0

    def test_cassandra_timing(self, analyzer):
        cfg = _default_config(database_type=DatabaseType.CASSANDRA)
        timing = analyzer.analyze_failover_timing(cfg)
        # Cassandra has no promotion (leaderless)
        assert timing.promotion_time_seconds == 0.0


# ===================================================================
# 22. Parametrized cross-cutting tests
# ===================================================================


class TestCrossCutting:
    @pytest.mark.parametrize("db", list(DatabaseType))
    @pytest.mark.parametrize("mode", list(ReplicationMode))
    def test_all_db_replication_combos(self, analyzer, db, mode):
        cfg = _default_config(database_type=db, replication_mode=mode)
        result = analyzer.analyze(cfg)
        assert 0.0 <= result.overall_reliability_score <= 100.0
        assert result.timing.total_seconds >= 0.0

    @pytest.mark.parametrize("strategy", list(SplitBrainStrategy))
    def test_split_brain_all_strategies_range(self, analyzer, strategy):
        cfg = _default_config(split_brain_strategy=strategy)
        risk = analyzer.assess_split_brain_risk(cfg)
        assert 0.0 <= risk <= 1.0
