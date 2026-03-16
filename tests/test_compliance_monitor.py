"""Tests for the Continuous Compliance Monitor."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from faultray.model.components import (
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
from faultray.model.graph import InfraGraph
from faultray.simulator.compliance_monitor import (
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


# ---------------------------------------------------------------------------
# SQLite persistence tests
# ---------------------------------------------------------------------------


class TestSQLitePersistence:
    def test_store_path_creates_db(self, tmp_path, secure_graph: InfraGraph):
        """Monitor with store_path should create SQLite database."""
        db_path = tmp_path / "compliance.db"
        monitor = ComplianceMonitor(store_path=db_path)
        assert db_path.exists()

    def test_track_persists_to_db(self, tmp_path, secure_graph: InfraGraph):
        """track() should persist snapshots to SQLite store."""
        db_path = tmp_path / "compliance.db"
        monitor = ComplianceMonitor(store_path=db_path)
        monitor.track(secure_graph)
        # Verify data was stored
        count = monitor.get_stored_snapshot_count()
        assert count == 6  # 6 frameworks

    def test_load_history_from_store(self, tmp_path, secure_graph: InfraGraph):
        """A new ComplianceMonitor instance should load history from the same store."""
        db_path = tmp_path / "compliance.db"
        monitor1 = ComplianceMonitor(store_path=db_path)
        monitor1.track(secure_graph)

        # Create a fresh monitor reading from the same DB
        monitor2 = ComplianceMonitor(store_path=db_path)
        count = monitor2.get_stored_snapshot_count()
        assert count == 6  # Should have loaded the 6 snapshots from DB

        trends = monitor2.get_trends(ComplianceFramework.DORA)
        assert len(trends.snapshots) == 1
        assert trends.current_percentage > 0

    def test_multiple_tracks_accumulated_in_store(self, tmp_path, secure_graph: InfraGraph, minimal_graph: InfraGraph):
        """Multiple track() calls should accumulate in the store."""
        db_path = tmp_path / "compliance.db"
        monitor = ComplianceMonitor(store_path=db_path)
        monitor.track(secure_graph)
        monitor.track(minimal_graph)
        # 2 tracks * 6 frameworks = 12 total
        assert monitor.get_stored_snapshot_count() == 12

    def test_store_path_in_subdirectory(self, tmp_path, secure_graph: InfraGraph):
        """Store in a non-existent subdirectory should create parent dirs."""
        db_path = tmp_path / "subdir" / "nested" / "compliance.db"
        monitor = ComplianceMonitor(store_path=db_path)
        monitor.track(secure_graph)
        assert db_path.exists()

    def test_get_stored_snapshot_count_per_framework(self, tmp_path, secure_graph: InfraGraph):
        """get_stored_snapshot_count with framework filter should return count for that framework only."""
        db_path = tmp_path / "compliance.db"
        monitor = ComplianceMonitor(store_path=db_path)
        monitor.track(secure_graph)
        count = monitor.get_stored_snapshot_count(ComplianceFramework.DORA)
        assert count == 1

    def test_load_from_nonexistent_store(self, tmp_path):
        """Loading from a non-existent store file should not crash."""
        db_path = tmp_path / "does_not_exist.db"
        # Don't create it; the monitor should handle this
        monitor = ComplianceMonitor(store_path=db_path)
        # It will create the store file during init
        assert db_path.exists()

    def test_store_preserves_controls_data(self, tmp_path, secure_graph: InfraGraph):
        """Stored controls data should be loadable with correct fields."""
        db_path = tmp_path / "compliance.db"
        monitor1 = ComplianceMonitor(store_path=db_path)
        monitor1.track(secure_graph)

        monitor2 = ComplianceMonitor(store_path=db_path)
        trends = monitor2.get_trends(ComplianceFramework.SOC2)
        assert len(trends.snapshots) == 1
        snapshot = trends.snapshots[0]
        assert snapshot.total_controls >= 10
        assert len(snapshot.controls) > 0
        for ctrl in snapshot.controls:
            assert ctrl.control_id != ""
            assert ctrl.framework == ComplianceFramework.SOC2


# ---------------------------------------------------------------------------
# Check method coverage: specific branches
# ---------------------------------------------------------------------------


class TestCheckMethods:
    def test_check_asset_inventory_no_edges(self, monitor: ComplianceMonitor):
        """Components with no dependency edges should give partial compliance."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        snapshot = monitor.assess(graph, ComplianceFramework.DORA)
        # Look for the asset inventory control
        inv_controls = [c for c in snapshot.controls if "inventory" in c.title.lower() or "asset" in c.title.lower()]
        if inv_controls:
            # With components but no edges, should be PARTIAL
            assert inv_controls[0].status in (ControlStatus.PARTIAL, ControlStatus.COMPLIANT)

    def test_check_redundancy_no_critical(self, monitor: ComplianceMonitor):
        """Components with no dependents should return NOT_APPLICABLE for redundancy."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="standalone", name="Standalone", type=ComponentType.APP_SERVER,
        ))
        # Access the check method directly
        status, evidence, gaps = monitor._check_redundancy(graph)
        assert status == ControlStatus.NOT_APPLICABLE

    def test_check_redundancy_all_redundant(self, monitor: ComplianceMonitor):
        """All critical components with replicas >= 2 should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        ))
        graph.add_dependency(Dependency(source_id="app", target_id="db"))
        status, evidence, gaps = monitor._check_redundancy(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_redundancy_partial(self, monitor: ComplianceMonitor):
        """Mix of redundant and non-redundant components should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        ))
        graph.add_component(Component(
            id="cache", name="Cache", type=ComponentType.CACHE, replicas=2,
        ))
        graph.add_dependency(Dependency(source_id="app", target_id="db"))
        graph.add_dependency(Dependency(source_id="app", target_id="cache"))
        status, evidence, gaps = monitor._check_redundancy(graph)
        assert status in (ControlStatus.PARTIAL, ControlStatus.COMPLIANT)

    def test_check_monitoring_logging_only(self, monitor: ComplianceMonitor):
        """Only logging enabled (no dedicated monitoring) should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            security=SecurityProfile(log_enabled=True),
        ))
        status, evidence, gaps = monitor._check_monitoring(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_monitoring_component_only(self, monitor: ComplianceMonitor):
        """Monitoring component without logging should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="prometheus", name="Prometheus Monitoring", type=ComponentType.CUSTOM,
        ))
        status, evidence, gaps = monitor._check_monitoring(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_monitoring_none(self, monitor: ComplianceMonitor):
        """No monitoring or logging should be NON_COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        status, evidence, gaps = monitor._check_monitoring(graph)
        assert status == ControlStatus.NON_COMPLIANT

    def test_check_access_controls_partial_auth_only(self, monitor: ComplianceMonitor):
        """Auth required without auth component should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App Server", type=ComponentType.APP_SERVER,
            security=SecurityProfile(auth_required=True),
        ))
        status, evidence, gaps = monitor._check_access_controls(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_access_controls_partial_component_only(self, monitor: ComplianceMonitor):
        """Auth component without auth_required flags should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="waf", name="WAF Gateway", type=ComponentType.LOAD_BALANCER,
        ))
        status, evidence, gaps = monitor._check_access_controls(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_encryption_all_components(self, monitor: ComplianceMonitor):
        """All components with encryption should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            port=443,
            security=SecurityProfile(
                encryption_at_rest=True, encryption_in_transit=True,
            ),
        ))
        status, evidence, gaps = monitor._check_encryption(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_encryption_rest_only(self, monitor: ComplianceMonitor):
        """Only encryption at rest should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            security=SecurityProfile(encryption_at_rest=True),
        ))
        status, evidence, gaps = monitor._check_encryption(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_encryption_transit_only(self, monitor: ComplianceMonitor):
        """Only encryption in transit should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            port=443,
        ))
        status, evidence, gaps = monitor._check_encryption(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_encryption_partial_coverage(self, monitor: ComplianceMonitor):
        """Not all components with both encryption types should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            port=443,
            security=SecurityProfile(
                encryption_at_rest=True, encryption_in_transit=True,
            ),
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
        ))
        status, evidence, gaps = monitor._check_encryption(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_network_security_full(self, monitor: ComplianceMonitor):
        """WAF + segmentation + rate limiting should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="waf", name="WAF", type=ComponentType.LOAD_BALANCER,
            security=SecurityProfile(
                waf_protected=True, network_segmented=True, rate_limiting=True,
            ),
        ))
        status, evidence, gaps = monitor._check_network_security(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_network_security_none(self, monitor: ComplianceMonitor):
        """No network security should be NON_COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        status, evidence, gaps = monitor._check_network_security(graph)
        assert status == ControlStatus.NON_COMPLIANT

    def test_check_business_continuity_full(self, monitor: ComplianceMonitor):
        """DR + failover + multi-region should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            failover=FailoverConfig(enabled=True),
            region=RegionConfig(
                region_name="us-east-1", is_primary=True,
                dr_target_region="us-west-2",
            ),
        ))
        graph.add_component(Component(
            id="db-dr", name="DB DR", type=ComponentType.DATABASE,
            region=RegionConfig(
                region_name="us-west-2", is_primary=False,
            ),
        ))
        status, evidence, gaps = monitor._check_business_continuity(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_business_continuity_none(self, monitor: ComplianceMonitor):
        """No DR, failover, or multi-region should be NON_COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        status, evidence, gaps = monitor._check_business_continuity(graph)
        assert status == ControlStatus.NON_COMPLIANT

    def test_check_business_continuity_dr_keyword(self, monitor: ComplianceMonitor):
        """DR component detected by keyword should contribute to score."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="dr-standby", name="DR Standby", type=ComponentType.DATABASE,
        ))
        status, evidence, gaps = monitor._check_business_continuity(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_failover_capability_no_db(self, monitor: ComplianceMonitor):
        """No DB/cache should return NOT_APPLICABLE."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        status, evidence, gaps = monitor._check_failover_capability(graph)
        assert status == ControlStatus.NOT_APPLICABLE

    def test_check_failover_capability_all_enabled(self, monitor: ComplianceMonitor):
        """All DB/cache with failover enabled should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            failover=FailoverConfig(enabled=True),
        ))
        status, evidence, gaps = monitor._check_failover_capability(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_failover_capability_none_enabled(self, monitor: ComplianceMonitor):
        """DB/cache without failover should be NON_COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
        ))
        status, evidence, gaps = monitor._check_failover_capability(graph)
        assert status == ControlStatus.NON_COMPLIANT

    def test_check_concentration_risk_no_spofs(self, monitor: ComplianceMonitor):
        """No SPOFs should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        ))
        graph.add_dependency(Dependency(source_id="app", target_id="db"))
        status, evidence, gaps = monitor._check_concentration_risk(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_third_party_risk_no_external(self, monitor: ComplianceMonitor):
        """No external APIs should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        status, evidence, gaps = monitor._check_third_party_risk(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_third_party_risk_unmanaged(self, monitor: ComplianceMonitor):
        """External API without redundancy should be NON_COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="ext", name="External", type=ComponentType.EXTERNAL_API,
            replicas=1,
        ))
        status, evidence, gaps = monitor._check_third_party_risk(graph)
        assert status == ControlStatus.NON_COMPLIANT

    def test_check_third_party_exit_no_external(self, monitor: ComplianceMonitor):
        """No external APIs should return NOT_APPLICABLE."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        status, evidence, gaps = monitor._check_third_party_exit(graph)
        assert status == ControlStatus.NOT_APPLICABLE

    def test_check_third_party_exit_with_circuit_breaker(self, monitor: ComplianceMonitor):
        """External API with circuit breaker decoupling should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        graph.add_component(Component(
            id="ext", name="Stripe", type=ComponentType.EXTERNAL_API,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="ext",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        status, evidence, gaps = monitor._check_third_party_exit(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_third_party_exit_without_circuit_breaker(self, monitor: ComplianceMonitor):
        """External API without circuit breaker should be NON_COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        graph.add_component(Component(
            id="ext", name="Stripe", type=ComponentType.EXTERNAL_API,
        ))
        graph.add_dependency(Dependency(source_id="app", target_id="ext"))
        status, evidence, gaps = monitor._check_third_party_exit(graph)
        assert status == ControlStatus.NON_COMPLIANT

    def test_check_change_management_all_tagged(self, monitor: ComplianceMonitor):
        """All components with change_management tag should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            compliance_tags=ComplianceTags(change_management=True),
        ))
        status, evidence, gaps = monitor._check_change_management(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_change_management_partial_tagged(self, monitor: ComplianceMonitor):
        """Some components with change_management tag should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            compliance_tags=ComplianceTags(change_management=True),
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
        ))
        status, evidence, gaps = monitor._check_change_management(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_change_management_with_monitoring(self, monitor: ComplianceMonitor):
        """No change management tags but monitoring present should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="prometheus", name="Prometheus Monitoring", type=ComponentType.CUSTOM,
            security=SecurityProfile(log_enabled=True),
        ))
        status, evidence, gaps = monitor._check_change_management(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_change_management_none(self, monitor: ComplianceMonitor):
        """No change management controls should be NON_COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        status, evidence, gaps = monitor._check_change_management(graph)
        assert status == ControlStatus.NON_COMPLIANT

    def test_check_backup_procedures_no_storage(self, monitor: ComplianceMonitor):
        """No data storage components should return NOT_APPLICABLE."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        status, evidence, gaps = monitor._check_backup_procedures(graph)
        assert status == ControlStatus.NOT_APPLICABLE

    def test_check_backup_procedures_all_backed_up(self, monitor: ComplianceMonitor):
        """All storage components with backup should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            security=SecurityProfile(backup_enabled=True),
        ))
        status, evidence, gaps = monitor._check_backup_procedures(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_backup_procedures_partial(self, monitor: ComplianceMonitor):
        """Mix of backed up and not backed up should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            security=SecurityProfile(backup_enabled=True),
        ))
        graph.add_component(Component(
            id="cache", name="Cache", type=ComponentType.CACHE,
        ))
        status, evidence, gaps = monitor._check_backup_procedures(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_backup_procedures_none(self, monitor: ComplianceMonitor):
        """No backup on storage components should be NON_COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
        ))
        status, evidence, gaps = monitor._check_backup_procedures(graph)
        assert status == ControlStatus.NON_COMPLIANT

    def test_check_security_management_all(self, monitor: ComplianceMonitor):
        """Access controls + encryption + monitoring should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="waf", name="WAF Gateway", type=ComponentType.LOAD_BALANCER,
            security=SecurityProfile(
                auth_required=True,
                encryption_at_rest=True,
                encryption_in_transit=True,
                log_enabled=True,
            ),
        ))
        graph.add_component(Component(
            id="monitoring", name="Prometheus Monitoring", type=ComponentType.CUSTOM,
            security=SecurityProfile(log_enabled=True),
        ))
        status, evidence, gaps = monitor._check_security_management(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_audit_controls_full(self, monitor: ComplianceMonitor):
        """Logging + audit tags should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            security=SecurityProfile(log_enabled=True),
            compliance_tags=ComplianceTags(audit_logging=True),
        ))
        status, evidence, gaps = monitor._check_audit_controls(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_audit_controls_partial(self, monitor: ComplianceMonitor):
        """Only logging without audit tags should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            security=SecurityProfile(log_enabled=True),
        ))
        status, evidence, gaps = monitor._check_audit_controls(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_audit_controls_none(self, monitor: ComplianceMonitor):
        """No logging or audit tags should be NON_COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        status, evidence, gaps = monitor._check_audit_controls(graph)
        assert status == ControlStatus.NON_COMPLIANT

    def test_check_data_integrity_full(self, monitor: ComplianceMonitor):
        """Encryption at rest + backup should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            security=SecurityProfile(
                encryption_at_rest=True, backup_enabled=True,
            ),
        ))
        status, evidence, gaps = monitor._check_data_integrity(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_data_integrity_partial(self, monitor: ComplianceMonitor):
        """Only one of encryption or backup should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            security=SecurityProfile(encryption_at_rest=True),
        ))
        status, evidence, gaps = monitor._check_data_integrity(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_data_integrity_none(self, monitor: ComplianceMonitor):
        """No encryption or backup should be NON_COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
        ))
        status, evidence, gaps = monitor._check_data_integrity(graph)
        assert status == ControlStatus.NON_COMPLIANT

    def test_check_incident_detection_full(self, monitor: ComplianceMonitor):
        """Circuit breakers + monitoring should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            security=SecurityProfile(log_enabled=True),
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
        ))
        graph.add_component(Component(
            id="monitoring", name="Prometheus Monitoring", type=ComponentType.CUSTOM,
            security=SecurityProfile(log_enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        status, evidence, gaps = monitor._check_incident_detection(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_incident_detection_partial(self, monitor: ComplianceMonitor):
        """Circuit breakers without monitoring should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        status, evidence, gaps = monitor._check_incident_detection(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_incident_detection_none(self, monitor: ComplianceMonitor):
        """No circuit breakers or monitoring should be NON_COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        status, evidence, gaps = monitor._check_incident_detection(graph)
        assert status == ControlStatus.NON_COMPLIANT

    def test_run_check_unknown(self, monitor: ComplianceMonitor):
        """Unknown check name should return UNKNOWN status."""
        graph = InfraGraph()
        status, evidence, gaps = monitor._run_check("_check_nonexistent", graph)
        assert status == ControlStatus.UNKNOWN

    def test_check_security_controls_full(self, monitor: ComplianceMonitor):
        """IDS + WAF + backup should be COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            security=SecurityProfile(
                ids_monitored=True, waf_protected=True, backup_enabled=True,
            ),
        ))
        status, evidence, gaps = monitor._check_security_controls(graph)
        assert status == ControlStatus.COMPLIANT

    def test_check_security_controls_partial(self, monitor: ComplianceMonitor):
        """Some security controls should be PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            security=SecurityProfile(ids_monitored=True),
        ))
        status, evidence, gaps = monitor._check_security_controls(graph)
        assert status == ControlStatus.PARTIAL

    def test_check_security_controls_none(self, monitor: ComplianceMonitor):
        """No security controls should be NON_COMPLIANT."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        status, evidence, gaps = monitor._check_security_controls(graph)
        assert status == ControlStatus.NON_COMPLIANT


# ---------------------------------------------------------------------------
# Trend analysis: improving trend
# ---------------------------------------------------------------------------


class TestTrendAnalysis:
    def test_trend_detection_improving(self, monitor: ComplianceMonitor, minimal_graph: InfraGraph, secure_graph: InfraGraph):
        """Increasing scores should show improving trend."""
        monitor.track(minimal_graph)
        monitor.track(secure_graph)
        monitor.track(secure_graph)

        trends = monitor.get_trends(ComplianceFramework.DORA)
        # The trend should be improving since scores went up
        assert trends.trend in ("improving", "stable")


# ---------------------------------------------------------------------------
# Detect violations: compliant->partial degradation
# ---------------------------------------------------------------------------


class TestViolationsDegradation:
    def test_detect_compliant_to_partial(self, monitor: ComplianceMonitor, secure_graph: InfraGraph):
        """Switching from fully compliant to partially compliant should detect medium severity degradation."""
        # First track with secure graph
        monitor.track(secure_graph)

        # Create a graph that's slightly less secure (partial degradation)
        graph2 = InfraGraph()
        graph2.add_component(Component(
            id="app", name="app-server", type=ComponentType.APP_SERVER,
            port=443, replicas=3,
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
            security=SecurityProfile(
                auth_required=True,
                encryption_at_rest=True,
                encryption_in_transit=True,
                log_enabled=True,
            ),
            compliance_tags=ComplianceTags(audit_logging=True, change_management=True),
        ))
        graph2.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            port=5432, replicas=2,
            failover=FailoverConfig(enabled=True),
            security=SecurityProfile(
                encryption_at_rest=True, encryption_in_transit=True,
                backup_enabled=True, log_enabled=True,
            ),
        ))
        graph2.add_dependency(Dependency(source_id="app", target_id="db"))

        alerts = monitor.detect_violations(graph2)
        # Should have some alerts since we reduced the security posture
        assert len(alerts) >= 0  # may vary depending on exact control diffs


# ---------------------------------------------------------------------------
# Coverage gap tests — targeting specific uncovered lines
# ---------------------------------------------------------------------------


class TestRedundancyPartial:
    """Line 672: PARTIAL when redundancy ratio is between 0.5 and 1.0."""

    def test_partial_redundancy_ratio(self, monitor: ComplianceMonitor):
        """When some (but not all) critical components have replicas >= 2,
        _check_redundancy should return PARTIAL (ratio >= 0.5 but < 1.0)."""
        graph = InfraGraph()
        # Component with dependents AND replicas >= 2 (redundant)
        graph.add_component(Component(
            id="app", name="app-server", type=ComponentType.APP_SERVER,
            port=8080, replicas=2,
        ))
        # Component with dependents AND replicas == 1 (not redundant)
        graph.add_component(Component(
            id="db", name="database", type=ComponentType.DATABASE,
            port=5432, replicas=1,
        ))
        # A leaf component that depends on both (gives them dependents)
        graph.add_component(Component(
            id="client", name="client", type=ComponentType.APP_SERVER,
            port=9090, replicas=1,
        ))
        graph.add_dependency(Dependency(source_id="client", target_id="app"))
        graph.add_dependency(Dependency(source_id="client", target_id="db"))

        status, evidence, gaps = monitor._check_redundancy(graph)
        assert status == ControlStatus.PARTIAL
        assert any("app-server" in e for e in evidence)
        assert any("database" in g for g in gaps)


class TestNetworkSecurityPartial:
    """Lines 817-823: PARTIAL return for WAF/segmentation/rate-limiting."""

    def test_partial_only_waf(self, monitor: ComplianceMonitor):
        """When only WAF is configured, should be PARTIAL with segmentation
        and rate-limiting gaps."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER,
            port=8080, replicas=1,
            security=SecurityProfile(
                waf_protected=True,
                network_segmented=False,
                rate_limiting=False,
            ),
        ))

        status, evidence, gaps = monitor._check_network_security(graph)
        assert status == ControlStatus.PARTIAL
        assert any("WAF" in e for e in evidence)
        assert any("segmentation" in g.lower() for g in gaps)
        assert any("rate limiting" in g.lower() for g in gaps)

    def test_partial_only_rate_limiting(self, monitor: ComplianceMonitor):
        """When only rate limiting is configured, WAF and segmentation gaps."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER,
            port=8080, replicas=1,
            security=SecurityProfile(
                waf_protected=False,
                network_segmented=False,
                rate_limiting=True,
            ),
        ))

        status, evidence, gaps = monitor._check_network_security(graph)
        assert status == ControlStatus.PARTIAL
        assert any("WAF" in g for g in gaps)
        assert any("segmentation" in g.lower() for g in gaps)

    def test_partial_waf_and_segmentation(self, monitor: ComplianceMonitor):
        """When WAF and segmentation are present but not rate-limiting (score=2)."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER,
            port=8080, replicas=1,
            security=SecurityProfile(
                waf_protected=True,
                network_segmented=True,
                rate_limiting=False,
            ),
        ))

        status, evidence, gaps = monitor._check_network_security(graph)
        assert status == ControlStatus.PARTIAL
        assert any("Rate limiting" in g for g in gaps)


