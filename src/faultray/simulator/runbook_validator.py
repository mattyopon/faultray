# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Runbook completeness validator.

Analyzes infrastructure topology to identify all critical failure scenarios
and validates that operational runbooks exist, are complete, and cover
the necessary recovery steps for each scenario.

Includes the newer Pydantic-based RunbookValidationEngine for granular
per-step validation, coverage gap analysis, MTTR estimation, staleness
detection, auto-suggestion, escalation validation, and runbook comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


class RunbookStatus(str, Enum):
    """Status of a runbook's completeness."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"
    OUTDATED = "outdated"


@dataclass
class RecoveryStep:
    """A single step in a recovery runbook."""

    order: int
    description: str
    is_automated: bool
    estimated_time_minutes: float
    requires_approval: bool


@dataclass
class Runbook:
    """An operational runbook for a specific failure scenario."""

    scenario_id: str
    title: str
    component_id: str
    steps: list[RecoveryStep]
    last_tested: str | None  # ISO date string or None
    owner: str
    status: RunbookStatus
    estimated_total_time_minutes: float


@dataclass
class RunbookGap:
    """A gap in runbook coverage -- a scenario without an adequate runbook."""

    scenario_description: str
    component_id: str
    component_name: str
    severity: str  # "critical", "high", "medium", "low"
    reason: str  # Why a runbook is needed for this scenario
    suggested_steps: list[str]


@dataclass
class RunbookValidationReport:
    """Complete report from runbook completeness validation."""

    total_scenarios: int
    covered_scenarios: int
    coverage_percent: float
    completeness_score: float  # 0-100
    gaps: list[RunbookGap]
    existing_runbooks: list[Runbook]
    recommendations: list[str]
    mean_recovery_time_minutes: float


# Standard failure modes per component type.
_FAILURE_MODES: dict[ComponentType, list[str]] = {
    ComponentType.DATABASE: [
        "data corruption",
        "replication lag",
        "connection pool exhaustion",
    ],
    ComponentType.LOAD_BALANCER: [
        "routing failure",
        "health check misconfiguration",
    ],
    ComponentType.APP_SERVER: [
        "out of memory",
        "thread exhaustion",
        "dependency timeout",
    ],
    ComponentType.CACHE: [
        "cache invalidation storm",
        "memory overflow",
    ],
    ComponentType.QUEUE: [
        "message backlog",
        "dead letter overflow",
    ],
    ComponentType.WEB_SERVER: [
        "connection limit exceeded",
        "TLS certificate expiry",
    ],
    ComponentType.STORAGE: [
        "disk full",
        "IO throttling",
    ],
    ComponentType.DNS: [
        "DNS resolution failure",
        "TTL misconfiguration",
    ],
    ComponentType.EXTERNAL_API: [
        "upstream timeout",
        "rate limiting",
    ],
    ComponentType.CUSTOM: [
        "unexpected failure",
    ],
}

# Suggested recovery steps for each failure mode (keyed by mode string).
_SUGGESTED_STEPS: dict[str, list[str]] = {
    # DATABASE
    "data corruption": [
        "Identify affected tables or documents",
        "Switch traffic to read replicas",
        "Restore from latest verified backup",
        "Validate data integrity after restore",
        "Re-enable write traffic",
        "Notify stakeholders of data window",
    ],
    "replication lag": [
        "Check replication status and lag metrics",
        "Identify blocking queries on primary",
        "Pause non-critical batch jobs",
        "Increase replica resources if needed",
        "Monitor until lag returns to baseline",
    ],
    "connection pool exhaustion": [
        "Identify top connection consumers",
        "Kill idle connections if safe",
        "Increase connection pool size temporarily",
        "Scale up database or add read replicas",
        "Review application connection management",
    ],
    # LOAD_BALANCER
    "routing failure": [
        "Check health of backend targets",
        "Verify routing rules and listener configuration",
        "Failover to backup load balancer if available",
        "Manually update DNS if needed",
        "Monitor traffic distribution",
    ],
    "health check misconfiguration": [
        "Review health check endpoint and thresholds",
        "Temporarily disable flapping health checks",
        "Correct health check configuration",
        "Re-register healthy targets",
        "Validate routing is restored",
    ],
    # APP_SERVER
    "out of memory": [
        "Identify memory-consuming processes or requests",
        "Restart affected instances",
        "Enable memory limits or OOM killer",
        "Scale horizontally if under load",
        "Review code for memory leaks",
    ],
    "thread exhaustion": [
        "Identify blocked or slow threads",
        "Restart affected instances",
        "Increase thread pool size temporarily",
        "Add circuit breakers for slow dependencies",
        "Scale horizontally",
    ],
    "dependency timeout": [
        "Identify which dependency is timing out",
        "Enable or adjust circuit breaker settings",
        "Increase timeout thresholds if appropriate",
        "Switch to fallback or cached responses",
        "Notify dependency team",
    ],
    # CACHE
    "cache invalidation storm": [
        "Identify trigger for mass invalidation",
        "Enable request coalescing or singleflight",
        "Rate-limit cache rebuild requests",
        "Scale backend to absorb increased load",
        "Monitor cache hit rate recovery",
    ],
    "memory overflow": [
        "Check current memory usage and eviction policy",
        "Increase cache memory allocation",
        "Review TTL settings for large objects",
        "Restart cache nodes if unresponsive",
        "Monitor memory usage post-fix",
    ],
    # QUEUE
    "message backlog": [
        "Check consumer health and throughput",
        "Scale up consumers",
        "Identify poison messages causing processing failures",
        "Increase consumer concurrency",
        "Monitor queue depth until normal",
    ],
    "dead letter overflow": [
        "Review dead letter queue messages for patterns",
        "Fix root cause of message processing failures",
        "Replay or discard dead letter messages",
        "Set up alerts for dead letter queue depth",
        "Monitor processing success rate",
    ],
    # WEB_SERVER
    "connection limit exceeded": [
        "Check current connection count and limits",
        "Increase max connections if resources allow",
        "Enable connection keep-alive tuning",
        "Scale horizontally behind load balancer",
        "Identify and block abusive clients",
    ],
    "TLS certificate expiry": [
        "Identify expiring or expired certificates",
        "Renew or replace certificates immediately",
        "Restart web server to load new certificates",
        "Verify TLS handshake works for clients",
        "Set up automated certificate renewal",
    ],
    # STORAGE
    "disk full": [
        "Identify largest files and directories",
        "Remove old logs, temp files, or archives",
        "Expand disk volume if possible",
        "Enable log rotation and retention policies",
        "Monitor disk usage trending",
    ],
    "IO throttling": [
        "Check IOPS limits and current utilization",
        "Reduce IO-heavy batch operations",
        "Upgrade storage tier or increase provisioned IOPS",
        "Distribute IO across multiple volumes",
        "Monitor IO latency",
    ],
    # DNS
    "DNS resolution failure": [
        "Verify DNS server health",
        "Check zone file for misconfigurations",
        "Failover to backup DNS provider",
        "Update client resolver configuration if needed",
        "Monitor DNS resolution times",
    ],
    "TTL misconfiguration": [
        "Identify records with incorrect TTL values",
        "Update TTL to appropriate values",
        "Flush DNS caches if stale records are served",
        "Verify propagation of corrected records",
    ],
    # EXTERNAL_API
    "upstream timeout": [
        "Confirm upstream service status",
        "Enable circuit breaker for the upstream",
        "Serve cached or fallback responses",
        "Contact upstream provider if outage confirmed",
        "Monitor upstream response times",
    ],
    "rate limiting": [
        "Check current request rate against limits",
        "Implement request throttling on our side",
        "Request rate limit increase from provider",
        "Queue non-urgent requests for later",
        "Monitor request success rate",
    ],
    # CUSTOM
    "unexpected failure": [
        "Gather logs and metrics from the component",
        "Restart the component",
        "Check recent changes or deployments",
        "Escalate to component owner",
        "Monitor for recurrence",
    ],
}


class RunbookValidator:
    """Validates that operational runbooks cover all critical failure scenarios.

    Analyzes the infrastructure graph to auto-identify failure scenarios
    for each component type, then checks whether the provided runbooks
    adequately cover those scenarios.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def validate(
        self, runbooks: list[Runbook] | None = None
    ) -> RunbookValidationReport:
        """Run a full validation of runbook completeness.

        Args:
            runbooks: Existing runbooks to check against identified scenarios.
                      If ``None``, all scenarios will be reported as gaps.

        Returns:
            A ``RunbookValidationReport`` with coverage, gaps, and recommendations.
        """
        runbooks = runbooks or []

        scenarios = self._identify_critical_scenarios()
        total_scenarios = len(scenarios)

        if total_scenarios == 0:
            return RunbookValidationReport(
                total_scenarios=0,
                covered_scenarios=0,
                coverage_percent=100.0,
                completeness_score=100.0,
                gaps=[],
                existing_runbooks=list(runbooks),
                recommendations=[],
                mean_recovery_time_minutes=0.0,
            )

        covered, gaps = self._check_coverage(scenarios, runbooks)
        coverage_percent = (covered / total_scenarios) * 100.0 if total_scenarios else 0.0
        completeness_score = self._calculate_completeness(runbooks)
        mean_recovery = self._estimate_mean_recovery(runbooks)
        recommendations = self._build_recommendations(
            gaps, runbooks, coverage_percent, completeness_score
        )

        return RunbookValidationReport(
            total_scenarios=total_scenarios,
            covered_scenarios=covered,
            coverage_percent=round(coverage_percent, 2),
            completeness_score=round(completeness_score, 2),
            gaps=gaps,
            existing_runbooks=list(runbooks),
            recommendations=recommendations,
            mean_recovery_time_minutes=round(mean_recovery, 2),
        )

    def generate_required_scenarios(self) -> list[RunbookGap]:
        """Generate a list of all required runbook scenarios as gaps.

        This is useful when no runbooks exist yet and you want to see the
        full list of scenarios that need coverage.
        """
        scenarios = self._identify_critical_scenarios()
        gaps: list[RunbookGap] = []
        for comp_id, scenario, severity in scenarios:
            comp = self.graph.get_component(comp_id)
            comp_name = comp.name if comp else comp_id
            suggested = self._suggest_recovery_steps(comp_id, scenario)
            gaps.append(
                RunbookGap(
                    scenario_description=f"{scenario} on {comp_name}",
                    component_id=comp_id,
                    component_name=comp_name,
                    severity=severity,
                    reason=f"No runbook exists for '{scenario}' affecting {comp_name}",
                    suggested_steps=suggested,
                )
            )
        return gaps

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _identify_critical_scenarios(
        self,
    ) -> list[tuple[str, str, str]]:
        """Identify all failure scenarios from the graph topology.

        Returns a list of ``(component_id, scenario_description, severity)``.
        Severity is determined by the number of dependents and whether the
        component is a single point of failure (SPOF).
        """
        scenarios: list[tuple[str, str, str]] = []

        for comp_id, comp in self.graph.components.items():
            failure_modes = _FAILURE_MODES.get(comp.type, ["unexpected failure"])

            dependents = self.graph.get_dependents(comp_id)
            num_dependents = len(dependents)
            is_spof = comp.replicas <= 1 and not comp.failover.enabled

            for mode in failure_modes:
                severity = self._compute_severity(num_dependents, is_spof)
                scenarios.append((comp_id, mode, severity))

        return scenarios

    @staticmethod
    def _compute_severity(num_dependents: int, is_spof: bool) -> str:
        """Compute severity based on dependent count and SPOF status."""
        if is_spof and num_dependents >= 2:
            return "critical"
        if is_spof or num_dependents >= 3:
            return "critical"
        if num_dependents >= 2:
            return "high"
        if num_dependents >= 1:
            return "medium"
        return "low"

    def _check_coverage(
        self,
        scenarios: list[tuple[str, str, str]],
        runbooks: list[Runbook],
    ) -> tuple[int, list[RunbookGap]]:
        """Check which scenarios are covered by provided runbooks.

        A scenario is considered covered if there is at least one runbook whose
        ``scenario_id`` exactly matches ``"{component_id}:{scenario_description}"``
        **or** whose ``component_id`` matches and whose ``title`` contains the
        scenario description (case-insensitive).

        Returns the count of covered scenarios and a list of gaps.
        """
        # Index runbooks for fast lookup.
        by_scenario_id: dict[str, Runbook] = {}
        by_component: dict[str, list[Runbook]] = {}
        for rb in runbooks:
            by_scenario_id[rb.scenario_id] = rb
            by_component.setdefault(rb.component_id, []).append(rb)

        covered = 0
        gaps: list[RunbookGap] = []

        for comp_id, scenario, severity in scenarios:
            canonical_id = f"{comp_id}:{scenario}"
            comp = self.graph.get_component(comp_id)
            comp_name = comp.name if comp else comp_id

            # Check by exact scenario_id match first.
            if canonical_id in by_scenario_id:
                rb = by_scenario_id[canonical_id]
                if rb.status not in (RunbookStatus.MISSING, RunbookStatus.OUTDATED):
                    covered += 1
                    continue
                # Runbook exists but is missing/outdated -- still a gap.
                gaps.append(
                    RunbookGap(
                        scenario_description=f"{scenario} on {comp_name}",
                        component_id=comp_id,
                        component_name=comp_name,
                        severity=severity,
                        reason=(
                            f"Runbook exists but status is '{rb.status.value}'"
                        ),
                        suggested_steps=self._suggest_recovery_steps(
                            comp_id, scenario
                        ),
                    )
                )
                continue

            # Fuzzy match: same component and title contains scenario.
            matched = False
            for rb in by_component.get(comp_id, []):
                if scenario.lower() in rb.title.lower():
                    if rb.status not in (
                        RunbookStatus.MISSING,
                        RunbookStatus.OUTDATED,
                    ):
                        matched = True
                        break

            if matched:
                covered += 1
            else:
                gaps.append(
                    RunbookGap(
                        scenario_description=f"{scenario} on {comp_name}",
                        component_id=comp_id,
                        component_name=comp_name,
                        severity=severity,
                        reason=(
                            f"No runbook exists for '{scenario}' affecting {comp_name}"
                        ),
                        suggested_steps=self._suggest_recovery_steps(
                            comp_id, scenario
                        ),
                    )
                )

        return covered, gaps

    def _suggest_recovery_steps(
        self, component_id: str, scenario: str
    ) -> list[str]:
        """Suggest recovery steps for a given failure scenario."""
        steps = _SUGGESTED_STEPS.get(scenario)
        if steps:
            return list(steps)
        # Fallback: generic steps.
        comp = self.graph.get_component(component_id)
        comp_name = comp.name if comp else component_id
        return [
            f"Investigate {scenario} on {comp_name}",
            f"Apply mitigation for {scenario}",
            f"Verify {comp_name} has recovered",
            "Notify stakeholders",
        ]

    def _calculate_completeness(self, runbooks: list[Runbook]) -> float:
        """Calculate a completeness score (0-100) for provided runbooks.

        The score considers:
        - Status distribution (complete=1.0, partial=0.5, outdated=0.25, missing=0)
        - Number of steps (more detailed = better, up to a cap)
        - Automation level (higher automation = better)
        - Testing recency (tested runbooks score higher)
        """
        if not runbooks:
            return 0.0

        scores: list[float] = []
        for rb in runbooks:
            score = 0.0

            # Status weight (0-40 points).
            status_weights = {
                RunbookStatus.COMPLETE: 40.0,
                RunbookStatus.PARTIAL: 20.0,
                RunbookStatus.OUTDATED: 10.0,
                RunbookStatus.MISSING: 0.0,
            }
            score += status_weights.get(rb.status, 0.0)

            # Step detail (0-25 points). Cap at 5+ steps for full score.
            step_count = len(rb.steps)
            if step_count >= 5:
                score += 25.0
            elif step_count > 0:
                score += (step_count / 5.0) * 25.0

            # Automation level (0-20 points).
            if rb.steps:
                auto_ratio = sum(
                    1 for s in rb.steps if s.is_automated
                ) / len(rb.steps)
                score += auto_ratio * 20.0

            # Testing recency (0-15 points).
            if rb.last_tested is not None:
                score += 15.0  # Any test date gets full recency credit.

            scores.append(min(100.0, score))

        return sum(scores) / len(scores)

    def _estimate_mean_recovery(self, runbooks: list[Runbook]) -> float:
        """Estimate mean time to recovery across all runbooks."""
        if not runbooks:
            return 0.0
        times = [
            rb.estimated_total_time_minutes
            for rb in runbooks
            if rb.estimated_total_time_minutes > 0
        ]
        if not times:
            return 0.0
        return sum(times) / len(times)

    def _build_recommendations(
        self,
        gaps: list[RunbookGap],
        runbooks: list[Runbook],
        coverage_percent: float,
        completeness_score: float,
    ) -> list[str]:
        """Build actionable recommendations based on validation results."""
        recommendations: list[str] = []

        # Coverage recommendations.
        if coverage_percent < 50.0:
            recommendations.append(
                f"Runbook coverage is critically low ({coverage_percent:.1f}%). "
                "Prioritize creating runbooks for critical severity gaps."
            )
        elif coverage_percent < 80.0:
            recommendations.append(
                f"Runbook coverage is below target ({coverage_percent:.1f}%). "
                "Focus on high and critical severity gaps."
            )

        # Critical gaps.
        critical_gaps = [g for g in gaps if g.severity == "critical"]
        if critical_gaps:
            comp_names = ", ".join(
                sorted({g.component_name for g in critical_gaps})
            )
            recommendations.append(
                f"Create runbooks for {len(critical_gaps)} critical "
                f"scenario(s) affecting: {comp_names}"
            )

        # Outdated runbooks.
        outdated = [rb for rb in runbooks if rb.status == RunbookStatus.OUTDATED]
        if outdated:
            recommendations.append(
                f"Update {len(outdated)} outdated runbook(s): "
                + ", ".join(rb.title for rb in outdated)
            )

        # Partial runbooks.
        partial = [rb for rb in runbooks if rb.status == RunbookStatus.PARTIAL]
        if partial:
            recommendations.append(
                f"Complete {len(partial)} partial runbook(s): "
                + ", ".join(rb.title for rb in partial)
            )

        # Untested runbooks.
        untested = [rb for rb in runbooks if rb.last_tested is None]
        if untested:
            recommendations.append(
                f"Schedule testing for {len(untested)} untested runbook(s)."
            )

        # Low automation.
        for rb in runbooks:
            if rb.steps:
                auto_ratio = sum(
                    1 for s in rb.steps if s.is_automated
                ) / len(rb.steps)
                if auto_ratio < 0.3:
                    recommendations.append(
                        f"Runbook '{rb.title}' has low automation "
                        f"({auto_ratio*100:.0f}%). Consider automating "
                        "repetitive steps to reduce MTTR."
                    )

        # Completeness.
        if completeness_score < 50.0 and runbooks:
            recommendations.append(
                f"Overall completeness score is low ({completeness_score:.1f}/100). "
                "Add more detail, automation, and testing to existing runbooks."
            )

        return recommendations


