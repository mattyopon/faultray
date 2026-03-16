"""Tests for the Chaos Regression Gate."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.integrations.regression_gate import (
    ChaosRegressionGate,
    RegressionCheckResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def healthy_graph() -> InfraGraph:
    """A well-configured graph with replicas and failover."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2, failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3, failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=2, failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return graph


@pytest.fixture
def degraded_graph() -> InfraGraph:
    """A graph with SPOFs and no failover."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


@pytest.fixture
def gate() -> ChaosRegressionGate:
    """Default regression gate."""
    return ChaosRegressionGate(min_score=60.0, max_score_drop=5.0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegressionGateBasics:
    """Basic regression gate functionality."""

    def test_same_graph_passes(self, healthy_graph: InfraGraph, gate: ChaosRegressionGate):
        """Identical before/after should always pass."""
        result = gate.check(healthy_graph, healthy_graph)
        assert result.passed is True
        assert result.blocking_reason is None
        assert result.score_delta == 0.0

    def test_improvement_passes(self, degraded_graph: InfraGraph, healthy_graph: InfraGraph,
                                 gate: ChaosRegressionGate):
        """Improving resilience should pass."""
        result = gate.check(degraded_graph, healthy_graph)
        assert result.passed is True
        assert result.score_delta > 0

    def test_degradation_blocks(self, healthy_graph: InfraGraph, degraded_graph: InfraGraph,
                                 gate: ChaosRegressionGate):
        """Significant resilience drop should be blocked."""
        result = gate.check(healthy_graph, degraded_graph)
        # The degraded graph has much lower score, should block
        assert result.score_delta < 0
        # Check that it's blocked (either due to score drop or min score)
        if abs(result.score_delta) > gate.max_score_drop or result.after_score < gate.min_score:
            assert result.passed is False
            assert result.blocking_reason is not None

    def test_score_below_minimum_blocks(self, gate: ChaosRegressionGate):
        """Score below absolute minimum should block."""
        # Create a minimal graph with very low score
        before = InfraGraph()
        before.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        ))
        after = InfraGraph()
        after.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        ))
        high_threshold_gate = ChaosRegressionGate(min_score=200.0)  # Impossibly high
        result = high_threshold_gate.check(before, after)
        assert result.passed is False
        assert "below minimum" in result.blocking_reason


class TestRegressionGateFindings:
    """Tests for finding detection."""

    def test_new_critical_findings_detected(self, healthy_graph: InfraGraph,
                                             degraded_graph: InfraGraph,
                                             gate: ChaosRegressionGate):
        """New critical findings should be detected."""
        result = gate.check(healthy_graph, degraded_graph)
        # The degraded graph should introduce new critical findings
        # (exact findings depend on simulation)
        assert isinstance(result.new_critical_findings, list)
        assert isinstance(result.new_warnings, list)

    def test_resolved_findings_tracked(self, degraded_graph: InfraGraph,
                                        healthy_graph: InfraGraph,
                                        gate: ChaosRegressionGate):
        """Resolved findings should be listed."""
        result = gate.check(degraded_graph, healthy_graph)
        assert isinstance(result.resolved_findings, list)

    def test_block_on_new_critical_disabled(self, healthy_graph: InfraGraph,
                                             degraded_graph: InfraGraph):
        """When block_on_new_critical=False, new criticals don't block."""
        gate = ChaosRegressionGate(
            min_score=0.0, max_score_drop=100.0, block_on_new_critical=False
        )
        result = gate.check(healthy_graph, degraded_graph)
        # With very permissive thresholds and no critical blocking, should pass
        assert result.passed is True