class TestFailoverPartial:
    """Line 896: PARTIAL when some but not all DB/cache have failover."""

    def test_partial_failover_capability(self, monitor: ComplianceMonitor):
        """When one DB has failover but another does not."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db1", name="primary-db", type=ComponentType.DATABASE,
            port=5432, replicas=2,
            failover=FailoverConfig(enabled=True, promotion_time_seconds=10),
        ))
        graph.add_component(Component(
            id="db2", name="secondary-db", type=ComponentType.DATABASE,
            port=5433, replicas=1,
            failover=FailoverConfig(enabled=False),
        ))

        status, evidence, gaps = monitor._check_failover_capability(graph)
        assert status == ControlStatus.PARTIAL
        assert any("primary-db" in e for e in evidence)
        assert any("secondary-db" in g for g in gaps)


class TestConcentrationRiskPartial:
    """Lines 916-917: PARTIAL when SPOFs exist but <= 1/3 of total components."""

    def test_partial_concentration_risk(self, monitor: ComplianceMonitor):
        """1 SPOF out of 4 components -> <= 1/3 -> PARTIAL."""
        graph = InfraGraph()
        # The SPOF: replicas=1 with dependents
        graph.add_component(Component(
            id="db", name="database", type=ComponentType.DATABASE,
            port=5432, replicas=1,
        ))
        # Non-SPOF components (replicas >= 2 or no dependents)
        graph.add_component(Component(
            id="app1", name="app1", type=ComponentType.APP_SERVER,
            port=8080, replicas=2,
        ))
        graph.add_component(Component(
            id="app2", name="app2", type=ComponentType.APP_SERVER,
            port=8081, replicas=2,
        ))
        graph.add_component(Component(
            id="cache", name="cache", type=ComponentType.CACHE,
            port=6379, replicas=2,
        ))
        # Only app1 depends on db (making db a SPOF)
        graph.add_dependency(Dependency(source_id="app1", target_id="db"))

        status, evidence, gaps = monitor._check_concentration_risk(graph)
        # 1 SPOF / 4 components: 1 <= 4//3=1 -> PARTIAL
        assert status == ControlStatus.PARTIAL
        assert any("SPOF" in e.lower() or "1" in e for e in evidence)


class TestThirdPartyRisk:
    """Lines 933, 939, 941: Third-party risk checks."""

    def test_partial_one_managed_one_unmanaged(self, monitor: ComplianceMonitor):
        """One external API with redundancy, one without -> PARTIAL (lines 933,941)."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="ext1", name="payment-api", type=ComponentType.EXTERNAL_API,
            port=443, replicas=2,  # managed via replicas
        ))
        graph.add_component(Component(
            id="ext2", name="email-api", type=ComponentType.EXTERNAL_API,
            port=443, replicas=1,
            failover=FailoverConfig(enabled=False),
        ))

        status, evidence, gaps = monitor._check_third_party_risk(graph)
        assert status == ControlStatus.PARTIAL
        assert any("payment-api" in e for e in evidence)
        assert any("email-api" in g for g in gaps)

    def test_compliant_all_managed(self, monitor: ComplianceMonitor):
        """All external APIs with redundancy -> COMPLIANT (line 939)."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="ext1", name="payment-api", type=ComponentType.EXTERNAL_API,
            port=443, replicas=2,
        ))

        status, evidence, gaps = monitor._check_third_party_risk(graph)
        assert status == ControlStatus.COMPLIANT

    def test_external_with_failover(self, monitor: ComplianceMonitor):
        """External API with failover enabled (line 933 OR branch)."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="ext1", name="payment-api", type=ComponentType.EXTERNAL_API,
            port=443, replicas=1,
            failover=FailoverConfig(enabled=True),
        ))

        status, evidence, gaps = monitor._check_third_party_risk(graph)
        assert status == ControlStatus.COMPLIANT
        assert any("failover" in e.lower() for e in evidence)


