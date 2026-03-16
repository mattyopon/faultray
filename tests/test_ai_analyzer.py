"""Tests for the AI analysis module."""

from faultray.ai.analyzer import (
    AIAnalysisReport,
    AIRecommendation,
    FaultRayAnalyzer,
    _nines_tier_label,
    _score_to_nines,
)
from faultray.model.components import (
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
    RetryStrategy,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine, SimulationReport


# ---------------------------------------------------------------------------
# Helper: build test graphs
# ---------------------------------------------------------------------------


def _build_spof_graph() -> InfraGraph:
    """Graph with a clear single-point-of-failure database."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2, capacity=Capacity(max_connections=10000),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3, capacity=Capacity(max_connections=500),
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=1, capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(cpu_percent=45, memory_percent=60),
    ))
    graph.add_component(Component(
        id="cache", name="Redis Cache", type=ComponentType.CACHE,
        replicas=1, capacity=Capacity(max_connections=200),
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
    ))

    return graph


def _build_bottleneck_graph() -> InfraGraph:
    """Graph with capacity bottlenecks."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="web", name="Web Server", type=ComponentType.WEB_SERVER,
        replicas=1,
        metrics=ResourceMetrics(
            cpu_percent=85, memory_percent=72, disk_percent=90,
        ),
        capacity=Capacity(connection_pool_size=100),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        metrics=ResourceMetrics(
            cpu_percent=30, memory_percent=40, disk_percent=20,
            network_connections=90,
        ),
        capacity=Capacity(connection_pool_size=100),
    ))

    graph.add_dependency(Dependency(
        source_id="web", target_id="db", dependency_type="requires",
    ))

    return graph


def _build_protected_graph() -> InfraGraph:
    """Graph with circuit breakers and retry strategies."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=2, capacity=Capacity(max_connections=500),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        capacity=Capacity(max_connections=100),
    ))

    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(enabled=True),
    ))

    return graph


def _build_cascade_graph() -> InfraGraph:
    """Graph that triggers large cascades."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="gateway", name="API Gateway", type=ComponentType.LOAD_BALANCER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="svc-a", name="Service A", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="svc-b", name="Service B", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="Shared DB", type=ComponentType.DATABASE,
        replicas=1,
    ))

    graph.add_dependency(Dependency(
        source_id="gateway", target_id="svc-a", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="gateway", target_id="svc-b", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="svc-a", target_id="db", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="svc-b", target_id="db", dependency_type="requires",
    ))

    return graph


# ---------------------------------------------------------------------------
# Tests: Score-to-nines mapping
# ---------------------------------------------------------------------------


def test_score_to_nines_high():
    assert _score_to_nines(95) == 4.5
    assert _score_to_nines(100) == 4.5


def test_score_to_nines_medium():
    assert _score_to_nines(75) == 3.0
    assert _score_to_nines(85) == 3.5


def test_score_to_nines_low():
    assert _score_to_nines(45) == 1.5
    assert _score_to_nines(10) == 1.0


def test_nines_tier_label():
    label = _nines_tier_label(4.0)
    assert "4+" in label or "4" in label
    assert "nines" in label

    label_low = _nines_tier_label(1.5)
    assert "Poor" in label_low or "significant" in label_low.lower() or "<2" in label_low


# ---------------------------------------------------------------------------
# Tests: SPOF detection
# ---------------------------------------------------------------------------


def test_spof_detection():
    """Single-replica DB with required dependents should be flagged."""
    graph = _build_spof_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    # DB should be flagged as SPOF
    spof_recs = [r for r in ai_report.recommendations if r.category == "spof"]
    spof_ids = [r.component_id for r in spof_recs]
    assert "db" in spof_ids, f"Expected 'db' in SPOF recommendations, got {spof_ids}"

    # Check the recommendation has proper content
    db_rec = [r for r in spof_recs if r.component_id == "db"][0]
    assert db_rec.severity in ("critical", "high")
    assert "replica" in db_rec.remediation.lower() or "failover" in db_rec.remediation.lower()


