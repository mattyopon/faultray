"""Tests for the SLO Budget Simulator."""

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    OperationalProfile,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine, SimulationReport
from faultray.simulator.scenarios import Fault, FaultType, Scenario
from faultray.simulator.slo_budget import BudgetSimulation, SLOBudgetSimulator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_test_graph() -> InfraGraph:
    """Build a 3-component graph: lb -> app -> db."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=1, capacity=Capacity(max_connections=10000),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(max_connections=500, timeout_seconds=30),
        metrics=ResourceMetrics(network_connections=100),
        operational_profile=OperationalProfile(mttr_minutes=15),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=50, disk_percent=40),
        operational_profile=OperationalProfile(mttr_minutes=30),
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    return graph


def _run_default_simulation(graph: InfraGraph) -> SimulationReport:
    """Run default scenarios and return the report."""
    engine = SimulationEngine(graph)
    return engine.run_all_defaults(include_feed=False, include_plugins=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_budget_simulation_returns_dataclass():
    """simulate() should return a BudgetSimulation."""
    graph = _build_test_graph()
    report = _run_default_simulation(graph)
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    result = simulator.simulate(report)

    assert isinstance(result, BudgetSimulation)


def test_budget_total_calculation():
    """Budget total should match the formula: (1 - slo/100) * days * 24 * 60."""
    graph = _build_test_graph()
    report = _run_default_simulation(graph)
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    result = simulator.simulate(report)

    expected_total = (1 - 99.9 / 100) * 30 * 24 * 60  # 43.2 minutes
    assert abs(result.budget_total_minutes - expected_total) < 0.1


def test_budget_remaining_with_consumption():
    """Remaining budget should decrease as consumed minutes increase."""
    graph = _build_test_graph()
    report = _run_default_simulation(graph)
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    result0 = simulator.simulate(report, current_consumed_minutes=0)
    result10 = simulator.simulate(report, current_consumed_minutes=10)

    assert (
        result0.current_budget_remaining_minutes
        > result10.current_budget_remaining_minutes
    )
    diff = (
        result0.current_budget_remaining_minutes
        - result10.current_budget_remaining_minutes
    )
    assert abs(diff - 10.0) < 0.1


def test_risk_appetite_aggressive():
    """With most budget remaining, risk appetite should be aggressive."""
    graph = _build_test_graph()
    report = _run_default_simulation(graph)
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    result = simulator.simulate(report, current_consumed_minutes=0)

    assert result.risk_appetite == "aggressive"


def test_risk_appetite_conservative():
    """With most budget consumed, risk appetite should be conservative."""
    graph = _build_test_graph()
    report = _run_default_simulation(graph)
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    # Total budget is ~43.2 min. Consuming 40 leaves only ~3.2 = ~7.4%
    result = simulator.simulate(report, current_consumed_minutes=40)

    assert result.risk_appetite == "conservative"


def test_risk_appetite_moderate():
    """With about half the budget consumed, risk appetite should be moderate."""
    graph = _build_test_graph()
    report = _run_default_simulation(graph)
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    # Total budget is ~43.2 min. Consuming 25 leaves ~18.2 = ~42%
    result = simulator.simulate(report, current_consumed_minutes=25)

    assert result.risk_appetite == "moderate"


def test_scenarios_classified():
    """All scenarios should be classified as either safe or unsafe."""
    graph = _build_test_graph()
    report = _run_default_simulation(graph)
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    result = simulator.simulate(report)

    total_classified = (
        len(result.scenarios_within_budget)
        + len(result.scenarios_exceeding_budget)
    )
    assert total_classified == len(report.results)


def test_high_consumption_more_unsafe():
    """Higher consumption should lead to more unsafe scenarios."""
    graph = _build_test_graph()
    report = _run_default_simulation(graph)
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    result_low = simulator.simulate(report, current_consumed_minutes=0)
    result_high = simulator.simulate(report, current_consumed_minutes=42)

    assert (
        len(result_high.scenarios_exceeding_budget)
        >= len(result_low.scenarios_exceeding_budget)
    )


def test_slo_target_stored():
    """BudgetSimulation should store the SLO target."""
    graph = _build_test_graph()
    report = _run_default_simulation(graph)
    simulator = SLOBudgetSimulator(graph, slo_target=99.95, window_days=7)

    result = simulator.simulate(report)

    assert result.slo_target == 99.95
    assert result.window_days == 7


def test_max_safe_blast_radius_range():
    """Max safe blast radius should be between 0 and 1."""
    graph = _build_test_graph()
    report = _run_default_simulation(graph)
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    result = simulator.simulate(report)

    assert 0.0 <= result.max_safe_blast_radius <= 1.0


def test_scenario_details_populated():
    """Scenario details list should be populated with correct keys."""
    graph = _build_test_graph()
    report = _run_default_simulation(graph)
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    result = simulator.simulate(report)

    assert len(result.scenario_details) == len(report.results)
    for detail in result.scenario_details:
        assert "scenario_name" in detail
        assert "risk_score" in detail
        assert "estimated_downtime_minutes" in detail
        assert "blast_radius" in detail
        assert "within_budget" in detail


def test_simulate_from_scenarios():
    """simulate_from_scenarios should run scenarios and evaluate budget."""
    graph = _build_test_graph()
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    scenarios = [
        Scenario(
            id="s1", name="DB Down", description="Test",
            faults=[Fault(
                target_component_id="db",
                fault_type=FaultType.COMPONENT_DOWN,
            )],
        ),
    ]

    result = simulator.simulate_from_scenarios(scenarios)

    assert isinstance(result, BudgetSimulation)
    total_classified = (
        len(result.scenarios_within_budget)
        + len(result.scenarios_exceeding_budget)
    )
    assert total_classified == 1


def test_stricter_slo_gives_less_budget():
    """A stricter SLO (e.g. 99.99) should give less total budget."""
    graph = _build_test_graph()
    report = _run_default_simulation(graph)

    sim_999 = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)
    sim_9999 = SLOBudgetSimulator(graph, slo_target=99.99, window_days=30)

    result_999 = sim_999.simulate(report)
    result_9999 = sim_9999.simulate(report)

    assert result_999.budget_total_minutes > result_9999.budget_total_minutes


def test_estimate_downtime_no_effects():
    """Scenario with no cascade effects should estimate 0 downtime."""
    graph = _build_test_graph()
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)
    from faultray.simulator.engine import ScenarioResult
    from faultray.simulator.cascade import CascadeChain

    scenario = Scenario(
        id="s-noeffect", name="No Effect", description="Nothing",
        faults=[],
    )
    cascade = CascadeChain(
        trigger="No Effect", effects=[], total_components=3,
    )
    result = ScenarioResult(scenario=scenario, cascade=cascade, risk_score=0.0)
    assert simulator._estimate_downtime(result) == 0.0


def test_estimate_downtime_degraded_only():
    """Scenario with only degraded effects should return fractional downtime."""
    from faultray.model.components import HealthStatus
    from faultray.simulator.cascade import CascadeChain, CascadeEffect
    from faultray.simulator.engine import ScenarioResult

    graph = _build_test_graph()
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    scenario = Scenario(
        id="s-deg", name="Degraded", description="Degraded only",
        faults=[Fault(target_component_id="app", fault_type=FaultType.LATENCY_SPIKE)],
    )
    effects = [
        CascadeEffect(
            component_id="app", component_name="App",
            health=HealthStatus.DEGRADED, reason="Latency spike",
        ),
    ]
    cascade = CascadeChain(
        trigger="Degraded", effects=effects, total_components=3,
    )
    result = ScenarioResult(scenario=scenario, cascade=cascade, risk_score=3.0)
    downtime = simulator._estimate_downtime(result)
    assert downtime == 1.0  # 1 degraded component * 1.0 min


def test_estimate_downtime_down_component_no_mttr():
    """DOWN component with zero MTTR should fallback to 30.0 min default."""
    from faultray.model.components import HealthStatus
    from faultray.simulator.cascade import CascadeChain, CascadeEffect
    from faultray.simulator.engine import ScenarioResult

    graph = InfraGraph()
    graph.add_component(Component(
        id="svc", name="Service", type=ComponentType.APP_SERVER,
        replicas=1,
        operational_profile=OperationalProfile(mttr_minutes=0),
    ))

    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)
    scenario = Scenario(
        id="s-down", name="Down", description="Down",
        faults=[Fault(target_component_id="svc", fault_type=FaultType.COMPONENT_DOWN)],
    )
    effects = [
        CascadeEffect(
            component_id="svc", component_name="Service",
            health=HealthStatus.DOWN, reason="Down",
        ),
    ]
    cascade = CascadeChain(
        trigger="Down", effects=effects, total_components=1,
    )
    result = ScenarioResult(scenario=scenario, cascade=cascade, risk_score=5.0)
    downtime = simulator._estimate_downtime(result)
    # Default MTTR=30 * severity_factor=min(5/10, 1.0)=0.5 -> 15.0
    assert downtime > 0


def test_estimate_downtime_unknown_component():
    """DOWN effect for unknown component should use default 30.0 MTTR."""
    from faultray.model.components import HealthStatus
    from faultray.simulator.cascade import CascadeChain, CascadeEffect
    from faultray.simulator.engine import ScenarioResult

    graph = _build_test_graph()
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)

    scenario = Scenario(
        id="s-unk", name="Unknown", description="Unknown",
        faults=[],
    )
    effects = [
        CascadeEffect(
            component_id="nonexistent", component_name="Ghost",
            health=HealthStatus.DOWN, reason="Down",
        ),
    ]
    cascade = CascadeChain(
        trigger="Unknown", effects=effects, total_components=3,
    )
    result = ScenarioResult(scenario=scenario, cascade=cascade, risk_score=8.0)
    downtime = simulator._estimate_downtime(result)
    assert downtime > 0  # Should use default 30.0 * severity_factor


def test_classify_appetite_zero_budget():
    """Zero budget total should return conservative."""
    graph = _build_test_graph()
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)
    assert simulator._classify_appetite(0.0, 0.0) == "conservative"


def test_max_safe_blast_method():
    """_max_safe_blast should scale with remaining budget."""
    graph = _build_test_graph()
    simulator = SLOBudgetSimulator(graph, slo_target=99.9, window_days=30)
    assert simulator._max_safe_blast(0.0) == 0.0
    assert simulator._max_safe_blast(43.2) == 1.0
    assert 0.0 < simulator._max_safe_blast(20.0) < 1.0
