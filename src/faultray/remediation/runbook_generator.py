# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Auto Runbook Generator.

Automatically generates incident response runbooks based on simulation
results. Each critical/warning scenario gets a detailed runbook with:
- Detection steps (what alerts to look for)
- Diagnosis steps (how to confirm the issue)
- Mitigation steps (immediate actions)
- Recovery steps (full recovery procedure)
- Post-incident steps (review and prevention)
- Communication templates (status page, Slack messages)

Runbooks are generated in Markdown format and can be exported to
Confluence, Notion, or as standalone HTML.
"""

from __future__ import annotations

import html as html_mod
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeEffect
from faultray.simulator.engine import ScenarioResult, SimulationReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RunbookStep:
    """A single step in a runbook."""

    order: int
    phase: str  # detection, diagnosis, mitigation, recovery, post_incident
    title: str
    description: str
    commands: list[str] = field(default_factory=list)
    expected_outcome: str = ""
    escalation: str | None = None
    time_estimate: str = "5 min"

    def to_dict(self) -> dict:
        return {
            "order": self.order,
            "phase": self.phase,
            "title": self.title,
            "description": self.description,
            "commands": self.commands,
            "expected_outcome": self.expected_outcome,
            "escalation": self.escalation,
            "time_estimate": self.time_estimate,
        }


@dataclass
class CommunicationTemplate:
    """A communication template for incident response."""

    channel: str  # status_page, slack, email, pagerduty
    severity: str
    template: str

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "severity": self.severity,
            "template": self.template,
        }


@dataclass
class Runbook:
    """A complete incident response runbook."""

    id: str
    title: str
    scenario: str
    severity: str
    affected_components: list[str] = field(default_factory=list)
    blast_radius: int = 0
    estimated_recovery_time: str = "15 min"
    steps: list[RunbookStep] = field(default_factory=list)
    communication_templates: list[CommunicationTemplate] = field(default_factory=list)
    related_runbooks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    owner: str = "SRE Team"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "scenario": self.scenario,
            "severity": self.severity,
            "affected_components": self.affected_components,
            "blast_radius": self.blast_radius,
            "estimated_recovery_time": self.estimated_recovery_time,
            "steps": [s.to_dict() for s in self.steps],
            "communication_templates": [c.to_dict() for c in self.communication_templates],
            "related_runbooks": self.related_runbooks,
            "tags": self.tags,
            "last_updated": self.last_updated.isoformat(),
            "owner": self.owner,
        }


@dataclass
class RunbookLibrary:
    """Collection of generated runbooks with coverage statistics."""

    runbooks: list[Runbook] = field(default_factory=list)
    total_scenarios_covered: int = 0
    uncovered_scenarios: list[str] = field(default_factory=list)
    coverage_percentage: float = 0.0

    def to_dict(self) -> dict:
        return {
            "runbooks": [r.to_dict() for r in self.runbooks],
            "total_scenarios_covered": self.total_scenarios_covered,
            "uncovered_scenarios": self.uncovered_scenarios,
            "coverage_percentage": round(self.coverage_percentage, 1),
        }


# ---------------------------------------------------------------------------
# Component type category mapping for step generation
# ---------------------------------------------------------------------------

_COMPONENT_CATEGORY: dict[str, str] = {
    ComponentType.DATABASE.value: "database",
    ComponentType.CACHE.value: "cache",
    ComponentType.QUEUE.value: "queue",
    ComponentType.LOAD_BALANCER.value: "network",
    ComponentType.DNS.value: "network",
    ComponentType.EXTERNAL_API.value: "external",
    ComponentType.WEB_SERVER.value: "service",
    ComponentType.APP_SERVER.value: "service",
    ComponentType.STORAGE.value: "storage",
    ComponentType.CUSTOM.value: "service",
}


# ---------------------------------------------------------------------------
# Runbook Generator
# ---------------------------------------------------------------------------


class RunbookGenerator:
    """Generates incident response runbooks from simulation results."""

    def generate(
        self, graph: InfraGraph, sim_report: SimulationReport
    ) -> RunbookLibrary:
        """Generate runbooks for all critical and warning scenarios."""
        runbooks: list[Runbook] = []
        covered = 0
        uncovered: list[str] = []

        actionable = sim_report.critical_findings + sim_report.warnings
        for result in actionable:
            try:
                rb = self.generate_for_scenario(graph, result)
                runbooks.append(rb)
                covered += 1
            except Exception as exc:
                logger.warning(
                    "Failed to generate runbook for scenario %s: %s",
                    result.scenario.name,
                    exc,
                )
                uncovered.append(result.scenario.name)

        # Passed scenarios are not uncovered - they just don't need runbooks
        total = len(actionable)
        coverage = (covered / total * 100.0) if total > 0 else 100.0

        # Link related runbooks by shared affected components
        self._link_related(runbooks)

        return RunbookLibrary(
            runbooks=runbooks,
            total_scenarios_covered=covered,
            uncovered_scenarios=uncovered,
            coverage_percentage=coverage,
        )

    def generate_for_scenario(
        self, graph: InfraGraph, result: ScenarioResult
    ) -> Runbook:
        """Generate a runbook for a single scenario result."""
        scenario = result.scenario
        cascade = result.cascade
        effects = cascade.effects

        affected_ids = [e.component_id for e in effects]
        severity = "critical" if result.is_critical else "warning"
        blast = len(affected_ids)

        # Determine primary failure type from scenario faults
        primary_fault = None
        primary_comp_id = None
        if scenario.faults:
            primary_fault = scenario.faults[0].fault_type.value
            primary_comp_id = scenario.faults[0].target_component_id

        # Determine component category for the primary target
        comp = graph.get_component(primary_comp_id) if primary_comp_id else None
        category = "service"
        if comp:
            category = _COMPONENT_CATEGORY.get(comp.type.value, "service")

        steps = self._generate_steps(
            graph, effects, primary_fault, primary_comp_id, category
        )
        comms = self._generate_communications(
            severity, primary_comp_id or "unknown", blast, effects
        )

        # Estimate recovery time
        recovery_time = self._estimate_recovery_time(effects, comp)

        # Tags
        tags = [severity]
        if primary_fault:
            tags.append(primary_fault)
        if category:
            tags.append(category)

        runbook_id = f"rb-{scenario.id}"

        return Runbook(
            id=runbook_id,
            title=f"Runbook: {scenario.name}",
            scenario=scenario.name,
            severity=severity,
            affected_components=affected_ids,
            blast_radius=blast,
            estimated_recovery_time=recovery_time,
            steps=steps,
            communication_templates=comms,
            tags=tags,
        )

    def generate_for_component(
        self, graph: InfraGraph, component_id: str
    ) -> Runbook:
        """Generate a generic runbook for a component failure."""
        comp = graph.get_component(component_id)
        if comp is None:
            raise ValueError(f"Component not found: {component_id}")

        category = _COMPONENT_CATEGORY.get(comp.type.value, "service")
        affected = graph.get_all_affected(component_id)

        # Build synthetic effects
        effects = [
            CascadeEffect(
                component_id=comp.id,
                component_name=comp.name,
                health=HealthStatus.DOWN,
                reason="Component failure (generic runbook)",
            )
        ]

        steps = self._generate_steps(
            graph, effects, "component_down", component_id, category
        )
        comms = self._generate_communications(
            "critical", component_id, len(affected) + 1, effects
        )
        recovery_time = self._estimate_recovery_time(effects, comp)

        return Runbook(
            id=f"rb-component-{component_id}",
            title=f"Runbook: {comp.name} Failure",
            scenario=f"{comp.name} component failure",
            severity="critical",
            affected_components=[component_id] + list(affected),
            blast_radius=len(affected) + 1,
            estimated_recovery_time=recovery_time,
            steps=steps,
            communication_templates=comms,
            tags=["critical", "component_down", category],
        )

    # ------------------------------------------------------------------
    # Export methods
    # ------------------------------------------------------------------

    def to_markdown(self, runbook: Runbook) -> str:
        """Convert a runbook to Markdown format."""
        lines: list[str] = []
        lines.append(f"# {runbook.title}")
        lines.append("")
        lines.append(f"**ID:** {runbook.id}  ")
        lines.append(f"**Severity:** {runbook.severity.upper()}  ")
        lines.append(f"**Scenario:** {runbook.scenario}  ")
        lines.append(f"**Blast Radius:** {runbook.blast_radius} components  ")
        lines.append(f"**Estimated Recovery Time:** {runbook.estimated_recovery_time}  ")
        lines.append(f"**Owner:** {runbook.owner}  ")
        lines.append(f"**Last Updated:** {runbook.last_updated.strftime('%Y-%m-%d %H:%M UTC')}  ")
        lines.append(f"**Tags:** {', '.join(runbook.tags)}  ")
        lines.append("")

        # Affected components
        lines.append("## Affected Components")
        lines.append("")
        for comp_id in runbook.affected_components:
            lines.append(f"- `{comp_id}`")
        lines.append("")

        # Steps grouped by phase
        phases = ["detection", "diagnosis", "mitigation", "recovery", "post_incident"]
        phase_titles = {
            "detection": "Detection",
            "diagnosis": "Diagnosis",
            "mitigation": "Mitigation",
            "recovery": "Recovery",
            "post_incident": "Post-Incident",
        }

        for phase in phases:
            phase_steps = [s for s in runbook.steps if s.phase == phase]
            if not phase_steps:
                continue

            lines.append(f"## Phase: {phase_titles.get(phase, phase)}")
            lines.append("")

            for step in phase_steps:
                lines.append(f"### Step {step.order}: {step.title}")
                lines.append("")
                lines.append(step.description)
                lines.append("")

                if step.commands:
                    lines.append("**Commands:**")
                    lines.append("")
                    lines.append("```bash")
                    for cmd in step.commands:
                        lines.append(cmd)
                    lines.append("```")
                    lines.append("")

                if step.expected_outcome:
                    lines.append(f"**Expected Outcome:** {step.expected_outcome}")
                    lines.append("")

                if step.escalation:
                    lines.append(f"**Escalation:** {step.escalation}")
                    lines.append("")

                lines.append(f"**Time Estimate:** {step.time_estimate}")
                lines.append("")

        # Communication templates
        if runbook.communication_templates:
            lines.append("## Communication Templates")
            lines.append("")
            for tmpl in runbook.communication_templates:
                lines.append(f"### {tmpl.channel.replace('_', ' ').title()} ({tmpl.severity})")
                lines.append("")
                lines.append("```")
                lines.append(tmpl.template)
                lines.append("```")
                lines.append("")

        # Related runbooks
        if runbook.related_runbooks:
            lines.append("## Related Runbooks")
            lines.append("")
            for related in runbook.related_runbooks:
                lines.append(f"- {related}")
            lines.append("")

        return "\n".join(lines)

    def to_html(self, runbook: Runbook) -> str:
        """Convert a runbook to standalone HTML format."""
        md_content = self.to_markdown(runbook)
        html_mod.escape(md_content)

        # Simple markdown-to-HTML conversion
        html_body = self._md_to_html(md_content)

        severity_colors = {
            "critical": "#dc3545",
            "warning": "#ffc107",
            "info": "#17a2b8",
        }
        badge_color = severity_colors.get(runbook.severity, "#6c757d")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_mod.escape(runbook.title)}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem;
            color: #333;
            line-height: 1.6;
        }}
        h1 {{ border-bottom: 2px solid #333; padding-bottom: 0.5rem; }}
        h2 {{ color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 0.3rem; margin-top: 2rem; }}
        h3 {{ color: #34495e; }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            color: white;
            font-weight: bold;
            font-size: 0.85rem;
            background: {badge_color};
        }}
        .meta {{ background: #f8f9fa; padding: 1rem; border-radius: 8px; margin: 1rem 0; }}
        .meta p {{ margin: 0.3rem 0; }}
        pre {{
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 1rem;
            border-radius: 6px;
            overflow-x: auto;
        }}
        code {{ background: #f1f1f1; padding: 0.15rem 0.4rem; border-radius: 3px; font-size: 0.9em; }}
        pre code {{ background: none; padding: 0; }}
        ul {{ padding-left: 1.5rem; }}
        .step-card {{
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 1rem;
            margin: 0.5rem 0;
        }}
        .time-badge {{
            background: #e3f2fd;
            color: #1565c0;
            padding: 0.15rem 0.5rem;
            border-radius: 3px;
            font-size: 0.8rem;
        }}
    </style>
</head>
<body>
{html_body}
</body>
</html>"""

    def export_library(
        self,
        library: RunbookLibrary,
        output_dir: Path,
        format: str = "markdown",
    ) -> list[Path]:
        """Export all runbooks in a library to files."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for runbook in library.runbooks:
            safe_name = runbook.id.replace("/", "_").replace(" ", "_")
            if format == "html":
                ext = ".html"
                content = self.to_html(runbook)
            else:
                ext = ".md"
                content = self.to_markdown(runbook)

            path = output_dir / f"{safe_name}{ext}"
            path.write_text(content, encoding="utf-8")
            paths.append(path)

        # Write index file
        index_path = output_dir / f"index{'.html' if format == 'html' else '.md'}"
        index_content = self._generate_index(library, format)
        index_path.write_text(index_content, encoding="utf-8")
        paths.insert(0, index_path)

        return paths

    # ------------------------------------------------------------------
    # Step generation logic
    # ------------------------------------------------------------------

    def _generate_steps(
        self,
        graph: InfraGraph,
        effects: list[CascadeEffect],
        fault_type: str | None,
        primary_comp_id: str | None,
        category: str,
    ) -> list[RunbookStep]:
        """Generate runbook steps based on failure type and component category."""
        steps: list[RunbookStep] = []
        order = 1
        comp_name = primary_comp_id or "component"
        comp = graph.get_component(primary_comp_id) if primary_comp_id else None
        if comp:
            comp_name = comp.name

        # ---- Detection ----
        steps.append(RunbookStep(
            order=order,
            phase="detection",
            title=f"Check monitoring dashboard for {comp_name} alerts",
            description=(
                f"Review the monitoring dashboard for any alerts related to {comp_name}. "
                "Check for anomalies in error rates, latency, and availability metrics."
            ),
            commands=[
                f"# Check alerting system for {comp_name} alerts",
                f"# Example: kubectl get events --field-selector involvedObject.name={primary_comp_id}",
            ],
            expected_outcome="Identify active alerts and their severity",
            time_estimate="1 min",
        ))
        order += 1

        steps.append(RunbookStep(
            order=order,
            phase="detection",
            title="Verify health check status",
            description=f"Confirm the health status of {comp_name} by running health checks.",
            commands=[
                f"# curl -s http://{primary_comp_id}:8080/health",
                f"kubectl get pods -l app={primary_comp_id}",
            ],
            expected_outcome="Health check returns status or connection error confirming the issue",
            time_estimate="1 min",
        ))
        order += 1

        if category == "database":
            steps.append(RunbookStep(
                order=order,
                phase="detection",
                title="Check database connectivity",
                description="Verify database is accepting connections and responding to queries.",
                commands=[
                    "# Check database status",
                    f"kubectl exec -it $(kubectl get pod -l app={primary_comp_id} -o jsonpath='{{.items[0].metadata.name}}') -- pg_isready",
                ],
                expected_outcome="Database reports accepting or refusing connections",
                time_estimate="2 min",
            ))
            order += 1

        # ---- Diagnosis ----
        steps.append(RunbookStep(
            order=order,
            phase="diagnosis",
            title=f"Check application logs for {comp_name}",
            description=f"Review recent logs to identify the root cause of the {comp_name} issue.",
            commands=[
                f"kubectl logs -l app={primary_comp_id} --tail=100",
                f"kubectl logs -l app={primary_comp_id} --previous --tail=50",
            ],
            expected_outcome="Identify error messages, stack traces, or anomalous log patterns",
            escalation="If logs show data corruption, escalate to DBA team immediately",
            time_estimate="5 min",
        ))
        order += 1

        steps.append(RunbookStep(
            order=order,
            phase="diagnosis",
            title=f"Check resource utilization for {comp_name}",
            description="Verify CPU, memory, and disk usage to rule out resource exhaustion.",
            commands=[
                f"kubectl top pod -l app={primary_comp_id}",
                f"kubectl describe pod -l app={primary_comp_id}",
            ],
            expected_outcome="Resource usage within normal bounds or identify resource bottleneck",
            time_estimate="2 min",
        ))
        order += 1

        steps.append(RunbookStep(
            order=order,
            phase="diagnosis",
            title="Verify dependencies are reachable",
            description=f"Check that all downstream dependencies of {comp_name} are healthy.",
            commands=[
                "# Verify connectivity to dependencies",
                f"kubectl exec -it $(kubectl get pod -l app={primary_comp_id} -o jsonpath='{{.items[0].metadata.name}}') -- nslookup <dependency-host>",
            ],
            expected_outcome="All dependencies are reachable and responding",
            time_estimate="3 min",
        ))
        order += 1

        if category == "database":
            steps.append(RunbookStep(
                order=order,
                phase="diagnosis",
                title="Check replication lag",
                description="Verify replication status and lag on read replicas.",
                commands=[
                    "# PostgreSQL: SELECT * FROM pg_stat_replication;",
                    "# MySQL: SHOW SLAVE STATUS\\G",
                ],
                expected_outcome="Replication lag within acceptable bounds",
                escalation="If replication lag > 30s, escalate to DBA",
                time_estimate="2 min",
            ))
            order += 1

        if category == "network":
            steps.append(RunbookStep(
                order=order,
                phase="diagnosis",
                title="Check security groups and firewall rules",
                description="Verify network connectivity and firewall rules are not blocking traffic.",
                commands=[
                    "# Check security group rules",
                    "aws ec2 describe-security-groups --group-ids <sg-id>",
                    "# Verify DNS resolution",
                    f"nslookup {primary_comp_id}",
                ],
                expected_outcome="Network rules allow expected traffic",
                time_estimate="3 min",
            ))
            order += 1

        # ---- Mitigation ----
        replicas = comp.replicas if comp else 1

        if comp and comp.autoscaling.enabled:
            steps.append(RunbookStep(
                order=order,
                phase="mitigation",
                title="Verify autoscaling is triggered",
                description="Check if the horizontal pod autoscaler has triggered scaling.",
                commands=[
                    f"kubectl get hpa -l app={primary_comp_id}",
                    f"kubectl describe hpa {primary_comp_id}",
                ],
                expected_outcome="HPA has triggered and new pods are being provisioned",
                time_estimate="2 min",
            ))
            order += 1

        if comp and comp.failover.enabled:
            steps.append(RunbookStep(
                order=order,
                phase="mitigation",
                title="Verify failover activation",
                description="Confirm that failover has been triggered and the standby is active.",
                commands=[
                    f"# Check failover status for {comp_name}",
                    f"kubectl get pods -l app={primary_comp_id} -o wide",
                ],
                expected_outcome="Standby instance has been promoted and is serving traffic",
                time_estimate="3 min",
            ))
            order += 1

        steps.append(RunbookStep(
            order=order,
            phase="mitigation",
            title=f"Consider manual scaling for {comp_name}",
            description=(
                f"If automatic recovery is not sufficient, manually scale {comp_name}."
            ),
            commands=[
                f"kubectl scale deployment {primary_comp_id} --replicas={replicas + 1}",
            ],
            expected_outcome=f"{comp_name} running with additional capacity",
            escalation="If scaling doesn't resolve the issue within 5 minutes, escalate to on-call SRE",
            time_estimate="2 min",
        ))
        order += 1

        if category == "database":
            steps.append(RunbookStep(
                order=order,
                phase="mitigation",
                title="Initiate database failover if needed",
                description="If the primary database is unrecoverable, initiate failover to standby.",
                commands=[
                    "# AWS RDS: aws rds failover-db-cluster --db-cluster-identifier <cluster>",
                    "# PostgreSQL: pg_ctl promote -D /var/lib/postgresql/data",
                ],
                expected_outcome="Standby promoted to primary, traffic redirected",
                escalation="DBA approval required before initiating manual failover",
                time_estimate="5 min",
            ))
            order += 1

        if category == "network":
            steps.append(RunbookStep(
                order=order,
                phase="mitigation",
                title="Check load balancer health",
                description="Verify load balancer is routing traffic correctly.",
                commands=[
                    "# Check LB target health",
                    "aws elbv2 describe-target-health --target-group-arn <arn>",
                ],
                expected_outcome="Healthy targets are receiving traffic",
                time_estimate="2 min",
            ))
            order += 1

        # ---- Recovery ----
        steps.append(RunbookStep(
            order=order,
            phase="recovery",
            title="Apply fix based on root cause",
            description=(
                "Once the root cause is identified, apply the appropriate fix. "
                "This may include configuration changes, code deployments, or infrastructure updates."
            ),
            commands=[
                "# Apply fix specific to the identified root cause",
                f"# kubectl rollout restart deployment/{primary_comp_id}",
            ],
            expected_outcome="Root cause addressed and fix deployed",
            time_estimate="10 min",
        ))
        order += 1

        steps.append(RunbookStep(
            order=order,
            phase="recovery",
            title=f"Verify {comp_name} is healthy and serving traffic",
            description="Confirm the component has recovered and is processing requests normally.",
            commands=[
                f"kubectl get pods -l app={primary_comp_id}",
                f"# curl -s http://{primary_comp_id}:8080/health",
            ],
            expected_outcome="All pods running, health checks passing, metrics normalizing",
            time_estimate="5 min",
        ))
        order += 1

        steps.append(RunbookStep(
            order=order,
            phase="recovery",
            title="Verify dependent services have recovered",
            description=(
                "Check all services that depend on this component to ensure "
                "they have also recovered from the cascade failure."
            ),
            commands=[
                "# Check dependent service health",
                "kubectl get pods --all-namespaces | grep -v Running",
            ],
            expected_outcome="All dependent services healthy and operational",
            time_estimate="5 min",
        ))
        order += 1

        if category == "database":
            steps.append(RunbookStep(
                order=order,
                phase="recovery",
                title="Verify data integrity post-recovery",
                description="Run data integrity checks to ensure no data was corrupted or lost.",
                commands=[
                    "# Run application-specific data integrity checks",
                    "# PostgreSQL: SELECT count(*) FROM critical_table;",
                ],
                expected_outcome="Data integrity verified, no corruption detected",
                escalation="If data corruption is found, engage DBA and data recovery team",
                time_estimate="10 min",
            ))
            order += 1

        # ---- Post-Incident ----
        steps.append(RunbookStep(
            order=order,
            phase="post_incident",
            title="Update status page to resolved",
            description="Communicate resolution to stakeholders via status page and Slack.",
            commands=[],
            expected_outcome="All stakeholders informed of resolution",
            time_estimate="2 min",
        ))
        order += 1

        steps.append(RunbookStep(
            order=order,
            phase="post_incident",
            title="Schedule blameless post-mortem",
            description=(
                "Schedule a blameless post-mortem within 48 hours. "
                "Document timeline, root cause, impact, and action items."
            ),
            commands=[],
            expected_outcome="Post-mortem scheduled with all relevant team members",
            time_estimate="5 min",
        ))
        order += 1

        steps.append(RunbookStep(
            order=order,
            phase="post_incident",
            title="Create action items for prevention",
            description=(
                "Based on root cause analysis, create action items to prevent recurrence. "
                "Consider: additional monitoring, autoscaling, circuit breakers, redundancy."
            ),
            commands=[],
            expected_outcome="Action items created and assigned with due dates",
            time_estimate="15 min",
        ))
        order += 1

        return steps

    def _generate_communications(
        self,
        severity: str,
        component_id: str,
        blast_radius: int,
        effects: list[CascadeEffect],
    ) -> list[CommunicationTemplate]:
        """Generate communication templates for the incident."""
        templates: list[CommunicationTemplate] = []

        # Determine impact description
        down_count = sum(1 for e in effects if e.health == HealthStatus.DOWN)
        degraded_count = sum(1 for e in effects if e.health == HealthStatus.DEGRADED)
        if down_count > 0:
            impact = f"{down_count} service(s) down, {degraded_count} degraded"
        elif degraded_count > 0:
            impact = f"{degraded_count} service(s) experiencing degraded performance"
        else:
            impact = "potential service impact detected"

        # Status Page - Investigating
        templates.append(CommunicationTemplate(
            channel="status_page",
            severity=severity,
            template=(
                f"We are currently investigating issues with {component_id}. "
                f"Some users may experience {impact}. "
                "We are working to resolve this as quickly as possible. "
                "Next update in 30 minutes."
            ),
        ))

        # Status Page - Identified
        templates.append(CommunicationTemplate(
            channel="status_page",
            severity=severity,
            template=(
                f"We have identified the issue affecting {component_id}. "
                "The root cause is {{root_cause}}. "
                "We are implementing a fix. Estimated resolution: {{eta}}."
            ),
        ))

        # Status Page - Resolved
        templates.append(CommunicationTemplate(
            channel="status_page",
            severity=severity,
            template=(
                f"The issue affecting {component_id} has been resolved. "
                "All services are operating normally. "
                "We will publish a post-incident report within 48 hours."
            ),
        ))

        # Slack Alert
        severity_emoji = ":rotating_light:" if severity == "critical" else ":warning:"
        templates.append(CommunicationTemplate(
            channel="slack",
            severity=severity,
            template=(
                f"{severity_emoji} *INCIDENT* - {severity.upper()} - {component_id} failure detected\n"
                f"*Impact*: {impact}\n"
                f"*Blast Radius*: {blast_radius} components affected\n"
                f"*Runbook*: {{runbook_link}}"
            ),
        ))

        # PagerDuty
        if severity == "critical":
            templates.append(CommunicationTemplate(
                channel="pagerduty",
                severity=severity,
                template=(
                    f"CRITICAL: {component_id} failure - {blast_radius} components affected. "
                    f"Impact: {impact}. Immediate response required."
                ),
            ))

        return templates

    def _estimate_recovery_time(
        self, effects: list[CascadeEffect], comp=None
    ) -> str:
        """Estimate total recovery time based on effects and component config."""
        base_minutes = 15

        down_count = sum(1 for e in effects if e.health == HealthStatus.DOWN)
        if down_count > 3:
            base_minutes = 45
        elif down_count > 1:
            base_minutes = 30

        if comp:
            if comp.failover.enabled:
                base_minutes = max(5, base_minutes - 10)
            if comp.autoscaling.enabled:
                base_minutes = max(5, base_minutes - 5)

        if base_minutes >= 60:
            return f"{base_minutes // 60}h {base_minutes % 60}min"
        return f"{base_minutes} min"

    def _link_related(self, runbooks: list[Runbook]) -> None:
        """Link runbooks that share affected components."""
        for i, rb1 in enumerate(runbooks):
            s1 = set(rb1.affected_components)
            for j, rb2 in enumerate(runbooks):
                if i == j:
                    continue
                s2 = set(rb2.affected_components)
                if s1 & s2:
                    if rb2.id not in rb1.related_runbooks:
                        rb1.related_runbooks.append(rb2.id)

    def _generate_index(self, library: RunbookLibrary, format: str) -> str:
        """Generate an index file for the runbook library."""
        if format == "html":
            return self._generate_html_index(library)
        return self._generate_md_index(library)

    def _generate_md_index(self, library: RunbookLibrary) -> str:
        lines: list[str] = []
        lines.append("# Runbook Library")
        lines.append("")
        lines.append(f"**Total Runbooks:** {len(library.runbooks)}  ")
        lines.append(f"**Coverage:** {library.coverage_percentage:.1f}%  ")
        lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ")
        lines.append("")

        lines.append("## Runbooks")
        lines.append("")
        lines.append("| ID | Title | Severity | Blast Radius | Recovery Time |")
        lines.append("|---|---|---|---|---|")

        for rb in library.runbooks:
            lines.append(
                f"| [{rb.id}]({rb.id}.md) | {rb.title} | {rb.severity} "
                f"| {rb.blast_radius} | {rb.estimated_recovery_time} |"
            )
        lines.append("")

        if library.uncovered_scenarios:
            lines.append("## Uncovered Scenarios")
            lines.append("")
            for s in library.uncovered_scenarios:
                lines.append(f"- {s}")
            lines.append("")

        return "\n".join(lines)

    def _generate_html_index(self, library: RunbookLibrary) -> str:
        lines: list[str] = []
        lines.append("<!DOCTYPE html><html><head><title>Runbook Library</title>")
        lines.append("<style>body{font-family:sans-serif;max-width:900px;margin:0 auto;padding:2rem;}")
        lines.append("table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px;text-align:left}")
        lines.append("th{background:#f4f4f4}.critical{color:#dc3545}.warning{color:#ffc107}</style></head><body>")
        lines.append("<h1>Runbook Library</h1>")
        lines.append(f"<p>Total: {len(library.runbooks)} | Coverage: {library.coverage_percentage:.1f}%</p>")
        lines.append("<table><tr><th>ID</th><th>Title</th><th>Severity</th><th>Blast Radius</th><th>Recovery</th></tr>")
        for rb in library.runbooks:
            sev_class = rb.severity
            lines.append(
                f'<tr><td><a href="{rb.id}.html">{rb.id}</a></td>'
                f"<td>{html_mod.escape(rb.title)}</td>"
                f'<td class="{sev_class}">{rb.severity}</td>'
                f"<td>{rb.blast_radius}</td>"
                f"<td>{rb.estimated_recovery_time}</td></tr>"
            )
        lines.append("</table></body></html>")
        return "\n".join(lines)

    def _md_to_html(self, md: str) -> str:
        """Very basic markdown to HTML conversion for runbook export."""
        import re

        html_lines: list[str] = []
        in_code_block = False
        in_list = False

        for line in md.split("\n"):
            if line.startswith("```"):
                if in_code_block:
                    html_lines.append("</code></pre>")
                    in_code_block = False
                else:
                    html_lines.append("<pre><code>")
                    in_code_block = True
                continue

            if in_code_block:
                html_lines.append(html_mod.escape(line))
                continue

            # Headers
            if line.startswith("### "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h3>{html_mod.escape(line[4:])}</h3>")
            elif line.startswith("## "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h2>{html_mod.escape(line[3:])}</h2>")
            elif line.startswith("# "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h1>{html_mod.escape(line[2:])}</h1>")
            elif line.startswith("- "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                content = line[2:]
                # Handle inline code
                content = re.sub(r"`([^`]+)`", r"<code>\1</code>", html_mod.escape(content))
                html_lines.append(f"<li>{content}</li>")
            elif line.startswith("| "):
                # Skip table rendering in HTML (already rendered via structured HTML)
                continue
            elif line.startswith("**") and line.endswith("**"):
                html_lines.append(f"<p><strong>{html_mod.escape(line.strip('*'))}</strong></p>")
            elif line.strip():
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                # Handle bold and inline code
                escaped = html_mod.escape(line)
                escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
                escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
                # Handle trailing double space as <br>
                if escaped.endswith("  "):
                    escaped = escaped.rstrip() + "<br>"
                html_lines.append(f"<p>{escaped}</p>")
            else:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False

        if in_list:
            html_lines.append("</ul>")
        if in_code_block:
            html_lines.append("</code></pre>")

        return "\n".join(html_lines)
