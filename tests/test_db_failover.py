"""Tests for faultray.simulator.db_failover — Database Failover Simulator."""

from __future__ import annotations

import pytest

from faultray.model.graph import InfraGraph
from faultray.simulator.db_failover import (
    DBConfig,
    DBEngine,
    DBFailoverResult,
    DBFailoverScenario,
    DBFailoverSimulator,
    DBFailureMode,
    DBResilienceReport,
    ReplicationType,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def graph() -> InfraGraph:
    return InfraGraph()


@pytest.fixture
def simulator(graph: InfraGraph) -> DBFailoverSimulator:
    return DBFailoverSimulator(graph)


def _default_config(**overrides) -> DBConfig:
    defaults = dict(
        engine=DBEngine.POSTGRESQL,
        replicas=2,
        replication_type=ReplicationType.ASYNC,
        failover_time_seconds=30.0,
        connection_pool_size=100,
        max_connections=1000,
        storage_gb=100.0,
        iops=3000,
        read_replicas=1,
        multi_az=False,
    )
    defaults.update(overrides)
    return DBConfig(**defaults)


def _scenario(mode: DBFailureMode, severity: float = 0.5, target: str = "primary"):
    return DBFailoverScenario(failure_mode=mode, severity=severity, target_node=target)


# ===================================================================
# 1. Enum tests
# ===================================================================


class TestDBEngineEnum:
    def test_all_engines(self):
        engines = list(DBEngine)
        assert len(engines) == 8

    @pytest.mark.parametrize(
        "engine",
        [
            DBEngine.POSTGRESQL,
            DBEngine.MYSQL,
            DBEngine.AURORA,
            DBEngine.CLOUD_SQL,
            DBEngine.AZURE_SQL,
            DBEngine.COCKROACHDB,
            DBEngine.MONGODB,
            DBEngine.DYNAMODB,
        ],
    )
    def test_engine_values(self, engine: DBEngine):
        assert engine.value == engine.name.lower()

    def test_string_lookup(self):
        assert DBEngine("postgresql") == DBEngine.POSTGRESQL


class TestDBFailureModeEnum:
    def test_all_modes(self):
        assert len(list(DBFailureMode)) == 10

    @pytest.mark.parametrize("mode", list(DBFailureMode))
    def test_mode_is_string(self, mode: DBFailureMode):
        assert isinstance(mode.value, str)


class TestReplicationTypeEnum:
    def test_all_types(self):
        assert len(list(ReplicationType)) == 3

    def test_values(self):
        assert ReplicationType.SYNC.value == "sync"
        assert ReplicationType.ASYNC.value == "async"
        assert ReplicationType.SEMI_SYNC.value == "semi_sync"


# ===================================================================
# 2. Pydantic model tests
# ===================================================================


class TestDBConfig:
    def test_defaults(self):
        cfg = DBConfig(engine=DBEngine.POSTGRESQL)
        assert cfg.replicas == 1
        assert cfg.replication_type == ReplicationType.ASYNC
        assert cfg.failover_time_seconds == 30.0
        assert cfg.connection_pool_size == 100
        assert cfg.max_connections == 1000
        assert cfg.storage_gb == 100.0
        assert cfg.iops == 3000
        assert cfg.read_replicas == 0
        assert cfg.multi_az is False

    @pytest.mark.parametrize("engine", list(DBEngine))
    def test_all_engines_accepted(self, engine: DBEngine):
        cfg = DBConfig(engine=engine)
        assert cfg.engine == engine

    def test_custom_values(self):
        cfg = _default_config(replicas=3, multi_az=True, iops=10000)
        assert cfg.replicas == 3
        assert cfg.multi_az is True
        assert cfg.iops == 10000

    def test_serialization_roundtrip(self):
        cfg = _default_config()
        data = cfg.model_dump()
        restored = DBConfig(**data)
        assert restored == cfg


class TestDBFailoverScenario:
    def test_defaults(self):
        s = DBFailoverScenario(failure_mode=DBFailureMode.PRIMARY_FAILURE)
        assert s.severity == 0.5
        assert s.target_node == "primary"

    def test_severity_bounds(self):
        s = DBFailoverScenario(failure_mode=DBFailureMode.REPLICA_LAG, severity=0.0)
        assert s.severity == 0.0
        s = DBFailoverScenario(failure_mode=DBFailureMode.REPLICA_LAG, severity=1.0)
        assert s.severity == 1.0

    def test_severity_out_of_range(self):
        with pytest.raises(Exception):
            DBFailoverScenario(failure_mode=DBFailureMode.DEADLOCK, severity=1.5)
        with pytest.raises(Exception):
            DBFailoverScenario(failure_mode=DBFailureMode.DEADLOCK, severity=-0.1)


class TestDBFailoverResult:
    def test_defaults(self):
        scn = _scenario(DBFailureMode.PRIMARY_FAILURE)
        r = DBFailoverResult(scenario=scn)
        assert r.downtime_seconds == 0.0
        assert r.data_loss_transactions == 0
        assert r.connection_errors == 0
        assert r.read_availability_percent == 100.0
        assert r.write_availability_percent == 100.0
        assert r.recovery_steps == []
        assert r.rpo_seconds == 0.0
        assert r.rto_seconds == 0.0


class TestDBResilienceReport:
    def test_defaults(self):
        rpt = DBResilienceReport()
        assert rpt.configs_tested == 0
        assert rpt.scenarios_run == 0
        assert rpt.worst_rto_seconds == 0.0
        assert rpt.worst_rpo_seconds == 0.0
        assert rpt.results == []
        assert rpt.overall_db_resilience == 0.0
        assert rpt.recommendations == []


# ===================================================================
# 3. DBFailoverSimulator construction
# ===================================================================


class TestSimulatorInit:
    def test_stores_graph(self, graph, simulator):
        assert simulator.graph is graph


# ===================================================================
# 4. PRIMARY_FAILURE tests
# ===================================================================


class TestPrimaryFailure:
    def test_basic(self, simulator):
        cfg = _default_config()
        res = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE))
        assert res.downtime_seconds > 0
        assert res.rto_seconds > 0

    def test_severity_affects_downtime(self, simulator):
        cfg = _default_config()
        low = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE, 0.1))
        high = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE, 1.0))
        assert high.downtime_seconds > low.downtime_seconds

    def test_multi_az_reduces_downtime(self, simulator):
        cfg_no = _default_config(multi_az=False)
        cfg_az = _default_config(multi_az=True)
        s = _scenario(DBFailureMode.PRIMARY_FAILURE, 0.5)
        r_no = simulator.simulate_failover(cfg_no, s)
        r_az = simulator.simulate_failover(cfg_az, s)
        assert r_az.downtime_seconds < r_no.downtime_seconds

    def test_sync_no_data_loss(self, simulator):
        cfg = _default_config(replication_type=ReplicationType.SYNC)
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE, 1.0))
        assert r.data_loss_transactions == 0

    def test_async_has_data_loss(self, simulator):
        cfg = _default_config(replication_type=ReplicationType.ASYNC)
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE, 1.0))
        assert r.data_loss_transactions > 0

    def test_semi_sync_moderate_data_loss(self, simulator):
        cfg = _default_config(replication_type=ReplicationType.SEMI_SYNC)
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE, 1.0))
        cfg_async = _default_config(replication_type=ReplicationType.ASYNC)
        r_async = simulator.simulate_failover(cfg_async, _scenario(DBFailureMode.PRIMARY_FAILURE, 1.0))
        assert r.data_loss_transactions <= r_async.data_loss_transactions

    def test_read_replicas_maintain_read_avail(self, simulator):
        cfg = _default_config(read_replicas=2)
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE, 1.0))
        assert r.read_availability_percent == 100.0

    def test_no_read_replicas_zero_read_avail(self, simulator):
        cfg = _default_config(read_replicas=0)
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE, 1.0))
        assert r.read_availability_percent == 0.0

    def test_recovery_steps_present(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE))
        assert len(r.recovery_steps) >= 2

    def test_multi_az_adds_dns_step(self, simulator):
        cfg = _default_config(multi_az=True)
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE))
        assert any("DNS" in s for s in r.recovery_steps)

    def test_connection_errors(self, simulator):
        cfg = _default_config(max_connections=2000)
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE, 1.0))
        assert r.connection_errors > 0

    def test_zero_severity(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE, 0.0))
        assert r.downtime_seconds > 0  # still has base failover time
        assert r.data_loss_transactions == 0


