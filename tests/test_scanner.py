"""Tests for local scanner (discovery/scanner.py)."""

from __future__ import annotations

from collections import namedtuple
from unittest.mock import MagicMock, patch

import pytest

from faultray.discovery.scanner import (
    PORT_SERVICE_MAP,
    detect_component_type,
    scan_established_connections,
    scan_listening_services,
    scan_local,
    scan_system_metrics,
)
from faultray.model.components import ComponentType, ResourceMetrics


# ---------------------------------------------------------------------------
# Fake psutil structures
# ---------------------------------------------------------------------------

# Mimic psutil's addr namedtuple
_Addr = namedtuple("addr", ["ip", "port"])


def _fake_conn(status, laddr_ip, laddr_port, raddr=None, pid=None):
    """Build a fake psutil connection object."""
    conn = MagicMock()
    conn.status = status
    conn.laddr = _Addr(ip=laddr_ip, port=laddr_port)
    conn.raddr = _Addr(ip=raddr[0], port=raddr[1]) if raddr else None
    conn.pid = pid
    return conn


# ===================================================================
# PORT_SERVICE_MAP smoke test
# ===================================================================


class TestPortServiceMap:
    """Verify well-known port mappings exist."""

    def test_postgresql(self):
        assert PORT_SERVICE_MAP[5432] == (ComponentType.DATABASE, "postgresql")

    def test_mysql(self):
        assert PORT_SERVICE_MAP[3306] == (ComponentType.DATABASE, "mysql")

    def test_redis(self):
        assert PORT_SERVICE_MAP[6379] == (ComponentType.CACHE, "redis")

    def test_memcached(self):
        assert PORT_SERVICE_MAP[11211] == (ComponentType.CACHE, "memcached")

    def test_rabbitmq(self):
        assert PORT_SERVICE_MAP[5672] == (ComponentType.QUEUE, "rabbitmq")

    def test_kafka(self):
        assert PORT_SERVICE_MAP[9092] == (ComponentType.QUEUE, "kafka")

    def test_http(self):
        assert PORT_SERVICE_MAP[80] == (ComponentType.WEB_SERVER, "http")

    def test_https(self):
        assert PORT_SERVICE_MAP[443] == (ComponentType.WEB_SERVER, "https")

    def test_elasticsearch(self):
        assert PORT_SERVICE_MAP[9200] == (ComponentType.DATABASE, "elasticsearch")

    def test_mongodb(self):
        assert PORT_SERVICE_MAP[27017] == (ComponentType.DATABASE, "mongodb")


# ===================================================================
# detect_component_type  (port + process name heuristic)
# ===================================================================


class TestDetectComponentType:
    """Tests for detect_component_type()."""

    # Port-based detection
    def test_known_port(self):
        comp_type, svc = detect_component_type(5432, "some_process")
        assert comp_type == ComponentType.DATABASE
        assert svc == "postgresql"

    def test_known_port_redis(self):
        comp_type, svc = detect_component_type(6379, "")
        assert comp_type == ComponentType.CACHE
        assert svc == "redis"

    # Process name-based detection
    @pytest.mark.parametrize("name,expected_type,expected_svc", [
        ("nginx", ComponentType.WEB_SERVER, "nginx"),
        ("apache2", ComponentType.WEB_SERVER, "apache2"),
        ("httpd", ComponentType.WEB_SERVER, "httpd"),
        ("postgres", ComponentType.DATABASE, "postgresql"),
        ("mysqld", ComponentType.DATABASE, "mysql"),
        ("mariadb", ComponentType.DATABASE, "mysql"),
        ("redis-server", ComponentType.CACHE, "redis"),
        ("rabbitmq-server", ComponentType.QUEUE, "rabbitmq"),
        ("kafka.Kafka", ComponentType.QUEUE, "kafka"),
        ("mongod", ComponentType.DATABASE, "mongodb"),
        ("dockerd", ComponentType.APP_SERVER, "container-runtime"),
        ("containerd", ComponentType.APP_SERVER, "container-runtime"),
        ("node", ComponentType.APP_SERVER, "node"),
        ("python3", ComponentType.APP_SERVER, "python3"),
        ("java", ComponentType.APP_SERVER, "java"),
        ("haproxy", ComponentType.LOAD_BALANCER, "haproxy"),
        ("envoy", ComponentType.LOAD_BALANCER, "envoy"),
    ])
    def test_process_name_detection(self, name, expected_type, expected_svc):
        # Use a non-mapped port so name detection kicks in
        comp_type, svc = detect_component_type(55555, name)
        assert comp_type == expected_type
        assert svc == expected_svc

    def test_unknown_process_returns_custom(self):
        comp_type, svc = detect_component_type(55555, "some_random_binary")
        assert comp_type == ComponentType.CUSTOM
        assert svc == "some_random_binary"

    def test_port_takes_priority_over_name(self):
        """If the port is in PORT_SERVICE_MAP, port wins regardless of name."""
        comp_type, svc = detect_component_type(5432, "nginx")
        assert comp_type == ComponentType.DATABASE
        assert svc == "postgresql"


