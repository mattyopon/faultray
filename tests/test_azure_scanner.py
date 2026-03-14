"""Tests for Azure auto-discovery scanner.

All azure-mgmt calls are mocked -- tests work without actual Azure credentials.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from infrasim.model.components import ComponentType
from infrasim.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scanner(subscription_id: str = "sub-123", resource_group: str | None = None):
    """Import and instantiate AzureScanner."""
    from infrasim.discovery.azure_scanner import AzureScanner
    return AzureScanner(subscription_id=subscription_id, resource_group=resource_group)


def _mock_azure_modules(**extra_modules):
    """Create a sys.modules patch dict for Azure imports.

    Sets up azure / azure.identity / azure.mgmt.* with a consistent mock
    hierarchy so that imports resolve correctly.
    """
    mock_identity = extra_modules.pop("identity", MagicMock())
    mock_compute = extra_modules.pop("compute", MagicMock())
    mock_sql = extra_modules.pop("sql", MagicMock())
    mock_redis = extra_modules.pop("redis", MagicMock())
    mock_network = extra_modules.pop("network", MagicMock())
    mock_storage = extra_modules.pop("storage", MagicMock())
    mock_web = extra_modules.pop("web", MagicMock())
    mock_containerservice = extra_modules.pop("containerservice", MagicMock())
    mock_servicebus = extra_modules.pop("servicebus", MagicMock())
    mock_dns = extra_modules.pop("dns", MagicMock())

    mock_azure = MagicMock()
    mock_azure.identity = mock_identity
    mock_mgmt = MagicMock()
    mock_mgmt.compute = mock_compute
    mock_mgmt.sql = mock_sql
    mock_mgmt.redis = mock_redis
    mock_mgmt.network = mock_network
    mock_mgmt.storage = mock_storage
    mock_mgmt.web = mock_web
    mock_mgmt.containerservice = mock_containerservice
    mock_mgmt.servicebus = mock_servicebus
    mock_mgmt.dns = mock_dns

    modules = {
        "azure": mock_azure,
        "azure.identity": mock_identity,
        "azure.mgmt": mock_mgmt,
        "azure.mgmt.compute": mock_compute,
        "azure.mgmt.sql": mock_sql,
        "azure.mgmt.redis": mock_redis,
        "azure.mgmt.network": mock_network,
        "azure.mgmt.storage": mock_storage,
        "azure.mgmt.web": mock_web,
        "azure.mgmt.containerservice": mock_containerservice,
        "azure.mgmt.servicebus": mock_servicebus,
        "azure.mgmt.dns": mock_dns,
    }
    modules.update(extra_modules)
    return modules


def _mock_vm(name: str = "web-vm-1", location: str = "eastus", vm_size: str = "Standard_D2s_v3"):
    """Create a mock Azure VM object."""
    vm = MagicMock()
    vm.name = name
    vm.location = location
    hw = MagicMock()
    hw.vm_size = vm_size
    vm.hardware_profile = hw
    nic_ref = MagicMock()
    nic_ref.id = f"/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Network/networkInterfaces/{name}-nic"
    net_profile = MagicMock()
    net_profile.network_interfaces = [nic_ref]
    vm.network_profile = net_profile
    return vm


def _mock_sql_server(name: str = "sql-server-1", location: str = "eastus"):
    """Create a mock Azure SQL Server."""
    server = MagicMock()
    server.name = name
    server.location = location
    server.fully_qualified_domain_name = f"{name}.database.windows.net"
    server.id = f"/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Sql/servers/{name}"
    return server


def _mock_sql_db(name: str = "mydb", sku_name: str = "S0"):
    """Create a mock Azure SQL Database."""
    db = MagicMock()
    db.name = name
    sku = MagicMock()
    sku.name = sku_name
    db.sku = sku
    return db


def _mock_redis_cache(name: str = "redis-1", location: str = "eastus", sku_name: str = "Standard"):
    """Create a mock Azure Redis Cache."""
    cache = MagicMock()
    cache.name = name
    cache.location = location
    cache.host_name = f"{name}.redis.cache.windows.net"
    cache.ssl_port = 6380
    sku = MagicMock()
    sku.name = sku_name
    cache.sku = sku
    cache.shard_count = 0
    return cache


def _mock_app_service(name: str = "webapp-1", kind: str = "app", location: str = "eastus"):
    """Create a mock Azure App Service."""
    app = MagicMock()
    app.name = name
    app.kind = kind
    app.location = location
    app.default_host_name = f"{name}.azurewebsites.net"
    return app


def _mock_aks_cluster(name: str = "aks-1", location: str = "eastus", node_count: int = 3):
    """Create a mock AKS cluster."""
    cluster = MagicMock()
    cluster.name = name
    cluster.location = location
    cluster.fqdn = f"{name}.hcp.eastus.azmk8s.io"
    cluster.kubernetes_version = "1.28.0"
    pool = MagicMock()
    pool.count = node_count
    pool.availability_zones = ["1", "2", "3"]
    pool.enable_auto_scaling = True
    cluster.agent_pool_profiles = [pool]
    return cluster


def _mock_load_balancer(name: str = "lb-1", location: str = "eastus", sku_name: str = "Standard"):
    """Create a mock Azure Load Balancer."""
    lb = MagicMock()
    lb.name = name
    lb.location = location
    sku = MagicMock()
    sku.name = sku_name
    lb.sku = sku
    return lb


def _mock_storage_account(name: str = "storageacct1", location: str = "eastus", sku_name: str = "Standard_LRS"):
    """Create a mock Azure Storage Account."""
    account = MagicMock()
    account.name = name
    account.location = location
    sku = MagicMock()
    sku.name = sku_name
    account.sku = sku
    return account


def _mock_service_bus_namespace(name: str = "sb-ns-1", location: str = "eastus", sku_tier: str = "Standard"):
    """Create a mock Service Bus namespace."""
    ns = MagicMock()
    ns.name = name
    ns.location = location
    sku = MagicMock()
    sku.tier = sku_tier
    ns.sku = sku
    return ns


def _mock_dns_zone(name: str = "example.com"):
    """Create a mock Azure DNS zone."""
    zone = MagicMock()
    zone.name = name
    return zone


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAzureScannerInstantiation:
    """Test AzureScanner can be instantiated."""

    def test_create_scanner(self):
        scanner = _make_scanner()
        assert scanner.subscription_id == "sub-123"
        assert scanner.resource_group is None

    def test_create_scanner_with_resource_group(self):
        scanner = _make_scanner(resource_group="my-rg")
        assert scanner.resource_group == "my-rg"


class TestAzureLibCheck:
    """Test graceful handling of missing azure-identity."""

    def test_missing_azure_identity_raises(self):
        from infrasim.discovery.azure_scanner import _check_azure_libs

        with patch.dict(sys.modules, {"azure": None, "azure.identity": None}):
            with pytest.raises(RuntimeError, match="azure-identity"):
                _check_azure_libs()


class TestScanVirtualMachines:
    """Test VM scanning."""

    def test_scan_discovers_vms(self):
        mock_modules = _mock_azure_modules()
        vm = _mock_vm()
        mock_modules["azure.mgmt.compute"].ComputeManagementClient.return_value.virtual_machines.list_all.return_value = [vm]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_virtual_machines(graph)

        assert "azvm-web-vm-1" in graph.components
        comp = graph.components["azvm-web-vm-1"]
        assert comp.type == ComponentType.APP_SERVER
        assert comp.name == "web-vm-1"

    def test_scan_vms_with_resource_group(self):
        mock_modules = _mock_azure_modules()
        vm = _mock_vm(name="rg-vm")
        mock_modules["azure.mgmt.compute"].ComputeManagementClient.return_value.virtual_machines.list.return_value = [vm]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner(resource_group="my-rg")
            graph = InfraGraph()
            scanner._scan_virtual_machines(graph)

        assert "azvm-rg-vm" in graph.components

    def test_scan_vms_error_adds_warning(self):
        mock_modules = _mock_azure_modules()
        mock_modules["azure.mgmt.compute"].ComputeManagementClient.return_value.virtual_machines.list_all.side_effect = Exception("API error")

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_virtual_machines(graph)

        assert len(scanner._warnings) > 0
        assert "API error" in scanner._warnings[0]


class TestScanSqlDatabases:
    """Test SQL Database scanning."""

    def test_scan_discovers_sql_databases(self):
        mock_modules = _mock_azure_modules()
        server = _mock_sql_server()
        db = _mock_sql_db()

        sql_client = mock_modules["azure.mgmt.sql"].SqlManagementClient.return_value
        sql_client.servers.list.return_value = [server]
        sql_client.databases.list_by_server.return_value = [db]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_sql_databases(graph)

        assert "azsql-sql-server-1-mydb" in graph.components
        comp = graph.components["azsql-sql-server-1-mydb"]
        assert comp.type == ComponentType.DATABASE
        assert comp.port == 1433

    def test_skips_master_database(self):
        mock_modules = _mock_azure_modules()
        server = _mock_sql_server()
        master_db = _mock_sql_db(name="master")

        sql_client = mock_modules["azure.mgmt.sql"].SqlManagementClient.return_value
        sql_client.servers.list.return_value = [server]
        sql_client.databases.list_by_server.return_value = [master_db]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_sql_databases(graph)

        assert len(graph.components) == 0


class TestScanRedisCache:
    """Test Redis Cache scanning."""

    def test_scan_discovers_redis(self):
        mock_modules = _mock_azure_modules()
        cache = _mock_redis_cache()

        redis_client = mock_modules["azure.mgmt.redis"].RedisManagementClient.return_value
        redis_client.redis.list_by_subscription.return_value = [cache]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_redis_cache(graph)

        assert "azredis-redis-1" in graph.components
        comp = graph.components["azredis-redis-1"]
        assert comp.type == ComponentType.CACHE
        assert comp.port == 6380
        assert comp.replicas == 2  # Standard SKU


class TestScanAppService:
    """Test App Service / Functions scanning."""

    def test_scan_discovers_app_service(self):
        mock_modules = _mock_azure_modules()
        app = _mock_app_service()

        web_client = mock_modules["azure.mgmt.web"].WebSiteManagementClient.return_value
        web_client.web_apps.list.return_value = [app]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_app_service(graph)

        assert "azapp-webapp-1" in graph.components
        comp = graph.components["azapp-webapp-1"]
        assert comp.type == ComponentType.APP_SERVER
        assert "azure_app_service" in comp.tags

    def test_scan_discovers_function_app(self):
        mock_modules = _mock_azure_modules()
        func_app = _mock_app_service(name="func-1", kind="functionapp")

        web_client = mock_modules["azure.mgmt.web"].WebSiteManagementClient.return_value
        web_client.web_apps.list.return_value = [func_app]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_app_service(graph)

        assert "azfunc-func-1" in graph.components
        comp = graph.components["azfunc-func-1"]
        assert "azure_function" in comp.tags


class TestScanAKS:
    """Test AKS cluster scanning."""

    def test_scan_discovers_aks_cluster(self):
        mock_modules = _mock_azure_modules()
        cluster = _mock_aks_cluster()

        aks_client = mock_modules["azure.mgmt.containerservice"].ContainerServiceClient.return_value
        aks_client.managed_clusters.list.return_value = [cluster]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_aks(graph)

        assert "azaks-aks-1" in graph.components
        comp = graph.components["azaks-aks-1"]
        assert comp.type == ComponentType.APP_SERVER
        assert comp.replicas == 3


class TestScanLoadBalancer:
    """Test Load Balancer scanning."""

    def test_scan_discovers_load_balancer(self):
        mock_modules = _mock_azure_modules()
        lb = _mock_load_balancer()

        net_client = mock_modules["azure.mgmt.network"].NetworkManagementClient.return_value
        net_client.load_balancers.list_all.return_value = [lb]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_load_balancer(graph)

        assert "azlb-lb-1" in graph.components
        comp = graph.components["azlb-lb-1"]
        assert comp.type == ComponentType.LOAD_BALANCER
        assert comp.replicas == 2  # Standard SKU


class TestScanStorage:
    """Test Storage Account scanning."""

    def test_scan_discovers_storage(self):
        mock_modules = _mock_azure_modules()
        account = _mock_storage_account()

        storage_client = mock_modules["azure.mgmt.storage"].StorageManagementClient.return_value
        storage_client.storage_accounts.list.return_value = [account]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_storage(graph)

        assert "azstore-storageacct1" in graph.components
        comp = graph.components["azstore-storageacct1"]
        assert comp.type == ComponentType.STORAGE

    def test_grs_storage_has_more_replicas(self):
        mock_modules = _mock_azure_modules()
        account = _mock_storage_account(sku_name="Standard_GRS")

        storage_client = mock_modules["azure.mgmt.storage"].StorageManagementClient.return_value
        storage_client.storage_accounts.list.return_value = [account]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_storage(graph)

        comp = graph.components["azstore-storageacct1"]
        assert comp.replicas == 3


class TestScanServiceBus:
    """Test Service Bus scanning."""

    def test_scan_discovers_service_bus(self):
        mock_modules = _mock_azure_modules()
        ns = _mock_service_bus_namespace()

        sb_client = mock_modules["azure.mgmt.servicebus"].ServiceBusManagementClient.return_value
        sb_client.namespaces.list.return_value = [ns]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_service_bus(graph)

        assert "azsb-sb-ns-1" in graph.components
        comp = graph.components["azsb-sb-ns-1"]
        assert comp.type == ComponentType.QUEUE


class TestScanDNS:
    """Test DNS zone scanning."""

    def test_scan_discovers_dns_zones(self):
        mock_modules = _mock_azure_modules()
        zone = _mock_dns_zone()

        dns_client = mock_modules["azure.mgmt.dns"].DnsManagementClient.return_value
        dns_client.zones.list.return_value = [zone]

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()
            scanner._scan_dns(graph)

        assert "azdns-example.com" in graph.components
        comp = graph.components["azdns-example.com"]
        assert comp.type == ComponentType.DNS
        assert comp.replicas == 4


class TestInferDependencies:
    """Test dependency inference logic."""

    def test_infers_lb_to_app_dependency(self):
        mock_modules = _mock_azure_modules()
        net_client = mock_modules["azure.mgmt.network"].NetworkManagementClient.return_value
        net_client.network_security_groups.list_all.return_value = []

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()

            # Add LB and App Server manually
            from infrasim.model.components import Component
            graph.add_component(Component(
                id="azlb-lb1", name="lb1", type=ComponentType.LOAD_BALANCER, port=443,
            ))
            graph.add_component(Component(
                id="azapp-app1", name="app1", type=ComponentType.APP_SERVER, port=443,
            ))

            scanner._infer_dependencies(graph)

        deps = graph.all_dependency_edges()
        assert len(deps) >= 1
        assert any(d.source_id == "azlb-lb1" and d.target_id == "azapp-app1" for d in deps)

    def test_infers_app_to_db_dependency(self):
        mock_modules = _mock_azure_modules()
        net_client = mock_modules["azure.mgmt.network"].NetworkManagementClient.return_value
        net_client.network_security_groups.list_all.return_value = []

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            graph = InfraGraph()

            from infrasim.model.components import Component
            graph.add_component(Component(
                id="azapp-app1", name="app1", type=ComponentType.APP_SERVER, port=443,
            ))
            graph.add_component(Component(
                id="azsql-db1", name="db1", type=ComponentType.DATABASE, port=1433,
            ))

            scanner._infer_dependencies(graph)

        deps = graph.all_dependency_edges()
        assert any(d.source_id == "azapp-app1" and d.target_id == "azsql-db1" for d in deps)


class TestDetectSecurity:
    """Test security profile detection."""

    def test_https_port_sets_encryption_in_transit(self):
        scanner = _make_scanner()
        graph = InfraGraph()

        from infrasim.model.components import Component
        graph.add_component(Component(
            id="azapp-app1", name="app1", type=ComponentType.APP_SERVER, port=443,
        ))

        scanner._detect_security(graph)
        assert graph.components["azapp-app1"].security.encryption_in_transit is True

    def test_sql_gets_encryption_at_rest(self):
        scanner = _make_scanner()
        graph = InfraGraph()

        from infrasim.model.components import Component
        graph.add_component(Component(
            id="azsql-db1", name="db1", type=ComponentType.DATABASE, port=1433,
            tags=["azure_sql"],
        ))

        scanner._detect_security(graph)
        assert graph.components["azsql-db1"].security.encryption_at_rest is True


class TestFullScan:
    """Test full scan orchestration."""

    def test_full_scan_returns_result(self):
        mock_modules = _mock_azure_modules()

        # Set up empty returns for all services
        compute_client = mock_modules["azure.mgmt.compute"].ComputeManagementClient.return_value
        compute_client.virtual_machines.list_all.return_value = [_mock_vm()]

        sql_client = mock_modules["azure.mgmt.sql"].SqlManagementClient.return_value
        sql_client.servers.list.return_value = []

        redis_client = mock_modules["azure.mgmt.redis"].RedisManagementClient.return_value
        redis_client.redis.list_by_subscription.return_value = []

        web_client = mock_modules["azure.mgmt.web"].WebSiteManagementClient.return_value
        web_client.web_apps.list.return_value = []

        aks_client = mock_modules["azure.mgmt.containerservice"].ContainerServiceClient.return_value
        aks_client.managed_clusters.list.return_value = []

        net_client = mock_modules["azure.mgmt.network"].NetworkManagementClient.return_value
        net_client.load_balancers.list_all.return_value = []
        net_client.network_security_groups.list_all.return_value = []

        storage_client = mock_modules["azure.mgmt.storage"].StorageManagementClient.return_value
        storage_client.storage_accounts.list.return_value = []

        sb_client = mock_modules["azure.mgmt.servicebus"].ServiceBusManagementClient.return_value
        sb_client.namespaces.list.return_value = []

        dns_client = mock_modules["azure.mgmt.dns"].DnsManagementClient.return_value
        dns_client.zones.list.return_value = []

        with patch.dict(sys.modules, mock_modules):
            scanner = _make_scanner()
            result = scanner.scan()

        assert result.subscription_id == "sub-123"
        assert result.components_found >= 1
        assert result.scan_duration_seconds >= 0


class TestExtractResourceGroup:
    """Test resource group extraction from resource ID."""

    def test_extracts_resource_group(self):
        from infrasim.discovery.azure_scanner import _extract_resource_group

        rid = "/subscriptions/sub-123/resourceGroups/my-rg/providers/Microsoft.Sql/servers/srv1"
        assert _extract_resource_group(rid) == "my-rg"

    def test_returns_empty_for_invalid_id(self):
        from infrasim.discovery.azure_scanner import _extract_resource_group

        assert _extract_resource_group("") == ""
        assert _extract_resource_group("/subscriptions/sub-123") == ""