# ===================================================================
# 5. REPLICA_LAG tests
# ===================================================================


class TestReplicaLag:
    def test_no_downtime(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.REPLICA_LAG))
        assert r.downtime_seconds == 0.0

    def test_write_availability_full(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.REPLICA_LAG, 1.0))
        assert r.write_availability_percent == 100.0

    def test_read_availability_degraded(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.REPLICA_LAG, 1.0))
        assert r.read_availability_percent < 100.0

    def test_no_data_loss(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.REPLICA_LAG))
        assert r.data_loss_transactions == 0

    def test_rto_zero(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.REPLICA_LAG))
        assert r.rto_seconds == 0.0

    def test_low_severity_high_read_avail(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.REPLICA_LAG, 0.1))
        assert r.read_availability_percent >= 90.0


# ===================================================================
# 6. SPLIT_BRAIN tests
# ===================================================================


class TestSplitBrain:
    def test_high_data_loss(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.SPLIT_BRAIN, 1.0))
        assert r.data_loss_transactions > 0

    def test_write_avail_zero(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.SPLIT_BRAIN))
        assert r.write_availability_percent == 0.0

    def test_read_avail_degraded(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.SPLIT_BRAIN))
        assert r.read_availability_percent == 50.0

    def test_downtime_present(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.SPLIT_BRAIN))
        assert r.downtime_seconds > 0

    def test_recovery_steps_include_fence(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.SPLIT_BRAIN))
        assert any("Fence" in s for s in r.recovery_steps)

    def test_connection_errors(self, simulator):
        cfg = _default_config(max_connections=500)
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.SPLIT_BRAIN, 1.0))
        assert r.connection_errors == 500

    def test_rpo_equals_rto(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.SPLIT_BRAIN, 0.5))
        assert r.rpo_seconds == r.rto_seconds


