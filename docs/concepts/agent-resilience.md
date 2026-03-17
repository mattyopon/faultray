# AI Agent Resilience Simulation

FaultRay extends infrastructure resilience simulation to AI agent systems. It models agents, LLM endpoints, tool services, and orchestrators as first-class components in the dependency graph, then simulates agent-specific failure modes that traditional chaos engineering tools miss.

## Why Agent Resilience Matters

AI agents introduce failure modes that do not exist in traditional infrastructure:

- An agent can **hallucinate** (produce incorrect output) without any infrastructure component failing
- A **rate limit** on an LLM API can cascade through an entire multi-agent system
- An agent can enter an **infinite loop**, consuming resources without progress
- **Prompt injection** in external input can compromise agent behavior
- When a grounding data source goes down, agents may silently degrade to ungrounded responses

FaultRay simulates these scenarios before they happen in production.

## Component Types

FaultRay adds four agent-specific component types to the existing infrastructure types:

| Type | Value | When to Use |
|------|-------|-------------|
| **AI Agent** | `ai_agent` | Any LLM-powered agent that processes requests, uses tools, or makes decisions. Includes standalone agents and agents within multi-agent systems. |
| **LLM Endpoint** | `llm_endpoint` | The LLM API that agents call (Anthropic, OpenAI, Google, Azure OpenAI, self-hosted). Model rate limits, latency, and availability SLAs. |
| **Tool Service** | `tool_service` | External tools/APIs that agents invoke (database queries, web search, file operations, MCP servers). Tracks idempotency, side effects, and failure rates. |
| **Agent Orchestrator** | `agent_orchestrator` | Multi-agent coordination layer (sequential, parallel, hierarchical, or consensus patterns). Manages agent lifecycles and iteration limits. |

These integrate into the same dependency graph as traditional components (databases, load balancers, caches), enabling cross-layer analysis.

## Fault Types

Seven agent-specific fault types complement the existing infrastructure faults:

| Fault Type | Value | What It Simulates |
|------------|-------|-------------------|
| **Hallucination** | `hallucination` | Agent produces ungrounded, incorrect output. Downstream consumers receive wrong information. No infrastructure failure occurs -- the agent simply generates bad data. |
| **Context Overflow** | `context_overflow` | Agent's context window is exceeded. The agent cannot process the request and goes down until context is reset (~5s recovery). |
| **LLM Rate Limit** | `llm_rate_limit` | LLM provider throttles requests. Dependent agents experience delays or failures. Recovers when the rate limit window resets (~60s). |
| **Token Exhaustion** | `token_exhaustion` | Token budget is fully consumed. No further API calls are possible. Requires manual budget replenishment. |
| **Tool Failure** | `tool_failure` | A tool service fails. The agent falls back to LLM-only responses, which increases hallucination risk since the agent loses access to real data. |
| **Agent Loop** | `agent_loop` | Agent enters an infinite loop, consuming compute and tokens without making progress. Requires manual intervention or a circuit breaker. |
| **Prompt Injection** | `prompt_injection` | External input contains adversarial instructions that manipulate agent behavior. Agent outputs may be compromised. |

## Cross-Layer Analysis

The key insight of agent resilience simulation is that **infrastructure failures cause agent hallucinations**.

When a database or cache that serves as an agent's grounding data source goes down, the agent does not necessarily fail. Instead, it may continue operating but produce ungrounded responses -- hallucinations. This is worse than a clean failure because the system appears to work while producing incorrect results.

FaultRay traces these cross-layer dependencies:

```
Database (Layer 1) goes down
    |
    v
Agent loses grounding data source
    |
    v
Agent continues responding but hallucinates
    |
    v
Downstream tool service receives bad instructions
    |
    v
Tool executes incorrect action (e.g., wrong database write)
```

The `crossLayerRisk` query exposes this analysis. For each infrastructure component, it calculates which agents are affected and their hallucination probability when that component fails.

## The Three Pillars: PREDICT, ADOPT, MANAGE

FaultRay organizes agent resilience into three phases:

### PREDICT (Scenario Simulation)

Generate and run agent-specific chaos scenarios against your topology. This includes single-agent failures, cross-layer cascades, multi-endpoint outages, and prompt injection attacks.

```bash
faultray agent scenarios infra.yaml
```

### ADOPT (Risk Assessment)

Before deploying an agent, assess the risk it introduces. The ADOPT engine evaluates:

