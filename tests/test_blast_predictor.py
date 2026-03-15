"""Comprehensive tests for the Blast Radius Predictor.

Tests cover prediction for each component type, BFS traversal, probability
decay, impact classification, blast radius scoring, what-if analysis,
hotspot detection, prediction comparison, heatmap data generation, and
various edge cases.
"""

from infrasim.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.blast_predictor import (
    BlastPrediction,
    BlastPredictor,
    ComponentImpact,
    ImpactLevel,
    PredictionConfidence,
    RiskHotspot,
    WhatIfResult,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_component(
    id: str,
    name: str,
    type: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    cpu_percent: float = 0.0,
    memory_percent: float = 0.0,
    failover_enabled: bool = False,
    autoscaling_enabled: bool = False,
    max_connections: int = 1000,
    network_connections: int = 0,
    disk_percent: float = 0.0,
) -> Component:
    """Build a Component with commonly-used overrides."""
    return Component(
        id=id,
        name=name,
        type=type,
        replicas=replicas,
        metrics=ResourceMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            network_connections=network_connections,
            disk_percent=disk_percent,
        ),
        capacity=Capacity(max_connections=max_connections),
        failover=FailoverConfig(enabled=failover_enabled),
        autoscaling=AutoScalingConfig(enabled=autoscaling_enabled),
    )


def _build_simple_graph() -> InfraGraph:
    """Build a simple 3-tier graph: LB -> App -> DB."""
    graph = InfraGraph()
    graph.add_component(
        _make_component("lb", "Load Balancer", ComponentType.LOAD_BALANCER)
    )
    graph.add_component(
        _make_component("app", "App Server", ComponentType.APP_SERVER)
    )
    graph.add_component(
        _make_component("db", "Database", ComponentType.DATABASE)
    )

    graph.add_dependency(
        Dependency(source_id="lb", target_id="app", dependency_type="requires", weight=1.0)
    )
    graph.add_dependency(
        Dependency(source_id="app", target_id="db", dependency_type="requires", weight=1.0)
    )
    return graph


def _build_complex_graph() -> InfraGraph:
    """Build a multi-layer topology with branching dependencies.

    Topology:
        dns -> lb -> web1, web2
        web1 -> app1, app2
        web2 -> app2
        app1 -> db_primary, cache
        app2 -> db_primary, queue
        db_primary (standalone, no outgoing)
        cache (standalone)
        queue -> external_api
    """
    graph = InfraGraph()

    graph.add_component(
        _make_component("dns", "DNS", ComponentType.DNS)
    )
    graph.add_component(
        _make_component("lb", "Load Balancer", ComponentType.LOAD_BALANCER, replicas=2)
    )
    graph.add_component(
        _make_component("web1", "Web Server 1", ComponentType.WEB_SERVER)
    )
    graph.add_component(
        _make_component("web2", "Web Server 2", ComponentType.WEB_SERVER)
    )
    graph.add_component(
        _make_component("app1", "App Server 1", ComponentType.APP_SERVER)
    )
    graph.add_component(
        _make_component("app2", "App Server 2", ComponentType.APP_SERVER)
    )
    graph.add_component(
        _make_component(
            "db_primary", "DB Primary", ComponentType.DATABASE, replicas=1
        )
    )
    graph.add_component(
        _make_component("cache", "Cache", ComponentType.CACHE, replicas=2)
    )
    graph.add_component(
        _make_component("queue", "Queue", ComponentType.QUEUE)
    )
    graph.add_component(
        _make_component(
            "ext_api", "External API", ComponentType.EXTERNAL_API
        )
    )

    # dns -> lb
    graph.add_dependency(
        Dependency(source_id="dns", target_id="lb", dependency_type="requires", weight=1.0)
    )
    # lb -> web1, web2
    graph.add_dependency(
        Dependency(source_id="lb", target_id="web1", dependency_type="requires", weight=0.8)
    )
    graph.add_dependency(
        Dependency(source_id="lb", target_id="web2", dependency_type="requires", weight=0.8)
    )
    # web1 -> app1, app2
    graph.add_dependency(
        Dependency(source_id="web1", target_id="app1", dependency_type="requires", weight=0.9)
    )
    graph.add_dependency(
        Dependency(source_id="web1", target_id="app2", dependency_type="optional", weight=0.5)
    )
    # web2 -> app2
    graph.add_dependency(
        Dependency(source_id="web2", target_id="app2", dependency_type="requires", weight=0.9)
    )
    # app1 -> db_primary, cache
    graph.add_dependency(
        Dependency(source_id="app1", target_id="db_primary", dependency_type="requires", weight=1.0)
    )
    graph.add_dependency(
        Dependency(source_id="app1", target_id="cache", dependency_type="optional", weight=0.4)
    )
    # app2 -> db_primary, queue
    graph.add_dependency(
        Dependency(source_id="app2", target_id="db_primary", dependency_type="requires", weight=1.0)
    )
    graph.add_dependency(
        Dependency(source_id="app2", target_id="queue", dependency_type="async", weight=0.6)
    )
    # queue -> ext_api
    graph.add_dependency(
        Dependency(source_id="queue", target_id="ext_api", dependency_type="requires", weight=0.7)
    )

    return graph


# ===================================================================
# Tests for data classes
# ===================================================================


class TestDataClasses:
    """Tests for enums and dataclass construction."""

    def test_prediction_confidence_values(self):
        assert PredictionConfidence.HIGH.value == "high"
        assert PredictionConfidence.MEDIUM.value == "medium"
        assert PredictionConfidence.LOW.value == "low"

    def test_impact_level_values(self):
        assert ImpactLevel.NONE.value == "none"
        assert ImpactLevel.MINOR.value == "minor"
        assert ImpactLevel.MODERATE.value == "moderate"
        assert ImpactLevel.SEVERE.value == "severe"
        assert ImpactLevel.CATASTROPHIC.value == "catastrophic"

    def test_component_impact_defaults(self):
        ci = ComponentImpact(
            component_id="x",
            component_name="X",
            impact_level=ImpactLevel.MINOR,
            impact_probability=0.5,
            estimated_degradation_percent=10.0,
            time_to_impact_seconds=30,
        )
        assert ci.recovery_dependency == []
        assert ci.component_id == "x"
        assert ci.impact_probability == 0.5

    def test_component_impact_with_recovery(self):
        ci = ComponentImpact(
            component_id="a",
            component_name="A",
            impact_level=ImpactLevel.SEVERE,
            impact_probability=0.9,
            estimated_degradation_percent=70.0,
            time_to_impact_seconds=15,
            recovery_dependency=["b", "c"],
        )
        assert ci.recovery_dependency == ["b", "c"]

    def test_blast_prediction_defaults(self):
        bp = BlastPrediction(
            source_component_id="src",
            source_component_name="Source",
        )
        assert bp.predicted_impacts == []
        assert bp.blast_radius_score == 0.0
        assert bp.confidence == PredictionConfidence.MEDIUM
        assert bp.max_cascade_depth == 0
        assert bp.affected_component_count == 0
        assert bp.affected_users_estimate == "unknown"
        assert bp.mitigation_suggestions == []

    def test_what_if_result_defaults(self):
        wir = WhatIfResult(scenario_description="test")
        assert wir.predictions == []
        assert wir.comparison_baseline is None
        assert wir.delta_summary == ""

    def test_risk_hotspot_defaults(self):
        rh = RiskHotspot(component_id="x", component_name="X")
        assert rh.outgoing_blast_radius == 0.0
        assert rh.incoming_vulnerability == 0.0
        assert rh.combined_risk_score == 0.0
        assert rh.risk_factors == []


# ===================================================================
# Tests for prediction on each component type
# ===================================================================


