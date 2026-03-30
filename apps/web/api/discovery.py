"""FaultRay infrastructure discovery endpoint.

POST /api/discovery
  Body: { "action": "terraform", "tfstate_json": "<json string>" }
  Body: { "action": "kubernetes", "manifests": "<yaml/json string>", "namespace"?: string }

Dispatches to terraform or kubernetes parser based on 'action' field.
"""

from http.server import BaseHTTPRequestHandler
import json


def _run_terraform_parse(tfstate_json_str: str) -> dict:
    """Parse Terraform state and run simulation."""
    from faultray.discovery.terraform import parse_tf_state
    from faultray.simulator.engine import SimulationEngine

    state_dict = json.loads(tfstate_json_str)
    graph = parse_tf_state(state_dict)

    if len(graph.components) == 0:
        raise ValueError(
            "No infrastructure components found in the Terraform state. "
            "Ensure the state file contains resource definitions."
        )

    # Run simulation on parsed graph
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults(
        include_feed=False, include_plugins=False
    )

    # Calculate availability nines from resilience score
    score = report.resilience_score
    if score >= 99.999:
        nines = 5.0
    elif score >= 99.99:
        nines = 4.0 + (score - 99.99) / 0.009
    elif score >= 99.9:
        nines = 3.0 + (score - 99.9) / 0.09
    elif score >= 99.0:
        nines = 2.0 + (score - 99.0) / 0.9
    elif score >= 90.0:
        nines = 1.0 + (score - 90.0) / 9.0
    else:
        nines = score / 90.0

    if nines >= 4.0:
        avail = "99.99%"
    elif nines >= 3.0:
        avail = "99.9%"
    elif nines >= 2.0:
        avail = "99%"
    else:
        avail = f"{score:.1f}%"

    critical_failures = []
    for r in report.critical_findings[:10]:
        critical_failures.append(
            {
                "scenario": r.scenario.name,
                "impact": (
                    f"Risk score {r.risk_score:.1f}/10 - "
                    f"{len(r.cascade.effects)} components affected"
                ),
                "severity": "CRITICAL" if r.risk_score >= 8.0 else "HIGH",
            }
        )

    suggestions = []
    seen: set[str] = set()
    for r in report.warnings[:10]:
        title = f"Harden: {r.scenario.name}"
        if title not in seen:
            seen.add(title)
            suggestions.append(
                {
                    "title": title,
                    "description": (
                        f"Scenario risk score: {r.risk_score:.1f}. "
                        f"Consider adding redundancy or failover."
                    ),
                    "impact": f"+{(10 - r.risk_score) * 0.05:.1f} nines",
                    "effort": (
                        "Low" if r.risk_score < 5.0 else "Medium"
                    ),
                }
            )

    return {
        "scan_summary": {
            "components_found": len(graph.components),
            "dependencies_inferred": len(graph.all_dependency_edges()),
        },
        "overall_score": round(score, 1),
        "availability_estimate": avail,
        "nines": round(nines, 2),
        "scenarios_passed": len(report.passed),
        "scenarios_failed": len(report.critical_findings),
        "total_scenarios": len(report.results),
        "layers": {
            "software": round(min(nines, 7.0), 2),
            "hardware": round(min(nines * 1.3, 7.0), 2),
            "theoretical": round(min(nines * 1.5, 7.0), 2),
        },
        "critical_failures": critical_failures,
        "suggestions": suggestions[:5],
    }


