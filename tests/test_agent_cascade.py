"""Tests for agent-specific cascade failure logic."""

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.agent_cascade import (
    AGENT_COMPONENT_TYPES,
    AGENT_FAULT_TYPES,
    apply_agent_direct_effect,
    calculate_agent_likelihood,
    calculate_cross_layer_hallucination_risk,
    is_agent_component,
    is_agent_fault,
)


def _agent(
    id: str = "agent-1",
    name: str = "Test Agent",
    comp_type: ComponentType = ComponentType.AI_AGENT,
    **params,
) -> Component:
    """Create an agent component with optional parameters."""
    return Component(
        id=id, name=name, type=comp_type, parameters=params,
    )


def _infra(
    id: str = "db-1",
    name: str = "Database",
    comp_type: ComponentType = ComponentType.DATABASE,
) -> Component:
    """Create an infrastructure component."""
    return Component(id=id, name=name, type=comp_type)


def _build_db_tool_agent_graph() -> InfraGraph:
    """Build a graph: DB -> Tool -> Agent (agent depends on tool, tool depends on DB)."""
    g = InfraGraph()
    g.add_component(Component(
        id="db", name="Postgres", type=ComponentType.DATABASE,
    ))
    g.add_component(Component(
        id="tool", name="DB Query Tool", type=ComponentType.TOOL_SERVICE,
    ))
    g.add_component(Component(
        id="agent", name="Support Agent", type=ComponentType.AI_AGENT,
        parameters={"requires_grounding": 1, "hallucination_risk": 0.05},
    ))
    g.add_dependency(Dependency(source_id="agent", target_id="tool", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="tool", target_id="db", dependency_type="requires"))
    return g


class TestApplyAgentDirectEffect:
    """Test apply_agent_direct_effect for each agent fault type."""

    def test_hallucination_effect(self):
        comp = _agent(name="ChatBot")
        effect = apply_agent_direct_effect(comp, "hallucination")
        assert effect is not None
        assert effect.health == HealthStatus.DEGRADED
        assert effect.component_id == comp.id
        assert "hallucinating" in effect.reason

    def test_context_overflow_effect(self):
        comp = _agent(name="Summarizer")
        effect = apply_agent_direct_effect(comp, "context_overflow")
        assert effect is not None
        assert effect.health == HealthStatus.DOWN
        assert effect.estimated_time_seconds == 5
        assert "context window exceeded" in effect.reason

    def test_llm_rate_limit_effect(self):
        comp = _agent(name="API Endpoint", comp_type=ComponentType.LLM_ENDPOINT)
        effect = apply_agent_direct_effect(comp, "llm_rate_limit")
        assert effect is not None
        assert effect.health == HealthStatus.OVERLOADED
        assert effect.estimated_time_seconds == 60
        assert "rate limit" in effect.reason

    def test_token_exhaustion_effect(self):
        comp = _agent(name="Budget Agent")
        effect = apply_agent_direct_effect(comp, "token_exhaustion")
        assert effect is not None
        assert effect.health == HealthStatus.DOWN
        assert effect.estimated_time_seconds == 0
        assert "Token budget" in effect.reason

    def test_tool_failure_effect(self):
        comp = _agent(name="Tool Runner", comp_type=ComponentType.TOOL_SERVICE)
        effect = apply_agent_direct_effect(comp, "tool_failure")
        assert effect is not None
        assert effect.health == HealthStatus.DEGRADED
        assert effect.estimated_time_seconds == 30
        assert "failing" in effect.reason

    def test_agent_loop_effect(self):
        comp = _agent(name="Loop Agent")
        effect = apply_agent_direct_effect(comp, "agent_loop")
        assert effect is not None
        assert effect.health == HealthStatus.DOWN
        assert "infinite loop" in effect.reason

    def test_prompt_injection_effect(self):
        comp = _agent(name="Public Agent")
        effect = apply_agent_direct_effect(comp, "prompt_injection")
        assert effect is not None
        assert effect.health == HealthStatus.DEGRADED
        assert "prompt injection" in effect.reason

    def test_non_agent_fault_returns_none(self):
        comp = _agent()
        effect = apply_agent_direct_effect(comp, "component_down")
        assert effect is None

    def test_unknown_fault_returns_none(self):
        comp = _agent()
        effect = apply_agent_direct_effect(comp, "nonexistent_fault")
        assert effect is None

    def test_effect_has_correct_component_info(self):
        comp = _agent(id="my-agent", name="My Agent")
        effect = apply_agent_direct_effect(comp, "hallucination")
        assert effect is not None
        assert effect.component_id == "my-agent"
        assert effect.component_name == "My Agent"


