"""Tests for the Chaos Fuzzer (AFL-inspired infrastructure fuzzing)."""

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.chaos_fuzzer import ChaosFuzzer, FuzzReport, FuzzResult
from infrasim.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_test_graph() -> InfraGraph:
    """Build a simple 3-component test graph: lb -> app -> db."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=1, capacity=Capacity(max_connections=10000),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1, capacity=Capacity(max_connections=500, timeout_seconds=30),
        metrics=ResourceMetrics(network_connections=100),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1, capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=50, disk_percent=40),
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    return graph


def _build_large_graph(n: int = 10) -> InfraGraph:
    """Build a linear chain of N components."""
    graph = InfraGraph()
    for i in range(n):
        graph.add_component(Component(
            id=f"svc-{i}", name=f"Service {i}", type=ComponentType.APP_SERVER,
        ))
    for i in range(n - 1):
        graph.add_dependency(Dependency(
            source_id=f"svc-{i}", target_id=f"svc-{i+1}",
            dependency_type="requires",
        ))
    return graph


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fuzzer_returns_fuzz_report():
    """Fuzzer should return a FuzzReport dataclass."""
    graph = _build_test_graph()
    fuzzer = ChaosFuzzer(graph, seed=42)
    report = fuzzer.fuzz(iterations=10)

    assert isinstance(report, FuzzReport)
    assert report.total_iterations == 10


def test_fuzzer_finds_novel_failures():
    """With enough iterations, the fuzzer should discover at least one novel failure."""
    graph = _build_test_graph()
    fuzzer = ChaosFuzzer(graph, seed=42)
    report = fuzzer.fuzz(iterations=50)

    assert report.novel_failures_found > 0
    assert len(report.novel_scenarios) > 0


def test_fuzzer_deterministic_with_same_seed():
    """Same seed should produce identical results."""
    graph = _build_test_graph()

    fuzzer1 = ChaosFuzzer(graph, seed=123)
    report1 = fuzzer1.fuzz(iterations=30)

    fuzzer2 = ChaosFuzzer(graph, seed=123)
    report2 = fuzzer2.fuzz(iterations=30)

    assert report1.novel_failures_found == report2.novel_failures_found
    assert report1.highest_risk_score == report2.highest_risk_score
    assert report1.coverage == report2.coverage


def test_fuzzer_different_seeds_produce_different_results():
    """Different seeds should (very likely) produce different results."""
    graph = _build_test_graph()

    fuzzer1 = ChaosFuzzer(graph, seed=1)
    report1 = fuzzer1.fuzz(iterations=50)

    fuzzer2 = ChaosFuzzer(graph, seed=9999)
    report2 = fuzzer2.fuzz(iterations=50)

    # At least one of these should differ (with very high probability)
    differs = (
        report1.novel_failures_found != report2.novel_failures_found
        or report1.highest_risk_score != report2.highest_risk_score
        or report1.coverage != report2.coverage
    )
    assert differs, "Different seeds should produce different results"


def test_fuzzer_coverage():
    """Coverage should be between 0 and 1 and reflect actual component usage."""
    graph = _build_test_graph()
    fuzzer = ChaosFuzzer(graph, seed=42)
    report = fuzzer.fuzz(iterations=100)

    assert 0.0 <= report.coverage <= 1.0
    # With 3 components and 100 iterations, coverage should be high
    assert report.coverage > 0.5


def test_fuzzer_mutation_effectiveness_keys():
    """Mutation effectiveness should have entries for each mutation type used."""
    graph = _build_test_graph()
    fuzzer = ChaosFuzzer(graph, seed=42)
    report = fuzzer.fuzz(iterations=100)

    # At least some mutation types should appear
    assert len(report.mutation_effectiveness) > 0
    # All keys should be valid mutation types
    for key in report.mutation_effectiveness:
        assert key in ChaosFuzzer.MUTATION_TYPES


def test_fuzzer_novel_scenarios_sorted_by_risk():
    """Novel scenarios should be sorted by risk score descending."""
    graph = _build_test_graph()
    fuzzer = ChaosFuzzer(graph, seed=42)
    report = fuzzer.fuzz(iterations=100)

    if len(report.novel_scenarios) >= 2:
        for i in range(len(report.novel_scenarios) - 1):
            assert (
                report.novel_scenarios[i].risk_score
                >= report.novel_scenarios[i + 1].risk_score
            )


def test_fuzzer_novel_scenarios_capped_at_20():
    """At most 20 novel scenarios should be returned."""
    graph = _build_large_graph(20)
    fuzzer = ChaosFuzzer(graph, seed=42)
    report = fuzzer.fuzz(iterations=500)

    assert len(report.novel_scenarios) <= 20


def test_fuzzer_with_base_scenarios():
    """Fuzzer should accept user-supplied base scenarios."""
    graph = _build_test_graph()

    base = [
        Scenario(
            id="custom-1", name="Custom base", description="User scenario",
            faults=[Fault(
                target_component_id="db",
                fault_type=FaultType.DISK_FULL,
            )],
        ),
    ]

    fuzzer = ChaosFuzzer(graph, seed=42)
    report = fuzzer.fuzz(iterations=30, base_scenarios=base)

    assert isinstance(report, FuzzReport)
    assert report.total_iterations == 30


def test_fuzzer_empty_graph():
    """Fuzzer should handle an empty graph gracefully."""
    graph = InfraGraph()
    fuzzer = ChaosFuzzer(graph, seed=42)
    report = fuzzer.fuzz(iterations=10)

    assert report.total_iterations == 10
    assert report.novel_failures_found == 0
    assert report.highest_risk_score == 0.0
    assert report.coverage == 0.0


def test_fuzzer_single_component():
    """Fuzzer should work with a single-component graph."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="single", name="Single", type=ComponentType.APP_SERVER,
    ))

    fuzzer = ChaosFuzzer(graph, seed=42)
    report = fuzzer.fuzz(iterations=20)

    assert report.total_iterations == 20
    assert report.coverage == 1.0  # only one component, must be covered


def test_fuzz_result_dataclass():
    """FuzzResult should carry the correct fields."""
    scenario = Scenario(
        id="test", name="Test", description="Test",
        faults=[Fault(
            target_component_id="app",
            fault_type=FaultType.COMPONENT_DOWN,
        )],
    )
    result = FuzzResult(
        iteration=0,
        scenario=scenario,
        risk_score=5.0,
        is_novel=True,
        mutation_type="add_fault",
    )
    assert result.iteration == 0
    assert result.risk_score == 5.0
    assert result.is_novel is True
    assert result.mutation_type == "add_fault"


def test_fuzzer_highest_risk_score_nonnegative():
    """Highest risk score should always be non-negative."""
    graph = _build_test_graph()
    fuzzer = ChaosFuzzer(graph, seed=42)
    report = fuzzer.fuzz(iterations=50)

    assert report.highest_risk_score >= 0.0
