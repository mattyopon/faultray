# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Graph management, topology, and analysis endpoints."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from faultray.api.routes._shared import (
    get_graph,
    templates,
)
from faultray.api.routes._shared import _require_permission

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Graph data
# ---------------------------------------------------------------------------

@router.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    return templates.TemplateResponse(request, "graph.html", {
        "has_data": len(get_graph().components) > 0,
    })


@router.get("/api/graph-data", response_class=JSONResponse)
async def api_graph_data():
    """Return graph data as nodes + edges for D3.js."""
    graph = get_graph()
    data = graph.to_dict()

    nodes = []
    for comp_data in data["components"]:
        comp = graph.get_component(comp_data["id"])
        dependents = graph.get_dependents(comp_data["id"])
        nodes.append({
            "id": comp_data["id"],
            "name": comp_data["name"],
            "type": comp_data["type"],
            "host": comp_data["host"],
            "port": comp_data["port"],
            "replicas": comp_data["replicas"],
            "health": comp_data["health"],
            "utilization": round(comp.utilization(), 1) if comp else 0,
            "dependents_count": len(dependents),
            "cpu_percent": comp_data.get("metrics", {}).get("cpu_percent", 0),
            "memory_percent": comp_data.get("metrics", {}).get("memory_percent", 0),
        })

    edges = []
    for dep_data in data["dependencies"]:
        edges.append({
            "source": dep_data["source_id"],
            "target": dep_data["target_id"],
            "dependency_type": dep_data["dependency_type"],
            "weight": dep_data["weight"],
        })

    return JSONResponse({"nodes": nodes, "edges": edges})


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------

@router.get("/api/topology", response_class=JSONResponse)
async def get_topology():
    """Return infrastructure topology as nodes/edges for D3.js blast radius visualizer."""
    graph = get_graph()
    if not graph.components:
        return JSONResponse({
            "nodes": [],
            "edges": [],
            "metadata": {"total_components": 0, "total_edges": 0, "resilience_score": 0},
        })

    nodes = []
    for comp in graph.components.values():
        dependents = graph.get_dependents(comp.id)
        dependencies = graph.get_dependencies(comp.id)
        is_spof = comp.replicas <= 1 and len(dependents) > 0
        util = comp.utilization()
        if is_spof and util > 70:
            risk_level = "critical"
        elif is_spof or util > 80:
            risk_level = "high"
        elif util > 60:
            risk_level = "medium"
        else:
            risk_level = "low"

        nodes.append({
            "id": comp.id,
            "name": comp.name,
            "type": comp.type.value,
            "replicas": comp.replicas,
            "utilization": round(util, 1),
            "health": comp.health.value,
            "dependents_count": len(dependents),
            "dependencies_count": len(dependencies),
            "is_spof": is_spof,
            "risk_level": risk_level,
        })

    edges = []
    for dep in graph.all_dependency_edges():
        edges.append({
            "source": dep.source_id,
            "target": dep.target_id,
            "type": dep.dependency_type,
            "dependency_type": dep.dependency_type,
            "weight": dep.weight,
            "critical": dep.weight >= 0.8,
        })

    summary = graph.summary()
    return JSONResponse({
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "total_components": summary["total_components"],
            "total_edges": summary["total_dependencies"],
            "resilience_score": summary["resilience_score"],
        },
    })


@router.get("/blast-radius", response_class=HTMLResponse)
async def blast_radius_page(request: Request):
    """Interactive blast radius visualizer."""
    return templates.TemplateResponse(request, "blast_radius.html", {
        "has_data": len(get_graph().components) > 0,
    })


# ---------------------------------------------------------------------------
# Risk Heat Map
# ---------------------------------------------------------------------------

@router.get("/heatmap", response_class=HTMLResponse)
async def heatmap_page(request: Request):
    """Interactive risk heat map page."""
    graph = get_graph()
    return templates.TemplateResponse(request, "heatmap.html", {
        "has_data": len(graph.components) > 0,
        "active_page": "heatmap",
    })


