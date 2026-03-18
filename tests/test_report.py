"""Tests for the CLI report display functions."""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from faultray.model.components import HealthStatus
from faultray.model.demo import create_demo_graph
from faultray.reporter.report import (
    _health_color,
    _health_icon,
    _risk_label,
    print_infrastructure_summary,
    print_simulation_report,
)
from faultray.simulator.cascade import CascadeChain, CascadeEffect
from faultray.simulator.engine import ScenarioResult, SimulationEngine, SimulationReport
from faultray.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capture_console() -> tuple[Console, StringIO]:
    """Create a console that captures output to a string buffer."""
    buf = StringIO()
    con = Console(file=buf, force_terminal=False, width=120)
    return con, buf


def _make_result(name: str, risk: float, health: HealthStatus = HealthStatus.DOWN) -> ScenarioResult:
    """Build a minimal ScenarioResult for testing."""
    effect = CascadeEffect(
        component_id="comp-1",
        component_name="test-comp",
        health=health,
        reason="Test failure",
        estimated_time_seconds=30,
    )
    chain = CascadeChain(trigger="test", total_components=1)
    chain.effects.append(effect)
    fault = Fault(target_component_id="comp-1", fault_type=FaultType.COMPONENT_DOWN)
    scenario = Scenario(
        id=f"scenario-{name}",
        name=name,
        description=f"Test scenario: {name}",
        faults=[fault],
    )
    return ScenarioResult(scenario=scenario, cascade=chain, risk_score=risk)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestHealthColor:
    def test_healthy(self):
        assert _health_color(HealthStatus.HEALTHY) == "green"

    def test_degraded(self):
        assert _health_color(HealthStatus.DEGRADED) == "yellow"

    def test_overloaded(self):
        assert _health_color(HealthStatus.OVERLOADED) == "red"

    def test_down(self):
        assert _health_color(HealthStatus.DOWN) == "bold red"


class TestHealthIcon:
    def test_healthy(self):
        icon = _health_icon(HealthStatus.HEALTHY)
        assert "OK" in icon

    def test_degraded(self):
        icon = _health_icon(HealthStatus.DEGRADED)
        assert "WARN" in icon

    def test_overloaded(self):
        icon = _health_icon(HealthStatus.OVERLOADED)
        assert "OVERLOAD" in icon

    def test_down(self):
        icon = _health_icon(HealthStatus.DOWN)
        assert "DOWN" in icon


class TestRiskLabel:
    def test_critical(self):
        label = _risk_label(8.5)
        assert "CRITICAL" in label
        assert "8.5" in label

    def test_warning(self):
        label = _risk_label(5.0)
        assert "WARNING" in label
        assert "5.0" in label

    def test_low(self):
        label = _risk_label(2.0)
        assert "LOW" in label
        assert "2.0" in label

    def test_boundary_critical(self):
        label = _risk_label(7.0)
        assert "CRITICAL" in label

    def test_boundary_warning(self):
        label = _risk_label(4.0)
        assert "WARNING" in label

    def test_boundary_low(self):
        label = _risk_label(3.9)
        assert "LOW" in label


# ---------------------------------------------------------------------------
# Infrastructure summary printing
# ---------------------------------------------------------------------------

class TestPrintInfrastructureSummary:
    def test_prints_without_crashing(self):
        graph = create_demo_graph()
        con, buf = _capture_console()
        print_infrastructure_summary(graph, con)
        output = buf.getvalue()
        assert len(output) > 0

    def test_contains_overview_header(self):
        graph = create_demo_graph()
        con, buf = _capture_console()
        print_infrastructure_summary(graph, con)
        output = buf.getvalue()
        assert "Infrastructure Overview" in output

    def test_contains_component_count(self):
        graph = create_demo_graph()
        con, buf = _capture_console()
        print_infrastructure_summary(graph, con)
        output = buf.getvalue()
        assert "Components" in output
        assert "9" in output  # 9 demo components

    def test_contains_resilience_score(self):
        graph = create_demo_graph()
        con, buf = _capture_console()
        print_infrastructure_summary(graph, con)
        output = buf.getvalue()
        assert "Resilience Score" in output

    def test_uses_default_console(self):
        """Should not crash when no console is provided."""
        graph = create_demo_graph()
        # Should use default console - just check it doesn't crash
        print_infrastructure_summary(graph)


# ---------------------------------------------------------------------------
# Simulation report printing
# ---------------------------------------------------------------------------

class TestPrintSimulationReport:
    def test_prints_without_crashing(self):
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults()
        con, buf = _capture_console()
        print_simulation_report(report, con)
        output = buf.getvalue()
        assert len(output) > 0

    def test_contains_resilience_score(self):
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults()
        con, buf = _capture_console()
        print_simulation_report(report, con)
        output = buf.getvalue()
        assert "Resilience Score" in output

    def test_shows_critical_findings(self):
        result = _make_result("critical-test", 8.5)
        report = SimulationReport(results=[result], resilience_score=30.0)
        con, buf = _capture_console()
        print_simulation_report(report, con)
        output = buf.getvalue()
        assert "CRITICAL" in output
        assert "critical-test" in output

    def test_shows_warnings(self):
        result = _make_result("warning-test", 5.0)
        report = SimulationReport(results=[result], resilience_score=60.0)
        con, buf = _capture_console()
        print_simulation_report(report, con)
        output = buf.getvalue()
        assert "WARNING" in output

    def test_shows_passed_count(self):
        result = _make_result("safe-test", 1.0, health=HealthStatus.HEALTHY)
        report = SimulationReport(results=[result], resilience_score=95.0)
        con, buf = _capture_console()
        print_simulation_report(report, con)
        output = buf.getvalue()
        assert "passed" in output.lower()

    def test_mixed_results(self):
        results = [
            _make_result("crit-1", 9.0),
            _make_result("warn-1", 5.0),
            _make_result("pass-1", 1.0, health=HealthStatus.HEALTHY),
        ]
        report = SimulationReport(results=results, resilience_score=50.0)
        con, buf = _capture_console()
        print_simulation_report(report, con)
        output = buf.getvalue()
        assert "CRITICAL" in output
        assert "Resilience Score" in output

    def test_empty_report(self):
        report = SimulationReport(results=[], resilience_score=100.0)
        con, buf = _capture_console()
        print_simulation_report(report, con)
        output = buf.getvalue()
        assert "100" in output

    def test_uses_default_console(self):
        """Should not crash when no console is provided."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults()
        print_simulation_report(report)

    def test_cascade_tree_in_output(self):
        """Critical findings should include cascade path details."""
        result = _make_result("cascade-test", 8.0)
        report = SimulationReport(results=[result], resilience_score=40.0)
        con, buf = _capture_console()
        print_simulation_report(report, con)
        output = buf.getvalue()
        assert "test-comp" in output
