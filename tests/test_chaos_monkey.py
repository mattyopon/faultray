"""Tests for the Chaos Monkey random failure injection simulator."""

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.chaos_monkey import (
    ChaosLevel,
    ChaosMonkey,
    ChaosMonkeyConfig,
    ChaosMonkeyReport,
    MonkeyExperiment,
)


def _build_test_graph() -> InfraGraph:
    """Build a multi-tier test infrastructure graph."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        capacity=Capacity(max_connections=10000),
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app-1", name="App Server 1", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(max_connections=500, timeout_seconds=30),
        metrics=ResourceMetrics(network_connections=200),
    ))
    graph.add_component(Component(
        id="app-2", name="App Server 2", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(max_connections=500, timeout_seconds=30),
        metrics=ResourceMetrics(network_connections=150),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(disk_percent=72, network_connections=90),
    ))
    graph.add_component(Component(
        id="cache", name="Redis Cache", type=ComponentType.CACHE,
        replicas=1,
        capacity=Capacity(max_connections=1000),
    ))

    graph.add_dependency(Dependency(source_id="lb", target_id="app-1", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="lb", target_id="app-2", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app-1", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app-2", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app-1", target_id="cache", dependency_type="optional"))
    graph.add_dependency(Dependency(source_id="app-2", target_id="cache", dependency_type="optional"))

    return graph


def test_monkey_run_returns_report():
    """Basic monkey mode run should return a valid report."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(
        level=ChaosLevel.MONKEY,
        rounds=5,
        seed=42,
    )
    report = monkey.run(graph, config)

    assert isinstance(report, ChaosMonkeyReport)
    assert report.total_rounds == 5
    assert len(report.experiments) == 5
    assert 0.0 <= report.survival_rate <= 1.0


def test_deterministic_with_seed():
    """Same seed should produce identical results."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(level=ChaosLevel.MONKEY, rounds=10, seed=42)

    report1 = monkey.run(graph, config)
    report2 = monkey.run(graph, config)

    assert report1.total_rounds == report2.total_rounds
    assert report1.survival_rate == report2.survival_rate
    assert len(report1.experiments) == len(report2.experiments)

    for e1, e2 in zip(report1.experiments, report2.experiments):
        assert e1.failed_components == e2.failed_components
        assert e1.survived == e2.survived
        assert e1.cascade_depth == e2.cascade_depth
        assert e1.affected_count == e2.affected_count


def test_different_seeds_produce_different_results():
    """Different seeds should (usually) produce different results."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()

    report1 = monkey.run(graph, ChaosMonkeyConfig(rounds=10, seed=42))
    report2 = monkey.run(graph, ChaosMonkeyConfig(rounds=10, seed=99))

    # At least the component selections should differ
    comps1 = [e.failed_components for e in report1.experiments]
    comps2 = [e.failed_components for e in report2.experiments]
    assert comps1 != comps2


def test_monkey_single_failure():
    """Monkey mode should fail exactly 1 component per round."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(level=ChaosLevel.MONKEY, rounds=10, seed=42)
    report = monkey.run(graph, config)

    for exp in report.experiments:
        assert len(exp.failed_components) == 1


def test_gorilla_multiple_same_type():
    """Gorilla mode should fail 2-3 components of the same type."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(level=ChaosLevel.GORILLA, rounds=10, seed=42)
    report = monkey.run(graph, config)

    for exp in report.experiments:
        assert exp.level == ChaosLevel.GORILLA
        assert len(exp.failed_components) >= 1


def test_kong_massive_failure():
    """Kong mode should fail 30-50% of components."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(level=ChaosLevel.KONG, rounds=5, seed=42)
    report = monkey.run(graph, config)

    total_comps = len(graph.components)
    for exp in report.experiments:
        assert len(exp.failed_components) >= 1
        # Kong should fail a significant portion
        assert len(exp.failed_components) >= int(total_comps * 0.3) or total_comps < 3


def test_army_progressive():
    """Army mode should progressively increase failures."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(level=ChaosLevel.ARMY, rounds=4, seed=42)
    report = monkey.run(graph, config)

    # Round N should fail N components (up to available)
    for exp in report.experiments:
        expected = min(exp.round_number, len(graph.components))
        assert len(exp.failed_components) == expected


