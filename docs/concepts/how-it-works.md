# How It Works

FaultZero uses a graph-based simulation engine to model infrastructure and evaluate resilience without touching production systems.

## Overview

The simulation pipeline consists of four stages:

1. **Model Construction** — Build a directed graph of infrastructure components
2. **Scenario Generation** — Generate failure scenarios based on component types
3. **Simulation Execution** — Run each scenario through the graph engine
4. **Scoring & Reporting** — Aggregate results into actionable metrics

## Model Construction

FaultZero represents infrastructure as a directed acyclic graph (DAG) where:

- **Nodes** represent infrastructure components (servers, databases, load balancers, etc.)
- **Edges** represent dependencies between components
- **Attributes** encode component properties (redundancy, region, failover targets)

```
         ┌──────────┐
         │   CDN    │
         └────┬─────┘
              │
         ┌────▼─────┐
         │    LB     │
         └──┬────┬───┘
            │    │
       ┌────▼┐  ┌▼────┐
       │ App1│  │ App2│
       └──┬──┘  └──┬──┘
          │        │
       ┌──▼────────▼──┐
       │   Database    │
       └──────────────┘
```

## Scenario Generation

FaultZero generates failure scenarios based on:

- **Single component failure** — What happens when one node goes down?
- **Multi-component failure** — Regional outages, provider-wide incidents
- **Cascade propagation** — How failures spread through dependencies
- **Partial degradation** — Performance reduction vs. complete outage

The engine generates 150+ scenarios by default, covering common real-world failure patterns.

## Simulation Execution

For each scenario, the engine:

1. Marks the target component(s) as failed
2. Propagates failure through dependency edges
3. Evaluates redundancy and failover paths
4. Calculates the impact on end-user availability

The simulation uses a combination of:

- **Graph traversal** — BFS/DFS through dependency edges
- **Markov chains** — Probabilistic failure modeling
- **Monte Carlo methods** — Statistical confidence in availability estimates
- **Bayesian inference** — Updated risk scores based on observed patterns

## Scoring

Results are aggregated into a resilience score (0-100) that considers:

- Number and severity of SPOFs
- Cascade failure depth and breadth
- Redundancy coverage
- Geographic distribution
- Failover path availability

See [Risk Scoring](risk-scoring.md) for the detailed scoring algorithm.
