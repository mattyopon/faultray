# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Dynatrace Integration -- topology-aware resilience simulation.

Import Smartscape topology -> simulate -> export predictions for Davis AI.

Dynatrace's Smartscape provides a real-time topology map of all monitored
entities and their relationships.  This integration:

1. Pulls the Smartscape topology via Environment API v2
2. Converts Dynatrace entities to FaultRay InfraGraph components
3. Pulls entity metrics for calibration
4. Runs FaultRay simulation and exports results in Davis AI-compatible format
5. Optionally pushes failure predictions as Dynatrace Problems

Environment variables:
    DYNATRACE_ENVIRONMENT_URL  -- Dynatrace SaaS/Managed environment URL
    DYNATRACE_API_TOKEN        -- Dynatrace API token with read topology/metrics scope

When the API token is not set, all API calls return mock data.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DynatraceEntity:
    """Represents a Dynatrace Smartscape entity."""

    entity_id: str
    entity_type: str  # HOST, SERVICE, PROCESS_GROUP, APPLICATION
    display_name: str
    properties: dict = field(default_factory=dict)
    relationships: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

_MOCK_TOPOLOGY: dict = {
    "entities": [
        {
            "entityId": "HOST-ABC123",
            "type": "HOST",
            "displayName": "web-server-1",
            "properties": {"osType": "LINUX", "cpuCores": 4},
            "fromRelationships": {"isNetworkClientOfHost": ["HOST-DEF456"]},
            "toRelationships": {"runsOn": []},
        },
        {
            "entityId": "HOST-DEF456",
            "type": "HOST",
            "displayName": "db-server-1",
            "properties": {"osType": "LINUX", "cpuCores": 8},
            "fromRelationships": {},
            "toRelationships": {"isNetworkClientOfHost": ["HOST-ABC123"]},
        },
        {
            "entityId": "SERVICE-GHI789",
            "type": "SERVICE",
            "displayName": "api-gateway",
            "properties": {"serviceType": "WebService"},
            "fromRelationships": {"calls": ["SERVICE-JKL012"]},
            "toRelationships": {},
        },
        {
            "entityId": "SERVICE-JKL012",
            "type": "SERVICE",
            "displayName": "user-service",
            "properties": {"serviceType": "WebService"},
            "fromRelationships": {},
            "toRelationships": {"calls": ["SERVICE-GHI789"]},
        },
    ]
}

