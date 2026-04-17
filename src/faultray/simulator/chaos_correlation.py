# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Chaos Correlation Engine.

Analyzes results from multiple chaos experiments to discover hidden
dependencies, emergent failure patterns, and cross-experiment correlations
that aren't visible from individual tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from itertools import combinations

from pydantic import BaseModel, Field


class CorrelationType(str, Enum):
    """Type of correlation between two chaos experiments."""

    CAUSAL = "causal"
    TEMPORAL = "temporal"
    AMPLIFYING = "amplifying"
    MASKING = "masking"
    INDEPENDENT = "independent"


class ExperimentResult(BaseModel):
    """Result of a single chaos experiment."""

    experiment_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    target_component: str
    failure_type: str
    severity: float = Field(ge=0.0, le=1.0)
    affected_components: list[str] = Field(default_factory=list)
    impact_score: float = Field(ge=0.0, le=100.0)
    recovery_time_seconds: float = Field(ge=0.0)
    success: bool = True


class Correlation(BaseModel):
    """A discovered correlation between two experiments."""

    source_experiment: str
    target_experiment: str
    correlation_type: CorrelationType
    strength: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    description: str = ""


class HiddenDependency(BaseModel):
    """A hidden dependency discovered from experiment results."""

    component_a: str
    component_b: str
    evidence_count: int = 0
    correlation_strength: float = Field(ge=0.0, le=1.0)
    discovery_method: str = ""


class EmergentPattern(BaseModel):
    """An emergent failure pattern discovered across experiments."""

    pattern_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    description: str = ""
    involved_experiments: list[str] = Field(default_factory=list)
    frequency: int = 0
    risk_multiplier: float = 1.0
    recommended_action: str = ""


class CorrelationReport(BaseModel):
    """Complete correlation analysis report."""

    correlations: list[Correlation] = Field(default_factory=list)
    hidden_dependencies: list[HiddenDependency] = Field(default_factory=list)
    emergent_patterns: list[EmergentPattern] = Field(default_factory=list)
    total_experiments_analyzed: int = 0
    coverage_score: float = Field(ge=0.0, le=100.0, default=0.0)


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    return len(set_a & set_b) / len(union)


def _overlap_ratio(set_a: set[str], set_b: set[str]) -> float:
    """Compute overlap ratio (intersection / min size)."""
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / min(len(set_a), len(set_b))


