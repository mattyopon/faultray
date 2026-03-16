"""Integration tests verifying data flows between FaultRay commands.

These tests validate end-to-end workflows where the output of one engine
feeds into the next, ensuring structural compatibility across the pipeline:
  scan -> evaluate -> plan -> fix
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from faultray.model.components import (
    Capacity,
    ComplianceTags,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    ExternalSLAConfig,
    FailoverConfig,
    NetworkProfile,
    OperationalProfile,
    OperationalTeamConfig,
    ResourceMetrics,
    RuntimeJitter,
    SecurityProfile,
)
from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.cost_engine import CostImpactEngine
from faultray.simulator.planner import RemediationPlanner
from faultray.simulator.security_engine import SecurityResilienceEngine
from faultray.remediation.iac_generator import IaCGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_rich_graph() -> InfraGraph:
    """Build a graph with explicit values for all extended fields."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=30),
        capacity=Capacity(max_connections=10000, max_rps=50000),
        operational_profile=OperationalProfile(
            mtbf_hours=8760, mttr_minutes=5, deploy_downtime_seconds=10,
        ),
        network=NetworkProfile(rtt_ms=0.5, packet_loss_rate=0.0001),
        runtime_jitter=RuntimeJitter(gc_pause_ms=0.0),
        failover=FailoverConfig(enabled=True, promotion_time_seconds=10),
        security=SecurityProfile(
            encryption_in_transit=True, waf_protected=True,
            rate_limiting=True, auth_required=True,
        ),
        cost_profile=CostProfile(
            revenue_per_minute=500.0,
            sla_credit_percent=10.0,
            monthly_contract_value=100000.0,
            customer_ltv=5000.0,
            churn_rate_per_hour_outage=0.005,
            recovery_team_size=3,
        ),
        team=OperationalTeamConfig(
            team_size=5,
            oncall_coverage_hours=24.0,
            mean_acknowledge_time_minutes=3.0,
            runbook_coverage_percent=80.0,
            automation_percent=60.0,
        ),
        compliance_tags=ComplianceTags(
            pci_scope=True, audit_logging=True,
        ),
        external_sla=ExternalSLAConfig(provider_sla=99.95),
    ))

    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=3,
        metrics=ResourceMetrics(cpu_percent=50, memory_percent=60, network_connections=200),
        capacity=Capacity(max_connections=500, connection_pool_size=100),
        operational_profile=OperationalProfile(
            mtbf_hours=2160, mttr_minutes=10,
        ),
        network=NetworkProfile(rtt_ms=1.0, packet_loss_rate=0.001),
        runtime_jitter=RuntimeJitter(gc_pause_ms=5.0, gc_pause_frequency=0.1),
        security=SecurityProfile(
            encryption_in_transit=True, auth_required=True,
        ),
        cost_profile=CostProfile(
            revenue_per_minute=1000.0,
            customer_ltv=10000.0,
            churn_rate_per_hour_outage=0.01,
        ),
        team=OperationalTeamConfig(
            mean_acknowledge_time_minutes=5.0,
            runbook_coverage_percent=60.0,
            automation_percent=30.0,
        ),
        compliance_tags=ComplianceTags(
            contains_pii=True, audit_logging=True,
        ),
    ))

    graph.add_component(Component(
        id="db",
        name="PostgreSQL",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=40, memory_percent=70, disk_percent=65),
        capacity=Capacity(max_connections=100, max_disk_gb=500),
        operational_profile=OperationalProfile(
            mtbf_hours=4320, mttr_minutes=30,
        ),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            network_segmented=True,
        ),
        cost_profile=CostProfile(
            revenue_per_minute=2000.0,
            sla_credit_percent=20.0,
            monthly_contract_value=200000.0,
            recovery_team_size=4,
        ),
        team=OperationalTeamConfig(
            mean_acknowledge_time_minutes=10.0,
            runbook_coverage_percent=90.0,
            automation_percent=10.0,
        ),
        compliance_tags=ComplianceTags(
            pci_scope=True, contains_pii=True, audit_logging=True,
        ),
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires", weight=1.0,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires", weight=1.0,
    ))

    return graph


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_demo_to_evaluate_flow():
    """Demo graph -> SimulationEngine -> evaluate data structure is valid."""
    graph = create_demo_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    # Verify the report can be used by evaluate
    assert report.resilience_score >= 0
    assert len(report.results) > 0

    # Verify score_v2 works on same graph
    v2 = graph.resilience_score_v2()
    assert "score" in v2
    assert "breakdown" in v2
    assert isinstance(v2["score"], float)
    assert isinstance(v2["breakdown"], dict)
    assert "recommendations" in v2


