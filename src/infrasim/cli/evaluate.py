"""Cross-engine evaluation CLI command.

Runs all 5 simulation engines sequentially and produces a unified summary
covering static simulation, dynamic simulation, ops simulation, what-if
analysis, and capacity planning.
"""

from __future__ import annotations

import json as json_lib
import logging
import sys
from pathlib import Path

import typer

from infrasim.features import is_enabled

from infrasim.cli.main import (
    DEFAULT_MODEL_PATH,
    _load_graph_for_analysis,
    app,
    console,
)


def _compute_avg_availability(sli_timeline: list) -> float:
    """Compute average availability from an SLI timeline."""
    if not sli_timeline:
        return 100.0
    total = sum(p.availability_percent for p in sli_timeline)
    return total / len(sli_timeline)


def _run_evaluation(
    graph: object,
    model_name: str,
    ops_days: int = 7,
    max_scenarios: int = 0,
) -> dict:
    """Run all simulation engines on a graph and return evaluation data.

    Each engine is wrapped with a feature flag check and exception handler
    so that a single engine failure does not abort the entire evaluation.

    Returns a dict with keys: model, components, dependencies, static,
    dynamic, ops, whatif, capacity, verdict.
    """
    _logger = logging.getLogger(__name__)

    num_components = len(graph.components)
    num_dependencies = len(graph.all_dependency_edges())

    evaluation_data: dict = {
        "model": model_name,
        "components": num_components,
        "dependencies": num_dependencies,
    }

    # Track variables needed for verdict
    static_critical = 0
    static_warning = 0
    dyn_critical = 0
    dyn_warning = 0

    # Raw objects for Rich/HTML rendering
    raw: dict = {"graph": graph}

    # ------------------------------------------------------------------
    # 1. Static Simulation
    # ------------------------------------------------------------------
    if is_enabled("cascade_engine"):
        try:
            from infrasim.simulator.engine import SimulationEngine

            static_engine = SimulationEngine(graph)
            static_report = static_engine.run_all_defaults()

            total_generated = len(static_report.results)
            static_total = len(static_report.results)
            static_critical = len(static_report.critical_findings)
            static_warning = len(static_report.warnings)
            static_passed = len(static_report.passed)

            evaluation_data["static"] = {
                "resilience_score": round(static_report.resilience_score, 1),
                "total_scenarios": static_total,
                "generated_scenarios": total_generated,
                "critical": static_critical,
                "warning": static_warning,
                "passed": static_passed,
            }
            raw["static_report"] = static_report
        except Exception as e:
            _logger.warning("Static simulation engine failed: %s", e)
            evaluation_data["static"] = {"error": str(e)}
    else:
        evaluation_data["static"] = {"disabled": True}

    # Ensure static has defaults for verdict
    if "resilience_score" not in evaluation_data.get("static", {}):
        evaluation_data["static"].setdefault("resilience_score", 0)
        evaluation_data["static"].setdefault("total_scenarios", 0)
        evaluation_data["static"].setdefault("generated_scenarios", 0)
        evaluation_data["static"].setdefault("critical", 0)
        evaluation_data["static"].setdefault("warning", 0)
        evaluation_data["static"].setdefault("passed", 0)

    # ------------------------------------------------------------------
    # 2. Dynamic Simulation
    # ------------------------------------------------------------------
    if is_enabled("dynamic_engine"):
        try:
            from infrasim.simulator.dynamic_engine import DynamicSimulationEngine

            dyn_engine = DynamicSimulationEngine(graph)
            dyn_report = dyn_engine.run_all_dynamic_defaults()

            dyn_results = dyn_report.results
            dyn_total = len(dyn_results)
            dyn_critical = len(dyn_report.critical_findings)
            dyn_warning = len(dyn_report.warnings)
            dyn_passed = len(dyn_report.passed)

            dyn_worst_name = None
            dyn_worst_severity = 0.0
            for r in dyn_results:
                if r.peak_severity > dyn_worst_severity:
                    dyn_worst_severity = r.peak_severity
                    dyn_worst_name = r.scenario.name

            evaluation_data["dynamic"] = {
                "total_scenarios": dyn_total,
                "critical": dyn_critical,
                "warning": dyn_warning,
                "passed": dyn_passed,
                "worst_scenario": dyn_worst_name,
                "worst_severity": dyn_worst_severity,
            }
            raw["dyn_report"] = dyn_report
        except Exception as e:
            _logger.warning("Dynamic engine failed: %s", e)
            evaluation_data["dynamic"] = {"error": str(e)}
    else:
        evaluation_data["dynamic"] = {"disabled": True}

    # Ensure dynamic has defaults for verdict
    if "total_scenarios" not in evaluation_data.get("dynamic", {}):
        evaluation_data["dynamic"].setdefault("total_scenarios", 0)
        evaluation_data["dynamic"].setdefault("critical", 0)
        evaluation_data["dynamic"].setdefault("warning", 0)
        evaluation_data["dynamic"].setdefault("passed", 0)
        evaluation_data["dynamic"].setdefault("worst_scenario", None)
        evaluation_data["dynamic"].setdefault("worst_severity", 0.0)

    # ------------------------------------------------------------------
    # 3. Ops Simulation
    # ------------------------------------------------------------------
    if is_enabled("ops_engine"):
        try:
            from infrasim.model.components import SLOTarget
            from infrasim.simulator.ops_engine import OpsScenario, OpsSimulationEngine
            from infrasim.simulator.traffic import create_diurnal_weekly

            component_ids = list(graph.components.keys())
            deploy_targets: list[str] = []
            for comp_id, comp in graph.components.items():
                if comp.type.value in ("app_server", "web_server"):
                    deploy_targets.append(comp_id)
            if not deploy_targets:
                deploy_targets = component_ids[:2] if len(component_ids) >= 2 else list(component_ids)

            scheduled_deploys = []
            for dow in [1, 3]:  # Tuesday, Thursday
                for comp_id in deploy_targets:
                    scheduled_deploys.append({
                        "component_id": comp_id,
                        "day_of_week": dow,
                        "hour": 14,
                        "downtime_seconds": 30,
                    })

            ops_scenario = OpsScenario(
                id=f"evaluate-ops-{ops_days}d",
                name=f"Full operations ({ops_days}d)",
                duration_days=ops_days,
                traffic_patterns=[
                    create_diurnal_weekly(
                        peak=2.5, duration=ops_days * 86400, weekend_factor=0.6,
                    ),
                ],
                scheduled_deploys=scheduled_deploys,
                enable_random_failures=True,
                enable_degradation=True,
                enable_maintenance=True,
            )

            ops_engine = OpsSimulationEngine(graph)
            ops_result = ops_engine.run_ops_scenario(ops_scenario)

            ops_avg_avail = _compute_avg_availability(ops_result.sli_timeline)
            ops_total_events = len(ops_result.events)

            evaluation_data["ops"] = {
                "duration_days": ops_days,
                "avg_availability": round(ops_avg_avail, 4),
                "min_availability": round(ops_result.min_availability, 2),
                "total_downtime_seconds": round(ops_result.total_downtime_seconds, 1),
                "total_events": ops_total_events,
                "total_deploys": ops_result.total_deploys,
                "total_failures": ops_result.total_failures,
                "total_degradation_events": ops_result.total_degradation_events,
                "peak_utilization": round(ops_result.peak_utilization, 1),
            }
            raw["ops_result"] = ops_result
        except Exception as e:
            _logger.warning("Ops engine failed: %s", e)
            evaluation_data["ops"] = {"error": str(e)}
    else:
        evaluation_data["ops"] = {"disabled": True}

    # Ensure ops has defaults for rendering
    if "avg_availability" not in evaluation_data.get("ops", {}):
        evaluation_data["ops"].setdefault("duration_days", ops_days)
        evaluation_data["ops"].setdefault("avg_availability", 100.0)
        evaluation_data["ops"].setdefault("min_availability", 100.0)
        evaluation_data["ops"].setdefault("total_downtime_seconds", 0.0)
        evaluation_data["ops"].setdefault("total_events", 0)
        evaluation_data["ops"].setdefault("total_deploys", 0)
        evaluation_data["ops"].setdefault("total_failures", 0)
        evaluation_data["ops"].setdefault("total_degradation_events", 0)
        evaluation_data["ops"].setdefault("peak_utilization", 0.0)

    # ------------------------------------------------------------------
    # 4. What-If Analysis
    # ------------------------------------------------------------------
    whatif_results = []
    if is_enabled("whatif_engine"):
        try:
            from infrasim.simulator.whatif_engine import WhatIfEngine

            whatif_engine = WhatIfEngine(graph)
            whatif_results = whatif_engine.run_default_whatifs()

            evaluation_data["whatif"] = {
                "parameters_tested": len(whatif_results),
                "results": {
                    wr.parameter: {
                        "values": wr.values,
                        "slo_pass": wr.slo_pass,
                        "breakpoint": wr.breakpoint_value,
                    }
                    for wr in whatif_results
                },
            }
            raw["whatif_results"] = whatif_results
        except Exception as e:
            _logger.warning("What-If engine failed: %s", e)
            evaluation_data["whatif"] = {"error": str(e)}
    else:
        evaluation_data["whatif"] = {"disabled": True}

    if "parameters_tested" not in evaluation_data.get("whatif", {}):
        evaluation_data["whatif"].setdefault("parameters_tested", 0)
        evaluation_data["whatif"].setdefault("results", {})

    # ------------------------------------------------------------------
    # 5. Capacity Planning
    # ------------------------------------------------------------------
    if is_enabled("capacity_engine"):
        try:
            from infrasim.simulator.capacity_engine import CapacityPlanningEngine

            cap_engine = CapacityPlanningEngine(graph)
            cap_report = cap_engine.forecast(monthly_growth_rate=0.10, slo_target=99.9)

            over_provisioned = [
                f for f in cap_report.forecasts
                if f.recommended_replicas_3m < f.current_replicas
            ]
            bottleneck_count = len(cap_report.bottleneck_components)

            evaluation_data["capacity"] = {
                "over_provisioned_count": len(over_provisioned),
                "cost_reduction_percent": round(cap_report.estimated_monthly_cost_increase, 1),
                "bottleneck_count": bottleneck_count,
                "bottleneck_components": cap_report.bottleneck_components[:5],
                "error_budget_status": cap_report.error_budget.status,
            }
            raw["cap_report"] = cap_report
        except Exception as e:
            _logger.warning("Capacity engine failed: %s", e)
            evaluation_data["capacity"] = {"error": str(e)}
    else:
        evaluation_data["capacity"] = {"disabled": True}

    if "over_provisioned_count" not in evaluation_data.get("capacity", {}):
        evaluation_data["capacity"].setdefault("over_provisioned_count", 0)
        evaluation_data["capacity"].setdefault("cost_reduction_percent", 0.0)
        evaluation_data["capacity"].setdefault("bottleneck_count", 0)
        evaluation_data["capacity"].setdefault("bottleneck_components", [])
        evaluation_data["capacity"].setdefault("error_budget_status", "unknown")

    # ------------------------------------------------------------------
    # 6. 5-Layer Availability Limit Model
    # ------------------------------------------------------------------
    try:
        from infrasim.simulator.availability_model import compute_five_layer_model

        five_layer = compute_five_layer_model(graph)
        evaluation_data["availability_limits"] = {
            "layer1_software": {
                "nines": round(five_layer.layer1_software.nines, 2),
                "availability_percent": round(five_layer.layer1_software.availability * 100, 6),
                "annual_downtime_seconds": round(five_layer.layer1_software.annual_downtime_seconds, 0),
                "description": five_layer.layer1_software.description,
            },
            "layer2_hardware": {
                "nines": round(five_layer.layer2_hardware.nines, 2),
                "availability_percent": round(five_layer.layer2_hardware.availability * 100, 6),
                "annual_downtime_seconds": round(five_layer.layer2_hardware.annual_downtime_seconds, 0),
                "description": five_layer.layer2_hardware.description,
            },
            "layer3_theoretical": {
                "nines": round(five_layer.layer3_theoretical.nines, 2),
                "availability_percent": round(five_layer.layer3_theoretical.availability * 100, 6),
                "annual_downtime_seconds": round(five_layer.layer3_theoretical.annual_downtime_seconds, 0),
                "description": five_layer.layer3_theoretical.description,
            },
            "layer4_operational": {
                "nines": round(five_layer.layer4_operational.nines, 2),
                "availability_percent": round(five_layer.layer4_operational.availability * 100, 6),
                "annual_downtime_seconds": round(five_layer.layer4_operational.annual_downtime_seconds, 0),
                "description": five_layer.layer4_operational.description,
            },
            "layer5_external": {
                "nines": round(five_layer.layer5_external.nines, 2),
                "availability_percent": round(five_layer.layer5_external.availability * 100, 6),
                "annual_downtime_seconds": round(five_layer.layer5_external.annual_downtime_seconds, 0),
                "description": five_layer.layer5_external.description,
            },
        }
        raw["five_layer"] = five_layer
    except Exception as e:
        _logger.warning("5-Layer availability model failed: %s", e)
        evaluation_data["availability_limits"] = {"error": str(e)}

    # ------------------------------------------------------------------
    # Determine overall verdict
    # ------------------------------------------------------------------
    static_critical = evaluation_data.get("static", {}).get("critical", 0)
    static_warning = evaluation_data.get("static", {}).get("warning", 0)
    dyn_critical = evaluation_data.get("dynamic", {}).get("critical", 0)
    dyn_warning = evaluation_data.get("dynamic", {}).get("warning", 0)

    if dyn_critical > 0 or static_critical > 0:
        verdict = "NEEDS ATTENTION"
    elif dyn_warning > 0 or static_warning > 0:
        verdict = "ACCEPTABLE"
    else:
        verdict = "HEALTHY"

    evaluation_data["verdict"] = verdict

    # Attach raw objects for Rich/HTML rendering (not serialised)
    # Use .get() defaults so rendering code works even if an engine failed
    raw.setdefault("static_report", None)
    raw.setdefault("dyn_report", None)
    raw.setdefault("ops_result", None)
    raw.setdefault("whatif_results", whatif_results)
    raw.setdefault("cap_report", None)
    raw.setdefault("five_layer", None)
    evaluation_data["_raw"] = raw

    return evaluation_data


