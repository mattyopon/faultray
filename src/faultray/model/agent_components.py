# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""AI Agent component models for resilience simulation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """AI Agent configuration for resilience simulation."""

    framework: str = "custom"  # langchain, crewai, autogen, claude_agent_sdk, custom
    model_id: str = "claude-sonnet-4-20250514"
    max_context_tokens: int = 200000
    temperature: float = 0.7
    max_output_tokens: int = 4096
    concurrent_requests: int = 10
    retry_on_failure: bool = True
    max_retries: int = 3
    fallback_model_id: str | None = None  # Fallback LLM if primary fails
    tools: list[str] = Field(default_factory=list)  # Tool IDs this agent can use
    hallucination_risk: float = 0.05  # Base hallucination probability (0.0-1.0)
    requires_grounding: bool = False  # If True, agent must have data source access


class LLMEndpointConfig(BaseModel):
    """LLM API endpoint configuration."""

    provider: str = "anthropic"  # anthropic, openai, google, azure_openai, self_hosted
    model_id: str = "claude-sonnet-4-20250514"
    rate_limit_rpm: int = 1000  # Requests per minute
    rate_limit_tpm: int = 100000  # Tokens per minute
    avg_latency_ms: float = 500.0
    p99_latency_ms: float = 3000.0
    availability_sla: float = 99.9  # Provider's SLA percentage
    cost_per_1k_input_tokens: float = 0.003
    cost_per_1k_output_tokens: float = 0.015
    supports_streaming: bool = True
    context_window: int = 200000


class ToolServiceConfig(BaseModel):
    """Tool/MCP service that agents use."""

    tool_type: str = "api"  # api, database_query, web_search, file_operation, mcp_server
    idempotent: bool = False  # Safe to retry?
    side_effects: bool = True  # Does it modify external state?
    avg_latency_ms: float = 200.0
    failure_rate: float = 0.01  # Historical failure rate
    rate_limit_rpm: int | None = None


class AgentOrchestratorConfig(BaseModel):
    """Multi-agent orchestration configuration."""

    pattern: str = "sequential"  # sequential, parallel, hierarchical, consensus
    max_agents: int = 10
    timeout_seconds: float = 300.0
    max_iterations: int = 50  # Max loops for iterative agent patterns
    circuit_breaker_on_hallucination: bool = True
