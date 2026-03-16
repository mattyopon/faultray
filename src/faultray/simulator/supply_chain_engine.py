"""Supply Chain Risk Engine — map software vulnerabilities to infrastructure impact.

Reads vulnerability reports in Snyk, Dependabot, or Trivy JSON format and
maps each CVE to an infrastructure failure mode via the InfraGraph.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph


# Severity levels ordered by impact
SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

# Mapping from component type to typical infrastructure impact
_IMPACT_BY_COMPONENT_TYPE: dict[str, dict[str, str]] = {
    "database": {
        "critical": "data breach",
        "high": "data corruption",
        "medium": "degraded queries",
        "low": "minor performance impact",
    },
    "cache": {
        "critical": "cache poisoning",
        "high": "OOM",
        "medium": "degraded hit ratio",
        "low": "minor latency increase",
    },
    "app_server": {
        "critical": "remote code execution",
        "high": "OOM",
        "medium": "CPU spike",
        "low": "degraded performance",
    },
    "web_server": {
        "critical": "remote code execution",
        "high": "denial of service",
        "medium": "CPU spike",
        "low": "degraded performance",
    },
    "load_balancer": {
        "critical": "traffic hijack",
        "high": "denial of service",
        "medium": "degraded routing",
        "low": "minor latency increase",
    },
    "queue": {
        "critical": "message tampering",
        "high": "message loss",
        "medium": "delayed processing",
        "low": "minor latency increase",
    },
    "storage": {
        "critical": "data breach",
        "high": "data loss",
        "medium": "degraded throughput",
        "low": "minor latency increase",
    },
    "external_api": {
        "critical": "supply chain compromise",
        "high": "API abuse",
        "medium": "degraded availability",
        "low": "minor impact",
    },
}

DEFAULT_IMPACT: dict[str, str] = {
    "critical": "remote code execution",
    "high": "OOM",
    "medium": "CPU spike",
    "low": "degraded performance",
}


@dataclass
class VulnerabilityImpact:
    """A single vulnerability mapped to infrastructure impact."""

    cve_id: str
    package: str
    severity: str
    affected_components: list[str]
    infrastructure_impact: str  # e.g. "CPU spike", "OOM", "data breach"
    estimated_blast_radius: int  # number of transitively affected components
    risk_score: float  # 0-10


@dataclass
class SupplyChainReport:
    """Aggregated supply chain risk analysis for an infrastructure graph."""

    total_vulnerabilities: int
    critical_count: int
    infrastructure_risk_score: float  # 0-100
    impacts: list[VulnerabilityImpact] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class SupplyChainEngine:
    """Map software vulnerabilities to infrastructure failure modes."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_from_file(self, vuln_file: Path) -> SupplyChainReport:
        """Load vulnerabilities from a JSON file (Snyk / Dependabot / Trivy).

        The file must be an array of objects *or* a top-level object with a
        ``vulnerabilities`` or ``results`` key containing an array.
        """
        raw = json.loads(vuln_file.read_text(encoding="utf-8"))
        entries = self._normalize_input(raw)
        return self._analyze(entries)

    def analyze_from_data(self, data: list[dict]) -> SupplyChainReport:
        """Analyse a list of vulnerability dicts directly."""
        return self._analyze(data)

    def map_cve_to_impact(
        self,
        cve_id: str,
        severity: str,
        affected_components: list[str],
        package: str = "",
    ) -> VulnerabilityImpact:
        """Map a single CVE to an infrastructure failure mode."""
        severity = severity.lower()

        # Determine component types for affected components
        comp_types = set()
        for cid in affected_components:
            comp = self._graph.get_component(cid)
            if comp:
                comp_types.add(comp.type.value)

        # Determine infrastructure impact based on component type and severity
        impact = self._determine_impact(comp_types, severity)

        # Calculate blast radius (transitively affected components)
        blast_radius = 0
        for cid in affected_components:
            affected = self._graph.get_all_affected(cid)
            blast_radius = max(blast_radius, len(affected))

        # Risk score: severity * blast_radius normalised to 0-10
        sev_weight = SEVERITY_ORDER.get(severity, 1)
        risk_score = min(10.0, sev_weight * 2.0 + min(blast_radius, 3) * 0.5)

        return VulnerabilityImpact(
            cve_id=cve_id,
            package=package,
            severity=severity,
            affected_components=affected_components,
            infrastructure_impact=impact,
            estimated_blast_radius=blast_radius,
            risk_score=round(risk_score, 1),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_input(raw: dict | list) -> list[dict]:
        """Normalise raw JSON into a list of vulnerability dicts.

        Supports:
        * Direct array of vulnerability objects
        * Snyk format: ``{"vulnerabilities": [...]}``
        * Trivy format: ``{"Results": [{"Vulnerabilities": [...]}]}``
        * Dependabot/generic: ``{"results": [...]}``
        """
        if isinstance(raw, list):
            return raw

        if not isinstance(raw, dict):
            return []

        # Snyk
        if "vulnerabilities" in raw:
            return raw["vulnerabilities"]

        # Trivy
        if "Results" in raw:
            vulns: list[dict] = []
            for result in raw["Results"]:
                vulns.extend(result.get("Vulnerabilities", []))
            return vulns

        # Dependabot / generic
        if "results" in raw:
            return raw["results"]

        return []

    def _analyze(self, entries: list[dict]) -> SupplyChainReport:
        """Core analysis: iterate over vulnerability entries and build a report."""
        impacts: list[VulnerabilityImpact] = []
        component_ids = list(self._graph.components.keys())

        for entry in entries:
            cve_id = (
                entry.get("cve_id")
                or entry.get("VulnerabilityID")
                or entry.get("id")
                or entry.get("advisory", {}).get("cve_id", "UNKNOWN")
            )
            severity = (
                entry.get("severity")
                or entry.get("Severity")
                or entry.get("advisory", {}).get("severity", "medium")
            ).lower()
            package = (
                entry.get("package")
                or entry.get("PkgName")
                or entry.get("name")
                or ""
            )
            affected = entry.get("affected_components", [])

            # If no explicit component mapping, map by heuristic
            if not affected:
                affected = self._auto_map_components(entry, component_ids)

            impact = self.map_cve_to_impact(cve_id, severity, affected, package=package)
            impacts.append(impact)

        # Aggregate
        critical_count = sum(1 for i in impacts if i.severity == "critical")
        total = len(impacts)

        # Infrastructure risk score: weighted sum normalised to 0-100
        if total > 0:
            raw_score = sum(i.risk_score for i in impacts) / total * 10
            risk_score = min(100.0, raw_score)
        else:
            risk_score = 0.0

        recommendations = self._generate_recommendations(impacts)

        return SupplyChainReport(
            total_vulnerabilities=total,
            critical_count=critical_count,
            infrastructure_risk_score=round(risk_score, 1),
            impacts=impacts,
            recommendations=recommendations,
        )

    def _auto_map_components(
        self,
        entry: dict,
        component_ids: list[str],
    ) -> list[str]:
        """Heuristically map a vulnerability to infrastructure components.

        Uses the package name and vulnerability description to guess which
        component types are likely affected.
        """
        package = (
            entry.get("package")
            or entry.get("PkgName")
            or entry.get("name")
            or ""
        ).lower()
        description = (
            entry.get("description")
            or entry.get("Description")
            or entry.get("title")
            or ""
        ).lower()

        haystack = f"{package} {description}"

        matched_types: set[str] = set()
        type_keywords: dict[str, list[str]] = {
            "database": ["sql", "postgres", "mysql", "mongo", "redis", "database", "db"],
            "cache": ["cache", "redis", "memcache", "varnish"],
            "app_server": ["express", "flask", "django", "spring", "fastapi", "node", "server"],
            "web_server": ["nginx", "apache", "httpd", "web"],
            "queue": ["kafka", "rabbitmq", "sqs", "queue", "amqp"],
            "load_balancer": ["haproxy", "envoy", "loadbalancer", "proxy"],
            "storage": ["s3", "storage", "blob", "minio"],
        }

        for ctype, keywords in type_keywords.items():
            for kw in keywords:
                if kw in haystack:
                    matched_types.add(ctype)
                    break

        # Find matching component IDs in the graph
        matched_ids = [
            c.id
            for c in self._graph.components.values()
            if c.type.value in matched_types
        ]

        # If nothing matched, return first component as fallback
        if not matched_ids and component_ids:
            return [component_ids[0]]
        return matched_ids

    def _determine_impact(self, comp_types: set[str], severity: str) -> str:
        """Determine infrastructure impact from component types and severity."""
        # Use the most severe impact among the affected component types
        best_impact = DEFAULT_IMPACT.get(severity, "degraded performance")
        for ctype in comp_types:
            impacts = _IMPACT_BY_COMPONENT_TYPE.get(ctype, DEFAULT_IMPACT)
            impact = impacts.get(severity, best_impact)
            # Prefer more specific impacts
            if impact != best_impact:
                best_impact = impact
                break
        return best_impact

    @staticmethod
    def _generate_recommendations(impacts: list[VulnerabilityImpact]) -> list[str]:
        """Generate actionable recommendations from impact analysis."""
        recommendations: list[str] = []
        criticals = [i for i in impacts if i.severity == "critical"]
        highs = [i for i in impacts if i.severity == "high"]

        if criticals:
            packages = list({i.package for i in criticals if i.package})
            recommendations.append(
                f"URGENT: Patch {len(criticals)} critical vulnerabilities "
                f"immediately ({', '.join(packages[:5])})"
            )

        if highs:
            recommendations.append(
                f"Schedule patching of {len(highs)} high-severity vulnerabilities "
                f"within 7 days"
            )

        # High blast radius warnings
        high_blast = [i for i in impacts if i.estimated_blast_radius >= 3]
        if high_blast:
            recommendations.append(
                f"{len(high_blast)} vulnerabilities have blast radius >= 3 components. "
                f"Consider network segmentation to limit cascading impact."
            )

        # Generic advice
        data_breach_risks = [i for i in impacts if "breach" in i.infrastructure_impact]
        if data_breach_risks:
            recommendations.append(
                "Enable encryption at rest and in transit for components at risk of data breach"
            )

        if not recommendations and impacts:
            recommendations.append(
                "All vulnerabilities are low/medium severity. Monitor and patch during next cycle."
            )

        if not impacts:
            recommendations.append(
                "No vulnerabilities detected. Continue regular scanning."
            )

        return recommendations
