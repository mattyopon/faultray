# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""FastAPI web dashboard for FaultRay.

This module creates the FastAPI application, configures middleware
(CORS, rate limiting, auth), and registers all route modules.
Route handlers live in ``faultray.api.routes.*``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limiter — lightweight in-memory implementation
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple in-memory rate limiter using a sliding window."""

    MAX_KEYS = 10_000  # prevent unbounded memory growth

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _cleanup(self) -> None:
        """Remove expired entries; evict LRU entries when MAX_KEYS is exceeded."""
        now = time.time()
        cutoff = now - self.window
        expired = [k for k, v in self.requests.items() if not v or v[-1] < cutoff]
        for k in expired:
            del self.requests[k]
        # LRU eviction when still over the limit after expiry cleanup
        if len(self.requests) > self.MAX_KEYS:
            sorted_keys = sorted(
                self.requests.keys(),
                key=lambda k: self.requests[k][-1] if self.requests[k] else 0.0,
            )
            for k in sorted_keys[: len(self.requests) - self.MAX_KEYS]:
                del self.requests[k]

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        with self._lock:
            self.requests[client_id] = [
                t for t in self.requests[client_id] if now - t < self.window
            ]
            if len(self.requests[client_id]) >= self.max_requests:
                return False
            self.requests[client_id].append(now)
            # Periodic cleanup to prevent unbounded memory growth
            if len(self.requests) > self.MAX_KEYS:
                self._cleanup()
            return True


_rate_limiter = RateLimiter()

# ---------------------------------------------------------------------------
# Module-level state  (accessed by route modules via getter/setter functions)
# ---------------------------------------------------------------------------
_graph: InfraGraph | None = None
_model_path: Path | None = None
_last_report = None

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# State accessor functions  (used by route modules and external consumers)
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
    """Build the demo infrastructure graph."""
    from faultray.model.demo import create_demo_graph

    return create_demo_graph()


def _report_to_dict(report) -> dict:
    """Convert a SimulationReport to a JSON-serialisable dict."""
    from faultray.api.routes._shared import _report_to_dict as _impl
    return _impl(report)


async def _save_run(report_dict: dict, engine_type: str = "static") -> int | None:
    """Persist a simulation run to the database. Returns the row id or None."""
    from faultray.api.routes._shared import _save_run as _impl
    return await _impl(report_dict, engine_type)


def _estimate_availability(score: float) -> str:
    """Estimate availability nines from resilience score."""
    from faultray.api.routes._shared import _estimate_availability as _impl
    return _impl(score)


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
    """Lazy wrapper around auth.require_permission (opt-in RBAC)."""
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
    prom_url = os.environ.get("FAULTRAY_PROMETHEUS_URL", os.environ.get("PROMETHEUS_URL"))
    if prom_url:
        try:
            from faultray.discovery.prometheus_monitor import PrometheusMonitor

            interval = int(os.environ.get("FAULTRAY_PROMETHEUS_INTERVAL", os.environ.get("PROMETHEUS_INTERVAL", "60")))
            _prom_monitor = PrometheusMonitor(prom_url, get_graph(), interval)
            await _prom_monitor.start()
            logger.info("Prometheus monitor started: %s (interval=%ds)", prom_url, interval)
        except Exception:
            logger.warning("Could not start Prometheus monitor.", exc_info=True)

    yield

    # Shutdown Prometheus monitor
    if _prom_monitor is not None:
        await _prom_monitor.stop()


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


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

_allow_credentials = bool(_cors_origins) and _cors_origins != ["*"]

_cors_methods: list[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"]
_cors_headers: list[str] = ["Authorization", "Content-Type", "X-Requested-With", "Accept"]

if _allow_credentials:
    if "*" in _cors_origins:
        raise ValueError("allow_origins must not contain '*' when credentials are enabled")
    if "*" in _cors_methods:
        raise ValueError("allow_methods must not contain '*' when credentials are enabled")
    if "*" in _cors_headers:
        raise ValueError("allow_headers must not contain '*' when credentials are enabled")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=_cors_methods,
    allow_headers=_cors_headers,
)

# Session middleware — used by Web UI OAuth flow (HTTP-only cookie session)
# Bearer token auth is unaffected by this middleware.
_is_production = os.environ.get("FAULTRAY_ENV", "development") == "production"
_session_secret = (
    os.environ.get("FAULTRAY_SESSION_SECRET")
    or os.environ.get("JWT_SECRET_KEY")
    or ""
)
if not _session_secret:
    if _is_production:
        raise RuntimeError("FAULTRAY_SESSION_SECRET must be set in production")
    _session_secret = "faultray-dev-session-key"  # default dev-only value
    logger.warning(
        "Using default session secret — set FAULTRAY_SESSION_SECRET or JWT_SECRET_KEY for production"
    )
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    https_only=_is_production,
    same_site="lax",
)


# ---------------------------------------------------------------------------
# Rate-limiting middleware for /api/* routes
# ---------------------------------------------------------------------------

# Trusted proxy IPs whose X-Forwarded-For header will be honored.
# Set FAULTRAY_TRUSTED_PROXIES to a comma-separated list of IPs (e.g. "127.0.0.1,10.0.0.1").
# If empty, X-Forwarded-For is never trusted.
_trusted_proxies: set[str] = {
    ip.strip()
    for ip in os.environ.get("FAULTRAY_TRUSTED_PROXIES", "").split(",")
    if ip.strip()
}


def _get_client_ip(request: Request) -> str:
    """Return the real client IP, respecting X-Forwarded-For only from trusted proxies."""
    direct_ip = request.client.host if request.client else "unknown"
    if _trusted_proxies and direct_ip in _trusted_proxies:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return direct_ip


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Enforce rate limiting on all endpoints."""
    client_ip = _get_client_ip(request)
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
# Static files
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Router registration — existing external routers
# ---------------------------------------------------------------------------

