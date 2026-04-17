# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tests for the Financial Impact Report calculator."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationReport
from faultray.simulator.financial_impact import (
    DEFAULT_COST_PER_HOUR,
    DEFAULT_FIX_COST_PER_YEAR,
    ComponentImpact,
    FinancialImpactReport,
    RecommendedFix,
    _HOURS_PER_YEAR,
    calculate_financial_impact,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_graph() -> InfraGraph:
    """Single-component graph (database, 1 replica)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="PostgreSQL",
        type=ComponentType.DATABASE,
        replicas=1,
    ))
    return graph


@pytest.fixture
def redundant_graph() -> InfraGraph:
    """Database with 3 replicas — much higher availability."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="PostgreSQL (HA)",
        type=ComponentType.DATABASE,
        replicas=3,
    ))
    return graph


@pytest.fixture
def multi_component_graph() -> InfraGraph:
    """Typical web stack: LB -> App -> DB + Cache."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="nginx",
        type=ComponentType.LOAD_BALANCER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="app",
        name="api-server",
        type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db",
        name="PostgreSQL",
        type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_component(Component(
        id="cache",
        name="Redis",
        type=ComponentType.CACHE,
        replicas=1,
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
    ))

    return graph


@pytest.fixture
def graph_with_cost_profile() -> InfraGraph:
    """Graph where a component has an explicit cost_profile."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="api-server",
        type=ComponentType.APP_SERVER,
        replicas=1,
        cost_profile=CostProfile(revenue_per_minute=500.0),
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests: calculate_financial_impact
# ---------------------------------------------------------------------------

class TestCalculateFinancialImpact:
    """Core calculation tests."""

    def test_empty_graph(self) -> None:
        graph = InfraGraph()
        report = calculate_financial_impact(graph)

        assert report.resilience_score == 0.0
        assert report.total_annual_loss == 0.0
        assert report.total_downtime_hours == 0.0
        assert report.component_impacts == []
        assert report.top_risks == []
        assert report.recommended_fixes == []

    def test_single_component_has_positive_loss(self, simple_graph: InfraGraph) -> None:
        report = calculate_financial_impact(simple_graph)

        assert len(report.component_impacts) == 1
        impact = report.component_impacts[0]

        assert impact.component_id == "db"
        assert impact.component_type == "database"
        assert impact.cost_per_hour == DEFAULT_COST_PER_HOUR["database"]
        # A single database has some downtime, so loss > 0
        assert impact.annual_loss > 0
        assert impact.annual_downtime_hours > 0
        assert report.total_annual_loss > 0

    def test_redundant_component_has_lower_loss(
        self,
        simple_graph: InfraGraph,
        redundant_graph: InfraGraph,
    ) -> None:
        single_report = calculate_financial_impact(simple_graph)
        redundant_report = calculate_financial_impact(redundant_graph)

        assert redundant_report.total_annual_loss < single_report.total_annual_loss
        assert redundant_report.total_downtime_hours < single_report.total_downtime_hours

    def test_multi_component_impacts_sorted_by_loss(
        self, multi_component_graph: InfraGraph,
    ) -> None:
        report = calculate_financial_impact(multi_component_graph)

        assert len(report.component_impacts) == 4
        # Verify sorted descending
        losses = [c.annual_loss for c in report.component_impacts]
        assert losses == sorted(losses, reverse=True)

    def test_cost_per_hour_override(self, simple_graph: InfraGraph) -> None:
        report_default = calculate_financial_impact(simple_graph)
        report_override = calculate_financial_impact(
            simple_graph, cost_per_hour_override=1_000.0,
        )

        # With lower cost/hr, total loss should be lower
        assert report_override.total_annual_loss < report_default.total_annual_loss
        assert report_override.component_impacts[0].cost_per_hour == 1_000.0

    def test_cost_profile_revenue_per_minute_takes_precedence(
        self, graph_with_cost_profile: InfraGraph,
    ) -> None:
        report = calculate_financial_impact(graph_with_cost_profile)

        impact = report.component_impacts[0]
        # revenue_per_minute=500 -> cost_per_hour=30000
        assert impact.cost_per_hour == 500.0 * 60.0

    def test_cost_profile_beats_override(
        self, graph_with_cost_profile: InfraGraph,
    ) -> None:
        report = calculate_financial_impact(
            graph_with_cost_profile, cost_per_hour_override=1.0,
        )
        # The component's own cost_profile should take precedence
        impact = report.component_impacts[0]
        assert impact.cost_per_hour == 500.0 * 60.0

    def test_resilience_score_from_simulation_report(
        self, simple_graph: InfraGraph,
    ) -> None:
        mock_report = SimulationReport(resilience_score=42.5)
        report = calculate_financial_impact(
            simple_graph, simulation_report=mock_report,
        )
        assert report.resilience_score == 42.5

    def test_resilience_score_computed_from_graph(
        self, simple_graph: InfraGraph,
    ) -> None:
        report = calculate_financial_impact(simple_graph)
        # Should use graph.resilience_score() — exact value depends on graph
        assert 0.0 <= report.resilience_score <= 100.0


