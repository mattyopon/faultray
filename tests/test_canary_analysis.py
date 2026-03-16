"""Tests for Automated Canary Analysis."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.canary_analysis import (
    CanaryAnalyzer,
    CanaryConfig,
    CanaryMetric,
    CanaryResult,
    _autoscaling_coverage,
    _avg_blast_radius,
    _circuit_breaker_coverage,
    _count_critical_findings,
    _count_spofs,
    _failover_coverage,
    _max_dependency_depth,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_graph() -> InfraGraph:
    """Build a simple 3-component graph: LB -> App -> DB."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _resilient_graph() -> InfraGraph:
    """Build a well-configured resilient graph."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=6),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
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


def _degraded_graph() -> InfraGraph:
    """Build a degraded version of the simple graph (worse resilience)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="requires",
    ))
    return graph


def _write_infra_yaml(graph: InfraGraph, path: Path) -> Path:
    """Write an InfraGraph as YAML suitable for load_yaml."""
    data = {
        "schema_version": "3.0",
        "components": [],
        "dependencies": [],
    }
    for comp in graph.components.values():
        entry: dict = {
            "id": comp.id,
            "name": comp.name,
            "type": comp.type.value,
            "replicas": comp.replicas,
        }
        if comp.failover.enabled:
            entry["failover"] = {
                "enabled": True,
                "health_check_interval_seconds": comp.failover.health_check_interval_seconds,
            }
        if comp.autoscaling.enabled:
            entry["autoscaling"] = {
                "enabled": True,
                "min_replicas": comp.autoscaling.min_replicas,
                "max_replicas": comp.autoscaling.max_replicas,
            }
        data["components"].append(entry)

    for edge in graph.all_dependency_edges():
        dep_entry: dict = {
            "source": edge.source_id,
            "target": edge.target_id,
            "type": edge.dependency_type,
        }
        if edge.circuit_breaker.enabled:
            dep_entry["circuit_breaker"] = {"enabled": True}
        data["dependencies"].append(dep_entry)

    yaml_path = path
    yaml_path.write_text(
        yaml.dump(data, default_flow_style=False),
        encoding="utf-8",
    )
    return yaml_path


# ---------------------------------------------------------------------------
# Metric extractor tests
# ---------------------------------------------------------------------------

class TestMetricExtractors:
    def test_count_spofs(self):
        assert _count_spofs(_simple_graph()) >= 1
        assert _count_spofs(_resilient_graph()) == 0

    def test_count_critical_findings(self):
        assert _count_critical_findings(_simple_graph()) >= 1
        # Resilient graph still has topological blast radius (graph structure),
        # but fewer SPOFs due to failover/replicas
        assert _count_critical_findings(_resilient_graph()) <= _count_critical_findings(_simple_graph())

    def test_avg_blast_radius(self):
        radius = _avg_blast_radius(_simple_graph())
        assert 0.0 <= radius <= 1.0

    def test_avg_blast_radius_empty(self):
        assert _avg_blast_radius(InfraGraph()) == 0.0

    def test_max_dependency_depth(self):
        depth = _max_dependency_depth(_simple_graph())
        assert depth >= 2  # at least lb->app->db = 3

    def test_max_dependency_depth_empty(self):
        assert _max_dependency_depth(InfraGraph()) == 0

    def test_failover_coverage(self):
        assert _failover_coverage(_simple_graph()) == 0.0
        assert _failover_coverage(_resilient_graph()) == 100.0
        assert _failover_coverage(InfraGraph()) == 100.0

    def test_circuit_breaker_coverage(self):
        assert _circuit_breaker_coverage(_simple_graph()) == 0.0
        assert _circuit_breaker_coverage(_resilient_graph()) == 100.0
        assert _circuit_breaker_coverage(InfraGraph()) == 100.0

    def test_autoscaling_coverage(self):
        assert _autoscaling_coverage(_simple_graph()) == 0.0
        # resilient graph has 2/3 with autoscaling (lb, app but not db)
        cov = _autoscaling_coverage(_resilient_graph())
        assert cov > 0.0
        assert _autoscaling_coverage(InfraGraph()) == 100.0


