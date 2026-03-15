"""Tests for the Executive PDF-Style HTML Report Generator."""

from __future__ import annotations

import pytest

from infrasim.ai.analyzer import AIAnalysisReport, AIRecommendation
from infrasim.model.components import (
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    SecurityProfile,
)
from infrasim.model.graph import InfraGraph
from infrasim.reporter.executive_pdf import (
    ExecutiveReport,
    ExecutiveReportGenerator,
    ReportSection,
    _grade_color,
    _score_to_grade,
    _traffic_light_class,
    _traffic_light_label,
)
from infrasim.simulator.cascade import CascadeChain
from infrasim.simulator.engine import ScenarioResult, SimulationReport
from infrasim.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_test_graph() -> InfraGraph:
    """Build a simple test graph."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=2,
        port=443,
        cost_profile=CostProfile(hourly_infra_cost=5.0, revenue_per_minute=50.0),
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=1,
        port=443,
        cost_profile=CostProfile(hourly_infra_cost=10.0, revenue_per_minute=100.0),
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            auth_required=True,
        ),
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        replicas=1,
        port=5432,
        cost_profile=CostProfile(hourly_infra_cost=20.0, revenue_per_minute=200.0),
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app"))
    graph.add_dependency(Dependency(source_id="app", target_id="db"))
    return graph


def _build_test_sim_report() -> SimulationReport:
    """Build a test simulation report."""
    scenario_pass = Scenario(
        id="lb-failure",
        name="Load Balancer Failure",
        description="Test LB failover",
        faults=[Fault(target_component_id="lb", fault_type=FaultType.COMPONENT_DOWN)],
    )
    scenario_critical = Scenario(
        id="db-spof",
        name="Database SPOF",
        description="Database single point of failure",
        faults=[Fault(target_component_id="db", fault_type=FaultType.COMPONENT_DOWN)],
    )

    report = SimulationReport(
        results=[
            ScenarioResult(
                scenario=scenario_pass,
                cascade=CascadeChain(trigger="lb"),
                risk_score=2.0,
            ),
            ScenarioResult(
                scenario=scenario_critical,
                cascade=CascadeChain(trigger="db"),
                risk_score=8.5,
            ),
        ],
        resilience_score=65.0,
    )
    return report


def _build_test_ai_report() -> AIAnalysisReport:
    """Build a test AI analysis report."""
    return AIAnalysisReport(
        summary="Infrastructure shows moderate resilience with 1 critical SPOF identified.",
        top_risks=[
            "Database is a single point of failure",
            "App server lacks redundancy",
            "No circuit breakers configured",
        ],
        recommendations=[
            AIRecommendation(
                component_id="db",
                category="spof",
                severity="critical",
                title="Add database replica",
                description="Database has no redundancy and is a SPOF.",
                remediation="Add a read replica and enable failover.",
                estimated_impact="2.5 -> 3.5 nines",
                effort="medium",
            ),
            AIRecommendation(
                component_id="app",
                category="spof",
                severity="high",
                title="Scale app server",
                description="App server has only 1 replica.",
                remediation="Increase replicas to 3 and enable autoscaling.",
                estimated_impact="3.5 -> 4.0 nines",
                effort="low",
            ),
            AIRecommendation(
                component_id="app",
                category="config",
                severity="medium",
                title="Add circuit breakers",
                description="Dependencies lack circuit breakers.",
                remediation="Enable circuit breakers on all dependency edges.",
                estimated_impact="Reduced cascade failure risk",
                effort="low",
            ),
            AIRecommendation(
                component_id="lb",
                category="config",
                severity="low",
                title="Review load balancer health checks",
                description="Health check interval could be optimized.",
                remediation="Reduce health check interval to 5s.",
                estimated_impact="Faster failover detection",
                effort="high",
            ),
        ],
        availability_assessment="Tier 2: Standard availability (2-3 nines)",
        upgrade_path="Add database replicas and app server autoscaling to reach 4 nines.",
        estimated_current_nines=2.5,
        theoretical_max_nines=4.0,
    )


# ---------------------------------------------------------------------------
# Grade calculation tests
# ---------------------------------------------------------------------------


class TestGradeCalculation:
    def test_score_to_grade_a_plus(self):
        assert _score_to_grade(95) == "A+"
        assert _score_to_grade(100) == "A+"

    def test_score_to_grade_a(self):
        assert _score_to_grade(90) == "A"
        assert _score_to_grade(94) == "A"

    def test_score_to_grade_b(self):
        assert _score_to_grade(75) == "B"
        assert _score_to_grade(79) == "B"

    def test_score_to_grade_c(self):
        assert _score_to_grade(60) == "C"
        assert _score_to_grade(64) == "C"

    def test_score_to_grade_d(self):
        assert _score_to_grade(45) == "D"
        assert _score_to_grade(49) == "D"

    def test_score_to_grade_f(self):
        assert _score_to_grade(0) == "F"
        assert _score_to_grade(39) == "F"

    def test_grade_color_mapping(self):
        assert _grade_color("A+") == "#28a745"
        assert _grade_color("B") == "#5cb85c"
        assert _grade_color("C") == "#ffc107"
        assert _grade_color("D") == "#fd7e14"
        assert _grade_color("F") == "#dc3545"


class TestTrafficLight:
    def test_green_for_high_score(self):
        assert _traffic_light_class(90) == "status-green"
        assert _traffic_light_label(90) == "Passed"

    def test_yellow_for_medium_score(self):
        assert _traffic_light_class(60) == "status-yellow"
        assert _traffic_light_label(60) == "Needs Attention"

    def test_red_for_low_score(self):
        assert _traffic_light_class(30) == "status-red"
        assert _traffic_light_label(30) == "Critical"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestDataClasses:
    def test_report_section(self):
        section = ReportSection(
            title="Test Section",
            content_html="<p>Content</p>",
            page_break_before=True,
        )
        assert section.title == "Test Section"
        assert section.page_break_before is True

    def test_executive_report(self):
        from datetime import datetime, timezone
        report = ExecutiveReport(
            title="Test Report",
            company_name="Acme Corp",
            assessment_date=datetime.now(timezone.utc),
            prepared_by="Tester",
            executive_summary="All good.",
            resilience_grade="B+",
            resilience_score=80.0,
            financial_risk="$50,000",
            key_findings=["Finding 1"],
            recommendation_count=3,
            compliance_status={"soc2": 85.0},
        )
        assert report.company_name == "Acme Corp"
        assert report.resilience_grade == "B+"


# ---------------------------------------------------------------------------
# Generator tests
# ---------------------------------------------------------------------------


class TestExecutiveReportGenerator:
    def test_generate_returns_html(self):
        """generate() should return a valid HTML string."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report, company_name="Acme Corp")

        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html
        assert "Acme Corp" in html
        assert "</html>" in html

    def test_html_is_self_contained(self):
        """HTML should have inline CSS, no external dependencies."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "<style>" in html
        # Should not reference external CSS/JS
        assert 'href="http' not in html
        assert '<script src=' not in html

    def test_html_has_no_javascript(self):
        """HTML should have no JavaScript (for PDF compatibility)."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "<script>" not in html
        assert "<script " not in html

    def test_html_contains_print_styles(self):
        """HTML should include @media print CSS."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "@media print" in html
        assert "page-break" in html or "break-after" in html

    def test_html_contains_cover_page(self):
        """HTML should have a cover page."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report, company_name="TestCo")

        assert "TestCo" in html
        assert "Resilience Grade" in html
        assert "CONFIDENTIAL" in html

    def test_html_contains_executive_summary(self):
        """HTML should have an executive summary section."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "Executive Summary" in html
        assert "Resilience Score" in html
        assert "SLA Achievement" in html

    def test_html_contains_risk_overview(self):
        """HTML should have a risk overview section."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "Risk Overview" in html
        assert "Critical" in html

    def test_html_contains_financial_impact(self):
        """HTML should have a financial impact section."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "Financial Impact" in html
        assert "Cost of Downtime" in html
        assert "ROI" in html

    def test_html_contains_compliance(self):
        """HTML should have a compliance section."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "Compliance Status" in html

    def test_html_contains_recommendations(self):
        """HTML should have a recommendations section."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "Recommendations" in html
        assert "Add database replica" in html

    def test_html_contains_effort_impact_matrix(self):
        """HTML should have an effort/impact matrix."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "Effort / Impact Matrix" in html
        assert "Quick Wins" in html
        assert "Strategic" in html

    def test_html_contains_trend_section(self):
        """HTML should have a trend/outlook section."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "Resilience Trend" in html
        assert "nines" in html
        assert "Upgrade Path" in html

    def test_html_contains_appendix(self):
        """HTML should have a technical appendix."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "Appendix" in html
        assert "Component Inventory" in html
        assert "Scenario Results" in html

    def test_grade_in_cover_page(self):
        """Cover page should show the correct grade."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        grade = _score_to_grade(sim_report.resilience_score)
        assert grade in html

    def test_spof_detection(self):
        """Report should identify SPOFs."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "SPOF" in html

    def test_custom_company_name(self):
        """Company name should appear throughout the report."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(
            graph, sim_report, ai_report,
            company_name="Mega Corp International",
        )

        assert "Mega Corp International" in html

    def test_a4_page_size_in_css(self):
        """CSS should specify A4 page size for printing."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)

        assert "A4" in html

    def test_html_escaping(self):
        """Special characters in company name should be escaped."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(
            graph, sim_report, ai_report,
            company_name='<script>alert("xss")</script>',
        )

        assert '<script>alert("xss")</script>' not in html
        assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_recommendations(self):
        """Report should handle empty recommendations."""
        graph = _build_test_graph()
        sim_report = _build_test_sim_report()
        ai_report = AIAnalysisReport(
            summary="Everything looks fine.",
            top_risks=[],
            recommendations=[],
            availability_assessment="Good",
            upgrade_path="None needed.",
            estimated_current_nines=4.0,
            theoretical_max_nines=5.0,
        )

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)
        assert "<!DOCTYPE html>" in html

    def test_zero_resilience_score(self):
        """Report should handle zero resilience score."""
        graph = _build_test_graph()
        sim_report = SimulationReport(results=[], resilience_score=0.0)
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)
        assert "F" in html  # Grade F for score 0

    def test_perfect_resilience_score(self):
        """Report should handle perfect resilience score."""
        graph = _build_test_graph()
        sim_report = SimulationReport(results=[], resilience_score=100.0)
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)
        assert "A+" in html

    def test_single_component_graph(self):
        """Report should handle a single-component graph."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="solo",
            name="Solo Service",
            type=ComponentType.APP_SERVER,
            replicas=1,
        ))
        sim_report = SimulationReport(results=[], resilience_score=50.0)
        ai_report = _build_test_ai_report()

        generator = ExecutiveReportGenerator()
        html = generator.generate(graph, sim_report, ai_report)
        assert "<!DOCTYPE html>" in html
        assert "Solo Service" in html
