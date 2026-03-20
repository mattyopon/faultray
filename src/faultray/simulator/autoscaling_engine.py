# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Auto-Scaling Recommendation Engine.

Analyzes simulation results and component utilization to recommend
auto-scaling parameters, exportable as Kubernetes HPA YAML or AWS
Auto Scaling Group policy JSON.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import yaml

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Utilization threshold above which scaling is recommended.
_SCALE_TRIGGER_THRESHOLD = 60.0
# Default target utilization for auto-scaling policies.
_DEFAULT_TARGET_UTILIZATION = 70.0
# Maximum replicas cap.
_MAX_REPLICAS_CAP = 20
# Default cooldown in seconds.
_DEFAULT_COOLDOWN = 300


@dataclass
class AutoScalingRecommendation:
    """A single auto-scaling recommendation for a component."""

    component_id: str
    component_name: str
    current_replicas: int
    recommended_min: int
    recommended_max: int
    target_utilization: float
    scale_up_threshold: float
    cooldown_seconds: int
    confidence: float  # 0-1
    reasoning: str

    def to_kubernetes_hpa(self) -> str:
        """Export as Kubernetes HPA YAML string."""
        # Sanitize the component_id for K8s naming (lowercase, alphanumeric + dashes)
        k8s_name = self.component_id.replace("_", "-").lower()

        hpa = {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "name": f"{k8s_name}-hpa",
                "labels": {
                    "app": k8s_name,
                    "generated-by": "faultray",
                },
            },
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": k8s_name,
                },
                "minReplicas": self.recommended_min,
                "maxReplicas": self.recommended_max,
                "metrics": [
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": int(self.target_utilization),
                            },
                        },
                    },
                ],
                "behavior": {
                    "scaleUp": {
                        "stabilizationWindowSeconds": 60,
                        "policies": [
                            {
                                "type": "Percent",
                                "value": 100,
                                "periodSeconds": 60,
                            },
                        ],
                    },
                    "scaleDown": {
                        "stabilizationWindowSeconds": self.cooldown_seconds,
                        "policies": [
                            {
                                "type": "Percent",
                                "value": 25,
                                "periodSeconds": 60,
                            },
                        ],
                    },
                },
            },
        }

        return yaml.dump(hpa, default_flow_style=False, sort_keys=False)

    def to_aws_asg(self) -> str:
        """Export as AWS Auto Scaling Group policy JSON."""
        policy = {
            "AutoScalingGroupName": f"{self.component_id}-asg",
            "MinSize": self.recommended_min,
            "MaxSize": self.recommended_max,
            "DesiredCapacity": self.current_replicas,
            "DefaultCooldown": self.cooldown_seconds,
            "TargetTrackingScalingPolicy": {
                "PolicyName": f"{self.component_id}-target-tracking",
                "TargetTrackingConfiguration": {
                    "PredefinedMetricSpecification": {
                        "PredefinedMetricType": "ASGAverageCPUUtilization",
                    },
                    "TargetValue": self.target_utilization,
                    "ScaleInCooldown": self.cooldown_seconds,
                    "ScaleOutCooldown": 60,
                },
            },
            "Tags": [
                {
                    "Key": "generated-by",
                    "Value": "faultray",
                },
                {
                    "Key": "component",
                    "Value": self.component_id,
                },
            ],
        }
        return json.dumps(policy, indent=2)


