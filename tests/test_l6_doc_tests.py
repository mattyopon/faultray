# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L6 Documentation Tests — Value (Acceptance) layer.

Validates that documented examples and sample configurations actually work:
- SDK docstring examples execute successfully
- Example YAML files are valid and loadable
- Entry points are functional
"""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.model.loader import load_yaml


# ---------------------------------------------------------------------------
# L6-DOC-001: Example YAML files are valid
# ---------------------------------------------------------------------------


class TestExampleYamlFiles:
    """Verify that all example YAML files in the examples/ directory load."""

    EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

    def _example_yamls(self) -> list[Path]:
        if not self.EXAMPLES_DIR.exists():
            return []
        return sorted(self.EXAMPLES_DIR.glob("*.yaml"))

    def test_examples_directory_exists(self) -> None:
        """The examples/ directory should exist."""
        assert self.EXAMPLES_DIR.exists(), "examples/ directory not found"

    def test_at_least_one_example_yaml_exists(self) -> None:
        """There should be at least one example YAML."""
        yamls = self._example_yamls()
        assert len(yamls) > 0, "No example YAML files found"

    @pytest.mark.parametrize(
        "yaml_name",
        [
            "demo-infra.yaml",
            "ecommerce-platform.yaml",
            "fintech-banking.yaml",
            "healthcare-ehr.yaml",
            "saas-multi-tenant.yaml",
            "hybrid-onprem-cloud.yaml",
            "ai-agent-workflow.yaml",
            "supply-chain-agent.yaml",
        ],
    )
    def test_example_yaml_loads_successfully(self, yaml_name: str) -> None:
        """Each example YAML should load without errors."""
        yaml_path = self.EXAMPLES_DIR / yaml_name
        if not yaml_path.exists():
            pytest.skip(f"{yaml_name} not found in examples/")
        graph = load_yaml(yaml_path)
        assert len(graph.components) > 0, f"{yaml_name} has no components"


# ---------------------------------------------------------------------------
# L6-DOC-002: SDK docstring examples work
# ---------------------------------------------------------------------------


class TestSDKDocstringExamples:
    """Verify that SDK usage patterns from docstrings actually work."""

    def test_faultzero_demo_creates_graph(self) -> None:
        """FaultZero.demo() should return a working instance."""
        from faultray.sdk import FaultZero

        fz = FaultZero.demo()
        assert fz.resilience_score >= 0
        assert fz.resilience_score <= 100

    def test_faultzero_simulate_returns_report(self) -> None:
        """fz.simulate() should return a SimulationReport."""
        from faultray.sdk import FaultZero

        fz = FaultZero.demo()
        report = fz.simulate()
        assert hasattr(report, "results")
        assert hasattr(report, "resilience_score")
        assert hasattr(report, "critical_findings")

    def test_faultzero_from_yaml(self) -> None:
        """FaultZero(yaml_path) should work with example files."""
        example = Path(__file__).resolve().parent.parent / "examples" / "demo-infra.yaml"
        if not example.exists():
            pytest.skip("demo-infra.yaml not found")
        from faultray.sdk import FaultZero

        fz = FaultZero(str(example))
        assert fz.resilience_score >= 0

    def test_faultzero_from_text(self) -> None:
        """FaultZero.from_text() should parse natural language."""
        from faultray.sdk import FaultZero

        fz = FaultZero.from_text("3 web servers behind ALB with Aurora and Redis")
        assert fz.resilience_score >= 0

    def test_simulation_report_has_findings(self) -> None:
        """A demo simulation should produce critical_findings, warnings, passed."""
        from faultray.sdk import FaultZero

        fz = FaultZero.demo()
        report = fz.simulate()
        total = len(report.critical_findings) + len(report.warnings) + len(report.passed)
        assert total == len(report.results)


# ---------------------------------------------------------------------------
# L6-DOC-003: Sample config validity
# ---------------------------------------------------------------------------


class TestSampleConfigValidity:
    """Verify sample configurations are well-formed."""

    def test_demo_graph_has_expected_components(self) -> None:
        """The demo graph should contain the documented component set."""
        from faultray.model.demo import create_demo_graph

        graph = create_demo_graph()
        comp_ids = set(graph.components.keys())
        # Based on documented demo: nginx, app-1, app-2, postgres, redis, rabbitmq
        expected = {"nginx", "app-1", "app-2", "postgres", "redis", "rabbitmq"}
        assert expected.issubset(comp_ids), (
            f"Missing components: {expected - comp_ids}"
        )

    def test_demo_graph_dependencies_are_valid(self) -> None:
        """All demo dependencies should reference existing components."""
        from faultray.model.demo import create_demo_graph

        graph = create_demo_graph()
        comp_ids = set(graph.components.keys())
        for dep in graph.all_dependency_edges():
            assert dep.source_id in comp_ids, f"Unknown source: {dep.source_id}"
            assert dep.target_id in comp_ids, f"Unknown target: {dep.target_id}"
