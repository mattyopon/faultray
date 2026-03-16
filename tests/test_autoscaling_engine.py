"""Tests for the Auto-Scaling Recommendation Engine."""

import json

import yaml

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    FailoverConfig,
    RegionConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph, Dependency
from faultray.simulator.autoscaling_engine import (
    AutoScalingRecommendation,
    AutoScalingRecommendationEngine,
    _DEFAULT_TARGET_UTILIZATION,
    _MAX_REPLICAS_CAP,
    _SCALE_TRIGGER_THRESHOLD,
)


def _build_graph() -> InfraGraph:
    """Build a test graph with varied components."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=30),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
        metrics=ResourceMetrics(cpu_percent=75, memory_percent=60),
        capacity=Capacity(max_connections=1000),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=85, memory_percent=70, disk_percent=50),
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=5),
    ))
    # Dependencies: lb -> app -> db, app -> cache
    from faultray.model.components import Dependency as DepModel
    graph.add_dependency(DepModel(source_id="lb", target_id="app"))
    graph.add_dependency(DepModel(source_id="app", target_id="db"))
    graph.add_dependency(DepModel(source_id="app", target_id="cache", dependency_type="optional"))
    return graph


def test_recommend_returns_all_components():
    """Recommendations should be generated for every component."""
    graph = _build_graph()
    engine = AutoScalingRecommendationEngine(graph)
    recs = engine.recommend()
    assert len(recs) == len(graph.components)
    ids = {r.component_id for r in recs}
    assert ids == set(graph.components.keys())


def test_recommend_sorted_by_confidence():
    """Recommendations should be sorted by confidence descending."""
    graph = _build_graph()
    engine = AutoScalingRecommendationEngine(graph)
    recs = engine.recommend()
    for i in range(len(recs) - 1):
        assert recs[i].confidence >= recs[i + 1].confidence


def test_high_utilization_gets_higher_confidence():
    """Component with higher utilization should get higher confidence."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="hot", name="Hot", type=ComponentType.APP_SERVER,
        replicas=1, metrics=ResourceMetrics(cpu_percent=95),
    ))
    graph.add_component(Component(
        id="cold", name="Cold", type=ComponentType.APP_SERVER,
        replicas=3, metrics=ResourceMetrics(cpu_percent=20),
    ))
    engine = AutoScalingRecommendationEngine(graph)
    recs = engine.recommend()
    hot_rec = next(r for r in recs if r.component_id == "hot")
    cold_rec = next(r for r in recs if r.component_id == "cold")
    assert hot_rec.confidence > cold_rec.confidence


def test_spof_increases_confidence():
    """Single replica with dependents should increase confidence."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="spof", name="SPOF", type=ComponentType.DATABASE,
        replicas=1, metrics=ResourceMetrics(cpu_percent=65),
    ))
    graph.add_component(Component(
        id="consumer", name="Consumer", type=ComponentType.APP_SERVER,
        replicas=2, metrics=ResourceMetrics(cpu_percent=65),
    ))
    from faultray.model.components import Dependency as DepModel
    graph.add_dependency(DepModel(source_id="consumer", target_id="spof"))

    engine = AutoScalingRecommendationEngine(graph)
    recs = engine.recommend()
    spof_rec = next(r for r in recs if r.component_id == "spof")
    consumer_rec = next(r for r in recs if r.component_id == "consumer")
    assert spof_rec.confidence > consumer_rec.confidence


def test_existing_autoscaling_lowers_confidence():
    """Components with autoscaling already enabled should have lower confidence."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="with_as", name="With AS", type=ComponentType.APP_SERVER,
        replicas=2, metrics=ResourceMetrics(cpu_percent=70),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="without_as", name="Without AS", type=ComponentType.APP_SERVER,
        replicas=2, metrics=ResourceMetrics(cpu_percent=70),
    ))
    engine = AutoScalingRecommendationEngine(graph)
    recs = engine.recommend()
    with_rec = next(r for r in recs if r.component_id == "with_as")
    without_rec = next(r for r in recs if r.component_id == "without_as")
    assert with_rec.confidence < without_rec.confidence


