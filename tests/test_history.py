"""Tests for historical trend tracking (history.py)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from faultray.history import HistoryEntry, HistoryTracker, TrendAnalysis, _compute_model_hash
from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_graph(
    num_components: int = 3,
    replicas: int = 2,
    failover: bool = True,
) -> InfraGraph:
    """Create a simple InfraGraph for testing."""
    graph = InfraGraph()
    for i in range(num_components):
        ctype = [ComponentType.LOAD_BALANCER, ComponentType.APP_SERVER, ComponentType.DATABASE][i % 3]
        comp = Component(
            id=f"comp_{i}",
            name=f"Component {i}",
            type=ctype,
            port=8080 + i,
            replicas=replicas,
            failover=FailoverConfig(enabled=failover),
            autoscaling=AutoScalingConfig(enabled=True),
        )
        graph.add_component(comp)
    if num_components >= 2:
        graph.add_dependency(Dependency(source_id="comp_0", target_id="comp_1"))
    return graph


def _tracker_in_tmp(tmp_path: Path) -> HistoryTracker:
    """Create a HistoryTracker with a temp database."""
    return HistoryTracker(db_path=tmp_path / "test_history.db")


# ---------------------------------------------------------------------------
# 1. HistoryTracker initialization
# ---------------------------------------------------------------------------

class TestHistoryTrackerInit:
    def test_creates_db_directory(self, tmp_path):
        db = tmp_path / "sub" / "dir" / "history.db"
        tracker = HistoryTracker(db_path=db)
        assert db.parent.exists()

    def test_creates_table(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)
        conn = sqlite3.connect(str(tracker.db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='history'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_idempotent_init(self, tmp_path):
        """Calling _init_db twice should not fail."""
        tracker = _tracker_in_tmp(tmp_path)
        tracker._init_db()  # second call


# ---------------------------------------------------------------------------
# 2. Recording entries
# ---------------------------------------------------------------------------

class TestRecord:
    def test_record_basic(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)
        graph = _make_graph()
        entry = tracker.record(graph)

        assert isinstance(entry, HistoryEntry)
        assert entry.resilience_score > 0
        assert entry.component_count == 3
        assert entry.model_hash != ""
        assert entry.timestamp != ""

    def test_record_with_report(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)
        graph = _make_graph()

        # Mock a SimulationReport
        report = MagicMock()
        report.critical_findings = [1, 2]  # 2 critical
        report.warnings = [1]  # 1 warning
        report.results = [1, 2, 3, 4, 5]

        entry = tracker.record(graph, report=report)

        assert entry.critical_count == 2
        assert entry.warning_count == 1
        assert entry.metadata.get("total_scenarios") == 5

    def test_record_with_security_report(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)
        graph = _make_graph()

        sec_report = MagicMock()
        sec_report.security_resilience_score = 75.0
        sec_report.total_attacks_simulated = 10

        entry = tracker.record(graph, security_report=sec_report)

        assert entry.security_score == 75.0
        assert entry.metadata.get("attacks_simulated") == 10

    def test_record_persists_to_db(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)
        graph = _make_graph()
        tracker.record(graph)

        conn = sqlite3.connect(str(tracker.db_path))
        count = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        conn.close()
        assert count == 1


# ---------------------------------------------------------------------------
# 3. Retrieving history
# ---------------------------------------------------------------------------

class TestGetHistory:
    def test_empty_history(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)
        entries = tracker.get_history()
        assert entries == []

    def test_returns_entries_in_order(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)
        graph = _make_graph()

        # Record 3 entries
        for _ in range(3):
            tracker.record(graph)

        entries = tracker.get_history()
        assert len(entries) == 3
        # Timestamps should be ascending
        for i in range(1, len(entries)):
            assert entries[i].timestamp >= entries[i - 1].timestamp

    def test_filters_by_days(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)
        graph = _make_graph()

        # Insert an old entry directly
        old_date = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(timespec="seconds")
        conn = sqlite3.connect(str(tracker.db_path))
        conn.execute(
            """INSERT INTO history
            (timestamp, resilience_score, resilience_score_v2, security_score,
             critical_count, warning_count, component_count, model_hash, metadata_json)
            VALUES (?, 50.0, 40.0, 0.0, 0, 0, 3, 'old', '{}')""",
            (old_date,),
        )
        conn.commit()
        conn.close()

        # Record a current entry
        tracker.record(graph)

        # 90 day filter should only return the recent one
        entries_90 = tracker.get_history(days=90)
        assert len(entries_90) == 1

        # 365 day filter should return both
        entries_365 = tracker.get_history(days=365)
        assert len(entries_365) == 2


# ---------------------------------------------------------------------------
# 4. Trend analysis
# ---------------------------------------------------------------------------

class TestAnalyzeTrend:
    def test_empty_trend(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)
        trend = tracker.analyze_trend()

        assert trend.score_trend == "stable"
        assert trend.score_change_30d == 0.0
        assert trend.entries == []
        assert "No history" in trend.recommendation

    def test_stable_trend(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)
        graph = _make_graph(replicas=2, failover=True)

        for _ in range(5):
            tracker.record(graph)

        trend = tracker.analyze_trend()
        assert trend.score_trend == "stable"
        assert len(trend.entries) == 5

    def test_improving_trend(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)

        # Insert entries with increasing scores
        conn = sqlite3.connect(str(tracker.db_path))
        base = datetime.now(timezone.utc) - timedelta(days=20)
        for i in range(5):
            ts = (base + timedelta(days=i * 5)).isoformat(timespec="seconds")
            score = 50.0 + i * 5.0  # 50, 55, 60, 65, 70
            conn.execute(
                """INSERT INTO history
                (timestamp, resilience_score, resilience_score_v2, security_score,
                 critical_count, warning_count, component_count, model_hash, metadata_json)
                VALUES (?, ?, 0.0, 0.0, 0, 0, 3, 'test', '{}')""",
                (ts, score),
            )
        conn.commit()
        conn.close()

        trend = tracker.analyze_trend(days=30)
        assert trend.score_trend == "improving"
        assert trend.score_change_30d > 0

    def test_degrading_trend(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)

        conn = sqlite3.connect(str(tracker.db_path))
        base = datetime.now(timezone.utc) - timedelta(days=20)
        for i in range(5):
            ts = (base + timedelta(days=i * 5)).isoformat(timespec="seconds")
            score = 80.0 - i * 5.0  # 80, 75, 70, 65, 60
            conn.execute(
                """INSERT INTO history
                (timestamp, resilience_score, resilience_score_v2, security_score,
                 critical_count, warning_count, component_count, model_hash, metadata_json)
                VALUES (?, ?, 0.0, 0.0, 0, 0, 3, 'test', '{}')""",
                (ts, score),
            )
        conn.commit()
        conn.close()

        trend = tracker.analyze_trend(days=30)
        assert trend.score_trend == "degrading"
        assert trend.score_change_30d < 0

    def test_detects_regressions(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)

        conn = sqlite3.connect(str(tracker.db_path))
        base = datetime.now(timezone.utc) - timedelta(days=10)
        scores = [80.0, 82.0, 70.0, 72.0, 60.0]  # Two regressions: 82->70, 72->60
        for i, score in enumerate(scores):
            ts = (base + timedelta(days=i * 2)).isoformat(timespec="seconds")
            conn.execute(
                """INSERT INTO history
                (timestamp, resilience_score, resilience_score_v2, security_score,
                 critical_count, warning_count, component_count, model_hash, metadata_json)
                VALUES (?, ?, 0.0, 0.0, 0, 0, 3, 'test', '{}')""",
                (ts, score),
            )
        conn.commit()
        conn.close()

        trend = tracker.analyze_trend(days=30)
        assert len(trend.regression_dates) == 2

    def test_best_worst_scores(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)

        conn = sqlite3.connect(str(tracker.db_path))
        base = datetime.now(timezone.utc) - timedelta(days=10)
        scores = [60.0, 85.0, 40.0, 90.0, 70.0]
        for i, score in enumerate(scores):
            ts = (base + timedelta(days=i * 2)).isoformat(timespec="seconds")
            conn.execute(
                """INSERT INTO history
                (timestamp, resilience_score, resilience_score_v2, security_score,
                 critical_count, warning_count, component_count, model_hash, metadata_json)
                VALUES (?, ?, 0.0, 0.0, 0, 0, 3, 'test', '{}')""",
                (ts, score),
            )
        conn.commit()
        conn.close()

        trend = tracker.analyze_trend(days=30)
        assert trend.best_score == 90.0
        assert trend.worst_score == 40.0


# ---------------------------------------------------------------------------
# 5. Get regressions
# ---------------------------------------------------------------------------

class TestGetRegressions:
    def test_no_regressions(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)
        graph = _make_graph()
        for _ in range(3):
            tracker.record(graph)

        regressions = tracker.get_regressions()
        assert len(regressions) == 0

    def test_with_regressions(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)

        conn = sqlite3.connect(str(tracker.db_path))
        base = datetime.now(timezone.utc) - timedelta(days=5)
        # 80 -> 75 = -5 (regression), 75 -> 60 = -15 (regression)
        scores = [80.0, 75.0, 60.0]
        for i, score in enumerate(scores):
            ts = (base + timedelta(days=i)).isoformat(timespec="seconds")
            conn.execute(
                """INSERT INTO history
                (timestamp, resilience_score, resilience_score_v2, security_score,
                 critical_count, warning_count, component_count, model_hash, metadata_json)
                VALUES (?, ?, 0.0, 0.0, 0, 0, 3, 'test', '{}')""",
                (ts, score),
            )
        conn.commit()
        conn.close()

        regressions = tracker.get_regressions()
        assert len(regressions) == 2
        # Both drops > 2 points qualify as regressions
        assert regressions[0].resilience_score == 75.0
        assert regressions[1].resilience_score == 60.0


# ---------------------------------------------------------------------------
# 6. JSON export
# ---------------------------------------------------------------------------

class TestJsonExport:
    def test_to_json(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)
        graph = _make_graph()
        tracker.record(graph)

        json_str = tracker.to_json(days=90)
        data = json.loads(json_str)

        assert "entries" in data
        assert "trend" in data
        assert len(data["entries"]) == 1
        assert data["trend"]["direction"] == "stable"


# ---------------------------------------------------------------------------
# 7. Model hash
# ---------------------------------------------------------------------------

class TestModelHash:
    def test_compute_model_hash(self):
        graph = _make_graph()
        h = _compute_model_hash(graph)
        assert isinstance(h, str)
        assert len(h) == 16

    def test_same_graph_same_hash(self):
        g1 = _make_graph(num_components=2)
        g2 = _make_graph(num_components=2)
        assert _compute_model_hash(g1) == _compute_model_hash(g2)

    def test_different_graph_different_hash(self):
        g1 = _make_graph(num_components=2)
        g2 = _make_graph(num_components=4)
        assert _compute_model_hash(g1) != _compute_model_hash(g2)


# ---------------------------------------------------------------------------
# 8. Recommendation generation
# ---------------------------------------------------------------------------

class TestRecommendations:
    def test_low_score_recommendation(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)

        conn = sqlite3.connect(str(tracker.db_path))
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            """INSERT INTO history
            (timestamp, resilience_score, resilience_score_v2, security_score,
             critical_count, warning_count, component_count, model_hash, metadata_json)
            VALUES (?, 30.0, 25.0, 0.0, 5, 3, 3, 'test', '{}')""",
            (ts,),
        )
        conn.commit()
        conn.close()

        trend = tracker.analyze_trend()
        assert "auto-fix" in trend.recommendation.lower() or "below 50" in trend.recommendation.lower()

    def test_critical_findings_recommendation(self, tmp_path):
        tracker = _tracker_in_tmp(tmp_path)

        conn = sqlite3.connect(str(tracker.db_path))
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            """INSERT INTO history
            (timestamp, resilience_score, resilience_score_v2, security_score,
             critical_count, warning_count, component_count, model_hash, metadata_json)
            VALUES (?, 70.0, 65.0, 0.0, 3, 0, 5, 'test', '{}')""",
            (ts,),
        )
        conn.commit()
        conn.close()

        trend = tracker.analyze_trend()
        assert "critical" in trend.recommendation.lower()
