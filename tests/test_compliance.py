"""Tests for the DORA compliance report generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.ai.analyzer import AIAnalysisReport, AIRecommendation, FaultRayAnalyzer
from faultray.model.components import ComponentType, HealthStatus
from faultray.model.demo import create_demo_graph
from faultray.reporter.compliance import (
    _esc,
    _health_badge,
    _severity_badge,
    generate_dora_report,
)
from faultray.simulator.engine import SimulationEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def demo_graph():
    return create_demo_graph()


@pytest.fixture
def demo_sim_report(demo_graph):
    engine = SimulationEngine(demo_graph)
    return engine.run_all_defaults()


@pytest.fixture
def demo_ai_report(demo_graph, demo_sim_report):
    analyzer = FaultRayAnalyzer()
    return analyzer.analyze(demo_graph, demo_sim_report)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestEsc:
    def test_escapes_html_entities(self):
        assert _esc("<script>") == "&lt;script&gt;"
        assert _esc("a & b") == "a &amp; b"
        assert _esc('"hello"') == "&quot;hello&quot;"

    def test_plain_text_unchanged(self):
        assert _esc("hello world") == "hello world"

    def test_converts_non_string(self):
        assert _esc(42) == "42"


class TestSeverityBadge:
    def test_critical_badge(self):
        badge = _severity_badge("critical")
        assert "CRITICAL" in badge
        assert "#dc3545" in badge  # red color

    def test_high_badge(self):
        badge = _severity_badge("high")
        assert "HIGH" in badge
        assert "#fd7e14" in badge  # orange color

    def test_medium_badge(self):
        badge = _severity_badge("medium")
        assert "MEDIUM" in badge

    def test_low_badge(self):
        badge = _severity_badge("low")
        assert "LOW" in badge
        assert "#28a745" in badge  # green color

    def test_unknown_severity(self):
        badge = _severity_badge("unknown")
        assert "UNKNOWN" in badge
        assert "#6c757d" in badge  # gray fallback


class TestHealthBadge:
    def test_healthy_badge(self):
        badge = _health_badge(HealthStatus.HEALTHY)
        assert "HEALTHY" in badge
        assert "#28a745" in badge

    def test_degraded_badge(self):
        badge = _health_badge(HealthStatus.DEGRADED)
        assert "DEGRADED" in badge

    def test_overloaded_badge(self):
        badge = _health_badge(HealthStatus.OVERLOADED)
        assert "OVERLOADED" in badge

    def test_down_badge(self):
        badge = _health_badge(HealthStatus.DOWN)
        assert "DOWN" in badge
        assert "#dc3545" in badge


# ---------------------------------------------------------------------------
# Full DORA report generation
# ---------------------------------------------------------------------------

class TestGenerateDoraReport:
    def test_generates_html_file(self, tmp_path, demo_graph, demo_sim_report, demo_ai_report):
        output = tmp_path / "dora-test.html"
        result_path = generate_dora_report(demo_graph, demo_sim_report, demo_ai_report, output)
        assert result_path.exists()
        content = result_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_contains_dora_title(self, tmp_path, demo_graph, demo_sim_report, demo_ai_report):
        output = tmp_path / "dora-title.html"
        generate_dora_report(demo_graph, demo_sim_report, demo_ai_report, output)
        content = output.read_text(encoding="utf-8")
        assert "DORA Compliance Report" in content

    def test_contains_dora_article_references(self, tmp_path, demo_graph, demo_sim_report, demo_ai_report):
        output = tmp_path / "dora-articles.html"
        generate_dora_report(demo_graph, demo_sim_report, demo_ai_report, output)
        content = output.read_text(encoding="utf-8")
        # DORA articles should be referenced
        assert "Art. 5-16" in content or "Art. 5" in content
        assert "Art. 24-27" in content or "Art. 24" in content
        assert "Art. 28-30" in content or "Art. 28" in content
        assert "Art. 17-23" in content or "Art. 17" in content

    def test_contains_risk_assessment(self, tmp_path, demo_graph, demo_sim_report, demo_ai_report):
        output = tmp_path / "dora-risk.html"
        generate_dora_report(demo_graph, demo_sim_report, demo_ai_report, output)
        content = output.read_text(encoding="utf-8")
        assert "ICT Risk Management" in content

    def test_contains_resilience_testing(self, tmp_path, demo_graph, demo_sim_report, demo_ai_report):
        output = tmp_path / "dora-testing.html"
        generate_dora_report(demo_graph, demo_sim_report, demo_ai_report, output)
        content = output.read_text(encoding="utf-8")
        assert "Resilience Testing" in content
        assert "Resilience Score" in content

    def test_contains_remediation_plan(self, tmp_path, demo_graph, demo_sim_report, demo_ai_report):
        output = tmp_path / "dora-remediation.html"
        generate_dora_report(demo_graph, demo_sim_report, demo_ai_report, output)
        content = output.read_text(encoding="utf-8")
        assert "Remediation Plan" in content

    def test_contains_top_risks(self, tmp_path, demo_graph, demo_sim_report, demo_ai_report):
        output = tmp_path / "dora-risks.html"
        generate_dora_report(demo_graph, demo_sim_report, demo_ai_report, output)
        content = output.read_text(encoding="utf-8")
        assert "Top Risks" in content

    def test_contains_executive_summary(self, tmp_path, demo_graph, demo_sim_report, demo_ai_report):
        output = tmp_path / "dora-summary.html"
        generate_dora_report(demo_graph, demo_sim_report, demo_ai_report, output)
        content = output.read_text(encoding="utf-8")
        assert "Executive Summary" in content

    def test_contains_timestamp(self, tmp_path, demo_graph, demo_sim_report, demo_ai_report):
        output = tmp_path / "dora-time.html"
        generate_dora_report(demo_graph, demo_sim_report, demo_ai_report, output)
        content = output.read_text(encoding="utf-8")
        assert "UTC" in content

    def test_incident_impact_section(self, tmp_path, demo_graph, demo_sim_report, demo_ai_report):
        output = tmp_path / "dora-incident.html"
        generate_dora_report(demo_graph, demo_sim_report, demo_ai_report, output)
        content = output.read_text(encoding="utf-8")
        assert "Incident Impact" in content or "ICT Incident" in content

    def test_third_party_section(self, tmp_path, demo_graph, demo_sim_report, demo_ai_report):
        output = tmp_path / "dora-3rd.html"
        generate_dora_report(demo_graph, demo_sim_report, demo_ai_report, output)
        content = output.read_text(encoding="utf-8")
        assert "Third-Party" in content
