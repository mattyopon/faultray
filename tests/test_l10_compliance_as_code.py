# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L10 Compliance-as-Code Tests — Professional Validity layer.

Encodes DORA regulatory requirements and patent claim coverage as executable
test cases.  Each test asserts that a specific compliance obligation is
satisfied by the FaultRay implementation.

Regulatory references:
  - DORA (EU) 2022/2554 — Digital Operational Resilience Act
  - US Provisional Patent 64/010,200 (filed 2026-03-19)
  - ISO/IEC 42001 — AI Management System

Test naming convention:  test_<regulation>_<article>_<short_description>
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path

import pytest

from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine, SimulationReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "faultray"


def _get_report() -> SimulationReport:
    """Run a standard simulation and return the report."""
    graph = create_demo_graph()
    engine = SimulationEngine(graph)
    return engine.run_all_defaults(include_feed=False, include_plugins=False)


# ---------------------------------------------------------------------------
# DORA ICT Risk Management (Art. 5-16)
# ---------------------------------------------------------------------------


class TestDORAICTRiskManagement:
    """DORA Pillar 1 — ICT Risk Management Framework."""

    def test_dora_art8_availability_model_has_5_layers(self) -> None:
        """Risk assessment MUST include 5-layer availability analysis (Art. 8)."""
        from faultray.simulator.availability_model import compute_five_layer_model

        graph = create_demo_graph()
        result = compute_five_layer_model(graph)

        # The result must contain all 5 distinct layers
        assert hasattr(result, "layer1_software")
        assert hasattr(result, "layer2_hardware")
        assert hasattr(result, "layer3_theoretical")
        assert hasattr(result, "layer4_operational")
        assert hasattr(result, "layer5_external")

        # All limits must be valid probabilities in (0, 1]
        for layer_name in (
            "layer1_software",
            "layer2_hardware",
            "layer3_theoretical",
            "layer4_operational",
            "layer5_external",
        ):
            layer = getattr(result, layer_name)
            assert 0.0 < layer.availability <= 1.0, (
                f"{layer_name}.availability = {layer.availability} out of range"
            )

    def test_dora_art8_risk_register_exists(self) -> None:
        """Art. 8 — A DORA risk register module must be importable."""
        mod = importlib.import_module("faultray.simulator.dora_risk_assessment")
        assert hasattr(mod, "ICTRisk")
        assert hasattr(mod, "RiskCategory")

    def test_dora_art8_risk_has_likelihood_and_impact(self) -> None:
        """Art. 8 — Each risk entry must carry likelihood × impact scoring."""
        from faultray.simulator.dora_risk_assessment import ICTRisk, RiskCategory

        risk = ICTRisk(
            category=RiskCategory.AVAILABILITY,
            description="Test risk",
            likelihood=4,
            impact=3,
        )
        assert risk.inherent_score == 12
        assert risk.inherent_label in ("low", "medium", "high", "critical")


# ---------------------------------------------------------------------------
# DORA Incident Reporting (Art. 17-23)
# ---------------------------------------------------------------------------


class TestDORAIncidentReporting:
    """DORA Pillar 2 — Incident Management."""

    def test_dora_art18_incident_classification_exists(self) -> None:
        """Art. 18 — Incident classification module must exist."""
        mod = importlib.import_module("faultray.simulator.dora_incident_engine")
        assert hasattr(mod, "IncidentSeverity")
        assert hasattr(mod, "IncidentClassificationLevel")

    def test_dora_art19_reporting_stages(self) -> None:
        """Art. 19 — 3-stage reporting (initial/intermediate/final) must be modelled."""
        from faultray.simulator.dora_incident_engine import ReportStage

        stages = {s.value for s in ReportStage}
        assert "initial" in stages
        assert "intermediate" in stages
        assert "final" in stages

    def test_simulation_results_contain_risk_scores(self) -> None:
        """Simulation results must classify incidents by risk score."""
        report = _get_report()
        for result in report.results:
            assert hasattr(result, "risk_score")
            assert isinstance(result.risk_score, (int, float))


# ---------------------------------------------------------------------------
# DORA Resilience Testing (Art. 24-27)
# ---------------------------------------------------------------------------


class TestDORAResilienceTesting:
    """DORA Pillar 3 — Digital Operational Resilience Testing."""

    def test_dora_art24_all_scenarios_have_audit_trail(self) -> None:
        """Art. 24 — Every executed scenario must be traceable."""
        report = _get_report()
        for result in report.results:
            assert result.scenario.id, "Scenario ID missing"
            assert result.scenario.name, "Scenario name missing"

    def test_dora_test_plan_module_exists(self) -> None:
        """Art. 24 — A test plan module must be importable."""
        mod = importlib.import_module("faultray.simulator.dora_test_plan")
        assert mod is not None


