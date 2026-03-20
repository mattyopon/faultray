# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Chaos Monkey Mode - Random failure injection simulation.

Inspired by Netflix's Chaos Monkey, this mode randomly selects components
to fail and observes the system's behavior. Unlike targeted scenarios,
Chaos Monkey tests the system's resilience to unpredictable failures.

Modes:
- monkey: Random single component failure
- gorilla: Random AZ/zone failure (multiple components of the same type)
- kong: Random region failure (massive multi-component failure)
- army: Combined random failures across multiple dimensions (progressive)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType


class ChaosLevel(str, Enum):
    """Level of chaos to inject."""

    MONKEY = "monkey"
    GORILLA = "gorilla"
    KONG = "kong"
    ARMY = "army"


@dataclass
class ChaosMonkeyConfig:
    """Configuration for a Chaos Monkey run."""

    level: ChaosLevel = ChaosLevel.MONKEY
    rounds: int = 10
    seed: int | None = None
    exclude_components: list[str] = field(default_factory=list)
    max_simultaneous_failures: int = 1
    target_types: list[str] | None = None


@dataclass
class MonkeyExperiment:
    """Result of a single chaos experiment."""

    round_number: int
    failed_components: list[str]
    level: ChaosLevel
    survived: bool
    cascade_depth: int
    affected_count: int
    resilience_during: float
    recovery_possible: bool


@dataclass
class ChaosMonkeyReport:
    """Complete report from a Chaos Monkey run."""

    config: ChaosMonkeyConfig
    experiments: list[MonkeyExperiment] = field(default_factory=list)
    total_rounds: int = 0
    survival_rate: float = 0.0
    avg_cascade_depth: float = 0.0
    avg_affected: float = 0.0
    worst_experiment: MonkeyExperiment | None = None
    best_experiment: MonkeyExperiment | None = None
    most_dangerous_component: str = ""
    safest_component: str = ""
    mean_time_to_impact: float = 0.0
    resilience_score_range: tuple[float, float] = (0.0, 0.0)
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fault types to randomly select from
# ---------------------------------------------------------------------------

_FAULT_TYPES = [
    FaultType.COMPONENT_DOWN,
    FaultType.MEMORY_EXHAUSTION,
    FaultType.CPU_SATURATION,
    FaultType.DISK_FULL,
    FaultType.CONNECTION_POOL_EXHAUSTION,
    FaultType.NETWORK_PARTITION,
]


