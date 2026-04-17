# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Bus Factor Analyzer — Organizational / Personnel Risk Detection.

Calculates the "bus factor" of an infrastructure system: how many people
need to leave before the system becomes unmanageable.

Algorithm:
1. For each component, look up its ``owner`` field.
2. Group components by owner.
3. For each owner, compute the total number of direct dependents across
   all their components (= impact scope if they leave).
4. ``impact_if_leaves`` is the percentage of all system components that
   would be directly affected.
5. ``bus_factor`` = minimum number of people whose departure would leave
   ≥ 50 % of components unowned.
6. ``risk_score`` = 100 × (1-person-owned components / total components).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph

# ---------------------------------------------------------------------------
# Risk-level thresholds (impact_if_leaves, 0-100)
# ---------------------------------------------------------------------------
_CRITICAL_THRESHOLD = 50.0   # >50% impact → critical
_HIGH_THRESHOLD = 25.0       # >25% impact → high
_MEDIUM_THRESHOLD = 10.0     # >10% impact → medium


def _risk_level(impact: float) -> str:
    if impact >= _CRITICAL_THRESHOLD:
        return "critical"
    if impact >= _HIGH_THRESHOLD:
        return "high"
    if impact >= _MEDIUM_THRESHOLD:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PersonRisk:
    """Risk profile for a single person (owner)."""

    owner: str
    components: list[str]
    total_dependents: int
    impact_if_leaves: float   # 0-100, percentage of total components affected
    risk_level: str           # critical / high / medium / low

    def to_dict(self) -> dict:
        return {
            "owner": self.owner,
            "components": self.components,
            "total_dependents": self.total_dependents,
            "impact_if_leaves": round(self.impact_if_leaves, 1),
            "risk_level": self.risk_level,
        }


@dataclass
class BusFactorReport:
    """Aggregated bus factor analysis result."""

    bus_factor: int                      # min people whose exit makes system unmanageable
    people_risks: list[PersonRisk] = field(default_factory=list)
    unowned_components: list[str] = field(default_factory=list)
    single_owner_components: list[str] = field(default_factory=list)
    risk_score: float = 0.0              # 0-100, higher = more personnel risk
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "bus_factor": self.bus_factor,
            "risk_score": round(self.risk_score, 1),
            "summary": self.summary,
            "unowned_components": self.unowned_components,
            "single_owner_components": self.single_owner_components,
            "people_risks": [p.to_dict() for p in self.people_risks],
        }


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class BusFactorAnalyzer:
    """Analyze personnel / ownership concentration risk in an InfraGraph."""

    def analyze(self, graph: InfraGraph) -> BusFactorReport:
        """Run bus-factor analysis on *graph*.

        Args:
            graph: The infrastructure graph to inspect.

        Returns:
            A :class:`BusFactorReport` with per-person risk profiles and
            aggregate bus-factor metrics.
        """
        components = graph.components
        total = len(components)

        if total == 0:
            return BusFactorReport(
                bus_factor=0,
                risk_score=0.0,
                summary="No components found.",
            )

        # --- Collect ownership data ---
        owner_to_comp_ids: dict[str, list[str]] = {}
        unowned: list[str] = []

        for comp_id, comp in components.items():
            owner = (comp.owner or "").strip()
            if not owner:
                unowned.append(comp_id)
                continue
            owner_to_comp_ids.setdefault(owner, []).append(comp_id)

        # --- Identify single-owner components ---
        # A component is "single-owner" when exactly 1 person owns it
        # (i.e., all components in this system since we track per-owner).
        # Here: a component is "single-owner" when its owner appears only
        # for that component (owner owns exactly 1 component).
        single_owner_components: list[str] = [
            comp_ids[0]
            for comp_ids in owner_to_comp_ids.values()
            if len(comp_ids) == 1
        ]

        # --- Build PersonRisk entries ---
        people_risks: list[PersonRisk] = []
        for owner, comp_ids in owner_to_comp_ids.items():
            # Count unique dependents across all owned components
            affected_ids: set[str] = set()
            for cid in comp_ids:
                for dep in graph.get_dependents(cid):
                    if dep.id not in comp_ids:   # don't double-count own comps
                        affected_ids.add(dep.id)

            impact = (len(affected_ids) / total) * 100.0 if total > 0 else 0.0
            people_risks.append(
                PersonRisk(
                    owner=owner,
                    components=list(comp_ids),
                    total_dependents=len(affected_ids),
                    impact_if_leaves=round(impact, 1),
                    risk_level=_risk_level(impact),
                )
            )

        # Sort by impact descending
        people_risks.sort(key=lambda p: p.impact_if_leaves, reverse=True)

        # --- Bus factor ---
        # Minimum number of owners to remove to leave ≥ 50% of components unowned.
        owned_component_count = sum(len(ids) for ids in owner_to_comp_ids.values())
        threshold = owned_component_count * 0.5

        # Sort owners by number of components managed (most → least)
        sorted_owners = sorted(
            owner_to_comp_ids.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )
        accumulated = 0
        bus_factor = 0
        for _, comp_ids in sorted_owners:
            accumulated += len(comp_ids)
            bus_factor += 1
            if accumulated >= threshold:
                break

        # If no owners exist at all, bus_factor = 0
        if not owner_to_comp_ids:
            bus_factor = 0

        # --- Risk score ---
        # Based on: proportion of components only one person knows about.
        if total > 0:
            risk_score = (len(single_owner_components) / total) * 100.0
        else:
            risk_score = 0.0

        # Boost risk score for very low bus factor
        if bus_factor == 1 and risk_score < 60.0:
            risk_score = max(risk_score, 60.0)

        risk_score = min(100.0, risk_score)

        # --- Summary ---
        n_owners = len(owner_to_comp_ids)
        summary = (
            f"{total} component(s) analysed across {n_owners} owner(s). "
            f"Bus factor: {bus_factor}. "
            f"{len(single_owner_components)} component(s) known only to one person. "
            f"{len(unowned)} unowned. "
            f"Risk score: {risk_score:.1f}/100."
        )

        return BusFactorReport(
            bus_factor=bus_factor,
            people_risks=people_risks,
            unowned_components=unowned,
            single_owner_components=single_owner_components,
            risk_score=risk_score,
            summary=summary,
        )
