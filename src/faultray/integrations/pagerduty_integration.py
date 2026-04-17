# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""PagerDuty Integration -- incident-triggered cascade analysis.

Receive PagerDuty incident -> auto-analyze blast radius -> enrich with cost impact.

This integration bridges PagerDuty's incident management with FaultRay's
predictive simulation.  When an incident fires, FaultRay instantly calculates:
- Full blast radius (cascade analysis)
- Estimated financial impact (revenue loss + SLA credits)
- Auto-generated runbook steps
- Resolution recommendations ranked by effectiveness

Environment variables:
    PAGERDUTY_API_KEY  -- PagerDuty REST API v2 token (required for live mode)

When the API key is not set, all API calls are mocked so the integration
can be tested without a PagerDuty account.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEngine
from faultray.simulator.financial_risk import FinancialRiskEngine, FinancialRiskReport
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.scenarios import Fault, FaultType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class IncidentAnalysis:
    """Result of analyzing a PagerDuty incident against the infrastructure graph."""

    incident_id: str
    incident_title: str
    affected_components: list[str]
    blast_radius: int
    estimated_downtime_minutes: float
    cost_impact_usd: float
    cascade_chain: CascadeChain | None = None
    severity: str = "unknown"
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ImpactReport:
    """Combined cascade + financial impact report for an incident."""

    incident_id: str
    cascade: CascadeChain
    financial: FinancialRiskReport | None = None
    affected_services: list[str] = field(default_factory=list)
    estimated_recovery_hours: float = 0.0
    total_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class PagerDutyIntegration:
    """Incident-triggered cascade analysis with PagerDuty.

    When a PagerDuty incident webhook arrives, this integration:

    1. Parses the incident to identify the affected component
    2. Runs CascadeEngine to compute the full blast radius
    3. Runs FinancialRiskEngine for cost impact estimation
    4. Generates runbook and resolution recommendations
    5. Optionally posts enrichment notes back to PagerDuty

    Example::

        graph = InfraGraph.load(Path("infra.json"))
        pd = PagerDutyIntegration(
            api_key=os.environ.get("PAGERDUTY_API_KEY"),
            graph=graph,
        )
        analysis = pd.receive_incident(webhook_payload)
        impact = pd.analyze_impact(analysis)
        pd.add_note(analysis.incident_id,
                     f"Blast radius: {impact.cascade.severity}/10")
    """

    def __init__(
        self,
        api_key: str | None = None,
        graph: InfraGraph | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("PAGERDUTY_API_KEY", "")
        self._graph = graph or InfraGraph()
        self._mock = not self._api_key
        if self._mock:
            logger.info("PagerDutyIntegration running in mock mode (no API key).")

    # ------------------------------------------------------------------
    # Receive incident
    # ------------------------------------------------------------------

    def receive_incident(self, webhook_payload: dict) -> IncidentAnalysis:
        """Parse a PagerDuty webhook payload and run initial cascade analysis.

        Supports both V2 webhook (``event.data``) and V3 generic webhook formats.

        Args:
            webhook_payload: Raw PagerDuty webhook JSON payload.

        Returns:
            :class:`IncidentAnalysis` with blast radius and initial findings.
        """
        # Extract incident data -- handle both V2 and V3 formats
        incident = (
            webhook_payload.get("event", {}).get("data", {})
            or webhook_payload.get("incident", {})
            or webhook_payload
        )

        incident_id = incident.get("id", "unknown")
        title = incident.get("title", incident.get("summary", "Unknown incident"))
        severity = incident.get("urgency", incident.get("severity", "high"))

        # Identify affected component from the incident
        component_id = self._extract_component_id(incident)

        # Run cascade analysis
        cascade_engine = CascadeEngine(self._graph)
        affected: list[str] = []
        chain: CascadeChain | None = None

        if component_id:
            fault = Fault(
                target_component_id=component_id,
                fault_type=FaultType.COMPONENT_DOWN,
            )
            chain = cascade_engine.simulate_fault(fault)
            affected = [e.component_id for e in chain.effects]

        # Estimate downtime from cascade effects
        estimated_downtime = 0.0
        if chain:
            for effect in chain.effects:
                comp = self._graph.get_component(effect.component_id)
                if comp and effect.health == HealthStatus.DOWN:
                    estimated_downtime = max(
                        estimated_downtime,
                        comp.operational_profile.mttr_minutes,
                    )

        # Quick cost estimate
        cost_impact = 0.0
        if chain:
            for effect in chain.effects:
                comp = self._graph.get_component(effect.component_id)
                if comp and effect.health in (HealthStatus.DOWN, HealthStatus.OVERLOADED):
                    cost_impact += comp.cost_profile.revenue_per_minute * estimated_downtime

        return IncidentAnalysis(
            incident_id=incident_id,
            incident_title=title,
            affected_components=affected,
            blast_radius=len(affected),
            estimated_downtime_minutes=estimated_downtime,
            cost_impact_usd=cost_impact,
            cascade_chain=chain,
            severity=severity,
            recommendations=self._quick_recommendations(component_id, chain),
        )

    # ------------------------------------------------------------------
    # Analyze impact
    # ------------------------------------------------------------------

    def analyze_impact(self, incident: IncidentAnalysis) -> ImpactReport:
        """Deep-dive impact analysis combining cascade and financial engines.

        Args:
            incident: :class:`IncidentAnalysis` from :meth:`receive_incident`.

        Returns:
            :class:`ImpactReport` with detailed financial and cascade analysis.
        """
        chain = incident.cascade_chain
        if chain is None:
            chain = CascadeChain(trigger="unknown", total_components=len(self._graph.components))

        # Run full simulation to feed into financial engine
        engine = SimulationEngine(self._graph)
        report = engine.run_all()

        # Financial risk analysis
        fin_engine = FinancialRiskEngine(self._graph)
        fin_report = fin_engine.analyze(report)

        # Affected services (unique component names)
        affected_services = []
        for effect in chain.effects:
            comp = self._graph.get_component(effect.component_id)
            if comp:
                affected_services.append(comp.name)

        # Estimate recovery time
        recovery_hours = 0.0
        for effect in chain.effects:
            comp = self._graph.get_component(effect.component_id)
            if comp and effect.health == HealthStatus.DOWN:
                recovery_hours = max(
                    recovery_hours,
                    comp.operational_profile.mttr_minutes / 60.0,
                )

        return ImpactReport(
            incident_id=incident.incident_id,
            cascade=chain,
            financial=fin_report,
            affected_services=affected_services,
            estimated_recovery_hours=recovery_hours,
            total_cost_usd=fin_report.expected_annual_loss if fin_report else 0.0,
        )

    # ------------------------------------------------------------------
    # Add note to incident
    # ------------------------------------------------------------------

    def add_note(self, incident_id: str, note_text: str) -> bool:
        """Add an enrichment note to a PagerDuty incident via REST API.

        Args:
            incident_id: PagerDuty incident ID.
            note_text: Note content to append.

        Returns:
            True if the note was added (or mock mode).
        """
        if self._mock:
            logger.info(
                "Mock add_note: incident=%s note=%s",
                incident_id,
                note_text[:80],
            )
            return True

        try:
            with httpx.Client(
                base_url="https://api.pagerduty.com",
                timeout=15,
                headers={
                    "Authorization": f"Token token={self._api_key}",
                    "Content-Type": "application/json",
                },
            ) as client:
                resp = client.post(
                    f"/incidents/{incident_id}/notes",
                    json={"note": {"content": note_text}},
                )
                resp.raise_for_status()
                return True
        except Exception as exc:
            logger.warning("PagerDuty add_note failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Generate runbook
    # ------------------------------------------------------------------

    def generate_runbook(self, incident: IncidentAnalysis) -> str:
        """Auto-generate a runbook for the incident based on cascade analysis.

        Args:
            incident: :class:`IncidentAnalysis` from :meth:`receive_incident`.

        Returns:
            Markdown-formatted runbook string.
        """
        lines = [
            f"# Runbook: {incident.incident_title}",
            f"**Incident ID:** {incident.incident_id}",
            f"**Severity:** {incident.severity}",
            f"**Blast Radius:** {incident.blast_radius} components",
            f"**Estimated Downtime:** {incident.estimated_downtime_minutes:.0f} min",
            f"**Cost Impact:** ${incident.cost_impact_usd:,.2f}",
            "",
            "## Affected Components",
        ]

        for comp_id in incident.affected_components:
            comp = self._graph.get_component(comp_id)
            name = comp.name if comp else comp_id
            lines.append(f"- {name} (`{comp_id}`)")

        lines.extend(["", "## Resolution Steps"])
        for i, rec in enumerate(incident.recommendations, 1):
            lines.append(f"{i}. {rec}")

        if incident.cascade_chain:
            lines.extend(["", "## Cascade Details"])
            for effect in incident.cascade_chain.effects:
                lines.append(
                    f"- **{effect.component_name}**: {effect.health.value} -- {effect.reason}"
                )

        lines.extend([
            "",
            "## Verification",
            "- [ ] All affected components restored to HEALTHY",
            "- [ ] Monitoring dashboards show normal metrics",
            "- [ ] No cascading alerts in the last 15 minutes",
        ])

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Auto-resolve recommendation
    # ------------------------------------------------------------------

    def auto_resolve_recommendation(self, incident: IncidentAnalysis) -> list[str]:
        """Generate prioritized resolution recommendations.

        Args:
            incident: :class:`IncidentAnalysis` from :meth:`receive_incident`.

        Returns:
            List of recommended resolution steps, ordered by priority.
        """
        steps: list[str] = []

        if not incident.cascade_chain:
            return ["Investigate the incident manually -- no cascade data available."]

        # Find the root cause component
        root_effects = [
            e for e in incident.cascade_chain.effects
            if e.health == HealthStatus.DOWN
        ]

        if root_effects:
            root = root_effects[0]
            comp = self._graph.get_component(root.component_id)
            if comp:
                if comp.failover.enabled:
                    steps.append(
                        f"Trigger failover for {comp.name} "
                        f"(promotion time: {comp.failover.promotion_time_seconds}s)"
                    )
                if comp.autoscaling.enabled:
                    steps.append(
                        f"Verify autoscaling is active for {comp.name} "
                        f"(min: {comp.autoscaling.min_replicas}, "
                        f"max: {comp.autoscaling.max_replicas})"
                    )
                if comp.replicas > 1:
                    steps.append(
                        f"Check health of remaining {comp.replicas - 1} replicas of {comp.name}"
                    )
                steps.append(f"Restart {comp.name} if no failover available")

        # Downstream mitigation
        downstream = [
            e for e in incident.cascade_chain.effects
            if e.health in (HealthStatus.DEGRADED, HealthStatus.OVERLOADED)
        ]
        if downstream:
            steps.append(
                f"Monitor {len(downstream)} degraded downstream services for recovery"
            )

        steps.append("Verify all services return to HEALTHY status")
        steps.append("Review cascade chain for systemic improvements")

        return steps

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_component_id(self, incident: dict) -> str | None:
        """Try to map a PagerDuty incident to an InfraGraph component ID."""
        # Check service name
        service = incident.get("service", {})
        service_name = service.get("summary", service.get("name", ""))
        if service_name:
            for comp in self._graph.components.values():
                if (
                    comp.name.lower() == service_name.lower()
                    or comp.id.lower() == service_name.lower()
                ):
                    return comp.id

        # Check custom_details for component_id
        body = incident.get("body", {})
        details = body.get("details", {})
        if isinstance(details, dict):
            comp_id = details.get("component_id", details.get("host", ""))
            if comp_id and self._graph.get_component(comp_id):
                return comp_id

        # Check title for component references
        title = incident.get("title", "")
        for comp in self._graph.components.values():
            if comp.name.lower() in title.lower() or comp.id in title:
                return comp.id

        return None

    def _quick_recommendations(
        self, component_id: str | None, chain: CascadeChain | None,
    ) -> list[str]:
        """Generate quick recommendations from cascade analysis."""
        recs: list[str] = []
        if not component_id or not chain:
            return ["Investigate incident -- could not map to infrastructure component."]

        comp = self._graph.get_component(component_id)
        if comp:
            if comp.replicas <= 1:
                recs.append(
                    f"SPOF detected: {comp.name} has only {comp.replicas} replica(s). "
                    "Consider adding redundancy."
                )
            if not comp.failover.enabled:
                recs.append(f"Enable failover for {comp.name} to reduce MTTR.")
            if not comp.autoscaling.enabled and comp.utilization() > 60:
                recs.append(
                    f"Enable autoscaling for {comp.name} "
                    f"(current utilization: {comp.utilization():.0f}%)."
                )

        # Check for missing circuit breakers in affected edges
        if chain:
            for effect in chain.effects:
                dep_comp = self._graph.get_component(effect.component_id)
                if dep_comp and component_id:
                    edge = self._graph.get_dependency_edge(effect.component_id, component_id)
                    if edge and not edge.circuit_breaker.enabled:
                        recs.append(
                            f"Add circuit breaker on dependency "
                            f"{effect.component_name} -> {comp.name if comp else component_id}."
                        )

        return recs or ["No specific recommendations -- investigate manually."]
