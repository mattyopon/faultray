"""Tests for Continuous Compliance Monitor with SQLite persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

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
        id="app", name="app-server", type=ComponentType.APP_SERVER,
        port=8080, replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="database", type=ComponentType.DATABASE,
        port=5432, replicas=1,
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


@pytest.fixture
def secure_graph() -> InfraGraph:
    """A well-configured graph with security features."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="waf", name="WAF / API Gateway", type=ComponentType.LOAD_BALANCER,
        port=443, replicas=2,
        security=SecurityProfile(
            waf_protected=True, rate_limiting=True, auth_required=True,
            network_segmented=True, encryption_at_rest=True,
            encryption_in_transit=True, backup_enabled=True,
            log_enabled=True, ids_monitored=True,
        ),
        compliance_tags=ComplianceTags(audit_logging=True, change_management=True),
    ))
    graph.add_component(Component(
        id="app", name="app-server", type=ComponentType.APP_SERVER,
        port=443, replicas=3,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        security=SecurityProfile(
            auth_required=True, encryption_at_rest=True,
            encryption_in_transit=True, log_enabled=True,
            ids_monitored=True, network_segmented=True, backup_enabled=True,
        ),
        compliance_tags=ComplianceTags(audit_logging=True, change_management=True),
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        port=5432, replicas=2,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=15),
        region=RegionConfig(region="us-east-1", is_primary=True, dr_target_region="us-west-2"),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            backup_enabled=True, log_enabled=True, network_segmented=True,
        ),
        compliance_tags=ComplianceTags(audit_logging=True, change_management=True),
    ))
    graph.add_component(Component(
        id="monitoring", name="Prometheus Monitoring", type=ComponentType.CUSTOM,
        replicas=2, security=SecurityProfile(log_enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="waf", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return graph


# ---------------------------------------------------------------------------
# SQLite persistence tests
# ---------------------------------------------------------------------------


class TestSQLitePersistence:
    def test_store_creates_db(self, tmp_path: Path, secure_graph: InfraGraph):
        """Providing a store_path should create the SQLite file after track()."""
        db_path = tmp_path / "compliance.db"
        monitor = ComplianceMonitor(store_path=db_path)
        monitor.track(secure_graph)
        assert db_path.exists()

    def test_persist_and_load_snapshots(self, tmp_path: Path, secure_graph: InfraGraph):
        """Snapshots should survive across monitor instances."""
        db_path = tmp_path / "compliance.db"

        # Write
        m1 = ComplianceMonitor(store_path=db_path)
        m1.track(secure_graph)
        count1 = m1.get_stored_snapshot_count()
        assert count1 > 0

        # Read in new instance
        m2 = ComplianceMonitor(store_path=db_path)
        count2 = m2.get_stored_snapshot_count()
        assert count2 == count1

    def test_trend_survives_restart(self, tmp_path: Path, secure_graph: InfraGraph, minimal_graph: InfraGraph):
        """Trend analysis should work across restarts with SQLite."""
        db_path = tmp_path / "compliance.db"

        m1 = ComplianceMonitor(store_path=db_path)
        m1.track(secure_graph)
        m1.track(secure_graph)

        # New instance loads history
        m2 = ComplianceMonitor(store_path=db_path)
        m2.track(minimal_graph)

        trends = m2.get_trends(ComplianceFramework.DORA)
        assert len(trends.snapshots) == 3

    def test_snapshot_per_framework(self, tmp_path: Path, secure_graph: InfraGraph):
        """Each track() call should create one snapshot per framework."""
        db_path = tmp_path / "compliance.db"
        monitor = ComplianceMonitor(store_path=db_path)
        monitor.track(secure_graph)

        total = monitor.get_stored_snapshot_count()
        assert total == len(ComplianceFramework)

    def test_get_stored_snapshot_count_by_framework(self, tmp_path: Path, secure_graph: InfraGraph):
        db_path = tmp_path / "compliance.db"
        monitor = ComplianceMonitor(store_path=db_path)
        monitor.track(secure_graph)

        for fw in ComplianceFramework:
            assert monitor.get_stored_snapshot_count(fw) == 1

    def test_no_store_path_works(self, secure_graph: InfraGraph):
        """Monitor without store_path should work as before (in-memory only)."""
        monitor = ComplianceMonitor()
        monitor.track(secure_graph)
        assert monitor.get_stored_snapshot_count() > 0


# ---------------------------------------------------------------------------
# Snapshot and trend tests with SQLite
# ---------------------------------------------------------------------------


class TestSnapshotTrendWithStore:
    def test_assess_produces_snapshot(self, tmp_path: Path, secure_graph: InfraGraph):
        db_path = tmp_path / "compliance.db"
        monitor = ComplianceMonitor(store_path=db_path)
        snap = monitor.assess(secure_graph, ComplianceFramework.SOC2)
        assert isinstance(snap, ComplianceSnapshot)
        assert snap.total_controls >= 10

    def test_violations_detected_on_degradation(
        self, tmp_path: Path, secure_graph: InfraGraph, minimal_graph: InfraGraph,
    ):
        db_path = tmp_path / "compliance.db"
        monitor = ComplianceMonitor(store_path=db_path)
        monitor.track(secure_graph)

        alerts = monitor.detect_violations(minimal_graph)
        degradation_alerts = [a for a in alerts if a.alert_type == "degradation"]
        assert len(degradation_alerts) > 0

    def test_audit_readiness_with_store(self, tmp_path: Path, secure_graph: InfraGraph):
        db_path = tmp_path / "compliance.db"
        monitor = ComplianceMonitor(store_path=db_path)
        monitor.track(secure_graph)
        readiness = monitor.get_audit_readiness(ComplianceFramework.DORA)
        assert readiness > 0

    def test_evidence_package_with_store(self, tmp_path: Path, secure_graph: InfraGraph):
        db_path = tmp_path / "compliance.db"
        monitor = ComplianceMonitor(store_path=db_path)
        monitor.track(secure_graph)
        package = monitor.generate_evidence_package(ComplianceFramework.SOC2)
        assert package["status"] == "assessed"
        assert len(package["controls"]) >= 10