# ===================================================================
# 7. CONNECTION_POOL_EXHAUSTION tests
# ===================================================================


class TestConnectionPoolExhaustion:
    def test_connection_errors_match_severity(self, simulator):
        cfg = _default_config(max_connections=1000)
        r = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.CONNECTION_POOL_EXHAUSTION, 1.0)
        )
        assert r.connection_errors == 1000

    def test_no_downtime(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.CONNECTION_POOL_EXHAUSTION)
        )
        assert r.downtime_seconds == 0.0

    def test_no_data_loss(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.CONNECTION_POOL_EXHAUSTION)
        )
        assert r.data_loss_transactions == 0

    def test_availability_degraded(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.CONNECTION_POOL_EXHAUSTION, 1.0)
        )
        assert r.read_availability_percent < 100.0
        assert r.write_availability_percent < 100.0

    def test_zero_severity_full_avail(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.CONNECTION_POOL_EXHAUSTION, 0.0)
        )
        assert r.read_availability_percent == 100.0
        assert r.write_availability_percent == 100.0
        assert r.connection_errors == 0


# ===================================================================
# 8. STORAGE_FULL tests
# ===================================================================


class TestStorageFull:
    def test_write_avail_zero(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.STORAGE_FULL))
        assert r.write_availability_percent == 0.0

    def test_read_avail_full(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.STORAGE_FULL))
        assert r.read_availability_percent == 100.0

    def test_no_data_loss(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.STORAGE_FULL))
        assert r.data_loss_transactions == 0

    def test_no_downtime(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.STORAGE_FULL))
        assert r.downtime_seconds == 0.0

    def test_recovery_steps(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.STORAGE_FULL))
        assert len(r.recovery_steps) >= 2


# ===================================================================
# 9. LONG_RUNNING_QUERY tests
# ===================================================================


