# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Blast Radius Containment Verifier.

Tests whether failure containment mechanisms (circuit breakers, bulkheads,
rate limiters, timeouts) actually work under various failure scenarios.
Simulates failures and verifies that they DON'T propagate beyond the
expected blast radius.  Critical for enterprise customers who need to
prove their failure isolation works.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ContainmentMechanism(str, Enum):
    """Types of failure containment mechanisms."""

    CIRCUIT_BREAKER = "circuit_breaker"
    BULKHEAD = "bulkhead"
    RATE_LIMITER = "rate_limiter"
    TIMEOUT = "timeout"
    RETRY_BUDGET = "retry_budget"
    LOAD_SHEDDING = "load_shedding"
    GRACEFUL_DEGRADATION = "graceful_degradation"
    FAILOVER = "failover"


class ContainmentStatus(str, Enum):
    """Result of a containment test."""

    CONTAINED = "contained"
    PARTIALLY_CONTAINED = "partially_contained"
    BREACHED = "breached"
    NOT_TESTED = "not_tested"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ContainmentRule(BaseModel):
    """Defines expected containment behaviour for a component."""

    mechanism: ContainmentMechanism
    component_id: str
    max_blast_radius: int = 0
    max_propagation_depth: int = 1
    timeout_seconds: float | None = None


class ContainmentTest(BaseModel):
    """Result of testing containment for a single failure scenario."""

    failure_component: str
    failure_type: str = "component_failure"
    expected_blast_radius: int = 0
    actual_blast_radius: int = 0
    expected_affected: list[str] = Field(default_factory=list)
    actual_affected: list[str] = Field(default_factory=list)
    status: ContainmentStatus = ContainmentStatus.NOT_TESTED
    containment_effectiveness: float = 0.0


class ContainmentGap(BaseModel):
    """Identifies a component that is missing containment mechanisms."""

    component_id: str
    missing_mechanisms: list[ContainmentMechanism] = Field(default_factory=list)
    risk_level: str = "low"
    recommendation: str = ""


class ContainmentReport(BaseModel):
    """Overall containment verification report."""

    tests_run: int = 0
    contained: int = 0
    breached: int = 0
    containment_score: float = 0.0
    tests: list[ContainmentTest] = Field(default_factory=list)
    gaps: list[ContainmentGap] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Main verifier
# ---------------------------------------------------------------------------


