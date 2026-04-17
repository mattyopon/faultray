# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Financial Impact Report — translate resilience scores into dollar amounts.

Bridges the gap between technical resilience metrics and business-level
financial exposure.  Takes availability model output (MTBF, MTTR,
availability per component) and produces dollar-denominated risk estimates,
recommended fixes, and ROI projections.

Default cost estimates are intentionally *conservative* (i.e. lower-bound).
Real costs are almost always higher due to reputation damage, customer churn,
and opportunity cost that are difficult to model precisely.

Default cost-per-hour by component type (USD):
    database        $10,000/hr  — data loss risk, transaction integrity
    app_server       $5,000/hr  — primary business logic
    web_server       $5,000/hr  — user-facing traffic
    load_balancer    $8,000/hr  — total traffic disruption when SPOF
    cache            $2,000/hr  — degraded latency, DB overload risk
    queue            $3,000/hr  — async job loss, ordering issues
    storage          $6,000/hr  — data unavailability
    dns             $15,000/hr  — complete unreachability
    external_api     $4,000/hr  — third-party dependency
    ai_agent         $3,000/hr  — AI-powered feature unavailable
    llm_endpoint     $4,000/hr  — LLM provider outage
    tool_service     $2,000/hr  — agent tool unavailable
    agent_orchestrator $5,000/hr — orchestration layer down
    custom           $3,000/hr  — fallback estimate

Default annual fix cost (adding one replica, USD/year):
    database        $24,000/yr  — managed replica instance
    app_server      $12,000/yr  — additional compute node
    web_server      $12,000/yr  — additional web node
    load_balancer    $6,000/yr  — redundant LB instance
    cache            $4,800/yr  — cache replica
    queue            $7,200/yr  — queue mirror/replica
    storage         $18,000/yr  — replicated storage
    dns              $1,200/yr  — redundant DNS provider
    external_api     $6,000/yr  — multi-provider or caching layer
    ai_agent         $9,600/yr  — additional agent instance
    llm_endpoint     $6,000/yr  — multi-provider fallback
    tool_service     $4,800/yr  — additional tool replica
    agent_orchestrator $12,000/yr — orchestrator replica
    custom           $6,000/yr  — fallback estimate
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph
from faultray.simulator.availability_model import (
    FiveLayerResult,
    ThreeLayerResult,
    _DEFAULT_MTBF,
    _DEFAULT_MTTR,
    compute_three_layer_model,
)
from faultray.simulator.engine import SimulationReport

# ---------------------------------------------------------------------------
# Default cost tables (conservative estimates, USD)
# ---------------------------------------------------------------------------

#: Hourly cost of downtime by component type.
DEFAULT_COST_PER_HOUR: dict[str, float] = {
    "database": 10_000.0,
    "app_server": 5_000.0,
    "web_server": 5_000.0,
    "load_balancer": 8_000.0,
    "cache": 2_000.0,
    "queue": 3_000.0,
    "storage": 6_000.0,
    "dns": 15_000.0,
    "external_api": 4_000.0,
    "ai_agent": 3_000.0,
    "llm_endpoint": 4_000.0,
    "tool_service": 2_000.0,
    "agent_orchestrator": 5_000.0,
    "automation": 1_000.0,
    "serverless": 4_000.0,
    "scheduled_job": 2_000.0,
    "custom": 3_000.0,
}

#: Annual cost of adding one replica by component type.
DEFAULT_FIX_COST_PER_YEAR: dict[str, float] = {
    "database": 24_000.0,
    "app_server": 12_000.0,
    "web_server": 12_000.0,
    "load_balancer": 6_000.0,
    "cache": 4_800.0,
    "queue": 7_200.0,
    "storage": 18_000.0,
    "dns": 1_200.0,
    "external_api": 6_000.0,
    "ai_agent": 9_600.0,
    "llm_endpoint": 6_000.0,
    "tool_service": 4_800.0,
    "agent_orchestrator": 12_000.0,
    "automation": 2_400.0,
    "serverless": 9_600.0,
    "scheduled_job": 4_800.0,
    "custom": 6_000.0,
}

#: Hours in a year.
_HOURS_PER_YEAR: float = 8760.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ComponentImpact:
    """Financial impact for a single component."""

    component_id: str
    component_type: str
    availability: float
    annual_downtime_hours: float
    annual_loss: float
    cost_per_hour: float
    risk_description: str


@dataclass
class RecommendedFix:
    """A recommended resilience improvement with ROI projection."""

    component_id: str
    description: str
    annual_cost: float
    annual_savings: float
    roi: float  # savings / cost


@dataclass
class FinancialImpactReport:
    """Complete financial impact report."""

    resilience_score: float
    total_annual_loss: float
    total_downtime_hours: float
    component_impacts: list[ComponentImpact] = field(default_factory=list)
    top_risks: list[ComponentImpact] = field(default_factory=list)
    recommended_fixes: list[RecommendedFix] = field(default_factory=list)
    total_fix_cost: float = 0.0
    total_savings: float = 0.0
    roi: float = 0.0


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def _component_availability(comp_id: str, comp_type: str, replicas: int,
                            layer_details: dict[str, float]) -> float:
    """Return per-component hardware availability from layer2 details.

    Falls back to a simple MTBF/(MTBF+MTTR) estimate when the component
    is not present in the availability model output (e.g. not on the
    critical path).
    """
    if comp_id in layer_details:
        return layer_details[comp_id]

    # Fallback: compute from defaults
    mtbf = _DEFAULT_MTBF.get(comp_type, 2160.0)
    mttr = _DEFAULT_MTTR.get(comp_type, 0.5)
    a_single = mtbf / (mtbf + mttr)
    return 1.0 - (1.0 - a_single) ** max(replicas, 1)


