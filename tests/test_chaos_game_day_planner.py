"""Tests for chaos_game_day_planner module -- Chaos Game Day Planner."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.chaos_game_day_planner import (
    ActionItem,
    BlastRadius,
    ChaosGameDayPlanner,
    DifficultyLevel,
    Finding,
    FindingSeverity,
    GameDayPlan,
    GameDayReport,
    GameDayType,
    Hypothesis,
    Participant,
    ParticipantRole,
    PhaseType,
    RollbackPlan,
    Scenario,
    ScenarioPriority,
    ScheduleBlock,
    SuccessCriterion,
    _build_blast_radius,
    _build_compliance_notes,
    _build_hypothesis,
    _build_rollback,
    _build_schedule,
    _build_success_criteria,
    _cascade_reach,
    _compute_report_score,
    _compute_risk_score,
    _dependency_depth,
    _dependent_count,
    _generate_action_item,
    _generate_finding,
    _generate_lessons_learned,
    _generate_scenario,
    _generate_summary,
    _has_circuit_breaker_on_edges,
    _has_incoming_circuit_breakers,
    _is_spof,
    _prioritize_components,
    _risk_score_to_priority,
    _select_injection_type,
    _uid,
    _assign_default_participants,
    _COMPONENT_INJECTION_MAP,
    _DIFFICULTY_CONFIG,
    _PRIORITY_WEIGHTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "c1",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    *,
    failover: bool = False,
    autoscaling: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=cid, type=ctype, replicas=replicas, health=health)
    if failover:
        c.failover.enabled = True
    if autoscaling:
        c.autoscaling.enabled = True
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# Test: Data class instantiation
# ---------------------------------------------------------------------------


class TestDataClasses:
    """Verify all data classes instantiate correctly."""

    def test_participant_defaults(self) -> None:
        p = Participant(name="Alice", role=ParticipantRole.GAME_MASTER)
        assert p.name == "Alice"
        assert p.role == ParticipantRole.GAME_MASTER
        assert p.team == ""
        assert p.contact == ""

    def test_hypothesis_defaults(self) -> None:
        h = Hypothesis(
            steady_state="System is healthy",
            action="Kill process",
            observation="System recovers",
        )
        assert h.validated is None
        assert h.notes == ""

    def test_rollback_plan_defaults(self) -> None:
        r = RollbackPlan(description="Restart service")
        assert r.steps == []
        assert r.estimated_time_minutes == 5
        assert r.automated is False

    def test_blast_radius_defaults(self) -> None:
        b = BlastRadius()
        assert b.affected_components == []
        assert b.affected_percentage == 0.0
        assert b.max_allowed_percentage == 25.0
        assert b.within_safety_boundary is True

    def test_success_criterion_defaults(self) -> None:
        s = SuccessCriterion(description="Recovers in < 5 min")
        assert s.met is False
        assert s.metric == ""
        assert s.threshold == ""

    def test_finding_defaults(self) -> None:
        f = Finding(
            id="f1", title="Test", description="A finding",
            severity=FindingSeverity.HIGH,
        )
        assert f.affected_components == []
        assert f.recommendation == ""

    def test_action_item_defaults(self) -> None:
        a = ActionItem(id="a1", title="Fix", description="Fix it")
        assert a.owner == ""
        assert a.priority == ScenarioPriority.MEDIUM
        assert a.related_finding_id == ""

    def test_schedule_block_defaults(self) -> None:
        now = datetime.now(timezone.utc)
        sb = ScheduleBlock(
            phase=PhaseType.EXECUTION,
            start_time=now,
            end_time=now + timedelta(hours=1),
        )
        assert sb.description == ""
        assert sb.scenarios == []


# ---------------------------------------------------------------------------
# Test: Enum values
# ---------------------------------------------------------------------------


class TestEnums:
    """Verify enum values match expected strings."""

    def test_game_day_types(self) -> None:
        assert GameDayType.TABLETOP.value == "tabletop"
        assert GameDayType.CONTROLLED_INJECTION.value == "controlled_injection"
        assert GameDayType.FULL_SCALE_CHAOS.value == "full_scale_chaos"

    def test_difficulty_levels(self) -> None:
        assert DifficultyLevel.BEGINNER.value == "beginner"
        assert DifficultyLevel.INTERMEDIATE.value == "intermediate"
        assert DifficultyLevel.ADVANCED.value == "advanced"

    def test_participant_roles(self) -> None:
        assert ParticipantRole.GAME_MASTER.value == "game_master"
        assert ParticipantRole.OPERATOR.value == "operator"
        assert ParticipantRole.OBSERVER.value == "observer"

    def test_scenario_priority(self) -> None:
        assert ScenarioPriority.CRITICAL.value == "critical"
        assert ScenarioPriority.LOW.value == "low"

    def test_phase_types(self) -> None:
        assert PhaseType.PRE_GAME_BRIEFING.value == "pre_game_briefing"
        assert PhaseType.EXECUTION.value == "execution"
        assert PhaseType.POST_GAME_REVIEW.value == "post_game_review"

    def test_finding_severity(self) -> None:
        assert FindingSeverity.CRITICAL.value == "critical"
        assert FindingSeverity.INFO.value == "info"


# ---------------------------------------------------------------------------
# Test: Internal helpers
# ---------------------------------------------------------------------------


class TestUid:
    """Test unique ID generation."""

    def test_uid_length(self) -> None:
        uid = _uid()
        assert len(uid) == 8

    def test_uid_uniqueness(self) -> None:
        ids = {_uid() for _ in range(100)}
        assert len(ids) == 100


class TestIsSpof:
    """Test single-point-of-failure detection."""

    def test_single_replica_with_dependents_is_spof(self) -> None:
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        assert _is_spof(b, g) is True

    def test_multi_replica_not_spof(self) -> None:
        a = _comp("a1")
        b = _comp("b1", replicas=2)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        assert _is_spof(b, g) is False

    def test_failover_not_spof(self) -> None:
        a = _comp("a1")
        b = _comp("b1", failover=True)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        assert _is_spof(b, g) is False

    def test_no_dependents_not_spof(self) -> None:
        a = _comp("a1")
        g = _graph(a)
        assert _is_spof(a, g) is False


class TestDependentCount:
    """Test dependent count helper."""

    def test_no_dependents(self) -> None:
        g = _graph(_comp("a1"))
        assert _dependent_count(_comp("a1"), g) == 0

    def test_multiple_dependents(self) -> None:
        a, b, c = _comp("a1"), _comp("b1"), _comp("c1")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a1", target_id="c1"))
        g.add_dependency(Dependency(source_id="b1", target_id="c1"))
        assert _dependent_count(c, g) == 2


class TestCircuitBreakers:
    """Test circuit breaker detection helpers."""

    def test_no_circuit_breaker_on_edges(self) -> None:
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        assert _has_circuit_breaker_on_edges("a1", g) is False

    def test_circuit_breaker_on_edge(self) -> None:
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        dep = Dependency(source_id="a1", target_id="b1")
        dep.circuit_breaker.enabled = True
        g.add_dependency(dep)
        assert _has_circuit_breaker_on_edges("a1", g) is True

    def test_incoming_circuit_breakers_all_covered(self) -> None:
        a, b, c = _comp("a1"), _comp("b1"), _comp("c1")
        g = _graph(a, b, c)
        dep1 = Dependency(source_id="a1", target_id="c1")
        dep1.circuit_breaker.enabled = True
        dep2 = Dependency(source_id="b1", target_id="c1")
        dep2.circuit_breaker.enabled = True
        g.add_dependency(dep1)
        g.add_dependency(dep2)
        assert _has_incoming_circuit_breakers("c1", g) is True

    def test_incoming_circuit_breakers_partial(self) -> None:
        a, b, c = _comp("a1"), _comp("b1"), _comp("c1")
        g = _graph(a, b, c)
        dep1 = Dependency(source_id="a1", target_id="c1")
        dep1.circuit_breaker.enabled = True
        dep2 = Dependency(source_id="b1", target_id="c1")
        g.add_dependency(dep1)
        g.add_dependency(dep2)
        assert _has_incoming_circuit_breakers("c1", g) is False

    def test_incoming_circuit_breakers_no_dependents(self) -> None:
        g = _graph(_comp("a1"))
        assert _has_incoming_circuit_breakers("a1", g) is False


class TestDependencyDepth:
    """Test dependency chain depth calculation."""

    def test_single_node_depth(self) -> None:
        g = _graph(_comp("a1"))
        assert _dependency_depth("a1", g) == 1

    def test_chain_depth(self) -> None:
        a, b, c = _comp("a1"), _comp("b1"), _comp("c1")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        g.add_dependency(Dependency(source_id="b1", target_id="c1"))
        assert _dependency_depth("a1", g) == 3


class TestCascadeReach:
    """Test cascade reach computation."""

    def test_no_cascade(self) -> None:
        g = _graph(_comp("a1"))
        assert _cascade_reach("a1", g) == set()

    def test_cascade_chain(self) -> None:
        a, b, c = _comp("a1"), _comp("b1"), _comp("c1")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="b1", target_id="a1"))
        g.add_dependency(Dependency(source_id="c1", target_id="b1"))
        # Failing a1 cascades upstream to b1, then c1
        assert _cascade_reach("a1", g) == {"b1", "c1"}


class TestRiskScoring:
    """Test risk score computation and priority mapping."""

    def test_spof_with_high_dependents(self) -> None:
        db = _comp("db1", ctype=ComponentType.DATABASE)
        apps = [_comp(f"app{i}") for i in range(4)]
        g = _graph(db, *apps)
        for app in apps:
            g.add_dependency(Dependency(source_id=app.id, target_id="db1"))
        score = _compute_risk_score(db, g)
        assert score >= 70  # Should be CRITICAL

    def test_low_risk_component(self) -> None:
        c = _comp("c1", replicas=3, failover=True)
        g = _graph(c)
        score = _compute_risk_score(c, g)
        assert score < 25  # LOW

    def test_priority_mapping_critical(self) -> None:
        assert _risk_score_to_priority(70) == ScenarioPriority.CRITICAL
        assert _risk_score_to_priority(100) == ScenarioPriority.CRITICAL

    def test_priority_mapping_high(self) -> None:
        assert _risk_score_to_priority(50) == ScenarioPriority.HIGH
        assert _risk_score_to_priority(69) == ScenarioPriority.HIGH

    def test_priority_mapping_medium(self) -> None:
        assert _risk_score_to_priority(25) == ScenarioPriority.MEDIUM
        assert _risk_score_to_priority(49) == ScenarioPriority.MEDIUM

    def test_priority_mapping_low(self) -> None:
        assert _risk_score_to_priority(0) == ScenarioPriority.LOW
        assert _risk_score_to_priority(24) == ScenarioPriority.LOW


class TestSelectInjectionType:
    """Test injection type selection based on component type."""

    def test_database_injection(self) -> None:
        c = _comp("db1", ctype=ComponentType.DATABASE)
        assert _select_injection_type(c) == "disk_full"

    def test_cache_injection(self) -> None:
        c = _comp("cache1", ctype=ComponentType.CACHE)
        assert _select_injection_type(c) == "eviction_storm"

    def test_app_server_injection(self) -> None:
        c = _comp("app1", ctype=ComponentType.APP_SERVER)
        assert _select_injection_type(c) == "memory_leak"

    def test_custom_injection_fallback(self) -> None:
        c = _comp("x1", ctype=ComponentType.CUSTOM)
        assert _select_injection_type(c) == "process_crash"


class TestBuildHelpers:
    """Test hypothesis, rollback, blast radius, and success criteria builders."""

    def test_build_hypothesis(self) -> None:
        c = _comp("app1")
        h = _build_hypothesis(c, "memory_leak")
        assert "app1" in h.steady_state
        assert "memory_leak" in h.action
        assert h.validated is None

    def test_build_rollback(self) -> None:
        c = _comp("app1")
        r = _build_rollback(c, "process_crash")
        assert len(r.steps) == 4
        assert r.estimated_time_minutes == 5
        assert r.automated is False

    def test_build_rollback_disk_full(self) -> None:
        c = _comp("db1", ctype=ComponentType.DATABASE)
        r = _build_rollback(c, "disk_full")
        assert r.estimated_time_minutes == 15

    def test_build_rollback_autoscale_automated(self) -> None:
        c = _comp("app1", autoscaling=True)
        r = _build_rollback(c, "process_crash")
        assert r.automated is True

    def test_build_blast_radius_empty_graph(self) -> None:
        c = _comp("a1")
        g = _graph(c)
        br = _build_blast_radius(c, g, 1, 25.0)
        assert br.affected_components == []
        assert br.affected_percentage == 0.0
        assert br.within_safety_boundary is True

    def test_build_blast_radius_exceeds_boundary(self) -> None:
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="b1", target_id="a1"))
        br = _build_blast_radius(a, g, 2, 10.0)
        # b1 depends on a1, so 1 affected out of 2 = 50%
        assert br.affected_percentage == 50.0
        assert br.within_safety_boundary is False

    def test_build_success_criteria_basic(self) -> None:
        c = _comp("app1")
        criteria = _build_success_criteria(c, "process_crash")
        assert len(criteria) == 2
        assert criteria[0].metric == "detection_time_seconds"

    def test_build_success_criteria_with_failover(self) -> None:
        c = _comp("app1", failover=True)
        criteria = _build_success_criteria(c, "process_crash")
        assert len(criteria) == 3
        assert any("failover" in cr.description.lower() for cr in criteria)


# ---------------------------------------------------------------------------
# Test: Scenario generation
# ---------------------------------------------------------------------------


class TestGenerateScenario:
    """Test individual scenario generation."""

    def test_scenario_fields(self) -> None:
        c = _comp("app1")
        g = _graph(c)
        s = _generate_scenario(c, g, DifficultyLevel.INTERMEDIATE, 1)
        assert s.id.startswith("scenario-")
        assert "app1" in s.name
        assert s.target_components == ["app1"]
        assert s.difficulty == DifficultyLevel.INTERMEDIATE
        assert s.hypothesis is not None
        assert s.rollback_plan is not None
        assert len(s.success_criteria) >= 2
        assert len(s.tags) >= 2


class TestPrioritizeComponents:
    """Test component prioritization by risk."""

    def test_spof_ranked_first(self) -> None:
        db = _comp("db1", ctype=ComponentType.DATABASE)
        cache = _comp("cache1", ctype=ComponentType.CACHE, replicas=3, failover=True)
        app = _comp("app1")
        g = _graph(db, cache, app)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        g.add_dependency(Dependency(source_id="app1", target_id="cache1"))
        ranked = _prioritize_components([db, cache, app], g)
        # db1 is SPOF and has a dependent -> highest risk
        assert ranked[0][0].id == "db1"


# ---------------------------------------------------------------------------
# Test: Schedule building
# ---------------------------------------------------------------------------


class TestBuildSchedule:
    """Test schedule construction."""

    def test_schedule_has_three_phases(self) -> None:
        start = datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc)
        schedule = _build_schedule(
            GameDayType.CONTROLLED_INJECTION,
            DifficultyLevel.INTERMEDIATE,
            ["s1"],
            start,
        )
        assert len(schedule) == 3
        assert schedule[0].phase == PhaseType.PRE_GAME_BRIEFING
        assert schedule[1].phase == PhaseType.EXECUTION
        assert schedule[2].phase == PhaseType.POST_GAME_REVIEW

    def test_schedule_times_are_contiguous(self) -> None:
        start = datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc)
        schedule = _build_schedule(
            GameDayType.CONTROLLED_INJECTION,
            DifficultyLevel.BEGINNER,
            ["s1"],
            start,
        )
        assert schedule[0].start_time == start
        assert schedule[0].end_time == schedule[1].start_time
        assert schedule[1].end_time == schedule[2].start_time

    def test_execution_block_contains_scenarios(self) -> None:
        start = datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc)
        schedule = _build_schedule(
            GameDayType.CONTROLLED_INJECTION,
            DifficultyLevel.INTERMEDIATE,
            ["s1", "s2"],
            start,
        )
        assert schedule[1].scenarios == ["s1", "s2"]


# ---------------------------------------------------------------------------
# Test: Participant assignment
# ---------------------------------------------------------------------------


class TestAssignParticipants:
    """Test default participant assignment."""

    def test_tabletop_participants(self) -> None:
        p = _assign_default_participants(GameDayType.TABLETOP)
        roles = [x.role for x in p]
        assert ParticipantRole.GAME_MASTER in roles
        assert ParticipantRole.OPERATOR in roles
        assert ParticipantRole.OBSERVER in roles
        assert len(p) == 3

    def test_controlled_injection_participants(self) -> None:
        p = _assign_default_participants(GameDayType.CONTROLLED_INJECTION)
        assert len(p) == 4

    def test_full_scale_participants(self) -> None:
        p = _assign_default_participants(GameDayType.FULL_SCALE_CHAOS)
        assert len(p) == 6


# ---------------------------------------------------------------------------
# Test: Compliance notes
# ---------------------------------------------------------------------------


class TestComplianceNotes:
    """Test compliance note generation."""

    def test_beginner_no_production(self) -> None:
        notes = _build_compliance_notes(
            GameDayType.CONTROLLED_INJECTION, DifficultyLevel.BEGINNER,
        )
        assert any("staging" in n.lower() for n in notes)

    def test_advanced_allows_production(self) -> None:
        notes = _build_compliance_notes(
            GameDayType.CONTROLLED_INJECTION, DifficultyLevel.ADVANCED,
        )
        assert any("production" in n.lower() for n in notes)

    def test_full_scale_stakeholder_note(self) -> None:
        notes = _build_compliance_notes(
            GameDayType.FULL_SCALE_CHAOS, DifficultyLevel.ADVANCED,
        )
        assert any("stakeholder" in n.lower() for n in notes)


# ---------------------------------------------------------------------------
# Test: Finding and action item generation
# ---------------------------------------------------------------------------


class TestFindingGeneration:
    """Test finding and action item generation."""

    def test_passed_scenario_finding(self) -> None:
        s = Scenario(
            id="s1", name="Test", description="desc",
            target_components=["app1"],
            priority=ScenarioPriority.HIGH,
            difficulty=DifficultyLevel.INTERMEDIATE,
            hypothesis=Hypothesis(
                steady_state="ok", action="kill", observation="recover",
            ),
            rollback_plan=RollbackPlan(description="restart"),
            blast_radius=BlastRadius(),
            injection_type="process_crash",
        )
        f = _generate_finding(s, validated=True)
        assert f.severity == FindingSeverity.INFO
        assert "passed" in f.title.lower()

    def test_failed_critical_scenario_finding(self) -> None:
        s = Scenario(
            id="s1", name="Test", description="desc",
            target_components=["db1"],
            priority=ScenarioPriority.CRITICAL,
            difficulty=DifficultyLevel.ADVANCED,
            hypothesis=Hypothesis(
                steady_state="ok", action="kill", observation="recover",
            ),
            rollback_plan=RollbackPlan(description="restart"),
            blast_radius=BlastRadius(),
            injection_type="disk_full",
        )
        f = _generate_finding(s, validated=False)
        assert f.severity == FindingSeverity.CRITICAL
        assert "failed" in f.title.lower()

    def test_action_item_from_finding(self) -> None:
        f = Finding(
            id="f1", title="Failure", description="bad",
            severity=FindingSeverity.HIGH,
            recommendation="Add replicas",
        )
        a = _generate_action_item(f)
        assert a.priority == ScenarioPriority.HIGH
        assert a.related_finding_id == "f1"
        assert "Add replicas" in a.description


# ---------------------------------------------------------------------------
# Test: Report scoring
# ---------------------------------------------------------------------------


class TestReportScoring:
    """Test report score computation."""

    def test_perfect_score(self) -> None:
        assert _compute_report_score(10, 10, []) == 100.0

    def test_zero_total(self) -> None:
        assert _compute_report_score(0, 0, []) == 0.0

    def test_penalty_for_critical_finding(self) -> None:
        findings = [
            Finding(
                id="f1", title="T", description="D",
                severity=FindingSeverity.CRITICAL,
            ),
        ]
        score = _compute_report_score(5, 5, findings)
        assert score == 80.0

    def test_score_clamps_to_zero(self) -> None:
        findings = [
            Finding(id=f"f{i}", title="T", description="D",
                    severity=FindingSeverity.CRITICAL)
            for i in range(10)
        ]
        score = _compute_report_score(1, 10, findings)
        assert score == 0.0


class TestLessonsLearned:
    """Test lessons learned generation."""

    def test_critical_lesson(self) -> None:
        findings = [
            Finding(id="f1", title="T", description="D",
                    severity=FindingSeverity.CRITICAL),
        ]
        lessons = _generate_lessons_learned(findings)
        assert any("critical" in l.lower() for l in lessons)

    def test_info_lesson(self) -> None:
        findings = [
            Finding(id="f1", title="T", description="D",
                    severity=FindingSeverity.INFO),
        ]
        lessons = _generate_lessons_learned(findings)
        assert any("passed" in l.lower() for l in lessons)

    def test_no_findings_lesson(self) -> None:
        lessons = _generate_lessons_learned([])
        assert len(lessons) == 1
        assert "no scenarios" in lessons[0].lower()


# ---------------------------------------------------------------------------
# Test: ChaosGameDayPlanner
# ---------------------------------------------------------------------------


class TestPlannerCreatePlan:
    """Test ChaosGameDayPlanner.create_plan method."""

    def test_create_plan_basic(self) -> None:
        g = _graph(
            _comp("app1"),
            _comp("db1", ctype=ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        planner = ChaosGameDayPlanner(g)
        plan = planner.create_plan("Test Game Day")
        assert plan.name == "Test Game Day"
        assert plan.game_day_type == GameDayType.CONTROLLED_INJECTION
        assert plan.difficulty == DifficultyLevel.INTERMEDIATE
        assert len(plan.scenarios) > 0
        assert len(plan.schedule) == 3
        assert len(plan.participants) > 0
        assert len(plan.compliance_notes) > 0
        assert plan.id.startswith("gd-")

    def test_create_plan_custom_difficulty(self) -> None:
        g = _graph(_comp("app1"))
        planner = ChaosGameDayPlanner(g)
        plan = planner.create_plan("Beginner Day", difficulty=DifficultyLevel.BEGINNER)
        assert plan.difficulty == DifficultyLevel.BEGINNER

    def test_create_plan_custom_scheduled_date(self) -> None:
        g = _graph(_comp("app1"))
        planner = ChaosGameDayPlanner(g)
        target_date = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
        plan = planner.create_plan("Future Day", scheduled_date=target_date)
        assert plan.scheduled_date == target_date

    def test_create_plan_custom_participants(self) -> None:
        g = _graph(_comp("app1"))
        planner = ChaosGameDayPlanner(g)
        custom = [Participant(name="Bob", role=ParticipantRole.GAME_MASTER)]
        plan = planner.create_plan("Custom Day", participants=custom)
        assert len(plan.participants) == 1
        assert plan.participants[0].name == "Bob"

    def test_create_plan_empty_graph(self) -> None:
        g = _graph()
        planner = ChaosGameDayPlanner(g)
        plan = planner.create_plan("Empty Day")
        assert plan.scenarios == []

    def test_create_plan_tabletop_fewer_scenarios(self) -> None:
        comps = [_comp(f"app{i}") for i in range(5)]
        g = _graph(*comps)
        planner = ChaosGameDayPlanner(g)
        plan = planner.create_plan(
            "Tabletop Day", game_day_type=GameDayType.TABLETOP,
        )
        assert len(plan.scenarios) <= 2


class TestPlannerGenerateScenarios:
    """Test scenario generation logic."""

    def test_no_scenarios_for_empty_graph(self) -> None:
        g = _graph()
        planner = ChaosGameDayPlanner(g)
        assert planner.generate_scenarios() == []

    def test_max_scenarios_respected(self) -> None:
        comps = [_comp(f"c{i}") for i in range(20)]
        g = _graph(*comps)
        planner = ChaosGameDayPlanner(g)
        scenarios = planner.generate_scenarios(difficulty=DifficultyLevel.BEGINNER)
        config = _DIFFICULTY_CONFIG[DifficultyLevel.BEGINNER]
        assert len(scenarios) <= config["max_scenarios"]

    def test_beginner_filters_unsafe_blast_radius(self) -> None:
        # Create a topology where one component has a huge blast radius
        comps = [_comp(f"c{i}") for i in range(20)]
        g = _graph(*comps)
        # All depend on c0 -> blast radius could exceed beginner limit of 10%
        for i in range(1, 20):
            g.add_dependency(Dependency(source_id=f"c{i}", target_id="c0"))
        planner = ChaosGameDayPlanner(g)
        scenarios = planner.generate_scenarios(difficulty=DifficultyLevel.BEGINNER)
        for s in scenarios:
            if s.target_components == ["c0"]:
                # c0 should be filtered out because its blast radius exceeds 10%
                pytest.fail("Should not include scenario with unsafe blast radius")


class TestPlannerPrioritizeScenarios:
    """Test scenario prioritization."""

    def test_critical_first(self) -> None:
        s_low = Scenario(
            id="s1", name="Low", description="",
            target_components=["a"], priority=ScenarioPriority.LOW,
            difficulty=DifficultyLevel.BEGINNER,
            hypothesis=Hypothesis(steady_state="", action="", observation=""),
            rollback_plan=RollbackPlan(description=""),
            blast_radius=BlastRadius(),
        )
        s_critical = Scenario(
            id="s2", name="Critical", description="",
            target_components=["b"], priority=ScenarioPriority.CRITICAL,
            difficulty=DifficultyLevel.BEGINNER,
            hypothesis=Hypothesis(steady_state="", action="", observation=""),
            rollback_plan=RollbackPlan(description=""),
            blast_radius=BlastRadius(),
        )
        g = _graph()
        planner = ChaosGameDayPlanner(g)
        ordered = planner.prioritize_scenarios([s_low, s_critical])
        assert ordered[0].priority == ScenarioPriority.CRITICAL


class TestPlannerBlastRadius:
    """Test blast radius estimation."""

    def test_unknown_component(self) -> None:
        g = _graph(_comp("a1"))
        planner = ChaosGameDayPlanner(g)
        br = planner.estimate_blast_radius("nonexistent")
        assert br.within_safety_boundary is True
        assert br.affected_components == []

    def test_known_component(self) -> None:
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="b1", target_id="a1"))
        planner = ChaosGameDayPlanner(g)
        br = planner.estimate_blast_radius("a1")
        assert "b1" in br.affected_components


class TestPlannerReport:
    """Test report generation."""

    def test_report_with_explicit_results(self) -> None:
        g = _graph(
            _comp("app1"),
            _comp("db1", ctype=ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        planner = ChaosGameDayPlanner(g)
        plan = planner.create_plan("Test Day")
        results = {s.id: True for s in plan.scenarios}
        report = planner.generate_report(plan, results)
        assert report.completed_scenarios == report.total_scenarios
        assert report.overall_score > 0.0
        assert report.plan_name == "Test Day"
        assert report.summary != ""
        assert len(report.lessons_learned) > 0

    def test_report_with_failures(self) -> None:
        g = _graph(_comp("app1"))
        planner = ChaosGameDayPlanner(g)
        plan = planner.create_plan("Fail Day")
        results = {s.id: False for s in plan.scenarios}
        report = planner.generate_report(plan, results)
        assert any(f.severity != FindingSeverity.INFO for f in report.findings)
        assert len(report.action_items) > 0

    def test_report_default_results(self) -> None:
        g = _graph(_comp("app1"))
        planner = ChaosGameDayPlanner(g)
        plan = planner.create_plan("Default Day")
        report = planner.generate_report(plan)
        assert report.completed_scenarios == len(plan.scenarios)


class TestPlannerWeakestLinks:
    """Test weakest link identification."""

    def test_weakest_links_ordering(self) -> None:
        db = _comp("db1", ctype=ComponentType.DATABASE)
        cache = _comp("cache1", ctype=ComponentType.CACHE, replicas=3, failover=True)
        app = _comp("app1")
        g = _graph(db, cache, app)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        planner = ChaosGameDayPlanner(g)
        links = planner.identify_weakest_links(top_n=3)
        assert len(links) == 3
        assert links[0][1] >= links[1][1]  # Descending score

    def test_weakest_links_empty_graph(self) -> None:
        g = _graph()
        planner = ChaosGameDayPlanner(g)
        assert planner.identify_weakest_links() == []


class TestPlannerBuildSchedule:
    """Test planner's schedule building method."""

    def test_build_schedule_uses_plan_date(self) -> None:
        g = _graph(_comp("app1"))
        planner = ChaosGameDayPlanner(g)
        plan = planner.create_plan("Sched Day")
        schedule = planner.build_schedule(plan)
        assert len(schedule) == 3
        assert schedule[0].start_time == plan.scheduled_date

    def test_build_schedule_custom_start(self) -> None:
        g = _graph(_comp("app1"))
        planner = ChaosGameDayPlanner(g)
        plan = planner.create_plan("Sched Day")
        custom = datetime(2027, 1, 1, 8, 0, tzinfo=timezone.utc)
        schedule = planner.build_schedule(plan, start_time=custom)
        assert schedule[0].start_time == custom


