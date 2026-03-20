# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Simulation-related API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from faultray.api.routes._shared import (
    _report_to_dict,
    _save_run,
    get_graph,
    get_last_report,
    set_last_report,
    templates,
)
from faultray.api.server import _require_permission
from faultray.simulator.engine import SimulationEngine

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Simulation page (HTML)
# ---------------------------------------------------------------------------

@router.get("/simulation", response_class=HTMLResponse)
async def simulation_page(request: Request):
    report_data = None
    _last_report = get_last_report()
    if _last_report is not None:
        report_data = _report_to_dict(_last_report)

    return templates.TemplateResponse("simulation.html", {
        "request": request,
        "report": report_data,
        "has_data": len(get_graph().components) > 0,
    })


@router.get("/simulation/run")
async def simulation_run_get():
    """Run simulation and return JSON results (GET endpoint)."""
    graph = get_graph()
    if not graph.components:
        return JSONResponse({"error": "No infrastructure loaded. Visit /demo first."}, status_code=400)

    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()
    set_last_report(report)
    report_dict = _report_to_dict(report)

    # Persist to database
    run_id = await _save_run(report_dict, engine_type="static")
    if run_id is not None:
        report_dict["run_id"] = run_id

    return JSONResponse(report_dict)


@router.post("/api/simulate", response_class=JSONResponse)
async def api_simulate(request: Request, user=Depends(_require_permission("run_simulation"))):
    """Run simulation and return JSON results (POST endpoint)."""
    graph = get_graph()
    if not graph.components:
        return JSONResponse({"error": "No infrastructure loaded. Visit /demo first."}, status_code=400)

    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()
    set_last_report(report)
    report_dict = _report_to_dict(report)

    # Persist to database
    run_id = await _save_run(report_dict, engine_type="static")
    if run_id is not None:
        report_dict["run_id"] = run_id

    # Audit log
    try:
        from faultray.api.database import get_session_factory, log_audit

        sf = get_session_factory()
        async with sf() as session:
            await log_audit(
                session,
                user_id=user.id if user else None,
                action="simulate",
                resource_type="simulation_run",
                resource_id=str(run_id) if run_id else None,
                details={"resilience_score": report_dict.get("resilience_score")},
                ip=request.client.host if request.client else None,
            )
            await session.commit()
    except Exception:
        logger.debug("Could not write audit log for simulate.", exc_info=True)

    return JSONResponse(report_dict)


@router.post("/api/simulate-failure/{component_id}", response_class=JSONResponse)
async def simulate_failure(
    component_id: str,
    user=Depends(_require_permission("run_simulation")),
):
    """Simulate a component failure and return cascade effects with wave-by-wave breakdown."""
    from faultray.simulator.cascade import CascadeEngine
    from faultray.simulator.scenarios import Fault, FaultType

    graph = get_graph()
    if not graph.components:
        raise HTTPException(status_code=400, detail="No infrastructure loaded. Visit /demo first.")

    comp = graph.get_component(component_id)
    if comp is None:
        raise HTTPException(status_code=404, detail=f"Component '{component_id}' not found.")

    # Run cascade simulation
    cascade_engine = CascadeEngine(graph)
    fault = Fault(
        target_component_id=component_id,
        fault_type=FaultType.COMPONENT_DOWN,
    )
    chain = cascade_engine.simulate_fault(fault)

    # Organise effects into waves based on estimated_time_seconds
    waves: list[dict] = []
    if chain.effects:
        wave0_comps = []
        remaining = []
        for effect in chain.effects:
            if effect.component_id == component_id:
                wave0_comps.append({
                    "id": effect.component_id,
                    "health": effect.health.value,
                    "reason": effect.reason,
                })
            else:
                remaining.append(effect)

        if wave0_comps:
            waves.append({"wave": 0, "components": wave0_comps})

        remaining.sort(key=lambda e: e.estimated_time_seconds)

        current_wave = 1
        current_bucket: list[dict] = []
        prev_time = 0
        for effect in remaining:
            if effect.estimated_time_seconds > prev_time and current_bucket:
                waves.append({"wave": current_wave, "components": current_bucket})
                current_wave += 1
                current_bucket = []
            current_bucket.append({
                "id": effect.component_id,
                "health": effect.health.value,
                "reason": effect.reason,
            })
            prev_time = effect.estimated_time_seconds

        if current_bucket:
            waves.append({"wave": current_wave, "components": current_bucket})

    total_affected = len(chain.effects)
    total_components = len(graph.components)
    blast_radius_score = total_affected / total_components if total_components > 0 else 0

    severity = chain.severity
    if severity > 7:
        recovery_est = "30-60 minutes"
    elif severity > 4:
        recovery_est = "15-30 minutes"
    elif severity > 2:
        recovery_est = "5-15 minutes"
    else:
        recovery_est = "< 5 minutes"

    return JSONResponse({
        "root_cause": component_id,
        "total_affected": total_affected,
        "risk_score": round(severity, 1),
        "waves": waves,
        "blast_radius_score": round(blast_radius_score, 2),
        "recovery_time_estimate": recovery_est,
    })


