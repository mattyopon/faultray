# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Team Workspace API — multi-tenant team management with projects and members.

Provides CRUD endpoints for teams, team membership, and team-scoped projects.
Persists data using the existing SQLite database via SQLAlchemy async ORM.
"""

from __future__ import annotations

import datetime as _dt
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

teams_router = APIRouter(prefix="/api/teams", tags=["teams"])


# ---------------------------------------------------------------------------
# Database table creation helper
# ---------------------------------------------------------------------------

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS team_workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_members (
    team_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    joined_at TEXT NOT NULL,
    PRIMARY KEY (team_id, user_id),
    FOREIGN KEY (team_id) REFERENCES team_workspaces(id)
);

CREATE TABLE IF NOT EXISTS team_projects (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    name TEXT NOT NULL,
    model_data TEXT,
    last_score REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (team_id) REFERENCES team_workspaces(id)
);
"""


async def _ensure_tables(session) -> None:
    """Create team workspace tables if they don't already exist."""
    from sqlalchemy import text

    for statement in _TABLES_SQL.strip().split(';'):
        stmt = statement.strip()
        if stmt:
            await session.execute(text(stmt))
    await session.commit()


def _get_session_factory():
    """Lazily import and return the session factory."""
    from faultray.api.database import get_session_factory
    return get_session_factory()


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Team CRUD
# ---------------------------------------------------------------------------

@teams_router.post("/")
async def create_team(request: Request) -> JSONResponse:
    """Create a new team workspace.

    Expects JSON body: ``{"name": "...", "owner_id": "..."}``
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    name = body.get("name", "").strip()
    owner_id = body.get("owner_id", "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required")
    if not owner_id:
        raise HTTPException(status_code=400, detail="'owner_id' is required")

    try:
        from sqlalchemy import text

        sf = _get_session_factory()
        async with sf() as session:
            await _ensure_tables(session)

            team_id = uuid.uuid4().hex[:12]
            now = _now_iso()

            await session.execute(
                text(
                    "INSERT INTO team_workspaces (id, name, owner_id, created_at) "
                    "VALUES (:id, :name, :owner_id, :created_at)"
                ),
                {"id": team_id, "name": name, "owner_id": owner_id, "created_at": now},
            )

            # Add owner as admin member
            await session.execute(
                text(
                    "INSERT INTO team_members (team_id, user_id, role, joined_at) "
                    "VALUES (:team_id, :user_id, :role, :joined_at)"
                ),
                {"team_id": team_id, "user_id": owner_id, "role": "admin", "joined_at": now},
            )

            await session.commit()

            return JSONResponse(
                {
                    "id": team_id,
                    "name": name,
                    "owner_id": owner_id,
                    "created_at": now,
                    "members": [{"user_id": owner_id, "role": "admin"}],
                },
                status_code=201,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to create team: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="Database not available")


@teams_router.get("/")
async def list_teams(user_id: str | None = None) -> JSONResponse:
    """List teams, optionally filtered by user membership."""
    try:
        from sqlalchemy import text

        sf = _get_session_factory()
        async with sf() as session:
            await _ensure_tables(session)

            if user_id:
                rows = (
                    await session.execute(
                        text(
                            "SELECT tw.id, tw.name, tw.owner_id, tw.created_at "
                            "FROM team_workspaces tw "
                            "INNER JOIN team_members tm ON tw.id = tm.team_id "
                            "WHERE tm.user_id = :user_id "
                            "ORDER BY tw.created_at DESC"
                        ),
                        {"user_id": user_id},
                    )
                ).fetchall()
            else:
                rows = (
                    await session.execute(
                        text(
                            "SELECT id, name, owner_id, created_at "
                            "FROM team_workspaces ORDER BY created_at DESC"
                        )
                    )
                ).fetchall()

            teams = [
                {"id": r[0], "name": r[1], "owner_id": r[2], "created_at": r[3]}
                for r in rows
            ]
            return JSONResponse({"teams": teams, "count": len(teams)})
    except Exception as exc:
        logger.debug("Could not list teams: %s", exc)
        return JSONResponse({"teams": [], "count": 0, "note": "Database not available"})


@teams_router.get("/{team_id}")
async def get_team(team_id: str) -> JSONResponse:
    """Get a single team with its members."""
    try:
        from sqlalchemy import text

        sf = _get_session_factory()
        async with sf() as session:
            await _ensure_tables(session)

            row = (
                await session.execute(
                    text(
                        "SELECT id, name, owner_id, created_at "
                        "FROM team_workspaces WHERE id = :id"
                    ),
                    {"id": team_id},
                )
            ).fetchone()

            if row is None:
                raise HTTPException(status_code=404, detail="Team not found")

            members_rows = (
                await session.execute(
                    text(
                        "SELECT user_id, role, joined_at "
                        "FROM team_members WHERE team_id = :team_id"
                    ),
                    {"team_id": team_id},
                )
            ).fetchall()

            members = [
                {"user_id": m[0], "role": m[1], "joined_at": m[2]}
                for m in members_rows
            ]

            return JSONResponse({
                "id": row[0],
                "name": row[1],
                "owner_id": row[2],
                "created_at": row[3],
                "members": members,
            })
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("Could not get team: %s", exc)
        raise HTTPException(status_code=503, detail="Database not available")


# ---------------------------------------------------------------------------
# Team member management
# ---------------------------------------------------------------------------

@teams_router.post("/{team_id}/members")
async def add_member(team_id: str, request: Request) -> JSONResponse:
    """Add a member to a team.

    Expects JSON body: ``{"user_id": "...", "role": "viewer"}``
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    user_id = body.get("user_id", "").strip()
    role = body.get("role", "viewer").strip()

    if not user_id:
        raise HTTPException(status_code=400, detail="'user_id' is required")
    if role not in ("admin", "editor", "viewer"):
        raise HTTPException(status_code=400, detail="'role' must be admin, editor, or viewer")

    try:
        from sqlalchemy import text

        sf = _get_session_factory()
        async with sf() as session:
            await _ensure_tables(session)

            # Verify team exists
            team_row = (
                await session.execute(
                    text("SELECT id FROM team_workspaces WHERE id = :id"),
                    {"id": team_id},
                )
            ).fetchone()
            if team_row is None:
                raise HTTPException(status_code=404, detail="Team not found")

            # Check if already a member
            existing = (
                await session.execute(
                    text(
                        "SELECT user_id FROM team_members "
                        "WHERE team_id = :team_id AND user_id = :user_id"
                    ),
                    {"team_id": team_id, "user_id": user_id},
                )
            ).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="User is already a member")

            now = _now_iso()
            await session.execute(
                text(
                    "INSERT INTO team_members (team_id, user_id, role, joined_at) "
                    "VALUES (:team_id, :user_id, :role, :joined_at)"
                ),
                {"team_id": team_id, "user_id": user_id, "role": role, "joined_at": now},
            )
            await session.commit()

            return JSONResponse(
                {"team_id": team_id, "user_id": user_id, "role": role, "joined_at": now},
                status_code=201,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to add member: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="Database not available")


