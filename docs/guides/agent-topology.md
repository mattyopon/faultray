# AI Agent Topology (#83)

FaultRay v11+ models AI agents as first-class components alongside
infrastructure. Four optional YAML config groups describe agent behavior:

| Group | Purpose | Flattened into |
|---|---|---|
| `agent_config` | Agent-level behavior (loop limits, memory, tools) | `component.parameters` |
| `llm_config` | LLM choice + rate limits + fallback | `component.parameters` |
| `tool_config` | External tool allow-list + permissions | `component.parameters` |
| `orchestrator_config` | Multi-agent orchestration (supervisor, voting) | `component.parameters` |

All four groups are **optional** — omit what you don't need. Keys get
flattened into `component.parameters` (see
`src/faultray/model/loader.py:214-224`) so downstream simulator engines
(adoption, monitor, scenarios) see a unified parameter bag.

## Minimal example

```yaml
# examples/agent-topology-minimal.yaml
schema_version: "4.0"
components:
  - id: sre_bot
    name: SRE Copilot
    type: ai_agent
    host: agent-sre.internal
    port: 443

    agent_config:
      max_loop_iterations: 5
      memory_backend: redis
      timeout_seconds: 30

    llm_config:
      provider: anthropic
      model: claude-sonnet-4
      max_tokens: 4000
      rate_limit_rpm: 60
      fallback_provider: openai
      fallback_model: gpt-4.1

    tool_config:
      allowed_tools:
        - kubectl.read
        - prometheus.query
      permission_mode: least_privilege

  - id: kubernetes
    name: Kubernetes API
    type: container_orchestrator
    host: kubeapi.internal
    port: 6443

dependencies:
  - source: sre_bot
    target: kubernetes
    type: requires
```

## Advanced: multi-agent orchestrator

```yaml
# examples/agent-topology-advanced.yaml
schema_version: "4.0"
components:
  - id: supervisor
    name: Incident Supervisor
    type: ai_agent

    agent_config:
      role: supervisor
      max_loop_iterations: 3

    orchestrator_config:
      strategy: majority_vote
      workers: [triage_bot, remediation_bot, audit_bot]
      voting_threshold: 0.67
      timeout_seconds: 60

  - id: triage_bot
    name: Triage Agent
    type: ai_agent
    agent_config: { role: worker, specialty: log_analysis }
    llm_config: { provider: anthropic, model: claude-haiku-4-5 }

  - id: remediation_bot
    name: Remediation Agent
    type: ai_agent
    agent_config: { role: worker, specialty: infra_action }
    llm_config: { provider: anthropic, model: claude-sonnet-4-6 }
    tool_config:
      allowed_tools: [kubectl.patch, pagerduty.resolve]
      permission_mode: require_approval

  - id: audit_bot
    name: Audit Agent
    type: ai_agent
    agent_config: { role: worker, specialty: compliance_check }
    llm_config: { provider: openai, model: gpt-4.1 }

dependencies:
  - { source: supervisor, target: triage_bot, type: requires }
  - { source: supervisor, target: remediation_bot, type: requires }
  - { source: supervisor, target: audit_bot, type: requires }
```

## Key → engine mapping

These keys are what the simulator engines look for after flattening:

| Parameter key (flattened) | Consumer engine |
|---|---|
| `max_loop_iterations` | `AdoptionEngine` (loop-risk heuristic) |
| `memory_backend` | `AdoptionEngine` (state-loss blast-radius) |
| `timeout_seconds` | `AgentMonitorEngine` (SLO alerts) |
| `provider` / `model` | `AdoptionEngine` (rate-limit cascade) |
| `rate_limit_rpm` | `AdoptionEngine` + scenario generator |
| `fallback_provider` / `fallback_model` | resilience credit in score |
| `allowed_tools` | `AgentScenarios` (blast radius bound) |
| `permission_mode` | `AgentScenarios` + supply-chain engine |
| `strategy` (orchestrator) | multi-agent cascade scenario |
| `voting_threshold` | orchestrator quorum scenario |

Unknown keys are passed through — forward-compatible for new engines.

## Validation

`faultray load <file>.yaml` prints a warning line if a required key is
missing for an `ai_agent`-typed component. `faultray simulate --engine
agent` refuses to run if no `agent_config` or `llm_config` is present
on any `ai_agent` node.

## Related

- [Minimal example](../../examples/agent-topology-minimal.yaml)
- [Advanced example](../../examples/agent-topology-advanced.yaml)
- Loader source: `src/faultray/model/loader.py:214-224` (flattening)
- CHANGELOG v11.0.0 entry: introduced the four config groups
