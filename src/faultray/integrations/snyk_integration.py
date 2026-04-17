# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Snyk Integration -- vulnerability-to-infrastructure impact analysis.

Convert CVE vulnerabilities -> infrastructure failure scenarios -> business cost.

Traditional vulnerability scanners report severity in isolation (CVSS scores).
This integration bridges the gap by answering:
  "If this vulnerability is exploited, what is the *actual business impact*
   on our specific infrastructure?"

Workflow:
    1. Pull vulnerabilities from Snyk API v1
    2. Map each vulnerability to infrastructure failure scenarios
    3. Run SecurityResilienceEngine + CascadeEngine simulations
    4. Calculate financial impact with FinancialRiskEngine
    5. Re-prioritize vulnerabilities by actual business impact (not just CVSS)

Environment variables:
    SNYK_API_TOKEN  -- Snyk API authentication token
    SNYK_ORG_ID     -- Snyk organization ID

When the API token is not set, mock data is returned.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEngine
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.financial_risk import FinancialRiskEngine, FinancialRiskReport
from faultray.simulator.scenarios import Fault, FaultType, Scenario
from faultray.simulator.security_engine import SecurityResilienceEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Vulnerability:
    """Represents a single Snyk vulnerability."""

    id: str
    title: str
    severity: str  # critical, high, medium, low
    cvss: float  # 0.0 - 10.0
    package_name: str
    affected_versions: str
    description: str = ""
    exploit_maturity: str = "no-known-exploit"
    url: str = ""


@dataclass
class ImpactResult:
    """Result of simulating the infrastructure impact of a vulnerability."""

    vulnerability_id: str
    cascade: CascadeChain
    affected_components: list[str]
    blast_radius: int
    risk_score: float  # Combined CVSS + infrastructure risk
    estimated_downtime_minutes: float = 0.0


@dataclass
class PrioritizedVuln:
    """Vulnerability re-ranked by actual business impact."""

    vulnerability: Vulnerability
    business_impact_score: float  # 0-100
    original_cvss: float
    infrastructure_blast_radius: int
    estimated_cost_usd: float
    priority_rank: int = 0
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

