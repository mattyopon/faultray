"""FastAPI web dashboard for FaultRay."""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limiter — lightweight in-memory implementation
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple in-memory rate limiter using a sliding window."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        self.requests[client_id] = [
            t for t in self.requests[client_id] if now - t < self.window
        ]
        if len(self.requests[client_id]) >= self.max_requests:
            return False
        self.requests[client_id].append(now)
        return True


_rate_limiter = RateLimiter()

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_graph: InfraGraph | None = None
_model_path: Path | None = None
_last_report = None

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Lifespan — initialise database on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialise the database and optional Prometheus monitor on startup."""
    from faultray.api.database import init_db
    try:
        await init_db()
        logger.info("FaultRay database initialised.")
    except Exception:
        logger.warning("Database initialisation skipped (aiosqlite may not be installed).")

    # Start Prometheus background monitor if configured
    _prom_monitor = None
    prom_url = os.environ.get("FAULTRAY_PROMETHEUS_URL", os.environ.get("FAULTRAY_PROMETHEUS_URL", os.environ.get("FAULTRAY_PROMETHEUS_URL")))
    if prom_url:
        try:
            from faultray.discovery.prometheus_monitor import PrometheusMonitor

            interval = int(os.environ.get("FAULTRAY_PROMETHEUS_INTERVAL", os.environ.get("FAULTRAY_PROMETHEUS_INTERVAL", os.environ.get("FAULTRAY_PROMETHEUS_INTERVAL", "60"))))
            _prom_monitor = PrometheusMonitor(prom_url, get_graph(), interval)
            await _prom_monitor.start()
            logger.info("Prometheus monitor started: %s (interval=%ds)", prom_url, interval)
        except Exception:
            logger.warning("Could not start Prometheus monitor.", exc_info=True)

    yield

    # Shutdown Prometheus monitor
    if _prom_monitor is not None:
        await _prom_monitor.stop()


from faultray.api.openapi_config import OPENAPI_CONFIG, OPENAPI_TAGS
from faultray.api.v1.routes import router as v1_router

app = FastAPI(
    title=OPENAPI_CONFIG["title"],
    description=OPENAPI_CONFIG["description"],
    version=OPENAPI_CONFIG["version"],
    contact=OPENAPI_CONFIG["contact"],
    license_info=OPENAPI_CONFIG["license_info"],
    docs_url=OPENAPI_CONFIG["docs_url"],
    redoc_url=OPENAPI_CONFIG["redoc_url"],
    openapi_url=OPENAPI_CONFIG["openapi_url"],
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS middleware — origins configurable via FAULTRAY_CORS_ORIGINS env var
# ---------------------------------------------------------------------------
_cors_origins_raw = os.environ.get("FAULTRAY_CORS_ORIGINS", "")
_cors_origins: list[str] = [
    origin.strip()
    for origin in _cors_origins_raw.split(",")
    if origin.strip()
] if _cors_origins_raw else []

if _cors_origins == ["*"]:
    logger.warning(
        "CORS is configured with allow_origins='*'. "
        "This is insecure for production. Set FAULTRAY_CORS_ORIGINS to specific origins."
    )

# Only allow credentials when specific origins are set (not wildcard or empty)
_allow_credentials = bool(_cors_origins) and _cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Rate-limiting middleware for /api/* routes
# ---------------------------------------------------------------------------

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Enforce rate limiting on all endpoints."""
    # Use X-Forwarded-For for proxy-aware client IP detection
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # First IP in the chain is the original client
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": 429,
                    "message": "Too many requests. Please try again later.",
                }
            },
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Structured error responses
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """Return structured JSON error responses for HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.status_code, "message": exc.detail}},
    )


# ---------------------------------------------------------------------------
# Insurance scoring router
# ---------------------------------------------------------------------------
from faultray.api.insurance_api import insurance_router

app.include_router(insurance_router)

# ---------------------------------------------------------------------------
# Embeddable widget router
# ---------------------------------------------------------------------------
from faultray.api.widget import widget_router

app.include_router(widget_router)

# ---------------------------------------------------------------------------
# GraphQL-like API router
# ---------------------------------------------------------------------------
from faultray.api.graphql_api import graphql_router

app.include_router(graphql_router)

# ---------------------------------------------------------------------------
# Team Workspace API router
# ---------------------------------------------------------------------------
from faultray.api.teams import teams_router

app.include_router(teams_router)

# ---------------------------------------------------------------------------
# Resilience Leaderboard API router
# ---------------------------------------------------------------------------
from faultray.api.leaderboard import leaderboard_router

app.include_router(leaderboard_router)


# ---------------------------------------------------------------------------
# Stripe Billing routes
# ---------------------------------------------------------------------------

from faultray.api.billing import (
    PricingTier as _PricingTier,
    TIER_LIMITS as _TIER_LIMITS,
    StripeManager as _StripeManager,
    UsageTracker as _UsageTracker,
    _stripe_available,
)

_stripe_mgr = _StripeManager()


@app.post("/api/billing/checkout", response_class=JSONResponse)
async def billing_checkout(request: Request):
    """Create a Stripe Checkout Session and return the redirect URL."""
    if not _stripe_mgr.enabled:
        return JSONResponse(
            {"error": "Billing is not configured. Running in free-tier mode."},
            status_code=503,
        )

    body = await request.json()
    tier_str = body.get("tier", "pro")
    team_id = body.get("team_id", "")
    success_url = body.get("success_url", str(request.base_url) + "billing?status=success")
    cancel_url = body.get("cancel_url", str(request.base_url) + "billing?status=cancelled")

    if not team_id:
        return JSONResponse({"error": "team_id is required"}, status_code=400)

    try:
        tier = _PricingTier(tier_str)
    except ValueError:
        return JSONResponse(
            {"error": f"Invalid tier: {tier_str}. Choose pro or enterprise."},
            status_code=400,
        )

    if tier == _PricingTier.FREE:
        return JSONResponse(
            {"error": "Cannot purchase the free tier."},
            status_code=400,
        )

    try:
        url = await _stripe_mgr.create_checkout_session(
            tier=tier,
            team_id=team_id,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return JSONResponse({"checkout_url": url})
    except Exception as exc:
        logger.error("Checkout session creation failed: %s", exc, exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Receive and process Stripe webhook events."""
    if not _stripe_mgr.enabled:
        return JSONResponse({"error": "Stripe is not configured"}, status_code=503)

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event_data = await _stripe_mgr.handle_webhook_event(payload, sig_header)
        await _stripe_mgr.persist_webhook_event(event_data)
        return JSONResponse({"status": "ok", "event_type": event_data.get("event_type")})
    except ValueError as exc:
        logger.warning("Invalid Stripe webhook payload: %s", exc)
        return JSONResponse({"error": "Invalid payload"}, status_code=400)
    except Exception as exc:
        logger.error("Stripe webhook processing failed: %s", exc, exc_info=True)
        return JSONResponse({"error": "Webhook processing failed"}, status_code=400)