class TestCalculateAgentLikelihood:
    """Test calculate_agent_likelihood for each fault type."""

    def test_hallucination_no_grounding(self):
        comp = _agent(hallucination_risk=0.05, requires_grounding=0)
        likelihood = calculate_agent_likelihood(comp, "hallucination")
        assert likelihood is not None
        # No grounding doubles risk: 0.05 * 2.0 * 10 = 1.0, clamped to [0.2, 1.0]
        assert 0.2 <= likelihood <= 1.0

    def test_hallucination_with_grounding(self):
        comp = _agent(hallucination_risk=0.05, requires_grounding=1)
        likelihood = calculate_agent_likelihood(comp, "hallucination")
        assert likelihood is not None
        # With grounding: 0.05 * 10 = 0.5
        assert 0.2 <= likelihood <= 1.0

    def test_hallucination_with_grounding_lower_than_without(self):
        comp_grounded = _agent(hallucination_risk=0.05, requires_grounding=1)
        comp_ungrounded = _agent(hallucination_risk=0.05, requires_grounding=0)
        l_grounded = calculate_agent_likelihood(comp_grounded, "hallucination")
        l_ungrounded = calculate_agent_likelihood(comp_ungrounded, "hallucination")
        assert l_grounded is not None
        assert l_ungrounded is not None
        assert l_grounded <= l_ungrounded

    def test_context_overflow_large_context(self):
        comp = _agent(max_context_tokens=200000)
        likelihood = calculate_agent_likelihood(comp, "context_overflow")
        assert likelihood == 0.2

    def test_context_overflow_medium_context(self):
        comp = _agent(max_context_tokens=100000)
        likelihood = calculate_agent_likelihood(comp, "context_overflow")
        assert likelihood == 0.4

    def test_context_overflow_small_context(self):
        comp = _agent(max_context_tokens=32000)
        likelihood = calculate_agent_likelihood(comp, "context_overflow")
        assert likelihood == 0.6

    def test_context_overflow_very_small_context(self):
        comp = _agent(max_context_tokens=8000)
        likelihood = calculate_agent_likelihood(comp, "context_overflow")
        assert likelihood == 0.8

    def test_llm_rate_limit_baseline(self):
        comp = _agent()
        likelihood = calculate_agent_likelihood(comp, "llm_rate_limit")
        assert likelihood == 0.5

    def test_token_exhaustion_baseline(self):
        comp = _agent()
        likelihood = calculate_agent_likelihood(comp, "token_exhaustion")
        assert likelihood == 0.3

    def test_tool_failure_low_failure_rate(self):
        comp = _agent(failure_rate=0.01)
        likelihood = calculate_agent_likelihood(comp, "tool_failure")
        assert likelihood is not None
        assert 0.2 <= likelihood <= 1.0

    def test_tool_failure_high_failure_rate(self):
        comp = _agent(failure_rate=0.1)
        likelihood = calculate_agent_likelihood(comp, "tool_failure")
        assert likelihood is not None
        assert likelihood > calculate_agent_likelihood(
            _agent(failure_rate=0.01), "tool_failure"
        )

    def test_agent_loop_baseline(self):
        comp = _agent()
        likelihood = calculate_agent_likelihood(comp, "agent_loop")
        assert likelihood == 0.3

    def test_prompt_injection_baseline(self):
        comp = _agent()
        likelihood = calculate_agent_likelihood(comp, "prompt_injection")
        assert likelihood == 0.4

    def test_non_agent_fault_returns_none(self):
        comp = _agent()
        likelihood = calculate_agent_likelihood(comp, "component_down")
        assert likelihood is None

    def test_unknown_fault_returns_none(self):
        comp = _agent()
        likelihood = calculate_agent_likelihood(comp, "nonexistent")
        assert likelihood is None


class TestIsAgentComponent:
    """Test is_agent_component helper."""

    def test_ai_agent_is_agent(self):
        assert is_agent_component(_agent(comp_type=ComponentType.AI_AGENT))

    def test_llm_endpoint_is_agent(self):
        assert is_agent_component(_agent(comp_type=ComponentType.LLM_ENDPOINT))

    def test_tool_service_is_agent(self):
        assert is_agent_component(_agent(comp_type=ComponentType.TOOL_SERVICE))

    def test_orchestrator_is_agent(self):
        assert is_agent_component(_agent(comp_type=ComponentType.AGENT_ORCHESTRATOR))

    def test_database_is_not_agent(self):
        assert not is_agent_component(_infra(comp_type=ComponentType.DATABASE))

    def test_app_server_is_not_agent(self):
        assert not is_agent_component(_infra(comp_type=ComponentType.APP_SERVER))

    def test_load_balancer_is_not_agent(self):
        assert not is_agent_component(_infra(comp_type=ComponentType.LOAD_BALANCER))


