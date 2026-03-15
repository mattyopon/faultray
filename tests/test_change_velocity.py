"""Tests for the Change Velocity Impact Analyzer."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.change_velocity import (
    ChangeVelocityAnalyzer,
    ChangeVelocityProfile,
    VelocityImpactReport,
    _classify_cfr,
    _classify_deploy_freq,
    _classify_lead_time,
    _classify_mttr,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_basic_graph() -> InfraGraph:
    """Build a 3-component graph: lb -> app -> db."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        operational_profile=OperationalProfile(deploy_downtime_seconds=5),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        operational_profile=OperationalProfile(mttr_minutes=30, deploy_downtime_seconds=60),
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    return graph


def _build_minimal_graph() -> InfraGraph:
    """Build a minimal single-component graph."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="api", name="API Server", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    return graph


def _build_resilient_graph() -> InfraGraph:
    """Build a highly resilient graph (all features enabled)."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=3,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=6),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=5,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=3, max_replicas=20),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=3,
        failover=FailoverConfig(enabled=True),
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


# ---------------------------------------------------------------------------
# Tests: DORA Classification Helpers
# ---------------------------------------------------------------------------


class TestDORAClassificationHelpers:
    """Test individual DORA classification functions."""

    def test_deploy_freq_elite(self):
        assert _classify_deploy_freq(7) == "Elite"
        assert _classify_deploy_freq(14) == "Elite"

    def test_deploy_freq_high(self):
        assert _classify_deploy_freq(3) == "High"
        assert _classify_deploy_freq(1) == "High"

    def test_deploy_freq_medium(self):
        assert _classify_deploy_freq(0.5) == "Medium"
        assert _classify_deploy_freq(0.25) == "Medium"

    def test_deploy_freq_low(self):
        assert _classify_deploy_freq(0.1) == "Low"
        assert _classify_deploy_freq(0.04) == "Low"

    def test_lead_time_elite(self):
        assert _classify_lead_time(0.5) == "Elite"
        assert _classify_lead_time(1.0) == "Elite"

    def test_lead_time_high(self):
        assert _classify_lead_time(24) == "High"
        assert _classify_lead_time(168) == "High"

    def test_lead_time_medium(self):
        assert _classify_lead_time(336) == "Medium"
        assert _classify_lead_time(720) == "Medium"

    def test_lead_time_low(self):
        assert _classify_lead_time(1000) == "Low"

    def test_cfr_elite(self):
        assert _classify_cfr(1.0) == "Elite"
        assert _classify_cfr(5.0) == "Elite"

    def test_cfr_high(self):
        assert _classify_cfr(8.0) == "High"

    def test_cfr_medium(self):
        assert _classify_cfr(12.0) == "Medium"

    def test_cfr_low(self):
        assert _classify_cfr(20.0) == "Low"

    def test_mttr_elite(self):
        assert _classify_mttr(30) == "Elite"
        assert _classify_mttr(60) == "Elite"

    def test_mttr_high(self):
        assert _classify_mttr(120) == "High"
        assert _classify_mttr(1440) == "High"

    def test_mttr_medium(self):
        assert _classify_mttr(5000) == "Medium"

    def test_mttr_low(self):
        assert _classify_mttr(20000) == "Low"


# ---------------------------------------------------------------------------
# Tests: Analyze
# ---------------------------------------------------------------------------


class TestAnalyze:
    """Test the main analyze() method."""

    def test_analyze_returns_report(self):
        """analyze() should return a VelocityImpactReport."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze()

        assert isinstance(report, VelocityImpactReport)

    def test_elite_classification(self):
        """Daily deploys with low CFR and fast MTTR should be Elite."""
        graph = _build_resilient_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(
            deploys_per_week=14,
            change_failure_rate=2.0,
            mttr_minutes=30,
            lead_time_hours=0.5,
        )

        assert report.dora_classification == "Elite"

    def test_low_classification(self):
        """Rare deploys with high CFR and slow MTTR should be Low."""
        graph = _build_minimal_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(
            deploys_per_week=0.04,
            change_failure_rate=25.0,
            mttr_minutes=50000,
            lead_time_hours=5000,
        )

        assert report.dora_classification == "Low"

    def test_stability_impact_range(self):
        """Stability impact should be between 0 and 100."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze()

        assert 0.0 <= report.stability_impact <= 100.0

    def test_optimal_frequency_positive(self):
        """Optimal deploy frequency should always be positive."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(
            deploys_per_week=50,
            change_failure_rate=20,
            mttr_minutes=1440,
        )

        assert report.optimal_deploy_frequency >= 1.0

    def test_weekly_downtime_calculation(self):
        """Weekly downtime should equal deploys * CFR/100 * MTTR."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(
            deploys_per_week=10,
            change_failure_rate=10.0,
            mttr_minutes=60,
        )

        expected = 10 * (10.0 / 100) * 60  # = 60 minutes
        assert abs(report.estimated_downtime_minutes_per_week - expected) < 0.1

    def test_dora_scores_present(self):
        """DORA scores should contain all four metrics."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze()

        assert "deployment_frequency" in report.dora_scores
        assert "lead_time" in report.dora_scores
        assert "change_failure_rate" in report.dora_scores
        assert "mttr" in report.dora_scores

    def test_current_velocity_stored(self):
        """Report should store the input velocity profile."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(
            deploys_per_week=7,
            change_failure_rate=3.0,
            mttr_minutes=45,
            lead_time_hours=12,
        )

        assert report.current_velocity.deploys_per_week == 7
        assert report.current_velocity.change_failure_rate == 3.0
        assert report.current_velocity.mttr_minutes == 45
        assert report.current_velocity.lead_time_hours == 12


