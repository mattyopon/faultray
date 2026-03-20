# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Carbon Footprint Engine.

Estimates the carbon emissions of infrastructure components based on their
compute usage, region-specific carbon intensity factors, and replica counts.
Provides sustainability scoring and green recommendations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Carbon intensity factors in grams CO2 per CPU-hour by cloud region.
# Sources: cloud provider sustainability reports (approximate averages).
CARBON_FACTORS_G_PER_CPU_HOUR: dict[str, float] = {
    # AWS regions
    "us-east-1": 0.38,
    "us-east-2": 0.40,
    "us-west-1": 0.25,
    "us-west-2": 0.18,
    "eu-west-1": 0.25,
    "eu-west-2": 0.20,
    "eu-central-1": 0.30,
    "ap-northeast-1": 0.42,
    "ap-southeast-1": 0.45,
    "ap-south-1": 0.60,
    "ca-central-1": 0.12,
    "sa-east-1": 0.10,
    # GCP regions
    "us-central1": 0.32,
    "us-east4": 0.35,
    "europe-west1": 0.12,
    "europe-west4": 0.28,
    "europe-north1": 0.05,
    "asia-east1": 0.48,
    "asia-northeast1": 0.42,
    # Azure regions
    "eastus": 0.38,
    "westus2": 0.18,
    "northeurope": 0.15,
    "westeurope": 0.25,
    "swedencentral": 0.05,
    # Default for unknown regions
    "default": 0.35,
}

# Average car emits ~120g CO2 per km.
_CAR_CO2_G_PER_KM = 120.0

# Hours per year.
_HOURS_PER_YEAR = 365.25 * 24

# Grams per kilogram.
_G_PER_KG = 1000.0

# Recommended low-carbon regions (< 0.15g CO2/CPU-hour).
_GREEN_REGIONS = [
    ("europe-north1", 0.05, "GCP Finland — near-zero carbon, wind/nuclear"),
    ("swedencentral", 0.05, "Azure Sweden — hydro/wind powered"),
    ("sa-east-1", 0.10, "AWS São Paulo — largely hydroelectric"),
    ("ca-central-1", 0.12, "AWS Canada — hydroelectric"),
    ("europe-west1", 0.12, "GCP Belgium — low carbon"),
    ("northeurope", 0.15, "Azure Ireland — wind powered"),
]


@dataclass
class CarbonReport:
    """Carbon footprint analysis report."""

    total_annual_kg: float
    per_component: dict[str, float]  # component_id -> kg CO2/year
    equivalent_car_km: float  # total CO2 in car driving equivalent
    green_recommendations: list[dict]  # [{recommendation, potential_savings_kg, ...}]
    sustainability_score: float  # 0-100 (100 = most efficient)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "total_annual_kg": round(self.total_annual_kg, 2),
            "per_component": {
                k: round(v, 2) for k, v in self.per_component.items()
            },
            "equivalent_car_km": round(self.equivalent_car_km, 1),
            "green_recommendations": self.green_recommendations,
            "sustainability_score": round(self.sustainability_score, 1),
        }