@router.get("/api/risk-heatmap", response_class=JSONResponse)
async def api_risk_heatmap():
    """Return risk heat map data as JSON."""
    graph = get_graph()
    if not graph.components:
        return JSONResponse({
            "components": [],
            "zones": [],
            "hotspots": [],
            "overall_risk_score": 0,
            "risk_distribution": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "dimension_weights": {},
        })

    from faultray.simulator.risk_heatmap import RiskHeatMapEngine

    engine = RiskHeatMapEngine()
    data = engine.analyze(graph)
    return JSONResponse(data.to_dict())


# ---------------------------------------------------------------------------
# Cost Attribution
# ---------------------------------------------------------------------------

@router.get("/cost-attribution", response_class=HTMLResponse)
async def cost_attribution_page(request: Request):
    """Cost attribution dashboard page."""
    graph = get_graph()
    report_data = None
    if graph.components:
        try:
            from faultray.simulator.cost_attribution import (
                CostAttributionEngine,
                CostModel,
            )

            cost_model = CostModel(revenue_per_hour=10_000.0)
            engine = CostAttributionEngine()
            report = engine.analyze(graph, cost_model)
            report_data = {
                "total_annual_risk": report.total_annual_risk,
                "components": [
                    {
                        "id": p.component_id,
                        "name": p.component_name,
                        "team": p.owner_team,
                        "direct_cost": p.direct_cost,
                        "cascade_cost": p.cascade_cost,
                        "total_annual_risk": p.total_annual_risk,
                        "percentage_of_total_risk": p.percentage_of_total_risk,
                        "improvement_roi": p.improvement_roi,
                    }
                    for p in report.component_profiles
                ],
                "teams": [
                    {
                        "name": t.team_name,
                        "total_annual_risk": t.total_annual_risk,
                        "percentage_of_total_risk": t.percentage_of_total_risk,
                        "recommended_budget": t.recommended_budget,
                        "component_count": len(t.owned_components),
                    }
                    for t in report.team_profiles
                ],
                "opportunities": [
                    {"component": o[0], "savings": o[1], "action": o[2]}
                    for o in report.cost_reduction_opportunities[:5]
                ],
            }
        except Exception:
            logger.warning("Cost attribution analysis failed", exc_info=True)

    return templates.TemplateResponse(request, "cost_attribution.html", {
        "has_data": len(graph.components) > 0,
        "active_page": "cost_attribution",
        "report": report_data,
    })


@router.get("/api/cost-attribution", response_class=JSONResponse)
async def api_cost_attribution(
    revenue_per_hour: float = 10_000.0,
    user=Depends(_require_permission("view_results")),
):
    """Get failure cost attribution analysis."""
    graph = get_graph()
    if not graph.components:
        return JSONResponse({
            "total_annual_risk": 0,
            "components": [],
            "teams": [],
            "cost_reduction_opportunities": [],
            "budget_allocation": {},
        })

    from faultray.simulator.cost_attribution import (
        CostAttributionEngine,
        CostModel,
    )

    cost_model = CostModel(revenue_per_hour=revenue_per_hour)
    engine = CostAttributionEngine()
    report = engine.analyze(graph, cost_model)

    return JSONResponse({
        "total_annual_risk": report.total_annual_risk,
        "currency": cost_model.currency,
        "components": [
            {
                "id": p.component_id,
                "name": p.component_name,
                "team": p.owner_team,
                "annual_failure_probability": p.annual_failure_probability,
                "estimated_downtime_hours": p.estimated_downtime_hours,
                "direct_cost": p.direct_cost,
                "cascade_cost": p.cascade_cost,
                "total_annual_risk": p.total_annual_risk,
                "percentage_of_total_risk": p.percentage_of_total_risk,
                "improvement_roi": p.improvement_roi,
            }
            for p in report.component_profiles
        ],
        "teams": [
            {
                "name": t.team_name,
                "owned_components": t.owned_components,
                "total_annual_risk": t.total_annual_risk,
                "highest_risk_component": t.highest_risk_component,
                "percentage_of_total_risk": t.percentage_of_total_risk,
                "recommended_budget": t.recommended_budget,
            }
            for t in report.team_profiles
        ],
        "cost_reduction_opportunities": [
            {"component": o[0], "savings": o[1], "action": o[2]}
            for o in report.cost_reduction_opportunities
        ],
        "budget_allocation": report.budget_allocation,
    })


