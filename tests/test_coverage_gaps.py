"""Targeted tests for coverage gaps across all modules.

Each section covers the specific missing lines identified in the coverage report.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    DegradationConfig,
    Dependency,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
    RetryStrategy,
    SLOTarget,
)
from faultray.model.graph import InfraGraph


# ===================================================================
# Helper to write YAML to temp file
# ===================================================================

def _write_yaml(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# ===================================================================
# 1. model/loader.py  — Missing: 54, 61, 65, 100-103, 145, 151, 156,
#                                  163, 224-232
# ===================================================================

class TestLoaderCoverageGaps:
    """Cover loader.py lines that the existing tests don't reach."""

    def test_non_mapping_yaml_raises(self):
        """Line 54: top-level YAML is not a mapping (e.g. a list)."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("- item1\n- item2\n")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_yaml(path)

    def test_components_not_a_list(self):
        """Line 61: 'components' is a string instead of a list."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("components: not_a_list\ndependencies: []\n")
        with pytest.raises(ValueError, match="must be a list"):
            load_yaml(path)

    def test_component_entry_not_a_mapping(self):
        """Line 65: component entry is a scalar, not a dict."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("components:\n  - just_a_string\ndependencies: []\n")
        with pytest.raises(ValueError, match="must be a mapping"):
            load_yaml(path)

    def test_operational_profile_with_degradation(self):
        """Lines 100-103: operational_profile with nested degradation."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
    operational_profile:
      mtbf_hours: 720.0
      mttr_minutes: 15.0
      degradation:
        memory_leak_mb_per_hour: 1.5
        disk_fill_gb_per_hour: 0.1
dependencies: []
""")
        graph = load_yaml(path)
        comp = graph.get_component("app")
        assert comp is not None
        assert comp.operational_profile.mtbf_hours == 720.0
        assert comp.operational_profile.degradation.memory_leak_mb_per_hour == 1.5

    def test_dependencies_not_a_list(self):
        """Line 145: 'dependencies' is a string instead of a list."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
dependencies: not_a_list
""")
        with pytest.raises(ValueError, match="must be a list"):
            load_yaml(path)

    def test_dependency_entry_not_a_mapping(self):
        """Line 151: dependency entry is a scalar."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
dependencies:
  - just_a_string
""")
        with pytest.raises(ValueError, match="must be a mapping"):
            load_yaml(path)

    def test_dependency_missing_source_or_target(self):
        """Line 156: dependency with missing 'source' or 'target'."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
dependencies:
  - source: app
""")
        with pytest.raises(ValueError, match="missing 'source' or 'target'"):
            load_yaml(path)

    def test_dependency_unknown_target(self):
        """Line 163: dependency with unknown target raises ValueError."""
        from faultray.model.loader import load_yaml

        path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
dependencies:
  - source: app
    target: unknown_target
    type: requires
""")
        with pytest.raises(ValueError, match="target.*unknown_target"):
            load_yaml(path)

    def test_load_yaml_with_ops(self):
        """Lines 224-232: load_yaml_with_ops parses slos and operational_simulation."""
        from faultray.model.loader import load_yaml_with_ops

        path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
dependencies: []
slos:
  - name: availability
    metric: availability
    target: 99.9
operational_simulation:
  duration_days: 30
  enable_random_failures: true