def _run_k8s_parse(manifests: str, namespace: str | None = None) -> dict:
    """Parse Kubernetes manifests and run simulation."""
    import yaml
    from faultray.simulator.engine import SimulationEngine

    # Parse the manifests to extract resources
    docs = list(yaml.safe_load_all(manifests))
    docs = [d for d in docs if d is not None]

    if not docs:
        raise ValueError(
            "No valid Kubernetes resources found in the input. "
            "Provide YAML/JSON manifests or kubectl output."
        )

    # Build an InfraGraph from K8s manifests manually
    from faultray.model.loader import InfraGraph

    graph = InfraGraph()
    _parse_k8s_resources(graph, docs, namespace)

    if len(graph.components) == 0:
        raise ValueError(
            "No infrastructure components could be extracted from the "
            "Kubernetes manifests. Ensure the input contains Deployments, "
            "StatefulSets, Services, or other workload resources."
        )

    # Run simulation
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults(
        include_feed=False, include_plugins=False
    )

    # Calculate availability nines
    score = report.resilience_score
    if score >= 99.999:
        nines = 5.0
    elif score >= 99.99:
        nines = 4.0 + (score - 99.99) / 0.009
    elif score >= 99.9:
        nines = 3.0 + (score - 99.9) / 0.09
    elif score >= 99.0:
        nines = 2.0 + (score - 99.0) / 0.9
    elif score >= 90.0:
        nines = 1.0 + (score - 90.0) / 9.0
    else:
        nines = score / 90.0

    if nines >= 4.0:
        avail = "99.99%"
    elif nines >= 3.0:
        avail = "99.9%"
    elif nines >= 2.0:
        avail = "99%"
    else:
        avail = f"{score:.1f}%"

    critical_failures = []
    for r in report.critical_findings[:10]:
        critical_failures.append(
            {
                "scenario": r.scenario.name,
                "impact": (
                    f"Risk score {r.risk_score:.1f}/10 - "
                    f"{len(r.cascade.effects)} components affected"
                ),
                "severity": "CRITICAL" if r.risk_score >= 8.0 else "HIGH",
            }
        )

    suggestions = []
    seen: set[str] = set()
    for r in report.warnings[:10]:
        title = f"Harden: {r.scenario.name}"
        if title not in seen:
            seen.add(title)
            suggestions.append(
                {
                    "title": title,
                    "description": (
                        f"Scenario risk score: {r.risk_score:.1f}. "
                        f"Consider adding redundancy or failover."
                    ),
                    "impact": f"+{(10 - r.risk_score) * 0.05:.1f} nines",
                    "effort": (
                        "Low" if r.risk_score < 5.0 else "Medium"
                    ),
                }
            )

    return {
        "scan_summary": {
            "components_found": len(graph.components),
            "dependencies_inferred": len(graph.all_dependency_edges()),
            "namespace": namespace,
        },
        "overall_score": round(score, 1),
        "availability_estimate": avail,
        "nines": round(nines, 2),
        "scenarios_passed": len(report.passed),
        "scenarios_failed": len(report.critical_findings),
        "total_scenarios": len(report.results),
        "layers": {
            "software": round(min(nines, 7.0), 2),
            "hardware": round(min(nines * 1.3, 7.0), 2),
            "theoretical": round(min(nines * 1.5, 7.0), 2),
        },
        "critical_failures": critical_failures,
        "suggestions": suggestions[:5],
    }


