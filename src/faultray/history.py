# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Historical trend tracking for FaultRay resilience scores.

Tracks resilience scores over time using SQLite to detect trends,
regressions, and improvements in infrastructure resilience.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class HistoryEntry:
    """A single recorded resilience evaluation snapshot."""

    timestamp: str
    resilience_score: float
    resilience_score_v2: float
    security_score: float
    critical_count: int
    warning_count: int
    component_count: int
    model_hash: str
    metadata: dict = field(default_factory=dict)


@dataclass
class TrendAnalysis:
    """Analysis of score trends over a time period."""

    entries: list[HistoryEntry]
    score_trend: str  # "improving", "stable", "degrading"
    score_change_30d: float  # delta over last 30 days
    best_score: float
    worst_score: float
    regression_dates: list[str]  # dates where score dropped
    recommendation: str


def _compute_model_hash(graph: Any) -> str:
    """Compute a deterministic hash of the infrastructure model."""
    try:
        data = graph.to_dict()
        raw = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    except Exception:
        return "unknown"


class HistoryTracker:
    """Track resilience scores over time using SQLite."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path.home() / ".faultray" / "history.db"
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite database and create tables if needed."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    resilience_score REAL NOT NULL,
                    resilience_score_v2 REAL NOT NULL DEFAULT 0.0,
                    security_score REAL NOT NULL DEFAULT 0.0,
                    critical_count INTEGER NOT NULL DEFAULT 0,
                    warning_count INTEGER NOT NULL DEFAULT 0,
                    component_count INTEGER NOT NULL DEFAULT 0,
                    model_hash TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_timestamp
                ON history (timestamp)
            """)

    def _connect(self) -> sqlite3.Connection:
        """Create a new SQLite connection."""
        return sqlite3.connect(str(self.db_path))

    def record(
        self,
        graph: Any,
        report: Any | None = None,
        security_report: Any | None = None,
    ) -> HistoryEntry:
        """Record a new history entry from an InfraGraph and optional reports.

        Args:
            graph: An InfraGraph instance.
            report: Optional SimulationReport with critical/warning counts.
            security_report: Optional SecurityReport with security score.

        Returns:
            The recorded HistoryEntry.
        """
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # Resilience score v1
        resilience_score = graph.resilience_score()

        # Resilience score v2
        v2_data = graph.resilience_score_v2()
        resilience_score_v2 = v2_data.get("score", 0.0) if isinstance(v2_data, dict) else 0.0

        # Security score
        security_score = 0.0
        if security_report is not None:
            security_score = getattr(security_report, "security_resilience_score", 0.0)

        # Critical and warning counts from report
        critical_count = 0
        warning_count = 0
        if report is not None:
            critical_count = len(getattr(report, "critical_findings", []))
            warning_count = len(getattr(report, "warnings", []))

        component_count = len(graph.components)
        model_hash = _compute_model_hash(graph)

        metadata: dict = {}
        if report is not None:
            metadata["total_scenarios"] = len(getattr(report, "results", []))
        if security_report is not None:
            metadata["attacks_simulated"] = getattr(
                security_report, "total_attacks_simulated", 0
            )

        entry = HistoryEntry(
            timestamp=now,
            resilience_score=resilience_score,
            resilience_score_v2=resilience_score_v2,
            security_score=security_score,
            critical_count=critical_count,
            warning_count=warning_count,
            component_count=component_count,
            model_hash=model_hash,
            metadata=metadata,
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO history
                    (timestamp, resilience_score, resilience_score_v2,
                     security_score, critical_count, warning_count,
                     component_count, model_hash, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.timestamp,
                    entry.resilience_score,
                    entry.resilience_score_v2,
                    entry.security_score,
                    entry.critical_count,
                    entry.warning_count,
                    entry.component_count,
                    entry.model_hash,
                    json.dumps(entry.metadata),
                ),
            )

        return entry

    def get_history(self, days: int = 90) -> list[HistoryEntry]:
        """Retrieve history entries from the last N days.

        Args:
            days: Number of days to look back (default: 90).

        Returns:
            List of HistoryEntry objects ordered by timestamp ascending.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
            timespec="seconds"
        )
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, resilience_score, resilience_score_v2,
                       security_score, critical_count, warning_count,
                       component_count, model_hash, metadata_json
                FROM history
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
                """,
                (cutoff,),
            ).fetchall()

        return [
            HistoryEntry(
                timestamp=r[0],
                resilience_score=r[1],
                resilience_score_v2=r[2],
                security_score=r[3],
                critical_count=r[4],
                warning_count=r[5],
                component_count=r[6],
                model_hash=r[7],
                metadata=json.loads(r[8]) if r[8] else {},
            )
            for r in rows
        ]

    def analyze_trend(self, days: int = 90) -> TrendAnalysis:
        """Analyze score trends over the specified time period.

        Args:
            days: Number of days to analyze (default: 90).

        Returns:
            A TrendAnalysis with trend direction, deltas, and recommendations.
        """
        entries = self.get_history(days=days)

        if not entries:
            return TrendAnalysis(
                entries=[],
                score_trend="stable",
                score_change_30d=0.0,
                best_score=0.0,
                worst_score=0.0,
                regression_dates=[],
                recommendation="No history data available. Run evaluations to start tracking.",
            )

        scores = [e.resilience_score for e in entries]
        best_score = max(scores)
        worst_score = min(scores)

        # Calculate 30-day change
        now = datetime.now(timezone.utc)
        cutoff_30d = (now - timedelta(days=30)).isoformat(timespec="seconds")
        recent_entries = [e for e in entries if e.timestamp >= cutoff_30d]

        if len(recent_entries) >= 2:
            score_change_30d = recent_entries[-1].resilience_score - recent_entries[0].resilience_score
        elif len(entries) >= 2:
            score_change_30d = entries[-1].resilience_score - entries[0].resilience_score
        else:
            score_change_30d = 0.0

        # Detect regressions (score drops)
        regression_dates: list[str] = []
        for i in range(1, len(entries)):
            delta = entries[i].resilience_score - entries[i - 1].resilience_score
            if delta < -2.0:  # More than 2 points drop
                regression_dates.append(entries[i].timestamp)

        # Determine trend
        if len(entries) < 2:
            score_trend = "stable"
        elif score_change_30d > 3.0:
            score_trend = "improving"
        elif score_change_30d < -3.0:
            score_trend = "degrading"
        else:
            score_trend = "stable"

        # Generate recommendation
        recommendation = self._generate_recommendation(
            score_trend, entries[-1], regression_dates
        )

        return TrendAnalysis(
            entries=entries,
            score_trend=score_trend,
            score_change_30d=round(score_change_30d, 1),
            best_score=best_score,
            worst_score=worst_score,
            regression_dates=regression_dates,
            recommendation=recommendation,
        )

    def get_regressions(self) -> list[HistoryEntry]:
        """Get entries where the resilience score dropped significantly.

        Returns entries where the score dropped more than 2 points from the
        preceding entry.
        """
        entries = self.get_history(days=365)
        regressions: list[HistoryEntry] = []
        for i in range(1, len(entries)):
            delta = entries[i].resilience_score - entries[i - 1].resilience_score
            if delta < -2.0:
                regressions.append(entries[i])
        return regressions

    def to_json(self, days: int = 90) -> str:
        """Export history as a JSON string.

        Args:
            days: Number of days to include (default: 90).

        Returns:
            JSON string with history entries and trend analysis.
        """
        entries = self.get_history(days=days)
        trend = self.analyze_trend(days=days)
        data = {
            "entries": [
                {
                    "timestamp": e.timestamp,
                    "resilience_score": e.resilience_score,
                    "resilience_score_v2": e.resilience_score_v2,
                    "security_score": e.security_score,
                    "critical_count": e.critical_count,
                    "warning_count": e.warning_count,
                    "component_count": e.component_count,
                    "model_hash": e.model_hash,
                    "metadata": e.metadata,
                }
                for e in entries
            ],
            "trend": {
                "direction": trend.score_trend,
                "score_change_30d": trend.score_change_30d,
                "best_score": trend.best_score,
                "worst_score": trend.worst_score,
                "regression_count": len(trend.regression_dates),
                "regression_dates": trend.regression_dates,
                "recommendation": trend.recommendation,
            },
        }
        return json.dumps(data, indent=2)

    def _generate_recommendation(
        self,
        trend: str,
        latest: HistoryEntry,
        regressions: list[str],
    ) -> str:
        """Generate a human-readable recommendation based on trend data."""
        parts: list[str] = []

        if trend == "degrading":
            parts.append(
                "Resilience score is declining. Review recent infrastructure "
                "changes for regressions."
            )
        elif trend == "improving":
            parts.append(
                "Resilience score is improving. Continue applying remediations."
            )
        else:
            parts.append("Resilience score is stable.")

        if latest.critical_count > 0:
            parts.append(
                f"There are {latest.critical_count} critical findings. "
                "Address these to improve your score."
            )

        if latest.resilience_score < 50:
            parts.append(
                "Score is below 50. Consider running 'faultray auto-fix' "
                "to generate remediation code."
            )
        elif latest.resilience_score < 80:
            parts.append(
                "Score is moderate. Run 'faultray evaluate' for detailed analysis."
            )

        if len(regressions) >= 3:
            parts.append(
                f"Detected {len(regressions)} regressions. "
                "Set up CI/CD baseline checks with 'faultray simulate --baseline'."
            )

        return " ".join(parts)
