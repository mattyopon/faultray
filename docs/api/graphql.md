# GraphQL API

FaultZero exposes a GraphQL endpoint for flexible querying of infrastructure models and simulation results.

## Endpoint

```
POST /api/graphql
```

## Schema Overview

```graphql
type Query {
  models: [Model!]!
  model(id: ID!): Model
  simulation(id: ID!): Simulation
  simulations(modelId: ID!): [Simulation!]!
}

type Mutation {
  createModel(input: ModelInput!): Model!
  runSimulation(modelId: ID!, options: SimulationOptions): Simulation!
  deleteModel(id: ID!): Boolean!
}

type Model {
  id: ID!
  name: String!
  nodes: [Node!]!
  edges: [Edge!]!
  createdAt: DateTime!
  latestScore: Int
}

type Node {
  id: ID!
  type: NodeType!
  provider: String
  region: String
  redundancy: Int
  metadata: JSON
}

type Edge {
  from: ID!
  to: ID!
  weight: Float
}

type Simulation {
  id: ID!
  modelId: ID!
  resilienceScore: Int!
  totalScenarios: Int!
  passed: Int!
  failed: Int!
  critical: Int!
  warning: Int!
  scenarios: [ScenarioResult!]!
  createdAt: DateTime!
}

type ScenarioResult {
  name: String!
  status: ScenarioStatus!
  impact: String
  affectedNodes: [ID!]!
}

enum NodeType {
  COMPUTE
  DATABASE
  LOAD_BALANCER
  CDN
  DNS
  STORAGE
  CACHE
  QUEUE
}

enum ScenarioStatus {
  PASSED
  WARNING
  FAILED
  CRITICAL
}
```

## Example Queries

### Get model with resilience score

```graphql
query {
  model(id: "abc123") {
    name
    latestScore
    nodes {
      id
      type
      region
    }
  }
}
```

### Run simulation and get results

```graphql
mutation {
  runSimulation(modelId: "abc123", options: { cascadeDepth: 5 }) {
    resilienceScore
    totalScenarios
    critical
    scenarios {
      name
      status
      affectedNodes
    }
  }
}
```

### List all critical findings

```graphql
query {
  simulation(id: "sim_456") {
    scenarios(filter: { status: CRITICAL }) {
      name
      impact
      affectedNodes
    }
  }
}
```

## Authentication

Include your API key in the `Authorization` header:

```bash
curl -X POST http://localhost:8000/api/graphql \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ models { id name latestScore } }"}'
```