class AutoScalingRecommendationEngine:
    """Analyzes infrastructure components and recommends auto-scaling parameters.

    For each component the engine evaluates current utilization headroom,
    existing autoscaling configuration, replica count, and the component's
    position in the dependency graph (leaf nodes need less aggressive scaling
    than bottleneck services).

    Parameters
    ----------
    graph:
        The infrastructure graph to analyse.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def recommend(self) -> list[AutoScalingRecommendation]:
        """Generate auto-scaling recommendations for all components.

        Returns a list of :class:`AutoScalingRecommendation` sorted by
        confidence (highest first).
        """
        recommendations: list[AutoScalingRecommendation] = []

        for comp_id, comp in self.graph.components.items():
            util = comp.utilization()
            dependents = self.graph.get_dependents(comp_id)

            # Calculate effective utilization — use component metrics or a
            # type-based estimate when no metrics are reported.
            effective_util = util
            if effective_util < 10.0:
                # Estimate based on component type
                _type_defaults = {
                    "app_server": 45.0,
                    "web_server": 40.0,
                    "database": 55.0,
                    "cache": 35.0,
                    "load_balancer": 25.0,
                    "queue": 30.0,
                }
                effective_util = _type_defaults.get(comp.type.value, 30.0)

            # Determine if scaling is recommended
            needs_scaling = effective_util > _SCALE_TRIGGER_THRESHOLD
            has_dependents = len(dependents) > 0

            # Calculate confidence based on multiple factors
            confidence = self._calculate_confidence(
                effective_util, comp.replicas, has_dependents,
                comp.autoscaling.enabled,
            )

            # Calculate recommended replicas
            recommended_min = comp.replicas
            if needs_scaling:
                # Scale factor based on utilization above threshold
                scale_factor = effective_util / _DEFAULT_TARGET_UTILIZATION
                recommended_max = min(
                    _MAX_REPLICAS_CAP,
                    max(comp.replicas * 2, int(comp.replicas * scale_factor) + 1),
                )
            else:
                recommended_max = min(_MAX_REPLICAS_CAP, max(2, comp.replicas * 2))

            # Ensure min <= max
            recommended_min = min(recommended_min, recommended_max)

            # Scale-up threshold
            scale_up_threshold = min(80.0, effective_util + 10.0) if needs_scaling else 70.0

            # Cooldown
            cooldown = _DEFAULT_COOLDOWN
            if comp.autoscaling.enabled:
                cooldown = comp.autoscaling.scale_down_delay_seconds

            # Reasoning
            reasoning = self._build_reasoning(
                comp_id, effective_util, comp.replicas, needs_scaling,
                has_dependents, comp.autoscaling.enabled,
            )

            recommendations.append(AutoScalingRecommendation(
                component_id=comp_id,
                component_name=comp.name,
                current_replicas=comp.replicas,
                recommended_min=recommended_min,
                recommended_max=recommended_max,
                target_utilization=_DEFAULT_TARGET_UTILIZATION,
                scale_up_threshold=scale_up_threshold,
                cooldown_seconds=cooldown,
                confidence=round(confidence, 2),
                reasoning=reasoning,
            ))

        # Sort by confidence descending
        recommendations.sort(key=lambda r: r.confidence, reverse=True)
        return recommendations

    @staticmethod
    def _calculate_confidence(
        utilization: float,
        replicas: int,
        has_dependents: bool,
        autoscaling_enabled: bool,
    ) -> float:
        """Calculate recommendation confidence (0-1).

        Higher confidence when:
        - utilization is high (clear need to scale)
        - component is a SPOF (single replica with dependents)
        - autoscaling is not already configured
        """
        confidence = 0.5  # base

        # High utilization increases confidence
        if utilization > 90:
            confidence += 0.3
        elif utilization > 80:
            confidence += 0.25
        elif utilization > 70:
            confidence += 0.2
        elif utilization > 60:
            confidence += 0.1

        # SPOF with dependents
        if replicas <= 1 and has_dependents:
            confidence += 0.15

        # Already has autoscaling — lower confidence (less urgent)
        if autoscaling_enabled:
            confidence -= 0.2

        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _build_reasoning(
        component_id: str,
        utilization: float,
        replicas: int,
        needs_scaling: bool,
        has_dependents: bool,
        autoscaling_enabled: bool,
    ) -> str:
        """Build a human-readable reasoning string."""
        parts: list[str] = []

        if needs_scaling:
            parts.append(
                f"Utilization at {utilization:.0f}% exceeds {_SCALE_TRIGGER_THRESHOLD:.0f}% threshold."
            )
        else:
            parts.append(
                f"Utilization at {utilization:.0f}% is within acceptable range."
            )

        if replicas <= 1:
            parts.append("Single replica — no redundancy.")
            if has_dependents:
                parts.append("Other components depend on this; SPOF risk.")

        if autoscaling_enabled:
            parts.append("Autoscaling already configured; review existing policy.")
        else:
            parts.append("No autoscaling configured; HPA recommended.")

        return " ".join(parts)

    def export_all_k8s(self, recommendations: list[AutoScalingRecommendation] | None = None) -> str:
        """Export all recommendations as a combined K8s HPA YAML document.

        Parameters
        ----------
        recommendations:
            Pre-computed recommendations.  If ``None``, :meth:`recommend` is
            called automatically.
        """
        if recommendations is None:
            recommendations = self.recommend()

        docs = []
        for rec in recommendations:
            docs.append(rec.to_kubernetes_hpa())
        return "---\n".join(docs)

    def export_all_aws(self, recommendations: list[AutoScalingRecommendation] | None = None) -> str:
        """Export all recommendations as a combined AWS ASG JSON array.

        Parameters
        ----------
        recommendations:
            Pre-computed recommendations.  If ``None``, :meth:`recommend` is
            called automatically.
        """
        if recommendations is None:
            recommendations = self.recommend()

        policies = [json.loads(rec.to_aws_asg()) for rec in recommendations]
        return json.dumps(policies, indent=2)
