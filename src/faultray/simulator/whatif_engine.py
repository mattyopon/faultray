"""What-if Analysis engine for FaultRay v4.0.

Runs parametric sweeps over operational scenarios, varying one parameter
at a time (MTTR, MTBF, traffic, replicas, maintenance duration) and
reporting the impact on SLO compliance.  This enables capacity planning
and risk assessment by answering questions like "What if MTTR doubles?"
or "What if traffic spikes 3x?".
"""

from __future__ import annotations

import copy
import logging
import random
from typing import Any

from pydantic import BaseModel

from faultray.model.graph import InfraGraph
import faultray.simulator.ops_engine as ops_engine_mod
from faultray.simulator.ops_engine import (
    OpsScenario,
    OpsSimulationEngine,
    OpsSimulationResult,
    TimeUnit,
)
from faultray.simulator.traffic import create_diurnal_weekly

logger = logging.getLogger(__name__)

# Supported sweep parameter names.
SUPPORTED_PARAMETERS: set[str] = {
    "mttr_factor",
    "mtbf_factor",
    "traffic_factor",
    "replica_factor",
    "maint_duration_factor",
}

# SLO pass threshold: average availability >= 99.9%.
_SLO_THRESHOLD = 99.9


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class WhatIfScenario(BaseModel):
    """Configuration for a single what-if parametric sweep.

    Attributes
    ----------
    base_scenario:
        The base OpsScenario to modify for each sweep value.
    parameter:
        Which parameter to sweep.  Must be one of ``SUPPORTED_PARAMETERS``.
    values:
        List of factor values to test (e.g. [0.5, 0.75, 1.0, 1.5, 2.0]).
    description:
        Human-readable description of the what-if analysis.
    """

    base_scenario: OpsScenario
    parameter: str
    values: list[float]
    description: str = ""
    seed: int = 42


class WhatIfResult(BaseModel):
    """Result of a what-if parametric sweep.

    Attributes
    ----------
    parameter:
        The parameter that was swept.
    values:
        The factor values that were tested.
    avg_availabilities:
        Average availability (%) for each sweep value.
    min_availabilities:
        Minimum availability (%) observed for each sweep value.
    total_failures:
        Total failure event count for each sweep value.
    total_downtimes:
        Total downtime in seconds for each sweep value.
    slo_pass:
        Whether average availability >= 99.9% for each sweep value.
    breakpoint_value:
        The first value where the SLO fails, or ``None`` if all pass.
    summary:
        Human-readable summary of the analysis.
    """

    parameter: str
    values: list[float]
    avg_availabilities: list[float]
    min_availabilities: list[float]
    total_failures: list[int]
    total_downtimes: list[float]
    slo_pass: list[bool]
    breakpoint_value: float | None = None
    summary: str = ""


class MultiWhatIfScenario(BaseModel):
    """Configuration for a multi-parameter what-if analysis."""

    base_scenario: OpsScenario
    parameters: dict[str, float]  # e.g., {"mttr_factor": 2.0, "traffic_factor": 3.0}
    description: str = ""
    seed: int = 42


class MultiWhatIfResult(BaseModel):
    """Result of a multi-parameter what-if analysis."""

    parameters: dict[str, float]
    avg_availability: float
    min_availability: float
    total_failures: int
    total_downtime_seconds: float
    slo_pass: bool
    summary: str = ""


# ---------------------------------------------------------------------------
# What-if Engine
# ---------------------------------------------------------------------------


