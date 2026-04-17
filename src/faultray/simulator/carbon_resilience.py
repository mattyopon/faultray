# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Carbon-Aware Resilience Engine.

Quantifies the environmental cost of resilience decisions.  Shows trade-offs
such as "adding a standby replica improves RTO by 25 minutes but increases
CO2 by 12%."  Generates ESG-ready sustainability reports for infrastructure
resilience configurations.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PowerSource(str, Enum):
    GRID_AVERAGE = "grid_average"
    RENEWABLE = "renewable"
    FOSSIL = "fossil"
    NUCLEAR = "nuclear"
    MIXED = "mixed"


class CarbonIntensityRegion(str, Enum):
    US_EAST = "us_east"
    US_WEST = "us_west"
    EU_WEST = "eu_west"
    EU_NORTH = "eu_north"
    ASIA_EAST = "asia_east"
    ASIA_SOUTH = "asia_south"


# Default carbon intensities (gCO2 / kWh) per region.
DEFAULT_CARBON_INTENSITY: dict[CarbonIntensityRegion, float] = {
    CarbonIntensityRegion.US_EAST: 386.0,
    CarbonIntensityRegion.US_WEST: 210.0,
    CarbonIntensityRegion.EU_WEST: 275.0,
    CarbonIntensityRegion.EU_NORTH: 30.0,
    CarbonIntensityRegion.ASIA_EAST: 550.0,
    CarbonIntensityRegion.ASIA_SOUTH: 710.0,
}

# Hours in one year.
_HOURS_PER_YEAR = 8766.0  # 365.25 * 24

# Watts to kilowatts.
_W_TO_KW = 1000.0


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CarbonProfile(BaseModel):
    """Power / carbon profile for a single infrastructure component."""

    component_id: str
    power_consumption_watts: float
    carbon_intensity_gco2_per_kwh: float
    region: CarbonIntensityRegion
    power_source: PowerSource
    pue: float = Field(default=1.2, description="Power Usage Effectiveness")


class CarbonFootprint(BaseModel):
    """Calculated annual carbon footprint for a component."""

    component_id: str
    annual_kwh: float
    annual_co2_kg: float
    per_replica_co2_kg: float
    total_with_replicas_co2_kg: float


class ResilienceCarbonTradeoff(BaseModel):
    """Trade-off analysis between a resilience change and its carbon cost."""

    change_description: str
    resilience_improvement: float
    carbon_increase_percent: float
    carbon_increase_kg: float
    efficiency_ratio: float


class CarbonOptimization(BaseModel):
    """A single optimization recommendation."""

    recommendation: str
    current_co2_kg: float
    optimized_co2_kg: float
    savings_percent: float
    resilience_impact: str


