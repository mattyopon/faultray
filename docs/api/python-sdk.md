# Python SDK

The FaultZero Python SDK provides a programmatic interface for building models, running simulations, and analyzing results.

## Installation

```bash
pip install faultzero
```

## Quick Start

```python
from infrasim import InfraGraph, SimulationEngine

# Build a model
graph = InfraGraph()
graph.add_node("web-lb", type="load_balancer", region="us-east-1")
graph.add_node("app-1", type="compute", region="us-east-1")
graph.add_node("app-2", type="compute", region="us-east-1")
graph.add_node("db-primary", type="database", region="us-east-1")

graph.add_edge("web-lb", "app-1")
graph.add_edge("web-lb", "app-2")
graph.add_edge("app-1", "db-primary")
graph.add_edge("app-2", "db-primary")

# Run simulation
engine = SimulationEngine(graph)
results = engine.simulate()

print(f"Resilience Score: {results.resilience_score}/100")
print(f"SPOFs found: {results.spof_count}")
```

## Core Classes

### InfraGraph

The main class for building infrastructure models.

```python
from infrasim import InfraGraph

graph = InfraGraph()

# Add nodes
graph.add_node(
    node_id="my-server",
    type="compute",
    provider="aws",
    region="us-east-1",
    redundancy=2,
    metadata={"instance_type": "m5.large"}
)

# Add edges (dependencies)
graph.add_edge(from_node="lb", to_node="my-server")

# Save / Load
graph.save("model.json")
loaded = InfraGraph.load("model.json")
```

### SimulationEngine

Runs failure scenarios against a model.

```python
from infrasim import SimulationEngine

engine = SimulationEngine(graph)

# Run all scenarios
results = engine.simulate()

# Run specific scenario types
results = engine.simulate(scenarios=["spof", "cascade"])

# Dynamic simulation with traffic patterns
results = engine.simulate(dynamic=True, duration_hours=24)
```

### SimulationResult

Contains the results of a simulation run.

```python
results = engine.simulate()

# Overall metrics
results.resilience_score      # int (0-100)
results.total_scenarios        # int
results.passed                 # int
results.failed                 # int
results.critical               # int
results.warning                # int
results.spof_count             # int

# Detailed scenario results
for scenario in results.scenarios:
    print(f"{scenario.name}: {scenario.status}")
    if scenario.status == "CRITICAL":
        print(f"  Impact: {scenario.impact}")
        print(f"  Affected: {scenario.affected_nodes}")
```

## Advanced Usage

### Custom scoring weights

```python
from infrasim import ScoringConfig

config = ScoringConfig(
    spof_weight=0.35,
    cascade_weight=0.25,
    redundancy_weight=0.25,
    geographic_weight=0.15
)

results = engine.simulate(scoring_config=config)
```

### Cloud provider scanning

```python
from infrasim.scanners import AWSScanner

scanner = AWSScanner(profile="my-profile", region="us-east-1")
graph = scanner.scan()

results = SimulationEngine(graph).simulate()
```

### CI/CD integration

```python
results = engine.simulate()

if results.resilience_score < 80:
    print("FAIL: Resilience score below threshold")
    sys.exit(2)
```
