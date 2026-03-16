"""Export FaultRay findings in SARIF format for GitHub Security integration.

SARIF (Static Analysis Results Interchange Format) is a standard JSON format
for static analysis results. When uploaded to GitHub via the CodeQL action,
findings appear in the Security tab of the repository.

Reference: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
"""

from __future__ import annotations

from typing import Any

from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationReport


# SARIF severity levels mapped from risk scores
_SEVERITY_LEVELS = {
    "critical": {"level": "error", "score": 9.0},
    "high": {"level": "error", "score": 7.0},
    "medium": {"level": "warning", "score": 4.0},
    "low": {"level": "note", "score": 0.0},
}

# Remediation suggestions by finding type keyword
_REMEDIATION_MAP = {
    "single point of failure": (
        "Add redundancy by increasing replicas to at least 2. "
        "Enable failover configuration for automatic recovery."
    ),
    "spof": (
        "Add redundancy by increasing replicas to at least 2. "
        "Enable failover configuration for automatic recovery."
    ),
    "cascade": (
        "Add circuit breakers between dependent services. "
        "Configure retry strategies with exponential backoff."
    ),
    "traffic": (
        "Enable autoscaling with appropriate thresholds. "
        "Add rate limiting at the load balancer level."
    ),
    "overload": (
        "Increase capacity limits or enable horizontal autoscaling. "
        "Review connection pool sizes and timeout values."
    ),
    "database": (
        "Add read replicas for database redundancy. "
        "Configure automated failover with minimal promotion time."
    ),
    "cache": (
        "Deploy cache replicas with cache warming enabled. "
        "Configure singleflight to prevent thundering herd."
    ),
}

# SARIF tool information
_TOOL_NAME = "FaultRay"
_TOOL_VERSION = "2.1.0"
_TOOL_URI = "https://github.com/faultray/faultray"
_SARIF_SCHEMA = "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json"
_SARIF_VERSION = "2.1.0"


def _risk_to_sarif_level(risk_score: float) -> str:
    """Convert a risk score (0-10) to a SARIF level string."""
    if risk_score >= 7.0:
        return "error"
    if risk_score >= 4.0:
        return "warning"
    return "note"


def _risk_to_severity(risk_score: float) -> str:
    """Convert a risk score to a human-readable severity label."""
    if risk_score >= 9.0:
        return "critical"
    if risk_score >= 7.0:
        return "high"
    if risk_score >= 4.0:
        return "medium"
    return "low"


def _get_remediation(scenario_name: str) -> str:
    """Look up remediation advice based on scenario name keywords."""
    name_lower = scenario_name.lower()
    for keyword, remediation in _REMEDIATION_MAP.items():
        if keyword in name_lower:
            return remediation
    return (
        "Review the infrastructure configuration for this component. "
        "Consider adding redundancy, circuit breakers, or autoscaling."
    )


def _make_rule(rule_id: str, scenario_name: str, risk_score: float) -> dict:
    """Create a SARIF rule definition."""
    severity = _risk_to_severity(risk_score)
    return {
        "id": rule_id,
        "name": scenario_name.replace(" ", ""),
        "shortDescription": {
            "text": scenario_name,
        },
        "fullDescription": {
            "text": f"FaultRay detected: {scenario_name} (risk score: {risk_score:.1f}/10)",
        },
        "defaultConfiguration": {
            "level": _risk_to_sarif_level(risk_score),
        },
        "properties": {
            "tags": ["resilience", "infrastructure", severity],
            "precision": "high",
            "problem.severity": severity,
        },
        "helpUri": _TOOL_URI,
        "help": {
            "text": _get_remediation(scenario_name),
            "markdown": f"**Remediation:** {_get_remediation(scenario_name)}",
        },
    }


def _make_result(
    rule_id: str,
    scenario_name: str,
    risk_score: float,
    affected_components: list[str],
    infrastructure_file: str = "infrastructure.yaml",
) -> dict:
    """Create a SARIF result entry."""
    message_text = (
        f"{scenario_name}: risk score {risk_score:.1f}/10. "
        f"Affected components: {', '.join(affected_components) if affected_components else 'system-wide'}. "
        f"{_get_remediation(scenario_name)}"
    )

    locations = []
    if infrastructure_file:
        locations.append({
            "physicalLocation": {
                "artifactLocation": {
                    "uri": infrastructure_file,
                    "uriBaseId": "%SRCROOT%",
                },
                "region": {
                    "startLine": 1,
                    "startColumn": 1,
                },
            },
            "message": {
                "text": f"Infrastructure definition affecting: {', '.join(affected_components) or 'system'}",
            },
        })

    return {
        "ruleId": rule_id,
        "ruleIndex": 0,  # Will be updated during export
        "level": _risk_to_sarif_level(risk_score),
        "message": {
            "text": message_text,
        },
        "locations": locations,
        "properties": {
            "risk_score": risk_score,
            "affected_components": affected_components,
        },
    }


