"""Tests for GCP auto-discovery scanner.

All google-cloud calls are mocked — tests work without actual GCP credentials.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scanner(project_id: str = "my-project"):
    """Import and instantiate GCPScanner (ensures module is importable)."""
    from faultray.discovery.gcp_scanner import GCPScanner
    return GCPScanner(project_id=project_id)


def _mock_compute_instance(
    name: str = "web-server-1",
    instance_id: int = 12345,
    status: str = "RUNNING",
    machine_type: str = "zones/us-central1-a/machineTypes/n1-standard-1",
    ip: str = "10.0.0.2",
    network: str = "projects/my-project/global/networks/default",
    tags: list[str] | None = None,
):
    """Create a mock Compute Engine instance."""
    inst = MagicMock()
    inst.name = name
    inst.id = instance_id
    inst.status = status
    inst.machine_type = machine_type

    nic = MagicMock()
    nic.network_i_p = ip
    nic.network = network
    inst.network_interfaces = [nic]

    tag_obj = MagicMock()
    tag_obj.items = tags or []
    inst.tags = tag_obj

    return inst


def _mock_firewall_rule(
    name: str = "allow-web",
    direction: str = "INGRESS",
    disabled: bool = False,
    source_tags: list[str] | None = None,
    target_tags: list[str] | None = None,
    ports: list[str] | None = None,
    network: str = "projects/my-project/global/networks/default",
):
    """Create a mock firewall rule."""
    rule = MagicMock()
    rule.name = name
    rule.direction = direction
    rule.disabled = disabled
    rule.source_tags = source_tags or []
    rule.target_tags = target_tags or []
    rule.network = network

    allowed = MagicMock()
    allowed.ports = ports or []
    rule.allowed = [allowed]

    return rule


def _patch_gcp_modules(**extra_modules):
    """Create a sys.modules patch dict for GCP imports.

    Sets up google / google.cloud / google.cloud.compute_v1 with a consistent
    mock hierarchy so that ``from google.cloud import compute_v1`` resolves
    correctly.

    Extra modules (e.g. ``google.cloud.sql_v1``) can be passed as keyword
    arguments.  Their values are also wired onto the ``google.cloud`` mock.
    """
    mock_compute_v1 = extra_modules.pop("compute_v1", MagicMock())
    mock_google_cloud = MagicMock()
    mock_google_cloud.compute_v1 = mock_compute_v1
    mock_google = MagicMock()
    mock_google.cloud = mock_google_cloud

    modules = {
        "google": mock_google,
        "google.cloud": mock_google_cloud,
        "google.cloud.compute_v1": mock_compute_v1,
    }

    for mod_name, mock_obj in extra_modules.items():
        # e.g. mod_name = "google.cloud.sql_v1"
        attr = mod_name.split(".")[-1]
        setattr(mock_google_cloud, attr, mock_obj)
        modules[mod_name] = mock_obj

    return modules, mock_compute_v1, mock_google_cloud


def _reload_scanner(modules_dict):
    """Reload the gcp_scanner module with patched sys.modules and return it."""
    with patch.dict(sys.modules, modules_dict):
        import faultray.discovery.gcp_scanner as gcp_mod
        importlib.reload(gcp_mod)
        return gcp_mod


# ---------------------------------------------------------------------------
# Tests: Module import and initialization
# ---------------------------------------------------------------------------

class TestGCPScannerInit:
    """Tests for GCPScanner initialization and import handling."""

    def test_scanner_init(self):
        scanner = _make_scanner("test-project")
        assert scanner.project_id == "test-project"

    def test_gcp_type_map(self):
        from faultray.discovery.gcp_scanner import GCP_TYPE_MAP
        assert GCP_TYPE_MAP["compute"] == ComponentType.APP_SERVER
        assert GCP_TYPE_MAP["cloud_sql"] == ComponentType.DATABASE
        assert GCP_TYPE_MAP["memorystore"] == ComponentType.CACHE
        assert GCP_TYPE_MAP["cloud_load_balancing"] == ComponentType.LOAD_BALANCER
        assert GCP_TYPE_MAP["gke"] == ComponentType.APP_SERVER
        assert GCP_TYPE_MAP["cloud_storage"] == ComponentType.STORAGE
        assert GCP_TYPE_MAP["pub_sub"] == ComponentType.QUEUE
        assert GCP_TYPE_MAP["cloud_dns"] == ComponentType.DNS
        assert GCP_TYPE_MAP["cloud_run"] == ComponentType.APP_SERVER
        assert GCP_TYPE_MAP["cloud_functions"] == ComponentType.APP_SERVER

    def test_import_error_graceful(self):
        """Test that missing google-cloud libraries raise a clear RuntimeError."""
        from faultray.discovery.gcp_scanner import _check_gcp_libs

        with patch("builtins.__import__", side_effect=ImportError("No module named 'google.cloud.compute_v1'")):
            with pytest.raises(RuntimeError, match="google-cloud-compute is required"):
                _check_gcp_libs()

    def test_discovery_result_dataclass(self):
        from faultray.discovery.gcp_scanner import GCPDiscoveryResult
        result = GCPDiscoveryResult(
            project_id="test-project",
            components_found=5,
            dependencies_inferred=3,
            graph=InfraGraph(),
        )
        assert result.project_id == "test-project"
        assert result.components_found == 5
        assert result.dependencies_inferred == 3
        assert result.warnings == []
        assert result.scan_duration_seconds == 0.0


# ---------------------------------------------------------------------------
# Tests: Compute Engine scanning
# ---------------------------------------------------------------------------

class TestComputeEngineScanning:
    """Tests for Compute Engine instance discovery."""

    def test_scan_compute_instances(self):
        """Test that Compute Engine instances are discovered correctly."""
        graph = InfraGraph()

        inst = _mock_compute_instance(name="web-1", ip="10.0.0.5")
        zone_response = MagicMock()
        zone_response.instances = [inst]

        mock_compute_v1 = MagicMock()
        mock_client = MagicMock()
        mock_client.aggregated_list.return_value = [
            ("zones/us-central1-a", zone_response),
        ]
        mock_compute_v1.InstancesClient.return_value = mock_client

        modules, _, _ = _patch_gcp_modules(compute_v1=mock_compute_v1)

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_compute_instances(graph)

        assert "gce-web-1" in graph.components
        comp = graph.components["gce-web-1"]
        assert comp.type == ComponentType.APP_SERVER
        assert comp.host == "10.0.0.5"

    def test_scan_compute_skips_non_running(self):
        """Test that stopped instances are skipped."""
        graph = InfraGraph()

        inst = _mock_compute_instance(name="stopped-vm", status="TERMINATED")
        zone_response = MagicMock()
        zone_response.instances = [inst]

        mock_compute_v1 = MagicMock()
        mock_client = MagicMock()
        mock_client.aggregated_list.return_value = [
            ("zones/us-central1-a", zone_response),
        ]
        mock_compute_v1.InstancesClient.return_value = mock_client

        modules, _, _ = _patch_gcp_modules(compute_v1=mock_compute_v1)

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_compute_instances(graph)

        assert len(graph.components) == 0

    def test_scan_compute_tags_tracked(self):
        """Test that network tags are tracked for dependency inference."""
        graph = InfraGraph()

        inst = _mock_compute_instance(name="app-1", tags=["web", "api"])
        zone_response = MagicMock()
        zone_response.instances = [inst]

        mock_compute_v1 = MagicMock()
        mock_client = MagicMock()
        mock_client.aggregated_list.return_value = [
            ("zones/us-central1-a", zone_response),
        ]
        mock_compute_v1.InstancesClient.return_value = mock_client

        modules, _, _ = _patch_gcp_modules(compute_v1=mock_compute_v1)

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_compute_instances(graph)

        assert scanner._component_tags["gce-app-1"] == ["web", "api"]

    def test_scan_compute_empty_zone(self):
        """Test that zones with no instances are skipped."""
        graph = InfraGraph()

        zone_response = MagicMock()
        zone_response.instances = None

        mock_compute_v1 = MagicMock()
        mock_client = MagicMock()
        mock_client.aggregated_list.return_value = [
            ("zones/us-central1-a", zone_response),
        ]
        mock_compute_v1.InstancesClient.return_value = mock_client

        modules, _, _ = _patch_gcp_modules(compute_v1=mock_compute_v1)

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_compute_instances(graph)

        assert len(graph.components) == 0


# ---------------------------------------------------------------------------
# Tests: Cloud SQL scanning
# ---------------------------------------------------------------------------

class TestCloudSQLScanning:
    """Tests for Cloud SQL discovery."""

    def test_scan_cloud_sql(self):
        """Test Cloud SQL instance discovery."""
        graph = InfraGraph()

        mock_instance = MagicMock()
        mock_instance.name = "my-postgres-db"
        mock_instance.database_version = "POSTGRES_14"
        mock_instance.region = "us-central1"

        settings = MagicMock()
        settings.availability_type = "REGIONAL"
        backup_cfg = MagicMock()
        backup_cfg.enabled = True
        settings.backup_configuration = backup_cfg
        mock_instance.settings = settings

        ip_addr = MagicMock()
        ip_addr.type_ = "PRIVATE"
        ip_addr.ip_address = "10.0.1.5"
        mock_instance.ip_addresses = [ip_addr]

        mock_sql_module = MagicMock()
        mock_sql_client = MagicMock()
        mock_sql_client.list.return_value = [mock_instance]
        mock_sql_module.SqlInstancesServiceClient.return_value = mock_sql_client

        modules, _, _ = _patch_gcp_modules(**{"google.cloud.sql_v1": mock_sql_module})

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_cloud_sql(graph)

        assert "cloudsql-my-postgres-db" in graph.components
        comp = graph.components["cloudsql-my-postgres-db"]
        assert comp.type == ComponentType.DATABASE
        assert comp.port == 5432
        assert comp.replicas == 2
        assert comp.failover.enabled is True
        assert comp.security.backup_enabled is True
        assert comp.host == "10.0.1.5"

    def test_scan_cloud_sql_mysql(self):
        """Test MySQL Cloud SQL detection."""
        graph = InfraGraph()

        mock_instance = MagicMock()
        mock_instance.name = "my-mysql-db"
        mock_instance.database_version = "MYSQL_8_0"
        mock_instance.region = "us-central1"
        mock_instance.settings = MagicMock()
        mock_instance.settings.availability_type = "ZONAL"
        mock_instance.settings.backup_configuration = None
        mock_instance.ip_addresses = []

        mock_sql_module = MagicMock()
        mock_sql_client = MagicMock()
        mock_sql_client.list.return_value = [mock_instance]
        mock_sql_module.SqlInstancesServiceClient.return_value = mock_sql_client

        modules, _, _ = _patch_gcp_modules(**{"google.cloud.sql_v1": mock_sql_module})

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_cloud_sql(graph)

        comp = graph.components["cloudsql-my-mysql-db"]
        assert comp.port == 3306
        assert comp.replicas == 1


# ---------------------------------------------------------------------------
# Tests: Memorystore scanning
# ---------------------------------------------------------------------------

class TestMemorystoreScanning:
    """Tests for Memorystore (Redis) discovery."""

    def test_scan_memorystore(self):
        """Test Memorystore instance discovery."""
        graph = InfraGraph()

        mock_instance = MagicMock()
        mock_instance.name = "projects/my-project/locations/us-central1/instances/my-redis"
        mock_instance.tier = "STANDARD"
        mock_instance.replica_count = 2
        mock_instance.host = "10.0.2.3"
        mock_instance.port = 6379
        mock_instance.location_id = "us-central1"
        mock_instance.transit_encryption_mode = 1

        mock_redis_v1 = MagicMock()
        mock_redis_client = MagicMock()
        mock_redis_client.list_instances.return_value = [mock_instance]
        mock_redis_v1.CloudRedisClient.return_value = mock_redis_client

        modules, _, _ = _patch_gcp_modules(**{"google.cloud.redis_v1": mock_redis_v1})

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_memorystore(graph)

        assert "memorystore-my-redis" in graph.components
        comp = graph.components["memorystore-my-redis"]
        assert comp.type == ComponentType.CACHE
        assert comp.replicas == 3
        assert comp.failover.enabled is True
        assert comp.security.encryption_in_transit is True


# ---------------------------------------------------------------------------
# Tests: Cloud Load Balancing scanning
# ---------------------------------------------------------------------------

class TestCloudLoadBalancingScanning:
    """Tests for Cloud Load Balancing discovery."""

    def test_scan_load_balancing(self):
        """Test forwarding rule discovery."""
        graph = InfraGraph()

        mock_rule = MagicMock()
        mock_rule.name = "my-lb-rule"
        mock_rule.port_range = "443-443"
        mock_rule.I_p_address = "34.120.0.1"

        mock_compute_v1 = MagicMock()
        mock_fw_client = MagicMock()
        mock_fw_client.list.return_value = [mock_rule]
        mock_compute_v1.GlobalForwardingRulesClient.return_value = mock_fw_client

        modules, _, _ = _patch_gcp_modules(compute_v1=mock_compute_v1)

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_cloud_load_balancing(graph)

        assert "gclb-my-lb-rule" in graph.components
        comp = graph.components["gclb-my-lb-rule"]
        assert comp.type == ComponentType.LOAD_BALANCER
        assert comp.port == 443
        assert comp.replicas == 3


# ---------------------------------------------------------------------------
# Tests: GKE scanning
# ---------------------------------------------------------------------------

class TestGKEScanning:
    """Tests for GKE cluster discovery."""

    def test_scan_gke_cluster(self):
        """Test GKE cluster discovery."""
        graph = InfraGraph()

        mock_pool = MagicMock()
        mock_pool.initial_node_count = 3
        mock_pool.autoscaling = MagicMock()
        mock_pool.autoscaling.enabled = True

        mock_cluster = MagicMock()
        mock_cluster.name = "prod-cluster"
        mock_cluster.endpoint = "35.224.0.1"
        mock_cluster.location = "us-central1"
        mock_cluster.locations = ["us-central1-a", "us-central1-b", "us-central1-c"]
        mock_cluster.node_pools = [mock_pool]
        mock_cluster.current_master_version = "1.28.3-gke.1"

        mock_response = MagicMock()
        mock_response.clusters = [mock_cluster]

        mock_container_v1 = MagicMock()
        mock_gke_client = MagicMock()
        mock_gke_client.list_clusters.return_value = mock_response
        mock_container_v1.ClusterManagerClient.return_value = mock_gke_client

        modules, _, _ = _patch_gcp_modules(**{"google.cloud.container_v1": mock_container_v1})

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_gke(graph)

        assert "gke-prod-cluster" in graph.components
        comp = graph.components["gke-prod-cluster"]
        assert comp.type == ComponentType.APP_SERVER
        assert comp.replicas == 3
        assert comp.failover.enabled is True
        assert comp.autoscaling.enabled is True


# ---------------------------------------------------------------------------
# Tests: Cloud Storage scanning
# ---------------------------------------------------------------------------

class TestCloudStorageScanning:
    """Tests for Cloud Storage (GCS) discovery."""

    def test_scan_gcs_bucket(self):
        """Test GCS bucket discovery."""
        graph = InfraGraph()

        mock_bucket = MagicMock()
        mock_bucket.name = "my-data-bucket"
        mock_bucket.versioning_enabled = True
        mock_bucket.location = "US"
        mock_bucket.default_kms_key_name = "projects/my-project/locations/global/keyRings/kr/cryptoKeys/key"

        mock_storage = MagicMock()
        mock_storage_client = MagicMock()
        mock_storage_client.list_buckets.return_value = [mock_bucket]
        mock_storage.Client.return_value = mock_storage_client

        modules, _, _ = _patch_gcp_modules(**{"google.cloud.storage": mock_storage})

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_cloud_storage(graph)

        assert "gcs-my-data-bucket" in graph.components
        comp = graph.components["gcs-my-data-bucket"]
        assert comp.type == ComponentType.STORAGE
        assert comp.replicas == 3
        assert comp.security.encryption_at_rest is True
        assert comp.security.backup_enabled is True


# ---------------------------------------------------------------------------
# Tests: Pub/Sub scanning
# ---------------------------------------------------------------------------

class TestPubSubScanning:
    """Tests for Pub/Sub discovery."""

    def test_scan_pubsub_topic(self):
        """Test Pub/Sub topic discovery."""
        graph = InfraGraph()

        mock_topic = MagicMock()
        mock_topic.name = "projects/my-project/topics/events-topic"

        mock_pubsub_v1 = MagicMock()
        mock_publisher = MagicMock()
        mock_publisher.list_topics.return_value = [mock_topic]
        mock_pubsub_v1.PublisherClient.return_value = mock_publisher

        modules, _, _ = _patch_gcp_modules(**{"google.cloud.pubsub_v1": mock_pubsub_v1})

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_pub_sub(graph)

        assert "pubsub-events-topic" in graph.components
        comp = graph.components["pubsub-events-topic"]
        assert comp.type == ComponentType.QUEUE
        assert comp.replicas == 3


# ---------------------------------------------------------------------------
# Tests: Cloud DNS scanning
# ---------------------------------------------------------------------------

class TestCloudDNSScanning:
    """Tests for Cloud DNS discovery."""

    def test_scan_cloud_dns(self):
        """Test Cloud DNS managed zone discovery."""
        graph = InfraGraph()

        mock_zone = MagicMock()
        mock_zone.name = "my-zone"
        mock_zone.dns_name = "example.com."

        mock_dns = MagicMock()
        mock_dns_client = MagicMock()
        mock_dns_client.list_zones.return_value = [mock_zone]
        mock_dns.Client.return_value = mock_dns_client

        modules, _, _ = _patch_gcp_modules(**{"google.cloud.dns": mock_dns})

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_cloud_dns(graph)

        assert "clouddns-my-zone" in graph.components
        comp = graph.components["clouddns-my-zone"]
        assert comp.type == ComponentType.DNS
        assert comp.replicas == 4


# ---------------------------------------------------------------------------
# Tests: Cloud Run scanning
# ---------------------------------------------------------------------------

class TestCloudRunScanning:
    """Tests for Cloud Run discovery."""

    def test_scan_cloud_run(self):
        """Test Cloud Run service discovery."""
        graph = InfraGraph()

        scaling = MagicMock()
        scaling.min_instance_count = 1
        scaling.max_instance_count = 50

        template = MagicMock()
        template.scaling = scaling

        mock_service = MagicMock()
        mock_service.name = "projects/my-project/locations/us-central1/services/api-service"
        mock_service.uri = "https://api-service-xxx.run.app"
        mock_service.template = template

        mock_run_v2 = MagicMock()
        mock_run_client = MagicMock()
        mock_run_client.list_services.return_value = [mock_service]
        mock_run_v2.ServicesClient.return_value = mock_run_client

        modules, _, _ = _patch_gcp_modules(**{"google.cloud.run_v2": mock_run_v2})

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_cloud_run(graph)

        assert "cloudrun-api-service" in graph.components
        comp = graph.components["cloudrun-api-service"]
        assert comp.type == ComponentType.APP_SERVER
        assert comp.autoscaling.enabled is True
        assert comp.autoscaling.min_replicas == 1
        assert comp.autoscaling.max_replicas == 50
        assert comp.security.encryption_in_transit is True


# ---------------------------------------------------------------------------
# Tests: Cloud Functions scanning
# ---------------------------------------------------------------------------

class TestCloudFunctionsScanning:
    """Tests for Cloud Functions discovery."""

    def test_scan_cloud_functions(self):
        """Test Cloud Functions discovery."""
        graph = InfraGraph()

        svc_cfg = MagicMock()
        svc_cfg.available_memory = "512M"
        svc_cfg.timeout_seconds = 120

        build_cfg = MagicMock()
        build_cfg.runtime = "python311"

        mock_func = MagicMock()
        mock_func.name = "projects/my-project/locations/us-central1/functions/process-data"
        mock_func.service_config = svc_cfg
        mock_func.build_config = build_cfg

        mock_functions_v2 = MagicMock()
        mock_func_client = MagicMock()
        mock_func_client.list_functions.return_value = [mock_func]
        mock_functions_v2.FunctionServiceClient.return_value = mock_func_client

        modules, _, _ = _patch_gcp_modules(**{"google.cloud.functions_v2": mock_functions_v2})

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._scan_cloud_functions(graph)

        assert "gcf-process-data" in graph.components
        comp = graph.components["gcf-process-data"]
        assert comp.type == ComponentType.APP_SERVER
        assert comp.capacity.max_memory_mb == 512.0
        assert comp.capacity.timeout_seconds == 120.0
        assert comp.autoscaling.enabled is True


# ---------------------------------------------------------------------------
# Tests: Dependency inference
# ---------------------------------------------------------------------------

class TestDependencyInference:
    """Tests for firewall-rule-based dependency inference."""

    def test_infer_dependencies_from_firewall_rules(self):
        """Test dependency inference from VPC firewall rules."""
        graph = InfraGraph()

        comp_web = Component(id="gce-web", name="web", type=ComponentType.APP_SERVER)
        comp_db = Component(id="gce-db", name="db", type=ComponentType.DATABASE)
        graph.add_component(comp_web)
        graph.add_component(comp_db)

        fw_rule = _mock_firewall_rule(
            source_tags=["web-tag"],
            target_tags=["db-tag"],
            ports=["5432"],
        )

        mock_compute_v1 = MagicMock()
        mock_fw_client = MagicMock()
        mock_fw_client.list.return_value = [fw_rule]
        mock_compute_v1.FirewallsClient.return_value = mock_fw_client

        modules, _, _ = _patch_gcp_modules(compute_v1=mock_compute_v1)

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._component_tags = {
                "gce-web": ["web-tag"],
                "gce-db": ["db-tag"],
            }
            scanner._infer_dependencies(graph)

        edges = graph.all_dependency_edges()
        assert len(edges) == 1
        assert edges[0].source_id == "gce-web"
        assert edges[0].target_id == "gce-db"
        assert edges[0].dependency_type == "requires"
        assert edges[0].port == 5432

    def test_infer_dependencies_optional_for_non_db_ports(self):
        """Test that non-DB ports create optional dependencies."""
        graph = InfraGraph()

        comp_a = Component(id="gce-a", name="a", type=ComponentType.APP_SERVER)
        comp_b = Component(id="gce-b", name="b", type=ComponentType.APP_SERVER)
        graph.add_component(comp_a)
        graph.add_component(comp_b)

        fw_rule = _mock_firewall_rule(
            source_tags=["frontend"],
            target_tags=["backend"],
            ports=["8080"],
        )

        mock_compute_v1 = MagicMock()
        mock_fw_client = MagicMock()
        mock_fw_client.list.return_value = [fw_rule]
        mock_compute_v1.FirewallsClient.return_value = mock_fw_client

        modules, _, _ = _patch_gcp_modules(compute_v1=mock_compute_v1)

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._component_tags = {
                "gce-a": ["frontend"],
                "gce-b": ["backend"],
            }
            scanner._infer_dependencies(graph)

        edges = graph.all_dependency_edges()
        assert len(edges) == 1
        assert edges[0].dependency_type == "optional"

    def test_infer_dependencies_skips_egress_rules(self):
        """Test that EGRESS firewall rules are ignored."""
        graph = InfraGraph()

        comp_a = Component(id="gce-a", name="a", type=ComponentType.APP_SERVER)
        comp_b = Component(id="gce-b", name="b", type=ComponentType.APP_SERVER)
        graph.add_component(comp_a)
        graph.add_component(comp_b)

        fw_rule = _mock_firewall_rule(
            direction="EGRESS",
            source_tags=["frontend"],
            target_tags=["backend"],
            ports=["8080"],
        )

        mock_compute_v1 = MagicMock()
        mock_fw_client = MagicMock()
        mock_fw_client.list.return_value = [fw_rule]
        mock_compute_v1.FirewallsClient.return_value = mock_fw_client

        modules, _, _ = _patch_gcp_modules(compute_v1=mock_compute_v1)

        with patch.dict(sys.modules, modules):
            gcp_mod = _reload_scanner(modules)
            scanner = gcp_mod.GCPScanner(project_id="my-project")
            scanner._component_tags = {
                "gce-a": ["frontend"],
                "gce-b": ["backend"],
            }
            scanner._infer_dependencies(graph)

        assert len(graph.all_dependency_edges()) == 0


# ---------------------------------------------------------------------------
# Tests: Security detection
# ---------------------------------------------------------------------------

class TestSecurityDetection:
    """Tests for security profile enrichment."""

    def test_detect_security_network_segmented(self):
        """Test that components with network tags get network_segmented=True."""
        scanner = _make_scanner()
        graph = InfraGraph()

        comp = Component(id="gce-web", name="web", type=ComponentType.APP_SERVER)
        graph.add_component(comp)
        scanner._component_tags = {"gce-web": ["web-tag"]}

        scanner._detect_security(graph)
        assert graph.components["gce-web"].security.network_segmented is True

    def test_detect_security_encryption_in_transit(self):
        """Test that HTTPS components get encryption_in_transit=True."""
        scanner = _make_scanner()
        graph = InfraGraph()

        comp = Component(id="gclb-rule", name="lb", type=ComponentType.LOAD_BALANCER, port=443)
        graph.add_component(comp)

        scanner._detect_security(graph)
        assert graph.components["gclb-rule"].security.encryption_in_transit is True

    def test_detect_security_no_tags_not_segmented(self):
        """Test that components without tags are not marked as segmented."""
        scanner = _make_scanner()
        graph = InfraGraph()

        comp = Component(id="gce-plain", name="plain", type=ComponentType.APP_SERVER)
        graph.add_component(comp)
        scanner._component_tags = {}

        scanner._detect_security(graph)
        assert graph.components["gce-plain"].security.network_segmented is False


# ---------------------------------------------------------------------------
# Tests: Full scan integration
# ---------------------------------------------------------------------------

class TestFullScan:
    """Tests for the full scan() method."""

    @patch("faultray.discovery.gcp_scanner._check_gcp_libs")
    def test_full_scan_empty(self, mock_check):
        """Test full scan with no resources."""
        scanner = _make_scanner()

        with patch.object(scanner, "_scan_compute_instances"), \
             patch.object(scanner, "_scan_cloud_sql"), \
             patch.object(scanner, "_scan_memorystore"), \
             patch.object(scanner, "_scan_cloud_load_balancing"), \
             patch.object(scanner, "_scan_cloud_run"), \
             patch.object(scanner, "_scan_gke"), \
             patch.object(scanner, "_scan_cloud_storage"), \
             patch.object(scanner, "_scan_pub_sub"), \
             patch.object(scanner, "_scan_cloud_dns"), \
             patch.object(scanner, "_scan_cloud_functions"), \
             patch.object(scanner, "_infer_dependencies"), \
             patch.object(scanner, "_detect_security"):
            result = scanner.scan()

        assert result.project_id == "my-project"
        assert result.components_found == 0
        assert result.dependencies_inferred == 0
        assert result.scan_duration_seconds >= 0

    @patch("faultray.discovery.gcp_scanner._check_gcp_libs")
    def test_full_scan_warnings_on_error(self, mock_check):
        """Test that scan errors are captured as warnings."""
        scanner = _make_scanner()

        with patch.object(scanner, "_scan_compute_instances", side_effect=ValueError("test error")), \
             patch.object(scanner, "_scan_cloud_sql"), \
             patch.object(scanner, "_scan_memorystore"), \
             patch.object(scanner, "_scan_cloud_load_balancing"), \
             patch.object(scanner, "_scan_cloud_run"), \
             patch.object(scanner, "_scan_gke"), \
             patch.object(scanner, "_scan_cloud_storage"), \
             patch.object(scanner, "_scan_pub_sub"), \
             patch.object(scanner, "_scan_cloud_dns"), \
             patch.object(scanner, "_scan_cloud_functions"), \
             patch.object(scanner, "_infer_dependencies"), \
             patch.object(scanner, "_detect_security"):
            result = scanner.scan()

        assert len(result.warnings) >= 1
        assert "Compute Engine" in result.warnings[0]

    @patch("faultray.discovery.gcp_scanner._check_gcp_libs")
    def test_runtime_error_propagates(self, mock_check):
        """Test that RuntimeError (import errors) propagates through scan()."""
        scanner = _make_scanner()

        with patch.object(scanner, "_scan_compute_instances", side_effect=RuntimeError("import error")):
            with pytest.raises(RuntimeError, match="import error"):
                scanner.scan()

    @patch("faultray.discovery.gcp_scanner._check_gcp_libs")
    def test_scan_duration_recorded(self, mock_check):
        """Test that scan duration is recorded."""
        scanner = _make_scanner()

        with patch.object(scanner, "_scan_compute_instances"), \
             patch.object(scanner, "_scan_cloud_sql"), \
             patch.object(scanner, "_scan_memorystore"), \
             patch.object(scanner, "_scan_cloud_load_balancing"), \
             patch.object(scanner, "_scan_cloud_run"), \
             patch.object(scanner, "_scan_gke"), \
             patch.object(scanner, "_scan_cloud_storage"), \
             patch.object(scanner, "_scan_pub_sub"), \
             patch.object(scanner, "_scan_cloud_dns"), \
             patch.object(scanner, "_scan_cloud_functions"), \
             patch.object(scanner, "_infer_dependencies"), \
             patch.object(scanner, "_detect_security"):
            result = scanner.scan()

        assert result.scan_duration_seconds >= 0.0

    @patch("faultray.discovery.gcp_scanner._check_gcp_libs")
    def test_scan_missing_optional_libs_warning(self, mock_check):
        """Test that missing optional libs produce warnings, not crashes."""
        scanner = _make_scanner()

        with patch.object(scanner, "_scan_compute_instances"), \
             patch.object(scanner, "_scan_cloud_sql", side_effect=ValueError("lib missing")), \
             patch.object(scanner, "_scan_memorystore"), \
             patch.object(scanner, "_scan_cloud_load_balancing"), \
             patch.object(scanner, "_scan_cloud_run"), \
             patch.object(scanner, "_scan_gke"), \
             patch.object(scanner, "_scan_cloud_storage"), \
             patch.object(scanner, "_scan_pub_sub"), \
             patch.object(scanner, "_scan_cloud_dns"), \
             patch.object(scanner, "_scan_cloud_functions"), \
             patch.object(scanner, "_infer_dependencies"), \
             patch.object(scanner, "_detect_security"):
            result = scanner.scan()

        assert any("Cloud SQL" in w for w in result.warnings)
