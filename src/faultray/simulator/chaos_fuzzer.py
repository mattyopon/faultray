# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""AFL-inspired fuzzing for infrastructure chaos scenarios.

Randomly mutate scenarios to discover unknown failure patterns. The fuzzer
maintains a corpus of interesting scenarios (those that produce novel failure
fingerprints) and applies mutations to explore the failure space.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from faultray.model.graph import InfraGraph
from faultray.simulator.engine import ScenarioResult, SimulationEngine
from faultray.simulator.scenarios import Fault, FaultType, Scenario


@dataclass
class FuzzResult:
    """Result of a single fuzzing iteration."""

    iteration: int
    scenario: Scenario
    risk_score: float
    is_novel: bool  # True if this failure pattern wasn't seen before
    mutation_type: str  # "add_fault", "change_target", "combine", "amplify_traffic", etc.


@dataclass
class FuzzReport:
    """Summary report from a fuzzing campaign."""

    total_iterations: int
    novel_failures_found: int
    highest_risk_score: float
    novel_scenarios: list[FuzzResult]
    coverage: float  # fraction of components that were faulted (0.0-1.0)
    mutation_effectiveness: dict[str, float]  # {mutation_type: novel_discovery_rate}


class ChaosFuzzer:
    """AFL-inspired fuzzer for infrastructure chaos scenarios.

    The fuzzer works by:
    1. Starting with a seed corpus (either user-supplied or auto-generated).
    2. Picking a scenario from the corpus and applying a random mutation.
    3. Running the mutated scenario through the simulation engine.
    4. If the failure pattern is novel, adding it to the corpus.
    5. Repeating for N iterations.
    """

    MUTATION_TYPES = [
        "add_fault",
        "remove_fault",
        "change_target",
        "change_type",
        "combine",
        "amplify_traffic",
    ]

    def __init__(self, graph: InfraGraph, seed: int = 42) -> None:
        self.graph = graph
        self.engine = SimulationEngine(graph)
        self.rng = random.Random(seed)
        self._seen_patterns: set[str] = set()

    def fuzz(
        self,
        iterations: int = 100,
        base_scenarios: list[Scenario] | None = None,
    ) -> FuzzReport:
        """Run *iterations* rounds of mutation-based fuzzing.

        Parameters
        ----------
        iterations:
            Number of fuzzing iterations.
        base_scenarios:
            Optional seed scenarios.  If ``None``, the fuzzer generates a
            small seed corpus from the graph's component IDs.

        Returns
        -------
        FuzzReport
            Aggregated fuzzing results.
        """
        results: list[FuzzResult] = []
        comp_ids = list(self.graph.components.keys())
        fault_types = list(FaultType)

        # Start with base scenarios or generate random ones
        corpus: list[Scenario] = list(
            base_scenarios or self._generate_seed_corpus(comp_ids)
        )

        # Edge case: if the graph has no components, return immediately
        if not comp_ids or not corpus:
            return FuzzReport(
                total_iterations=iterations,
                novel_failures_found=0,
                highest_risk_score=0.0,
                novel_scenarios=[],
                coverage=0.0,
                mutation_effectiveness={},
            )

        for i in range(iterations):
            # Pick a scenario from the corpus
            parent = self.rng.choice(corpus)

            # Mutate it
            mutation_type = self.rng.choice(self.MUTATION_TYPES)
            mutated = self._mutate(parent, mutation_type, comp_ids, fault_types)

            # Simulate
            sim_result: ScenarioResult = self.engine.run_scenario(mutated)

            # Check if this is a novel failure pattern
            pattern = self._fingerprint(sim_result)
            is_novel = pattern not in self._seen_patterns
            if is_novel:
                self._seen_patterns.add(pattern)
                corpus.append(mutated)  # Add interesting mutations to corpus

            results.append(
                FuzzResult(
                    iteration=i,
                    scenario=mutated,
                    risk_score=sim_result.risk_score,
                    is_novel=is_novel,
                    mutation_type=mutation_type,
                )
            )

        novel = [r for r in results if r.is_novel]
        mutation_stats: dict[str, float] = {}
        for mt in self.MUTATION_TYPES:
            mt_results = [r for r in results if r.mutation_type == mt]
            if mt_results:
                mutation_stats[mt] = sum(
                    1 for r in mt_results if r.is_novel
                ) / len(mt_results)

        faulted_components: set[str] = set()
        for r in results:
            for f in r.scenario.faults:
                faulted_components.add(f.target_component_id)

        return FuzzReport(
            total_iterations=iterations,
            novel_failures_found=len(novel),
            highest_risk_score=max(
                (r.risk_score for r in results), default=0.0
            ),
            novel_scenarios=sorted(
                novel, key=lambda r: r.risk_score, reverse=True
            )[:20],
            coverage=len(faulted_components) / max(len(comp_ids), 1),
            mutation_effectiveness=mutation_stats,
        )

    # ------------------------------------------------------------------
    # Mutation operators
    # ------------------------------------------------------------------

    def _mutate(
        self,
        scenario: Scenario,
        mutation_type: str,
        comp_ids: list[str],
        fault_types: list[FaultType],
    ) -> Scenario:
        """Apply a mutation to create a new scenario."""
        faults = list(scenario.faults)

        if mutation_type == "add_fault" and comp_ids:
            faults.append(
                Fault(
                    target_component_id=self.rng.choice(comp_ids),
                    fault_type=self.rng.choice(fault_types),
                    severity=self.rng.uniform(0.3, 1.0),
                )
            )
        elif mutation_type == "remove_fault" and len(faults) > 1:
            faults.pop(self.rng.randint(0, len(faults) - 1))
        elif mutation_type == "change_target" and faults and comp_ids:
            idx = self.rng.randint(0, len(faults) - 1)
            faults[idx] = Fault(
                target_component_id=self.rng.choice(comp_ids),
                fault_type=faults[idx].fault_type,
                severity=faults[idx].severity,
            )
        elif mutation_type == "change_type" and faults:
            idx = self.rng.randint(0, len(faults) - 1)
            faults[idx] = Fault(
                target_component_id=faults[idx].target_component_id,
                fault_type=self.rng.choice(fault_types),
                severity=faults[idx].severity,
            )
        elif mutation_type == "combine" and len(comp_ids) >= 2:
            targets = self.rng.sample(comp_ids, min(3, len(comp_ids)))
            faults = [
                Fault(
                    target_component_id=t,
                    fault_type=self.rng.choice(fault_types),
                )
                for t in targets
            ]
        elif mutation_type == "amplify_traffic":
            traffic = self.rng.uniform(2.0, 15.0)
            return Scenario(
                id=f"fuzz-{id(faults)}",
                name=f"Fuzz (traffic {traffic:.1f}x)",
                description="Fuzzer-generated",
                faults=faults,
                traffic_multiplier=traffic,
            )

        return Scenario(
            id=f"fuzz-{id(faults)}",
            name=f"Fuzz ({mutation_type})",
            description="Fuzzer-generated",
            faults=faults,
        )

    # ------------------------------------------------------------------
    # Seed corpus generation
    # ------------------------------------------------------------------

    def _generate_seed_corpus(
        self, comp_ids: list[str]
    ) -> list[Scenario]:
        """Generate initial seed scenarios (one per component, up to 5)."""
        seeds: list[Scenario] = []
        for cid in comp_ids[:5]:
            seeds.append(
                Scenario(
                    id=f"seed-{cid}",
                    name=f"Seed: {cid} down",
                    description="Seed",
                    faults=[
                        Fault(
                            target_component_id=cid,
                            fault_type=FaultType.COMPONENT_DOWN,
                        )
                    ],
                )
            )
        return seeds

    # ------------------------------------------------------------------
    # Fingerprinting
    # ------------------------------------------------------------------

    def _fingerprint(self, result: ScenarioResult) -> str:
        """Create a fingerprint of the failure pattern.

        The fingerprint captures which components ended up DOWN.  Two
        scenarios that produce the same set of downed components are
        considered equivalent.
        """
        affected = sorted(
            e.component_id
            for e in result.cascade.effects
            if e.health.value == "down"
        )
        return "|".join(affected)