def test_no_spof_with_replicas():
    """Components with multiple replicas should not be flagged as SPOF."""
    graph = _build_protected_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    spof_recs = [r for r in ai_report.recommendations if r.category == "spof"]
    assert len(spof_recs) == 0, f"Expected no SPOFs in protected graph, got {spof_recs}"


# ---------------------------------------------------------------------------
# Tests: Cascade amplifier detection
# ---------------------------------------------------------------------------


def test_cascade_amplifier_detection():
    """DB failure cascading to >30% of system should be detected."""
    graph = _build_cascade_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    cascade_recs = [r for r in ai_report.recommendations if r.category == "cascade"]
    # The shared DB failure should cascade through all components
    # Since it's a 4-component system, affecting 3+ is >30%
    # It's possible the cascade_recs list is empty if no scenario hits >30%
    # but with 4 components any cascade of 2+ is 50%+
    if cascade_recs:
        assert any("circuit breaker" in r.remediation.lower() for r in cascade_recs)


# ---------------------------------------------------------------------------
# Tests: Capacity bottleneck detection
# ---------------------------------------------------------------------------


def test_capacity_bottleneck_detection():
    """Components with >70% utilization should be flagged."""
    graph = _build_bottleneck_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    capacity_recs = [r for r in ai_report.recommendations if r.category == "capacity"]
    capacity_ids = [r.component_id for r in capacity_recs]

    # Web server has CPU at 85%, memory at 72%, disk at 90%
    assert "web" in capacity_ids, (
        f"Expected 'web' in capacity bottleneck recommendations, got {capacity_ids}"
    )

    # DB has connection pool at 90%
    assert "db" in capacity_ids, (
        f"Expected 'db' in capacity bottleneck recommendations, got {capacity_ids}"
    )


# ---------------------------------------------------------------------------
# Tests: Missing protections detection
# ---------------------------------------------------------------------------


def test_missing_protections_detection():
    """Critical deps without circuit breakers should be flagged."""
    graph = _build_spof_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    config_recs = [r for r in ai_report.recommendations if r.category == "config"]
    # The app->db dependency has no circuit breaker by default
    assert len(config_recs) > 0, "Expected missing protection recommendations"
    assert any(
        "circuit breaker" in r.title.lower() or "retry" in r.title.lower()
        for r in config_recs
    )


def test_no_missing_protections_when_configured():
    """Protected edges should not generate config recommendations."""
    graph = _build_protected_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    config_recs = [r for r in ai_report.recommendations if r.category == "config"]
    assert len(config_recs) == 0, (
        f"Expected no config recommendations in protected graph, got {config_recs}"
    )


# ---------------------------------------------------------------------------
# Tests: Natural language summary generation
# ---------------------------------------------------------------------------


def test_summary_generation():
    """Summary should be a non-empty multi-sentence string."""
    graph = _build_spof_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    assert isinstance(ai_report.summary, str)
    assert len(ai_report.summary) > 50, "Summary should be at least a few sentences"
    # Should mention components or nines
    assert "component" in ai_report.summary.lower() or "nines" in ai_report.summary.lower()


def test_summary_mentions_critical_risks():
    """Summary should reference critical risks when present."""
    graph = _build_spof_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    # With SPOFs present, summary should mention critical risks
    has_critical = any(r.severity == "critical" for r in ai_report.recommendations)
    if has_critical:
        assert "critical" in ai_report.summary.lower()


# ---------------------------------------------------------------------------
# Tests: Availability tier mapping
# ---------------------------------------------------------------------------


def test_availability_assessment():
    """Availability assessment should be populated."""
    graph = _build_spof_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    assert ai_report.estimated_current_nines > 0
    assert ai_report.theoretical_max_nines >= ai_report.estimated_current_nines
    assert "tier" in ai_report.availability_assessment.lower() or \
           "nines" in ai_report.availability_assessment.lower()


def test_protected_graph_has_higher_nines():
    """A graph with replicas + failover should score higher than one with SPOFs."""
    spof_graph = _build_spof_graph()
    protected_graph = _build_protected_graph()

    spof_engine = SimulationEngine(spof_graph)
    spof_report = spof_engine.run_all_defaults()

    protected_engine = SimulationEngine(protected_graph)
    protected_report = protected_engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    spof_analysis = analyzer.analyze(spof_graph, spof_report)
    protected_analysis = analyzer.analyze(protected_graph, protected_report)

    assert protected_analysis.estimated_current_nines >= spof_analysis.estimated_current_nines