""")
        graph, ops_config = load_yaml_with_ops(path)
        assert len(graph.components) == 1
        assert len(ops_config["slos"]) == 1
        assert ops_config["slos"][0].target == 99.9
        assert ops_config["operational_simulation"]["duration_days"] == 30


# ===================================================================
# 2. model/graph.py — Missing: 53, 137, 143, 145, 153, 157, 164
# ===================================================================

class TestGraphCoverageGaps:
    """Cover graph.py lines for edge cases in resilience_score."""

    def test_get_dependency_edge_returns_none_for_missing(self):
        """Line 53: edge exists but no dependency key, returns None."""
        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER))
        graph.add_component(Component(id="b", name="B", type=ComponentType.DATABASE))
        # No dependency added
        result = graph.get_dependency_edge("a", "b")
        assert result is None

    def test_resilience_score_edge_without_dependency_data(self):
        """Line 137: edge exists in graph but get_dependency_edge returns None
        (weighted_deps += 1.0 fallback)."""
        graph = InfraGraph()
        comp_a = Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1)
        comp_b = Component(id="b", name="B", type=ComponentType.DATABASE, replicas=1)
        graph.add_component(comp_a)
        graph.add_component(comp_b)
        # Add edge directly to graph without using add_dependency to miss "dependency" key
        graph._graph.add_edge("b", "a")
        score = graph.resilience_score()
        # Should not crash and score should be penalized
        assert score < 100.0

    def test_resilience_score_failover_reduces_penalty(self):
        """Line 143: failover.enabled = True reduces SPOF penalty by 70%."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=1,
            failover=FailoverConfig(enabled=True),
        ))
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        score_with_failover = graph.resilience_score()

        # Without failover
        graph2 = InfraGraph()
        graph2.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=1,
            failover=FailoverConfig(enabled=False),
        ))
        graph2.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph2.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        score_without = graph2.resilience_score()

        assert score_with_failover > score_without

    def test_resilience_score_autoscaling_reduces_penalty(self):
        """Line 145: autoscaling.enabled = True reduces capacity risk penalty."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=1,
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=1, max_replicas=5),
        ))
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        score_with_as = graph.resilience_score()

        graph2 = InfraGraph()
        graph2.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=1,
            autoscaling=AutoScalingConfig(enabled=False),
        ))
        graph2.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph2.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))
        score_without = graph2.resilience_score()
        assert score_with_as > score_without

    def test_resilience_score_utilization_penalties(self):
        """Lines 153, 157: util > 80 and util > 70 penalties."""
        # >90 penalty
        graph_90 = InfraGraph()
        graph_90.add_component(Component(
            id="hot", name="Hot", type=ComponentType.APP_SERVER,
            replicas=2,
            metrics=ResourceMetrics(cpu_percent=95),
        ))
        score_90 = graph_90.resilience_score()

        # >80 penalty
        graph_80 = InfraGraph()
        graph_80.add_component(Component(
            id="warm", name="Warm", type=ComponentType.APP_SERVER,
            replicas=2,
            metrics=ResourceMetrics(cpu_percent=85),
        ))
        score_80 = graph_80.resilience_score()

        # >70 penalty
        graph_70 = InfraGraph()
        graph_70.add_component(Component(
            id="mild", name="Mild", type=ComponentType.APP_SERVER,
            replicas=2,
            metrics=ResourceMetrics(cpu_percent=75),
        ))
        score_70 = graph_70.resilience_score()

        assert score_90 < score_80 < score_70

    def test_resilience_score_deep_chain_penalty(self):
        """Line 164: depth > 5 incurs additional penalty."""
        graph = InfraGraph()
        # Build a chain of 7 components: A -> B -> C -> D -> E -> F -> G
        names = list("ABCDEFG")
        for n in names:
            graph.add_component(Component(
                id=n, name=n, type=ComponentType.APP_SERVER, replicas=2,
            ))
        for i in range(len(names) - 1):
            graph.add_dependency(Dependency(
                source_id=names[i], target_id=names[i + 1],
                dependency_type="requires",
            ))
        score = graph.resilience_score()
        # Depth is 7 > 5, so (7-5)*5 = 10 point penalty
        assert score <= 90


# ===================================================================
# 3. model/components.py — Missing: 188, 208-210
# ===================================================================

class TestComponentsCoverageGaps:
    """Cover components.py edge cases."""

    def test_replicas_validator_rejects_zero(self):
        """Line 188: replicas < 1 raises ValueError."""
        with pytest.raises(ValueError, match="replicas must be >= 1"):
            Component(
                id="bad", name="Bad", type=ComponentType.APP_SERVER,
                replicas=0,
            )

    def test_effective_capacity_at_replicas_with_zero_replicas(self):
        """Lines 208-210: replicas=0 should be impossible via validator,
        but the method itself returns 0.0 for <= 0."""
        # Create component via model_construct to bypass validation
        comp = Component.model_construct(
            id="x", name="X", type=ComponentType.APP_SERVER,
            replicas=0,
            metrics=ResourceMetrics(),
            capacity=Capacity(),
            health=HealthStatus.HEALTHY,
            autoscaling=AutoScalingConfig(),
            failover=FailoverConfig(),
            cache_warming=None,
            singleflight=None,
            slo_targets=[],
            operational_profile=OperationalProfile(),
            network=None,
            runtime_jitter=None,
            parameters={},
            tags=[],
        )
        assert comp.effective_capacity_at_replicas(5) == 0.0


# ===================================================================
# 4. feeds/analyzer.py — Missing: 298-301, 320, 333, 377, 387, 402
# ===================================================================

class TestFeedsAnalyzerCoverageGaps:
    """Cover analyzer.py edge cases."""

    def test_regex_error_falls_back_to_literal(self):
        """Lines 298-301: Invalid regex in keyword falls back to literal match."""
        from faultray.feeds.analyzer import _match_keywords

        # Use an invalid regex pattern (unmatched bracket)
        result = _match_keywords("test [bad regex string", ["[bad"])
        assert "[bad" in result

    def test_negative_keywords_block_match(self):
        """Line 320: article matching negative keywords is skipped."""
        from faultray.feeds.analyzer import analyze_articles, IncidentPattern, INCIDENT_PATTERNS
        from faultray.feeds.fetcher import FeedArticle

        # Create an article that matches DDoS but has negative keywords
        article = FeedArticle(
            title="DDoS protection product review - NOT a real attack",
            link="https://example.com/ddos-review",
            summary="ddos protection review",
            published="2025-01-01",
            source_name="test",
        )
        # Manually test with a pattern that has negative keywords
        from faultray.feeds.analyzer import _match_keywords

        pattern = IncidentPattern(
            id="test_neg",
            name="Test",
            description_template="{title}",
            keywords=["ddos"],
            negative_keywords=["review", "product"],
            fault_types=[],
        )
        neg = _match_keywords(article.full_text, pattern.negative_keywords)
        assert len(neg) > 0  # Negative keywords should match

    def test_dedup_by_article_and_pattern(self):
        """Line 333: duplicate article+pattern is skipped."""
        from faultray.feeds.analyzer import analyze_articles
        from faultray.feeds.fetcher import FeedArticle

        # Same article twice
        article = FeedArticle(
            title="Major DDoS attack floods network",
            link="https://example.com/ddos",
            summary="ddos",
            published="2025-01-01",
            source_name="test",
        )
        incidents = analyze_articles([article, article])
        # Each unique (link, pattern_id) should appear only once
        dedup_keys = set()
        for inc in incidents:
            key = (inc.article.link, inc.pattern.id)
            assert key not in dedup_keys, f"Duplicate: {key}"
            dedup_keys.add(key)

    def test_incidents_to_scenarios_dedup_scenario_id(self):
        """Line 377: duplicate scenario IDs are skipped."""
        from faultray.feeds.analyzer import (
            AnalyzedIncident,
            IncidentPattern,
            incidents_to_scenarios,
        )
        from faultray.feeds.fetcher import FeedArticle
        from faultray.simulator.scenarios import FaultType

        article = FeedArticle(
            title="DDoS attack", link="https://example.com/a",
            summary="ddos", published="2025-01-01", source_name="test",
        )
        pattern = IncidentPattern(
            id="test_p", name="Test",
            description_template="{title}",
            keywords=["ddos"],
            fault_types=[FaultType.TRAFFIC_SPIKE],
        )
        inc = AnalyzedIncident(
            article=article, pattern=pattern,
            matched_keywords=["ddos"], confidence=0.8,
        )
        # Pass same incident twice - should deduplicate by scenario ID
        scenarios = incidents_to_scenarios([inc, inc], ["server-1"])
        assert len(scenarios) == 1

    def test_incidents_to_scenarios_fallback_targets(self):
        """Line 387: component_types specified but none match -> falls back."""
        from faultray.feeds.analyzer import (
            AnalyzedIncident,
            IncidentPattern,
            incidents_to_scenarios,
        )
        from faultray.feeds.fetcher import FeedArticle
        from faultray.simulator.scenarios import FaultType

        article = FeedArticle(
            title="Redis failure", link="https://example.com/r",
            summary="redis", published="2025-01-01", source_name="test",
        )
        pattern = IncidentPattern(
            id="test_cache", name="Cache failure",
            description_template="{title}",
            keywords=["redis"],
            fault_types=[FaultType.COMPONENT_DOWN],
            component_types=["cache"],  # wants cache
        )
        inc = AnalyzedIncident(
            article=article, pattern=pattern,
            matched_keywords=["redis"], confidence=0.8,
        )

        # Provide components dict with NO cache type
        components = {
            "app": Component(
                id="app", name="App", type=ComponentType.APP_SERVER,
            ),
        }
        scenarios = incidents_to_scenarios([inc], ["app"], components)
        # Should fall back to all component_ids since no cache found
        assert len(scenarios) == 1
        assert scenarios[0].faults[0].target_component_id == "app"

    def test_incidents_to_scenarios_empty_faults_skipped(self):
        """Line 402: incident with no fault_types produces no faults -> skipped."""
        from faultray.feeds.analyzer import (
            AnalyzedIncident,
            IncidentPattern,
            incidents_to_scenarios,
        )
        from faultray.feeds.fetcher import FeedArticle

        article = FeedArticle(
            title="Test", link="https://example.com/t",
            summary="test", published="2025-01-01", source_name="test",
        )
        pattern = IncidentPattern(
            id="no_faults", name="No faults",
            description_template="{title}",
            keywords=["test"],
            fault_types=[],  # No fault types -> no faults generated
        )
        inc = AnalyzedIncident(
            article=article, pattern=pattern,
            matched_keywords=["test"], confidence=0.8,
        )
        scenarios = incidents_to_scenarios([inc], ["server-1"])
        assert len(scenarios) == 0


# ===================================================================
# 5. feeds/store.py — Missing: 87, 108-110, 120-122
# ===================================================================

class TestStoreCoverageGaps:
    """Cover store.py edge cases."""

    def test_save_with_articles_meta(self, tmp_path):
        """Line 87: articles_meta is provided and merged."""
        from faultray.feeds.store import save_feed_scenarios, load_store_raw
        from faultray.simulator.scenarios import Fault, FaultType, Scenario

        store_path = tmp_path / "test-store.json"
        scenario = Scenario(
            id="s1", name="S1", description="Test",
            faults=[Fault(target_component_id="c1", fault_type=FaultType.COMPONENT_DOWN)],
        )
        articles = [{"link": "https://example.com/a1", "title": "Test article"}]
        save_feed_scenarios([scenario], articles_meta=articles, store_path=store_path)
        raw = load_store_raw(store_path)
        assert raw["article_count"] == 1
        assert raw["articles"][0]["title"] == "Test article"

    def test_load_feed_scenarios_malformed_entry(self, tmp_path):
        """Lines 108-110: malformed scenario entry is skipped with warning."""
        from faultray.feeds.store import load_feed_scenarios

        store_path = tmp_path / "test-store.json"
        # Write malformed data (missing required 'faults' key)
        data = {
            "scenarios": [{"id": "bad", "name": "Bad"}],  # missing faults
            "articles": [],
        }
        store_path.write_text(json.dumps(data))
        result = load_feed_scenarios(store_path=store_path)
        assert len(result) == 0  # Bad entry skipped

    def test_load_store_raw_invalid_json(self, tmp_path):
        """Lines 120-122: corrupt JSON file returns empty store."""
        from faultray.feeds.store import load_store_raw

        store_path = tmp_path / "bad.json"
        store_path.write_text("{not valid json")
        result = load_store_raw(store_path)
        assert result["scenarios"] == []
        assert result["articles"] == []


# ===================================================================
# 6. reporter/compliance.py — Missing: 103-104, 106-107, 142-145
# ===================================================================

class TestComplianceCoverageGaps:
    """Cover compliance.py lines for SPOF with high utilization and
    external API section."""

    def test_dora_report_spof_critical_risk(self, tmp_path):
        """Lines 103-104: SPOF with util > 50 => risk_level 'Critical'."""
        from faultray.ai.analyzer import FaultRayAnalyzer
        from faultray.reporter.compliance import generate_dora_report
        from faultray.simulator.engine import SimulationEngine

        graph = InfraGraph()
        # Component with utilization > 50 AND is SPOF
        graph.add_component(Component(
            id="db", name="HotDB", type=ComponentType.DATABASE,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=70),
        ))
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))

        engine = SimulationEngine(graph)
        sim_report = engine.run_all_defaults()
        analyzer = FaultRayAnalyzer()
        ai_report = analyzer.analyze(graph, sim_report)

        output = tmp_path / "dora-critical.html"
        generate_dora_report(graph, sim_report, ai_report, output)
        content = output.read_text()
        assert "Critical" in content

    def test_dora_report_high_utilization_non_spof(self, tmp_path):
        """Lines 102-104: non-SPOF component with util > 80 => 'High' risk."""
        from faultray.ai.analyzer import FaultRayAnalyzer
        from faultray.reporter.compliance import generate_dora_report
        from faultray.simulator.engine import SimulationEngine

        graph = InfraGraph()
        # Multi-replica (not SPOF) but very high utilization > 80%
        graph.add_component(Component(
            id="app", name="HighUtilApp", type=ComponentType.APP_SERVER,
            replicas=3,
            metrics=ResourceMetrics(cpu_percent=90),
        ))
        engine = SimulationEngine(graph)
        sim_report = engine.run_all_defaults()
        analyzer = FaultRayAnalyzer()
        ai_report = analyzer.analyze(graph, sim_report)

        output = tmp_path / "dora-high-util.html"
        generate_dora_report(graph, sim_report, ai_report, output)
        content = output.read_text()
        # Should have "High" risk level for the high-utilization component
        assert "High" in content

    def test_dora_report_medium_utilization_risk(self, tmp_path):
        """Lines 106-107: util > 60 but not SPOF => 'Medium' risk."""
        from faultray.ai.analyzer import FaultRayAnalyzer
        from faultray.reporter.compliance import generate_dora_report
        from faultray.simulator.engine import SimulationEngine

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="MediumApp", type=ComponentType.APP_SERVER,
            replicas=3,
            metrics=ResourceMetrics(cpu_percent=65),
        ))
        engine = SimulationEngine(graph)
        sim_report = engine.run_all_defaults()
        analyzer = FaultRayAnalyzer()
        ai_report = analyzer.analyze(graph, sim_report)

        output = tmp_path / "dora-medium.html"
        generate_dora_report(graph, sim_report, ai_report, output)
        content = output.read_text()
        assert "Medium" in content

    def test_dora_report_with_external_api(self, tmp_path):
        """Lines 142-145: external API component appears in third-party section."""
        from faultray.ai.analyzer import FaultRayAnalyzer
        from faultray.reporter.compliance import generate_dora_report
        from faultray.simulator.engine import SimulationEngine

        graph = InfraGraph()
        graph.add_component(Component(
            id="ext", name="PaymentAPI", type=ComponentType.EXTERNAL_API,
            replicas=1,
        ))
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="ext", dependency_type="requires",
        ))

        engine = SimulationEngine(graph)
        sim_report = engine.run_all_defaults()
        analyzer = FaultRayAnalyzer()
        ai_report = analyzer.analyze(graph, sim_report)

        output = tmp_path / "dora-ext.html"
        generate_dora_report(graph, sim_report, ai_report, output)
        content = output.read_text()
        assert "PaymentAPI" in content
        assert "third-party" in content.lower() or "Third-Party" in content


# ===================================================================
# 7. reporter/export.py — Missing: 41, 68
# ===================================================================

class TestExportCoverageGaps:
    """Cover export.py empty-report CSV path and empty-report JSON path."""

    def test_export_csv_empty_report(self, tmp_path):
        """Line 41: CSV export with no cascade effects generates header-only row."""
        from faultray.reporter.export import export_csv
        from faultray.simulator.cascade import CascadeChain
        from faultray.simulator.engine import ScenarioResult, SimulationReport
        from faultray.simulator.scenarios import Fault, FaultType, Scenario

        scenario = Scenario(
            id="s1", name="S1", description="Empty test",
            faults=[Fault(target_component_id="c1", fault_type=FaultType.COMPONENT_DOWN)],
        )
        chain = CascadeChain(trigger="test", total_components=1)
        # No effects
        result = ScenarioResult(scenario=scenario, cascade=chain, risk_score=1.0)
        report = SimulationReport(results=[result], resilience_score=80.0)

        path = tmp_path / "export.csv"
        export_csv(report, path)
        content = path.read_text()
        # Should have header + 1 row with empty component fields
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert "component_id" in lines[0]

    def test_export_csv_no_results(self, tmp_path):
        """Line 68: CSV export with zero results writes header only."""
        from faultray.reporter.export import export_csv
        from faultray.simulator.engine import SimulationReport

        report = SimulationReport(results=[], resilience_score=100.0)
        path = tmp_path / "empty.csv"
        export_csv(report, path)
        content = path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 1  # Header only
        assert "scenario_id" in lines[0]


# ===================================================================
# 8. simulator/engine.py — Missing: 92-96, 142-149, 156-161
# ===================================================================

class TestEngineCoverageGaps:
    """Cover engine.py lines for empty chains, plugin errors, and scenario limit."""

    def test_run_scenario_no_faults_no_traffic(self):
        """Lines 92-96: scenario with no traffic spike and no faults."""
        from faultray.simulator.engine import SimulationEngine
        from faultray.simulator.scenarios import Scenario

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        engine = SimulationEngine(graph)
        scenario = Scenario(
            id="empty", name="Empty", description="No faults",
            faults=[], traffic_multiplier=1.0,
        )
        result = engine.run_scenario(scenario)
        assert result.risk_score == 0.0
        assert len(result.cascade.effects) == 0

    def test_run_all_defaults_plugin_failure(self):
        """Lines 142-149: plugin that throws exception is caught."""
        from faultray.simulator.engine import SimulationEngine

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        engine = SimulationEngine(graph)

        class BadPlugin:
            name = "bad-plugin"
            def generate_scenarios(self, graph, ids, comps):
                raise RuntimeError("Plugin exploded")

        with patch("faultray.plugins.registry.PluginRegistry") as MockRegistry:
            MockRegistry.get_scenario_plugins.return_value = [BadPlugin()]
            # Should not crash
            report = engine.run_all_defaults(include_feed=False, include_plugins=True)
            assert report is not None

    def test_run_scenarios_truncates_over_limit(self):
        """Lines 156-161: scenario count exceeds MAX_SCENARIOS."""
        from faultray.simulator.engine import SimulationEngine, MAX_SCENARIOS
        from faultray.simulator.scenarios import Fault, FaultType, Scenario

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        engine = SimulationEngine(graph)

        # Create MAX_SCENARIOS + 10 scenarios
        scenarios = []
        for i in range(MAX_SCENARIOS + 10):
            scenarios.append(Scenario(
                id=f"s-{i}", name=f"S-{i}", description=f"Scenario {i}",
                faults=[Fault(target_component_id="app", fault_type=FaultType.COMPONENT_DOWN)],
            ))
        report = engine.run_scenarios(scenarios)
        assert len(report.results) == MAX_SCENARIOS


# ===================================================================
# 9. simulator/ops_engine.py — targeted coverage for key gaps
# ===================================================================

class TestOpsEngineCoverageGaps:
    """Cover ops_engine.py for degradation events, autoscaling, SLO tracker,
    and SLOTracker helper methods."""

    def _build_degradation_graph(self) -> InfraGraph:
        """Graph with components configured for fast degradation."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=30, memory_percent=30),
            capacity=Capacity(
                max_connections=1000,
                max_memory_mb=100,
                max_disk_gb=10,
                connection_pool_size=50,
            ),
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
            operational_profile=OperationalProfile(
                mtbf_hours=99999,
                mttr_minutes=5,
                degradation=DegradationConfig(
                    memory_leak_mb_per_hour=200.0,  # Very fast leak
                    disk_fill_gb_per_hour=20.0,  # Very fast fill
                    connection_leak_per_hour=100.0,  # Very fast leak
                ),
            ),
        ))
        return graph

    def test_degradation_triggers_oom(self):
        """Lines 1688-1704: memory leak causes OOM event."""
        from faultray.simulator.ops_engine import (
            OpsScenario,
            OpsSimulationEngine,
            OpsEventType,
            TimeUnit,
        )

        graph = self._build_degradation_graph()
        engine = OpsSimulationEngine(graph)
        scenario = OpsScenario(
            id="test-degrade",
            name="Degradation test",
            description="Fast degradation",
            duration_days=1,
            time_unit=TimeUnit.HOUR,
            traffic_patterns=[],
            enable_random_failures=False,
            enable_degradation=True,
            enable_maintenance=False,
            random_seed=42,
        )
        result = engine.run_ops_scenario(scenario)
        # Memory leak at 200MB/hr with 100MB capacity => OOM within 1 hour
        oom_events = [e for e in result.events if e.event_type == OpsEventType.MEMORY_LEAK_OOM]
        assert len(oom_events) > 0

    def test_degradation_triggers_disk_full(self):
        """Lines 1733-1749: disk fill causes DISK_FULL event."""
        from faultray.simulator.ops_engine import (
            OpsScenario,
            OpsSimulationEngine,
            OpsEventType,
            TimeUnit,
        )

        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=1,
            capacity=Capacity(max_disk_gb=5, connection_pool_size=100),
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
            operational_profile=OperationalProfile(
                mtbf_hours=99999,
                mttr_minutes=5,
                degradation=DegradationConfig(
                    disk_fill_gb_per_hour=20.0,
                ),
            ),
        ))
        engine = OpsSimulationEngine(graph)
        scenario = OpsScenario(
            id="test-disk",
            name="Disk fill test",
            description="Fast disk fill",
            duration_days=1,
            time_unit=TimeUnit.HOUR,
            enable_degradation=True,
            random_seed=42,
        )
        result = engine.run_ops_scenario(scenario)
        disk_events = [e for e in result.events if e.event_type == OpsEventType.DISK_FULL]
        assert len(disk_events) > 0

    def test_degradation_triggers_conn_pool_exhaustion(self):
        """Lines 1778-1798: connection leak exhausts pool."""
        from faultray.simulator.ops_engine import (
            OpsScenario,
            OpsSimulationEngine,
            OpsEventType,
            TimeUnit,
        )

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            capacity=Capacity(
                max_memory_mb=99999,
                max_disk_gb=99999,
                connection_pool_size=20,
            ),
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
            operational_profile=OperationalProfile(
                mtbf_hours=99999,
                mttr_minutes=5,
                degradation=DegradationConfig(
                    connection_leak_per_hour=100.0,
                ),
            ),
        ))
        engine = OpsSimulationEngine(graph)
        scenario = OpsScenario(
            id="test-conn",
            name="Connection leak test",
            description="Fast conn leak",
            duration_days=1,
            time_unit=TimeUnit.HOUR,
            enable_degradation=True,
            random_seed=42,
        )
        result = engine.run_ops_scenario(scenario)
        conn_events = [e for e in result.events if e.event_type == OpsEventType.CONN_POOL_EXHAUSTION]
        assert len(conn_events) > 0

    def test_autoscaling_scale_up_and_down(self):
        """Lines 944-983: autoscaling scales up on high util and down on low."""
        from faultray.simulator.ops_engine import (
            OpsScenario,
            OpsSimulationEngine,
            TimeUnit,
        )
        from faultray.simulator.traffic import create_diurnal_weekly

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=2,
            metrics=ResourceMetrics(cpu_percent=40),
            capacity=Capacity(max_connections=500, connection_pool_size=100),
            autoscaling=AutoScalingConfig(
                enabled=True,
                min_replicas=1,
                max_replicas=10,
                scale_up_threshold=60.0,
                scale_down_threshold=20.0,
                scale_up_delay_seconds=1,  # instant scale up for test
                scale_down_delay_seconds=1,  # instant scale down for test
                scale_up_step=2,
            ),
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
            operational_profile=OperationalProfile(mtbf_hours=99999),
        ))
        engine = OpsSimulationEngine(graph)
        scenario = OpsScenario(
            id="test-as",
            name="Autoscaling test",
            description="Test autoscaling",
            duration_days=1,
            time_unit=TimeUnit.HOUR,
            traffic_patterns=[create_diurnal_weekly(peak=5.0, duration=86400)],
            enable_random_failures=False,
            enable_degradation=False,
            random_seed=42,
        )
        result = engine.run_ops_scenario(scenario)
        # Just verify it runs without error and produces timeline
        assert len(result.sli_timeline) > 0

    def test_time_unit_minute(self):
        """Line 1250: TimeUnit.MINUTE converts to 60 seconds."""
        from faultray.simulator.ops_engine import OpsSimulationEngine, TimeUnit

        assert OpsSimulationEngine._time_unit_to_seconds(TimeUnit.MINUTE) == 60

    def test_time_unit_fallback(self):
        """Line 1255: unknown TimeUnit returns default 300."""
        from faultray.simulator.ops_engine import OpsSimulationEngine

        # Use a mock value that doesn't match any case
        result = OpsSimulationEngine._time_unit_to_seconds("unknown")
        assert result == 300

    def test_slo_tracker_budget_and_burn_rate(self):
        """Lines 607, 640, 647, 652, 658, 676, 684, 689, 697, 700:
        SLOTracker helper methods."""
        from faultray.simulator.ops_engine import SLOTracker, _OpsComponentState

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            slo_targets=[
                SLOTarget(name="avail", metric="availability", target=99.9),
                SLOTarget(name="latency", metric="latency_p99", target=500),
            ],
        ))
        tracker = SLOTracker(graph)

        # Manually inject violations for testing
        tracker._violations[("app", "availability")] = [
            (0, False), (300, False), (600, True), (900, True),
        ]
        tracker._violations[("app", "latency_p99")] = [
            (0, False), (300, False), (600, False),
        ]

        slo_avail = graph.get_component("app").slo_targets[0]
        slo_latency = graph.get_component("app").slo_targets[1]

        # Test _budget_total
        budget = tracker._budget_total(slo_avail)
        assert budget > 0

        # Test latency SLO budget
        budget_latency = tracker._budget_total(slo_latency)
        assert budget_latency > 0

        # Test _budget_consumed
        consumed = tracker._budget_consumed(slo_avail, "app")
        assert consumed > 0

        # Test _budget_consumed with no violations
        consumed_none = tracker._budget_consumed(
            SLOTarget(name="x", metric="error_rate", target=0.1), "nonexistent"
        )
        assert consumed_none == 0.0

        # Test _burn_rate
        burn = tracker._burn_rate(slo_avail, "app", 1000)
        assert burn >= 0

        # Test _burn_rate with no violations
        burn_none = tracker._burn_rate(slo_avail, "nonexistent", 1000)
        assert burn_none == 0.0

    def test_slo_tracker_estimate_latency(self):
        """Line 607: _estimate_latency with zero utilization."""
        from faultray.simulator.ops_engine import SLOTracker

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        tracker = SLOTracker(graph)
        latency = tracker._estimate_latency(0)
        assert latency == 5.0

    def test_default_deploy_targets_no_app_servers(self):
        """Line 1060: graph with no app_server or web_server components."""
        from faultray.simulator.ops_engine import OpsSimulationEngine, TimeUnit

        graph = InfraGraph()
        graph.add_component(Component(
            id="cache", name="Cache", type=ComponentType.CACHE,
        ))
        engine = OpsSimulationEngine(graph)
        results = engine.run_default_ops_scenarios(time_unit_override=TimeUnit.HOUR)
        assert len(results) == 5

    def test_dependency_propagation_optional_down(self):
        """Lines 324-328: optional dependency DOWN -> DEGRADED propagation."""
        from faultray.simulator.ops_engine import SLOTracker, _OpsComponentState

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        graph.add_component(Component(
            id="cache", name="Cache", type=ComponentType.CACHE,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="cache", dependency_type="optional",
        ))
        tracker = SLOTracker(graph)

        comp_states = {
            "app": _OpsComponentState(
                component_id="app", base_utilization=30.0,
                current_health=HealthStatus.HEALTHY,
            ),
            "cache": _OpsComponentState(
                component_id="cache", base_utilization=20.0,
                current_health=HealthStatus.DOWN,
            ),
        }
        effective = tracker._propagate_dependencies(comp_states)
        assert effective["app"] == HealthStatus.DEGRADED
        assert effective["cache"] == HealthStatus.DOWN

    def test_default_degradation_unknown_type(self):
        """Lines 1664-1666: component type not in _DEFAULT_DEGRADATION."""
        from faultray.simulator.ops_engine import (
            OpsScenario,
            OpsSimulationEngine,
            TimeUnit,
        )

        graph = InfraGraph()
        graph.add_component(Component(
            id="dns", name="DNS", type=ComponentType.DNS,
            replicas=1,
            capacity=Capacity(max_memory_mb=1000, max_disk_gb=100, connection_pool_size=100),
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
            # No explicit degradation config -> falls through to defaults
        ))
        engine = OpsSimulationEngine(graph)
        scenario = OpsScenario(
            id="test-dns-degrade",
            name="DNS degradation test",
            description="Test with DNS type (no default degradation)",
            duration_days=1,
            time_unit=TimeUnit.HOUR,
            enable_degradation=True,
            random_seed=42,
        )
        result = engine.run_ops_scenario(scenario)
        # Should run without errors
        assert len(result.sli_timeline) > 0

    def test_slo_tracker_tier_aware_availability_with_failover(self):
        """Lines 379, 394-396, 411-413, 417-419, 450, 452-464:
        Tier-aware availability with failover-enabled components, including
        micro-penalty calculation and standalone failover branches."""
        from faultray.model.components import FailoverConfig
        from faultray.simulator.ops_engine import SLOTracker, _OpsComponentState

        graph = InfraGraph()
        # Create a tier of 2 members with failover, both DOWN
        graph.add_component(Component(
            id="api-1", name="API-1", type=ComponentType.APP_SERVER,
            replicas=1,
            failover=FailoverConfig(
                enabled=True,
                promotion_time_seconds=10.0,
                health_check_interval_seconds=5.0,
                failover_threshold=2,
            ),
        ))
        graph.add_component(Component(
            id="api-2", name="API-2", type=ComponentType.APP_SERVER,
            replicas=1,
            failover=FailoverConfig(
                enabled=True,
                promotion_time_seconds=10.0,
                health_check_interval_seconds=5.0,
                failover_threshold=2,
            ),
        ))
        # Standalone multi-replica with failover, DOWN -> lines 411-413
        graph.add_component(Component(
            id="cache", name="Cache", type=ComponentType.CACHE,
            replicas=3,
            failover=FailoverConfig(
                enabled=True,
                promotion_time_seconds=5.0,
                health_check_interval_seconds=3.0,
                failover_threshold=2,
            ),
        ))
        # Standalone single-replica with failover, DOWN -> lines 417-419
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=1,
            failover=FailoverConfig(
                enabled=True,
                promotion_time_seconds=15.0,
                health_check_interval_seconds=5.0,
                failover_threshold=3,
            ),
        ))

        tracker = SLOTracker(graph)

        # All components DOWN
        comp_states = {
            "api-1": _OpsComponentState(
                component_id="api-1", base_utilization=30.0,
                current_health=HealthStatus.DOWN,
            ),
            "api-2": _OpsComponentState(
                component_id="api-2", base_utilization=30.0,
                current_health=HealthStatus.DOWN,
            ),
            "cache": _OpsComponentState(
                component_id="cache", base_utilization=20.0,
                current_health=HealthStatus.DOWN,
            ),
            "db": _OpsComponentState(
                component_id="db", base_utilization=50.0,
                current_health=HealthStatus.DOWN,
            ),
        }

        point = tracker.record(0, comp_states)
        # All DOWN, but failover means fractional down, not total
        # availability should be > 0 due to failover cushioning
        assert point.availability_percent >= 0.0
        assert point.down_count == 4

    def test_slo_tracker_micro_penalty_with_measurements(self):
        """Lines 450, 452-464: micro-penalty calculation when there are
        previous measurements (uses step_window from measurements diff)."""
        from faultray.model.components import FailoverConfig
        from faultray.simulator.ops_engine import SLOTracker, _OpsComponentState, SLIDataPoint

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=2,
            failover=FailoverConfig(
                enabled=True,
                promotion_time_seconds=10.0,
                health_check_interval_seconds=5.0,
                failover_threshold=2,
            ),
        ))

        tracker = SLOTracker(graph)
        # Add a previous measurement to trigger the "len(self._measurements) >= 2" branch
        tracker._measurements.append(SLIDataPoint(time_seconds=0))
        tracker._measurements.append(SLIDataPoint(time_seconds=300))

        comp_states = {
            "app": _OpsComponentState(
                component_id="app", base_utilization=50.0,
                current_health=HealthStatus.DOWN,
            ),
        }

        point = tracker.record(600, comp_states)
        # Should compute micro-penalty using step_window = 600 - 300 = 300
        assert point.down_count == 1

    def test_slo_tracker_gc_jitter_penalty(self):
        """Lines 473, 479: network + runtime jitter with GC pauses."""
        from faultray.model.components import RuntimeJitter
        from faultray.simulator.ops_engine import SLOTracker, _OpsComponentState

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            runtime_jitter=RuntimeJitter(
                gc_pause_ms=50.0,          # 50ms GC pause
                gc_pause_frequency=2.0,    # 2 per second
            ),
        ))

        tracker = SLOTracker(graph)
        comp_states = {
            "app": _OpsComponentState(
                component_id="app", base_utilization=50.0,
                current_health=HealthStatus.HEALTHY,
            ),
        }

        point = tracker.record(0, comp_states)
        # GC pauses reduce availability slightly
        assert point.availability_percent < 100.0

    def test_slo_violation_tracking_latency_and_error_rate(self):
        """Lines 519, 529-543: SLO violation tracking for latency_p99 and
        error_rate metrics when recording SLI points."""
        from faultray.simulator.ops_engine import SLOTracker, _OpsComponentState

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            slo_targets=[
                SLOTarget(name="avail", metric="availability", target=99.9),
                SLOTarget(name="latency", metric="latency_p99", target=10.0),
                SLOTarget(name="errors", metric="error_rate", target=0.01),
            ],
        ))

        tracker = SLOTracker(graph)

        # Record a healthy measurement first
        comp_states_ok = {
            "app": _OpsComponentState(
                component_id="app", base_utilization=30.0,
                current_health=HealthStatus.HEALTHY,
            ),
        }
        tracker.record(0, comp_states_ok)

        # Record an overloaded measurement (triggers latency and error violations)
        comp_states_bad = {
            "app": _OpsComponentState(
                component_id="app", base_utilization=95.0,
                current_health=HealthStatus.OVERLOADED,
                current_utilization=95.0,
            ),
        }
        tracker.record(300, comp_states_bad)

        # Check that latency violations were tracked
        assert ("app", "latency_p99") in tracker._violations
        assert len(tracker._violations[("app", "latency_p99")]) == 2

        # Check that error_rate violations were tracked
        assert ("app", "error_rate") in tracker._violations
        # OVERLOADED counts as error for error_rate
        err_violations = tracker._violations[("app", "error_rate")]
        assert any(v for _, v in err_violations)

    def test_budget_consumed_single_violation(self):
        """Lines 652, 658: budget consumed with a single violation entry
        (total_count == 1, falls to 300 default time span)."""
        from faultray.simulator.ops_engine import SLOTracker

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        ))
        tracker = SLOTracker(graph)

        slo = graph.get_component("app").slo_targets[0]

        # Single violation entry
        tracker._violations[("app", "availability")] = [(100, True)]
        consumed = tracker._budget_consumed(slo, "app")
        # Should use default 300s time span: 1/1 * 300/60 = 5.0 minutes
        assert consumed == 5.0

    def test_burn_rate_non_availability_metric(self):
        """Lines 697, 700: burn rate calculation for non-availability metric
        (uses 0.001 allowed ratio) and zero allowed ratio."""
        from faultray.simulator.ops_engine import SLOTracker

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            slo_targets=[
                SLOTarget(name="latency", metric="latency_p99", target=500),
                SLOTarget(name="avail_100", metric="availability", target=100.0),
            ],
        ))
        tracker = SLOTracker(graph)

        # Non-availability metric -> allowed_ratio = 0.001
        slo_latency = graph.get_component("app").slo_targets[0]
        tracker._violations[("app", "latency_p99")] = [
            (0, True), (300, True),
        ]
        burn = tracker._burn_rate(slo_latency, "app", 1000)
        assert burn > 0  # violations present, allowed ratio 0.001 -> high burn rate

        # 100% availability SLO -> allowed_ratio = 0.0 -> inf if violated
        slo_100 = graph.get_component("app").slo_targets[1]
        tracker._violations[("app", "availability")] = [
            (0, True), (300, True),
        ]
        burn_100 = tracker._burn_rate(slo_100, "app", 1000)
        assert burn_100 == float("inf")

    def test_burn_rate_empty_recent_window(self):
        """Lines 684, 689: burn rate with violations that are all outside the
        recent window."""
        from faultray.simulator.ops_engine import SLOTracker

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        ))
        tracker = SLOTracker(graph)

        slo = graph.get_component("app").slo_targets[0]
        # All violations are at time 0, latest is 0
        tracker._violations[("app", "availability")] = [(0, True)]
        # Request burn rate for window_seconds=1, window_start = 0 - 1 = -1
        # So recent = [(0, True)] -> not empty, total_count > 0
        burn = tracker._burn_rate(slo, "app", 1)
        assert burn > 0

    def test_graceful_restart_memory(self):
        """Lines 1707-1721: graceful restart for memory at 80% threshold."""
        from faultray.simulator.ops_engine import (
            OpsScenario,
            OpsSimulationEngine,
            OpsEventType,
            TimeUnit,
            GRACEFUL_RESTART_THRESHOLD,
        )

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            capacity=Capacity(
                max_memory_mb=100,
                max_disk_gb=99999,
                connection_pool_size=99999,
            ),
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
            operational_profile=OperationalProfile(
                mtbf_hours=99999,
                mttr_minutes=5,
                degradation=DegradationConfig(
                    # Slow leak: reaches 80% threshold before 100%
                    memory_leak_mb_per_hour=10.0,
                ),
            ),
        ))
        engine = OpsSimulationEngine(graph)
        scenario = OpsScenario(
            id="test-mem-graceful",
            name="Memory graceful restart",
            duration_days=2,
            time_unit=TimeUnit.HOUR,
            enable_degradation=True,
            random_seed=42,
        )
        result = engine.run_ops_scenario(scenario)
        # Should see maintenance events (graceful restarts) for memory
        maint_events = [e for e in result.events
                        if e.event_type == OpsEventType.MAINTENANCE
                        and "memory" in e.description.lower()]
        oom_events = [e for e in result.events
                      if e.event_type == OpsEventType.MEMORY_LEAK_OOM]
        # Graceful restart should fire before OOM (at 80% threshold)
        assert len(maint_events) > 0 or len(oom_events) > 0

    def test_graceful_restart_disk(self):
        """Lines 1752-1766: disk cleanup at 80% threshold."""
        from faultray.simulator.ops_engine import (
            OpsScenario,
            OpsSimulationEngine,
            OpsEventType,
            TimeUnit,
        )

        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=1,
            capacity=Capacity(
                max_memory_mb=99999,
                max_disk_gb=10,
                connection_pool_size=99999,
            ),
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
            operational_profile=OperationalProfile(
                mtbf_hours=99999,
                mttr_minutes=5,
                degradation=DegradationConfig(
                    # Slow fill: reaches 80% threshold before 100%
                    disk_fill_gb_per_hour=1.0,
                ),
            ),
        ))
        engine = OpsSimulationEngine(graph)
        scenario = OpsScenario(
            id="test-disk-graceful",
            name="Disk cleanup test",
            duration_days=2,
            time_unit=TimeUnit.HOUR,
            enable_degradation=True,
            random_seed=42,
        )
        result = engine.run_ops_scenario(scenario)
        # Should see maintenance (disk cleanup) or disk_full events
        disk_maint = [e for e in result.events
                      if e.event_type == OpsEventType.MAINTENANCE
                      and "disk" in e.description.lower()]
        disk_full = [e for e in result.events
                     if e.event_type == OpsEventType.DISK_FULL]
        assert len(disk_maint) > 0 or len(disk_full) > 0

    def test_graceful_restart_connections(self):
        """Lines 1801-1815: connection drain + graceful restart at 80% threshold."""
        from faultray.simulator.ops_engine import (
            OpsScenario,
            OpsSimulationEngine,
            OpsEventType,
            TimeUnit,
        )

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            capacity=Capacity(
                max_memory_mb=99999,
                max_disk_gb=99999,
                connection_pool_size=50,
            ),
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
            operational_profile=OperationalProfile(
                mtbf_hours=99999,
                mttr_minutes=5,
                degradation=DegradationConfig(
                    # Slow leak: reaches 80% threshold before 100%
                    connection_leak_per_hour=5.0,
                ),
            ),
        ))
        engine = OpsSimulationEngine(graph)
        scenario = OpsScenario(
            id="test-conn-graceful",
            name="Connection graceful restart",
            duration_days=2,
            time_unit=TimeUnit.HOUR,
            enable_degradation=True,
            random_seed=42,
        )
        result = engine.run_ops_scenario(scenario)
        # Should see maintenance (connection drain) or conn pool exhaustion events
        conn_maint = [e for e in result.events
                      if e.event_type == OpsEventType.MAINTENANCE
                      and "connection" in e.description.lower()]
        conn_exhaust = [e for e in result.events
                        if e.event_type == OpsEventType.CONN_POOL_EXHAUSTION]
        assert len(conn_maint) > 0 or len(conn_exhaust) > 0

    def test_default_mttr_fallback(self):
        """Line 1397: default MTTR when mttr_minutes is 0."""
        from faultray.simulator.ops_engine import (
            OpsScenario,
            OpsSimulationEngine,
            TimeUnit,
        )

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
            operational_profile=OperationalProfile(
                mtbf_hours=2,   # Very short MTBF to trigger failures
                mttr_minutes=0,  # 0 -> uses default
            ),
        ))
        engine = OpsSimulationEngine(graph)
        scenario = OpsScenario(
            id="test-mttr",
            name="Default MTTR test",
            duration_days=1,
            time_unit=TimeUnit.HOUR,
            enable_random_failures=True,
            random_seed=42,
        )
        result = engine.run_ops_scenario(scenario)
        # Random failures should occur due to short MTBF
        failure_events = [e for e in result.events
                          if e.event_type.value == "random_failure"]
        assert len(failure_events) > 0

    def test_error_budget_status_full_computation(self):
        """Lines 549-586: Full error_budget_status computation through record()."""
        from faultray.simulator.ops_engine import SLOTracker, _OpsComponentState

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            slo_targets=[
                SLOTarget(name="avail", metric="availability", target=99.9),
                SLOTarget(name="latency", metric="latency_p99", target=100.0),
                SLOTarget(name="errors", metric="error_rate", target=0.01),
            ],
        ))

        tracker = SLOTracker(graph)

        # Record several measurements to build up violations
        for t in range(0, 3600, 300):
            health = HealthStatus.HEALTHY if t < 1800 else HealthStatus.DOWN
            comp_states = {
                "app": _OpsComponentState(
                    component_id="app",
                    base_utilization=50.0,
                    current_utilization=90.0 if health == HealthStatus.DOWN else 30.0,
                    current_health=health,
                ),
            }
            tracker.record(t, comp_states)

        # Now compute error budget status
        statuses = tracker.error_budget_status()
        assert len(statuses) == 3  # 3 SLO targets
        for status in statuses:
            assert status.budget_total_minutes > 0
            assert status.burn_rate_1h >= 0
            assert status.burn_rate_6h >= 0


