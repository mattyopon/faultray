# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""SLA contract validator — verify infrastructure meets SLA commitments.

Cross-references architecture patterns (redundancy, failover, monitoring)
against contractual SLA requirements to identify gaps before they cause
SLA breaches.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Default component availability assumptions (fraction, e.g. 0.999 = 99.9%)
# ---------------------------------------------------------------------------

_DEFAULT_AVAILABILITY: dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 0.9999,
    ComponentType.WEB_SERVER: 0.999,
    ComponentType.APP_SERVER: 0.999,
    ComponentType.DATABASE: 0.9995,
    ComponentType.CACHE: 0.999,
    ComponentType.QUEUE: 0.9999,
    ComponentType.DNS: 0.99999,
    ComponentType.STORAGE: 0.99999,
    ComponentType.EXTERNAL_API: 0.999,
    ComponentType.CUSTOM: 0.999,
    ComponentType.AI_AGENT: 0.999,
    ComponentType.LLM_ENDPOINT: 0.999,
    ComponentType.TOOL_SERVICE: 0.999,
    ComponentType.AGENT_ORCHESTRATOR: 0.999,
    ComponentType.AUTOMATION: 0.999,
    ComponentType.SERVERLESS: 0.999,
    ComponentType.SCHEDULED_JOB: 0.999,
}

# Minutes per month (30.44 days)
_MINUTES_PER_MONTH: float = 30.44 * 24 * 60  # ~43833.6


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PenaltyTier:
    """A single penalty tier in an SLA contract.

    Parameters
    ----------
    threshold:
        Availability threshold as a percentage (e.g. 99.9).
        If actual availability falls below this, the penalty applies.
    penalty_percent:
        Financial penalty as a percentage of monthly contract value
        (e.g. 10.0 means 10% credit).
    description:
        Human-readable description of this tier.
    """

    threshold: float
    penalty_percent: float
    description: str = ""


@dataclass
class SLAContract:
    """A contractual SLA definition for a service.

    Parameters
    ----------
    service_name:
        Name of the service covered by this contract.
    availability_target:
        Required availability as a percentage (e.g. 99.99).
    max_response_time_ms:
        Maximum acceptable response time in milliseconds.
    max_downtime_minutes_per_month:
        Maximum allowed downtime minutes per month.
    rpo_minutes:
        Recovery Point Objective in minutes — maximum acceptable data loss.
    rto_minutes:
        Recovery Time Objective in minutes — maximum time to restore service.
    penalty_tiers:
        Ordered list of penalty tiers (highest threshold first).
    monthly_contract_value:
        Monthly revenue at risk under this contract (USD).
    """

    service_name: str
    availability_target: float  # e.g. 99.99
    max_response_time_ms: float = 500.0
    max_downtime_minutes_per_month: float = 4.32  # ~99.99%
    rpo_minutes: float = 15.0
    rto_minutes: float = 30.0
    penalty_tiers: list[PenaltyTier] = field(default_factory=list)
    monthly_contract_value: float = 0.0


@dataclass
class SLAViolationRisk:
    """A detected risk of SLA violation.

    Parameters
    ----------
    contract:
        The SLA contract being assessed.
    violation_type:
        Category: "availability", "rto", "rpo", or "response_time".
    current_capability:
        Current estimated capability for this dimension.
    required_level:
        Required level per the SLA contract.
    gap:
        Numeric gap between required and current (positive = shortfall).
    risk_level:
        Severity: "critical", "high", "medium", or "low".
    remediation:
        Actionable recommendation to close the gap.
    estimated_penalty_exposure:
        Monthly financial exposure (USD) if the SLA is breached.
    """

    contract: SLAContract
    violation_type: str
    current_capability: float
    required_level: float
    gap: float
    risk_level: str
    remediation: str
    estimated_penalty_exposure: float = 0.0


@dataclass
class SLAValidationReport:
    """Aggregated validation report across one or more SLA contracts.

    Parameters
    ----------
    contracts:
        All contracts that were validated.
    violations:
        All detected violation risks.
    overall_compliance:
        True only if zero violations were found.
    compliance_score:
        A 0-100 score reflecting overall compliance health.
    total_penalty_exposure:
        Sum of penalty exposures across all violations (USD/month).
    recommendations:
        Deduplicated list of actionable improvement recommendations.
    """

    contracts: list[SLAContract]
    violations: list[SLAViolationRisk]
    overall_compliance: bool
    compliance_score: float
    total_penalty_exposure: float
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Validator engine
# ---------------------------------------------------------------------------


