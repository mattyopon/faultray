"""Tests for SLA Contract Validator module.

Comprehensive tests covering all violation types, edge cases, boundary
conditions, penalty calculations, and graph configurations.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.sla_contract_validator import (
    PenaltyTier,
    SLAContract,
    SLAValidationReport,
    SLAValidator,
    SLAViolationRisk,
    _DEFAULT_AVAILABILITY,
    _MINUTES_PER_MONTH,
)


# ---------------------------------------------------------------------------
# Graph factory helpers
# ---------------------------------------------------------------------------


def _empty_graph() -> InfraGraph:
    """Empty graph with no components."""
    return InfraGraph()


def _single_component_graph(
    *,
    replicas: int = 1,
    failover: bool = False,
    autoscaling: bool = False,
    backup: bool = False,
    backup_freq_hours: float = 24.0,
    comp_type: ComponentType = ComponentType.APP_SERVER,
    mtbf_hours: float = 0.0,
    mttr_minutes: float = 0.0,
) -> InfraGraph:
    """Graph with a single component."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="srv",
        name="Server",
        type=comp_type,
        replicas=replicas,
        failover=FailoverConfig(
            enabled=failover,
            promotion_time_seconds=10,
            health_check_interval_seconds=5,
            failover_threshold=3,
        ),
        autoscaling=AutoScalingConfig(
            enabled=autoscaling,
            min_replicas=1,
            max_replicas=5,
            scale_up_delay_seconds=15,
        ),
        security=SecurityProfile(
            backup_enabled=backup,
            backup_frequency_hours=backup_freq_hours,
        ),
        operational_profile=OperationalProfile(
            mtbf_hours=mtbf_hours,
            mttr_minutes=mttr_minutes,
        ),
    ))
    return graph


def _simple_graph() -> InfraGraph:
    """Three-tier graph: LB -> App -> DB, all single replica, no failover."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        security=SecurityProfile(backup_enabled=False),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires", latency_ms=2.0,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires", latency_ms=5.0,
    ))
    return graph


def _ha_graph() -> InfraGraph:
    """Highly available graph: multi-replica with failover on all components."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=3,
        failover=FailoverConfig(
            enabled=True, promotion_time_seconds=5,
            health_check_interval_seconds=5, failover_threshold=2,
        ),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=5,
        failover=FailoverConfig(
            enabled=True, promotion_time_seconds=10,
            health_check_interval_seconds=5, failover_threshold=2,
        ),
        autoscaling=AutoScalingConfig(enabled=True, scale_up_delay_seconds=15),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=3,
        failover=FailoverConfig(
            enabled=True, promotion_time_seconds=15,
            health_check_interval_seconds=5, failover_threshold=3,
        ),
        security=SecurityProfile(backup_enabled=True, backup_frequency_hours=1.0),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires", latency_ms=1.0,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires", latency_ms=2.0,
    ))
    return graph


