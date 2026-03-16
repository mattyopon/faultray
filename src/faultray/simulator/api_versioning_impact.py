"""API Versioning Impact Analyzer for FaultRay.

Analyzes the resilience impact of API versioning strategies across a
distributed infrastructure graph.  Features include:

- Track API versions per component (v1, v2, v3, etc.)
- Detect breaking changes between versions (field removals, type changes,
  endpoint deprecations)
- Analyze version compatibility matrix across dependent services
- Calculate migration cost/risk when upgrading API versions
- Identify version skew risks (when services run different versions)
- Support versioning strategies: URL path, header, query param,
  content negotiation
- Generate version deprecation timelines and sunset plans
- Assess backward compatibility scores

Usage:
    from faultray.simulator.api_versioning_impact import (
        ApiVersioningImpactEngine,
        ApiVersion,
        BreakingChange,
        VersioningStrategy,
    )
    engine = ApiVersioningImpactEngine()
    report = engine.generate_health_report(graph, versions, changes)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class VersioningStrategy(str, Enum):
    """Supported API versioning strategies."""

    URL_PATH = "url_path"
    HEADER = "header"
    QUERY_PARAM = "query_param"
    CONTENT_TYPE = "content_type"
    CONTENT_NEGOTIATION = "content_negotiation"
    CUSTOM = "custom"


class ChangeType(str, Enum):
    """Classification of a change between two API versions."""

    BREAKING = "breaking"
    NON_BREAKING = "non_breaking"
    DEPRECATION = "deprecation"
    REMOVAL = "removal"
    ADDITION = "addition"
    FIELD_TYPE_CHANGE = "field_type_change"
    ENDPOINT_RENAME = "endpoint_rename"
    AUTH_CHANGE = "auth_change"
    RATE_LIMIT_CHANGE = "rate_limit_change"
    PAGINATION_CHANGE = "pagination_change"


class CompatibilityLevel(str, Enum):
    """Pairwise compatibility between two API versions."""

    FULL = "full"
    BACKWARD = "backward"
    FORWARD = "forward"
    NONE = "none"


class SunsetPhase(str, Enum):
    """Lifecycle phase for an API version."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUNSET = "sunset"
    REMOVED = "removed"


class SkewSeverity(str, Enum):
    """Severity of version skew across dependent services."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class MigrationRiskLevel(str, Enum):
    """Overall risk level for a migration."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGLIGIBLE = "negligible"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class ApiVersion(BaseModel):
    """Represents a single API version for a component."""

    version: str
    component_id: str
    strategy: VersioningStrategy = VersioningStrategy.URL_PATH
    phase: SunsetPhase = SunsetPhase.ACTIVE
    release_date: str = ""
    deprecation_date: str = ""
    sunset_date: str = ""
    consumers: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)
    fields_spec: dict[str, str] = Field(default_factory=dict)
    supported_versions: list[str] = Field(default_factory=list)


class BreakingChange(BaseModel):
    """Describes a single breaking change between two API versions."""

    source_version: str
    target_version: str
    component_id: str
    change_type: ChangeType
    description: str
    affected_endpoints: list[str] = Field(default_factory=list)
    affected_field: str = ""
    risk_score: float = 0.0
    rollback_safe: bool = True
    migration_effort_hours: float = 1.0


class CompatibilityMatrix(BaseModel):
    """Version-to-version compatibility matrix for a component."""

    component_id: str
    versions: list[str] = Field(default_factory=list)
    matrix: dict[str, dict[str, CompatibilityLevel]] = Field(
        default_factory=dict
    )


class VersionSkewRisk(BaseModel):
    """Risk assessment when services run different API versions."""

    component_ids: list[str] = Field(default_factory=list)
    versions_in_use: dict[str, str] = Field(default_factory=dict)
    severity: SkewSeverity = SkewSeverity.NONE
    max_version_gap: int = 0
    description: str = ""
    affected_consumers: list[str] = Field(default_factory=list)


class MigrationRisk(BaseModel):
    """Risk assessment for migrating a single consumer between API versions."""

    consumer_id: str
    source_version: str
    target_version: str
    risk_score: float = 0.0
    breaking_changes_count: int = 0
    affected_endpoints_count: int = 0
    estimated_effort_hours: float = 0.0
    migration_steps: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    risk_level: MigrationRiskLevel = MigrationRiskLevel.LOW


class SunsetPolicy(BaseModel):
    """Sunset policy configuration and enforcement status."""

    component_id: str
    version: str
    phase: SunsetPhase
    deprecation_date: str = ""
    sunset_date: str = ""
    removal_date: str = ""
    grace_period_days: int = 90
    active_consumers: int = 0
    migration_complete_percent: float = 0.0
    violations: list[str] = Field(default_factory=list)


class SunsetImpact(BaseModel):
    """Impact assessment of sunsetting an API version."""

    component_id: str
    version: str
    affected_consumers: list[str] = Field(default_factory=list)
    total_consumers: int = 0
    consumers_migrated: int = 0
    migration_percent: float = 0.0
    blocking_issues: list[str] = Field(default_factory=list)
    estimated_outage_risk: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class SunsetPlanEntry(BaseModel):
    """An entry in the deprecation timeline."""

    component_id: str
    version: str
    current_status: SunsetPhase
    recommended_action: str
    deadline: str = ""
    consumers_affected: int = 0
    days_until_sunset: int | None = None


class SunsetPlan(BaseModel):
    """Complete deprecation timeline and sunset plan."""

    entries: list[SunsetPlanEntry] = Field(default_factory=list)
    total_versions_to_sunset: int = 0
    total_consumers_affected: int = 0


