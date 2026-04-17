# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Incident Replay Engine - Replay real-world outages on your infrastructure.

Take famous cloud outages (AWS us-east-1 2021, Cloudflare 2022, etc.) and
simulate their impact on YOUR specific infrastructure topology. Answer:
'Would my system have survived the AWS us-east-1 outage?'

This is unique because it bridges historical incident data with forward-looking
simulation, giving teams concrete evidence of their resilience posture.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class IncidentEvent:
    """A single event in the timeline of a historical incident."""

    timestamp_offset: timedelta
    event_type: str  # "service_degradation", "full_outage", "partial_recovery", "full_recovery"
    affected_services: list[str]
    description: str


@dataclass
class HistoricalIncident:
    """A documented real-world cloud/infrastructure outage."""

    id: str
    name: str
    provider: str  # "aws", "azure", "gcp", "cloudflare", "generic"
    date: datetime
    duration: timedelta
    root_cause: str
    affected_services: list[str]
    affected_regions: list[str]
    severity: str  # "critical", "major", "minor"
    timeline: list[IncidentEvent]
    lessons_learned: list[str]
    post_mortem_url: str
    tags: list[str] = field(default_factory=list)


@dataclass
class AffectedComponent:
    """Describes how a specific component in the user's infra is affected."""

    component_id: str
    component_name: str
    impact_type: str  # "direct", "cascade", "degraded", "unaffected"
    health_during_incident: HealthStatus
    recovery_time: timedelta | None
    reason: str


@dataclass
class ReplayEvent:
    """A single event in the replay timeline."""

    timestamp_offset: timedelta
    event_type: str
    component_id: str
    old_health: HealthStatus
    new_health: HealthStatus
    description: str


@dataclass
class ReplayResult:
    """The full result of replaying a historical incident on user infrastructure."""

    incident: HistoricalIncident
    survived: bool
    impact_score: float  # 0-10
    affected_components: list[AffectedComponent]
    timeline: list[ReplayEvent]
    downtime_estimate: timedelta
    revenue_impact_estimate: float | None
    survival_factors: list[str]
    vulnerability_factors: list[str]
    recommendations: list[str]
    resilience_grade_during_incident: str  # A-F


# ---------------------------------------------------------------------------
# Service-to-component mapping
# ---------------------------------------------------------------------------

