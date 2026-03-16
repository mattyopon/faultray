"""Reliability Contract Engine — define and verify reliability contracts.

A reliability contract is a formal agreement between a service provider
and its consumers about behavior under failure conditions.  For example:
"Auth service guarantees 99.95% availability, <200ms p99 latency, and
graceful degradation to cached tokens within 30s of primary failure."

This engine registers contracts, verifies them against the infrastructure
graph, traces dependency chains, and generates comprehensive reports.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ContractType(str, Enum):
    """Types of reliability contracts."""
    AVAILABILITY = "availability"
    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    DEGRADATION_BEHAVIOR = "degradation_behavior"
    RECOVERY_TIME = "recovery_time"


class ContractStatus(str, Enum):
    """Verification status of a reliability contract."""
    VERIFIED = "verified"
    VIOLATED = "violated"
    UNTESTED = "untested"
    CONDITIONALLY_MET = "conditionally_met"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ReliabilityContract(BaseModel):
    """A formal reliability contract between a provider and its consumers."""
    contract_id: str
    provider_component: str
    consumer_components: list[str] = Field(default_factory=list)
    contract_type: ContractType
    target_value: float
    unit: str = ""
    conditions: str = ""
    priority: int = Field(default=3, ge=1, le=5)


class ContractVerification(BaseModel):
    """Result of verifying a single reliability contract."""
    contract: ReliabilityContract
    status: ContractStatus
    actual_value: float
    margin: float
    failure_scenarios_tested: int = 0
    worst_case_value: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class ContractDependencyChain(BaseModel):
    """A dependency chain with contract-level analysis."""
    chain: list[str] = Field(default_factory=list)
    weakest_contract: ReliabilityContract | None = None
    chain_availability: float = 100.0
    bottleneck_component: str = ""


class ContractReport(BaseModel):
    """Aggregated report across all reliability contracts."""
    total_contracts: int = 0
    verified: int = 0
    violated: int = 0
    untested: int = 0
    verifications: list[ContractVerification] = Field(default_factory=list)
    dependency_chains: list[ContractDependencyChain] = Field(default_factory=list)
    overall_contract_health: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Default availability per component type (fraction)
# ---------------------------------------------------------------------------

_BASE_AVAILABILITY: dict[ComponentType, float] = {
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
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ReliabilityContractEngine:
    """Register, verify, and report on reliability contracts."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._contracts: list[ReliabilityContract] = []

    # -- registration ------------------------------------------------------

    def add_contract(self, contract: ReliabilityContract) -> None:
        """Register a reliability contract."""
        self._contracts.append(contract)

    # -- single contract verification -------------------------------------

    def verify_contract(self, contract: ReliabilityContract) -> ContractVerification:
        """Verify a single contract against the infrastructure graph."""
        comp = self._graph.get_component(contract.provider_component)
        if comp is None:
            return ContractVerification(
                contract=contract,
                status=ContractStatus.UNTESTED,
                actual_value=0.0,
                margin=0.0,
                failure_scenarios_tested=0,
                worst_case_value=0.0,
                evidence=["Provider component not found in graph"],
            )

        verifier = {
            ContractType.AVAILABILITY: self._verify_availability,
            ContractType.LATENCY: self._verify_latency,
            ContractType.ERROR_RATE: self._verify_error_rate,
            ContractType.THROUGHPUT: self._verify_throughput,
            ContractType.DEGRADATION_BEHAVIOR: self._verify_degradation,
            ContractType.RECOVERY_TIME: self._verify_recovery_time,
        }
        return verifier[contract.contract_type](contract, comp)

    # -- bulk verification ------------------------------------------------

    def verify_all(self) -> list[ContractVerification]:
        """Verify every registered contract."""
        return [self.verify_contract(c) for c in self._contracts]

    # -- dependency chains ------------------------------------------------

    def trace_dependency_chains(self) -> list[ContractDependencyChain]:
        """Find contract dependency chains through the graph."""
        chains: list[ContractDependencyChain] = []
        paths = self._graph.get_critical_paths()
        for path in paths:
            if len(path) < 2:
                continue
            avail = 100.0
            worst_avail = 100.0
            bottleneck = path[0]
            weakest: ReliabilityContract | None = None
            for cid in path:
                comp = self._graph.get_component(cid)
                if comp is None:
                    continue
                comp_avail = self._component_availability(comp) * 100.0
                avail *= comp_avail / 100.0
                if comp_avail < worst_avail:
                    worst_avail = comp_avail
                    bottleneck = cid
                # Find contract with lowest target for this component
                for c in self._contracts:
                    if c.provider_component == cid:
                        if weakest is None or c.target_value < weakest.target_value:
                            weakest = c
            chains.append(ContractDependencyChain(
                chain=path,
                weakest_contract=weakest,
                chain_availability=round(avail, 6),
                bottleneck_component=bottleneck,
            ))
        return chains

    # -- gap analysis -----------------------------------------------------

    def find_contract_gaps(self) -> list[str]:
        """Return component IDs that have no contracts."""
        covered = {c.provider_component for c in self._contracts}
        return [
            cid for cid in self._graph.components
            if cid not in covered
        ]

    # -- report -----------------------------------------------------------

    def generate_report(self) -> ContractReport:
        """Generate a comprehensive contract report."""
        verifications = self.verify_all()
        chains = self.trace_dependency_chains()
        gaps = self.find_contract_gaps()

        verified = sum(1 for v in verifications if v.status == ContractStatus.VERIFIED)
        violated = sum(1 for v in verifications if v.status == ContractStatus.VIOLATED)
        untested = sum(1 for v in verifications if v.status == ContractStatus.UNTESTED)
        conditionally = sum(
            1 for v in verifications if v.status == ContractStatus.CONDITIONALLY_MET
        )

        total = len(verifications)
        if total > 0:
            health = ((verified + conditionally * 0.5) / total) * 100.0
        else:
            health = 0.0

        recommendations: list[str] = []
        for v in verifications:
            if v.status == ContractStatus.VIOLATED:
                recommendations.append(
                    f"Contract '{v.contract.contract_id}' violated: "
                    f"actual={v.actual_value:.4f}, target={v.contract.target_value:.4f}"
                )
            elif v.status == ContractStatus.CONDITIONALLY_MET:
                recommendations.append(
                    f"Contract '{v.contract.contract_id}' conditionally met — "
                    f"margin={v.margin:.4f}; consider improving resilience"
                )
        if gaps:
            recommendations.append(
                f"{len(gaps)} component(s) lack reliability contracts: "
                + ", ".join(gaps)
            )
        for ch in chains:
            if ch.chain_availability < 99.0:
                recommendations.append(
                    f"Dependency chain {' -> '.join(ch.chain)} has low availability "
                    f"({ch.chain_availability:.4f}%); bottleneck: {ch.bottleneck_component}"
                )

        return ContractReport(
            total_contracts=total,
            verified=verified,
            violated=violated,
            untested=untested,
            verifications=verifications,
            dependency_chains=chains,
            overall_contract_health=round(health, 2),
            recommendations=recommendations,
        )

    # -- private: per-type verifiers --------------------------------------

    def _verify_availability(
        self, contract: ReliabilityContract, comp: Component,
    ) -> ContractVerification:
        avail = self._component_availability(comp) * 100.0
        target = contract.target_value
        margin = avail - target
        scenarios = 1 + int(comp.replicas > 1) + int(comp.failover.enabled)
        worst = avail * 0.95 if comp.replicas <= 1 else avail * 0.99

        if margin >= 1.0:
            status = ContractStatus.VERIFIED
        elif margin >= 0:
            status = ContractStatus.CONDITIONALLY_MET
        else:
            status = ContractStatus.VIOLATED

        evidence = [f"Replicas: {comp.replicas}"]
        if comp.failover.enabled:
            evidence.append("Failover enabled")
        if comp.autoscaling.enabled:
            evidence.append("Autoscaling enabled")

        return ContractVerification(
            contract=contract, status=status,
            actual_value=round(avail, 6), margin=round(margin, 6),
            failure_scenarios_tested=scenarios,
            worst_case_value=round(worst, 6), evidence=evidence,
        )

    def _verify_latency(
        self, contract: ReliabilityContract, comp: Component,
    ) -> ContractVerification:
        latency = self._estimate_component_latency(comp)
        target = contract.target_value
        margin = target - latency
        worst = latency * 1.5

        if margin >= target * 0.2:
            status = ContractStatus.VERIFIED
        elif margin >= 0:
            status = ContractStatus.CONDITIONALLY_MET
        else:
            status = ContractStatus.VIOLATED

        evidence = [f"Estimated latency: {latency:.1f}ms"]
        deps = self._graph.get_dependencies(comp.id)
        evidence.append(f"Dependency count: {len(deps)}")

        return ContractVerification(
            contract=contract, status=status,
            actual_value=round(latency, 4), margin=round(margin, 4),
            failure_scenarios_tested=1 + len(deps),
            worst_case_value=round(worst, 4), evidence=evidence,
        )

    def _verify_error_rate(
        self, contract: ReliabilityContract, comp: Component,
    ) -> ContractVerification:
        error_rate = self._estimate_error_rate(comp)
        target = contract.target_value
        margin = target - error_rate
        worst = error_rate * 2.0

        if margin >= target * 0.3:
            status = ContractStatus.VERIFIED
        elif margin >= 0:
            status = ContractStatus.CONDITIONALLY_MET
        else:
            status = ContractStatus.VIOLATED

        evidence: list[str] = []
        has_cb = self._has_circuit_breakers(comp)
        has_retry = self._has_retry_strategy(comp)
        if has_cb:
            evidence.append("Circuit breakers detected")
        if has_retry:
            evidence.append("Retry strategy detected")
        if not has_cb and not has_retry:
            evidence.append("No error mitigation detected")

        return ContractVerification(
            contract=contract, status=status,
            actual_value=round(error_rate, 6), margin=round(margin, 6),
            failure_scenarios_tested=2,
            worst_case_value=round(worst, 6), evidence=evidence,
        )

    def _verify_throughput(
        self, contract: ReliabilityContract, comp: Component,
    ) -> ContractVerification:
        throughput = self._estimate_throughput(comp)
        target = contract.target_value
        margin = throughput - target
        worst = throughput * 0.7

        if margin >= target * 0.2:
            status = ContractStatus.VERIFIED
        elif margin >= 0:
            status = ContractStatus.CONDITIONALLY_MET
        else:
            status = ContractStatus.VIOLATED

        evidence = [f"Max RPS: {comp.capacity.max_rps}"]
        if comp.autoscaling.enabled:
            evidence.append(
                f"Autoscaling: {comp.autoscaling.min_replicas}-"
                f"{comp.autoscaling.max_replicas} replicas"
            )

        return ContractVerification(
            contract=contract, status=status,
            actual_value=round(throughput, 2), margin=round(margin, 2),
            failure_scenarios_tested=1 + int(comp.autoscaling.enabled),
            worst_case_value=round(worst, 2), evidence=evidence,
        )

    def _verify_degradation(
        self, contract: ReliabilityContract, comp: Component,
    ) -> ContractVerification:
        has_fallback = self._has_fallback(comp)
        # target_value represents expected degradation time in seconds
        if has_fallback:
            actual = 1.0  # has fallback
            status = ContractStatus.VERIFIED
            evidence = ["Fallback mechanisms detected"]
        else:
            actual = 0.0
            status = ContractStatus.VIOLATED
            evidence = ["No fallback mechanisms detected"]

        margin = actual - contract.target_value
        worst = 0.0

        # Check if there are cache/queue fallbacks among dependencies
        deps = self._graph.get_dependencies(comp.id)
        for dep in deps:
            if dep.type in (ComponentType.CACHE, ComponentType.QUEUE):
                evidence.append(f"Fallback dependency: {dep.id} ({dep.type.value})")
                if not has_fallback:
                    status = ContractStatus.CONDITIONALLY_MET
                    actual = 0.5

        margin = actual - contract.target_value

        return ContractVerification(
            contract=contract, status=status,
            actual_value=actual, margin=round(margin, 4),
            failure_scenarios_tested=1 + len(deps),
            worst_case_value=worst, evidence=evidence,
        )

    def _verify_recovery_time(
        self, contract: ReliabilityContract, comp: Component,
    ) -> ContractVerification:
        recovery_s = self._estimate_recovery_time(comp)
        target = contract.target_value  # seconds
        margin = target - recovery_s
        worst = recovery_s * 1.5

        if margin >= target * 0.2:
            status = ContractStatus.VERIFIED
        elif margin >= 0:
            status = ContractStatus.CONDITIONALLY_MET
        else:
            status = ContractStatus.VIOLATED

        evidence: list[str] = []
        if comp.failover.enabled:
            evidence.append(
                f"Failover promotion: {comp.failover.promotion_time_seconds}s"
            )
        if comp.autoscaling.enabled:
            evidence.append(
                f"Scale-up delay: {comp.autoscaling.scale_up_delay_seconds}s"
            )
        if not comp.failover.enabled and not comp.autoscaling.enabled:
            evidence.append("No automated recovery mechanism")

        return ContractVerification(
            contract=contract, status=status,
            actual_value=round(recovery_s, 2), margin=round(margin, 2),
            failure_scenarios_tested=2,
            worst_case_value=round(worst, 2), evidence=evidence,
        )

    # -- private: estimation helpers --------------------------------------

    def _component_availability(self, comp: Component) -> float:
        """Estimate component availability as a fraction (0-1)."""
        base = _BASE_AVAILABILITY.get(comp.type, 0.999)
        replicas = max(comp.replicas, 1)
        effective = 1.0 - (1.0 - base) ** replicas
        if comp.failover.enabled and replicas > 1:
            effective = 1.0 - (1.0 - effective) * 0.5
        return effective

    def _estimate_component_latency(self, comp: Component) -> float:
        """Estimate latency in ms through a component and its deps."""
        base_ms = comp.network.rtt_ms + comp.network.dns_resolution_ms
        deps = self._graph.get_dependencies(comp.id)
        for dep in deps:
            edge = self._graph.get_dependency_edge(comp.id, dep.id)
            if edge:
                base_ms += edge.latency_ms
        return base_ms

    def _estimate_error_rate(self, comp: Component) -> float:
        """Estimate effective error rate as a fraction."""
        base_unavail = 1.0 - _BASE_AVAILABILITY.get(comp.type, 0.999)
        if self._has_circuit_breakers(comp):
            base_unavail *= 0.3
        if self._has_retry_strategy(comp):
            base_unavail *= 0.5
        if comp.replicas > 1:
            base_unavail *= 0.5
        return base_unavail

    def _estimate_throughput(self, comp: Component) -> float:
        """Estimate effective throughput in RPS."""
        base_rps = float(comp.capacity.max_rps * comp.replicas)
        if comp.autoscaling.enabled:
            base_rps *= comp.autoscaling.max_replicas / max(comp.replicas, 1)
        return base_rps

    def _estimate_recovery_time(self, comp: Component) -> float:
        """Estimate recovery time in seconds."""
        if comp.failover.enabled:
            detection = (
                comp.failover.health_check_interval_seconds
                * comp.failover.failover_threshold
            )
            return detection + comp.failover.promotion_time_seconds
        if comp.autoscaling.enabled:
            return float(comp.autoscaling.scale_up_delay_seconds)
        return comp.operational_profile.mttr_minutes * 60.0

    def _has_circuit_breakers(self, comp: Component) -> bool:
        """Check if any dependency edge from this component has a circuit breaker."""
        deps = self._graph.get_dependencies(comp.id)
        for dep in deps:
            edge = self._graph.get_dependency_edge(comp.id, dep.id)
            if edge and edge.circuit_breaker.enabled:
                return True
        return False

    def _has_retry_strategy(self, comp: Component) -> bool:
        """Check if any dependency edge from this component has retries."""
        deps = self._graph.get_dependencies(comp.id)
        for dep in deps:
            edge = self._graph.get_dependency_edge(comp.id, dep.id)
            if edge and edge.retry_strategy.enabled:
                return True
        return False

    def _has_fallback(self, comp: Component) -> bool:
        """Check if the component has fallback mechanisms."""
        if comp.failover.enabled:
            return True
        if comp.replicas > 1:
            return True
        deps = self._graph.get_dependencies(comp.id)
        for dep in deps:
            edge = self._graph.get_dependency_edge(comp.id, dep.id)
            if edge and edge.dependency_type == "optional":
                return True
        return False
