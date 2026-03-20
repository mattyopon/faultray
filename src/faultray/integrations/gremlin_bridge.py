# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Gremlin Bridge -- simulation vs real chaos engineering comparison.

Import Gremlin scenarios -> run FaultRay prediction -> compare with Gremlin results.
Enables 'predict then verify' hybrid workflow.

The core value proposition: use FaultRay's *fast, safe* simulation to explore
thousands of failure scenarios, then validate the most interesting predictions
with Gremlin's *real* chaos experiments.  After validation, compare predictions
with actual results to continuously improve simulation accuracy.

Workflow:
    1. Import Gremlin attack definitions -> FaultRay Scenarios
    2. Run FaultRay prediction (fast, safe, no production impact)
    3. Import Gremlin execution results after real chaos test
    4. Compare prediction vs reality (precision, recall, F1)
    5. Generate hybrid report with accuracy metrics
    6. Recommend next tests to maximize coverage

Environment variables:
    GREMLIN_API_KEY  -- Gremlin API key
    GREMLIN_TEAM_ID  -- Gremlin team identifier

When the API key is not set, mock data is returned.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType, Scenario

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PredictionResult:
    """FaultRay's prediction for a scenario."""

    scenario_id: str
    affected_components: list[str]
    severity_scores: dict[str, float] = field(default_factory=dict)  # comp_id -> severity 0-10
    overall_severity: float = 0.0
    cascade_chain: CascadeChain | None = None


@dataclass
class GremlinResult:
    """Actual results from a Gremlin chaos experiment."""

    attack_id: str
    attack_type: str
    target: str
    affected_components: list[str]  # components that were actually impacted
    severity_observed: dict[str, float] = field(default_factory=dict)  # comp_id -> observed severity
    duration_seconds: int = 0
    status: str = "completed"  # completed, aborted, failed


@dataclass
class ComparisonReport:
    """Comparison of FaultRay prediction vs Gremlin actual results."""

    scenario_id: str
    precision: float  # of predicted affected, what fraction were actually affected
    recall: float  # of actually affected, what fraction were predicted
    f1: float  # harmonic mean of precision and recall
    severity_match: float  # how close severity predictions were (0-1, 1=perfect)
    predicted_only: list[str]  # FaultRay predicted but Gremlin didn't observe
    observed_only: list[str]  # Gremlin observed but FaultRay missed
    correctly_predicted: list[str]  # both predicted and observed


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

_MOCK_GREMLIN_SCENARIOS: dict = {
    "attacks": [
        {
            "guid": "attack-001",
            "attackType": "cpu",
            "targetType": "Host",
            "target": "web-server-1",
            "args": {"length": 300, "cores": 0, "percent": 100},
        },
        {
            "guid": "attack-002",
            "attackType": "shutdown",
            "targetType": "Host",
            "target": "db-server-1",
            "args": {"delay": 0, "reboot": True},
        },
        {
            "guid": "attack-003",
            "attackType": "latency",
            "targetType": "Host",
            "target": "api-gateway",
            "args": {"length": 300, "ms": 2000, "jitter": 500},
        },
    ]
}

