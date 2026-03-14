"""Tests for the Cyber Insurance Scoring API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from infrasim.api.insurance_api import (
    InsuranceScore,
    _score_to_grade,
    compute_insurance_score,
)
from infrasim.api.server import app, set_graph
from infrasim.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    SecurityProfile,
    CostProfile,
)
from infrasim.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_graph():
    """Reset server graph state before/after each test."""
    set_graph(None)
    yield
    set_graph(None)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def minimal_graph() -> InfraGraph:
    """Minimal graph with a single component and no security controls."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    return graph


@pytest.fixture
def secure_graph() -> InfraGraph:
    """Well-configured graph with security, failover, and backups."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            waf_protected=True, rate_limiting=True, auth_required=True,
            network_segmented=True, backup_enabled=True,
            backup_frequency_hours=4.0, log_enabled=True, ids_monitored=True,
        ),
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=5),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            waf_protected=True, rate_limiting=True, auth_required=True,
            network_segmented=True, backup_enabled=True,
            backup_frequency_hours=4.0, log_enabled=True, ids_monitored=True,
        ),
        operational_profile=OperationalProfile(mtbf_hours=1000, mttr_minutes=3),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            waf_protected=False, rate_limiting=True, auth_required=True,
            network_segmented=True, backup_enabled=True,
            backup_frequency_hours=1.0, log_enabled=True, ids_monitored=True,
        ),
        operational_profile=OperationalProfile(mtbf_hours=2000, mttr_minutes=10),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


@pytest.fixture
def graph_with_costs() -> InfraGraph:
    """Graph with cost profiles for financial estimation."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        cost_profile=CostProfile(
            hourly_infra_cost=10.0,
            revenue_per_minute=50.0,
            recovery_engineer_cost=200.0,
        ),
        operational_profile=OperationalProfile(mttr_minutes=15),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        cost_profile=CostProfile(
            hourly_infra_cost=20.0,
            revenue_per_minute=100.0,
            recovery_engineer_cost=300.0,
        ),
        operational_profile=OperationalProfile(mttr_minutes=30),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db"))
    return graph


# ---------------------------------------------------------------------------
# Grade mapping
# ---------------------------------------------------------------------------


class TestScoreToGrade:
    def test_a_plus(self):
        assert _score_to_grade(95) == "A+"
        assert _score_to_grade(90) == "A+"
        assert _score_to_grade(100) == "A+"

    def test_a(self):
        assert _score_to_grade(85) == "A"
        assert _score_to_grade(80) == "A"

    def test_b_plus(self):
        assert _score_to_grade(75) == "B+"
        assert _score_to_grade(70) == "B+"

    def test_b(self):
        assert _score_to_grade(65) == "B"
        assert _score_to_grade(60) == "B"

    def test_c(self):
        assert _score_to_grade(55) == "C"
        assert _score_to_grade(50) == "C"

    def test_d(self):
        assert _score_to_grade(45) == "D"
        assert _score_to_grade(40) == "D"

    def test_f(self):
        assert _score_to_grade(39) == "F"
        assert _score_to_grade(0) == "F"


# ---------------------------------------------------------------------------
# InsuranceScore dataclass
# ---------------------------------------------------------------------------


class TestInsuranceScoreDataclass:
    def test_default_values(self):
        score = InsuranceScore(
            overall_score=75,
            risk_grade="B+",
            resilience_score=80.0,
            security_score=70.0,
            recovery_score=60.0,
            operational_score=65.0,
            annual_expected_loss=5000.0,
            max_single_incident_cost=10000.0,
        )
        assert score.overall_score == 75
        assert score.risk_grade == "B+"
        assert score.risk_factors == []
        assert score.mitigation_recommendations == []
        assert score.compliance_summary == {}


# ---------------------------------------------------------------------------
# compute_insurance_score
# ---------------------------------------------------------------------------