from faultray.api.insurance_api import insurance_router

app.include_router(insurance_router)

from faultray.api.widget import widget_router

app.include_router(widget_router)

from faultray.api.graphql_api import graphql_router

app.include_router(graphql_router)

from faultray.api.teams import teams_router

app.include_router(teams_router)

from faultray.api.leaderboard import leaderboard_router

app.include_router(leaderboard_router)

# APM Collector routes
from faultray.apm.collector import apm_router

app.include_router(apm_router)

# Meta API routes (action-based dispatchers for E2E compatibility)
from faultray.api.routes.meta import router as meta_router

app.include_router(meta_router)


# ---------------------------------------------------------------------------
# Stripe Billing routes (inline because they use module-level _stripe_mgr)
# ---------------------------------------------------------------------------

from faultray.api.billing import (
    PricingTier as _PricingTier,
    TIER_LIMITS as _TIER_LIMITS,
    StripeManager as _StripeManager,
    UsageTracker as _UsageTracker,
)

_stripe_mgr = _StripeManager()


@app.post("/api/billing/checkout", response_class=JSONResponse)
async def billing_checkout(request: Request, user=Depends(_require_permission("manage_billing"))):
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
async def billing_portal(request: Request, team_id: str = "", user=Depends(_require_permission("manage_billing"))):
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
async def billing_usage(team_id: str = "", user=Depends(_require_permission("view_results"))):
    """Return current usage stats and tier information for a team."""
    if not team_id:
        return JSONResponse({"error": "team_id query parameter is required"}, status_code=400)

    tracker = _UsageTracker(db_session_factory=None)
    usage = await tracker.get_usage(team_id)

    graph = get_graph()
    usage["component_count"] = len(graph.components) if graph and graph.components else 0

    usage["stripe_enabled"] = _stripe_mgr.enabled
    if _stripe_mgr.enabled:
        sub = await _stripe_mgr.get_subscription(team_id)
        usage["subscription"] = sub

    return JSONResponse(usage)


@app.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request):
    """Billing management page."""
    return templates.TemplateResponse(request, "billing.html", {
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


# ---------------------------------------------------------------------------
# Router registration — refactored route modules
# ---------------------------------------------------------------------------

from faultray.api.routes.dashboard import router as dashboard_router
from faultray.api.routes.simulation import router as simulation_router
from faultray.api.routes.graph import router as graph_router
from faultray.api.routes.compliance import router as compliance_router
from faultray.api.routes.projects import router as projects_router
from faultray.api.routes.admin import router as admin_router
from faultray.api.routes.badge import router as badge_router

app.include_router(dashboard_router)
app.include_router(simulation_router)
app.include_router(graph_router)
app.include_router(compliance_router)
app.include_router(projects_router)
app.include_router(admin_router)
app.include_router(badge_router)


# ---------------------------------------------------------------------------
# API versioning — v1 prefix (backward-compatible dual-mount)
# ---------------------------------------------------------------------------

from fastapi import APIRouter as _APIRouter

_v1_router = _APIRouter(prefix="/api/v1")


@_v1_router.get("/graph-data", response_class=JSONResponse)
async def v1_graph_data():
    from faultray.api.routes.graph import api_graph_data
    return await api_graph_data()


@_v1_router.post("/simulate", response_class=JSONResponse)
async def v1_simulate(request: Request, user=Depends(_require_permission("run_simulation"))):
    from faultray.api.routes.simulation import api_simulate
    return await api_simulate(request, user)


@_v1_router.get("/runs", response_class=JSONResponse)
async def v1_list_runs(
    limit: int = 50,
    offset: int = 0,
    project_id: int | None = None,
    user=Depends(_require_permission("view_results")),
):
    from faultray.api.routes.projects import list_runs
    return await list_runs(limit, offset, project_id, user)


@_v1_router.get("/runs/{run_id}", response_class=JSONResponse)
async def v1_get_run(run_id: int, user=Depends(_require_permission("view_results"))):
    from faultray.api.routes.projects import get_run
    return await get_run(run_id, user)


@_v1_router.get("/analyze", response_class=JSONResponse)
async def v1_analyze(user=Depends(_require_permission("view_results"))):
    from faultray.api.routes.simulation import api_analyze
    return await api_analyze(user)


@_v1_router.get("/projects", response_class=JSONResponse)
async def v1_list_projects(user=Depends(_require_permission("view_results"))):
    from faultray.api.routes.projects import list_projects
    return await list_projects(user)


@_v1_router.get("/score-history", response_class=JSONResponse)
async def v1_score_history(limit: int = 30, user=Depends(_require_permission("view_results"))):
    from faultray.api.routes.dashboard import api_score_history
    return await api_score_history(limit, user)


@_v1_router.get("/compliance/{framework}", response_class=JSONResponse)
async def v1_compliance(framework: str, user=Depends(_require_permission("view_results"))):
    from faultray.api.routes.compliance import api_compliance_check
    return await api_compliance_check(framework, user)


# ---------------------------------------------------------------------------
# API v1 typed routes (OpenAPI schema with Pydantic models)
# Must be included before _v1_router so typed routes take precedence
# ---------------------------------------------------------------------------

from faultray.api.v1.saas_routes import saas_router

app.include_router(v1_router)
app.include_router(saas_router)
app.include_router(_v1_router)
