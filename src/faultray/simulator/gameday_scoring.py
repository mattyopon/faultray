"""SRE Game Day scoring engine — measure team resilience response.

Provides scoring framework for chaos engineering game days,
with difficulty levels, time-based scoring, hint system,
and performance tracking for SRE team improvement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone

from faultray.model.graph import InfraGraph


class Difficulty(str, Enum):
    NOVICE = "novice"           # Single component failure, obvious symptoms
    INTERMEDIATE = "intermediate"  # Multi-component, some investigation needed
    ADVANCED = "advanced"       # Cascade failures, subtle symptoms
    EXPERT = "expert"           # Complex scenarios, misleading symptoms


class ChallengeCategory(str, Enum):
    DETECTION = "detection"           # Can you find the problem?
    DIAGNOSIS = "diagnosis"           # Can you identify root cause?
    MITIGATION = "mitigation"         # Can you stop the bleeding?
    RECOVERY = "recovery"             # Can you restore service?
    PREVENTION = "prevention"         # Can you prevent recurrence?
    COMMUNICATION = "communication"   # Can you coordinate response?


class ScenarioStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


@dataclass
class Hint:
    """A hint for a challenge step."""
    hint_number: int
    text: str
    penalty_points: int  # Points deducted for using this hint


@dataclass
class ChallengeStep:
    """A single step in a game day challenge."""
    step_number: int
    category: ChallengeCategory
    description: str
    success_criteria: str
    max_points: int
    time_limit_seconds: int
    hints: list[Hint]
    hints_used: int = 0
    points_earned: int = 0
    completed: bool = False
    time_taken_seconds: int = 0


@dataclass
class GameDayScenario:
    """A complete game day scenario with challenge steps."""
    scenario_id: str
    title: str
    description: str
    difficulty: Difficulty
    steps: list[ChallengeStep]
    max_total_points: int
    time_limit_minutes: int
    status: ScenarioStatus = ScenarioStatus.NOT_STARTED
    start_time: str | None = None
    end_time: str | None = None
    final_score: int = 0
    grade: str = ""
    feedback: list[str] = field(default_factory=list)


@dataclass
class TeamPerformance:
    """Track a team's performance across game days."""
    team_name: str
    scenarios_completed: int = 0
    total_points: int = 0
    max_possible_points: int = 0
    average_score_percent: float = 0.0
    average_time_seconds: float = 0.0
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    improvement_trend: str = "new"  # "improving", "stable", "declining", "new"
    history: list[dict] = field(default_factory=list)


@dataclass
class LeaderboardEntry:
    """A single entry in the leaderboard."""
    rank: int
    team_name: str
    total_score: int
    scenarios_completed: int
    average_percent: float
    best_scenario: str
    badge: str  # "gold", "silver", "bronze", "participant"


@dataclass
class GameDayReport:
    """Full game day report."""
    scenarios: list[GameDayScenario]
    leaderboard: list[LeaderboardEntry]
    total_participants: int
    average_score_percent: float
    hardest_scenario: str
    easiest_scenario: str
    category_performance: dict[str, float]  # category -> avg score %
    recommendations: list[str]


