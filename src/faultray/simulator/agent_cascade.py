"""Agent-specific cascade failure logic for AI agent components.

Implements the formal probabilistic model defined in:
    docs/patent/ai-agent-formal-spec.md

Key concepts:
    - H(a, D, I): Hallucination probability as a function of agent a,
      data sources D, and infrastructure state I.
    - Cross-layer cascade: Infrastructure faults (L1) propagate through
      data availability (L2) to agent behavior (L3) to downstream impact (L4).
    - Agent-to-agent cascade: Hallucinated output from agent A fed to agent B
      produces compound failure with probability H_chain.
    - 10-mode failure taxonomy covering all known AI agent failure modes.
"""

from __future__ import annotations

from dataclasses import dataclass

from faultray.model.components import ComponentType, HealthStatus, Component
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeEffect


# ---------------------------------------------------------------------------
# Formal probabilistic model (see ai-agent-formal-spec.md Section 1)
# ---------------------------------------------------------------------------

# Default degradation/overload factors for H(a, D, I) computation
DEFAULT_DEGRADATION_FACTOR = 0.5  # delta in spec
DEFAULT_OVERLOAD_FACTOR = 0.3     # omega in spec


@dataclass
class DataSourceState:
    """State of a single data source relative to an agent.

    Attributes:
        source_id: Component ID of the data source.
        weight: Dependency weight w(d) in [0, 1].
        status: Current health status from infrastructure state I.
    """
    source_id: str
    weight: float
    status: HealthStatus


def calculate_hallucination_probability(
    agent: Component,
    infra_state: dict[str, HealthStatus] | None = None,
    data_sources: list[DataSourceState] | None = None,
    *,
    degradation_factor: float = DEFAULT_DEGRADATION_FACTOR,
    overload_factor: float = DEFAULT_OVERLOAD_FACTOR,
) -> float:
    """Compute H(a, D, I) — hallucination probability for an agent.

    Implements the formal model from ai-agent-formal-spec.md Section 1:

        For each data source d:
            If HEALTHY:   h_d = h0
            If DOWN:      h_d = h0 + (1 - h0) * w(d)
            If DEGRADED:  h_d = h0 + (1 - h0) * w(d) * degradation_factor
            If OVERLOADED: h_d = h0 + (1 - h0) * w(d) * overload_factor

        Combined: H = 1 - product(1 - h_d) for all unhealthy sources
        When all healthy: H = h0

    Args:
        agent: The AI agent component.
        infra_state: Mapping of component_id -> HealthStatus. If provided and
            data_sources is None, data sources are inferred from agent parameters.
        data_sources: Explicit list of DataSourceState objects. Overrides
            infra_state-based inference when provided.
        degradation_factor: delta factor for DEGRADED sources (default 0.5).
        overload_factor: omega factor for OVERLOADED sources (default 0.3).

    Returns:
        Hallucination probability in [0, 1].
    """
    params = agent.parameters or {}
    h0 = float(params.get("hallucination_risk", 0.05))

    if data_sources is None and infra_state is None:
        return h0

    sources = data_sources or []

    # If no explicit data_sources but infra_state provided, build from params
    if not sources and infra_state:
        dep_weights = params.get("data_source_weights", "")
        if isinstance(dep_weights, str) and dep_weights:
            # Format: "source_id:weight,source_id:weight,..."
            for pair in dep_weights.split(","):
                parts = pair.strip().split(":")
                if len(parts) == 2:
                    sid, w = parts[0].strip(), float(parts[1].strip())
                    status = infra_state.get(sid, HealthStatus.HEALTHY)
                    sources.append(DataSourceState(source_id=sid, weight=w, status=status))

    if not sources:
        return h0

    # Compute per-source h_d values for unhealthy sources
    unhealthy_contributions: list[float] = []
    for ds in sources:
        if ds.status == HealthStatus.HEALTHY:
            continue
        w = min(1.0, max(0.0, ds.weight))
        if ds.status == HealthStatus.DOWN:
            h_d = h0 + (1.0 - h0) * w
        elif ds.status == HealthStatus.DEGRADED:
            h_d = h0 + (1.0 - h0) * w * degradation_factor
        elif ds.status == HealthStatus.OVERLOADED:
            h_d = h0 + (1.0 - h0) * w * overload_factor
        else:
            continue
        unhealthy_contributions.append(h_d)

    if not unhealthy_contributions:
        return h0

    # Combined: H = 1 - product(1 - h_d)
    product = 1.0
    for h_d in unhealthy_contributions:
        product *= (1.0 - h_d)
    return min(1.0, max(0.0, 1.0 - product))


