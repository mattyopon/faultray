"""Data Integrity Simulator.

Simulates data corruption, consistency, and integrity failure scenarios.
Tests what happens when data becomes inconsistent across replicas, when
writes are partially applied, or when backups contain corrupted data.
Critical for financial services, healthcare, and any system where data
accuracy is paramount.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


class IntegrityFailureType(str, Enum):
    """Types of data integrity failures."""

    PARTIAL_WRITE = "partial_write"
    REPLICATION_LAG = "replication_lag"
    SPLIT_BRAIN = "split_brain"
    BACKUP_CORRUPTION = "backup_corruption"
    SCHEMA_DRIFT = "schema_drift"
    STALE_CACHE = "stale_cache"
    ORPHANED_RECORDS = "orphaned_records"
    CONSTRAINT_VIOLATION = "constraint_violation"
    ENCODING_ERROR = "encoding_error"
    CLOCK_SKEW = "clock_skew"


class DataConsistencyLevel(str, Enum):
    """Data consistency models."""

    STRONG = "strong"
    EVENTUAL = "eventual"
    CAUSAL = "causal"
    READ_YOUR_WRITES = "read_your_writes"
    MONOTONIC = "monotonic"


class IntegrityScenario(BaseModel):
    """A data integrity failure scenario to simulate."""

    scenario_id: str
    failure_type: IntegrityFailureType
    target_component: str
    affected_data_percent: float = Field(default=10.0, ge=0.0, le=100.0)
    duration_minutes: float = Field(default=30.0, ge=0.0)
    consistency_level: DataConsistencyLevel = DataConsistencyLevel.EVENTUAL


class IntegrityImpact(BaseModel):
    """Impact assessment from simulating a data integrity failure."""

    scenario: IntegrityScenario
    data_loss_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    recovery_complexity: str = "manual_simple"
    detection_time_minutes: float = Field(default=5.0, ge=0.0)
    recovery_time_minutes: float = Field(default=30.0, ge=0.0)
    affected_transactions: int = Field(default=0, ge=0)
    financial_impact_estimate: float = Field(default=0.0, ge=0.0)


class IntegrityGuardrail(BaseModel):
    """A guardrail mechanism that protects against data integrity failures."""

    mechanism: str
    effectiveness: float = Field(default=0.5, ge=0.0, le=1.0)
    applicable_failures: list[IntegrityFailureType] = Field(default_factory=list)


class DataIntegrityReport(BaseModel):
    """Comprehensive data integrity simulation report."""

    scenarios_tested: int = 0
    critical_risks: int = 0
    impacts: list[IntegrityImpact] = Field(default_factory=list)
    guardrails_evaluated: list[IntegrityGuardrail] = Field(default_factory=list)
    overall_integrity_score: float = Field(default=100.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Risk weights by failure type and component type
# ---------------------------------------------------------------------------

_FAILURE_BASE_RISK: dict[IntegrityFailureType, float] = {
    IntegrityFailureType.PARTIAL_WRITE: 0.5,
    IntegrityFailureType.REPLICATION_LAG: 0.4,
    IntegrityFailureType.SPLIT_BRAIN: 0.8,
    IntegrityFailureType.BACKUP_CORRUPTION: 0.6,
    IntegrityFailureType.SCHEMA_DRIFT: 0.3,
    IntegrityFailureType.STALE_CACHE: 0.2,
    IntegrityFailureType.ORPHANED_RECORDS: 0.35,
    IntegrityFailureType.CONSTRAINT_VIOLATION: 0.45,
    IntegrityFailureType.ENCODING_ERROR: 0.25,
    IntegrityFailureType.CLOCK_SKEW: 0.3,
}

_COMPONENT_RISK_MODIFIERS: dict[ComponentType, dict[IntegrityFailureType, float]] = {
    ComponentType.DATABASE: {
        IntegrityFailureType.SPLIT_BRAIN: 1.5,
        IntegrityFailureType.REPLICATION_LAG: 1.4,
        IntegrityFailureType.PARTIAL_WRITE: 1.3,
        IntegrityFailureType.CONSTRAINT_VIOLATION: 1.2,
    },
    ComponentType.CACHE: {
        IntegrityFailureType.STALE_CACHE: 1.6,
        IntegrityFailureType.ENCODING_ERROR: 1.4,
    },
    ComponentType.QUEUE: {
        IntegrityFailureType.PARTIAL_WRITE: 1.2,
        IntegrityFailureType.ORPHANED_RECORDS: 1.3,
    },
    ComponentType.STORAGE: {
        IntegrityFailureType.BACKUP_CORRUPTION: 1.3,
        IntegrityFailureType.ENCODING_ERROR: 1.2,
    },
}

_RECOVERY_COMPLEXITY_MAP: dict[str, int] = {
    "automatic": 0,
    "manual_simple": 1,
    "manual_complex": 2,
    "impossible": 3,
}

_CONSISTENCY_RISK_FACTOR: dict[DataConsistencyLevel, float] = {
    DataConsistencyLevel.STRONG: 0.6,
    DataConsistencyLevel.EVENTUAL: 1.0,
    DataConsistencyLevel.CAUSAL: 0.8,
    DataConsistencyLevel.READ_YOUR_WRITES: 0.85,
    DataConsistencyLevel.MONOTONIC: 0.9,
}

# ---------------------------------------------------------------------------
# Standard guardrails
# ---------------------------------------------------------------------------

_STANDARD_GUARDRAILS: list[dict] = [
    {
        "mechanism": "checksums",
        "effectiveness": 0.8,
        "applicable_failures": [
            IntegrityFailureType.BACKUP_CORRUPTION,
            IntegrityFailureType.ENCODING_ERROR,
            IntegrityFailureType.PARTIAL_WRITE,
        ],
    },
    {
        "mechanism": "WAL",
        "effectiveness": 0.9,
        "applicable_failures": [
            IntegrityFailureType.PARTIAL_WRITE,
            IntegrityFailureType.SPLIT_BRAIN,
        ],
    },
    {
        "mechanism": "CDC",
        "effectiveness": 0.7,
        "applicable_failures": [
            IntegrityFailureType.REPLICATION_LAG,
            IntegrityFailureType.SCHEMA_DRIFT,
            IntegrityFailureType.ORPHANED_RECORDS,
        ],
    },
    {
        "mechanism": "idempotency_keys",
        "effectiveness": 0.85,
        "applicable_failures": [
            IntegrityFailureType.PARTIAL_WRITE,
            IntegrityFailureType.CONSTRAINT_VIOLATION,
        ],
    },
    {
        "mechanism": "saga_pattern",
        "effectiveness": 0.75,
        "applicable_failures": [
            IntegrityFailureType.PARTIAL_WRITE,
            IntegrityFailureType.ORPHANED_RECORDS,
            IntegrityFailureType.CONSTRAINT_VIOLATION,
        ],
    },
    {
        "mechanism": "NTP_sync",
        "effectiveness": 0.9,
        "applicable_failures": [
            IntegrityFailureType.CLOCK_SKEW,
        ],
    },
    {
        "mechanism": "cache_invalidation",
        "effectiveness": 0.8,
        "applicable_failures": [
            IntegrityFailureType.STALE_CACHE,
        ],
    },
]


class DataIntegritySimulator:
    """Simulates data integrity failure scenarios against an infrastructure graph.

    Parameters
    ----------
    graph:
        The infrastructure graph to analyze.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate_failure(self, scenario: IntegrityScenario) -> IntegrityImpact:
        """Simulate a data integrity failure and return its impact."""
        comp = self.graph.get_component(scenario.target_component)
        if comp is None:
            logger.warning(
                "Component %s not found; returning minimal impact.",
                scenario.target_component,
            )
            return IntegrityImpact(
                scenario=scenario,
                data_loss_risk=0.0,
                recovery_complexity="automatic",
                detection_time_minutes=0.0,
                recovery_time_minutes=0.0,
                affected_transactions=0,
                financial_impact_estimate=0.0,
            )

        data_loss_risk = self._calc_data_loss_risk(scenario, comp)
        recovery_complexity = self._calc_recovery_complexity(scenario, comp)
        detection_time = self._calc_detection_time(scenario, comp)
        recovery_time = self._calc_recovery_time(scenario, comp, recovery_complexity)
        affected_txns = self._calc_affected_transactions(scenario, comp)
        financial_impact = self._calc_financial_impact(
            scenario, comp, affected_txns, recovery_time,
        )

        return IntegrityImpact(
            scenario=scenario,
            data_loss_risk=min(1.0, max(0.0, data_loss_risk)),
            recovery_complexity=recovery_complexity,
            detection_time_minutes=max(0.0, detection_time),
            recovery_time_minutes=max(0.0, recovery_time),
            affected_transactions=max(0, affected_txns),
            financial_impact_estimate=max(0.0, financial_impact),
        )

    def evaluate_guardrails(self, component_id: str) -> list[IntegrityGuardrail]:
        """Assess which guardrails apply to *component_id* and their effectiveness."""
        comp = self.graph.get_component(component_id)
        if comp is None:
            return []

        guardrails: list[IntegrityGuardrail] = []
        for gdef in _STANDARD_GUARDRAILS:
            applicable = self._filter_applicable_failures(
                gdef["applicable_failures"], comp,
            )
            if not applicable:
                continue
            eff = gdef["effectiveness"]
            # Boost effectiveness if component has backup enabled
            if comp.security.backup_enabled and any(
                f in applicable
                for f in [
                    IntegrityFailureType.BACKUP_CORRUPTION,
                    IntegrityFailureType.PARTIAL_WRITE,
                ]
            ):
                eff = min(1.0, eff + 0.05)
            guardrails.append(
                IntegrityGuardrail(
                    mechanism=gdef["mechanism"],
                    effectiveness=eff,
                    applicable_failures=applicable,
                )
            )
        return guardrails

    def assess_consistency_risk(self, component_id: str) -> float:
        """Return a risk score (0.0-1.0) for data consistency issues."""
        comp = self.graph.get_component(component_id)
        if comp is None:
            return 0.0

        risk = 0.3  # baseline

        # Databases with replicas face replication lag risk
        if comp.type == ComponentType.DATABASE:
            risk += 0.15
            if comp.replicas > 1:
                risk += 0.1  # replication lag
        elif comp.type == ComponentType.CACHE:
            risk += 0.1
        elif comp.type == ComponentType.QUEUE:
            risk += 0.05

        # Multi-replica susceptibility to split-brain
        if comp.replicas > 2:
            risk += 0.1

        # No backup increases risk
        if not comp.security.backup_enabled:
            risk += 0.1

        # Degraded or down health
        if comp.health == HealthStatus.DOWN:
            risk += 0.2
        elif comp.health in (HealthStatus.DEGRADED, HealthStatus.OVERLOADED):
            risk += 0.1

        return min(1.0, max(0.0, risk))

    def find_vulnerable_components(self) -> list[str]:
        """Return component IDs most vulnerable to data integrity issues.

        A component is considered *vulnerable* when its consistency risk
        score exceeds 0.4.  Results are sorted by risk descending.
        """
        scored: list[tuple[str, float]] = []
        for comp_id in self.graph.components:
            risk = self.assess_consistency_risk(comp_id)
            if risk > 0.4:
                scored.append((comp_id, risk))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [cid for cid, _ in scored]

    def generate_report(
        self, scenarios: list[IntegrityScenario],
    ) -> DataIntegrityReport:
        """Run all *scenarios* and produce a consolidated report."""
        impacts: list[IntegrityImpact] = []
        critical = 0
        all_guardrails: dict[str, IntegrityGuardrail] = {}
        recommendations: list[str] = []

        for scenario in scenarios:
            impact = self.simulate_failure(scenario)
            impacts.append(impact)

            if impact.data_loss_risk >= 0.7:
                critical += 1

            # Collect guardrails for the target component
            for g in self.evaluate_guardrails(scenario.target_component):
                if g.mechanism not in all_guardrails:
                    all_guardrails[g.mechanism] = g

        guardrail_list = list(all_guardrails.values())

        # Generate recommendations
        recommendations = self._build_recommendations(impacts, guardrail_list)

        # Overall integrity score: start at 100, deduct for risks
        score = self._calc_integrity_score(impacts, guardrail_list)

        return DataIntegrityReport(
            scenarios_tested=len(scenarios),
            critical_risks=critical,
            impacts=impacts,
            guardrails_evaluated=guardrail_list,
            overall_integrity_score=score,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calc_data_loss_risk(
        self, scenario: IntegrityScenario, comp: Component,
    ) -> float:
        base = _FAILURE_BASE_RISK.get(scenario.failure_type, 0.3)

        # Apply component-type modifier
        modifier = (
            _COMPONENT_RISK_MODIFIERS
            .get(comp.type, {})
            .get(scenario.failure_type, 1.0)
        )
        risk = base * modifier

        # Consistency level factor
        risk *= _CONSISTENCY_RISK_FACTOR.get(
            scenario.consistency_level, 1.0,
        )

        # Affected data percentage amplifies risk
        risk *= (scenario.affected_data_percent / 100.0)

        # Duration amplification (longer = worse, up to 2x at 120 min)
        duration_factor = min(2.0, 1.0 + scenario.duration_minutes / 120.0)
        risk *= duration_factor

        # Backup reduces backup-corruption risk
        if (
            scenario.failure_type == IntegrityFailureType.BACKUP_CORRUPTION
            and comp.security.backup_enabled
        ):
            risk *= 0.5

        # Multi-replica resilience to single-node corruption
        if comp.replicas > 1 and scenario.failure_type not in (
            IntegrityFailureType.REPLICATION_LAG,
            IntegrityFailureType.SPLIT_BRAIN,
        ):
            risk *= max(0.3, 1.0 - 0.15 * (comp.replicas - 1))

        return risk

    def _calc_recovery_complexity(
        self, scenario: IntegrityScenario, comp: Component,
    ) -> str:
        ft = scenario.failure_type

        if ft == IntegrityFailureType.STALE_CACHE:
            return "automatic"
        if ft == IntegrityFailureType.REPLICATION_LAG:
            return "automatic" if comp.replicas > 1 else "manual_simple"
        if ft in (
            IntegrityFailureType.SPLIT_BRAIN,
            IntegrityFailureType.BACKUP_CORRUPTION,
        ):
            if scenario.affected_data_percent > 50:
                return "impossible" if not comp.security.backup_enabled else "manual_complex"
            return "manual_complex"
        if ft == IntegrityFailureType.PARTIAL_WRITE:
            return "manual_simple" if comp.security.backup_enabled else "manual_complex"
        if ft in (
            IntegrityFailureType.SCHEMA_DRIFT,
            IntegrityFailureType.ORPHANED_RECORDS,
        ):
            return "manual_simple"
        if ft == IntegrityFailureType.CONSTRAINT_VIOLATION:
            return "manual_simple"
        if ft == IntegrityFailureType.ENCODING_ERROR:
            return "manual_simple"
        # CLOCK_SKEW or any future type
        return "automatic" if ft == IntegrityFailureType.CLOCK_SKEW else "manual_simple"

    def _calc_detection_time(
        self, scenario: IntegrityScenario, comp: Component,
    ) -> float:
        base_detection: dict[IntegrityFailureType, float] = {
            IntegrityFailureType.PARTIAL_WRITE: 5.0,
            IntegrityFailureType.REPLICATION_LAG: 2.0,
            IntegrityFailureType.SPLIT_BRAIN: 10.0,
            IntegrityFailureType.BACKUP_CORRUPTION: 60.0,
            IntegrityFailureType.SCHEMA_DRIFT: 30.0,
            IntegrityFailureType.STALE_CACHE: 1.0,
            IntegrityFailureType.ORPHANED_RECORDS: 120.0,
            IntegrityFailureType.CONSTRAINT_VIOLATION: 1.0,
            IntegrityFailureType.ENCODING_ERROR: 15.0,
            IntegrityFailureType.CLOCK_SKEW: 5.0,
        }
        detection = base_detection.get(scenario.failure_type, 10.0)

        # Logging reduces detection time
        if comp.security.log_enabled:
            detection *= 0.5

        # IDS monitoring reduces detection time further
        if comp.security.ids_monitored:
            detection *= 0.7

        return detection

    def _calc_recovery_time(
        self,
        scenario: IntegrityScenario,
        comp: Component,
        complexity: str,
    ) -> float:
        complexity_multiplier = {
            "automatic": 1.0,
            "manual_simple": 3.0,
            "manual_complex": 8.0,
            "impossible": 20.0,
        }
        mult = complexity_multiplier.get(complexity, 3.0)
        base_time = comp.operational_profile.mttr_minutes
        if base_time <= 0:
            base_time = 30.0

        recovery = base_time * mult

        # Failover speeds up recovery
        if comp.failover.enabled:
            recovery *= 0.5

        return recovery

    def _calc_affected_transactions(
        self, scenario: IntegrityScenario, comp: Component,
    ) -> int:
        # Estimate based on max_rps, duration, and affected percent
        rps = comp.capacity.max_rps if comp.capacity.max_rps > 0 else 100
        total_txns = rps * scenario.duration_minutes * 60
        affected = total_txns * (scenario.affected_data_percent / 100.0)
        return int(affected)

    def _calc_financial_impact(
        self,
        scenario: IntegrityScenario,
        comp: Component,
        affected_txns: int,
        recovery_time: float,
    ) -> float:
        rpm = comp.cost_profile.revenue_per_minute
        if rpm <= 0:
            rpm = 0.0
        return affected_txns * rpm if rpm > 0 else recovery_time * rpm

    def _filter_applicable_failures(
        self,
        failures: list[IntegrityFailureType],
        comp: Component,
    ) -> list[IntegrityFailureType]:
        """Keep only failures relevant to *comp*'s type."""
        result = []
        for f in failures:
            # Cache-specific failures only apply to CACHE
            if f == IntegrityFailureType.STALE_CACHE and comp.type != ComponentType.CACHE:
                continue
            result.append(f)
        return result

    def _build_recommendations(
        self,
        impacts: list[IntegrityImpact],
        guardrails: list[IntegrityGuardrail],
    ) -> list[str]:
        recs: list[str] = []
        seen: set[str] = set()

        for impact in impacts:
            comp = self.graph.get_component(impact.scenario.target_component)
            ft = impact.scenario.failure_type

            if impact.data_loss_risk >= 0.7:
                rec = (
                    f"CRITICAL: High data loss risk ({impact.data_loss_risk:.0%}) "
                    f"for {impact.scenario.target_component} under {ft.value}."
                )
                if rec not in seen:
                    recs.append(rec)
                    seen.add(rec)

            if impact.recovery_complexity == "impossible":
                rec = (
                    f"Enable backups for {impact.scenario.target_component} "
                    f"to make {ft.value} recoverable."
                )
                if rec not in seen:
                    recs.append(rec)
                    seen.add(rec)

            if comp and not comp.security.backup_enabled:
                rec = f"Enable backups for {impact.scenario.target_component}."
                if rec not in seen:
                    recs.append(rec)
                    seen.add(rec)

            if comp and comp.replicas <= 1 and ft in (
                IntegrityFailureType.SPLIT_BRAIN,
                IntegrityFailureType.REPLICATION_LAG,
            ):
                rec = (
                    f"Add replicas to {impact.scenario.target_component} "
                    f"to mitigate {ft.value}."
                )
                if rec not in seen:
                    recs.append(rec)
                    seen.add(rec)

        # Guardrail coverage recommendations
        covered_failures: set[IntegrityFailureType] = set()
        for g in guardrails:
            for f in g.applicable_failures:
                covered_failures.add(f)
        uncovered = set(IntegrityFailureType) - covered_failures
        if uncovered:
            rec = (
                "Consider adding guardrails for uncovered failure types: "
                + ", ".join(sorted(f.value for f in uncovered))
                + "."
            )
            if rec not in seen:
                recs.append(rec)
                seen.add(rec)

        return recs

    def _calc_integrity_score(
        self,
        impacts: list[IntegrityImpact],
        guardrails: list[IntegrityGuardrail],
    ) -> float:
        if not impacts:
            return 100.0

        score = 100.0

        # Deduct for each impact's risk
        for impact in impacts:
            score -= impact.data_loss_risk * 15.0
            complexity_penalty = {
                "automatic": 0,
                "manual_simple": 2,
                "manual_complex": 5,
                "impossible": 15,
            }
            score -= complexity_penalty.get(impact.recovery_complexity, 2)

        # Guardrails add back some score
        for g in guardrails:
            score += g.effectiveness * 2.0

        return min(100.0, max(0.0, score))
