"""Terraform FaultZero Provider - integrate FaultZero into Terraform workflow.

Analyzes terraform plan files for resilience impact by building before/after
InfraGraphs and comparing their simulation results.

Usage:
    terraform plan -out=plan.out
    faultzero tf-check plan.out --fail-on-regression
"""

from __future__ import annotations

import json
import logging
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from infrasim.discovery.terraform import parse_tf_plan, parse_tf_state
from infrasim.model.graph import InfraGraph
from infrasim.simulator.engine import SimulationEngine

logger = logging.getLogger(__name__)


@dataclass
class TerraformPlanAnalysis:
    """Result of analyzing a terraform plan for resilience impact."""

    plan_file: str
    resources_added: int
    resources_changed: int
    resources_destroyed: int
    score_before: float
    score_after: float
    score_delta: float
    new_risks: list[str]
    resolved_risks: list[str]
    recommendation: str  # "safe to apply" / "review recommended" / "high risk"
    changes: list[dict] = field(default_factory=list)


class TerraformFaultZeroProvider:
    """Integrate FaultZero into Terraform workflow.

    Usage in Terraform:
        terraform plan -out=plan.out
        faultzero tf-check plan.out --fail-on-regression
    """

    def __init__(self, tf_dir: Path | None = None) -> None:
        self.tf_dir = tf_dir

    def analyze_plan(self, plan_file: Path) -> TerraformPlanAnalysis:
        """Analyze a terraform plan for resilience impact.

        Steps:
        1. Load the plan JSON (either from file or via terraform show -json)
        2. Build before/after InfraGraphs
        3. Simulate both
        4. Compare scores
        5. Identify new/resolved risks
        """
        plan_json = self._load_plan_json(plan_file)
        plan_data = parse_tf_plan(plan_json)

        before_graph: InfraGraph = plan_data["before"]
        after_graph: InfraGraph = plan_data["after"]
        changes: list[dict] = plan_data["changes"]

        # Count change types
        resources_added = sum(
            1 for c in changes if c["actions"] == ["create"]
        )
        resources_destroyed = sum(
            1 for c in changes if "delete" in c["actions"] and "create" not in c["actions"]
        )
        resources_changed = len(changes) - resources_added - resources_destroyed

        # Calculate resilience scores
        score_before = before_graph.resilience_score() if before_graph.components else 0.0
        score_after = after_graph.resilience_score() if after_graph.components else 0.0
        score_delta = score_after - score_before

        # Run simulations to find risks
        before_risks = self._find_critical_risks(before_graph)
        after_risks = self._find_critical_risks(after_graph)

        new_risks = sorted(set(after_risks) - set(before_risks))
        resolved_risks = sorted(set(before_risks) - set(after_risks))

        # Determine recommendation
        recommendation = self._determine_recommendation(
            score_delta, new_risks, changes
        )

        return TerraformPlanAnalysis(
            plan_file=str(plan_file),
            resources_added=resources_added,
            resources_changed=resources_changed,
            resources_destroyed=resources_destroyed,
            score_before=round(score_before, 1),
            score_after=round(score_after, 1),
            score_delta=round(score_delta, 1),
            new_risks=new_risks,
            resolved_risks=resolved_risks,
            recommendation=recommendation,
            changes=changes,
        )

    def analyze_plan_json(self, plan_json: dict) -> TerraformPlanAnalysis:
        """Analyze a terraform plan from already-parsed JSON dict.

        This is a convenience method for when the plan JSON is already loaded,
        useful for testing or programmatic usage.
        """
        plan_data = parse_tf_plan(plan_json)

        before_graph: InfraGraph = plan_data["before"]
        after_graph: InfraGraph = plan_data["after"]
        changes: list[dict] = plan_data["changes"]

        resources_added = sum(
            1 for c in changes if c["actions"] == ["create"]
        )
        resources_destroyed = sum(
            1 for c in changes if "delete" in c["actions"] and "create" not in c["actions"]
        )
        resources_changed = len(changes) - resources_added - resources_destroyed

        score_before = before_graph.resilience_score() if before_graph.components else 0.0
        score_after = after_graph.resilience_score() if after_graph.components else 0.0
        score_delta = score_after - score_before

        before_risks = self._find_critical_risks(before_graph)
        after_risks = self._find_critical_risks(after_graph)

        new_risks = sorted(set(after_risks) - set(before_risks))
        resolved_risks = sorted(set(before_risks) - set(after_risks))

        recommendation = self._determine_recommendation(
            score_delta, new_risks, changes
        )

        return TerraformPlanAnalysis(
            plan_file="<json>",
            resources_added=resources_added,
            resources_changed=resources_changed,
            resources_destroyed=resources_destroyed,
            score_before=round(score_before, 1),
            score_after=round(score_after, 1),
            score_delta=round(score_delta, 1),
            new_risks=new_risks,
            resolved_risks=resolved_risks,
            recommendation=recommendation,
            changes=changes,
        )

    def check_policy(self, plan_file: Path, min_score: float = 60.0) -> bool:
        """Policy check: does the plan maintain minimum resilience score?

        Returns True if the plan's after-state score is >= min_score.
        """
        analysis = self.analyze_plan(plan_file)
        return analysis.score_after >= min_score

    def check_policy_json(self, plan_json: dict, min_score: float = 60.0) -> bool:
        """Policy check from already-parsed JSON."""
        analysis = self.analyze_plan_json(plan_json)
        return analysis.score_after >= min_score

    def generate_sentinel_policy(self, min_score: float = 60.0) -> str:
        """Generate a HashiCorp Sentinel policy for FaultZero checks.

        This generates a Sentinel policy that can be used with Terraform
        Enterprise/Cloud to enforce resilience score thresholds.
        """
        return textwrap.dedent(f"""\
            # FaultZero Sentinel Policy
            # Enforces minimum resilience score for infrastructure changes.
            #
            # Install: Add to your Sentinel policy set in Terraform Cloud/Enterprise.
            # Requires: FaultZero CLI installed on the Sentinel runner.

            import "tfplan/v2" as tfplan
            import "subprocess"

            # Minimum resilience score required for plan approval
            min_resilience_score = {min_score}

            # Run FaultZero analysis on the plan
            faultzero_check = rule {{
                result = subprocess.run(["faultzero", "tf-check", "--min-score", string(min_resilience_score), "--json"])
                score_data = json.unmarshal(result.stdout)
                score_data["score_after"] >= min_resilience_score
            }}

            # Main policy rule
            main = rule {{
                faultzero_check
            }}
        """)

    def _load_plan_json(self, plan_file: Path) -> dict:
        """Load plan JSON from a file.

        If the file contains raw JSON, parse it directly.
        Otherwise, try running 'terraform show -json <plan_file>'.
        """
        content = plan_file.read_text(encoding="utf-8", errors="replace")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Not a JSON file -- try terraform show
            return self._run_terraform_show(plan_file)

    def _run_terraform_show(self, plan_file: Path) -> dict:
        """Run 'terraform show -json <plan_file>' and return parsed JSON."""
        cmd = ["terraform", "show", "-json", str(plan_file)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.tf_dir,
        )
        if result.returncode != 0:
            raise RuntimeError(f"terraform show failed: {result.stderr}")
        return json.loads(result.stdout)

    def _find_critical_risks(self, graph: InfraGraph) -> list[str]:
        """Find critical risks in an InfraGraph by running simulation."""
        if not graph.components:
            return []

        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False
        )

        risks = []
        for result in report.critical_findings:
            scenario_name = result.scenario.name if result.scenario else "unknown"
            risks.append(scenario_name)

        return risks

    def _determine_recommendation(
        self,
        score_delta: float,
        new_risks: list[str],
        changes: list[dict],
    ) -> str:
        """Determine the recommendation based on analysis results."""
        # Check for high-risk changes
        high_risk_changes = [c for c in changes if c.get("risk_level", 0) >= 8]

        if high_risk_changes or len(new_risks) >= 3 or score_delta <= -15.0:
            return "high risk"

        if new_risks or score_delta < -5.0:
            return "review recommended"

        return "safe to apply"