# ===================================================================
# scan_listening_services (mocked psutil)
# ===================================================================


class TestScanListeningServices:
    """Tests for scan_listening_services() with mocked psutil."""

    @patch("faultray.discovery.scanner.psutil")
    def test_discovers_listening_services(self, mock_psutil):
        mock_proc = MagicMock()
        mock_proc.name.return_value = "postgres"

        mock_psutil.net_connections.return_value = [
            _fake_conn("LISTEN", "0.0.0.0", 5432, pid=1234),
            _fake_conn("LISTEN", "0.0.0.0", 6379, pid=5678),
            _fake_conn("ESTABLISHED", "0.0.0.0", 5432, raddr=("10.0.0.1", 45678), pid=1234),
        ]
        mock_psutil.Process.return_value = mock_proc
        mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})

        services = scan_listening_services()

        # Only LISTEN connections, 2 unique ports
        assert len(services) == 2
        ports = [s["port"] for s in services]
        assert 5432 in ports
        assert 6379 in ports
        assert services[0]["port"] < services[1]["port"]  # sorted

    @patch("faultray.discovery.scanner.psutil")
    def test_deduplicates_ports(self, mock_psutil):
        mock_proc = MagicMock()
        mock_proc.name.return_value = "nginx"

        mock_psutil.net_connections.return_value = [
            _fake_conn("LISTEN", "0.0.0.0", 80, pid=100),
            _fake_conn("LISTEN", "127.0.0.1", 80, pid=100),  # same port
        ]
        mock_psutil.Process.return_value = mock_proc
        mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})

        services = scan_listening_services()
        assert len(services) == 1

    @patch("faultray.discovery.scanner.psutil")
    def test_handles_no_such_process(self, mock_psutil):
        NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        mock_psutil.NoSuchProcess = NoSuchProcess
        mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
        mock_psutil.Process.side_effect = NoSuchProcess()
        mock_psutil.net_connections.return_value = [
            _fake_conn("LISTEN", "0.0.0.0", 8080, pid=9999),
        ]

        services = scan_listening_services()
        assert len(services) == 1
        assert services[0]["process"] == ""

    @patch("faultray.discovery.scanner.psutil")
    def test_handles_access_denied(self, mock_psutil):
        AccessDenied = type("AccessDenied", (Exception,), {})
        mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        mock_psutil.AccessDenied = AccessDenied
        mock_psutil.Process.side_effect = AccessDenied()
        mock_psutil.net_connections.return_value = [
            _fake_conn("LISTEN", "0.0.0.0", 3306, pid=2000),
        ]

        services = scan_listening_services()
        assert len(services) == 1
        assert services[0]["process"] == ""

    @patch("faultray.discovery.scanner.psutil")
    def test_no_pid(self, mock_psutil):
        mock_psutil.net_connections.return_value = [
            _fake_conn("LISTEN", "0.0.0.0", 9090, pid=None),
        ]
        mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})

        services = scan_listening_services()
        assert len(services) == 1
        assert services[0]["process"] == ""
        assert services[0]["pid"] is None


# ===================================================================
# scan_established_connections (mocked psutil)
# ===================================================================


