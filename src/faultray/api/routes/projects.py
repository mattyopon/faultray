# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Project management, simulation runs CRUD, and audit log endpoints."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from faultray.api.routes._shared import (
    _decompress_json,
    _optional_user,
    _require_permission,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Simulation runs CRUD
# ---------------------------------------------------------------------------

@router.get("/api/runs", response_class=JSONResponse)
async def list_runs(
    limit: int = 50,
    offset: int = 0,
    project_id: int | None = None,
    user=Depends(_require_permission("view_results")),
):
    """List past simulation runs (newest first)."""
    try:
        from faultray.api.database import SimulationRunRow, get_session_factory
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(SimulationRunRow)

            if project_id is not None:
                stmt = stmt.where(SimulationRunRow.project_id == project_id)

            run_filter = await _team_visible_run_filter(session, user)
            if run_filter is not None:
                stmt = stmt.where(run_filter)

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


def _user_is_global_admin(user) -> bool:
    """True if *user* holds the global admin (deployment superadmin) role.

    This is the UserRow.role granted to the setup admin; OAuth-created users are
    always editor/viewer, so it is never attacker-obtainable. A global admin is
    entitled to see every tenant's data (support / ops), so tenant scoping does
    not apply to them.
    """
    return str(getattr(user, "role", "") or "").strip().lower() == "admin"


async def _run_visible_to_user(session, row, user) -> bool:
    """Return True if *user* is allowed to access simulation run *row*.

    Enforces tenant isolation:
    - no resolved user (backward-compatible no-auth mode) -> unrestricted;
    - global admin (superadmin) -> unrestricted;
    - an authenticated user with NO team -> only unowned (project-less) runs, so
      an unscoped / misconfigured account can never see another tenant's
      project-assigned runs;
    - a team-scoped user -> runs whose project belongs to that team (or runs
      with no project).
    """
    if user is None or _user_is_global_admin(user):
        return True
    if getattr(user, "team_id", None) is None:
        return row.project_id is None
    if row.project_id is None:
        return True
    from faultray.api.database import ProjectRow
    from sqlalchemy import select

    owner_team = (
        await session.execute(
            select(ProjectRow.team_id).where(ProjectRow.id == row.project_id)
        )
    ).scalar_one_or_none()
    return owner_team == user.team_id


async def _team_visible_run_filter(session, user):
    """Return a WHERE condition restricting a ``SimulationRunRow`` query to runs
    visible to *user*, or ``None`` for no restriction.

    List/aggregate-query analogue of :func:`_run_visible_to_user`:
    - no user (no-auth mode) or global admin -> ``None`` (no restriction), which
      keeps single-tenant / unauthenticated deployments working unchanged;
    - an authenticated user with NO team -> only project-less runs, so an
      unscoped / misconfigured account can never see another tenant's runs;
    - a team-scoped user -> runs whose project belongs to their team, plus runs
      with no project.

    Centralising this here means every cross-tenant run query (runs list, score
    history, …) shares one definition and cannot drift out of sync.
    """
    if user is None or _user_is_global_admin(user):
        return None
    from faultray.api.database import ProjectRow, SimulationRunRow
    from sqlalchemy import select

    if getattr(user, "team_id", None) is None:
        return SimulationRunRow.project_id.is_(None)

    team_project_ids = (
        await session.execute(
            select(ProjectRow.id).where(ProjectRow.team_id == user.team_id)
        )
    ).scalars().all()
    return (SimulationRunRow.project_id.is_(None)) | (
        SimulationRunRow.project_id.in_(team_project_ids)
    )


@router.get("/api/runs/{run_id}", response_class=JSONResponse)
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

            if row is None or not await _run_visible_to_user(session, row, user):
                # Return 404 (not 403) so cross-tenant ids are indistinguishable
                # from non-existent ones (no enumeration oracle).
                return JSONResponse({"error": "Run not found"}, status_code=404)

            return JSONResponse({
                "id": row.id,
                "project_id": row.project_id,
                "engine_type": row.engine_type,
                "config_json": json.loads(row.config_json) if row.config_json else None,
                "results_json": _decompress_json(row.results_json) if row.results_json else None,
                "risk_score": row.risk_score,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })
    except Exception as exc:
        logger.debug("Could not get run: %s", exc)
        return JSONResponse({"error": "Database not available"}, status_code=503)


@router.delete("/api/runs/{run_id}", response_class=JSONResponse)
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

            if row is None or not await _run_visible_to_user(session, row, user):
                return JSONResponse({"error": "Run not found"}, status_code=404)

            await session.delete(row)

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
# Projects CRUD
# ---------------------------------------------------------------------------

@router.post("/api/projects", response_class=JSONResponse)
async def create_project(request: Request, user=Depends(_require_permission("create_project"))):
    """Create a new project."""
    try:
        from faultray.api.database import ProjectRow, get_session_factory, log_audit

        body = await request.json()
        name = body.get("name")
        if not name:
            return JSONResponse({"error": "name is required"}, status_code=400)

        requested_team_id = body.get("team_id")

        # Tenant safety: a team-scoped caller may only create projects within
        # their own team — never assign a project to an arbitrary team supplied
        # in the request body. Unscoped callers (e.g. admins with no team) may
        # set any team_id.
        if user is not None and getattr(user, "team_id", None) is not None:
            if requested_team_id and requested_team_id != user.team_id:
                return JSONResponse(
                    {"error": "Cannot assign project to a different team"},
                    status_code=403,
                )
            team_id = user.team_id
        else:
            team_id = requested_team_id if requested_team_id else (
                user.team_id if user else None
            )

        session_factory = get_session_factory()
        async with session_factory() as session:
            project = ProjectRow(
                name=name,
                owner_id=user.id if user else None,
                team_id=team_id,
            )
            session.add(project)
            await session.flush()

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


@router.get("/api/projects", response_class=JSONResponse)
async def list_projects(user=Depends(_require_permission("view_results"))):
    """List projects visible to the current user."""
    try:
        from faultray.api.database import ProjectRow, get_session_factory
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(ProjectRow)

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
# Audit logs
# ---------------------------------------------------------------------------

@router.get("/api/audit-logs", response_class=JSONResponse)
async def list_audit_logs(
    limit: int = 100,
    offset: int = 0,
    user=Depends(_optional_user),
):
    """List audit log entries.

    Requires authentication (audit entries expose user ids and IP addresses).
    A user scoped to a team only sees entries generated by members of that
    team; admins / unscoped users see all entries.
    """
    # Fail closed: audit logs leak user ids / IP addresses, so an
    # unauthenticated caller must never read them.
    if user is None:
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    try:
        from faultray.api.database import AuditLog, UserRow, get_session_factory
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(AuditLog)

            # Tenant scoping: restrict to audit entries whose actor belongs to
            # the caller's team (plus the caller's own entries). Unscoped
            # users (e.g. admins with no team) are not restricted.
            if user is not None and getattr(user, "team_id", None) is not None:
                team_user_ids = (
                    await session.execute(
                        select(UserRow.id).where(UserRow.team_id == user.team_id)
                    )
                ).scalars().all()
                stmt = stmt.where(AuditLog.user_id.in_(team_user_ids))

            stmt = (
                stmt.order_by(AuditLog.id.desc())
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
