"""Tests for faultray.simulator.gameday_trainer — Virtual GameDay Training Platform."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from faultray.simulator.gameday_trainer import (
    DifficultyLevel,
    GameDayTrainer,
    ParticipantAction,
    ParticipantRole,
    TrainingPhase,
    TrainingReport,
    TrainingScore,
    TrainingScenario,
    TrainingSession,
    _BASE_PHASES,
    _DIFFICULTY_TIME_MULTIPLIER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_action(
    role: ParticipantRole = ParticipantRole.ON_CALL_ENGINEER,
    phase: TrainingPhase = TrainingPhase.DETECTION,
    correct: bool = True,
    minutes: float = 5.0,
    description: str = "Checked dashboards",
) -> ParticipantAction:
    return ParticipantAction(
        timestamp=_now(),
        participant_role=role,
        phase=phase,
        action_description=description,
        was_correct=correct,
        time_taken_minutes=minutes,
    )


def _make_scenario(
    trainer: GameDayTrainer,
    difficulty: DifficultyLevel = DifficultyLevel.BEGINNER,
    name: str = "Test Scenario",
    components: list[str] | None = None,
    failures: list[str] | None = None,
) -> TrainingScenario:
    return trainer.create_scenario(
        name=name,
        difficulty=difficulty,
        target_components=components or ["api-server"],
        injected_failures=failures or ["latency-spike"],
    )


def _make_session(
    trainer: GameDayTrainer,
    scenario: TrainingScenario | None = None,
    participants: list[ParticipantRole] | None = None,
) -> TrainingSession:
    sc = scenario or _make_scenario(trainer)
    parts = participants or [ParticipantRole.ON_CALL_ENGINEER]
    return trainer.start_session(sc, parts)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestTrainingPhaseEnum:
    def test_all_phases_exist(self):
        expected = {"detection", "triage", "investigation", "mitigation", "recovery", "postmortem"}
        assert {p.value for p in TrainingPhase} == expected

    def test_phase_count(self):
        assert len(TrainingPhase) == 6

    def test_phase_is_str(self):
        for p in TrainingPhase:
            assert isinstance(p, str)
            assert isinstance(p.value, str)

    def test_detection(self):
        assert TrainingPhase.DETECTION.value == "detection"

    def test_triage(self):
        assert TrainingPhase.TRIAGE.value == "triage"

    def test_investigation(self):
        assert TrainingPhase.INVESTIGATION.value == "investigation"

    def test_mitigation(self):
        assert TrainingPhase.MITIGATION.value == "mitigation"

    def test_recovery(self):
        assert TrainingPhase.RECOVERY.value == "recovery"

    def test_postmortem(self):
        assert TrainingPhase.POSTMORTEM.value == "postmortem"


class TestParticipantRoleEnum:
    def test_all_roles_exist(self):
        expected = {
            "incident_commander", "on_call_engineer",
            "communication_lead", "subject_matter_expert",
        }
        assert {r.value for r in ParticipantRole} == expected

    def test_role_count(self):
        assert len(ParticipantRole) == 4

    def test_role_is_str(self):
        for r in ParticipantRole:
            assert isinstance(r, str)

    def test_incident_commander(self):
        assert ParticipantRole.INCIDENT_COMMANDER.value == "incident_commander"

    def test_on_call_engineer(self):
        assert ParticipantRole.ON_CALL_ENGINEER.value == "on_call_engineer"

    def test_communication_lead(self):
        assert ParticipantRole.COMMUNICATION_LEAD.value == "communication_lead"

    def test_subject_matter_expert(self):
        assert ParticipantRole.SUBJECT_MATTER_EXPERT.value == "subject_matter_expert"


class TestDifficultyLevelEnum:
    def test_all_levels_exist(self):
        expected = {"beginner", "intermediate", "advanced", "expert"}
        assert {d.value for d in DifficultyLevel} == expected

    def test_level_count(self):
        assert len(DifficultyLevel) == 4

    def test_beginner(self):
        assert DifficultyLevel.BEGINNER.value == "beginner"

    def test_intermediate(self):
        assert DifficultyLevel.INTERMEDIATE.value == "intermediate"

    def test_advanced(self):
        assert DifficultyLevel.ADVANCED.value == "advanced"

    def test_expert(self):
        assert DifficultyLevel.EXPERT.value == "expert"


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


class TestTrainingScenarioModel:
    def test_create_minimal(self):
        s = TrainingScenario(
            scenario_id="abc123", name="s", description="d", difficulty=DifficultyLevel.BEGINNER,
        )
        assert s.scenario_id == "abc123"
        assert s.phases == []
        assert s.target_components == []
        assert s.injected_failures == []

    def test_create_full(self):
        s = TrainingScenario(
            scenario_id="xyz",
            name="full",
            description="desc",
            difficulty=DifficultyLevel.EXPERT,
            phases=[{"phase": TrainingPhase.DETECTION, "description": "d", "expected_duration_minutes": 5.0, "hints": []}],
            target_components=["db"],
            injected_failures=["disk-full"],
        )
        assert len(s.phases) == 1
        assert s.target_components == ["db"]

    def test_field_types(self):
        s = TrainingScenario(
            scenario_id="id", name="n", description="d", difficulty=DifficultyLevel.BEGINNER,
        )
        assert isinstance(s.difficulty, DifficultyLevel)
        assert isinstance(s.phases, list)


class TestParticipantActionModel:
    def test_create(self):
        a = _make_action()
        assert a.was_correct is True
        assert a.time_taken_minutes == 5.0
        assert isinstance(a.timestamp, datetime)

    def test_incorrect_action(self):
        a = _make_action(correct=False)
        assert a.was_correct is False

    def test_custom_description(self):
        a = _make_action(description="Ran query")
        assert a.action_description == "Ran query"

    def test_various_phases(self):
        for phase in TrainingPhase:
            a = _make_action(phase=phase)
            assert a.phase == phase

    def test_various_roles(self):
        for role in ParticipantRole:
            a = _make_action(role=role)
            assert a.participant_role == role


class TestTrainingScoreModel:
    def test_defaults(self):
        s = TrainingScore()
        assert s.overall_score == 0.0
        assert s.detection_speed == 0.0
        assert s.areas_for_improvement == []

    def test_custom_values(self):
        s = TrainingScore(
            overall_score=85.0,
            detection_speed=90.0,
            triage_accuracy=80.0,
            communication_score=70.0,
            recovery_effectiveness=95.0,
            areas_for_improvement=["comms"],
        )
        assert s.overall_score == 85.0
        assert s.areas_for_improvement == ["comms"]


class TestTrainingSessionModel:
    def test_create_minimal(self):
        sc = TrainingScenario(
            scenario_id="s1", name="n", description="d", difficulty=DifficultyLevel.BEGINNER,
        )
        ts = TrainingSession(session_id="sess1", scenario=sc, start_time=_now())
        assert ts.end_time is None
        assert ts.score is None
        assert ts.actions == []

    def test_end_time_nullable(self):
        sc = TrainingScenario(
            scenario_id="s1", name="n", description="d", difficulty=DifficultyLevel.BEGINNER,
        )
        ts = TrainingSession(session_id="s", scenario=sc, start_time=_now(), end_time=_now())
        assert ts.end_time is not None


class TestTrainingReportModel:
    def test_defaults(self):
        r = TrainingReport()
        assert r.sessions_completed == 0
        assert r.dora_evidence_generated is False
        assert r.score_trend == []

    def test_custom(self):
        r = TrainingReport(
            sessions_completed=5,
            average_score=72.5,
            score_trend=[60, 70, 80],
            weakest_phase="detection",
            strongest_phase="recovery",
            recommendations=["drill more"],
            dora_evidence_generated=True,
        )
        assert r.sessions_completed == 5
        assert r.dora_evidence_generated is True


# ---------------------------------------------------------------------------
# Constants / config tests
# ---------------------------------------------------------------------------


class TestConstants:
    def test_difficulty_multiplier_keys(self):
        assert set(_DIFFICULTY_TIME_MULTIPLIER.keys()) == set(DifficultyLevel)

    def test_beginner_multiplier(self):
        assert _DIFFICULTY_TIME_MULTIPLIER[DifficultyLevel.BEGINNER] == 1.0

    def test_intermediate_multiplier(self):
        assert _DIFFICULTY_TIME_MULTIPLIER[DifficultyLevel.INTERMEDIATE] == 0.8

    def test_advanced_multiplier(self):
        assert _DIFFICULTY_TIME_MULTIPLIER[DifficultyLevel.ADVANCED] == 0.6

    def test_expert_multiplier(self):
        assert _DIFFICULTY_TIME_MULTIPLIER[DifficultyLevel.EXPERT] == 0.4

    def test_base_phases_count(self):
        assert len(_BASE_PHASES) == 6

    def test_base_phases_keys(self):
        for p in _BASE_PHASES:
            assert "phase" in p
            assert "description" in p
            assert "expected_duration_minutes" in p
            assert "hints" in p

    def test_base_phases_cover_all_training_phases(self):
        covered = {p["phase"] for p in _BASE_PHASES}
        assert covered == set(TrainingPhase)


# ---------------------------------------------------------------------------
# GameDayTrainer.__init__
# ---------------------------------------------------------------------------


class TestTrainerInit:
    def test_creates_instance(self):
        t = GameDayTrainer()
        assert isinstance(t, GameDayTrainer)

    def test_sessions_list_empty(self):
        t = GameDayTrainer()
        assert t._sessions == []


# ---------------------------------------------------------------------------
# create_scenario
# ---------------------------------------------------------------------------


class TestCreateScenario:
    def test_returns_scenario(self):
        t = GameDayTrainer()
        sc = _make_scenario(t)
        assert isinstance(sc, TrainingScenario)

    def test_scenario_id_length(self):
        t = GameDayTrainer()
        sc = _make_scenario(t)
        assert len(sc.scenario_id) == 12

    def test_scenario_id_hex(self):
        t = GameDayTrainer()
        sc = _make_scenario(t)
        int(sc.scenario_id, 16)  # should not raise

    def test_scenario_ids_unique(self):
        t = GameDayTrainer()
        ids = {_make_scenario(t).scenario_id for _ in range(20)}
        assert len(ids) == 20

    def test_name_preserved(self):
        t = GameDayTrainer()
        sc = _make_scenario(t, name="My Drill")
        assert sc.name == "My Drill"

    def test_difficulty_preserved(self):
        t = GameDayTrainer()
        for d in DifficultyLevel:
            sc = _make_scenario(t, difficulty=d)
            assert sc.difficulty == d

    def test_target_components_preserved(self):
        t = GameDayTrainer()
        sc = _make_scenario(t, components=["web", "db"])
        assert sc.target_components == ["web", "db"]

    def test_injected_failures_preserved(self):
        t = GameDayTrainer()
        sc = _make_scenario(t, failures=["crash", "oom"])
        assert sc.injected_failures == ["crash", "oom"]

    def test_description_contains_difficulty(self):
        t = GameDayTrainer()
        sc = _make_scenario(t, difficulty=DifficultyLevel.ADVANCED)
        assert "Advanced" in sc.description

    def test_description_contains_components(self):
        t = GameDayTrainer()
        sc = _make_scenario(t, components=["redis"])
        assert "redis" in sc.description

    def test_description_contains_failures(self):
        t = GameDayTrainer()
        sc = _make_scenario(t, failures=["timeout"])
        assert "timeout" in sc.description

    def test_phases_count(self):
        t = GameDayTrainer()
        sc = _make_scenario(t)
        assert len(sc.phases) == 6

    def test_beginner_durations_unchanged(self):
        t = GameDayTrainer()
        sc = _make_scenario(t, difficulty=DifficultyLevel.BEGINNER)
        for phase, base in zip(sc.phases, _BASE_PHASES):
            assert phase["expected_duration_minutes"] == base["expected_duration_minutes"]

    def test_expert_durations_scaled(self):
        t = GameDayTrainer()
        sc = _make_scenario(t, difficulty=DifficultyLevel.EXPERT)
        for phase, base in zip(sc.phases, _BASE_PHASES):
            expected = round(base["expected_duration_minutes"] * 0.4, 2)
            assert phase["expected_duration_minutes"] == expected

    def test_intermediate_durations_scaled(self):
        t = GameDayTrainer()
        sc = _make_scenario(t, difficulty=DifficultyLevel.INTERMEDIATE)
        for phase, base in zip(sc.phases, _BASE_PHASES):
            expected = round(base["expected_duration_minutes"] * 0.8, 2)
            assert phase["expected_duration_minutes"] == expected

    def test_advanced_durations_scaled(self):
        t = GameDayTrainer()
        sc = _make_scenario(t, difficulty=DifficultyLevel.ADVANCED)
        for phase, base in zip(sc.phases, _BASE_PHASES):
            expected = round(base["expected_duration_minutes"] * 0.6, 2)
            assert phase["expected_duration_minutes"] == expected

    def test_phases_have_hints(self):
        t = GameDayTrainer()
        sc = _make_scenario(t)
        for phase in sc.phases:
            assert isinstance(phase["hints"], list)
            assert len(phase["hints"]) >= 1

    def test_phases_have_descriptions(self):
        t = GameDayTrainer()
        sc = _make_scenario(t)
        for phase in sc.phases:
            assert len(phase["description"]) > 0

    def test_phases_contain_training_phase_objects(self):
        t = GameDayTrainer()
        sc = _make_scenario(t)
        for phase in sc.phases:
            assert isinstance(phase["phase"], TrainingPhase)

    def test_multiple_components(self):
        t = GameDayTrainer()
        sc = _make_scenario(t, components=["a", "b", "c"])
        assert len(sc.target_components) == 3

    def test_empty_components(self):
        t = GameDayTrainer()
        sc = t.create_scenario("x", DifficultyLevel.BEGINNER, [], ["fail"])
        assert sc.target_components == []

    def test_empty_failures(self):
        t = GameDayTrainer()
        sc = t.create_scenario("x", DifficultyLevel.BEGINNER, ["comp"], [])
        assert sc.injected_failures == []

    def test_hints_are_copies(self):
        t = GameDayTrainer()
        sc1 = _make_scenario(t)
        sc2 = _make_scenario(t)
        sc1.phases[0]["hints"].append("extra")
        assert "extra" not in sc2.phases[0]["hints"]


# ---------------------------------------------------------------------------
# start_session
# ---------------------------------------------------------------------------


class TestStartSession:
    def test_returns_session(self):
        t = GameDayTrainer()
        s = _make_session(t)
        assert isinstance(s, TrainingSession)

    def test_session_id_length(self):
        t = GameDayTrainer()
        s = _make_session(t)
        assert len(s.session_id) == 12

    def test_session_id_hex(self):
        t = GameDayTrainer()
        s = _make_session(t)
        int(s.session_id, 16)

    def test_session_ids_unique(self):
        t = GameDayTrainer()
        sc = _make_scenario(t)
        ids = {t.start_session(sc, [ParticipantRole.ON_CALL_ENGINEER]).session_id for _ in range(20)}
        assert len(ids) == 20

    def test_scenario_attached(self):
        t = GameDayTrainer()
        sc = _make_scenario(t)
        s = t.start_session(sc, [ParticipantRole.ON_CALL_ENGINEER])
        assert s.scenario == sc

    def test_participants_attached(self):
        t = GameDayTrainer()
        parts = [ParticipantRole.INCIDENT_COMMANDER, ParticipantRole.ON_CALL_ENGINEER]
        s = _make_session(t, participants=parts)
        assert s.participants == parts

    def test_start_time_set(self):
        t = GameDayTrainer()
        before = _now()
        s = _make_session(t)
        after = _now()
        assert before <= s.start_time <= after

    def test_end_time_none(self):
        t = GameDayTrainer()
        s = _make_session(t)
        assert s.end_time is None

    def test_score_none(self):
        t = GameDayTrainer()
        s = _make_session(t)
        assert s.score is None

    def test_actions_empty(self):
        t = GameDayTrainer()
        s = _make_session(t)
        assert s.actions == []

    def test_session_tracked_internally(self):
        t = GameDayTrainer()
        s = _make_session(t)
        assert s in t._sessions

    def test_multiple_sessions_tracked(self):
        t = GameDayTrainer()
        _make_session(t)
        _make_session(t)
        assert len(t._sessions) == 2

    def test_single_participant(self):
        t = GameDayTrainer()
        s = _make_session(t, participants=[ParticipantRole.SUBJECT_MATTER_EXPERT])
        assert len(s.participants) == 1

    def test_all_roles_as_participants(self):
        t = GameDayTrainer()
        s = _make_session(t, participants=list(ParticipantRole))
        assert len(s.participants) == 4


# ---------------------------------------------------------------------------
# record_action
# ---------------------------------------------------------------------------


class TestRecordAction:
    def test_appends_action(self):
        t = GameDayTrainer()
        s = _make_session(t)
        a = _make_action()
        s2 = t.record_action(s, a)
        assert len(s2.actions) == 1

    def test_returns_same_session(self):
        t = GameDayTrainer()
        s = _make_session(t)
        a = _make_action()
        s2 = t.record_action(s, a)
        assert s2 is s

    def test_multiple_actions(self):
        t = GameDayTrainer()
        s = _make_session(t)
        for _ in range(5):
            t.record_action(s, _make_action())
        assert len(s.actions) == 5

    def test_preserves_action_data(self):
        t = GameDayTrainer()
        s = _make_session(t)
        a = _make_action(description="specific action", correct=False, minutes=12.5)
        t.record_action(s, a)
        assert s.actions[0].action_description == "specific action"
        assert s.actions[0].was_correct is False
        assert s.actions[0].time_taken_minutes == 12.5

    def test_action_order_maintained(self):
        t = GameDayTrainer()
        s = _make_session(t)
        phases = [TrainingPhase.DETECTION, TrainingPhase.TRIAGE, TrainingPhase.MITIGATION]
        for p in phases:
            t.record_action(s, _make_action(phase=p))
        assert [a.phase for a in s.actions] == phases

    def test_different_roles(self):
        t = GameDayTrainer()
        s = _make_session(t)
        for role in ParticipantRole:
            t.record_action(s, _make_action(role=role))
        roles = [a.participant_role for a in s.actions]
        assert roles == list(ParticipantRole)


# ---------------------------------------------------------------------------
# end_session
# ---------------------------------------------------------------------------


class TestEndSession:
    def test_sets_end_time(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action())
        before = _now()
        t.end_session(s)
        after = _now()
        assert s.end_time is not None
        assert before <= s.end_time <= after

    def test_sets_score(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(correct=True))
        t.end_session(s)
        assert s.score is not None
        assert isinstance(s.score, TrainingScore)

    def test_returns_session(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action())
        result = t.end_session(s)
        assert result is s

    def test_score_reflects_actions(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(correct=True))
        t.record_action(s, _make_action(correct=True))
        t.end_session(s)
        assert s.score is not None
        assert s.score.overall_score == 100.0

    def test_end_session_no_actions(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.end_session(s)
        assert s.score is not None
        assert s.score.overall_score == 0.0

    def test_end_time_after_start_time(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.end_session(s)
        assert s.end_time is not None
        assert s.end_time >= s.start_time


# ---------------------------------------------------------------------------
# score_session
# ---------------------------------------------------------------------------


class TestScoreSession:
    def test_no_actions(self):
        t = GameDayTrainer()
        s = _make_session(t)
        score = t.score_session(s)
        assert score.overall_score == 0.0
        assert score.detection_speed == 0.0
        assert score.triage_accuracy == 0.0
        assert score.communication_score == 0.0
        assert score.recovery_effectiveness == 0.0
        assert "No actions recorded" in score.areas_for_improvement

    def test_all_correct(self):
        t = GameDayTrainer()
        s = _make_session(t)
        for phase in TrainingPhase:
            t.record_action(s, _make_action(phase=phase, correct=True))
        score = t.score_session(s)
        assert score.overall_score == 100.0

    def test_all_incorrect(self):
        t = GameDayTrainer()
        s = _make_session(t)
        for phase in TrainingPhase:
            t.record_action(s, _make_action(phase=phase, correct=False))
        score = t.score_session(s)
        assert score.overall_score == 0.0

    def test_half_correct(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(correct=True))
        t.record_action(s, _make_action(correct=False))
        score = t.score_session(s)
        assert score.overall_score == 50.0

    def test_detection_speed(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(phase=TrainingPhase.DETECTION, correct=True))
        t.record_action(s, _make_action(phase=TrainingPhase.DETECTION, correct=False))
        score = t.score_session(s)
        assert score.detection_speed == 50.0

    def test_detection_all_correct(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(phase=TrainingPhase.DETECTION, correct=True))
        score = t.score_session(s)
        assert score.detection_speed == 100.0

    def test_triage_accuracy(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(phase=TrainingPhase.TRIAGE, correct=True))
        t.record_action(s, _make_action(phase=TrainingPhase.TRIAGE, correct=True))
        t.record_action(s, _make_action(phase=TrainingPhase.TRIAGE, correct=False))
        score = t.score_session(s)
        assert round(score.triage_accuracy, 2) == 66.67

    def test_recovery_effectiveness(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(phase=TrainingPhase.RECOVERY, correct=True))
        score = t.score_session(s)
        assert score.recovery_effectiveness == 100.0

    def test_recovery_none(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(phase=TrainingPhase.DETECTION, correct=True))
        score = t.score_session(s)
        assert score.recovery_effectiveness == 0.0

    def test_communication_with_lead(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(role=ParticipantRole.COMMUNICATION_LEAD, correct=True))
        t.record_action(s, _make_action(role=ParticipantRole.COMMUNICATION_LEAD, correct=False))
        score = t.score_session(s)
        assert score.communication_score == 50.0

    def test_communication_without_lead(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(role=ParticipantRole.ON_CALL_ENGINEER, correct=True))
        score = t.score_session(s)
        assert score.communication_score == 50.0

    def test_communication_all_correct(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(role=ParticipantRole.COMMUNICATION_LEAD, correct=True))
        score = t.score_session(s)
        assert score.communication_score == 100.0

    def test_areas_for_improvement_low_phase(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(phase=TrainingPhase.DETECTION, correct=False))
        t.record_action(s, _make_action(phase=TrainingPhase.TRIAGE, correct=True))
        score = t.score_session(s)
        assert any("detection" in area for area in score.areas_for_improvement)

    def test_areas_for_improvement_good_performance(self):
        t = GameDayTrainer()
        s = _make_session(t)
        for phase in TrainingPhase:
            t.record_action(s, _make_action(phase=phase, correct=True))
        score = t.score_session(s)
        assert "Maintain current performance" in score.areas_for_improvement

    def test_areas_multiple_weak_phases(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(phase=TrainingPhase.DETECTION, correct=False))
        t.record_action(s, _make_action(phase=TrainingPhase.TRIAGE, correct=False))
        t.record_action(s, _make_action(phase=TrainingPhase.RECOVERY, correct=True))
        score = t.score_session(s)
        assert len(score.areas_for_improvement) >= 2

    def test_overall_score_rounded(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(correct=True))
        t.record_action(s, _make_action(correct=True))
        t.record_action(s, _make_action(correct=False))
        score = t.score_session(s)
        assert score.overall_score == round(200.0 / 3.0, 2)

    def test_score_is_training_score(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action())
        score = t.score_session(s)
        assert isinstance(score, TrainingScore)

    def test_phases_not_present_score_zero(self):
        t = GameDayTrainer()
        s = _make_session(t)
        # Only detection actions - triage/recovery should be 0
        t.record_action(s, _make_action(phase=TrainingPhase.DETECTION, correct=True))
        score = t.score_session(s)
        assert score.triage_accuracy == 0.0
        assert score.recovery_effectiveness == 0.0

    def test_many_actions(self):
        t = GameDayTrainer()
        s = _make_session(t)
        for i in range(100):
            t.record_action(s, _make_action(correct=(i % 3 != 0)))
        score = t.score_session(s)
        assert 0.0 <= score.overall_score <= 100.0

    def test_improvement_areas_contain_percentage(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(phase=TrainingPhase.MITIGATION, correct=False))
        score = t.score_session(s)
        weak_areas = [a for a in score.areas_for_improvement if "mitigation" in a]
        assert len(weak_areas) >= 1
        assert "0%" in weak_areas[0]

    def test_50_percent_phase_not_flagged(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(phase=TrainingPhase.INVESTIGATION, correct=True))
        t.record_action(s, _make_action(phase=TrainingPhase.INVESTIGATION, correct=False))
        score = t.score_session(s)
        # 50% is not < 50, so should NOT be flagged
        flagged = [a for a in score.areas_for_improvement if "investigation" in a]
        assert len(flagged) == 0


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_empty_sessions(self):
        t = GameDayTrainer()
        r = t.generate_report([])
        assert r.sessions_completed == 0
        assert r.average_score == 0.0
        assert r.score_trend == []
        assert r.weakest_phase == ""
        assert r.strongest_phase == ""
        assert r.dora_evidence_generated is False
        assert "No sessions to report on" in r.recommendations

    def test_single_session(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(correct=True))
        t.end_session(s)
        r = t.generate_report([s])
        assert r.sessions_completed == 1
        assert r.average_score == 100.0
        assert len(r.score_trend) == 1

    def test_dora_evidence_generated(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(correct=True))
        t.end_session(s)
        r = t.generate_report([s])
        assert r.dora_evidence_generated is True

    def test_no_dora_evidence_empty(self):
        t = GameDayTrainer()
        r = t.generate_report([])
        assert r.dora_evidence_generated is False

    def test_multiple_sessions_average(self):
        t = GameDayTrainer()
        sessions = []
        # Session 1: 100%
        s1 = _make_session(t)
        t.record_action(s1, _make_action(correct=True))
        t.end_session(s1)
        sessions.append(s1)
        # Session 2: 0%
        s2 = _make_session(t)
        t.record_action(s2, _make_action(correct=False))
        t.end_session(s2)
        sessions.append(s2)
        r = t.generate_report(sessions)
        assert r.average_score == 50.0

    def test_score_trend(self):
        t = GameDayTrainer()
        sessions = []
        for correct in [True, False, True]:
            s = _make_session(t)
            t.record_action(s, _make_action(correct=correct))
            t.end_session(s)
            sessions.append(s)
        r = t.generate_report(sessions)
        assert r.score_trend == [100.0, 0.0, 100.0]

    def test_weakest_and_strongest_phase(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(phase=TrainingPhase.DETECTION, correct=True))
        t.record_action(s, _make_action(phase=TrainingPhase.TRIAGE, correct=False))
        t.end_session(s)
        r = t.generate_report([s])
        assert r.weakest_phase == "triage"
        assert r.strongest_phase == "detection"

    def test_recommendations_low_score(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(correct=False))
        t.end_session(s)
        r = t.generate_report([s])
        assert any("additional training" in rec for rec in r.recommendations)

    def test_recommendations_moderate_score(self):
        t = GameDayTrainer()
        s = _make_session(t)
        # 3 correct, 1 wrong = 75%
        for _ in range(3):
            t.record_action(s, _make_action(correct=True))
        t.record_action(s, _make_action(correct=False))
        t.end_session(s)
        r = t.generate_report([s])
        assert any("weaker phases" in rec for rec in r.recommendations)

    def test_recommendations_few_sessions(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(correct=True))
        t.end_session(s)
        r = t.generate_report([s])
        assert any("more sessions" in rec for rec in r.recommendations)

    def test_recommendations_weakest_phase_mentioned(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(phase=TrainingPhase.RECOVERY, correct=False))
        t.record_action(s, _make_action(phase=TrainingPhase.DETECTION, correct=True))
        t.end_session(s)
        r = t.generate_report([s])
        assert any("recovery" in rec for rec in r.recommendations)

    def test_report_type(self):
        t = GameDayTrainer()
        r = t.generate_report([])
        assert isinstance(r, TrainingReport)

    def test_sessions_without_score_auto_scored(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(correct=True))
        # Don't call end_session, so s.score is None
        r = t.generate_report([s])
        assert r.sessions_completed == 1
        assert r.average_score == 100.0

    def test_three_sessions_enough_trend(self):
        t = GameDayTrainer()
        sessions = []
        for _ in range(3):
            s = _make_session(t)
            t.record_action(s, _make_action(correct=True))
            t.end_session(s)
            sessions.append(s)
        r = t.generate_report(sessions)
        # 3 sessions -> no "more sessions" rec
        assert not any("more sessions" in rec for rec in r.recommendations)

    def test_perfect_score_recommendation(self):
        t = GameDayTrainer()
        sessions = []
        for _ in range(5):
            s = _make_session(t)
            t.record_action(s, _make_action(correct=True, phase=TrainingPhase.DETECTION))
            t.record_action(s, _make_action(correct=True, phase=TrainingPhase.TRIAGE))
            t.end_session(s)
            sessions.append(s)
        r = t.generate_report(sessions)
        # avg = 100, >= 3 sessions, both phases are 100%, weakest exists
        # Should have at most the weakest-phase rec and maintain-cadence
        assert r.average_score == 100.0

    def test_report_with_mixed_phases(self):
        t = GameDayTrainer()
        s = _make_session(t)
        for phase in TrainingPhase:
            t.record_action(s, _make_action(phase=phase, correct=(phase != TrainingPhase.POSTMORTEM)))
        t.end_session(s)
        r = t.generate_report([s])
        assert r.weakest_phase == "postmortem"

    def test_report_multiple_sessions_phase_aggregation(self):
        t = GameDayTrainer()
        sessions = []
        # Session 1: detection=100%, triage=0%
        s1 = _make_session(t)
        t.record_action(s1, _make_action(phase=TrainingPhase.DETECTION, correct=True))
        t.record_action(s1, _make_action(phase=TrainingPhase.TRIAGE, correct=False))
        t.end_session(s1)
        sessions.append(s1)
        # Session 2: detection=0%, triage=100%
        s2 = _make_session(t)
        t.record_action(s2, _make_action(phase=TrainingPhase.DETECTION, correct=False))
        t.record_action(s2, _make_action(phase=TrainingPhase.TRIAGE, correct=True))
        t.end_session(s2)
        sessions.append(s2)
        r = t.generate_report(sessions)
        # Both phases avg 50%, so weakest/strongest may be equal — just verify they exist
        assert r.weakest_phase != ""
        assert r.strongest_phase != ""

    def test_score_trend_rounded(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.record_action(s, _make_action(correct=True))
        t.record_action(s, _make_action(correct=True))
        t.record_action(s, _make_action(correct=False))
        t.end_session(s)
        r = t.generate_report([s])
        for val in r.score_trend:
            assert val == round(val, 2)

    def test_average_score_rounded(self):
        t = GameDayTrainer()
        sessions = []
        for correct in [True, True, False]:
            s = _make_session(t)
            t.record_action(s, _make_action(correct=correct))
            t.end_session(s)
            sessions.append(s)
        r = t.generate_report(sessions)
        assert r.average_score == round(r.average_score, 2)


# ---------------------------------------------------------------------------
# Integration / end-to-end tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_workflow(self):
        t = GameDayTrainer()
        sc = t.create_scenario(
            "DR Drill",
            DifficultyLevel.INTERMEDIATE,
            ["api", "db"],
            ["network-partition", "disk-full"],
        )
        s = t.start_session(
            sc,
            [ParticipantRole.INCIDENT_COMMANDER, ParticipantRole.ON_CALL_ENGINEER,
             ParticipantRole.COMMUNICATION_LEAD],
        )
        # Record actions for each phase
        for phase in TrainingPhase:
            t.record_action(s, _make_action(
                role=ParticipantRole.INCIDENT_COMMANDER, phase=phase, correct=True,
            ))
            t.record_action(s, _make_action(
                role=ParticipantRole.ON_CALL_ENGINEER, phase=phase, correct=True,
            ))
            t.record_action(s, _make_action(
                role=ParticipantRole.COMMUNICATION_LEAD, phase=phase, correct=(phase != TrainingPhase.POSTMORTEM),
            ))
        t.end_session(s)
        assert s.score is not None
        assert s.score.overall_score > 80.0
        r = t.generate_report([s])
        assert r.sessions_completed == 1
        assert r.dora_evidence_generated is True

    def test_multiple_sessions_report(self):
        t = GameDayTrainer()
        sessions = []
        for diff in DifficultyLevel:
            sc = _make_scenario(t, difficulty=diff)
            s = t.start_session(sc, [ParticipantRole.ON_CALL_ENGINEER])
            t.record_action(s, _make_action(correct=True))
            t.end_session(s)
            sessions.append(s)
        r = t.generate_report(sessions)
        assert r.sessions_completed == 4
        assert r.average_score == 100.0

    def test_trainer_accumulates_sessions(self):
        t = GameDayTrainer()
        for _ in range(5):
            _make_session(t)
        assert len(t._sessions) == 5

    def test_session_not_shared_across_trainers(self):
        t1 = GameDayTrainer()
        t2 = GameDayTrainer()
        _make_session(t1)
        assert len(t1._sessions) == 1
        assert len(t2._sessions) == 0

    def test_scenario_reuse_across_sessions(self):
        t = GameDayTrainer()
        sc = _make_scenario(t)
        s1 = t.start_session(sc, [ParticipantRole.ON_CALL_ENGINEER])
        s2 = t.start_session(sc, [ParticipantRole.INCIDENT_COMMANDER])
        assert s1.scenario == s2.scenario
        assert s1.session_id != s2.session_id

    def test_empty_session_scoring(self):
        t = GameDayTrainer()
        s = _make_session(t)
        t.end_session(s)
        assert s.score is not None
        assert s.score.overall_score == 0.0
        r = t.generate_report([s])
        assert r.sessions_completed == 1

    def test_high_performing_team_maintain_cadence(self):
        """When avg >= 80, 3+ sessions, and weakest phase >= 80%, recommend maintaining cadence."""
        t = GameDayTrainer()
        sessions = []
        for _ in range(4):
            s = _make_session(t)
            # All correct across all phases -> all phase accuracies = 100%
            for phase in TrainingPhase:
                t.record_action(s, _make_action(phase=phase, correct=True))
            t.end_session(s)
            sessions.append(s)
        r = t.generate_report(sessions)
        assert r.average_score == 100.0
        assert "Team is performing well" in " ".join(r.recommendations)

    def test_weakest_phase_recommendation_only_when_below_80(self):
        """Weakest phase recommendation only fires when its accuracy is below 80%."""
        t = GameDayTrainer()
        sessions = []
        for _ in range(3):
            s = _make_session(t)
            t.record_action(s, _make_action(phase=TrainingPhase.DETECTION, correct=True))
            t.record_action(s, _make_action(phase=TrainingPhase.TRIAGE, correct=True))
            t.end_session(s)
            sessions.append(s)
        r = t.generate_report(sessions)
        # All phases at 100%, so no "Prioritize improvement" recommendation
        assert not any("Prioritize improvement" in rec for rec in r.recommendations)
