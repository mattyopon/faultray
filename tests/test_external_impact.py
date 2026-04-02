"""Tests for External SaaS Dependency Impact Analyzer (Feature E)."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.model.components import (
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.external_dependency_analyzer import (
    ExternalDependencyAnalyzer,
    ExternalDependencyReport,
    ExternalImpact,
    _classify_risk,
    _compute_risk_score,
    _estimate_downtime,
    _lookup_service_info,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_graph_with_external(
    *,
    dep_type: str = "requires",
    circuit_breaker: bool = False,
) -> InfraGraph:
    """Build a simple graph: web-app -> stripe (external_api)."""
    g = InfraGraph()
    g.add_component(Component(id="web-app", name="Web Application", type=ComponentType.APP_SERVER, replicas=2))
    g.add_component(Component(id="stripe", name="Stripe Payment API", type=ComponentType.EXTERNAL_API, host="api.stripe.com"))
    g.add_dependency(Dependency(
        source_id="web-app",
        target_id="stripe",
        dependency_type=dep_type,
        circuit_breaker=CircuitBreakerConfig(enabled=circuit_breaker),
    ))
    return g


def _make_multi_external_graph() -> InfraGraph:
    """Build a graph with multiple external services and cascade."""
    g = InfraGraph()
    g.add_component(Component(id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(Component(id="app", name="App Server", type=ComponentType.APP_SERVER, replicas=3))
    g.add_component(Component(id="worker", name="Worker", type=ComponentType.APP_SERVER, replicas=1))
    g.add_component(Component(id="stripe", name="Stripe Payment API", type=ComponentType.EXTERNAL_API, host="api.stripe.com"))
    g.add_component(Component(id="s3", name="AWS S3", type=ComponentType.EXTERNAL_API, host="s3.amazonaws.com"))
    g.add_component(Component(id="sendgrid", name="SendGrid Email", type=ComponentType.EXTERNAL_API, host="api.sendgrid.com"))
    g.add_component(Component(id="db", name="PostgreSQL", type=ComponentType.DATABASE, replicas=2))

    g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="stripe", dependency_type="requires",
                                circuit_breaker=CircuitBreakerConfig(enabled=False)))
    g.add_dependency(Dependency(source_id="app", target_id="s3", dependency_type="requires",
                                circuit_breaker=CircuitBreakerConfig(enabled=True)))
    g.add_dependency(Dependency(source_id="worker", target_id="sendgrid", dependency_type="optional"))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return g


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------

class TestClassifyRisk:
    def test_no_fallback_high_blast_radius_is_critical(self) -> None:
        assert _classify_risk(60.0, has_fallback=False, dep_type="requires") == "critical"

    def test_no_fallback_medium_blast_radius_is_high(self) -> None:
        assert _classify_risk(25.0, has_fallback=False, dep_type="requires") == "high"

    def test_no_fallback_low_blast_radius_is_medium(self) -> None:
        assert _classify_risk(10.0, has_fallback=False, dep_type="requires") == "medium"

    def test_with_fallback_high_blast_radius_is_high(self) -> None:
        assert _classify_risk(60.0, has_fallback=True, dep_type="requires") == "high"

    def test_with_fallback_low_blast_radius_is_low(self) -> None:
        assert _classify_risk(10.0, has_fallback=True, dep_type="requires") == "low"

    def test_optional_dep_never_critical(self) -> None:
        level = _classify_risk(80.0, has_fallback=False, dep_type="optional")
        assert level in ("low", "medium")

    def test_optional_dep_low_blast_is_low(self) -> None:
        assert _classify_risk(5.0, has_fallback=False, dep_type="optional") == "low"


class TestEstimateDowntime:
    def test_optional_dep_zero_downtime(self) -> None:
        assert _estimate_downtime(has_fallback=False, dep_type="optional", affected_count=5) == 0.0

    def test_no_fallback_has_long_downtime(self) -> None:
        dt = _estimate_downtime(has_fallback=False, dep_type="requires", affected_count=3)
        assert dt >= 60.0

    def test_with_fallback_has_short_downtime(self) -> None:
        dt = _estimate_downtime(has_fallback=True, dep_type="requires", affected_count=1)
        assert dt < 10.0

    def test_more_affected_means_longer_downtime(self) -> None:
        dt_small = _estimate_downtime(has_fallback=False, dep_type="requires", affected_count=1)
        dt_large = _estimate_downtime(has_fallback=False, dep_type="requires", affected_count=10)
        assert dt_large > dt_small


class TestLookupServiceInfo:
    def test_stripe_lookup(self) -> None:
        impact, mitigation = _lookup_service_info("Stripe Payment API")
        assert "payment" in impact.lower()
        assert "circuit" in mitigation.lower()

    def test_s3_lookup(self) -> None:
        impact, _ = _lookup_service_info("AWS S3")
        assert "storage" in impact.lower() or "s3" in impact.lower() or "file" in impact.lower()

    def test_sendgrid_lookup(self) -> None:
        impact, _ = _lookup_service_info("SendGrid Email")
        assert "email" in impact.lower() or "mail" in impact.lower()

    def test_unknown_service_returns_default(self) -> None:
        impact, mitigation = _lookup_service_info("SomeRandomSaaS42")
        assert len(impact) > 0
        assert len(mitigation) > 0

    def test_case_insensitive(self) -> None:
        impact1, _ = _lookup_service_info("stripe")
        impact2, _ = _lookup_service_info("STRIPE")
        assert impact1 == impact2


class TestComputeRiskScore:
    def test_no_impacts_returns_zero(self) -> None:
        assert _compute_risk_score([], 5) == 0.0

    def test_critical_impact_high_score(self) -> None:
        impacts = [
            ExternalImpact(
                external_service="Stripe",
                component_id="stripe",
                affected_components=["web-app"],
                blast_radius_percent=50.0,
                estimated_downtime_minutes=60.0,
                business_impact="payments stop",
                mitigation="add circuit breaker",
                has_fallback=False,
                risk_level="critical",
            )
        ]
        score = _compute_risk_score(impacts, 4)
        assert score > 0.0
        assert score <= 100.0

    def test_low_risk_impact_lower_score(self) -> None:
        high_risk_impact = ExternalImpact(
            external_service="A", component_id="a", affected_components=["b"],
            blast_radius_percent=60.0, estimated_downtime_minutes=60.0,
            business_impact="bad", mitigation="fix", has_fallback=False, risk_level="critical",
        )
        low_risk_impact = ExternalImpact(
            external_service="B", component_id="b", affected_components=[],
            blast_radius_percent=5.0, estimated_downtime_minutes=2.0,
            business_impact="minor", mitigation="ok", has_fallback=True, risk_level="low",
        )
        score_high = _compute_risk_score([high_risk_impact], 5)
        score_low = _compute_risk_score([low_risk_impact], 5)
        assert score_high > score_low


# ---------------------------------------------------------------------------
# Integration tests: ExternalDependencyAnalyzer
# ---------------------------------------------------------------------------

class TestExternalDependencyAnalyzer:
    def test_empty_graph_returns_empty_report(self) -> None:
        g = InfraGraph()
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        assert report.total_external_deps == 0
        assert report.risk_score == 0.0
        assert "No components" in report.summary

    def test_no_external_api_returns_empty_report(self) -> None:
        g = InfraGraph()
        g.add_component(Component(id="db", name="DB", type=ComponentType.DATABASE, replicas=2))
        g.add_component(Component(id="app", name="App", type=ComponentType.APP_SERVER, replicas=1))
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        assert report.total_external_deps == 0

    def test_single_external_api_detected(self) -> None:
        g = _make_graph_with_external()
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        assert report.total_external_deps == 1
        assert len(report.impacts) == 1

    def test_stripe_identified_in_impacts(self) -> None:
        g = _make_graph_with_external()
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        assert report.impacts[0].external_service == "Stripe Payment API"
        assert report.impacts[0].component_id == "stripe"

    def test_blast_radius_calculated(self) -> None:
        g = _make_graph_with_external()
        # 2 total components: web-app depends on stripe
        # when stripe fails, web-app is affected (1 of 2 non-stripe = 50%)
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        impact = report.impacts[0]
        assert impact.blast_radius_percent > 0.0
        assert impact.blast_radius_percent <= 100.0

    def test_no_circuit_breaker_marked_unprotected(self) -> None:
        g = _make_graph_with_external(circuit_breaker=False)
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        assert report.unprotected_count >= 1
        assert not report.impacts[0].has_fallback

    def test_circuit_breaker_marks_protected(self) -> None:
        g = _make_graph_with_external(circuit_breaker=True)
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        assert report.impacts[0].has_fallback

    def test_optional_dep_does_not_count_as_unprotected(self) -> None:
        g = _make_graph_with_external(dep_type="optional", circuit_breaker=False)
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        # optional dependency without CB should NOT be counted as unprotected requires
        assert report.unprotected_count == 0

    def test_service_filter_restricts_results(self) -> None:
        g = _make_multi_external_graph()
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze(service_filter="stripe")
        assert all("stripe" in imp.external_service.lower() for imp in report.impacts)

    def test_multiple_external_services_analyzed(self) -> None:
        g = _make_multi_external_graph()
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        assert report.total_external_deps == 3  # stripe, s3, sendgrid

    def test_report_risk_score_is_valid_range(self) -> None:
        g = _make_multi_external_graph()
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        assert 0.0 <= report.risk_score <= 100.0

    def test_summary_contains_count(self) -> None:
        g = _make_multi_external_graph()
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        assert "3" in report.summary

    def test_impacts_sorted_critical_first(self) -> None:
        g = _make_multi_external_graph()
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        levels = [risk_order.get(i.risk_level, 4) for i in report.impacts]
        assert levels == sorted(levels), "Impacts should be sorted by risk level"

    def test_affected_components_excludes_self(self) -> None:
        g = _make_graph_with_external()
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        for impact in report.impacts:
            assert impact.component_id not in impact.affected_components

    def test_downtime_zero_for_optional_dep(self) -> None:
        g = _make_graph_with_external(dep_type="optional")
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        assert report.impacts[0].estimated_downtime_minutes == 0.0

    def test_report_dataclass_fields(self) -> None:
        g = _make_graph_with_external()
        analyzer = ExternalDependencyAnalyzer(g)
        report = analyzer.analyze()
        assert isinstance(report, ExternalDependencyReport)
        assert isinstance(report.impacts[0], ExternalImpact)
        # Verify all required fields are present
        impact = report.impacts[0]
        assert isinstance(impact.external_service, str)
        assert isinstance(impact.component_id, str)
        assert isinstance(impact.affected_components, list)
        assert isinstance(impact.blast_radius_percent, float)
        assert isinstance(impact.estimated_downtime_minutes, float)
        assert isinstance(impact.business_impact, str)
        assert isinstance(impact.mitigation, str)
        assert isinstance(impact.has_fallback, bool)
        assert isinstance(impact.risk_level, str)
        assert impact.risk_level in ("critical", "high", "medium", "low")