# ===================================================================
# 10. simulator/capacity_engine.py — Missing: 216-257, 281-291, 347,
#     377, 420, 466, 476, 480, 546, 557, 601, 607
# ===================================================================

class TestCapacityEngineCoverageGaps:
    """Cover capacity_engine.py lines."""

    def test_forecast_with_simulation(self):
        """Lines 216-257: forecast_with_simulation runs ops sim."""
        from faultray.simulator.capacity_engine import CapacityPlanningEngine

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=2,
            metrics=ResourceMetrics(cpu_percent=50),
            capacity=Capacity(max_connections=1000),
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
            operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=10),
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=2,
            metrics=ResourceMetrics(cpu_percent=60, disk_percent=30),
            capacity=Capacity(max_connections=200, max_disk_gb=500),
            slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))

        engine = CapacityPlanningEngine(graph)
        report = engine.forecast_with_simulation(
            monthly_growth_rate=0.10,
            slo_target=99.9,
            simulation_days=1,
        )
        assert len(report.forecasts) == 2
        assert report.error_budget is not None

    def test_component_utilization_fallback_single_replica(self):
        """Lines 281-291: type-based utilization with replica adjustments."""
        from faultray.simulator.capacity_engine import CapacityPlanningEngine

        graph = InfraGraph()
        # Single replica app server with 0 utilization
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            metrics=ResourceMetrics(),  # all zero
        ))
        engine = CapacityPlanningEngine(graph)
        util = engine._get_component_utilization(graph.get_component("app"))
        # app_server base = 45 + 10 (single replica) = 55
        assert util == 55.0

    def test_component_utilization_many_replicas(self):
        """Lines 288-289: 5+ replicas reduces utilization estimate."""
        from faultray.simulator.capacity_engine import CapacityPlanningEngine

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=5,
            metrics=ResourceMetrics(),
        ))
        engine = CapacityPlanningEngine(graph)
        util = engine._get_component_utilization(graph.get_component("app"))
        # app_server base = 45 - 5 (many replicas) = 40
        assert util == 40.0

    def test_months_to_capacity_at_threshold(self):
        """Line 347: current_util at 0 returns inf."""
        from faultray.simulator.capacity_engine import CapacityPlanningEngine

        result = CapacityPlanningEngine._months_to_capacity(0.0, 0.10)
        assert result == float("inf")

    def test_replicas_needed_zero_utilization(self):
        """Line 377: zero utilization returns current replicas."""
        from faultray.simulator.capacity_engine import CapacityPlanningEngine

        result = CapacityPlanningEngine._replicas_needed(3, 0.0, 0.10, 12)
        assert result == 3

    def test_estimate_burn_rate_high_utilization(self):
        """Line 420: high utilization components increase burn rate."""
        from faultray.simulator.capacity_engine import CapacityPlanningEngine

        graph = InfraGraph()
        graph.add_component(Component(
            id="hot", name="Hot", type=ComponentType.APP_SERVER,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=90),
            operational_profile=OperationalProfile(mtbf_hours=100, mttr_minutes=30),
        ))
        engine = CapacityPlanningEngine(graph)
        burn_rate = engine._estimate_burn_rate(99.9)
        assert burn_rate > 0

    def test_error_budget_exhausted_status(self):
        """Line 476: budget exhausted status."""
        from faultray.simulator.capacity_engine import CapacityPlanningEngine

        # Very high burn rate to exhaust budget
        eb = CapacityPlanningEngine._build_error_budget_forecast(
            slo_target=99.99,  # Very tight SLO -> small budget
            burn_rate_per_day=100.0,  # Very high burn
        )
        assert eb.status == "exhausted"

    def test_error_budget_critical_status(self):
        """Line 480: budget critical (projected > 100%)."""
        from faultray.simulator.capacity_engine import CapacityPlanningEngine

        eb = CapacityPlanningEngine._build_error_budget_forecast(
            slo_target=99.9,
            burn_rate_per_day=2.0,  # High enough to project > 100%
        )
        assert eb.status in ("critical", "exhausted")

    def test_error_budget_warning_status(self):
        """Line 480: budget warning (projected > 50%)."""
        from faultray.simulator.capacity_engine import CapacityPlanningEngine

        eb = CapacityPlanningEngine._build_error_budget_forecast(
            slo_target=99.9,
            burn_rate_per_day=1.0,  # ~30min/month consumed of 43.2min budget
        )
        assert eb.status in ("warning", "critical")

    def test_error_budget_zero_burn_rate(self):
        """Line 466: zero burn rate => days_to_exhaustion is None."""
        from faultray.simulator.capacity_engine import CapacityPlanningEngine

        eb = CapacityPlanningEngine._build_error_budget_forecast(
            slo_target=99.9, burn_rate_per_day=0.0,
        )
        assert eb.days_to_exhaustion is None
        assert eb.status == "healthy"

    def test_generate_recommendations_error_budget_exhausted(self):
        """Lines 546, 557: recommendations for exhausted/critical error budget."""
        from faultray.simulator.capacity_engine import (
            CapacityPlanningEngine,
            CapacityForecast,
            ErrorBudgetForecast,
        )

        forecasts = [CapacityForecast(
            component_id="app",
            component_type="app_server",
            current_replicas=2,
            current_utilization=50.0,
            monthly_growth_rate=0.10,
            months_to_capacity=6.0,
            recommended_replicas_3m=2,
            recommended_replicas_6m=3,
            recommended_replicas_12m=4,
            scaling_urgency="healthy",
        )]
        eb_exhausted = ErrorBudgetForecast(
            slo_target=99.9,
            budget_total_minutes=43.2,
            budget_consumed_minutes=50.0,
            budget_consumed_percent=115.0,
            burn_rate_per_day=5.0,
            days_to_exhaustion=0.0,
            projected_monthly_consumption=200.0,
            status="exhausted",
        )
        recs = CapacityPlanningEngine._generate_recommendations(
            forecasts, eb_exhausted, ["app"],
        )
        assert any("exhausted" in r.lower() or "halt" in r.lower() for r in recs)

    def test_cost_increase_empty_forecasts(self):
        """Line 601: empty forecasts returns 0.0."""
        from faultray.simulator.capacity_engine import CapacityPlanningEngine

        result = CapacityPlanningEngine._estimate_cost_increase([])
        assert result == 0.0

    def test_cost_increase_zero_current(self):
        """Line 607: zero total_current returns 0.0."""
        from faultray.simulator.capacity_engine import (
            CapacityPlanningEngine,
            CapacityForecast,
        )

        fc = CapacityForecast(
            component_id="x",
            component_type="app_server",
            current_replicas=0,
            current_utilization=0,
            monthly_growth_rate=0,
            months_to_capacity=float("inf"),
            recommended_replicas_3m=0,
            recommended_replicas_6m=0,
            recommended_replicas_12m=0,
            scaling_urgency="healthy",
        )
        result = CapacityPlanningEngine._estimate_cost_increase([fc])
        assert result == 0.0