def _no_redundancy_graph() -> InfraGraph:
    """Graph with no redundancy: single replica, no failover, no backup."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=1000, mttr_minutes=60),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=2000, mttr_minutes=120),
        security=SecurityProfile(backup_enabled=False),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


# ---------------------------------------------------------------------------
# Contract factory helpers
# ---------------------------------------------------------------------------


def _standard_contract(**overrides) -> SLAContract:
    """Build a standard SLA contract with sane defaults."""
    kwargs = dict(
        service_name="Web API",
        availability_target=99.9,
        max_response_time_ms=500.0,
        max_downtime_minutes_per_month=43.8,
        rpo_minutes=15.0,
        rto_minutes=30.0,
        penalty_tiers=[
            PenaltyTier(threshold=99.9, penalty_percent=10.0, description="10% credit"),
            PenaltyTier(threshold=99.0, penalty_percent=25.0, description="25% credit"),
        ],
        monthly_contract_value=100_000.0,
    )
    kwargs.update(overrides)
    return SLAContract(**kwargs)


def _four_nines_contract(**overrides) -> SLAContract:
    """99.99% availability contract."""
    kwargs = dict(
        service_name="Premium API",
        availability_target=99.99,
        max_response_time_ms=200.0,
        max_downtime_minutes_per_month=4.32,
        rpo_minutes=5.0,
        rto_minutes=10.0,
        penalty_tiers=[
            PenaltyTier(threshold=99.99, penalty_percent=10.0),
            PenaltyTier(threshold=99.9, penalty_percent=25.0),
            PenaltyTier(threshold=99.0, penalty_percent=50.0),
        ],
        monthly_contract_value=500_000.0,
    )
    kwargs.update(overrides)
    return SLAContract(**kwargs)


# ===========================================================================
# PenaltyTier tests
# ===========================================================================


class TestPenaltyTier:
    """Tests for the PenaltyTier dataclass."""

    def test_basic_creation(self) -> None:
        tier = PenaltyTier(threshold=99.9, penalty_percent=10.0, description="10% credit")
        assert tier.threshold == 99.9
        assert tier.penalty_percent == 10.0
        assert tier.description == "10% credit"

    def test_default_description(self) -> None:
        tier = PenaltyTier(threshold=99.0, penalty_percent=25.0)
        assert tier.description == ""

    def test_zero_penalty(self) -> None:
        tier = PenaltyTier(threshold=99.99, penalty_percent=0.0)
        assert tier.penalty_percent == 0.0

    def test_high_penalty(self) -> None:
        tier = PenaltyTier(threshold=90.0, penalty_percent=100.0)
        assert tier.penalty_percent == 100.0


# ===========================================================================
# SLAContract tests
# ===========================================================================


class TestSLAContract:
    """Tests for the SLAContract dataclass."""

    def test_basic_creation(self) -> None:
        contract = _standard_contract()
        assert contract.service_name == "Web API"
        assert contract.availability_target == 99.9
        assert contract.max_response_time_ms == 500.0
        assert contract.rpo_minutes == 15.0
        assert contract.rto_minutes == 30.0

    def test_penalty_tiers_populated(self) -> None:
        contract = _standard_contract()
        assert len(contract.penalty_tiers) == 2
        assert contract.penalty_tiers[0].threshold == 99.9
        assert contract.penalty_tiers[1].threshold == 99.0

    def test_defaults(self) -> None:
        contract = SLAContract(service_name="Minimal", availability_target=99.0)
        assert contract.availability_target == 99.0
        assert contract.max_response_time_ms == 500.0
        assert contract.rpo_minutes == 15.0
        assert contract.rto_minutes == 30.0
        assert contract.penalty_tiers == []
        assert contract.monthly_contract_value == 0.0

    def test_custom_monthly_value(self) -> None:
        contract = _standard_contract(monthly_contract_value=1_000_000.0)
        assert contract.monthly_contract_value == 1_000_000.0


# ===========================================================================
# SLAViolationRisk tests
# ===========================================================================


class TestSLAViolationRisk:
    """Tests for the SLAViolationRisk dataclass."""

    def test_creation(self) -> None:
        contract = _standard_contract()
        v = SLAViolationRisk(
            contract=contract,
            violation_type="availability",
            current_capability=99.5,
            required_level=99.9,
            gap=0.4,
            risk_level="medium",
            remediation="Add replicas.",
            estimated_penalty_exposure=10000.0,
        )
        assert v.violation_type == "availability"
        assert v.gap == 0.4
        assert v.risk_level == "medium"
        assert v.estimated_penalty_exposure == 10000.0

    def test_all_violation_types(self) -> None:
        contract = _standard_contract()
        for vtype in ("availability", "rto", "rpo", "response_time"):
            v = SLAViolationRisk(
                contract=contract,
                violation_type=vtype,
                current_capability=0.0,
                required_level=1.0,
                gap=1.0,
                risk_level="critical",
                remediation="Fix it.",
            )
            assert v.violation_type == vtype

    def test_default_penalty_exposure(self) -> None:
        contract = _standard_contract()
        v = SLAViolationRisk(
            contract=contract,
            violation_type="availability",
            current_capability=99.0,
            required_level=99.9,
            gap=0.9,
            risk_level="high",
            remediation="Fix.",
        )
        assert v.estimated_penalty_exposure == 0.0


# ===========================================================================
# SLAValidationReport tests
# ===========================================================================


class TestSLAValidationReport:
    """Tests for the SLAValidationReport dataclass."""

    def test_compliant_report(self) -> None:
        report = SLAValidationReport(
            contracts=[_standard_contract()],
            violations=[],
            overall_compliance=True,
            compliance_score=100.0,
            total_penalty_exposure=0.0,
            recommendations=[],
        )
        assert report.overall_compliance is True
        assert report.compliance_score == 100.0
        assert report.total_penalty_exposure == 0.0

    def test_non_compliant_report(self) -> None:
        contract = _standard_contract()
        v = SLAViolationRisk(
            contract=contract,
            violation_type="availability",
            current_capability=99.0,
            required_level=99.9,
            gap=0.9,
            risk_level="high",
            remediation="Add replicas.",
            estimated_penalty_exposure=25000.0,
        )
        report = SLAValidationReport(
            contracts=[contract],
            violations=[v],
            overall_compliance=False,
            compliance_score=85.0,
            total_penalty_exposure=25000.0,
            recommendations=["Add replicas."],
        )
        assert report.overall_compliance is False
        assert report.compliance_score == 85.0
        assert report.total_penalty_exposure == 25000.0


# ===========================================================================
# SLAValidator — Empty / trivial inputs
# ===========================================================================


class TestValidatorEmptyInputs:
    """Tests with empty graphs or empty contract lists."""

    def test_empty_contracts_list(self) -> None:
        graph = _simple_graph()
        validator = SLAValidator(graph)
        report = validator.validate([])
        assert report.overall_compliance is True
        assert report.compliance_score == 100.0
        assert report.violations == []
        assert report.recommendations == []
        assert report.total_penalty_exposure == 0.0

    def test_empty_graph_with_contract(self) -> None:
        graph = _empty_graph()
        validator = SLAValidator(graph)
        contract = _standard_contract()
        report = validator.validate([contract])
        # Empty graph -> availability = 0.0 -> violation
        assert report.overall_compliance is False
        avail_violations = [v for v in report.violations if v.violation_type == "availability"]
        assert len(avail_violations) == 1
        assert avail_violations[0].current_capability == 0.0

    def test_empty_graph_rto(self) -> None:
        graph = _empty_graph()
        validator = SLAValidator(graph)
        contract = _standard_contract()
        report = validator.validate([contract])
        rto_violations = [v for v in report.violations if v.violation_type == "rto"]
        assert len(rto_violations) == 1
        assert rto_violations[0].current_capability == float("inf")

    def test_empty_graph_rpo_infinite(self) -> None:
        """Empty graph has no components, so RPO is infinite -> violation."""
        graph = _empty_graph()
        validator = SLAValidator(graph)
        contract = _standard_contract(rpo_minutes=60.0)
        report = validator.validate([contract])
        rpo_violations = [v for v in report.violations if v.violation_type == "rpo"]
        assert len(rpo_violations) == 1
        assert rpo_violations[0].current_capability == float("inf")


# ===========================================================================
# SLAValidator — Availability checks
# ===========================================================================


class TestAvailabilityCheck:
    """Tests for the availability dimension."""

    def test_ha_graph_meets_three_nines(self) -> None:
        graph = _ha_graph()
        validator = SLAValidator(graph)
        contract = _standard_contract(availability_target=99.9)
        report = validator.validate([contract])
        avail_violations = [v for v in report.violations if v.violation_type == "availability"]
        assert len(avail_violations) == 0

    def test_single_replica_below_four_nines(self) -> None:
        graph = _simple_graph()
        validator = SLAValidator(graph)
        contract = _four_nines_contract()
        report = validator.validate([contract])
        avail_violations = [v for v in report.violations if v.violation_type == "availability"]
        assert len(avail_violations) == 1
        v = avail_violations[0]
        assert v.current_capability < 99.99
        assert v.required_level == 99.99
        assert v.gap > 0

    def test_no_redundancy_availability(self) -> None:
        graph = _no_redundancy_graph()
        validator = SLAValidator(graph)
        estimated = validator._estimate_availability()
        # With MTBF=1000h / MTTR=1h for app and MTBF=2000h / MTTR=2h for db
        # A_app = 1000/(1000+1) ~ 0.999001
        # A_db  = 2000/(2000+2) ~ 0.999001
        # system ~ 0.999001 * 0.999001 ~ 0.998003 -> 99.80%
        assert estimated < 99.9

    def test_availability_with_mtbf_mttr_override(self) -> None:
        graph = _single_component_graph(mtbf_hours=10000, mttr_minutes=6)
        validator = SLAValidator(graph)
        estimated = validator._estimate_availability()
        # A = 10000 / (10000 + 0.1) ~ 99.999%
        assert estimated > 99.99

    def test_replicas_boost_availability(self) -> None:
        graph1 = _single_component_graph(replicas=1)
        graph3 = _single_component_graph(replicas=3)
        v1 = SLAValidator(graph1)._estimate_availability()
        v3 = SLAValidator(graph3)._estimate_availability()
        assert v3 > v1

    def test_failover_boosts_availability(self) -> None:
        graph_no = _single_component_graph(replicas=2, failover=False)
        graph_fo = _single_component_graph(replicas=2, failover=True)
        v_no = SLAValidator(graph_no)._estimate_availability()
        v_fo = SLAValidator(graph_fo)._estimate_availability()
        assert v_fo > v_no

    def test_optional_dependency_not_on_critical_path(self) -> None:
        """Optional dependencies should not reduce system availability."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="cache", name="Cache", type=ComponentType.CACHE, replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=100, mttr_minutes=60),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="cache", dependency_type="optional",
        ))
        validator = SLAValidator(graph)
        avail = validator._estimate_availability()
        # Cache with optional dep should NOT reduce availability
        app_only_graph = _single_component_graph(replicas=2, comp_type=ComponentType.APP_SERVER)
        app_only_avail = SLAValidator(app_only_graph)._estimate_availability()
        assert abs(avail - app_only_avail) < 0.01

    def test_availability_zero_percent_sla(self) -> None:
        """An SLA of 0% should always be met."""
        graph = _no_redundancy_graph()
        validator = SLAValidator(graph)
        contract = _standard_contract(availability_target=0.0)
        report = validator.validate([contract])
        avail_violations = [v for v in report.violations if v.violation_type == "availability"]
        assert len(avail_violations) == 0

    def test_availability_100_percent_sla(self) -> None:
        """An SLA of 100% can never be met."""
        graph = _ha_graph()
        validator = SLAValidator(graph)
        contract = _standard_contract(availability_target=100.0)
        report = validator.validate([contract])
        avail_violations = [v for v in report.violations if v.violation_type == "availability"]
        assert len(avail_violations) == 1

    def test_availability_exactly_meeting_sla(self) -> None:
        """If current availability exactly matches the target, no violation."""
        graph = _simple_graph()
        validator = SLAValidator(graph)
        estimated = validator._estimate_availability()
        # Set target to exactly the estimated value
        contract = _standard_contract(availability_target=estimated)
        report = validator.validate([contract])
        avail_violations = [v for v in report.violations if v.violation_type == "availability"]
        assert len(avail_violations) == 0

    def test_availability_just_under_sla(self) -> None:
        """If target is barely above estimated, should detect violation."""
        graph = _simple_graph()
        validator = SLAValidator(graph)
        estimated = validator._estimate_availability()
        contract = _standard_contract(availability_target=estimated + 0.001)
        report = validator.validate([contract])
        avail_violations = [v for v in report.violations if v.violation_type == "availability"]
        assert len(avail_violations) == 1
        assert avail_violations[0].gap > 0