class TestScanEstablishedConnections:
    """Tests for scan_established_connections() with mocked psutil."""

    @patch("faultray.discovery.scanner.psutil")
    def test_discovers_established_connections(self, mock_psutil):
        mock_psutil.net_connections.return_value = [
            _fake_conn("ESTABLISHED", "10.0.0.1", 45678, raddr=("10.0.0.2", 5432), pid=100),
            _fake_conn("ESTABLISHED", "10.0.0.1", 45679, raddr=("10.0.0.3", 6379), pid=100),
            _fake_conn("LISTEN", "0.0.0.0", 8080, pid=200),  # not established
        ]

        connections = scan_established_connections()

        assert len(connections) == 2
        remote_ports = [c["remote_port"] for c in connections]
        assert 5432 in remote_ports
        assert 6379 in remote_ports

    @patch("faultray.discovery.scanner.psutil")
    def test_skips_no_raddr(self, mock_psutil):
        mock_psutil.net_connections.return_value = [
            _fake_conn("ESTABLISHED", "10.0.0.1", 45678, raddr=None, pid=100),
        ]

        connections = scan_established_connections()
        assert len(connections) == 0

    @patch("faultray.discovery.scanner.psutil")
    def test_deduplicates_connections(self, mock_psutil):
        mock_psutil.net_connections.return_value = [
            _fake_conn("ESTABLISHED", "10.0.0.1", 45678, raddr=("10.0.0.2", 5432), pid=100),
            _fake_conn("ESTABLISHED", "10.0.0.1", 45678, raddr=("10.0.0.2", 5432), pid=100),
        ]

        connections = scan_established_connections()
        assert len(connections) == 1


# ===================================================================
# scan_system_metrics (mocked psutil)
# ===================================================================


class TestScanSystemMetrics:
    """Tests for scan_system_metrics() with mocked psutil."""

    @patch("faultray.discovery.scanner.psutil")
    def test_returns_resource_metrics(self, mock_psutil):
        mock_psutil.cpu_percent.return_value = 35.5
        mock_psutil.virtual_memory.return_value = MagicMock(
            percent=60.0,
            used=4 * 1024**3,    # 4 GB
            total=8 * 1024**3,   # 8 GB
        )
        mock_psutil.disk_usage.return_value = MagicMock(
            percent=45.0,
            used=200 * 1024**3,   # 200 GB
            total=500 * 1024**3,  # 500 GB
        )
        mock_psutil.net_connections.return_value = [MagicMock()] * 150  # 150 connections

        metrics = scan_system_metrics()

        assert metrics.cpu_percent == 35.5
        assert metrics.memory_percent == 60.0
        assert metrics.memory_used_mb == pytest.approx(4 * 1024, rel=0.01)
        assert metrics.disk_percent == 45.0
        assert metrics.network_connections == 150


# ===================================================================
# scan_local (full integration, all mocked)
# ===================================================================