class MigrationPlan(BaseModel):
    """Step-by-step plan for migrating consumers to a new API version."""

    component_id: str
    source_version: str
    target_version: str
    total_consumers: int = 0
    migration_risks: list[MigrationRisk] = Field(default_factory=list)
    overall_risk_score: float = 0.0
    overall_risk_level: MigrationRiskLevel = MigrationRiskLevel.LOW
    estimated_total_effort_hours: float = 0.0
    estimated_downtime_minutes: float = 0.0
    parallel_possible: bool = False
    phases: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class StrategyConsistencyReport(BaseModel):
    """Report on versioning strategy consistency across components."""

    consistent: bool = True
    strategy_counts: dict[str, int] = Field(default_factory=dict)
    dominant_strategy: str | None = None
    outliers: list[str] = Field(default_factory=list)
    total_components: int = 0


class VersionHealthReport(BaseModel):
    """Comprehensive health report for all API versions."""

    versions: list[ApiVersion] = Field(default_factory=list)
    breaking_changes: list[BreakingChange] = Field(default_factory=list)
    compatibility_matrices: list[CompatibilityMatrix] = Field(
        default_factory=list
    )
    skew_risks: list[VersionSkewRisk] = Field(default_factory=list)
    sunset_policies: list[SunsetPolicy] = Field(default_factory=list)
    sunset_impacts: list[SunsetImpact] = Field(default_factory=list)
    sunset_plan: SunsetPlan | None = None
    migration_plans: list[MigrationPlan] = Field(default_factory=list)
    strategy_consistency: StrategyConsistencyReport | None = None
    overall_versioning_health: float = 0.0
    backward_compatibility_score: float = 1.0
    total_breaking_changes: int = 0
    deprecated_versions_count: int = 0
    at_risk_consumers: int = 0
    recommendations: list[str] = Field(default_factory=list)
    component_version_map: dict[str, list[str]] = Field(
        default_factory=dict
    )


# ---------------------------------------------------------------------------
# Severity / risk mapping tables
# ---------------------------------------------------------------------------

_CHANGE_TYPE_RISK: dict[ChangeType, float] = {
    ChangeType.BREAKING: 10.0,
    ChangeType.REMOVAL: 8.0,
    ChangeType.DEPRECATION: 4.0,
    ChangeType.NON_BREAKING: 1.0,
    ChangeType.ADDITION: 0.5,
    ChangeType.FIELD_TYPE_CHANGE: 7.0,
    ChangeType.ENDPOINT_RENAME: 6.0,
    ChangeType.AUTH_CHANGE: 9.0,
    ChangeType.RATE_LIMIT_CHANGE: 3.0,
    ChangeType.PAGINATION_CHANGE: 4.0,
}

_STRATEGY_COMPLEXITY: dict[VersioningStrategy, float] = {
    VersioningStrategy.URL_PATH: 1.0,
    VersioningStrategy.HEADER: 1.5,
    VersioningStrategy.QUERY_PARAM: 1.2,
    VersioningStrategy.CONTENT_TYPE: 2.0,
    VersioningStrategy.CONTENT_NEGOTIATION: 2.0,
    VersioningStrategy.CUSTOM: 2.5,
}

_PHASE_RISK_MULTIPLIER: dict[SunsetPhase, float] = {
    SunsetPhase.ACTIVE: 0.0,
    SunsetPhase.DEPRECATED: 1.0,
    SunsetPhase.SUNSET: 2.0,
    SunsetPhase.REMOVED: 5.0,
}

_COMPATIBILITY_SCORE: dict[CompatibilityLevel, float] = {
    CompatibilityLevel.FULL: 1.0,
    CompatibilityLevel.BACKWARD: 0.7,
    CompatibilityLevel.FORWARD: 0.5,
    CompatibilityLevel.NONE: 0.0,
}

_EFFORT_PER_BREAKING_CHANGE: float = 4.0
_EFFORT_PER_ENDPOINT: float = 1.0
_MAX_RISK_SCORE: float = 100.0
_BREAKING_TYPES: frozenset[ChangeType] = frozenset({
    ChangeType.BREAKING,
    ChangeType.REMOVAL,
    ChangeType.FIELD_TYPE_CHANGE,
    ChangeType.AUTH_CHANGE,
})


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _change_id(change: BreakingChange) -> str:
    """Deterministic identifier for a breaking change."""
    raw = (
        f"{change.component_id}:{change.source_version}:"
        f"{change.target_version}:{change.change_type.value}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _compute_change_risk(
    change_type: ChangeType,
    num_affected_endpoints: int,
    num_consumers: int,
    strategy: VersioningStrategy,
) -> float:
    """Compute risk score for a single change."""
    base = _CHANGE_TYPE_RISK.get(change_type, 1.0)
    endpoint_factor = max(1.0, num_affected_endpoints * 0.5)
    consumer_factor = max(1.0, num_consumers * 0.3)
    complexity = _STRATEGY_COMPLEXITY.get(strategy, 1.0)
    score = base * endpoint_factor * consumer_factor * complexity
    return min(_MAX_RISK_SCORE, round(score, 2))


def _days_until(date_str: str) -> int | None:
    """Return number of days from now until *date_str* (ISO-8601), or None."""
    if not date_str:
        return None
    try:
        target = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = (target - now).days
        return delta
    except (ValueError, TypeError):
        return None


def _version_sort_key(v: str) -> tuple:
    """Sort key that handles numeric segments so v2 < v10."""
    parts: list[int | str] = []
    segment = ""
    for ch in v:
        if ch.isdigit():
            segment += ch
        else:
            if segment:
                parts.append(int(segment))
                segment = ""
            parts.append(ch)
    if segment:
        parts.append(int(segment))
    return tuple(0 if isinstance(p, int) else 1 for p in parts), tuple(parts)


