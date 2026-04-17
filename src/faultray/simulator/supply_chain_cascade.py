# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Supply chain attack propagation simulation.

Simulates how a compromised or vulnerable package propagates through
the infrastructure and agent layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


@dataclass
class PackageImpact:
    """Impact of a package vulnerability on the system."""

    package_name: str
    package_version: str
    cve_id: str
    severity: str
    affected_components: list[str]  # Component IDs
    total_blast_radius: int  # Including transitive dependents
    agent_hallucination_risk: bool  # If compromised package feeds data to agents
    risk_score: float  # 0-10
    attack_path: list[str]  # Package -> Component -> Dependent chain
    recommendation: str


@dataclass
class SupplyChainAttackReport:
    """Report of a simulated supply chain attack."""

    total_packages_analyzed: int
    vulnerable_packages: int
    compromised_packages: int
    package_impacts: list[PackageImpact] = field(default_factory=list)
    cross_layer_risks: list[str] = field(default_factory=list)  # Agent hallucination risks
    overall_risk_score: float = 0.0  # 0-100
    recommendations: list[str] = field(default_factory=list)


class SupplyChainCascadeEngine:
    """Simulates supply chain attack propagation across infra + agent layers."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def simulate_package_compromise(self, component_id: str, package_name: str) -> PackageImpact:
        """Simulate what happens when a specific package is compromised."""
        comp = self.graph.get_component(component_id)
        if comp is None:
            raise ValueError(f"Component '{component_id}' not found")

        # Get all transitively affected components
        affected = self.graph.get_all_affected(component_id)

        # Check for agent hallucination risk
        agent_risk = False
        agent_components = []
        for aid in affected:
            ac = self.graph.get_component(aid)
            if ac and ac.type in (ComponentType.AI_AGENT, ComponentType.AGENT_ORCHESTRATOR):
                agent_risk = True
                agent_components.append(ac.name)

        # Build attack path
        attack_path = [f"pkg:{package_name}", comp.name]
        for aid in list(affected)[:5]:  # First 5 for readability
            ac = self.graph.get_component(aid)
            if ac:
                attack_path.append(ac.name)

        # Calculate risk score
        blast = len(affected)
        risk_score = min(10.0, 4.0 + blast * 0.5 + (2.0 if agent_risk else 0.0))

        recommendation = self._generate_recommendation(comp, package_name, agent_risk, blast)

        return PackageImpact(
            package_name=package_name,
            package_version="",
            cve_id="",
            severity="critical",
            affected_components=[comp.id] + list(affected),
            total_blast_radius=blast,
            agent_hallucination_risk=agent_risk,
            risk_score=round(risk_score, 1),
            attack_path=attack_path,
            recommendation=recommendation,
        )

    def analyze_all_packages(self) -> SupplyChainAttackReport:
        """Analyze all components for supply chain risks based on their parameters."""
        impacts: list[PackageImpact] = []
        cross_layer_risks: list[str] = []
        total_packages = 0
        vulnerable = 0

        for comp in self.graph.components.values():
            params = comp.parameters or {}
            packages_str = str(params.get("packages", ""))
            if not packages_str or packages_str == "0":
                continue

            # Parse package list from parameters (comma-separated)
            pkg_list = [p.strip() for p in packages_str.split(",") if p.strip()]
            total_packages += len(pkg_list)

            for pkg in pkg_list:
                # Check if package has known vulnerability marker
                vuln_key = f"vuln_{pkg.replace('-', '_').replace('.', '_')}"
                if params.get(vuln_key):
                    vulnerable += 1
                    impact = self.simulate_package_compromise(comp.id, pkg)
                    impact.cve_id = str(params.get(vuln_key, ""))
                    impacts.append(impact)

                    if impact.agent_hallucination_risk:
                        cross_layer_risks.append(
                            f"Compromised package '{pkg}' in {comp.name} can feed "
                            f"poisoned data to AI agents, causing hallucinations"
                        )

        # Also check each component for general supply chain risk
        # Components without explicit package lists still have implicit dependencies
        for comp in self.graph.components.values():
            params = comp.parameters or {}
            sbom_risk = str(params.get("sbom_risk", ""))
            if sbom_risk in ("high", "critical"):
                impact = self.simulate_package_compromise(comp.id, f"{comp.name}-deps")
                impact.severity = sbom_risk
                impacts.append(impact)

        overall = (
            min(100.0, sum(i.risk_score for i in impacts) / max(len(impacts), 1) * 10)
            if impacts
            else 0.0
        )
        recommendations = self._aggregate_recommendations(impacts, cross_layer_risks)

        return SupplyChainAttackReport(
            total_packages_analyzed=total_packages,
            vulnerable_packages=vulnerable,
            compromised_packages=len([i for i in impacts if i.severity == "critical"]),
            package_impacts=impacts,
            cross_layer_risks=cross_layer_risks,
            overall_risk_score=round(overall, 1),
            recommendations=recommendations,
        )

    def _generate_recommendation(
        self, comp: Component, package_name: str, agent_risk: bool, blast: int
    ) -> str:
        parts = [f"Patch or replace '{package_name}' in {comp.name}."]
        if blast >= 5:
            parts.append(f"High blast radius ({blast} components). Prioritize immediate patching.")
        if agent_risk:
            parts.append(
                "CRITICAL: Compromised package can poison AI agent outputs. "
                "Isolate agent data sources from affected component immediately."
            )
        return " ".join(parts)

    def _aggregate_recommendations(
        self, impacts: list[PackageImpact], cross_layer_risks: list[str]
    ) -> list[str]:
        recs: list[str] = []
        critical = [i for i in impacts if i.risk_score >= 7.0]
        if critical:
            recs.append(f"URGENT: {len(critical)} critical supply chain risks require immediate action")
        if cross_layer_risks:
            recs.append(
                f"AI SAFETY: {len(cross_layer_risks)} supply chain risks can cause agent hallucinations"
            )
        high_blast = [i for i in impacts if i.total_blast_radius >= 5]
        if high_blast:
            recs.append(
                f"BLAST RADIUS: {len(high_blast)} packages affect 5+ components. "
                "Consider network segmentation"
            )
        if not recs:
            recs.append("No critical supply chain risks detected")
        return recs
