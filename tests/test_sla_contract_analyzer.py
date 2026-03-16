"""Comprehensive tests for SLA Contract Analyzer (target: 100% coverage)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    ExternalSLAConfig,
    SLOTarget,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.sla_contract_analyzer import (
    BudgetAllocation,
    CascadeImpact,
    CompliancePeriod,
    ComplianceRecord,
    ComplianceReport,
    CompositeResult,
    ConsistencyResult,
    ConsistencyStatus,
    ErrorBudgetResult,
    MonitoringGap,
    NegotiationRecommendation,
    PenaltyEstimate,
    RiskLevel,
    SLAContract,
    SLAContractAnalyzer,
    SLAMetricType,
    ThirdPartyRisk,
    _MINUTES_PER_MONTH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "c1",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    slo_targets: list[SLOTarget] | None = None,
    external_sla: ExternalSLAConfig | None = None,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        slo_targets=slo_targets or [],
        external_sla=external_sla,
    )


def _graph(*comps: Component) -> InfraGraph:
    from faultray.model.graph import InfraGraph
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _dep(source: str, target: str, dep_type: str = "requires") -> Dependency:
    return Dependency(source_id=source, target_id=target, dependency_type=dep_type)


def _contract(
    sid: str = "c1",
    target: float = 99.9,
    metric: SLAMetricType = SLAMetricType.AVAILABILITY,
    penalty: float = 1000.0,
    contract_value: float = 10000.0,
    is_third_party: bool = False,
    provider_name: str = "",
    window: int = 30,
) -> SLAContract:
    return SLAContract(
        service_id=sid,
        metric_type=metric,
        target_value=target,
        penalty_rate_per_percent=penalty,
        measurement_window_days=window,
        monthly_contract_value=contract_value,
        is_third_party=is_third_party,
        provider_name=provider_name,
    )


def _record(
    sid: str = "c1",
    met: bool = True,
    actual: float = 99.95,
    target: float = 99.9,
    penalty: float = 0.0,
    days_ago: int = 10,
    downtime: float = 0.0,
) -> ComplianceRecord:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_ago)
    end = start + timedelta(days=1)
    return ComplianceRecord(
        service_id=sid,
        period_start=start,
        period_end=end,
        actual_value=actual,
        target_value=target,
        met_sla=met,
        penalty_incurred=penalty,
        downtime_minutes=downtime,
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def analyzer() -> SLAContractAnalyzer:
    return SLAContractAnalyzer()


# ===========================================================================
# Tests: Composite SLA
# ===========================================================================


class TestCompositeSLA:
    """Tests for calculate_composite_sla."""

    def test_empty_graph(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph()
        result = analyzer.calculate_composite_sla(g, {})
        assert result.composite_sla == 100.0
        assert result.weakest_service == ""
        assert result.chain_depth == 0
        assert result.services_analyzed == 0

    def test_single_service_with_contract(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1", target=99.9)}
        result = analyzer.calculate_composite_sla(g, contracts)
        assert result.composite_sla == pytest.approx(99.9, abs=0.01)
        assert result.weakest_service == "s1"
        assert result.services_analyzed == 1

    def test_single_service_no_contract(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        result = analyzer.calculate_composite_sla(g, {})
        assert result.composite_sla == pytest.approx(100.0, abs=0.01)
        assert result.services_analyzed == 1
        # Should recommend defining a contract.
        assert any("no SLA contract" in r for r in result.recommendations)

    def test_two_services_availability_composition(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(_dep("a", "b"))
        contracts = {
            "a": _contract("a", target=99.9),
            "b": _contract("b", target=99.9),
        }
        result = analyzer.calculate_composite_sla(g, contracts)
        # 99.9% * 99.9% = 99.8001%
        expected = 99.9 * 99.9 / 100.0
        assert result.composite_sla == pytest.approx(expected, abs=0.001)
        assert result.chain_depth >= 1

    def test_weakest_service_identified(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("a"), _comp("b"))
        contracts = {
            "a": _contract("a", target=99.99),
            "b": _contract("b", target=99.0),
        }
        result = analyzer.calculate_composite_sla(g, contracts)
        assert result.weakest_service == "b"

    def test_non_availability_metric_uses_minimum(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("a"), _comp("b"))
        contracts = {
            "a": _contract("a", target=95.0, metric=SLAMetricType.LATENCY),
            "b": _contract("b", target=98.0, metric=SLAMetricType.LATENCY),
        }
        result = analyzer.calculate_composite_sla(g, contracts)
        assert result.composite_sla == pytest.approx(95.0, abs=0.01)

    def test_low_composite_generates_recommendation(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("a"), _comp("b"))
        contracts = {
            "a": _contract("a", target=95.0),
            "b": _contract("b", target=95.0),
        }
        result = analyzer.calculate_composite_sla(g, contracts)
        assert result.composite_sla < 99.0
        assert any("below 99%" in r for r in result.recommendations)

    def test_deep_chain_recommendation(self, analyzer: SLAContractAnalyzer) -> None:
        comps = [_comp(f"s{i}") for i in range(7)]
        g = _graph(*comps)
        for i in range(6):
            g.add_dependency(_dep(f"s{i}", f"s{i+1}"))
        contracts = {f"s{i}": _contract(f"s{i}", target=99.99) for i in range(7)}
        result = analyzer.calculate_composite_sla(g, contracts)
        assert result.chain_depth > 5
        assert any("chain depth" in r.lower() for r in result.recommendations)

    def test_healthy_sla_message(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1", target=99.99)}
        result = analyzer.calculate_composite_sla(g, contracts)
        assert any("healthy" in r.lower() for r in result.recommendations)


# ===========================================================================
# Tests: Penalty Calculation
# ===========================================================================


class TestPenaltyCalculation:
    """Tests for calculate_penalty."""

    def test_no_breach(self, analyzer: SLAContractAnalyzer) -> None:
        c = _contract("s1", target=99.9)
        result = analyzer.calculate_penalty(c, actual_value=99.95)
        assert result.breach_amount_percent == 0.0
        assert result.penalty_amount == 0.0
        assert result.risk_level == RiskLevel.LOW
        assert "no penalty" in result.details.lower()

    def test_exact_target_no_breach(self, analyzer: SLAContractAnalyzer) -> None:
        c = _contract("s1", target=99.9)
        result = analyzer.calculate_penalty(c, actual_value=99.9)
        assert result.breach_amount_percent == 0.0
        assert result.penalty_amount == 0.0

    def test_small_breach(self, analyzer: SLAContractAnalyzer) -> None:
        c = _contract("s1", target=99.9, penalty=1000.0)
        result = analyzer.calculate_penalty(c, actual_value=99.5)
        assert result.breach_amount_percent == pytest.approx(0.4, abs=0.01)
        assert result.penalty_amount == pytest.approx(400.0, abs=0.01)
        assert result.risk_level == RiskLevel.LOW

    def test_medium_breach(self, analyzer: SLAContractAnalyzer) -> None:
        c = _contract("s1", target=99.9, penalty=1000.0)
        result = analyzer.calculate_penalty(c, actual_value=99.0)
        assert result.risk_level == RiskLevel.MEDIUM

    def test_high_breach(self, analyzer: SLAContractAnalyzer) -> None:
        c = _contract("s1", target=99.9, penalty=1000.0)
        result = analyzer.calculate_penalty(c, actual_value=97.0)
        assert result.risk_level == RiskLevel.HIGH

    def test_critical_breach(self, analyzer: SLAContractAnalyzer) -> None:
        c = _contract("s1", target=99.9, penalty=1000.0)
        result = analyzer.calculate_penalty(c, actual_value=90.0)
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.breach_amount_percent > 5.0

    def test_credit_percent_calculation(self, analyzer: SLAContractAnalyzer) -> None:
        c = _contract("s1", target=99.9, penalty=1000.0, contract_value=10000.0)
        result = analyzer.calculate_penalty(c, actual_value=98.9)
        # breach = 1.0%, penalty = 1000.0, credit = 1000/10000 * 100 = 10%
        assert result.contract_credit_percent == pytest.approx(10.0, abs=0.01)

    def test_zero_contract_value(self, analyzer: SLAContractAnalyzer) -> None:
        c = _contract("s1", target=99.9, penalty=1000.0, contract_value=0.0)
        result = analyzer.calculate_penalty(c, actual_value=98.9)
        assert result.contract_credit_percent == 0.0


# ===========================================================================
# Tests: Monitoring Gap Detection
# ===========================================================================


class TestMonitoringGaps:
    """Tests for detect_monitoring_gaps."""

    def test_no_gaps(self, analyzer: SLAContractAnalyzer) -> None:
        slo = SLOTarget(name="avail", metric="availability", target=99.9)
        g = _graph(_comp("s1", slo_targets=[slo]))
        contracts = {"s1": _contract("s1")}
        gaps = analyzer.detect_monitoring_gaps(g, contracts)
        assert len(gaps) == 0

    def test_no_contract(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        gaps = analyzer.detect_monitoring_gaps(g, {})
        assert len(gaps) == 1
        assert gaps[0].gap_type == "no_contract"
        assert gaps[0].severity == RiskLevel.MEDIUM

    def test_no_slo_targets(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1")}
        gaps = analyzer.detect_monitoring_gaps(g, contracts)
        assert any(g.gap_type == "no_slo_targets" for g in gaps)

    def test_third_party_missing_external_sla(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1", is_third_party=True, provider_name="AWS")}
        gaps = analyzer.detect_monitoring_gaps(g, contracts)
        assert any(g.gap_type == "missing_external_sla" for g in gaps)

    def test_metric_mismatch(self, analyzer: SLAContractAnalyzer) -> None:
        slo = SLOTarget(name="latency", metric="latency_p99", target=500.0, unit="ms")
        g = _graph(_comp("s1", slo_targets=[slo]))
        contracts = {"s1": _contract("s1", metric=SLAMetricType.AVAILABILITY)}
        gaps = analyzer.detect_monitoring_gaps(g, contracts)
        assert any(g.gap_type == "metric_mismatch" for g in gaps)

    def test_third_party_with_external_sla_no_gap(self, analyzer: SLAContractAnalyzer) -> None:
        slo = SLOTarget(name="avail", metric="availability", target=99.9)
        ext = ExternalSLAConfig(provider_sla=99.9)
        g = _graph(_comp("s1", slo_targets=[slo], external_sla=ext))
        contracts = {"s1": _contract("s1", is_third_party=True, provider_name="AWS")}
        gaps = analyzer.detect_monitoring_gaps(g, contracts)
        # Should have no gaps since SLO, external_sla, and metric all match.
        assert len(gaps) == 0


# ===========================================================================
# Tests: Upstream/Downstream Consistency
# ===========================================================================


class TestConsistency:
    """Tests for validate_consistency."""

    def test_consistent_simple(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(_dep("a", "b"))
        contracts = {
            "a": _contract("a", target=99.5),
            "b": _contract("b", target=99.9),
        }
        result = analyzer.validate_consistency(g, contracts, "a")
        assert result.status == ConsistencyStatus.CONSISTENT
        assert "b" in result.downstream_services

    def test_service_not_in_graph(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("a"))
        contracts = {"a": _contract("a")}
        result = analyzer.validate_consistency(g, contracts, "missing")
        assert result.status == ConsistencyStatus.CONSISTENT
        assert "not found" in result.issues[0].lower()

    def test_no_contract_warning(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("a"))
        result = analyzer.validate_consistency(g, {}, "a")
        assert result.status == ConsistencyStatus.WARNING

    def test_downstream_too_low(self, analyzer: SLAContractAnalyzer) -> None:
        """Service promises more than downstream can deliver."""
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(_dep("a", "b"))
        contracts = {
            "a": _contract("a", target=99.99),
            "b": _contract("b", target=99.0),
        }
        result = analyzer.validate_consistency(g, contracts, "a")
        assert result.status == ConsistencyStatus.INCONSISTENT
        assert len(result.issues) > 0
        assert any("downstream" in i.lower() for i in result.issues)

    def test_upstream_expects_more(self, analyzer: SLAContractAnalyzer) -> None:
        """Upstream service has higher SLA than this service."""
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(_dep("a", "b"))
        contracts = {
            "a": _contract("a", target=99.99),
            "b": _contract("b", target=99.0),
        }
        result = analyzer.validate_consistency(g, contracts, "b")
        assert result.status == ConsistencyStatus.INCONSISTENT
        assert any("upstream" in i.lower() for i in result.issues)


# ===========================================================================
# Tests: SLA Budget Allocation
# ===========================================================================


class TestBudgetAllocation:
    """Tests for allocate_sla_budget."""

    def test_empty_contracts(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        result = analyzer.allocate_sla_budget(g, {}, 100.0)
        assert result == []

    def test_single_service(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1")}
        result = analyzer.allocate_sla_budget(g, contracts, 100.0)
        assert len(result) == 1
        assert result[0].service_id == "s1"
        assert result[0].allocated_downtime_minutes == pytest.approx(100.0, abs=0.01)
        assert result[0].fraction_of_total == pytest.approx(1.0, abs=0.01)

    def test_critical_service_gets_less(self, analyzer: SLAContractAnalyzer) -> None:
        """Service with more dependents gets less downtime budget."""
        a = _comp("a")
        b = _comp("b")
        c = _comp("c")
        g = _graph(a, b, c)
        g.add_dependency(_dep("b", "a"))  # b depends on a
        g.add_dependency(_dep("c", "a"))  # c depends on a
        contracts = {
            "a": _contract("a"),
            "b": _contract("b"),
            "c": _contract("c"),
        }
        result = analyzer.allocate_sla_budget(g, contracts, 300.0)
        alloc_map = {a.service_id: a for a in result}
        # 'a' has 2 dependents => weight 1/(1+2)=0.333
        # 'b' has 0 dependents => weight 1/(1+0)=1.0
        # 'c' has 0 dependents => weight 1/(1+0)=1.0
        assert alloc_map["a"].allocated_downtime_minutes < alloc_map["b"].allocated_downtime_minutes

    def test_service_not_in_graph(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph()
        contracts = {"x": _contract("x")}
        result = analyzer.allocate_sla_budget(g, contracts, 100.0)
        assert len(result) == 1
        assert result[0].service_id == "x"

    def test_sorted_by_allocated_minutes(self, analyzer: SLAContractAnalyzer) -> None:
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(_dep("b", "a"))
        contracts = {"a": _contract("a"), "b": _contract("b")}
        result = analyzer.allocate_sla_budget(g, contracts, 200.0)
        assert result[0].allocated_downtime_minutes <= result[1].allocated_downtime_minutes


# ===========================================================================
# Tests: Historical Compliance Tracking
# ===========================================================================


class TestComplianceTracking:
    """Tests for track_compliance."""

    def test_empty_records(self, analyzer: SLAContractAnalyzer) -> None:
        result = analyzer.track_compliance([])
        assert result["total_records"] == 0
        assert result["overall_compliance_rate"] == 100.0
        assert result["total_penalty"] == 0.0

    def test_all_met(self, analyzer: SLAContractAnalyzer) -> None:
        records = [
            _record("s1", met=True, penalty=0.0),
            _record("s1", met=True, penalty=0.0, days_ago=5),
        ]
        result = analyzer.track_compliance(records)
        assert result["overall_compliance_rate"] == 100.0
        assert result["total_penalty"] == 0.0
        per = result["per_service"]
        assert "s1" in per
        assert per["s1"]["compliance_rate"] == 100.0

    def test_mixed_compliance(self, analyzer: SLAContractAnalyzer) -> None:
        records = [
            _record("s1", met=True),
            _record("s1", met=False, actual=98.0, penalty=500.0, days_ago=5),
            _record("s2", met=False, actual=95.0, penalty=1000.0),
        ]
        result = analyzer.track_compliance(records)
        assert result["total_records"] == 3
        assert result["overall_compliance_rate"] == pytest.approx(33.33, abs=0.1)
        assert result["total_penalty"] == 1500.0
        per = result["per_service"]
        assert per["s1"]["compliance_rate"] == 50.0
        assert per["s2"]["worst_actual"] == 95.0

    def test_multiple_services(self, analyzer: SLAContractAnalyzer) -> None:
        records = [
            _record("s1", met=True),
            _record("s2", met=True),
            _record("s3", met=False, penalty=200.0),
        ]
        result = analyzer.track_compliance(records)
        assert len(result["per_service"]) == 3
        assert result["total_penalty"] == 200.0


# ===========================================================================
# Tests: Error Budget Derivation
# ===========================================================================


class TestErrorBudget:
    """Tests for derive_error_budget."""

    def test_three_nines(self, analyzer: SLAContractAnalyzer) -> None:
        c = _contract("s1", target=99.9)
        result = analyzer.derive_error_budget(c)
        assert result.error_budget_percent == pytest.approx(0.1, abs=0.001)
        # 43200 * 0.001 = 43.2 minutes
        assert result.error_budget_minutes_per_month == pytest.approx(43.2, abs=0.1)
        assert result.monthly_request_budget == pytest.approx(1000.0, abs=1.0)

    def test_two_nines(self, analyzer: SLAContractAnalyzer) -> None:
        c = _contract("s1", target=99.0)
        result = analyzer.derive_error_budget(c, monthly_requests=100_000)
        assert result.error_budget_percent == pytest.approx(1.0, abs=0.001)
        assert result.monthly_request_budget == pytest.approx(1000.0, abs=1.0)

    def test_perfect_sla(self, analyzer: SLAContractAnalyzer) -> None:
        c = _contract("s1", target=100.0)
        result = analyzer.derive_error_budget(c)
        assert result.error_budget_percent == 0.0
        assert result.error_budget_minutes_per_month == 0.0

    def test_custom_requests(self, analyzer: SLAContractAnalyzer) -> None:
        c = _contract("s1", target=99.9)
        result = analyzer.derive_error_budget(c, monthly_requests=10_000_000)
        assert result.monthly_request_budget == pytest.approx(10_000.0, abs=1.0)


# ===========================================================================
# Tests: SLA Negotiation Recommendations
# ===========================================================================


class TestNegotiations:
    """Tests for recommend_negotiations."""

    def test_no_recommendations_healthy(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1", target=99.99)}
        recs = analyzer.recommend_negotiations(g, contracts)
        assert recs == []

    def test_downstream_unreachable(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(_dep("a", "b"))
        contracts = {
            "a": _contract("a", target=99.99),
            "b": _contract("b", target=99.0),
        }
        recs = analyzer.recommend_negotiations(g, contracts)
        a_recs = [r for r in recs if r.service_id == "a"]
        assert len(a_recs) >= 1
        assert any("unreachable" in r.rationale.lower() for r in a_recs)

    def test_critical_service_upgrade(self, analyzer: SLAContractAnalyzer) -> None:
        """Service with 4+ dependents and low SLA -> recommend upgrade."""
        comps = [_comp("core")] + [_comp(f"dep{i}") for i in range(4)]
        g = _graph(*comps)
        for i in range(4):
            g.add_dependency(_dep(f"dep{i}", "core"))
        contracts = {"core": _contract("core", target=99.5)}
        recs = analyzer.recommend_negotiations(g, contracts)
        core_recs = [r for r in recs if r.service_id == "core"]
        assert len(core_recs) >= 1
        assert any(r.recommended_target == 99.99 for r in core_recs)

    def test_third_party_low_sla(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {
            "s1": _contract("s1", target=99.0, is_third_party=True, provider_name="Vendor")
        }
        recs = analyzer.recommend_negotiations(g, contracts)
        assert len(recs) >= 1
        assert any("third-party" in r.rationale.lower() for r in recs)

    def test_service_not_in_graph_skipped(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {"missing": _contract("missing", target=99.0)}
        recs = analyzer.recommend_negotiations(g, contracts)
        assert recs == []


# ===========================================================================
# Tests: Compliance Reporting
# ===========================================================================


class TestComplianceReport:
    """Tests for generate_compliance_report."""

    def test_empty_report(self, analyzer: SLAContractAnalyzer) -> None:
        now = datetime.now(timezone.utc)
        report = analyzer.generate_compliance_report(
            {}, [], period_start=now - timedelta(days=30), period_end=now,
        )
        assert report.overall_compliance_rate == 100.0
        assert report.total_penalty == 0.0
        assert report.services_in_compliance == 0
        assert report.services_in_violation == 0

    def test_monthly_report(self, analyzer: SLAContractAnalyzer) -> None:
        now = datetime.now(timezone.utc)
        records = [
            _record("s1", met=True, days_ago=5),
            _record("s1", met=False, penalty=500.0, actual=98.0, days_ago=10),
            _record("s2", met=True, days_ago=7),
        ]
        contracts = {"s1": _contract("s1"), "s2": _contract("s2")}
        report = analyzer.generate_compliance_report(
            contracts, records,
            period=CompliancePeriod.MONTHLY,
            period_start=now - timedelta(days=30),
            period_end=now,
        )
        assert report.period == CompliancePeriod.MONTHLY
        assert report.total_penalty == 500.0
        assert report.services_in_violation >= 1
        assert "monthly" in report.summary.lower()

    def test_quarterly_report(self, analyzer: SLAContractAnalyzer) -> None:
        now = datetime.now(timezone.utc)
        records = [_record("s1", met=True, days_ago=i) for i in range(1, 80, 10)]
        contracts = {"s1": _contract("s1")}
        report = analyzer.generate_compliance_report(
            contracts, records,
            period=CompliancePeriod.QUARTERLY,
            period_start=now - timedelta(days=90),
            period_end=now,
        )
        assert report.period == CompliancePeriod.QUARTERLY
        assert report.overall_compliance_rate == 100.0

    def test_high_penalty_recommendation(self, analyzer: SLAContractAnalyzer) -> None:
        now = datetime.now(timezone.utc)
        records = [
            _record("s1", met=False, penalty=6000.0, days_ago=5),
            _record("s2", met=False, penalty=6000.0, days_ago=10),
        ]
        contracts = {"s1": _contract("s1"), "s2": _contract("s2")}
        report = analyzer.generate_compliance_report(
            contracts, records,
            period_start=now - timedelta(days=30),
            period_end=now,
        )
        assert report.total_penalty == 12000.0
        assert any("significant" in r.lower() for r in report.recommendations)

    def test_default_period_boundaries(self, analyzer: SLAContractAnalyzer) -> None:
        """When period_start/end are None, defaults should be applied."""
        records = [_record("s1", met=True, days_ago=5)]
        contracts = {"s1": _contract("s1")}
        report = analyzer.generate_compliance_report(contracts, records)
        assert report.period == CompliancePeriod.MONTHLY
        # Should have period_start and period_end set.
        assert report.period_start < report.period_end

    def test_contract_without_records(self, analyzer: SLAContractAnalyzer) -> None:
        """Service with contract but no records in period should be in compliance."""
        now = datetime.now(timezone.utc)
        contracts = {"s1": _contract("s1")}
        report = analyzer.generate_compliance_report(
            contracts, [],
            period_start=now - timedelta(days=30), period_end=now,
        )
        assert report.services_in_compliance == 1
        assert report.services_in_violation == 0


# ===========================================================================
# Tests: Third-Party Risk Assessment
# ===========================================================================


class TestThirdPartyRisk:
    """Tests for assess_third_party_risk."""

    def test_no_third_parties(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1")}
        risks = analyzer.assess_third_party_risk(g, contracts)
        assert risks == []

    def test_low_risk_third_party(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"), _comp("tp"))
        contracts = {
            "s1": _contract("s1", target=99.99),
            "tp": _contract("tp", target=99.99, is_third_party=True, provider_name="AWS"),
        }
        risks = analyzer.assess_third_party_risk(g, contracts)
        assert len(risks) == 1
        assert risks[0].risk_level == RiskLevel.LOW

    def test_high_risk_third_party(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"), _comp("tp"))
        contracts = {
            "s1": _contract("s1", target=99.9),
            "tp": _contract("tp", target=98.0, is_third_party=True, provider_name="Vendor"),
        }
        risks = analyzer.assess_third_party_risk(g, contracts)
        assert len(risks) == 1
        # impact = composite_without_tp - composite_with_tp
        # without = 99.9, with = 99.9 * 98.0 / 100 = 97.902
        # impact ~= 1.998 -> CRITICAL
        assert risks[0].risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert risks[0].recommendation != ""

    def test_medium_risk_third_party(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"), _comp("tp"))
        contracts = {
            "s1": _contract("s1", target=99.9),
            "tp": _contract("tp", target=99.7, is_third_party=True, provider_name="CDN"),
        }
        risks = analyzer.assess_third_party_risk(g, contracts)
        assert len(risks) == 1
        assert risks[0].provider_name == "CDN"


# ===========================================================================
# Tests: SLA Cascade Impact
# ===========================================================================


class TestCascadeImpact:
    """Tests for analyze_cascade_impact."""

    def test_single_service_breach(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1", target=99.9)}
        result = analyzer.analyze_cascade_impact(g, contracts, "s1")
        assert result.breached_service == "s1"
        assert result.original_composite == pytest.approx(99.9, abs=0.01)
        assert result.degraded_composite < result.original_composite
        assert result.composite_drop > 0

    def test_cascade_with_dependencies(self, analyzer: SLAContractAnalyzer) -> None:
        a = _comp("a")
        b = _comp("b")
        c = _comp("c")
        g = _graph(a, b, c)
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "c"))
        contracts = {
            "a": _contract("a", target=99.9),
            "b": _contract("b", target=99.9),
            "c": _contract("c", target=99.9),
        }
        result = analyzer.analyze_cascade_impact(g, contracts, "c")
        assert "b" in result.affected_services or "a" in result.affected_services
        assert result.cascade_depth >= 1

    def test_explicit_degraded_sla(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1", target=99.9)}
        result = analyzer.analyze_cascade_impact(g, contracts, "s1", degraded_sla=95.0)
        assert result.degraded_composite == pytest.approx(95.0, abs=0.01)
        assert result.composite_drop > 4.0
        assert result.risk_level == RiskLevel.CRITICAL

    def test_service_not_in_graph(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1")}
        result = analyzer.analyze_cascade_impact(g, contracts, "missing")
        assert result.breached_service == "missing"
        assert result.affected_services == []

    def test_low_risk_level(self, analyzer: SLAContractAnalyzer) -> None:
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1", target=99.999)}
        result = analyzer.analyze_cascade_impact(g, contracts, "s1")
        # Default degradation is 1% of current = 99.999 * 0.99 = 98.99901
        # Drop is small relative to 100
        assert result.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH)


# ===========================================================================
# Tests: Internal Helpers
# ===========================================================================


class TestInternalHelpers:
    """Tests for static/private methods."""

    def test_dominant_metric_empty(self) -> None:
        result = SLAContractAnalyzer._dominant_metric({})
        assert result == SLAMetricType.AVAILABILITY

    def test_dominant_metric_latency(self) -> None:
        contracts = {
            "a": _contract("a", metric=SLAMetricType.LATENCY),
            "b": _contract("b", metric=SLAMetricType.LATENCY),
            "c": _contract("c", metric=SLAMetricType.AVAILABILITY),
        }
        result = SLAContractAnalyzer._dominant_metric(contracts)
        assert result == SLAMetricType.LATENCY

    def test_multiply_availability(self) -> None:
        result = SLAContractAnalyzer._multiply_availability(
            {"a": 99.9, "b": 99.9}
        )
        assert result == pytest.approx(99.8001, abs=0.001)

    def test_multiply_availability_single(self) -> None:
        result = SLAContractAnalyzer._multiply_availability({"a": 99.0})
        assert result == pytest.approx(99.0, abs=0.001)

    def test_max_chain_depth_empty(self) -> None:
        g = _graph()
        assert SLAContractAnalyzer._max_chain_depth(g) == 0

    def test_max_chain_depth_chain(self) -> None:
        comps = [_comp(f"s{i}") for i in range(4)]
        g = _graph(*comps)
        for i in range(3):
            g.add_dependency(_dep(f"s{i}", f"s{i+1}"))
        depth = SLAContractAnalyzer._max_chain_depth(g)
        assert depth >= 3

    def test_cascade_depth_bfs_not_in_graph(self) -> None:
        g = _graph(_comp("s1"))
        assert SLAContractAnalyzer._cascade_depth_bfs(g, "missing") == 0

    def test_cascade_depth_bfs_single(self) -> None:
        g = _graph(_comp("s1"))
        assert SLAContractAnalyzer._cascade_depth_bfs(g, "s1") == 0

    def test_cascade_depth_bfs_chain(self) -> None:
        a, b, c = _comp("a"), _comp("b"), _comp("c")
        g = _graph(a, b, c)
        g.add_dependency(_dep("b", "a"))
        g.add_dependency(_dep("c", "b"))
        depth = SLAContractAnalyzer._cascade_depth_bfs(g, "a")
        assert depth >= 1


# ===========================================================================
# Tests: Enum and Model coverage
# ===========================================================================


class TestModels:
    """Tests for enum values and model defaults."""

    def test_sla_metric_type_values(self) -> None:
        assert SLAMetricType.AVAILABILITY.value == "availability"
        assert SLAMetricType.LATENCY.value == "latency"
        assert SLAMetricType.THROUGHPUT.value == "throughput"
        assert SLAMetricType.ERROR_RATE.value == "error_rate"
        assert SLAMetricType.DURABILITY.value == "durability"

    def test_compliance_period_values(self) -> None:
        assert CompliancePeriod.MONTHLY.value == "monthly"
        assert CompliancePeriod.QUARTERLY.value == "quarterly"

    def test_risk_level_values(self) -> None:
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_consistency_status_values(self) -> None:
        assert ConsistencyStatus.CONSISTENT.value == "consistent"
        assert ConsistencyStatus.INCONSISTENT.value == "inconsistent"
        assert ConsistencyStatus.WARNING.value == "warning"

    def test_sla_contract_defaults(self) -> None:
        c = SLAContract(service_id="test")
        assert c.metric_type == SLAMetricType.AVAILABILITY
        assert c.target_value == 99.9
        assert c.penalty_rate_per_percent == 1000.0
        assert c.measurement_window_days == 30
        assert c.monthly_contract_value == 10000.0
        assert c.is_third_party is False
        assert c.provider_name == ""

    def test_composite_result_defaults(self) -> None:
        r = CompositeResult(
            composite_sla=99.9,
            weakest_service="s1",
            chain_depth=1,
            services_analyzed=1,
        )
        assert r.per_service_sla == {}
        assert r.recommendations == []

    def test_penalty_estimate_defaults(self) -> None:
        p = PenaltyEstimate(
            service_id="s1",
            breach_amount_percent=0.1,
            penalty_amount=100.0,
            contract_credit_percent=1.0,
            risk_level=RiskLevel.LOW,
        )
        assert p.details == ""

    def test_monitoring_gap_defaults(self) -> None:
        mg = MonitoringGap(
            service_id="s1",
            gap_type="test",
            description="desc",
            severity=RiskLevel.LOW,
        )
        assert mg.recommendation == ""

    def test_consistency_result_defaults(self) -> None:
        cr = ConsistencyResult(status=ConsistencyStatus.CONSISTENT)
        assert cr.issues == []
        assert cr.upstream_services == []
        assert cr.downstream_services == []
        assert cr.recommendations == []

    def test_error_budget_result(self) -> None:
        eb = ErrorBudgetResult(
            service_id="s1",
            target_value=99.9,
            error_budget_percent=0.1,
            error_budget_minutes_per_month=43.2,
            monthly_request_budget=1000.0,
        )
        assert eb.service_id == "s1"

    def test_cascade_impact_defaults(self) -> None:
        ci = CascadeImpact(
            breached_service="s1",
            original_composite=99.9,
            degraded_composite=99.0,
            composite_drop=0.9,
        )
        assert ci.affected_services == []
        assert ci.cascade_depth == 0
        assert ci.risk_level == RiskLevel.LOW

    def test_negotiation_recommendation_defaults(self) -> None:
        nr = NegotiationRecommendation(
            service_id="s1",
            current_target=99.0,
            recommended_target=99.9,
            rationale="test",
        )
        assert nr.estimated_cost_impact == 0.0

    def test_compliance_report_defaults(self) -> None:
        now = datetime.now(timezone.utc)
        cr = ComplianceReport(
            period=CompliancePeriod.MONTHLY,
            period_start=now,
            period_end=now,
            overall_compliance_rate=100.0,
            services_in_compliance=0,
            services_in_violation=0,
            total_penalty=0.0,
        )
        assert cr.per_service == []
        assert cr.summary == ""
        assert cr.recommendations == []

    def test_third_party_risk_defaults(self) -> None:
        tp = ThirdPartyRisk(
            service_id="s1",
            provider_name="AWS",
            provider_sla=99.9,
            impact_on_composite=0.1,
            risk_level=RiskLevel.LOW,
        )
        assert tp.recommendation == ""

    def test_budget_allocation_model(self) -> None:
        ba = BudgetAllocation(
            service_id="s1",
            allocated_downtime_minutes=43.2,
            weight=1.0,
            fraction_of_total=0.5,
        )
        assert ba.service_id == "s1"

    def test_compliance_record_model(self) -> None:
        now = datetime.now(timezone.utc)
        cr = ComplianceRecord(
            service_id="s1",
            period_start=now,
            period_end=now + timedelta(days=1),
            actual_value=99.95,
            target_value=99.9,
            met_sla=True,
        )
        assert cr.penalty_incurred == 0.0
        assert cr.downtime_minutes == 0.0

    def test_minutes_per_month_constant(self) -> None:
        assert _MINUTES_PER_MONTH == 43200.0


# ===========================================================================
# Tests: Edge Cases and Integration
# ===========================================================================


class TestEdgeCases:
    """Edge cases and integration scenarios."""

    def test_large_chain_composite(self, analyzer: SLAContractAnalyzer) -> None:
        """10-service chain should degrade composite significantly."""
        comps = [_comp(f"s{i}") for i in range(10)]
        g = _graph(*comps)
        for i in range(9):
            g.add_dependency(_dep(f"s{i}", f"s{i+1}"))
        contracts = {f"s{i}": _contract(f"s{i}", target=99.9) for i in range(10)}
        result = analyzer.calculate_composite_sla(g, contracts)
        # 99.9^10 / 100^9 ~ 99.0044%
        assert result.composite_sla < 99.1
        assert result.chain_depth >= 9

    def test_all_perfect_sla(self, analyzer: SLAContractAnalyzer) -> None:
        """All services at 100% should produce 100% composite."""
        g = _graph(_comp("a"), _comp("b"))
        contracts = {
            "a": _contract("a", target=100.0),
            "b": _contract("b", target=100.0),
        }
        result = analyzer.calculate_composite_sla(g, contracts)
        assert result.composite_sla == pytest.approx(100.0, abs=0.001)

    def test_third_party_only_service_in_graph(self, analyzer: SLAContractAnalyzer) -> None:
        """Only a third-party service in graph -> composite_without is empty."""
        g = _graph(_comp("tp"))
        contracts = {
            "tp": _contract("tp", target=99.0, is_third_party=True, provider_name="AWS"),
        }
        risks = analyzer.assess_third_party_risk(g, contracts)
        assert len(risks) == 1
        # With only one service, without map is empty -> composite_without = 100.0
        assert risks[0].impact_on_composite > 0

    def test_third_party_high_risk(self, analyzer: SLAContractAnalyzer) -> None:
        """Third-party with impact > 0.5 but <= 1.0 -> HIGH risk."""
        g = _graph(_comp("s1"), _comp("tp"))
        contracts = {
            "s1": _contract("s1", target=99.99),
            "tp": _contract("tp", target=99.3, is_third_party=True, provider_name="Vendor"),
        }
        risks = analyzer.assess_third_party_risk(g, contracts)
        assert len(risks) == 1
        # without tp: 99.99, with tp: 99.99 * 99.3 / 100 = 99.2901..
        # impact ~ 0.6999 -> HIGH
        assert risks[0].risk_level == RiskLevel.HIGH
        assert risks[0].recommendation != ""

    def test_cascade_medium_risk(self, analyzer: SLAContractAnalyzer) -> None:
        """Cascade drop > 0.1 but <= 0.5 -> MEDIUM risk."""
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1", target=99.9)}
        # Degrade to 99.6 -> drop = 99.9 - 99.6 = 0.3 -> MEDIUM
        result = analyzer.analyze_cascade_impact(g, contracts, "s1", degraded_sla=99.6)
        assert result.composite_drop == pytest.approx(0.3, abs=0.01)
        assert result.risk_level == RiskLevel.MEDIUM

    def test_cascade_high_risk(self, analyzer: SLAContractAnalyzer) -> None:
        """Cascade drop > 0.5 but <= 1.0 -> HIGH risk."""
        g = _graph(_comp("s1"))
        contracts = {"s1": _contract("s1", target=99.9)}
        result = analyzer.analyze_cascade_impact(g, contracts, "s1", degraded_sla=99.2)
        assert result.composite_drop == pytest.approx(0.7, abs=0.01)
        assert result.risk_level == RiskLevel.HIGH

    def test_max_chain_depth_with_cycle(self, analyzer: SLAContractAnalyzer) -> None:
        """Graph with a cycle should fall back to len(components)."""
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "a"))
        depth = SLAContractAnalyzer._max_chain_depth(g)
        # Should fall back to len(components) = 2 for cyclic graph.
        assert depth == 2

    def test_cascade_bfs_revisit(self, analyzer: SLAContractAnalyzer) -> None:
        """BFS with diamond dependency hits 'continue' for already-visited node."""
        a = _comp("a")
        b = _comp("b")
        c = _comp("c")
        d = _comp("d")
        g = _graph(a, b, c, d)
        # d depends on a and b; both a and b depend on c (diamond).
        g.add_dependency(_dep("b", "a"))
        g.add_dependency(_dep("c", "a"))
        g.add_dependency(_dep("c", "b"))
        g.add_dependency(_dep("d", "c"))
        # Cascade from a: a -> b,c -> c(already visited),d
        depth = SLAContractAnalyzer._cascade_depth_bfs(g, "a")
        assert depth >= 2

    def test_full_workflow(self, analyzer: SLAContractAnalyzer) -> None:
        """Integration test: full analysis workflow."""
        a = _comp("api", slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)])
        b = _comp("db", slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)])
        tp = _comp(
            "cdn",
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
            external_sla=ExternalSLAConfig(provider_sla=99.9),
        )
        g = _graph(a, b, tp)
        g.add_dependency(_dep("api", "db"))
        g.add_dependency(_dep("api", "cdn"))

        contracts = {
            "api": _contract("api", target=99.9),
            "db": _contract("db", target=99.95),
            "cdn": _contract("cdn", target=99.9, is_third_party=True, provider_name="CloudFront"),
        }

        # Composite SLA
        composite = analyzer.calculate_composite_sla(g, contracts)
        assert composite.composite_sla > 0
        assert composite.services_analyzed == 3

        # Monitoring gaps
        gaps = analyzer.detect_monitoring_gaps(g, contracts)
        assert isinstance(gaps, list)

        # Consistency
        consistency = analyzer.validate_consistency(g, contracts, "api")
        assert isinstance(consistency.status, ConsistencyStatus)

        # Budget allocation
        alloc = analyzer.allocate_sla_budget(g, contracts, 100.0)
        assert len(alloc) == 3

        # Error budget
        eb = analyzer.derive_error_budget(contracts["api"])
        assert eb.error_budget_percent > 0

        # Cascade impact
        cascade = analyzer.analyze_cascade_impact(g, contracts, "db")
        assert cascade.breached_service == "db"

        # Third-party risk
        tp_risks = analyzer.assess_third_party_risk(g, contracts)
        assert len(tp_risks) == 1

        # Negotiation recommendations
        neg_recs = analyzer.recommend_negotiations(g, contracts)
        assert isinstance(neg_recs, list)

        # Penalty
        penalty = analyzer.calculate_penalty(contracts["api"], 99.5)
        assert penalty.penalty_amount > 0

        # Compliance tracking
        records = [
            _record("api", met=True, days_ago=5),
            _record("db", met=False, penalty=300.0, actual=99.0, days_ago=10),
        ]
        tracking = analyzer.track_compliance(records)
        assert tracking["total_records"] == 2

        # Compliance report
        report = analyzer.generate_compliance_report(contracts, records)
        assert isinstance(report.summary, str)
