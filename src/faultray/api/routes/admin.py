# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Admin, config, health, marketplace, calendar, chat, templates, agents,
supply chain, OAuth, billing, and miscellaneous endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from faultray.api.routes._shared import (
    get_graph,
    get_model_path,
    templates,
)
from faultray.api.server import _require_permission

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Health, Versioning & API docs
# ---------------------------------------------------------------------------

@router.get("/api/health", response_class=JSONResponse)
async def health_check():
    """Return API health status."""
    from faultray.api.api_versioning import health_checker

    graph = get_graph()
    component_count = len(graph.components) if graph else 0
    return JSONResponse(health_checker.check(component_count))


@router.get("/api/versions", response_class=JSONResponse)
async def api_versions():
    """List available API versions."""
    from faultray.api.api_versioning import list_versions

    return JSONResponse({"versions": list_versions()})


@router.get("/api-docs", response_class=HTMLResponse)
async def api_docs_page(request: Request):
    """Interactive API documentation."""
    return templates.TemplateResponse("api_docs.html", {
        "request": request,
    })


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "has_data": True,
    })


# ---------------------------------------------------------------------------
# OAuth2 SSO
# ---------------------------------------------------------------------------

@router.get("/auth/login/{provider}")
async def oauth_login(provider: str):
    """Redirect to the OAuth provider's authorization page."""
    from faultray.api.oauth import OAuthConfig, generate_oauth_url

    config = OAuthConfig.from_env(provider)
    if config is None:
        return JSONResponse(
            {"error": f"OAuth provider '{provider}' is not configured"},
            status_code=400,
        )

    url = generate_oauth_url(config)
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=url)


@router.get("/auth/callback")
async def oauth_callback(code: str = "", state: str = "", provider: str = "github"):
    """Handle the OAuth callback."""
    from faultray.api.oauth import OAuthConfig, exchange_code_for_token, get_user_profile

    config = OAuthConfig.from_env(provider)
    if config is None:
        return JSONResponse(
            {"error": f"OAuth provider '{provider}' is not configured"},
            status_code=400,
        )

    if not code:
        return JSONResponse({"error": "Missing authorization code"}, status_code=400)

    try:
        access_token = await exchange_code_for_token(config, code)
        profile = await get_user_profile(config, access_token)
    except Exception as exc:
        logger.warning("OAuth callback failed: %s", exc)
        return JSONResponse({"error": f"OAuth exchange failed: {exc}"}, status_code=502)

    try:
        from faultray.api.auth import generate_api_key, hash_api_key
        from faultray.api.database import UserRow, get_session_factory
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(UserRow).where(UserRow.email == profile["email"])
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            api_key = generate_api_key()

            if user is None:
                user = UserRow(
                    email=profile["email"],
                    name=profile["name"],
                    api_key_hash=hash_api_key(api_key),
                )
                session.add(user)
            else:
                user.api_key_hash = hash_api_key(api_key)
                user.name = profile["name"]

            await session.commit()
            await session.refresh(user)

            return JSONResponse({
                "message": "Login successful",
                "user": {"id": user.id, "email": user.email, "name": user.name},
                "api_key": api_key,
            })
    except Exception as exc:
        logger.warning("OAuth user creation failed: %s", exc)
        return JSONResponse({"error": f"User creation failed: {exc}"}, status_code=500)


# ---------------------------------------------------------------------------
# Marketplace
# ---------------------------------------------------------------------------

@router.get("/marketplace", response_class=HTMLResponse)
async def marketplace_page(request: Request):
    """Marketplace HTML page."""
    graph = get_graph()
    has_data = bool(graph and graph.components)
    return templates.TemplateResponse("marketplace.html", {
        "request": request,
        "has_data": has_data,
        "active_page": "marketplace",
    })