class ContainmentVerifier:
    """Verifies blast-radius containment across an infrastructure graph."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._rules: list[ContainmentRule] = []

    @property
    def rules(self) -> list[ContainmentRule]:
        return list(self._rules)

    def add_rule(self, rule: ContainmentRule) -> None:
        """Register a containment expectation."""
        self._rules.append(rule)

    # ------------------------------------------------------------------
    # Verification helpers
    # ------------------------------------------------------------------

    def _get_rules_for(self, component_id: str) -> list[ContainmentRule]:
        """Return all rules that apply to *component_id*."""
        return [r for r in self._rules if r.component_id == component_id]

    def _expected_blast_radius(self, component_id: str) -> int:
        """Smallest max_blast_radius declared across all rules for *component_id*."""
        rules = self._get_rules_for(component_id)
        if not rules:
            return 0
        return min(r.max_blast_radius for r in rules)

    def _expected_affected(self, component_id: str, actual: set[str]) -> list[str]:
        """Return the expected affected list bounded by rules."""
        rules = self._get_rules_for(component_id)
        if not rules:
            return []
        max_radius = min(r.max_blast_radius for r in rules)
        # Return up to max_radius items from actual set (sorted for determinism).
        return sorted(actual)[: max_radius]

    def _determine_status(
        self, expected: int, actual: int
    ) -> ContainmentStatus:
        """Decide containment status based on expected vs actual blast radius."""
        if actual <= expected:
            return ContainmentStatus.CONTAINED
        if actual <= int(expected * 1.5):
            return ContainmentStatus.PARTIALLY_CONTAINED
        return ContainmentStatus.BREACHED

    @staticmethod
    def _effectiveness(expected: int, actual: int) -> float:
        """Containment effectiveness 0-1.  1.0 == perfect containment."""
        if actual == 0:
            return 1.0
        if expected == 0:
            return 0.0 if actual > 0 else 1.0
        ratio = expected / actual
        return min(1.0, max(0.0, ratio))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify_containment(self, component_id: str) -> ContainmentTest:
        """Test whether a failure in *component_id* is properly contained."""
        try:
            affected = self._graph.get_all_affected(component_id)
        except Exception:
            # Component not in the graph — no blast radius.
            affected = set()
        actual_radius = len(affected)
        expected_radius = self._expected_blast_radius(component_id)
        expected_aff = self._expected_affected(component_id, affected)
        status = self._determine_status(expected_radius, actual_radius)
        eff = self._effectiveness(expected_radius, actual_radius)
        return ContainmentTest(
            failure_component=component_id,
            failure_type="component_failure",
            expected_blast_radius=expected_radius,
            actual_blast_radius=actual_radius,
            expected_affected=expected_aff,
            actual_affected=sorted(affected),
            status=status,
            containment_effectiveness=eff,
        )

    def verify_all(self) -> list[ContainmentTest]:
        """Verify containment for every component in the graph."""
        results: list[ContainmentTest] = []
        for cid in self._graph.components:
            results.append(self.verify_containment(cid))
        return results

    def find_containment_gaps(self) -> list[ContainmentGap]:
        """Identify components missing key containment mechanisms."""
        gaps: list[ContainmentGap] = []
        ruled_ids = {r.component_id for r in self._rules}

        for cid, comp in self._graph.components.items():
            missing: list[ContainmentMechanism] = []

            # Check failover
            if not comp.failover.enabled:
                missing.append(ContainmentMechanism.FAILOVER)

            # Check bulkhead (autoscaling + replicas > 1)
            if not comp.autoscaling.enabled and comp.replicas <= 1:
                missing.append(ContainmentMechanism.BULKHEAD)

            # Check circuit breakers on incoming dependency edges
            has_cb = False
            for dep_comp in self._graph.get_dependents(comp.id):
                edge = self._graph.get_dependency_edge(dep_comp.id, comp.id)
                if edge and edge.circuit_breaker.enabled:
                    has_cb = True
                    break
            dependents = self._graph.get_dependents(comp.id)
            if dependents and not has_cb:
                missing.append(ContainmentMechanism.CIRCUIT_BREAKER)

            # Check timeout (capacity.timeout_seconds > 0 is good)
            if comp.capacity.timeout_seconds <= 0:
                missing.append(ContainmentMechanism.TIMEOUT)

            # Check rate limiter (security.rate_limiting)
            if not comp.security.rate_limiting:
                missing.append(ContainmentMechanism.RATE_LIMITER)

            # Check retry budget on outgoing edges
            has_retry = False
            for dep_comp in self._graph.get_dependencies(comp.id):
                edge = self._graph.get_dependency_edge(comp.id, dep_comp.id)
                if edge and edge.retry_strategy.enabled:
                    has_retry = True
                    break
            outgoing = self._graph.get_dependencies(comp.id)
            if outgoing and not has_retry:
                missing.append(ContainmentMechanism.RETRY_BUDGET)

            if not missing:
                continue

            # Determine risk level
            affected_count = len(self._graph.get_all_affected(cid))
            if affected_count >= 5 or len(missing) >= 4:
                risk = "critical"
            elif affected_count >= 3 or len(missing) >= 3:
                risk = "high"
            elif affected_count >= 1 or len(missing) >= 2:
                risk = "medium"
            else:
                risk = "low"

            recommendation = (
                f"Add {', '.join(m.value for m in missing)} to '{cid}'"
            )
            if cid not in ruled_ids:
                recommendation += " and define containment rules"

            gaps.append(
                ContainmentGap(
                    component_id=cid,
                    missing_mechanisms=missing,
                    risk_level=risk,
                    recommendation=recommendation,
                )
            )
        return gaps

    def calculate_containment_score(self) -> float:
        """Overall containment effectiveness as a 0-100 score."""
        tests = self.verify_all()
        if not tests:
            return 100.0
        contained_count = sum(
            1 for t in tests if t.status == ContainmentStatus.CONTAINED
        )
        partial_count = sum(
            1 for t in tests if t.status == ContainmentStatus.PARTIALLY_CONTAINED
        )
        total = len(tests)
        return round((contained_count + partial_count * 0.5) / total * 100.0, 1)

    def generate_report(self) -> ContainmentReport:
        """Produce a full containment verification report."""
        tests = self.verify_all()
        gaps = self.find_containment_gaps()

        contained = sum(1 for t in tests if t.status == ContainmentStatus.CONTAINED)
        breached = sum(1 for t in tests if t.status == ContainmentStatus.BREACHED)
        score = self.calculate_containment_score()

        recommendations: list[str] = []
        for gap in gaps:
            recommendations.append(gap.recommendation)
        for t in tests:
            if t.status == ContainmentStatus.BREACHED:
                recommendations.append(
                    f"Failure in '{t.failure_component}' breaches containment "
                    f"(actual={t.actual_blast_radius} > expected={t.expected_blast_radius})"
                )

        # Deduplicate
        seen: set[str] = set()
        unique: list[str] = []
        for r in recommendations:
            if r not in seen:
                seen.add(r)
                unique.append(r)

        return ContainmentReport(
            tests_run=len(tests),
            contained=contained,
            breached=breached,
            containment_score=score,
            tests=tests,
            gaps=gaps,
            recommendations=unique,
        )
