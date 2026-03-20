# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Virtual GameDay Training Platform — practice incident response in simulation.

Enables teams to run multi-phase training scenarios where system state changes
over time, tracks participant actions, and scores response effectiveness.
Ideal for onboarding, annual DR drills, and DORA compliance training evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TrainingPhase(str, Enum):
    DETECTION = "detection"
    TRIAGE = "triage"
    INVESTIGATION = "investigation"
    MITIGATION = "mitigation"
    RECOVERY = "recovery"
    POSTMORTEM = "postmortem"


class ParticipantRole(str, Enum):
    INCIDENT_COMMANDER = "incident_commander"
    ON_CALL_ENGINEER = "on_call_engineer"
    COMMUNICATION_LEAD = "communication_lead"
    SUBJECT_MATTER_EXPERT = "subject_matter_expert"


class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TrainingScenario(BaseModel):
    scenario_id: str
    name: str
    description: str
    difficulty: DifficultyLevel
    phases: list[dict] = Field(default_factory=list)
    target_components: list[str] = Field(default_factory=list)
    injected_failures: list[str] = Field(default_factory=list)


class ParticipantAction(BaseModel):
    timestamp: datetime
    participant_role: ParticipantRole
    phase: TrainingPhase
    action_description: str
    was_correct: bool
    time_taken_minutes: float


class TrainingScore(BaseModel):
    overall_score: float = 0.0
    detection_speed: float = 0.0
    triage_accuracy: float = 0.0
    communication_score: float = 0.0
    recovery_effectiveness: float = 0.0
    areas_for_improvement: list[str] = Field(default_factory=list)


class TrainingSession(BaseModel):
    session_id: str
    scenario: TrainingScenario
    participants: list[ParticipantRole] = Field(default_factory=list)
    actions: list[ParticipantAction] = Field(default_factory=list)
    start_time: datetime
    end_time: datetime | None = None
    score: TrainingScore | None = None


class TrainingReport(BaseModel):
    sessions_completed: int = 0
    average_score: float = 0.0
    score_trend: list[float] = Field(default_factory=list)
    weakest_phase: str = ""
    strongest_phase: str = ""
    recommendations: list[str] = Field(default_factory=list)
    dora_evidence_generated: bool = False


# ---------------------------------------------------------------------------
# Default phase definitions per difficulty
# ---------------------------------------------------------------------------

_DIFFICULTY_TIME_MULTIPLIER: dict[DifficultyLevel, float] = {
    DifficultyLevel.BEGINNER: 1.0,
    DifficultyLevel.INTERMEDIATE: 0.8,
    DifficultyLevel.ADVANCED: 0.6,
    DifficultyLevel.EXPERT: 0.4,
}

_BASE_PHASES: list[dict] = [
    {
        "phase": TrainingPhase.DETECTION,
        "description": "Detect the incident from alerts and monitoring dashboards.",
        "expected_duration_minutes": 10.0,
        "hints": ["Check recent alert history", "Review dashboard anomalies"],
    },
    {
        "phase": TrainingPhase.TRIAGE,
        "description": "Assess severity and assign initial priority.",
        "expected_duration_minutes": 8.0,
        "hints": ["Use severity matrix", "Identify affected user segments"],
    },
    {
        "phase": TrainingPhase.INVESTIGATION,
        "description": "Investigate root cause through logs and metrics.",
        "expected_duration_minutes": 20.0,
        "hints": ["Correlate timestamps across services", "Check recent deployments"],
    },
    {
        "phase": TrainingPhase.MITIGATION,
        "description": "Apply immediate mitigation to reduce impact.",
        "expected_duration_minutes": 15.0,
        "hints": ["Consider rollback", "Enable circuit breakers"],
    },
    {
        "phase": TrainingPhase.RECOVERY,
        "description": "Restore systems to full operational state.",
        "expected_duration_minutes": 12.0,
        "hints": ["Verify health checks pass", "Monitor error rates post-fix"],
    },
    {
        "phase": TrainingPhase.POSTMORTEM,
        "description": "Conduct blameless postmortem and document learnings.",
        "expected_duration_minutes": 30.0,
        "hints": ["Use 5-Whys technique", "Identify action items"],
    },
]


# ---------------------------------------------------------------------------
# GameDayTrainer
# ---------------------------------------------------------------------------


