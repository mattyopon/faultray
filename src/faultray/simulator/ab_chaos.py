"""Chaos A/B Testing Engine.

Compares two architecture variants under the same chaos scenarios to
determine which design is more resilient.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.scenarios import Scenario, generate_default_scenarios


@dataclass
class ABResult:
    """Result of a single scenario comparison between two variants."""

    scenario_name: str
    variant_a_score: float  # risk_score from simulation (lower is better)
    variant_b_score: float
    winner: str  # "A", "B", "tie"
    difference: float  # absolute difference in risk scores


@dataclass
class ABReport:
    """Complete A/B comparison report."""

    variant_a_name: str
    variant_b_name: str
    scenarios_tested: int
    a_wins: int
    b_wins: int
    ties: int
    overall_winner: str  # "A", "B", "tie"
    variant_a_resilience: float  # resilience score (0-100, higher is better)
    variant_b_resilience: float
    variant_a_avg_risk: float  # average risk score (0-10, lower is better)
    variant_b_avg_risk: float
    results: list[ABResult] = field(default_factory=list)
    recommendation: str = ""


class ChaosABTester:
    """Compare two architecture variants under identical chaos scenarios."""

    # Threshold for considering scores equal (risk scores are 0-10)
    TIE_THRESHOLD = 0.1

    def __init__(
        self,
        graph_a: InfraGraph,
        graph_b: InfraGraph,
        name_a: str = "Current",
        name_b: str = "Proposed",
    ) -> None:
        self.graph_a = graph_a
        self.graph_b = graph_b
        self.name_a = name_a
        self.name_b = name_b

    def test(self, scenarios: list[Scenario] | None = None) -> ABReport:
        """Run the given scenarios on both architectures and compare.

        If *scenarios* is ``None``, default scenarios are auto-generated
        from the **intersection** of component IDs present in both graphs,
        so the comparison is fair.

        Parameters
        ----------
        scenarios:
            Explicit list of scenarios to test.  Each scenario's fault
            targets must exist in both graphs.

        Returns
        -------
        ABReport
            Full comparison report.
        """
        if scenarios is None:
            scenarios = self._generate_common_scenarios()

        # Filter scenarios to only those whose fault targets exist in both
        valid_scenarios = self._filter_valid_scenarios(scenarios)

        engine_a = SimulationEngine(self.graph_a)
        engine_b = SimulationEngine(self.graph_b)

        results: list[ABResult] = []
        a_wins = 0
        b_wins = 0
        ties = 0

        for scenario in valid_scenarios:
            result_a = engine_a.run_scenario(scenario)
            result_b = engine_b.run_scenario(scenario)

            risk_a = result_a.risk_score
            risk_b = result_b.risk_score
            diff = abs(risk_a - risk_b)

            if diff <= self.TIE_THRESHOLD:
                winner = "tie"
                ties += 1
            elif risk_a < risk_b:
                winner = "A"
                a_wins += 1
            else:
                winner = "B"
                b_wins += 1

            results.append(ABResult(
                scenario_name=scenario.name,
                variant_a_score=risk_a,
                variant_b_score=risk_b,
                winner=winner,
                difference=diff,
            ))

        # Determine overall winner
        if a_wins > b_wins:
            overall_winner = "A"
        elif b_wins > a_wins:
            overall_winner = "B"
        else:
            overall_winner = "tie"

        # Resilience scores
        res_a = self.graph_a.resilience_score()
        res_b = self.graph_b.resilience_score()

        # Average risk scores
        avg_risk_a = (
            sum(r.variant_a_score for r in results) / len(results)
            if results else 0.0
        )
        avg_risk_b = (
            sum(r.variant_b_score for r in results) / len(results)
            if results else 0.0
        )

        # Generate recommendation
        recommendation = self._generate_recommendation(
            overall_winner, a_wins, b_wins, ties, len(results),
            res_a, res_b, avg_risk_a, avg_risk_b,
        )

        return ABReport(
            variant_a_name=self.name_a,
            variant_b_name=self.name_b,
            scenarios_tested=len(results),
            a_wins=a_wins,
            b_wins=b_wins,
            ties=ties,
            overall_winner=overall_winner,
            variant_a_resilience=res_a,
            variant_b_resilience=res_b,
            variant_a_avg_risk=round(avg_risk_a, 2),
            variant_b_avg_risk=round(avg_risk_b, 2),
            results=results,
            recommendation=recommendation,
        )

    def test_default(self) -> ABReport:
        """Auto-generate scenarios and compare both architectures."""
        return self.test(scenarios=None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_common_scenarios(self) -> list[Scenario]:
        """Generate default scenarios using only components present in both graphs."""
        common_ids = sorted(
            set(self.graph_a.components.keys())
            & set(self.graph_b.components.keys())
        )
        if not common_ids:
            return []

        # Merge component metadata from both graphs for scenario generation
        merged_components: dict = {}
        for cid in common_ids:
            comp_a = self.graph_a.get_component(cid)
            if comp_a is not None:
                merged_components[cid] = comp_a

        return generate_default_scenarios(common_ids, components=merged_components)

    def _filter_valid_scenarios(self, scenarios: list[Scenario]) -> list[Scenario]:
        """Filter scenarios to only include those whose fault targets exist
        in both graphs."""
        valid: list[Scenario] = []
        a_ids = set(self.graph_a.components.keys())
        b_ids = set(self.graph_b.components.keys())

        for scenario in scenarios:
            # All fault targets must exist in both graphs
            all_targets = {f.target_component_id for f in scenario.faults}
            if all_targets <= a_ids and all_targets <= b_ids:
                valid.append(scenario)

        return valid

    def _generate_recommendation(
        self,
        overall_winner: str,
        a_wins: int,
        b_wins: int,
        ties: int,
        total: int,
        res_a: float,
        res_b: float,
        avg_risk_a: float,
        avg_risk_b: float,
    ) -> str:
        """Generate a human-readable recommendation based on results."""
        if total == 0:
            return (
                "No common scenarios could be tested. The two architectures "
                "share no common component IDs. Consider renaming components "
                "to match for a fair comparison."
            )

        winner_name = self.name_a if overall_winner == "A" else self.name_b
        loser_name = self.name_b if overall_winner == "A" else self.name_a

        if overall_winner == "tie":
            return (
                f"Both '{self.name_a}' and '{self.name_b}' performed equally "
                f"across {total} chaos scenarios "
                f"(resilience: {res_a:.1f} vs {res_b:.1f}). "
                f"Consider additional criteria such as cost, complexity, "
                f"and operational overhead for the final decision."
            )

        winner_wins = max(a_wins, b_wins)
        win_pct = winner_wins / total * 100

        return (
            f"'{winner_name}' outperformed '{loser_name}' in "
            f"{winner_wins}/{total} scenarios ({win_pct:.0f}%). "
            f"Resilience scores: {winner_name}="
            f"{res_a if overall_winner == 'A' else res_b:.1f}, "
            f"{loser_name}="
            f"{res_b if overall_winner == 'A' else res_a:.1f}. "
            f"Average risk: {winner_name}="
            f"{avg_risk_a if overall_winner == 'A' else avg_risk_b:.2f}, "
            f"{loser_name}="
            f"{avg_risk_b if overall_winner == 'A' else avg_risk_a:.2f}. "
            f"Recommend adopting '{winner_name}'."
        )
