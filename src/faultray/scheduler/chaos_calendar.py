"""Chaos Calendar - Schedule and track chaos experiments.

A calendar-based system for planning, scheduling, and tracking chaos
engineering experiments. Supports:
- Recurring experiments (daily, weekly, monthly)
- One-time scheduled experiments
- Experiment history and results tracking
- Team coordination (who runs what, when)
- Blackout windows (no experiments during releases, holidays)
- Auto-scheduling recommendations based on risk analysis
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path.home() / ".faultzero"
_DEFAULT_CALENDAR_PATH = _DEFAULT_DIR / "calendar.json"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExperimentStatus(str, Enum):
    """Status of a chaos experiment."""

    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class RecurrencePattern(str, Enum):
    """Recurrence frequency for experiments."""

    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ChaosExperiment:
    """A single chaos experiment entry on the calendar."""

    id: str
    name: str
    description: str
    scenario_ids: list[str] = field(default_factory=list)
    target_components: list[str] = field(default_factory=list)
    scheduled_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    recurrence: RecurrencePattern = RecurrencePattern.ONCE
    status: ExperimentStatus = ExperimentStatus.SCHEDULED
    owner: str = ""
    tags: list[str] = field(default_factory=list)
    infrastructure_file: str = ""
    results: dict | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_estimate: str = "30m"
    notes: str = ""

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "scenario_ids": self.scenario_ids,
            "target_components": self.target_components,
            "scheduled_time": self.scheduled_time.isoformat(),
            "recurrence": self.recurrence.value,
            "status": self.status.value,
            "owner": self.owner,
            "tags": self.tags,
            "infrastructure_file": self.infrastructure_file,
            "results": self.results,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "duration_estimate": self.duration_estimate,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ChaosExperiment:
        """Deserialize from a dict."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            scenario_ids=data.get("scenario_ids", []),
            target_components=data.get("target_components", []),
            scheduled_time=datetime.fromisoformat(data["scheduled_time"]),
            recurrence=RecurrencePattern(data.get("recurrence", "once")),
            status=ExperimentStatus(data.get("status", "scheduled")),
            owner=data.get("owner", ""),
            tags=data.get("tags", []),
            infrastructure_file=data.get("infrastructure_file", ""),
            results=data.get("results"),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(timezone.utc),
            duration_estimate=data.get("duration_estimate", "30m"),
            notes=data.get("notes", ""),
        )


@dataclass
class BlackoutWindow:
    """A period during which no chaos experiments should run."""

    start: datetime
    end: datetime
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BlackoutWindow:
        return cls(
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
            reason=data.get("reason", ""),
        )


@dataclass
class CalendarView:
    """A snapshot of the calendar state for rendering."""

    experiments: list[ChaosExperiment]
    upcoming: list[ChaosExperiment]
    overdue: list[ChaosExperiment]
    history: list[ChaosExperiment]
    blackout_windows: list[BlackoutWindow]
    coverage_score: float
    experiment_frequency: float
    streak: int


# ---------------------------------------------------------------------------
# ChaosCalendar
# ---------------------------------------------------------------------------