class GameDayScoringEngine:
    """Score and manage SRE game day exercises."""

    # Difficulty multipliers
    _DIFFICULTY_MULTIPLIER: dict[Difficulty, float] = {
        Difficulty.NOVICE: 1.0,
        Difficulty.INTERMEDIATE: 1.5,
        Difficulty.ADVANCED: 2.0,
        Difficulty.EXPERT: 3.0,
    }

    # Time bonus thresholds (% of time limit used -> bonus multiplier)
    _TIME_BONUSES = [
        (0.25, 1.5),   # Under 25% time: 50% bonus
        (0.50, 1.25),  # Under 50% time: 25% bonus
        (0.75, 1.1),   # Under 75% time: 10% bonus
        (1.0, 1.0),    # At or over time: no bonus
    ]

    # Grade thresholds
    _GRADES = [
        (95, "S", "Exceptional — SRE Master"),
        (85, "A", "Excellent — Production Ready"),
        (75, "B", "Good — Solid Foundation"),
        (60, "C", "Adequate — Needs Practice"),
        (40, "D", "Below Average — Training Required"),
        (0, "F", "Failing — Fundamental Gaps"),
    ]

    def __init__(self) -> None:
        self._scenarios: list[GameDayScenario] = []
        self._team_performances: dict[str, TeamPerformance] = {}

    def generate_scenarios(self, graph: InfraGraph, difficulty: Difficulty | None = None) -> list[GameDayScenario]:
        """Generate game day scenarios based on infrastructure topology."""
        scenarios = []

        if difficulty is None or difficulty == Difficulty.NOVICE:
            scenarios.extend(self._generate_novice_scenarios(graph))
        if difficulty is None or difficulty == Difficulty.INTERMEDIATE:
            scenarios.extend(self._generate_intermediate_scenarios(graph))
        if difficulty is None or difficulty == Difficulty.ADVANCED:
            scenarios.extend(self._generate_advanced_scenarios(graph))
        if difficulty is None or difficulty == Difficulty.EXPERT:
            scenarios.extend(self._generate_expert_scenarios(graph))

        self._scenarios.extend(scenarios)
        return scenarios

    def score_scenario(self, scenario: GameDayScenario, step_results: list[dict]) -> GameDayScenario:
        """Score a completed scenario based on step results.

        step_results: list of {"step_number": int, "completed": bool, "time_taken_seconds": int, "hints_used": int}
        """
        total_earned = 0
        total_possible = 0

        for result in step_results:
            step_num = result.get("step_number", 0)
            matching_steps = [s for s in scenario.steps if s.step_number == step_num]
            if not matching_steps:
                continue
            step = matching_steps[0]

            step.completed = result.get("completed", False)
            step.time_taken_seconds = result.get("time_taken_seconds", 0)
            step.hints_used = result.get("hints_used", 0)

            if step.completed:
                base_points = step.max_points

                # Apply time bonus
                time_ratio = step.time_taken_seconds / step.time_limit_seconds if step.time_limit_seconds > 0 else 1.0
                time_mult = 1.0
                for threshold, mult in self._TIME_BONUSES:
                    if time_ratio <= threshold:
                        time_mult = mult
                        break

                # Apply hint penalty
                hint_penalty = sum(
                    h.penalty_points for h in step.hints[:step.hints_used]
                )

                # Calculate final step score
                earned = max(0, int(base_points * time_mult - hint_penalty))
                step.points_earned = earned
                total_earned += earned
            else:
                step.points_earned = 0

            total_possible += step.max_points

        # Apply difficulty multiplier
        diff_mult = self._DIFFICULTY_MULTIPLIER.get(scenario.difficulty, 1.0)
        scenario.final_score = int(total_earned * diff_mult)
        scenario.max_total_points = int(total_possible * diff_mult)

        # Calculate grade
        pct = (scenario.final_score / scenario.max_total_points * 100) if scenario.max_total_points > 0 else 0
        scenario.grade = self._calculate_grade(pct)

        # Generate feedback
        scenario.feedback = self._generate_feedback(scenario)
        scenario.status = ScenarioStatus.COMPLETED
        scenario.end_time = datetime.now(timezone.utc).isoformat()

        return scenario

    def record_team_performance(self, team_name: str, scenario: GameDayScenario) -> TeamPerformance:
        """Record a team's performance on a scenario."""
        if team_name not in self._team_performances:
            self._team_performances[team_name] = TeamPerformance(team_name=team_name)

        perf = self._team_performances[team_name]
        perf.scenarios_completed += 1
        perf.total_points += scenario.final_score
        perf.max_possible_points += scenario.max_total_points

        if perf.max_possible_points > 0:
            perf.average_score_percent = round(
                perf.total_points / perf.max_possible_points * 100, 1
            )

        # Track time
        total_time = sum(s.time_taken_seconds for s in scenario.steps)
        if perf.scenarios_completed > 0:
            prev_total = perf.average_time_seconds * (perf.scenarios_completed - 1)
            perf.average_time_seconds = round(
                (prev_total + total_time) / perf.scenarios_completed, 1
            )

        # Record history
        perf.history.append({
            "scenario_id": scenario.scenario_id,
            "score": scenario.final_score,
            "max": scenario.max_total_points,
            "grade": scenario.grade,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Update trend
        if len(perf.history) >= 3:
            recent = [h["score"] / h["max"] * 100 if h["max"] > 0 else 0 for h in perf.history[-3:]]
            if all(recent[i] <= recent[i+1] for i in range(len(recent)-1)):
                perf.improvement_trend = "improving"
            elif all(recent[i] >= recent[i+1] for i in range(len(recent)-1)):
                perf.improvement_trend = "declining"
            else:
                perf.improvement_trend = "stable"

        # Analyze strengths/weaknesses
        perf.strengths, perf.weaknesses = self._analyze_team_skills(scenario)

        return perf

    def generate_leaderboard(self) -> list[LeaderboardEntry]:
        """Generate a ranked leaderboard from all team performances."""
        entries = []
        for name, perf in self._team_performances.items():
            best = ""
            if perf.history:
                best_entry = max(perf.history, key=lambda h: h["score"] / h["max"] if h["max"] > 0 else 0)
                best = best_entry.get("scenario_id", "")

            badge = self._calculate_badge(perf.average_score_percent)

            entries.append(LeaderboardEntry(
                rank=0,
                team_name=name,
                total_score=perf.total_points,
                scenarios_completed=perf.scenarios_completed,
                average_percent=perf.average_score_percent,
                best_scenario=best,
                badge=badge,
            ))

        # Sort by total score descending
        entries.sort(key=lambda e: e.total_score, reverse=True)
        for i, entry in enumerate(entries):
            entry.rank = i + 1

        return entries

    def generate_report(self) -> GameDayReport:
        """Generate a full game day report."""
        completed = [s for s in self._scenarios if s.status == ScenarioStatus.COMPLETED]
        leaderboard = self.generate_leaderboard()

        # Average score
        if completed:
            avg_pct = sum(
                s.final_score / s.max_total_points * 100 if s.max_total_points > 0 else 0
                for s in completed
            ) / len(completed)
        else:
            avg_pct = 0.0

        # Hardest/easiest
        if completed:
            hardest = min(completed, key=lambda s: s.final_score / s.max_total_points if s.max_total_points > 0 else 1)
            easiest = max(completed, key=lambda s: s.final_score / s.max_total_points if s.max_total_points > 0 else 0)
            hardest_name = hardest.title
            easiest_name = easiest.title
        else:
            hardest_name = "N/A"
            easiest_name = "N/A"

        # Category performance
        cat_perf = self._calculate_category_performance(completed)

        recommendations = self._generate_report_recommendations(completed, cat_perf)

        return GameDayReport(
            scenarios=self._scenarios,
            leaderboard=leaderboard,
            total_participants=len(self._team_performances),
            average_score_percent=round(avg_pct, 1),
            hardest_scenario=hardest_name,
            easiest_scenario=easiest_name,
            category_performance=cat_perf,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Scenario generation
    # ------------------------------------------------------------------

    def _generate_novice_scenarios(self, graph: InfraGraph) -> list[GameDayScenario]:
        scenarios = []
        comps = list(graph.components.values())
        if not comps:
            return scenarios

        # Scenario: Single component DOWN
        target = comps[0]
        scenarios.append(GameDayScenario(
            scenario_id="NOV-001",
            title=f"Single Component Failure: {target.name}",
            description=f"{target.name} has gone DOWN. Detect, diagnose, and recover.",
            difficulty=Difficulty.NOVICE,
            steps=[
                ChallengeStep(
                    step_number=1,
                    category=ChallengeCategory.DETECTION,
                    description=f"Identify that {target.name} is down",
                    success_criteria="Correctly identify the failed component",
                    max_points=20,
                    time_limit_seconds=120,
                    hints=[
                        Hint(1, "Check the health status of each component", 5),
                        Hint(2, f"Look at {target.type.value} components", 10),
                    ],
                ),
                ChallengeStep(
                    step_number=2,
                    category=ChallengeCategory.DIAGNOSIS,
                    description="Identify the root cause",
                    success_criteria="Explain why the component failed",
                    max_points=30,
                    time_limit_seconds=180,
                    hints=[
                        Hint(1, "Check CPU, memory, and disk metrics", 5),
                        Hint(2, "Review recent changes and deployments", 10),
                    ],
                ),
                ChallengeStep(
                    step_number=3,
                    category=ChallengeCategory.RECOVERY,
                    description=f"Restore {target.name} to healthy state",
                    success_criteria="Component returns to HEALTHY status",
                    max_points=50,
                    time_limit_seconds=300,
                    hints=[
                        Hint(1, "Try restarting the component", 10),
                        Hint(2, "Check if failover is available", 15),
                    ],
                ),
            ],
            max_total_points=100,
            time_limit_minutes=10,
        ))

        return scenarios

    def _generate_intermediate_scenarios(self, graph: InfraGraph) -> list[GameDayScenario]:
        scenarios = []
        comps = list(graph.components.values())
        if len(comps) < 2:
            return scenarios

        scenarios.append(GameDayScenario(
            scenario_id="INT-001",
            title="Cascading Failure Drill",
            description="A dependency failure is causing cascading effects. Find and fix the root cause.",
            difficulty=Difficulty.INTERMEDIATE,
            steps=[
                ChallengeStep(
                    step_number=1,
                    category=ChallengeCategory.DETECTION,
                    description="Identify all affected components",
                    success_criteria="List all components experiencing issues",
                    max_points=25,
                    time_limit_seconds=180,
                    hints=[
                        Hint(1, "Check the dependency graph for connected components", 5),
                    ],
                ),
                ChallengeStep(
                    step_number=2,
                    category=ChallengeCategory.DIAGNOSIS,
                    description="Find the root cause of the cascade",
                    success_criteria="Identify the original failing component",
                    max_points=35,
                    time_limit_seconds=300,
                    hints=[
                        Hint(1, "The root cause is usually upstream in the dependency chain", 10),
                        Hint(2, "Look for the component with the earliest failure timestamp", 15),
                    ],
                ),
                ChallengeStep(
                    step_number=3,
                    category=ChallengeCategory.MITIGATION,
                    description="Stop the bleeding — prevent further cascade",
                    success_criteria="Isolate the failing component",
                    max_points=40,
                    time_limit_seconds=240,
                    hints=[
                        Hint(1, "Consider enabling circuit breakers", 10),
                    ],
                ),
                ChallengeStep(
                    step_number=4,
                    category=ChallengeCategory.PREVENTION,
                    description="Implement measures to prevent recurrence",
                    success_criteria="Add failover, circuit breakers, or other resilience measures",
                    max_points=50,
                    time_limit_seconds=600,
                    hints=[
                        Hint(1, "Review the blast radius and add isolation", 10),
                    ],
                ),
            ],
            max_total_points=150,
            time_limit_minutes=20,
        ))

        return scenarios

    def _generate_advanced_scenarios(self, graph: InfraGraph) -> list[GameDayScenario]:
        scenarios = []
        comps = list(graph.components.values())
        if len(comps) < 3:
            return scenarios

        scenarios.append(GameDayScenario(
            scenario_id="ADV-001",
            title="Multi-Region Failure Simulation",
            description="A regional outage has taken down multiple components. Coordinate the response.",
            difficulty=Difficulty.ADVANCED,
            steps=[
                ChallengeStep(
                    step_number=1,
                    category=ChallengeCategory.DETECTION,
                    description="Assess the blast radius of the regional outage",
                    success_criteria="Correctly map all affected services and users",
                    max_points=30,
                    time_limit_seconds=300,
                    hints=[Hint(1, "Group components by region/zone tags", 10)],
                ),
                ChallengeStep(
                    step_number=2,
                    category=ChallengeCategory.COMMUNICATION,
                    description="Draft an incident communication plan",
                    success_criteria="Status page update + stakeholder notification",
                    max_points=25,
                    time_limit_seconds=180,
                    hints=[Hint(1, "Use the SEV classification to determine communication scope", 5)],
                ),
                ChallengeStep(
                    step_number=3,
                    category=ChallengeCategory.MITIGATION,
                    description="Failover traffic to healthy region",
                    success_criteria="Traffic successfully routed to standby region",
                    max_points=45,
                    time_limit_seconds=600,
                    hints=[
                        Hint(1, "Check DNS failover configuration", 10),
                        Hint(2, "Verify standby region has sufficient capacity", 15),
                    ],
                ),
                ChallengeStep(
                    step_number=4,
                    category=ChallengeCategory.RECOVERY,
                    description="Restore the failed region and rebalance",
                    success_criteria="Both regions operational with balanced traffic",
                    max_points=50,
                    time_limit_seconds=900,
                    hints=[Hint(1, "Gradually shift traffic back — don't thundering-herd", 15)],
                ),
                ChallengeStep(
                    step_number=5,
                    category=ChallengeCategory.PREVENTION,
                    description="Write a postmortem and implement preventive measures",
                    success_criteria="Actionable postmortem with timeline and action items",
                    max_points=50,
                    time_limit_seconds=600,
                    hints=[Hint(1, "Use the 5 Whys technique", 10)],
                ),
            ],
            max_total_points=200,
            time_limit_minutes=45,
        ))

        return scenarios

    def _generate_expert_scenarios(self, graph: InfraGraph) -> list[GameDayScenario]:
        scenarios = []
        comps = list(graph.components.values())
        if len(comps) < 2:
            return scenarios

        scenarios.append(GameDayScenario(
            scenario_id="EXP-001",
            title="Byzantine Failure with Misleading Metrics",
            description="A subtle data corruption issue is causing intermittent failures. Metrics are misleading — the real problem is hidden.",
            difficulty=Difficulty.EXPERT,
            steps=[
                ChallengeStep(
                    step_number=1,
                    category=ChallengeCategory.DETECTION,
                    description="Notice the anomalous behavior despite green dashboards",
                    success_criteria="Identify that metrics are not reflecting reality",
                    max_points=40,
                    time_limit_seconds=600,
                    hints=[
                        Hint(1, "Compare end-user error reports with internal metrics", 15),
                        Hint(2, "Check for split-brain or inconsistent state", 20),
                    ],
                ),
                ChallengeStep(
                    step_number=2,
                    category=ChallengeCategory.DIAGNOSIS,
                    description="Identify the Byzantine component",
                    success_criteria="Find the component producing inconsistent results",
                    max_points=60,
                    time_limit_seconds=900,
                    hints=[
                        Hint(1, "Byzantine failures produce different outputs for different observers", 20),
                    ],
                ),
                ChallengeStep(
                    step_number=3,
                    category=ChallengeCategory.MITIGATION,
                    description="Quarantine the Byzantine component without data loss",
                    success_criteria="Isolate component while preserving in-flight data",
                    max_points=50,
                    time_limit_seconds=600,
                    hints=[Hint(1, "Drain connections before quarantine", 15)],
                ),
                ChallengeStep(
                    step_number=4,
                    category=ChallengeCategory.RECOVERY,
                    description="Verify data integrity and restore service",
                    success_criteria="All data verified, service restored with correct behavior",
                    max_points=50,
                    time_limit_seconds=900,
                    hints=[Hint(1, "Compare checksums across replicas", 15)],
                ),
            ],
            max_total_points=200,
            time_limit_minutes=50,
        ))

        return scenarios

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _calculate_grade(self, percent: float) -> str:
        for threshold, grade, _ in self._GRADES:
            if percent >= threshold:
                return grade
        return "F"

    @staticmethod
    def _calculate_badge(avg_percent: float) -> str:
        if avg_percent >= 90:
            return "gold"
        elif avg_percent >= 75:
            return "silver"
        elif avg_percent >= 50:
            return "bronze"
        else:
            return "participant"

    def _generate_feedback(self, scenario: GameDayScenario) -> list[str]:
        feedback = []
        for step in scenario.steps:
            if not step.completed:
                feedback.append(f"Step {step.step_number} ({step.category.value}): Not completed — practice {step.category.value} skills")
            elif step.hints_used > 0:
                feedback.append(f"Step {step.step_number} ({step.category.value}): Completed with {step.hints_used} hint(s) — try without hints next time")
            elif step.time_taken_seconds > step.time_limit_seconds * 0.75:
                feedback.append(f"Step {step.step_number} ({step.category.value}): Completed but close to time limit — improve speed")
            else:
                feedback.append(f"Step {step.step_number} ({step.category.value}): Excellent performance!")
        return feedback

    def _analyze_team_skills(self, scenario: GameDayScenario) -> tuple[list[str], list[str]]:
        strengths = []
        weaknesses = []
        cat_scores: dict[str, list[float]] = {}

        for step in scenario.steps:
            cat = step.category.value
            cat_scores.setdefault(cat, [])
            pct = step.points_earned / step.max_points * 100 if step.max_points > 0 else 0
            cat_scores[cat].append(pct)

        for cat, scores in cat_scores.items():
            avg = sum(scores) / len(scores) if scores else 0
            if avg >= 80:
                strengths.append(cat)
            elif avg < 50:
                weaknesses.append(cat)

        return strengths, weaknesses

    def _calculate_category_performance(self, scenarios: list[GameDayScenario]) -> dict[str, float]:
        cat_scores: dict[str, list[float]] = {}
        for scenario in scenarios:
            for step in scenario.steps:
                cat = step.category.value
                cat_scores.setdefault(cat, [])
                pct = step.points_earned / step.max_points * 100 if step.max_points > 0 else 0
                cat_scores[cat].append(pct)

        return {
            cat: round(sum(scores) / len(scores), 1) if scores else 0.0
            for cat, scores in cat_scores.items()
        }

    def _generate_report_recommendations(
        self,
        scenarios: list[GameDayScenario],
        cat_perf: dict[str, float],
    ) -> list[str]:
        recs = []

        # Find weak categories
        weak = [(cat, score) for cat, score in cat_perf.items() if score < 60]
        for cat, score in sorted(weak, key=lambda x: x[1]):
            recs.append(f"Focus training on {cat} — average score {score:.0f}%")

        # Check if expert scenarios attempted
        expert_done = any(s.difficulty == Difficulty.EXPERT and s.status == ScenarioStatus.COMPLETED for s in scenarios)
        if not expert_done and scenarios:
            recs.append("Challenge the team with Expert-level scenarios for deeper learning")

        if not recs:
            recs.append("Great performance across all categories! Consider increasing difficulty.")

        return recs[:5]
