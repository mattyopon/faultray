"""Tests for the Carbon Footprint Engine."""

from faultray.model.components import (
    Component,
    ComponentType,
    RegionConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.carbon_engine import (
    CARBON_FACTORS_G_PER_CPU_HOUR,
    CarbonEngine,
    CarbonReport,
    _HOURS_PER_YEAR,
)


def _build_carbon_graph() -> InfraGraph:
    """Build a test graph for carbon analysis."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
        region=RegionConfig(region="us-east-1"),
        metrics=ResourceMetrics(cpu_percent=60),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=2,
        region=RegionConfig(region="eu-west-1"),
        metrics=ResourceMetrics(cpu_percent=70),
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE,
        replicas=1,
        region=RegionConfig(region="europe-north1"),
        metrics=ResourceMetrics(cpu_percent=20),
    ))
    return graph


def test_analyze_returns_report():
    """analyze() should return a CarbonReport."""
    graph = _build_carbon_graph()
    engine = CarbonEngine(graph)
    report = engine.analyze()
    assert isinstance(report, CarbonReport)
    assert report.total_annual_kg > 0


def test_per_component_all_present():
    """Every component should appear in per_component output."""
    graph = _build_carbon_graph()
    engine = CarbonEngine(graph)
    report = engine.analyze()
    assert set(report.per_component.keys()) == set(graph.components.keys())


def test_total_equals_sum_of_components():
    """Total annual kg should equal sum of per-component values."""
    graph = _build_carbon_graph()
    engine = CarbonEngine(graph)
    report = engine.analyze()
    total_from_components = sum(report.per_component.values())
    assert abs(report.total_annual_kg - total_from_components) < 0.01


def test_more_replicas_more_carbon():
    """Component with more replicas should emit more CO2."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="small", name="Small", type=ComponentType.APP_SERVER,
        replicas=1, region=RegionConfig(region="us-east-1"),
    ))
    graph.add_component(Component(
        id="large", name="Large", type=ComponentType.APP_SERVER,
        replicas=10, region=RegionConfig(region="us-east-1"),
    ))
    engine = CarbonEngine(graph)
    report = engine.analyze()
    assert report.per_component["large"] > report.per_component["small"]
    assert report.per_component["large"] == report.per_component["small"] * 10


def test_green_region_less_carbon():
    """Component in a green region should emit less CO2."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="dirty", name="Dirty", type=ComponentType.APP_SERVER,
        replicas=1, region=RegionConfig(region="ap-south-1"),  # 0.60 g/CPU-h
    ))
    graph.add_component(Component(
        id="clean", name="Clean", type=ComponentType.APP_SERVER,
        replicas=1, region=RegionConfig(region="europe-north1"),  # 0.05 g/CPU-h
    ))
    engine = CarbonEngine(graph)
    report = engine.analyze()
    assert report.per_component["clean"] < report.per_component["dirty"]


def test_car_km_equivalent():
    """Car km equivalent should be proportional to total emissions."""
    graph = _build_carbon_graph()
    engine = CarbonEngine(graph)
    report = engine.analyze()
    assert report.equivalent_car_km > 0
    # Should be total_g / 120g per km
    total_g = report.total_annual_kg * 1000
    expected_km = total_g / 120.0
    assert abs(report.equivalent_car_km - expected_km) < 0.1


def test_sustainability_score_range():
    """Sustainability score should be between 0 and 100."""
    graph = _build_carbon_graph()
    engine = CarbonEngine(graph)
    report = engine.analyze()
    assert 0 <= report.sustainability_score <= 100


def test_green_region_higher_sustainability():
    """Infrastructure in green regions should have higher sustainability score."""
    # All-green infrastructure
    green_graph = InfraGraph()
    green_graph.add_component(Component(
        id="a", name="A", type=ComponentType.APP_SERVER,
        replicas=1, region=RegionConfig(region="europe-north1"),
        metrics=ResourceMetrics(cpu_percent=50),
    ))

    # All-dirty infrastructure
    dirty_graph = InfraGraph()
    dirty_graph.add_component(Component(
        id="a", name="A", type=ComponentType.APP_SERVER,
        replicas=1, region=RegionConfig(region="ap-south-1"),
        metrics=ResourceMetrics(cpu_percent=50),
    ))

    green_report = CarbonEngine(green_graph).analyze()
    dirty_report = CarbonEngine(dirty_graph).analyze()
    assert green_report.sustainability_score > dirty_report.sustainability_score


def test_recommendations_generated():
    """Green recommendations should be generated for high-carbon components."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="high_carbon", name="High Carbon", type=ComponentType.APP_SERVER,
        replicas=5, region=RegionConfig(region="ap-south-1"),
        metrics=ResourceMetrics(cpu_percent=60),
    ))
    engine = CarbonEngine(graph)
    report = engine.analyze()
    assert len(report.green_recommendations) > 0
    # Should suggest region migration
    region_recs = [
        r for r in report.green_recommendations if "suggested_region" in r
    ]
    assert len(region_recs) > 0


def test_consolidation_recommendation():
    """Over-provisioned components should get consolidation recommendations."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="overprovisioned", name="Over", type=ComponentType.APP_SERVER,
        replicas=5, region=RegionConfig(region="us-east-1"),
        metrics=ResourceMetrics(cpu_percent=10),  # very low utilization
    ))
    engine = CarbonEngine(graph)
    report = engine.analyze()
    consolidation_recs = [
        r for r in report.green_recommendations if "consolidate" in r.get("recommendation", "").lower()
    ]
    assert len(consolidation_recs) > 0


def test_to_dict():
    """to_dict() should produce a JSON-serializable dict."""
    import json

    graph = _build_carbon_graph()
    engine = CarbonEngine(graph)
    report = engine.analyze()
    d = report.to_dict()
    serialized = json.dumps(d)
    assert isinstance(serialized, str)
    assert "total_annual_kg" in d
    assert "sustainability_score" in d


def test_empty_graph():
    """Engine should handle an empty graph."""
    graph = InfraGraph()
    engine = CarbonEngine(graph)
    report = engine.analyze()
    assert report.total_annual_kg == 0
    assert report.equivalent_car_km == 0
    assert report.sustainability_score == 100.0


def test_unknown_region_uses_default():
    """Unknown region should use the default carbon factor."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="unknown", name="Unknown", type=ComponentType.APP_SERVER,
        replicas=1, region=RegionConfig(region="my-custom-region"),
    ))
    engine = CarbonEngine(graph)
    report = engine.analyze()
    expected_kg = 1 * _HOURS_PER_YEAR * CARBON_FACTORS_G_PER_CPU_HOUR["default"] / 1000
    assert abs(report.per_component["unknown"] - expected_kg) < 0.01