class TestPlannerAssignParticipants:
    """Test participant assignment method."""

    def test_assign_custom_participants(self) -> None:
        g = _graph(_comp("app1"))
        planner = ChaosGameDayPlanner(g)
        plan = planner.create_plan("Part Day")
        custom = [Participant(name="Alice", role=ParticipantRole.OPERATOR)]
        updated = planner.assign_participants(plan, custom)
        assert len(updated.participants) == 1
        assert updated.participants[0].name == "Alice"

    def test_assign_default_participants(self) -> None:
        g = _graph(_comp("app1"))
        planner = ChaosGameDayPlanner(g)
        plan = planner.create_plan("Part Day")
        plan.participants = []
        updated = planner.assign_participants(plan)
        assert len(updated.participants) > 0


class TestPlannerValidate:
    """Test plan validation."""

    def test_valid_plan_no_issues(self) -> None:
        g = _graph(_comp("app1"))
        planner = ChaosGameDayPlanner(g)
        plan = planner.create_plan("Valid Day")
        issues = planner.validate_plan(plan)
        assert isinstance(issues, list)
        # A properly generated plan should have no critical issues
        assert not any("no scenarios" in i.lower() for i in issues)
        assert not any("no participants" in i.lower() for i in issues)
        assert not any("no game master" in i.lower() for i in issues)

    def test_empty_plan_has_issues(self) -> None:
        now = datetime.now(timezone.utc)
        plan = GameDayPlan(
            id="gd-test", name="Empty",
            game_day_type=GameDayType.TABLETOP,
            difficulty=DifficultyLevel.BEGINNER,
            description="", created_at=now, scheduled_date=now,
        )
        g = _graph()
        planner = ChaosGameDayPlanner(g)
        issues = planner.validate_plan(plan)
        assert any("no scenarios" in i.lower() for i in issues)
        assert any("no participants" in i.lower() for i in issues)

    def test_multiple_game_masters_issue(self) -> None:
        now = datetime.now(timezone.utc)
        plan = GameDayPlan(
            id="gd-test", name="Multi GM",
            game_day_type=GameDayType.TABLETOP,
            difficulty=DifficultyLevel.BEGINNER,
            description="", created_at=now, scheduled_date=now,
            participants=[
                Participant(name="GM1", role=ParticipantRole.GAME_MASTER),
                Participant(name="GM2", role=ParticipantRole.GAME_MASTER),
            ],
            schedule=[
                ScheduleBlock(
                    phase=PhaseType.EXECUTION,
                    start_time=now, end_time=now + timedelta(hours=1),
                )
            ],
        )
        g = _graph()
        planner = ChaosGameDayPlanner(g)
        issues = planner.validate_plan(plan)
        assert any("multiple game masters" in i.lower() for i in issues)

    def test_blast_radius_exceeds_boundary_issue(self) -> None:
        # Manually create a plan with an unsafe scenario
        now = datetime.now(timezone.utc)
        scenario = Scenario(
            id="s1", name="Unsafe", description="",
            target_components=["a1"],
            priority=ScenarioPriority.HIGH,
            difficulty=DifficultyLevel.ADVANCED,
            hypothesis=Hypothesis(steady_state="", action="", observation=""),
            rollback_plan=RollbackPlan(description="rollback", steps=["step1"]),
            blast_radius=BlastRadius(
                affected_percentage=60.0,
                max_allowed_percentage=25.0,
                within_safety_boundary=False,
            ),
        )
        plan = GameDayPlan(
            id="gd-test", name="Unsafe Plan",
            game_day_type=GameDayType.CONTROLLED_INJECTION,
            difficulty=DifficultyLevel.ADVANCED,
            description="", created_at=now, scheduled_date=now,
            participants=[Participant(name="GM", role=ParticipantRole.GAME_MASTER)],
            scenarios=[scenario],
            schedule=[
                ScheduleBlock(
                    phase=PhaseType.EXECUTION,
                    start_time=now, end_time=now + timedelta(hours=1),
                )
            ],
        )
        g = _graph()
        planner = ChaosGameDayPlanner(g)
        issues = planner.validate_plan(plan)
        assert any("blast radius" in i.lower() for i in issues)


