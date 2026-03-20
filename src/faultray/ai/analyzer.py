# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""AI-enhanced analysis layer for FaultRay simulation results.

Provides intelligent prioritization, natural language summaries,
and remediation recommendations based on simulation results.

Works in two modes:
1. Built-in rules engine (no API key needed) -- always available
2. LLM-enhanced (optional, requires FAULTRAY_AI_API_KEY) -- future
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationReport


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AIRecommendation:
    """A single actionable recommendation from AI analysis."""

    component_id: str
    category: str  # "spof", "capacity", "cascade", "config", "cost"
    severity: str  # "critical", "high", "medium", "low"
    title: str
    description: str
    remediation: str
    estimated_impact: str  # e.g., "4.2 -> 5.1 nines"
    effort: str  # "low", "medium", "high"


@dataclass
class AIAnalysisReport:
    """Complete AI analysis report."""

    summary: str  # Natural language summary
    top_risks: list[str]  # Top 3-5 risks in plain language
    recommendations: list[AIRecommendation]
    availability_assessment: str  # Current tier assessment
    upgrade_path: str  # What to do to reach next tier
    estimated_current_nines: float
    theoretical_max_nines: float


# ---------------------------------------------------------------------------
# LLM provider interface (for future integration)
# ---------------------------------------------------------------------------

class LLMProvider(Protocol):
    """Interface for pluggable LLM providers (future use)."""

    def generate_summary(self, context: dict) -> str:
        """Generate a natural language summary from analysis context."""
        ...

    def generate_recommendations(self, context: dict) -> list[dict]:
        """Generate enhanced recommendations from analysis context."""
        ...


# ---------------------------------------------------------------------------
# Rule-based analyzer
# ---------------------------------------------------------------------------

def _score_to_nines(resilience_score: float) -> float:
    """Map a resilience score (0-100) to estimated availability nines."""
    if resilience_score >= 95:
        return 4.5
    elif resilience_score >= 90:
        return 4.0
    elif resilience_score >= 80:
        return 3.5
    elif resilience_score >= 70:
        return 3.0
    elif resilience_score >= 60:
        return 2.5
    elif resilience_score >= 50:
        return 2.0
    elif resilience_score >= 30:
        return 1.5
    else:
        return 1.0


def _nines_tier_label(nines: float) -> str:
    """Human-readable tier label for a given nines value."""
    if nines >= 4.5:
        return "Excellent (4.5+ nines -- ~2.6 min downtime/month)"
    elif nines >= 4.0:
        return "High (4+ nines -- ~4.3 min downtime/month)"
    elif nines >= 3.5:
        return "Good (3.5 nines -- ~13 min downtime/month)"
    elif nines >= 3.0:
        return "Standard (3 nines -- ~43 min downtime/month)"
    elif nines >= 2.5:
        return "Basic (2.5 nines -- ~2.2 hr downtime/month)"
    elif nines >= 2.0:
        return "Low (2 nines -- ~7.3 hr downtime/month)"
    else:
        return "Poor (<2 nines -- significant downtime expected)"


