# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Datadog Integration -- metrics-driven resilience simulation.

Pull metrics from Datadog -> update InfraGraph -> auto-simulate -> push alerts back.
Enables 'Observability -> Predictability' workflow that Datadog lacks natively.

Workflow:
    1. Pull real-time metrics from Datadog Metrics API v2
    2. Map metrics to InfraGraph ResourceMetrics
    3. Run CascadeEngine simulation automatically
    4. Push resilience scores and failure predictions back as Datadog events/metrics
    5. Export dashboard widget JSON for native Datadog integration

Environment variables:
    DATADOG_API_KEY   -- Datadog API key (required for live mode)
    DATADOG_APP_KEY   -- Datadog Application key (required for live mode)

When API keys are not set, all API calls return realistic mock data so the
integration can be tested without a Datadog account.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine, SimulationReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

_MOCK_METRICS: dict[str, list[dict]] = {
    "system.cpu.user": [
        {"scope": "host:web-1", "pointlist": [[1700000000, 45.2], [1700003600, 47.8]]},
        {"scope": "host:db-1", "pointlist": [[1700000000, 62.1], [1700003600, 65.3]]},
    ],
    "system.mem.pct_usable": [
        {"scope": "host:web-1", "pointlist": [[1700000000, 0.55], [1700003600, 0.58]]},
        {"scope": "host:db-1", "pointlist": [[1700000000, 0.72], [1700003600, 0.75]]},
    ],
    "system.disk.in_use": [
        {"scope": "host:web-1", "pointlist": [[1700000000, 0.30], [1700003600, 0.31]]},
        {"scope": "host:db-1", "pointlist": [[1700000000, 0.65], [1700003600, 0.68]]},
    ],
}


