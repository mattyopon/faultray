"""Tests for the MANAGE engine — agent runtime monitoring and anomaly detection."""

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.agent_monitor import (
    AgentMonitorEngine,
    AlertSeverity,
    MonitoringPlan,
    MonitoringRule,
    PredictedFault,
)


def _build_agent_infra_graph() -> InfraGraph:
    """Build a graph with agent + infrastructure components."""
    g = InfraGraph()
    g.add_component(Component(
        id="agent", name="Support Agent", type=ComponentType.AI_AGENT,
        parameters={
            "max_context_tokens": 200000,
            "hallucination_risk": 0.05,
        },
    ))
    g.add_component(Component(
        id="llm", name="Claude API", type=ComponentType.LLM_ENDPOINT,
        parameters={"rate_limit_rpm": 1000, "p99_latency_ms": 3000},
    ))
    g.add_component(Component(
        id="tool", name="Search Tool", type=ComponentType.TOOL_SERVICE,
        parameters={"failure_rate": 0.01},
    ))
    g.add_component(Component(
        id="orch", name="Orchestrator", type=ComponentType.AGENT_ORCHESTRATOR,
        parameters={"max_iterations": 50},
    ))
    g.add_component(Component(
        id="db", name="Postgres", type=ComponentType.DATABASE,
    ))
    g.add_dependency(Dependency(source_id="agent", target_id="llm", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="agent", target_id="tool", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="agent", target_id="db", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="orch", target_id="agent", dependency_type="requires"))
    return g


class TestGenerateMonitoringPlan:
    """Test AgentMonitorEngine.generate_monitoring_plan."""

    def test_returns_monitoring_plan(self):
        g = _build_agent_infra_graph()
        engine = AgentMonitorEngine(g)
        plan = engine.generate_monitoring_plan()
        assert isinstance(plan, MonitoringPlan)

    def test_generates_rules(self):
        g = _build_agent_infra_graph()
        engine = AgentMonitorEngine(g)
        plan = engine.generate_monitoring_plan()
        assert len(plan.rules) > 0

    def test_coverage_percent_computed(self):
        g = _build_agent_infra_graph()
        engine = AgentMonitorEngine(g)
        plan = engine.generate_monitoring_plan()
        assert plan.coverage_percent > 0.0
        assert plan.coverage_percent <= 100.0

    def test_total_components_monitored(self):
        g = _build_agent_infra_graph()
        engine = AgentMonitorEngine(g)
        plan = engine.generate_monitoring_plan()
        assert plan.total_components_monitored > 0
        assert plan.total_components_monitored <= len(g.components)