# ======================================================================
# Pydantic-based Runbook Validation Engine (v2)
# ======================================================================


class RunbookStepType(str, Enum):
    """Type of a runbook step."""

    DIAGNOSTIC = "diagnostic"
    REMEDIATION = "remediation"
    ESCALATION = "escalation"
    VERIFICATION = "verification"
    ROLLBACK = "rollback"
    NOTIFICATION = "notification"
    MANUAL_CHECK = "manual_check"


class ValidationResult(str, Enum):
    """Result of validating a runbook or step."""

    VALID = "valid"
    STALE = "stale"
    INCOMPLETE = "incomplete"
    INCORRECT = "incorrect"
    UNTESTABLE = "untestable"
    MISSING_COMPONENT = "missing_component"


class RunbookStep(BaseModel):
    """A single step in a runbook."""

    step_number: int
    description: str
    step_type: RunbookStepType
    target_component_id: str
    expected_outcome: str
    timeout_seconds: float
    requires_approval: bool


class RunbookV2(BaseModel):
    """An operational runbook (v2 Pydantic model)."""

    id: str
    name: str
    scenario: str
    steps: list[RunbookStep]
    last_tested: str
    owner: str
    severity: str


class StepValidation(BaseModel):
    """Validation result for a single runbook step."""

    step_number: int
    result: ValidationResult
    reason: str
    suggestion: str