SERVICE_COMPONENT_MAPPING: dict[str, dict] = {
    # AWS services
    "ec2": {
        "types": [ComponentType.WEB_SERVER, ComponentType.APP_SERVER],
        "name_patterns": ["ec2", "instance", "server", "web", "app"],
    },
    "rds": {
        "types": [ComponentType.DATABASE],
        "name_patterns": ["rds", "aurora", "postgres", "mysql", "database", "db"],
    },
    "elasticache": {
        "types": [ComponentType.CACHE],
        "name_patterns": ["redis", "memcached", "cache", "elasticache"],
    },
    "alb": {
        "types": [ComponentType.LOAD_BALANCER],
        "name_patterns": ["alb", "elb", "lb", "load"],
    },
    "s3": {
        "types": [ComponentType.STORAGE],
        "name_patterns": ["s3", "storage", "bucket", "object"],
    },
    "sqs": {
        "types": [ComponentType.QUEUE],
        "name_patterns": ["sqs", "queue", "mq", "rabbit"],
    },
    "lambda": {
        "types": [ComponentType.APP_SERVER],
        "name_patterns": ["lambda", "function", "serverless"],
    },
    "route53": {
        "types": [ComponentType.DNS],
        "name_patterns": ["dns", "route53", "nameserver"],
    },
    "cloudfront": {
        "types": [ComponentType.EXTERNAL_API, ComponentType.LOAD_BALANCER],
        "name_patterns": ["cdn", "cloudfront", "edge", "distribution"],
    },
    "api_gateway": {
        "types": [ComponentType.EXTERNAL_API, ComponentType.APP_SERVER],
        "name_patterns": ["api-gw", "gateway", "apigw", "api_gateway"],
    },
    "cloudwatch": {
        "types": [ComponentType.EXTERNAL_API],
        "name_patterns": ["cloudwatch", "monitoring", "metrics"],
    },
    "ecs": {
        "types": [ComponentType.APP_SERVER],
        "name_patterns": ["ecs", "fargate", "container"],
    },
    "eks": {
        "types": [ComponentType.APP_SERVER],
        "name_patterns": ["eks", "kubernetes", "k8s"],
    },
    "dynamodb": {
        "types": [ComponentType.DATABASE],
        "name_patterns": ["dynamodb", "dynamo", "nosql"],
    },
    # Azure services
    "azure_vm": {
        "types": [ComponentType.WEB_SERVER, ComponentType.APP_SERVER],
        "name_patterns": ["vm", "azure-vm", "virtual-machine"],
    },
    "azure_sql": {
        "types": [ComponentType.DATABASE],
        "name_patterns": ["azure-sql", "cosmos", "azure-db"],
    },
    "azure_storage": {
        "types": [ComponentType.STORAGE],
        "name_patterns": ["azure-storage", "blob", "azure-blob"],
    },
    "azure_lb": {
        "types": [ComponentType.LOAD_BALANCER],
        "name_patterns": ["azure-lb", "front-door", "traffic-manager"],
    },
    # GCP services
    "compute_engine": {
        "types": [ComponentType.WEB_SERVER, ComponentType.APP_SERVER],
        "name_patterns": ["gce", "compute", "gcp-vm"],
    },
    "cloud_sql": {
        "types": [ComponentType.DATABASE],
        "name_patterns": ["cloud-sql", "spanner", "gcp-db"],
    },
    "gcs": {
        "types": [ComponentType.STORAGE],
        "name_patterns": ["gcs", "cloud-storage", "gcp-storage"],
    },
    # Generic / cross-provider services
    "dns": {
        "types": [ComponentType.DNS],
        "name_patterns": ["dns", "nameserver", "resolver"],
    },
    "cdn": {
        "types": [ComponentType.EXTERNAL_API, ComponentType.LOAD_BALANCER],
        "name_patterns": ["cdn", "edge", "akamai", "fastly", "cloudflare"],
    },
    "database": {
        "types": [ComponentType.DATABASE],
        "name_patterns": ["db", "database", "sql", "mongo", "postgres", "mysql"],
    },
    "load_balancer": {
        "types": [ComponentType.LOAD_BALANCER],
        "name_patterns": ["lb", "load", "balancer", "nginx", "haproxy"],
    },
    "server": {
        "types": [ComponentType.WEB_SERVER, ComponentType.APP_SERVER],
        "name_patterns": ["server", "host", "node", "instance"],
    },
    "cache": {
        "types": [ComponentType.CACHE],
        "name_patterns": ["cache", "redis", "memcached"],
    },
    "queue": {
        "types": [ComponentType.QUEUE],
        "name_patterns": ["queue", "mq", "kafka", "rabbit", "sns"],
    },
}


# ---------------------------------------------------------------------------
# Incident Replay Engine
# ---------------------------------------------------------------------------

