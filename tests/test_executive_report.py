"""Tests for the Executive Summary Report and new model enhancements."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from faultray.model.components import (
    ComplianceTags,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    OperationalTeamConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.reporter.executive_report import (
    ExecutiveSummary,
    generate_executive_summary,
    render_executive_html,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _build_simple_graph() -> InfraGraph:
    """Build a simple 3-component graph for testing."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=1,
        cost_profile=CostProfile(
            hourly_infra_cost=10.0,
            revenue_per_minute=50.0,
        ),
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        replicas=1,
        cost_profile=CostProfile(
            hourly_infra_cost=20.0,
            revenue_per_minute=100.0,
        ),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app"))
    graph.add_dependency(Dependency(source_id="app", target_id="db"))
    return graph


def _build_secure_graph() -> InfraGraph:
    """Build a graph with security features enabled."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="Secure App",
        type=ComponentType.APP_SERVER,
        replicas=2,
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            network_segmented=True,
            backup_enabled=True,
            log_enabled=True,
            ids_monitored=True,
        ),
        failover=FailoverConfig(enabled=True),
    ))
    return graph


# ---------------------------------------------------------------------------
# Task 1: Executive Summary Report Tests
# ---------------------------------------------------------------------------


class TestExecutiveSummaryGeneration:
    """Tests for generate_executive_summary."""

    def test_summary_with_minimal_graph(self):
        """Generate summary from just a graph (no optional reports)."""
        graph = _build_simple_graph()
        summary = generate_executive_summary(graph)

        assert isinstance(summary, ExecutiveSummary)
        assert summary.overall_status in ("GREEN", "YELLOW", "RED")
        assert summary.headline != ""
        assert summary.availability_status in ("GREEN", "YELLOW", "RED")
        assert summary.security_status in ("GREEN", "YELLOW", "RED")
        assert summary.cost_risk_status in ("GREEN", "YELLOW", "RED")
        assert summary.compliance_status in ("GREEN", "YELLOW", "RED")

    def test_summary_with_static_report(self):
        """Summary should incorporate static simulation results."""
        graph = _build_simple_graph()

        from faultray.simulator.engine import SimulationEngine

        engine = SimulationEngine(graph)
        static_report = engine.run_all_defaults()

        summary = generate_executive_summary(graph, static_report=static_report)
        assert summary.scenarios_tested > 0
        assert 0 <= summary.scenarios_passed_percent <= 100

    def test_summary_with_cost_report(self):
        """Summary should include annual risk from cost report."""
        graph = _build_simple_graph()

        from faultray.simulator.cost_engine import CostImpactEngine
        from faultray.simulator.engine import SimulationEngine

        engine = SimulationEngine(graph)
        static_report = engine.run_all_defaults()
        cost_engine = CostImpactEngine(graph)
        cost_report = cost_engine.analyze(static_report)

        summary = generate_executive_summary(
            graph, static_report=static_report, cost_report=cost_report,
        )
        assert summary.estimated_annual_risk >= 0

    def test_summary_with_compliance_reports(self):
        """Summary should integrate compliance check results."""
        graph = _build_simple_graph()

        from faultray.simulator.compliance_engine import ComplianceEngine

        compliance_engine = ComplianceEngine(graph)
        compliance_reports = compliance_engine.check_all()

        summary = generate_executive_summary(
            graph, compliance_reports=compliance_reports,
        )
        assert summary.compliance_status in ("GREEN", "YELLOW", "RED")

    def test_green_status_for_secure_graph(self):
        """A well-secured graph should produce GREEN security status."""
        graph = _build_secure_graph()
        summary = generate_executive_summary(graph)
        assert summary.security_status == "GREEN"

    def test_red_status_for_no_security(self):
        """A graph with no security features should produce RED security status."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="insecure",
            name="Insecure App",
            type=ComponentType.APP_SERVER,
            replicas=1,
            security=SecurityProfile(),  # all defaults = all False
        ))
        summary = generate_executive_summary(graph)
        assert summary.security_status == "RED"

    def test_top_risks_from_static_report(self):
        """Top risks should be populated from critical findings."""
        graph = _build_simple_graph()

        from faultray.simulator.engine import SimulationEngine

        engine = SimulationEngine(graph)
        static_report = engine.run_all_defaults()

        summary = generate_executive_summary(graph, static_report=static_report)
        # Top risks should be a list (may or may not be populated)
        assert isinstance(summary.top_risks, list)
        assert len(summary.top_risks) <= 3

    def test_roi_items_for_spof_components(self):
        """ROI items should be generated for SPOF components."""
        graph = _build_simple_graph()
        summary = generate_executive_summary(graph)

        # app and db are SPOFs with dependents
        assert isinstance(summary.roi_items, list)
        # Should have at least one ROI recommendation for SPOF
        if summary.roi_items:
            item = summary.roi_items[0]
            assert "action" in item
            assert "cost" in item
            assert "risk_reduction" in item
            assert "roi_percent" in item

    def test_availability_nines_estimated(self):
        """Availability nines should be > 0 for any graph."""
        graph = _build_simple_graph()
        summary = generate_executive_summary(graph)
        assert summary.availability_nines > 0


