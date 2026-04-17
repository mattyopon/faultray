# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Collector API — FastAPI router for receiving APM agent telemetry.

Integrates into the existing FaultRay FastAPI application via
``app.include_router(apm_router)``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from faultray.apm.metrics_db import MetricsDB
from faultray.apm.models import (
    AgentHeartbeat,
    AgentRegistration,
    MetricsBatch,
    MetricsQuery,
)

logger = logging.getLogger(__name__)

apm_router = APIRouter(prefix="/api/apm", tags=["APM"])

# ---------------------------------------------------------------------------
# Module-level MetricsDB instance (initialised lazily)
# ---------------------------------------------------------------------------

_metrics_db: MetricsDB | None = None


def get_metrics_db() -> MetricsDB:
    """Return the shared MetricsDB instance, creating it if needed."""
    global _metrics_db
    if _metrics_db is None:
        _metrics_db = MetricsDB()
        _metrics_db.open()
    return _metrics_db


def set_metrics_db(db: MetricsDB) -> None:
    """Replace the shared MetricsDB (useful for tests)."""
    global _metrics_db
    _metrics_db = db


# ---------------------------------------------------------------------------
# Authentication helper
# ---------------------------------------------------------------------------

async def _verify_agent_key(request: Request) -> str | None:
    """Verify the agent API key from the Authorization header.

    Returns the agent identifier or None if auth is not enforced.
    For now, accept any Bearer token if present — the collector is
    designed to be deployed on a private network.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


# ---------------------------------------------------------------------------
# Metrics ingestion
# ---------------------------------------------------------------------------

class IngestResponse(BaseModel):
    status: str = "ok"
    metrics_stored: int = 0
    traces_stored: int = 0


@apm_router.post("/metrics", response_model=IngestResponse)
async def ingest_metrics(batch: MetricsBatch) -> IngestResponse:
    """Receive a batch of metrics from an agent."""
    db = get_metrics_db()

    metrics_count = 0
    traces_count = 0

    # Store host metrics as individual metric points
    if batch.host_metrics:
        hm = batch.host_metrics
        host_points = [
            {"name": "cpu_percent", "value": hm.cpu_percent, "metric_type": "gauge"},
            {"name": "memory_percent", "value": hm.memory_percent, "metric_type": "gauge"},
            {"name": "memory_used_mb", "value": hm.memory_used_mb, "metric_type": "gauge"},
            {"name": "disk_percent", "value": hm.disk_percent, "metric_type": "gauge"},
            {"name": "disk_used_gb", "value": hm.disk_used_gb, "metric_type": "gauge"},
            {"name": "network_bytes_sent", "value": hm.network_bytes_sent, "metric_type": "counter"},
            {"name": "network_bytes_recv", "value": hm.network_bytes_recv, "metric_type": "counter"},
            {"name": "network_connections", "value": hm.network_connections, "metric_type": "gauge"},
            {"name": "load_avg_1m", "value": hm.load_avg_1m, "metric_type": "gauge"},
            {"name": "load_avg_5m", "value": hm.load_avg_5m, "metric_type": "gauge"},
        ]
        ts = batch.timestamp.isoformat()
        for p in host_points:
            p["timestamp"] = ts
        metrics_count += db.insert_metrics(batch.agent_id, host_points)

    # Store custom metrics
    if batch.custom_metrics:
        custom_points = [
            {
                "name": m.name,
                "value": m.value,
                "metric_type": m.metric_type.value,
                "tags": m.tags,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in batch.custom_metrics
        ]
        metrics_count += db.insert_metrics(batch.agent_id, custom_points)

    # Store traces
    if batch.traces:
        trace_dicts = [
            {
                "trace_id": t.trace_id,
                "span_id": t.span_id,
                "parent_span_id": t.parent_span_id,
                "operation": t.operation,
                "service": t.service,
                "duration_ms": t.duration_ms,
                "status_code": t.status_code,
                "error": t.error,
                "tags": t.tags,
                "start_time": t.start_time.isoformat(),
            }
            for t in batch.traces
        ]
        traces_count += db.insert_traces(trace_dicts)

    # Update agent heartbeat
    db.update_agent_heartbeat(batch.agent_id, "running")

    # Run anomaly detection (lazy import to avoid circular deps)
    try:
        from faultray.apm.anomaly import get_anomaly_engine

        engine = get_anomaly_engine()
        if engine is not None and batch.host_metrics:
            engine.check_batch(batch.agent_id, batch.host_metrics, db)
    except Exception:
        logger.debug("Anomaly check skipped", exc_info=True)

    # Update topology if connections present
    if batch.connections or batch.processes:
        try:
            from faultray.apm.topology_updater import update_topology_from_batch

            update_topology_from_batch(batch)
        except Exception:
            logger.debug("Topology update skipped", exc_info=True)

    return IngestResponse(
        metrics_stored=metrics_count,
        traces_stored=traces_count,
    )


# ---------------------------------------------------------------------------
# Agent registration & heartbeat
# ---------------------------------------------------------------------------

@apm_router.post("/agents/register")
async def register_agent(reg: AgentRegistration) -> dict[str, str]:
    """Register an agent with the collector."""
    db = get_metrics_db()
    db.register_agent(reg.model_dump())
    logger.info("Agent registered: %s (%s)", reg.agent_id, reg.hostname)
    return {"status": "registered", "agent_id": reg.agent_id}


@apm_router.post("/agents/{agent_id}/heartbeat")
async def agent_heartbeat(agent_id: str, hb: AgentHeartbeat) -> dict[str, str]:
    """Receive a heartbeat from an agent."""
    db = get_metrics_db()
    db.update_agent_heartbeat(agent_id, hb.status.value)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Query endpoints
# ---------------------------------------------------------------------------

@apm_router.get("/agents")
async def list_agents() -> list[dict[str, Any]]:
    """List all registered agents."""
    db = get_metrics_db()
    return db.list_agents()


@apm_router.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict[str, Any]:
    """Get a single agent's info and latest metrics."""
    db = get_metrics_db()
    agent = db.get_agent(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )
    agent["latest_metrics"] = db.get_latest_metrics(agent_id)
    return agent


