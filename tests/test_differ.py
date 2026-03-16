"""Tests for SimulationDiffer (result comparison)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultray.differ import DiffResult, SimulationDiffer


@pytest.fixture
def baseline_results() -> dict:
    """A baseline result set with some critical and warning scenarios."""
    return {
        "resilience_score": 80.0,
        "total_scenarios": 5,
        "critical_count": 1,
        "warning_count": 1,
        "passed_count": 3,
        "results": [
            {
                "scenario_name": "db-failure",
                "risk_score": 8.5,
                "is_critical": True,
                "is_warning": False,
                "cascade": {
                    "effects": [
                        {"component_id": "db-primary", "component_name": "DB Primary"},
                    ]
                },
            },
            {
                "scenario_name": "cache-miss",
                "risk_score": 5.0,
                "is_critical": False,
                "is_warning": True,
                "cascade": {
                    "effects": [
                        {"component_id": "redis-1", "component_name": "Redis"},
                    ]
                },
            },
            {
                "scenario_name": "lb-failover",
                "risk_score": 2.0,
                "is_critical": False,
                "is_warning": False,
                "cascade": {"effects": []},
            },
            {
                "scenario_name": "dns-timeout",
                "risk_score": 1.0,
                "is_critical": False,
                "is_warning": False,
                "cascade": {"effects": []},
            },
            {
                "scenario_name": "network-partition",
                "risk_score": 3.0,
                "is_critical": False,
                "is_warning": False,
                "cascade": {"effects": []},
            },
        ],
    }


@pytest.fixture
def improved_results(baseline_results: dict) -> dict:
    """Results where a critical issue was resolved and score improved."""
    data = {
        "resilience_score": 90.0,
        "total_scenarios": 5,
        "critical_count": 0,
        "warning_count": 1,
        "passed_count": 4,
        "results": [
            {
                "scenario_name": "db-failure",
                "risk_score": 3.0,  # Was critical, now resolved
                "is_critical": False,
                "is_warning": False,
                "cascade": {"effects": []},
            },
            {
                "scenario_name": "cache-miss",
                "risk_score": 5.0,
                "is_critical": False,
                "is_warning": True,
                "cascade": {
                    "effects": [
                        {"component_id": "redis-1", "component_name": "Redis"},
                    ]
                },
            },
            {
                "scenario_name": "lb-failover",
                "risk_score": 2.0,
                "is_critical": False,
                "is_warning": False,
                "cascade": {"effects": []},
            },
            {
                "scenario_name": "dns-timeout",
                "risk_score": 1.0,
                "is_critical": False,
                "is_warning": False,
                "cascade": {"effects": []},
            },
            {
                "scenario_name": "network-partition",
                "risk_score": 3.0,
                "is_critical": False,
                "is_warning": False,
                "cascade": {"effects": []},
            },
        ],
    }
    return data


@pytest.fixture
def regressed_results(baseline_results: dict) -> dict:
    """Results where new critical issues appeared and score dropped."""
    data = {
        "resilience_score": 60.0,
        "total_scenarios": 6,
        "critical_count": 3,
        "warning_count": 1,
        "passed_count": 2,
        "results": [
            {
                "scenario_name": "db-failure",
                "risk_score": 8.5,
                "is_critical": True,
                "is_warning": False,
                "cascade": {
                    "effects": [
                        {"component_id": "db-primary", "component_name": "DB Primary"},
                    ]
                },
            },
            {
                "scenario_name": "cache-miss",
                "risk_score": 5.0,
                "is_critical": False,
                "is_warning": True,
                "cascade": {
                    "effects": [
                        {"component_id": "redis-1", "component_name": "Redis"},
                    ]
                },
            },
            {
                "scenario_name": "api-overload",
                "risk_score": 9.0,
                "is_critical": True,
                "is_warning": False,
                "cascade": {
                    "effects": [
                        {"component_id": "api-gw", "component_name": "API Gateway"},
                    ]
                },
            },
            {
                "scenario_name": "storage-full",
                "risk_score": 7.5,
                "is_critical": True,
                "is_warning": False,
                "cascade": {
                    "effects": [
                        {"component_id": "s3-bucket", "component_name": "S3 Bucket"},
                    ]
                },
            },
            {
                "scenario_name": "lb-failover",
                "risk_score": 2.0,
                "is_critical": False,
                "is_warning": False,
                "cascade": {"effects": []},
            },
            {
                "scenario_name": "dns-timeout",
                "risk_score": 1.0,
                "is_critical": False,
                "is_warning": False,
                "cascade": {"effects": []},
            },
        ],
    }
    return data


class TestSimulationDiffer:
    def test_diff_no_change(self, baseline_results: dict):
        """Diffing identical results should show no regression."""
        differ = SimulationDiffer()
        result = differ.diff(baseline_results, baseline_results)

        assert result.score_delta == 0.0
        assert result.new_critical == []
        assert result.resolved_critical == []
        assert result.regression_detected is False

    def test_diff_improvement(self, baseline_results: dict, improved_results: dict):
        """Resolved critical should appear in resolved_critical list."""
        differ = SimulationDiffer()
        result = differ.diff(baseline_results, improved_results)

        assert result.score_before == 80.0
        assert result.score_after == 90.0
        assert result.score_delta == 10.0
        assert "db-failure" in result.resolved_critical
        assert result.new_critical == []
        assert result.regression_detected is False

    def test_diff_regression(self, baseline_results: dict, regressed_results: dict):
        """New critical findings should trigger regression detection."""
        differ = SimulationDiffer()
        result = differ.diff(baseline_results, regressed_results)

        assert result.score_before == 80.0
        assert result.score_after == 60.0
        assert result.score_delta == -20.0
        assert "api-overload" in result.new_critical
        assert "storage-full" in result.new_critical
        assert result.regression_detected is True

    def test_diff_component_changes(self, baseline_results: dict, regressed_results: dict):
        """Component-level changes should be detected."""
        differ = SimulationDiffer()
        result = differ.diff(baseline_results, regressed_results)

        # regressed_results has api-gw and s3-bucket that baseline doesn't
        assert any("api-gw" in c for c in result.component_changes)
        assert any("s3-bucket" in c for c in result.component_changes)

    def test_diff_files(self, tmp_path: Path, baseline_results: dict, improved_results: dict):
        """diff_files() should load and compare two JSON files."""
        before_path = tmp_path / "before.json"
        after_path = tmp_path / "after.json"

        before_path.write_text(json.dumps(baseline_results))
        after_path.write_text(json.dumps(improved_results))

        differ = SimulationDiffer()
        result = differ.diff_files(before_path, after_path)

        assert result.score_delta == 10.0
        assert result.regression_detected is False

    def test_diff_empty_results(self):
        """Diffing empty result sets should work without errors."""
        differ = SimulationDiffer()
        result = differ.diff(
            {"resilience_score": 0.0, "results": []},
            {"resilience_score": 0.0, "results": []},
        )
        assert result.score_delta == 0.0
        assert result.regression_detected is False

    def test_diff_new_critical_triggers_regression(self):
        """Even if score stays same, new critical should trigger regression."""
        before = {
            "resilience_score": 80.0,
            "results": [
                {"scenario_name": "s1", "risk_score": 3.0, "is_critical": False, "is_warning": False, "cascade": {"effects": []}},
            ],
        }
        after = {
            "resilience_score": 80.0,
            "results": [
                {"scenario_name": "s1", "risk_score": 3.0, "is_critical": False, "is_warning": False, "cascade": {"effects": []}},
                {"scenario_name": "s2", "risk_score": 8.0, "is_critical": True, "is_warning": False, "cascade": {"effects": []}},
            ],
        }
        differ = SimulationDiffer()
        result = differ.diff(before, after)
        assert result.regression_detected is True
        assert "s2" in result.new_critical

    def test_diff_warning_changes(self):
        """Warning changes should be tracked correctly."""
        before = {
            "resilience_score": 80.0,
            "results": [
                {"scenario_name": "w1", "risk_score": 5.0, "is_critical": False, "is_warning": True, "cascade": {"effects": []}},
            ],
        }
        after = {
            "resilience_score": 85.0,
            "results": [
                {"scenario_name": "w1", "risk_score": 2.0, "is_critical": False, "is_warning": False, "cascade": {"effects": []}},
                {"scenario_name": "w2", "risk_score": 4.5, "is_critical": False, "is_warning": True, "cascade": {"effects": []}},
            ],
        }
        differ = SimulationDiffer()
        result = differ.diff(before, after)
        assert "w1" in result.resolved_warnings
        assert "w2" in result.new_warnings


class TestDiffResult:
    def test_dataclass_fields(self):
        """DiffResult should have all expected fields."""
        dr = DiffResult(
            score_before=80.0,
            score_after=70.0,
            score_delta=-10.0,
            new_critical=["s1"],
            resolved_critical=[],
            new_warnings=[],
            resolved_warnings=["w1"],
            component_changes=["added: api-gw"],
            regression_detected=True,
        )
        assert dr.score_before == 80.0
        assert dr.score_after == 70.0
        assert dr.score_delta == -10.0
        assert dr.new_critical == ["s1"]
        assert dr.resolved_warnings == ["w1"]
        assert dr.regression_detected is True
