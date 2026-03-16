"""Executive-Level Resilience Dashboard.

Generates executive-level resilience dashboards with business-oriented metrics,
translating technical resilience data into business impact scores, financial
risk exposure, compliance status, and trend analysis.  Designed for C-level
reporting (board decks, investor briefs, quarterly summaries).

All data models use Pydantic v2 BaseModel.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HOURS_PER_YEAR = 8760.0
_HOURS_PER_MONTH = 730.0
_DEFAULT_REVENUE_PER_HOUR = 10_000.0
_DEFAULT_PERIOD_DAYS = 30
_COMPLIANCE_FRAMEWORKS_DEFAULT = ["SOC2", "ISO27001", "PCI_DSS", "HIPAA", "NIST_CSF"]
_INCIDENT_PERIOD_BUCKET_DAYS = 7

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DashboardSection(str, Enum):
    """Sections available in an executive dashboard."""

    RESILIENCE_SCORE = "resilience_score"
    FINANCIAL_EXPOSURE = "financial_exposure"
    COMPLIANCE_STATUS = "compliance_status"
    INCIDENT_TRENDS = "incident_trends"
    RISK_HEATMAP = "risk_heatmap"
    CAPACITY_FORECAST = "capacity_forecast"
    SLA_PERFORMANCE = "sla_performance"
    TEAM_READINESS = "team_readiness"


class RiskTrend(str, Enum):
    """Directional trend indicator for risk metrics."""

    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    CRITICAL_DECLINE = "critical_decline"


class ExecutiveRating(str, Enum):
    """Qualitative rating for executive-level reporting."""

    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    NEEDS_ATTENTION = "needs_attention"
    CRITICAL = "critical"


class ReportFormat(str, Enum):
    """Format presets controlling the level of detail included."""

    SUMMARY = "summary"
    DETAILED = "detailed"
    BOARD_READY = "board_ready"
    INVESTOR_BRIEF = "investor_brief"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class ResilienceScorecard(BaseModel):
    """Overall resilience scorecard with per-category breakdown."""

    overall_score: float = 0.0
    category_scores: dict[str, float] = Field(default_factory=dict)
    trend: RiskTrend = RiskTrend.STABLE
    rating: ExecutiveRating = ExecutiveRating.ACCEPTABLE
    period_start: str = ""
    period_end: str = ""


class FinancialExposure(BaseModel):
    """Financial risk exposure estimates."""

    estimated_annual_loss_usd: float = 0.0
    worst_case_loss_usd: float = 0.0
    insurance_coverage_gap_usd: float = 0.0
    risk_reduction_roi: float = 0.0


class ComplianceSnapshot(BaseModel):
    """Point-in-time compliance status across frameworks."""

    frameworks_assessed: int = 0
    compliant_count: int = 0
    non_compliant_count: int = 0
    compliance_percentage: float = 0.0
    critical_gaps: list[str] = Field(default_factory=list)


class IncidentTrendData(BaseModel):
    """Incident metrics for a single reporting period."""

    period: str = ""
    total_incidents: int = 0
    mttr_hours: float = 0.0
    mttd_hours: float = 0.0
    p1_count: int = 0
    trend: RiskTrend = RiskTrend.STABLE


class RiskHeatmapCell(BaseModel):
    """A single cell in a likelihood x impact risk matrix."""

    category: str = ""
    likelihood: float = 0.0
    impact: float = 0.0
    risk_level: float = 0.0
    mitigation_status: str = "open"


class CapacityForecast(BaseModel):
    """Capacity runway forecast for a single service."""

    service_id: str = ""
    current_utilization: float = 0.0
    peak_utilization: float = 0.0
    months_to_capacity: float = 0.0
    scale_recommendation: str = ""


class ExecutiveDashboard(BaseModel):
    """Complete executive dashboard payload."""

    generated_at: str = ""
    report_format: ReportFormat = ReportFormat.BOARD_READY
    scorecard: ResilienceScorecard = Field(default_factory=ResilienceScorecard)
    financial_exposure: FinancialExposure = Field(default_factory=FinancialExposure)
    compliance: ComplianceSnapshot = Field(default_factory=ComplianceSnapshot)
    incident_trends: list[IncidentTrendData] = Field(default_factory=list)
    risk_heatmap: list[RiskHeatmapCell] = Field(default_factory=list)
    capacity_forecasts: list[CapacityForecast] = Field(default_factory=list)
    key_recommendations: list[str] = Field(default_factory=list)
    executive_summary: str = ""


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _rating_from_score(score: float) -> ExecutiveRating:
    """Map a 0-100 score to an :class:`ExecutiveRating`."""
    if score >= 90:
        return ExecutiveRating.EXCELLENT
    if score >= 75:
        return ExecutiveRating.GOOD
    if score >= 60:
        return ExecutiveRating.ACCEPTABLE
    if score >= 40:
        return ExecutiveRating.NEEDS_ATTENTION
    return ExecutiveRating.CRITICAL


def _trend_from_scores(current: float, previous: float) -> RiskTrend:
    """Derive a :class:`RiskTrend` from two successive scores."""
    delta = current - previous
    if delta > 5:
        return RiskTrend.IMPROVING
    if delta > -2:
        return RiskTrend.STABLE
    if delta > -10:
        return RiskTrend.DEGRADING
    return RiskTrend.CRITICAL_DECLINE


def _count_spofs(graph: InfraGraph) -> int:
    """Count single-points-of-failure."""
    count = 0
    for comp in graph.components.values():
        if comp.replicas <= 1 and not comp.failover.enabled:
            dependents = graph.get_dependents(comp.id)
            if dependents:
                count += 1
    return count


def _redundancy_score(graph: InfraGraph) -> float:
    """Score 0-100 based on proportion of components with redundancy."""
    if not graph.components:
        return 0.0
    redundant = sum(
        1
        for c in graph.components.values()
        if c.replicas >= 2 or c.failover.enabled
    )
    return (redundant / len(graph.components)) * 100.0


def _dependency_diversity_score(graph: InfraGraph) -> float:
    """Score 0-100 reflecting diversity (fewer deep chains = higher)."""
    paths = graph.get_critical_paths()
    if not paths:
        return 100.0
    max_depth = len(paths[0])
    if max_depth <= 2:
        return 100.0
    if max_depth >= 10:
        return 10.0
    return max(10.0, 100.0 - (max_depth - 2) * 11.25)


def _health_mix_score(graph: InfraGraph) -> float:
    """Score 0-100 based on proportion of healthy components."""
    if not graph.components:
        return 0.0
    healthy = sum(
        1
        for c in graph.components.values()
        if c.health == HealthStatus.HEALTHY
    )
    return (healthy / len(graph.components)) * 100.0


def _component_utilization(comp: Component) -> float:
    """Return utilization for a component (0-100)."""
    return comp.utilization()


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ExecutiveDashboardEngine:
    """Stateless engine that produces executive-level dashboards.

    All computation derives from the supplied :class:`InfraGraph` and optional
    incident data.  No mutable state is held between calls.
    """

    # -- public API ---------------------------------------------------------

    def generate_dashboard(
        self,
        graph: InfraGraph,
        report_format: ReportFormat = ReportFormat.BOARD_READY,
        incidents: list[dict[str, Any]] | None = None,
        period_days: int = _DEFAULT_PERIOD_DAYS,
    ) -> ExecutiveDashboard:
        """Generate a complete executive dashboard.

        Parameters
        ----------
        graph:
            The infrastructure graph to analyse.
        report_format:
            Level of detail (SUMMARY omits heatmap & capacity; BOARD_READY
            includes everything).
        incidents:
            Optional list of incident dicts with keys ``timestamp`` (ISO str),
            ``severity`` (``"P1"``-``"P4"``), ``ttd_hours``, ``ttr_hours``.
        period_days:
            Reporting window in days.
        """
        if incidents is None:
            incidents = []

        scorecard = self.compute_resilience_scorecard(graph)
        financial = self.estimate_financial_exposure(graph)
        compliance = self.assess_compliance_status(graph)
        inc_trends = self.analyze_incident_trends(incidents, period_days)

        # Sections controlled by report_format
        heatmap: list[RiskHeatmapCell] = []
        capacity: list[CapacityForecast] = []

        if report_format in (
            ReportFormat.BOARD_READY,
            ReportFormat.DETAILED,
        ):
            heatmap = self.build_risk_heatmap(graph)
            capacity = self.forecast_capacity(graph)

        if report_format == ReportFormat.DETAILED:
            heatmap = self.build_risk_heatmap(graph)
            capacity = self.forecast_capacity(graph)

        recommendations = self._build_recommendations(graph, scorecard)

        dashboard = ExecutiveDashboard(
            generated_at=datetime.now(timezone.utc).isoformat(),
            report_format=report_format,
            scorecard=scorecard,
            financial_exposure=financial,
            compliance=compliance,
            incident_trends=inc_trends,
            risk_heatmap=heatmap,
            capacity_forecasts=capacity,
            key_recommendations=recommendations,
            executive_summary="",
        )

        dashboard.executive_summary = self.generate_executive_summary(dashboard)
        return dashboard

    def compute_resilience_scorecard(
        self,
        graph: InfraGraph,
    ) -> ResilienceScorecard:
        """Compute a resilience scorecard with category breakdown.

        Categories:
        - redundancy: proportion of components with replicas or failover.
        - dependency_diversity: inverse of max dependency depth.
        - health_mix: proportion of healthy components.
        """
        redundancy = _redundancy_score(graph)
        diversity = _dependency_diversity_score(graph)
        health = _health_mix_score(graph)

        category_scores = {
            "redundancy": round(redundancy, 1),
            "dependency_diversity": round(diversity, 1),
            "health_mix": round(health, 1),
        }

        # Weighted average (redundancy most important)
        overall = (redundancy * 0.4 + diversity * 0.3 + health * 0.3)
        overall = max(0.0, min(100.0, overall))

        rating = _rating_from_score(overall)

        now = datetime.now(timezone.utc)
        period_end = now.isoformat()
        period_start = (now - timedelta(days=_DEFAULT_PERIOD_DAYS)).isoformat()

        return ResilienceScorecard(
            overall_score=round(overall, 1),
            category_scores=category_scores,
            trend=RiskTrend.STABLE,
            rating=rating,
            period_start=period_start,
            period_end=period_end,
        )

    def estimate_financial_exposure(
        self,
        graph: InfraGraph,
        revenue_per_hour_usd: float = _DEFAULT_REVENUE_PER_HOUR,
    ) -> FinancialExposure:
        """Estimate financial risk from downtime probability.

        Model:
        - ``downtime_probability`` is derived from the inverse of resilience
          posture (more SPOFs / less redundancy = higher probability).
        - ``estimated_annual_loss = downtime_probability * revenue_per_hour *
          estimated_annual_downtime_hours``.
        """
        if not graph.components:
            return FinancialExposure()

        # Use component-level revenue if available
        custom_rev = [
            c.cost_profile.revenue_per_minute * 60
            for c in graph.components.values()
            if c.cost_profile.revenue_per_minute > 0
        ]
        effective_rev = max(custom_rev) if custom_rev else revenue_per_hour_usd

        # Downtime probability grows with lack of redundancy
        redundancy_ratio = _redundancy_score(graph) / 100.0
        spof_count = _count_spofs(graph)
        health_ratio = _health_mix_score(graph) / 100.0

        # Base downtime probability: 0.01 (1%) at perfect, up to 0.15 (15%) worst
        base_prob = 0.01 + 0.14 * (1.0 - redundancy_ratio)
        # Additional penalty for SPOFs
        spof_penalty = min(0.10, spof_count * 0.02)
        # Additional penalty for unhealthy components
        health_penalty = 0.05 * (1.0 - health_ratio)

        downtime_probability = min(1.0, base_prob + spof_penalty + health_penalty)

        estimated_hours = downtime_probability * _HOURS_PER_YEAR * 0.01
        estimated_annual_loss = downtime_probability * effective_rev * estimated_hours

        # Worst case: all SPOFs fail simultaneously, extended outage
        worst_hours = max(estimated_hours * 3.0, 24.0)
        worst_case_loss = effective_rev * worst_hours

        # Insurance gap: 40% of worst case is typical gap
        insurance_gap = worst_case_loss * 0.4

        # ROI of risk reduction
        if estimated_annual_loss > 0:
            potential_reduction = estimated_annual_loss * redundancy_ratio
            investment_estimate = sum(
                c.cost_profile.hourly_infra_cost * _HOURS_PER_YEAR
                for c in graph.components.values()
                if c.replicas >= 2 or c.failover.enabled
            )
            if investment_estimate > 0:
                risk_reduction_roi = (potential_reduction / investment_estimate) * 100.0
            else:
                risk_reduction_roi = 0.0
        else:
            risk_reduction_roi = 0.0

        return FinancialExposure(
            estimated_annual_loss_usd=round(estimated_annual_loss, 2),
            worst_case_loss_usd=round(worst_case_loss, 2),
            insurance_coverage_gap_usd=round(insurance_gap, 2),
            risk_reduction_roi=round(risk_reduction_roi, 1),
        )

    def assess_compliance_status(
        self,
        graph: InfraGraph,
        frameworks: list[str] | None = None,
    ) -> ComplianceSnapshot:
        """Assess compliance posture against a list of frameworks.

        Uses component security profiles and compliance tags to determine
        whether controls are met for each framework.
        """
        if frameworks is None:
            frameworks = list(_COMPLIANCE_FRAMEWORKS_DEFAULT)

        if not graph.components:
            return ComplianceSnapshot(
                frameworks_assessed=len(frameworks),
                compliant_count=0,
                non_compliant_count=len(frameworks),
                compliance_percentage=0.0,
                critical_gaps=["No components to assess"],
            )

        compliant = 0
        non_compliant = 0
        gaps: list[str] = []

        for fw in frameworks:
            score = self._assess_single_framework(graph, fw)
            if score >= 70.0:
                compliant += 1
            else:
                non_compliant += 1
                gaps.append(f"{fw}: score {score:.0f}/100 — below threshold")

        total = compliant + non_compliant
        pct = (compliant / total * 100.0) if total > 0 else 0.0

        return ComplianceSnapshot(
            frameworks_assessed=len(frameworks),
            compliant_count=compliant,
            non_compliant_count=non_compliant,
            compliance_percentage=round(pct, 1),
            critical_gaps=gaps,
        )

    def analyze_incident_trends(
        self,
        incidents: list[dict[str, Any]],
        period_days: int = _DEFAULT_PERIOD_DAYS,
    ) -> list[IncidentTrendData]:
        """Group incidents into weekly buckets and compute trends.

        Each incident dict should contain:
        - ``timestamp``: ISO-format datetime string
        - ``severity``: ``"P1"`` through ``"P4"``
        - ``ttr_hours``: time to resolve
        - ``ttd_hours``: time to detect
        """
        if not incidents:
            return []

        bucket_days = _INCIDENT_PERIOD_BUCKET_DAYS
        num_buckets = max(1, period_days // bucket_days)

        # Parse and sort incidents
        parsed: list[tuple[datetime, dict[str, Any]]] = []
        for inc in incidents:
            ts_raw = inc.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_raw)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
            parsed.append((ts, inc))

        parsed.sort(key=lambda x: x[0])

        if not parsed:
            return []

        earliest = parsed[0][0]
        buckets: list[list[dict[str, Any]]] = [[] for _ in range(num_buckets)]
        for ts, inc in parsed:
            bucket_idx = min(
                num_buckets - 1,
                int((ts - earliest).total_seconds() / (bucket_days * 86400)),
            )
            buckets[bucket_idx].append(inc)

        results: list[IncidentTrendData] = []
        prev_count: int | None = None

        for idx, bucket in enumerate(buckets):
            total = len(bucket)
            p1 = sum(1 for i in bucket if i.get("severity") == "P1")
            ttr_vals = [i.get("ttr_hours", 0.0) for i in bucket]
            ttd_vals = [i.get("ttd_hours", 0.0) for i in bucket]
            mttr = (sum(ttr_vals) / len(ttr_vals)) if ttr_vals else 0.0
            mttd = (sum(ttd_vals) / len(ttd_vals)) if ttd_vals else 0.0

            if prev_count is not None:
                if total < prev_count:
                    trend = RiskTrend.IMPROVING
                elif total > prev_count + 2:
                    trend = RiskTrend.CRITICAL_DECLINE
                elif total > prev_count:
                    trend = RiskTrend.DEGRADING
                else:
                    trend = RiskTrend.STABLE
            else:
                trend = RiskTrend.STABLE

            period_label = f"week-{idx + 1}"
            results.append(
                IncidentTrendData(
                    period=period_label,
                    total_incidents=total,
                    mttr_hours=round(mttr, 2),
                    mttd_hours=round(mttd, 2),
                    p1_count=p1,
                    trend=trend,
                )
            )
            prev_count = total

        return results

    def build_risk_heatmap(
        self,
        graph: InfraGraph,
    ) -> list[RiskHeatmapCell]:
        """Build a risk heatmap with likelihood x impact cells.

        Categories assessed:
        - infrastructure_failure
        - cascade_failure
        - capacity_exhaustion
        - security_breach
        - data_loss
        """
        if not graph.components:
            return []

        cells: list[RiskHeatmapCell] = []

        # 1. Infrastructure failure
        spof_count = _count_spofs(graph)
        total = len(graph.components)
        infra_likelihood = min(1.0, spof_count / max(total, 1) * 1.5)
        infra_impact = 0.7 if spof_count > 0 else 0.3
        cells.append(
            RiskHeatmapCell(
                category="infrastructure_failure",
                likelihood=round(infra_likelihood, 2),
                impact=round(infra_impact, 2),
                risk_level=round(infra_likelihood * infra_impact, 2),
                mitigation_status="partial" if spof_count > 0 else "mitigated",
            )
        )

        # 2. Cascade failure
        paths = graph.get_critical_paths()
        max_depth = len(paths[0]) if paths else 0
        cascade_likelihood = min(1.0, max_depth / 10.0)
        cascade_impact = min(1.0, max_depth / 8.0)
        edges = graph.all_dependency_edges()
        cb_count = sum(1 for e in edges if e.circuit_breaker.enabled) if edges else 0
        if edges and cb_count == len(edges):
            cascade_status = "mitigated"
        elif cb_count > 0:
            cascade_status = "partial"
        else:
            cascade_status = "open"
        cells.append(
            RiskHeatmapCell(
                category="cascade_failure",
                likelihood=round(cascade_likelihood, 2),
                impact=round(cascade_impact, 2),
                risk_level=round(cascade_likelihood * cascade_impact, 2),
                mitigation_status=cascade_status,
            )
        )

        # 3. Capacity exhaustion
        utils = [_component_utilization(c) for c in graph.components.values()]
        max_util = max(utils) / 100.0 if utils else 0.0
        avg_util = (sum(utils) / len(utils)) / 100.0 if utils else 0.0
        cap_likelihood = min(1.0, max_util)
        cap_impact = 0.5 + 0.3 * avg_util
        has_autoscaling = any(c.autoscaling.enabled for c in graph.components.values())
        cells.append(
            RiskHeatmapCell(
                category="capacity_exhaustion",
                likelihood=round(cap_likelihood, 2),
                impact=round(min(1.0, cap_impact), 2),
                risk_level=round(cap_likelihood * min(1.0, cap_impact), 2),
                mitigation_status="mitigated" if has_autoscaling else "open",
            )
        )

        # 4. Security breach
        sec_scores: list[float] = []
        for comp in graph.components.values():
            sp = comp.security
            sec_count = sum([
                sp.encryption_at_rest,
                sp.encryption_in_transit,
                sp.waf_protected,
                sp.rate_limiting,
                sp.auth_required,
                sp.network_segmented,
            ])
            sec_scores.append(sec_count / 6.0)
        avg_sec = sum(sec_scores) / len(sec_scores) if sec_scores else 0.0
        sec_likelihood = 1.0 - avg_sec
        sec_impact = 0.9  # security breaches are always high impact
        cells.append(
            RiskHeatmapCell(
                category="security_breach",
                likelihood=round(sec_likelihood, 2),
                impact=round(sec_impact, 2),
                risk_level=round(sec_likelihood * sec_impact, 2),
                mitigation_status="mitigated" if avg_sec >= 0.8 else ("partial" if avg_sec >= 0.4 else "open"),
            )
        )

        # 5. Data loss
        backup_count = sum(
            1 for c in graph.components.values() if c.security.backup_enabled
        )
        dl_likelihood = 1.0 - (backup_count / total) if total > 0 else 1.0
        dl_impact = 0.95
        cells.append(
            RiskHeatmapCell(
                category="data_loss",
                likelihood=round(dl_likelihood, 2),
                impact=round(dl_impact, 2),
                risk_level=round(dl_likelihood * dl_impact, 2),
                mitigation_status="mitigated" if backup_count == total else ("partial" if backup_count > 0 else "open"),
            )
        )

        return cells

    def forecast_capacity(
        self,
        graph: InfraGraph,
    ) -> list[CapacityForecast]:
        """Forecast capacity runway for each component.

        Uses current utilization to project months until capacity is exhausted,
        assuming a simple linear growth model (5% increase per month as
        default).
        """
        if not graph.components:
            return []

        growth_rate = 0.05  # 5% per month
        forecasts: list[CapacityForecast] = []

        for comp in graph.components.values():
            current_util = _component_utilization(comp)
            # Peak is estimated at 1.3x current for bursty workloads
            peak_util = min(100.0, current_util * 1.3)

            if current_util >= 100.0:
                months = 0.0
            elif growth_rate <= 0:
                months = float("inf")
            else:
                remaining = 100.0 - current_util
                if remaining <= 0:
                    months = 0.0
                else:
                    # months = remaining / (current * growth_rate), min 0.1
                    growth_abs = max(current_util * growth_rate, 1.0)
                    months = remaining / growth_abs

            months = round(min(months, 120.0), 1)

            if months <= 3:
                recommendation = "Scale immediately — capacity exhaustion imminent"
            elif months <= 6:
                recommendation = "Plan scaling within next quarter"
            elif months <= 12:
                recommendation = "Monitor and plan scaling within next year"
            else:
                recommendation = "No immediate action required"

            if comp.autoscaling.enabled:
                recommendation = "Autoscaling enabled — monitor for burst capacity"
                months = max(months, 12.0)

            forecasts.append(
                CapacityForecast(
                    service_id=comp.id,
                    current_utilization=round(current_util, 1),
                    peak_utilization=round(peak_util, 1),
                    months_to_capacity=months,
                    scale_recommendation=recommendation,
                )
            )

        return forecasts

    def generate_executive_summary(
        self,
        dashboard: ExecutiveDashboard,
    ) -> str:
        """Generate a 2-3 sentence executive summary highlighting top risks.

        The summary is suitable for inclusion in board decks or investor
        briefs.
        """
        score = dashboard.scorecard.overall_score
        rating = dashboard.scorecard.rating
        loss = dashboard.financial_exposure.estimated_annual_loss_usd

        parts: list[str] = []

        # Sentence 1: Overall posture
        parts.append(
            f"Infrastructure resilience is rated {rating.value.upper()} "
            f"with an overall score of {score:.0f}/100."
        )

        # Sentence 2: Financial exposure
        if loss > 0:
            parts.append(
                f"Estimated annual financial exposure from downtime is "
                f"${loss:,.0f}."
            )
        else:
            parts.append("No significant financial exposure detected.")

        # Sentence 3: Top risk or compliance
        if dashboard.compliance.critical_gaps:
            gap_count = len(dashboard.compliance.critical_gaps)
            parts.append(
                f"There {'is' if gap_count == 1 else 'are'} "
                f"{gap_count} critical compliance gap{'s' if gap_count != 1 else ''} "
                f"requiring immediate attention."
            )
        elif dashboard.risk_heatmap:
            high_risk = [
                c for c in dashboard.risk_heatmap if c.risk_level > 0.5
            ]
            if high_risk:
                parts.append(
                    f"{len(high_risk)} risk area{'s' if len(high_risk) != 1 else ''} "
                    f"exceed{'s' if len(high_risk) == 1 else ''} acceptable thresholds."
                )
            else:
                parts.append("All risk areas are within acceptable thresholds.")
        else:
            parts.append("No significant risks identified.")

        return " ".join(parts)

    # -- internal helpers ---------------------------------------------------

    def _assess_single_framework(
        self,
        graph: InfraGraph,
        framework: str,
    ) -> float:
        """Score a single compliance framework (0-100).

        Scoring is based on security profiles and compliance tags across all
        components.
        """
        if not graph.components:
            return 0.0

        scores: list[float] = []

        for comp in graph.components.values():
            sp = comp.security
            ct = comp.compliance_tags
            comp_score = 0.0
            checks = 0

            # Common controls across frameworks
            if sp.encryption_at_rest:
                comp_score += 15
            checks += 15

            if sp.encryption_in_transit:
                comp_score += 15
            checks += 15

            if sp.auth_required:
                comp_score += 10
            checks += 10

            if sp.log_enabled:
                comp_score += 10
            checks += 10

            if ct.audit_logging:
                comp_score += 10
            checks += 10

            if ct.change_management:
                comp_score += 10
            checks += 10

            if sp.backup_enabled:
                comp_score += 10
            checks += 10

            if sp.network_segmented:
                comp_score += 10
            checks += 10

            if sp.rate_limiting:
                comp_score += 5
            checks += 5

            if sp.waf_protected:
                comp_score += 5
            checks += 5

            # Framework-specific adjustments
            if framework == "PCI_DSS":
                if ct.pci_scope and not sp.encryption_at_rest:
                    comp_score -= 20
            elif framework == "HIPAA":
                if ct.contains_phi and not sp.encryption_at_rest:
                    comp_score -= 20
                if ct.contains_phi and not ct.audit_logging:
                    comp_score -= 15
            elif framework == "SOC2":
                if not ct.change_management:
                    comp_score -= 5

            normalized = max(0.0, min(100.0, (comp_score / checks * 100.0) if checks > 0 else 0.0))
            scores.append(normalized)

        return sum(scores) / len(scores) if scores else 0.0

    def _build_recommendations(
        self,
        graph: InfraGraph,
        scorecard: ResilienceScorecard,
    ) -> list[str]:
        """Generate prioritized recommendations."""
        recs: list[str] = []

        score = scorecard.overall_score

        if score < 50:
            recs.append(
                "URGENT: Resilience score is critically low. "
                "Prioritize redundancy and failover for all critical components."
            )
        elif score < 75:
            recs.append(
                "Resilience score below target. Focus on eliminating single "
                "points of failure and improving dependency diversity."
            )

        # SPOF
        for comp in graph.components.values():
            if comp.replicas <= 1 and not comp.failover.enabled:
                dependents = graph.get_dependents(comp.id)
                if dependents:
                    recs.append(
                        f"Add redundancy to '{comp.name}' — single point of failure "
                        f"affecting {len(dependents)} dependent(s)."
                    )

        # Unhealthy
        for comp in graph.components.values():
            if comp.health == HealthStatus.DOWN:
                recs.append(
                    f"Investigate and restore '{comp.name}' (currently DOWN)."
                )
            elif comp.health == HealthStatus.DEGRADED:
                recs.append(
                    f"Address degradation in '{comp.name}' before it becomes critical."
                )

        # High utilization
        for comp in graph.components.values():
            util = _component_utilization(comp)
            if util > 80:
                recs.append(
                    f"Scale '{comp.name}' — utilization at {util:.0f}% "
                    f"(target < 60%)."
                )

        # Circuit breakers
        edges = graph.all_dependency_edges()
        missing = sum(1 for e in edges if not e.circuit_breaker.enabled)
        if missing > 0:
            recs.append(
                f"Enable circuit breakers on {missing} unprotected dependency edge(s)."
            )

        # Autoscaling
        no_as = [c for c in graph.components.values() if not c.autoscaling.enabled]
        if no_as and len(graph.components) > 1:
            recs.append(
                f"Enable autoscaling for {len(no_as)} component(s) to "
                f"improve recovery time."
            )

        return recs[:10]