class TestLongRunningQuery:
    def test_no_downtime(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.LONG_RUNNING_QUERY))
        assert r.downtime_seconds == 0.0

    def test_connection_errors_proportional(self, simulator):
        cfg = _default_config(connection_pool_size=200)
        r = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.LONG_RUNNING_QUERY, 1.0)
        )
        assert r.connection_errors > 0

    def test_availability_degraded(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.LONG_RUNNING_QUERY, 1.0)
        )
        assert r.read_availability_percent < 100.0
        assert r.write_availability_percent < 100.0

    def test_no_data_loss(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.LONG_RUNNING_QUERY))
        assert r.data_loss_transactions == 0


# ===================================================================
# 10. DEADLOCK tests
# ===================================================================


class TestDeadlock:
    def test_no_downtime(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.DEADLOCK))
        assert r.downtime_seconds == 0.0

    def test_small_data_loss(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.DEADLOCK, 1.0))
        assert r.data_loss_transactions > 0
        assert r.data_loss_transactions <= 10

    def test_read_avail_full(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.DEADLOCK))
        assert r.read_availability_percent == 100.0

    def test_write_avail_degraded(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.DEADLOCK, 1.0))
        assert r.write_availability_percent < 100.0

    def test_recovery_steps(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.DEADLOCK))
        assert any("deadlock" in s.lower() for s in r.recovery_steps)


# ===================================================================
# 11. BACKUP_FAILURE tests
# ===================================================================


class TestBackupFailure:
    def test_no_downtime(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.BACKUP_FAILURE))
        assert r.downtime_seconds == 0.0

    def test_rpo_increases(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.BACKUP_FAILURE, 1.0))
        assert r.rpo_seconds > 0

    def test_full_availability(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.BACKUP_FAILURE))
        assert r.read_availability_percent == 100.0
        assert r.write_availability_percent == 100.0

    def test_no_data_loss(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.BACKUP_FAILURE))
        assert r.data_loss_transactions == 0

    def test_no_connection_errors(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.BACKUP_FAILURE))
        assert r.connection_errors == 0


# ===================================================================
# 12. SCHEMA_MIGRATION_FAILURE tests
# ===================================================================


class TestSchemaMigrationFailure:
    def test_write_avail_zero(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.SCHEMA_MIGRATION_FAILURE, 1.0)
        )
        assert r.write_availability_percent == 0.0

    def test_downtime_based_on_severity(self, simulator):
        cfg = _default_config()
        low = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.SCHEMA_MIGRATION_FAILURE, 0.1)
        )
        high = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.SCHEMA_MIGRATION_FAILURE, 1.0)
        )
        assert high.downtime_seconds > low.downtime_seconds

    def test_rto_matches_downtime(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.SCHEMA_MIGRATION_FAILURE, 0.5)
        )
        assert r.rto_seconds == r.downtime_seconds

    def test_read_avail_degraded(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.SCHEMA_MIGRATION_FAILURE, 1.0)
        )
        assert r.read_availability_percent < 100.0

    def test_recovery_steps(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.SCHEMA_MIGRATION_FAILURE)
        )
        assert any("Rollback" in s for s in r.recovery_steps)


# ===================================================================
# 13. FAILOVER_TIMEOUT tests
# ===================================================================


class TestFailoverTimeout:
    def test_both_avail_zero(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.FAILOVER_TIMEOUT))
        assert r.read_availability_percent == 0.0
        assert r.write_availability_percent == 0.0

    def test_high_downtime(self, simulator):
        cfg = _default_config(failover_time_seconds=30.0)
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.FAILOVER_TIMEOUT, 1.0))
        assert r.downtime_seconds >= 60.0

    def test_multi_az_reduces_downtime(self, simulator):
        s = _scenario(DBFailureMode.FAILOVER_TIMEOUT, 0.5)
        r_no = simulator.simulate_failover(_default_config(multi_az=False), s)
        r_az = simulator.simulate_failover(_default_config(multi_az=True), s)
        assert r_az.downtime_seconds < r_no.downtime_seconds

    def test_connection_errors(self, simulator):
        cfg = _default_config(max_connections=500)
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.FAILOVER_TIMEOUT, 1.0))
        assert r.connection_errors == 500

    def test_data_loss(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.FAILOVER_TIMEOUT, 1.0))
        assert r.data_loss_transactions > 0

    def test_recovery_steps_include_manual_promotion(self, simulator):
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.FAILOVER_TIMEOUT))
        assert any("Manual" in s for s in r.recovery_steps)


