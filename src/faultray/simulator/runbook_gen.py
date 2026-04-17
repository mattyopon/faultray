# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Automated Runbook Generator for incident response playbooks.

Generates structured runbooks based on infrastructure graph topology,
component properties, and dependency relationships.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


class IncidentType(str, Enum):
    COMPONENT_DOWN = "component_down"
    HIGH_LATENCY = "high_latency"
    DATA_CORRUPTION = "data_corruption"
    SECURITY_BREACH = "security_breach"
    CAPACITY_EXHAUSTION = "capacity_exhaustion"
    CASCADING_FAILURE = "cascading_failure"
    DEPENDENCY_FAILURE = "dependency_failure"


class StepType(str, Enum):
    DIAGNOSTIC = "diagnostic"
    MITIGATION = "mitigation"
    VERIFICATION = "verification"
    ESCALATION = "escalation"
    COMMUNICATION = "communication"


@dataclass
class RunbookStep:
    order: int
    step_type: StepType
    title: str
    description: str
    commands: list[str]  # CLI commands to execute
    expected_outcome: str
    timeout_minutes: int = 5
    requires_approval: bool = False


@dataclass
class Runbook:
    id: str
    title: str
    incident_type: IncidentType
    component_id: str
    component_name: str
    severity: str  # "SEV1"..."SEV4"
    steps: list[RunbookStep] = field(default_factory=list)
    estimated_resolution_minutes: int = 30
    escalation_contacts: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    post_incident: list[str] = field(default_factory=list)


@dataclass
class RunbookLibrary:
    runbooks: list[Runbook] = field(default_factory=list)
    total_count: int = 0
    coverage_percent: float = 0.0  # % of components covered
    incident_types_covered: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

# Which incident types apply to each component type
_COMPONENT_INCIDENT_MAP: dict[ComponentType, list[IncidentType]] = {
    ComponentType.DATABASE: [
        IncidentType.COMPONENT_DOWN,
        IncidentType.HIGH_LATENCY,
        IncidentType.DATA_CORRUPTION,
        IncidentType.SECURITY_BREACH,
        IncidentType.CAPACITY_EXHAUSTION,
    ],
    ComponentType.CACHE: [
        IncidentType.COMPONENT_DOWN,
        IncidentType.HIGH_LATENCY,
        IncidentType.CAPACITY_EXHAUSTION,
    ],
    ComponentType.QUEUE: [
        IncidentType.COMPONENT_DOWN,
        IncidentType.HIGH_LATENCY,
        IncidentType.CAPACITY_EXHAUSTION,
    ],
    ComponentType.LOAD_BALANCER: [
        IncidentType.COMPONENT_DOWN,
        IncidentType.HIGH_LATENCY,
        IncidentType.SECURITY_BREACH,
    ],
    ComponentType.WEB_SERVER: [
        IncidentType.COMPONENT_DOWN,
        IncidentType.HIGH_LATENCY,
        IncidentType.SECURITY_BREACH,
        IncidentType.CAPACITY_EXHAUSTION,
    ],
    ComponentType.APP_SERVER: [
        IncidentType.COMPONENT_DOWN,
        IncidentType.HIGH_LATENCY,
        IncidentType.SECURITY_BREACH,
        IncidentType.CAPACITY_EXHAUSTION,
    ],
    ComponentType.STORAGE: [
        IncidentType.COMPONENT_DOWN,
        IncidentType.DATA_CORRUPTION,
        IncidentType.CAPACITY_EXHAUSTION,
    ],
    ComponentType.DNS: [
        IncidentType.COMPONENT_DOWN,
        IncidentType.HIGH_LATENCY,
    ],
    ComponentType.EXTERNAL_API: [
        IncidentType.COMPONENT_DOWN,
        IncidentType.HIGH_LATENCY,
        IncidentType.DEPENDENCY_FAILURE,
    ],
    ComponentType.CUSTOM: [
        IncidentType.COMPONENT_DOWN,
        IncidentType.HIGH_LATENCY,
    ],
}

