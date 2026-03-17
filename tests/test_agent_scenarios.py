"""Tests for agent-specific chaos scenario generation."""

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.agent_scenarios import generate_agent_scenarios
from faultray.simulator.scenarios import FaultType


def _build_full_agent_graph() -> InfraGraph:
    """Build a graph with all agent component types + infra."""
    g = InfraGraph()
    g.add_component(Component(
        id="agent-1", name="Support Agent", type=ComponentType.AI_AGENT,
    ))
    g.add_component(Component(
        id="agent-2", name="Code Agent", type=ComponentType.AI_AGENT,
    ))
    g.add_component(Component(
        id="llm-1", name="Claude API", type=ComponentType.LLM_ENDPOINT,
    ))
    g.add_component(Component(
        id="llm-2", name="OpenAI API", type=ComponentType.LLM_ENDPOINT,
    ))
    g.add_component(Component(
        id="tool-1", name="Web Search", type=ComponentType.TOOL_SERVICE,
    ))
    g.add_component(Component(
        id="orch", name="Orchestrator", type=ComponentType.AGENT_ORCHESTRATOR,
    ))
    g.add_component(Component(
        id="db", name="Postgres", type=ComponentType.DATABASE,
    ))
    g.add_component(Component(
        id="cache", name="Redis", type=ComponentType.CACHE,
    ))
    # Dependencies
    g.add_dependency(Dependency(source_id="agent-1", target_id="llm-1", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="agent-2", target_id="llm-2", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="agent-1", target_id="tool-1", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="orch", target_id="agent-1", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="orch", target_id="agent-2", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="tool-1", target_id="db", dependency_type="requires"))
    return g


