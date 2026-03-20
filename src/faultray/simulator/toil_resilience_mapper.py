# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Toil-Resilience Mapper — maps operational toil to resilience gaps.

Answers questions like "you're spending 40% of toil on DNS issues BECAUSE
your DNS has no redundancy." Quantifies the ROI of resilience improvements
in terms of toil reduction.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component
from faultray.model.graph import InfraGraph


class ToilCategory(str, Enum):
    """Categories of operational toil that map to resilience gaps."""

    INCIDENT_RESPONSE = "incident_response"
    MANUAL_SCALING = "manual_scaling"
    CONFIG_DRIFT_FIX = "config_drift_fix"
    CERTIFICATE_RENEWAL = "certificate_renewal"
    BACKUP_RESTORE = "backup_restore"
    FAILOVER_MANUAL = "failover_manual"
    LOG_INVESTIGATION = "log_investigation"
    RESTART_SERVICE = "restart_service"
    CAPACITY_PLANNING = "capacity_planning"
    PATCH_MANAGEMENT = "patch_management"


class ToilEntry(BaseModel):
    """A single toil entry reported by the operations team."""

    category: ToilCategory
    component_id: str
    hours_per_month: float = Field(ge=0)
    frequency_per_month: int = Field(ge=0)
    automatable: bool = True
    description: str = ""


class ResilienceGap(BaseModel):
    """A detected gap in infrastructure resilience."""

    component_id: str
    gap_type: str  # no_redundancy, no_autoscaling, no_circuit_breaker, no_failover, high_utilization
    severity: float = Field(ge=0, le=1)
    description: str = ""


class ToilResilienceLink(BaseModel):
    """Links a toil entry to a resilience gap with causation analysis."""

    toil_entry: ToilEntry
    resilience_gap: ResilienceGap
    causation_strength: float = Field(ge=0, le=1)
    estimated_toil_reduction_percent: float = Field(ge=0, le=100)
    recommended_fix: str = ""


class ROIAnalysis(BaseModel):
    """ROI analysis for a recommended resilience fix."""

    fix_description: str
    implementation_cost_hours: float
    monthly_toil_saved_hours: float
    payback_period_months: float
    annual_savings_hours: float
    priority_score: float


class ToilResilienceReport(BaseModel):
    """Full report mapping toil to resilience gaps with ROI analysis."""

    total_toil_hours_per_month: float
    toil_by_category: dict[str, float]
    top_links: list[ToilResilienceLink]
    roi_analyses: list[ROIAnalysis]
    automatable_percent: float
    recommendations: list[str]


# Mapping rules: toil category -> gap types with causation strengths
_CATEGORY_GAP_MAP: dict[ToilCategory, list[tuple[str, float]]] = {
    ToilCategory.INCIDENT_RESPONSE: [("no_failover", 0.9), ("no_circuit_breaker", 0.8)],
    ToilCategory.MANUAL_SCALING: [("no_autoscaling", 0.95)],
    ToilCategory.CONFIG_DRIFT_FIX: [("high_utilization", 0.5)],
    ToilCategory.CERTIFICATE_RENEWAL: [("no_redundancy", 0.3)],
    ToilCategory.BACKUP_RESTORE: [("no_redundancy", 0.4)],
    ToilCategory.FAILOVER_MANUAL: [("no_failover", 0.95)],
    ToilCategory.LOG_INVESTIGATION: [("no_circuit_breaker", 0.3)],
    ToilCategory.RESTART_SERVICE: [("no_redundancy", 0.85)],
    ToilCategory.CAPACITY_PLANNING: [("no_autoscaling", 0.8), ("high_utilization", 0.7)],
    ToilCategory.PATCH_MANAGEMENT: [("no_redundancy", 0.3)],
}

# Estimated toil reduction when the gap is fixed
_REDUCTION_MAP: dict[str, float] = {
    "no_redundancy": 70.0,
    "no_autoscaling": 85.0,
    "no_circuit_breaker": 60.0,
    "no_failover": 80.0,
    "high_utilization": 50.0,
}

