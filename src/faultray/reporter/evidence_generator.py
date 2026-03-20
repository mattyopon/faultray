# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Compliance Evidence Auto-Generator.

Automatically generates audit-ready compliance evidence from FaultRay
simulation results.  Maps simulation outputs to real control IDs
for SOC 2, DORA, ISO 27001, and PCI-DSS frameworks.  Exports to CSV.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EvidenceItem:
    """A single piece of compliance evidence."""

    framework: str  # SOC2, ISO27001, PCI-DSS, DORA
    control_id: str
    control_description: str
    test_performed: str
    test_date: str
    result: str  # "Pass", "Fail", "Partial"
    evidence_detail: str
    simulation_id: str | None = None


@dataclass
class EvidencePackage:
    """A complete evidence package for one compliance framework."""

    framework: str
    generated_at: str
    total_controls_tested: int
    passed: int
    failed: int
    coverage_percent: float
    items: list[EvidenceItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Control mappings
# ---------------------------------------------------------------------------

CONTROL_MAPPINGS: dict[str, dict[str, dict[str, str]]] = {
    "SOC2": {
        "CC9.1": {
            "test": "chaos_simulation",
            "description": "Risk mitigation — change management testing",
        },
        "A1.2": {
            "test": "availability_model",
            "description": "Availability — system availability commitment",
        },
        "CC7.2": {
            "test": "security_analysis",
            "description": "System operations — security event monitoring",
        },
        "CC8.1": {
            "test": "dr_simulation",
            "description": "Change management — disaster recovery testing",
        },
        "CC6.1": {
            "test": "security_analysis",
            "description": "Logical and physical access — access controls",
        },
        "CC7.1": {
            "test": "chaos_simulation",
            "description": "System operations — monitoring infrastructure",
        },
    },
    "DORA": {
        "Art.11": {
            "test": "resilience_score",
            "description": "ICT risk management — resilience testing",
        },
        "Art.23": {
            "test": "incident_reporting",
            "description": "ICT incident classification and reporting",
        },
        "Art.26": {
            "test": "supply_chain",
            "description": "ICT third-party risk management",
        },
        "Art.25": {
            "test": "chaos_simulation",
            "description": "Testing of ICT tools and systems",
        },
    },
    "ISO27001": {
        "A.17.1": {
            "test": "dr_simulation",
            "description": "Information security continuity — business continuity planning",
        },
        "A.17.2": {
            "test": "availability_model",
            "description": "Redundancies — availability of processing facilities",
        },
        "A.12.1": {
            "test": "chaos_simulation",
            "description": "Operational procedures and responsibilities",
        },
        "A.12.6": {
            "test": "security_analysis",
            "description": "Technical vulnerability management",
        },
    },
    "PCI-DSS": {
        "Req.10": {
            "test": "security_analysis",
            "description": "Log and monitor access to system components",
        },
        "Req.11": {
            "test": "chaos_simulation",
            "description": "Test security of systems and networks regularly",
        },
        "Req.12": {
            "test": "dr_simulation",
            "description": "Support information security with policies and programs",
        },
    },
}


# ---------------------------------------------------------------------------
# Test evaluators
# ---------------------------------------------------------------------------

def _evaluate_chaos_simulation(
    graph: InfraGraph,
    simulation_report: object | None,
) -> tuple[str, str]:
    """Evaluate chaos simulation evidence.

    Returns (result, detail).
    """
    if simulation_report is None:
        return "Fail", "No chaos simulation report provided"

    critical = len(getattr(simulation_report, "critical_findings", []))
    warnings = len(getattr(simulation_report, "warnings", []))
    passed = len(getattr(simulation_report, "passed", []))
    total = len(getattr(simulation_report, "results", []))
    score = getattr(simulation_report, "resilience_score", 0.0)

    detail = (
        f"Chaos simulation executed with {total} scenarios. "
        f"Resilience score: {score:.1f}/100. "
        f"Results: {passed} passed, {warnings} warnings, {critical} critical."
    )

    if critical > 0:
        return "Fail", detail
    if warnings > 0:
        return "Partial", detail
    return "Pass", detail


def _evaluate_availability_model(
    graph: InfraGraph,
    simulation_report: object | None,
) -> tuple[str, str]:
    """Evaluate availability model evidence."""
    score_data = graph.resilience_score_v2()
    score = score_data["score"]
    redundancy = score_data["breakdown"]["redundancy"]
    headroom = score_data["breakdown"]["capacity_headroom"]

    detail = (
        f"Availability assessment: resilience score {score:.1f}/100. "
        f"Redundancy: {redundancy:.1f}/20. Capacity headroom: {headroom:.1f}/20."
    )

    if score >= 80:
        return "Pass", detail
    if score >= 50:
        return "Partial", detail
    return "Fail", detail


def _evaluate_security_analysis(
    graph: InfraGraph,
    security_report: object | None,
) -> tuple[str, str]:
    """Evaluate security controls evidence."""
    if security_report is not None:
        # Use security report if available
        findings = getattr(security_report, "findings", [])
        critical = sum(1 for f in findings if getattr(f, "severity", "") == "critical")
        detail = (
            f"Security analysis completed. "
            f"{len(findings)} finding(s), {critical} critical."
        )
        if critical > 0:
            return "Fail", detail
        if findings:
            return "Partial", detail
        return "Pass", detail

    # Fall back to analysing the graph's security profiles
    issues: list[str] = []
    for comp_id, comp in graph.components.items():
        sec = comp.security
        if not sec.encryption_at_rest:
            issues.append(f"{comp_id}: no encryption at rest")
        if not sec.encryption_in_transit:
            issues.append(f"{comp_id}: no encryption in transit")
        if not sec.log_enabled:
            issues.append(f"{comp_id}: logging disabled")

    if not issues:
        return "Pass", "All components have encryption and logging enabled."
    detail = f"Security gaps found: {'; '.join(issues[:5])}"
    if len(issues) > 5:
        detail += f" (and {len(issues) - 5} more)"
    if any("encryption" in i for i in issues):
        return "Fail", detail
    return "Partial", detail


def _evaluate_dr_simulation(
    graph: InfraGraph,
    dr_results: object | None,
) -> tuple[str, str]:
    """Evaluate disaster recovery evidence."""
    if dr_results is not None:
        scenarios = dr_results if isinstance(dr_results, list) else [dr_results]
        total = len(scenarios)
        passed_count = sum(
            1 for s in scenarios
            if getattr(s, "rpo_met", True) and getattr(s, "rto_met", True)
        )
        detail = f"DR simulation: {passed_count}/{total} scenarios met RPO/RTO targets."
        if passed_count == total:
            return "Pass", detail
        if passed_count > 0:
            return "Partial", detail
        return "Fail", detail

    # Fallback: check region configuration
    multi_region = sum(
        1 for c in graph.components.values()
        if c.region.dr_target_region
    )
    total = len(graph.components)
    detail = f"{multi_region}/{total} components have DR region configured."
    if multi_region == 0:
        return "Fail", detail
    if multi_region < total:
        return "Partial", detail
    return "Pass", detail


def _evaluate_resilience_score(
    graph: InfraGraph,
    simulation_report: object | None,
) -> tuple[str, str]:
    """Evaluate overall resilience score for ICT risk management."""
    score = graph.resilience_score()
    detail = f"Infrastructure resilience score: {score:.1f}/100."
    if score >= 80:
        return "Pass", detail
    if score >= 50:
        return "Partial", detail
    return "Fail", detail


def _evaluate_incident_reporting(
    graph: InfraGraph,
    simulation_report: object | None,
) -> tuple[str, str]:
    """Evaluate incident reporting capabilities."""
    comps_with_logging = sum(
        1 for c in graph.components.values() if c.security.log_enabled
    )
    comps_with_monitoring = sum(
        1 for c in graph.components.values() if c.security.ids_monitored
    )
    total = len(graph.components)

    detail = (
        f"Logging enabled: {comps_with_logging}/{total}. "
        f"IDS monitoring: {comps_with_monitoring}/{total}."
    )

    if comps_with_logging == total and comps_with_monitoring == total:
        return "Pass", detail
    if comps_with_logging > 0:
        return "Partial", detail
    return "Fail", detail


def _evaluate_supply_chain(
    graph: InfraGraph,
    simulation_report: object | None,
) -> tuple[str, str]:
    """Evaluate third-party / supply chain risk management."""
    from faultray.model.components import ComponentType

    external = [
        c for c in graph.components.values()
        if c.type == ComponentType.EXTERNAL_API
    ]

    if not external:
        return "Pass", "No external API dependencies detected."

    with_failover = sum(1 for c in external if c.failover.enabled)
    detail = (
        f"{len(external)} external dependency(ies). "
        f"{with_failover} have failover configured."
    )
    if with_failover == len(external):
        return "Pass", detail
    if with_failover > 0:
        return "Partial", detail
    return "Fail", detail


_TEST_EVALUATORS = {
    "chaos_simulation": _evaluate_chaos_simulation,
    "availability_model": _evaluate_availability_model,
    "security_analysis": _evaluate_security_analysis,
    "dr_simulation": _evaluate_dr_simulation,
    "resilience_score": _evaluate_resilience_score,
    "incident_reporting": _evaluate_incident_reporting,
    "supply_chain": _evaluate_supply_chain,
}


# ---------------------------------------------------------------------------
# EvidenceGenerator
# ---------------------------------------------------------------------------

class EvidenceGenerator:
    """Generate audit-ready compliance evidence from simulation results.

    Args:
        graph: The infrastructure graph under test.
    """

    # Expose control mappings as class attribute for testing / extension
    CONTROL_MAPPINGS = CONTROL_MAPPINGS

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    @staticmethod
    def supported_frameworks() -> list[str]:
        """Return the list of supported compliance frameworks."""
        return list(CONTROL_MAPPINGS.keys())

    def generate(
        self,
        framework: str,
        simulation_report: object | None = None,
        security_report: object | None = None,
        dr_results: object | None = None,
    ) -> EvidencePackage:
        """Generate an evidence package for *framework*.

        Args:
            framework: One of ``SOC2``, ``DORA``, ``ISO27001``, ``PCI-DSS``.
            simulation_report: A :class:`SimulationReport` (optional).
            security_report: A security analysis report (optional).
            dr_results: DR simulation results (optional).

        Returns:
            An :class:`EvidencePackage` containing all evaluated controls.

        Raises:
            ValueError: If *framework* is not supported.
        """
        framework_upper = framework.upper().replace("-", "").replace("_", "")
        # Normalise common aliases
        alias_map = {
            "PCIDSS": "PCI-DSS",
            "SOC2": "SOC2",
            "DORA": "DORA",
            "ISO27001": "ISO27001",
        }
        normalised = alias_map.get(framework_upper, framework)

        controls = CONTROL_MAPPINGS.get(normalised)
        if controls is None:
            raise ValueError(
                f"Unsupported framework '{framework}'. "
                f"Supported: {list(CONTROL_MAPPINGS.keys())}"
            )

        test_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        items: list[EvidenceItem] = []

        for control_id, mapping in controls.items():
            test_type = mapping["test"]
            description = mapping["description"]

            evaluator = _TEST_EVALUATORS.get(test_type)
            if evaluator is None:
                result = "Fail"
                detail = f"No evaluator for test type '{test_type}'"
            else:
                # Select the correct report to pass
                if test_type in ("chaos_simulation", "resilience_score",
                                 "incident_reporting", "supply_chain"):
                    result, detail = evaluator(self.graph, simulation_report)
                elif test_type == "security_analysis":
                    result, detail = evaluator(self.graph, security_report)
                elif test_type in ("dr_simulation",):
                    result, detail = evaluator(self.graph, dr_results)
                elif test_type == "availability_model":
                    result, detail = evaluator(self.graph, simulation_report)
                else:
                    result, detail = evaluator(self.graph, simulation_report)

            items.append(EvidenceItem(
                framework=normalised,
                control_id=control_id,
                control_description=description,
                test_performed=test_type,
                test_date=test_date,
                result=result,
                evidence_detail=detail,
                simulation_id=None,
            ))

        passed = sum(1 for i in items if i.result == "Pass")
        failed = sum(1 for i in items if i.result == "Fail")
        total = len(items)
        coverage = (passed / total * 100.0) if total else 0.0

        return EvidencePackage(
            framework=normalised,
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_controls_tested=total,
            passed=passed,
            failed=failed,
            coverage_percent=round(coverage, 1),
            items=items,
        )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_csv(self, package: EvidencePackage, output_path: Path) -> None:
        """Export an evidence package to CSV.

        Args:
            package: The evidence package to export.
            output_path: Destination file path.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "Framework",
                "Control ID",
                "Control Description",
                "Test Performed",
                "Test Date",
                "Result",
                "Evidence Detail",
                "Simulation ID",
            ])
            for item in package.items:
                writer.writerow([
                    item.framework,
                    item.control_id,
                    item.control_description,
                    item.test_performed,
                    item.test_date,
                    item.result,
                    item.evidence_detail,
                    item.simulation_id or "",
                ])

    def export_json(self, package: EvidencePackage) -> dict:
        """Export an evidence package to a JSON-serialisable dict."""
        return {
            "framework": package.framework,
            "generated_at": package.generated_at,
            "total_controls_tested": package.total_controls_tested,
            "passed": package.passed,
            "failed": package.failed,
            "coverage_percent": package.coverage_percent,
            "items": [
                {
                    "framework": i.framework,
                    "control_id": i.control_id,
                    "control_description": i.control_description,
                    "test_performed": i.test_performed,
                    "test_date": i.test_date,
                    "result": i.result,
                    "evidence_detail": i.evidence_detail,
                    "simulation_id": i.simulation_id,
                }
                for i in package.items
            ],
        }
