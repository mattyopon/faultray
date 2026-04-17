# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Infrastructure cost anomaly detector.

Identifies unusual cost patterns, over-provisioned resources, underutilized
components, and cost optimization opportunities by analyzing infrastructure
topology and resource allocation patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


class AnomalyType(str, Enum):
    """Types of cost anomalies detected in infrastructure configurations."""

    OVER_PROVISIONED = "over_provisioned"
    UNDER_UTILIZED = "under_utilized"
    COST_SPIKE = "cost_spike"
    REDUNDANT_COMPONENT = "redundant_component"
    MISSING_SPOT_OPPORTUNITY = "missing_spot_opportunity"
    OVERSIZED_INSTANCE = "oversized_instance"
    IDLE_RESOURCE = "idle_resource"
    UNBALANCED_REPLICAS = "unbalanced_replicas"


# Base monthly cost per replica by component type (USD).
_BASE_MONTHLY_COST: dict[ComponentType, float] = {
    ComponentType.DATABASE: 500.0,
    ComponentType.APP_SERVER: 200.0,
    ComponentType.CACHE: 150.0,
    ComponentType.LOAD_BALANCER: 100.0,
    ComponentType.WEB_SERVER: 180.0,
    ComponentType.QUEUE: 120.0,
    ComponentType.STORAGE: 80.0,
    ComponentType.DNS: 50.0,
    ComponentType.EXTERNAL_API: 0.0,
    ComponentType.CUSTOM: 100.0,
    ComponentType.AI_AGENT: 300.0,
    ComponentType.LLM_ENDPOINT: 800.0,
    ComponentType.TOOL_SERVICE: 150.0,
    ComponentType.AGENT_ORCHESTRATOR: 250.0,
    ComponentType.AUTOMATION: 50.0,
    ComponentType.SERVERLESS: 180.0,
    ComponentType.SCHEDULED_JOB: 100.0,
}

# Tier classification for cost reporting.
_COMPONENT_TIER: dict[ComponentType, str] = {
    ComponentType.DATABASE: "compute",
    ComponentType.APP_SERVER: "compute",
    ComponentType.WEB_SERVER: "compute",
    ComponentType.CACHE: "compute",
    ComponentType.LOAD_BALANCER: "network",
    ComponentType.DNS: "network",
    ComponentType.QUEUE: "compute",
    ComponentType.STORAGE: "storage",
    ComponentType.EXTERNAL_API: "network",
    ComponentType.CUSTOM: "compute",
    ComponentType.AI_AGENT: "compute",
    ComponentType.LLM_ENDPOINT: "compute",
    ComponentType.TOOL_SERVICE: "compute",
    ComponentType.AGENT_ORCHESTRATOR: "compute",
    ComponentType.AUTOMATION: "compute",
    ComponentType.SERVERLESS: "compute",
    ComponentType.SCHEDULED_JOB: "compute",
}

# Minimum replicas threshold factor — replicas above this multiple of the
# minimum required are considered over-provisioned.
_OVER_PROVISION_FACTOR = 3


@dataclass
class CostAnomaly:
    """A single cost anomaly detected in the infrastructure graph."""

    component_id: str
    component_name: str
    anomaly_type: AnomalyType
    description: str
    current_monthly_cost: float
    optimized_monthly_cost: float
    savings_potential: float
    savings_percent: float
    confidence: float  # 0-1.0
    recommendation: str
    risk_if_optimized: str  # What could go wrong


@dataclass
class CostEfficiencyReport:
    """Full cost-efficiency analysis for an infrastructure graph."""

    total_monthly_cost: float
    optimizable_cost: float
    potential_savings: float
    savings_percent: float
    efficiency_score: float  # 0-100
    anomalies: list[CostAnomaly] = field(default_factory=list)
    top_recommendations: list[str] = field(default_factory=list)
    cost_by_component_type: dict[str, float] = field(default_factory=dict)
    cost_by_tier: dict[str, float] = field(default_factory=dict)