class CoverageGap(BaseModel):
    """A failure scenario not covered by any runbook."""

    component_id: str
    component_name: str
    failure_scenario: str
    severity: str


class EscalationValidation(BaseModel):
    """Validation of escalation paths within a runbook."""

    has_escalation: bool
    escalation_steps: list[int] = Field(default_factory=list)
    has_notification: bool
    notification_steps: list[int] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    is_valid: bool


class RunbookDiff(BaseModel):
    """A single difference between two runbooks."""

    field: str
    old_value: str
    new_value: str


class RunbookComparison(BaseModel):
    """Comparison of two runbook versions."""

    runbook_a_id: str
    runbook_b_id: str
    differences: list[RunbookDiff] = Field(default_factory=list)
    steps_added: list[int] = Field(default_factory=list)
    steps_removed: list[int] = Field(default_factory=list)
    steps_modified: list[int] = Field(default_factory=list)
    is_identical: bool


class RunbookValidationReportV2(BaseModel):
    """Full validation report for a runbook (v2)."""

    runbook_id: str
    overall_result: ValidationResult
    step_validations: list[StepValidation]
    coverage_gaps: list[str]
    staleness_days: int
    recommendations: list[str]
    estimated_mttr_minutes: float
    confidence: float


# Standard failure scenarios per component type for coverage analysis.
_COVERAGE_SCENARIOS: dict[ComponentType, list[str]] = {
    ComponentType.DATABASE: [
        "database_failover",
        "replication_lag",
        "connection_exhaustion",
    ],
    ComponentType.LOAD_BALANCER: [
        "routing_failure",
        "health_check_misconfiguration",
    ],
    ComponentType.APP_SERVER: [
        "oom_kill",
        "thread_exhaustion",
        "dependency_timeout",
    ],
    ComponentType.CACHE: [
        "cache_stampede",
        "memory_overflow",
    ],
    ComponentType.QUEUE: [
        "message_backlog",
        "dead_letter_overflow",
    ],
    ComponentType.WEB_SERVER: [
        "connection_limit",
        "tls_expiry",
    ],
    ComponentType.STORAGE: [
        "disk_full",
        "io_throttle",
    ],
    ComponentType.DNS: [
        "dns_resolution_failure",
        "ttl_misconfiguration",
    ],
    ComponentType.EXTERNAL_API: [
        "upstream_timeout",
        "rate_limiting",
    ],
    ComponentType.CUSTOM: [
        "unexpected_failure",
    ],
}