# ===========================================================================
# SLAValidator — RTO checks
# ===========================================================================


class TestRTOCheck:
    """Tests for the RTO dimension."""

    def test_no_failover_high_rto(self) -> None:
        graph = _no_redundancy_graph()
        validator = SLAValidator(graph)
        rto = validator._estimate_rto()
        # Worst MTTR is 120 minutes
        assert rto >= 60.0

    def test_failover_reduces_rto(self) -> None:
        graph_no = _single_component_graph(replicas=2, failover=False)
        graph_fo = _single_component_graph(replicas=2, failover=True)
        rto_no = SLAValidator(graph_no)._estimate_rto()
        rto_fo = SLAValidator(graph_fo)._estimate_rto()
        assert rto_fo < rto_no

    def test_autoscaling_reduces_rto(self) -> None:
        graph_no = _single_component_graph(replicas=1, autoscaling=False)
        graph_as = _single_component_graph(replicas=1, autoscaling=True)
        rto_no = SLAValidator(graph_no)._estimate_rto()
        rto_as = SLAValidator(graph_as)._estimate_rto()
        assert rto_as <= rto_no

    def test_rto_violation_detected(self) -> None:
        graph = _no_redundancy_graph()
        validator = SLAValidator(graph)
        contract = _standard_contract(rto_minutes=5.0)
        report = validator.validate([contract])
        rto_violations = [v for v in report.violations if v.violation_type == "rto"]
        assert len(rto_violations) == 1
        assert rto_violations[0].current_capability > 5.0

    def test_rto_met_with_failover(self) -> None:
        graph = _ha_graph()
        validator = SLAValidator(graph)
        rto = validator._estimate_rto()
        # With failover: detection = 5s * 3 = 15s, promotion = 15s => 30s = 0.5min
        assert rto < 5.0

    def test_empty_graph_rto_infinite(self) -> None:
        graph = _empty_graph()
        validator = SLAValidator(graph)
        rto = validator._estimate_rto()
        assert rto == float("inf")

    def test_rto_exactly_meeting_requirement(self) -> None:
        graph = _single_component_graph(
            replicas=2, failover=True, autoscaling=True,
        )
        validator = SLAValidator(graph)
        rto = validator._estimate_rto()
        contract = _standard_contract(rto_minutes=rto)
        report = validator.validate([contract])
        rto_violations = [v for v in report.violations if v.violation_type == "rto"]
        assert len(rto_violations) == 0

    def test_rto_just_over_requirement(self) -> None:
        graph = _single_component_graph(replicas=2, failover=True)
        validator = SLAValidator(graph)
        rto = validator._estimate_rto()
        contract = _standard_contract(rto_minutes=rto - 0.001)
        report = validator.validate([contract])
        rto_violations = [v for v in report.violations if v.violation_type == "rto"]
        assert len(rto_violations) == 1