def test_yaml_roundtrip():
    """Save graph to JSON -> reload -> verify components match."""
    graph = create_demo_graph()

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        graph.save(tmp_path)
        reloaded = InfraGraph.load(tmp_path)

        # Verify component IDs match
        assert set(graph.components.keys()) == set(reloaded.components.keys())

        # Verify component attributes are preserved
        for comp_id, original in graph.components.items():
            loaded = reloaded.get_component(comp_id)
            assert loaded is not None
            assert loaded.name == original.name
            assert loaded.type == original.type
            assert loaded.replicas == original.replicas
            assert loaded.port == original.port

        # Verify dependencies are preserved
        original_edges = graph.all_dependency_edges()
        loaded_edges = reloaded.all_dependency_edges()
        assert len(original_edges) == len(loaded_edges)

        # Verify resilience scores are consistent
        assert graph.resilience_score() == pytest.approx(
            reloaded.resilience_score(), abs=0.01
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def test_simulate_to_cost_flow():
    """SimulationEngine output feeds into CostImpactEngine."""
    graph = create_demo_graph()
    sim_engine = SimulationEngine(graph)
    report = sim_engine.run_all_defaults()

    cost_engine = CostImpactEngine(graph)
    cost_report = cost_engine.analyze(report)

    assert cost_report.total_annual_risk >= 0
    assert len(cost_report.impacts) == len(report.results)
    assert cost_report.summary != ""

    # Impacts should be sorted by total_impact descending
    for i in range(len(cost_report.impacts) - 1):
        assert cost_report.impacts[i].total_impact >= cost_report.impacts[i + 1].total_impact


def test_evaluate_to_plan_flow():
    """Evaluate results -> Planner generates actionable plan."""
    graph = create_demo_graph()
    planner = RemediationPlanner(graph)
    plan = planner.plan(target_score=90.0)

    assert len(plan.phases) > 0
    assert plan.total_budget >= 0
    assert plan.total_weeks > 0
    assert plan.current_score >= 0
    assert plan.target_score == 90.0

    # Each phase has tasks
    for phase in plan.phases:
        assert len(phase.tasks) > 0
        assert phase.phase_number in (1, 2, 3)
        assert phase.estimated_weeks > 0
        for task in phase.tasks:
            assert task.id != ""
            assert task.title != ""
            assert task.required_role != ""
            assert task.estimated_hours > 0


def test_five_layer_model_uses_all_fields():
    """5-layer model correctly uses MTBF, failover, network, external SLA, and team config."""
    from faultray.simulator.availability_model import compute_five_layer_model

    graph = _build_rich_graph()
    result = compute_five_layer_model(graph)

    # Layer 1 (Software): should exist
    assert 0.0 < result.layer1_software.availability <= 1.0
    assert result.layer1_software.annual_downtime_seconds > 0

    # Layer 2 (Hardware): uses MTBF, replicas, failover
    assert 0.0 < result.layer2_hardware.availability <= 1.0
    # LB has failover enabled, so its tier availability should be reflected
    assert "lb" in result.layer2_hardware.details

    # Layer 3 (Theoretical): uses network profiles and runtime jitter
    assert 0.0 < result.layer3_theoretical.availability <= 1.0

    # Layer 4 (Operational): uses team config (runbook, automation)
    assert 0.0 < result.layer4_operational.availability <= 1.0
    # High runbook+automation should yield better availability than defaults
    default_graph = create_demo_graph()
    default_result = compute_five_layer_model(default_graph)
    # Rich graph has higher runbook/automation coverage
    assert result.layer4_operational.availability >= default_result.layer4_operational.availability

    # Layer 5 (External SLA): uses external_sla config
    assert 0.0 < result.layer5_external.availability <= 1.0
    # LB has external_sla with 99.95%, so external availability should be < 1.0
    assert result.layer5_external.availability < 1.0
    assert "lb" in result.layer5_external.details


def test_security_to_insurance_flow():
    """SecurityResilienceEngine -> insurance score integration."""
    graph = _build_rich_graph()

    sec_engine = SecurityResilienceEngine(graph)
    sec_report = sec_engine.simulate_all_attacks()

    assert sec_report.total_attacks_simulated > 0
    assert 0.0 <= sec_report.security_resilience_score <= 100.0

    # Score breakdown should contain all categories
    assert "encryption" in sec_report.score_breakdown
    assert "access_control" in sec_report.score_breakdown
    assert "network" in sec_report.score_breakdown
    assert "monitoring" in sec_report.score_breakdown
    assert "recovery" in sec_report.score_breakdown

    # Components with security features should have some mitigation
    for result in sec_report.results:
        assert result.blast_radius >= 1  # at least the entry point


def test_fix_generates_valid_terraform():
    """IaCGenerator output is parseable and addresses findings."""
    graph = create_demo_graph()
    gen = IaCGenerator(graph)
    plan = gen.generate(target_score=90.0)

    assert len(plan.files) > 0

    for f in plan.files:
        assert f.content.strip()  # not empty
        assert f.phase in (1, 2, 3)
        assert f.path  # has a path
        assert f.description  # has a description
        assert f.monthly_cost >= 0
        assert f.impact_score_delta > 0

    # Verify plan metrics
    assert plan.total_monthly_cost >= 0
    assert plan.expected_score_before >= 0
    assert plan.expected_score_after >= plan.expected_score_before
    assert plan.total_phases > 0


def test_full_pipeline():
    """Complete pipeline: demo -> simulate -> evaluate -> cost -> security -> plan -> fix."""
    graph = create_demo_graph()

    # Simulate
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()
    assert len(report.results) > 0
    assert report.resilience_score >= 0

    # Cost
    cost_engine = CostImpactEngine(graph)
    cost_report = cost_engine.analyze(report)
    assert len(cost_report.impacts) == len(report.results)
    assert cost_report.total_annual_risk >= 0

    # Security
    sec_engine = SecurityResilienceEngine(graph)
    sec_report = sec_engine.simulate_all_attacks()
    assert sec_report.total_attacks_simulated > 0

    # Plan
    planner = RemediationPlanner(graph)
    plan = planner.plan(target_score=90.0)
    assert len(plan.phases) > 0

    # Fix
    gen = IaCGenerator(graph)
    fix_plan = gen.generate(target_score=90.0)
    assert len(fix_plan.files) > 0

    # Plan uses resilience_score_v2() while report uses resilience_score().
    # Both should be valid scores, though they may differ numerically.
    assert plan.current_score >= 0
    assert plan.current_score <= 100
    v2 = graph.resilience_score_v2()
    assert plan.current_score == pytest.approx(v2["score"], abs=0.1)


def test_cost_engine_uses_monthly_contract_value():
    """Cost engine uses monthly_contract_value for SLA penalty when set."""
    graph = _build_rich_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    cost_engine = CostImpactEngine(graph)
    cost_report = cost_engine.analyze(report)

    # Should complete without error and have valid impacts
    assert len(cost_report.impacts) > 0
    assert cost_report.total_annual_risk >= 0


def test_cost_engine_uses_customer_ltv_churn():
    """Cost engine includes reputation cost from customer_ltv and churn_rate."""
    graph = _build_rich_graph()

    # Build a graph without LTV/churn for comparison
    basic_graph = InfraGraph()
    basic_graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=1,
        cost_profile=CostProfile(revenue_per_minute=1000.0),
        operational_profile=OperationalProfile(mttr_minutes=60.0),
    ))
    basic_graph.add_component(Component(
        id="app-ltv",
        name="App Server LTV",
        type=ComponentType.APP_SERVER,
        replicas=1,
        cost_profile=CostProfile(
            revenue_per_minute=1000.0,
            customer_ltv=50000.0,
            churn_rate_per_hour_outage=0.02,
        ),
        operational_profile=OperationalProfile(mttr_minutes=60.0),
    ))

    # Both should be non-negative; the LTV component adds churn cost
    from faultray.simulator.cascade import CascadeChain, CascadeEffect
    from faultray.simulator.engine import SimulationReport, ScenarioResult
    from faultray.simulator.scenarios import Scenario, Fault, FaultType
    from faultray.model.components import HealthStatus

    for comp_id in ["app", "app-ltv"]:
        g = InfraGraph()
        comp = basic_graph.get_component(comp_id)
        g.add_component(comp)

        effects = [CascadeEffect(
            component_id=comp_id,
            component_name=comp.name,
            health=HealthStatus.DOWN,
            reason="test",
        )]
        scenario = Scenario(
            id="s1", name="test", description="test",
            faults=[Fault(target_component_id=comp_id, fault_type=FaultType.COMPONENT_DOWN)],
        )
        cascade = CascadeChain(trigger="test", effects=effects, total_components=1)
        sim_report = SimulationReport(
            results=[ScenarioResult(scenario=scenario, cascade=cascade, risk_score=5.0)],
            resilience_score=50.0, total_generated=1,
        )

        ce = CostImpactEngine(g)
        cr = ce.analyze(sim_report)
        if comp_id == "app":
            loss_basic = cr.impacts[0].business_loss
        else:
            loss_ltv = cr.impacts[0].business_loss

    # With LTV/churn, business loss should be higher
    assert loss_ltv > loss_basic