def parse_version_number(version_str: str) -> tuple[int, ...]:
    """Extract numeric version components from a version string.

    Handles formats like ``v1``, ``v2.1``, ``1.2.3``, ``v1.0.0-beta``.
    """
    if not version_str:
        return (0,)
    import re

    cleaned = version_str.lstrip("vV").strip()
    cleaned = re.split(r"[-+]", cleaned)[0]
    parts = cleaned.split(".")
    result: list[int] = []
    for p in parts:
        digits = re.match(r"(\d+)", p)
        if digits:
            result.append(int(digits.group(1)))
    return tuple(result) if result else (0,)


def version_distance(v1: str, v2: str) -> int:
    """Calculate the distance between two versions as an integer.

    Major differences are weighted more heavily than minor/patch.
    """
    t1 = parse_version_number(v1)
    t2 = parse_version_number(v2)
    max_len = max(len(t1), len(t2))
    t1p = t1 + (0,) * (max_len - len(t1))
    t2p = t2 + (0,) * (max_len - len(t2))
    weights = [100 ** (max_len - 1 - i) for i in range(max_len)]
    return sum(abs(t1p[i] - t2p[i]) * weights[i] for i in range(max_len))


def classify_skew_severity(version_gap: int) -> SkewSeverity:
    """Classify the severity of version skew based on gap magnitude."""
    if version_gap <= 0:
        return SkewSeverity.NONE
    if version_gap == 1:
        return SkewSeverity.LOW
    if version_gap == 2:
        return SkewSeverity.MEDIUM
    if version_gap == 3:
        return SkewSeverity.HIGH
    return SkewSeverity.CRITICAL


def classify_migration_risk_level(
    breaking_count: int,
    effort_hours: float,
    rollback_safe: bool,
) -> MigrationRiskLevel:
    """Classify the risk level of a migration step."""
    if breaking_count == 0 and effort_hours < 2.0:
        return MigrationRiskLevel.NEGLIGIBLE
    if not rollback_safe and breaking_count >= 3:
        return MigrationRiskLevel.CRITICAL
    if not rollback_safe or breaking_count >= 3:
        return MigrationRiskLevel.HIGH
    if breaking_count >= 1 or effort_hours >= 4.0:
        return MigrationRiskLevel.MEDIUM
    return MigrationRiskLevel.LOW


def compute_breaking_change_score(changes: list[BreakingChange]) -> float:
    """Compute a 0.0-1.0 score representing breaking-change severity.

    1.0 means no breaking changes; 0.0 means severe breakage.
    """
    if not changes:
        return 1.0
    severity_map: dict[ChangeType, float] = {
        ChangeType.BREAKING: 0.20,
        ChangeType.REMOVAL: 0.20,
        ChangeType.FIELD_TYPE_CHANGE: 0.15,
        ChangeType.AUTH_CHANGE: 0.18,
        ChangeType.ENDPOINT_RENAME: 0.10,
        ChangeType.DEPRECATION: 0.05,
        ChangeType.RATE_LIMIT_CHANGE: 0.05,
        ChangeType.PAGINATION_CHANGE: 0.07,
        ChangeType.NON_BREAKING: 0.01,
        ChangeType.ADDITION: 0.01,
    }
    total_penalty = sum(
        severity_map.get(c.change_type, 0.10) for c in changes
    )
    return max(0.0, 1.0 - min(total_penalty, 1.0))


def _aggregate_risk(levels: list[MigrationRiskLevel]) -> MigrationRiskLevel:
    """Determine the overall risk from a collection of step risks."""
    if not levels:
        return MigrationRiskLevel.LOW
    order = [
        MigrationRiskLevel.NEGLIGIBLE,
        MigrationRiskLevel.LOW,
        MigrationRiskLevel.MEDIUM,
        MigrationRiskLevel.HIGH,
        MigrationRiskLevel.CRITICAL,
    ]
    max_idx = max(order.index(lev) for lev in levels)
    return order[max_idx]


