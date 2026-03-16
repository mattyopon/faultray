"""Tests for MetricCalibrator -- hybrid mode calibration from real metrics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from faultray.discovery.metric_calibrator import CalibrationResult, MetricCalibrator
from faultray.model.components import Component, ComponentType, ResourceMetrics
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component(cid: str, host: str = "", cpu: float = 0.0, mem: float = 0.0) -> Component:
    return Component(
        id=cid,
        name=cid.replace("_", " ").title(),
        type=ComponentType.APP_SERVER,
        host=host,
        metrics=ResourceMetrics(cpu_percent=cpu, memory_percent=mem),
    )


def _make_graph(components: list[Component]) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


def _mock_prom_client(cpu_data: list[dict], mem_total_data: list[dict], mem_avail_data: list[dict]):
    """Create a mock httpx client that returns canned Prometheus responses."""
    client = MagicMock()

    def fake_get(path, params=None):
        query = params.get("query", "") if params else ""
        resp = MagicMock()
        resp.status_code = 200

        if "node_cpu_seconds_total" in query:
            resp.json.return_value = {
                "status": "success",
                "data": {"resultType": "vector", "result": cpu_data},
            }
        elif query == "node_memory_MemTotal_bytes":
            resp.json.return_value = {
                "status": "success",
                "data": {"resultType": "vector", "result": mem_total_data},
            }
        elif query == "node_memory_MemAvailable_bytes":
            resp.json.return_value = {
                "status": "success",
                "data": {"resultType": "vector", "result": mem_avail_data},
            }
        else:
            resp.json.return_value = {"status": "success", "data": {"result": []}}

        resp.raise_for_status = MagicMock()
        return resp

    client.get = fake_get
    return client


# ---------------------------------------------------------------------------
# Tests: Prometheus calibration
# ---------------------------------------------------------------------------


class TestPrometheusCalibration:
    def test_calibrate_cpu_adjusts_value(self):
        comp = _make_component("web", host="10.0.1.5", cpu=20.0)
        graph = _make_graph([comp])

        client = _mock_prom_client(
            cpu_data=[{"metric": {"instance": "10.0.1.5:9100"}, "value": [1234, "75.3"]}],
            mem_total_data=[],
            mem_avail_data=[],
        )

        cal = MetricCalibrator(graph)
        results = cal.calibrate_from_prometheus("http://fake:9090", _client=client)

        assert len(results) >= 1
        cpu_result = [r for r in results if r.metric == "cpu_percent"]
        assert len(cpu_result) == 1
        assert cpu_result[0].actual_value == pytest.approx(75.3)
        assert cpu_result[0].calibrated is True
        # Component should be updated
        assert comp.metrics.cpu_percent == pytest.approx(75.3)

    def test_calibrate_memory_adjusts_value(self):
        comp = _make_component("db", host="10.0.2.10", mem=30.0)
        graph = _make_graph([comp])

        client = _mock_prom_client(
            cpu_data=[],
            mem_total_data=[{"metric": {"instance": "10.0.2.10:9100"}, "value": [1234, "8589934592"]}],  # 8 GB
            mem_avail_data=[{"metric": {"instance": "10.0.2.10:9100"}, "value": [1234, "2147483648"]}],  # 2 GB
        )

        cal = MetricCalibrator(graph)
        results = cal.calibrate_from_prometheus("http://fake:9090", _client=client)

        mem_results = [r for r in results if r.metric == "memory_percent"]
        assert len(mem_results) == 1
        # (1 - 2GB/8GB) * 100 = 75%
        assert mem_results[0].actual_value == pytest.approx(75.0)
        assert mem_results[0].calibrated is True

    def test_no_calibration_when_within_threshold(self):
        comp = _make_component("app", host="10.0.1.1", cpu=50.0)
        graph = _make_graph([comp])

        client = _mock_prom_client(
            cpu_data=[{"metric": {"instance": "10.0.1.1:9100"}, "value": [1234, "51.0"]}],
            mem_total_data=[],
            mem_avail_data=[],
        )

        cal = MetricCalibrator(graph)
        results = cal.calibrate_from_prometheus("http://fake:9090", deviation_threshold=10.0, _client=client)

        cpu_result = [r for r in results if r.metric == "cpu_percent"]
        assert len(cpu_result) == 1
        assert cpu_result[0].calibrated is False
        # Component should NOT be updated
        assert comp.metrics.cpu_percent == pytest.approx(50.0)

    def test_unmatched_instance_skipped(self):
        comp = _make_component("web", host="10.0.1.5")
        graph = _make_graph([comp])

        client = _mock_prom_client(
            cpu_data=[{"metric": {"instance": "192.168.1.1:9100"}, "value": [1234, "80.0"]}],
            mem_total_data=[],
            mem_avail_data=[],
        )

        cal = MetricCalibrator(graph)
        results = cal.calibrate_from_prometheus("http://fake:9090", _client=client)

        assert len(results) == 0

    def test_empty_host_never_matches(self):
        comp = _make_component("app", host="", cpu=10.0)
        graph = _make_graph([comp])

        client = _mock_prom_client(
            cpu_data=[{"metric": {"instance": "10.0.0.1:9100"}, "value": [1234, "80.0"]}],
            mem_total_data=[],
            mem_avail_data=[],
        )

        cal = MetricCalibrator(graph)
        results = cal.calibrate_from_prometheus("http://fake:9090", _client=client)

        assert len(results) == 0


# ---------------------------------------------------------------------------
# Tests: CloudWatch calibration
# ---------------------------------------------------------------------------


class TestCloudWatchCalibration:
    def test_calibrate_from_cloudwatch_adjusts_cpu(self):
        comp = _make_component("web-server", host="i-12345", cpu=20.0)
        comp.type = ComponentType.APP_SERVER
        graph = _make_graph([comp])

        mock_cw = MagicMock()
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {
                    "Id": "cpu_web_server",
                    "Values": [65.0, 70.0, 75.0],
                    "Timestamps": [],
                }
            ]
        }

        cal = MetricCalibrator(graph)
        results = cal.calibrate_from_cloudwatch("ap-northeast-1", _cw_client=mock_cw)

        assert len(results) >= 1
        cpu_result = [r for r in results if r.metric == "cpu_percent"]
        assert len(cpu_result) == 1
        # Average of 65, 70, 75 = 70
        assert cpu_result[0].actual_value == pytest.approx(70.0)
        assert cpu_result[0].calibrated is True

    def test_cloudwatch_empty_values_skipped(self):
        comp = _make_component("srv", host="i-99999", cpu=40.0)
        graph = _make_graph([comp])

        mock_cw = MagicMock()
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "cpu_srv", "Values": [], "Timestamps": []}
            ]
        }

        cal = MetricCalibrator(graph)
        results = cal.calibrate_from_cloudwatch("us-east-1", _cw_client=mock_cw)

        assert len(results) == 0

    def test_cloudwatch_exception_handled(self):
        comp = _make_component("web", host="i-111", cpu=10.0)
        graph = _make_graph([comp])

        mock_cw = MagicMock()
        mock_cw.get_metric_data.side_effect = Exception("Access Denied")

        cal = MetricCalibrator(graph)
        results = cal.calibrate_from_cloudwatch("us-west-2", _cw_client=mock_cw)

        # Should return empty list, not raise
        assert results == []


# ---------------------------------------------------------------------------
# Tests: apply_calibration
# ---------------------------------------------------------------------------


class TestApplyCalibration:
    def test_apply_updates_metrics(self):
        comp = _make_component("app", host="10.0.1.1", cpu=20.0, mem=30.0)
        graph = _make_graph([comp])

        results = [
            CalibrationResult(
                component_id="app",
                metric="cpu_percent",
                simulated_value=20.0,
                actual_value=80.0,
                deviation_percent=300.0,
                calibrated=True,
            ),
            CalibrationResult(
                component_id="app",
                metric="memory_percent",
                simulated_value=30.0,
                actual_value=60.0,
                deviation_percent=100.0,
                calibrated=True,
            ),
        ]

        cal = MetricCalibrator(graph)
        cal.apply_calibration(results)

        assert comp.metrics.cpu_percent == pytest.approx(80.0)
        assert comp.metrics.memory_percent == pytest.approx(60.0)

    def test_apply_skips_non_calibrated(self):
        comp = _make_component("app", host="10.0.1.1", cpu=20.0)
        graph = _make_graph([comp])

        results = [
            CalibrationResult(
                component_id="app",
                metric="cpu_percent",
                simulated_value=20.0,
                actual_value=22.0,
                deviation_percent=10.0,
                calibrated=False,
            ),
        ]

        cal = MetricCalibrator(graph)
        cal.apply_calibration(results)

        assert comp.metrics.cpu_percent == pytest.approx(20.0)

    def test_apply_skips_unknown_component(self):
        graph = _make_graph([])

        results = [
            CalibrationResult(
                component_id="nonexistent",
                metric="cpu_percent",
                simulated_value=0.0,
                actual_value=50.0,
                deviation_percent=100.0,
                calibrated=True,
            ),
        ]

        cal = MetricCalibrator(graph)
        # Should not raise
        cal.apply_calibration(results)