class TestRecommendedFixes:
    """Tests for the fix recommendation logic."""

    def test_single_replica_gets_fix_recommendation(
        self, simple_graph: InfraGraph,
    ) -> None:
        report = calculate_financial_impact(simple_graph)

        assert len(report.recommended_fixes) >= 1
        fix = report.recommended_fixes[0]

        assert fix.component_id == "db"
        assert "replica" in fix.description.lower()
        assert fix.annual_cost == DEFAULT_FIX_COST_PER_YEAR["database"]
        assert fix.annual_savings > 0
        assert fix.roi > 0

    def test_no_fix_for_redundant_component(
        self, redundant_graph: InfraGraph,
    ) -> None:
        report = calculate_financial_impact(redundant_graph)

        # 3 replicas — no "add replica" fix recommended
        db_fixes = [f for f in report.recommended_fixes if f.component_id == "db"]
        assert len(db_fixes) == 0

    def test_fixes_sorted_by_roi_descending(
        self, multi_component_graph: InfraGraph,
    ) -> None:
        report = calculate_financial_impact(multi_component_graph)

        rois = [f.roi for f in report.recommended_fixes]
        assert rois == sorted(rois, reverse=True)

    def test_total_fix_cost_and_savings(
        self, multi_component_graph: InfraGraph,
    ) -> None:
        report = calculate_financial_impact(multi_component_graph)

        expected_fix_cost = sum(f.annual_cost for f in report.recommended_fixes)
        expected_savings = sum(f.annual_savings for f in report.recommended_fixes)

        assert report.total_fix_cost == round(expected_fix_cost, 2)
        assert report.total_savings == round(expected_savings, 2)

    def test_overall_roi(self, multi_component_graph: InfraGraph) -> None:
        report = calculate_financial_impact(multi_component_graph)

        if report.total_fix_cost > 0:
            expected_roi = report.total_savings / report.total_fix_cost
            assert report.roi == round(expected_roi, 1)


class TestTopRisks:
    """Tests for top risk identification."""

    def test_top_risks_subset_of_impacts(
        self, multi_component_graph: InfraGraph,
    ) -> None:
        report = calculate_financial_impact(multi_component_graph)

        risk_ids = {r.component_id for r in report.top_risks}
        impact_ids = {c.component_id for c in report.component_impacts}
        assert risk_ids.issubset(impact_ids)

    def test_top_risks_limited_to_10(self) -> None:
        """Even with many components, top_risks should be capped at 10."""
        graph = InfraGraph()
        for i in range(15):
            graph.add_component(Component(
                id=f"app-{i}",
                name=f"App Server {i}",
                type=ComponentType.APP_SERVER,
                replicas=1,
            ))

        report = calculate_financial_impact(graph)
        assert len(report.top_risks) <= 10

    def test_zero_loss_components_not_in_top_risks(self) -> None:
        """Components with zero annual loss should not appear in top_risks."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app",
            name="App Server",
            type=ComponentType.APP_SERVER,
            replicas=1,
        ))

        report = calculate_financial_impact(graph)
        for risk in report.top_risks:
            assert risk.annual_loss > 0


class TestDataclasses:
    """Verify dataclass structure and defaults."""

    def test_component_impact_fields(self) -> None:
        impact = ComponentImpact(
            component_id="db",
            component_type="database",
            availability=0.999,
            annual_downtime_hours=8.76,
            annual_loss=87_600.0,
            cost_per_hour=10_000.0,
            risk_description="SPOF",
        )
        assert impact.component_id == "db"
        assert impact.annual_loss == 87_600.0

    def test_recommended_fix_fields(self) -> None:
        fix = RecommendedFix(
            component_id="db",
            description="Add replica",
            annual_cost=24_000.0,
            annual_savings=87_000.0,
            roi=3.6,
        )
        assert fix.roi == 3.6

    def test_report_defaults(self) -> None:
        report = FinancialImpactReport(
            resilience_score=50.0,
            total_annual_loss=100_000.0,
            total_downtime_hours=10.0,
        )
        assert report.component_impacts == []
        assert report.top_risks == []
        assert report.recommended_fixes == []
        assert report.total_fix_cost == 0.0
        assert report.total_savings == 0.0
        assert report.roi == 0.0


class TestDefaultCostTables:
    """Verify cost table completeness and values."""

    def test_all_component_types_have_default_cost(self) -> None:
        for ct in ComponentType:
            assert ct.value in DEFAULT_COST_PER_HOUR, (
                f"Missing DEFAULT_COST_PER_HOUR for {ct.value}"
            )

    def test_all_component_types_have_default_fix_cost(self) -> None:
        for ct in ComponentType:
            assert ct.value in DEFAULT_FIX_COST_PER_YEAR, (
                f"Missing DEFAULT_FIX_COST_PER_YEAR for {ct.value}"
            )

    def test_cost_values_are_positive(self) -> None:
        for k, v in DEFAULT_COST_PER_HOUR.items():
            assert v > 0, f"DEFAULT_COST_PER_HOUR[{k}] must be positive"
        for k, v in DEFAULT_FIX_COST_PER_YEAR.items():
            assert v > 0, f"DEFAULT_FIX_COST_PER_YEAR[{k}] must be positive"

    def test_hours_per_year_constant(self) -> None:
        assert _HOURS_PER_YEAR == 8760.0


class TestDemoGraphFinancialImpact:
    """Integration test using the demo graph."""

    def test_demo_graph_produces_valid_report(self) -> None:
        from faultray.model.demo import create_demo_graph

        graph = create_demo_graph()
        report = calculate_financial_impact(graph)

        # Should have impacts for all 9 demo components
        assert len(report.component_impacts) == len(graph.components)
        assert report.total_annual_loss > 0
        assert report.total_downtime_hours > 0
        assert report.resilience_score > 0

        # Should recommend fixes for SPOF components (replicas=1)
        assert len(report.recommended_fixes) > 0

        # ROI should be positive
        assert report.roi > 0
