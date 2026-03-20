# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Blast Radius Predictor - predicts the blast radius of component failures.

Uses graph-based BFS traversal and statistical modeling to predict how
component failures cascade through the infrastructure dependency graph.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from faultray.model.graph import InfraGraph


class PredictionConfidence(str, Enum):
    """Confidence level of a blast radius prediction."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ImpactLevel(str, Enum):
    """Severity level of impact on a component."""

    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    CATASTROPHIC = "catastrophic"


@dataclass
class ComponentImpact:
    """Predicted impact on a single component from a failure."""

    component_id: str
    component_name: str
    impact_level: ImpactLevel
    impact_probability: float
    estimated_degradation_percent: float
    time_to_impact_seconds: int
    recovery_dependency: list[str] = field(default_factory=list)


@dataclass
class BlastPrediction:
    """Complete blast radius prediction for a component failure."""

    source_component_id: str
    source_component_name: str
    predicted_impacts: list[ComponentImpact] = field(default_factory=list)
    blast_radius_score: float = 0.0
    confidence: PredictionConfidence = PredictionConfidence.MEDIUM
    max_cascade_depth: int = 0
    affected_component_count: int = 0
    affected_users_estimate: str = "unknown"
    mitigation_suggestions: list[str] = field(default_factory=list)


@dataclass
class WhatIfResult:
    """Result of a what-if analysis comparing baseline vs modified prediction."""

    scenario_description: str
    predictions: list[BlastPrediction] = field(default_factory=list)
    comparison_baseline: BlastPrediction | None = None
    delta_summary: str = ""


@dataclass
class RiskHotspot:
    """A component identified as a risk hotspot."""

    component_id: str
    component_name: str
    outgoing_blast_radius: float = 0.0
    incoming_vulnerability: float = 0.0
    combined_risk_score: float = 0.0
    risk_factors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default probability decay factor per BFS level
_DEFAULT_DECAY_FACTOR = 0.8

# Propagation delay per cascade level (seconds)
_PROPAGATION_DELAY_SECONDS = 15

# Maximum BFS depth
_MAX_BFS_DEPTH = 20


class BlastPredictor:
    """Predicts the blast radius of component failures using graph analysis.

    The predictor uses BFS traversal from the failed component through
    dependency edges, calculating impact probability with decay based on
    distance, redundancy, and load factors.
    """

    def __init__(
        self,
        decay_factor: float = _DEFAULT_DECAY_FACTOR,
        propagation_delay: int = _PROPAGATION_DELAY_SECONDS,
    ) -> None:
        self._decay_factor = decay_factor
        self._propagation_delay = propagation_delay

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, graph: InfraGraph, component_id: str) -> BlastPrediction:
        """Predict blast radius for a single component failure.

        Args:
            graph: The infrastructure dependency graph.
            component_id: ID of the component that fails.

        Returns:
            A BlastPrediction describing the predicted impact.
        """
        source = graph.get_component(component_id)
        if source is None:
            return BlastPrediction(
                source_component_id=component_id,
                source_component_name="unknown",
            )

        impacts: list[ComponentImpact] = []
        max_depth = 0

        # BFS from the failed component through dependents (upstream impact)
        # Queue entries: (component_id, current_probability, depth)
        visited: set[str] = {component_id}
        queue: deque[tuple[str, float, int]] = deque()

        # Seed the queue with components that depend ON the failed component
        for dep_comp in graph.get_dependents(component_id):
            if dep_comp.id not in visited:
                edge = graph.get_dependency_edge(dep_comp.id, component_id)
                edge_weight = edge.weight if edge else 1.0
                dep_type = edge.dependency_type if edge else "requires"
                initial_prob = self._initial_impact_probability(
                    edge_weight, dep_type
                )
                queue.append((dep_comp.id, initial_prob, 1))
                visited.add(dep_comp.id)

        while queue:
            comp_id, current_prob, depth = queue.popleft()
            if depth > _MAX_BFS_DEPTH:
                continue

            comp = graph.get_component(comp_id)
            if comp is None:
                continue

            # Calculate target resilience from redundancy, failover, load
            target_resilience = self._component_resilience(comp)

            # Decay probability
            prob = current_prob * self._decay_factor * (1.0 - target_resilience)
            prob = max(0.0, min(1.0, prob))

            if prob < 0.01:
                # Probability too low to matter
                continue

            # Determine impact level
            edge = graph.get_dependency_edge(comp_id, component_id)
            dep_criticality = edge.weight if edge else 0.5
            impact_level = self._classify_impact(prob, dep_criticality)

            if impact_level == ImpactLevel.NONE:
                continue

            degradation = self._estimate_degradation(prob, impact_level)
            time_to_impact = depth * self._propagation_delay

            # Recovery dependencies: the source + any other dependencies
            recovery_deps = [component_id]

            impact = ComponentImpact(
                component_id=comp_id,
                component_name=comp.name,
                impact_level=impact_level,
                impact_probability=round(prob, 4),
                estimated_degradation_percent=round(degradation, 1),
                time_to_impact_seconds=time_to_impact,
                recovery_dependency=recovery_deps,
            )
            impacts.append(impact)

            if depth > max_depth:
                max_depth = depth

            # Continue BFS to next level
            for next_dep in graph.get_dependents(comp_id):
                if next_dep.id not in visited:
                    next_edge = graph.get_dependency_edge(next_dep.id, comp_id)
                    next_weight = next_edge.weight if next_edge else 1.0
                    next_dep_type = (
                        next_edge.dependency_type if next_edge else "requires"
                    )
                    next_prob = prob * self._initial_impact_probability(
                        next_weight, next_dep_type
                    )
                    queue.append((next_dep.id, next_prob, depth + 1))
                    visited.add(next_dep.id)

        # Calculate blast radius score
        blast_score = self._calculate_blast_score(impacts, max_depth)

        # Determine confidence
        confidence = self._determine_confidence(graph, component_id, impacts)

        # Estimate affected users
        affected_users = self._estimate_affected_users(impacts)

        # Generate mitigation suggestions
        suggestions = self._generate_mitigations(
            graph, component_id, impacts
        )

        return BlastPrediction(
            source_component_id=component_id,
            source_component_name=source.name,
            predicted_impacts=impacts,
            blast_radius_score=round(blast_score, 1),
            confidence=confidence,
            max_cascade_depth=max_depth,
            affected_component_count=len(impacts),
            affected_users_estimate=affected_users,
            mitigation_suggestions=suggestions,
        )

    def predict_all(
        self, graph: InfraGraph
    ) -> dict[str, BlastPrediction]:
        """Predict blast radius for all components in the graph.

        Args:
            graph: The infrastructure dependency graph.

        Returns:
            Dictionary mapping component_id -> BlastPrediction.
        """
        results: dict[str, BlastPrediction] = {}
        for comp_id in graph.components:
            results[comp_id] = self.predict(graph, comp_id)
        return results

    def what_if(
        self,
        graph: InfraGraph,
        component_id: str,
        change: dict,
    ) -> WhatIfResult:
        """Run a what-if analysis: what happens if we change a component?

        Supported changes:
            - replicas: int  (change replica count)
            - failover_enabled: bool
            - autoscaling_enabled: bool
            - current_cpu_percent: float
            - current_memory_percent: float

        Args:
            graph: The infrastructure dependency graph.
            component_id: ID of the component to modify.
            change: Dictionary of property changes.

        Returns:
            WhatIfResult with baseline and modified predictions.
        """
        # Baseline prediction
        baseline = self.predict(graph, component_id)

        # Clone the graph and apply changes
        modified_graph = self._clone_graph(graph)
        comp = modified_graph.get_component(component_id)
        if comp is None:
            return WhatIfResult(
                scenario_description=f"Component {component_id} not found",
                predictions=[baseline],
                comparison_baseline=baseline,
                delta_summary="No change - component not found",
            )

        # Apply changes
        change_descriptions: list[str] = []
        if "replicas" in change:
            old_val = comp.replicas
            new_val = max(1, int(change["replicas"]))
            comp.replicas = new_val
            change_descriptions.append(
                f"replicas: {old_val} -> {new_val}"
            )
        if "failover_enabled" in change:
            old_val = comp.failover.enabled
            comp.failover.enabled = bool(change["failover_enabled"])
            change_descriptions.append(
                f"failover: {old_val} -> {comp.failover.enabled}"
            )
        if "autoscaling_enabled" in change:
            old_val = comp.autoscaling.enabled
            comp.autoscaling.enabled = bool(change["autoscaling_enabled"])
            change_descriptions.append(
                f"autoscaling: {old_val} -> {comp.autoscaling.enabled}"
            )
        if "current_cpu_percent" in change:
            old_val = comp.metrics.cpu_percent
            comp.metrics.cpu_percent = float(change["current_cpu_percent"])
            change_descriptions.append(
                f"cpu: {old_val:.0f}% -> {comp.metrics.cpu_percent:.0f}%"
            )
        if "current_memory_percent" in change:
            old_val = comp.metrics.memory_percent
            comp.metrics.memory_percent = float(
                change["current_memory_percent"]
            )
            change_descriptions.append(
                f"memory: {old_val:.0f}% -> {comp.metrics.memory_percent:.0f}%"
            )

        scenario_desc = (
            f"What-if: {', '.join(change_descriptions)} "
            f"on {comp.name}"
        )

        # Re-predict with modified graph
        modified_prediction = self.predict(modified_graph, component_id)

        # Build delta summary
        delta = self._build_delta_summary(
            baseline, modified_prediction, change_descriptions, comp.name
        )

        return WhatIfResult(
            scenario_description=scenario_desc,
            predictions=[modified_prediction],
            comparison_baseline=baseline,
            delta_summary=delta,
        )

    def find_hotspots(
        self, graph: InfraGraph, top_n: int = 10
    ) -> list[RiskHotspot]:
        """Find the highest-risk components in the infrastructure.

        Risk is determined by combining:
        - Outgoing blast radius: how much damage this component's failure causes
        - Incoming vulnerability: how many failure paths lead to this component

        Args:
            graph: The infrastructure dependency graph.
            top_n: Number of top hotspots to return.

        Returns:
            List of RiskHotspot sorted by combined_risk_score descending.
        """
        hotspots: list[RiskHotspot] = []

        for comp_id, comp in graph.components.items():
            # Outgoing blast radius
            prediction = self.predict(graph, comp_id)
            outgoing = prediction.blast_radius_score

            # Incoming vulnerability: how many components can cause this to fail
            incoming = self._calculate_incoming_vulnerability(graph, comp_id)

            # Combined risk
            combined = outgoing * 0.6 + incoming * 0.4

            # Identify risk factors
            risk_factors = self._identify_risk_factors(graph, comp, prediction)

            hotspots.append(
                RiskHotspot(
                    component_id=comp_id,
                    component_name=comp.name,
                    outgoing_blast_radius=round(outgoing, 1),
                    incoming_vulnerability=round(incoming, 1),
                    combined_risk_score=round(combined, 1),
                    risk_factors=risk_factors,
                )
            )

        # Sort by combined risk score descending
        hotspots.sort(key=lambda h: h.combined_risk_score, reverse=True)
        return hotspots[:top_n]

    def compare_predictions(
        self,
        pred_a: BlastPrediction,
        pred_b: BlastPrediction,
    ) -> dict:
        """Compare two blast predictions.

        Args:
            pred_a: First prediction.
            pred_b: Second prediction.

        Returns:
            Dictionary with comparison metrics.
        """
        score_delta = pred_b.blast_radius_score - pred_a.blast_radius_score
        count_delta = (
            pred_b.affected_component_count - pred_a.affected_component_count
        )
        depth_delta = pred_b.max_cascade_depth - pred_a.max_cascade_depth

        # Impact level distribution
        dist_a = self._impact_distribution(pred_a)
        dist_b = self._impact_distribution(pred_b)

        # Components only in A, only in B, in both
        ids_a = {i.component_id for i in pred_a.predicted_impacts}
        ids_b = {i.component_id for i in pred_b.predicted_impacts}

        return {
            "blast_radius_score_delta": round(score_delta, 1),
            "affected_component_count_delta": count_delta,
            "max_cascade_depth_delta": depth_delta,
            "pred_a_score": pred_a.blast_radius_score,
            "pred_b_score": pred_b.blast_radius_score,
            "pred_a_confidence": pred_a.confidence.value,
            "pred_b_confidence": pred_b.confidence.value,
            "impact_distribution_a": dist_a,
            "impact_distribution_b": dist_b,
            "components_only_in_a": sorted(ids_a - ids_b),
            "components_only_in_b": sorted(ids_b - ids_a),
            "components_in_both": sorted(ids_a & ids_b),
            "improved": score_delta < 0,
        }

    def generate_heatmap_data(self, graph: InfraGraph) -> list[dict]:
        """Generate data suitable for heatmap visualization.

        Each entry represents a component with its risk metrics.

        Args:
            graph: The infrastructure dependency graph.

        Returns:
            List of dicts with component risk data for heatmap rendering.
        """
        predictions = self.predict_all(graph)
        heatmap: list[dict] = []

        for comp_id, comp in graph.components.items():
            pred = predictions[comp_id]
            incoming = self._calculate_incoming_vulnerability(graph, comp_id)

            heatmap.append(
                {
                    "component_id": comp_id,
                    "component_name": comp.name,
                    "component_type": comp.type.value,
                    "blast_radius_score": pred.blast_radius_score,
                    "affected_component_count": pred.affected_component_count,
                    "max_cascade_depth": pred.max_cascade_depth,
                    "incoming_vulnerability": round(incoming, 1),
                    "replicas": comp.replicas,
                    "failover_enabled": comp.failover.enabled,
                    "autoscaling_enabled": comp.autoscaling.enabled,
                    "current_utilization": round(comp.utilization(), 1),
                    "confidence": pred.confidence.value,
                    "risk_level": self._risk_level_label(
                        pred.blast_radius_score
                    ),
                }
            )

        # Sort by blast_radius_score descending
        heatmap.sort(key=lambda h: h["blast_radius_score"], reverse=True)
        return heatmap

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _initial_impact_probability(
        edge_weight: float, dependency_type: str
    ) -> float:
        """Calculate the initial impact probability based on edge properties."""
        if dependency_type == "optional":
            return edge_weight * 0.3
        if dependency_type == "async":
            return edge_weight * 0.2
        # "requires" or unknown
        return edge_weight

    @staticmethod
    def _component_resilience(comp) -> float:
        """Calculate a component's resilience factor (0.0 to <1.0).

        Higher resilience means the component is more likely to absorb
        the failure without cascading.
        """
        resilience = 0.0

        # Redundancy from replicas
        if comp.replicas >= 3:
            resilience += 0.4
        elif comp.replicas >= 2:
            resilience += 0.25

        # Failover
        if comp.failover.enabled:
            resilience += 0.2

        # Autoscaling
        if comp.autoscaling.enabled:
            resilience += 0.1

        # Load factor: high load reduces resilience
        utilization = comp.utilization()
        if utilization > 80:
            resilience -= 0.15
        elif utilization > 60:
            resilience -= 0.05

        # Clamp to [0.0, 0.95) to ensure some probability always passes
        return max(0.0, min(0.95, resilience))

    @staticmethod
    def _classify_impact(
        probability: float, criticality: float
    ) -> ImpactLevel:
        """Classify the impact level based on probability and criticality."""
        score = probability * criticality

        if score >= 0.7:
            return ImpactLevel.CATASTROPHIC
        if score >= 0.5:
            return ImpactLevel.SEVERE
        if score >= 0.3:
            return ImpactLevel.MODERATE
        if score >= 0.1:
            return ImpactLevel.MINOR
        return ImpactLevel.NONE

    @staticmethod
    def _estimate_degradation(
        probability: float, impact_level: ImpactLevel
    ) -> float:
        """Estimate the degradation percentage based on probability and level."""
        base_degradation = {
            ImpactLevel.CATASTROPHIC: 90.0,
            ImpactLevel.SEVERE: 70.0,
            ImpactLevel.MODERATE: 40.0,
            ImpactLevel.MINOR: 15.0,
            ImpactLevel.NONE: 0.0,
        }
        return base_degradation.get(impact_level, 0.0) * probability

    @staticmethod
    def _calculate_blast_score(
        impacts: list[ComponentImpact], max_depth: int
    ) -> float:
        """Calculate the blast radius score on a 0-100 scale.

        Formula:
            score = min(100,
                (severe_count * 25 + moderate_count * 10 + minor_count * 3)
                * depth_multiplier)
        """
        severe_count = sum(
            1
            for i in impacts
            if i.impact_level in (ImpactLevel.CATASTROPHIC, ImpactLevel.SEVERE)
        )
        moderate_count = sum(
            1 for i in impacts if i.impact_level == ImpactLevel.MODERATE
        )
        minor_count = sum(
            1 for i in impacts if i.impact_level == ImpactLevel.MINOR
        )

        depth_multiplier = 1.0 + max_depth * 0.15
        raw = (severe_count * 25 + moderate_count * 10 + minor_count * 3)
        score = raw * depth_multiplier

        return min(100.0, score)

    @staticmethod
    def _determine_confidence(
        graph: InfraGraph,
        component_id: str,
        impacts: list[ComponentImpact],
    ) -> PredictionConfidence:
        """Determine the prediction confidence level.

        Higher confidence when:
        - Graph has clear dependency structure
        - Component has well-defined properties (replicas, failover, etc.)
        - Few optional/async dependencies (more deterministic)
        """
        comp = graph.get_component(component_id)
        if comp is None:
            return PredictionConfidence.LOW

        total_components = len(graph.components)
        if total_components <= 1:
            return PredictionConfidence.HIGH

        # Check how well-defined the graph is
        edges = graph.all_dependency_edges()
        if not edges:
            return PredictionConfidence.HIGH  # No deps = trivially confident

        # Count non-deterministic edges
        non_deterministic = sum(
            1
            for e in edges
            if e.dependency_type in ("optional", "async")
        )
        determinism_ratio = 1.0 - (non_deterministic / len(edges))

        if determinism_ratio >= 0.8:
            return PredictionConfidence.HIGH
        if determinism_ratio >= 0.5:
            return PredictionConfidence.MEDIUM
        return PredictionConfidence.LOW

    @staticmethod
    def _estimate_affected_users(impacts: list[ComponentImpact]) -> str:
        """Estimate the number of affected users based on impact severity."""
        if not impacts:
            return "none"

        catastrophic = sum(
            1
            for i in impacts
            if i.impact_level == ImpactLevel.CATASTROPHIC
        )
        severe = sum(
            1 for i in impacts if i.impact_level == ImpactLevel.SEVERE
        )
        moderate = sum(
            1 for i in impacts if i.impact_level == ImpactLevel.MODERATE
        )

        if catastrophic > 0:
            return "all users likely affected"
        if severe > 2:
            return "majority of users affected"
        if severe > 0:
            return "significant portion of users affected"
        if moderate > 0:
            return "some users affected"
        return "minimal user impact"

    @staticmethod
    def _generate_mitigations(
        graph: InfraGraph,
        component_id: str,
        impacts: list[ComponentImpact],
    ) -> list[str]:
        """Generate mitigation suggestions to reduce blast radius."""
        suggestions: list[str] = []
        comp = graph.get_component(component_id)
        if comp is None:
            return suggestions

        # Check replicas
        if comp.replicas < 2:
            suggestions.append(
                f"Add replicas to {comp.name} (currently {comp.replicas}). "
                f"Recommended: at least 2 replicas for redundancy."
            )

        # Check failover
        if not comp.failover.enabled:
            suggestions.append(
                f"Enable failover for {comp.name} to allow automatic "
                f"recovery on failure."
            )

        # Check autoscaling
        if not comp.autoscaling.enabled:
            suggestions.append(
                f"Enable autoscaling for {comp.name} to handle "
                f"load-related failures."
            )

        # Check for circuit breakers on incoming edges
        dependents = graph.get_dependents(component_id)
        for dep in dependents:
            edge = graph.get_dependency_edge(dep.id, component_id)
            if edge and not edge.circuit_breaker.enabled:
                suggestions.append(
                    f"Enable circuit breaker on {dep.name} -> {comp.name} "
                    f"edge to limit cascade propagation."
                )

        # If high blast radius, suggest architectural changes
        severe_impacts = [
            i
            for i in impacts
            if i.impact_level
            in (ImpactLevel.CATASTROPHIC, ImpactLevel.SEVERE)
        ]
        if len(severe_impacts) > 2:
            suggestions.append(
                f"Consider decomposing dependencies on {comp.name} "
                f"to reduce single-point-of-failure risk."
            )

        return suggestions

    def _calculate_incoming_vulnerability(
        self, graph: InfraGraph, component_id: str
    ) -> float:
        """Calculate how vulnerable a component is to upstream failures.

        Measures how many failure paths lead to this component.
        """
        # Count all components whose failure could affect this one
        vulnerability = 0.0
        for other_id in graph.components:
            if other_id == component_id:
                continue
            pred = self.predict(graph, other_id)
            for impact in pred.predicted_impacts:
                if impact.component_id == component_id:
                    # Weight by impact probability
                    vulnerability += impact.impact_probability * 25.0
                    break

        return min(100.0, vulnerability)

    @staticmethod
    def _clone_graph(graph: InfraGraph) -> InfraGraph:
        """Create a deep copy of an InfraGraph for what-if analysis."""
        new_graph = InfraGraph()
        for comp_id, comp in graph.components.items():
            # Deep copy the component
            cloned = comp.model_copy(deep=True)
            new_graph.add_component(cloned)
        # Re-add all dependency edges
        for edge in graph.all_dependency_edges():
            cloned_edge = edge.model_copy(deep=True)
            new_graph.add_dependency(cloned_edge)
        return new_graph

    def _build_delta_summary(
        self,
        baseline: BlastPrediction,
        modified: BlastPrediction,
        change_descriptions: list[str],
        comp_name: str,
    ) -> str:
        """Build a human-readable delta summary."""
        old_score = baseline.blast_radius_score
        new_score = modified.blast_radius_score
        delta = new_score - old_score

        changes_str = ", ".join(change_descriptions)

        if delta < -1.0:
            return (
                f"Blast radius reduced from {old_score:.0f} to "
                f"{new_score:.0f} by {changes_str} on {comp_name}"
            )
        if delta > 1.0:
            return (
                f"Blast radius increased from {old_score:.0f} to "
                f"{new_score:.0f} after {changes_str} on {comp_name}"
            )
        return (
            f"Blast radius unchanged (~{old_score:.0f}) after "
            f"{changes_str} on {comp_name}"
        )

    @staticmethod
    def _impact_distribution(pred: BlastPrediction) -> dict[str, int]:
        """Count impacts by level."""
        dist: dict[str, int] = {
            ImpactLevel.CATASTROPHIC.value: 0,
            ImpactLevel.SEVERE.value: 0,
            ImpactLevel.MODERATE.value: 0,
            ImpactLevel.MINOR.value: 0,
        }
        for impact in pred.predicted_impacts:
            if impact.impact_level.value in dist:
                dist[impact.impact_level.value] += 1
        return dist

    @staticmethod
    def _identify_risk_factors(
        graph: InfraGraph,
        comp,
        prediction: BlastPrediction,
    ) -> list[str]:
        """Identify specific risk factors for a component."""
        factors: list[str] = []

        if comp.replicas < 2:
            factors.append("single-point-of-failure (no replicas)")

        if not comp.failover.enabled:
            factors.append("no failover configured")

        if comp.utilization() > 80:
            factors.append(
                f"high utilization ({comp.utilization():.0f}%)"
            )

        dependents = graph.get_dependents(comp.id)
        if len(dependents) > 3:
            factors.append(
                f"high fan-in ({len(dependents)} dependents)"
            )

        if prediction.max_cascade_depth > 2:
            factors.append(
                f"deep cascade chain (depth {prediction.max_cascade_depth})"
            )

        if prediction.blast_radius_score > 50:
            factors.append("high blast radius score")

        return factors

    @staticmethod
    def _risk_level_label(score: float) -> str:
        """Return a human-readable risk level label."""
        if score >= 75:
            return "critical"
        if score >= 50:
            return "high"
        if score >= 25:
            return "medium"
        if score > 0:
            return "low"
        return "none"
