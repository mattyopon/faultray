"""Tests for Prometheus discovery (discovery/prometheus.py)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from faultray.discovery.prometheus import (
    PrometheusClient,
    _parse_instance,
    _safe_float,
)
from faultray.model.components import Component, ComponentType, ResourceMetrics
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prom_result(instance: str, value: float) -> dict:
    """Build a single Prometheus instant-query result vector element."""
    return {
        "metric": {"instance": instance},
        "value": [1700000000, str(value)],
    }


def _make_targets_response(targets: list[dict]) -> dict:
    """Build a Prometheus /api/v1/targets response body."""
    return {
        "status": "success",
        "data": {
            "activeTargets": targets,
        },
    }


def _make_target(instance: str, job: str) -> dict:
    """Build a single active target entry."""
    return {
        "labels": {"instance": instance, "job": job},
        "health": "up",
    }


def _make_query_response(results: list[dict]) -> dict:
    """Build a Prometheus /api/v1/query response body."""
    return {
        "status": "success",
        "data": {"result": results},
    }


# ---------------------------------------------------------------------------
# _parse_instance
# ---------------------------------------------------------------------------


class TestParseInstance:
    def test_host_and_port(self):
        host, port = _parse_instance("10.0.1.5:9100")
        assert host == "10.0.1.5"
        assert port == 9100

    def test_host_only(self):
        host, port = _parse_instance("myhost")
        assert host == "myhost"
        assert port == 0

    def test_with_scheme(self):
        host, port = _parse_instance("http://10.0.0.1:8080")
        assert host == "10.0.0.1"
        assert port == 8080


# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------


class TestSafeFloat:
    def test_valid_string(self):
        assert _safe_float("42.5") == 42.5

    def test_valid_int(self):
        assert _safe_float(10) == 10.0

    def test_invalid_string(self):
        assert _safe_float("NaN-bad", default=0.0) == 0.0

    def test_none(self):
        assert _safe_float(None, default=-1.0) == -1.0


# ---------------------------------------------------------------------------
# PrometheusClient._guess_type
# ---------------------------------------------------------------------------


class TestGuessType:
    """Test component type guessing from job name and port."""

    @pytest.mark.parametrize("job,expected", [
        ("nginx", ComponentType.LOAD_BALANCER),
        ("haproxy", ComponentType.LOAD_BALANCER),
        ("envoy-sidecar", ComponentType.LOAD_BALANCER),
        ("traefik", ComponentType.LOAD_BALANCER),
        ("my-lb", ComponentType.LOAD_BALANCER),
        ("postgres-exporter", ComponentType.DATABASE),
        ("mysql", ComponentType.DATABASE),
        ("mariadb-prod", ComponentType.DATABASE),
        ("mongo-atlas", ComponentType.DATABASE),
        ("elasticsearch-cluster", ComponentType.DATABASE),
        ("redis-cache", ComponentType.CACHE),
        ("memcached", ComponentType.CACHE),
        ("app-cache", ComponentType.CACHE),
        ("rabbitmq", ComponentType.QUEUE),
        ("kafka-broker", ComponentType.QUEUE),
        ("nats-server", ComponentType.QUEUE),
        ("task-queue", ComponentType.QUEUE),
        ("minio", ComponentType.STORAGE),
        ("s3-gateway", ComponentType.STORAGE),
        ("ceph-monitor", ComponentType.STORAGE),
        ("object-storage", ComponentType.STORAGE),
        ("coredns", ComponentType.DNS),
        ("bind-dns", ComponentType.DNS),
        ("web-frontend", ComponentType.WEB_SERVER),
        ("httpd-server", ComponentType.WEB_SERVER),
        ("apache-app", ComponentType.WEB_SERVER),
    ])
    def test_job_name_matching(self, job, expected):
        assert PrometheusClient._guess_type(job, 0) == expected

    def test_unknown_job_defaults_to_app_server(self):
        assert PrometheusClient._guess_type("my-custom-service", 0) == ComponentType.APP_SERVER

    def test_port_fallback_for_unknown_job(self):
        # Port 5432 => DATABASE from PORT_SERVICE_MAP
        assert PrometheusClient._guess_type("unknown-job", 5432) == ComponentType.DATABASE

    def test_port_fallback_redis(self):
        assert PrometheusClient._guess_type("unknown-job", 6379) == ComponentType.CACHE


# ---------------------------------------------------------------------------
# PrometheusClient.query & get_targets (mocked httpx)
# ---------------------------------------------------------------------------


class TestPrometheusClientQueries:
    """Test low-level query methods with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_query_success(self):
        client = PrometheusClient(url="http://fake-prom:9090")
        resp_data = _make_query_response([_prom_result("host:9100", 42.0)])

        mock_response = MagicMock()
        mock_response.json.return_value = resp_data
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("faultray.discovery.prometheus.httpx.AsyncClient", return_value=mock_http_client):
            results = await client.query("up")

        assert len(results) == 1
        assert results[0]["metric"]["instance"] == "host:9100"

    @pytest.mark.asyncio
    async def test_query_failure_status(self):
        client = PrometheusClient(url="http://fake-prom:9090")
        resp_data = {"status": "error", "error": "bad query"}

        mock_response = MagicMock()
        mock_response.json.return_value = resp_data
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("faultray.discovery.prometheus.httpx.AsyncClient", return_value=mock_http_client):
            with pytest.raises(RuntimeError, match="Prometheus query failed"):
                await client.query("bad{query")

    @pytest.mark.asyncio
    async def test_get_targets_success(self):
        client = PrometheusClient(url="http://fake-prom:9090")
        resp_data = _make_targets_response([
            _make_target("10.0.0.1:9100", "node"),
            _make_target("10.0.0.2:9100", "node"),
        ])

        mock_response = MagicMock()
        mock_response.json.return_value = resp_data
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("faultray.discovery.prometheus.httpx.AsyncClient", return_value=mock_http_client):
            targets = await client.get_targets()

        assert len(targets) == 2
        assert targets[0]["labels"]["job"] == "node"

    @pytest.mark.asyncio
    async def test_get_targets_failure(self):
        client = PrometheusClient(url="http://fake-prom:9090")
        resp_data = {"status": "error"}

        mock_response = MagicMock()
        mock_response.json.return_value = resp_data
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("faultray.discovery.prometheus.httpx.AsyncClient", return_value=mock_http_client):
            with pytest.raises(RuntimeError, match="Failed to fetch targets"):
                await client.get_targets()

    @pytest.mark.asyncio
    async def test_connection_error(self):
        client = PrometheusClient(url="http://fake-prom:9090")

        mock_http_client = AsyncMock()
        mock_http_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("faultray.discovery.prometheus.httpx.AsyncClient", return_value=mock_http_client):
            with pytest.raises(httpx.ConnectError):
                await client.query("up")


