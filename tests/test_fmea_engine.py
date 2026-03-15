"""Tests for the FMEA (Failure Mode & Effects Analysis) engine."""

from infrasim.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.fmea_engine import FMEAEngine, FMEAReport, FailureMode


def _build_test_graph() -> InfraGraph:
    """Build a multi-tier test infrastructure graph."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        capacity=Capacity(max_connections=10000),
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(max_connections=500, timeout_seconds=30),
        metrics=ResourceMetrics(cpu_percent=60, memory_percent=55, network_connections=200),
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
    graph.add_component(Component(
        id="queue", name="Message Queue", type=ComponentType.QUEUE,
        replicas=1,
        capacity=Capacity(max_connections=500),
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))
    graph.add_dependency(Dependency(source_id="app", target_id="queue", dependency_type="async"))

    return graph


def test_analyze_returns_report():
    """Full analysis returns an FMEAReport with failure modes."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    report = engine.analyze(graph)

    assert isinstance(report, FMEAReport)
    assert len(report.failure_modes) > 0
    assert report.total_rpn > 0
    assert report.average_rpn > 0


def test_analyze_component_returns_modes():
    """Single component analysis returns failure modes for that component."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    modes = engine.analyze_component(graph, "db")

    assert len(modes) > 0
    for m in modes:
        assert isinstance(m, FailureMode)
        assert m.component_id == "db"
        assert m.component_name == "Database"
        assert 1 <= m.severity <= 10
        assert 1 <= m.occurrence <= 10
        assert 1 <= m.detection <= 10
        assert m.rpn == m.severity * m.occurrence * m.detection


def test_analyze_nonexistent_component():
    """Analyzing a non-existent component returns empty list."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    modes = engine.analyze_component(graph, "does-not-exist")
    assert modes == []


def test_severity_reflects_dependents():
    """Components with more dependents should have higher severity."""
    graph = _build_test_graph()
    engine = FMEAEngine()

    # db is depended on by app which is depended on by lb
    sev_db = engine.calculate_severity(graph, "db")
    # queue is only depended on by app (async)
    sev_queue = engine.calculate_severity(graph, "queue")

    # db affects more of the system
    assert sev_db >= sev_queue


def test_occurrence_lower_with_replicas():
    """Components with replicas should have lower occurrence score."""
    graph = _build_test_graph()
    engine = FMEAEngine()

    # lb has replicas=2, app has replicas=1
    occ_lb = engine.calculate_occurrence(graph, "lb")
    occ_app = engine.calculate_occurrence(graph, "app")

    # lb should have lower occurrence since it has replicas
    assert occ_lb <= occ_app


def test_detection_lower_with_health_checks():
    """Components with health checks should have lower detection score."""
    graph = _build_test_graph()
    engine = FMEAEngine()

    # lb has failover+health checks enabled
    det_lb = engine.calculate_detection(graph, "lb")
    # queue has nothing
    det_queue = engine.calculate_detection(graph, "queue")

    assert det_lb < det_queue


def test_rpn_calculation():
    """RPN should be S * O * D."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    modes = engine.analyze_component(graph, "app")

    for m in modes:
        assert m.rpn == m.severity * m.occurrence * m.detection


def test_risk_categorization():
    """Report should correctly categorize high/medium/low risk."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    report = engine.analyze(graph)

    high = sum(1 for fm in report.failure_modes if fm.rpn > 200)
    medium = sum(1 for fm in report.failure_modes if 100 < fm.rpn <= 200)
    low = sum(1 for fm in report.failure_modes if fm.rpn <= 100)

    assert report.high_risk_count == high
    assert report.medium_risk_count == medium
    assert report.low_risk_count == low


def test_top_risks_sorted():
    """Top risks should be sorted by RPN descending."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    report = engine.analyze(graph)

    rpns = [fm.rpn for fm in report.top_risks]
    assert rpns == sorted(rpns, reverse=True)


def test_rpn_by_component():
    """RPN by component should aggregate correctly."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    report = engine.analyze(graph)

    for comp_id, total_rpn in report.rpn_by_component.items():
        expected = sum(fm.rpn for fm in report.failure_modes if fm.component_id == comp_id)
        assert total_rpn == expected