class ChaosCalendar:
    """Schedule and track chaos engineering experiments.

    Stores data in a JSON file at ``~/.faultzero/calendar.json``.

    Args:
        store_path: Path to the JSON calendar file. Defaults to
                    ``~/.faultzero/calendar.json``.
    """

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = store_path or _DEFAULT_CALENDAR_PATH
        self._experiments: dict[str, ChaosExperiment] = {}
        self._blackouts: list[BlackoutWindow] = []
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load calendar data from JSON file."""
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                for exp_data in data.get("experiments", []):
                    exp = ChaosExperiment.from_dict(exp_data)
                    self._experiments[exp.id] = exp
                for bw_data in data.get("blackout_windows", []):
                    self._blackouts.append(BlackoutWindow.from_dict(bw_data))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("Could not load calendar data: %s", exc)

    def _save(self) -> None:
        """Persist calendar data to JSON file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "experiments": [exp.to_dict() for exp in self._experiments.values()],
            "blackout_windows": [bw.to_dict() for bw in self._blackouts],
        }
        self._path.write_text(json.dumps(data, indent=2, default=str))

    # ------------------------------------------------------------------
    # Experiment management
    # ------------------------------------------------------------------

    def schedule(self, experiment: ChaosExperiment) -> str:
        """Schedule a chaos experiment.

        If the experiment's ``id`` is empty, a UUID is generated.
        Returns the experiment ID.
        """
        if not experiment.id:
            experiment.id = str(uuid.uuid4())[:8]

        # Check blackout windows
        for bw in self._blackouts:
            if bw.start <= experiment.scheduled_time <= bw.end:
                experiment.status = ExperimentStatus.SKIPPED
                experiment.notes = f"Skipped: blackout window ({bw.reason})"
                logger.info(
                    "Experiment %s hits blackout window '%s', marking as skipped.",
                    experiment.id, bw.reason,
                )

        experiment.updated_at = datetime.now(timezone.utc)
        self._experiments[experiment.id] = experiment
        self._save()
        return experiment.id

    def cancel(self, experiment_id: str) -> bool:
        """Cancel a scheduled experiment. Returns True if found and cancelled."""
        exp = self._experiments.get(experiment_id)
        if exp is None:
            return False
        exp.status = ExperimentStatus.CANCELLED
        exp.updated_at = datetime.now(timezone.utc)
        self._save()
        return True

    def reschedule(self, experiment_id: str, new_time: datetime) -> bool:
        """Reschedule an experiment to a new time. Returns True if found."""
        exp = self._experiments.get(experiment_id)
        if exp is None:
            return False
        exp.scheduled_time = new_time
        exp.status = ExperimentStatus.SCHEDULED
        exp.updated_at = datetime.now(timezone.utc)

        # Re-check blackout
        for bw in self._blackouts:
            if bw.start <= new_time <= bw.end:
                exp.status = ExperimentStatus.SKIPPED
                exp.notes = f"Skipped: blackout window ({bw.reason})"

        self._save()
        return True

    def complete(self, experiment_id: str, results: dict) -> bool:
        """Mark an experiment as completed with results. Returns True if found."""
        exp = self._experiments.get(experiment_id)
        if exp is None:
            return False
        exp.status = ExperimentStatus.COMPLETED
        exp.results = results
        exp.updated_at = datetime.now(timezone.utc)
        self._save()
        return True

    # ------------------------------------------------------------------
    # Blackout windows
    # ------------------------------------------------------------------

    def add_blackout(self, window: BlackoutWindow) -> None:
        """Register a blackout window. Experiments during this period will be skipped."""
        self._blackouts.append(window)

        # Mark any existing experiments that fall in the blackout
        for exp in self._experiments.values():
            if exp.status == ExperimentStatus.SCHEDULED:
                if window.start <= exp.scheduled_time <= window.end:
                    exp.status = ExperimentStatus.SKIPPED
                    exp.notes = f"Skipped: blackout window ({window.reason})"
                    exp.updated_at = datetime.now(timezone.utc)

        self._save()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_experiment(self, experiment_id: str) -> ChaosExperiment | None:
        """Get a single experiment by ID."""
        return self._experiments.get(experiment_id)

    def get_upcoming(self, days: int = 7) -> list[ChaosExperiment]:
        """Get experiments scheduled in the next N days."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days)
        upcoming = [
            exp for exp in self._experiments.values()
            if exp.status == ExperimentStatus.SCHEDULED
            and now <= exp.scheduled_time <= cutoff
        ]
        upcoming.sort(key=lambda e: e.scheduled_time)
        return upcoming

    def get_overdue(self) -> list[ChaosExperiment]:
        """Get experiments that were scheduled but not yet run."""
        now = datetime.now(timezone.utc)
        overdue = [
            exp for exp in self._experiments.values()
            if exp.status == ExperimentStatus.SCHEDULED
            and exp.scheduled_time < now
        ]
        overdue.sort(key=lambda e: e.scheduled_time)
        return overdue

    def get_history(self, days: int = 90) -> list[ChaosExperiment]:
        """Get completed/failed experiments from the last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        completed_statuses = {
            ExperimentStatus.COMPLETED,
            ExperimentStatus.FAILED,
        }
        history = [
            exp for exp in self._experiments.values()
            if exp.status in completed_statuses
            and exp.updated_at >= cutoff
        ]
        history.sort(key=lambda e: e.updated_at, reverse=True)
        return history

    def get_calendar_view(self) -> CalendarView:
        """Build a full calendar view with statistics."""
        all_exps = list(self._experiments.values())
        upcoming = self.get_upcoming(days=7)
        overdue = self.get_overdue()
        history = self.get_history(days=90)

        # Coverage: % of unique target components tested in last 30 days
        recent_history = self.get_history(days=30)
        tested_components: set[str] = set()
        for exp in recent_history:
            tested_components.update(exp.target_components)
        all_components: set[str] = set()
        for exp in all_exps:
            all_components.update(exp.target_components)
        coverage = (len(tested_components) / len(all_components) * 100.0) if all_components else 0.0

        # Experiment frequency: experiments per week over last 30 days
        completed_recent = [
            exp for exp in recent_history
            if exp.status == ExperimentStatus.COMPLETED
        ]
        frequency = len(completed_recent) / 4.0 if completed_recent else 0.0

        # Streak: consecutive weeks with at least one completed experiment
        streak = self._calculate_streak()

        return CalendarView(
            experiments=all_exps,
            upcoming=upcoming,
            overdue=overdue,
            history=history,
            blackout_windows=list(self._blackouts),
            coverage_score=round(coverage, 1),
            experiment_frequency=round(frequency, 1),
            streak=streak,
        )

    def get_coverage(self, graph: InfraGraph) -> dict[str, bool]:
        """Check which components have been tested in the last 30 days.

        Returns a dict mapping component ID to whether it was tested.
        """
        recent = self.get_history(days=30)
        tested: set[str] = set()
        for exp in recent:
            tested.update(exp.target_components)

        return {
            comp_id: comp_id in tested
            for comp_id in graph.components
        }

    # ------------------------------------------------------------------
    # Auto-scheduling
    # ------------------------------------------------------------------

    def auto_schedule(
        self,
        graph: InfraGraph,
        frequency: RecurrencePattern = RecurrencePattern.WEEKLY,
        owner: str = "auto-scheduler",
    ) -> list[ChaosExperiment]:
        """Automatically schedule experiments for critical components.

        Logic:
        1. Identify SPOFs and high-risk components.
        2. Prioritize untested components.
        3. Spread experiments across the week.
        4. Avoid blackout windows.
        5. Prioritize components not tested recently.
        """
        coverage = self.get_coverage(graph)
        experiments: list[ChaosExperiment] = []

        # Gather components sorted by risk (SPOFs first, then by dependent count)
        ranked: list[tuple[str, int]] = []
        for comp_id, comp in graph.components.items():
            dependents = graph.get_dependents(comp_id)
            is_spof = comp.replicas <= 1 and len(dependents) > 0
            risk_score = len(dependents) * 10
            if is_spof:
                risk_score += 50
            if not coverage.get(comp_id, False):
                risk_score += 30  # untested bonus
            ranked.append((comp_id, risk_score))

        ranked.sort(key=lambda x: x[1], reverse=True)

        # Schedule experiments, spreading across days
        base_time = datetime.now(timezone.utc).replace(
            hour=10, minute=0, second=0, microsecond=0,
        )
        # Start from tomorrow
        base_time += timedelta(days=1)
        day_offset = 0

        for comp_id, risk_score in ranked:
            comp = graph.get_component(comp_id)
            if comp is None:
                continue

            scheduled_time = base_time + timedelta(days=day_offset)

            # Skip blackout windows
            in_blackout = True
            max_retries = 14  # avoid infinite loop
            retries = 0
            while in_blackout and retries < max_retries:
                in_blackout = False
                for bw in self._blackouts:
                    if bw.start <= scheduled_time <= bw.end:
                        scheduled_time = bw.end + timedelta(hours=1)
                        in_blackout = True
                        break
                retries += 1

            experiment = ChaosExperiment(
                id=str(uuid.uuid4())[:8],
                name=f"Auto: {comp.name} Resilience Test",
                description=f"Automated chaos test for {comp.name} ({comp.type.value}). Risk score: {risk_score}.",
                scenario_ids=[f"kill-{comp_id}"],
                target_components=[comp_id],
                scheduled_time=scheduled_time,
                recurrence=frequency,
                status=ExperimentStatus.SCHEDULED,
                owner=owner,
                tags=["auto-scheduled"],
                duration_estimate="30m",
            )

            eid = self.schedule(experiment)
            experiments.append(self._experiments[eid])
            day_offset += 1

        return experiments

    # ------------------------------------------------------------------
    # iCalendar export
    # ------------------------------------------------------------------

    def export_ical(self) -> str:
        """Export all scheduled experiments as an iCalendar (.ics) string.

        The output can be imported into Google Calendar, Outlook, etc.
        """
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//FaultZero//ChaosCalendar//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]

        for exp in self._experiments.values():
            if exp.status in (ExperimentStatus.CANCELLED, ExperimentStatus.SKIPPED):
                continue

            dt_start = exp.scheduled_time.strftime("%Y%m%dT%H%M%SZ")
            # Estimate end time from duration_estimate
            duration_minutes = self._parse_duration(exp.duration_estimate)
            dt_end = (exp.scheduled_time + timedelta(minutes=duration_minutes)).strftime("%Y%m%dT%H%M%SZ")

            description = exp.description
            if exp.target_components:
                description += f"\\nTarget: {', '.join(exp.target_components)}"
            if exp.owner:
                description += f"\\nOwner: {exp.owner}"

            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{exp.id}@faultzero",
                f"DTSTART:{dt_start}",
                f"DTEND:{dt_end}",
                f"SUMMARY:Chaos Experiment: {exp.name}",
                f"DESCRIPTION:{description}",
                f"STATUS:{'CONFIRMED' if exp.status == ExperimentStatus.SCHEDULED else 'COMPLETED'}",
                "END:VEVENT",
            ])

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_streak(self) -> int:
        """Calculate consecutive weeks with at least one completed experiment."""
        now = datetime.now(timezone.utc)
        streak = 0
        for weeks_ago in range(52):  # check up to a year
            week_start = now - timedelta(weeks=weeks_ago + 1)
            week_end = now - timedelta(weeks=weeks_ago)
            has_experiment = any(
                exp.status == ExperimentStatus.COMPLETED
                and week_start <= exp.updated_at <= week_end
                for exp in self._experiments.values()
            )
            if has_experiment:
                streak += 1
            else:
                break
        return streak

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        """Parse a duration string like '30m', '1h', '2h30m' into minutes."""
        if not duration_str:
            return 30
        minutes = 0
        current = ""
        for ch in duration_str:
            if ch.isdigit():
                current += ch
            elif ch == "h" and current:
                minutes += int(current) * 60
                current = ""
            elif ch == "m" and current:
                minutes += int(current)
                current = ""
        # Handle plain number (assume minutes)
        if current:
            minutes += int(current)
        return minutes if minutes > 0 else 30