_MOCK_GREMLIN_RESULT: dict = {
    "attack_id": "attack-001",
    "status": "completed",
    "target": "web-server-1",
    "affected": ["web-server-1", "api-gateway"],
    "duration": 300,
    "severity": {"web-server-1": 8.0, "api-gateway": 4.0},
}


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class GremlinBridge:
    """Bridge between FaultRay simulation and Gremlin real chaos engineering.

    Enables a 'predict then verify' workflow:

    1. **Predict**: FaultRay simulates thousands of scenarios safely
    2. **Prioritize**: Rank scenarios by predicted severity
    3. **Verify**: Run the most interesting predictions as real Gremlin attacks
    4. **Compare**: Measure prediction accuracy (precision/recall/F1)
    5. **Improve**: Use comparison data to calibrate simulation models

    Example::

        graph = InfraGraph.load(Path("infra.json"))
        bridge = GremlinBridge(
            api_key=os.environ.get("GREMLIN_API_KEY"),
            team_id=os.environ.get("GREMLIN_TEAM_ID"),
            graph=graph,
        )
        scenarios = bridge.import_scenarios(gremlin_json)
        for scenario in scenarios:
            prediction = bridge.predict(scenario)
            gremlin_result = bridge.import_results(scenario.id)
            comparison = bridge.compare(prediction, gremlin_result)
            print(f"F1: {comparison.f1:.2f}")
    """

    def __init__(
        self,
        api_key: str | None = None,
        team_id: str | None = None,
        graph: InfraGraph | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("GREMLIN_API_KEY", "")
        self._team_id = team_id or os.environ.get("GREMLIN_TEAM_ID", "")
        self._graph = graph or InfraGraph()
        self._mock = not self._api_key
        if self._mock:
            logger.info("GremlinBridge running in mock mode (no API key).")

    # ------------------------------------------------------------------
    # Import scenarios
    # ------------------------------------------------------------------

    def import_scenarios(self, gremlin_json: dict | None = None) -> list[Scenario]:
        """Convert Gremlin attack definitions to FaultRay Scenarios.

        Args:
            gremlin_json: Gremlin attacks JSON. If None, fetches from API (or mock).

        Returns:
            List of :class:`Scenario` objects for FaultRay simulation.
        """
        if gremlin_json is None:
            gremlin_json = self._fetch_attacks()

        attacks = gremlin_json.get("attacks", [])
        scenarios: list[Scenario] = []

        # Map Gremlin attack types to FaultRay FaultType
        attack_type_map: dict[str, FaultType] = {
            "cpu": FaultType.CPU_SATURATION,
            "memory": FaultType.MEMORY_EXHAUSTION,
            "disk": FaultType.DISK_FULL,
            "shutdown": FaultType.COMPONENT_DOWN,
            "process_killer": FaultType.COMPONENT_DOWN,
            "latency": FaultType.LATENCY_SPIKE,
            "packet_loss": FaultType.NETWORK_PARTITION,
            "blackhole": FaultType.NETWORK_PARTITION,
            "dns": FaultType.NETWORK_PARTITION,
        }

        for attack in attacks:
            attack_id = attack.get("guid", attack.get("id", "unknown"))
            attack_type = attack.get("attackType", "shutdown")
            target = attack.get("target", "")
            args = attack.get("args", {})

            fault_type = attack_type_map.get(attack_type, FaultType.COMPONENT_DOWN)

            # Find the target component in the graph
            comp_id = self._resolve_target(target)
            if not comp_id:
                logger.warning(
                    "Gremlin target '%s' not found in graph, skipping.", target
                )
                continue

            scenario = Scenario(
                id=f"gremlin-{attack_id}",
                name=f"Gremlin: {attack_type} on {target}",
                description=(
                    f"Imported from Gremlin attack {attack_id}. "
                    f"Type: {attack_type}, Target: {target}, Args: {args}"
                ),
                faults=[
                    Fault(
                        target_component_id=comp_id,
                        fault_type=fault_type,
                        severity=1.0,
                        duration_seconds=args.get("length", 300),
                        parameters={"gremlin_attack_id": attack_id, **args},
                    )
                ],
            )
            scenarios.append(scenario)

        return scenarios

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------

    def predict(self, scenario: Scenario) -> PredictionResult:
        """Run FaultRay prediction for a single scenario.

        Args:
            scenario: A :class:`Scenario` (typically from :meth:`import_scenarios`).

        Returns:
            :class:`PredictionResult` with predicted affected components and severity.
        """
        cascade_engine = CascadeEngine(self._graph)

        if not scenario.faults:
            return PredictionResult(scenario_id=scenario.id, affected_components=[])

        fault = scenario.faults[0]
        chain = cascade_engine.simulate_fault(fault)

        affected = [e.component_id for e in chain.effects]
        severity_scores: dict[str, float] = {}

        for effect in chain.effects:
            health_severity = {
                HealthStatus.DOWN: 10.0,
                HealthStatus.OVERLOADED: 6.0,
                HealthStatus.DEGRADED: 3.0,
                HealthStatus.HEALTHY: 0.0,
            }
            severity_scores[effect.component_id] = health_severity.get(
                effect.health, 0.0
            )

        return PredictionResult(
            scenario_id=scenario.id,
            affected_components=affected,
            severity_scores=severity_scores,
            overall_severity=chain.severity,
            cascade_chain=chain,
        )

    # ------------------------------------------------------------------
    # Import results
    # ------------------------------------------------------------------

    def import_results(self, gremlin_attack_id: str) -> GremlinResult:
        """Import actual results from a completed Gremlin attack.

        Args:
            gremlin_attack_id: Gremlin attack GUID.

        Returns:
            :class:`GremlinResult` with observed impact data.
        """
        if self._mock:
            logger.debug("Returning mock Gremlin result for %s", gremlin_attack_id)
            mock = _MOCK_GREMLIN_RESULT
            return GremlinResult(
                attack_id=mock["attack_id"],
                attack_type="cpu",
                target=mock["target"],
                affected_components=mock["affected"],
                severity_observed=mock["severity"],
                duration_seconds=mock["duration"],
                status=mock["status"],
            )

        try:
            with httpx.Client(
                base_url="https://api.gremlin.com",
                timeout=30,
                headers={
                    "Authorization": f"Key {self._api_key}",
                    "X-Gremlin-Agent": "faultray",
                },
            ) as client:
                resp = client.get(
                    f"/v1/attacks/{gremlin_attack_id}",
                    params={"teamId": self._team_id},
                )
                resp.raise_for_status()
                data = resp.json()

                return GremlinResult(
                    attack_id=gremlin_attack_id,
                    attack_type=data.get("attackType", "unknown"),
                    target=data.get("target", ""),
                    affected_components=data.get("impactedTargets", []),
                    severity_observed=data.get("severityMap", {}),
                    duration_seconds=data.get("duration", 0),
                    status=data.get("status", "completed"),
                )
        except Exception as exc:
            logger.warning("Gremlin import_results failed: %s", exc)
            return GremlinResult(
                attack_id=gremlin_attack_id,
                attack_type="unknown",
                target="",
                affected_components=[],
                status="error",
            )

    # ------------------------------------------------------------------
    # Compare
    # ------------------------------------------------------------------

    def compare(
        self,
        prediction: PredictionResult,
        gremlin_result: GremlinResult,
    ) -> ComparisonReport:
        """Compare FaultRay prediction with Gremlin actual results.

        Computes precision, recall, F1, severity match, and identifies
        what FaultRay missed vs what it predicted that didn't happen.

        Args:
            prediction: FaultRay's prediction.
            gremlin_result: Gremlin's observed results.

        Returns:
            :class:`ComparisonReport` with accuracy metrics.
        """
        predicted_set = set(prediction.affected_components)
        observed_set = set(gremlin_result.affected_components)

        correctly_predicted = predicted_set & observed_set
        predicted_only = predicted_set - observed_set  # false positives
        observed_only = observed_set - predicted_set  # false negatives

        # Precision: of what we predicted, how much was right
        precision = (
            len(correctly_predicted) / len(predicted_set)
            if predicted_set
            else 0.0
        )

        # Recall: of what actually happened, how much did we predict
        recall = (
            len(correctly_predicted) / len(observed_set)
            if observed_set
            else 0.0
        )

        # F1: harmonic mean
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        # Severity match: how close were our severity predictions
        severity_diffs: list[float] = []
        for comp_id in correctly_predicted:
            pred_sev = prediction.severity_scores.get(comp_id, 0.0)
            obs_sev = gremlin_result.severity_observed.get(comp_id, 0.0)
            if obs_sev > 0:
                # Normalized difference: 0 = perfect, 1 = maximally wrong
                diff = abs(pred_sev - obs_sev) / 10.0
                severity_diffs.append(1.0 - diff)

        severity_match = (
            sum(severity_diffs) / len(severity_diffs)
            if severity_diffs
            else 0.0
        )

        return ComparisonReport(
            scenario_id=prediction.scenario_id,
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            severity_match=round(severity_match, 4),
            predicted_only=sorted(predicted_only),
            observed_only=sorted(observed_only),
            correctly_predicted=sorted(correctly_predicted),
        )

    # ------------------------------------------------------------------
    # Generate hybrid report
    # ------------------------------------------------------------------

    def generate_hybrid_report(
        self, comparisons: list[ComparisonReport],
    ) -> str:
        """Generate a Markdown hybrid workflow report from comparison data.

        Args:
            comparisons: List of comparison reports.

        Returns:
            Markdown-formatted report string.
        """
        if not comparisons:
            return "# Hybrid Report\n\nNo comparison data available."

        avg_precision = sum(c.precision for c in comparisons) / len(comparisons)
        avg_recall = sum(c.recall for c in comparisons) / len(comparisons)
        avg_f1 = sum(c.f1 for c in comparisons) / len(comparisons)
        avg_severity = sum(c.severity_match for c in comparisons) / len(comparisons)

        lines = [
            "# FaultRay x Gremlin Hybrid Report",
            "",
            "## Overall Accuracy",
            f"- **Precision**: {avg_precision:.1%} (of predicted impacts, this fraction occurred)",
            f"- **Recall**: {avg_recall:.1%} (of actual impacts, this fraction was predicted)",
            f"- **F1 Score**: {avg_f1:.1%} (harmonic mean)",
            f"- **Severity Match**: {avg_severity:.1%} (prediction accuracy for severity levels)",
            f"- **Scenarios Compared**: {len(comparisons)}",
            "",
            "## Per-Scenario Results",
        ]

        for comp in comparisons:
            lines.extend([
                f"### {comp.scenario_id}",
                f"- Precision: {comp.precision:.1%} | Recall: {comp.recall:.1%} | F1: {comp.f1:.1%}",
                f"- Severity Match: {comp.severity_match:.1%}",
            ])
            if comp.predicted_only:
                lines.append(
                    f"- **FaultRay predicted but not observed**: {', '.join(comp.predicted_only)}"
                )
            if comp.observed_only:
                lines.append(
                    f"- **Gremlin observed but FaultRay missed**: {', '.join(comp.observed_only)}"
                )
            if comp.correctly_predicted:
                lines.append(
                    f"- **Correctly predicted**: {', '.join(comp.correctly_predicted)}"
                )
            lines.append("")

        lines.extend([
            "## Recommendations",
            "",
        ])

        if avg_recall < 0.7:
            lines.append(
                "- **Low recall**: FaultRay is missing real impacts. "
                "Review dependency graph completeness and cascade rules."
            )
        if avg_precision < 0.7:
            lines.append(
                "- **Low precision**: FaultRay is over-predicting impacts. "
                "Review circuit breaker and failover configurations."
            )
        if avg_severity < 0.7:
            lines.append(
                "- **Severity mismatch**: Predicted severity differs from observed. "
                "Calibrate component metrics and capacity thresholds."
            )
        if avg_f1 >= 0.8:
            lines.append(
                "- **Good accuracy**: FaultRay predictions align well with Gremlin results. "
                "Simulation model is well-calibrated."
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Recommend next test
    # ------------------------------------------------------------------

    def recommend_next_test(
        self, prediction: PredictionResult,
    ) -> list[str]:
        """Recommend which scenarios to verify next with Gremlin.

        Prioritizes scenarios that:
        1. Have high predicted severity (most dangerous)
        2. Affect many components (widest blast radius)
        3. Involve single points of failure

        Args:
            prediction: A FaultRay prediction result.

        Returns:
            List of recommended Gremlin test descriptions.
        """
        recommendations: list[str] = []

        if prediction.overall_severity >= 7.0:
            recommendations.append(
                f"HIGH PRIORITY: Verify scenario '{prediction.scenario_id}' "
                f"(predicted severity {prediction.overall_severity}/10). "
                "This is a critical risk prediction that should be validated."
            )

        # Check for SPOF components in the prediction
        for comp_id in prediction.affected_components:
            comp = self._graph.get_component(comp_id)
            if comp and comp.replicas <= 1:
                dependents = self._graph.get_dependents(comp_id)
                if len(dependents) > 0:
                    recommendations.append(
                        f"Test SPOF: {comp.name} ({comp_id}) has {len(dependents)} "
                        f"dependent(s) but only 1 replica. Verify cascade behavior."
                    )

        # Suggest testing untested components
        if prediction.cascade_chain:
            for effect in prediction.cascade_chain.effects:
                if effect.health == HealthStatus.DOWN:
                    recommendations.append(
                        f"Verify DOWN prediction for {effect.component_name}: "
                        f"{effect.reason}"
                    )

        if not recommendations:
            recommendations.append(
                f"Scenario '{prediction.scenario_id}' has low predicted severity "
                f"({prediction.overall_severity}/10). Consider testing higher-risk "
                "scenarios first."
            )

        return recommendations

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_attacks(self) -> dict:
        """Fetch attack list from Gremlin API or return mock data."""
        if self._mock:
            logger.debug("Returning mock Gremlin scenarios.")
            return dict(_MOCK_GREMLIN_SCENARIOS)

        try:
            with httpx.Client(
                base_url="https://api.gremlin.com",
                timeout=30,
                headers={
                    "Authorization": f"Key {self._api_key}",
                    "X-Gremlin-Agent": "faultray",
                },
            ) as client:
                resp = client.get(
                    "/v1/attacks",
                    params={"teamId": self._team_id},
                )
                resp.raise_for_status()
                return {"attacks": resp.json()}
        except Exception as exc:
            logger.warning("Gremlin fetch_attacks failed: %s", exc)
            return {"attacks": []}

    def _resolve_target(self, target: str) -> str | None:
        """Resolve a Gremlin target name to an InfraGraph component ID."""
        if not target:
            return None

        # Exact match on ID
        if self._graph.get_component(target):
            return target

        # Match by name or host
        for comp in self._graph.components.values():
            if comp.name.lower() == target.lower():
                return comp.id
            if comp.host and comp.host.lower() == target.lower():
                return comp.id

        return None