class IncidentReplayEngine:
    """Replay historical cloud outages against a user's infrastructure graph.

    The engine maps incident-affected services to the user's infrastructure
    components, then simulates the impact considering multi-AZ, failover,
    replicas, and cascade effects.
    """

    def __init__(self) -> None:
        from faultray.simulator.incident_db import HISTORICAL_INCIDENTS

        self._incidents: dict[str, HistoricalIncident] = {
            inc.id: inc for inc in HISTORICAL_INCIDENTS
        }

    # -- public API --------------------------------------------------------

    def list_incidents(
        self, provider: str | None = None
    ) -> list[HistoricalIncident]:
        """Return all known historical incidents, optionally filtered by provider."""
        incidents = list(self._incidents.values())
        if provider:
            incidents = [i for i in incidents if i.provider == provider]
        return sorted(incidents, key=lambda i: i.date, reverse=True)

    def get_incident(self, incident_id: str) -> HistoricalIncident:
        """Look up a single incident by ID.

        Raises:
            KeyError: If incident_id is not found.
        """
        if incident_id not in self._incidents:
            raise KeyError(
                f"Unknown incident ID '{incident_id}'. "
                f"Available: {sorted(self._incidents.keys())}"
            )
        return self._incidents[incident_id]

    def replay(
        self, graph: InfraGraph, incident: HistoricalIncident
    ) -> ReplayResult:
        """Replay a historical incident against the given infrastructure.

        For each service affected in the real incident, the engine:
        1. Finds matching components in the user's infrastructure.
        2. Checks multi-AZ / multi-region / failover resilience.
        3. Determines direct impact or survival.
        4. Runs cascade analysis on directly-affected components.
        5. Aggregates results into a ReplayResult.
        """
        affected: list[AffectedComponent] = []
        replay_events: list[ReplayEvent] = []
        survival_factors: list[str] = []
        vulnerability_factors: list[str] = []
        recommendations: list[str] = []
        directly_affected_ids: set[str] = set()

        # Phase 1: Determine directly-affected components
        for service in incident.affected_services:
            matching = self._find_matching_components(graph, service)
            if not matching:
                continue

            for comp in matching:
                survived, health, reason = self._evaluate_component(
                    comp, incident, service
                )
                if survived:
                    impact_type = "degraded" if health == HealthStatus.DEGRADED else "unaffected"
                    survival_factors.append(reason)
                else:
                    impact_type = "direct"
                    directly_affected_ids.add(comp.id)
                    vulnerability_factors.append(reason)

                recovery_time = self._estimate_recovery_time(comp, incident) if not survived else None

                affected.append(AffectedComponent(
                    component_id=comp.id,
                    component_name=comp.name,
                    impact_type=impact_type,
                    health_during_incident=health,
                    recovery_time=recovery_time,
                    reason=reason,
                ))

                # Build timeline events based on incident timeline
                comp_events = self._build_replay_events(comp, incident, health, survived)
                replay_events.extend(comp_events)

        # Phase 2: Cascade analysis for directly-affected components
        cascade_affected = self._run_cascade_analysis(
            graph, directly_affected_ids, incident
        )
        for ca in cascade_affected:
            if ca.component_id not in {a.component_id for a in affected}:
                affected.append(ca)
                vulnerability_factors.append(
                    f"Cascade impact on {ca.component_name}: {ca.reason}"
                )

        # Phase 3: Scoring
        impact_score = self._calculate_impact_score(affected, graph)
        survived = impact_score < 5.0
        downtime = self._estimate_total_downtime(affected, incident)
        revenue_impact = self._estimate_revenue_impact(graph, downtime)
        grade = self._calculate_grade(impact_score)

        # Phase 4: Generate recommendations
        recommendations = self._generate_recommendations(
            affected, incident, graph, survival_factors, vulnerability_factors
        )

        # Deduplicate
        survival_factors = list(dict.fromkeys(survival_factors))
        vulnerability_factors = list(dict.fromkeys(vulnerability_factors))

        # Sort timeline
        replay_events.sort(key=lambda e: e.timestamp_offset)

        return ReplayResult(
            incident=incident,
            survived=survived,
            impact_score=round(impact_score, 1),
            affected_components=affected,
            timeline=replay_events,
            downtime_estimate=downtime,
            revenue_impact_estimate=revenue_impact,
            survival_factors=survival_factors,
            vulnerability_factors=vulnerability_factors,
            recommendations=recommendations,
            resilience_grade_during_incident=grade,
        )

    def replay_all(self, graph: InfraGraph) -> list[ReplayResult]:
        """Replay ALL known historical incidents against the infrastructure."""
        return [self.replay(graph, inc) for inc in self._incidents.values()]

    def find_vulnerable_incidents(
        self, graph: InfraGraph
    ) -> list[tuple[HistoricalIncident, float]]:
        """Find incidents the infrastructure is vulnerable to.

        Returns a sorted list of (incident, vulnerability_score) tuples
        where vulnerability_score > 0 means there is at least some exposure.
        The list is sorted by vulnerability_score descending.
        """
        results: list[tuple[HistoricalIncident, float]] = []
        for incident in self._incidents.values():
            score = self._quick_vulnerability_score(graph, incident)
            if score > 0:
                results.append((incident, score))
        return sorted(results, key=lambda x: x[1], reverse=True)

    # -- private helpers ---------------------------------------------------

    def _find_matching_components(
        self, graph: InfraGraph, service: str
    ) -> list[Component]:
        """Find components that correspond to the given service identifier."""
        mapping = SERVICE_COMPONENT_MAPPING.get(service)
        if not mapping:
            return []

        matched: list[Component] = []
        target_types = mapping["types"]
        name_patterns = mapping["name_patterns"]

        for comp in graph.components.values():
            # Match by component type
            if comp.type in target_types:
                matched.append(comp)
                continue
            # Match by name pattern
            comp_name_lower = comp.name.lower()
            comp_id_lower = comp.id.lower()
            for pattern in name_patterns:
                if pattern in comp_name_lower or pattern in comp_id_lower:
                    matched.append(comp)
                    break

        return matched

    def _evaluate_component(
        self,
        comp: Component,
        incident: HistoricalIncident,
        service: str,
    ) -> tuple[bool, HealthStatus, str]:
        """Evaluate whether a component survives the incident.

        Returns (survived, resulting_health, reason).
        """
        is_global = "global" in incident.affected_regions

        # Check 1: Region/AZ protection
        if not is_global and comp.region.region:
            comp_region = comp.region.region.lower()
            affected_lower = [r.lower() for r in incident.affected_regions]
            if comp_region and comp_region not in affected_lower:
                return (
                    True,
                    HealthStatus.HEALTHY,
                    f"{comp.name} is in region '{comp.region.region}', "
                    f"which was not affected (incident hit {incident.affected_regions})",
                )

        # Check 2: Multi-AZ with failover to unaffected region
        if not is_global and comp.failover.enabled and comp.region.dr_target_region:
            dr_region = comp.region.dr_target_region.lower()
            affected_lower = [r.lower() for r in incident.affected_regions]
            if dr_region not in affected_lower:
                return (
                    True,
                    HealthStatus.DEGRADED,
                    f"{comp.name} has failover to DR region '{comp.region.dr_target_region}' "
                    f"(unaffected). Failover time: {comp.failover.promotion_time_seconds}s",
                )

        # Check 3: Replicas > 1 can absorb partial outage
        if comp.replicas > 1 and not is_global:
            return (
                True,
                HealthStatus.DEGRADED,
                f"{comp.name} has {comp.replicas} replicas - degraded but not down. "
                f"Remaining replicas absorb load",
            )

        # Check 4: Replicas > 1 but global outage -> still degraded
        if comp.replicas > 2 and is_global:
            return (
                True,
                HealthStatus.DEGRADED,
                f"{comp.name} has {comp.replicas} replicas. Even in global outage, "
                f"distributed replicas may partially survive",
            )

        # Check 5: Component has no protection -> goes down
        reason_parts: list[str] = []
        if comp.replicas <= 1:
            reason_parts.append("single instance (no replicas)")
        if not comp.failover.enabled:
            reason_parts.append("no failover configured")
        if not comp.region.region:
            reason_parts.append("no region specified")
        elif is_global:
            reason_parts.append("global outage affects all regions")
        else:
            reason_parts.append(
                f"in affected region {comp.region.region}"
            )

        return (
            False,
            HealthStatus.DOWN,
            f"{comp.name} would go DOWN: {', '.join(reason_parts)}",
        )

    def _estimate_recovery_time(
        self, comp: Component, incident: HistoricalIncident
    ) -> timedelta:
        """Estimate how long it takes for a component to recover."""
        # Use failover time if available, otherwise fraction of incident duration
        if comp.failover.enabled:
            return timedelta(seconds=comp.failover.promotion_time_seconds)
        # Use MTTR if configured
        if comp.operational_profile.mttr_minutes > 0:
            return timedelta(minutes=comp.operational_profile.mttr_minutes)
        # Default: assume recovery takes ~70% of incident duration
        return timedelta(seconds=incident.duration.total_seconds() * 0.7)

    def _build_replay_events(
        self,
        comp: Component,
        incident: HistoricalIncident,
        resulting_health: HealthStatus,
        survived: bool,
    ) -> list[ReplayEvent]:
        """Create timeline events for a component based on the incident timeline."""
        events: list[ReplayEvent] = []

        if not incident.timeline:
            # If no detailed timeline, create synthetic events
            events.append(ReplayEvent(
                timestamp_offset=timedelta(0),
                event_type="incident_start",
                component_id=comp.id,
                old_health=HealthStatus.HEALTHY,
                new_health=resulting_health,
                description=f"Incident begins: {comp.name} -> {resulting_health.value}",
            ))
            if survived:
                events.append(ReplayEvent(
                    timestamp_offset=timedelta(minutes=5),
                    event_type="survived",
                    component_id=comp.id,
                    old_health=resulting_health,
                    new_health=resulting_health,
                    description=f"{comp.name} survives with {resulting_health.value} status",
                ))
            else:
                events.append(ReplayEvent(
                    timestamp_offset=incident.duration,
                    event_type="full_recovery",
                    component_id=comp.id,
                    old_health=resulting_health,
                    new_health=HealthStatus.HEALTHY,
                    description=f"{comp.name} recovers after {incident.duration}",
                ))
            return events

        # Map incident timeline events to component events
        for ie in incident.timeline:
            if ie.event_type == "full_outage":
                new_h = HealthStatus.DOWN if not survived else HealthStatus.DEGRADED
            elif ie.event_type == "service_degradation":
                new_h = HealthStatus.DEGRADED
            elif ie.event_type == "partial_recovery":
                new_h = HealthStatus.DEGRADED
            elif ie.event_type == "full_recovery":
                new_h = HealthStatus.HEALTHY
            else:
                new_h = resulting_health

            events.append(ReplayEvent(
                timestamp_offset=ie.timestamp_offset,
                event_type=ie.event_type,
                component_id=comp.id,
                old_health=HealthStatus.HEALTHY if not events else events[-1].new_health,
                new_health=new_h,
                description=f"{comp.name}: {ie.description}",
            ))

        return events

    def _run_cascade_analysis(
        self,
        graph: InfraGraph,
        directly_affected_ids: set[str],
        incident: HistoricalIncident,
    ) -> list[AffectedComponent]:
        """Run BFS cascade analysis from all directly-affected components."""
        cascade_results: list[AffectedComponent] = []
        visited: set[str] = set(directly_affected_ids)
        queue: deque[str] = deque(directly_affected_ids)

        while queue:
            current_id = queue.popleft()
            dependents = graph.get_dependents(current_id)

            for dep_comp in dependents:
                if dep_comp.id in visited:
                    continue
                visited.add(dep_comp.id)

                edge = graph.get_dependency_edge(dep_comp.id, current_id)
                dep_type = edge.dependency_type if edge else "requires"

                if dep_type == "requires":
                    if dep_comp.replicas > 1:
                        health = HealthStatus.DEGRADED
                        reason = (
                            f"Required dependency '{current_id}' is down. "
                            f"{dep_comp.replicas} replicas absorb partial load"
                        )
                    else:
                        health = HealthStatus.DOWN
                        reason = (
                            f"Required dependency '{current_id}' is down. "
                            f"No replicas or failover - cascading failure"
                        )
                        queue.append(dep_comp.id)
                elif dep_type == "optional":
                    health = HealthStatus.DEGRADED
                    reason = (
                        f"Optional dependency '{current_id}' is down. "
                        f"Degraded functionality but still operational"
                    )
                else:  # async
                    health = HealthStatus.DEGRADED
                    reason = (
                        f"Async dependency '{current_id}' is down. "
                        f"Queue building up, eventual consistency delayed"
                    )

                recovery_time = None
                if health == HealthStatus.DOWN:
                    recovery_time = self._estimate_recovery_time(dep_comp, incident)

                cascade_results.append(AffectedComponent(
                    component_id=dep_comp.id,
                    component_name=dep_comp.name,
                    impact_type="cascade",
                    health_during_incident=health,
                    recovery_time=recovery_time,
                    reason=reason,
                ))

        return cascade_results

    def _calculate_impact_score(
        self, affected: list[AffectedComponent], graph: InfraGraph
    ) -> float:
        """Calculate overall impact score (0-10).

        0 = no impact, 10 = total system failure.
        """
        if not affected:
            return 0.0

        total_components = max(len(graph.components), 1)
        down_count = sum(
            1 for a in affected if a.health_during_incident == HealthStatus.DOWN
        )
        degraded_count = sum(
            1 for a in affected if a.health_during_incident == HealthStatus.DEGRADED
        )

        # Weighted impact: DOWN=1.0, DEGRADED=0.3
        weighted = (down_count * 1.0 + degraded_count * 0.3) / total_components
        score = min(10.0, weighted * 10.0)

        # Boost score if many components are fully down
        if down_count > 0:
            down_ratio = down_count / total_components
            if down_ratio > 0.5:
                score = max(score, 8.0)
            elif down_ratio > 0.3:
                score = max(score, 6.0)

        return score

    def _estimate_total_downtime(
        self, affected: list[AffectedComponent], incident: HistoricalIncident
    ) -> timedelta:
        """Estimate total downtime across affected components."""
        down_components = [
            a for a in affected if a.health_during_incident == HealthStatus.DOWN
        ]
        if not down_components:
            return timedelta(0)

        # Use max recovery time among all down components
        max_recovery = timedelta(0)
        for comp in down_components:
            if comp.recovery_time and comp.recovery_time > max_recovery:
                max_recovery = comp.recovery_time

        # Cap at incident duration
        if max_recovery > incident.duration:
            max_recovery = incident.duration

        return max_recovery if max_recovery > timedelta(0) else incident.duration

    def _estimate_revenue_impact(
        self, graph: InfraGraph, downtime: timedelta
    ) -> float | None:
        """Estimate revenue impact from downtime."""
        total_rev_per_minute = sum(
            c.cost_profile.revenue_per_minute
            for c in graph.components.values()
            if c.cost_profile.revenue_per_minute > 0
        )
        if total_rev_per_minute <= 0:
            return None
        return total_rev_per_minute * (downtime.total_seconds() / 60.0)

    def _calculate_grade(self, impact_score: float) -> str:
        """Convert impact score to letter grade (A=best, F=worst)."""
        if impact_score <= 1.0:
            return "A"
        elif impact_score <= 3.0:
            return "B"
        elif impact_score <= 5.0:
            return "C"
        elif impact_score <= 7.0:
            return "D"
        else:
            return "F"

    def _generate_recommendations(
        self,
        affected: list[AffectedComponent],
        incident: HistoricalIncident,
        graph: InfraGraph,
        survival_factors: list[str],
        vulnerability_factors: list[str],
    ) -> list[str]:
        """Generate actionable recommendations based on replay results."""
        recs: list[str] = []

        down_components = [
            a for a in affected if a.health_during_incident == HealthStatus.DOWN
        ]
        [
            a for a in affected if a.health_during_incident == HealthStatus.DEGRADED
        ]

        # Recommendation: Multi-region
        single_region = [
            a for a in down_components
            if not graph.get_component(a.component_id) or
               not graph.get_component(a.component_id).region.dr_target_region
        ]
        if single_region:
            names = ", ".join(a.component_name for a in single_region[:3])
            recs.append(
                f"Enable multi-region failover for: {names}. "
                f"This incident ({incident.name}) affected "
                f"{', '.join(incident.affected_regions)}."
            )

        # Recommendation: Add replicas
        no_replicas = [
            a for a in down_components
            if graph.get_component(a.component_id) and
               graph.get_component(a.component_id).replicas <= 1
        ]
        if no_replicas:
            names = ", ".join(a.component_name for a in no_replicas[:3])
            recs.append(
                f"Add replicas to: {names}. "
                f"Multiple replicas would have prevented full outage."
            )

        # Recommendation: Enable failover
        no_failover = [
            a for a in down_components
            if graph.get_component(a.component_id) and
               not graph.get_component(a.component_id).failover.enabled
        ]
        if no_failover:
            names = ", ".join(a.component_name for a in no_failover[:3])
            recs.append(
                f"Enable automated failover for: {names}. "
                f"Failover to an unaffected region would have kept these services running."
            )

        # Recommendation: Circuit breakers for cascade prevention
        cascade = [a for a in affected if a.impact_type == "cascade"]
        if cascade:
            recs.append(
                f"{len(cascade)} components were affected by cascade failure. "
                f"Add circuit breakers on critical dependency edges to contain blast radius."
            )

        # Generic lessons learned from the incident
        for lesson in incident.lessons_learned[:2]:
            recs.append(f"Lesson from {incident.name}: {lesson}")

        return recs

    def _quick_vulnerability_score(
        self, graph: InfraGraph, incident: HistoricalIncident
    ) -> float:
        """Quickly estimate vulnerability to an incident (0-10) without full replay.

        Returns 0 if no components match any affected services.
        """
        total_matching = 0
        vulnerable = 0

        for service in incident.affected_services:
            matching = self._find_matching_components(graph, service)
            total_matching += len(matching)
            for comp in matching:
                is_global = "global" in incident.affected_regions
                # Quick check: is the component in the affected region?
                if not is_global and comp.region.region:
                    comp_region = comp.region.region.lower()
                    affected_lower = [r.lower() for r in incident.affected_regions]
                    if comp_region not in affected_lower:
                        continue  # Not vulnerable

                # Check if it has protection
                has_protection = (
                    comp.replicas > 1
                    or comp.failover.enabled
                    or (not is_global and comp.region.dr_target_region)
                )
                if not has_protection:
                    vulnerable += 1
                else:
                    vulnerable += 0.3  # Partially vulnerable (degraded)

        if total_matching == 0:
            return 0.0

        return min(10.0, (vulnerable / max(total_matching, 1)) * 10.0)