- **Blast radius** -- how many components are affected if this agent fails
- **Failsafe mechanisms** -- human escalation, fallback LLM, hallucination circuit breaker, iteration limits, redundancy, data grounding
- **Hallucination impact** -- what happens when the agent hallucinates (especially dangerous if it can trigger tools with side effects)
- **Risk score** (0-10) with actionable recommendations

```bash
faultray agent assess infra.yaml
```

Risk levels:
- **LOW** (0-3): Safe to deploy
- **MEDIUM** (4-6): Deploy with mitigations
- **HIGH** (7-8): Significant risk, needs redesign
- **CRITICAL** (9-10): Do not deploy without major changes

### MANAGE (Monitoring Plan)

Generate monitoring rules derived from simulation results. These rules detect pre-failure conditions before they cascade:

- Context window approaching capacity
- Hallucination detection rate exceeding baseline
- LLM request rate nearing provider limits
- Tool service error rate increasing
- Orchestrator approaching iteration limits
- Infrastructure degradation affecting agent grounding

```bash
faultray agent monitor infra.yaml
```

## Example YAML Configuration

```yaml
components:
  - id: claude-endpoint
    name: Claude API
    type: llm_endpoint
    replicas: 1
    parameters:
      provider: anthropic
      model_id: claude-sonnet-4-20250514
      rate_limit_rpm: 1000
      rate_limit_tpm: 100000
      avg_latency_ms: 500
      p99_latency_ms: 3000
      availability_sla: 99.9

  - id: support-agent
    name: Customer Support Agent
    type: ai_agent
    replicas: 2
    parameters:
      framework: langchain
      model_id: claude-sonnet-4-20250514
      max_context_tokens: 200000
      temperature: 0.3
      hallucination_risk: 0.03
      requires_grounding: 1
      fallback_model_id: gpt-4o
      circuit_breaker_on_hallucination: 1
      max_iterations: 25
      human_escalation: 1

  - id: search-tool
    name: Knowledge Base Search
    type: tool_service
    replicas: 2
    parameters:
      tool_type: database_query
      idempotent: 1
      side_effects: 0
      failure_rate: 0.005

  - id: ticket-tool
    name: Ticket Creation API
    type: tool_service
    replicas: 1
    parameters:
      tool_type: api
      idempotent: 0
      side_effects: 1
      failure_rate: 0.02

  - id: orchestrator
    name: Agent Coordinator
    type: agent_orchestrator
    replicas: 1
    parameters:
      pattern: hierarchical
      max_agents: 5
      timeout_seconds: 120
      max_iterations: 30
      circuit_breaker_on_hallucination: 1

  - id: customer-db
    name: Customer Database
    type: database
    replicas: 2
    region: us-east-1

dependencies:
  - from: support-agent
    to: claude-endpoint
  - from: support-agent
    to: search-tool
  - from: support-agent
    to: ticket-tool
  - from: search-tool
    to: customer-db
  - from: orchestrator
    to: support-agent
```

## CLI Usage

### Run all agent scenarios

```bash
# List generated scenarios
faultray agent scenarios infra.yaml

# JSON output for automation
faultray agent scenarios infra.yaml --json
```

### Assess agent deployment risk

```bash
# Interactive risk report
faultray agent assess infra.yaml

# JSON for CI/CD gate
faultray agent assess infra.yaml --json
```

### Generate monitoring plan

```bash
# View monitoring rules
faultray agent monitor infra.yaml

# Export as JSON for integration with Datadog, Grafana, etc.
faultray agent monitor infra.yaml --json
```

### Run full simulation including agent scenarios

```bash
# Standard simulation includes agent scenarios automatically
faultray simulate infra.yaml
```

## GraphQL API

Agent data is also available via the GraphQL API:

```graphql
{
  agentAssessment(topologyId: "default") {
    agentName
    riskScore
    riskLevel
    maxBlastRadius
    safeToDeploy
    recommendations
  }
}

{
  agentMonitoringPlan(topologyId: "default") {
    totalComponentsMonitored
    coveragePercent
    rules {
      name
      metric
      threshold
      severity
      recommendedAction
    }
  }
}

{
  agentScenarios(topologyId: "default") {
    id
    name
    description
    faults {
      target
      type
    }
  }
}

{
  crossLayerRisk(topologyId: "default", componentId: "customer-db") {
    agentId
    risk
    reason
  }
}
```