@app.get("/api/billing/portal", response_class=JSONResponse)
async def billing_portal(request: Request, team_id: str = ""):
    """Return a Stripe Customer Portal URL for subscription management."""
    if not _stripe_mgr.enabled:
        return JSONResponse(
            {"error": "Billing is not configured. Running in free-tier mode."},
            status_code=503,
        )

    if not team_id:
        return JSONResponse({"error": "team_id query parameter is required"}, status_code=400)

    sub = await _stripe_mgr.get_subscription(team_id)
    if sub is None or not sub.get("stripe_customer_id"):
        return JSONResponse(
            {"error": "No active subscription found for this team."},
            status_code=404,
        )

    return_url = str(request.base_url) + "billing"

    try:
        url = await _stripe_mgr.create_customer_portal_session(
            customer_id=sub["stripe_customer_id"],
            return_url=return_url,
        )
        return JSONResponse({"portal_url": url})
    except Exception as exc:
        logger.error("Customer portal creation failed: %s", exc, exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/billing/usage", response_class=JSONResponse)
async def billing_usage(team_id: str = ""):
    """Return current usage stats and tier information for a team."""
    if not team_id:
        return JSONResponse({"error": "team_id query parameter is required"}, status_code=400)

    tracker = _UsageTracker(db_session_factory=None)
    usage = await tracker.get_usage(team_id)

    # Include current component count from loaded graph
    graph = get_graph()
    usage["component_count"] = len(graph.components) if graph and graph.components else 0

    # Augment with Stripe billing status
    usage["stripe_enabled"] = _stripe_mgr.enabled
    if _stripe_mgr.enabled:
        sub = await _stripe_mgr.get_subscription(team_id)
        usage["subscription"] = sub

    return JSONResponse(usage)


@app.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request):
    """Billing management page."""
    return templates.TemplateResponse("billing.html", {
        "request": request,
        "has_data": True,
        "stripe_enabled": _stripe_mgr.enabled,
        "tiers": {
            tier.value: {
                "max_components": limits.max_components,
                "max_simulations_per_month": limits.max_simulations_per_month,
                "compliance_reports": limits.compliance_reports,
                "insurance_api": limits.insurance_api,
                "custom_sso": limits.custom_sso,
                "support_sla": limits.support_sla,
            }
            for tier, limits in _TIER_LIMITS.items()
        },
        "active_page": "billing",
    })


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_graph() -> InfraGraph:
    """Return current graph, creating an empty one if needed."""
    global _graph
    if _graph is None:
        _graph = InfraGraph()
    return _graph


def set_graph(graph: InfraGraph) -> None:
    global _graph
    _graph = graph


def build_demo_graph() -> InfraGraph:
    """Build the demo infrastructure graph.

    Delegates to the shared helper in :mod:`faultray.model.demo` so that
    CLI ``demo`` command and the web dashboard use identical data.
    """
    from faultray.model.demo import create_demo_graph

    return create_demo_graph()


def _report_to_dict(report) -> dict:
    """Convert a SimulationReport to a JSON-serialisable dict."""
    def _result_dict(r):
        return {
            "scenario_id": r.scenario.id,
            "scenario_name": r.scenario.name,
            "scenario_description": r.scenario.description,
            "risk_score": round(r.risk_score, 2),
            "is_critical": r.is_critical,
            "is_warning": r.is_warning,
            "cascade": {
                "trigger": r.cascade.trigger,
                "severity": round(r.cascade.severity, 2),
                "effects": [
                    {
                        "component_id": e.component_id,
                        "component_name": e.component_name,
                        "health": e.health.value,
                        "reason": e.reason,
                        "estimated_time_seconds": e.estimated_time_seconds,
                        "metrics_impact": e.metrics_impact,
                    }
                    for e in r.cascade.effects
                ],
            },
        }

    return {
        "resilience_score": round(report.resilience_score, 1),
        "total_scenarios": len(report.results),
        "critical_count": len(report.critical_findings),
        "warning_count": len(report.warnings),
        "passed_count": len(report.passed),
        "critical": [_result_dict(r) for r in report.critical_findings],
        "warnings": [_result_dict(r) for r in report.warnings],
        "passed": [_result_dict(r) for r in report.passed],
    }


async def _save_run(report_dict: dict, engine_type: str = "static") -> int | None:
    """Persist a simulation run to the database. Returns the row id or None."""
    try:
        from faultray.api.database import SimulationRunRow, get_session_factory

        session_factory = get_session_factory()
        async with session_factory() as session:
            row = SimulationRunRow(
                engine_type=engine_type,
                config_json=None,
                results_json=json.dumps(report_dict),
                risk_score=report_dict.get("resilience_score"),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id
    except Exception:
        logger.debug("Could not persist simulation run.", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Auth dependency — lazy import so the app still works without aiosqlite
# ---------------------------------------------------------------------------

async def _optional_user(request: Request):
    """Try to resolve the current user; return None if auth module unavailable."""
    try:
        from faultray.api.auth import get_current_user
        from fastapi.security import HTTPBearer

        scheme = HTTPBearer(auto_error=False)
        credentials = await scheme(request)
        return await get_current_user(request, credentials)
    except Exception:
        return None


def _require_permission(permission: str):
    """Lazy wrapper around auth.require_permission (opt-in RBAC).

    Falls back to allowing all access if the auth module cannot be loaded.
    """
    async def _dep(request: Request):
        try:
            from faultray.api.auth import require_permission
            checker = require_permission(permission)
            return await checker(request)
        except HTTPException:
            raise
        except Exception:
            return None
    return _dep


# ---------------------------------------------------------------------------
# HTML routes (public)
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    graph = get_graph()
    summary = graph.summary()

    report_data = None
    if _last_report is not None:
        report_data = _report_to_dict(_last_report)

    # Build enhanced dashboard context
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

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "summary": summary,
        "has_data": len(graph.components) > 0,
        "report": report_data,
        "dashboard": type("D", (), dashboard_data)(),
    })