# ---------------------------------------------------------------------------
# Incident Replay
# ---------------------------------------------------------------------------

@router.get("/api/incidents", response_class=JSONResponse)
async def list_incidents(
    provider: str | None = None,
    user=Depends(_require_permission("view_results")),
):
    """List available historical incidents for replay."""
    from faultray.simulator.incident_replay import IncidentReplayEngine

    engine = IncidentReplayEngine()
    incidents = engine.list_incidents(provider=provider)
    return JSONResponse({
        "incidents": [
            {
                "id": inc.id,
                "name": inc.name,
                "provider": inc.provider,
                "date": inc.date.isoformat(),
                "duration_hours": round(inc.duration.total_seconds() / 3600, 1),
                "severity": inc.severity,
                "affected_services": inc.affected_services,
                "affected_regions": inc.affected_regions,
                "root_cause": inc.root_cause,
                "lessons_learned": inc.lessons_learned,
                "post_mortem_url": inc.post_mortem_url,
                "tags": inc.tags,
            }
            for inc in incidents
        ],
        "count": len(incidents),
    })


@router.post("/api/replay/{incident_id}", response_class=JSONResponse)
async def replay_incident(
    incident_id: str,
    user=Depends(_require_permission("run_simulation")),
):
    """Replay a historical incident against current infrastructure."""
    from faultray.simulator.incident_replay import IncidentReplayEngine

    graph = get_graph()
    if not graph.components:
        raise HTTPException(
            status_code=400,
            detail="No infrastructure loaded. Visit /demo first or load a model.",
        )

    engine = IncidentReplayEngine()
    try:
        incident = engine.get_incident(incident_id)
    except KeyError:
        available = sorted(engine._incidents.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Unknown incident ID '{incident_id}'. Available: {available}",
        )

    result = engine.replay(graph, incident)

    return JSONResponse({
        "incident_id": result.incident.id,
        "incident_name": result.incident.name,
        "survived": result.survived,
        "impact_score": result.impact_score,
        "resilience_grade": result.resilience_grade_during_incident,
        "downtime_estimate_minutes": round(result.downtime_estimate.total_seconds() / 60, 1),
        "revenue_impact_estimate": result.revenue_impact_estimate,
        "affected_components": [
            {
                "id": ac.component_id,
                "name": ac.component_name,
                "impact_type": ac.impact_type,
                "health": ac.health_during_incident.value,
                "recovery_time_minutes": (
                    round(ac.recovery_time.total_seconds() / 60, 1)
                    if ac.recovery_time else None
                ),
                "reason": ac.reason,
            }
            for ac in result.affected_components
        ],
        "survival_factors": result.survival_factors,
        "vulnerability_factors": result.vulnerability_factors,
        "recommendations": result.recommendations,
    })


# ---------------------------------------------------------------------------
# What-If Analysis
# ---------------------------------------------------------------------------

@router.get("/whatif", response_class=HTMLResponse)
async def whatif_page(request: Request):
    """Interactive what-if analysis page."""
    graph = get_graph()
    return templates.TemplateResponse("whatif.html", {
        "request": request,
        "has_data": len(graph.components) > 0,
        "active_page": "whatif",
    })