@router.get("/api/marketplace/packages", response_class=JSONResponse)
async def list_marketplace_packages(
    category: str | None = None,
    provider: str | None = None,
):
    """List all marketplace packages."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    packages = mp.list_packages(category=category, provider=provider)
    return JSONResponse({"packages": [p.to_dict() for p in packages]})


@router.get("/api/marketplace/packages/{package_id}", response_class=JSONResponse)
async def get_marketplace_package(package_id: str):
    """Get a specific marketplace package by ID."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    try:
        pkg = mp.get_package(package_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Package not found: {package_id}")
    return JSONResponse(pkg.to_dict())


@router.post("/api/marketplace/install/{package_id}", response_class=JSONResponse)
async def install_marketplace_package(package_id: str):
    """Install a marketplace package."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    try:
        scenarios = mp.install_package(package_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Package not found: {package_id}")
    return JSONResponse({
        "installed": len(scenarios),
        "package_id": package_id,
        "scenarios": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "fault_count": len(s.faults),
            }
            for s in scenarios
        ],
    })


@router.get("/api/marketplace/featured", response_class=JSONResponse)
async def get_featured_packages():
    """Get featured marketplace packages."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    featured = mp.get_featured()
    return JSONResponse({"packages": [p.to_dict() for p in featured]})


@router.get("/api/marketplace/categories", response_class=JSONResponse)
async def get_marketplace_categories():
    """Get all marketplace categories."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    categories = mp.get_categories()
    return JSONResponse({"categories": [c.to_dict() for c in categories]})


@router.get("/api/marketplace/popular", response_class=JSONResponse)
async def get_popular_packages():
    """Get most popular marketplace packages."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    popular = mp.get_popular()
    return JSONResponse({"packages": [p.to_dict() for p in popular]})


@router.get("/api/marketplace/search", response_class=JSONResponse)
async def search_marketplace_packages(q: str = ""):
    """Search marketplace packages by query."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    results = mp.search(q)
    return JSONResponse({"packages": [p.to_dict() for p in results]})


# ---------------------------------------------------------------------------
# Chaos Calendar
# ---------------------------------------------------------------------------

@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):
    """Chaos Calendar page."""
    graph = get_graph()
    return templates.TemplateResponse("calendar.html", {
        "request": request,
        "has_data": len(graph.components) > 0,
        "active_page": "calendar",
    })


@router.get("/api/calendar", response_class=JSONResponse)
async def api_calendar_view():
    """Return calendar view JSON."""
    from faultray.scheduler.chaos_calendar import ChaosCalendar

    cal = ChaosCalendar()
    view = cal.get_calendar_view()

    return JSONResponse({
        "experiments": [exp.to_dict() for exp in view.experiments],
        "upcoming": [exp.to_dict() for exp in view.upcoming],
        "overdue": [exp.to_dict() for exp in view.overdue],
        "history": [exp.to_dict() for exp in view.history],
        "blackout_windows": [bw.to_dict() for bw in view.blackout_windows],
        "coverage_score": view.coverage_score,
        "experiment_frequency": view.experiment_frequency,
        "streak": view.streak,
    })


@router.post("/api/calendar/schedule", response_class=JSONResponse)
async def api_calendar_schedule(request: Request):
    """Schedule a new chaos experiment."""
    from faultray.scheduler.chaos_calendar import ChaosCalendar, ChaosExperiment

    body = await request.json()
    cal = ChaosCalendar()

    experiment = ChaosExperiment(
        id="",
        name=body.get("name", "Untitled Experiment"),
        description=body.get("description", ""),
        scenario_ids=body.get("scenario_ids", []),
        target_components=body.get("target_components", []),
        owner=body.get("owner", ""),
        tags=body.get("tags", []),
        infrastructure_file=body.get("infrastructure_file", ""),
        duration_estimate=body.get("duration_estimate", "30m"),
        notes=body.get("notes", ""),
    )

    if "scheduled_time" in body:
        from datetime import datetime
        experiment.scheduled_time = datetime.fromisoformat(body["scheduled_time"])
    if "recurrence" in body:
        from faultray.scheduler.chaos_calendar import RecurrencePattern
        experiment.recurrence = RecurrencePattern(body["recurrence"])

    eid = cal.schedule(experiment)
    return JSONResponse({"experiment_id": eid, "status": "scheduled"})


@router.delete("/api/calendar/{experiment_id}", response_class=JSONResponse)
async def api_calendar_cancel(experiment_id: str):
    """Cancel a scheduled experiment."""
    from faultray.scheduler.chaos_calendar import ChaosCalendar

    cal = ChaosCalendar()
    success = cal.cancel(experiment_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    return JSONResponse({"experiment_id": experiment_id, "status": "cancelled"})


@router.post("/api/calendar/auto-schedule", response_class=JSONResponse)
async def api_calendar_auto_schedule():
    """Auto-schedule experiments for critical components."""
    from faultray.scheduler.chaos_calendar import ChaosCalendar

    graph = get_graph()
    if not graph.components:
        raise HTTPException(status_code=400, detail="No infrastructure loaded. Visit /demo first.")

    cal = ChaosCalendar()
    experiments = cal.auto_schedule(graph)
    return JSONResponse({
        "scheduled": len(experiments),
        "experiments": [exp.to_dict() for exp in experiments],
    })


@router.get("/api/calendar/ical")
async def api_calendar_ical():
    """Download iCalendar (.ics) file."""
    from faultray.scheduler.chaos_calendar import ChaosCalendar

    cal = ChaosCalendar()
    ical = cal.export_ical()
    return Response(
        content=ical,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=chaos-calendar.ics"},
    )


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Chat interface page."""
    from faultray.api.chat_engine import ChatEngine

    graph = get_graph()
    engine = ChatEngine()
    suggestions = engine.get_suggestions(graph) if graph.components else [
        "Load the demo infrastructure first",
    ]
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "has_data": len(graph.components) > 0,
        "suggestions": suggestions,
        "active_page": "chat",
    })


