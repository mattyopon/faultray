"""Tests for the FaultRay public Python SDK surface."""

from __future__ import annotations


class TestSDKVersion:
    def test_version_is_string(self):
        import faultray
        assert isinstance(faultray.__version__, str)

    def test_version_is_10_0_0(self):
        import faultray
        assert faultray.__version__ == "10.0.0"


class TestSDKAllExports:
    def test_all_contains_expected_names(self):
        import faultray
        expected = [
            "InfraGraph", "Component", "ComponentType", "Dependency",
            "load_yaml",
            "SimulationEngine", "SimulationReport",
            "DynamicSimulationEngine", "OpsSimulationEngine",
            "CascadeEngine",
            "compute_three_layer_model", "compute_five_layer_model",
            "run_monte_carlo",
            "CostImpactEngine", "SecurityResilienceEngine",
        ]
        for name in expected:
            assert name in faultray.__all__, f"{name} missing from __all__"


class TestSDKImports:
    """Verify that each name in __all__ can be imported."""

    def test_import_infragraph(self):
        from faultray import InfraGraph
        assert InfraGraph is not None

    def test_import_component(self):
        from faultray import Component, ComponentType, Dependency
        assert Component is not None
        assert ComponentType is not None
        assert Dependency is not None

    def test_import_load_yaml(self):
        from faultray import load_yaml
        assert callable(load_yaml)

    def test_import_simulation_engine(self):
        from faultray import SimulationEngine, SimulationReport
        assert SimulationEngine is not None
        assert SimulationReport is not None

    def test_import_dynamic_engine(self):
        from faultray import DynamicSimulationEngine
        assert DynamicSimulationEngine is not None

    def test_import_ops_engine(self):
        from faultray import OpsSimulationEngine
        assert OpsSimulationEngine is not None

    def test_import_cascade_engine(self):
        from faultray import CascadeEngine
        assert CascadeEngine is not None

    def test_import_availability_models(self):
        from faultray import compute_three_layer_model, compute_five_layer_model
        assert callable(compute_three_layer_model)
        assert callable(compute_five_layer_model)

    def test_import_monte_carlo(self):
        from faultray import run_monte_carlo
        assert callable(run_monte_carlo)

    def test_import_cost_engine(self):
        from faultray import CostImpactEngine
        assert CostImpactEngine is not None

    def test_import_security_engine(self):
        from faultray import SecurityResilienceEngine
        assert SecurityResilienceEngine is not None


class TestSDKLazyImportErrors:
    def test_nonexistent_attr_raises(self):
        import faultray
        import pytest
        with pytest.raises(AttributeError, match="no attribute"):
            _ = faultray.NonExistentThing


class TestSDKBasicUsage:
    """Verify the SDK can be used for a basic simulation workflow."""

    def test_create_graph_and_run(self):
        from faultray import InfraGraph, SimulationEngine
        graph = InfraGraph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults()
        # Empty graph produces a report with high resilience and no findings
        assert report.resilience_score >= 0
        assert isinstance(report.critical_findings, list)
