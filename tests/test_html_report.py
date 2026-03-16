"""Tests for the HTML report generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.model.components import HealthStatus
from faultray.model.demo import create_demo_graph
from faultray.reporter.html_report import (
    _build_dependency_svg,
    _build_finding,
    _health_class,
    _health_icon,
    _score_color,
    _util_color,
    generate_html_report,
    save_html_report,
)
from faultray.simulator.cascade import CascadeChain, CascadeEffect
from faultray.simulator.engine import ScenarioResult, SimulationEngine, SimulationReport
from faultray.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def demo_graph():
    return create_demo_graph()


@pytest.fixture
def demo_report(demo_graph):
    engine = SimulationEngine(demo_graph)
    return engine.run_all_defaults()


@pytest.fixture
def minimal_report():
    """A minimal report for unit testing individual helpers."""
    effect = CascadeEffect(
        component_id="web-1",
        component_name="web-server",
        health=HealthStatus.DOWN,
        reason="Node crashed",
        estimated_time_seconds=30,
    )
    chain = CascadeChain(trigger="test-fault", total_components=2)
    chain.effects.append(effect)

    fault = Fault(target_component_id="web-1", fault_type=FaultType.COMPONENT_DOWN)
    scenario = Scenario(
        id="test-1",
        name="Test Failure",
        description="Web server goes down",
        faults=[fault],
    )
    result = ScenarioResult(scenario=scenario, cascade=chain, risk_score=8.0)
    return SimulationReport(results=[result], resilience_score=55.0)


# ---------------------------------------------------------------------------
# Template helper functions
# ---------------------------------------------------------------------------

class TestHealthIcon:
    def test_healthy(self):
        assert _health_icon(HealthStatus.HEALTHY) == "OK"

    def test_degraded(self):
        assert _health_icon(HealthStatus.DEGRADED) == "WARN"

    def test_overloaded(self):
        assert _health_icon(HealthStatus.OVERLOADED) == "OVER"

    def test_down(self):
        assert _health_icon(HealthStatus.DOWN) == "DOWN"


class TestHealthClass:
    def test_healthy(self):
        assert _health_class(HealthStatus.HEALTHY) == "healthy"

    def test_degraded(self):
        assert _health_class(HealthStatus.DEGRADED) == "degraded"

    def test_overloaded(self):
        assert _health_class(HealthStatus.OVERLOADED) == "overloaded"

    def test_down(self):
        assert _health_class(HealthStatus.DOWN) == "down"


class TestScoreColor:
    def test_high_score(self):
        assert _score_color(90) == "green"
        assert _score_color(80) == "green"

    def test_medium_score(self):
        assert _score_color(70) == "yellow"
        assert _score_color(60) == "yellow"

    def test_low_score(self):
        assert _score_color(50) == "red"
        assert _score_color(0) == "red"


class TestUtilColor:
    def test_high_util(self):
        assert _util_color(90) == "red"
        assert _util_color(81) == "red"

    def test_medium_util(self):
        assert _util_color(70) == "yellow"
        assert _util_color(61) == "yellow"

    def test_low_util(self):
        assert _util_color(50) == "green"
        assert _util_color(0) == "green"


# ---------------------------------------------------------------------------
# Finding builder
# ---------------------------------------------------------------------------

class TestBuildFinding:
    def test_build_finding_structure(self, minimal_report):
        result = minimal_report.results[0]
        finding = _build_finding(result)
        assert finding["name"] == "Test Failure"
        assert finding["description"] == "Web server goes down"
        assert "8.0" in finding["risk_score"]
        assert len(finding["effects"]) == 1

    def test_build_finding_effect_details(self, minimal_report):
        result = minimal_report.results[0]
        finding = _build_finding(result)
        effect = finding["effects"][0]
        assert effect["component_name"] == "web-server"
        assert effect["health_icon"] == "DOWN"
        assert effect["health_class"] == "down"
        assert "crashed" in effect["reason"].lower()


# ---------------------------------------------------------------------------
# SVG dependency map
# ---------------------------------------------------------------------------

class TestDependencySvg:
    def test_svg_with_demo_graph(self, demo_graph):
        svg = _build_dependency_svg(demo_graph)
        assert "<svg" in svg
        assert "</svg>" in svg
        assert "arrowhead" in svg

    def test_svg_empty_graph(self):
        from faultray.model.graph import InfraGraph
        graph = InfraGraph()
        svg = _build_dependency_svg(graph)
        assert "No components" in svg

    def test_svg_contains_component_names(self, demo_graph):
        svg = _build_dependency_svg(demo_graph)
        # At least some component names should appear
        assert "nginx" in svg.lower() or "api-server" in svg.lower() or "postgres" in svg.lower()


# ---------------------------------------------------------------------------
# Full HTML report generation
# ---------------------------------------------------------------------------

class TestGenerateHtmlReport:
    def test_generate_returns_html(self, demo_report, demo_graph):
        html = generate_html_report(demo_report, demo_graph)
        assert "<!DOCTYPE html>" in html or "<html" in html
        assert "</html>" in html

    def test_report_contains_resilience_score(self, demo_report, demo_graph):
        html = generate_html_report(demo_report, demo_graph)
        assert "Resilience" in html

    def test_report_contains_components(self, demo_report, demo_graph):
        html = generate_html_report(demo_report, demo_graph)
        # Should contain component information
        assert "nginx" in html.lower() or "api-server" in html.lower()

    def test_report_contains_svg(self, demo_report, demo_graph):
        html = generate_html_report(demo_report, demo_graph)
        assert "<svg" in html

    def test_report_contains_timestamp(self, demo_report, demo_graph):
        html = generate_html_report(demo_report, demo_graph)
        assert "UTC" in html


class TestSaveHtmlReport:
    def test_save_creates_file(self, tmp_path, demo_report, demo_graph):
        output = tmp_path / "test-report.html"
        save_html_report(demo_report, demo_graph, output)
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "<html" in content.lower()
        assert "Resilience" in content

    def test_save_with_minimal_report(self, tmp_path, minimal_report):
        from faultray.model.graph import InfraGraph
        from faultray.model.components import Component, ComponentType

        graph = InfraGraph()
        graph.add_component(Component(
            id="web-1", name="web-server",
            type=ComponentType.WEB_SERVER, host="web01", port=80,
        ))
        output = tmp_path / "minimal-report.html"
        save_html_report(minimal_report, graph, output)
        assert output.exists()
