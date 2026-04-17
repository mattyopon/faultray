# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Shared state and helpers used across router modules.

All router modules import from here instead of directly from server.py to
avoid circular imports.  The actual state variables live in ``server.py``;
this module re-exports thin wrappers that proxy through to them.
"""

from __future__ import annotations

import base64
import json
import logging
import zlib
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Module-level state — accessed via getter/setters in server.py
# We import them lazily to avoid circular imports.
# ---------------------------------------------------------------------------

def get_graph() -> InfraGraph:
    from faultray.api.server import get_graph as _get_graph
    return _get_graph()


def set_graph(graph: InfraGraph) -> None:
    from faultray.api.server import set_graph as _set_graph
    _set_graph(graph)


def get_last_report():
    from faultray.api import server
    return server._last_report


def set_last_report(report) -> None:
    from faultray.api import server
    server._last_report = report


def get_model_path():
    from faultray.api import server
    return server._model_path


def build_demo_graph() -> InfraGraph:
    from faultray.api.server import build_demo_graph as _build
    return _build()


# ---------------------------------------------------------------------------
# Auth dependencies — these MUST resolve to the same function objects as in
# server.py for FastAPI dependency_overrides to work.
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
# Report conversion helper
# ---------------------------------------------------------------------------

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

    score = round(report.resilience_score, 1)
    results = [_result_dict(r) for r in report.results]
    criticals = [_result_dict(r) for r in report.critical_findings]
    warnings_list = [_result_dict(r) for r in report.warnings]
    passed_list = [_result_dict(r) for r in report.passed]

    # Build recommendations from critical and warning findings
    recommendations: list[str] = []
    for r in report.critical_findings:
        recommendations.append(
            f"[CRITICAL] {r.scenario.name}: {r.scenario.description}"
        )
    for r in report.warnings:
        recommendations.append(
            f"[WARNING] {r.scenario.name}: {r.scenario.description}"
        )

    # Component-level scores from cascade effects
    component_scores: dict[str, dict] = {}
    for r in report.results:
        for e in r.cascade.effects:
            cid = e.component_id
            if cid not in component_scores:
                component_scores[cid] = {
                    "component_id": cid,
                    "component_name": e.component_name,
                    "affected_count": 0,
                    "health_states": [],
                }
            component_scores[cid]["affected_count"] += 1
            component_scores[cid]["health_states"].append(e.health.value)

    return {
        "resilience_score": score,
        "overall_score": score,
        "total_scenarios": len(report.results),
        "critical_count": len(report.critical_findings),
        "warning_count": len(report.warnings),
        "passed_count": len(report.passed),
        "critical": criticals,
        "warnings": warnings_list,
        "passed": passed_list,
        "scenarios": results,
        "cascade_simulations": results,
        "recommendations": recommendations,
        "component_scores": component_scores,
    }


def _compress_json(data: dict) -> str:
    """Compress a dict to a base64-encoded zlib-compressed string."""
    raw = json.dumps(data).encode()
    return base64.b64encode(zlib.compress(raw)).decode()


def _decompress_json(value: str) -> dict:
    """Decompress a value produced by _compress_json, or fall back to plain JSON."""
    try:
        return json.loads(zlib.decompress(base64.b64decode(value)))
    except Exception:
        # Legacy uncompressed rows
        return json.loads(value)


async def _save_run(report_dict: dict, engine_type: str = "static") -> int | None:
    """Persist a simulation run to the database. Returns the row id or None."""
    try:
        import datetime as _dt

        from faultray.api.database import SimulationRunRow, get_session_factory
        from sqlalchemy import delete

        session_factory = get_session_factory()
        async with session_factory() as session:
            # Purge records older than 30 days
            cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=30)
            await session.execute(
                delete(SimulationRunRow).where(SimulationRunRow.created_at < cutoff)
            )

            row = SimulationRunRow(
                engine_type=engine_type,
                config_json=None,
                results_json=_compress_json(report_dict),
                risk_score=report_dict.get("resilience_score"),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id
    except Exception:
        logger.debug("Could not persist simulation run.", exc_info=True)
        return None


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