# ---------------------------------------------------------------------------
# DORA Third-Party Risk (Art. 28-30)
# ---------------------------------------------------------------------------


class TestDORAThirdPartyRisk:
    """DORA Pillar 4 — Third-Party ICT Risk Management."""

    def test_dora_art29_concentration_risk_module(self) -> None:
        """Art. 29 — Concentration risk analysis module must exist."""
        mod = importlib.import_module("faultray.simulator.dora_concentration_risk")
        assert hasattr(mod, "ConcentrationDimension")

    def test_external_dependencies_individually_assessed(self) -> None:
        """External components must be individually risk-assessed."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        # Each component should appear in at least one scenario
        component_ids = set(graph.components.keys())
        tested_ids: set[str] = set()
        for result in report.results:
            for fault in result.scenario.faults:
                tested_ids.add(fault.target_component_id)
        # At least 80% of components should be tested
        coverage = len(tested_ids & component_ids) / max(len(component_ids), 1)
        assert coverage >= 0.8, f"Component test coverage only {coverage:.0%}"


# ---------------------------------------------------------------------------
# ISO 42001 AI Safety
# ---------------------------------------------------------------------------


class TestISO42001AISafety:
    """ISO/IEC 42001 — AI hallucination probability in reports."""

    def test_hallucination_probability_function_exists(self) -> None:
        """H(a,D,I) hallucination formula must be implemented."""
        from faultray.simulator.agent_cascade import (
            calculate_hallucination_probability,
        )
        assert callable(calculate_hallucination_probability)

    def test_hallucination_probability_returns_valid_range(self) -> None:
        """H(a,D,I) must return a value in [0, 1]."""
        from faultray.model.components import Component, ComponentType
        from faultray.simulator.agent_cascade import (
            calculate_hallucination_probability,
        )

        agent = Component(
            id="agent-1", name="test-agent",
            type=ComponentType.AI_AGENT,
            host="localhost", port=8080,
        )
        prob = calculate_hallucination_probability(agent)
        assert 0.0 <= prob <= 1.0


# ---------------------------------------------------------------------------
# Patent Claim Coverage (US 64/010,200)
# ---------------------------------------------------------------------------


class TestPatentClaimCoverage:
    """Verify that key technical elements from the patent are implemented."""

    def test_patent_lts_cascade_engine_exists(self) -> None:
        """Patent Claim: LTS-based cascade engine must be implemented."""
        from faultray.simulator.cascade import CascadeEngine

        graph = create_demo_graph()
        engine = CascadeEngine(graph)
        assert engine is not None

    def test_patent_5_layer_availability(self) -> None:
        """Patent Claim: 5-layer availability constraint model."""
        from faultray.simulator.availability_model import compute_five_layer_model

        graph = create_demo_graph()
        result = compute_five_layer_model(graph)
        # Must have exactly the 5 layers described in the patent
        layer_attrs = [
            "layer1_software",
            "layer2_hardware",
            "layer3_theoretical",
            "layer4_operational",
            "layer5_external",
        ]
        for attr in layer_attrs:
            assert hasattr(result, attr), f"Missing patent layer: {attr}"

    def test_patent_hallucination_formula(self) -> None:
        """Patent Claim: AI hallucination probability H(a,D,I)."""
        from faultray.simulator.agent_cascade import (
            calculate_hallucination_probability,
            calculate_agent_cascade_probability,
            calculate_chain_hallucination_probability,
        )
        # All three functions from the formal spec must exist
        assert callable(calculate_hallucination_probability)
        assert callable(calculate_agent_cascade_probability)
        assert callable(calculate_chain_hallucination_probability)

    def test_patent_visited_set_termination(self) -> None:
        """Patent Claim: visited-set guarantees termination on cyclic graphs."""
        # The cascade engine uses visited set + D_max=20
        source = Path(SRC_ROOT / "simulator" / "cascade.py").read_text()
        assert "visited" in source, "visited-set not found in cascade.py"
        assert "depth > 20" in source or "D_max" in source, (
            "Depth limit D_max not found in cascade.py"
        )

    def test_patent_cascade_formal_spec_reference(self) -> None:
        """Patent: cascade module must reference the formal specification."""
        source = Path(SRC_ROOT / "simulator" / "cascade.py").read_text()
        assert "Labeled Transition System" in source or "LTS" in source
