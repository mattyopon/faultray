# Your First Simulation

This guide walks you through running your first FaultZero simulation and interpreting the results.

## Creating an infrastructure model

An infrastructure model describes your system as a directed graph of components and their dependencies. You can create one manually or scan from an existing environment.

### Manual model (YAML)

```yaml
nodes:
  - id: web-lb
    type: load_balancer
    provider: aws
    region: us-east-1
    redundancy: 2

  - id: web-server-1
    type: compute
    provider: aws
    region: us-east-1

  - id: web-server-2
    type: compute
    provider: aws
    region: us-east-1

  - id: primary-db
    type: database
    provider: aws
    region: us-east-1

edges:
  - from: web-lb
    to: web-server-1
  - from: web-lb
    to: web-server-2
  - from: web-server-1
    to: primary-db
  - from: web-server-2
    to: primary-db
```

### From cloud provider

```bash
faultzero scan --provider aws --output my-infra.json
```

## Running the simulation

```bash
faultzero simulate -m my-infra.json --json
```

### Sample output

```json
{
  "resilience_score": 62,
  "total_scenarios": 156,
  "passed": 120,
  "failed": 36,
  "critical": 3,
  "warning": 12,
  "spof_count": 2,
  "cascade_risks": 1,
  "availability_ceiling": "99.5%"
}
```

## Understanding the results

### Resilience Score

The resilience score (0-100) summarizes your infrastructure's ability to withstand failures:

| Score Range | Rating | Meaning |
|-------------|--------|---------|
| 80-100 | Excellent | Highly resilient, minimal risk |
| 50-79 | Fair | Some vulnerabilities need attention |
| 0-49 | Poor | Critical issues require immediate action |

### Single Points of Failure (SPOFs)

SPOFs are components whose failure would cause a complete system outage. In the example above, `primary-db` is a SPOF because both web servers depend on it with no failover.

### Cascade Risks

Cascade risks identify failure chains where one component's failure triggers additional failures downstream.

## Fixing issues

FaultZero provides actionable recommendations. For example, to address the database SPOF:

```yaml
  - id: replica-db
    type: database
    provider: aws
    region: us-east-1
    failover_target: primary-db
```

Re-run the simulation to verify improvements:

```bash
faultzero simulate -m my-infra-v2.json
```

## Next Steps

- [How It Works](../concepts/how-it-works.md) — Understand the simulation engine internals
- [Risk Scoring](../concepts/risk-scoring.md) — Learn how scores are calculated