# Base CLI commands by component type
_CLI_COMMANDS: dict[ComponentType, dict[str, list[str]]] = {
    ComponentType.DATABASE: {
        "diagnostic": [
            "kubectl get pods -l app={name} -o wide",
            "kubectl logs -l app={name} --tail=100",
            "pg_isready -h {name} -p 5432",
        ],
        "mitigation": [
            "kubectl rollout restart deployment/{name}",
        ],
        "verification": [
            "kubectl get pods -l app={name}",
            "pg_isready -h {name} -p 5432",
        ],
    },
    ComponentType.CACHE: {
        "diagnostic": [
            "kubectl get pods -l app={name} -o wide",
            "redis-cli -h {name} ping",
            "redis-cli -h {name} info memory",
        ],
        "mitigation": [
            "kubectl rollout restart deployment/{name}",
        ],
        "verification": [
            "redis-cli -h {name} ping",
            "redis-cli -h {name} dbsize",
        ],
    },
    ComponentType.QUEUE: {
        "diagnostic": [
            "kubectl get pods -l app={name} -o wide",
            "kubectl logs -l app={name} --tail=100",
        ],
        "mitigation": [
            "kubectl rollout restart deployment/{name}",
        ],
        "verification": [
            "kubectl get pods -l app={name}",
        ],
    },
    ComponentType.LOAD_BALANCER: {
        "diagnostic": [
            "kubectl get svc {name} -o wide",
            "curl -s -o /dev/null -w '%{{http_code}}' http://{name}/healthz",
        ],
        "mitigation": [
            "kubectl rollout restart deployment/{name}",
        ],
        "verification": [
            "curl -s -o /dev/null -w '%{{http_code}}' http://{name}/healthz",
        ],
    },
    ComponentType.WEB_SERVER: {
        "diagnostic": [
            "kubectl get pods -l app={name} -o wide",
            "curl -s -o /dev/null -w '%{{http_code}}' http://{name}/healthz",
        ],
        "mitigation": [
            "kubectl rollout restart deployment/{name}",
        ],
        "verification": [
            "curl -s -o /dev/null -w '%{{http_code}}' http://{name}/healthz",
        ],
    },
    ComponentType.APP_SERVER: {
        "diagnostic": [
            "kubectl get pods -l app={name} -o wide",
            "kubectl logs -l app={name} --tail=100",
            "curl -s -o /dev/null -w '%{{http_code}}' http://{name}/healthz",
        ],
        "mitigation": [
            "kubectl rollout restart deployment/{name}",
        ],
        "verification": [
            "kubectl get pods -l app={name}",
            "curl -s -o /dev/null -w '%{{http_code}}' http://{name}/healthz",
        ],
    },
    ComponentType.STORAGE: {
        "diagnostic": [
            "aws s3 ls s3://{name}/ --summarize",
            "kubectl get pvc -l app={name}",
        ],
        "mitigation": [
            "kubectl rollout restart deployment/{name}",
        ],
        "verification": [
            "aws s3 ls s3://{name}/ --summarize",
        ],
    },
    ComponentType.DNS: {
        "diagnostic": [
            "dig {name} +short",
            "nslookup {name}",
        ],
        "mitigation": [
            "aws route53 list-resource-record-sets --hosted-zone-id ZONE_ID",
        ],
        "verification": [
            "dig {name} +short",
        ],
    },
    ComponentType.EXTERNAL_API: {
        "diagnostic": [
            "curl -s -o /dev/null -w '%{{http_code}}' https://{name}/status",
        ],
        "mitigation": [],
        "verification": [
            "curl -s -o /dev/null -w '%{{http_code}}' https://{name}/status",
        ],
    },
    ComponentType.CUSTOM: {
        "diagnostic": [
            "kubectl get pods -l app={name} -o wide",
            "kubectl logs -l app={name} --tail=100",
        ],
        "mitigation": [
            "kubectl rollout restart deployment/{name}",
        ],
        "verification": [
            "kubectl get pods -l app={name}",
        ],
    },
}

# Resolution time estimates (minutes) per incident type
_RESOLUTION_ESTIMATES: dict[IncidentType, int] = {
    IncidentType.COMPONENT_DOWN: 30,
    IncidentType.HIGH_LATENCY: 20,
    IncidentType.DATA_CORRUPTION: 60,
    IncidentType.SECURITY_BREACH: 90,
    IncidentType.CAPACITY_EXHAUSTION: 25,
    IncidentType.CASCADING_FAILURE: 45,
    IncidentType.DEPENDENCY_FAILURE: 35,
}