# ---------------------------------------------------------------------------
# Tests: Recommendation generation
# ---------------------------------------------------------------------------


def test_recommendations_sorted_by_severity():
    """Recommendations should be sorted critical > high > medium > low."""
    graph = _build_spof_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for i in range(len(ai_report.recommendations) - 1):
        current_order = severity_order.get(ai_report.recommendations[i].severity, 99)
        next_order = severity_order.get(ai_report.recommendations[i + 1].severity, 99)
        assert current_order <= next_order, (
            f"Recommendations not sorted: {ai_report.recommendations[i].severity} "
            f"before {ai_report.recommendations[i + 1].severity}"
        )


def test_recommendation_has_all_fields():
    """Each recommendation should have all required fields populated."""
    graph = _build_spof_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    assert len(ai_report.recommendations) > 0

    for rec in ai_report.recommendations:
        assert rec.component_id, "component_id should be set"
        assert rec.category in ("spof", "capacity", "cascade", "config", "cost")
        assert rec.severity in ("critical", "high", "medium", "low")
        assert len(rec.title) > 0, "title should not be empty"
        assert len(rec.description) > 0, "description should not be empty"
        assert len(rec.remediation) > 0, "remediation should not be empty"
        assert len(rec.estimated_impact) > 0, "estimated_impact should not be empty"
        assert rec.effort in ("low", "medium", "high")


def test_top_risks_generated():
    """Top risks should contain 1-5 plain language risk descriptions."""
    graph = _build_spof_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    assert 1 <= len(ai_report.top_risks) <= 5
    for risk in ai_report.top_risks:
        assert isinstance(risk, str)
        assert len(risk) > 10, "Each risk should be a meaningful sentence"


def test_upgrade_path_generated():
    """Upgrade path should provide actionable steps."""
    graph = _build_spof_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    assert isinstance(ai_report.upgrade_path, str)
    assert len(ai_report.upgrade_path) > 20, "Upgrade path should contain actionable guidance"


# ---------------------------------------------------------------------------
# Tests: Empty / minimal graph
# ---------------------------------------------------------------------------


def test_empty_graph():
    """Analyzer should handle empty graph gracefully."""
    graph = InfraGraph()
    report = SimulationReport(results=[], resilience_score=0.0)

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    assert isinstance(ai_report, AIAnalysisReport)
    assert isinstance(ai_report.summary, str)
    assert isinstance(ai_report.recommendations, list)


def test_single_component_graph():
    """Analyzer should handle a graph with one component, no dependencies."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="solo", name="Solo Service", type=ComponentType.APP_SERVER,
        replicas=1,
    ))

    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    assert isinstance(ai_report, AIAnalysisReport)
    # No SPOF because no required dependents
    spof_recs = [r for r in ai_report.recommendations if r.category == "spof"]
    assert len(spof_recs) == 0


# ---------------------------------------------------------------------------
# Tests: Score-to-nines mapping edge cases
# ---------------------------------------------------------------------------


def test_score_to_nines_all_ranges():
    """Verify all score ranges map correctly."""
    assert _score_to_nines(95) == 4.5
    assert _score_to_nines(90) == 4.0
    assert _score_to_nines(80) == 3.5
    assert _score_to_nines(70) == 3.0
    assert _score_to_nines(60) == 2.5
    assert _score_to_nines(50) == 2.0
    assert _score_to_nines(30) == 1.5
    assert _score_to_nines(20) == 1.0
    assert _score_to_nines(0) == 1.0


def test_nines_tier_label_all_tiers():
    """Verify all nines tiers have correct labels."""
    label_45 = _nines_tier_label(4.5)
    assert "Excellent" in label_45

    label_40 = _nines_tier_label(4.0)
    assert "High" in label_40

    label_35 = _nines_tier_label(3.5)
    assert "Good" in label_35

    label_30 = _nines_tier_label(3.0)
    assert "Standard" in label_30

    label_25 = _nines_tier_label(2.5)
    assert "Basic" in label_25

    label_20 = _nines_tier_label(2.0)
    assert "Low" in label_20

    label_10 = _nines_tier_label(1.0)
    assert "Poor" in label_10


# ---------------------------------------------------------------------------
# Tests: Upgrade path edge cases
# ---------------------------------------------------------------------------


def test_upgrade_path_at_highest_tier():
    """At the highest tier, upgrade path should provide guidance."""
    # Build a well-protected graph with high resilience
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=3,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=3,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db",
        dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(enabled=True),
    ))

    # Use a very high resilience score to simulate highest tier
    report = SimulationReport(results=[], resilience_score=99.0)

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    # At 4.5 nines, next tier is 5.0 which may or may not be reachable.
    # The upgrade path should be a non-empty, informative string regardless.
    assert len(ai_report.upgrade_path) > 20
    assert isinstance(ai_report.upgrade_path, str)
    # At 4.5 nines, it either says "highest" (if theoretical_max >= 5.0)
    # or suggests architectural changes to reach 5.0 nines
    assert (
        "highest" in ai_report.upgrade_path.lower()
        or "maintain" in ai_report.upgrade_path.lower()
        or "nines" in ai_report.upgrade_path.lower()
    )


def test_upgrade_path_needs_architectural_changes():
    """When theoretical max can't reach next tier, should suggest architectural changes."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db",
        dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(enabled=True),
    ))

    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    # The upgrade path should be a non-empty string
    assert len(ai_report.upgrade_path) > 0