def _verdict_color(verdict: str) -> str:
    """Return a Rich color string for a verdict."""
    if verdict == "NEEDS ATTENTION":
        return "red"
    elif verdict == "ACCEPTABLE":
        return "yellow"
    return "green"


def _print_comparison_table(data_a: dict, data_b: dict) -> None:
    """Print a side-by-side comparison summary of two evaluation results."""
    from rich.table import Table
    from rich.text import Text

    table = Table(
        title="COMPARISON SUMMARY",
        show_header=True,
        header_style="bold",
        title_style="bold cyan",
    )
    table.add_column("Metric", style="cyan", width=24)
    table.add_column(f"Model A ({data_a['model']})", width=22)
    table.add_column(f"Model B ({data_b['model']})", width=22)
    table.add_column("Delta", width=24)

    def _delta_text(val_a: float, val_b: float, fmt: str = ".1f", higher_is_better: bool = True) -> Text:
        """Build a colored delta Text object."""
        diff = val_b - val_a
        if abs(diff) < 1e-9:
            return Text(f"  0", style="dim")
        sign = "+" if diff > 0 else ""
        label = f"{sign}{diff:{fmt}}"
        if higher_is_better:
            color = "green" if diff > 0 else "red"
        else:
            color = "red" if diff > 0 else "green"
        return Text(label, style=color)

    def _delta_text_inverse(val_a: float, val_b: float, fmt: str = ".1f") -> Text:
        """Lower is better (e.g. critical count, downtime)."""
        return _delta_text(val_a, val_b, fmt=fmt, higher_is_better=False)

    # Resilience Score
    rs_a = data_a["static"]["resilience_score"]
    rs_b = data_b["static"]["resilience_score"]
    table.add_row(
        "Resilience Score",
        f"{rs_a:.0f}/100",
        f"{rs_b:.0f}/100",
        _delta_text(rs_a, rs_b, ".0f"),
    )

    # Static Critical
    sc_a = data_a["static"]["critical"]
    sc_b = data_b["static"]["critical"]
    table.add_row(
        "Static Critical",
        str(sc_a),
        str(sc_b),
        _delta_text_inverse(sc_a, sc_b, ".0f"),
    )

    # Static Warning
    sw_a = data_a["static"]["warning"]
    sw_b = data_b["static"]["warning"]
    table.add_row(
        "Static Warning",
        str(sw_a),
        str(sw_b),
        _delta_text_inverse(sw_a, sw_b, ".0f"),
    )

    # Static Passed
    sp_a = data_a["static"]["passed"]
    sp_b = data_b["static"]["passed"]
    table.add_row(
        "Static Passed",
        str(sp_a),
        str(sp_b),
        _delta_text(sp_a, sp_b, ".0f"),
    )

    table.add_section()

    # Dynamic Critical
    dc_a = data_a["dynamic"]["critical"]
    dc_b = data_b["dynamic"]["critical"]
    table.add_row(
        "Dynamic Critical",
        str(dc_a),
        str(dc_b),
        _delta_text_inverse(dc_a, dc_b, ".0f"),
    )

    # Dynamic Warning
    dw_a = data_a["dynamic"]["warning"]
    dw_b = data_b["dynamic"]["warning"]
    table.add_row(
        "Dynamic Warning",
        str(dw_a),
        str(dw_b),
        _delta_text_inverse(dw_a, dw_b, ".0f"),
    )

    # Dynamic Worst Severity
    dsev_a = data_a["dynamic"]["worst_severity"]
    dsev_b = data_b["dynamic"]["worst_severity"]
    table.add_row(
        "Dynamic Worst Severity",
        f"{dsev_a:.1f}",
        f"{dsev_b:.1f}",
        _delta_text_inverse(dsev_a, dsev_b, ".1f"),
    )

    table.add_section()

    # Ops Availability
    oa_a = data_a["ops"]["avg_availability"]
    oa_b = data_b["ops"]["avg_availability"]
    table.add_row(
        "Ops Availability %",
        f"{oa_a:.3f}%",
        f"{oa_b:.3f}%",
        _delta_text(oa_a, oa_b, ".4f"),
    )

    # Ops Downtime
    od_a = data_a["ops"]["total_downtime_seconds"]
    od_b = data_b["ops"]["total_downtime_seconds"]
    table.add_row(
        "Ops Downtime (s)",
        f"{od_a:.1f}",
        f"{od_b:.1f}",
        _delta_text_inverse(od_a, od_b, ".1f"),
    )

    table.add_section()

    # Over-provisioned
    op_a = data_a["capacity"]["over_provisioned_count"]
    op_b = data_b["capacity"]["over_provisioned_count"]
    table.add_row(
        "Over-provisioned",
        str(op_a),
        str(op_b),
        _delta_text_inverse(op_a, op_b, ".0f"),
    )

    # Cost reduction %
    cr_a = data_a["capacity"]["cost_reduction_percent"]
    cr_b = data_b["capacity"]["cost_reduction_percent"]
    table.add_row(
        "Cost Reduction %",
        f"{cr_a:.1f}%",
        f"{cr_b:.1f}%",
        _delta_text_inverse(cr_a, cr_b, ".1f"),
    )

    table.add_section()

    # Verdict
    v_a = data_a["verdict"]
    v_b = data_b["verdict"]
    verdict_delta_style = "dim"
    if v_a != v_b:
        # Rank: HEALTHY > ACCEPTABLE > NEEDS ATTENTION
        rank = {"HEALTHY": 3, "ACCEPTABLE": 2, "NEEDS ATTENTION": 1}
        if rank.get(v_b, 0) > rank.get(v_a, 0):
            verdict_delta_style = "green"
        else:
            verdict_delta_style = "red"
    table.add_row(
        "Verdict",
        Text(v_a, style=_verdict_color(v_a)),
        Text(v_b, style=_verdict_color(v_b)),
        Text(
            "no change" if v_a == v_b else f"{v_a} -> {v_b}",
            style=verdict_delta_style,
        ),
    )

    console.print()
    console.print(table)