def calculate_agent_cascade_probability(
    source_agent_h: float,
    target_agent_h: float,
    amplification_factor: float = 1.0,
) -> float:
    """Compute effective hallucination probability for an agent receiving output from another agent.

    Implements agent-to-agent cascade from ai-agent-formal-spec.md Section 4:

        H_effective(target) = 1 - (1 - H(target)) * (1 - H(source) * amplification)

    Args:
        source_agent_h: Hallucination probability of the upstream (source) agent.
        target_agent_h: Hallucination probability of the downstream (target) agent.
        amplification_factor: How much of the source's hallucination propagates.
            1.0 = no independent verification; 0.0 = full verification (no propagation).

    Returns:
        Effective hallucination probability for the target agent in [0, 1].
    """
    amp = min(1.0, max(0.0, amplification_factor))
    inherited_risk = source_agent_h * amp
    h_effective = 1.0 - (1.0 - target_agent_h) * (1.0 - inherited_risk)
    return min(1.0, max(0.0, h_effective))


def calculate_chain_hallucination_probability(
    agent_probabilities: list[float],
) -> float:
    """Compute compound hallucination probability for a chain of agents.

    Implements H_chain from ai-agent-formal-spec.md Section 4:

        H_chain(a_n) = 1 - product(1 - H_effective(a_i)) for i = 1..n

    Args:
        agent_probabilities: List of per-agent effective hallucination probabilities.

    Returns:
        Compound probability that at least one agent in the chain hallucinates.
    """
    if not agent_probabilities:
        return 0.0
    product = 1.0
    for p in agent_probabilities:
        product *= (1.0 - min(1.0, max(0.0, p)))
    return min(1.0, max(0.0, 1.0 - product))


# ---------------------------------------------------------------------------
# Agent fault taxonomy (10 modes — see ai-agent-formal-spec.md Section 3)
# ---------------------------------------------------------------------------