def _parse_k8s_resources(
    graph: "InfraGraph",
    docs: list[dict],
    namespace: str | None,
) -> None:
    """Extract FaultRay components from Kubernetes resource definitions."""
    from faultray.model.loader import (
        Component,
        ComponentType,
        Capacity,
        Dependency,
        ResourceMetrics,
    )

    # Type mapping for K8s resources
    K8S_TYPE_MAP = {
        "Deployment": ComponentType.APP_SERVER,
        "StatefulSet": ComponentType.DATABASE,
        "DaemonSet": ComponentType.APP_SERVER,
        "Service": ComponentType.LOAD_BALANCER,
        "Ingress": ComponentType.LOAD_BALANCER,
        "ConfigMap": ComponentType.CUSTOM,
        "CronJob": ComponentType.APP_SERVER,
        "Job": ComponentType.APP_SERVER,
    }

    service_selectors: dict[str, dict[str, str]] = {}
    workload_labels: dict[str, dict[str, str]] = {}

    for doc in docs:
        if not isinstance(doc, dict):
            continue

        kind = doc.get("kind", "")
        metadata = doc.get("metadata", {})
        name = metadata.get("name", "unknown")
        ns = metadata.get("namespace", "default")

        # Filter by namespace if specified
        if namespace and ns != namespace:
            continue

        spec = doc.get("spec", {})
        comp_type = K8S_TYPE_MAP.get(kind)
        if comp_type is None:
            continue

        comp_id = f"{ns}-{name}".replace("/", "-").replace(".", "-")

        if kind in ("Deployment", "StatefulSet", "DaemonSet"):
            replicas = spec.get("replicas", 1)
            template = spec.get("template", {})
            template_labels = (
                template.get("metadata", {}).get("labels", {})
            )
            workload_labels[comp_id] = template_labels

            # Extract resource requests for capacity
            containers = (
                template.get("spec", {}).get("containers", [])
            )
            port = 80
            if containers:
                ports = containers[0].get("ports", [])
                if ports:
                    port = ports[0].get("containerPort", 80)

            graph.add_component(
                Component(
                    id=comp_id,
                    name=f"{name} ({kind})",
                    type=comp_type,
                    host=f"{name}.{ns}.svc.cluster.local",
                    port=port,
                    replicas=replicas,
                    capacity=Capacity(
                        max_connections=1000 * replicas,
                    ),
                    metrics=ResourceMetrics(
                        cpu_percent=30.0,
                        memory_percent=40.0,
                    ),
                )
            )

        elif kind == "Service":
            selector = spec.get("selector", {})
            service_selectors[comp_id] = selector
            ports = spec.get("ports", [])
            port = ports[0].get("port", 80) if ports else 80

            graph.add_component(
                Component(
                    id=comp_id,
                    name=f"{name} (Service)",
                    type=comp_type,
                    host=f"{name}.{ns}.svc.cluster.local",
                    port=port,
                    replicas=1,
                    capacity=Capacity(max_connections=10000),
                    metrics=ResourceMetrics(
                        cpu_percent=10.0,
                        memory_percent=10.0,
                    ),
                )
            )

        elif kind == "Ingress":
            graph.add_component(
                Component(
                    id=comp_id,
                    name=f"{name} (Ingress)",
                    type=comp_type,
                    host=name,
                    port=443,
                    replicas=2,
                    capacity=Capacity(max_connections=50000),
                    metrics=ResourceMetrics(
                        cpu_percent=15.0,
                        memory_percent=15.0,
                    ),
                )
            )

            # Link ingress to backend services
            rules = spec.get("rules", [])
            for rule in rules:
                http = rule.get("http", {})
                paths = http.get("paths", [])
                for p in paths:
                    backend = p.get("backend", {})
                    svc = backend.get("service", {})
                    svc_name = svc.get("name", "")
                    if svc_name:
                        target_id = f"{ns}-{svc_name}".replace(
                            "/", "-"
                        ).replace(".", "-")
                        if graph.get_component(target_id):
                            graph.add_dependency(
                                Dependency(
                                    source=comp_id,
                                    target=target_id,
                                )
                            )

    # Match services to workloads by selector
    for svc_id, selector in service_selectors.items():
        if not selector:
            continue
        for wl_id, labels in workload_labels.items():
            if all(
                labels.get(k) == v for k, v in selector.items()
            ):
                graph.add_dependency(
                    Dependency(source=svc_id, target=wl_id)
                )


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}

            action = data.get("action", "")

            if action == "terraform":
                tfstate_json = data.get("tfstate_json")
                if not tfstate_json:
                    self._send_error(
                        400,
                        "Missing 'tfstate_json' in request body. "
                        "Provide the output of 'terraform show -json' "
                        "or the contents of a .tfstate file.",
                    )
                    return
                result = _run_terraform_parse(tfstate_json)
                self._send_json(200, result)

            elif action == "kubernetes":
                manifests = data.get("manifests")
                if not manifests:
                    self._send_error(
                        400,
                        "Missing 'manifests' in request body. "
                        "Provide Kubernetes YAML/JSON manifests or "
                        "kubectl output.",
                    )
                    return
                namespace = data.get("namespace")
                result = _run_k8s_parse(manifests, namespace)
                self._send_json(200, result)

            else:
                self._send_error(
                    400,
                    "Missing or invalid 'action' field. "
                    "Must be 'terraform' or 'kubernetes'.",
                )

        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON in request body")
        except ValueError as e:
            self._send_error(400, str(e))
        except Exception as e:
            error_type = type(e).__name__
            self._send_error(
                500, f"Discovery error ({error_type}): {e}"
            )

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header(
            "Access-Control-Allow-Methods", "POST, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, Authorization"
        )
        self.end_headers()

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_error(self, status: int, message: str):
        self._send_json(status, {"error": {"message": message}})

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
