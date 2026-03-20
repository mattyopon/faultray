# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Overmind Bridge -- blast radius analysis + FaultRay cascade simulation.

Overmind (overmind.tech) analyzes Terraform plan blast radius by querying live
cloud APIs.  FaultRay simulates how failures cascade through the dependency
graph.  Together they answer two complementary questions:

- **Overmind**: "What cloud resources get affected by this Terraform change?"
- **FaultRay**: "How does that change propagate as a failure cascade?"

Workflow::

    1. Run Overmind on a terraform plan (obtains blast radius JSON)
    2. Parse Overmind output -> :class:`OvermindAnalysis`
    3. Map affected resources -> FaultRay :class:`InfraGraph` components
    4. Run FaultRay cascade simulation on those components
    5. Produce combined :class:`EnrichedAnalysis` + JSON report

Example usage::

    bridge = OvermindBridge(graph=my_infra_graph)
    with open("overmind_output.json") as fh:
        raw = json.load(fh)
    analysis = OvermindBridge.from_overmind_json(raw)
    enriched = bridge.enrich_with_cascade(analysis, my_infra_graph)
    report = bridge.generate_combined_report(enriched)
    print(json.dumps(report, indent=2))

Overmind JSON schema (as observed / documented):
    {
      "metadata": {"run_id": "...", "plan_file": "...", ...},
      "risks": [
        {
          "uuid": "...",
          "severity": "critical|high|medium|low|info",
          "title": "...",
          "description": "...",
          "context": {...}   # optional extra info
        }
      ],
      "changes": [
        {
          "resource_type": "aws_instance",
          "resource_address": "aws_instance.web",
          "action": "create|update|delete|replace",
          "blast_radius": {
            "directly_affected": ["res_a", "res_b"],
            "indirectly_affected": ["res_c"],
            "affected_count": 3
          }
        }
      ]
    }

When the schema varies, reasonable defaults are used.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------

_SEVERITY_ORDER: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "info": 0,
}

_SEVERITY_SCORE: dict[str, float] = {
    "critical": 9.0,
    "high": 7.0,
    "medium": 5.0,
    "low": 2.5,
    "info": 0.5,
}


def _normalize_severity(raw: str) -> str:
    """Normalize a severity string to lowercase, defaulting to 'medium'."""
    normalized = raw.strip().lower() if raw else "medium"
    return normalized if normalized in _SEVERITY_ORDER else "medium"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class OvermindRisk:
    """A single risk identified by Overmind."""

    uuid: str
    severity: str  # critical | high | medium | low | info
    title: str
    description: str
    context: dict = field(default_factory=dict)

    @property
    def severity_score(self) -> float:
        """Numeric severity score (0-10) for ranking."""
        return _SEVERITY_SCORE.get(self.severity, 5.0)

    @property
    def severity_rank(self) -> int:
        """Integer rank for sorting (higher = more severe)."""
        return _SEVERITY_ORDER.get(self.severity, 2)


@dataclass
class OvermindBlastRadius:
    """Blast radius details attached to a single change."""

    directly_affected: list[str] = field(default_factory=list)
    indirectly_affected: list[str] = field(default_factory=list)

    @property
    def all_affected(self) -> list[str]:
        """All affected resource addresses (direct + indirect, deduplicated)."""
        seen: set[str] = set()
        result: list[str] = []
        for addr in self.directly_affected + self.indirectly_affected:
            if addr not in seen:
                seen.add(addr)
                result.append(addr)
        return result

    @property
    def affected_count(self) -> int:
        return len(self.all_affected)


@dataclass
class OvermindChange:
    """A single resource change from Overmind output."""

    resource_type: str
    resource_address: str
    action: str  # create | update | delete | replace
    blast_radius: OvermindBlastRadius = field(default_factory=OvermindBlastRadius)

    @property
    def is_destructive(self) -> bool:
        """True if the change removes or replaces a resource."""
        return self.action in ("delete", "replace", "destroy")