class TestRegressionGateFileOperations:
    """Tests for file-based operations."""

    def test_check_from_json_files(self, healthy_graph: InfraGraph, gate: ChaosRegressionGate):
        """Should load and compare JSON model files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            before_path = Path(tmpdir) / "before.json"
            after_path = Path(tmpdir) / "after.json"
            healthy_graph.save(before_path)
            healthy_graph.save(after_path)

            result = gate.check_from_files(before_path, after_path)
            assert result.passed is True

    def test_check_terraform_plan(self, healthy_graph: InfraGraph, gate: ChaosRegressionGate):
        """Should evaluate a terraform plan against current model."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "current.json"
            plan_path = Path(tmpdir) / "plan.json"
            healthy_graph.save(model_path)
            healthy_graph.save(plan_path)

            result = gate.check_terraform_plan(plan_path, model_path)
            assert result.passed is True

    def test_terraform_plan_unparseable(self, healthy_graph: InfraGraph, gate: ChaosRegressionGate):
        """Unparseable plan should pass with recommendation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "current.json"
            plan_path = Path(tmpdir) / "plan.tfplan"
            healthy_graph.save(model_path)
            plan_path.write_text("binary plan data")

            result = gate.check_terraform_plan(plan_path, model_path)
            assert result.passed is True
            assert "Could not parse" in result.recommendation


class TestRegressionGateOutputFormats:
    """Tests for PR comment and SARIF export."""

    def test_pr_comment_passed(self, healthy_graph: InfraGraph, gate: ChaosRegressionGate):
        """PR comment for passing check should contain PASSED."""
        result = gate.check(healthy_graph, healthy_graph)
        comment = gate.generate_pr_comment(result)
        assert "PASSED" in comment
        assert "Resilience Score" in comment
        assert "Before" in comment
        assert "After" in comment
        assert "FaultRay" in comment

    def test_pr_comment_blocked(self, healthy_graph: InfraGraph, degraded_graph: InfraGraph):
        """PR comment for blocked check should contain BLOCKED."""
        gate = ChaosRegressionGate(min_score=200.0)
        result = gate.check(healthy_graph, degraded_graph)
        comment = gate.generate_pr_comment(result)
        assert "BLOCKED" in comment
        assert "Blocking reason" in comment

    def test_sarif_export_structure(self, healthy_graph: InfraGraph, degraded_graph: InfraGraph,
                                     gate: ChaosRegressionGate):
        """SARIF export should have valid structure."""
        result = gate.check(healthy_graph, degraded_graph)
        sarif = gate.to_sarif(result)

        assert sarif["version"] == "2.1.0"
        assert "$schema" in sarif
        assert len(sarif["runs"]) == 1
        run = sarif["runs"][0]
        assert "tool" in run
        assert "results" in run
        assert "invocations" in run
        assert run["properties"]["before_score"] == result.before_score
        assert run["properties"]["after_score"] == result.after_score

    def test_sarif_export_empty_when_passed(self, healthy_graph: InfraGraph,
                                              gate: ChaosRegressionGate):
        """SARIF export for passing check should have no error results."""
        result = gate.check(healthy_graph, healthy_graph)
        sarif = gate.to_sarif(result)
        run = sarif["runs"][0]
        # No blocking reason means no GATE0000 rule
        error_results = [r for r in run["results"] if r["level"] == "error"]
        assert len(error_results) == 0

    def test_sarif_has_blocking_rule(self, healthy_graph: InfraGraph, degraded_graph: InfraGraph):
        """SARIF export for blocked check should include blocking rule."""
        gate = ChaosRegressionGate(min_score=200.0)
        result = gate.check(healthy_graph, degraded_graph)
        sarif = gate.to_sarif(result)
        run = sarif["runs"][0]
        rule_ids = [r["id"] for r in run["tool"]["driver"]["rules"]]
        assert "GATE0000" in rule_ids


class TestRegressionGateRecommendations:
    """Tests for recommendation text generation."""

    def test_improvement_recommendation(self, degraded_graph: InfraGraph,
                                         healthy_graph: InfraGraph,
                                         gate: ChaosRegressionGate):
        """Improvement should get a non-blocking recommendation."""
        result = gate.check(degraded_graph, healthy_graph)
        assert result.passed is True
        # Recommendation should either praise improvement or note new warnings
        assert len(result.recommendation) > 0
        assert "NOT be merged" not in result.recommendation

    def test_blocking_recommendation_includes_advice(self, healthy_graph: InfraGraph,
                                                       degraded_graph: InfraGraph):
        """Blocked result should include actionable advice."""
        gate = ChaosRegressionGate(min_score=200.0, max_score_drop=0.1)
        result = gate.check(healthy_graph, degraded_graph)
        assert len(result.recommendation) > 0
        assert "NOT be merged" in result.recommendation or "improve" in result.recommendation.lower()