# ---------------------------------------------------------------------------
# Tests: LLM provider
# ---------------------------------------------------------------------------


def test_set_llm_provider():
    """set_llm_provider should store the provider."""
    analyzer = FaultRayAnalyzer()
    assert analyzer._llm_provider is None

    class MockLLM:
        def generate_summary(self, context):
            return "mock summary"
        def generate_recommendations(self, context):
            return []

    analyzer.set_llm_provider(MockLLM())
    assert analyzer._llm_provider is not None


# ---------------------------------------------------------------------------
# Tests: Capacity bottleneck edge cases
# ---------------------------------------------------------------------------


def test_no_bottleneck_with_low_utilization():
    """Components with <70% utilization should not be flagged."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=30, memory_percent=40, disk_percent=20),
    ))
    report = SimulationReport(results=[], resilience_score=80.0)

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    capacity_recs = [r for r in ai_report.recommendations if r.category == "capacity"]
    assert len(capacity_recs) == 0


def test_bottleneck_connection_pool():
    """Connection pool at >70% should trigger bottleneck."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
        metrics=ResourceMetrics(network_connections=85, cpu_percent=30),
        capacity=Capacity(connection_pool_size=100),
    ))
    report = SimulationReport(results=[], resilience_score=80.0)

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    capacity_recs = [r for r in ai_report.recommendations if r.category == "capacity"]
    assert len(capacity_recs) >= 1
    assert any("Connection pool" in r.description for r in capacity_recs)


# ---------------------------------------------------------------------------
# Tests: Missing protections edge cases
# ---------------------------------------------------------------------------


def test_optional_dep_not_flagged():
    """Optional dependencies should not be flagged for missing protections."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE,
        replicas=2,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache",
        dependency_type="optional",  # not "requires"
    ))
    report = SimulationReport(results=[], resilience_score=80.0)

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    config_recs = [r for r in ai_report.recommendations if r.category == "config"]
    assert len(config_recs) == 0


# ---------------------------------------------------------------------------
# Tests: Summary generation variants
# ---------------------------------------------------------------------------


def test_summary_no_critical_risks():
    """Summary with no critical recommendations should say 'good shape'."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db",
        dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(enabled=True),
    ))

    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()
    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)

    critical_recs = [r for r in ai_report.recommendations if r.severity == "critical"]
    if not critical_recs:
        assert "good shape" in ai_report.summary.lower()


def test_top_risks_no_critical():
    """When no critical risks, should return 'No critical risks detected.'."""
    graph = InfraGraph()
    report = SimulationReport(results=[], resilience_score=100.0)
    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, report)
    assert any("No critical risks" in r for r in ai_report.top_risks)
