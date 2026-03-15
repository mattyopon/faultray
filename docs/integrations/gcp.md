# GCP Integration

FaultZero integrates with Google Cloud Platform to scan and model your GCP infrastructure.

## Setup

Install the GCP extras:

```bash
pip install "faultzero[gcp]"
```

Authenticate with Google Cloud:

```bash
gcloud auth application-default login
# or set GOOGLE_APPLICATION_CREDENTIALS
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

## Scanning

### Full project scan

```bash
faultzero scan --provider gcp --output gcp-infra.json
```

### Specific project

```bash
faultzero scan --provider gcp --project my-project-id --output gcp.json
```

## Supported Services

| Service | Component Type | Details |
|---------|---------------|---------|
| Compute Engine | Compute | Instances, instance groups, MIGs |
| Cloud SQL | Database | Instances, replicas, high availability |
| Cloud Memorystore | Cache | Redis instances, failover replicas |
| Cloud Load Balancing | Load Balancer | Backend services, health checks |
| Cloud Storage | Storage | Buckets, dual-region, turbo replication |
| Cloud DNS | DNS | Managed zones, routing policies |
| Cloud CDN | CDN | Backend buckets, cache policies |
| GKE | Container | Clusters, node pools, regional clusters |
| Cloud Functions | Serverless | Functions, min instances |
| Pub/Sub | Queue | Topics, subscriptions, dead letter topics |

## Example

```python
from infrasim.scanners import GCPScanner

scanner = GCPScanner(project="my-project-id")
graph = scanner.scan()

print(f"Discovered {len(graph.nodes)} GCP resources")
```

## Required Roles

The service account needs the following IAM roles:

- `roles/compute.viewer`
- `roles/cloudsql.viewer`
- `roles/redis.viewer`
- `roles/storage.objectViewer`
- `roles/dns.reader`
- `roles/container.viewer`
