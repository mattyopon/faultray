"""Genetic Algorithm for optimal failure scenario discovery.

Evolves a population of failure-scenario chromosomes (bitstrings indicating
which components are faulted) to find the combination that causes the
highest-severity cascade.  Useful for worst-case analysis and red-team
scenario generation.

Uses ONLY the Python standard library.

Basic usage::

    >>> from faultray.model.graph import InfraGraph
    >>> graph = InfraGraph()
    >>> # ... populate graph ...
    >>> optimizer = GAOptimizer(graph)
    >>> result = optimizer.evolve()
    >>> print(result.best_fitness, result.best_scenario)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from faultray.model.components import HealthStatus
from faultray.simulator.cascade import CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType, Scenario

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph

# Type alias for clarity
Chromosome = list[bool]


@dataclass
class GAResult:
    """Result of a Genetic Algorithm optimisation run.

    Attributes:
        best_fitness: Highest fitness (severity) achieved.
        best_chromosome: The chromosome that achieved it.
        generation_history: Per-generation best fitness values.
        best_scenario: The ``Scenario`` corresponding to the best chromosome.
    """

    best_fitness: float = 0.0
    best_chromosome: Chromosome = field(default_factory=list)
    generation_history: list[float] = field(default_factory=list)
    best_scenario: Scenario | None = None


class GAOptimizer:
    """Genetic Algorithm optimiser that discovers worst-case failure scenarios.

    Each chromosome is a boolean list of length ``N`` (number of components).
    A ``True`` at index *i* means that the *i*-th component is injected with
    a ``COMPONENT_DOWN`` fault.  Fitness equals the cascade severity produced
    by injecting all flagged faults simultaneously.

    Parameters:
        graph: The infrastructure dependency graph.
        population_size: Number of individuals per generation.
        generations: Maximum number of generations to evolve.
        seed: Optional RNG seed for reproducibility.
    """

    def __init__(
        self,
        graph: InfraGraph,
        population_size: int = 50,
        generations: int = 100,
        seed: int | None = None,
    ) -> None:
        self.graph = graph
        self.population_size = population_size
        self.generations = generations
        self._rng = random.Random(seed)
        self._cascade_engine = CascadeEngine(graph)
        self._component_ids: list[str] = list(graph.components.keys())
        self._n = len(self._component_ids)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evolve(self) -> GAResult:
        """Run the GA evolution loop and return the best result.

        Returns:
            A ``GAResult`` with the best fitness, chromosome, generation
            history, and the decoded ``Scenario``.
        """
        if self._n == 0:
            return GAResult()

        # Initialise random population
        population = [self._random_chromosome() for _ in range(self.population_size)]

        best_fitness = 0.0
        best_chromosome: Chromosome = [False] * self._n
        generation_history: list[float] = []

        for _gen in range(self.generations):
            # Evaluate fitness for every individual
            fitness_scores = [self._fitness(ch) for ch in population]

            # Track generation best
            gen_best_idx = max(range(len(fitness_scores)), key=lambda i: fitness_scores[i])
            gen_best_fit = fitness_scores[gen_best_idx]
            generation_history.append(gen_best_fit)

            if gen_best_fit > best_fitness:
                best_fitness = gen_best_fit
                best_chromosome = list(population[gen_best_idx])

            # Build next generation via selection, crossover, mutation
            next_population: list[Chromosome] = []

            # Elitism: carry the best individual forward
            next_population.append(list(population[gen_best_idx]))

            while len(next_population) < self.population_size:
                parent1 = self._tournament_select(population, fitness_scores)
                parent2 = self._tournament_select(population, fitness_scores)
                child1, child2 = self._crossover(parent1, parent2)
                self._mutate(child1)
                self._mutate(child2)
                next_population.append(child1)
                if len(next_population) < self.population_size:
                    next_population.append(child2)

            population = next_population

            # Early stopping if we have reached maximum possible severity
            if best_fitness >= 10.0:
                break

        best_scenario = self._chromosome_to_scenario(best_chromosome)

        return GAResult(
            best_fitness=best_fitness,
            best_chromosome=best_chromosome,
            generation_history=generation_history,
            best_scenario=best_scenario,
        )

    def best_scenario(self) -> Scenario:
        """Convenience wrapper: evolve and return only the best Scenario."""
        result = self.evolve()
        if result.best_scenario is not None:
            return result.best_scenario
        return Scenario(
            id="ga-empty",
            name="No scenario found",
            description="GA found no impactful failure combination.",
            faults=[],
        )

    # ------------------------------------------------------------------
    # GA operators
    # ------------------------------------------------------------------

    def _fitness(self, chromosome: Chromosome) -> float:
        """Evaluate a chromosome's fitness as the total cascade severity.

        Each ``True`` bit injects a ``COMPONENT_DOWN`` fault on the
        corresponding component.  The cascade engine simulates each fault
        independently and the severities are accumulated (capped at 10.0).
        """
        total_severity = 0.0
        for idx, active in enumerate(chromosome):
            if not active:
                continue
            comp_id = self._component_ids[idx]
            fault = Fault(
                target_component_id=comp_id,
                fault_type=FaultType.COMPONENT_DOWN,
            )
            chain = self._cascade_engine.simulate_fault(fault)
            total_severity += chain.severity

        return min(10.0, total_severity)

    def _tournament_select(
        self,
        population: list[Chromosome],
        fitness_scores: list[float],
        k: int = 3,
    ) -> Chromosome:
        """Select an individual via tournament selection (pick *k* random
        individuals, return the fittest).
        """
        indices = self._rng.sample(range(len(population)), min(k, len(population)))
        best_idx = max(indices, key=lambda i: fitness_scores[i])
        return list(population[best_idx])

    def _crossover(
        self, parent1: Chromosome, parent2: Chromosome
    ) -> tuple[Chromosome, Chromosome]:
        """Single-point crossover between two parents."""
        if self._n <= 1:
            return list(parent1), list(parent2)
        point = self._rng.randint(1, self._n - 1)
        child1 = parent1[:point] + parent2[point:]
        child2 = parent2[:point] + parent1[point:]
        return child1, child2

    def _mutate(self, chromosome: Chromosome, rate: float = 0.05) -> None:
        """Flip random bits in the chromosome with probability *rate*."""
        for i in range(len(chromosome)):
            if self._rng.random() < rate:
                chromosome[i] = not chromosome[i]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _random_chromosome(self) -> Chromosome:
        """Generate a random chromosome with low fault density."""
        # On average ~10 % of components are faulted
        return [self._rng.random() < 0.1 for _ in range(self._n)]

    def _chromosome_to_scenario(self, chromosome: Chromosome) -> Scenario:
        """Decode a chromosome into a ``Scenario``."""
        faults: list[Fault] = []
        for idx, active in enumerate(chromosome):
            if active:
                faults.append(
                    Fault(
                        target_component_id=self._component_ids[idx],
                        fault_type=FaultType.COMPONENT_DOWN,
                    )
                )

        return Scenario(
            id="ga-best",
            name="GA-optimised worst-case scenario",
            description=(
                f"Genetic Algorithm discovered scenario with "
                f"{len(faults)} simultaneous faults."
            ),
            faults=faults,
        )
