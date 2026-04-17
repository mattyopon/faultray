# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""SQLite-based time-series metrics storage with retention management.

Design goals:
- Minimal external dependencies (uses sqlite3 stdlib + aiosqlite for async).
- Efficient time-range queries via indexed ``timestamp`` column.
- Automatic data purge beyond retention window.
- Aggregation queries (avg, min, max, sum, count) over time buckets.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB_DIR = Path.home() / ".faultray"
_DEFAULT_DB_NAME = "apm_metrics.db"

# Retention default: 7 days
_DEFAULT_RETENTION_HOURS = 168


class MetricsDB:
    """Synchronous SQLite time-series metrics store.

    Uses WAL journal mode for concurrent reader/writer access.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        retention_hours: int = _DEFAULT_RETENTION_HOURS,
    ) -> None:
        if db_path is None:
            _DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
            db_path = _DEFAULT_DB_DIR / _DEFAULT_DB_NAME
        self.db_path = Path(db_path)
        self.retention_hours = retention_hours
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open or create the database and ensure schema exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path), timeout=10, check_same_thread=False
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._create_tables()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.open()
        assert self._conn is not None
        return self._conn

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_tables(self) -> None:
        c = self.conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS metric_points (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id    TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                value       REAL    NOT NULL,
                metric_type TEXT    NOT NULL DEFAULT 'gauge',
                tags_json   TEXT    DEFAULT '{}',
                timestamp   TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_mp_agent_name_ts
                ON metric_points (agent_id, name, timestamp);
            CREATE INDEX IF NOT EXISTS idx_mp_ts
                ON metric_points (timestamp);

            CREATE TABLE IF NOT EXISTS agent_registry (
                agent_id      TEXT PRIMARY KEY,
                hostname      TEXT    NOT NULL DEFAULT '',
                ip_address    TEXT    NOT NULL DEFAULT '',
                os_info       TEXT    NOT NULL DEFAULT '',
                agent_version TEXT    NOT NULL DEFAULT '',
                labels_json   TEXT    DEFAULT '{}',
                status        TEXT    NOT NULL DEFAULT 'unknown',
                registered_at TEXT    NOT NULL,
                last_seen     TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id    TEXT    NOT NULL UNIQUE,
                rule_name   TEXT    NOT NULL,
                agent_id    TEXT    NOT NULL DEFAULT '',
                metric_name TEXT    NOT NULL DEFAULT '',
                metric_value REAL   NOT NULL DEFAULT 0,
                threshold   REAL   NOT NULL DEFAULT 0,
                severity    TEXT    NOT NULL DEFAULT 'warning',
                message     TEXT    NOT NULL DEFAULT '',
                fired_at    TEXT    NOT NULL,
                resolved_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_agent_ts
                ON alerts (agent_id, fired_at);

            CREATE TABLE IF NOT EXISTS traces (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id       TEXT    NOT NULL,
                span_id        TEXT    NOT NULL,
                parent_span_id TEXT,
                operation      TEXT    NOT NULL DEFAULT '',
                service        TEXT    NOT NULL DEFAULT '',
                duration_ms    REAL    NOT NULL DEFAULT 0,
                status_code    INTEGER NOT NULL DEFAULT 0,
                error          TEXT,
                tags_json      TEXT    DEFAULT '{}',
                start_time     TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_traces_svc_ts
                ON traces (service, start_time);
            """
        )
        c.commit()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def insert_metrics(
        self,
        agent_id: str,
        metrics: list[dict[str, Any]],
    ) -> int:
        """Insert a batch of metric data-points. Returns count inserted."""
        rows = []
        for m in metrics:
            rows.append((
                agent_id,
                m["name"],
                float(m["value"]),
                m.get("metric_type", "gauge"),
                json.dumps(m.get("tags", {})),
                m.get("timestamp", _dt.datetime.now(_dt.timezone.utc).isoformat()),
            ))
        self.conn.executemany(
            """
            INSERT INTO metric_points (agent_id, name, value, metric_type, tags_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()
        return len(rows)

    def register_agent(self, info: dict[str, Any]) -> None:
        """Register or update an agent entry."""
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO agent_registry
                (agent_id, hostname, ip_address, os_info, agent_version,
                 labels_json, status, registered_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                hostname = excluded.hostname,
                ip_address = excluded.ip_address,
                os_info = excluded.os_info,
                agent_version = excluded.agent_version,
                labels_json = excluded.labels_json,
                status = excluded.status,
                last_seen = excluded.last_seen
            """,
            (
                info.get("agent_id", ""),
                info.get("hostname", ""),
                info.get("ip_address", ""),
                info.get("os_info", ""),
                info.get("agent_version", ""),
                json.dumps(info.get("labels", {})),
                info.get("status", "running"),
                info.get("registered_at", now),
                now,
            ),
        )
        self.conn.commit()

    def update_agent_heartbeat(self, agent_id: str, status: str = "running") -> None:
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE agent_registry SET status = ?, last_seen = ? WHERE agent_id = ?",
            (status, now, agent_id),
        )
        self.conn.commit()

    def insert_alert(self, alert: dict[str, Any]) -> None:
        """Insert an alert record."""
        self.conn.execute(
            """
            INSERT OR IGNORE INTO alerts
                (alert_id, rule_name, agent_id, metric_name, metric_value,
                 threshold, severity, message, fired_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert.get("alert_id", ""),
                alert.get("rule_name", ""),
                alert.get("agent_id", ""),
                alert.get("metric_name", ""),
                float(alert.get("metric_value", 0)),
                float(alert.get("threshold", 0)),
                alert.get("severity", "warning"),
                alert.get("message", ""),
                alert.get("fired_at", _dt.datetime.now(_dt.timezone.utc).isoformat()),
                alert.get("resolved_at"),
            ),
        )
        self.conn.commit()

    def insert_traces(self, traces: list[dict[str, Any]]) -> int:
        rows = []
        for t in traces:
            rows.append((
                t.get("trace_id", ""),
                t.get("span_id", ""),
                t.get("parent_span_id"),
                t.get("operation", ""),
                t.get("service", ""),
                float(t.get("duration_ms", 0)),
                int(t.get("status_code", 0)),
                t.get("error"),
                json.dumps(t.get("tags", {})),
                t.get("start_time", _dt.datetime.now(_dt.timezone.utc).isoformat()),
            ))
        self.conn.executemany(
            """
            INSERT INTO traces
                (trace_id, span_id, parent_span_id, operation, service,
                 duration_ms, status_code, error, tags_json, start_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Read / query operations
    # ------------------------------------------------------------------

    def query_metrics(
        self,
        agent_id: str | None = None,
        metric_name: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        aggregation: str = "avg",
        interval_seconds: int = 60,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query metrics with optional aggregation over time buckets."""
        agg_fn = {
            "avg": "AVG(value)",
            "min": "MIN(value)",
            "max": "MAX(value)",
            "sum": "SUM(value)",
            "count": "COUNT(*)",
        }.get(aggregation, "AVG(value)")

        conditions: list[str] = []
        params: list[Any] = []

        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if metric_name:
            conditions.append("name = ?")
            params.append(metric_name)
        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Group by time buckets using strftime
        sql = f"""
            SELECT
                name,
                agent_id,
                {agg_fn} AS value,
                CAST(strftime('%s', timestamp) AS INTEGER) / {interval_seconds}
                    * {interval_seconds} AS bucket,
                COUNT(*) AS sample_count
            FROM metric_points
            {where}
            GROUP BY name, agent_id, bucket
            ORDER BY bucket ASC
            LIMIT ?
        """
        params.append(limit)

        cursor = self.conn.execute(sql, params)
        results = []
        for row in cursor.fetchall():
            results.append({
                "metric_name": row[0],
                "agent_id": row[1],
                "value": row[2],
                "bucket_epoch": row[3],
                "sample_count": row[4],
            })
        return results

    def get_latest_metrics(self, agent_id: str) -> list[dict[str, Any]]:
        """Get the most recent value for each metric name for an agent."""
        cursor = self.conn.execute(
            """
            SELECT name, value, metric_type, tags_json, timestamp
            FROM metric_points
            WHERE agent_id = ?
            AND id IN (
                SELECT MAX(id)
                FROM metric_points
                WHERE agent_id = ?
                GROUP BY name
            )
            ORDER BY name
            """,
            (agent_id, agent_id),
        )
        return [
            {
                "name": r[0],
                "value": r[1],
                "metric_type": r[2],
                "tags": json.loads(r[3]) if r[3] else {},
                "timestamp": r[4],
            }
            for r in cursor.fetchall()
        ]

    def list_agents(self) -> list[dict[str, Any]]:
        cursor = self.conn.execute(
            """
            SELECT agent_id, hostname, ip_address, os_info, agent_version,
                   labels_json, status, registered_at, last_seen
            FROM agent_registry
            ORDER BY last_seen DESC
            """
        )
        return [
            {
                "agent_id": r[0],
                "hostname": r[1],
                "ip_address": r[2],
                "os_info": r[3],
                "agent_version": r[4],
                "labels": json.loads(r[5]) if r[5] else {},
                "status": r[6],
                "registered_at": r[7],
                "last_seen": r[8],
            }
            for r in cursor.fetchall()
        ]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        cursor = self.conn.execute(
            """
            SELECT agent_id, hostname, ip_address, os_info, agent_version,
                   labels_json, status, registered_at, last_seen
            FROM agent_registry WHERE agent_id = ?
            """,
            (agent_id,),
        )
        r = cursor.fetchone()
        if r is None:
            return None
        return {
            "agent_id": r[0],
            "hostname": r[1],
            "ip_address": r[2],
            "os_info": r[3],
            "agent_version": r[4],
            "labels": json.loads(r[5]) if r[5] else {},
            "status": r[6],
            "registered_at": r[7],
            "last_seen": r[8],
        }

    def list_alerts(
        self,
        agent_id: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        cursor = self.conn.execute(
            f"""
            SELECT alert_id, rule_name, agent_id, metric_name, metric_value,
                   threshold, severity, message, fired_at, resolved_at
            FROM alerts {where}
            ORDER BY fired_at DESC
            LIMIT ?
            """,
            params,
        )
        return [
            {
                "alert_id": r[0],
                "rule_name": r[1],
                "agent_id": r[2],
                "metric_name": r[3],
                "metric_value": r[4],
                "threshold": r[5],
                "severity": r[6],
                "message": r[7],
                "fired_at": r[8],
                "resolved_at": r[9],
            }
            for r in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # Retention / purge
    # ------------------------------------------------------------------

    def purge_old_data(self) -> int:
        """Delete metric data older than the retention window. Returns count deleted."""
        cutoff = (
            _dt.datetime.now(_dt.timezone.utc)
            - _dt.timedelta(hours=self.retention_hours)
        ).isoformat()
        cursor = self.conn.execute(
            "DELETE FROM metric_points WHERE timestamp < ?", (cutoff,)
        )
        deleted = cursor.rowcount
        # Also purge old traces
        self.conn.execute("DELETE FROM traces WHERE start_time < ?", (cutoff,))
        self.conn.commit()
        if deleted > 0:
            logger.info("Purged %d old metric points (cutoff=%s)", deleted, cutoff)
        return deleted

    def get_stats(self) -> dict[str, int]:
        """Return database statistics."""
        c = self.conn
        metrics_count = c.execute("SELECT COUNT(*) FROM metric_points").fetchone()[0]
        agents_count = c.execute("SELECT COUNT(*) FROM agent_registry").fetchone()[0]
        alerts_count = c.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        traces_count = c.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        return {
            "metric_points": metrics_count,
            "agents": agents_count,
            "total_agents": agents_count,
            "alerts": alerts_count,
            "traces": traces_count,
        }
