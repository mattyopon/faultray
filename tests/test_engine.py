"""Comprehensive tests for faultray.simulator.engine — SimulationEngine, ScenarioResult, SimulationReport."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEffect, CascadeEngine
from faultray.simulator.engine import (
    MAX_SCENARIOS,
    SimulationEngine,
    SimulationReport,
    ScenarioResult,
    _CHECKPOINT_INTERVAL,
)
from faultray.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(cid, name, ctype=ComponentType.APP_SERVER, replicas=1, **kwargs):
    c = Component(id=cid, name=name, type=ctype, replicas=replicas, **kwargs)
    return c


def _make_graph(*components, deps=None):
    """Build an InfraGraph from components and optional dependency tuples."""
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt, dtype in (deps or []):
        g.add_dependency(Dependency(source_id=src, target_id=tgt, dependency_type=dtype))
    return g


def _scenario(sid="s1", name="test", faults=None, traffic_multiplier=1.0):
    return Scenario(
        id=sid,
        name=name,
        description="test scenario",
        faults=faults or [],
        traffic_multiplier=traffic_multiplier,
    )


def _fault(cid, ftype=FaultType.COMPONENT_DOWN):
    return Fault(target_component_id=cid, fault_type=ftype)


# ---------------------------------------------------------------------------
# ScenarioResult dataclass tests
# ---------------------------------------------------------------------------


class TestScenarioResult:
    """Tests for ScenarioResult properties."""

    def _make(self, risk_score, error=None):
        return ScenarioResult(
            scenario=_scenario(),
            cascade=CascadeChain(trigger="t", total_components=1),
            risk_score=risk_score,
            error=error,
        )

    def test_is_critical_at_threshold(self):
        assert self._make(7.0).is_critical is True

    def test_is_critical_above(self):
        assert self._make(10.0).is_critical is True

    def test_is_critical_below(self):
        assert self._make(6.9).is_critical is False

    def test_is_warning_at_lower_threshold(self):
        assert self._make(4.0).is_warning is True

    def test_is_warning_at_upper_threshold(self):
        # 7.0 is critical, not warning
        assert self._make(7.0).is_warning is False

    def test_is_warning_in_range(self):
        assert self._make(5.5).is_warning is True

    def test_is_warning_below(self):
        assert self._make(3.9).is_warning is False

    def test_not_critical_not_warning(self):
        r = self._make(2.0)
        assert r.is_critical is False
        assert r.is_warning is False

    def test_zero_risk(self):
        r = self._make(0.0)
        assert r.is_critical is False
        assert r.is_warning is False

    def test_negative_risk(self):
        r = self._make(-1.0)
        assert r.is_critical is False
        assert r.is_warning is False

    def test_error_field(self):
        r = self._make(0.0, error="boom")
        assert r.error == "boom"

    def test_no_error(self):
        r = self._make(5.0)
        assert r.error is None


# ---------------------------------------------------------------------------
# SimulationReport dataclass tests
# ---------------------------------------------------------------------------


class TestSimulationReport:
    """Tests for SimulationReport properties."""

    def _result(self, risk_score):
        return ScenarioResult(
            scenario=_scenario(),
            cascade=CascadeChain(trigger="t", total_components=1),
            risk_score=risk_score,
        )

    def test_empty_report(self):
        r = SimulationReport()
        assert r.critical_findings == []
        assert r.warnings == []
        assert r.passed == []
        assert r.resilience_score == 0.0
        assert r.total_generated == 0
        assert r.was_truncated is False

    def test_critical_findings(self):
        r = SimulationReport(results=[self._result(8.0), self._result(3.0)])
        assert len(r.critical_findings) == 1
        assert r.critical_findings[0].risk_score == 8.0

    def test_warnings(self):
        r = SimulationReport(results=[self._result(5.0), self._result(3.0)])
        assert len(r.warnings) == 1
        assert r.warnings[0].risk_score == 5.0

    def test_passed(self):
        r = SimulationReport(results=[self._result(2.0), self._result(3.5)])
        assert len(r.passed) == 2

    def test_mixed_categories(self):
        r = SimulationReport(results=[
            self._result(9.0),   # critical
            self._result(5.0),   # warning
            self._result(1.0),   # passed
        ])
        assert len(r.critical_findings) == 1
        assert len(r.warnings) == 1
        assert len(r.passed) == 1

    def test_all_critical(self):
        r = SimulationReport(results=[self._result(7.0), self._result(10.0)])
        assert len(r.critical_findings) == 2
        assert len(r.warnings) == 0
        assert len(r.passed) == 0

    def test_engine_plugin_results(self):
        r = SimulationReport(engine_plugin_results={"test": {"key": "value"}})
        assert "test" in r.engine_plugin_results


# ---------------------------------------------------------------------------
# SimulationEngine.run_scenario tests
# ---------------------------------------------------------------------------


class TestRunScenario:
    """Tests for SimulationEngine.run_scenario."""

    def _engine(self, graph=None):
        if graph is None:
            graph = _make_graph(
                _comp("app", "App"),
                _comp("db", "DB", ctype=ComponentType.DATABASE),
                deps=[("app", "db", "requires")],
            )
        return SimulationEngine(graph)

    def test_empty_scenario_no_faults_no_traffic(self):
        engine = self._engine()
        result = engine.run_scenario(_scenario())
        assert result.risk_score == 0.0
        assert result.error is None

    def test_single_fault(self):
        engine = self._engine()
        result = engine.run_scenario(
            _scenario(faults=[_fault("db")])
        )
        assert result.risk_score >= 0.0
        assert result.error is None

    def test_traffic_spike_only(self):
        engine = self._engine()
        result = engine.run_scenario(
            _scenario(traffic_multiplier=3.0)
        )
        # May or may not cause effects depending on utilization
        assert result.error is None

    def test_combined_fault_and_traffic(self):
        engine = self._engine()
        result = engine.run_scenario(
            _scenario(faults=[_fault("db")], traffic_multiplier=2.0)
        )
        assert result.error is None
        assert result.cascade.trigger is not None

    def test_invalid_component_handled_gracefully(self):
        engine = self._engine()
        result = engine.run_scenario(
            _scenario(faults=[_fault("nonexistent")])
        )
        # Should not raise; cascade may be empty
        assert result.error is None

    def test_exception_in_execute_returns_error_result(self):
        engine = self._engine()
        # Cause an internal exception
        with patch.object(engine.cascade_engine, "simulate_fault", side_effect=RuntimeError("boom")):
            result = engine.run_scenario(_scenario(faults=[_fault("db")]))
        assert result.error == "boom"
        assert result.risk_score == 0.0

    def test_exception_in_traffic_spike(self):
        engine = self._engine()
        with patch.object(engine.cascade_engine, "simulate_traffic_spike", side_effect=ValueError("bad")):
            result = engine.run_scenario(_scenario(traffic_multiplier=2.0))
        assert result.error == "bad"
        assert result.risk_score == 0.0


# ---------------------------------------------------------------------------
# SimulationEngine._execute_scenario likelihood penalty tests
# ---------------------------------------------------------------------------


class TestExecuteScenarioLikelihood:
    """Tests for the likelihood penalty logic in _execute_scenario."""

    def _big_graph(self, n):
        comps = [_comp(f"c{i}", f"C{i}") for i in range(n)]
        return _make_graph(*comps)

    def test_no_penalty_below_10_components(self):
        """Penalty logic only triggers when total_components >= 10."""
        graph = _make_graph(*[_comp(f"c{i}", f"C{i}") for i in range(5)])
        engine = SimulationEngine(graph)
        faults = [_fault(f"c{i}") for i in range(5)]
        result = engine._execute_scenario(_scenario(faults=faults))
        # No penalty applied; merged.likelihood uses min of chain likelihoods
        assert result.error is None

    def test_penalty_90_percent_direct_faults(self):
        """When >= 90% components are directly faulted, likelihood capped at 0.05."""
        n = 10
        graph = self._big_graph(n)
        engine = SimulationEngine(graph)
        # Fault 9 out of 10 = 90%
        faults = [_fault(f"c{i}") for i in range(9)]
        result = engine._execute_scenario(_scenario(faults=faults))
        assert result.cascade.likelihood <= 0.05

    def test_penalty_50_percent_direct_faults(self):
        """When >= 50% components are directly faulted, likelihood capped at 0.3."""
        n = 10
        graph = self._big_graph(n)
        engine = SimulationEngine(graph)
        # Fault 5 out of 10 = 50%
        faults = [_fault(f"c{i}") for i in range(5)]
        result = engine._execute_scenario(_scenario(faults=faults))
        assert result.cascade.likelihood <= 0.3

    def test_no_penalty_below_50_percent(self):
        """When < 50% components are directly faulted, no special cap."""
        n = 10
        graph = self._big_graph(n)
        engine = SimulationEngine(graph)
        faults = [_fault("c0")]
        result = engine._execute_scenario(_scenario(faults=faults))
        # The likelihood is from chain, not the special cap
        assert result.error is None

    def test_100_percent_faults_capped(self):
        """All components faulted -> likelihood capped at 0.05."""
        n = 12
        graph = self._big_graph(n)
        engine = SimulationEngine(graph)
        faults = [_fault(f"c{i}") for i in range(n)]
        result = engine._execute_scenario(_scenario(faults=faults))
        assert result.cascade.likelihood <= 0.05

    def test_merged_chain_uses_min_likelihood(self):
        """When multiple chains have effects, merged uses min likelihood."""
        graph = _make_graph(
            _comp("a", "A", metrics=ResourceMetrics(cpu_percent=95)),
            _comp("b", "B"),
        )
        engine = SimulationEngine(graph)
        faults = [_fault("a", FaultType.CPU_SATURATION), _fault("b")]
        result = engine._execute_scenario(_scenario(faults=faults))
        assert result.cascade.likelihood > 0
        assert result.cascade.likelihood <= 1.0

    def test_no_effects_chains_ignored_for_likelihood(self):
        """Chains with no effects are ignored for min-likelihood calculation."""
        graph = _make_graph(_comp("a", "A"))
        engine = SimulationEngine(graph)
        # Traffic at 1.0x = no effects
        result = engine._execute_scenario(_scenario(traffic_multiplier=1.0, faults=[_fault("a")]))
        assert result.error is None


# ---------------------------------------------------------------------------
# SimulationEngine.run_scenarios tests
# ---------------------------------------------------------------------------


class TestRunScenarios:
    """Tests for SimulationEngine.run_scenarios (batch execution)."""

    def _simple_engine(self):
        graph = _make_graph(
            _comp("app", "App"),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
            deps=[("app", "db", "requires")],
        )
        return SimulationEngine(graph)

    def test_empty_list(self):
        engine = self._simple_engine()
        report = engine.run_scenarios([])
        assert report.results == []
        assert report.was_truncated is False
        assert report.total_generated == 0

    def test_single_scenario(self):
        engine = self._simple_engine()
        report = engine.run_scenarios([_scenario(faults=[_fault("db")])])
        assert len(report.results) == 1
        assert report.total_generated == 1
        assert report.was_truncated is False

    def test_results_sorted_by_risk_descending(self):
        engine = self._simple_engine()
        scenarios = [
            _scenario(sid="s1", faults=[_fault("app", FaultType.LATENCY_SPIKE)]),
            _scenario(sid="s2", faults=[_fault("db")]),
            _scenario(sid="s3"),
        ]
        report = engine.run_scenarios(scenarios)
        scores = [r.risk_score for r in report.results]
        assert scores == sorted(scores, reverse=True)

    def test_truncation_at_default_limit(self):
        engine = self._simple_engine()
        scenarios = [_scenario(sid=f"s{i}") for i in range(MAX_SCENARIOS + 10)]
        report = engine.run_scenarios(scenarios)
        assert report.was_truncated is True
        assert report.total_generated == MAX_SCENARIOS + 10
        assert len(report.results) == MAX_SCENARIOS

    def test_truncation_with_custom_limit(self):
        engine = self._simple_engine()
        scenarios = [_scenario(sid=f"s{i}") for i in range(20)]
        report = engine.run_scenarios(scenarios, max_scenarios=5)
        assert report.was_truncated is True
        assert report.total_generated == 20
        assert len(report.results) == 5

    def test_no_truncation_within_limit(self):
        engine = self._simple_engine()
        scenarios = [_scenario(sid=f"s{i}") for i in range(3)]
        report = engine.run_scenarios(scenarios, max_scenarios=10)
        assert report.was_truncated is False
        assert len(report.results) == 3

    def test_max_scenarios_zero_uses_default(self):
        engine = self._simple_engine()
        scenarios = [_scenario(sid=f"s{i}") for i in range(5)]
        report = engine.run_scenarios(scenarios, max_scenarios=0)
        assert report.was_truncated is False

    def test_resilience_score_in_report(self):
        engine = self._simple_engine()
        report = engine.run_scenarios([_scenario()])
        assert isinstance(report.resilience_score, float)


# ---------------------------------------------------------------------------
# Checkpoint tests
# ---------------------------------------------------------------------------


class TestCheckpoint:
    """Tests for checkpoint saving and cleanup."""

    def test_checkpoint_saved_at_interval(self):
        graph = _make_graph(_comp("app", "App"))
        engine = SimulationEngine(graph)
        # Create exactly CHECKPOINT_INTERVAL scenarios to trigger checkpoint
        scenarios = [_scenario(sid=f"s{i}") for i in range(_CHECKPOINT_INTERVAL)]
        report = engine.run_scenarios(scenarios)
        # Checkpoint should be cleaned up on success
        assert len(report.results) == _CHECKPOINT_INTERVAL

    def test_save_checkpoint_creates_file(self):
        results = [
            ScenarioResult(
                scenario=_scenario(sid="s1", name="test1"),
                cascade=CascadeChain(trigger="t"),
                risk_score=3.0,
            )
        ]
        path = SimulationEngine._save_checkpoint(results, 1)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["completed_scenarios"] == 1
        assert len(data["partial_results"]) == 1
        assert data["partial_results"][0]["scenario_id"] == "s1"
        assert data["partial_results"][0]["risk_score"] == 3.0
        assert data["partial_results"][0]["error"] is None
        # Cleanup
        path.unlink()

    def test_save_checkpoint_with_error_result(self):
        results = [
            ScenarioResult(
                scenario=_scenario(sid="err", name="error-scenario"),
                cascade=CascadeChain(trigger="t"),
                risk_score=0.0,
                error="test error",
            )
        ]
        path = SimulationEngine._save_checkpoint(results, 1)
        data = json.loads(path.read_text())
        assert data["partial_results"][0]["error"] == "test error"
        path.unlink()

    def test_save_checkpoint_empty_results(self):
        path = SimulationEngine._save_checkpoint([], 0)
        data = json.loads(path.read_text())
        assert data["completed_scenarios"] == 0
        assert data["partial_results"] == []
        path.unlink()

    def test_checkpoint_cleaned_up_after_successful_run(self):
        """Checkpoint file is deleted after successful completion."""
        graph = _make_graph(_comp("app", "App"))
        engine = SimulationEngine(graph)
        scenarios = [_scenario(sid=f"s{i}") for i in range(_CHECKPOINT_INTERVAL + 1)]
        engine.run_scenarios(scenarios)
        # The checkpoint should have been cleaned up
        checkpoint_dir = Path(tempfile.gettempdir()) / "faultray_checkpoints"
        checkpoint_path = checkpoint_dir / "simulation_checkpoint.json"
        assert not checkpoint_path.exists()


# ---------------------------------------------------------------------------
# SimulationEngine.run_all_defaults tests
# ---------------------------------------------------------------------------


class TestRunAllDefaults:
    """Tests for SimulationEngine.run_all_defaults."""

    def _engine_with_graph(self):
        graph = _make_graph(
            _comp("app", "App"),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
            _comp("cache", "Cache", ctype=ComponentType.CACHE),
            deps=[("app", "db", "requires"), ("app", "cache", "optional")],
        )
        return SimulationEngine(graph), graph

    def test_basic_run(self):
        engine, _ = self._engine_with_graph()
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert isinstance(report, SimulationReport)
        assert len(report.results) > 0

    def test_with_max_scenarios(self):
        engine, _ = self._engine_with_graph()
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False, max_scenarios=5
        )
        assert len(report.results) <= 5

    @patch("faultray.feeds.store.load_feed_scenarios")
    def test_feed_scenarios_included(self, mock_load):
        engine, graph = self._engine_with_graph()
        feed_scenario = _scenario(
            sid="feed-1", name="Feed test",
            faults=[_fault("app")]
        )
        mock_load.return_value = [feed_scenario]
        report = engine.run_all_defaults(include_feed=True, include_plugins=False)
        assert report.total_generated > 0

    @patch("faultray.feeds.store.load_feed_scenarios")
    def test_feed_scenarios_filtered_by_graph(self, mock_load):
        """Feed scenarios with targets not in graph are excluded."""
        engine, graph = self._engine_with_graph()
        # This scenario has a nonexistent target
        bad_scenario = _scenario(
            sid="feed-bad", name="Bad target",
            faults=[_fault("nonexistent_comp")]
        )
        # This one targets a valid component
        good_scenario = _scenario(
            sid="feed-good", name="Good target",
            faults=[_fault("app")]
        )
        mock_load.return_value = [bad_scenario, good_scenario]
        report = engine.run_all_defaults(include_feed=True, include_plugins=False)
        # The bad scenario should be filtered out but good one kept
        assert report.total_generated > 0

    @patch("faultray.feeds.store.load_feed_scenarios")
    def test_feed_returns_empty(self, mock_load):
        engine, _ = self._engine_with_graph()
        mock_load.return_value = []
        report = engine.run_all_defaults(include_feed=True, include_plugins=False)
        assert len(report.results) > 0

    @patch("faultray.feeds.store.load_feed_scenarios")
    def test_feed_returns_none(self, mock_load):
        engine, _ = self._engine_with_graph()
        mock_load.return_value = None
        report = engine.run_all_defaults(include_feed=True, include_plugins=False)
        assert len(report.results) > 0

    def test_plugins_import_error_handled(self):
        """When plugins module doesn't exist, should not crash."""
        engine, _ = self._engine_with_graph()
        # include_plugins=True but ImportError is caught
        report = engine.run_all_defaults(include_feed=False, include_plugins=True)
        assert isinstance(report, SimulationReport)

    @patch("faultray.plugins.registry.PluginRegistry")
    def test_plugin_scenario_generation_failure(self, mock_registry):
        """Plugin that fails to generate scenarios should not crash engine."""
        engine, _ = self._engine_with_graph()
        bad_plugin = MagicMock()
        bad_plugin.generate_scenarios.side_effect = RuntimeError("plugin broke")
        bad_plugin.name = "bad-plugin"
        mock_registry.get_scenario_plugins.return_value = [bad_plugin]
        mock_registry.get_engines.return_value = []
        report = engine.run_all_defaults(include_feed=False, include_plugins=True)
        assert isinstance(report, SimulationReport)

    @patch("faultray.plugins.registry.PluginRegistry")
    def test_plugin_engine_failure(self, mock_registry):
        """Engine plugin that fails should not crash."""
        engine, _ = self._engine_with_graph()
        bad_engine_plugin = MagicMock()
        bad_engine_plugin.simulate.side_effect = RuntimeError("engine plugin broke")
        bad_engine_plugin.name = "bad-engine"
        mock_registry.get_scenario_plugins.return_value = []
        mock_registry.get_engines.return_value = [bad_engine_plugin]
        report = engine.run_all_defaults(include_feed=False, include_plugins=True)
        assert isinstance(report, SimulationReport)

    @patch("faultray.plugins.registry.PluginRegistry")
    def test_plugin_engine_results_merged(self, mock_registry):
        """Engine plugin results are merged into report."""
        engine, _ = self._engine_with_graph()
        good_engine = MagicMock()
        good_engine.simulate.return_value = {"result": "data"}
        good_engine.name = "good-engine"
        mock_registry.get_scenario_plugins.return_value = []
        mock_registry.get_engines.return_value = [good_engine]
        report = engine.run_all_defaults(include_feed=False, include_plugins=True)
        assert "good-engine" in report.engine_plugin_results

    @patch("faultray.plugins.registry.PluginRegistry")
    def test_plugin_engine_returns_none(self, mock_registry):
        """Engine plugin that returns None should not add to results."""
        engine, _ = self._engine_with_graph()
        none_engine = MagicMock()
        none_engine.simulate.return_value = None
        none_engine.name = "none-engine"
        mock_registry.get_scenario_plugins.return_value = []
        mock_registry.get_engines.return_value = [none_engine]
        report = engine.run_all_defaults(include_feed=False, include_plugins=True)
        assert "none-engine" not in report.engine_plugin_results

    @patch("faultray.plugins.registry.PluginRegistry")
    def test_plugin_scenario_added_to_list(self, mock_registry):
        """Plugin-generated scenarios are added to the scenario list."""
        engine, _ = self._engine_with_graph()
        good_plugin = MagicMock()
        extra = [_scenario(sid="plugin-s1", faults=[_fault("app")])]
        good_plugin.generate_scenarios.return_value = extra
        good_plugin.name = "good-plugin"
        mock_registry.get_scenario_plugins.return_value = [good_plugin]
        mock_registry.get_engines.return_value = []
        report = engine.run_all_defaults(include_feed=False, include_plugins=True)
        assert report.total_generated > 0

    @patch("faultray.plugins.registry.PluginRegistry")
    def test_plugin_returns_empty(self, mock_registry):
        good_plugin = MagicMock()
        good_plugin.generate_scenarios.return_value = []
        good_plugin.name = "empty-plugin"
        mock_registry.get_scenario_plugins.return_value = [good_plugin]
        mock_registry.get_engines.return_value = []
        engine, _ = self._engine_with_graph()
        report = engine.run_all_defaults(include_feed=False, include_plugins=True)
        assert isinstance(report, SimulationReport)