@dataclass
class OvermindAnalysis:
    """Parsed result of running Overmind on a Terraform plan."""

    risks: list[OvermindRisk] = field(default_factory=list)
    changes: list[OvermindChange] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def critical_risks(self) -> list[OvermindRisk]:
        return [r for r in self.risks if r.severity in ("critical", "high")]

    @property
    def all_blast_radius_items(self) -> list[str]:
        """Deduplicated union of all blast-radius items across all changes."""
        seen: set[str] = set()
        result: list[str] = []
        for change in self.changes:
            for addr in change.blast_radius.all_affected:
                if addr not in seen:
                    seen.add(addr)
                    result.append(addr)
        return result

    @property
    def highest_risk_severity(self) -> str:
        """Highest severity level present in risks."""
        if not self.risks:
            return "info"
        return max(self.risks, key=lambda r: r.severity_rank).severity


@dataclass
class CascadeImpact:
    """FaultRay cascade result for a single affected component."""

    component_id: str
    component_name: str
    triggered_by: str  # Overmind change address that triggered this
    cascade_chain: CascadeChain | None
    affected_downstream: list[str] = field(default_factory=list)
    overall_severity: float = 0.0


@dataclass
class EnrichedAnalysis:
    """Combined Overmind blast radius + FaultRay cascade simulation result."""

    overmind: OvermindAnalysis
    cascade_impacts: list[CascadeImpact] = field(default_factory=list)
    unmapped_resources: list[str] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def total_cascade_affected(self) -> list[str]:
        """All components affected by any cascade (deduplicated)."""
        seen: set[str] = set()
        result: list[str] = []
        for impact in self.cascade_impacts:
            if impact.component_id not in seen:
                seen.add(impact.component_id)
                result.append(impact.component_id)
            for comp_id in impact.affected_downstream:
                if comp_id not in seen:
                    seen.add(comp_id)
                    result.append(comp_id)
        return result

    @property
    def max_cascade_severity(self) -> float:
        """Highest overall_severity across all cascade impacts."""
        if not self.cascade_impacts:
            return 0.0
        return max(i.overall_severity for i in self.cascade_impacts)


# ---------------------------------------------------------------------------
# OvermindBridge
# ---------------------------------------------------------------------------