@router.post("/api/chat", response_class=JSONResponse)
async def chat_api(request: Request):
    """Process a chat message about infrastructure."""
    from faultray.api.chat_engine import ChatEngine

    body = await request.json()
    question = body.get("question", "").strip()
    if not question:
        return JSONResponse(
            {"error": "No question provided"},
            status_code=400,
        )

    graph = get_graph()
    engine = ChatEngine()
    response = engine.ask(question, graph)

    return JSONResponse({
        "text": response.text,
        "intent": response.intent.value,
        "data": response.data,
        "suggestions": response.suggestions,
        "visualization": response.visualization,
    })


# ---------------------------------------------------------------------------
# Slack Bot
# ---------------------------------------------------------------------------

@router.post("/api/slack/commands", response_class=JSONResponse)
async def slack_command_handler(request: Request):
    """Handle Slack slash commands."""
    try:
        try:
            form = await request.form()
            text = form.get("text", "help")
            user_id = form.get("user_id", "")
            channel_id = form.get("channel_id", "")
        except Exception:
            try:
                body = await request.json()
            except Exception:
                body = {}
            text = body.get("text", "help")
            user_id = body.get("user_id", "")
            channel_id = body.get("channel_id", "")

        from faultray.integrations.slack_bot import FaultRaySlackBot, parse_slack_command

        model_path = get_model_path()

        bot = FaultRaySlackBot(model_path=model_path)
        command = parse_slack_command(str(text), user_id=str(user_id), channel_id=str(channel_id))
        response = bot.handle_command(command)

        return JSONResponse(response.to_dict())
    except Exception as exc:
        logger.error("Slack command handler error: %s", exc, exc_info=True)
        return JSONResponse(
            {"text": f"Internal error: {exc}", "response_type": "ephemeral"},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Template Gallery
# ---------------------------------------------------------------------------

@router.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request, category: str | None = None):
    """Render the Template Gallery page."""
    from dataclasses import asdict

    from faultray.templates.gallery import TemplateGallery, TemplateCategory

    gallery = TemplateGallery()
    gallery_templates = gallery.list_templates(category=category)
    categories = [c.value for c in TemplateCategory]

    template_data = [asdict(t) for t in gallery_templates]
    for td in template_data:
        td["category_value"] = td["category"]

    return templates.TemplateResponse("gallery.html", {
        "request": request,
        "has_data": True,
        "gallery_templates": template_data,
        "categories": categories,
        "active_category": category,
    })


@router.get("/api/templates", response_class=JSONResponse)
async def api_list_templates(category: str | None = None):
    """List all gallery templates as JSON."""
    from dataclasses import asdict

    from faultray.templates.gallery import TemplateGallery

    gallery = TemplateGallery()
    gallery_templates = gallery.list_templates(category=category)
    return JSONResponse([asdict(t) for t in gallery_templates])