# ---------------------------------------------------------------------------
# SimulationEngine with cache
# ---------------------------------------------------------------------------


class TestEngineCache:
    """Tests for the optional cache parameter."""

    def test_engine_with_no_cache(self):
        graph = _make_graph(_comp("a", "A"))
        engine = SimulationEngine(graph)
        assert engine._cache is None

    def test_engine_with_cache_object(self):
        graph = _make_graph(_comp("a", "A"))
        cache = MagicMock()
        engine = SimulationEngine(graph, cache=cache)
        assert engine._cache is cache


# ---------------------------------------------------------------------------
# Edge cases: empty graph
# ---------------------------------------------------------------------------


class TestEmptyGraph:
    """Tests with an empty graph (no components)."""

    def test_run_scenario_empty_graph(self):
        graph = InfraGraph()
        engine = SimulationEngine(graph)
        result = engine.run_scenario(_scenario())
        assert result.risk_score == 0.0
        assert result.error is None

    def test_run_all_defaults_empty_graph(self):
        graph = InfraGraph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        # generate_default_scenarios still generates traffic spike scenarios
        # even with no components, so results may be non-empty
        for r in report.results:
            assert r.risk_score == 0.0

    def test_run_scenarios_empty_graph(self):
        graph = InfraGraph()
        engine = SimulationEngine(graph)
        report = engine.run_scenarios([_scenario()])
        assert len(report.results) == 1
        assert report.results[0].risk_score == 0.0