def test_cost_engine_uses_recovery_team_size():
    """Cost engine uses recovery_team_size from component when set."""
    from faultray.simulator.cascade import CascadeChain, CascadeEffect
    from faultray.simulator.engine import SimulationReport, ScenarioResult
    from faultray.simulator.scenarios import Scenario, Fault, FaultType
    from faultray.model.components import HealthStatus

    graph = InfraGraph()
    graph.add_component(Component(
        id="svc",
        name="Service",
        type=ComponentType.APP_SERVER,
        cost_profile=CostProfile(
            recovery_engineer_cost=200.0,
            recovery_team_size=5,
        ),
        operational_profile=OperationalProfile(mttr_minutes=60.0),
    ))

    effects = [CascadeEffect(
        component_id="svc",
        component_name="Service",
        health=HealthStatus.DOWN,
        reason="test",
    )]
    scenario = Scenario(
        id="s1", name="test", description="test",
        faults=[Fault(target_component_id="svc", fault_type=FaultType.COMPONENT_DOWN)],
    )
    cascade = CascadeChain(trigger="test", effects=effects, total_components=1)
    sim_report = SimulationReport(
        results=[ScenarioResult(scenario=scenario, cascade=cascade, risk_score=5.0)],
        resilience_score=50.0, total_generated=1,
    )

    # Engine default is 2 engineers, but component says 5
    engine = CostImpactEngine(graph, num_engineers=2)
    report = engine.analyze(sim_report)

    # recovery_cost = 200 * 1hr * 5 = 1000 (uses component team_size=5)
    assert report.impacts[0].recovery_cost == 1000.0


