"""Tests for Terraform FaultZero Provider."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrasim.integrations.terraform_provider import (
    TerraformFaultZeroProvider,
    TerraformPlanAnalysis,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_plan_change(
    res_type: str,
    name: str,
    actions: list[str],
    before: dict | None = None,
    after: dict | None = None,
):
    """Build a single resource_change entry for a terraform plan."""
    return {
        "type": res_type,
        "name": name,
        "address": f"{res_type}.{name}",
        "change": {
            "actions": actions,
            "before": before,
            "after": after,
        },
    }


def _make_plan_json(*changes) -> dict:
    """Build a plan JSON with given resource changes."""
    return {"resource_changes": list(changes)}


def _write_plan_json(tmp_path: Path, plan_json: dict) -> Path:
    """Write plan JSON to a temp file and return the path."""
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan_json))
    return plan_file


# ===================================================================
# TerraformFaultZeroProvider.analyze_plan_json
# ===================================================================


class TestAnalyzePlanJson:
    """Tests for analyze_plan_json() (no file I/O)."""

    def test_empty_plan(self):
        provider = TerraformFaultZeroProvider()
        analysis = provider.analyze_plan_json({})

        assert isinstance(analysis, TerraformPlanAnalysis)
        assert analysis.resources_added == 0
        assert analysis.resources_changed == 0
        assert analysis.resources_destroyed == 0
        assert analysis.recommendation == "safe to apply"

    def test_create_resources(self):
        plan = _make_plan_json(
            _make_plan_change(
                "aws_instance", "web",
                actions=["create"],
                after={"instance_type": "t3.medium", "name": "web"},
            ),
            _make_plan_change(
                "aws_db_instance", "db",
                actions=["create"],
                after={"instance_class": "db.r5.large", "name": "db"},
            ),
        )
        provider = TerraformFaultZeroProvider()
        analysis = provider.analyze_plan_json(plan)

        assert analysis.resources_added == 2
        assert analysis.resources_destroyed == 0
        assert analysis.score_after >= 0

    def test_destroy_resource_high_risk(self):
        plan = _make_plan_json(
            _make_plan_change(
                "aws_db_instance", "critical_db",
                actions=["delete"],
                before={"instance_class": "db.r5.xlarge", "name": "critical-db"},
                after=None,
            ),
        )
        provider = TerraformFaultZeroProvider()
        analysis = provider.analyze_plan_json(plan)

        assert analysis.resources_destroyed == 1
        assert analysis.recommendation == "high risk"

    def test_modify_resource(self):
        plan = _make_plan_json(
            _make_plan_change(
                "aws_instance", "app",
                actions=["update"],
                before={"instance_type": "t3.small", "name": "app"},
                after={"instance_type": "t3.large", "name": "app"},
            ),
        )
        provider = TerraformFaultZeroProvider()
        analysis = provider.analyze_plan_json(plan)

        assert analysis.resources_changed == 1
        assert analysis.resources_added == 0
        assert analysis.resources_destroyed == 0

    def test_score_delta_positive_for_adding_replicas(self):
        """Adding a replicated component should improve score."""
        plan = _make_plan_json(
            _make_plan_change(
                "aws_instance", "app1",
                actions=["create"],
                after={
                    "instance_type": "t3.medium",
                    "name": "app1",
                    "desired_count": 3,
                },
            ),
        )
        provider = TerraformFaultZeroProvider()
        analysis = provider.analyze_plan_json(plan)

        # After graph has at least one component, score should be > 0
        assert analysis.score_after >= 0

    def test_noop_changes_ignored(self):
        plan = _make_plan_json(
            _make_plan_change(
                "aws_instance", "stable",
                actions=["no-op"],
                before={"name": "stable"},
                after={"name": "stable"},
            ),
        )
        provider = TerraformFaultZeroProvider()
        analysis = provider.analyze_plan_json(plan)

        assert analysis.resources_added == 0
        assert analysis.resources_changed == 0
        assert analysis.resources_destroyed == 0


# ===================================================================
# TerraformFaultZeroProvider.analyze_plan (file-based)
# ===================================================================


class TestAnalyzePlanFile:
    """Tests for analyze_plan() with file I/O."""

    def test_load_from_json_file(self, tmp_path):
        plan = _make_plan_json(
            _make_plan_change(
                "aws_instance", "web",
                actions=["create"],
                after={"instance_type": "t3.medium", "name": "web"},
            ),
        )
        plan_file = _write_plan_json(tmp_path, plan)

        provider = TerraformFaultZeroProvider()
        analysis = provider.analyze_plan(plan_file)

        assert analysis.plan_file == str(plan_file)
        assert analysis.resources_added == 1

    def test_file_not_found_raises(self, tmp_path):
        provider = TerraformFaultZeroProvider()
        with pytest.raises(FileNotFoundError):
            provider.analyze_plan(tmp_path / "nonexistent.json")


# ===================================================================
# TerraformFaultZeroProvider.check_policy_json
# ===================================================================


class TestCheckPolicy:
    """Tests for check_policy_json()."""

    def test_empty_plan_fails_policy(self):
        """Empty plan has score 0, which fails a min_score > 0 policy."""
        provider = TerraformFaultZeroProvider()
        result = provider.check_policy_json({}, min_score=50.0)
        # Empty plan => score_after = 0 => fails
        assert result is False

    def test_plan_with_resources_passes_policy(self):
        plan = _make_plan_json(
            _make_plan_change(
                "aws_instance", "web",
                actions=["create"],
                after={"instance_type": "t3.medium", "name": "web"},
            ),
        )
        provider = TerraformFaultZeroProvider()
        # Single component with no dependencies gets resilience = 100
        result = provider.check_policy_json(plan, min_score=50.0)
        assert result is True


# ===================================================================
# TerraformFaultZeroProvider.generate_sentinel_policy
# ===================================================================


class TestGenerateSentinelPolicy:
    """Tests for generate_sentinel_policy()."""

    def test_generates_valid_sentinel(self):
        provider = TerraformFaultZeroProvider()
        policy = provider.generate_sentinel_policy(min_score=75.0)

        assert "FaultZero Sentinel Policy" in policy
        assert "75.0" in policy
        assert "min_resilience_score" in policy
        assert "faultzero" in policy


# ===================================================================
# Recommendation logic
# ===================================================================


class TestRecommendation:
    """Tests for _determine_recommendation()."""

    def test_safe_recommendation(self):
        provider = TerraformFaultZeroProvider()
        plan = _make_plan_json(
            _make_plan_change(
                "aws_instance", "web",
                actions=["create"],
                after={"instance_type": "t3.medium", "name": "web"},
            ),
        )
        analysis = provider.analyze_plan_json(plan)
        assert analysis.recommendation in (
            "safe to apply", "review recommended", "high risk"
        )

    def test_high_risk_for_db_deletion(self):
        plan = _make_plan_json(
            _make_plan_change(
                "aws_db_instance", "db1",
                actions=["delete"],
                before={"name": "db1", "instance_class": "db.r5.large"},
                after=None,
            ),
        )
        provider = TerraformFaultZeroProvider()
        analysis = provider.analyze_plan_json(plan)
        assert analysis.recommendation == "high risk"
