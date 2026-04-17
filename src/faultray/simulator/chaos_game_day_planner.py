# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Chaos Game Day Planner -- plans and orchestrates chaos engineering game day exercises.

Generates structured game day plans with scenario generation, participant roles,
hypothesis-driven experiments, progressive difficulty, and comprehensive reporting.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Sequence

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GameDayType(str, Enum):
    """Type of game day exercise."""

    TABLETOP = "tabletop"
    CONTROLLED_INJECTION = "controlled_injection"
    FULL_SCALE_CHAOS = "full_scale_chaos"


class DifficultyLevel(str, Enum):
    """Progressive difficulty levels for game day exercises."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ParticipantRole(str, Enum):
    """Roles assigned to participants during a game day."""

    GAME_MASTER = "game_master"
    OPERATOR = "operator"
    OBSERVER = "observer"


class ScenarioPriority(str, Enum):
    """Risk-based priority for scenarios."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PhaseType(str, Enum):
    """Phases of a game day exercise."""

    PRE_GAME_BRIEFING = "pre_game_briefing"
    EXECUTION = "execution"
    POST_GAME_REVIEW = "post_game_review"


class FindingSeverity(str, Enum):
    """Severity of findings from a game day."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Participant:
    """A participant in a game day exercise."""

    name: str
    role: ParticipantRole
    team: str = ""
    contact: str = ""


@dataclass
class Hypothesis:
    """A hypothesis-driven experiment design element."""

    steady_state: str
    action: str
    observation: str
    validated: bool | None = None
    notes: str = ""


@dataclass
class RollbackPlan:
    """A rollback plan for an injection scenario."""

    description: str
    steps: list[str] = field(default_factory=list)
    estimated_time_minutes: int = 5
    automated: bool = False


@dataclass
class BlastRadius:
    """Estimated blast radius for a scenario."""

    affected_components: list[str] = field(default_factory=list)
    affected_percentage: float = 0.0
    max_allowed_percentage: float = 25.0
    within_safety_boundary: bool = True


@dataclass
class SuccessCriterion:
    """A success criterion for a scenario."""

    description: str
    metric: str = ""
    threshold: str = ""
    met: bool = False


@dataclass
class Scenario:
    """A chaos scenario to execute during a game day."""

    id: str
    name: str
    description: str
    target_components: list[str]
    priority: ScenarioPriority
    difficulty: DifficultyLevel
    hypothesis: Hypothesis
    rollback_plan: RollbackPlan
    blast_radius: BlastRadius
    success_criteria: list[SuccessCriterion] = field(default_factory=list)
    injection_type: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class ScheduleBlock:
    """A scheduled block within the game day timeline."""

    phase: PhaseType
    start_time: datetime
    end_time: datetime
    description: str = ""
    scenarios: list[str] = field(default_factory=list)


@dataclass
class Finding:
    """A finding from the game day exercise."""

    id: str
    title: str
    description: str
    severity: FindingSeverity
    affected_components: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class ActionItem:
    """An action item generated from findings."""

    id: str
    title: str
    description: str
    owner: str = ""
    due_date: str = ""
    priority: ScenarioPriority = ScenarioPriority.MEDIUM
    related_finding_id: str = ""


@dataclass
class GameDayPlan:
    """A complete game day plan."""

    id: str
    name: str
    game_day_type: GameDayType
    difficulty: DifficultyLevel
    description: str
    created_at: datetime
    scheduled_date: datetime
    participants: list[Participant] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)
    schedule: list[ScheduleBlock] = field(default_factory=list)
    compliance_notes: list[str] = field(default_factory=list)


@dataclass
class GameDayReport:
    """A report generated after completing a game day."""

    plan_id: str
    plan_name: str
    generated_at: datetime
    completed_scenarios: int = 0
    total_scenarios: int = 0
    findings: list[Finding] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    overall_score: float = 0.0
    summary: str = ""
    lessons_learned: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Difficulty configuration
# ---------------------------------------------------------------------------

_DIFFICULTY_CONFIG: dict[DifficultyLevel, dict] = {
    DifficultyLevel.BEGINNER: {
        "max_scenarios": 3,
        "max_targets_per_scenario": 1,
        "blast_radius_limit": 10.0,
        "execution_window_minutes": 60,
        "briefing_minutes": 30,
        "review_minutes": 30,
        "include_rollback": True,
        "allow_production": False,
    },
    DifficultyLevel.INTERMEDIATE: {
        "max_scenarios": 5,
        "max_targets_per_scenario": 2,
        "blast_radius_limit": 25.0,
        "execution_window_minutes": 120,
        "briefing_minutes": 45,
        "review_minutes": 45,
        "include_rollback": True,
        "allow_production": True,
    },
    DifficultyLevel.ADVANCED: {
        "max_scenarios": 10,
        "max_targets_per_scenario": 4,
        "blast_radius_limit": 50.0,
        "execution_window_minutes": 240,
        "briefing_minutes": 60,
        "review_minutes": 60,
        "include_rollback": True,
        "allow_production": True,
    },
}


# ---------------------------------------------------------------------------
# Injection type mapping
# ---------------------------------------------------------------------------

_COMPONENT_INJECTION_MAP: dict[ComponentType, list[str]] = {
    ComponentType.LOAD_BALANCER: ["health_check_failure", "connection_exhaustion"],
    ComponentType.WEB_SERVER: ["process_crash", "cpu_spike"],
    ComponentType.APP_SERVER: ["memory_leak", "latency_injection", "process_crash"],
    ComponentType.DATABASE: ["disk_full", "connection_pool_exhaustion", "replication_lag"],
    ComponentType.CACHE: ["eviction_storm", "cache_flush", "connection_failure"],
    ComponentType.QUEUE: ["message_backlog", "consumer_lag", "partition_loss"],
    ComponentType.STORAGE: ["io_latency", "disk_corruption", "capacity_exhaustion"],
    ComponentType.DNS: ["resolution_failure", "ttl_expiry", "propagation_delay"],
    ComponentType.EXTERNAL_API: ["timeout", "rate_limit_hit", "connection_refused"],
    ComponentType.CUSTOM: ["process_crash", "resource_exhaustion"],
    ComponentType.AI_AGENT: ["hallucination", "tool_call_failure", "context_overflow"],
    ComponentType.LLM_ENDPOINT: ["rate_limit_hit", "model_degradation", "timeout"],
    ComponentType.TOOL_SERVICE: ["tool_timeout", "invalid_input", "resource_exhaustion"],
    ComponentType.AGENT_ORCHESTRATOR: ["workflow_deadlock", "agent_timeout", "state_corruption"],
    ComponentType.AUTOMATION: ["trigger_failure", "execution_timeout", "resource_exhaustion"],
    ComponentType.SERVERLESS: ["cold_start_latency", "timeout", "memory_exhaustion"],
    ComponentType.SCHEDULED_JOB: ["job_skip", "execution_timeout", "resource_exhaustion"],
}

# ---------------------------------------------------------------------------
# Priority scoring weights
# ---------------------------------------------------------------------------

_PRIORITY_WEIGHTS = {
    "spof": 40,
    "high_dependents": 25,
    "no_failover": 15,
    "no_circuit_breaker": 10,
    "deep_chain": 10,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    """Generate a short unique identifier."""
    return uuid.uuid4().hex[:8]


def _is_spof(comp: Component, graph: InfraGraph) -> bool:
    """Return True if the component is a single point of failure."""
    if comp.replicas > 1:
        return False
    if comp.failover.enabled:
        return False
    dependents = graph.get_dependents(comp.id)
    return len(dependents) > 0


def _dependent_count(comp: Component, graph: InfraGraph) -> int:
    """Return the number of components that directly depend on *comp*."""
    return len(graph.get_dependents(comp.id))


def _has_circuit_breaker_on_edges(comp_id: str, graph: InfraGraph) -> bool:
    """Return True if any outgoing edge from *comp_id* has circuit breaker enabled."""
    deps = graph.get_dependencies(comp_id)
    for dep in deps:
        edge = graph.get_dependency_edge(comp_id, dep.id)
        if edge and edge.circuit_breaker.enabled:
            return True
    return False


def _has_incoming_circuit_breakers(comp_id: str, graph: InfraGraph) -> bool:
    """Return True if all incoming edges to *comp_id* have circuit breakers."""
    dependents = graph.get_dependents(comp_id)
    if not dependents:
        return False
    for dep in dependents:
        edge = graph.get_dependency_edge(dep.id, comp_id)
        if not edge or not edge.circuit_breaker.enabled:
            return False
    return True


def _dependency_depth(comp_id: str, graph: InfraGraph) -> int:
    """Return the longest dependency chain depth starting from *comp_id*."""
    visited: set[str] = set()

    def _dfs(cid: str) -> int:
        if cid in visited:
            return 0
        visited.add(cid)
        deps = graph.get_dependencies(cid)
        if not deps:
            return 1
        return 1 + max(_dfs(d.id) for d in deps)

    return _dfs(comp_id)


def _cascade_reach(comp_id: str, graph: InfraGraph) -> set[str]:
    """Return the set of all transitively affected component IDs."""
    return graph.get_all_affected(comp_id)


def _compute_risk_score(comp: Component, graph: InfraGraph) -> int:
    """Compute a risk score for a component (higher = riskier, higher priority)."""
    score = 0
    if _is_spof(comp, graph):
        score += _PRIORITY_WEIGHTS["spof"]
    dep_count = _dependent_count(comp, graph)
    if dep_count >= 3:
        score += _PRIORITY_WEIGHTS["high_dependents"]
    elif dep_count >= 1:
        score += _PRIORITY_WEIGHTS["high_dependents"] // 2
    if not comp.failover.enabled:
        score += _PRIORITY_WEIGHTS["no_failover"]
    if not _has_incoming_circuit_breakers(comp.id, graph):
        score += _PRIORITY_WEIGHTS["no_circuit_breaker"]
    depth = _dependency_depth(comp.id, graph)
    if depth >= 3:
        score += _PRIORITY_WEIGHTS["deep_chain"]
    return score


def _risk_score_to_priority(score: int) -> ScenarioPriority:
    """Map a numeric risk score to a priority level."""
    if score >= 70:
        return ScenarioPriority.CRITICAL
    if score >= 50:
        return ScenarioPriority.HIGH
    if score >= 25:
        return ScenarioPriority.MEDIUM
    return ScenarioPriority.LOW


def _select_injection_type(comp: Component) -> str:
    """Select the most relevant injection type for a component."""
    injections = _COMPONENT_INJECTION_MAP.get(comp.type, ["process_crash"])
    return injections[0]


def _build_hypothesis(comp: Component, injection_type: str) -> Hypothesis:
    """Build a hypothesis for a component injection scenario."""
    return Hypothesis(
        steady_state=f"Component '{comp.id}' is healthy and serving requests normally",
        action=f"Inject '{injection_type}' fault into component '{comp.id}'",
        observation=(
            f"System should detect failure of '{comp.id}' and recover "
            f"within acceptable thresholds"
        ),
    )


def _build_rollback(comp: Component, injection_type: str) -> RollbackPlan:
    """Build a rollback plan for a given injection."""
    return RollbackPlan(
        description=f"Rollback '{injection_type}' on component '{comp.id}'",
        steps=[
            f"Stop fault injection on '{comp.id}'",
            f"Verify '{comp.id}' returns to healthy state",
            "Validate dependent services are restored",
            "Confirm monitoring returns to baseline",
        ],
        estimated_time_minutes=5 if injection_type != "disk_full" else 15,
        automated=comp.autoscaling.enabled,
    )


def _build_blast_radius(
    comp: Component,
    graph: InfraGraph,
    total_components: int,
    max_allowed_pct: float,
) -> BlastRadius:
    """Compute the blast radius for injecting a fault on *comp*."""
    affected = _cascade_reach(comp.id, graph)
    affected_ids = sorted(affected)
    pct = (len(affected_ids) / total_components * 100.0) if total_components > 0 else 0.0
    return BlastRadius(
        affected_components=affected_ids,
        affected_percentage=round(pct, 1),
        max_allowed_percentage=max_allowed_pct,
        within_safety_boundary=pct <= max_allowed_pct,
    )


def _build_success_criteria(comp: Component, injection_type: str) -> list[SuccessCriterion]:
    """Build success criteria for a scenario."""
    criteria = [
        SuccessCriterion(
            description=f"Failure of '{comp.id}' is detected within monitoring SLA",
            metric="detection_time_seconds",
            threshold="< 60",
        ),
        SuccessCriterion(
            description=f"System recovers from '{injection_type}' automatically or manually",
            metric="recovery_time_minutes",
            threshold="< 15",
        ),
    ]
    if comp.failover.enabled:
        criteria.append(
            SuccessCriterion(
                description=f"Failover for '{comp.id}' activates successfully",
                metric="failover_success",
                threshold="true",
            )
        )
    return criteria


def _generate_scenario(
    comp: Component,
    graph: InfraGraph,
    difficulty: DifficultyLevel,
    total_components: int,
) -> Scenario:
    """Generate a single scenario for a target component."""
    config = _DIFFICULTY_CONFIG[difficulty]
    injection_type = _select_injection_type(comp)
    risk_score = _compute_risk_score(comp, graph)
    priority = _risk_score_to_priority(risk_score)

    return Scenario(
        id=f"scenario-{_uid()}",
        name=f"Inject {injection_type} on {comp.id}",
        description=(
            f"Test system resilience by injecting '{injection_type}' "
            f"fault on component '{comp.id}' ({comp.type.value})"
        ),
        target_components=[comp.id],
        priority=priority,
        difficulty=difficulty,
        hypothesis=_build_hypothesis(comp, injection_type),
        rollback_plan=_build_rollback(comp, injection_type),
        blast_radius=_build_blast_radius(
            comp, graph, total_components, config["blast_radius_limit"],
        ),
        success_criteria=_build_success_criteria(comp, injection_type),
        injection_type=injection_type,
        tags=[comp.type.value, injection_type],
    )


def _prioritize_components(
    components: Sequence[Component],
    graph: InfraGraph,
) -> list[tuple[Component, int]]:
    """Return components sorted by risk score descending."""
    scored = [(c, _compute_risk_score(c, graph)) for c in components]
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored


def _build_schedule(
    game_day_type: GameDayType,
    difficulty: DifficultyLevel,
    scenario_ids: list[str],
    start_time: datetime,
) -> list[ScheduleBlock]:
    """Build the game day schedule with briefing, execution windows, and review."""
    config = _DIFFICULTY_CONFIG[difficulty]
    briefing_min = config["briefing_minutes"]
    execution_min = config["execution_window_minutes"]
    review_min = config["review_minutes"]

    schedule: list[ScheduleBlock] = []

    # Pre-game briefing
    briefing_end = start_time + timedelta(minutes=briefing_min)
    schedule.append(
        ScheduleBlock(
            phase=PhaseType.PRE_GAME_BRIEFING,
            start_time=start_time,
            end_time=briefing_end,
            description="Team briefing: review scenarios, assign roles, confirm safety measures",
        )
    )

    # Execution window
    exec_start = briefing_end
    exec_end = exec_start + timedelta(minutes=execution_min)
    schedule.append(
        ScheduleBlock(
            phase=PhaseType.EXECUTION,
            start_time=exec_start,
            end_time=exec_end,
            description="Execute chaos scenarios with monitoring and rollback readiness",
            scenarios=scenario_ids,
        )
    )

    # Post-game review
    review_start = exec_end
    review_end = review_start + timedelta(minutes=review_min)
    schedule.append(
        ScheduleBlock(
            phase=PhaseType.POST_GAME_REVIEW,
            start_time=review_start,
            end_time=review_end,
            description="Review results, document findings, assign action items",
        )
    )

    return schedule


def _assign_default_participants(game_day_type: GameDayType) -> list[Participant]:
    """Assign default participant roles based on game day type."""
    participants = [
        Participant(name="Game Master", role=ParticipantRole.GAME_MASTER, team="SRE"),
    ]
    if game_day_type == GameDayType.TABLETOP:
        participants.extend([
            Participant(name="Operator 1", role=ParticipantRole.OPERATOR, team="Engineering"),
            Participant(name="Observer 1", role=ParticipantRole.OBSERVER, team="Management"),
        ])
    elif game_day_type == GameDayType.CONTROLLED_INJECTION:
        participants.extend([
            Participant(name="Operator 1", role=ParticipantRole.OPERATOR, team="SRE"),
            Participant(name="Operator 2", role=ParticipantRole.OPERATOR, team="Engineering"),
            Participant(name="Observer 1", role=ParticipantRole.OBSERVER, team="Management"),
        ])
    else:  # FULL_SCALE_CHAOS
        participants.extend([
            Participant(name="Operator 1", role=ParticipantRole.OPERATOR, team="SRE"),
            Participant(name="Operator 2", role=ParticipantRole.OPERATOR, team="Engineering"),
            Participant(name="Operator 3", role=ParticipantRole.OPERATOR, team="Platform"),
            Participant(name="Observer 1", role=ParticipantRole.OBSERVER, team="Management"),
            Participant(name="Observer 2", role=ParticipantRole.OBSERVER, team="Product"),
        ])
    return participants


def _build_compliance_notes(
    game_day_type: GameDayType,
    difficulty: DifficultyLevel,
) -> list[str]:
    """Generate compliance notes based on chaos engineering principles."""
    notes = [
        "Minimize blast radius: start with smallest scope and expand gradually",
        "Have rollback plans ready for every injection scenario",
    ]
    config = _DIFFICULTY_CONFIG[difficulty]
    if config["allow_production"]:
        notes.append(
            "Run in production: exercises should reflect real-world conditions"
        )
    else:
        notes.append(
            "Staging only: beginner exercises should not target production"
        )
    if game_day_type == GameDayType.FULL_SCALE_CHAOS:
        notes.append(
            "Coordinate with all stakeholders before full-scale chaos exercises"
        )
    notes.append("Document all findings and share with the broader organization")
    return notes


def _generate_finding(
    scenario: Scenario,
    validated: bool,
) -> Finding:
    """Generate a finding from a scenario result."""
    if validated:
        return Finding(
            id=f"finding-{_uid()}",
            title=f"Scenario passed: {scenario.name}",
            description=(
                f"Hypothesis validated for scenario '{scenario.name}'. "
                f"System handled '{scenario.injection_type}' on "
                f"{', '.join(scenario.target_components)} as expected."
            ),
            severity=FindingSeverity.INFO,
            affected_components=scenario.target_components,
            recommendation="Continue monitoring and re-test periodically",
        )

    severity_map = {
        ScenarioPriority.CRITICAL: FindingSeverity.CRITICAL,
        ScenarioPriority.HIGH: FindingSeverity.HIGH,
        ScenarioPriority.MEDIUM: FindingSeverity.MEDIUM,
        ScenarioPriority.LOW: FindingSeverity.LOW,
    }
    return Finding(
        id=f"finding-{_uid()}",
        title=f"Scenario failed: {scenario.name}",
        description=(
            f"Hypothesis NOT validated for scenario '{scenario.name}'. "
            f"System did not handle '{scenario.injection_type}' on "
            f"{', '.join(scenario.target_components)} within expected thresholds."
        ),
        severity=severity_map.get(scenario.priority, FindingSeverity.MEDIUM),
        affected_components=scenario.target_components,
        recommendation=(
            f"Improve resilience for {', '.join(scenario.target_components)}: "
            f"consider adding redundancy, circuit breakers, or failover"
        ),
    )


def _generate_action_item(finding: Finding) -> ActionItem:
    """Generate an action item from a finding."""
    priority_map = {
        FindingSeverity.CRITICAL: ScenarioPriority.CRITICAL,
        FindingSeverity.HIGH: ScenarioPriority.HIGH,
        FindingSeverity.MEDIUM: ScenarioPriority.MEDIUM,
        FindingSeverity.LOW: ScenarioPriority.LOW,
        FindingSeverity.INFO: ScenarioPriority.LOW,
    }
    return ActionItem(
        id=f"action-{_uid()}",
        title=f"Address: {finding.title}",
        description=finding.recommendation,
        priority=priority_map.get(finding.severity, ScenarioPriority.MEDIUM),
        related_finding_id=finding.id,
    )


def _compute_report_score(
    completed: int,
    total: int,
    findings: list[Finding],
) -> float:
    """Compute an overall game day score (0-100)."""
    if total == 0:
        return 0.0
    base = (completed / total) * 100.0

    # Penalize for high-severity findings
    penalty = 0.0
    for f in findings:
        if f.severity == FindingSeverity.CRITICAL:
            penalty += 20.0
        elif f.severity == FindingSeverity.HIGH:
            penalty += 10.0
        elif f.severity == FindingSeverity.MEDIUM:
            penalty += 5.0

    return max(0.0, min(100.0, base - penalty))


def _generate_summary(
    plan: GameDayPlan,
    completed: int,
    total: int,
    score: float,
    findings: list[Finding],
) -> str:
    """Generate a human-readable summary for the game day report."""
    critical_count = sum(1 for f in findings if f.severity == FindingSeverity.CRITICAL)
    high_count = sum(1 for f in findings if f.severity == FindingSeverity.HIGH)
    info_count = sum(1 for f in findings if f.severity == FindingSeverity.INFO)

    lines = [
        f"Game Day Report: {plan.name}",
        f"Type: {plan.game_day_type.value}",
        f"Difficulty: {plan.difficulty.value}",
        f"Scenarios: {completed}/{total} completed",
        f"Score: {score:.1f}/100",
    ]
    if critical_count:
        lines.append(f"Critical findings: {critical_count}")
    if high_count:
        lines.append(f"High findings: {high_count}")
    if info_count:
        lines.append(f"Passed scenarios (info): {info_count}")
    return "\n".join(lines)


def _generate_lessons_learned(findings: list[Finding]) -> list[str]:
    """Generate lessons learned from findings."""
    lessons: list[str] = []
    severity_counts: dict[str, int] = {}
    for f in findings:
        severity_counts[f.severity.value] = severity_counts.get(f.severity.value, 0) + 1

    if severity_counts.get("critical", 0) > 0:
        lessons.append(
            "Critical gaps identified in system resilience; "
            "immediate remediation required before next game day"
        )
    if severity_counts.get("high", 0) > 0:
        lessons.append(
            "High-severity issues found; prioritize remediation "
            "within the next sprint cycle"
        )
    if severity_counts.get("info", 0) > 0:
        count = severity_counts["info"]
        lessons.append(
            f"{count} scenario(s) passed successfully, "
            f"validating existing resilience measures"
        )
    if not lessons:
        lessons.append("No scenarios were evaluated in this game day")
    return lessons


# ---------------------------------------------------------------------------
# Main planner class
# ---------------------------------------------------------------------------


class ChaosGameDayPlanner:
    """Plans and orchestrates chaos engineering game day exercises.

    Analyzes an infrastructure graph to identify weak links, generates
    prioritized scenarios with hypothesis-driven experiments, and produces
    comprehensive game day plans with scheduling and role assignment.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # -- Plan creation ------------------------------------------------------

    def create_plan(
        self,
        name: str,
        game_day_type: GameDayType = GameDayType.CONTROLLED_INJECTION,
        difficulty: DifficultyLevel = DifficultyLevel.INTERMEDIATE,
        scheduled_date: datetime | None = None,
        participants: list[Participant] | None = None,
    ) -> GameDayPlan:
        """Create a comprehensive game day plan.

        Generates scenarios by analyzing the infrastructure graph, builds
        a schedule, assigns participants, and returns a complete plan.
        """
        now = datetime.now(timezone.utc)
        if scheduled_date is None:
            scheduled_date = now + timedelta(days=7)

        scenarios = self.generate_scenarios(game_day_type, difficulty)
        scenario_ids = [s.id for s in scenarios]
        schedule = _build_schedule(game_day_type, difficulty, scenario_ids, scheduled_date)

        if participants is None:
            participants = _assign_default_participants(game_day_type)

        return GameDayPlan(
            id=f"gd-{_uid()}",
            name=name,
            game_day_type=game_day_type,
            difficulty=difficulty,
            description=(
                f"Chaos game day exercise ({game_day_type.value}) "
                f"at {difficulty.value} difficulty targeting "
                f"{len(scenarios)} scenario(s)"
            ),
            created_at=now,
            scheduled_date=scheduled_date,
            participants=participants,
            scenarios=scenarios,
            schedule=schedule,
            compliance_notes=_build_compliance_notes(game_day_type, difficulty),
        )

    # -- Scenario generation ------------------------------------------------

    def generate_scenarios(
        self,
        game_day_type: GameDayType = GameDayType.CONTROLLED_INJECTION,
        difficulty: DifficultyLevel = DifficultyLevel.INTERMEDIATE,
    ) -> list[Scenario]:
        """Generate scenarios by analyzing infrastructure graph weaknesses.

        Components are prioritized by risk score and limited by difficulty
        settings.  Tabletop exercises produce fewer scenarios than full-scale
        chaos.
        """
        components = list(self._graph.components.values())
        if not components:
            return []

        config = _DIFFICULTY_CONFIG[difficulty]
        max_scenarios = config["max_scenarios"]

        # Tabletop exercises are more conservative
        if game_day_type == GameDayType.TABLETOP:
            max_scenarios = min(max_scenarios, 2)

        total = len(components)
        ranked = _prioritize_components(components, self._graph)

        scenarios: list[Scenario] = []
        for comp, _score in ranked[:max_scenarios]:
            scenario = _generate_scenario(comp, self._graph, difficulty, total)
            # Filter out scenarios exceeding safety boundaries at beginner
            if difficulty == DifficultyLevel.BEGINNER:
                if not scenario.blast_radius.within_safety_boundary:
                    continue
            scenarios.append(scenario)

        return scenarios

    # -- Scenario prioritization --------------------------------------------

    def prioritize_scenarios(
        self,
        scenarios: list[Scenario],
    ) -> list[Scenario]:
        """Return scenarios sorted by priority (critical first)."""
        priority_order = {
            ScenarioPriority.CRITICAL: 0,
            ScenarioPriority.HIGH: 1,
            ScenarioPriority.MEDIUM: 2,
            ScenarioPriority.LOW: 3,
        }
        return sorted(scenarios, key=lambda s: priority_order.get(s.priority, 99))

    # -- Blast radius estimation --------------------------------------------

    def estimate_blast_radius(
        self,
        component_id: str,
        max_allowed_pct: float = 25.0,
    ) -> BlastRadius:
        """Estimate the blast radius for a component failure."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return BlastRadius(within_safety_boundary=True)
        total = len(self._graph.components)
        return _build_blast_radius(comp, self._graph, total, max_allowed_pct)

    # -- Report generation --------------------------------------------------

    def generate_report(
        self,
        plan: GameDayPlan,
        scenario_results: dict[str, bool] | None = None,
    ) -> GameDayReport:
        """Generate a game day report from a plan and scenario results.

        *scenario_results* maps scenario IDs to pass/fail booleans.  If not
        supplied, scenarios are evaluated based on blast radius safety.
        """
        if scenario_results is None:
            scenario_results = {}
            for scenario in plan.scenarios:
                # Default: pass if within safety boundary
                scenario_results[scenario.id] = scenario.blast_radius.within_safety_boundary

        total = len(plan.scenarios)
        completed = 0
        findings: list[Finding] = []

        for scenario in plan.scenarios:
            passed = scenario_results.get(scenario.id, False)
            scenario.hypothesis.validated = passed
            completed += 1
            findings.append(_generate_finding(scenario, passed))

        action_items: list[ActionItem] = []
        for finding in findings:
            if finding.severity != FindingSeverity.INFO:
                action_items.append(_generate_action_item(finding))

        score = _compute_report_score(completed, total, findings)
        summary = _generate_summary(plan, completed, total, score, findings)
        lessons = _generate_lessons_learned(findings)

        return GameDayReport(
            plan_id=plan.id,
            plan_name=plan.name,
            generated_at=datetime.now(timezone.utc),
            completed_scenarios=completed,
            total_scenarios=total,
            findings=findings,
            action_items=action_items,
            overall_score=score,
            summary=summary,
            lessons_learned=lessons,
        )

    # -- Weakest links analysis ---------------------------------------------

    def identify_weakest_links(self, top_n: int = 5) -> list[tuple[str, int]]:
        """Identify the top-N weakest components by risk score.

        Returns a list of (component_id, risk_score) tuples sorted descending.
        """
        components = list(self._graph.components.values())
        ranked = _prioritize_components(components, self._graph)
        return [(c.id, score) for c, score in ranked[:top_n]]

    # -- Schedule building --------------------------------------------------

    def build_schedule(
        self,
        plan: GameDayPlan,
        start_time: datetime | None = None,
    ) -> list[ScheduleBlock]:
        """Build or rebuild the schedule for a plan."""
        if start_time is None:
            start_time = plan.scheduled_date
        scenario_ids = [s.id for s in plan.scenarios]
        return _build_schedule(
            plan.game_day_type, plan.difficulty, scenario_ids, start_time,
        )

    # -- Participant management ---------------------------------------------

    def assign_participants(
        self,
        plan: GameDayPlan,
        participants: list[Participant] | None = None,
    ) -> GameDayPlan:
        """Assign participants to the plan, or use defaults."""
        if participants is not None:
            plan.participants = participants
        else:
            plan.participants = _assign_default_participants(plan.game_day_type)
        return plan

    # -- Validation ---------------------------------------------------------

    def validate_plan(self, plan: GameDayPlan) -> list[str]:
        """Validate a game day plan and return a list of issues found."""
        issues: list[str] = []

        if not plan.scenarios:
            issues.append("Plan has no scenarios defined")
        if not plan.participants:
            issues.append("Plan has no participants assigned")

        gm_count = sum(
            1 for p in plan.participants if p.role == ParticipantRole.GAME_MASTER
        )
        if gm_count == 0:
            issues.append("No game master assigned")
        if gm_count > 1:
            issues.append("Multiple game masters assigned; exactly one is recommended")

        if not plan.schedule:
            issues.append("Plan has no schedule defined")

        for scenario in plan.scenarios:
            if not scenario.rollback_plan.steps:
                issues.append(
                    f"Scenario '{scenario.id}' has no rollback steps"
                )
            if not scenario.blast_radius.within_safety_boundary:
                issues.append(
                    f"Scenario '{scenario.id}' blast radius "
                    f"({scenario.blast_radius.affected_percentage}%) "
                    f"exceeds safety boundary "
                    f"({scenario.blast_radius.max_allowed_percentage}%)"
                )

        return issues

    # -- Risk heatmap -------------------------------------------------------

    def risk_heatmap(self) -> dict[str, dict]:
        """Generate a risk heatmap for all components.

        Returns a dict keyed by component ID with risk score, priority, and
        whether the component is a SPOF.
        """
        result: dict[str, dict] = {}
        for comp in self._graph.components.values():
            score = _compute_risk_score(comp, self._graph)
            result[comp.id] = {
                "risk_score": score,
                "priority": _risk_score_to_priority(score).value,
                "is_spof": _is_spof(comp, self._graph),
                "dependent_count": _dependent_count(comp, self._graph),
                "has_failover": comp.failover.enabled,
                "has_circuit_breaker": _has_incoming_circuit_breakers(
                    comp.id, self._graph,
                ),
            }
        return result