class TestPlannerRiskHeatmap:
    """Test risk heatmap generation."""

    def test_heatmap_structure(self) -> None:
        db = _comp("db1", ctype=ComponentType.DATABASE)
        app = _comp("app1")
        g = _graph(db, app)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        planner = ChaosGameDayPlanner(g)
        heatmap = planner.risk_heatmap()
        assert "db1" in heatmap
        assert "app1" in heatmap
        assert "risk_score" in heatmap["db1"]
        assert "priority" in heatmap["db1"]
        assert "is_spof" in heatmap["db1"]
        assert "dependent_count" in heatmap["db1"]
        assert "has_failover" in heatmap["db1"]
        assert "has_circuit_breaker" in heatmap["db1"]

    def test_heatmap_spof_detected(self) -> None:
        db = _comp("db1", ctype=ComponentType.DATABASE)
        app = _comp("app1")
        g = _graph(db, app)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        planner = ChaosGameDayPlanner(g)
        heatmap = planner.risk_heatmap()
        assert heatmap["db1"]["is_spof"] is True
        assert heatmap["db1"]["dependent_count"] == 1

    def test_heatmap_empty_graph(self) -> None:
        g = _graph()
        planner = ChaosGameDayPlanner(g)
        assert planner.risk_heatmap() == {}