def test_max_replicas_capped():
    """Recommended max replicas should not exceed the cap."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="huge", name="Huge", type=ComponentType.APP_SERVER,
        replicas=15,
        metrics=ResourceMetrics(cpu_percent=90),
    ))
    engine = AutoScalingRecommendationEngine(graph)
    recs = engine.recommend()
    rec = recs[0]
    assert rec.recommended_max <= _MAX_REPLICAS_CAP


def test_recommended_min_le_max():
    """Recommended min should always be <= recommended max."""
    graph = _build_graph()
    engine = AutoScalingRecommendationEngine(graph)
    recs = engine.recommend()
    for r in recs:
        assert r.recommended_min <= r.recommended_max


def test_to_kubernetes_hpa_valid_yaml():
    """K8s HPA export should produce valid YAML."""
    rec = AutoScalingRecommendation(
        component_id="my_app",
        component_name="My App",
        current_replicas=3,
        recommended_min=3,
        recommended_max=10,
        target_utilization=70.0,
        scale_up_threshold=75.0,
        cooldown_seconds=300,
        confidence=0.8,
        reasoning="test",
    )
    hpa_yaml = rec.to_kubernetes_hpa()
    parsed = yaml.safe_load(hpa_yaml)
    assert parsed["kind"] == "HorizontalPodAutoscaler"
    assert parsed["apiVersion"] == "autoscaling/v2"
    assert parsed["spec"]["minReplicas"] == 3
    assert parsed["spec"]["maxReplicas"] == 10
    assert parsed["metadata"]["name"] == "my-app-hpa"
    # Check that the resource target is correct
    metrics = parsed["spec"]["metrics"]
    assert len(metrics) == 1
    assert metrics[0]["resource"]["target"]["averageUtilization"] == 70


def test_to_aws_asg_valid_json():
    """AWS ASG export should produce valid JSON."""
    rec = AutoScalingRecommendation(
        component_id="web_server",
        component_name="Web Server",
        current_replicas=2,
        recommended_min=2,
        recommended_max=8,
        target_utilization=70.0,
        scale_up_threshold=75.0,
        cooldown_seconds=300,
        confidence=0.7,
        reasoning="test",
    )
    asg_json = rec.to_aws_asg()
    parsed = json.loads(asg_json)
    assert parsed["MinSize"] == 2
    assert parsed["MaxSize"] == 8
    assert parsed["DefaultCooldown"] == 300
    assert "TargetTrackingScalingPolicy" in parsed


def test_export_all_k8s():
    """export_all_k8s should combine multiple HPA docs with --- separator."""
    graph = _build_graph()
    engine = AutoScalingRecommendationEngine(graph)
    combined = engine.export_all_k8s()
    # Should have multiple YAML documents
    docs = combined.split("---")
    assert len(docs) == len(graph.components)
    # Each doc should be valid YAML
    for doc in docs:
        parsed = yaml.safe_load(doc)
        assert parsed["kind"] == "HorizontalPodAutoscaler"


def test_export_all_aws():
    """export_all_aws should produce a valid JSON array."""
    graph = _build_graph()
    engine = AutoScalingRecommendationEngine(graph)
    combined = engine.export_all_aws()
    parsed = json.loads(combined)
    assert isinstance(parsed, list)
    assert len(parsed) == len(graph.components)


def test_reasoning_mentions_utilization():
    """Reasoning should mention utilization threshold."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="hot", name="Hot", type=ComponentType.APP_SERVER,
        replicas=1, metrics=ResourceMetrics(cpu_percent=90),
    ))
    engine = AutoScalingRecommendationEngine(graph)
    recs = engine.recommend()
    assert any("utilization" in r.reasoning.lower() for r in recs)


def test_empty_graph():
    """Engine should handle an empty graph without errors."""
    graph = InfraGraph()
    engine = AutoScalingRecommendationEngine(graph)
    recs = engine.recommend()
    assert recs == []


def test_low_utilization_component():
    """Component with low utilization should still get a recommendation."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="idle", name="Idle", type=ComponentType.APP_SERVER,
        replicas=5, metrics=ResourceMetrics(cpu_percent=5),
    ))
    engine = AutoScalingRecommendationEngine(graph)
    recs = engine.recommend()
    assert len(recs) == 1
    # Low utilization should have moderate confidence
    assert recs[0].confidence <= 0.6