class CarbonEngine:
    """Estimates the carbon footprint of infrastructure components.

    For each component, the engine calculates annual CO2 emissions based on:
    - Number of replicas (each replica consumes compute)
    - Region-specific carbon intensity factor
    - Running 24/7/365

    Parameters
    ----------
    graph:
        The infrastructure graph to analyse.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def analyze(self) -> CarbonReport:
        """Analyze the carbon footprint of all components.

        Returns
        -------
        CarbonReport
            Comprehensive carbon footprint analysis with recommendations.
        """
        per_component: dict[str, float] = {}
        total_annual_g = 0.0

        for comp_id, comp in self.graph.components.items():
            # Determine region
            region = comp.region.region if comp.region.region else "default"
            carbon_factor = CARBON_FACTORS_G_PER_CPU_HOUR.get(
                region, CARBON_FACTORS_G_PER_CPU_HOUR["default"]
            )

            # Annual CO2 in grams = replicas * hours_per_year * carbon_factor
            annual_g = comp.replicas * _HOURS_PER_YEAR * carbon_factor
            per_component[comp_id] = annual_g / _G_PER_KG  # convert to kg
            total_annual_g += annual_g

        total_annual_kg = total_annual_g / _G_PER_KG

        # Car driving equivalent
        equivalent_car_km = (total_annual_g / _CAR_CO2_G_PER_KM) if _CAR_CO2_G_PER_KM > 0 else 0.0

        # Green recommendations
        green_recommendations = self._generate_recommendations(per_component)

        # Sustainability score
        sustainability_score = self._calculate_sustainability_score(per_component)

        return CarbonReport(
            total_annual_kg=total_annual_kg,
            per_component=per_component,
            equivalent_car_km=equivalent_car_km,
            green_recommendations=green_recommendations,
            sustainability_score=sustainability_score,
        )

    def _generate_recommendations(
        self, per_component: dict[str, float],
    ) -> list[dict]:
        """Generate green infrastructure recommendations."""
        recommendations: list[dict] = []

        for comp_id, comp in self.graph.components.items():
            region = comp.region.region if comp.region.region else "default"
            current_factor = CARBON_FACTORS_G_PER_CPU_HOUR.get(
                region, CARBON_FACTORS_G_PER_CPU_HOUR["default"]
            )
            current_kg = per_component.get(comp_id, 0.0)

            # Recommend low-carbon region if current region is high-carbon
            if current_factor > 0.20:
                # Find the best green region
                best_region, best_factor, best_desc = _GREEN_REGIONS[0]
                potential_kg = comp.replicas * _HOURS_PER_YEAR * best_factor / _G_PER_KG
                savings_kg = current_kg - potential_kg

                if savings_kg > 0:
                    recommendations.append({
                        "recommendation": (
                            f"Move {comp.name} from '{region}' to '{best_region}' "
                            f"({best_desc})"
                        ),
                        "component": comp_id,
                        "current_region": region,
                        "suggested_region": best_region,
                        "potential_savings_kg": round(savings_kg, 2),
                        "savings_percent": round(
                            (savings_kg / current_kg * 100) if current_kg > 0 else 0, 1
                        ),
                    })

            # Recommend consolidation for over-provisioned components
            if comp.replicas > 2 and comp.utilization() < 30:
                reduced_replicas = max(2, comp.replicas - 1)
                savings_kg = (
                    (comp.replicas - reduced_replicas)
                    * _HOURS_PER_YEAR
                    * current_factor
                    / _G_PER_KG
                )
                recommendations.append({
                    "recommendation": (
                        f"Consolidate {comp.name}: reduce replicas from "
                        f"{comp.replicas} to {reduced_replicas} "
                        f"(utilization at {comp.utilization():.0f}%)"
                    ),
                    "component": comp_id,
                    "current_replicas": comp.replicas,
                    "suggested_replicas": reduced_replicas,
                    "potential_savings_kg": round(savings_kg, 2),
                })

            # Recommend spot/preemptible instances for non-critical workloads
            if comp.type.value in ("app_server", "web_server") and comp.replicas > 1:
                # Spot instances can reduce carbon through better utilization
                spot_savings_kg = current_kg * 0.15  # ~15% efficiency gain
                recommendations.append({
                    "recommendation": (
                        f"Use spot/preemptible instances for {comp.name} "
                        f"to improve utilization efficiency"
                    ),
                    "component": comp_id,
                    "potential_savings_kg": round(spot_savings_kg, 2),
                })

        # Sort by savings potential descending
        recommendations.sort(
            key=lambda r: r.get("potential_savings_kg", 0),
            reverse=True,
        )

        return recommendations

    def _calculate_sustainability_score(
        self, per_component: dict[str, float],
    ) -> float:
        """Calculate a sustainability score (0-100).

        Scoring factors:
        - Region carbon intensity (lower is better)
        - Utilization efficiency (higher is better - less waste)
        - Component-to-replica ratio (fewer replicas per component is better)

        100 = perfectly green, 0 = worst possible.
        """
        if not self.graph.components:
            return 100.0

        scores: list[float] = []

        for comp_id, comp in self.graph.components.items():
            region = comp.region.region if comp.region.region else "default"
            factor = CARBON_FACTORS_G_PER_CPU_HOUR.get(
                region, CARBON_FACTORS_G_PER_CPU_HOUR["default"]
            )

            # Region score: map factor to 0-100 scale
            # 0.05 = 100 (greenest), 0.60 = 0 (dirtiest)
            max_factor = 0.60
            min_factor = 0.05
            if factor <= min_factor:
                region_score = 100.0
            elif factor >= max_factor:
                region_score = 0.0
            else:
                region_score = (1.0 - (factor - min_factor) / (max_factor - min_factor)) * 100.0

            # Utilization score: higher utilization = less waste
            util = comp.utilization()
            if util < 10:
                util = 40.0  # estimated for components without metrics
            util_score = min(100.0, util * 1.5)  # 67% utilization = 100 score

            # Combine: 60% region, 40% utilization
            component_score = region_score * 0.6 + util_score * 0.4
            scores.append(component_score)

        return sum(scores) / len(scores) if scores else 100.0
