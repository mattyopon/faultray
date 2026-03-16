"""Tests for the Infrastructure Anomaly Detection Engine."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.anomaly_detector import (
    Anomaly,
    AnomalyDetector,
    AnomalyReport,
    AnomalySeverity,
    AnomalyType,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover.enabled = True
    return c


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_graph() -> InfraGraph:
    return InfraGraph()


@pytest.fixture
def single_component_graph() -> InfraGraph:
    g = InfraGraph()
    g.add_component(_comp("app", "App Server"))
    return g


@pytest.fixture
def healthy_graph() -> InfraGraph:
    """Well-configured graph with replicas, failover, encryption, logging, backups."""
    g = InfraGraph()
    db = Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=3, failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_at_rest=True, log_enabled=True, backup_enabled=True,
        ),
    )
    app = Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3, failover=FailoverConfig(enabled=True),
        security=SecurityProfile(log_enabled=True),
    )
    lb = Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2, failover=FailoverConfig(enabled=True),
        security=SecurityProfile(log_enabled=True),
    )
    g.add_component(db)
    g.add_component(app)
    g.add_component(lb)
    g.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    g.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return g


@pytest.fixture
def spof_graph() -> InfraGraph:
    """Graph with a single-replica DB depended on by two app servers."""
    g = InfraGraph()
    g.add_component(_comp("db", "PostgreSQL", ComponentType.DATABASE, replicas=1))
    g.add_component(_comp("app1", "App 1", replicas=3))
    g.add_component(_comp("app2", "App 2", replicas=3))
    g.add_dependency(Dependency(source_id="app1", target_id="db", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app2", target_id="db", dependency_type="requires"))
    return g


# ===========================================================================
# Tests: detect_utilization_anomalies
# ===========================================================================


class TestUtilizationAnomalies:
    """Tests for utilization spike and waste detection."""

    def test_high_utilization_critical(self):
        """Utilization > 95% should be CRITICAL."""
        g = InfraGraph()
        g.add_component(Component(
            id="hot", name="Hot Server", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(cpu_percent=96.0),
        ))
        detector = AnomalyDetector(utilization_threshold=80.0)
        anomalies = detector.detect_utilization_anomalies(g)
        assert len(anomalies) == 1
        assert anomalies[0].severity == AnomalySeverity.CRITICAL
        assert anomalies[0].anomaly_type == AnomalyType.UTILIZATION_SPIKE

    def test_high_utilization_high(self):
        """Utilization 91-95% should be HIGH."""
        g = InfraGraph()
        g.add_component(Component(
            id="warm", name="Warm Server", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(cpu_percent=92.0),
        ))
        detector = AnomalyDetector(utilization_threshold=80.0)
        anomalies = detector.detect_utilization_anomalies(g)
        assert len(anomalies) == 1
        assert anomalies[0].severity == AnomalySeverity.HIGH

    def test_high_utilization_medium(self):
        """Utilization 81-90% should be MEDIUM."""
        g = InfraGraph()
        g.add_component(Component(
            id="mid", name="Mid Server", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(cpu_percent=85.0),
        ))
        detector = AnomalyDetector(utilization_threshold=80.0)
        anomalies = detector.detect_utilization_anomalies(g)
        assert len(anomalies) == 1
        assert anomalies[0].severity == AnomalySeverity.MEDIUM

    def test_normal_utilization_no_anomaly(self):
        """Utilization within threshold should not flag."""
        g = InfraGraph()
        g.add_component(Component(
            id="ok", name="OK Server", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(cpu_percent=50.0),
        ))
        detector = AnomalyDetector(utilization_threshold=80.0)
        anomalies = detector.detect_utilization_anomalies(g)
        assert len(anomalies) == 0

    def test_zero_utilization_with_replicas_flags_waste(self):
        """Zero utilization with multiple replicas should flag capacity waste."""
        g = InfraGraph()
        g.add_component(_comp("idle", "Idle Server", replicas=3))
        detector = AnomalyDetector()
        anomalies = detector.detect_utilization_anomalies(g)
        capacity = [a for a in anomalies if a.anomaly_type == AnomalyType.CAPACITY_ANOMALY]
        assert len(capacity) == 1
        assert capacity[0].severity == AnomalySeverity.LOW

    def test_zero_utilization_single_replica_no_flag(self):
        """Zero utilization with 1 replica should not flag waste."""
        g = InfraGraph()
        g.add_component(_comp("single", "Single", replicas=1))
        detector = AnomalyDetector()
        anomalies = detector.detect_utilization_anomalies(g)
        assert len(anomalies) == 0

    def test_custom_threshold(self):
        """Custom utilization threshold should be respected."""
        g = InfraGraph()
        g.add_component(Component(
            id="s", name="Server", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(cpu_percent=55.0),
        ))
        # With threshold at 50, 55% should flag
        detector = AnomalyDetector(utilization_threshold=50.0)
        anomalies = detector.detect_utilization_anomalies(g)
        assert len(anomalies) == 1

    def test_anomaly_id_format(self):
        """Anomaly IDs should follow the pattern type-componentId."""
        g = InfraGraph()
        g.add_component(Component(
            id="srv1", name="Server 1", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(cpu_percent=95.0),
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_utilization_anomalies(g)
        assert anomalies[0].id == "utilization_spike-srv1"

    def test_utilization_expected_range(self):
        """Expected range should reflect the threshold."""
        g = InfraGraph()
        g.add_component(Component(
            id="s", name="S", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(cpu_percent=90.0),
        ))
        detector = AnomalyDetector(utilization_threshold=75.0)
        anomalies = detector.detect_utilization_anomalies(g)
        assert "75" in anomalies[0].expected_range


# ===========================================================================
# Tests: detect_health_anomalies
# ===========================================================================


class TestHealthAnomalies:
    """Tests for health status anomaly detection."""

    def test_down_component_critical(self):
        """DOWN component should be CRITICAL."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", health=HealthStatus.DOWN))
        detector = AnomalyDetector()
        anomalies = detector.detect_health_anomalies(g)
        assert len(anomalies) == 1
        assert anomalies[0].severity == AnomalySeverity.CRITICAL
        assert anomalies[0].anomaly_type == AnomalyType.HEALTH_ANOMALY

    def test_degraded_component_high(self):
        """DEGRADED component should be HIGH."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", health=HealthStatus.DEGRADED))
        detector = AnomalyDetector()
        anomalies = detector.detect_health_anomalies(g)
        assert len(anomalies) == 1
        assert anomalies[0].severity == AnomalySeverity.HIGH

    def test_overloaded_component_high(self):
        """OVERLOADED component should be HIGH."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", health=HealthStatus.OVERLOADED))
        detector = AnomalyDetector()
        anomalies = detector.detect_health_anomalies(g)
        assert len(anomalies) == 1
        assert anomalies[0].severity == AnomalySeverity.HIGH

    def test_healthy_component_no_anomaly(self):
        """HEALTHY component should not be flagged."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", health=HealthStatus.HEALTHY))
        detector = AnomalyDetector()
        anomalies = detector.detect_health_anomalies(g)
        assert len(anomalies) == 0

    def test_down_with_dependents_higher_confidence(self):
        """DOWN component with dependents should have higher confidence."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", health=HealthStatus.DOWN))
        g.add_component(_comp("app", "App"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        detector = AnomalyDetector()
        anomalies = detector.detect_health_anomalies(g)
        db_anomalies = [a for a in anomalies if a.component_id == "db"]
        assert len(db_anomalies) == 1
        assert db_anomalies[0].confidence == 0.9

    def test_down_without_dependents_lower_confidence(self):
        """DOWN component without dependents should have lower confidence."""
        g = InfraGraph()
        g.add_component(_comp("leaf", "Leaf", health=HealthStatus.DOWN))
        detector = AnomalyDetector()
        anomalies = detector.detect_health_anomalies(g)
        assert anomalies[0].confidence == 0.8

    def test_health_anomaly_id_format(self):
        """Health anomaly ID should follow the naming pattern."""
        g = InfraGraph()
        g.add_component(_comp("svc1", "Service 1", health=HealthStatus.DOWN))
        detector = AnomalyDetector()
        anomalies = detector.detect_health_anomalies(g)
        assert anomalies[0].id == "health_anomaly-svc1"


# ===========================================================================
# Tests: detect_topology_anomalies
# ===========================================================================


class TestTopologyAnomalies:
    """Tests for topology pattern anomaly detection."""

    def test_deep_dependency_chain(self):
        """Dependency chain deeper than threshold should flag."""
        g = InfraGraph()
        # Create a chain: c0 -> c1 -> c2 -> c3 -> c4 -> c5
        for i in range(6):
            g.add_component(_comp(f"c{i}", f"Comp {i}"))
        for i in range(5):
            g.add_dependency(Dependency(source_id=f"c{i}", target_id=f"c{i+1}"))
        detector = AnomalyDetector(dependency_depth_threshold=4)
        anomalies = detector.detect_topology_anomalies(g)
        deep = [a for a in anomalies if "deep" in a.description.lower() or "depth" in a.description.lower()]
        assert len(deep) >= 1
        assert deep[0].severity == AnomalySeverity.HIGH

    def test_shallow_chain_no_flag(self):
        """Chain within threshold should not flag."""
        g = InfraGraph()
        for i in range(3):
            g.add_component(_comp(f"c{i}", f"Comp {i}"))
        for i in range(2):
            g.add_dependency(Dependency(source_id=f"c{i}", target_id=f"c{i+1}"))
        detector = AnomalyDetector(dependency_depth_threshold=4)
        anomalies = detector.detect_topology_anomalies(g)
        deep = [a for a in anomalies if "depth" in a.description.lower()]
        assert len(deep) == 0

    def test_orphan_component_detected(self):
        """Component with no connections should be flagged as orphan."""
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("db", "DB"))
        g.add_component(_comp("orphan", "Orphan"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        detector = AnomalyDetector()
        anomalies = detector.detect_topology_anomalies(g)
        orphans = [a for a in anomalies if "orphan" in a.description.lower()]
        assert len(orphans) == 1
        assert orphans[0].component_id == "orphan"
        assert orphans[0].severity == AnomalySeverity.LOW

    def test_no_orphan_when_single_component(self):
        """Single component should not be flagged as orphan."""
        g = InfraGraph()
        g.add_component(_comp("solo", "Solo"))
        detector = AnomalyDetector()
        anomalies = detector.detect_topology_anomalies(g)
        orphans = [a for a in anomalies if "orphan" in a.description.lower()]
        assert len(orphans) == 0

    def test_circular_dependency_detected(self):
        """Circular dependency should be flagged as CRITICAL."""
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_component(_comp("c", "C"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        g.add_dependency(Dependency(source_id="c", target_id="a"))
        detector = AnomalyDetector()
        anomalies = detector.detect_topology_anomalies(g)
        circular = [a for a in anomalies if "circular" in a.description.lower()]
        assert len(circular) >= 1
        assert circular[0].severity == AnomalySeverity.CRITICAL
        assert circular[0].confidence == 1.0

    def test_high_fanout_detected(self):
        """Component with more than 5 dependencies should be flagged."""
        g = InfraGraph()
        g.add_component(_comp("hub", "Hub"))
        for i in range(7):
            g.add_component(_comp(f"dep{i}", f"Dep {i}"))
            g.add_dependency(Dependency(source_id="hub", target_id=f"dep{i}"))
        detector = AnomalyDetector()
        anomalies = detector.detect_topology_anomalies(g)
        fanout = [a for a in anomalies if "fan-out" in a.description.lower()]
        assert len(fanout) == 1
        assert fanout[0].component_id == "hub"
        assert fanout[0].severity == AnomalySeverity.MEDIUM

    def test_fanout_at_5_no_flag(self):
        """Exactly 5 dependencies should not flag fan-out."""
        g = InfraGraph()
        g.add_component(_comp("hub", "Hub"))
        for i in range(5):
            g.add_component(_comp(f"dep{i}", f"Dep {i}"))
            g.add_dependency(Dependency(source_id="hub", target_id=f"dep{i}"))
        detector = AnomalyDetector()
        anomalies = detector.detect_topology_anomalies(g)
        fanout = [a for a in anomalies if "fan-out" in a.description.lower()]
        assert len(fanout) == 0

    def test_empty_graph_no_topology_anomalies(self, empty_graph):
        """Empty graph should produce no topology anomalies."""
        detector = AnomalyDetector()
        anomalies = detector.detect_topology_anomalies(empty_graph)
        assert len(anomalies) == 0

    def test_cycle_detection_exception_handled(self, monkeypatch):
        """When nx.simple_cycles raises, the exception should be swallowed."""
        from unittest.mock import patch

        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))

        with patch("networkx.simple_cycles", side_effect=RuntimeError("fail")):
            detector = AnomalyDetector()
            anomalies = detector.detect_topology_anomalies(g)
        circular = [a for a in anomalies if "circular" in a.description.lower()]
        assert len(circular) == 0


# ===========================================================================
# Tests: detect_configuration_anomalies
# ===========================================================================


class TestConfigurationAnomalies:
    """Tests for configuration issue detection."""

    def test_database_insufficient_replicas(self):
        """Database with 1 replica should be flagged (min_replicas=2)."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=1))
        detector = AnomalyDetector(min_replicas_for_critical=2)
        anomalies = detector.detect_configuration_anomalies(g)
        replica_issues = [a for a in anomalies if "replica" in a.description.lower()]
        assert len(replica_issues) >= 1

    def test_database_sufficient_replicas(self):
        """Database with enough replicas should not flag replica issues."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=3, failover=True))
        detector = AnomalyDetector(min_replicas_for_critical=2)
        anomalies = detector.detect_configuration_anomalies(g)
        replica_issues = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.CONFIGURATION_ANOMALY
            and "replica" in a.description.lower()
        ]
        assert len(replica_issues) == 0

    def test_database_no_failover(self):
        """Database without failover should be flagged as HIGH."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=3, failover=False))
        detector = AnomalyDetector()
        anomalies = detector.detect_configuration_anomalies(g)
        failover_issues = [a for a in anomalies if "failover" in a.description.lower()]
        assert len(failover_issues) == 1
        assert failover_issues[0].severity == AnomalySeverity.HIGH

    def test_database_with_failover_no_failover_flag(self):
        """Database with failover should not flag failover issues."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=3, failover=True))
        detector = AnomalyDetector()
        anomalies = detector.detect_configuration_anomalies(g)
        failover_issues = [a for a in anomalies if "failover" in a.description.lower()]
        assert len(failover_issues) == 0

    def test_over_provisioned_replicas(self):
        """Component with > 10 replicas should be flagged."""
        g = InfraGraph()
        g.add_component(_comp("big", "Big Service", replicas=15))
        detector = AnomalyDetector()
        anomalies = detector.detect_configuration_anomalies(g)
        overprov = [a for a in anomalies if "over-provisioned" in a.description.lower()]
        assert len(overprov) == 1
        assert overprov[0].severity == AnomalySeverity.MEDIUM

    def test_ten_replicas_no_flag(self):
        """Exactly 10 replicas should NOT be flagged as over-provisioned."""
        g = InfraGraph()
        g.add_component(_comp("ok", "OK Service", replicas=10))
        detector = AnomalyDetector()
        anomalies = detector.detect_configuration_anomalies(g)
        overprov = [a for a in anomalies if "over-provisioned" in a.description.lower()]
        assert len(overprov) == 0

    def test_component_with_many_dependents_insufficient_replicas(self):
        """Component with >= 2 dependents and < min replicas should be CRITICAL."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=1))
        g.add_component(_comp("app1", "App1"))
        g.add_component(_comp("app2", "App2"))
        g.add_dependency(Dependency(source_id="app1", target_id="db", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="app2", target_id="db", dependency_type="requires"))
        detector = AnomalyDetector(min_replicas_for_critical=2)
        anomalies = detector.detect_configuration_anomalies(g)
        replica_crit = [
            a for a in anomalies
            if "replica" in a.description.lower()
            and a.severity == AnomalySeverity.CRITICAL
        ]
        assert len(replica_crit) >= 1

    def test_load_balancer_insufficient_replicas(self):
        """Load balancer type should also trigger replica checks."""
        g = InfraGraph()
        g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=1))
        detector = AnomalyDetector(min_replicas_for_critical=2)
        anomalies = detector.detect_configuration_anomalies(g)
        replica_issues = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.CONFIGURATION_ANOMALY
            and "replica" in a.description.lower()
        ]
        assert len(replica_issues) >= 1


# ===========================================================================
# Tests: detect_security_anomalies
# ===========================================================================


class TestSecurityAnomalies:
    """Tests for security configuration gap detection."""

    def test_database_no_encryption(self):
        """Database without encryption at rest should be CRITICAL."""
        g = InfraGraph()
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            security=SecurityProfile(encryption_at_rest=False),
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_security_anomalies(g)
        encrypt = [a for a in anomalies if "encryption" in a.description.lower()]
        assert len(encrypt) == 1
        assert encrypt[0].severity == AnomalySeverity.CRITICAL

    def test_database_with_encryption_no_flag(self):
        """Database with encryption should not flag encryption issue."""
        g = InfraGraph()
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            security=SecurityProfile(encryption_at_rest=True, log_enabled=True, backup_enabled=True),
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_security_anomalies(g)
        encrypt = [a for a in anomalies if "encryption" in a.description.lower()]
        assert len(encrypt) == 0

    def test_no_logging(self):
        """Component without logging should be flagged MEDIUM."""
        g = InfraGraph()
        g.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            security=SecurityProfile(log_enabled=False),
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_security_anomalies(g)
        log_issues = [a for a in anomalies if "logging" in a.description.lower()]
        assert len(log_issues) == 1
        assert log_issues[0].severity == AnomalySeverity.MEDIUM

    def test_logging_enabled_no_flag(self):
        """Component with logging should not flag logging issue."""
        g = InfraGraph()
        g.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            security=SecurityProfile(log_enabled=True),
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_security_anomalies(g)
        log_issues = [a for a in anomalies if "logging" in a.description.lower()]
        assert len(log_issues) == 0

    def test_database_no_backup(self):
        """Database without backups should be HIGH."""
        g = InfraGraph()
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            security=SecurityProfile(backup_enabled=False),
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_security_anomalies(g)
        backup_issues = [a for a in anomalies if "backup" in a.description.lower()]
        assert len(backup_issues) == 1
        assert backup_issues[0].severity == AnomalySeverity.HIGH

    def test_storage_no_backup(self):
        """Storage without backups should be HIGH."""
        g = InfraGraph()
        g.add_component(Component(
            id="s3", name="S3 Storage", type=ComponentType.STORAGE,
            security=SecurityProfile(backup_enabled=False),
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_security_anomalies(g)
        backup_issues = [a for a in anomalies if "backup" in a.description.lower()]
        assert len(backup_issues) == 1

    def test_app_server_no_backup_not_flagged(self):
        """App server without backup should NOT flag a backup issue (only DB/Storage)."""
        g = InfraGraph()
        g.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            security=SecurityProfile(backup_enabled=False, log_enabled=True),
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_security_anomalies(g)
        backup_issues = [a for a in anomalies if "backup" in a.description.lower()]
        assert len(backup_issues) == 0

    def test_security_anomaly_id_format(self):
        """Security anomaly IDs should follow naming pattern."""
        g = InfraGraph()
        g.add_component(Component(
            id="db1", name="DB1", type=ComponentType.DATABASE,
            security=SecurityProfile(encryption_at_rest=False),
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_security_anomalies(g)
        encrypt = [a for a in anomalies if "encryption" in a.description.lower()]
        assert encrypt[0].id == "security_anomaly-encrypt-db1"


# ===========================================================================
# Tests: detect_dependency_anomalies
# ===========================================================================


class TestDependencyAnomalies:
    """Tests for dependency relationship anomaly detection."""

    def test_external_api_without_circuit_breaker(self):
        """Dependency on external API without CB should be flagged HIGH."""
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("ext", "External API", ComponentType.EXTERNAL_API))
        g.add_dependency(Dependency(
            source_id="app", target_id="ext", dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=False),
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_dependency_anomalies(g)
        cb_issues = [a for a in anomalies if "circuit breaker" in a.description.lower()]
        assert len(cb_issues) == 1
        assert cb_issues[0].severity == AnomalySeverity.HIGH

    def test_external_api_with_circuit_breaker_no_flag(self):
        """Dependency on external API with CB should not flag."""
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("ext", "External API", ComponentType.EXTERNAL_API))
        g.add_dependency(Dependency(
            source_id="app", target_id="ext", dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_dependency_anomalies(g)
        cb_issues = [a for a in anomalies if "circuit breaker" in a.description.lower()]
        assert len(cb_issues) == 0

    def test_single_required_dependency_no_redundancy(self):
        """Component with single required dep that has no redundancy should flag."""
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=1, failover=False))
        g.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        detector = AnomalyDetector(min_replicas_for_critical=2)
        anomalies = detector.detect_dependency_anomalies(g)
        single = [a for a in anomalies if "single" in a.description.lower()]
        assert len(single) == 1
        assert single[0].severity == AnomalySeverity.MEDIUM

    def test_single_required_dependency_with_redundancy_no_flag(self):
        """Single required dep with replicas >= min should not flag."""
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=3, failover=True))
        g.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        detector = AnomalyDetector(min_replicas_for_critical=2)
        anomalies = detector.detect_dependency_anomalies(g)
        single = [a for a in anomalies if "single" in a.description.lower()]
        assert len(single) == 0

    def test_multiple_required_deps_no_single_flag(self):
        """Component with multiple required deps should not flag single-dep."""
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("db1", "DB1", ComponentType.DATABASE, replicas=1))
        g.add_component(_comp("db2", "DB2", ComponentType.DATABASE, replicas=1))
        g.add_dependency(Dependency(source_id="app", target_id="db1", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="app", target_id="db2", dependency_type="requires"))
        detector = AnomalyDetector()
        anomalies = detector.detect_dependency_anomalies(g)
        single = [a for a in anomalies if "single" in a.description.lower()]
        assert len(single) == 0

    def test_no_dependencies_no_flag(self):
        """Component with no dependencies should produce no dependency anomalies."""
        g = InfraGraph()
        g.add_component(_comp("standalone", "Standalone"))
        detector = AnomalyDetector()
        anomalies = detector.detect_dependency_anomalies(g)
        assert len(anomalies) == 0

    def test_optional_dependency_not_counted_as_required(self):
        """Optional dependency should not be counted as 'required' for single-dep check."""
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("cache", "Cache", ComponentType.CACHE, replicas=1))
        g.add_dependency(Dependency(
            source_id="app", target_id="cache", dependency_type="optional",
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_dependency_anomalies(g)
        single = [a for a in anomalies if "single" in a.description.lower()]
        # No required deps at all, so no single-dep flag
        assert len(single) == 0


# ===========================================================================
# Tests: Full detect() pipeline
# ===========================================================================


class TestFullDetect:
    """Tests for the full detect() aggregation."""

    def test_empty_graph_report(self, empty_graph):
        """Empty graph should produce a clean report."""
        detector = AnomalyDetector()
        report = detector.detect(empty_graph)
        assert isinstance(report, AnomalyReport)
        assert report.total_count == 0
        assert report.critical_count == 0
        assert report.high_count == 0
        assert report.health_score == 100.0
        assert report.risk_areas == []
        assert report.top_recommendations == []
        assert len(report.anomalies) == 0

    def test_healthy_graph_high_health_score(self, healthy_graph):
        """Well-configured graph should have a high health score."""
        detector = AnomalyDetector()
        report = detector.detect(healthy_graph)
        # May have some minor anomalies but health score should be decent
        assert report.health_score >= 50.0

    def test_spof_graph_has_anomalies(self, spof_graph):
        """SPOF graph should produce multiple anomalies."""
        detector = AnomalyDetector()
        report = detector.detect(spof_graph)
        assert report.total_count > 0
        assert len(report.anomalies) == report.total_count

    def test_critical_count_accurate(self):
        """Critical count should match actual CRITICAL anomalies."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN))
        detector = AnomalyDetector()
        report = detector.detect(g)
        actual_critical = sum(
            1 for a in report.anomalies if a.severity == AnomalySeverity.CRITICAL
        )
        assert report.critical_count == actual_critical

    def test_high_count_accurate(self):
        """High count should match actual HIGH anomalies."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", health=HealthStatus.DEGRADED))
        detector = AnomalyDetector()
        report = detector.detect(g)
        actual_high = sum(
            1 for a in report.anomalies if a.severity == AnomalySeverity.HIGH
        )
        assert report.high_count == actual_high

    def test_health_score_decreases_with_critical(self):
        """Health score should decrease with CRITICAL anomalies (-15 each)."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN))
        detector = AnomalyDetector()
        report = detector.detect(g)
        assert report.health_score < 100.0

    def test_health_score_never_negative(self):
        """Health score should never go below 0."""
        g = InfraGraph()
        # Add many unhealthy components to drive score negative before clamping
        for i in range(20):
            g.add_component(_comp(
                f"db{i}", f"DB {i}", ComponentType.DATABASE,
                health=HealthStatus.DOWN,
            ))
        detector = AnomalyDetector()
        report = detector.detect(g)
        assert report.health_score >= 0.0

    def test_risk_areas_deduplicated(self):
        """Risk areas should be deduplicated anomaly type values."""
        g = InfraGraph()
        g.add_component(Component(
            id="db1", name="DB1", type=ComponentType.DATABASE,
            security=SecurityProfile(encryption_at_rest=False, log_enabled=False),
        ))
        g.add_component(Component(
            id="db2", name="DB2", type=ComponentType.DATABASE,
            security=SecurityProfile(encryption_at_rest=False, log_enabled=False),
        ))
        detector = AnomalyDetector()
        report = detector.detect(g)
        # Should not have duplicate risk areas
        assert len(report.risk_areas) == len(set(report.risk_areas))

    def test_top_recommendations_max_5(self):
        """Top recommendations should have at most 5 entries."""
        g = InfraGraph()
        # Add many components to generate many anomalies
        for i in range(10):
            g.add_component(Component(
                id=f"db{i}", name=f"DB {i}", type=ComponentType.DATABASE,
                security=SecurityProfile(encryption_at_rest=False, log_enabled=False, backup_enabled=False),
            ))
        detector = AnomalyDetector()
        report = detector.detect(g)
        assert len(report.top_recommendations) <= 5

    def test_top_recommendations_from_highest_severity(self):
        """Top recommendations should prioritize highest severity anomalies."""
        g = InfraGraph()
        # CRITICAL: DB without encryption
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            security=SecurityProfile(encryption_at_rest=False, log_enabled=True, backup_enabled=True),
        ))
        # LOW: idle component
        g.add_component(_comp("idle", "Idle", replicas=3))
        detector = AnomalyDetector()
        report = detector.detect(g)
        if report.top_recommendations:
            # First recommendation should come from a high-severity anomaly
            # (encryption is CRITICAL)
            assert len(report.top_recommendations) >= 1

    def test_top_recommendations_deduplicated(self):
        """Top recommendations should not have duplicates."""
        g = InfraGraph()
        for i in range(5):
            g.add_component(Component(
                id=f"db{i}", name=f"DB {i}", type=ComponentType.DATABASE,
                security=SecurityProfile(encryption_at_rest=False),
            ))
        detector = AnomalyDetector()
        report = detector.detect(g)
        assert len(report.top_recommendations) == len(set(report.top_recommendations))