def export_sarif(
    sim_report: SimulationReport,
    graph: InfraGraph,
    infrastructure_file: str = "infrastructure.yaml",
) -> dict:
    """Generate a SARIF JSON document from simulation results.

    Parameters
    ----------
    sim_report:
        The simulation report containing scenario results.
    graph:
        The infrastructure graph that was simulated.
    infrastructure_file:
        Path to the infrastructure definition file (for location references).

    Returns
    -------
    dict
        A SARIF 2.1.0 compliant JSON structure.
    """
    rules: list[dict] = []
    results: list[dict] = []
    rule_index_map: dict[str, int] = {}

    # Process all findings (critical and warning)
    findings = sim_report.critical_findings + sim_report.warnings
    for idx, scenario_result in enumerate(findings):
        scenario = scenario_result.scenario
        rule_id = f"FZ{idx + 1:04d}"

        # Determine affected components from cascade effects
        affected = []
        if scenario_result.cascade and scenario_result.cascade.effects:
            affected = list({
                e.component_id
                for e in scenario_result.cascade.effects
                if hasattr(e, "component_id") and e.component_id
            })
        if not affected and scenario.faults:
            affected = [f.target_component_id for f in scenario.faults]

        # Create rule
        rule = _make_rule(rule_id, scenario.name, scenario_result.risk_score)
        rule_index = len(rules)
        rules.append(rule)
        rule_index_map[rule_id] = rule_index

        # Create result
        result = _make_result(
            rule_id=rule_id,
            scenario_name=scenario.name,
            risk_score=scenario_result.risk_score,
            affected_components=affected,
            infrastructure_file=infrastructure_file,
        )
        result["ruleIndex"] = rule_index
        results.append(result)

    # Build SARIF document
    sarif: dict[str, Any] = {
        "$schema": _SARIF_SCHEMA,
        "version": _SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": _TOOL_NAME,
                        "version": _TOOL_VERSION,
                        "informationUri": _TOOL_URI,
                        "rules": rules,
                    },
                },
                "results": results,
                "invocations": [
                    {
                        "executionSuccessful": True,
                        "toolExecutionNotifications": [],
                    },
                ],
                "properties": {
                    "resilience_score": sim_report.resilience_score,
                    "total_scenarios": len(sim_report.results),
                    "critical_count": len(sim_report.critical_findings),
                    "warning_count": len(sim_report.warnings),
                    "passed_count": len(sim_report.passed),
                },
            },
        ],
    }

    return sarif


class SARIFExporter:
    """Convenience class for SARIF export operations."""

    @staticmethod
    def from_simulation(
        sim_report: SimulationReport,
        graph: InfraGraph,
        infrastructure_file: str = "infrastructure.yaml",
    ) -> dict:
        """Export simulation results as SARIF.

        Parameters
        ----------
        sim_report:
            The simulation report.
        graph:
            The infrastructure graph.
        infrastructure_file:
            Path to the infrastructure definition file.

        Returns
        -------
        dict
            SARIF 2.1.0 compliant JSON structure.
        """
        return export_sarif(sim_report, graph, infrastructure_file)

    @staticmethod
    def from_json_results(results: dict, infrastructure_file: str = "infrastructure.yaml") -> dict:
        """Generate a minimal SARIF document from JSON simulation results.

        This is used in CI/CD pipelines where the full SimulationReport
        object is not available, only the JSON output from `faultray simulate --json`.

        Parameters
        ----------
        results:
            JSON dict from `faultray simulate --json`.
        infrastructure_file:
            Path to the infrastructure definition file.

        Returns
        -------
        dict
            SARIF 2.1.0 compliant JSON structure.
        """
        rules: list[dict] = []
        sarif_results: list[dict] = []

        score = results.get("resilience_score", 0)
        critical_count = results.get("critical", 0)
        warning_count = results.get("warning", 0)
        passed_count = results.get("passed", 0)

        scenarios = results.get("scenarios", [])
        idx = 0
        for scenario in scenarios:
            name = scenario.get("name", "unknown")
            # Only include scenarios that have findings
            severity = scenario.get("severity", "info")
            if severity in ("info",):
                continue

            risk_score = 7.0 if severity == "critical" else 4.0 if severity == "warning" else 1.0
            rule_id = f"FZ{idx + 1:04d}"

            rule = _make_rule(rule_id, name, risk_score)
            rules.append(rule)

            result_entry = _make_result(
                rule_id=rule_id,
                scenario_name=name,
                risk_score=risk_score,
                affected_components=[],
                infrastructure_file=infrastructure_file,
            )
            result_entry["ruleIndex"] = idx
            sarif_results.append(result_entry)
            idx += 1

        # If no specific scenarios but we have counts, add summary rules
        if not sarif_results and (critical_count > 0 or warning_count > 0):
            if critical_count > 0:
                rule_id = "FZ0001"
                rules.append(_make_rule(rule_id, "Critical Resilience Findings", 8.0))
                result_entry = _make_result(
                    rule_id=rule_id,
                    scenario_name=f"{critical_count} critical resilience finding(s) detected",
                    risk_score=8.0,
                    affected_components=[],
                    infrastructure_file=infrastructure_file,
                )
                result_entry["ruleIndex"] = 0
                sarif_results.append(result_entry)

            if warning_count > 0:
                rule_id = f"FZ{len(rules) + 1:04d}"
                rules.append(_make_rule(rule_id, "Warning Resilience Findings", 5.0))
                result_entry = _make_result(
                    rule_id=rule_id,
                    scenario_name=f"{warning_count} warning resilience finding(s) detected",
                    risk_score=5.0,
                    affected_components=[],
                    infrastructure_file=infrastructure_file,
                )
                result_entry["ruleIndex"] = len(rules) - 1
                sarif_results.append(result_entry)

        return {
            "$schema": _SARIF_SCHEMA,
            "version": _SARIF_VERSION,
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": _TOOL_NAME,
                            "version": _TOOL_VERSION,
                            "informationUri": _TOOL_URI,
                            "rules": rules,
                        },
                    },
                    "results": sarif_results,
                    "invocations": [
                        {
                            "executionSuccessful": True,
                            "toolExecutionNotifications": [],
                        },
                    ],
                    "properties": {
                        "resilience_score": score,
                        "critical_count": critical_count,
                        "warning_count": warning_count,
                        "passed_count": passed_count,
                    },
                },
            ],
        }