def _build_comparison_json(data_a: dict, data_b: dict) -> dict:
    """Build a JSON-serialisable comparison dict from two evaluation dicts."""
    def _safe(d: dict) -> dict:
        """Strip non-serialisable _raw key."""
        return {k: v for k, v in d.items() if k != "_raw"}

    comparison: dict = {}
    # Resilience score delta
    comparison["resilience_score_delta"] = round(
        data_b["static"]["resilience_score"] - data_a["static"]["resilience_score"], 1
    )
    comparison["static_critical_delta"] = (
        data_b["static"]["critical"] - data_a["static"]["critical"]
    )
    comparison["static_warning_delta"] = (
        data_b["static"]["warning"] - data_a["static"]["warning"]
    )
    comparison["static_passed_delta"] = (
        data_b["static"]["passed"] - data_a["static"]["passed"]
    )
    comparison["dynamic_critical_delta"] = (
        data_b["dynamic"]["critical"] - data_a["dynamic"]["critical"]
    )
    comparison["dynamic_warning_delta"] = (
        data_b["dynamic"]["warning"] - data_a["dynamic"]["warning"]
    )
    comparison["dynamic_worst_severity_delta"] = round(
        data_b["dynamic"]["worst_severity"] - data_a["dynamic"]["worst_severity"], 1
    )
    comparison["ops_availability_delta"] = round(
        data_b["ops"]["avg_availability"] - data_a["ops"]["avg_availability"], 4
    )
    comparison["ops_downtime_delta"] = round(
        data_b["ops"]["total_downtime_seconds"] - data_a["ops"]["total_downtime_seconds"], 1
    )
    comparison["over_provisioned_delta"] = (
        data_b["capacity"]["over_provisioned_count"] - data_a["capacity"]["over_provisioned_count"]
    )
    comparison["cost_reduction_delta"] = round(
        data_b["capacity"]["cost_reduction_percent"] - data_a["capacity"]["cost_reduction_percent"], 1
    )
    comparison["verdict_a"] = data_a["verdict"]
    comparison["verdict_b"] = data_b["verdict"]
    comparison["verdict_changed"] = data_a["verdict"] != data_b["verdict"]

    return {
        "model_a": _safe(data_a),
        "model_b": _safe(data_b),
        "comparison": comparison,
    }