# ---------------------------------------------------------------------------
# Test: Summary generation
# ---------------------------------------------------------------------------


class TestGenerateSummary:
    """Test report summary text generation."""

    def test_summary_contains_plan_name(self) -> None:
        now = datetime.now(timezone.utc)
        plan = GameDayPlan(
            id="gd-1", name="My Day",
            game_day_type=GameDayType.TABLETOP,
            difficulty=DifficultyLevel.BEGINNER,
            description="", created_at=now, scheduled_date=now,
        )
        summary = _generate_summary(plan, 5, 5, 100.0, [])
        assert "My Day" in summary
        assert "5/5" in summary
        assert "100.0" in summary

    def test_summary_with_critical_findings(self) -> None:
        now = datetime.now(timezone.utc)
        plan = GameDayPlan(
            id="gd-1", name="Test",
            game_day_type=GameDayType.CONTROLLED_INJECTION,
            difficulty=DifficultyLevel.INTERMEDIATE,
            description="", created_at=now, scheduled_date=now,
        )
        findings = [
            Finding(id="f1", title="T", description="D",
                    severity=FindingSeverity.CRITICAL),
        ]
        summary = _generate_summary(plan, 3, 5, 60.0, findings)
        assert "critical" in summary.lower()


# ---------------------------------------------------------------------------
# Test: Configuration constants
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Cover remaining edge cases for 100% coverage."""

    def test_dependency_depth_with_cycle(self) -> None:
        """Graph with a cycle should not loop forever."""
        a, b = _comp("a1"), _comp("b1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        g.add_dependency(Dependency(source_id="b1", target_id="a1"))
        depth = _dependency_depth("a1", g)
        assert depth >= 1  # Must terminate

    def test_risk_score_deep_chain(self) -> None:
        """Component at the top of a chain >= 3 deep gets deep_chain weight."""
        a, b, c = _comp("a1"), _comp("b1"), _comp("c1")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        g.add_dependency(Dependency(source_id="b1", target_id="c1"))
        score = _compute_risk_score(a, g)
        # depth of a1 == 3, so deep_chain weight should apply
        assert score >= _PRIORITY_WEIGHTS["deep_chain"]

    def test_report_score_penalty_high(self) -> None:
        """HIGH findings should subtract 10 from score."""
        findings = [
            Finding(id="f1", title="T", description="D",
                    severity=FindingSeverity.HIGH),
        ]
        score = _compute_report_score(5, 5, findings)
        assert score == 90.0

    def test_report_score_penalty_medium(self) -> None:
        """MEDIUM findings should subtract 5 from score."""
        findings = [
            Finding(id="f1", title="T", description="D",
                    severity=FindingSeverity.MEDIUM),
        ]
        score = _compute_report_score(5, 5, findings)
        assert score == 95.0

    def test_summary_with_high_findings(self) -> None:
        """Summary should mention high findings when present."""
        now = datetime.now(timezone.utc)
        plan = GameDayPlan(
            id="gd-1", name="Test",
            game_day_type=GameDayType.CONTROLLED_INJECTION,
            difficulty=DifficultyLevel.INTERMEDIATE,
            description="", created_at=now, scheduled_date=now,
        )
        findings = [
            Finding(id="f1", title="T", description="D",
                    severity=FindingSeverity.HIGH),
        ]
        summary = _generate_summary(plan, 3, 5, 80.0, findings)
        assert "high" in summary.lower()

    def test_lessons_learned_high_severity(self) -> None:
        """HIGH-severity findings should produce remediation lesson."""
        findings = [
            Finding(id="f1", title="T", description="D",
                    severity=FindingSeverity.HIGH),
        ]
        lessons = _generate_lessons_learned(findings)
        assert any("high" in l.lower() for l in lessons)

    def test_validate_no_rollback_steps(self) -> None:
        """Scenario with empty rollback steps should be flagged."""
        now = datetime.now(timezone.utc)
        scenario = Scenario(
            id="s1", name="No Rollback", description="",
            target_components=["a1"],
            priority=ScenarioPriority.MEDIUM,
            difficulty=DifficultyLevel.BEGINNER,
            hypothesis=Hypothesis(steady_state="", action="", observation=""),
            rollback_plan=RollbackPlan(description="empty", steps=[]),
            blast_radius=BlastRadius(),
        )
        plan = GameDayPlan(
            id="gd-test", name="Rollback Test",
            game_day_type=GameDayType.CONTROLLED_INJECTION,
            difficulty=DifficultyLevel.BEGINNER,
            description="", created_at=now, scheduled_date=now,
            participants=[Participant(name="GM", role=ParticipantRole.GAME_MASTER)],
            scenarios=[scenario],
            schedule=[
                ScheduleBlock(
                    phase=PhaseType.EXECUTION,
                    start_time=now, end_time=now + timedelta(hours=1),
                )
            ],
        )
        g = _graph()
        planner = ChaosGameDayPlanner(g)
        issues = planner.validate_plan(plan)
        assert any("rollback" in i.lower() for i in issues)

    def test_validate_no_schedule(self) -> None:
        """Plan with no schedule should be flagged."""
        now = datetime.now(timezone.utc)
        plan = GameDayPlan(
            id="gd-test", name="No Sched",
            game_day_type=GameDayType.TABLETOP,
            difficulty=DifficultyLevel.BEGINNER,
            description="", created_at=now, scheduled_date=now,
            participants=[Participant(name="GM", role=ParticipantRole.GAME_MASTER)],
            scenarios=[
                Scenario(
                    id="s1", name="S", description="",
                    target_components=["a1"],
                    priority=ScenarioPriority.LOW,
                    difficulty=DifficultyLevel.BEGINNER,
                    hypothesis=Hypothesis(steady_state="", action="", observation=""),
                    rollback_plan=RollbackPlan(description="r", steps=["s"]),
                    blast_radius=BlastRadius(),
                )
            ],
        )
        g = _graph()
        planner = ChaosGameDayPlanner(g)
        issues = planner.validate_plan(plan)
        assert any("no schedule" in i.lower() for i in issues)


class TestConfigConstants:
    """Test configuration constants are properly defined."""

    def test_difficulty_config_keys(self) -> None:
        for level in DifficultyLevel:
            assert level in _DIFFICULTY_CONFIG

    def test_injection_map_covers_all_types(self) -> None:
        for ct in ComponentType:
            assert ct in _COMPONENT_INJECTION_MAP

    def test_priority_weights_sum(self) -> None:
        total = sum(_PRIORITY_WEIGHTS.values())
        assert total == 100