# ---------------------------------------------------------------------------
# CanaryMetric tests
# ---------------------------------------------------------------------------

class TestCanaryMetric:
    def test_to_dict(self):
        m = CanaryMetric(
            name="test_metric",
            baseline_value=90.0,
            canary_value=85.0,
            delta=-5.0,
            delta_percent=-5.56,
            verdict="fail",
            threshold=3.0,
        )
        d = m.to_dict()
        assert d["name"] == "test_metric"
        assert d["verdict"] == "fail"
        assert d["baseline_value"] == 90.0


# ---------------------------------------------------------------------------
# CanaryAnalyzer - analyze_graphs
# ---------------------------------------------------------------------------

class TestCanaryAnalyzerGraphs:
    def test_identical_graphs_pass(self):
        graph = _simple_graph()
        analyzer = CanaryAnalyzer()
        result = analyzer.analyze_graphs(graph, graph)
        assert result.overall_verdict == "pass"
        assert result.failed_count == 0
        assert result.marginal_count == 0

    def test_improved_graph_pass(self):
        baseline = _simple_graph()
        canary = _resilient_graph()
        analyzer = CanaryAnalyzer()
        result = analyzer.analyze_graphs(baseline, canary)
        assert result.overall_verdict == "pass"

    def test_degraded_graph_fail(self):
        baseline = _resilient_graph()
        canary = _degraded_graph()
        analyzer = CanaryAnalyzer()
        result = analyzer.analyze_graphs(baseline, canary)
        # Degraded graph should trigger failures
        assert result.overall_verdict in ("fail", "marginal")
        assert result.failed_count + result.marginal_count > 0

    def test_result_has_all_metrics(self):
        analyzer = CanaryAnalyzer()
        result = analyzer.analyze_graphs(_simple_graph(), _simple_graph())
        metric_names = {m.name for m in result.metrics}
        expected = {
            "resilience_score",
            "spof_count",
            "critical_findings",
            "avg_blast_radius",
            "component_count",
            "dependency_depth",
            "failover_coverage",
            "circuit_breaker_coverage",
            "autoscaling_coverage",
        }
        assert expected == metric_names

    def test_result_to_dict(self):
        analyzer = CanaryAnalyzer()
        result = analyzer.analyze_graphs(_simple_graph(), _simple_graph())
        d = result.to_dict()
        assert "overall_verdict" in d
        assert "metrics" in d
        assert isinstance(d["metrics"], list)
        assert "timestamp" in d

    def test_custom_config(self):
        baseline = _simple_graph()
        canary = _simple_graph()
        config = CanaryConfig(
            score_threshold=0.0,
            spof_threshold=0,
            critical_threshold=0,
            blast_radius_threshold=0.0,
            marginal_zone=0.0,
        )
        analyzer = CanaryAnalyzer()
        result = analyzer.analyze_graphs(baseline, canary, config=config)
        # Identical graphs should still pass even with strict config
        assert result.overall_verdict == "pass"

    def test_strict_config_detects_regression(self):
        baseline = _resilient_graph()
        canary = _simple_graph()
        config = CanaryConfig(
            score_threshold=1.0,
            spof_threshold=0,
            critical_threshold=0,
            blast_radius_threshold=0.01,
            marginal_zone=0.5,
        )
        analyzer = CanaryAnalyzer()
        result = analyzer.analyze_graphs(baseline, canary, config=config)
        assert result.overall_verdict == "fail"

    def test_summary_present(self):
        analyzer = CanaryAnalyzer()
        result = analyzer.analyze_graphs(_simple_graph(), _simple_graph())
        assert len(result.summary) > 0
        assert "PASSED" in result.summary

    def test_recommendations_on_fail(self):
        baseline = _resilient_graph()
        canary = _degraded_graph()
        analyzer = CanaryAnalyzer()
        result = analyzer.analyze_graphs(baseline, canary)
        if result.overall_verdict in ("fail", "marginal"):
            assert len(result.recommendations) > 0


# ---------------------------------------------------------------------------
# CanaryAnalyzer - file-based analyze
# ---------------------------------------------------------------------------

