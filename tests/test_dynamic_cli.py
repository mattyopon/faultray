"""Tests for dynamic simulation CLI output and result handling."""

from dataclasses import dataclass, field
from io import StringIO

from rich.console import Console

from faultray.cli import _print_dynamic_results
from faultray.simulator.dynamic_engine import (
    DynamicScenario,
    DynamicScenarioResult,
    DynamicSimulationReport,
)


def _make_result(
    name: str = "test-scenario",
    peak_severity: float = 0.0,
    peak_time: int = 60,
    recovery: int | None = 120,
) -> DynamicScenarioResult:
    """Create a DynamicScenarioResult with the given peak severity."""
    scenario = DynamicScenario(
        id=f"test-{name}",
        name=name,
        description=f"Test scenario: {name}",
        duration_seconds=300,
        time_step_seconds=5,
    )
    return DynamicScenarioResult(
        scenario=scenario,
        peak_severity=peak_severity,
        peak_time_seconds=peak_time,
        recovery_time_seconds=recovery,
    )


def _capture_output(results: list) -> str:
    """Run _print_dynamic_results and capture the rendered text."""
    buf = StringIO()
    con = Console(file=buf, force_terminal=False, width=120)
    _print_dynamic_results(results, con)
    return buf.getvalue()


# --- Bug fix verification: peak_severity is float, not string ----------------


def test_critical_detected():
    """Results with peak_severity >= 7.0 must count as critical."""
    results = [_make_result("ddos-10x", peak_severity=8.5, recovery=None)]
    output = _capture_output(results)
    assert "Critical: 1" in output
    assert "CRITICAL" in output
    assert "ddos-10x" in output
    assert "severity: 8.5" in output


def test_warning_detected():
    """Results with peak_severity in [4.0, 7.0) must count as warning."""
    results = [_make_result("slow-drain", peak_severity=5.2)]
    output = _capture_output(results)
    assert "Warning: 1" in output
    assert "WARNING" in output
    assert "slow-drain" in output


def test_passed_detected():
    """Results with peak_severity < 4.0 count as passed (no detail output)."""
    results = [_make_result("minor-blip", peak_severity=2.0)]
    output = _capture_output(results)
    assert "Passed: 1" in output
    assert "Critical: 0" in output
    assert "Warning: 0" in output
    # Passed results should NOT appear in the detail section
    assert "minor-blip" not in output


def test_mixed_results():
    """Mixed bag of critical, warning, and passed results."""
    results = [
        _make_result("crit-1", peak_severity=9.0, recovery=None),
        _make_result("crit-2", peak_severity=7.0, recovery=200),
        _make_result("warn-1", peak_severity=4.0),
        _make_result("warn-2", peak_severity=6.9),
        _make_result("pass-1", peak_severity=3.9),
        _make_result("pass-2", peak_severity=0.0),
    ]
    output = _capture_output(results)
    assert "Total: 6" in output
    assert "Critical: 2" in output
    assert "Warning: 2" in output
    assert "Passed: 2" in output


def test_empty_results():
    """Empty results list should display a friendly message."""
    output = _capture_output([])
    assert "No dynamic scenarios" in output


def test_recovery_none_shows_no_recovery():
    """When recovery_time_seconds is None, show 'no recovery'."""
    results = [_make_result("no-recover", peak_severity=8.0, recovery=None)]
    output = _capture_output(results)
    assert "no recovery" in output


def test_recovery_present_shows_seconds():
    """When recovery_time_seconds is set, show the value."""
    results = [_make_result("quick-fix", peak_severity=7.5, recovery=45)]
    output = _capture_output(results)
    assert "45s" in output


# --- DynamicSimulationReport property tests ----------------------------------


def test_report_critical_findings():
    """DynamicSimulationReport.critical_findings uses is_critical property."""
    report = DynamicSimulationReport(
        results=[
            _make_result("a", peak_severity=8.0),
            _make_result("b", peak_severity=3.0),
            _make_result("c", peak_severity=7.0),
        ]
    )
    assert len(report.critical_findings) == 2
    assert len(report.warnings) == 0
    assert len(report.passed) == 1


def test_report_warnings():
    """DynamicSimulationReport.warnings uses is_warning property."""
    report = DynamicSimulationReport(
        results=[
            _make_result("a", peak_severity=4.0),
            _make_result("b", peak_severity=6.9),
            _make_result("c", peak_severity=3.9),
        ]
    )
    assert len(report.critical_findings) == 0
    assert len(report.warnings) == 2
    assert len(report.passed) == 1


# --- DynamicScenarioResult property boundary tests ---------------------------


def test_severity_boundary_critical():
    """Exactly 7.0 is critical."""
    r = _make_result("boundary", peak_severity=7.0)
    assert r.is_critical is True
    assert r.is_warning is False


def test_severity_boundary_warning_upper():
    """6.999... is warning (not critical)."""
    r = _make_result("boundary", peak_severity=6.999)
    assert r.is_critical is False
    assert r.is_warning is True


def test_severity_boundary_warning_lower():
    """Exactly 4.0 is warning."""
    r = _make_result("boundary", peak_severity=4.0)
    assert r.is_critical is False
    assert r.is_warning is True


def test_severity_boundary_passed():
    """3.999... is passed (not warning)."""
    r = _make_result("boundary", peak_severity=3.999)
    assert r.is_critical is False
    assert r.is_warning is False


def test_severity_zero():
    """Zero severity is passed."""
    r = _make_result("zero", peak_severity=0.0)
    assert r.is_critical is False
    assert r.is_warning is False
