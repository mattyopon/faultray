# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Dashboard summary, score history, htmx fragments, and badge endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from faultray.api.routes._shared import (
    _estimate_availability,
    _report_to_dict,
    get_graph,
    get_last_report,
    set_last_report,
    templates,
)
from faultray.api.routes._shared import _require_permission
from faultray.simulator.engine import SimulationEngine

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Main dashboard (HTML)
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    graph = get_graph()
    summary = graph.summary()

    _last_report = get_last_report()
    report_data = None
    if _last_report is not None:
        report_data = _report_to_dict(_last_report)

    total_comps = max(len(graph.components), 1)
    failover_count = sum(1 for c in graph.components.values() if c.failover.enabled)
    autoscale_count = sum(1 for c in graph.components.values() if c.autoscaling.enabled)
    monitoring_count = sum(
        1 for c in graph.components.values()
        if c.failover.health_check_interval_seconds > 0
    )
    cb_count = 0
    for edge in graph.all_dependency_edges():
        if edge.circuit_breaker.enabled:
            cb_count += 1
    total_edges = max(summary.get("total_dependencies", 1), 1)

    failover_pct = round(failover_count / total_comps * 100)
    autoscale_pct = round(autoscale_count / total_comps * 100)
    monitoring_pct = round(monitoring_count / total_comps * 100)
    cb_pct = round(cb_count / total_edges * 100)

    res_score = summary.get("resilience_score", 0)
    sla = _estimate_availability(res_score)

    spof_count = 0
    for comp in graph.components.values():
        dependents = graph.get_dependents(comp.id)
        if comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled:
            spof_count += 1

    maturity_points = 0
    if res_score >= 40:
        maturity_points += 1
    if failover_pct >= 30:
        maturity_points += 1
    if monitoring_pct >= 50:
        maturity_points += 1
    if cb_pct >= 20:
        maturity_points += 1
    if spof_count == 0:
        maturity_points += 1
    sre_maturity = max(1, min(5, maturity_points))

    risk_dist = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    if report_data:
        risk_dist["critical"] = report_data.get("critical_count", 0)
        risk_dist["high"] = report_data.get("warning_count", 0)
        risk_dist["low"] = report_data.get("passed_count", 0)

    compliance_scores = {}
    for fw in ["soc2", "hipaa", "iso27001", "pci-dss"]:
        enc_count = sum(
            1 for c in graph.components.values()
            if c.security.encryption_at_rest or c.security.encryption_in_transit
        )
        backup_count = sum(1 for c in graph.components.values() if c.security.backup_enabled)
        base = round(
            (enc_count + backup_count + failover_count + monitoring_count)
            / max(total_comps * 4, 1) * 100
        )
        compliance_scores[fw] = min(100, max(0, base))

    recent_activity: list[dict] = []
    if report_data:
        recent_activity.append({
            "type": "sim",
            "message": f"Simulation completed: {report_data['total_scenarios']} scenarios",
            "time": "latest",
        })
        if report_data["critical_count"] > 0:
            recent_activity.append({
                "type": "alert",
                "message": f"{report_data['critical_count']} critical findings detected",
                "time": "latest",
            })
        recent_activity.append({
            "type": "score",
            "message": f"Resilience score: {report_data['resilience_score']}",
            "time": "latest",
        })

    sparkline = "_ _ _ _"
    if res_score >= 80:
        sparkline = "_ - ~ ^"
    elif res_score >= 60:
        sparkline = "_ _ - ~"
    elif res_score >= 40:
        sparkline = "v _ _ -"

    dashboard_data = {
        "resilience_score": res_score,
        "sla_estimate": sla,
        "spof_count": spof_count,
        "sre_maturity_level": sre_maturity,
        "risk_distribution": risk_dist,
        "component_breakdown": summary.get("component_types", {}),
        "compliance_scores": compliance_scores,
        "recent_activity": recent_activity,
        "sparkline": sparkline,
        "quick_stats": {
            "failover_pct": failover_pct,
            "circuit_breaker_pct": cb_pct,
            "autoscaling_pct": autoscale_pct,
            "monitoring_pct": monitoring_pct,
        },
    }

    return templates.TemplateResponse(request, "dashboard.html", {
        "summary": summary,
        "has_data": len(graph.components) > 0,
        "report": report_data,
        "dashboard": type("D", (), dashboard_data)(),
    })


# ---------------------------------------------------------------------------
# Demo loader
# ---------------------------------------------------------------------------

@router.get("/demo")
async def load_demo(request: Request):
    """Load demo infrastructure and redirect to dashboard."""
    from faultray.api.routes._shared import build_demo_graph, set_graph

    graph = build_demo_graph()
    set_graph(graph)
    set_last_report(None)

    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()
    set_last_report(report)

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=303)


