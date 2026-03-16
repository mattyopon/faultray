"""Tests for the Golden Signal Analyzer module.

Covers all classes, enums, analysis logic, edge cases, and report generation
to achieve 99%+ code coverage.
"""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.golden_signal_analyzer import (
    GoldenSignalAnalyzer,
    GoldenSignalReport,
    SignalReading,
    SignalStatus,
    SignalSummary,
    SignalThreshold,
    SignalType,
    _classify,
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
# 1. Enum values
# ===================================================================


class TestSignalTypeEnum:
    def test_values(self):
        assert SignalType.LATENCY == "latency"
        assert SignalType.TRAFFIC == "traffic"
        assert SignalType.ERRORS == "errors"
        assert SignalType.SATURATION == "saturation"

    def test_member_count(self):
        assert len(SignalType) == 4

    def test_str_mixin(self):
        assert isinstance(SignalType.LATENCY, str)


class TestSignalStatusEnum:
    def test_values(self):
        assert SignalStatus.HEALTHY == "healthy"
        assert SignalStatus.WARNING == "warning"
        assert SignalStatus.CRITICAL == "critical"

    def test_member_count(self):
        assert len(SignalStatus) == 3

    def test_str_mixin(self):
        assert isinstance(SignalStatus.HEALTHY, str)


# ===================================================================
# 2. Dataclass construction
# ===================================================================


class TestSignalThreshold:
    def test_basic(self):
        t = SignalThreshold(warning_threshold=10.0, critical_threshold=50.0, unit="ms")
        assert t.warning_threshold == 10.0
        assert t.critical_threshold == 50.0
        assert t.unit == "ms"


class TestSignalReading:
    def test_basic(self):
        t = SignalThreshold(200.0, 1000.0, "ms")
        r = SignalReading(
            component_id="c1",
            component_name="web",
            signal_type=SignalType.LATENCY,
            value=50.0,
            status=SignalStatus.HEALTHY,
            threshold=t,
            details="ok",
        )
        assert r.component_id == "c1"
        assert r.signal_type == SignalType.LATENCY
        assert r.status == SignalStatus.HEALTHY
        assert r.details == "ok"


class TestSignalSummary:
    def test_basic(self):
        s = SignalSummary(
            signal_type=SignalType.ERRORS,
            total_readings=5,
            healthy_count=4,
            warning_count=1,
            critical_count=0,
            worst_reading=None,
            average_value=1.5,
            recommendation="Check errors.",
        )
        assert s.total_readings == 5
        assert s.healthy_count == 4
        assert s.worst_reading is None


class TestGoldenSignalReport:
    def test_defaults(self):
        r = GoldenSignalReport()
        assert r.readings == []
        assert r.summaries == []
        assert r.overall_health == SignalStatus.HEALTHY
        assert r.total_components == 0
        assert r.signals_in_violation == 0
        assert r.top_issues == []
        assert r.recommendations == []
        assert r.summary == ""


# ===================================================================
# 3. _classify helper
# ===================================================================


class TestClassify:
    def test_healthy(self):
        t = SignalThreshold(70.0, 90.0, "%")
        assert _classify(0.0, t) == SignalStatus.HEALTHY
        assert _classify(69.9, t) == SignalStatus.HEALTHY

    def test_warning(self):
        t = SignalThreshold(70.0, 90.0, "%")
        assert _classify(70.0, t) == SignalStatus.WARNING
        assert _classify(89.9, t) == SignalStatus.WARNING

    def test_critical(self):
        t = SignalThreshold(70.0, 90.0, "%")
        assert _classify(90.0, t) == SignalStatus.CRITICAL
        assert _classify(100.0, t) == SignalStatus.CRITICAL


# ===================================================================
# 4. Empty graph
# ===================================================================


class TestEmptyGraph:
    def test_analyze_empty(self):
        g = _graph()
        report = GoldenSignalAnalyzer(g).analyze()
        assert report.total_components == 0
        assert report.readings == []
        assert report.summaries == []
        assert report.overall_health == SignalStatus.HEALTHY
        assert report.signals_in_violation == 0
        assert "No components" in report.summary

    def test_analyze_signal_empty(self):
        g = _graph()
        a = GoldenSignalAnalyzer(g)
        for st in SignalType:
            s = a.analyze_signal(st)
            assert s.total_readings == 0
            assert s.worst_reading is None
            assert s.average_value == 0.0


# ===================================================================
# 5. Single healthy component — all 4 signals HEALTHY
# ===================================================================


class TestSingleHealthyComponent:
    def setup_method(self):
        self.comp = _comp("web1", "WebServer", ComponentType.WEB_SERVER)
        self.graph = _graph(self.comp)
        self.report = GoldenSignalAnalyzer(self.graph).analyze()

    def test_total_components(self):
        assert self.report.total_components == 1

    def test_readings_count(self):
        assert len(self.report.readings) == 4

    def test_all_healthy(self):
        for r in self.report.readings:
            assert r.status == SignalStatus.HEALTHY

    def test_overall_healthy(self):
        assert self.report.overall_health == SignalStatus.HEALTHY

    def test_no_violations(self):
        assert self.report.signals_in_violation == 0

    def test_no_issues(self):
        assert self.report.top_issues == []

    def test_no_recommendations(self):
        assert self.report.recommendations == []

    def test_summary_string(self):
        assert "1 components" in self.report.summary
        assert "HEALTHY" in self.report.summary


# ===================================================================
# 6. Latency analysis — all health states x component types
# ===================================================================


class TestLatencyByHealth:
    @pytest.mark.parametrize(
        "health, expected_status",
        [
            (HealthStatus.HEALTHY, SignalStatus.HEALTHY),
            (HealthStatus.DEGRADED, SignalStatus.WARNING),
            (HealthStatus.OVERLOADED, SignalStatus.CRITICAL),
            (HealthStatus.DOWN, SignalStatus.CRITICAL),
        ],
    )
    def test_latency_status_per_health(self, health, expected_status):
        c = _comp("c1", "comp", ComponentType.APP_SERVER, health=health)
        g = _graph(c)
        a = GoldenSignalAnalyzer(g)
        r = a._analyze_latency(c)
        assert r.status == expected_status
        assert r.signal_type == SignalType.LATENCY

    def test_healthy_base_value(self):
        c = _comp("c1", "comp", ComponentType.APP_SERVER, health=HealthStatus.HEALTHY)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 50.0  # base * 1.0

    def test_degraded_base_value(self):
        c = _comp("c1", "comp", ComponentType.APP_SERVER, health=HealthStatus.DEGRADED)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 500.0

    def test_overloaded_base_value(self):
        c = _comp("c1", "comp", ComponentType.APP_SERVER, health=HealthStatus.OVERLOADED)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 2000.0

    def test_down_base_value(self):
        c = _comp("c1", "comp", ComponentType.APP_SERVER, health=HealthStatus.DOWN)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 9999.0


class TestLatencyByType:
    def test_database_multiplier(self):
        c = _comp("db1", "DB", ComponentType.DATABASE, health=HealthStatus.HEALTHY)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 50.0 * 1.5  # 75.0

    def test_external_api_multiplier(self):
        c = _comp("api1", "API", ComponentType.EXTERNAL_API, health=HealthStatus.HEALTHY)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 50.0 * 2.0  # 100.0

    def test_cache_multiplier(self):
        c = _comp("cache1", "Cache", ComponentType.CACHE, health=HealthStatus.HEALTHY)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 50.0 * 0.5  # 25.0

    def test_load_balancer_default_multiplier(self):
        c = _comp("lb1", "LB", ComponentType.LOAD_BALANCER, health=HealthStatus.HEALTHY)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 50.0  # multiplier 1.0

    def test_queue_default_multiplier(self):
        c = _comp("q1", "Queue", ComponentType.QUEUE, health=HealthStatus.HEALTHY)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 50.0

    def test_storage_default_multiplier(self):
        c = _comp("s1", "Storage", ComponentType.STORAGE, health=HealthStatus.HEALTHY)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 50.0

    def test_dns_default_multiplier(self):
        c = _comp("d1", "DNS", ComponentType.DNS, health=HealthStatus.HEALTHY)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 50.0

    def test_custom_default_multiplier(self):
        c = _comp("x1", "Custom", ComponentType.CUSTOM, health=HealthStatus.HEALTHY)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 50.0

    def test_web_server_default_multiplier(self):
        c = _comp("w1", "Web", ComponentType.WEB_SERVER, health=HealthStatus.HEALTHY)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 50.0

    def test_database_degraded_combined(self):
        c = _comp("db1", "DB", ComponentType.DATABASE, health=HealthStatus.DEGRADED)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 500.0 * 1.5  # 750.0
        assert r.status == SignalStatus.WARNING

    def test_external_api_overloaded(self):
        c = _comp("api1", "API", ComponentType.EXTERNAL_API, health=HealthStatus.OVERLOADED)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 2000.0 * 2.0  # 4000.0
        assert r.status == SignalStatus.CRITICAL

    def test_latency_details_string(self):
        c = _comp("c1", "Comp", ComponentType.CACHE, health=HealthStatus.HEALTHY)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert "Latency" in r.details
        assert "cache" in r.details
        assert "0.5x" in r.details


# ===================================================================
# 7. Traffic analysis
# ===================================================================


class TestTraffic:
    def test_zero_connections_healthy(self):
        c = _comp("c1", "App", ComponentType.APP_SERVER)
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == 0.0
        assert r.status == SignalStatus.HEALTHY

    def test_high_traffic_warning(self):
        c = _comp("c1", "App", ComponentType.APP_SERVER)
        c.metrics.network_connections = 750
        c.capacity.max_connections = 1000
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == 75.0
        assert r.status == SignalStatus.WARNING

    def test_high_traffic_critical(self):
        c = _comp("c1", "App", ComponentType.APP_SERVER)
        c.metrics.network_connections = 950
        c.capacity.max_connections = 1000
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == 95.0
        assert r.status == SignalStatus.CRITICAL

    def test_exact_warning_threshold(self):
        c = _comp("c1", "App", ComponentType.APP_SERVER)
        c.metrics.network_connections = 700
        c.capacity.max_connections = 1000
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == 70.0
        assert r.status == SignalStatus.WARNING

    def test_exact_critical_threshold(self):
        c = _comp("c1", "App", ComponentType.APP_SERVER)
        c.metrics.network_connections = 900
        c.capacity.max_connections = 1000
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == 90.0
        assert r.status == SignalStatus.CRITICAL

    def test_full_capacity(self):
        c = _comp("c1", "App", ComponentType.APP_SERVER)
        c.metrics.network_connections = 1000
        c.capacity.max_connections = 1000
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == 100.0
        assert r.status == SignalStatus.CRITICAL

    def test_details_string(self):
        c = _comp("c1", "App", ComponentType.APP_SERVER)
        c.metrics.network_connections = 100
        c.capacity.max_connections = 1000
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert "Traffic" in r.details
        assert "100/1000" in r.details


class TestTrafficDefaultCapacities:
    """When max_connections == 0, default capacity should be used."""

    def test_web_server_default(self):
        c = _comp("w1", "Web", ComponentType.WEB_SERVER)
        c.capacity.max_connections = 0
        c.metrics.network_connections = 700
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == (700 / 1000) * 100.0  # default 1000
        assert r.status == SignalStatus.WARNING

    def test_app_server_default(self):
        c = _comp("a1", "App", ComponentType.APP_SERVER)
        c.capacity.max_connections = 0
        c.metrics.network_connections = 450
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == (450 / 500) * 100.0  # default 500 → 90%
        assert r.status == SignalStatus.CRITICAL

    def test_database_default(self):
        c = _comp("db1", "DB", ComponentType.DATABASE)
        c.capacity.max_connections = 0
        c.metrics.network_connections = 100
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == (100 / 200) * 100.0  # default 200

    def test_cache_default(self):
        c = _comp("cache1", "Cache", ComponentType.CACHE)
        c.capacity.max_connections = 0
        c.metrics.network_connections = 2500
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == (2500 / 5000) * 100.0  # default 5000

    def test_queue_default(self):
        c = _comp("q1", "Queue", ComponentType.QUEUE)
        c.capacity.max_connections = 0
        c.metrics.network_connections = 1500
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == (1500 / 2000) * 100.0  # default 2000

    def test_fallback_default(self):
        c = _comp("x1", "Custom", ComponentType.CUSTOM)
        c.capacity.max_connections = 0
        c.metrics.network_connections = 250
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == (250 / 500) * 100.0  # fallback 500

    def test_load_balancer_fallback(self):
        c = _comp("lb1", "LB", ComponentType.LOAD_BALANCER)
        c.capacity.max_connections = 0
        c.metrics.network_connections = 400
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == (400 / 500) * 100.0  # fallback 500

    def test_storage_fallback(self):
        c = _comp("s1", "Storage", ComponentType.STORAGE)
        c.capacity.max_connections = 0
        c.metrics.network_connections = 100
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == (100 / 500) * 100.0

    def test_dns_fallback(self):
        c = _comp("d1", "DNS", ComponentType.DNS)
        c.capacity.max_connections = 0
        c.metrics.network_connections = 200
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == (200 / 500) * 100.0

    def test_external_api_fallback(self):
        c = _comp("api1", "API", ComponentType.EXTERNAL_API)
        c.capacity.max_connections = 0
        c.metrics.network_connections = 300
        g = _graph(c)
        r = GoldenSignalAnalyzer(g)._analyze_traffic(c)
        assert r.value == (300 / 500) * 100.0


# ===================================================================
# 8. Errors analysis — all health states
# ===================================================================


class TestErrors:
    @pytest.mark.parametrize(
        "health, expected_value, expected_status",
        [
            (HealthStatus.HEALTHY, 0.0, SignalStatus.HEALTHY),
            (HealthStatus.DEGRADED, 5.0, SignalStatus.CRITICAL),
            (HealthStatus.OVERLOADED, 15.0, SignalStatus.CRITICAL),
            (HealthStatus.DOWN, 100.0, SignalStatus.CRITICAL),
        ],
    )
    def test_error_rate_per_health(self, health, expected_value, expected_status):
        c = _comp("c1", "comp", health=health)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_errors(c)
        assert r.value == expected_value
        assert r.status == expected_status
        assert r.signal_type == SignalType.ERRORS

    def test_details_string(self):
        c = _comp("c1", "comp", health=HealthStatus.DEGRADED)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_errors(c)
        assert "Error rate" in r.details
        assert "degraded" in r.details


# ===================================================================
# 9. Saturation analysis
# ===================================================================


class TestSaturation:
    def test_all_zero_healthy(self):
        c = _comp("c1", "comp")
        r = GoldenSignalAnalyzer(_graph(c))._analyze_saturation(c)
        assert r.value == 0.0
        assert r.status == SignalStatus.HEALTHY

    def test_cpu_high_warning(self):
        c = _comp("c1", "comp")
        c.metrics.cpu_percent = 75.0
        r = GoldenSignalAnalyzer(_graph(c))._analyze_saturation(c)
        assert r.value == 75.0
        assert r.status == SignalStatus.WARNING

    def test_memory_high_critical(self):
        c = _comp("c1", "comp")
        c.metrics.memory_percent = 90.0
        r = GoldenSignalAnalyzer(_graph(c))._analyze_saturation(c)
        assert r.value == 90.0
        assert r.status == SignalStatus.CRITICAL

    def test_disk_high_critical(self):
        c = _comp("c1", "comp")
        c.metrics.disk_percent = 88.0
        r = GoldenSignalAnalyzer(_graph(c))._analyze_saturation(c)
        assert r.value == 88.0
        assert r.status == SignalStatus.CRITICAL

    def test_uses_max_of_all(self):
        c = _comp("c1", "comp")
        c.metrics.cpu_percent = 50.0
        c.metrics.memory_percent = 80.0
        c.metrics.disk_percent = 60.0
        r = GoldenSignalAnalyzer(_graph(c))._analyze_saturation(c)
        assert r.value == 80.0  # max of the three
        assert r.status == SignalStatus.WARNING

    def test_exact_warning_boundary(self):
        c = _comp("c1", "comp")
        c.metrics.cpu_percent = 70.0
        r = GoldenSignalAnalyzer(_graph(c))._analyze_saturation(c)
        assert r.status == SignalStatus.WARNING

    def test_exact_critical_boundary(self):
        c = _comp("c1", "comp")
        c.metrics.cpu_percent = 85.0
        r = GoldenSignalAnalyzer(_graph(c))._analyze_saturation(c)
        assert r.status == SignalStatus.CRITICAL

    def test_just_below_warning(self):
        c = _comp("c1", "comp")
        c.metrics.cpu_percent = 69.9
        r = GoldenSignalAnalyzer(_graph(c))._analyze_saturation(c)
        assert r.status == SignalStatus.HEALTHY

    def test_details_string(self):
        c = _comp("c1", "comp")
        c.metrics.cpu_percent = 80.0
        c.metrics.memory_percent = 60.0
        c.metrics.disk_percent = 40.0
        r = GoldenSignalAnalyzer(_graph(c))._analyze_saturation(c)
        assert "Saturation" in r.details
        assert "cpu=80.0%" in r.details
        assert "mem=60.0%" in r.details
        assert "disk=40.0%" in r.details


# ===================================================================
# 10. Overall health determination
# ===================================================================


class TestOverallHealth:
    def test_all_healthy(self):
        c = _comp("c1", "comp")
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.overall_health == SignalStatus.HEALTHY

    def test_warning_from_saturation(self):
        c = _comp("c1", "comp")
        c.metrics.cpu_percent = 75.0
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.overall_health == SignalStatus.WARNING

    def test_critical_from_errors(self):
        c = _comp("c1", "comp", health=HealthStatus.DOWN)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.overall_health == SignalStatus.CRITICAL

    def test_critical_overrides_warning(self):
        c1 = _comp("c1", "OKish", health=HealthStatus.HEALTHY)
        c1.metrics.cpu_percent = 75.0  # WARNING saturation
        c2 = _comp("c2", "Bad", health=HealthStatus.DOWN)  # CRITICAL errors
        report = GoldenSignalAnalyzer(_graph(c1, c2)).analyze()
        assert report.overall_health == SignalStatus.CRITICAL

    def test_warning_but_no_critical(self):
        c = _comp("c1", "comp")
        c.metrics.cpu_percent = 72.0
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.overall_health == SignalStatus.WARNING


# ===================================================================
# 11. analyze_signal for each type (standalone invocation)
# ===================================================================


class TestAnalyzeSignalStandalone:
    """Test analyze_signal called without pre-computed readings."""

    def test_latency(self):
        c = _comp("c1", "comp", health=HealthStatus.DEGRADED)
        a = GoldenSignalAnalyzer(_graph(c))
        s = a.analyze_signal(SignalType.LATENCY)
        assert s.signal_type == SignalType.LATENCY
        assert s.total_readings == 1
        assert s.warning_count == 1
        assert s.worst_reading is not None
        assert s.worst_reading.value == 500.0

    def test_traffic(self):
        c = _comp("c1", "comp")
        c.metrics.network_connections = 800
        c.capacity.max_connections = 1000
        a = GoldenSignalAnalyzer(_graph(c))
        s = a.analyze_signal(SignalType.TRAFFIC)
        assert s.signal_type == SignalType.TRAFFIC
        assert s.total_readings == 1
        assert s.warning_count == 1

    def test_errors(self):
        c = _comp("c1", "comp", health=HealthStatus.OVERLOADED)
        a = GoldenSignalAnalyzer(_graph(c))
        s = a.analyze_signal(SignalType.ERRORS)
        assert s.signal_type == SignalType.ERRORS
        assert s.critical_count == 1

    def test_saturation(self):
        c = _comp("c1", "comp")
        c.metrics.cpu_percent = 90.0
        a = GoldenSignalAnalyzer(_graph(c))
        s = a.analyze_signal(SignalType.SATURATION)
        assert s.signal_type == SignalType.SATURATION
        assert s.critical_count == 1


# ===================================================================
# 12. Signal summaries — counts, averages, worst reading
# ===================================================================


class TestSignalSummaries:
    def test_counts(self):
        c1 = _comp("c1", "A", health=HealthStatus.HEALTHY)
        c2 = _comp("c2", "B", health=HealthStatus.DEGRADED)
        c3 = _comp("c3", "C", health=HealthStatus.DOWN)
        report = GoldenSignalAnalyzer(_graph(c1, c2, c3)).analyze()

        latency_summary = next(
            s for s in report.summaries if s.signal_type == SignalType.LATENCY
        )
        assert latency_summary.total_readings == 3
        assert latency_summary.healthy_count == 1
        assert latency_summary.warning_count == 1
        assert latency_summary.critical_count == 1

    def test_average_value(self):
        c1 = _comp("c1", "A")
        c2 = _comp("c2", "B")
        c1.metrics.cpu_percent = 60.0
        c2.metrics.cpu_percent = 80.0
        report = GoldenSignalAnalyzer(_graph(c1, c2)).analyze()

        sat_summary = next(
            s for s in report.summaries if s.signal_type == SignalType.SATURATION
        )
        assert sat_summary.average_value == 70.0

    def test_worst_reading(self):
        c1 = _comp("c1", "A", health=HealthStatus.HEALTHY)
        c2 = _comp("c2", "B", health=HealthStatus.DOWN)
        report = GoldenSignalAnalyzer(_graph(c1, c2)).analyze()

        errors_summary = next(
            s for s in report.summaries if s.signal_type == SignalType.ERRORS
        )
        assert errors_summary.worst_reading is not None
        assert errors_summary.worst_reading.component_id == "c2"
        assert errors_summary.worst_reading.value == 100.0

    def test_all_summaries_present(self):
        c = _comp("c1", "comp")
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert len(report.summaries) == 4
        types = {s.signal_type for s in report.summaries}
        assert types == {SignalType.LATENCY, SignalType.TRAFFIC, SignalType.ERRORS, SignalType.SATURATION}

    def test_healthy_summary_recommendation(self):
        c = _comp("c1", "comp")
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        for s in report.summaries:
            assert "healthy" in s.recommendation.lower() or s.recommendation


# ===================================================================
# 13. Recommendations generation
# ===================================================================


class TestRecommendations:
    def test_critical_latency_recommendation(self):
        c = _comp("c1", "Slow", health=HealthStatus.OVERLOADED)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        recs = [r for r in report.recommendations if "latency" in r.lower() or "Slow" in r]
        assert len(recs) > 0

    def test_critical_errors_recommendation(self):
        c = _comp("c1", "Broken", health=HealthStatus.DOWN)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        recs = [r for r in report.recommendations if "error" in r.lower() or "Broken" in r]
        assert len(recs) > 0

    def test_warning_saturation_recommendation(self):
        c = _comp("c1", "Loaded")
        c.metrics.cpu_percent = 75.0
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        recs = [r for r in report.recommendations if "Loaded" in r]
        assert len(recs) > 0

    def test_warning_traffic_recommendation(self):
        c = _comp("c1", "Busy")
        c.metrics.network_connections = 750
        c.capacity.max_connections = 1000
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        recs = [r for r in report.recommendations if "Busy" in r]
        assert len(recs) > 0

    def test_no_duplicate_recommendations(self):
        c1 = _comp("c1", "A", health=HealthStatus.DOWN)
        c2 = _comp("c2", "B", health=HealthStatus.DOWN)
        report = GoldenSignalAnalyzer(_graph(c1, c2)).analyze()
        # Each recommendation should be unique
        assert len(report.recommendations) == len(set(report.recommendations))

    def test_critical_traffic_recommendation(self):
        c = _comp("c1", "Saturated")
        c.metrics.network_connections = 950
        c.capacity.max_connections = 1000
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        recs = [r for r in report.recommendations if "Saturated" in r]
        assert len(recs) > 0

    def test_critical_saturation_recommendation(self):
        c = _comp("c1", "Full")
        c.metrics.cpu_percent = 95.0
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        recs = [r for r in report.recommendations if "Full" in r]
        assert len(recs) > 0


# ===================================================================
# 14. Top issues list
# ===================================================================


class TestTopIssues:
    def test_max_five_issues(self):
        comps = [
            _comp(f"c{i}", f"Comp{i}", health=HealthStatus.DOWN) for i in range(5)
        ]
        report = GoldenSignalAnalyzer(_graph(*comps)).analyze()
        assert len(report.top_issues) <= 5

    def test_critical_before_warning(self):
        c1 = _comp("c1", "Critical", health=HealthStatus.DOWN)
        c2 = _comp("c2", "Warning")
        c2.metrics.cpu_percent = 75.0
        report = GoldenSignalAnalyzer(_graph(c1, c2)).analyze()
        if report.top_issues:
            assert "[CRITICAL]" in report.top_issues[0]

    def test_no_issues_when_all_healthy(self):
        c = _comp("c1", "comp")
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.top_issues == []

    def test_issue_format_includes_signal_type(self):
        c = _comp("c1", "Broken", health=HealthStatus.DOWN)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert any("latency" in i or "errors" in i for i in report.top_issues)

    def test_issue_format_includes_component_name(self):
        c = _comp("c1", "MyService", health=HealthStatus.DOWN)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert any("MyService" in i for i in report.top_issues)


# ===================================================================
# 15. Summary string
# ===================================================================


class TestSummaryString:
    def test_contains_component_count(self):
        c = _comp("c1", "comp")
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert "1 components" in report.summary

    def test_contains_overall_health(self):
        c = _comp("c1", "comp")
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert "HEALTHY" in report.summary

    def test_contains_violation_count(self):
        c = _comp("c1", "comp")
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert "0/4" in report.summary

    def test_critical_summary(self):
        c = _comp("c1", "comp", health=HealthStatus.DOWN)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert "CRITICAL" in report.summary

    def test_top_issue_in_summary(self):
        c = _comp("c1", "BadComp", health=HealthStatus.DOWN)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert "Top issue" in report.summary

    def test_no_top_issue_when_healthy(self):
        c = _comp("c1", "comp")
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert "Top issue" not in report.summary


# ===================================================================
# 16. Mixed components
# ===================================================================


class TestMixedComponents:
    def test_some_healthy_some_degraded_some_down(self):
        c1 = _comp("c1", "Healthy", health=HealthStatus.HEALTHY)
        c2 = _comp("c2", "Degraded", health=HealthStatus.DEGRADED)
        c3 = _comp("c3", "Down", health=HealthStatus.DOWN)
        report = GoldenSignalAnalyzer(_graph(c1, c2, c3)).analyze()
        assert report.total_components == 3
        assert report.overall_health == SignalStatus.CRITICAL
        assert report.signals_in_violation > 0
        assert len(report.readings) == 12  # 3 components * 4 signals

    def test_mixed_types(self):
        comps = [
            _comp("db1", "DB", ComponentType.DATABASE),
            _comp("web1", "Web", ComponentType.WEB_SERVER),
            _comp("cache1", "Cache", ComponentType.CACHE),
            _comp("api1", "API", ComponentType.EXTERNAL_API),
        ]
        report = GoldenSignalAnalyzer(_graph(*comps)).analyze()
        assert report.total_components == 4
        assert len(report.readings) == 16

    def test_mixed_health_and_saturation(self):
        c1 = _comp("c1", "Normal")
        c2 = _comp("c2", "Loaded")
        c2.metrics.cpu_percent = 80.0
        c3 = _comp("c3", "Sick", health=HealthStatus.DOWN)
        report = GoldenSignalAnalyzer(_graph(c1, c2, c3)).analyze()
        assert report.overall_health == SignalStatus.CRITICAL

    def test_multiple_warnings_no_critical(self):
        c1 = _comp("c1", "A")
        c1.metrics.cpu_percent = 72.0
        c2 = _comp("c2", "B")
        c2.metrics.memory_percent = 74.0
        report = GoldenSignalAnalyzer(_graph(c1, c2)).analyze()
        assert report.overall_health == SignalStatus.WARNING


# ===================================================================
# 17. Edge cases
# ===================================================================


class TestEdgeCases:
    def test_all_components_down(self):
        comps = [_comp(f"c{i}", f"Down{i}", health=HealthStatus.DOWN) for i in range(3)]
        report = GoldenSignalAnalyzer(_graph(*comps)).analyze()
        assert report.overall_health == SignalStatus.CRITICAL
        assert report.signals_in_violation >= 2  # at least latency & errors

    def test_all_components_perfect(self):
        comps = [_comp(f"c{i}", f"Perfect{i}") for i in range(5)]
        report = GoldenSignalAnalyzer(_graph(*comps)).analyze()
        assert report.overall_health == SignalStatus.HEALTHY
        assert report.signals_in_violation == 0
        assert report.top_issues == []
        assert report.recommendations == []

    def test_single_database(self):
        c = _comp("db1", "MainDB", ComponentType.DATABASE)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.total_components == 1
        # Latency for healthy DB = 50 * 1.5 = 75ms → HEALTHY
        latency_readings = [r for r in report.readings if r.signal_type == SignalType.LATENCY]
        assert latency_readings[0].value == 75.0
        assert latency_readings[0].status == SignalStatus.HEALTHY

    def test_single_cache(self):
        c = _comp("c1", "MainCache", ComponentType.CACHE)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        latency_readings = [r for r in report.readings if r.signal_type == SignalType.LATENCY]
        assert latency_readings[0].value == 25.0

    def test_single_external_api(self):
        c = _comp("api1", "ExtAPI", ComponentType.EXTERNAL_API)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        latency_readings = [r for r in report.readings if r.signal_type == SignalType.LATENCY]
        assert latency_readings[0].value == 100.0

    def test_overloaded_component_all_signals(self):
        c = _comp("c1", "Overloaded", health=HealthStatus.OVERLOADED)
        c.metrics.cpu_percent = 95.0
        c.metrics.network_connections = 950
        c.capacity.max_connections = 1000
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.overall_health == SignalStatus.CRITICAL
        # Latency CRITICAL (2000ms), Errors CRITICAL (15%), Saturation CRITICAL (95%), Traffic CRITICAL (95%)
        critical_readings = [r for r in report.readings if r.status == SignalStatus.CRITICAL]
        assert len(critical_readings) == 4

    def test_signals_in_violation_count(self):
        c = _comp("c1", "comp", health=HealthStatus.DEGRADED)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        # DEGRADED → latency WARNING (500ms), errors CRITICAL (5%)
        assert report.signals_in_violation >= 2

    def test_large_number_of_components(self):
        comps = [_comp(f"c{i}", f"Comp{i}") for i in range(50)]
        report = GoldenSignalAnalyzer(_graph(*comps)).analyze()
        assert report.total_components == 50
        assert len(report.readings) == 200

    def test_component_with_replicas(self):
        c = _comp("c1", "comp", replicas=5)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.total_components == 1
        assert report.overall_health == SignalStatus.HEALTHY


# ===================================================================
# 18. analyze_signal with pre-computed readings
# ===================================================================


class TestAnalyzeSignalWithReadings:
    def test_filters_by_signal_type(self):
        c = _comp("c1", "comp", health=HealthStatus.DEGRADED)
        c.metrics.cpu_percent = 90.0
        a = GoldenSignalAnalyzer(_graph(c))
        all_readings = a.analyze().readings
        summary = a.analyze_signal(SignalType.LATENCY, all_readings)
        assert summary.total_readings == 1
        assert summary.signal_type == SignalType.LATENCY


# ===================================================================
# 19. Signal summaries recommendation text
# ===================================================================


class TestSummaryRecommendations:
    def test_healthy_recommendation(self):
        c = _comp("c1", "comp")
        a = GoldenSignalAnalyzer(_graph(c))
        s = a.analyze_signal(SignalType.LATENCY)
        assert "healthy" in s.recommendation.lower()

    def test_warning_recommendation(self):
        c = _comp("c1", "comp", health=HealthStatus.DEGRADED)
        a = GoldenSignalAnalyzer(_graph(c))
        s = a.analyze_signal(SignalType.LATENCY)
        assert s.recommendation  # non-empty

    def test_critical_recommendation(self):
        c = _comp("c1", "comp", health=HealthStatus.DOWN)
        a = GoldenSignalAnalyzer(_graph(c))
        s = a.analyze_signal(SignalType.ERRORS)
        assert "error" in s.recommendation.lower() or "investigation" in s.recommendation.lower()


# ===================================================================
# 20. Comprehensive report field validation
# ===================================================================


class TestReportFields:
    def test_report_with_degraded(self):
        c = _comp("c1", "Degraded", health=HealthStatus.DEGRADED)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.total_components == 1
        assert len(report.summaries) == 4
        assert report.overall_health in (SignalStatus.WARNING, SignalStatus.CRITICAL)
        assert report.summary != ""

    def test_report_readings_have_correct_component_info(self):
        c = _comp("myid", "MyName", ComponentType.CACHE)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        for r in report.readings:
            assert r.component_id == "myid"
            assert r.component_name == "MyName"

    def test_report_readings_have_thresholds(self):
        c = _comp("c1", "comp")
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        for r in report.readings:
            assert r.threshold is not None
            assert r.threshold.unit in ("ms", "%")

    def test_report_readings_have_details(self):
        c = _comp("c1", "comp")
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        for r in report.readings:
            assert r.details  # non-empty string


# ===================================================================
# 21. Latency edge: warning boundary at 200ms
# ===================================================================


class TestLatencyBoundary:
    def test_just_below_200(self):
        """External API healthy = 50*2.0 = 100ms → HEALTHY"""
        c = _comp("api1", "API", ComponentType.EXTERNAL_API, health=HealthStatus.HEALTHY)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_latency(c)
        assert r.value == 100.0
        assert r.status == SignalStatus.HEALTHY

    def test_at_exactly_200(self):
        """Need a scenario that produces exactly 200ms."""
        # Can't easily produce exactly 200 with the given health values and multipliers.
        # Use _classify directly instead.
        from faultray.simulator.golden_signal_analyzer import _LATENCY_THRESHOLD
        assert _classify(200.0, _LATENCY_THRESHOLD) == SignalStatus.WARNING

    def test_at_exactly_1000(self):
        from faultray.simulator.golden_signal_analyzer import _LATENCY_THRESHOLD
        assert _classify(1000.0, _LATENCY_THRESHOLD) == SignalStatus.CRITICAL


# ===================================================================
# 22. Violations count
# ===================================================================


class TestViolationsCount:
    def test_zero_violations(self):
        c = _comp("c1", "comp")
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.signals_in_violation == 0

    def test_one_violation(self):
        c = _comp("c1", "comp")
        c.metrics.cpu_percent = 75.0  # WARNING saturation only
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.signals_in_violation == 1

    def test_multiple_violations(self):
        c = _comp("c1", "comp", health=HealthStatus.DOWN)
        c.metrics.cpu_percent = 95.0
        c.metrics.network_connections = 950
        c.capacity.max_connections = 1000
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.signals_in_violation == 4  # all four in violation

    def test_two_violations(self):
        c = _comp("c1", "comp", health=HealthStatus.DEGRADED)
        # DEGRADED → latency 500ms (WARNING), errors 5% (CRITICAL)
        # Traffic 0% (HEALTHY), Saturation 0% (HEALTHY)
        report = GoldenSignalAnalyzer(_graph(c)).analyze()
        assert report.signals_in_violation == 2


# ===================================================================
# 23. Multiple components with same signal issues
# ===================================================================


class TestMultipleComponentsSameIssue:
    def test_two_components_same_error(self):
        c1 = _comp("c1", "Svc1", health=HealthStatus.DOWN)
        c2 = _comp("c2", "Svc2", health=HealthStatus.DOWN)
        report = GoldenSignalAnalyzer(_graph(c1, c2)).analyze()
        error_summary = next(s for s in report.summaries if s.signal_type == SignalType.ERRORS)
        assert error_summary.critical_count == 2

    def test_multiple_traffic_warnings(self):
        c1 = _comp("c1", "Svc1")
        c1.metrics.network_connections = 750
        c1.capacity.max_connections = 1000
        c2 = _comp("c2", "Svc2")
        c2.metrics.network_connections = 800
        c2.capacity.max_connections = 1000
        report = GoldenSignalAnalyzer(_graph(c1, c2)).analyze()
        traffic_summary = next(s for s in report.summaries if s.signal_type == SignalType.TRAFFIC)
        assert traffic_summary.warning_count == 2


# ===================================================================
# 24. Latency warning from degraded errors signal
# ===================================================================


class TestDegradedErrorsWarning:
    def test_degraded_errors_is_critical(self):
        """DEGRADED health → error rate 5% which is at the critical threshold."""
        c = _comp("c1", "comp", health=HealthStatus.DEGRADED)
        r = GoldenSignalAnalyzer(_graph(c))._analyze_errors(c)
        assert r.value == 5.0
        assert r.status == SignalStatus.CRITICAL  # 5% >= critical threshold 5%