@teams_router.delete("/{team_id}/members/{user_id}")
async def remove_member(team_id: str, user_id: str) -> JSONResponse:
    """Remove a member from a team.

    The team owner cannot be removed.
    """
    try:
        from sqlalchemy import text

        sf = _get_session_factory()
        async with sf() as session:
            await _ensure_tables(session)

            # Check that team exists and user is not the owner
            team_row = (
                await session.execute(
                    text("SELECT owner_id FROM team_workspaces WHERE id = :id"),
                    {"id": team_id},
                )
            ).fetchone()
            if team_row is None:
                raise HTTPException(status_code=404, detail="Team not found")
            if team_row[0] == user_id:
                raise HTTPException(status_code=400, detail="Cannot remove the team owner")

            result = await session.execute(
                text(
                    "DELETE FROM team_members "
                    "WHERE team_id = :team_id AND user_id = :user_id"
                ),
                {"team_id": team_id, "user_id": user_id},
            )
            await session.commit()

            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Member not found")

            return JSONResponse({"removed": True, "team_id": team_id, "user_id": user_id})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to remove member: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="Database not available")


# ---------------------------------------------------------------------------
# Team projects
# ---------------------------------------------------------------------------

@teams_router.post("/{team_id}/projects")
async def create_project(team_id: str, request: Request) -> JSONResponse:
    """Create a project within a team.

    Expects JSON body: ``{"name": "..."}``
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="'name' is required")

    try:
        from sqlalchemy import text

        sf = _get_session_factory()
        async with sf() as session:
            await _ensure_tables(session)

            # Verify team exists
            team_row = (
                await session.execute(
                    text("SELECT id FROM team_workspaces WHERE id = :id"),
                    {"id": team_id},
                )
            ).fetchone()
            if team_row is None:
                raise HTTPException(status_code=404, detail="Team not found")

            project_id = uuid.uuid4().hex[:12]
            now = _now_iso()

            await session.execute(
                text(
                    "INSERT INTO team_projects (id, team_id, name, model_data, last_score, created_at, updated_at) "
                    "VALUES (:id, :team_id, :name, :model_data, :last_score, :created_at, :updated_at)"
                ),
                {
                    "id": project_id,
                    "team_id": team_id,
                    "name": name,
                    "model_data": None,
                    "last_score": None,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            await session.commit()

            return JSONResponse(
                {
                    "id": project_id,
                    "team_id": team_id,
                    "name": name,
                    "last_score": None,
                    "created_at": now,
                    "updated_at": now,
                },
                status_code=201,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to create project: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="Database not available")


@teams_router.get("/{team_id}/projects")
async def list_projects(team_id: str) -> JSONResponse:
    """List all projects belonging to a team."""
    try:
        from sqlalchemy import text

        sf = _get_session_factory()
        async with sf() as session:
            await _ensure_tables(session)

            # Verify team exists
            team_row = (
                await session.execute(
                    text("SELECT id FROM team_workspaces WHERE id = :id"),
                    {"id": team_id},
                )
            ).fetchone()
            if team_row is None:
                raise HTTPException(status_code=404, detail="Team not found")

            rows = (
                await session.execute(
                    text(
                        "SELECT id, team_id, name, last_score, created_at, updated_at "
                        "FROM team_projects WHERE team_id = :team_id "
                        "ORDER BY created_at DESC"
                    ),
                    {"team_id": team_id},
                )
            ).fetchall()

            projects = [
                {
                    "id": r[0],
                    "team_id": r[1],
                    "name": r[2],
                    "last_score": r[3],
                    "created_at": r[4],
                    "updated_at": r[5],
                }
                for r in rows
            ]
            return JSONResponse({"projects": projects, "count": len(projects)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("Could not list projects: %s", exc)
        return JSONResponse({"projects": [], "count": 0, "note": "Database not available"})
