# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Resilience Timeline - Track infrastructure resilience evolution over time.

Records resilience scores, genome traits, and key events over time, enabling
teams to see whether their infrastructure is improving or degrading.

Features:
- Automatic snapshot on every simulation run
- Score trend analysis (improving/degrading/stable)
- Event correlation (score changes tied to infrastructure changes)
- Milestone tracking (when you first hit 99.9%, etc.)
- Regression detection (automatic alert when score drops)
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Block characters for sparkline rendering (low to high)
_SPARK_CHARS = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"

# Default storage path
_DEFAULT_TIMELINE_PATH = Path.home() / ".faultzero" / "timeline.jsonl"


@dataclass
class TimelineSnapshot:
    """A single point-in-time resilience snapshot."""

    timestamp: str  # ISO 8601
    resilience_score: float
    component_count: int
    spof_count: int
    critical_findings: int
    warning_count: int
    genome_hash: str | None
    infrastructure_hash: str  # hash of the graph for change detection
    metadata: dict = field(default_factory=dict)
    event: str | None = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "resilience_score": self.resilience_score,
            "component_count": self.component_count,
            "spof_count": self.spof_count,
            "critical_findings": self.critical_findings,
            "warning_count": self.warning_count,
            "genome_hash": self.genome_hash,
            "infrastructure_hash": self.infrastructure_hash,
            "metadata": self.metadata,
            "event": self.event,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TimelineSnapshot:
        return cls(
            timestamp=data["timestamp"],
            resilience_score=data["resilience_score"],
            component_count=data["component_count"],
            spof_count=data.get("spof_count", 0),
            critical_findings=data.get("critical_findings", 0),
            warning_count=data.get("warning_count", 0),
            genome_hash=data.get("genome_hash"),
            infrastructure_hash=data.get("infrastructure_hash", ""),
            metadata=data.get("metadata", {}),
            event=data.get("event"),
        )


@dataclass
class TimelineMilestone:
    """A significant event in the resilience timeline."""

    timestamp: str
    milestone_type: str  # score_threshold, zero_critical, nines_achieved, regression
    description: str
    score_at_milestone: float

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "milestone_type": self.milestone_type,
            "description": self.description,
            "score_at_milestone": self.score_at_milestone,
        }


@dataclass
class TimelineTrend:
    """Trend analysis for a specific time period."""

    period: str  # "7d", "30d", "90d"
    start_score: float
    end_score: float
    delta: float
    trend: str  # "improving", "stable", "degrading", "critical_degradation"
    avg_score: float
    min_score: float
    max_score: float
    volatility: float  # standard deviation
    snapshots_count: int


@dataclass
class TimelineReport:
    """Complete timeline report with all analytics."""

    snapshots: list[TimelineSnapshot]
    milestones: list[TimelineMilestone]
    trends: dict[str, TimelineTrend]  # period -> trend
    current_score: float
    all_time_high: float
    all_time_low: float
    days_tracked: int
    total_snapshots: int
    regressions: list[tuple[str, float, float]]  # (timestamp, from_score, to_score)
    sparkline: str  # ASCII sparkline


def _compute_infrastructure_hash(graph: InfraGraph) -> str:
    """Compute a deterministic hash of the infrastructure graph."""
    try:
        data = graph.to_dict()
        raw = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    except Exception:
        return "unknown"


def _count_spofs(graph: InfraGraph) -> int:
    """Count single points of failure in the graph."""
    spof_count = 0
    for comp in graph.components.values():
        dependents = graph.get_dependents(comp.id)
        if comp.replicas <= 1 and len(dependents) > 0:
            # Check if any dependent has a 'requires' dependency
            for dep_comp in dependents:
                edge = graph.get_dependency_edge(dep_comp.id, comp.id)
                if edge and edge.dependency_type == "requires":
                    spof_count += 1
                    break
    return spof_count


