# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Toil calculator — measure and track operational toil.

Implements Google SRE's toil measurement framework to identify
manual, repetitive, automatable, tactical, and devoid-of-enduring-value
operational work in infrastructure management.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


class ToilCategory(str, Enum):
    """Categories of operational toil."""

    MANUAL_SCALING = "manual_scaling"
    MANUAL_FAILOVER = "manual_failover"
    ALERT_RESPONSE = "alert_response"
    LOG_REVIEW = "log_review"
    CERT_ROTATION = "cert_rotation"
    BACKUP_VERIFICATION = "backup_verification"
    DEPENDENCY_UPDATES = "dependency_updates"
    CAPACITY_PLANNING = "capacity_planning"
    CONFIG_MANAGEMENT = "config_management"
    INCIDENT_RESPONSE = "incident_response"


class AutomationPotential(str, Enum):
    """How easily the toil can be automated."""

    FULLY_AUTOMATABLE = "fully_automatable"
    PARTIALLY_AUTOMATABLE = "partially_automatable"
    REQUIRES_JUDGMENT = "requires_judgment"
    NOT_AUTOMATABLE = "not_automatable"


@dataclass
class ToilItem:
    """A single source of operational toil."""

    component_id: str
    component_name: str
    category: ToilCategory
    description: str
    hours_per_month: float
    automation_potential: AutomationPotential
    automation_savings_percent: float  # 0-100
    priority: str  # "critical", "high", "medium", "low"


@dataclass
class ToilReport:
    """Full toil analysis report."""

    toil_items: list[ToilItem]
    total_hours_per_month: float
    automatable_hours: float
    toil_percent: float  # % of total ops time spent on toil
    toil_score: float  # 0-100 (100 = no toil)
    top_toil_sources: list[str]
    automation_recommendations: list[str]
    estimated_savings_hours: float


# Default hours estimates per toil activity
_TOIL_ESTIMATES: dict[ToilCategory, float] = {
    ToilCategory.MANUAL_SCALING: 4.0,
    ToilCategory.MANUAL_FAILOVER: 2.0,
    ToilCategory.ALERT_RESPONSE: 8.0,
    ToilCategory.LOG_REVIEW: 6.0,
    ToilCategory.CERT_ROTATION: 1.0,
    ToilCategory.BACKUP_VERIFICATION: 2.0,
    ToilCategory.DEPENDENCY_UPDATES: 4.0,
    ToilCategory.CAPACITY_PLANNING: 3.0,
    ToilCategory.CONFIG_MANAGEMENT: 5.0,
    ToilCategory.INCIDENT_RESPONSE: 10.0,
}


