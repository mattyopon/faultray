"""Tests for the Cost Impact Engine."""

from __future__ import annotations

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
    SLOTarget,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.cascade import CascadeChain, CascadeEffect
from infrasim.simulator.cost_engine import (
    CostImpactEngine,
    CostImpactReport,
    ScenarioCostImpact,
)
from infrasim.simulator.engine import SimulationEngine, SimulationReport, ScenarioResult
from infrasim.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scenario(
    sid: str = "s1",
    name: str = "test-scenario",
    target: str = "app",
    fault_type: FaultType = FaultType.COMPONENT_DOWN,
) -> Scenario:
    """Create a simple scenario with a single fault."""
    return Scenario(
        id=sid,
        name=name,
        description="Test scenario",
        faults=[Fault(target_component_id=target, fault_type=fault_type)],
    )


def _build_graph_with_costs() -> InfraGraph:
    """Build a graph with cost profiles set for testing."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=2,
        cost_profile=CostProfile(
            hourly_infra_cost=10.0,
            revenue_per_minute=100.0,
            sla_credit_percent=10.0,
            recovery_engineer_cost=150.0,
        ),
        operational_profile=OperationalProfile(mttr_minutes=15.0),
        slo_targets=[SLOTarget(name="Availability", metric="availability", target=99.9)],
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=3,
        cost_profile=CostProfile(
            hourly_infra_cost=20.0,
            revenue_per_minute=200.0,
            sla_credit_percent=15.0,
            recovery_engineer_cost=200.0,
        ),
        operational_profile=OperationalProfile(mttr_minutes=30.0),
        slo_targets=[SLOTarget(name="Availability", metric="availability", target=99.9)],
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        replicas=2,
        cost_profile=CostProfile(
            hourly_infra_cost=50.0,
            revenue_per_minute=500.0,
            sla_credit_percent=20.0,
            recovery_engineer_cost=300.0,
        ),
        operational_profile=OperationalProfile(mttr_minutes=60.0),
        slo_targets=[SLOTarget(name="Availability", metric="availability", target=99.95)],
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app"))
    graph.add_dependency(Dependency(source_id="app", target_id="db"))
    return graph


def _build_report_with_effects(
    graph: InfraGraph,
    effects: list[CascadeEffect],
    scenario_name: str = "test-scenario",
    scenario_id: str = "s1",
    likelihood: float = 1.0,
) -> SimulationReport:
    """Build a SimulationReport with a single scenario containing given effects."""
    scenario = _make_scenario(sid=scenario_id, name=scenario_name)
    cascade = CascadeChain(
        trigger=scenario_name,
        effects=effects,
        total_components=len(graph.components),
        likelihood=likelihood,
    )
    result = ScenarioResult(
        scenario=scenario,
        cascade=cascade,
        risk_score=cascade.severity,
    )
    return SimulationReport(
        results=[result],
        resilience_score=8.0,
        total_generated=1,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cost_profile_defaults():
    """CostProfile should have sensible defaults."""
    cp = CostProfile()
    assert cp.hourly_infra_cost == 0.0
    assert cp.revenue_per_minute == 0.0
    assert cp.sla_credit_percent == 0.0
    assert cp.recovery_engineer_cost == 100.0


def test_cost_calculation_known_values():
    """Cost calculation with known values should produce expected results."""
    graph = _build_graph_with_costs()

    # Simulate: app goes DOWN, causing cascade to lb (degraded).
    effects = [
        CascadeEffect(
            component_id="app",
            component_name="App Server",
            health=HealthStatus.DOWN,
            reason="Component failure",
        ),
        CascadeEffect(
            component_id="lb",
            component_name="Load Balancer",
            health=HealthStatus.DEGRADED,
            reason="Dependency app is down",
        ),
    ]
    report = _build_report_with_effects(graph, effects)

    engine = CostImpactEngine(graph)
    cost_report = engine.analyze(report)

    assert len(cost_report.impacts) == 1
    impact = cost_report.impacts[0]

    # App is DOWN with mttr_minutes=30.0, so downtime = 30.0 minutes.
    assert impact.downtime_minutes == 30.0

    # Business loss:
    #   app (DOWN, factor=1.0): 200 * 30 * 1.0 = 6000
    #   lb (DEGRADED, factor=0.2): 100 * 30 * 0.2 = 600
    #   total = 6600
    assert impact.business_loss == 6600.0

    # SLA penalty: downtime=30min > allowed (43200 * 0.001 = 43.2min) -> NO breach
    # Actually 99.9% SLO -> allowed = 43200 * 0.001 = 43.2 min.
    # 30 < 43.2 so no SLA penalty.
    assert impact.sla_penalty == 0.0

    # Recovery cost: max hourly cost = 200 (app is DOWN), mttr_hours = 0.5,
    #   num_engineers = 2 -> 200 * 0.5 * 2 = 200
    assert impact.recovery_cost == 200.0

    assert impact.total_impact == 6800.0


def test_ranking_order_highest_first():
    """Scenarios should be ranked by total cost impact, highest first."""
    graph = _build_graph_with_costs()

    # Two scenarios with different cost impacts.
    effects_low = [
        CascadeEffect(
            component_id="lb",
            component_name="Load Balancer",
            health=HealthStatus.DEGRADED,
            reason="Minor issue",
        ),
    ]
    effects_high = [
        CascadeEffect(
            component_id="db",
            component_name="Database",
            health=HealthStatus.DOWN,
            reason="Database crash",
        ),
        CascadeEffect(
            component_id="app",
            component_name="App Server",
            health=HealthStatus.DOWN,
            reason="Cascade from db",
        ),
    ]

    scenario_low = _make_scenario(sid="s-low", name="low-impact", target="lb")
    scenario_high = _make_scenario(sid="s-high", name="high-impact", target="db")

    cascade_low = CascadeChain(
        trigger="low-impact",
        effects=effects_low,
        total_components=3,
    )
    cascade_high = CascadeChain(
        trigger="high-impact",
        effects=effects_high,
        total_components=3,
    )

    report = SimulationReport(
        results=[
            ScenarioResult(scenario=scenario_low, cascade=cascade_low, risk_score=1.0),
            ScenarioResult(scenario=scenario_high, cascade=cascade_high, risk_score=5.0),
        ],
        resilience_score=7.0,
        total_generated=2,
    )

    engine = CostImpactEngine(graph)
    cost_report = engine.analyze(report)

    assert len(cost_report.impacts) == 2
    # High impact should be first.
    assert cost_report.impacts[0].scenario_name == "high-impact"
    assert cost_report.impacts[0].total_impact >= cost_report.impacts[1].total_impact


def test_zero_cost_scenario():
    """Scenario with no effects should have zero cost."""
    graph = _build_graph_with_costs()

    scenario = _make_scenario(sid="s-zero", name="no-effects")
    cascade = CascadeChain(
        trigger="no-effects",
        effects=[],
        total_components=3,
    )
    report = SimulationReport(
        results=[ScenarioResult(scenario=scenario, cascade=cascade, risk_score=0.0)],
        resilience_score=10.0,
        total_generated=1,
    )

    engine = CostImpactEngine(graph)
    cost_report = engine.analyze(report)

    assert len(cost_report.impacts) == 1
    impact = cost_report.impacts[0]
    assert impact.total_impact == 0.0
    assert impact.business_loss == 0.0
    assert impact.sla_penalty == 0.0
    assert impact.recovery_cost == 0.0
    assert impact.downtime_minutes == 0.0


def test_sla_penalty_calculation():
    """SLA penalty should trigger when downtime exceeds allowed budget."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="api",
        name="API Gateway",
        type=ComponentType.APP_SERVER,
        cost_profile=CostProfile(
            revenue_per_minute=1000.0,
            sla_credit_percent=25.0,
        ),
        operational_profile=OperationalProfile(mttr_minutes=120.0),
        slo_targets=[SLOTarget(name="Availability", metric="availability", target=99.99)],
    ))

    # 99.99% SLO => allowed downtime = 43200 * 0.0001 = 4.32 minutes/month.
    # With mttr=120 minutes, downtime=120 >> 4.32 -> SLA breach.
    effects = [
        CascadeEffect(
            component_id="api",
            component_name="API Gateway",
            health=HealthStatus.DOWN,
            reason="Full outage",
        ),
    ]
    report = _build_report_with_effects(graph, effects)

    engine = CostImpactEngine(graph)
    cost_report = engine.analyze(report)

    impact = cost_report.impacts[0]
    # SLA penalty = monthly_revenue * sla_credit_percent / 100
    # monthly_revenue = 1000 * 43200 = 43,200,000
    # sla_penalty = 43,200,000 * 0.25 = 10,800,000
    assert impact.sla_penalty == 10_800_000.0
    assert impact.sla_penalty > 0