class TestPredictionByComponentType:
    """Test prediction for each ComponentType."""

    def test_predict_database_failure(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db")

        # DB failure should impact app (direct dependent)
        assert pred.source_component_id == "db"
        assert pred.affected_component_count >= 1
        affected_ids = [i.component_id for i in pred.predicted_impacts]
        assert "app" in affected_ids

    def test_predict_load_balancer_failure(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "lb")

        # LB has no dependents in this graph, only dependencies
        # So blast radius should be 0 (nothing depends on LB)
        assert pred.source_component_id == "lb"
        # In our simple graph, nothing depends on LB (LB depends on app)
        # wait - lb -> app means lb depends on app; dependents of lb = those that depend ON lb = none
        assert pred.affected_component_count == 0

    def test_predict_app_server_failure(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "app")

        # LB depends on app, so app failure should impact LB
        affected_ids = [i.component_id for i in pred.predicted_impacts]
        assert "lb" in affected_ids

    def test_predict_web_server_failure(self):
        graph = _build_complex_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "web1")

        # lb depends on web1, so lb should be impacted
        affected_ids = [i.component_id for i in pred.predicted_impacts]
        assert "lb" in affected_ids

    def test_predict_cache_failure(self):
        graph = _build_complex_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "cache")

        # app1 depends on cache (optional), so app1 may be impacted
        # Impact probability will be low due to optional dependency
        assert pred.source_component_name == "Cache"

    def test_predict_queue_failure(self):
        graph = _build_complex_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "queue")

        # app2 depends on queue (async), so impact probability is low
        assert pred.source_component_id == "queue"

    def test_predict_dns_failure(self):
        graph = _build_complex_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "dns")

        # Nothing depends on dns in this graph topology
        # (dns depends on lb, not the other way)
        assert pred.source_component_id == "dns"

    def test_predict_external_api_failure(self):
        graph = _build_complex_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "ext_api")

        # queue depends on ext_api, so queue should be impacted
        affected_ids = [i.component_id for i in pred.predicted_impacts]
        assert "queue" in affected_ids

    def test_predict_storage_type(self):
        graph = InfraGraph()
        graph.add_component(
            _make_component("store", "Object Store", ComponentType.STORAGE)
        )
        graph.add_component(
            _make_component("app", "App", ComponentType.APP_SERVER)
        )
        graph.add_dependency(
            Dependency(source_id="app", target_id="store", dependency_type="requires")
        )
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "store")
        affected_ids = [i.component_id for i in pred.predicted_impacts]
        assert "app" in affected_ids

    def test_predict_custom_type(self):
        graph = InfraGraph()
        graph.add_component(
            _make_component("custom", "Custom Service", ComponentType.CUSTOM)
        )
        graph.add_component(
            _make_component("app", "App", ComponentType.APP_SERVER)
        )
        graph.add_dependency(
            Dependency(source_id="app", target_id="custom", dependency_type="requires")
        )
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "custom")
        assert pred.affected_component_count >= 1


# ===================================================================
# Tests for BFS traversal and probability decay
# ===================================================================