@apm_router.get("/agents/{agent_id}/metrics")
async def get_agent_metrics(
    agent_id: str,
    metric_name: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    aggregation: str = "avg",
    interval: int = 60,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Query metrics for a specific agent."""
    db = get_metrics_db()
    return db.query_metrics(
        agent_id=agent_id,
        metric_name=metric_name,
        start_time=start_time,
        end_time=end_time,
        aggregation=aggregation,
        interval_seconds=interval,
        limit=limit,
    )


@apm_router.post("/metrics/query")
async def query_metrics(query: MetricsQuery) -> list[dict[str, Any]]:
    """Advanced metrics query with filters and aggregation."""
    db = get_metrics_db()
    return db.query_metrics(
        agent_id=query.agent_id,
        metric_name=query.metric_names[0] if query.metric_names else None,
        start_time=query.start_time.isoformat() if query.start_time else None,
        end_time=query.end_time.isoformat() if query.end_time else None,
        aggregation=query.aggregation,
        interval_seconds=query.interval_seconds,
        limit=query.limit,
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@apm_router.get("/alerts")
async def list_alerts(
    agent_id: str | None = None,
    severity: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List recent alerts."""
    db = get_metrics_db()
    return db.list_alerts(agent_id=agent_id, severity=severity, limit=limit)


# ---------------------------------------------------------------------------
# Stats / health
# ---------------------------------------------------------------------------

@apm_router.get("/stats")
async def apm_stats() -> dict[str, Any]:
    """Return APM system statistics."""
    db = get_metrics_db()
    return db.get_stats()


@apm_router.post("/purge")
async def purge_old_data() -> dict[str, int]:
    """Manually trigger data purge (retention policy)."""
    db = get_metrics_db()
    deleted = db.purge_old_data()
    return {"deleted": deleted}
