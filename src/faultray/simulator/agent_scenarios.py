# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Agent-specific chaos scenario generation."""

from __future__ import annotations

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph
from faultray.simulator.scenarios import Scenario, Fault, FaultType


AGENT_TYPES = {
    ComponentType.AI_AGENT,
    ComponentType.LLM_ENDPOINT,
    ComponentType.TOOL_SERVICE,
    ComponentType.AGENT_ORCHESTRATOR,
}


def generate_agent_scenarios(graph: InfraGraph) -> list[Scenario]:
    """Generate agent-specific chaos scenarios for all agent components."""
    scenarios: list[Scenario] = []

    agent_components = [
        c for c in graph.components.values()
        if c.type in AGENT_TYPES
    ]

    if not agent_components:
        return scenarios

    # 1. Single agent failures (each agent fault type x each agent)
    for comp in agent_components:
        if comp.type == ComponentType.AI_AGENT:
            for ft in [FaultType.HALLUCINATION, FaultType.CONTEXT_OVERFLOW, FaultType.AGENT_LOOP]:
                scenarios.append(Scenario(
                    id=f"agent-{ft.value}-{comp.id}",
                    name=f"{ft.value.replace('_', ' ').title()} on {comp.name}",
                    description=f"Simulate {ft.value} failure on agent {comp.name}",
                    faults=[Fault(target_component_id=comp.id, fault_type=ft)],
                ))

        if comp.type == ComponentType.LLM_ENDPOINT:
            for ft in [FaultType.LLM_RATE_LIMIT, FaultType.TOKEN_EXHAUSTION, FaultType.COMPONENT_DOWN]:
                scenarios.append(Scenario(
                    id=f"llm-{ft.value}-{comp.id}",
                    name=f"{ft.value.replace('_', ' ').title()} on {comp.name}",
                    description=f"Simulate {ft.value} on LLM endpoint {comp.name}",
                    faults=[Fault(target_component_id=comp.id, fault_type=ft)],
                ))

        if comp.type == ComponentType.TOOL_SERVICE:
            for ft in [FaultType.TOOL_FAILURE, FaultType.COMPONENT_DOWN, FaultType.LATENCY_SPIKE]:
                scenarios.append(Scenario(
                    id=f"tool-{ft.value}-{comp.id}",
                    name=f"{ft.value.replace('_', ' ').title()} on {comp.name}",
                    description=f"Simulate {ft.value} on tool {comp.name}",
                    faults=[Fault(target_component_id=comp.id, fault_type=ft)],
                ))

        if comp.type == ComponentType.AGENT_ORCHESTRATOR:
            for ft in [FaultType.AGENT_LOOP, FaultType.COMPONENT_DOWN, FaultType.CONTEXT_OVERFLOW]:
                scenarios.append(Scenario(
                    id=f"orch-{ft.value}-{comp.id}",
                    name=f"{ft.value.replace('_', ' ').title()} on {comp.name}",
                    description=f"Simulate {ft.value} on orchestrator {comp.name}",
                    faults=[Fault(target_component_id=comp.id, fault_type=ft)],
                ))

    # 2. Cross-layer scenarios: Infra failure -> Agent hallucination
    infra_components = [
        c for c in graph.components.values()
        if c.type in (ComponentType.DATABASE, ComponentType.CACHE, ComponentType.STORAGE)
    ]
    for infra in infra_components:
        scenarios.append(Scenario(
            id=f"cross-layer-{infra.id}-down",
            name=f"Cross-layer: {infra.name} down -> Agent hallucination risk",
            description=(
                f"Infrastructure failure on {infra.name} may cause dependent agents "
                f"to lose grounding data and hallucinate"
            ),
            faults=[Fault(target_component_id=infra.id, fault_type=FaultType.COMPONENT_DOWN)],
        ))

    # 3. All LLM endpoints down (total AI outage)
    llm_endpoints = [c for c in agent_components if c.type == ComponentType.LLM_ENDPOINT]
    if len(llm_endpoints) >= 2:
        scenarios.append(Scenario(
            id="all-llm-down",
            name="All LLM Endpoints Down",
            description="All LLM API endpoints are unavailable simultaneously",
            faults=[
                Fault(target_component_id=c.id, fault_type=FaultType.COMPONENT_DOWN)
                for c in llm_endpoints
            ],
        ))

    # 4. Prompt injection on all agents
    ai_agents = [c for c in agent_components if c.type == ComponentType.AI_AGENT]
    for agent in ai_agents:
        scenarios.append(Scenario(
            id=f"prompt-injection-{agent.id}",
            name=f"Prompt Injection on {agent.name}",
            description=f"External input contains prompt injection targeting {agent.name}",
            faults=[Fault(target_component_id=agent.id, fault_type=FaultType.PROMPT_INJECTION)],
        ))

    # 5. Cascading: LLM rate limit -> agent degradation -> orchestrator failure
    for llm in llm_endpoints:
        dependent_agents = [
            a for a in ai_agents
            if llm.id in [dep.id for dep in graph.get_dependencies(a.id)]
        ]
        if dependent_agents:
            scenarios.append(Scenario(
                id=f"cascade-ratelimit-{llm.id}",
                name=f"Rate Limit Cascade from {llm.name}",
                description=f"Rate limiting on {llm.name} cascades through dependent agents",
                faults=[Fault(target_component_id=llm.id, fault_type=FaultType.LLM_RATE_LIMIT)],
            ))

    return scenarios
