"""Tests for toil calculator."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.toil_calculator import (
    AutomationPotential,
    ToilCalculator,
    ToilCategory,
    ToilItem,
    ToilReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
    autoscaling: bool = False,
    log_enabled: bool = True,
    backup_enabled: bool = True,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover.enabled = True
    if autoscaling:
        c.autoscaling.enabled = True
    c.security.log_enabled = log_enabled
    c.security.backup_enabled = backup_enabled
    return c


def _chain_graph() -> InfraGraph:
    """lb -> api -> db"""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("api", "API", replicas=3))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_toil_categories(self):
        assert ToilCategory.MANUAL_SCALING.value == "manual_scaling"
        assert ToilCategory.INCIDENT_RESPONSE.value == "incident_response"
        assert ToilCategory.CERT_ROTATION.value == "cert_rotation"

    def test_automation_potential(self):
        assert AutomationPotential.FULLY_AUTOMATABLE.value == "fully_automatable"
        assert AutomationPotential.NOT_AUTOMATABLE.value == "not_automatable"

    def test_all_toil_categories(self):
        assert len(ToilCategory) == 10

    def test_all_automation_levels(self):
        assert len(AutomationPotential) == 4


# ---------------------------------------------------------------------------
# Tests: Empty graph
# ---------------------------------------------------------------------------


class TestEmptyGraph:
    def test_no_components(self):
        g = InfraGraph()
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert report.total_hours_per_month == 0
        assert report.toil_score == 100.0
        assert report.toil_percent == 0
        assert report.automatable_hours == 0
        assert len(report.toil_items) == 0

    def test_empty_recommendations(self):
        g = InfraGraph()
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert report.automation_recommendations == []
        assert report.top_toil_sources == []


# ---------------------------------------------------------------------------
# Tests: Manual scaling detection
# ---------------------------------------------------------------------------


class TestManualScaling:
    def test_no_autoscaling_multi_replica(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3, autoscaling=False))
        calc = ToilCalculator()
        report = calc.analyze(g)
        scaling_items = [i for i in report.toil_items if i.category == ToilCategory.MANUAL_SCALING]
        assert len(scaling_items) == 1
        assert scaling_items[0].automation_potential == AutomationPotential.FULLY_AUTOMATABLE

    def test_autoscaling_enabled_no_toil(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3, autoscaling=True))
        calc = ToilCalculator()
        report = calc.analyze(g)
        scaling_items = [i for i in report.toil_items if i.category == ToilCategory.MANUAL_SCALING]
        assert len(scaling_items) == 0

    def test_single_replica_no_scaling_toil(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=1, autoscaling=False))
        calc = ToilCalculator()
        report = calc.analyze(g)
        scaling_items = [i for i in report.toil_items if i.category == ToilCategory.MANUAL_SCALING]
        assert len(scaling_items) == 0


# ---------------------------------------------------------------------------
# Tests: Manual failover detection
# ---------------------------------------------------------------------------


class TestManualFailover:
    def test_no_failover_with_dependents(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, failover=False))
        g.add_component(_comp("api", "API"))
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        calc = ToilCalculator()
        report = calc.analyze(g)
        failover_items = [i for i in report.toil_items if i.category == ToilCategory.MANUAL_FAILOVER]
        assert len(failover_items) == 1
        assert failover_items[0].priority in ("critical", "high")

    def test_failover_enabled_no_toil(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, failover=True))
        g.add_component(_comp("api", "API"))
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        calc = ToilCalculator()
        report = calc.analyze(g)
        failover_items = [i for i in report.toil_items if i.category == ToilCategory.MANUAL_FAILOVER]
        assert len(failover_items) == 0

    def test_no_dependents_no_failover_toil(self):
        g = InfraGraph()
        g.add_component(_comp("leaf", "Leaf", failover=False))
        calc = ToilCalculator()
        report = calc.analyze(g)
        failover_items = [i for i in report.toil_items if i.category == ToilCategory.MANUAL_FAILOVER]
        assert len(failover_items) == 0

    def test_critical_priority_many_dependents(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, failover=False))
        for i in range(3):
            g.add_component(_comp(f"svc{i}", f"Service{i}"))
            g.add_dependency(Dependency(source_id=f"svc{i}", target_id="db"))
        calc = ToilCalculator()
        report = calc.analyze(g)
        failover_items = [i for i in report.toil_items if i.category == ToilCategory.MANUAL_FAILOVER]
        assert failover_items[0].priority == "critical"


# ---------------------------------------------------------------------------
# Tests: Alert response / incident response
# ---------------------------------------------------------------------------


class TestAlertResponse:
    def test_degraded_generates_alert_toil(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", health=HealthStatus.DEGRADED))
        calc = ToilCalculator()
        report = calc.analyze(g)
        alert_items = [i for i in report.toil_items if i.category == ToilCategory.ALERT_RESPONSE]
        assert len(alert_items) == 1

    def test_overloaded_generates_alert_toil(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", health=HealthStatus.OVERLOADED))
        calc = ToilCalculator()
        report = calc.analyze(g)
        alert_items = [i for i in report.toil_items if i.category == ToilCategory.ALERT_RESPONSE]
        assert len(alert_items) == 1
        assert alert_items[0].automation_potential == AutomationPotential.PARTIALLY_AUTOMATABLE

    def test_down_generates_incident_toil(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", health=HealthStatus.DOWN))
        calc = ToilCalculator()
        report = calc.analyze(g)
        incident_items = [i for i in report.toil_items if i.category == ToilCategory.INCIDENT_RESPONSE]
        assert len(incident_items) == 1
        assert incident_items[0].priority == "critical"
        assert incident_items[0].automation_potential == AutomationPotential.REQUIRES_JUDGMENT

    def test_healthy_no_alert_toil(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", health=HealthStatus.HEALTHY))
        calc = ToilCalculator()
        report = calc.analyze(g)
        alert_items = [i for i in report.toil_items if i.category in (ToilCategory.ALERT_RESPONSE, ToilCategory.INCIDENT_RESPONSE)]
        assert len(alert_items) == 0


# ---------------------------------------------------------------------------
# Tests: Log review
# ---------------------------------------------------------------------------


class TestLogReview:
    def test_no_log_monitoring(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", log_enabled=False))
        calc = ToilCalculator()
        report = calc.analyze(g)
        log_items = [i for i in report.toil_items if i.category == ToilCategory.LOG_REVIEW]
        assert len(log_items) == 1
        assert log_items[0].automation_potential == AutomationPotential.FULLY_AUTOMATABLE

    def test_log_enabled_no_toil(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", log_enabled=True))
        calc = ToilCalculator()
        report = calc.analyze(g)
        log_items = [i for i in report.toil_items if i.category == ToilCategory.LOG_REVIEW]
        assert len(log_items) == 0


# ---------------------------------------------------------------------------
# Tests: Backup verification
# ---------------------------------------------------------------------------


class TestBackupVerification:
    def test_database_no_backup(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, backup_enabled=False))
        calc = ToilCalculator()
        report = calc.analyze(g)
        backup_items = [i for i in report.toil_items if i.category == ToilCategory.BACKUP_VERIFICATION]
        assert len(backup_items) == 1
        assert backup_items[0].automation_savings_percent == 95

    def test_storage_no_backup(self):
        g = InfraGraph()
        g.add_component(_comp("s3", "Storage", ComponentType.STORAGE, backup_enabled=False))
        calc = ToilCalculator()
        report = calc.analyze(g)
        backup_items = [i for i in report.toil_items if i.category == ToilCategory.BACKUP_VERIFICATION]
        assert len(backup_items) == 1

    def test_app_server_no_backup_no_toil(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", ComponentType.APP_SERVER, backup_enabled=False))
        calc = ToilCalculator()
        report = calc.analyze(g)
        backup_items = [i for i in report.toil_items if i.category == ToilCategory.BACKUP_VERIFICATION]
        assert len(backup_items) == 0

    def test_database_with_backup_no_toil(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, backup_enabled=True))
        calc = ToilCalculator()
        report = calc.analyze(g)
        backup_items = [i for i in report.toil_items if i.category == ToilCategory.BACKUP_VERIFICATION]
        assert len(backup_items) == 0


# ---------------------------------------------------------------------------
# Tests: Report calculations
# ---------------------------------------------------------------------------


class TestReportCalculations:
    def test_total_hours(self):
        g = _chain_graph()
        calc = ToilCalculator()
        report = calc.analyze(g)
        expected = sum(i.hours_per_month for i in report.toil_items)
        assert report.total_hours_per_month == round(expected, 1)

    def test_automatable_hours(self):
        g = _chain_graph()
        calc = ToilCalculator()
        report = calc.analyze(g)
        expected = sum(
            i.hours_per_month * (i.automation_savings_percent / 100)
            for i in report.toil_items
        )
        assert report.automatable_hours == round(expected, 1)

    def test_toil_percent(self):
        g = _chain_graph()
        calc = ToilCalculator(monthly_ops_hours=160.0)
        report = calc.analyze(g)
        expected = report.total_hours_per_month / 160.0 * 100
        assert report.toil_percent == round(expected, 1)

    def test_toil_score_decreases_with_toil(self):
        g = _chain_graph()
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert report.toil_score < 100.0

    def test_toil_score_100_for_empty(self):
        g = InfraGraph()
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert report.toil_score == 100.0

    def test_toil_score_minimum_zero(self):
        g = InfraGraph()
        # Add many toil-generating components
        for i in range(20):
            g.add_component(_comp(
                f"svc{i}", f"Service{i}",
                replicas=5, autoscaling=False, failover=False,
                health=HealthStatus.DOWN, log_enabled=False,
            ))
            if i > 0:
                g.add_dependency(Dependency(source_id=f"svc{i}", target_id="svc0"))
        calc = ToilCalculator(monthly_ops_hours=10.0)
        report = calc.analyze(g)
        assert report.toil_score >= 0

    def test_custom_monthly_ops_hours(self):
        g = _chain_graph()
        calc = ToilCalculator(monthly_ops_hours=80.0)
        report = calc.analyze(g)
        expected_pct = report.total_hours_per_month / 80.0 * 100
        assert report.toil_percent == round(expected_pct, 1)

    def test_zero_ops_hours(self):
        g = _chain_graph()
        calc = ToilCalculator(monthly_ops_hours=0)
        report = calc.analyze(g)
        assert report.toil_percent == 0

    def test_items_sorted_by_hours_descending(self):
        g = _chain_graph()
        calc = ToilCalculator()
        report = calc.analyze(g)
        if len(report.toil_items) > 1:
            for i in range(len(report.toil_items) - 1):
                assert report.toil_items[i].hours_per_month >= report.toil_items[i + 1].hours_per_month


# ---------------------------------------------------------------------------
# Tests: Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_recommendations_generated(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3, autoscaling=False, log_enabled=False))
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert len(report.automation_recommendations) >= 1

    def test_fully_automatable_recommendation(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3, autoscaling=False))
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert any("Automate" in r for r in report.automation_recommendations)

    def test_partially_automatable_recommendation(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", health=HealthStatus.DEGRADED))
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert any("Partially" in r or "automate" in r.lower() for r in report.automation_recommendations)

    def test_max_five_recommendations(self):
        g = InfraGraph()
        for i in range(10):
            g.add_component(_comp(
                f"svc{i}", f"Service{i}",
                replicas=3, autoscaling=False, failover=False,
                health=HealthStatus.DEGRADED, log_enabled=False,
            ))
            if i > 0:
                g.add_dependency(Dependency(source_id=f"svc{i}", target_id="svc0"))
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert len(report.automation_recommendations) <= 5

    def test_no_duplicate_category_recommendations(self):
        g = InfraGraph()
        for i in range(5):
            g.add_component(_comp(f"api{i}", f"API{i}", replicas=3, autoscaling=False))
        calc = ToilCalculator()
        report = calc.analyze(g)
        # Only one recommendation per category
        scaling_recs = [r for r in report.automation_recommendations if "manual_scaling" in r]
        assert len(scaling_recs) <= 1


# ---------------------------------------------------------------------------
# Tests: Top toil sources
# ---------------------------------------------------------------------------


class TestTopToilSources:
    def test_top_sources_populated(self):
        g = _chain_graph()
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert len(report.top_toil_sources) >= 1

    def test_top_sources_max_five(self):
        g = InfraGraph()
        for i in range(10):
            g.add_component(_comp(
                f"svc{i}", f"Service{i}",
                replicas=3, autoscaling=False, failover=False,
                health=HealthStatus.DOWN, log_enabled=False,
                backup_enabled=False,
            ))
            if i > 0:
                g.add_dependency(Dependency(source_id=f"svc{i}", target_id="svc0"))
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert len(report.top_toil_sources) <= 5

    def test_top_sources_unique(self):
        g = _chain_graph()
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert len(report.top_toil_sources) == len(set(report.top_toil_sources))


# ---------------------------------------------------------------------------
# Tests: ToilItem dataclass
# ---------------------------------------------------------------------------


class TestToilItem:
    def test_fields(self):
        item = ToilItem(
            component_id="api",
            component_name="API Server",
            category=ToilCategory.MANUAL_SCALING,
            description="Manual scaling needed",
            hours_per_month=4.0,
            automation_potential=AutomationPotential.FULLY_AUTOMATABLE,
            automation_savings_percent=90,
            priority="high",
        )
        assert item.component_id == "api"
        assert item.hours_per_month == 4.0
        assert item.automation_savings_percent == 90
        assert item.priority == "high"


# ---------------------------------------------------------------------------
# Tests: Chain graph integration
# ---------------------------------------------------------------------------


class TestChainGraph:
    def test_chain_graph_toil(self):
        g = _chain_graph()
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert report.total_hours_per_month > 0
        assert len(report.toil_items) >= 1

    def test_estimated_savings(self):
        g = _chain_graph()
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert report.estimated_savings_hours == report.automatable_hours

    def test_multiple_component_toil_items(self):
        g = _chain_graph()
        calc = ToilCalculator()
        report = calc.analyze(g)
        component_ids = {i.component_id for i in report.toil_items}
        assert len(component_ids) >= 1


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_component_no_toil(self):
        g = InfraGraph()
        g.add_component(_comp(
            "api", "API",
            replicas=1, autoscaling=True, failover=True,
            health=HealthStatus.HEALTHY, log_enabled=True,
        ))
        calc = ToilCalculator()
        report = calc.analyze(g)
        assert len(report.toil_items) == 0
        assert report.toil_score == 100.0

    def test_all_toil_triggers(self):
        g = InfraGraph()
        # Component that triggers every toil check
        g.add_component(_comp(
            "db", "DB", ComponentType.DATABASE,
            replicas=3, autoscaling=False, failover=False,
            health=HealthStatus.DOWN, log_enabled=False,
            backup_enabled=False,
        ))
        g.add_component(_comp("api", "API"))
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        calc = ToilCalculator()
        report = calc.analyze(g)
        categories = {i.category for i in report.toil_items if i.component_id == "db"}
        assert ToilCategory.MANUAL_SCALING in categories
        assert ToilCategory.MANUAL_FAILOVER in categories
        assert ToilCategory.INCIDENT_RESPONSE in categories
        assert ToilCategory.LOG_REVIEW in categories
        assert ToilCategory.BACKUP_VERIFICATION in categories

    def test_report_dataclass_fields(self):
        report = ToilReport(
            toil_items=[],
            total_hours_per_month=0,
            automatable_hours=0,
            toil_percent=0,
            toil_score=100.0,
            top_toil_sources=[],
            automation_recommendations=[],
            estimated_savings_hours=0,
        )
        assert report.toil_score == 100.0
        assert report.estimated_savings_hours == 0