class TestRulesForAgentType:
    """Test that rules are generated for AI_AGENT components."""

    def test_context_usage_rule_generated(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        context_rules = [r for r in plan.rules if "context" in r.rule_id.lower()]
        assert len(context_rules) >= 1
        rule = context_rules[0]
        assert rule.component_id == "agent"
        assert rule.predicted_fault == PredictedFault.CONTEXT_OVERFLOW_RISK
        assert rule.severity == AlertSeverity.WARNING

    def test_hallucination_rate_rule_generated(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        halluc_rules = [r for r in plan.rules if "hallucination" in r.rule_id.lower()]
        assert len(halluc_rules) >= 1
        rule = halluc_rules[0]
        assert rule.component_id == "agent"
        assert rule.predicted_fault == PredictedFault.HALLUCINATION_RISK
        assert rule.severity == AlertSeverity.CRITICAL

    def test_context_threshold_based_on_max_tokens(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        context_rules = [r for r in plan.rules if "context-usage" in r.rule_id]
        assert len(context_rules) == 1
        # Threshold should be 80% of max_context_tokens (200000)
        assert context_rules[0].threshold == 200000 * 0.8


class TestRulesForLLMEndpoint:
    """Test that rules are generated for LLM_ENDPOINT components."""

    def test_rate_limit_rule_generated(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        rate_rules = [r for r in plan.rules if "rate-limit" in r.rule_id]
        assert len(rate_rules) >= 1
        rule = rate_rules[0]
        assert rule.component_id == "llm"
        assert rule.predicted_fault == PredictedFault.RATE_LIMIT_APPROACHING
        assert rule.operator == "gt"

    def test_latency_rule_generated(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        latency_rules = [r for r in plan.rules if "latency" in r.rule_id]
        assert len(latency_rules) >= 1
        rule = latency_rules[0]
        assert rule.component_id == "llm"
        assert rule.predicted_fault == PredictedFault.CASCADING_FAILURE_RISK
        assert rule.severity == AlertSeverity.CRITICAL

    def test_rate_limit_threshold_based_on_rpm(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        rate_rules = [r for r in plan.rules if "rate-limit" in r.rule_id]
        # Threshold should be 80% of rate_limit_rpm (1000)
        assert rate_rules[0].threshold == 1000 * 0.8


class TestRulesForToolService:
    """Test that rules are generated for TOOL_SERVICE components."""

    def test_error_rate_rule_generated(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        tool_rules = [r for r in plan.rules if r.component_id == "tool"]
        assert len(tool_rules) >= 1
        rule = tool_rules[0]
        assert rule.predicted_fault == PredictedFault.TOOL_DEGRADATION
        assert rule.severity == AlertSeverity.WARNING

    def test_error_rate_threshold_based_on_failure_rate(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        tool_rules = [r for r in plan.rules if r.component_id == "tool"]
        # Threshold should be 3x failure_rate (0.01)
        assert tool_rules[0].threshold == 0.01 * 3


class TestRulesForOrchestrator:
    """Test that rules are generated for AGENT_ORCHESTRATOR components."""

    def test_iteration_count_rule_generated(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        orch_rules = [r for r in plan.rules if r.component_id == "orch"]
        assert len(orch_rules) >= 1
        rule = orch_rules[0]
        assert "iteration" in rule.rule_id
        assert rule.predicted_fault == PredictedFault.CASCADING_FAILURE_RISK
        assert rule.severity == AlertSeverity.WARNING

    def test_iteration_threshold_based_on_max(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        orch_rules = [r for r in plan.rules if r.component_id == "orch"]
        # Threshold should be 80% of max_iterations (50)
        assert orch_rules[0].threshold == 50 * 0.8


class TestCrossLayerRules:
    """Test cross-layer rules when agents depend on databases."""

    def test_db_agent_cross_layer_rule_generated(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        cross_rules = [r for r in plan.rules if "grounding-risk" in r.rule_id]
        assert len(cross_rules) >= 1

    def test_cross_layer_rule_references_infra_component(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        cross_rules = [r for r in plan.rules if "grounding-risk" in r.rule_id]
        assert cross_rules[0].component_id == "db"

    def test_cross_layer_rule_is_critical_severity(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        cross_rules = [r for r in plan.rules if "grounding-risk" in r.rule_id]
        assert cross_rules[0].severity == AlertSeverity.CRITICAL

    def test_cross_layer_rule_predicts_hallucination(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        cross_rules = [r for r in plan.rules if "grounding-risk" in r.rule_id]
        assert cross_rules[0].predicted_fault == PredictedFault.HALLUCINATION_RISK

    def test_no_cross_layer_rules_without_agent_db_dependency(self):
        """A database with no agent dependents should not generate cross-layer rules."""
        g = InfraGraph()
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
        ))
        g.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
        ))
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        cross_rules = [r for r in plan.rules if "grounding-risk" in r.rule_id]
        assert len(cross_rules) == 0


class TestMonitoringRuleStructure:
    """Test that MonitoringRule fields are properly populated."""

    def test_rule_has_all_required_fields(self):
        g = _build_agent_infra_graph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        for rule in plan.rules:
            assert rule.rule_id != ""
            assert rule.name != ""
            assert rule.description != ""
            assert rule.component_id != ""
            assert rule.metric != ""
            assert rule.threshold >= 0
            assert rule.operator in ("gt", "lt", "gte", "lte")
            assert isinstance(rule.predicted_fault, PredictedFault)
            assert isinstance(rule.severity, AlertSeverity)
            assert rule.recommended_action != ""


class TestEmptyGraph:
    """Test monitoring plan with empty or non-agent graphs."""

    def test_empty_graph_returns_empty_plan(self):
        g = InfraGraph()
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        assert plan.rules == []
        assert plan.total_components_monitored == 0
        assert plan.coverage_percent == 0.0

    def test_infra_only_graph_returns_no_agent_rules(self):
        g = InfraGraph()
        g.add_component(Component(id="db", name="DB", type=ComponentType.DATABASE))
        g.add_component(Component(id="app", name="App", type=ComponentType.APP_SERVER))
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        plan = AgentMonitorEngine(g).generate_monitoring_plan()
        # No agent components, so no agent-specific rules
        agent_rule_ids = [r.rule_id for r in plan.rules if "agent" in r.rule_id.lower()]
        assert len(agent_rule_ids) == 0