class WhatIfEngine:
    """Parametric sweep engine for what-if analysis.

    For each value in a ``WhatIfScenario``, modifies the infrastructure
    graph or scenario configuration, runs the operational simulation, and
    collects the results to identify SLO breakpoints.

    Parameters
    ----------
    graph:
        The base infrastructure graph to use for simulations.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_whatif(self, whatif: WhatIfScenario) -> WhatIfResult:
        """Run a single what-if parametric sweep.

        For each value in ``whatif.values``, applies the corresponding
        parameter modification to a deep copy of the graph/scenario,
        runs the operational simulation, and collects metrics.

        Parameters
        ----------
        whatif:
            The what-if scenario configuration.

        Returns
        -------
        WhatIfResult
            Aggregated results across all sweep values.

        Raises
        ------
        ValueError
            If ``whatif.parameter`` is not in ``SUPPORTED_PARAMETERS``.
        """
        if whatif.parameter not in SUPPORTED_PARAMETERS:
            raise ValueError(
                f"Unsupported parameter '{whatif.parameter}'. "
                f"Must be one of: {sorted(SUPPORTED_PARAMETERS)}"
            )

        avg_availabilities: list[float] = []
        min_availabilities: list[float] = []
        total_failures: list[int] = []
        total_downtimes: list[float] = []
        slo_pass: list[bool] = []

        original_rng = ops_engine_mod._ops_rng
        try:
            for value in whatif.values:
                logger.info(
                    "What-if: %s=%s (scenario=%s)",
                    whatif.parameter,
                    value,
                    whatif.base_scenario.id,
                )

                # Apply the parameter modification
                modified_graph, modified_scenario = self._apply_factor(
                    whatif.parameter, value, whatif.base_scenario
                )

                # Reset the module-level RNG to ensure identical random
                # event sequences across sweep values, making results
                # truly comparable.
                ops_engine_mod._ops_rng = random.Random(whatif.seed)

                # Run the ops simulation on the modified graph
                engine = OpsSimulationEngine(modified_graph)
                result = engine.run_ops_scenario(modified_scenario)

                # Collect metrics
                avg_avail = self._compute_avg_availability(result)
                avg_availabilities.append(round(avg_avail, 4))
                min_availabilities.append(result.min_availability)
                total_failures.append(result.total_failures)
                total_downtimes.append(result.total_downtime_seconds)
                slo_pass.append(avg_avail >= _SLO_THRESHOLD)
        finally:
            ops_engine_mod._ops_rng = original_rng

        # Find the breakpoint: first value where SLO fails
        breakpoint_value: float | None = None
        for i, passed in enumerate(slo_pass):
            if not passed:
                breakpoint_value = whatif.values[i]
                break

        whatif_result = WhatIfResult(
            parameter=whatif.parameter,
            values=whatif.values,
            avg_availabilities=avg_availabilities,
            min_availabilities=min_availabilities,
            total_failures=total_failures,
            total_downtimes=total_downtimes,
            slo_pass=slo_pass,
            breakpoint_value=breakpoint_value,
            summary=self._build_whatif_summary(
                whatif, avg_availabilities, slo_pass, breakpoint_value
            ),
        )

        return whatif_result

    def run_default_whatifs(self) -> list[WhatIfResult]:
        """Run the 5 default what-if analyses.

        Uses the 7-day full operations scenario as the base scenario
        and sweeps each of the 5 supported parameters across a
        representative range of values.

        Returns
        -------
        list[WhatIfResult]
            Results for all 5 default what-if analyses.
        """
        base_scenario = self._create_default_base_scenario()

        default_whatifs: list[WhatIfScenario] = [
            WhatIfScenario(
                base_scenario=base_scenario,
                parameter="mttr_factor",
                values=[0.5, 1.0, 2.0, 4.0, 8.0],
                description="What if MTTR doubles?",
            ),
            WhatIfScenario(
                base_scenario=base_scenario,
                parameter="mtbf_factor",
                values=[0.05, 0.1, 0.25, 0.5, 1.0],
                description="What if MTBF drops drastically?",
            ),
            WhatIfScenario(
                base_scenario=base_scenario,
                parameter="traffic_factor",
                values=[1.0, 1.5, 2.0, 3.0, 5.0],
                description="What if traffic spikes?",
            ),
            WhatIfScenario(
                base_scenario=base_scenario,
                parameter="replica_factor",
                values=[0.5, 0.75, 1.0, 1.25, 1.5],
                description="What if we reduce replicas?",
            ),
            WhatIfScenario(
                base_scenario=base_scenario,
                parameter="maint_duration_factor",
                values=[0.5, 1.0, 2.0, 3.0, 5.0],
                description="What if maintenance takes longer?",
            ),
        ]

        results: list[WhatIfResult] = []
        for whatif in default_whatifs:
            result = self.run_whatif(whatif)
            results.append(result)

        return results

    def run_multi_whatif(self, whatif: MultiWhatIfScenario) -> MultiWhatIfResult:
        """Run a multi-parameter what-if analysis.

        Applies ALL parameter modifications simultaneously to a single
        graph/scenario copy, runs the simulation, and returns the result.

        Parameters
        ----------
        whatif:
            The multi-parameter what-if scenario configuration.

        Returns
        -------
        MultiWhatIfResult
            Result of the combined parameter simulation.

        Raises
        ------
        ValueError
            If any parameter in ``whatif.parameters`` is not in
            ``SUPPORTED_PARAMETERS``.
        """
        unsupported = set(whatif.parameters.keys()) - SUPPORTED_PARAMETERS
        if unsupported:
            raise ValueError(
                f"Unsupported parameter(s): {sorted(unsupported)}. "
                f"Must be one of: {sorted(SUPPORTED_PARAMETERS)}"
            )

        logger.info(
            "Multi what-if: %s (scenario=%s)",
            whatif.parameters,
            whatif.base_scenario.id,
        )

        # Start from a deep copy of the graph and scenario
        modified_graph = copy.deepcopy(self.graph)
        modified_scenario = whatif.base_scenario.model_copy(deep=True)

        # Apply all parameter modifications sequentially to the same
        # graph/scenario copies.
        for param, value in whatif.parameters.items():
            # Use _apply_factor which returns new copies; we need to
            # apply modifications cumulatively on the same objects.
            if param == "mttr_factor":
                for comp in modified_graph.components.values():
                    if comp.operational_profile.mttr_minutes <= 0:
                        comp.operational_profile.mttr_minutes = (
                            ops_engine_mod._DEFAULT_MTTR_MINUTES.get(
                                comp.type.value, 30.0
                            )
                        )
                    comp.operational_profile.mttr_minutes *= value
            elif param == "mtbf_factor":
                for comp in modified_graph.components.values():
                    if comp.operational_profile.mtbf_hours <= 0:
                        comp.operational_profile.mtbf_hours = (
                            ops_engine_mod._DEFAULT_MTBF_HOURS.get(
                                comp.type.value, 2160.0
                            )
                        )
                    comp.operational_profile.mtbf_hours *= value
            elif param == "traffic_factor":
                for pattern in modified_scenario.traffic_patterns:
                    pattern.base_multiplier *= value
            elif param == "replica_factor":
                for comp in modified_graph.components.values():
                    original = comp.replicas
                    unclamped = round(original * value)
                    new_replicas = max(1, unclamped)
                    comp.replicas = new_replicas
                    # Only adjust metrics when replicas actually changed
                    # and clamping did not prevent the reduction.
                    if (
                        original > 0
                        and new_replicas != original
                        and unclamped == new_replicas
                    ):
                        load_ratio = original / new_replicas
                        comp.metrics.cpu_percent = min(
                            100.0, comp.metrics.cpu_percent * load_ratio
                        )
                        comp.metrics.memory_percent = min(
                            100.0, comp.metrics.memory_percent * load_ratio
                        )
                    if comp.autoscaling.enabled:
                        comp.autoscaling.min_replicas = max(
                            1, round(comp.autoscaling.min_replicas * value)
                        )
                        comp.autoscaling.max_replicas = max(
                            1, round(comp.autoscaling.max_replicas * value)
                        )
            elif param == "maint_duration_factor":
                modified_scenario.maintenance_duration_factor = value

        # Reset the module-level RNG for reproducibility, restoring after
        original_rng = ops_engine_mod._ops_rng
        try:
            ops_engine_mod._ops_rng = random.Random(whatif.seed)

            # Run the ops simulation
            engine = OpsSimulationEngine(modified_graph)
            result = engine.run_ops_scenario(modified_scenario)
        finally:
            ops_engine_mod._ops_rng = original_rng

        # Collect metrics
        avg_avail = self._compute_avg_availability(result)

        param_desc = ", ".join(
            f"{k}={v}" for k, v in whatif.parameters.items()
        )
        description = whatif.description or f"Multi what-if: {param_desc}"
        slo_passed = avg_avail >= _SLO_THRESHOLD

        summary_lines = [
            f"Analysis: {description}",
            f"Parameters: {whatif.parameters}",
            f"Avg Availability: {avg_avail:.4f}%",
            f"Min Availability: {result.min_availability:.2f}%",
            f"Total Failures: {result.total_failures}",
            f"SLO ({_SLO_THRESHOLD}%): {'PASS' if slo_passed else 'FAIL'}",
        ]

        return MultiWhatIfResult(
            parameters=whatif.parameters,
            avg_availability=round(avg_avail, 4),
            min_availability=result.min_availability,
            total_failures=result.total_failures,
            total_downtime_seconds=result.total_downtime_seconds,
            slo_pass=slo_passed,
            summary="\n".join(summary_lines),
        )

    def run_default_multi_whatifs(self) -> list[MultiWhatIfResult]:
        """Run default multi-parameter combinations.

        Tests key parameter combinations to evaluate combined effects
        on system availability and SLO compliance.

        Returns
        -------
        list[MultiWhatIfResult]
            Results for all default multi-parameter combinations.
        """
        base_scenario = self._create_default_base_scenario()

        default_combos: list[MultiWhatIfScenario] = [
            MultiWhatIfScenario(
                base_scenario=base_scenario,
                parameters={"mttr_factor": 2.0, "maint_duration_factor": 2.0},
                description="Worst case: slow recovery + long maintenance",
            ),
            MultiWhatIfScenario(
                base_scenario=base_scenario,
                parameters={"traffic_factor": 3.0, "mtbf_factor": 0.5},
                description="Growth stress: high traffic + frequent failures",
            ),
            MultiWhatIfScenario(
                base_scenario=base_scenario,
                parameters={"replica_factor": 0.5, "mttr_factor": 2.0},
                description="Cost optimized: fewer replicas + slow recovery",
            ),
            MultiWhatIfScenario(
                base_scenario=base_scenario,
                parameters={"mttr_factor": 0.25, "maint_duration_factor": 0.5},
                description="Best case: fast recovery + short maintenance",
            ),
        ]

        results: list[MultiWhatIfResult] = []
        for combo in default_combos:
            result = self.run_multi_whatif(combo)
            results.append(result)

        return results

    # ------------------------------------------------------------------
    # Parameter application methods
    # ------------------------------------------------------------------

    def _apply_factor(
        self,
        parameter: str,
        value: float,
        base_scenario: OpsScenario,
    ) -> tuple[InfraGraph, OpsScenario]:
        """Apply a sweep factor to a deep copy of the graph and scenario.

        Parameters
        ----------
        parameter:
            The parameter name to modify.
        value:
            The factor value to apply.
        base_scenario:
            The base scenario (will be deep-copied if modified).

        Returns
        -------
        tuple[InfraGraph, OpsScenario]
            The modified graph and scenario.
        """
        dispatch = {
            "mttr_factor": self._apply_mttr_factor,
            "mtbf_factor": self._apply_mtbf_factor,
            "traffic_factor": self._apply_traffic_factor,
            "replica_factor": self._apply_replica_factor,
            "maint_duration_factor": self._apply_maint_duration_factor,
        }

        apply_fn = dispatch[parameter]
        return apply_fn(value, base_scenario)

    def _apply_mttr_factor(
        self, factor: float, base_scenario: OpsScenario
    ) -> tuple[InfraGraph, OpsScenario]:
        """Multiply all component MTTR values by *factor*.

        A factor of 2.0 means recovery takes twice as long;
        0.5 means recovery is twice as fast.

        Pre-populates zero MTTR values with type-based defaults before
        applying the factor, because ``0 * factor = 0`` would make
        the factor ineffective.

        Parameters
        ----------
        factor:
            Multiplicative factor for MTTR.
        base_scenario:
            The base scenario (returned as-is).

        Returns
        -------
        tuple[InfraGraph, OpsScenario]
            Modified graph with scaled MTTR and the original scenario.
        """
        graph = copy.deepcopy(self.graph)
        max_mtbf_hours = base_scenario.duration_days * 24.0
        for comp in graph.components.values():
            if comp.operational_profile.mtbf_hours <= 0:
                comp.operational_profile.mtbf_hours = (
                    ops_engine_mod._DEFAULT_MTBF_HOURS.get(
                        comp.type.value, 2160.0
                    )
                )
            comp.operational_profile.mtbf_hours = min(
                comp.operational_profile.mtbf_hours, max_mtbf_hours
            )
            if comp.operational_profile.mttr_minutes <= 0:
                comp.operational_profile.mttr_minutes = (
                    ops_engine_mod._DEFAULT_MTTR_MINUTES.get(
                        comp.type.value, 30.0
                    )
                )
            comp.operational_profile.mttr_minutes *= factor
        return graph, base_scenario

    def _apply_mtbf_factor(
        self, factor: float, base_scenario: OpsScenario
    ) -> tuple[InfraGraph, OpsScenario]:
        """Multiply all component MTBF values by *factor*.

        A factor of 0.5 means failures happen twice as often;
        2.0 means components are twice as reliable.

        Pre-populates zero MTBF values with type-based defaults before
        applying the factor, because ``0 * factor = 0`` would make
        the factor ineffective.

        Parameters
        ----------
        factor:
            Multiplicative factor for MTBF.
        base_scenario:
            The base scenario (returned as-is).

        Returns
        -------
        tuple[InfraGraph, OpsScenario]
            Modified graph with scaled MTBF and the original scenario.
        """
        graph = copy.deepcopy(self.graph)
        for comp in graph.components.values():
            # Pre-populate zero MTBF with type-based defaults
            if comp.operational_profile.mtbf_hours <= 0:
                comp.operational_profile.mtbf_hours = (
                    ops_engine_mod._DEFAULT_MTBF_HOURS.get(
                        comp.type.value, 2160.0
                    )
                )
            comp.operational_profile.mtbf_hours *= factor
        return graph, base_scenario

    def _apply_traffic_factor(
        self, factor: float, base_scenario: OpsScenario
    ) -> tuple[InfraGraph, OpsScenario]:
        """Multiply traffic pattern peak multipliers by *factor*.

        A factor of 2.0 means traffic peaks are twice as high;
        0.5 means traffic is halved.

        Parameters
        ----------
        factor:
            Multiplicative factor for traffic peak multipliers.
        base_scenario:
            The base scenario (will be deep-copied and modified).

        Returns
        -------
        tuple[InfraGraph, OpsScenario]
            Original graph and modified scenario with scaled traffic.
        """
        scenario = base_scenario.model_copy(deep=True)
        for pattern in scenario.traffic_patterns:
            pattern.base_multiplier *= factor
        return copy.deepcopy(self.graph), scenario

    def _apply_replica_factor(
        self, factor: float, base_scenario: OpsScenario
    ) -> tuple[InfraGraph, OpsScenario]:
        """Multiply all component replica counts by *factor*.

        The resulting replica count is rounded to the nearest integer
        and clamped to a minimum of 1.  Autoscaling min/max replicas
        are also scaled proportionally.

        When replicas decrease, per-replica load increases proportionally.
        Component metrics (CPU, memory) are scaled inversely to reflect
        this: halving replicas roughly doubles each instance's load.

        A factor of 0.5 means half the replicas; 1.5 means 50% more.

        Parameters
        ----------
        factor:
            Multiplicative factor for replica counts.
        base_scenario:
            The base scenario (returned as-is).

        Returns
        -------
        tuple[InfraGraph, OpsScenario]
            Modified graph with scaled replicas and the original scenario.
        """
        graph = copy.deepcopy(self.graph)
        for comp in graph.components.values():
            original = comp.replicas
            unclamped = round(original * factor)
            new_replicas = max(1, unclamped)
            comp.replicas = new_replicas

            # Scale metrics inversely: fewer replicas → higher per-instance
            # load.  This ensures the simulation reflects the actual impact
            # of reducing or increasing replica counts.
            # Skip adjustment when clamping prevented the intended reduction.
            if (
                original > 0
                and new_replicas != original
                and unclamped == new_replicas
            ):
                load_ratio = original / new_replicas
                comp.metrics.cpu_percent = min(
                    100.0, comp.metrics.cpu_percent * load_ratio
                )
                comp.metrics.memory_percent = min(
                    100.0, comp.metrics.memory_percent * load_ratio
                )

            if comp.autoscaling.enabled:
                comp.autoscaling.min_replicas = max(
                    1, round(comp.autoscaling.min_replicas * factor)
                )
                comp.autoscaling.max_replicas = max(
                    1, round(comp.autoscaling.max_replicas * factor)
                )
        return graph, base_scenario

    def _apply_maint_duration_factor(
        self, factor: float, base_scenario: OpsScenario
    ) -> tuple[InfraGraph, OpsScenario]:
        """Multiply all maintenance duration values by *factor*.

        Sets ``maintenance_duration_factor`` on the scenario so the
        ops engine applies the multiplier to type-based default
        maintenance durations.  A factor of 2.0 means maintenance
        windows last twice as long.

        Parameters
        ----------
        factor:
            Multiplicative factor for maintenance durations.
        base_scenario:
            The base scenario (will be deep-copied and modified).

        Returns
        -------
        tuple[InfraGraph, OpsScenario]
            Original graph (deep-copied) and modified scenario with
            the maintenance duration factor applied.
        """
        scenario = base_scenario.model_copy(deep=True)
        scenario.maintenance_duration_factor = factor
        return copy.deepcopy(self.graph), scenario

    # ------------------------------------------------------------------
    # Default base scenario
    # ------------------------------------------------------------------

    def _create_default_base_scenario(self) -> OpsScenario:
        """Create the default 7-day full operations base scenario.

        Mirrors the "ops-7d-full" scenario from
        ``OpsSimulationEngine.run_default_ops_scenarios()`` with
        deployments, random failures, degradation, and maintenance
        enabled.

        Returns
        -------
        OpsScenario
            A fully-configured 7-day operational scenario.
        """
        component_ids = list(self.graph.components.keys())

        # Identify app-server-like components for deploy targets
        deploy_targets: list[str] = []
        for comp_id, comp in self.graph.components.items():
            if comp.type.value in ("app_server", "web_server"):
                deploy_targets.append(comp_id)
        if not deploy_targets:
            deploy_targets = (
                component_ids[:2]
                if len(component_ids) >= 2
                else list(component_ids)
            )

        # Scheduled deploys on Tuesday and Thursday at 14:00
        tuesday_deploys: list[dict[str, Any]] = [
            {
                "component_id": comp_id,
                "day_of_week": 1,
                "hour": 14,
                "downtime_seconds": 30,
            }
            for comp_id in deploy_targets
        ]
        thursday_deploys: list[dict[str, Any]] = [
            {
                "component_id": comp_id,
                "day_of_week": 3,
                "hour": 14,
                "downtime_seconds": 30,
            }
            for comp_id in deploy_targets
        ]

        return OpsScenario(
            id="whatif-7d-full",
            name="7-day full operations (what-if base)",
            description=(
                "Full operational simulation for 7 days including "
                "diurnal-weekly traffic, scheduled deployments "
                "(Tue/Thu), random MTBF-based failures, gradual "
                "degradation (memory leaks, disk fill), and "
                "weekly maintenance windows.  Used as the base "
                "scenario for what-if analysis."
            ),
            duration_days=7,
            time_unit=TimeUnit.FIVE_MINUTES,
            traffic_patterns=[
                create_diurnal_weekly(
                    peak=2.5, duration=604800, weekend_factor=0.6
                ),
            ],
            scheduled_deploys=tuesday_deploys + thursday_deploys,
            enable_random_failures=True,
            enable_degradation=True,
            enable_maintenance=True,
            maintenance_day_of_week=6,  # Sunday
            maintenance_hour=2,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_avg_availability(result: OpsSimulationResult) -> float:
        """Compute the average availability across all SLI data points.

        Parameters
        ----------
        result:
            The simulation result containing the SLI timeline.

        Returns
        -------
        float
            Average availability percentage, or 100.0 if no data.
        """
        if not result.sli_timeline:
            return 100.0
        total = sum(p.availability_percent for p in result.sli_timeline)
        return total / len(result.sli_timeline)

    @staticmethod
    def _build_whatif_summary(
        whatif: WhatIfScenario,
        avg_availabilities: list[float],
        slo_pass: list[bool],
        breakpoint_value: float | None,
    ) -> str:
        """Build a human-readable summary of the what-if analysis.

        Parameters
        ----------
        whatif:
            The what-if scenario configuration.
        avg_availabilities:
            Average availability for each sweep value.
        slo_pass:
            SLO pass/fail for each sweep value.
        breakpoint_value:
            First value where SLO fails, or None.

        Returns
        -------
        str
            Multi-line summary string.
        """
        lines: list[str] = []

        if whatif.description:
            lines.append(f"Analysis: {whatif.description}")

        lines.append(f"Parameter: {whatif.parameter}")
        lines.append(f"Sweep values: {whatif.values}")
        lines.append("")

        # Results table
        lines.append(f"{'Value':>8}  {'Avg Avail':>10}  {'SLO':>6}")
        lines.append(f"{'-----':>8}  {'----------':>10}  {'------':>6}")
        for i, value in enumerate(whatif.values):
            avail_str = f"{avg_availabilities[i]:.4f}%"
            slo_str = "PASS" if slo_pass[i] else "FAIL"
            lines.append(f"{value:>8.2f}  {avail_str:>10}  {slo_str:>6}")

        lines.append("")
        if breakpoint_value is not None:
            lines.append(
                f"SLO breakpoint: {whatif.parameter}={breakpoint_value} "
                f"(first value where avg availability < {_SLO_THRESHOLD}%)"
            )
        else:
            lines.append(
                f"All values passed the {_SLO_THRESHOLD}% SLO threshold."
            )

        return "\n".join(lines)
