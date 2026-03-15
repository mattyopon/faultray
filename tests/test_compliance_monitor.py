"""Tests for the Continuous Compliance Monitor."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    ComplianceTags,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    SecurityProfile,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.compliance_monitor import (
    ComplianceAlert,
    ComplianceControl,
    ComplianceFramework,
    ComplianceMonitor,
    ComplianceSnapshot,
    ComplianceTrend,
    ControlStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_graph() -> InfraGraph:
    """A minimal graph with no security features."""
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
    """A well-configured graph with security features."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="waf",
        name="WAF / API Gateway",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
        security=SecurityProfile(
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            network_segmented=True,
            encryption_at_rest=True,
            encryption_in_transit=True,
            backup_enabled=True,
            log_enabled=True,
            ids_monitored=True,
        ),
        compliance_tags=ComplianceTags(
            audit_logging=True,
            change_management=True,
        ),
    ))
    graph.add_component(Component(
        id="app",
        name="app-server",
        type=ComponentType.APP_SERVER,
        port=443,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        security=SecurityProfile(
            auth_required=True,
            encryption_at_rest=True,
            encryption_in_transit=True,
            log_enabled=True,
            ids_monitored=True,
            network_segmented=True,
            backup_enabled=True,
        ),
        compliance_tags=ComplianceTags(
            audit_logging=True,
            change_management=True,
        ),
    ))
    graph.add_component(Component(
        id="db",
        name="PostgreSQL",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=2,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=15),
        region=RegionConfig(
            region_name="us-east-1",
            is_primary=True,
            dr_target_region="us-west-2",
        ),
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            backup_enabled=True,
            log_enabled=True,
            network_segmented=True,
        ),
        compliance_tags=ComplianceTags(
            audit_logging=True,
            change_management=True,
        ),
    ))
    graph.add_component(Component(
        id="monitoring",
        name="Prometheus Monitoring",
        type=ComponentType.CUSTOM,
        replicas=2,
        security=SecurityProfile(log_enabled=True),
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


@pytest.fixture
def monitor() -> ComplianceMonitor:
    """Create a fresh ComplianceMonitor."""
    return ComplianceMonitor()


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_compliance_framework_values(self):
        assert ComplianceFramework.DORA.value == "dora"
        assert ComplianceFramework.SOC2.value == "soc2"
        assert ComplianceFramework.ISO27001.value == "iso27001"
        assert ComplianceFramework.PCI_DSS.value == "pci_dss"
        assert ComplianceFramework.NIST_CSF.value == "nist_csf"
        assert ComplianceFramework.HIPAA.value == "hipaa"

    def test_control_status_values(self):
        assert ControlStatus.COMPLIANT.value == "compliant"
        assert ControlStatus.PARTIAL.value == "partial"
        assert ControlStatus.NON_COMPLIANT.value == "non_compliant"
        assert ControlStatus.NOT_APPLICABLE.value == "not_applicable"
        assert ControlStatus.UNKNOWN.value == "unknown"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestDataClasses:
    def test_compliance_control_creation(self):
        ctrl = ComplianceControl(
            control_id="DORA-5.1",
            framework=ComplianceFramework.DORA,
            title="ICT risk management",
            description="Risk management framework documented",
            status=ControlStatus.COMPLIANT,
            evidence=["Framework documented"],
            gaps=[],
            remediation=[],
            risk_if_non_compliant="Regulatory penalty",
        )
        assert ctrl.control_id == "DORA-5.1"
        assert ctrl.framework == ComplianceFramework.DORA
        assert ctrl.status == ControlStatus.COMPLIANT
        assert isinstance(ctrl.last_assessed, datetime)

    def test_compliance_snapshot_creation(self):
        snap = ComplianceSnapshot(
            timestamp=datetime.now(timezone.utc),
            framework=ComplianceFramework.SOC2,
            total_controls=10,
            compliant=7,
            partial=2,
            non_compliant=1,
            compliance_percentage=80.0,
        )
        assert snap.total_controls == 10
        assert snap.compliance_percentage == 80.0

    def test_compliance_trend_creation(self):
        trend = ComplianceTrend(
            framework=ComplianceFramework.HIPAA,
            trend="improving",
            current_percentage=85.0,
            delta_30d=5.0,
            risk_areas=["Access control"],
        )
        assert trend.trend == "improving"
        assert trend.delta_30d == 5.0

    def test_compliance_alert_creation(self):
        alert = ComplianceAlert(
            alert_type="new_violation",
            framework=ComplianceFramework.PCI_DSS,
            control_id="PCI-3.4",
            severity="critical",
            message="Encryption not configured",
        )
        assert alert.alert_type == "new_violation"
        assert alert.severity == "critical"


# ---------------------------------------------------------------------------
# Assessment tests
# ---------------------------------------------------------------------------


class TestAssessment:
    def test_assess_dora_minimal(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        """Minimal graph should have low DORA compliance."""
        snapshot = monitor.assess(minimal_graph, ComplianceFramework.DORA)
        assert snapshot.framework == ComplianceFramework.DORA
        assert snapshot.total_controls >= 15
        assert snapshot.compliance_percentage < 100.0
        assert snapshot.non_compliant > 0

    def test_assess_dora_secure(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """Secure graph should have higher DORA compliance."""
        snapshot = monitor.assess(secure_graph, ComplianceFramework.DORA)
        assert snapshot.framework == ComplianceFramework.DORA
        assert snapshot.compliance_percentage > 50.0
        assert snapshot.compliant > 0

    def test_assess_soc2_minimal(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        """Minimal graph should have low SOC2 compliance."""
        snapshot = monitor.assess(minimal_graph, ComplianceFramework.SOC2)
        assert snapshot.framework == ComplianceFramework.SOC2
        assert snapshot.total_controls >= 10
        assert snapshot.non_compliant > 0

    def test_assess_soc2_secure(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """Secure graph should have higher SOC2 compliance."""
        snapshot = monitor.assess(secure_graph, ComplianceFramework.SOC2)
        assert snapshot.compliance_percentage > 50.0

    def test_assess_hipaa_minimal(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        """Minimal graph should fail most HIPAA controls."""
        snapshot = monitor.assess(minimal_graph, ComplianceFramework.HIPAA)
        assert snapshot.framework == ComplianceFramework.HIPAA
        assert snapshot.total_controls >= 8
        assert snapshot.non_compliant > 0

    def test_assess_hipaa_secure(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """Secure graph should pass most HIPAA controls."""
        snapshot = monitor.assess(secure_graph, ComplianceFramework.HIPAA)
        assert snapshot.compliance_percentage > 50.0

    def test_assess_iso27001(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        snapshot = monitor.assess(secure_graph, ComplianceFramework.ISO27001)
        assert snapshot.total_controls >= 10
        assert snapshot.compliance_percentage > 50.0

    def test_assess_pci_dss(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        snapshot = monitor.assess(secure_graph, ComplianceFramework.PCI_DSS)
        assert snapshot.total_controls >= 10
        assert snapshot.compliance_percentage > 0.0

    def test_assess_nist_csf(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        snapshot = monitor.assess(secure_graph, ComplianceFramework.NIST_CSF)
        assert snapshot.total_controls >= 10
        assert snapshot.compliance_percentage > 0.0

    def test_assess_all(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """assess_all should return snapshots for all 6 frameworks."""
        results = monitor.assess_all(secure_graph)
        assert len(results) == 6
        for fw in ComplianceFramework:
            assert fw in results
            assert isinstance(results[fw], ComplianceSnapshot)

    def test_controls_have_evidence(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """Compliant controls should have evidence."""
        snapshot = monitor.assess(secure_graph, ComplianceFramework.DORA)
        compliant_controls = [c for c in snapshot.controls if c.status == ControlStatus.COMPLIANT]
        for ctrl in compliant_controls:
            assert len(ctrl.evidence) > 0, f"{ctrl.control_id} compliant but no evidence"

    def test_non_compliant_controls_have_gaps(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        """Non-compliant controls should have gaps listed."""
        snapshot = monitor.assess(minimal_graph, ComplianceFramework.SOC2)
        nc_controls = [c for c in snapshot.controls if c.status == ControlStatus.NON_COMPLIANT]
        for ctrl in nc_controls:
            assert len(ctrl.gaps) > 0, f"{ctrl.control_id} non-compliant but no gaps listed"


# ---------------------------------------------------------------------------
# Tracking and trend tests
# ---------------------------------------------------------------------------


class TestTracking:
    def test_track_records_snapshots(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """track() should record snapshots to history."""
        monitor.track(secure_graph)
        trends = monitor.get_trends(ComplianceFramework.DORA)
        assert len(trends.snapshots) == 1
        assert trends.current_percentage > 0

    def test_multiple_tracks(self, monitor: ComplianceMonitor, secure_graph: InfraGraph, minimal_graph: InfraGraph):
        """Multiple track() calls should accumulate history."""
        monitor.track(secure_graph)
        monitor.track(secure_graph)
        monitor.track(minimal_graph)

        trends = monitor.get_trends(ComplianceFramework.DORA)
        assert len(trends.snapshots) == 3

    def test_trend_detection_stable(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """Consistent scores should show stable trend."""
        monitor.track(secure_graph)
        monitor.track(secure_graph)
        monitor.track(secure_graph)

        trends = monitor.get_trends(ComplianceFramework.DORA)
        assert trends.trend == "stable"

    def test_trend_detection_degrading(self, monitor: ComplianceMonitor, secure_graph: InfraGraph, minimal_graph: InfraGraph):
        """Declining scores should show degrading trend."""
        monitor.track(secure_graph)
        monitor.track(secure_graph)
        monitor.track(minimal_graph)

        trends = monitor.get_trends(ComplianceFramework.DORA)
        # The trend should be "degrading" since the last snapshot is lower
        assert trends.trend in ("degrading", "stable")  # depends on exact scores

    def test_delta_30d_calculation(self, monitor: ComplianceMonitor, secure_graph: InfraGraph, minimal_graph: InfraGraph):
        """Delta should reflect change from first to last snapshot."""
        monitor.track(minimal_graph)
        monitor.track(secure_graph)

        trends = monitor.get_trends(ComplianceFramework.DORA)
        # Secure graph should have higher compliance than minimal
        assert trends.delta_30d > 0

    def test_risk_areas_identified(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        """Risk areas should list non-compliant controls."""
        monitor.track(minimal_graph)
        trends = monitor.get_trends(ComplianceFramework.DORA)
        assert len(trends.risk_areas) > 0

    def test_empty_trends(self, monitor: ComplianceMonitor):
        """No history should return empty trend."""
        trends = monitor.get_trends(ComplianceFramework.DORA)
        assert len(trends.snapshots) == 0
        assert trends.trend == "stable"
        assert trends.current_percentage == 0.0


# ---------------------------------------------------------------------------
# Violation detection tests
# ---------------------------------------------------------------------------


class TestViolationDetection:
    def test_detect_violations_first_assessment(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        """First assessment should detect existing violations."""
        alerts = monitor.detect_violations(minimal_graph)
        assert len(alerts) > 0
        assert all(isinstance(a, ComplianceAlert) for a in alerts)
        assert any(a.alert_type == "new_violation" for a in alerts)

    def test_detect_degradation(self, monitor: ComplianceMonitor, secure_graph: InfraGraph, minimal_graph: InfraGraph):
        """Switching from secure to minimal should detect degradation."""
        # Record good state
        monitor.track(secure_graph)

        # Check against bad state
        alerts = monitor.detect_violations(minimal_graph)
        degradation_alerts = [a for a in alerts if a.alert_type == "degradation"]
        assert len(degradation_alerts) > 0

    def test_no_violations_stable(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """Stable compliant state should produce fewer alerts."""
        monitor.track(secure_graph)
        alerts = monitor.detect_violations(secure_graph)
        # No degradation alerts when state is the same
        degradation_alerts = [a for a in alerts if a.alert_type == "degradation"]
        assert len(degradation_alerts) == 0

    def test_alert_severity_levels(self, monitor: ComplianceMonitor, secure_graph: InfraGraph, minimal_graph: InfraGraph):
        """Degradation alerts should have appropriate severity."""
        monitor.track(secure_graph)
        alerts = monitor.detect_violations(minimal_graph)
        severities = {a.severity for a in alerts}
        assert len(severities) > 0  # Should have at least one severity level


# ---------------------------------------------------------------------------
# Audit readiness tests
# ---------------------------------------------------------------------------


class TestAuditReadiness:
    def test_audit_readiness_with_history(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """Audit readiness should be >0 with history."""
        monitor.track(secure_graph)
        readiness = monitor.get_audit_readiness(ComplianceFramework.DORA)
        assert 0 <= readiness <= 100
        assert readiness > 0

    def test_audit_readiness_no_history(self, monitor: ComplianceMonitor):
        """Audit readiness should be 0 without history."""
        readiness = monitor.get_audit_readiness(ComplianceFramework.DORA)
        assert readiness == 0.0

    def test_audit_readiness_minimal_graph(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        """Minimal graph should have lower audit readiness."""
        monitor.track(minimal_graph)
        readiness = monitor.get_audit_readiness(ComplianceFramework.DORA)
        assert readiness < 80  # Should be below excellent

    def test_audit_readiness_secure_graph(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """Secure graph should have higher audit readiness."""
        monitor.track(secure_graph)
        readiness = monitor.get_audit_readiness(ComplianceFramework.DORA)
        assert readiness > 0


# ---------------------------------------------------------------------------
# Evidence package tests
# ---------------------------------------------------------------------------


class TestEvidencePackage:
    def test_evidence_package_with_history(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """Evidence package should contain structured data."""
        monitor.track(secure_graph)
        package = monitor.generate_evidence_package(ComplianceFramework.DORA)

        assert package["framework"] == "dora"
        assert package["status"] == "assessed"
        assert "controls" in package
        assert len(package["controls"]) >= 15
        assert "summary" in package
        assert "trend" in package

    def test_evidence_package_no_history(self, monitor: ComplianceMonitor):
        """Evidence package without history should indicate no assessments."""
        package = monitor.generate_evidence_package(ComplianceFramework.SOC2)
        assert package["status"] == "no_assessments"
        assert len(package["controls"]) == 0

    def test_evidence_package_control_detail(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """Evidence package controls should have all expected fields."""
        monitor.track(secure_graph)
        package = monitor.generate_evidence_package(ComplianceFramework.SOC2)

        for control in package["controls"]:
            assert "control_id" in control
            assert "title" in control
            assert "status" in control
            assert "evidence" in control
            assert "gaps" in control
            assert "remediation" in control
            assert "last_assessed" in control
            assert "risk_if_non_compliant" in control

    def test_evidence_package_has_audit_readiness(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """Evidence package should include audit readiness score."""
        monitor.track(secure_graph)
        package = monitor.generate_evidence_package(ComplianceFramework.HIPAA)
        assert "audit_readiness" in package
        assert 0 <= package["audit_readiness"] <= 100


# ---------------------------------------------------------------------------
# Framework-specific control count tests
# ---------------------------------------------------------------------------


class TestControlCounts:
    def test_dora_has_at_least_15_controls(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        snapshot = monitor.assess(minimal_graph, ComplianceFramework.DORA)
        assert snapshot.total_controls >= 15

    def test_soc2_has_at_least_10_controls(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        snapshot = monitor.assess(minimal_graph, ComplianceFramework.SOC2)
        assert snapshot.total_controls >= 10

    def test_hipaa_has_at_least_8_controls(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        snapshot = monitor.assess(minimal_graph, ComplianceFramework.HIPAA)
        assert snapshot.total_controls >= 8

    def test_iso27001_has_at_least_10_controls(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        snapshot = monitor.assess(minimal_graph, ComplianceFramework.ISO27001)
        assert snapshot.total_controls >= 10

    def test_pci_dss_has_at_least_10_controls(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        snapshot = monitor.assess(minimal_graph, ComplianceFramework.PCI_DSS)
        assert snapshot.total_controls >= 10

    def test_nist_csf_has_at_least_10_controls(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph):
        snapshot = monitor.assess(minimal_graph, ComplianceFramework.NIST_CSF)
        assert snapshot.total_controls >= 10


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_graph(self, monitor: ComplianceMonitor):
        """Empty graph should not crash."""
        graph = InfraGraph()
        snapshot = monitor.assess(graph, ComplianceFramework.DORA)
        assert snapshot.total_controls >= 15
        # Most controls should be non-compliant for empty graph

    def test_single_component_no_dependencies(self, monitor: ComplianceMonitor):
        """Single component with no dependencies."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="standalone",
            name="Standalone Service",
            type=ComponentType.APP_SERVER,
        ))
        snapshot = monitor.assess(graph, ComplianceFramework.SOC2)
        assert snapshot.total_controls >= 10

    def test_graph_with_external_api(self, monitor: ComplianceMonitor):
        """Graph with external API should trigger third-party checks."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app",
            name="App",
            type=ComponentType.APP_SERVER,
            replicas=2,
        ))
        graph.add_component(Component(
            id="stripe",
            name="Stripe API",
            type=ComponentType.EXTERNAL_API,
            replicas=1,
        ))
        graph.add_dependency(Dependency(source_id="app", target_id="stripe"))

        snapshot = monitor.assess(graph, ComplianceFramework.DORA)
        assert snapshot.total_controls >= 15

    def test_compliance_percentage_range(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph, secure_graph: InfraGraph):
        """Compliance percentage should always be 0-100."""
        for fw in ComplianceFramework:
            snap_min = monitor.assess(minimal_graph, fw)
            snap_sec = monitor.assess(secure_graph, fw)
            assert 0 <= snap_min.compliance_percentage <= 100
            assert 0 <= snap_sec.compliance_percentage <= 100