def test_recovery_cost_calculation():
    """Recovery cost should scale with engineer cost, MTTR, and engineer count."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="svc",
        name="Service",
        type=ComponentType.APP_SERVER,
        cost_profile=CostProfile(recovery_engineer_cost=250.0),
        operational_profile=OperationalProfile(mttr_minutes=60.0),
    ))

    effects = [
        CascadeEffect(
            component_id="svc",
            component_name="Service",
            health=HealthStatus.DOWN,
            reason="Service down",
        ),
    ]
    report = _build_report_with_effects(graph, effects)

    # Use 3 engineers.
    engine = CostImpactEngine(graph, num_engineers=3)
    cost_report = engine.analyze(report)

    impact = cost_report.impacts[0]
    # Recovery cost = 250 * (60/60) * 3 = 750
    assert impact.recovery_cost == 750.0


def test_annual_risk_calculation():
    """Annual risk should aggregate impact * annual probability."""
    graph = _build_graph_with_costs()

    effects = [
        CascadeEffect(
            component_id="app",
            component_name="App Server",
            health=HealthStatus.DOWN,
            reason="Failure",
        ),
    ]
    report = _build_report_with_effects(
        graph, effects, likelihood=0.5,
    )

    engine = CostImpactEngine(graph)
    cost_report = engine.analyze(report)

    assert cost_report.total_annual_risk > 0
    # Annual probability = min(1.0, 0.5) * 12 = 6.0
    # total_annual_risk = total_impact * 6.0
    impact = cost_report.impacts[0]
    expected_annual = impact.total_impact * 6.0
    assert abs(cost_report.total_annual_risk - expected_annual) < 0.01


def test_empty_graph():
    """Cost engine should handle an empty graph gracefully."""
    graph = InfraGraph()
    report = SimulationReport(
        results=[],
        resilience_score=10.0,
        total_generated=0,
    )

    engine = CostImpactEngine(graph)
    cost_report = engine.analyze(report)

    assert len(cost_report.impacts) == 0
    assert cost_report.total_annual_risk == 0.0
    assert cost_report.highest_impact_scenario == ""
    assert cost_report.summary != ""


def test_cost_profile_on_component():
    """CostProfile should be accessible on Component with defaults."""
    comp = Component(
        id="test",
        name="Test",
        type=ComponentType.APP_SERVER,
    )
    assert comp.cost_profile.hourly_infra_cost == 0.0
    assert comp.cost_profile.revenue_per_minute == 0.0
    assert comp.cost_profile.sla_credit_percent == 0.0
    assert comp.cost_profile.recovery_engineer_cost == 100.0


def test_cost_profile_custom_values():
    """CostProfile should accept custom values."""
    comp = Component(
        id="test",
        name="Test",
        type=ComponentType.APP_SERVER,
        cost_profile=CostProfile(
            hourly_infra_cost=50.0,
            revenue_per_minute=200.0,
            sla_credit_percent=10.0,
            recovery_engineer_cost=300.0,
        ),
    )
    assert comp.cost_profile.hourly_infra_cost == 50.0
    assert comp.cost_profile.revenue_per_minute == 200.0
    assert comp.cost_profile.sla_credit_percent == 10.0
    assert comp.cost_profile.recovery_engineer_cost == 300.0


def test_no_revenue_no_business_loss():
    """Components without revenue should contribute zero business loss."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="worker",
        name="Worker",
        type=ComponentType.APP_SERVER,
        cost_profile=CostProfile(revenue_per_minute=0.0),
        operational_profile=OperationalProfile(mttr_minutes=30.0),
    ))

    effects = [
        CascadeEffect(
            component_id="worker",
            component_name="Worker",
            health=HealthStatus.DOWN,
            reason="Worker down",
        ),
    ]
    report = _build_report_with_effects(graph, effects)

    engine = CostImpactEngine(graph)
    cost_report = engine.analyze(report)

    assert cost_report.impacts[0].business_loss == 0.0