class RunbookValidationEngine:
    """Stateless engine for validating operational runbooks against topology.

    All methods are stateless -- the engine holds no mutable state and can
    be reused across multiple invocations.
    """

    # ------------------------------------------------------------------
    # validate_runbook
    # ------------------------------------------------------------------

    def validate_runbook(
        self, graph: InfraGraph, runbook: RunbookV2
    ) -> RunbookValidationReportV2:
        """Validate a runbook against the infrastructure graph.

        Checks each step for target component existence, step ordering,
        timeout sanity, and overall completeness.  Also computes staleness
        and MTTR.
        """
        step_validations: list[StepValidation] = []
        recommendations: list[str] = []
        coverage_gaps: list[str] = []

        has_diagnostic = False
        has_verification = False
        has_remediation = False

        for step in runbook.steps:
            sv = self._validate_step(graph, step)
            step_validations.append(sv)
            if step.step_type == RunbookStepType.DIAGNOSTIC:
                has_diagnostic = True
            if step.step_type == RunbookStepType.VERIFICATION:
                has_verification = True
            if step.step_type == RunbookStepType.REMEDIATION:
                has_remediation = True

        # Completeness checks.
        if not has_diagnostic:
            recommendations.append(
                "Add a diagnostic step to identify the root cause."
            )
        if not has_verification:
            recommendations.append(
                "Add a verification step to confirm recovery."
            )
        if not has_remediation and runbook.steps:
            recommendations.append(
                "Add a remediation step to fix the issue."
            )

        # Staleness.
        staleness_days = self._compute_staleness(runbook)
        if staleness_days > 90:
            recommendations.append(
                f"Runbook is stale ({staleness_days} days since last test). "
                "Schedule a test."
            )

        # MTTR.
        mttr = self.estimate_mttr(runbook)

        # Determine overall result.
        overall = self._determine_overall(step_validations, staleness_days, runbook)

        # Confidence: fraction of valid steps.
        total_steps = len(step_validations)
        valid_steps = sum(
            1 for sv in step_validations if sv.result == ValidationResult.VALID
        )
        confidence = valid_steps / total_steps if total_steps > 0 else 0.0

        # Coverage gaps for the scenario's component types.
        for step in runbook.steps:
            comp = graph.get_component(step.target_component_id)
            if comp is None:
                coverage_gaps.append(
                    f"Component '{step.target_component_id}' not found in topology"
                )

        return RunbookValidationReportV2(
            runbook_id=runbook.id,
            overall_result=overall,
            step_validations=step_validations,
            coverage_gaps=coverage_gaps,
            staleness_days=staleness_days,
            recommendations=recommendations,
            estimated_mttr_minutes=mttr,
            confidence=round(confidence, 2),
        )

    # ------------------------------------------------------------------
    # find_coverage_gaps
    # ------------------------------------------------------------------

    def find_coverage_gaps(
        self, graph: InfraGraph, runbooks: list[RunbookV2]
    ) -> list[CoverageGap]:
        """Find failure scenarios not covered by any existing runbook."""
        # Build set of (component_id, scenario) covered by runbooks.
        covered: set[tuple[str, str]] = set()
        for rb in runbooks:
            for step in rb.steps:
                covered.add((step.target_component_id, rb.scenario))

        # Also consider runbook scenario text matching component ids.
        covered_scenarios: set[str] = set()
        for rb in runbooks:
            covered_scenarios.add(rb.scenario.lower())

        gaps: list[CoverageGap] = []
        for comp_id, comp in graph.components.items():
            scenarios = _COVERAGE_SCENARIOS.get(comp.type, ["unexpected_failure"])
            dependents = graph.get_dependents(comp_id)
            num_dependents = len(dependents)
            is_spof = comp.replicas <= 1 and not comp.failover.enabled

            for scenario in scenarios:
                # Check if any runbook covers this component+scenario.
                if (comp_id, scenario) in covered:
                    continue
                # Fuzzy: check if the scenario name appears in any runbook scenario.
                if scenario.lower() in covered_scenarios:
                    continue
                severity = self._severity_from_dependents(num_dependents, is_spof)
                gaps.append(
                    CoverageGap(
                        component_id=comp_id,
                        component_name=comp.name,
                        failure_scenario=scenario,
                        severity=severity,
                    )
                )
        return gaps

    # ------------------------------------------------------------------
    # estimate_mttr
    # ------------------------------------------------------------------

    def estimate_mttr(self, runbook: RunbookV2) -> float:
        """Estimate Mean Time To Recovery from runbook steps.

        MTTR is the sum of all step timeouts (as a proxy for execution
        time).  Steps requiring approval add a fixed 5-minute overhead.
        """
        if not runbook.steps:
            return 0.0
        total_seconds = 0.0
        for step in runbook.steps:
            total_seconds += step.timeout_seconds
            if step.requires_approval:
                total_seconds += 300.0  # 5 min approval overhead
        return round(total_seconds / 60.0, 2)

    # ------------------------------------------------------------------
    # detect_stale_runbooks
    # ------------------------------------------------------------------

    def detect_stale_runbooks(
        self, runbooks: list[RunbookV2], max_age_days: int = 90
    ) -> list[str]:
        """Return IDs of runbooks not tested within *max_age_days*."""
        stale_ids: list[str] = []
        for rb in runbooks:
            days = self._compute_staleness(rb)
            if days > max_age_days:
                stale_ids.append(rb.id)
        return stale_ids

    # ------------------------------------------------------------------
    # suggest_runbook
    # ------------------------------------------------------------------

    def suggest_runbook(
        self, graph: InfraGraph, failure_scenario: str
    ) -> RunbookV2:
        """Auto-generate a runbook skeleton for a failure scenario.

        The generated runbook follows a standard pattern:
        1. Diagnostic step
        2. Notification step
        3. Remediation step for each component
        4. Verification step
        5. Rollback step
        """
        steps: list[RunbookStep] = []
        step_num = 1

        component_ids = list(graph.components.keys())
        first_comp = component_ids[0] if component_ids else "unknown"

        # Step 1: Diagnostic.
        steps.append(
            RunbookStep(
                step_number=step_num,
                description=f"Diagnose {failure_scenario}",
                step_type=RunbookStepType.DIAGNOSTIC,
                target_component_id=first_comp,
                expected_outcome="Root cause identified",
                timeout_seconds=300.0,
                requires_approval=False,
            )
        )
        step_num += 1

        # Step 2: Notification.
        steps.append(
            RunbookStep(
                step_number=step_num,
                description="Notify on-call team",
                step_type=RunbookStepType.NOTIFICATION,
                target_component_id=first_comp,
                expected_outcome="Team notified",
                timeout_seconds=60.0,
                requires_approval=False,
            )
        )
        step_num += 1

        # Step 3+: Remediation per component.
        for comp_id in component_ids:
            comp = graph.get_component(comp_id)
            comp_name = comp.name if comp else comp_id
            steps.append(
                RunbookStep(
                    step_number=step_num,
                    description=f"Remediate {failure_scenario} on {comp_name}",
                    step_type=RunbookStepType.REMEDIATION,
                    target_component_id=comp_id,
                    expected_outcome=f"{comp_name} recovered",
                    timeout_seconds=600.0,
                    requires_approval=False,
                )
            )
            step_num += 1

        # Verification step.
        steps.append(
            RunbookStep(
                step_number=step_num,
                description="Verify system recovery",
                step_type=RunbookStepType.VERIFICATION,
                target_component_id=first_comp,
                expected_outcome="All components healthy",
                timeout_seconds=300.0,
                requires_approval=False,
            )
        )
        step_num += 1

        # Rollback step.
        steps.append(
            RunbookStep(
                step_number=step_num,
                description="Rollback if recovery failed",
                step_type=RunbookStepType.ROLLBACK,
                target_component_id=first_comp,
                expected_outcome="System rolled back to previous state",
                timeout_seconds=600.0,
                requires_approval=True,
            )
        )

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        return RunbookV2(
            id=f"auto-{failure_scenario.replace(' ', '-').lower()}",
            name=f"Runbook: {failure_scenario}",
            scenario=failure_scenario,
            steps=steps,
            last_tested=now_str,
            owner="auto-generated",
            severity="high",
        )

    # ------------------------------------------------------------------
    # validate_escalation_path
    # ------------------------------------------------------------------

    def validate_escalation_path(
        self, runbook: RunbookV2
    ) -> EscalationValidation:
        """Validate that escalation and notification steps are present and ordered."""
        escalation_steps: list[int] = []
        notification_steps: list[int] = []
        issues: list[str] = []

        for step in runbook.steps:
            if step.step_type == RunbookStepType.ESCALATION:
                escalation_steps.append(step.step_number)
            if step.step_type == RunbookStepType.NOTIFICATION:
                notification_steps.append(step.step_number)

        has_escalation = len(escalation_steps) > 0
        has_notification = len(notification_steps) > 0

        if not has_escalation:
            issues.append("No escalation step found.")
        if not has_notification:
            issues.append("No notification step found.")

        # Check that notification comes before escalation.
        if has_escalation and has_notification:
            first_notification = min(notification_steps)
            first_escalation = min(escalation_steps)
            if first_escalation < first_notification:
                issues.append(
                    "Escalation step occurs before notification step."
                )

        # Check escalation is not the first step.
        if has_escalation:
            first_step = min(s.step_number for s in runbook.steps) if runbook.steps else 0
            if min(escalation_steps) == first_step:
                issues.append(
                    "Escalation should not be the first step; "
                    "add diagnostic steps before escalating."
                )

        is_valid = len(issues) == 0

        return EscalationValidation(
            has_escalation=has_escalation,
            escalation_steps=escalation_steps,
            has_notification=has_notification,
            notification_steps=notification_steps,
            issues=issues,
            is_valid=is_valid,
        )

    # ------------------------------------------------------------------
    # compare_runbooks
    # ------------------------------------------------------------------

    def compare_runbooks(
        self, runbook_a: RunbookV2, runbook_b: RunbookV2
    ) -> RunbookComparison:
        """Compare two runbook versions and report differences."""
        differences: list[RunbookDiff] = []

        # Compare top-level fields.
        for field_name in ("name", "scenario", "owner", "severity", "last_tested"):
            val_a = getattr(runbook_a, field_name)
            val_b = getattr(runbook_b, field_name)
            if val_a != val_b:
                differences.append(
                    RunbookDiff(
                        field=field_name,
                        old_value=str(val_a),
                        new_value=str(val_b),
                    )
                )

        # Compare steps.
        steps_a = {s.step_number: s for s in runbook_a.steps}
        steps_b = {s.step_number: s for s in runbook_b.steps}

        all_step_nums = sorted(set(steps_a.keys()) | set(steps_b.keys()))
        steps_added: list[int] = []
        steps_removed: list[int] = []
        steps_modified: list[int] = []

        for sn in all_step_nums:
            if sn not in steps_a:
                steps_added.append(sn)
            elif sn not in steps_b:
                steps_removed.append(sn)
            else:
                sa = steps_a[sn]
                sb = steps_b[sn]
                if sa != sb:
                    steps_modified.append(sn)

        is_identical = (
            len(differences) == 0
            and len(steps_added) == 0
            and len(steps_removed) == 0
            and len(steps_modified) == 0
        )

        return RunbookComparison(
            runbook_a_id=runbook_a.id,
            runbook_b_id=runbook_b.id,
            differences=differences,
            steps_added=steps_added,
            steps_removed=steps_removed,
            steps_modified=steps_modified,
            is_identical=is_identical,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_step(
        self, graph: InfraGraph, step: RunbookStep
    ) -> StepValidation:
        """Validate a single runbook step against the graph."""
        comp = graph.get_component(step.target_component_id)

        if comp is None:
            return StepValidation(
                step_number=step.step_number,
                result=ValidationResult.MISSING_COMPONENT,
                reason=f"Component '{step.target_component_id}' not found in topology.",
                suggestion=f"Remove or update step targeting '{step.target_component_id}'.",
            )

        if step.timeout_seconds <= 0:
            return StepValidation(
                step_number=step.step_number,
                result=ValidationResult.INCORRECT,
                reason="Timeout must be positive.",
                suggestion="Set a positive timeout value.",
            )

        if step.timeout_seconds > 3600:
            return StepValidation(
                step_number=step.step_number,
                result=ValidationResult.UNTESTABLE,
                reason=f"Timeout of {step.timeout_seconds}s exceeds 1 hour; hard to test.",
                suggestion="Reduce timeout or split into smaller steps.",
            )

        if not step.description.strip():
            return StepValidation(
                step_number=step.step_number,
                result=ValidationResult.INCOMPLETE,
                reason="Step description is empty.",
                suggestion="Add a meaningful description.",
            )

        if not step.expected_outcome.strip():
            return StepValidation(
                step_number=step.step_number,
                result=ValidationResult.INCOMPLETE,
                reason="Expected outcome is empty.",
                suggestion="Describe the expected outcome.",
            )

        return StepValidation(
            step_number=step.step_number,
            result=ValidationResult.VALID,
            reason="Step is valid.",
            suggestion="",
        )

    def _compute_staleness(self, runbook: RunbookV2) -> int:
        """Compute days since the runbook was last tested."""
        if not runbook.last_tested:
            return 9999
        try:
            last = datetime.strptime(runbook.last_tested, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            now = datetime.now(timezone.utc)
            return max(0, (now - last).days)
        except ValueError:
            return 9999

    @staticmethod
    def _severity_from_dependents(num_dependents: int, is_spof: bool) -> str:
        """Derive severity string from dependent count and SPOF status."""
        if is_spof and num_dependents >= 2:
            return "critical"
        if is_spof or num_dependents >= 3:
            return "critical"
        if num_dependents >= 2:
            return "high"
        if num_dependents >= 1:
            return "medium"
        return "low"

    def _determine_overall(
        self,
        step_validations: list[StepValidation],
        staleness_days: int,
        runbook: RunbookV2,
    ) -> ValidationResult:
        """Determine the overall validation result."""
        if not step_validations:
            return ValidationResult.INCOMPLETE

        results = [sv.result for sv in step_validations]

        if ValidationResult.MISSING_COMPONENT in results:
            return ValidationResult.MISSING_COMPONENT

        if ValidationResult.INCORRECT in results:
            return ValidationResult.INCORRECT

        if staleness_days > 180:
            return ValidationResult.STALE

        if ValidationResult.UNTESTABLE in results:
            return ValidationResult.UNTESTABLE

        if ValidationResult.INCOMPLETE in results:
            return ValidationResult.INCOMPLETE

        if staleness_days > 90:
            return ValidationResult.STALE

        return ValidationResult.VALID