class GameDayTrainer:
    """Orchestrates virtual game-day training sessions."""

    def __init__(self) -> None:
        self._sessions: list[TrainingSession] = []

    # -- scenario -----------------------------------------------------------

    def create_scenario(
        self,
        name: str,
        difficulty: DifficultyLevel,
        target_components: list[str],
        injected_failures: list[str],
    ) -> TrainingScenario:
        """Generate a training scenario with phases scaled to *difficulty*."""
        multiplier = _DIFFICULTY_TIME_MULTIPLIER[difficulty]
        phases: list[dict] = []
        for base in _BASE_PHASES:
            phases.append(
                {
                    "phase": base["phase"],
                    "description": base["description"],
                    "expected_duration_minutes": round(
                        base["expected_duration_minutes"] * multiplier, 2
                    ),
                    "hints": list(base["hints"]),
                }
            )

        description = (
            f"{difficulty.value.capitalize()} training targeting "
            f"{', '.join(target_components)} with failures: "
            f"{', '.join(injected_failures)}."
        )

        return TrainingScenario(
            scenario_id=uuid4().hex[:12],
            name=name,
            description=description,
            difficulty=difficulty,
            phases=phases,
            target_components=target_components,
            injected_failures=injected_failures,
        )

    # -- session lifecycle --------------------------------------------------

    def start_session(
        self,
        scenario: TrainingScenario,
        participants: list[ParticipantRole],
    ) -> TrainingSession:
        """Start a new training session for the given *scenario*."""
        session = TrainingSession(
            session_id=uuid4().hex[:12],
            scenario=scenario,
            participants=participants,
            start_time=datetime.now(timezone.utc),
        )
        self._sessions.append(session)
        return session

    def record_action(
        self,
        session: TrainingSession,
        action: ParticipantAction,
    ) -> TrainingSession:
        """Append an action to *session* and return it."""
        session.actions.append(action)
        return session

    def end_session(self, session: TrainingSession) -> TrainingSession:
        """Mark *session* as ended, compute its score, and return it."""
        session.end_time = datetime.now(timezone.utc)
        session.score = self.score_session(session)
        return session

    # -- scoring ------------------------------------------------------------

    def score_session(self, session: TrainingSession) -> TrainingScore:
        """Compute a detailed :class:`TrainingScore` for *session*."""
        actions = session.actions
        if not actions:
            return TrainingScore(
                overall_score=0.0,
                detection_speed=0.0,
                triage_accuracy=0.0,
                communication_score=0.0,
                recovery_effectiveness=0.0,
                areas_for_improvement=["No actions recorded"],
            )

        # -- per-phase accuracy --
        phase_correct: dict[TrainingPhase, list[bool]] = {}
        for a in actions:
            phase_correct.setdefault(a.phase, []).append(a.was_correct)

        def _accuracy(phase: TrainingPhase) -> float:
            bools = phase_correct.get(phase, [])
            if not bools:
                return 0.0
            return (sum(bools) / len(bools)) * 100.0

        detection_speed = _accuracy(TrainingPhase.DETECTION)
        triage_accuracy = _accuracy(TrainingPhase.TRIAGE)
        recovery_effectiveness = _accuracy(TrainingPhase.RECOVERY)

        # -- communication: based on COMMUNICATION_LEAD actions --
        comm_actions = [a for a in actions if a.participant_role == ParticipantRole.COMMUNICATION_LEAD]
        if comm_actions:
            communication_score = (sum(a.was_correct for a in comm_actions) / len(comm_actions)) * 100.0
        else:
            communication_score = 50.0  # neutral when no comms lead participated

        # -- overall --
        correct_total = sum(a.was_correct for a in actions)
        overall_score = (correct_total / len(actions)) * 100.0

        # -- improvement areas --
        areas: list[str] = []
        for phase in TrainingPhase:
            acc = _accuracy(phase)
            if phase in phase_correct and acc < 50.0:
                areas.append(f"Improve {phase.value} accuracy (currently {acc:.0f}%)")
        if not areas:
            areas.append("Maintain current performance")

        return TrainingScore(
            overall_score=round(overall_score, 2),
            detection_speed=round(detection_speed, 2),
            triage_accuracy=round(triage_accuracy, 2),
            communication_score=round(communication_score, 2),
            recovery_effectiveness=round(recovery_effectiveness, 2),
            areas_for_improvement=areas,
        )

    # -- reporting ----------------------------------------------------------

    def generate_report(self, sessions: list[TrainingSession]) -> TrainingReport:
        """Aggregate multiple sessions into a :class:`TrainingReport`."""
        if not sessions:
            return TrainingReport(
                sessions_completed=0,
                average_score=0.0,
                score_trend=[],
                weakest_phase="",
                strongest_phase="",
                recommendations=["No sessions to report on"],
                dora_evidence_generated=False,
            )

        scores: list[float] = []
        phase_accuracy_totals: dict[str, list[float]] = {}

        for s in sessions:
            sc = s.score or self.score_session(s)
            scores.append(sc.overall_score)

            # accumulate per-phase correctness across sessions
            phase_correct_map: dict[str, list[bool]] = {}
            for a in s.actions:
                phase_correct_map.setdefault(a.phase.value, []).append(a.was_correct)

            for phase_name, bools in phase_correct_map.items():
                acc = (sum(bools) / len(bools)) * 100.0 if bools else 0.0
                phase_accuracy_totals.setdefault(phase_name, []).append(acc)

        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
        score_trend = [round(s, 2) for s in scores]

        # determine weakest / strongest
        phase_avg: dict[str, float] = {}
        for phase_name, accs in phase_accuracy_totals.items():
            phase_avg[phase_name] = sum(accs) / len(accs)

        if phase_avg:
            weakest_phase = min(phase_avg, key=lambda k: phase_avg[k])
            strongest_phase = max(phase_avg, key=lambda k: phase_avg[k])
        else:
            weakest_phase = ""
            strongest_phase = ""

        # recommendations
        recommendations: list[str] = []
        if avg_score < 50:
            recommendations.append("Schedule additional training sessions")
        if avg_score < 80:
            recommendations.append("Focus on weaker phases with targeted drills")
        if len(sessions) < 3:
            recommendations.append("Run more sessions to establish reliable trend data")
        if weakest_phase and phase_avg.get(weakest_phase, 100.0) < 80.0:
            recommendations.append(f"Prioritize improvement in {weakest_phase} phase")
        if not recommendations:
            recommendations.append("Team is performing well — maintain cadence")

        dora_evidence = len(sessions) >= 1

        return TrainingReport(
            sessions_completed=len(sessions),
            average_score=avg_score,
            score_trend=score_trend,
            weakest_phase=weakest_phase,
            strongest_phase=strongest_phase,
            recommendations=recommendations,
            dora_evidence_generated=dora_evidence,
        )