class CostAnomalyDetector:
    """Detect cost anomalies in an infrastructure graph.

    Analyses the topology, replica counts, dependency structure and component
    health to find over-provisioned resources, redundant components,
    unbalanced replicas and idle resources.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self) -> CostEfficiencyReport:
        """Run all anomaly detectors and build the efficiency report."""
        components = self._graph.components

        if not components:
            return CostEfficiencyReport(
                total_monthly_cost=0.0,
                optimizable_cost=0.0,
                potential_savings=0.0,
                savings_percent=0.0,
                efficiency_score=100.0,
            )

        # Collect anomalies from all detectors.
        anomalies: list[CostAnomaly] = []
        anomalies.extend(self._detect_over_provisioning())
        anomalies.extend(self._detect_redundant_components())
        anomalies.extend(self._detect_unbalanced_replicas())
        anomalies.extend(self._detect_idle_resources())

        # Aggregate costs.
        total_cost = sum(
            self._estimate_component_cost(c) for c in components.values()
        )
        optimizable_cost = sum(a.savings_potential for a in anomalies)
        savings_percent = (
            (optimizable_cost / total_cost * 100.0) if total_cost > 0 else 0.0
        )

        # Build per-type and per-tier cost breakdowns.
        cost_by_type: dict[str, float] = {}
        cost_by_tier: dict[str, float] = {}
        for comp in components.values():
            cost = self._estimate_component_cost(comp)
            type_key = comp.type.value
            cost_by_type[type_key] = cost_by_type.get(type_key, 0.0) + cost
            tier = _COMPONENT_TIER.get(comp.type, "compute")
            cost_by_tier[tier] = cost_by_tier.get(tier, 0.0) + cost

        efficiency = self._calculate_efficiency_score(anomalies, total_cost)

        # Top recommendations (unique, ordered by savings desc).
        top_recs: list[str] = []
        seen: set[str] = set()
        for a in sorted(anomalies, key=lambda x: x.savings_potential, reverse=True):
            if a.recommendation not in seen:
                seen.add(a.recommendation)
                top_recs.append(a.recommendation)

        return CostEfficiencyReport(
            total_monthly_cost=total_cost,
            optimizable_cost=optimizable_cost,
            potential_savings=optimizable_cost,
            savings_percent=savings_percent,
            efficiency_score=efficiency,
            anomalies=anomalies,
            top_recommendations=top_recs,
            cost_by_component_type=cost_by_type,
            cost_by_tier=cost_by_tier,
        )

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------

    def _detect_over_provisioning(self) -> list[CostAnomaly]:
        """Detect components whose replicas exceed 3x the minimum needed.

        The minimum needed is estimated as ``max(1, number_of_dependents)``.
        """
        anomalies: list[CostAnomaly] = []
        for comp in self._graph.components.values():
            dependents = self._graph.get_dependents(comp.id)
            min_needed = max(1, len(dependents))
            if comp.replicas > min_needed * _OVER_PROVISION_FACTOR:
                current_cost = self._estimate_component_cost(comp)
                optimized_replicas = min_needed * _OVER_PROVISION_FACTOR
                optimized_cost = self._base_cost(comp.type) * optimized_replicas
                savings = current_cost - optimized_cost
                anomalies.append(
                    CostAnomaly(
                        component_id=comp.id,
                        component_name=comp.name,
                        anomaly_type=AnomalyType.OVER_PROVISIONED,
                        description=(
                            f"Component '{comp.name}' has {comp.replicas} replicas "
                            f"but only ~{min_needed} are needed based on dependents "
                            f"(>{_OVER_PROVISION_FACTOR}x threshold)."
                        ),
                        current_monthly_cost=current_cost,
                        optimized_monthly_cost=optimized_cost,
                        savings_potential=savings,
                        savings_percent=(
                            (savings / current_cost * 100.0) if current_cost > 0 else 0.0
                        ),
                        confidence=0.8,
                        recommendation=(
                            f"Reduce replicas for '{comp.name}' from {comp.replicas} "
                            f"to {optimized_replicas}."
                        ),
                        risk_if_optimized=(
                            "Reduced capacity headroom; may impact availability "
                            "during traffic spikes."
                        ),
                    )
                )
        return anomalies

    def _detect_redundant_components(self) -> list[CostAnomaly]:
        """Detect components with the same type that share all dependents.

        Two components are considered redundant when they have identical
        ``ComponentType`` *and* neither one has any unique dependent that the
        other does not.
        """
        anomalies: list[CostAnomaly] = []
        components = list(self._graph.components.values())
        seen_pairs: set[tuple[str, str]] = set()

        for i, comp_a in enumerate(components):
            for comp_b in components[i + 1:]:
                if comp_a.type != comp_b.type:
                    continue
                pair = tuple(sorted([comp_a.id, comp_b.id]))
                if pair in seen_pairs:
                    continue

                deps_a = {d.id for d in self._graph.get_dependents(comp_a.id)}
                deps_b = {d.id for d in self._graph.get_dependents(comp_b.id)}

                # Both have no unique dependents — they serve the same set.
                if deps_a == deps_b:
                    seen_pairs.add(pair)
                    # The cheaper component is the candidate for removal.
                    cost_a = self._estimate_component_cost(comp_a)
                    cost_b = self._estimate_component_cost(comp_b)
                    if cost_a <= cost_b:
                        removable, keep = comp_a, comp_b
                        remove_cost = cost_a
                    else:
                        removable, keep = comp_b, comp_a
                        remove_cost = cost_b

                    anomalies.append(
                        CostAnomaly(
                            component_id=removable.id,
                            component_name=removable.name,
                            anomaly_type=AnomalyType.REDUNDANT_COMPONENT,
                            description=(
                                f"Component '{removable.name}' appears redundant with "
                                f"'{keep.name}' (same type, same dependents)."
                            ),
                            current_monthly_cost=remove_cost,
                            optimized_monthly_cost=0.0,
                            savings_potential=remove_cost,
                            savings_percent=100.0,
                            confidence=0.6,
                            recommendation=(
                                f"Consider consolidating '{removable.name}' into "
                                f"'{keep.name}'."
                            ),
                            risk_if_optimized=(
                                "Removing a redundant component reduces failover "
                                "capacity and may create a single point of failure."
                            ),
                        )
                    )
        return anomalies

    def _detect_unbalanced_replicas(self) -> list[CostAnomaly]:
        """Detect same-type components with wildly different replica counts.

        If the max replica count for a given type exceeds 3x the min count,
        the higher-replica component is flagged.
        """
        anomalies: list[CostAnomaly] = []
        by_type: dict[ComponentType, list] = {}
        for comp in self._graph.components.values():
            by_type.setdefault(comp.type, []).append(comp)

        for ctype, comps in by_type.items():
            if len(comps) < 2:
                continue
            min_replicas = min(c.replicas for c in comps)
            max_replicas = max(c.replicas for c in comps)
            if min_replicas <= 0:
                continue
            if max_replicas > min_replicas * _OVER_PROVISION_FACTOR:
                # Flag the component(s) with the highest replica count.
                for comp in comps:
                    if comp.replicas == max_replicas:
                        current_cost = self._estimate_component_cost(comp)
                        balanced_replicas = min_replicas * _OVER_PROVISION_FACTOR
                        optimized_cost = self._base_cost(comp.type) * balanced_replicas
                        savings = current_cost - optimized_cost
                        if savings <= 0:
                            continue
                        anomalies.append(
                            CostAnomaly(
                                component_id=comp.id,
                                component_name=comp.name,
                                anomaly_type=AnomalyType.UNBALANCED_REPLICAS,
                                description=(
                                    f"Component '{comp.name}' has {comp.replicas} replicas "
                                    f"while other {ctype.value} components have as few as "
                                    f"{min_replicas} (>{_OVER_PROVISION_FACTOR}x imbalance)."
                                ),
                                current_monthly_cost=current_cost,
                                optimized_monthly_cost=optimized_cost,
                                savings_potential=savings,
                                savings_percent=(
                                    (savings / current_cost * 100.0)
                                    if current_cost > 0
                                    else 0.0
                                ),
                                confidence=0.7,
                                recommendation=(
                                    f"Balance replicas for '{comp.name}' — consider "
                                    f"reducing from {comp.replicas} to ~{balanced_replicas}."
                                ),
                                risk_if_optimized=(
                                    "Reducing replicas may impact throughput for this "
                                    "component if traffic is unevenly distributed."
                                ),
                            )
                        )
        return anomalies

    def _detect_idle_resources(self) -> list[CostAnomaly]:
        """Detect orphan components with no dependents and no dependencies.

        A component with HEALTHY status but zero graph connections is
        considered idle.
        """
        anomalies: list[CostAnomaly] = []
        for comp in self._graph.components.values():
            dependents = self._graph.get_dependents(comp.id)
            dependencies = self._graph.get_dependencies(comp.id)
            if (
                len(dependents) == 0
                and len(dependencies) == 0
                and comp.health == HealthStatus.HEALTHY
            ):
                cost = self._estimate_component_cost(comp)
                anomalies.append(
                    CostAnomaly(
                        component_id=comp.id,
                        component_name=comp.name,
                        anomaly_type=AnomalyType.IDLE_RESOURCE,
                        description=(
                            f"Component '{comp.name}' is healthy but has no dependents "
                            f"and no dependencies — it appears to be idle."
                        ),
                        current_monthly_cost=cost,
                        optimized_monthly_cost=0.0,
                        savings_potential=cost,
                        savings_percent=100.0,
                        confidence=0.9,
                        recommendation=(
                            f"Investigate whether '{comp.name}' is still needed; "
                            f"consider decommissioning to save ${cost:.0f}/month."
                        ),
                        risk_if_optimized=(
                            "If the component serves undocumented traffic it "
                            "could cause outages when removed."
                        ),
                    )
                )
        return anomalies

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    def _estimate_component_cost(self, comp) -> float:
        """Estimate monthly cost for a component based on type and replicas."""
        return self._base_cost(comp.type) * comp.replicas

    @staticmethod
    def _base_cost(ctype: ComponentType) -> float:
        """Return per-replica monthly base cost for a component type."""
        return _BASE_MONTHLY_COST.get(ctype, 100.0)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _calculate_efficiency_score(
        self,
        anomalies: list[CostAnomaly],
        total_cost: float,
    ) -> float:
        """Calculate an efficiency score from 0 (wasteful) to 100 (optimal).

        ``score = 100 - (optimizable_cost / total_cost * 100)``
        Clamped to [0, 100].
        """
        if total_cost <= 0:
            return 100.0
        optimizable = sum(a.savings_potential for a in anomalies)
        raw = 100.0 - (optimizable / total_cost * 100.0)
        return max(0.0, min(100.0, raw))