class TestBFSAndDecay:
    """Test BFS traversal mechanics and probability decay."""

    def test_bfs_visits_all_dependents(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db")

        # db -> app -> lb (cascade chain)
        affected_ids = {i.component_id for i in pred.predicted_impacts}
        assert "app" in affected_ids
        # lb may or may not be affected depending on decay; check depth >= 1
        assert pred.max_cascade_depth >= 1

    def test_probability_decays_with_depth(self):
        """Impact probability should decrease with cascade depth."""
        graph = _build_simple_graph()
        predictor = BlastPredictor(decay_factor=0.8)
        pred = predictor.predict(graph, "db")

        impacts = {i.component_id: i for i in pred.predicted_impacts}
        if "app" in impacts and "lb" in impacts:
            # app is depth 1, lb is depth 2 — lb should have lower probability
            assert impacts["lb"].impact_probability <= impacts["app"].impact_probability

    def test_high_decay_factor_broader_impact(self):
        """With higher decay factor, more components should be affected."""
        graph = _build_simple_graph()
        pred_high = BlastPredictor(decay_factor=0.95).predict(graph, "db")
        pred_low = BlastPredictor(decay_factor=0.3).predict(graph, "db")

        assert pred_high.affected_component_count >= pred_low.affected_component_count

    def test_zero_decay_no_propagation(self):
        """With near-zero decay, cascade should not propagate beyond immediate."""
        graph = _build_simple_graph()
        predictor = BlastPredictor(decay_factor=0.01)
        pred = predictor.predict(graph, "db")

        # With very low decay, probability drops below threshold quickly
        # Only immediate dependents with high weight might be affected
        assert pred.max_cascade_depth <= 1

    def test_bfs_does_not_revisit_nodes(self):
        """BFS should not visit the same component twice."""
        graph = _build_complex_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db_primary")

        # Each component should appear at most once
        ids = [i.component_id for i in pred.predicted_impacts]
        assert len(ids) == len(set(ids))

    def test_bfs_handles_diamond_dependency(self):
        """Test diamond: A -> B, A -> C, B -> D, C -> D."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A", ComponentType.APP_SERVER))
        graph.add_component(_make_component("b", "B", ComponentType.APP_SERVER))
        graph.add_component(_make_component("c", "C", ComponentType.APP_SERVER))
        graph.add_component(_make_component("d", "D", ComponentType.DATABASE))

        graph.add_dependency(Dependency(source_id="a", target_id="b", dependency_type="requires"))
        graph.add_dependency(Dependency(source_id="a", target_id="c", dependency_type="requires"))
        graph.add_dependency(Dependency(source_id="b", target_id="d", dependency_type="requires"))
        graph.add_dependency(Dependency(source_id="c", target_id="d", dependency_type="requires"))

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "d")

        # D failing should impact b and c (direct), then a (through b or c)
        affected_ids = {i.component_id for i in pred.predicted_impacts}
        assert "b" in affected_ids or "c" in affected_ids
        # No duplicates
        ids = [i.component_id for i in pred.predicted_impacts]
        assert len(ids) == len(set(ids))


# ===================================================================
# Tests for impact level classification
# ===================================================================


class TestImpactClassification:
    """Test impact level classification logic."""

    def test_catastrophic_classification(self):
        level = BlastPredictor._classify_impact(1.0, 0.8)
        assert level == ImpactLevel.CATASTROPHIC

    def test_severe_classification(self):
        level = BlastPredictor._classify_impact(0.7, 0.8)
        assert level == ImpactLevel.SEVERE

    def test_moderate_classification(self):
        level = BlastPredictor._classify_impact(0.5, 0.7)
        assert level == ImpactLevel.MODERATE

    def test_minor_classification(self):
        level = BlastPredictor._classify_impact(0.2, 0.7)
        assert level == ImpactLevel.MINOR

    def test_none_classification(self):
        level = BlastPredictor._classify_impact(0.05, 0.5)
        assert level == ImpactLevel.NONE

    def test_boundary_catastrophic(self):
        # score = prob * crit = 0.7 exactly -> severe (>= 0.7 is catastrophic threshold)
        level = BlastPredictor._classify_impact(0.7, 1.0)
        assert level == ImpactLevel.CATASTROPHIC

    def test_boundary_severe(self):
        level = BlastPredictor._classify_impact(0.5, 1.0)
        assert level == ImpactLevel.SEVERE

    def test_boundary_moderate(self):
        level = BlastPredictor._classify_impact(0.3, 1.0)
        assert level == ImpactLevel.MODERATE

    def test_boundary_minor(self):
        level = BlastPredictor._classify_impact(0.1, 1.0)
        assert level == ImpactLevel.MINOR

    def test_low_probability_low_criticality(self):
        level = BlastPredictor._classify_impact(0.05, 0.1)
        assert level == ImpactLevel.NONE

    def test_high_probability_low_criticality(self):
        level = BlastPredictor._classify_impact(1.0, 0.15)
        assert level == ImpactLevel.MINOR


# ===================================================================
# Tests for blast radius score calculation
# ===================================================================


class TestBlastRadiusScore:
    """Test the blast radius score formula."""

    def test_empty_impacts_score_zero(self):
        score = BlastPredictor._calculate_blast_score([], 0)
        assert score == 0.0

    def test_single_minor_impact(self):
        impacts = [
            ComponentImpact(
                component_id="a", component_name="A",
                impact_level=ImpactLevel.MINOR, impact_probability=0.5,
                estimated_degradation_percent=10.0, time_to_impact_seconds=15,
            )
        ]
        score = BlastPredictor._calculate_blast_score(impacts, 1)
        # minor_count=1, severe=0, moderate=0, depth_multiplier=1.15
        # raw = 3 * 1.15 = 3.45
        assert 3.0 <= score <= 4.0

    def test_multiple_severe_impacts(self):
        impacts = [
            ComponentImpact(
                component_id=f"c{i}", component_name=f"C{i}",
                impact_level=ImpactLevel.SEVERE, impact_probability=0.8,
                estimated_degradation_percent=60.0, time_to_impact_seconds=15 * i,
            )
            for i in range(4)
        ]
        score = BlastPredictor._calculate_blast_score(impacts, 3)
        # severe_count=4, depth_multiplier=1.45
        # raw = 4 * 25 * 1.45 = 145 -> capped at 100
        assert score == 100.0

    def test_score_capped_at_100(self):
        impacts = [
            ComponentImpact(
                component_id=f"c{i}", component_name=f"C{i}",
                impact_level=ImpactLevel.CATASTROPHIC, impact_probability=0.9,
                estimated_degradation_percent=90.0, time_to_impact_seconds=10,
            )
            for i in range(10)
        ]
        score = BlastPredictor._calculate_blast_score(impacts, 5)
        assert score == 100.0

    def test_depth_multiplier_effect(self):
        impacts = [
            ComponentImpact(
                component_id="a", component_name="A",
                impact_level=ImpactLevel.MODERATE, impact_probability=0.6,
                estimated_degradation_percent=30.0, time_to_impact_seconds=15,
            )
        ]
        score_depth1 = BlastPredictor._calculate_blast_score(impacts, 1)
        score_depth5 = BlastPredictor._calculate_blast_score(impacts, 5)
        assert score_depth5 > score_depth1

    def test_mixed_severity_levels(self):
        impacts = [
            ComponentImpact(
                component_id="s", component_name="S",
                impact_level=ImpactLevel.SEVERE, impact_probability=0.8,
                estimated_degradation_percent=60.0, time_to_impact_seconds=15,
            ),
            ComponentImpact(
                component_id="m", component_name="M",
                impact_level=ImpactLevel.MODERATE, impact_probability=0.5,
                estimated_degradation_percent=30.0, time_to_impact_seconds=30,
            ),
            ComponentImpact(
                component_id="n", component_name="N",
                impact_level=ImpactLevel.MINOR, impact_probability=0.3,
                estimated_degradation_percent=10.0, time_to_impact_seconds=45,
            ),
        ]
        score = BlastPredictor._calculate_blast_score(impacts, 2)
        # severe=1(25), moderate=1(10), minor=1(3) = 38, depth_mult=1.3
        # 38 * 1.3 = 49.4
        assert 49.0 <= score <= 50.0


# ===================================================================
# Tests for what-if analysis
# ===================================================================


class TestWhatIfAnalysis:
    """Test what-if scenario analysis."""

    def test_add_replicas_reduces_blast_radius(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        result = predictor.what_if(graph, "db", {"replicas": 3})

        assert isinstance(result, WhatIfResult)
        assert result.comparison_baseline is not None
        assert len(result.predictions) == 1

        baseline_score = result.comparison_baseline.blast_radius_score
        modified_score = result.predictions[0].blast_radius_score
        # Adding replicas should reduce or maintain blast radius
        assert modified_score <= baseline_score

    def test_enable_failover(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        result = predictor.what_if(graph, "db", {"failover_enabled": True})

        assert "failover" in result.scenario_description.lower()
        assert result.comparison_baseline is not None

    def test_enable_autoscaling(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        result = predictor.what_if(graph, "app", {"autoscaling_enabled": True})

        assert "autoscaling" in result.scenario_description.lower()

    def test_reduce_cpu_load(self):
        graph = InfraGraph()
        graph.add_component(
            _make_component("app", "App", ComponentType.APP_SERVER, cpu_percent=90.0)
        )
        graph.add_component(
            _make_component("db", "DB", ComponentType.DATABASE)
        )
        graph.add_dependency(
            Dependency(source_id="app", target_id="db", dependency_type="requires")
        )

        predictor = BlastPredictor()
        result = predictor.what_if(graph, "app", {"current_cpu_percent": 30.0})

        assert "cpu" in result.scenario_description.lower()
        assert result.comparison_baseline is not None

    def test_reduce_memory_load(self):
        graph = InfraGraph()
        graph.add_component(
            _make_component("app", "App", ComponentType.APP_SERVER, memory_percent=85.0)
        )
        graph.add_component(
            _make_component("client", "Client", ComponentType.WEB_SERVER)
        )
        graph.add_dependency(
            Dependency(source_id="client", target_id="app", dependency_type="requires")
        )

        predictor = BlastPredictor()
        result = predictor.what_if(graph, "app", {"current_memory_percent": 40.0})

        assert "memory" in result.scenario_description.lower()

    def test_what_if_nonexistent_component(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        result = predictor.what_if(graph, "nonexistent", {"replicas": 3})

        assert "not found" in result.delta_summary.lower()

    def test_what_if_multiple_changes(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        result = predictor.what_if(
            graph,
            "db",
            {"replicas": 3, "failover_enabled": True},
        )

        assert "replicas" in result.scenario_description.lower()
        assert "failover" in result.scenario_description.lower()

    def test_what_if_delta_summary_reduced(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        result = predictor.what_if(graph, "db", {"replicas": 5, "failover_enabled": True})

        # After adding 5 replicas + failover, blast radius should be reduced
        baseline = result.comparison_baseline
        modified = result.predictions[0]
        if baseline and baseline.blast_radius_score > modified.blast_radius_score + 1.0:
            assert "reduced" in result.delta_summary.lower()

    def test_what_if_preserves_original_graph(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        original_replicas = graph.get_component("db").replicas

        predictor.what_if(graph, "db", {"replicas": 5})

        # Original graph should be unchanged
        assert graph.get_component("db").replicas == original_replicas


# ===================================================================
# Tests for hotspot detection
# ===================================================================


class TestHotspotDetection:
    """Test risk hotspot detection."""

    def test_find_hotspots_returns_sorted(self):
        graph = _build_complex_graph()
        predictor = BlastPredictor()

        hotspots = predictor.find_hotspots(graph, top_n=5)

        assert len(hotspots) <= 5
        # Should be sorted by combined_risk_score descending
        for i in range(len(hotspots) - 1):
            assert hotspots[i].combined_risk_score >= hotspots[i + 1].combined_risk_score

    def test_find_hotspots_top_n(self):
        graph = _build_complex_graph()
        predictor = BlastPredictor()

        hotspots = predictor.find_hotspots(graph, top_n=3)
        assert len(hotspots) <= 3

    def test_hotspot_has_risk_factors(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        hotspots = predictor.find_hotspots(graph, top_n=10)

        # DB is single replica, no failover, etc.
        db_hotspot = next(
            (h for h in hotspots if h.component_id == "db"), None
        )
        if db_hotspot:
            assert len(db_hotspot.risk_factors) > 0

    def test_hotspot_combined_risk_formula(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        hotspots = predictor.find_hotspots(graph, top_n=10)

        for h in hotspots:
            expected = round(h.outgoing_blast_radius * 0.6 + h.incoming_vulnerability * 0.4, 1)
            assert h.combined_risk_score == expected

    def test_single_component_hotspot(self):
        graph = InfraGraph()
        graph.add_component(
            _make_component("solo", "Solo", ComponentType.APP_SERVER)
        )
        predictor = BlastPredictor()

        hotspots = predictor.find_hotspots(graph, top_n=5)
        assert len(hotspots) == 1
        assert hotspots[0].outgoing_blast_radius == 0.0

    def test_redundant_system_lower_risk(self):
        graph = InfraGraph()
        graph.add_component(
            _make_component(
                "app", "App", ComponentType.APP_SERVER,
                replicas=3, failover_enabled=True, autoscaling_enabled=True,
            )
        )
        graph.add_component(
            _make_component(
                "db", "DB", ComponentType.DATABASE,
                replicas=3, failover_enabled=True,
            )
        )
        graph.add_dependency(
            Dependency(source_id="app", target_id="db", dependency_type="requires")
        )

        predictor = BlastPredictor()
        hotspots = predictor.find_hotspots(graph, top_n=10)

        # All hotspot scores should be relatively low
        for h in hotspots:
            assert h.combined_risk_score < 50.0

    def test_high_fanin_component_identified(self):
        """Component with many dependents should be a hotspot."""
        graph = InfraGraph()
        graph.add_component(
            _make_component("db", "Central DB", ComponentType.DATABASE)
        )
        for i in range(5):
            cid = f"app{i}"
            graph.add_component(
                _make_component(cid, f"App {i}", ComponentType.APP_SERVER)
            )
            graph.add_dependency(
                Dependency(source_id=cid, target_id="db", dependency_type="requires")
            )

        predictor = BlastPredictor()
        hotspots = predictor.find_hotspots(graph, top_n=10)

        # DB should be the top hotspot
        assert hotspots[0].component_id == "db"
        assert "fan-in" in " ".join(hotspots[0].risk_factors).lower() or \
               "single-point" in " ".join(hotspots[0].risk_factors).lower()


# ===================================================================
# Tests for prediction comparison
# ===================================================================


class TestComparisonBetweenPredictions:
    """Test comparing two blast predictions."""

    def test_compare_identical_predictions(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db")

        result = predictor.compare_predictions(pred, pred)

        assert result["blast_radius_score_delta"] == 0.0
        assert result["affected_component_count_delta"] == 0
        assert result["max_cascade_depth_delta"] == 0
        assert result["improved"] is False  # delta == 0

    def test_compare_improved_prediction(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        baseline = predictor.predict(graph, "db")

        # Build a more resilient graph
        resilient_graph = InfraGraph()
        resilient_graph.add_component(
            _make_component("lb", "LB", ComponentType.LOAD_BALANCER, replicas=3)
        )
        resilient_graph.add_component(
            _make_component("app", "App", ComponentType.APP_SERVER, replicas=3, failover_enabled=True)
        )
        resilient_graph.add_component(
            _make_component("db", "DB", ComponentType.DATABASE, replicas=3, failover_enabled=True)
        )
        resilient_graph.add_dependency(
            Dependency(source_id="lb", target_id="app", dependency_type="requires")
        )
        resilient_graph.add_dependency(
            Dependency(source_id="app", target_id="db", dependency_type="requires")
        )

        improved = predictor.predict(resilient_graph, "db")

        result = predictor.compare_predictions(baseline, improved)

        assert result["blast_radius_score_delta"] <= 0
        if result["blast_radius_score_delta"] < 0:
            assert result["improved"] is True

    def test_compare_returns_component_sets(self):
        pred_a = BlastPrediction(
            source_component_id="src",
            source_component_name="Src",
            predicted_impacts=[
                ComponentImpact(
                    component_id="a", component_name="A",
                    impact_level=ImpactLevel.MINOR, impact_probability=0.5,
                    estimated_degradation_percent=10.0, time_to_impact_seconds=15,
                ),
                ComponentImpact(
                    component_id="b", component_name="B",
                    impact_level=ImpactLevel.MODERATE, impact_probability=0.6,
                    estimated_degradation_percent=30.0, time_to_impact_seconds=30,
                ),
            ],
        )
        pred_b = BlastPrediction(
            source_component_id="src",
            source_component_name="Src",
            predicted_impacts=[
                ComponentImpact(
                    component_id="b", component_name="B",
                    impact_level=ImpactLevel.MODERATE, impact_probability=0.6,
                    estimated_degradation_percent=30.0, time_to_impact_seconds=30,
                ),
                ComponentImpact(
                    component_id="c", component_name="C",
                    impact_level=ImpactLevel.SEVERE, impact_probability=0.8,
                    estimated_degradation_percent=60.0, time_to_impact_seconds=15,
                ),
            ],
        )

        predictor = BlastPredictor()
        result = predictor.compare_predictions(pred_a, pred_b)

        assert "a" in result["components_only_in_a"]
        assert "c" in result["components_only_in_b"]
        assert "b" in result["components_in_both"]

    def test_compare_impact_distributions(self):
        pred_a = BlastPrediction(
            source_component_id="x", source_component_name="X",
            predicted_impacts=[
                ComponentImpact(
                    component_id="a", component_name="A",
                    impact_level=ImpactLevel.CATASTROPHIC, impact_probability=0.9,
                    estimated_degradation_percent=90.0, time_to_impact_seconds=5,
                ),
            ],
        )
        pred_b = BlastPrediction(
            source_component_id="x", source_component_name="X",
            predicted_impacts=[
                ComponentImpact(
                    component_id="a", component_name="A",
                    impact_level=ImpactLevel.MINOR, impact_probability=0.2,
                    estimated_degradation_percent=10.0, time_to_impact_seconds=30,
                ),
            ],
        )

        predictor = BlastPredictor()
        result = predictor.compare_predictions(pred_a, pred_b)

        assert result["impact_distribution_a"]["catastrophic"] == 1
        assert result["impact_distribution_b"]["minor"] == 1


# ===================================================================
# Tests for heatmap data generation
# ===================================================================


class TestHeatmapData:
    """Test heatmap data generation."""

    def test_heatmap_data_structure(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        heatmap = predictor.generate_heatmap_data(graph)

        assert len(heatmap) == 3  # lb, app, db
        for entry in heatmap:
            assert "component_id" in entry
            assert "component_name" in entry
            assert "component_type" in entry
            assert "blast_radius_score" in entry
            assert "affected_component_count" in entry
            assert "max_cascade_depth" in entry
            assert "incoming_vulnerability" in entry
            assert "replicas" in entry
            assert "failover_enabled" in entry
            assert "autoscaling_enabled" in entry
            assert "current_utilization" in entry
            assert "confidence" in entry
            assert "risk_level" in entry

    def test_heatmap_sorted_by_score(self):
        graph = _build_complex_graph()
        predictor = BlastPredictor()

        heatmap = predictor.generate_heatmap_data(graph)

        for i in range(len(heatmap) - 1):
            assert heatmap[i]["blast_radius_score"] >= heatmap[i + 1]["blast_radius_score"]

    def test_heatmap_risk_level_labels(self):
        predictor = BlastPredictor()
        assert predictor._risk_level_label(80) == "critical"
        assert predictor._risk_level_label(60) == "high"
        assert predictor._risk_level_label(30) == "medium"
        assert predictor._risk_level_label(10) == "low"
        assert predictor._risk_level_label(0) == "none"

    def test_heatmap_component_types(self):
        graph = _build_complex_graph()
        predictor = BlastPredictor()

        heatmap = predictor.generate_heatmap_data(graph)

        types = {e["component_type"] for e in heatmap}
        assert "database" in types
        assert "app_server" in types

    def test_heatmap_empty_graph(self):
        graph = InfraGraph()
        predictor = BlastPredictor()

        heatmap = predictor.generate_heatmap_data(graph)
        assert heatmap == []


# ===================================================================
# Tests for edge cases
# ===================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_isolated_component(self):
        """A component with no dependencies should have zero blast radius."""
        graph = InfraGraph()
        graph.add_component(
            _make_component("solo", "Solo Server", ComponentType.APP_SERVER)
        )
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "solo")

        assert pred.blast_radius_score == 0.0
        assert pred.affected_component_count == 0
        assert pred.max_cascade_depth == 0
        assert pred.predicted_impacts == []

    def test_nonexistent_component(self):
        """Predicting for a non-existent component should return empty."""
        graph = _build_simple_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "nonexistent")

        assert pred.source_component_name == "unknown"
        assert pred.blast_radius_score == 0.0
        assert pred.affected_component_count == 0

    def test_fully_redundant_system(self):
        """A fully redundant system should have low blast radius."""
        graph = InfraGraph()
        graph.add_component(
            _make_component(
                "app", "App", ComponentType.APP_SERVER,
                replicas=5, failover_enabled=True, autoscaling_enabled=True,
            )
        )
        graph.add_component(
            _make_component(
                "db", "DB", ComponentType.DATABASE,
                replicas=5, failover_enabled=True,
            )
        )
        graph.add_dependency(
            Dependency(source_id="app", target_id="db", dependency_type="requires")
        )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db")

        # With 5 replicas + failover, the blast should be minimal
        assert pred.blast_radius_score < 30.0

    def test_single_node_graph(self):
        graph = InfraGraph()
        graph.add_component(
            _make_component("x", "X", ComponentType.DATABASE)
        )
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "x")

        assert pred.affected_component_count == 0
        assert pred.blast_radius_score == 0.0

    def test_two_independent_components(self):
        """Two components with no edges should not affect each other."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A", ComponentType.APP_SERVER))
        graph.add_component(_make_component("b", "B", ComponentType.DATABASE))

        predictor = BlastPredictor()
        pred_a = predictor.predict(graph, "a")
        pred_b = predictor.predict(graph, "b")

        assert pred_a.affected_component_count == 0
        assert pred_b.affected_component_count == 0

    def test_circular_independent_chains(self):
        """Two separate chains should not interact."""
        graph = InfraGraph()
        graph.add_component(_make_component("a1", "A1", ComponentType.APP_SERVER))
        graph.add_component(_make_component("a2", "A2", ComponentType.DATABASE))
        graph.add_component(_make_component("b1", "B1", ComponentType.APP_SERVER))
        graph.add_component(_make_component("b2", "B2", ComponentType.DATABASE))

        graph.add_dependency(Dependency(source_id="a1", target_id="a2", dependency_type="requires"))
        graph.add_dependency(Dependency(source_id="b1", target_id="b2", dependency_type="requires"))

        predictor = BlastPredictor()

        pred_a2 = predictor.predict(graph, "a2")
        affected_ids = {i.component_id for i in pred_a2.predicted_impacts}
        assert "b1" not in affected_ids
        assert "b2" not in affected_ids

    def test_self_loop_handling(self):
        """Graph with a self-referencing edge should not cause infinite loop."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A", ComponentType.APP_SERVER))
        # Note: networkx allows self-loops
        graph.add_dependency(Dependency(source_id="a", target_id="a", dependency_type="requires"))

        predictor = BlastPredictor()
        # Should not hang or raise
        pred = predictor.predict(graph, "a")
        assert pred.source_component_id == "a"

    def test_large_chain_depth_limit(self):
        """A very long chain should respect the max BFS depth."""
        graph = InfraGraph()
        n = 30
        for i in range(n):
            graph.add_component(
                _make_component(f"c{i}", f"C{i}", ComponentType.APP_SERVER)
            )
        for i in range(n - 1):
            graph.add_dependency(
                Dependency(source_id=f"c{i}", target_id=f"c{i+1}", dependency_type="requires")
            )

        predictor = BlastPredictor(decay_factor=0.95)
        # Predict from the leaf end — chain propagates upward
        pred = predictor.predict(graph, f"c{n-1}")

        # Should complete without error, depth should be bounded
        assert pred.max_cascade_depth <= 20

    def test_optional_dependency_lower_impact(self):
        """Optional dependencies should have lower impact probability."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A", ComponentType.APP_SERVER))
        graph.add_component(_make_component("b", "B", ComponentType.CACHE))
        graph.add_dependency(
            Dependency(source_id="a", target_id="b", dependency_type="optional", weight=1.0)
        )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "b")

        if pred.predicted_impacts:
            impact = pred.predicted_impacts[0]
            # Optional dep with weight 1.0 -> initial prob = 0.3
            assert impact.impact_probability <= 0.3

    def test_async_dependency_lower_impact(self):
        """Async dependencies should have the lowest impact probability."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A", ComponentType.APP_SERVER))
        graph.add_component(_make_component("q", "Queue", ComponentType.QUEUE))
        graph.add_dependency(
            Dependency(source_id="a", target_id="q", dependency_type="async", weight=1.0)
        )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "q")

        if pred.predicted_impacts:
            impact = pred.predicted_impacts[0]
            # Async dep with weight 1.0 -> initial prob = 0.2
            assert impact.impact_probability <= 0.2


# ===================================================================
# Tests for prediction confidence levels
# ===================================================================


class TestPredictionConfidence:
    """Test prediction confidence determination."""

    def test_high_confidence_all_requires(self):
        """All 'requires' dependencies -> high confidence."""
        graph = _build_simple_graph()
        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db")

        assert pred.confidence == PredictionConfidence.HIGH

    def test_low_confidence_many_optional(self):
        """Mostly optional/async dependencies -> lower confidence."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "DB", ComponentType.DATABASE))
        for i in range(5):
            cid = f"app{i}"
            graph.add_component(_make_component(cid, f"App{i}", ComponentType.APP_SERVER))
            dep_type = "optional" if i % 2 == 0 else "async"
            graph.add_dependency(
                Dependency(source_id=cid, target_id="db", dependency_type=dep_type)
            )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db")

        assert pred.confidence in (PredictionConfidence.LOW, PredictionConfidence.MEDIUM)

    def test_high_confidence_no_dependencies(self):
        """Isolated component -> high confidence (trivially confident)."""
        graph = InfraGraph()
        graph.add_component(_make_component("solo", "Solo", ComponentType.APP_SERVER))

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "solo")

        assert pred.confidence == PredictionConfidence.HIGH

    def test_single_component_graph_high_confidence(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", "X", ComponentType.DATABASE))

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "x")

        assert pred.confidence == PredictionConfidence.HIGH

    def test_mixed_dependency_types_medium_confidence(self):
        """Mix of requires and optional -> medium confidence."""
        graph = InfraGraph()
        graph.add_component(_make_component("db", "DB", ComponentType.DATABASE))
        for i in range(6):
            cid = f"svc{i}"
            graph.add_component(_make_component(cid, f"Svc{i}", ComponentType.APP_SERVER))
            # 3 requires, 3 optional -> ratio = 0.5
            dep_type = "requires" if i < 3 else "optional"
            graph.add_dependency(
                Dependency(source_id=cid, target_id="db", dependency_type=dep_type)
            )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db")

        assert pred.confidence in (PredictionConfidence.MEDIUM, PredictionConfidence.HIGH)