class FaultRayAnalyzer:
    """Rule-based intelligent analyzer for simulation results.

    Provides SPOF detection, cascade analysis, capacity assessment,
    and natural-language recommendations without requiring an external
    LLM API key.  Drop in an ``LLMProvider`` via ``set_llm_provider()``
    to upgrade summaries with LLM-generated text.
    """

    def __init__(self) -> None:
        self._llm_provider: LLMProvider | None = None

    def set_llm_provider(self, provider: LLMProvider) -> None:
        """Plug in an LLM provider for enhanced analysis (future)."""
        self._llm_provider = provider

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def analyze(
        self,
        graph: InfraGraph,
        simulation_report: SimulationReport,
        ops_report: object | None = None,
    ) -> AIAnalysisReport:
        """Analyze simulation results and generate recommendations.

        Args:
            graph: The infrastructure graph.
            simulation_report: Result from ``SimulationEngine.run_all_defaults()``.
            ops_report: Optional result from ``OpsSimulationEngine`` (unused for now).

        Returns:
            A complete ``AIAnalysisReport`` with recommendations.
        """
        recommendations: list[AIRecommendation] = []

        # 1. SPOF detection
        recommendations.extend(self._detect_spofs(graph))

        # 2. Cascade amplifier detection
        recommendations.extend(
            self._detect_cascade_amplifiers(graph, simulation_report)
        )

        # 3. Capacity bottleneck detection
        recommendations.extend(self._detect_capacity_bottlenecks(graph))

        # 4. Missing protections (circuit breakers / retry strategies)
        recommendations.extend(self._detect_missing_protections(graph))

        # 5. Availability assessment
        resilience_score = simulation_report.resilience_score
        current_nines = _score_to_nines(resilience_score)
        theoretical_max = self._estimate_theoretical_max(graph, recommendations)

        availability_assessment = (
            f"Current tier: {_nines_tier_label(current_nines)} "
            f"(resilience score {resilience_score:.0f}/100)"
        )

        # 6. Upgrade path
        upgrade_path = self._generate_upgrade_path(
            current_nines, theoretical_max, recommendations
        )

        # 7. Top risks
        top_risks = self._generate_top_risks(recommendations, simulation_report)

        # 8. Natural language summary
        summary = self._generate_summary(
            graph, simulation_report, recommendations,
            current_nines, theoretical_max,
        )

        # Sort recommendations: critical > high > medium > low
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        recommendations.sort(key=lambda r: severity_order.get(r.severity, 99))

        return AIAnalysisReport(
            summary=summary,
            top_risks=top_risks,
            recommendations=recommendations,
            availability_assessment=availability_assessment,
            upgrade_path=upgrade_path,
            estimated_current_nines=current_nines,
            theoretical_max_nines=theoretical_max,
        )

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------

    def _detect_spofs(self, graph: InfraGraph) -> list[AIRecommendation]:
        """Find components with replicas=1 that have 'requires' dependents."""
        recs: list[AIRecommendation] = []

        for comp in graph.components.values():
            if comp.replicas > 1:
                continue
            if comp.failover.enabled:
                continue

            dependents = graph.get_dependents(comp.id)
            requires_dependents = []
            for dep_comp in dependents:
                edge = graph.get_dependency_edge(dep_comp.id, comp.id)
                if edge and edge.dependency_type == "requires":
                    requires_dependents.append(dep_comp)

            if not requires_dependents:
                continue

            # Calculate cascade scope
            all_affected = graph.get_all_affected(comp.id)
            total = len(graph.components)
            pct_affected = (len(all_affected) / total * 100) if total > 0 else 0

            severity = "critical" if pct_affected > 30 else "high"
            dep_names = ", ".join(d.name for d in requires_dependents[:3])

            # Estimate nines improvement from adding a replica
            current_nines = _score_to_nines(graph.resilience_score())
            # Adding a replica typically improves score by 5-15 points
            estimated_improvement = min(0.5, pct_affected / 100 * 1.5)
            improved_nines = current_nines + estimated_improvement

            recs.append(AIRecommendation(
                component_id=comp.id,
                category="spof",
                severity=severity,
                title=f"Single point of failure: {comp.name}",
                description=(
                    f"{comp.name} ({comp.type.value}) has only 1 replica but "
                    f"{len(requires_dependents)} component(s) require it "
                    f"({dep_names}). If it fails, {pct_affected:.0f}% of the "
                    f"system ({len(all_affected)} components) will be affected."
                ),
                remediation=(
                    f"Add at least 1 replica to {comp.name}. "
                    f"For databases, configure primary-standby with automatic "
                    f"failover. For stateless services, add replicas behind "
                    f"a load balancer."
                ),
                estimated_impact=f"{current_nines:.1f} -> {improved_nines:.1f} nines",
                effort="medium" if comp.type == ComponentType.DATABASE else "low",
            ))

        return recs

    def _detect_cascade_amplifiers(
        self,
        graph: InfraGraph,
        simulation_report: SimulationReport,
    ) -> list[AIRecommendation]:
        """Find scenarios where >30% of components are affected (cascade amplifiers)."""
        recs: list[AIRecommendation] = []
        total = len(graph.components)
        if total == 0:
            return recs

        seen_triggers: set[str] = set()

        for result in simulation_report.results:
            cascade = result.cascade
            if not cascade.effects:
                continue

            affected_count = len(cascade.effects)
            pct_affected = affected_count / total * 100

            if pct_affected < 30:
                continue

            # Identify the root cause component (first effect in chain)
            root_id = cascade.effects[0].component_id
            if root_id in seen_triggers:
                continue
            seen_triggers.add(root_id)

            root_comp = graph.get_component(root_id)
            root_name = root_comp.name if root_comp else root_id

            down_count = sum(
                1 for e in cascade.effects if e.health == HealthStatus.DOWN
            )
            severity = "critical" if pct_affected > 50 else "high"

            recs.append(AIRecommendation(
                component_id=root_id,
                category="cascade",
                severity=severity,
                title=f"Cascade amplifier: {root_name}",
                description=(
                    f"Failure of {root_name} cascades to {affected_count} "
                    f"components ({pct_affected:.0f}% of the system). "
                    f"{down_count} component(s) go fully DOWN."
                ),
                remediation=(
                    f"Add circuit breakers on dependencies to {root_name}. "
                    f"Implement bulkheads to isolate failure domains. "
                    f"Consider async communication patterns where possible."
                ),
                estimated_impact=(
                    f"Reduces blast radius from {pct_affected:.0f}% to "
                    f"<{max(10, pct_affected // 3):.0f}% of system"
                ),
                effort="medium",
            ))

        return recs

    def _detect_capacity_bottlenecks(
        self,
        graph: InfraGraph,
    ) -> list[AIRecommendation]:
        """Find components with CPU/memory/disk utilization >70%."""
        recs: list[AIRecommendation] = []

        for comp in graph.components.values():
            bottleneck_reasons: list[str] = []

            if comp.metrics.cpu_percent > 70:
                bottleneck_reasons.append(
                    f"CPU at {comp.metrics.cpu_percent:.0f}%"
                )
            if comp.metrics.memory_percent > 70:
                bottleneck_reasons.append(
                    f"Memory at {comp.metrics.memory_percent:.0f}%"
                )
            if comp.metrics.disk_percent > 70:
                bottleneck_reasons.append(
                    f"Disk at {comp.metrics.disk_percent:.0f}%"
                )

            # Connection pool utilization
            if comp.capacity.connection_pool_size > 0:
                pool_util = (
                    comp.metrics.network_connections
                    / comp.capacity.connection_pool_size * 100
                )
                if pool_util > 70:
                    bottleneck_reasons.append(
                        f"Connection pool at {pool_util:.0f}% "
                        f"({comp.metrics.network_connections}/"
                        f"{comp.capacity.connection_pool_size})"
                    )

            if not bottleneck_reasons:
                continue

            max_util = max(
                comp.metrics.cpu_percent,
                comp.metrics.memory_percent,
                comp.metrics.disk_percent,
            )
            severity = "high" if max_util > 85 else "medium"

            recs.append(AIRecommendation(
                component_id=comp.id,
                category="capacity",
                severity=severity,
                title=f"Capacity bottleneck: {comp.name}",
                description=(
                    f"{comp.name} is running hot: "
                    + "; ".join(bottleneck_reasons)
                    + ". Under traffic spikes, this component will saturate first."
                ),
                remediation=(
                    f"Scale {comp.name} by adding replicas or upgrading "
                    f"instance size. "
                    + (
                        "Enable autoscaling to handle traffic spikes automatically. "
                        if not comp.autoscaling.enabled
                        else ""
                    )
                    + (
                        "Current disk usage is high -- consider log rotation "
                        "or data archival."
                        if comp.metrics.disk_percent > 70
                        else ""
                    )
                ),
                estimated_impact="Prevents saturation-induced outages",
                effort="low" if comp.autoscaling.enabled else "medium",
            ))

        return recs

    def _detect_missing_protections(
        self,
        graph: InfraGraph,
    ) -> list[AIRecommendation]:
        """Check if critical dependency edges lack circuit breakers or retry strategies."""
        recs: list[AIRecommendation] = []
        seen_edges: set[tuple[str, str]] = set()

        for edge in graph.all_dependency_edges():
            if edge.dependency_type != "requires":
                continue

            edge_key = (edge.source_id, edge.target_id)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            missing: list[str] = []
            if not edge.circuit_breaker.enabled:
                missing.append("circuit breaker")
            if not edge.retry_strategy.enabled:
                missing.append("retry strategy")

            if not missing:
                continue

            source = graph.get_component(edge.source_id)
            target = graph.get_component(edge.target_id)
            source_name = source.name if source else edge.source_id
            target_name = target.name if target else edge.target_id

            recs.append(AIRecommendation(
                component_id=edge.source_id,
                category="config",
                severity="medium",
                title=(
                    f"Missing {' and '.join(missing)}: "
                    f"{source_name} -> {target_name}"
                ),
                description=(
                    f"The critical dependency from {source_name} to "
                    f"{target_name} lacks {' and '.join(missing)}. "
                    f"Without these, failures in {target_name} will "
                    f"propagate uncontrolled to {source_name}."
                ),
                remediation=(
                    f"Enable {' and '.join(missing)} on the "
                    f"{source_name} -> {target_name} dependency edge. "
                    + (
                        "Circuit breakers prevent cascade by fast-failing "
                        "when the downstream is unhealthy. "
                        if "circuit breaker" in missing
                        else ""
                    )
                    + (
                        "Retry with exponential backoff and jitter prevents "
                        "thundering herd on transient failures."
                        if "retry strategy" in missing
                        else ""
                    )
                ),
                estimated_impact="Prevents uncontrolled cascade propagation",
                effort="low",
            ))

        return recs

    # ------------------------------------------------------------------
    # Assessment helpers
    # ------------------------------------------------------------------

    def _estimate_theoretical_max(
        self,
        graph: InfraGraph,
        recommendations: list[AIRecommendation],
    ) -> float:
        """Estimate the best achievable nines if all recommendations are applied."""
        current = _score_to_nines(graph.resilience_score())

        # Each recommendation category adds estimated improvement
        spof_count = sum(1 for r in recommendations if r.category == "spof")
        cascade_count = sum(1 for r in recommendations if r.category == "cascade")
        config_count = sum(1 for r in recommendations if r.category == "config")
        capacity_count = sum(1 for r in recommendations if r.category == "capacity")

        improvement = 0.0
        improvement += min(1.5, spof_count * 0.4)  # SPOFs have biggest impact
        improvement += min(0.8, cascade_count * 0.3)
        improvement += min(0.5, config_count * 0.15)
        improvement += min(0.3, capacity_count * 0.1)

        return min(5.0, current + improvement)

    def _generate_upgrade_path(
        self,
        current_nines: float,
        theoretical_max: float,
        recommendations: list[AIRecommendation],
    ) -> str:
        """Generate a specific upgrade path to reach the next nines tier."""
        # Determine next tier target
        tiers = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
        next_tier = None
        for t in tiers:
            if t > current_nines:
                next_tier = t
                break
        if next_tier is None:
            return (
                "Your infrastructure is already at the highest practical "
                "availability tier. Focus on maintaining current reliability "
                "and reducing operational toil."
            )

        if theoretical_max < next_tier:
            return (
                f"Next tier is {next_tier:.1f} nines "
                f"({_nines_tier_label(next_tier)}). "
                f"With all recommended changes, you can reach "
                f"~{theoretical_max:.1f} nines. Additional architectural "
                f"changes (multi-region, active-active) may be needed for "
                f"{next_tier:.1f} nines."
            )

        # Build upgrade steps from recommendations, prioritizing by category
        steps: list[str] = []
        critical_recs = [r for r in recommendations if r.severity == "critical"]
        high_recs = [r for r in recommendations if r.severity == "high"]

        for rec in critical_recs[:3]:
            steps.append(f"[Critical] {rec.title}: {rec.remediation.split('.')[0]}")
        for rec in high_recs[:2]:
            steps.append(f"[High] {rec.title}: {rec.remediation.split('.')[0]}")

        steps_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))
        return (
            f"To reach {next_tier:.1f} nines "
            f"({_nines_tier_label(next_tier)}):\n{steps_text}"
        )

    def _generate_top_risks(
        self,
        recommendations: list[AIRecommendation],
        simulation_report: SimulationReport,
    ) -> list[str]:
        """Generate top 3-5 risks in plain language."""
        risks: list[str] = []

        # Add critical recommendation risks
        for rec in recommendations:
            if rec.severity == "critical":
                risks.append(rec.description.split(".")[0] + ".")

        # Add high-severity risks if we need more
        if len(risks) < 3:
            for rec in recommendations:
                if rec.severity == "high" and len(risks) < 5:
                    risks.append(rec.description.split(".")[0] + ".")

        # Add simulation-derived risks
        for result in simulation_report.critical_findings[:2]:
            risk_text = (
                f"Scenario '{result.scenario.name}' has risk score "
                f"{result.risk_score:.1f}/10 with "
                f"{len(result.cascade.effects)} affected components."
            )
            if risk_text not in risks and len(risks) < 5:
                risks.append(risk_text)

        return risks[:5] if risks else ["No critical risks detected."]

    def _generate_summary(
        self,
        graph: InfraGraph,
        simulation_report: SimulationReport,
        recommendations: list[AIRecommendation],
        current_nines: float,
        theoretical_max: float,
    ) -> str:
        """Generate a 3-5 sentence natural language summary."""
        total_components = len(graph.components)
        len(simulation_report.critical_findings)
        warning_count = len(simulation_report.warnings)
        spof_count = sum(1 for r in recommendations if r.category == "spof")
        sum(1 for r in recommendations if r.category == "cascade")
        critical_recs = sum(1 for r in recommendations if r.severity == "critical")

        # Opening sentence
        if critical_recs == 0:
            opening = (
                f"Your infrastructure ({total_components} components) is in "
                f"good shape with no critical risks detected."
            )
        else:
            opening = (
                f"Your infrastructure ({total_components} components) has "
                f"{critical_recs} critical risk(s) that need immediate attention."
            )

        # SPOF detail
        spof_detail = ""
        if spof_count > 0:
            # Find the worst SPOF
            spof_recs = [r for r in recommendations if r.category == "spof"]
            if spof_recs:
                worst = spof_recs[0]
                spof_detail = (
                    f" The biggest risk is a single-point-of-failure in "
                    f"{worst.component_id} -- {worst.description.split('. If')[0].split(' has ')[1]}."
                )

        # Availability sentence
        avail_detail = (
            f" Current estimated availability is ~{current_nines:.1f} nines "
            f"({_nines_tier_label(current_nines).split('(')[0].strip()})."
        )

        # Improvement sentence
        if theoretical_max > current_nines:
            improvement = (
                f" Applying the top recommendations could improve availability "
                f"from ~{current_nines:.1f} to ~{theoretical_max:.1f} nines."
            )
        else:
            improvement = ""

        # Warning count
        if warning_count > 0:
            warnings_text = (
                f" Additionally, {warning_count} warning-level scenarios "
                f"were detected during simulation."
            )
        else:
            warnings_text = ""

        return opening + spof_detail + avail_detail + improvement + warnings_text


# Backward-compatible alias
FaultRayAnalyzer = FaultRayAnalyzer
