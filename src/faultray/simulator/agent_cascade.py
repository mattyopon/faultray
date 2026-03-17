"""Agent-specific cascade failure logic for AI agent components."""

from __future__ import annotations

from faultray.model.components import ComponentType, HealthStatus, Component
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeEffect


def apply_agent_direct_effect(component: Component, fault_type_value: str) -> CascadeEffect | None:
    """Apply direct fault effect for agent component types.

    Returns None if this is not an agent-specific fault, letting the
    standard CascadeEngine handle it.
    """

    agent_fault_map = {
        "hallucination": {
            "health": HealthStatus.DEGRADED,
            "reason": f"Agent {component.name} is hallucinating — producing ungrounded outputs. "
                      "Downstream consumers may receive incorrect information.",
            "time": 0,  # Instant, no recovery needed — just wrong output
        },
        "context_overflow": {
            "health": HealthStatus.DOWN,
            "reason": f"Agent {component.name} context window exceeded — cannot process request. "
                      "Agent is unable to function until context is reset.",
            "time": 5,  # Context reset time
        },
        "llm_rate_limit": {
            "health": HealthStatus.OVERLOADED,
            "reason": f"LLM endpoint {component.name} rate limit reached — requests are being throttled. "
                      "Dependent agents will experience delays or failures.",
            "time": 60,  # Rate limit window reset
        },
        "token_exhaustion": {
            "health": HealthStatus.DOWN,
            "reason": f"Token budget for {component.name} exhausted — no further API calls possible. "
                      "Agent is completely non-functional until budget is replenished.",
            "time": 0,  # Manual intervention required
        },
        "tool_failure": {
            "health": HealthStatus.DEGRADED,
            "reason": f"Tool service {component.name} is failing — agent cannot execute tool calls. "
                      "Agent may fall back to LLM-only responses (increased hallucination risk).",
            "time": 30,
        },
        "agent_loop": {
            "health": HealthStatus.DOWN,
            "reason": f"Agent {component.name} entered infinite loop — consuming resources without progress. "
                      "Max iterations exceeded. Requires manual intervention.",
            "time": 0,
        },
        "prompt_injection": {
            "health": HealthStatus.DEGRADED,
            "reason": f"Agent {component.name} behavior compromised by prompt injection in external input. "
                      "Agent outputs may be manipulated. Security risk.",
            "time": 0,
        },
    }

    effect_def = agent_fault_map.get(fault_type_value)
    if effect_def is None:
        return None

    return CascadeEffect(
        component_id=component.id,
        component_name=component.name,
        health=effect_def["health"],
        reason=effect_def["reason"],
        estimated_time_seconds=effect_def["time"],
        metrics_impact={},
        latency_ms=0.0,
    )


def calculate_agent_likelihood(component: Component, fault_type_value: str) -> float | None:
    """Calculate likelihood for agent-specific faults.

    Returns None if not an agent-specific fault.

    Note: Component.parameters values are float | int | str, so boolean-like
    parameters are stored as int (1/0) or str ("true"/"false").
    """
    params = component.parameters or {}

    if fault_type_value == "hallucination":
        # Higher risk if: no grounding, high temperature, no tools
        base_risk = float(params.get("hallucination_risk", 0.05))
        has_grounding = bool(params.get("requires_grounding", 0))
        if not has_grounding:
            base_risk *= 2.0
        return min(1.0, max(0.2, base_risk * 10))  # Scale to 0.2-1.0

    if fault_type_value == "context_overflow":
        max_tokens = int(params.get("max_context_tokens", 200000))
        # Larger context = less likely to overflow
        if max_tokens >= 200000:
            return 0.2
        elif max_tokens >= 100000:
            return 0.4
        elif max_tokens >= 32000:
            return 0.6
        return 0.8

    if fault_type_value == "llm_rate_limit":
        return 0.5  # Depends on traffic, moderate baseline

    if fault_type_value == "token_exhaustion":
        return 0.3  # Budget management usually prevents this

    if fault_type_value == "tool_failure":
        failure_rate = float(params.get("failure_rate", 0.01))
        return min(1.0, max(0.2, failure_rate * 20))

    if fault_type_value == "agent_loop":
        return 0.3  # Relatively rare with proper max_iterations

    if fault_type_value == "prompt_injection":
        return 0.4  # Depends on input sanitization

    return None


AGENT_COMPONENT_TYPES = {
    ComponentType.AI_AGENT,
    ComponentType.LLM_ENDPOINT,
    ComponentType.TOOL_SERVICE,
    ComponentType.AGENT_ORCHESTRATOR,
}

AGENT_FAULT_TYPES = {
    "hallucination", "context_overflow", "llm_rate_limit",
    "token_exhaustion", "tool_failure", "agent_loop", "prompt_injection",
}


def is_agent_component(component: Component) -> bool:
    """Check if a component is an agent-type component."""
    return component.type in AGENT_COMPONENT_TYPES


def is_agent_fault(fault_type_value: str) -> bool:
    """Check if a fault type is agent-specific."""
    return fault_type_value in AGENT_FAULT_TYPES


def calculate_cross_layer_hallucination_risk(
    graph: InfraGraph,
    failed_component_id: str,
) -> list[tuple[str, float, str]]:
    """Calculate hallucination risk for agents that depend on a failed infra component.

    This is the KEY cross-layer insight: infrastructure failures can cause
    agent hallucinations when agents lose access to their grounding data.

    Returns list of (agent_id, hallucination_probability, reason).
    """
    risks: list[tuple[str, float, str]] = []
    failed = graph.get_component(failed_component_id)
    if failed is None:
        return risks

    # Find all agents that transitively depend on the failed component
    affected_ids = graph.get_all_affected(failed_component_id)

    for comp_id in affected_ids:
        comp = graph.get_component(comp_id)
        if comp is None:
            continue
        if comp.type != ComponentType.AI_AGENT:
            continue

        params = comp.parameters or {}
        requires_grounding = bool(params.get("requires_grounding", 0))
        base_hallucination_risk = float(params.get("hallucination_risk", 0.05))

        # If the agent requires grounding and its data source is down,
        # hallucination risk increases dramatically
        if requires_grounding and failed.type in (ComponentType.DATABASE, ComponentType.CACHE, ComponentType.STORAGE):
            risk = min(1.0, base_hallucination_risk * 10)
            reason = (
                f"Agent '{comp.name}' requires grounding data from '{failed.name}' ({failed.type.value}). "
                f"With data source down, agent may hallucinate at {risk:.0%} probability."
            )
            risks.append((comp.id, risk, reason))
        elif failed.type == ComponentType.EXTERNAL_API:
            risk = min(1.0, base_hallucination_risk * 5)
            reason = (
                f"Agent '{comp.name}' depends on external API '{failed.name}'. "
                f"Without API access, agent may produce ungrounded responses at {risk:.0%} probability."
            )
            risks.append((comp.id, risk, reason))

    return risks