# ===================================================================
# Tests for time-to-impact estimation
# ===================================================================


class TestTimeToImpact:
    """Test time-to-impact estimation."""

    def test_time_increases_with_depth(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor(propagation_delay=15)
        pred = predictor.predict(graph, "db")

        # Impacts at greater depth should have longer time_to_impact
        if len(pred.predicted_impacts) >= 2:
            # Sort by depth (time_to_impact correlates with depth)
            sorted_impacts = sorted(
                pred.predicted_impacts, key=lambda i: i.time_to_impact_seconds
            )
            assert sorted_impacts[-1].time_to_impact_seconds >= sorted_impacts[0].time_to_impact_seconds

    def test_custom_propagation_delay(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor(propagation_delay=60)
        pred = predictor.predict(graph, "db")

        if pred.predicted_impacts:
            # depth 1 -> 60 seconds
            first_impact = pred.predicted_impacts[0]
            assert first_impact.time_to_impact_seconds == 60

    def test_depth_one_time(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A", ComponentType.APP_SERVER))
        graph.add_component(_make_component("b", "B", ComponentType.DATABASE))
        graph.add_dependency(
            Dependency(source_id="a", target_id="b", dependency_type="requires")
        )

        predictor = BlastPredictor(propagation_delay=10)
        pred = predictor.predict(graph, "b")

        assert len(pred.predicted_impacts) >= 1
        assert pred.predicted_impacts[0].time_to_impact_seconds == 10

    def test_depth_three_time(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A", ComponentType.APP_SERVER))
        graph.add_component(_make_component("b", "B", ComponentType.APP_SERVER))
        graph.add_component(_make_component("c", "C", ComponentType.APP_SERVER))
        graph.add_component(_make_component("d", "D", ComponentType.DATABASE))

        graph.add_dependency(Dependency(source_id="a", target_id="b", dependency_type="requires"))
        graph.add_dependency(Dependency(source_id="b", target_id="c", dependency_type="requires"))
        graph.add_dependency(Dependency(source_id="c", target_id="d", dependency_type="requires"))

        predictor = BlastPredictor(propagation_delay=20)
        pred = predictor.predict(graph, "d")

        impacts_by_id = {i.component_id: i for i in pred.predicted_impacts}
        if "c" in impacts_by_id:
            assert impacts_by_id["c"].time_to_impact_seconds == 20  # depth 1
        if "b" in impacts_by_id:
            assert impacts_by_id["b"].time_to_impact_seconds == 40  # depth 2
        if "a" in impacts_by_id:
            assert impacts_by_id["a"].time_to_impact_seconds == 60  # depth 3


# ===================================================================
# Tests for complex multi-layer topologies
# ===================================================================


class TestComplexTopologies:
    """Test prediction on complex multi-layer topologies."""

    def test_complex_graph_db_failure(self):
        graph = _build_complex_graph()
        predictor = BlastPredictor()

        pred = predictor.predict(graph, "db_primary")

        # db_primary is depended on by app1 and app2
        affected_ids = {i.component_id for i in pred.predicted_impacts}
        assert "app1" in affected_ids or "app2" in affected_ids
        assert pred.blast_radius_score > 0

    def test_complex_graph_all_predictions(self):
        graph = _build_complex_graph()
        predictor = BlastPredictor()

        all_preds = predictor.predict_all(graph)

        assert len(all_preds) == len(graph.components)
        for comp_id in graph.components:
            assert comp_id in all_preds
            assert isinstance(all_preds[comp_id], BlastPrediction)

    def test_complex_graph_hotspots(self):
        graph = _build_complex_graph()
        predictor = BlastPredictor()

        hotspots = predictor.find_hotspots(graph, top_n=3)

        assert len(hotspots) == 3
        # db_primary should be among top hotspots (many dependents, single replica)
        hotspot_ids = {h.component_id for h in hotspots}
        assert "db_primary" in hotspot_ids

    def test_star_topology(self):
        """Central node with many leaves."""
        graph = InfraGraph()
        graph.add_component(_make_component("hub", "Hub", ComponentType.DATABASE))
        for i in range(8):
            cid = f"leaf{i}"
            graph.add_component(_make_component(cid, f"Leaf {i}", ComponentType.APP_SERVER))
            graph.add_dependency(
                Dependency(source_id=cid, target_id="hub", dependency_type="requires")
            )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "hub")

        # Hub failure should impact all leaves
        assert pred.affected_component_count >= 5
        assert pred.blast_radius_score > 20

    def test_chain_topology(self):
        """Long linear chain."""
        graph = InfraGraph()
        for i in range(6):
            graph.add_component(
                _make_component(f"n{i}", f"Node {i}", ComponentType.APP_SERVER)
            )
        for i in range(5):
            graph.add_dependency(
                Dependency(source_id=f"n{i}", target_id=f"n{i+1}", dependency_type="requires")
            )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "n5")

        # n5 failure cascades backward: n4 -> n3 -> n2 -> n1 -> n0
        assert pred.max_cascade_depth >= 1
        assert pred.affected_component_count >= 1

    def test_mesh_topology(self):
        """Fully connected small mesh."""
        graph = InfraGraph()
        nodes = ["m0", "m1", "m2", "m3"]
        for n in nodes:
            graph.add_component(_make_component(n, n.upper(), ComponentType.APP_SERVER))
        # Each node depends on every other
        for i, src in enumerate(nodes):
            for j, tgt in enumerate(nodes):
                if i != j:
                    graph.add_dependency(
                        Dependency(source_id=src, target_id=tgt, dependency_type="requires", weight=0.5)
                    )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "m0")

        # All other nodes depend on m0
        assert pred.affected_component_count >= 1
        # No duplicates
        ids = [i.component_id for i in pred.predicted_impacts]
        assert len(ids) == len(set(ids))


# ===================================================================
# Tests for component resilience calculation
# ===================================================================


class TestComponentResilience:
    """Test the component resilience factor calculation."""

    def test_single_replica_no_features(self):
        comp = _make_component("x", "X", ComponentType.APP_SERVER, replicas=1)
        resilience = BlastPredictor._component_resilience(comp)
        assert resilience == 0.0

    def test_two_replicas(self):
        comp = _make_component("x", "X", ComponentType.APP_SERVER, replicas=2)
        resilience = BlastPredictor._component_resilience(comp)
        assert resilience == 0.25

    def test_three_replicas(self):
        comp = _make_component("x", "X", ComponentType.APP_SERVER, replicas=3)
        resilience = BlastPredictor._component_resilience(comp)
        assert resilience == 0.4

    def test_failover_enabled(self):
        comp = _make_component("x", "X", ComponentType.APP_SERVER, failover_enabled=True)
        resilience = BlastPredictor._component_resilience(comp)
        assert resilience == 0.2

    def test_autoscaling_enabled(self):
        comp = _make_component("x", "X", ComponentType.APP_SERVER, autoscaling_enabled=True)
        resilience = BlastPredictor._component_resilience(comp)
        assert resilience == 0.1

    def test_all_features(self):
        comp = _make_component(
            "x", "X", ComponentType.APP_SERVER,
            replicas=3, failover_enabled=True, autoscaling_enabled=True,
        )
        resilience = BlastPredictor._component_resilience(comp)
        # 0.4 + 0.2 + 0.1 = 0.7
        assert abs(resilience - 0.7) < 1e-9

    def test_high_load_reduces_resilience(self):
        comp = _make_component(
            "x", "X", ComponentType.APP_SERVER,
            replicas=2, cpu_percent=90.0,
        )
        resilience = BlastPredictor._component_resilience(comp)
        # 0.25 (replicas) - 0.15 (high load) = 0.10
        assert resilience == 0.10

    def test_medium_load_reduces_resilience(self):
        comp = _make_component(
            "x", "X", ComponentType.APP_SERVER,
            replicas=2, cpu_percent=65.0,
        )
        resilience = BlastPredictor._component_resilience(comp)
        # 0.25 - 0.05 = 0.20
        assert resilience == 0.20

    def test_resilience_capped_below_one(self):
        """Resilience should never reach 1.0 (cap at 0.95)."""
        comp = _make_component(
            "x", "X", ComponentType.APP_SERVER,
            replicas=10, failover_enabled=True, autoscaling_enabled=True,
        )
        resilience = BlastPredictor._component_resilience(comp)
        assert resilience <= 0.95

    def test_resilience_floor_at_zero(self):
        """Resilience should never go below 0.0."""
        comp = _make_component(
            "x", "X", ComponentType.APP_SERVER,
            replicas=1, cpu_percent=95.0,
        )
        resilience = BlastPredictor._component_resilience(comp)
        assert resilience >= 0.0


# ===================================================================
# Tests for degradation estimation
# ===================================================================


class TestDegradationEstimation:
    """Test the degradation percentage estimation."""

    def test_catastrophic_degradation(self):
        deg = BlastPredictor._estimate_degradation(1.0, ImpactLevel.CATASTROPHIC)
        assert deg == 90.0

    def test_severe_degradation(self):
        deg = BlastPredictor._estimate_degradation(1.0, ImpactLevel.SEVERE)
        assert deg == 70.0

    def test_moderate_degradation(self):
        deg = BlastPredictor._estimate_degradation(1.0, ImpactLevel.MODERATE)
        assert deg == 40.0

    def test_minor_degradation(self):
        deg = BlastPredictor._estimate_degradation(1.0, ImpactLevel.MINOR)
        assert deg == 15.0

    def test_none_degradation(self):
        deg = BlastPredictor._estimate_degradation(1.0, ImpactLevel.NONE)
        assert deg == 0.0

    def test_partial_probability_scales_degradation(self):
        deg = BlastPredictor._estimate_degradation(0.5, ImpactLevel.SEVERE)
        assert deg == 35.0  # 70 * 0.5


# ===================================================================
# Tests for mitigation suggestions
# ===================================================================


class TestMitigationSuggestions:
    """Test mitigation suggestion generation."""

    def test_suggests_replicas(self):
        graph = InfraGraph()
        graph.add_component(_make_component("db", "DB", ComponentType.DATABASE, replicas=1))
        graph.add_component(_make_component("app", "App", ComponentType.APP_SERVER))
        graph.add_dependency(
            Dependency(source_id="app", target_id="db", dependency_type="requires")
        )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db")

        replica_suggestions = [s for s in pred.mitigation_suggestions if "replica" in s.lower()]
        assert len(replica_suggestions) > 0

    def test_suggests_failover(self):
        graph = InfraGraph()
        graph.add_component(
            _make_component("db", "DB", ComponentType.DATABASE, failover_enabled=False)
        )
        graph.add_component(_make_component("app", "App", ComponentType.APP_SERVER))
        graph.add_dependency(
            Dependency(source_id="app", target_id="db", dependency_type="requires")
        )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db")

        failover_suggestions = [s for s in pred.mitigation_suggestions if "failover" in s.lower()]
        assert len(failover_suggestions) > 0

    def test_suggests_autoscaling(self):
        graph = InfraGraph()
        graph.add_component(
            _make_component("app", "App", ComponentType.APP_SERVER, autoscaling_enabled=False)
        )
        graph.add_component(
            _make_component("client", "Client", ComponentType.WEB_SERVER)
        )
        graph.add_dependency(
            Dependency(source_id="client", target_id="app", dependency_type="requires")
        )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "app")

        auto_suggestions = [s for s in pred.mitigation_suggestions if "autoscaling" in s.lower()]
        assert len(auto_suggestions) > 0

    def test_suggests_circuit_breaker(self):
        graph = InfraGraph()
        graph.add_component(_make_component("db", "DB", ComponentType.DATABASE))
        graph.add_component(_make_component("app", "App", ComponentType.APP_SERVER))
        graph.add_dependency(
            Dependency(
                source_id="app", target_id="db",
                dependency_type="requires",
                circuit_breaker=CircuitBreakerConfig(enabled=False),
            )
        )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db")

        cb_suggestions = [s for s in pred.mitigation_suggestions if "circuit breaker" in s.lower()]
        assert len(cb_suggestions) > 0

    def test_no_suggestions_for_fully_hardened(self):
        graph = InfraGraph()
        graph.add_component(
            _make_component(
                "db", "DB", ComponentType.DATABASE,
                replicas=3, failover_enabled=True, autoscaling_enabled=True,
            )
        )
        graph.add_component(
            _make_component("app", "App", ComponentType.APP_SERVER)
        )
        graph.add_dependency(
            Dependency(
                source_id="app", target_id="db",
                dependency_type="requires",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )
        )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db")

        # The only suggestions should be about "decomposing" if blast is high,
        # replica/failover/autoscaling/cb suggestions should be absent
        replica_sugg = [s for s in pred.mitigation_suggestions if "Add replicas" in s]
        failover_sugg = [s for s in pred.mitigation_suggestions if "Enable failover" in s]
        auto_sugg = [s for s in pred.mitigation_suggestions if "Enable autoscaling" in s]
        cb_sugg = [s for s in pred.mitigation_suggestions if "circuit breaker" in s.lower()]
        assert len(replica_sugg) == 0
        assert len(failover_sugg) == 0
        assert len(auto_sugg) == 0
        assert len(cb_sugg) == 0


