"""Tests for the OTel Simulation Exporter module.

Covers all enums, data models, exporter logic, serialisation, and the full
pipeline to achieve 100% code coverage.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.otel_exporter import (
    MetricType,
    OTelExportConfig,
    OTelExportResult,
    OTelSignalType,
    OTelSimulationExporter,
    SimulationLog,
    SimulationMetric,
    SimulationSpan,
    SpanStatus,
    _health_to_severity,
    _new_span_id,
    _new_trace_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ===================================================================
# 1. OTelSignalType enum
# ===================================================================


class TestOTelSignalTypeEnum:
    def test_trace_value(self):
        assert OTelSignalType.TRACE == "trace"

    def test_metric_value(self):
        assert OTelSignalType.METRIC == "metric"

    def test_log_value(self):
        assert OTelSignalType.LOG == "log"

    def test_member_count(self):
        assert len(OTelSignalType) == 3

    def test_str_mixin(self):
        assert isinstance(OTelSignalType.TRACE, str)

    def test_iteration(self):
        values = [s.value for s in OTelSignalType]
        assert "trace" in values
        assert "metric" in values
        assert "log" in values


# ===================================================================
# 2. MetricType enum
# ===================================================================


class TestMetricTypeEnum:
    def test_gauge(self):
        assert MetricType.GAUGE == "gauge"

    def test_counter(self):
        assert MetricType.COUNTER == "counter"

    def test_histogram(self):
        assert MetricType.HISTOGRAM == "histogram"

    def test_member_count(self):
        assert len(MetricType) == 3

    def test_str_mixin(self):
        assert isinstance(MetricType.GAUGE, str)

    def test_iteration(self):
        values = [m.value for m in MetricType]
        assert set(values) == {"gauge", "counter", "histogram"}


# ===================================================================
# 3. SpanStatus enum
# ===================================================================


class TestSpanStatusEnum:
    def test_ok(self):
        assert SpanStatus.OK == "ok"

    def test_error(self):
        assert SpanStatus.ERROR == "error"

    def test_unset(self):
        assert SpanStatus.UNSET == "unset"

    def test_member_count(self):
        assert len(SpanStatus) == 3

    def test_str_mixin(self):
        assert isinstance(SpanStatus.OK, str)

    def test_iteration(self):
        values = [s.value for s in SpanStatus]
        assert set(values) == {"ok", "error", "unset"}


# ===================================================================
# 4. SimulationSpan model
# ===================================================================


class TestSimulationSpan:
    def test_minimal_creation(self):
        now = datetime.now(timezone.utc)
        s = SimulationSpan(
            trace_id="a" * 32,
            span_id="b" * 16,
            operation_name="test.op",
            service_name="svc",
            start_time=now,
            end_time=now + timedelta(seconds=1),
        )
        assert s.trace_id == "a" * 32
        assert s.span_id == "b" * 16
        assert s.parent_span_id is None
        assert s.status == SpanStatus.UNSET
        assert s.attributes == {}
        assert s.events == []

    def test_full_creation(self):
        now = datetime.now(timezone.utc)
        s = SimulationSpan(
            trace_id="t" * 32,
            span_id="s" * 16,
            parent_span_id="p" * 16,
            operation_name="op",
            service_name="svc",
            start_time=now,
            end_time=now + timedelta(seconds=2),
            status=SpanStatus.ERROR,
            attributes={"key": "val", "num": 42},
            events=[{"name": "evt"}],
        )
        assert s.parent_span_id == "p" * 16
        assert s.status == SpanStatus.ERROR
        assert s.attributes["key"] == "val"
        assert len(s.events) == 1

    def test_defaults_are_independent(self):
        now = datetime.now(timezone.utc)
        s1 = SimulationSpan(
            trace_id="a" * 32, span_id="b" * 16,
            operation_name="op", service_name="s",
            start_time=now, end_time=now,
        )
        s2 = SimulationSpan(
            trace_id="c" * 32, span_id="d" * 16,
            operation_name="op2", service_name="s2",
            start_time=now, end_time=now,
        )
        s1.attributes["x"] = 1
        assert "x" not in s2.attributes

    def test_span_serialisation_roundtrip(self):
        now = datetime.now(timezone.utc)
        s = SimulationSpan(
            trace_id="aa" * 16, span_id="bb" * 8,
            operation_name="op", service_name="svc",
            start_time=now, end_time=now,
        )
        d = s.model_dump()
        s2 = SimulationSpan(**d)
        assert s2.trace_id == s.trace_id


# ===================================================================
# 5. SimulationMetric model
# ===================================================================


class TestSimulationMetric:
    def test_creation(self):
        now = datetime.now(timezone.utc)
        m = SimulationMetric(
            name="cpu", description="CPU usage",
            metric_type=MetricType.GAUGE,
            value=75.5, unit="percent",
            timestamp=now,
        )
        assert m.name == "cpu"
        assert m.metric_type == MetricType.GAUGE
        assert m.value == 75.5
        assert m.labels == {}

    def test_with_labels(self):
        now = datetime.now(timezone.utc)
        m = SimulationMetric(
            name="rps", description="requests per second",
            metric_type=MetricType.COUNTER,
            value=100, unit="req/s",
            timestamp=now, labels={"env": "prod"},
        )
        assert m.labels["env"] == "prod"

    def test_histogram_type(self):
        now = datetime.now(timezone.utc)
        m = SimulationMetric(
            name="latency", description="req latency",
            metric_type=MetricType.HISTOGRAM,
            value=12.3, unit="ms", timestamp=now,
        )
        assert m.metric_type == MetricType.HISTOGRAM

    def test_metric_serialisation_roundtrip(self):
        now = datetime.now(timezone.utc)
        m = SimulationMetric(
            name="n", description="d", metric_type=MetricType.GAUGE,
            value=1.0, unit="u", timestamp=now,
        )
        d = m.model_dump()
        m2 = SimulationMetric(**d)
        assert m2.name == m.name


# ===================================================================
# 6. SimulationLog model
# ===================================================================


class TestSimulationLog:
    def test_creation(self):
        now = datetime.now(timezone.utc)
        lg = SimulationLog(
            timestamp=now, severity="INFO",
            body="hello", service_name="svc",
        )
        assert lg.severity == "INFO"
        assert lg.body == "hello"
        assert lg.attributes == {}

    def test_with_attributes(self):
        now = datetime.now(timezone.utc)
        lg = SimulationLog(
            timestamp=now, severity="ERROR",
            body="fail", service_name="svc",
            attributes={"err": True, "code": 500},
        )
        assert lg.attributes["err"] is True
        assert lg.attributes["code"] == 500

    def test_log_serialisation_roundtrip(self):
        now = datetime.now(timezone.utc)
        lg = SimulationLog(
            timestamp=now, severity="WARN",
            body="b", service_name="s",
        )
        d = lg.model_dump()
        lg2 = SimulationLog(**d)
        assert lg2.body == lg.body


# ===================================================================
# 7. OTelExportConfig model
# ===================================================================


class TestOTelExportConfig:
    def test_defaults(self):
        c = OTelExportConfig()
        assert c.endpoint == ""
        assert c.protocol == "grpc"
        assert c.headers == {}
        assert c.batch_size == 100
        assert c.export_traces is True
        assert c.export_metrics is True
        assert c.export_logs is True

    def test_custom_values(self):
        c = OTelExportConfig(
            endpoint="http://localhost:4317",
            protocol="http",
            headers={"Authorization": "Bearer tok"},
            batch_size=50,
            export_traces=False,
            export_metrics=False,
            export_logs=False,
        )
        assert c.endpoint == "http://localhost:4317"
        assert c.protocol == "http"
        assert c.batch_size == 50
        assert c.export_traces is False
        assert c.export_metrics is False
        assert c.export_logs is False

    def test_partial_override(self):
        c = OTelExportConfig(export_logs=False)
        assert c.export_traces is True
        assert c.export_logs is False


# ===================================================================
# 8. OTelExportResult model
# ===================================================================


class TestOTelExportResult:
    def test_defaults(self):
        r = OTelExportResult()
        assert r.spans_generated == 0
        assert r.metrics_generated == 0
        assert r.logs_generated == 0
        assert r.export_format == "otlp_json"
        assert r.payload_size_bytes == 0

    def test_custom_values(self):
        r = OTelExportResult(
            spans_generated=10,
            metrics_generated=20,
            logs_generated=5,
            export_format="otlp_json",
            payload_size_bytes=1234,
        )
        assert r.spans_generated == 10
        assert r.payload_size_bytes == 1234


# ===================================================================
# 9. Helper functions
# ===================================================================


class TestNewTraceId:
    def test_length(self):
        tid = _new_trace_id()
        assert len(tid) == 32

    def test_hex_chars(self):
        tid = _new_trace_id()
        int(tid, 16)  # should not raise

    def test_unique(self):
        ids = {_new_trace_id() for _ in range(100)}
        assert len(ids) == 100


class TestNewSpanId:
    def test_length(self):
        sid = _new_span_id()
        assert len(sid) == 16

    def test_hex_chars(self):
        sid = _new_span_id()
        int(sid, 16)

    def test_unique(self):
        ids = {_new_span_id() for _ in range(100)}
        assert len(ids) == 100


class TestHealthToSeverity:
    def test_healthy(self):
        assert _health_to_severity("healthy") == "INFO"

    def test_degraded(self):
        assert _health_to_severity("degraded") == "WARN"

    def test_overloaded(self):
        assert _health_to_severity("overloaded") == "WARN"

    def test_down(self):
        assert _health_to_severity("down") == "ERROR"

    def test_unknown(self):
        assert _health_to_severity("something_else") == "INFO"

    def test_empty_string(self):
        assert _health_to_severity("") == "INFO"


# ===================================================================
# 10. OTelSimulationExporter — __init__
# ===================================================================


class TestExporterInit:
    def test_default_config(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        assert exp.config.endpoint == ""
        assert exp.config.protocol == "grpc"

    def test_custom_config(self):
        g = _graph()
        cfg = OTelExportConfig(endpoint="http://otel:4317")
        exp = OTelSimulationExporter(g, config=cfg)
        assert exp.config.endpoint == "http://otel:4317"

    def test_graph_reference(self):
        c = _comp("a", "Alpha")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        assert exp.graph.get_component("a") is not None


# ===================================================================
# 11. generate_trace
# ===================================================================


class TestGenerateTrace:
    def test_empty_affected(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("s1", [], 100.0, True)
        assert len(spans) == 1
        root = spans[0]
        assert root.parent_span_id is None
        assert root.status == SpanStatus.OK
        assert "s1" in root.operation_name

    def test_single_component(self):
        c = _comp("web", "WebServer")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("failover", ["web"], 200.0, True)
        assert len(spans) == 2
        root, child = spans[0], spans[1]
        assert child.parent_span_id == root.span_id
        assert child.trace_id == root.trace_id
        assert child.service_name == "WebServer"

    def test_multiple_components(self):
        c1 = _comp("a", "A")
        c2 = _comp("b", "B")
        c3 = _comp("c", "C")
        g = _graph(c1, c2, c3)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("cascade", ["a", "b", "c"], 300.0, False)
        assert len(spans) == 4
        root = spans[0]
        assert root.status == SpanStatus.ERROR
        for child in spans[1:]:
            assert child.parent_span_id == root.span_id

    def test_unhealthy_component_generates_error_span(self):
        c = _comp("db", "Database", health=HealthStatus.DOWN)
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("db-fail", ["db"], 50.0, False)
        child = spans[1]
        assert child.status == SpanStatus.ERROR
        assert len(child.events) == 1
        assert child.events[0]["name"] == "health_degraded"

    def test_degraded_component_generates_error_span(self):
        c = _comp("cache", "Cache", health=HealthStatus.DEGRADED)
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("degrade", ["cache"], 100.0, True)
        child = spans[1]
        assert child.status == SpanStatus.ERROR
        assert child.events[0]["attributes"]["health"] == "degraded"

    def test_overloaded_component_generates_error_span(self):
        c = _comp("api", "API", health=HealthStatus.OVERLOADED)
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("overload", ["api"], 100.0, True)
        child = spans[1]
        assert child.status == SpanStatus.ERROR

    def test_healthy_component_generates_ok_span(self):
        c = _comp("web", "Web", health=HealthStatus.HEALTHY)
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("check", ["web"], 100.0, True)
        child = spans[1]
        assert child.status == SpanStatus.OK
        assert child.events == []

    def test_unknown_component_id(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("missing", ["no_exist"], 100.0, True)
        assert len(spans) == 2
        child = spans[1]
        assert child.service_name == "no_exist"
        assert child.attributes["component.type"] == "unknown"

    def test_trace_ids_are_consistent(self):
        c = _comp("x", "X")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("t", ["x"], 50.0, True)
        tid = spans[0].trace_id
        for s in spans:
            assert s.trace_id == tid

    def test_span_ids_are_unique(self):
        c1 = _comp("a", "A")
        c2 = _comp("b", "B")
        g = _graph(c1, c2)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("t", ["a", "b"], 100.0, True)
        ids = [s.span_id for s in spans]
        assert len(ids) == len(set(ids))

    def test_root_span_attributes(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("sc", ["a", "b"], 100.0, True)
        root = spans[0]
        assert root.attributes["faultray.scenario"] == "sc"
        assert root.attributes["faultray.success"] is True
        assert root.attributes["faultray.affected_count"] == 2

    def test_child_span_timing_sequential(self):
        c1 = _comp("a", "A")
        c2 = _comp("b", "B")
        g = _graph(c1, c2)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("t", ["a", "b"], 200.0, True)
        # child spans should be sequential
        assert spans[1].start_time <= spans[2].start_time

    def test_child_span_operation_name(self):
        c = _comp("svc1", "Service1")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("run", ["svc1"], 100.0, True)
        assert spans[1].operation_name == "component.evaluate.svc1"

    def test_root_span_operation_name(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("my_scenario", [], 10.0, True)
        assert spans[0].operation_name == "simulation.my_scenario"

    def test_root_span_service_name(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("s", [], 10.0, True)
        assert spans[0].service_name == "faultray-simulator"

    def test_success_true_ok(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("s", [], 10.0, True)
        assert spans[0].status == SpanStatus.OK

    def test_success_false_error(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("s", [], 10.0, False)
        assert spans[0].status == SpanStatus.ERROR

    def test_child_component_type_attribute(self):
        c = _comp("db", "DB", ctype=ComponentType.DATABASE)
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("t", ["db"], 10.0, True)
        assert spans[1].attributes["component.type"] == "database"

    def test_child_component_id_attribute(self):
        c = _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER)
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("t", ["lb"], 10.0, True)
        assert spans[1].attributes["component.id"] == "lb"


# ===================================================================
# 12. generate_metrics
# ===================================================================


class TestGenerateMetrics:
    def test_returns_three_metrics(self):
        c = _comp("web", "Web")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("web", "healthy", 55.0)
        assert len(metrics) == 3

    def test_health_metric_healthy(self):
        c = _comp("w", "W")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("w", "healthy", 0.0)
        health_m = metrics[0]
        assert health_m.name == "faultray.component.health"
        assert health_m.value == 2.0
        assert health_m.metric_type == MetricType.GAUGE

    def test_health_metric_degraded(self):
        c = _comp("w", "W")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("w", "degraded", 0.0)
        assert metrics[0].value == 1.0

    def test_health_metric_overloaded(self):
        c = _comp("w", "W")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("w", "overloaded", 0.0)
        assert metrics[0].value == 1.0

    def test_health_metric_down(self):
        c = _comp("w", "W")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("w", "down", 0.0)
        assert metrics[0].value == 0.0

    def test_health_metric_unknown_status(self):
        c = _comp("w", "W")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("w", "banana", 0.0)
        assert metrics[0].value == 2.0  # default

    def test_utilization_metric(self):
        c = _comp("w", "W")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("w", "healthy", 88.8)
        util_m = metrics[1]
        assert util_m.name == "faultray.component.utilization"
        assert util_m.value == 88.8
        assert util_m.unit == "percent"

    def test_events_counter_metric(self):
        c = _comp("w", "W")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("w", "healthy", 0.0)
        counter_m = metrics[2]
        assert counter_m.name == "faultray.simulation.events"
        assert counter_m.value == 1.0
        assert counter_m.metric_type == MetricType.COUNTER

    def test_labels_contain_component_id(self):
        c = _comp("svc1", "Service1")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("svc1", "healthy", 0.0)
        for m in metrics:
            assert m.labels["component_id"] == "svc1"

    def test_labels_contain_service_name(self):
        c = _comp("svc1", "Service1")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("svc1", "healthy", 0.0)
        for m in metrics:
            assert m.labels["service"] == "Service1"

    def test_labels_contain_component_type(self):
        c = _comp("db", "DB", ctype=ComponentType.DATABASE)
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("db", "healthy", 0.0)
        assert metrics[0].labels["component_type"] == "database"

    def test_unknown_component_fallback(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("ghost", "healthy", 0.0)
        assert len(metrics) == 3
        assert metrics[0].labels["service"] == "ghost"
        assert "component_type" not in metrics[0].labels

    def test_metric_timestamps_are_utc(self):
        c = _comp("x", "X")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("x", "healthy", 0.0)
        for m in metrics:
            assert m.timestamp.tzinfo is not None


# ===================================================================
# 13. generate_logs
# ===================================================================


class TestGenerateLogs:
    def test_empty_events(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        logs = exp.generate_logs("a", [])
        assert logs == []

    def test_single_event(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        logs = exp.generate_logs("a", ["started"])
        assert len(logs) == 1
        assert logs[0].body == "started"
        assert logs[0].service_name == "A"

    def test_multiple_events(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        logs = exp.generate_logs("a", ["e1", "e2", "e3"])
        assert len(logs) == 3

    def test_default_severity(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        logs = exp.generate_logs("a", ["x"])
        assert logs[0].severity == "INFO"

    def test_custom_severity(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        logs = exp.generate_logs("a", ["crash"], severity="ERROR")
        assert logs[0].severity == "ERROR"

    def test_log_attributes(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        logs = exp.generate_logs("a", ["ev1", "ev2"])
        assert logs[0].attributes["component.id"] == "a"
        assert logs[0].attributes["event.index"] == 0
        assert logs[1].attributes["event.index"] == 1

    def test_unknown_component_fallback(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        logs = exp.generate_logs("missing", ["msg"])
        assert logs[0].service_name == "missing"

    def test_log_timestamps_increment(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        logs = exp.generate_logs("a", ["e1", "e2", "e3"])
        for i in range(len(logs) - 1):
            assert logs[i].timestamp <= logs[i + 1].timestamp


# ===================================================================
# 14. export_to_json
# ===================================================================


class TestExportToJson:
    def test_empty_inputs(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        result = exp.export_to_json([], [], [])
        assert result == {
            "resourceSpans": [],
            "resourceMetrics": [],
            "resourceLogs": [],
        }

    def test_span_serialisation(self):
        now = datetime.now(timezone.utc)
        span = SimulationSpan(
            trace_id="a" * 32, span_id="b" * 16,
            operation_name="op", service_name="svc",
            start_time=now, end_time=now + timedelta(seconds=1),
            status=SpanStatus.OK,
        )
        g = _graph()
        exp = OTelSimulationExporter(g)
        result = exp.export_to_json([span], [], [])
        rs = result["resourceSpans"]
        assert len(rs) == 1
        assert rs[0]["traceId"] == "a" * 32
        assert rs[0]["spanId"] == "b" * 16
        assert rs[0]["status"]["code"] == "ok"
        assert "parentSpanId" not in rs[0]

    def test_span_with_parent(self):
        now = datetime.now(timezone.utc)
        span = SimulationSpan(
            trace_id="a" * 32, span_id="b" * 16,
            parent_span_id="p" * 16,
            operation_name="op", service_name="svc",
            start_time=now, end_time=now,
        )
        g = _graph()
        exp = OTelSimulationExporter(g)
        result = exp.export_to_json([span], [], [])
        assert result["resourceSpans"][0]["parentSpanId"] == "p" * 16

    def test_metric_serialisation(self):
        now = datetime.now(timezone.utc)
        metric = SimulationMetric(
            name="cpu", description="CPU", metric_type=MetricType.GAUGE,
            value=50.0, unit="percent", timestamp=now,
            labels={"env": "test"},
        )
        g = _graph()
        exp = OTelSimulationExporter(g)
        result = exp.export_to_json([], [metric], [])
        rm = result["resourceMetrics"]
        assert len(rm) == 1
        assert rm[0]["name"] == "cpu"
        assert rm[0]["type"] == "gauge"
        assert rm[0]["labels"]["env"] == "test"

    def test_log_serialisation(self):
        now = datetime.now(timezone.utc)
        lg = SimulationLog(
            timestamp=now, severity="WARN",
            body="timeout", service_name="svc",
            attributes={"x": 1},
        )
        g = _graph()
        exp = OTelSimulationExporter(g)
        result = exp.export_to_json([], [], [lg])
        rl = result["resourceLogs"]
        assert len(rl) == 1
        assert rl[0]["severityText"] == "WARN"
        assert rl[0]["body"] == "timeout"
        assert rl[0]["serviceName"] == "svc"

    def test_combined(self):
        now = datetime.now(timezone.utc)
        span = SimulationSpan(
            trace_id="a" * 32, span_id="b" * 16,
            operation_name="op", service_name="svc",
            start_time=now, end_time=now,
        )
        metric = SimulationMetric(
            name="n", description="d", metric_type=MetricType.COUNTER,
            value=1.0, unit="u", timestamp=now,
        )
        lg = SimulationLog(
            timestamp=now, severity="INFO",
            body="ok", service_name="s",
        )
        g = _graph()
        exp = OTelSimulationExporter(g)
        result = exp.export_to_json([span], [metric], [lg])
        assert len(result["resourceSpans"]) == 1
        assert len(result["resourceMetrics"]) == 1
        assert len(result["resourceLogs"]) == 1

    def test_unix_nano_timestamps(self):
        now = datetime.now(timezone.utc)
        span = SimulationSpan(
            trace_id="a" * 32, span_id="b" * 16,
            operation_name="op", service_name="svc",
            start_time=now, end_time=now,
        )
        g = _graph()
        exp = OTelSimulationExporter(g)
        result = exp.export_to_json([span], [], [])
        start_ns = result["resourceSpans"][0]["startTimeUnixNano"]
        assert isinstance(start_ns, int)
        assert start_ns > 0

    def test_json_serialisable(self):
        now = datetime.now(timezone.utc)
        span = SimulationSpan(
            trace_id="a" * 32, span_id="b" * 16,
            operation_name="op", service_name="svc",
            start_time=now, end_time=now,
            attributes={"k": "v", "n": 42, "f": 1.5, "b": True},
            events=[{"name": "e1"}],
        )
        metric = SimulationMetric(
            name="n", description="d", metric_type=MetricType.GAUGE,
            value=1.0, unit="u", timestamp=now,
        )
        lg = SimulationLog(
            timestamp=now, severity="INFO", body="b", service_name="s",
        )
        g = _graph()
        exp = OTelSimulationExporter(g)
        result = exp.export_to_json([span], [metric], [lg])
        serialised = json.dumps(result)
        assert isinstance(serialised, str)
        assert len(serialised) > 0


# ===================================================================
# 15. generate_simulation_telemetry — full pipeline
# ===================================================================


class TestGenerateSimulationTelemetry:
    def test_empty_results(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        result = exp.generate_simulation_telemetry([])
        assert result.spans_generated == 0
        assert result.metrics_generated == 0
        assert result.logs_generated == 0
        assert result.export_format == "otlp_json"
        assert result.payload_size_bytes > 0  # empty JSON still has bytes

    def test_single_scenario(self):
        c = _comp("web", "Web")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "failover",
            "affected_components": ["web"],
            "duration_ms": 100.0,
            "success": True,
            "health_status": "healthy",
            "utilization": 50.0,
            "events": ["started", "completed"],
        }])
        assert res.spans_generated == 2  # root + 1 child
        assert res.metrics_generated == 3
        assert res.logs_generated == 2
        assert res.payload_size_bytes > 0

    def test_multiple_scenarios(self):
        c1 = _comp("a", "A")
        c2 = _comp("b", "B")
        g = _graph(c1, c2)
        exp = OTelSimulationExporter(g)
        res = exp.generate_simulation_telemetry([
            {
                "scenario_name": "s1",
                "affected_components": ["a"],
                "duration_ms": 50.0,
                "success": True,
                "events": ["e1"],
            },
            {
                "scenario_name": "s2",
                "affected_components": ["b"],
                "duration_ms": 80.0,
                "success": False,
                "events": ["e2"],
            },
        ])
        # 2 roots + 2 children = 4 spans
        assert res.spans_generated == 4
        assert res.metrics_generated == 6  # 3 per component
        assert res.logs_generated == 2

    def test_scenario_multiple_affected(self):
        c1 = _comp("a", "A")
        c2 = _comp("b", "B")
        g = _graph(c1, c2)
        exp = OTelSimulationExporter(g)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "cascade",
            "affected_components": ["a", "b"],
            "duration_ms": 200.0,
            "success": False,
            "events": ["evt"],
        }])
        assert res.spans_generated == 3  # root + 2 children
        assert res.metrics_generated == 6  # 3 per component * 2
        assert res.logs_generated == 2    # 1 event * 2 components

    def test_no_events_no_logs(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "s",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": True,
        }])
        assert res.logs_generated == 0

    def test_disable_traces(self):
        c = _comp("a", "A")
        g = _graph(c)
        cfg = OTelExportConfig(export_traces=False)
        exp = OTelSimulationExporter(g, config=cfg)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "s",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": True,
            "events": ["e"],
        }])
        assert res.spans_generated == 0
        assert res.metrics_generated == 3
        assert res.logs_generated == 1

    def test_disable_metrics(self):
        c = _comp("a", "A")
        g = _graph(c)
        cfg = OTelExportConfig(export_metrics=False)
        exp = OTelSimulationExporter(g, config=cfg)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "s",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": True,
            "events": ["e"],
        }])
        assert res.spans_generated == 2
        assert res.metrics_generated == 0
        assert res.logs_generated == 1

    def test_disable_logs(self):
        c = _comp("a", "A")
        g = _graph(c)
        cfg = OTelExportConfig(export_logs=False)
        exp = OTelSimulationExporter(g, config=cfg)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "s",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": True,
            "events": ["e"],
        }])
        assert res.spans_generated == 2
        assert res.metrics_generated == 3
        assert res.logs_generated == 0

    def test_disable_all(self):
        c = _comp("a", "A")
        g = _graph(c)
        cfg = OTelExportConfig(
            export_traces=False, export_metrics=False, export_logs=False,
        )
        exp = OTelSimulationExporter(g, config=cfg)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "s",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": True,
            "events": ["e"],
        }])
        assert res.spans_generated == 0
        assert res.metrics_generated == 0
        assert res.logs_generated == 0

    def test_default_health_status(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "s",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": True,
        }])
        assert res.metrics_generated == 3

    def test_default_utilization(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "s",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": True,
        }])
        assert res.metrics_generated > 0

    def test_default_scenario_name(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        res = exp.generate_simulation_telemetry([{}])
        assert res.spans_generated == 1  # just root span

    def test_payload_size_positive(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "s",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": True,
            "events": ["e"],
        }])
        assert res.payload_size_bytes > 100

    def test_health_severity_mapping_in_pipeline(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        # down -> ERROR severity
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "s",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": False,
            "health_status": "down",
            "events": ["crash"],
        }])
        assert res.logs_generated == 1

    def test_no_affected_components(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "noop",
            "affected_components": [],
            "duration_ms": 10.0,
            "success": True,
            "events": ["e"],
        }])
        assert res.spans_generated == 1  # root only
        assert res.metrics_generated == 0
        assert res.logs_generated == 0

    def test_export_format_always_otlp_json(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        res = exp.generate_simulation_telemetry([])
        assert res.export_format == "otlp_json"

    def test_large_batch(self):
        comps = [_comp(f"c{i}", f"C{i}") for i in range(10)]
        g = _graph(*comps)
        exp = OTelSimulationExporter(g)
        scenarios = [
            {
                "scenario_name": f"s{i}",
                "affected_components": [f"c{j}" for j in range(10)],
                "duration_ms": 100.0,
                "success": i % 2 == 0,
                "events": [f"event_{i}"],
            }
            for i in range(5)
        ]
        res = exp.generate_simulation_telemetry(scenarios)
        # 5 scenarios * (1 root + 10 children) = 55 spans
        assert res.spans_generated == 55
        # 5 scenarios * 10 components * 3 metrics = 150
        assert res.metrics_generated == 150
        # 5 scenarios * 10 components * 1 event = 50
        assert res.logs_generated == 50


# ===================================================================
# 16. Edge cases and integration
# ===================================================================


class TestEdgeCases:
    def test_zero_duration(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("s", [], 0.0, True)
        assert spans[0].start_time == spans[0].end_time

    def test_very_large_duration(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("s", [], 1_000_000.0, True)
        diff = (spans[0].end_time - spans[0].start_time).total_seconds()
        assert diff == pytest.approx(1000.0, abs=1)

    def test_special_characters_in_scenario_name(self):
        g = _graph()
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("fail/over-test.v2", [], 10.0, True)
        assert "fail/over-test.v2" in spans[0].operation_name

    def test_special_characters_in_events(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        logs = exp.generate_logs("a", ['error: "timeout"', "line\nnewline"])
        assert len(logs) == 2
        assert '"timeout"' in logs[0].body

    def test_unicode_in_events(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        logs = exp.generate_logs("a", ["component crashed"])
        assert len(logs) == 1

    def test_many_events_generate_many_logs(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        events = [f"event_{i}" for i in range(50)]
        logs = exp.generate_logs("a", events)
        assert len(logs) == 50

    def test_utilization_zero(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("a", "healthy", 0.0)
        assert metrics[1].value == 0.0

    def test_utilization_hundred(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("a", "healthy", 100.0)
        assert metrics[1].value == 100.0

    def test_multiple_exports_independent(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        r1 = exp.generate_simulation_telemetry([{
            "scenario_name": "s1",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": True,
        }])
        r2 = exp.generate_simulation_telemetry([{
            "scenario_name": "s2",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": False,
        }])
        assert r1.spans_generated == r2.spans_generated

    def test_config_none_uses_defaults(self):
        g = _graph()
        exp = OTelSimulationExporter(g, config=None)
        assert exp.config.export_traces is True

    def test_graph_with_many_component_types(self):
        comps = [
            _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER),
            _comp("web", "Web", ctype=ComponentType.WEB_SERVER),
            _comp("app", "App", ctype=ComponentType.APP_SERVER),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
            _comp("cache", "Cache", ctype=ComponentType.CACHE),
            _comp("queue", "Queue", ctype=ComponentType.QUEUE),
        ]
        g = _graph(*comps)
        exp = OTelSimulationExporter(g)
        ids = [c.id for c in comps]
        spans = exp.generate_trace("full", ids, 600.0, True)
        assert len(spans) == 7  # root + 6 children

    def test_empty_events_list_no_logs_in_pipeline(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "s",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": True,
            "events": [],
        }])
        assert res.logs_generated == 0

    def test_metric_description_fields(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("a", "healthy", 50.0)
        descriptions = [m.description for m in metrics]
        assert any("health" in d.lower() for d in descriptions)
        assert any("utilization" in d.lower() for d in descriptions)
        assert any("simulation" in d.lower() or "count" in d.lower() or "events" in d.lower() for d in descriptions)

    def test_metric_units(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        metrics = exp.generate_metrics("a", "healthy", 50.0)
        units = [m.unit for m in metrics]
        assert "status" in units
        assert "percent" in units
        assert "count" in units

    def test_span_end_after_start(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        spans = exp.generate_trace("s", ["a"], 500.0, True)
        for s in spans:
            assert s.end_time >= s.start_time

    def test_export_to_json_multiple_spans(self):
        now = datetime.now(timezone.utc)
        spans = [
            SimulationSpan(
                trace_id="a" * 32, span_id=f"{i:016x}",
                operation_name=f"op{i}", service_name="svc",
                start_time=now, end_time=now,
            )
            for i in range(5)
        ]
        g = _graph()
        exp = OTelSimulationExporter(g)
        result = exp.export_to_json(spans, [], [])
        assert len(result["resourceSpans"]) == 5

    def test_pipeline_degraded_severity_logs(self):
        c = _comp("a", "A")
        g = _graph(c)
        exp = OTelSimulationExporter(g)
        res = exp.generate_simulation_telemetry([{
            "scenario_name": "s",
            "affected_components": ["a"],
            "duration_ms": 10.0,
            "success": True,
            "health_status": "degraded",
            "events": ["slowdown"],
        }])
        assert res.logs_generated == 1