def test_ops_engine_uses_acknowledge_time():
    """Ops engine includes mean_acknowledge_time_minutes in recovery duration."""
    from faultray.simulator.ops_engine import OpsSimulationEngine, OpsScenario

    graph = InfraGraph()
    graph.add_component(Component(
        id="svc",
        name="Service",
        type=ComponentType.APP_SERVER,
        replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=100, mttr_minutes=10),
        team=OperationalTeamConfig(mean_acknowledge_time_minutes=15.0),
        capacity=Capacity(max_connections=1000),
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=30),
    ))

    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="ack-test", name="Ack Time Test",
        duration_days=30, enable_random_failures=True,
    )
    result = engine.run_ops_scenario(scenario)

    # Find random failure events for 'svc'
    failure_events = [
        e for e in result.events
        if e.target_component_id == "svc" and "Random failure" in e.description
    ]

    # If there are failure events, their duration should include ack time
    # total_recovery = mttr(10min) + ack(15min) = 25min = 1500 seconds
    for event in failure_events:
        assert event.duration_seconds == int(25 * 60)


def test_compliance_engine_pci_scope():
    """Compliance engine generates PCI-specific checks when pci_scope=True."""
    from faultray.simulator.compliance_engine import ComplianceEngine

    graph = InfraGraph()
    graph.add_component(Component(
        id="payments",
        name="Payment Service",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
        compliance_tags=ComplianceTags(pci_scope=True),
        security=SecurityProfile(encryption_at_rest=False, network_segmented=False),
    ))
    graph.add_component(Component(
        id="db",
        name="Card DB",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
        compliance_tags=ComplianceTags(pci_scope=True),
        security=SecurityProfile(encryption_at_rest=True, network_segmented=True),
    ))
    graph.add_dependency(Dependency(source_id="payments", target_id="db"))

    engine = ComplianceEngine(graph)
    report = engine.check_pci_dss()

    # Should have Req-3.4 and Req-1.3 checks
    control_ids = [c.control_id for c in report.checks]
    assert "Req-3.4" in control_ids, "PCI scope should trigger Req-3.4 check"
    assert "Req-1.3" in control_ids, "PCI scope should trigger Req-1.3 check"

    # Req-3.4 should fail (payments lacks encryption_at_rest)
    req34 = next(c for c in report.checks if c.control_id == "Req-3.4")
    assert req34.status == "fail"

    # Req-1.3 should fail (payments lacks network_segmented)
    req13 = next(c for c in report.checks if c.control_id == "Req-1.3")
    assert req13.status == "fail"