@router.get("/api/whatif/components")
async def whatif_components():
    """Return current components with their parameters for the what-if UI."""
    from faultray.api.routes._shared import _estimate_availability

    graph = get_graph()
    if not graph.components:
        return JSONResponse({"components": {}, "baseline_score": 0, "spof_count": 0})

    components = {}
    for comp_id, comp in graph.components.items():
        has_cb = False
        for edge in graph.all_dependency_edges():
            if edge.target_id == comp_id and edge.circuit_breaker.enabled:
                has_cb = True
                break

        components[comp_id] = {
            "name": comp.name,
            "type": comp.type.value,
            "replicas": comp.replicas,
            "circuit_breaker": has_cb,
            "autoscaling": comp.autoscaling.enabled,
            "failover": comp.failover.enabled,
            "health_check": comp.failover.health_check_interval_seconds > 0,
        }

    score = graph.resilience_score()

    spof_count = 0
    for comp in graph.components.values():
        dependents = graph.get_dependents(comp.id)
        if comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled:
            spof_count += 1

    avail = _estimate_availability(score)

    v2 = graph.resilience_score_v2()
    recs = v2.get("recommendations", [])[:5]

    return JSONResponse({
        "components": components,
        "baseline_score": round(score, 1),
        "spof_count": spof_count,
        "availability_estimate": avail,
        "recommendations": recs,
    })


@router.post("/api/whatif/calculate")
async def whatif_calculate(request: Request):
    """Calculate resilience for modified parameters."""
    import copy

    from faultray.api.routes._shared import _estimate_availability

    graph = get_graph()
    if not graph.components:
        return JSONResponse({"error": "No infrastructure loaded"}, status_code=400)

    body = await request.json()
    modifications = body.get("modifications", {})

    baseline_score = graph.resilience_score()

    modified_graph = copy.deepcopy(graph)

    for comp_id, mods in modifications.items():
        comp = modified_graph.get_component(comp_id)
        if not comp:
            continue

        if "replicas" in mods:
            comp.replicas = max(1, int(mods["replicas"]))
        if "autoscaling" in mods:
            comp.autoscaling.enabled = bool(mods["autoscaling"])
            if comp.autoscaling.enabled and comp.autoscaling.max_replicas <= comp.replicas:
                comp.autoscaling.max_replicas = comp.replicas * 2
        if "failover" in mods:
            comp.failover.enabled = bool(mods["failover"])
        if "health_check" in mods:
            if bool(mods["health_check"]):
                comp.failover.health_check_interval_seconds = 10.0
            else:
                comp.failover.health_check_interval_seconds = 0.0
        if "circuit_breaker" in mods:
            for u, v, data in modified_graph._graph.edges(data=True):
                dep = data.get("dependency")
                if dep and dep.target_id == comp_id:
                    dep.circuit_breaker.enabled = bool(mods["circuit_breaker"])

    new_score = modified_graph.resilience_score()
    delta = round(new_score - baseline_score, 1)

    spof_count = 0
    for comp in modified_graph.components.values():
        dependents = modified_graph.get_dependents(comp.id)
        if comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled:
            spof_count += 1

    avail = _estimate_availability(new_score)

    v2 = modified_graph.resilience_score_v2()
    recs = v2.get("recommendations", [])[:5]

    return JSONResponse({
        "resilience_score": round(new_score, 1),
        "delta": delta,
        "spof_count": spof_count,
        "availability_estimate": avail,
        "recommendations": recs,
    })


@router.post("/api/whatif/export")
async def whatif_export(request: Request):
    """Export modified infrastructure as YAML."""
    import copy

    import yaml

    graph = get_graph()
    if not graph.components:
        return JSONResponse({"error": "No infrastructure loaded"}, status_code=400)

    body = await request.json()
    modifications = body.get("modifications", {})

    modified_graph = copy.deepcopy(graph)

    for comp_id, mods in modifications.items():
        comp = modified_graph.get_component(comp_id)
        if not comp:
            continue

        if "replicas" in mods:
            comp.replicas = max(1, int(mods["replicas"]))
        if "autoscaling" in mods:
            comp.autoscaling.enabled = bool(mods["autoscaling"])
        if "failover" in mods:
            comp.failover.enabled = bool(mods["failover"])
        if "circuit_breaker" in mods:
            for u, v, data in modified_graph._graph.edges(data=True):
                dep = data.get("dependency")
                if dep and dep.target_id == comp_id:
                    dep.circuit_breaker.enabled = bool(mods["circuit_breaker"])

    from fastapi.responses import Response

    export_dict = modified_graph.to_dict()
    yaml_content = yaml.dump(export_dict, default_flow_style=False, allow_unicode=True)

    return Response(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={"Content-Disposition": "attachment; filename=whatif-modified.yaml"},
    )