# ===================================================================
# 14. assess_replication_risk tests
# ===================================================================


class TestAssessReplicationRisk:
    def test_async_single_no_az(self, simulator):
        cfg = _default_config(
            replication_type=ReplicationType.ASYNC,
            replicas=1,
            read_replicas=0,
            multi_az=False,
        )
        risk = simulator.assess_replication_risk(cfg)
        assert risk == pytest.approx(1.0)  # maxed out

    def test_sync_multi_replica_multi_az(self, simulator):
        cfg = _default_config(
            replication_type=ReplicationType.SYNC,
            replicas=3,
            read_replicas=2,
            multi_az=True,
        )
        risk = simulator.assess_replication_risk(cfg)
        assert risk == 0.0

    def test_semi_sync_moderate(self, simulator):
        cfg = _default_config(
            replication_type=ReplicationType.SEMI_SYNC,
            replicas=2,
            read_replicas=1,
            multi_az=False,
        )
        risk = simulator.assess_replication_risk(cfg)
        assert 0.0 < risk < 1.0

    def test_risk_range(self, simulator):
        for rt in ReplicationType:
            for multi in [True, False]:
                cfg = _default_config(replication_type=rt, multi_az=multi)
                r = simulator.assess_replication_risk(cfg)
                assert 0.0 <= r <= 1.0


# ===================================================================
# 15. calculate_rpo tests
# ===================================================================


class TestCalculateRPO:
    def test_sync_zero(self, simulator):
        cfg = _default_config(replication_type=ReplicationType.SYNC)
        assert simulator.calculate_rpo(cfg) == 0.0

    def test_semi_sync(self, simulator):
        cfg = _default_config(replication_type=ReplicationType.SEMI_SYNC)
        assert simulator.calculate_rpo(cfg) == 1.0

    def test_async(self, simulator):
        cfg = _default_config(replication_type=ReplicationType.ASYNC)
        assert simulator.calculate_rpo(cfg) == 5.0

    @pytest.mark.parametrize("rt", list(ReplicationType))
    def test_rpo_non_negative(self, simulator, rt):
        cfg = _default_config(replication_type=rt)
        assert simulator.calculate_rpo(cfg) >= 0.0


# ===================================================================
# 16. calculate_rto tests
# ===================================================================


class TestCalculateRTO:
    def test_multi_az_reduces(self, simulator):
        cfg_no = _default_config(multi_az=False, replicas=2)
        cfg_az = _default_config(multi_az=True, replicas=2)
        assert simulator.calculate_rto(cfg_az) < simulator.calculate_rto(cfg_no)

    def test_no_replicas_doubles(self, simulator):
        cfg_one = _default_config(replicas=1, read_replicas=0)
        cfg_two = _default_config(replicas=2, read_replicas=1)
        assert simulator.calculate_rto(cfg_one) > simulator.calculate_rto(cfg_two)

    def test_base_failover_time(self, simulator):
        cfg = _default_config(failover_time_seconds=60.0, replicas=2, multi_az=False)
        assert simulator.calculate_rto(cfg) == 60.0

    def test_multi_az_factor(self, simulator):
        cfg = _default_config(failover_time_seconds=100.0, replicas=2, multi_az=True)
        assert simulator.calculate_rto(cfg) == pytest.approx(40.0)


# ===================================================================
# 17. recommend_config tests
# ===================================================================