class TestCanaryAnalyzerFiles:
    def test_analyze_yaml_files(self, tmp_path):
        baseline = _simple_graph()
        canary = _simple_graph()

        baseline_path = _write_infra_yaml(baseline, tmp_path / "baseline.yaml")
        canary_path = _write_infra_yaml(canary, tmp_path / "canary.yaml")

        analyzer = CanaryAnalyzer()
        result = analyzer.analyze(baseline_path, canary_path)
        assert result.overall_verdict == "pass"
        assert result.baseline_file == str(baseline_path)
        assert result.canary_file == str(canary_path)

    def test_analyze_regression_yaml(self, tmp_path):
        baseline = _resilient_graph()
        canary = _degraded_graph()

        baseline_path = _write_infra_yaml(baseline, tmp_path / "baseline.yaml")
        canary_path = _write_infra_yaml(canary, tmp_path / "canary.yaml")

        analyzer = CanaryAnalyzer()
        result = analyzer.analyze(baseline_path, canary_path)
        assert result.overall_verdict in ("fail", "marginal")

    def test_analyze_nonexistent_baseline(self, tmp_path):
        canary_path = _write_infra_yaml(_simple_graph(), tmp_path / "canary.yaml")
        analyzer = CanaryAnalyzer()
        with pytest.raises(FileNotFoundError):
            analyzer.analyze(Path("/nonexistent.yaml"), canary_path)

    def test_analyze_nonexistent_canary(self, tmp_path):
        baseline_path = _write_infra_yaml(_simple_graph(), tmp_path / "baseline.yaml")
        analyzer = CanaryAnalyzer()
        with pytest.raises(FileNotFoundError):
            analyzer.analyze(baseline_path, Path("/nonexistent.yaml"))


# ---------------------------------------------------------------------------
# CanaryAnalyzer - quick_compare
# ---------------------------------------------------------------------------

