# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Bidirectional bridge between APM live data and FaultRay simulations.

Responsibilities:
1. Mark simulation-critical components for heavy APM monitoring.
2. Feed real APM metrics into simulation parameters (model calibration).
3. Generate "predicted vs actual" comparison reports.
"""

from __future__ import annotations

import logging
from typing import Any

from faultray.apm.metrics_db import MetricsDB
from faultray.model.components import ResourceMetrics
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


class SimulationAPMLink:
    """Links simulation results with live APM data."""

    def __init__(self, graph: InfraGraph, db: MetricsDB) -> None:
        self.graph = graph
        self.db = db

    # ------------------------------------------------------------------
    # 1. Priority monitoring from simulation results
    # ------------------------------------------------------------------

    def mark_critical_components(
        self, simulation_results: dict[str, Any]
    ) -> list[str]:
        """Identify components the simulation flagged as high-risk and return
        their IDs so the agent can increase monitoring frequency for them.
        """
        critical_ids: list[str] = []

        scenarios = simulation_results.get("scenarios", [])
        for scenario in scenarios:
            severity = scenario.get("severity", "").lower()
            if severity in ("critical", "high"):
                component_id = scenario.get("component_id", "")
                if component_id and component_id not in critical_ids:
                    critical_ids.append(component_id)

        if critical_ids:
            logger.info(
                "Marked %d components for priority monitoring: %s",
                len(critical_ids),
                critical_ids,
            )
        return critical_ids

    # ------------------------------------------------------------------
    # 2. Model calibration from APM data
    # ------------------------------------------------------------------

    def calibrate_model(self, agent_component_map: dict[str, str] | None = None) -> int:
        """Update graph component metrics with real APM data.

        ``agent_component_map`` maps agent_id → component_id.
        If not provided, attempts to match by hostname/label.

        Returns the number of components calibrated.
        """
        mapping = agent_component_map or self._auto_map_agents()
        calibrated = 0

        for agent_id, component_id in mapping.items():
            component = self.graph.get_component(component_id)
            if component is None:
                continue

            latest = self.db.get_latest_metrics(agent_id)
            if not latest:
                continue

            metrics_map = {m["name"]: m["value"] for m in latest}

            # Update ResourceMetrics on the component
            component.metrics = ResourceMetrics(
                cpu_percent=metrics_map.get("cpu_percent", 0.0),
                memory_percent=metrics_map.get("memory_percent", 0.0),
                memory_used_mb=metrics_map.get("memory_used_mb", 0.0),
                disk_percent=metrics_map.get("disk_percent", 0.0),
                disk_used_gb=metrics_map.get("disk_used_gb", 0.0),
                network_connections=int(metrics_map.get("network_connections", 0)),
            )
            calibrated += 1

        if calibrated:
            logger.info("Calibrated %d component(s) with APM data", calibrated)
        return calibrated

    # ------------------------------------------------------------------
    # 3. Predicted vs Actual comparison
    # ------------------------------------------------------------------

    def compare_prediction_vs_actual(
        self,
        simulation_results: dict[str, Any],
        agent_component_map: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Compare simulation predictions with actual APM measurements.

        Returns a list of comparison records for each component where both
        predicted and actual data exist.
        """
        mapping = agent_component_map or self._auto_map_agents()
        # Reverse mapping: component_id → agent_id
        comp_to_agent = {v: k for k, v in mapping.items()}
        comparisons: list[dict[str, Any]] = []

        predicted = simulation_results.get("component_scores", {})
        for component_id, pred_score in predicted.items():
            agent_id = comp_to_agent.get(component_id)
            if not agent_id:
                continue

            latest = self.db.get_latest_metrics(agent_id)
            if not latest:
                continue

            metrics_map = {m["name"]: m["value"] for m in latest}
            actual_cpu = metrics_map.get("cpu_percent", 0.0)
            actual_mem = metrics_map.get("memory_percent", 0.0)

            comparisons.append({
                "component_id": component_id,
                "agent_id": agent_id,
                "predicted_risk_score": pred_score,
                "actual_cpu_percent": actual_cpu,
                "actual_memory_percent": actual_mem,
                "cpu_stress_level": "high" if actual_cpu > 80 else "normal",
                "memory_stress_level": "high" if actual_mem > 80 else "normal",
            })

        return comparisons

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _auto_map_agents(self) -> dict[str, str]:
        """Attempt to auto-map agents to graph components by hostname/label."""
        mapping: dict[str, str] = {}
        agents = self.db.list_agents()

        for agent in agents:
            agent_id = agent["agent_id"]
            hostname = agent.get("hostname", "")
            labels = agent.get("labels", {})

            # Try matching by component_id label
            if "component_id" in labels:
                mapping[agent_id] = labels["component_id"]
                continue

            # Try matching by hostname
            for comp_id, comp in self.graph.components.items():
                if hostname and hostname.lower() in comp.name.lower():
                    mapping[agent_id] = comp_id
                    break

        return mapping