# ===========================================================================
# SLAValidator — RPO checks
# ===========================================================================


class TestRPOCheck:
    """Tests for the RPO dimension."""

    def test_no_backup_high_rpo(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
            security=SecurityProfile(backup_enabled=False),
        ))
        validator = SLAValidator(graph)
        rpo = validator._estimate_rpo()
        assert rpo == 1440.0  # 24 hours fallback

    def test_backup_reduces_rpo(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
            security=SecurityProfile(backup_enabled=True, backup_frequency_hours=1.0),
        ))
        validator = SLAValidator(graph)
        rpo = validator._estimate_rpo()
        assert rpo == 60.0  # 1 hour in minutes

    def test_replicas_near_zero_rpo(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=3,
            security=SecurityProfile(backup_enabled=False),
        ))
        validator = SLAValidator(graph)
        rpo = validator._estimate_rpo()
        assert rpo == 0.0

    def test_rpo_violation_detected(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
            security=SecurityProfile(backup_enabled=True, backup_frequency_hours=4.0),
        ))
        validator = SLAValidator(graph)
        contract = _standard_contract(rpo_minutes=15.0)
        report = validator.validate([contract])
        rpo_violations = [v for v in report.violations if v.violation_type == "rpo"]
        assert len(rpo_violations) == 1
        assert rpo_violations[0].current_capability == 240.0  # 4h in minutes

    def test_rpo_no_stateful_components(self) -> None:
        """Non-stateful components don't affect RPO."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        ))
        validator = SLAValidator(graph)
        rpo = validator._estimate_rpo()
        assert rpo == 0.0  # no stateful -> no data loss concern

    def test_rpo_stateful_types(self) -> None:
        """DATABASE, STORAGE, and QUEUE are stateful."""
        for stype in (ComponentType.DATABASE, ComponentType.STORAGE, ComponentType.QUEUE):
            graph = InfraGraph()
            graph.add_component(Component(
                id="store", name="Store", type=stype, replicas=1,
                security=SecurityProfile(backup_enabled=False),
            ))
            validator = SLAValidator(graph)
            rpo = validator._estimate_rpo()
            assert rpo == 1440.0, f"Expected 1440 RPO for {stype} without backup"

    def test_rpo_exactly_meeting_requirement(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
            security=SecurityProfile(backup_enabled=True, backup_frequency_hours=0.25),
        ))
        validator = SLAValidator(graph)
        rpo = validator._estimate_rpo()
        assert rpo == 15.0  # 0.25h * 60 = 15 min
        contract = _standard_contract(rpo_minutes=15.0)
        report = validator.validate([contract])
        rpo_violations = [v for v in report.violations if v.violation_type == "rpo"]
        assert len(rpo_violations) == 0

    def test_rpo_empty_graph(self) -> None:
        graph = _empty_graph()
        validator = SLAValidator(graph)
        rpo = validator._estimate_rpo()
        # Empty graph -> early return of inf (no components to evaluate)
        assert rpo == float("inf")


# ===========================================================================
# SLAValidator — Response time checks
# ===========================================================================


class TestResponseTimeCheck:
    """Tests for the response time dimension."""

    def test_low_latency_graph(self) -> None:
        graph = _ha_graph()
        validator = SLAValidator(graph)
        rt = validator._estimate_response_time()
        # 2 edges with 1ms + 2ms = 3ms latency + 3 components * 5ms = 18ms
        assert rt < 500.0

    def test_high_latency_edges(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER,
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.APP_SERVER,
        ))
        graph.add_dependency(Dependency(
            source_id="a", target_id="b", dependency_type="requires", latency_ms=300.0,
        ))
        validator = SLAValidator(graph)
        rt = validator._estimate_response_time()
        # 300ms + 2 * 5ms = 310ms
        assert rt >= 300.0

    def test_response_time_violation(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER,
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.APP_SERVER,
        ))
        graph.add_dependency(Dependency(
            source_id="a", target_id="b", dependency_type="requires", latency_ms=400.0,
        ))
        validator = SLAValidator(graph)
        contract = _standard_contract(max_response_time_ms=200.0)
        report = validator.validate([contract])
        rt_violations = [v for v in report.violations if v.violation_type == "response_time"]
        assert len(rt_violations) == 1
        assert rt_violations[0].current_capability > 200.0

    def test_response_time_empty_graph(self) -> None:
        graph = _empty_graph()
        validator = SLAValidator(graph)
        rt = validator._estimate_response_time()
        assert rt == 0.0  # no edges, no components


# ===========================================================================
# SLAValidator — Penalty tier calculations
# ===========================================================================


class TestPenaltyCalculation:
    """Tests for penalty tier walking and financial exposure."""

    def test_no_penalty_tiers(self) -> None:
        graph = _simple_graph()
        validator = SLAValidator(graph)
        contract = SLAContract(
            service_name="No Penalty",
            availability_target=99.99,
            monthly_contract_value=100_000.0,
            penalty_tiers=[],
        )
        penalty = validator._calculate_penalty(contract, 95.0)
        assert penalty == 0.0

    def test_no_contract_value(self) -> None:
        graph = _simple_graph()
        validator = SLAValidator(graph)
        contract = SLAContract(
            service_name="Free",
            availability_target=99.99,
            monthly_contract_value=0.0,
            penalty_tiers=[
                PenaltyTier(threshold=99.9, penalty_percent=10.0),
            ],
        )
        penalty = validator._calculate_penalty(contract, 95.0)
        assert penalty == 0.0

    def test_single_tier_triggered(self) -> None:
        graph = _simple_graph()
        validator = SLAValidator(graph)
        contract = SLAContract(
            service_name="Test",
            availability_target=99.9,
            monthly_contract_value=100_000.0,
            penalty_tiers=[
                PenaltyTier(threshold=99.9, penalty_percent=10.0),
            ],
        )
        # Actual availability 99.5 < 99.9 threshold -> 10% penalty
        penalty = validator._calculate_penalty(contract, 99.5)
        assert penalty == 10_000.0  # 100_000 * 10%

    def test_multiple_tiers_highest_penalty(self) -> None:
        graph = _simple_graph()
        validator = SLAValidator(graph)
        contract = SLAContract(
            service_name="Test",
            availability_target=99.99,
            monthly_contract_value=200_000.0,
            penalty_tiers=[
                PenaltyTier(threshold=99.99, penalty_percent=5.0),
                PenaltyTier(threshold=99.9, penalty_percent=10.0),
                PenaltyTier(threshold=99.0, penalty_percent=25.0),
            ],
        )
        # Actual availability 98.0 is below ALL thresholds -> highest penalty 25%
        penalty = validator._calculate_penalty(contract, 98.0)
        assert penalty == 50_000.0  # 200_000 * 25%

    def test_above_all_thresholds_no_penalty(self) -> None:
        graph = _simple_graph()
        validator = SLAValidator(graph)
        contract = SLAContract(
            service_name="Test",
            availability_target=99.9,
            monthly_contract_value=100_000.0,
            penalty_tiers=[
                PenaltyTier(threshold=99.9, penalty_percent=10.0),
                PenaltyTier(threshold=99.0, penalty_percent=25.0),
            ],
        )
        # Actual 99.95 is above all thresholds -> no penalty
        penalty = validator._calculate_penalty(contract, 99.95)
        assert penalty == 0.0

    def test_exactly_at_threshold_no_penalty(self) -> None:
        """If actual == threshold, the condition < threshold is not met."""
        graph = _simple_graph()
        validator = SLAValidator(graph)
        contract = SLAContract(
            service_name="Test",
            availability_target=99.9,
            monthly_contract_value=100_000.0,
            penalty_tiers=[
                PenaltyTier(threshold=99.9, penalty_percent=10.0),
            ],
        )
        penalty = validator._calculate_penalty(contract, 99.9)
        assert penalty == 0.0

    def test_just_below_threshold(self) -> None:
        graph = _simple_graph()
        validator = SLAValidator(graph)
        contract = SLAContract(
            service_name="Test",
            availability_target=99.9,
            monthly_contract_value=100_000.0,
            penalty_tiers=[
                PenaltyTier(threshold=99.9, penalty_percent=10.0),
            ],
        )
        penalty = validator._calculate_penalty(contract, 99.899)
        assert penalty == 10_000.0

    def test_penalty_exposure_in_report(self) -> None:
        graph = _no_redundancy_graph()
        validator = SLAValidator(graph)
        contract = _four_nines_contract(monthly_contract_value=200_000.0)
        report = validator.validate([contract])
        # Should have violations with penalty exposure
        if report.violations:
            assert report.total_penalty_exposure > 0


# ===========================================================================
# SLAValidator — Compliance score
# ===========================================================================


class TestComplianceScore:
    """Tests for compliance score computation."""

    def test_perfect_compliance(self) -> None:
        graph = _ha_graph()
        validator = SLAValidator(graph)
        contract = _standard_contract(
            availability_target=90.0,
            rto_minutes=600,
            rpo_minutes=1500,
            max_response_time_ms=10000,
        )
        report = validator.validate([contract])
        assert report.compliance_score == 100.0
        assert report.overall_compliance is True

    def test_low_compliance(self) -> None:
        graph = _no_redundancy_graph()
        validator = SLAValidator(graph)
        contract = _four_nines_contract(
            rto_minutes=0.1,
            rpo_minutes=0.1,
            max_response_time_ms=1.0,
        )
        report = validator.validate([contract])
        assert report.compliance_score < 100.0
        assert report.overall_compliance is False

    def test_score_never_below_zero(self) -> None:
        graph = _no_redundancy_graph()
        validator = SLAValidator(graph)
        # Create many contracts to generate many violations
        contracts = [
            _four_nines_contract(service_name=f"svc-{i}", rto_minutes=0.01, rpo_minutes=0.01)
            for i in range(10)
        ]
        report = validator.validate(contracts)
        assert report.compliance_score >= 0.0

    def test_compute_compliance_score_empty_contracts(self) -> None:
        """Direct call with empty contracts list returns 100."""
        graph = _simple_graph()
        validator = SLAValidator(graph)
        score = validator._compute_compliance_score([], [])
        assert score == 100.0

    def test_score_never_above_100(self) -> None:
        graph = _ha_graph()
        validator = SLAValidator(graph)
        report = validator.validate([_standard_contract(
            availability_target=0.0,
            rto_minutes=99999,
            rpo_minutes=99999,
            max_response_time_ms=99999,
        )])
        assert report.compliance_score <= 100.0

    def test_deductions_by_severity(self) -> None:
        """Higher severity violations should produce lower scores."""
        graph = _no_redundancy_graph()
        validator = SLAValidator(graph)

        # Mild violation (just barely miss)
        mild = _standard_contract(
            availability_target=validator._estimate_availability() + 0.01,
            rto_minutes=99999,
            rpo_minutes=99999,
            max_response_time_ms=99999,
        )
        report_mild = validator.validate([mild])

        # Severe violation
        severe = _standard_contract(
            availability_target=99.9999,
            rto_minutes=0.001,
            rpo_minutes=0.001,
            max_response_time_ms=0.001,
        )
        report_severe = validator.validate([severe])

        assert report_severe.compliance_score <= report_mild.compliance_score


# ===========================================================================
# SLAValidator — Risk classification
# ===========================================================================


class TestRiskClassification:
    """Tests for the _classify_risk static method."""

    def test_low_risk(self) -> None:
        assert SLAValidator._classify_risk(0.05, (0.1, 0.5, 1.0)) == "low"

    def test_medium_risk(self) -> None:
        assert SLAValidator._classify_risk(0.3, (0.1, 0.5, 1.0)) == "medium"

    def test_high_risk(self) -> None:
        assert SLAValidator._classify_risk(0.8, (0.1, 0.5, 1.0)) == "high"

    def test_critical_risk(self) -> None:
        assert SLAValidator._classify_risk(5.0, (0.1, 0.5, 1.0)) == "critical"

    def test_boundary_low_medium(self) -> None:
        assert SLAValidator._classify_risk(0.1, (0.1, 0.5, 1.0)) == "low"

    def test_boundary_medium_high(self) -> None:
        assert SLAValidator._classify_risk(0.5, (0.1, 0.5, 1.0)) == "medium"

    def test_boundary_high_critical(self) -> None:
        assert SLAValidator._classify_risk(1.0, (0.1, 0.5, 1.0)) == "high"

    def test_zero_gap(self) -> None:
        assert SLAValidator._classify_risk(0.0, (0.1, 0.5, 1.0)) == "low"


# ===========================================================================
# SLAValidator — Multiple overlapping contracts
# ===========================================================================


class TestMultipleContracts:
    """Tests with multiple SLA contracts."""

    def test_two_contracts_different_targets(self) -> None:
        graph = _simple_graph()
        validator = SLAValidator(graph)
        contracts = [
            _standard_contract(service_name="API-Free", availability_target=99.0),
            _four_nines_contract(service_name="API-Premium"),
        ]
        report = validator.validate(contracts)
        assert len(report.contracts) == 2
        # Premium should have more violations than free
        premium_violations = [
            v for v in report.violations if v.contract.service_name == "API-Premium"
        ]
        free_violations = [
            v for v in report.violations if v.contract.service_name == "API-Free"
        ]
        assert len(premium_violations) >= len(free_violations)

    def test_three_contracts_aggregated(self) -> None:
        graph = _ha_graph()
        validator = SLAValidator(graph)
        contracts = [
            _standard_contract(service_name="Svc-A", availability_target=99.0),
            _standard_contract(service_name="Svc-B", availability_target=99.9),
            _four_nines_contract(service_name="Svc-C"),
        ]
        report = validator.validate(contracts)
        assert len(report.contracts) == 3
        # Total penalty is sum across all violations
        manual_sum = sum(v.estimated_penalty_exposure for v in report.violations)
        assert abs(report.total_penalty_exposure - manual_sum) < 0.01

    def test_recommendations_deduplicated(self) -> None:
        graph = _no_redundancy_graph()
        validator = SLAValidator(graph)
        # Two contracts that will produce the same remediation
        contracts = [
            _standard_contract(service_name="A", availability_target=99.99),
            _standard_contract(service_name="B", availability_target=99.99),
        ]
        report = validator.validate(contracts)
        # Each unique remediation should appear only once
        assert len(report.recommendations) == len(set(report.recommendations))


# ===========================================================================
# SLAValidator — Full redundancy vs no redundancy
# ===========================================================================


class TestRedundancyContrast:
    """Compare fully-redundant vs non-redundant infrastructure."""

    def test_ha_passes_more_checks(self) -> None:
        ha = _ha_graph()
        no_ha = _no_redundancy_graph()
        contract = _standard_contract()

        report_ha = SLAValidator(ha).validate([contract])
        report_no = SLAValidator(no_ha).validate([contract])

        assert len(report_ha.violations) <= len(report_no.violations)

    def test_ha_higher_compliance_score(self) -> None:
        ha = _ha_graph()
        no_ha = _no_redundancy_graph()
        contract = _four_nines_contract()

        score_ha = SLAValidator(ha).validate([contract]).compliance_score
        score_no = SLAValidator(no_ha).validate([contract]).compliance_score

        assert score_ha >= score_no

    def test_ha_lower_penalty_exposure(self) -> None:
        ha = _ha_graph()
        no_ha = _no_redundancy_graph()
        contract = _four_nines_contract(monthly_contract_value=500_000.0)

        penalty_ha = SLAValidator(ha).validate([contract]).total_penalty_exposure
        penalty_no = SLAValidator(no_ha).validate([contract]).total_penalty_exposure

        assert penalty_ha <= penalty_no


# ===========================================================================
# SLAValidator — Remediation text
# ===========================================================================


class TestRemediationText:
    """Tests for remediation recommendations."""

    def test_availability_remediation_large_gap(self) -> None:
        text = SLAValidator._availability_remediation(99.0, 99.99)
        assert "redundant replicas" in text.lower() or "failover" in text.lower()

    def test_availability_remediation_medium_gap(self) -> None:
        text = SLAValidator._availability_remediation(99.7, 99.9)
        assert "failover" in text.lower() or "replica" in text.lower()

    def test_availability_remediation_small_gap(self) -> None:
        text = SLAValidator._availability_remediation(99.85, 99.9)
        assert "health-check" in text.lower() or "promotion" in text.lower()

    def test_rto_remediation(self) -> None:
        text = SLAValidator._rto_remediation(60.0, 10.0)
        assert "failover" in text.lower()
        assert "60.0" in text
        assert "10.0" in text

    def test_rpo_remediation(self) -> None:
        text = SLAValidator._rpo_remediation(1440.0, 15.0)
        assert "backup" in text.lower() or "replication" in text.lower()
        assert "1440.0" in text
        assert "15.0" in text

    def test_remediation_in_report(self) -> None:
        graph = _no_redundancy_graph()
        validator = SLAValidator(graph)
        contract = _four_nines_contract()
        report = validator.validate([contract])
        assert len(report.recommendations) > 0
        for rec in report.recommendations:
            assert len(rec) > 10  # meaningful text


# ===========================================================================
# SLAValidator — Component type coverage
# ===========================================================================


class TestComponentTypeCoverage:
    """Ensure all component types have default availability."""

    def test_all_types_have_defaults(self) -> None:
        for ct in ComponentType:
            assert ct in _DEFAULT_AVAILABILITY, f"Missing default for {ct}"

    def test_each_type_can_estimate_availability(self) -> None:
        for ct in ComponentType:
            graph = _single_component_graph(comp_type=ct)
            validator = SLAValidator(graph)
            avail = validator._estimate_availability()
            assert 0.0 < avail <= 100.0, f"Bad availability for {ct}: {avail}"


# ===========================================================================
# SLAValidator — Determinism
# ===========================================================================


class TestDeterminism:
    """Analytical calculations should be deterministic."""

    def test_availability_deterministic(self) -> None:
        graph = _simple_graph()
        v = SLAValidator(graph)
        a1 = v._estimate_availability()
        a2 = v._estimate_availability()
        assert a1 == a2

    def test_rto_deterministic(self) -> None:
        graph = _simple_graph()
        v = SLAValidator(graph)
        r1 = v._estimate_rto()
        r2 = v._estimate_rto()
        assert r1 == r2

    def test_rpo_deterministic(self) -> None:
        graph = _simple_graph()
        v = SLAValidator(graph)
        r1 = v._estimate_rpo()
        r2 = v._estimate_rpo()
        assert r1 == r2

    def test_full_report_deterministic(self) -> None:
        graph = _simple_graph()
        contract = _standard_contract()
        r1 = SLAValidator(graph).validate([contract])
        r2 = SLAValidator(graph).validate([contract])
        assert r1.compliance_score == r2.compliance_score
        assert r1.total_penalty_exposure == r2.total_penalty_exposure
        assert len(r1.violations) == len(r2.violations)


# ===========================================================================
# SLAValidator — Edge cases with various graph topologies
# ===========================================================================


class TestGraphTopologies:
    """Tests with different graph structures."""

    def test_single_standalone_component(self) -> None:
        graph = _single_component_graph()
        validator = SLAValidator(graph)
        contract = _standard_contract(availability_target=90.0, rto_minutes=9999)
        report = validator.validate([contract])
        # Single APP_SERVER with default 99.9% should pass 90%
        avail_violations = [v for v in report.violations if v.violation_type == "availability"]
        assert len(avail_violations) == 0

    def test_deep_chain(self) -> None:
        """A long chain of components in series should lower availability."""
        graph = InfraGraph()
        prev_id = None
        for i in range(10):
            cid = f"svc-{i}"
            graph.add_component(Component(
                id=cid, name=f"Service {i}", type=ComponentType.APP_SERVER, replicas=1,
            ))
            if prev_id:
                graph.add_dependency(Dependency(
                    source_id=prev_id, target_id=cid, dependency_type="requires",
                ))
            prev_id = cid

        validator = SLAValidator(graph)
        avail = validator._estimate_availability()
        # 10 components in series, each ~99.9% -> system ~99.0%
        assert avail < 99.9

    def test_parallel_independent_components(self) -> None:
        """Multiple independent components (no deps) should all be on critical path."""
        graph = InfraGraph()
        for i in range(5):
            graph.add_component(Component(
                id=f"svc-{i}", name=f"Service {i}", type=ComponentType.APP_SERVER, replicas=1,
            ))
        validator = SLAValidator(graph)
        avail = validator._estimate_availability()
        # All are standalone -> all on critical path -> multiplicative
        single_avail = _DEFAULT_AVAILABILITY[ComponentType.APP_SERVER]
        expected = (single_avail ** 5) * 100.0
        assert abs(avail - expected) < 0.01

    def test_mixed_dependency_types(self) -> None:
        """Graph with requires and optional deps."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        ))
        graph.add_component(Component(
            id="cache", name="Cache", type=ComponentType.CACHE, replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=100, mttr_minutes=60),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="cache", dependency_type="optional",
        ))
        validator = SLAValidator(graph)
        avail = validator._estimate_availability()
        # Cache is optional -> should not lower availability
        assert avail > 99.0


# ===========================================================================
# Constants sanity checks
# ===========================================================================


class TestConstants:
    """Verify module-level constants are reasonable."""

    def test_minutes_per_month(self) -> None:
        # 30.44 days * 24 hours * 60 minutes
        expected = 30.44 * 24 * 60
        assert abs(_MINUTES_PER_MONTH - expected) < 0.1

    def test_default_availabilities_in_range(self) -> None:
        for ct, avail in _DEFAULT_AVAILABILITY.items():
            assert 0.0 < avail <= 1.0, f"{ct} has out-of-range availability: {avail}"

    def test_default_availabilities_reasonable(self) -> None:
        # All defaults should be at least 99.9%
        for ct, avail in _DEFAULT_AVAILABILITY.items():
            assert avail >= 0.999, f"{ct} has surprisingly low default availability: {avail}"