class CarbonResilienceReport(BaseModel):
    """Full ESG-ready carbon-resilience report."""

    total_annual_co2_kg: float
    co2_per_component: list[CarbonFootprint]
    tradeoffs: list[ResilienceCarbonTradeoff]
    optimizations: list[CarbonOptimization]
    esg_summary: str
    carbon_efficiency_score: float = Field(
        default=0.0, ge=0.0, le=100.0,
    )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CarbonResilienceEngine:
    """Main engine for carbon-aware resilience analysis.

    Parameters
    ----------
    graph:
        The infrastructure graph to analyse.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self.carbon_intensities: dict[CarbonIntensityRegion, float] = dict(
            DEFAULT_CARBON_INTENSITY,
        )

    # -- public API ----------------------------------------------------------

    def calculate_footprint(
        self,
        component_id: str,
        profile: CarbonProfile,
    ) -> CarbonFootprint:
        """Calculate the annual carbon footprint for one component."""
        comp = self.graph.get_component(component_id)
        replicas = comp.replicas if comp else 1

        per_replica_kwh = (
            profile.power_consumption_watts / _W_TO_KW
            * _HOURS_PER_YEAR
            * profile.pue
        )

        per_replica_co2_kg = (
            per_replica_kwh * profile.carbon_intensity_gco2_per_kwh / _W_TO_KW
        )

        total_co2_kg = per_replica_co2_kg * replicas

        return CarbonFootprint(
            component_id=component_id,
            annual_kwh=per_replica_kwh * replicas,
            annual_co2_kg=per_replica_co2_kg,
            per_replica_co2_kg=per_replica_co2_kg,
            total_with_replicas_co2_kg=total_co2_kg,
        )

    def analyze_tradeoff(
        self,
        change: str,
        before_replicas: int,
        after_replicas: int,
        profile: CarbonProfile,
        resilience_delta: float,
    ) -> ResilienceCarbonTradeoff:
        """Analyse the carbon trade-off of a resilience change."""
        per_replica_kwh = (
            profile.power_consumption_watts / _W_TO_KW
            * _HOURS_PER_YEAR
            * profile.pue
        )
        per_replica_co2_kg = (
            per_replica_kwh * profile.carbon_intensity_gco2_per_kwh / _W_TO_KW
        )

        before_co2 = per_replica_co2_kg * before_replicas
        after_co2 = per_replica_co2_kg * after_replicas

        carbon_increase_kg = after_co2 - before_co2
        carbon_increase_pct = (
            (carbon_increase_kg / before_co2 * 100.0) if before_co2 > 0 else 0.0
        )

        efficiency = (
            resilience_delta / carbon_increase_pct
            if carbon_increase_pct != 0.0
            else 0.0
        )

        return ResilienceCarbonTradeoff(
            change_description=change,
            resilience_improvement=resilience_delta,
            carbon_increase_percent=carbon_increase_pct,
            carbon_increase_kg=carbon_increase_kg,
            efficiency_ratio=efficiency,
        )

    def suggest_optimizations(
        self,
        profiles: list[CarbonProfile],
    ) -> list[CarbonOptimization]:
        """Suggest carbon-saving optimizations for the given profiles."""
        optimizations: list[CarbonOptimization] = []

        for profile in profiles:
            current_co2 = self._single_co2_kg(profile)

            # 1. Region migration to EU_NORTH (lowest intensity)
            if profile.region != CarbonIntensityRegion.EU_NORTH:
                best_intensity = self.carbon_intensities[
                    CarbonIntensityRegion.EU_NORTH
                ]
                optimized_co2 = self._co2_with_intensity(profile, best_intensity)
                savings = (
                    ((current_co2 - optimized_co2) / current_co2 * 100.0)
                    if current_co2 > 0
                    else 0.0
                )
                optimizations.append(CarbonOptimization(
                    recommendation=(
                        f"Migrate {profile.component_id} to EU_NORTH "
                        f"(low-carbon region)"
                    ),
                    current_co2_kg=current_co2,
                    optimized_co2_kg=optimized_co2,
                    savings_percent=savings,
                    resilience_impact="Possible latency increase for non-EU users",
                ))

            # 2. Switch to renewable power
            if profile.power_source != PowerSource.RENEWABLE:
                optimized_co2 = current_co2 * 0.1  # ~90% reduction
                savings = (
                    ((current_co2 - optimized_co2) / current_co2 * 100.0)
                    if current_co2 > 0
                    else 0.0
                )
                optimizations.append(CarbonOptimization(
                    recommendation=(
                        f"Switch {profile.component_id} to renewable power"
                    ),
                    current_co2_kg=current_co2,
                    optimized_co2_kg=optimized_co2,
                    savings_percent=savings,
                    resilience_impact="No resilience impact",
                ))

            # 3. Improve PUE
            if profile.pue > 1.1:
                optimized_pue = 1.1
                optimized_co2 = current_co2 * (optimized_pue / profile.pue)
                savings = (
                    ((current_co2 - optimized_co2) / current_co2 * 100.0)
                    if current_co2 > 0
                    else 0.0
                )
                optimizations.append(CarbonOptimization(
                    recommendation=(
                        f"Improve PUE for {profile.component_id} "
                        f"from {profile.pue} to {optimized_pue}"
                    ),
                    current_co2_kg=current_co2,
                    optimized_co2_kg=optimized_co2,
                    savings_percent=savings,
                    resilience_impact="No resilience impact",
                ))

        return optimizations

    def calculate_total_footprint(
        self,
        profiles: list[CarbonProfile],
    ) -> float:
        """Return total annual CO2 in kg across all profiles."""
        total = 0.0
        for profile in profiles:
            fp = self.calculate_footprint(profile.component_id, profile)
            total += fp.total_with_replicas_co2_kg
        return total

    def generate_report(
        self,
        profiles: list[CarbonProfile],
    ) -> CarbonResilienceReport:
        """Generate a comprehensive ESG-ready carbon-resilience report."""
        footprints: list[CarbonFootprint] = []
        for profile in profiles:
            footprints.append(
                self.calculate_footprint(profile.component_id, profile),
            )

        total_co2 = sum(fp.total_with_replicas_co2_kg for fp in footprints)
        optimizations = self.suggest_optimizations(profiles)

        # Build a default trade-off for each component that has replicas > 1
        tradeoffs: list[ResilienceCarbonTradeoff] = []
        for profile in profiles:
            comp = self.graph.get_component(profile.component_id)
            if comp and comp.replicas > 1:
                tradeoffs.append(
                    self.analyze_tradeoff(
                        change=f"Remove 1 replica from {profile.component_id}",
                        before_replicas=comp.replicas,
                        after_replicas=comp.replicas - 1,
                        profile=profile,
                        resilience_delta=-10.0,
                    ),
                )

        score = self._carbon_efficiency_score(profiles)

        esg_summary = (
            f"Total annual CO2: {total_co2:.1f} kg. "
            f"Carbon efficiency score: {score:.1f}/100. "
            f"{len(optimizations)} optimization(s) identified."
        )

        return CarbonResilienceReport(
            total_annual_co2_kg=total_co2,
            co2_per_component=footprints,
            tradeoffs=tradeoffs,
            optimizations=optimizations,
            esg_summary=esg_summary,
            carbon_efficiency_score=score,
        )

    # -- private helpers -----------------------------------------------------

    def _single_co2_kg(self, profile: CarbonProfile) -> float:
        """CO2 in kg for a *single* replica of the given profile."""
        kwh = (
            profile.power_consumption_watts / _W_TO_KW
            * _HOURS_PER_YEAR
            * profile.pue
        )
        return kwh * profile.carbon_intensity_gco2_per_kwh / _W_TO_KW

    def _co2_with_intensity(
        self,
        profile: CarbonProfile,
        intensity: float,
    ) -> float:
        """CO2 in kg for a single replica using a different intensity."""
        kwh = (
            profile.power_consumption_watts / _W_TO_KW
            * _HOURS_PER_YEAR
            * profile.pue
        )
        return kwh * intensity / _W_TO_KW

    def _carbon_efficiency_score(
        self,
        profiles: list[CarbonProfile],
    ) -> float:
        """Compute a 0-100 carbon efficiency score.

        Scoring logic:
        - Lower carbon intensity → higher score
        - Renewable power source → bonus
        - Better PUE → bonus

        100 = best-possible (EU_NORTH + renewable + PUE 1.0)
        0   = worst-possible (ASIA_SOUTH + fossil + PUE ≥ 2.0)
        """
        if not profiles:
            return 100.0

        scores: list[float] = []
        max_intensity = max(self.carbon_intensities.values())  # 710
        min_intensity = min(self.carbon_intensities.values())  # 30

        for profile in profiles:
            # Region score (0-50)
            intensity = profile.carbon_intensity_gco2_per_kwh
            if max_intensity == min_intensity:
                region_score = 50.0
            else:
                region_score = (
                    (1.0 - (intensity - min_intensity)
                     / (max_intensity - min_intensity))
                    * 50.0
                )
            region_score = max(0.0, min(50.0, region_score))

            # Power source score (0-30)
            power_scores = {
                PowerSource.RENEWABLE: 30.0,
                PowerSource.NUCLEAR: 25.0,
                PowerSource.MIXED: 15.0,
                PowerSource.GRID_AVERAGE: 10.0,
                PowerSource.FOSSIL: 0.0,
            }
            power_score = power_scores.get(profile.power_source, 10.0)

            # PUE score (0-20): PUE 1.0 → 20, PUE 2.0+ → 0
            pue_score = max(0.0, min(20.0, (2.0 - profile.pue) * 20.0))

            scores.append(region_score + power_score + pue_score)

        raw = sum(scores) / len(scores)
        return max(0.0, min(100.0, raw))
