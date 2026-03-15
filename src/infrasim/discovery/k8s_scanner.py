"""Kubernetes infrastructure auto-discovery scanner.

Connects to a live Kubernetes cluster via the kubernetes Python client to
discover all infrastructure resources and generates a complete InfraGraph
with components, dependencies, metrics, security profiles, and autoscaling
configurations.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from infrasim.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    ResourceMetrics,
    SecurityProfile,
)
from infrasim.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Name/label patterns that indicate a database workload
_DB_PATTERNS = {"postgres", "postgresql", "mysql", "mariadb", "mongo", "mongodb", "redis", "cassandra", "cockroach", "couchdb"}


def _check_k8s_lib() -> None:
    """Check that the kubernetes library is importable."""
    try:
        import kubernetes  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "kubernetes is required for K8s scanning. "
            "Install with: pip install 'faultzero[k8s]'"
        )


def _looks_like_database(name: str, labels: dict[str, str] | None = None) -> bool:
    """Heuristic to determine if a workload is a database based on name/labels."""
    name_lower = name.lower()
    if any(pat in name_lower for pat in _DB_PATTERNS):
        return True
    if labels:
        for val in labels.values():
            if any(pat in val.lower() for pat in _DB_PATTERNS):
                return True
    return False


@dataclass
class K8sDiscoveryResult:
    """Result of a Kubernetes infrastructure discovery scan."""

    context: str | None
    namespace: str | None
    components_found: int
    dependencies_inferred: int
    graph: InfraGraph
    warnings: list[str] = field(default_factory=list)
    scan_duration_seconds: float = 0.0


class K8sScanner:
    """Discover Kubernetes infrastructure and generate InfraGraph automatically."""

    def __init__(self, context: str | None = None, namespace: str | None = None):
        self.context = context
        self.namespace = namespace
        self._warnings: list[str] = []
        # Service selector tracking: service_comp_id -> selector labels
        self._service_selectors: dict[str, dict[str, str]] = {}
        # Deployment/StatefulSet label tracking: comp_id -> labels
        self._workload_labels: dict[str, dict[str, str]] = {}
        # HPA targets: comp_id -> AutoScalingConfig
        self._hpa_configs: dict[str, AutoScalingConfig] = {}
        # PDB tracking: comp_id -> (min_available, max_unavailable)
        self._pdb_configs: dict[str, dict] = {}
        # Network policy tracking: comp_id -> has network policy
        self._network_policies: set[str] = set()

    def _get_api_client(self):
        """Create a kubernetes API client."""
        from kubernetes import client, config

        try:
            if self.context:
                config.load_kube_config(context=self.context)
            else:
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config()
        except Exception as exc:
            raise RuntimeError(f"Failed to load Kubernetes config: {exc}")

        return client

    def scan(self) -> K8sDiscoveryResult:
        """Run a full Kubernetes infrastructure scan.

        Returns a K8sDiscoveryResult with the discovered InfraGraph.
        """
        _check_k8s_lib()

        start = time.monotonic()
        graph = InfraGraph()

        scanners = [
            ("Deployments", self._scan_deployments),
            ("StatefulSets", self._scan_statefulsets),
            ("Services", self._scan_services),
            ("Ingresses", self._scan_ingresses),
            ("HPA", self._scan_hpa),
            ("PDB", self._scan_pdb),
            ("NetworkPolicies", self._scan_network_policies),
        ]

        for name, scanner_fn in scanners:
            try:
                scanner_fn(graph)
            except RuntimeError:
                raise  # Re-raise library import errors
            except Exception as exc:
                msg = f"Failed to scan {name}: {exc}"
                logger.warning(msg)
                self._warnings.append(msg)

        # Post-processing
        try:
            self._apply_hpa(graph)
        except Exception as exc:
            msg = f"Failed to apply HPA configs: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        try:
            self._apply_pdb(graph)
        except Exception as exc:
            msg = f"Failed to apply PDB configs: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        try:
            self._apply_network_policies(graph)
        except Exception as exc:
            msg = f"Failed to apply network policies: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        try:
            self._infer_dependencies(graph)
        except Exception as exc:
            msg = f"Failed to infer dependencies: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        duration = time.monotonic() - start
        dep_count = len(graph.all_dependency_edges())

        return K8sDiscoveryResult(
            context=self.context,
            namespace=self.namespace,
            components_found=len(graph.components),
            dependencies_inferred=dep_count,
            graph=graph,
            warnings=list(self._warnings),
            scan_duration_seconds=round(duration, 2),
        )

    # ── Individual Resource Scanners ─────────────────────────────────────────

    def _scan_deployments(self, graph: InfraGraph) -> None:
        """Discover Deployments."""
        k8s_client = self._get_api_client()
        apps_v1 = k8s_client.AppsV1Api()

        try:
            if self.namespace:
                deployments = apps_v1.list_namespaced_deployment(namespace=self.namespace)
            else:
                deployments = apps_v1.list_deployment_for_all_namespaces()

            for deploy in deployments.items:
                name = deploy.metadata.name
                ns = deploy.metadata.namespace or "default"
                comp_id = f"deploy-{ns}-{name}"

                replicas = deploy.spec.replicas if deploy.spec.replicas is not None else 1
                labels = dict(deploy.metadata.labels or {})
                selector_labels = {}
                if deploy.spec.selector and deploy.spec.selector.match_labels:
                    selector_labels = dict(deploy.spec.selector.match_labels)

                self._workload_labels[comp_id] = {**labels, **selector_labels}

                # Determine component type
                comp_type = ComponentType.DATABASE if _looks_like_database(name, labels) else ComponentType.APP_SERVER

                component = Component(
                    id=comp_id,
                    name=f"{ns}/{name}",
                    type=comp_type,
                    replicas=max(replicas, 1),
                    region=RegionConfig(region=ns),
                    tags=["deployment", f"namespace:{ns}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Deployment scan error: {exc}")

    def _scan_statefulsets(self, graph: InfraGraph) -> None:
        """Discover StatefulSets."""
        k8s_client = self._get_api_client()
        apps_v1 = k8s_client.AppsV1Api()

        try:
            if self.namespace:
                statefulsets = apps_v1.list_namespaced_stateful_set(namespace=self.namespace)
            else:
                statefulsets = apps_v1.list_stateful_set_for_all_namespaces()

            for sts in statefulsets.items:
                name = sts.metadata.name
                ns = sts.metadata.namespace or "default"
                comp_id = f"sts-{ns}-{name}"

                replicas = sts.spec.replicas if sts.spec.replicas is not None else 1
                labels = dict(sts.metadata.labels or {})
                selector_labels = {}
                if sts.spec.selector and sts.spec.selector.match_labels:
                    selector_labels = dict(sts.spec.selector.match_labels)

                self._workload_labels[comp_id] = {**labels, **selector_labels}

                # StatefulSets are often databases; heuristic based on name/labels
                comp_type = ComponentType.DATABASE if _looks_like_database(name, labels) else ComponentType.APP_SERVER

                component = Component(
                    id=comp_id,
                    name=f"{ns}/{name}",
                    type=comp_type,
                    replicas=max(replicas, 1),
                    region=RegionConfig(region=ns),
                    failover=FailoverConfig(
                        enabled=replicas > 1,
                    ),
                    tags=["statefulset", f"namespace:{ns}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"StatefulSet scan error: {exc}")

    def _scan_services(self, graph: InfraGraph) -> None:
        """Discover Services and record their selectors for dependency inference."""
        k8s_client = self._get_api_client()
        core_v1 = k8s_client.CoreV1Api()

        try:
            if self.namespace:
                services = core_v1.list_namespaced_service(namespace=self.namespace)
            else:
                services = core_v1.list_service_for_all_namespaces()

            for svc in services.items:
                name = svc.metadata.name
                ns = svc.metadata.namespace or "default"

                # Skip kubernetes system service
                if name == "kubernetes" and ns == "default":
                    continue

                selector = dict(svc.spec.selector or {}) if svc.spec.selector else {}
                svc_comp_id = f"svc-{ns}-{name}"
                self._service_selectors[svc_comp_id] = selector

                # Determine port
                port = 0
                if svc.spec.ports:
                    port = svc.spec.ports[0].port or 0
        except Exception as exc:
            self._warnings.append(f"Service scan error: {exc}")

    def _scan_ingresses(self, graph: InfraGraph) -> None:
        """Discover Ingresses as load balancer components."""
        k8s_client = self._get_api_client()
        networking_v1 = k8s_client.NetworkingV1Api()

        try:
            if self.namespace:
                ingresses = networking_v1.list_namespaced_ingress(namespace=self.namespace)
            else:
                ingresses = networking_v1.list_ingress_for_all_namespaces()

            for ingress in ingresses.items:
                name = ingress.metadata.name
                ns = ingress.metadata.namespace or "default"
                comp_id = f"ingress-{ns}-{name}"

                # Extract host
                host = ""
                if ingress.spec.rules:
                    host = ingress.spec.rules[0].host or ""

                # Check for TLS
                has_tls = bool(ingress.spec.tls) if ingress.spec.tls else False

                component = Component(
                    id=comp_id,
                    name=f"{ns}/{name}",
                    type=ComponentType.LOAD_BALANCER,
                    host=host,
                    port=443 if has_tls else 80,
                    replicas=2,  # Ingress controllers are typically HA
                    region=RegionConfig(region=ns),
                    security=SecurityProfile(
                        encryption_in_transit=has_tls,
                    ),
                    tags=["ingress", f"namespace:{ns}"],
                )
                graph.add_component(component)

                # Create dependency edges from ingress to backend services
                if ingress.spec.rules:
                    for rule in ingress.spec.rules:
                        if rule.http and rule.http.paths:
                            for path in rule.http.paths:
                                if path.backend and path.backend.service:
                                    backend_svc_name = path.backend.service.name
                                    # Find matching workload via service selector
                                    svc_comp_id = f"svc-{ns}-{backend_svc_name}"
                                    # Store for later dependency resolution
                                    self._service_selectors.setdefault(svc_comp_id, {})
        except Exception as exc:
            self._warnings.append(f"Ingress scan error: {exc}")

    def _scan_hpa(self, graph: InfraGraph) -> None:
        """Discover HorizontalPodAutoscalers."""
        k8s_client = self._get_api_client()
        autoscaling_v2 = k8s_client.AutoscalingV2Api()

        try:
            if self.namespace:
                hpas = autoscaling_v2.list_namespaced_horizontal_pod_autoscaler(
                    namespace=self.namespace
                )
            else:
                hpas = autoscaling_v2.list_horizontal_pod_autoscaler_for_all_namespaces()

            for hpa in hpas.items:
                ns = hpa.metadata.namespace or "default"
                target_ref = hpa.spec.scale_target_ref
                target_kind = target_ref.kind.lower() if target_ref.kind else ""
                target_name = target_ref.name

                # Map HPA target to component id
                if target_kind == "deployment":
                    target_comp_id = f"deploy-{ns}-{target_name}"
                elif target_kind == "statefulset":
                    target_comp_id = f"sts-{ns}-{target_name}"
                else:
                    continue

                min_replicas = hpa.spec.min_replicas or 1
                max_replicas = hpa.spec.max_replicas or 10

                # Extract CPU threshold from metrics
                cpu_threshold = 70.0
                if hpa.spec.metrics:
                    for metric in hpa.spec.metrics:
                        if (
                            metric.type == "Resource"
                            and metric.resource
                            and metric.resource.name == "cpu"
                        ):
                            if metric.resource.target and metric.resource.target.average_utilization:
                                cpu_threshold = float(metric.resource.target.average_utilization)

                self._hpa_configs[target_comp_id] = AutoScalingConfig(
                    enabled=True,
                    min_replicas=min_replicas,
                    max_replicas=max_replicas,
                    scale_up_threshold=cpu_threshold,
                )
        except Exception as exc:
            self._warnings.append(f"HPA scan error: {exc}")

    def _scan_pdb(self, graph: InfraGraph) -> None:
        """Discover PodDisruptionBudgets."""
        k8s_client = self._get_api_client()
        policy_v1 = k8s_client.PolicyV1Api()

        try:
            if self.namespace:
                pdbs = policy_v1.list_namespaced_pod_disruption_budget(namespace=self.namespace)
            else:
                pdbs = policy_v1.list_pod_disruption_budget_for_all_namespaces()

            for pdb in pdbs.items:
                ns = pdb.metadata.namespace or "default"
                selector = dict(pdb.spec.selector.match_labels or {}) if pdb.spec.selector and pdb.spec.selector.match_labels else {}

                min_available = None
                max_unavailable = None
                if pdb.spec.min_available is not None:
                    min_available = pdb.spec.min_available
                if pdb.spec.max_unavailable is not None:
                    max_unavailable = pdb.spec.max_unavailable

                # Match PDB to workloads by label selector
                for comp_id, labels in self._workload_labels.items():
                    if not selector:
                        continue
                    # Check if all PDB selector labels exist in workload labels
                    if all(labels.get(k) == v for k, v in selector.items()):
                        self._pdb_configs[comp_id] = {
                            "min_available": min_available,
                            "max_unavailable": max_unavailable,
                        }
        except Exception as exc:
            self._warnings.append(f"PDB scan error: {exc}")

    def _scan_network_policies(self, graph: InfraGraph) -> None:
        """Discover NetworkPolicies."""
        k8s_client = self._get_api_client()
        networking_v1 = k8s_client.NetworkingV1Api()

        try:
            if self.namespace:
                policies = networking_v1.list_namespaced_network_policy(namespace=self.namespace)
            else:
                policies = networking_v1.list_network_policy_for_all_namespaces()

            for policy in policies.items:
                ns = policy.metadata.namespace or "default"
                selector = dict(policy.spec.pod_selector.match_labels or {}) if policy.spec.pod_selector and policy.spec.pod_selector.match_labels else {}

                # Match network policy to workloads by label selector
                for comp_id, labels in self._workload_labels.items():
                    if not selector:
                        # Empty selector matches all pods in namespace
                        if f"namespace:{ns}" in graph.components.get(comp_id, Component(id="", name="", type=ComponentType.APP_SERVER)).tags:
                            self._network_policies.add(comp_id)
                        continue
                    if all(labels.get(k) == v for k, v in selector.items()):
                        self._network_policies.add(comp_id)
        except Exception as exc:
            self._warnings.append(f"NetworkPolicy scan error: {exc}")

    # ── Post-processing ──────────────────────────────────────────────────────

    def _apply_hpa(self, graph: InfraGraph) -> None:
        """Apply HPA configurations to matching components."""
        for comp_id, hpa_config in self._hpa_configs.items():
            comp = graph.get_component(comp_id)
            if comp:
                comp.autoscaling = hpa_config

    def _apply_pdb(self, graph: InfraGraph) -> None:
        """Apply PDB configurations to affect resilience scoring.

        PDB with minAvailable or maxUnavailable improves resilience because it
        guarantees a minimum number of running pods during disruptions.
        Components with PDB get failover enabled.
        """
        for comp_id, pdb_config in self._pdb_configs.items():
            comp = graph.get_component(comp_id)
            if comp:
                comp.failover = FailoverConfig(enabled=True)
                # Store PDB info as tags for visibility
                if pdb_config.get("min_available") is not None:
                    comp.tags.append(f"pdb:minAvailable={pdb_config['min_available']}")
                if pdb_config.get("max_unavailable") is not None:
                    comp.tags.append(f"pdb:maxUnavailable={pdb_config['max_unavailable']}")

    def _apply_network_policies(self, graph: InfraGraph) -> None:
        """Apply NetworkPolicy status to security profiles."""
        for comp_id in self._network_policies:
            comp = graph.get_component(comp_id)
            if comp:
                comp.security.network_segmented = True

    # ── Dependency Inference ─────────────────────────────────────────────────

    def _infer_dependencies(self, graph: InfraGraph) -> None:
        """Infer dependencies from service selectors and network policies."""
        existing_edges: set[tuple[str, str]] = set()

        # Match services to workloads via label selectors, then create edges
        # from ingresses/other workloads to services' backing workloads
        for svc_comp_id, selector in self._service_selectors.items():
            if not selector:
                continue

            # Find workloads matching this service's selector
            matching_workloads = []
            for comp_id, labels in self._workload_labels.items():
                if comp_id not in graph.components:
                    continue
                if all(labels.get(k) == v for k, v in selector.items()):
                    matching_workloads.append(comp_id)

            # Extract service namespace from svc_comp_id: "svc-{ns}-{name}"
            parts = svc_comp_id.split("-", 2)
            if len(parts) < 3:
                continue
            svc_ns = parts[1]

            # Create edges from ingress to matching workloads
            for comp_id in graph.components:
                if not comp_id.startswith("ingress-"):
                    continue
                # Check if ingress is in the same namespace
                ingress_ns = comp_id.split("-", 2)[1] if len(comp_id.split("-", 2)) > 1 else ""
                if ingress_ns != svc_ns:
                    continue

                for workload_id in matching_workloads:
                    edge_key = (comp_id, workload_id)
                    if edge_key in existing_edges:
                        continue
                    existing_edges.add(edge_key)
                    dep = Dependency(
                        source_id=comp_id,
                        target_id=workload_id,
                        dependency_type="requires",
                        protocol="http",
                        port=80,
                    )
                    graph.add_dependency(dep)

            # Create inter-workload edges: if workload A is in same namespace and
            # references a service whose selector matches workload B
            for other_comp_id in graph.components:
                if other_comp_id.startswith("ingress-"):
                    continue
                if other_comp_id in matching_workloads:
                    continue
                if other_comp_id not in self._workload_labels:
                    continue

                # Same namespace heuristic
                other_ns = other_comp_id.split("-", 2)[1] if len(other_comp_id.split("-", 2)) > 1 else ""
                if other_ns != svc_ns:
                    continue

                for workload_id in matching_workloads:
                    edge_key = (other_comp_id, workload_id)
                    if edge_key in existing_edges:
                        continue
                    # Only create if the target is a database or cache (likely dependency)
                    target_comp = graph.get_component(workload_id)
                    if target_comp and target_comp.type in (ComponentType.DATABASE, ComponentType.CACHE):
                        existing_edges.add(edge_key)
                        dep = Dependency(
                            source_id=other_comp_id,
                            target_id=workload_id,
                            dependency_type="requires",
                            protocol="tcp",
                            port=target_comp.port if target_comp.port else 0,
                        )
                        graph.add_dependency(dep)
