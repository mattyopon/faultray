"""Tests for the ADOPT engine — AI agent adoption risk assessment."""

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.adoption_engine import (
    AdoptionEngine,
    AdoptionRiskLevel,
    AgentAdoptionReport,
)


def _build_agent_graph(
    *,
    with_side_effect_tool: bool = False,
    agent_params: dict | None = None,
    agent_replicas: int = 1,
) -> InfraGraph:
    """Build a graph with an agent and optional dependencies."""
    g = InfraGraph()
    params = agent_params or {}
    g.add_component(Component(
        id="agent", name="Support Agent", type=ComponentType.AI_AGENT,
        replicas=agent_replicas, parameters=params,
    ))
    g.add_component(Component(
        id="llm", name="Claude API", type=ComponentType.LLM_ENDPOINT,
        parameters={"rate_limit_rpm": 1000, "p99_latency_ms": 3000},
    ))
    g.add_dependency(Dependency(
        source_id="agent", target_id="llm", dependency_type="requires",
    ))

    if with_side_effect_tool:
        g.add_component(Component(
            id="tool-write", name="DB Writer", type=ComponentType.TOOL_SERVICE,
            parameters={"side_effects": 1, "failure_rate": 0.02},
        ))
        g.add_dependency(Dependency(
            source_id="agent", target_id="tool-write", dependency_type="requires",
        ))

    return g


class TestAdoptionEngineAssessAgent:
    """Test AdoptionEngine.assess_agent."""

    def test_returns_report_for_valid_agent(self):
        g = _build_agent_graph()
        engine = AdoptionEngine(g)
        report = engine.assess_agent("agent")
        assert isinstance(report, AgentAdoptionReport)
        assert report.agent_id == "agent"
        assert report.agent_name == "Support Agent"

    def test_risk_score_is_bounded(self):
        g = _build_agent_graph()
        engine = AdoptionEngine(g)
        report = engine.assess_agent("agent")
        assert 0.0 <= report.risk_score <= 10.0

    def test_risk_level_matches_score(self):
        g = _build_agent_graph()
        engine = AdoptionEngine(g)
        report = engine.assess_agent("agent")
        if report.risk_score < 4.0:
            assert report.risk_level == AdoptionRiskLevel.LOW
        elif report.risk_score < 7.0:
            assert report.risk_level == AdoptionRiskLevel.MEDIUM
        elif report.risk_score < 9.0:
            assert report.risk_level == AdoptionRiskLevel.HIGH
        else:
            assert report.risk_level == AdoptionRiskLevel.CRITICAL

    def test_raises_for_nonexistent_component(self):
        g = _build_agent_graph()
        engine = AdoptionEngine(g)
        with pytest.raises(ValueError, match="not found"):
            engine.assess_agent("nonexistent")

    def test_raises_for_non_agent_component(self):
        g = _build_agent_graph()
        engine = AdoptionEngine(g)
        with pytest.raises(ValueError, match="not an agent type"):
            engine.assess_agent("llm")

    def test_safe_to_deploy_when_low_risk(self):
        """An agent with many failsafes should be considered safe to deploy."""
        g = _build_agent_graph(
            agent_params={
                "human_escalation": 1,
                "fallback_model_id": "gpt-4o",
                "circuit_breaker_on_hallucination": 1,
                "max_iterations": 50,
                "requires_grounding": 1,
            },
            agent_replicas=2,
        )
        engine = AdoptionEngine(g)
        report = engine.assess_agent("agent")
        assert report.safe_to_deploy is True
        assert report.risk_score < 7.0


class TestFailsafeImpactOnRisk:
    """Test that failsafes reduce risk scores."""

    def test_more_failsafes_lower_risk(self):
        # Agent without failsafes
        g_no_failsafe = _build_agent_graph(agent_params={})
        report_no = AdoptionEngine(g_no_failsafe).assess_agent("agent")

        # Agent with all failsafes
        g_failsafe = _build_agent_graph(
            agent_params={
                "human_escalation": 1,
                "fallback_model_id": "gpt-4o",
                "circuit_breaker_on_hallucination": 1,
                "max_iterations": 50,
                "requires_grounding": 1,
            },
            agent_replicas=2,
        )
        report_yes = AdoptionEngine(g_failsafe).assess_agent("agent")
        assert report_yes.risk_score < report_no.risk_score

    def test_failsafes_are_listed_in_report(self):
        g = _build_agent_graph(
            agent_params={"human_escalation": 1, "max_iterations": 50},
        )
        engine = AdoptionEngine(g)
        report = engine.assess_agent("agent")
        assert len(report.failsafes) > 0
        failsafe_names = [f.name for f in report.failsafes]
        assert "Human escalation" in failsafe_names
        assert "Iteration limit" in failsafe_names

    def test_present_failsafes_marked_correctly(self):
        g = _build_agent_graph(
            agent_params={"human_escalation": 1, "max_iterations": 50},
        )
        report = AdoptionEngine(g).assess_agent("agent")
        human_fs = next(f for f in report.failsafes if f.name == "Human escalation")
        assert human_fs.present is True
        iteration_fs = next(f for f in report.failsafes if f.name == "Iteration limit")
        assert iteration_fs.present is True

    def test_absent_failsafes_marked_correctly(self):
        g = _build_agent_graph(agent_params={})
        report = AdoptionEngine(g).assess_agent("agent")
        human_fs = next(f for f in report.failsafes if f.name == "Human escalation")
        assert human_fs.present is False


