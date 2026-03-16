"""FaultRay — Zero-risk infrastructure chaos simulation."""

__version__ = "10.1.0"


def __getattr__(name: str):
    """Lazy imports for the public API surface.

    This ensures ``import faultray`` never fails even when optional
    dependencies (e.g. pydantic, networkx) are missing — individual
    symbols raise ImportError only when actually accessed.
    """
    _import_map = {
        # Model layer
        "InfraGraph": ("faultray.model.graph", "InfraGraph"),
        "Component": ("faultray.model.components", "Component"),
        "ComponentType": ("faultray.model.components", "ComponentType"),
        "Dependency": ("faultray.model.components", "Dependency"),
        "load_yaml": ("faultray.model.loader", "load_yaml"),
        # Simulation engines
        "SimulationEngine": ("faultray.simulator.engine", "SimulationEngine"),
        "SimulationReport": ("faultray.simulator.engine", "SimulationReport"),
        "DynamicSimulationEngine": ("faultray.simulator.dynamic_engine", "DynamicSimulationEngine"),
        "OpsSimulationEngine": ("faultray.simulator.ops_engine", "OpsSimulationEngine"),
        "CascadeEngine": ("faultray.simulator.cascade", "CascadeEngine"),
        # Availability models
        "compute_three_layer_model": (
            "faultray.simulator.availability_model", "compute_three_layer_model",
        ),
        "compute_five_layer_model": (
            "faultray.simulator.availability_model", "compute_five_layer_model",
        ),
        # Monte Carlo
        "run_monte_carlo": ("faultray.simulator.monte_carlo", "run_monte_carlo"),
        # Specialist engines
        "CostImpactEngine": ("faultray.simulator.cost_engine", "CostImpactEngine"),
        "SecurityResilienceEngine": (
            "faultray.simulator.security_engine", "SecurityResilienceEngine",
        ),
        # SLA Validator
        "SLAValidatorEngine": (
            "faultray.simulator.sla_validator", "SLAValidatorEngine",
        ),
        "SLATarget": (
            "faultray.simulator.sla_validator", "SLATarget",
        ),
        # CI/CD Gate
        "CIGateGenerator": (
            "faultray.ci.github_action", "CIGateGenerator",
        ),
        "CIGateConfig": (
            "faultray.ci.github_action", "CIGateConfig",
        ),
        "SARIFExporter": (
            "faultray.ci.sarif_exporter", "SARIFExporter",
        ),
        # SDK entry point
        "FaultZero": ("faultray.sdk", "FaultZero"),
    }

    if name in _import_map:
        module_path, attr = _import_map[name]
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)

    raise AttributeError(f"module 'faultray' has no attribute {name!r}")


__all__ = [
    "InfraGraph", "Component", "ComponentType", "Dependency",
    "load_yaml",
    "SimulationEngine", "SimulationReport",
    "DynamicSimulationEngine", "OpsSimulationEngine",
    "CascadeEngine",
    "compute_three_layer_model", "compute_five_layer_model",
    "run_monte_carlo",
    "CostImpactEngine", "SecurityResilienceEngine",
    "SLAValidatorEngine", "SLATarget",
    "CIGateGenerator", "CIGateConfig", "SARIFExporter",
    "FaultZero",
]
