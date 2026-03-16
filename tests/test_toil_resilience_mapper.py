"""Tests for toil-resilience mapper."""

from __future__ import annotations

import math

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.toil_resilience_mapper import (
    ROIAnalysis,
    ResilienceGap,
    ToilCategory,
    ToilEntry,
    ToilResilienceLink,
    ToilResilienceMapper,
    ToilResilienceReport,
    _CATEGORY_GAP_MAP,
    _FIX_COST_MAP,
    _FIX_DESCRIPTIONS,
    _REDUCTION_MAP,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid,
    name,
    ctype=ComponentType.APP_SERVER,
    replicas=1,
    failover=False,
    autoscaling=False,
    health=HealthStatus.HEALTHY,
    cpu_pct=0.0,
):
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True, promotion_time_seconds=10)
    if autoscaling:
        c.autoscaling = AutoScalingConfig(enabled=True, min_replicas=1, max_replicas=5)
    if cpu_pct > 0:
        c.metrics.cpu_percent = cpu_pct
    return c


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _entry(
    cat=ToilCategory.INCIDENT_RESPONSE,
    cid="app",
    hours=10.0,
    freq=5,
    automatable=True,
    desc="test toil",
):
    return ToilEntry(
        category=cat,
        component_id=cid,
        hours_per_month=hours,
        frequency_per_month=freq,
        automatable=automatable,
        description=desc,
    )


# ===========================================================================
# ToilCategory enum tests
# ===========================================================================


class TestToilCategory:
    def test_all_enum_values_exist(self):
        expected = {
            "INCIDENT_RESPONSE",
            "MANUAL_SCALING",
            "CONFIG_DRIFT_FIX",
            "CERTIFICATE_RENEWAL",
            "BACKUP_RESTORE",
            "FAILOVER_MANUAL",
            "LOG_INVESTIGATION",
            "RESTART_SERVICE",
            "CAPACITY_PLANNING",
            "PATCH_MANAGEMENT",
        }
        actual = {m.name for m in ToilCategory}
        assert actual == expected

    def test_enum_count(self):
        assert len(ToilCategory) == 10

    def test_enum_string_values(self):
        assert ToilCategory.INCIDENT_RESPONSE.value == "incident_response"
        assert ToilCategory.MANUAL_SCALING.value == "manual_scaling"
        assert ToilCategory.CONFIG_DRIFT_FIX.value == "config_drift_fix"
        assert ToilCategory.CERTIFICATE_RENEWAL.value == "certificate_renewal"
        assert ToilCategory.BACKUP_RESTORE.value == "backup_restore"
        assert ToilCategory.FAILOVER_MANUAL.value == "failover_manual"
        assert ToilCategory.LOG_INVESTIGATION.value == "log_investigation"
        assert ToilCategory.RESTART_SERVICE.value == "restart_service"
        assert ToilCategory.CAPACITY_PLANNING.value == "capacity_planning"
        assert ToilCategory.PATCH_MANAGEMENT.value == "patch_management"

    def test_enum_is_str(self):
        for cat in ToilCategory:
            assert isinstance(cat, str)

    def test_category_gap_map_covers_all_categories(self):
        for cat in ToilCategory:
            assert cat in _CATEGORY_GAP_MAP


# ===========================================================================
# ToilEntry model tests
# ===========================================================================


class TestToilEntry:
    def test_basic_creation(self):
        entry = _entry()
        assert entry.category == ToilCategory.INCIDENT_RESPONSE
        assert entry.component_id == "app"
        assert entry.hours_per_month == 10.0
        assert entry.frequency_per_month == 5
        assert entry.automatable is True
        assert entry.description == "test toil"

    def test_all_categories(self):
        for cat in ToilCategory:
            e = _entry(cat=cat)
            assert e.category == cat

    def test_zero_hours(self):
        e = _entry(hours=0.0)
        assert e.hours_per_month == 0.0

    def test_zero_frequency(self):
        e = _entry(freq=0)
        assert e.frequency_per_month == 0

    def test_not_automatable(self):
        e = _entry(automatable=False)
        assert e.automatable is False

    def test_negative_hours_rejected(self):
        with pytest.raises(Exception):
            ToilEntry(
                category=ToilCategory.INCIDENT_RESPONSE,
                component_id="x",
                hours_per_month=-1,
                frequency_per_month=1,
            )

    def test_negative_frequency_rejected(self):
        with pytest.raises(Exception):
            ToilEntry(
                category=ToilCategory.INCIDENT_RESPONSE,
                component_id="x",
                hours_per_month=1,
                frequency_per_month=-1,
            )

    def test_empty_description(self):
        e = ToilEntry(
            category=ToilCategory.MANUAL_SCALING,
            component_id="x",
            hours_per_month=1,
            frequency_per_month=1,
        )
        assert e.description == ""

    def test_large_hours(self):
        e = _entry(hours=1000.0)
        assert e.hours_per_month == 1000.0


