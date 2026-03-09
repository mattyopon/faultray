"""Simulation engine - orchestrates scenario execution."""

from __future__ import annotations

from dataclasses import dataclass, field

from infrasim.model.graph import InfraGraph
from infrasim.simulator.cascade import CascadeChain, CascadeEngine
from infrasim.simulator.scenarios import Scenario, generate_default_scenarios


@dataclass
class ScenarioResult:
    """Result of running a single scenario."""

    scenario: Scenario
    cascade: CascadeChain
    risk_score: float = 0.0

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

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self.cascade_engine = CascadeEngine(graph)

    def run_scenario(self, scenario: Scenario) -> ScenarioResult:
        """Run a single chaos scenario."""
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

    def run_all_defaults(self) -> SimulationReport:
        """Run all default scenarios."""
        component_ids = list(self.graph.components.keys())
        scenarios = generate_default_scenarios(
            component_ids, components=self.graph.components
        )
        return self.run_scenarios(scenarios)

    def run_scenarios(self, scenarios: list[Scenario]) -> SimulationReport:
        """Run a list of scenarios and generate a report."""
        results = []
        for scenario in scenarios:
            result = self.run_scenario(scenario)
            results.append(result)

        # Sort by risk score descending
        results.sort(key=lambda r: r.risk_score, reverse=True)

        return SimulationReport(
            results=results,
            resilience_score=self.graph.resilience_score(),
        )