_DEFAULT_POST_INCIDENT = [
    "Conduct blameless postmortem within 48 hours",
    "Update monitoring and alerting thresholds",
    "Review and update this runbook based on lessons learned",
    "Create follow-up tickets for long-term improvements",
]


class RunbookGenerator:
    """Generates incident response runbooks from an infrastructure graph."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._cache: dict[str, Runbook] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_for_component(self, component_id: str) -> list[Runbook]:
        """Generate all applicable runbooks for a component.

        Raises ``KeyError`` when *component_id* is not in the graph.
        """
        comp = self._graph.get_component(component_id)
        if comp is None:
            raise KeyError(f"Component '{component_id}' not found in graph")

        incident_types = self._applicable_incidents(component_id)
        runbooks: list[Runbook] = []
        for it in incident_types:
            rb = self._build_runbook(component_id, it)
            self._cache[rb.id] = rb
            runbooks.append(rb)
        return runbooks

    def generate_all(self) -> RunbookLibrary:
        """Generate runbooks for every component and return a library."""
        all_runbooks: list[Runbook] = []
        components_covered: set[str] = set()
        incident_types_seen: set[str] = set()

        for cid in self._graph.components:
            rbs = self.generate_for_component(cid)
            if rbs:
                components_covered.add(cid)
            for rb in rbs:
                all_runbooks.append(rb)
                incident_types_seen.add(rb.incident_type.value)

        total_components = len(self._graph.components)
        coverage = (
            (len(components_covered) / total_components * 100.0)
            if total_components > 0
            else 0.0
        )

        return RunbookLibrary(
            runbooks=all_runbooks,
            total_count=len(all_runbooks),
            coverage_percent=coverage,
            incident_types_covered=sorted(incident_types_seen),
        )

    def generate_for_incident_type(
        self, incident_type: IncidentType
    ) -> list[Runbook]:
        """Generate runbooks of a specific type for all applicable components."""
        runbooks: list[Runbook] = []
        for cid in self._graph.components:
            applicable = self._applicable_incidents(cid)
            if incident_type in applicable:
                rb = self._build_runbook(cid, incident_type)
                self._cache[rb.id] = rb
                runbooks.append(rb)
        return runbooks

    def get_runbook(self, runbook_id: str) -> Runbook | None:
        """Retrieve a previously generated runbook by ID."""
        return self._cache.get(runbook_id)

    def format_runbook(self, runbook: Runbook) -> str:
        """Format a runbook as readable Markdown text."""
        lines: list[str] = []
        lines.append(f"# {runbook.title}")
        lines.append("")
        lines.append(f"**Runbook ID:** {runbook.id}")
        lines.append(f"**Severity:** {runbook.severity}")
        lines.append(
            f"**Component:** {runbook.component_name} (`{runbook.component_id}`)"
        )
        lines.append(f"**Incident Type:** {runbook.incident_type.value}")
        lines.append(
            f"**Estimated Resolution:** {runbook.estimated_resolution_minutes} minutes"
        )
        lines.append("")

        # Prerequisites
        if runbook.prerequisites:
            lines.append("## Prerequisites")
            lines.append("")
            for prereq in runbook.prerequisites:
                lines.append(f"- {prereq}")
            lines.append("")

        # Escalation contacts
        if runbook.escalation_contacts:
            lines.append("## Escalation Contacts")
            lines.append("")
            for contact in runbook.escalation_contacts:
                lines.append(f"- {contact}")
            lines.append("")

        # Steps
        lines.append("## Steps")
        lines.append("")
        for step in runbook.steps:
            approval_tag = " [REQUIRES APPROVAL]" if step.requires_approval else ""
            lines.append(
                f"### Step {step.order}: {step.title}{approval_tag}"
            )
            lines.append("")
            lines.append(f"**Type:** {step.step_type.value}")
            lines.append(f"**Timeout:** {step.timeout_minutes} minutes")
            lines.append("")
            lines.append(step.description)
            lines.append("")
            if step.commands:
                lines.append("```bash")
                for cmd in step.commands:
                    lines.append(cmd)
                lines.append("```")
                lines.append("")
            lines.append(f"**Expected Outcome:** {step.expected_outcome}")
            lines.append("")

        # Post-incident
        if runbook.post_incident:
            lines.append("## Post-Incident Actions")
            lines.append("")
            for item in runbook.post_incident:
                lines.append(f"- {item}")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _applicable_incidents(self, component_id: str) -> list[IncidentType]:
        """Determine which incident types are relevant for a component."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return []

        base = list(
            _COMPONENT_INCIDENT_MAP.get(comp.type, [IncidentType.COMPONENT_DOWN, IncidentType.HIGH_LATENCY])
        )

        # If this component has dependents, cascading failure is relevant
        dependents = self._graph.get_dependents(component_id)
        if len(dependents) >= 2 and IncidentType.CASCADING_FAILURE not in base:
            base.append(IncidentType.CASCADING_FAILURE)

        # If this component depends on others, dependency failure is relevant
        dependencies = self._graph.get_dependencies(component_id)
        if dependencies and IncidentType.DEPENDENCY_FAILURE not in base:
            base.append(IncidentType.DEPENDENCY_FAILURE)

        return base

    def _severity_for(self, component_id: str, incident_type: IncidentType) -> str:
        """Calculate severity based on dependents count and incident type."""
        dependents = self._graph.get_dependents(component_id)
        all_affected = self._graph.get_all_affected(component_id)

        # Security breach and data corruption are inherently high severity
        if incident_type in (IncidentType.SECURITY_BREACH, IncidentType.DATA_CORRUPTION):
            if len(all_affected) >= 3:
                return "SEV1"
            return "SEV2"

        # Cascading failure with wide blast radius
        if incident_type == IncidentType.CASCADING_FAILURE:
            if len(all_affected) >= 5:
                return "SEV1"
            if len(all_affected) >= 2:
                return "SEV2"
            return "SEV3"

        # General severity based on dependents
        if len(dependents) >= 3 or len(all_affected) >= 5:
            return "SEV1"
        if len(dependents) >= 1 or len(all_affected) >= 2:
            return "SEV2"

        comp = self._graph.get_component(component_id)
        if comp and comp.type in (ComponentType.DATABASE, ComponentType.LOAD_BALANCER):
            return "SEV2"

        return "SEV3"

    def _build_runbook(self, component_id: str, incident_type: IncidentType) -> Runbook:
        """Build a complete runbook for a component + incident type pair."""
        comp = self._graph.get_component(component_id)
        assert comp is not None

        severity = self._severity_for(component_id, incident_type)
        runbook_id = f"rb-{component_id}-{incident_type.value}"
        title = f"{incident_type.value.replace('_', ' ').title()} - {comp.name}"

        steps = self._generate_steps(component_id, incident_type)
        resolution = self._estimate_resolution(component_id, incident_type)
        escalation = self._escalation_contacts(severity)
        prerequisites = self._prerequisites(component_id, incident_type)
        post_incident = list(_DEFAULT_POST_INCIDENT)

        # Add incident-specific post-incident items
        if incident_type == IncidentType.SECURITY_BREACH:
            post_incident.insert(0, "Conduct forensic analysis of compromised systems")
            post_incident.insert(1, "Rotate all affected credentials and secrets")
        elif incident_type == IncidentType.DATA_CORRUPTION:
            post_incident.insert(0, "Verify data integrity across all replicas")
        elif incident_type == IncidentType.CASCADING_FAILURE:
            post_incident.insert(0, "Review circuit breaker thresholds and timeout settings")

        return Runbook(
            id=runbook_id,
            title=title,
            incident_type=incident_type,
            component_id=component_id,
            component_name=comp.name,
            severity=severity,
            steps=steps,
            estimated_resolution_minutes=resolution,
            escalation_contacts=escalation,
            prerequisites=prerequisites,
            post_incident=post_incident,
        )

    def _generate_steps(
        self, component_id: str, incident_type: IncidentType
    ) -> list[RunbookStep]:
        """Generate ordered steps for a runbook."""
        comp = self._graph.get_component(component_id)
        assert comp is not None
        name_slug = comp.name.lower().replace(" ", "-")

        steps: list[RunbookStep] = []
        order = 1

        # --- Communication (first) ---
        steps.append(RunbookStep(
            order=order,
            step_type=StepType.COMMUNICATION,
            title="Notify stakeholders",
            description=(
                f"Alert the on-call team about {incident_type.value.replace('_', ' ')} "
                f"affecting {comp.name}."
            ),
            commands=[
                f"pagerduty-cli trigger --service {name_slug} "
                f"--severity {self._severity_for(component_id, incident_type)}",
            ],
            expected_outcome="On-call team acknowledged the incident.",
            timeout_minutes=2,
        ))
        order += 1

        # --- Diagnostic steps ---
        cmd_templates = _CLI_COMMANDS.get(comp.type, _CLI_COMMANDS[ComponentType.CUSTOM])
        diag_cmds = [c.format(name=name_slug) for c in cmd_templates.get("diagnostic", [])]

        steps.append(RunbookStep(
            order=order,
            step_type=StepType.DIAGNOSTIC,
            title="Initial diagnostics",
            description=f"Gather diagnostic information for {comp.name}.",
            commands=diag_cmds,
            expected_outcome="Root cause indicators identified.",
            timeout_minutes=5,
        ))
        order += 1

        # Check component health
        steps.append(RunbookStep(
            order=order,
            step_type=StepType.DIAGNOSTIC,
            title="Check component health status",
            description=f"Verify health status and metrics for {comp.name}.",
            commands=[
                f"kubectl describe pod -l app={name_slug}",
                f"kubectl top pod -l app={name_slug}",
            ],
            expected_outcome="Component health status assessed.",
            timeout_minutes=3,
        ))
        order += 1

        # Incident-type-specific diagnostic steps
        if incident_type == IncidentType.HIGH_LATENCY:
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.DIAGNOSTIC,
                title="Analyze latency metrics",
                description="Check response time percentiles and identify bottlenecks.",
                commands=[
                    f"kubectl logs -l app={name_slug} --tail=200 | grep -i 'latency\\|slow\\|timeout'",
                ],
                expected_outcome="Latency source identified.",
                timeout_minutes=5,
            ))
            order += 1

        if incident_type == IncidentType.CAPACITY_EXHAUSTION:
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.DIAGNOSTIC,
                title="Check resource utilization",
                description="Examine CPU, memory, disk, and connection pool usage.",
                commands=[
                    f"kubectl top pod -l app={name_slug}",
                    f"kubectl exec -it $(kubectl get pod -l app={name_slug} -o name | head -1) -- df -h",
                ],
                expected_outcome="Resource exhaustion point identified.",
                timeout_minutes=5,
            ))
            order += 1

        if incident_type == IncidentType.DATA_CORRUPTION:
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.DIAGNOSTIC,
                title="Assess data integrity",
                description="Run integrity checks on affected data stores.",
                commands=[
                    f"kubectl exec -it $(kubectl get pod -l app={name_slug} -o name | head -1) "
                    "-- pg_dump --schema-only | md5sum",
                ],
                expected_outcome="Scope of data corruption determined.",
                timeout_minutes=10,
            ))
            order += 1

        if incident_type == IncidentType.SECURITY_BREACH:
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.DIAGNOSTIC,
                title="Investigate security indicators",
                description="Check access logs and audit trail for unauthorized activity.",
                commands=[
                    f"kubectl logs -l app={name_slug} --tail=500 | grep -i 'auth\\|unauthorized\\|forbidden'",
                    "aws cloudtrail lookup-events --max-items 20",
                ],
                expected_outcome="Breach vector and scope identified.",
                timeout_minutes=10,
            ))
            order += 1

        # Check dependencies
        dependencies = self._graph.get_dependencies(component_id)
        if dependencies:
            dep_names = ", ".join(d.name for d in dependencies)
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.DIAGNOSTIC,
                title="Check downstream dependencies",
                description=f"Verify health of dependencies: {dep_names}.",
                commands=[
                    f"kubectl get pods -l app={d.name.lower().replace(' ', '-')} -o wide"
                    for d in dependencies
                ],
                expected_outcome="Dependency health confirmed.",
                timeout_minutes=5,
            ))
            order += 1

        # --- Mitigation steps ---

        # Circuit breaker check (if dependencies have circuit breakers)
        has_cb = False
        for dep_comp in dependencies:
            edge = self._graph.get_dependency_edge(component_id, dep_comp.id)
            if edge and edge.circuit_breaker.enabled:
                has_cb = True
                break
        if has_cb:
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.MITIGATION,
                title="Verify circuit breakers",
                description="Check circuit breaker states for dependencies.",
                commands=[
                    f"kubectl exec -it $(kubectl get pod -l app={name_slug} -o name | head -1) "
                    "-- curl -s localhost:8080/actuator/circuitbreakers",
                ],
                expected_outcome="Circuit breakers in expected state.",
                timeout_minutes=3,
            ))
            order += 1

        # Failover step
        if comp.failover.enabled:
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.MITIGATION,
                title="Initiate failover",
                description=(
                    f"Trigger failover for {comp.name}. "
                    f"Estimated promotion time: {comp.failover.promotion_time_seconds}s."
                ),
                commands=[
                    f"kubectl exec -it $(kubectl get pod -l app={name_slug} -o name | head -1) "
                    "-- pg_ctl promote" if comp.type == ComponentType.DATABASE else
                    f"kubectl rollout restart deployment/{name_slug}",
                ],
                expected_outcome="Failover completed and standby promoted to primary.",
                timeout_minutes=int(comp.failover.promotion_time_seconds / 60) + 2,
                requires_approval=True,
            ))
            order += 1

        # Scaling step (if autoscaling or replicas > 1)
        if comp.autoscaling.enabled:
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.MITIGATION,
                title="Scale up component",
                description=f"Increase replicas for {comp.name} to handle load.",
                commands=[
                    f"kubectl scale deployment/{name_slug} "
                    f"--replicas={comp.autoscaling.max_replicas}",
                ],
                expected_outcome=f"Scaled to {comp.autoscaling.max_replicas} replicas.",
                timeout_minutes=5,
            ))
            order += 1
        elif comp.replicas > 1:
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.MITIGATION,
                title="Verify replica health",
                description=f"Ensure all {comp.replicas} replicas are running.",
                commands=[
                    f"kubectl get pods -l app={name_slug} -o wide",
                ],
                expected_outcome=f"All {comp.replicas} replicas healthy.",
                timeout_minutes=3,
            ))
            order += 1

        # Restart step (general mitigation)
        mit_cmds = [c.format(name=name_slug) for c in cmd_templates.get("mitigation", [])]
        if mit_cmds:
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.MITIGATION,
                title=f"Restart {comp.name}",
                description=f"Perform a rolling restart of {comp.name}.",
                commands=mit_cmds,
                expected_outcome=f"{comp.name} restarted successfully.",
                timeout_minutes=10,
                requires_approval=incident_type == IncidentType.DATA_CORRUPTION,
            ))
            order += 1

        # Security-specific mitigation
        if incident_type == IncidentType.SECURITY_BREACH:
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.MITIGATION,
                title="Isolate affected component",
                description=f"Apply network policy to isolate {comp.name}.",
                commands=[
                    f"kubectl apply -f network-policy-isolate-{name_slug}.yaml",
                    "aws ec2 modify-instance-attribute --groups sg-isolated",
                ],
                expected_outcome="Component network access restricted.",
                timeout_minutes=5,
                requires_approval=True,
            ))
            order += 1

        # Data corruption specific: restore from backup
        if incident_type == IncidentType.DATA_CORRUPTION and comp.security.backup_enabled:
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.MITIGATION,
                title="Restore from backup",
                description="Restore data from the most recent verified backup.",
                commands=[
                    f"aws s3 cp s3://backups/{name_slug}/latest.sql.gz /tmp/restore.sql.gz",
                    "gunzip /tmp/restore.sql.gz",
                    f"psql -h {name_slug} -U admin -d main < /tmp/restore.sql",
                ],
                expected_outcome="Data restored from backup.",
                timeout_minutes=30,
                requires_approval=True,
            ))
            order += 1

        # --- Verification steps ---
        ver_cmds = [c.format(name=name_slug) for c in cmd_templates.get("verification", [])]
        steps.append(RunbookStep(
            order=order,
            step_type=StepType.VERIFICATION,
            title="Verify component recovery",
            description=f"Confirm that {comp.name} is operating normally.",
            commands=ver_cmds,
            expected_outcome=f"{comp.name} healthy and serving traffic.",
            timeout_minutes=5,
        ))
        order += 1

        # Verify dependents
        dependents = self._graph.get_dependents(component_id)
        if dependents:
            dep_names = ", ".join(d.name for d in dependents)
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.VERIFICATION,
                title="Verify dependent services",
                description=f"Confirm dependent services are recovered: {dep_names}.",
                commands=[
                    f"kubectl get pods -l app={d.name.lower().replace(' ', '-')} -o wide"
                    for d in dependents
                ],
                expected_outcome="All dependent services operational.",
                timeout_minutes=5,
            ))
            order += 1

        # Log verification for compliance
        if comp.security.log_enabled:
            steps.append(RunbookStep(
                order=order,
                step_type=StepType.VERIFICATION,
                title="Verify logging integrity",
                description="Ensure all incident actions were logged properly.",
                commands=[
                    f"kubectl logs -l app={name_slug} --since=1h | wc -l",
                ],
                expected_outcome="Logging operational and incident actions recorded.",
                timeout_minutes=3,
            ))
            order += 1

        # --- Escalation step ---
        steps.append(RunbookStep(
            order=order,
            step_type=StepType.ESCALATION,
            title="Escalate if unresolved",
            description=(
                "If the issue persists after completing above steps, escalate "
                "to the next tier of support."
            ),
            commands=[],
            expected_outcome="Issue escalated and acknowledged by next tier.",
            timeout_minutes=5,
        ))
        order += 1

        # --- Final communication ---
        steps.append(RunbookStep(
            order=order,
            step_type=StepType.COMMUNICATION,
            title="Send resolution update",
            description="Notify stakeholders that the incident has been resolved.",
            commands=[
                f"pagerduty-cli resolve --service {name_slug}",
            ],
            expected_outcome="All stakeholders notified of resolution.",
            timeout_minutes=2,
        ))

        return steps

    def _estimate_resolution(
        self, component_id: str, incident_type: IncidentType
    ) -> int:
        """Estimate resolution time in minutes."""
        base = _RESOLUTION_ESTIMATES.get(incident_type, 30)
        comp = self._graph.get_component(component_id)
        if comp is None:
            return base

        # Failover reduces resolution time
        if comp.failover.enabled:
            base = int(base * 0.6)

        # Autoscaling reduces capacity issues
        if comp.autoscaling.enabled and incident_type == IncidentType.CAPACITY_EXHAUSTION:
            base = int(base * 0.5)

        # More dependents = longer resolution (blast radius)
        dependents = self._graph.get_dependents(component_id)
        if len(dependents) > 3:
            base = int(base * 1.5)
        elif len(dependents) > 1:
            base = int(base * 1.2)

        return max(5, base)  # at least 5 minutes

    def _escalation_contacts(self, severity: str) -> list[str]:
        """Return escalation contacts based on severity level."""
        contacts = ["On-call engineer", "Team lead"]
        if severity in ("SEV1", "SEV2"):
            contacts.append("Engineering manager")
            contacts.append("VP of Engineering")
        if severity == "SEV1":
            contacts.append("CTO")
            contacts.append("Incident commander")
        return contacts

    def _prerequisites(
        self, component_id: str, incident_type: IncidentType
    ) -> list[str]:
        """Generate prerequisites for the runbook."""
        comp = self._graph.get_component(component_id)
        assert comp is not None

        prereqs = [
            "kubectl CLI configured and authenticated",
            f"Access to {comp.name} namespace/cluster",
        ]

        if comp.type == ComponentType.DATABASE:
            prereqs.append("Database admin credentials available")
        if comp.security.encryption_at_rest:
            prereqs.append("Encryption keys accessible for data recovery")
        if comp.security.encryption_in_transit:
            prereqs.append("TLS certificates available")
        if incident_type == IncidentType.SECURITY_BREACH:
            prereqs.append("Security team notified and engaged")
            prereqs.append("Forensic tools available")

        return prereqs
