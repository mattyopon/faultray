"""Tests for the Compliance Engine (SOC 2, ISO 27001, PCI DSS, NIST CSF)."""

from __future__ import annotations

import pytest

from faultray.model.components import (
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
from faultray.model.graph import InfraGraph
from faultray.simulator.compliance_engine import ComplianceCheck, ComplianceEngine, ComplianceReport


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

    def test_has_redundancy_with_type_filter(self):
        """_has_redundancy should filter by component type when specified."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER,
            replicas=3,
        ))
        graph.add_component(Component(
            id="db", name="db", type=ComponentType.DATABASE,
            replicas=1,
        ))
        engine = ComplianceEngine(graph)
        # DB type with replicas=1 should fail redundancy check
        assert engine._has_redundancy([ComponentType.DATABASE]) is False
        # APP type with replicas=3 should pass
        assert engine._has_redundancy([ComponentType.APP_SERVER]) is True
        # No filter should pass (app has replicas >= 2)
        assert engine._has_redundancy() is True

    def test_has_redundancy_all_single_replica(self):
        """_has_redundancy should return False when all components have replicas < 2."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, replicas=1,
        ))
        engine = ComplianceEngine(graph)
        assert engine._has_redundancy() is False

    def test_dr_region_by_non_primary(self):
        """DR region detection via non-primary region config."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db-dr", name="DB DR",
            type=ComponentType.DATABASE, replicas=2,
            region=RegionConfig(region="us-west-2", is_primary=False),
        ))
        engine = ComplianceEngine(graph)
        assert engine._has_dr_region() is True

    def test_soc2_pi13_partial_circuit_breakers(self):
        """PI1.3 should be 'partial' when some but not all edges have CB."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="db", name="db", type=ComponentType.DATABASE, replicas=2,
        ))
        graph.add_component(Component(
            id="cache", name="cache", type=ComponentType.CACHE, replicas=2,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="cache", dependency_type="optional",
            circuit_breaker=CircuitBreakerConfig(enabled=False),
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_soc2()
        pi13 = [c for c in report.checks if c.control_id == "PI1.3"]
        assert pi13[0].status == "partial"

    def test_soc2_a12_availability_partial(self):
        """A1.2 should be 'partial' when only failover OR redundancy exists."""
        graph = InfraGraph()
        # No redundancy but has failover on db
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, replicas=1,
        ))
        graph.add_component(Component(
            id="db", name="db", type=ComponentType.DATABASE, replicas=1,
            failover=FailoverConfig(enabled=True, promotion_time_seconds=10),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_soc2()
        a12 = [c for c in report.checks if c.control_id == "A1.2"]
        assert a12[0].status == "partial"

    def test_iso27001_a1712_partial_redundancy(self):
        """A.17.1.2 should be 'partial' when some components lack redundancy."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="db", name="db", type=ComponentType.DATABASE, replicas=1,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_iso27001()
        a1712 = [c for c in report.checks if c.control_id == "A.17.1.2"]
        # 1 of 2 components lacks redundancy (50%), so should be partial
        assert a1712[0].status == "partial"

    def test_iso27001_encryption_partial(self):
        """A.10.1.1 should be 'partial' when some but not all have encryption."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="lb", name="lb", type=ComponentType.LOAD_BALANCER, port=443, replicas=2,
        ))
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, port=80, replicas=1,
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_iso27001()
        a1011 = [c for c in report.checks if c.control_id == "A.10.1.1"]
        assert a1011[0].status == "partial"

    def test_pci_dss_req61_partial(self):
        """Req-6.1 should be 'partial' when only monitoring OR cb exists."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, replicas=1,
        ))
        graph.add_component(Component(
            id="db", name="db", type=ComponentType.DATABASE, replicas=1,
        ))
        # No monitoring, but circuit breakers
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_pci_dss()
        req61 = [c for c in report.checks if c.control_id == "Req-6.1"]
        assert req61[0].status == "partial"

    def test_pci_dss_req62_partial(self):
        """Req-6.2 should be 'partial' when only auth OR encryption exists."""
        graph = InfraGraph()
        # Has auth (via name) but no encryption (port != 443)
        graph.add_component(Component(
            id="auth-svc", name="auth service", type=ComponentType.APP_SERVER,
            port=8080, replicas=1,
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_pci_dss()
        req62 = [c for c in report.checks if c.control_id == "Req-6.2"]
        assert req62[0].status == "partial"

    def test_pci_dss_pci_scope_components(self):
        """PCI-scope checks (Req-3.4, Req-1.3) should be generated for PCI-tagged components."""
        from faultray.model.components import ComplianceTags, SecurityProfile
        graph = InfraGraph()
        graph.add_component(Component(
            id="payment-db", name="Payment DB", type=ComponentType.DATABASE,
            replicas=2,
            compliance_tags=ComplianceTags(pci_scope=True),
            security=SecurityProfile(encryption_at_rest=True, network_segmented=True),
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_pci_dss()
        req34 = [c for c in report.checks if c.control_id == "Req-3.4"]
        req13 = [c for c in report.checks if c.control_id == "Req-1.3"]
        assert len(req34) == 1
        assert req34[0].status == "pass"
        assert len(req13) == 1
        assert req13[0].status == "pass"

    def test_pci_dss_pci_scope_fail(self):
        """PCI-scope checks should fail when components lack encryption/segmentation."""
        from faultray.model.components import ComplianceTags, SecurityProfile
        graph = InfraGraph()
        graph.add_component(Component(
            id="payment-db", name="Payment DB", type=ComponentType.DATABASE,
            replicas=2,
            compliance_tags=ComplianceTags(pci_scope=True),
            security=SecurityProfile(encryption_at_rest=False, network_segmented=False),
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_pci_dss()
        req34 = [c for c in report.checks if c.control_id == "Req-3.4"]
        req13 = [c for c in report.checks if c.control_id == "Req-1.3"]
        assert req34[0].status == "fail"
        assert req13[0].status == "fail"

    def test_nist_csf_prds2_partial(self):
        """PR.DS-2 should be 'partial' when some have encryption and some don't."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="lb", name="lb", type=ComponentType.LOAD_BALANCER, port=443, replicas=2,
        ))
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, port=80, replicas=1,
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_nist_csf()
        prds2 = [c for c in report.checks if c.control_id == "PR.DS-2"]
        assert prds2[0].status == "partial"

    def test_nist_csf_rsmi1_partial(self):
        """RS.MI-1 should be 'partial' when some edges have circuit breakers."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="db", name="db", type=ComponentType.DATABASE, replicas=2,
        ))
        graph.add_component(Component(
            id="cache", name="cache", type=ComponentType.CACHE, replicas=2,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="cache", dependency_type="optional",
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_nist_csf()
        rsmi1 = [c for c in report.checks if c.control_id == "RS.MI-1"]
        assert rsmi1[0].status == "partial"

    def test_nist_csf_recovery_partial(self):
        """RC.RP-1 should be 'partial' when only 1 of failover/autoscaling/DR exists."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="db", type=ComponentType.DATABASE,
            replicas=2,
            failover=FailoverConfig(enabled=True, promotion_time_seconds=10),
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_nist_csf()
        rcrp1 = [c for c in report.checks if c.control_id == "RC.RP-1"]
        assert rcrp1[0].status == "partial"

    def test_nist_csf_rcim1_partial(self):
        """RC.IM-1 should be 'partial' when only redundancy or failover (not both)."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="db", type=ComponentType.DATABASE,
            replicas=2,  # has redundancy
            # no failover
        ))
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER,
            replicas=2,
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_nist_csf()
        rcim1 = [c for c in report.checks if c.control_id == "RC.IM-1"]
        # no components without redundancy, but no failover -> partial
        assert rcim1[0].status == "partial"

    def test_nist_csf_pii_components(self):
        """PR.DS-1 check should appear for PII-tagged components."""
        from faultray.model.components import ComplianceTags, SecurityProfile
        graph = InfraGraph()
        graph.add_component(Component(
            id="user-db", name="User DB", type=ComponentType.DATABASE,
            replicas=2,
            compliance_tags=ComplianceTags(contains_pii=True),
            security=SecurityProfile(encryption_at_rest=True, encryption_in_transit=True),
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_nist_csf()
        prds1 = [c for c in report.checks if c.control_id == "PR.DS-1"]
        assert len(prds1) == 1
        assert prds1[0].status == "pass"

    def test_nist_csf_pii_partial_encryption(self):
        """PR.DS-1 should be 'partial' when PII component has only rest OR transit encryption."""
        from faultray.model.components import ComplianceTags, SecurityProfile
        graph = InfraGraph()
        graph.add_component(Component(
            id="user-db", name="User DB", type=ComponentType.DATABASE,
            replicas=2,
            compliance_tags=ComplianceTags(contains_pii=True),
            security=SecurityProfile(encryption_at_rest=True, encryption_in_transit=False),
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_nist_csf()
        prds1 = [c for c in report.checks if c.control_id == "PR.DS-1"]
        assert prds1[0].status == "partial"

    def test_nist_csf_pii_no_encryption(self):
        """PR.DS-1 should be 'fail' when PII has no encryption at all."""
        from faultray.model.components import ComplianceTags, SecurityProfile
        graph = InfraGraph()
        graph.add_component(Component(
            id="user-db", name="User DB", type=ComponentType.DATABASE,
            replicas=2,
            compliance_tags=ComplianceTags(contains_pii=True),
            security=SecurityProfile(encryption_at_rest=False, encryption_in_transit=False),
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_nist_csf()
        prds1 = [c for c in report.checks if c.control_id == "PR.DS-1"]
        assert prds1[0].status == "fail"

    def test_nist_csf_audit_logging_tags(self):
        """DE.AE-3 should be generated and pass when monitoring + audit tags exist."""
        from faultray.model.components import ComplianceTags
        graph = InfraGraph()
        graph.add_component(Component(
            id="otel", name="otel-collector", type=ComponentType.CUSTOM, replicas=2,
        ))
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, replicas=2,
            compliance_tags=ComplianceTags(audit_logging=True),
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_nist_csf()
        deae3 = [c for c in report.checks if c.control_id == "DE.AE-3"]
        assert len(deae3) == 1
        assert deae3[0].status == "pass"

    def test_nist_csf_audit_logging_partial(self):
        """DE.AE-3 should be 'partial' when monitoring but no audit tags (or vice versa)."""
        from faultray.model.components import ComplianceTags
        graph = InfraGraph()
        # Has monitoring (otel) but no audit_logging tags
        graph.add_component(Component(
            id="otel", name="otel-collector", type=ComponentType.CUSTOM, replicas=2,
        ))
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, replicas=2,
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_nist_csf()
        deae3 = [c for c in report.checks if c.control_id == "DE.AE-3"]
        assert len(deae3) == 1
        assert deae3[0].status == "partial"

    def test_nist_csf_audit_logging_fail(self):
        """DE.AE-3 should be 'fail' when no monitoring and no audit tags."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, replicas=2,
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_nist_csf()
        deae3 = [c for c in report.checks if c.control_id == "DE.AE-3"]
        assert len(deae3) == 1
        assert deae3[0].status == "fail"

    def test_has_pci_scope(self):
        """_has_pci_scope should detect PCI-tagged components."""
        from faultray.model.components import ComplianceTags
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER,
            compliance_tags=ComplianceTags(pci_scope=True),
        ))
        engine = ComplianceEngine(graph)
        assert engine._has_pci_scope() is True

    def test_has_pii_data(self):
        """_has_pii_data should detect PII-tagged components."""
        from faultray.model.components import ComplianceTags
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="db", type=ComponentType.DATABASE,
            compliance_tags=ComplianceTags(contains_pii=True),
        ))
        engine = ComplianceEngine(graph)
        assert engine._has_pii_data() is True

    def test_has_audit_logging_tags(self):
        """_has_audit_logging_tags should detect audit_logging tags."""
        from faultray.model.components import ComplianceTags
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER,
            compliance_tags=ComplianceTags(audit_logging=True),
        ))
        engine = ComplianceEngine(graph)
        assert engine._has_audit_logging_tags() is True

    def test_iso27001_a1711_partial_failover_only(self):
        """A.17.1.1 should be 'partial' when only failover but no DR region."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="db", type=ComponentType.DATABASE,
            replicas=2,
            failover=FailoverConfig(enabled=True, promotion_time_seconds=10),
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_iso27001()
        a1711 = [c for c in report.checks if c.control_id == "A.17.1.1"]
        assert a1711[0].status == "partial"

    def test_pci_dss_req105_partial(self):
        """Req-10.5 should be 'partial' when TLS exists but some non-encrypted."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="lb", name="lb", type=ComponentType.LOAD_BALANCER, port=443, replicas=2,
        ))
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, port=80, replicas=1,
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_pci_dss()
        req105 = [c for c in report.checks if c.control_id == "Req-10.5"]
        assert req105[0].status == "partial"

    def test_pci_dss_req65_partial(self):
        """Req-6.5 should be 'partial' when some edges have CB."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="db", name="db", type=ComponentType.DATABASE, replicas=2,
        ))
        graph.add_component(Component(
            id="cache", name="cache", type=ComponentType.CACHE, replicas=2,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="cache", dependency_type="optional",
        ))
        engine = ComplianceEngine(graph)
        report = engine.check_pci_dss()
        req65 = [c for c in report.checks if c.control_id == "Req-6.5"]
        assert req65[0].status == "partial"
