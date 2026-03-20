# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Backtest engine -- validate FaultRay predictions against real incidents."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType

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
    predicted_severity: float        # 0-10 scale from CascadeChain.severity
    predicted_downtime_minutes: float  # estimated downtime
    precision: float  # TP / (TP + FP)
    recall: float  # TP / (TP + FN)
    f1_score: float
    severity_accuracy: float         # 0.0-1.0
    downtime_mae: float              # absolute error in minutes
    prediction_confidence: float     # overall confidence 0.0-1.0
    cascade_chain: CascadeChain | None  # detailed cascade result
    details: dict = field(default_factory=dict)


class BacktestEngine:
    """Run simulations against historical incidents and measure prediction accuracy."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def run_backtest(self, incidents: list[RealIncident]) -> list[BacktestResult]:
        """Run backtest for each incident: simulate via CascadeEngine, compare, compute metrics."""
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
                    predicted_downtime_minutes=0.0,
                    precision=0.0,
                    recall=0.0,
                    f1_score=0.0,
                    severity_accuracy=0.0,
                    downtime_mae=incident.actual_downtime_minutes,
                    prediction_confidence=0.0,
                    cascade_chain=None,
                    details={"skipped": True, "reason": "component_not_found"},
                ))
                continue

            # CascadeEngine simulation
            fault = Fault(
                target_component_id=incident.failed_component,
                fault_type=FaultType.COMPONENT_DOWN,
                severity=1.0,
            )
            cascade_engine = CascadeEngine(self.graph)
            chain = cascade_engine.simulate_fault(fault)

            # Extract predictions from cascade chain
            predicted = [e.component_id for e in chain.effects]
            predicted_list = sorted(set(predicted))
            predicted_severity = chain.severity

            # Estimate downtime from cascade chain
            predicted_downtime = self._estimate_downtime(chain)

            # Precision / Recall / F1
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

            # Severity accuracy
            severity_accuracy = self._calc_severity_accuracy(
                predicted_severity, incident.actual_severity,
            )

            # Downtime MAE
            downtime_mae = abs(predicted_downtime - incident.actual_downtime_minutes)

            # Prediction confidence (weighted average)
            downtime_component = max(0.0, 1.0 - downtime_mae / 60)
            confidence = f1 * 0.5 + severity_accuracy * 0.3 + downtime_component * 0.2

            results.append(BacktestResult(
                incident=incident,
                predicted_affected=predicted_list,
                predicted_severity=round(predicted_severity, 2),
                predicted_downtime_minutes=round(predicted_downtime, 2),
                precision=round(precision, 4),
                recall=round(recall, 4),
                f1_score=round(f1, 4),
                severity_accuracy=round(severity_accuracy, 4),
                downtime_mae=round(downtime_mae, 2),
                prediction_confidence=round(confidence, 4),
                cascade_chain=chain,
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

    def calibrate(self, results: list[BacktestResult]) -> dict[str, float]:
        """Compute calibration adjustments from backtest results.

        Analyses systematic biases in predictions and recommends parameter
        adjustments for the simulation engine.
        """
        if not results:
            return {}

        adjustments: dict[str, float] = {}

        # Downtime bias correction
        downtime_errors = [
            r.predicted_downtime_minutes - r.incident.actual_downtime_minutes
            for r in results
        ]
        avg_error = sum(downtime_errors) / len(downtime_errors)
        if abs(avg_error) > 10:  # 10-minute bias threshold
            adjustments["downtime_bias_correction"] = round(-avg_error, 2)

        # Recall check -- low recall suggests hidden dependencies
        avg_recall = sum(r.recall for r in results) / len(results)
        if avg_recall < 0.7:
            adjustments["dependency_weight_threshold_reduction"] = 0.1

        # Severity bias correction
        severity_errors = [
            r.predicted_severity - self._severity_str_to_float(r.incident.actual_severity)
            for r in results
        ]
        avg_sev_error = sum(severity_errors) / len(severity_errors)
        if abs(avg_sev_error) > 2.0:
            adjustments["severity_bias_correction"] = round(-avg_sev_error, 2)

        return adjustments

    def summary(self, results: list[BacktestResult]) -> dict:
        """Generate an aggregate summary of backtest results."""
        if not results:
            return {"total_incidents": 0, "avg_f1": 0.0}

        n = len(results)
        avg_p = sum(r.precision for r in results) / n
        avg_r = sum(r.recall for r in results) / n
        avg_f1 = sum(r.f1_score for r in results) / n
        avg_sev_acc = sum(r.severity_accuracy for r in results) / n
        avg_dt_mae = sum(r.downtime_mae for r in results) / n
        avg_conf = sum(r.prediction_confidence for r in results) / n

        return {
            "total_incidents": n,
            "avg_precision": round(avg_p, 3),
            "avg_recall": round(avg_r, 3),
            "avg_f1": round(avg_f1, 3),
            "avg_severity_accuracy": round(avg_sev_acc, 3),
            "avg_downtime_mae_minutes": round(avg_dt_mae, 2),
            "avg_confidence": round(avg_conf, 3),
            "calibration": self.calibrate(results),
            "per_incident": [
                {
                    "incident_id": r.incident.incident_id,
                    "component": r.incident.failed_component,
                    "precision": round(r.precision, 3),
                    "recall": round(r.recall, 3),
                    "f1": round(r.f1_score, 3),
                    "severity_accuracy": round(r.severity_accuracy, 3),
                    "downtime_mae": round(r.downtime_mae, 2),
                    "confidence": round(r.prediction_confidence, 3),
                }
                for r in results
            ],
        }

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_downtime(chain: CascadeChain) -> float:
        """Estimate downtime in minutes from a CascadeChain.

        Uses the maximum estimated_time_seconds across all effects as the
        primary estimate, falling back to a heuristic based on the number
        of DOWN components.
        """
        if not chain.effects:
            return 0.0

        from faultray.model.components import HealthStatus

        # Max estimated_time_seconds from cascade effects
        max_time_sec = max(e.estimated_time_seconds for e in chain.effects)

        # Count DOWN components for heuristic fallback
        down_count = sum(
            1 for e in chain.effects if e.health == HealthStatus.DOWN
        )

        if max_time_sec > 0:
            return max_time_sec / 60.0
        elif down_count > 0:
            # Heuristic: each DOWN component adds ~5 minutes of recovery time
            return down_count * 5.0
        else:
            return 0.0

    @staticmethod
    def _severity_str_to_float(s: str) -> float:
        """Map severity string to a 0-10 float scale."""
        mapping = {
            "critical": 9.0,
            "high": 7.0,
            "medium": 5.0,
            "low": 2.0,
        }
        return mapping.get(s.lower(), 5.0)

    def _calc_severity_accuracy(self, predicted: float, actual_str: str) -> float:
        """Compute severity accuracy between predicted (0-10) and actual (string).

        Returns a value between 0.0 and 1.0 where 1.0 means perfect match.
        """
        actual = self._severity_str_to_float(actual_str)
        # Max possible distance is 10.0 (e.g. 0 vs 10)
        distance = abs(predicted - actual)
        return max(0.0, 1.0 - distance / 10.0)

    @staticmethod
    def _calc_prf(
        predicted: list[str], actual: list[str],
    ) -> tuple[float, float, float]:
        """Calculate Precision, Recall, F1 from predicted and actual component lists."""
        actual_set = set(actual)
        predicted_set = set(predicted)

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
        return precision, recall, f1
