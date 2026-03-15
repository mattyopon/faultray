# Kubernetes Integration

FaultZero can scan Kubernetes clusters to model workload resilience, pod distribution, and service dependencies.

## Setup

Install the Kubernetes extras:

```bash
pip install "faultzero[k8s]"
```

Ensure `kubectl` is configured and has access to your cluster:

```bash
kubectl cluster-info
```

## Scanning

### Current context

```bash
faultzero scan --provider k8s --output k8s-infra.json
```

### Specific namespace

```bash
faultzero scan --provider k8s --namespace production --output k8s.json
```

### Specific kubeconfig

```bash
faultzero scan --provider k8s --kubeconfig ~/.kube/prod-config --output k8s.json
```

## What gets scanned

FaultZero analyzes the following Kubernetes resources:

| Resource | What is modeled |
|----------|----------------|
| Deployments | Replica count, pod anti-affinity, topology spread |
| StatefulSets | Ordered deployment, persistent volumes |
| Services | Service mesh, load balancing, endpoints |
| Ingress | Traffic routing, TLS termination |
| Nodes | Node distribution, taints, availability zones |
| PVCs | Storage class, replication, backup |
| HPA | Auto-scaling thresholds, min/max replicas |
| PDB | Disruption budget, min available |
| NetworkPolicies | Network segmentation, isolation |

## Resilience Checks

FaultZero evaluates Kubernetes-specific resilience factors:

- **Pod anti-affinity** — Are replicas spread across nodes/AZs?
- **PodDisruptionBudget** — Are disruption budgets defined?
- **Resource limits** — Are CPU/memory limits set to prevent noisy neighbors?
- **Liveness/readiness probes** — Are health checks configured?
- **Node distribution** — Are pods spread across failure domains?
- **HPA configuration** — Is auto-scaling properly configured?

## Example

```python
from infrasim.scanners import K8sScanner

scanner = K8sScanner(namespace="production")
graph = scanner.scan()

# Check for pods without anti-affinity
for node in graph.nodes:
    if node.type == "compute" and not node.metadata.get("anti_affinity"):
        print(f"WARNING: {node.id} has no pod anti-affinity rule")
```