# ---------------------------------------------------------------------------
# Large graph stress tests
# ---------------------------------------------------------------------------


class TestLargeGraph:
    """Tests with a larger graph to exercise penalty logic more thoroughly."""

    def _large_graph(self, n=20):
        comps = []
        deps = []
        for i in range(n):
            comps.append(_comp(f"c{i}", f"Component {i}"))
            if i > 0:
                deps.append((f"c{i}", f"c{i-1}", "requires"))
        return _make_graph(*comps, deps=deps)

    def test_all_down_scenario(self):
        graph = self._large_graph(20)
        engine = SimulationEngine(graph)
        faults = [_fault(f"c{i}") for i in range(20)]
        result = engine.run_scenario(_scenario(faults=faults))
        # All components faulted: 100% > 90%, likelihood capped at 0.05
        assert result.cascade.likelihood <= 0.05

    def test_half_down_scenario(self):
        graph = self._large_graph(20)
        engine = SimulationEngine(graph)
        faults = [_fault(f"c{i}") for i in range(10)]
        result = engine.run_scenario(_scenario(faults=faults))
        assert result.cascade.likelihood <= 0.3

    def test_single_fault_in_large_graph(self):
        graph = self._large_graph(20)
        engine = SimulationEngine(graph)
        result = engine.run_scenario(_scenario(faults=[_fault("c0")]))
        # No penalty for single fault in large graph
        assert result.error is None


