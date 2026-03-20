# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Automated Canary Analysis for Infrastructure Resilience.

Compares resilience metrics between two infrastructure states (before/after)
to detect regressions. Used in CI/CD to validate that infrastructure
changes don't degrade resilience.

Answers: "Did this change make my infrastructure more or less resilient?"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from faultray.model.graph import InfraGraph
from faultray.model.loader import load_yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CanaryMetric:
    """A single metric comparison between baseline and canary."""

    name: str
    baseline_value: float
    canary_value: float
    delta: float
    delta_percent: float
    verdict: str  # "pass", "fail", "marginal"
    threshold: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "baseline_value": round(self.baseline_value, 4),
            "canary_value": round(self.canary_value, 4),
            "delta": round(self.delta, 4),
            "delta_percent": round(self.delta_percent, 2),
            "verdict": self.verdict,
            "threshold": round(self.threshold, 4),
        }


@dataclass
class CanaryResult:
    """Overall result of a canary analysis."""

    overall_verdict: str  # "pass", "fail", "marginal"
    baseline_file: str
    canary_file: str
    metrics: list[CanaryMetric]
    passed_count: int
    failed_count: int
    marginal_count: int
    summary: str
    recommendations: list[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "overall_verdict": self.overall_verdict,
            "baseline_file": self.baseline_file,
            "canary_file": self.canary_file,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "marginal_count": self.marginal_count,
            "summary": self.summary,
            "recommendations": self.recommendations,
            "metrics": [m.to_dict() for m in self.metrics],
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class CanaryConfig:
    """Thresholds for canary analysis."""

    score_threshold: float = 5.0  # max allowed resilience score drop
    spof_threshold: int = 0  # max new SPOFs allowed
    critical_threshold: int = 0  # max new critical findings allowed
    blast_radius_threshold: float = 0.1  # max blast radius increase
    marginal_zone: float = 2.0  # changes within this range are "marginal"


# ---------------------------------------------------------------------------
# Metric extractors
# ---------------------------------------------------------------------------

def _count_spofs(graph: InfraGraph) -> int:
    """Count components that are single points of failure."""
    count = 0
    for comp in graph.components.values():
        dependents = graph.get_dependents(comp.id)
        if comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled:
            count += 1
    return count


def _count_critical_findings(graph: InfraGraph) -> int:
    """Count critical findings (SPOFs + high blast radius components)."""
    spof_count = _count_spofs(graph)
    total = len(graph.components)
    high_blast = 0
    if total > 0:
        for comp in graph.components.values():
            affected = graph.get_all_affected(comp.id)
            if len(affected) / total > 0.5:
                high_blast += 1
    return spof_count + high_blast


def _avg_blast_radius(graph: InfraGraph) -> float:
    """Calculate the average blast radius across all components."""
    total = len(graph.components)
    if total == 0:
        return 0.0
    blast_sum = 0.0
    for comp in graph.components.values():
        affected = graph.get_all_affected(comp.id)
        blast_sum += len(affected) / total
    return blast_sum / total


def _max_dependency_depth(graph: InfraGraph) -> int:
    """Return the length of the longest dependency chain."""
    paths = graph.get_critical_paths()
    if not paths:
        return 0
    return len(paths[0])


def _failover_coverage(graph: InfraGraph) -> float:
    """Percentage of components with failover enabled."""
    if not graph.components:
        return 100.0
    with_failover = sum(1 for c in graph.components.values() if c.failover.enabled)
    return (with_failover / len(graph.components)) * 100.0


def _circuit_breaker_coverage(graph: InfraGraph) -> float:
    """Percentage of dependency edges with circuit breakers enabled."""
    edges = graph.all_dependency_edges()
    if not edges:
        return 100.0
    cb_enabled = sum(1 for e in edges if e.circuit_breaker.enabled)
    return (cb_enabled / len(edges)) * 100.0


def _autoscaling_coverage(graph: InfraGraph) -> float:
    """Percentage of components with autoscaling enabled."""
    if not graph.components:
        return 100.0
    with_as = sum(1 for c in graph.components.values() if c.autoscaling.enabled)
    return (with_as / len(graph.components)) * 100.0


# ---------------------------------------------------------------------------
# Canary Analyzer
# ---------------------------------------------------------------------------

class CanaryAnalyzer:
    """Compares two infrastructure states and produces a canary analysis."""

    def analyze(
        self,
        baseline_yaml: Path,
        canary_yaml: Path,
        config: CanaryConfig | None = None,
    ) -> CanaryResult:
        """Compare two YAML infrastructure definitions.

        Args:
            baseline_yaml: Path to the baseline (before) infrastructure YAML.
            canary_yaml: Path to the canary (after) infrastructure YAML.
            config: Optional thresholds for pass/fail/marginal verdicts.

        Returns:
            A :class:`CanaryResult` with per-metric comparisons.
        """
        if not baseline_yaml.exists():
            raise FileNotFoundError(f"Baseline file not found: {baseline_yaml}")
        if not canary_yaml.exists():
            raise FileNotFoundError(f"Canary file not found: {canary_yaml}")

        baseline = load_yaml(baseline_yaml)
        canary = load_yaml(canary_yaml)

        result = self.analyze_graphs(
            baseline, canary,
            config=config,
            baseline_file=str(baseline_yaml),
            canary_file=str(canary_yaml),
        )
        return result

    def analyze_graphs(
        self,
        baseline: InfraGraph,
        canary: InfraGraph,
        config: CanaryConfig | None = None,
        baseline_file: str = "<baseline>",
        canary_file: str = "<canary>",
    ) -> CanaryResult:
        """Compare two InfraGraph instances directly.

        Args:
            baseline: The baseline (before) graph.
            canary: The canary (after) graph.
            config: Optional thresholds.
            baseline_file: Label for the baseline source.
            canary_file: Label for the canary source.

        Returns:
            A :class:`CanaryResult` with per-metric comparisons.
        """
        if config is None:
            config = CanaryConfig()

        metrics: list[CanaryMetric] = []
        recommendations: list[str] = []

        # 1. Resilience Score
        b_score = baseline.resilience_score()
        c_score = canary.resilience_score()
        metrics.append(self._make_metric(
            "resilience_score", b_score, c_score,
            threshold=config.score_threshold,
            marginal_zone=config.marginal_zone,
            higher_is_better=True,
        ))

        # 2. SPOF Count
        b_spof = float(_count_spofs(baseline))
        c_spof = float(_count_spofs(canary))
        metrics.append(self._make_metric(
            "spof_count", b_spof, c_spof,
            threshold=float(config.spof_threshold),
            marginal_zone=0.0,
            higher_is_better=False,
        ))

        # 3. Critical Findings
        b_crit = float(_count_critical_findings(baseline))
        c_crit = float(_count_critical_findings(canary))
        metrics.append(self._make_metric(
            "critical_findings", b_crit, c_crit,
            threshold=float(config.critical_threshold),
            marginal_zone=0.0,
            higher_is_better=False,
        ))

        # 4. Average Blast Radius
        b_blast = _avg_blast_radius(baseline)
        c_blast = _avg_blast_radius(canary)
        metrics.append(self._make_metric(
            "avg_blast_radius", b_blast, c_blast,
            threshold=config.blast_radius_threshold,
            marginal_zone=config.blast_radius_threshold * 0.5,
            higher_is_better=False,
        ))

        # 5. Component Count
        b_comp = float(len(baseline.components))
        c_comp = float(len(canary.components))
        metrics.append(self._make_metric(
            "component_count", b_comp, c_comp,
            threshold=float("inf"),  # informational
            marginal_zone=0.0,
            higher_is_better=True,
            informational=True,
        ))

        # 6. Dependency Depth
        b_depth = float(_max_dependency_depth(baseline))
        c_depth = float(_max_dependency_depth(canary))
        metrics.append(self._make_metric(
            "dependency_depth", b_depth, c_depth,
            threshold=2.0,
            marginal_zone=1.0,
            higher_is_better=False,
        ))

        # 7. Failover Coverage %
        b_fo = _failover_coverage(baseline)
        c_fo = _failover_coverage(canary)
        metrics.append(self._make_metric(
            "failover_coverage", b_fo, c_fo,
            threshold=10.0,
            marginal_zone=5.0,
            higher_is_better=True,
        ))

        # 8. Circuit Breaker Coverage %
        b_cb = _circuit_breaker_coverage(baseline)
        c_cb = _circuit_breaker_coverage(canary)
        metrics.append(self._make_metric(
            "circuit_breaker_coverage", b_cb, c_cb,
            threshold=10.0,
            marginal_zone=5.0,
            higher_is_better=True,
        ))

        # 9. Autoscaling Coverage %
        b_as = _autoscaling_coverage(baseline)
        c_as = _autoscaling_coverage(canary)
        metrics.append(self._make_metric(
            "autoscaling_coverage", b_as, c_as,
            threshold=10.0,
            marginal_zone=5.0,
            higher_is_better=True,
        ))

        # --- Aggregate verdicts ---
        passed_count = sum(1 for m in metrics if m.verdict == "pass")
        failed_count = sum(1 for m in metrics if m.verdict == "fail")
        marginal_count = sum(1 for m in metrics if m.verdict == "marginal")

        if failed_count > 0:
            overall = "fail"
        elif marginal_count > 0:
            overall = "marginal"
        else:
            overall = "pass"

        # --- Recommendations ---
        for m in metrics:
            if m.verdict == "fail":
                recommendations.append(
                    f"{m.name}: degraded from {m.baseline_value:.2f} to "
                    f"{m.canary_value:.2f} (delta: {m.delta:+.2f}). "
                    f"This exceeds the threshold of {m.threshold:.2f}."
                )
            elif m.verdict == "marginal":
                recommendations.append(
                    f"{m.name}: slight change from {m.baseline_value:.2f} to "
                    f"{m.canary_value:.2f} (delta: {m.delta:+.2f}). "
                    f"Monitor closely."
                )

        # --- Summary ---
        if overall == "pass":
            summary = (
                f"Canary analysis PASSED. Infrastructure resilience is maintained "
                f"or improved ({passed_count}/{len(metrics)} metrics passed)."
            )
        elif overall == "fail":
            summary = (
                f"Canary analysis FAILED. {failed_count} metric(s) show resilience "
                f"regression exceeding thresholds."
            )
        else:
            summary = (
                f"Canary analysis MARGINAL. {marginal_count} metric(s) show changes "
                f"within the marginal zone. Review recommended."
            )

        return CanaryResult(
            overall_verdict=overall,
            baseline_file=baseline_file,
            canary_file=canary_file,
            metrics=metrics,
            passed_count=passed_count,
            failed_count=failed_count,
            marginal_count=marginal_count,
            summary=summary,
            recommendations=recommendations,
        )

    def quick_compare(
        self,
        baseline_yaml: Path,
        canary_yaml: Path,
    ) -> str:
        """Return a one-line summary comparing two infrastructure files."""
        result = self.analyze(baseline_yaml, canary_yaml)
        score_metric = next(
            (m for m in result.metrics if m.name == "resilience_score"), None,
        )
        score_info = ""
        if score_metric:
            score_info = (
                f" (score: {score_metric.baseline_value:.1f} -> "
                f"{score_metric.canary_value:.1f}, "
                f"delta: {score_metric.delta:+.1f})"
            )
        return f"{result.overall_verdict.upper()}{score_info}"

    # ---- Helpers -----------------------------------------------------------

    @staticmethod
    def _make_metric(
        name: str,
        baseline: float,
        canary: float,
        threshold: float,
        marginal_zone: float,
        higher_is_better: bool,
        informational: bool = False,
    ) -> CanaryMetric:
        """Build a :class:`CanaryMetric` with automatic verdict."""
        delta = canary - baseline
        if baseline != 0:
            delta_percent = (delta / abs(baseline)) * 100.0
        else:
            delta_percent = 0.0 if delta == 0 else (100.0 if delta > 0 else -100.0)

        if informational:
            verdict = "pass"
        elif higher_is_better:
            # Degradation = score DROP exceeds threshold
            degradation = -delta  # positive means we dropped
            if degradation > threshold:
                verdict = "fail"
            elif degradation > marginal_zone:
                verdict = "marginal"
            else:
                verdict = "pass"
        else:
            # Degradation = value INCREASE exceeds threshold
            degradation = delta  # positive means it grew (bad)
            if degradation > threshold:
                verdict = "fail"
            elif degradation > marginal_zone:
                verdict = "marginal"
            else:
                verdict = "pass"

        return CanaryMetric(
            name=name,
            baseline_value=baseline,
            canary_value=canary,
            delta=delta,
            delta_percent=delta_percent,
            verdict=verdict,
            threshold=threshold,
        )