class TestGenerateAgentScenarios:
    """Test generate_agent_scenarios returns scenarios."""

    def test_returns_scenarios_for_agent_graph(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        assert len(scenarios) > 0

    def test_returns_empty_for_no_agents(self):
        g = InfraGraph()
        g.add_component(Component(id="db", name="DB", type=ComponentType.DATABASE))
        g.add_component(Component(id="app", name="App", type=ComponentType.APP_SERVER))
        scenarios = generate_agent_scenarios(g)
        assert scenarios == []

    def test_scenario_has_valid_structure(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        for s in scenarios:
            assert s.id != ""
            assert s.name != ""
            assert s.description != ""
            assert len(s.faults) >= 1


class TestHallucinationScenarios:
    """Test that hallucination scenarios are generated for AI_AGENT types."""

    def test_hallucination_scenarios_generated(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        halluc = [s for s in scenarios if "hallucination" in s.id.lower()]
        assert len(halluc) >= 1

    def test_hallucination_targets_ai_agent(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        halluc = [s for s in scenarios if "hallucination" in s.id.lower()]
        for s in halluc:
            for f in s.faults:
                assert f.fault_type == FaultType.HALLUCINATION
                # Target should be an AI_AGENT
                comp = g.get_component(f.target_component_id)
                assert comp is not None
                assert comp.type == ComponentType.AI_AGENT

    def test_context_overflow_scenarios_for_agents(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        ctx = [s for s in scenarios if "context_overflow" in s.id.lower() and "agent-" in s.id]
        assert len(ctx) >= 1

    def test_agent_loop_scenarios_for_agents(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        loops = [s for s in scenarios if "agent_loop" in s.id.lower() and "agent-" in s.id]
        assert len(loops) >= 1


class TestLLMEndpointScenarios:
    """Test scenarios for LLM_ENDPOINT components."""

    def test_rate_limit_scenarios_generated(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        rate_limit = [s for s in scenarios if "llm_rate_limit" in s.id.lower()]
        assert len(rate_limit) >= 1

    def test_token_exhaustion_scenarios_generated(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        token = [s for s in scenarios if "token_exhaustion" in s.id.lower()]
        assert len(token) >= 1

    def test_component_down_scenarios_for_llm(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        down = [s for s in scenarios if "component_down" in s.id.lower() and "llm-" in s.id]
        assert len(down) >= 1


class TestToolServiceScenarios:
    """Test scenarios for TOOL_SERVICE components."""

    def test_tool_failure_scenarios_generated(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        tool_fail = [s for s in scenarios if "tool_failure" in s.id.lower()]
        assert len(tool_fail) >= 1

    def test_tool_latency_spike_scenarios(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        latency = [s for s in scenarios if "latency_spike" in s.id.lower() and "tool-" in s.id]
        assert len(latency) >= 1


class TestOrchestratorScenarios:
    """Test scenarios for AGENT_ORCHESTRATOR components."""

    def test_orchestrator_loop_scenario(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        orch_loop = [s for s in scenarios if "orch-" in s.id and "agent_loop" in s.id]
        assert len(orch_loop) >= 1

    def test_orchestrator_down_scenario(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        orch_down = [s for s in scenarios if "orch-" in s.id and "component_down" in s.id]
        assert len(orch_down) >= 1

    def test_orchestrator_context_overflow_scenario(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        orch_ctx = [s for s in scenarios if "orch-" in s.id and "context_overflow" in s.id]
        assert len(orch_ctx) >= 1


class TestCrossLayerScenarios:
    """Test cross-layer scenarios for DB + Agent combinations."""

    def test_cross_layer_scenarios_generated_for_db(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        cross = [s for s in scenarios if "cross-layer" in s.id]
        assert len(cross) >= 1

    def test_cross_layer_targets_infra_component(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        cross = [s for s in scenarios if "cross-layer" in s.id]
        for s in cross:
            for f in s.faults:
                assert f.fault_type == FaultType.COMPONENT_DOWN
                comp = g.get_component(f.target_component_id)
                assert comp is not None
                assert comp.type in (ComponentType.DATABASE, ComponentType.CACHE, ComponentType.STORAGE)

    def test_cross_layer_for_cache(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        cache_cross = [s for s in scenarios if "cross-layer-cache" in s.id]
        assert len(cache_cross) >= 1

    def test_cross_layer_description_mentions_hallucination(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        cross = [s for s in scenarios if "cross-layer" in s.id]
        for s in cross:
            assert "hallucinate" in s.description.lower() or "hallucination" in s.description.lower()


class TestAllLLMDownScenario:
    """Test all-LLM-down scenario generation."""

    def test_all_llm_down_when_multiple_endpoints(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        all_llm = [s for s in scenarios if s.id == "all-llm-down"]
        assert len(all_llm) == 1

    def test_all_llm_down_faults_target_all_endpoints(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        all_llm = [s for s in scenarios if s.id == "all-llm-down"][0]
        target_ids = {f.target_component_id for f in all_llm.faults}
        assert "llm-1" in target_ids
        assert "llm-2" in target_ids
        assert len(all_llm.faults) == 2
        for f in all_llm.faults:
            assert f.fault_type == FaultType.COMPONENT_DOWN

    def test_no_all_llm_down_with_single_endpoint(self):
        g = InfraGraph()
        g.add_component(Component(
            id="agent", name="Agent", type=ComponentType.AI_AGENT,
        ))
        g.add_component(Component(
            id="llm", name="Single LLM", type=ComponentType.LLM_ENDPOINT,
        ))
        g.add_dependency(Dependency(
            source_id="agent", target_id="llm", dependency_type="requires",
        ))
        scenarios = generate_agent_scenarios(g)
        all_llm = [s for s in scenarios if s.id == "all-llm-down"]
        assert len(all_llm) == 0


class TestPromptInjectionScenarios:
    """Test prompt injection scenario generation."""

    def test_prompt_injection_scenarios_generated(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        injection = [s for s in scenarios if "prompt-injection" in s.id]
        # One per AI_AGENT
        ai_agents = [c for c in g.components.values() if c.type == ComponentType.AI_AGENT]
        assert len(injection) == len(ai_agents)

    def test_prompt_injection_fault_type(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        injection = [s for s in scenarios if "prompt-injection" in s.id]
        for s in injection:
            assert s.faults[0].fault_type == FaultType.PROMPT_INJECTION


class TestCascadeRateLimitScenarios:
    """Test cascading rate limit scenarios."""

    def test_cascade_rate_limit_for_llm_with_dependents(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        cascade = [s for s in scenarios if "cascade-ratelimit" in s.id]
        # llm-1 has dependent agent-1, llm-2 has dependent agent-2
        assert len(cascade) >= 1

    def test_cascade_rate_limit_fault_type(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        cascade = [s for s in scenarios if "cascade-ratelimit" in s.id]
        for s in cascade:
            assert s.faults[0].fault_type == FaultType.LLM_RATE_LIMIT


class TestScenarioCount:
    """Test that scenario counts are reasonable."""

    def test_full_graph_produces_many_scenarios(self):
        g = _build_full_agent_graph()
        scenarios = generate_agent_scenarios(g)
        # With 2 agents, 2 LLMs, 1 tool, 1 orch, 1 db, 1 cache:
        # - AI_AGENT: 3 faults x 2 = 6
        # - LLM: 3 faults x 2 = 6
        # - Tool: 3 faults x 1 = 3
        # - Orchestrator: 3 faults x 1 = 3
        # - Cross-layer: db + cache = 2
        # - All-LLM-down: 1
        # - Prompt injection: 2
        # - Cascade rate limit: >= 1
        assert len(scenarios) >= 20

    def test_minimal_graph_produces_few_scenarios(self):
        g = InfraGraph()
        g.add_component(Component(
            id="agent", name="Agent", type=ComponentType.AI_AGENT,
        ))
        scenarios = generate_agent_scenarios(g)
        # Just 3 single-fault scenarios + 1 prompt injection
        assert len(scenarios) >= 4
