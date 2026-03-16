"""Calibrate simulation models using real-world metrics.

Reads REAL metrics from Prometheus or CloudWatch (read-only) and adjusts
simulation parameters so that the model matches observed reality.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


@dataclass
class CalibrationResult:
    """Result of calibrating a single metric on a component."""

    component_id: str
    metric: str
    simulated_value: float
    actual_value: float
    deviation_percent: float
    calibrated: bool


class MetricCalibrator:
    """Calibrate simulation models using real-world metrics.

    Reads metrics from Prometheus or AWS CloudWatch (strictly read-only)
    and adjusts the component resource metrics in the InfraGraph so the
    model reflects actual system behaviour.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calibrate_from_prometheus(
        self,
        url: str,
        *,
        deviation_threshold: float = 10.0,
        _client: object | None = None,
    ) -> list[CalibrationResult]:
        """Read Prometheus metrics and calibrate component metrics.

        Queries ``up``, ``node_cpu_seconds_total``, and
        ``node_memory_MemAvailable_bytes`` from the given Prometheus
        endpoint.  Only **read** operations are performed.

        Args:
            url: Prometheus base URL (e.g. ``http://prometheus:9090``).
            deviation_threshold: minimum deviation % to trigger calibration.
            _client: optional pre-built HTTP client (for testing / DI).

        Returns:
            A list of :class:`CalibrationResult` entries.
        """
        import httpx

        client = _client or httpx.Client(base_url=url.rstrip("/"), timeout=30)
        results: list[CalibrationResult] = []

        try:
            # --- CPU ---
            cpu_data = self._prom_query(
                client,
                '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
            )
            for entry in cpu_data:
                instance = entry["metric"].get("instance", "")
                actual_cpu = self._safe_float(entry["value"][1])
                comp = self._find_component_by_host(instance)
                if comp is None:
                    continue
                sim_cpu = comp.metrics.cpu_percent
                dev = self._deviation(sim_cpu, actual_cpu)
                calibrated = abs(dev) >= deviation_threshold
                if calibrated:
                    comp.metrics.cpu_percent = actual_cpu
                results.append(
                    CalibrationResult(
                        component_id=comp.id,
                        metric="cpu_percent",
                        simulated_value=sim_cpu,
                        actual_value=actual_cpu,
                        deviation_percent=dev,
                        calibrated=calibrated,
                    )
                )

            # --- Memory ---
            mem_total_data = self._prom_query(client, "node_memory_MemTotal_bytes")
            mem_avail_data = self._prom_query(client, "node_memory_MemAvailable_bytes")

            mem_totals: dict[str, float] = {}
            for entry in mem_total_data:
                inst = entry["metric"].get("instance", "")
                mem_totals[inst] = self._safe_float(entry["value"][1])

            for entry in mem_avail_data:
                inst = entry["metric"].get("instance", "")
                avail = self._safe_float(entry["value"][1])
                total = mem_totals.get(inst, 0.0)
                if total <= 0:
                    continue
                actual_mem_pct = (1.0 - avail / total) * 100.0
                comp = self._find_component_by_host(inst)
                if comp is None:
                    continue
                sim_mem = comp.metrics.memory_percent
                dev = self._deviation(sim_mem, actual_mem_pct)
                calibrated = abs(dev) >= deviation_threshold
                if calibrated:
                    comp.metrics.memory_percent = actual_mem_pct
                results.append(
                    CalibrationResult(
                        component_id=comp.id,
                        metric="memory_percent",
                        simulated_value=sim_mem,
                        actual_value=actual_mem_pct,
                        deviation_percent=dev,
                        calibrated=calibrated,
                    )
                )
        finally:
            if _client is None and hasattr(client, "close"):
                client.close()

        return results

    def calibrate_from_cloudwatch(
        self,
        region: str,
        *,
        deviation_threshold: float = 10.0,
        _cw_client: object | None = None,
    ) -> list[CalibrationResult]:
        """Read CloudWatch metrics and adjust component utilization / MTBF.

        Uses **GetMetricData** only -- strictly read-only, no writes.

        Args:
            region: AWS region (e.g. ``ap-northeast-1``).
            deviation_threshold: minimum deviation % to trigger calibration.
            _cw_client: optional pre-built boto3 CloudWatch client (for DI).

        Returns:
            A list of :class:`CalibrationResult` entries.
        """
        import datetime

        if _cw_client is None:
            import boto3

            cw = boto3.client("cloudwatch", region_name=region)
        else:
            cw = _cw_client

        results: list[CalibrationResult] = []
        end_time = datetime.datetime.now(datetime.timezone.utc)
        start_time = end_time - datetime.timedelta(hours=1)

        for comp in self._graph.components.values():
            # Build metric queries based on component type
            queries = self._build_cw_queries(comp.id, comp.type.value)
            if not queries:
                continue

            try:
                response = cw.get_metric_data(
                    MetricDataQueries=queries,
                    StartTime=start_time,
                    EndTime=end_time,
                )
            except Exception as exc:
                logger.warning("CloudWatch query failed for %s: %s", comp.id, exc)
                continue

            for metric_result in response.get("MetricDataResults", []):
                metric_id = metric_result.get("Id", "")
                values = metric_result.get("Values", [])
                if not values:
                    continue
                actual_value = sum(values) / len(values)

                if metric_id.startswith("cpu_"):
                    sim_value = comp.metrics.cpu_percent
                    metric_name = "cpu_percent"
                elif metric_id.startswith("mem_"):
                    sim_value = comp.metrics.memory_percent
                    metric_name = "memory_percent"
                else:
                    continue

                dev = self._deviation(sim_value, actual_value)
                calibrated = abs(dev) >= deviation_threshold
                if calibrated:
                    if metric_name == "cpu_percent":
                        comp.metrics.cpu_percent = actual_value
                    elif metric_name == "memory_percent":
                        comp.metrics.memory_percent = actual_value

                results.append(
                    CalibrationResult(
                        component_id=comp.id,
                        metric=metric_name,
                        simulated_value=sim_value,
                        actual_value=actual_value,
                        deviation_percent=dev,
                        calibrated=calibrated,
                    )
                )

        return results

    def apply_calibration(self, results: list[CalibrationResult]) -> None:
        """Apply calibration adjustments to the graph.

        Only results where ``calibrated`` is ``True`` and the component
        exists in the graph are applied.
        """
        for r in results:
            if not r.calibrated:
                continue
            comp = self._graph.get_component(r.component_id)
            if comp is None:
                continue
            if r.metric == "cpu_percent":
                comp.metrics.cpu_percent = r.actual_value
            elif r.metric == "memory_percent":
                comp.metrics.memory_percent = r.actual_value

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_component_by_host(self, instance: str) -> object | None:
        """Match a Prometheus ``instance`` label to a graph component."""
        # Strip port from instance (e.g. "10.0.1.5:9100" -> "10.0.1.5")
        host = instance.split(":")[0] if ":" in instance else instance
        for comp in self._graph.components.values():
            if comp.host and (comp.host == host or comp.host == instance):
                return comp
        return None

    @staticmethod
    def _prom_query(client: object, query: str) -> list[dict]:
        """Execute an instant PromQL query and return the result vector."""
        resp = client.get("/api/v1/query", params={"query": query})
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            return []
        return data.get("data", {}).get("result", [])

    @staticmethod
    def _safe_float(value: str | float | int, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _deviation(simulated: float, actual: float) -> float:
        """Percentage deviation of simulated from actual."""
        if actual == 0.0:
            return 0.0 if simulated == 0.0 else 100.0
        return ((simulated - actual) / actual) * 100.0

    @staticmethod
    def _build_cw_queries(comp_id: str, comp_type: str) -> list[dict]:
        """Build CloudWatch GetMetricData queries for a component."""
        safe_id = comp_id.replace("-", "_").replace(".", "_")
        queries: list[dict] = []

        namespace = "AWS/EC2"
        if comp_type == "database":
            namespace = "AWS/RDS"
        elif comp_type == "cache":
            namespace = "AWS/ElastiCache"
        elif comp_type == "load_balancer":
            namespace = "AWS/ELB"

        queries.append(
            {
                "Id": f"cpu_{safe_id}",
                "MetricStat": {
                    "Metric": {
                        "Namespace": namespace,
                        "MetricName": "CPUUtilization",
                        "Dimensions": [{"Name": "InstanceId", "Value": comp_id}],
                    },
                    "Period": 300,
                    "Stat": "Average",
                },
            }
        )

        if comp_type == "database":
            queries.append(
                {
                    "Id": f"mem_{safe_id}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/RDS",
                            "MetricName": "FreeableMemory",
                            "Dimensions": [
                                {"Name": "DBInstanceIdentifier", "Value": comp_id}
                            ],
                        },
                        "Period": 300,
                        "Stat": "Average",
                    },
                }
            )

        return queries