# ---------------------------------------------------------------------------
# Dashboard summary API
# ---------------------------------------------------------------------------

@router.get("/api/dashboard/summary", response_class=JSONResponse)
async def dashboard_summary():
    """Aggregated dashboard data for the enhanced V2 dashboard."""
    graph = get_graph()
    summary = graph.summary()

    res_score = summary.get("resilience_score", 0)
    sla = _estimate_availability(res_score)

    spof_count = 0
    for comp in graph.components.values():
        dependents = graph.get_dependents(comp.id)
        if comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled:
            spof_count += 1

    total_comps = max(len(graph.components), 1)
    failover_count = sum(1 for c in graph.components.values() if c.failover.enabled)
    autoscale_count = sum(1 for c in graph.components.values() if c.autoscaling.enabled)
    monitoring_count = sum(
        1 for c in graph.components.values()
        if c.failover.health_check_interval_seconds > 0
    )

    cb_count = 0
    for edge in graph.all_dependency_edges():
        if edge.circuit_breaker.enabled:
            cb_count += 1
    total_edges = max(summary.get("total_dependencies", 1), 1)

    failover_pct = round(failover_count / total_comps * 100)
    autoscale_pct = round(autoscale_count / total_comps * 100)
    monitoring_pct = round(monitoring_count / total_comps * 100)
    cb_pct = round(cb_count / total_edges * 100)

    maturity_points = 0
    if res_score >= 40:
        maturity_points += 1
    if failover_pct >= 30:
        maturity_points += 1
    if monitoring_pct >= 50:
        maturity_points += 1
    if cb_pct >= 20:
        maturity_points += 1
    if spof_count == 0:
        maturity_points += 1
    sre_maturity = max(1, min(5, maturity_points))

    _last_report = get_last_report()
    risk_dist = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    if _last_report is not None:
        report_d = _report_to_dict(_last_report)
        risk_dist["critical"] = report_d.get("critical_count", 0)
        risk_dist["high"] = report_d.get("warning_count", 0)
        risk_dist["low"] = report_d.get("passed_count", 0)

    comp_breakdown = summary.get("component_types", {})

    compliance_scores = {}
    for fw in ["soc2", "hipaa", "iso27001", "pci-dss"]:
        enc_count = sum(
            1 for c in graph.components.values()
            if c.security.encryption_at_rest or c.security.encryption_in_transit
        )
        backup_count = sum(1 for c in graph.components.values() if c.security.backup_enabled)
        base = round(
            (enc_count + backup_count + failover_count + monitoring_count)
            / max(total_comps * 4, 1) * 100
        )
        compliance_scores[fw] = min(100, max(0, base))

    recent_activity: list[dict] = []
    if _last_report is not None:
        rd = _report_to_dict(_last_report)
        recent_activity.append({
            "type": "sim",
            "message": f"Simulation completed: {rd['total_scenarios']} scenarios",
            "time": "latest",
        })
        if rd["critical_count"] > 0:
            recent_activity.append({
                "type": "alert",
                "message": f"{rd['critical_count']} critical findings detected",
                "time": "latest",
            })
        recent_activity.append({
            "type": "score",
            "message": f"Resilience score: {rd['resilience_score']}",
            "time": "latest",
        })

    sparkline = "_ _ _ _"
    if res_score >= 80:
        sparkline = "_ - ~ ^"
    elif res_score >= 60:
        sparkline = "_ _ - ~"
    elif res_score >= 40:
        sparkline = "v _ _ -"

    return JSONResponse({
        "resilience_score": res_score,
        "sla_estimate": sla,
        "spof_count": spof_count,
        "sre_maturity_level": sre_maturity,
        "risk_distribution": risk_dist,
        "component_breakdown": comp_breakdown,
        "compliance_scores": compliance_scores,
        "recent_activity": recent_activity,
        "sparkline": sparkline,
        "quick_stats": {
            "failover_pct": failover_pct,
            "circuit_breaker_pct": cb_pct,
            "autoscaling_pct": autoscale_pct,
            "monitoring_pct": monitoring_pct,
        },
    })


# ---------------------------------------------------------------------------
# Score history
# ---------------------------------------------------------------------------