class TestScanLocal:
    """Tests for scan_local() with fully mocked psutil."""

    @patch("faultray.discovery.scanner.scan_established_connections")
    @patch("faultray.discovery.scanner.scan_system_metrics")
    @patch("faultray.discovery.scanner.scan_listening_services")
    @patch("faultray.discovery.scanner.socket")
    def test_scan_local_builds_graph(
        self, mock_socket, mock_listening, mock_metrics, mock_established,
    ):
        mock_socket.gethostname.return_value = "testhost"

        mock_listening.return_value = [
            {"port": 5432, "address": "0.0.0.0", "pid": 100, "process": "postgres"},
            {"port": 6379, "address": "0.0.0.0", "pid": 200, "process": "redis-server"},
            {"port": 8080, "address": "0.0.0.0", "pid": 300, "process": "node"},
        ]

        mock_metrics.return_value = ResourceMetrics(
            cpu_percent=25.0,
            memory_percent=50.0,
            memory_used_mb=4096.0,
            memory_total_mb=8192.0,
            disk_percent=40.0,
            disk_used_gb=200.0,
            disk_total_gb=500.0,
            network_connections=50,
        )

        # app (8080) connects to postgres (5432) and redis (6379)
        mock_established.return_value = [
            {"local_port": 8080, "remote_host": "127.0.0.1", "remote_port": 5432, "pid": 300},
            {"local_port": 8080, "remote_host": "127.0.0.1", "remote_port": 6379, "pid": 300},
        ]

        graph = scan_local()

        # 3 components
        assert len(graph.components) == 3

        # Check types
        pg_id = "testhost:postgresql:5432"
        redis_id = "testhost:redis:6379"
        app_id = "testhost:app-8080:8080"

        pg = graph.get_component(pg_id)
        assert pg is not None
        assert pg.type == ComponentType.DATABASE

        redis_comp = graph.get_component(redis_id)
        assert redis_comp is not None
        assert redis_comp.type == ComponentType.CACHE

        app = graph.get_component(app_id)
        assert app is not None
        assert app.type == ComponentType.APP_SERVER

        # Dependencies: app -> postgres and app -> redis
        app_deps = graph.get_dependencies(app_id)
        dep_ids = [d.id for d in app_deps]
        assert pg_id in dep_ids
        assert redis_id in dep_ids

    @patch("faultray.discovery.scanner.scan_established_connections")
    @patch("faultray.discovery.scanner.scan_system_metrics")
    @patch("faultray.discovery.scanner.scan_listening_services")
    @patch("faultray.discovery.scanner.socket")
    def test_scan_local_custom_hostname(
        self, mock_socket, mock_listening, mock_metrics, mock_established,
    ):
        mock_listening.return_value = [
            {"port": 80, "address": "0.0.0.0", "pid": 1, "process": "nginx"},
        ]
        mock_metrics.return_value = ResourceMetrics(
            cpu_percent=10.0,
            memory_percent=30.0,
            memory_used_mb=2048.0,
            memory_total_mb=4096.0,
            disk_percent=20.0,
            disk_used_gb=50.0,
            disk_total_gb=250.0,
            network_connections=20,
        )
        mock_established.return_value = []

        graph = scan_local(hostname="myserver")

        assert len(graph.components) == 1
        comp = graph.get_component("myserver:http:80")
        assert comp is not None
        assert comp.host == "myserver"

    @patch("faultray.discovery.scanner.scan_established_connections")
    @patch("faultray.discovery.scanner.scan_system_metrics")
    @patch("faultray.discovery.scanner.scan_listening_services")
    @patch("faultray.discovery.scanner.socket")
    def test_scan_local_no_self_dependency(
        self, mock_socket, mock_listening, mock_metrics, mock_established,
    ):
        mock_socket.gethostname.return_value = "host"
        mock_listening.return_value = [
            {"port": 8080, "address": "0.0.0.0", "pid": 1, "process": "app"},
        ]
        mock_metrics.return_value = ResourceMetrics(
            cpu_percent=0, memory_percent=0, memory_used_mb=0,
            memory_total_mb=0, disk_percent=0, disk_used_gb=0,
            disk_total_gb=0, network_connections=0,
        )
        # Connection from port 8080 to itself (same port)
        mock_established.return_value = [
            {"local_port": 8080, "remote_host": "127.0.0.1", "remote_port": 8080, "pid": 1},
        ]

        graph = scan_local()

        comp_id = "host:app-8080:8080"
        deps = graph.get_dependencies(comp_id)
        # Should not have a self-dependency
        assert all(d.id != comp_id for d in deps)

    @patch("faultray.discovery.scanner.scan_established_connections")
    @patch("faultray.discovery.scanner.scan_system_metrics")
    @patch("faultray.discovery.scanner.scan_listening_services")
    @patch("faultray.discovery.scanner.socket")
    def test_scan_local_empty(
        self, mock_socket, mock_listening, mock_metrics, mock_established,
    ):
        mock_socket.gethostname.return_value = "empty"
        mock_listening.return_value = []
        mock_metrics.return_value = ResourceMetrics(
            cpu_percent=0, memory_percent=0, memory_used_mb=0,
            memory_total_mb=0, disk_percent=0, disk_used_gb=0,
            disk_total_gb=0, network_connections=0,
        )
        mock_established.return_value = []

        graph = scan_local()
        assert len(graph.components) == 0