# ===========================================================================
# ResilienceGap model tests
# ===========================================================================


class TestResilienceGap:
    def test_basic_creation(self):
        g = ResilienceGap(component_id="db", gap_type="no_redundancy", severity=0.8)
        assert g.component_id == "db"
        assert g.gap_type == "no_redundancy"
        assert g.severity == 0.8
        assert g.description == ""

    def test_all_gap_types(self):
        for gt in ["no_redundancy", "no_autoscaling", "no_circuit_breaker", "no_failover", "high_utilization"]:
            g = ResilienceGap(component_id="c", gap_type=gt, severity=0.5)
            assert g.gap_type == gt

    def test_severity_min(self):
        g = ResilienceGap(component_id="c", gap_type="no_redundancy", severity=0.0)
        assert g.severity == 0.0

    def test_severity_max(self):
        g = ResilienceGap(component_id="c", gap_type="no_redundancy", severity=1.0)
        assert g.severity == 1.0

    def test_severity_out_of_range_high(self):
        with pytest.raises(Exception):
            ResilienceGap(component_id="c", gap_type="no_redundancy", severity=1.5)

    def test_severity_out_of_range_low(self):
        with pytest.raises(Exception):
            ResilienceGap(component_id="c", gap_type="no_redundancy", severity=-0.1)

    def test_with_description(self):
        g = ResilienceGap(
            component_id="db",
            gap_type="no_failover",
            severity=0.9,
            description="DB has no failover",
        )
        assert g.description == "DB has no failover"


# ===========================================================================
# ToilResilienceLink model tests
# ===========================================================================


class TestToilResilienceLink:
    def test_basic_creation(self):
        entry = _entry()
        gap = ResilienceGap(component_id="app", gap_type="no_failover", severity=0.8)
        link = ToilResilienceLink(
            toil_entry=entry,
            resilience_gap=gap,
            causation_strength=0.9,
            estimated_toil_reduction_percent=80.0,
            recommended_fix="Enable failover",
        )
        assert link.causation_strength == 0.9
        assert link.estimated_toil_reduction_percent == 80.0
        assert link.recommended_fix == "Enable failover"

    def test_causation_strength_bounds(self):
        entry = _entry()
        gap = ResilienceGap(component_id="app", gap_type="no_failover", severity=0.5)
        # Valid range
        for s in [0.0, 0.5, 1.0]:
            link = ToilResilienceLink(
                toil_entry=entry,
                resilience_gap=gap,
                causation_strength=s,
                estimated_toil_reduction_percent=50.0,
            )
            assert link.causation_strength == s

    def test_causation_strength_out_of_range(self):
        entry = _entry()
        gap = ResilienceGap(component_id="app", gap_type="no_failover", severity=0.5)
        with pytest.raises(Exception):
            ToilResilienceLink(
                toil_entry=entry,
                resilience_gap=gap,
                causation_strength=1.5,
                estimated_toil_reduction_percent=50.0,
            )

    def test_reduction_percent_bounds(self):
        entry = _entry()
        gap = ResilienceGap(component_id="app", gap_type="no_failover", severity=0.5)
        for pct in [0.0, 50.0, 100.0]:
            link = ToilResilienceLink(
                toil_entry=entry,
                resilience_gap=gap,
                causation_strength=0.5,
                estimated_toil_reduction_percent=pct,
            )
            assert link.estimated_toil_reduction_percent == pct

    def test_reduction_percent_out_of_range(self):
        entry = _entry()
        gap = ResilienceGap(component_id="app", gap_type="no_failover", severity=0.5)
        with pytest.raises(Exception):
            ToilResilienceLink(
                toil_entry=entry,
                resilience_gap=gap,
                causation_strength=0.5,
                estimated_toil_reduction_percent=150.0,
            )


# ===========================================================================
# ROIAnalysis model tests
# ===========================================================================


class TestROIAnalysis:
    def test_basic_creation(self):
        roi = ROIAnalysis(
            fix_description="Add replicas",
            implementation_cost_hours=20.0,
            monthly_toil_saved_hours=5.0,
            payback_period_months=4.0,
            annual_savings_hours=60.0,
            priority_score=3.0,
        )
        assert roi.fix_description == "Add replicas"
        assert roi.implementation_cost_hours == 20.0
        assert roi.monthly_toil_saved_hours == 5.0
        assert roi.payback_period_months == 4.0
        assert roi.annual_savings_hours == 60.0
        assert roi.priority_score == 3.0

    def test_zero_values(self):
        roi = ROIAnalysis(
            fix_description="x",
            implementation_cost_hours=0.0,
            monthly_toil_saved_hours=0.0,
            payback_period_months=0.0,
            annual_savings_hours=0.0,
            priority_score=0.0,
        )
        assert roi.monthly_toil_saved_hours == 0.0