# ===========================================================================
# Tests: AnomalyReport fields
# ===========================================================================


class TestAnomalyReportFields:
    """Tests for AnomalyReport data class fields."""

    def test_default_report(self):
        """Default AnomalyReport should have sensible defaults."""
        report = AnomalyReport()
        assert report.anomalies == []
        assert report.total_count == 0
        assert report.critical_count == 0
        assert report.high_count == 0
        assert report.health_score == 100.0
        assert report.risk_areas == []
        assert report.top_recommendations == []


# ===========================================================================
# Tests: Anomaly data class
# ===========================================================================


class TestAnomalyDataClass:
    """Tests for the Anomaly data class."""

    def test_anomaly_fields(self):
        a = Anomaly(
            id="utilization_spike-db",
            anomaly_type=AnomalyType.UTILIZATION_SPIKE,
            severity=AnomalySeverity.CRITICAL,
            component_id="db",
            component_name="PostgreSQL",
            description="High utilization",
            metric_value=95.0,
            expected_range="0-80%",
            confidence=0.95,
            recommendation="Scale up",
        )
        assert a.id == "utilization_spike-db"
        assert a.anomaly_type == AnomalyType.UTILIZATION_SPIKE
        assert a.severity == AnomalySeverity.CRITICAL
        assert a.metric_value == 95.0
        assert a.confidence == 0.95