# ---------------------------------------------------------------------------
# Chaos Monkey
# ---------------------------------------------------------------------------

@router.get("/chaos-monkey", response_class=HTMLResponse)
async def chaos_monkey_page(request: Request):
    """Chaos Monkey dashboard."""
    graph = get_graph()
    return templates.TemplateResponse("chaos_monkey.html", {
        "request": request,
        "has_data": bool(graph.components),
        "active_page": "chaos_monkey",
    })


@router.post("/api/chaos-monkey", response_class=JSONResponse)
async def api_chaos_monkey(request: Request):
    """Run a Chaos Monkey experiment and return results."""
    from faultray.simulator.chaos_monkey import ChaosLevel, ChaosMonkey, ChaosMonkeyConfig

    graph = get_graph()

    try:
        form = await request.form()
        level_str = form.get("level", "monkey")
        rounds = int(form.get("rounds", "10"))
        seed_str = form.get("seed")
        exclude_str = form.get("exclude", "")
    except Exception:
        level_str = request.query_params.get("level", "monkey")
        rounds = int(request.query_params.get("rounds", "10"))
        seed_str = request.query_params.get("seed")
        exclude_str = request.query_params.get("exclude", "")

    try:
        chaos_level = ChaosLevel(level_str)
    except ValueError:
        chaos_level = ChaosLevel.MONKEY

    seed = int(seed_str) if seed_str else None
    exclude_list = [x.strip() for x in exclude_str.split(",") if x.strip()] if exclude_str else []

    config = ChaosMonkeyConfig(
        level=chaos_level,
        rounds=min(rounds, 100),
        seed=seed,
        exclude_components=exclude_list,
    )

    monkey = ChaosMonkey()
    report = monkey.run(graph, config)

    return JSONResponse({
        "total_rounds": report.total_rounds,
        "survival_rate": report.survival_rate,
        "avg_cascade_depth": report.avg_cascade_depth,
        "avg_affected": report.avg_affected,
        "most_dangerous_component": report.most_dangerous_component,
        "safest_component": report.safest_component,
        "mean_time_to_impact": report.mean_time_to_impact,
        "resilience_score_range": list(report.resilience_score_range),
        "recommendations": report.recommendations,
        "experiments": [
            {
                "round": e.round_number,
                "failed_components": e.failed_components,
                "level": e.level.value,
                "survived": e.survived,
                "cascade_depth": e.cascade_depth,
                "affected_count": e.affected_count,
                "resilience_during": e.resilience_during,
                "recovery_possible": e.recovery_possible,
            }
            for e in report.experiments
        ],
        "worst_experiment": {
            "round": report.worst_experiment.round_number,
            "failed_components": report.worst_experiment.failed_components,
            "affected_count": report.worst_experiment.affected_count,
        } if report.worst_experiment else None,
        "best_experiment": {
            "round": report.best_experiment.round_number,
            "failed_components": report.best_experiment.failed_components,
            "affected_count": report.best_experiment.affected_count,
        } if report.best_experiment else None,
    })


# ---------------------------------------------------------------------------
# FMEA Analysis
# ---------------------------------------------------------------------------

@router.get("/fmea", response_class=HTMLResponse)
async def fmea_page(request: Request):
    """FMEA dashboard."""
    graph = get_graph()
    return templates.TemplateResponse("fmea.html", {
        "request": request,
        "has_data": bool(graph.components),
        "active_page": "fmea",
    })


@router.get("/api/fmea", response_class=JSONResponse)
async def api_fmea(
    component: str | None = None,
    min_rpn: int = 0,
):
    """Run FMEA analysis and return results as JSON."""
    from faultray.simulator.fmea_engine import FMEAEngine

    graph = get_graph()
    engine = FMEAEngine()

    if component:
        modes = engine.analyze_component(graph, component)
        report = engine._build_report(modes)
    else:
        report = engine.analyze(graph)

    failure_modes = report.failure_modes
    if min_rpn > 0:
        failure_modes = [fm for fm in failure_modes if fm.rpn >= min_rpn]

    return JSONResponse({
        "total_rpn": report.total_rpn,
        "average_rpn": report.average_rpn,
        "high_risk_count": report.high_risk_count,
        "medium_risk_count": report.medium_risk_count,
        "low_risk_count": report.low_risk_count,
        "failure_modes": [
            {
                "id": fm.id,
                "component_id": fm.component_id,
                "component_name": fm.component_name,
                "mode": fm.mode,
                "cause": fm.cause,
                "effect_local": fm.effect_local,
                "effect_system": fm.effect_system,
                "severity": fm.severity,
                "occurrence": fm.occurrence,
                "detection": fm.detection,
                "rpn": fm.rpn,
                "current_controls": fm.current_controls,
                "recommended_actions": fm.recommended_actions,
                "responsible": fm.responsible,
            }
            for fm in failure_modes
        ],
        "rpn_by_component": report.rpn_by_component,
        "rpn_by_failure_mode": report.rpn_by_failure_mode,
        "improvement_priority": [
            {"component": c, "action": a, "rpn": r}
            for c, a, r in report.improvement_priority
        ],
    })