# ---------------------------------------------------------------------------
# Topology Diff
# ---------------------------------------------------------------------------

@router.get("/topology-diff", response_class=HTMLResponse)
async def topology_diff_page(request: Request):
    """Topology Diff page."""
    return templates.TemplateResponse(request, "topology_diff.html", {
        "has_data": True,
        "active_page": "topology_diff",
    })


@router.post("/api/topology-diff")
async def topology_diff_api(request: Request):
    """Compare two uploaded YAML files and return diff results."""
    import tempfile

    form = await request.form()
    before_file = form.get("before_file")
    after_file = form.get("after_file")

    if not before_file or not after_file:
        return JSONResponse({"error": "Both before_file and after_file are required"}, status_code=400)

    try:
        before_content = await before_file.read()
        after_content = await after_file.read()

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="wb") as bf:
            bf.write(before_content)
            before_path = Path(bf.name)

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="wb") as af:
            af.write(after_content)
            after_path = Path(af.name)

        from faultray.reporter.topology_diff import TopologyDiffer

        differ = TopologyDiffer()
        result = differ.diff_files(before_path, after_path)
        mermaid_code = differ.to_mermaid(result)

        before_path.unlink(missing_ok=True)
        after_path.unlink(missing_ok=True)

        return JSONResponse({
            "diff": result.to_dict(),
            "mermaid": mermaid_code,
        })
    except Exception as e:
        logger.exception("Topology diff failed")
        return JSONResponse({"error": str(e)}, status_code=400)


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

@router.get("/api/benchmark/{industry}", response_class=JSONResponse)
async def benchmark_industry(
    industry: str,
    user=Depends(_require_permission("view_results")),
):
    """Benchmark infrastructure against industry peers."""
    graph = get_graph()
    if not graph.components:
        return JSONResponse(
            {"error": "No infrastructure loaded. Visit /demo first."},
            status_code=400,
        )

    from faultray.simulator.benchmarking import BenchmarkEngine, INDUSTRY_PROFILES

    engine = BenchmarkEngine()

    if industry == "list":
        profiles = engine.list_industries()
        return JSONResponse({
            "industries": [
                {
                    "industry": p.industry,
                    "display_name": p.display_name,
                    "avg_score": p.avg_resilience_score,
                    "median_score": p.median_resilience_score,
                    "sample_size": p.sample_size,
                }
                for p in profiles
            ],
        })

    if industry == "all":
        results = engine.compare_across_industries(graph)
        data = {}
        for ind, result in results.items():
            data[ind] = {
                "your_score": result.your_score,
                "percentile": result.percentile,
                "rank": result.rank_description,
                "strengths": len(result.strengths),
                "weaknesses": len(result.weaknesses),
            }
        return JSONResponse({"benchmarks": data})

    if industry not in INDUSTRY_PROFILES:
        available = sorted(INDUSTRY_PROFILES.keys())
        return JSONResponse(
            {"error": f"Unknown industry '{industry}'. Available: {available}"},
            status_code=400,
        )

    result = engine.benchmark(graph, industry)
    radar = engine.generate_radar_chart_data(result)
    return JSONResponse({
        "your_score": result.your_score,
        "industry": result.industry,
        "percentile": result.percentile,
        "rank": result.rank_description,
        "comparison": {
            k: {"yours": v[0], "industry_avg": v[1]}
            for k, v in result.comparison.items()
        },
        "strengths": result.strengths,
        "weaknesses": result.weaknesses,
        "improvement_priority": result.improvement_priority,
        "radar_chart": radar,
    })