class TestQuickCompare:
    def test_quick_compare_pass(self, tmp_path):
        graph = _simple_graph()
        p1 = _write_infra_yaml(graph, tmp_path / "a.yaml")
        p2 = _write_infra_yaml(graph, tmp_path / "b.yaml")

        analyzer = CanaryAnalyzer()
        summary = analyzer.quick_compare(p1, p2)
        assert "PASS" in summary

    def test_quick_compare_regression(self, tmp_path):
        baseline = _resilient_graph()
        canary = _degraded_graph()

        p1 = _write_infra_yaml(baseline, tmp_path / "a.yaml")
        p2 = _write_infra_yaml(canary, tmp_path / "b.yaml")

        analyzer = CanaryAnalyzer()
        summary = analyzer.quick_compare(p1, p2)
        assert summary.startswith("FAIL") or summary.startswith("MARGINAL")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_vs_nonempty(self):
        """Comparing empty graph to non-empty should handle gracefully."""
        empty = InfraGraph()
        populated = _simple_graph()
        analyzer = CanaryAnalyzer()
        result = analyzer.analyze_graphs(empty, populated)
        # Going from empty to populated introduces SPOFs and blast radius,
        # so some metrics will degrade. The result should not crash.
        assert result.overall_verdict in ("pass", "fail", "marginal")
        assert len(result.metrics) == 9

    def test_nonempty_vs_empty(self):
        """Removing all components is a severe regression."""
        populated = _simple_graph()
        empty = InfraGraph()
        analyzer = CanaryAnalyzer()
        result = analyzer.analyze_graphs(populated, empty)
        # Score drop should be detected
        # Note: empty graph has score 0, populated has > 0
        assert result.overall_verdict in ("fail", "marginal")

    def test_delta_percent_zero_baseline(self):
        """When baseline value is 0, delta_percent should not divide by zero."""
        analyzer = CanaryAnalyzer()
        metric = analyzer._make_metric(
            "test", 0.0, 5.0, threshold=10.0,
            marginal_zone=2.0, higher_is_better=True,
        )
        assert metric.delta_percent == 100.0  # positive from zero

    def test_informational_metric_always_passes(self):
        analyzer = CanaryAnalyzer()
        metric = analyzer._make_metric(
            "info", 10.0, 5.0, threshold=1.0,
            marginal_zone=0.5, higher_is_better=True,
            informational=True,
        )
        assert metric.verdict == "pass"

    def test_marginal_verdict_higher_is_better(self):
        """Line 423: higher_is_better metric where degradation is between marginal_zone and threshold."""
        analyzer = CanaryAnalyzer()
        # baseline=100, canary=96 -> delta=-4, degradation=4
        # threshold=5.0, marginal_zone=2.0 -> 2.0 < 4.0 <= 5.0 -> marginal
        metric = analyzer._make_metric(
            "score", 100.0, 96.0, threshold=5.0,
            marginal_zone=2.0, higher_is_better=True,
        )
        assert metric.verdict == "marginal"

    def test_marginal_verdict_lower_is_better(self):
        """Line 432: non-higher_is_better metric where delta is between marginal_zone and threshold."""
        analyzer = CanaryAnalyzer()
        # baseline=10, canary=12 -> delta=2, degradation=2
        # threshold=3.0, marginal_zone=1.0 -> 1.0 < 2.0 <= 3.0 -> marginal
        metric = analyzer._make_metric(
            "errors", 10.0, 12.0, threshold=3.0,
            marginal_zone=1.0, higher_is_better=False,
        )
        assert metric.verdict == "marginal"

    def test_marginal_overall_verdict_and_summary(self):
        """Lines 329, 342, 360: overall marginal verdict with recommendation and summary text.

        Build graphs with enough components so that disabling failover on one
        produces a failover_coverage drop that lands in the marginal zone
        (between marginal_zone=5.0 and threshold=10.0 for higher_is_better).

        With 12 components all having failover, coverage is 100%.
        Disabling failover on 1 gives coverage 91.67% -> degradation ~8.33%,
        which is > 5.0 (marginal_zone) and <= 10.0 (threshold) -> marginal.
        """
        def _build_large_failover_graph() -> InfraGraph:
            graph = InfraGraph()
            for i in range(12):
                graph.add_component(Component(
                    id=f"svc-{i}",
                    name=f"Service {i}",
                    type=ComponentType.APP_SERVER,
                    replicas=2,
                    failover=FailoverConfig(enabled=True),
                    autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
                ))
            # Chain dependencies: svc-0 -> svc-1 -> ... -> svc-11
            for i in range(11):
                graph.add_dependency(Dependency(
                    source_id=f"svc-{i}",
                    target_id=f"svc-{i+1}",
                    dependency_type="requires",
                    circuit_breaker=CircuitBreakerConfig(enabled=True),
                ))
            return graph

        baseline = _build_large_failover_graph()
        canary = _build_large_failover_graph()

        # Disable failover on one canary component: 12->11 -> coverage
        # drops from 100% to 91.67%, degradation = 8.33 which is in (5, 10].
        canary.components["svc-11"].failover = FailoverConfig(enabled=False)

        # Use lenient config so all score/spof/critical/blast_radius metrics
        # pass easily; only the failover_coverage metric should be marginal.
        config = CanaryConfig(
            score_threshold=90.0,
            spof_threshold=100,
            critical_threshold=100,
            blast_radius_threshold=10.0,
            marginal_zone=50.0,  # wide enough so resilience_score doesn't go marginal
        )
        analyzer = CanaryAnalyzer()
        result = analyzer.analyze_graphs(baseline, canary, config=config)

        # Verify the overall verdict is marginal (line 329)
        assert result.failed_count == 0, (
            f"Expected no failures but got {result.failed_count}: "
            + ", ".join(f"{m.name}={m.verdict}(delta={m.delta})" for m in result.metrics if m.verdict == "fail")
        )
        assert result.marginal_count > 0
        assert result.overall_verdict == "marginal"

        # Summary should contain the MARGINAL text (line 360)
        assert "MARGINAL" in result.summary
        assert "marginal zone" in result.summary

        # Recommendations should contain marginal text (line 342)
        marginal_recs = [r for r in result.recommendations if "Monitor closely" in r]
        assert len(marginal_recs) > 0
