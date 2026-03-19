"""Feature Flag Risk Analyzer.

Analyses feature flag configurations and their operational risks.
Detects stale flags, dependency chains, technical debt, flag conflicts,
rollback safety issues, evaluation performance impact, and missing
kill-switch coverage.  Produces cleanup recommendations and ownership
accountability mappings so teams can keep flag sprawl under control.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_STALE_THRESHOLD_DAYS = 30
_DEFAULT_LONG_LIVED_THRESHOLD_DAYS = 90
_MAX_FLAGS_BEFORE_LATENCY_WARN = 20
_MAX_FLAGS_BEFORE_LATENCY_CRITICAL = 50
_EVAL_OVERHEAD_PER_FLAG_MS = 0.5
_ROLLBACK_SAFE_SCORE = 80.0
_ROLLBACK_RISKY_SCORE = 50.0
_TECH_DEBT_LOW = 10.0
_TECH_DEBT_MEDIUM = 30.0
_TECH_DEBT_HIGH = 60.0
_COVERAGE_GOOD = 80.0
_COVERAGE_ACCEPTABLE = 50.0


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RiskFlagType(str, Enum):
    """Kind of feature flag."""

    RELEASE = "release"
    EXPERIMENT = "experiment"
    OPS = "ops"
    PERMISSION = "permission"
    KILL_SWITCH = "kill_switch"


class CleanupPriority(str, Enum):
    """How urgently a flag should be cleaned up."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class RollbackSafety(str, Enum):
    """Whether a flag can be safely turned off."""

    SAFE = "safe"
    RISKY = "risky"
    DANGEROUS = "dangerous"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class FlagDefinition(BaseModel):
    """A single feature flag definition with metadata for risk analysis."""

    id: str
    name: str
    flag_type: RiskFlagType
    enabled: bool = True
    rollout_percentage: float = Field(default=100.0, ge=0.0, le=100.0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_toggled_at: datetime | None = None
    owner: str = ""
    team: str = ""
    dependencies: list[str] = Field(default_factory=list)
    conflicts_with: list[str] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    code_references: int = 0
    has_unit_tests: bool = False
    description: str = ""


class StaleFlagResult(BaseModel):
    """A flag detected as stale."""

    flag_id: str
    days_since_toggle: int
    flag_type: RiskFlagType
    recommendation: str


class FlagDependencyResult(BaseModel):
    """A dependency relationship between flags."""

    flag_id: str
    depends_on: list[str] = Field(default_factory=list)
    depended_by: list[str] = Field(default_factory=list)
    circular: bool = False
    chain_depth: int = 0


class TechDebtResult(BaseModel):
    """Technical debt assessment for a flag."""

    flag_id: str
    age_days: int
    flag_type: RiskFlagType
    debt_score: float
    reasons: list[str] = Field(default_factory=list)
    cleanup_priority: CleanupPriority


class FlagCoverageResult(BaseModel):
    """Flag coverage analysis for components."""

    total_components: int
    flagged_components: int
    unflagged_components: list[str] = Field(default_factory=list)
    coverage_percent: float
    assessment: str


class RollbackSafetyResult(BaseModel):
    """Rollback safety analysis for a flag."""

    flag_id: str
    safety: RollbackSafety
    score: float
    dependent_flags: list[str] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class FlagConflictResult(BaseModel):
    """A detected conflict between flags."""

    flag_a_id: str
    flag_b_id: str
    conflict_type: str
    severity: str
    description: str
    resolution: str


class GradualRolloutRisk(BaseModel):
    """Risk assessment for a gradual rollout."""

    flag_id: str
    rollout_percentage: float
    risk_level: str
    affected_component_count: int
    recommendations: list[str] = Field(default_factory=list)


class EvalPerformanceResult(BaseModel):
    """Flag evaluation performance impact."""

    total_flags: int
    estimated_latency_ms: float
    status: str
    recommendations: list[str] = Field(default_factory=list)


class KillSwitchAuditResult(BaseModel):
    """Kill switch audit for critical paths."""

    total_components: int
    covered_components: list[str] = Field(default_factory=list)
    uncovered_components: list[str] = Field(default_factory=list)
    coverage_percent: float
    kill_switches: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class CleanupRecommendation(BaseModel):
    """A recommendation to clean up a flag."""

    flag_id: str
    priority: CleanupPriority
    reason: str
    action: str
    estimated_effort: str


class FlagOwnershipReport(BaseModel):
    """Ownership and accountability mapping."""

    total_flags: int
    owners: dict[str, list[str]] = Field(default_factory=dict)
    teams: dict[str, list[str]] = Field(default_factory=dict)
    unowned_flags: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class RiskAnalysisReport(BaseModel):
    """Complete risk analysis summary."""

    total_flags: int
    stale_flags: int
    high_debt_flags: int
    conflict_count: int
    kill_switch_coverage_percent: float
    overall_risk_score: float
    risk_level: str
    top_recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class FeatureFlagRiskAnalyzer:
    """Stateless engine that analyses feature flag configurations and their
    operational risks."""

    # -- public API ---------------------------------------------------------

    def detect_stale_flags(
        self,
        flags: list[FlagDefinition],
        threshold_days: int = _DEFAULT_STALE_THRESHOLD_DAYS,
        now: datetime | None = None,
    ) -> list[StaleFlagResult]:
        """Find flags that have not been toggled in *threshold_days*."""
        now = now or datetime.now(timezone.utc)
        results: list[StaleFlagResult] = []
        for flag in flags:
            ref_time = flag.last_toggled_at or flag.created_at
            days_since = (now - ref_time).days
            if days_since >= threshold_days:
                rec = self._stale_recommendation(flag, days_since)
                results.append(
                    StaleFlagResult(
                        flag_id=flag.id,
                        days_since_toggle=days_since,
                        flag_type=flag.flag_type,
                        recommendation=rec,
                    )
                )
        return results

    def analyze_dependencies(
        self,
        flags: list[FlagDefinition],
    ) -> list[FlagDependencyResult]:
        """Analyse dependency graph among flags.  Detects circular deps."""
        flag_map = {f.id: f for f in flags}
        results: list[FlagDependencyResult] = []

        for flag in flags:
            depends_on = [d for d in flag.dependencies if d in flag_map]
            depended_by = [
                f.id for f in flags if flag.id in f.dependencies
            ]
            circular = self._has_circular_dependency(flag.id, flag_map)
            chain_depth = self._dependency_chain_depth(flag.id, flag_map, set())
            results.append(
                FlagDependencyResult(
                    flag_id=flag.id,
                    depends_on=sorted(depends_on),
                    depended_by=sorted(depended_by),
                    circular=circular,
                    chain_depth=chain_depth,
                )
            )
        return results

    def calculate_tech_debt(
        self,
        flags: list[FlagDefinition],
        now: datetime | None = None,
    ) -> list[TechDebtResult]:
        """Score technical debt accumulated from long-lived flags."""
        now = now or datetime.now(timezone.utc)
        results: list[TechDebtResult] = []
        for flag in flags:
            age_days = (now - flag.created_at).days
            score, reasons = self._compute_debt_score(flag, age_days)
            priority = self._debt_to_priority(score)
            results.append(
                TechDebtResult(
                    flag_id=flag.id,
                    age_days=age_days,
                    flag_type=flag.flag_type,
                    debt_score=round(score, 2),
                    reasons=reasons,
                    cleanup_priority=priority,
                )
            )
        return results

    def analyze_coverage(
        self,
        graph: InfraGraph,
        flags: list[FlagDefinition],
    ) -> FlagCoverageResult:
        """Determine which code paths / components are covered by flags."""
        all_ids = set(graph.components.keys())
        flagged: set[str] = set()
        for flag in flags:
            for cid in flag.affected_components:
                if cid in all_ids:
                    flagged.add(cid)
        unflagged = sorted(all_ids - flagged)
        total = len(all_ids) if all_ids else 1
        pct = round(len(flagged) / total * 100, 2)
        assessment = self._coverage_assessment(pct)
        return FlagCoverageResult(
            total_components=len(all_ids),
            flagged_components=len(flagged),
            unflagged_components=unflagged,
            coverage_percent=pct,
            assessment=assessment,
        )

    def assess_rollback_safety(
        self,
        flags: list[FlagDefinition],
        graph: InfraGraph,
    ) -> list[RollbackSafetyResult]:
        """Score how safely each flag can be turned off."""
        {f.id: f for f in flags}
        results: list[RollbackSafetyResult] = []
        component_ids = set(graph.components.keys())

        for flag in flags:
            dependent_flags = [
                f.id for f in flags if flag.id in f.dependencies
            ]
            affected = [c for c in flag.affected_components if c in component_ids]
            score, reasons = self._compute_rollback_score(
                flag, dependent_flags, affected, graph
            )
            safety = self._classify_rollback(score)
            results.append(
                RollbackSafetyResult(
                    flag_id=flag.id,
                    safety=safety,
                    score=round(score, 2),
                    dependent_flags=sorted(dependent_flags),
                    affected_components=sorted(affected),
                    reasons=reasons,
                )
            )
        return results

    def detect_conflicts(
        self,
        flags: list[FlagDefinition],
    ) -> list[FlagConflictResult]:
        """Find mutually exclusive or conflicting flag pairs."""
        conflicts: list[FlagConflictResult] = []
        {f.id: f for f in flags}

        for i, fa in enumerate(flags):
            for fb in flags[i + 1:]:
                # Explicit mutual exclusion
                if fb.id in fa.conflicts_with or fa.id in fb.conflicts_with:
                    if fa.enabled and fb.enabled:
                        conflicts.append(
                            FlagConflictResult(
                                flag_a_id=fa.id,
                                flag_b_id=fb.id,
                                conflict_type="mutual_exclusion",
                                severity="critical",
                                description=(
                                    f"Flags {fa.id} and {fb.id} are mutually "
                                    f"exclusive but both enabled"
                                ),
                                resolution="Disable one of the conflicting flags",
                            )
                        )

                # Overlapping component coverage
                overlap = set(fa.affected_components) & set(fb.affected_components)
                if overlap and fa.enabled and fb.enabled:
                    if fa.flag_type == fb.flag_type == RiskFlagType.EXPERIMENT:
                        conflicts.append(
                            FlagConflictResult(
                                flag_a_id=fa.id,
                                flag_b_id=fb.id,
                                conflict_type="experiment_overlap",
                                severity="high",
                                description=(
                                    f"Experiments {fa.id} and {fb.id} overlap "
                                    f"on components: {sorted(overlap)}"
                                ),
                                resolution=(
                                    "Stagger experiments or exclude overlapping components"
                                ),
                            )
                        )

                # Dependency conflict — both depend on each other
                if fb.id in fa.dependencies and fa.id in fb.dependencies:
                    conflicts.append(
                        FlagConflictResult(
                            flag_a_id=fa.id,
                            flag_b_id=fb.id,
                            conflict_type="circular_dependency",
                            severity="critical",
                            description=(
                                f"Flags {fa.id} and {fb.id} have a circular dependency"
                            ),
                            resolution="Break the circular dependency between flags",
                        )
                    )
        return conflicts

    def assess_gradual_rollout_risk(
        self,
        flags: list[FlagDefinition],
        graph: InfraGraph,
    ) -> list[GradualRolloutRisk]:
        """Evaluate risk for flags with percentage-based rollouts."""
        results: list[GradualRolloutRisk] = []
        component_ids = set(graph.components.keys())

        for flag in flags:
            if flag.rollout_percentage >= 100.0 or not flag.enabled:
                continue
            affected_count = len(
                [c for c in flag.affected_components if c in component_ids]
            )
            risk_level, recs = self._assess_rollout(
                flag, affected_count, len(component_ids)
            )
            results.append(
                GradualRolloutRisk(
                    flag_id=flag.id,
                    rollout_percentage=flag.rollout_percentage,
                    risk_level=risk_level,
                    affected_component_count=affected_count,
                    recommendations=recs,
                )
            )
        return results

    def evaluate_performance_impact(
        self,
        flags: list[FlagDefinition],
    ) -> EvalPerformanceResult:
        """Estimate latency impact from evaluating too many flags."""
        active = [f for f in flags if f.enabled]
        total = len(active)
        latency = round(total * _EVAL_OVERHEAD_PER_FLAG_MS, 2)
        recs: list[str] = []

        if total >= _MAX_FLAGS_BEFORE_LATENCY_CRITICAL:
            status = "critical"
            recs.append(
                f"Active flag count ({total}) far exceeds recommended "
                f"maximum of {_MAX_FLAGS_BEFORE_LATENCY_WARN}; "
                f"estimated added latency {latency}ms"
            )
            recs.append("Archive unused flags and consolidate flag checks")
        elif total >= _MAX_FLAGS_BEFORE_LATENCY_WARN:
            status = "warning"
            recs.append(
                f"Active flag count ({total}) exceeds recommended "
                f"maximum of {_MAX_FLAGS_BEFORE_LATENCY_WARN}; "
                f"estimated added latency {latency}ms"
            )
            recs.append("Consider batching flag evaluations")
        else:
            status = "healthy"

        return EvalPerformanceResult(
            total_flags=total,
            estimated_latency_ms=latency,
            status=status,
            recommendations=recs,
        )

    def audit_kill_switches(
        self,
        graph: InfraGraph,
        flags: list[FlagDefinition],
    ) -> KillSwitchAuditResult:
        """Audit whether critical code paths have kill switches."""
        all_ids = set(graph.components.keys())
        kill_switches: list[str] = []
        covered: set[str] = set()

        for flag in flags:
            if flag.flag_type == RiskFlagType.KILL_SWITCH:
                kill_switches.append(flag.id)
                for cid in flag.affected_components:
                    if cid in all_ids:
                        covered.add(cid)

        uncovered = sorted(all_ids - covered)
        total = len(all_ids) if all_ids else 1
        pct = round(len(covered) / total * 100, 2)
        recs: list[str] = []
        if uncovered:
            recs.append(
                f"{len(uncovered)} component(s) lack kill-switch coverage: "
                f"{uncovered}"
            )
        if not kill_switches:
            recs.append("No kill switches defined; add kill switches for critical paths")

        return KillSwitchAuditResult(
            total_components=len(all_ids),
            covered_components=sorted(covered),
            uncovered_components=uncovered,
            coverage_percent=pct,
            kill_switches=sorted(kill_switches),
            recommendations=recs,
        )

    def generate_cleanup_recommendations(
        self,
        flags: list[FlagDefinition],
        now: datetime | None = None,
    ) -> list[CleanupRecommendation]:
        """Produce prioritised cleanup recommendations."""
        now = now or datetime.now(timezone.utc)
        recs: list[CleanupRecommendation] = []

        for flag in flags:
            age_days = (now - flag.created_at).days
            score, reasons = self._compute_debt_score(flag, age_days)
            priority = self._debt_to_priority(score)

            if priority == CleanupPriority.NONE:
                continue

            action = self._cleanup_action(flag, age_days)
            effort = self._estimate_cleanup_effort(flag)
            reason = "; ".join(reasons) if reasons else "General debt accumulation"

            recs.append(
                CleanupRecommendation(
                    flag_id=flag.id,
                    priority=priority,
                    reason=reason,
                    action=action,
                    estimated_effort=effort,
                )
            )

        recs.sort(key=lambda r: list(CleanupPriority).index(r.priority))
        return recs

    def map_ownership(
        self,
        flags: list[FlagDefinition],
    ) -> FlagOwnershipReport:
        """Map flag ownership and accountability."""
        owners: dict[str, list[str]] = {}
        teams: dict[str, list[str]] = {}
        unowned: list[str] = []
        recs: list[str] = []

        for flag in flags:
            if flag.owner:
                owners.setdefault(flag.owner, []).append(flag.id)
            else:
                unowned.append(flag.id)

            if flag.team:
                teams.setdefault(flag.team, []).append(flag.id)

        if unowned:
            recs.append(
                f"{len(unowned)} flag(s) have no assigned owner: {sorted(unowned)}"
            )

        # Detect overloaded owners
        for owner, fids in owners.items():
            if len(fids) > 10:
                recs.append(
                    f"Owner '{owner}' manages {len(fids)} flags; "
                    f"consider redistributing"
                )

        return FlagOwnershipReport(
            total_flags=len(flags),
            owners={k: sorted(v) for k, v in owners.items()},
            teams={k: sorted(v) for k, v in teams.items()},
            unowned_flags=sorted(unowned),
            recommendations=recs,
        )

    def generate_risk_report(
        self,
        graph: InfraGraph,
        flags: list[FlagDefinition],
        now: datetime | None = None,
    ) -> RiskAnalysisReport:
        """Produce an overall risk analysis report."""
        now = now or datetime.now(timezone.utc)

        stale = self.detect_stale_flags(flags, now=now)
        debts = self.calculate_tech_debt(flags, now=now)
        conflicts = self.detect_conflicts(flags)
        ks_audit = self.audit_kill_switches(graph, flags)
        perf = self.evaluate_performance_impact(flags)

        high_debt_count = sum(
            1 for d in debts if d.cleanup_priority in (
                CleanupPriority.CRITICAL, CleanupPriority.HIGH
            )
        )

        risk_score = self._compute_overall_risk(
            len(stale), high_debt_count, len(conflicts),
            ks_audit.coverage_percent, perf.status, len(flags),
        )
        risk_level = self._classify_risk_level(risk_score)

        top_recs: list[str] = []
        if stale:
            top_recs.append(
                f"Clean up {len(stale)} stale flag(s)"
            )
        if high_debt_count:
            top_recs.append(
                f"Address {high_debt_count} high-debt flag(s)"
            )
        if conflicts:
            top_recs.append(
                f"Resolve {len(conflicts)} flag conflict(s)"
            )
        if ks_audit.coverage_percent < _COVERAGE_GOOD:
            top_recs.append(
                f"Improve kill-switch coverage from "
                f"{ks_audit.coverage_percent}%"
            )
        top_recs.extend(perf.recommendations)

        return RiskAnalysisReport(
            total_flags=len(flags),
            stale_flags=len(stale),
            high_debt_flags=high_debt_count,
            conflict_count=len(conflicts),
            kill_switch_coverage_percent=ks_audit.coverage_percent,
            overall_risk_score=round(risk_score, 2),
            risk_level=risk_level,
            top_recommendations=top_recs,
        )

    # -- private helpers ----------------------------------------------------

    def _stale_recommendation(self, flag: FlagDefinition, days: int) -> str:
        if flag.flag_type == RiskFlagType.RELEASE and flag.enabled:
            return (
                f"Flag '{flag.id}' has been enabled for {days} days; "
                f"consider removing the flag and making the feature permanent"
            )
        if flag.flag_type == RiskFlagType.EXPERIMENT:
            return (
                f"Experiment '{flag.id}' has not been toggled in {days} days; "
                f"conclude the experiment and remove the flag"
            )
        if flag.flag_type == RiskFlagType.KILL_SWITCH:
            return (
                f"Kill switch '{flag.id}' idle for {days} days; "
                f"verify it still functions correctly"
            )
        return (
            f"Flag '{flag.id}' has not been toggled in {days} days; "
            f"review whether it is still needed"
        )

    def _has_circular_dependency(
        self, start_id: str, flag_map: dict[str, FlagDefinition]
    ) -> bool:
        visited: set[str] = set()
        stack: list[str] = [start_id]
        while stack:
            current = stack.pop()
            if current in visited:
                if current == start_id and len(visited) > 0:
                    return True
                continue
            visited.add(current)
            f = flag_map.get(current)
            if f:
                for dep_id in f.dependencies:
                    if dep_id == start_id and len(visited) > 1:
                        return True
                    if dep_id in flag_map:
                        stack.append(dep_id)
        return False

    def _dependency_chain_depth(
        self,
        flag_id: str,
        flag_map: dict[str, FlagDefinition],
        visited: set[str],
    ) -> int:
        if flag_id in visited or flag_id not in flag_map:
            return 0
        visited = visited | {flag_id}
        flag = flag_map[flag_id]
        if not flag.dependencies:
            return 0
        max_child = 0
        for dep_id in flag.dependencies:
            if dep_id in flag_map:
                child_depth = self._dependency_chain_depth(dep_id, flag_map, visited)
                max_child = max(max_child, child_depth)
        return 1 + max_child

    def _compute_debt_score(
        self, flag: FlagDefinition, age_days: int
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        # Age-based debt
        if age_days > _DEFAULT_LONG_LIVED_THRESHOLD_DAYS:
            age_penalty = min(40.0, (age_days - _DEFAULT_LONG_LIVED_THRESHOLD_DAYS) * 0.3)
            score += age_penalty
            reasons.append(
                f"Flag is {age_days} days old (long-lived threshold: "
                f"{_DEFAULT_LONG_LIVED_THRESHOLD_DAYS} days)"
            )

        # Release flags that are fully rolled out
        if (
            flag.flag_type == RiskFlagType.RELEASE
            and flag.enabled
            and flag.rollout_percentage >= 100.0
        ):
            score += 20.0
            reasons.append(
                "Release flag is fully rolled out; "
                "should be removed and code made permanent"
            )

        # Experiment flags that are enabled but old
        if flag.flag_type == RiskFlagType.EXPERIMENT and age_days > 30:
            score += 15.0
            reasons.append(
                "Experiment has been running for over 30 days; "
                "conclude and clean up"
            )

        # No tests
        if not flag.has_unit_tests and flag.code_references > 0:
            score += 10.0
            reasons.append("Flag has code references but no unit tests")

        # Many code references make removal harder
        if flag.code_references > 10:
            score += min(15.0, flag.code_references * 0.5)
            reasons.append(
                f"Flag referenced in {flag.code_references} places; "
                f"removal complexity is high"
            )

        return score, reasons

    def _debt_to_priority(self, score: float) -> CleanupPriority:
        if score >= _TECH_DEBT_HIGH:
            return CleanupPriority.CRITICAL
        if score >= _TECH_DEBT_MEDIUM:
            return CleanupPriority.HIGH
        if score >= _TECH_DEBT_LOW:
            return CleanupPriority.MEDIUM
        if score > 0:
            return CleanupPriority.LOW
        return CleanupPriority.NONE

    def _coverage_assessment(self, pct: float) -> str:
        if pct >= _COVERAGE_GOOD:
            return "good"
        if pct >= _COVERAGE_ACCEPTABLE:
            return "acceptable"
        return "poor"

    def _compute_rollback_score(
        self,
        flag: FlagDefinition,
        dependent_flags: list[str],
        affected: list[str],
        graph: InfraGraph,
    ) -> tuple[float, list[str]]:
        score = 100.0
        reasons: list[str] = []

        # Dependent flags reduce safety
        if dependent_flags:
            penalty = min(40.0, len(dependent_flags) * 15.0)
            score -= penalty
            reasons.append(
                f"{len(dependent_flags)} flag(s) depend on this flag"
            )

        # Many affected components reduce safety
        if len(affected) > 5:
            penalty = min(30.0, (len(affected) - 5) * 3.0)
            score -= penalty
            reasons.append(
                f"Flag affects {len(affected)} components"
            )

        # Kill switches should be safe to rollback
        if flag.flag_type == RiskFlagType.KILL_SWITCH:
            score = min(score + 10.0, 100.0)
            reasons.append("Kill switch rollback is inherently safer")

        # Experiments with partial rollout
        if (
            flag.flag_type == RiskFlagType.EXPERIMENT
            and flag.rollout_percentage < 100.0
        ):
            score = min(score + 5.0, 100.0)
            reasons.append("Partial rollout experiment; limited blast radius")

        # No tests makes rollback riskier
        if not flag.has_unit_tests:
            score -= 10.0
            reasons.append("No unit tests to verify rollback behavior")

        score = max(0.0, min(100.0, score))
        return score, reasons

    def _classify_rollback(self, score: float) -> RollbackSafety:
        if score >= _ROLLBACK_SAFE_SCORE:
            return RollbackSafety.SAFE
        if score >= _ROLLBACK_RISKY_SCORE:
            return RollbackSafety.RISKY
        return RollbackSafety.DANGEROUS

    def _assess_rollout(
        self,
        flag: FlagDefinition,
        affected_count: int,
        total_components: int,
    ) -> tuple[str, list[str]]:
        recs: list[str] = []
        risk_score = 0

        if flag.rollout_percentage < 5.0:
            risk_score += 1
            recs.append("Very low rollout; consider increasing if canary is healthy")
        elif flag.rollout_percentage > 75.0:
            risk_score += 2
            recs.append("High rollout percentage; monitor error rates closely")

        if affected_count > total_components * 0.5 and total_components > 0:
            risk_score += 2
            recs.append("Affects majority of components; use staged rollout")

        if flag.dependencies:
            risk_score += len(flag.dependencies)
            recs.append(
                f"Has {len(flag.dependencies)} dependency/ies; "
                f"verify all are enabled"
            )

        if not flag.has_unit_tests:
            risk_score += 1
            recs.append("No unit tests; add tests before wider rollout")

        if risk_score >= 4:
            return "high", recs
        if risk_score >= 2:
            return "medium", recs
        return "low", recs

    def _cleanup_action(self, flag: FlagDefinition, age_days: int) -> str:
        if (
            flag.flag_type == RiskFlagType.RELEASE
            and flag.enabled
            and flag.rollout_percentage >= 100.0
        ):
            return (
                f"Remove flag '{flag.id}' and make the feature permanent; "
                f"delete all {flag.code_references} code references"
            )
        if flag.flag_type == RiskFlagType.EXPERIMENT:
            return (
                f"Conclude experiment '{flag.id}'; "
                f"either graduate to release or remove"
            )
        if not flag.enabled and age_days > _DEFAULT_LONG_LIVED_THRESHOLD_DAYS:
            return (
                f"Flag '{flag.id}' has been disabled for {age_days} days; "
                f"remove the flag and dead code"
            )
        return f"Review flag '{flag.id}' and decide whether to keep or remove"

    def _estimate_cleanup_effort(self, flag: FlagDefinition) -> str:
        refs = flag.code_references
        if refs == 0:
            return "trivial"
        if refs <= 3:
            return "small"
        if refs <= 10:
            return "medium"
        return "large"

    def _compute_overall_risk(
        self,
        stale_count: int,
        high_debt_count: int,
        conflict_count: int,
        ks_coverage: float,
        perf_status: str,
        total_flags: int,
    ) -> float:
        if total_flags == 0:
            return 0.0

        score = 0.0

        # Stale flags
        stale_ratio = stale_count / total_flags
        score += stale_ratio * 25.0

        # High debt
        debt_ratio = high_debt_count / total_flags
        score += debt_ratio * 25.0

        # Conflicts
        score += min(25.0, conflict_count * 10.0)

        # Kill switch coverage gap
        coverage_gap = max(0.0, 100.0 - ks_coverage) / 100.0
        score += coverage_gap * 15.0

        # Performance
        if perf_status == "critical":
            score += 10.0
        elif perf_status == "warning":
            score += 5.0

        return min(100.0, score)

    def _classify_risk_level(self, score: float) -> str:
        if score >= 70.0:
            return "critical"
        if score >= 40.0:
            return "high"
        if score >= 20.0:
            return "medium"
        return "low"