@app.get("/components", response_class=HTMLResponse)
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

    return templates.TemplateResponse("components.html", {
        "request": request,
        "components": comps,
        "has_data": len(comps) > 0,
    })


@app.get("/simulation", response_class=HTMLResponse)
async def simulation_page(request: Request):
    report_data = None
    if _last_report is not None:
        report_data = _report_to_dict(_last_report)

    return templates.TemplateResponse("simulation.html", {
        "request": request,
        "report": report_data,
        "has_data": len(get_graph().components) > 0,
    })


@app.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    return templates.TemplateResponse("graph.html", {
        "request": request,
        "has_data": len(get_graph().components) > 0,
    })


@app.get("/analyze", response_class=HTMLResponse)
async def analyze_page(request: Request):
    """Run AI analysis and render the analyze page."""
    global _last_report
    graph = get_graph()
    has_data = len(graph.components) > 0

    analysis_data = None
    if has_data:
        # Run simulation if not already done
        if _last_report is None:
            engine = SimulationEngine(graph)
            _last_report = engine.run_all_defaults()

        # Run AI analysis
        from faultray.ai.analyzer import FaultRayAnalyzer
        import dataclasses

        analyzer = FaultRayAnalyzer()
        ai_report = analyzer.analyze(graph, _last_report)

        # Convert to template-friendly dict
        analysis_data = dataclasses.asdict(ai_report)

    return templates.TemplateResponse("analyze.html", {
        "request": request,
        "has_data": has_data,
        "analysis": analysis_data,
    })


@app.get("/advisor", response_class=HTMLResponse)
async def advisor_page(request: Request, target_nines: float = 4.0):
    """Architecture Advisor page — shows redesign recommendations."""
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


# ---------------------------------------------------------------------------
# JSON API routes
# ---------------------------------------------------------------------------

@app.get("/api/architecture-advice", response_class=JSONResponse)
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


@app.get("/api/analyze", response_class=JSONResponse)
async def api_analyze(user=Depends(_require_permission("view_results"))):
    """Run AI analysis and return JSON results."""
    global _last_report
    graph = get_graph()
    if not graph.components:
        return JSONResponse(
            {"error": "No infrastructure loaded. Visit /demo first."},
            status_code=400,
        )

    # Run simulation if not already done
    if _last_report is None:
        engine = SimulationEngine(graph)
        _last_report = engine.run_all_defaults()

    from faultray.ai.analyzer import FaultRayAnalyzer
    import dataclasses

    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, _last_report)
    report_dict = dataclasses.asdict(ai_report)

    return JSONResponse(report_dict)


@app.get("/simulation/run")
async def simulation_run_get():
    """Run simulation and return JSON results (GET endpoint)."""
    global _last_report
    graph = get_graph()
    if not graph.components:
        return JSONResponse({"error": "No infrastructure loaded. Visit /demo first."}, status_code=400)

    engine = SimulationEngine(graph)
    _last_report = engine.run_all_defaults()
    report_dict = _report_to_dict(_last_report)

    # Persist to database
    run_id = await _save_run(report_dict, engine_type="static")
    if run_id is not None:
        report_dict["run_id"] = run_id

    return JSONResponse(report_dict)


@app.post("/api/simulate", response_class=JSONResponse)
async def api_simulate(request: Request, user=Depends(_require_permission("run_simulation"))):
    """Run simulation and return JSON results (POST endpoint)."""
    global _last_report
    graph = get_graph()
    if not graph.components:
        return JSONResponse({"error": "No infrastructure loaded. Visit /demo first."}, status_code=400)

    engine = SimulationEngine(graph)
    _last_report = engine.run_all_defaults()
    report_dict = _report_to_dict(_last_report)

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


@app.get("/api/graph-data", response_class=JSONResponse)
async def api_graph_data(user=Depends(_require_permission("view_results"))):
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


@app.get("/demo")
async def load_demo(request: Request):
    """Load demo infrastructure and redirect to dashboard."""
    global _last_report
    graph = build_demo_graph()
    set_graph(graph)
    _last_report = None

    # Run simulation automatically for the demo
    engine = SimulationEngine(graph)
    _last_report = engine.run_all_defaults()

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=303)


# ---------------------------------------------------------------------------
# Simulation runs CRUD  (persistence layer)
# ---------------------------------------------------------------------------