# Implementation cost estimates (hours)
_FIX_COST_MAP: dict[str, float] = {
    "no_redundancy": 16.0,
    "no_autoscaling": 12.0,
    "no_circuit_breaker": 8.0,
    "no_failover": 20.0,
    "high_utilization": 10.0,
}

_FIX_DESCRIPTIONS: dict[str, str] = {
    "no_redundancy": "Add redundant replicas",
    "no_autoscaling": "Enable autoscaling",
    "no_circuit_breaker": "Add circuit breakers",
    "no_failover": "Enable automatic failover",
    "high_utilization": "Optimize capacity and reduce utilization",
}


class ToilResilienceMapper:
    """Maps operational toil to resilience gaps and calculates ROI."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._toil_entries: list[ToilEntry] = []

    def add_toil(self, entry: ToilEntry) -> None:
        """Add a toil entry."""
        self._toil_entries.append(entry)

    def detect_resilience_gaps(self) -> list[ResilienceGap]:
        """Analyze the infrastructure graph for resilience gaps."""
        gaps: list[ResilienceGap] = []
        for comp in self._graph.components.values():
            gaps.extend(self._detect_component_gaps(comp))
        return gaps

    def _detect_component_gaps(self, comp: Component) -> list[ResilienceGap]:
        """Detect resilience gaps for a single component."""
        gaps: list[ResilienceGap] = []

        # No redundancy: single replica, no failover
        if comp.replicas <= 1 and not comp.failover.enabled:
            dependents = self._graph.get_dependents(comp.id)
            severity = min(1.0, 0.5 + len(dependents) * 0.1)
            gaps.append(ResilienceGap(
                component_id=comp.id,
                gap_type="no_redundancy",
                severity=severity,
                description=f"{comp.name} has no redundancy (1 replica, no failover)",
            ))

        # No autoscaling
        if not comp.autoscaling.enabled:
            severity = 0.6 if comp.replicas > 1 else 0.8
            gaps.append(ResilienceGap(
                component_id=comp.id,
                gap_type="no_autoscaling",
                severity=severity,
                description=f"{comp.name} has no autoscaling configured",
            ))

        # No failover
        if not comp.failover.enabled:
            dependents = self._graph.get_dependents(comp.id)
            severity = min(1.0, 0.4 + len(dependents) * 0.15)
            gaps.append(ResilienceGap(
                component_id=comp.id,
                gap_type="no_failover",
                severity=severity,
                description=f"{comp.name} has no automatic failover",
            ))

        # No circuit breaker on incoming edges
        all_edges = self._graph.all_dependency_edges()
        has_cb = any(
            e.target_id == comp.id and e.circuit_breaker.enabled
            for e in all_edges
        )
        if not has_cb and self._graph.get_dependents(comp.id):
            gaps.append(ResilienceGap(
                component_id=comp.id,
                gap_type="no_circuit_breaker",
                severity=0.6,
                description=f"{comp.name} has no circuit breaker protection",
            ))

        # High utilization
        util = comp.utilization()
        if util > 70:
            severity = min(1.0, (util - 70) / 30)
            gaps.append(ResilienceGap(
                component_id=comp.id,
                gap_type="high_utilization",
                severity=severity,
                description=f"{comp.name} has high utilization ({util:.0f}%)",
            ))

        return gaps

    def map_toil_to_gaps(self) -> list[ToilResilienceLink]:
        """Correlate toil entries to detected resilience gaps."""
        gaps = self.detect_resilience_gaps()
        gap_by_component: dict[str, list[ResilienceGap]] = {}
        for gap in gaps:
            gap_by_component.setdefault(gap.component_id, []).append(gap)

        links: list[ToilResilienceLink] = []
        for entry in self._toil_entries:
            comp_gaps = gap_by_component.get(entry.component_id, [])
            category_gap_types = _CATEGORY_GAP_MAP.get(entry.category, [])

            for gap in comp_gaps:
                for gap_type, strength in category_gap_types:
                    if gap.gap_type == gap_type:
                        reduction = _REDUCTION_MAP.get(gap_type, 30.0)
                        fix_desc = _FIX_DESCRIPTIONS.get(
                            gap_type, f"Fix {gap_type} for {entry.component_id}"
                        )
                        links.append(ToilResilienceLink(
                            toil_entry=entry,
                            resilience_gap=gap,
                            causation_strength=strength,
                            estimated_toil_reduction_percent=reduction,
                            recommended_fix=fix_desc,
                        ))

        # Sort by causation_strength * toil hours descending
        links.sort(
            key=lambda lnk: lnk.causation_strength * lnk.toil_entry.hours_per_month,
            reverse=True,
        )
        return links

    def calculate_roi(
        self, link: ToilResilienceLink, implementation_hours: float
    ) -> ROIAnalysis:
        """Calculate ROI for fixing a specific toil-resilience link."""
        monthly_saved = (
            link.toil_entry.hours_per_month
            * link.estimated_toil_reduction_percent
            / 100.0
        )
        if monthly_saved > 0:
            payback = implementation_hours / monthly_saved
        else:
            payback = float("inf")

        annual_savings = monthly_saved * 12.0
        # Priority: higher savings and lower cost = higher priority
        if implementation_hours > 0:
            priority = (annual_savings / implementation_hours) * link.causation_strength
        else:
            priority = annual_savings * link.causation_strength

        return ROIAnalysis(
            fix_description=link.recommended_fix,
            implementation_cost_hours=implementation_hours,
            monthly_toil_saved_hours=round(monthly_saved, 2),
            payback_period_months=round(payback, 2),
            annual_savings_hours=round(annual_savings, 2),
            priority_score=round(priority, 2),
        )

    def generate_report(self) -> ToilResilienceReport:
        """Generate a full toil-resilience mapping report with ROI analysis."""
        links = self.map_toil_to_gaps()

        total_hours = sum(e.hours_per_month for e in self._toil_entries)
        automatable_hours = sum(
            e.hours_per_month for e in self._toil_entries if e.automatable
        )
        automatable_pct = (
            (automatable_hours / total_hours * 100.0) if total_hours > 0 else 0.0
        )

        toil_by_cat: dict[str, float] = {}
        for entry in self._toil_entries:
            key = entry.category.value
            toil_by_cat[key] = toil_by_cat.get(key, 0.0) + entry.hours_per_month

        # Calculate ROI for each link using default cost estimates
        roi_analyses: list[ROIAnalysis] = []
        seen_fixes: set[str] = set()
        for link in links:
            fix_key = f"{link.resilience_gap.component_id}:{link.resilience_gap.gap_type}"
            if fix_key in seen_fixes:
                continue
            seen_fixes.add(fix_key)
            cost = _FIX_COST_MAP.get(link.resilience_gap.gap_type, 16.0)
            roi_analyses.append(self.calculate_roi(link, cost))

        roi_analyses.sort(key=lambda r: r.priority_score, reverse=True)

        recommendations: list[str] = []
        for roi in roi_analyses[:5]:
            if roi.payback_period_months < float("inf"):
                recommendations.append(
                    f"{roi.fix_description}: saves {roi.monthly_toil_saved_hours:.1f}h/month, "
                    f"pays back in {roi.payback_period_months:.1f} months"
                )
            else:
                recommendations.append(
                    f"{roi.fix_description}: implementation cost {roi.implementation_cost_hours:.0f}h"
                )

        return ToilResilienceReport(
            total_toil_hours_per_month=round(total_hours, 2),
            toil_by_category=toil_by_cat,
            top_links=links,
            roi_analyses=roi_analyses,
            automatable_percent=round(automatable_pct, 2),
            recommendations=recommendations,
        )
