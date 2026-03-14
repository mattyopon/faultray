"""Tests for the Compliance Engine (SOC 2, ISO 27001, PCI DSS, NIST CSF)."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.compliance_engine import ComplianceCheck, ComplianceEngine, ComplianceReport


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_graph() -> InfraGraph:
    """A minimal graph with no security features - should fail most checks."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="app-server",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db",
        name="database",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app",
        target_id="db",
        dependency_type="requires",
    ))
    return graph


@pytest.fixture
def secure_graph() -> InfraGraph:
    """A well-configured graph with security features - should pass most checks."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="waf",
        name="WAF / API Gateway",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
    ))
    graph.add_component(Component(
        id="app",
        name="app-server",
        type=ComponentType.APP_SERVER,
        port=443,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
    ))
    graph.add_component(Component(
        id="db",
        name="PostgreSQL",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=2,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=15),
        region=RegionConfig(
            region="us-east-1",
            dr_target_region="us-west-2",
        ),
    ))
    graph.add_component(Component(
        id="otel-collector",
        name="OpenTelemetry Collector",
        type=ComponentType.CUSTOM,
        port=4317,
        replicas=2,
    ))

    graph.add_dependency(Dependency(
        source_id="waf",
        target_id="app",
        dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app",
        target_id="db",
        dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return graph


# ---------------------------------------------------------------------------
# ComplianceCheck dataclass tests
# ---------------------------------------------------------------------------


class TestComplianceCheck:
    def test_fields(self):
        check = ComplianceCheck(
            framework="soc2",
            control_id="CC6.1",
            description="Access controls",
            status="pass",
            evidence="Auth component found",
            recommendation="",
        )
        assert check.framework == "soc2"
        assert check.control_id == "CC6.1"
        assert check.status == "pass"

    def test_fail_status(self):
        check = ComplianceCheck(
            framework="pci_dss",
            control_id="Req-10.1",
            description="Audit trails",
            status="fail",
            evidence="No monitoring",
            recommendation="Deploy monitoring",
        )
        assert check.status == "fail"
        assert check.recommendation == "Deploy monitoring"


# ---------------------------------------------------------------------------
# ComplianceReport dataclass tests
# ---------------------------------------------------------------------------


class TestComplianceReport:
    def test_empty_report(self):
        report = ComplianceReport(framework="soc2")
        assert report.total_checks == 0
        assert report.compliance_percent == 0.0

    def test_report_with_checks(self):
        report = ComplianceReport(
            framework="soc2",
            total_checks=5,
            passed=3,
            failed=1,
            partial=1,
            compliance_percent=70.0,
            checks=[],
        )
        assert report.passed == 3
        assert report.failed == 1


# ---------------------------------------------------------------------------
# SOC 2 Type II
# ---------------------------------------------------------------------------


class TestSOC2:
    def test_minimal_graph_fails_most_checks(self, minimal_graph):
        engine = ComplianceEngine(minimal_graph)
        report = engine.check_soc2()
        assert report.framework == "soc2"
        assert report.total_checks >= 4
        assert report.failed >= 2  # no auth, no monitoring at minimum

    def test_secure_graph_passes_most_checks(self, secure_graph):
        engine = ComplianceEngine(secure_graph)
        report = engine.check_soc2()
        assert report.framework == "soc2"
        assert report.passed >= 3
        assert report.compliance_percent >= 70.0

    def test_cc6_1_access_control(self, secure_graph):
        engine = ComplianceEngine(secure_graph)
        report = engine.check_soc2()
        cc6_1 = [c for c in report.checks if c.control_id == "CC6.1"]
        assert len(cc6_1) == 1
        assert cc6_1[0].status == "pass"  # WAF component present

    def test_cc7_2_monitoring(self, minimal_graph):
        engine = ComplianceEngine(minimal_graph)
        report = engine.check_soc2()
        cc7_2 = [c for c in report.checks if c.control_id == "CC7.2"]
        assert len(cc7_2) == 1
        assert cc7_2[0].status == "fail"  # no monitoring


# ---------------------------------------------------------------------------
# ISO 27001
# ---------------------------------------------------------------------------


class TestISO27001:
    def test_minimal_graph_has_low_compliance(self, minimal_graph):
        engine = ComplianceEngine(minimal_graph)
        report = engine.check_iso27001()
        assert report.framework == "iso27001"
        assert report.total_checks >= 5
        assert report.failed >= 2

    def test_secure_graph_has_high_compliance(self, secure_graph):
        engine = ComplianceEngine(secure_graph)
        report = engine.check_iso27001()
        assert report.passed >= 4
        assert report.compliance_percent >= 70.0

    def test_a17_business_continuity(self, secure_graph):
        engine = ComplianceEngine(secure_graph)
        report = engine.check_iso27001()
        a17 = [c for c in report.checks if c.control_id.startswith("A.17")]
        assert len(a17) >= 2
        # DR region and failover both present
        a17_1_1 = [c for c in a17 if c.control_id == "A.17.1.1"]
        assert a17_1_1[0].status == "pass"


# ---------------------------------------------------------------------------
# PCI DSS
# ---------------------------------------------------------------------------


class TestPCIDSS:
    def test_minimal_graph_fails(self, minimal_graph):
        engine = ComplianceEngine(minimal_graph)
        report = engine.check_pci_dss()
        assert report.framework == "pci_dss"
        assert report.total_checks >= 5
        assert report.failed >= 2

    def test_secure_graph_passes(self, secure_graph):
        engine = ComplianceEngine(secure_graph)
        report = engine.check_pci_dss()
        assert report.passed >= 3
        assert report.compliance_percent >= 60.0

    def test_req_10_audit_trails(self, secure_graph):
        engine = ComplianceEngine(secure_graph)
        report = engine.check_pci_dss()
        req_10_1 = [c for c in report.checks if c.control_id == "Req-10.1"]
        assert len(req_10_1) == 1
        assert req_10_1[0].status == "pass"  # otel-collector present


# ---------------------------------------------------------------------------
# NIST CSF
# ---------------------------------------------------------------------------


class TestNISTCSF:
    def test_minimal_graph_has_low_compliance(self, minimal_graph):
        engine = ComplianceEngine(minimal_graph)
        report = engine.check_nist_csf()
        assert report.framework == "nist_csf"
        assert report.total_checks >= 7
        assert report.failed >= 3

    def test_secure_graph_has_high_compliance(self, secure_graph):
        engine = ComplianceEngine(secure_graph)
        report = engine.check_nist_csf()
        assert report.passed >= 5
        assert report.compliance_percent >= 70.0

    def test_identify_function(self, secure_graph):
        engine = ComplianceEngine(secure_graph)
        report = engine.check_nist_csf()
        id_checks = [c for c in report.checks if c.control_id.startswith("ID.")]
        assert len(id_checks) >= 2
        assert all(c.status == "pass" for c in id_checks)

    def test_recover_function(self, secure_graph):
        engine = ComplianceEngine(secure_graph)
        report = engine.check_nist_csf()
        rc_checks = [c for c in report.checks if c.control_id.startswith("RC.")]
        assert len(rc_checks) >= 1


# ---------------------------------------------------------------------------
# check_all
# ---------------------------------------------------------------------------


class TestCheckAll:
    def test_returns_all_frameworks(self, secure_graph):
        engine = ComplianceEngine(secure_graph)
        all_reports = engine.check_all()
        assert "soc2" in all_reports
        assert "iso27001" in all_reports
        assert "pci_dss" in all_reports
        assert "nist_csf" in all_reports

    def test_all_reports_have_checks(self, secure_graph):
        engine = ComplianceEngine(secure_graph)
        all_reports = engine.check_all()
        for fw, report in all_reports.items():
            assert report.total_checks > 0, f"{fw} has no checks"
            assert report.framework == fw


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_graph(self):
        graph = InfraGraph()
        engine = ComplianceEngine(graph)
        report = engine.check_soc2()
        assert report.total_checks >= 4
        # Empty graph: no auth, no monitoring, etc.

    def test_partial_encryption(self):
        """Graph with both encrypted and non-encrypted components."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="lb",
            name="load-balancer",
            type=ComponentType.LOAD_BALANCER,
            port=443,  # encrypted
            replicas=2,
        ))
        graph.add_component(Component(
            id="app",
            name="app-server",
            type=ComponentType.APP_SERVER,
            port=80,  # NOT encrypted
            replicas=1,
        ))
        graph.add_dependency(Dependency(
            source_id="lb", target_id="app", dependency_type="requires",
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_soc2()
        cc6_6 = [c for c in report.checks if c.control_id == "CC6.6"]
        assert cc6_6[0].status == "partial"

    def test_no_dependencies_circuit_breaker_na(self):
        """Graph with no dependencies should mark CB as not_applicable."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="standalone",
            name="standalone-app",
            type=ComponentType.APP_SERVER,
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_soc2()
        pi1_3 = [c for c in report.checks if c.control_id == "PI1.3"]
        assert pi1_3[0].status == "not_applicable"

    def test_compliance_percent_calculation(self):
        """Verify compliance percentage calculation with mixed results."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="auth-gateway",
            name="Auth Gateway",
            type=ComponentType.LOAD_BALANCER,
            port=443,
            replicas=2,
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_soc2()
        # At least passes auth (CC6.1) and encryption (CC6.6)
        assert report.compliance_percent > 0
        assert report.compliance_percent <= 100
