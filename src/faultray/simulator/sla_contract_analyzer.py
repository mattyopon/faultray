"""SLA Contract Analyzer -- cross-service SLA analysis and validation.

Analyzes SLA contracts across dependent services, computes composite SLAs,
detects monitoring gaps, validates upstream/downstream consistency, tracks
historical compliance, derives error budgets, allocates SLA budgets,
generates compliance reports, and assesses third-party dependency risk.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SLAMetricType(str, Enum):
    """Type of SLA metric."""

    AVAILABILITY = "availability"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    DURABILITY = "durability"


class CompliancePeriod(str, Enum):
    """Reporting period for compliance reports."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class RiskLevel(str, Enum):
    """Risk severity level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConsistencyStatus(str, Enum):
    """Result of upstream/downstream consistency check."""

    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    WARNING = "warning"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SLAContract(BaseModel):
    """An SLA contract for a single service."""

    service_id: str
    metric_type: SLAMetricType = SLAMetricType.AVAILABILITY
    target_value: float = Field(default=99.9, ge=0.0, le=100.0)
    penalty_rate_per_percent: float = Field(default=1000.0, ge=0.0)
    measurement_window_days: int = Field(default=30, ge=1)
    monthly_contract_value: float = Field(default=10000.0, ge=0.0)
    is_third_party: bool = False
    provider_name: str = ""


class ComplianceRecord(BaseModel):
    """Historical compliance record for a service in a given period."""

    service_id: str
    period_start: datetime
    period_end: datetime
    actual_value: float
    target_value: float
    met_sla: bool
    penalty_incurred: float = 0.0
    downtime_minutes: float = 0.0


class CompositeResult(BaseModel):
    """Result of composite SLA calculation."""

    composite_sla: float
    weakest_service: str
    chain_depth: int
    services_analyzed: int
    per_service_sla: dict[str, float] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class PenaltyEstimate(BaseModel):
    """Estimated financial penalty for SLA breach."""

    service_id: str
    breach_amount_percent: float
    penalty_amount: float
    contract_credit_percent: float
    risk_level: RiskLevel
    details: str = ""


class MonitoringGap(BaseModel):
    """A detected gap in SLA monitoring coverage."""

    service_id: str
    gap_type: str
    description: str
    severity: RiskLevel
    recommendation: str = ""


class ConsistencyResult(BaseModel):
    """Result of upstream/downstream SLA consistency validation."""

    status: ConsistencyStatus
    issues: list[str] = Field(default_factory=list)
    upstream_services: list[str] = Field(default_factory=list)
    downstream_services: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class BudgetAllocation(BaseModel):
    """SLA budget allocation for a service."""

    service_id: str
    allocated_downtime_minutes: float
    weight: float
    fraction_of_total: float


class ErrorBudgetResult(BaseModel):
    """Error budget derived from an SLA target."""

    service_id: str
    target_value: float
    error_budget_percent: float
    error_budget_minutes_per_month: float
    monthly_request_budget: float


class ComplianceReport(BaseModel):
    """Periodic SLA compliance report."""

    period: CompliancePeriod
    period_start: datetime
    period_end: datetime
    overall_compliance_rate: float
    services_in_compliance: int
    services_in_violation: int
    total_penalty: float
    per_service: list[dict[str, object]] = Field(default_factory=list)
    summary: str = ""
    recommendations: list[str] = Field(default_factory=list)


class ThirdPartyRisk(BaseModel):
    """Risk assessment for a third-party SLA dependency."""

    service_id: str
    provider_name: str
    provider_sla: float
    impact_on_composite: float
    risk_level: RiskLevel
    recommendation: str = ""


class CascadeImpact(BaseModel):
    """How one service's SLA breach affects the composite SLA."""

    breached_service: str
    original_composite: float
    degraded_composite: float
    composite_drop: float
    affected_services: list[str] = Field(default_factory=list)
    cascade_depth: int = 0
    risk_level: RiskLevel = RiskLevel.LOW


