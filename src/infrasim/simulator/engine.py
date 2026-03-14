"""Simulation engine - orchestrates scenario execution."""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from infrasim.model.graph import InfraGraph
from infrasim.simulator.cascade import CascadeChain, CascadeEngine
from infrasim.simulator.scenarios import Scenario, generate_default_scenarios

logger = logging.getLogger(__name__)

MAX_SCENARIOS = 2000

# Checkpoint interval: save partial results every N scenarios
_CHECKPOINT_INTERVAL = 100


@dataclass
class ScenarioResult:
    """Result of running a single scenario."""

    scenario: Scenario
    cascade: CascadeChain
    risk_score: float = 0.0
    error: str | None = None

    @property
    def is_critical(self) -> bool:
        return self.risk_score >= 7.0

    @property
    def is_warning(self) -> bool:
        return 4.0 <= self.risk_score < 7.0


@dataclass
class SimulationReport:
    """Complete simulation report."""

    results: list[ScenarioResult] = field(default_factory=list)
    resilience_score: float = 0.0
    total_generated: int = 0
    was_truncated: bool = False
    engine_plugin_results: dict[str, dict] = field(default_factory=dict)

    @property
    def critical_findings(self) -> list[ScenarioResult]:
        return [r for r in self.results if r.is_critical]

    @property
    def warnings(self) -> list[ScenarioResult]:
        return [r for r in self.results if r.is_warning]

    @property
    def passed(self) -> list[ScenarioResult]:
        return [r for r in self.results if not r.is_critical and not r.is_warning]