@app.get("/api/runs", response_class=JSONResponse)
async def list_runs(
    limit: int = 50,
    offset: int = 0,
    project_id: int | None = None,
    user=Depends(_require_permission("view_results")),
):
    """List past simulation runs (newest first).

    Optional query parameters:
    - ``project_id``: filter by project
    """
    try:
        from faultray.api.database import (
            ProjectRow,
            SimulationRunRow,
            get_session_factory,
        )
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(SimulationRunRow)

            # Filter by project_id if provided
            if project_id is not None:
                stmt = stmt.where(SimulationRunRow.project_id == project_id)

            # Multi-tenant: when auth is active, only return runs belonging
            # to projects owned by the user's team.
            if user is not None and user.team_id is not None:
                team_project_ids_stmt = select(ProjectRow.id).where(
                    ProjectRow.team_id == user.team_id
                )
                team_project_ids = (
                    await session.execute(team_project_ids_stmt)
                ).scalars().all()
                # Include runs with no project (legacy) or runs in team projects
                stmt = stmt.where(
                    (SimulationRunRow.project_id.is_(None))
                    | (SimulationRunRow.project_id.in_(team_project_ids))
                )

            stmt = (
                stmt.order_by(SimulationRunRow.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

            runs = []
            for row in rows:
                runs.append({
                    "id": row.id,
                    "project_id": row.project_id,
                    "engine_type": row.engine_type,
                    "risk_score": row.risk_score,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })
            return JSONResponse({"runs": runs, "count": len(runs)})
    except Exception as exc:
        logger.debug("Could not list runs: %s", exc)
        return JSONResponse({"runs": [], "count": 0, "note": "Database not available"})


@app.get("/api/runs/{run_id}", response_class=JSONResponse)
async def get_run(run_id: int, user=Depends(_require_permission("view_results"))):
    """Get a specific simulation run by ID."""
    try:
        from faultray.api.database import SimulationRunRow, get_session_factory
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(SimulationRunRow).where(SimulationRunRow.id == run_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return JSONResponse({"error": "Run not found"}, status_code=404)

            return JSONResponse({
                "id": row.id,
                "project_id": row.project_id,
                "engine_type": row.engine_type,
                "config_json": json.loads(row.config_json) if row.config_json else None,
                "results_json": json.loads(row.results_json) if row.results_json else None,
                "risk_score": row.risk_score,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })
    except Exception as exc:
        logger.debug("Could not get run: %s", exc)
        return JSONResponse({"error": "Database not available"}, status_code=503)


@app.delete("/api/runs/{run_id}", response_class=JSONResponse)
async def delete_run(run_id: int, request: Request, user=Depends(_require_permission("run_simulation"))):
    """Delete a simulation run by ID."""
    try:
        from faultray.api.database import SimulationRunRow, get_session_factory, log_audit
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(SimulationRunRow).where(SimulationRunRow.id == run_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return JSONResponse({"error": "Run not found"}, status_code=404)

            await session.delete(row)

            # Audit log
            await log_audit(
                session,
                user_id=user.id if user else None,
                action="delete_run",
                resource_type="simulation_run",
                resource_id=str(run_id),
                ip=request.client.host if request.client else None,
            )

            await session.commit()
            return JSONResponse({"deleted": True, "id": run_id})
    except Exception as exc:
        logger.debug("Could not delete run: %s", exc)
        return JSONResponse({"error": "Database not available"}, status_code=503)


# ---------------------------------------------------------------------------
# Projects CRUD (multi-tenant)
# ---------------------------------------------------------------------------

@app.post("/api/projects", response_class=JSONResponse)
async def create_project(request: Request, user=Depends(_require_permission("create_project"))):
    """Create a new project.

    Expects JSON body with ``name`` (required) and ``team_id`` (optional).
    """
    try:
        from faultray.api.database import ProjectRow, get_session_factory, log_audit

        body = await request.json()
        name = body.get("name")
        if not name:
            return JSONResponse({"error": "name is required"}, status_code=400)

        team_id = body.get("team_id")

        session_factory = get_session_factory()
        async with session_factory() as session:
            project = ProjectRow(
                name=name,
                owner_id=user.id if user else None,
                team_id=team_id if team_id else (user.team_id if user else None),
            )
            session.add(project)
            await session.flush()

            # Audit log
            await log_audit(
                session,
                user_id=user.id if user else None,
                action="create_project",
                resource_type="project",
                resource_id=str(project.id),
                details={"name": name, "team_id": project.team_id},
                ip=request.client.host if request.client else None,
            )

            await session.commit()
            await session.refresh(project)

            return JSONResponse({
                "id": project.id,
                "name": project.name,
                "owner_id": project.owner_id,
                "team_id": project.team_id,
                "created_at": project.created_at.isoformat() if project.created_at else None,
            }, status_code=201)
    except Exception as exc:
        logger.debug("Could not create project: %s", exc)
        return JSONResponse({"error": "Database not available"}, status_code=503)


@app.get("/api/projects", response_class=JSONResponse)
async def list_projects(user=Depends(_require_permission("view_results"))):
    """List projects visible to the current user.

    When auth is active and the user belongs to a team, only projects
    belonging to that team (or owned by the user) are returned.
    """
    try:
        from faultray.api.database import ProjectRow, get_session_factory
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(ProjectRow)

            # Multi-tenant filter
            if user is not None and user.team_id is not None:
                stmt = stmt.where(
                    (ProjectRow.team_id == user.team_id)
                    | (ProjectRow.owner_id == user.id)
                )

            stmt = stmt.order_by(ProjectRow.created_at.desc())
            result = await session.execute(stmt)
            rows = result.scalars().all()

            projects = []
            for row in rows:
                projects.append({
                    "id": row.id,
                    "name": row.name,
                    "owner_id": row.owner_id,
                    "team_id": row.team_id,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })
            return JSONResponse({"projects": projects, "count": len(projects)})
    except Exception as exc:
        logger.debug("Could not list projects: %s", exc)
        return JSONResponse({"projects": [], "count": 0, "note": "Database not available"})


# ---------------------------------------------------------------------------
# Audit logs (admin only)
# ---------------------------------------------------------------------------

@app.get("/api/audit-logs", response_class=JSONResponse)
async def list_audit_logs(
    limit: int = 100,
    offset: int = 0,
    user=Depends(_optional_user),
):
    """List audit log entries (admin-only when auth is active).

    In backward-compatible mode (no users), anyone can view logs.
    When auth is active, only team owners (user_id == 1 by convention) or
    any authenticated user can access for now.
    """
    try:
        from faultray.api.database import AuditLog, get_session_factory
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = (
                select(AuditLog)
                .order_by(AuditLog.id.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

            logs = []
            for row in rows:
                logs.append({
                    "id": row.id,
                    "user_id": row.user_id,
                    "action": row.action,
                    "resource_type": row.resource_type,
                    "resource_id": row.resource_id,
                    "details": json.loads(row.details_json) if row.details_json else None,
                    "ip_address": row.ip_address,
                    "created_at": row.created_at,
                })
            return JSONResponse({"audit_logs": logs, "count": len(logs)})
    except Exception as exc:
        logger.debug("Could not list audit logs: %s", exc)
        return JSONResponse({"audit_logs": [], "count": 0, "note": "Database not available"})


# ---------------------------------------------------------------------------
# OAuth2 SSO routes (optional — only active when env vars are configured)
# ---------------------------------------------------------------------------

@app.get("/auth/login/{provider}")
async def oauth_login(provider: str):
    """Redirect to the OAuth provider's authorization page.

    Only active when ``FAULTRAY_OAUTH_{PROVIDER}_CLIENT_ID`` and
    ``FAULTRAY_OAUTH_{PROVIDER}_CLIENT_SECRET`` env vars are set
    (legacy ``FAULTRAY_OAUTH_*`` and ``FAULTRAY_OAUTH_*`` also accepted as fallbacks).
    """
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


@app.get("/auth/callback")
async def oauth_callback(code: str = "", state: str = "", provider: str = "github"):
    """Handle the OAuth callback, create or update the user, and return an API key.

    The *provider* query parameter indicates which OAuth provider to use.
    """
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

    # Create or update user in the database
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
                # Rotate API key on each login
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
# New page routes (HTML — templates assumed to exist)
# ---------------------------------------------------------------------------

@app.get("/security", response_class=HTMLResponse)
async def security_page(request: Request):
    graph = get_graph()
    return templates.TemplateResponse("security.html", {
        "request": request,
        "has_data": len(graph.components) > 0,
    })


@app.get("/cost", response_class=HTMLResponse)
async def cost_page(request: Request):
    graph = get_graph()
    return templates.TemplateResponse("cost.html", {
        "request": request,
        "has_data": len(graph.components) > 0,
    })


@app.get("/compliance", response_class=HTMLResponse)
async def compliance_page(request: Request):
    graph = get_graph()
    return templates.TemplateResponse("compliance.html", {
        "request": request,
        "has_data": len(graph.components) > 0,
    })


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    return templates.TemplateResponse("reports.html", {
        "request": request,
        "has_data": _last_report is not None,
    })


@app.get("/report/executive", response_class=HTMLResponse)
async def executive_report(company_name: str = "Your Organization"):
    """Generate executive report (printable HTML).

    Returns a self-contained HTML report designed for C-suite audiences.
    Print to PDF via browser (Ctrl+P) or wkhtmltopdf.
    """
    global _last_report
    graph = get_graph()
    if not graph.components:
        return HTMLResponse(
            "<html><body><h1>No infrastructure loaded.</h1>"
            "<p>Visit /demo first to load a demo infrastructure.</p></body></html>",
            status_code=400,
        )

    # Run simulation if not already done
    if _last_report is None:
        engine = SimulationEngine(graph)
        _last_report = engine.run_all_defaults()

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


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "has_data": True,
    })


@app.get("/blast-radius", response_class=HTMLResponse)
async def blast_radius_page(request: Request):
    """Interactive blast radius visualizer."""
    return templates.TemplateResponse("blast_radius.html", {
        "request": request,
        "has_data": len(get_graph().components) > 0,
    })


@app.get("/api/topology", response_class=JSONResponse)
async def get_topology(user=Depends(_require_permission("view_results"))):
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
        # Determine risk level
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


@app.post("/api/simulate-failure/{component_id}", response_class=JSONResponse)
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
    # Wave 0 = direct failure, then group by time buckets
    waves: list[dict] = []
    if chain.effects:
        # Wave 0: the directly failed component
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

        # Sort remaining by estimated_time_seconds for wave ordering
        remaining.sort(key=lambda e: e.estimated_time_seconds)

        # Group into waves by time buckets
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

    # Estimate recovery time based on severity
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
# Incident Replay API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/incidents", response_class=JSONResponse)
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


@app.post("/api/replay/{incident_id}", response_class=JSONResponse)
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
# htmx fragment endpoints
# ---------------------------------------------------------------------------

@app.get("/htmx/score-cards", response_class=HTMLResponse)
async def htmx_score_cards(request: Request):
    """Dashboard score-card HTML fragment (htmx partial)."""
    graph = get_graph()
    summary = graph.summary()

    report_data = None
    if _last_report is not None:
        report_data = _report_to_dict(_last_report)

    return templates.TemplateResponse("fragments/score_cards.html", {
        "request": request,
        "summary": summary,
        "report": report_data,
    })


@app.get("/htmx/risk-table", response_class=HTMLResponse)
async def htmx_risk_table(request: Request):
    """Risk table HTML fragment (htmx partial)."""
    report_data = None
    if _last_report is not None:
        report_data = _report_to_dict(_last_report)

    return templates.TemplateResponse("fragments/risk_table.html", {
        "request": request,
        "report": report_data,
    })


# ---------------------------------------------------------------------------
# New JSON API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/score-history", response_class=JSONResponse)
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


@app.get("/api/compliance/{framework}", response_class=JSONResponse)
async def api_compliance_check(
    framework: str,
    user=Depends(_require_permission("view_results")),
):
    """Return compliance check results for the given framework.

    Supported frameworks: soc2, pci-dss, hipaa, iso27001.
    Returns mock data until a full compliance engine is implemented.
    """
    graph = get_graph()
    if not graph.components:
        return JSONResponse(
            {"error": "No infrastructure loaded. Visit /demo first."},
            status_code=400,
        )

    supported = {"soc2", "pci-dss", "hipaa", "iso27001"}
    if framework not in supported:
        return JSONResponse(
            {"error": f"Unsupported framework: {framework}. Supported: {sorted(supported)}"},
            status_code=400,
        )

    # Evaluate basic compliance signals from component tags and security profiles
    checks: list[dict] = []
    for comp in graph.components.values():
        sec = comp.security
        ct = comp.compliance_tags

        check = {
            "component_id": comp.id,
            "component_name": comp.name,
            "encryption_at_rest": sec.encryption_at_rest,
            "encryption_in_transit": sec.encryption_in_transit,
            "audit_logging": ct.audit_logging,
            "backup_enabled": sec.backup_enabled,
            "data_classification": ct.data_classification,
        }

        if framework == "pci-dss":
            check["pci_scope"] = ct.pci_scope
            check["waf_protected"] = sec.waf_protected
            check["network_segmented"] = sec.network_segmented
        elif framework == "hipaa":
            check["contains_phi"] = ct.contains_phi
            check["access_control"] = sec.auth_required
        elif framework == "soc2":
            check["change_management"] = ct.change_management
            check["monitoring"] = sec.log_enabled
        elif framework == "iso27001":
            check["ids_monitored"] = sec.ids_monitored
            check["patch_sla_hours"] = sec.patch_sla_hours

        checks.append(check)

    # Compute an overall compliance ratio
    total_checks = 0
    passed_checks = 0
    for check in checks:
        for key, val in check.items():
            if key in ("component_id", "component_name", "data_classification",
                       "patch_sla_hours"):
                continue
            total_checks += 1
            if val is True:
                passed_checks += 1

    compliance_pct = (
        round(passed_checks / total_checks * 100, 1)
        if total_checks > 0
        else 0.0
    )

    return JSONResponse({
        "framework": framework,
        "compliance_percent": compliance_pct,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "components": checks,
    })


# ---------------------------------------------------------------------------
# Industry Benchmarking endpoint
# ---------------------------------------------------------------------------

@app.get("/api/benchmark/{industry}", response_class=JSONResponse)
async def benchmark_industry(
    industry: str,
    user=Depends(_require_permission("view_results")),
):
    """Benchmark infrastructure against industry peers.

    Compare your infrastructure's resilience against anonymized industry
    benchmarks for fintech, saas, healthcare, and other verticals.
    Use ``industry=all`` to compare across all industries.
    """
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
# Slack Bot endpoint
# ---------------------------------------------------------------------------

@app.post("/api/slack/commands", response_class=JSONResponse)
async def slack_command_handler(request: Request):
    """Handle Slack slash commands for FaultRay.

    Expected form data from Slack:
        text: "simulate", "score", "trend", "help"
        user_id: Slack user ID
        channel_id: Slack channel ID
    """
    try:
        # Slack sends form-encoded data
        try:
            form = await request.form()
            text = form.get("text", "help")
            user_id = form.get("user_id", "")
            channel_id = form.get("channel_id", "")
        except Exception:
            # Fallback to JSON body (for testing / non-Slack callers)
            try:
                body = await request.json()
            except Exception:
                body = {}
            text = body.get("text", "help")
            user_id = body.get("user_id", "")
            channel_id = body.get("channel_id", "")

        from faultray.integrations.slack_bot import FaultRaySlackBot, parse_slack_command

        # Use the currently loaded graph's model path if available
        model_path = _model_path

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
# API versioning — mount v1 prefix (backward-compatible dual-mount)
# ---------------------------------------------------------------------------

from fastapi import APIRouter as _APIRouter

_v1_router = _APIRouter(prefix="/api/v1")


@_v1_router.get("/graph-data", response_class=JSONResponse)
async def v1_graph_data(user=Depends(_require_permission("view_results"))):
    return await api_graph_data(user)


@_v1_router.post("/simulate", response_class=JSONResponse)
async def v1_simulate(request: Request, user=Depends(_require_permission("run_simulation"))):
    return await api_simulate(request, user)


@_v1_router.get("/runs", response_class=JSONResponse)
async def v1_list_runs(
    limit: int = 50,
    offset: int = 0,
    project_id: int | None = None,
    user=Depends(_require_permission("view_results")),
):
    return await list_runs(limit, offset, project_id, user)


@_v1_router.get("/runs/{run_id}", response_class=JSONResponse)
async def v1_get_run(run_id: int, user=Depends(_require_permission("view_results"))):
    return await get_run(run_id, user)


@_v1_router.get("/analyze", response_class=JSONResponse)
async def v1_analyze(user=Depends(_require_permission("view_results"))):
    return await api_analyze(user)


@_v1_router.get("/projects", response_class=JSONResponse)
async def v1_list_projects(user=Depends(_require_permission("view_results"))):
    return await list_projects(user)


@_v1_router.get("/score-history", response_class=JSONResponse)
async def v1_score_history(limit: int = 30, user=Depends(_require_permission("view_results"))):
    return await api_score_history(limit, user)


@_v1_router.get("/compliance/{framework}", response_class=JSONResponse)
async def v1_compliance(framework: str, user=Depends(_require_permission("view_results"))):
    return await api_compliance_check(framework, user)


# ---------------------------------------------------------------------------
# Marketplace API endpoints
# ---------------------------------------------------------------------------


@app.get("/api/marketplace/packages", response_class=JSONResponse)
async def list_marketplace_packages(
    category: str | None = None,
    provider: str | None = None,
):
    """List all marketplace packages, optionally filtered by category/provider."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    packages = mp.list_packages(category=category, provider=provider)
    return JSONResponse({"packages": [p.to_dict() for p in packages]})


@app.get("/api/marketplace/packages/{package_id}", response_class=JSONResponse)
async def get_marketplace_package(package_id: str):
    """Get a specific marketplace package by ID."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    try:
        pkg = mp.get_package(package_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Package not found: {package_id}")
    return JSONResponse(pkg.to_dict())


@app.post("/api/marketplace/install/{package_id}", response_class=JSONResponse)
async def install_marketplace_package(package_id: str):
    """Install a marketplace package (convert scenarios to FaultRay format)."""
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


@app.get("/api/marketplace/featured", response_class=JSONResponse)
async def get_featured_packages():
    """Get featured/curated marketplace packages."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    featured = mp.get_featured()
    return JSONResponse({"packages": [p.to_dict() for p in featured]})


@app.get("/api/marketplace/categories", response_class=JSONResponse)
async def get_marketplace_categories():
    """Get all marketplace categories with package counts."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    categories = mp.get_categories()
    return JSONResponse({"categories": [c.to_dict() for c in categories]})


@app.get("/api/marketplace/popular", response_class=JSONResponse)
async def get_popular_packages():
    """Get most popular marketplace packages by downloads."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    popular = mp.get_popular()
    return JSONResponse({"packages": [p.to_dict() for p in popular]})


@app.get("/api/marketplace/search", response_class=JSONResponse)
async def search_marketplace_packages(q: str = ""):
    """Search marketplace packages by query."""
    from faultray.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()
    results = mp.search(q)
    return JSONResponse({"packages": [p.to_dict() for p in results]})


@app.get("/marketplace", response_class=HTMLResponse)
async def marketplace_page(request: Request):
    """Marketplace HTML page."""
    graph = get_graph()
    has_data = bool(graph and graph.components)
    return templates.TemplateResponse("marketplace.html", {
        "request": request,
        "has_data": has_data,
        "active_page": "marketplace",
    })


# ---------------------------------------------------------------------------
# Conversational Infrastructure Chat
# ---------------------------------------------------------------------------

@app.get("/chat", response_class=HTMLResponse)
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


@app.post("/api/chat", response_class=JSONResponse)
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
# Resilience Badge endpoints
# ---------------------------------------------------------------------------

@app.get("/badge/{badge_type}.svg")
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
        # Default to resilience
        svg = gen.generate_resilience_badge(graph, badge_style)

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/badge/all")
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


@app.get("/api/badge-markdown")
async def get_badge_markdown(base_url: str = "http://localhost:8000"):
    """Return markdown to embed badges in README."""
    from faultray.api.badge_generator import BadgeGenerator

    gen = BadgeGenerator()
    return JSONResponse({
        "markdown": gen.get_markdown_links(base_url),
    })


# ---------------------------------------------------------------------------
# Chaos Calendar endpoints
# ---------------------------------------------------------------------------

@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):
    """Chaos Calendar page — schedule and track chaos experiments."""
    graph = get_graph()
    return templates.TemplateResponse("calendar.html", {
        "request": request,
        "has_data": len(graph.components) > 0,
        "active_page": "calendar",
    })


@app.get("/api/calendar", response_class=JSONResponse)
async def api_calendar_view():
    """Return calendar view JSON with experiments, stats, and blackout windows."""
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


@app.post("/api/calendar/schedule", response_class=JSONResponse)
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


@app.delete("/api/calendar/{experiment_id}", response_class=JSONResponse)
async def api_calendar_cancel(experiment_id: str):
    """Cancel a scheduled experiment."""
    from faultray.scheduler.chaos_calendar import ChaosCalendar

    cal = ChaosCalendar()
    success = cal.cancel(experiment_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    return JSONResponse({"experiment_id": experiment_id, "status": "cancelled"})


@app.post("/api/calendar/auto-schedule", response_class=JSONResponse)
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


@app.get("/api/calendar/ical")
async def api_calendar_ical():
    """Download iCalendar (.ics) file for import into Google Calendar, Outlook, etc."""
    from faultray.scheduler.chaos_calendar import ChaosCalendar

    cal = ChaosCalendar()
    ical = cal.export_ical()
    return Response(
        content=ical,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=chaos-calendar.ics"},
    )


# ---------------------------------------------------------------------------
# Risk Heat Map
# ---------------------------------------------------------------------------


@app.get("/heatmap", response_class=HTMLResponse)
async def heatmap_page(request: Request):
    """Interactive risk heat map page."""
    graph = get_graph()
    return templates.TemplateResponse("heatmap.html", {
        "request": request,
        "has_data": len(graph.components) > 0,
        "active_page": "heatmap",
    })


@app.get("/api/risk-heatmap", response_class=JSONResponse)
async def api_risk_heatmap(user=Depends(_require_permission("view_results"))):
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


@app.get("/cost-attribution", response_class=HTMLResponse)
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

    return templates.TemplateResponse("cost_attribution.html", {
        "request": request,
        "has_data": len(graph.components) > 0,
        "active_page": "cost_attribution",
        "report": report_data,
    })


@app.get("/api/cost-attribution", response_class=JSONResponse)
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
# Topology Diff endpoints
# ---------------------------------------------------------------------------


@app.get("/topology-diff", response_class=HTMLResponse)
async def topology_diff_page(request: Request):
    """Topology Diff page - compare two infrastructure YAML files."""
    return templates.TemplateResponse("topology_diff.html", {
        "request": request,
        "has_data": True,  # Always accessible (uses file upload)
        "active_page": "topology_diff",
    })


@app.post("/api/topology-diff")
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

        # Write to temp files for the loader
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

        # Cleanup temp files
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
# What-If Analysis endpoints
# ---------------------------------------------------------------------------


@app.get("/whatif", response_class=HTMLResponse)
async def whatif_page(request: Request):
    """Interactive what-if analysis page."""
    graph = get_graph()
    return templates.TemplateResponse("whatif.html", {
        "request": request,
        "has_data": len(graph.components) > 0,
        "active_page": "whatif",
    })


@app.get("/api/whatif/components")
async def whatif_components():
    """Return current components with their parameters for the what-if UI."""
    graph = get_graph()
    if not graph.components:
        return JSONResponse({"components": {}, "baseline_score": 0, "spof_count": 0})

    components = {}
    for comp_id, comp in graph.components.items():
        # Check if any edge targeting this component has circuit breakers
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

    # Count SPOFs
    spof_count = 0
    for comp in graph.components.values():
        dependents = graph.get_dependents(comp.id)
        if comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled:
            spof_count += 1

    # Availability estimate
    avail = _estimate_availability(score)

    # Recommendations from v2 score
    v2 = graph.resilience_score_v2()
    recs = v2.get("recommendations", [])[:5]

    return JSONResponse({
        "components": components,
        "baseline_score": round(score, 1),
        "spof_count": spof_count,
        "availability_estimate": avail,
        "recommendations": recs,
    })


@app.post("/api/whatif/calculate")
async def whatif_calculate(request: Request):
    """Calculate resilience for modified parameters.

    Body: {"modifications": {"component_id": {"replicas": 3, "circuit_breaker": true, ...}}}
    Returns: {"resilience_score": 85.0, "delta": +12.5, "spof_count": 0, ...}
    """
    import copy

    graph = get_graph()
    if not graph.components:
        return JSONResponse({"error": "No infrastructure loaded"}, status_code=400)

    body = await request.json()
    modifications = body.get("modifications", {})

    baseline_score = graph.resilience_score()

    # Create a deep copy and apply modifications
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
            # Apply circuit breaker to all edges targeting this component
            for u, v, data in modified_graph._graph.edges(data=True):
                dep = data.get("dependency")
                if dep and dep.target_id == comp_id:
                    dep.circuit_breaker.enabled = bool(mods["circuit_breaker"])

    new_score = modified_graph.resilience_score()
    delta = round(new_score - baseline_score, 1)

    # Count SPOFs in modified graph
    spof_count = 0
    for comp in modified_graph.components.values():
        dependents = modified_graph.get_dependents(comp.id)
        if comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled:
            spof_count += 1

    avail = _estimate_availability(new_score)

    # Get updated recommendations
    v2 = modified_graph.resilience_score_v2()
    recs = v2.get("recommendations", [])[:5]

    return JSONResponse({
        "resilience_score": round(new_score, 1),
        "delta": delta,
        "spof_count": spof_count,
        "availability_estimate": avail,
        "recommendations": recs,
    })


@app.post("/api/whatif/export")
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

    # Convert to YAML
    export_dict = modified_graph.to_dict()
    yaml_content = yaml.dump(export_dict, default_flow_style=False, allow_unicode=True)

    return Response(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={"Content-Disposition": "attachment; filename=whatif-modified.yaml"},
    )


def _estimate_availability(score: float) -> str:
    """Estimate availability nines from resilience score."""
    if score >= 95:
        return "99.99"
    elif score >= 85:
        return "99.95"
    elif score >= 75:
        return "99.9"
    elif score >= 60:
        return "99.5"
    elif score >= 40:
        return "99.0"
    else:
        return "95.0"


# ---------------------------------------------------------------------------
# Pareto Optimizer routes
# ---------------------------------------------------------------------------


@app.get("/optimizer", response_class=HTMLResponse)
async def optimizer_page(request: Request):
    """Pareto Optimizer page."""
    graph = get_graph()
    return templates.TemplateResponse("optimizer.html", {
        "request": request,
        "has_data": bool(graph and graph.components),
        "active_page": "optimizer",
    })


@app.get("/api/optimize", response_class=JSONResponse)
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
# Anomaly Detection routes
# ---------------------------------------------------------------------------


@app.get("/anomaly", response_class=HTMLResponse)
async def anomaly_page(request: Request):
    """Anomaly Detection page."""
    graph = get_graph()
    return templates.TemplateResponse("anomaly.html", {
        "request": request,
        "has_data": bool(graph and graph.components),
        "active_page": "anomaly",
    })


@app.get("/api/anomalies", response_class=JSONResponse)
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
# API v1 typed routes (OpenAPI schema with Pydantic models)
# Must be included before _v1_router so typed routes take precedence
# ---------------------------------------------------------------------------
app.include_router(v1_router)

app.include_router(_v1_router)


# ---------------------------------------------------------------------------
# API Documentation page
# ---------------------------------------------------------------------------

@app.get("/api-docs", response_class=HTMLResponse)
async def api_docs_page(request: Request):
    """Interactive API documentation."""
    return templates.TemplateResponse("api_docs.html", {
        "request": request,
    })


# ---------------------------------------------------------------------------
# API Health, Versioning & Dashboard Summary (v2)
# ---------------------------------------------------------------------------

@app.get("/api/health", response_class=JSONResponse)
async def health_check():
    """Return API health status, version, uptime, and component count."""
    from faultray.api.api_versioning import health_checker

    graph = get_graph()
    component_count = len(graph.components) if graph else 0
    return JSONResponse(health_checker.check(component_count))


@app.get("/api/versions", response_class=JSONResponse)
async def api_versions():
    """List available API versions and their lifecycle status."""
    from faultray.api.api_versioning import list_versions

    return JSONResponse({"versions": list_versions()})


@app.get("/api/dashboard/summary", response_class=JSONResponse)
async def dashboard_summary():
    """Aggregated dashboard data for the enhanced V2 dashboard."""
    graph = get_graph()
    summary = graph.summary()

    # Resilience score
    res_score = summary.get("resilience_score", 0)

    # SLA estimate
    sla = _estimate_availability(res_score)

    # SPOF count
    spof_count = 0
    for comp in graph.components.values():
        dependents = graph.get_dependents(comp.id)
        if comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled:
            spof_count += 1

    # SRE Maturity heuristic (L1-L5 based on resilience features)
    total_comps = max(len(graph.components), 1)

    failover_count = sum(1 for c in graph.components.values() if c.failover.enabled)
    autoscale_count = sum(1 for c in graph.components.values() if c.autoscaling.enabled)
    monitoring_count = sum(
        1 for c in graph.components.values()
        if c.failover.health_check_interval_seconds > 0
    )

    # Count circuit breakers across edges
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

    # Risk distribution from last report
    risk_dist = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    if _last_report is not None:
        report_d = _report_to_dict(_last_report)
        risk_dist["critical"] = report_d.get("critical_count", 0)
        risk_dist["high"] = report_d.get("warning_count", 0)
        risk_dist["low"] = report_d.get("passed_count", 0)

    # Component breakdown
    comp_breakdown = summary.get("component_types", {})

    # Compliance scores (lightweight from available data)
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

    # Recent activity from last report
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

    # Sparkline (simplified trend indicator)
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
# Template Gallery routes
# ---------------------------------------------------------------------------

@app.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request, category: str | None = None):
    """Render the Template Gallery page."""
    from dataclasses import asdict

    from faultray.templates.gallery import TemplateGallery, TemplateCategory

    gallery = TemplateGallery()
    gallery_templates = gallery.list_templates(category=category)
    categories = [c.value for c in TemplateCategory]

    template_data = [asdict(t) for t in gallery_templates]
    # Add category enum value for filtering
    for td in template_data:
        td["category_value"] = td["category"]

    return templates.TemplateResponse("gallery.html", {
        "request": request,
        "has_data": True,
        "gallery_templates": template_data,
        "categories": categories,
        "active_category": category,
    })


@app.get("/api/templates", response_class=JSONResponse)
async def api_list_templates(category: str | None = None):
    """List all gallery templates as JSON."""
    from dataclasses import asdict

    from faultray.templates.gallery import TemplateGallery

    gallery = TemplateGallery()
    gallery_templates = gallery.list_templates(category=category)
    return JSONResponse([asdict(t) for t in gallery_templates])


@app.get("/api/templates/{template_id}", response_class=JSONResponse)
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
# FMEA Analysis routes
# ---------------------------------------------------------------------------

@app.get("/fmea", response_class=HTMLResponse)
async def fmea_page(request: Request):
    """FMEA (Failure Mode & Effects Analysis) dashboard."""
    graph = get_graph()
    return templates.TemplateResponse("fmea.html", {
        "request": request,
        "has_data": bool(graph.components),
        "active_page": "fmea",
    })


@app.get("/api/fmea", response_class=JSONResponse)
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
# Chaos Monkey routes
# ---------------------------------------------------------------------------

@app.get("/chaos-monkey", response_class=HTMLResponse)
async def chaos_monkey_page(request: Request):
    """Chaos Monkey dashboard."""
    graph = get_graph()
    return templates.TemplateResponse("chaos_monkey.html", {
        "request": request,
        "has_data": bool(graph.components),
        "active_page": "chaos_monkey",
    })


@app.post("/api/chaos-monkey", response_class=JSONResponse)
async def api_chaos_monkey(request: Request):
    """Run a Chaos Monkey experiment and return results."""
    from faultray.simulator.chaos_monkey import ChaosLevel, ChaosMonkey, ChaosMonkeyConfig

    graph = get_graph()

    # Parse params from form data or query string
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
# Attack Surface Analysis
# ---------------------------------------------------------------------------

@app.get("/attack-surface", response_class=HTMLResponse)
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

    return templates.TemplateResponse("attack_surface.html", {
        "request": request,
        "has_data": has_data,
        "report": report_data,
    })


@app.get("/api/attack-surface", response_class=JSONResponse)
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
# Score Decomposition
# ---------------------------------------------------------------------------

@app.get("/score-explain", response_class=HTMLResponse)
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

    return templates.TemplateResponse("score_explain.html", {
        "request": request,
        "has_data": has_data,
        "decomposition": decomposition_data,
    })


@app.get("/api/score-decomposition", response_class=JSONResponse)
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
# Agent Assessment
# ---------------------------------------------------------------------------

@app.get("/agents", response_class=HTMLResponse)
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


@app.post("/api/v1/agent/assess", response_class=JSONResponse)
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


@app.post("/api/v1/agent/monitor", response_class=JSONResponse)
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


@app.post("/api/v1/agent/scenarios", response_class=JSONResponse)
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

@app.get("/supply-chain", response_class=HTMLResponse)
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


@app.post("/api/v1/supply-chain/analyze", response_class=JSONResponse)
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