class TestRecommendConfig:
    @pytest.mark.parametrize("engine", list(DBEngine))
    def test_high_avail(self, simulator, engine):
        cfg = simulator.recommend_config(engine, 99.99)
        assert cfg.engine == engine
        assert cfg.replicas == 3
        assert cfg.replication_type == ReplicationType.SYNC
        assert cfg.multi_az is True
        assert cfg.read_replicas >= 2

    @pytest.mark.parametrize("engine", list(DBEngine))
    def test_medium_avail(self, simulator, engine):
        cfg = simulator.recommend_config(engine, 99.9)
        assert cfg.replicas == 2
        assert cfg.replication_type == ReplicationType.SEMI_SYNC
        assert cfg.multi_az is True

    @pytest.mark.parametrize("engine", list(DBEngine))
    def test_low_avail(self, simulator, engine):
        cfg = simulator.recommend_config(engine, 99.0)
        assert cfg.replicas == 1
        assert cfg.replication_type == ReplicationType.ASYNC
        assert cfg.multi_az is False

    def test_high_avail_has_more_iops(self, simulator):
        high = simulator.recommend_config(DBEngine.AURORA, 99.99)
        low = simulator.recommend_config(DBEngine.AURORA, 99.0)
        assert high.iops > low.iops

    def test_high_avail_has_more_storage(self, simulator):
        high = simulator.recommend_config(DBEngine.AURORA, 99.99)
        low = simulator.recommend_config(DBEngine.AURORA, 99.0)
        assert high.storage_gb > low.storage_gb


# ===================================================================
# 18. generate_report tests
# ===================================================================


class TestGenerateReport:
    def test_empty_inputs(self, simulator):
        rpt = simulator.generate_report([], [])
        assert rpt.configs_tested == 0
        assert rpt.scenarios_run == 0
        assert rpt.overall_db_resilience == 0.0

    def test_single_config_single_scenario(self, simulator):
        cfg = _default_config()
        s = _scenario(DBFailureMode.PRIMARY_FAILURE)
        rpt = simulator.generate_report([cfg], [s])
        assert rpt.configs_tested == 1
        assert rpt.scenarios_run == 1
        assert len(rpt.results) == 1

    def test_multiple_combos(self, simulator):
        configs = [_default_config(), _default_config(engine=DBEngine.MYSQL)]
        scenarios = [
            _scenario(DBFailureMode.PRIMARY_FAILURE),
            _scenario(DBFailureMode.REPLICA_LAG),
        ]
        rpt = simulator.generate_report(configs, scenarios)
        assert rpt.configs_tested == 2
        assert rpt.scenarios_run == 4
        assert len(rpt.results) == 4

    def test_worst_rto_tracked(self, simulator):
        cfgs = [_default_config(failover_time_seconds=100.0)]
        scns = [_scenario(DBFailureMode.PRIMARY_FAILURE, 1.0)]
        rpt = simulator.generate_report(cfgs, scns)
        assert rpt.worst_rto_seconds > 0

    def test_worst_rpo_tracked(self, simulator):
        cfgs = [_default_config(replication_type=ReplicationType.ASYNC)]
        scns = [_scenario(DBFailureMode.PRIMARY_FAILURE, 1.0)]
        rpt = simulator.generate_report(cfgs, scns)
        assert rpt.worst_rpo_seconds > 0

    def test_resilience_score_range(self, simulator):
        cfgs = [_default_config()]
        scns = [_scenario(m) for m in DBFailureMode]
        rpt = simulator.generate_report(cfgs, scns)
        assert 0.0 <= rpt.overall_db_resilience <= 100.0

    def test_recommendations_present(self, simulator):
        cfg = _default_config(
            multi_az=False,
            replication_type=ReplicationType.ASYNC,
            read_replicas=0,
            replicas=1,
        )
        rpt = simulator.generate_report([cfg], [_scenario(DBFailureMode.PRIMARY_FAILURE)])
        assert len(rpt.recommendations) > 0

    def test_recommendations_deduplicated(self, simulator):
        cfg = _default_config(multi_az=False, replicas=1, read_replicas=0)
        scns = [_scenario(DBFailureMode.PRIMARY_FAILURE), _scenario(DBFailureMode.REPLICA_LAG)]
        rpt = simulator.generate_report([cfg], scns)
        assert len(rpt.recommendations) == len(set(rpt.recommendations))


# ===================================================================
# 19. Cross-engine scenario matrix
# ===================================================================