class SLAValidator:
    """Validate infrastructure against SLA contract commitments.

    The validator cross-references the topology in an :class:`InfraGraph`
    with a set of :class:`SLAContract` definitions and produces a report
    identifying compliance gaps, financial risk, and remediations.

    Parameters
    ----------
    graph:
        The infrastructure graph to analyse.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # -- public entry point ------------------------------------------------

    def validate(self, contracts: list[SLAContract]) -> SLAValidationReport:
        """Validate all contracts and return a consolidated report.

        Parameters
        ----------
        contracts:
            List of SLA contracts to validate against the infrastructure.

        Returns
        -------
        SLAValidationReport
        """
        if not contracts:
            return SLAValidationReport(
                contracts=[],
                violations=[],
                overall_compliance=True,
                compliance_score=100.0,
                total_penalty_exposure=0.0,
                recommendations=[],
            )

        all_violations: list[SLAViolationRisk] = []
        for contract in contracts:
            all_violations.extend(self._check_availability(contract))
            all_violations.extend(self._check_rto(contract))
            all_violations.extend(self._check_rpo(contract))
            all_violations.extend(self._check_response_time(contract))

        overall_compliance = len(all_violations) == 0
        compliance_score = self._compute_compliance_score(contracts, all_violations)
        total_penalty = sum(v.estimated_penalty_exposure for v in all_violations)

        # Build deduplicated recommendations
        seen: set[str] = set()
        recommendations: list[str] = []
        for v in all_violations:
            if v.remediation and v.remediation not in seen:
                seen.add(v.remediation)
                recommendations.append(v.remediation)

        return SLAValidationReport(
            contracts=list(contracts),
            violations=all_violations,
            overall_compliance=overall_compliance,
            compliance_score=compliance_score,
            total_penalty_exposure=total_penalty,
            recommendations=recommendations,
        )

    # -- per-dimension checks ----------------------------------------------

    def _check_availability(self, contract: SLAContract) -> list[SLAViolationRisk]:
        """Check whether infrastructure can meet the availability target."""
        estimated = self._estimate_availability()
        required = contract.availability_target

        if estimated >= required:
            return []

        gap = required - estimated
        risk_level = self._classify_risk(gap, thresholds=(0.1, 0.5, 1.0))
        penalty = self._calculate_penalty(contract, estimated)

        remediation = self._availability_remediation(estimated, required)

        return [SLAViolationRisk(
            contract=contract,
            violation_type="availability",
            current_capability=estimated,
            required_level=required,
            gap=gap,
            risk_level=risk_level,
            remediation=remediation,
            estimated_penalty_exposure=penalty,
        )]

    def _check_rto(self, contract: SLAContract) -> list[SLAViolationRisk]:
        """Check whether infrastructure can meet the RTO requirement."""
        estimated_rto = self._estimate_rto()
        required_rto = contract.rto_minutes

        if estimated_rto <= required_rto:
            return []

        gap = estimated_rto - required_rto
        risk_level = self._classify_risk(gap, thresholds=(5.0, 15.0, 30.0))
        penalty = self._calculate_penalty(contract, self._estimate_availability())

        remediation = self._rto_remediation(estimated_rto, required_rto)

        return [SLAViolationRisk(
            contract=contract,
            violation_type="rto",
            current_capability=estimated_rto,
            required_level=required_rto,
            gap=gap,
            risk_level=risk_level,
            remediation=remediation,
            estimated_penalty_exposure=penalty,
        )]

    def _check_rpo(self, contract: SLAContract) -> list[SLAViolationRisk]:
        """Check whether infrastructure can meet the RPO requirement."""
        estimated_rpo = self._estimate_rpo()
        required_rpo = contract.rpo_minutes

        if estimated_rpo <= required_rpo:
            return []

        gap = estimated_rpo - required_rpo
        risk_level = self._classify_risk(gap, thresholds=(5.0, 30.0, 60.0))
        penalty = self._calculate_penalty(contract, self._estimate_availability())

        remediation = self._rpo_remediation(estimated_rpo, required_rpo)

        return [SLAViolationRisk(
            contract=contract,
            violation_type="rpo",
            current_capability=estimated_rpo,
            required_level=required_rpo,
            gap=gap,
            risk_level=risk_level,
            remediation=remediation,
            estimated_penalty_exposure=penalty,
        )]

    def _check_response_time(self, contract: SLAContract) -> list[SLAViolationRisk]:
        """Check whether infrastructure can meet the response time target."""
        estimated_rt = self._estimate_response_time()
        required_rt = contract.max_response_time_ms

        if estimated_rt <= required_rt:
            return []

        gap = estimated_rt - required_rt
        risk_level = self._classify_risk(gap, thresholds=(50.0, 200.0, 500.0))
        penalty = self._calculate_penalty(contract, self._estimate_availability())

        remediation = (
            f"Estimated response time ({estimated_rt:.0f}ms) exceeds target "
            f"({required_rt:.0f}ms). Consider adding caching, optimising queries, "
            f"or deploying components in closer proximity."
        )

        return [SLAViolationRisk(
            contract=contract,
            violation_type="response_time",
            current_capability=estimated_rt,
            required_level=required_rt,
            gap=gap,
            risk_level=risk_level,
            remediation=remediation,
            estimated_penalty_exposure=penalty,
        )]

    # -- estimation helpers ------------------------------------------------

    def _estimate_availability(self) -> float:
        """Estimate system-level availability as a percentage (e.g. 99.95).

        Strategy:
        * Each component has a base availability from its type.
        * Replicas >= 2 boost availability via parallel redundancy:
          ``A_eff = 1 - (1 - A_base)^n``.
        * Failover adds a further boost by halving the remaining
          unavailability window.
        * System availability is the product of all *critical-path*
          component availabilities (series model).  A component is on
          the critical path if it has at least one ``requires`` dependent
          or if it is a standalone/leaf node.
        """
        if not self._graph.components:
            return 0.0

        system_avail = 1.0

        for comp_id, comp in self._graph.components.items():
            base = _DEFAULT_AVAILABILITY.get(comp.type, 0.999)

            # MTBF / MTTR override if provided
            mtbf = comp.operational_profile.mtbf_hours
            mttr_h = comp.operational_profile.mttr_minutes / 60.0
            if mtbf > 0 and mttr_h > 0:
                base = mtbf / (mtbf + mttr_h)

            # Parallel redundancy
            replicas = max(comp.replicas, 1)
            effective = 1.0 - (1.0 - base) ** replicas

            # Failover bonus
            if comp.failover.enabled and replicas > 1:
                # Failover cuts remaining downtime roughly in half
                effective = 1.0 - (1.0 - effective) * 0.5

            # Only multiply into system if on the critical path
            dependents = self._graph.get_dependents(comp_id)
            has_requires = any(
                (edge := self._graph.get_dependency_edge(d.id, comp_id))
                and edge.dependency_type == "requires"
                for d in dependents
            )
            if has_requires or not dependents:
                system_avail *= effective

        return max(0.0, min(100.0, system_avail * 100.0))

    def _estimate_rto(self) -> float:
        """Estimate Recovery Time Objective in minutes.

        Heuristics:
        * Base RTO is worst-case MTTR across all components.
        * Failover reduces component RTO to promotion_time + detection_time.
        * Autoscaling reduces RTO via faster replacement.
        * Monitoring (health checks at short intervals) speeds detection.
        """
        if not self._graph.components:
            return float("inf")

        worst_rto = 0.0

        for comp in self._graph.components.values():
            comp_rto = comp.operational_profile.mttr_minutes
            if comp_rto <= 0:
                comp_rto = 30.0  # default 30 minutes

            if comp.failover.enabled:
                detection_s = (
                    comp.failover.health_check_interval_seconds
                    * comp.failover.failover_threshold
                )
                promotion_s = comp.failover.promotion_time_seconds
                comp_rto = (detection_s + promotion_s) / 60.0

            if comp.autoscaling.enabled:
                scale_up_s = comp.autoscaling.scale_up_delay_seconds
                comp_rto = min(comp_rto, scale_up_s / 60.0)

            worst_rto = max(worst_rto, comp_rto)

        return worst_rto

    def _estimate_rpo(self) -> float:
        """Estimate Recovery Point Objective in minutes.

        Heuristics:
        * Components without backups have RPO = infinity (capped at 1440 min / 24h).
        * Components with backups: RPO = backup_frequency_hours * 60.
        * Replicas > 1 imply synchronous replication (RPO near 0 for that component).
        """
        if not self._graph.components:
            return float("inf")

        worst_rpo = 0.0

        for comp in self._graph.components.values():
            # Only stateful components affect RPO
            if comp.type not in (
                ComponentType.DATABASE,
                ComponentType.STORAGE,
                ComponentType.QUEUE,
            ):
                continue

            if comp.replicas > 1:
                # Synchronous replication — near-zero RPO
                comp_rpo = 0.0
            elif comp.security.backup_enabled:
                comp_rpo = comp.security.backup_frequency_hours * 60.0
            else:
                comp_rpo = 1440.0  # 24 hours — effectively no backup

            worst_rpo = max(worst_rpo, comp_rpo)

        return worst_rpo

    def _estimate_response_time(self) -> float:
        """Estimate total response time in milliseconds.

        Sums up latency across all dependency edges on the longest
        critical path, plus base processing time per component.
        """
        total_ms = 0.0
        for edge in self._graph.all_dependency_edges():
            total_ms += edge.latency_ms

        # Add base processing overhead per component
        total_ms += len(self._graph.components) * 5.0  # 5ms per hop

        return total_ms

    # -- penalty calculation -----------------------------------------------

    def _calculate_penalty(self, contract: SLAContract, actual_availability: float) -> float:
        """Walk through penalty tiers to find the applicable penalty rate.

        Parameters
        ----------
        contract:
            The SLA contract with penalty tiers.
        actual_availability:
            The estimated availability as a percentage (e.g. 99.5).

        Returns
        -------
        float
            Monthly penalty exposure in USD.
        """
        if not contract.penalty_tiers or contract.monthly_contract_value <= 0:
            return 0.0

        # Sort tiers by threshold descending — first match wins
        sorted_tiers = sorted(contract.penalty_tiers, key=lambda t: t.threshold, reverse=True)

        applicable_percent = 0.0
        for tier in sorted_tiers:
            if actual_availability < tier.threshold:
                applicable_percent = max(applicable_percent, tier.penalty_percent)

        return contract.monthly_contract_value * applicable_percent / 100.0

    # -- scoring -----------------------------------------------------------

    def _compute_compliance_score(
        self,
        contracts: list[SLAContract],
        violations: list[SLAViolationRisk],
    ) -> float:
        """Compute a 0-100 compliance score.

        100 = fully compliant, 0 = critical violations on every contract.
        Each violation deducts points based on severity.
        """
        if not contracts:
            return 100.0

        deductions = {
            "critical": 25.0,
            "high": 15.0,
            "medium": 8.0,
            "low": 3.0,
        }

        total_deduction = 0.0
        for v in violations:
            total_deduction += deductions.get(v.risk_level, 5.0)

        return max(0.0, min(100.0, 100.0 - total_deduction))

    # -- risk classification -----------------------------------------------

    @staticmethod
    def _classify_risk(gap: float, thresholds: tuple[float, float, float]) -> str:
        """Classify risk level based on gap magnitude.

        Parameters
        ----------
        gap:
            Numeric gap (positive = shortfall).
        thresholds:
            Tuple of (low_max, medium_max, high_max).
            gap <= low_max → "low"
            gap <= medium_max → "medium"
            gap <= high_max → "high"
            gap > high_max → "critical"
        """
        low_max, med_max, high_max = thresholds
        if gap <= low_max:
            return "low"
        if gap <= med_max:
            return "medium"
        if gap <= high_max:
            return "high"
        return "critical"

    # -- remediation text generators ---------------------------------------

    @staticmethod
    def _availability_remediation(current: float, required: float) -> str:
        gap = required - current
        parts = [
            f"Availability gap of {gap:.4f}% "
            f"(current: {current:.4f}%, required: {required:.4f}%)."
        ]
        if gap > 0.5:
            parts.append(
                "Add redundant replicas and enable failover for all critical components."
            )
        elif gap > 0.1:
            parts.append(
                "Enable failover and increase replica count on bottleneck components."
            )
        else:
            parts.append(
                "Fine-tune health-check intervals and reduce failover promotion time."
            )
        return " ".join(parts)

    @staticmethod
    def _rto_remediation(current: float, required: float) -> str:
        return (
            f"Estimated RTO ({current:.1f} min) exceeds target ({required:.1f} min). "
            f"Enable automated failover, reduce health-check intervals, "
            f"and implement auto-scaling to meet the target."
        )

    @staticmethod
    def _rpo_remediation(current: float, required: float) -> str:
        return (
            f"Estimated RPO ({current:.1f} min) exceeds target ({required:.1f} min). "
            f"Enable backups with shorter intervals, add database replicas, "
            f"or implement continuous replication."
        )