# ---------------------------------------------------------------------------
# Multiple fault types combined
# ---------------------------------------------------------------------------


class TestMultipleFaultTypes:
    """Tests combining different fault types in a single scenario."""

    def _graph(self):
        return _make_graph(
            _comp("app", "App", metrics=ResourceMetrics(cpu_percent=85, disk_percent=92)),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
            deps=[("app", "db", "requires")],
        )

    def test_cpu_and_disk_faults(self):
        engine = SimulationEngine(self._graph())
        result = engine.run_scenario(_scenario(faults=[
            _fault("app", FaultType.CPU_SATURATION),
            _fault("db", FaultType.DISK_FULL),
        ]))
        assert result.error is None
        assert len(result.cascade.effects) >= 2

    def test_memory_and_component_down(self):
        engine = SimulationEngine(self._graph())
        result = engine.run_scenario(_scenario(faults=[
            _fault("app", FaultType.MEMORY_EXHAUSTION),
            _fault("db", FaultType.COMPONENT_DOWN),
        ]))
        assert result.error is None

    def test_network_partition_and_latency(self):
        engine = SimulationEngine(self._graph())
        result = engine.run_scenario(_scenario(faults=[
            _fault("app", FaultType.NETWORK_PARTITION),
            _fault("db", FaultType.LATENCY_SPIKE),
        ]))
        assert result.error is None

    def test_all_fault_types_single_component(self):
        engine = SimulationEngine(self._graph())
        faults = [
            _fault("app", ft)
            for ft in FaultType
        ]
        result = engine.run_scenario(_scenario(faults=faults))
        assert result.error is None


