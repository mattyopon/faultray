"""Incident Post-Mortem Generator.

Auto-generates blameless incident post-mortem documents from simulation
results. Each critical/warning scenario produces a post-mortem that
follows the industry-standard format:

1. Incident Summary
2. Impact Assessment
3. Timeline of Events
4. Root Cause Analysis
5. Contributing Factors
6. What Went Well / What Didn't
7. Action Items
8. Lessons Learned
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain
from faultray.simulator.engine import ScenarioResult, SimulationReport
from faultray.simulator.scenarios import FaultType


@dataclass
class PostMortemSection:
    """A single section of a post-mortem document."""

    title: str
    content: str  # markdown


@dataclass
class ActionItem:
    """An actionable item from a post-mortem."""

    id: str
    description: str
    owner: str  # "SRE Team", "Platform Team", "Application Team"
    priority: str  # "P0", "P1", "P2", "P3"
    status: str  # "open", "in_progress", "done"
    due_date: str
    category: str  # "prevention", "detection", "mitigation", "process"


@dataclass
class PostMortem:
    """A complete post-mortem document for a simulated incident."""

    incident_id: str
    title: str
    severity: str  # "SEV1", "SEV2", "SEV3", "SEV4"
    date: datetime = field(default_factory=datetime.now)
    duration_estimate: str = ""
    summary: str = ""
    impact: str = ""
    root_cause: str = ""
    timeline: list[tuple[str, str]] = field(default_factory=list)  # (time_offset, event)
    contributing_factors: list[str] = field(default_factory=list)
    what_went_well: list[str] = field(default_factory=list)
    what_didnt: list[str] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)
    affected_components: list[str] = field(default_factory=list)
    blast_radius: int = 0
    sections: list[PostMortemSection] = field(default_factory=list)


@dataclass
class PostMortemLibrary:
    """Collection of post-mortems from a simulation run."""

    postmortems: list[PostMortem] = field(default_factory=list)
    total_action_items: int = 0
    critical_postmortems: int = 0
    common_themes: list[str] = field(default_factory=list)


class PostMortemGenerator:
    """Generates post-mortem documents from simulation results."""

    def generate(
        self, graph: InfraGraph, sim_report: SimulationReport
    ) -> PostMortemLibrary:
        """Generate post-mortems for all critical and warning scenarios."""
        postmortems: list[PostMortem] = []

        # Process critical findings first, then warnings
        relevant = sim_report.critical_findings + sim_report.warnings

        for result in relevant:
            pm = self.generate_for_scenario(graph, result)
            postmortems.append(pm)

        total_action_items = sum(len(pm.action_items) for pm in postmortems)
        critical_count = sum(
            1 for pm in postmortems if pm.severity in ("SEV1", "SEV2")
        )

        # Identify common themes
        themes = self._identify_common_themes(postmortems, graph)

        return PostMortemLibrary(
            postmortems=postmortems,
            total_action_items=total_action_items,
            critical_postmortems=critical_count,
            common_themes=themes,
        )

    def generate_for_scenario(
        self, graph: InfraGraph, result: ScenarioResult
    ) -> PostMortem:
        """Generate a post-mortem for a single scenario result."""
        scenario = result.scenario
        cascade = result.cascade

        # Generate a stable incident ID from scenario
        incident_id = self._generate_incident_id(scenario.id)

        # Determine severity
        severity = self._classify_severity(result.risk_score)

        # Extract affected components
        affected = [e.component_id for e in cascade.effects]
        total = len(graph.components)
        blast_radius = len(set(affected))

        # Generate title
        title = self._generate_title(scenario.name, cascade)

        # Generate summary
        summary = self._generate_summary(scenario, cascade, total)

        # Generate impact assessment
        impact = self._generate_impact(cascade, total, graph)

        # Generate timeline
        timeline = self._generate_timeline(cascade, graph)

        # Generate root cause
        root_cause = self._generate_root_cause(scenario, cascade)

        # Identify contributing factors
        contributing = self._identify_contributing_factors(cascade, graph)

        # What went well / what didn't
        went_well = self._identify_what_went_well(cascade, graph)
        went_bad = self._identify_what_didnt(cascade, graph)

        # Generate action items
        action_items = self._generate_action_items(cascade, graph, incident_id)

        # Lessons learned
        lessons = self._generate_lessons(cascade, graph)

        # Duration estimate
        duration = self._estimate_duration(cascade)

        pm = PostMortem(
            incident_id=incident_id,
            title=title,
            severity=severity,
            duration_estimate=duration,
            summary=summary,
            impact=impact,
            root_cause=root_cause,
            timeline=timeline,
            contributing_factors=contributing,
            what_went_well=went_well,
            what_didnt=went_bad,
            action_items=action_items,
            lessons_learned=lessons,
            affected_components=list(set(affected)),
            blast_radius=blast_radius,
        )

        # Build sections for markdown export
        pm.sections = self._build_sections(pm)

        return pm

    def to_markdown(self, postmortem: PostMortem) -> str:
        """Convert a post-mortem to markdown format."""
        lines: list[str] = []

        lines.append(f"# Post-Mortem: {postmortem.title}")
        lines.append("")
        lines.append(f"**Incident ID:** {postmortem.incident_id}")
        lines.append(f"**Severity:** {postmortem.severity}")
        lines.append(f"**Date:** {postmortem.date.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**Duration:** {postmortem.duration_estimate}")
        lines.append(f"**Blast Radius:** {postmortem.blast_radius} components affected")
        lines.append("")

        # Summary
        lines.append("## 1. Incident Summary")
        lines.append("")
        lines.append(postmortem.summary)
        lines.append("")

        # Impact
        lines.append("## 2. Impact Assessment")
        lines.append("")
        lines.append(postmortem.impact)
        lines.append("")

        # Timeline
        lines.append("## 3. Timeline of Events")
        lines.append("")
        lines.append("| Time | Event |")
        lines.append("|------|-------|")
        for time_offset, event in postmortem.timeline:
            lines.append(f"| {time_offset} | {event} |")
        lines.append("")

        # Root Cause
        lines.append("## 4. Root Cause Analysis")
        lines.append("")
        lines.append(postmortem.root_cause)
        lines.append("")

        # Contributing Factors
        lines.append("## 5. Contributing Factors")
        lines.append("")
        for factor in postmortem.contributing_factors:
            lines.append(f"- {factor}")
        lines.append("")

        # What Went Well / What Didn't
        lines.append("## 6. What Went Well")
        lines.append("")
        for item in postmortem.what_went_well:
            lines.append(f"- {item}")
        lines.append("")

        lines.append("## 7. What Didn't Go Well")
        lines.append("")
        for item in postmortem.what_didnt:
            lines.append(f"- {item}")
        lines.append("")

        # Action Items
        lines.append("## 8. Action Items")
        lines.append("")
        lines.append("| ID | Description | Owner | Priority | Category | Status |")
        lines.append("|-----|-------------|-------|----------|----------|--------|")
        for ai in postmortem.action_items:
            lines.append(
                f"| {ai.id} | {ai.description} | {ai.owner} | "
                f"{ai.priority} | {ai.category} | {ai.status} |"
            )
        lines.append("")

        # Lessons Learned
        lines.append("## 9. Lessons Learned")
        lines.append("")
        for lesson in postmortem.lessons_learned:
            lines.append(f"- {lesson}")
        lines.append("")

        # Footer
        lines.append("---")
        lines.append(
            "*This post-mortem was auto-generated by FaultRay. "
            "It follows blameless post-mortem principles: focus on systems, not people.*"
        )

        return "\n".join(lines)

    def to_html(self, postmortem: PostMortem) -> str:
        """Convert a post-mortem to HTML format."""
        self.to_markdown(postmortem)

        # Simple markdown-to-HTML conversion
        html_lines: list[str] = []
        html_lines.append("<!DOCTYPE html>")
        html_lines.append("<html><head>")
        html_lines.append(f"<title>Post-Mortem: {postmortem.title}</title>")
        html_lines.append("<style>")
        html_lines.append("body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; ")
        html_lines.append("  max-width: 900px; margin: 40px auto; padding: 0 20px; line-height: 1.6; }")
        html_lines.append("h1 { color: #d32f2f; border-bottom: 2px solid #d32f2f; padding-bottom: 8px; }")
        html_lines.append("h2 { color: #1976d2; margin-top: 32px; }")
        html_lines.append("table { border-collapse: collapse; width: 100%; margin: 16px 0; }")
        html_lines.append("th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }")
        html_lines.append("th { background: #f5f5f5; font-weight: 600; }")
        html_lines.append("tr:nth-child(even) { background: #fafafa; }")
        html_lines.append(".sev1 { color: #d32f2f; font-weight: bold; }")
        html_lines.append(".sev2 { color: #f57c00; font-weight: bold; }")
        html_lines.append(".sev3 { color: #fbc02d; }")
        html_lines.append(".sev4 { color: #388e3c; }")
        html_lines.append(".meta { color: #666; font-size: 0.9em; }")
        html_lines.append("ul { padding-left: 20px; }")
        html_lines.append("li { margin-bottom: 4px; }")
        html_lines.append("hr { border: none; border-top: 1px solid #ddd; margin: 32px 0; }")
        html_lines.append(".footer { color: #999; font-style: italic; font-size: 0.85em; }")
        html_lines.append("</style>")
        html_lines.append("</head><body>")

        # Title
        sev_class = postmortem.severity.lower().replace("sev", "sev")
        html_lines.append(f"<h1>Post-Mortem: {_escape_html(postmortem.title)}</h1>")
        html_lines.append("<div class='meta'>")
        html_lines.append(
            f"<strong>Incident ID:</strong> {postmortem.incident_id} | "
            f"<strong>Severity:</strong> <span class='{sev_class}'>{postmortem.severity}</span> | "
            f"<strong>Date:</strong> {postmortem.date.strftime('%Y-%m-%d %H:%M')} | "
            f"<strong>Duration:</strong> {_escape_html(postmortem.duration_estimate)} | "
            f"<strong>Blast Radius:</strong> {postmortem.blast_radius} components"
        )
        html_lines.append("</div>")

        # Summary
        html_lines.append("<h2>1. Incident Summary</h2>")
        html_lines.append(f"<p>{_escape_html(postmortem.summary)}</p>")

        # Impact
        html_lines.append("<h2>2. Impact Assessment</h2>")
        html_lines.append(f"<p>{_escape_html(postmortem.impact)}</p>")

        # Timeline
        html_lines.append("<h2>3. Timeline of Events</h2>")
        html_lines.append("<table><tr><th>Time</th><th>Event</th></tr>")
        for time_offset, event in postmortem.timeline:
            html_lines.append(
                f"<tr><td>{_escape_html(time_offset)}</td>"
                f"<td>{_escape_html(event)}</td></tr>"
            )
        html_lines.append("</table>")

        # Root Cause
        html_lines.append("<h2>4. Root Cause Analysis</h2>")
        html_lines.append(f"<p>{_escape_html(postmortem.root_cause)}</p>")

        # Contributing Factors
        html_lines.append("<h2>5. Contributing Factors</h2>")
        html_lines.append("<ul>")
        for factor in postmortem.contributing_factors:
            html_lines.append(f"<li>{_escape_html(factor)}</li>")
        html_lines.append("</ul>")

        # What Went Well
        html_lines.append("<h2>6. What Went Well</h2>")
        html_lines.append("<ul>")
        for item in postmortem.what_went_well:
            html_lines.append(f"<li>{_escape_html(item)}</li>")
        html_lines.append("</ul>")

        # What Didn't Go Well
        html_lines.append("<h2>7. What Didn't Go Well</h2>")
        html_lines.append("<ul>")
        for item in postmortem.what_didnt:
            html_lines.append(f"<li>{_escape_html(item)}</li>")
        html_lines.append("</ul>")

        # Action Items
        html_lines.append("<h2>8. Action Items</h2>")
        html_lines.append(
            "<table><tr><th>ID</th><th>Description</th><th>Owner</th>"
            "<th>Priority</th><th>Category</th><th>Status</th></tr>"
        )
        for ai in postmortem.action_items:
            html_lines.append(
                f"<tr><td>{_escape_html(ai.id)}</td>"
                f"<td>{_escape_html(ai.description)}</td>"
                f"<td>{_escape_html(ai.owner)}</td>"
                f"<td>{_escape_html(ai.priority)}</td>"
                f"<td>{_escape_html(ai.category)}</td>"
                f"<td>{_escape_html(ai.status)}</td></tr>"
            )
        html_lines.append("</table>")

        # Lessons Learned
        html_lines.append("<h2>9. Lessons Learned</h2>")
        html_lines.append("<ul>")
        for lesson in postmortem.lessons_learned:
            html_lines.append(f"<li>{_escape_html(lesson)}</li>")
        html_lines.append("</ul>")

        # Footer
        html_lines.append("<hr>")
        html_lines.append(
            "<p class='footer'>This post-mortem was auto-generated by FaultRay. "
            "It follows blameless post-mortem principles: focus on systems, not people.</p>"
        )
        html_lines.append("</body></html>")

        return "\n".join(html_lines)

    def export_library(
        self, library: PostMortemLibrary, output_dir: Path, fmt: str = "md"
    ) -> list[Path]:
        """Export all post-mortems in the library to files.

        Args:
            library: The post-mortem library to export.
            output_dir: Directory to write files to.
            fmt: Output format - "md" or "html".

        Returns:
            List of paths to the generated files.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for pm in library.postmortems:
            safe_title = pm.incident_id.replace("/", "_").replace(" ", "_")
            if fmt == "html":
                filename = f"{safe_title}.html"
                content = self.to_html(pm)
            else:
                filename = f"{safe_title}.md"
                content = self.to_markdown(pm)

            filepath = output_dir / filename
            filepath.write_text(content, encoding="utf-8")
            paths.append(filepath)

        # Write summary file
        summary_path = output_dir / f"_summary.{fmt}"
        summary_content = self._generate_library_summary(library, fmt)
        summary_path.write_text(summary_content, encoding="utf-8")
        paths.append(summary_path)

        return paths

    # -----------------------------------------------------------------------
    # Internal content generation methods
    # -----------------------------------------------------------------------

    @staticmethod
    def _generate_incident_id(scenario_id: str) -> str:
        """Generate a stable incident ID from scenario ID."""
        h = hashlib.md5(scenario_id.encode()).hexdigest()[:8]
        return f"INC-{h.upper()}"

    @staticmethod
    def _classify_severity(risk_score: float) -> str:
        """Classify severity from risk score."""
        if risk_score >= 8.0:
            return "SEV1"
        elif risk_score >= 6.0:
            return "SEV2"
        elif risk_score >= 4.0:
            return "SEV3"
        else:
            return "SEV4"

    def _generate_title(self, scenario_name: str, cascade: CascadeChain) -> str:
        """Generate a descriptive post-mortem title."""
        down_count = sum(1 for e in cascade.effects if e.health == HealthStatus.DOWN)
        degraded_count = sum(
            1 for e in cascade.effects
            if e.health in (HealthStatus.DEGRADED, HealthStatus.OVERLOADED)
        )

        if down_count > 1:
            return f"Cascading Failure: {scenario_name} ({down_count} services DOWN)"
        elif down_count == 1:
            down_comp = next(
                e.component_name for e in cascade.effects if e.health == HealthStatus.DOWN
            )
            return f"Service Outage: {down_comp} ({scenario_name})"
        elif degraded_count > 0:
            return f"Service Degradation: {scenario_name} ({degraded_count} services affected)"
        else:
            return f"Incident: {scenario_name}"

    def _generate_summary(
        self, scenario, cascade: CascadeChain, total_components: int
    ) -> str:
        """Generate the incident summary."""
        affected_count = len(cascade.effects)
        down_count = sum(1 for e in cascade.effects if e.health == HealthStatus.DOWN)
        degraded_count = sum(
            1 for e in cascade.effects if e.health == HealthStatus.DEGRADED
        )

        # Identify the trigger
        trigger = cascade.trigger

        summary_parts = [
            f"A simulated incident was triggered by: {trigger}.",
        ]

        if affected_count > 0:
            summary_parts.append(
                f"The incident affected {affected_count} out of {total_components} "
                f"infrastructure components ({affected_count / total_components * 100:.0f}% "
                f"of the system)."
            )

        if down_count > 0:
            summary_parts.append(f"{down_count} component(s) went completely DOWN.")
        if degraded_count > 0:
            summary_parts.append(f"{degraded_count} component(s) experienced degradation.")

        summary_parts.append(
            f"The overall risk score for this scenario was "
            f"{cascade.severity:.1f}/10."
        )

        return " ".join(summary_parts)

    def _generate_impact(
        self, cascade: CascadeChain, total_components: int, graph: InfraGraph
    ) -> str:
        """Generate the impact assessment."""
        affected_count = len(set(e.component_id for e in cascade.effects))
        down_effects = [e for e in cascade.effects if e.health == HealthStatus.DOWN]
        degraded_effects = [
            e for e in cascade.effects
            if e.health in (HealthStatus.DEGRADED, HealthStatus.OVERLOADED)
        ]

        lines = []
        lines.append(
            f"**Components Affected:** {affected_count} out of {total_components} "
            f"({affected_count / total_components * 100:.0f}% blast radius)"
        )

        if down_effects:
            down_names = ", ".join(sorted(set(e.component_name for e in down_effects)))
            lines.append(f"\n**Services DOWN:** {down_names}")

        if degraded_effects:
            deg_names = ", ".join(sorted(set(e.component_name for e in degraded_effects)))
            lines.append(f"\n**Services Degraded:** {deg_names}")

        # Estimate traffic impact
        traffic_pct = min(100, affected_count / total_components * 100)
        if traffic_pct > 50:
            lines.append(
                f"\n**Estimated Traffic Impact:** ~{traffic_pct:.0f}% of traffic affected. "
                f"Major service disruption expected."
            )
        elif traffic_pct > 20:
            lines.append(
                f"\n**Estimated Traffic Impact:** ~{traffic_pct:.0f}% of traffic affected. "
                f"Partial service disruption."
            )
        else:
            lines.append(
                f"\n**Estimated Traffic Impact:** ~{traffic_pct:.0f}% of traffic affected. "
                f"Limited user impact."
            )

        # Count dependent services
        all_affected_ids = set(e.component_id for e in cascade.effects)
        dependent_count = 0
        for comp_id in all_affected_ids:
            deps = graph.get_dependents(comp_id)
            for dep in deps:
                if dep.id not in all_affected_ids:
                    dependent_count += 1

        if dependent_count > 0:
            lines.append(
                f"\n**Dependent Services:** {dependent_count} additional service(s) "
                f"potentially experiencing degradation due to upstream failures."
            )

        return "\n".join(lines)

    def _generate_timeline(
        self, cascade: CascadeChain, graph: InfraGraph
    ) -> list[tuple[str, str]]:
        """Generate a timeline of events from cascade effects."""
        timeline: list[tuple[str, str]] = []

        # Sort effects by estimated time
        sorted_effects = sorted(cascade.effects, key=lambda e: e.estimated_time_seconds)

        for i, effect in enumerate(sorted_effects):
            t = effect.estimated_time_seconds

            if i == 0:
                # Initial trigger
                timeline.append(
                    ("T+0s", f"{effect.component_name} failure detected: {effect.reason}")
                )
            else:
                time_str = self._format_time_offset(t)
                health_str = effect.health.value.upper()
                timeline.append(
                    (time_str, f"{effect.component_name} status: {health_str} - {effect.reason}")
                )

            # Check for mitigation mechanisms
            comp = graph.get_component(effect.component_id)
            if comp:
                if comp.failover.enabled and effect.health == HealthStatus.DOWN:
                    fo_time = t + int(comp.failover.promotion_time_seconds)
                    timeline.append((
                        self._format_time_offset(fo_time),
                        f"Failover initiated for {effect.component_name} "
                        f"(promotion time: {comp.failover.promotion_time_seconds}s)"
                    ))

                if comp.autoscaling.enabled and effect.health in (
                    HealthStatus.OVERLOADED, HealthStatus.DEGRADED
                ):
                    as_time = t + comp.autoscaling.scale_up_delay_seconds
                    timeline.append((
                        self._format_time_offset(as_time),
                        f"Autoscaling triggered for {effect.component_name} "
                        f"(scaling by {comp.autoscaling.scale_up_step} replicas)"
                    ))

        # Add circuit breaker activations
        for effect in sorted_effects:
            if "circuit breaker" in effect.reason.lower():
                timeline.append((
                    self._format_time_offset(effect.estimated_time_seconds),
                    f"Circuit breaker activated: cascade stopped at {effect.component_name}"
                ))

        # Sort final timeline by time
        timeline.sort(key=lambda x: self._parse_time_offset(x[0]))

        return timeline

    def _generate_root_cause(self, scenario, cascade: CascadeChain) -> str:
        """Generate root cause analysis from scenario and cascade."""
        faults = scenario.faults if hasattr(scenario, 'faults') else []
        parts = []

        for fault in faults:
            fault_type = fault.fault_type
            target = fault.target_component_id

            cause_map = {
                FaultType.COMPONENT_DOWN: (
                    f"Single point of failure in **{target}**. The component went down "
                    f"without adequate redundancy or failover mechanisms in place."
                ),
                FaultType.DISK_FULL: (
                    f"Resource exhaustion (disk full) on **{target}**. "
                    f"Insufficient disk capacity monitoring or alerting led to the disk "
                    f"filling up, causing the component to become unavailable."
                ),
                FaultType.MEMORY_EXHAUSTION: (
                    f"Memory exhaustion on **{target}**. The component ran out of memory, "
                    f"likely due to a memory leak, traffic spike, or insufficient capacity."
                ),
                FaultType.CPU_SATURATION: (
                    f"CPU saturation on **{target}**. The component's CPU was fully "
                    f"utilized, causing request queuing and increased latency."
                ),
                FaultType.CONNECTION_POOL_EXHAUSTION: (
                    f"Connection pool exhaustion on **{target}**. All available connections "
                    f"were consumed, preventing new requests from being processed."
                ),
                FaultType.NETWORK_PARTITION: (
                    f"Network partition affecting **{target}**. The component became "
                    f"unreachable due to a network failure, isolating it from dependent services."
                ),
                FaultType.LATENCY_SPIKE: (
                    f"Latency spike on **{target}**. Response times degraded significantly, "
                    f"causing timeouts in upstream services."
                ),
                FaultType.TRAFFIC_SPIKE: (
                    f"Traffic spike overwhelming **{target}**. The component could not handle "
                    f"the increased request volume."
                ),
            }

            parts.append(cause_map.get(
                fault_type,
                f"Failure of type '{fault_type.value}' on **{target}**."
            ))

        # Add cascade analysis
        down_effects = [e for e in cascade.effects if e.health == HealthStatus.DOWN]
        if len(down_effects) > 1:
            parts.append(
                f"\nThe initial failure cascaded through the dependency graph, "
                f"causing {len(down_effects)} components to go DOWN. "
                f"This indicates insufficient isolation between services."
            )

        if scenario.traffic_multiplier > 1.0:
            parts.append(
                f"\nA {scenario.traffic_multiplier}x traffic spike amplified the impact "
                f"of the underlying failure."
            )

        return "\n\n".join(parts) if parts else "Root cause could not be determined from simulation data."

    def _identify_contributing_factors(
        self, cascade: CascadeChain, graph: InfraGraph
    ) -> list[str]:
        """Identify contributing factors from cascade effects."""
        factors: list[str] = []

        affected_ids = set(e.component_id for e in cascade.effects)

        for comp_id in affected_ids:
            comp = graph.get_component(comp_id)
            if not comp:
                continue

            if comp.replicas <= 1:
                factors.append(
                    f"No redundancy on {comp.name} (single replica)"
                )

            if not comp.failover.enabled:
                factors.append(
                    f"No failover configured for {comp.name}"
                )

            if not comp.autoscaling.enabled:
                factors.append(
                    f"No autoscaling on {comp.name} to absorb load"
                )

        # Check dependency edges for missing circuit breakers
        all_edges = graph.all_dependency_edges()
        for edge in all_edges:
            if edge.source_id in affected_ids or edge.target_id in affected_ids:
                if not edge.circuit_breaker.enabled:
                    source = graph.get_component(edge.source_id)
                    target = graph.get_component(edge.target_id)
                    s_name = source.name if source else edge.source_id
                    t_name = target.name if target else edge.target_id
                    factors.append(
                        f"No circuit breaker on dependency: {s_name} -> {t_name}"
                    )

        # Deduplicate
        return list(dict.fromkeys(factors))[:10]  # Limit to 10 factors

    def _identify_what_went_well(
        self, cascade: CascadeChain, graph: InfraGraph
    ) -> list[str]:
        """Identify what went well (protective mechanisms that helped)."""
        well: list[str] = []

        # Check for circuit breakers that stopped cascade
        for effect in cascade.effects:
            if "circuit breaker" in effect.reason.lower():
                well.append(
                    f"Circuit breaker on {effect.component_name} stopped further cascade propagation"
                )

        # Check for components with failover
        for effect in cascade.effects:
            comp = graph.get_component(effect.component_id)
            if comp and comp.failover.enabled:
                well.append(
                    f"Failover enabled on {comp.name} (promotion time: "
                    f"{comp.failover.promotion_time_seconds}s)"
                )

        # Check for components with autoscaling
        for effect in cascade.effects:
            comp = graph.get_component(effect.component_id)
            if comp and comp.autoscaling.enabled:
                well.append(
                    f"Autoscaling configured on {comp.name} "
                    f"(max {comp.autoscaling.max_replicas} replicas)"
                )

        # Check for components that were NOT affected (isolation worked)
        affected_ids = set(e.component_id for e in cascade.effects)
        unaffected_count = len(graph.components) - len(affected_ids)
        if unaffected_count > 0 and len(affected_ids) > 0:
            well.append(
                f"{unaffected_count} component(s) remained unaffected, "
                f"indicating some degree of fault isolation"
            )

        if not well:
            well.append("Limited protective mechanisms were in place for this scenario")

        return list(dict.fromkeys(well))[:8]

    def _identify_what_didnt(
        self, cascade: CascadeChain, graph: InfraGraph
    ) -> list[str]:
        """Identify what didn't go well."""
        bad: list[str] = []

        affected_ids = set(e.component_id for e in cascade.effects)
        total = len(graph.components)

        # High blast radius
        if len(affected_ids) > total * 0.5:
            bad.append(
                f"Blast radius was too large: {len(affected_ids)}/{total} components affected "
                f"({len(affected_ids) / total * 100:.0f}%)"
            )

        # SPOFs that went down
        for effect in cascade.effects:
            if effect.health == HealthStatus.DOWN:
                comp = graph.get_component(effect.component_id)
                if comp and comp.replicas <= 1 and not comp.failover.enabled:
                    bad.append(
                        f"Single point of failure: {comp.name} went DOWN with no "
                        f"redundancy or failover"
                    )

        # Missing circuit breakers on cascade paths
        cascade_edges = 0
        missing_cb = 0
        for edge in graph.all_dependency_edges():
            if edge.source_id in affected_ids and edge.target_id in affected_ids:
                cascade_edges += 1
                if not edge.circuit_breaker.enabled:
                    missing_cb += 1

        if missing_cb > 0:
            bad.append(
                f"{missing_cb} dependency edge(s) in the cascade path lacked circuit breakers"
            )

        # No autoscaling on overloaded components
        for effect in cascade.effects:
            if effect.health == HealthStatus.OVERLOADED:
                comp = graph.get_component(effect.component_id)
                if comp and not comp.autoscaling.enabled:
                    bad.append(
                        f"{comp.name} became overloaded with no autoscaling to absorb load"
                    )

        if not bad:
            bad.append("The scenario exposed areas for improvement in system resilience")

        return list(dict.fromkeys(bad))[:8]

    def _generate_action_items(
        self, cascade: CascadeChain, graph: InfraGraph, incident_id: str
    ) -> list[ActionItem]:
        """Generate action items from cascade analysis."""
        items: list[ActionItem] = []
        counter = 1

        affected_ids = set(e.component_id for e in cascade.effects)

        for effect in cascade.effects:
            comp = graph.get_component(effect.component_id)
            if not comp:
                continue

            # P0: No replicas on a DOWN component
            if effect.health == HealthStatus.DOWN and comp.replicas <= 1:
                items.append(ActionItem(
                    id=f"{incident_id}-{counter:03d}",
                    description=f"Add redundancy to {comp.name} (currently {comp.replicas} replica)",
                    owner="Platform Team",
                    priority="P0",
                    status="open",
                    due_date="1 week",
                    category="prevention",
                ))
                counter += 1

            # P1: No circuit breaker on affected edges
            for edge in graph.all_dependency_edges():
                if edge.target_id == comp.id and edge.source_id in affected_ids:
                    if not edge.circuit_breaker.enabled:
                        source = graph.get_component(edge.source_id)
                        s_name = source.name if source else edge.source_id
                        items.append(ActionItem(
                            id=f"{incident_id}-{counter:03d}",
                            description=(
                                f"Implement circuit breaker pattern on "
                                f"{s_name} -> {comp.name} dependency"
                            ),
                            owner="SRE Team",
                            priority="P1",
                            status="open",
                            due_date="2 weeks",
                            category="mitigation",
                        ))
                        counter += 1

            # P1: No autoscaling on overloaded component
            if effect.health in (HealthStatus.OVERLOADED, HealthStatus.DEGRADED):
                if not comp.autoscaling.enabled:
                    items.append(ActionItem(
                        id=f"{incident_id}-{counter:03d}",
                        description=f"Enable autoscaling for {comp.name}",
                        owner="Platform Team",
                        priority="P1",
                        status="open",
                        due_date="2 weeks",
                        category="prevention",
                    ))
                    counter += 1

            # P1: No failover on DOWN component
            if effect.health == HealthStatus.DOWN and not comp.failover.enabled:
                items.append(ActionItem(
                    id=f"{incident_id}-{counter:03d}",
                    description=f"Enable failover configuration for {comp.name}",
                    owner="SRE Team",
                    priority="P1",
                    status="open",
                    due_date="2 weeks",
                    category="mitigation",
                ))
                counter += 1

            # P2: No health check monitoring
            if not comp.failover.enabled or comp.failover.health_check_interval_seconds <= 0:
                items.append(ActionItem(
                    id=f"{incident_id}-{counter:03d}",
                    description=f"Add health check monitoring for {comp.name}",
                    owner="SRE Team",
                    priority="P2",
                    status="open",
                    due_date="1 month",
                    category="detection",
                ))
                counter += 1

        # Deduplicate by description
        seen_descs: set[str] = set()
        unique_items: list[ActionItem] = []
        for item in items:
            if item.description not in seen_descs:
                seen_descs.add(item.description)
                unique_items.append(item)

        # Sort by priority
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        unique_items.sort(key=lambda x: priority_order.get(x.priority, 99))

        return unique_items[:20]  # Limit to 20 action items

    def _generate_lessons(
        self, cascade: CascadeChain, graph: InfraGraph
    ) -> list[str]:
        """Generate lessons learned from the incident."""
        lessons: list[str] = []

        affected_count = len(set(e.component_id for e in cascade.effects))
        total = len(graph.components)
        down_count = sum(1 for e in cascade.effects if e.health == HealthStatus.DOWN)

        if affected_count > total * 0.5:
            lessons.append(
                "High blast radius indicates insufficient fault isolation. "
                "Consider implementing bulkhead patterns and circuit breakers "
                "to contain failures."
            )

        if down_count > 0:
            # Check for SPOFs
            spofs = [
                e for e in cascade.effects
                if e.health == HealthStatus.DOWN
                and graph.get_component(e.component_id)
                and graph.get_component(e.component_id).replicas <= 1  # type: ignore
            ]
            if spofs:
                lessons.append(
                    "Single points of failure (SPOFs) were the primary cause of downtime. "
                    "Every critical service should have at least 2 replicas with failover."
                )

        # Circuit breaker lessons
        has_cb = any("circuit breaker" in e.reason.lower() for e in cascade.effects)
        if has_cb:
            lessons.append(
                "Circuit breakers effectively limited cascade propagation in some paths. "
                "Expand circuit breaker coverage to all critical dependency edges."
            )
        else:
            all_edges = graph.all_dependency_edges()
            if all_edges and not any(e.circuit_breaker.enabled for e in all_edges):
                lessons.append(
                    "No circuit breakers were in place to stop cascade propagation. "
                    "Implementing the circuit breaker pattern is a high-priority improvement."
                )

        # Autoscaling lessons
        overloaded = [
            e for e in cascade.effects if e.health == HealthStatus.OVERLOADED
        ]
        if overloaded:
            lessons.append(
                "Components became overloaded without autoscaling to absorb the spike. "
                "Autoscaling should be enabled for all components that handle user traffic."
            )

        if not lessons:
            lessons.append(
                "This simulation highlights the importance of regular chaos testing "
                "to proactively identify and address reliability weaknesses."
            )

        return lessons

    def _estimate_duration(self, cascade: CascadeChain) -> str:
        """Estimate incident duration from cascade effects."""
        max_time = max(
            (e.estimated_time_seconds for e in cascade.effects),
            default=0,
        )

        # Add estimated recovery time (assume MTTR of 30 minutes)
        total_seconds = max_time + 1800  # 30 min recovery

        if total_seconds < 300:
            return "< 5 minutes"
        elif total_seconds < 3600:
            return f"~{total_seconds // 60} minutes"
        else:
            hours = total_seconds / 3600
            return f"~{hours:.1f} hours"

    def _build_sections(self, pm: PostMortem) -> list[PostMortemSection]:
        """Build structured sections for the post-mortem."""
        return [
            PostMortemSection(title="Incident Summary", content=pm.summary),
            PostMortemSection(title="Impact Assessment", content=pm.impact),
            PostMortemSection(
                title="Timeline",
                content="\n".join(f"- **{t}**: {e}" for t, e in pm.timeline),
            ),
            PostMortemSection(title="Root Cause Analysis", content=pm.root_cause),
            PostMortemSection(
                title="Contributing Factors",
                content="\n".join(f"- {f}" for f in pm.contributing_factors),
            ),
            PostMortemSection(
                title="What Went Well",
                content="\n".join(f"- {w}" for w in pm.what_went_well),
            ),
            PostMortemSection(
                title="What Didn't Go Well",
                content="\n".join(f"- {w}" for w in pm.what_didnt),
            ),
            PostMortemSection(
                title="Lessons Learned",
                content="\n".join(f"- {lesson}" for lesson in pm.lessons_learned),
            ),
        ]

    def _identify_common_themes(
        self, postmortems: list[PostMortem], graph: InfraGraph
    ) -> list[str]:
        """Identify common themes across all post-mortems."""
        themes: list[str] = []

        if not postmortems:
            return themes

        # Count SPOF mentions
        spof_count = sum(
            1 for pm in postmortems
            for f in pm.contributing_factors
            if "single" in f.lower() or "no redundancy" in f.lower()
        )
        if spof_count > 0:
            themes.append(
                f"Single Points of Failure: Found in {spof_count} contributing factor(s) "
                f"across post-mortems"
            )

        # Count missing circuit breakers
        cb_count = sum(
            1 for pm in postmortems
            for f in pm.contributing_factors
            if "circuit breaker" in f.lower()
        )
        if cb_count > 0:
            themes.append(
                f"Missing Circuit Breakers: Identified in {cb_count} contributing factor(s)"
            )

        # Count missing autoscaling
        as_count = sum(
            1 for pm in postmortems
            for f in pm.contributing_factors
            if "autoscaling" in f.lower()
        )
        if as_count > 0:
            themes.append(
                f"Insufficient Autoscaling: Mentioned in {as_count} contributing factor(s)"
            )

        # Count missing failover
        fo_count = sum(
            1 for pm in postmortems
            for f in pm.contributing_factors
            if "failover" in f.lower()
        )
        if fo_count > 0:
            themes.append(
                f"Missing Failover: Identified in {fo_count} contributing factor(s)"
            )

        # High severity count
        sev12 = sum(
            1 for pm in postmortems if pm.severity in ("SEV1", "SEV2")
        )
        if sev12 > 0:
            themes.append(
                f"Critical Severity: {sev12} post-mortem(s) rated SEV1/SEV2"
            )

        return themes

    def _generate_library_summary(
        self, library: PostMortemLibrary, fmt: str
    ) -> str:
        """Generate a summary document for the post-mortem library."""
        if fmt == "html":
            return self._library_summary_html(library)
        return self._library_summary_md(library)

    def _library_summary_md(self, library: PostMortemLibrary) -> str:
        """Generate markdown summary of the library."""
        lines: list[str] = []
        lines.append("# Post-Mortem Library Summary")
        lines.append("")
        lines.append(f"**Total Post-Mortems:** {len(library.postmortems)}")
        lines.append(f"**Critical (SEV1/SEV2):** {library.critical_postmortems}")
        lines.append(f"**Total Action Items:** {library.total_action_items}")
        lines.append("")

        if library.common_themes:
            lines.append("## Common Themes")
            lines.append("")
            for theme in library.common_themes:
                lines.append(f"- {theme}")
            lines.append("")

        lines.append("## Post-Mortem Index")
        lines.append("")
        lines.append("| Incident ID | Title | Severity | Blast Radius | Action Items |")
        lines.append("|-------------|-------|----------|--------------|--------------|")
        for pm in library.postmortems:
            lines.append(
                f"| {pm.incident_id} | {pm.title} | {pm.severity} | "
                f"{pm.blast_radius} | {len(pm.action_items)} |"
            )
        lines.append("")

        # Action items summary by priority
        all_items = [ai for pm in library.postmortems for ai in pm.action_items]
        if all_items:
            lines.append("## Action Items by Priority")
            lines.append("")
            for priority in ("P0", "P1", "P2", "P3"):
                p_items = [ai for ai in all_items if ai.priority == priority]
                if p_items:
                    lines.append(f"### {priority} ({len(p_items)} items)")
                    lines.append("")
                    for ai in p_items:
                        lines.append(f"- [{ai.id}] {ai.description} (Owner: {ai.owner})")
                    lines.append("")

        lines.append("---")
        lines.append("*Generated by FaultRay*")

        return "\n".join(lines)

    def _library_summary_html(self, library: PostMortemLibrary) -> str:
        """Generate HTML summary of the library."""
        # Reuse markdown and wrap in basic HTML
        md_content = self._library_summary_md(library)
        return (
            "<!DOCTYPE html><html><head>"
            "<title>Post-Mortem Library Summary</title>"
            "<style>body { font-family: sans-serif; max-width: 900px; margin: 40px auto; }"
            "table { border-collapse: collapse; width: 100%; }"
            "th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }"
            "th { background: #f5f5f5; }</style>"
            "</head><body>"
            f"<pre>{_escape_html(md_content)}</pre>"
            "</body></html>"
        )

    @staticmethod
    def _format_time_offset(seconds: int) -> str:
        """Format seconds into a human-readable time offset."""
        if seconds < 60:
            return f"T+{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            if secs > 0:
                return f"T+{minutes}m{secs}s"
            return f"T+{minutes}m"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if minutes > 0:
                return f"T+{hours}h{minutes}m"
            return f"T+{hours}h"

    @staticmethod
    def _parse_time_offset(offset: str) -> int:
        """Parse a time offset string back to seconds for sorting."""
        if not offset.startswith("T+"):
            return 0
        rest = offset[2:]
        total = 0
        # Parse hours
        if "h" in rest:
            h_part, rest = rest.split("h", 1)
            total += int(h_part) * 3600
        # Parse minutes
        if "m" in rest:
            m_part, rest = rest.split("m", 1)
            if m_part:
                total += int(m_part) * 60
        # Parse seconds
        if "s" in rest:
            s_part = rest.replace("s", "")
            if s_part:
                total += int(s_part)
        return total


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
