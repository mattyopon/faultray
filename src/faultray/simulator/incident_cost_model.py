# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Incident Cost Modeling Engine.

Calculates the total business cost of incidents including direct, indirect,
and opportunity costs.  Provides ROI analysis, scenario comparison,
error-budget valuation, annual projections, executive reporting, and
cascading-cost modelling.

All calculations are **stateless** and rely only on the Python standard
library plus the existing ``faultray`` model layer and Pydantic v2.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CostCategory(str, Enum):
    """Categories of incident cost."""

    DIRECT_REVENUE_LOSS = "direct_revenue_loss"
    SLA_CREDITS = "sla_credits"
    ENGINEERING_TIME = "engineering_time"
    CUSTOMER_CHURN = "customer_churn"
    BRAND_DAMAGE = "brand_damage"
    REGULATORY_FINE = "regulatory_fine"
    DATA_RECOVERY = "data_recovery"
    COMMUNICATION = "communication"
    LEGAL = "legal"
    OPPORTUNITY_COST = "opportunity_cost"


class IncidentSeverity(str, Enum):
    """Incident severity levels (SEV1 = most severe)."""

    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"
    SEV5 = "sev5"


# ---------------------------------------------------------------------------
# Severity multipliers / constants
# ---------------------------------------------------------------------------

_SEVERITY_MULTIPLIER: dict[IncidentSeverity, float] = {
    IncidentSeverity.SEV1: 5.0,
    IncidentSeverity.SEV2: 3.0,
    IncidentSeverity.SEV3: 1.5,
    IncidentSeverity.SEV4: 1.0,
    IncidentSeverity.SEV5: 0.5,
}

_SEVERITY_ENGINEER_COUNT: dict[IncidentSeverity, int] = {
    IncidentSeverity.SEV1: 10,
    IncidentSeverity.SEV2: 5,
    IncidentSeverity.SEV3: 3,
    IncidentSeverity.SEV4: 2,
    IncidentSeverity.SEV5: 1,
}

_BASE_REVENUE_PER_MINUTE = 100.0
_BASE_ENGINEER_HOURLY = 150.0
_BASE_CUSTOMER_LTV = 5_000.0
_BASE_CHURN_RATE_PER_HOUR = 0.001
_BASE_SLA_CREDIT_PCT = 10.0
_BASE_COMMUNICATION_COST_PER_MIN = 10.0
_BASE_LEGAL_HOURLY = 500.0
_BASE_BRAND_DAMAGE_PER_USER = 0.50
_BASE_DATA_RECOVERY_PER_COMPONENT = 25_000.0
_BASE_REGULATORY_FINE = 50_000.0
_BASE_OPPORTUNITY_PER_MIN = 50.0


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class IncidentProfile(BaseModel):
    """Describes a specific incident scenario for cost calculation."""

    severity: IncidentSeverity
    duration_minutes: float
    affected_users: int
    affected_components: list[str] = Field(default_factory=list)
    data_loss: bool = False
    public_facing: bool = False
    sla_breach: bool = False
    regulatory_impact: bool = False


class CostBreakdown(BaseModel):
    """A single line item in the cost report."""

    category: CostCategory
    amount: float
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    calculation_basis: str = ""
    is_recurring: bool = False


class IncidentCostReport(BaseModel):
    """Full cost analysis for one incident."""

    total_cost: float
    breakdown: list[CostBreakdown] = Field(default_factory=list)
    cost_per_minute: float = 0.0
    cost_per_user: float = 0.0
    annualized_risk: float = 0.0
    roi_of_prevention: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class ROIAnalysis(BaseModel):
    """ROI analysis for prevention investment."""

    investment: float
    expected_annual_loss_without: float
    expected_annual_loss_with: float
    annual_savings: float
    roi_percent: float
    payback_months: float
    recommendation: str = ""