_MOCK_METRICS: dict = {
    "HOST-ABC123": {"cpu.usage": 42.5, "memory.usage": 58.0, "disk.usage": 35.0},
    "HOST-DEF456": {"cpu.usage": 65.0, "memory.usage": 72.0, "disk.usage": 60.0},
}


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class DynatraceIntegration:
    """Topology-aware resilience simulation with Dynatrace Smartscape.

    Converts Dynatrace's auto-discovered topology into a FaultRay InfraGraph,
    runs predictive simulation, and exports results compatible with Davis AI.

    Example::

        graph = InfraGraph()
        dt = DynatraceIntegration(
            environment_url="https://abc123.live.dynatrace.com",
            api_token=os.environ.get("DYNATRACE_API_TOKEN"),
            graph=graph,
        )
        topology = dt.pull_topology()
        graph = dt.convert_smartscape_to_graph(topology)
        results = dt.simulate_and_export()
    """

    def __init__(
        self,
        environment_url: str | None = None,
        api_token: str | None = None,
        graph: InfraGraph | None = None,
    ) -> None:
        self._env_url = (
            environment_url
            or os.environ.get("DYNATRACE_ENVIRONMENT_URL", "")
        ).rstrip("/")
        self._api_token = api_token or os.environ.get("DYNATRACE_API_TOKEN", "")
        self._graph = graph or InfraGraph()
        self._mock = not self._api_token
        if self._mock:
            logger.info("DynatraceIntegration running in mock mode (no API token).")

    # ------------------------------------------------------------------
    # Pull topology
    # ------------------------------------------------------------------

    def pull_topology(self) -> dict:
        """Pull Smartscape topology from Dynatrace Environment API v2.

        Returns:
            Dict with ``entities`` list containing Smartscape entity data.
        """
        if self._mock:
            logger.debug("Returning mock Dynatrace topology.")
            return dict(_MOCK_TOPOLOGY)

        entities: list[dict] = []
        entity_types = ["HOST", "SERVICE", "PROCESS_GROUP", "APPLICATION"]

        with httpx.Client(
            base_url=self._env_url,
            timeout=30,
            headers={"Authorization": f"Api-Token {self._api_token}"},
        ) as client:
            for etype in entity_types:
                try:
                    resp = client.get(
                        "/api/v2/entities",
                        params={
                            "entitySelector": f'type("{etype}")',
                            "fields": "+properties,+fromRelationships,+toRelationships",
                            "pageSize": 500,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    entities.extend(data.get("entities", []))
                except Exception as exc:
                    logger.warning(
                        "Dynatrace topology pull failed for %s: %s", etype, exc
                    )

        return {"entities": entities}

    # ------------------------------------------------------------------
    # Convert Smartscape -> InfraGraph
    # ------------------------------------------------------------------

    def convert_smartscape_to_graph(self, topology: dict) -> InfraGraph:
        """Convert Dynatrace Smartscape topology to a FaultRay InfraGraph.

        Args:
            topology: Dict returned by :meth:`pull_topology`.

        Returns:
            Populated :class:`InfraGraph` (also updates the internal graph).
        """
        graph = InfraGraph()
        entities = topology.get("entities", [])

        # Map Dynatrace entity types to FaultRay ComponentType
        type_map = {
            "HOST": ComponentType.APP_SERVER,
            "SERVICE": ComponentType.WEB_SERVER,
            "PROCESS_GROUP": ComponentType.APP_SERVER,
            "APPLICATION": ComponentType.WEB_SERVER,
            "DATABASE": ComponentType.DATABASE,
        }

        entity_ids = set()
        for entity in entities:
            entity_id = entity.get("entityId", "")
            display_name = entity.get("displayName", entity_id)
            etype = entity.get("type", "HOST")

            comp_type = type_map.get(etype, ComponentType.CUSTOM)

            # Check properties for database hints
            props = entity.get("properties", {})
            if props.get("databaseVendor") or "database" in display_name.lower():
                comp_type = ComponentType.DATABASE

            comp = Component(
                id=entity_id,
                name=display_name,
                type=comp_type,
                host=display_name,
            )
            graph.add_component(comp)
            entity_ids.add(entity_id)

        # Build dependency edges from relationships
        for entity in entities:
            entity_id = entity.get("entityId", "")
            from_rels = entity.get("fromRelationships", {})

            for rel_type, targets in from_rels.items():
                if not isinstance(targets, list):
                    continue
                for target_id in targets:
                    if target_id in entity_ids and target_id != entity_id:
                        dep = Dependency(
                            source_id=entity_id,
                            target_id=target_id,
                            dependency_type="requires",
                            protocol="http",
                        )
                        graph.add_dependency(dep)

        self._graph = graph
        return graph

    # ------------------------------------------------------------------
    # Pull metrics
    # ------------------------------------------------------------------

    def pull_metrics(
        self,
        entity_ids: list[str] | None = None,
        metric_keys: list[str] | None = None,
    ) -> dict:
        """Pull metrics from Dynatrace Metrics API v2.

        Args:
            entity_ids: List of entity IDs to query. Defaults to all graph components.
            metric_keys: Metric keys to query. Defaults to CPU, memory, disk.

        Returns:
            Dict keyed by entity_id, each mapping metric_key to value.
        """
        if entity_ids is None:
            entity_ids = list(self._graph.components.keys())
        if metric_keys is None:
            metric_keys = [
                "builtin:host.cpu.usage",
                "builtin:host.mem.usage",
                "builtin:host.disk.used",
            ]

        if self._mock:
            logger.debug("Returning mock Dynatrace metrics.")
            result: dict[str, dict] = {}
            for eid in entity_ids:
                result[eid] = _MOCK_METRICS.get(eid, {
                    "cpu.usage": 50.0,
                    "memory.usage": 60.0,
                    "disk.usage": 40.0,
                })
            return result

        result = {}
        with httpx.Client(
            base_url=self._env_url,
            timeout=30,
            headers={"Authorization": f"Api-Token {self._api_token}"},
        ) as client:
            for metric_key in metric_keys:
                try:
                    entity_selector = ",".join(
                        f'entityId("{eid}")' for eid in entity_ids
                    )
                    resp = client.get(
                        "/api/v2/metrics/query",
                        params={
                            "metricSelector": metric_key,
                            "entitySelector": entity_selector,
                            "resolution": "1h",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for series in data.get("result", [{}])[0].get("data", []):
                        eid = series.get("dimensions", [""])[0]
                        values = series.get("values", [])
                        valid_values = [v for v in values if v is not None]
                        if valid_values:
                            avg = sum(valid_values) / len(valid_values)
                            short_key = metric_key.split(":")[-1] if ":" in metric_key else metric_key
                            result.setdefault(eid, {})[short_key] = avg
                except Exception as exc:
                    logger.warning(
                        "Dynatrace metrics query failed for %s: %s", metric_key, exc
                    )

        return result

    # ------------------------------------------------------------------
    # Simulate and export
    # ------------------------------------------------------------------

    def simulate_and_export(self) -> dict:
        """Run FaultRay simulation and export in Davis AI-compatible format.

        Returns:
            Dict with simulation results structured for Davis AI consumption:
            ``predictions``, ``topology_risks``, ``resilience_score``.
        """
        engine = SimulationEngine(self._graph)
        report = engine.run_all()

        predictions = []
        for result in report.results:
            if result.is_critical or result.is_warning:
                predictions.append({
                    "title": result.scenario.name,
                    "severity": "CRITICAL" if result.is_critical else "WARNING",
                    "risk_score": result.risk_score,
                    "affected_entities": [
                        e.component_id for e in result.cascade.effects
                    ],
                    "description": result.scenario.description,
                    "cascade_trigger": result.cascade.trigger,
                })

        topology_risks = []
        for comp_id, comp in self._graph.components.items():
            dependents = self._graph.get_dependents(comp_id)
            if comp.replicas <= 1 and len(dependents) > 0:
                topology_risks.append({
                    "entity_id": comp_id,
                    "entity_name": comp.name,
                    "risk_type": "SINGLE_POINT_OF_FAILURE",
                    "dependent_count": len(dependents),
                    "recommendation": f"Add redundancy to {comp.name}",
                })

        return {
            "resilience_score": report.resilience_score,
            "total_scenarios": len(report.results),
            "critical_count": len(report.critical_findings),
            "warning_count": len(report.warnings),
            "predictions": predictions,
            "topology_risks": topology_risks,
            "davis_compatible": True,
        }

    # ------------------------------------------------------------------
    # Push problem
    # ------------------------------------------------------------------

    def push_problem(
        self,
        title: str,
        description: str,
        severity: str = "CUSTOM_ALERT",
    ) -> bool:
        """Push a failure prediction as a Dynatrace Custom Problem via API v2.

        Args:
            title: Problem title.
            description: Problem description.
            severity: Dynatrace event severity
                (``CUSTOM_ALERT``, ``ERROR``, ``AVAILABILITY``).

        Returns:
            True if the problem was created (or mock mode).
        """
        if self._mock:
            logger.info(
                "Mock push_problem: title=%s severity=%s", title, severity
            )
            return True

        payload = {
            "eventType": severity,
            "title": title,
            "description": description,
            "source": "FaultRay",
            "properties": {
                "tool": "faultray",
                "type": "prediction",
            },
        }
        try:
            with httpx.Client(
                base_url=self._env_url,
                timeout=15,
                headers={"Authorization": f"Api-Token {self._api_token}"},
            ) as client:
                resp = client.post("/api/v2/events/ingest", json=payload)
                resp.raise_for_status()
                return True
        except Exception as exc:
            logger.warning("Dynatrace push_problem failed: %s", exc)
            return False