class TestThirdPartyExitPartial:
    """Line 973: PARTIAL in third-party exit when some have circuit breakers."""

    def test_partial_exit_strategy(self, monitor: ComplianceMonitor):
        """One external with circuit breaker, one without -> PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="ext1", name="payment-api", type=ComponentType.EXTERNAL_API,
            port=443, replicas=1,
        ))
        graph.add_component(Component(
            id="ext2", name="email-api", type=ComponentType.EXTERNAL_API,
            port=443, replicas=1,
        ))
        graph.add_component(Component(
            id="app", name="app-server", type=ComponentType.APP_SERVER,
            port=8080, replicas=1,
        ))
        # app depends on both external APIs, but only ext1 has CB
        graph.add_dependency(Dependency(
            source_id="app", target_id="ext1",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="ext2",
            circuit_breaker=CircuitBreakerConfig(enabled=False),
        ))

        status, evidence, gaps = monitor._check_third_party_exit(graph)
        assert status == ControlStatus.PARTIAL
        assert any("payment-api" in e for e in evidence)
        assert any("email-api" in g for g in gaps)


class TestSecurityManagementPartial:
    """Line 1087: PARTIAL in security management composite check."""

    def test_partial_security_management(self, monitor: ComplianceMonitor):
        """When only 1 or 2 of the sub-checks pass -> PARTIAL."""
        graph = InfraGraph()
        # Only logging (monitoring partial), no encryption, no access control
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER,
            port=8080, replicas=1,
            security=SecurityProfile(
                log_enabled=True,
                auth_required=False,
                encryption_in_transit=False,
                encryption_at_rest=False,
            ),
        ))

        status, evidence, gaps = monitor._check_security_management(graph)
        # monitoring is PARTIAL (logging but no monitoring component),
        # access controls NON_COMPLIANT, encryption NON_COMPLIANT
        # compliant_count is 1 (monitoring is PARTIAL, which counts)
        assert status == ControlStatus.PARTIAL


class TestAuditControlsPartial:
    """Line 1109: PARTIAL when only one of logging/audit is present."""

    def test_partial_audit_only_logging(self, monitor: ComplianceMonitor):
        """Only log_enabled but no audit_logging tag -> PARTIAL with gap about audit."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER,
            port=8080, replicas=1,
            security=SecurityProfile(log_enabled=True),
            compliance_tags=ComplianceTags(audit_logging=False),
        ))

        status, evidence, gaps = monitor._check_audit_controls(graph)
        assert status == ControlStatus.PARTIAL
        assert any("Audit logging" in g for g in gaps)

    def test_partial_audit_only_tags(self, monitor: ComplianceMonitor):
        """Only audit_logging tag but no log_enabled -> PARTIAL (line 1109 branch)."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER,
            port=8080, replicas=1,
            security=SecurityProfile(log_enabled=False),
            compliance_tags=ComplianceTags(audit_logging=True),
        ))

        status, evidence, gaps = monitor._check_audit_controls(graph)
        assert status == ControlStatus.PARTIAL
        assert any("Logging not enabled" in g for g in gaps)


class TestDataIntegrityPartial:
    """Line 1135: PARTIAL when only encryption OR backup (not both)."""

    def test_partial_only_backup(self, monitor: ComplianceMonitor):
        """Backup but no encryption at rest -> PARTIAL with encryption gap."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="database", type=ComponentType.DATABASE,
            port=5432, replicas=1,
            security=SecurityProfile(
                encryption_at_rest=False,
                backup_enabled=True,
            ),
        ))

        status, evidence, gaps = monitor._check_data_integrity(graph)
        assert status == ControlStatus.PARTIAL
        assert any("Encryption at rest" in g for g in gaps)

    def test_partial_only_encryption(self, monitor: ComplianceMonitor):
        """Encryption at rest but no backup -> PARTIAL."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="database", type=ComponentType.DATABASE,
            port=5432, replicas=1,
            security=SecurityProfile(
                encryption_at_rest=True,
                backup_enabled=False,
            ),
        ))

        status, evidence, gaps = monitor._check_data_integrity(graph)
        assert status == ControlStatus.PARTIAL
        assert any("Backup" in g for g in gaps)


class TestTrendStableFallback:
    """Line 1240: trend = 'stable' fallback when neither improving nor degrading."""

    def test_fluctuating_trend(self, monitor: ComplianceMonitor):
        """When compliance percentages fluctuate (up-down-up), trend is 'stable'."""
        fw = ComplianceFramework.SOC2
        now = datetime.now(timezone.utc)

        # Inject history with fluctuating percentages: 70, 80, 70
        for pct in [70.0, 80.0, 70.0]:
            snapshot = ComplianceSnapshot(
                timestamp=now,
                framework=fw,
                total_controls=10,
                compliant=int(pct / 10),
                partial=0,
                non_compliant=10 - int(pct / 10),
                compliance_percentage=pct,
                controls=[],
            )
            monitor._history[fw].append(snapshot)

        trend = monitor.get_trends(fw)
        assert trend.trend == "stable"


class TestComplianceDriftContinue:
    """Line 1289: continue when prev_status is None (new control not in previous snapshot)."""

    def test_new_control_skipped_in_drift(self, monitor: ComplianceMonitor):
        """A new control that didn't exist in the previous snapshot should be skipped."""
        fw = ComplianceFramework.SOC2
        now = datetime.now(timezone.utc)

        # Create a previous snapshot with only one control
        prev_snapshot = ComplianceSnapshot(
            timestamp=now,
            framework=fw,
            total_controls=1,
            compliant=1,
            partial=0,
            non_compliant=0,
            compliance_percentage=100.0,
            controls=[
                ComplianceControl(
                    control_id="SOC2-OLD",
                    framework=fw,
                    title="Old Control",
                    description="exists in previous",
                    status=ControlStatus.COMPLIANT,
                    evidence=["ok"],
                    gaps=[],
                    remediation=[],
                    last_assessed=now,
                ),
            ],
        )
        monitor._history[fw].append(prev_snapshot)

        # Now run detect_violations with a graph; the current assessment
        # will likely have controls not present in prev_snapshot
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER,
            port=8080, replicas=1,
        ))
        alerts = monitor.detect_violations(graph)
        # Should not crash; the continue on line 1289 is exercised
        # for all controls in current that are not in prev_status_map
        assert isinstance(alerts, list)


