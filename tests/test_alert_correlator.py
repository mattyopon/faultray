"""Tests for alert correlator."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.alert_correlator import (
    Alert,
    AlertCluster,
    AlertCorrelator,
    AlertSeverity,
    AlertStatus,
    CorrelationReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 15, 12, 0, 0)


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


def _alert(
    aid: str,
    cid: str,
    severity: AlertSeverity = AlertSeverity.HIGH,
    title: str = "Alert",
    ts: datetime | None = None,
) -> Alert:
    return Alert(
        id=aid,
        component_id=cid,
        severity=severity,
        title=title,
        description=f"Alert on {cid}",
        timestamp=ts or _NOW,
    )


def _chain_graph() -> InfraGraph:
    """lb -> api -> db"""
    g = InfraGraph()
    g.add_component(_comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER))
    g.add_component(_comp("api", "API Server"))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_severity_values(self):
        assert AlertSeverity.CRITICAL.value == "critical"
        assert AlertSeverity.INFO.value == "info"

    def test_status_values(self):
        assert AlertStatus.ACTIVE.value == "active"
        assert AlertStatus.SUPPRESSED.value == "suppressed"


# ---------------------------------------------------------------------------
# Tests: Alert management
# ---------------------------------------------------------------------------


class TestAlertManagement:
    def test_add_alert(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "api"))
        assert len(corr.get_alerts()) == 1

    def test_add_alerts(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alerts([_alert("a1", "api"), _alert("a2", "db")])
        assert len(corr.get_alerts()) == 2


# ---------------------------------------------------------------------------
# Tests: Empty correlate
# ---------------------------------------------------------------------------


class TestEmptyCorrelate:
    def test_no_alerts(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        report = corr.correlate()
        assert report.total_alerts == 0
        assert len(report.clusters) == 0
        assert report.noise_reduction_percent == 0


# ---------------------------------------------------------------------------
# Tests: Single alert
# ---------------------------------------------------------------------------


class TestSingleAlert:
    def test_single_alert_one_cluster(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "db"))
        report = corr.correlate()
        assert report.total_alerts == 1
        assert len(report.clusters) == 1

    def test_single_alert_confidence(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "db"))
        report = corr.correlate()
        assert report.clusters[0].confidence == 0.5  # single alert = low confidence


# ---------------------------------------------------------------------------
# Tests: Correlated alerts (dependency chain)
# ---------------------------------------------------------------------------


class TestCorrelatedAlerts:
    def test_dependent_alerts_clustered(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        # db fails, api alerts (api depends on db → correlated)
        corr.add_alerts([
            _alert("a1", "db", AlertSeverity.CRITICAL, ts=_NOW),
            _alert("a2", "api", AlertSeverity.HIGH, ts=_NOW + timedelta(minutes=2)),
        ])
        report = corr.correlate()
        assert len(report.clusters) == 1
        assert len(report.clusters[0].alerts) == 2

    def test_root_cause_identified(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alerts([
            _alert("a1", "db", AlertSeverity.CRITICAL, ts=_NOW),
            _alert("a2", "api", AlertSeverity.HIGH, ts=_NOW + timedelta(minutes=2)),
        ])
        report = corr.correlate()
        # db is the dependency that api depends on → root cause
        assert report.clusters[0].root_cause_component == "db"

    def test_noise_reduction(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alerts([
            _alert("a1", "db", AlertSeverity.CRITICAL, ts=_NOW),
            _alert("a2", "api", AlertSeverity.HIGH, ts=_NOW + timedelta(minutes=1)),
        ])
        report = corr.correlate()
        assert report.noise_reduction_percent > 0
        assert report.suppressed_count >= 1  # 2 alerts → 1 cluster → 1 suppressed


# ---------------------------------------------------------------------------
# Tests: Uncorrelated alerts
# ---------------------------------------------------------------------------


class TestUncorrelatedAlerts:
    def test_time_separated_not_clustered(self):
        g = _chain_graph()
        corr = AlertCorrelator(g, time_window_minutes=5)
        corr.add_alerts([
            _alert("a1", "db", ts=_NOW),
            _alert("a2", "api", ts=_NOW + timedelta(hours=1)),
        ])
        report = corr.correlate()
        # Time difference > 5min window → not correlated
        assert len(report.clusters) == 2

    def test_unrelated_components_not_clustered(self):
        g = InfraGraph()
        g.add_component(_comp("a", "Service A"))
        g.add_component(_comp("b", "Service B"))
        # No dependency between a and b
        corr = AlertCorrelator(g)
        corr.add_alerts([
            _alert("a1", "a", ts=_NOW),
            _alert("a2", "b", ts=_NOW),
        ])
        report = corr.correlate()
        assert len(report.clusters) == 2


# ---------------------------------------------------------------------------
# Tests: Shared dependency correlation
# ---------------------------------------------------------------------------


class TestSharedDependency:
    def test_shared_dep_clustered(self):
        g = InfraGraph()
        g.add_component(_comp("db", "Database", ComponentType.DATABASE))
        g.add_component(_comp("api1", "API-1"))
        g.add_component(_comp("api2", "API-2"))
        g.add_dependency(Dependency(source_id="api1", target_id="db"))
        g.add_dependency(Dependency(source_id="api2", target_id="db"))

        corr = AlertCorrelator(g)
        corr.add_alerts([
            _alert("a1", "api1", ts=_NOW),
            _alert("a2", "api2", ts=_NOW + timedelta(minutes=1)),
        ])
        report = corr.correlate()
        # api1 and api2 share dependency on db → correlated
        assert len(report.clusters) == 1


# ---------------------------------------------------------------------------
# Tests: find_root_cause
# ---------------------------------------------------------------------------


class TestFindRootCause:
    def test_root_cause_is_alerting_dependency(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "db"))
        root = corr.find_root_cause("api")
        assert root == "db"

    def test_root_cause_is_self_when_no_dep_alerting(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "api"))
        root = corr.find_root_cause("api")
        assert root == "api"

    def test_root_cause_nonexistent(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        assert corr.find_root_cause("nope") is None


# ---------------------------------------------------------------------------
# Tests: Cluster properties
# ---------------------------------------------------------------------------


class TestClusterProperties:
    def test_cluster_severity(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alerts([
            _alert("a1", "db", AlertSeverity.CRITICAL),
            _alert("a2", "api", AlertSeverity.LOW),
        ])
        report = corr.correlate()
        assert report.clusters[0].severity == AlertSeverity.CRITICAL

    def test_cluster_affected_components(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alerts([
            _alert("a1", "db"),
            _alert("a2", "api"),
        ])
        report = corr.correlate()
        affected = report.clusters[0].affected_components
        assert "db" in affected
        assert "api" in affected

    def test_cluster_id(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "api"))
        report = corr.correlate()
        assert report.clusters[0].cluster_id.startswith("cluster-")

    def test_confidence_increases_with_alerts(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alerts([
            _alert("a1", "db", ts=_NOW),
            _alert("a2", "api", ts=_NOW + timedelta(minutes=1)),
            _alert("a3", "lb", ts=_NOW + timedelta(minutes=2)),
        ])
        report = corr.correlate()
        assert report.clusters[0].confidence > 0.5


# ---------------------------------------------------------------------------
# Tests: Report
# ---------------------------------------------------------------------------


class TestReport:
    def test_report_root_causes(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "db"))
        report = corr.correlate()
        assert len(report.root_causes) >= 1

    def test_report_recommendations(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "api"))
        report = corr.correlate()
        assert len(report.top_recommendations) >= 1

    def test_recommendations_for_down_component(self):
        g = InfraGraph()
        g.add_component(_comp("db", "Database", ComponentType.DATABASE, health=HealthStatus.DOWN))
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "db", AlertSeverity.CRITICAL))
        report = corr.correlate()
        assert any("Restart" in r or "failover" in r.lower() for r in report.top_recommendations)

    def test_recommendations_for_overloaded(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", health=HealthStatus.OVERLOADED))
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "api"))
        report = corr.correlate()
        assert any("scale" in r.lower() or "Scale" in r for r in report.top_recommendations)


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_duplicate_component_alerts(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alerts([
            _alert("a1", "api", ts=_NOW),
            _alert("a2", "api", ts=_NOW + timedelta(minutes=1)),
        ])
        report = corr.correlate()
        assert len(report.clusters) == 1  # same component → correlated

    def test_alert_on_unknown_component(self):
        g = _chain_graph()
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "unknown_service"))
        report = corr.correlate()
        assert report.total_alerts == 1

    def test_custom_time_window(self):
        g = _chain_graph()
        corr = AlertCorrelator(g, time_window_minutes=1)
        corr.add_alerts([
            _alert("a1", "db", ts=_NOW),
            _alert("a2", "api", ts=_NOW + timedelta(minutes=3)),
        ])
        report = corr.correlate()
        # 3 min apart with 1 min window → not correlated
        assert len(report.clusters) == 2

    def test_alert_fields(self):
        a = Alert(
            id="test",
            component_id="api",
            severity=AlertSeverity.HIGH,
            title="Test Alert",
            description="Test",
            timestamp=_NOW,
            status=AlertStatus.ACTIVE,
            metric_value=95.5,
        )
        assert a.metric_value == 95.5
        assert a.status == AlertStatus.ACTIVE


# ---------------------------------------------------------------------------
# Tests: _are_correlated — b is a dependency of a (line 233)
# ---------------------------------------------------------------------------


class TestCorrelationByDependency:
    def test_b_is_dependency_of_a(self):
        """When alert B's component is a dependency of alert A's component,
        they should be correlated (line 233: b.component_id in a_deps)."""
        g = InfraGraph()
        g.add_component(_comp("api", "API Server"))
        g.add_component(_comp("db", "Database", ComponentType.DATABASE))
        # api depends on db
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        corr = AlertCorrelator(g)
        # Alert on api first, then on db. api depends on db, so
        # when checking api vs db: a_deps={db}, b.component_id=db → True
        corr.add_alerts([
            _alert("a1", "api", AlertSeverity.CRITICAL, ts=_NOW),
            _alert("a2", "db", AlertSeverity.HIGH, ts=_NOW + timedelta(minutes=1)),
        ])
        report = corr.correlate()
        # Both should be in the same cluster
        assert len(report.clusters) == 1
        assert len(report.clusters[0].alerts) == 2


# ---------------------------------------------------------------------------
# Tests: _infer_cause branches (lines 275, 280)
# ---------------------------------------------------------------------------


class TestInferCauseBranches:
    def test_degraded_component_cause(self):
        """DEGRADED component should produce degraded cause message (line 275)."""
        g = InfraGraph()
        g.add_component(_comp("api", "API Server", health=HealthStatus.DEGRADED))
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "api", AlertSeverity.HIGH))
        report = corr.correlate()
        assert "degraded" in report.clusters[0].probable_cause.lower()
        assert "impacting" in report.clusters[0].probable_cause.lower()

    def test_many_alerts_infrastructure_issue(self):
        """More than 3 alerts on a HEALTHY component should trigger the
        infrastructure issue cause (line 280)."""
        g = InfraGraph()
        g.add_component(_comp("api", "API Server", health=HealthStatus.HEALTHY))
        corr = AlertCorrelator(g)
        # Add 5 alerts on same component (all within time window)
        for i in range(5):
            corr.add_alert(_alert(
                f"a{i}", "api", AlertSeverity.MEDIUM,
                ts=_NOW + timedelta(minutes=i),
            ))
        report = corr.correlate()
        # All alerts on same component → single cluster with > 3 alerts
        assert len(report.clusters) == 1
        assert len(report.clusters[0].alerts) > 3
        assert "infrastructure issue" in report.clusters[0].probable_cause.lower()


# ---------------------------------------------------------------------------
# Tests: _recommend_action branches (lines 292, 297, 303)
# ---------------------------------------------------------------------------


class TestRecommendActionBranches:
    def test_down_with_failover_enabled(self):
        """DOWN component with failover enabled should recommend verifying
        failover activation (line 292)."""
        g = InfraGraph()
        g.add_component(_comp("db", "Database", ComponentType.DATABASE,
                              health=HealthStatus.DOWN, failover=True))
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "db", AlertSeverity.CRITICAL))
        report = corr.correlate()
        action = report.clusters[0].recommended_action
        assert "failover" in action.lower()
        assert "Verify" in action

    def test_overloaded_with_autoscaling(self):
        """OVERLOADED component with autoscaling enabled should recommend
        checking autoscaling (line 297)."""
        g = InfraGraph()
        c = Component(id="api", name="API Server", type=ComponentType.APP_SERVER,
                      replicas=2)
        c.health = HealthStatus.OVERLOADED
        c.autoscaling.enabled = True
        g.add_component(c)
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "api", AlertSeverity.HIGH))
        report = corr.correlate()
        action = report.clusters[0].recommended_action
        assert "autoscaling" in action.lower()
        assert "max instances" in action.lower()

    def test_healthy_with_multiple_replicas(self):
        """HEALTHY component with replicas > 1 should get 'Investigate' action
        (line 303 — the final fallback)."""
        g = InfraGraph()
        g.add_component(_comp("api", "API Server", replicas=3,
                              health=HealthStatus.HEALTHY))
        corr = AlertCorrelator(g)
        corr.add_alert(_alert("a1", "api", AlertSeverity.MEDIUM))
        report = corr.correlate()
        action = report.clusters[0].recommended_action
        assert "Investigate" in action
        assert "logs and metrics" in action