# ---------------------------------------------------------------------------
# PrometheusClient.discover_components (mocked)
# ---------------------------------------------------------------------------


class TestDiscoverComponents:
    """Test full discover_components flow with mocked responses."""

    @pytest.mark.asyncio
    async def test_discover_creates_components_with_metrics(self):
        client = PrometheusClient(url="http://fake-prom:9090")

        targets_resp = _make_targets_response([
            _make_target("10.0.0.1:9100", "node"),
            _make_target("10.0.0.2:5432", "postgres"),
        ])

        # Each query() call returns metric results for these instances
        cpu_results = [_prom_result("10.0.0.1:9100", 45.0), _prom_result("10.0.0.2:5432", 30.0)]
        mem_results = [_prom_result("10.0.0.1:9100", 60.0), _prom_result("10.0.0.2:5432", 55.0)]
        disk_results = [_prom_result("10.0.0.1:9100", 40.0)]
        net_results = [_prom_result("10.0.0.1:9100", 120.0)]
        mem_total = [_prom_result("10.0.0.1:9100", 8 * 1024**3)]  # 8 GB
        mem_avail = [_prom_result("10.0.0.1:9100", 3.2 * 1024**3)]  # 3.2 GB
        disk_total = [_prom_result("10.0.0.1:9100", 500 * 1024**3)]  # 500 GB
        disk_avail = [_prom_result("10.0.0.1:9100", 300 * 1024**3)]  # 300 GB

        # Patch get_targets and query
        async def mock_get_targets():
            return targets_resp["data"]["activeTargets"]

        query_responses = iter([
            cpu_results, mem_results, disk_results, net_results,
            mem_total, mem_avail, disk_total, disk_avail,
        ])

        async def mock_query(promql):
            return next(query_responses)

        client.get_targets = mock_get_targets
        client.query = mock_query

        graph = await client.discover_components()

        assert len(graph.components) == 2

        # Check node component
        node_comp = graph.get_component("10.0.0.1:9100")
        assert node_comp is not None
        assert node_comp.type == ComponentType.APP_SERVER
        assert node_comp.host == "10.0.0.1"
        assert node_comp.port == 9100
        assert node_comp.metrics.cpu_percent == 45.0
        assert node_comp.metrics.memory_percent == 60.0

        # Check postgres component
        pg_comp = graph.get_component("10.0.0.2:5432")
        assert pg_comp is not None
        assert pg_comp.type == ComponentType.DATABASE

    @pytest.mark.asyncio
    async def test_discover_empty_targets(self):
        client = PrometheusClient(url="http://fake-prom:9090")

        async def mock_get_targets():
            return []

        query_calls = []

        async def mock_query(promql):
            query_calls.append(promql)
            return []

        client.get_targets = mock_get_targets
        client.query = mock_query

        graph = await client.discover_components()
        assert len(graph.components) == 0

    @pytest.mark.asyncio
    async def test_discover_skips_empty_instance(self):
        client = PrometheusClient(url="http://fake-prom:9090")

        async def mock_get_targets():
            return [{"labels": {"instance": "", "job": "node"}}]

        async def mock_query(promql):
            return []

        client.get_targets = mock_get_targets
        client.query = mock_query

        graph = await client.discover_components()
        assert len(graph.components) == 0