# ---------------------------------------------------------------------------
# Tests: Architecture Risk Factors
# ---------------------------------------------------------------------------


class TestArchitectureRisks:
    """Test architecture risk analysis."""

    def test_single_replica_risk(self):
        """Single-replica services should be flagged as risks."""
        graph = _build_minimal_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(deploys_per_week=10)

        # Single replica is a risk at 10 deploys/week
        assert len(report.architecture_risk_factors) >= 1
        assert any("single replica" in r.lower() for r in report.architecture_risk_factors)

    def test_stateful_without_failover(self):
        """Stateful service without failover should be flagged."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="Database", type=ComponentType.DATABASE,
            replicas=1,
        ))

        analyzer = ChangeVelocityAnalyzer(graph)
        report = analyzer.analyze(deploys_per_week=5)

        assert any("failover" in r.lower() for r in report.architecture_risk_factors)

    def test_no_risks_resilient_arch(self):
        """Resilient architecture should have fewer risks."""
        graph = _build_resilient_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(deploys_per_week=10, change_failure_rate=3.0)

        # No single-replica risks, DB has failover
        single_replica_risks = [
            r for r in report.architecture_risk_factors
            if "single replica" in r.lower()
        ]
        assert len(single_replica_risks) == 0


# ---------------------------------------------------------------------------
# Tests: Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    """Test recommendation generation."""

    def test_high_cfr_recommendations(self):
        """High CFR should produce specific recommendations."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(change_failure_rate=20.0)

        assert len(report.recommendations) >= 1
        assert any("failure rate" in r.lower() for r in report.recommendations)

    def test_high_mttr_recommendations(self):
        """High MTTR should produce recovery recommendations."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(mttr_minutes=2000)

        assert len(report.recommendations) >= 1

    def test_elite_positive_feedback(self):
        """Elite level with high stability should get positive feedback."""
        graph = _build_resilient_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(
            deploys_per_week=14,
            change_failure_rate=2.0,
            mttr_minutes=15,
            lead_time_hours=0.5,
        )

        assert report.dora_classification == "Elite"
        assert any("elite" in r.lower() for r in report.recommendations)

    def test_low_dora_gets_ci_recommendation(self):
        """Low DORA classification should recommend CI/CD."""
        graph = _build_minimal_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(
            deploys_per_week=0.04,
            change_failure_rate=25.0,
            mttr_minutes=50000,
            lead_time_hours=5000,
        )

        assert any("ci/cd" in r.lower() for r in report.recommendations)


# ---------------------------------------------------------------------------
# Tests: Velocity Sweep
# ---------------------------------------------------------------------------


class TestVelocitySweep:
    """Test simulate_velocity_sweep."""

    def test_sweep_returns_list(self):
        """sweep should return a list of dicts."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        results = analyzer.simulate_velocity_sweep()

        assert isinstance(results, list)
        assert len(results) == 5  # default [1, 5, 10, 20, 50]

    def test_sweep_custom_range(self):
        """sweep with custom range should match count."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        results = analyzer.simulate_velocity_sweep(deploy_range=[2, 4, 8])

        assert len(results) == 3

    def test_sweep_dict_keys(self):
        """Each sweep result should have required keys."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        results = analyzer.simulate_velocity_sweep()

        for r in results:
            assert "deploys_per_week" in r
            assert "dora_classification" in r
            assert "stability_impact" in r
            assert "estimated_downtime_minutes_per_week" in r
            assert "optimal_deploy_frequency" in r

    def test_sweep_downtime_increases_with_frequency(self):
        """Higher deploy frequency should increase estimated downtime."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        results = analyzer.simulate_velocity_sweep(
            deploy_range=[1, 50],
            change_failure_rate=10.0,
        )

        assert results[1]["estimated_downtime_minutes_per_week"] > results[0]["estimated_downtime_minutes_per_week"]

    def test_sweep_empty_graph(self):
        """Sweep on empty graph should still work."""
        graph = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(graph)

        results = analyzer.simulate_velocity_sweep()

        assert len(results) == 5
        for r in results:
            assert r["stability_impact"] >= 0


# ---------------------------------------------------------------------------
# Tests: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases."""

    def test_zero_deploys(self):
        """Zero deploys should still produce a valid report."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(deploys_per_week=0)

        assert isinstance(report, VelocityImpactReport)
        assert report.estimated_downtime_minutes_per_week == 0.0

    def test_very_high_cfr(self):
        """100% CFR should produce valid results."""
        graph = _build_basic_graph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze(
            deploys_per_week=10,
            change_failure_rate=100.0,
        )

        assert report.dora_classification == "Low"
        assert report.estimated_downtime_minutes_per_week > 0

    def test_empty_graph_analyze(self):
        """Analyze on empty graph should not crash."""
        graph = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(graph)

        report = analyzer.analyze()

        assert isinstance(report, VelocityImpactReport)
        assert report.stability_impact >= 0
