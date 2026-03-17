# FaultRay v11.0.0 — AI Agent Resilience Simulation

FaultRay now simulates **AI agent failure modes** alongside traditional infrastructure, enabling unified resilience analysis across the full stack.

## Highlights

- **4 new component types**: `ai_agent`, `llm_endpoint`, `tool_service`, `agent_orchestrator` for modeling LangChain, CrewAI, AutoGen, and other agent frameworks
- **7 new fault types**: hallucination, context overflow, LLM rate limiting, token exhaustion, tool failure, agent loops, and prompt injection
- **3 new engines**: PREDICT (agent cascade simulation), ADOPT (agent adoption risk assessment), MANAGE (monitoring rule generation)
- **Cross-layer analysis**: Infrastructure failures (DB down, cache miss) are automatically assessed for agent hallucination risk, with blast radius spanning both infrastructure and agent layers

## New CLI Commands

```
faultray agent assess <topology>     # Agent adoption risk assessment
faultray agent monitor <topology>    # Generate monitoring rules
faultray agent scenarios <topology>  # List agent-specific chaos scenarios
```

## YAML Schema

Schema version bumped to **4.0** with new `agent_config`, `llm_config`, `tool_config`, and `orchestrator_config` syntax. Fully backward compatible with existing v3.0 topologies.

## Engine Changes

- `CascadeEngine` now delegates to `AgentCascadeEngine` for agent-specific faults
- `SimulationEngine.run_all_defaults()` automatically includes agent scenarios

## Install

```bash
pip install faultray==11.0.0
```

## Full Changelog

See [CHANGELOG.md](https://github.com/mattyopon/faultray/blob/main/CHANGELOG.md) for the complete history.
