"""Tests for the Statistical Anomaly Detector."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
    SecurityProfile,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.anomaly_detector import (
    Anomaly,
    AnomalyDetector,
    AnomalyReport,
    AnomalyType,
    _iqr_bounds,
    _mean,
    _quartiles,
    _std_dev,
    _z_score,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def spof_graph() -> InfraGraph:
    """Graph with an obvious SPOF: single-replica DB with many dependents."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=3,
    ))
    graph.add_component(Component(
        id="app1", name="App Server 1", type=ComponentType.APP_SERVER,
        replicas=3,
    ))
    graph.add_component(Component(
        id="app2", name="App Server 2", type=ComponentType.APP_SERVER,
        replicas=3,
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app1", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="lb", target_id="app2", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app1", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app2", target_id="db", dependency_type="requires"))
    return graph


@pytest.fixture
def healthy_graph() -> InfraGraph:
    """Well-configured graph with consistent settings."""
    graph = InfraGraph()
    for i, (name, ctype) in enumerate([
        ("LB", ComponentType.LOAD_BALANCER),
        ("App", ComponentType.APP_SERVER),
        ("DB", ComponentType.DATABASE),
    ]):
        graph.add_component(Component(
            id=name.lower(), name=name, type=ctype,
            replicas=3,
            failover=FailoverConfig(enabled=True),
            autoscaling=AutoScalingConfig(enabled=True),
        ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return graph


@pytest.fixture
def inconsistent_graph() -> InfraGraph:
    """Graph with inconsistent configurations across similar components."""
    graph = InfraGraph()
    # Three app servers, only 2 have failover
    graph.add_component(Component(
        id="app1", name="App Server 1", type=ComponentType.APP_SERVER,
        replicas=3, failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app2", name="App Server 2", type=ComponentType.APP_SERVER,
        replicas=3, failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app3", name="App Server 3", type=ComponentType.APP_SERVER,
        replicas=3, failover=FailoverConfig(enabled=False),  # inconsistent
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=2,
    ))
    graph.add_dependency(Dependency(source_id="app1", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app2", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app3", target_id="db", dependency_type="requires"))
    return graph


@pytest.fixture
def utilization_graph() -> InfraGraph:
    """Graph with varied utilization levels."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app1", name="App Normal", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=50.0),
    ))
    graph.add_component(Component(
        id="app2", name="App Normal 2", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=55.0),
    ))
    graph.add_component(Component(
        id="app3", name="App Normal 3", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=45.0),
    ))
    graph.add_component(Component(
        id="app_hot", name="App Hot", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=95.0),  # outlier
    ))
    return graph


@pytest.fixture
def orphan_graph() -> InfraGraph:
    """Graph with an orphan component (no connections)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=2,
    ))
    graph.add_component(Component(
        id="orphan", name="Orphan Service", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


@pytest.fixture
def empty_graph() -> InfraGraph:
    return InfraGraph()


@pytest.fixture
def security_inconsistent_graph() -> InfraGraph:
    """Graph with inconsistent security settings."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app1", name="App 1", type=ComponentType.APP_SERVER,
        replicas=2,
        security=SecurityProfile(encryption_at_rest=True, backup_enabled=True),
    ))
    graph.add_component(Component(
        id="app2", name="App 2", type=ComponentType.APP_SERVER,
        replicas=2,
        security=SecurityProfile(encryption_at_rest=True, backup_enabled=True),
    ))
    graph.add_component(Component(
        id="app3", name="App 3", type=ComponentType.APP_SERVER,
        replicas=2,
        security=SecurityProfile(encryption_at_rest=False, backup_enabled=False),  # inconsistent
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests: Statistics helpers
# ---------------------------------------------------------------------------


class TestStatisticsHelpers:
    """Tests for basic statistics functions."""

    def test_mean_basic(self):
        assert _mean([1.0, 2.0, 3.0]) == 2.0

    def test_mean_single(self):
        assert _mean([5.0]) == 5.0

    def test_mean_empty(self):
        assert _mean([]) == 0.0

    def test_std_dev_basic(self):
        std = _std_dev([1.0, 2.0, 3.0, 4.0, 5.0])
        assert abs(std - 1.4142) < 0.01  # sqrt(2) for population std dev

    def test_std_dev_uniform(self):
        assert _std_dev([5.0, 5.0, 5.0]) == 0.0

    def test_std_dev_single(self):
        assert _std_dev([5.0]) == 0.0

    def test_z_score_basic(self):
        z = _z_score(5.0, 3.0, 1.0)
        assert z == 2.0

    def test_z_score_negative(self):
        z = _z_score(1.0, 3.0, 1.0)
        assert z == -2.0

    def test_z_score_zero_std(self):
        z = _z_score(5.0, 3.0, 0.0)
        assert z == 0.0

    def test_quartiles_basic(self):
        q1, q2, q3 = _quartiles([1.0, 2.0, 3.0, 4.0, 5.0])
        assert q1 == 2.0
        assert q2 == 3.0
        assert q3 == 4.0

    def test_quartiles_empty(self):
        q1, q2, q3 = _quartiles([])
        assert q1 == 0.0
        assert q2 == 0.0
        assert q3 == 0.0

    def test_iqr_bounds(self):
        lower, upper = _iqr_bounds([1.0, 2.0, 3.0, 4.0, 5.0])
        iqr = 4.0 - 2.0  # Q3 - Q1
        assert lower == 2.0 - 1.5 * iqr
        assert upper == 4.0 + 1.5 * iqr


# ---------------------------------------------------------------------------
# Tests: AnomalyDetector
# ---------------------------------------------------------------------------


class TestAnomalyDetector:
    """Tests for the AnomalyDetector class."""

    def test_detect_empty_graph(self, empty_graph):
        detector = AnomalyDetector()
        report = detector.detect(empty_graph)
        assert isinstance(report, AnomalyReport)
        assert report.total_components_analyzed == 0
        assert len(report.anomalies) == 0

    def test_detect_spof_graph(self, spof_graph):
        detector = AnomalyDetector()
        report = detector.detect(spof_graph)
        assert report.total_components_analyzed == 4
        assert len(report.anomalies) > 0

        # Should detect the single-replica DB as an anomaly
        db_anomalies = [a for a in report.anomalies if a.component_id == "db"]
        assert len(db_anomalies) > 0

    def test_detect_healthy_graph(self, healthy_graph):
        detector = AnomalyDetector()
        report = detector.detect(healthy_graph)
        # Healthy graph should have fewer anomalies
        critical = [a for a in report.anomalies if a.severity == "critical"]
        assert len(critical) == 0

    def test_detect_report_fields(self, spof_graph):
        detector = AnomalyDetector()
        report = detector.detect(spof_graph)
        assert isinstance(report.total_components_analyzed, int)
        assert isinstance(report.anomaly_rate, float)
        assert isinstance(report.critical_count, int)
        assert isinstance(report.warning_count, int)
        assert isinstance(report.healthiest_components, list)
        assert isinstance(report.most_anomalous_components, list)


# ---------------------------------------------------------------------------
# Tests: Replica anomalies
# ---------------------------------------------------------------------------


class TestReplicaAnomalies:
    """Tests for replica outlier detection."""

    def test_detects_low_replica_outlier(self, spof_graph):
        detector = AnomalyDetector()
        anomalies = detector.detect_replica_anomalies(spof_graph)

        # db has 1 replica while others have 3 - should be flagged
        replica_anomalies = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.REPLICA_OUTLIER
        ]
        assert len(replica_anomalies) >= 1

        # Check that db is flagged
        db_flagged = any(a.component_id == "db" for a in replica_anomalies)
        assert db_flagged

    def test_no_outlier_when_uniform(self):
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"app{i}", name=f"App {i}", type=ComponentType.APP_SERVER,
                replicas=2,
            ))
        detector = AnomalyDetector()
        anomalies = detector.detect_replica_anomalies(graph)
        replica_outliers = [a for a in anomalies if a.anomaly_type == AnomalyType.REPLICA_OUTLIER]
        assert len(replica_outliers) == 0

    def test_under_provisioned_detection(self, spof_graph):
        detector = AnomalyDetector()
        anomalies = detector.detect_replica_anomalies(spof_graph)

        # db has replicas=1 with 2 dependents, no failover
        under_provisioned = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.UNDER_PROVISIONED
            or a.anomaly_type == AnomalyType.REPLICA_OUTLIER
        ]
        db_flagged = any(a.component_id == "db" for a in under_provisioned)
        assert db_flagged


# ---------------------------------------------------------------------------
# Tests: Utilization anomalies
# ---------------------------------------------------------------------------


class TestUtilizationAnomalies:
    """Tests for utilization outlier detection."""

    def test_detects_high_utilization(self, utilization_graph):
        detector = AnomalyDetector()
        anomalies = detector.detect_utilization_anomalies(utilization_graph)

        high_util = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.UTILIZATION_OUTLIER
        ]
        assert len(high_util) >= 1
        assert any(a.component_id == "app_hot" for a in high_util)

    def test_no_outlier_when_uniform_utilization(self):
        graph = InfraGraph()
        for i in range(4):
            graph.add_component(Component(
                id=f"app{i}", name=f"App {i}", type=ComponentType.APP_SERVER,
                replicas=2,
                metrics=ResourceMetrics(cpu_percent=50.0),
            ))
        detector = AnomalyDetector()
        anomalies = detector.detect_utilization_anomalies(graph)
        assert len(anomalies) == 0

    def test_needs_minimum_samples(self):
        """Should need at least 3 non-zero utilization values."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app1", name="App 1", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(cpu_percent=50.0),
        ))
        graph.add_component(Component(
            id="app2", name="App 2", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(cpu_percent=95.0),
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_utilization_anomalies(graph)
        assert len(anomalies) == 0  # Not enough samples


# ---------------------------------------------------------------------------
# Tests: Config inconsistencies
# ---------------------------------------------------------------------------


class TestConfigInconsistencies:
    """Tests for configuration inconsistency detection."""

    def test_detects_failover_inconsistency(self, inconsistent_graph):
        detector = AnomalyDetector()
        anomalies = detector.detect_config_inconsistencies(inconsistent_graph)

        failover_issues = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.CONFIG_INCONSISTENCY
            and "failover" in a.description
        ]
        assert len(failover_issues) >= 1
        assert any(a.component_id == "app3" for a in failover_issues)

    def test_detects_security_inconsistency(self, security_inconsistent_graph):
        detector = AnomalyDetector()
        anomalies = detector.detect_config_inconsistencies(security_inconsistent_graph)

        security_issues = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.SECURITY_INCONSISTENCY
        ]
        assert len(security_issues) >= 1
        assert any(a.component_id == "app3" for a in security_issues)

    def test_no_inconsistency_when_uniform(self, healthy_graph):
        detector = AnomalyDetector()
        anomalies = detector.detect_config_inconsistencies(healthy_graph)

        # Healthy graph has consistent configs - should have fewer issues
        failover_issues = [
            a for a in anomalies
            if "failover" in a.description.lower()
            and a.anomaly_type == AnomalyType.CONFIG_INCONSISTENCY
        ]
        assert len(failover_issues) == 0


# ---------------------------------------------------------------------------
# Tests: Dependency anomalies
# ---------------------------------------------------------------------------


class TestDependencyAnomalies:
    """Tests for dependency graph anomaly detection."""

    def test_detects_orphan_component(self, orphan_graph):
        detector = AnomalyDetector()
        anomalies = detector.detect_dependency_anomalies(orphan_graph)

        orphans = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.DEPENDENCY_ANOMALY
            and "orphan" in a.description.lower()
        ]
        assert len(orphans) >= 1
        assert any(a.component_id == "orphan" for a in orphans)

    def test_detects_hub_component(self):
        """Component with many dependents should be flagged as a hub."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="Central DB", type=ComponentType.DATABASE,
            replicas=1,
        ))
        for i in range(6):
            graph.add_component(Component(
                id=f"app{i}", name=f"App {i}", type=ComponentType.APP_SERVER,
                replicas=2,
            ))
            graph.add_dependency(Dependency(
                source_id=f"app{i}", target_id="db", dependency_type="requires",
            ))
        detector = AnomalyDetector()
        anomalies = detector.detect_dependency_anomalies(graph)

        hubs = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.DEPENDENCY_ANOMALY
            and "hub" in a.description.lower()
        ]
        assert len(hubs) >= 1
        assert any(a.component_id == "db" for a in hubs)


# ---------------------------------------------------------------------------
# Tests: Capacity mismatches
# ---------------------------------------------------------------------------


class TestCapacityMismatches:
    """Tests for capacity mismatch detection."""

    def test_detects_high_fanin_low_capacity(self):
        """Component with many dependents but low replicas."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=1,
        ))
        for i in range(4):
            graph.add_component(Component(
                id=f"app{i}", name=f"App {i}", type=ComponentType.APP_SERVER,
                replicas=3,
            ))
            graph.add_dependency(Dependency(
                source_id=f"app{i}", target_id="db", dependency_type="requires",
            ))

        detector = AnomalyDetector()
        anomalies = detector.detect_capacity_mismatches(graph)
        assert len(anomalies) >= 1
        assert any(
            a.component_id == "db"
            and a.anomaly_type == AnomalyType.CAPACITY_MISMATCH
            for a in anomalies
        )

    def test_no_mismatch_when_balanced(self):
        """Properly scaled components should not trigger."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=3,
        ))
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=3,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))

        detector = AnomalyDetector()
        anomalies = detector.detect_capacity_mismatches(graph)
        # With balanced replicas and only 1 dependent, no mismatch expected
        capacity_issues = [a for a in anomalies if a.anomaly_type == AnomalyType.CAPACITY_MISMATCH]
        assert len(capacity_issues) == 0


# ---------------------------------------------------------------------------
# Tests: Anomaly data class
# ---------------------------------------------------------------------------


class TestAnomalyDataClass:
    """Tests for the Anomaly data class."""

    def test_anomaly_fields(self):
        a = Anomaly(
            anomaly_type=AnomalyType.REPLICA_OUTLIER,
            component_id="db",
            component_name="PostgreSQL",
            severity="critical",
            description="Low replica count",
            expected_value=">= 2",
            actual_value="1",
            z_score=-2.5,
            recommendation="Add replicas",
            confidence=0.85,
        )
        assert a.anomaly_type == AnomalyType.REPLICA_OUTLIER
        assert a.component_id == "db"
        assert a.severity == "critical"
        assert a.z_score == -2.5
        assert a.confidence == 0.85

    def test_anomaly_type_enum_values(self):
        """All enum values should be lowercase snake_case strings."""
        for t in AnomalyType:
            assert t.value == t.value.lower()
            assert "_" in t.value or t.value.isalpha()


# ---------------------------------------------------------------------------
# Tests: Full detection pipeline
# ---------------------------------------------------------------------------


class TestFullDetection:
    """Integration tests for the full detection pipeline."""

    def test_full_report_structure(self, spof_graph):
        detector = AnomalyDetector()
        report = detector.detect(spof_graph)

        assert isinstance(report, AnomalyReport)
        assert report.total_components_analyzed == len(spof_graph.components)
        assert 0 <= report.anomaly_rate <= 100
        assert report.critical_count >= 0
        assert report.warning_count >= 0
        assert isinstance(report.healthiest_components, list)
        assert isinstance(report.most_anomalous_components, list)

    def test_anomaly_confidence_range(self, spof_graph):
        """All confidence values should be between 0 and 1."""
        detector = AnomalyDetector()
        report = detector.detect(spof_graph)
        for a in report.anomalies:
            assert 0.0 <= a.confidence <= 1.0

    def test_anomaly_severity_valid(self, spof_graph):
        """All severity values should be valid."""
        detector = AnomalyDetector()
        report = detector.detect(spof_graph)
        valid_severities = {"critical", "warning", "info"}
        for a in report.anomalies:
            assert a.severity in valid_severities

    def test_anomaly_has_recommendation(self, spof_graph):
        """All anomalies should have a recommendation."""
        detector = AnomalyDetector()
        report = detector.detect(spof_graph)
        for a in report.anomalies:
            assert a.recommendation, f"Missing recommendation for {a.component_id}: {a.description}"

    def test_most_anomalous_ordered(self, spof_graph):
        detector = AnomalyDetector()
        report = detector.detect(spof_graph)
        if len(report.most_anomalous_components) >= 2:
            # Most anomalous should be ordered by anomaly count
            anomaly_counts: dict[str, int] = {}
            for a in report.anomalies:
                anomaly_counts[a.component_id] = anomaly_counts.get(a.component_id, 0) + 1
            for i in range(len(report.most_anomalous_components) - 1):
                c1 = report.most_anomalous_components[i]
                c2 = report.most_anomalous_components[i + 1]
                assert anomaly_counts.get(c1, 0) >= anomaly_counts.get(c2, 0)


# ---------------------------------------------------------------------------
# Additional tests for 99%+ coverage
# ---------------------------------------------------------------------------


class TestReplicaAnomaliesSingleComponent:
    """Cover detect_replica_anomalies with < 2 components (line 201)."""

    def test_replica_anomalies_single_component(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_replica_anomalies(graph)
        assert len(anomalies) == 0  # Not enough components for comparison


class TestReplicaUnderProvisioned:
    """Cover the UNDER_PROVISIONED branch (line 237)."""

    def test_under_provisioned_single_replica_many_dependents(self):
        """Component with replicas=1, >= 2 dependents, no failover,
        but z-score NOT < -1.5 (not a statistical outlier)."""
        graph = InfraGraph()
        # Make a component with replicas=1 that has 2+ dependents
        # but the z-score is NOT < -1.5 (i.e., other components also have low replicas)
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=1,
        ))
        graph.add_component(Component(
            id="app1", name="App1", type=ComponentType.APP_SERVER,
            replicas=1,
        ))
        graph.add_component(Component(
            id="app2", name="App2", type=ComponentType.APP_SERVER,
            replicas=2,
        ))
        graph.add_dependency(Dependency(
            source_id="app1", target_id="db", dependency_type="requires",
        ))
        graph.add_dependency(Dependency(
            source_id="app2", target_id="db", dependency_type="requires",
        ))

        detector = AnomalyDetector()
        anomalies = detector.detect_replica_anomalies(graph)

        # db has replicas=1, num_dependents=2, no failover
        # With replicas [1, 1, 2], mean=1.33, std=0.47
        # z for db = (1 - 1.33) / 0.47 = -0.71 -> NOT < -1.5
        # So it should hit the elif (UNDER_PROVISIONED) branch
        under = [a for a in anomalies if a.anomaly_type == AnomalyType.UNDER_PROVISIONED]
        assert len(under) >= 1
        assert any(a.component_id == "db" for a in under)


class TestUtilizationSkipZero:
    """Cover the util <= 0.0 continue branch (line 277)."""

    def test_skip_zero_utilization_components(self):
        graph = InfraGraph()
        # 3 components with utilization, 1 with zero
        graph.add_component(Component(
            id="app1", name="App1", type=ComponentType.APP_SERVER,
            replicas=2, metrics=ResourceMetrics(cpu_percent=50.0),
        ))
        graph.add_component(Component(
            id="app2", name="App2", type=ComponentType.APP_SERVER,
            replicas=2, metrics=ResourceMetrics(cpu_percent=55.0),
        ))
        graph.add_component(Component(
            id="app3", name="App3", type=ComponentType.APP_SERVER,
            replicas=2, metrics=ResourceMetrics(cpu_percent=45.0),
        ))
        graph.add_component(Component(
            id="no_util", name="NoUtil", type=ComponentType.APP_SERVER,
            replicas=2,
            # No metrics -> utilization = 0.0 -> should be skipped
        ))

        detector = AnomalyDetector()
        anomalies = detector.detect_utilization_anomalies(graph)
        # no_util should not appear in anomalies (skipped at line 277)
        no_util_anomalies = [a for a in anomalies if a.component_id == "no_util"]
        assert len(no_util_anomalies) == 0


class TestUtilizationOverProvisioned:
    """Cover the over-provisioned branch (lines 301-302)."""

    def test_detects_over_provisioned_component(self):
        """Component with very low utilization should be flagged as over-provisioned."""
        graph = InfraGraph()
        # 3 normal components + 1 very low utilization
        graph.add_component(Component(
            id="app1", name="App1", type=ComponentType.APP_SERVER,
            replicas=2, metrics=ResourceMetrics(cpu_percent=70.0),
        ))
        graph.add_component(Component(
            id="app2", name="App2", type=ComponentType.APP_SERVER,
            replicas=2, metrics=ResourceMetrics(cpu_percent=75.0),
        ))
        graph.add_component(Component(
            id="app3", name="App3", type=ComponentType.APP_SERVER,
            replicas=2, metrics=ResourceMetrics(cpu_percent=80.0),
        ))
        graph.add_component(Component(
            id="idle", name="Idle", type=ComponentType.APP_SERVER,
            replicas=2, metrics=ResourceMetrics(cpu_percent=5.0),
        ))

        detector = AnomalyDetector()
        anomalies = detector.detect_utilization_anomalies(graph)

        over_provisioned = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.OVER_PROVISIONED
        ]
        assert len(over_provisioned) >= 1
        assert any(a.component_id == "idle" for a in over_provisioned)


class TestConfigInconsistenciesSingleComponent:
    """Cover detect_config_inconsistencies with < 2 components (line 329)."""

    def test_config_inconsistencies_single_component(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_config_inconsistencies(graph)
        assert len(anomalies) == 0


class TestAutoscalingInconsistency:
    """Cover autoscaling inconsistency detection (lines 373-375)."""

    def test_detects_autoscaling_inconsistency(self):
        """Most components have autoscaling but one doesn't."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app1", name="App1", type=ComponentType.APP_SERVER,
            replicas=2, autoscaling=AutoScalingConfig(enabled=True),
        ))
        graph.add_component(Component(
            id="app2", name="App2", type=ComponentType.APP_SERVER,
            replicas=2, autoscaling=AutoScalingConfig(enabled=True),
        ))
        graph.add_component(Component(
            id="app3", name="App3", type=ComponentType.APP_SERVER,
            replicas=2,
            # No autoscaling - inconsistent with peers
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_config_inconsistencies(graph)
        as_issues = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.CONFIG_INCONSISTENCY
            and "autoscaling" in a.description.lower()
        ]
        assert len(as_issues) >= 1
        assert any(a.component_id == "app3" for a in as_issues)


class TestCircuitBreakerInconsistency:
    """Cover circuit breaker inconsistency detection (lines 402-407)."""

    def test_detects_circuit_breaker_inconsistency(self):
        """Most edges have CB but one doesn't."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app1", name="App1", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="app2", name="App2", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        ))
        # 2 edges with CB, 1 without
        graph.add_dependency(Dependency(
            source_id="app1", target_id="db", dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="app2", target_id="db", dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        graph.add_dependency(Dependency(
            source_id="app1", target_id="app2", dependency_type="optional",
            # No circuit breaker - inconsistent
        ))

        detector = AnomalyDetector()
        anomalies = detector.detect_config_inconsistencies(graph)
        cb_issues = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.CONFIG_INCONSISTENCY
            and "circuit" in a.description.lower()
        ]
        assert len(cb_issues) >= 1


class TestDependencyAnomalyEdgeCases:
    """Cover dependency anomaly edge cases."""

    def test_dependency_anomalies_empty_graph(self):
        """Direct call to detect_dependency_anomalies with empty graph (line 467)."""
        graph = InfraGraph()
        detector = AnomalyDetector()
        anomalies = detector.detect_dependency_anomalies(graph)
        assert len(anomalies) == 0

    def test_dependency_anomalies_uniform_dependents(self):
        """All components have same number of dependents -> std=0 -> z=0 (line 485)."""
        graph = InfraGraph()
        # Create a ring: each has exactly 1 dependent
        for i in range(4):
            graph.add_component(Component(
                id=f"svc{i}", name=f"Service{i}", type=ComponentType.APP_SERVER,
                replicas=2,
            ))
        for i in range(4):
            graph.add_dependency(Dependency(
                source_id=f"svc{i}", target_id=f"svc{(i+1) % 4}",
                dependency_type="requires",
            ))

        detector = AnomalyDetector()
        anomalies = detector.detect_dependency_anomalies(graph)
        # With std=0, no hub should be detected (z=0 for all)
        hubs = [a for a in anomalies if "hub" in a.description.lower()]
        assert len(hubs) == 0


class TestCircularDependencyDetection:
    """Cover circular dependency detection (lines 537-560)."""

    def test_detects_circular_dependency(self):
        """Graph with a cycle should produce circular dependency anomalies."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="ServiceA", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="b", name="ServiceB", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="c", name="ServiceC", type=ComponentType.APP_SERVER, replicas=2,
        ))
        # Create a cycle: a -> b -> c -> a
        graph.add_dependency(Dependency(
            source_id="a", target_id="b", dependency_type="requires",
        ))
        graph.add_dependency(Dependency(
            source_id="b", target_id="c", dependency_type="requires",
        ))
        graph.add_dependency(Dependency(
            source_id="c", target_id="a", dependency_type="requires",
        ))

        detector = AnomalyDetector()
        anomalies = detector.detect_dependency_anomalies(graph)

        circular = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.DEPENDENCY_ANOMALY
            and "circular" in a.description.lower()
        ]
        assert len(circular) >= 1


class TestCapacityMismatchSingleComponent:
    """Cover detect_capacity_mismatches with < 2 components (line 570)."""

    def test_capacity_mismatches_single_component(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        ))
        detector = AnomalyDetector()
        anomalies = detector.detect_capacity_mismatches(graph)
        assert len(anomalies) == 0


class TestCircularDependencyExceptionHandling:
    """Cover the except block in cycle detection (lines 559-560)."""

    def test_cycle_detection_exception_handled(self, monkeypatch):
        """When nx.simple_cycles raises, the exception should be swallowed."""
        from unittest.mock import patch
        import networkx as nx

        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_dependency(Dependency(
            source_id="a", target_id="b", dependency_type="requires",
        ))

        # Mock nx.simple_cycles to raise an exception
        with patch("networkx.simple_cycles", side_effect=RuntimeError("graph error")):
            detector = AnomalyDetector()
            anomalies = detector.detect_dependency_anomalies(graph)

        # Should not raise, and circular anomalies should be empty
        circular = [a for a in anomalies if "circular" in a.description.lower()]
        assert len(circular) == 0
