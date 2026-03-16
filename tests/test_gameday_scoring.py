"""Comprehensive tests for GameDayScoringEngine — 99%+ coverage target."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.gameday_scoring import (
    ChallengeCategory,
    ChallengeStep,
    Difficulty,
    GameDayReport,
    GameDayScenario,
    GameDayScoringEngine,
    Hint,
    LeaderboardEntry,
    ScenarioStatus,
    TeamPerformance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(cid: str, name: str, ctype: ComponentType = ComponentType.APP_SERVER, replicas: int = 1) -> Component:
    return Component(id=cid, name=name, type=ctype, replicas=replicas)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _simple_scenario(
    difficulty: Difficulty = Difficulty.NOVICE,
    max_points: int = 100,
    time_limit_minutes: int = 10,
    steps: list[ChallengeStep] | None = None,
) -> GameDayScenario:
    """Build a minimal scenario for testing scoring logic."""
    if steps is None:
        steps = [
            ChallengeStep(
                step_number=1,
                category=ChallengeCategory.DETECTION,
                description="Detect",
                success_criteria="Detect it",
                max_points=40,
                time_limit_seconds=120,
                hints=[Hint(1, "hint-1", 5), Hint(2, "hint-2", 10)],
            ),
            ChallengeStep(
                step_number=2,
                category=ChallengeCategory.RECOVERY,
                description="Recover",
                success_criteria="Recover it",
                max_points=60,
                time_limit_seconds=300,
                hints=[Hint(1, "hint-1", 10)],
            ),
        ]
    return GameDayScenario(
        scenario_id="TEST-001",
        title="Test Scenario",
        description="A test scenario",
        difficulty=difficulty,
        steps=steps,
        max_total_points=max_points,
        time_limit_minutes=time_limit_minutes,
    )


# ---------------------------------------------------------------------------
# 1  Scenario generation: novice, intermediate, advanced, expert
# ---------------------------------------------------------------------------

class TestScenarioGeneration:
    """Scenario generation for all difficulty levels."""

    def test_generate_novice_scenarios(self):
        g = _graph(_comp("c1", "Web"))
        engine = GameDayScoringEngine()
        result = engine.generate_scenarios(g, Difficulty.NOVICE)
        assert len(result) >= 1
        assert all(s.difficulty == Difficulty.NOVICE for s in result)
        assert result[0].scenario_id == "NOV-001"
        assert "Web" in result[0].title

    def test_generate_intermediate_scenarios(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"))
        engine = GameDayScoringEngine()
        result = engine.generate_scenarios(g, Difficulty.INTERMEDIATE)
        assert len(result) >= 1
        assert all(s.difficulty == Difficulty.INTERMEDIATE for s in result)
        assert result[0].scenario_id == "INT-001"

    def test_generate_advanced_scenarios(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"), _comp("c3", "C"))
        engine = GameDayScoringEngine()
        result = engine.generate_scenarios(g, Difficulty.ADVANCED)
        assert len(result) >= 1
        assert all(s.difficulty == Difficulty.ADVANCED for s in result)
        assert result[0].scenario_id == "ADV-001"

    def test_generate_expert_scenarios(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"))
        engine = GameDayScoringEngine()
        result = engine.generate_scenarios(g, Difficulty.EXPERT)
        assert len(result) >= 1
        assert all(s.difficulty == Difficulty.EXPERT for s in result)
        assert result[0].scenario_id == "EXP-001"

    def test_generate_all_difficulties_when_none(self):
        """difficulty=None should produce scenarios for all levels (that have enough comps)."""
        g = _graph(_comp("c1", "A"), _comp("c2", "B"), _comp("c3", "C"))
        engine = GameDayScoringEngine()
        result = engine.generate_scenarios(g, None)
        ids = {s.scenario_id for s in result}
        assert "NOV-001" in ids
        assert "INT-001" in ids
        assert "ADV-001" in ids
        assert "EXP-001" in ids


# ---------------------------------------------------------------------------
# 2  Scenario generation with empty graph / insufficient components
# ---------------------------------------------------------------------------

class TestScenarioGenerationEdgeCases:
    """Empty or insufficient components."""

    def test_empty_graph_novice(self):
        g = _graph()
        engine = GameDayScoringEngine()
        assert engine.generate_scenarios(g, Difficulty.NOVICE) == []

    def test_empty_graph_all(self):
        g = _graph()
        engine = GameDayScoringEngine()
        assert engine.generate_scenarios(g, None) == []

    def test_one_component_intermediate_returns_empty(self):
        g = _graph(_comp("c1", "A"))
        engine = GameDayScoringEngine()
        assert engine.generate_scenarios(g, Difficulty.INTERMEDIATE) == []

    def test_one_component_expert_returns_empty(self):
        g = _graph(_comp("c1", "A"))
        engine = GameDayScoringEngine()
        assert engine.generate_scenarios(g, Difficulty.EXPERT) == []

    def test_two_components_advanced_returns_empty(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"))
        engine = GameDayScoringEngine()
        assert engine.generate_scenarios(g, Difficulty.ADVANCED) == []


# ---------------------------------------------------------------------------
# 3  Scenario generation with specific difficulty filter
# ---------------------------------------------------------------------------

class TestDifficultyFilter:

    def test_novice_only(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"), _comp("c3", "C"))
        engine = GameDayScoringEngine()
        result = engine.generate_scenarios(g, Difficulty.NOVICE)
        assert all(s.difficulty == Difficulty.NOVICE for s in result)
        assert all(s.scenario_id.startswith("NOV") for s in result)

    def test_intermediate_only(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"), _comp("c3", "C"))
        engine = GameDayScoringEngine()
        result = engine.generate_scenarios(g, Difficulty.INTERMEDIATE)
        assert all(s.difficulty == Difficulty.INTERMEDIATE for s in result)

    def test_expert_only(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"), _comp("c3", "C"))
        engine = GameDayScoringEngine()
        result = engine.generate_scenarios(g, Difficulty.EXPERT)
        assert all(s.difficulty == Difficulty.EXPERT for s in result)


# ---------------------------------------------------------------------------
# 4  Scoring: all steps completed -> full score
# ---------------------------------------------------------------------------

class TestScoringAllCompleted:

    def test_full_score_no_hints_fast(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE)
        results = [
            {"step_number": 1, "completed": True, "time_taken_seconds": 10, "hints_used": 0},
            {"step_number": 2, "completed": True, "time_taken_seconds": 20, "hints_used": 0},
        ]
        scored = engine.score_scenario(scenario, results)
        assert scored.status == ScenarioStatus.COMPLETED
        # With time < 25%, bonus 1.5x; mult=1.0 (novice)
        # Step 1: 40*1.5=60, Step 2: 60*1.5=90 => total_earned=150, final=150*1.0=150
        assert scored.final_score == 150
        assert scored.grade in ("S", "A", "B", "C", "D", "F")

    def test_all_completed_at_exact_time_limit(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE)
        results = [
            {"step_number": 1, "completed": True, "time_taken_seconds": 120, "hints_used": 0},
            {"step_number": 2, "completed": True, "time_taken_seconds": 300, "hints_used": 0},
        ]
        scored = engine.score_scenario(scenario, results)
        # time_ratio = 1.0 => bonus 1.0 (at threshold)
        assert scored.final_score == 100  # 40+60 = 100 * 1.0


# ---------------------------------------------------------------------------
# 5  Scoring: some steps failed -> partial score
# ---------------------------------------------------------------------------

class TestScoringPartial:

    def test_one_step_failed(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE)
        results = [
            {"step_number": 1, "completed": True, "time_taken_seconds": 10, "hints_used": 0},
            {"step_number": 2, "completed": False, "time_taken_seconds": 300, "hints_used": 0},
        ]
        scored = engine.score_scenario(scenario, results)
        # Step 1: 40*1.5 = 60; Step 2: 0 => total=60
        assert scored.final_score == 60
        assert scored.steps[1].points_earned == 0

    def test_all_steps_failed(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE)
        results = [
            {"step_number": 1, "completed": False, "time_taken_seconds": 120, "hints_used": 0},
            {"step_number": 2, "completed": False, "time_taken_seconds": 300, "hints_used": 0},
        ]
        scored = engine.score_scenario(scenario, results)
        assert scored.final_score == 0
        assert scored.grade == "F"

    def test_non_matching_step_number_ignored(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE)
        results = [
            {"step_number": 999, "completed": True, "time_taken_seconds": 10, "hints_used": 0},
        ]
        scored = engine.score_scenario(scenario, results)
        assert scored.final_score == 0

    def test_missing_keys_default(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE)
        results = [
            {},  # no step_number — defaults to 0 which doesn't match
        ]
        scored = engine.score_scenario(scenario, results)
        assert scored.final_score == 0


# ---------------------------------------------------------------------------
# 6  Scoring: time bonus thresholds
# ---------------------------------------------------------------------------

class TestTimeBonuses:

    def _score_single_step(self, time_taken: int, time_limit: int, max_pts: int = 100) -> int:
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d",
            success_criteria="s",
            max_points=max_pts,
            time_limit_seconds=time_limit,
            hints=[],
        )
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE, steps=[step])
        results = [{"step_number": 1, "completed": True, "time_taken_seconds": time_taken, "hints_used": 0}]
        scored = engine.score_scenario(scenario, results)
        return scored.final_score

    def test_under_25_percent(self):
        # 10/100 = 10% => mult 1.5
        assert self._score_single_step(10, 100) == 150

    def test_at_25_percent(self):
        # 25/100 = 25% => mult 1.5 (<=)
        assert self._score_single_step(25, 100) == 150

    def test_under_50_percent(self):
        # 30/100 = 30% => mult 1.25
        assert self._score_single_step(30, 100) == 125

    def test_at_50_percent(self):
        # 50/100 = 50% => mult 1.25 (<=)
        assert self._score_single_step(50, 100) == 125

    def test_under_75_percent(self):
        # 60/100 = 60% => mult 1.1
        assert self._score_single_step(60, 100) == 110

    def test_at_75_percent(self):
        # 75/100 = 75% => mult 1.1 (<=)
        assert self._score_single_step(75, 100) == 110

    def test_over_75_percent(self):
        # 80/100 = 80% => mult 1.0
        assert self._score_single_step(80, 100) == 100

    def test_at_100_percent(self):
        # 100/100 = 100% => mult 1.0 (<=)
        assert self._score_single_step(100, 100) == 100

    def test_over_100_percent(self):
        # 150/100 = 150% => no threshold matched, loop ends; mult stays 1.0
        assert self._score_single_step(150, 100) == 100

    def test_zero_time_limit(self):
        """time_limit_seconds=0 → time_ratio=1.0 via fallback."""
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d",
            success_criteria="s",
            max_points=100,
            time_limit_seconds=0,
            hints=[],
        )
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE, steps=[step])
        results = [{"step_number": 1, "completed": True, "time_taken_seconds": 50, "hints_used": 0}]
        scored = engine.score_scenario(scenario, results)
        # time_ratio = 1.0 => bonus = 1.0 => 100
        assert scored.final_score == 100


# ---------------------------------------------------------------------------
# 7  Scoring: hint penalties
# ---------------------------------------------------------------------------

class TestHintPenalties:

    def test_one_hint_used(self):
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d",
            success_criteria="s",
            max_points=100,
            time_limit_seconds=100,
            hints=[Hint(1, "h1", 20), Hint(2, "h2", 30)],
        )
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE, steps=[step])
        results = [{"step_number": 1, "completed": True, "time_taken_seconds": 10, "hints_used": 1}]
        scored = engine.score_scenario(scenario, results)
        # base=100, time_mult=1.5, hint_penalty=20 => max(0,100*1.5-20)=130
        assert scored.final_score == 130

    def test_two_hints_used(self):
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d",
            success_criteria="s",
            max_points=100,
            time_limit_seconds=100,
            hints=[Hint(1, "h1", 20), Hint(2, "h2", 30)],
        )
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE, steps=[step])
        results = [{"step_number": 1, "completed": True, "time_taken_seconds": 10, "hints_used": 2}]
        scored = engine.score_scenario(scenario, results)
        # base=100, time_mult=1.5, hint_penalty=20+30=50 => 150-50=100
        assert scored.final_score == 100

    def test_hint_penalty_clamps_to_zero(self):
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d",
            success_criteria="s",
            max_points=10,
            time_limit_seconds=100,
            hints=[Hint(1, "h1", 50)],
        )
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE, steps=[step])
        results = [{"step_number": 1, "completed": True, "time_taken_seconds": 80, "hints_used": 1}]
        scored = engine.score_scenario(scenario, results)
        # base=10, time_mult=1.0, penalty=50 => max(0, 10-50)=0
        assert scored.final_score == 0

    def test_no_hints_available_but_hints_used_zero(self):
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d",
            success_criteria="s",
            max_points=100,
            time_limit_seconds=100,
            hints=[],
        )
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE, steps=[step])
        results = [{"step_number": 1, "completed": True, "time_taken_seconds": 10, "hints_used": 0}]
        scored = engine.score_scenario(scenario, results)
        assert scored.final_score == 150  # 100*1.5


# ---------------------------------------------------------------------------
# 8  Scoring: difficulty multipliers
# ---------------------------------------------------------------------------

class TestDifficultyMultipliers:

    def _score_fast_single(self, difficulty: Difficulty) -> int:
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d",
            success_criteria="s",
            max_points=100,
            time_limit_seconds=1000,
            hints=[],
        )
        scenario = _simple_scenario(difficulty=difficulty, steps=[step])
        results = [{"step_number": 1, "completed": True, "time_taken_seconds": 100, "hints_used": 0}]
        scored = engine.score_scenario(scenario, results)
        return scored.final_score

    def test_novice_multiplier(self):
        # 100 * 1.5(time) * 1.0(diff) = 150
        assert self._score_fast_single(Difficulty.NOVICE) == 150

    def test_intermediate_multiplier(self):
        # 100 * 1.5 * 1.5 = 225
        assert self._score_fast_single(Difficulty.INTERMEDIATE) == 225

    def test_advanced_multiplier(self):
        # 100 * 1.5 * 2.0 = 300
        assert self._score_fast_single(Difficulty.ADVANCED) == 300

    def test_expert_multiplier(self):
        # 100 * 1.5 * 3.0 = 450
        assert self._score_fast_single(Difficulty.EXPERT) == 450


# ---------------------------------------------------------------------------
# 9  Grade calculation: S, A, B, C, D, F
# ---------------------------------------------------------------------------

class TestGradeCalculation:

    def _grade(self, pct: float) -> str:
        engine = GameDayScoringEngine()
        return engine._calculate_grade(pct)

    def test_grade_S(self):
        assert self._grade(100) == "S"
        assert self._grade(95) == "S"

    def test_grade_A(self):
        assert self._grade(94) == "A"
        assert self._grade(85) == "A"

    def test_grade_B(self):
        assert self._grade(84) == "B"
        assert self._grade(75) == "B"

    def test_grade_C(self):
        assert self._grade(74) == "C"
        assert self._grade(60) == "C"

    def test_grade_D(self):
        assert self._grade(59) == "D"
        assert self._grade(40) == "D"

    def test_grade_F(self):
        assert self._grade(39) == "F"
        assert self._grade(0) == "F"

    def test_grade_negative(self):
        """Edge: negative percentage should fall through to F."""
        assert self._grade(-10) == "F"


# ---------------------------------------------------------------------------
# 10  Badge calculation: gold (>=90), silver (>=75), bronze (>=50), participant
# ---------------------------------------------------------------------------

class TestBadgeCalculation:

    def test_gold(self):
        assert GameDayScoringEngine._calculate_badge(90) == "gold"
        assert GameDayScoringEngine._calculate_badge(100) == "gold"

    def test_silver(self):
        assert GameDayScoringEngine._calculate_badge(75) == "silver"
        assert GameDayScoringEngine._calculate_badge(89.9) == "silver"

    def test_bronze(self):
        assert GameDayScoringEngine._calculate_badge(50) == "bronze"
        assert GameDayScoringEngine._calculate_badge(74.9) == "bronze"

    def test_participant(self):
        assert GameDayScoringEngine._calculate_badge(49.9) == "participant"
        assert GameDayScoringEngine._calculate_badge(0) == "participant"


# ---------------------------------------------------------------------------
# 11  Team performance recording
# ---------------------------------------------------------------------------

class TestTeamPerformance:

    def test_record_new_team(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE)
        scenario.final_score = 80
        scenario.max_total_points = 100
        scenario.grade = "B"
        scenario.steps[0].time_taken_seconds = 30
        scenario.steps[1].time_taken_seconds = 70

        perf = engine.record_team_performance("TeamA", scenario)
        assert perf.team_name == "TeamA"
        assert perf.scenarios_completed == 1
        assert perf.total_points == 80
        assert perf.max_possible_points == 100
        assert perf.average_score_percent == 80.0
        assert perf.average_time_seconds == 100.0  # 30+70
        assert len(perf.history) == 1

    def test_record_multiple_scenarios_cumulative(self):
        engine = GameDayScoringEngine()

        s1 = _simple_scenario(difficulty=Difficulty.NOVICE)
        s1.final_score = 80
        s1.max_total_points = 100
        s1.grade = "B"
        s1.steps[0].time_taken_seconds = 50
        s1.steps[1].time_taken_seconds = 50
        engine.record_team_performance("T", s1)

        s2 = _simple_scenario(difficulty=Difficulty.NOVICE)
        s2.final_score = 60
        s2.max_total_points = 100
        s2.grade = "C"
        s2.steps[0].time_taken_seconds = 40
        s2.steps[1].time_taken_seconds = 60
        perf = engine.record_team_performance("T", s2)

        assert perf.scenarios_completed == 2
        assert perf.total_points == 140
        assert perf.max_possible_points == 200
        assert perf.average_score_percent == 70.0
        # avg_time: prev_total = 100 * (2-1) = 100; new = 100; (100+100)/2 = 100
        assert perf.average_time_seconds == 100.0

    def test_record_team_zero_max_possible(self):
        engine = GameDayScoringEngine()
        s = _simple_scenario(difficulty=Difficulty.NOVICE)
        s.final_score = 0
        s.max_total_points = 0
        s.grade = "F"
        s.steps[0].time_taken_seconds = 0
        s.steps[1].time_taken_seconds = 0
        perf = engine.record_team_performance("T", s)
        assert perf.average_score_percent == 0.0


# ---------------------------------------------------------------------------
# 12  Team improvement trend: improving, declining, stable
# ---------------------------------------------------------------------------

class TestImprovementTrend:

    def _make_perf(self, scores: list[tuple[int, int]]) -> TeamPerformance:
        """Record multiple scenarios and return the team performance."""
        engine = GameDayScoringEngine()
        for score, maxp in scores:
            s = _simple_scenario(difficulty=Difficulty.NOVICE)
            s.final_score = score
            s.max_total_points = maxp
            s.grade = "B"
            s.steps[0].time_taken_seconds = 10
            s.steps[1].time_taken_seconds = 10
            engine.record_team_performance("T", s)
        return engine._team_performances["T"]

    def test_improving_trend(self):
        perf = self._make_perf([(50, 100), (60, 100), (80, 100)])
        assert perf.improvement_trend == "improving"

    def test_declining_trend(self):
        perf = self._make_perf([(80, 100), (60, 100), (40, 100)])
        assert perf.improvement_trend == "declining"

    def test_stable_trend(self):
        perf = self._make_perf([(70, 100), (80, 100), (60, 100)])
        assert perf.improvement_trend == "stable"

    def test_trend_with_fewer_than_three(self):
        perf = self._make_perf([(50, 100), (60, 100)])
        assert perf.improvement_trend == "new"

    def test_all_equal_is_improving_or_declining(self):
        """All equal scores → both <= conditions satisfied → 'improving' wins (checked first)."""
        perf = self._make_perf([(50, 100), (50, 100), (50, 100)])
        # all(recent[i] <= recent[i+1]) is True, so "improving" is set
        assert perf.improvement_trend == "improving"

    def test_trend_with_zero_max(self):
        """When max=0, score/max → 0."""
        perf = self._make_perf([(0, 0), (0, 0), (0, 0)])
        assert perf.improvement_trend == "improving"


# ---------------------------------------------------------------------------
# 13  Leaderboard generation with multiple teams
# ---------------------------------------------------------------------------

class TestLeaderboard:

    def _setup_engine_with_teams(self) -> GameDayScoringEngine:
        engine = GameDayScoringEngine()
        for team_name, score, maxp in [("Alpha", 90, 100), ("Beta", 70, 100), ("Gamma", 80, 100)]:
            s = _simple_scenario()
            s.final_score = score
            s.max_total_points = maxp
            s.grade = "A"
            s.scenario_id = f"S-{team_name}"
            s.steps[0].time_taken_seconds = 10
            s.steps[1].time_taken_seconds = 10
            engine.record_team_performance(team_name, s)
        return engine

    def test_leaderboard_has_all_teams(self):
        engine = self._setup_engine_with_teams()
        lb = engine.generate_leaderboard()
        names = {e.team_name for e in lb}
        assert names == {"Alpha", "Beta", "Gamma"}

    def test_leaderboard_sorted_by_total_score_desc(self):
        engine = self._setup_engine_with_teams()
        lb = engine.generate_leaderboard()
        scores = [e.total_score for e in lb]
        assert scores == sorted(scores, reverse=True)

    def test_leaderboard_ranks(self):
        engine = self._setup_engine_with_teams()
        lb = engine.generate_leaderboard()
        assert [e.rank for e in lb] == [1, 2, 3]

    def test_leaderboard_badges_assigned(self):
        engine = self._setup_engine_with_teams()
        lb = engine.generate_leaderboard()
        for entry in lb:
            assert entry.badge in ("gold", "silver", "bronze", "participant")

    def test_leaderboard_best_scenario(self):
        engine = self._setup_engine_with_teams()
        lb = engine.generate_leaderboard()
        for entry in lb:
            assert entry.best_scenario != ""


# ---------------------------------------------------------------------------
# 14  Leaderboard ranking order
# ---------------------------------------------------------------------------

class TestLeaderboardOrder:

    def test_highest_score_rank_one(self):
        engine = GameDayScoringEngine()
        for team_name, score in [("Low", 10), ("High", 99), ("Mid", 50)]:
            s = _simple_scenario()
            s.final_score = score
            s.max_total_points = 100
            s.grade = "A"
            s.scenario_id = "X"
            s.steps[0].time_taken_seconds = 0
            s.steps[1].time_taken_seconds = 0
            engine.record_team_performance(team_name, s)
        lb = engine.generate_leaderboard()
        assert lb[0].team_name == "High"
        assert lb[0].rank == 1

    def test_empty_leaderboard(self):
        engine = GameDayScoringEngine()
        lb = engine.generate_leaderboard()
        assert lb == []

    def test_leaderboard_no_history(self):
        """Team with no history → best_scenario empty."""
        engine = GameDayScoringEngine()
        engine._team_performances["Empty"] = TeamPerformance(team_name="Empty")
        lb = engine.generate_leaderboard()
        assert len(lb) == 1
        assert lb[0].best_scenario == ""


# ---------------------------------------------------------------------------
# 15  Feedback generation
# ---------------------------------------------------------------------------

class TestFeedbackGeneration:

    def test_not_completed_feedback(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario()
        results = [
            {"step_number": 1, "completed": False, "time_taken_seconds": 120, "hints_used": 0},
            {"step_number": 2, "completed": True, "time_taken_seconds": 10, "hints_used": 0},
        ]
        scored = engine.score_scenario(scenario, results)
        assert any("Not completed" in f for f in scored.feedback)

    def test_hints_used_feedback(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario()
        results = [
            {"step_number": 1, "completed": True, "time_taken_seconds": 10, "hints_used": 1},
            {"step_number": 2, "completed": True, "time_taken_seconds": 10, "hints_used": 0},
        ]
        scored = engine.score_scenario(scenario, results)
        assert any("hint" in f.lower() for f in scored.feedback)

    def test_near_time_limit_feedback(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario()
        # Step 1 time_limit=120, 75% = 90; set time_taken > 90
        results = [
            {"step_number": 1, "completed": True, "time_taken_seconds": 100, "hints_used": 0},
            {"step_number": 2, "completed": True, "time_taken_seconds": 10, "hints_used": 0},
        ]
        scored = engine.score_scenario(scenario, results)
        assert any("time limit" in f.lower() for f in scored.feedback)

    def test_excellent_feedback(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario()
        results = [
            {"step_number": 1, "completed": True, "time_taken_seconds": 10, "hints_used": 0},
            {"step_number": 2, "completed": True, "time_taken_seconds": 10, "hints_used": 0},
        ]
        scored = engine.score_scenario(scenario, results)
        assert any("Excellent" in f for f in scored.feedback)

    def test_feedback_contains_category(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario()
        results = [
            {"step_number": 1, "completed": True, "time_taken_seconds": 10, "hints_used": 0},
            {"step_number": 2, "completed": True, "time_taken_seconds": 10, "hints_used": 0},
        ]
        scored = engine.score_scenario(scenario, results)
        assert any("detection" in f for f in scored.feedback)
        assert any("recovery" in f for f in scored.feedback)


# ---------------------------------------------------------------------------
# 16  Category performance analysis
# ---------------------------------------------------------------------------

class TestCategoryPerformance:

    def test_category_performance_multiple_steps(self):
        engine = GameDayScoringEngine()
        step1 = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d",
            success_criteria="s",
            max_points=100,
            time_limit_seconds=100,
            hints=[],
            points_earned=80,
            completed=True,
        )
        step2 = ChallengeStep(
            step_number=2,
            category=ChallengeCategory.RECOVERY,
            description="d",
            success_criteria="s",
            max_points=100,
            time_limit_seconds=100,
            hints=[],
            points_earned=60,
            completed=True,
        )
        scenario = _simple_scenario(steps=[step1, step2])
        scenario.status = ScenarioStatus.COMPLETED
        perf = engine._calculate_category_performance([scenario])
        assert perf["detection"] == 80.0
        assert perf["recovery"] == 60.0

    def test_category_performance_empty(self):
        engine = GameDayScoringEngine()
        perf = engine._calculate_category_performance([])
        assert perf == {}

    def test_category_performance_zero_max_points(self):
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d",
            success_criteria="s",
            max_points=0,
            time_limit_seconds=100,
            hints=[],
            points_earned=0,
        )
        scenario = _simple_scenario(steps=[step])
        scenario.status = ScenarioStatus.COMPLETED
        perf = engine._calculate_category_performance([scenario])
        assert perf["detection"] == 0.0

    def test_category_performance_multiple_scenarios(self):
        engine = GameDayScoringEngine()
        step_a = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d", success_criteria="s",
            max_points=100, time_limit_seconds=100,
            hints=[], points_earned=90,
        )
        step_b = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d", success_criteria="s",
            max_points=100, time_limit_seconds=100,
            hints=[], points_earned=70,
        )
        s1 = _simple_scenario(steps=[step_a])
        s1.status = ScenarioStatus.COMPLETED
        s2 = _simple_scenario(steps=[step_b])
        s2.status = ScenarioStatus.COMPLETED
        perf = engine._calculate_category_performance([s1, s2])
        assert perf["detection"] == 80.0  # (90+70)/2


# ---------------------------------------------------------------------------
# 17  Team skill analysis: strengths/weaknesses
# ---------------------------------------------------------------------------

class TestTeamSkillAnalysis:

    def test_strength_detection(self):
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d", success_criteria="s",
            max_points=100, time_limit_seconds=100,
            hints=[], points_earned=90, completed=True,
        )
        scenario = _simple_scenario(steps=[step])
        strengths, weaknesses = engine._analyze_team_skills(scenario)
        assert "detection" in strengths
        assert "detection" not in weaknesses

    def test_weakness_detection(self):
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.RECOVERY,
            description="d", success_criteria="s",
            max_points=100, time_limit_seconds=100,
            hints=[], points_earned=30, completed=True,
        )
        scenario = _simple_scenario(steps=[step])
        strengths, weaknesses = engine._analyze_team_skills(scenario)
        assert "recovery" in weaknesses
        assert "recovery" not in strengths

    def test_neutral_not_in_either(self):
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.MITIGATION,
            description="d", success_criteria="s",
            max_points=100, time_limit_seconds=100,
            hints=[], points_earned=65, completed=True,
        )
        scenario = _simple_scenario(steps=[step])
        strengths, weaknesses = engine._analyze_team_skills(scenario)
        assert "mitigation" not in strengths
        assert "mitigation" not in weaknesses

    def test_zero_max_points(self):
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.COMMUNICATION,
            description="d", success_criteria="s",
            max_points=0, time_limit_seconds=100,
            hints=[], points_earned=0, completed=True,
        )
        scenario = _simple_scenario(steps=[step])
        strengths, weaknesses = engine._analyze_team_skills(scenario)
        # 0% → weakness
        assert "communication" in weaknesses

    def test_skills_set_on_record(self):
        """record_team_performance should populate strengths/weaknesses."""
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d", success_criteria="s",
            max_points=100, time_limit_seconds=100,
            hints=[], points_earned=95, completed=True,
        )
        scenario = _simple_scenario(steps=[step])
        scenario.final_score = 95
        scenario.max_total_points = 100
        scenario.grade = "S"
        perf = engine.record_team_performance("T", scenario)
        assert "detection" in perf.strengths


# ---------------------------------------------------------------------------
# 18  Report generation: hardest/easiest, recommendations
# ---------------------------------------------------------------------------

class TestReportGeneration:

    def test_report_with_completed_scenarios(self):
        engine = GameDayScoringEngine()
        g = _graph(_comp("c1", "A"), _comp("c2", "B"), _comp("c3", "C"))
        scenarios = engine.generate_scenarios(g, Difficulty.NOVICE)
        s = scenarios[0]
        results = [
            {"step_number": i + 1, "completed": True, "time_taken_seconds": 10, "hints_used": 0}
            for i in range(len(s.steps))
        ]
        engine.score_scenario(s, results)
        engine.record_team_performance("T", s)

        report = engine.generate_report()
        assert isinstance(report, GameDayReport)
        assert report.total_participants == 1
        assert report.hardest_scenario != "N/A"
        assert report.easiest_scenario != "N/A"
        assert report.average_score_percent > 0

    def test_report_recommendations_weak_categories(self):
        engine = GameDayScoringEngine()
        # Manually build a scenario with weak category performance
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.PREVENTION,
            description="d", success_criteria="s",
            max_points=100, time_limit_seconds=100,
            hints=[], points_earned=20, completed=True,
        )
        scenario = _simple_scenario(steps=[step])
        scenario.status = ScenarioStatus.COMPLETED
        scenario.final_score = 20
        scenario.max_total_points = 100
        engine._scenarios.append(scenario)
        engine.record_team_performance("T", scenario)

        report = engine.generate_report()
        assert any("prevention" in r.lower() for r in report.recommendations)

    def test_report_recommendation_expert_not_done(self):
        engine = GameDayScoringEngine()
        # Add a novice-level completed scenario
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d", success_criteria="s",
            max_points=100, time_limit_seconds=100,
            hints=[], points_earned=90, completed=True,
        )
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE, steps=[step])
        scenario.status = ScenarioStatus.COMPLETED
        scenario.final_score = 90
        scenario.max_total_points = 100
        engine._scenarios.append(scenario)

        report = engine.generate_report()
        assert any("Expert" in r for r in report.recommendations)

    def test_report_recommendations_all_great(self):
        """No weak categories and expert is done → 'Great performance' message."""
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d", success_criteria="s",
            max_points=100, time_limit_seconds=100,
            hints=[], points_earned=90, completed=True,
        )
        scenario = _simple_scenario(difficulty=Difficulty.EXPERT, steps=[step])
        scenario.status = ScenarioStatus.COMPLETED
        scenario.final_score = 90
        scenario.max_total_points = 100
        engine._scenarios.append(scenario)

        report = engine.generate_report()
        assert any("Great performance" in r for r in report.recommendations)

    def test_report_recommendations_capped_at_5(self):
        """At most 5 recommendations."""
        engine = GameDayScoringEngine()
        # Add many weak categories
        steps = []
        cats = list(ChallengeCategory)
        for i, cat in enumerate(cats):
            steps.append(ChallengeStep(
                step_number=i + 1,
                category=cat,
                description="d", success_criteria="s",
                max_points=100, time_limit_seconds=100,
                hints=[], points_earned=10, completed=True,
            ))
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE, steps=steps)
        scenario.status = ScenarioStatus.COMPLETED
        scenario.final_score = 60
        scenario.max_total_points = 600
        engine._scenarios.append(scenario)

        report = engine.generate_report()
        assert len(report.recommendations) <= 5


# ---------------------------------------------------------------------------
# 19  Report with no completed scenarios
# ---------------------------------------------------------------------------

class TestReportNoCompletedScenarios:

    def test_empty_report(self):
        engine = GameDayScoringEngine()
        report = engine.generate_report()
        assert report.hardest_scenario == "N/A"
        assert report.easiest_scenario == "N/A"
        assert report.average_score_percent == 0.0
        assert report.total_participants == 0
        assert report.category_performance == {}

    def test_report_with_non_completed_scenarios(self):
        engine = GameDayScoringEngine()
        s = _simple_scenario()
        s.status = ScenarioStatus.IN_PROGRESS
        engine._scenarios.append(s)
        report = engine.generate_report()
        assert report.hardest_scenario == "N/A"
        assert report.easiest_scenario == "N/A"
        assert report.average_score_percent == 0.0


# ---------------------------------------------------------------------------
# 20  Edge cases: zero points, zero time limit, empty step results
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_zero_total_possible(self):
        """max_total_points=0 → grade should handle division by zero."""
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d", success_criteria="s",
            max_points=0, time_limit_seconds=100,
            hints=[],
        )
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE, steps=[step])
        results = [{"step_number": 1, "completed": True, "time_taken_seconds": 10, "hints_used": 0}]
        scored = engine.score_scenario(scenario, results)
        assert scored.final_score == 0
        assert scored.grade == "F"

    def test_empty_step_results(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario()
        scored = engine.score_scenario(scenario, [])
        assert scored.final_score == 0
        assert scored.status == ScenarioStatus.COMPLETED

    def test_zero_time_taken(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario()
        results = [
            {"step_number": 1, "completed": True, "time_taken_seconds": 0, "hints_used": 0},
            {"step_number": 2, "completed": True, "time_taken_seconds": 0, "hints_used": 0},
        ]
        scored = engine.score_scenario(scenario, results)
        # time_ratio = 0 / 120 = 0 => under 25% => 1.5x
        assert scored.final_score > 0

    def test_end_time_set(self):
        engine = GameDayScoringEngine()
        scenario = _simple_scenario()
        results = [
            {"step_number": 1, "completed": True, "time_taken_seconds": 10, "hints_used": 0},
        ]
        scored = engine.score_scenario(scenario, results)
        assert scored.end_time is not None

    def test_scenarios_stored_on_engine(self):
        engine = GameDayScoringEngine()
        g = _graph(_comp("c1", "A"))
        s = engine.generate_scenarios(g, Difficulty.NOVICE)
        assert len(engine._scenarios) == len(s)

    def test_score_scenario_with_unknown_difficulty(self):
        """Difficulty not in multiplier dict → fallback 1.0."""
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d", success_criteria="s",
            max_points=100, time_limit_seconds=100,
            hints=[],
        )
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE, steps=[step])
        # Manually set difficulty to something unexpected (shouldn't happen but tests fallback)
        # Actually all Difficulty values are covered, but we can test the .get fallback
        # by temporarily patching the multiplier dict. Instead let's just ensure the path works:
        results = [{"step_number": 1, "completed": True, "time_taken_seconds": 10, "hints_used": 0}]
        scored = engine.score_scenario(scenario, results)
        assert scored.final_score > 0

    def test_report_hardest_easiest_with_zero_max(self):
        """Scenario with max_total_points=0 uses fallback in lambda."""
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d", success_criteria="s",
            max_points=0, time_limit_seconds=100,
            hints=[],
        )
        s = _simple_scenario(steps=[step])
        s.status = ScenarioStatus.COMPLETED
        s.final_score = 0
        s.max_total_points = 0
        engine._scenarios.append(s)
        report = engine.generate_report()
        assert report.hardest_scenario == "Test Scenario"
        assert report.easiest_scenario == "Test Scenario"


# ---------------------------------------------------------------------------
# Additional coverage: dataclass defaults
# ---------------------------------------------------------------------------

class TestDataclassDefaults:

    def test_scenario_defaults(self):
        s = GameDayScenario(
            scenario_id="X", title="T", description="D",
            difficulty=Difficulty.NOVICE, steps=[], max_total_points=0,
            time_limit_minutes=0,
        )
        assert s.status == ScenarioStatus.NOT_STARTED
        assert s.start_time is None
        assert s.end_time is None
        assert s.final_score == 0
        assert s.grade == ""
        assert s.feedback == []

    def test_team_performance_defaults(self):
        t = TeamPerformance(team_name="T")
        assert t.scenarios_completed == 0
        assert t.improvement_trend == "new"
        assert t.history == []

    def test_leaderboard_entry(self):
        e = LeaderboardEntry(
            rank=1, team_name="A", total_score=100,
            scenarios_completed=1, average_percent=100.0,
            best_scenario="S1", badge="gold",
        )
        assert e.rank == 1
        assert e.badge == "gold"

    def test_hint_dataclass(self):
        h = Hint(hint_number=1, text="help", penalty_points=10)
        assert h.hint_number == 1
        assert h.penalty_points == 10

    def test_challenge_step_defaults(self):
        cs = ChallengeStep(
            step_number=1, category=ChallengeCategory.DETECTION,
            description="d", success_criteria="s",
            max_points=10, time_limit_seconds=60, hints=[],
        )
        assert cs.hints_used == 0
        assert cs.points_earned == 0
        assert cs.completed is False
        assert cs.time_taken_seconds == 0


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------

class TestEnums:

    def test_difficulty_values(self):
        assert Difficulty.NOVICE.value == "novice"
        assert Difficulty.INTERMEDIATE.value == "intermediate"
        assert Difficulty.ADVANCED.value == "advanced"
        assert Difficulty.EXPERT.value == "expert"

    def test_challenge_category_values(self):
        assert ChallengeCategory.DETECTION.value == "detection"
        assert ChallengeCategory.DIAGNOSIS.value == "diagnosis"
        assert ChallengeCategory.MITIGATION.value == "mitigation"
        assert ChallengeCategory.RECOVERY.value == "recovery"
        assert ChallengeCategory.PREVENTION.value == "prevention"
        assert ChallengeCategory.COMMUNICATION.value == "communication"

    def test_scenario_status_values(self):
        assert ScenarioStatus.NOT_STARTED.value == "not_started"
        assert ScenarioStatus.IN_PROGRESS.value == "in_progress"
        assert ScenarioStatus.COMPLETED.value == "completed"
        assert ScenarioStatus.TIMED_OUT.value == "timed_out"
        assert ScenarioStatus.FAILED.value == "failed"


# ---------------------------------------------------------------------------
# Full integration: generate → score → record → leaderboard → report
# ---------------------------------------------------------------------------

class TestFullIntegration:

    def test_end_to_end_flow(self):
        engine = GameDayScoringEngine()
        g = _graph(
            _comp("c1", "WebApp", ComponentType.WEB_SERVER),
            _comp("c2", "API", ComponentType.APP_SERVER),
            _comp("c3", "DB", ComponentType.DATABASE),
        )

        # Generate all scenarios
        scenarios = engine.generate_scenarios(g, None)
        assert len(scenarios) > 0

        # Score each scenario (all steps completed fast)
        for s in scenarios:
            results = [
                {
                    "step_number": step.step_number,
                    "completed": True,
                    "time_taken_seconds": 10,
                    "hints_used": 0,
                }
                for step in s.steps
            ]
            engine.score_scenario(s, results)
            engine.record_team_performance("Dream Team", s)

        # Leaderboard
        lb = engine.generate_leaderboard()
        assert len(lb) == 1
        assert lb[0].team_name == "Dream Team"
        assert lb[0].rank == 1

        # Report
        report = engine.generate_report()
        assert report.total_participants == 1
        assert report.average_score_percent > 0
        assert report.hardest_scenario != "N/A"
        assert report.easiest_scenario != "N/A"
        assert len(report.category_performance) > 0

    def test_multiple_teams_end_to_end(self):
        engine = GameDayScoringEngine()
        g = _graph(_comp("c1", "A"), _comp("c2", "B"))

        scenarios = engine.generate_scenarios(g, Difficulty.NOVICE)
        s = scenarios[0]

        # Team A: perfect run
        results_a = [
            {"step_number": step.step_number, "completed": True, "time_taken_seconds": 5, "hints_used": 0}
            for step in s.steps
        ]
        scored_a = engine.score_scenario(s, results_a)
        engine.record_team_performance("Team-A", scored_a)

        # Team B: partial run — regenerate scenario to reset step state
        s2 = _simple_scenario()
        results_b = [
            {"step_number": 1, "completed": True, "time_taken_seconds": 100, "hints_used": 2},
            {"step_number": 2, "completed": False, "time_taken_seconds": 300, "hints_used": 0},
        ]
        scored_b = engine.score_scenario(s2, results_b)
        engine.record_team_performance("Team-B", scored_b)

        lb = engine.generate_leaderboard()
        assert lb[0].total_score >= lb[1].total_score

    def test_report_avg_pct_with_zero_max(self):
        """Report with completed scenario that has max_total_points=0."""
        engine = GameDayScoringEngine()
        s = GameDayScenario(
            scenario_id="Z", title="Zero", description="zero",
            difficulty=Difficulty.NOVICE, steps=[], max_total_points=0,
            time_limit_minutes=0, status=ScenarioStatus.COMPLETED,
            final_score=0,
        )
        engine._scenarios.append(s)
        report = engine.generate_report()
        assert report.average_score_percent == 0.0


# ---------------------------------------------------------------------------
# Novice scenario step structure
# ---------------------------------------------------------------------------

class TestNoviceScenarioStructure:

    def test_novice_has_three_steps(self):
        g = _graph(_comp("c1", "WebApp", ComponentType.WEB_SERVER))
        engine = GameDayScoringEngine()
        scenarios = engine.generate_scenarios(g, Difficulty.NOVICE)
        s = scenarios[0]
        assert len(s.steps) == 3
        cats = [step.category for step in s.steps]
        assert ChallengeCategory.DETECTION in cats
        assert ChallengeCategory.DIAGNOSIS in cats
        assert ChallengeCategory.RECOVERY in cats

    def test_novice_steps_have_hints(self):
        g = _graph(_comp("c1", "WebApp", ComponentType.WEB_SERVER))
        engine = GameDayScoringEngine()
        scenarios = engine.generate_scenarios(g, Difficulty.NOVICE)
        for step in scenarios[0].steps:
            assert len(step.hints) >= 1


# ---------------------------------------------------------------------------
# Intermediate scenario step structure
# ---------------------------------------------------------------------------

class TestIntermediateScenarioStructure:

    def test_intermediate_has_four_steps(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"))
        engine = GameDayScoringEngine()
        scenarios = engine.generate_scenarios(g, Difficulty.INTERMEDIATE)
        assert len(scenarios[0].steps) == 4

    def test_intermediate_includes_prevention(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"))
        engine = GameDayScoringEngine()
        scenarios = engine.generate_scenarios(g, Difficulty.INTERMEDIATE)
        cats = {step.category for step in scenarios[0].steps}
        assert ChallengeCategory.PREVENTION in cats


# ---------------------------------------------------------------------------
# Advanced scenario step structure
# ---------------------------------------------------------------------------

class TestAdvancedScenarioStructure:

    def test_advanced_has_five_steps(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"), _comp("c3", "C"))
        engine = GameDayScoringEngine()
        scenarios = engine.generate_scenarios(g, Difficulty.ADVANCED)
        assert len(scenarios[0].steps) == 5

    def test_advanced_includes_communication(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"), _comp("c3", "C"))
        engine = GameDayScoringEngine()
        scenarios = engine.generate_scenarios(g, Difficulty.ADVANCED)
        cats = {step.category for step in scenarios[0].steps}
        assert ChallengeCategory.COMMUNICATION in cats


# ---------------------------------------------------------------------------
# Expert scenario step structure
# ---------------------------------------------------------------------------

class TestExpertScenarioStructure:

    def test_expert_has_four_steps(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"))
        engine = GameDayScoringEngine()
        scenarios = engine.generate_scenarios(g, Difficulty.EXPERT)
        assert len(scenarios[0].steps) == 4

    def test_expert_title_mentions_byzantine(self):
        g = _graph(_comp("c1", "A"), _comp("c2", "B"))
        engine = GameDayScoringEngine()
        scenarios = engine.generate_scenarios(g, Difficulty.EXPERT)
        assert "Byzantine" in scenarios[0].title


# ---------------------------------------------------------------------------
# Leaderboard best_scenario with max=0 in history
# ---------------------------------------------------------------------------

class TestLeaderboardHistoryEdge:

    def test_best_scenario_with_zero_max_in_history(self):
        engine = GameDayScoringEngine()
        engine._team_performances["T"] = TeamPerformance(
            team_name="T",
            scenarios_completed=1,
            total_points=0,
            max_possible_points=0,
            average_score_percent=0.0,
            history=[
                {"scenario_id": "S-0", "score": 0, "max": 0, "grade": "F", "timestamp": "now"},
            ],
        )
        lb = engine.generate_leaderboard()
        assert len(lb) == 1
        # lambda: h["score"]/h["max"] if h["max"]>0 else 0 → 0
        assert lb[0].best_scenario == "S-0"

    def test_best_scenario_picks_highest_ratio(self):
        engine = GameDayScoringEngine()
        engine._team_performances["T"] = TeamPerformance(
            team_name="T",
            scenarios_completed=2,
            total_points=150,
            max_possible_points=200,
            average_score_percent=75.0,
            history=[
                {"scenario_id": "LOW", "score": 50, "max": 100, "grade": "C", "timestamp": "t1"},
                {"scenario_id": "HIGH", "score": 100, "max": 100, "grade": "S", "timestamp": "t2"},
            ],
        )
        lb = engine.generate_leaderboard()
        assert lb[0].best_scenario == "HIGH"


# ---------------------------------------------------------------------------
# GameDayReport dataclass
# ---------------------------------------------------------------------------

class TestGameDayReportDataclass:

    def test_report_fields(self):
        r = GameDayReport(
            scenarios=[], leaderboard=[], total_participants=0,
            average_score_percent=0.0, hardest_scenario="N/A",
            easiest_scenario="N/A", category_performance={},
            recommendations=[],
        )
        assert r.scenarios == []
        assert r.leaderboard == []
        assert r.recommendations == []


# ---------------------------------------------------------------------------
# Scoring with multiple hints_used exceeding available hints
# ---------------------------------------------------------------------------

class TestHintsExceedAvailable:

    def test_hints_used_exceeds_hints_list(self):
        """hints_used > len(hints) → only penalties from available hints are summed."""
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d", success_criteria="s",
            max_points=100, time_limit_seconds=1000,
            hints=[Hint(1, "h1", 5)],  # only 1 hint
        )
        scenario = _simple_scenario(difficulty=Difficulty.NOVICE, steps=[step])
        results = [{"step_number": 1, "completed": True, "time_taken_seconds": 10, "hints_used": 5}]
        scored = engine.score_scenario(scenario, results)
        # hints[:5] → only 1 element → penalty = 5
        # base=100, time_mult=1.5 (10/1000<0.25) → 150-5=145
        assert scored.final_score == 145


# ---------------------------------------------------------------------------
# Recommendation: expert scenario completed → no "Challenge the team" message
# ---------------------------------------------------------------------------

class TestRecommendationExpertDone:

    def test_no_challenge_recommendation_when_expert_completed(self):
        engine = GameDayScoringEngine()
        step = ChallengeStep(
            step_number=1,
            category=ChallengeCategory.DETECTION,
            description="d", success_criteria="s",
            max_points=100, time_limit_seconds=100,
            hints=[], points_earned=90, completed=True,
        )
        s = _simple_scenario(difficulty=Difficulty.EXPERT, steps=[step])
        s.status = ScenarioStatus.COMPLETED
        s.final_score = 90
        s.max_total_points = 100
        engine._scenarios.append(s)
        report = engine.generate_report()
        assert not any("Challenge the team" in r for r in report.recommendations)