class ChaosCorrelationEngine:
    """Engine for analyzing correlations across chaos experiments."""

    OVERLAP_THRESHOLD = 0.3
    JACCARD_THRESHOLD = 0.4

    def __init__(self) -> None:
        self._results: list[ExperimentResult] = []

    @property
    def results(self) -> list[ExperimentResult]:
        """Return all stored experiment results."""
        return list(self._results)

    def add_result(self, result: ExperimentResult) -> None:
        """Add a single experiment result."""
        self._results.append(result)

    def add_results(self, results: list[ExperimentResult]) -> None:
        """Add a batch of experiment results."""
        self._results.extend(results)

    def _determine_correlation_type(
        self, a: ExperimentResult, b: ExperimentResult
    ) -> CorrelationType:
        """Determine the correlation type between two experiments."""
        affected_a = set(a.affected_components)
        affected_b = set(b.affected_components)

        # Same target component suggests causal relationship
        if a.target_component == b.target_component:
            return CorrelationType.CAUSAL

        # If one experiment's affected components contain the other's target,
        # the first masks the second
        if b.target_component in affected_a and a.target_component not in affected_b:
            return CorrelationType.MASKING
        if a.target_component in affected_b and b.target_component not in affected_a:
            return CorrelationType.MASKING

        # If one experiment has higher impact when both share affected components
        if a.impact_score > b.impact_score * 1.5 or b.impact_score > a.impact_score * 1.5:
            return CorrelationType.AMPLIFYING

        # Same affected components suggest temporal correlation
        if affected_a == affected_b and affected_a:
            return CorrelationType.TEMPORAL

        # Default: if overlap exists but no special pattern, temporal
        return CorrelationType.TEMPORAL

    def find_correlations(self) -> list[Correlation]:
        """Discover correlations between experiments."""
        correlations: list[Correlation] = []

        if len(self._results) < 2:
            return correlations

        for a, b in combinations(self._results, 2):
            affected_a = set(a.affected_components)
            affected_b = set(b.affected_components)

            overlap = _overlap_ratio(affected_a, affected_b)

            if overlap < self.OVERLAP_THRESHOLD:
                continue

            corr_type = self._determine_correlation_type(a, b)
            strength = min(1.0, overlap)
            confidence = min(1.0, (overlap + 0.5 * min(a.severity, b.severity)))

            description = (
                f"{corr_type.value} correlation between "
                f"{a.experiment_id} and {b.experiment_id}: "
                f"overlap={overlap:.2f}"
            )

            correlations.append(
                Correlation(
                    source_experiment=a.experiment_id,
                    target_experiment=b.experiment_id,
                    correlation_type=corr_type,
                    strength=strength,
                    confidence=min(1.0, confidence),
                    description=description,
                )
            )

        return correlations

    def discover_hidden_dependencies(self) -> list[HiddenDependency]:
        """Find hidden dependencies from affected component overlap patterns."""
        if len(self._results) < 2:
            return []

        # Collect all pairs of components that appear together
        pair_counts: dict[tuple[str, str], int] = {}
        pair_experiments: dict[tuple[str, str], list[str]] = {}

        for result in self._results:
            components = sorted(set(result.affected_components))
            for i, comp_a in enumerate(components):
                for comp_b in components[i + 1 :]:
                    pair = (comp_a, comp_b)
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1
                    if pair not in pair_experiments:
                        pair_experiments[pair] = []
                    pair_experiments[pair].append(result.experiment_id)

        # Build component occurrence sets for Jaccard calculation
        component_experiments: dict[str, set[str]] = {}
        for result in self._results:
            for comp in result.affected_components:
                if comp not in component_experiments:
                    component_experiments[comp] = set()
                component_experiments[comp].add(result.experiment_id)

        dependencies: list[HiddenDependency] = []

        for (comp_a, comp_b), count in pair_counts.items():
            if count < 2:
                continue

            exps_a = component_experiments.get(comp_a, set())
            exps_b = component_experiments.get(comp_b, set())
            jaccard = _jaccard_similarity(exps_a, exps_b)

            if jaccard >= self.JACCARD_THRESHOLD:
                dependencies.append(
                    HiddenDependency(
                        component_a=comp_a,
                        component_b=comp_b,
                        evidence_count=count,
                        correlation_strength=min(1.0, jaccard),
                        discovery_method="jaccard_co_occurrence",
                    )
                )

        return dependencies

    def detect_emergent_patterns(self) -> list[EmergentPattern]:
        """Detect emergent failure patterns across experiments."""
        if len(self._results) < 2:
            return []

        patterns: list[EmergentPattern] = []

        # Pattern 1: Cascade failure — experiments where affected count is high
        cascade_experiments = [
            r for r in self._results if len(r.affected_components) >= 3
        ]
        if len(cascade_experiments) >= 2:
            avg_impact = sum(r.impact_score for r in cascade_experiments) / len(
                cascade_experiments
            )
            patterns.append(
                EmergentPattern(
                    name="cascade_failure",
                    description=(
                        "Multiple experiments show cascade behavior "
                        "affecting 3+ components"
                    ),
                    involved_experiments=[r.experiment_id for r in cascade_experiments],
                    frequency=len(cascade_experiments),
                    risk_multiplier=1.0 + avg_impact / 100.0,
                    recommended_action="Implement circuit breakers between tightly coupled components",
                )
            )

        # Pattern 2: Split-brain — experiments targeting different components
        # but with overlapping affected sets
        target_groups: dict[str, list[ExperimentResult]] = {}
        for r in self._results:
            if r.target_component not in target_groups:
                target_groups[r.target_component] = []
            target_groups[r.target_component].append(r)

        if len(target_groups) >= 2:
            targets = list(target_groups.keys())
            for i, t1 in enumerate(targets):
                for t2 in targets[i + 1 :]:
                    for r1 in target_groups[t1]:
                        for r2 in target_groups[t2]:
                            a_set = set(r1.affected_components)
                            b_set = set(r2.affected_components)
                            if a_set and b_set and a_set & b_set:
                                patterns.append(
                                    EmergentPattern(
                                        name="split_brain",
                                        description=(
                                            f"Components {t1} and {t2} failures "
                                            f"both affect shared components"
                                        ),
                                        involved_experiments=[
                                            r1.experiment_id,
                                            r2.experiment_id,
                                        ],
                                        frequency=1,
                                        risk_multiplier=1.5,
                                        recommended_action=(
                                            "Add consensus protocol or leader election "
                                            "to prevent split-brain scenarios"
                                        ),
                                    )
                                )

        # Pattern 3: Thundering herd — multiple experiments with high impact
        # and fast recovery (indicates retry storms)
        herd_experiments = [
            r
            for r in self._results
            if r.impact_score >= 50.0 and r.recovery_time_seconds <= 30.0
        ]
        if len(herd_experiments) >= 2:
            patterns.append(
                EmergentPattern(
                    name="thundering_herd",
                    description=(
                        "Multiple high-impact experiments with fast recovery "
                        "suggest retry storm potential"
                    ),
                    involved_experiments=[r.experiment_id for r in herd_experiments],
                    frequency=len(herd_experiments),
                    risk_multiplier=2.0,
                    recommended_action="Implement exponential backoff and jitter for retries",
                )
            )

        return patterns

    def calculate_coverage(self, all_components: list[str]) -> float:
        """Calculate chaos test coverage as a percentage."""
        if not all_components:
            return 0.0

        all_set = set(all_components)
        tested: set[str] = set()

        for result in self._results:
            tested.add(result.target_component)
            tested.update(result.affected_components)

        covered = tested & all_set
        return (len(covered) / len(all_set)) * 100.0

    def generate_report(self, all_components: list[str]) -> CorrelationReport:
        """Generate a full correlation analysis report."""
        correlations = self.find_correlations()
        hidden_deps = self.discover_hidden_dependencies()
        patterns = self.detect_emergent_patterns()
        coverage = self.calculate_coverage(all_components)

        return CorrelationReport(
            correlations=correlations,
            hidden_dependencies=hidden_deps,
            emergent_patterns=patterns,
            total_experiments_analyzed=len(self._results),
            coverage_score=coverage,
        )