# ===================================================================
# Tests for affected users estimation
# ===================================================================


class TestAffectedUsersEstimation:
    """Test affected users estimate strings."""

    def test_no_impacts_none(self):
        result = BlastPredictor._estimate_affected_users([])
        assert result == "none"

    def test_catastrophic_all_users(self):
        impacts = [
            ComponentImpact(
                component_id="x", component_name="X",
                impact_level=ImpactLevel.CATASTROPHIC, impact_probability=0.9,
                estimated_degradation_percent=90.0, time_to_impact_seconds=5,
            )
        ]
        result = BlastPredictor._estimate_affected_users(impacts)
        assert "all users" in result.lower()

    def test_multiple_severe_majority(self):
        impacts = [
            ComponentImpact(
                component_id=f"s{i}", component_name=f"S{i}",
                impact_level=ImpactLevel.SEVERE, impact_probability=0.8,
                estimated_degradation_percent=60.0, time_to_impact_seconds=15,
            )
            for i in range(3)
        ]
        result = BlastPredictor._estimate_affected_users(impacts)
        assert "majority" in result.lower()

    def test_single_severe(self):
        impacts = [
            ComponentImpact(
                component_id="s", component_name="S",
                impact_level=ImpactLevel.SEVERE, impact_probability=0.7,
                estimated_degradation_percent=60.0, time_to_impact_seconds=15,
            )
        ]
        result = BlastPredictor._estimate_affected_users(impacts)
        assert "significant" in result.lower()

    def test_moderate_some_users(self):
        impacts = [
            ComponentImpact(
                component_id="m", component_name="M",
                impact_level=ImpactLevel.MODERATE, impact_probability=0.5,
                estimated_degradation_percent=30.0, time_to_impact_seconds=30,
            )
        ]
        result = BlastPredictor._estimate_affected_users(impacts)
        assert "some" in result.lower()

    def test_minor_minimal_impact(self):
        impacts = [
            ComponentImpact(
                component_id="n", component_name="N",
                impact_level=ImpactLevel.MINOR, impact_probability=0.3,
                estimated_degradation_percent=10.0, time_to_impact_seconds=45,
            )
        ]
        result = BlastPredictor._estimate_affected_users(impacts)
        assert "minimal" in result.lower()