class TestComputeInsuranceScore:
    def test_empty_graph_returns_f(self):
        graph = InfraGraph()
        score = compute_insurance_score(graph)
        assert score.overall_score == 0
        assert score.risk_grade == "F"
        assert score.resilience_score == 0.0
        assert score.security_score == 0.0

    def test_minimal_graph_low_score(self, minimal_graph):
        score = compute_insurance_score(minimal_graph)
        # No security controls, single replica, no failover -> low score
        assert score.overall_score < 60
        assert score.risk_grade in ("F", "D", "C")

    def test_secure_graph_high_score(self, secure_graph):
        score = compute_insurance_score(secure_graph)
        # Full security, replicas, failover -> high score
        assert score.overall_score >= 60
        assert score.risk_grade in ("A+", "A", "B+", "B")

    def test_secure_graph_beats_minimal(self, minimal_graph, secure_graph):
        minimal_score = compute_insurance_score(minimal_graph)
        secure_score = compute_insurance_score(secure_graph)
        assert secure_score.overall_score > minimal_score.overall_score

    def test_scores_are_bounded(self, secure_graph):
        score = compute_insurance_score(secure_graph)
        assert 0 <= score.overall_score <= 100
        assert 0.0 <= score.resilience_score <= 100.0
        assert 0.0 <= score.security_score <= 100.0
        assert 0.0 <= score.recovery_score <= 100.0
        assert 0.0 <= score.operational_score <= 100.0

    def test_risk_factors_populated(self, minimal_graph):
        score = compute_insurance_score(minimal_graph)
        # Minimal graph should have risk factors (no encryption, etc.)
        assert len(score.risk_factors) >= 1

    def test_compliance_summary_populated(self, secure_graph):
        score = compute_insurance_score(secure_graph)
        assert "components_assessed" in score.compliance_summary
        assert score.compliance_summary["components_assessed"] == 3

    def test_financial_estimates(self, graph_with_costs):
        score = compute_insurance_score(graph_with_costs)
        assert score.annual_expected_loss >= 0
        assert score.max_single_incident_cost >= 0

    def test_mitigation_recommendations(self, minimal_graph):
        score = compute_insurance_score(minimal_graph)
        # Low-security graph should generate recommendations
        assert len(score.mitigation_recommendations) >= 1


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


class TestInsuranceAPIEndpoints:
    def test_benchmark_endpoint(self, client):
        resp = client.get("/api/insurance/benchmark")
        assert resp.status_code == 200
        data = resp.json()
        assert "benchmarks" in data
        assert "scoring_methodology" in data
        assert "grade_scale" in data
        # Check benchmark categories
        assert "startup_mvp" in data["benchmarks"]
        assert "enterprise" in data["benchmarks"]
        assert "mission_critical" in data["benchmarks"]

    def test_score_endpoint_valid_yaml(self, client):
        yaml_content = """
components:
  - id: app
    name: App Server
    type: app_server
    replicas: 2
  - id: db
    name: Database
    type: database
    replicas: 1
dependencies:
  - source: app
    target: db
    type: requires
"""
        resp = client.post("/api/insurance/score", json={"yaml_content": yaml_content})
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_score" in data
        assert "risk_grade" in data
        assert "resilience_score" in data
        assert "security_score" in data
        assert "recovery_score" in data
        assert "operational_score" in data
        assert "risk_factors" in data
        assert "compliance_summary" in data

    def test_score_endpoint_invalid_yaml(self, client):
        resp = client.post("/api/insurance/score", json={"yaml_content": "invalid: [yaml: {"})
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    def test_score_endpoint_empty_yaml(self, client):
        yaml_content = """
components: []
dependencies: []
"""
        resp = client.post("/api/insurance/score", json={"yaml_content": yaml_content})
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_score"] == 0
        assert data["risk_grade"] == "F"

    def test_benchmark_grade_scale_complete(self, client):
        resp = client.get("/api/insurance/benchmark")
        data = resp.json()
        grades = data["grade_scale"]
        for g in ("A+", "A", "B+", "B", "C", "D", "F"):
            assert g in grades

    def test_benchmark_scoring_methodology(self, client):
        resp = client.get("/api/insurance/benchmark")
        data = resp.json()
        methodology = data["scoring_methodology"]
        # Weights should sum to 1.0
        total = sum(methodology.values())
        assert abs(total - 1.0) < 0.001

    def test_score_endpoint_with_security(self, client):
        yaml_content = """
components:
  - id: app
    name: App Server
    type: app_server
    replicas: 3
    failover:
      enabled: true
    autoscaling:
      enabled: true
  - id: db
    name: Database
    type: database
    replicas: 2
    failover:
      enabled: true
dependencies:
  - source: app
    target: db
    type: requires
"""
        resp = client.post("/api/insurance/score", json={"yaml_content": yaml_content})
        assert resp.status_code == 200
        data = resp.json()
        # This infra has replicas and failover, so score should be reasonable
        assert data["overall_score"] > 0

    def test_insurance_router_registered(self, client):
        """Verify the insurance router is registered in the FastAPI app."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        paths = data["paths"]
        assert "/api/insurance/score" in paths
        assert "/api/insurance/benchmark" in paths
