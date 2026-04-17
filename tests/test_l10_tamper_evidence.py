# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L10 Tamper Evidence Tests — Professional Validity layer.

Validates that simulation results can be verified for integrity:
- Results contain sufficient metadata for audit trail
- Tampering with results is detectable
- Result data structures have required fields
"""

from __future__ import annotations

import hashlib
import json

import pytest

from faultray.model.demo import create_demo_graph
from faultray.simulator.engine import SimulationEngine, SimulationReport, ScenarioResult
from faultray.simulator.monte_carlo import run_monte_carlo


# ---------------------------------------------------------------------------
# L10-TAMP-001: Simulation results contain metadata
# ---------------------------------------------------------------------------


class TestResultMetadata:
    """Verify that results include enough metadata for audit trails."""

    def test_report_has_result_count(self) -> None:
        """SimulationReport should track total generated scenarios."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        assert hasattr(report, "total_generated")
        assert report.total_generated >= 0

    def test_report_tracks_truncation(self) -> None:
        """SimulationReport should indicate if results were truncated."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        assert hasattr(report, "was_truncated")
        assert isinstance(report.was_truncated, bool)

    def test_scenario_result_has_risk_score(self) -> None:
        """Each ScenarioResult should have a numeric risk_score."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        for result in report.results:
            assert hasattr(result, "risk_score")
            assert isinstance(result.risk_score, (int, float))

    def test_scenario_result_has_scenario_reference(self) -> None:
        """Each ScenarioResult should reference its source scenario."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        for result in report.results:
            assert hasattr(result, "scenario")
            assert hasattr(result.scenario, "id")
            assert hasattr(result.scenario, "name")

    def test_monte_carlo_result_has_trial_count(self) -> None:
        """MonteCarloResult should record the number of trials."""
        graph = create_demo_graph()
        result = run_monte_carlo(graph, n_trials=100, seed=42)
        assert result.n_trials == 100


# ---------------------------------------------------------------------------
# L10-TAMP-002: Result integrity verification
# ---------------------------------------------------------------------------


class TestResultIntegrity:
    """Verify that result data can be hashed for integrity checking."""

    def test_monte_carlo_results_hashable(self) -> None:
        """Monte Carlo trial results should be hashable for integrity."""
        graph = create_demo_graph()
        result = run_monte_carlo(graph, n_trials=100, seed=42)

        # Create a hash of the trial results
        data = json.dumps(result.trial_results, sort_keys=True)
        digest = hashlib.sha256(data.encode()).hexdigest()
        assert len(digest) == 64  # SHA-256 hex digest

    def test_result_hash_changes_on_modification(self) -> None:
        """Modifying results should change the hash."""
        graph = create_demo_graph()
        result = run_monte_carlo(graph, n_trials=100, seed=42)

        original_data = json.dumps(result.trial_results, sort_keys=True)
        original_hash = hashlib.sha256(original_data.encode()).hexdigest()

        # Tamper with a single trial result
        tampered = list(result.trial_results)
        tampered[0] = 0.0  # Force change
        tampered_data = json.dumps(tampered, sort_keys=True)
        tampered_hash = hashlib.sha256(tampered_data.encode()).hexdigest()

        assert original_hash != tampered_hash, "Hash should change after tampering"

    def test_simulation_report_categories_consistent(self) -> None:
        """critical + warning + passed should equal total results."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        categorized = (
            len(report.critical_findings)
            + len(report.warnings)
            + len(report.passed)
        )
        assert categorized == len(report.results), (
            f"Categories ({categorized}) != total ({len(report.results)})"
        )


# ---------------------------------------------------------------------------
# L10-TAMP-003: Risk score classification boundaries
# ---------------------------------------------------------------------------


class TestRiskScoreClassification:
    """Verify that risk score thresholds are correctly applied."""

    def test_critical_threshold_is_7(self) -> None:
        """Scores >= 7.0 should be classified as critical."""
        from faultray.simulator.cascade import CascadeChain
        from faultray.simulator.scenarios import Scenario

        result = ScenarioResult(
            scenario=Scenario(id="test", name="Test", description="test", faults=[]),
            cascade=CascadeChain(trigger="test", total_components=10),
            risk_score=7.0,
        )
        assert result.is_critical

    def test_warning_threshold_is_4_to_7(self) -> None:
        """Scores in [4.0, 7.0) should be classified as warning."""
        from faultray.simulator.cascade import CascadeChain
        from faultray.simulator.scenarios import Scenario

        result = ScenarioResult(
            scenario=Scenario(id="test", name="Test", description="test", faults=[]),
            cascade=CascadeChain(trigger="test", total_components=10),
            risk_score=5.0,
        )
        assert result.is_warning
        assert not result.is_critical

    def test_passed_below_4(self) -> None:
        """Scores below 4.0 should be neither critical nor warning."""
        from faultray.simulator.cascade import CascadeChain
        from faultray.simulator.scenarios import Scenario

        result = ScenarioResult(
            scenario=Scenario(id="test", name="Test", description="test", faults=[]),
            cascade=CascadeChain(trigger="test", total_components=10),
            risk_score=3.0,
        )
        assert not result.is_critical
        assert not result.is_warning