class ScenarioComparison(BaseModel):
    """Side-by-side comparison of multiple incident scenarios."""

    scenarios: list[IncidentCostReport] = Field(default_factory=list)
    worst_case_cost: float = 0.0
    best_case_cost: float = 0.0
    average_cost: float = 0.0
    cost_variance: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class ErrorBudgetValue(BaseModel):
    """Monetary value of the error budget."""

    slo_target: float
    error_budget_percent: float
    error_budget_minutes_per_month: float
    cost_per_budget_minute: float
    total_budget_value: float
    remaining_budget_minutes: float = 0.0
    remaining_budget_value: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class AnnualProjection(BaseModel):
    """Annual cost projection based on historical data."""

    projected_incidents: int
    projected_annual_cost: float
    cost_by_severity: dict[str, float] = Field(default_factory=dict)
    cost_trend: str = ""  # increasing / decreasing / stable
    confidence_interval_low: float = 0.0
    confidence_interval_high: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class ExecutiveIncidentReport(BaseModel):
    """High-level executive summary of incident cost analysis."""

    incident_summary: str = ""
    total_cost: float = 0.0
    cost_breakdown_summary: dict[str, float] = Field(default_factory=dict)
    business_impact: str = ""
    risk_rating: str = ""
    top_recommendations: list[str] = Field(default_factory=list)
    prevention_investment: float = 0.0
    expected_roi: float = 0.0