class ChaosMonkey:
    """Netflix-style random failure injection simulator."""

    def run(
        self,
        graph: InfraGraph,
        config: ChaosMonkeyConfig | None = None,
    ) -> ChaosMonkeyReport:
        """Run a full Chaos Monkey experiment suite."""
        if config is None:
            config = ChaosMonkeyConfig()

        rng = random.Random(config.seed)
        eligible = self._get_eligible_components(graph, config)

        if not eligible:
            return ChaosMonkeyReport(
                config=config,
                total_rounds=0,
                survival_rate=1.0,
                recommendations=["No eligible components to test."],
            )

        experiments: list[MonkeyExperiment] = []

        for round_num in range(1, config.rounds + 1):
            if config.level == ChaosLevel.ARMY:
                # Progressive: round N fails N components
                num_failures = min(round_num, len(eligible))
                exp = self._run_experiment(
                    graph, rng, eligible, round_num, config.level, num_failures
                )
            elif config.level == ChaosLevel.GORILLA:
                num_failures = min(rng.randint(2, 3), len(eligible))
                exp = self._run_gorilla_experiment(
                    graph, rng, eligible, round_num, num_failures
                )
            elif config.level == ChaosLevel.KONG:
                pct = rng.uniform(0.3, 0.5)
                num_failures = max(1, int(len(eligible) * pct))
                exp = self._run_experiment(
                    graph, rng, eligible, round_num, ChaosLevel.KONG, num_failures
                )
            else:
                exp = self._run_experiment(
                    graph, rng, eligible, round_num, ChaosLevel.MONKEY, 1
                )
            experiments.append(exp)

        return self._build_report(graph, config, experiments)

    def run_single(
        self,
        graph: InfraGraph,
        level: ChaosLevel = ChaosLevel.MONKEY,
        seed: int | None = None,
    ) -> MonkeyExperiment:
        """Run a single chaos experiment."""
        config = ChaosMonkeyConfig(level=level, rounds=1, seed=seed)
        report = self.run(graph, config)
        if report.experiments:
            return report.experiments[0]
        return MonkeyExperiment(
            round_number=1,
            failed_components=[],
            level=level,
            survived=True,
            cascade_depth=0,
            affected_count=0,
            resilience_during=graph.resilience_score(),
            recovery_possible=True,
        )

    def find_weakest_point(
        self,
        graph: InfraGraph,
        rounds: int = 50,
        seed: int | None = None,
    ) -> str:
        """Find the single component whose failure causes the most damage.

        Tests each component individually and returns the one with highest impact.
        """
        rng = random.Random(seed)
        comp_ids = list(graph.components.keys())

        if not comp_ids:
            return ""

        damage: dict[str, float] = {cid: 0.0 for cid in comp_ids}
        count: dict[str, int] = {cid: 0 for cid in comp_ids}

        for _ in range(rounds):
            target = rng.choice(comp_ids)
            fault_type = rng.choice(_FAULT_TYPES)
            fault = Fault(target_component_id=target, fault_type=fault_type)
            engine = CascadeEngine(graph)
            chain = engine.simulate_fault(fault)

            affected = len(chain.effects)
            damage[target] += affected
            count[target] += 1

        # Average damage per component
        avg_damage = {}
        for cid in comp_ids:
            if count[cid] > 0:
                avg_damage[cid] = damage[cid] / count[cid]
            else:
                avg_damage[cid] = 0.0

        return max(avg_damage, key=lambda k: avg_damage[k])

    def stress_test(
        self,
        graph: InfraGraph,
        max_failures: int = 5,
        seed: int | None = None,
    ) -> list[MonkeyExperiment]:
        """Progressive stress test -- increase simultaneous failures until breaking point."""
        config = ChaosMonkeyConfig(
            level=ChaosLevel.ARMY,
            rounds=max_failures,
            seed=seed,
        )
        report = self.run(graph, config)
        return report.experiments

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _get_eligible_components(
        self, graph: InfraGraph, config: ChaosMonkeyConfig
    ) -> list[str]:
        """Get list of component IDs eligible for failure injection."""
        eligible = []
        for cid, comp in graph.components.items():
            if cid in config.exclude_components:
                continue
            if config.target_types is not None:
                if comp.type.value not in config.target_types:
                    continue
            eligible.append(cid)
        return eligible

    def _run_experiment(
        self,
        graph: InfraGraph,
        rng: random.Random,
        eligible: list[str],
        round_num: int,
        level: ChaosLevel,
        num_failures: int,
    ) -> MonkeyExperiment:
        """Run a single experiment failing N random components."""
        num_failures = min(num_failures, len(eligible))
        targets = rng.sample(eligible, num_failures)

        return self._evaluate_failures(graph, rng, targets, round_num, level)

    def _run_gorilla_experiment(
        self,
        graph: InfraGraph,
        rng: random.Random,
        eligible: list[str],
        round_num: int,
        num_failures: int,
    ) -> MonkeyExperiment:
        """Run a gorilla experiment -- fail multiple components of the same type."""
        # Group eligible components by type
        by_type: dict[str, list[str]] = {}
        for cid in eligible:
            comp = graph.get_component(cid)
            if comp:
                tval = comp.type.value
                by_type.setdefault(tval, []).append(cid)

        # Pick a type that has enough components
        viable_types = [t for t, ids in by_type.items() if len(ids) >= 2]
        if not viable_types:
            # Fall back to random selection
            return self._run_experiment(
                graph, rng, eligible, round_num, ChaosLevel.GORILLA, num_failures
            )

        chosen_type = rng.choice(viable_types)
        pool = by_type[chosen_type]
        count = min(num_failures, len(pool))
        targets = rng.sample(pool, count)

        return self._evaluate_failures(graph, rng, targets, round_num, ChaosLevel.GORILLA)

    def _evaluate_failures(
        self,
        graph: InfraGraph,
        rng: random.Random,
        targets: list[str],
        round_num: int,
        level: ChaosLevel,
    ) -> MonkeyExperiment:
        """Evaluate the impact of failing specific components."""
        engine = CascadeEngine(graph)
        all_affected: set[str] = set()
        max_depth = 0
        total_time = 0.0
        total_comps = len(graph.components)

        for target in targets:
            fault_type = rng.choice(_FAULT_TYPES)
            fault = Fault(target_component_id=target, fault_type=fault_type)
            chain = engine.simulate_fault(fault)

            for effect in chain.effects:
                all_affected.add(effect.component_id)
                if effect.estimated_time_seconds > total_time:
                    total_time = effect.estimated_time_seconds

            # Cascade depth: count effects beyond the direct target
            depth = max(0, len(chain.effects) - 1)
            if depth > max_depth:
                max_depth = depth

        affected_count = len(all_affected)

        # Determine survival: system survives if less than 50% of components affected
        survived = affected_count < (total_comps * 0.5)

        # Resilience during failure: simple estimate
        if total_comps > 0:
            healthy_ratio = (total_comps - affected_count) / total_comps
            resilience_during = max(0.0, graph.resilience_score() * healthy_ratio)
        else:
            resilience_during = 0.0

        # Recovery possible if any non-affected components remain
        recovery_possible = affected_count < total_comps

        return MonkeyExperiment(
            round_number=round_num,
            failed_components=targets,
            level=level,
            survived=survived,
            cascade_depth=max_depth,
            affected_count=affected_count,
            resilience_during=round(resilience_during, 1),
            recovery_possible=recovery_possible,
        )

    def _build_report(
        self,
        graph: InfraGraph,
        config: ChaosMonkeyConfig,
        experiments: list[MonkeyExperiment],
    ) -> ChaosMonkeyReport:
        """Build the final Chaos Monkey report."""
        if not experiments:
            return ChaosMonkeyReport(
                config=config,
                total_rounds=0,
                survival_rate=1.0,
            )

        total = len(experiments)
        survived = sum(1 for e in experiments if e.survived)

        depths = [e.cascade_depth for e in experiments]
        affected_counts = [e.affected_count for e in experiments]
        resilience_scores = [e.resilience_during for e in experiments]

        worst = max(experiments, key=lambda e: e.affected_count)
        best = min(experiments, key=lambda e: e.affected_count)

        # Find most dangerous / safest component across experiments
        danger_score: dict[str, float] = {}
        for exp in experiments:
            for comp_id in exp.failed_components:
                danger_score[comp_id] = danger_score.get(comp_id, 0.0) + exp.affected_count

        most_dangerous = max(danger_score, key=lambda k: danger_score[k]) if danger_score else ""
        safest = min(danger_score, key=lambda k: danger_score[k]) if danger_score else ""

        # Mean time to impact (average estimated time from experiments with effects)
        times = [e.cascade_depth * 5.0 for e in experiments if e.cascade_depth > 0]
        mtti = sum(times) / len(times) if times else 0.0

        recommendations = self._generate_recommendations(
            graph, config, experiments, most_dangerous
        )

        return ChaosMonkeyReport(
            config=config,
            experiments=experiments,
            total_rounds=total,
            survival_rate=round(survived / total, 3) if total > 0 else 1.0,
            avg_cascade_depth=round(sum(depths) / total, 1) if total > 0 else 0.0,
            avg_affected=round(sum(affected_counts) / total, 1) if total > 0 else 0.0,
            worst_experiment=worst,
            best_experiment=best,
            most_dangerous_component=most_dangerous,
            safest_component=safest,
            mean_time_to_impact=round(mtti, 1),
            resilience_score_range=(
                min(resilience_scores) if resilience_scores else 0.0,
                max(resilience_scores) if resilience_scores else 0.0,
            ),
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self,
        graph: InfraGraph,
        config: ChaosMonkeyConfig,
        experiments: list[MonkeyExperiment],
        most_dangerous: str,
    ) -> list[str]:
        """Generate actionable recommendations from experiment results."""
        recs: list[str] = []

        survival_rate = sum(1 for e in experiments if e.survived) / max(len(experiments), 1)

        if survival_rate < 0.5:
            recs.append(
                f"Critical: System survived only {survival_rate:.0%} of experiments. "
                "Major resilience improvements needed."
            )
        elif survival_rate < 0.8:
            recs.append(
                f"Warning: System survival rate is {survival_rate:.0%}. "
                "Consider adding redundancy to key components."
            )

        if most_dangerous:
            comp = graph.get_component(most_dangerous)
            if comp:
                recs.append(
                    f"Most dangerous component: '{comp.name}' ({most_dangerous}). "
                    "Prioritize adding redundancy and failover for this component."
                )
                if comp.replicas <= 1:
                    recs.append(
                        f"Component '{comp.name}' is a single instance. "
                        "Add replicas to reduce blast radius."
                    )
                if not comp.failover.enabled:
                    recs.append(
                        f"Component '{comp.name}' has no failover. "
                        "Enable failover for automatic recovery."
                    )

        # Check for patterns
        deep_cascades = [e for e in experiments if e.cascade_depth >= 3]
        if deep_cascades:
            recs.append(
                f"{len(deep_cascades)} experiments had deep cascades (depth >= 3). "
                "Add circuit breakers to limit failure propagation."
            )

        no_recovery = [e for e in experiments if not e.recovery_possible]
        if no_recovery:
            recs.append(
                f"{len(no_recovery)} experiments resulted in unrecoverable failures. "
                "Implement automated recovery mechanisms."
            )

        return recs