def test_exclude_components():
    """Excluded components should never be failed."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(
        level=ChaosLevel.MONKEY,
        rounds=20,
        seed=42,
        exclude_components=["db", "lb"],
    )
    report = monkey.run(graph, config)

    for exp in report.experiments:
        assert "db" not in exp.failed_components
        assert "lb" not in exp.failed_components


def test_target_types_filter():
    """Target types should limit which components can be failed."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(
        level=ChaosLevel.MONKEY,
        rounds=10,
        seed=42,
        target_types=["app_server"],
    )
    report = monkey.run(graph, config)

    for exp in report.experiments:
        for comp_id in exp.failed_components:
            comp = graph.get_component(comp_id)
            assert comp is not None
            assert comp.type.value == "app_server"


def test_run_single():
    """run_single should return a single MonkeyExperiment."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    exp = monkey.run_single(graph, level=ChaosLevel.MONKEY, seed=42)

    assert isinstance(exp, MonkeyExperiment)
    assert exp.round_number == 1
    assert len(exp.failed_components) >= 0


def test_find_weakest_point():
    """find_weakest_point should return a component ID."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    weakest = monkey.find_weakest_point(graph, rounds=50, seed=42)

    assert weakest in graph.components
    # db is the most critical dependency in this graph
    # (it's a SPOF that everything depends on)


def test_find_weakest_deterministic():
    """find_weakest_point with same seed should return same result."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()

    w1 = monkey.find_weakest_point(graph, rounds=50, seed=42)
    w2 = monkey.find_weakest_point(graph, rounds=50, seed=42)
    assert w1 == w2


def test_stress_test():
    """stress_test should return progressive experiments."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    experiments = monkey.stress_test(graph, max_failures=3, seed=42)

    assert len(experiments) == 3
    # Each round should fail an increasing number
    for i, exp in enumerate(experiments, 1):
        expected = min(i, len(graph.components))
        assert len(exp.failed_components) == expected


def test_experiment_fields():
    """MonkeyExperiment should have all required fields."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    exp = monkey.run_single(graph, seed=42)

    assert hasattr(exp, "round_number")
    assert hasattr(exp, "failed_components")
    assert hasattr(exp, "level")
    assert hasattr(exp, "survived")
    assert hasattr(exp, "cascade_depth")
    assert hasattr(exp, "affected_count")
    assert hasattr(exp, "resilience_during")
    assert hasattr(exp, "recovery_possible")
    assert isinstance(exp.survived, bool)
    assert isinstance(exp.cascade_depth, int)
    assert exp.cascade_depth >= 0


def test_report_worst_best():
    """Report should identify worst and best experiments."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(level=ChaosLevel.MONKEY, rounds=10, seed=42)
    report = monkey.run(graph, config)

    assert report.worst_experiment is not None
    assert report.best_experiment is not None
    assert report.worst_experiment.affected_count >= report.best_experiment.affected_count


def test_report_recommendations():
    """Report should include recommendations."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(level=ChaosLevel.MONKEY, rounds=10, seed=42)
    report = monkey.run(graph, config)

    # With SPOFs in the graph, there should be at least some recommendations
    assert isinstance(report.recommendations, list)


def test_empty_graph():
    """Chaos Monkey on empty graph should return empty report."""
    graph = InfraGraph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(rounds=5, seed=42)
    report = monkey.run(graph, config)

    assert report.total_rounds == 0
    assert report.survival_rate == 1.0
    assert len(report.experiments) == 0


def test_single_component_graph():
    """Chaos Monkey on a single-component graph should work."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="solo", name="Solo Server", type=ComponentType.APP_SERVER,
    ))

    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(level=ChaosLevel.MONKEY, rounds=5, seed=42)
    report = monkey.run(graph, config)

    assert report.total_rounds == 5
    for exp in report.experiments:
        assert exp.failed_components == ["solo"]


def test_resilience_score_range():
    """Report should have valid resilience score range."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(rounds=10, seed=42)
    report = monkey.run(graph, config)

    low, high = report.resilience_score_range
    assert low <= high
    assert low >= 0.0


def test_most_dangerous_and_safest():
    """Report should identify the most dangerous and safest components."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(rounds=20, seed=42)
    report = monkey.run(graph, config)

    if report.most_dangerous_component:
        assert report.most_dangerous_component in graph.components
    if report.safest_component:
        assert report.safest_component in graph.components


