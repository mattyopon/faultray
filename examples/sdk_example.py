"""Example: Using FaultZero as a Python library.

Demonstrates how to load infrastructure, run simulations, and
compute availability models programmatically.
"""

from infrasim import load_yaml, SimulationEngine, compute_five_layer_model

# Load infrastructure from YAML
graph = load_yaml("infra.yaml")

# Run simulation
engine = SimulationEngine(graph)
report = engine.run_all_defaults()

print(f"Resilience: {report.resilience_score:.0f}/100")
print(f"Critical: {len(report.critical_findings)}")

# 5-Layer availability model
layers = compute_five_layer_model(graph)
print(layers.summary)
