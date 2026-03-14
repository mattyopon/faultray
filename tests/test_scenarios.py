"""Tests for scenario generation logic."""

from infrasim.model.components import Capacity, Component, ComponentType
from infrasim.simulator.scenarios import FaultType, generate_default_scenarios


def _make_components(n: int) -> dict[str, Component]:
    """Create N app_server components for testing."""
    comps = {}
    for i in range(n):
        comp = Component(
            id=f"app-{i}",
            name=f"App Server {i}",
            type=ComponentType.APP_SERVER,
        )
        comps[comp.id] = comp
    return comps


def _find_scenario(scenarios, scenario_id: str):
    """Find a scenario by its ID."""
    for s in scenarios:
        if s.id == scenario_id:
            return s
    return None


def test_rolling_restart_keeps_at_least_one_up():
    """Rolling restart failure must not bring down ALL app servers."""
    for n in range(2, 8):
        comps = _make_components(n)
        ids = list(comps.keys())
        scenarios = generate_default_scenarios(ids, components=comps)
        sc = _find_scenario(scenarios, "rolling-restart-fail")
        assert sc is not None, f"rolling-restart-fail missing for {n} app servers"

        faulted = len(sc.faults)
        # Must bring down at least 1, but never ALL
        assert faulted >= 1, f"Should fault >= 1, got {faulted} for {n} servers"
        assert faulted < n, (
            f"Rolling restart should keep at least 1 server up, "
            f"but faulted {faulted}/{n}"
        )


def test_rolling_restart_two_servers():
    """With exactly 2 app servers, only 1 should go down."""
    comps = _make_components(2)
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "rolling-restart-fail")
    assert sc is not None
    assert len(sc.faults) == 1, f"Expected 1 fault for 2 servers, got {len(sc.faults)}"


def test_rolling_restart_three_servers():
    """With 3 app servers, maxUnavailable=25% -> max(1, 3//4)=1 server down."""
    comps = _make_components(3)
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "rolling-restart-fail")
    assert sc is not None
    assert len(sc.faults) == 1, f"Expected 1 fault for 3 servers (maxUnavailable=25%), got {len(sc.faults)}"


def test_no_rolling_restart_with_one_server():
    """With only 1 app server, rolling restart scenario should not be generated."""
    comps = _make_components(1)
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)
    sc = _find_scenario(scenarios, "rolling-restart-fail")
    assert sc is None, "Should not generate rolling restart for single server"


def test_cascading_timeout_scenarios():
    """Category 29: Components with timeout_seconds > 0 should generate cascading timeout scenarios."""
    comps = {
        "db-1": Component(
            id="db-1", name="Database 1", type=ComponentType.DATABASE,
            capacity=Capacity(timeout_seconds=60.0),
        ),
        "app-1": Component(
            id="app-1", name="App Server 1", type=ComponentType.APP_SERVER,
            capacity=Capacity(timeout_seconds=30.0),
        ),
    }
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)

    # Both components have timeout_seconds > 0, so both should get a cascading timeout scenario
    sc_db = _find_scenario(scenarios, "cascading-timeout-db-1")
    sc_app = _find_scenario(scenarios, "cascading-timeout-app-1")
    assert sc_db is not None, "cascading-timeout-db-1 should be generated"
    assert sc_app is not None, "cascading-timeout-app-1 should be generated"

    # Verify the fault is a LATENCY_SPIKE with multiplier 20
    assert len(sc_db.faults) == 1
    assert sc_db.faults[0].fault_type == FaultType.LATENCY_SPIKE
    assert sc_db.faults[0].parameters.get("multiplier") == 20


def test_sustained_degradation_scenarios():
    """Category 30: Each app_server should get a sustained degradation scenario."""
    comps = _make_components(3)
    ids = list(comps.keys())
    scenarios = generate_default_scenarios(ids, components=comps)

    for i in range(3):
        sc = _find_scenario(scenarios, f"sustained-degradation-app-{i}")
        assert sc is not None, f"sustained-degradation-app-{i} should be generated"
        # Should have exactly 2 faults: CPU_SATURATION + MEMORY_EXHAUSTION
        assert len(sc.faults) == 2, f"Expected 2 faults, got {len(sc.faults)}"
        fault_types = {f.fault_type for f in sc.faults}
        assert FaultType.CPU_SATURATION in fault_types
        assert FaultType.MEMORY_EXHAUSTION in fault_types
        # Check severities
        for f in sc.faults:
            if f.fault_type == FaultType.CPU_SATURATION:
                assert f.severity == 0.8
            elif f.fault_type == FaultType.MEMORY_EXHAUSTION:
                assert f.severity == 0.7