_MOCK_VULNS: list[dict] = [
    {
        "id": "SNYK-JS-LODASH-1234",
        "title": "Prototype Pollution in lodash",
        "severity": "high",
        "cvssScore": 7.5,
        "packageName": "lodash",
        "version": "<4.17.21",
        "description": "Prototype pollution vulnerability allowing property injection.",
        "exploit": "Proof of Concept",
    },
    {
        "id": "SNYK-PYTHON-REQUESTS-5678",
        "title": "SSRF in requests",
        "severity": "medium",
        "cvssScore": 5.3,
        "packageName": "requests",
        "version": "<2.28.0",
        "description": "Server-Side Request Forgery via redirect handling.",
        "exploit": "No Known Exploit",
    },
    {
        "id": "SNYK-JS-EXPRESS-9012",
        "title": "Remote Code Execution in express",
        "severity": "critical",
        "cvssScore": 9.8,
        "packageName": "express",
        "version": "<4.18.0",
        "description": "RCE via crafted request to middleware chain.",
        "exploit": "Mature",
    },
]


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class SnykIntegration:
    """Vulnerability-to-infrastructure impact analysis with Snyk.

    Converts CVE vulnerabilities into concrete infrastructure failure
    scenarios, simulates their impact, and re-prioritizes by actual
    business cost rather than generic CVSS scores.

    Example::

        graph = InfraGraph.load(Path("infra.json"))
        snyk = SnykIntegration(
            api_token=os.environ.get("SNYK_API_TOKEN"),
            org_id=os.environ.get("SNYK_ORG_ID"),
            graph=graph,
        )
        vulns = snyk.pull_vulnerabilities()
        scenarios = snyk.convert_to_scenarios(vulns)
        impacts = snyk.simulate_impact(scenarios)
        cost = snyk.cost_impact(impacts)
        ranked = snyk.reprioritize(vulns, impacts)
    """

    def __init__(
        self,
        api_token: str | None = None,
        org_id: str | None = None,
        graph: InfraGraph | None = None,
    ) -> None:
        self._api_token = api_token or os.environ.get("SNYK_API_TOKEN", "")
        self._org_id = org_id or os.environ.get("SNYK_ORG_ID", "")
        self._graph = graph or InfraGraph()
        self._mock = not self._api_token
        if self._mock:
            logger.info("SnykIntegration running in mock mode (no API token).")

    # ------------------------------------------------------------------
    # Pull vulnerabilities
    # ------------------------------------------------------------------

    def pull_vulnerabilities(
        self, project_id: str | None = None,
    ) -> list[Vulnerability]:
        """Pull vulnerability data from Snyk API v1.

        Args:
            project_id: Optional Snyk project ID. If None, pulls org-level issues.

        Returns:
            List of :class:`Vulnerability` objects.
        """
        if self._mock:
            logger.debug("Returning mock Snyk vulnerabilities.")
            return [
                Vulnerability(
                    id=v["id"],
                    title=v["title"],
                    severity=v["severity"],
                    cvss=v["cvssScore"],
                    package_name=v["packageName"],
                    affected_versions=v["version"],
                    description=v.get("description", ""),
                    exploit_maturity=v.get("exploit", "no-known-exploit"),
                )
                for v in _MOCK_VULNS
            ]

        vulns: list[Vulnerability] = []
        endpoint = (
            f"/v1/org/{self._org_id}/project/{project_id}/aggregated-issues"
            if project_id
            else f"/v1/org/{self._org_id}/issues"
        )

        try:
            with httpx.Client(
                base_url="https://api.snyk.io",
                timeout=30,
                headers={
                    "Authorization": f"token {self._api_token}",
                    "Content-Type": "application/json",
                },
            ) as client:
                resp = client.post(endpoint, json={"filters": {}})
                resp.raise_for_status()
                data = resp.json()

                for issue in data.get("issues", []):
                    vuln_data = issue.get("issueData", issue)
                    vulns.append(Vulnerability(
                        id=vuln_data.get("id", ""),
                        title=vuln_data.get("title", ""),
                        severity=vuln_data.get("severity", "medium"),
                        cvss=vuln_data.get("cvssScore", 0.0),
                        package_name=vuln_data.get("packageName", ""),
                        affected_versions=vuln_data.get("version", ""),
                        description=vuln_data.get("description", ""),
                        exploit_maturity=vuln_data.get("exploit", "no-known-exploit"),
                        url=vuln_data.get("url", ""),
                    ))
        except Exception as exc:
            logger.warning("Snyk pull_vulnerabilities failed: %s", exc)

        return vulns

    # ------------------------------------------------------------------
    # Convert to scenarios
    # ------------------------------------------------------------------

    def convert_to_scenarios(
        self, vulns: list[Vulnerability],
    ) -> list[Scenario]:
        """Convert CVE vulnerabilities to FaultRay failure scenarios.

        Severity mapping:
            - critical -> COMPONENT_DOWN
            - high     -> CPU_SATURATION (resource exhaustion attack)
            - medium   -> LATENCY_SPIKE (degraded performance)
            - low      -> LATENCY_SPIKE (minor impact)

        Args:
            vulns: List of vulnerabilities from :meth:`pull_vulnerabilities`.

        Returns:
            List of :class:`Scenario` objects for simulation.
        """
        severity_to_fault: dict[str, FaultType] = {
            "critical": FaultType.COMPONENT_DOWN,
            "high": FaultType.CPU_SATURATION,
            "medium": FaultType.LATENCY_SPIKE,
            "low": FaultType.LATENCY_SPIKE,
        }

        scenarios: list[Scenario] = []

        for vuln in vulns:
            fault_type = severity_to_fault.get(vuln.severity, FaultType.LATENCY_SPIKE)

            # Find components that might use the vulnerable package
            target_components = self._find_affected_components(vuln)

            for comp_id in target_components:
                scenario = Scenario(
                    id=f"snyk-{vuln.id}-{comp_id}",
                    name=f"CVE: {vuln.title} on {comp_id}",
                    description=(
                        f"Simulates exploitation of {vuln.title} "
                        f"({vuln.package_name} {vuln.affected_versions}) "
                        f"on component {comp_id}. CVSS: {vuln.cvss}"
                    ),
                    faults=[
                        Fault(
                            target_component_id=comp_id,
                            fault_type=fault_type,
                            severity=min(1.0, vuln.cvss / 10.0),
                            parameters={
                                "vuln_id": vuln.id,
                                "cvss": vuln.cvss,
                                "package": vuln.package_name,
                            },
                        )
                    ],
                )
                scenarios.append(scenario)

        return scenarios

    # ------------------------------------------------------------------
    # Simulate impact
    # ------------------------------------------------------------------

    def simulate_impact(
        self, scenarios: list[Scenario],
    ) -> list[ImpactResult]:
        """Run cascade + security simulation for vulnerability scenarios.

        Args:
            scenarios: Scenarios from :meth:`convert_to_scenarios`.

        Returns:
            List of :class:`ImpactResult` for each scenario.
        """
        cascade_engine = CascadeEngine(self._graph)
        security_engine = SecurityResilienceEngine(self._graph)

        results: list[ImpactResult] = []
        security_score = security_engine.security_resilience_score()

        for scenario in scenarios:
            if not scenario.faults:
                continue

            fault = scenario.faults[0]
            chain = cascade_engine.simulate_fault(fault)

            # Calculate combined risk: cascade severity + inverse security posture
            cascade_risk = chain.severity
            security_factor = 1.0 - (security_score / 100.0)  # 0=fully secured, 1=no security
            combined_risk = cascade_risk * (1.0 + security_factor * 0.5)

            # Estimate downtime from affected components
            downtime = 0.0
            for effect in chain.effects:
                comp = self._graph.get_component(effect.component_id)
                if comp:
                    downtime = max(downtime, comp.operational_profile.mttr_minutes)

            results.append(ImpactResult(
                vulnerability_id=fault.parameters.get("vuln_id", scenario.id),
                cascade=chain,
                affected_components=[e.component_id for e in chain.effects],
                blast_radius=len(chain.effects),
                risk_score=min(10.0, combined_risk),
                estimated_downtime_minutes=downtime,
            ))

        return results

    # ------------------------------------------------------------------
    # Cost impact
    # ------------------------------------------------------------------

    def cost_impact(
        self, results: list[ImpactResult],
    ) -> FinancialRiskReport:
        """Calculate financial cost of vulnerability exploitation scenarios.

        Args:
            results: Impact results from :meth:`simulate_impact`.

        Returns:
            :class:`FinancialRiskReport` with aggregated financial impact.
        """
        engine = SimulationEngine(self._graph)
        report = engine.run_all()

        fin_engine = FinancialRiskEngine(self._graph)
        return fin_engine.analyze(report)

    # ------------------------------------------------------------------
    # Reprioritize
    # ------------------------------------------------------------------

    def reprioritize(
        self,
        vulns: list[Vulnerability],
        impacts: list[ImpactResult],
    ) -> list[PrioritizedVuln]:
        """Re-rank vulnerabilities by actual business impact.

        Instead of relying solely on CVSS scores, this combines:
        - CVSS score (generic severity)
        - Infrastructure blast radius (how much cascades)
        - Financial impact (revenue loss)
        - Exploit maturity (how likely to be exploited)

        Args:
            vulns: Original vulnerability list.
            impacts: Simulation impacts from :meth:`simulate_impact`.

        Returns:
            List of :class:`PrioritizedVuln` sorted by business_impact_score desc.
        """
        # Build impact lookup by vuln ID
        impact_map: dict[str, ImpactResult] = {}
        for impact in impacts:
            impact_map[impact.vulnerability_id] = impact

        prioritized: list[PrioritizedVuln] = []

        for vuln in vulns:
            impact = impact_map.get(vuln.id)

            # CVSS component (0-40 points)
            cvss_score = (vuln.cvss / 10.0) * 40.0

            # Blast radius component (0-30 points)
            total_components = max(len(self._graph.components), 1)
            if impact:
                blast_ratio = impact.blast_radius / total_components
                blast_score = blast_ratio * 30.0
            else:
                blast_score = 0.0

            # Exploit maturity component (0-20 points)
            maturity_map = {
                "mature": 20.0,
                "proof-of-concept": 15.0,
                "no-known-exploit": 5.0,
            }
            maturity_score = maturity_map.get(
                vuln.exploit_maturity.lower(), 5.0,
            )

            # Downtime cost component (0-10 points)
            if impact and impact.estimated_downtime_minutes > 0:
                # Scale: 60+ minutes = full 10 points
                downtime_score = min(10.0, impact.estimated_downtime_minutes / 60.0 * 10.0)
            else:
                downtime_score = 0.0

            business_impact = cvss_score + blast_score + maturity_score + downtime_score

            # Estimated cost from downtime
            estimated_cost = 0.0
            if impact:
                for comp_id in impact.affected_components:
                    comp = self._graph.get_component(comp_id)
                    if comp:
                        estimated_cost += (
                            comp.cost_profile.revenue_per_minute
                            * impact.estimated_downtime_minutes
                        )

            reasoning_parts = [
                f"CVSS {vuln.cvss} ({cvss_score:.0f}pts)",
                f"blast_radius {impact.blast_radius if impact else 0} ({blast_score:.0f}pts)",
                f"exploit {vuln.exploit_maturity} ({maturity_score:.0f}pts)",
                f"downtime ({downtime_score:.0f}pts)",
            ]

            prioritized.append(PrioritizedVuln(
                vulnerability=vuln,
                business_impact_score=round(business_impact, 1),
                original_cvss=vuln.cvss,
                infrastructure_blast_radius=impact.blast_radius if impact else 0,
                estimated_cost_usd=round(estimated_cost, 2),
                reasoning=", ".join(reasoning_parts),
            ))

        # Sort by business impact descending
        prioritized.sort(key=lambda p: p.business_impact_score, reverse=True)

        # Assign priority ranks
        for i, p in enumerate(prioritized):
            p.priority_rank = i + 1

        return prioritized

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_affected_components(self, vuln: Vulnerability) -> list[str]:
        """Find graph components likely affected by a vulnerability.

        Heuristic: match package name against component tags, names, or
        return all web/app server components for web framework vulns.
        """
        affected: list[str] = []
        pkg = vuln.package_name.lower()

        for comp_id, comp in self._graph.components.items():
            # Check tags for package references
            if any(pkg in tag.lower() for tag in comp.tags):
                affected.append(comp_id)
                continue

            # Check component name
            if pkg in comp.name.lower():
                affected.append(comp_id)
                continue

        # If no direct match, target web/app servers for web framework vulns
        if not affected:
            web_frameworks = {"express", "flask", "django", "fastapi", "spring", "rails"}
            if pkg in web_frameworks:
                for comp_id, comp in self._graph.components.items():
                    if comp.type in (ComponentType.WEB_SERVER, ComponentType.APP_SERVER):
                        affected.append(comp_id)

        # Fallback: if still no match, target all components
        if not affected:
            affected = list(self._graph.components.keys())

        return affected
