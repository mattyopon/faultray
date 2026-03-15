"""Auto-remediation pipeline for FaultZero.

Orchestrates the full scan -> evaluate -> fix -> validate -> apply cycle.
Dry-run by default for safety.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PipelineStep:
    """A single step in the remediation pipeline."""

    name: str
    status: str = "pending"  # "pending", "running", "passed", "failed", "skipped"
    output: str = ""
    duration_seconds: float = 0.0


@dataclass
class PipelineResult:
    """Result of the full remediation pipeline execution."""

    steps: list[PipelineStep] = field(default_factory=list)
    score_before: float = 0.0
    score_after: float = 0.0
    files_generated: int = 0
    dry_run: bool = True
    success: bool = False

    def to_dict(self) -> dict:
        """Convert to JSON-serialisable dict."""
        return {
            "steps": [
                {
                    "name": s.name,
                    "status": s.status,
                    "output": s.output,
                    "duration_seconds": round(s.duration_seconds, 3),
                }
                for s in self.steps
            ],
            "score_before": round(self.score_before, 1),
            "score_after": round(self.score_after, 1),
            "score_improvement": round(self.score_after - self.score_before, 1),
            "files_generated": self.files_generated,
            "dry_run": self.dry_run,
            "success": self.success,
        }


class AutoRemediationPipeline:
    """Orchestrate: scan -> evaluate -> fix -> validate -> (optional) apply.

    This pipeline is safe by default (dry_run=True) and generates
    remediation IaC code using the IaCGenerator. It validates generated
    code syntax and provides a diff preview before optionally saving files.
    """

    def __init__(
        self,
        graph_or_path: Any,
        output_dir: Path | None = None,
    ) -> None:
        """Initialize the pipeline.

        Args:
            graph_or_path: An InfraGraph instance or a Path to a model file.
            output_dir: Directory for generated remediation files.
                        Defaults to ./remediation-output/
        """
        self._graph = self._resolve_graph(graph_or_path)
        self.output_dir = output_dir or Path("remediation-output")

    def run(
        self,
        target_score: float = 90.0,
        dry_run: bool = True,
    ) -> PipelineResult:
        """Execute the full remediation pipeline.

        Steps:
        1. Evaluate current state
        2. Generate remediation IaC
        3. Validate generated code (syntax check)
        4. Show diff preview
        5. (If not dry_run) Save files
        6. Re-evaluate to predict improvement

        Args:
            target_score: The target resilience score (0-100).
            dry_run: If True (default), preview changes without saving files.

        Returns:
            A PipelineResult with all step outcomes.
        """
        result = PipelineResult(dry_run=dry_run)

        # Step 1: Evaluate current state
        step1 = self._run_step("Evaluate current state", self._step_evaluate)
        result.steps.append(step1)
        if step1.status == "failed":
            return result

        score_before = self._graph.resilience_score()
        result.score_before = score_before

        # Step 2: Generate remediation IaC
        step2 = self._run_step(
            "Generate remediation IaC",
            lambda: self._step_generate(target_score),
        )
        result.steps.append(step2)
        if step2.status == "failed":
            return result

        # Step 3: Validate generated code
        step3 = self._run_step("Validate generated code", self._step_validate)
        result.steps.append(step3)
        # Validation failure is not fatal (warning only)

        # Step 4: Show diff preview
        step4 = self._run_step("Generate diff preview", self._step_diff_preview)
        result.steps.append(step4)

        result.files_generated = len(self._plan.files) if self._plan else 0

        # Step 5: Save files (if not dry_run)
        if dry_run:
            step5 = PipelineStep(name="Save files", status="skipped", output="Dry run mode - files not saved")
            result.steps.append(step5)
        else:
            step5 = self._run_step("Save files", self._step_save_files)
            result.steps.append(step5)
            if step5.status == "failed":
                return result

        # Step 6: Re-evaluate predicted improvement
        step6 = self._run_step("Predict improvement", self._step_predict_improvement)
        result.steps.append(step6)

        if self._plan:
            result.score_after = min(100.0, self._plan.expected_score_after)
        else:
            result.score_after = score_before

        # Determine overall success
        failed_steps = [s for s in result.steps if s.status == "failed"]
        result.success = len(failed_steps) == 0

        # Record to history
        self._record_history()

        return result

    # ------------------------------------------------------------------
    # Internal step implementations
    # ------------------------------------------------------------------

    _plan: Any = None
    _generator: Any = None
    _diff_text: str = ""

    def _run_step(self, name: str, func: Any) -> PipelineStep:
        """Execute a pipeline step with timing and error handling."""
        step = PipelineStep(name=name, status="running")
        start = time.monotonic()
        try:
            output = func()
            step.output = str(output) if output else "OK"
            step.status = "passed"
        except Exception as exc:
            step.output = str(exc)
            step.status = "failed"
        step.duration_seconds = time.monotonic() - start
        return step

    def _step_evaluate(self) -> str:
        """Evaluate the current infrastructure state."""
        score = self._graph.resilience_score()
        v2 = self._graph.resilience_score_v2()
        v2_score = v2.get("score", 0.0) if isinstance(v2, dict) else 0.0
        comp_count = len(self._graph.components)
        dep_count = len(self._graph.all_dependency_edges())

        return (
            f"Score: {score:.1f}/100 (v2: {v2_score:.1f}/100), "
            f"{comp_count} components, {dep_count} dependencies"
        )

    def _step_generate(self, target_score: float) -> str:
        """Generate remediation IaC code."""
        from infrasim.remediation.iac_generator import IaCGenerator

        self._generator = IaCGenerator(self._graph)
        self._plan = self._generator.generate(target_score=target_score)

        file_count = len(self._plan.files)
        cost = self._plan.total_monthly_cost
        improvement = self._plan.expected_score_after - self._plan.expected_score_before

        if file_count == 0:
            return "No remediations needed - infrastructure meets target score."

        return (
            f"Generated {file_count} remediation files "
            f"(+{improvement:.1f} score improvement, "
            f"${cost:,.2f}/month estimated cost)"
        )

    def _step_validate(self) -> str:
        """Validate the syntax of generated IaC code."""
        if not self._plan or not self._plan.files:
            return "No files to validate."

        errors: list[str] = []
        warnings: list[str] = []

        for f in self._plan.files:
            file_errors = self._validate_file(f)
            if file_errors:
                for err in file_errors:
                    if "warning" in err.lower():
                        warnings.append(f"{f.path}: {err}")
                    else:
                        errors.append(f"{f.path}: {err}")

        if errors:
            raise ValueError(
                f"Validation errors: {len(errors)} error(s), {len(warnings)} warning(s). "
                f"First error: {errors[0]}"
            )

        return f"All {len(self._plan.files)} files passed validation ({len(warnings)} warnings)"

    def _step_diff_preview(self) -> str:
        """Generate a diff preview of the remediation plan."""
        if not self._plan or not self._generator:
            return "No plan to preview."

        self._diff_text = self._generator.dry_run(self._plan)
        lines = self._diff_text.strip().split("\n")
        return f"Diff preview generated ({len(lines)} lines)"

    def _step_save_files(self) -> str:
        """Write remediation files to disk."""
        if not self._plan or not self._generator:
            return "No plan to save."

        self._generator.write_to_directory(self._plan, self.output_dir)

        file_count = len(self._plan.files)
        return f"Saved {file_count} files to {self.output_dir}"

    def _step_predict_improvement(self) -> str:
        """Predict the resilience score after applying remediations."""
        if not self._plan:
            return "No plan available for prediction."

        before = self._plan.expected_score_before
        after = self._plan.expected_score_after
        delta = after - before
        risk_reduction = self._plan.risk_reduction_percent

        return (
            f"Predicted score: {before:.1f} -> {after:.1f} (+{delta:.1f}), "
            f"risk reduction: {risk_reduction:.1f}%"
        )

    def _validate_file(self, remediation_file: Any) -> list[str]:
        """Validate a single remediation file's content.

        Performs basic syntax checks for Terraform and Kubernetes files.
        """
        errors: list[str] = []
        content = remediation_file.content
        path = remediation_file.path

        if path.endswith(".tf"):
            errors.extend(self._validate_terraform(content))
        elif path.endswith((".yaml", ".yml")):
            errors.extend(self._validate_kubernetes(content))

        return errors

    def _validate_terraform(self, content: str) -> list[str]:
        """Basic Terraform syntax validation (brace matching)."""
        errors: list[str] = []

        # Check brace balance
        open_count = content.count("{")
        close_count = content.count("}")
        if open_count != close_count:
            errors.append(
                f"Unbalanced braces: {open_count} opening, {close_count} closing"
            )

        # Check for resource blocks
        if "resource " not in content and "data " not in content and "module " not in content:
            errors.append("Warning: No resource, data, or module blocks found")

        return errors

    def _validate_kubernetes(self, content: str) -> list[str]:
        """Basic Kubernetes YAML validation."""
        errors: list[str] = []

        if "apiVersion:" not in content and "kind:" not in content:
            errors.append("Warning: Missing apiVersion or kind fields")

        return errors

    def get_diff_preview(self) -> str:
        """Return the cached diff preview text from the last run."""
        return self._diff_text

    def _resolve_graph(self, graph_or_path: Any) -> Any:
        """Resolve graph_or_path to an InfraGraph instance."""
        if isinstance(graph_or_path, (str, Path)):
            path = Path(graph_or_path)
            from infrasim.model.graph import InfraGraph

            if str(path).endswith((".yaml", ".yml")):
                from infrasim.model.loader import load_yaml
                return load_yaml(path)
            return InfraGraph.load(path)

        return graph_or_path

    def _record_history(self) -> None:
        """Try to record the pipeline run to history."""
        try:
            from infrasim.history import HistoryTracker

            tracker = HistoryTracker()
            tracker.record(self._graph)
        except Exception:
            pass  # Best-effort