# ---------------------------------------------------------------------------
# Anomaly Detection
# ---------------------------------------------------------------------------

@router.get("/anomaly", response_class=HTMLResponse)
async def anomaly_page(request: Request):
    """Anomaly Detection page."""
    graph = get_graph()
    return templates.TemplateResponse("anomaly.html", {
        "request": request,
        "has_data": bool(graph and graph.components),
        "active_page": "anomaly",
    })


@router.get("/api/anomalies", response_class=JSONResponse)
async def api_anomalies(
    request: Request,
    anomaly_type: str | None = None,
    severity: str | None = None,
):
    """Run anomaly detection and return results."""
    graph = get_graph()
    if not graph or not graph.components:
        return JSONResponse({
            "total_components_analyzed": 0,
            "anomaly_rate": 0.0,
            "critical_count": 0,
            "warning_count": 0,
            "healthiest_components": [],
            "most_anomalous_components": [],
            "anomalies": [],
        })

    from faultray.simulator.anomaly_detector import AnomalyDetector, AnomalyType

    detector = AnomalyDetector()
    report = detector.detect(graph)

    anomalies = report.anomalies

    if anomaly_type:
        try:
            target_type = AnomalyType(anomaly_type)
            anomalies = [a for a in anomalies if a.anomaly_type == target_type]
        except ValueError:
            pass

    if severity:
        anomalies = [a for a in anomalies if a.severity == severity]

    return JSONResponse({
        "total_components_analyzed": report.total_components_analyzed,
        "anomaly_rate": report.anomaly_rate,
        "critical_count": report.critical_count,
        "warning_count": report.warning_count,
        "healthiest_components": report.healthiest_components,
        "most_anomalous_components": report.most_anomalous_components,
        "anomalies": [
            {
                "type": a.anomaly_type.value,
                "component_id": a.component_id,
                "component_name": a.component_name,
                "severity": a.severity,
                "description": a.description,
                "expected_value": a.expected_value,
                "actual_value": a.actual_value,
                "z_score": a.z_score,
                "recommendation": a.recommendation,
                "confidence": a.confidence,
            }
            for a in anomalies
        ],
    })


# ---------------------------------------------------------------------------
# Pareto Optimizer
# ---------------------------------------------------------------------------

@router.get("/optimizer", response_class=HTMLResponse)
async def optimizer_page(request: Request):
    """Pareto Optimizer page."""
    graph = get_graph()
    return templates.TemplateResponse("optimizer.html", {
        "request": request,
        "has_data": bool(graph and graph.components),
        "active_page": "optimizer",
    })


