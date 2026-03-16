# Azure Integration

FaultRay integrates with Microsoft Azure to scan and model your Azure infrastructure.

## Setup

Install the Azure extras:

```bash
pip install "faultray[azure]"
```

Authenticate with Azure:

```bash
az login
# or use service principal
export AZURE_CLIENT_ID=...
export AZURE_CLIENT_SECRET=...
export AZURE_TENANT_ID=...
export AZURE_SUBSCRIPTION_ID=...
```

## Scanning

### Full subscription scan

```bash
faultray scan --provider azure --output azure-infra.json
```

### Specific resource group

```bash
faultray scan --provider azure --resource-group my-rg --output azure.json
```

## Supported Services

| Service | Component Type | Details |
|---------|---------------|---------|
| Virtual Machines | Compute | VMs, VMSS, availability sets |
| Azure SQL | Database | Single, elastic pools, managed instances |
| Azure Cache for Redis | Cache | Instances, clustering, geo-replication |
| Azure Load Balancer | Load Balancer | Standard LB, Application Gateway |
| Azure Blob Storage | Storage | Accounts, GRS, RA-GRS |
| Azure DNS | DNS | Zones, Traffic Manager profiles |
| Azure CDN | CDN | Profiles, endpoints, origins |
| AKS | Container | Clusters, node pools |
| Azure Functions | Serverless | Function apps, premium plans |
| Service Bus | Queue | Queues, topics, geo-DR |

## Example

```python
from faultray.scanners import AzureScanner

scanner = AzureScanner(subscription_id="my-subscription-id")
graph = scanner.scan()

print(f"Discovered {len(graph.nodes)} Azure resources")
```

## Required Permissions

The service principal needs the `Reader` role at the subscription level, or specific read permissions for each resource type.