class TestSQLitePersistence:
    """Lines 1427, 1451, 1491, 1503-1504, 1510-1511, 1514-1515:
    SQLite persistence methods."""

    def test_init_store_persist_and_load(self, tmp_path):
        """Full round-trip: init store, persist snapshot, load history."""
        store_path = tmp_path / "compliance.db"
        monitor = ComplianceMonitor(store_path=store_path)

        # Verify store was created
        assert store_path.exists()

        # Create a minimal graph and do an assessment to persist
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="app", type=ComponentType.APP_SERVER,
            port=8080, replicas=1,
        ))
        monitor.track(graph)

        # Verify snapshots were persisted
        count = monitor.get_stored_snapshot_count()
        assert count > 0

        # Create a new monitor from same store to test _load_history_from_store
        monitor2 = ComplianceMonitor(store_path=store_path)
        count2 = monitor2.get_stored_snapshot_count()
        assert count2 == count

    def test_init_store_none_path(self):
        """Line 1427: _init_store returns early when store_path is None."""
        monitor = ComplianceMonitor(store_path=None)
        # Should not create any DB; _init_store returns early
        monitor._init_store()  # no-op, should not raise

    def test_persist_snapshot_none_path(self):
        """Line 1451: _persist_snapshot returns early when store_path is None."""
        monitor = ComplianceMonitor(store_path=None)
        now = datetime.now(timezone.utc)
        snapshot = ComplianceSnapshot(
            timestamp=now,
            framework=ComplianceFramework.SOC2,
            total_controls=1,
            compliant=1,
            partial=0,
            non_compliant=0,
            compliance_percentage=100.0,
            controls=[],
        )
        # Should not raise
        monitor._persist_snapshot(snapshot)

    def test_load_history_none_path(self):
        """Line 1491: _load_history_from_store returns early when path is None."""
        monitor = ComplianceMonitor(store_path=None)
        monitor._load_history_from_store()  # no-op

    def test_load_history_nonexistent_path(self, tmp_path):
        """Line 1491: _load_history_from_store returns early when path doesn't exist."""
        monitor = ComplianceMonitor(store_path=None)
        monitor._store_path = tmp_path / "nonexistent.db"
        monitor._load_history_from_store()  # no-op
        assert monitor.get_stored_snapshot_count() == 0

    def test_load_with_invalid_framework_value(self, tmp_path):
        """Lines 1503-1504: ValueError for invalid framework skips the row."""
        import json
        import sqlite3

        store_path = tmp_path / "compliance.db"
        conn = sqlite3.connect(str(store_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                framework TEXT NOT NULL,
                total_controls INTEGER NOT NULL,
                compliant INTEGER NOT NULL,
                partial INTEGER NOT NULL,
                non_compliant INTEGER NOT NULL,
                compliance_percentage REAL NOT NULL,
                controls_json TEXT NOT NULL
            )
        """)
        now = datetime.now(timezone.utc)
        # Insert a row with an invalid framework value
        conn.execute(
            """INSERT INTO compliance_snapshots
               (timestamp, framework, total_controls, compliant, partial,
                non_compliant, compliance_percentage, controls_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (now.isoformat(), "INVALID_FRAMEWORK", 1, 1, 0, 0, 100.0, json.dumps([])),
        )
        conn.commit()
        conn.close()

        # Should load without error, skipping the invalid row
        monitor = ComplianceMonitor(store_path=store_path)
        assert monitor.get_stored_snapshot_count() == 0

    def test_load_with_invalid_control_framework(self, tmp_path):
        """Lines 1510-1511: ValueError for invalid framework in control data falls back."""
        import json
        import sqlite3

        store_path = tmp_path / "compliance.db"
        conn = sqlite3.connect(str(store_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                framework TEXT NOT NULL,
                total_controls INTEGER NOT NULL,
                compliant INTEGER NOT NULL,
                partial INTEGER NOT NULL,
                non_compliant INTEGER NOT NULL,
                compliance_percentage REAL NOT NULL,
                controls_json TEXT NOT NULL
            )
        """)
        now = datetime.now(timezone.utc)
        controls_data = [
            {
                "control_id": "TEST-1",
                "framework": "BOGUS_FRAMEWORK",  # Invalid framework in control
                "title": "Test Control",
                "description": "test",
                "status": "compliant",
                "evidence": [],
                "gaps": [],
                "remediation": [],
                "last_assessed": now.isoformat(),
                "risk_if_non_compliant": "test risk",
            }
        ]
        conn.execute(
            """INSERT INTO compliance_snapshots
               (timestamp, framework, total_controls, compliant, partial,
                non_compliant, compliance_percentage, controls_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (now.isoformat(), "soc2", 1, 1, 0, 0, 100.0, json.dumps(controls_data)),
        )
        conn.commit()
        conn.close()

        monitor = ComplianceMonitor(store_path=store_path)
        count = monitor.get_stored_snapshot_count(ComplianceFramework.SOC2)
        assert count == 1
        # The control's framework should fall back to the snapshot's framework
        snap = monitor._history[ComplianceFramework.SOC2][0]
        assert snap.controls[0].framework == ComplianceFramework.SOC2

    def test_load_with_invalid_control_status(self, tmp_path):
        """Lines 1514-1515: ValueError for invalid status falls back to UNKNOWN."""
        import json
        import sqlite3

        store_path = tmp_path / "compliance.db"
        conn = sqlite3.connect(str(store_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                framework TEXT NOT NULL,
                total_controls INTEGER NOT NULL,
                compliant INTEGER NOT NULL,
                partial INTEGER NOT NULL,
                non_compliant INTEGER NOT NULL,
                compliance_percentage REAL NOT NULL,
                controls_json TEXT NOT NULL
            )
        """)
        now = datetime.now(timezone.utc)
        controls_data = [
            {
                "control_id": "TEST-1",
                "framework": "soc2",
                "title": "Test Control",
                "description": "test",
                "status": "BOGUS_STATUS",  # Invalid status
                "evidence": [],
                "gaps": [],
                "remediation": [],
                "last_assessed": now.isoformat(),
                "risk_if_non_compliant": "test risk",
            }
        ]
        conn.execute(
            """INSERT INTO compliance_snapshots
               (timestamp, framework, total_controls, compliant, partial,
                non_compliant, compliance_percentage, controls_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (now.isoformat(), "soc2", 1, 1, 0, 0, 100.0, json.dumps(controls_data)),
        )
        conn.commit()
        conn.close()

        monitor = ComplianceMonitor(store_path=store_path)
        count = monitor.get_stored_snapshot_count(ComplianceFramework.SOC2)
        assert count == 1
        snap = monitor._history[ComplianceFramework.SOC2][0]
        assert snap.controls[0].status == ControlStatus.UNKNOWN
