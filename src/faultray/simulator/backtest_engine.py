"""Backtest engine -- validate FaultRay predictions against real incidents."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


@dataclass
class RealIncident:
    """A real-world incident record for backtest comparison."""

    incident_id: str
    timestamp: str
    failed_component: str
    actual_affected_components: list[str]
    actual_downtime_minutes: float
    actual_severity: str  # critical/high/medium/low
    root_cause: str = ""
    recovery_actions: list[str] = field(default_factory=list)


@dataclass
class BacktestResult:
    """Result of comparing a simulation prediction against a real incident."""

    incident: RealIncident
    predicted_affected: list[str]
    predicted_severity: float
    precision: float  # TP / (TP + FP)
    recall: float  # TP / (TP + FN)
    f1_score: float
    details: dict = field(default_factory=dict)


class BacktestEngine:
    """Run simulations against historical incidents and measure prediction accuracy."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def run_backtest(self, incidents: list[RealIncident]) -> list[BacktestResult]:
        """Run backtest for each incident: simulate, compare, compute metrics."""
        results: list[BacktestResult] = []
        for incident in incidents:
            # Skip if the failed component is not in the graph
            if incident.failed_component not in self.graph.components:
                logger.warning(
                    "Component %r not found in graph, skipping incident %s",
                    incident.failed_component,
                    incident.incident_id,
                )
                results.append(BacktestResult(
                    incident=incident,
                    predicted_affected=[],
                    predicted_severity=0.0,
                    precision=0.0,
                    recall=0.0,
                    f1_score=0.0,
                    details={"skipped": True, "reason": "component_not_found"},
                ))
                continue

            # Use graph.get_all_affected() to predict cascade impact
            predicted = self.graph.get_all_affected(incident.failed_component)
            predicted_list = sorted(predicted)

            actual_set = set(incident.actual_affected_components)
            predicted_set = set(predicted_list)

            tp = len(actual_set & predicted_set)
            fp = len(predicted_set - actual_set)
            fn = len(actual_set - predicted_set)

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )

            # Predicted severity: fraction of total system affected, scaled 0-10
            total_components = max(len(self.graph.components), 1)
            predicted_severity = len(predicted_list) / total_components * 10

            results.append(BacktestResult(
                incident=incident,
                predicted_affected=predicted_list,
                predicted_severity=round(predicted_severity, 2),
                precision=round(precision, 4),
                recall=round(recall, 4),
                f1_score=round(f1, 4),
                details={
                    "true_positives": sorted(actual_set & predicted_set),
                    "false_positives": sorted(predicted_set - actual_set),
                    "false_negatives": sorted(actual_set - predicted_set),
                },
            ))

        return results

    @staticmethod
    def load_incidents(path: Path) -> list[RealIncident]:
        """Load incidents from a JSON file."""
        data = json.loads(path.read_text())
        return [RealIncident(**inc) for inc in data]

    def summary(self, results: list[BacktestResult]) -> dict:
        """Generate an aggregate summary of backtest results."""
        if not results:
            return {"total_incidents": 0, "avg_f1": 0.0}

        avg_p = sum(r.precision for r in results) / len(results)
        avg_r = sum(r.recall for r in results) / len(results)
        avg_f1 = sum(r.f1_score for r in results) / len(results)

        return {
            "total_incidents": len(results),
            "avg_precision": round(avg_p, 3),
            "avg_recall": round(avg_r, 3),
            "avg_f1": round(avg_f1, 3),
            "results": [
                {
                    "incident_id": r.incident.incident_id,
                    "component": r.incident.failed_component,
                    "precision": round(r.precision, 3),
                    "recall": round(r.recall, 3),
                    "f1": round(r.f1_score, 3),
                }
                for r in results
            ],
        }
