# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Observability Integration Hub -- import metrics from monitoring platforms.

Imports real metrics from Datadog, New Relic, Grafana, or JSON files to
calibrate FaultRay simulation models.  All external API calls are
**read-only** -- this module never writes to monitoring platforms.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


@dataclass
class MetricImportResult:
    """Result of importing metrics from a monitoring platform."""

    source: str  # "datadog", "newrelic", "grafana", "json"
    components_updated: int
    metrics_imported: int
    calibration_applied: bool
    errors: list[str] = field(default_factory=list)
    details: list[dict] = field(default_factory=list)


class ObservabilityHub:
    """Import real metrics from monitoring platforms to calibrate simulations.

    Supported platforms:
    - Datadog (via Metrics Query API v1)
    - New Relic (via NRQL API)
    - Grafana (via Datasource Proxy API)
    - Generic JSON file

    All API interactions are strictly read-only.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Datadog
    # ------------------------------------------------------------------

    def import_from_datadog(
        self,
        api_key: str,
        app_key: str,
        hours: int = 24,
        *,
        _client: object | None = None,
    ) -> MetricImportResult:
        """Import metrics from Datadog API (read-only).

        Queries: system.cpu.user, system.mem.used, system.disk.used

        Args:
            api_key: Datadog API key.
            app_key: Datadog Application key.
            hours: Number of hours of historical data to query.
            _client: Optional pre-built httpx client for testing / DI.

        Returns:
            MetricImportResult with import statistics.
        """
        import time

        import httpx

        client = _client or httpx.Client(
            base_url="https://api.datadoghq.com",
            timeout=30,
            headers={
                "DD-API-KEY": api_key,
                "DD-APPLICATION-KEY": app_key,
            },
        )

        now = int(time.time())
        from_ts = now - (hours * 3600)

        metrics_imported = 0
        components_updated: set[str] = set()
        errors: list[str] = []
        details: list[dict] = []

        metric_queries = [
            ("system.cpu.user", "cpu_percent"),
            ("system.mem.pct_usable", "memory_percent"),
            ("system.disk.in_use", "disk_percent"),
        ]

        try:
            for dd_metric, local_metric in metric_queries:
                try:
                    resp = client.get(
                        "/api/v1/query",
                        params={
                            "from": from_ts,
                            "to": now,
                            "query": f"avg:{dd_metric}{{*}} by {{host}}",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for series in data.get("series", []):
                        host = series.get("scope", "")
                        pointlist = series.get("pointlist", [])
                        if not pointlist:
                            continue

                        # Average over the time range
                        values = [p[1] for p in pointlist if p[1] is not None]
                        if not values:
                            continue
                        avg_value = sum(values) / len(values)

                        # Convert fractional metrics (0-1) to percentage
                        if local_metric in ("memory_percent", "disk_percent"):
                            avg_value = avg_value * 100.0

                        comp = self._find_component_by_host(host)
                        if comp is None:
                            continue

                        self._apply_metric(comp, local_metric, avg_value)
                        metrics_imported += 1
                        components_updated.add(comp.id)
                        details.append({
                            "component_id": comp.id,
                            "metric": local_metric,
                            "value": round(avg_value, 2),
                            "source_metric": dd_metric,
                        })
                except Exception as exc:
                    errors.append(f"Datadog query '{dd_metric}' failed: {exc}")
                    logger.warning("Datadog query failed for %s: %s", dd_metric, exc)
        finally:
            if _client is None and hasattr(client, "close"):
                client.close()

        return MetricImportResult(
            source="datadog",
            components_updated=len(components_updated),
            metrics_imported=metrics_imported,
            calibration_applied=metrics_imported > 0,
            errors=errors,
            details=details,
        )

    # ------------------------------------------------------------------
    # New Relic
    # ------------------------------------------------------------------

    def import_from_newrelic(
        self,
        api_key: str,
        account_id: str,
        hours: int = 24,
        *,
        _client: object | None = None,
    ) -> MetricImportResult:
        """Import from New Relic NRQL API (read-only).

        Uses NRQL queries to fetch CPU, memory, and disk metrics from
        New Relic Infrastructure.

        Args:
            api_key: New Relic User API key.
            account_id: New Relic account ID.
            hours: Number of hours of historical data to query.
            _client: Optional pre-built httpx client for testing / DI.

        Returns:
            MetricImportResult with import statistics.
        """
        import httpx

        client = _client or httpx.Client(
            base_url="https://api.newrelic.com",
            timeout=30,
            headers={
                "Api-Key": api_key,
                "Content-Type": "application/json",
            },
        )

        metrics_imported = 0
        components_updated: set[str] = set()
        errors: list[str] = []
        details: list[dict] = []

        nrql_queries = [
            (
                f"SELECT average(cpuPercent) FROM SystemSample "
                f"FACET hostname SINCE {hours} hours ago",
                "cpu_percent",
            ),
            (
                f"SELECT average(memoryUsedPercent) FROM SystemSample "
                f"FACET hostname SINCE {hours} hours ago",
                "memory_percent",
            ),
            (
                f"SELECT average(diskUsedPercent) FROM SystemSample "
                f"FACET hostname SINCE {hours} hours ago",
                "disk_percent",
            ),
        ]

        try:
            for nrql, local_metric in nrql_queries:
                try:
                    resp = client.get(
                        f"/v2/accounts/{account_id}/query",
                        params={"nrql": nrql},
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for facet in data.get("facets", []):
                        hostname = facet.get("name", "")
                        results = facet.get("results", [])
                        if not results:
                            continue

                        avg_value = results[0].get("average", 0.0)
                        if avg_value is None:
                            continue

                        comp = self._find_component_by_host(hostname)
                        if comp is None:
                            continue

                        self._apply_metric(comp, local_metric, avg_value)
                        metrics_imported += 1
                        components_updated.add(comp.id)
                        details.append({
                            "component_id": comp.id,
                            "metric": local_metric,
                            "value": round(avg_value, 2),
                            "source": "newrelic",
                        })
                except Exception as exc:
                    errors.append(f"New Relic NRQL query failed: {exc}")
                    logger.warning("New Relic query failed: %s", exc)
        finally:
            if _client is None and hasattr(client, "close"):
                client.close()

        return MetricImportResult(
            source="newrelic",
            components_updated=len(components_updated),
            metrics_imported=metrics_imported,
            calibration_applied=metrics_imported > 0,
            errors=errors,
            details=details,
        )

    # ------------------------------------------------------------------
    # Grafana
    # ------------------------------------------------------------------

    def import_from_grafana(
        self,
        url: str,
        api_key: str,
        dashboard_uid: str,
        *,
        _client: object | None = None,
    ) -> MetricImportResult:
        """Import from Grafana datasource API (read-only).

        Fetches the dashboard definition to discover panel queries,
        then proxies through Grafana's datasource API to fetch metrics.

        Args:
            url: Grafana base URL (e.g. ``http://grafana:3000``).
            api_key: Grafana API key / service account token.
            dashboard_uid: UID of the dashboard to import from.
            _client: Optional pre-built httpx client for testing / DI.

        Returns:
            MetricImportResult with import statistics.
        """
        import httpx

        base_url = url.rstrip("/")
        client = _client or httpx.Client(
            base_url=base_url,
            timeout=30,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        metrics_imported = 0
        components_updated: set[str] = set()
        errors: list[str] = []
        details: list[dict] = []

        try:
            # Fetch dashboard to discover panels
            try:
                resp = client.get(f"/api/dashboards/uid/{dashboard_uid}")
                resp.raise_for_status()
                dashboard_data = resp.json()
            except Exception as exc:
                errors.append(f"Failed to fetch Grafana dashboard: {exc}")
                return MetricImportResult(
                    source="grafana",
                    components_updated=0,
                    metrics_imported=0,
                    calibration_applied=False,
                    errors=errors,
                )

            dashboard = dashboard_data.get("dashboard", {})
            panels = dashboard.get("panels", [])

            for panel in panels:
                panel_title = panel.get("title", "").lower()
                targets = panel.get("targets", [])

                # Determine metric type from panel title
                local_metric = None
                if "cpu" in panel_title:
                    local_metric = "cpu_percent"
                elif "memory" in panel_title or "mem" in panel_title:
                    local_metric = "memory_percent"
                elif "disk" in panel_title:
                    local_metric = "disk_percent"

                if local_metric is None:
                    continue

                # Extract metrics from panel data (if inline data is provided)
                datasource_id = panel.get("datasource", {})
                if isinstance(datasource_id, dict):
                    datasource_id = datasource_id.get("uid", "")

                # Try to fetch panel data through datasource proxy
                for target in targets:
                    expr = target.get("expr", "")
                    target.get("refId", "A")
                    if not expr:
                        continue

                    try:
                        query_resp = client.get(
                            "/api/datasources/proxy/1/api/v1/query",
                            params={"query": expr},
                        )
                        query_resp.raise_for_status()
                        query_data = query_resp.json()

                        for result in query_data.get("data", {}).get("result", []):
                            instance = result.get("metric", {}).get("instance", "")
                            value_pair = result.get("value", [])
                            if len(value_pair) < 2:
                                continue

                            avg_value = float(value_pair[1])
                            comp = self._find_component_by_host(instance)
                            if comp is None:
                                continue

                            self._apply_metric(comp, local_metric, avg_value)
                            metrics_imported += 1
                            components_updated.add(comp.id)
                            details.append({
                                "component_id": comp.id,
                                "metric": local_metric,
                                "value": round(avg_value, 2),
                                "panel": panel.get("title", ""),
                            })
                    except Exception as exc:
                        errors.append(f"Grafana query failed for panel '{panel.get('title', '')}': {exc}")
                        logger.warning("Grafana query failed: %s", exc)
        finally:
            if _client is None and hasattr(client, "close"):
                client.close()

        return MetricImportResult(
            source="grafana",
            components_updated=len(components_updated),
            metrics_imported=metrics_imported,
            calibration_applied=metrics_imported > 0,
            errors=errors,
            details=details,
        )

    # ------------------------------------------------------------------
    # Generic JSON
    # ------------------------------------------------------------------

    def import_from_json(self, path: Path) -> MetricImportResult:
        """Import metrics from a generic JSON file.

        Expected format::

            {
                "component_id": {
                    "cpu_percent": 45.0,
                    "memory_percent": 60.0,
                    "disk_percent": 30.0,
                    "network_connections": 150
                },
                ...
            }

        Args:
            path: Path to the JSON file.

        Returns:
            MetricImportResult with import statistics.
        """
        errors: list[str] = []
        details: list[dict] = []
        metrics_imported = 0
        components_updated: set[str] = set()

        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            return MetricImportResult(
                source="json",
                components_updated=0,
                metrics_imported=0,
                calibration_applied=False,
                errors=[f"Failed to read JSON file: {exc}"],
            )

        if not isinstance(data, dict):
            return MetricImportResult(
                source="json",
                components_updated=0,
                metrics_imported=0,
                calibration_applied=False,
                errors=["JSON root must be an object mapping component_id to metrics"],
            )

        metric_fields = {
            "cpu_percent",
            "memory_percent",
            "disk_percent",
            "network_connections",
            "memory_used_mb",
            "memory_total_mb",
            "disk_used_gb",
            "disk_total_gb",
            "open_files",
        }

        for comp_id, metrics in data.items():
            comp = self._graph.get_component(comp_id)
            if comp is None:
                errors.append(f"Component '{comp_id}' not found in graph, skipped")
                continue

            if not isinstance(metrics, dict):
                errors.append(f"Metrics for '{comp_id}' must be a dict, skipped")
                continue

            updated = False
            for metric_name, value in metrics.items():
                if metric_name not in metric_fields:
                    continue
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError):
                    errors.append(
                        f"Invalid value for {comp_id}.{metric_name}: {value}"
                    )
                    continue

                self._apply_metric(comp, metric_name, numeric_value)
                metrics_imported += 1
                updated = True
                details.append({
                    "component_id": comp_id,
                    "metric": metric_name,
                    "value": round(numeric_value, 2),
                })

            if updated:
                components_updated.add(comp_id)

        return MetricImportResult(
            source="json",
            components_updated=len(components_updated),
            metrics_imported=metrics_imported,
            calibration_applied=metrics_imported > 0,
            errors=errors,
            details=details,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_component_by_host(self, host_or_instance: str) -> object | None:
        """Match a host/instance identifier to a graph component.

        Tries exact match on component host, then strips port and retries.
        Falls back to matching component id.
        """
        if not host_or_instance:
            return None

        # Strip port (e.g. "10.0.1.5:9100" -> "10.0.1.5")
        host = host_or_instance.split(":")[0] if ":" in host_or_instance else host_or_instance

        for comp in self._graph.components.values():
            if comp.host and (comp.host == host or comp.host == host_or_instance):
                return comp
            if comp.id == host or comp.id == host_or_instance:
                return comp
            if comp.name and comp.name.lower() == host.lower():
                return comp

        return None

    @staticmethod
    def _apply_metric(comp: object, metric_name: str, value: float) -> None:
        """Apply a metric value to a component's ResourceMetrics."""
        if metric_name == "cpu_percent":
            comp.metrics.cpu_percent = value
        elif metric_name == "memory_percent":
            comp.metrics.memory_percent = value
        elif metric_name == "disk_percent":
            comp.metrics.disk_percent = value
        elif metric_name == "network_connections":
            comp.metrics.network_connections = int(value)
        elif metric_name == "memory_used_mb":
            comp.metrics.memory_used_mb = value
        elif metric_name == "memory_total_mb":
            comp.metrics.memory_total_mb = value
        elif metric_name == "disk_used_gb":
            comp.metrics.disk_used_gb = value
        elif metric_name == "disk_total_gb":
            comp.metrics.disk_total_gb = value
        elif metric_name == "open_files":
            comp.metrics.open_files = int(value)
