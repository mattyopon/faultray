"""Incident Correlation — map real incidents to FaultZero scenarios.

Validates simulation accuracy by comparing real-world incidents against
predicted failure scenarios.

Usage:
    infrasim correlate my-model.json --incidents incidents.csv
    infrasim correlate my-model.json --pagerduty-key <key> --days 90
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from infrasim.model.graph import InfraGraph
from infrasim.simulator.engine import SimulationEngine, SimulationReport

logger = logging.getLogger(__name__)


@dataclass
class IncidentRecord:
    """A single incident record."""

    id: str
    title: str
    severity: str  # "critical", "major", "minor"
    affected_components: list[str]
    root_cause: str
    duration_minutes: float
    date: str
    source: str  # "pagerduty", "opsgenie", "manual", "csv"


@dataclass
class CorrelationResult:
    """Correlation result for a single incident."""

    incident: IncidentRecord
    matching_scenarios: list[str]  # scenario names that predicted this
    predicted: bool  # was this incident type covered by simulation?
    severity_match: bool  # did simulation predict correct severity?
    coverage_gap: str | None  # if not predicted, what was missing?


@dataclass
class CorrelationReport:
    """Full correlation report."""

    total_incidents: int
    predicted_count: int
    prediction_rate: float  # predicted / total (0.0 - 1.0)
    unpredicted_incidents: list[CorrelationResult]
    predicted_incidents: list[CorrelationResult]
    recommendations: list[str]  # new scenarios to add
    severity_accuracy: float  # fraction with matching severity


class IncidentCorrelator:
    """Correlates real incidents with FaultZero simulation scenarios.

    Given an InfraGraph and a simulation report, this class can determine
    which real-world incidents were predicted by the simulation and which
    represent coverage gaps.
    """

    # Mapping of common root cause keywords to scenario/fault patterns
    ROOT_CAUSE_PATTERNS: dict[str, list[str]] = {
        "component_down": [
            "down", "crash", "oom", "killed", "unreachable", "offline",
            "terminated", "failure", "died", "hung",
        ],
        "latency_spike": [
            "latency", "slow", "timeout", "degraded", "response time",
            "high latency", "delayed",
        ],
        "cpu_saturation": [
            "cpu", "cpu spike", "high cpu", "cpu saturation", "compute",
        ],
        "memory_exhaustion": [
            "memory", "oom", "out of memory", "memory leak", "heap",
        ],
        "disk_full": [
            "disk", "disk full", "storage", "no space", "filesystem",
        ],
        "connection_pool_exhaustion": [
            "connection pool", "pool exhaustion", "max connections",
            "too many connections", "connection limit",
        ],
        "network_partition": [
            "network", "partition", "split brain", "connectivity",
            "dns", "routing",
        ],
        "traffic_spike": [
            "traffic", "load", "spike", "burst", "ddos", "overload",
            "capacity", "scaling",
        ],
    }

    # Severity mapping for comparison
    SEVERITY_LEVELS: dict[str, int] = {
        "critical": 3,
        "major": 2,
        "minor": 1,
        "low": 0,
    }

    def __init__(
        self,
        graph: InfraGraph,
        simulation_report: SimulationReport | None = None,
    ) -> None:
        self.graph = graph
        self.simulation_report = simulation_report

        # If no report provided, run a simulation
        if self.simulation_report is None:
            engine = SimulationEngine(graph)
            self.simulation_report = engine.run_all_defaults(
                include_feed=False, include_plugins=False,
            )

    def correlate(self, incidents: list[IncidentRecord]) -> CorrelationReport:
        """Correlate incidents against simulation scenarios.

        For each incident, check if any simulation scenario:
        1. Targets the same or overlapping components
        2. Simulates the same fault type (inferred from root cause)
        3. Has a matching severity level
        """
        results: list[CorrelationResult] = []
        predicted_count = 0
        severity_match_count = 0

        for incident in incidents:
            result = self._correlate_single(incident)
            results.append(result)
            if result.predicted:
                predicted_count += 1
            if result.severity_match:
                severity_match_count += 1

        total = len(incidents) if incidents else 1  # avoid division by zero
        prediction_rate = predicted_count / total if incidents else 0.0
        severity_accuracy = severity_match_count / total if incidents else 0.0

        unpredicted = [r for r in results if not r.predicted]
        predicted = [r for r in results if r.predicted]

        recommendations = self._generate_recommendations(unpredicted)

        return CorrelationReport(
            total_incidents=len(incidents),
            predicted_count=predicted_count,
            prediction_rate=round(prediction_rate, 3),
            unpredicted_incidents=unpredicted,
            predicted_incidents=predicted,
            recommendations=recommendations,
            severity_accuracy=round(severity_accuracy, 3),
        )

    def _correlate_single(self, incident: IncidentRecord) -> CorrelationResult:
        """Correlate a single incident against simulation results."""
        matching_scenarios: list[str] = []
        best_severity_match = False

        # Infer fault types from root cause description
        inferred_faults = self._infer_fault_types(incident.root_cause)

        # Get affected component IDs (normalize)
        affected_ids = set(
            c.lower().strip() for c in incident.affected_components
        )
        graph_ids = set(
            cid.lower() for cid in self.graph.components.keys()
        )

        # Find matching simulation scenarios
        for result in self.simulation_report.results:
            scenario = result.scenario
            scenario_targets = set()
            scenario_fault_types = set()

            for fault in scenario.faults:
                scenario_targets.add(fault.target_component_id.lower())
                scenario_fault_types.add(fault.fault_type.value)

            # Check component overlap
            component_overlap = bool(
                affected_ids & scenario_targets
                or affected_ids & graph_ids  # incident refers to graph components
            )

            # Check fault type match
            fault_match = bool(inferred_faults & scenario_fault_types)

            if component_overlap and fault_match:
                matching_scenarios.append(scenario.name)

                # Check severity match
                scenario_severity = self._risk_to_severity(result.risk_score)
                incident_severity_level = self.SEVERITY_LEVELS.get(
                    incident.severity.lower(), 0
                )
                scenario_severity_level = self.SEVERITY_LEVELS.get(
                    scenario_severity, 0
                )
                if abs(incident_severity_level - scenario_severity_level) <= 1:
                    best_severity_match = True

            elif fault_match and not affected_ids:
                # Incident doesn't specify components but fault type matches
                matching_scenarios.append(scenario.name)

        predicted = len(matching_scenarios) > 0
        coverage_gap = None

        if not predicted:
            coverage_gap = self._describe_coverage_gap(
                incident, inferred_faults, affected_ids
            )

        return CorrelationResult(
            incident=incident,
            matching_scenarios=matching_scenarios,
            predicted=predicted,
            severity_match=best_severity_match,
            coverage_gap=coverage_gap,
        )

    def _infer_fault_types(self, root_cause: str) -> set[str]:
        """Infer fault types from a root cause description."""
        root_cause_lower = root_cause.lower()
        inferred = set()

        for fault_type, keywords in self.ROOT_CAUSE_PATTERNS.items():
            for keyword in keywords:
                if keyword in root_cause_lower:
                    inferred.add(fault_type)
                    break

        # Default to component_down if nothing matched
        if not inferred:
            inferred.add("component_down")

        return inferred

    def _risk_to_severity(self, risk_score: float) -> str:
        """Convert a risk score (0-10) to a severity level."""
        if risk_score >= 7.0:
            return "critical"
        elif risk_score >= 4.0:
            return "major"
        elif risk_score >= 1.0:
            return "minor"
        return "low"

    def _describe_coverage_gap(
        self,
        incident: IncidentRecord,
        inferred_faults: set[str],
        affected_ids: set[str],
    ) -> str:
        """Describe why an incident was not predicted."""
        parts = []

        # Check if affected components exist in the graph
        graph_ids_lower = set(cid.lower() for cid in self.graph.components.keys())
        missing_components = affected_ids - graph_ids_lower
        if missing_components:
            parts.append(
                f"Components not in model: {', '.join(sorted(missing_components))}"
            )

        # Check if fault types are covered
        scenario_fault_types = set()
        for result in self.simulation_report.results:
            for fault in result.scenario.faults:
                scenario_fault_types.add(fault.fault_type.value)

        uncovered_faults = inferred_faults - scenario_fault_types
        if uncovered_faults:
            parts.append(
                f"Fault types not simulated: {', '.join(sorted(uncovered_faults))}"
            )

        if not parts:
            parts.append(
                "Fault type and components exist but no matching scenario combination"
            )

        return "; ".join(parts)

    def _generate_recommendations(
        self, unpredicted: list[CorrelationResult]
    ) -> list[str]:
        """Generate recommendations for improving simulation coverage."""
        recommendations: list[str] = []
        seen_gaps: set[str] = set()

        for result in unpredicted:
            incident = result.incident

            # Recommend adding missing components
            graph_ids_lower = set(
                cid.lower() for cid in self.graph.components.keys()
            )
            for comp in incident.affected_components:
                if comp.lower() not in graph_ids_lower:
                    rec = f"Add component '{comp}' to the infrastructure model"
                    if rec not in seen_gaps:
                        seen_gaps.add(rec)
                        recommendations.append(rec)

            # Recommend fault scenarios based on root cause
            inferred = self._infer_fault_types(incident.root_cause)
            for fault_type in inferred:
                rec = (
                    f"Add {fault_type} scenario for "
                    f"{', '.join(incident.affected_components) or 'affected components'}"
                )
                if rec not in seen_gaps:
                    seen_gaps.add(rec)
                    recommendations.append(rec)

        # General recommendation if many unpredicted
        if len(unpredicted) > 3:
            recommendations.append(
                "Consider running FaultZero with feed-generated scenarios "
                "(--include-feeds) for broader coverage"
            )

        return recommendations

    def import_from_pagerduty(
        self, api_key: str, days: int = 90
    ) -> list[IncidentRecord]:
        """Import incidents from PagerDuty API (read-only).

        Requires the PagerDuty REST API v2 token with read access.
        """
        try:
            import httpx
        except ImportError:
            raise ImportError(
                "httpx is required for PagerDuty integration. "
                "Install with: pip install httpx"
            )

        from datetime import datetime, timedelta, timezone

        since = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        until = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        headers = {
            "Authorization": f"Token token={api_key}",
            "Content-Type": "application/json",
        }

        incidents: list[IncidentRecord] = []
        offset = 0
        limit = 100

        with httpx.Client(timeout=30.0) as client:
            while True:
                resp = client.get(
                    "https://api.pagerduty.com/incidents",
                    headers=headers,
                    params={
                        "since": since,
                        "until": until,
                        "limit": limit,
                        "offset": offset,
                        "sort_by": "created_at:desc",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                for inc in data.get("incidents", []):
                    urgency = inc.get("urgency", "low")
                    severity = {
                        "high": "critical",
                        "low": "minor",
                    }.get(urgency, "major")

                    # Extract affected service names
                    service = inc.get("service", {})
                    affected = [service.get("summary", "")] if service else []

                    incidents.append(IncidentRecord(
                        id=inc.get("id", ""),
                        title=inc.get("title", ""),
                        severity=severity,
                        affected_components=affected,
                        root_cause=inc.get("title", ""),  # PagerDuty doesn't have a root cause field
                        duration_minutes=_pd_duration_minutes(inc),
                        date=inc.get("created_at", ""),
                        source="pagerduty",
                    ))

                if not data.get("more", False):
                    break
                offset += limit

        return incidents

    def import_from_csv(self, path: Path) -> list[IncidentRecord]:
        """Import incidents from a CSV file.

        Expected CSV columns:
            id, title, severity, affected_components, root_cause,
            duration_minutes, date

        affected_components should be semicolon-separated.
        """
        incidents: list[IncidentRecord] = []
        content = path.read_text(encoding="utf-8")

        reader = csv.DictReader(content.splitlines())
        for row in reader:
            affected_raw = row.get("affected_components", "")
            affected = [
                c.strip() for c in affected_raw.split(";")
                if c.strip()
            ]

            try:
                duration = float(row.get("duration_minutes", 0))
            except (ValueError, TypeError):
                duration = 0.0

            incidents.append(IncidentRecord(
                id=row.get("id", ""),
                title=row.get("title", ""),
                severity=row.get("severity", "minor").lower(),
                affected_components=affected,
                root_cause=row.get("root_cause", ""),
                duration_minutes=duration,
                date=row.get("date", ""),
                source="csv",
            ))

        return incidents


def _pd_duration_minutes(incident: dict) -> float:
    """Calculate PagerDuty incident duration in minutes."""
    from datetime import datetime

    created = incident.get("created_at", "")
    resolved = incident.get("last_status_change_at", "")

    if not created or not resolved:
        return 0.0

    try:
        # Parse ISO format
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        created_dt = datetime.strptime(created[:19] + "Z", fmt)
        resolved_dt = datetime.strptime(resolved[:19] + "Z", fmt)
        delta = resolved_dt - created_dt
        return max(0.0, delta.total_seconds() / 60.0)
    except (ValueError, TypeError):
        return 0.0
