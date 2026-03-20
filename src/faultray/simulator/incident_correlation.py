# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Incident Correlation Engine — correlate incidents across services.

Identifies common root causes, cascading failure patterns, and recurring
incident clusters using temporal proximity, dependency graph analysis,
and symptom similarity.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ── Enums ────────────────────────────────────────────────────────


class CorrelationType(str, Enum):
    """Type of correlation between two incidents."""

    TEMPORAL = "temporal"
    DEPENDENCY = "dependency"
    SYMPTOM = "symptom"
    DEPLOYMENT = "deployment"
    INFRASTRUCTURE = "infrastructure"
    CONFIGURATION = "configuration"


class IncidentSeverity(str, Enum):
    """Severity levels for incidents."""

    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"
    SEV5 = "sev5"


class CorrelationStrength(str, Enum):
    """Strength of correlation between incidents."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


class RootCauseCategory(str, Enum):
    """Categories of root causes for incident clusters."""

    DEPLOYMENT_FAILURE = "deployment_failure"
    INFRASTRUCTURE_ISSUE = "infrastructure_issue"
    DEPENDENCY_FAILURE = "dependency_failure"
    CONFIGURATION_ERROR = "configuration_error"
    CAPACITY_EXHAUSTION = "capacity_exhaustion"
    EXTERNAL_OUTAGE = "external_outage"
    UNKNOWN = "unknown"


# ── Pydantic Models ─────────────────────────────────────────────


class IncidentRecord(BaseModel):
    """A single incident record from the monitoring system."""

    incident_id: str
    service_id: str
    severity: IncidentSeverity
    title: str
    started_at: str
    duration_minutes: float
    symptoms: list[str] = Field(default_factory=list)
    deployment_id: Optional[str] = None


class CorrelationLink(BaseModel):
    """A correlation between two incidents."""

    source_incident_id: str
    target_incident_id: str
    correlation_type: CorrelationType
    strength: CorrelationStrength
    confidence: float
    explanation: str


class IncidentCluster(BaseModel):
    """A group of correlated incidents sharing a root cause."""

    cluster_id: str
    incidents: list[str] = Field(default_factory=list)
    root_cause_category: RootCauseCategory
    root_cause_description: str
    contributing_factors: list[str] = Field(default_factory=list)


class RecurrencePattern(BaseModel):
    """A pattern of recurring incidents."""

    pattern_id: str
    incident_count: int
    avg_interval_hours: float
    affected_services: list[str] = Field(default_factory=list)
    likely_trigger: str


class IncidentCorrelationReport(BaseModel):
    """Full incident correlation analysis report."""

    clusters: list[IncidentCluster] = Field(default_factory=list)
    links: list[CorrelationLink] = Field(default_factory=list)
    recurrence_patterns: list[RecurrencePattern] = Field(default_factory=list)
    total_incidents: int = 0
    correlated_count: int = 0
    systemic_issues: list[str] = Field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────


_SEVERITY_WEIGHT: dict[IncidentSeverity, float] = {
    IncidentSeverity.SEV1: 1.0,
    IncidentSeverity.SEV2: 0.8,
    IncidentSeverity.SEV3: 0.5,
    IncidentSeverity.SEV4: 0.3,
    IncidentSeverity.SEV5: 0.1,
}


def _parse_time(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp string into a timezone-aware datetime."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _symptom_overlap(a: list[str], b: list[str]) -> float:
    """Return Jaccard similarity of two symptom lists (0-1)."""
    if not a and not b:
        return 0.0
    set_a = {s.lower().strip() for s in a}
    set_b = {s.lower().strip() for s in b}
    if not set_a and not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _strength_from_confidence(confidence: float) -> CorrelationStrength:
    """Map a confidence score to a CorrelationStrength."""
    if confidence >= 0.75:
        return CorrelationStrength.STRONG
    if confidence >= 0.45:
        return CorrelationStrength.MODERATE
    if confidence >= 0.2:
        return CorrelationStrength.WEAK
    return CorrelationStrength.NONE


# ── Engine ───────────────────────────────────────────────────────


class IncidentCorrelationEngine:
    """Stateless engine for correlating incidents across infrastructure."""

    # ── Public API ───────────────────────────────────────────────

    def correlate_incidents(
        self,
        graph: InfraGraph,
        incidents: list[IncidentRecord],
    ) -> IncidentCorrelationReport:
        """Run full correlation analysis and produce a report."""
        if not incidents:
            return IncidentCorrelationReport(total_incidents=0)

        temporal_links = self.find_temporal_correlations(incidents)
        dependency_links = self.find_dependency_correlations(graph, incidents)
        symptom_links = self.find_symptom_correlations(incidents)

        all_links = temporal_links + dependency_links + symptom_links

        # De-duplicate links (keep highest confidence per pair)
        all_links = self._deduplicate_links(all_links)

        clusters = self.cluster_incidents(all_links, incidents)

        # Enrich clusters with root cause from graph
        for cluster in clusters:
            if cluster.root_cause_category == RootCauseCategory.UNKNOWN:
                category = self.identify_root_cause(graph, cluster)
                cluster.root_cause_category = category
                if cluster.root_cause_description == "":
                    cluster.root_cause_description = category.value.replace("_", " ").title()

        recurrence = self.detect_recurrence(incidents)

        correlated_ids: set[str] = set()
        for link in all_links:
            if link.strength != CorrelationStrength.NONE:
                correlated_ids.add(link.source_incident_id)
                correlated_ids.add(link.target_incident_id)

        systemic = self._detect_systemic_issues(graph, incidents, clusters, recurrence)

        return IncidentCorrelationReport(
            clusters=clusters,
            links=all_links,
            recurrence_patterns=recurrence,
            total_incidents=len(incidents),
            correlated_count=len(correlated_ids),
            systemic_issues=systemic,
        )

    def find_temporal_correlations(
        self,
        incidents: list[IncidentRecord],
        window_minutes: float = 30.0,
    ) -> list[CorrelationLink]:
        """Find incidents that occurred close together in time."""
        links: list[CorrelationLink] = []
        if len(incidents) < 2:
            return links

        sorted_inc = sorted(incidents, key=lambda i: _parse_time(i.started_at))

        for i, inc_a in enumerate(sorted_inc):
            time_a = _parse_time(inc_a.started_at)
            for inc_b in sorted_inc[i + 1:]:
                if inc_a.incident_id == inc_b.incident_id:
                    continue
                time_b = _parse_time(inc_b.started_at)
                diff_min = abs((time_b - time_a).total_seconds()) / 60.0
                if diff_min > window_minutes:
                    break  # sorted, no more matches possible

                # Confidence inversely proportional to time gap
                confidence = max(0.0, 1.0 - diff_min / window_minutes)
                # Boost confidence for same deployment
                if (
                    inc_a.deployment_id
                    and inc_b.deployment_id
                    and inc_a.deployment_id == inc_b.deployment_id
                ):
                    confidence = min(1.0, confidence + 0.2)

                strength = _strength_from_confidence(confidence)
                if strength == CorrelationStrength.NONE:
                    continue

                links.append(CorrelationLink(
                    source_incident_id=inc_a.incident_id,
                    target_incident_id=inc_b.incident_id,
                    correlation_type=CorrelationType.TEMPORAL,
                    strength=strength,
                    confidence=round(confidence, 4),
                    explanation=(
                        f"Incidents occurred within {diff_min:.1f} minutes of each other"
                    ),
                ))

        return links

    def find_dependency_correlations(
        self,
        graph: InfraGraph,
        incidents: list[IncidentRecord],
    ) -> list[CorrelationLink]:
        """Find incidents on services that are connected via the dependency graph."""
        links: list[CorrelationLink] = []
        if len(incidents) < 2:
            return links

        service_ids = {inc.service_id for inc in incidents}

        # Build mapping of service_id → incident records
        service_incidents: dict[str, list[IncidentRecord]] = defaultdict(list)
        for inc in incidents:
            service_incidents[inc.service_id].append(inc)

        checked: set[tuple[str, str]] = set()

        for inc_a in incidents:
            comp_a = graph.get_component(inc_a.service_id)
            if comp_a is None:
                continue

            # Direct dependencies
            deps_a = {d.id for d in graph.get_dependencies(inc_a.service_id)}
            dependents_a = {d.id for d in graph.get_dependents(inc_a.service_id)}
            all_related = deps_a | dependents_a

            # Shared dependencies (transitive via one hop)
            for other_sid in service_ids:
                if other_sid == inc_a.service_id:
                    continue
                for inc_b in service_incidents[other_sid]:
                    pair = tuple(sorted([inc_a.incident_id, inc_b.incident_id]))
                    if pair in checked:
                        continue
                    checked.add(pair)

                    comp_b = graph.get_component(inc_b.service_id)
                    if comp_b is None:
                        continue

                    # Direct dependency: a→b or b→a
                    if other_sid in all_related:
                        links.append(CorrelationLink(
                            source_incident_id=inc_a.incident_id,
                            target_incident_id=inc_b.incident_id,
                            correlation_type=CorrelationType.DEPENDENCY,
                            strength=CorrelationStrength.STRONG,
                            confidence=0.85,
                            explanation=(
                                f"{inc_a.service_id} and {inc_b.service_id} "
                                "are directly connected in the dependency graph"
                            ),
                        ))
                        continue

                    # Shared dependency (both depend on a common service)
                    deps_b = {d.id for d in graph.get_dependencies(inc_b.service_id)}
                    shared = deps_a & deps_b
                    if shared:
                        shared_names = ", ".join(sorted(shared))
                        links.append(CorrelationLink(
                            source_incident_id=inc_a.incident_id,
                            target_incident_id=inc_b.incident_id,
                            correlation_type=CorrelationType.DEPENDENCY,
                            strength=CorrelationStrength.MODERATE,
                            confidence=0.65,
                            explanation=(
                                f"{inc_a.service_id} and {inc_b.service_id} "
                                f"share dependencies: {shared_names}"
                            ),
                        ))
                        continue

                    # Transitive dependency (a→x→b)
                    affected_a = graph.get_all_affected(inc_a.service_id)
                    if inc_b.service_id in affected_a:
                        links.append(CorrelationLink(
                            source_incident_id=inc_a.incident_id,
                            target_incident_id=inc_b.incident_id,
                            correlation_type=CorrelationType.DEPENDENCY,
                            strength=CorrelationStrength.WEAK,
                            confidence=0.4,
                            explanation=(
                                f"{inc_b.service_id} is transitively affected by "
                                f"{inc_a.service_id}"
                            ),
                        ))

        return links

    def find_symptom_correlations(
        self,
        incidents: list[IncidentRecord],
    ) -> list[CorrelationLink]:
        """Find incidents that share similar symptoms."""
        links: list[CorrelationLink] = []
        if len(incidents) < 2:
            return links

        for i, inc_a in enumerate(incidents):
            for inc_b in incidents[i + 1:]:
                if inc_a.incident_id == inc_b.incident_id:
                    continue
                if not inc_a.symptoms or not inc_b.symptoms:
                    continue

                overlap = _symptom_overlap(inc_a.symptoms, inc_b.symptoms)
                if overlap < 0.2:
                    continue

                confidence = overlap
                # Boost for same severity
                if inc_a.severity == inc_b.severity:
                    confidence = min(1.0, confidence + 0.1)

                strength = _strength_from_confidence(confidence)
                if strength == CorrelationStrength.NONE:
                    continue

                shared_symptoms = sorted(
                    set(s.lower().strip() for s in inc_a.symptoms)
                    & set(s.lower().strip() for s in inc_b.symptoms)
                )

                links.append(CorrelationLink(
                    source_incident_id=inc_a.incident_id,
                    target_incident_id=inc_b.incident_id,
                    correlation_type=CorrelationType.SYMPTOM,
                    strength=strength,
                    confidence=round(confidence, 4),
                    explanation=(
                        f"Shared symptoms: {', '.join(shared_symptoms)}"
                    ),
                ))

        return links

    def cluster_incidents(
        self,
        links: list[CorrelationLink],
        incidents: list[IncidentRecord],
    ) -> list[IncidentCluster]:
        """Group correlated incidents into clusters using union-find."""
        incident_map: dict[str, IncidentRecord] = {
            inc.incident_id: inc for inc in incidents
        }
        all_ids = set(incident_map.keys())

        # Union-Find
        parent: dict[str, str] = {iid: iid for iid in all_ids}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # Merge linked incidents (skip NONE strength)
        for link in links:
            if link.strength == CorrelationStrength.NONE:
                continue
            sid = link.source_incident_id
            tid = link.target_incident_id
            if sid in all_ids and tid in all_ids:
                union(sid, tid)

        # Group by root
        groups: dict[str, list[str]] = defaultdict(list)
        for iid in all_ids:
            groups[find(iid)].append(iid)

        clusters: list[IncidentCluster] = []
        for idx, (_, members) in enumerate(sorted(groups.items()), start=1):
            cluster_incidents_records = [incident_map[m] for m in members]
            services = sorted({inc.service_id for inc in cluster_incidents_records})
            deployments = sorted({
                inc.deployment_id
                for inc in cluster_incidents_records
                if inc.deployment_id
            })

            # Determine contributing factors
            factors: list[str] = []
            if deployments:
                factors.append(f"deployment(s): {', '.join(deployments)}")
            all_symptoms: set[str] = set()
            for inc in cluster_incidents_records:
                for s in inc.symptoms:
                    all_symptoms.add(s.lower().strip())
            if all_symptoms:
                factors.append(f"common symptoms: {', '.join(sorted(all_symptoms)[:5])}")
            if len(services) > 1:
                factors.append(f"multi-service impact: {', '.join(services)}")

            # Determine root cause from cluster links
            cluster_links = [
                link for link in links
                if link.source_incident_id in members
                and link.target_incident_id in members
                and link.strength != CorrelationStrength.NONE
            ]
            root_category, description = self._categorize_cluster(
                cluster_incidents_records, cluster_links, deployments
            )

            clusters.append(IncidentCluster(
                cluster_id=f"CLU-{idx:04d}",
                incidents=sorted(members),
                root_cause_category=root_category,
                root_cause_description=description,
                contributing_factors=factors,
            ))

        # Sort clusters by size desc then by id
        clusters.sort(key=lambda c: (-len(c.incidents), c.cluster_id))
        return clusters

    def detect_recurrence(
        self,
        incidents: list[IncidentRecord],
    ) -> list[RecurrencePattern]:
        """Detect recurring incident patterns across services."""
        patterns: list[RecurrencePattern] = []
        if len(incidents) < 2:
            return patterns

        # Group by service
        by_service: dict[str, list[IncidentRecord]] = defaultdict(list)
        for inc in incidents:
            by_service[inc.service_id].append(inc)

        pattern_counter = 0
        for service_id, service_incs in sorted(by_service.items()):
            if len(service_incs) < 2:
                continue

            sorted_incs = sorted(service_incs, key=lambda i: _parse_time(i.started_at))
            intervals: list[float] = []
            for i in range(1, len(sorted_incs)):
                t1 = _parse_time(sorted_incs[i - 1].started_at)
                t2 = _parse_time(sorted_incs[i].started_at)
                interval_hours = abs((t2 - t1).total_seconds()) / 3600.0
                intervals.append(interval_hours)

            if not intervals:
                continue

            avg_interval = sum(intervals) / len(intervals)

            # Determine likely trigger
            all_symptoms: list[str] = []
            for inc in sorted_incs:
                all_symptoms.extend(inc.symptoms)

            # Find most common symptom
            symptom_freq: dict[str, int] = defaultdict(int)
            for s in all_symptoms:
                symptom_freq[s.lower().strip()] += 1
            if symptom_freq:
                most_common = max(symptom_freq, key=symptom_freq.get)  # type: ignore[arg-type]
                trigger = f"recurring symptom: {most_common}"
            else:
                trigger = "unknown recurring trigger"

            # Check for deployment correlation
            deploy_ids = [inc.deployment_id for inc in sorted_incs if inc.deployment_id]
            if len(deploy_ids) >= 2:
                trigger = f"deployment-related recurrence ({len(deploy_ids)} deployments)"

            pattern_counter += 1
            patterns.append(RecurrencePattern(
                pattern_id=f"REC-{pattern_counter:04d}",
                incident_count=len(sorted_incs),
                avg_interval_hours=round(avg_interval, 2),
                affected_services=[service_id],
                likely_trigger=trigger,
            ))

        # Also detect cross-service recurrence via shared symptoms
        symptom_to_incidents: dict[str, list[IncidentRecord]] = defaultdict(list)
        for inc in incidents:
            for s in inc.symptoms:
                symptom_to_incidents[s.lower().strip()].append(inc)

        for symptom, symp_incs in sorted(symptom_to_incidents.items()):
            services_affected = sorted({inc.service_id for inc in symp_incs})
            if len(services_affected) < 2 or len(symp_incs) < 3:
                continue

            sorted_symp = sorted(symp_incs, key=lambda i: _parse_time(i.started_at))
            intervals = []
            for i in range(1, len(sorted_symp)):
                t1 = _parse_time(sorted_symp[i - 1].started_at)
                t2 = _parse_time(sorted_symp[i].started_at)
                intervals.append(abs((t2 - t1).total_seconds()) / 3600.0)

            if not intervals:
                continue

            avg_iv = sum(intervals) / len(intervals)
            pattern_counter += 1
            patterns.append(RecurrencePattern(
                pattern_id=f"REC-{pattern_counter:04d}",
                incident_count=len(sorted_symp),
                avg_interval_hours=round(avg_iv, 2),
                affected_services=services_affected,
                likely_trigger=f"cross-service symptom: {symptom}",
            ))

        return patterns

    def identify_root_cause(
        self,
        graph: InfraGraph,
        cluster: IncidentCluster,
    ) -> RootCauseCategory:
        """Identify the most likely root cause category for a cluster."""
        if not cluster.incidents:
            return RootCauseCategory.UNKNOWN

        # Check contributing factors for deployment signals
        for factor in cluster.contributing_factors:
            if "deployment" in factor.lower():
                return RootCauseCategory.DEPLOYMENT_FAILURE

        # Check if affected services share a common dependency that is external
        for iid in cluster.incidents:
            # extract service_id from incident_id naming or from the cluster context
            pass  # We can't directly map without the incidents list

        # Check graph for dependency patterns among incident service ids
        # Since we have the cluster description and factors, use heuristics
        desc = cluster.root_cause_description.lower()
        for factor in cluster.contributing_factors:
            fl = factor.lower()
            if "multi-service" in fl:
                # Multiple services affected → likely infrastructure or dependency
                return RootCauseCategory.INFRASTRUCTURE_ISSUE
            if "configuration" in fl or "config" in fl:
                return RootCauseCategory.CONFIGURATION_ERROR

        if "capacity" in desc or "exhaustion" in desc:
            return RootCauseCategory.CAPACITY_EXHAUSTION

        if "external" in desc or "outage" in desc:
            return RootCauseCategory.EXTERNAL_OUTAGE

        if "dependency" in desc:
            return RootCauseCategory.DEPENDENCY_FAILURE

        if "infrastructure" in desc or "infra" in desc:
            return RootCauseCategory.INFRASTRUCTURE_ISSUE

        if "config" in desc:
            return RootCauseCategory.CONFIGURATION_ERROR

        if "deploy" in desc:
            return RootCauseCategory.DEPLOYMENT_FAILURE

        # Graph-based heuristic: check if cluster services are on a dependency chain
        component_ids = set()
        for iid in cluster.incidents:
            for comp in graph.components.values():
                if comp.id in iid or iid in comp.id:
                    component_ids.add(comp.id)

        if len(component_ids) >= 2:
            for cid in component_ids:
                affected = graph.get_all_affected(cid)
                overlap = affected & component_ids
                if len(overlap) >= 1:
                    return RootCauseCategory.DEPENDENCY_FAILURE

        return RootCauseCategory.UNKNOWN

    # ── Private helpers ──────────────────────────────────────────

    def _deduplicate_links(
        self,
        links: list[CorrelationLink],
    ) -> list[CorrelationLink]:
        """Keep only the highest-confidence link per incident pair."""
        best: dict[tuple[str, str], CorrelationLink] = {}
        for link in links:
            pair = tuple(sorted([link.source_incident_id, link.target_incident_id]))
            existing = best.get(pair)
            if existing is None or link.confidence > existing.confidence:
                best[pair] = link
        return sorted(best.values(), key=lambda link_item: -link_item.confidence)

    def _categorize_cluster(
        self,
        incidents: list[IncidentRecord],
        links: list[CorrelationLink],
        deployments: list[str],
    ) -> tuple[RootCauseCategory, str]:
        """Determine root cause category and description for a cluster."""
        if len(incidents) == 1:
            inc = incidents[0]
            if inc.deployment_id:
                return (
                    RootCauseCategory.DEPLOYMENT_FAILURE,
                    f"Single incident linked to deployment {inc.deployment_id}",
                )
            return (RootCauseCategory.UNKNOWN, f"Isolated incident on {inc.service_id}")

        # Check for deployment correlation
        if deployments:
            return (
                RootCauseCategory.DEPLOYMENT_FAILURE,
                f"Correlated with deployments: {', '.join(deployments)}",
            )

        # Check link types
        dep_links = [lnk for lnk in links if lnk.correlation_type == CorrelationType.DEPENDENCY]
        temporal_links = [lnk for lnk in links if lnk.correlation_type == CorrelationType.TEMPORAL]
        symptom_links = [lnk for lnk in links if lnk.correlation_type == CorrelationType.SYMPTOM]

        if dep_links:
            return (
                RootCauseCategory.DEPENDENCY_FAILURE,
                "Dependency chain failure across services",
            )

        if symptom_links and not temporal_links:
            services = sorted({inc.service_id for inc in incidents})
            return (
                RootCauseCategory.INFRASTRUCTURE_ISSUE,
                f"Shared symptoms across {', '.join(services)}",
            )

        if temporal_links:
            services = sorted({inc.service_id for inc in incidents})
            return (
                RootCauseCategory.INFRASTRUCTURE_ISSUE,
                f"Temporally correlated incidents on {', '.join(services)}",
            )

        return (RootCauseCategory.UNKNOWN, "Insufficient data for root cause determination")

    def _detect_systemic_issues(
        self,
        graph: InfraGraph,
        incidents: list[IncidentRecord],
        clusters: list[IncidentCluster],
        recurrence: list[RecurrencePattern],
    ) -> list[str]:
        """Detect systemic issues from correlation analysis."""
        issues: list[str] = []

        # High incident rate across services
        service_counts: dict[str, int] = defaultdict(int)
        for inc in incidents:
            service_counts[inc.service_id] += 1

        for sid, count in service_counts.items():
            if count >= 3:
                issues.append(
                    f"Service {sid} has {count} incidents — potential reliability issue"
                )

        # Large clusters indicate systemic problems
        for cluster in clusters:
            if len(cluster.incidents) >= 4:
                issues.append(
                    f"Cluster {cluster.cluster_id} contains {len(cluster.incidents)} "
                    f"incidents — systemic {cluster.root_cause_category.value}"
                )

        # Recurring patterns
        for pattern in recurrence:
            if pattern.incident_count >= 3 and pattern.avg_interval_hours < 168:
                issues.append(
                    f"Recurring pattern {pattern.pattern_id}: "
                    f"{pattern.incident_count} incidents every ~{pattern.avg_interval_hours:.0f}h "
                    f"on {', '.join(pattern.affected_services)}"
                )

        # SEV1/SEV2 concentration
        sev_high = sum(
            1 for inc in incidents
            if inc.severity in (IncidentSeverity.SEV1, IncidentSeverity.SEV2)
        )
        if sev_high >= 2:
            issues.append(
                f"{sev_high} high-severity incidents (SEV1/SEV2) detected — "
                "potential major outage pattern"
            )

        # Check for external dependency impact
        for inc in incidents:
            comp = graph.get_component(inc.service_id)
            if comp and comp.type == ComponentType.EXTERNAL_API:
                dependents = graph.get_dependents(inc.service_id)
                if dependents:
                    dep_names = [d.id for d in dependents[:5]]
                    issues.append(
                        f"External API {inc.service_id} incident impacts: "
                        f"{', '.join(dep_names)}"
                    )

        return issues
