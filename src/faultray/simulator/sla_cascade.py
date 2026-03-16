"""SLA Cascade Calculator — composite SLA computation and cascade impact prediction.

Calculates composite SLA from dependency chains and predicts how SLA
violations propagate through service graphs. Provides financial risk
estimation, conflict detection, and compliance projection.
"""

from __future__ import annotations

from collections import deque
from enum import Enum

import networkx as nx
from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SLAType(str, Enum):
    """Type of SLA metric being tracked."""

    AVAILABILITY = "availability"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    DURABILITY = "durability"


class SLATier(str, Enum):
    """SLA service tier level."""

    PLATINUM = "platinum"
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"
    BEST_EFFORT = "best_effort"


# Default target values per tier (availability percentage).
_TIER_DEFAULTS: dict[SLATier, float] = {
    SLATier.PLATINUM: 99.999,
    SLATier.GOLD: 99.99,
    SLATier.SILVER: 99.9,
    SLATier.BRONZE: 99.5,
    SLATier.BEST_EFFORT: 95.0,
}

# Default penalty per violation percent (USD) per tier.
_TIER_PENALTY_DEFAULTS: dict[SLATier, float] = {
    SLATier.PLATINUM: 10000.0,
    SLATier.GOLD: 5000.0,
    SLATier.SILVER: 2000.0,
    SLATier.BRONZE: 500.0,
    SLATier.BEST_EFFORT: 0.0,
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ServiceSLA(BaseModel):
    """SLA definition for a single service."""

    service_id: str
    sla_type: SLAType = SLAType.AVAILABILITY
    target: float = Field(default=99.9, ge=0.0, le=100.0)
    tier: SLATier = SLATier.SILVER
    penalty_per_violation_percent: float = Field(default=2000.0, ge=0.0)
    measurement_window_days: int = Field(default=30, ge=1)


class CascadeResult(BaseModel):
    """Result of composite SLA calculation across a dependency chain."""

    composite_sla: float
    weakest_link: str
    chain_depth: int
    bottleneck_services: list[str] = Field(default_factory=list)
    sla_gap: float = 0.0
    financial_risk: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class SLABreachImpact(BaseModel):
    """Impact analysis of an SLA breach on a specific service."""

    breached_service: str
    affected_services: list[str] = Field(default_factory=list)
    cascade_depth: int = 0
    total_sla_degradation: float = 0.0
    estimated_penalty: float = 0.0
    recovery_recommendations: list[str] = Field(default_factory=list)


class FinancialRiskReport(BaseModel):
    """Financial risk summary from SLA analysis."""

    total_annual_risk: float = 0.0
    service_risks: dict[str, float] = Field(default_factory=dict)
    highest_risk_service: str = ""
    risk_by_tier: dict[str, float] = Field(default_factory=dict)
    mitigation_savings: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class SLAConflict(BaseModel):
    """A detected conflict between SLA definitions."""

    service_id: str
    conflict_type: str
    description: str
    severity: str = "warning"
    resolution: str = ""


class ComplianceProjection(BaseModel):
    """SLA compliance projection over time."""

    months: int = 12
    projected_compliance_rate: float = 100.0
    projected_violations: int = 0
    projected_penalty_total: float = 0.0
    monthly_projections: list[dict[str, float]] = Field(default_factory=list)
    risk_trend: str = "stable"
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SLACascadeEngine:
    """Engine for computing composite SLAs and cascade impacts.

    Works with an :class:`InfraGraph` plus a mapping of per-service SLA
    definitions to calculate how SLA targets compose across dependency
    chains, detect conflicts, predict breaches and estimate financial risk.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_composite_sla(
        self,
        graph: InfraGraph,
        slas: dict[str, ServiceSLA],
    ) -> CascadeResult:
        """Calculate the composite SLA for a dependency graph.

        For availability SLAs the composite is the product of individual
        availability fractions. For other SLA types the weakest target is
        used. Services without an explicit SLA entry are treated as 100%
        (perfect).

        Returns a :class:`CascadeResult` with composite value, weakest
        link identification, bottleneck list and recommendations.
        """
        if not graph.components:
            return CascadeResult(
                composite_sla=100.0,
                weakest_link="",
                chain_depth=0,
            )

        sla_values: dict[str, float] = {}
        for cid in graph.components:
            sla = slas.get(cid)
            sla_values[cid] = sla.target if sla else 100.0

        # Determine dominant SLA type from the provided SLAs.
        dominant_type = self._dominant_sla_type(slas)

        if dominant_type == SLAType.AVAILABILITY:
            composite = self._composite_availability(sla_values)
        else:
            composite = min(sla_values.values()) if sla_values else 100.0

        weakest = self.find_weakest_link(graph, slas)
        chain_depth = self._max_chain_depth(graph)
        bottlenecks = self._find_bottlenecks(graph, slas)

        # SLA gap: difference between best and worst individual SLA.
        targets = [sla.target for sla in slas.values()] if slas else []
        sla_gap = (max(targets) - min(targets)) if targets else 0.0

        # Financial risk estimate (annual).
        financial_risk = self._estimate_financial_risk_simple(slas)

        recommendations = self._generate_recommendations(
            graph, slas, composite, bottlenecks, chain_depth,
        )

        return CascadeResult(
            composite_sla=round(composite, 6),
            weakest_link=weakest,
            chain_depth=chain_depth,
            bottleneck_services=bottlenecks,
            sla_gap=round(sla_gap, 6),
            financial_risk=round(financial_risk, 2),
            recommendations=recommendations,
        )

    def find_weakest_link(
        self,
        graph: InfraGraph,
        slas: dict[str, ServiceSLA],
    ) -> str:
        """Return the service_id with the lowest SLA target.

        If multiple services share the lowest target, the one with the
        most dependents (highest upstream impact) is returned.
        """
        if not slas:
            return ""

        min_target = min(s.target for s in slas.values())
        candidates = [sid for sid, s in slas.items() if s.target == min_target]

        if len(candidates) == 1:
            return candidates[0]

        # Break tie by number of dependents.
        best = candidates[0]
        best_deps = len(graph.get_dependents(best)) if best in graph.components else 0
        for cid in candidates[1:]:
            n = len(graph.get_dependents(cid)) if cid in graph.components else 0
            if n > best_deps:
                best = cid
                best_deps = n
        return best

    def simulate_sla_breach(
        self,
        graph: InfraGraph,
        slas: dict[str, ServiceSLA],
        breached_service: str,
    ) -> SLABreachImpact:
        """Simulate the impact of an SLA breach on *breached_service*.

        Traces all upstream dependents and estimates cascading SLA
        degradation and penalty costs.
        """
        if breached_service not in graph.components:
            return SLABreachImpact(breached_service=breached_service)

        affected = graph.get_all_affected(breached_service)
        affected_list = sorted(affected)

        cascade_depth = self._cascade_depth_from(graph, breached_service)

        # Degradation: each hop reduces effective availability multiplicatively.
        breached_sla = slas.get(breached_service)
        breach_gap = 0.0
        if breached_sla:
            breach_gap = breached_sla.target - (breached_sla.target * 0.99)

        total_degradation = breach_gap * (1 + len(affected_list))

        estimated_penalty = 0.0
        if breached_sla:
            estimated_penalty += breached_sla.penalty_per_violation_percent * max(breach_gap, 1.0)
        for aid in affected_list:
            a_sla = slas.get(aid)
            if a_sla:
                estimated_penalty += a_sla.penalty_per_violation_percent * max(breach_gap * 0.5, 0.5)

        recommendations: list[str] = []
        if cascade_depth > 2:
            recommendations.append(
                f"Deep cascade detected ({cascade_depth} levels). "
                "Add circuit breakers to limit blast radius."
            )
        if len(affected_list) > 3:
            recommendations.append(
                f"{len(affected_list)} services affected. "
                "Consider adding redundancy to the breached service."
            )
        if breached_sla and breached_sla.tier in (SLATier.PLATINUM, SLATier.GOLD):
            recommendations.append(
                f"High-tier SLA ({breached_sla.tier.value}) breached. "
                "Immediate incident response required."
            )
        if not recommendations:
            recommendations.append("Monitor downstream services for degradation.")

        return SLABreachImpact(
            breached_service=breached_service,
            affected_services=affected_list,
            cascade_depth=cascade_depth,
            total_sla_degradation=round(total_degradation, 6),
            estimated_penalty=round(estimated_penalty, 2),
            recovery_recommendations=recommendations,
        )

    def recommend_sla_targets(
        self,
        graph: InfraGraph,
    ) -> list[ServiceSLA]:
        """Recommend SLA targets for all services in the graph.

        Heuristic:
        - Leaf services (no dependents) get Silver tier.
        - Services with 1-3 dependents get Gold tier.
        - Services with >3 dependents get Platinum tier.
        - Services with no dependencies (entry points) get Silver tier
          unless they also have many dependents.
        """
        recommendations: list[ServiceSLA] = []
        for cid, comp in graph.components.items():
            dependents = graph.get_dependents(cid)
            n_deps = len(dependents)

            if n_deps > 3:
                tier = SLATier.PLATINUM
            elif n_deps >= 1:
                tier = SLATier.GOLD
            else:
                tier = SLATier.SILVER

            target = _TIER_DEFAULTS[tier]
            penalty = _TIER_PENALTY_DEFAULTS[tier]

            recommendations.append(
                ServiceSLA(
                    service_id=cid,
                    sla_type=SLAType.AVAILABILITY,
                    target=target,
                    tier=tier,
                    penalty_per_violation_percent=penalty,
                    measurement_window_days=30,
                )
            )
        return recommendations

    def calculate_financial_risk(
        self,
        graph: InfraGraph,
        slas: dict[str, ServiceSLA],
    ) -> FinancialRiskReport:
        """Calculate comprehensive financial risk from SLA definitions."""
        if not slas:
            return FinancialRiskReport()

        service_risks: dict[str, float] = {}
        risk_by_tier: dict[str, float] = {}
        total_risk = 0.0

        for sid, sla in slas.items():
            # Annual risk = penalty * expected violation percentage.
            # Expected violation = (100 - target) as a rough annual probability.
            expected_violation_pct = 100.0 - sla.target
            annual_risk = sla.penalty_per_violation_percent * expected_violation_pct * 12 / max(sla.measurement_window_days, 1) * 30
            service_risks[sid] = round(annual_risk, 2)
            total_risk += annual_risk

            tier_key = sla.tier.value
            risk_by_tier[tier_key] = risk_by_tier.get(tier_key, 0.0) + annual_risk

        # Round tier risks.
        risk_by_tier = {k: round(v, 2) for k, v in risk_by_tier.items()}

        highest_risk_service = max(service_risks, key=service_risks.get) if service_risks else ""  # type: ignore[arg-type]

        # Mitigation savings: if all services were upgraded to next tier.
        mitigation_savings = total_risk * 0.3  # Conservative 30% reduction estimate.

        recommendations: list[str] = []
        for sid, risk in sorted(service_risks.items(), key=lambda x: x[1], reverse=True)[:3]:
            sla = slas[sid]
            recommendations.append(
                f"Service '{sid}' (tier={sla.tier.value}) has annual risk ${risk:,.2f}. "
                f"Consider upgrading SLA target from {sla.target}%."
            )

        if total_risk > 100_000:
            recommendations.append(
                "Total annual risk exceeds $100,000. Review SLA strategy urgently."
            )

        return FinancialRiskReport(
            total_annual_risk=round(total_risk, 2),
            service_risks=service_risks,
            highest_risk_service=highest_risk_service,
            risk_by_tier=risk_by_tier,
            mitigation_savings=round(mitigation_savings, 2),
            recommendations=recommendations,
        )

    def detect_sla_conflicts(
        self,
        slas: dict[str, ServiceSLA],
    ) -> list[SLAConflict]:
        """Detect conflicts and inconsistencies among SLA definitions.

        Checks for:
        - Tier/target mismatch (e.g. platinum tier but low target).
        - Zero penalty on paid tiers.
        - Duplicate SLA types on same service.
        - Unrealistically high targets (> 99.999%).
        - Measurement window inconsistencies.
        """
        conflicts: list[SLAConflict] = []

        # Track SLA types per service for duplicate detection.
        type_map: dict[str, list[SLAType]] = {}

        for sid, sla in slas.items():
            # Tier/target mismatch.
            expected_min = _TIER_DEFAULTS.get(sla.tier, 95.0)
            if sla.target < expected_min - 1.0:
                conflicts.append(
                    SLAConflict(
                        service_id=sid,
                        conflict_type="tier_target_mismatch",
                        description=(
                            f"Service '{sid}' has tier '{sla.tier.value}' "
                            f"but target {sla.target}% is below expected "
                            f"minimum {expected_min}%."
                        ),
                        severity="error",
                        resolution=f"Raise target to at least {expected_min}% or downgrade tier.",
                    )
                )

            # Zero penalty on non-best-effort tier.
            if sla.penalty_per_violation_percent == 0.0 and sla.tier != SLATier.BEST_EFFORT:
                conflicts.append(
                    SLAConflict(
                        service_id=sid,
                        conflict_type="zero_penalty",
                        description=(
                            f"Service '{sid}' has tier '{sla.tier.value}' "
                            f"but zero penalty — SLA is unenforceable."
                        ),
                        severity="warning",
                        resolution="Set a penalty or move to best_effort tier.",
                    )
                )

            # Unrealistically high target.
            if sla.target > 99.999:
                conflicts.append(
                    SLAConflict(
                        service_id=sid,
                        conflict_type="unrealistic_target",
                        description=(
                            f"Service '{sid}' target {sla.target}% exceeds five nines. "
                            f"This is extremely difficult to achieve."
                        ),
                        severity="warning",
                        resolution="Consider whether such a high target is realistic.",
                    )
                )

            # Very short measurement window.
            if sla.measurement_window_days < 7:
                conflicts.append(
                    SLAConflict(
                        service_id=sid,
                        conflict_type="short_window",
                        description=(
                            f"Service '{sid}' measurement window is only "
                            f"{sla.measurement_window_days} days. "
                            f"This may cause noisy SLA reporting."
                        ),
                        severity="info",
                        resolution="Consider a 30-day measurement window.",
                    )
                )

            # Track for duplicate detection.
            type_map.setdefault(sid, []).append(sla.sla_type)

        # Duplicate SLA types.
        for sid, types in type_map.items():
            seen: set[SLAType] = set()
            for t in types:
                if t in seen:
                    conflicts.append(
                        SLAConflict(
                            service_id=sid,
                            conflict_type="duplicate_sla_type",
                            description=(
                                f"Service '{sid}' has duplicate SLA type '{t.value}'."
                            ),
                            severity="error",
                            resolution="Remove or consolidate duplicate SLA definitions.",
                        )
                    )
                seen.add(t)

        # Cross-service window inconsistency.
        windows = {sla.measurement_window_days for sla in slas.values()}
        if len(windows) > 1:
            conflicts.append(
                SLAConflict(
                    service_id="*",
                    conflict_type="inconsistent_windows",
                    description=(
                        f"Mixed measurement windows found: {sorted(windows)}. "
                        f"This makes cross-service SLA comparison difficult."
                    ),
                    severity="warning",
                    resolution="Standardise measurement windows across services.",
                )
            )

        return conflicts

    def project_sla_compliance(
        self,
        graph: InfraGraph,
        slas: dict[str, ServiceSLA],
        months: int = 12,
    ) -> ComplianceProjection:
        """Project SLA compliance over *months*.

        Uses a simple stochastic model: each service has a monthly
        probability of violation proportional to ``(100 - target) / 100``.
        The cascade multiplier increases the probability for services
        with many dependencies.
        """
        if not slas or months <= 0:
            return ComplianceProjection(months=max(months, 0))

        monthly_projections: list[dict[str, float]] = []
        total_violations = 0
        total_penalty = 0.0

        for month in range(1, months + 1):
            month_violations = 0
            month_penalty = 0.0

            for sid, sla in slas.items():
                # Base violation probability.
                base_prob = (100.0 - sla.target) / 100.0

                # Cascade multiplier: more dependencies → higher risk.
                deps = []
                if sid in graph.components:
                    deps = graph.get_dependencies(sid)
                cascade_mult = 1.0 + len(deps) * 0.1

                effective_prob = min(base_prob * cascade_mult, 1.0)

                # Deterministic expected violations.
                expected = effective_prob
                month_violations += int(expected > 0.5)
                month_penalty += expected * sla.penalty_per_violation_percent

            total_violations += month_violations
            total_penalty += month_penalty

            monthly_projections.append({
                "month": float(month),
                "expected_violations": float(month_violations),
                "expected_penalty": round(month_penalty, 2),
            })

        # Compliance rate.
        total_possible = len(slas) * months
        compliance_rate = (
            (total_possible - total_violations) / total_possible * 100.0
            if total_possible > 0
            else 100.0
        )

        # Trend analysis from first half vs second half.
        if months >= 4:
            half = months // 2
            first_half = sum(p["expected_penalty"] for p in monthly_projections[:half])
            second_half = sum(p["expected_penalty"] for p in monthly_projections[half:])
            if second_half > first_half * 1.2:
                risk_trend = "worsening"
            elif second_half < first_half * 0.8:
                risk_trend = "improving"
            else:
                risk_trend = "stable"
        else:
            risk_trend = "stable"

        recommendations: list[str] = []
        if compliance_rate < 99.0:
            recommendations.append(
                f"Projected compliance rate {compliance_rate:.1f}% is below 99%. "
                "Consider raising SLA targets or adding redundancy."
            )
        if total_penalty > 50_000:
            recommendations.append(
                f"Projected annual penalties ${total_penalty:,.2f} are significant. "
                "Review SLA contracts and mitigation strategies."
            )
        if risk_trend == "worsening":
            recommendations.append(
                "Risk trend is worsening over time. Investigate root causes."
            )
        if not recommendations:
            recommendations.append("SLA compliance projection looks healthy.")

        return ComplianceProjection(
            months=months,
            projected_compliance_rate=round(compliance_rate, 4),
            projected_violations=total_violations,
            projected_penalty_total=round(total_penalty, 2),
            monthly_projections=monthly_projections,
            risk_trend=risk_trend,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dominant_sla_type(slas: dict[str, ServiceSLA]) -> SLAType:
        """Return the most common SLA type, defaulting to AVAILABILITY."""
        if not slas:
            return SLAType.AVAILABILITY
        counts: dict[SLAType, int] = {}
        for s in slas.values():
            counts[s.sla_type] = counts.get(s.sla_type, 0) + 1
        return max(counts, key=counts.get)  # type: ignore[arg-type]

    @staticmethod
    def _composite_availability(sla_values: dict[str, float]) -> float:
        """Multiply availability fractions together."""
        composite = 1.0
        for v in sla_values.values():
            composite *= v / 100.0
        return composite * 100.0

    @staticmethod
    def _max_chain_depth(graph: InfraGraph) -> int:
        """Longest dependency chain in the graph."""
        if not graph.components:
            return 0
        try:
            return nx.dag_longest_path_length(graph._graph) + 1
        except Exception:
            # Graph may have cycles.
            return len(graph.components)

    @staticmethod
    def _find_bottlenecks(
        graph: InfraGraph,
        slas: dict[str, ServiceSLA],
    ) -> list[str]:
        """Services whose SLA target is significantly below peers.

        A service is a bottleneck if its target is more than 0.5%
        below the average of all SLA targets, or if it has dependents
        but a lower SLA than any of them.
        """
        if not slas:
            return []
        avg_target = sum(s.target for s in slas.values()) / len(slas)
        bottlenecks: list[str] = []
        for sid, sla in slas.items():
            if sla.target < avg_target - 0.5:
                bottlenecks.append(sid)
            elif sid in graph.components:
                dependents = graph.get_dependents(sid)
                for dep in dependents:
                    dep_sla = slas.get(dep.id)
                    if dep_sla and dep_sla.target > sla.target:
                        if sid not in bottlenecks:
                            bottlenecks.append(sid)
                        break
        return sorted(bottlenecks)

    @staticmethod
    def _estimate_financial_risk_simple(slas: dict[str, ServiceSLA]) -> float:
        """Quick annual financial risk estimate from penalties."""
        total = 0.0
        for sla in slas.values():
            violation_pct = 100.0 - sla.target
            annual = sla.penalty_per_violation_percent * violation_pct * (365.0 / max(sla.measurement_window_days, 1))
            total += annual
        return total

    @staticmethod
    def _cascade_depth_from(graph: InfraGraph, component_id: str) -> int:
        """BFS depth from *component_id* through dependents."""
        if component_id not in graph.components:
            return 0
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

    @staticmethod
    def _generate_recommendations(
        graph: InfraGraph,
        slas: dict[str, ServiceSLA],
        composite: float,
        bottlenecks: list[str],
        chain_depth: int,
    ) -> list[str]:
        recs: list[str] = []

        if composite < 99.0:
            recs.append(
                f"Composite SLA {composite:.4f}% is below 99%. "
                "Improve weakest services or add redundancy."
            )

        if bottlenecks:
            recs.append(
                f"Bottleneck services detected: {', '.join(bottlenecks)}. "
                "These limit overall system SLA."
            )

        if chain_depth > 5:
            recs.append(
                f"Dependency chain depth is {chain_depth}. "
                "Deep chains amplify SLA degradation. Consider flattening the architecture."
            )

        # Check for services without SLAs.
        for cid in graph.components:
            if cid not in slas:
                recs.append(
                    f"Service '{cid}' has no SLA defined. "
                    "Define an SLA to ensure end-to-end coverage."
                )
                break  # Only report once.

        if not recs:
            recs.append("SLA configuration looks healthy.")

        return recs