class TestCrossEngineMatrix:
    @pytest.mark.parametrize("engine", list(DBEngine))
    @pytest.mark.parametrize("mode", list(DBFailureMode))
    def test_all_engine_mode_combinations(self, simulator, engine, mode):
        cfg = _default_config(engine=engine)
        r = simulator.simulate_failover(cfg, _scenario(mode, 0.5))
        assert isinstance(r, DBFailoverResult)
        assert r.read_availability_percent >= 0.0
        assert r.write_availability_percent >= 0.0


# ===================================================================
# 20. Cross-replication-type tests
# ===================================================================


class TestCrossReplicationType:
    @pytest.mark.parametrize("rt", list(ReplicationType))
    def test_primary_failure_all_rep_types(self, simulator, rt):
        cfg = _default_config(replication_type=rt)
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE, 0.5))
        assert isinstance(r, DBFailoverResult)

    @pytest.mark.parametrize("rt", list(ReplicationType))
    def test_rpo_ordering(self, simulator, rt):
        cfg = _default_config(replication_type=rt)
        rpo = simulator.calculate_rpo(cfg)
        if rt == ReplicationType.SYNC:
            assert rpo == 0.0
        elif rt == ReplicationType.SEMI_SYNC:
            assert rpo == 1.0
        else:
            assert rpo == 5.0


# ===================================================================
# 21. Edge cases & boundary values
# ===================================================================


class TestEdgeCases:
    def test_severity_zero(self, simulator):
        cfg = _default_config()
        for mode in DBFailureMode:
            r = simulator.simulate_failover(cfg, _scenario(mode, 0.0))
            assert r.connection_errors >= 0
            assert r.data_loss_transactions >= 0

    def test_severity_one(self, simulator):
        cfg = _default_config()
        for mode in DBFailureMode:
            r = simulator.simulate_failover(cfg, _scenario(mode, 1.0))
            assert r.read_availability_percent >= 0.0
            assert r.write_availability_percent >= 0.0

    def test_max_connections_zero(self, simulator):
        cfg = _default_config(max_connections=0)
        r = simulator.simulate_failover(
            cfg, _scenario(DBFailureMode.CONNECTION_POOL_EXHAUSTION, 1.0)
        )
        assert r.connection_errors == 0

    def test_very_high_failover_time(self, simulator):
        cfg = _default_config(failover_time_seconds=9999.0)
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE, 1.0))
        assert r.downtime_seconds > 9999.0

    def test_target_node_field(self, simulator):
        s = _scenario(DBFailureMode.PRIMARY_FAILURE, target="replica-1")
        assert s.target_node == "replica-1"

    def test_report_with_all_modes(self, simulator):
        cfg = _default_config()
        scns = [_scenario(m, 0.5) for m in DBFailureMode]
        rpt = simulator.generate_report([cfg], scns)
        assert rpt.scenarios_run == len(DBFailureMode)

    def test_recommend_boundary_99_99(self, simulator):
        c1 = simulator.recommend_config(DBEngine.POSTGRESQL, 99.99)
        c2 = simulator.recommend_config(DBEngine.POSTGRESQL, 99.989)
        assert c1.replicas == 3
        assert c2.replicas == 2

    def test_recommend_boundary_99_9(self, simulator):
        c1 = simulator.recommend_config(DBEngine.POSTGRESQL, 99.9)
        c2 = simulator.recommend_config(DBEngine.POSTGRESQL, 99.89)
        assert c1.replicas == 2
        assert c2.replicas == 1

    def test_unknown_handler_fallback(self, simulator, monkeypatch):
        """When a failure mode has no registered handler, return default result."""
        from faultray.simulator import db_failover
        # Temporarily clear the handler map to force the fallback
        original = db_failover._FAILURE_HANDLERS.copy()
        monkeypatch.setattr(db_failover, "_FAILURE_HANDLERS", {})
        cfg = _default_config()
        r = simulator.simulate_failover(cfg, _scenario(DBFailureMode.PRIMARY_FAILURE))
        assert r.downtime_seconds == 0.0
        assert r.data_loss_transactions == 0
        # restore is done automatically by monkeypatch