class TestIsAgentFault:
    """Test is_agent_fault helper."""

    def test_hallucination_is_agent_fault(self):
        assert is_agent_fault("hallucination")

    def test_context_overflow_is_agent_fault(self):
        assert is_agent_fault("context_overflow")

    def test_llm_rate_limit_is_agent_fault(self):
        assert is_agent_fault("llm_rate_limit")

    def test_token_exhaustion_is_agent_fault(self):
        assert is_agent_fault("token_exhaustion")

    def test_tool_failure_is_agent_fault(self):
        assert is_agent_fault("tool_failure")

    def test_agent_loop_is_agent_fault(self):
        assert is_agent_fault("agent_loop")

    def test_prompt_injection_is_agent_fault(self):
        assert is_agent_fault("prompt_injection")

    def test_component_down_is_not_agent_fault(self):
        assert not is_agent_fault("component_down")

    def test_latency_spike_is_not_agent_fault(self):
        assert not is_agent_fault("latency_spike")

    def test_unknown_is_not_agent_fault(self):
        assert not is_agent_fault("nonexistent")


class TestAgentConstantSets:
    """Test AGENT_COMPONENT_TYPES and AGENT_FAULT_TYPES sets."""

    def test_agent_component_types_has_four_entries(self):
        assert len(AGENT_COMPONENT_TYPES) == 4

    def test_agent_fault_types_has_seven_entries(self):
        assert len(AGENT_FAULT_TYPES) == 7

    def test_agent_fault_types_match_fault_enum(self):
        """All entries in AGENT_FAULT_TYPES should correspond to FaultType values."""
        from faultray.simulator.scenarios import FaultType
        fault_values = {ft.value for ft in FaultType}
        for aft in AGENT_FAULT_TYPES:
            assert aft in fault_values, f"{aft} not found in FaultType enum"


class TestCalculateCrossLayerHallucinationRisk:
    """Test cross-layer hallucination risk calculation."""

    def test_db_failure_increases_grounded_agent_risk(self):
        g = _build_db_tool_agent_graph()
        risks = calculate_cross_layer_hallucination_risk(g, "db")
        assert len(risks) >= 1
        agent_risk = [r for r in risks if r[0] == "agent"]
        assert len(agent_risk) == 1
        agent_id, probability, reason = agent_risk[0]
        assert probability > 0.0
        assert probability <= 1.0
        assert "grounding" in reason.lower() or "hallucinate" in reason.lower()

    def test_nonexistent_component_returns_empty(self):
        g = _build_db_tool_agent_graph()
        risks = calculate_cross_layer_hallucination_risk(g, "nonexistent")
        assert risks == []

    def test_agent_without_grounding_not_flagged_for_db_failure(self):
        """An agent that does NOT require grounding should not be in risk list
        for a DATABASE failure (only grounded agents are flagged)."""
        g = InfraGraph()
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
        ))
        g.add_component(Component(
            id="agent", name="Agent", type=ComponentType.AI_AGENT,
            parameters={"requires_grounding": 0, "hallucination_risk": 0.05},
        ))
        g.add_dependency(Dependency(source_id="agent", target_id="db", dependency_type="requires"))
        risks = calculate_cross_layer_hallucination_risk(g, "db")
        # Agent without grounding requirement should not appear
        agent_risks = [r for r in risks if r[0] == "agent"]
        assert len(agent_risks) == 0

    def test_external_api_failure_affects_dependent_agent(self):
        g = InfraGraph()
        g.add_component(Component(
            id="ext-api", name="Weather API", type=ComponentType.EXTERNAL_API,
        ))
        g.add_component(Component(
            id="agent", name="Weather Agent", type=ComponentType.AI_AGENT,
            parameters={"hallucination_risk": 0.1},
        ))
        g.add_dependency(Dependency(
            source_id="agent", target_id="ext-api", dependency_type="requires",
        ))
        risks = calculate_cross_layer_hallucination_risk(g, "ext-api")
        assert len(risks) == 1
        assert risks[0][0] == "agent"
        assert risks[0][1] > 0.0

    def test_cache_failure_affects_grounded_agent(self):
        g = InfraGraph()
        g.add_component(Component(
            id="cache", name="Redis Cache", type=ComponentType.CACHE,
        ))
        g.add_component(Component(
            id="agent", name="Cached Agent", type=ComponentType.AI_AGENT,
            parameters={"requires_grounding": 1, "hallucination_risk": 0.05},
        ))
        g.add_dependency(Dependency(
            source_id="agent", target_id="cache", dependency_type="requires",
        ))
        risks = calculate_cross_layer_hallucination_risk(g, "cache")
        assert len(risks) == 1
        assert risks[0][0] == "agent"

    def test_no_agent_dependents_returns_empty(self):
        g = InfraGraph()
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
        ))
        g.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        risks = calculate_cross_layer_hallucination_risk(g, "db")
        assert risks == []

    def test_transitive_dependency_detected(self):
        """DB -> Tool -> Agent: agent is transitively affected by DB failure."""
        g = _build_db_tool_agent_graph()
        risks = calculate_cross_layer_hallucination_risk(g, "db")
        # The agent should appear even though it's 2 hops away
        agent_ids = [r[0] for r in risks]
        assert "agent" in agent_ids