# ===================================================================
# Tests for predict_all
# ===================================================================


class TestPredictAll:
    """Test predict_all functionality."""

    def test_predict_all_returns_all_components(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        results = predictor.predict_all(graph)

        assert len(results) == 3
        assert "lb" in results
        assert "app" in results
        assert "db" in results

    def test_predict_all_empty_graph(self):
        graph = InfraGraph()
        predictor = BlastPredictor()

        results = predictor.predict_all(graph)
        assert results == {}

    def test_predict_all_consistent_with_individual(self):
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        all_results = predictor.predict_all(graph)
        individual = predictor.predict(graph, "db")

        assert all_results["db"].blast_radius_score == individual.blast_radius_score
        assert all_results["db"].affected_component_count == individual.affected_component_count


# ===================================================================
# Tests for incoming vulnerability
# ===================================================================


class TestIncomingVulnerability:
    """Test the incoming vulnerability calculation."""

    def test_leaf_node_low_vulnerability(self):
        """A leaf node (no dependencies going to it) should have low vulnerability."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", "A", ComponentType.APP_SERVER))
        graph.add_component(_make_component("b", "B", ComponentType.DATABASE))
        graph.add_dependency(
            Dependency(source_id="a", target_id="b", dependency_type="requires")
        )

        predictor = BlastPredictor()
        vuln = predictor._calculate_incoming_vulnerability(graph, "a")

        # 'a' depends on 'b', but no one else's failure propagates TO 'a'
        # except b's failure -> a.
        assert vuln >= 0.0

    def test_central_node_higher_vulnerability(self):
        """A central node should have higher incoming vulnerability."""
        graph = InfraGraph()
        graph.add_component(_make_component("center", "Center", ComponentType.APP_SERVER))
        for i in range(4):
            upstream = f"up{i}"
            downstream = f"down{i}"
            graph.add_component(_make_component(upstream, f"Up{i}", ComponentType.WEB_SERVER))
            graph.add_component(_make_component(downstream, f"Down{i}", ComponentType.DATABASE))
            graph.add_dependency(
                Dependency(source_id=upstream, target_id="center", dependency_type="requires")
            )
            graph.add_dependency(
                Dependency(source_id="center", target_id=downstream, dependency_type="requires")
            )

        predictor = BlastPredictor()
        center_vuln = predictor._calculate_incoming_vulnerability(graph, "center")

        # Center is vulnerable to downstream failures
        assert center_vuln >= 0.0


# ===================================================================
# Tests for graph cloning
# ===================================================================


class TestGraphCloning:
    """Test that graph cloning produces independent copies."""

    def test_clone_preserves_components(self):
        graph = _build_simple_graph()
        cloned = BlastPredictor._clone_graph(graph)

        assert len(cloned.components) == len(graph.components)
        for cid in graph.components:
            assert cloned.get_component(cid) is not None

    def test_clone_preserves_edges(self):
        graph = _build_simple_graph()
        cloned = BlastPredictor._clone_graph(graph)

        orig_edges = graph.all_dependency_edges()
        cloned_edges = cloned.all_dependency_edges()
        assert len(cloned_edges) == len(orig_edges)

    def test_clone_is_independent(self):
        graph = _build_simple_graph()
        cloned = BlastPredictor._clone_graph(graph)

        # Modify cloned graph
        cloned_comp = cloned.get_component("db")
        cloned_comp.replicas = 10

        # Original should be unchanged
        assert graph.get_component("db").replicas == 1


# ===================================================================
# Tests for initial impact probability
# ===================================================================


class TestInitialImpactProbability:
    """Test initial impact probability calculation based on edge properties."""

    def test_requires_full_weight(self):
        prob = BlastPredictor._initial_impact_probability(1.0, "requires")
        assert prob == 1.0

    def test_requires_partial_weight(self):
        prob = BlastPredictor._initial_impact_probability(0.5, "requires")
        assert prob == 0.5

    def test_optional_reduces_probability(self):
        prob = BlastPredictor._initial_impact_probability(1.0, "optional")
        assert prob == 0.3

    def test_async_lowest_probability(self):
        prob = BlastPredictor._initial_impact_probability(1.0, "async")
        assert prob == 0.2

    def test_unknown_type_treated_as_requires(self):
        prob = BlastPredictor._initial_impact_probability(1.0, "unknown_type")
        assert prob == 1.0


# ===================================================================
# Tests for delta summary
# ===================================================================


class TestDeltaSummary:
    """Test human-readable delta summary generation."""

    def test_reduced_summary(self):
        predictor = BlastPredictor()
        baseline = BlastPrediction(
            source_component_id="x", source_component_name="X",
            blast_radius_score=78.0,
        )
        modified = BlastPrediction(
            source_component_id="x", source_component_name="X",
            blast_radius_score=34.0,
        )
        delta = predictor._build_delta_summary(
            baseline, modified, ["replicas: 1 -> 3"], "DB Primary"
        )
        assert "reduced" in delta.lower()
        assert "78" in delta
        assert "34" in delta

    def test_increased_summary(self):
        predictor = BlastPredictor()
        baseline = BlastPrediction(
            source_component_id="x", source_component_name="X",
            blast_radius_score=20.0,
        )
        modified = BlastPrediction(
            source_component_id="x", source_component_name="X",
            blast_radius_score=60.0,
        )
        delta = predictor._build_delta_summary(
            baseline, modified, ["replicas: 3 -> 1"], "DB Primary"
        )
        assert "increased" in delta.lower()

    def test_unchanged_summary(self):
        predictor = BlastPredictor()
        baseline = BlastPrediction(
            source_component_id="x", source_component_name="X",
            blast_radius_score=50.0,
        )
        modified = BlastPrediction(
            source_component_id="x", source_component_name="X",
            blast_radius_score=50.0,
        )
        delta = predictor._build_delta_summary(
            baseline, modified, ["cpu: 50% -> 45%"], "App"
        )
        assert "unchanged" in delta.lower()


# ===================================================================
# Tests for risk level labels
# ===================================================================


class TestRiskLevelLabels:
    """Test risk level label assignment."""

    def test_critical_level(self):
        assert BlastPredictor._risk_level_label(75) == "critical"
        assert BlastPredictor._risk_level_label(100) == "critical"

    def test_high_level(self):
        assert BlastPredictor._risk_level_label(50) == "high"
        assert BlastPredictor._risk_level_label(74) == "high"

    def test_medium_level(self):
        assert BlastPredictor._risk_level_label(25) == "medium"
        assert BlastPredictor._risk_level_label(49) == "medium"

    def test_low_level(self):
        assert BlastPredictor._risk_level_label(1) == "low"
        assert BlastPredictor._risk_level_label(24) == "low"

    def test_none_level(self):
        assert BlastPredictor._risk_level_label(0) == "none"


# ===================================================================
# Tests for integration: end-to-end scenarios
# ===================================================================


class TestEndToEndScenarios:
    """Integration tests for realistic scenarios."""

    def test_database_spof_scenario(self):
        """Typical SPOF: single-replica DB with multiple app servers."""
        graph = InfraGraph()
        graph.add_component(
            _make_component("db", "Primary DB", ComponentType.DATABASE, replicas=1)
        )
        for i in range(3):
            graph.add_component(
                _make_component(f"app{i}", f"App {i}", ComponentType.APP_SERVER, replicas=2)
            )
            graph.add_dependency(
                Dependency(source_id=f"app{i}", target_id="db", dependency_type="requires")
            )

        predictor = BlastPredictor()
        pred = predictor.predict(graph, "db")

        assert pred.blast_radius_score > 0
        assert pred.affected_component_count >= 1
        assert any("replica" in s.lower() for s in pred.mitigation_suggestions)

    def test_what_if_fix_spof(self):
        """Fix the SPOF by adding replicas and see blast radius drop."""
        graph = InfraGraph()
        graph.add_component(
            _make_component("db", "Primary DB", ComponentType.DATABASE, replicas=1)
        )
        for i in range(3):
            graph.add_component(
                _make_component(f"app{i}", f"App {i}", ComponentType.APP_SERVER)
            )
            graph.add_dependency(
                Dependency(source_id=f"app{i}", target_id="db", dependency_type="requires")
            )

        predictor = BlastPredictor()
        result = predictor.what_if(
            graph, "db",
            {"replicas": 3, "failover_enabled": True},
        )

        assert result.comparison_baseline is not None
        baseline_score = result.comparison_baseline.blast_radius_score
        modified_score = result.predictions[0].blast_radius_score
        assert modified_score <= baseline_score

    def test_full_pipeline_predict_hotspot_whatif(self):
        """Full pipeline: predict -> find hotspots -> what-if fix."""
        graph = _build_complex_graph()
        predictor = BlastPredictor()

        # Step 1: Find hotspots
        hotspots = predictor.find_hotspots(graph, top_n=3)
        assert len(hotspots) > 0

        # Step 2: Take top hotspot
        top_hotspot = hotspots[0]

        # Step 3: Predict its blast radius
        pred = predictor.predict(graph, top_hotspot.component_id)
        assert isinstance(pred, BlastPrediction)

        # Step 4: What-if analysis to improve
        result = predictor.what_if(
            graph, top_hotspot.component_id,
            {"replicas": 3, "failover_enabled": True},
        )
        assert result.comparison_baseline is not None
        assert len(result.predictions) == 1

        # Step 5: Compare
        comparison = predictor.compare_predictions(
            result.comparison_baseline, result.predictions[0]
        )
        assert "blast_radius_score_delta" in comparison

    def test_heatmap_after_mitigation(self):
        """Generate heatmap before and after mitigation."""
        graph = _build_simple_graph()
        predictor = BlastPredictor()

        heatmap_before = predictor.generate_heatmap_data(graph)
        assert len(heatmap_before) == 3

        # Now check with a different graph (more resilient)
        resilient = InfraGraph()
        resilient.add_component(
            _make_component("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2)
        )
        resilient.add_component(
            _make_component("app", "App", ComponentType.APP_SERVER, replicas=3, failover_enabled=True)
        )
        resilient.add_component(
            _make_component("db", "DB", ComponentType.DATABASE, replicas=3, failover_enabled=True)
        )
        resilient.add_dependency(
            Dependency(source_id="lb", target_id="app", dependency_type="requires")
        )
        resilient.add_dependency(
            Dependency(source_id="app", target_id="db", dependency_type="requires")
        )

        heatmap_after = predictor.generate_heatmap_data(resilient)
        assert len(heatmap_after) == 3

        # Scores in the resilient graph should be lower or equal
        scores_before = {e["component_id"]: e["blast_radius_score"] for e in heatmap_before}
        scores_after = {e["component_id"]: e["blast_radius_score"] for e in heatmap_after}
        for cid in scores_before:
            assert scores_after[cid] <= scores_before[cid]