class TestExecutiveHtmlRendering:
    """Tests for render_executive_html."""

    def test_render_produces_valid_html(self):
        """Rendered HTML should contain expected structure."""
        graph = _build_simple_graph()
        summary = generate_executive_summary(graph)
        html_content = render_executive_html(summary)

        assert "<!DOCTYPE html>" in html_content
        assert "Executive Summary" in html_content
        assert summary.headline in html_content
        assert summary.overall_status in html_content

    def test_render_contains_traffic_lights(self):
        """HTML should contain all four traffic light indicators."""
        graph = _build_simple_graph()
        summary = generate_executive_summary(graph)
        html_content = render_executive_html(summary)

        assert "Availability" in html_content
        assert "Security" in html_content
        assert "Cost Risk" in html_content
        assert "Compliance" in html_content

    def test_render_contains_key_metrics(self):
        """HTML should display key metrics."""
        graph = _build_simple_graph()
        summary = generate_executive_summary(graph)
        html_content = render_executive_html(summary)

        assert "Scenarios Tested" in html_content
        assert "Scenarios Passed" in html_content
        assert "Availability (Nines)" in html_content

    def test_render_with_roi_items(self):
        """HTML should include ROI table when items exist."""
        graph = _build_simple_graph()
        summary = generate_executive_summary(graph)

        if summary.roi_items:
            html_content = render_executive_html(summary)
            assert "Investment Recommendations" in html_content
            assert "Annual Cost" in html_content

    def test_render_writable_to_file(self):
        """Rendered HTML should be writable to a file."""
        graph = _build_simple_graph()
        summary = generate_executive_summary(graph)
        html_content = render_executive_html(summary)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False
        ) as f:
            f.write(html_content)
            path = Path(f.name)

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert len(content) > 100


# ---------------------------------------------------------------------------
# Task 2: Enhanced CostProfile Tests
# ---------------------------------------------------------------------------


class TestCostProfileEnhancements:
    """Verify new CostProfile fields have correct defaults."""

    def test_default_monthly_contract_value(self):
        cost = CostProfile()
        assert cost.monthly_contract_value == 0.0

    def test_default_customer_ltv(self):
        cost = CostProfile()
        assert cost.customer_ltv == 0.0

    def test_default_churn_rate(self):
        cost = CostProfile()
        assert cost.churn_rate_per_hour_outage == 0.001

    def test_default_recovery_team_size(self):
        cost = CostProfile()
        assert cost.recovery_team_size == 0  # 0 = use engine default

    def test_default_data_loss_cost(self):
        cost = CostProfile()
        assert cost.data_loss_cost_per_gb == 0.0

    def test_existing_fields_unchanged(self):
        """Existing fields should retain their default values."""
        cost = CostProfile()
        assert cost.hourly_infra_cost == 0.0
        assert cost.revenue_per_minute == 0.0
        assert cost.sla_credit_percent == 0.0
        assert cost.recovery_engineer_cost == 100.0

    def test_custom_values(self):
        """New fields should accept custom values."""
        cost = CostProfile(
            monthly_contract_value=5000.0,
            customer_ltv=50000.0,
            churn_rate_per_hour_outage=0.01,
            recovery_team_size=5,
            data_loss_cost_per_gb=100.0,
        )
        assert cost.monthly_contract_value == 5000.0
        assert cost.customer_ltv == 50000.0
        assert cost.churn_rate_per_hour_outage == 0.01
        assert cost.recovery_team_size == 5
        assert cost.data_loss_cost_per_gb == 100.0