# ===========================================================================
# Tests: Enum values
# ===========================================================================


class TestEnumValues:
    """Tests for enum value consistency."""

    def test_anomaly_type_values(self):
        """All AnomalyType values should be lowercase snake_case."""
        for t in AnomalyType:
            assert t.value == t.value.lower()

    def test_severity_values(self):
        """All AnomalySeverity values should be lowercase."""
        for s in AnomalySeverity:
            assert s.value == s.value.lower()

    def test_anomaly_type_string_enum(self):
        """AnomalyType should be usable as a string."""
        assert AnomalyType.UTILIZATION_SPIKE == "utilization_spike"

    def test_severity_string_enum(self):
        """AnomalySeverity should be usable as a string."""
        assert AnomalySeverity.CRITICAL == "critical"


# ===========================================================================
# Tests: Custom thresholds
# ===========================================================================


class TestCustomThresholds:
    """Tests for custom threshold configurations."""

    def test_custom_utilization_threshold(self):
        """Detector should respect custom utilization threshold."""
        g = InfraGraph()
        g.add_component(Component(
            id="s", name="S", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(cpu_percent=60.0),
        ))
        # Threshold 50 -> should flag
        d1 = AnomalyDetector(utilization_threshold=50.0)
        assert len(d1.detect_utilization_anomalies(g)) > 0
        # Threshold 70 -> should not flag
        d2 = AnomalyDetector(utilization_threshold=70.0)
        assert len(d2.detect_utilization_anomalies(g)) == 0

    def test_custom_depth_threshold(self):
        """Detector should respect custom dependency depth threshold."""
        g = InfraGraph()
        for i in range(6):
            g.add_component(_comp(f"c{i}", f"C{i}"))
        for i in range(5):
            g.add_dependency(Dependency(source_id=f"c{i}", target_id=f"c{i+1}"))
        # Threshold 3 -> should flag (chain of 6)
        d1 = AnomalyDetector(dependency_depth_threshold=3)
        deep1 = [a for a in d1.detect_topology_anomalies(g) if "depth" in a.description.lower()]
        assert len(deep1) >= 1
        # Threshold 10 -> should not flag
        d2 = AnomalyDetector(dependency_depth_threshold=10)
        deep2 = [a for a in d2.detect_topology_anomalies(g) if "depth" in a.description.lower()]
        assert len(deep2) == 0

    def test_custom_min_replicas(self):
        """Detector should respect custom min_replicas_for_critical."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2, failover=True))
        # min_replicas=3 -> should flag
        d1 = AnomalyDetector(min_replicas_for_critical=3)
        rep1 = [
            a for a in d1.detect_configuration_anomalies(g)
            if "replica" in a.description.lower()
        ]
        assert len(rep1) >= 1
        # min_replicas=2 -> should not flag
        d2 = AnomalyDetector(min_replicas_for_critical=2)
        rep2 = [
            a for a in d2.detect_configuration_anomalies(g)
            if "replica" in a.description.lower()
        ]
        assert len(rep2) == 0


# ===========================================================================
# Tests: Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge case tests."""

    def test_all_detection_methods_return_lists(self):
        """All detection methods should return lists even on empty graph."""
        g = InfraGraph()
        detector = AnomalyDetector()
        assert isinstance(detector.detect_utilization_anomalies(g), list)
        assert isinstance(detector.detect_health_anomalies(g), list)
        assert isinstance(detector.detect_topology_anomalies(g), list)
        assert isinstance(detector.detect_configuration_anomalies(g), list)
        assert isinstance(detector.detect_security_anomalies(g), list)
        assert isinstance(detector.detect_dependency_anomalies(g), list)

    def test_confidence_range_all_anomalies(self, spof_graph):
        """All confidence values should be between 0 and 1."""
        detector = AnomalyDetector()
        report = detector.detect(spof_graph)
        for a in report.anomalies:
            assert 0.0 <= a.confidence <= 1.0, (
                f"Confidence {a.confidence} out of range for {a.id}"
            )

    def test_all_anomalies_have_recommendations(self, spof_graph):
        """All anomalies should have non-empty recommendations."""
        detector = AnomalyDetector()
        report = detector.detect(spof_graph)
        for a in report.anomalies:
            assert a.recommendation, f"Missing recommendation for {a.id}"

    def test_all_anomalies_have_ids(self, spof_graph):
        """All anomalies should have non-empty IDs."""
        detector = AnomalyDetector()
        report = detector.detect(spof_graph)
        for a in report.anomalies:
            assert a.id, f"Missing ID for anomaly on {a.component_id}"

    def test_single_component_graph(self, single_component_graph):
        """Single component graph should handle gracefully."""
        detector = AnomalyDetector()
        report = detector.detect(single_component_graph)
        assert isinstance(report, AnomalyReport)
        # Should still find some anomalies (e.g., no logging)
        assert report.health_score <= 100.0
