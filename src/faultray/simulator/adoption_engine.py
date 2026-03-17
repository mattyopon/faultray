"""ADOPT engine — AI Agent adoption risk assessment.

Evaluates the risk of introducing AI agents into existing infrastructure
by simulating agent failure scenarios before deployment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


class AdoptionRiskLevel(str, Enum):
    LOW = "low"           # Score 0-3: Safe to deploy
    MEDIUM = "medium"     # Score 4-6: Deploy with mitigations
    HIGH = "high"         # Score 7-8: Significant risk, needs redesign
    CRITICAL = "critical" # Score 9-10: Do not deploy without major changes


@dataclass
class FailsafeAssessment:
    """Assessment of a specific failsafe mechanism."""
    name: str
    present: bool
    description: str
    recommendation: str = ""


@dataclass
class AgentAdoptionReport:
    """Risk assessment report for adding an AI agent to infrastructure."""
    agent_name: str
    agent_id: str
    risk_score: float  # 0-10
    risk_level: AdoptionRiskLevel
    max_blast_radius: int  # Number of components affected if agent fails
    hallucination_impact: str  # Description of hallucination consequences
    failsafes: list[FailsafeAssessment] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    safe_to_deploy: bool = True


class AdoptionEngine:
    """Evaluates risk of adding AI agents to existing infrastructure."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def assess_agent(self, agent_id: str) -> AgentAdoptionReport:
        """Assess the risk of a specific agent component."""
        agent = self.graph.get_component(agent_id)
        if agent is None:
            raise ValueError(f"Component '{agent_id}' not found in graph")
        if agent.type not in (ComponentType.AI_AGENT, ComponentType.AGENT_ORCHESTRATOR):
            raise ValueError(f"Component '{agent_id}' is not an agent type")

        # 1. Calculate blast radius
        affected = self.graph.get_all_affected(agent_id)
        blast_radius = len(affected)

        # 2. Check failsafes
        failsafes = self._check_failsafes(agent)
        failsafe_score = sum(1 for f in failsafes if f.present) / max(len(failsafes), 1)

        # 3. Check hallucination impact
        hallucination_impact = self._assess_hallucination_impact(agent)

        # 4. Check dependency chain depth
        deps = self.graph.get_dependencies(agent_id)
        depth = len(deps)

        # 5. Calculate risk score
        risk_score = self._calculate_risk_score(
            blast_radius=blast_radius,
            failsafe_ratio=failsafe_score,
            has_side_effects=self._has_side_effects(agent),
            depth=depth,
            replicas=agent.replicas,
        )

        # 6. Generate recommendations
        recommendations = self._generate_recommendations(agent, failsafes, risk_score)

        risk_level = self._score_to_level(risk_score)

        return AgentAdoptionReport(
            agent_name=agent.name,
            agent_id=agent.id,
            risk_score=round(risk_score, 1),
            risk_level=risk_level,
            max_blast_radius=blast_radius,
            hallucination_impact=hallucination_impact,
            failsafes=failsafes,
            recommendations=recommendations,
            safe_to_deploy=risk_score < 7.0,
        )

    def assess_all_agents(self) -> list[AgentAdoptionReport]:
        """Assess all agent components in the graph."""
        agent_types = {ComponentType.AI_AGENT, ComponentType.AGENT_ORCHESTRATOR}
        agents = [c for c in self.graph.components.values() if c.type in agent_types]
        return [self.assess_agent(a.id) for a in agents]

    def _check_failsafes(self, agent: Component) -> list[FailsafeAssessment]:
        """Check what failsafe mechanisms are in place."""
        failsafes = []
        params = agent.parameters or {}

        # 1. Human escalation path
        failsafes.append(FailsafeAssessment(
            name="Human escalation",
            present=bool(params.get("human_escalation", 0)),
            description="Agent can escalate to human when uncertain",
            recommendation="Add human-in-the-loop for high-stakes decisions",
        ))

        # 2. Fallback LLM
        has_fallback = bool(params.get("fallback_model_id", ""))
        failsafes.append(FailsafeAssessment(
            name="Fallback LLM",
            present=has_fallback,
            description="Alternative LLM endpoint if primary fails",
            recommendation="Configure a fallback model (e.g., OpenAI as backup for Claude)",
        ))

        # 3. Circuit breaker on hallucination
        failsafes.append(FailsafeAssessment(
            name="Hallucination circuit breaker",
            present=bool(params.get("circuit_breaker_on_hallucination", 0)),
            description="Automatically stops agent if hallucination detected",
            recommendation="Enable circuit breaker for hallucination detection",
        ))

        # 4. Max iterations limit
        max_iter = int(params.get("max_iterations", 0))
        failsafes.append(FailsafeAssessment(
            name="Iteration limit",
            present=max_iter > 0,
            description=f"Max iterations: {max_iter}" if max_iter > 0 else "No iteration limit",
            recommendation="Set max_iterations to prevent infinite agent loops",
        ))

        # 5. Replicas for redundancy
        failsafes.append(FailsafeAssessment(
            name="Redundancy",
            present=agent.replicas > 1,
            description=f"Replicas: {agent.replicas}",
            recommendation="Run at least 2 replicas for agent availability",
        ))

        # 6. Grounding data source
        failsafes.append(FailsafeAssessment(
            name="Data grounding",
            present=bool(params.get("requires_grounding", 0)),
            description="Agent is grounded in verified data sources",
            recommendation="Enable requires_grounding and connect to verified data sources",
        ))

        return failsafes

    def _assess_hallucination_impact(self, agent: Component) -> str:
        """Describe what happens when this agent hallucinates."""
        affected = self.graph.get_all_affected(agent.id)
        params = agent.parameters or {}
        risk = float(params.get("hallucination_risk", 0.05))

        if not affected:
            return f"Low impact — agent has no dependents. Hallucination risk: {risk:.1%}"

        # Check if any downstream component has side effects
        has_downstream_side_effects = False
        for comp_id in affected:
            comp = self.graph.get_component(comp_id)
            if comp and comp.type == ComponentType.TOOL_SERVICE:
                if bool(comp.parameters.get("side_effects", 0)):
                    has_downstream_side_effects = True
                    break

        if has_downstream_side_effects:
            return (
                f"HIGH impact — agent hallucination can trigger tools with side effects "
                f"(e.g., database writes, API calls, financial transactions). "
                f"Hallucination risk: {risk:.1%}. Affected components: {len(affected)}"
            )

        return (
            f"Medium impact — agent hallucination affects {len(affected)} downstream components. "
            f"Hallucination risk: {risk:.1%}. No side-effect tools detected."
        )

    def _has_side_effects(self, agent: Component) -> bool:
        """Check if agent can trigger side effects through tools."""
        deps = self.graph.get_dependencies(agent.id)
        for dep in deps:
            if dep.type == ComponentType.TOOL_SERVICE:
                if bool(dep.parameters.get("side_effects", 0)):
                    return True
        return False

    def _calculate_risk_score(
        self,
        blast_radius: int,
        failsafe_ratio: float,
        has_side_effects: bool,
        depth: int,
        replicas: int,
    ) -> float:
        """Calculate overall risk score (0-10)."""
        score = 0.0

        # Blast radius contribution (0-3)
        if blast_radius >= 10:
            score += 3.0
        elif blast_radius >= 5:
            score += 2.0
        elif blast_radius >= 2:
            score += 1.0

        # Failsafe deficiency (0-3)
        score += (1.0 - failsafe_ratio) * 3.0

        # Side effects (0-2)
        if has_side_effects:
            score += 2.0

        # Dependency depth (0-1)
        if depth > 5:
            score += 1.0
        elif depth > 3:
            score += 0.5

        # Single replica penalty (0-1)
        if replicas <= 1:
            score += 1.0

        return min(10.0, score)

    def _score_to_level(self, score: float) -> AdoptionRiskLevel:
        if score >= 9.0:
            return AdoptionRiskLevel.CRITICAL
        if score >= 7.0:
            return AdoptionRiskLevel.HIGH
        if score >= 4.0:
            return AdoptionRiskLevel.MEDIUM
        return AdoptionRiskLevel.LOW

    def _generate_recommendations(
        self,
        agent: Component,
        failsafes: list[FailsafeAssessment],
        risk_score: float,
    ) -> list[str]:
        """Generate actionable recommendations."""
        recs = []

        for fs in failsafes:
            if not fs.present:
                recs.append(fs.recommendation)

        if risk_score >= 7.0:
            recs.insert(0, "CRITICAL: Consider phased rollout — start with non-critical workflows only")

        if risk_score >= 4.0:
            recs.append("Add comprehensive logging for all agent decisions for audit trail")

        return recs
