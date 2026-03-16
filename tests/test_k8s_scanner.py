"""Tests for Kubernetes auto-discovery scanner.

All kubernetes client calls are mocked — tests work without an actual cluster.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from faultray.model.components import ComponentType, Dependency
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scanner(context: str | None = None, namespace: str | None = None):
    """Import and instantiate K8sScanner."""
    from faultray.discovery.k8s_scanner import K8sScanner
    return K8sScanner(context=context, namespace=namespace)


def _mock_deployment(
    name: str = "api-server",
    namespace: str = "production",
    replicas: int = 3,
    labels: dict | None = None,
    selector_labels: dict | None = None,
):
    """Create a mock Kubernetes Deployment."""
    deploy = MagicMock()
    deploy.metadata.name = name
    deploy.metadata.namespace = namespace
    deploy.metadata.labels = labels or {"app": name}
    deploy.spec.replicas = replicas

    selector = MagicMock()
    selector.match_labels = selector_labels or {"app": name}
    deploy.spec.selector = selector

    return deploy


def _mock_statefulset(
    name: str = "postgres",
    namespace: str = "production",
    replicas: int = 3,
    labels: dict | None = None,
    selector_labels: dict | None = None,
):
    """Create a mock Kubernetes StatefulSet."""
    sts = MagicMock()
    sts.metadata.name = name
    sts.metadata.namespace = namespace
    sts.metadata.labels = labels or {"app": name}
    sts.spec.replicas = replicas

    selector = MagicMock()
    selector.match_labels = selector_labels or {"app": name}
    sts.spec.selector = selector

    return sts


def _mock_service(
    name: str = "api-service",
    namespace: str = "production",
    selector: dict | None = None,
    port: int = 80,
):
    """Create a mock Kubernetes Service."""
    svc = MagicMock()
    svc.metadata.name = name
    svc.metadata.namespace = namespace
    svc.spec.selector = selector or {"app": "api-server"}

    svc_port = MagicMock()
    svc_port.port = port
    svc.spec.ports = [svc_port]

    return svc


def _mock_ingress(
    name: str = "main-ingress",
    namespace: str = "production",
    host: str = "api.example.com",
    has_tls: bool = True,
    backend_service: str = "api-service",
):
    """Create a mock Kubernetes Ingress."""
    ingress = MagicMock()
    ingress.metadata.name = name
    ingress.metadata.namespace = namespace

    # Rules
    backend = MagicMock()
    backend.service.name = backend_service

    path = MagicMock()
    path.backend = backend

    http = MagicMock()
    http.paths = [path]

    rule = MagicMock()
    rule.host = host
    rule.http = http

    ingress.spec.rules = [rule]

    # TLS
    if has_tls:
        tls = MagicMock()
        ingress.spec.tls = [tls]
    else:
        ingress.spec.tls = None

    return ingress


def _mock_hpa(
    name: str = "api-hpa",
    namespace: str = "production",
    target_kind: str = "Deployment",
    target_name: str = "api-server",
    min_replicas: int = 2,
    max_replicas: int = 10,
    cpu_threshold: int = 80,
):
    """Create a mock HorizontalPodAutoscaler."""
    hpa = MagicMock()
    hpa.metadata.name = name
    hpa.metadata.namespace = namespace

    target_ref = MagicMock()
    target_ref.kind = target_kind
    target_ref.name = target_name
    hpa.spec.scale_target_ref = target_ref

    hpa.spec.min_replicas = min_replicas
    hpa.spec.max_replicas = max_replicas

    # CPU metric
    metric = MagicMock()
    metric.type = "Resource"
    metric.resource.name = "cpu"
    metric.resource.target.average_utilization = cpu_threshold
    hpa.spec.metrics = [metric]

    return hpa


def _mock_pdb(
    name: str = "api-pdb",
    namespace: str = "production",
    selector_labels: dict | None = None,
    min_available: int | None = 2,
    max_unavailable: int | None = None,
):
    """Create a mock PodDisruptionBudget."""
    pdb = MagicMock()
    pdb.metadata.name = name
    pdb.metadata.namespace = namespace

    selector = MagicMock()
    selector.match_labels = selector_labels or {"app": "api-server"}
    pdb.spec.selector = selector

    pdb.spec.min_available = min_available
    pdb.spec.max_unavailable = max_unavailable

    return pdb


def _mock_network_policy(
    name: str = "deny-all",
    namespace: str = "production",
    selector_labels: dict | None = None,
):
    """Create a mock NetworkPolicy."""
    policy = MagicMock()
    policy.metadata.name = name
    policy.metadata.namespace = namespace

    pod_selector = MagicMock()
    pod_selector.match_labels = selector_labels or {"app": "api-server"}
    policy.spec.pod_selector = pod_selector

    return policy


def _mock_k8s_client():
    """Create a mock kubernetes client module."""
    mock_client = MagicMock()
    mock_config = MagicMock()
    return mock_client, mock_config


# ---------------------------------------------------------------------------
# Tests: Module import and initialization
# ---------------------------------------------------------------------------

class TestK8sScannerInit:
    """Tests for K8sScanner initialization and import handling."""

    def test_scanner_init_defaults(self):
        scanner = _make_scanner()
        assert scanner.context is None
        assert scanner.namespace is None

    def test_scanner_init_with_context(self):
        scanner = _make_scanner(context="my-cluster", namespace="production")
        assert scanner.context == "my-cluster"
        assert scanner.namespace == "production"

    def test_import_error_graceful(self):
        """Test that missing kubernetes library raises a clear RuntimeError."""
        from faultray.discovery.k8s_scanner import _check_k8s_lib

        with patch("builtins.__import__", side_effect=ImportError("No module named 'kubernetes'")):
            with pytest.raises(RuntimeError, match="kubernetes is required"):
                _check_k8s_lib()

    def test_discovery_result_dataclass(self):
        from faultray.discovery.k8s_scanner import K8sDiscoveryResult
        result = K8sDiscoveryResult(
            context="my-cluster",
            namespace="production",
            components_found=5,
            dependencies_inferred=3,
            graph=InfraGraph(),
        )
        assert result.context == "my-cluster"
        assert result.namespace == "production"
        assert result.components_found == 5
        assert result.warnings == []

    def test_looks_like_database(self):
        from faultray.discovery.k8s_scanner import _looks_like_database
        assert _looks_like_database("postgres-primary") is True
        assert _looks_like_database("mysql-master") is True
        assert _looks_like_database("redis-cache") is True
        assert _looks_like_database("mongodb") is True
        assert _looks_like_database("api-server") is False
        assert _looks_like_database("web-frontend") is False
        assert _looks_like_database("app", {"app.kubernetes.io/name": "postgresql"}) is True


# ---------------------------------------------------------------------------
# Tests: Deployment scanning
# ---------------------------------------------------------------------------

class TestDeploymentScanning:
    """Tests for Deployment discovery."""

    def test_scan_deployments(self):
        """Test that Deployments are discovered correctly."""
        scanner = _make_scanner(namespace="production")
        graph = InfraGraph()

        deploy = _mock_deployment(name="api-server", replicas=3)

        mock_client = MagicMock()
        mock_apps_v1 = MagicMock()
        response = MagicMock()
        response.items = [deploy]
        mock_apps_v1.list_namespaced_deployment.return_value = response
        mock_client.AppsV1Api.return_value = mock_apps_v1

        with patch.object(scanner, "_get_api_client", return_value=mock_client):
            scanner._scan_deployments(graph)

        assert "deploy-production-api-server" in graph.components
        comp = graph.components["deploy-production-api-server"]
        assert comp.type == ComponentType.APP_SERVER
        assert comp.replicas == 3
        assert "deployment" in comp.tags

    def test_scan_deployment_database_heuristic(self):
        """Test that deployments with DB names get DATABASE type."""
        scanner = _make_scanner(namespace="production")
        graph = InfraGraph()

        deploy = _mock_deployment(name="redis-cache", replicas=1)

        mock_client = MagicMock()
        mock_apps_v1 = MagicMock()
        response = MagicMock()
        response.items = [deploy]
        mock_apps_v1.list_namespaced_deployment.return_value = response
        mock_client.AppsV1Api.return_value = mock_apps_v1

        with patch.object(scanner, "_get_api_client", return_value=mock_client):
            scanner._scan_deployments(graph)

        comp = graph.components["deploy-production-redis-cache"]
        assert comp.type == ComponentType.DATABASE


# ---------------------------------------------------------------------------
# Tests: StatefulSet scanning
# ---------------------------------------------------------------------------

class TestStatefulSetScanning:
    """Tests for StatefulSet discovery."""

    def test_scan_statefulsets(self):
        """Test that StatefulSets are discovered correctly."""
        scanner = _make_scanner(namespace="production")
        graph = InfraGraph()

        sts = _mock_statefulset(name="postgres", replicas=3)

        mock_client = MagicMock()
        mock_apps_v1 = MagicMock()
        response = MagicMock()
        response.items = [sts]
        mock_apps_v1.list_namespaced_stateful_set.return_value = response
        mock_client.AppsV1Api.return_value = mock_apps_v1

        with patch.object(scanner, "_get_api_client", return_value=mock_client):
            scanner._scan_statefulsets(graph)

        assert "sts-production-postgres" in graph.components
        comp = graph.components["sts-production-postgres"]
        assert comp.type == ComponentType.DATABASE  # name matches DB pattern
        assert comp.replicas == 3
        assert comp.failover.enabled is True  # replicas > 1

    def test_scan_statefulset_non_database(self):
        """Test StatefulSet that is not a database."""
        scanner = _make_scanner(namespace="production")
        graph = InfraGraph()

        sts = _mock_statefulset(name="zookeeper", replicas=3)

        mock_client = MagicMock()
        mock_apps_v1 = MagicMock()
        response = MagicMock()
        response.items = [sts]
        mock_apps_v1.list_namespaced_stateful_set.return_value = response
        mock_client.AppsV1Api.return_value = mock_apps_v1

        with patch.object(scanner, "_get_api_client", return_value=mock_client):
            scanner._scan_statefulsets(graph)

        comp = graph.components["sts-production-zookeeper"]
        assert comp.type == ComponentType.APP_SERVER  # Not in DB pattern


# ---------------------------------------------------------------------------
# Tests: Service scanning
# ---------------------------------------------------------------------------

class TestServiceScanning:
    """Tests for Service discovery."""

    def test_scan_services_records_selectors(self):
        """Test that Service selectors are recorded for dependency inference."""
        scanner = _make_scanner(namespace="production")
        graph = InfraGraph()

        svc = _mock_service(name="api-service", selector={"app": "api-server"})

        mock_client = MagicMock()
        mock_core_v1 = MagicMock()
        response = MagicMock()
        response.items = [svc]
        mock_core_v1.list_namespaced_service.return_value = response
        mock_client.CoreV1Api.return_value = mock_core_v1

        with patch.object(scanner, "_get_api_client", return_value=mock_client):
            scanner._scan_services(graph)

        assert "svc-production-api-service" in scanner._service_selectors
        assert scanner._service_selectors["svc-production-api-service"] == {"app": "api-server"}

    def test_scan_services_skips_kubernetes_svc(self):
        """Test that the default 'kubernetes' service is skipped."""
        scanner = _make_scanner()
        graph = InfraGraph()

        svc = _mock_service(name="kubernetes", namespace="default")

        mock_client = MagicMock()
        mock_core_v1 = MagicMock()
        response = MagicMock()
        response.items = [svc]
        mock_core_v1.list_service_for_all_namespaces.return_value = response
        mock_client.CoreV1Api.return_value = mock_core_v1

        with patch.object(scanner, "_get_api_client", return_value=mock_client):
            scanner._scan_services(graph)

        assert "svc-default-kubernetes" not in scanner._service_selectors


# ---------------------------------------------------------------------------
# Tests: Ingress scanning
# ---------------------------------------------------------------------------

class TestIngressScanning:
    """Tests for Ingress discovery."""

    def test_scan_ingresses(self):
        """Test that Ingresses are discovered as LOAD_BALANCER components."""
        scanner = _make_scanner(namespace="production")
        graph = InfraGraph()

        ingress = _mock_ingress(name="main-ingress", host="api.example.com", has_tls=True)

        mock_client = MagicMock()
        mock_net_v1 = MagicMock()
        response = MagicMock()
        response.items = [ingress]
        mock_net_v1.list_namespaced_ingress.return_value = response
        mock_client.NetworkingV1Api.return_value = mock_net_v1

        with patch.object(scanner, "_get_api_client", return_value=mock_client):
            scanner._scan_ingresses(graph)

        assert "ingress-production-main-ingress" in graph.components
        comp = graph.components["ingress-production-main-ingress"]
        assert comp.type == ComponentType.LOAD_BALANCER
        assert comp.host == "api.example.com"
        assert comp.port == 443
        assert comp.security.encryption_in_transit is True

    def test_scan_ingress_no_tls(self):
        """Test ingress without TLS."""
        scanner = _make_scanner(namespace="production")
        graph = InfraGraph()

        ingress = _mock_ingress(name="http-ingress", has_tls=False)

        mock_client = MagicMock()
        mock_net_v1 = MagicMock()
        response = MagicMock()
        response.items = [ingress]
        mock_net_v1.list_namespaced_ingress.return_value = response
        mock_client.NetworkingV1Api.return_value = mock_net_v1

        with patch.object(scanner, "_get_api_client", return_value=mock_client):
            scanner._scan_ingresses(graph)

        comp = graph.components["ingress-production-http-ingress"]
        assert comp.port == 80
        assert comp.security.encryption_in_transit is False


# ---------------------------------------------------------------------------
# Tests: HPA scanning
# ---------------------------------------------------------------------------

class TestHPAScanning:
    """Tests for HorizontalPodAutoscaler discovery."""

    def test_scan_hpa(self):
        """Test HPA discovery and application to target components."""
        scanner = _make_scanner(namespace="production")
        graph = InfraGraph()

        hpa = _mock_hpa(
            target_kind="Deployment",
            target_name="api-server",
            min_replicas=2,
            max_replicas=10,
            cpu_threshold=80,
        )

        mock_client = MagicMock()
        mock_autoscaling = MagicMock()
        response = MagicMock()
        response.items = [hpa]
        mock_autoscaling.list_namespaced_horizontal_pod_autoscaler.return_value = response
        mock_client.AutoscalingV2Api.return_value = mock_autoscaling

        with patch.object(scanner, "_get_api_client", return_value=mock_client):
            scanner._scan_hpa(graph)

        target_id = "deploy-production-api-server"
        assert target_id in scanner._hpa_configs
        hpa_config = scanner._hpa_configs[target_id]
        assert hpa_config.enabled is True
        assert hpa_config.min_replicas == 2
        assert hpa_config.max_replicas == 10
        assert hpa_config.scale_up_threshold == 80.0

    def test_apply_hpa_to_component(self):
        """Test that HPA config is applied to matching component."""
        scanner = _make_scanner()
        graph = InfraGraph()

        from faultray.model.components import Component, AutoScalingConfig

        comp = Component(id="deploy-prod-api", name="prod/api", type=ComponentType.APP_SERVER, replicas=3)
        graph.add_component(comp)

        scanner._hpa_configs = {
            "deploy-prod-api": AutoScalingConfig(
                enabled=True, min_replicas=2, max_replicas=20
            )
        }

        scanner._apply_hpa(graph)

        updated = graph.components["deploy-prod-api"]
        assert updated.autoscaling.enabled is True
        assert updated.autoscaling.min_replicas == 2
        assert updated.autoscaling.max_replicas == 20


# ---------------------------------------------------------------------------
# Tests: PDB scanning
# ---------------------------------------------------------------------------

class TestPDBScanning:
    """Tests for PodDisruptionBudget discovery."""

    def test_scan_pdb(self):
        """Test PDB discovery and label matching."""
        scanner = _make_scanner(namespace="production")
        graph = InfraGraph()

        pdb = _mock_pdb(
            selector_labels={"app": "api-server"},
            min_available=2,
        )

        # Pre-populate workload labels (normally set by deployment scan)
        scanner._workload_labels = {
            "deploy-production-api-server": {"app": "api-server"},
        }

        mock_client = MagicMock()
        mock_policy = MagicMock()
        response = MagicMock()
        response.items = [pdb]
        mock_policy.list_namespaced_pod_disruption_budget.return_value = response
        mock_client.PolicyV1Api.return_value = mock_policy

        with patch.object(scanner, "_get_api_client", return_value=mock_client):
            scanner._scan_pdb(graph)

        assert "deploy-production-api-server" in scanner._pdb_configs
        assert scanner._pdb_configs["deploy-production-api-server"]["min_available"] == 2

    def test_apply_pdb_enables_failover(self):
        """Test that PDB config enables failover on matching components."""
        scanner = _make_scanner()
        graph = InfraGraph()

        from faultray.model.components import Component

        comp = Component(id="deploy-prod-api", name="prod/api", type=ComponentType.APP_SERVER, replicas=3)
        graph.add_component(comp)

        scanner._pdb_configs = {
            "deploy-prod-api": {"min_available": 2, "max_unavailable": None}
        }

        scanner._apply_pdb(graph)

        updated = graph.components["deploy-prod-api"]
        assert updated.failover.enabled is True
        assert any("pdb:minAvailable=2" in t for t in updated.tags)


# ---------------------------------------------------------------------------
# Tests: NetworkPolicy scanning
# ---------------------------------------------------------------------------

class TestNetworkPolicyScanning:
    """Tests for NetworkPolicy discovery."""

    def test_scan_network_policies(self):
        """Test NetworkPolicy discovery and label matching."""
        scanner = _make_scanner(namespace="production")
        graph = InfraGraph()

        from faultray.model.components import Component
        comp = Component(
            id="deploy-production-api-server", name="production/api-server",
            type=ComponentType.APP_SERVER, tags=["deployment", "namespace:production"]
        )
        graph.add_component(comp)

        policy = _mock_network_policy(selector_labels={"app": "api-server"})

        scanner._workload_labels = {
            "deploy-production-api-server": {"app": "api-server"},
        }

        mock_client = MagicMock()
        mock_net_v1 = MagicMock()
        response = MagicMock()
        response.items = [policy]
        mock_net_v1.list_namespaced_network_policy.return_value = response
        mock_client.NetworkingV1Api.return_value = mock_net_v1

        with patch.object(scanner, "_get_api_client", return_value=mock_client):
            scanner._scan_network_policies(graph)

        assert "deploy-production-api-server" in scanner._network_policies

    def test_apply_network_policies_sets_segmented(self):
        """Test that NetworkPolicy sets network_segmented=True."""
        scanner = _make_scanner()
        graph = InfraGraph()

        from faultray.model.components import Component

        comp = Component(id="deploy-prod-api", name="prod/api", type=ComponentType.APP_SERVER)
        graph.add_component(comp)

        scanner._network_policies = {"deploy-prod-api"}

        scanner._apply_network_policies(graph)

        assert graph.components["deploy-prod-api"].security.network_segmented is True


# ---------------------------------------------------------------------------
# Tests: Dependency inference
# ---------------------------------------------------------------------------

class TestDependencyInference:
    """Tests for service-selector-based dependency inference."""

    def test_infer_ingress_to_workload_dependency(self):
        """Test dependency from ingress to workload via service selector."""
        scanner = _make_scanner()
        graph = InfraGraph()

        from faultray.model.components import Component

        # Add ingress and workload
        ingress = Component(
            id="ingress-production-main", name="production/main",
            type=ComponentType.LOAD_BALANCER, tags=["ingress", "namespace:production"]
        )
        deploy = Component(
            id="deploy-production-api", name="production/api",
            type=ComponentType.APP_SERVER, tags=["deployment", "namespace:production"]
        )
        graph.add_component(ingress)
        graph.add_component(deploy)

        scanner._service_selectors = {
            "svc-production-api-service": {"app": "api"},
        }
        scanner._workload_labels = {
            "deploy-production-api": {"app": "api"},
        }

        scanner._infer_dependencies(graph)

        edges = graph.all_dependency_edges()
        assert len(edges) >= 1
        found = any(
            e.source_id == "ingress-production-main" and e.target_id == "deploy-production-api"
            for e in edges
        )
        assert found

    def test_infer_workload_to_database_dependency(self):
        """Test dependency from app workload to database workload."""
        scanner = _make_scanner()
        graph = InfraGraph()

        from faultray.model.components import Component

        app = Component(
            id="deploy-production-api", name="production/api",
            type=ComponentType.APP_SERVER, tags=["deployment", "namespace:production"]
        )
        db = Component(
            id="sts-production-postgres", name="production/postgres",
            type=ComponentType.DATABASE, port=5432, tags=["statefulset", "namespace:production"]
        )
        graph.add_component(app)
        graph.add_component(db)

        scanner._service_selectors = {
            "svc-production-postgres": {"app": "postgres"},
        }
        scanner._workload_labels = {
            "deploy-production-api": {"app": "api"},
            "sts-production-postgres": {"app": "postgres"},
        }

        scanner._infer_dependencies(graph)

        edges = graph.all_dependency_edges()
        found = any(
            e.source_id == "deploy-production-api" and e.target_id == "sts-production-postgres"
            for e in edges
        )
        assert found


# ---------------------------------------------------------------------------
# Tests: Full scan integration
# ---------------------------------------------------------------------------

class TestFullScan:
    """Tests for the full scan() method."""

    @patch("faultray.discovery.k8s_scanner._check_k8s_lib")
    def test_full_scan_empty(self, mock_check):
        """Test full scan with no resources."""
        scanner = _make_scanner()

        with patch.object(scanner, "_scan_deployments"), \
             patch.object(scanner, "_scan_statefulsets"), \
             patch.object(scanner, "_scan_services"), \
             patch.object(scanner, "_scan_ingresses"), \
             patch.object(scanner, "_scan_hpa"), \
             patch.object(scanner, "_scan_pdb"), \
             patch.object(scanner, "_scan_network_policies"), \
             patch.object(scanner, "_apply_hpa"), \
             patch.object(scanner, "_apply_pdb"), \
             patch.object(scanner, "_apply_network_policies"), \
             patch.object(scanner, "_infer_dependencies"):
            result = scanner.scan()

        assert result.context is None
        assert result.namespace is None
        assert result.components_found == 0
        assert result.dependencies_inferred == 0

    @patch("faultray.discovery.k8s_scanner._check_k8s_lib")
    def test_full_scan_with_context(self, mock_check):
        """Test full scan with context and namespace."""
        scanner = _make_scanner(context="my-cluster", namespace="production")

        with patch.object(scanner, "_scan_deployments"), \
             patch.object(scanner, "_scan_statefulsets"), \
             patch.object(scanner, "_scan_services"), \
             patch.object(scanner, "_scan_ingresses"), \
             patch.object(scanner, "_scan_hpa"), \
             patch.object(scanner, "_scan_pdb"), \
             patch.object(scanner, "_scan_network_policies"), \
             patch.object(scanner, "_apply_hpa"), \
             patch.object(scanner, "_apply_pdb"), \
             patch.object(scanner, "_apply_network_policies"), \
             patch.object(scanner, "_infer_dependencies"):
            result = scanner.scan()

        assert result.context == "my-cluster"
        assert result.namespace == "production"

    @patch("faultray.discovery.k8s_scanner._check_k8s_lib")
    def test_full_scan_warnings_on_error(self, mock_check):
        """Test that scan errors are captured as warnings."""
        scanner = _make_scanner()

        with patch.object(scanner, "_scan_deployments", side_effect=ValueError("test error")), \
             patch.object(scanner, "_scan_statefulsets"), \
             patch.object(scanner, "_scan_services"), \
             patch.object(scanner, "_scan_ingresses"), \
             patch.object(scanner, "_scan_hpa"), \
             patch.object(scanner, "_scan_pdb"), \
             patch.object(scanner, "_scan_network_policies"), \
             patch.object(scanner, "_apply_hpa"), \
             patch.object(scanner, "_apply_pdb"), \
             patch.object(scanner, "_apply_network_policies"), \
             patch.object(scanner, "_infer_dependencies"):
            result = scanner.scan()

        assert len(result.warnings) >= 1
        assert "Deployments" in result.warnings[0]

    @patch("faultray.discovery.k8s_scanner._check_k8s_lib")
    def test_runtime_error_propagates(self, mock_check):
        """Test that RuntimeError (import errors) propagates through scan()."""
        scanner = _make_scanner()

        with patch.object(scanner, "_scan_deployments", side_effect=RuntimeError("import error")):
            with pytest.raises(RuntimeError, match="import error"):
                scanner.scan()

    @patch("faultray.discovery.k8s_scanner._check_k8s_lib")
    def test_scan_duration_recorded(self, mock_check):
        """Test that scan duration is recorded."""
        scanner = _make_scanner()

        with patch.object(scanner, "_scan_deployments"), \
             patch.object(scanner, "_scan_statefulsets"), \
             patch.object(scanner, "_scan_services"), \
             patch.object(scanner, "_scan_ingresses"), \
             patch.object(scanner, "_scan_hpa"), \
             patch.object(scanner, "_scan_pdb"), \
             patch.object(scanner, "_scan_network_policies"), \
             patch.object(scanner, "_apply_hpa"), \
             patch.object(scanner, "_apply_pdb"), \
             patch.object(scanner, "_apply_network_policies"), \
             patch.object(scanner, "_infer_dependencies"):
            result = scanner.scan()

        assert result.scan_duration_seconds >= 0.0

    @patch("faultray.discovery.k8s_scanner._check_k8s_lib")
    def test_all_namespaces_when_no_namespace(self, mock_check):
        """Test that scanner queries all namespaces when namespace is not specified."""
        scanner = _make_scanner(namespace=None)
        graph = InfraGraph()

        deploy = _mock_deployment(name="api", namespace="default", replicas=1)

        mock_client = MagicMock()
        mock_apps_v1 = MagicMock()
        response = MagicMock()
        response.items = [deploy]
        mock_apps_v1.list_deployment_for_all_namespaces.return_value = response
        mock_client.AppsV1Api.return_value = mock_apps_v1

        with patch.object(scanner, "_get_api_client", return_value=mock_client):
            scanner._scan_deployments(graph)

        # Should call list_deployment_for_all_namespaces, not list_namespaced_deployment
        mock_apps_v1.list_deployment_for_all_namespaces.assert_called_once()
        mock_apps_v1.list_namespaced_deployment.assert_not_called()