def apply_agent_direct_effect(component: Component, fault_type_value: str) -> CascadeEffect | None:
    """Apply direct fault effect for agent component types.

    Covers the complete 10-mode failure taxonomy defined in the formal spec.
    Returns None if this is not an agent-specific fault, letting the
    standard CascadeEngine handle it.
    """

    agent_fault_map: dict[str, dict] = {
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
        # --- New failure modes (completing the 10-mode taxonomy) ---
        "confidence_miscalibration": {
            "health": HealthStatus.DEGRADED,
            "reason": f"Agent {component.name} confidence scores are miscalibrated — high confidence "
                      "on incorrect outputs. Downstream systems may trust unreliable information.",
            "time": 0,  # Requires model recalibration
        },
        "cot_collapse": {
            "health": HealthStatus.DEGRADED,
            "reason": f"Agent {component.name} chain-of-thought reasoning collapsed mid-sequence. "
                      "Initial reasoning steps may be valid but final answer is unreliable.",
            "time": 0,  # Retry or reduce complexity
        },
        "output_amplification": {
            "health": HealthStatus.DEGRADED,
            "reason": f"Agent {component.name} is amplifying hallucinated input from upstream agent. "
                      "Compound error: upstream hallucination treated as ground truth.",
            "time": 0,  # Requires breaking cascade chain
        },
        "grounding_staleness": {
            "health": HealthStatus.DEGRADED,
            "reason": f"Agent {component.name} grounding data is stale — cached information is outdated. "
                      "Responses may be structurally valid but factually incorrect.",
            "time": 300,  # Cache refresh time
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

    Uses the formal probabilistic model H(a, D, I) for hallucination-related
    faults and heuristic models for other fault types.

    Returns None if not an agent-specific fault.

    Note: Component.parameters values are float | int | str, so boolean-like
    parameters are stored as int (1/0) or str ("true"/"false").
    """
    params = component.parameters or {}

    if fault_type_value == "hallucination":
        # Use the formal model: compute H(a, D, I) with available info
        h0 = float(params.get("hallucination_risk", 0.05))
        has_grounding = bool(params.get("requires_grounding", 0))
        if not has_grounding:
            # Without grounding, base rate is amplified (agent has no data sources
            # to anchor outputs, so model hallucination_risk acts as a stronger signal)
            h0 = min(1.0, h0 * 2.0)
        # Scale to likelihood range [0.2, 1.0] for cascade severity computation
        return min(1.0, max(0.2, h0 * 10))

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

    # --- New failure modes ---

    if fault_type_value == "confidence_miscalibration":
        # Higher risk when temperature is high or model is fine-tuned
        temperature = float(params.get("temperature", 0.7))
        return min(1.0, max(0.2, temperature * 0.6))

    if fault_type_value == "cot_collapse":
        # More likely with longer reasoning chains and smaller context windows
        max_tokens = int(params.get("max_context_tokens", 200000))
        if max_tokens < 32000:
            return 0.5
        return 0.3

    if fault_type_value == "output_amplification":
        # Likelihood depends on whether the agent consumes other agents' output
        has_agent_input = bool(params.get("receives_agent_output", 0))
        if has_agent_input:
            return 0.6  # Significant risk when consuming unverified agent output
        return 0.2

    if fault_type_value == "grounding_staleness":
        # Higher risk when cache TTLs are long
        cache_ttl = float(params.get("grounding_cache_ttl_seconds", 300))
        if cache_ttl > 3600:
            return 0.7
        elif cache_ttl > 600:
            return 0.5
        return 0.3

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
    "confidence_miscalibration", "cot_collapse", "output_amplification",
    "grounding_staleness",
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

    Implements the cross-layer cascade model (L1 -> L2 -> L3) from
    ai-agent-formal-spec.md Section 2.

    Infrastructure failure (L1) causes data source unavailability (L2), which
    increases agent hallucination probability (L3) via the formal model H(a, D, I).

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
        h0 = float(params.get("hallucination_risk", 0.05))

        # Determine dependency weight based on failed component type
        grounding_types = (ComponentType.DATABASE, ComponentType.CACHE, ComponentType.STORAGE)
        is_grounding_source = failed.type in grounding_types
        is_external_api = failed.type == ComponentType.EXTERNAL_API

        if requires_grounding and is_grounding_source:
            # Use formal model: data source is DOWN with weight 1.0 (critical grounding)
            w = 1.0
            h_d = h0 + (1.0 - h0) * w  # = 1.0 when h0 < 1
            risk = min(1.0, 1.0 - (1.0 - h_d))  # single source: H = h_d
            reason = (
                f"Agent '{comp.name}' requires grounding data from '{failed.name}' ({failed.type.value}). "
                f"With data source DOWN, hallucination probability H(a,D,I) = {risk:.0%} "
                f"(base h0={h0}, weight w={w}, status=DOWN)."
            )
            risks.append((comp.id, risk, reason))
        elif is_external_api:
            # External API: significant but not total grounding dependency
            w = 0.8
            h_d = h0 + (1.0 - h0) * w
            risk = min(1.0, h_d)
            reason = (
                f"Agent '{comp.name}' depends on external API '{failed.name}'. "
                f"Without API access, hallucination probability H(a,D,I) = {risk:.0%} "
                f"(base h0={h0}, weight w={w}, status=DOWN)."
            )
            risks.append((comp.id, risk, reason))

    return risks


def propagate_agent_to_agent_cascade(
    graph: InfraGraph,
    source_agent_id: str,
    source_hallucination_prob: float,
) -> list[tuple[str, float, str]]:
    """Propagate hallucination risk from one agent to downstream agents.

    Implements agent-to-agent cascade from ai-agent-formal-spec.md Section 4:
    When agent A hallucinates and its output feeds agent B, agent B's effective
    hallucination probability increases.

    Args:
        graph: The infrastructure dependency graph.
        source_agent_id: ID of the source agent that is hallucinating.
        source_hallucination_prob: H(source) — hallucination probability of source.

    Returns:
        List of (agent_id, effective_hallucination_prob, reason) for all
        downstream agents affected by the cascade.
    """
    results: list[tuple[str, float, str]] = []
    source = graph.get_component(source_agent_id)
    if source is None:
        return results

    # BFS through agents that depend on this agent's output
    visited: set[str] = {source_agent_id}
    # Queue: (agent_id, incoming_h_prob)
    from collections import deque
    queue: deque[tuple[str, float]] = deque()

    # Find direct dependents that are agents
    for dep_comp in graph.get_dependents(source_agent_id):
        if dep_comp.id not in visited and dep_comp.type == ComponentType.AI_AGENT:
            queue.append((dep_comp.id, source_hallucination_prob))
            visited.add(dep_comp.id)

    while queue:
        agent_id, incoming_h = queue.popleft()
        agent = graph.get_component(agent_id)
        if agent is None:
            continue

        params = agent.parameters or {}
        h0 = float(params.get("hallucination_risk", 0.05))
        amp = float(params.get("amplification_factor", 1.0))

        # Compute effective hallucination probability
        h_effective = calculate_agent_cascade_probability(incoming_h, h0, amp)

        reason = (
            f"Agent '{agent.name}' receives output from hallucinating upstream agent. "
            f"Compound hallucination probability: H_effective = {h_effective:.0%} "
            f"(own h0={h0}, upstream H={incoming_h:.2f}, amplification={amp})."
        )
        results.append((agent_id, h_effective, reason))

        # Continue cascade to further downstream agents
        for next_dep in graph.get_dependents(agent_id):
            if next_dep.id not in visited and next_dep.type == ComponentType.AI_AGENT:
                queue.append((next_dep.id, h_effective))
                visited.add(next_dep.id)

    return results
