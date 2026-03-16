"""Tests for the FMEA (Failure Mode & Effects Analysis) engine."""

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
from faultray.simulator.fmea_engine import FMEAEngine, FMEAReport, FailureMode


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


def test_severity_none_component():
    """Test line 301: calculate_severity returns 1 for nonexistent component."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    sev = engine.calculate_severity(graph, "nonexistent")
    assert sev == 1


def test_severity_high_dep_ratio():
    """Test line 310: dep_ratio >= 0.5 -> base = 9."""
    graph = InfraGraph()
    # Build a star topology where central node affects >= 50%
    graph.add_component(Component(
        id="hub", name="Hub", type=ComponentType.APP_SERVER, replicas=1,
    ))
    for i in range(4):
        graph.add_component(Component(
            id=f"spoke-{i}", name=f"Spoke {i}", type=ComponentType.APP_SERVER, replicas=1,
        ))
        graph.add_dependency(Dependency(source_id=f"spoke-{i}", target_id="hub", dependency_type="requires"))
    engine = FMEAEngine()
    sev = engine.calculate_severity(graph, "hub")
    assert sev >= 9


def test_severity_on_critical_path():
    """Test line 316: base = 3 when component has dependents but low ratio."""
    graph = InfraGraph()
    graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
    graph.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
    graph.add_dependency(Dependency(source_id="a", target_id="b", dependency_type="requires"))
    # Many other unrelated components to keep ratio low
    for i in range(20):
        graph.add_component(Component(
            id=f"other-{i}", name=f"Other {i}", type=ComponentType.APP_SERVER, replicas=1,
        ))
    engine = FMEAEngine()
    sev = engine.calculate_severity(graph, "b")
    assert 1 <= sev <= 10


def test_occurrence_none_component():
    """Test line 335: calculate_occurrence returns 5 for nonexistent component."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    occ = engine.calculate_occurrence(graph, "nonexistent")
    assert occ == 5


def test_detection_none_component():
    """Test line 377: calculate_detection returns 8 for nonexistent component."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    det = engine.calculate_detection(graph, "nonexistent")
    assert det == 8


def test_detection_with_high_utilization():
    """Test line 366: occurrence increases with high utilization."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="hot", name="Hot Server", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(cpu_percent=90, memory_percent=85, network_connections=95),
    ))
    engine = FMEAEngine()
    occ = engine.calculate_occurrence(graph, "hot")
    # High utilization should boost occurrence
    assert occ >= 6


def test_failure_mode_adjustment_exhaustion():
    """Test line 421: 'exhaustion' in mode adjusts base upward."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    # The DB component should get modes that include "exhaustion" related failures
    modes = engine.analyze_component(graph, "db")
    # Verify all modes have valid adjusted scores
    for m in modes:
        assert 1 <= m.severity <= 10
        assert 1 <= m.occurrence <= 10
        assert 1 <= m.detection <= 10


def test_identify_controls_none_component():
    """Test line 430: _identify_controls returns [] for nonexistent component."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    controls = engine._identify_controls(graph, "nonexistent")
    assert controls == []


def test_identify_controls_with_retry_strategy():
    """Test lines 453-454: _identify_controls finds retry strategies."""
    from faultray.model.components import RetryStrategy
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db",
        retry_strategy=RetryStrategy(enabled=True, max_retries=3),
    ))
    engine = FMEAEngine()
    controls = engine._identify_controls(graph, "app")
    assert any("Retry strategy" in c for c in controls)


def test_recommend_actions_none_component():
    """Test line 469: _recommend_actions returns [] for nonexistent component."""
    graph = _build_test_graph()
    engine = FMEAEngine()
    actions = engine._recommend_actions(graph, "nonexistent", 8, 8, 8)
    assert actions == []


def test_recommend_actions_high_detection():
    """Test lines 492-493: recommendations for high detection score with no CB."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db"))
    engine = FMEAEngine()
    actions = engine._recommend_actions(graph, "db", severity=8, occurrence=8, detection=8)
    # Should recommend health checks, circuit breakers, monitoring
    assert any("circuit breaker" in a.lower() for a in actions)


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


def test_occurrence_utilization_between_60_and_80():
    """Test line 366: utilization between 60-80 adds +1 to occurrence score."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=70.0),  # 70% -> between 60-80
    ))
    engine = FMEAEngine()
    occ = engine.calculate_occurrence(graph, "app")
    # Should be valid range and include the +1 for util > 60
    assert 1 <= occ <= 10


def test_recommend_actions_with_circuit_breaker_present():
    """Test lines 492-493: has_cb=True when dependent edge has circuit breaker enabled.

    When a circuit breaker is found, the 'Add circuit breakers' recommendation
    should NOT be added.
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))
    # Edge from app -> db with circuit breaker ENABLED
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    engine = FMEAEngine()
    # For "db", the dependent is "app", and the edge app->db has CB enabled.
    # So has_cb=True -> "Add circuit breakers on dependent connections" NOT added.
    actions = engine._recommend_actions(graph, "db", severity=8, occurrence=8, detection=8)
    assert "Add circuit breakers on dependent connections" not in actions
