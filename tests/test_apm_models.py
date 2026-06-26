"""Tests for FaultRay APM Pydantic models."""

from __future__ import annotations

import datetime as _dt

import pytest
from pydantic import ValidationError

from faultray.apm.models import (
    AgentConfig,
    AgentHeartbeat,
    AgentRegistration,
    AgentStatus,
    AgentStatusResponse,
    Alert,
    AlertRule,
    AlertSeverity,
    AnomalyResult,
    ConnectionInfo,
    HostMetrics,
    MetricPoint,
    MetricsBatch,
    MetricsQuery,
    MetricsResponse,
    MetricType,
    ProcessInfo,
    TraceSpan,
)


class TestMetricPoint:
    def test_defaults(self) -> None:
        mp = MetricPoint(name="cpu", value=42.0)
        assert mp.name == "cpu"
        assert mp.value == 42.0
        assert mp.metric_type == MetricType.GAUGE
        assert mp.tags == {}
        assert mp.timestamp is not None

    def test_with_tags(self) -> None:
        mp = MetricPoint(name="req_count", value=100, metric_type=MetricType.COUNTER, tags={"env": "prod"})
        assert mp.tags == {"env": "prod"}
        assert mp.metric_type == MetricType.COUNTER


class TestHostMetrics:
    def test_defaults(self) -> None:
        hm = HostMetrics()
        assert hm.cpu_percent == 0.0
        assert hm.cpu_count == 1
        assert hm.memory_total_mb == 0.0

    def test_with_values(self) -> None:
        hm = HostMetrics(cpu_percent=75.5, memory_percent=60.0, disk_percent=40.0)
        assert hm.cpu_percent == 75.5


class TestProcessInfo:
    def test_basic(self) -> None:
        p = ProcessInfo(pid=1234, name="python", cpu_percent=5.0)
        assert p.pid == 1234
        assert p.connections == []

    def test_with_connections(self) -> None:
        conn = ConnectionInfo(local_addr="127.0.0.1", local_port=8080, status="LISTEN")
        p = ProcessInfo(pid=1, name="nginx", connections=[conn])
        assert len(p.connections) == 1
        assert p.connections[0].local_port == 8080


class TestConnectionInfo:
    def test_defaults(self) -> None:
        c = ConnectionInfo()
        assert c.local_addr == ""
        assert c.pid is None


class TestTraceSpan:
    def test_defaults(self) -> None:
        ts = TraceSpan()
        assert ts.trace_id != ""
        assert ts.span_id != ""
        assert ts.duration_ms == 0.0

    def test_with_values(self) -> None:
        ts = TraceSpan(operation="GET /api", service="web", duration_ms=150.0, status_code=200)
        assert ts.operation == "GET /api"
        assert ts.status_code == 200


class TestAgentRegistration:
    def test_auto_id(self) -> None:
        reg = AgentRegistration(hostname="web-01")
        assert len(reg.agent_id) == 12
        assert reg.hostname == "web-01"


class TestAgentHeartbeat:
    def test_basic(self) -> None:
        hb = AgentHeartbeat(agent_id="abc123")
        assert hb.status == AgentStatus.RUNNING


class TestMetricsBatch:
    def test_minimal(self) -> None:
        batch = MetricsBatch(agent_id="a1")
        assert batch.host_metrics is None
        assert batch.processes == []

    def test_with_host_metrics(self) -> None:
        hm = HostMetrics(cpu_percent=50.0)
        batch = MetricsBatch(agent_id="a1", host_metrics=hm)
        assert batch.host_metrics is not None
        assert batch.host_metrics.cpu_percent == 50.0

    def test_serialization_roundtrip(self) -> None:
        hm = HostMetrics(cpu_percent=42.0, memory_percent=60.0)
        batch = MetricsBatch(agent_id="a1", host_metrics=hm)
        json_str = batch.model_dump_json()
        restored = MetricsBatch.model_validate_json(json_str)
        assert restored.agent_id == "a1"
        assert restored.host_metrics is not None
        assert restored.host_metrics.cpu_percent == 42.0

    def test_aggregate_connections_cap_rejects_product(self) -> None:
        # SEC (DoS): the per-list cap bounds each connections list but not the
        # processes x connections PRODUCT. The aggregate budget must reject a
        # batch whose total nested connections exceed _MAX_TOTAL_CONNECTIONS,
        # before tens of millions of nested objects are constructed/flattened.
        from faultray.apm.models import _MAX_TOTAL_CONNECTIONS

        per_proc = 600
        n_procs = (_MAX_TOTAL_CONNECTIONS // per_proc) + 5  # total > limit
        procs = [
            {"pid": i, "connections": [{"local_port": 1} for _ in range(per_proc)]}
            for i in range(n_procs)
        ]
        with pytest.raises(ValidationError, match="too many connections"):
            MetricsBatch(agent_id="a1", processes=procs)

    def test_aggregate_connections_cap_allows_normal_batch(self) -> None:
        procs = [
            {"pid": i, "connections": [{"local_port": 1} for _ in range(20)]}
            for i in range(50)
        ]
        batch = MetricsBatch(agent_id="a1", processes=procs)
        assert sum(len(p.connections) for p in batch.processes) == 1000


class TestAlertRule:
    def test_defaults(self) -> None:
        rule = AlertRule(name="test", metric_name="cpu")
        assert rule.condition == "gt"
        assert rule.severity == AlertSeverity.WARNING
        assert rule.enabled is True

    def test_custom(self) -> None:
        rule = AlertRule(
            name="low_disk",
            metric_name="disk_free_gb",
            condition="lt",
            threshold=10.0,
            severity=AlertSeverity.CRITICAL,
        )
        assert rule.condition == "lt"
        assert rule.severity == AlertSeverity.CRITICAL


class TestAlert:
    def test_defaults(self) -> None:
        a = Alert()
        assert a.alert_id != ""
        assert a.severity == AlertSeverity.WARNING
        assert a.resolved_at is None


class TestAnomalyResult:
    def test_basic(self) -> None:
        ar = AnomalyResult(metric_name="cpu", current_value=95.0, is_anomaly=True)
        assert ar.is_anomaly is True


class TestAgentConfig:
    def test_defaults(self) -> None:
        cfg = AgentConfig()
        assert cfg.collector_url == "http://localhost:8080"
        assert cfg.collect_interval_seconds == 15
        assert cfg.collect_processes is True
        assert cfg.collect_connections is True
        assert cfg.collect_traces is False


class TestMetricsQuery:
    def test_defaults(self) -> None:
        q = MetricsQuery()
        assert q.aggregation == "avg"
        assert q.limit == 1000


class TestMetricsResponse:
    def test_basic(self) -> None:
        r = MetricsResponse(agent_id="a1", metric_name="cpu")
        assert r.data_points == []


class TestAgentStatusResponse:
    def test_basic(self) -> None:
        r = AgentStatusResponse(agent_id="a1")
        assert r.status == AgentStatus.UNKNOWN
