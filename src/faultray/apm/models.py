# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Pydantic data models for APM metrics, traces, and agent registration."""

from __future__ import annotations

import datetime as _dt
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

# Upper bound on the number of items accepted in any single agent->collector
# batch list (processes / connections / traces / custom_metrics). Bounds memory
# use and DB write amplification from an oversized or malicious POST; mirrors
# the collector's ``_MAX_LIMIT`` query-param cap. Pydantic rejects larger lists
# with a 422 before the ingest handler runs.
_MAX_BATCH_ITEMS = 10000

# Aggregate cap on connections across the WHOLE batch (top-level list plus every
# process's nested list). The per-list max_length bounds each list individually
# but not their PRODUCT: 10000 processes x 10000 connections each = 100M nested
# ConnectionInfo objects would still validate and then flatten in
# update_topology_from_batch(). Bound the sum so the intended batch budget holds.
_MAX_TOTAL_CONNECTIONS = 100_000


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MetricType(str, Enum):
    """Type of metric being reported."""

    GAUGE = "gauge"
    COUNTER = "counter"
    HISTOGRAM = "histogram"


class AgentStatus(str, Enum):
    """Agent lifecycle status."""

    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    UNKNOWN = "unknown"


class AlertSeverity(str, Enum):
    """Alert severity level."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Metric data-points
# ---------------------------------------------------------------------------

class MetricPoint(BaseModel):
    """A single metric data-point."""

    name: str = Field(..., description="Metric name, e.g. 'cpu_percent'")
    value: float = Field(..., description="Metric value")
    metric_type: MetricType = Field(MetricType.GAUGE, description="Metric type")
    tags: dict[str, str] = Field(default_factory=dict, description="Dimensional tags")
    timestamp: _dt.datetime = Field(
        default_factory=lambda: _dt.datetime.now(_dt.timezone.utc),
        description="UTC timestamp",
    )


class HostMetrics(BaseModel):
    """System-level metrics collected by the agent."""

    cpu_percent: float = 0.0
    cpu_count: int = 1
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    network_bytes_sent: int = 0
    network_bytes_recv: int = 0
    network_connections: int = 0
    load_avg_1m: float = 0.0
    load_avg_5m: float = 0.0
    load_avg_15m: float = 0.0


class ProcessInfo(BaseModel):
    """Information about a single process."""

    pid: int
    name: str = ""
    cmdline: str = ""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_rss_mb: float = 0.0
    status: str = ""
    create_time: float = 0.0
    num_threads: int = 0
    # Cap nested connection lists too. update_topology_from_batch() flattens
    # every process's connections, so an unbounded list here would let one
    # process with a huge connections array bypass the per-batch list cap and
    # still drive excessive validation / memory / topology work.
    connections: list[ConnectionInfo] = Field(
        default_factory=list, max_length=_MAX_BATCH_ITEMS
    )


class ConnectionInfo(BaseModel):
    """Network connection information."""

    local_addr: str = ""
    local_port: int = 0
    remote_addr: str = ""
    remote_port: int = 0
    status: str = ""
    pid: int | None = None


# Fix forward reference
ProcessInfo.model_rebuild()


class TraceSpan(BaseModel):
    """A single trace span for request-level latency measurement."""

    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_span_id: str | None = None
    operation: str = ""
    service: str = ""
    duration_ms: float = 0.0
    status_code: int = 0
    error: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    start_time: _dt.datetime = Field(
        default_factory=lambda: _dt.datetime.now(_dt.timezone.utc),
    )


# ---------------------------------------------------------------------------
# Agent registration & heartbeat
# ---------------------------------------------------------------------------

class AgentRegistration(BaseModel):
    """Agent registration / heartbeat payload."""

    agent_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    hostname: str = ""
    ip_address: str = ""
    os_info: str = ""
    agent_version: str = ""
    labels: dict[str, str] = Field(default_factory=dict)
    registered_at: _dt.datetime = Field(
        default_factory=lambda: _dt.datetime.now(_dt.timezone.utc),
    )


class AgentHeartbeat(BaseModel):
    """Periodic heartbeat from an agent."""

    agent_id: str = ""
    status: AgentStatus = AgentStatus.RUNNING
    uptime_seconds: float = 0.0
    timestamp: _dt.datetime = Field(
        default_factory=lambda: _dt.datetime.now(_dt.timezone.utc),
    )


# ---------------------------------------------------------------------------
# Batch payloads (agent → collector)
# ---------------------------------------------------------------------------

class MetricsBatch(BaseModel):
    """Batch of metrics sent by an agent."""

    agent_id: str
    host_metrics: HostMetrics | None = None
    processes: list[ProcessInfo] = Field(
        default_factory=list, max_length=_MAX_BATCH_ITEMS
    )
    connections: list[ConnectionInfo] = Field(
        default_factory=list, max_length=_MAX_BATCH_ITEMS
    )
    traces: list[TraceSpan] = Field(
        default_factory=list, max_length=_MAX_BATCH_ITEMS
    )
    custom_metrics: list[MetricPoint] = Field(
        default_factory=list, max_length=_MAX_BATCH_ITEMS
    )
    timestamp: _dt.datetime = Field(
        default_factory=lambda: _dt.datetime.now(_dt.timezone.utc),
    )

    @model_validator(mode="before")
    @classmethod
    def _bound_total_connections(cls, data: Any) -> Any:
        """Reject an abusive processes x connections product up front.

        Runs on the raw payload BEFORE the nested ConnectionInfo models are
        built, so a batch whose aggregate connection count (top-level + every
        process's nested list) exceeds the budget is rejected (422) without
        constructing/validating tens of millions of nested objects or flattening
        them in update_topology_from_batch().
        """
        if isinstance(data, dict):
            top = data.get("connections")
            total = len(top) if isinstance(top, list) else 0
            procs = data.get("processes")
            if isinstance(procs, list):
                for proc in procs:
                    if isinstance(proc, dict):
                        nested = proc.get("connections")
                        if isinstance(nested, list):
                            total += len(nested)
            if total > _MAX_TOTAL_CONNECTIONS:
                raise ValueError(
                    f"too many connections in batch: {total} exceeds the "
                    f"{_MAX_TOTAL_CONNECTIONS} aggregate limit (top-level + nested)"
                )
        return data


# ---------------------------------------------------------------------------
# Alert / anomaly models
# ---------------------------------------------------------------------------

class AlertRule(BaseModel):
    """Definition of an alert rule."""

    name: str
    metric_name: str
    condition: str = "gt"  # gt, lt, gte, lte, eq
    threshold: float = 0.0
    duration_seconds: int = 0  # how long condition must hold
    severity: AlertSeverity = AlertSeverity.WARNING
    labels: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    notification_channels: list[str] = Field(default_factory=list)


class Alert(BaseModel):
    """A fired alert."""

    alert_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    rule_name: str = ""
    agent_id: str = ""
    metric_name: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0
    severity: AlertSeverity = AlertSeverity.WARNING
    message: str = ""
    fired_at: _dt.datetime = Field(
        default_factory=lambda: _dt.datetime.now(_dt.timezone.utc),
    )
    resolved_at: _dt.datetime | None = None


class AnomalyResult(BaseModel):
    """Result from the anomaly detection engine."""

    metric_name: str
    agent_id: str = ""
    current_value: float = 0.0
    expected_value: float = 0.0
    deviation_sigma: float = 0.0
    is_anomaly: bool = False
    trend: str = ""  # "stable", "increasing", "decreasing", "spike"
    timestamp: _dt.datetime = Field(
        default_factory=lambda: _dt.datetime.now(_dt.timezone.utc),
    )


# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------

class AgentConfig(BaseModel):
    """Configuration for the FaultRay APM agent."""

    agent_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    collector_url: str = "http://localhost:8080"
    api_key: str = ""
    collect_interval_seconds: int = 15
    send_interval_seconds: int = 30
    collect_processes: bool = True
    process_filter: list[str] = Field(
        default_factory=list,
        description="Process name patterns to monitor (empty = all)",
    )
    collect_connections: bool = True
    collect_traces: bool = False
    labels: dict[str, str] = Field(default_factory=dict)
    log_level: str = "INFO"
    pid_file: str = "/var/run/faultray-agent.pid"
    log_file: str = "/var/log/faultray-agent.log"
    # Auto-discovery + simulation settings
    cloud_provider: str | None = Field(
        default=None,
        description='Cloud provider for discovery: "aws", "gcp", "azure", or None',
    )
    cloud_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific configuration (region, profile, project_id, etc.)",
    )
    discovery_interval_seconds: int = Field(
        default=3600,
        description="Interval between auto-discovery + simulation cycles (default: 1 hour)",
    )
    auto_simulate: bool = Field(
        default=True,
        description="Enable automatic chaos simulation after each discovery cycle",
    )
    model_output_path: str = Field(
        default="",
        description="Path for saving discovered model JSON (default: ~/.faultray/auto-model.json)",
    )


# ---------------------------------------------------------------------------
# Query / response models
# ---------------------------------------------------------------------------

class MetricsQuery(BaseModel):
    """Query parameters for metrics retrieval."""

    agent_id: str | None = None
    metric_names: list[str] = Field(default_factory=list)
    start_time: _dt.datetime | None = None
    end_time: _dt.datetime | None = None
    aggregation: str = "avg"  # avg, min, max, sum, count
    interval_seconds: int = Field(default=60, ge=1, le=86400)  # bucket size
    tags: dict[str, str] = Field(default_factory=dict)
    limit: int = Field(default=1000, ge=1, le=10000)


class MetricsResponse(BaseModel):
    """Response containing queried metrics."""

    agent_id: str = ""
    metric_name: str = ""
    data_points: list[dict[str, Any]] = Field(default_factory=list)
    aggregation: str = "avg"
    interval_seconds: int = 60


class AgentStatusResponse(BaseModel):
    """Agent status overview."""

    agent_id: str
    hostname: str = ""
    status: AgentStatus = AgentStatus.UNKNOWN
    last_seen: _dt.datetime | None = None
    uptime_seconds: float = 0.0
    labels: dict[str, str] = Field(default_factory=dict)
    latest_metrics: HostMetrics | None = None