def test_controls_identified():
    """Existing controls should be identified for protected components."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    modes = engine.analyze_component(graph, "lb")

    # lb has replicas and failover
    any_controls = any(len(m.current_controls) > 0 for m in modes)
    assert any_controls


def test_recommendations_for_unprotected():
    """Unprotected components should get improvement recommendations."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    modes = engine.analyze_component(graph, "db")

    # db has no failover, no autoscaling, single replica
    any_actions = any(len(m.recommended_actions) > 0 for m in modes)
    assert any_actions


def test_spreadsheet_format():
    """Spreadsheet export should return a list of dicts."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    report = engine.analyze(graph)
    rows = engine.to_spreadsheet_format(report)

    assert len(rows) == len(report.failure_modes)
    for row in rows:
        assert "Component" in row
        assert "RPN" in row
        assert "Severity (S)" in row
        assert isinstance(row["RPN"], int)


def test_failure_mode_types_correct():
    """Each component type should get the correct failure mode catalogue."""
    graph = _build_test_graph()
    engine = FMEAEngine()

    # Database should get database-specific modes
    db_modes = engine.analyze_component(graph, "db")
    db_mode_names = {m.mode for m in db_modes}
    assert "Primary failure" in db_mode_names or "Replication lag" in db_mode_names

    # Cache should get cache-specific modes
    cache_modes = engine.analyze_component(graph, "cache")
    cache_mode_names = {m.mode for m in cache_modes}
    assert "Cache eviction storm (thundering herd)" in cache_mode_names or "Data inconsistency (stale cache)" in cache_mode_names

    # Queue should get queue-specific modes
    queue_modes = engine.analyze_component(graph, "queue")
    queue_mode_names = {m.mode for m in queue_modes}
    assert "Queue depth overflow (backpressure)" in queue_mode_names or "Consumer lag" in queue_mode_names


def test_empty_graph():
    """Analyzing an empty graph should return empty report."""
    graph = InfraGraph()
    engine = FMEAEngine()
    report = engine.analyze(graph)

    assert report.total_rpn == 0
    assert report.average_rpn == 0.0
    assert len(report.failure_modes) == 0


def test_improvement_priority_order():
    """Improvement priority should list highest-RPN actions first."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    report = engine.analyze(graph)

    if len(report.improvement_priority) >= 2:
        rpns = [item[2] for item in report.improvement_priority]
        # Should be in descending order (highest RPN first)
        assert rpns == sorted(rpns, reverse=True)


def test_well_protected_component_has_lower_rpn():
    """A component with replicas + failover + autoscaling should have lower RPN."""
    graph = InfraGraph()

    # Well-protected component
    graph.add_component(Component(
        id="protected", name="Protected", type=ComponentType.APP_SERVER,
        replicas=3,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        metrics=ResourceMetrics(cpu_percent=30, memory_percent=25),
    ))

    # Unprotected component
    graph.add_component(Component(
        id="unprotected", name="Unprotected", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=85, memory_percent=80),
    ))

    engine = FMEAEngine()
    protected_modes = engine.analyze_component(graph, "protected")
    unprotected_modes = engine.analyze_component(graph, "unprotected")

    avg_rpn_protected = sum(m.rpn for m in protected_modes) / len(protected_modes)
    avg_rpn_unprotected = sum(m.rpn for m in unprotected_modes) / len(unprotected_modes)

    assert avg_rpn_protected < avg_rpn_unprotected


def test_reproducible_results():
    """FMEA analysis should produce identical results across runs."""
    graph = _build_test_graph()
    engine = FMEAEngine()

    report1 = engine.analyze(graph)
    report2 = engine.analyze(graph)

    assert report1.total_rpn == report2.total_rpn
    assert report1.average_rpn == report2.average_rpn
    assert len(report1.failure_modes) == len(report2.failure_modes)

    for fm1, fm2 in zip(report1.failure_modes, report2.failure_modes):
        assert fm1.rpn == fm2.rpn
        assert fm1.severity == fm2.severity
        assert fm1.occurrence == fm2.occurrence
        assert fm1.detection == fm2.detection