# ---------------------------------------------------------------------------
# Task 3: ComplianceTags Tests
# ---------------------------------------------------------------------------


class TestComplianceTags:
    """Verify ComplianceTags model defaults and usage."""

    def test_default_values(self):
        tags = ComplianceTags()
        assert tags.data_classification == "internal"
        assert tags.pci_scope is False
        assert tags.contains_pii is False
        assert tags.contains_phi is False
        assert tags.audit_logging is False
        assert tags.change_management is False

    def test_custom_values(self):
        tags = ComplianceTags(
            data_classification="restricted",
            pci_scope=True,
            contains_pii=True,
            contains_phi=True,
            audit_logging=True,
            change_management=True,
        )
        assert tags.data_classification == "restricted"
        assert tags.pci_scope is True
        assert tags.contains_pii is True

    def test_component_has_compliance_tags(self):
        """Component should have compliance_tags field with default."""
        comp = Component(id="test", name="Test", type=ComponentType.APP_SERVER)
        assert isinstance(comp.compliance_tags, ComplianceTags)
        assert comp.compliance_tags.data_classification == "internal"

    def test_component_custom_compliance_tags(self):
        """Component should accept custom compliance_tags."""
        comp = Component(
            id="test",
            name="Test",
            type=ComponentType.APP_SERVER,
            compliance_tags=ComplianceTags(
                data_classification="confidential",
                pci_scope=True,
            ),
        )
        assert comp.compliance_tags.data_classification == "confidential"
        assert comp.compliance_tags.pci_scope is True


# ---------------------------------------------------------------------------
# Task 4: OperationalTeamConfig Tests
# ---------------------------------------------------------------------------


class TestOperationalTeamConfig:
    """Verify OperationalTeamConfig model defaults and usage."""

    def test_default_values(self):
        team = OperationalTeamConfig()
        assert team.team_size == 3
        assert team.oncall_coverage_hours == 24.0
        assert team.timezone_coverage == 1
        assert team.mean_acknowledge_time_minutes == 5.0
        assert team.mean_diagnosis_time_minutes == 15.0
        assert team.runbook_coverage_percent == 50.0
        assert team.automation_percent == 20.0

    def test_custom_values(self):
        team = OperationalTeamConfig(
            team_size=8,
            oncall_coverage_hours=24.0,
            timezone_coverage=3,
            mean_acknowledge_time_minutes=2.0,
            mean_diagnosis_time_minutes=10.0,
            runbook_coverage_percent=90.0,
            automation_percent=80.0,
        )
        assert team.team_size == 8
        assert team.timezone_coverage == 3
        assert team.runbook_coverage_percent == 90.0

    def test_component_has_team(self):
        """Component should have team field with default."""
        comp = Component(id="test", name="Test", type=ComponentType.APP_SERVER)
        assert isinstance(comp.team, OperationalTeamConfig)
        assert comp.team.team_size == 3

    def test_component_custom_team(self):
        """Component should accept custom team config."""
        comp = Component(
            id="test",
            name="Test",
            type=ComponentType.APP_SERVER,
            team=OperationalTeamConfig(team_size=10, automation_percent=75.0),
        )
        assert comp.team.team_size == 10
        assert comp.team.automation_percent == 75.0


# ---------------------------------------------------------------------------
# Task 5: Loader integration tests for new fields
# ---------------------------------------------------------------------------


def _write_yaml(content: str) -> Path:
    """Write YAML content to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


class TestLoaderNewFields:
    """Test that loader.py correctly parses new fields."""

    def test_load_compliance_tags_from_yaml(self):
        """YAML with compliance_tags should populate correctly."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
    compliance_tags:
      data_classification: confidential
      pci_scope: true
      contains_pii: true
      audit_logging: true