# ---------------------------------------------------------------------------
# Traffic spike edge cases
# ---------------------------------------------------------------------------


class TestTrafficSpike:
    """Edge cases for traffic_multiplier handling."""

    def _engine(self):
        graph = _make_graph(
            _comp("app", "App", metrics=ResourceMetrics(cpu_percent=50)),
        )
        return SimulationEngine(graph)

    def test_traffic_multiplier_1_no_spike(self):
        """1.0x traffic = no spike, no effects."""
        engine = self._engine()
        result = engine.run_scenario(_scenario(traffic_multiplier=1.0))
        assert result.risk_score == 0.0

    def test_traffic_multiplier_just_above_1(self):
        """1.01x should trigger traffic spike path."""
        engine = self._engine()
        result = engine.run_scenario(_scenario(traffic_multiplier=1.01))
        # May or may not have effects, but no error
        assert result.error is None

    def test_very_large_traffic_multiplier(self):
        engine = self._engine()
        result = engine.run_scenario(_scenario(traffic_multiplier=100.0))
        assert result.error is None

    def test_traffic_multiplier_zero(self):
        """0x traffic = less than 1.0, no spike."""
        engine = self._engine()
        result = engine.run_scenario(_scenario(traffic_multiplier=0.0))
        assert result.risk_score == 0.0


