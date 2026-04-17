# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Golden output tests — verify command outputs maintain expected structure.

These tests do NOT check exact values (which may change with versions); they
verify that the structural contract (required JSON keys, types, etc.) is stable.
Any regression that removes a required key or changes its type will be caught.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent


def _run(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a faultray CLI command and return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, "-m", "faultray", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(_REPO_ROOT),
    )


def _parse_json_output(result: subprocess.CompletedProcess) -> dict:
    """Parse stdout as JSON, providing a clear error on failure."""
    stdout = result.stdout.strip()
    if not stdout:
        pytest.fail(
            f"Command produced no stdout.\n"
            f"Return code: {result.returncode}\n"
            f"Stderr: {result.stderr[:2000]}"
        )
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"stdout is not valid JSON: {exc}\n"
            f"stdout (first 500 chars): {stdout[:500]}\n"
            f"stderr (first 500 chars): {result.stderr[:500]}"
        )


# ===========================================================================
# simulate --json  (faultray-model.json)
# ===========================================================================

class TestSimulateOutput:
    """faultray simulate -m faultray-model.json --json output structure is stable."""

    def test_simulate_exits_zero(self):
        result = _run("simulate", "-m", "faultray-model.json", "--json")
        assert result.returncode == 0, (
            f"simulate exited {result.returncode}.\nStderr: {result.stderr[:1000]}"
        )

    def test_simulate_stdout_is_valid_json(self):
        result = _run("simulate", "-m", "faultray-model.json", "--json")
        assert result.returncode == 0
        _parse_json_output(result)  # raises on parse failure

    def test_simulate_has_resilience_score(self):
        result = _run("simulate", "-m", "faultray-model.json", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        assert "resilience_score" in data, "Missing key: resilience_score"
        assert isinstance(data["resilience_score"], (int, float))

    def test_simulate_has_scenarios(self):
        result = _run("simulate", "-m", "faultray-model.json", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        assert "scenarios" in data, "Missing key: scenarios"
        assert isinstance(data["scenarios"], list)

    def test_simulate_has_severity_counts(self):
        """critical, warning, and passed counters must all be present."""
        result = _run("simulate", "-m", "faultray-model.json", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        for key in ("critical", "warning", "passed"):
            assert key in data, f"Missing key: {key}"
            assert isinstance(data[key], int), f"{key} should be an int"

    def test_simulate_scenarios_have_required_fields(self):
        """Each scenario entry must have name and severity."""
        result = _run("simulate", "-m", "faultray-model.json", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        assert len(data["scenarios"]) > 0, "Expected at least one scenario"
        for i, scenario in enumerate(data["scenarios"]):
            assert "name" in scenario, f"scenarios[{i}] missing 'name'"
            assert "severity" in scenario, f"scenarios[{i}] missing 'severity'"

    def test_simulate_resilience_score_in_valid_range(self):
        """resilience_score should be between 0 and 100 (or 0.0–1.0 depending on version)."""
        result = _run("simulate", "-m", "faultray-model.json", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        score = data["resilience_score"]
        assert 0.0 <= score <= 100.0, f"resilience_score {score} is out of expected range [0, 100]"


# ===========================================================================
# dora assess --json
# ===========================================================================

class TestDORAOutput:
    """faultray dora assess examples/demo-infra.yaml --json output structure is stable."""

    def test_dora_assess_exits_zero(self):
        result = _run("dora", "assess", "examples/demo-infra.yaml", "--json")
        assert result.returncode == 0, (
            f"dora assess exited {result.returncode}.\nStderr: {result.stderr[:1000]}"
        )

    def test_dora_assess_stdout_is_valid_json(self):
        result = _run("dora", "assess", "examples/demo-infra.yaml", "--json")
        assert result.returncode == 0
        _parse_json_output(result)

    def test_dora_has_compliance_rate(self):
        result = _run("dora", "assess", "examples/demo-infra.yaml", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        assert "compliance_rate_percent" in data, "Missing key: compliance_rate_percent"
        assert isinstance(data["compliance_rate_percent"], (int, float))

    def test_dora_has_article_statuses(self):
        result = _run("dora", "assess", "examples/demo-infra.yaml", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        assert "article_statuses" in data, "Missing key: article_statuses"
        assert isinstance(data["article_statuses"], dict)

    def test_dora_has_overall_status(self):
        result = _run("dora", "assess", "examples/demo-infra.yaml", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        assert "overall_status" in data, "Missing key: overall_status"
        assert isinstance(data["overall_status"], str)

    def test_dora_compliance_rate_is_percentage(self):
        """compliance_rate_percent must be in [0, 100]."""
        result = _run("dora", "assess", "examples/demo-infra.yaml", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        rate = data["compliance_rate_percent"]
        assert 0.0 <= rate <= 100.0, f"compliance_rate_percent {rate} out of [0, 100]"

    def test_dora_article_statuses_are_non_empty(self):
        """At least one article must be evaluated."""
        result = _run("dora", "assess", "examples/demo-infra.yaml", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        assert len(data["article_statuses"]) > 0, "article_statuses should not be empty"

    def test_dora_article_statuses_have_string_values(self):
        """Every article status value should be a string."""
        result = _run("dora", "assess", "examples/demo-infra.yaml", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        for article, status in data["article_statuses"].items():
            assert isinstance(status, str), (
                f"{article} status should be a string, got {type(status)}"
            )

    def test_dora_overall_status_is_known_value(self):
        """overall_status must be one of the expected compliance values."""
        result = _run("dora", "assess", "examples/demo-infra.yaml", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        known_statuses = {
            "compliant",
            "non_compliant",
            "partially_compliant",
            "not_applicable",
        }
        assert data["overall_status"] in known_statuses, (
            f"Unexpected overall_status: {data['overall_status']!r}. "
            f"Expected one of {known_statuses}"
        )


# ===========================================================================
# iac-export  (Terraform)
# ===========================================================================

class TestIaCExportOutput:
    """faultray iac-export produces a Terraform file with expected structure."""

    def test_iac_export_exits_zero(self, tmp_path):
        result = _run(
            "iac-export", "examples/demo-infra.yaml",
            "--output", str(tmp_path),
            "--format", "terraform",
        )
        assert result.returncode == 0, (
            f"iac-export exited {result.returncode}.\nStderr: {result.stderr[:1000]}"
        )

    def test_iac_export_creates_tf_file(self, tmp_path):
        _run(
            "iac-export", "examples/demo-infra.yaml",
            "--output", str(tmp_path),
            "--format", "terraform",
        )
        tf_files = list(tmp_path.glob("*.tf"))
        assert len(tf_files) >= 1, "Expected at least one .tf file to be generated"

    def test_iac_terraform_has_provider_block(self, tmp_path):
        _run(
            "iac-export", "examples/demo-infra.yaml",
            "--output", str(tmp_path),
            "--format", "terraform",
        )
        tf_file = next(tmp_path.glob("*.tf"), None)
        assert tf_file is not None
        content = tf_file.read_text()
        assert "provider" in content, "Terraform output missing 'provider' block"

    def test_iac_terraform_has_resource_blocks(self, tmp_path):
        _run(
            "iac-export", "examples/demo-infra.yaml",
            "--output", str(tmp_path),
            "--format", "terraform",
        )
        tf_file = next(tmp_path.glob("*.tf"), None)
        assert tf_file is not None
        content = tf_file.read_text()
        assert "resource" in content, "Terraform output missing 'resource' blocks"

    def test_iac_terraform_has_required_version(self, tmp_path):
        _run(
            "iac-export", "examples/demo-infra.yaml",
            "--output", str(tmp_path),
            "--format", "terraform",
        )
        tf_file = next(tmp_path.glob("*.tf"), None)
        assert tf_file is not None
        content = tf_file.read_text()
        assert "required_version" in content, (
            "Terraform output missing 'required_version' constraint"
        )

    def test_iac_terraform_file_is_non_empty(self, tmp_path):
        _run(
            "iac-export", "examples/demo-infra.yaml",
            "--output", str(tmp_path),
            "--format", "terraform",
        )
        tf_file = next(tmp_path.glob("*.tf"), None)
        assert tf_file is not None
        assert tf_file.stat().st_size > 0, "Generated .tf file should not be empty"


# ===========================================================================
# simulate with faultray-model.json — additional structural checks
# ===========================================================================

class TestSimulateAdditional:
    """Additional structural checks for simulate output."""

    def test_simulate_total_scenarios_is_nonnegative(self):
        result = _run("simulate", "-m", "faultray-model.json", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        if "total_scenarios" in data:
            assert data["total_scenarios"] >= 0

    def test_simulate_counts_sum_correctly(self):
        """critical + warning + passed should equal total scenarios (if present)."""
        result = _run("simulate", "-m", "faultray-model.json", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        # total_scenarios may not always be present; skip if absent
        if "total_scenarios" not in data:
            return
        total = data["total_scenarios"]
        n_info = data.get("info", 0)
        counted = data["critical"] + data["warning"] + n_info + data["passed"]
        assert counted == total, (
            f"critical({data['critical']}) + warning({data['warning']}) + "
            f"info({n_info}) + passed({data['passed']}) = {counted} != total_scenarios({total})"
        )

    def test_simulate_no_unexpected_keys_at_top_level(self):
        """All expected keys are present; extra keys are allowed but log a notice."""
        result = _run("simulate", "-m", "faultray-model.json", "--json")
        assert result.returncode == 0
        data = _parse_json_output(result)
        required_keys = {"resilience_score", "scenarios", "critical", "warning", "passed"}
        missing = required_keys - set(data.keys())
        assert not missing, f"Missing required top-level keys: {missing}"
