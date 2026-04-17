# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""SQLAlchemy async database layer for FaultRay SaaS persistence."""

from __future__ import annotations

import datetime as _dt
import json as _json
from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, Float, Integer, String, Text, ForeignKey, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ---------------------------------------------------------------------------
# Database path
# ---------------------------------------------------------------------------
DB_DIR = Path.home() / ".faultray"
DB_PATH = DB_DIR / "faultray.db"


def get_database_url(path: Path | None = None) -> str:
    """Return the async SQLite database URL."""
    p = path or DB_PATH
    return f"sqlite+aiosqlite:///{p}"


# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ORM models (SQLAlchemy 2.0 mapped_column style)
# ---------------------------------------------------------------------------

class TeamRow(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )

    # relationships
    users: Mapped[list["UserRow"]] = relationship(back_populates="team")
    projects: Mapped[list["ProjectRow"]] = relationship(back_populates="team")


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    # OAuth fields
    oauth_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    oauth_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tier: Mapped[str] = mapped_column(String(20), nullable=False, server_default="free")
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )

    # relationships
    team: Mapped[TeamRow | None] = relationship(back_populates="users")
    projects: Mapped[list["ProjectRow"]] = relationship(back_populates="owner")


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    # relationships
    owner: Mapped[UserRow | None] = relationship(back_populates="projects")
    team: Mapped[TeamRow | None] = relationship(back_populates="projects")
    simulation_runs: Mapped[list["SimulationRunRow"]] = relationship(
        back_populates="project", cascade="all, delete-orphan",
    )


class SimulationRunRow(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True,
    )
    engine_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="static",
    )
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    results_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )

    # relationships
    project: Mapped[ProjectRow | None] = relationship(back_populates="simulation_runs")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[str] = mapped_column(
        String(50), default=lambda: datetime.now(_dt.timezone.utc).isoformat(),
    )


class SubscriptionRow(Base):
    """Team subscription / pricing tier."""
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    tier: Mapped[str] = mapped_column(
        String(20), nullable=False, default="free",
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
    )
    started_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    expires_at: Mapped[_dt.datetime | None] = mapped_column(
        DateTime, nullable=True,
    )


class UsageLogRow(Base):
    """Per-team resource usage log."""
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )


class IntegrationConfigRow(Base):
    """Per-team third-party integration configuration."""
    __tablename__ = "integration_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )  # slack, pagerduty, opsgenie, datadog, grafana, jira, linear
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
    )


async def log_audit(
    session: AsyncSession,
    user_id: int | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
    ip: str | None = None,
) -> AuditLog:
    """Persist an audit log entry.

    Parameters
    ----------
    session:
        An active async SQLAlchemy session.
    user_id:
        The id of the acting user, or ``None`` for unauthenticated actions.
    action:
        Short verb describing the action, e.g. ``"simulate"``, ``"delete_run"``.
    resource_type:
        The kind of resource affected, e.g. ``"simulation_run"``, ``"project"``.
    resource_id:
        Optional identifier of the affected resource.
    details:
        Optional dict with extra context; serialised as JSON.
    ip:
        Client IP address if available.
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details_json=_json.dumps(details) if details else None,
        ip_address=ip,
    )
    session.add(entry)
    await session.flush()
    return entry


# ---------------------------------------------------------------------------
# Engine / session factory
# ---------------------------------------------------------------------------

_engine = None
_session_factory = None


def _get_engine(url: str | None = None):
    global _engine
    if _engine is None:
        db_url = url or get_database_url()
        _engine = create_async_engine(db_url, echo=False)
    return _engine


def get_session_factory(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        engine = _get_engine(url)
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


def reset_engine() -> None:
    """Reset engine and session factory (useful for tests)."""
    global _engine, _session_factory
    if _engine is not None:
        # We don't await dispose here; callers should do that if needed.
        _engine = None
    _session_factory = None


async def init_db(url: str | None = None) -> None:
    """Create all tables if they don't exist.

    Also ensures the database directory exists.
    """
    if url is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)

    engine = _get_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