def _is_mock_mode(api_key: str | None, app_key: str | None) -> bool:
    """Return True when we should use mock data instead of live API."""
    return not api_key or not app_key


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class DatadogIntegration:
    """Bi-directional Datadog integration for metrics-driven resilience simulation.

    When ``api_key`` and ``app_key`` are provided, real Datadog API calls are
    made.  Otherwise, the integration operates in **mock mode** returning
    realistic sample data -- ideal for demos, tests, and offline development.

    Typical usage::

        graph = InfraGraph.load(Path("infra.json"))
        dd = DatadogIntegration(
            api_key=os.environ.get("DATADOG_API_KEY"),
            app_key=os.environ.get("DATADOG_APP_KEY"),
            graph=graph,
        )
        metrics = dd.pull_metrics(period="1h")
        dd.update_graph(metrics)
        report = dd.auto_simulate()
        dd.push_event("FaultRay Simulation", f"Score: {report.resilience_score}")
        dd.push_metric("faultray.resilience_score", report.resilience_score,
                        tags=["env:prod"])
    """

    def __init__(
        self,
        api_key: str | None = None,
        app_key: str | None = None,
        graph: InfraGraph | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("DATADOG_API_KEY", "")
        self._app_key = app_key or os.environ.get("DATADOG_APP_KEY", "")
        self._graph = graph or InfraGraph()
        self._mock = _is_mock_mode(self._api_key, self._app_key)
        if self._mock:
            logger.info("DatadogIntegration running in mock mode (no API keys).")

    # ------------------------------------------------------------------
    # Pull metrics
    # ------------------------------------------------------------------

    def pull_metrics(self, period: str = "1h") -> dict:
        """Pull infrastructure metrics from Datadog Metrics API v2.

        Args:
            period: Time window to query (e.g. ``"1h"``, ``"6h"``, ``"24h"``).

        Returns:
            Dict keyed by metric name, each containing a list of series dicts
            with ``scope`` and ``pointlist`` keys.
        """
        if self._mock:
            logger.debug("Returning mock Datadog metrics for period=%s", period)
            return dict(_MOCK_METRICS)

        hours = _parse_period_hours(period)
        now = int(time.time())
        from_ts = now - (hours * 3600)

        metric_queries = [
            "system.cpu.user",
            "system.mem.pct_usable",
            "system.disk.in_use",
        ]

        result: dict[str, list[dict]] = {}
        with httpx.Client(
            base_url="https://api.datadoghq.com",
            timeout=30,
            headers={
                "DD-API-KEY": self._api_key,
                "DD-APPLICATION-KEY": self._app_key,
            },
        ) as client:
            for metric in metric_queries:
                try:
                    resp = client.get(
                        "/api/v1/query",
                        params={
                            "from": from_ts,
                            "to": now,
                            "query": f"avg:{metric}{{*}} by {{host}}",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    result[metric] = data.get("series", [])
                except Exception as exc:
                    logger.warning("Datadog query failed for %s: %s", metric, exc)
                    result[metric] = []

        return result

    # ------------------------------------------------------------------
    # Update graph
    # ------------------------------------------------------------------

    def update_graph(self, metrics: dict) -> int:
        """Map pulled Datadog metrics onto InfraGraph ResourceMetrics.

        Args:
            metrics: Dict returned by :meth:`pull_metrics`.

        Returns:
            Number of component metrics updated.
        """
        updated = 0
        metric_mapping = {
            "system.cpu.user": "cpu_percent",
            "system.mem.pct_usable": "memory_percent",
            "system.disk.in_use": "disk_percent",
        }

        for dd_metric, local_metric in metric_mapping.items():
            for series in metrics.get(dd_metric, []):
                scope = series.get("scope", "")
                host = scope.replace("host:", "") if scope.startswith("host:") else scope
                pointlist = series.get("pointlist", [])
                values = [p[1] for p in pointlist if p[1] is not None]
                if not values:
                    continue
                avg_value = sum(values) / len(values)

                # Fractional metrics (0-1) → percentage
                if local_metric in ("memory_percent", "disk_percent"):
                    avg_value *= 100.0

                comp = self._find_component(host)
                if comp is None:
                    continue

                _apply_metric(comp, local_metric, avg_value)
                updated += 1

        return updated

    # ------------------------------------------------------------------
    # Auto-simulate
    # ------------------------------------------------------------------

    def auto_simulate(self) -> SimulationReport:
        """Run a full FaultRay simulation using the current graph state.

        Returns:
            :class:`SimulationReport` with cascade results, risk scores, and
            resilience score.
        """
        engine = SimulationEngine(self._graph)
        return engine.run_all()

    # ------------------------------------------------------------------
    # Push event
    # ------------------------------------------------------------------

    def push_event(
        self,
        title: str,
        text: str,
        alert_type: str = "warning",
        tags: list[str] | None = None,
    ) -> bool:
        """Push an event to Datadog Events API v1.

        Args:
            title: Event title.
            text: Event body (supports Markdown).
            alert_type: One of ``info``, ``warning``, ``error``, ``success``.
            tags: Optional list of tags (e.g. ``["env:prod", "team:sre"]``).

        Returns:
            True if the event was accepted (or mock mode).
        """
        if self._mock:
            logger.info("Mock push_event: title=%s alert_type=%s", title, alert_type)
            return True

        payload = {
            "title": title,
            "text": text,
            "alert_type": alert_type,
            "source_type_name": "faultray",
            "tags": tags or ["source:faultray"],
        }
        try:
            with httpx.Client(
                base_url="https://api.datadoghq.com",
                timeout=15,
                headers={
                    "DD-API-KEY": self._api_key,
                    "DD-APPLICATION-KEY": self._app_key,
                },
            ) as client:
                resp = client.post("/api/v1/events", json=payload)
                resp.raise_for_status()
                return True
        except Exception as exc:
            logger.warning("Datadog push_event failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Push metric
    # ------------------------------------------------------------------

    def push_metric(
        self,
        metric_name: str,
        value: float,
        tags: list[str] | None = None,
    ) -> bool:
        """Submit a custom metric to Datadog (e.g. ``faultray.resilience_score``).

        Args:
            metric_name: Metric name (dotted notation).
            value: Metric value.
            tags: Optional list of tags.

        Returns:
            True if the metric was accepted (or mock mode).
        """
        if self._mock:
            logger.info("Mock push_metric: %s=%s", metric_name, value)
            return True

        now = int(time.time())
        payload = {
            "series": [
                {
                    "metric": metric_name,
                    "type": "gauge",
                    "points": [[now, value]],
                    "tags": tags or ["source:faultray"],
                }
            ]
        }
        try:
            with httpx.Client(
                base_url="https://api.datadoghq.com",
                timeout=15,
                headers={"DD-API-KEY": self._api_key},
            ) as client:
                resp = client.post("/api/v1/series", json=payload)
                resp.raise_for_status()
                return True
        except Exception as exc:
            logger.warning("Datadog push_metric failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Continuous polling loop
    # ------------------------------------------------------------------

    def run_continuous(self, interval_minutes: int = 60, max_iterations: int = 0) -> None:
        """Run a continuous pull -> update -> simulate -> push loop.

        Args:
            interval_minutes: Polling interval in minutes.
            max_iterations: Stop after N iterations (0 = infinite).
        """
        iteration = 0
        while True:
            iteration += 1
            logger.info("DatadogIntegration loop iteration %d", iteration)

            metrics = self.pull_metrics(period=f"{interval_minutes}m")
            updated = self.update_graph(metrics)
            logger.info("Updated %d component metrics", updated)

            report = self.auto_simulate()
            score = report.resilience_score
            critical = len(report.critical_findings)
            warnings = len(report.warnings)

            self.push_metric("faultray.resilience_score", score)
            self.push_metric("faultray.critical_findings", float(critical))
            self.push_metric("faultray.warnings", float(warnings))

            if critical > 0:
                self.push_event(
                    title=f"FaultRay: {critical} critical risks detected",
                    text=(
                        f"Resilience score: {score}/100\n"
                        f"Critical findings: {critical}\n"
                        f"Warnings: {warnings}"
                    ),
                    alert_type="error",
                )

            if max_iterations and iteration >= max_iterations:
                logger.info("Reached max_iterations=%d, stopping.", max_iterations)
                break

            time.sleep(interval_minutes * 60)

    # ------------------------------------------------------------------
    # Dashboard JSON export
    # ------------------------------------------------------------------

    def export_dashboard_json(self) -> dict:
        """Generate a Datadog dashboard widget definition for FaultRay metrics.

        Returns:
            Dict suitable for use in Datadog Dashboard API ``widgets`` array.
        """
        return {
            "title": "FaultRay Resilience Dashboard",
            "description": "Infrastructure resilience metrics powered by FaultRay",
            "widgets": [
                {
                    "definition": {
                        "type": "query_value",
                        "title": "Resilience Score",
                        "requests": [
                            {
                                "q": "avg:faultray.resilience_score{*}",
                                "aggregator": "last",
                            }
                        ],
                        "precision": 1,
                    }
                },
                {
                    "definition": {
                        "type": "timeseries",
                        "title": "Resilience Score Over Time",
                        "requests": [
                            {
                                "q": "avg:faultray.resilience_score{*}",
                                "display_type": "line",
                            }
                        ],
                    }
                },
                {
                    "definition": {
                        "type": "query_value",
                        "title": "Critical Findings",
                        "requests": [
                            {
                                "q": "avg:faultray.critical_findings{*}",
                                "aggregator": "last",
                                "conditional_formats": [
                                    {"comparator": ">", "value": 0, "palette": "white_on_red"},
                                    {"comparator": "<=", "value": 0, "palette": "white_on_green"},
                                ],
                            }
                        ],
                    }
                },
                {
                    "definition": {
                        "type": "event_stream",
                        "title": "FaultRay Events",
                        "query": "sources:faultray",
                        "event_size": "s",
                    }
                },
            ],
            "layout_type": "ordered",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_component(self, host_or_id: str) -> object | None:
        """Match a host identifier to a graph component."""
        if not host_or_id:
            return None
        host = host_or_id.split(":")[0] if ":" in host_or_id else host_or_id
        for comp in self._graph.components.values():
            if comp.host and (comp.host == host or comp.host == host_or_id):
                return comp
            if comp.id == host or comp.id == host_or_id:
                return comp
            if comp.name and comp.name.lower() == host.lower():
                return comp
        return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _apply_metric(comp: object, metric_name: str, value: float) -> None:
    """Apply a metric value to a component's ResourceMetrics."""
    if metric_name == "cpu_percent":
        comp.metrics.cpu_percent = value
    elif metric_name == "memory_percent":
        comp.metrics.memory_percent = value
    elif metric_name == "disk_percent":
        comp.metrics.disk_percent = value


def _parse_period_hours(period: str) -> int:
    """Parse period string like '1h', '6h', '24h', '60m' into hours."""
    period = period.strip().lower()
    if period.endswith("h"):
        return max(1, int(period[:-1]))
    if period.endswith("m"):
        return max(1, int(period[:-1]) // 60)
    if period.endswith("d"):
        return max(1, int(period[:-1]) * 24)
    return 1
