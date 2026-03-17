"""MANAGE engine — Agent runtime monitoring and anomaly detection.

Connects FaultRay simulation results to runtime metrics,
enabling predictive fault detection for AI agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class PredictedFault(str, Enum):
    HALLUCINATION_RISK = "hallucination_risk"
    CONTEXT_OVERFLOW_RISK = "context_overflow_risk"
    RATE_LIMIT_APPROACHING = "rate_limit_approaching"
    CASCADING_FAILURE_RISK = "cascading_failure_risk"
    TOOL_DEGRADATION = "tool_degradation"


@dataclass
class MonitoringRule:
    """A monitoring rule derived from simulation results."""
    rule_id: str
    name: str
    description: str
    component_id: str
    metric: str
    threshold: float
    operator: str  # "gt", "lt", "gte", "lte"
    predicted_fault: PredictedFault
    severity: AlertSeverity
    recommended_action: str


@dataclass
class MonitoringPlan:
    """Complete monitoring plan for agent infrastructure."""
    rules: list[MonitoringRule] = field(default_factory=list)
    total_components_monitored: int = 0
    coverage_percent: float = 0.0


class AgentMonitorEngine:
    """Generates monitoring rules from simulation analysis.

    This engine analyzes the infrastructure graph and generates
    monitoring rules that can detect pre-failure conditions
    identified by FaultRay simulations.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def generate_monitoring_plan(self) -> MonitoringPlan:
        """Generate a complete monitoring plan for all agent components."""
        rules: list[MonitoringRule] = []
        monitored = set()

        for comp in self.graph.components.values():
            comp_rules = self._rules_for_component(comp)
            rules.extend(comp_rules)
            if comp_rules:
                monitored.add(comp.id)

        total = len(self.graph.components)

        return MonitoringPlan(
            rules=rules,
            total_components_monitored=len(monitored),
            coverage_percent=round(len(monitored) / max(total, 1) * 100, 1),
        )

    def _rules_for_component(self, comp: Component) -> list[MonitoringRule]:
        """Generate monitoring rules for a single component."""
        rules = []
        params = comp.parameters or {}

        if comp.type == ComponentType.AI_AGENT:
            rules.extend(self._agent_rules(comp, params))
        elif comp.type == ComponentType.LLM_ENDPOINT:
            rules.extend(self._llm_rules(comp, params))
        elif comp.type == ComponentType.TOOL_SERVICE:
            rules.extend(self._tool_rules(comp, params))
        elif comp.type == ComponentType.AGENT_ORCHESTRATOR:
            rules.extend(self._orchestrator_rules(comp, params))

        # Cross-layer: infra components that agents depend on
        if comp.type in (ComponentType.DATABASE, ComponentType.CACHE):
            dependent_agents = [
                c for c in self.graph.components.values()
                if c.type == ComponentType.AI_AGENT
                and comp.id in [d.id for d in self.graph.get_dependencies(c.id)]
            ]
            if dependent_agents:
                rules.extend(self._infra_agent_rules(comp, dependent_agents))

        return rules

    def _agent_rules(self, comp: Component, params: dict) -> list[MonitoringRule]:
        max_tokens = int(params.get("max_context_tokens", 200000))
        return [
            MonitoringRule(
                rule_id=f"{comp.id}-context-usage",
                name=f"Context window usage on {comp.name}",
                description="Alert when context window is nearing capacity",
                component_id=comp.id,
                metric="context_tokens_used",
                threshold=max_tokens * 0.8,
                operator="gt",
                predicted_fault=PredictedFault.CONTEXT_OVERFLOW_RISK,
                severity=AlertSeverity.WARNING,
                recommended_action="Implement context summarization or reduce input size",
            ),
            MonitoringRule(
                rule_id=f"{comp.id}-hallucination-rate",
                name=f"Hallucination rate on {comp.name}",
                description="Alert when hallucination detection rate exceeds baseline",
                component_id=comp.id,
                metric="hallucination_detected_rate",
                threshold=float(params.get("hallucination_risk", 0.05)) * 2,
                operator="gt",
                predicted_fault=PredictedFault.HALLUCINATION_RISK,
                severity=AlertSeverity.CRITICAL,
                recommended_action="Check grounding data sources. Consider switching to fallback model.",
            ),
        ]

    def _llm_rules(self, comp: Component, params: dict) -> list[MonitoringRule]:
        rpm_limit = int(params.get("rate_limit_rpm", 1000))
        return [
            MonitoringRule(
                rule_id=f"{comp.id}-rate-limit",
                name=f"Rate limit approaching on {comp.name}",
                description="Alert when request rate nears provider limit",
                component_id=comp.id,
                metric="requests_per_minute",
                threshold=rpm_limit * 0.8,
                operator="gt",
                predicted_fault=PredictedFault.RATE_LIMIT_APPROACHING,
                severity=AlertSeverity.WARNING,
                recommended_action="Enable request queuing or switch to fallback endpoint",
            ),
            MonitoringRule(
                rule_id=f"{comp.id}-latency",
                name=f"Latency spike on {comp.name}",
                description="Alert when LLM response latency exceeds P99",
                component_id=comp.id,
                metric="response_latency_ms",
                threshold=float(params.get("p99_latency_ms", 3000)),
                operator="gt",
                predicted_fault=PredictedFault.CASCADING_FAILURE_RISK,
                severity=AlertSeverity.CRITICAL,
                recommended_action="LLM provider may be degraded. Activate fallback endpoint.",
            ),
        ]

    def _tool_rules(self, comp: Component, params: dict) -> list[MonitoringRule]:
        return [
            MonitoringRule(
                rule_id=f"{comp.id}-error-rate",
                name=f"Error rate on {comp.name}",
                description="Alert when tool error rate exceeds baseline",
                component_id=comp.id,
                metric="error_rate",
                threshold=float(params.get("failure_rate", 0.01)) * 3,
                operator="gt",
                predicted_fault=PredictedFault.TOOL_DEGRADATION,
                severity=AlertSeverity.WARNING,
                recommended_action="Tool service degrading. Agents may fall back to LLM-only responses.",
            ),
        ]

    def _orchestrator_rules(self, comp: Component, params: dict) -> list[MonitoringRule]:
        max_iter = int(params.get("max_iterations", 50))
        return [
            MonitoringRule(
                rule_id=f"{comp.id}-iteration-count",
                name=f"Iteration count on {comp.name}",
                description="Alert when orchestrator approaches iteration limit",
                component_id=comp.id,
                metric="current_iteration",
                threshold=max_iter * 0.8,
                operator="gt",
                predicted_fault=PredictedFault.CASCADING_FAILURE_RISK,
                severity=AlertSeverity.WARNING,
                recommended_action="Agent may be in a loop. Check for circular task delegation.",
            ),
        ]

    def _infra_agent_rules(
        self, infra: Component, dependent_agents: list[Component]
    ) -> list[MonitoringRule]:
        agent_names = ", ".join(a.name for a in dependent_agents)
        return [
            MonitoringRule(
                rule_id=f"{infra.id}-agent-grounding-risk",
                name=f"Cross-layer: {infra.name} degradation → agent hallucination risk",
                description=(
                    f"When {infra.name} degrades, agents ({agent_names}) "
                    f"may lose grounding data and hallucinate"
                ),
                component_id=infra.id,
                metric="error_rate",
                threshold=0.05,
                operator="gt",
                predicted_fault=PredictedFault.HALLUCINATION_RISK,
                severity=AlertSeverity.CRITICAL,
                recommended_action=(
                    f"Infrastructure degradation on {infra.name} detected. "
                    f"Pre-emptively switch dependent agents to safe mode."
                ),
            ),
        ]