# ---------------------------------------------------------------------------
# Score Decomposition
# ---------------------------------------------------------------------------

@router.get("/score-explain", response_class=HTMLResponse)
async def score_explain_page(request: Request):
    """Resilience Score Decomposition page."""
    graph = get_graph()
    has_data = len(graph.components) > 0

    decomposition_data = None
    if has_data:
        from faultray.simulator.score_decomposition import ScoreDecomposer

        decomposer = ScoreDecomposer()
        decomposition = decomposer.decompose(graph)
        decomposition_data = decomposition.to_dict()

    return templates.TemplateResponse(request, "score_explain.html", {
        "has_data": has_data,
        "decomposition": decomposition_data,
    })


@router.get("/api/score-decomposition", response_class=JSONResponse)
async def api_score_decomposition(user=Depends(_require_permission("view_results"))):
    """Return resilience score decomposition as JSON."""
    graph = get_graph()
    if not graph.components:
        return JSONResponse(
            {"error": "No infrastructure loaded. Visit /demo first."},
            status_code=400,
        )

    from faultray.simulator.score_decomposition import ScoreDecomposer

    decomposer = ScoreDecomposer()
    decomposition = decomposer.decompose(graph)
    return JSONResponse(decomposition.to_dict())


# ---------------------------------------------------------------------------
# Attack Surface Analysis
# ---------------------------------------------------------------------------

@router.get("/attack-surface", response_class=HTMLResponse)
async def attack_surface_page(request: Request):
    """Attack Surface Analysis page."""
    graph = get_graph()
    has_data = len(graph.components) > 0

    report_data = None
    if has_data:
        from faultray.simulator.attack_surface import AttackSurfaceAnalyzer

        analyzer = AttackSurfaceAnalyzer()
        report = analyzer.analyze(graph)
        report_data = report.to_dict()

    return templates.TemplateResponse(request, "attack_surface.html", {
        "has_data": has_data,
        "report": report_data,
    })


@router.get("/api/attack-surface", response_class=JSONResponse)
async def api_attack_surface(user=Depends(_require_permission("view_results"))):
    """Return attack surface analysis as JSON."""
    graph = get_graph()
    if not graph.components:
        return JSONResponse(
            {"error": "No infrastructure loaded. Visit /demo first."},
            status_code=400,
        )

    from faultray.simulator.attack_surface import AttackSurfaceAnalyzer

    analyzer = AttackSurfaceAnalyzer()
    report = analyzer.analyze(graph)
    return JSONResponse(report.to_dict())


# ---------------------------------------------------------------------------
# Components page (HTML)
# ---------------------------------------------------------------------------

@router.get("/components", response_class=HTMLResponse)
async def components_page(request: Request):
    graph = get_graph()
    comps = []
    for comp in graph.components.values():
        deps = graph.get_dependencies(comp.id)
        dependents = graph.get_dependents(comp.id)
        comps.append({
            "id": comp.id,
            "name": comp.name,
            "type": comp.type.value,
            "host": comp.host,
            "port": comp.port,
            "replicas": comp.replicas,
            "utilization": round(comp.utilization(), 1),
            "health": comp.health.value,
            "cpu_percent": comp.metrics.cpu_percent,
            "memory_percent": comp.metrics.memory_percent,
            "disk_percent": comp.metrics.disk_percent,
            "network_connections": comp.metrics.network_connections,
            "max_connections": comp.capacity.max_connections,
            "max_rps": comp.capacity.max_rps,
            "dependencies": [d.name for d in deps],
            "dependents": [d.name for d in dependents],
            "tags": comp.tags,
        })

    return templates.TemplateResponse(request, "components.html", {
        "components": comps,
        "has_data": len(comps) > 0,
    })
