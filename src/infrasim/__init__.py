"""FaultZero — Zero-risk infrastructure chaos simulation."""

__version__ = "2.1.0"


def __getattr__(name: str):
    """Lazy imports for the public API surface.

    This ensures ``import infrasim`` never fails even when optional
    dependencies (e.g. pydantic, networkx) are missing — individual
    symbols raise ImportError only when actually accessed.
    """
    _import_map = {
        # Model layer
        "InfraGraph": ("infrasim.model.graph", "InfraGraph"),
        "Component": ("infrasim.model.components", "Component"),
        "ComponentType": ("infrasim.model.components", "ComponentType"),
        "Dependency": ("infrasim.model.components", "Dependency"),
        "load_yaml": ("infrasim.model.loader", "load_yaml"),
        # Simulation engines
        "SimulationEngine": ("infrasim.simulator.engine", "SimulationEngine"),
        "SimulationReport": ("infrasim.simulator.engine", "SimulationReport"),
        "DynamicSimulationEngine": ("infrasim.simulator.dynamic_engine", "DynamicSimulationEngine"),
        "OpsSimulationEngine": ("infrasim.simulator.ops_engine", "OpsSimulationEngine"),
        "CascadeEngine": ("infrasim.simulator.cascade", "CascadeEngine"),
        # Availability models
        "compute_three_layer_model": (
            "infrasim.simulator.availability_model", "compute_three_layer_model",
        ),
        "compute_five_layer_model": (
            "infrasim.simulator.availability_model", "compute_five_layer_model",
        ),
        # Monte Carlo
        "run_monte_carlo": ("infrasim.simulator.monte_carlo", "run_monte_carlo"),
        # Specialist engines
        "CostImpactEngine": ("infrasim.simulator.cost_engine", "CostImpactEngine"),
        "SecurityResilienceEngine": (
            "infrasim.simulator.security_engine", "SecurityResilienceEngine",
        ),
    }

    if name in _import_map:
        module_path, attr = _import_map[name]
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)

    raise AttributeError(f"module 'infrasim' has no attribute {name!r}")


__all__ = [
    "InfraGraph", "Component", "ComponentType", "Dependency",
    "load_yaml",
    "SimulationEngine", "SimulationReport",
    "DynamicSimulationEngine", "OpsSimulationEngine",
    "CascadeEngine",
    "compute_three_layer_model", "compute_five_layer_model",
    "run_monte_carlo",
    "CostImpactEngine", "SecurityResilienceEngine",
]