@app.command()
def evaluate(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    file: Path = typer.Option(None, "--file", "-f", help="Alias for --model"),
    compare: Path = typer.Option(None, "--compare", "-c", help="Compare with another model"),
    html: Path = typer.Option(None, "--html", help="Export cross-engine HTML report"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
    ops_days: int = typer.Option(7, "--ops-days", help="Ops simulation duration in days"),
    max_scenarios: int = typer.Option(0, "--max-scenarios", help="Max static scenarios (0=default)"),
) -> None:
    """Run all 5 simulation engines and produce a unified evaluation report.

    Examples:
        # Full evaluation with default model
        faultzero evaluate

        # Evaluate a specific model
        faultzero evaluate --model my-model.json

        # Compare two models side by side
        faultzero evaluate --model model-a.json --compare model-b.json

        # Export cross-engine HTML report
        faultzero evaluate --html evaluation.html

        # JSON output for automation
        faultzero evaluate --json

        # Custom ops simulation duration
        faultzero evaluate --ops-days 14

        # Limit static simulation scenarios
        faultzero evaluate --max-scenarios 100
    """
    from rich.panel import Panel

    resolved_model = file if file is not None else model
    graph = _load_graph_for_analysis(resolved_model, yaml_file=None)

    num_components = len(graph.components)
    num_dependencies = len(graph.all_dependency_edges())
    model_name = resolved_model.name

    console.print(
        f"\n[cyan]Starting full evaluation of [bold]{model_name}[/bold] "
        f"({num_components} components, {num_dependencies} dependencies)...[/]\n"
    )

    # Run evaluation on primary model
    console.print("[cyan]  [1/5] Running static simulation...[/]")
    console.print("[cyan]  [2/5] Running dynamic simulation...[/]")
    console.print(f"[cyan]  [3/5] Running ops simulation ({ops_days} days)...[/]")
    console.print("[cyan]  [4/5] Running what-if analysis...[/]")
    console.print("[cyan]  [5/5] Running capacity planning...[/]")

    evaluation_data = _run_evaluation(graph, model_name, ops_days, max_scenarios)

    # Auto-record to history
    _auto_record_history(graph, evaluation_data)

    # ------------------------------------------------------------------
    # Compare mode
    # ------------------------------------------------------------------
    if compare is not None:
        graph_b = _load_graph_for_analysis(compare, yaml_file=None)
        model_name_b = compare.name
        num_comp_b = len(graph_b.components)
        num_dep_b = len(graph_b.all_dependency_edges())

        console.print(
            f"\n[cyan]Starting full evaluation of [bold]{model_name_b}[/bold] "
            f"({num_comp_b} components, {num_dep_b} dependencies)...[/]\n"
        )
        console.print("[cyan]  [1/5] Running static simulation...[/]")
        console.print("[cyan]  [2/5] Running dynamic simulation...[/]")
        console.print(f"[cyan]  [3/5] Running ops simulation ({ops_days} days)...[/]")
        console.print("[cyan]  [4/5] Running what-if analysis...[/]")
        console.print("[cyan]  [5/5] Running capacity planning...[/]")

        evaluation_data_b = _run_evaluation(graph_b, model_name_b, ops_days, max_scenarios)

        # JSON compare output
        if json_output:
            console.print_json(data=_build_comparison_json(evaluation_data, evaluation_data_b))
            return

        # Print individual reports for both models, then comparison table
        _print_rich_report(evaluation_data, ops_days)
        console.print("\n[bold bright_blue]--- Model B ---[/]\n")
        _print_rich_report(evaluation_data_b, ops_days)

        # Comparison table
        _print_comparison_table(evaluation_data, evaluation_data_b)

        # HTML export for compare mode is not yet supported
        if html:
            _export_html_report(
                html, evaluation_data, graph,
                evaluation_data["_raw"]["static_report"],
                evaluation_data["_raw"]["dyn_report"],
                evaluation_data["_raw"]["ops_result"],
                evaluation_data["_raw"]["whatif_results"],
                evaluation_data["_raw"]["cap_report"],
            )
            console.print(f"\n[green]HTML report saved to {html}[/]")
        return

    # ------------------------------------------------------------------
    # Single model mode
    # ------------------------------------------------------------------
    if json_output:
        # Strip _raw before JSON output
        safe_data = {k: v for k, v in evaluation_data.items() if k != "_raw"}
        console.print_json(data=safe_data)
        return

    _print_rich_report(evaluation_data, ops_days)

    # HTML export
    if html:
        _export_html_report(
            html, evaluation_data, graph,
            evaluation_data["_raw"]["static_report"],
            evaluation_data["_raw"]["dyn_report"],
            evaluation_data["_raw"]["ops_result"],
            evaluation_data["_raw"]["whatif_results"],
            evaluation_data["_raw"]["cap_report"],
        )
        console.print(f"\n[green]HTML report saved to {html}[/]")


def _print_rich_report(evaluation_data: dict, ops_days: int) -> None:
    """Print the Rich console output for a single evaluation."""
    from rich.panel import Panel

    model_name = evaluation_data["model"]
    num_components = evaluation_data["components"]
    num_dependencies = evaluation_data["dependencies"]
    static = evaluation_data["static"]
    dynamic = evaluation_data["dynamic"]
    ops = evaluation_data["ops"]
    capacity = evaluation_data["capacity"]
    verdict = evaluation_data["verdict"]
    verdict_color = _verdict_color(verdict)

    raw = evaluation_data["_raw"]
    static_report = raw["static_report"]
    whatif_results = raw["whatif_results"]
    cap_report = raw["cap_report"]
    ops_result = raw["ops_result"]

    static_total = static["total_scenarios"]
    total_generated = static["generated_scenarios"]
    static_critical = static["critical"]
    static_warning = static["warning"]
    static_passed = static["passed"]

    dyn_total = dynamic["total_scenarios"]
    dyn_critical = dynamic["critical"]
    dyn_warning = dynamic["warning"]
    dyn_passed = dynamic["passed"]
    dyn_worst_name = dynamic["worst_scenario"]
    dyn_worst_severity = dynamic["worst_severity"]

    ops_avg_avail = ops["avg_availability"]
    ops_total_events = ops["total_events"]

    over_provisioned_count = capacity["over_provisioned_count"]
    bottleneck_count = capacity["bottleneck_count"]
    cost_val = capacity["cost_reduction_percent"]

    box_width = 60

    # Header
    header_lines = (
        f"  FaultZero Full Evaluation Report\n"
        f"  Model: {model_name}\n"
        f"  Components: {num_components}  |  Dependencies: {num_dependencies}"
    )
    console.print(Panel(
        header_lines,
        style="bold",
        border_style="bright_blue",
        width=box_width,
    ))

    # 1. Static
    console.print(f"\n  [bold]1. Static Simulation[/]")
    console.print(f"     Resilience Score: [bold]{static_report.resilience_score:.0f}/100[/]")
    console.print(
        f"     Scenarios: [bold]{static_total:,}[/] tested"
        f" ({total_generated:,} generated)"
    )
    crit_color = "red" if static_critical > 0 else "dim"
    warn_color = "yellow" if static_warning > 0 else "dim"
    console.print(
        f"     [{crit_color}]Critical: {static_critical}[/]  |  "
        f"[{warn_color}]Warning: {static_warning}[/]  |  "
        f"[green]Passed: {static_passed}[/]"
    )

    # 2. Dynamic
    console.print(f"\n  [bold]2. Dynamic Simulation[/]")
    console.print(f"     Scenarios: [bold]{dyn_total:,}[/] tested")
    crit_color = "red" if dyn_critical > 0 else "dim"
    warn_color = "yellow" if dyn_warning > 0 else "dim"
    console.print(
        f"     [{crit_color}]Critical: {dyn_critical}[/]  |  "
        f"[{warn_color}]Warning: {dyn_warning}[/]  |  "
        f"[green]Passed: {dyn_passed}[/]"
    )
    if dyn_worst_name and dyn_worst_severity >= 4.0:
        sev_color = "red" if dyn_worst_severity >= 7.0 else "yellow"
        console.print(
            f"     [{sev_color}]Worst: {dyn_worst_name} "
            f"(severity: {dyn_worst_severity:.1f})[/]"
        )

    # 3. Ops
    console.print(f"\n  [bold]3. Ops Simulation ({ops_days} days)[/]")
    if ops_avg_avail >= 99.9:
        avail_color = "green"
    elif ops_avg_avail >= 99.0:
        avail_color = "yellow"
    else:
        avail_color = "red"
    console.print(
        f"     Availability: [{avail_color}]{ops_avg_avail:.3f}%[/]  |  "
        f"Downtime: {ops_result.total_downtime_seconds:.1f}s"
    )
    console.print(
        f"     Events: {ops_total_events} total "
        f"({ops_result.total_deploys} deploys, "
        f"{ops_result.total_degradation_events} degradation)"
    )
    console.print(f"     Peak Utilization: {ops_result.peak_utilization:.1f}%")

    # 4. What-If
    console.print(f"\n  [bold]4. What-If Analysis[/]")
    whatif_parts = []
    for wr in whatif_results:
        param_short = wr.parameter.replace("_factor", "").replace("_", " ").title()
        extreme_val = wr.values[-1]
        extreme_pass = wr.slo_pass[-1] if wr.slo_pass else True
        pass_str = "[green]PASS[/]" if extreme_pass else "[red]FAIL[/]"
        whatif_parts.append(f"{param_short} {extreme_val}x: {pass_str}")
    for i in range(0, len(whatif_parts), 3):
        chunk = whatif_parts[i : i + 3]
        console.print(f"     {' | '.join(chunk)}")

    # 5. Capacity
    console.print(f"\n  [bold]5. Capacity Planning[/]")
    if over_provisioned_count:
        console.print(f"     Over-provisioned: {over_provisioned_count} components")
    else:
        console.print(f"     Over-provisioned: 0 components")
    if cost_val < 0:
        console.print(f"     Cost Reduction: [green]{cost_val:.1f}%[/]")
    elif cost_val > 0:
        console.print(f"     Cost Increase: [yellow]+{cost_val:.1f}%[/]")
    else:
        console.print(f"     Cost Change: 0.0%")
    console.print(f"     Bottlenecks: {bottleneck_count} components")

    # 6. 5-Layer Availability Limits
    limits = evaluation_data.get("availability_limits", {})
    if limits:
        console.print(f"\n  [bold]6. 5-Layer Availability Limits[/]")
        for layer_key, label in [
            ("layer1_software", "Layer 1 (Software)"),
            ("layer2_hardware", "Layer 2 (Hardware)"),
            ("layer3_theoretical", "Layer 3 (Theoretical)"),
            ("layer4_operational", "Layer 4 (Operational)"),
            ("layer5_external", "Layer 5 (External SLA)"),
        ]:
            layer = limits.get(layer_key, {})
            if not layer:
                continue
            nines = layer.get("nines", 0)
            avail_pct = layer.get("availability_percent", 0)
            dt = layer.get("annual_downtime_seconds", 0)
            if nines >= 5:
                color = "green"
            elif nines >= 3:
                color = "yellow"
            else:
                color = "red"
            console.print(
                f"     [{color}]{label:25s} {nines:.2f} nines "
                f"({avail_pct:.4f}%) — {dt:.0f}s/year[/]"
            )

    # 7. Resilience Score v2
    graph = raw["graph"]
    score_v2 = graph.resilience_score_v2()
    console.print(f"\n  [bold]7. Resilience Score v2[/]")
    v2_total = score_v2["score"]
    if v2_total >= 80:
        v2_color = "green"
    elif v2_total >= 50:
        v2_color = "yellow"
    else:
        v2_color = "red"
    console.print(f"     Total: [{v2_color}][bold]{v2_total:.0f}/100[/bold][/]")

    breakdown = score_v2.get("breakdown", {})
    category_labels = {
        "redundancy": "Redundancy",
        "circuit_breaker_coverage": "Circuit Breakers",
        "auto_recovery": "Auto Recovery",
        "dependency_risk": "Dependency Risk",
        "capacity_headroom": "Capacity Headroom",
    }
    for key, label in category_labels.items():
        val = breakdown.get(key, 0.0)
        max_val = 20.0
        bar_len = int(val / max_val * 20)
        bar = "\u2588" * bar_len + "\u2591" * (20 - bar_len)
        if val >= 15:
            bar_color = "green"
        elif val >= 10:
            bar_color = "yellow"
        else:
            bar_color = "red"
        console.print(
            f"     [{bar_color}]{label:20s} {bar} {val:.1f}/20[/]"
        )

    v2_recs = score_v2.get("recommendations", [])
    if v2_recs:
        console.print(f"     [bold]Top Recommendations:[/]")
        for rec in v2_recs[:5]:
            console.print(f"       - {rec}")

    # Overall Assessment
    l1_nines = limits.get("layer1_software", {}).get("nines", 0) if limits else 0
    l2_nines = limits.get("layer2_hardware", {}).get("nines", 0) if limits else 0
    l3_nines = limits.get("layer3_theoretical", {}).get("nines", 0) if limits else 0
    assessment_lines = (
        f"  Overall Assessment\n"
        f"  [dim]|[/] Architecture Score: [bold]{static_report.resilience_score:.0f}/100[/] (structural)\n"
        f"  [dim]|[/] Operational Score: [{avail_color}]{ops_avg_avail:.3f}%[/] availability\n"
        f"  [dim]|[/] Availability Ceiling: [bold]{l3_nines:.2f} nines[/] (theoretical)\n"
        f"  [dim]|[/] Practical Ceiling: [bold]{l1_nines:.2f} nines[/] (software limit)\n"
        f"  [dim]|[/] Dynamic Risks: "
        f"[red]{dyn_critical} CRITICAL[/], "
        f"[yellow]{dyn_warning} WARNING[/]\n"
        f"  [dim]|[/] Cost Optimization: {abs(cost_val):.1f}% "
        f"{'reduction' if cost_val < 0 else 'increase' if cost_val > 0 else 'change'} possible\n"
        f"  [dim]|[/] Verdict: [{verdict_color}][bold]{verdict}[/bold][/]"
    )

    console.print()
    console.print(Panel(
        assessment_lines,
        border_style=verdict_color,
        width=box_width,
    ))


def _export_html_report(
    path: Path,
    data: dict,
    graph: object,
    static_report: object,
    dyn_report: object,
    ops_result: object,
    whatif_results: list,
    cap_report: object,
) -> None:
    """Generate a cross-engine HTML evaluation report."""
    verdict = data.get("verdict", "UNKNOWN")
    verdict_color = "#e74c3c" if verdict == "NEEDS ATTENTION" else (
        "#f39c12" if verdict == "ACCEPTABLE" else "#2ecc71"
    )

    static = data.get("static", {})
    dynamic = data.get("dynamic", {})
    ops = data.get("ops", {})
    capacity = data.get("capacity", {})

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FaultZero Full Evaluation Report - {data.get('model', '')}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       margin: 2em auto; max-width: 900px; color: #333; }}
h1 {{ border-bottom: 3px solid #3498db; padding-bottom: 0.3em; }}
h2 {{ color: #2c3e50; margin-top: 1.5em; }}
.verdict {{ background: {verdict_color}; color: #fff; padding: 0.5em 1em;
            border-radius: 4px; display: inline-block; font-size: 1.2em;
            font-weight: bold; }}
.metric {{ display: inline-block; margin: 0.3em 1em 0.3em 0;
           padding: 0.4em 0.8em; background: #f8f9fa; border-radius: 4px;
           border-left: 3px solid #3498db; }}
.critical {{ border-left-color: #e74c3c; }}
.warning {{ border-left-color: #f39c12; }}
.pass {{ border-left-color: #2ecc71; }}
table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
th, td {{ border: 1px solid #ddd; padding: 0.5em; text-align: left; }}
th {{ background: #f8f9fa; }}
</style>
</head>
<body>
<h1>FaultZero Full Evaluation Report</h1>
<p>Model: <strong>{data.get('model', '')}</strong> |
   Components: {data.get('components', 0)} |
   Dependencies: {data.get('dependencies', 0)}</p>
<p class="verdict">{verdict}</p>

<h2>1. Static Simulation</h2>
<div class="metric">Resilience Score: <strong>{static.get('resilience_score', 0)}/100</strong></div>
<div class="metric">Scenarios: {static.get('total_scenarios', 0)} tested</div>
<div class="metric critical">Critical: {static.get('critical', 0)}</div>
<div class="metric warning">Warning: {static.get('warning', 0)}</div>
<div class="metric pass">Passed: {static.get('passed', 0)}</div>

<h2>2. Dynamic Simulation</h2>
<div class="metric">Scenarios: {dynamic.get('total_scenarios', 0)} tested</div>
<div class="metric critical">Critical: {dynamic.get('critical', 0)}</div>
<div class="metric warning">Warning: {dynamic.get('warning', 0)}</div>
<div class="metric pass">Passed: {dynamic.get('passed', 0)}</div>
{'<p>Worst: ' + str(dynamic.get('worst_scenario', '')) + ' (severity: ' + str(dynamic.get('worst_severity', 0)) + ')</p>' if dynamic.get('worst_severity', 0) >= 4.0 else ''}

<h2>3. Ops Simulation ({ops.get('duration_days', 7)} days)</h2>
<div class="metric">Availability: {ops.get('avg_availability', 100.0):.3f}%</div>
<div class="metric">Downtime: {ops.get('total_downtime_seconds', 0):.1f}s</div>
<div class="metric">Events: {ops.get('total_events', 0)}</div>
<div class="metric">Peak Utilization: {ops.get('peak_utilization', 0):.1f}%</div>

<h2>4. What-If Analysis</h2>
<table>
<tr><th>Parameter</th><th>Values</th><th>SLO Pass</th><th>Breakpoint</th></tr>
"""

    whatif_data = data.get("whatif", {}).get("results", {})
    for param, info in whatif_data.items():
        values_str = ", ".join(str(v) for v in info.get("values", []))
        pass_str = ", ".join("PASS" if p else "FAIL" for p in info.get("slo_pass", []))
        bp = info.get("breakpoint")
        bp_str = str(bp) if bp is not None else "None"
        html_content += f"<tr><td>{param}</td><td>{values_str}</td><td>{pass_str}</td><td>{bp_str}</td></tr>\n"

    html_content += f"""</table>

<h2>5. Capacity Planning</h2>
<div class="metric">Over-provisioned: {capacity.get('over_provisioned_count', 0)} components</div>
<div class="metric">Cost Change: {capacity.get('cost_reduction_percent', 0):.1f}%</div>
<div class="metric">Bottlenecks: {capacity.get('bottleneck_count', 0)} components</div>

<h2>Overall Assessment</h2>
<ul>
<li>Architecture Score: {static.get('resilience_score', 0)}/100 (structural)</li>
<li>Operational Score: {ops.get('avg_availability', 100.0):.3f}% availability</li>
<li>Dynamic Risks: {dynamic.get('critical', 0)} CRITICAL, {dynamic.get('warning', 0)} WARNING</li>
<li>Cost Optimization: {abs(capacity.get('cost_reduction_percent', 0)):.1f}% possible</li>
<li>Verdict: <strong>{verdict}</strong></li>
</ul>

<hr>
<p><em>Generated by FaultZero evaluate</em></p>
</body>
</html>"""

    path.write_text(html_content, encoding="utf-8")


def _auto_record_history(graph: object, evaluation_data: dict) -> None:
    """Auto-record evaluation results to history tracker (best-effort)."""
    try:
        from infrasim.history import HistoryTracker

        raw = evaluation_data.get("_raw", {})
        static_report = raw.get("static_report")
        tracker = HistoryTracker()
        tracker.record(graph, report=static_report)
    except Exception:
        pass  # History recording is best-effort, never breaks the CLI