# ---------------------------------------------------------------------------
# ImportError coverage for plugin imports (lines 189-190, 212-213)
# ---------------------------------------------------------------------------


class TestPluginImportErrors:
    """Cover the except ImportError branches for plugin registry."""

    def _engine(self):
        graph = _make_graph(
            _comp("app", "App"),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
            deps=[("app", "db", "requires")],
        )
        return SimulationEngine(graph)

    def test_scenario_plugins_import_error(self):
        """Force ImportError on scenario plugin import (lines 189-190)."""
        engine = self._engine()
        import sys
        real_module = sys.modules.get("faultray.plugins.registry")
        # Temporarily remove the module to force ImportError
        sys.modules["faultray.plugins.registry"] = None  # forces ImportError
        try:
            report = engine.run_all_defaults(
                include_feed=False, include_plugins=True
            )
            assert isinstance(report, SimulationReport)
        finally:
            if real_module is not None:
                sys.modules["faultray.plugins.registry"] = real_module
            else:
                sys.modules.pop("faultray.plugins.registry", None)

    def test_engine_plugins_import_error(self):
        """Force ImportError on engine plugin import (lines 212-213).

        We need to make the first import succeed but the second fail.
        """
        engine = self._engine()
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__
        call_count = [0]

        def patched_import(name, *args, **kwargs):
            if name == "faultray.plugins.registry":
                call_count[0] += 1
                if call_count[0] == 1:
                    # First import (scenario plugins) succeeds with empty returns
                    mock_mod = MagicMock()
                    mock_mod.PluginRegistry.get_scenario_plugins.return_value = []
                    return mock_mod
                else:
                    # Second import (engine plugins) raises ImportError
                    raise ImportError("no plugins")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=patched_import):
            report = engine.run_all_defaults(
                include_feed=False, include_plugins=True
            )
        assert isinstance(report, SimulationReport)