# ===========================================================================
# ToilResilienceReport model tests
# ===========================================================================


class TestToilResilienceReport:
    def test_basic_creation(self):
        report = ToilResilienceReport(
            total_toil_hours_per_month=40.0,
            toil_by_category={"incident_response": 20.0, "manual_scaling": 20.0},
            top_links=[],
            roi_analyses=[],
            automatable_percent=75.0,
            recommendations=["Fix stuff"],
        )
        assert report.total_toil_hours_per_month == 40.0
        assert len(report.toil_by_category) == 2
        assert report.automatable_percent == 75.0
        assert len(report.recommendations) == 1

    def test_empty_report(self):
        report = ToilResilienceReport(
            total_toil_hours_per_month=0.0,
            toil_by_category={},
            top_links=[],
            roi_analyses=[],
            automatable_percent=0.0,
            recommendations=[],
        )
        assert report.total_toil_hours_per_month == 0.0
        assert report.top_links == []


# ===========================================================================
# ToilResilienceMapper — detect_resilience_gaps tests
# ===========================================================================


class TestDetectResilienceGaps:
    def test_empty_graph(self):
        g = _graph()
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        assert gaps == []

    def test_single_component_no_redundancy(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        gap_types = {gap.gap_type for gap in gaps}
        assert "no_redundancy" in gap_types

    def test_single_component_no_autoscaling(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        gap_types = {gap.gap_type for gap in gaps}
        assert "no_autoscaling" in gap_types

    def test_single_component_no_failover(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        gap_types = {gap.gap_type for gap in gaps}
        assert "no_failover" in gap_types

    def test_component_with_redundancy_no_gap(self):
        g = _graph(_comp("app", "App", replicas=3, failover=True))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        gap_types = {gap.gap_type for gap in gaps if gap.component_id == "app"}
        assert "no_redundancy" not in gap_types

    def test_component_with_autoscaling_no_gap(self):
        g = _graph(_comp("app", "App", autoscaling=True))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        gap_types = {gap.gap_type for gap in gaps if gap.component_id == "app"}
        assert "no_autoscaling" not in gap_types

    def test_component_with_failover_no_gap(self):
        g = _graph(_comp("app", "App", failover=True))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        gap_types = {gap.gap_type for gap in gaps if gap.component_id == "app"}
        assert "no_failover" not in gap_types

    def test_high_utilization_gap(self):
        g = _graph(_comp("app", "App", cpu_pct=85.0))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        gap_types = {gap.gap_type for gap in gaps}
        assert "high_utilization" in gap_types

    def test_no_high_utilization_gap_when_low(self):
        g = _graph(_comp("app", "App", cpu_pct=50.0))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        gap_types = {gap.gap_type for gap in gaps}
        assert "high_utilization" not in gap_types

    def test_high_utilization_severity_scales(self):
        g = _graph(_comp("app", "App", cpu_pct=85.0))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        util_gaps = [gap for gap in gaps if gap.gap_type == "high_utilization"]
        assert len(util_gaps) == 1
        assert 0 < util_gaps[0].severity <= 1.0

    def test_high_utilization_at_boundary(self):
        g = _graph(_comp("app", "App", cpu_pct=70.0))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        gap_types = {gap.gap_type for gap in gaps}
        assert "high_utilization" not in gap_types

    def test_high_utilization_just_above_boundary(self):
        g = _graph(_comp("app", "App", cpu_pct=71.0))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        gap_types = {gap.gap_type for gap in gaps}
        assert "high_utilization" in gap_types

    def test_circuit_breaker_gap_with_dependents(self):
        g = _graph(_comp("app", "App"), _comp("db", "DB"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        db_gaps = {gap.gap_type for gap in gaps if gap.component_id == "db"}
        assert "no_circuit_breaker" in db_gaps

    def test_no_circuit_breaker_gap_without_dependents(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        cb_gaps = [gap for gap in gaps if gap.gap_type == "no_circuit_breaker"]
        assert len(cb_gaps) == 0

    def test_circuit_breaker_present_no_gap(self):
        g = _graph(_comp("app", "App"), _comp("db", "DB"))
        dep = Dependency(source_id="app", target_id="db")
        dep.circuit_breaker = CircuitBreakerConfig(enabled=True)
        g.add_dependency(dep)
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        db_cb_gaps = [
            gap for gap in gaps
            if gap.component_id == "db" and gap.gap_type == "no_circuit_breaker"
        ]
        assert len(db_cb_gaps) == 0

    def test_multiple_components_all_gaps(self):
        g = _graph(
            _comp("app", "App"),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        assert len(gaps) > 0
        component_ids = {gap.component_id for gap in gaps}
        assert "app" in component_ids
        assert "db" in component_ids

    def test_fully_resilient_component(self):
        g = _graph(_comp("app", "App", replicas=3, failover=True, autoscaling=True))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        app_gaps = [gap for gap in gaps if gap.component_id == "app"]
        app_gap_types = {gap.gap_type for gap in app_gaps}
        assert "no_redundancy" not in app_gap_types
        assert "no_autoscaling" not in app_gap_types
        assert "no_failover" not in app_gap_types

    def test_redundancy_severity_increases_with_dependents(self):
        g = _graph(
            _comp("db", "DB"),
            _comp("app1", "App1"),
            _comp("app2", "App2"),
        )
        g.add_dependency(Dependency(source_id="app1", target_id="db"))
        g.add_dependency(Dependency(source_id="app2", target_id="db"))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        db_redundancy = [
            gap for gap in gaps
            if gap.component_id == "db" and gap.gap_type == "no_redundancy"
        ]
        assert len(db_redundancy) == 1
        assert db_redundancy[0].severity > 0.5

    def test_failover_severity_increases_with_dependents(self):
        g = _graph(
            _comp("db", "DB"),
            _comp("app1", "App1"),
            _comp("app2", "App2"),
            _comp("app3", "App3"),
        )
        g.add_dependency(Dependency(source_id="app1", target_id="db"))
        g.add_dependency(Dependency(source_id="app2", target_id="db"))
        g.add_dependency(Dependency(source_id="app3", target_id="db"))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        db_failover = [
            gap for gap in gaps
            if gap.component_id == "db" and gap.gap_type == "no_failover"
        ]
        assert len(db_failover) == 1
        assert db_failover[0].severity > 0.5


# ===========================================================================
# ToilResilienceMapper — add_toil tests
# ===========================================================================


class TestAddToil:
    def test_add_single_entry(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry())
        assert len(mapper._toil_entries) == 1

    def test_add_multiple_entries(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.INCIDENT_RESPONSE))
        mapper.add_toil(_entry(cat=ToilCategory.MANUAL_SCALING))
        mapper.add_toil(_entry(cat=ToilCategory.RESTART_SERVICE))
        assert len(mapper._toil_entries) == 3


# ===========================================================================
# ToilResilienceMapper — map_toil_to_gaps tests
# ===========================================================================


class TestMapToilToGaps:
    def test_incident_response_maps_to_no_failover(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.INCIDENT_RESPONSE, cid="app"))
        links = mapper.map_toil_to_gaps()
        gap_types = {link.resilience_gap.gap_type for link in links}
        assert "no_failover" in gap_types

    def test_manual_scaling_maps_to_no_autoscaling(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.MANUAL_SCALING, cid="app"))
        links = mapper.map_toil_to_gaps()
        gap_types = {link.resilience_gap.gap_type for link in links}
        assert "no_autoscaling" in gap_types

    def test_failover_manual_maps_to_no_failover(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app"))
        links = mapper.map_toil_to_gaps()
        gap_types = {link.resilience_gap.gap_type for link in links}
        assert "no_failover" in gap_types

    def test_restart_service_maps_to_no_redundancy(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.RESTART_SERVICE, cid="app"))
        links = mapper.map_toil_to_gaps()
        gap_types = {link.resilience_gap.gap_type for link in links}
        assert "no_redundancy" in gap_types

    def test_capacity_planning_maps_to_autoscaling_and_utilization(self):
        g = _graph(_comp("app", "App", cpu_pct=85.0))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.CAPACITY_PLANNING, cid="app"))
        links = mapper.map_toil_to_gaps()
        gap_types = {link.resilience_gap.gap_type for link in links}
        assert "no_autoscaling" in gap_types
        assert "high_utilization" in gap_types

    def test_config_drift_maps_to_high_utilization(self):
        g = _graph(_comp("app", "App", cpu_pct=80.0))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.CONFIG_DRIFT_FIX, cid="app"))
        links = mapper.map_toil_to_gaps()
        gap_types = {link.resilience_gap.gap_type for link in links}
        assert "high_utilization" in gap_types

    def test_no_matching_gaps(self):
        g = _graph(_comp("app", "App", replicas=3, failover=True, autoscaling=True))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.MANUAL_SCALING, cid="app"))
        links = mapper.map_toil_to_gaps()
        scaling_links = [
            l for l in links if l.toil_entry.category == ToilCategory.MANUAL_SCALING
        ]
        assert len(scaling_links) == 0

    def test_toil_on_nonexistent_component(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.INCIDENT_RESPONSE, cid="nonexistent"))
        links = mapper.map_toil_to_gaps()
        ne_links = [l for l in links if l.toil_entry.component_id == "nonexistent"]
        assert len(ne_links) == 0

    def test_no_toil_entries(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        links = mapper.map_toil_to_gaps()
        assert links == []

    def test_links_sorted_by_impact(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.RESTART_SERVICE, cid="app", hours=2.0))
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app", hours=20.0))
        links = mapper.map_toil_to_gaps()
        if len(links) >= 2:
            impact_first = links[0].causation_strength * links[0].toil_entry.hours_per_month
            impact_second = links[1].causation_strength * links[1].toil_entry.hours_per_month
            assert impact_first >= impact_second

    def test_incident_response_maps_to_circuit_breaker(self):
        g = _graph(_comp("app", "App"), _comp("db", "DB"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.INCIDENT_RESPONSE, cid="db"))
        links = mapper.map_toil_to_gaps()
        gap_types = {link.resilience_gap.gap_type for link in links}
        assert "no_circuit_breaker" in gap_types

    def test_log_investigation_maps_to_circuit_breaker(self):
        g = _graph(_comp("app", "App"), _comp("db", "DB"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.LOG_INVESTIGATION, cid="db"))
        links = mapper.map_toil_to_gaps()
        gap_types = {link.resilience_gap.gap_type for link in links}
        assert "no_circuit_breaker" in gap_types

    def test_certificate_renewal_lower_causation(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.CERTIFICATE_RENEWAL, cid="app"))
        links = mapper.map_toil_to_gaps()
        for link in links:
            if link.toil_entry.category == ToilCategory.CERTIFICATE_RENEWAL:
                assert link.causation_strength <= 0.5

    def test_patch_management_lower_causation(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.PATCH_MANAGEMENT, cid="app"))
        links = mapper.map_toil_to_gaps()
        for link in links:
            if link.toil_entry.category == ToilCategory.PATCH_MANAGEMENT:
                assert link.causation_strength <= 0.5

    def test_backup_restore_lower_causation(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.BACKUP_RESTORE, cid="app"))
        links = mapper.map_toil_to_gaps()
        for link in links:
            if link.toil_entry.category == ToilCategory.BACKUP_RESTORE:
                assert link.causation_strength <= 0.5

    def test_recommended_fix_populated(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app"))
        links = mapper.map_toil_to_gaps()
        for link in links:
            assert link.recommended_fix != ""

    def test_multiple_toil_categories_same_component(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.INCIDENT_RESPONSE, cid="app"))
        mapper.add_toil(_entry(cat=ToilCategory.RESTART_SERVICE, cid="app"))
        mapper.add_toil(_entry(cat=ToilCategory.MANUAL_SCALING, cid="app"))
        links = mapper.map_toil_to_gaps()
        assert len(links) >= 3

    def test_all_categories_produce_links_for_vulnerable_component(self):
        # Component with every gap type
        g = _graph(_comp("app", "App", cpu_pct=85.0), _comp("client", "Client"))
        g.add_dependency(Dependency(source_id="client", target_id="app"))
        mapper = ToilResilienceMapper(g)
        for cat in ToilCategory:
            mapper.add_toil(_entry(cat=cat, cid="app", hours=1.0))
        links = mapper.map_toil_to_gaps()
        categories_with_links = {link.toil_entry.category for link in links}
        assert len(categories_with_links) >= 8


