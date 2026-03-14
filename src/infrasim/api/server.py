"""FastAPI web dashboard for ChaosProof."""

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
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from infrasim.model.graph import InfraGraph
from infrasim.simulator.engine import SimulationEngine

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
_last_report = None

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Lifespan — initialise database on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialise the database and optional Prometheus monitor on startup."""
    from infrasim.api.database import init_db
    try:
        await init_db()
        logger.info("ChaosProof database initialised.")
    except Exception:
        logger.warning("Database initialisation skipped (aiosqlite may not be installed).")

    # Start Prometheus background monitor if configured
    _prom_monitor = None
    prom_url = os.environ.get("CHAOSPROOF_PROMETHEUS_URL", os.environ.get("INFRASIM_PROMETHEUS_URL"))
    if prom_url:
        try:
            from infrasim.discovery.prometheus_monitor import PrometheusMonitor

            interval = int(os.environ.get("CHAOSPROOF_PROMETHEUS_INTERVAL", os.environ.get("INFRASIM_PROMETHEUS_INTERVAL", "60")))
            _prom_monitor = PrometheusMonitor(prom_url, get_graph(), interval)
            await _prom_monitor.start()
            logger.info("Prometheus monitor started: %s (interval=%ds)", prom_url, interval)
        except Exception:
            logger.warning("Could not start Prometheus monitor.", exc_info=True)

    yield

    # Shutdown Prometheus monitor
    if _prom_monitor is not None:
        await _prom_monitor.stop()


app = FastAPI(
    title="ChaosProof API",
    description="Zero-risk infrastructure chaos engineering platform — simulate failures without touching production",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS middleware — origins configurable via CHAOSPROOF_CORS_ORIGINS env var
# ---------------------------------------------------------------------------
_cors_origins_raw = os.environ.get("CHAOSPROOF_CORS_ORIGINS", os.environ.get("INFRASIM_CORS_ORIGINS", "*"))
_cors_origins: list[str] = [
    origin.strip()
    for origin in _cors_origins_raw.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Rate-limiting middleware for /api/* routes
# ---------------------------------------------------------------------------

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Enforce rate limiting on /api/* endpoints."""
    if request.url.path.startswith("/api"):
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
from infrasim.api.insurance_api import insurance_router

app.include_router(insurance_router)


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

    Delegates to the shared helper in :mod:`infrasim.model.demo` so that
    CLI ``demo`` command and the web dashboard use identical data.
    """
    from infrasim.model.demo import create_demo_graph

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
        from infrasim.api.database import SimulationRunRow, get_session_factory

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
        from infrasim.api.auth import get_current_user
        from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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
            from infrasim.api.auth import require_permission
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

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "summary": summary,
        "has_data": len(graph.components) > 0,
        "report": report_data,
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
        from infrasim.ai.analyzer import InfraSimAnalyzer
        import dataclasses

        analyzer = InfraSimAnalyzer()
        ai_report = analyzer.analyze(graph, _last_report)

        # Convert to template-friendly dict
        analysis_data = dataclasses.asdict(ai_report)

    return templates.TemplateResponse("analyze.html", {
        "request": request,
        "has_data": has_data,
        "analysis": analysis_data,
    })


# ---------------------------------------------------------------------------
# JSON API routes
# ---------------------------------------------------------------------------

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

    from infrasim.ai.analyzer import InfraSimAnalyzer
    import dataclasses

    analyzer = InfraSimAnalyzer()
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
        from infrasim.api.database import get_session_factory, log_audit

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
        from infrasim.api.database import (
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
        from infrasim.api.database import SimulationRunRow, get_session_factory
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
        from infrasim.api.database import SimulationRunRow, get_session_factory, log_audit
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
        from infrasim.api.database import ProjectRow, get_session_factory, log_audit

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
        from infrasim.api.database import ProjectRow, get_session_factory
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
        from infrasim.api.database import AuditLog, get_session_factory
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

    Only active when ``CHAOSPROOF_OAUTH_{PROVIDER}_CLIENT_ID`` and
    ``CHAOSPROOF_OAUTH_{PROVIDER}_CLIENT_SECRET`` env vars are set.
    """
    from infrasim.api.oauth import OAuthConfig, generate_oauth_url

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
    from infrasim.api.oauth import OAuthConfig, exchange_code_for_token, get_user_profile

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
        from infrasim.api.auth import generate_api_key, hash_api_key
        from infrasim.api.database import UserRow, get_session_factory
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


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "has_data": True,
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
        from infrasim.api.database import SimulationRunRow, get_session_factory
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


app.include_router(_v1_router)
