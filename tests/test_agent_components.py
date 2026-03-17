"""Tests for AI agent component types and configuration models."""

from faultray.model.components import Component, ComponentType
from faultray.model.agent_components import (
    AgentConfig,
    AgentOrchestratorConfig,
    LLMEndpointConfig,
    ToolServiceConfig,
)
from faultray.simulator.scenarios import FaultType


class TestAgentComponentTypes:
    """Verify that agent-specific ComponentType values exist."""

    def test_ai_agent_type_exists(self):
        assert ComponentType.AI_AGENT == "ai_agent"

    def test_llm_endpoint_type_exists(self):
        assert ComponentType.LLM_ENDPOINT == "llm_endpoint"

    def test_tool_service_type_exists(self):
        assert ComponentType.TOOL_SERVICE == "tool_service"

    def test_agent_orchestrator_type_exists(self):
        assert ComponentType.AGENT_ORCHESTRATOR == "agent_orchestrator"

    def test_agent_types_are_distinct(self):
        agent_types = {
            ComponentType.AI_AGENT,
            ComponentType.LLM_ENDPOINT,
            ComponentType.TOOL_SERVICE,
            ComponentType.AGENT_ORCHESTRATOR,
        }
        assert len(agent_types) == 4

    def test_agent_component_can_be_created(self):
        comp = Component(
            id="agent-1", name="My Agent", type=ComponentType.AI_AGENT,
        )
        assert comp.id == "agent-1"
        assert comp.type == ComponentType.AI_AGENT

    def test_llm_endpoint_component_can_be_created(self):
        comp = Component(
            id="llm-1", name="Claude API", type=ComponentType.LLM_ENDPOINT,
        )
        assert comp.type == ComponentType.LLM_ENDPOINT

    def test_tool_service_component_can_be_created(self):
        comp = Component(
            id="tool-1", name="Web Search", type=ComponentType.TOOL_SERVICE,
        )
        assert comp.type == ComponentType.TOOL_SERVICE

    def test_orchestrator_component_can_be_created(self):
        comp = Component(
            id="orch-1", name="Orchestrator", type=ComponentType.AGENT_ORCHESTRATOR,
        )
        assert comp.type == ComponentType.AGENT_ORCHESTRATOR


class TestAgentFaultTypes:
    """Verify that agent-specific FaultType values exist."""

    def test_hallucination_fault_exists(self):
        assert FaultType.HALLUCINATION == "hallucination"

    def test_context_overflow_fault_exists(self):
        assert FaultType.CONTEXT_OVERFLOW == "context_overflow"

    def test_llm_rate_limit_fault_exists(self):
        assert FaultType.LLM_RATE_LIMIT == "llm_rate_limit"

    def test_token_exhaustion_fault_exists(self):
        assert FaultType.TOKEN_EXHAUSTION == "token_exhaustion"

    def test_tool_failure_fault_exists(self):
        assert FaultType.TOOL_FAILURE == "tool_failure"

    def test_agent_loop_fault_exists(self):
        assert FaultType.AGENT_LOOP == "agent_loop"

    def test_prompt_injection_fault_exists(self):
        assert FaultType.PROMPT_INJECTION == "prompt_injection"

    def test_all_agent_faults_are_distinct(self):
        agent_faults = {
            FaultType.HALLUCINATION,
            FaultType.CONTEXT_OVERFLOW,
            FaultType.LLM_RATE_LIMIT,
            FaultType.TOKEN_EXHAUSTION,
            FaultType.TOOL_FAILURE,
            FaultType.AGENT_LOOP,
            FaultType.PROMPT_INJECTION,
        }
        assert len(agent_faults) == 7