def test_degraded_partial_business_loss():
    """Degraded components should incur partial (20%) business loss."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="api",
        name="API",
        type=ComponentType.APP_SERVER,
        cost_profile=CostProfile(revenue_per_minute=100.0),
        operational_profile=OperationalProfile(mttr_minutes=0.0),
    ))

    effects = [
        CascadeEffect(
            component_id="api",
            component_name="API",
            health=HealthStatus.DEGRADED,
            reason="Latency spike",
        ),
    ]
    report = _build_report_with_effects(graph, effects)

    engine = CostImpactEngine(graph)
    cost_report = engine.analyze(report)

    impact = cost_report.impacts[0]
    # No DOWN components -> fallback downtime = severity * 6.0
    # Degraded-only -> severity capped at 4.0 (single effect cap at 1.5)
    # Business loss = 100 * downtime * 0.2
    assert impact.business_loss > 0.0


def test_overloaded_half_business_loss():
    """Overloaded components should incur 50% business loss."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="api",
        name="API",
        type=ComponentType.APP_SERVER,
        cost_profile=CostProfile(revenue_per_minute=100.0),
        operational_profile=OperationalProfile(mttr_minutes=10.0),
    ))

    effects = [
        CascadeEffect(
            component_id="api",
            component_name="API",
            health=HealthStatus.OVERLOADED,
            reason="CPU saturated",
        ),
    ]
    report = _build_report_with_effects(graph, effects)

    engine = CostImpactEngine(graph)
    cost_report = engine.analyze(report)

    impact = cost_report.impacts[0]
    # mttr = 10 min, overloaded factor = 0.5
    # business_loss = 100 * 10 * 0.5 = 500
    assert impact.business_loss == 500.0


def test_full_simulation_integration():
    """Cost engine should work with a real SimulationEngine run."""
    graph = _build_graph_with_costs()

    sim_engine = SimulationEngine(graph)
    sim_report = sim_engine.run_all_defaults()

    cost_engine = CostImpactEngine(graph)
    cost_report = cost_engine.analyze(sim_report)

    # Should have impacts for all scenarios.
    assert len(cost_report.impacts) == len(sim_report.results)
    assert cost_report.total_annual_risk >= 0
    assert cost_report.summary != ""

    # Impacts should be sorted descending by total_impact.
    for i in range(len(cost_report.impacts) - 1):
        assert cost_report.impacts[i].total_impact >= cost_report.impacts[i + 1].total_impact


def test_highest_impact_scenario_name():
    """highest_impact_scenario should match the first (highest) entry."""
    graph = _build_graph_with_costs()

    effects = [
        CascadeEffect(
            component_id="db",
            component_name="Database",
            health=HealthStatus.DOWN,
            reason="DB crash",
        ),
    ]
    report = _build_report_with_effects(graph, effects, scenario_name="DB Failure")

    engine = CostImpactEngine(graph)
    cost_report = engine.analyze(report)

    assert cost_report.highest_impact_scenario == "DB Failure"