class TestSideEffectImpactOnRisk:
    """Test that side-effect tools increase risk scores."""

    def test_side_effect_tool_increases_risk(self):
        g_no_se = _build_agent_graph(with_side_effect_tool=False)
        report_no = AdoptionEngine(g_no_se).assess_agent("agent")

        g_se = _build_agent_graph(with_side_effect_tool=True)
        report_se = AdoptionEngine(g_se).assess_agent("agent")
        assert report_se.risk_score > report_no.risk_score

    def test_hallucination_impact_mentions_side_effects(self):
        """When a side-effect tool depends ON the agent (is downstream),
        the hallucination impact should flag it."""
        g = _build_agent_graph(with_side_effect_tool=False)
        # Add a tool service that depends ON the agent (downstream)
        g.add_component(Component(
            id="tool-downstream", name="DB Writer", type=ComponentType.TOOL_SERVICE,
            parameters={"side_effects": 1},
        ))
        g.add_dependency(Dependency(
            source_id="tool-downstream", target_id="agent", dependency_type="requires",
        ))
        report = AdoptionEngine(g).assess_agent("agent")
        # hallucination_impact should mention side effects since a side-effect tool
        # is downstream of the agent
        assert "side effect" in report.hallucination_impact.lower() or \
               "HIGH" in report.hallucination_impact


class TestAssessAllAgents:
    """Test assess_all_agents returns reports for all agents."""

    def test_returns_report_for_each_agent(self):
        g = InfraGraph()
        g.add_component(Component(
            id="agent-1", name="Agent A", type=ComponentType.AI_AGENT,
        ))
        g.add_component(Component(
            id="agent-2", name="Agent B", type=ComponentType.AI_AGENT,
        ))
        g.add_component(Component(
            id="orch", name="Orchestrator", type=ComponentType.AGENT_ORCHESTRATOR,
        ))
        g.add_component(Component(
            id="llm", name="LLM", type=ComponentType.LLM_ENDPOINT,
        ))
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
        ))
        engine = AdoptionEngine(g)
        reports = engine.assess_all_agents()
        # Only AI_AGENT and AGENT_ORCHESTRATOR are assessed
        assert len(reports) == 3
        report_ids = {r.agent_id for r in reports}
        assert "agent-1" in report_ids
        assert "agent-2" in report_ids
        assert "orch" in report_ids
        # LLM_ENDPOINT and DATABASE should not be in reports
        assert "llm" not in report_ids
        assert "db" not in report_ids

    def test_no_agents_returns_empty_list(self):
        g = InfraGraph()
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
        ))
        engine = AdoptionEngine(g)
        reports = engine.assess_all_agents()
        assert reports == []


class TestAdoptionRiskLevelMapping:
    """Test the score-to-level mapping."""

    def test_low_level(self):
        engine = AdoptionEngine(InfraGraph())
        assert engine._score_to_level(0.0) == AdoptionRiskLevel.LOW
        assert engine._score_to_level(3.9) == AdoptionRiskLevel.LOW

    def test_medium_level(self):
        engine = AdoptionEngine(InfraGraph())
        assert engine._score_to_level(4.0) == AdoptionRiskLevel.MEDIUM
        assert engine._score_to_level(6.9) == AdoptionRiskLevel.MEDIUM

    def test_high_level(self):
        engine = AdoptionEngine(InfraGraph())
        assert engine._score_to_level(7.0) == AdoptionRiskLevel.HIGH
        assert engine._score_to_level(8.9) == AdoptionRiskLevel.HIGH

    def test_critical_level(self):
        engine = AdoptionEngine(InfraGraph())
        assert engine._score_to_level(9.0) == AdoptionRiskLevel.CRITICAL
        assert engine._score_to_level(10.0) == AdoptionRiskLevel.CRITICAL


class TestRecommendations:
    """Test recommendation generation."""

    def test_high_risk_gets_critical_recommendation(self):
        """Agents with score >= 7 should get a CRITICAL recommendation."""
        g = _build_agent_graph(with_side_effect_tool=True)
        # Add many dependencies to increase blast radius
        for i in range(10):
            g.add_component(Component(
                id=f"dep-{i}", name=f"Dep {i}", type=ComponentType.APP_SERVER,
            ))
            g.add_dependency(Dependency(
                source_id=f"dep-{i}", target_id="agent", dependency_type="requires",
            ))
        engine = AdoptionEngine(g)
        report = engine.assess_agent("agent")
        if report.risk_score >= 7.0:
            critical_recs = [r for r in report.recommendations if "CRITICAL" in r]
            assert len(critical_recs) >= 1

    def test_absent_failsafes_generate_recommendations(self):
        g = _build_agent_graph(agent_params={})
        report = AdoptionEngine(g).assess_agent("agent")
        # Absent failsafes should produce recommendations
        assert len(report.recommendations) > 0