class CascadingCostResult(BaseModel):
    """Cost modelling of cascading failures."""

    initial_component: str = ""
    total_cost: float = 0.0
    affected_components: list[str] = Field(default_factory=list)
    per_component_cost: dict[str, float] = Field(default_factory=dict)
    cascade_depth: int = 0
    duration_minutes: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class IncidentCostEngine:
    """Stateless engine for incident cost modelling.

    All public methods accept an ``InfraGraph`` and scenario descriptors and
    return Pydantic model instances.
    """

    # -- helpers (internal) -------------------------------------------------

    @staticmethod
    def _severity_mult(severity: IncidentSeverity) -> float:
        return _SEVERITY_MULTIPLIER.get(severity, 1.0)

    @staticmethod
    def _engineer_count(severity: IncidentSeverity) -> int:
        return _SEVERITY_ENGINEER_COUNT.get(severity, 2)

    @staticmethod
    def _component_revenue(graph: InfraGraph, comp_id: str) -> float:
        comp = graph.get_component(comp_id)
        if comp is None:
            return _BASE_REVENUE_PER_MINUTE
        return comp.cost_profile.revenue_per_minute or _BASE_REVENUE_PER_MINUTE

    @staticmethod
    def _avg_mtbf_hours(graph: InfraGraph) -> float:
        vals = [
            c.operational_profile.mtbf_hours
            for c in graph.components.values()
            if c.operational_profile.mtbf_hours > 0
        ]
        if not vals:
            return 720.0  # default 30 days
        return sum(vals) / len(vals)

    # -- cost line-item calculators -----------------------------------------

    def _calc_revenue_loss(
        self,
        graph: InfraGraph,
        profile: IncidentProfile,
    ) -> CostBreakdown:
        total_rev = sum(
            self._component_revenue(graph, cid) for cid in profile.affected_components
        ) if profile.affected_components else _BASE_REVENUE_PER_MINUTE
        amount = total_rev * profile.duration_minutes * self._severity_mult(profile.severity)
        return CostBreakdown(
            category=CostCategory.DIRECT_REVENUE_LOSS,
            amount=round(amount, 2),
            confidence=0.9,
            calculation_basis=(
                f"revenue/min({total_rev:.0f}) x duration({profile.duration_minutes:.0f}) "
                f"x severity_mult({self._severity_mult(profile.severity)})"
            ),
            is_recurring=False,
        )

    def _calc_sla_credits(
        self,
        graph: InfraGraph,
        profile: IncidentProfile,
    ) -> CostBreakdown:
        if not profile.sla_breach:
            return CostBreakdown(
                category=CostCategory.SLA_CREDITS,
                amount=0.0,
                confidence=1.0,
                calculation_basis="No SLA breach",
            )
        total_rev = sum(
            self._component_revenue(graph, cid) for cid in profile.affected_components
        ) if profile.affected_components else _BASE_REVENUE_PER_MINUTE
        monthly_value = total_rev * 60 * 24 * 30
        amount = monthly_value * (_BASE_SLA_CREDIT_PCT / 100) * self._severity_mult(profile.severity)
        return CostBreakdown(
            category=CostCategory.SLA_CREDITS,
            amount=round(amount, 2),
            confidence=0.85,
            calculation_basis=(
                f"monthly_value({monthly_value:.0f}) x sla_pct({_BASE_SLA_CREDIT_PCT}%) "
                f"x severity_mult({self._severity_mult(profile.severity)})"
            ),
        )

    def _calc_engineering_time(
        self,
        profile: IncidentProfile,
    ) -> CostBreakdown:
        eng_count = self._engineer_count(profile.severity)
        hours = profile.duration_minutes / 60 * 1.5  # 1.5x for diagnostics
        amount = _BASE_ENGINEER_HOURLY * hours * eng_count
        return CostBreakdown(
            category=CostCategory.ENGINEERING_TIME,
            amount=round(amount, 2),
            confidence=0.9,
            calculation_basis=(
                f"${_BASE_ENGINEER_HOURLY}/hr x {hours:.1f}hr x {eng_count} engineers"
            ),
        )

    def _calc_customer_churn(
        self,
        profile: IncidentProfile,
    ) -> CostBreakdown:
        churn_hours = profile.duration_minutes / 60
        churned = profile.affected_users * _BASE_CHURN_RATE_PER_HOUR * churn_hours
        mult = self._severity_mult(profile.severity)
        amount = churned * _BASE_CUSTOMER_LTV * mult
        return CostBreakdown(
            category=CostCategory.CUSTOMER_CHURN,
            amount=round(amount, 2),
            confidence=0.6,
            calculation_basis=(
                f"users({profile.affected_users}) x churn_rate({_BASE_CHURN_RATE_PER_HOUR}/hr) "
                f"x hours({churn_hours:.1f}) x ltv(${_BASE_CUSTOMER_LTV}) x sev_mult({mult})"
            ),
            is_recurring=True,
        )

    def _calc_brand_damage(
        self,
        profile: IncidentProfile,
    ) -> CostBreakdown:
        if not profile.public_facing:
            return CostBreakdown(
                category=CostCategory.BRAND_DAMAGE,
                amount=0.0,
                confidence=1.0,
                calculation_basis="Not public-facing",
            )
        mult = self._severity_mult(profile.severity)
        amount = profile.affected_users * _BASE_BRAND_DAMAGE_PER_USER * mult
        return CostBreakdown(
            category=CostCategory.BRAND_DAMAGE,
            amount=round(amount, 2),
            confidence=0.4,
            calculation_basis=(
                f"users({profile.affected_users}) x ${_BASE_BRAND_DAMAGE_PER_USER}/user "
                f"x sev_mult({mult})"
            ),
            is_recurring=True,
        )

    def _calc_regulatory_fine(
        self,
        profile: IncidentProfile,
    ) -> CostBreakdown:
        if not profile.regulatory_impact:
            return CostBreakdown(
                category=CostCategory.REGULATORY_FINE,
                amount=0.0,
                confidence=1.0,
                calculation_basis="No regulatory impact",
            )
        mult = self._severity_mult(profile.severity)
        amount = _BASE_REGULATORY_FINE * mult
        return CostBreakdown(
            category=CostCategory.REGULATORY_FINE,
            amount=round(amount, 2),
            confidence=0.5,
            calculation_basis=f"base_fine(${_BASE_REGULATORY_FINE}) x sev_mult({mult})",
        )

    def _calc_data_recovery(
        self,
        profile: IncidentProfile,
    ) -> CostBreakdown:
        if not profile.data_loss:
            return CostBreakdown(
                category=CostCategory.DATA_RECOVERY,
                amount=0.0,
                confidence=1.0,
                calculation_basis="No data loss",
            )
        n = max(len(profile.affected_components), 1)
        amount = _BASE_DATA_RECOVERY_PER_COMPONENT * n * self._severity_mult(profile.severity)
        return CostBreakdown(
            category=CostCategory.DATA_RECOVERY,
            amount=round(amount, 2),
            confidence=0.7,
            calculation_basis=(
                f"${_BASE_DATA_RECOVERY_PER_COMPONENT}/comp x {n} components "
                f"x sev_mult({self._severity_mult(profile.severity)})"
            ),
        )

    def _calc_communication(
        self,
        profile: IncidentProfile,
    ) -> CostBreakdown:
        mult = self._severity_mult(profile.severity)
        amount = _BASE_COMMUNICATION_COST_PER_MIN * profile.duration_minutes * mult
        return CostBreakdown(
            category=CostCategory.COMMUNICATION,
            amount=round(amount, 2),
            confidence=0.8,
            calculation_basis=(
                f"${_BASE_COMMUNICATION_COST_PER_MIN}/min x {profile.duration_minutes:.0f}min "
                f"x sev_mult({mult})"
            ),
        )

    def _calc_legal(
        self,
        profile: IncidentProfile,
    ) -> CostBreakdown:
        if not (profile.regulatory_impact or profile.data_loss):
            return CostBreakdown(
                category=CostCategory.LEGAL,
                amount=0.0,
                confidence=1.0,
                calculation_basis="No legal exposure",
            )
        hours = max(profile.duration_minutes / 60, 1.0) * self._severity_mult(profile.severity)
        amount = _BASE_LEGAL_HOURLY * hours
        return CostBreakdown(
            category=CostCategory.LEGAL,
            amount=round(amount, 2),
            confidence=0.5,
            calculation_basis=f"${_BASE_LEGAL_HOURLY}/hr x {hours:.1f}hr",
        )

    def _calc_opportunity_cost(
        self,
        profile: IncidentProfile,
    ) -> CostBreakdown:
        mult = self._severity_mult(profile.severity)
        amount = _BASE_OPPORTUNITY_PER_MIN * profile.duration_minutes * mult
        return CostBreakdown(
            category=CostCategory.OPPORTUNITY_COST,
            amount=round(amount, 2),
            confidence=0.5,
            calculation_basis=(
                f"${_BASE_OPPORTUNITY_PER_MIN}/min x {profile.duration_minutes:.0f}min "
                f"x sev_mult({mult})"
            ),
        )

    # -- recommendations ----------------------------------------------------

    @staticmethod
    def _build_recommendations(
        graph: InfraGraph,
        profile: IncidentProfile,
        total_cost: float,
    ) -> list[str]:
        recs: list[str] = []
        if total_cost > 500_000:
            recs.append(
                "CRITICAL: Incident cost exceeds $500K. "
                "Implement comprehensive redundancy and automated failover immediately."
            )
        elif total_cost > 100_000:
            recs.append(
                "HIGH: Incident cost exceeds $100K. "
                "Review resilience posture and prioritize prevention investment."
            )

        if profile.data_loss:
            recs.append(
                "Enable automated backups and point-in-time recovery for all data stores."
            )

        if profile.sla_breach:
            recs.append(
                "Review SLA commitments and implement proactive monitoring with "
                "burn-rate alerts to prevent future breaches."
            )

        if profile.regulatory_impact:
            recs.append(
                "Engage compliance team to review regulatory exposure and "
                "strengthen data-protection controls."
            )

        if profile.public_facing and profile.affected_users > 10_000:
            recs.append(
                "Prepare a customer-communication plan and consider proactive "
                "status-page updates during incidents."
            )

        # SPOF detection
        for cid in profile.affected_components:
            comp = graph.get_component(cid)
            if comp is not None and comp.replicas <= 1 and not comp.failover.enabled:
                recs.append(
                    f"Component '{cid}' is a single point of failure. "
                    f"Add replicas or enable failover."
                )

        return recs

    # -- public API ---------------------------------------------------------

    def calculate_incident_cost(
        self,
        graph: InfraGraph,
        profile: IncidentProfile,
    ) -> IncidentCostReport:
        """Calculate the total business cost of an incident."""
        items = [
            self._calc_revenue_loss(graph, profile),
            self._calc_sla_credits(graph, profile),
            self._calc_engineering_time(profile),
            self._calc_customer_churn(profile),
            self._calc_brand_damage(profile),
            self._calc_regulatory_fine(profile),
            self._calc_data_recovery(profile),
            self._calc_communication(profile),
            self._calc_legal(profile),
            self._calc_opportunity_cost(profile),
        ]
        total = sum(item.amount for item in items)
        cost_per_min = total / max(profile.duration_minutes, 1.0)
        cost_per_user = total / max(profile.affected_users, 1)
        mtbf = self._avg_mtbf_hours(graph)
        incidents_per_year = 8760 / mtbf  # 8760 hours in a year
        annualized = total * incidents_per_year
        prevention_cost = total * 0.2  # assume 20% of incident cost
        roi = ((annualized - prevention_cost) / max(prevention_cost, 1.0)) * 100

        recs = self._build_recommendations(graph, profile, total)

        return IncidentCostReport(
            total_cost=round(total, 2),
            breakdown=items,
            cost_per_minute=round(cost_per_min, 2),
            cost_per_user=round(cost_per_user, 2),
            annualized_risk=round(annualized, 2),
            roi_of_prevention=round(roi, 2),
            recommendations=recs,
        )

    def estimate_prevention_roi(
        self,
        graph: InfraGraph,
        profiles: list[IncidentProfile],
        investment: float,
    ) -> ROIAnalysis:
        """Estimate ROI of a prevention investment across multiple scenarios."""
        total_loss = 0.0
        for p in profiles:
            report = self.calculate_incident_cost(graph, p)
            total_loss += report.annualized_risk

        # Prevention is assumed to reduce incidents by 70%
        reduction_factor = 0.70
        loss_with = total_loss * (1 - reduction_factor)
        savings = total_loss - loss_with - investment
        roi_pct = (savings / max(investment, 1.0)) * 100
        monthly_savings = (total_loss * reduction_factor) / 12
        payback = investment / max(monthly_savings, 1.0)

        if roi_pct > 200:
            rec = "Strongly recommended: Investment delivers exceptional ROI."
        elif roi_pct > 50:
            rec = "Recommended: Investment delivers solid positive ROI."
        elif roi_pct > 0:
            rec = "Marginal: Investment is positive but returns are modest."
        else:
            rec = "Not recommended: Investment does not recoup costs within the analysis period."

        return ROIAnalysis(
            investment=round(investment, 2),
            expected_annual_loss_without=round(total_loss, 2),
            expected_annual_loss_with=round(loss_with, 2),
            annual_savings=round(savings, 2),
            roi_percent=round(roi_pct, 2),
            payback_months=round(payback, 2),
            recommendation=rec,
        )

    def compare_scenarios(
        self,
        graph: InfraGraph,
        profiles: list[IncidentProfile],
    ) -> ScenarioComparison:
        """Compare costs across multiple incident scenarios."""
        if not profiles:
            return ScenarioComparison()

        reports: list[IncidentCostReport] = []
        for p in profiles:
            reports.append(self.calculate_incident_cost(graph, p))

        costs = [r.total_cost for r in reports]
        worst = max(costs)
        best = min(costs)
        avg = sum(costs) / len(costs)
        variance = sum((c - avg) ** 2 for c in costs) / len(costs)

        recs: list[str] = []
        if worst > 2 * avg:
            recs.append(
                "Worst-case scenario is more than 2x the average. "
                "Focus mitigation on the highest-cost scenario."
            )
        if best < avg * 0.1:
            recs.append(
                "Best-case cost is very low. "
                "Consider focusing resources on preventing more expensive scenarios."
            )
        if len(costs) > 1 and variance > avg ** 2:
            recs.append(
                "High cost variance across scenarios. "
                "Standardize incident response to reduce variability."
            )

        return ScenarioComparison(
            scenarios=reports,
            worst_case_cost=round(worst, 2),
            best_case_cost=round(best, 2),
            average_cost=round(avg, 2),
            cost_variance=round(variance, 2),
            recommendations=recs,
        )

    def calculate_error_budget_value(
        self,
        graph: InfraGraph,
        slo_target: float,
    ) -> ErrorBudgetValue:
        """Calculate the monetary value of the error budget.

        ``slo_target`` is expressed as a percentage, e.g. 99.9.
        """
        error_budget_pct = 100.0 - slo_target
        minutes_per_month = 30 * 24 * 60  # 43 200
        budget_minutes = minutes_per_month * (error_budget_pct / 100)

        # Estimate cost per minute from a representative profile
        total_rev = sum(
            (c.cost_profile.revenue_per_minute or _BASE_REVENUE_PER_MINUTE)
            for c in graph.components.values()
        ) if graph.components else _BASE_REVENUE_PER_MINUTE
        cost_per_min = total_rev

        total_value = cost_per_min * budget_minutes

        recs: list[str] = []
        if slo_target >= 99.99:
            recs.append(
                "Four-nines SLO leaves a very tight error budget. "
                "Invest heavily in automated recovery."
            )
        elif slo_target >= 99.9:
            recs.append(
                "Three-nines SLO is standard. "
                "Balance feature velocity with reliability work."
            )
        else:
            recs.append(
                "SLO below 99.9% provides generous error budget. "
                "Consider tightening SLO as reliability matures."
            )

        return ErrorBudgetValue(
            slo_target=slo_target,
            error_budget_percent=round(error_budget_pct, 4),
            error_budget_minutes_per_month=round(budget_minutes, 2),
            cost_per_budget_minute=round(cost_per_min, 2),
            total_budget_value=round(total_value, 2),
            remaining_budget_minutes=round(budget_minutes, 2),
            remaining_budget_value=round(total_value, 2),
            recommendations=recs,
        )

    def project_annual_incident_cost(
        self,
        graph: InfraGraph,
        historical_incidents: list[IncidentProfile],
    ) -> AnnualProjection:
        """Project annual incident cost from historical data."""
        if not historical_incidents:
            return AnnualProjection(
                projected_incidents=0,
                projected_annual_cost=0.0,
                recommendations=["No historical data available for projection."],
            )

        n = len(historical_incidents)
        # Assume the list represents a sample period; scale to 12 months
        # For simplicity, assume the list represents 1 month of data
        annual_factor = 12

        total_cost = 0.0
        by_sev: dict[str, float] = {}
        for p in historical_incidents:
            report = self.calculate_incident_cost(graph, p)
            total_cost += report.total_cost
            sev_key = p.severity.value
            by_sev[sev_key] = by_sev.get(sev_key, 0.0) + report.total_cost

        projected_cost = total_cost * annual_factor
        projected_count = n * annual_factor

        # Scale severity breakdown
        for k in by_sev:
            by_sev[k] = round(by_sev[k] * annual_factor, 2)

        # Confidence interval (simple +/-30%)
        low = projected_cost * 0.7
        high = projected_cost * 1.3

        # Trend heuristic: look at severity distribution
        sev1_frac = by_sev.get("sev1", 0.0) / max(projected_cost, 1.0)
        if sev1_frac > 0.5:
            trend = "increasing"
        elif sev1_frac < 0.1:
            trend = "decreasing"
        else:
            trend = "stable"

        recs: list[str] = []
        if projected_cost > 1_000_000:
            recs.append(
                "Projected annual cost exceeds $1M. "
                "Consider a dedicated reliability engineering programme."
            )
        if projected_count > 50:
            recs.append(
                "Projected incident count is high. "
                "Invest in proactive monitoring and chaos engineering."
            )
        if trend == "increasing":
            recs.append(
                "Severity trend is increasing. "
                "Prioritize incident prevention over response improvement."
            )

        return AnnualProjection(
            projected_incidents=projected_count,
            projected_annual_cost=round(projected_cost, 2),
            cost_by_severity=by_sev,
            cost_trend=trend,
            confidence_interval_low=round(low, 2),
            confidence_interval_high=round(high, 2),
            recommendations=recs,
        )

    def generate_executive_report(
        self,
        graph: InfraGraph,
        profile: IncidentProfile,
    ) -> ExecutiveIncidentReport:
        """Generate a high-level executive summary for an incident."""
        report = self.calculate_incident_cost(graph, profile)

        summary_parts: list[str] = [
            f"A {profile.severity.value.upper()} incident lasted {profile.duration_minutes:.0f} minutes",
            f"affecting {profile.affected_users:,} users",
        ]
        if profile.affected_components:
            summary_parts.append(
                f"across {len(profile.affected_components)} components"
            )
        summary = ", ".join(summary_parts) + "."

        breakdown_dict: dict[str, float] = {}
        for item in report.breakdown:
            if item.amount > 0:
                breakdown_dict[item.category.value] = item.amount

        # Risk rating
        if report.total_cost > 500_000:
            risk = "CRITICAL"
        elif report.total_cost > 100_000:
            risk = "HIGH"
        elif report.total_cost > 10_000:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        impact_parts: list[str] = []
        if profile.data_loss:
            impact_parts.append("Data loss occurred")
        if profile.sla_breach:
            impact_parts.append("SLA was breached")
        if profile.regulatory_impact:
            impact_parts.append("Regulatory exposure identified")
        if profile.public_facing:
            impact_parts.append("Incident was customer-visible")
        business_impact = ". ".join(impact_parts) + "." if impact_parts else "No major business impact flags."

        prevention = report.total_cost * 0.2
        expected_roi = report.roi_of_prevention

        return ExecutiveIncidentReport(
            incident_summary=summary,
            total_cost=report.total_cost,
            cost_breakdown_summary=breakdown_dict,
            business_impact=business_impact,
            risk_rating=risk,
            top_recommendations=report.recommendations[:5],
            prevention_investment=round(prevention, 2),
            expected_roi=round(expected_roi, 2),
        )

    def calculate_cascading_cost(
        self,
        graph: InfraGraph,
        initial_component: str,
        duration: float,
    ) -> CascadingCostResult:
        """Calculate cost of cascading failures from an initial component."""
        comp = graph.get_component(initial_component)
        if comp is None:
            return CascadingCostResult(
                initial_component=initial_component,
                recommendations=[f"Component '{initial_component}' not found in graph."],
            )

        affected_ids = graph.get_all_affected(initial_component)
        all_ids = [initial_component] + sorted(affected_ids)
        per_comp: dict[str, float] = {}
        total = 0.0

        for depth, cid in enumerate(all_ids):
            c = graph.get_component(cid)
            if c is None:
                continue
            rev = c.cost_profile.revenue_per_minute or _BASE_REVENUE_PER_MINUTE
            # Cascading cost increases with depth (delay in detection)
            depth_mult = 1.0 + depth * 0.2
            cost = rev * duration * depth_mult
            per_comp[cid] = round(cost, 2)
            total += cost

        # Cascade depth = length of longest path from initial component
        paths = graph.get_cascade_path(initial_component)
        cascade_depth = max((len(p) for p in paths), default=1) if paths else 1

        recs: list[str] = []
        if len(all_ids) > 3:
            recs.append(
                "Cascading failure affects many components. "
                "Add circuit breakers to limit blast radius."
            )
        if cascade_depth > 3:
            recs.append(
                "Deep cascade chain detected. "
                "Reduce dependency depth or add isolation boundaries."
            )
        if comp.replicas <= 1:
            recs.append(
                f"Initial component '{initial_component}' has no replicas. "
                f"Add redundancy to prevent cascade trigger."
            )

        return CascadingCostResult(
            initial_component=initial_component,
            total_cost=round(total, 2),
            affected_components=list(affected_ids),
            per_component_cost=per_comp,
            cascade_depth=cascade_depth,
            duration_minutes=duration,
            recommendations=recs,
        )
