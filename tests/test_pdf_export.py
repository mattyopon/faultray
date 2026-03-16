"""Tests for PDF-ready HTML and Markdown report export."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from faultray.cli import app
from faultray.model.components import HealthStatus
from faultray.model.demo import create_demo_graph
from faultray.reporter.pdf_report import (
    export_markdown,
    generate_pdf_ready_html,
    save_pdf_ready_html,
)
from faultray.simulator.cascade import CascadeChain, CascadeEffect
from faultray.simulator.engine import ScenarioResult, SimulationEngine, SimulationReport
from faultray.simulator.scenarios import Fault, FaultType, Scenario

runner = CliRunner()


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
    """A minimal SimulationReport for unit testing."""
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
    result = ScenarioResult(scenario=scenario, cascade=chain, risk_score=8.5)
    return SimulationReport(results=[result], resilience_score=42.0)


# ---------------------------------------------------------------------------
# PDF-ready HTML tests
# ---------------------------------------------------------------------------

class TestPdfReadyHtml:
    def test_contains_print_media_css(self, demo_report, demo_graph):
        html = generate_pdf_ready_html(demo_report, demo_graph)
        assert '@media print' in html
        assert '@page' in html
        assert 'size: A4' in html

    def test_contains_original_html_content(self, demo_report, demo_graph):
        html = generate_pdf_ready_html(demo_report, demo_graph)
        assert "FaultRay" in html or "FaultRay" in html
        assert "</html>" in html

    def test_save_pdf_ready_html(self, demo_report, demo_graph, tmp_path):
        output = tmp_path / "report.html"
        result_path = save_pdf_ready_html(demo_report, demo_graph, output)
        assert result_path.exists()
        content = result_path.read_text(encoding="utf-8")
        assert '@media print' in content
        assert '@page' in content

    def test_save_creates_parent_dirs(self, demo_report, demo_graph, tmp_path):
        output = tmp_path / "sub" / "dir" / "report.html"
        result_path = save_pdf_ready_html(demo_report, demo_graph, output)
        assert result_path.exists()


# ---------------------------------------------------------------------------
# Markdown export tests
# ---------------------------------------------------------------------------

class TestMarkdownExport:
    def test_contains_header(self, demo_report, demo_graph):
        md = export_markdown(demo_report, demo_graph)
        assert "# FaultRay Chaos Simulation Report" in md

    def test_contains_summary_table(self, demo_report, demo_graph):
        md = export_markdown(demo_report, demo_graph)
        assert "Resilience Score" in md
        assert "Total Components" in md

    def test_contains_components_section(self, demo_report, demo_graph):
        md = export_markdown(demo_report, demo_graph)
        assert "## Components" in md

    def test_critical_findings_section(self, minimal_report, demo_graph):
        md = export_markdown(minimal_report, demo_graph)
        assert "## Critical Findings" in md
        assert "Test Failure" in md

    def test_write_to_file(self, demo_report, demo_graph, tmp_path):
        output = tmp_path / "report.md"
        md = export_markdown(demo_report, demo_graph, output)
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert content == md

    def test_without_output_path(self, demo_report, demo_graph):
        md = export_markdown(demo_report, demo_graph, output_path=None)
        assert isinstance(md, str)
        assert len(md) > 0


# ---------------------------------------------------------------------------
# CLI flag tests
# ---------------------------------------------------------------------------

class TestCliFlags:
    def _create_model_file(self, tmp_path: Path) -> Path:
        graph = create_demo_graph()
        model_path = tmp_path / "test-model.json"
        graph.save(model_path)
        return model_path

    def test_pdf_flag(self, tmp_path):
        model_path = self._create_model_file(tmp_path)
        output = tmp_path / "out.html"
        result = runner.invoke(
            app,
            ["simulate", "--model", str(model_path), "--pdf", str(output)],
        )
        assert result.exit_code == 0
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert '@media print' in content

    def test_md_flag(self, tmp_path):
        model_path = self._create_model_file(tmp_path)
        output = tmp_path / "out.md"
        result = runner.invoke(
            app,
            ["simulate", "--model", str(model_path), "--md", str(output)],
        )
        assert result.exit_code == 0
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "# FaultRay" in content

    def test_both_flags(self, tmp_path):
        model_path = self._create_model_file(tmp_path)
        pdf_out = tmp_path / "out.html"
        md_out = tmp_path / "out.md"
        result = runner.invoke(
            app,
            [
                "simulate",
                "--model", str(model_path),
                "--pdf", str(pdf_out),
                "--md", str(md_out),
            ],
        )
        assert result.exit_code == 0
        assert pdf_out.exists()
        assert md_out.exists()