@router.get("/api/score-history", response_class=JSONResponse)
async def api_score_history(
    limit: int = 30,
    user=Depends(_require_permission("view_results")),
):
    """Return resilience score history from past simulation runs."""
    try:
        from faultray.api.database import SimulationRunRow, get_session_factory
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = (
                select(SimulationRunRow)
                .where(SimulationRunRow.risk_score.isnot(None))
                .order_by(SimulationRunRow.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

            history = [
                {
                    "id": row.id,
                    "score": row.risk_score,
                    "engine_type": row.engine_type,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in reversed(rows)
            ]
            return JSONResponse({"history": history, "count": len(history)})
    except Exception:
        logger.debug("Could not fetch score history.", exc_info=True)
        return JSONResponse({"history": [], "count": 0, "note": "Database not available"})


# ---------------------------------------------------------------------------
# htmx fragments
# ---------------------------------------------------------------------------

@router.get("/htmx/score-cards", response_class=HTMLResponse)
async def htmx_score_cards(request: Request):
    """Dashboard score-card HTML fragment (htmx partial)."""
    graph = get_graph()
    summary = graph.summary()

    _last_report = get_last_report()
    report_data = None
    if _last_report is not None:
        report_data = _report_to_dict(_last_report)

    return templates.TemplateResponse(request, "fragments/score_cards.html", {
        "summary": summary,
        "report": report_data,
    })


@router.get("/htmx/risk-table", response_class=HTMLResponse)
async def htmx_risk_table(request: Request):
    """Risk table HTML fragment (htmx partial)."""
    _last_report = get_last_report()
    report_data = None
    if _last_report is not None:
        report_data = _report_to_dict(_last_report)

    return templates.TemplateResponse(request, "fragments/risk_table.html", {
        "report": report_data,
    })


# ---------------------------------------------------------------------------
# Badges
# ---------------------------------------------------------------------------

@router.get("/badge/{badge_type}.svg")
async def get_badge_svg(badge_type: str, style: str = "flat"):
    """Return SVG badge for embedding in READMEs and dashboards."""
    from faultray.api.badge_generator import BadgeGenerator, BadgeStyle

    graph = get_graph()
    gen = BadgeGenerator()

    style_map = {
        "flat": BadgeStyle.FLAT,
        "flat_square": BadgeStyle.FLAT_SQUARE,
        "flat-square": BadgeStyle.FLAT_SQUARE,
        "for_the_badge": BadgeStyle.FOR_THE_BADGE,
        "for-the-badge": BadgeStyle.FOR_THE_BADGE,
        "plastic": BadgeStyle.PLASTIC,
    }
    badge_style = style_map.get(style, BadgeStyle.FLAT)

    type_map = {
        "resilience_score": "resilience",
        "sla_estimate": "sla",
        "grade": "grade",
        "spof_count": "spof",
        "component_count": "component",
    }

    svg = ""
    bt = type_map.get(badge_type, badge_type)
    if bt == "resilience":
        svg = gen.generate_resilience_badge(graph, badge_style)
    elif bt == "sla":
        svg = gen.generate_sla_badge(graph, badge_style)
    elif bt == "grade":
        svg = gen.generate_grade_badge(graph, badge_style)
    elif bt == "spof":
        svg = gen.generate_spof_badge(graph, badge_style)
    elif bt == "component":
        svg = gen._generate_component_count_badge(graph, badge_style)
    else:
        svg = gen.generate_resilience_badge(graph, badge_style)

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/badge/all")
async def get_all_badges():
    """Return all badge URLs and markdown snippets."""
    from faultray.api.badge_generator import BadgeGenerator

    graph = get_graph()
    gen = BadgeGenerator()
    badges = gen.generate_all_badges(graph)

    return JSONResponse({
        "badges": {name: f"/badge/{name}.svg" for name in badges},
        "markdown": gen.get_markdown_links(""),
    })


@router.get("/api/badge-markdown")
async def get_badge_markdown(base_url: str = "http://localhost:8000"):
    """Return markdown to embed badges in README."""
    from faultray.api.badge_generator import BadgeGenerator

    gen = BadgeGenerator()
    return JSONResponse({
        "markdown": gen.get_markdown_links(base_url),
    })


# ---------------------------------------------------------------------------
# Reports page
# ---------------------------------------------------------------------------

@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    _last_report = get_last_report()
    return templates.TemplateResponse(request, "reports.html", {
        "has_data": _last_report is not None,
    })


@router.get("/report/executive", response_class=HTMLResponse)
async def executive_report(company_name: str = "Your Organization"):
    """Generate executive report (printable HTML)."""
    graph = get_graph()
    if not graph.components:
        return HTMLResponse(
            "<html><body><h1>No infrastructure loaded.</h1>"
            "<p>Visit /demo first to load a demo infrastructure.</p></body></html>",
            status_code=400,
        )

    _last_report = get_last_report()
    if _last_report is None:
        engine = SimulationEngine(graph)
        _last_report = engine.run_all_defaults()
        set_last_report(_last_report)

    from faultray.ai.analyzer import FaultRayAnalyzer
    from faultray.reporter.executive_pdf import ExecutiveReportGenerator

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, _last_report)

    generator = ExecutiveReportGenerator()
    html_content = generator.generate(
        graph, _last_report, ai_report,
        company_name=company_name,
    )
    return HTMLResponse(html_content)