@router.get("/api/templates/{template_id}", response_class=JSONResponse)
async def api_get_template(template_id: str):
    """Get a specific template by ID."""
    from dataclasses import asdict

    from faultray.templates.gallery import TemplateGallery

    gallery = TemplateGallery()
    try:
        t = gallery.get_template(template_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return JSONResponse(asdict(t))


# ---------------------------------------------------------------------------
# Agent Assessment
# ---------------------------------------------------------------------------

@router.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request):
    """AI Agent assessment page."""
    graph = get_graph()
    has_data = len(graph.components) > 0

    assessment_data = None
    monitoring_data = None
    scenarios_data = None
    if has_data:
        import dataclasses

        from faultray.simulator.adoption_engine import AdoptionEngine
        from faultray.simulator.agent_monitor import AgentMonitorEngine
        from faultray.simulator.agent_scenarios import generate_agent_scenarios

        engine = AdoptionEngine(graph)
        reports = engine.assess_all_agents()
        assessment_data = [dataclasses.asdict(r) for r in reports]

        monitor = AgentMonitorEngine(graph)
        plan = monitor.generate_monitoring_plan()
        monitoring_data = dataclasses.asdict(plan)

        scenarios = generate_agent_scenarios(graph)
        scenarios_data = [s.model_dump() for s in scenarios]

    return templates.TemplateResponse("agents.html", {
        "request": request,
        "has_data": has_data,
        "active_page": "agents",
        "assessments": assessment_data,
        "monitoring": monitoring_data,
        "scenarios": scenarios_data,
    })


@router.post("/api/v1/agent/assess", response_class=JSONResponse)
async def agent_assess(request: Request, user=Depends(_require_permission("view_results"))):
    """Run agent adoption risk assessment."""
    import dataclasses

    graph = get_graph()
    if not graph.components:
        return JSONResponse(
            {"error": "No infrastructure loaded. Visit /demo first."},
            status_code=400,
        )

    from faultray.simulator.adoption_engine import AdoptionEngine

    engine = AdoptionEngine(graph)
    reports = engine.assess_all_agents()
    return JSONResponse({"assessments": [dataclasses.asdict(r) for r in reports]})


@router.post("/api/v1/agent/monitor", response_class=JSONResponse)
async def agent_monitor(request: Request, user=Depends(_require_permission("view_results"))):
    """Generate agent monitoring plan."""
    import dataclasses

    graph = get_graph()
    if not graph.components:
        return JSONResponse(
            {"error": "No infrastructure loaded. Visit /demo first."},
            status_code=400,
        )

    from faultray.simulator.agent_monitor import AgentMonitorEngine

    monitor = AgentMonitorEngine(graph)
    plan = monitor.generate_monitoring_plan()
    return JSONResponse(dataclasses.asdict(plan))


@router.post("/api/v1/agent/scenarios", response_class=JSONResponse)
async def agent_scenarios(request: Request, user=Depends(_require_permission("view_results"))):
    """List agent-specific scenarios."""
    graph = get_graph()
    if not graph.components:
        return JSONResponse(
            {"error": "No infrastructure loaded. Visit /demo first."},
            status_code=400,
        )

    from faultray.simulator.agent_scenarios import generate_agent_scenarios

    scenarios = generate_agent_scenarios(graph)
    return JSONResponse({"scenarios": [s.model_dump() for s in scenarios]})


# ---------------------------------------------------------------------------
# Supply Chain Analysis
# ---------------------------------------------------------------------------

@router.get("/supply-chain", response_class=HTMLResponse)
async def supply_chain_page(request: Request):
    """Supply chain attack analysis page."""
    graph = get_graph()
    has_data = len(graph.components) > 0

    report_data = None
    if has_data:
        import dataclasses

        from faultray.simulator.supply_chain_cascade import SupplyChainCascadeEngine

        engine = SupplyChainCascadeEngine(graph)
        report = engine.analyze_all_packages()
        report_data = dataclasses.asdict(report)

    return templates.TemplateResponse("supply_chain.html", {
        "request": request,
        "has_data": has_data,
        "active_page": "supply_chain",
        "report": report_data,
    })


@router.post("/api/v1/supply-chain/analyze", response_class=JSONResponse)
async def supply_chain_analyze(request: Request, user=Depends(_require_permission("view_results"))):
    """Run supply chain attack analysis."""
    import dataclasses

    graph = get_graph()
    if not graph.components:
        return JSONResponse(
            {"error": "No infrastructure loaded. Visit /demo first."},
            status_code=400,
        )

    from faultray.simulator.supply_chain_cascade import SupplyChainCascadeEngine

    engine = SupplyChainCascadeEngine(graph)
    report = engine.analyze_all_packages()
    return JSONResponse(dataclasses.asdict(report))