# ===========================================================================
# ToilResilienceMapper — calculate_roi tests
# ===========================================================================


class TestCalculateROI:
    def _make_link(self, hours=10.0, reduction=80.0, strength=0.9, gap_type="no_failover"):
        entry = _entry(hours=hours)
        gap = ResilienceGap(component_id="app", gap_type=gap_type, severity=0.8)
        return ToilResilienceLink(
            toil_entry=entry,
            resilience_gap=gap,
            causation_strength=strength,
            estimated_toil_reduction_percent=reduction,
            recommended_fix="Enable failover",
        )

    def test_positive_roi(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        link = self._make_link(hours=20.0, reduction=80.0)
        roi = mapper.calculate_roi(link, implementation_hours=16.0)
        assert roi.monthly_toil_saved_hours == 16.0
        assert roi.payback_period_months == 1.0
        assert roi.annual_savings_hours == 192.0
        assert roi.priority_score > 0

    def test_break_even(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        link = self._make_link(hours=10.0, reduction=50.0)
        roi = mapper.calculate_roi(link, implementation_hours=5.0)
        assert roi.monthly_toil_saved_hours == 5.0
        assert roi.payback_period_months == 1.0

    def test_negative_roi_expensive_fix(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        link = self._make_link(hours=1.0, reduction=10.0)
        roi = mapper.calculate_roi(link, implementation_hours=100.0)
        assert roi.payback_period_months > 12.0
        assert roi.priority_score < 1.0

    def test_zero_toil_hours(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        link = self._make_link(hours=0.0, reduction=80.0)
        roi = mapper.calculate_roi(link, implementation_hours=10.0)
        assert roi.monthly_toil_saved_hours == 0.0
        assert roi.payback_period_months == float("inf")

    def test_zero_implementation_cost(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        link = self._make_link(hours=10.0, reduction=80.0)
        roi = mapper.calculate_roi(link, implementation_hours=0.0)
        assert roi.payback_period_months == 0.0
        assert roi.priority_score > 0

    def test_annual_savings_calculation(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        link = self._make_link(hours=10.0, reduction=50.0)
        roi = mapper.calculate_roi(link, implementation_hours=5.0)
        assert roi.annual_savings_hours == 60.0  # 5.0 * 12

    def test_priority_considers_causation_strength(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        link_high = self._make_link(hours=10.0, reduction=80.0, strength=0.9)
        link_low = self._make_link(hours=10.0, reduction=80.0, strength=0.1)
        roi_high = mapper.calculate_roi(link_high, 10.0)
        roi_low = mapper.calculate_roi(link_low, 10.0)
        assert roi_high.priority_score > roi_low.priority_score

    def test_fix_description_propagated(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        link = self._make_link()
        roi = mapper.calculate_roi(link, 10.0)
        assert roi.fix_description == "Enable failover"

    def test_large_implementation_cost(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        link = self._make_link(hours=5.0, reduction=50.0)
        roi = mapper.calculate_roi(link, implementation_hours=1000.0)
        assert roi.payback_period_months > 100

    def test_zero_reduction_percent(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        link = self._make_link(hours=10.0, reduction=0.0)
        roi = mapper.calculate_roi(link, implementation_hours=10.0)
        assert roi.monthly_toil_saved_hours == 0.0
        assert math.isinf(roi.payback_period_months)

    def test_full_reduction_percent(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        link = self._make_link(hours=10.0, reduction=100.0)
        roi = mapper.calculate_roi(link, implementation_hours=10.0)
        assert roi.monthly_toil_saved_hours == 10.0


# ===========================================================================
# ToilResilienceMapper — generate_report tests
# ===========================================================================


class TestGenerateReport:
    def test_empty_report(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        report = mapper.generate_report()
        assert report.total_toil_hours_per_month == 0.0
        assert report.toil_by_category == {}
        assert report.top_links == []
        assert report.roi_analyses == []
        assert report.automatable_percent == 0.0
        assert report.recommendations == []

    def test_single_toil_entry(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app", hours=10.0))
        report = mapper.generate_report()
        assert report.total_toil_hours_per_month == 10.0
        assert "failover_manual" in report.toil_by_category

    def test_multiple_toil_entries(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app", hours=10.0))
        mapper.add_toil(_entry(cat=ToilCategory.RESTART_SERVICE, cid="app", hours=5.0))
        report = mapper.generate_report()
        assert report.total_toil_hours_per_month == 15.0

    def test_toil_by_category_aggregation(self):
        g = _graph(_comp("app", "App"), _comp("db", "DB"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.INCIDENT_RESPONSE, cid="app", hours=10.0))
        mapper.add_toil(_entry(cat=ToilCategory.INCIDENT_RESPONSE, cid="db", hours=5.0))
        report = mapper.generate_report()
        assert report.toil_by_category["incident_response"] == 15.0

    def test_automatable_percent_all_automatable(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(hours=10.0, automatable=True))
        mapper.add_toil(_entry(hours=5.0, automatable=True))
        report = mapper.generate_report()
        assert report.automatable_percent == 100.0

    def test_automatable_percent_none_automatable(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(hours=10.0, automatable=False))
        report = mapper.generate_report()
        assert report.automatable_percent == 0.0

    def test_automatable_percent_mixed(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(hours=10.0, automatable=True))
        mapper.add_toil(_entry(hours=10.0, automatable=False))
        report = mapper.generate_report()
        assert report.automatable_percent == 50.0

    def test_roi_analyses_populated(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app", hours=20.0))
        report = mapper.generate_report()
        assert len(report.roi_analyses) > 0

    def test_roi_analyses_sorted_by_priority(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app", hours=20.0))
        mapper.add_toil(_entry(cat=ToilCategory.RESTART_SERVICE, cid="app", hours=5.0))
        report = mapper.generate_report()
        if len(report.roi_analyses) >= 2:
            assert report.roi_analyses[0].priority_score >= report.roi_analyses[1].priority_score

    def test_recommendations_generated(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app", hours=20.0))
        report = mapper.generate_report()
        assert len(report.recommendations) > 0

    def test_recommendations_capped_at_5(self):
        g = _graph(
            _comp("a", "A", cpu_pct=85.0),
            _comp("b", "B", cpu_pct=85.0),
            _comp("c", "C", cpu_pct=85.0),
        )
        for cid_pair in [("a", "b"), ("b", "c")]:
            g.add_dependency(Dependency(source_id=cid_pair[0], target_id=cid_pair[1]))
        mapper = ToilResilienceMapper(g)
        for cat in ToilCategory:
            for cid in ["a", "b", "c"]:
                mapper.add_toil(_entry(cat=cat, cid=cid, hours=5.0))
        report = mapper.generate_report()
        assert len(report.recommendations) <= 5

    def test_top_links_populated(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app", hours=20.0))
        report = mapper.generate_report()
        assert len(report.top_links) > 0

    def test_report_with_no_gaps(self):
        g = _graph(_comp("app", "App", replicas=3, failover=True, autoscaling=True))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.MANUAL_SCALING, cid="app", hours=10.0))
        report = mapper.generate_report()
        assert report.total_toil_hours_per_month == 10.0
        # Links may be empty since autoscaling gap doesn't exist
        scaling_links = [
            l for l in report.top_links
            if l.toil_entry.category == ToilCategory.MANUAL_SCALING
        ]
        assert len(scaling_links) == 0

    def test_report_deduplicates_roi_by_fix(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        # Two toil entries that map to the same gap
        mapper.add_toil(_entry(cat=ToilCategory.INCIDENT_RESPONSE, cid="app", hours=10.0))
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app", hours=5.0))
        report = mapper.generate_report()
        # ROI should be deduplicated by component_id:gap_type
        failover_rois = [
            r for r in report.roi_analyses
            if "failover" in r.fix_description.lower()
        ]
        assert len(failover_rois) <= 1

    def test_empty_graph_report(self):
        g = _graph()
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.INCIDENT_RESPONSE, cid="app", hours=10.0))
        report = mapper.generate_report()
        assert report.total_toil_hours_per_month == 10.0
        assert report.top_links == []
        assert report.roi_analyses == []

    def test_report_recommendation_format(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app", hours=20.0))
        report = mapper.generate_report()
        for rec in report.recommendations:
            assert "saves" in rec or "cost" in rec

    def test_report_zero_toil_hours_infinite_payback_recommendation(self):
        """When toil hours is 0, payback is infinite; recommendation shows cost instead."""
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app", hours=0.0))
        report = mapper.generate_report()
        # With 0 hours, monthly_saved=0, payback=inf -> the else branch formats with "cost"
        for rec in report.recommendations:
            assert "cost" in rec or "saves" in rec

    def test_report_is_pydantic_model(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        report = mapper.generate_report()
        assert isinstance(report, ToilResilienceReport)
        # Should be serializable
        d = report.model_dump()
        assert "total_toil_hours_per_month" in d


# ===========================================================================
# Mapping constants tests
# ===========================================================================


class TestMappingConstants:
    def test_reduction_map_all_gap_types(self):
        for gt in ["no_redundancy", "no_autoscaling", "no_circuit_breaker", "no_failover", "high_utilization"]:
            assert gt in _REDUCTION_MAP
            assert 0 < _REDUCTION_MAP[gt] <= 100

    def test_fix_cost_map_all_gap_types(self):
        for gt in ["no_redundancy", "no_autoscaling", "no_circuit_breaker", "no_failover", "high_utilization"]:
            assert gt in _FIX_COST_MAP
            assert _FIX_COST_MAP[gt] > 0

    def test_fix_descriptions_all_gap_types(self):
        for gt in ["no_redundancy", "no_autoscaling", "no_circuit_breaker", "no_failover", "high_utilization"]:
            assert gt in _FIX_DESCRIPTIONS
            assert len(_FIX_DESCRIPTIONS[gt]) > 0

    def test_category_gap_map_values_are_valid(self):
        for cat, mappings in _CATEGORY_GAP_MAP.items():
            for gap_type, strength in mappings:
                assert isinstance(gap_type, str)
                assert 0 < strength <= 1.0


# ===========================================================================
# Edge case and integration tests
# ===========================================================================


class TestEdgeCases:
    def test_single_component_full_lifecycle(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.INCIDENT_RESPONSE, cid="app", hours=10.0))
        gaps = mapper.detect_resilience_gaps()
        assert len(gaps) > 0
        links = mapper.map_toil_to_gaps()
        assert len(links) > 0
        report = mapper.generate_report()
        assert report.total_toil_hours_per_month == 10.0
        assert len(report.roi_analyses) > 0

    def test_all_gaps_fixed_no_links(self):
        g = _graph(
            _comp("app", "App", replicas=3, failover=True, autoscaling=True),
        )
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.MANUAL_SCALING, cid="app", hours=10.0))
        links = mapper.map_toil_to_gaps()
        # autoscaling is enabled, so no_autoscaling gap shouldn't exist
        scaling_links = [
            l for l in links
            if l.resilience_gap.gap_type == "no_autoscaling"
        ]
        assert len(scaling_links) == 0

    def test_high_toil_on_nonexistent_component(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cid="ghost", hours=100.0))
        links = mapper.map_toil_to_gaps()
        ghost_links = [l for l in links if l.toil_entry.component_id == "ghost"]
        assert len(ghost_links) == 0
        report = mapper.generate_report()
        assert report.total_toil_hours_per_month == 100.0

    def test_utilization_at_100_percent(self):
        g = _graph(_comp("app", "App", cpu_pct=100.0))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        util_gaps = [gap for gap in gaps if gap.gap_type == "high_utilization"]
        assert len(util_gaps) == 1
        assert util_gaps[0].severity == 1.0

    def test_multiple_components_independent(self):
        g = _graph(
            _comp("app1", "App1"),
            _comp("app2", "App2"),
        )
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.RESTART_SERVICE, cid="app1", hours=5.0))
        mapper.add_toil(_entry(cat=ToilCategory.MANUAL_SCALING, cid="app2", hours=3.0))
        links = mapper.map_toil_to_gaps()
        app1_links = [l for l in links if l.toil_entry.component_id == "app1"]
        app2_links = [l for l in links if l.toil_entry.component_id == "app2"]
        assert len(app1_links) > 0
        assert len(app2_links) > 0

    def test_chain_topology(self):
        g = _graph(
            _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER),
            _comp("app", "App"),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="lb", target_id="app"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.INCIDENT_RESPONSE, cid="db", hours=15.0))
        report = mapper.generate_report()
        assert report.total_toil_hours_per_month == 15.0
        assert len(report.top_links) > 0

    def test_report_model_dump_roundtrip(self):
        g = _graph(_comp("app", "App"))
        mapper = ToilResilienceMapper(g)
        mapper.add_toil(_entry(cat=ToilCategory.FAILOVER_MANUAL, cid="app", hours=10.0))
        report = mapper.generate_report()
        d = report.model_dump()
        restored = ToilResilienceReport(**d)
        assert restored.total_toil_hours_per_month == report.total_toil_hours_per_month
        assert len(restored.top_links) == len(report.top_links)

    def test_many_components_performance(self):
        comps = [_comp(f"c{i}", f"C{i}") for i in range(20)]
        g = _graph(*comps)
        mapper = ToilResilienceMapper(g)
        for i in range(20):
            mapper.add_toil(_entry(cat=ToilCategory.RESTART_SERVICE, cid=f"c{i}", hours=1.0))
        report = mapper.generate_report()
        assert report.total_toil_hours_per_month == 20.0
        assert len(report.top_links) > 0

    def test_severity_capped_at_1(self):
        # Many dependents should not push severity above 1.0
        comps = [_comp("db", "DB")] + [_comp(f"app{i}", f"App{i}") for i in range(10)]
        g = _graph(*comps)
        for i in range(10):
            g.add_dependency(Dependency(source_id=f"app{i}", target_id="db"))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        for gap in gaps:
            assert gap.severity <= 1.0

    def test_replicas_greater_than_1_no_redundancy_gap(self):
        g = _graph(_comp("app", "App", replicas=3))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        redundancy_gaps = [
            gap for gap in gaps
            if gap.component_id == "app" and gap.gap_type == "no_redundancy"
        ]
        # replicas > 1 but no failover -> still no_redundancy check: replicas<=1 AND not failover
        # with replicas=3, the condition comp.replicas <= 1 is False, so no gap
        assert len(redundancy_gaps) == 0

    def test_failover_only_no_redundancy_gap(self):
        # failover=True but replicas=1 -> no_redundancy condition: replicas<=1 AND not failover.enabled
        # failover.enabled is True, so no gap
        g = _graph(_comp("app", "App", replicas=1, failover=True))
        mapper = ToilResilienceMapper(g)
        gaps = mapper.detect_resilience_gaps()
        redundancy_gaps = [
            gap for gap in gaps
            if gap.component_id == "app" and gap.gap_type == "no_redundancy"
        ]
        assert len(redundancy_gaps) == 0

    def test_autoscaling_severity_differs_by_replicas(self):
        g1 = _graph(_comp("app", "App", replicas=1))
        g2 = _graph(_comp("app", "App", replicas=3))
        m1 = ToilResilienceMapper(g1)
        m2 = ToilResilienceMapper(g2)
        gaps1 = [g for g in m1.detect_resilience_gaps() if g.gap_type == "no_autoscaling"]
        gaps2 = [g for g in m2.detect_resilience_gaps() if g.gap_type == "no_autoscaling"]
        assert len(gaps1) == 1
        assert len(gaps2) == 1
        # Single replica gets higher severity
        assert gaps1[0].severity > gaps2[0].severity