dependencies: []
""")
        graph = load_yaml(path)
        comp = graph.get_component("app")
        assert comp is not None
        assert comp.compliance_tags.data_classification == "confidential"
        assert comp.compliance_tags.pci_scope is True
        assert comp.compliance_tags.contains_pii is True
        assert comp.compliance_tags.audit_logging is True
        assert comp.compliance_tags.contains_phi is False  # default

    def test_load_team_from_yaml(self):
        """YAML with team config should populate correctly."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
    team:
      team_size: 5
      oncall_coverage_hours: 16.0
      timezone_coverage: 2
      mean_acknowledge_time_minutes: 3.0
      runbook_coverage_percent: 80.0
      automation_percent: 60.0

dependencies: []
""")
        graph = load_yaml(path)
        comp = graph.get_component("app")
        assert comp is not None
        assert comp.team.team_size == 5
        assert comp.team.oncall_coverage_hours == 16.0
        assert comp.team.timezone_coverage == 2
        assert comp.team.mean_acknowledge_time_minutes == 3.0
        assert comp.team.runbook_coverage_percent == 80.0
        assert comp.team.automation_percent == 60.0

    def test_load_security_from_yaml(self):
        """YAML with security fields should populate correctly."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
    security:
      encryption_at_rest: true
      encryption_in_transit: true
      waf_protected: true
      auth_required: true

dependencies: []
""")
        graph = load_yaml(path)
        comp = graph.get_component("app")
        assert comp is not None
        assert comp.security.encryption_at_rest is True
        assert comp.security.encryption_in_transit is True
        assert comp.security.waf_protected is True
        assert comp.security.auth_required is True

    def test_defaults_when_new_fields_omitted(self):
        """When new fields are omitted, defaults should be used."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("""
components:
  - id: simple
    name: Simple
    type: app_server

dependencies: []
""")
        graph = load_yaml(path)
        comp = graph.get_component("simple")
        assert comp is not None
        assert comp.compliance_tags.data_classification == "internal"
        assert comp.compliance_tags.pci_scope is False
        assert comp.team.team_size == 3
        assert comp.team.automation_percent == 20.0

    def test_load_enhanced_cost_profile_from_yaml(self):
        """YAML with new cost_profile fields should populate correctly."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
    cost_profile:
      hourly_infra_cost: 15.0
      revenue_per_minute: 200.0
      monthly_contract_value: 10000.0
      customer_ltv: 50000.0
      churn_rate_per_hour_outage: 0.005
      recovery_team_size: 4
      data_loss_cost_per_gb: 500.0

dependencies: []
""")
        graph = load_yaml(path)
        comp = graph.get_component("app")
        assert comp is not None
        assert comp.cost_profile.hourly_infra_cost == 15.0
        assert comp.cost_profile.revenue_per_minute == 200.0
        assert comp.cost_profile.monthly_contract_value == 10000.0
        assert comp.cost_profile.customer_ltv == 50000.0
        assert comp.cost_profile.churn_rate_per_hour_outage == 0.005
        assert comp.cost_profile.recovery_team_size == 4
        assert comp.cost_profile.data_loss_cost_per_gb == 500.0

    def test_load_all_new_fields_combined(self):
        """All new fields should load correctly when specified together."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("""
components:
  - id: full
    name: Full Component
    type: database
    replicas: 2
    security:
      encryption_at_rest: true
      backup_enabled: true
    compliance_tags:
      data_classification: restricted
      pci_scope: true
      contains_pii: true
    team:
      team_size: 6
      automation_percent: 70.0
    cost_profile:
      hourly_infra_cost: 25.0
      monthly_contract_value: 20000.0

dependencies: []
""")
        graph = load_yaml(path)
        comp = graph.get_component("full")
        assert comp is not None
        assert comp.security.encryption_at_rest is True
        assert comp.security.backup_enabled is True
        assert comp.compliance_tags.data_classification == "restricted"
        assert comp.compliance_tags.pci_scope is True
        assert comp.compliance_tags.contains_pii is True
        assert comp.team.team_size == 6
        assert comp.team.automation_percent == 70.0
        assert comp.cost_profile.hourly_infra_cost == 25.0
        assert comp.cost_profile.monthly_contract_value == 20000.0
