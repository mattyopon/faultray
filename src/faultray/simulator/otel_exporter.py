# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""OpenTelemetry Simulation Exporter — generates OTel-compatible telemetry.

Produces traces, metrics, and logs in OTLP-compatible JSON format from chaos
simulation results.  This is the *reverse* of typical OTel usage: instead of
collecting data from production, FaultRay **generates** simulation data so
users can visualise results in Grafana / Datadog / New Relic dashboards.

No data is sent anywhere — the exporter only builds the OTel-compatible
payload structure.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OTelSignalType(str, Enum):
    """Top-level OTel signal categories."""

    TRACE = "trace"
    METRIC = "metric"
    LOG = "log"


class MetricType(str, Enum):
    """Supported OTel metric instrument types."""

    GAUGE = "gauge"
    COUNTER = "counter"
    HISTOGRAM = "histogram"


class SpanStatus(str, Enum):
    """Span completion status (mirrors OTel StatusCode)."""

    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class SimulationSpan(BaseModel):
    """A single span representing one step in a simulation trace."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    operation_name: str
    service_name: str
    start_time: datetime
    end_time: datetime
    status: SpanStatus = SpanStatus.UNSET
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)
    events: list[dict] = Field(default_factory=list)


class SimulationMetric(BaseModel):
    """A single metric data-point produced by a simulation."""

    name: str
    description: str
    metric_type: MetricType
    value: float
    unit: str
    timestamp: datetime
    labels: dict[str, str] = Field(default_factory=dict)


class SimulationLog(BaseModel):
    """A single log record produced by a simulation."""

    timestamp: datetime
    severity: str
    body: str
    service_name: str
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)


class OTelExportConfig(BaseModel):
    """Configuration for the OTel exporter."""

    endpoint: str = ""
    protocol: str = "grpc"
    headers: dict[str, str] = Field(default_factory=dict)
    batch_size: int = 100
    export_traces: bool = True
    export_metrics: bool = True
    export_logs: bool = True


class OTelExportResult(BaseModel):
    """Summary returned after a full telemetry generation pass."""

    spans_generated: int = 0
    metrics_generated: int = 0
    logs_generated: int = 0
    export_format: str = "otlp_json"
    payload_size_bytes: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_trace_id() -> str:
    return uuid4().hex[:32]


def _new_span_id() -> str:
    return uuid4().hex[:16]


def _health_to_severity(health: str) -> str:
    mapping = {
        "healthy": "INFO",
        "degraded": "WARN",
        "overloaded": "WARN",
        "down": "ERROR",
    }
    return mapping.get(health, "INFO")


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------


class OTelSimulationExporter:
    """Generates OTel-compatible telemetry from FaultRay simulation results."""

    def __init__(
        self,
        graph: InfraGraph,
        config: OTelExportConfig | None = None,
    ) -> None:
        self.graph = graph
        self.config = config or OTelExportConfig()

    # -- traces -----------------------------------------------------------

    def generate_trace(
        self,
        scenario_name: str,
        affected_components: list[str],
        duration_ms: float,
        success: bool,
    ) -> list[SimulationSpan]:
        """Create a trace from a simulation scenario execution."""

        now = datetime.now(timezone.utc)
        trace_id = _new_trace_id()
        root_span_id = _new_span_id()

        root_span = SimulationSpan(
            trace_id=trace_id,
            span_id=root_span_id,
            operation_name=f"simulation.{scenario_name}",
            service_name="faultray-simulator",
            start_time=now,
            end_time=now + timedelta(milliseconds=duration_ms),
            status=SpanStatus.OK if success else SpanStatus.ERROR,
            attributes={
                "faultray.scenario": scenario_name,
                "faultray.success": success,
                "faultray.affected_count": len(affected_components),
            },
        )
        spans: list[SimulationSpan] = [root_span]

        child_offset = 0.0
        for comp_id in affected_components:
            comp = self.graph.get_component(comp_id)
            child_span_id = _new_span_id()
            svc = comp.name if comp else comp_id
            child_duration = duration_ms / max(len(affected_components), 1)

            child_start = now + timedelta(milliseconds=child_offset)
            child_end = child_start + timedelta(milliseconds=child_duration)

            child_status = SpanStatus.OK
            child_events: list[dict] = []
            if comp and comp.health != HealthStatus.HEALTHY:
                child_status = SpanStatus.ERROR
                child_events.append({
                    "name": "health_degraded",
                    "timestamp": child_start.isoformat(),
                    "attributes": {"health": comp.health.value},
                })

            spans.append(
                SimulationSpan(
                    trace_id=trace_id,
                    span_id=child_span_id,
                    parent_span_id=root_span_id,
                    operation_name=f"component.evaluate.{comp_id}",
                    service_name=svc,
                    start_time=child_start,
                    end_time=child_end,
                    status=child_status,
                    attributes={
                        "component.id": comp_id,
                        "component.type": comp.type.value if comp else "unknown",
                    },
                    events=child_events,
                )
            )
            child_offset += child_duration

        return spans

    # -- metrics ----------------------------------------------------------

    def generate_metrics(
        self,
        component_id: str,
        health_status: str,
        utilization: float,
    ) -> list[SimulationMetric]:
        """Create metrics for a single component snapshot."""

        now = datetime.now(timezone.utc)
        comp = self.graph.get_component(component_id)
        labels: dict[str, str] = {
            "component_id": component_id,
            "service": comp.name if comp else component_id,
        }
        if comp:
            labels["component_type"] = comp.type.value

        metrics: list[SimulationMetric] = [
            SimulationMetric(
                name="faultray.component.health",
                description="Component health status (0=down, 1=degraded, 2=healthy)",
                metric_type=MetricType.GAUGE,
                value={"healthy": 2.0, "degraded": 1.0, "overloaded": 1.0, "down": 0.0}.get(
                    health_status, 2.0
                ),
                unit="status",
                timestamp=now,
                labels=labels,
            ),
            SimulationMetric(
                name="faultray.component.utilization",
                description="Component utilization percentage",
                metric_type=MetricType.GAUGE,
                value=utilization,
                unit="percent",
                timestamp=now,
                labels=labels,
            ),
            SimulationMetric(
                name="faultray.simulation.events",
                description="Count of simulation events for component",
                metric_type=MetricType.COUNTER,
                value=1.0,
                unit="count",
                timestamp=now,
                labels=labels,
            ),
        ]
        return metrics

    # -- logs -------------------------------------------------------------

    def generate_logs(
        self,
        component_id: str,
        events: list[str],
        severity: str = "INFO",
    ) -> list[SimulationLog]:
        """Create log records for simulation events on a component."""

        now = datetime.now(timezone.utc)
        comp = self.graph.get_component(component_id)
        svc = comp.name if comp else component_id
        logs: list[SimulationLog] = []

        for idx, event_text in enumerate(events):
            logs.append(
                SimulationLog(
                    timestamp=now + timedelta(milliseconds=idx),
                    severity=severity,
                    body=event_text,
                    service_name=svc,
                    attributes={
                        "component.id": component_id,
                        "event.index": idx,
                    },
                )
            )
        return logs

    # -- JSON export ------------------------------------------------------

    def export_to_json(
        self,
        spans: list[SimulationSpan],
        metrics: list[SimulationMetric],
        logs: list[SimulationLog],
    ) -> dict:
        """Serialize telemetry to OTLP-compatible JSON structure."""

        def _ser_span(s: SimulationSpan) -> dict:
            d = {
                "traceId": s.trace_id,
                "spanId": s.span_id,
                "operationName": s.operation_name,
                "serviceName": s.service_name,
                "startTimeUnixNano": int(s.start_time.timestamp() * 1e9),
                "endTimeUnixNano": int(s.end_time.timestamp() * 1e9),
                "status": {"code": s.status.value},
                "attributes": s.attributes,
                "events": s.events,
            }
            if s.parent_span_id:
                d["parentSpanId"] = s.parent_span_id
            return d

        def _ser_metric(m: SimulationMetric) -> dict:
            return {
                "name": m.name,
                "description": m.description,
                "type": m.metric_type.value,
                "value": m.value,
                "unit": m.unit,
                "timestampUnixNano": int(m.timestamp.timestamp() * 1e9),
                "labels": m.labels,
            }

        def _ser_log(lg: SimulationLog) -> dict:
            return {
                "timestampUnixNano": int(lg.timestamp.timestamp() * 1e9),
                "severityText": lg.severity,
                "body": lg.body,
                "serviceName": lg.service_name,
                "attributes": lg.attributes,
            }

        return {
            "resourceSpans": [_ser_span(s) for s in spans],
            "resourceMetrics": [_ser_metric(m) for m in metrics],
            "resourceLogs": [_ser_log(lg) for lg in logs],
        }

    # -- full pipeline ----------------------------------------------------

    def generate_simulation_telemetry(
        self,
        scenario_results: list[dict],
    ) -> OTelExportResult:
        """Generate full OTel telemetry from a batch of scenario results.

        Each *scenario_result* dict is expected to contain:
          - ``scenario_name`` (str)
          - ``affected_components`` (list[str])
          - ``duration_ms`` (float)
          - ``success`` (bool)
          - ``health_status`` (str)  — optional, default ``"healthy"``
          - ``utilization`` (float) — optional, default ``0.0``
          - ``events`` (list[str])  — optional, default ``[]``
        """

        all_spans: list[SimulationSpan] = []
        all_metrics: list[SimulationMetric] = []
        all_logs: list[SimulationLog] = []

        for res in scenario_results:
            name = res.get("scenario_name", "unknown")
            affected = res.get("affected_components", [])
            dur = res.get("duration_ms", 0.0)
            ok = res.get("success", True)
            health = res.get("health_status", "healthy")
            util = res.get("utilization", 0.0)
            evts = res.get("events", [])

            if self.config.export_traces:
                all_spans.extend(
                    self.generate_trace(name, affected, dur, ok)
                )

            for comp_id in affected:
                if self.config.export_metrics:
                    all_metrics.extend(
                        self.generate_metrics(comp_id, health, util)
                    )
                if self.config.export_logs and evts:
                    severity = _health_to_severity(health)
                    all_logs.extend(
                        self.generate_logs(comp_id, evts, severity)
                    )

        payload = self.export_to_json(all_spans, all_metrics, all_logs)
        payload_bytes = len(json.dumps(payload).encode())

        return OTelExportResult(
            spans_generated=len(all_spans),
            metrics_generated=len(all_metrics),
            logs_generated=len(all_logs),
            export_format="otlp_json",
            payload_size_bytes=payload_bytes,
        )