def _estimate_downtime_minutes(risks: list[MigrationRisk]) -> float:
    """Estimate total downtime in minutes based on migration risks."""
    total = 0.0
    for risk in risks:
        base = risk.estimated_effort_hours * 2.0
        if risk.risk_level in (
            MigrationRiskLevel.HIGH,
            MigrationRiskLevel.CRITICAL,
        ):
            base *= 3.0
        base += risk.breaking_changes_count * 5.0
        total += base
    return round(total, 1)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ApiVersioningImpactEngine:
    """Stateless engine for analysing API versioning resilience impact.

    All methods are pure functions on their arguments -- no internal state
    is mutated across calls.
    """

    # ------------------------------------------------------------------
    # Breaking-change analysis
    # ------------------------------------------------------------------

    def analyze_breaking_changes(
        self,
        graph: InfraGraph,
        versions: list[ApiVersion],
        changes: list[BreakingChange],
    ) -> list[BreakingChange]:
        """Analyse and score breaking changes across the infrastructure.

        Each :class:`BreakingChange` in *changes* is enriched with a computed
        ``risk_score`` that reflects the number of affected endpoints, the
        number of consumers of the source version, and the versioning-strategy
        complexity.

        Returns a list sorted by ``risk_score`` descending.
        """
        scored: list[BreakingChange] = []
        version_map = self._build_version_map(versions)

        for change in changes:
            source_v = version_map.get(
                (change.component_id, change.source_version)
            )
            num_consumers = len(source_v.consumers) if source_v else 0
            strategy = (
                source_v.strategy
                if source_v
                else VersioningStrategy.URL_PATH
            )
            risk = _compute_change_risk(
                change.change_type,
                len(change.affected_endpoints),
                num_consumers,
                strategy,
            )
            scored.append(change.model_copy(update={"risk_score": risk}))

        scored.sort(key=lambda c: c.risk_score, reverse=True)
        return scored

    # ------------------------------------------------------------------
    # Compatibility matrix
    # ------------------------------------------------------------------

    def compute_compatibility_matrix(
        self,
        versions: list[ApiVersion],
        changes: list[BreakingChange],
    ) -> list[CompatibilityMatrix]:
        """Build version compatibility matrices grouped by component.

        For each component that has versions, computes a mapping of
        ``{ver_a: {ver_b: CompatibilityLevel, ...}, ...}``.
        """
        by_component: dict[str, list[ApiVersion]] = {}
        for v in versions:
            by_component.setdefault(v.component_id, []).append(v)

        changes_by_comp: dict[str, list[BreakingChange]] = {}
        for c in changes:
            changes_by_comp.setdefault(c.component_id, []).append(c)

        matrices: list[CompatibilityMatrix] = []
        for comp_id, comp_versions in sorted(by_component.items()):
            ver_ids = sorted(
                [v.version for v in comp_versions], key=_version_sort_key
            )
            matrix: dict[str, dict[str, CompatibilityLevel]] = {}
            comp_changes = changes_by_comp.get(comp_id, [])

            for va in ver_ids:
                matrix[va] = {}
                for vb in ver_ids:
                    if va == vb:
                        matrix[va][vb] = CompatibilityLevel.FULL
                        continue
                    matrix[va][vb] = self._determine_compatibility(
                        va, vb, comp_changes
                    )

            matrices.append(
                CompatibilityMatrix(
                    component_id=comp_id,
                    versions=ver_ids,
                    matrix=matrix,
                )
            )

        return matrices

    # ------------------------------------------------------------------
    # Sunset policy evaluation
    # ------------------------------------------------------------------

    def evaluate_sunset_policies(
        self,
        versions: list[ApiVersion],
        policies: list[SunsetPolicy] | None = None,
    ) -> list[SunsetPolicy]:
        """Evaluate sunset policies for all versions and detect violations.

        If *policies* is ``None``, default policies are generated from the
        version metadata.
        """
        if policies is None:
            policies = self._generate_default_policies(versions)

        evaluated: list[SunsetPolicy] = []
        version_map = self._build_version_map(versions)

        for policy in policies:
            violations: list[str] = list(policy.violations)
            api_ver = version_map.get(
                (policy.component_id, policy.version)
            )

            if api_ver:
                active_consumers = len(api_ver.consumers)
            else:
                active_consumers = policy.active_consumers

            # Deprecated/sunset version still has consumers
            if policy.phase in (SunsetPhase.DEPRECATED, SunsetPhase.SUNSET):
                if active_consumers > 0:
                    violations.append(
                        f"{active_consumers} consumer(s) still using "
                        f"deprecated version {policy.version}"
                    )

            # Check if sunset date has passed
            if policy.sunset_date:
                days_left = _days_until(policy.sunset_date)
                if days_left is not None and days_left < 0:
                    if active_consumers > 0:
                        violations.append(
                            f"Sunset date passed {abs(days_left)} day(s) ago "
                            f"but {active_consumers} consumer(s) remain"
                        )
                elif (
                    days_left is not None
                    and days_left < policy.grace_period_days
                ):
                    if policy.migration_complete_percent < 100.0:
                        violations.append(
                            f"Only {days_left} day(s) until sunset but "
                            f"migration is {policy.migration_complete_percent:.0f}% complete"
                        )

            # Removed phase
            if policy.phase == SunsetPhase.REMOVED and active_consumers > 0:
                violations.append(
                    f"Version {policy.version} is REMOVED but "
                    f"{active_consumers} consumer(s) still reference it"
                )

            migration_pct = policy.migration_complete_percent
            if api_ver and api_ver.consumers:
                total = len(api_ver.consumers)
                if total > 0 and active_consumers < total:
                    migration_pct = (
                        (total - active_consumers) / total
                    ) * 100.0

            evaluated.append(
                policy.model_copy(
                    update={
                        "violations": violations,
                        "active_consumers": active_consumers,
                        "migration_complete_percent": round(
                            migration_pct, 1
                        ),
                    }
                )
            )

        return evaluated

    # ------------------------------------------------------------------
    # Sunset impact simulation
    # ------------------------------------------------------------------

    def simulate_sunset_impact(
        self,
        graph: InfraGraph,
        versions: list[ApiVersion],
        component_id: str,
        version: str,
    ) -> SunsetImpact:
        """Simulate the impact of sunsetting a specific API version.

        Examines consumers, graph dependencies, and produces an outage risk
        estimate together with recommendations.
        """
        version_map = self._build_version_map(versions)
        api_ver = version_map.get((component_id, version))

        affected_consumers: list[str] = []
        if api_ver:
            affected_consumers = list(api_ver.consumers)

        # Check dependent components in the graph
        if component_id in graph.components:
            dependents = graph.get_dependents(component_id)
        else:
            dependents = []
        for dep in dependents:
            if dep.id not in affected_consumers:
                affected_consumers.append(dep.id)

        total = len(affected_consumers)
        migrated = 0
        newer_versions = self._find_newer_versions(
            versions, component_id, version
        )
        newer_consumer_ids: set[str] = set()
        for nv in newer_versions:
            newer_consumer_ids.update(nv.consumers)

        for cid in affected_consumers:
            if cid in newer_consumer_ids:
                migrated += 1

        migration_pct = (migrated / total * 100.0) if total > 0 else 100.0
        not_migrated = total - migrated

        blocking: list[str] = []
        if not_migrated > 0:
            blocking.append(
                f"{not_migrated} consumer(s) have not migrated"
            )
        if api_ver and api_ver.phase == SunsetPhase.ACTIVE:
            blocking.append(
                "Version is still in ACTIVE phase — deprecate first"
            )

        outage_risk = 0.0
        if total > 0:
            outage_risk = min(1.0, not_migrated / total)
        if api_ver and api_ver.phase == SunsetPhase.ACTIVE:
            outage_risk = min(1.0, outage_risk + 0.3)

        recommendations = self._sunset_recommendations(
            api_ver, not_migrated, total, migration_pct
        )

        return SunsetImpact(
            component_id=component_id,
            version=version,
            affected_consumers=affected_consumers,
            total_consumers=total,
            consumers_migrated=migrated,
            migration_percent=round(migration_pct, 1),
            blocking_issues=blocking,
            estimated_outage_risk=round(outage_risk, 3),
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Version skew detection
    # ------------------------------------------------------------------

    def detect_version_skew(
        self,
        graph: InfraGraph,
        versions: list[ApiVersion],
    ) -> list[VersionSkewRisk]:
        """Detect version skew risks across the infrastructure graph.

        Version skew occurs when interconnected services use different API
        versions, potentially causing compatibility issues.
        """
        # Build per-component active version map
        active_map: dict[str, str] = {}
        for v in versions:
            if v.phase == SunsetPhase.ACTIVE:
                prev = active_map.get(v.component_id)
                if prev is None or _version_sort_key(
                    v.version
                ) > _version_sort_key(prev):
                    active_map[v.component_id] = v.version

        risks: list[VersionSkewRisk] = []
        clusters = self._find_version_clusters(graph, active_map)

        for cluster_ids in clusters:
            versions_in_cluster: dict[str, str] = {}
            for cid in cluster_ids:
                ver = active_map.get(cid)
                if ver:
                    versions_in_cluster[cid] = ver

            if len(versions_in_cluster) < 2:
                continue

            unique_versions = set(versions_in_cluster.values())
            if len(unique_versions) <= 1:
                continue

            version_strings = list(versions_in_cluster.values())
            max_gap = 0
            for i in range(len(version_strings)):
                for j in range(i + 1, len(version_strings)):
                    gap = version_distance(
                        version_strings[i], version_strings[j]
                    )
                    max_gap = max(max_gap, gap)

            severity = classify_skew_severity(max_gap)

            affected_consumers: list[str] = []
            for cid in cluster_ids:
                for dep_comp in graph.get_dependents(cid):
                    if dep_comp.id not in affected_consumers:
                        affected_consumers.append(dep_comp.id)

            risks.append(
                VersionSkewRisk(
                    component_ids=sorted(cluster_ids),
                    versions_in_use=versions_in_cluster,
                    severity=severity,
                    max_version_gap=max_gap,
                    description=(
                        f"Version skew detected across "
                        f"{len(cluster_ids)} components: "
                        f"{len(unique_versions)} different versions "
                        f"in use (gap={max_gap})"
                    ),
                    affected_consumers=affected_consumers,
                )
            )

        return risks

    # ------------------------------------------------------------------
    # Migration planning
    # ------------------------------------------------------------------

    def generate_migration_plan(
        self,
        graph: InfraGraph,
        versions: list[ApiVersion],
        changes: list[BreakingChange],
        component_id: str,
        source_version: str,
        target_version: str,
    ) -> MigrationPlan:
        """Generate a migration plan for consumers moving between versions.

        Assesses risk for each consumer, orders migration phases, and produces
        overall effort estimates.
        """
        version_map = self._build_version_map(versions)
        source_v = version_map.get((component_id, source_version))
        consumers = source_v.consumers if source_v else []

        relevant_changes = [
            c
            for c in changes
            if c.component_id == component_id
            and c.source_version == source_version
            and c.target_version == target_version
        ]
        breaking_count = sum(
            1
            for c in relevant_changes
            if c.change_type in _BREAKING_TYPES
        )
        all_rollback_safe = (
            all(c.rollback_safe for c in relevant_changes)
            if relevant_changes
            else True
        )

        migration_risks: list[MigrationRisk] = []
        total_effort = 0.0

        for cid in consumers:
            affected_ep_count = sum(
                len(c.affected_endpoints) for c in relevant_changes
            )
            effort = (
                breaking_count * _EFFORT_PER_BREAKING_CHANGE
                + affected_ep_count * _EFFORT_PER_ENDPOINT
            )
            strategy = (
                source_v.strategy
                if source_v
                else VersioningStrategy.URL_PATH
            )
            risk_score = _compute_change_risk(
                (
                    ChangeType.BREAKING
                    if breaking_count > 0
                    else ChangeType.NON_BREAKING
                ),
                affected_ep_count,
                1,
                strategy,
            )

            risk_factors: list[str] = []
            if breaking_count > 0:
                risk_factors.append(f"{breaking_count} breaking change(s)")
            if affected_ep_count > 5:
                risk_factors.append(
                    f"{affected_ep_count} endpoints affected"
                )

            dep_comp = graph.get_component(cid)
            if dep_comp and dep_comp.type == ComponentType.EXTERNAL_API:
                risk_factors.append(
                    "Consumer is an external API — coordination required"
                )
                effort *= 1.5

            steps = self._migration_steps(
                source_version, target_version, breaking_count
            )
            risk_level = classify_migration_risk_level(
                breaking_count, effort, all_rollback_safe
            )

            migration_risks.append(
                MigrationRisk(
                    consumer_id=cid,
                    source_version=source_version,
                    target_version=target_version,
                    risk_score=round(risk_score, 2),
                    breaking_changes_count=breaking_count,
                    affected_endpoints_count=affected_ep_count,
                    estimated_effort_hours=round(effort, 1),
                    migration_steps=steps,
                    risk_factors=risk_factors,
                    risk_level=risk_level,
                )
            )
            total_effort += effort

        migration_risks.sort(key=lambda r: r.risk_score, reverse=True)
        overall_risk = (
            sum(r.risk_score for r in migration_risks)
            / len(migration_risks)
            if migration_risks
            else 0.0
        )
        overall_level = _aggregate_risk(
            [r.risk_level for r in migration_risks]
        )
        downtime = _estimate_downtime_minutes(migration_risks)

        # Can parallelize if consumers are independent
        parallel_possible = len(consumers) > 1 and breaking_count == 0

        phases = self._migration_phases(len(consumers), breaking_count)
        recommendations = self._migration_recommendations(
            migration_risks, breaking_count, len(consumers)
        )

        return MigrationPlan(
            component_id=component_id,
            source_version=source_version,
            target_version=target_version,
            total_consumers=len(consumers),
            migration_risks=migration_risks,
            overall_risk_score=round(overall_risk, 2),
            overall_risk_level=overall_level,
            estimated_total_effort_hours=round(total_effort, 1),
            estimated_downtime_minutes=downtime,
            parallel_possible=parallel_possible,
            phases=phases,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Sunset plan generation
    # ------------------------------------------------------------------

    def generate_sunset_plan(
        self,
        versions: list[ApiVersion],
    ) -> SunsetPlan:
        """Generate a deprecation timeline and sunset plan."""
        entries: list[SunsetPlanEntry] = []
        total_consumers = 0

        for v in versions:
            if v.phase not in (SunsetPhase.DEPRECATED, SunsetPhase.SUNSET):
                continue

            days_until = None
            if v.sunset_date:
                days_until = _days_until(v.sunset_date)

            if v.phase == SunsetPhase.DEPRECATED:
                action = (
                    f"Migrate consumers from {v.version} to "
                    f"latest active version"
                )
            else:
                action = (
                    f"Urgently migrate off {v.version} — sunset imminent"
                )

            consumers_count = len(v.consumers)
            total_consumers += consumers_count

            entries.append(
                SunsetPlanEntry(
                    component_id=v.component_id,
                    version=v.version,
                    current_status=v.phase,
                    recommended_action=action,
                    deadline=v.sunset_date,
                    consumers_affected=consumers_count,
                    days_until_sunset=days_until,
                )
            )

        # Sort by urgency
        def sort_key(e: SunsetPlanEntry) -> tuple[int, int]:
            status_order = (
                0 if e.current_status == SunsetPhase.SUNSET else 1
            )
            days = (
                e.days_until_sunset
                if e.days_until_sunset is not None
                else 999999
            )
            return (status_order, days)

        entries.sort(key=sort_key)

        return SunsetPlan(
            entries=entries,
            total_versions_to_sunset=len(entries),
            total_consumers_affected=total_consumers,
        )

    # ------------------------------------------------------------------
    # Strategy consistency
    # ------------------------------------------------------------------

    def analyze_strategy_consistency(
        self,
        versions: list[ApiVersion],
    ) -> StrategyConsistencyReport:
        """Analyze consistency of versioning strategies across components."""
        strategy_counts: dict[str, int] = {}
        component_strategies: dict[str, VersioningStrategy] = {}

        for v in versions:
            # Use latest version's strategy per component
            existing = component_strategies.get(v.component_id)
            if existing is None or _version_sort_key(
                v.version
            ) > _version_sort_key(""):
                component_strategies[v.component_id] = v.strategy

        for strat in component_strategies.values():
            strategy_counts[strat.value] = (
                strategy_counts.get(strat.value, 0) + 1
            )

        unique_strategies = set(component_strategies.values())
        consistent = len(unique_strategies) <= 1

        dominant_strategy = None
        if strategy_counts:
            dominant_strategy = max(
                strategy_counts, key=lambda k: strategy_counts[k]
            )

        outliers: list[str] = []
        if dominant_strategy and not consistent:
            for cid, strat in component_strategies.items():
                if strat.value != dominant_strategy:
                    outliers.append(cid)

        return StrategyConsistencyReport(
            consistent=consistent,
            strategy_counts=strategy_counts,
            dominant_strategy=dominant_strategy,
            outliers=sorted(outliers),
            total_components=len(component_strategies),
        )

    # ------------------------------------------------------------------
    # Backward compatibility score
    # ------------------------------------------------------------------

    def compute_backward_compatibility_score(
        self,
        graph: InfraGraph,
        versions: list[ApiVersion],
        changes: list[BreakingChange],
    ) -> float:
        """Compute an overall backward compatibility score (0.0-1.0).

        Evaluates breaking changes on dependency edges and strategy
        consistency.
        """
        edges = graph.all_dependency_edges()
        if not edges:
            return 1.0

        active_map: dict[str, str] = {}
        for v in versions:
            if v.phase == SunsetPhase.ACTIVE:
                prev = active_map.get(v.component_id)
                if prev is None or _version_sort_key(
                    v.version
                ) > _version_sort_key(prev):
                    active_map[v.component_id] = v.version

        scores: list[float] = []

        for dep in edges:
            src_ver = active_map.get(dep.source_id)
            tgt_ver = active_map.get(dep.target_id)
            if src_ver is None or tgt_ver is None:
                continue

            if src_ver == tgt_ver:
                scores.append(1.0)
                continue

            # Collect breaking changes between the two versions
            relevant = [
                c
                for c in changes
                if c.component_id == dep.target_id
                and (
                    (
                        c.source_version == src_ver
                        and c.target_version == tgt_ver
                    )
                    or (
                        c.source_version == tgt_ver
                        and c.target_version == src_ver
                    )
                )
            ]
            if relevant:
                scores.append(compute_breaking_change_score(relevant))
            else:
                # Versions differ but no explicit breaking changes recorded
                gap = version_distance(src_ver, tgt_ver)
                if gap == 0:
                    scores.append(1.0)
                elif gap <= 1:
                    scores.append(0.9)
                elif gap <= 2:
                    scores.append(0.7)
                else:
                    scores.append(0.5)

        if not scores:
            return 1.0
        return round(sum(scores) / len(scores), 4)

    # ------------------------------------------------------------------
    # Full health report
    # ------------------------------------------------------------------

    def generate_health_report(
        self,
        graph: InfraGraph,
        versions: list[ApiVersion],
        changes: list[BreakingChange],
        policies: list[SunsetPolicy] | None = None,
    ) -> VersionHealthReport:
        """Generate a comprehensive version health report.

        Combines breaking-change analysis, compatibility matrices, sunset
        evaluation, skew detection, and migration plans into a single report.
        """
        scored_changes = self.analyze_breaking_changes(
            graph, versions, changes
        )
        compat_matrices = self.compute_compatibility_matrix(
            versions, changes
        )
        evaluated_policies = self.evaluate_sunset_policies(
            versions, policies
        )
        skew_risks = self.detect_version_skew(graph, versions)

        sunset_impacts: list[SunsetImpact] = []
        deprecated_versions = [
            v
            for v in versions
            if v.phase in (SunsetPhase.DEPRECATED, SunsetPhase.SUNSET)
        ]
        for dv in deprecated_versions:
            impact = self.simulate_sunset_impact(
                graph, versions, dv.component_id, dv.version
            )
            sunset_impacts.append(impact)

        migration_plans: list[MigrationPlan] = []
        for dv in deprecated_versions:
            newer = self._find_newer_versions(
                versions, dv.component_id, dv.version
            )
            if newer:
                target = newer[0]
                plan = self.generate_migration_plan(
                    graph,
                    versions,
                    changes,
                    dv.component_id,
                    dv.version,
                    target.version,
                )
                migration_plans.append(plan)

        sunset_plan = self.generate_sunset_plan(versions)
        strategy_report = self.analyze_strategy_consistency(versions)
        bc_score = self.compute_backward_compatibility_score(
            graph, versions, changes
        )

        health_score = self._compute_versioning_health(
            versions, scored_changes, evaluated_policies
        )

        deprecated_count = sum(
            1
            for v in versions
            if v.phase
            in (
                SunsetPhase.DEPRECATED,
                SunsetPhase.SUNSET,
                SunsetPhase.REMOVED,
            )
        )
        at_risk = sum(
            si.total_consumers - si.consumers_migrated
            for si in sunset_impacts
        )
        total_breaking = sum(
            1
            for c in scored_changes
            if c.change_type in _BREAKING_TYPES
        )

        recommendations = self._health_recommendations(
            versions,
            scored_changes,
            evaluated_policies,
            sunset_impacts,
            strategy_report,
        )

        comp_map: dict[str, list[str]] = {}
        for v in versions:
            comp_map.setdefault(v.component_id, []).append(v.version)

        return VersionHealthReport(
            versions=versions,
            breaking_changes=scored_changes,
            compatibility_matrices=compat_matrices,
            skew_risks=skew_risks,
            sunset_policies=evaluated_policies,
            sunset_impacts=sunset_impacts,
            sunset_plan=sunset_plan,
            migration_plans=migration_plans,
            strategy_consistency=strategy_report,
            overall_versioning_health=round(health_score, 1),
            backward_compatibility_score=bc_score,
            total_breaking_changes=total_breaking,
            deprecated_versions_count=deprecated_count,
            at_risk_consumers=at_risk,
            recommendations=recommendations,
            component_version_map=comp_map,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_version_map(
        versions: list[ApiVersion],
    ) -> dict[tuple[str, str], ApiVersion]:
        return {(v.component_id, v.version): v for v in versions}

    @staticmethod
    def _determine_compatibility(
        va: str,
        vb: str,
        changes: list[BreakingChange],
    ) -> CompatibilityLevel:
        relevant = [
            c
            for c in changes
            if (c.source_version == va and c.target_version == vb)
            or (c.source_version == vb and c.target_version == va)
        ]
        if not relevant:
            return CompatibilityLevel.FULL

        has_breaking = any(
            c.change_type in _BREAKING_TYPES for c in relevant
        )
        has_deprecation = any(
            c.change_type == ChangeType.DEPRECATION for c in relevant
        )

        if has_breaking:
            return CompatibilityLevel.NONE
        if has_deprecation:
            return CompatibilityLevel.BACKWARD
        return CompatibilityLevel.FORWARD

    @staticmethod
    def _generate_default_policies(
        versions: list[ApiVersion],
    ) -> list[SunsetPolicy]:
        policies: list[SunsetPolicy] = []
        for v in versions:
            if v.phase == SunsetPhase.ACTIVE:
                continue
            policies.append(
                SunsetPolicy(
                    component_id=v.component_id,
                    version=v.version,
                    phase=v.phase,
                    deprecation_date=v.deprecation_date or v.release_date,
                    sunset_date=v.sunset_date,
                    active_consumers=len(v.consumers),
                )
            )
        return policies

    @staticmethod
    def _find_newer_versions(
        versions: list[ApiVersion],
        component_id: str,
        version: str,
    ) -> list[ApiVersion]:
        comp_versions = [
            v
            for v in versions
            if v.component_id == component_id and v.version != version
        ]
        comp_versions.sort(
            key=lambda v: _version_sort_key(v.version), reverse=True
        )
        target_key = _version_sort_key(version)
        return [
            cv
            for cv in comp_versions
            if _version_sort_key(cv.version) > target_key
        ]

    @staticmethod
    def _find_version_clusters(
        graph: InfraGraph,
        active_map: dict[str, str],
    ) -> list[set[str]]:
        """Find clusters of components connected by dependencies."""
        registered = set(active_map.keys())
        if not registered:
            return []

        visited: set[str] = set()
        clusters: list[set[str]] = []

        for cid in sorted(registered):
            if cid in visited:
                continue
            if graph.get_component(cid) is None:
                continue
            cluster: set[str] = set()
            queue = [cid]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                if current in registered:
                    cluster.add(current)
                for dep_comp in graph.get_dependencies(current):
                    if dep_comp.id not in visited:
                        queue.append(dep_comp.id)
                for dep_comp in graph.get_dependents(current):
                    if dep_comp.id not in visited:
                        queue.append(dep_comp.id)
            if len(cluster) >= 2:
                clusters.append(cluster)

        return clusters

    @staticmethod
    def _migration_steps(
        source: str,
        target: str,
        breaking_count: int,
    ) -> list[str]:
        steps = [
            f"Review changelog between {source} and {target}",
            f"Update API client to target version {target}",
            "Run integration test suite against new version",
        ]
        if breaking_count > 0:
            steps.insert(
                1, f"Adapt to {breaking_count} breaking change(s)"
            )
            steps.append(
                "Verify all breaking-change adaptations in staging"
            )
        steps.append("Deploy updated client to production")
        steps.append("Monitor error rates for 24 hours post-migration")
        return steps

    @staticmethod
    def _migration_phases(
        num_consumers: int,
        breaking_count: int,
    ) -> list[str]:
        phases = ["Phase 1: Announce deprecation and migration timeline"]
        if breaking_count > 0:
            phases.append(
                "Phase 2: Publish migration guide for breaking changes"
            )
        else:
            phases.append("Phase 2: Publish migration guide")
        if num_consumers > 3:
            phases.append(
                "Phase 3: Migrate internal consumers first (canary)"
            )
            phases.append(
                "Phase 4: Migrate external consumers in batches"
            )
            phases.append("Phase 5: Sunset old version")
        else:
            phases.append("Phase 3: Migrate all consumers")
            phases.append("Phase 4: Sunset old version")
        return phases

    @staticmethod
    def _migration_recommendations(
        risks: list[MigrationRisk],
        breaking_count: int,
        num_consumers: int,
    ) -> list[str]:
        recs: list[str] = []
        high_risk = [r for r in risks if r.risk_score > 50]
        if high_risk:
            recs.append(
                f"{len(high_risk)} consumer(s) have high migration risk — "
                "consider providing dedicated support"
            )
        if breaking_count > 3:
            recs.append(
                f"{breaking_count} breaking changes detected — "
                "consider a compatibility shim for gradual migration"
            )
        if num_consumers > 5:
            recs.append(
                "Large consumer base — use phased rollout with canary groups"
            )
        if not recs:
            recs.append(
                "Migration risk is low — proceed with standard timeline"
            )
        return recs

    @staticmethod
    def _sunset_recommendations(
        api_ver: ApiVersion | None,
        not_migrated: int,
        total: int,
        migration_pct: float,
    ) -> list[str]:
        recs: list[str] = []
        if not_migrated > 0:
            recs.append(
                f"Contact {not_migrated} remaining consumer(s) "
                "to complete migration"
            )
        if api_ver and api_ver.phase == SunsetPhase.ACTIVE:
            recs.append("Move version to DEPRECATED phase before sunset")
        if migration_pct < 50.0 and total > 0:
            recs.append(
                "Less than 50% migration complete — extend sunset deadline"
            )
        if migration_pct >= 100.0:
            recs.append(
                "All consumers migrated — safe to proceed with removal"
            )
        if total == 0:
            recs.append(
                "No consumers detected — version can be safely removed"
            )
        return recs

    @staticmethod
    def _compute_versioning_health(
        versions: list[ApiVersion],
        changes: list[BreakingChange],
        policies: list[SunsetPolicy],
    ) -> float:
        """Compute 0-100 health score where 100 = perfectly healthy."""
        if not versions:
            return 100.0

        score = 100.0

        # Penalty for breaking changes
        breaking = [
            c for c in changes if c.change_type in _BREAKING_TYPES
        ]
        score -= min(40.0, len(breaking) * 5.0)

        # Penalty for policy violations
        for policy in policies:
            if policy.violations:
                score -= min(10.0, len(policy.violations) * 3.0)

        # Penalty for versions past sunset with consumers
        for v in versions:
            if v.phase == SunsetPhase.REMOVED and v.consumers:
                score -= 15.0
            elif v.phase == SunsetPhase.SUNSET and v.consumers:
                score -= 10.0

        return max(0.0, score)

    @staticmethod
    def _health_recommendations(
        versions: list[ApiVersion],
        changes: list[BreakingChange],
        policies: list[SunsetPolicy],
        impacts: list[SunsetImpact],
        strategy_report: StrategyConsistencyReport,
    ) -> list[str]:
        recs: list[str] = []

        breaking = [
            c for c in changes if c.change_type in _BREAKING_TYPES
        ]
        if len(breaking) > 5:
            recs.append(
                f"High number of breaking changes ({len(breaking)}) — "
                "consider semantic versioning discipline"
            )

        violation_count = sum(len(p.violations) for p in policies)
        if violation_count > 0:
            recs.append(
                f"{violation_count} sunset policy violation(s) detected — "
                "review and enforce migration deadlines"
            )

        at_risk = sum(
            1 for si in impacts if si.estimated_outage_risk > 0.5
        )
        if at_risk > 0:
            recs.append(
                f"{at_risk} version sunset(s) pose significant outage risk — "
                "prioritise consumer migration"
            )

        removed_with_consumers = [
            v
            for v in versions
            if v.phase == SunsetPhase.REMOVED and v.consumers
        ]
        if removed_with_consumers:
            recs.append(
                f"{len(removed_with_consumers)} removed version(s) still "
                "have active consumers — immediate action required"
            )

        active_count = sum(
            1 for v in versions if v.phase == SunsetPhase.ACTIVE
        )
        if active_count > 5:
            recs.append(
                f"{active_count} active API versions — consider "
                "consolidating to reduce maintenance burden"
            )

        if not strategy_report.consistent and strategy_report.outliers:
            recs.append(
                "Inconsistent versioning strategies — "
                f"components {', '.join(strategy_report.outliers)} "
                f"deviate from dominant strategy "
                f"({strategy_report.dominant_strategy})"
            )

        if not recs:
            recs.append(
                "API versioning health is good — no action required"
            )

        return recs