@router.get("/api/optimize", response_class=JSONResponse)
async def api_optimize(
    request: Request,
    budget: float | None = None,
    target_score: float | None = None,
):
    """Run Pareto optimization and return frontier data."""
    graph = get_graph()
    if not graph or not graph.components:
        return JSONResponse({"solutions": [], "current": {}, "cost_to_next_nine": 0})

    from faultray.simulator.pareto_optimizer import ParetoOptimizer

    optimizer = ParetoOptimizer()

    if budget is not None:
        solution = optimizer.find_best_for_budget(graph, budget)
        return JSONResponse({
            "solutions": [{
                "resilience_score": solution.resilience_score,
                "estimated_monthly_cost": solution.estimated_monthly_cost,
                "availability_nines": solution.availability_nines,
                "spof_count": solution.spof_count,
                "is_current": solution.is_current,
                "improvements": solution.improvements_from_current,
                "variables": solution.variables,
            }],
            "current": {},
            "cost_to_next_nine": 0,
        })

    if target_score is not None:
        solution = optimizer.find_cheapest_for_score(graph, target_score)
        return JSONResponse({
            "solutions": [{
                "resilience_score": solution.resilience_score,
                "estimated_monthly_cost": solution.estimated_monthly_cost,
                "availability_nines": solution.availability_nines,
                "spof_count": solution.spof_count,
                "is_current": solution.is_current,
                "improvements": solution.improvements_from_current,
                "variables": solution.variables,
            }],
            "current": {},
            "cost_to_next_nine": 0,
        })

    frontier = optimizer.generate_frontier(graph)
    return JSONResponse({
        "solutions": [
            {
                "resilience_score": s.resilience_score,
                "estimated_monthly_cost": s.estimated_monthly_cost,
                "availability_nines": s.availability_nines,
                "spof_count": s.spof_count,
                "is_current": s.is_current,
                "improvements": s.improvements_from_current,
                "variables": s.variables,
            }
            for s in frontier.solutions
        ],
        "current": {
            "resilience_score": frontier.current_solution.resilience_score,
            "estimated_monthly_cost": frontier.current_solution.estimated_monthly_cost,
            "availability_nines": frontier.current_solution.availability_nines,
        },
        "cost_to_next_nine": frontier.cost_to_next_nine,
    })


# ---------------------------------------------------------------------------
# AI Analyze
# ---------------------------------------------------------------------------

@router.get("/analyze", response_class=HTMLResponse)
async def analyze_page(request: Request):
    """Run AI analysis and render the analyze page."""
    graph = get_graph()
    has_data = len(graph.components) > 0

    analysis_data = None
    if has_data:
        _last_report = get_last_report()
        if _last_report is None:
            engine = SimulationEngine(graph)
            _last_report = engine.run_all_defaults()
            set_last_report(_last_report)

        from faultray.ai.analyzer import FaultRayAnalyzer
        import dataclasses

        analyzer = FaultRayAnalyzer()
        ai_report = analyzer.analyze(graph, _last_report)
        analysis_data = dataclasses.asdict(ai_report)

    return templates.TemplateResponse("analyze.html", {
        "request": request,
        "has_data": has_data,
        "analysis": analysis_data,
    })


@router.get("/api/analyze", response_class=JSONResponse)
async def api_analyze(user=Depends(_require_permission("view_results"))):
    """Run AI analysis and return JSON results."""
    graph = get_graph()
    if not graph.components:
        return JSONResponse(
            {"error": "No infrastructure loaded. Visit /demo first."},
            status_code=400,
        )

    _last_report = get_last_report()
    if _last_report is None:
        engine = SimulationEngine(graph)
        _last_report = engine.run_all_defaults()
        set_last_report(_last_report)

    from faultray.ai.analyzer import FaultRayAnalyzer
    import dataclasses

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, _last_report)
    report_dict = dataclasses.asdict(ai_report)

    return JSONResponse(report_dict)


@router.get("/api/architecture-advice", response_class=JSONResponse)
async def get_architecture_advice(
    target_nines: float = 4.0,
    user=Depends(_require_permission("view_results")),
):
    """Get AI architecture recommendations."""
    graph = get_graph()
    if not graph.components:
        return JSONResponse(
            {"error": "No infrastructure loaded. Visit /demo first."},
            status_code=400,
        )

    import dataclasses

    from faultray.ai.architecture_advisor import ArchitectureAdvisor

    advisor = ArchitectureAdvisor()
    report = advisor.advise(graph, target_nines=target_nines)
    report_dict = dataclasses.asdict(report)

    return JSONResponse(report_dict)


@router.get("/advisor", response_class=HTMLResponse)
async def advisor_page(request: Request, target_nines: float = 4.0):
    """Architecture Advisor page."""
    graph = get_graph()
    has_data = len(graph.components) > 0

    advisor_data = None
    if has_data:
        import dataclasses

        from faultray.ai.architecture_advisor import ArchitectureAdvisor

        advisor = ArchitectureAdvisor()
        report = advisor.advise(graph, target_nines=target_nines)
        advisor_data = dataclasses.asdict(report)

    return templates.TemplateResponse("advisor.html", {
        "request": request,
        "has_data": has_data,
        "report": advisor_data,
        "target_nines": target_nines,
    })