class SimulationEngine:
    """Runs chaos scenarios against an InfraGraph."""

    def __init__(self, graph: InfraGraph, cache=None) -> None:
        self.graph = graph
        self.cascade_engine = CascadeEngine(graph)
        self._cache = cache  # Optional ResultCache instance

    def run_scenario(self, scenario: Scenario) -> ScenarioResult:
        """Run a single chaos scenario with graceful error handling."""
        try:
            return self._execute_scenario(scenario)
        except Exception as e:
            logger.warning("Scenario %s failed: %s", scenario.id, e)
            total_components = len(self.graph.components)
            return ScenarioResult(
                scenario=scenario,
                cascade=CascadeChain(
                    trigger=scenario.name,
                    total_components=total_components,
                ),
                risk_score=0.0,
                error=str(e),
            )

    def _execute_scenario(self, scenario: Scenario) -> ScenarioResult:
        """Internal scenario execution logic."""
        chains: list[CascadeChain] = []
        total_components = len(self.graph.components)

        # Handle traffic spike scenarios
        if scenario.traffic_multiplier > 1.0:
            chain = self.cascade_engine.simulate_traffic_spike(scenario.traffic_multiplier)
            chains.append(chain)

        # Handle fault injection scenarios
        for fault in scenario.faults:
            chain = self.cascade_engine.simulate_fault(fault)
            chains.append(chain)

        # Merge chains with proper total_components context
        if chains:
            merged = CascadeChain(
                trigger=scenario.name,
                total_components=total_components,
            )
            # Use the minimum likelihood from all chains (compound failures
            # are only as likely as the least likely sub-fault)
            likelihoods = [c.likelihood for c in chains if c.effects]
            if likelihoods:
                merged.likelihood = min(likelihoods)

            # Apply a steep likelihood penalty when a scenario directly faults
            # a very high fraction of components.  Simultaneous all-down events
            # are extremely unrealistic; the cascade engine should determine
            # real spread from a small number of root causes instead.
            if total_components >= 10:
                directly_faulted = len(scenario.faults)
                direct_ratio = directly_faulted / total_components
                if direct_ratio >= 0.9:
                    merged.likelihood = min(merged.likelihood, 0.05)
                elif direct_ratio >= 0.5:
                    merged.likelihood = min(merged.likelihood, 0.3)

            for chain in chains:
                merged.effects.extend(chain.effects)
            risk_score = merged.severity
        else:
            merged = CascadeChain(
                trigger=scenario.name,
                total_components=total_components,
            )
            risk_score = 0.0

        return ScenarioResult(
            scenario=scenario,
            cascade=merged,
            risk_score=risk_score,
        )

    def run_all_defaults(
        self, include_feed: bool = True, include_plugins: bool = True,
        max_scenarios: int = 0,
    ) -> SimulationReport:
        """Run all default scenarios plus feed-generated and plugin scenarios."""
        component_ids = list(self.graph.components.keys())
        scenarios = generate_default_scenarios(
            component_ids, components=self.graph.components
        )

        if include_feed:
            from infrasim.feeds.store import load_feed_scenarios

            feed_scenarios = load_feed_scenarios()
            if feed_scenarios:
                # Filter to only scenarios whose targets exist in this graph
                valid = []
                for s in feed_scenarios:
                    valid_faults = [
                        f for f in s.faults
                        if f.target_component_id in self.graph.components
                    ]
                    if valid_faults:
                        s.faults = valid_faults
                        valid.append(s)
                scenarios.extend(valid)

        # Plugin-generated scenarios
        if include_plugins:
            try:
                from infrasim.plugins.registry import PluginRegistry

                for plugin in PluginRegistry.get_scenario_plugins():
                    try:
                        extra = plugin.generate_scenarios(
                            self.graph, component_ids, self.graph.components,
                        )
                        if extra:
                            scenarios.extend(extra)
                    except Exception:
                        logger.warning(
                            "Plugin %s failed to generate scenarios",
                            getattr(plugin, "name", "unknown"),
                            exc_info=True,
                        )
            except ImportError:
                pass

        report = self.run_scenarios(scenarios, max_scenarios=max_scenarios)

        # Run registered engine plugins and merge their results
        if include_plugins:
            try:
                from infrasim.plugins.registry import PluginRegistry

                for plugin in PluginRegistry.get_engines():
                    try:
                        plugin_results = plugin.simulate(self.graph, scenarios)
                        if plugin_results:
                            report.engine_plugin_results[
                                getattr(plugin, "name", "unknown")
                            ] = plugin_results
                    except Exception:
                        logger.warning(
                            "Engine plugin %s failed",
                            getattr(plugin, "name", "unknown"),
                            exc_info=True,
                        )
            except ImportError:
                pass

        return report

    def run_scenarios(
        self, scenarios: list[Scenario], max_scenarios: int = 0,
    ) -> SimulationReport:
        """Run a list of scenarios and generate a report.

        Parameters
        ----------
        scenarios:
            The scenarios to execute.
        max_scenarios:
            Override the truncation limit.  ``0`` means use the module-level
            ``MAX_SCENARIOS`` default.
        """
        limit = max_scenarios if max_scenarios > 0 else MAX_SCENARIOS
        total_generated = len(scenarios)
        was_truncated = total_generated > limit

        if was_truncated:
            logger.warning(
                "Scenario count %d exceeds limit, truncating to %d",
                total_generated,
                limit,
            )
            scenarios = scenarios[:limit]

        results = []
        checkpoint_path: Path | None = None
        for idx, scenario in enumerate(scenarios):
            result = self.run_scenario(scenario)
            results.append(result)

            # Checkpoint: save partial results every _CHECKPOINT_INTERVAL scenarios
            if (idx + 1) % _CHECKPOINT_INTERVAL == 0:
                checkpoint_path = self._save_checkpoint(results, idx + 1)

        # Clean up checkpoint file on successful completion
        if checkpoint_path and checkpoint_path.exists():
            try:
                checkpoint_path.unlink()
            except OSError:
                pass

        # Sort by risk score descending
        results.sort(key=lambda r: r.risk_score, reverse=True)

        return SimulationReport(
            results=results,
            resilience_score=self.graph.resilience_score(),
            total_generated=total_generated,
            was_truncated=was_truncated,
        )

    @staticmethod
    def _save_checkpoint(results: list[ScenarioResult], count: int) -> Path:
        """Save partial simulation results to a temporary checkpoint file."""
        checkpoint_dir = Path(tempfile.gettempdir()) / "chaosproof_checkpoints"
        checkpoint_dir.mkdir(exist_ok=True)
        checkpoint_path = checkpoint_dir / "simulation_checkpoint.json"

        try:
            data = {
                "completed_scenarios": count,
                "partial_results": [
                    {
                        "scenario_id": r.scenario.id,
                        "scenario_name": r.scenario.name,
                        "risk_score": r.risk_score,
                        "error": r.error,
                    }
                    for r in results
                ],
            }
            checkpoint_path.write_text(json.dumps(data, indent=2))
            logger.debug(
                "Checkpoint saved: %d scenarios to %s", count, checkpoint_path
            )
        except Exception as exc:
            logger.debug("Failed to save checkpoint: %s", exc)

        return checkpoint_path