def _risk_description(comp_id: str, comp_type: str, replicas: int,
                      dependents_count: int) -> str:
    """Generate a human-readable risk description."""
    parts: list[str] = []
    if replicas <= 1:
        parts.append("Single point of failure (no replicas)")
    if dependents_count > 0:
        parts.append(f"{dependents_count} dependent component(s)")
    if not parts:
        parts.append("Baseline operational risk")
    return "; ".join(parts)


def calculate_financial_impact(
    graph: InfraGraph,
    simulation_report: SimulationReport | None = None,
    availability_result: ThreeLayerResult | FiveLayerResult | None = None,
    cost_per_hour_override: float | None = None,
) -> FinancialImpactReport:
    """Calculate the financial impact of the current infrastructure topology.

    Parameters
    ----------
    graph:
        Infrastructure graph to analyse.
    simulation_report:
        Optional simulation report (used for resilience score).
    availability_result:
        Pre-computed availability model.  If ``None``, the 3-layer model
        is computed automatically from *graph*.
    cost_per_hour_override:
        When provided, overrides the default per-type cost for **all**
        components.  Per-component YAML ``cost_profile.revenue_per_minute``
        still takes precedence when set.
    """
    if not graph.components:
        return FinancialImpactReport(
            resilience_score=0.0,
            total_annual_loss=0.0,
            total_downtime_hours=0.0,
        )

    # Resilience score
    if simulation_report is not None:
        resilience_score = simulation_report.resilience_score
    else:
        resilience_score = graph.resilience_score()

    # Availability model
    if availability_result is None:
        availability_result = compute_three_layer_model(graph)

    # Layer 2 (hardware) details give per-component availability
    layer2_details = availability_result.layer2_hardware.details

    # Build per-component impacts
    component_impacts: list[ComponentImpact] = []

    for comp in graph.components.values():
        comp_type = comp.type.value

        # Determine cost per hour:
        # 1. Component's own cost_profile.revenue_per_minute (converted to /hr)
        # 2. CLI override
        # 3. Default table
        if comp.cost_profile.revenue_per_minute > 0:
            cph = comp.cost_profile.revenue_per_minute * 60.0
        elif cost_per_hour_override is not None:
            cph = cost_per_hour_override
        else:
            cph = DEFAULT_COST_PER_HOUR.get(comp_type, 3_000.0)

        avail = _component_availability(
            comp.id, comp_type, comp.replicas, layer2_details,
        )

        downtime_hours = (1.0 - avail) * _HOURS_PER_YEAR
        annual_loss = downtime_hours * cph

        dependents = graph.get_dependents(comp.id)
        risk_desc = _risk_description(
            comp.id, comp_type, comp.replicas, len(dependents),
        )

        component_impacts.append(ComponentImpact(
            component_id=comp.id,
            component_type=comp_type,
            availability=avail,
            annual_downtime_hours=round(downtime_hours, 2),
            annual_loss=round(annual_loss, 2),
            cost_per_hour=cph,
            risk_description=risk_desc,
        ))

    # Sort by annual loss descending to find top risks
    component_impacts.sort(key=lambda c: c.annual_loss, reverse=True)
    top_risks = [c for c in component_impacts if c.annual_loss > 0][:10]

    total_annual_loss = sum(c.annual_loss for c in component_impacts)
    total_downtime_hours = sum(c.annual_downtime_hours for c in component_impacts)

    # Recommended fixes: for components with replicas <= 1 and significant loss
    recommended_fixes: list[RecommendedFix] = []
    for impact in component_impacts:
        comp = graph.get_component(impact.component_id)
        if comp is None:
            continue
        if comp.replicas > 1:
            continue
        if impact.annual_loss <= 0:
            continue

        fix_cost = DEFAULT_FIX_COST_PER_YEAR.get(
            impact.component_type, 6_000.0,
        )

        # Estimate savings: adding a replica raises availability dramatically.
        # New availability with 2 replicas: 1 - (1 - A_single)^2
        # The current single-instance availability is already in impact.availability.
        a_single = impact.availability
        a_with_replica = 1.0 - (1.0 - a_single) ** 2
        new_downtime = (1.0 - a_with_replica) * _HOURS_PER_YEAR
        new_loss = new_downtime * impact.cost_per_hour
        savings = impact.annual_loss - new_loss

        if savings <= 0:
            continue

        roi = savings / fix_cost if fix_cost > 0 else 0.0

        recommended_fixes.append(RecommendedFix(
            component_id=impact.component_id,
            description=f"Add replica for {impact.component_id} ({impact.component_type})",
            annual_cost=round(fix_cost, 2),
            annual_savings=round(savings, 2),
            roi=round(roi, 1),
        ))

    # Sort fixes by ROI descending
    recommended_fixes.sort(key=lambda f: f.roi, reverse=True)

    total_fix_cost = sum(f.annual_cost for f in recommended_fixes)
    total_savings = sum(f.annual_savings for f in recommended_fixes)
    overall_roi = total_savings / total_fix_cost if total_fix_cost > 0 else 0.0

    return FinancialImpactReport(
        resilience_score=round(resilience_score, 1),
        total_annual_loss=round(total_annual_loss, 2),
        total_downtime_hours=round(total_downtime_hours, 2),
        component_impacts=component_impacts,
        top_risks=top_risks,
        recommended_fixes=recommended_fixes,
        total_fix_cost=round(total_fix_cost, 2),
        total_savings=round(total_savings, 2),
        roi=round(overall_roi, 1),
    )
