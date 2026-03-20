# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Deployment strategy recommender — analyze infrastructure and recommend optimal deployment strategies.

Evaluates infrastructure graphs and recommends the best deployment strategy
(blue-green, canary, rolling update, recreate, A/B testing, shadow) based on
component characteristics, risk tolerance, health status, and dependency topology.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


class DeploymentType(str, Enum):
    """Deployment strategy type."""

    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    ROLLING_UPDATE = "rolling_update"
    RECREATE = "recreate"
    AB_TESTING = "ab_testing"
    SHADOW = "shadow"


class RiskTolerance(str, Enum):
    """Risk tolerance level for deployment decisions."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class DeploymentRecommendation:
    """Recommendation for deploying a single component."""

    strategy: DeploymentType
    risk_level: float  # 0-100
    estimated_duration_minutes: int
    rollback_time_minutes: int
    recommended_canary_percent: float  # 0-100
    prerequisites: list[str]
    risks: list[str]
    steps: list[str]


@dataclass
class DeploymentPlan:
    """Overall deployment plan for multiple components."""

    recommendations: dict[str, DeploymentRecommendation]
    overall_strategy: DeploymentType
    total_duration: int  # minutes
    total_risk_score: float  # 0-100


class DeploymentStrategyAdvisor:
    """Analyze infrastructure graphs and recommend deployment strategies."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    def recommend(
        self,
        graph: InfraGraph,
        component_id: str,
        risk_tolerance: RiskTolerance = RiskTolerance.MODERATE,
    ) -> DeploymentRecommendation:
        """Recommend a deployment strategy for a single component."""
        comp = graph.get_component(component_id)
        if comp is None:
            # Unknown component — safest default
            return DeploymentRecommendation(
                strategy=DeploymentType.RECREATE,
                risk_level=80.0,
                estimated_duration_minutes=30,
                rollback_time_minutes=30,
                recommended_canary_percent=0.0,
                prerequisites=["Identify component before deploying"],
                risks=["Component not found in infrastructure graph"],
                steps=["Locate component", "Recreate with new version"],
            )

        # Gather characteristics
        replicas = comp.replicas
        health = comp.health
        comp_type = comp.type
        dependents = graph.get_dependents(comp.id)
        dependent_count = len(dependents)
        has_failover = comp.failover.enabled
        has_autoscaling = comp.autoscaling.enabled

        # Determine strategy based on characteristics and risk tolerance
        strategy = self._select_strategy(
            comp_type, replicas, health, dependent_count,
            has_failover, has_autoscaling, risk_tolerance,
        )

        risk_level = self._calculate_risk(
            strategy, replicas, health, dependent_count,
            has_failover, has_autoscaling, risk_tolerance,
        )

        duration = self._estimate_duration(strategy, replicas, comp_type)
        rollback_time = self._estimate_rollback_time(strategy, comp_type)
        canary_percent = self._recommend_canary_percent(strategy, risk_tolerance)
        prerequisites = self._gather_prerequisites(strategy, comp, has_failover, has_autoscaling)
        risks = self._identify_risks(strategy, comp, dependent_count, health)
        steps = self._generate_steps(strategy, comp)

        return DeploymentRecommendation(
            strategy=strategy,
            risk_level=round(risk_level, 1),
            estimated_duration_minutes=duration,
            rollback_time_minutes=rollback_time,
            recommended_canary_percent=canary_percent,
            prerequisites=prerequisites,
            risks=risks,
            steps=steps,
        )

    def plan(
        self,
        graph: InfraGraph,
        component_ids: list[str],
        risk_tolerance: RiskTolerance = RiskTolerance.MODERATE,
    ) -> DeploymentPlan:
        """Create a deployment plan for multiple components."""
        if not component_ids:
            return DeploymentPlan(
                recommendations={},
                overall_strategy=DeploymentType.ROLLING_UPDATE,
                total_duration=0,
                total_risk_score=0.0,
            )

        recommendations: dict[str, DeploymentRecommendation] = {}
        for cid in component_ids:
            recommendations[cid] = self.recommend(graph, cid, risk_tolerance)

        # Overall strategy is the most conservative strategy among components
        strategy_priority = [
            DeploymentType.RECREATE,
            DeploymentType.BLUE_GREEN,
            DeploymentType.CANARY,
            DeploymentType.SHADOW,
            DeploymentType.AB_TESTING,
            DeploymentType.ROLLING_UPDATE,
        ]

        overall = DeploymentType.ROLLING_UPDATE
        for prio in strategy_priority:
            if any(r.strategy == prio for r in recommendations.values()):
                overall = prio
                break

        total_duration = sum(r.estimated_duration_minutes for r in recommendations.values())
        total_risk = max(r.risk_level for r in recommendations.values()) if recommendations else 0.0

        # Sort recommendations: deploy highest-risk components last
        sorted_recs: dict[str, DeploymentRecommendation] = dict(
            sorted(recommendations.items(), key=lambda item: item[1].risk_level)
        )

        return DeploymentPlan(
            recommendations=sorted_recs,
            overall_strategy=overall,
            total_duration=total_duration,
            total_risk_score=round(total_risk, 1),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_strategy(
        self,
        comp_type: ComponentType,
        replicas: int,
        health: HealthStatus,
        dependent_count: int,
        has_failover: bool,
        has_autoscaling: bool,
        risk_tolerance: RiskTolerance,
    ) -> DeploymentType:
        """Select deployment strategy based on component characteristics."""
        # Unhealthy components should be recreated (safest recovery)
        if health in (HealthStatus.DOWN, HealthStatus.OVERLOADED):
            return DeploymentType.RECREATE

        # Databases and stateful stores — always blue-green for safety
        if comp_type in (ComponentType.DATABASE, ComponentType.STORAGE):
            return DeploymentType.BLUE_GREEN

        # Single replica — limited options
        if replicas == 1:
            if risk_tolerance == RiskTolerance.AGGRESSIVE:
                return DeploymentType.RECREATE
            return DeploymentType.BLUE_GREEN

        # Conservative risk tolerance prefers blue-green for critical components
        if risk_tolerance == RiskTolerance.CONSERVATIVE:
            if dependent_count >= 3 or comp_type == ComponentType.LOAD_BALANCER:
                return DeploymentType.BLUE_GREEN
            if comp_type == ComponentType.CACHE:
                return DeploymentType.BLUE_GREEN
            return DeploymentType.CANARY

        # Aggressive tolerance favors rolling updates for stateless
        if risk_tolerance == RiskTolerance.AGGRESSIVE:
            if comp_type in (
                ComponentType.APP_SERVER,
                ComponentType.WEB_SERVER,
                ComponentType.EXTERNAL_API,
                ComponentType.CUSTOM,
            ):
                return DeploymentType.ROLLING_UPDATE
            if comp_type == ComponentType.CACHE:
                return DeploymentType.ROLLING_UPDATE
            return DeploymentType.CANARY

        # Moderate tolerance — default
        if comp_type in (ComponentType.LOAD_BALANCER, ComponentType.DNS):
            return DeploymentType.BLUE_GREEN
        if comp_type == ComponentType.QUEUE:
            return DeploymentType.CANARY
        if comp_type == ComponentType.CACHE:
            return DeploymentType.CANARY
        if dependent_count >= 3:
            return DeploymentType.CANARY

        # Stateless services with sufficient replicas
        if comp_type in (
            ComponentType.APP_SERVER,
            ComponentType.WEB_SERVER,
            ComponentType.EXTERNAL_API,
            ComponentType.CUSTOM,
        ) and replicas >= 2:
            return DeploymentType.ROLLING_UPDATE

        return DeploymentType.CANARY

    def _calculate_risk(
        self,
        strategy: DeploymentType,
        replicas: int,
        health: HealthStatus,
        dependent_count: int,
        has_failover: bool,
        has_autoscaling: bool,
        risk_tolerance: RiskTolerance,
    ) -> float:
        """Calculate risk level (0-100) for a deployment."""
        # Base risk by strategy
        strategy_base = {
            DeploymentType.BLUE_GREEN: 20.0,
            DeploymentType.CANARY: 30.0,
            DeploymentType.ROLLING_UPDATE: 35.0,
            DeploymentType.AB_TESTING: 25.0,
            DeploymentType.SHADOW: 15.0,
            DeploymentType.RECREATE: 50.0,
        }
        risk = strategy_base.get(strategy, 40.0)

        # Adjust for replicas — single replica is riskier
        if replicas == 1:
            risk += 20.0
        elif replicas <= 2:
            risk += 5.0

        # Adjust for health
        if health == HealthStatus.DOWN:
            risk += 25.0
        elif health == HealthStatus.OVERLOADED:
            risk += 15.0
        elif health == HealthStatus.DEGRADED:
            risk += 10.0

        # Adjust for dependents
        risk += min(dependent_count * 5.0, 25.0)

        # Mitigations
        if has_failover:
            risk -= 10.0
        if has_autoscaling:
            risk -= 5.0

        # Tolerance adjustment
        if risk_tolerance == RiskTolerance.CONSERVATIVE:
            risk += 5.0
        elif risk_tolerance == RiskTolerance.AGGRESSIVE:
            risk -= 5.0

        return max(0.0, min(100.0, risk))

    def _estimate_duration(
        self,
        strategy: DeploymentType,
        replicas: int,
        comp_type: ComponentType,
    ) -> int:
        """Estimate deployment duration in minutes."""
        base_minutes = {
            DeploymentType.BLUE_GREEN: 15,
            DeploymentType.CANARY: 30,
            DeploymentType.ROLLING_UPDATE: 10,
            DeploymentType.RECREATE: 5,
            DeploymentType.AB_TESTING: 20,
            DeploymentType.SHADOW: 25,
        }
        duration = base_minutes.get(strategy, 15)

        # Databases take longer
        if comp_type in (ComponentType.DATABASE, ComponentType.STORAGE):
            duration *= 2

        # More replicas = more time for rolling updates
        if strategy == DeploymentType.ROLLING_UPDATE:
            duration += replicas * 2

        return duration

    def _estimate_rollback_time(
        self,
        strategy: DeploymentType,
        comp_type: ComponentType,
    ) -> int:
        """Estimate rollback time in minutes."""
        rollback = {
            DeploymentType.BLUE_GREEN: 2,
            DeploymentType.CANARY: 5,
            DeploymentType.ROLLING_UPDATE: 10,
            DeploymentType.RECREATE: 15,
            DeploymentType.AB_TESTING: 3,
            DeploymentType.SHADOW: 1,
        }
        time = rollback.get(strategy, 10)

        # Databases take longer to roll back
        if comp_type in (ComponentType.DATABASE, ComponentType.STORAGE):
            time *= 3

        return time

    def _recommend_canary_percent(
        self,
        strategy: DeploymentType,
        risk_tolerance: RiskTolerance,
    ) -> float:
        """Recommend initial canary traffic percentage."""
        if strategy != DeploymentType.CANARY:
            return 0.0

        if risk_tolerance == RiskTolerance.CONSERVATIVE:
            return 5.0
        if risk_tolerance == RiskTolerance.AGGRESSIVE:
            return 25.0
        return 10.0

    def _gather_prerequisites(
        self,
        strategy: DeploymentType,
        comp,
        has_failover: bool,
        has_autoscaling: bool,
    ) -> list[str]:
        """Gather prerequisites for the deployment."""
        prereqs: list[str] = []

        if strategy == DeploymentType.BLUE_GREEN:
            prereqs.append("Provision parallel environment")
            prereqs.append("Configure traffic switch mechanism")
        elif strategy == DeploymentType.CANARY:
            prereqs.append("Set up traffic splitting")
            prereqs.append("Configure monitoring and alerting")
        elif strategy == DeploymentType.ROLLING_UPDATE:
            prereqs.append("Verify rolling update controller is configured")
        elif strategy == DeploymentType.RECREATE:
            prereqs.append("Schedule maintenance window")
            prereqs.append("Notify stakeholders of expected downtime")

        if not has_failover and comp.replicas <= 1:
            prereqs.append("Consider enabling failover before deployment")

        if not has_autoscaling and comp.replicas >= 3:
            prereqs.append("Consider enabling autoscaling")

        prereqs.append("Create backup of current state")
        prereqs.append("Verify health checks are configured")

        return prereqs

    def _identify_risks(
        self,
        strategy: DeploymentType,
        comp,
        dependent_count: int,
        health: HealthStatus,
    ) -> list[str]:
        """Identify risks associated with the deployment."""
        risks: list[str] = []

        if strategy == DeploymentType.RECREATE:
            risks.append("Full downtime during deployment")

        if comp.replicas == 1:
            risks.append("Single replica — no redundancy during deployment")

        if dependent_count > 0:
            risks.append(f"{dependent_count} dependent component(s) may be affected")

        if health != HealthStatus.HEALTHY:
            risks.append(f"Component is currently {health.value}")

        if strategy == DeploymentType.ROLLING_UPDATE and comp.replicas <= 2:
            risks.append("Limited capacity during rolling update with few replicas")

        if comp.type in (ComponentType.DATABASE, ComponentType.STORAGE):
            risks.append("Stateful component — data migration may be required")

        return risks

    def _generate_steps(
        self,
        strategy: DeploymentType,
        comp,
    ) -> list[str]:
        """Generate deployment steps."""
        steps: list[str] = []

        if strategy == DeploymentType.BLUE_GREEN:
            steps = [
                f"Deploy new version of {comp.id} to green environment",
                "Run smoke tests on green environment",
                "Switch traffic from blue to green",
                "Monitor for errors",
                "Decommission blue environment after validation",
            ]
        elif strategy == DeploymentType.CANARY:
            steps = [
                f"Deploy new version of {comp.id} to canary instances",
                "Route small percentage of traffic to canary",
                "Monitor error rates and latency",
                "Gradually increase canary traffic",
                "Promote canary to full deployment",
            ]
        elif strategy == DeploymentType.ROLLING_UPDATE:
            steps = [
                f"Begin rolling update of {comp.id}",
                "Update instances one at a time",
                "Verify health check passes for each updated instance",
                "Continue until all instances are updated",
            ]
        elif strategy == DeploymentType.RECREATE:
            steps = [
                f"Stop all instances of {comp.id}",
                "Deploy new version",
                "Start all instances",
                "Verify health checks pass",
            ]
        elif strategy == DeploymentType.AB_TESTING:
            steps = [
                f"Deploy variant B of {comp.id}",
                "Split traffic between A and B based on criteria",
                "Collect metrics and user behavior data",
                "Analyze results",
                "Promote winning variant",
            ]
        elif strategy == DeploymentType.SHADOW:
            steps = [
                f"Deploy shadow version of {comp.id}",
                "Mirror production traffic to shadow",
                "Compare responses without affecting users",
                "Validate shadow version behavior",
                "Promote shadow to production",
            ]

        return steps