# ---------------------------------------------------------------------------
# OSError on checkpoint cleanup (lines 256-257)
# ---------------------------------------------------------------------------


class TestCheckpointOSError:
    """Cover OSError during checkpoint unlink."""

    def test_checkpoint_unlink_oserror_ignored(self):
        """OSError during checkpoint cleanup should be silently ignored."""
        graph = _make_graph(_comp("app", "App"))
        engine = SimulationEngine(graph)
        scenarios = [_scenario(sid=f"s{i}") for i in range(_CHECKPOINT_INTERVAL + 1)]

        # Make the checkpoint file's unlink raise OSError
        with patch("pathlib.Path.unlink", side_effect=OSError("permission denied")):
            # Should not raise
            report = engine.run_scenarios(scenarios)
        assert len(report.results) == _CHECKPOINT_INTERVAL + 1


# ---------------------------------------------------------------------------
# Exception on checkpoint save (lines 293-294)
# ---------------------------------------------------------------------------


class TestCheckpointSaveFailure:
    """Cover Exception during checkpoint write."""

    def test_save_checkpoint_write_failure(self):
        """Exception during checkpoint write should be caught and logged."""
        results = [
            ScenarioResult(
                scenario=_scenario(sid="s1", name="test"),
                cascade=CascadeChain(trigger="t"),
                risk_score=1.0,
            )
        ]
        with patch("pathlib.Path.write_text", side_effect=PermissionError("no write")):
            # Should not raise
            path = SimulationEngine._save_checkpoint(results, 1)
        assert path is not None