class OvermindBridge:
    """Bridge between Overmind blast radius analysis and FaultRay cascade simulation.

    Combines Overmind's live-cloud blast radius assessment with FaultRay's
    fast, safe cascade simulation to give a complete picture of deployment risk:

    - **Before deployment**: understand *what* will be affected (Overmind) and
      *how bad* the cascade failure would be if something goes wrong (FaultRay).
    - **Risk prioritization**: surface which Terraform changes carry the highest
      combined blast-radius + cascade-severity risk.

    Example::

        graph = InfraGraph.load(Path("infra.json"))
        bridge = OvermindBridge(graph=graph)
        with open("overmind_output.json") as fh:
            raw = json.load(fh)
        analysis = OvermindBridge.from_overmind_json(raw)
        enriched = bridge.enrich_with_cascade(analysis, graph)
        report = bridge.generate_combined_report(enriched)
    """

    def __init__(self, graph: InfraGraph | None = None) -> None:
        self._graph = graph or InfraGraph()

    # ------------------------------------------------------------------
    # Parse Overmind JSON
    # ------------------------------------------------------------------

    @staticmethod
    def from_overmind_json(data: dict) -> OvermindAnalysis:
        """Parse Overmind JSON output into an :class:`OvermindAnalysis`.

        Designed to be flexible: unknown or missing keys are handled with
        reasonable defaults so that variations in Overmind's output schema
        do not cause hard failures.

        Args:
            data: Parsed Overmind JSON (dict).

        Returns:
            :class:`OvermindAnalysis` with parsed risks, changes, and metadata.
        """
        # -- metadata --
        metadata: dict = data.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        # -- risks --
        risks: list[OvermindRisk] = []
        for raw_risk in data.get("risks", []):
            if not isinstance(raw_risk, dict):
                continue
            risks.append(
                OvermindRisk(
                    uuid=str(raw_risk.get("uuid", raw_risk.get("id", ""))),
                    severity=_normalize_severity(raw_risk.get("severity", "medium")),
                    title=str(raw_risk.get("title", raw_risk.get("name", "Unknown risk"))),
                    description=str(raw_risk.get("description", raw_risk.get("detail", ""))),
                    context=raw_risk.get("context", raw_risk.get("extra", {})) or {},
                )
            )

        # -- changes --
        changes: list[OvermindChange] = []
        for raw_change in data.get("changes", []):
            if not isinstance(raw_change, dict):
                continue

            raw_br = raw_change.get("blast_radius", {}) or {}
            if not isinstance(raw_br, dict):
                raw_br = {}

            directly = raw_br.get("directly_affected", raw_br.get("direct", [])) or []
            indirectly = raw_br.get("indirectly_affected", raw_br.get("indirect", [])) or []

            # Some schemas embed affected items at change level
            if not directly and not indirectly:
                directly = raw_change.get("affected", raw_change.get("impacted", [])) or []

            blast = OvermindBlastRadius(
                directly_affected=list(directly),
                indirectly_affected=list(indirectly),
            )

            changes.append(
                OvermindChange(
                    resource_type=str(
                        raw_change.get("resource_type", raw_change.get("type", "unknown"))
                    ),
                    resource_address=str(
                        raw_change.get(
                            "resource_address",
                            raw_change.get("address", raw_change.get("resource", "")),
                        )
                    ),
                    action=str(raw_change.get("action", raw_change.get("change_type", "update"))).lower(),
                    blast_radius=blast,
                )
            )

        logger.info(
            "Parsed Overmind output: %d risks, %d changes", len(risks), len(changes)
        )
        return OvermindAnalysis(risks=risks, changes=changes, metadata=metadata)

    # ------------------------------------------------------------------
    # Enrich with cascade simulation
    # ------------------------------------------------------------------

    def enrich_with_cascade(
        self,
        analysis: OvermindAnalysis,
        graph: InfraGraph | None = None,
    ) -> EnrichedAnalysis:
        """Run FaultRay cascade simulation on blast-radius components.

        For each resource in Overmind's blast radius, attempts to find a
        matching component in the InfraGraph and simulates a
        :data:`~faultray.simulator.scenarios.FaultType.COMPONENT_DOWN` fault.
        This reveals which additional downstream services would be affected.

        Resources that cannot be mapped to a graph component are recorded in
        :attr:`EnrichedAnalysis.unmapped_resources` rather than silently dropped.

        Args:
            analysis: Parsed :class:`OvermindAnalysis` from Overmind output.
            graph: :class:`InfraGraph` to simulate against.  Uses the graph
                passed to the constructor when *None*.

        Returns:
            :class:`EnrichedAnalysis` with cascade simulation results attached.
        """
        g = graph or self._graph
        cascade_engine = CascadeEngine(g)

        cascade_impacts: list[CascadeImpact] = []
        unmapped: list[str] = []

        for change in analysis.changes:
            for resource_addr in change.blast_radius.all_affected:
                comp_id = self._resolve_resource(resource_addr, g)
                if comp_id is None:
                    if resource_addr not in unmapped:
                        logger.debug(
                            "Overmind resource '%s' not found in InfraGraph.", resource_addr
                        )
                        unmapped.append(resource_addr)
                    continue

                comp = g.get_component(comp_id)
                if comp is None:
                    continue

                # Choose fault type based on Overmind change action
                fault_type = self._action_to_fault_type(change.action)
                fault = Fault(
                    target_component_id=comp_id,
                    fault_type=fault_type,
                    severity=1.0,
                    duration_seconds=300,
                    parameters={"overmind_change": change.resource_address},
                )

                try:
                    chain = cascade_engine.simulate_fault(fault)
                except Exception as exc:  # pragma: no cover
                    logger.warning(
                        "Cascade simulation failed for component '%s': %s", comp_id, exc
                    )
                    chain = None

                downstream = (
                    [e.component_id for e in chain.effects if e.component_id != comp_id]
                    if chain
                    else []
                )
                overall_severity = chain.severity if chain else 0.0

                cascade_impacts.append(
                    CascadeImpact(
                        component_id=comp_id,
                        component_name=comp.name,
                        triggered_by=change.resource_address,
                        cascade_chain=chain,
                        affected_downstream=downstream,
                        overall_severity=overall_severity,
                    )
                )

        return EnrichedAnalysis(
            overmind=analysis,
            cascade_impacts=cascade_impacts,
            unmapped_resources=unmapped,
        )

    # ------------------------------------------------------------------
    # Generate combined report
    # ------------------------------------------------------------------

    def generate_combined_report(self, enriched: EnrichedAnalysis) -> dict:
        """Generate a combined JSON report from an :class:`EnrichedAnalysis`.

        The report merges Overmind's blast radius data with FaultRay's cascade
        simulation results into a single dict suitable for CI/CD output,
        dashboards, or further tooling.

        Report structure::

            {
              "generated_at": "<ISO 8601 timestamp>",
              "summary": { ... },
              "overmind": { "risks": [...], "changes": [...] },
              "cascade_analysis": { "impacts": [...] },
              "recommendations": [ ... ],
            }

        Args:
            enriched: :class:`EnrichedAnalysis` from :meth:`enrich_with_cascade`.

        Returns:
            Combined report as a plain dict.
        """
        analysis = enriched.overmind

        # -- Summary --
        risk_by_severity: dict[str, int] = {}
        for risk in analysis.risks:
            risk_by_severity[risk.severity] = risk_by_severity.get(risk.severity, 0) + 1

        summary = {
            "overmind_risks": len(analysis.risks),
            "overmind_changes": len(analysis.changes),
            "blast_radius_items": len(analysis.all_blast_radius_items),
            "highest_risk_severity": analysis.highest_risk_severity,
            "risks_by_severity": risk_by_severity,
            "faultray_components_simulated": len(enriched.cascade_impacts),
            "faultray_unmapped_resources": len(enriched.unmapped_resources),
            "faultray_total_cascade_affected": len(enriched.total_cascade_affected),
            "faultray_max_cascade_severity": round(enriched.max_cascade_severity, 2),
        }

        # -- Overmind section --
        risks_out = [
            {
                "uuid": r.uuid,
                "severity": r.severity,
                "title": r.title,
                "description": r.description,
            }
            for r in sorted(analysis.risks, key=lambda r: r.severity_rank, reverse=True)
        ]

        changes_out = [
            {
                "resource_type": c.resource_type,
                "resource_address": c.resource_address,
                "action": c.action,
                "is_destructive": c.is_destructive,
                "directly_affected": c.blast_radius.directly_affected,
                "indirectly_affected": c.blast_radius.indirectly_affected,
                "affected_count": c.blast_radius.affected_count,
            }
            for c in analysis.changes
        ]

        # -- Cascade section --
        impacts_out: list[dict] = []
        for impact in sorted(
            enriched.cascade_impacts, key=lambda i: i.overall_severity, reverse=True
        ):
            chain_effects: list[dict] = []
            if impact.cascade_chain:
                for effect in impact.cascade_chain.effects:
                    chain_effects.append(
                        {
                            "component_id": effect.component_id,
                            "component_name": effect.component_name,
                            "health": effect.health.value,
                            "reason": effect.reason,
                        }
                    )

            impacts_out.append(
                {
                    "component_id": impact.component_id,
                    "component_name": impact.component_name,
                    "triggered_by": impact.triggered_by,
                    "cascade_severity": round(impact.overall_severity, 2),
                    "affected_downstream": impact.affected_downstream,
                    "cascade_effects": chain_effects,
                }
            )

        # -- Recommendations --
        recommendations = self._build_recommendations(enriched)

        return {
            "generated_at": enriched.generated_at,
            "summary": summary,
            "overmind": {
                "risks": risks_out,
                "changes": changes_out,
                "metadata": analysis.metadata,
            },
            "cascade_analysis": {
                "impacts": impacts_out,
                "unmapped_resources": enriched.unmapped_resources,
                "total_cascade_affected": enriched.total_cascade_affected,
            },
            "recommendations": recommendations,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _action_to_fault_type(action: str) -> FaultType:
        """Map an Overmind change action to a FaultRay FaultType."""
        mapping: dict[str, FaultType] = {
            "delete": FaultType.COMPONENT_DOWN,
            "destroy": FaultType.COMPONENT_DOWN,
            "replace": FaultType.COMPONENT_DOWN,
            "update": FaultType.LATENCY_SPIKE,
            "create": FaultType.LATENCY_SPIKE,
            "no-op": FaultType.LATENCY_SPIKE,
        }
        return mapping.get(action.lower(), FaultType.COMPONENT_DOWN)

    @staticmethod
    def _resolve_resource(resource_addr: str, graph: InfraGraph) -> str | None:
        """Resolve an Overmind resource address to an InfraGraph component ID.

        Tries several matching strategies in order:
        1. Exact match on component ID.
        2. Exact match on component name.
        3. Suffix match: the last segment of the Terraform address (e.g.,
           ``aws_instance.web`` -> ``web``) matched against component names.
        4. Case-insensitive partial name match.
        """
        if not resource_addr:
            return None

        # 1. Exact ID match
        if graph.get_component(resource_addr):
            return resource_addr

        # 2. Exact name match
        for comp in graph.components.values():
            if comp.name == resource_addr:
                return comp.id

        # 3. Suffix match (e.g. "aws_instance.web" -> "web")
        suffix = resource_addr.rsplit(".", 1)[-1]
        for comp in graph.components.values():
            if comp.name.lower() == suffix.lower():
                return comp.id

        # 4. Case-insensitive partial match on the full address
        addr_lower = resource_addr.lower()
        for comp in graph.components.values():
            name_lower = comp.name.lower()
            if name_lower in addr_lower or addr_lower in name_lower:
                return comp.id

        return None

    @staticmethod
    def _build_recommendations(enriched: EnrichedAnalysis) -> list[str]:
        """Build human-readable recommendations from an :class:`EnrichedAnalysis`."""
        recs: list[str] = []

        # High-severity Overmind risks
        critical_risks = enriched.overmind.critical_risks
        if critical_risks:
            recs.append(
                f"Overmind identified {len(critical_risks)} critical/high-severity risk(s). "
                "Review these before applying the Terraform plan: "
                + "; ".join(r.title for r in critical_risks[:3])
                + ("..." if len(critical_risks) > 3 else ".")
            )

        # High cascade severity
        if enriched.max_cascade_severity >= 7.0:
            worst = max(enriched.cascade_impacts, key=lambda i: i.overall_severity)
            recs.append(
                f"FaultRay cascade simulation shows CRITICAL severity "
                f"({enriched.max_cascade_severity:.1f}/10) if component "
                f"'{worst.component_name}' fails. "
                "Verify resilience patterns (circuit breakers, replicas, failover) "
                "before deploying."
            )
        elif enriched.max_cascade_severity >= 4.0:
            recs.append(
                f"FaultRay cascade simulation shows moderate severity "
                f"({enriched.max_cascade_severity:.1f}/10). "
                "Consider deploying during a low-traffic window."
            )

        # Destructive changes
        destructive = [c for c in enriched.overmind.changes if c.is_destructive]
        if destructive:
            recs.append(
                f"{len(destructive)} destructive change(s) detected "
                f"({', '.join(c.resource_address for c in destructive[:3])}). "
                "Ensure data is backed up and rollback procedures are in place."
            )

        # Large blast radius
        blast_count = len(enriched.overmind.all_blast_radius_items)
        if blast_count >= 10:
            recs.append(
                f"Large blast radius: {blast_count} resources affected by this plan. "
                "Consider applying changes incrementally."
            )

        # Unmapped resources warning
        if enriched.unmapped_resources:
            recs.append(
                f"{len(enriched.unmapped_resources)} Overmind resource(s) could not be "
                "mapped to the FaultRay model. The cascade analysis may be incomplete. "
                "Update the FaultRay model or run 'faultray scan' to discover components."
            )

        if not recs:
            recs.append(
                "No critical risks detected. The blast radius is contained and cascade "
                "severity is low. The plan appears safe to apply."
            )

        return recs