# ---------------------------------------------------------------------------
# PrometheusClient.update_metrics (mocked)
# ---------------------------------------------------------------------------


class TestUpdateMetrics:
    """Test update_metrics on an existing graph."""

    @pytest.mark.asyncio
    async def test_update_metrics_on_existing_graph(self):
        client = PrometheusClient(url="http://fake-prom:9090")

        # Build a graph with one component
        graph = InfraGraph()
        comp = Component(
            id="webhost:8080",
            name="web app",
            type=ComponentType.APP_SERVER,
            host="webhost",
            port=8080,
            metrics=ResourceMetrics(cpu_percent=10.0, memory_percent=20.0),
        )
        graph.add_component(comp)

        # Mock query to return new metrics
        cpu_results = [_prom_result("webhost:8080", 75.0)]
        mem_results = [_prom_result("webhost:8080", 80.0)]
        disk_results = [_prom_result("webhost:8080", 50.0)]
        net_results = [_prom_result("webhost:8080", 200.0)]
        mem_total = [_prom_result("webhost:8080", 16 * 1024**3)]  # 16 GB
        mem_avail = [_prom_result("webhost:8080", 3.2 * 1024**3)]  # 3.2 GB
        disk_total = [_prom_result("webhost:8080", 1000 * 1024**3)]  # 1 TB
        disk_avail = [_prom_result("webhost:8080", 500 * 1024**3)]  # 500 GB

        query_responses = iter([
            cpu_results, mem_results, disk_results, net_results,
            mem_total, mem_avail, disk_total, disk_avail,
        ])

        async def mock_query(promql):
            return next(query_responses)

        client.query = mock_query

        updated_graph = await client.update_metrics(graph)

        updated_comp = updated_graph.get_component("webhost:8080")
        assert updated_comp.metrics.cpu_percent == 75.0
        assert updated_comp.metrics.memory_percent == 80.0
        assert updated_comp.metrics.disk_percent == 50.0
        assert updated_comp.metrics.network_connections == 200

    @pytest.mark.asyncio
    async def test_update_metrics_no_matching_instance(self):
        client = PrometheusClient(url="http://fake-prom:9090")

        graph = InfraGraph()
        comp = Component(
            id="missing:9999",
            name="missing",
            type=ComponentType.APP_SERVER,
            host="missing",
            port=9999,
            metrics=ResourceMetrics(cpu_percent=5.0),
        )
        graph.add_component(comp)

        # No prometheus data for this host
        async def mock_query(promql):
            return []

        client.query = mock_query

        updated_graph = await client.update_metrics(graph)

        # Metrics should remain unchanged
        updated_comp = updated_graph.get_component("missing:9999")
        assert updated_comp.metrics.cpu_percent == 5.0