def _generate_sparkline(scores: list[float], width: int = 40) -> str:
    """Generate an ASCII sparkline from a list of scores.

    Uses Unicode block characters to create a mini chart.
    """
    if not scores:
        return ""

    # Downsample if too many points
    if len(scores) > width:
        step = len(scores) / width
        sampled = []
        for i in range(width):
            idx = int(i * step)
            sampled.append(scores[idx])
        scores = sampled

    min_val = min(scores)
    max_val = max(scores)
    value_range = max_val - min_val

    if value_range == 0:
        # All values are the same
        return _SPARK_CHARS[4] * len(scores)

    chars = []
    for score in scores:
        normalized = (score - min_val) / value_range
        idx = int(normalized * (len(_SPARK_CHARS) - 1))
        idx = max(0, min(len(_SPARK_CHARS) - 1, idx))
        chars.append(_SPARK_CHARS[idx])

    return "".join(chars)


def _classify_trend(delta: float, volatility: float) -> str:
    """Classify a trend based on score delta and volatility."""
    if delta > 5.0:
        return "improving"
    elif delta < -10.0:
        return "critical_degradation"
    elif delta < -3.0:
        return "degrading"
    else:
        return "stable"


class ResilienceTimeline:
    """Track and analyze infrastructure resilience evolution over time.

    Stores snapshots in a JSON Lines file for simplicity and portability.
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or _DEFAULT_TIMELINE_PATH
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        """Ensure the storage directory and file exist."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            self.storage_path.touch()

    def _load_all_snapshots(self) -> list[TimelineSnapshot]:
        """Load all snapshots from the JSONL file."""
        snapshots: list[TimelineSnapshot] = []
        if not self.storage_path.exists():
            return snapshots

        try:
            text = self.storage_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    snapshots.append(TimelineSnapshot.from_dict(data))
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.debug("Skipping malformed timeline entry: %s", exc)
        except OSError as exc:
            logger.warning("Failed to read timeline file: %s", exc)

        return snapshots

    def _append_snapshot(self, snapshot: TimelineSnapshot) -> None:
        """Append a snapshot to the JSONL file."""
        try:
            with open(self.storage_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot.to_dict(), default=str) + "\n")
        except OSError as exc:
            logger.warning("Failed to write timeline snapshot: %s", exc)

    def record(
        self,
        graph: InfraGraph,
        event: str | None = None,
        report: Any | None = None,
        genome_hash: str | None = None,
    ) -> TimelineSnapshot:
        """Record a new resilience snapshot.

        Args:
            graph: The current infrastructure graph.
            event: Optional description of what triggered this snapshot.
            report: Optional SimulationReport for critical/warning counts.
            genome_hash: Optional chaos genome hash.

        Returns:
            The recorded TimelineSnapshot.
        """
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        resilience_score = graph.resilience_score()
        component_count = len(graph.components)
        spof_count = _count_spofs(graph)
        infrastructure_hash = _compute_infrastructure_hash(graph)

        critical_findings = 0
        warning_count = 0
        metadata: dict = {}

        if report is not None:
            critical_findings = len(getattr(report, "critical_findings", []))
            warning_count = len(getattr(report, "warnings", []))
            metadata["total_scenarios"] = len(getattr(report, "results", []))

        snapshot = TimelineSnapshot(
            timestamp=now,
            resilience_score=round(resilience_score, 1),
            component_count=component_count,
            spof_count=spof_count,
            critical_findings=critical_findings,
            warning_count=warning_count,
            genome_hash=genome_hash,
            infrastructure_hash=infrastructure_hash,
            metadata=metadata,
            event=event,
        )

        self._append_snapshot(snapshot)

        # Check for milestones
        self._check_milestones(snapshot)

        return snapshot

    def _check_milestones(self, snapshot: TimelineSnapshot) -> None:
        """Check if the new snapshot triggers any milestones."""
        all_snapshots = self._load_all_snapshots()
        if len(all_snapshots) < 2:
            return

        score = snapshot.resilience_score

        # Check for score thresholds
        thresholds = [50.0, 75.0, 90.0, 95.0, 99.0]
        previous_scores = [s.resilience_score for s in all_snapshots[:-1]]
        prev_max = max(previous_scores) if previous_scores else 0.0

        for threshold in thresholds:
            if score >= threshold and prev_max < threshold:
                logger.info(
                    "Milestone: Score reached %.0f (%.1f)", threshold, score
                )

        # Check for zero critical findings
        if snapshot.critical_findings == 0:
            prev_with_critical = any(
                s.critical_findings > 0 for s in all_snapshots[:-1]
            )
            if prev_with_critical:
                logger.info("Milestone: Zero critical findings achieved!")

        # Check for regression
        if len(all_snapshots) >= 2:
            prev_score = all_snapshots[-2].resilience_score
            if prev_score - score >= 5.0:
                logger.warning(
                    "Regression detected: score dropped from %.1f to %.1f",
                    prev_score,
                    score,
                )

    def get_history(self, days: int = 90) -> list[TimelineSnapshot]:
        """Get snapshots from the last N days.

        Args:
            days: Number of days to look back.

        Returns:
            List of snapshots ordered by timestamp ascending.
        """
        all_snapshots = self._load_all_snapshots()
        if days <= 0:
            return all_snapshots

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
            timespec="seconds"
        )
        return [s for s in all_snapshots if s.timestamp >= cutoff]

    def get_trends(self) -> dict[str, TimelineTrend]:
        """Calculate trends for multiple time periods.

        Returns:
            Dict mapping period string to TimelineTrend.
        """
        periods = {"7d": 7, "30d": 30, "90d": 90}
        trends: dict[str, TimelineTrend] = {}

        for period_name, days in periods.items():
            snapshots = self.get_history(days=days)
            if not snapshots:
                trends[period_name] = TimelineTrend(
                    period=period_name,
                    start_score=0.0,
                    end_score=0.0,
                    delta=0.0,
                    trend="stable",
                    avg_score=0.0,
                    min_score=0.0,
                    max_score=0.0,
                    volatility=0.0,
                    snapshots_count=0,
                )
                continue

            scores = [s.resilience_score for s in snapshots]
            start_score = scores[0]
            end_score = scores[-1]
            delta = end_score - start_score
            avg_score = sum(scores) / len(scores)
            min_score = min(scores)
            max_score = max(scores)

            # Calculate standard deviation (volatility)
            if len(scores) > 1:
                variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
                volatility = math.sqrt(variance)
            else:
                volatility = 0.0

            trend = _classify_trend(delta, volatility)

            trends[period_name] = TimelineTrend(
                period=period_name,
                start_score=round(start_score, 1),
                end_score=round(end_score, 1),
                delta=round(delta, 1),
                trend=trend,
                avg_score=round(avg_score, 1),
                min_score=round(min_score, 1),
                max_score=round(max_score, 1),
                volatility=round(volatility, 2),
                snapshots_count=len(snapshots),
            )

        return trends

    def get_milestones(self) -> list[TimelineMilestone]:
        """Detect milestones from the timeline history.

        Returns:
            List of milestones ordered by timestamp.
        """
        all_snapshots = self._load_all_snapshots()
        if not all_snapshots:
            return []

        milestones: list[TimelineMilestone] = []
        thresholds = [50.0, 75.0, 90.0, 95.0, 99.0]
        threshold_achieved: set[float] = set()
        had_critical = False
        prev_score: float | None = None

        for snap in all_snapshots:
            score = snap.resilience_score

            # Score threshold milestones
            for threshold in thresholds:
                if threshold not in threshold_achieved and score >= threshold:
                    threshold_achieved.add(threshold)
                    milestones.append(TimelineMilestone(
                        timestamp=snap.timestamp,
                        milestone_type="score_threshold",
                        description=f"Resilience score reached {threshold:.0f}%",
                        score_at_milestone=score,
                    ))

            # Nines achieved milestones
            if score >= 99.9 and (prev_score is None or prev_score < 99.9):
                milestones.append(TimelineMilestone(
                    timestamp=snap.timestamp,
                    milestone_type="nines_achieved",
                    description="Three nines (99.9%) resilience achieved",
                    score_at_milestone=score,
                ))

            # Zero critical findings
            if snap.critical_findings == 0 and had_critical:
                milestones.append(TimelineMilestone(
                    timestamp=snap.timestamp,
                    milestone_type="zero_critical",
                    description="Zero critical findings achieved",
                    score_at_milestone=score,
                ))

            if snap.critical_findings > 0:
                had_critical = True

            # Regression detection
            if prev_score is not None and prev_score - score >= 5.0:
                milestones.append(TimelineMilestone(
                    timestamp=snap.timestamp,
                    milestone_type="regression",
                    description=(
                        f"Score regression: {prev_score:.1f} -> {score:.1f} "
                        f"(delta: {score - prev_score:.1f})"
                    ),
                    score_at_milestone=score,
                ))

            prev_score = score

        return milestones

    def detect_regressions(
        self, threshold: float = 5.0
    ) -> list[tuple[str, float, float]]:
        """Detect score regressions exceeding the threshold.

        Args:
            threshold: Minimum score drop to count as a regression.

        Returns:
            List of (timestamp, from_score, to_score) tuples.
        """
        all_snapshots = self._load_all_snapshots()
        regressions: list[tuple[str, float, float]] = []

        for i in range(1, len(all_snapshots)):
            prev = all_snapshots[i - 1].resilience_score
            curr = all_snapshots[i].resilience_score
            if prev - curr >= threshold:
                regressions.append((
                    all_snapshots[i].timestamp,
                    prev,
                    curr,
                ))

        return regressions

    def generate_sparkline(self, width: int = 40) -> str:
        """Generate an ASCII sparkline of resilience scores.

        Args:
            width: Maximum number of characters in the sparkline.

        Returns:
            ASCII sparkline string.
        """
        all_snapshots = self._load_all_snapshots()
        scores = [s.resilience_score for s in all_snapshots]
        return _generate_sparkline(scores, width=width)

    def generate_report(self) -> TimelineReport:
        """Generate a comprehensive timeline report.

        Returns:
            TimelineReport with all analytics.
        """
        all_snapshots = self._load_all_snapshots()
        milestones = self.get_milestones()
        trends = self.get_trends()
        regressions = self.detect_regressions()
        sparkline = self.generate_sparkline()

        if all_snapshots:
            scores = [s.resilience_score for s in all_snapshots]
            current_score = scores[-1]
            all_time_high = max(scores)
            all_time_low = min(scores)

            # Calculate days tracked
            try:
                first_ts = datetime.fromisoformat(all_snapshots[0].timestamp)
                last_ts = datetime.fromisoformat(all_snapshots[-1].timestamp)
                days_tracked = max(1, (last_ts - first_ts).days)
            except (ValueError, TypeError):
                days_tracked = 0
        else:
            current_score = 0.0
            all_time_high = 0.0
            all_time_low = 0.0
            days_tracked = 0

        return TimelineReport(
            snapshots=all_snapshots,
            milestones=milestones,
            trends=trends,
            current_score=current_score,
            all_time_high=all_time_high,
            all_time_low=all_time_low,
            days_tracked=days_tracked,
            total_snapshots=len(all_snapshots),
            regressions=regressions,
            sparkline=sparkline,
        )

    def export_csv(self, path: Path) -> Path:
        """Export timeline data to CSV.

        Args:
            path: Output file path.

        Returns:
            The path to the written CSV file.
        """
        all_snapshots = self._load_all_snapshots()
        path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "timestamp",
            "resilience_score",
            "component_count",
            "spof_count",
            "critical_findings",
            "warning_count",
            "genome_hash",
            "infrastructure_hash",
            "event",
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for snap in all_snapshots:
                writer.writerow({
                    "timestamp": snap.timestamp,
                    "resilience_score": snap.resilience_score,
                    "component_count": snap.component_count,
                    "spof_count": snap.spof_count,
                    "critical_findings": snap.critical_findings,
                    "warning_count": snap.warning_count,
                    "genome_hash": snap.genome_hash or "",
                    "infrastructure_hash": snap.infrastructure_hash,
                    "event": snap.event or "",
                })

        return path

    def reset(self) -> None:
        """Clear all timeline data."""
        if self.storage_path.exists():
            self.storage_path.write_text("")
        logger.info("Timeline data has been reset.")
