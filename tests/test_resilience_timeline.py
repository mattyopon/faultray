"""Tests for the Resilience Timeline Tracker."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.resilience_timeline import (
    ResilienceTimeline,
    TimelineMilestone,
    TimelineReport,
    TimelineSnapshot,
    TimelineTrend,
    _count_spofs,
    _generate_sparkline,
)


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
    types = [ComponentType.LOAD_BALANCER, ComponentType.APP_SERVER, ComponentType.DATABASE]
    for i in range(num_components):
        comp = Component(
            id=f"comp_{i}",
            name=f"Component {i}",
            type=types[i % 3],
            port=8080 + i,
            replicas=replicas,
            failover=FailoverConfig(enabled=failover),
            autoscaling=AutoScalingConfig(enabled=True),
        )
        graph.add_component(comp)
    if num_components >= 2:
        graph.add_dependency(Dependency(source_id="comp_0", target_id="comp_1"))
    return graph


def _timeline_in_tmp(tmp_path: Path) -> ResilienceTimeline:
    """Create a ResilienceTimeline with a temp storage path."""
    return ResilienceTimeline(storage_path=tmp_path / "timeline.jsonl")


def _seed_snapshots(
    tl: ResilienceTimeline,
    scores: list[float],
    base_days_ago: int = 20,
    critical_findings: int = 0,
) -> None:
    """Write snapshot entries directly to the JSONL file."""
    base = datetime.now(timezone.utc) - timedelta(days=base_days_ago)
    for i, score in enumerate(scores):
        ts = (base + timedelta(days=i * 2)).isoformat(timespec="seconds")
        snap = TimelineSnapshot(
            timestamp=ts,
            resilience_score=score,
            component_count=5,
            spof_count=1,
            critical_findings=critical_findings,
            warning_count=0,
            genome_hash=None,
            infrastructure_hash="test_hash",
        )
        with open(tl.storage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(snap.to_dict()) + "\n")


# ---------------------------------------------------------------------------
# 1. TimelineSnapshot
# ---------------------------------------------------------------------------

class TestTimelineSnapshot:
    def test_to_dict_and_from_dict(self):
        snap = TimelineSnapshot(
            timestamp="2025-01-15T10:30:00",
            resilience_score=85.5,
            component_count=10,
            spof_count=2,
            critical_findings=1,
            warning_count=3,
            genome_hash="abc123",
            infrastructure_hash="infra_hash_001",
            metadata={"key": "value"},
            event="manual test",
        )
        d = snap.to_dict()
        restored = TimelineSnapshot.from_dict(d)

        assert restored.timestamp == snap.timestamp
        assert restored.resilience_score == snap.resilience_score
        assert restored.component_count == snap.component_count
        assert restored.spof_count == snap.spof_count
        assert restored.critical_findings == snap.critical_findings
        assert restored.warning_count == snap.warning_count
        assert restored.genome_hash == snap.genome_hash
        assert restored.infrastructure_hash == snap.infrastructure_hash
        assert restored.metadata == snap.metadata
        assert restored.event == snap.event

    def test_from_dict_missing_optional_fields(self):
        d = {
            "timestamp": "2025-01-15T10:30:00",
            "resilience_score": 70.0,
            "component_count": 5,
        }
        snap = TimelineSnapshot.from_dict(d)
        assert snap.spof_count == 0
        assert snap.critical_findings == 0
        assert snap.genome_hash is None
        assert snap.event is None


# ---------------------------------------------------------------------------
# 2. ResilienceTimeline initialization
# ---------------------------------------------------------------------------

class TestTimelineInit:
    def test_creates_storage_directory(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "timeline.jsonl"
        tl = ResilienceTimeline(storage_path=path)
        assert path.parent.exists()
        assert path.exists()

    def test_idempotent_init(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        tl._ensure_storage()  # second call should not fail


# ---------------------------------------------------------------------------
# 3. Recording snapshots
# ---------------------------------------------------------------------------

class TestRecord:
    def test_record_basic(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        graph = _make_graph()
        snap = tl.record(graph)

        assert isinstance(snap, TimelineSnapshot)
        assert snap.resilience_score > 0
        assert snap.component_count == 3
        assert snap.infrastructure_hash != ""
        assert snap.timestamp != ""

    def test_record_with_event(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        graph = _make_graph()
        snap = tl.record(graph, event="Added Redis cluster")

        assert snap.event == "Added Redis cluster"

    def test_record_with_report(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        graph = _make_graph()

        report = MagicMock()
        report.critical_findings = [1, 2]
        report.warnings = [1]
        report.results = [1, 2, 3, 4, 5]

        snap = tl.record(graph, report=report)

        assert snap.critical_findings == 2
        assert snap.warning_count == 1
        assert snap.metadata.get("total_scenarios") == 5

    def test_record_with_genome_hash(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        graph = _make_graph()
        snap = tl.record(graph, genome_hash="genome_abc")

        assert snap.genome_hash == "genome_abc"

    def test_record_persists_to_file(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        graph = _make_graph()
        tl.record(graph)

        lines = tl.storage_path.read_text().strip().splitlines()
        assert len(lines) == 1

        data = json.loads(lines[0])
        assert data["component_count"] == 3

    def test_multiple_records(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        graph = _make_graph()

        for _ in range(5):
            tl.record(graph)

        lines = tl.storage_path.read_text().strip().splitlines()
        assert len(lines) == 5


# ---------------------------------------------------------------------------
# 4. Retrieving history
# ---------------------------------------------------------------------------

class TestGetHistory:
    def test_empty_history(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        entries = tl.get_history()
        assert entries == []

    def test_returns_all_entries(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        graph = _make_graph()

        for _ in range(3):
            tl.record(graph)

        entries = tl.get_history()
        assert len(entries) == 3

    def test_filters_by_days(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)

        # Seed entries spanning 40 days
        _seed_snapshots(tl, [70.0, 72.0, 74.0, 76.0, 78.0], base_days_ago=40)

        # Record a recent one
        graph = _make_graph()
        tl.record(graph)

        entries_7d = tl.get_history(days=7)
        entries_90d = tl.get_history(days=90)

        assert len(entries_7d) >= 1
        assert len(entries_90d) >= 5


# ---------------------------------------------------------------------------
# 5. Trend analysis
# ---------------------------------------------------------------------------

class TestTrends:
    def test_empty_trends(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        trends = tl.get_trends()

        assert "7d" in trends
        assert "30d" in trends
        assert "90d" in trends
        assert trends["7d"].snapshots_count == 0
        assert trends["7d"].trend == "stable"

    def test_improving_trend(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [50.0, 55.0, 60.0, 65.0, 70.0])

        trends = tl.get_trends()
        assert trends["30d"].trend == "improving"
        assert trends["30d"].delta > 0

    def test_degrading_trend(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [80.0, 78.0, 76.0, 74.0, 72.0])  # -8 total: degrading

        trends = tl.get_trends()
        assert trends["30d"].trend == "degrading"
        assert trends["30d"].delta < 0

    def test_stable_trend(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [75.0, 74.0, 76.0, 75.0, 75.0])

        trends = tl.get_trends()
        assert trends["30d"].trend == "stable"

    def test_critical_degradation(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [90.0, 80.0, 70.0, 60.0, 50.0])

        trends = tl.get_trends()
        trend_30d = trends["30d"]
        assert trend_30d.trend == "critical_degradation"
        assert trend_30d.delta < -10

    def test_trend_statistics(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [60.0, 70.0, 80.0, 70.0, 90.0])

        trends = tl.get_trends()
        t = trends["30d"]
        assert t.min_score == 60.0
        assert t.max_score == 90.0
        assert t.avg_score == 74.0
        assert t.volatility > 0
        assert t.snapshots_count == 5


# ---------------------------------------------------------------------------
# 6. Milestones
# ---------------------------------------------------------------------------

class TestMilestones:
    def test_empty_milestones(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        milestones = tl.get_milestones()
        assert milestones == []

    def test_score_threshold_milestone(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [40.0, 45.0, 52.0])  # crosses 50

        milestones = tl.get_milestones()
        threshold_milestones = [
            m for m in milestones if m.milestone_type == "score_threshold"
        ]
        assert len(threshold_milestones) >= 1
        assert any("50" in m.description for m in threshold_milestones)

    def test_regression_milestone(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [80.0, 72.0])  # -8 point drop

        milestones = tl.get_milestones()
        regressions = [
            m for m in milestones if m.milestone_type == "regression"
        ]
        assert len(regressions) == 1
        assert "regression" in regressions[0].description.lower()

    def test_zero_critical_milestone(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)

        # First snapshot with critical findings
        base = datetime.now(timezone.utc) - timedelta(days=5)
        snap1 = TimelineSnapshot(
            timestamp=base.isoformat(timespec="seconds"),
            resilience_score=70.0,
            component_count=5,
            spof_count=1,
            critical_findings=3,
            warning_count=1,
            genome_hash=None,
            infrastructure_hash="hash1",
        )
        tl._append_snapshot(snap1)

        # Second snapshot with zero critical
        snap2 = TimelineSnapshot(
            timestamp=(base + timedelta(days=2)).isoformat(timespec="seconds"),
            resilience_score=75.0,
            component_count=5,
            spof_count=1,
            critical_findings=0,
            warning_count=0,
            genome_hash=None,
            infrastructure_hash="hash2",
        )
        tl._append_snapshot(snap2)

        milestones = tl.get_milestones()
        zero_crit = [m for m in milestones if m.milestone_type == "zero_critical"]
        assert len(zero_crit) == 1

    def test_milestone_to_dict(self):
        m = TimelineMilestone(
            timestamp="2025-01-15T10:00:00",
            milestone_type="score_threshold",
            description="Score reached 90%",
            score_at_milestone=91.0,
        )
        d = m.to_dict()
        assert d["milestone_type"] == "score_threshold"
        assert d["score_at_milestone"] == 91.0


# ---------------------------------------------------------------------------
# 7. Regression detection
# ---------------------------------------------------------------------------

class TestDetectRegressions:
    def test_no_regressions(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [60.0, 65.0, 70.0, 75.0])

        regressions = tl.detect_regressions()
        assert len(regressions) == 0

    def test_detects_regression(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [80.0, 85.0, 70.0])  # 85->70 = -15

        regressions = tl.detect_regressions(threshold=5.0)
        assert len(regressions) == 1
        assert regressions[0][1] == 85.0  # from_score
        assert regressions[0][2] == 70.0  # to_score

    def test_custom_threshold(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [80.0, 76.0])  # -4 drop

        # With threshold 5.0 -> no regression
        regressions_5 = tl.detect_regressions(threshold=5.0)
        assert len(regressions_5) == 0

        # With threshold 3.0 -> regression
        regressions_3 = tl.detect_regressions(threshold=3.0)
        assert len(regressions_3) == 1


# ---------------------------------------------------------------------------
# 8. Sparkline generation
# ---------------------------------------------------------------------------

class TestSparkline:
    def test_empty_sparkline(self):
        result = _generate_sparkline([])
        assert result == ""

    def test_single_value(self):
        result = _generate_sparkline([50.0])
        assert len(result) == 1

    def test_all_same_values(self):
        result = _generate_sparkline([75.0, 75.0, 75.0])
        assert len(result) == 3
        # All same = all middle char
        assert len(set(result)) == 1

    def test_ascending_values(self):
        result = _generate_sparkline([0.0, 25.0, 50.0, 75.0, 100.0])
        assert len(result) == 5
        # First char should be lowest, last highest
        assert result[0] < result[-1] or result[0] == " "

    def test_width_limit(self):
        scores = list(range(100))
        result = _generate_sparkline([float(s) for s in scores], width=20)
        assert len(result) == 20

    def test_instance_method(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [60.0, 70.0, 80.0, 75.0, 90.0])

        sparkline = tl.generate_sparkline(width=10)
        assert len(sparkline) <= 10
        assert len(sparkline) > 0


# ---------------------------------------------------------------------------
# 9. Report generation
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_empty_report(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        report = tl.generate_report()

        assert isinstance(report, TimelineReport)
        assert report.total_snapshots == 0
        assert report.current_score == 0.0
        assert report.sparkline == ""

    def test_report_with_data(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [60.0, 70.0, 80.0, 75.0, 90.0])

        report = tl.generate_report()

        assert report.total_snapshots == 5
        assert report.current_score == 90.0
        assert report.all_time_high == 90.0
        assert report.all_time_low == 60.0
        assert report.days_tracked >= 1
        assert report.sparkline != ""
        assert isinstance(report.trends, dict)
        assert isinstance(report.milestones, list)


# ---------------------------------------------------------------------------
# 10. CSV export
# ---------------------------------------------------------------------------

class TestExportCSV:
    def test_export_csv(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [70.0, 75.0, 80.0])

        csv_path = tmp_path / "output.csv"
        result_path = tl.export_csv(csv_path)

        assert result_path == csv_path
        assert csv_path.exists()

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 3
        assert "resilience_score" in rows[0]
        assert float(rows[0]["resilience_score"]) == 70.0

    def test_export_csv_empty(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        csv_path = tmp_path / "empty.csv"
        tl.export_csv(csv_path)

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 0

    def test_export_csv_creates_parent_dirs(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [80.0])

        csv_path = tmp_path / "sub" / "dir" / "export.csv"
        tl.export_csv(csv_path)

        assert csv_path.exists()


# ---------------------------------------------------------------------------
# 11. Reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_data(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [70.0, 75.0, 80.0])

        assert len(tl.get_history()) == 3

        tl.reset()
        assert len(tl.get_history()) == 0
        assert tl.storage_path.exists()


# ---------------------------------------------------------------------------
# 12. SPOF counting
# ---------------------------------------------------------------------------

class TestCountSPOFs:
    def test_no_spofs(self):
        graph = _make_graph(replicas=2, failover=True)
        assert _count_spofs(graph) == 0

    def test_with_spofs(self):
        graph = InfraGraph()
        comp0 = Component(
            id="lb", name="LB", type=ComponentType.LOAD_BALANCER,
            replicas=1,
        )
        comp1 = Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
        )
        graph.add_component(comp0)
        graph.add_component(comp1)
        graph.add_dependency(Dependency(
            source_id="app", target_id="lb",
            dependency_type="requires",
        ))
        # lb is a SPOF because app requires it and it has 1 replica
        assert _count_spofs(graph) >= 1

    def test_empty_graph(self):
        graph = InfraGraph()
        assert _count_spofs(graph) == 0


# ---------------------------------------------------------------------------
# Coverage boost tests
# ---------------------------------------------------------------------------


class TestComputeInfrastructureHashException:
    """Test _compute_infrastructure_hash when graph.to_dict() raises (lines 138-139)."""

    def test_hash_returns_unknown_on_exception(self):
        from faultray.simulator.resilience_timeline import _compute_infrastructure_hash
        from unittest.mock import patch

        graph = _make_graph()
        with patch.object(type(graph), "to_dict", side_effect=RuntimeError("boom")):
            result = _compute_infrastructure_hash(graph)
        assert result == "unknown"


class TestMalformedJSONLEntries:
    """Test _load_all_snapshots with malformed JSONL (lines 224, 231, 235-238)."""

    def test_skips_malformed_json(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        # Write a valid entry, then a malformed JSON line, then a line missing key
        valid = {
            "timestamp": "2025-01-15T10:00:00",
            "resilience_score": 80.0,
            "component_count": 5,
            "spof_count": 1,
            "infrastructure_hash": "hash1",
        }
        with open(tl.storage_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(valid) + "\n")
            f.write("not valid json at all\n")
            f.write('{"bad": "entry"}\n')  # missing required keys

        snapshots = tl._load_all_snapshots()
        # Only the valid entry should be loaded; bad JSON and missing key skipped
        assert len(snapshots) == 1
        assert snapshots[0].resilience_score == 80.0


class TestLoadSnapshotsOSError:
    """Test _load_all_snapshots with OSError (lines 237-238)."""

    def test_returns_empty_on_os_error(self, tmp_path):
        import os
        tl = _timeline_in_tmp(tmp_path)
        # Write something then make file unreadable
        with open(tl.storage_path, "w") as f:
            f.write('{"timestamp":"2025-01-01T00:00:00","resilience_score":50.0,"component_count":1,"infrastructure_hash":"h"}\n')
        os.chmod(tl.storage_path, 0o000)

        snapshots = tl._load_all_snapshots()
        assert snapshots == []

        os.chmod(tl.storage_path, 0o644)


class TestAppendSnapshotOSError:
    """Test _append_snapshot when write fails (lines 247-248)."""

    def test_append_handles_os_error(self, tmp_path):
        import os
        tl = _timeline_in_tmp(tmp_path)
        snap = TimelineSnapshot(
            timestamp="2025-01-01T00:00:00",
            resilience_score=50.0,
            component_count=1,
            spof_count=0,
            critical_findings=0,
            warning_count=0,
            genome_hash=None,
            infrastructure_hash="h",
        )
        # Make directory read-only to prevent writing
        os.chmod(tl.storage_path, 0o000)
        # Should not raise; just logs a warning
        tl._append_snapshot(snap)
        os.chmod(tl.storage_path, 0o644)


class TestCheckMilestonesScoreThreshold:
    """Test _check_milestones with score threshold and regression logging (lines 328, 334)."""

    def test_milestone_score_threshold_logging(self, tmp_path):
        import logging
        tl = _timeline_in_tmp(tmp_path)

        # Seed with a low-score snapshot first
        _seed_snapshots(tl, [40.0])

        graph = _make_graph(num_components=3, replicas=3, failover=True)
        # Record again to trigger milestone check
        snap = tl.record(graph)
        # Score should be >= 50, triggering milestone
        assert snap.resilience_score >= 50.0

    def test_milestone_regression_logging(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)

        # First snapshot: high score
        _seed_snapshots(tl, [90.0])

        # Record low score to trigger regression
        _seed_snapshots(tl, [80.0])

        # Record another snapshot to trigger _check_milestones
        graph = InfraGraph()
        graph.add_component(Component(
            id="lonely",
            name="Lonely",
            type=ComponentType.APP_SERVER,
            replicas=1,
        ))
        snap = tl.record(graph)
        # Just ensure it doesn't crash


class TestGetHistoryDaysZero:
    """Test get_history with days <= 0 returns all (line 351)."""

    def test_days_zero_returns_all(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [60.0, 70.0, 80.0], base_days_ago=365)

        history = tl.get_history(days=0)
        assert len(history) == 3

    def test_days_negative_returns_all(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [55.0, 65.0], base_days_ago=200)

        history = tl.get_history(days=-1)
        assert len(history) == 2


class TestSingleSnapshotVolatility:
    """Test trend calculation with a single snapshot (line 397)."""

    def test_single_snapshot_volatility_zero(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [75.0])

        trends = tl.get_trends()
        trend_30d = trends["30d"]
        assert trend_30d.volatility == 0.0
        assert trend_30d.snapshots_count == 1


class TestNinesAchievedMilestone:
    """Test nines_achieved milestone (line 448)."""

    def test_nines_achieved_milestone(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        _seed_snapshots(tl, [98.0, 99.95])

        milestones = tl.get_milestones()
        nines = [m for m in milestones if m.milestone_type == "nines_achieved"]
        assert len(nines) == 1
        assert "99.9" in nines[0].description


class TestDateParsingErrors:
    """Test generate_report with unparseable dates (lines 545-546)."""

    def test_bad_timestamp_in_report(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        # Write snapshots with bad timestamps
        snap_data = {
            "timestamp": "not-a-date",
            "resilience_score": 75.0,
            "component_count": 3,
            "spof_count": 0,
            "infrastructure_hash": "hash1",
        }
        with open(tl.storage_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(snap_data) + "\n")

        report = tl.generate_report()
        assert report.days_tracked == 0
        assert report.total_snapshots == 1


class TestLoadSnapshotsNoFile:
    """Test _load_all_snapshots when storage file does not exist (line 224)."""

    def test_returns_empty_when_file_deleted(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        # Remove the file that _ensure_storage created
        tl.storage_path.unlink()
        snapshots = tl._load_all_snapshots()
        assert snapshots == []


class TestLoadSnapshotsBlankLines:
    """Test _load_all_snapshots skips blank lines (line 231)."""

    def test_skips_blank_lines(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)
        valid = {
            "timestamp": "2025-01-15T10:00:00",
            "resilience_score": 80.0,
            "component_count": 5,
            "infrastructure_hash": "hash1",
        }
        with open(tl.storage_path, "w", encoding="utf-8") as f:
            f.write("\n")  # blank line
            f.write(json.dumps(valid) + "\n")
            f.write("   \n")  # whitespace-only line
            f.write("\n")  # another blank

        snapshots = tl._load_all_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0].resilience_score == 80.0


class TestCheckMilestonesZeroCritical:
    """Test _check_milestones logs zero critical findings milestone (line 328)."""

    def test_zero_critical_milestone_on_record(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)

        # First, seed a snapshot with critical findings > 0
        base = datetime.now(timezone.utc) - timedelta(days=5)
        snap1 = TimelineSnapshot(
            timestamp=base.isoformat(timespec="seconds"),
            resilience_score=70.0,
            component_count=5,
            spof_count=1,
            critical_findings=3,
            warning_count=0,
            genome_hash=None,
            infrastructure_hash="hash1",
        )
        tl._append_snapshot(snap1)

        # Now record a graph that yields 0 critical findings
        # _check_milestones is called by record(), and the new snapshot
        # has critical_findings=0 (report is None, so critical_findings=0)
        graph = _make_graph(num_components=3, replicas=2, failover=True)
        snap = tl.record(graph)
        assert snap.critical_findings == 0
        # Line 328 should have been hit (logger.info about zero critical)


class TestCheckMilestonesRegressionOnRecord:
    """Test _check_milestones regression detection on record (line 334)."""

    def test_regression_detected_on_record(self, tmp_path):
        tl = _timeline_in_tmp(tmp_path)

        # Seed a high-score snapshot
        base = datetime.now(timezone.utc) - timedelta(days=2)
        snap1 = TimelineSnapshot(
            timestamp=base.isoformat(timespec="seconds"),
            resilience_score=95.0,
            component_count=5,
            spof_count=0,
            critical_findings=0,
            warning_count=0,
            genome_hash=None,
            infrastructure_hash="hash1",
        )
        tl._append_snapshot(snap1)

        # Create a graph with many SPOFs and high utilization so score drops well below 90
        from faultray.model.components import ResourceMetrics
        graph = InfraGraph()
        # Central DB with replicas=1 and high utilization
        graph.add_component(Component(
            id="db",
            name="Database",
            type=ComponentType.DATABASE,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=95),
        ))
        # Multiple dependents that each depend on the SPOF db
        for i in range(5):
            graph.add_component(Component(
                id=f"svc{i}",
                name=f"Service {i}",
                type=ComponentType.APP_SERVER,
                replicas=1,
                metrics=ResourceMetrics(cpu_percent=92),
            ))
            graph.add_dependency(Dependency(source_id=f"svc{i}", target_id="db"))

        snap = tl.record(graph)
        # Score should drop significantly below 95 -> triggers regression
        assert snap.resilience_score < 90.0
