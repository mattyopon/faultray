# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Autopilot Pipeline: 要件定義→トポロジー設計→シミュレーション検証→Terraform生成の全自動フロー。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from faultray.autopilot.requirements_parser import RequirementsParser, RequirementsSpec
from faultray.autopilot.terraform_generator import TerraformGenerator, TerraformOutput
from faultray.autopilot.topology_designer import TopologyDesigner
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine, SimulationReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    """Complete result of the autopilot pipeline."""

    spec: RequirementsSpec | None = None
    graph: InfraGraph | None = None
    simulation: SimulationReport | None = None
    terraform: TerraformOutput | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    @property
    def availability_score(self) -> float:
        """Return simulated resilience score (0-100) or 0 if not simulated."""
        if self.simulation is not None:
            return self.simulation.resilience_score
        return 0.0


# ---------------------------------------------------------------------------
# AutopilotPipeline
# ---------------------------------------------------------------------------


class AutopilotPipeline:
    """Orchestrate the full autopilot pipeline.

    Steps:
      1. Parse requirements (text / file)
      2. Design topology (InfraGraph)
      3. Simulate (SimulationEngine)
      4. Generate Terraform HCL
    """

    def __init__(self) -> None:
        self._parser = RequirementsParser()
        self._designer = TopologyDesigner()
        self._tf_gen = TerraformGenerator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_from_text(self, text: str) -> PipelineResult:
        """Run full pipeline from requirements text."""
        result = PipelineResult()

        # Step 1: Parse
        try:
            spec = self._parser.parse_text(text)
            result.spec = spec
            logger.info("Step 1 complete: parsed requirements for '%s'", spec.app_name)
        except Exception as exc:
            result.errors.append(f"Step 1 (Requirements Parsing) failed: {exc}")
            return result

        return self._run_steps_2_to_4(result)

    def run_from_file(self, requirements_path: Path) -> PipelineResult:
        """Run full pipeline from a requirements file (Markdown / plain text)."""
        result = PipelineResult()

        if not requirements_path.exists():
            result.errors.append(f"Requirements file not found: {requirements_path}")
            return result

        # Step 1: Parse
        try:
            spec = self._parser.parse_file(requirements_path)
            result.spec = spec
            logger.info(
                "Step 1 complete: parsed requirements from '%s'", requirements_path
            )
        except Exception as exc:
            result.errors.append(f"Step 1 (Requirements Parsing) failed: {exc}")
            return result

        return self._run_steps_2_to_4(result)

    def run_from_yaml(self, yaml_path: Path) -> PipelineResult:
        """Run Terraform generation only from an existing InfraGraph YAML."""
        result = PipelineResult()

        if not yaml_path.exists():
            result.errors.append(f"YAML file not found: {yaml_path}")
            return result

        try:
            from faultray.model.graph import InfraGraph

            graph = InfraGraph.load(yaml_path)
            result.graph = graph
        except Exception as exc:
            result.errors.append(f"Failed to load YAML topology: {exc}")
            return result

        # Create a minimal spec for the generator
        spec = RequirementsSpec(
            app_name=yaml_path.stem,
            app_type="web_app",
        )
        result.spec = spec

        # Step 4: Generate Terraform
        result = self._step_4_terraform(result, generate_only=True)
        return result

    def terraform_only(self, result: PipelineResult, output_dir: Path) -> None:
        """Write Terraform files to output_dir (no deploy)."""
        if result.terraform is None:
            logger.warning("No Terraform output to write.")
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in result.terraform.files.items():
            filepath = output_dir / filename
            filepath.write_text(content, encoding="utf-8")
            logger.info("Written: %s", filepath)

    # ------------------------------------------------------------------
    # Private steps
    # ------------------------------------------------------------------

    def _run_steps_2_to_4(self, result: PipelineResult) -> PipelineResult:
        if result.spec is None:
            raise ValueError("_run_steps_2_to_4: result.spec must not be None")

        # Step 2: Design topology
        try:
            graph = self._designer.design(result.spec)
            result.graph = graph
            logger.info(
                "Step 2 complete: topology with %d components", len(graph.components)
            )
        except Exception as exc:
            result.errors.append(f"Step 2 (Topology Design) failed: {exc}")
            return result

        # Step 3: Simulate
        result = self._step_3_simulate(result)
        if not result.success:
            return result

        # Step 4: Generate Terraform
        result = self._step_4_terraform(result)
        return result

    def _step_3_simulate(self, result: PipelineResult) -> PipelineResult:
        """Run SimulationEngine against the designed graph."""
        if result.graph is None:
            raise ValueError("_step_3_simulate: result.graph must not be None")

        try:
            engine = SimulationEngine(result.graph)
            report = engine.run_all_defaults()
            result.simulation = report
            logger.info(
                "Step 3 complete: resilience_score=%.1f, critical=%d",
                report.resilience_score,
                len(report.critical_findings),
            )

            # Warn if simulation found critical issues
            for finding in report.critical_findings[:5]:  # cap to 5 warnings
                result.warnings.append(
                    f"[SIMULATION CRITICAL] {finding.scenario.name}: "
                    f"risk_score={finding.risk_score:.1f}"
                )
        except Exception as exc:
            # Simulation failure is non-fatal; continue to Terraform generation
            logger.warning("Step 3 (Simulation) encountered an error: %s", exc)
            result.warnings.append(f"Step 3 (Simulation) skipped: {exc}")

        return result

    def _step_4_terraform(
        self, result: PipelineResult, generate_only: bool = False
    ) -> PipelineResult:
        """Generate Terraform HCL from InfraGraph."""
        if result.graph is None:
            raise ValueError("_step_4_terraform: result.graph must not be None")
        if result.spec is None:
            raise ValueError("_step_4_terraform: result.spec must not be None")

        try:
            tf_output = self._tf_gen.generate(result.graph, result.spec)
            result.terraform = tf_output
            result.warnings.extend(tf_output.warnings)
            logger.info(
                "Step 4 complete: generated %d Terraform files",
                len(tf_output.files),
            )
        except Exception as exc:
            result.errors.append(f"Step 4 (Terraform Generation) failed: {exc}")

        return result
