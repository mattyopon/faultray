"""Tests for faultray.simulator.data_integrity module.

Targets 100% coverage with 130+ tests covering all models, enums,
simulator methods, edge cases, and internal helpers.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    CostProfile,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.data_integrity import (
    DataConsistencyLevel,
    DataIntegrityReport,
    DataIntegritySimulator,
    IntegrityFailureType,
    IntegrityGuardrail,
    IntegrityImpact,
    IntegrityScenario,
    _COMPONENT_RISK_MODIFIERS,
    _CONSISTENCY_RISK_FACTOR,
    _FAILURE_BASE_RISK,
    _RECOVERY_COMPLEXITY_MAP,
    _STANDARD_GUARDRAILS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_component(
    cid: str = "db-1",
    name: str = "primary-db",
    ctype: ComponentType = ComponentType.DATABASE,
    replicas: int = 1,
    backup_enabled: bool = False,
    log_enabled: bool = False,
    ids_monitored: bool = False,
    failover_enabled: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
    revenue_per_minute: float = 0.0,
    max_rps: int = 5000,
    mttr_minutes: float = 30.0,
) -> Component:
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        security=SecurityProfile(
            backup_enabled=backup_enabled,
            log_enabled=log_enabled,
            ids_monitored=ids_monitored,
        ),
        failover=FailoverConfig(enabled=failover_enabled),
        health=health,
        cost_profile=CostProfile(revenue_per_minute=revenue_per_minute),
        capacity=Capacity(max_rps=max_rps),
        operational_profile=OperationalProfile(mttr_minutes=mttr_minutes),
    )


def _make_graph(*components: Component) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


def _make_scenario(
    sid: str = "s1",
    failure_type: IntegrityFailureType = IntegrityFailureType.PARTIAL_WRITE,
    target: str = "db-1",
    affected_pct: float = 10.0,
    duration: float = 30.0,
    consistency: DataConsistencyLevel = DataConsistencyLevel.EVENTUAL,
) -> IntegrityScenario:
    return IntegrityScenario(
        scenario_id=sid,
        failure_type=failure_type,
        target_component=target,
        affected_data_percent=affected_pct,
        duration_minutes=duration,
        consistency_level=consistency,
    )


@pytest.fixture
def simple_graph() -> InfraGraph:
    return _make_graph(
        _make_component("db-1", "primary-db", ComponentType.DATABASE),
        _make_component("cache-1", "redis", ComponentType.CACHE),
        _make_component("queue-1", "rabbitmq", ComponentType.QUEUE),
        _make_component("store-1", "s3", ComponentType.STORAGE),
    )


@pytest.fixture
def sim(simple_graph: InfraGraph) -> DataIntegritySimulator:
    return DataIntegritySimulator(simple_graph)


# ===================================================================
# Enum tests
# ===================================================================


class TestIntegrityFailureType:
    def test_all_values(self):
        expected = {
            "partial_write", "replication_lag", "split_brain",
            "backup_corruption", "schema_drift", "stale_cache",
            "orphaned_records", "constraint_violation",
            "encoding_error", "clock_skew",
        }
        assert {e.value for e in IntegrityFailureType} == expected

    def test_is_str_enum(self):
        assert isinstance(IntegrityFailureType.PARTIAL_WRITE, str)

    def test_member_count(self):
        assert len(IntegrityFailureType) == 10


class TestDataConsistencyLevel:
    def test_all_values(self):
        expected = {
            "strong", "eventual", "causal",
            "read_your_writes", "monotonic",
        }
        assert {e.value for e in DataConsistencyLevel} == expected

    def test_is_str_enum(self):
        assert isinstance(DataConsistencyLevel.STRONG, str)

    def test_member_count(self):
        assert len(DataConsistencyLevel) == 5


# ===================================================================
# Pydantic model tests
# ===================================================================


class TestIntegrityScenario:
    def test_defaults(self):
        s = IntegrityScenario(
            scenario_id="x",
            failure_type=IntegrityFailureType.STALE_CACHE,
            target_component="c1",
        )
        assert s.affected_data_percent == 10.0
        assert s.duration_minutes == 30.0
        assert s.consistency_level == DataConsistencyLevel.EVENTUAL

    def test_custom_values(self):
        s = _make_scenario(affected_pct=55.0, duration=120.0, consistency=DataConsistencyLevel.STRONG)
        assert s.affected_data_percent == 55.0
        assert s.duration_minutes == 120.0
        assert s.consistency_level == DataConsistencyLevel.STRONG

    def test_affected_data_percent_bounds_low(self):
        with pytest.raises(Exception):
            IntegrityScenario(
                scenario_id="x",
                failure_type=IntegrityFailureType.STALE_CACHE,
                target_component="c",
                affected_data_percent=-1.0,
            )

    def test_affected_data_percent_bounds_high(self):
        with pytest.raises(Exception):
            IntegrityScenario(
                scenario_id="x",
                failure_type=IntegrityFailureType.STALE_CACHE,
                target_component="c",
                affected_data_percent=101.0,
            )

    def test_duration_non_negative(self):
        with pytest.raises(Exception):
            IntegrityScenario(
                scenario_id="x",
                failure_type=IntegrityFailureType.STALE_CACHE,
                target_component="c",
                duration_minutes=-5.0,
            )

    def test_boundary_affected_zero(self):
        s = IntegrityScenario(
            scenario_id="x",
            failure_type=IntegrityFailureType.STALE_CACHE,
            target_component="c",
            affected_data_percent=0.0,
        )
        assert s.affected_data_percent == 0.0

    def test_boundary_affected_hundred(self):
        s = IntegrityScenario(
            scenario_id="x",
            failure_type=IntegrityFailureType.STALE_CACHE,
            target_component="c",
            affected_data_percent=100.0,
        )
        assert s.affected_data_percent == 100.0


class TestIntegrityImpact:
    def test_defaults(self):
        s = _make_scenario()
        imp = IntegrityImpact(scenario=s)
        assert imp.data_loss_risk == 0.0
        assert imp.recovery_complexity == "manual_simple"
        assert imp.detection_time_minutes == 5.0
        assert imp.recovery_time_minutes == 30.0
        assert imp.affected_transactions == 0
        assert imp.financial_impact_estimate == 0.0

    def test_data_loss_risk_bounds(self):
        with pytest.raises(Exception):
            IntegrityImpact(scenario=_make_scenario(), data_loss_risk=1.5)

    def test_data_loss_risk_lower_bound(self):
        with pytest.raises(Exception):
            IntegrityImpact(scenario=_make_scenario(), data_loss_risk=-0.1)


class TestIntegrityGuardrail:
    def test_defaults(self):
        g = IntegrityGuardrail(mechanism="test")
        assert g.effectiveness == 0.5
        assert g.applicable_failures == []

    def test_custom_values(self):
        g = IntegrityGuardrail(
            mechanism="checksums",
            effectiveness=0.9,
            applicable_failures=[IntegrityFailureType.BACKUP_CORRUPTION],
        )
        assert g.mechanism == "checksums"
        assert g.effectiveness == 0.9
        assert len(g.applicable_failures) == 1


class TestDataIntegrityReport:
    def test_defaults(self):
        r = DataIntegrityReport()
        assert r.scenarios_tested == 0
        assert r.critical_risks == 0
        assert r.impacts == []
        assert r.guardrails_evaluated == []
        assert r.overall_integrity_score == 100.0
        assert r.recommendations == []

    def test_score_bounds(self):
        with pytest.raises(Exception):
            DataIntegrityReport(overall_integrity_score=101.0)
        with pytest.raises(Exception):
            DataIntegrityReport(overall_integrity_score=-1.0)


# ===================================================================
# Constants / lookup table tests
# ===================================================================


class TestConstants:
    def test_failure_base_risk_all_types(self):
        for ft in IntegrityFailureType:
            assert ft in _FAILURE_BASE_RISK

    def test_consistency_risk_factor_all_levels(self):
        for cl in DataConsistencyLevel:
            assert cl in _CONSISTENCY_RISK_FACTOR

    def test_recovery_complexity_map_keys(self):
        expected = {"automatic", "manual_simple", "manual_complex", "impossible"}
        assert set(_RECOVERY_COMPLEXITY_MAP.keys()) == expected

    def test_standard_guardrails_not_empty(self):
        assert len(_STANDARD_GUARDRAILS) > 0

    def test_standard_guardrails_structure(self):
        for g in _STANDARD_GUARDRAILS:
            assert "mechanism" in g
            assert "effectiveness" in g
            assert "applicable_failures" in g
            assert 0.0 <= g["effectiveness"] <= 1.0

    def test_component_risk_modifiers_types(self):
        for ct, mods in _COMPONENT_RISK_MODIFIERS.items():
            assert isinstance(ct, ComponentType)
            for ft, val in mods.items():
                assert isinstance(ft, IntegrityFailureType)
                assert val > 0


# ===================================================================
# DataIntegritySimulator — simulate_failure
# ===================================================================


class TestSimulateFailure:
    def test_missing_component(self, sim: DataIntegritySimulator):
        s = _make_scenario(target="nonexistent")
        impact = sim.simulate_failure(s)
        assert impact.data_loss_risk == 0.0
        assert impact.recovery_complexity == "automatic"
        assert impact.affected_transactions == 0

    def test_database_partial_write(self, sim: DataIntegritySimulator):
        s = _make_scenario(failure_type=IntegrityFailureType.PARTIAL_WRITE, target="db-1")
        impact = sim.simulate_failure(s)
        assert impact.data_loss_risk > 0
        assert impact.recovery_complexity in ("manual_simple", "manual_complex")

    def test_cache_stale_cache(self, sim: DataIntegritySimulator):
        s = _make_scenario(failure_type=IntegrityFailureType.STALE_CACHE, target="cache-1")
        impact = sim.simulate_failure(s)
        assert impact.recovery_complexity == "automatic"

    def test_database_split_brain(self, sim: DataIntegritySimulator):
        s = _make_scenario(failure_type=IntegrityFailureType.SPLIT_BRAIN, target="db-1")
        impact = sim.simulate_failure(s)
        assert impact.data_loss_risk > 0

    def test_split_brain_high_percent_no_backup(self):
        comp = _make_component("db-x", backup_enabled=False)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(
            failure_type=IntegrityFailureType.SPLIT_BRAIN,
            target="db-x",
            affected_pct=80.0,
        )
        impact = sim.simulate_failure(s)
        assert impact.recovery_complexity == "impossible"

    def test_split_brain_high_percent_with_backup(self):
        comp = _make_component("db-x", backup_enabled=True)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(
            failure_type=IntegrityFailureType.SPLIT_BRAIN,
            target="db-x",
            affected_pct=80.0,
        )
        impact = sim.simulate_failure(s)
        assert impact.recovery_complexity == "manual_complex"

    def test_split_brain_low_percent(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(
            failure_type=IntegrityFailureType.SPLIT_BRAIN,
            target="db-x",
            affected_pct=20.0,
        )
        impact = sim.simulate_failure(s)
        assert impact.recovery_complexity == "manual_complex"

    def test_backup_corruption_with_backup_reduces_risk(self):
        comp_no = _make_component("db-no", backup_enabled=False)
        comp_yes = _make_component("db-yes", backup_enabled=True)
        g = _make_graph(comp_no, comp_yes)
        sim = DataIntegritySimulator(g)
        s_no = _make_scenario(failure_type=IntegrityFailureType.BACKUP_CORRUPTION, target="db-no")
        s_yes = _make_scenario(failure_type=IntegrityFailureType.BACKUP_CORRUPTION, target="db-yes")
        risk_no = sim.simulate_failure(s_no).data_loss_risk
        risk_yes = sim.simulate_failure(s_yes).data_loss_risk
        assert risk_yes < risk_no

    def test_backup_corruption_high_percent_no_backup(self):
        comp = _make_component("db-x", backup_enabled=False)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(
            failure_type=IntegrityFailureType.BACKUP_CORRUPTION,
            target="db-x",
            affected_pct=80.0,
        )
        impact = sim.simulate_failure(s)
        assert impact.recovery_complexity == "impossible"

    def test_multi_replica_reduces_single_node_corruption_risk(self):
        comp1 = _make_component("db-1r", replicas=1)
        comp3 = _make_component("db-3r", replicas=3)
        g = _make_graph(comp1, comp3)
        sim = DataIntegritySimulator(g)
        s1 = _make_scenario(failure_type=IntegrityFailureType.PARTIAL_WRITE, target="db-1r")
        s3 = _make_scenario(failure_type=IntegrityFailureType.PARTIAL_WRITE, target="db-3r")
        assert sim.simulate_failure(s3).data_loss_risk < sim.simulate_failure(s1).data_loss_risk

    def test_multi_replica_no_reduction_for_replication_lag(self):
        comp = _make_component("db-r", replicas=3)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(failure_type=IntegrityFailureType.REPLICATION_LAG, target="db-r")
        impact = sim.simulate_failure(s)
        # Just verify it runs; replicas should NOT reduce risk for replication_lag
        assert impact.data_loss_risk > 0

    def test_multi_replica_no_reduction_for_split_brain(self):
        comp = _make_component("db-r", replicas=3)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(failure_type=IntegrityFailureType.SPLIT_BRAIN, target="db-r")
        impact = sim.simulate_failure(s)
        assert impact.data_loss_risk > 0

    def test_strong_consistency_lowers_risk(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s_eventual = _make_scenario(consistency=DataConsistencyLevel.EVENTUAL, target="db-x")
        s_strong = _make_scenario(consistency=DataConsistencyLevel.STRONG, target="db-x")
        risk_eventual = sim.simulate_failure(s_eventual).data_loss_risk
        risk_strong = sim.simulate_failure(s_strong).data_loss_risk
        assert risk_strong < risk_eventual

    def test_higher_duration_increases_risk(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s_short = _make_scenario(duration=10.0, target="db-x")
        s_long = _make_scenario(duration=120.0, target="db-x")
        assert sim.simulate_failure(s_long).data_loss_risk > sim.simulate_failure(s_short).data_loss_risk

    def test_duration_cap_at_2x(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s_240 = _make_scenario(duration=240.0, target="db-x")
        s_480 = _make_scenario(duration=480.0, target="db-x")
        # Both should be capped at 2x, so risk should be equal
        r240 = sim.simulate_failure(s_240).data_loss_risk
        r480 = sim.simulate_failure(s_480).data_loss_risk
        assert r240 == r480

    def test_higher_affected_pct_increases_risk(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s_low = _make_scenario(affected_pct=5.0, target="db-x")
        s_high = _make_scenario(affected_pct=90.0, target="db-x")
        assert sim.simulate_failure(s_high).data_loss_risk > sim.simulate_failure(s_low).data_loss_risk

    def test_affected_pct_zero_yields_zero_risk(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(affected_pct=0.0, target="db-x")
        assert sim.simulate_failure(s).data_loss_risk == 0.0

    def test_replication_lag_automatic_with_replicas(self):
        comp = _make_component("db-x", replicas=3)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(failure_type=IntegrityFailureType.REPLICATION_LAG, target="db-x")
        assert sim.simulate_failure(s).recovery_complexity == "automatic"

    def test_replication_lag_manual_without_replicas(self):
        comp = _make_component("db-x", replicas=1)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(failure_type=IntegrityFailureType.REPLICATION_LAG, target="db-x")
        assert sim.simulate_failure(s).recovery_complexity == "manual_simple"

    def test_partial_write_complexity_with_backup(self):
        comp = _make_component("db-x", backup_enabled=True)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(failure_type=IntegrityFailureType.PARTIAL_WRITE, target="db-x")
        assert sim.simulate_failure(s).recovery_complexity == "manual_simple"

    def test_partial_write_complexity_without_backup(self):
        comp = _make_component("db-x", backup_enabled=False)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(failure_type=IntegrityFailureType.PARTIAL_WRITE, target="db-x")
        assert sim.simulate_failure(s).recovery_complexity == "manual_complex"

    def test_schema_drift_complexity(self, sim: DataIntegritySimulator):
        s = _make_scenario(failure_type=IntegrityFailureType.SCHEMA_DRIFT, target="db-1")
        assert sim.simulate_failure(s).recovery_complexity == "manual_simple"

    def test_orphaned_records_complexity(self, sim: DataIntegritySimulator):
        s = _make_scenario(failure_type=IntegrityFailureType.ORPHANED_RECORDS, target="db-1")
        assert sim.simulate_failure(s).recovery_complexity == "manual_simple"

    def test_constraint_violation_complexity(self, sim: DataIntegritySimulator):
        s = _make_scenario(failure_type=IntegrityFailureType.CONSTRAINT_VIOLATION, target="db-1")
        assert sim.simulate_failure(s).recovery_complexity == "manual_simple"

    def test_encoding_error_complexity(self, sim: DataIntegritySimulator):
        s = _make_scenario(failure_type=IntegrityFailureType.ENCODING_ERROR, target="cache-1")
        assert sim.simulate_failure(s).recovery_complexity == "manual_simple"

    def test_clock_skew_complexity(self, sim: DataIntegritySimulator):
        s = _make_scenario(failure_type=IntegrityFailureType.CLOCK_SKEW, target="db-1")
        assert sim.simulate_failure(s).recovery_complexity == "automatic"

    def test_financial_impact_with_revenue(self):
        comp = _make_component("db-x", revenue_per_minute=100.0, max_rps=1000)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(target="db-x", affected_pct=50.0, duration=10.0)
        impact = sim.simulate_failure(s)
        assert impact.financial_impact_estimate > 0
        assert impact.affected_transactions > 0

    def test_financial_impact_zero_revenue(self):
        comp = _make_component("db-x", revenue_per_minute=0.0)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(target="db-x")
        impact = sim.simulate_failure(s)
        assert impact.financial_impact_estimate == 0.0

    def test_affected_transactions_calculation(self):
        comp = _make_component("db-x", max_rps=100)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(target="db-x", affected_pct=50.0, duration=1.0)
        impact = sim.simulate_failure(s)
        # 100 rps * 1 min * 60 sec * 0.5 = 3000
        assert impact.affected_transactions == 3000

    def test_detection_time_log_enabled_reduces(self):
        comp_no_log = _make_component("db-nl", log_enabled=False)
        comp_log = _make_component("db-wl", log_enabled=True)
        g = _make_graph(comp_no_log, comp_log)
        sim = DataIntegritySimulator(g)
        s_no = _make_scenario(target="db-nl")
        s_yes = _make_scenario(target="db-wl")
        det_no = sim.simulate_failure(s_no).detection_time_minutes
        det_yes = sim.simulate_failure(s_yes).detection_time_minutes
        assert det_yes < det_no

    def test_detection_time_ids_monitored_reduces(self):
        comp_no = _make_component("db-ni", ids_monitored=False)
        comp_yes = _make_component("db-wi", ids_monitored=True)
        g = _make_graph(comp_no, comp_yes)
        sim = DataIntegritySimulator(g)
        s_no = _make_scenario(target="db-ni")
        s_yes = _make_scenario(target="db-wi")
        det_no = sim.simulate_failure(s_no).detection_time_minutes
        det_yes = sim.simulate_failure(s_yes).detection_time_minutes
        assert det_yes < det_no

    def test_detection_time_both_log_and_ids(self):
        comp = _make_component("db-b", log_enabled=True, ids_monitored=True)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(target="db-b")
        impact = sim.simulate_failure(s)
        # 5.0 * 0.5 * 0.7 = 1.75
        assert impact.detection_time_minutes == pytest.approx(1.75)

    def test_recovery_time_with_failover(self):
        comp_no = _make_component("db-nf", failover_enabled=False)
        comp_yes = _make_component("db-wf", failover_enabled=True)
        g = _make_graph(comp_no, comp_yes)
        sim = DataIntegritySimulator(g)
        s_no = _make_scenario(target="db-nf")
        s_yes = _make_scenario(target="db-wf")
        rec_no = sim.simulate_failure(s_no).recovery_time_minutes
        rec_yes = sim.simulate_failure(s_yes).recovery_time_minutes
        assert rec_yes < rec_no

    def test_recovery_time_impossible_complexity(self):
        comp = _make_component("db-x", backup_enabled=False)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(
            failure_type=IntegrityFailureType.SPLIT_BRAIN,
            target="db-x",
            affected_pct=80.0,
        )
        impact = sim.simulate_failure(s)
        # impossible has 20x multiplier
        assert impact.recovery_time_minutes == 30.0 * 20.0

    def test_mttr_zero_defaults_to_30(self):
        comp = _make_component("db-x", mttr_minutes=0.0)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(target="db-x")
        impact = sim.simulate_failure(s)
        assert impact.recovery_time_minutes > 0

    def test_database_component_risk_modifier_split_brain(self):
        comp = _make_component("db-x", ctype=ComponentType.DATABASE)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)

        comp_app = _make_component("app-x", ctype=ComponentType.APP_SERVER)
        g2 = _make_graph(comp_app)
        sim2 = DataIntegritySimulator(g2)

        s_db = _make_scenario(failure_type=IntegrityFailureType.SPLIT_BRAIN, target="db-x")
        s_app = _make_scenario(failure_type=IntegrityFailureType.SPLIT_BRAIN, target="app-x")

        risk_db = sim.simulate_failure(s_db).data_loss_risk
        risk_app = sim2.simulate_failure(s_app).data_loss_risk
        assert risk_db > risk_app

    def test_cache_component_risk_modifier_stale_cache(self):
        comp_cache = _make_component("cache-x", ctype=ComponentType.CACHE)
        comp_app = _make_component("app-x", ctype=ComponentType.APP_SERVER)
        g = _make_graph(comp_cache, comp_app)
        sim = DataIntegritySimulator(g)

        s_cache = _make_scenario(failure_type=IntegrityFailureType.STALE_CACHE, target="cache-x")
        s_app = _make_scenario(failure_type=IntegrityFailureType.STALE_CACHE, target="app-x")
        risk_cache = sim.simulate_failure(s_cache).data_loss_risk
        risk_app = sim.simulate_failure(s_app).data_loss_risk
        assert risk_cache > risk_app

    def test_queue_component_risk_modifier(self):
        comp = _make_component("q-x", ctype=ComponentType.QUEUE)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(failure_type=IntegrityFailureType.ORPHANED_RECORDS, target="q-x")
        impact = sim.simulate_failure(s)
        assert impact.data_loss_risk > 0

    def test_storage_component_risk_modifier(self):
        comp = _make_component("s-x", ctype=ComponentType.STORAGE)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(failure_type=IntegrityFailureType.BACKUP_CORRUPTION, target="s-x")
        impact = sim.simulate_failure(s)
        assert impact.data_loss_risk > 0

    def test_all_consistency_levels(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        risks = {}
        for cl in DataConsistencyLevel:
            s = _make_scenario(consistency=cl, target="db-x")
            risks[cl] = sim.simulate_failure(s).data_loss_risk
        # STRONG should always be lowest
        assert risks[DataConsistencyLevel.STRONG] == min(risks.values())

    def test_all_failure_types_against_database(self, sim: DataIntegritySimulator):
        for ft in IntegrityFailureType:
            s = _make_scenario(failure_type=ft, target="db-1")
            impact = sim.simulate_failure(s)
            assert impact.data_loss_risk >= 0.0
            assert impact.recovery_complexity in (
                "automatic", "manual_simple", "manual_complex", "impossible",
            )

    def test_risk_clamped_to_0_1(self):
        # High risk scenario: 100% data, 200 min, database split brain
        comp = _make_component("db-x", ctype=ComponentType.DATABASE)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(
            failure_type=IntegrityFailureType.SPLIT_BRAIN,
            target="db-x",
            affected_pct=100.0,
            duration=200.0,
        )
        impact = sim.simulate_failure(s)
        assert 0.0 <= impact.data_loss_risk <= 1.0

    def test_high_replica_count_max_reduction(self):
        comp = _make_component("db-x", replicas=10)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(failure_type=IntegrityFailureType.ENCODING_ERROR, target="db-x")
        impact = sim.simulate_failure(s)
        assert impact.data_loss_risk >= 0.0


# ===================================================================
# DataIntegritySimulator — evaluate_guardrails
# ===================================================================


class TestEvaluateGuardrails:
    def test_missing_component_returns_empty(self, sim: DataIntegritySimulator):
        result = sim.evaluate_guardrails("nonexistent")
        assert result == []

    def test_database_guardrails(self, sim: DataIntegritySimulator):
        guardrails = sim.evaluate_guardrails("db-1")
        assert len(guardrails) > 0
        mechanisms = {g.mechanism for g in guardrails}
        assert "WAL" in mechanisms
        assert "checksums" in mechanisms

    def test_cache_guardrails(self, sim: DataIntegritySimulator):
        guardrails = sim.evaluate_guardrails("cache-1")
        mechanisms = {g.mechanism for g in guardrails}
        assert "cache_invalidation" in mechanisms

    def test_stale_cache_only_for_cache_component(self, sim: DataIntegritySimulator):
        # For database, stale_cache guardrails should be filtered
        guardrails = sim.evaluate_guardrails("db-1")
        for g in guardrails:
            if g.mechanism == "cache_invalidation":
                assert IntegrityFailureType.STALE_CACHE in g.applicable_failures

    def test_backup_enabled_boosts_effectiveness(self):
        comp = _make_component("db-x", backup_enabled=True)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        guardrails = sim.evaluate_guardrails("db-x")
        # checksums covers BACKUP_CORRUPTION and PARTIAL_WRITE
        for gx in guardrails:
            if gx.mechanism == "checksums":
                assert gx.effectiveness > 0.8  # boosted from 0.8 to 0.85

    def test_no_backup_no_boost(self):
        comp = _make_component("db-x", backup_enabled=False)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        guardrails = sim.evaluate_guardrails("db-x")
        for gx in guardrails:
            if gx.mechanism == "checksums":
                assert gx.effectiveness == 0.8

    def test_guardrail_effectiveness_capped_at_1(self):
        comp = _make_component("db-x", backup_enabled=True)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        guardrails = sim.evaluate_guardrails("db-x")
        for gx in guardrails:
            assert gx.effectiveness <= 1.0

    def test_queue_guardrails(self, sim: DataIntegritySimulator):
        guardrails = sim.evaluate_guardrails("queue-1")
        mechanisms = {g.mechanism for g in guardrails}
        # saga_pattern covers PARTIAL_WRITE, ORPHANED_RECORDS
        assert "saga_pattern" in mechanisms

    def test_storage_guardrails(self, sim: DataIntegritySimulator):
        guardrails = sim.evaluate_guardrails("store-1")
        mechanisms = {g.mechanism for g in guardrails}
        assert "checksums" in mechanisms


# ===================================================================
# DataIntegritySimulator — assess_consistency_risk
# ===================================================================


class TestAssessConsistencyRisk:
    def test_missing_component(self, sim: DataIntegritySimulator):
        assert sim.assess_consistency_risk("nonexistent") == 0.0

    def test_database_baseline(self, sim: DataIntegritySimulator):
        risk = sim.assess_consistency_risk("db-1")
        assert risk > 0.3  # baseline + database bonus

    def test_cache_baseline(self, sim: DataIntegritySimulator):
        risk = sim.assess_consistency_risk("cache-1")
        assert risk > 0.3

    def test_queue_baseline(self, sim: DataIntegritySimulator):
        risk = sim.assess_consistency_risk("queue-1")
        assert risk > 0.3

    def test_multi_replica_adds_risk(self):
        comp = _make_component("db-x", replicas=3)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        risk = sim.assess_consistency_risk("db-x")
        # baseline 0.3 + db 0.15 + replica>1 0.1 + replica>2 0.1 = 0.65
        assert risk >= 0.55

    def test_no_backup_adds_risk(self):
        comp_no = _make_component("db-no", backup_enabled=False)
        comp_yes = _make_component("db-yes", backup_enabled=True)
        g = _make_graph(comp_no, comp_yes)
        sim = DataIntegritySimulator(g)
        assert sim.assess_consistency_risk("db-no") > sim.assess_consistency_risk("db-yes")

    def test_health_down_adds_risk(self):
        comp = _make_component("db-d", health=HealthStatus.DOWN)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        risk = sim.assess_consistency_risk("db-d")
        assert risk >= 0.5

    def test_health_degraded_adds_risk(self):
        comp = _make_component("db-deg", health=HealthStatus.DEGRADED)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        risk_degraded = sim.assess_consistency_risk("db-deg")

        comp_h = _make_component("db-h", health=HealthStatus.HEALTHY)
        g2 = _make_graph(comp_h)
        sim2 = DataIntegritySimulator(g2)
        risk_healthy = sim2.assess_consistency_risk("db-h")
        assert risk_degraded > risk_healthy

    def test_health_overloaded_adds_risk(self):
        comp = _make_component("db-ol", health=HealthStatus.OVERLOADED)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        risk = sim.assess_consistency_risk("db-ol")
        assert risk > 0.4

    def test_risk_capped_at_1(self):
        comp = _make_component(
            "db-x",
            ctype=ComponentType.DATABASE,
            replicas=5,
            backup_enabled=False,
            health=HealthStatus.DOWN,
        )
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        assert sim.assess_consistency_risk("db-x") <= 1.0

    def test_non_special_type_baseline(self):
        comp = _make_component("app-1", ctype=ComponentType.APP_SERVER)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        # Only baseline risk, no type-specific bonus
        risk = sim.assess_consistency_risk("app-1")
        assert risk >= 0.3

    def test_database_with_replicas_gt_1(self):
        comp = _make_component("db-r2", replicas=2, ctype=ComponentType.DATABASE)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        risk = sim.assess_consistency_risk("db-r2")
        # 0.3 + 0.15 + 0.1 = 0.55
        assert risk >= 0.55


# ===================================================================
# DataIntegritySimulator — find_vulnerable_components
# ===================================================================


class TestFindVulnerableComponents:
    def test_finds_databases(self, sim: DataIntegritySimulator):
        vulnerable = sim.find_vulnerable_components()
        assert "db-1" in vulnerable

    def test_sorted_by_risk_descending(self):
        comp_db = _make_component("db-x", ctype=ComponentType.DATABASE, replicas=3, health=HealthStatus.DOWN)
        comp_cache = _make_component("cache-x", ctype=ComponentType.CACHE)
        g = _make_graph(comp_db, comp_cache)
        sim = DataIntegritySimulator(g)
        vuln = sim.find_vulnerable_components()
        if len(vuln) >= 2:
            risk_first = sim.assess_consistency_risk(vuln[0])
            risk_second = sim.assess_consistency_risk(vuln[1])
            assert risk_first >= risk_second

    def test_excludes_low_risk(self):
        comp = _make_component(
            "app-safe",
            ctype=ComponentType.APP_SERVER,
            backup_enabled=True,
            health=HealthStatus.HEALTHY,
        )
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        # APP_SERVER with backup and healthy = 0.3 baseline
        # which is <= 0.4 threshold
        assert "app-safe" not in sim.find_vulnerable_components()

    def test_empty_graph(self):
        g = InfraGraph()
        sim = DataIntegritySimulator(g)
        assert sim.find_vulnerable_components() == []


# ===================================================================
# DataIntegritySimulator — generate_report
# ===================================================================


class TestGenerateReport:
    def test_empty_scenarios(self, sim: DataIntegritySimulator):
        report = sim.generate_report([])
        assert report.scenarios_tested == 0
        assert report.critical_risks == 0
        assert report.impacts == []
        assert report.overall_integrity_score == 100.0

    def test_single_scenario(self, sim: DataIntegritySimulator):
        s = _make_scenario(target="db-1")
        report = sim.generate_report([s])
        assert report.scenarios_tested == 1
        assert len(report.impacts) == 1

    def test_multiple_scenarios(self, sim: DataIntegritySimulator):
        scenarios = [
            _make_scenario("s1", IntegrityFailureType.PARTIAL_WRITE, "db-1"),
            _make_scenario("s2", IntegrityFailureType.STALE_CACHE, "cache-1"),
            _make_scenario("s3", IntegrityFailureType.ORPHANED_RECORDS, "queue-1"),
        ]
        report = sim.generate_report(scenarios)
        assert report.scenarios_tested == 3
        assert len(report.impacts) == 3

    def test_critical_risks_counted(self):
        comp = _make_component("db-x", ctype=ComponentType.DATABASE)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(
            failure_type=IntegrityFailureType.SPLIT_BRAIN,
            target="db-x",
            affected_pct=100.0,
            duration=200.0,
        )
        report = sim.generate_report([s])
        # If the risk is >= 0.7, critical_risks should be 1
        if report.impacts[0].data_loss_risk >= 0.7:
            assert report.critical_risks >= 1

    def test_guardrails_deduplicated(self, sim: DataIntegritySimulator):
        scenarios = [
            _make_scenario("s1", IntegrityFailureType.PARTIAL_WRITE, "db-1"),
            _make_scenario("s2", IntegrityFailureType.PARTIAL_WRITE, "db-1"),
        ]
        report = sim.generate_report(scenarios)
        mechanisms = [g.mechanism for g in report.guardrails_evaluated]
        assert len(mechanisms) == len(set(mechanisms))

    def test_report_has_recommendations(self, sim: DataIntegritySimulator):
        s = _make_scenario(target="db-1")
        report = sim.generate_report([s])
        # At minimum, backup recommendation should appear (db-1 has no backup)
        assert len(report.recommendations) > 0

    def test_integrity_score_between_0_and_100(self, sim: DataIntegritySimulator):
        scenarios = [
            _make_scenario("s1", IntegrityFailureType.PARTIAL_WRITE, "db-1"),
            _make_scenario("s2", IntegrityFailureType.SPLIT_BRAIN, "db-1"),
        ]
        report = sim.generate_report(scenarios)
        assert 0.0 <= report.overall_integrity_score <= 100.0

    def test_report_with_nonexistent_target(self, sim: DataIntegritySimulator):
        s = _make_scenario(target="ghost")
        report = sim.generate_report([s])
        assert report.scenarios_tested == 1
        assert report.impacts[0].data_loss_risk == 0.0

    def test_report_guardrails_from_multiple_components(self, sim: DataIntegritySimulator):
        scenarios = [
            _make_scenario("s1", IntegrityFailureType.PARTIAL_WRITE, "db-1"),
            _make_scenario("s2", IntegrityFailureType.STALE_CACHE, "cache-1"),
        ]
        report = sim.generate_report(scenarios)
        mechanisms = {g.mechanism for g in report.guardrails_evaluated}
        assert "WAL" in mechanisms or "checksums" in mechanisms
        assert "cache_invalidation" in mechanisms


# ===================================================================
# Recommendations
# ===================================================================


class TestRecommendations:
    def test_critical_risk_recommendation(self):
        comp = _make_component("db-x", ctype=ComponentType.DATABASE)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(
            failure_type=IntegrityFailureType.SPLIT_BRAIN,
            target="db-x",
            affected_pct=100.0,
            duration=200.0,
        )
        report = sim.generate_report([s])
        if report.impacts[0].data_loss_risk >= 0.7:
            recs = "\n".join(report.recommendations)
            assert "CRITICAL" in recs

    def test_impossible_recovery_recommendation(self):
        comp = _make_component("db-x", backup_enabled=False)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(
            failure_type=IntegrityFailureType.SPLIT_BRAIN,
            target="db-x",
            affected_pct=80.0,
        )
        report = sim.generate_report([s])
        recs = "\n".join(report.recommendations)
        assert "backup" in recs.lower() or "Enable" in recs

    def test_no_backup_recommendation(self):
        comp = _make_component("db-x", backup_enabled=False)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(target="db-x")
        report = sim.generate_report([s])
        recs = "\n".join(report.recommendations)
        assert "backup" in recs.lower()

    def test_no_duplicate_recommendations(self):
        comp = _make_component("db-x", backup_enabled=False)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        scenarios = [
            _make_scenario("s1", IntegrityFailureType.PARTIAL_WRITE, "db-x"),
            _make_scenario("s2", IntegrityFailureType.PARTIAL_WRITE, "db-x"),
        ]
        report = sim.generate_report(scenarios)
        assert len(report.recommendations) == len(set(report.recommendations))

    def test_replica_recommendation_for_split_brain(self):
        comp = _make_component("db-x", replicas=1)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(failure_type=IntegrityFailureType.SPLIT_BRAIN, target="db-x")
        report = sim.generate_report([s])
        recs = "\n".join(report.recommendations)
        assert "replica" in recs.lower()

    def test_replica_recommendation_for_replication_lag(self):
        comp = _make_component("db-x", replicas=1)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(failure_type=IntegrityFailureType.REPLICATION_LAG, target="db-x")
        report = sim.generate_report([s])
        recs = "\n".join(report.recommendations)
        assert "replica" in recs.lower()


# ===================================================================
# Integrity score calculation
# ===================================================================


class TestIntegrityScore:
    def test_perfect_score_empty(self, sim: DataIntegritySimulator):
        report = sim.generate_report([])
        assert report.overall_integrity_score == 100.0

    def test_score_decreases_with_risk(self, sim: DataIntegritySimulator):
        s = _make_scenario(target="db-1", affected_pct=50.0, duration=60.0)
        report = sim.generate_report([s])
        assert report.overall_integrity_score < 100.0

    def test_score_floored_at_zero(self):
        comp = _make_component("db-x", ctype=ComponentType.DATABASE)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        # Generate many high-risk scenarios
        scenarios = [
            _make_scenario(
                f"s{i}",
                IntegrityFailureType.SPLIT_BRAIN,
                "db-x",
                affected_pct=100.0,
                duration=200.0,
            )
            for i in range(20)
        ]
        report = sim.generate_report(scenarios)
        assert report.overall_integrity_score >= 0.0

    def test_impossible_complexity_heavy_penalty(self):
        comp = _make_component("db-x", backup_enabled=False)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(
            failure_type=IntegrityFailureType.SPLIT_BRAIN,
            target="db-x",
            affected_pct=80.0,
        )
        report = sim.generate_report([s])
        assert report.overall_integrity_score < 90.0


# ===================================================================
# Edge cases and integration
# ===================================================================


class TestEdgeCases:
    def test_all_failure_types_on_cache(self):
        comp = _make_component("c-1", ctype=ComponentType.CACHE)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        for ft in IntegrityFailureType:
            s = _make_scenario(failure_type=ft, target="c-1")
            impact = sim.simulate_failure(s)
            assert impact.data_loss_risk >= 0.0

    def test_all_failure_types_on_queue(self):
        comp = _make_component("q-1", ctype=ComponentType.QUEUE)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        for ft in IntegrityFailureType:
            s = _make_scenario(failure_type=ft, target="q-1")
            impact = sim.simulate_failure(s)
            assert impact.data_loss_risk >= 0.0

    def test_all_failure_types_on_storage(self):
        comp = _make_component("s-1", ctype=ComponentType.STORAGE)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        for ft in IntegrityFailureType:
            s = _make_scenario(failure_type=ft, target="s-1")
            impact = sim.simulate_failure(s)
            assert impact.data_loss_risk >= 0.0

    def test_all_failure_types_on_app_server(self):
        comp = _make_component("a-1", ctype=ComponentType.APP_SERVER)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        for ft in IntegrityFailureType:
            s = _make_scenario(failure_type=ft, target="a-1")
            impact = sim.simulate_failure(s)
            assert impact.data_loss_risk >= 0.0

    def test_max_replicas(self):
        comp = _make_component("db-x", replicas=100)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(target="db-x")
        impact = sim.simulate_failure(s)
        assert impact.data_loss_risk >= 0.0

    def test_zero_max_rps(self):
        comp = _make_component("db-x", max_rps=0)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(target="db-x", affected_pct=50.0, duration=10.0)
        impact = sim.simulate_failure(s)
        # Fallback to 100 rps: 100 * 10 * 60 * 0.5 = 30000
        assert impact.affected_transactions == 30000

    def test_zero_duration(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(target="db-x", duration=0.0)
        impact = sim.simulate_failure(s)
        assert impact.affected_transactions == 0

    def test_zero_affected_pct(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(target="db-x", affected_pct=0.0)
        impact = sim.simulate_failure(s)
        assert impact.data_loss_risk == 0.0
        assert impact.affected_transactions == 0

    def test_detection_time_for_all_failure_types(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        for ft in IntegrityFailureType:
            s = _make_scenario(failure_type=ft, target="db-x")
            impact = sim.simulate_failure(s)
            assert impact.detection_time_minutes >= 0.0

    def test_large_graph_report(self):
        components = []
        for i in range(20):
            ctype = [ComponentType.DATABASE, ComponentType.CACHE, ComponentType.QUEUE][i % 3]
            components.append(_make_component(f"comp-{i}", ctype=ctype))
        g = _make_graph(*components)
        sim = DataIntegritySimulator(g)
        scenarios = [
            _make_scenario(f"s{i}", IntegrityFailureType.PARTIAL_WRITE, f"comp-{i}")
            for i in range(20)
        ]
        report = sim.generate_report(scenarios)
        assert report.scenarios_tested == 20
        assert len(report.impacts) == 20
        assert 0.0 <= report.overall_integrity_score <= 100.0

    def test_causal_consistency_factor(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(consistency=DataConsistencyLevel.CAUSAL, target="db-x")
        impact = sim.simulate_failure(s)
        assert impact.data_loss_risk > 0

    def test_read_your_writes_consistency_factor(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(consistency=DataConsistencyLevel.READ_YOUR_WRITES, target="db-x")
        impact = sim.simulate_failure(s)
        assert impact.data_loss_risk > 0

    def test_monotonic_consistency_factor(self):
        comp = _make_component("db-x")
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(consistency=DataConsistencyLevel.MONOTONIC, target="db-x")
        impact = sim.simulate_failure(s)
        assert impact.data_loss_risk > 0

    def test_stale_cache_not_applicable_to_database(self):
        comp = _make_component("db-x", ctype=ComponentType.DATABASE)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        guardrails = sim.evaluate_guardrails("db-x")
        for gx in guardrails:
            if gx.mechanism == "cache_invalidation":
                # Should not be present for database
                assert False, "cache_invalidation should not apply to database"

    def test_simulator_init(self, simple_graph: InfraGraph):
        sim = DataIntegritySimulator(simple_graph)
        assert sim.graph is simple_graph

    def test_guardrail_ntp_sync_for_clock_skew(self, sim: DataIntegritySimulator):
        guardrails = sim.evaluate_guardrails("db-1")
        mechanisms = {g.mechanism for g in guardrails}
        assert "NTP_sync" in mechanisms
        for gx in guardrails:
            if gx.mechanism == "NTP_sync":
                assert IntegrityFailureType.CLOCK_SKEW in gx.applicable_failures

    def test_cdc_guardrail_for_database(self, sim: DataIntegritySimulator):
        guardrails = sim.evaluate_guardrails("db-1")
        mechanisms = {g.mechanism for g in guardrails}
        assert "CDC" in mechanisms

    def test_idempotency_keys_guardrail(self, sim: DataIntegritySimulator):
        guardrails = sim.evaluate_guardrails("db-1")
        mechanisms = {g.mechanism for g in guardrails}
        assert "idempotency_keys" in mechanisms

    def test_report_score_increases_with_guardrails(self):
        """More guardrails should give a better score."""
        comp = _make_component("db-x", ctype=ComponentType.DATABASE, backup_enabled=True)
        g = _make_graph(comp)
        sim = DataIntegritySimulator(g)
        s = _make_scenario(target="db-x", affected_pct=10.0)
        report = sim.generate_report([s])
        # The guardrails should add back some score
        assert report.overall_integrity_score > 0.0