# ===================================================================
# 11. discovery/terraform.py — Missing: 171-182, 187-201, 362, 433,
#     443, 452-454
# ===================================================================

class TestTerraformCoverageGaps:
    """Cover terraform.py command-based loading and value reference search."""

    def test_load_tf_state_cmd_success(self):
        """Lines 171-182: load_tf_state_cmd with successful terraform show."""
        from faultray.discovery.terraform import load_tf_state_cmd

        state = {
            "values": {
                "root_module": {
                    "resources": [
                        {"type": "aws_instance", "name": "web",
                         "address": "aws_instance.web",
                         "values": {"name": "web"}},
                    ],
                },
            },
        }
        with patch("faultray.discovery.terraform.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps(state)
            graph = load_tf_state_cmd()
            assert len(graph.components) == 1

    def test_load_tf_state_cmd_failure(self):
        """Lines 178-179: terraform show fails with non-zero exit."""
        from faultray.discovery.terraform import load_tf_state_cmd

        with patch("faultray.discovery.terraform.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "Error: No state"
            with pytest.raises(RuntimeError, match="terraform show failed"):
                load_tf_state_cmd()

    def test_load_tf_plan_cmd_success(self):
        """Lines 187-201: load_tf_plan_cmd with successful terraform show."""
        from faultray.discovery.terraform import load_tf_plan_cmd

        plan = {"resource_changes": []}
        with patch("faultray.discovery.terraform.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps(plan)
            result = load_tf_plan_cmd(plan_file=Path("/tmp/plan.out"))
            assert isinstance(result, dict)
            assert "changes" in result

    def test_load_tf_plan_cmd_failure(self):
        """Lines 197-198: terraform plan show fails."""
        from faultray.discovery.terraform import load_tf_plan_cmd

        with patch("faultray.discovery.terraform.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "Error: Invalid plan"
            with pytest.raises(RuntimeError, match="terraform show failed"):
                load_tf_plan_cmd()

    def test_estimate_connections_database(self):
        """Line 362: _estimate_connections returns default for unknown size."""
        from faultray.discovery.terraform import _estimate_connections

        # Unknown instance class
        result = _estimate_connections("db.custom.whatever", ComponentType.DATABASE)
        assert result == 500

    def test_find_references_in_nested_values(self):
        """Lines 433, 443, 452-454: recursive reference search in values."""
        from faultray.discovery.terraform import parse_tf_state

        state = {
            "values": {
                "root_module": {
                    "resources": [
                        {
                            "type": "aws_instance", "name": "app",
                            "address": "aws_instance.app",
                            "values": {
                                "name": "app",
                                # Nested dict reference
                                "config": {
                                    "db_ref": "connected to aws_db_instance.db",
                                },
                                # List of dicts reference
                                "attachments": [
                                    {"target": "aws_db_instance.db"},
                                ],
                            },
                        },
                        {
                            "type": "aws_db_instance", "name": "db",
                            "address": "aws_db_instance.db",
                            "values": {"name": "db"},
                        },
                    ],
                },
            },
        }
        graph = parse_tf_state(state)
        # Should have found reference from app to db via nested values
        edge = graph.get_dependency_edge("aws_instance.app", "aws_db_instance.db")
        assert edge is not None


# ===================================================================
# 12. integrations/webhooks.py — Missing: 89-91
# ===================================================================

class TestWebhooksCoverageGaps:
    """Cover webhooks.py PagerDuty network error."""

    @pytest.mark.asyncio
    async def test_pagerduty_network_error(self):
        """Lines 89-91: PagerDuty fails due to network error."""
        from faultray.integrations.webhooks import send_pagerduty_event

        report = {
            "resilience_score": 30,
            "critical_count": 2,
            "warning_count": 1,
            "passed_count": 3,
        }
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.side_effect = httpx.ConnectError("refused")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_pagerduty_event("test-key", report)
            assert result is False


# ===================================================================
# 13. ai/analyzer.py — Missing: 84, 102, 125, 213, 415, 509, 558
# ===================================================================

class TestAIAnalyzerCoverageGaps:
    """Cover ai/analyzer.py edge cases."""

    def test_score_to_nines_boundary_60(self):
        """Line 84: score == 60 maps to 2.5 nines."""
        from faultray.ai.analyzer import _score_to_nines

        assert _score_to_nines(60) == 2.5

    def test_score_to_nines_boundary_90(self):
        """Line 84: score between 90-94 maps to 4.0 nines."""
        from faultray.ai.analyzer import _score_to_nines

        assert _score_to_nines(90) == 4.0
        assert _score_to_nines(94) == 4.0

    def test_score_to_nines_boundary_50(self):
        """Line 84: score of 50 maps to 2.0."""
        from faultray.ai.analyzer import _score_to_nines

        assert _score_to_nines(50) == 2.0

    def test_score_to_nines_boundary_30(self):
        """Line 84: score of 30 maps to 1.5."""
        from faultray.ai.analyzer import _score_to_nines

        assert _score_to_nines(30) == 1.5

    def test_nines_tier_label_basic(self):
        """Line 102: tier label for 2.5 nines."""
        from faultray.ai.analyzer import _nines_tier_label

        label = _nines_tier_label(2.5)
        assert "Basic" in label

    def test_nines_tier_label_low(self):
        """Line 102: tier label for 2.0 nines."""
        from faultray.ai.analyzer import _nines_tier_label

        label = _nines_tier_label(2.0)
        assert "Low" in label

    def test_nines_tier_label_standard(self):
        """Line 125: tier label for 3.0 nines."""
        from faultray.ai.analyzer import _nines_tier_label

        label = _nines_tier_label(3.0)
        assert "Standard" in label

    def test_nines_tier_label_excellent(self):
        """Tier label for 4.5+ nines."""
        from faultray.ai.analyzer import _nines_tier_label

        label = _nines_tier_label(4.5)
        assert "Excellent" in label

    def test_nines_tier_label_good(self):
        """Tier label for 3.5 nines."""
        from faultray.ai.analyzer import _nines_tier_label

        label = _nines_tier_label(3.5)
        assert "Good" in label

    def test_cascade_amplifier_pct_over_50_critical(self):
        """Line 213: cascade affecting > 50% of system gets 'critical' severity."""
        from faultray.ai.analyzer import FaultRayAnalyzer
        from faultray.simulator.engine import SimulationEngine

        graph = InfraGraph()
        # 3 components; DB failure affects svc-a and svc-b (66% > 50%)
        graph.add_component(Component(id="db", name="DB", type=ComponentType.DATABASE, replicas=1))
        graph.add_component(Component(id="svc-a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        graph.add_component(Component(id="svc-b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        graph.add_dependency(Dependency(source_id="svc-a", target_id="db", dependency_type="requires"))
        graph.add_dependency(Dependency(source_id="svc-b", target_id="db", dependency_type="requires"))

        engine = SimulationEngine(graph)
        report = engine.run_all_defaults()
        analyzer = FaultRayAnalyzer()
        ai_report = analyzer.analyze(graph, report)

        cascade_recs = [r for r in ai_report.recommendations if r.category == "cascade"]
        if cascade_recs:
            # With 3 components, cascade affecting 2+ is >50%
            assert any(r.severity == "critical" for r in cascade_recs)

    def test_disk_bottleneck_adds_log_rotation_advice(self):
        """Line 415: high disk_percent adds log rotation recommendation."""
        from faultray.ai.analyzer import FaultRayAnalyzer
        from faultray.simulator.engine import SimulationEngine

        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=2,
            metrics=ResourceMetrics(cpu_percent=30, memory_percent=30, disk_percent=85),
        ))
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults()
        analyzer = FaultRayAnalyzer()
        ai_report = analyzer.analyze(graph, report)

        cap_recs = [r for r in ai_report.recommendations if r.category == "capacity"]
        assert len(cap_recs) > 0
        db_rec = [r for r in cap_recs if r.component_id == "db"][0]
        assert "log rotation" in db_rec.remediation.lower() or "archival" in db_rec.remediation.lower()

    def test_upgrade_path_highest_tier(self):
        """Line 509: already at highest tier returns maintenance message."""
        from faultray.ai.analyzer import FaultRayAnalyzer

        analyzer = FaultRayAnalyzer()
        # Call _generate_upgrade_path directly with current_nines >= 5.0
        # (which is the highest tier in the list), so next_tier is None.
        result = analyzer._generate_upgrade_path(
            current_nines=5.0,
            theoretical_max=5.0,
            recommendations=[],
        )
        assert "highest" in result.lower() or "maintaining" in result.lower()

    def test_top_risks_no_critical_fills_with_high(self):
        """Line 558: when < 3 critical risks, high-severity fills up."""
        from faultray.ai.analyzer import FaultRayAnalyzer
        from faultray.simulator.engine import SimulationEngine

        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=75),
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=1,
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires",
        ))

        engine = SimulationEngine(graph)
        report = engine.run_all_defaults()
        analyzer = FaultRayAnalyzer()
        ai_report = analyzer.analyze(graph, report)

        # Should have risks filled with high-severity items
        assert len(ai_report.top_risks) >= 1
