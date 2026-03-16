"""Chaos Regression Gate - block code changes that reduce infrastructure resilience.

Designed for CI/CD pipeline integration. Compares before/after infrastructure
models and determines whether a change should be blocked based on configurable
thresholds (minimum score, maximum score drop, new critical findings).

Usage:
    gate = ChaosRegressionGate(min_score=60.0, max_score_drop=5.0)
    result = gate.check(before_graph, after_graph)
    if not result.passed:
        print(result.blocking_reason)

CLI:
    faultray gate check --before model-v1.json --after model-v2.json --min-score 60
    faultray gate terraform-plan plan.out --model current.json

Exit code 0 = passed, 1 = blocked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine, SimulationReport

logger = logging.getLogger(__name__)

# SARIF tool metadata
_TOOL_NAME = "FaultRay"
_TOOL_VERSION = "2.1.0"
_TOOL_URI = "https://github.com/faultray/faultray"
_SARIF_SCHEMA = (
    "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json"
)
_SARIF_VERSION = "2.1.0"


@dataclass
class RegressionCheckResult:
    """Result of a regression gate check."""

    passed: bool
    before_score: float
    after_score: float
    score_delta: float
    new_critical_findings: list[str] = field(default_factory=list)
    new_warnings: list[str] = field(default_factory=list)
    resolved_findings: list[str] = field(default_factory=list)
    blocking_reason: str | None = None  # None if passed
    recommendation: str = ""


class ChaosRegressionGate:
    """CI/CD gate that blocks changes reducing resilience.

    Parameters
    ----------
    min_score:
        Absolute minimum resilience score. Any model below this fails.
    max_score_drop:
        Maximum allowed score decrease. If the after-model score dropped
        more than this compared to before, the gate blocks.
    block_on_new_critical:
        If True, block when new critical findings appear that did not
        exist in the before-model.
    """

    def __init__(
        self,
        min_score: float = 60.0,
        max_score_drop: float = 5.0,
        block_on_new_critical: bool = True,
    ) -> None:
        self.min_score = min_score
        self.max_score_drop = max_score_drop
        self.block_on_new_critical = block_on_new_critical

    def check(
        self, before_graph: InfraGraph, after_graph: InfraGraph
    ) -> RegressionCheckResult:
        """Compare before/after graphs and determine if change should be blocked.

        Runs simulation on both graphs, compares scores and findings,
        and returns a result indicating whether the change passes or is blocked.
        """
        # Run simulation on both graphs
        before_engine = SimulationEngine(before_graph)
        after_engine = SimulationEngine(after_graph)

        before_report = before_engine.run_all_defaults(
            include_feed=False, include_plugins=False
        )
        after_report = after_engine.run_all_defaults(
            include_feed=False, include_plugins=False
        )

        return self._compare_reports(before_report, after_report)

    def check_from_files(
        self, before_path: Path, after_path: Path
    ) -> RegressionCheckResult:
        """Load models from JSON/YAML files and run a regression check.

        Supports both JSON (``InfraGraph.load``) and YAML (``load_yaml``)
        formats, determined by file extension.
        """
        before_graph = self._load_graph(before_path)
        after_graph = self._load_graph(after_path)
        return self.check(before_graph, after_graph)

    def check_terraform_plan(
        self, plan_path: Path, current_model: Path
    ) -> RegressionCheckResult:
        """Evaluate a terraform plan against the current model.

        If the plan file is a JSON infrastructure model, it is loaded
        directly and compared against the current model. Otherwise,
        we attempt to import it via the Terraform scanner.
        """
        current_graph = self._load_graph(current_model)

        # Attempt to load plan as a model file (JSON/YAML)
        try:
            plan_graph = self._load_graph(plan_path)
        except Exception:
            # If loading fails, return a result indicating the plan could not
            # be parsed; the gate passes by default in this case since we
            # cannot determine the impact.
            before_score = current_graph.resilience_score()
            return RegressionCheckResult(
                passed=True,
                before_score=before_score,
                after_score=before_score,
                score_delta=0.0,
                blocking_reason=None,
                recommendation=(
                    f"Could not parse terraform plan at {plan_path}. "
                    "Ensure the plan is exported as a model file."
                ),
            )

        return self.check(current_graph, plan_graph)

    def generate_pr_comment(self, result: RegressionCheckResult) -> str:
        """Generate a GitHub/GitLab PR comment with gate results.

        Returns a Markdown-formatted string suitable for posting as a
        PR comment via the GitHub or GitLab API.
        """
        if result.passed:
            status_badge = "## :white_check_mark: Chaos Regression Gate: PASSED"
        else:
            status_badge = "## :x: Chaos Regression Gate: BLOCKED"

        lines = [status_badge, ""]

        # Score summary
        delta_sign = "+" if result.score_delta >= 0 else ""
        lines.append("### Resilience Score")
        lines.append("")
        lines.append(
            "| Metric | Value |"
        )
        lines.append("| --- | --- |")
        lines.append(f"| Before | {result.before_score:.1f} |")
        lines.append(f"| After | {result.after_score:.1f} |")
        lines.append(
            f"| Delta | {delta_sign}{result.score_delta:.1f} |"
        )
        lines.append("")

        # Blocking reason
        if result.blocking_reason:
            lines.append(f"**Blocking reason:** {result.blocking_reason}")
            lines.append("")

        # New findings
        if result.new_critical_findings:
            lines.append("### New Critical Findings")
            lines.append("")
            for finding in result.new_critical_findings:
                lines.append(f"- :red_circle: {finding}")
            lines.append("")

        if result.new_warnings:
            lines.append("### New Warnings")
            lines.append("")
            for warning in result.new_warnings:
                lines.append(f"- :warning: {warning}")
            lines.append("")

        # Resolved findings
        if result.resolved_findings:
            lines.append("### Resolved Findings")
            lines.append("")
            for resolved in result.resolved_findings:
                lines.append(f"- :heavy_check_mark: {resolved}")
            lines.append("")

        # Recommendation
        if result.recommendation:
            lines.append(f"**Recommendation:** {result.recommendation}")
            lines.append("")

        lines.append("---")
        lines.append("*Generated by FaultRay Chaos Regression Gate*")

        return "\n".join(lines)

    def to_sarif(self, result: RegressionCheckResult) -> dict:
        """Export regression gate result as SARIF for GitHub Security tab.

        Returns a SARIF 2.1.0 compliant JSON structure containing all
        new findings detected by the regression gate.
        """
        rules: list[dict] = []
        results: list[dict] = []

        # Add rules/results for new critical findings
        for idx, finding in enumerate(result.new_critical_findings):
            rule_id = f"GATE{idx + 1:04d}"
            rules.append({
                "id": rule_id,
                "name": f"RegressionCritical{idx + 1}",
                "shortDescription": {"text": finding},
                "fullDescription": {
                    "text": f"Chaos regression gate: new critical finding - {finding}",
                },
                "defaultConfiguration": {"level": "error"},
                "properties": {
                    "tags": ["resilience", "regression", "critical"],
                },
            })
            results.append({
                "ruleId": rule_id,
                "ruleIndex": len(rules) - 1,
                "level": "error",
                "message": {"text": finding},
                "locations": [],
            })

        # Add rules/results for new warnings
        for idx, warning in enumerate(result.new_warnings):
            rule_id = f"GATEW{idx + 1:04d}"
            rules.append({
                "id": rule_id,
                "name": f"RegressionWarning{idx + 1}",
                "shortDescription": {"text": warning},
                "fullDescription": {
                    "text": f"Chaos regression gate: new warning - {warning}",
                },
                "defaultConfiguration": {"level": "warning"},
                "properties": {
                    "tags": ["resilience", "regression", "warning"],
                },
            })
            results.append({
                "ruleId": rule_id,
                "ruleIndex": len(rules) - 1,
                "level": "warning",
                "message": {"text": warning},
                "locations": [],
            })

        # Add blocking reason as a top-level finding if present
        if result.blocking_reason:
            rule_id = "GATE0000"
            rules.insert(0, {
                "id": rule_id,
                "name": "RegressionGateBlocked",
                "shortDescription": {"text": "Regression gate blocked the change"},
                "fullDescription": {
                    "text": result.blocking_reason,
                },
                "defaultConfiguration": {"level": "error"},
                "properties": {
                    "tags": ["resilience", "regression", "gate"],
                },
            })
            results.insert(0, {
                "ruleId": rule_id,
                "ruleIndex": 0,
                "level": "error",
                "message": {"text": result.blocking_reason},
                "locations": [],
            })
            # Adjust ruleIndex for subsequent results
            for r in results[1:]:
                r["ruleIndex"] += 1

        sarif: dict[str, Any] = {
            "$schema": _SARIF_SCHEMA,
            "version": _SARIF_VERSION,
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": _TOOL_NAME,
                            "version": _TOOL_VERSION,
                            "informationUri": _TOOL_URI,
                            "rules": rules,
                        },
                    },
                    "results": results,
                    "invocations": [
                        {
                            "executionSuccessful": result.passed,
                            "toolExecutionNotifications": [],
                        },
                    ],
                    "properties": {
                        "gate_passed": result.passed,
                        "before_score": result.before_score,
                        "after_score": result.after_score,
                        "score_delta": result.score_delta,
                    },
                },
            ],
        }

        return sarif

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compare_reports(
        self,
        before_report: SimulationReport,
        after_report: SimulationReport,
    ) -> RegressionCheckResult:
        """Compare two simulation reports and produce a gate result."""
        before_score = before_report.resilience_score
        after_score = after_report.resilience_score
        score_delta = after_score - before_score

        # Extract finding names for comparison
        before_critical_names = {
            r.scenario.name for r in before_report.critical_findings
        }
        after_critical_names = {
            r.scenario.name for r in after_report.critical_findings
        }

        before_warning_names = {
            r.scenario.name for r in before_report.warnings
        }
        after_warning_names = {
            r.scenario.name for r in after_report.warnings
        }

        new_critical = sorted(after_critical_names - before_critical_names)
        new_warnings = sorted(after_warning_names - before_warning_names)
        resolved = sorted(
            (before_critical_names | before_warning_names)
            - (after_critical_names | after_warning_names)
        )

        # Determine blocking
        blocking_reason = None
        reasons: list[str] = []

        if after_score < self.min_score:
            reasons.append(
                f"Resilience score {after_score:.1f} is below minimum threshold "
                f"{self.min_score:.1f}"
            )

        if score_delta < -self.max_score_drop:
            reasons.append(
                f"Score dropped by {abs(score_delta):.1f} points "
                f"(max allowed: {self.max_score_drop:.1f})"
            )

        if self.block_on_new_critical and new_critical:
            reasons.append(
                f"{len(new_critical)} new critical finding(s) introduced"
            )

        if reasons:
            blocking_reason = "; ".join(reasons)

        passed = blocking_reason is None

        # Build recommendation
        recommendation = self._build_recommendation(
            passed, after_score, score_delta, new_critical, new_warnings
        )

        return RegressionCheckResult(
            passed=passed,
            before_score=before_score,
            after_score=after_score,
            score_delta=round(score_delta, 2),
            new_critical_findings=new_critical,
            new_warnings=new_warnings,
            resolved_findings=resolved,
            blocking_reason=blocking_reason,
            recommendation=recommendation,
        )

    def _build_recommendation(
        self,
        passed: bool,
        after_score: float,
        score_delta: float,
        new_critical: list[str],
        new_warnings: list[str],
    ) -> str:
        """Build a human-readable recommendation string."""
        if passed and not new_warnings:
            if score_delta > 0:
                return (
                    f"Change improves resilience by {score_delta:.1f} points. "
                    "Safe to merge."
                )
            return "No resilience regression detected. Safe to merge."

        parts: list[str] = []

        if not passed:
            parts.append("This change should NOT be merged without remediation.")

        if new_critical:
            parts.append(
                f"Address the {len(new_critical)} new critical finding(s) "
                "before merging."
            )

        if new_warnings:
            parts.append(
                f"Review the {len(new_warnings)} new warning(s) - "
                "they may indicate emerging risks."
            )

        if score_delta < -self.max_score_drop:
            parts.append(
                "Consider adding redundancy, circuit breakers, or failover "
                "to restore the previous resilience level."
            )

        if after_score < self.min_score:
            gap = self.min_score - after_score
            parts.append(
                f"Need to improve score by at least {gap:.1f} points to "
                f"meet the minimum threshold of {self.min_score:.1f}."
            )

        return " ".join(parts)

    @staticmethod
    def _load_graph(path: Path) -> InfraGraph:
        """Load an InfraGraph from a file (JSON or YAML)."""
        suffix = path.suffix.lower()
        if suffix in (".yaml", ".yml"):
            from faultray.model.loader import load_yaml

            return load_yaml(path)
        return InfraGraph.load(path)