def test_compliance_engine_pii_gdpr():
    """Compliance engine generates GDPR/privacy checks when contains_pii=True."""
    from faultray.simulator.compliance_engine import ComplianceEngine

    graph = InfraGraph()
    graph.add_component(Component(
        id="user-db",
        name="User Database",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
        compliance_tags=ComplianceTags(contains_pii=True),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
        ),
    ))

    engine = ComplianceEngine(graph)
    report = engine.check_nist_csf()

    # Should have PR.DS-1 check for PII
    control_ids = [c.control_id for c in report.checks]
    assert "PR.DS-1" in control_ids, "PII components should trigger PR.DS-1 check"

    # PR.DS-1 should pass (both encryption types enabled)
    prds1 = next(c for c in report.checks if c.control_id == "PR.DS-1")
    assert prds1.status == "pass"


def test_compliance_engine_audit_logging():
    """Compliance engine uses audit_logging tag for audit checks."""
    from faultray.simulator.compliance_engine import ComplianceEngine

    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
        compliance_tags=ComplianceTags(audit_logging=True),
    ))

    engine = ComplianceEngine(graph)
    report = engine.check_nist_csf()

    # Should have DE.AE-3 check
    control_ids = [c.control_id for c in report.checks]
    assert "DE.AE-3" in control_ids, "audit_logging tag should trigger DE.AE-3 check"

    # DE.AE-3 should be partial (has audit tags but no monitoring component)
    deae3 = next(c for c in report.checks if c.control_id == "DE.AE-3")
    assert deae3.status == "partial"


def test_availability_model_team_config():
    """5-layer model Layer 4 uses team runbook/automation config."""
    from faultray.simulator.availability_model import compute_five_layer_model

    # Graph with high runbook/automation
    high_graph = InfraGraph()
    high_graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=10),
        team=OperationalTeamConfig(
            runbook_coverage_percent=95.0,
            automation_percent=90.0,
        ),
    ))

    # Graph with low runbook/automation
    low_graph = InfraGraph()
    low_graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=10),
        team=OperationalTeamConfig(
            runbook_coverage_percent=10.0,
            automation_percent=5.0,
        ),
    ))

    high_result = compute_five_layer_model(high_graph)
    low_result = compute_five_layer_model(low_graph)

    # Higher runbook/automation should produce higher Layer 4 availability
    assert high_result.layer4_operational.availability > low_result.layer4_operational.availability


def test_full_pipeline_with_rich_graph():
    """Complete pipeline with all extended fields set."""
    graph = _build_rich_graph()

    # Simulate
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()
    assert len(report.results) > 0

    # Cost
    cost_engine = CostImpactEngine(graph)
    cost_report = cost_engine.analyze(report)
    assert len(cost_report.impacts) > 0
    assert cost_report.total_annual_risk >= 0

    # Security
    sec_engine = SecurityResilienceEngine(graph)
    sec_report = sec_engine.simulate_all_attacks()
    assert sec_report.total_attacks_simulated > 0

    # Compliance
    from faultray.simulator.compliance_engine import ComplianceEngine
    compliance_engine = ComplianceEngine(graph)
    all_compliance = compliance_engine.check_all()
    assert "soc2" in all_compliance
    assert "pci_dss" in all_compliance
    # PCI checks should include scope-specific checks since we have pci_scope=True
    pci_control_ids = [c.control_id for c in all_compliance["pci_dss"].checks]
    assert "Req-3.4" in pci_control_ids

    # 5-layer availability
    from faultray.simulator.availability_model import compute_five_layer_model
    five_layer = compute_five_layer_model(graph)
    assert five_layer.layer4_operational.availability > 0
    assert five_layer.layer5_external.availability < 1.0  # has external SLA

    # Plan
    planner = RemediationPlanner(graph)
    plan = planner.plan(target_score=90.0)

    # Fix
    gen = IaCGenerator(graph)
    fix_plan = gen.generate(target_score=90.0)

    # Plan uses resilience_score_v2() while report uses resilience_score().
    # Both should be valid scores.
    assert plan.current_score >= 0
    assert plan.current_score <= 100
    v2 = graph.resilience_score_v2()
    assert plan.current_score == pytest.approx(v2["score"], abs=0.1)
