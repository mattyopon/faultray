"""Tests for agent-specific cascade failure logic."""

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.agent_cascade import (
    AGENT_COMPONENT_TYPES,
    AGENT_FAULT_TYPES,
    DataSourceState,
    apply_agent_direct_effect,
    calculate_agent_cascade_probability,
    calculate_agent_likelihood,
    calculate_chain_hallucination_probability,
    calculate_cross_layer_hallucination_risk,
    calculate_hallucination_probability,
    is_agent_component,
    is_agent_fault,
    propagate_agent_to_agent_cascade,
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

    def test_confidence_miscalibration_effect(self):
        comp = _agent(name="Overconfident Agent")
        effect = apply_agent_direct_effect(comp, "confidence_miscalibration")
        assert effect is not None
        assert effect.health == HealthStatus.DEGRADED
        assert "miscalibrated" in effect.reason

    def test_cot_collapse_effect(self):
        comp = _agent(name="Reasoning Agent")
        effect = apply_agent_direct_effect(comp, "cot_collapse")
        assert effect is not None
        assert effect.health == HealthStatus.DEGRADED
        assert "chain-of-thought" in effect.reason

    def test_output_amplification_effect(self):
        comp = _agent(name="Downstream Agent")
        effect = apply_agent_direct_effect(comp, "output_amplification")
        assert effect is not None
        assert effect.health == HealthStatus.DEGRADED
        assert "amplifying" in effect.reason

    def test_grounding_staleness_effect(self):
        comp = _agent(name="Stale Agent")
        effect = apply_agent_direct_effect(comp, "grounding_staleness")
        assert effect is not None
        assert effect.health == HealthStatus.DEGRADED
        assert "stale" in effect.reason
        assert effect.estimated_time_seconds == 300

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

    def test_confidence_miscalibration_default_temperature(self):
        comp = _agent()
        likelihood = calculate_agent_likelihood(comp, "confidence_miscalibration")
        assert likelihood is not None
        assert 0.2 <= likelihood <= 1.0

    def test_confidence_miscalibration_high_temperature(self):
        comp_high = _agent(temperature=1.5)
        comp_low = _agent(temperature=0.1)
        l_high = calculate_agent_likelihood(comp_high, "confidence_miscalibration")
        l_low = calculate_agent_likelihood(comp_low, "confidence_miscalibration")
        assert l_high is not None and l_low is not None
        assert l_high > l_low

    def test_cot_collapse_small_context(self):
        comp = _agent(max_context_tokens=16000)
        likelihood = calculate_agent_likelihood(comp, "cot_collapse")
        assert likelihood == 0.5

    def test_cot_collapse_large_context(self):
        comp = _agent(max_context_tokens=200000)
        likelihood = calculate_agent_likelihood(comp, "cot_collapse")
        assert likelihood == 0.3

    def test_output_amplification_with_agent_input(self):
        comp = _agent(receives_agent_output=1)
        likelihood = calculate_agent_likelihood(comp, "output_amplification")
        assert likelihood == 0.6

    def test_output_amplification_without_agent_input(self):
        comp = _agent(receives_agent_output=0)
        likelihood = calculate_agent_likelihood(comp, "output_amplification")
        assert likelihood == 0.2

    def test_grounding_staleness_long_ttl(self):
        comp = _agent(grounding_cache_ttl_seconds=7200)
        likelihood = calculate_agent_likelihood(comp, "grounding_staleness")
        assert likelihood == 0.7

    def test_grounding_staleness_short_ttl(self):
        comp = _agent(grounding_cache_ttl_seconds=60)
        likelihood = calculate_agent_likelihood(comp, "grounding_staleness")
        assert likelihood == 0.3

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

    def test_confidence_miscalibration_is_agent_fault(self):
        assert is_agent_fault("confidence_miscalibration")

    def test_cot_collapse_is_agent_fault(self):
        assert is_agent_fault("cot_collapse")

    def test_output_amplification_is_agent_fault(self):
        assert is_agent_fault("output_amplification")

    def test_grounding_staleness_is_agent_fault(self):
        assert is_agent_fault("grounding_staleness")

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

    def test_agent_fault_types_has_eleven_entries(self):
        assert len(AGENT_FAULT_TYPES) == 11

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


class TestCalculateHallucinationProbability:
    """Test the formal probabilistic model H(a, D, I)."""

    def test_no_data_sources_returns_base_rate(self):
        agent = _agent(hallucination_risk=0.05)
        h = calculate_hallucination_probability(agent)
        assert h == 0.05

    def test_all_healthy_returns_base_rate(self):
        agent = _agent(hallucination_risk=0.05)
        sources = [
            DataSourceState("db", 0.8, HealthStatus.HEALTHY),
            DataSourceState("cache", 0.5, HealthStatus.HEALTHY),
        ]
        h = calculate_hallucination_probability(agent, data_sources=sources)
        assert h == 0.05

    def test_single_down_source_increases_probability(self):
        agent = _agent(hallucination_risk=0.05)
        sources = [DataSourceState("db", 1.0, HealthStatus.DOWN)]
        h = calculate_hallucination_probability(agent, data_sources=sources)
        # h_d = 0.05 + (1 - 0.05) * 1.0 = 1.0
        assert h == 1.0

    def test_single_down_partial_weight(self):
        agent = _agent(hallucination_risk=0.1)
        sources = [DataSourceState("db", 0.5, HealthStatus.DOWN)]
        h = calculate_hallucination_probability(agent, data_sources=sources)
        # h_d = 0.1 + (1 - 0.1) * 0.5 = 0.1 + 0.45 = 0.55
        assert abs(h - 0.55) < 0.001

    def test_degraded_source_partial_increase(self):
        agent = _agent(hallucination_risk=0.1)
        sources = [DataSourceState("db", 1.0, HealthStatus.DEGRADED)]
        h = calculate_hallucination_probability(agent, data_sources=sources)
        # h_d = 0.1 + (1 - 0.1) * 1.0 * 0.5 = 0.1 + 0.45 = 0.55
        assert abs(h - 0.55) < 0.001

    def test_overloaded_source(self):
        agent = _agent(hallucination_risk=0.1)
        sources = [DataSourceState("api", 1.0, HealthStatus.OVERLOADED)]
        h = calculate_hallucination_probability(agent, data_sources=sources)
        # h_d = 0.1 + (1 - 0.1) * 1.0 * 0.3 = 0.1 + 0.27 = 0.37
        assert abs(h - 0.37) < 0.001

    def test_multiple_down_sources_compound(self):
        agent = _agent(hallucination_risk=0.0)
        sources = [
            DataSourceState("db", 0.5, HealthStatus.DOWN),
            DataSourceState("cache", 0.5, HealthStatus.DOWN),
        ]
        h = calculate_hallucination_probability(agent, data_sources=sources)
        # h_d1 = 0 + 1.0 * 0.5 = 0.5, h_d2 = 0.5
        # H = 1 - (1-0.5)*(1-0.5) = 1 - 0.25 = 0.75
        assert abs(h - 0.75) < 0.001

    def test_monotonicity_more_failures_higher_probability(self):
        agent = _agent(hallucination_risk=0.05)
        sources_one = [DataSourceState("db", 0.5, HealthStatus.DOWN)]
        sources_two = [
            DataSourceState("db", 0.5, HealthStatus.DOWN),
            DataSourceState("cache", 0.5, HealthStatus.DOWN),
        ]
        h_one = calculate_hallucination_probability(agent, data_sources=sources_one)
        h_two = calculate_hallucination_probability(agent, data_sources=sources_two)
        assert h_two > h_one

    def test_bounded_zero_to_one(self):
        agent = _agent(hallucination_risk=0.0)
        sources = [DataSourceState("db", 0.0, HealthStatus.DOWN)]
        h = calculate_hallucination_probability(agent, data_sources=sources)
        assert 0.0 <= h <= 1.0

    def test_infra_state_dict_mode(self):
        agent = _agent(
            hallucination_risk=0.1,
            data_source_weights="db:0.8,cache:0.5",
        )
        infra = {"db": HealthStatus.DOWN, "cache": HealthStatus.HEALTHY}
        h = calculate_hallucination_probability(agent, infra_state=infra)
        # Only db is DOWN: h_d = 0.1 + 0.9 * 0.8 = 0.82
        assert h > 0.1
        assert h <= 1.0


class TestAgentCascadeProbability:
    """Test agent-to-agent cascade probability calculation."""

    def test_no_source_hallucination_no_increase(self):
        h = calculate_agent_cascade_probability(0.0, 0.1)
        assert abs(h - 0.1) < 0.001

    def test_source_hallucination_increases_target(self):
        h = calculate_agent_cascade_probability(0.5, 0.1)
        # H = 1 - (1-0.1)*(1-0.5) = 1 - 0.9*0.5 = 1 - 0.45 = 0.55
        assert abs(h - 0.55) < 0.001

    def test_full_amplification(self):
        h = calculate_agent_cascade_probability(1.0, 0.0, amplification_factor=1.0)
        assert abs(h - 1.0) < 0.001

    def test_zero_amplification_no_propagation(self):
        h = calculate_agent_cascade_probability(1.0, 0.1, amplification_factor=0.0)
        assert abs(h - 0.1) < 0.001

    def test_partial_amplification(self):
        h = calculate_agent_cascade_probability(0.5, 0.1, amplification_factor=0.5)
        # inherited = 0.5 * 0.5 = 0.25
        # H = 1 - (1-0.1)*(1-0.25) = 1 - 0.9*0.75 = 1 - 0.675 = 0.325
        assert abs(h - 0.325) < 0.001


class TestChainHallucinationProbability:
    """Test compound chain probability."""

    def test_empty_chain(self):
        assert calculate_chain_hallucination_probability([]) == 0.0

    def test_single_agent(self):
        h = calculate_chain_hallucination_probability([0.3])
        assert abs(h - 0.3) < 0.001

    def test_two_agents(self):
        h = calculate_chain_hallucination_probability([0.3, 0.3])
        # H = 1 - (1-0.3)*(1-0.3) = 1 - 0.49 = 0.51
        assert abs(h - 0.51) < 0.001

    def test_chain_always_increases(self):
        h2 = calculate_chain_hallucination_probability([0.2, 0.2])
        h3 = calculate_chain_hallucination_probability([0.2, 0.2, 0.2])
        assert h3 > h2

    def test_chain_bounded_by_one(self):
        h = calculate_chain_hallucination_probability([0.9, 0.9, 0.9, 0.9])
        assert h <= 1.0


class TestPropagateAgentToAgentCascade:
    """Test agent-to-agent cascade propagation through the graph."""

    def test_single_hop_cascade(self):
        g = InfraGraph()
        g.add_component(Component(
            id="agent-a", name="Agent A", type=ComponentType.AI_AGENT,
            parameters={"hallucination_risk": 0.1},
        ))
        g.add_component(Component(
            id="agent-b", name="Agent B", type=ComponentType.AI_AGENT,
            parameters={"hallucination_risk": 0.05},
        ))
        g.add_dependency(Dependency(
            source_id="agent-b", target_id="agent-a", dependency_type="requires",
        ))
        results = propagate_agent_to_agent_cascade(g, "agent-a", 0.8)
        assert len(results) == 1
        agent_id, h_eff, reason = results[0]
        assert agent_id == "agent-b"
        assert h_eff > 0.05  # Must be higher than base
        assert "upstream" in reason.lower()

    def test_multi_hop_cascade(self):
        g = InfraGraph()
        g.add_component(Component(
            id="a1", name="Agent 1", type=ComponentType.AI_AGENT,
            parameters={"hallucination_risk": 0.1},
        ))
        g.add_component(Component(
            id="a2", name="Agent 2", type=ComponentType.AI_AGENT,
            parameters={"hallucination_risk": 0.1},
        ))
        g.add_component(Component(
            id="a3", name="Agent 3", type=ComponentType.AI_AGENT,
            parameters={"hallucination_risk": 0.1},
        ))
        g.add_dependency(Dependency(source_id="a2", target_id="a1", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="a3", target_id="a2", dependency_type="requires"))
        results = propagate_agent_to_agent_cascade(g, "a1", 0.5)
        assert len(results) == 2
        ids = [r[0] for r in results]
        assert "a2" in ids
        assert "a3" in ids
        # a3 should have higher risk than a2 (compound effect)
        h_a2 = next(r[1] for r in results if r[0] == "a2")
        h_a3 = next(r[1] for r in results if r[0] == "a3")
        assert h_a3 >= h_a2

    def test_nonexistent_source_returns_empty(self):
        g = InfraGraph()
        results = propagate_agent_to_agent_cascade(g, "nonexistent", 0.5)
        assert results == []

    def test_no_downstream_agents_returns_empty(self):
        g = InfraGraph()
        g.add_component(Component(
            id="agent-a", name="Agent A", type=ComponentType.AI_AGENT,
            parameters={"hallucination_risk": 0.1},
        ))
        results = propagate_agent_to_agent_cascade(g, "agent-a", 0.5)
        assert results == []

    def test_skips_non_agent_dependents(self):
        g = InfraGraph()
        g.add_component(Component(
            id="agent-a", name="Agent A", type=ComponentType.AI_AGENT,
            parameters={"hallucination_risk": 0.1},
        ))
        g.add_component(Component(
            id="app", name="App Server", type=ComponentType.APP_SERVER,
        ))
        g.add_dependency(Dependency(source_id="app", target_id="agent-a", dependency_type="requires"))
        results = propagate_agent_to_agent_cascade(g, "agent-a", 0.5)
        assert results == []

    def test_custom_amplification_factor(self):
        g = InfraGraph()
        g.add_component(Component(
            id="a1", name="Agent 1", type=ComponentType.AI_AGENT,
            parameters={"hallucination_risk": 0.1},
        ))
        g.add_component(Component(
            id="a2", name="Agent 2", type=ComponentType.AI_AGENT,
            parameters={"hallucination_risk": 0.1, "amplification_factor": 0.3},
        ))
        g.add_dependency(Dependency(source_id="a2", target_id="a1", dependency_type="requires"))
        results = propagate_agent_to_agent_cascade(g, "a1", 0.8)
        assert len(results) == 1
        # With low amplification, effective H should be lower than full amplification
        h_partial = results[0][1]
        # Compare with full amplification
        g2 = InfraGraph()
        g2.add_component(Component(
            id="a1", name="Agent 1", type=ComponentType.AI_AGENT,
            parameters={"hallucination_risk": 0.1},
        ))
        g2.add_component(Component(
            id="a2", name="Agent 2", type=ComponentType.AI_AGENT,
            parameters={"hallucination_risk": 0.1, "amplification_factor": 1.0},
        ))
        g2.add_dependency(Dependency(source_id="a2", target_id="a1", dependency_type="requires"))
        results2 = propagate_agent_to_agent_cascade(g2, "a1", 0.8)
        h_full = results2[0][1]
        assert h_partial < h_full