class TestAgentConfig:
    """Test AgentConfig model instantiation and defaults."""

    def test_default_instantiation(self):
        config = AgentConfig()
        assert config.framework == "custom"
        assert config.model_id == "claude-sonnet-4-20250514"
        assert config.max_context_tokens == 200000
        assert config.temperature == 0.7
        assert config.max_output_tokens == 4096
        assert config.concurrent_requests == 10
        assert config.retry_on_failure is True
        assert config.max_retries == 3
        assert config.fallback_model_id is None
        assert config.tools == []
        assert config.hallucination_risk == 0.05
        assert config.requires_grounding is False

    def test_custom_values(self):
        config = AgentConfig(
            framework="langchain",
            model_id="gpt-4o",
            max_context_tokens=128000,
            temperature=0.0,
            hallucination_risk=0.1,
            requires_grounding=True,
            tools=["web_search", "calculator"],
            fallback_model_id="gpt-4o-mini",
        )
        assert config.framework == "langchain"
        assert config.model_id == "gpt-4o"
        assert config.max_context_tokens == 128000
        assert config.temperature == 0.0
        assert config.hallucination_risk == 0.1
        assert config.requires_grounding is True
        assert len(config.tools) == 2
        assert config.fallback_model_id == "gpt-4o-mini"


class TestLLMEndpointConfig:
    """Test LLMEndpointConfig model instantiation and defaults."""

    def test_default_instantiation(self):
        config = LLMEndpointConfig()
        assert config.provider == "anthropic"
        assert config.model_id == "claude-sonnet-4-20250514"
        assert config.rate_limit_rpm == 1000
        assert config.rate_limit_tpm == 100000
        assert config.avg_latency_ms == 500.0
        assert config.p99_latency_ms == 3000.0
        assert config.availability_sla == 99.9
        assert config.cost_per_1k_input_tokens == 0.003
        assert config.cost_per_1k_output_tokens == 0.015
        assert config.supports_streaming is True
        assert config.context_window == 200000

    def test_custom_provider(self):
        config = LLMEndpointConfig(
            provider="openai",
            model_id="gpt-4o",
            rate_limit_rpm=500,
            context_window=128000,
        )
        assert config.provider == "openai"
        assert config.rate_limit_rpm == 500
        assert config.context_window == 128000


class TestToolServiceConfig:
    """Test ToolServiceConfig model instantiation and defaults."""

    def test_default_instantiation(self):
        config = ToolServiceConfig()
        assert config.tool_type == "api"
        assert config.idempotent is False
        assert config.side_effects is True
        assert config.avg_latency_ms == 200.0
        assert config.failure_rate == 0.01
        assert config.rate_limit_rpm is None

    def test_idempotent_read_only_tool(self):
        config = ToolServiceConfig(
            tool_type="database_query",
            idempotent=True,
            side_effects=False,
            failure_rate=0.001,
        )
        assert config.idempotent is True
        assert config.side_effects is False

    def test_mcp_server_tool(self):
        config = ToolServiceConfig(
            tool_type="mcp_server",
            rate_limit_rpm=60,
        )
        assert config.tool_type == "mcp_server"
        assert config.rate_limit_rpm == 60


class TestAgentOrchestratorConfig:
    """Test AgentOrchestratorConfig model instantiation and defaults."""

    def test_default_instantiation(self):
        config = AgentOrchestratorConfig()
        assert config.pattern == "sequential"
        assert config.max_agents == 10
        assert config.timeout_seconds == 300.0
        assert config.max_iterations == 50
        assert config.circuit_breaker_on_hallucination is True

    def test_parallel_orchestrator(self):
        config = AgentOrchestratorConfig(
            pattern="parallel",
            max_agents=5,
            timeout_seconds=120.0,
            max_iterations=20,
        )
        assert config.pattern == "parallel"
        assert config.max_agents == 5
        assert config.timeout_seconds == 120.0
        assert config.max_iterations == 20

    def test_hierarchical_orchestrator_without_circuit_breaker(self):
        config = AgentOrchestratorConfig(
            pattern="hierarchical",
            circuit_breaker_on_hallucination=False,
        )
        assert config.pattern == "hierarchical"
        assert config.circuit_breaker_on_hallucination is False