class NegotiationRecommendation(BaseModel):
    """Recommendation for SLA negotiation with a provider."""

    service_id: str
    current_target: float
    recommended_target: float
    rationale: str
    estimated_cost_impact: float = 0.0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MINUTES_PER_MONTH: float = 30 * 24 * 60  # 43200


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SLAContractAnalyzer:
    """Engine for comprehensive SLA contract analysis.

    Operates on an :class:`InfraGraph` and a mapping of service-level
    SLA contracts to compute composite SLAs, detect monitoring gaps,
    validate consistency, track compliance, and generate reports.
    """

    # ------------------------------------------------------------------
    # Composite SLA
    # ------------------------------------------------------------------

    def calculate_composite_sla(
        self,
        graph: InfraGraph,
        contracts: dict[str, SLAContract],
    ) -> CompositeResult:
        """Compute the composite SLA from dependent service SLAs.

        For availability contracts, SLAs are composed multiplicatively
        (product of individual availability fractions).  For other
        metric types, the weakest (minimum) target is used.

        Services in the graph without a contract are assumed to have
        100% SLA (perfect).
        """
        if not graph.components:
            return CompositeResult(
                composite_sla=100.0,
                weakest_service="",
                chain_depth=0,
                services_analyzed=0,
            )

        per_service: dict[str, float] = {}
        for cid in graph.components:
            contract = contracts.get(cid)
            per_service[cid] = contract.target_value if contract else 100.0

        dominant = self._dominant_metric(contracts)
        if dominant == SLAMetricType.AVAILABILITY:
            composite = self._multiply_availability(per_service)
        else:
            composite = min(per_service.values()) if per_service else 100.0

        weakest = min(per_service, key=per_service.get) if per_service else ""  # type: ignore[arg-type]
        chain_depth = self._max_chain_depth(graph)

        recs: list[str] = []
        if composite < 99.0:
            recs.append(
                f"Composite SLA {composite:.4f}% is below 99%. "
                "Improve the weakest services or add redundancy."
            )
        if chain_depth > 5:
            recs.append(
                f"Dependency chain depth is {chain_depth}. "
                "Deep chains amplify SLA degradation."
            )
        for cid in graph.components:
            if cid not in contracts:
                recs.append(
                    f"Service '{cid}' has no SLA contract. "
                    "Define a contract to ensure coverage."
                )
                break
        if not recs:
            recs.append("SLA composition looks healthy.")

        return CompositeResult(
            composite_sla=round(composite, 6),
            weakest_service=weakest,
            chain_depth=chain_depth,
            services_analyzed=len(per_service),
            per_service_sla=per_service,
            recommendations=recs,
        )

    # ------------------------------------------------------------------
    # Penalty Calculation
    # ------------------------------------------------------------------

    def calculate_penalty(
        self,
        contract: SLAContract,
        actual_value: float,
    ) -> PenaltyEstimate:
        """Calculate financial penalty for an SLA breach.

        The penalty is proportional to the breach amount (how far below
        the target the actual value fell) times the contractual penalty
        rate.  A credit percentage against the monthly contract value
        is also computed.
        """
        breach = contract.target_value - actual_value
        if breach <= 0:
            return PenaltyEstimate(
                service_id=contract.service_id,
                breach_amount_percent=0.0,
                penalty_amount=0.0,
                contract_credit_percent=0.0,
                risk_level=RiskLevel.LOW,
                details="SLA met -- no penalty.",
            )

        penalty = breach * contract.penalty_rate_per_percent
        credit_pct = (
            (penalty / contract.monthly_contract_value * 100.0)
            if contract.monthly_contract_value > 0
            else 0.0
        )

        if breach > 5.0:
            risk = RiskLevel.CRITICAL
        elif breach > 2.0:
            risk = RiskLevel.HIGH
        elif breach > 0.5:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        return PenaltyEstimate(
            service_id=contract.service_id,
            breach_amount_percent=round(breach, 6),
            penalty_amount=round(penalty, 2),
            contract_credit_percent=round(credit_pct, 2),
            risk_level=risk,
            details=(
                f"Actual {actual_value}% vs target {contract.target_value}%. "
                f"Breach of {breach:.4f}%."
            ),
        )

    # ------------------------------------------------------------------
    # Monitoring Gap Detection
    # ------------------------------------------------------------------

    def detect_monitoring_gaps(
        self,
        graph: InfraGraph,
        contracts: dict[str, SLAContract],
    ) -> list[MonitoringGap]:
        """Detect gaps in SLA monitoring coverage.

        Checks for:
        - Services with SLA contracts but no SLO targets configured
        - Services in the graph with no SLA contract
        - Services with contracts but without matching metric-type SLO
        - Third-party services missing provider SLA configuration
        """
        gaps: list[MonitoringGap] = []

        for cid, comp in graph.components.items():
            contract = contracts.get(cid)

            # No contract at all.
            if contract is None:
                gaps.append(MonitoringGap(
                    service_id=cid,
                    gap_type="no_contract",
                    description=f"Service '{cid}' is in the graph but has no SLA contract.",
                    severity=RiskLevel.MEDIUM,
                    recommendation="Define an SLA contract for this service.",
                ))
                continue

            # No SLO targets on the component.
            if not comp.slo_targets:
                gaps.append(MonitoringGap(
                    service_id=cid,
                    gap_type="no_slo_targets",
                    description=(
                        f"Service '{cid}' has an SLA contract but no SLO targets "
                        "configured on the component."
                    ),
                    severity=RiskLevel.HIGH,
                    recommendation="Add SLO targets to the component to enable monitoring.",
                ))

            # Third-party missing external_sla config.
            if contract.is_third_party and comp.external_sla is None:
                gaps.append(MonitoringGap(
                    service_id=cid,
                    gap_type="missing_external_sla",
                    description=(
                        f"Third-party service '{cid}' (provider: {contract.provider_name}) "
                        "has no external_sla configuration on the component."
                    ),
                    severity=RiskLevel.HIGH,
                    recommendation="Set external_sla on the component for accurate modelling.",
                ))

            # Metric-type mismatch between contract and SLO targets.
            if comp.slo_targets:
                slo_metrics = {s.metric for s in comp.slo_targets}
                expected_metric = contract.metric_type.value
                if expected_metric not in slo_metrics:
                    gaps.append(MonitoringGap(
                        service_id=cid,
                        gap_type="metric_mismatch",
                        description=(
                            f"Service '{cid}' SLA contract is for '{expected_metric}' "
                            f"but SLO targets only cover: {sorted(slo_metrics)}."
                        ),
                        severity=RiskLevel.MEDIUM,
                        recommendation=(
                            f"Add an SLO target for '{expected_metric}' on the component."
                        ),
                    ))

        return gaps

    # ------------------------------------------------------------------
    # Upstream/Downstream Consistency
    # ------------------------------------------------------------------

    def validate_consistency(
        self,
        graph: InfraGraph,
        contracts: dict[str, SLAContract],
        service_id: str,
    ) -> ConsistencyResult:
        """Validate that a service's SLA is consistent with its dependencies.

        A service should not promise a higher SLA than what its
        dependencies can collectively deliver (composite of downstream).
        Its SLA should also be at least as good as what upstream
        services expect.
        """
        if service_id not in graph.components:
            return ConsistencyResult(
                status=ConsistencyStatus.CONSISTENT,
                issues=["Service not found in graph."],
            )

        contract = contracts.get(service_id)
        if contract is None:
            return ConsistencyResult(
                status=ConsistencyStatus.WARNING,
                issues=[f"Service '{service_id}' has no SLA contract."],
                recommendations=["Define an SLA contract for this service."],
            )

        target = contract.target_value
        issues: list[str] = []
        recs: list[str] = []

        # Downstream: services this service depends on.
        downstream = graph.get_dependencies(service_id)
        downstream_ids = [d.id for d in downstream]
        downstream_slas: list[float] = []
        for d in downstream:
            dc = contracts.get(d.id)
            downstream_slas.append(dc.target_value if dc else 100.0)

        if downstream_slas:
            composite_downstream = self._multiply_availability(
                {f"d{i}": v for i, v in enumerate(downstream_slas)}
            )
            if target > composite_downstream:
                issues.append(
                    f"Service '{service_id}' promises {target}% but downstream "
                    f"composite is only {composite_downstream:.4f}%."
                )
                recs.append(
                    "Lower the service SLA or improve downstream dependencies."
                )

        # Upstream: services that depend on this service.
        upstream = graph.get_dependents(service_id)
        upstream_ids = [u.id for u in upstream]
        for u in upstream:
            uc = contracts.get(u.id)
            if uc and uc.target_value > target:
                issues.append(
                    f"Upstream service '{u.id}' expects {uc.target_value}% "
                    f"but '{service_id}' only offers {target}%."
                )
                recs.append(
                    f"Raise '{service_id}' SLA to at least {uc.target_value}% "
                    f"or lower '{u.id}' SLA."
                )

        if issues:
            status = ConsistencyStatus.INCONSISTENT
        else:
            status = ConsistencyStatus.CONSISTENT

        return ConsistencyResult(
            status=status,
            issues=issues,
            upstream_services=upstream_ids,
            downstream_services=downstream_ids,
            recommendations=recs,
        )

    # ------------------------------------------------------------------
    # SLA Budget Allocation
    # ------------------------------------------------------------------

    def allocate_sla_budget(
        self,
        graph: InfraGraph,
        contracts: dict[str, SLAContract],
        total_downtime_budget_minutes: float,
    ) -> list[BudgetAllocation]:
        """Allocate total downtime budget across services.

        Weight is determined by number of dependents (upstream impact).
        Services with more dependents get a smaller share of the budget
        (i.e. tighter constraint) because their outage is more impactful.
        """
        if not contracts:
            return []

        weights: dict[str, float] = {}
        for sid in contracts:
            if sid in graph.components:
                n_deps = len(graph.get_dependents(sid))
            else:
                n_deps = 0
            # Inverse weight: more dependents -> lower downtime allowance.
            weights[sid] = 1.0 / (1.0 + n_deps)

        total_weight = sum(weights.values())
        allocations: list[BudgetAllocation] = []
        for sid, w in weights.items():
            fraction = w / total_weight if total_weight > 0 else 0.0
            allocated = total_downtime_budget_minutes * fraction
            allocations.append(BudgetAllocation(
                service_id=sid,
                allocated_downtime_minutes=round(allocated, 2),
                weight=round(w, 4),
                fraction_of_total=round(fraction, 4),
            ))

        return sorted(allocations, key=lambda a: a.allocated_downtime_minutes)

    # ------------------------------------------------------------------
    # Historical SLA Compliance Tracking
    # ------------------------------------------------------------------

    def track_compliance(
        self,
        records: list[ComplianceRecord],
    ) -> dict[str, object]:
        """Analyze historical compliance records.

        Returns per-service and aggregate statistics including
        compliance rate, total penalties, and trend.
        """
        if not records:
            return {
                "total_records": 0,
                "overall_compliance_rate": 100.0,
                "total_penalty": 0.0,
                "per_service": {},
            }

        per_service: dict[str, dict[str, object]] = defaultdict(lambda: {
            "total": 0,
            "met": 0,
            "penalty": 0.0,
            "worst_actual": 100.0,
        })

        for r in records:
            entry = per_service[r.service_id]
            entry["total"] = int(entry["total"]) + 1  # type: ignore[arg-type]
            if r.met_sla:
                entry["met"] = int(entry["met"]) + 1  # type: ignore[arg-type]
            entry["penalty"] = float(entry["penalty"]) + r.penalty_incurred  # type: ignore[arg-type]
            entry["worst_actual"] = min(float(entry["worst_actual"]), r.actual_value)  # type: ignore[arg-type]

        total = len(records)
        met = sum(1 for r in records if r.met_sla)
        overall_rate = (met / total * 100.0) if total > 0 else 100.0
        total_penalty = sum(r.penalty_incurred for r in records)

        # Build per-service summaries.
        service_summary: dict[str, dict[str, object]] = {}
        for sid, info in per_service.items():
            t = int(info["total"])
            m = int(info["met"])
            service_summary[sid] = {
                "compliance_rate": round(m / t * 100.0, 2) if t > 0 else 100.0,
                "total_records": t,
                "met": m,
                "total_penalty": round(float(info["penalty"]), 2),
                "worst_actual": float(info["worst_actual"]),
            }

        return {
            "total_records": total,
            "overall_compliance_rate": round(overall_rate, 2),
            "total_penalty": round(total_penalty, 2),
            "per_service": service_summary,
        }

    # ------------------------------------------------------------------
    # Error Budget Derivation
    # ------------------------------------------------------------------

    def derive_error_budget(
        self,
        contract: SLAContract,
        monthly_requests: float = 1_000_000,
    ) -> ErrorBudgetResult:
        """Derive error budget from an SLA target.

        The error budget is ``100 - target`` expressed as a percentage.
        It is also converted to allowable downtime minutes per month
        and a request failure budget.
        """
        error_pct = 100.0 - contract.target_value
        downtime_minutes = _MINUTES_PER_MONTH * (error_pct / 100.0)
        request_budget = monthly_requests * (error_pct / 100.0)

        return ErrorBudgetResult(
            service_id=contract.service_id,
            target_value=contract.target_value,
            error_budget_percent=round(error_pct, 6),
            error_budget_minutes_per_month=round(downtime_minutes, 2),
            monthly_request_budget=round(request_budget, 2),
        )

    # ------------------------------------------------------------------
    # SLA Negotiation Recommendations
    # ------------------------------------------------------------------

    def recommend_negotiations(
        self,
        graph: InfraGraph,
        contracts: dict[str, SLAContract],
    ) -> list[NegotiationRecommendation]:
        """Generate SLA negotiation recommendations.

        Suggests target adjustments based on:
        - Consistency with downstream composite SLA
        - Number of upstream dependents
        - Third-party provider targets
        """
        recs: list[NegotiationRecommendation] = []

        for sid, contract in contracts.items():
            if sid not in graph.components:
                continue

            target = contract.target_value

            # Check downstream composite.
            downstream = graph.get_dependencies(sid)
            if downstream:
                ds_slas = [
                    contracts[d.id].target_value
                    if d.id in contracts else 100.0
                    for d in downstream
                ]
                composite_ds = self._multiply_availability(
                    {f"d{i}": v for i, v in enumerate(ds_slas)}
                )
                if target > composite_ds + 0.01:
                    recommended = math.floor(composite_ds * 100) / 100.0
                    recs.append(NegotiationRecommendation(
                        service_id=sid,
                        current_target=target,
                        recommended_target=recommended,
                        rationale=(
                            f"Downstream composite is {composite_ds:.4f}%. "
                            f"Current target {target}% is unreachable."
                        ),
                        estimated_cost_impact=(target - recommended)
                        * contract.penalty_rate_per_percent * -1,
                    ))

            # Critical service with many dependents should have higher SLA.
            dependents = graph.get_dependents(sid)
            if len(dependents) > 3 and target < 99.99:
                recs.append(NegotiationRecommendation(
                    service_id=sid,
                    current_target=target,
                    recommended_target=99.99,
                    rationale=(
                        f"Service has {len(dependents)} dependents. "
                        "Negotiate a higher SLA to protect upstream services."
                    ),
                    estimated_cost_impact=(99.99 - target)
                    * contract.penalty_rate_per_percent,
                ))

            # Third-party with low SLA.
            if contract.is_third_party and target < 99.9:
                recs.append(NegotiationRecommendation(
                    service_id=sid,
                    current_target=target,
                    recommended_target=99.9,
                    rationale=(
                        f"Third-party '{contract.provider_name}' SLA is below 99.9%. "
                        "Negotiate higher availability with the provider."
                    ),
                    estimated_cost_impact=(99.9 - target)
                    * contract.penalty_rate_per_percent,
                ))

        return recs

    # ------------------------------------------------------------------
    # SLA Reporting
    # ------------------------------------------------------------------

    def generate_compliance_report(
        self,
        contracts: dict[str, SLAContract],
        records: list[ComplianceRecord],
        period: CompliancePeriod = CompliancePeriod.MONTHLY,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> ComplianceReport:
        """Generate a monthly or quarterly SLA compliance report."""
        now = datetime.now(timezone.utc)
        if period_end is None:
            period_end = now
        if period_start is None:
            delta = timedelta(days=30) if period == CompliancePeriod.MONTHLY else timedelta(days=90)
            period_start = period_end - delta

        # Filter records to the period.
        period_records = [
            r for r in records
            if period_start <= r.period_start <= period_end
        ]

        total = len(period_records)
        met = sum(1 for r in period_records if r.met_sla)
        overall_rate = (met / total * 100.0) if total > 0 else 100.0
        total_penalty = sum(r.penalty_incurred for r in period_records)

        per_service: list[dict[str, object]] = []
        svc_groups: dict[str, list[ComplianceRecord]] = defaultdict(list)
        for r in period_records:
            svc_groups[r.service_id].append(r)

        in_compliance = 0
        in_violation = 0
        for sid, recs_list in svc_groups.items():
            svc_met = sum(1 for r in recs_list if r.met_sla)
            svc_total = len(recs_list)
            svc_rate = (svc_met / svc_total * 100.0) if svc_total > 0 else 100.0
            svc_penalty = sum(r.penalty_incurred for r in recs_list)
            if svc_rate >= 100.0:
                in_compliance += 1
            else:
                in_violation += 1
            per_service.append({
                "service_id": sid,
                "compliance_rate": round(svc_rate, 2),
                "total_records": svc_total,
                "penalty": round(svc_penalty, 2),
            })

        # Handle services with contracts but no records.
        for sid in contracts:
            if sid not in svc_groups:
                in_compliance += 1
                per_service.append({
                    "service_id": sid,
                    "compliance_rate": 100.0,
                    "total_records": 0,
                    "penalty": 0.0,
                })

        recs_out: list[str] = []
        if overall_rate < 99.0:
            recs_out.append(
                f"Overall compliance rate {overall_rate:.1f}% is below 99%. "
                "Review SLA strategies."
            )
        if total_penalty > 10_000:
            recs_out.append(
                f"Total penalties ${total_penalty:,.2f} are significant. "
                "Investigate root causes."
            )
        if not recs_out:
            recs_out.append("Compliance report looks healthy.")

        period_label = period.value
        summary = (
            f"{period_label.capitalize()} report: {in_compliance} services in compliance, "
            f"{in_violation} in violation. Total penalty: ${total_penalty:,.2f}."
        )

        return ComplianceReport(
            period=period,
            period_start=period_start,
            period_end=period_end,
            overall_compliance_rate=round(overall_rate, 2),
            services_in_compliance=in_compliance,
            services_in_violation=in_violation,
            total_penalty=round(total_penalty, 2),
            per_service=per_service,
            summary=summary,
            recommendations=recs_out,
        )

    # ------------------------------------------------------------------
    # Third-Party SLA Dependency Risk
    # ------------------------------------------------------------------

    def assess_third_party_risk(
        self,
        graph: InfraGraph,
        contracts: dict[str, SLAContract],
    ) -> list[ThirdPartyRisk]:
        """Assess risk from third-party SLA dependencies.

        Evaluates how each third-party service's SLA affects the
        composite SLA and assigns a risk level.
        """
        # Build full per-service map.
        per_service: dict[str, float] = {}
        for cid in graph.components:
            c = contracts.get(cid)
            per_service[cid] = c.target_value if c else 100.0

        full_composite = self._multiply_availability(per_service)

        risks: list[ThirdPartyRisk] = []
        for sid, contract in contracts.items():
            if not contract.is_third_party:
                continue

            # Composite without this service (treat as 100%).
            without = {k: v for k, v in per_service.items() if k != sid}
            if without:
                composite_without = self._multiply_availability(without)
            else:
                composite_without = 100.0

            impact = composite_without - full_composite

            if impact > 1.0:
                risk = RiskLevel.CRITICAL
            elif impact > 0.5:
                risk = RiskLevel.HIGH
            elif impact > 0.1:
                risk = RiskLevel.MEDIUM
            else:
                risk = RiskLevel.LOW

            rec = ""
            if risk in (RiskLevel.CRITICAL, RiskLevel.HIGH):
                rec = (
                    f"Third-party '{contract.provider_name}' significantly impacts "
                    "composite SLA. Consider adding redundancy or negotiating "
                    "a higher SLA."
                )
            elif risk == RiskLevel.MEDIUM:
                rec = (
                    f"Monitor third-party '{contract.provider_name}' SLA closely."
                )

            risks.append(ThirdPartyRisk(
                service_id=sid,
                provider_name=contract.provider_name,
                provider_sla=contract.target_value,
                impact_on_composite=round(impact, 6),
                risk_level=risk,
                recommendation=rec,
            ))

        return risks

    # ------------------------------------------------------------------
    # SLA Cascade Impact
    # ------------------------------------------------------------------

    def analyze_cascade_impact(
        self,
        graph: InfraGraph,
        contracts: dict[str, SLAContract],
        breached_service: str,
        degraded_sla: float | None = None,
    ) -> CascadeImpact:
        """Analyze how one service's SLA breach affects the composite SLA.

        Computes the composite SLA before and after the breach, the
        drop, and which upstream services are affected.
        """
        per_service: dict[str, float] = {}
        for cid in graph.components:
            c = contracts.get(cid)
            per_service[cid] = c.target_value if c else 100.0

        original = self._multiply_availability(per_service)

        # Apply degradation.
        if breached_service in per_service:
            if degraded_sla is not None:
                per_service[breached_service] = degraded_sla
            else:
                # Default: drop by 1% of current value.
                per_service[breached_service] *= 0.99

        degraded = self._multiply_availability(per_service)
        drop = original - degraded

        affected: list[str] = []
        if breached_service in graph.components:
            affected = sorted(graph.get_all_affected(breached_service))

        cascade_depth = self._cascade_depth_bfs(graph, breached_service)

        if drop > 1.0:
            risk = RiskLevel.CRITICAL
        elif drop > 0.5:
            risk = RiskLevel.HIGH
        elif drop > 0.1:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        return CascadeImpact(
            breached_service=breached_service,
            original_composite=round(original, 6),
            degraded_composite=round(degraded, 6),
            composite_drop=round(drop, 6),
            affected_services=affected,
            cascade_depth=cascade_depth,
            risk_level=risk,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dominant_metric(contracts: dict[str, SLAContract]) -> SLAMetricType:
        """Return the most common metric type, defaulting to AVAILABILITY."""
        if not contracts:
            return SLAMetricType.AVAILABILITY
        counts: dict[SLAMetricType, int] = {}
        for c in contracts.values():
            counts[c.metric_type] = counts.get(c.metric_type, 0) + 1
        return max(counts, key=counts.get)  # type: ignore[arg-type]

    @staticmethod
    def _multiply_availability(sla_map: dict[str, float]) -> float:
        """Multiply individual availability fractions to get composite."""
        composite = 1.0
        for v in sla_map.values():
            composite *= v / 100.0
        return composite * 100.0

    @staticmethod
    def _max_chain_depth(graph: InfraGraph) -> int:
        """Longest dependency chain length in the graph."""
        if not graph.components:
            return 0
        try:
            import networkx as nx
            return nx.dag_longest_path_length(graph._graph) + 1
        except Exception:
            return len(graph.components)

    @staticmethod
    def _cascade_depth_bfs(graph: InfraGraph, component_id: str) -> int:
        """BFS depth from *component_id* through its dependents."""
        if component_id not in graph.components:
            return 0
        from collections import deque
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(component_id, 0)])
        max_depth = 0
        while queue:
            current, depth = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            max_depth = max(max_depth, depth)
            for dep in graph.get_dependents(current):
                if dep.id not in visited:
                    queue.append((dep.id, depth + 1))
        return max_depth