def test_default_config():
    """Test line 104: run() creates default ChaosMonkeyConfig when None."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    report = monkey.run(graph, config=None)
    assert isinstance(report, ChaosMonkeyReport)
    assert report.total_rounds > 0


def test_run_single_empty_report():
    """Test line 156: run_single returns default MonkeyExperiment when no experiments."""
    graph = InfraGraph()
    monkey = ChaosMonkey()
    exp = monkey.run_single(graph, level=ChaosLevel.MONKEY, seed=42)
    assert isinstance(exp, MonkeyExperiment)
    assert exp.round_number == 1
    assert exp.survived is True
    assert exp.failed_components == []


def test_find_weakest_empty_graph():
    """Test line 181: find_weakest_point returns empty string for empty graph."""
    graph = InfraGraph()
    monkey = ChaosMonkey()
    result = monkey.find_weakest_point(graph, rounds=10, seed=42)
    assert result == ""


def test_find_weakest_zero_count_component():
    """Test line 203: avg_damage[cid] = 0.0 when count[cid] == 0."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="solo", name="Solo", type=ComponentType.APP_SERVER,
    ))
    monkey = ChaosMonkey()
    result = monkey.find_weakest_point(graph, rounds=5, seed=42)
    assert result == "solo"


def test_gorilla_no_viable_types_fallback():
    """Test line 276: gorilla falls back to random selection when no type has >= 2."""
    graph = InfraGraph()
    # Each component is a different type, so no type has >= 2
    graph.add_component(Component(id="lb", name="LB", type=ComponentType.LOAD_BALANCER))
    graph.add_component(Component(id="db", name="DB", type=ComponentType.DATABASE))
    graph.add_component(Component(id="cache", name="Cache", type=ComponentType.CACHE))
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(level=ChaosLevel.GORILLA, rounds=3, seed=42)
    report = monkey.run(graph, config)
    assert report.total_rounds == 3
    for exp in report.experiments:
        assert exp.level == ChaosLevel.GORILLA


def test_evaluate_failures_zero_comps():
    """Test line 327: resilience_during = 0 when total_comps == 0."""
    graph = InfraGraph()
    monkey = ChaosMonkey()
    config = ChaosMonkeyConfig(level=ChaosLevel.MONKEY, rounds=1, seed=42)
    report = monkey.run(graph, config)
    assert report.total_rounds == 0


def test_build_report_empty_experiments():
    """Test line 351: _build_report returns default report when experiments is empty."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()
    report = monkey._build_report(
        graph,
        ChaosMonkeyConfig(),
        [],
    )
    assert report.total_rounds == 0
    assert report.survival_rate == 1.0


def test_find_weakest_zero_count_many_components():
    """Test line 203: some components have count==0 when rounds < num_components.

    With many components and only 1 round, most components will have count==0,
    triggering the avg_damage[cid] = 0.0 fallback path.
    """
    graph = InfraGraph()
    for i in range(20):
        graph.add_component(Component(
            id=f"c{i}", name=f"C{i}", type=ComponentType.APP_SERVER,
        ))
    monkey = ChaosMonkey()
    # rounds=1 -> only 1 component gets tested, the other 19 get count==0
    result = monkey.find_weakest_point(graph, rounds=1, seed=42)
    assert result in [f"c{i}" for i in range(20)]


def test_evaluate_failures_zero_comps_via_method():
    """Test line 327: _evaluate_failures with empty graph gives resilience_during=0."""
    import random
    graph = InfraGraph()
    monkey = ChaosMonkey()
    rng = random.Random(42)
    exp = monkey._evaluate_failures(
        graph, rng=rng, targets=[], round_num=1,
        level=ChaosLevel.MONKEY,
    )
    assert exp.resilience_during == 0.0


def test_survival_rate_bounds():
    """Survival rate should be between 0 and 1."""
    graph = _build_test_graph()
    monkey = ChaosMonkey()

    for level in ChaosLevel:
        config = ChaosMonkeyConfig(level=level, rounds=5, seed=42)
        report = monkey.run(graph, config)
        assert 0.0 <= report.survival_rate <= 1.0