class ToilCalculator:
    """Calculate operational toil from infrastructure configuration."""

    def __init__(self, monthly_ops_hours: float = 160.0) -> None:
        self._monthly_ops_hours = monthly_ops_hours

    def analyze(self, graph: InfraGraph) -> ToilReport:
        """Analyze infrastructure for operational toil."""
        if not graph.components:
            return ToilReport(
                toil_items=[],
                total_hours_per_month=0,
                automatable_hours=0,
                toil_percent=0,
                toil_score=100.0,
                top_toil_sources=[],
                automation_recommendations=[],
                estimated_savings_hours=0,
            )

        items: list[ToilItem] = []

        for comp in graph.components.values():
            items.extend(self._analyze_component(graph, comp))

        total_hours = sum(i.hours_per_month for i in items)
        automatable = sum(
            i.hours_per_month * (i.automation_savings_percent / 100)
            for i in items
        )
        toil_pct = (total_hours / self._monthly_ops_hours * 100) if self._monthly_ops_hours > 0 else 0
        toil_score = max(0, 100 - toil_pct * 2)  # Penalize 2 points per % of toil

        # Sort by hours descending
        items.sort(key=lambda i: i.hours_per_month, reverse=True)

        top_sources = list(dict.fromkeys(i.category.value for i in items[:5]))
        recommendations = self._generate_recommendations(items)

        return ToilReport(
            toil_items=items,
            total_hours_per_month=round(total_hours, 1),
            automatable_hours=round(automatable, 1),
            toil_percent=round(toil_pct, 1),
            toil_score=round(toil_score, 1),
            top_toil_sources=top_sources,
            automation_recommendations=recommendations,
            estimated_savings_hours=round(automatable, 1),
        )

    def _analyze_component(self, graph: InfraGraph, comp) -> list[ToilItem]:
        """Analyze toil for a single component."""
        items: list[ToilItem] = []

        # Manual scaling (no autoscaling)
        if not comp.autoscaling.enabled and comp.replicas > 1:
            items.append(ToilItem(
                component_id=comp.id,
                component_name=comp.name,
                category=ToilCategory.MANUAL_SCALING,
                description=f"{comp.name} requires manual scaling ({comp.replicas} replicas, no autoscaling)",
                hours_per_month=_TOIL_ESTIMATES[ToilCategory.MANUAL_SCALING],
                automation_potential=AutomationPotential.FULLY_AUTOMATABLE,
                automation_savings_percent=90,
                priority="high",
            ))

        # Manual failover
        if not comp.failover.enabled:
            dependents = graph.get_dependents(comp.id)
            if dependents:
                items.append(ToilItem(
                    component_id=comp.id,
                    component_name=comp.name,
                    category=ToilCategory.MANUAL_FAILOVER,
                    description=f"{comp.name} has no automatic failover ({len(dependents)} dependents)",
                    hours_per_month=_TOIL_ESTIMATES[ToilCategory.MANUAL_FAILOVER],
                    automation_potential=AutomationPotential.FULLY_AUTOMATABLE,
                    automation_savings_percent=95,
                    priority="critical" if len(dependents) > 2 else "high",
                ))

        # Alert response (more alerts for unhealthy components)
        if comp.health in (HealthStatus.DEGRADED, HealthStatus.OVERLOADED):
            items.append(ToilItem(
                component_id=comp.id,
                component_name=comp.name,
                category=ToilCategory.ALERT_RESPONSE,
                description=f"{comp.name} is {comp.health.value}, generating frequent alerts",
                hours_per_month=_TOIL_ESTIMATES[ToilCategory.ALERT_RESPONSE],
                automation_potential=AutomationPotential.PARTIALLY_AUTOMATABLE,
                automation_savings_percent=50,
                priority="high",
            ))
        elif comp.health == HealthStatus.DOWN:
            items.append(ToilItem(
                component_id=comp.id,
                component_name=comp.name,
                category=ToilCategory.INCIDENT_RESPONSE,
                description=f"{comp.name} is DOWN, requiring incident response",
                hours_per_month=_TOIL_ESTIMATES[ToilCategory.INCIDENT_RESPONSE],
                automation_potential=AutomationPotential.REQUIRES_JUDGMENT,
                automation_savings_percent=30,
                priority="critical",
            ))

        # Log review (no monitoring)
        if not comp.security.log_enabled:
            items.append(ToilItem(
                component_id=comp.id,
                component_name=comp.name,
                category=ToilCategory.LOG_REVIEW,
                description=f"{comp.name} has no automated log monitoring",
                hours_per_month=_TOIL_ESTIMATES[ToilCategory.LOG_REVIEW],
                automation_potential=AutomationPotential.FULLY_AUTOMATABLE,
                automation_savings_percent=80,
                priority="medium",
            ))

        # Backup verification (data stores without backups)
        if comp.type in (ComponentType.DATABASE, ComponentType.STORAGE):
            if not comp.security.backup_enabled:
                items.append(ToilItem(
                    component_id=comp.id,
                    component_name=comp.name,
                    category=ToilCategory.BACKUP_VERIFICATION,
                    description=f"{comp.name} has no automated backups",
                    hours_per_month=_TOIL_ESTIMATES[ToilCategory.BACKUP_VERIFICATION],
                    automation_potential=AutomationPotential.FULLY_AUTOMATABLE,
                    automation_savings_percent=95,
                    priority="high",
                ))

        return items

    def _generate_recommendations(self, items: list[ToilItem]) -> list[str]:
        """Generate automation recommendations."""
        recs: list[str] = []
        seen_cats: set[str] = set()

        for item in items:
            if item.category.value in seen_cats:
                continue
            seen_cats.add(item.category.value)

            if item.automation_potential == AutomationPotential.FULLY_AUTOMATABLE:
                recs.append(
                    f"Automate {item.category.value}: saves ~{item.hours_per_month * item.automation_savings_percent / 100:.0f}hr/month"
                )
            elif item.automation_potential == AutomationPotential.PARTIALLY_AUTOMATABLE:
                recs.append(
                    f"Partially automate {item.category.value}: reduces toil by ~{item.automation_savings_percent:.0f}%"
                )

        return recs[:5]
