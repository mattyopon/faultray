# 5-Layer Model

FaultZero organizes infrastructure components into five logical layers, each representing a distinct tier of the technology stack.

## Layer Overview

```
┌─────────────────────────────────┐
│  Layer 5: Edge / CDN            │
├─────────────────────────────────┤
│  Layer 4: DNS / Routing         │
├─────────────────────────────────┤
│  Layer 3: Network / Load Bal.   │
├─────────────────────────────────┤
│  Layer 2: Compute / Application │
├─────────────────────────────────┤
│  Layer 1: Storage / Database    │
└─────────────────────────────────┘
```

## Layer 1: Storage / Database

The foundation layer handles persistent data storage.

- Databases (RDS, Cloud SQL, Cosmos DB)
- Object storage (S3, GCS, Blob Storage)
- File systems (EFS, Filestore)
- Cache layers (ElastiCache, Memorystore)

**Key resilience factors:** Replication, backup frequency, cross-region failover.

## Layer 2: Compute / Application

The application processing layer runs your business logic.

- Virtual machines (EC2, Compute Engine, Azure VMs)
- Containers (ECS, GKE, AKS)
- Serverless (Lambda, Cloud Functions, Azure Functions)
- Application servers

**Key resilience factors:** Auto-scaling, health checks, rolling deployments.

## Layer 3: Network / Load Balancing

The networking layer routes traffic between components.

- Load balancers (ALB/NLB, Cloud Load Balancing, Azure LB)
- VPCs and subnets
- Security groups and firewalls
- Service mesh (Istio, Linkerd)

**Key resilience factors:** Multi-AZ distribution, health check intervals, connection draining.

## Layer 4: DNS / Routing

The routing layer manages name resolution and traffic policies.

- DNS services (Route 53, Cloud DNS, Azure DNS)
- Traffic management (Global Accelerator, Traffic Manager)
- API gateways

**Key resilience factors:** TTL settings, failover routing policies, health-checked endpoints.

## Layer 5: Edge / CDN

The edge layer handles content delivery and DDoS protection.

- CDN (CloudFront, Cloud CDN, Azure CDN)
- WAF / DDoS protection (Shield, Cloud Armor)
- Edge functions (CloudFront Functions, Workers)

**Key resilience factors:** PoP distribution, origin failover, cache hit ratios.

## Cross-Layer Analysis

FaultZero evaluates failure impact across layers. A Layer 1 (database) failure might cascade through Layer 2 (application) and ultimately affect Layer 5 (CDN cache invalidation). The simulation engine traces these cross-layer dependencies to calculate true impact.

```bash
faultzero simulate -m model.json --cascade-depth 5
```
