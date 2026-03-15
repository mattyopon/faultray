"""Tests for SARIF and Excel export formats."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrasim.model.components import Component, ComponentType, HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.reporter.export import (
    export_excel,
    export_json,
    export_sarif,
    export_sarif_file,
)
from infrasim.simulator.cascade import CascadeChain, CascadeEffect
from infrasim.simulator.engine import ScenarioResult, SimulationEngine, SimulationReport
from infrasim.simulator.scenarios import Scenario


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_graph() -> InfraGraph:
    """Build a minimal graph for testing."""
    graph = InfraGraph()
    graph.add_component(
        Component(id="web", name="Web Server", type=ComponentType.WEB_SERVER)
    )
    graph.add_component(
        Component(id="db", name="Database", type=ComponentType.DATABASE)
    )
    return graph


@pytest.fixture
def sample_report(sample_graph: InfraGraph) -> SimulationReport:
    """Build a SimulationReport with mixed severity scenarios."""
    # Critical scenario
    critical_scenario = Scenario(
        id="s-critical-1",
        name="DB Total Failure",
        description="Primary database goes offline",
        faults=[],
    )
    critical_cascade = CascadeChain(trigger="DB Total Failure", total_components=2)
    critical_cascade.effects.append(
        CascadeEffect(
            component_id="db",
            component_name="Database",
            health=HealthStatus.DOWN,
            reason="Primary node unreachable",
            estimated_time_seconds=30,
        )
    )
    critical_cascade.likelihood = 0.8

    # Warning scenario
    warning_scenario = Scenario(
        id="s-warning-1",
        name="Cache Degradation",
        description="Cache hit rate drops significantly",
        faults=[],
    )
    warning_cascade = CascadeChain(trigger="Cache Degradation", total_components=2)
    warning_cascade.effects.append(
        CascadeEffect(
            component_id="web",
            component_name="Web Server",
            health=HealthStatus.DEGRADED,
            reason="Increased latency due to cache miss",
            estimated_time_seconds=10,
        )
    )
    warning_cascade.likelihood = 0.3

    # Passed scenario
    passed_scenario = Scenario(
        id="s-passed-1",
        name="Minor Network Jitter",
        description="Slight increase in network latency",
        faults=[],
    )
    passed_cascade = CascadeChain(trigger="Minor Network Jitter", total_components=2)

    results = [
        ScenarioResult(scenario=critical_scenario, cascade=critical_cascade, risk_score=8.5),
        ScenarioResult(scenario=warning_scenario, cascade=warning_cascade, risk_score=5.0),
        ScenarioResult(scenario=passed_scenario, cascade=passed_cascade, risk_score=1.0),
    ]

    return SimulationReport(
        results=results,
        resilience_score=65.0,
        total_generated=3,
    )


# ---------------------------------------------------------------------------
# SARIF export tests
# ---------------------------------------------------------------------------


class TestSarifExport:
    def test_sarif_valid_json(self, sample_report: SimulationReport):
        """export_sarif() should return valid JSON."""
        sarif_str = export_sarif(sample_report)
        data = json.loads(sarif_str)
        assert data["version"] == "2.1.0"

    def test_sarif_schema(self, sample_report: SimulationReport):
        """SARIF output should have the correct schema structure."""
        data = json.loads(export_sarif(sample_report))
        assert "$schema" in data
        assert "runs" in data
        assert len(data["runs"]) == 1

        run = data["runs"][0]
        assert "tool" in run
        assert run["tool"]["driver"]["name"] == "FaultZero"
        assert "rules" in run["tool"]["driver"]
        assert "results" in run

    def test_sarif_includes_critical_and_warning(self, sample_report: SimulationReport):
        """SARIF results should include critical and warning findings only."""
        data = json.loads(export_sarif(sample_report))
        results = data["runs"][0]["results"]

        # Should have 2 results (critical + warning), not the passed one
        assert len(results) == 2
        levels = {r["level"] for r in results}
        assert "error" in levels
        assert "warning" in levels

    def test_sarif_rules_match_results(self, sample_report: SimulationReport):
        """Each SARIF result should reference a defined rule."""
        data = json.loads(export_sarif(sample_report))
        rules = data["runs"][0]["tool"]["driver"]["rules"]
        results = data["runs"][0]["results"]

        rule_ids = {r["id"] for r in rules}
        for result in results:
            assert result["ruleId"] in rule_ids

    def test_sarif_file_export(self, sample_report: SimulationReport, tmp_path: Path):
        """export_sarif_file() should write SARIF to a file."""
        out = tmp_path / "results.sarif"
        path = export_sarif_file(sample_report, out)
        assert path.exists()

        data = json.loads(path.read_text())
        assert data["version"] == "2.1.0"

    def test_sarif_empty_report(self):
        """export_sarif() with no findings should produce valid but empty results."""
        report = SimulationReport(results=[], resilience_score=100.0)
        data = json.loads(export_sarif(report))
        assert data["runs"][0]["results"] == []
        assert data["runs"][0]["tool"]["driver"]["rules"] == []


# ---------------------------------------------------------------------------
# Excel export tests
# ---------------------------------------------------------------------------


class TestExcelExport:
    def _has_openpyxl(self) -> bool:
        try:
            import openpyxl
            return True
        except ImportError:
            return False

    def test_excel_export_creates_file(self, sample_report: SimulationReport, tmp_path: Path):
        """export_excel() should create an .xlsx file."""
        if not self._has_openpyxl():
            pytest.skip("openpyxl not installed")

        out = tmp_path / "results.xlsx"
        path = export_excel(sample_report, out)
        assert path.exists()
        assert path.suffix == ".xlsx"

    def test_excel_has_two_sheets(self, sample_report: SimulationReport, tmp_path: Path):
        """Excel file should have Summary and Results sheets."""
        if not self._has_openpyxl():
            pytest.skip("openpyxl not installed")

        import openpyxl

        out = tmp_path / "results.xlsx"
        export_excel(sample_report, out)

        wb = openpyxl.load_workbook(str(out))
        assert "Summary" in wb.sheetnames
        assert "Results" in wb.sheetnames

    def test_excel_summary_values(self, sample_report: SimulationReport, tmp_path: Path):
        """Summary sheet should contain correct values."""
        if not self._has_openpyxl():
            pytest.skip("openpyxl not installed")

        import openpyxl

        out = tmp_path / "results.xlsx"
        export_excel(sample_report, out)

        wb = openpyxl.load_workbook(str(out))
        ws = wb["Summary"]
        assert ws["B3"].value == 65.0  # resilience score
        assert ws["B4"].value == 3     # total scenarios
        assert ws["B5"].value == 1     # critical
        assert ws["B6"].value == 1     # warning
        assert ws["B7"].value == 1     # passed

    def test_excel_results_data(self, sample_report: SimulationReport, tmp_path: Path):
        """Results sheet should contain scenario data rows."""
        if not self._has_openpyxl():
            pytest.skip("openpyxl not installed")

        import openpyxl

        out = tmp_path / "results.xlsx"
        export_excel(sample_report, out)

        wb = openpyxl.load_workbook(str(out))
        ws = wb["Results"]
        # Row 1 is header, data starts at row 2
        assert ws.max_row >= 2  # At least header + 1 data row

    def test_excel_empty_report(self, tmp_path: Path):
        """export_excel() should work with an empty report."""
        if not self._has_openpyxl():
            pytest.skip("openpyxl not installed")

        report = SimulationReport(results=[], resilience_score=100.0)
        out = tmp_path / "empty.xlsx"
        path = export_excel(report, out)
        assert path.exists()

    def test_excel_missing_openpyxl(self, sample_report: SimulationReport, tmp_path: Path):
        """export_excel() should raise ImportError with helpful message when openpyxl missing."""
        import importlib
        import sys

        # Temporarily hide openpyxl
        openpyxl_mod = sys.modules.get("openpyxl")
        sys.modules["openpyxl"] = None  # type: ignore

        try:
            with pytest.raises(ImportError, match="openpyxl"):
                export_excel(sample_report, tmp_path / "test.xlsx")
        finally:
            if openpyxl_mod is not None:
                sys.modules["openpyxl"] = openpyxl_mod
            else:
                sys.modules.pop("openpyxl", None)

    def test_excel_creates_parent_dirs(self, sample_report: SimulationReport, tmp_path: Path):
        """export_excel() should create parent directories."""
        if not self._has_openpyxl():
            pytest.skip("openpyxl not installed")

        out = tmp_path / "nested" / "dir" / "results.xlsx"
        path = export_excel(sample_report, out)
        assert path.exists()
